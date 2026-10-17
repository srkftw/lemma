#!/usr/bin/env python3
"""Source-derived S-WFI/M-timer diagnostic and independent reset observations.
Host code supplies clocks and observes bytes; no debugger CSR writes or cache test.
"""
from __future__ import annotations
import argparse, json, os, re, signal, struct, subprocess, time
from pathlib import Path
from core0_common import Core0Error, load_json, repo_root, require_tools, sha256, write_json
from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS
from build_kernel import command_invoker, realize_toolchain, source_inputs
from audit_kernel import (validate_ir, validate_machine, function_ranges, defined_function_symbols,
    parse_load_segments, relocation_types, validate_compiled_stack, weighted_stack_graph,
    INTEGER_INSTRUCTIONS, KNOWN_CSRS)
from audit_core0 import parse_stack_sizes

POLICY='Lemma.Platform.RiscV.Development.WfiTimerPolicy.'
FIRMWARE='Lemma.Platform.RiscV.Development.WfiTimerFirmware.'
BASE=0x80410000
SIZE=32768
TRACE=0x80101000
INTERVALS=(8192,1000,1001,4096)
MAGIC=0x57464954494d4501
DONE=0x574649444f4e4501
OPS={
 'physicalRead64':('physical-read64',None,1,8,False,True,[]),
 'physicalWrite64':('physical-write64',None,2,8,True,True,[]),
 'firmwareCall':('firmware-call','lemma_exec_firmware_call',6,None,False,False,['u64']*6),
 'waitInterrupt':('wait-interrupt','lemma_exec_wait_interrupt',0,None,False,False,[]),
 'readSupervisorPending':('supervisor-pending','lemma_exec_supervisor_pending',0,None,False,False,[]),
 'readTime':('read-time','lemma_exec_read_time',0,None,False,False,[]),
 'setMachineCompare':('set-machine-compare','lemma_exec_set_machine_compare',1,None,False,False,['u64']),
 'forwardSupervisor':('forward-supervisor','lemma_exec_forward_supervisor',1,None,False,False,['u64']),
}

def require(value,message):
 if not value: raise Core0Error(message)

def validate_unit(unit,role):
 require(type(unit) is dict and set(unit)=={'schema_version','artifact_category','configuration','contract_version','role','roots','functions','used_execution_ops','used_device_ops','used_loops'},'WFI unit keys differ')
 require(type(unit['schema_version']) is int and unit['schema_version']==1 and
  unit['artifact_category']=='development-wfi-timer-execution-unit' and
  unit['configuration']=='wfi-timer-development-v1' and unit['role']==role and
  unit['contract_version']=={'kernel':'core0-kernel-v0.4','firmware':'core0-firmware-v0.1'}[role], 'WFI unit authority differs')
 rows=unit['functions'];require(type(rows) is list and rows,'WFI functions absent')
 prefixes=(POLICY,) if role=='kernel' else (FIRMWARE,'Lemma.Platform.RiscV.Firmware.')
 for row in rows:
  require(type(row) is dict and set(row)=={'source','symbol','args','effects'} and
   type(row['source']) is str and (row['source'].startswith(prefixes) or
    (role=='kernel' and row['source']=='Lemma.Core0.Memory.Status.iterationStop' and row['args']==[] and row['effects']==[])) and
   type(row['symbol']) is str and re.fullmatch('lemma_wfi_'+('s_' if role=='kernel' else 'm_')+'[A-Za-z0-9_]+',row['symbol']) and
   type(row['args']) is list and all(t in ('bool','u8','u32','u64') for t in row['args']) and
   type(row['effects']) is list and len(set(row['effects']))==len(row['effects']) and
   set(row['effects'])<= {'checked-access','physical-read','physical-write','machine-state','mmio-read','mmio-write','io-order','timer-state','sync-trap','interrupt-state','firmware-call','wait-state'}, 'WFI complete function signature/effects differ')
 names={r['source']:r['symbol'] for r in rows}
 require(len(names)==len(rows) and len(set(names.values()))==len(rows),'WFI duplicate source/symbol')
 roots=[(POLICY+'main',[]),(POLICY+'dispatch',['u64']*3)] if role=='kernel' else [(FIRMWARE+'dispatch',['u64']*3)]
 require(unit['roots']==[{'source':s,'symbol':names.get(s),'args':a} for s,a in roots],'WFI exact genuine roots differ')
 require(unit['used_device_ops']==[] and unit['used_loops']==[],'WFI unadmitted device/loop closure')
 ops=unit['used_execution_ops'];require(type(ops) is list and all(type(r) is dict for r in ops),'WFI operation rows absent')
 by={r.get('source_identity','').rsplit('.',1)[-1]:r for r in ops}
 expected={'physicalRead64','physicalWrite64','firmwareCall','waitInterrupt','readSupervisorPending'} if role=='kernel' else {'physicalRead64','physicalWrite64','readTime','setMachineCompare','forwardSupervisor'}
 require(len(by)==len(ops) and set(by)==expected,'WFI operation privilege closure differs')
 for name,row in by.items():
  stable,symbol,meaningful,width,write,physical,args=OPS[name]
  require(row=={'stable_id':'execution.'+stable,'source_identity':'Lemma.Core0.Execution.Op.'+name,
   'primitive_symbol':symbol,'arguments':args,'source_arguments':['u64']*6,'meaningful_arguments':meaningful,
   'result':'u64','returnkind':'checked' if name=='firmwareCall' else 'word','width_bytes':width,'write':write,'physical':physical},'WFI exact operation ABI differs:'+name)
 return names

def validate_records(raw,trace,boot,ranges,boot_status):
 require(len(raw)==SIZE and len(trace)==256,'WFI record capacity differs')
 words=list(struct.unpack('<4096Q',raw));h=words[:32]
 expected={0:MAGIC,1:boot,2:0x30,3:DONE,4:4,5:22,6:22,7:0x534543414c4c0001}
 for i,v in expected.items(): require(h[i]==v,f'WFI actual header{i} differs')
 require(all(v==0 for v in h[8:]) and all(v==0 for v in words[96:]),'WFI guest-cleared reserved bytes differ')
 fw=list(struct.unpack('<32Q',trace));rows=[];traps=[]
 for i,ticks in enumerate(INTERVALS):
  row=words[32+16*i:48+16*i];cause,tval,pc,status,enables,now,ordinal,after_fw=fw[8*i:8*i+8]
  require(row[0:2]==[i,ticks] and row[5:7]==[i,i+1] and row[7] in (0,1) and
   1<=row[8]<=65536 and row[9]==1 and row[11]==i+1 and all(v==0 for v in row[12:]), f'WFI finite identity/count/pending differs at{i}')
  require(0<row[2]<row[3]<=now<=after_fw<=row[4]<=row[10],f'WFI actual deadline/time order differs at{i}')
  require(row[3]-row[2]>=ticks,'firmware deadline did not include requested relative interval')
  require(cause==0x8000000000000007 and tval==0 and ordinal==i and status==boot_status and enables==0x282,'actual timer cause/tval/full status/enables/origin differs')
  require(any(address<=pc<address+size for name,(address,size) in ranges.items()
   if name.startswith('lemma_wfi_s_') or name in ('lemma_exec_wait_interrupt','lemma_exec_supervisor_pending')) and pc%4==0,'actual timer saved PC escapes compiled S suffix')
  rows.append(row);traps.append([cause,tval,pc,status,enables,now,ordinal,after_fw])
 return {'header':h,'rows':rows,'timer_frames':traps,'WFI_calls':sum(r[8]+1 for r in rows),
  'spurious_or_nonnotification_returns':sum(r[8]-1 for r in rows),
  'record_sha256':__import__('hashlib').sha256(raw).hexdigest(), 'checked_bytes':SIZE+256}

def diagnostic_inputs(root):
 pending=['Lemma.Compiler.WfiTimerExport'];seen=set()
 while pending:
  name=pending.pop()
  if name in seen: continue
  seen.add(name);p=root/(name.replace('.','/')+'.lean')
  require(p.is_file(),'missing genuine WFI import:'+name)
  for line in p.read_text().splitlines():
   if line.startswith('import '): pending.extend(n for n in line[7:].split() if n.startswith('Lemma.'))
 lean={n.replace('.','/')+'.lean' for n in seen}
 result={n:h for n,h in source_inputs(root).items() if not n.endswith('.lean') or n in lean}
 require(lean<=result.keys(),'WFI true imports absent from source inventory')
 result['scripts/check_guest_wfi_timer.py']=sha256(root/'scripts/check_guest_wfi_timer.py')
 return result

def _audit_platform(text,ranges,primitives):
 selected={n:ranges[n] for n in primitives};expected={a for start,size in selected.values() for a in range(start,start+size,4)};observed=set()
 for line in text.splitlines():
  m=re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)',line)
  if not m: continue
  address=int(m[1],16)
  if address not in expected: continue
  require(address not in observed and m[2] in INTEGER_INSTRUCTIONS,'unknown/duplicate generated machine instruction');observed.add(address)
  if m[2].startswith('csr'):
   csr=set(re.findall(r'\b(?:[ms][a-z][a-z0-9]+|satp|pmp[a-z0-9]+)\b',m[3]))
   require(csr and csr<=KNOWN_CSRS|{'pmpaddr5','pmpaddr6','pmpaddr7'},'generated diagnostic CSR escape')
 require(observed==expected,'generated machine function instruction coverage differs')
 return {'functions':selected,'four_byte_instructions':len(observed),'scope':'unchanged normal LemmaSim structured supervisor startup/primitives only'}

def build(root,out,timeout):
 tools=require_tools(('git','nix','lake','lean','opt','llc','clang','ld.lld','llvm-objcopy','llvm-readelf','llvm-nm','llvm-objdump','qemu-system-riscv64','dtc','flock'))
 commands=[];raw=command_invoker(root,out,tools,timeout,commands)
 def invoke(argv,cwd=out,env=None):
  if argv[0]=='lake': argv=('flock',str(root/'build/task006-lake.lock'),*argv)
  if argv[0]=='llvm-readelf': argv=(argv[0],'--elf-output-style=GNU',*argv[1:])
  return raw(argv,cwd,env)
 before=diagnostic_inputs(root);archive=out/'consumed-source-root';archive.mkdir()
 for name,digest in before.items():
  dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((root/name).read_bytes())
  require(sha256(dest)==digest,'WFI source archive differs:'+name)
 write_json(archive/'source-inputs.json',{'schema':'lemma-wfi-timer-source/1','source_inputs':before})
 versions,upstream=realize_toolchain(root,tools,invoke)
 invoke(('lake','build','Lemma.Compiler.WfiTimerExport'),root)
 consumer=out/'Export.lean';consumer.write_text('import Lemma.Compiler.WfiTimerExport\n\n#lemma_export_wfi_timer_probe\n')
 target=out/'target';invoke(('lake','env','lean',str(consumer.relative_to(root))),root,{**os.environ,'LEMMA_WFI_TIMER_OUTPUT':str(target)})
 units={};names={};ir={};stacks={}
 for role in ('firmware','kernel'):
  path=target/role;unit=load_json(path/'unit.json');units[role]=unit;names.update(validate_unit(unit,role))
  invoke(('opt','-S','-passes=default<O2>','program.ll','-o','program.opt.ll'),path)
  invoke(('llc',*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'),path)
  pre=(path/'program.ll').read_text();post=(path/'program.opt.ll').read_text()
  ir[role]={'before':validate_ir(pre,unit,optimized=False),'after':validate_ir(post,unit,optimized=True,optimization='O2')}
  frames=parse_stack_sizes(invoke(('llvm-readelf','--stack-sizes','program.o'),path).decode())
  validate_compiled_stack(invoke(('llvm-objdump','-d','--no-show-raw-insn','program.o'),path).decode(),frames)
  primitive={r['primitive_symbol']:0 for r in unit['used_execution_ops'] if r['primitive_symbol']}|{'core0_io_fence':0}
  stacks[role]=weighted_stack_graph(post,frames,primitive)
  for row in unit['roots']:
   limit=65536-4096 if role=='kernel' else 65536-4096-288
   require(stacks[role]['weighted_frame_chains'][row['symbol']]['bytes']<=limit,'WFI compiled stack overlaps reserved context')
 invoke(('clang',*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'),target)
 invoke(('ld.lld','-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map','startup.o','firmware/program.o','kernel/program.o','-o','image.elf'),target)
 symbols=invoke(('llvm-readelf','-s','--wide','image.elf'),target).decode();ranges=function_ranges(symbols)
 layout=load_json(target/'layout.json');primitives={r['symbol'] for r in layout['primitives']}
 require(defined_function_symbols(symbols)==set(names.values())|primitives,'WFI exact linked executable closure differs')
 require(not invoke(('llvm-nm','--undefined-only','image.elf'),target).strip(),'WFI foreign runtime dependency')
 require(not relocation_types(invoke(('llvm-readelf','-r','image.elf'),target).decode()),'WFI runtime relocation')
 header=invoke(('llvm-readelf','-h','image.elf'),target).decode();attrs=invoke(('llvm-readelf','-A','image.elf'),target).decode()
 require(all(v in header for v in ('ELF64','little endian','RISC-V','0x80000000')) and re.search(r'Flags:\s+0x0(?:\s|$)',header),'WFI ELF hardware attributes differ')
 require('rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0' in attrs,'WFI unsupported ISA')
 segments=parse_load_segments(invoke(('llvm-readelf','-l','--wide','image.elf'),target).decode())
 require(len(segments)==3 and all(r['physical_address']==r['virtual_address'] and not ('W' in r['flags'] and 'E' in r['flags']) for r in segments),'WFI load segment authority differs')
 for r,(base,limit) in zip(segments,((0x80000000,0x80010000),(0x80200000,0x80300000),(0x80400000,0x80400080))):
  require(base==r['virtual_address'] and 0<r['memory_size']<=limit-base,'WFI image escapes fixed envelope')
 disasm=invoke(('llvm-objdump','-d','--no-show-raw-insn','image.elf'),target).decode()
 validate_machine(disasm,ranges={n:ranges[n] for n in names.values()})
 platform=_audit_platform(disasm,ranges,primitives)
 invoke(('llvm-objcopy','-O','binary','--only-section=.text','image.elf','supervisor.bin'),target)
 code=(target/'supervisor.bin').read_bytes();start,size=ranges['lemma_exec_wait_interrupt']
 require(size==12 and code[start-0x80200000:start-0x80200000+12]==struct.pack('<3I',0x10500073,0x00000513,0x00008067),'actual S WFI/return instruction bytes differ')
 require(diagnostic_inputs(root)==before,'WFI producer consumed source changed')
 receipt={'schema':'lemma-wfi-timer-producer/1','status':'PASS_AUDIT','source_inputs':before,'tools':versions,'upstream':upstream,'units':units,'source_symbols':names,'functions':ranges,'ir':ir,'stack':stacks,'platform':platform,'linked_objects':['startup.o','firmware/program.o','kernel/program.o'],'files':{str(p.relative_to(target)):sha256(p) for p in target.rglob('*') if p.is_file()},'guest_sha256':sha256(target/'image.elf')}
 write_json(out/'audit.json',receipt);return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('--build-only',action='store_true',required=True)
 a=p.parse_args();require(1<=a.timeout<=120,'original producer command bound is120s')
 out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic();result={'status':'FAIL','scope':'genuine existing-profile WFI diagnostic build/audit only; no CPU'}
 try:
  result['audit']=build(repo_root(),out,a.timeout);result['status']='PASS_PRODUCER'
 except BaseException as e: result['error']=repr(e);raise
 finally:
  result['seconds']=time.monotonic()-started;write_json(out/'producer-result.json',result)
 print('WFI_TIMER:PASS_PRODUCER')
if __name__=='__main__': main()
