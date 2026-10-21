#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Finite OpticalFrame/1 C/RTL relation; no SoC/guest/runtime admission claim."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
WHOLE=300
COMMAND=120
RSS=3*1024**3//2
ADDRESS_SPACE=16*1024**3
OUTPUT=512*1024**2
FLOOR=8*1024**3
LAUNCH=12*1024**3
COMPILED=('sim/host/lemma_optical.c','sim/host/lemma_optical.h',
          'sim/rtl/lemma_optical.sv','sim/rtl/tests/optical_tb.cpp')
BINDINGS=('sim/rtl/lemma_soc.sv','sim/rtl/host/machine_runtime.cpp',
 'sim/rtl/host/machine_runtime.h','scripts/silicon_compute.py','scripts/silicon_profile.py',
 'sim/profiles/lemma-silicon-dev-0.17.0.json','Lemma/Platform/LemmaSim/Descriptor.lean',
 'Lemma/Platform/LemmaSim/DescriptorDTB.lean','Lemma/Platform/LemmaSim/MachineServices.lean',
 'Lemma/Platform/RiscV/ExecutionPrimitives.lean','Lemma/Machine/Primitives.lean',
 'docs/contracts/009-optical-frame-v1.html')
INPUTS=COMPILED+BINDINGS+('scripts/check_optical_controller.py','tooling/silicon/sim.nix','flake.lock')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def available():
 for line in Path('/proc/meminfo').read_text().splitlines():
  if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
 raise RuntimeError('host memory evidence unavailable')
def inventory():return {name:digest(ROOT/name) for name in INPUTS}
def output_bytes(out):
 total=0
 for path in out.rglob('*'):
  try:
   if path.is_symlink():raise RuntimeError('unexpected output symlink')
   if path.is_file():total+=path.stat().st_size
  except FileNotFoundError:pass  # Owned make temporaries may be renamed.
 return total

def processes():
 result={}
 for path in Path('/proc').iterdir():
  if not path.name.isdecimal():continue
  try:
   raw=(path/'stat').read_text();fields=raw[raw.rfind(')')+2:].split()
   result[int(path.name)]={'ppid':int(fields[1]),'pgrp':int(fields[2]),'sid':int(fields[3]),
    'start':int(fields[19]),'rss':int(fields[21])*os.sysconf('SC_PAGE_SIZE'),'state':fields[0]}
  except InterruptedError:raise
  except (OSError,ValueError,IndexError):pass
 return result

def thread_ids(pid):
 try:return {int(path.name) for path in (Path('/proc')/str(pid)/'task').iterdir()}
 except InterruptedError:raise
 except OSError:return set()

class Campaign:
 def __init__(self,out,before,started):
  # The dedicated controller is a subreaper, including a descendant whose
  # parent exits between samples or which creates its own session/group.
  if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0):
   raise OSError(ctypes.get_errno(),'Linux child subreaper unavailable')
  self.out=out;self.before=before;self.started=started;self.deadline=started+WHOLE
  self.seen={};self.groups={};self.peak=0;self.minimum=available();self.commands=[];self.interruption=0
  self.handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
  for sig in self.handlers:signal.signal(sig,self.interrupted)
 def interrupted(self,signum,frame):
  self.interruption=signum
  raise InterruptedError('optical controller interrupted: '+str(signum))
 def close(self):
  for sig,handler in self.handlers.items():signal.signal(sig,handler)
 def discover(self):
  rows=processes();owned={pid for pid,start in self.seen.items() if pid in rows and rows[pid]['start']==start}
  changed=True
  while changed:
   changed=False;parents={os.getpid()}|thread_ids(os.getpid())|owned
   for pid in owned:parents.update(thread_ids(pid))
   for pid,row in rows.items():
    group=self.groups.get(row['sid'])
    in_group=group is not None and row['start']>=group[0]
    # The admitted session retains its number while any member survives.
    if in_group and group[1] is not None and row['sid'] in rows and rows[row['sid']]['start']!=group[1]:in_group=False
    if pid!=os.getpid() and pid not in owned and (row['ppid'] in parents or in_group):
     self.seen[pid]=row['start'];owned.add(pid);changed=True
  live={pid:rows[pid] for pid in owned if rows[pid]['state']!='Z'}
  monitor=rows.get(os.getpid(),{}).get('rss',0)
  self.peak=max(self.peak,monitor+sum(row['rss'] for row in live.values()))
  return live
 def check(self):
  if self.interruption:raise InterruptedError('optical controller interrupted: '+str(self.interruption))
  live=self.discover();free=available();self.minimum=min(self.minimum,free)
  if time.monotonic()>self.deadline:raise TimeoutError('original300s whole deadline')
  if processes().get(os.getpid(),{}).get('rss',0)+sum(row['rss'] for row in live.values())>RSS:raise MemoryError('sampled aggregate1.5GiB RSS bound')
  if free<FLOOR:raise MemoryError('continuing8GiB host reserve')
  if output_bytes(self.out)>OUTPUT:raise RuntimeError('original512MiB output bound')
  return live
 def cleanup(self):
  previous={sig:signal.getsignal(sig) for sig in self.handlers}
  for sig in previous:signal.signal(sig,signal.SIG_IGN)
  try:self._cleanup()
  finally:
   for sig,handler in previous.items():signal.signal(sig,handler)
 def _cleanup(self):
  # Repeat discovery after each retirement: subreaped grandchildren may only
  # become direct children after their observed parent dies. Signal exact
  # PID/start identities, including members with a changed process group.
  until=time.monotonic()+5
  while time.monotonic()<until:
   live=self.discover()
   for pid,row in live.items():
    current=processes().get(pid)
    if current is not None and current['start']==row['start']:
     try:os.kill(pid,signal.SIGKILL)
     except ProcessLookupError:pass
   for pid,start in self.seen.items():
    current=processes().get(pid)
    if current is not None and current['start']==start and current['state']=='Z':
     try:os.waitpid(pid,os.WNOHANG)
     except ChildProcessError:pass
   if not self.discover():return
   time.sleep(.02)
  raise RuntimeError('observed owner remains after cleanup')
 def run(self,cmd,label):
  self.check();row={'argv':[str(v) for v in cmd],'log':label+'.log','status':'RUNNING'};self.commands.append(row)
  start=time.monotonic();limit=min(self.deadline,start+COMMAND)
  def limits():resource.setrlimit(resource.RLIMIT_AS,(ADDRESS_SPACE,ADDRESS_SPACE))
  with (self.out/row['log']).open('wb') as log:
   before_tick=int(time.clock_gettime(time.CLOCK_BOOTTIME)*os.sysconf('SC_CLK_TCK'))
   child=subprocess.Popen(row['argv'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
    start_new_session=True,preexec_fn=limits)
   self.groups[child.pid]=(before_tick,None)
   rows=processes()
   if child.pid in rows:self.seen[child.pid]=rows[child.pid]['start'];self.groups[child.pid]=(before_tick,rows[child.pid]['start'])
   row['pid']=child.pid;row['start_tick']=self.seen.get(child.pid);row['session_admission_tick']=before_tick
   try:
    while child.poll() is None:
     self.check()
     if time.monotonic()>limit:raise TimeoutError('original120s command deadline')
     time.sleep(.025)
    row['exit_code']=child.wait()
    self.check()
    if row['exit_code']!=0:raise RuntimeError('actual command failed: '+label)
    row['status']='PASS'
   finally:
    self.cleanup()
    if child.poll() is None:child.kill()
    child.wait(timeout=5)
    row['elapsed_seconds']=time.monotonic()-start
    if time.monotonic()>limit:
     row['status']='FAIL'
     raise TimeoutError('original120s command deadline including cleanup')
    if row['status']=='RUNNING':row['status']='FAIL'
 def tool_run(self,cmd,label):
  # Use the same normal pinned shell as check_silicon.py. The Nix launcher,
  # shell, tool inventory and compiler all remain children of this monitor;
  # no unobserved outer environment process precedes the whole clock.
  launcher=shutil.which('nix-shell')
  if launcher is None:raise RuntimeError('normal pinned nix-shell unavailable')
  query='\n'.join([
   'import hashlib,json,os,shutil,subprocess',
   'from pathlib import Path',
   'tools={}',
   "for name in ('cc','c++','make','verilator'):",
   ' found=shutil.which(name)',
   " if not found:raise RuntimeError('Missing pinned host tool '+name)",
   ' path=Path(found).resolve()',
   " if not str(path).startswith('/nix/store/'):raise RuntimeError('Unpinned host tool '+name)",
   " tools[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'version':subprocess.check_output([found,'--version'],text=True).splitlines()[0]}",
   "path=Path(tools['verilator']['path']).with_name('verilator_bin')",
   "tools['verilator_bin']={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'version':subprocess.check_output([str(path),'--version'],text=True).splitlines()[0]}",
   f'target=Path({str(self.out/"tools.json")!r})',
   "if target.exists() and json.loads(target.read_text())!=tools:raise RuntimeError('Pinned host tools changed')",
   "target.write_text(json.dumps(tools,indent=2)+'\\n')",
   f'argv={[str(v) for v in cmd]!r}',
   'os.execvp(argv[0],argv)'])
  self.run([launcher,str(ROOT/'tooling/silicon/sim.nix'),'--run',shlex.join(['python3','-c',query])],label)
  self.commands[-1]['effective_argv']=[str(v) for v in cmd]

def main():
 started=time.monotonic()
 parser=argparse.ArgumentParser();parser.add_argument('--work-dir',type=Path,required=True);args=parser.parse_args()
 out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 before=inventory();fresh=available()
 plan={'schema':'lemma-optical-controller-plan/1','compiled_sources':list(COMPILED),
  'sealed_not_executed_bindings':list(BINDINGS),'inputs':before,'whole_seconds':WHOLE,'command_seconds':COMMAND,
  'aggregate_rss_bytes':RSS,'address_space_bytes':ADDRESS_SPACE,'output_bytes':OUTPUT,
  'launch_available_bytes':LAUNCH,'continuing_available_bytes':FLOOR,'actual_fresh_available_bytes':fresh,
  'scope':'standalone C/RTL raw source, SG, timing and lifetime relation; no SoC reset-fabric, kernel, guest, native/Wasm admission, physical or arbitrary continuation claim'}
 (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 report={'schema':'lemma-optical-controller-result/1','status':'NOT_ADMITTED','commands':[]}
 if fresh<LAUNCH:
  report.update(reason='fresh12GiB joint memory proof refused before Popen',elapsed_seconds=time.monotonic()-started)
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');return 2
 campaign=Campaign(out,before,started);report.update(status='FAIL',commands=campaign.commands)
 try:
  for name in INPUTS:
   target=out/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/name).read_bytes())
   if digest(target)!=before[name]:raise RuntimeError('source changed during archival: '+name)
   campaign.check()
  campaign.tool_run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'sim/host'),
   '-c',ROOT/COMPILED[0],'-o',out/'model.o'],'c-model')
  campaign.tool_run(['verilator','--cc','--exe','--build','-j','1','-Wno-fatal','-fno-dfg',
   '--top-module','lemma_optical','--Mdir',out/'obj','-CFLAGS','-std=c++17 -I'+str(ROOT/'sim/host'),
   '-LDFLAGS',str(out/'model.o'),ROOT/COMPILED[2],ROOT/COMPILED[3]],'rtl-compile')
  campaign.run([out/'obj/Vlemma_optical'],'actual-relation')
  observation=(out/'actual-relation.log').read_text().strip()
  import re
  if not re.fullmatch(r'PASS optical-frame/1 cases=[1-9][0-9]* checks=[1-9][0-9]*',observation):raise RuntimeError('missing actual finite relation protocol')
  if before!=inventory():raise RuntimeError('consumed or sealed binding source changed')
  campaign.check();report.update(status='PASS_STANDALONE_OPTICAL1_RELATION',observation=observation)
 except BaseException as error:report['error']=type(error).__name__+': '+str(error)
 finally:
  try:campaign.cleanup()
  except BaseException as error:report.update(status='FAIL',cleanup_error=str(error))
  report.update(elapsed_seconds=time.monotonic()-campaign.started,peak_sampled_owned_rss_bytes=campaign.peak,
   minimum_host_available_bytes=campaign.minimum,observed_owners=[{'pid':pid,'start_tick':start} for pid,start in sorted(campaign.seen.items())],
   remaining_observed_owners=list(campaign.discover()),source_unchanged=before==inventory(),output_bytes=output_bytes(out),
   raw_logs={path.name:digest(path) for path in out.glob('*.log')})
  if (out/'tools.json').is_file():report['tools']=json.loads((out/'tools.json').read_text())
  if (report['elapsed_seconds']>WHOLE or report['output_bytes']>OUTPUT or report['remaining_observed_owners'] or not report['source_unchanged']):report['status']='FAIL'
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  # The result itself and final serialization remain within the original
  # whole/output limits. A terminal failure must also have a failing exit.
  if time.monotonic()>campaign.deadline or output_bytes(out)>OUTPUT:
   report['status']='FAIL';report['final_seal_error']='whole/output bound during result publication'
   (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  campaign.close()
 print(json.dumps(report,indent=2));return 0 if report['status']=='PASS_STANDALONE_OPTICAL1_RELATION' else 1

if __name__=='__main__':raise SystemExit(main())
