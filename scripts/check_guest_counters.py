#!/usr/bin/env python3
"""Genuine Lean RV64 counter program, closed object audit and actual RTL suffix.

Host-only orchestration/raw RAM observations. It never issues a debugger CSR
write, constructs a target program, or substitutes an instruction count for the
reference pipeline clock. Development ELF-preload execution is explicit.
"""
from __future__ import annotations
import argparse,json,os,re,select,signal,struct,subprocess,sys,tempfile,time
from pathlib import Path
from core0_common import Core0Error,load_json,repo_root,require_tools,sha256,write_json
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from build_kernel import command_invoker,realize_toolchain,source_inputs
from audit_kernel import (validate_ir,validate_machine,function_ranges,defined_function_symbols,
                         parse_load_segments,relocation_types,validate_compiled_stack,weighted_stack_graph)
from audit_core0 import parse_definitions_and_calls,parse_stack_sizes

SOURCE='Lemma.Platform.RiscV.Development.CounterPolicy.'
ROOT_SOURCE=SOURCE+'main'
CSR_OPERATIONS={
 'readMisa':('read-misa','lemma_exec_read_misa',0x301,False),
 'readMachineCycle':('read-machine-cycle','lemma_exec_read_machine_cycle',0xb00,False),
 'writeMachineCycle':('write-machine-cycle','lemma_exec_write_machine_cycle',0xb00,True),
 'readMachineRetired':('read-machine-retired','lemma_exec_read_machine_retired',0xb02,False),
 'writeMachineRetired':('write-machine-retired','lemma_exec_write_machine_retired',0xb02,True),
 'readMachineInhibit':('read-machine-inhibit','lemma_exec_read_machine_inhibit',0x320,False),
 'writeMachineInhibit':('write-machine-inhibit','lemma_exec_write_machine_inhibit',0x320,True),
 'readMachineCounterEnable':('read-machine-counter-enable','lemma_exec_read_machine_counter_enable',0x306,False),
 'writeMachineCounterEnable':('write-machine-counter-enable','lemma_exec_write_machine_counter_enable',0x306,True),
}

def require(value,message):
 if not value:raise Core0Error(message)

def validate_records(data):
 require(len(data)==25*8,'counter record capacity differs')
 r=list(struct.unpack('<25Q',data))
 require(r[0]==0x4353524755455354 and r[23]==0x4353525041535301,'compiled guest counter completion missing')
 require(r[1]==0x8000000000141100,'actual MISA differs from declared RV64IM/S/U profile')
 require(r[2:5]==[5,7,0],'actual inhibit/counter-enable WARL or clearing differs')
 require(r[24]==0,'actual cold/warm reset retained inhibit bits')
 require(r[5]==r[8]==123456 and r[6]==r[9]==789 and r[10]>r[7],
         'guest-written/inhibited counters changed, or MTIME was inhibited')
 require(r[11]>123456 and r[12]>789,'counters failed to resume')
 require(r[13]==r[15]==1000 and 2000<r[14]<r[16],'CY inhibition also inhibited IR, or CY changed')
 require(3000<r[17]<r[19] and r[18]==r[20]==4000,'IR inhibition also inhibited CY, or IR changed')
 require(r[21]<65536 and r[22]<65536,'modulo64 counter wrap differs')
 return r

def validate_unit(unit):
 require(isinstance(unit,dict) and unit.get('schema_version')==1 and
  unit.get('artifact_category')=='development-counter-execution-unit' and
  unit.get('configuration')=='counter-csr-development' and unit.get('role')=='firmware' and
  unit.get('contract_version')=='core0-firmware-v0.2','counter unit version/category differs')
 require(set(unit)=={'schema_version','artifact_category','configuration','contract_version','role','roots','functions','used_execution_ops','used_device_ops','used_loops'},'counter unit keys differ')
 rows=unit.get('functions');require(isinstance(rows,list) and rows,'counter function inventory missing')
 for row in rows:
  require(isinstance(row,dict) and set(row)=={'source','symbol','args','effects'} and
   isinstance(row['args'],list) and all(t in ('bool','u8','u32','u64') for t in row['args']) and
   isinstance(row['effects'],list) and len(set(row['effects']))==len(row['effects']) and
   set(row['effects'])<= {'checked-access','physical-write','machine-state','mmio-read','io-order','timer-state'},'counter function signature/effects differ')
 names={r.get('source'):r.get('symbol') for r in rows}
 require(len(names)==len(rows) and len(set(names.values()))==len(rows) and
  all(isinstance(s,str) and s.startswith(SOURCE) and re.fullmatch(r'lemma_counter_[A-Za-z0-9_]+',v or '') for s,v in names.items()),
  'counter reachable function/symbol closure differs')
 require(unit.get('roots')==[{'source':ROOT_SOURCE,'symbol':names.get(ROOT_SOURCE),'args':[]}],
  'counter entry is not the exact selected genuine source root')
 require(unit.get('used_loops')==[] and unit.get('used_device_ops')==[],'unadmitted loop/device in counter unit')
 ops=unit.get('used_execution_ops');require(isinstance(ops,list) and len(ops)==11,'counter operation count differs')
 by={r.get('source_identity','').rsplit('.',1)[-1]:r for r in ops}
 require(len(by)==len(ops) and set(by)==set(CSR_OPERATIONS)|{'physicalWrite64','readTime'},'counter source operation closure differs')
 for name,(ident,symbol,_,write) in CSR_OPERATIONS.items():
  r=by[name]
  require(set(r)=={'stable_id','source_identity','primitive_symbol','arguments','source_arguments','meaningful_arguments','result','returnkind','width_bytes','write','physical'} and
   r['width_bytes'] is None and r['physical'] is False and r['write']==write and r['result']=='u64','counter primitive effects/metadata differ: '+name)
  require(r.get('stable_id')=='execution.'+ident and r.get('primitive_symbol')==symbol and
   r.get('arguments')==(['u64'] if write else []) and r.get('returnkind')=='word' and
   r.get('source_arguments')==['u64']*6 and r.get('meaningful_arguments')==(1 if write else 0),
   'counter primitive ABI/identity differs: '+name)
 require(by['physicalWrite64']['primitive_symbol'] is None and by['physicalWrite64']['width_bytes']==8 and
  by['physicalWrite64']['physical'] is True and by['physicalWrite64']['write'] is True,'counter record write authority differs')
 return names

def validate_csr_bytes(code,base,ranges):
 checked={}
 for _,(_,symbol,csr,write) in CSR_OPERATIONS.items():
  require(symbol in ranges,'missing actual CSR primitive '+symbol)
  address,size=ranges[symbol]
  # Independently encode the declared single CSR access, ABI result and return.
  access=(csr<<20)|((10 if write else 0)<<15)|((1 if write else 2)<<12)|((0 if write else 10)<<7)|0x73
  words=[access,0x00000513,0x00008067] if write else [access,0x00008067]
  require(size==4*len(words) and address>=base and address+size<=base+len(code),'CSR primitive range differs')
  actual=code[address-base:address-base+size]
  require(actual==struct.pack('<'+'I'*len(words),*words),'CSR primitive actual instruction bytes differ: '+symbol)
  checked[symbol]={'csr':csr,'write':write,'instruction_words':words,'bytes':size}
 return checked

def build(root,out,timeout):
 tools=require_tools(('git','nix','lake','lean','opt','llc','clang','ld.lld','llvm-objcopy','llvm-readelf',
                      'llvm-nm','llvm-objdump','qemu-system-riscv64','dtc'))
 commands=[];raw_invoke=command_invoker(root,out,tools,timeout,commands)
 # require_tools resolves the readelf symlink to llvm-readobj. Select the
 # documented GNU output explicitly; stack metadata is still fail-closed.
 def invoke(argv,cwd=out,env=None):
  selected=(argv[0],'--elf-output-style=GNU',*argv[1:]) if argv[0]=='llvm-readelf' else argv
  return raw_invoke(selected,cwd,env)
 before=source_inputs(root);before['scripts/check_guest_counters.py']=sha256(root/'scripts/check_guest_counters.py')
 versions,upstream=realize_toolchain(root,tools,invoke)
 invoke(('lake','build','Lemma.Compiler.CounterExport'),root)
 consumer=out/'Export.lean';consumer.write_text('import Lemma.Compiler.CounterExport\n\n#lemma_export_counter_probe\n')
 target=out/'target';env={**os.environ,'LEMMA_COUNTER_OUTPUT':str(target)}
 invoke(('lake','env','lean',str(consumer.relative_to(root))),root,env)
 unit=load_json(target/'unit.json');names=validate_unit(unit)
 invoke(('opt','-S','-passes=default<O2>','program.ll','-o','program.opt.ll'),target)
 invoke(('llc',*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'),target)
 invoke(('clang',*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'),target)
 invoke(('ld.lld','-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map','startup.o','program.o','-o','image.elf'),target)
 pre=(target/'program.ll').read_text();post=(target/'program.opt.ll').read_text()
 frames=parse_stack_sizes(invoke(('llvm-readelf','--stack-sizes','program.o'),target).decode())
 program_disasm=invoke(('llvm-objdump','-d','--no-show-raw-insn','program.o'),target).decode()
 validate_compiled_stack(program_disasm,frames)
 stack=weighted_stack_graph(post,frames,{s:0 for _,s,_,_ in CSR_OPERATIONS.values()}|{'lemma_exec_read_time':0})
 require(max(row['bytes'] for row in stack['weighted_frame_chains'].values())<=8192,'counter bounded stack overlaps record/storage envelope')
 ir={'before':validate_ir(pre,unit,optimized=False),
     'after':validate_ir(post,unit,optimized=True,optimization='O2')}
 symbols=invoke(('llvm-readelf','-s','--wide','image.elf'),target).decode()
 ranges=function_ranges(symbols)
 expected=set(names.values())|{symbol for _,symbol,_,_ in CSR_OPERATIONS.values()}|{'_start','lemma_exec_read_time'}
 require(defined_function_symbols(symbols)==expected,'counter ELF executable provenance differs')
 header=invoke(('llvm-readelf','-h','image.elf'),target).decode()
 require(all(t in header for t in ('ELF64','little endian','RISC-V')) and
  re.search(r'Flags:\s+0x0(?:\s|$)',header) and '0x80000000' in header,'counter ELF hardware attributes differ')
 attrs=invoke(('llvm-readelf','-A','image.elf'),target).decode()
 require('rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0' in attrs,'counter ELF admits an unsupported extension')
 require(not invoke(('llvm-nm','--undefined-only','image.elf'),target).strip(),'unknown counter runtime dependency')
 require(not relocation_types(invoke(('llvm-readelf','-r','image.elf'),target).decode()),'counter runtime relocation')
 segments=parse_load_segments(invoke(('llvm-readelf','-l','--wide','image.elf'),target).decode())
 require(segments and all(0<r['memory_size'] and r['physical_address']==r['virtual_address'] and
  0x80000000<=r['virtual_address'] and r['virtual_address']+r['memory_size']<=0x80010000 and
  not ('W' in r['flags'] and 'E' in r['flags']) for r in segments),'counter ELF escapes immutable firmware envelope')
 invoke(('llvm-objcopy','-O','binary','--only-section=.text','image.elf','code.bin'),target)
 code=(target/'code.bin').read_bytes();primitive=validate_csr_bytes(code,0x80000000,ranges)
 disassembly=invoke(('llvm-objdump','-d','--no-show-raw-insn','image.elf'),target).decode()
 # New CSR names never enter any historical machine allowlist. Exact independent
 # CSR byte checks cover those nine bodies; the existing full-range scanner
 # covers every remaining function including startup and compiled guest policy.
 validate_machine(disassembly,ranges={s:r for s,r in ranges.items() if s not in primitive})
 after=source_inputs(root);after['scripts/check_guest_counters.py']=sha256(root/'scripts/check_guest_counters.py')
 require(after==before,'counter consumed compiler/source changed during build')
 files={p.name:sha256(p) for p in target.iterdir() if p.is_file()}
 receipt={'schema':'lemmasim-guest-csr/1','status':'PASS_AUDIT','profile':'core0-firmware-v0.2',
  'boot':'ELF-preload development diagnostic','source_inputs':before,'tools':versions,'upstream':upstream,
  'linked_objects':['startup.o','program.o'],'artifacts':files,'ir':ir,'primitive_bytes':primitive,'stack':stack,
  'functions':ranges,'remaining': ['S/U counter access and privilege faults','ISA exhaustiveness',
    'cross-backend processor timing','arbitrary cached translation/instruction-visibility checkpoint states']}
 write_json(out/'audit.json',receipt)
 return target,ranges,names,receipt

class Native:
 def __init__(self,data,target,path):
  path.mkdir();self.path=path;self.log=(path/'runtime.log').open('xb')
  self.command=[data['binary']['path'],'--session','--image',str(target/'image.elf'),'--rom',data['rom']['path'],
   '--uart-output',str(path/'uart.bin'),'--ram-dump','0x80100100:200:'+str(path/'records.bin'),
   '--report',str(path/'report.json'),'--quiet-uart','--trace-limit','0','--deadline','60']
  self.p=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True)
 def call(self,text):
  require(self.p.poll() is None,'native counter runtime ended early')
  self.p.stdin.write(text+'\n');self.p.stdin.flush()
  # Bound transport as well as native execution; this adds no virtual clock
  # step, forced guest fence, or controller drain.
  ready,_,_=select.select([self.p.stdout],[],[],65)
  require(ready,'native counter transport deadline exceeded')
  line=self.p.stdout.readline();require(line,'native counter response absent')
  row=json.loads(line);require(row.get('ok') is True,'native counter operation failed '+str(row))
  return row['result']
 def close(self):
  if self.p.poll() is None:
   try:self.call('destroy');self.p.wait(timeout=5)
   except BaseException:self.p.kill();self.p.wait(timeout=5)
  self.log.close()

def native_check(data,target,ranges,names,out):
 a=Native(data,target,out/'rtl-original');b=None;c=None
 try:
  lo,size=ranges[names[SOURCE+'stable']]
  boundary=None
  # Source-bound function range rather than debugger mutation selects a real
  # inhibited-counter state. The normal program has no forced fence or drain.
  for _ in range(2000):
   state=a.call('run 10')
   require(not state['finished'],'counter program finished before meaningful snapshot')
   if lo<=state['pc']<lo+size:boundary=state;break
  require(boundary is not None,'bounded inhibited-counter snapshot state not reached')
  prefix=out/'rtl-prefix.chk';a.call('snapshot '+str(prefix))
  require(a.call('inspect')==boundary,'snapshot changed live pipeline/counter state')
  original=a.call('run 5000000');require(original['finished'] and original['finish_code']==0x5555,'actual RTL counter guest rejected hardware')
  left=out/'rtl-final-original.chk';a.call('snapshot '+str(left));a.close()
  records=validate_records((a.path/'records.bin').read_bytes())
  b=Native(data,target,out/'rtl-fork');b.call('restore '+str(prefix))
  fork=b.call('run 5000000');require(fork['finished'] and fork['finish_code']==0x5555,'RTL continuation did not finish')
  right=out/'rtl-final-fork.chk';b.call('snapshot '+str(right));b.close()
  require((b.path/'records.bin').read_bytes()==(a.path/'records.bin').read_bytes(),'guest counter continuation records differ')
  require(sha256(left)==sha256(right),'authoritative same-native-backend continuation archive differs')
  c=Native(data,target,out/'rtl-reset');c.call('restore '+str(prefix));c.call('warm-reset 8')
  reset=c.call('run 5000000');require(reset['finished'] and reset['finish_code']==0x5555,'guest CSR policy failed after active-state eight-edge reset')
  c.close();reset_records=validate_records((c.path/'records.bin').read_bytes())
  return {'status':'PASS','command':a.command,'snapshot_boundary':boundary,'final':original,'records':records,
   'prefix_sha256':sha256(prefix),'final_sha256':sha256(left),'exact_archive_suffix':True,
   'reset_edges':8,'active_counter_reset_final':reset,'reset_guest_records':reset_records,
   'scope':'real guest M-counter accesses and one active inhibited-counter/pipeline suffix; no TLB/cache state completeness claim'}
 finally:
  a.close()
  if b:b.close()
  if c:c.close()

def fast_check(binary,target,dtb,out):
 from lemmasim_fast import QMP,CPU
 directory=out/'fast';directory.mkdir();log=(directory/'machine.log').open('xb')
 temporary=tempfile.TemporaryDirectory(prefix='lemma-guest-csr-',dir='/tmp')
 process=None;qmp=None
 base=Path(temporary.name)
 command=[str(binary),'-machine','lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1','-bios','none',
  '-kernel',str(target/'image.elf'),'-dtb',str(dtb),'-display','none','-monitor','none',
  '-serial','file:'+str(directory/'uart.bin'),'-qmp','unix:'+str(base/'qmp.sock')+',server=on,wait=off',
  '-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031',
  '-global','lemma-paper-pen.raw-output='+str(directory/'input.bin')]
 try:
  process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
  qmp=QMP(base/'qmp.sock',process,60)
  qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':'1000000'})
  qmp.execute('cont');deadline=time.monotonic()+60
  while qmp.execute('query-status')['running']:
   require(time.monotonic()<deadline,'actual fast guest counter execution deadline');time.sleep(.001)
  status=qmp.execute('query-status');records=directory/'records.bin'
  # Raw RAM observation only: no GDB connection, CSR writes, guest repair or
  # counter tolerance. A failure can leave partial guest-produced records.
  qmp.execute('pmemsave',{'val':0x80100100,'size':200,'filename':str(records)})
  values=validate_records(records.read_bytes())
  return {'status':'PASS','binary_sha256':sha256(binary),'command':command,'records':values,
   'machine_status':status,'scope':'same genuine guest architectural counter policy; no processor timing parity or QEMU migration completeness'}
 finally:
  if process and process.poll() is None:
   try:
    if qmp:qmp.execute('quit')
    process.wait(timeout=5)
   except BaseException:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  if qmp:qmp.close()
  log.close();temporary.cleanup()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--native-bundle',type=Path,required=True);p.add_argument('--timeout',type=int,default=300)
 p.add_argument('--fast',action='store_true',help='Use the same validated bundle fast binary; architecture only, no timing claim')
 args=p.parse_args();root=repo_root();out=args.work_dir.resolve();out.mkdir(exist_ok=False)
 result={'status':'RUNNING','qualification':'actual guest-issued CSR instructions; debugger CSR writes absent'}
 start=time.monotonic()
 try:
  require(1<=args.timeout<=600,'build timeout outside1..600s')
  from silicon_guest_bundle import prepared
  data=prepared(args.native_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0')
  target,ranges,names,audit=build(root,out,args.timeout)
  result['native_bundle']=data['native_bundle'];result['guest_sha256']=sha256(target/'image.elf')
  result['rtl']={'status':'RUNNING','scope':'actual M-mode counter guest and native active-state suffix'}
  try:result['rtl']=native_check(data,target,ranges,names,out)
  except BaseException as error:
   result['rtl'].update(status='FAIL',error=repr(error));raise
  result['status']='PASS_RTL'
  if args.fast:
   fast_data=prepared(args.native_bundle,'qemu','notebook','lemma-silicon-dev/0.3.0')
   result['fast_bundle']=fast_data['native_bundle']
   result['fast']={'status':'RUNNING','scope':'actual architectural counter guest; no timing parity'}
   try:result['fast']=fast_check(Path(fast_data['qemu']['path']),target,Path(fast_data['workloads']['notebook']['dtb']['path']),out)
   except BaseException as error:
    result['fast'].update(status='FAIL',error=repr(error));raise
   result['status']='PASS_ARCHITECTURAL_BOTH'
  else:result['fast']={'status':'NOT_RUN','scope':'fast architectural counter policy'}
 except BaseException as error:
  result.update(status='FAIL',error=repr(error));raise
 finally:
  result['wall_seconds']=time.monotonic()-start;write_json(out/'result.json',result)
 if result['status'] not in ('PASS_RTL','PASS_ARCHITECTURAL_BOTH'):raise SystemExit(1)
 print('GUEST_COUNTERS:'+result['status']+' actual Lean CSR instructions and exact native active-counter suffix')

if __name__=='__main__':main()
