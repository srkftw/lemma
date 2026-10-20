#!/usr/bin/env python3
"""Run actual Lean local PCM consumer Actions and consequential source negatives.

The maintained User module is appended verbatim with a finite RAM/service fixture.
This checks owned output lifecycle and receipts, not controller, CPU, audio
presentation, timing, checkpoint, sensor, or physical qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import time
from lean_export_host import environment, policy
ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT/'Lemma/User/Multimodal.lean',
             ROOT/'tests/multimodal/NotebookAudioActions.lean.inc',
             ROOT/'scripts/lean_export_host.py', Path(__file__).resolve()]
    inputs = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}
    source, fixture = paths[0].read_text(), paths[1].read_text()
    mutations = [
        ('accepted-is-consumed', '  .bind (audioPut 32 0) fun s _ =>',
         '  .bind (audioPut 32 16) fun s _ =>'),
        ('mute-does-not-revoke', '  .bind (stopAudio 1 1) fun s _ =>',
         '  .bind (.done 0 0) fun s _ =>'),
        ('skip-real-PCM-submission',
         '  .bind (submitPCM (audioPage+64) epoch) fun status accepted =>',
         '  .bind (.done 0 16) fun status accepted =>'),
        ('wire-bytes-budget', 'armPCM 1 16000 128 (ticks + 100000000)',
         'armPCM 1 16000 32 (ticks + 100000000)'),
        ('early-consumption-receipt', 'if 16 ≤ observed then stopAudio 0 0 else',
         'if 0 ≤ observed then stopAudio 0 0 else'),
        ('stale-revokes-successor', 'if mmDifferent (current) (epoch) = true then audioReceipt 4 else',
         'if mmDifferent (current) (epoch) = true then .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else audioReceipt 4 else')]
    report = {'status': 'FAIL', 'scope': __doc__, 'source_inputs': inputs,
              'started_unix': time.time(), 'cases': [], 'host_policy': policy(2),
              'limits': {'whole_seconds': 240, 'case_seconds': 30,
                         'address_bytes': 16 << 30, 'Lean_heap_MiB': 2048,
                         'file_bytes': 64 << 20}}
    start = time.monotonic()

    def limits():
        # The actual Lake startup reserves a1GiB thread stack. This virtual
        # bound matches existing target/component checkers; Lean heap is capped
        # separately. Address-space size is not an RSS or performance claim.
        resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))

    try:
        lake, lean = Path(shutil.which('lake') or ''), Path(shutil.which('lean') or '')
        if not lake.is_file() or not lean.is_file():
            raise ValueError('Pinned Lean/lake environment required')
        report['tools'] = {name: {'path': str(p.resolve()), 'sha256': sha(p.resolve().read_bytes())}
                           for name, p in [('lake', lake), ('lean', lean)]}
        cases = [('actual-maintained', source, True)]
        for name, old, new in mutations:
            if source.count(old) != 1:
                raise ValueError('Exact unique source-negative anchor missing: '+name)
            cases.append((name, source.replace(old, new, 1), False))
        for name, body, positive in cases:
            directory = out/name
            directory.mkdir()
            program = directory/'NotebookAudio.lean'
            program.write_text(body+'\n'+fixture)
            command = [str(lake), 'env', 'lean', '-j2', '-M2048', '--run', str(program)]
            began = time.monotonic()
            result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                    env={**os.environ, **environment(policy(2))},
                                    preexec_fn=limits,
                                    timeout=min(30, 240-(began-start)))
            raw = result.stdout+result.stderr
            (directory/'output.log').write_bytes(raw)
            success = result.returncode == 0 and b'NOTEBOOK_AUDIO_ACTIONS_PASS' in raw
            report['cases'].append({'case': name, 'expected_success': positive,
                                    'observed_success': success, 'exit_code': result.returncode,
                                    'seconds': time.monotonic()-began, 'command': command,
                                    'compiled_input_sha256': sha(program.read_bytes()),
                                    'output_sha256': sha(raw)})
            if success != positive or (not positive and b'uncaught exception:' not in raw):
                raise ValueError('Unexpected consequential Action result: '+name)
        if any(sha((ROOT/name).read_bytes()) != value for name, value in inputs.items()):
            raise ValueError('Consumed source changed during execution')
        report['status'] = 'PASS_HOSTED_NOTEBOOK_AUDIO_ACTIONS'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['seconds'] = time.monotonic()-start
        report['child_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({key: report.get(key) for key in ['status', 'seconds', 'error']}))
    return 0 if report['status'] == 'PASS_HOSTED_NOTEBOOK_AUDIO_ACTIONS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
