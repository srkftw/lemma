#!/usr/bin/env python3
"""Audit original course artifacts with a separately identified corrected observer.

No target compilation occurs. Complete original consumed-source roots remain
immutable; the observer receipt identifies the actual current audit helpers.
Original failure reports are retained before the ordinary full audit runs.
"""
import argparse,json,sys,time,shutil
from pathlib import Path
from core0_common import sha256,run_bounded,write_json,Core0Error
from build_kernel import source_inputs

def main():
 p=argparse.ArgumentParser(allow_abbrev=False)
 p.add_argument('--recover-run',type=Path);p.add_argument('--build',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
 a=p.parse_args();root=Path(__file__).resolve().parents[1];b=a.build.resolve();archive=a.source_root.resolve();out=a.output_dir.resolve()
 if out.exists() or not out.is_relative_to(root/'build/courses'):p.error('unused build/courses output required')
 out.mkdir(parents=True);started=time.monotonic();r={'status':'FAIL','scope':'full ordinary artifact audit of unchanged original course objects; current observer identified separately; CPU NOT_RUN'}
 try:
  original=json.loads((archive/'source-inputs.json').read_text());prov=json.loads((b/'provenance.json').read_text())
  if source_inputs(archive)!=original or prov['source_inputs']!=original:raise Core0Error('original input archive incomplete/changed')
  artifacts={n:sha256(b/n) for n in prov['artifacts']}
  if any(artifacts[n]!=h for n,h in prov['artifacts'].items()):raise Core0Error('original artifact changed before audit')
  current=source_inputs(root);observer={n:h for n,h in current.items() if n.startswith('scripts/')}
  for n,h in observer.items():
   t=out/'observer-source'/n;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/n,t)
   if sha256(t)!=h:raise Core0Error('observer changed during archive')
  write_json(out/'observer-inputs.json',observer)
  failure=b/'audit-failure.json'
  if failure.exists():shutil.copyfile(failure,out/'original-audit-failure.json')
  if a.recover_run is None:
   code='import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import audit_kernel; r=audit_kernel.audit(root=Path(sys.argv[4]),source_root=Path(sys.argv[2]),output_dir=Path(sys.argv[3]),timeout_seconds=60); print("ORIGINAL_COURSE_FULL_AUDIT:"+r["status"])'
   command=[sys.executable,'-c',code,str(root/'scripts'),str(archive),str(b),str(root)]
   result=run_bounded(command,cwd=root,timeout_seconds=900)
   (out/'audit.stdout.log').write_bytes(result.stdout);(out/'audit.stderr.log').write_bytes(result.stderr)
   r['command']={'argv':command,'returncode':result.returncode,'wall_seconds':result.elapsed_seconds}
   if result.returncode:raise Core0Error('full ordinary audit failed; actual output retained')
  else:
   previous=a.recover_run.resolve();observed=json.loads((previous/'result.json').read_text())
   cmd=observed.get('command',{})
   if cmd.get('returncode')!=0 or (previous/'audit.stdout.log').read_text()!='ORIGINAL_COURSE_FULL_AUDIT:PASS\n' or (previous/'audit.stderr.log').read_bytes():
    raise Core0Error('retained run did not actually finish the full ordinary audit')
   if cmd.get('argv',[])[-3:]!=[str(archive),str(b),str(root)] or json.loads((previous/'observer-inputs.json').read_text())!=observer:
    raise Core0Error('retained audit belongs to different sources/artifacts/observer')
   for name,h in observer.items():
    if sha256(previous/'observer-source'/name)!=h:raise Core0Error('original observer capture changed:'+name)
   r['retained_full_audit']={'path':str(previous),'result_sha256':sha256(previous/'result.json'),
    'stdout_sha256':sha256(previous/'audit.stdout.log'),'command':cmd,
    'qualification':'original full audit actually PASS; outer wrapper expected an absent source_inputs report field and failed afterwards'}
  audit=json.loads((b/'audit.json').read_text())
  if audit.get('status')!='PASS' or audit['image_sha256']!=artifacts['image.elf'] or audit['source_commit']!=prov['source_commit'] or audit['dirty_paths']!=prov['dirty_paths'] or audit['lean_source_realization']!=prov['lean_source_realization']:raise Core0Error('ordinary audit identity differs')
  if source_inputs(archive)!=original or any(sha256(b/n)!=h for n,h in artifacts.items()):raise Core0Error('original sources/artifacts changed during audit')
  if {n:sha256(root/n) for n in observer}!=observer:raise Core0Error('actual observer changed during audit')
  r.update(status='PASS_ORIGINAL_COURSE_FULL_ARTIFACT_AUDIT',source_root=str(archive),source_commit=prov['source_commit'],original_source_count=len(original),
   original_inventory_sha256=sha256(archive/'source-inputs.json'),image_sha256=sha256(b/'image.elf'),audit_sha256=sha256(b/'audit.json'),observer_inputs=observer)
 except BaseException as e:r['error']=repr(e);raise
 finally:
  r['wall_seconds']=time.monotonic()-started;write_json(out/'result.json',r)
 print(r['status'],r['wall_seconds'])
if __name__=='__main__':main()
