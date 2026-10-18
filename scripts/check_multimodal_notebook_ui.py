#!/usr/bin/env python3
"""Host-only real Lean Action checks of Notebook21 UI queue/control behavior.

The exact maintained source prefix is appended with a host-only interpreter
fixture so private Actions can be evaluated without exposing target test APIs.
Quarantined source-negative variants must fail. This is neither guest execution
nor a paper-controller/presentation or timing qualification.
"""
import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(raw):return hashlib.sha256(raw).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'Lemma/Applications/Notebook.lean';fixture=ROOT/'tests/multimodal/NotebookUIActions.lean.inc'
    inputs={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in (source,fixture,Path(__file__).resolve())}
    text=source.read_text();test=fixture.read_text();report={'status':'FAIL','scope':__doc__,'source_inputs':inputs,'cases':[]};start=time.monotonic()
    enqueue='  .boundedFoldU64 20 multimodalBarTile 20 0 width 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else\n'
    stop='if different captureActive 0 = true then multimodalSafety 0 else'
    guard='if width < 1024 then .done 16 0 else'
    cases=[('actual-maintained',text,True),
           ('quarantined-missing-dirty-enqueue',text.replace(enqueue,'',1),False),
           ('quarantined-stop-waits-behind-busy',text.replace(stop,'if different captureActive 0 = true then .done 0 0 else',1),False),
           ('quarantined-inactive-start-bypass',text.replace('if safetyX < 544 then Lemma.User.Multimodal.active','if safetyX < 544 then .done 0 1',1),False),
           ('quarantined-missing-width-guard',text.replace(guard,'if width < 1 then .done 16 0 else',1),False)]
    try:
        lake=Path(shutil.which('lake') or '');lean=Path(shutil.which('lean') or '')
        if not lake.is_file() or not lean.is_file():raise ValueError('pinned environment with actual Lean/lake is required')
        report['tools']={name:{'path':str(p.resolve()),'sha256':sha(p.resolve().read_bytes())} for name,p in [('lake',lake),('lean',lean)]}
        report['Lean_version']=subprocess.run([str(lean),'--version'],check=True,capture_output=True,text=True,timeout=10).stdout.strip()
        for label,body,positive in cases:
            if not positive and body==text:raise ValueError('source-negative mutation absent '+label)
            directory=out/label;directory.mkdir();program=directory/'NotebookUI.lean';program.write_text(body+test)
            command=[str(lake),'env','lean','--run',str(program)]
            began=time.monotonic();result=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=180)
            output=result.stdout+result.stderr;(directory/'output.log').write_bytes(output)
            observed=result.returncode==0 and b'NOTEBOOK21_UI_ACTIONS_PASS' in output
            report['cases'].append({'case':label,'expected_success':positive,'observed_success':observed,'exit_code':result.returncode,'seconds':time.monotonic()-began,'source_prefix_sha256':sha(body.encode()),'compiled_input_sha256':sha(program.read_bytes()),'command':command,'raw_output_sha256':sha(output)})
            if observed!=positive:raise ValueError('unexpected actual Lean Action outcome '+label)
            if not positive and b'error:' in output and b'uncaught exception:' not in output:raise ValueError('source-negative rejected by compile error instead of consequential Action assertion '+label)
        if any(sha((ROOT/name).read_bytes())!=digest for name,digest in inputs.items()):raise ValueError('consumed source changed during execution')
        report['status']='PASS_HOSTED_LEAN_ACTIONS'
    except BaseException as error:report['error']=repr(error)
    finally:
        report['seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(report['cases']),'seconds':report['seconds'],'error':report.get('error')}))
    return 0 if report['status']=='PASS_HOSTED_LEAN_ACTIONS' else 1
if __name__=='__main__':raise SystemExit(main())
