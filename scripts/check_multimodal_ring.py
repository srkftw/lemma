#!/usr/bin/env python3
"""Execute maintained kernel/User ring Actions and consequential private negatives.

Finite RAM/MMIO/service fixtures qualify ownership and consumer policy only.
Actual controller DMA, RTL, CPU, PCM export and physical presentation need their
separate executions. No fixture result is promoted to those claims.
"""
import argparse, hashlib, json, os, resource, shutil, subprocess, time
from pathlib import Path
from lean_export_host import environment, policy
ROOT = Path(__file__).resolve().parents[1]

def sha(raw): return hashlib.sha256(raw).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args(); out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    paths=[ROOT/p for p in ['Lemma/Platform/LemmaSim/MultimodalService.lean','Lemma/User/Multimodal.lean',
        'tests/multimodal/OwnedRecordActions.lean.inc','tests/multimodal/OwnedRingActions.lean.inc',
        'tests/multimodal/NotebookAudioActions.lean.inc','tests/multimodal/NotebookRingActions.lean.inc',
        'scripts/lean_export_host.py','scripts/check_multimodal_ring.py']]
    source_inputs={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in paths}
    kernel,user=paths[0].read_text(),paths[1].read_text()
    kernel_fixture=paths[2].read_text().rsplit('def main :=',1)[0]+'\n'+paths[3].read_text()
    user_fixture=paths[4].read_text().rsplit('def main :',1)[0]+'\n'+paths[5].read_text()
    mutations=[
      ('held-read-frame-reuse','kernel','if held &&& 255 = 2 then .done 6 0 else','if held &&& 255 = 1 then .done 6 0 else'),
      ('caller-DMA-address','kernel','ringWrite 104 physical','ringWrite 104 pointer'),
      ('ring-wire-byte-budget','kernel','remaining - count * 8','remaining - count * 2'),
      ('foreign-ring-owner','kernel','if mmDifferent owner descriptor = true then .done 7 0 else','if mmDifferent owner owner = true then .done 7 0 else'),
      ('changed-controller-epoch','kernel','if mmDifferent actual saved = true then .done 4 0 else','if mmDifferent actual actual = true then .done 4 0 else'),
      ('post-copy-expiry-publish','kernel',
        '.bind (ringCurrent descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind (ringWrite 120 (producer + count))',
        '.bind (.done 0 0) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind (ringWrite 120 (producer + count))'),
      ('accepted-claims-consumed','user','audioPut 32 (consumed - consumedBase)','audioPut 32 accepted'),
      ('refill-repeats-old-data','user','let n := producer + i.toUInt64 * 4','let n := i.toUInt64 * 4'),
      ('temporally-unsafe-counter-order','user',
        '.bind (statusOwnedPCM 4 epoch) fun s consumed => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 3 epoch) fun s submitted => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 2 epoch) fun s fetched => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 1 epoch) fun s accepted => if mmFailed s = true then .done s 0 else',
        '.bind (statusOwnedPCM 1 epoch) fun s accepted => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 2 epoch) fun s fetched => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 3 epoch) fun s submitted => if mmFailed s = true then .done s 0 else\n  .bind (statusOwnedPCM 4 epoch) fun s consumed => if mmFailed s = true then .done s 0 else'),
      ('ring-mute-skips-revoke','user',
        'else\n  .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind observeRing',
        'else\n  .bind (.done 0 0) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind observeRing'),
      ('ring-mute-observes-before-revoke','user',
        'else\n  .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind observeRing',
        'else\n  .bind observeRing fun _ _ =>\n  .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else\n  .bind observeRing'),
      ('ring-stale-revokes-successor','user','if mmDifferent current epoch = true then ringReceipt 4 else',
        'if mmDifferent current epoch = true then .bind (invoke 6 8 0 0) fun _ _ => ringReceipt 4 else')]
    report={'status':'FAIL','scope':__doc__,'source_inputs':source_inputs,'cases':[],
      'limits':{'whole_seconds':600,'case_seconds':45,'address_bytes':16<<30,'Lean_heap_MiB':2048,'file_bytes':64<<20},
      'started_unix':time.time(),'host_policy':policy(2)}
    started=time.monotonic()
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(64<<20,64<<20))
    try:
        lake=shutil.which('lake'); lean=shutil.which('lean')
        if not lake or not lean:raise ValueError('Pinned lake/Lean environment required')
        report['tools']={n:{'path':str(Path(p).resolve()),'sha256':sha(Path(p).resolve().read_bytes())} for n,p in [('lake',lake),('lean',lean)]}
        cases=[('actual-kernel','kernel',kernel,True),('actual-user','user',user,True)]
        for name,kind,old,new in mutations:
            body=kernel if kind=='kernel' else user
            if body.count(old)!=1:raise ValueError('Exact unique source-negative missing: '+name)
            cases.append((name,kind,body.replace(old,new,1),False))
        for name,kind,body,positive in cases:
            directory=out/name;directory.mkdir();program=directory/'Ring.lean'
            program.write_text(body+'\n'+(kernel_fixture if kind=='kernel' else user_fixture))
            command=[lake,'env','lean','-j2','-M2048','--run',str(program)]
            began=time.monotonic()
            result=subprocess.run(command,cwd=ROOT,env={**os.environ,**environment(policy(2))},
                capture_output=True,preexec_fn=limits,timeout=min(45,600-(began-started)))
            raw=result.stdout+result.stderr;(directory/'output.log').write_bytes(raw)
            marker=b'OWNED_RING_ACTIONS_PASS' if kind=='kernel' else b'NOTEBOOK_RING_ACTIONS_PASS'
            success=result.returncode==0 and marker in raw
            report['cases'].append({'case':name,'kind':kind,'expected_success':positive,'observed_success':success,
                'exit_code':result.returncode,'seconds':time.monotonic()-began,'command':command,
                'compiled_input_sha256':sha(program.read_bytes()),'output_sha256':sha(raw)})
            if success!=positive or (not positive and b'uncaught exception:' not in raw):
                raise ValueError('Unexpected consequential Action result: '+name)
        if any(sha((ROOT/name).read_bytes())!=value for name,value in source_inputs.items()):raise ValueError('Consumed source changed')
        report['status']='PASS_HOSTED_OWNED_RING_ACTIONS'
    except BaseException as error:report['error']=repr(error)
    finally:
        report['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['status','seconds','error']}))
    return 0 if report['status']=='PASS_HOSTED_OWNED_RING_ACTIONS' else 1
if __name__=='__main__':raise SystemExit(main())
