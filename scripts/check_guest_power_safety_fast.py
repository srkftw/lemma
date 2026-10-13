#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real checked Lean Power-v2 driver/WFI/reset reports on functional fast backend.

QEMU instruction time is not RTL pipeline timing. This checks the declared
independent Power-v2 device clock, reset interval and identical guest reports;
it does not establish general CPU timing or arbitrary cached-state continuation.
"""
import argparse,json,os,re,signal,subprocess,sys,time
from pathlib import Path
from lemmasim_session import request
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from check_notebook_workflow import guest_events
from check_guest_power_safety import sha,require

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--deadline',type=float,default=180);p.add_argument('--boot-cycles',type=int,default=20000000);a=p.parse_args()
 out=a.work_dir.resolve();out.mkdir();d=out/'session';start=time.monotonic();deadline=start+a.deadline
 peak_rss=0
 r={'status':'FAIL','scope':__doc__,'bounds':{'host_seconds':a.deadline,'boot_cycles':a.boot_cycles},'observer_sha256':sha(__file__)}
 cmd=[sys.executable,ROOT/'scripts/lemmasim','session','--backend','qemu','--profile','lemma-silicon-dev/0.4.0','--workload','power','--mode','laboratory','--headless','--paused','--session-dir',d,'--timeout','30']
 log=(out/'launch.log').open('xb');calls=(out/'commands.jsonl').open('x');proc=None
 def resources():
  nonlocal peak_rss
  if proc is None:return
  children=Path('/proc')/str(proc.pid)/'task'/str(proc.pid)/'children'
  if not children.exists():return
  for child in children.read_text().split():
   status=Path('/proc')/child/'status'
   try:
    match=re.search(r'(?m)^VmHWM:\s+(\d+) kB$',status.read_text())
    if match:peak_rss=max(peak_rss,int(match[1]))
   except FileNotFoundError:pass
 def control(v):
  resources();require(time.monotonic()<deadline,'declared host deadline exceeded');calls.write(json.dumps(v)+'\n');calls.flush();return request(d,v,timeout=min(40,deadline-time.monotonic()))
 def state():return control({'action':'inspect'})['machine']
 def power():return state()['devices']['power']
 def run(c):return control({'action':'run','cycles':c})
 def records():return [v for v in guest_events(d/'uart-0.bin') if v[0]==0x445]
 def boot(cause,epoch):
  begin=state()['cycle']
  while (0x445,cause,epoch,0,0) not in records():
   s=state();require(not s['finished'] and s['cycle']-begin<a.boot_cycles,'real Lean reset report exceeded bound');run(100000)
  return state()
 try:
  proc=subprocess.Popen(list(map(str,cmd)),cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
  while not (d/'session.json').exists():
   require(proc.poll() is None and time.monotonic()<min(deadline,start+60),'source-bound public startup failed');time.sleep(.02)
  initial=control({'action':'inspect'});r['identity']=initial['identity'];require(initial['machine']['cycle']==0,'cold prefix did not begin atcycle0')
  # TCG actually instantiates ACLINT; qtest does not. Run genuine reset-ROM
  # and guest instructions across the first prescaler boundary. The oracle
  # derives ticks from the declared 80ns release, using actual observed time.
  run(8);release=state();require(not power()['domain_reset'] and release['ticks']==0,'cold MTIME/domain release differs')
  require(release['virtual_ns']==80,'cold eight-edge qualification was not exact')
  run(9);before_tick=state();require(before_tick['virtual_ns']<180 and before_tick['ticks']==0,'cold MTIME retained absolute phase')
  run(1);first_tick=state();require(first_tick['ticks']==(first_tick['virtual_ns']-80)//100==1,'cold first MTIME tick differs')
  r['mtime_prefix']={'release':release,'before':before_tick,'after':first_tick}
  while not power()['watchdog_armed']:
   s=state();require(not s['finished'] and s['cycle']<a.boot_cycles,'Lean guest did not arm watchdog');run(10000)
  armed=state();require(records()==[(0x445,1,0,0,0)],'cold Lean report mismatch');r['armed']=armed
  stalled=None
  for _ in range(20):
   before=state();run(1000);after=state()
   # HMP is an architectural observer, not a guest substitute. Stable PC and
   # actual mcycle/minstret data distinguish WFI from an active busy loop.
   def reg(s,n):
    m=re.search(r'(?m)^\s*'+n+r'\s+([0-9a-fA-F]+)',s['cpu_registers']);return int(m[1],16) if m else None
   if reg(before,'pc') is not None and reg(before,'pc')==reg(after,'pc') and before['cpu_registers']==after['cpu_registers']:
    stalled=after;break
   # mcycle correctly changes in WFI, so require stable pc/minstret if exposed.
   if reg(before,'pc') is not None and reg(before,'pc')==reg(after,'pc') and reg(before,'minstret') is not None and reg(before,'minstret')==reg(after,'minstret'):
    stalled=after;break
  require(stalled is not None,'actual guest WFI retirement stall not observed');r['stalled']=stalled
  remaining=power()['watchdog_remaining'];require(remaining>1,'no preterminal state')
  run(remaining-1);pre=power();require(pre['watchdog_remaining']==1 and not pre['domain_reset'],'watchdog expired early')
  run(1);expired=power();require(expired['reset_cause']==4 and expired['reset_remaining']==8 and expired['domain_reset'],'watchdog expiry edge differs')
  run(7);require(power()['reset_remaining']==1,'reset shorter than eight device clocks');run(1);require(not power()['domain_reset'],'reset longer than eight clocks')
  r['watchdog_expiry']=expired;r['watchdog_restart']=boot(4,1)
  control({'action':'inject','kind':'pgood','level':0});run(2);require(power()['reset_cause']==6 and power()['reset_epoch']==2,'power-good loss differs')
  control({'action':'inject','kind':'pgood','level':1});run(8);require(not power()['domain_reset'],'safe power-good release differs');r['power_good_restart']=boot(6,2)
  control({'action':'inject','kind':'brownout','level':1});run(2);require(power()['reset_cause']==5 and power()['reset_epoch']==3,'brownout differs')
  run(10);require(power()['reset_epoch']==3 and power()['reset_remaining']==8,'held brownout repeated loss')
  control({'action':'inject','kind':'brownout','level':0});run(8);require(not power()['domain_reset'],'brownout release differs');r['brownout_restart']=boot(5,3)
  r['records']=records();require(r['records']==[(0x445,1,0,0,0),(0x445,4,1,0,0),(0x445,6,2,0,0),(0x445,5,3,0,0)],'guest reports differ from admitted native relation');r['status']='PASS'
 except BaseException as e:r['error']=str(e);raise
 finally:
  if proc is not None:
   if proc.poll() is None:
    try:control({'action':'destroy'});proc.wait(timeout=10)
    except BaseException:
     if proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
   r['owner_exit_code']=proc.returncode
  r['qemu_peak_rss_kib_sampled']=peak_rss
  calls.close();log.close();r['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'host_seconds':r['host_seconds']}))
if __name__=='__main__':main()
