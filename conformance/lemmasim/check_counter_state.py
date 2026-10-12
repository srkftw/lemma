#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual selected-profile clock/reset/CSR-engine and exact state checks.

Runs the current source-bound prepared machine and genuine Lean power probe.
CSR writes use the actual pinned debugger engine; guest-issued CSR instruction
and privilege qualification are explicitly absent. Only the separately reviewed
host elapsed-time statistics are permitted checkpoint differences.
"""
import argparse,hashlib,json,os,re,signal,socket,struct,subprocess,sys,tempfile,time
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from lemmasim_fast import QMP, CPU, prepared
from silicon_guest import verify_guest_build
from check_fast_state_equivalence import compare, layout, parse_json, section_payload

PROFILE = 'lemma-silicon-dev/0.3.0'
REVIEWED_CURRENT = '927bef771d31134b73b76a2c219d1717144feec6986b07df5c58ef85d08ad6e5'
REVIEWED_REFERENCE = '80e54f2095774ecdbfe3bcd36e52e7c55b1c5e566ecf869b4c6ed3f8c857b43a'
RELATION = {
 'cycles': '100MHz; floor(T1ns/10)-floor(T0ns/10), absolute fractional phase retained',
 'reset': 'completed paused QMP RESET zeros mcycle/minstret/inhibit/MTIME; no claim of parity with eight RTL reset edges',
 'retirement': 'actual raw QEMU icount minus existing exception adjustment, independent write/reset baseline',
 'checkpoint': 'all serialized bytes exact except two separately source-proven host elapsed-time statistics',
 'guest': 'strict current-source audited genuine Lean power probe, no target changes',
 'engine': 'debugger invokes real CSR handlers; guest-issued CSR instruction and privilege checks remain NOT_RUN',
 'reference': 'optional explicitly reviewed historical A5 binary; absence is NOT_RUN for that comparison',
}

def require(v,m):
 if not v:raise ValueError(m)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def serial_state(checkpoint):
 """Read actual saved UART fields through its independently fixed wire schema.

 This preserves live IRQ state: observing IIR through MMIO could acknowledge a
 pending interrupt. The pinned source/official decoder proof is recorded in the
 Task006 counter evidence. Unsupported schemas reject rather than infer offsets.
 """
 data=checkpoint.read_bytes();info=layout(data)
 metadata=parse_json(data[info['metadata_start']:])
 names=['divider','rbr','ier','iir','lcr','mcr','lsr','msr','scr','fcr_vmstate']
 fields=[{'name':n,'type':'uint16' if i==0 else 'uint8','size':2 if i==0 else 1} for i,n in enumerate(names)]
 expected={'name':'serial','instance_id':0,'vmsd_name':'serial','version':3,
  'fields':[{'name':'serial','type':'struct','struct':{'vmsd_name':'serial','version':3,'fields':fields},'size':11}]}
 require([d for d in metadata['devices'] if d.get('name')=='serial']==[expected],'unsupported UART serializer schema')
 offset,identity=section_payload(data,b'serial',3)
 require(data[offset+11:offset+16]==b'\x7e'+identity,'unsupported UART subsection/footer')
 state={};cursor=offset
 for field in fields:
  size=field['size'];state[field['name']]='0x'+data[cursor:cursor+size].hex();cursor+=size
 return state

class RSP:
 def __init__(self,path):
  self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.socket.settimeout(60)
  self.socket.connect(str(path));self.command('qSupported:qXfer:features:read+')
  require(self.command('qXfer:features:read:target.xml:0,1000')[:1] in (b'm',b'l'),'missing actual target XML')
  xml=b'';offset=0
  while True:
   result=self.command(f'qXfer:features:read:riscv-csr.xml:{offset:x},1000')
   require(result[:1] in (b'm',b'l'),'missing actual dynamic CSR feature')
   xml+=result[1:];offset+=len(result)-1
   require(len(xml)<=256*1024,'CSR XML exceeds bound')
   if result[:1]==b'l':break
  self.xml=xml;self.registers={}
  for reg in ET.fromstring(xml).iter('reg'):
   require('regnum' in reg.attrib,'dynamic CSR lacks exact register number')
   self.registers[reg.attrib['name']]=int(reg.attrib['regnum'],0)
  require({'mcycle','minstret','mcountinhibit'}<=self.registers.keys(),'required actual CSR handlers absent')
 def byte(self):
  b=self.socket.recv(1);require(len(b)==1,'GDB disconnected');return b
 def command(self,text):
  payload=text.encode();packet=b'$'+payload+b'#'+f'{sum(payload)&255:02x}'.encode();self.socket.sendall(packet)
  for _ in range(32):
   char=self.byte()
   if char==b'+':continue
   if char==b'-':raise ValueError('GDB negative checksum acknowledgement')
   require(char==b'$','malformed GDB frame')
   raw=bytearray()
   while True:
    char=self.byte()
    if char==b'#':break
    raw+=char;require(len(raw)<=1<<20,'GDB response exceeds bound')
   checksum=self.byte()+self.byte();require(sum(raw)&255==int(checksum,16),'GDB response checksum')
   self.socket.sendall(b'+');data=bytearray();i=0
   while i<len(raw):
    if raw[i]==ord('}'):
     i+=1;require(i<len(raw),'truncated GDB escape');data.append(raw[i]^32)
    elif raw[i]==ord('*'):
     i+=1;require(i<len(raw) and data,'truncated GDB run length');data+=bytes([data[-1]])*(raw[i]-29)
    else:data.append(raw[i])
    i+=1
   if data[:1] in (b'T',b'S') and text!='?':continue
   return bytes(data)
  raise ValueError('GDB response packet bound')
 def read(self,name):
  text=self.command('p'+format(self.registers[name],'x'))
  require(re.fullmatch(rb'[0-9a-fA-F]{16}',text),'malformed CSR read '+name)
  return int.from_bytes(bytes.fromhex(text.decode()),'little')
 def write(self,name,value):
  require(self.command('P'+format(self.registers[name],'x')+'='+value.to_bytes(8,'little').hex())==b'OK','CSR write rejected '+name)
 def close(self):self.socket.close()

class Machine:
 def __init__(self,binary,guest,directory,timeout):
  self.timeout=timeout;self.binary=Path(binary);self.guest=Path(guest);self.directory=Path(directory);self.directory.mkdir()
  self.temporary=tempfile.TemporaryDirectory(prefix='lemma-counter-',dir='/tmp');base=Path(self.temporary.name)
  self.log=(self.directory/'machine.log').open('xb');self.qmp=None;self.rsp=None
  self.command=[str(binary),'-machine','lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1','-bios','none',
   '-kernel',str(self.guest/'image.elf'),'-dtb',str(self.guest/'platform.dtb'),'-display','none','-monitor','none',
   '-serial','file:'+str(self.directory/'uart.bin'),'-qmp','unix:'+str(base/'qmp.sock')+',server=on,wait=off',
   '-gdb','unix:'+str(base/'gdb.sock')+',server=on,wait=off','-S','-no-shutdown',
   '-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031',
   '-global','lemma-paper-pen.raw-output='+str(self.directory/'input.bin')]
  self.process=subprocess.Popen(self.command,stdout=self.log,stderr=self.log,start_new_session=True)
  try:self.qmp=QMP(base/'qmp.sock',self.process,self.timeout);self.rsp=RSP(base/'gdb.sock')
  except BaseException:self.close();raise
 def get(self,prop):return self.qmp.execute('qom-get',{'path':'/machine/lemma-hardware','property':prop})
 def state(self):
  registers=self.qmp.execute('human-monitor-command',{'command-line':'info registers'})
  values={k:int(v,16) for k,v in re.findall(r'^\s*(mcycle|minstret|mcountinhibit|time|pc)\s+([0-9a-f]{16})\s*$',registers,re.M)}
  require({'mcycle','minstret','mcountinhibit','time','pc'}<=values.keys(),'actual register inventory absent')
  return {'ns':int(self.get('virtual-time')),'registers':values,'raw_register_dump':registers,'device_state':json.loads(self.get('device-state'))}
 def run(self,ns):
  require(ns>=int(self.get('virtual-time')),'time reversal')
  self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':str(ns)})
  self.qmp.execute('cont');deadline=time.monotonic()+self.timeout
  while self.qmp.execute('query-status')['running']:
   require(time.monotonic()<deadline,'bounded QEMU run timeout');time.sleep(.001)
  result=self.state();require(result['ns']==ns,'exact declared8ns boundary missed');return result
 def snapshot(self,path):self.qmp.execute('lemma-save-machine',{'filename':str(path)})
 def restore(self,path):self.qmp.execute('lemma-load-machine',{'filename':str(path)})
 def warm(self):
  generation=self.qmp.reset_generation;self.qmp.execute('system_reset');deadline=time.monotonic()+self.timeout
  while self.qmp.reset_generation==generation:
   self.qmp.execute('query-status');require(time.monotonic()<deadline,'reset event timeout')
  return self.state()
 def close(self):
  if getattr(self,'rsp',None):self.rsp.close();self.rsp=None
  if getattr(self,'process',None):
   if self.process.poll() is None:
    try:self.qmp.execute('quit') if self.qmp else None;self.process.wait(timeout=5)
    except BaseException:
     if self.process.poll() is None:os.killpg(self.process.pid,signal.SIGKILL)
     self.process.wait(timeout=5)
  if getattr(self,'qmp',None):self.qmp.close();self.qmp=None
  if getattr(self,'log',None):self.log.close()
  if getattr(self,'temporary',None):self.temporary.cleanup()

def rejected_startup(binary,guest,out,label,cpu,icount,expected):
 path=out/('startup-'+label+'.log')
 command=[str(binary),'-machine','lemma-silicon-fast','-cpu',cpu,'-m','128M','-smp','1','-bios','none',
  '-kernel',str(guest/'image.elf'),'-dtb',str(guest/'platform.dtb'),'-display','none','-monitor','none',
  '-serial','none','-S','-icount',icount]
 with path.open('xb') as log:
  process=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
  try:code=process.wait(timeout=15)
  finally:
   if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
 require(code==1,'unsupported startup did not return configuration failure: '+label)
 message=path.read_text();require(expected in message and 'assertion' not in message.lower(),'wrong unsupported startup failure: '+label)
 return {'name':label,'command':command,'returncode':code,'message':message,'all_processes_reaped':process.poll() is not None}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--guest-build',type=Path,help='strict audited current Lean power probe build; defaults to prepared power guest')
 parser.add_argument('--historical-reference',type=Path,help='optional previously reviewed A5 binary (SHA fixed in this checker)')
 parser.add_argument('--output-dir','--work-dir',dest='work_dir',type=Path,required=True)
 parser.add_argument('--timeout',type=int,default=60,help='bounded per-machine virtual run/request seconds, 1..300')
 parser.add_argument('--deadline',type=int,default=420,help='total host deadline in seconds, 1..900')
 args=parser.parse_args();require(1<=args.timeout<=300 and 1<=args.deadline<=900,'host deadline outside supported bounds')
 out=args.work_dir.resolve();out.mkdir(exist_ok=False)
 data=prepared('power',PROFILE);binary=Path(data['qemu']['path'])
 require(sha(binary)==REVIEWED_CURRENT,'current prepared binary lacks this checker exact reviewed identity')
 args.candidate=binary
 guest=(args.guest_build or Path(data['workloads']['power']['image']['path']).parent).resolve()
 build=json.loads((guest/'build.json').read_text())
 verify_guest_build(guest,'lemmasim-silicon-power-probe',build['optimization'])
 audit=json.loads((guest/'audit.json').read_text());require(audit['image_sha256']==sha(guest/'image.elf'),'audited ELF changed')
 args.old=args.historical_reference
 if args.old:require(sha(args.old)==REVIEWED_REFERENCE,'historical reference lacks its exact reviewed identity')
 result={'status':'FAIL','relation_declared_before_execution':RELATION,
  'candidate':{'path':str(binary),'sha256':sha(binary)},'prepared':{'path':'build/lemmasim/fast-prepared-0.3.0.json','sha256':sha(ROOT/'build/lemmasim/fast-prepared-0.3.0.json')},
  'reference':({'status':'SELECTED','path':str(args.old.resolve()),'sha256':sha(args.old)} if args.old else {'status':'NOT_RUN','reason':'no identified historical reference supplied'}),
  'guest':{n:sha(guest/n) for n in ['image.elf','platform.dtb','descriptor.bin','audit.json']},
  'observers':{str(n.relative_to(ROOT)):sha(n) for n in [Path(__file__).resolve(),ROOT/'scripts/lemmasim_fast.py',ROOT/'conformance/lemmasim/check_fast_state_equivalence.py']},
  'engine_scope':'GDB calls real pinned CSR handlers; guest-issued CSR/privilege qualification absent'}
 def deadline(signum,frame):raise TimeoutError('total counter observer host deadline exceeded')
 previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(args.deadline)
 machines=[]
 try:
  result['unsupported_startup']=[
   rejected_startup(args.candidate.resolve(),guest,out,'adaptive',CPU,'shift=auto','silicon0.3 counters require precise icount'),
   rejected_startup(args.candidate.resolve(),guest,out,'filtered-pmu',CPU+',smcntrpmf=true','shift=3,align=off,sleep=off','silicon0.3 counters require precise icount'),
   rejected_startup(args.candidate.resolve(),guest,out,'programmable-pmu',CPU+',zihpm=true','shift=3,align=off,sleep=off','requires the declared RV64IM/MSU/Sv39/PMP scalar CPU configuration')]
  old=None;stale=None
  if args.old:
   old=Machine(args.old.resolve(),guest,out/'old',args.timeout);machines.append(old);a=old.run(100000000)
   stale=out/'stale-a5.chk';old.snapshot(stale)
  candidate=Machine(args.candidate.resolve(),guest,out/'candidate',args.timeout);machines.append(candidate)
  b=candidate.run(100000000);result['cold']={'candidate':b}
  require(b['registers']['mcycle']==10000000,'cold100MHz counter rate')
  require(b['registers']['time']==1000000,'cold MTIME rate changed')
  cold_checkpoint=out/'cold.chk';candidate.snapshot(cold_checkpoint);cold_serial=serial_state(cold_checkpoint)
  if old:
   result['cold']['reference']=a
   require(a['registers']['mcycle']==100000000,'historical reference counter rate changed')
   require(a['registers']['minstret']==b['registers']['minstret'],'actual retired count source/schedule changed')
   require(a['registers']['time']==b['registers']['time'],'historical reference MTIME differs')
   require((out/'old/uart.bin').read_bytes()==(out/'candidate/uart.bin').read_bytes(),'historical reference guest UART changed')
   result['reference']['status']='PASS'

  repeated=[candidate.state() for _ in range(3)];require(all(s==repeated[0] for s in repeated),'inspection mutated state');result['repeated_reads']=repeated
  reset=candidate.warm();require(all(reset['registers'][k]==0 for k in ['mcycle','minstret','mcountinhibit','time']),'warm counters/inhibit/time not zero')
  warm_checkpoint=out/'warm-reset.chk';candidate.snapshot(warm_checkpoint);warm_serial=serial_state(warm_checkpoint)
  require(cold_serial['fcr_vmstate']=='0xc1','genuine cold guest did not exercise enabled FIFO state')
  require(warm_serial['fcr_vmstate']=='0x00' and warm_serial['iir']=='0x01','warm actual UART reset registers inconsistent')
  warm_fork=Machine(args.candidate.resolve(),guest,out/'warm-fork',args.timeout);machines.append(warm_fork);warm_fork.restore(warm_checkpoint)
  restored_reset=warm_fork.state();require(reset==restored_reset,'warm immediate restored register/private state changed')
  restored_checkpoint=out/'warm-restored.chk';warm_fork.snapshot(restored_checkpoint);restored_serial=serial_state(restored_checkpoint)
  reset_observation=compare(warm_checkpoint.read_bytes(),restored_checkpoint.read_bytes())
  require(reset_observation['status']=='PASS' and warm_serial==restored_serial,'warm UART/private checkpoint changed on load')
  after=candidate.run(101000000);require(after['registers']['mcycle']==100000 and after['registers']['time']==10000,'warm100MHz rate')
  warm_replayed=warm_fork.run(101000000);warm_left=out/'warm-final-original.chk';candidate.snapshot(warm_left)
  warm_right=out/'warm-final-replayed.chk';warm_fork.snapshot(warm_right)
  warm_observation=compare(warm_left.read_bytes(),warm_right.read_bytes())
  require(after==warm_replayed and warm_observation['status']=='PASS','warm exact CPU/RAM/UART continuation differs')
  result['warm']={'reset':reset,'restored_reset':restored_reset,'cold_uart':cold_serial,'warm_uart':warm_serial,
   'restored_uart':restored_serial,'reset_checkpoint_observation':reset_observation,'after':after,'replayed':warm_replayed,
   'continuation_checkpoint_observation':warm_observation}
  warm_fork.close();machines.remove(warm_fork)
  fractional=candidate.run(101001504);prefix=out/'fractional.chk';candidate.snapshot(prefix)
  end=candidate.run(101002008);left=out/'fractional-final-original.chk';candidate.snapshot(left)
  fork=Machine(args.candidate.resolve(),guest,out/'fractional-fork',args.timeout);machines.append(fork);fork.restore(prefix)
  replay=fork.run(101002008);right=out/'fractional-final-replayed.chk';fork.snapshot(right)
  observation=compare(left.read_bytes(),right.read_bytes());require(observation['status']=='PASS' and end==replay,'fractional exact continuation mismatch')
  result['fractional']={'prefix':fractional,'end':end,'replayed':replay,'checkpoint_observation':observation}
  # Real CSR write engine, not a target foreign instruction stream.
  candidate.rsp.write('mcycle',123);require(candidate.rsp.read('mcycle')==123,'mcycle write lost')
  candidate.rsp.write('mcountinhibit',5);candidate.rsp.write('minstret',456);inhibited=candidate.state()
  candidate.rsp.write('mcycle',789);inhibited=candidate.state();freeze=out/'inhibited.chk';candidate.snapshot(freeze)
  unchanged=candidate.run(101003008);require(unchanged['registers']['mcycle']==789 and unchanged['registers']['minstret']==456,'inhibit failed')
  candidate.rsp.write('mcountinhibit',0);resumed=candidate.run(101003512)
  require(resumed['registers']['mcycle']==789+101003512//10-101003008//10,'resume phase/rate failed')
  left=out/'inhibit-final-original.chk';candidate.snapshot(left)
  fork2=Machine(args.candidate.resolve(),guest,out/'inhibit-fork',args.timeout);machines.append(fork2);fork2.restore(freeze)
  fork2.run(101003008);fork2.rsp.write('mcountinhibit',0);replay=fork2.run(101003512);right=out/'inhibit-final-replayed.chk';fork2.snapshot(right)
  observation=compare(left.read_bytes(),right.read_bytes());require(observation['status']=='PASS' and resumed==replay,'inhibit exact continuation mismatch')
  result['write_inhibit']={'initial':inhibited,'frozen':unchanged,'resumed':resumed,'replayed':replay,'checkpoint_observation':observation}
  candidate.rsp.write('mcycle',(1<<64)-3);overflow=candidate.run(101003552)
  require(overflow['registers']['mcycle']==1,'counter modulo64 write/wrap differs');result['overflow']=overflow
  wrong=bytearray(prefix.read_bytes());name=b'cpu/lemma-counter-clock';needle=b'\x05'+bytes([len(name)])+name+struct.pack('>I',1)
  require(wrong.count(needle)==1,'counter subsection identity absent/ambiguous');offset=wrong.index(needle)+len(needle)
  require(struct.unpack('>Q',wrong[offset:offset+8])[0]==100000000,'counter marker mismatch');wrong[offset+7]^=1
  path=out/'wrong-frequency.chk';path.write_bytes(wrong)
  missing=bytearray(prefix.read_bytes());start=missing.index(needle)
  # Exact reviewed fixed schema: marker +2cfg words +2*12 privateu64 words.
  body_bytes=3*8+2*12*8
  del missing[start:start+len(needle)+body_bytes]
  missing_path=out/'missing-counter-subsection.chk';missing_path.write_bytes(missing)
  rejected=[];negative_paths=[('missing-counter-subsection',missing_path),('wrong-frequency',path)]
  if stale:negative_paths.append(('stale-A5',stale))
  for name,path in negative_paths:
   isolated=Machine(args.candidate.resolve(),guest,out/('negative-'+name),args.timeout);machines.append(isolated)
   try:isolated.restore(path)
   except RuntimeError as e:rejected.append({'name':name,'rejected':True,'error':str(e)})
   else:raise ValueError('unsupported counter state accepted: '+name)
   isolated.close();machines.remove(isolated)
  result['negative_state']=rejected;result['status']='PASS'
 except BaseException as error:
  result['error']=repr(error);raise
 finally:
  for m in machines:m.close()
  result['all_processes_reaped']=all(m.process.poll() is not None for m in machines)
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  signal.alarm(0);signal.signal(signal.SIGALRM,previous)
 print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'candidate':result['candidate']},indent=2))

if __name__=='__main__':main()
