#!/usr/bin/env python3
"""Actual canonical RTL course publication and independent cold guest load.

Only opaque raw medium backing and raw Console commands enter the machine.
No host journal decoder or target document/checker authority is used.
"""
from __future__ import annotations
import argparse,json,os,re,shutil,signal,subprocess,time
from pathlib import Path
from types import SimpleNamespace
from core0_common import sha256,write_json
from lemmasim_session import request
from lemmasim_course import send
ROOT=Path(__file__).resolve().parents[1]
ROW=re.compile(rb'K1 ((?:[0-9a-f]{16} ){4}[0-9a-f]{16})\n')

def rows(directory):
 p=directory/'uart.bin'
 if not p.exists():return []
 if p.stat().st_size>8*1024*1024:raise RuntimeError('course UART observation exceeded8MiB')
 return [tuple(int(x,16) for x in m[1].split()) for m in ROW.finditer(p.read_bytes())]

class Machine:
 def __init__(self,args,workload,disk,label,fail_flush=None):
  self.directory=args.work_dir/label;self.workload=workload;self.args=args;self.cycles=0;self.started=time.monotonic();self.observations=[]
  self.log=(args.work_dir/(label+'.launch.log')).open('xb')
  role='initializer' if workload=='initializer' else 'notebook'
  build=args.initializer_build if role=='initializer' else args.notebook_build
  source=args.source_root if (args.source_root/'source-inputs.json').is_file() else args.source_root/role
  self.argv=[str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.3.0',
   '--workload',workload,'--mode','laboratory' if fail_flush is not None else 'developer','--session-dir',str(self.directory),
   '--disk',str(disk),'--native-bundle',str(args.native_bundle),'--guest-build',str(build),
   '--guest-source-root',str(source),'--headless','--paused','--quantum','1000000','--timeout','120']
  if fail_flush is not None:self.argv+=['--fail-flush',str(fail_flush)]
  self.process=subprocess.Popen(self.argv,cwd=ROOT,stdout=self.log,stderr=self.log,start_new_session=True)
  until=time.monotonic()+120
  while not (self.directory/'session.json').exists():
   if self.process.poll() is not None:raise RuntimeError('actual course launch failed; see '+str(self.log.name))
   if time.monotonic()>until:raise RuntimeError('course launch publication deadline')
   time.sleep(.05)
 def until(self,predicate,max_cycles):
  while not predicate(rows(self.directory)):
   if self.cycles>=max_cycles:raise RuntimeError('declared course target-cycle boundary not reached')
   if time.monotonic()-self.args.started>getattr(self.args,'host_seconds',4800):raise RuntimeError('declared whole course scenario host ceiling')
   result=request(self.directory,{'action':'run','cycles':1000000},timeout=130)
   self.cycles=result['cycle']
   if self.cycles%2000000==0:self.observations.append(request(self.directory,{'action':'inspect'},timeout=130))
   if result.get('finished'):raise RuntimeError('guest machine ended before requested observation')
  return request(self.directory,{'action':'clock'},timeout=130)
 def command(self,operation,package=None,identity=1,edition=1,crc=0,node=2,transaction=7):
  args=SimpleNamespace(command=operation,session_dir=self.directory,package=package,identity=identity,
   edition=edition,crc=crc,node=node,transaction=transaction,cycle=None)
  return send(args)
 def outcome(self,begin,operation,status,command_cycles):
  if type(command_cycles) is not int or not 0<command_cycles<=100000000 or self.cycles>(1<<64)-1-command_cycles:
   raise ValueError('course command cycle budget must be1..100M without overflow')
  # A command owns a new budget from admission. Reusing an absolute cold-machine
  # deadline gave later commands less/zero work even when each obeyed its bound.
  self.until(lambda r:any(x[0]==0x4b1 and x[1]==operation+(status<<8) for x in r[begin:]),self.cycles+command_cycles)
  return next(x for x in rows(self.directory)[begin:] if x[0]==0x4b1 and x[1]==operation+(status<<8))
 def close(self):
  if self.process.poll() is None:
   try:request(self.directory,{'action':'destroy'},timeout=15)
   except Exception:pass
   try:self.process.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=5)
  self.log.close()

def main():
 p=argparse.ArgumentParser(allow_abbrev=False)
 for name in ('native-bundle','initializer-build','notebook-build','source-root','package','author-package','work-dir'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 for name,value in vars(a).items():setattr(a,name,value.resolve())
 if a.work_dir.exists() or not a.work_dir.is_relative_to(ROOT/'build/courses'):p.error('unused build/courses scenario directory required')
 a.work_dir.mkdir();a.started=time.monotonic();owned=[];report={'status':'FAIL','scope':'actual RTL guest course installer/Store/cold decoder; notebook Ready/UI/evidence binding NOT_RUN',
  'bounds':{'whole_host_seconds':4800,'cold_target_cycles':60000000,'per_install_or_load_command_cycles':100000000,'per_preflight_rejection_cycles':50000000,'maximum_declared_scenario_cycles':670000000,'medium_bytes':268435456},'commands':[]}
 try:
  for name in ('package','author_package'):
   value=getattr(a,name)
   if not value.is_file() or not 128<=value.stat().st_size<=32768:raise RuntimeError('required actual Lean published package missing/oversized')
  disk=a.work_dir/'durable.raw'
  with disk.open('xb') as f:f.truncate(268435456)
  first=Machine(a,'initializer',disk,'install');owned.append(first);report['commands'].append(first.argv)
  ready=first.until(lambda r:any(x[0]==0x4b0 for x in r) and any(x[0]==0x41f for x in r),60000000)
  report['initializer_ready']=ready
  receipts=[]
  for package in (a.package,a.author_package):
   begin=len(rows(first.directory));command=first.command('course-install',package=package,transaction=7+len(receipts))
   outcome=first.outcome(begin,1,0,100000000)
   if outcome[2]<=0:raise RuntimeError('guest Installed lacked a positive durable sequence')
   receipts.append({'artifact_sha256':sha256(package),'command':command,'outcome':outcome,'cycle':first.cycles})
  report['installed']=receipts
  crc=int.from_bytes(a.package.read_bytes()[80:88],'little')
  before=(first.directory/'backing.io').stat().st_size
  begin=len(rows(first.directory));first.command('course-install',package=a.package,transaction=11)
  rejected=first.outcome(begin,1,223,50000000)
  begin=len(rows(first.directory));first.command('course-delete-probe',crc=crc,transaction=12)
  denied=first.outcome(begin,3,223,50000000)
  corrupt=a.work_dir/'corrupt.lcp';raw=bytearray(a.package.read_bytes());raw[-1]^=1;corrupt.write_bytes(raw)
  begin=len(rows(first.directory));first.command('course-install',package=corrupt,transaction=13)
  invalid=first.outcome(begin,1,243,50000000)
  if (first.directory/'backing.io').stat().st_size!=before:raise RuntimeError('overwrite/delete/integrity rejection produced backing I/O')
  report['preflight_rejections']={'overwrite':rejected,'delete':denied,'integrity':invalid,'backing_outcome_bytes_unchanged':before}
  first.close()
  cold=Machine(a,'notebook',disk,'cold');owned.append(cold);report['commands'].append(cold.argv)
  cold.until(lambda r:any(x[0]==0x4b0 for x in r),60000000)
  loads=[]
  for package,edition in ((a.package,1),(a.author_package,2)):
   crc=int.from_bytes(package.read_bytes()[80:88],'little');begin=len(rows(cold.directory))
   admitted=cold.command('course-load',edition=edition,crc=crc,node=2)
   outcome=cold.outcome(begin,2,0,100000000)
   selected=next((x for x in rows(cold.directory)[begin:] if x[0]==0x4b3),None)
   present=next((x for x in rows(cold.directory)[begin:] if x[0]==0x4b2),None)
   if outcome[2]!=0 or selected!=(0x4b3,2,1,crc,edition) or present!=(0x4b2,package.stat().st_size,crc,1,edition):
    raise RuntimeError('actual cold package length/CRC/identity/edition/goal selection differs')
   loads.append({'command':admitted,'outcome':outcome,'selected':selected,'present':present,'cycle':cold.cycles})
  report.update(status='PASS_ACTUAL_COURSE_INSTALL_AND_COLD_SELECTION',cold_loads=loads,
   initializer_machine_identity=json.loads((first.directory/'session.json').read_text())['identity'],
   cold_machine_identity=json.loads((cold.directory/'session.json').read_text())['identity'])
 except BaseException as e:
  report['error']=repr(e)
  # Preserve the actual failed boundary observationally. This does not advance,
  # flush, drain, or classify the failed scenario as success; a later fork can
  # answer a new question without repeating this unchanged cold prefix.
  for machine in owned:
   if machine.process.poll() is None:
    failed={'session':str(machine.directory),'samples':machine.observations}
    try:
     failed['inspect']=request(machine.directory,{'action':'inspect'},timeout=130)
     failed['snapshot']=request(machine.directory,{'action':'snapshot','path':str(machine.directory.parent/(machine.directory.name+'-failed-boundary'))},timeout=130)
    except BaseException as observation_error:failed['observation_error']=repr(observation_error)
    report.setdefault('failed_boundaries',[]).append(failed)
  raise
 finally:
  for machine in owned:machine.close()
  report['wall_seconds']=time.monotonic()-a.started;write_json(a.work_dir/'result.json',report)
 print(report['status'],report['wall_seconds'])
if __name__=='__main__':main()
