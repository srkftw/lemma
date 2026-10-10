#!/usr/bin/env python3
"""Run the real guest Action cache probe and independently inspect its bytes.

Host-only development check; this cannot pass RV64/device acceptance.
Invoke through `lake env` so the pinned Lean module search path is available.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from store_oracle import recover

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, log, env):
    with log.open('xb') as stream:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            status = process.wait(timeout=120)
            if status:
                raise ValueError(f'Lean probe failed status{status}; retained {log}')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'schema_version': 1, 'scope': 'actual elaborated guest Actions plus independent literal observations; not RV64/device acceptance',
              'status': 'FAIL', 'inputs': {str(path.relative_to(ROOT)): sha(path) for path in (
                  ROOT / 'Lemma/Services/Store/Engine.lean', ROOT / 'conformance/lemmasim/StoreProbe.lean',
                  ROOT / 'conformance/lemmasim/StoreReadCache.lean', Path(__file__).resolve())}}
    try:
        support = output / 'support'
        support.mkdir()
        env = dict(os.environ)
        command(['lean', '-o', str(support / 'StoreProbe.olean'), 'conformance/lemmasim/StoreProbe.lean'],
                output / 'support.log', env)
        env['LEAN_PATH'] = str(support) + ':' + env.get('LEAN_PATH', '')
        env['LEMMA_CACHE_OUT'] = str(output / 'observations')
        command(['lean', 'conformance/lemmasim/StoreReadCache.lean'], output / 'probe.log', env)
        image = output / 'observations/cached-recovery.img'
        root, sequence, objects = recover(image.read_bytes())
        if root.generation != 2 or sequence != 3 or len(objects) != 2:
            raise ValueError('Independent recovered generation/sequence/object count differs')
        if objects[(1, 7)].payload != b'replacement' or objects[(2, 7)].payload != b'different namespace':
            raise ValueError('Independent namespace/replacement bytes differ')
        trace = output / 'observations/reads.trace'
        if trace.read_text().splitlines()[:3] != ['1:80:8:2', '1:81:9:2', '1:81:10:2']:
            raise ValueError('Independent cache/cross-sector trace differs')
        result.update(status='PASS', generation=2, sequence=3,
                      observations={str(path.relative_to(output)): sha(path) for path in (image, trace, output / 'probe.log')})
    except Exception as error:
        result['error'] = str(error)
    result['elapsed_seconds'] = time.monotonic() - started
    (output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
