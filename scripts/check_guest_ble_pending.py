#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observational startup/data Pending native BLE forks; captured tape only.

The delay process forwards actual hosted Lean frames unchanged. It does not
construct replies, calculate packets, make link decisions or acknowledge data.
"""
import argparse,csv,hashlib,json,os,selectors,shutil,signal,struct,subprocess,sys,time
from pathlib import Path
from lemmasim_session import request
from check_ble_wire_peer import encode
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from check_notebook_workflow import guest_events

DELAY='''import subprocess,sys,threading,time
from pathlib import Path
root=Path(sys.argv[1]);command=sys.argv[2:]
child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr)
def forward():
 try:
  while True:
   line=sys.stdin.buffer.readline(512)
   if not line:break
   child.stdin.write(line);child.stdin.flush()
 except (BrokenPipeError,ValueError):pass
threading.Thread(target=forward,daemon=True).start()
try:
 index=0
 while True:
  line=child.stdout.readline(257)
  if not line:break
  if len(line)>256 or not line.endswith(b"\\n"):raise RuntimeError("raw peer frame bound")
  if index<2:
   label="startup" if index==0 else "data"
   (root/("waiting-"+label)).write_bytes(line)
   limit=time.monotonic()+30
   while not (root/("release-"+label)).exists():
    if time.monotonic()>limit:raise RuntimeError("raw transport delay bound")
    time.sleep(.01)
  sys.stdout.buffer.write(line);sys.stdout.buffer.flush();index+=1
finally:
 if child.poll() is None:child.terminate()
 try:child.wait(timeout=5)
 except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
'''

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()
def require(value,message):
 if not value:raise ValueError(message)
def altered_tape(source,destination,request_id,kind):
 """Independent log-shape reader: change request bytes or accepted phase."""
 wire=bytearray(source.read_bytes());at=72;changed=0
 while at<len(wire):
  tag,identity,issued,header,length=struct.unpack_from('<5Q',wire,at);at+=40
  require(length<=27,'unexpected captured request bound')
  if identity==request_id and kind=='payload':
   require(length>0,'no opaque request bytes to mutate');wire[at]^=1;changed+=1
  at+=length;accepted,count=struct.unpack_from('<2Q',wire,at)
  if identity==request_id and tag==1 and kind=='phase':struct.pack_into('<Q',wire,at,accepted+1);changed+=1
  at+=16+count
 require(changed==(2 if kind=='payload' else 1),'mutation did not select exact inherited request')
 destination.write_bytes(wire)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--attach',action='store_true',help='Resume the already validated owned live fixture in this output')
 p.add_argument('--deadline',type=int,default=360);a=p.parse_args();out=a.work_dir.resolve()
 if not out.is_relative_to(ROOT/'build') or not 60<=a.deadline<=900:p.error('bounded output under build required')
 if a.attach:
  if not (out/'startup-observation.json').exists() or (out/'result.json').exists():p.error('attach needs retained startup fixture without final receipt')
  require((out/'delay.py').read_text()==DELAY,'retained raw transport wrapper differs')
 else:
  if out.exists():p.error('unused output required')
  out.mkdir(parents=True);(out/'delay.py').write_text(DELAY)
 directory=out/'session';started=time.monotonic();deadline=started+a.deadline
 result={'schema':'lemma-ble-pending-evidence/1','status':'FAIL','scope':'same-native startup and data Pending checkpoints, actual delayed hosted Lean frames, private tape-only continuation; no full Bluetooth, USB or durable radio receipt'}
 owner=None;log=None;commands=(out/'pending-commands.jsonl').open('x')
 def control(value):
  require(time.monotonic()<deadline,'whole-machine Pending host bound exceeded');commands.write(json.dumps(value)+'\n');commands.flush()
  return request(directory,value,timeout=min(130,deadline-time.monotonic()))
 def inspect():return control({'action':'inspect'})['machine']
 def run(n):control({'action':'run','cycles':n})
 def snapshot(label):
  before=inspect();path=out/label;capture=Path(before['ble']['capture_path']);old=sha(capture);t=time.monotonic()
  control({'action':'snapshot','path':str(path)});after=inspect()
  require(after==before and sha(capture)==old,'snapshot polled, admitted, drained or changed original pending work')
  require(struct.unpack_from('<Q',(path/'machine.chk').read_bytes(),8)[0]==5,'Pending container successor missing')
  return {'before':before,'after':after,'seconds':time.monotonic()-t,'checkpoint_bytes':(path/'machine.chk').stat().st_size,'sha256':sha(path/'machine.chk')}
 def events():return [v for v in guest_events(directory/'uart.bin') if 0x450<=v[0]<=0x453]
 try:
  if not a.attach:
   peer=[sys.executable,str(out/'delay.py'),str(out),shutil.which('nix'),'develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean']
   command=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.5.0','--workload','ble','--session-dir',str(directory),'--mode','laboratory','--headless','--paused','--quantum','1000','--ble-peer',peer[0],'--ble-peer-timeout-ms','30000','--ble-drop-packets','1']+['--ble-peer-arg='+v for v in peer[1:]]
   (out/'launch-argv.json').write_text(json.dumps(command,indent=2)+'\n');log=(out/'launch.log').open('xb');owner=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   while not (directory/'session.json').exists():
    require(owner.poll() is None and time.monotonic()<min(deadline,started+60),'source-validated public startup failed');time.sleep(.02)
   require(inspect()['ble']['pending_external']==1 and inspect()['cycle']==0,'cold startup handshake Pending absent')
   result['startup']=snapshot('startup');(out/'release-startup').touch()
  else:result['startup']=json.loads((out/'startup-observation.json').read_text())
  result['identity']=control({'action':'inspect'})['identity'];result['source_validated_public_startup']=True
  require(result['startup']['before']==result['startup']['after'] and result['startup']['before']['cycle']==0 and result['startup']['before']['ble']['pending_external']==1,'startup snapshot altered machine or omitted Pending')
  while True:
   state=inspect();result['last_live']=state
   require(not state['finished'],'guest failed before Pending data request: '+str(state['finish_code']))
   require(state['cycle']<20000000,'Pending data request did not reach declared first-packet bound')
   if state['ble']['peer_ready'] and state['ble']['pending_external'] and state['ble']['actual_rx_heads']==1:break
   run(1000)
  result['data']=snapshot('data')
  require((out/'waiting-data').exists(),'the delayed frame was not an actual hosted Lean response')
  before=inspect();run(3000);after=inspect()
  require(after['cycle']==before['cycle']+3000 and after['ble']['pending_external']==1 and after['ble']['accepted_replies']==1,'pending external transport stalled clocks or manufactured acceptance')
  result['pending_live_progress']={'before':before,'after':after};(out/'release-data').touch()
  while not any(v[0]==0x452 for v in events()):
   state=inspect();result['last_live']=state
   require(not state['finished'] and state['cycle']<20000000 and not any(v[0]==0x453 for v in events()),'actual guest failed lost-ACK retry');run(10000)
  final=inspect();result['final']=final;result['guest_records']=events();result['complete']=snapshot('complete')
  require([v[1] for v in events() if v[0]==0x450]==[0,1],'guest did not perform exactly one retry')
  require('ACCEPTED 1 DUPLICATES 1 PENDING 12 4c4d434d5030303101000200' in final['ble']['accepted_state'],'hosted Lean opaque dedup result differs')
  rows=list(csv.DictReader((directory/'ble-wire.csv').open()));chip=''.join(v['bit'] for v in rows if v['endpoint']=='chip');peer=''.join(v['bit'] for v in rows if v['endpoint']=='peer')
  require(chip==encode(2,list(bytes.fromhex('4c4d434d5030303101000200')))*2 and peer==encode(5,[])*2,'generated whole-machine samples differ from independent reference')
  original=Path(final['ble']['capture_path']);old_hash=sha(original);tape=out/'private.outcomes';shutil.copy2(original,tape)
  control({'action':'destroy'})
  if owner is not None:owner.wait(timeout=10)
  # Original peer is gone before either fork. The only external completion
  # source is the already captured tape privately copied above.
  prepared=json.loads((ROOT/'build/lemmasim/rtl-prepared-0.5.0.json').read_text());binary=prepared['binary']['path']
  require(sha(binary)==result['identity']['runtime'],'fork executable differs from validated original machine')
  result['forks']={}
  for label,identity in [('startup',0),('data',1)]:
   branch=out/(label+'-fork');branch.mkdir();errors=(branch/'errors.log').open('xb')
   command=[binary,'--restore',str(out/label/'machine.chk'),'--uart-output',str(branch/'uart.bin'),'--session','--ble-capture',str(branch/'outcomes'),'--fork-directory',str(branch),'--deadline','120']
   process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,start_new_session=True,text=True,bufsize=1);ready=selectors.DefaultSelector();ready.register(process.stdout,selectors.EVENT_READ)
   def raw(line):
    require(time.monotonic()<deadline,'private suffix host bound exceeded');process.stdin.write(line+'\n');process.stdin.flush();require(ready.select(min(130,deadline-time.monotonic())),'private response bound');wire=process.stdout.readline();require(wire,'private machine ended');return json.loads(wire)
   def call(line):
    r=raw(line);require(r.get('ok'),r.get('error','private command failed'));return r['result']
   def rejected(line,needle):
    before=call('inspect');capture=Path(before['ble']['capture_path']);old=sha(capture);reply=raw(line)
    require(not reply.get('ok') and needle in reply.get('error',''),'unexpected private rejection: '+str(reply))
    require(call('inspect')==before and sha(capture)==old,'rejected private request changed authoritative state/capture');return reply['error']
   try:
    initial=call('inspect');require(initial['ble']['fork_suspended'] and initial['ble']['pending_external'],'private Pending did not remain suspended')
    call('snapshot '+str(branch/'unchanged.chk'));require(sha(branch/'unchanged.chk')==sha(out/label/'machine.chk'),'restoration changed authoritative Pending bytes')
    observation={'initial':initial,'no_tape_rejection':rejected('run 1','captured outcomes')}
    bad=branch/'wrong-phase.outcomes';altered_tape(tape,bad,identity,'phase');observation['wrong_phase_rejection']=rejected('ble-outcomes '+str(bad),'inherited request and poll boundary')
    if identity:
     bad=branch/'wrong-bytes.outcomes';altered_tape(tape,bad,identity,'payload');observation['wrong_bytes_rejection']=rejected('ble-outcomes '+str(bad),'inherited request and poll boundary')
    t=time.monotonic();call('ble-outcomes '+str(tape));call('run '+str(final['cycle']-initial['cycle']));call('snapshot '+str(branch/'complete.chk'))
    require(sha(branch/'complete.chk')==sha(out/'complete/machine.chk'),'private Pending suffix differs from original accepted suffix')
    observation.update({'suffix_cycles':final['cycle']-initial['cycle'],'suffix_seconds':time.monotonic()-t,'checkpoint_sha256':sha(branch/'complete.chk')});result['forks'][label]=observation
   finally:
    if process.poll() is None:
     try:call('destroy');process.wait(timeout=10)
     except BaseException:
      if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
      process.wait(timeout=10)
    ready.close();errors.close()
  require(sha(original)==old_hash,'private forks changed original accepted capture');result['original_tape_sha256']=old_hash;result['status']='PASS'
 except BaseException as e:result['error']=str(e);raise
 finally:
  try:request(directory,{'action':'destroy'},timeout=10)
  except BaseException:pass
  if owner is not None and owner.poll() is None:
   os.killpg(owner.pid,signal.SIGTERM)
   try:owner.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(owner.pid,signal.SIGKILL);owner.wait(timeout=10)
  if log is not None:log.close()
  commands.close();result['host_seconds']=time.monotonic()-started;result['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'cycles':result['final']['cycle'],'host_seconds':result['host_seconds']},indent=2))
if __name__=='__main__':main()
