#!/usr/bin/env python3
"""Fresh genuine Lean S/U counter/trap corpus and bounded raw backend observations.
Host code supplies clocks, assembles/audits declared objects and reads guest RAM.
It never writes a debugger CSR, installs guest verdicts, or repairs a trap.
"""
from __future__ import annotations
import argparse,json,os,re,select,signal,struct,subprocess,tempfile,time
from pathlib import Path
from core0_common import Core0Error,load_json,repo_root,require_tools,sha256,write_json
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from build_kernel import command_invoker,realize_toolchain,source_inputs
from audit_kernel import (validate_ir,validate_machine,function_ranges,defined_function_symbols,
                         parse_load_segments,relocation_types,validate_compiled_stack,weighted_stack_graph)
from audit_core0 import parse_stack_sizes
from check_guest_counters import CSR_OPERATIONS as M_OPERATIONS

SOURCE='Lemma.Platform.RiscV.Development.CounterSuPolicy.'
PROFILE='core0-counter-su-v0.1'
BASE=0x80100000
SIZE=32768
COUNT=404
CY=0x1122334455667788
IR=0x2233445566778899
CSR_OPERATIONS={**M_OPERATIONS,
 'readCounterCycle':('read-counter-cycle','lemma_exec_read_counter_cycle',0xc00,False),
 'readCounterTime':('read-counter-time','lemma_exec_read_counter_time',0xc01,False),
 'readCounterRetired':('read-counter-retired','lemma_exec_read_counter_retired',0xc02,False),
 'readSupervisorCounterEnable':('read-supervisor-counter-enable','lemma_exec_read_supervisor_counter_enable',0x106,False),
 'writeSupervisorCounterEnable':('write-supervisor-counter-enable','lemma_exec_write_supervisor_counter_enable',0x106,True),
 'attemptWriteCounterCycle':('attempt-write-counter-cycle','lemma_exec_attempt_write_counter_cycle',0xc00,True),
 'attemptWriteCounterTime':('attempt-write-counter-time','lemma_exec_attempt_write_counter_time',0xc01,True),
 'attemptWriteCounterRetired':('attempt-write-counter-retired','lemma_exec_attempt_write_counter_retired',0xc02,True),
}
TRANSITIONS={'counterEnterSupervisor':'lemma_exec_counter_enter_supervisor',
             'counterEnterUser':'lemma_exec_counter_enter_user'}
EXTRA_FUNCTIONS={'_start','lemma_exec_read_time','lemma_counter_su_resume','lemma_counter_su_lower',
 'lemma_machine_vector','lemma_machine_fatal','lemma_machine_double_fault','lemma_counter_su_failure',*TRANSITIONS.values()}
OPS_BY_CASE=['readCounterCycle','readCounterTime','readCounterRetired','attemptWriteCounterCycle',
 'attemptWriteCounterTime','attemptWriteCounterRetired','readMachineCycle','writeMachineCycle',
 'readSupervisorCounterEnable','writeSupervisorCounterEnable']

def require(value,message):
 if not value:raise Core0Error(message)

def literal_cases():
 # Independent enumeration, rather than the guest's arithmetic case selectors.
 cases=[]
 for m in range(8):
  for s in range(8):
   for mode in (0,1):
    for op in range(3):cases.append((mode,op,m,s))
 for mode in (0,1):
  for op in range(3,6):cases.append((mode,op,7,7))
 for mode in (0,1):
  for op in (6,7):cases.append((mode,op,7,7))
 for mode in (0,1):
  for op in (8,9):cases.append((mode,op,7,7))
 for op in range(6):cases.append((3,op,0,0))
 require(len(cases)==COUNT,'empty/incomplete literal corpus')
 return cases

def permission(mode,op,m,s):
 if op<3:return mode==3 or bool(m&(1<<op)) and (mode==1 or bool(s&(1<<op)))
 if op in (8,9):return mode in (1,3)
 return False

def validate_records(data,ranges):
 require(len(data)==SIZE,'counter-su record capacity differs')
 words=list(struct.unpack('<4096Q',data));h=words[:32];rows=[];illegal=ecalls=0
 require(h[0]==0x4353554449414701 and h[1]==0x435355444f4e4501,'compiled diagnostic completion missing')
 ecall=ranges['lemma_counter_su_lower'][0]+8
 for i,(mode,op,m,s) in enumerate(literal_cases()):
  row=words[32+10*i:42+10*i];rows.append(row)
  require(row[:5]==[i,mode,op,m,s],f'actual corpus identity differs at {i}')
  allowed=permission(mode,op,m,s)
  cause=(0 if mode==3 else mode+8) if allowed else 2
  if not allowed:
   illegal+=1
   _,symbol,csr,write=CSR_OPERATIONS[OPS_BY_CASE[op]]
   tval=(csr<<20)|((10 if write else 0)<<15)|((1 if write else 2)<<12)|((0 if write else 10)<<7)|0x73
   pc=ranges[symbol][0]+(0 if write else 4)
  else:tval=0;pc=0 if mode==3 else ecall
  require(row[6:]==[cause,tval,pc,mode],f'actual cause/tval/PC/origin differs at {i}: {row[6:]} expected {[cause,tval,pc,mode]}')
  if mode in (0,1):ecalls+=1
  value=row[5]
  if allowed and op==1:require(0<h[10]<=value<=h[11],f'actual TIME escaped live MTIME bracket at {i}')
  else:
   expected=(CY if op==0 else IR if op==2 else 7 if op==8 else 0) if allowed else 0
   require(value==expected,f'actual counter result differs at {i}: {value} != {expected}')
 require((illegal,ecalls)==(255,398),'independent corpus trap totals differ')
 expected={0:0x4353554449414701,1:0x435355444f4e4501,2:BASE+256+(COUNT-1)*80,
  3:COUNT,4:ecalls,5:illegal,6:9,7:ecall,8:0,9:1,12:5,13:5,14:CY,15:IR,
  16:7,17:7,18:0,19:illegal+ecalls}
 for i,v in expected.items():require(h[i]==v,f'actual header {i} differs: {h[i]} != {v}')
 require(0<h[10]<h[11],'MTIME failed to advance while CY/IR inhibited')
 require(all(v==0 for v in h[20:]) and all(v==0 for v in words[32+10*COUNT:]),'guest-cleared reserved bytes differ')
 return {'header':h,'rows':rows,'illegal_traps':illegal,'ecalls':ecalls,'total_traps':illegal+ecalls,
  'record_sha256':__import__('hashlib').sha256(data).hexdigest(),'checked_bytes':SIZE}

def validate_unit(unit):
 require(isinstance(unit,dict) and unit.get('schema_version')==1 and
  unit.get('artifact_category')=='development-counter-su-execution-unit' and
  unit.get('configuration')=='counter-su-csr-development' and unit.get('role')=='firmware' and
  unit.get('contract_version')==PROFILE,'counter-su unit version/category differs')
 require(set(unit)=={'schema_version','artifact_category','configuration','contract_version','role','roots','functions','used_execution_ops','used_device_ops','used_loops'},'counter-su unit keys differ')
 rows=unit.get('functions');require(isinstance(rows,list) and rows,'counter-su functions missing')
 for row in rows:
  require(isinstance(row,dict) and set(row)=={'source','symbol','args','effects'} and
   isinstance(row['args'],list) and all(t in ('bool','u8','u32','u64') for t in row['args']) and
   isinstance(row['effects'],list) and len(set(row['effects']))==len(row['effects']) and
   set(row['effects'])<={'checked-access','physical-read','physical-write','machine-state','mmio-read','io-order','timer-state','privilege-transition','sync-trap'},
   'counter-su function signature/effects differ')
 names={r.get('source'):r.get('symbol') for r in rows}
 require(len(names)==len(rows) and len(set(names.values()))==len(rows) and
  all(isinstance(s,str) and s.startswith(SOURCE) and re.fullmatch(r'lemma_counter_su_[A-Za-z0-9_]+',v or '') for s,v in names.items()),'counter-su reachable source closure differs')
 expected_roots=[{'source':SOURCE+n,'symbol':names.get(SOURCE+n),'args':['u64']*a} for n,a in [('main',0),('probe',2),('trap',3)]]
 require(unit.get('roots')==expected_roots,'counter-su entry/probe/trap genuine source roots differ')
 require(unit.get('used_loops')==[] and unit.get('used_device_ops')==[],'unadmitted loop/device in diagnostic')
 ops=unit.get('used_execution_ops');require(isinstance(ops,list) and len(ops)==21,'counter-su operation count differs')
 by={r.get('source_identity','').rsplit('.',1)[-1]:r for r in ops}
 require(len(by)==len(ops) and set(by)==(set(CSR_OPERATIONS)-{'readMisa'})|set(TRANSITIONS)|{'physicalWrite64','physicalRead64','readTime'},'counter-su operation closure differs')
 for name,(ident,symbol,_,write) in CSR_OPERATIONS.items():
  if name=='readMisa':continue
  r=by[name]
  require(set(r)=={'stable_id','source_identity','primitive_symbol','arguments','source_arguments','meaningful_arguments','result','returnkind','width_bytes','write','physical'} and
   r['width_bytes'] is None and r['physical'] is False and r['write']==write and r['result']=='u64' and
   r['stable_id']=='execution.'+ident and r['primitive_symbol']==symbol and
   r['arguments']==(['u64'] if write else []) and r['returnkind']=='word' and
   r['source_arguments']==['u64']*6 and r['meaningful_arguments']==(1 if write else 0),'CSR ABI/identity differs: '+name)
 for name,symbol in TRANSITIONS.items():
  r=by[name];require(r['primitive_symbol']==symbol and r['arguments']==['u64']*2 and r['meaningful_arguments']==2 and r['returnkind']=='word' and r['width_bytes'] is None and not r['write'] and not r['physical'],'fixed privilege transport ABI differs')
 for name,write in [('physicalRead64',False),('physicalWrite64',True)]:
  r=by[name];require(r['primitive_symbol'] is None and r['width_bytes']==8 and r['physical'] is True and r['write']==write,'private RAM authority differs')
 return names

def validate_csr_bytes(code,base,ranges):
 checked={}
 for _,symbol,csr,write in CSR_OPERATIONS.values():
  require(symbol in ranges,'missing actual CSR primitive '+symbol)
  address,size=ranges[symbol]
  access=(csr<<20)|((10 if write else 0)<<15)|((1 if write else 2)<<12)|((0 if write else 10)<<7)|0x73
  words=[access,0x00000513,0x00008067] if write else [0x00000513,access,0x00008067]
  require(size==12 and address>=base and address+size<=base+len(code),'CSR primitive range differs')
  require(code[address-base:address-base+size]==struct.pack('<3I',*words),'actual CSR instruction bytes differ: '+symbol)
  checked[symbol]={'csr':csr,'write':write,'instruction_words':words,'bytes':size,'access_pc':address+(0 if write else 4)}
 # The lower entry is a no-relax AUIPC/JALR call to the genuinely compiled probe,
 # followed by the observed ECALL. The full scanner checks every remaining word.
 begin,size=ranges['lemma_counter_su_lower'];words=struct.unpack('<'+str(size//4)+'I',code[begin-base:begin-base+size])
 require(size==16 and words[2]==0x00000073 and words[0]&0xfff==0x97 and words[1]&0x707f==0x67,'lower compiled call/actual ECALL boundary differs')
 return checked

def build(root,out,timeout):
 tools=require_tools(('git','nix','lake','lean','opt','llc','clang','ld.lld','llvm-objcopy','llvm-readelf','llvm-nm','llvm-objdump','qemu-system-riscv64','dtc','flock'))
 commands=[];raw=command_invoker(root,out,tools,timeout,commands)
 def invoke(argv,cwd=out,env=None):
  if argv[0]=='lake':argv=('flock',str(root/'build/task006-lake.lock'),*argv)
  if argv[0]=='llvm-readelf':argv=(argv[0],'--elf-output-style=GNU',*argv[1:])
  return raw(argv,cwd,env)
 before=source_inputs(root);before['scripts/check_guest_counter_su.py']=sha256(root/'scripts/check_guest_counter_su.py');before['scripts/check_guest_counters.py']=sha256(root/'scripts/check_guest_counters.py')
 versions,upstream=realize_toolchain(root,tools,invoke)
 invoke(('lake','build','Lemma.Compiler.CounterSuExport'),root)
 consumer=out/'Export.lean';consumer.write_text('import Lemma.Compiler.CounterSuExport\n\n#lemma_export_counter_su_probe\n')
 target=out/'target';invoke(('lake','env','lean',str(consumer.relative_to(root))),root,{**os.environ,'LEMMA_COUNTER_SU_OUTPUT':str(target)})
 unit=load_json(target/'unit.json');names=validate_unit(unit)
 invoke(('opt','-S','-passes=default<O2>','program.ll','-o','program.opt.ll'),target)
 invoke(('llc',*LLC_ARGUMENTS,'-stack-size-section','-O2','program.opt.ll','-o','program.o'),target)
 invoke(('clang',*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'),target)
 invoke(('ld.lld','-m','elf64lriscv','--no-relax','-T','link.ld','-Map=image.map','startup.o','program.o','-o','image.elf'),target)
 pre=(target/'program.ll').read_text();post=(target/'program.opt.ll').read_text()
 frames=parse_stack_sizes(invoke(('llvm-readelf','--stack-sizes','program.o'),target).decode())
 validate_compiled_stack(invoke(('llvm-objdump','-d','--no-show-raw-insn','program.o'),target).decode(),frames)
 primitive_frames={s:0 for _,s,_,_ in CSR_OPERATIONS.values()}|{s:16 for s in TRANSITIONS.values()}|{'lemma_exec_read_time':0}
 stack=weighted_stack_graph(post,frames,primitive_frames)
 chains=stack['weighted_frame_chains']
 for root_name,bound in [('main',8192),('probe',4096),('trap',4096-288)]:
  require(chains[names[SOURCE+root_name]]['bytes']<=bound,'counter-su bounded '+root_name+' stack overlaps fixed partition')
 ir={'before':validate_ir(pre,unit,optimized=False),'after':validate_ir(post,unit,optimized=True,optimization='O2')}
 symbols=invoke(('llvm-readelf','-s','--wide','image.elf'),target).decode();ranges=function_ranges(symbols)
 require(defined_function_symbols(symbols)==set(names.values())|{s for _,s,_,_ in CSR_OPERATIONS.values()}|EXTRA_FUNCTIONS,'counter-su ELF executable provenance differs')
 header=invoke(('llvm-readelf','-h','image.elf'),target).decode()
 require(all(t in header for t in ('ELF64','little endian','RISC-V')) and re.search(r'Flags:\s+0x0(?:\s|$)',header) and '0x80000000' in header,'counter-su ELF hardware attributes differ')
 require('rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0' in invoke(('llvm-readelf','-A','image.elf'),target).decode(),'counter-su ELF unsupported ISA extension')
 require(not invoke(('llvm-nm','--undefined-only','image.elf'),target).strip(),'unknown counter-su runtime dependency')
 require(not relocation_types(invoke(('llvm-readelf','-r','image.elf'),target).decode()),'counter-su runtime relocation')
 segments=parse_load_segments(invoke(('llvm-readelf','-l','--wide','image.elf'),target).decode())
 require(segments and all(0<r['memory_size'] and r['physical_address']==r['virtual_address'] and 0x80000000<=r['virtual_address'] and r['virtual_address']+r['memory_size']<=0x80010000 and not ('W' in r['flags'] and 'E' in r['flags']) for r in segments),'counter-su image escapes immutable firmware envelope')
 invoke(('llvm-objcopy','-O','binary','--only-section=.text','image.elf','code.bin'),target)
 code=(target/'code.bin').read_bytes();primitive=validate_csr_bytes(code,0x80000000,ranges)
 disasm=invoke(('llvm-objdump','-d','--no-show-raw-insn','image.elf'),target).decode()
 validate_machine(disasm,ranges={s:r for s,r in ranges.items() if s not in primitive})
 after=source_inputs(root);after['scripts/check_guest_counter_su.py']=sha256(root/'scripts/check_guest_counter_su.py');after['scripts/check_guest_counters.py']=sha256(root/'scripts/check_guest_counters.py')
 require(after==before,'counter-su consumed compiler/source changed during build')
 receipt={'schema':'lemmasim-guest-counter-su/1','status':'PASS_AUDIT','profile':PROFILE,'boot':'ELF-preload development diagnostic','source_inputs':before,'tools':versions,'upstream':upstream,'linked_objects':['startup.o','program.o'],'artifacts':{p.name:sha256(p) for p in target.iterdir() if p.is_file()},'ir':ir,'primitive_bytes':primitive,'stack':stack,'functions':ranges,'source_symbols':names}
 write_json(out/'audit.json',receipt);return target,ranges,names,receipt

class Native:
 def __init__(self,data,target,path):
  path.mkdir();self.path=path;self.log=(path/'runtime.log').open('xb')
  self.command=[data['binary']['path'],'--session','--image',str(target/'image.elf'),'--rom',data['rom']['path'],'--uart-output',str(path/'uart.bin'),'--ram-dump',f'{BASE:#x}:{SIZE}:'+str(path/'records.bin'),'--report',str(path/'report.json'),'--quiet-uart','--trace-limit','0','--deadline','120']
  self.start=time.monotonic();self.p=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True)
 def call(self,text):
  require(self.p.poll() is None,'native counter-su runtime ended early')
  remaining=120-(time.monotonic()-self.start);require(remaining>0,'native original 120s host bound exceeded')
  self.p.stdin.write(text+'\n');self.p.stdin.flush();ready,_,_=select.select([self.p.stdout],[],[],remaining)
  require(ready,'native counter-su transport deadline exceeded');line=self.p.stdout.readline();require(line,'native counter-su response absent')
  row=json.loads(line);require(row.get('ok') is True,'native counter-su operation failed '+str(row));return row['result']
 def close(self):
  if self.p.poll() is None:
   try:self.call('destroy');self.p.wait(timeout=5)
   except BaseException:self.p.kill();self.p.wait(timeout=5)
  self.log.close()

def native_check(data,target,ranges,names,out):
 a=Native(data,target,out/'rtl-original');b=None;observed=[]
 try:
  enter,enter_size=ranges[TRANSITIONS['counterEnterUser']];access=ranges['lemma_exec_read_counter_cycle'][0]+4
  boundary=None
  # Large clear loop is guest work. Find its first fixed transition, then select
  # an actual CSR PC using individual clocks; never mutate a CSR/PC/register.
  for _ in range(20000):
   state=a.call('run 100');require(not state['finished'],'guest finished before declared snapshot boundary')
   if enter<=state['pc']<enter+enter_size:break
  else:raise Core0Error('bounded fixed User transition not reached within 2M clocks')
  for _ in range(2000):
   state=a.call('run 1')
   if state['pc']==access and state['privilege']==0:boundary=state;break
  require(boundary is not None,'actual first U cycle read PC not reached within transition bound')
  write_json(out/'rtl-boundary.json',boundary)
  prefix=out/'rtl-prefix.chk';a.call('snapshot '+str(prefix));require(a.call('inspect')==boundary,'snapshot changed original live state')
  remaining=5000000-int(boundary['cycle']);require(remaining>0,'native prefix exceeds declared 5M clock bound')
  original=a.call('run '+str(remaining));write_json(out/'rtl-original-final.json',original)
  left=out/'rtl-final-original.chk';a.call('snapshot '+str(left));a.close()
  require(original['finished'] and original['finish_code']==0x5555,'actual RTL counter-su guest rejected hardware')
  records=validate_records((a.path/'records.bin').read_bytes(),ranges)
  b=Native(data,target,out/'rtl-fork');b.call('restore '+str(prefix));fork=b.call('run '+str(remaining));write_json(out/'rtl-fork-final.json',fork)
  right=out/'rtl-final-fork.chk';b.call('snapshot '+str(right));b.close()
  require(fork['finished'] and fork['finish_code']==0x5555,'RTL counter-su private continuation rejected hardware')
  fork_records=validate_records((b.path/'records.bin').read_bytes(),ranges)
  require((b.path/'records.bin').read_bytes()==(a.path/'records.bin').read_bytes(),'guest counter-su suffix records differ')
  require(sha256(left)==sha256(right),'full authoritative same-native suffix archive differs')
  return {'status':'PASS','command':a.command,'host_bound_seconds':120,'clock_bound':5000000,'snapshot_boundary':boundary,'final':original,'records':records,'prefix_sha256':sha256(prefix),'final_sha256':sha256(left),'exact_archive_suffix':True,'fork_final':fork,'fork_command':b.command,'scope':'actual S/U/M counter permission/trap corpus and one inhibited pipeline native suffix; no arbitrary cached-state completeness'}
 finally:
  a.close()
  if b:b.close()

def fast_check(binary,target,dtb,out,ranges):
 from lemmasim_fast import QMP,CPU
 directory=out/'fast';directory.mkdir();log=(directory/'machine.log').open('xb');temporary=tempfile.TemporaryDirectory(prefix='lemma-counter-su-',dir='/tmp')
 process=qmp=None;base=Path(temporary.name)
 command=[str(binary),'-machine','lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1','-bios','none','-kernel',str(target/'image.elf'),'-dtb',str(dtb),'-display','none','-monitor','none','-serial','file:'+str(directory/'uart.bin'),'-qmp','unix:'+str(base/'qmp.sock')+',server=on,wait=off','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031','-global','lemma-paper-pen.raw-output='+str(directory/'input.bin')]
 try:
  start=time.monotonic();process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True);qmp=QMP(base/'qmp.sock',process,120)
  qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':'50000000'});qmp.execute('cont');deadline=start+120
  while qmp.execute('query-status')['running']:
   require(time.monotonic()<deadline,'actual fast counter-su 120s host bound exceeded');time.sleep(.001)
  status=qmp.execute('query-status');records=directory/'records.bin';qmp.execute('pmemsave',{'val':BASE,'size':SIZE,'filename':str(records)})
  values=validate_records(records.read_bytes(),ranges)
  return {'status':'PASS','binary_sha256':sha256(binary),'command':command,'records':values,'machine_status':status,'virtual_ns_bound':50000000,'host_bound_seconds':120,'elapsed_seconds':time.monotonic()-start,'scope':'same genuine guest architectural counter/trap corpus; no processor timing parity or QEMU migration completeness'}
 finally:
  if process and process.poll() is None:
   try:
    if qmp:qmp.execute('quit')
    process.wait(timeout=5)
   except BaseException:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
  if qmp:qmp.close()
  log.close();temporary.cleanup()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--native-bundle',type=Path,required=True);p.add_argument('--timeout',type=int,default=300);p.add_argument('--fast',action='store_true')
 args=p.parse_args();root=repo_root();out=args.work_dir.resolve();out.mkdir(exist_ok=False);start=time.monotonic()
 result={'status':'RUNNING','qualification':'actual guest CSR/privilege/trap instructions; no debugger CSR writes','profile':PROFILE,'plan':{'native_clocks':5000000,'native_boundary_seek_clocks':2002000,'fast_virtual_ns':50000000,'host_seconds_per_backend':120,'build_timeout_per_command':args.timeout}}
 write_json(out/'plan.json',result['plan'])
 try:
  require(1<=args.timeout<=600,'build timeout outside1..600s')
  from silicon_guest_bundle import prepared
  data=prepared(args.native_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');result['native_bundle']=data['native_bundle']
  target,ranges,names,audit=build(root,out,args.timeout);result['guest_sha256']=sha256(target/'image.elf')
  # Each backend has an independent verdict; one actual failure does not erase
  # partial raw records, prevent the other observation, or imply a hardware fix.
  for name,run in [('rtl',lambda:native_check(data,target,ranges,names,out))]:
   try:result[name]=run()
   except BaseException as error:result[name]={'status':'FAIL','error':repr(error)}
  if args.fast:
   fast_data=prepared(args.native_bundle,'qemu','notebook','lemma-silicon-dev/0.3.0');result['fast_bundle']=fast_data['native_bundle']
   try:result['fast']=fast_check(Path(fast_data['qemu']['path']),target,Path(fast_data['workloads']['notebook']['dtb']['path']),out,ranges)
   except BaseException as error:result['fast']={'status':'FAIL','error':repr(error)}
  else:result['fast']={'status':'NOT_RUN'}
  result['status']='PASS_ARCHITECTURAL_BOTH' if result['rtl']['status']=='PASS' and result['fast']['status']=='PASS' else 'PASS_RTL' if not args.fast and result['rtl']['status']=='PASS' else 'FAIL'
 except BaseException as error:result.update(status='FAIL',error=repr(error))
 finally:result['wall_seconds']=time.monotonic()-start;write_json(out/'result.json',result)
 if result['status'] not in ('PASS_RTL','PASS_ARCHITECTURAL_BOTH'):raise SystemExit(1)
 print('GUEST_COUNTER_SU:'+result['status']+' genuine permission/trap corpus and bounded native suffix')
if __name__=='__main__':main()
