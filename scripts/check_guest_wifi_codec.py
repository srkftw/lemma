#!/usr/bin/env python3
"""Genuinely elaborated RV64 pure Wi-Fi coding policy on a qualified RTL core.
Development ELF preload is explicit; this does not register a Wi-Fi device or
claim that a guest exchanged samples through a connected profile0.12 driver.
"""
from __future__ import annotations
import argparse,json,os,re,select,struct,subprocess,time
from pathlib import Path
from core0_common import Core0Error,repo_root,require_tools,sha256,write_json,load_json
from build_kernel import command_invoker,realize_toolchain,source_inputs
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from audit_kernel import validate_ir,validate_machine,function_ranges,defined_function_symbols,parse_load_segments,relocation_types,validate_compiled_stack,weighted_stack_graph
from audit_core0 import parse_stack_sizes

ROOT_SOURCE='Lemma.Platform.RiscV.Development.WiFiCodecPolicy.main'
PREFIXES=('Lemma.Platform.RiscV.Development.WiFiCodecPolicy.','Lemma.Radio.WiFi.Codec.')
def require(v,m):
 if not v:raise Core0Error(m)
def validate_unit(u):
 require(set(u)=={'schema_version','artifact_category','configuration','contract_version','role','roots','functions','used_execution_ops','used_device_ops','used_loops'} and u['schema_version']==1 and u['artifact_category']=='development-wifi-codec-execution-unit' and u['configuration']=='wifi-codec-development' and u['contract_version']=='core0-firmware-v0.2' and u['role']=='firmware','Wi-Fi pure codec unit identity differs')
 rows=u['functions'];require(isinstance(rows,list) and rows,'empty codec closure')
 names={r['source']:r['symbol'] for r in rows}
 require(len(names)==len(rows) and len(set(names.values()))==len(rows) and all(s.startswith(PREFIXES) and re.fullmatch('lemma_wifi_codec_[A-Za-z0-9_]+',v) for s,v in names.items()),'codec source provenance differs')
 for row in rows:
  require(set(row)=={'source','symbol','args','effects'} and all(t in ('bool','u8','u32','u64') for t in row['args']) and set(row['effects'])<= {'checked-access','physical-write'},'codec signature/effects differ')
 require(u['roots']==[{'source':ROOT_SOURCE,'symbol':names.get(ROOT_SOURCE),'args':[]}] and not u['used_loops'] and not u['used_device_ops'],'codec gained unadmitted root/loop/device')
 ops=u['used_execution_ops'];require(len(ops)==2,'codec memory operation inventory differs')
 require({r['source_identity'] for r in ops}=={'Lemma.Core0.Execution.Op.physicalWrite8','Lemma.Core0.Execution.Op.physicalWrite64'},'codec hardware authority differs')
 for r in ops:
  require(r['primitive_symbol'] is None and r['physical'] is True and r['write'] is True and r['width_bytes']==(1 if r['source_identity'].endswith('8') else 8),'codec physical write lowering differs')
 return names

def build(root,out,timeout):
 tools=require_tools(('git','nix','lake','lean','opt','llc','clang','ld.lld','llvm-objcopy','llvm-readelf','llvm-nm','llvm-objdump','qemu-system-riscv64','dtc','flock'))
 commands=[];raw=command_invoker(root,out,tools,timeout,commands)
 def invoke(argv,cwd=out,env=None):
  selected=(argv[0],'--elf-output-style=GNU',*argv[1:]) if argv[0]=='llvm-readelf' else argv
  return raw(selected,cwd,env)
 before=source_inputs(root);before['scripts/check_guest_wifi_codec.py']=sha256(root/'scripts/check_guest_wifi_codec.py')
 versions,upstream=realize_toolchain(root,tools,invoke)
 invoke(('flock','build/task006-lake.lock','lake','build','Lemma.Compiler.WiFiCodecExport'),root)
 consumer=out/'Export.lean';consumer.write_text('import Lemma.Compiler.WiFiCodecExport\n\n#lemma_export_wifi_codec_probe\n')
 target=out/'target';invoke(('flock','build/task006-lake.lock','lake','env','lean',str(consumer.relative_to(root))),root,{**os.environ,'LEMMA_WIFI_GUEST_OUTPUT':str(target)})
 unit=load_json(target/'unit.json');names=validate_unit(unit)
 invoke(('opt','-S','-passes=default<O2>','program.ll','-o','program.opt.ll'),target)
 invoke(('llc',*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'),target)
 invoke(('clang',*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'),target)
 invoke(('ld.lld','-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map','startup.o','program.o','-o','image.elf'),target)
 pre=(target/'program.ll').read_text();post=(target/'program.opt.ll').read_text()
 frames=parse_stack_sizes(invoke(('llvm-readelf','--stack-sizes','program.o'),target).decode())
 validate_compiled_stack(invoke(('llvm-objdump','-d','--no-show-raw-insn','program.o'),target).decode(),frames)
 stack=weighted_stack_graph(post,frames,{})
 require(max(r['bytes'] for r in stack['weighted_frame_chains'].values())<=8192,'codec stack overlaps guest records')
 ir={'before':validate_ir(pre,unit,optimized=False),'after':validate_ir(post,unit,optimized=True,optimization='O2')}
 symbols=invoke(('llvm-readelf','-s','--wide','image.elf'),target).decode();ranges=function_ranges(symbols)
 require(defined_function_symbols(symbols)==set(names.values())|{'_start'},'codec ELF executable provenance differs')
 header=invoke(('llvm-readelf','-h','image.elf'),target).decode()
 require(all(t in header for t in ('ELF64','little endian','RISC-V')) and re.search(r'Flags:\s+0x0(?:\s|$)',header) and '0x80000000' in header,'codec ELF attributes differ')
 require('rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0' in invoke(('llvm-readelf','-A','image.elf'),target).decode(),'codec ELF admits another ISA')
 require(not invoke(('llvm-nm','--undefined-only','image.elf'),target).strip() and not relocation_types(invoke(('llvm-readelf','-r','image.elf'),target).decode()),'codec unknown runtime/relocation')
 segments=parse_load_segments(invoke(('llvm-readelf','-l','--wide','image.elf'),target).decode())
 require(segments and all(0<r['memory_size'] and r['physical_address']==r['virtual_address'] and 0x80000000<=r['virtual_address'] and r['virtual_address']+r['memory_size']<=0x80010000 and not ('W' in r['flags'] and 'E' in r['flags']) for r in segments),'codec executable escapes envelope')
 validate_machine(invoke(('llvm-objdump','-d','--no-show-raw-insn','image.elf'),target).decode(),ranges=ranges)
 after=source_inputs(root);after['scripts/check_guest_wifi_codec.py']=sha256(root/'scripts/check_guest_wifi_codec.py');require(before==after,'codec consumed sources changed during compilation')
 receipt={'status':'PASS_AUDIT','source_inputs':before,'tools':versions,'upstream':upstream,'ir':ir,'stack':stack,'functions':ranges,'linked_objects':['startup.o','program.o'],'artifacts':{p.name:sha256(p) for p in target.iterdir() if p.is_file()}}
 write_json(out/'audit.json',receipt);return target,receipt

def crc_diagram(payload):
 s=[1]*32
 for octet in payload:
  for b in range(8):
   f=s[31]^((octet>>b)&1);s=[0]+s[:-1]
   for exponent in (0,1,2,4,5,7,8,10,11,12,16,22,23,26):s[exponent]^=f
 return sum((s[31-j]^1)<<j for j in range(32))
def carries(payload,seed):
 fcs=crc_diagram(payload);raw=[0]*16
 for octet in payload+fcs.to_bytes(4,'little'):raw.extend((octet>>k)&1 for k in range(8))
 tail=len(raw);raw.extend([0]*(((tail+6+23)//24)*24-tail));scr=[(seed>>j)&1 for j in range(7)];delay=[0]*6;out=[];coded=0
 for index,bit in enumerate(raw):
  feedback=scr[6]^scr[3];scr=[feedback]+scr[:-1];b=0 if tail<=index<tail+6 else bit^feedback
  a=b^delay[1]^delay[2]^delay[4]^delay[5];c=b^delay[0]^delay[1]^delay[2]^delay[5];delay=[b]+delay[:-1]
  if index%24==0:coded=0
  coded|=a<<((index%24)*2);coded|=c<<((index%24)*2+1)
  if index%24==23:out.append((coded<<13)|(sum(scr[j]<<j for j in range(7))<<6)|sum(delay[j]<<(5-j) for j in range(6)))
 return out

def validate_records(raw):
 require(len(raw)==1024,'guest RAM observation capacity differs')
 values=list(struct.unpack('<16Q',raw[:128]));payload=raw[0x300:0x320]
 require(values[:8]==[0x57494649504f4c01,0xcbf43926,0x1900009836,0x0e45889f13b0,0x401d2970b596,0x57494649444f4e01,0,32],'genuine guest numerical records/completion differ')
 require(payload==bytes(j*17 for j in range(16))+bytes(255^(j*17) for j in range(16)),'guest did not generate both selected payloads')
 require(values[8:]==carries(payload[:16],93),'actual guest DATA coding states differ from independent diagram oracle')
 return values,payload

def execute(data,target,out):
 directory=out/'native';directory.mkdir();log=(directory/'runtime.log').open('xb');p=None
 argv=[data['binary']['path'],'--session','--image',str(target/'image.elf'),'--rom',data['rom']['path'],'--uart-output',str(directory/'uart.bin'),'--ram-dump','0x80100100:1024:'+str(directory/'records.bin'),'--report',str(directory/'report.json'),'--quiet-uart','--trace-limit','0','--deadline','120']
 try:
  p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,start_new_session=True)
  def call(text):
   require(p.poll() is None,'native codec machine ended');p.stdin.write(text+'\n');p.stdin.flush();ready,_,_=select.select([p.stdout],[],[],125);require(ready,'native codec transport bound');row=json.loads(p.stdout.readline());require(row.get('ok') is True,'native codec command failed');return row['result']
  state=call('run 5000000');require(state['finished'] and state['finish_code']==0x5555,'actual RV64 codec guest failed or exhausted5M bound')
  call('destroy');p.wait(timeout=5);values,payload=validate_records((directory/'records.bin').read_bytes());(out/'guest-payloads.bin').write_bytes(payload)
  return {'status':'PASS_RTL_GUEST','command':argv,'final':state,'records':values,'record_sha256':sha256(directory/'records.bin'),'payloads':{'path':str(out/'guest-payloads.bin'),'bytes':32,'sha256':sha256(out/'guest-payloads.bin')}}
 finally:
  if p and p.poll() is None:
   os.killpg(p.pid,9);p.wait(timeout=5)
  log.close()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--native-bundle',type=Path,required=True);p.add_argument('--timeout',type=int,default=300)
 a=p.parse_args();root=repo_root();out=a.work_dir.resolve();require(out.is_relative_to(root/'build') and not out.exists(),'unused output under build required');require(30<=a.timeout<=600,'build timeout outside30..600s');out.mkdir(parents=True)
 start=time.monotonic();result={'schema':'lemma-wifi-codec-guest/1','status':'FAIL','plan':{'build_seconds':a.timeout,'native_seconds':120,'native_clocks':5000000},'scope':'pure common coding policy; connected Wi-Fi/HE remains unimplemented'}
 try:
  from silicon_guest_bundle import prepared
  data=prepared(a.native_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');result['native_bundle']=data['native_bundle'];target,audit=build(root,out,a.timeout);result['audit_sha256']=sha256(out/'audit.json');result['elf_sha256']=sha256(target/'image.elf');result['guest']=execute(data,target,out);result['status']='PASS_RTL_GUEST'
 except BaseException as e:result['error']=repr(e);raise
 finally:result['wall_seconds']=time.monotonic()-start;write_json(out/'result.json',result)
 print('WIFI_CODEC_GUEST:PASS_RTL_GUEST actual RV64 policy and independently observed DATA coding records')
if __name__=='__main__':main()
