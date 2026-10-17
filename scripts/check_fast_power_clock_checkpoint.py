#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Selected real-guest reset-phase suffix. Does not close QEMU cache-state omission."""
import argparse,json,os,signal,subprocess,sys,time
from pathlib import Path
from lemmasim_session import request,digest
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args();out=a.work_dir.resolve();out.mkdir();d=out/'session';start=time.monotonic();deadline=start+90;r={'status':'FAIL','scope':__doc__,'observer_sha256':digest(__file__)};owner=None
 log=(out/'launch.log').open('xb');commands=(out/'commands.jsonl').open('x')
 def call(v):
  if time.monotonic()>deadline:raise TimeoutError('declared90s checkpoint bound')
  commands.write(json.dumps(v)+'\n');commands.flush();return request(d,v,timeout=min(30,deadline-time.monotonic()))
 def state():return call({'action':'inspect'})['machine']
 def run(c):return call({'action':'run','cycles':c})
 def authoritative(s):return {k:s[k] for k in ('cycle','ticks','virtual_ns','cpu_registers','devices')}
 try:
  cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','qemu','--profile','lemma-silicon-dev/0.4.0','--workload','power','--mode','laboratory','--headless','--paused','--session-dir',str(d),'--timeout','30']
  owner=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
  while not (d/'session.json').exists():
   if owner.poll() is not None:raise RuntimeError('source-bound owner startup failed')
   if time.monotonic()>start+45:raise TimeoutError('startup45s bound')
   time.sleep(.02)
  initial=call({'action':'inspect'});r['identity']=initial['identity']
  if initial['machine']['cycle']!=0:raise ValueError('not cold cycle0')
  run(100);call({'action':'warm-reset'});run(8)
  released=state();origin=released['virtual_ns']
  if released['ticks']!=0 or released['devices']['power']['domain_reset']:raise ValueError('actual warm-reset release differs')
  run(7);before=state()
  if not 0<before['virtual_ns']-origin<100 or before['ticks']!=0:raise ValueError('not fractional pre-first-tick state')
  t=time.monotonic();call({'action':'snapshot','path':str(out/'fractional')});r['snapshot_seconds']=time.monotonic()-t
  if authoritative(state())!=authoritative(before):raise ValueError('snapshot changed authoritative observations')
  run(5);end=state()
  if end['ticks']!=(end['virtual_ns']-origin)//100:raise ValueError('uninterrupted next tick differs')
  t=time.monotonic();call({'action':'restore','path':str(out/'fractional')});r['restore_seconds']=time.monotonic()-t
  if authoritative(state())!=authoritative(before):raise ValueError('restored fractional state differs')
  run(5);restored=state()
  if authoritative(restored)!=authoritative(end):raise ValueError('selected genuine-instruction suffix differs')
  r.update(status='PASS',release=released,before=before,after=end,suffix_cycles=5,snapshot_bytes=(out/'fractional/machine.chk').stat().st_size)
 except BaseException as e:r['error']=str(e);raise
 finally:
  if owner is not None:
   if owner.poll() is None:
    try:call({'action':'destroy'});owner.wait(timeout=5)
    except BaseException:
     if owner.poll() is None:os.killpg(owner.pid,signal.SIGTERM)
     try:owner.wait(timeout=5)
     except subprocess.TimeoutExpired:os.killpg(owner.pid,signal.SIGKILL);owner.wait(timeout=5)
   r['owner_exit_code']=owner.returncode
  commands.close();log.close();r['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'host_seconds':r['host_seconds']}))
if __name__=='__main__':main()
