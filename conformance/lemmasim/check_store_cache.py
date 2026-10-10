#!/usr/bin/env python3
"""Run the real guest Action cache probe and independently inspect its bytes.

Host-only development check; this cannot pass RV64/device acceptance.
Invoke in the pinned environment. A private Lake build supplies the actual
guest import closure, including when the enclosing .lake directory is empty.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from store_oracle import recover

ROOT = Path(__file__).resolve().parents[2]
ENGINE = 'Lemma.Services.Store.Engine'


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


def prepare_dependencies(output, inherited):
    """Build only the probe's guest dependency in fresh, private Lake outputs.

    NotebookKernel does not import the separately linked store. An enclosing
    `lake env` therefore cannot establish that Engine's object exists. The
    private package copies maintained sources without alteration and never
    reads or writes the caller's .lake cache. Lake resolves the real import
    closure; this host check does not manufacture guest declarations.
    """
    workspace = output / 'dependencies'
    workspace.mkdir()
    shutil.copytree(ROOT / 'Lemma', workspace / 'Lemma')
    for name in ('lakefile.toml', 'lean-toolchain'):
        shutil.copyfile(ROOT / name, workspace / name)
    env = dict(inherited)
    # `lake env` callers can otherwise leak a populated or stale outer cache.
    env.pop('LEAN_PATH', None)
    env.pop('LEAN_SRC_PATH', None)
    lake = ['lake', '--no-cache', '-d', str(workspace)]
    command(lake + ['build', ENGINE], output / 'dependencies.log', env)
    library = workspace / '.lake/build/lib/lean'
    engine = library / 'Lemma/Services/Store/Engine.olean'
    if not engine.is_file():
        raise ValueError('fresh Lake build did not produce the actual Engine object')
    sources, objects = {}, {}
    for compiled in sorted((library / 'Lemma').rglob('*.olean')):
        module = compiled.relative_to(library).with_suffix('')
        source = module.with_suffix('.lean')
        snapshot, original = workspace / source, ROOT / source
        if not snapshot.is_file() or sha(snapshot) != sha(original):
            raise ValueError('compiled guest dependency differs from maintained source: ' + str(source))
        sources[str(source)] = sha(snapshot)
        objects[str(compiled.relative_to(output))] = sha(compiled)
    return lake, env, {'sources': sources, 'objects': objects,
                       'package_inputs': {name: sha(workspace / name) for name in ('lakefile.toml', 'lean-toolchain')}}


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
        lake, env, dependencies = prepare_dependencies(output, os.environ)
        result['dependencies'] = dependencies
        command(lake + ['env', 'lean', '-o', str(support / 'StoreProbe.olean'),
                        str(ROOT / 'conformance/lemmasim/StoreProbe.lean')],
                output / 'support.log', env)
        env['LEAN_PATH'] = str(support)
        env['LEMMA_CACHE_OUT'] = str(output / 'observations')
        command(lake + ['env', 'lean', str(ROOT / 'conformance/lemmasim/StoreReadCache.lean')],
                output / 'probe.log', env)
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
