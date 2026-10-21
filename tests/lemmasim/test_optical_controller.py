# SPDX-License-Identifier: Apache-2.0
"""Actual Linux ownership regressions for the standalone Optical checker."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
WORKER=r'''
import json,os,signal,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import check_optical_controller as check
out=Path(sys.argv[2]);mode=sys.argv[3]
check.COMMAND=.3 if mode=='deadline' else 3
campaign=check.Campaign(out,{},time.monotonic())
if mode in ('group','detached'):
 original_popen=check.subprocess.Popen
 def exited_leader(*args,**kwargs):
  child=original_popen(*args,**kwargs)
  child.wait(timeout=2)  # Reap it before Campaign's first discovery sample.
  return child
 check.subprocess.Popen=exited_leader
source=r"""
import os,signal,sys,time
from pathlib import Path
if os.fork():
 if sys.argv[2]=='interrupt':time.sleep(30)
 os._exit(0)
if sys.argv[2] in ('detached','interrupt'):os.setsid()
else:os.setpgid(0,0)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(30)
"""
error=None
try:
 if mode in ('group','detached'):
  campaign.run([sys.executable,'-c',source,str(out/'descendant.pid'),mode],'fork')
 elif mode=='deadline':
  campaign.run([sys.executable,'-c','import time;time.sleep(30)'],'deadline')
 else:
  (out/'monitor.pid').write_text(str(os.getpid()))
  campaign.run([sys.executable,'-c',source,str(out/'descendant.pid'),'interrupt'],'interrupt')
except BaseException as exc:error=type(exc).__name__
finally:
 campaign.cleanup();remaining=campaign.discover();campaign.close()
 (out/'worker.json').write_text(json.dumps({'error':error,'remaining':list(remaining),'seen':campaign.seen,'peak':campaign.peak,'commands':campaign.commands}))
'''


class OpticalOwnershipTests(unittest.TestCase):
 def run_worker(self,mode):
  with tempfile.TemporaryDirectory() as directory:
   out=Path(directory)
   child=subprocess.Popen([sys.executable,'-c',WORKER,str(ROOT),str(out),mode],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   try:
    if mode=='interrupt':
     until=time.monotonic()+3
     while not (out/'descendant.pid').exists():
      if child.poll() is not None or time.monotonic()>until:self.fail('actual detached child did not start')
      time.sleep(.01)
     os.kill(child.pid,signal.SIGTERM)
    stdout,stderr=child.communicate(timeout=8)
    self.assertEqual(child.returncode,0,(stdout,stderr))
    result=json.loads((out/'worker.json').read_text())
    self.assertFalse(result['remaining'])
    self.assertGreater(result['peak'],0)
    if (out/'descendant.pid').exists():
     pid=int((out/'descendant.pid').read_text())
     self.assertFalse(Path('/proc',str(pid)).exists(),'owned detached child was not reaped')
    return result
   finally:
    if child.poll() is None:child.kill();child.wait()

 def test_fast_leader_exit_with_changed_process_group(self):
  result=self.run_worker('group')
  self.assertIsNone(result['error'])
  self.assertGreaterEqual(len(result['seen']),1)
  self.assertIsNone(result['commands'][0]['start_tick'])

 def test_fast_leader_exit_with_new_session(self):
  result=self.run_worker('detached')
  self.assertIsNone(result['error'])
  self.assertGreaterEqual(len(result['seen']),1)
  self.assertIsNone(result['commands'][0]['start_tick'])

 def test_monitor_signal_retires_term_ignoring_detached_child(self):
  result=self.run_worker('interrupt')
  self.assertEqual(result['error'],'InterruptedError')

 def test_command_deadline_fails_and_reaps(self):
  result=self.run_worker('deadline')
  self.assertEqual(result['error'],'TimeoutError')
  self.assertEqual(result['commands'][0]['status'],'FAIL')


if __name__=='__main__':unittest.main()
