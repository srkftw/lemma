#!/usr/bin/env python3
"""Run the actual Lean owned record/PCM Actions and consequential source negatives.

These are hosted kernel ownership/policy checks, not controller, guest, timing,
checkpoint, audible presentation or physical qualification. Production code is
appended verbatim with a finite RAM/MMIO fixture; negative variants are private.
"""
import argparse, hashlib, json, shutil, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT/'Lemma/Platform/LemmaSim/MultimodalService.lean',
             ROOT/'tests/multimodal/OwnedRecordActions.lean.inc', Path(__file__).resolve()]
    inputs = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}
    body, fixture = paths[0].read_text(), paths[1].read_text()
    mutations = [
        ('copy-failure-leaks-owner',
         'if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else\n  .bind (get (row stream + 32))',
         'if mmFailed s = true then .done s 0 else\n  .bind (get (row stream + 32))'),
        ('application-DMA-address', 'write stream 160 destination', 'write stream 160 pointer'),
        ('CPU-take-bypasses-pending', 'if active = stream + 1 then .done 6 0 else',
         'if active = stream + 2 then .done 6 0 else'),
        ('changed-record-sequence', 'if mmDifferent (sequence) (expectedSequence) = true then', 'if mmDifferent (sequence) (sequence) = true then'),
        ('PCM-charges-wire-bytes', 'remaining - accepted * 8', 'remaining - accepted * 2'),
        ('completed-DMA-hides-controller-gap',
         'if mmDifferent (fault) (0) = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done (faultStatus fault) 0 else',
         'if mmDifferent (fault) (fault) = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done (faultStatus fault) 0 else'),
        ('retired-DMA-does-not-wait',
         'if status = 1 then .done 6 0 else\n    if (if status = 2 then true else if status = 3 then true else false) = false then fatal else releaseRecord',
         'if status = 1 then releaseRecord else\n    if (if status = 2 then true else if status = 3 then true else false) = false then fatal else releaseRecord')]
    report = {'status': 'FAIL', 'scope': __doc__, 'source_inputs': inputs, 'cases': [],
              'limits': {'whole_seconds': 180, 'case_seconds': 30}, 'started_unix': time.time()}
    start = time.monotonic()
    try:
        lake, lean = Path(shutil.which('lake') or ''), Path(shutil.which('lean') or '')
        if not lake.is_file() or not lean.is_file():
            raise ValueError('Pinned Lean/lake environment required')
        report['tools'] = {name: {'path': str(p.resolve()), 'sha256': digest(p.resolve().read_bytes())}
                           for name, p in [('lake', lake), ('lean', lean)]}
        cases = [('actual-maintained', body, True)]
        for name, old, new in mutations:
            if body.count(old) != 1:
                raise ValueError('Exact unique source-negative anchor missing: ' + name)
            cases.append((name, body.replace(old, new, 1), False))
        for name, source, positive in cases:
            directory = out/name
            directory.mkdir()
            program = directory/'OwnedIO.lean'
            program.write_text(source+'\n'+fixture)
            command = [str(lake), 'env', 'lean', '--run', str(program)]
            began = time.monotonic()
            result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                    timeout=min(30, 180-(began-start)))
            raw = result.stdout+result.stderr
            (directory/'output.log').write_bytes(raw)
            success = result.returncode == 0 and b'OWNED_RECORD_PCM_ACTIONS_PASS' in raw
            report['cases'].append({'case': name, 'expected_success': positive, 'observed_success': success,
                                    'exit_code': result.returncode, 'seconds': time.monotonic()-began,
                                    'compiled_input_sha256': digest(program.read_bytes()),
                                    'output_sha256': digest(raw), 'command': command})
            if success != positive or (not positive and b'uncaught exception:' not in raw):
                raise ValueError('Unexpected consequential Action result: '+name)
        if any(digest((ROOT/name).read_bytes()) != value for name, value in inputs.items()):
            raise ValueError('Consumed source changed during execution')
        report['status'] = 'PASS_HOSTED_OWNED_IO_ACTIONS'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['seconds'] = time.monotonic()-start
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ['status', 'seconds', 'error']}))
    return 0 if report['status'] == 'PASS_HOSTED_OWNED_IO_ACTIONS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
