#!/usr/bin/env python3
"""Build/audit/execute ordinary Lean SHA256/HMAC256; host-only independent oracle.
This does not qualify image authentication, anti-rollback or cryptographic
module certification. No host digest or host runtime enters the RV64 image.
"""
import argparse,fcntl,hashlib,hmac,json,os,re,resource,struct,subprocess,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from audit_core0 import parse_stack_sizes,validate_loop_stack_call_graph
from audit_kernel import validate_machine
ROOT=Path(__file__).resolve().parents[1]
REQUIRED={'Lemma.Crypto.SHA256.'+s for s in ('hash','update','finish','compress','roundStep','constant')}
REQUIRED|={'Lemma.Crypto.HMAC256.'+s for s in ('authenticate','begin','finish')}
REQUIRED.add('Lemma.Crypto.Probe.entry')
OPS={'execution.physical-read8','execution.physical-read64','execution.physical-write8','execution.physical-write64'}
DEVICE={'uart.enable-reset-fifo','uart.write-byte','uart.read-status'}
LITERALS={0x315348414d4c,0x3143414d484d4c,0x31414853414d454c,0x31444e45414d454c,0x6572656854206948}
def audit_ir(unit,pre,post):
 if unit.get('schema')!='lemma-crypto-rv64-component/1' or unit.get('contract_version')!='core0-boot-v0.1' or unit.get('root')!='Lemma.Crypto.Probe.entry':raise Core0Error('unknown crypto component tuple')
 if set(unit.get('used_execution_ops',[]))!=OPS or set(unit.get('used_device_ops',[]))!=DEVICE:raise Core0Error('crypto effect boundary differs')
 sources={};symbols={}
 for row in unit.get('functions',[]):
  name=re.sub(r'^_private\.[^.]+(?:\.[^.]+)*?\.[0-9]+\.(Lemma\..*)$',r'\1',row['source'])
  if not (name.startswith(('Lemma.Crypto.','Lemma.Kernel.Memory.Access.','Lemma.Boot.RecoveryExecuted.transmit')) or name in ('Lemma.Core0.Memory.Status.iterationStop','Lemma.Core0.Memory.Status.txTimeout')):raise Core0Error('foreign crypto source '+name)
  symbol=row['symbol']
  if name in sources or symbol in symbols or not re.fullmatch(r'lemma_crypto_core0_(scalar|action)_[0-9]+',symbol):raise Core0Error('ambiguous crypto provenance')
  if any(a not in ('u8','u32','u64','bool') for a in row['args']):raise Core0Error('foreign crypto ABI')
  if row['effects']!='{}':
   effect=row['effects']
   if not isinstance(effect,str) or not effect.startswith('[') or not effect.endswith(']') or not set(effect[1:-1].split(','))<= {'checked-access','physical-read','physical-write','mmio-read','mmio-write','io-order'}:raise Core0Error('unknown crypto authority')
  sources[name]=row;symbols[symbol]=name
 if not REQUIRED<=sources.keys() or unit['entry_symbol']!=sources[unit['root']]['symbol']:raise Core0Error('missing actual SHA/HMAC closure')
 for phase,ir in [('pre',pre),('post',post)]:
  definitions=re.findall(r'(?m)^define[^\n]*@([A-Za-z_0-9.$]+)\(',ir)
  if not definitions or len(definitions)!=len(set(definitions)) or not set(definitions)<=symbols.keys() or phase=='pre' and set(definitions)!=symbols.keys():raise Core0Error('crypto definition closure differs')
  if re.search(r'(?m)^@|\basm\b|\b(?:invoke|landingpad|resume|callbr|indirectbr|alloca)\b',ir) or re.search(r'\bcall[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):raise Core0Error('foreign crypto code/data/dispatch')
  declared={}
  for result,name,args in re.findall(r'(?m)^declare\s+(void|i[0-9]+)\s+@([^ (]+)\(([^)]*)\)',ir):
   if name in declared:raise Core0Error('duplicate crypto runtime')
   declared[name]=result+'('+re.sub(r'\s+','',args)+')'
  if declared.pop('core0_io_fence',None)!='void()' or any(n!='llvm.umin.i64' or s!='i64(i64,i64)' for n,s in declared.items()) or phase=='pre' and declared:raise Core0Error('unaccounted crypto runtime')
  calls=set(re.findall(r'\bcall[^\n]*@([A-Za-z_0-9.$]+)\(',ir))
  if not calls<=set(definitions)|set(declared)|{'core0_io_fence'}:raise Core0Error('unresolved crypto IR call')
 return {'genuine_functions':len(sources),'optimized_functions':len(definitions),'helpers':['core0_io_fence'],'intrinsics':declared}
def audit_elf(data,*,base=0x80000000,literals=LITERALS):
 if len(data)<64 or data[:7]!=b'\x7fELF\x02\x01\x01':raise Core0Error('not ELF64 LE')
 e=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
 if (e[1],e[2],e[3],e[4],e[7],e[8],e[9])!=(2,243,1,base,0,64,56):raise Core0Error('crypto ELF architecture/entry/flags differ')
 headers=[struct.unpack_from('<IIQQQQQQ',data,e[5]+i*56) for i in range(e[10])]
 loads=[row for row in headers if row[0]==1];attributes=[row for row in headers if row[0]==0x70000003]
 if len(loads)!=1 or len(attributes)!=1 or len(headers)!=2:raise Core0Error('crypto ELF requires sole RX load and exact nonload RISC-V metadata')
 kind,flags,offset,virtual,physical,files,memory,alignment=loads[0]
 if kind!=1 or flags!=5 or virtual!=base or physical!=virtual or files!=memory or not 0<files<=65536 or alignment!=4096 or offset>len(data)-files:raise Core0Error('crypto load envelope differs')
 sections=[struct.unpack_from('<IIQQQQIIQQ',data,e[6]+i*64) for i in range(e[12])]
 names=sections[e[13]];strings=data[names[4]:names[4]+names[5]];allocated={};attribute_section=None
 for s in sections:
  end=strings.find(b'\0',s[0]);name=strings[s[0]:end].decode('ascii')
  if name=='.riscv.attributes':
   if attribute_section is not None or s[1]!=0x70000003 or s[2]!=0:raise Core0Error('crypto architecture metadata section differs')
   attribute_section=s
  if not s[2]&2:continue
  if end<0 or name in allocated or name not in ('.text','.rodata'):raise Core0Error('unaccounted crypto allocated section')
  allocated[name]=s
 if '.text' not in allocated or allocated['.text'][2]!=6:raise Core0Error('crypto text authority differs')
 if attribute_section is None:raise Core0Error('missing architecture metadata')
 s=attribute_section
 if attributes[0]!=(0x70000003,4,s[4],0,0,s[5],s[5],1) or s[4]>len(data)-s[5]:raise Core0Error('crypto nonload metadata program/section relation differs')
 values=[]
 if '.rodata' in allocated:
  s=allocated['.rodata']
  if s[2]!=18 or s[8]!=8 or s[9]!=8 or s[5]%8:raise Core0Error('crypto readonly merge layout differs')
  values=list(struct.unpack_from('<'+'Q'*(s[5]//8),data,s[4]))
  if len(values)!=len(set(values)) or not set(values)<=literals:raise Core0Error('unaccounted crypto readonly bytes')
 return {'entry':e[4],'RX_load_bytes':files,'readonly_literals':values,'target_runtime':'only generated I/O fence; no hosted runtime'}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
 out.mkdir(parents=True);began=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
 report={'status':'FAIL','scope':__doc__,'bounds':{'seconds':600,'command_seconds':180,'qemu_seconds':60,'per_process_address_space':16<<30,'file_bytes':1<<30},'commands':[]};process=None
 try:
  from build_kernel import source_inputs
  before=source_inputs(ROOT);before['scripts/check_crypto.py']=sha256(Path(__file__));before['tests/crypto/SHA256.lean']=sha256(ROOT/'tests/crypto/SHA256.lean');report['source_inputs']=before
  report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
  report['dirty_paths']=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True).splitlines()
  tools=require_tools(('lake','lean','opt','llc','clang','ld.lld','llvm-nm','llvm-readelf','llvm-objdump','qemu-system-riscv64'));report['tools']={}
  for n,t in tools.items():
   if not str(t).startswith('/nix/store/'):raise Core0Error('pinned Nix tools required')
   report['tools'][n]={'path':str(t),'sha256':sha256(Path(t))}
  def run(label,argv,env=None):
   left=600-(time.monotonic()-began)
   if left<=0:raise Core0Error('crypto aggregate deadline')
   r=run_bounded(argv,cwd=out,timeout_seconds=min(180,left),env=env);(out/(label+'.log')).write_bytes(r.stdout+r.stderr);report['commands'].append({'argv':list(r.argv),'returncode':r.returncode,'seconds':r.elapsed_seconds})
   if r.returncode:raise Core0Error('crypto actual command failed: '+label)
   return r.stdout.decode()
  vectors=out/'sha-vectors.txt';vectors.write_text(''.join(str(n)+' '+hashlib.sha256(bytes((i*37+11)%256 for i in range(n))).hexdigest()+'\n' for n in [1,55,56,57,63,64,65,127,128,129,4095,4096]))
  env={**os.environ,'LEAN_NUM_THREADS':'2','LEMMA_SHA_VECTORS':str(vectors),'LEMMA_CRYPTO_OUT':str(out/'component')}
  export=out/'Export.lean';export.write_text('import Lemma.Compiler.CryptoExport\n#lemma_export_crypto\n')
  with (ROOT/'build/task006-lake.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   # Lake must use the real package workspace, not this ignored output dir.
   for label,tail in [('elaborate',['build','Lemma.Crypto.Probe','Lemma.Compiler.CryptoExport']),('actions',['env','lean',str(ROOT/'tests/crypto/SHA256.lean')]),('export',['env','lean',str(export)])]:
    argv=[tools['lake'],'-d',str(ROOT),*tail];text=run(label,argv,env)
    if label=='actions' and text.count('SHA256_ACTIONS:PASS')!=1 or label=='export' and text.count('CRYPTO_EXPORT:PASS')!=1:raise Core0Error('missing actual checked crypto result')
  d=out/'component';run('verify',[tools['opt'],'-passes=verify','-disable-output',str(d/'program.ll')]);run('opt',[tools['opt'],'-S','-passes=default<O2>',str(d/'program.ll'),'-o',str(d/'program.opt.ll')])
  unit=json.loads((d/'unit.json').read_text());post=(d/'program.opt.ll').read_text();report['closure']=audit_ir(unit,(d/'program.ll').read_text(),post)
  run('llvm',[tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section',str(d/'program.opt.ll'),'-o',str(d/'program.o')]);run('startup',[tools['clang'],*STARTUP_ARGUMENTS,str(d/'startup.S'),'-o',str(d/'startup.o')])
  if run('object-undefined',[tools['llvm-nm'],'--undefined-only',str(d/'program.o')]).split()!=['U','core0_io_fence']:raise Core0Error('unaccounted crypto object runtime')
  run('link',[tools['ld.lld'],'-m','elf64lriscv','--no-relax','-T',str(d/'link.ld'),'-o',str(d/'image.elf'),str(d/'startup.o'),str(d/'program.o')])
  if run('undefined',[tools['llvm-nm'],'--undefined-only',str(d/'image.elf')]).strip():raise Core0Error('unresolved crypto runtime')
  if 'There are no relocations in this file.' not in run('relocations',[tools['llvm-readelf'],'--elf-output-style=GNU','-r',str(d/'image.elf')]):raise Core0Error('crypto retains runtime relocations')
  machine=run('machine',[tools['llvm-objdump'],'-d','--no-show-raw-insn',str(d/'image.elf')]);validate_machine(machine)
  report['stack']=validate_loop_stack_call_graph(post,parse_stack_sizes(run('stack',[tools['llvm-readelf'],'--elf-output-style=GNU','--stack-sizes',str(d/'program.o')])))
  report['elf']=audit_elf((d/'image.elf').read_bytes());run('attributes',[tools['llvm-readelf'],'--elf-output-style=GNU','-h','-l','-A','-S',str(d/'image.elf')])
  # Match the established standalone Core0 runner. The machine-code audit
  # admits RV64IM/CSR/fence only; this component does not qualify the model's
  # additional reported extensions or canonical RTL timing.
  report['processor_scope']='Pinned standalone Core0 rv64 model; executable ISA separately audited; extension-reporting/timing conformance not qualified'
  uart=out/'uart.bin';argv=[tools['qemu-system-riscv64'],'-machine','virt','-cpu','rv64','-m','128M','-bios','none','-kernel',str(d/'image.elf'),'-display','none','-monitor','none','-serial','file:'+str(uart)]
  report['qemu_argv']=argv;started=time.monotonic()
  with (out/'qemu-stderr.log').open('xb') as log:
   process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   terminal=struct.pack('<Q',0x31444e45414d454c)
   while True:
    wire=uart.read_bytes() if uart.exists() else b''
    if len(wire)>=12*64+8:break
    if process.poll() is not None or time.monotonic()-started>=60 or time.monotonic()-began>=600:raise Core0Error('crypto guest exited/deadline before complete actual protocol')
    time.sleep(.02)
   if len(wire)!=12*64+8 or wire[-8:]!=terminal:raise Core0Error('crypto guest protocol length/terminal differs')
   rows=[]
   for i,n in enumerate([0,1,55,56,57,63,64,65,129,4096,3,8]):
    magic,case,status,length=struct.unpack_from('<4Q',wire,i*64);digest=wire[i*64+32:i*64+64]
    caseId=i if i<10 else 100+i-10
    message=bytes((j*37+11)%256 for j in range(n)) if i<10 else b'abc' if i==10 else b'Hi There'
    expected=hashlib.sha256(message).digest() if i<11 else hmac.new(b'\x0b'*20,message,hashlib.sha256).digest()
    if (magic,case,status,length)!=(0x31414853414d454c,caseId,0,n) or digest!=expected:raise Core0Error('actual RV64 digest differs at case '+str(caseId))
    rows.append({'case':caseId,'bytes':n,'actual_digest':digest.hex()})
   report['actual_rv64']={'status':'PASS','cases':rows,'seconds':time.monotonic()-started,'uart_sha256':sha256(uart),'protocol_stop':'all twelve actual digest records plus terminal, then host stops parked WFI workload; no timeout success'}
  report['artifacts']={str(f.relative_to(out)):sha256(f) for f in d.iterdir() if f.is_file()}
  if any(sha256(ROOT/n)!=h for n,h in before.items()):raise Core0Error('crypto consumed source changed')
  report['consumed_host_current_equal']=True
  report['status']='PASS_GENUINE_RV64_SHA256_HMAC_COMPONENT'
 except BaseException as e:report['error']=repr(e)
 finally:
  if process is not None:
   if process.poll() is None:process.terminate()
   try:process.wait(timeout=2)
   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
   report['qemu_reaped']=process.returncode is not None
  report['seconds']=time.monotonic()-began
  if report['seconds']>600:report['status']='FAIL';report['deadline_error']=True
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'seconds':report['seconds'],'error':report.get('error')},indent=2));return 0 if report['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
