#!/usr/bin/env python3
"""Independent cold guest load of previously acknowledged opaque course bytes.

The prior writer and fresh reader keep separate source identities. The original
failed scenario remains failed. Copying raw backing is not journal decoding,
initializing guest memory, or restoring a machine checkpoint.
"""
from __future__ import annotations
import argparse,json,resource,shutil,subprocess,time
from pathlib import Path
from check_course_guest import Machine,ROOT,rows
from core0_common import sha256,write_json
from lemmasim_session import request

def host_inputs():
 # Conservative complete project host-code inventory. Native runtime/tool
 # dependencies retain their separately validated bundle authority; guest
 # lowering retains its complete original source archive. No relocation of
 # the live launcher or substitution of a different ROOT is implied here.
 files=[]
 for directory in (ROOT/'scripts',ROOT/'conformance/lemmasim'):
  files.extend(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and
   (p.suffix in ('.py','.sh','.c','.cpp','.h','.lean','.sv') or p.name=='lemmasim'))
 if len(files)<200:raise RuntimeError('unexpectedly empty actual host-source inventory')
 return {str(p.relative_to(ROOT)):sha256(p) for p in sorted(files)}

def admitted_writer(receipt,packages,medium):
 if receipt.get('status')!='FAIL' or len(receipt.get('installed',[]))!=2 or 'preflight_rejections' not in receipt:
  raise ValueError('requires retained failed scenario with two actual Installed receipts and preflight observations')
 prior=[]
 for item,package,edition in zip(receipt['installed'],packages,(1,2)):
  raw=package.read_bytes();crc=int.from_bytes(raw[80:88],'little')
  expected=[0x4b1,1,edition,1+(edition<<16),crc]
  if item.get('artifact_sha256')!=sha256(package) or item.get('outcome')!=expected or item.get('command',{}).get('edition')!=edition:
   raise ValueError('acknowledged writer artifact/sequence/edition differs')
  prior.append({'artifact_sha256':item['artifact_sha256'],'outcome':item['outcome'],'cycle':item['cycle']})
 argv=receipt.get('commands',[[]])[0]
 if argv.count('--disk')!=1 or Path(argv[argv.index('--disk')+1]).resolve()!=medium:
  raise ValueError('opaque backing path differs from acknowledged writer')
 return prior

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
 for name in ('native-bundle','notebook-build','source-root','package','author-package','writer-result','medium','work-dir'):
  p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 for name,value in vars(a).items():setattr(a,name,value.resolve())
 if a.work_dir.exists() or not a.work_dir.is_relative_to(ROOT/'build/courses'):p.error('unused build/courses directory required')
 if not a.medium.is_file() or a.medium.stat().st_size!=268435456:p.error('actual canonical backing missing/wrong size')
 a.work_dir.mkdir();a.started=time.monotonic();a.initializer_build=a.notebook_build;a.host_seconds=1800;owned=[]
 report={'status':'FAIL','scope':'actual independent RTL cold decode/selection from acknowledged bytes; new writer, notebook Ready/UI and evidence binding NOT_RUN',
 'bounds':{'whole_host_seconds':1800,'cold_target_cycles':60000000,'per_load_command_cycles':100000000,'maximum_declared_cycles':260000000},'commands':[]}
 try:
  before=host_inputs();host_archive=a.work_dir/'host-source-root'
  for name,digest in before.items():
   target=host_archive/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
   if sha256(target)!=digest:raise RuntimeError('host source changed during original capture:'+name)
  write_json(host_archive/'source-inputs.json',before)
  report['actual_host_source']={'scope':'full conservative project host-code corpus; imported paths held stable throughout actual actor',
   'count':len(before),'root':str(host_archive),'inventory_sha256':sha256(host_archive/'source-inputs.json'),
   'unchanged_after_actor':False}
  observer_names=('check_course_cold.py','check_course_guest.py','lemmasim','lemmasim_session.py',
   'lemmasim_course.py','course_deployment.py','silicon_guest.py','silicon_guest_bundle.py','silicon_profile.py','core0_common.py')
  report['selected_observer_inputs']={name:sha256(ROOT/'scripts'/name) for name in observer_names}
  archive=a.work_dir/'selected-observer-source';archive.mkdir()
  for name in observer_names:
   shutil.copyfile(ROOT/'scripts'/name,archive/name)
   if sha256(archive/name)!=report['selected_observer_inputs'][name]:raise RuntimeError('observer source changed during capture')
  packages=(a.package,a.author_package);writer=json.loads(a.writer_result.read_text())
  report['original_writer']={'result':str(a.writer_result),'sha256':sha256(a.writer_result),'status':writer['status'],
   'installed':admitted_writer(writer,packages,a.medium),'commands':writer['commands'],
   'original_failed_cold_status': [list(row) for row in rows(a.writer_result.parent/'cold') if row[0]==0x4b1]}
  report['original_writer']['machine_identity']=json.loads((a.writer_result.parent/'install/session.json').read_text())['identity']
  # An ordinary independent cold machine receives privately copied opaque raw
  # bytes, never a checkpoint or host-interpreted document/package state.
  disk=a.work_dir/'durable.raw'
  subprocess.run(['cp','--reflink=auto','--sparse=always','--',str(a.medium),str(disk)],check=True)
  report['opaque_backing']={'original':str(a.medium),'private':str(disk),'sha256':sha256(disk),'bytes':disk.stat().st_size}
  machine=Machine(a,'notebook',disk,'cold');owned.append(machine);report['commands'].append(machine.argv)
  machine.until(lambda r:any(row[0]==0x4b0 for row in r),60000000)
  loads=[]
  for package,edition in zip(packages,(1,2)):
   crc=int.from_bytes(package.read_bytes()[80:88],'little');begin=len(rows(machine.directory));admission=machine.cycles
   command=machine.command('course-load',edition=edition,crc=crc,node=2)
   outcome=machine.outcome(begin,2,0,100000000)
   observed=rows(machine.directory)[begin:]
   present=next((row for row in observed if row[0]==0x4b2),None)
   selected=next((row for row in observed if row[0]==0x4b3),None)
   if outcome[2]!=0 or present!=(0x4b2,package.stat().st_size,crc,1,edition) or selected!=(0x4b3,2,1,crc,edition):
    raise RuntimeError('cold guest package length/CRC/identity/edition/reference differs')
   loads.append({'admission_cycle':admission,'completion_cycle':machine.cycles,'command':command,'outcome':outcome,'present':present,'selected':selected})
  report.update(status='PASS_ACTUAL_COLD_COURSE_SELECTION_AFTER_GUEST_MOUNT_WAIT',cold_loads=loads,
   cold_machine_identity=json.loads((machine.directory/'session.json').read_text())['identity'],
   final_inspect=request(machine.directory,{'action':'inspect'},timeout=130))
 except BaseException as error:
  report['error']=repr(error)
  for machine in owned:
   if machine.process.poll() is None:
    try:
     report['failed_boundary']={'inspect':request(machine.directory,{'action':'inspect'},timeout=130),
      'snapshot':request(machine.directory,{'action':'snapshot','path':str(a.work_dir/'failed-boundary')},timeout=130)}
    except BaseException as observer:report['observation_error']=repr(observer)
  raise
 finally:
  for machine in owned:machine.close()
  if 'actual_host_source' in report:
   unchanged=host_inputs()==before
   report['actual_host_source']['unchanged_after_actor']=unchanged
   if not unchanged:
    report['status']='FAIL'
    report['host_source_error']='actual host-code corpus changed during actor'
  report['wall_seconds']=time.monotonic()-a.started
  report['child_peak_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
  write_json(a.work_dir/'result.json',report)
 if report['status']=='FAIL':raise RuntimeError(report.get('host_source_error','actual cold course scenario failed'))
 print(report['status'],report['wall_seconds'])
if __name__=='__main__':main()
