#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual checked Lean Power-v2 policy through the public native RTL session.

No host watchdog MMIO or fabricated controller state. The immutable ELF preload
is explicitly development boot; this does not qualify notebook/update recovery.
"""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from lemmasim_session import request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from check_notebook_workflow import guest_events

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def require(v,message):
 if not v:raise ValueError(message)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--boot-cycles',type=int,default=20000000)
 p.add_argument('--deadline',type=float,default=450);p.add_argument('--timeout',type=int,default=45)
 a=p.parse_args();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 started=time.monotonic();deadline=started+a.deadline;directory=out/'session'
 result={'status':'FAIL','scope':__doc__,'bounds':{'boot_cycles':a.boot_cycles,'host_seconds':a.deadline,'operation_timeout':a.timeout}}
 command=[sys.executable,ROOT/'scripts/lemmasim','session','--backend','rtl','--profile','lemma-silicon-dev/0.4.0','--workload','power','--mode','laboratory','--headless','--paused','--session-dir',directory,'--timeout',str(a.timeout)]
 result['command']=list(map(str,command));process=None;commands=(out/'commands.jsonl').open('x');log=(out/'launch.log').open('xb')
 def control(value):
  require(time.monotonic()<deadline,'declared host campaign bound exceeded')
  commands.write(json.dumps(value)+'\n');commands.flush()
  return request(directory,value,timeout=min(a.timeout+15,deadline-time.monotonic()))
 def inspect():return control({'action':'inspect'})['machine']
 def run(n):return control({'action':'run','cycles':n})
 def records():return [row for row in guest_events(directory/'uart.bin') if row[0]==0x445]
 def boot(cause,epoch):
  before=inspect()['cycle'];t=time.monotonic()
  while (0x445,cause,epoch,0,0) not in records():
   state=inspect();require(not state['finished'],'guest failed before reset-cause report')
   require(state['cycle']-before<a.boot_cycles,'declared cold/restart instruction bound exceeded')
   run(min(100000,a.boot_cycles-(state['cycle']-before)))
  return {'state':inspect(),'host_seconds':time.monotonic()-t,'records':records()}
 try:
  process=subprocess.Popen(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  launch_deadline=min(deadline,time.monotonic()+60)
  while not (directory/'session.json').exists():
   require(process.poll() is None,'public source-bound launch failed; see launch.log')
   require(time.monotonic()<launch_deadline,'public owner startup deadline')
   time.sleep(0.02)
  initial=control({'action':'inspect'});result['identity']=initial['identity']
  result['initial']=initial['machine'];result['source_validated_public_startup']=True
  (out/'startup.json').write_text(json.dumps(initial,indent=2)+'\n')
  first=inspect();require(first['cycle']==0,'cold machine did not start at cycle0')
  while not first['power']['watchdog_armed']:
   require(not first['finished'] and first['cycle']<a.boot_cycles,'guest did not arm watchdog within bound')
   run(min(10000,a.boot_cycles-first['cycle']));first=inspect()
  require(records()==[(0x445,1,0,0,0)],'real Lean cold report identity/cause differs')
  require(0<first['power']['watchdog_remaining']<=100000,'wrong guest-configured watchdog bound')
  arm_boundary=first['cycle']-(100000-first['power']['watchdog_remaining'])
  # Reach actual WFI: distinguish watchdog progress from guest retirement.
  stalled=None
  for _ in range(25):
   before=inspect();run(1000);after=inspect()
   require(after['power']['watchdog_armed'],'watchdog expired before stalled-policy observation')
   if before['retired']==after['retired'] and before['pc']==after['pc']:
    stalled=after;break
  require(stalled is not None,'actual WFI did not stall supervised instruction retirement')
  result['armed']={'first':first,'arm_boundary':arm_boundary,'stalled':stalled}
  snap=out/'armed-snapshot';t=time.monotonic();control({'action':'snapshot','path':str(snap)})
  result['snapshot']={'host_seconds':time.monotonic()-t,'bytes':(snap/'machine.chk').stat().st_size}
  saved=inspect();remaining=saved['power']['watchdog_remaining'];require(remaining>1,'snapshot lacks preterminal watchdog state')
  before_retired=saved['retired'];run(remaining-1);terminal=inspect()
  require(terminal['power']['watchdog_remaining']==1 and terminal['power']['watchdog_armed'] and not terminal['power']['domain_reset'],'watchdog expired early')
  require(terminal['retired']==before_retired,'supervised guest progressed before watchdog expiry')
  run(1);expired=inspect()
  require(expired['cycle']==arm_boundary+100000 and expired['power']['reset_cause']==4 and expired['power']['reset_remaining']==8 and expired['power']['domain_reset'],'watchdog terminal edge differs')
  run(7);require(inspect()['power']['reset_remaining']==1 and inspect()['power']['domain_reset'],'reset interval shorter than eight edges')
  run(1);require(not inspect()['power']['domain_reset'],'reset interval longer than eight edges')
  result['expiry']=expired;result['watchdog_restart']=boot(4,1)
  final=inspect();end=out/'watchdog-complete';control({'action':'snapshot','path':str(end)})
  uart_start=(directory/'uart.bin').stat().st_size
  control({'action':'restore','path':str(snap)});run(final['cycle']-saved['cycle'])
  replay=out/'watchdog-replay';control({'action':'snapshot','path':str(replay)})
  require(sha(end/'machine.chk')==sha(replay/'machine.chk'),'arbitrary preterminal native checkpoint suffix differs')
  result['exact_suffix']={'whole_checkpoint_sha256':sha(end/'machine.chk'),'cycles':final['cycle']-saved['cycle'],'state':inspect()}
  result['replayed_uart_sha256']=hashlib.sha256((directory/'uart.bin').read_bytes()[uart_start:]).hexdigest()
  control({'action':'inject','kind':'pgood','level':0});run(2)
  low=inspect();require(low['power']['reset_cause']==6 and low['power']['domain_reset'],'power-good loss not admitted')
  control({'action':'inject','kind':'pgood','level':1});run(8)
  require(not inspect()['power']['domain_reset'],'safe qualification did not release reset')
  result['power_good_restart']=boot(6,2)
  control({'action':'inject','kind':'brownout','level':1});run(2);brown=inspect()
  require(brown['power']['reset_cause']==5 and brown['power']['reset_epoch']==3,'brownout reset cause/epoch differs')
  run(10);require(inspect()['power']['reset_epoch']==3 and inspect()['power']['reset_remaining']==8,'held brownout repeated loss/reset epoch')
  control({'action':'inject','kind':'brownout','level':0});run(8)
  result['brownout_restart']=boot(5,3)
  result['status']='PASS';result['records']=records()
 except BaseException as e:result['error']=str(e);raise
 finally:
  if process is not None:
   if process.poll() is None:
    try:control({'action':'destroy'});process.wait(timeout=10)
    except BaseException:
     if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
     try:process.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
   result['owner_exit_code']=process.returncode
  commands.close();log.close();result['host_seconds']=time.monotonic()-started
  result['observer_sha256']=sha(__file__)
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'host_seconds':result['host_seconds'],'expiry_cycle':result['expiry']['cycle']},indent=2))
if __name__=='__main__':main()
