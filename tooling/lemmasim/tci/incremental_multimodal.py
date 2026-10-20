#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recompile the one invalidated MM2 hardware object over an admitted flow runtime.

The predecessor retains its original 1047-object observation and three-object
flow producer. This producer binds those bytes, replaces exactly one object and
performs a real Wasm link. It neither recompiles upstream QEMU nor executes a
guest. Its separate runtime admission retains the entire predecessor receipt.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import time

import build as producer
from incremental_flow import inventory, unchanged, require, run

sys.path.insert(0, str(producer.ROOT / 'scripts'))
from lemmasim_browser_tci import retained_runtime

MODE = 'incremental-mm2-object-and-real-link/1'
EXPECTED = {'hw/riscv/' + name for name in (
    'lemma_qemu.c', 'lemma_multimodal_qemu.inc.c', 'lemma_multimodal_v2.c',
    'lemma_multimodal_v2.h', 'lemma_multimodal_checkpoint_valid.inc.c',
    'lemma_browser_control.inc.c')}
OBJECT = 'libqemu-riscv64-softmmu.a.p/hw_riscv_lemma_qemu.c.o'


def capture_sources(out, initial, validator, validator_sha):
    """Capture consumed tools before compilation, for later ordinary admission."""
    destination = out / 'producer-sources'
    destination.mkdir(exist_ok=False)
    for name in ('incremental_multimodal.py', 'incremental_flow.py', 'build.py', 'shell.nix'):
        path = producer.HERE / name
        require(producer.sha(path) == initial[str(path.relative_to(producer.ROOT))],
                'Producer changed before source capture')
        shutil.copyfile(path, destination / name)
    require(producer.sha(validator) == validator_sha, 'Validator changed before source capture')
    shutil.copyfile(validator, destination / 'runtime_validator.py')


def freeze_overlay(out):
    """Ordinary builds use maintained inputs without constructing a host patch."""
    out.mkdir(exist_ok=False)
    host = out / 'sim/host'
    host.mkdir(parents=True)
    names = ('lemma_multimodal_checkpoint.inc.c','lemma_multimodal_checkpoint_valid.inc.c',
             'lemma_multimodal_qemu.inc.c','lemma_multimodal_v2.c','lemma_multimodal_v2.h','lemma_qemu.c')
    for name in names:
        shutil.copyfile(producer.ROOT / 'sim/host' / name, host / name)
    patcher = producer.ROOT / 'tooling/lemmasim/patch_multimodal_v2.py'
    shutil.copyfile(patcher, out / 'maintained_patch.py')
    inputs = producer.identity(out)
    producer.write(out / 'source-inputs.json', inputs)
    (out / 'apply.py').write_text('''import hashlib,json,subprocess,sys
from pathlib import Path
here=Path(__file__).resolve().parent
inputs=json.loads((here/'source-inputs.json').read_text())
assert all(hashlib.sha256((here/n).read_bytes()).hexdigest()==h for n,h in inputs.items())
subprocess.run([sys.executable,str(here/'maintained_patch.py'),*sys.argv[1:],'--host-source',str(here/'sim/host')],check=True)
''')
    return out


def select_pcm_observer(source):
    bridge = source / 'hw/riscv/lemma_browser_control.inc.c'
    body = bridge.read_text()
    for name in ('consumed', 'submitted', 'epoch'):
        before = 's->multimodal.stream[8].' + name
        require(body.count(before) == 1, 'PCM bridge observer anchor differs')
        body = body.replace(before, 'lemma_mm_core(s)->stream[8].' + name)
    bridge.write_text(body)


def build(a):
    out = a.output_dir.resolve()
    out.mkdir(exist_ok=False)
    began = time.monotonic()
    report = {'schema': 'lemma-tci-public-build/1', 'result': 'FAIL',
        'production_mode': MODE, 'producer_input_root': str(producer.ROOT),
        'commands': [], 'fresh_object_count': 1, 'reused_object_count': 1046,
        'scope': __doc__, 'limits': {'whole_seconds': a.timeout,
        'tree_rss_bytes': 6 << 30, 'minimum_free_bytes': 2 << 30,
        'minimum_available_bytes': 2 << 30, 'output_bytes': 2 << 30}}
    try:
        initial = producer.sources()
        validator = producer.ROOT / "scripts/lemmasim_browser_tci.py"
        validator_sha = producer.sha(validator)
        capture_sources(out, initial, validator, validator_sha)
        parent, admission = retained_runtime(a.predecessor_runtime)
        require(admission['schema'] == 'lemma-tci-retained-runtime/2',
                'MM2 requires the nonrecursive admitted flow predecessor')
        old = producer.read(a.receipt)
        require(old.get('production_mode') == 'incremental-flow-objects-and-real-link/1'
                and producer.sha(a.receipt) == admission['original_build']['sha256'],
                'Actual three-object producer differs from admitted runtime')
        base = a.receipt.resolve().parent
        source = base / 'source'
        previous = producer.retained_source_identity(old, base / 'source-inputs.json', source)
        require(unchanged(old['retained_inputs']) and unchanged(old['fresh_object_inputs']),
                'A predecessor object or generated/tool input changed')
        commands = producer.read(base / 'commands.json')
        rows = [r for r in commands['compile'] if r['output'] == OBJECT]
        require(len(rows) == 1, 'Expected one actual hardware compiler command')
        row = rows[0]
        old_object = Path(row['argv'][row['argv'].index('-o') + 1])
        require(str(old_object) in old['fresh_object_inputs'], 'Unbound old hardware object')
        link_inputs = [Path(arg) for arg in commands['link'] if arg.endswith(('.o', '.a'))]
        bound = inventory([a.receipt, base / 'commands.json', base / 'source-inputs.json',
                           *link_inputs, parent / 'runtime.json'])
        require(unchanged(bound), 'Predecessor link input missing')
        report['inputs'] = initial
        report['runtime_validator'] = {'path': str(validator), 'sha256': validator_sha}
        report['predecessor'] = {'runtime_sha256': producer.sha(parent / 'runtime.json'),
            'build_sha256': producer.sha(a.receipt), 'source_sha256': old['source_closure_sha256']}
        report['retained_inputs'] = bound
        overlay = a.overlay.resolve() if a.overlay else freeze_overlay(out / 'frozen-overlay')
        overlay_inputs = producer.read(overlay / 'source-inputs.json')
        require(all(producer.sha(overlay / n) == h for n, h in overlay_inputs.items()),
                'Frozen MM2 overlay differs')
        overlay_bound = inventory([overlay / 'apply.py', overlay / 'source-inputs.json',
                                  *[overlay / n for n in overlay_inputs]])
        report['overlay_inputs'] = overlay_bound
        copy = out / 'source'
        subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(copy)], check=True)
        require(producer.identity(copy) == previous, 'Copied predecessor source differs')
        run(['python3', str(overlay / 'apply.py'), str(copy), '--mode', 'tci'],
            producer.ROOT, out, 'apply-exact-mm2-overlay', os.environ.copy(),
            began + a.timeout, report)
        # The PCM observer must read the selected controller, retaining the
        # exact output protocol and original waveform bytes for both ABIs.
        select_pcm_observer(copy)
        current = producer.identity(copy)
        changed = {n for n in current.keys() | previous.keys() if current.get(n) != previous.get(n)}
        require(changed == EXPECTED, 'MM2 overlay changes another source')
        report['changed_sources'] = {n: {'before': previous.get(n), 'after': current[n]}
                                     for n in sorted(changed)}
        producer.write(out / 'source-inputs.json', current)
        # Every old source/header dependency is considered. New headers are
        # reachable only through the sole changed hardware translation unit;
        # its fresh compiler depfile is retained and checked after compilation.
        original_observer = producer.read(parent / 'retained-closure.json')
        original_receipt = Path(original_observer['predecessor']['path'])
        original_commands = producer.read(original_receipt.parent / 'commands.json')
        dependents = set()
        for candidate in original_commands['compile']:
            obj = Path(candidate['argv'][candidate['argv'].index('-o') + 1])
            dep = Path(str(obj) + '.d')
            require(dep.is_file(), 'Original compiler dependency file absent')
            words = dep.read_text().replace('\\\n', ' ').split()
            if any(any(w.endswith('/' + n) for w in words) for n in changed & previous.keys()):
                dependents.add(candidate['output'])
        require(dependents == {OBJECT}, 'MM2 dependency closure is not one hardware object')
        report['dependency_affected_objects'] = sorted(dependents)
        env = os.environ.copy()
        env.update(EMCC_CORES='1', BINARYEN_CORES='1', EM_CACHE=str(out / 'emcache'))
        subprocess_copy = ['cp', '-a', '--reflink=auto', str(base / 'emcache'), str(out / 'emcache')]
        subprocess.run(subprocess_copy, check=True)
        fresh_object = out / 'multimodal.o'
        argv = [v.replace(str(source), str(copy)).replace(str(old_object), str(fresh_object))
                for v in row['argv']]
        link = [str(fresh_object) if v == str(old_object) else
                str(out / 'qemu-system-riscv64.js') if v == str(base / 'qemu-system-riscv64.js') else v
                for v in commands['link']]
        require(link.count(str(fresh_object)) == 1 and str(old_object) not in link,
                'Fresh hardware object is absent/duplicated')
        producer.write(out / 'commands.json', {'working_directory': commands['working_directory'],
                       'compile': [{'output': OBJECT, 'argv': argv}], 'link': link})
        run(argv, Path(commands['working_directory']), out, 'compile-mm2-hardware', env,
            began + a.timeout, report)
        dependencies = Path(str(fresh_object) + '.d').read_text().replace('\\\n', ' ').split()
        require(all(str(copy / n) in dependencies for n in EXPECTED),
                'Fresh compiler did not consume every MM2 source/header')
        run(link, Path(commands['working_directory']), out, 'real-wasm-link', env,
            began + a.timeout, report)
        require(unchanged(bound) and unchanged(overlay_bound) and producer.sources() == initial
                and producer.sha(validator) == validator_sha,
                'Producer/overlay/retained inputs changed')
        producer.retained_source_identity(old, base / 'source-inputs.json', source)
        report['fresh_object_inputs'] = inventory([fresh_object, Path(str(fresh_object) + '.d')])
        report.update(producer.completed_build_metadata(out, copy, out), result='BUILT_WASM64_QEMU_TCI')
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['elapsed_seconds'] = time.monotonic() - began
        producer.write(out / 'build.json', report)
        print(json.dumps({k: report.get(k) for k in ('result', 'error', 'elapsed_seconds')}))
    return 0 if report['result'] == 'BUILT_WASM64_QEMU_TCI' else 1


def admit(a):
    """Retain successful real outputs; admission is not another compilation."""
    r = producer.read(a.receipt)
    require(r.get('production_mode') == MODE and r.get('result') == 'BUILT_WASM64_QEMU_TCI',
            'Completed one-object PCM producer required')
    producer.retained_source_identity(r, a.receipt.parent / 'source-inputs.json', a.source_root)
    require(unchanged(r['retained_inputs']) and unchanged(r['overlay_inputs'])
            and unchanged(r['fresh_object_inputs']), 'Original compiler inputs changed')
    require(len(r['commands']) == 3 and all(x.get('exit_code') == 0 for x in r['commands']),
            'Original overlay/compiler/link commands did not all complete')
    candidates = [Path(k) for k, v in r['retained_inputs'].items()
                  if Path(k).name == 'runtime.json' and v['sha256'] == r['predecessor']['runtime_sha256']]
    require(len(candidates) == 1, 'Original runtime identity is ambiguous')
    parent, old = retained_runtime(candidates[0].parent)
    out = a.output_dir.resolve()
    out.mkdir(exist_ok=False)
    initial = producer.sources()
    require(shutil.disk_usage(out).free > 2 << 30, 'Runtime admission free-space floor')
    shutil.copytree(parent, out / 'predecessor')
    for name, item in r['outputs'].items():
        source = a.build_dir / name
        require(producer.sha(source) == item['sha256'] and source.stat().st_size == item['bytes'],
                'Compiled PCM runtime output differs')
        shutil.copyfile(source, out / name)
    for source, name in [(a.receipt, 'original-build.json'),
                         (a.receipt.parent / 'source-inputs.json', 'source-inputs.json'),
                         (a.receipt.parent / 'commands.json', 'commands.json'),
                         (a.receipt.parent / 'multimodal.o', 'hardware-object.o'),
                         (a.receipt.parent / 'multimodal.o.d', 'hardware-dependencies.d'),
                         (a.receipt.parent / 'compile-mm2-hardware.log', 'compile.log'),
                         (a.receipt.parent / 'real-wasm-link.log', 'link.log')]:
        shutil.copyfile(source, out / name)
    shutil.copytree(a.receipt.parent / 'producer-sources', out / 'producer-source')
    (out / 'overlay-source').mkdir()
    for name, item in r['overlay_inputs'].items():
        require(producer.sha(name) == item['sha256'], 'Frozen overlay source changed')
        shutil.copyfile(name, out / 'overlay-source' / Path(name).name)
    names = {'lemma_fast_block.c','lemma_model.c','lemma_model.h','lemma_multimodal.c',
        'lemma_multimodal.h','lemma_multimodal_qemu.inc.c','lemma_qemu.c','lemma_silicon_fast.h',
        'lemma_uart_ingress.h','lemma_uart_qemu.inc.c','lemma_multimodal_v2.c',
        'lemma_multimodal_v2.h','lemma_multimodal_checkpoint_valid.inc.c','lemma_browser_control.inc.c'}
    (out / 'controller-source').mkdir()
    for name in names:
        shutil.copyfile(a.source_root / 'hw/riscv' / name, out / 'controller-source' / name)
    require(producer.sources() == initial, 'Admission implementation inputs changed')
    m = {'schema':'lemma-tci-retained-runtime/3','abi':'lemma-qemu-wasm-control/1',
        'execution_binding':'lemma-silicon-fast-mm2-subset/0.1.0',
        'multimodal_controller_abi':2,'controller_contract':'lemma-multimodal-converter/2',
        'direct_helpers':old['direct_helpers'],'admission_inputs':initial,
        'original_build':{'path':str(a.receipt.resolve()),'sha256':producer.sha(a.receipt)},
        'files':producer.identity(out),
        'scope':'One freshly compiled MM2 hardware object and real Wasm link over the retained complete flow-runtime closure; functional subset, no Integrated16 union, exact continuation, or fresh upstream compilation claim.'}
    producer.write(out / 'runtime.json', m)
    retained_runtime(out)
    print(out / 'runtime.json')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predecessor-runtime', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--overlay', type=Path, help='Optional exact historical overlay; default freezes maintained MM2 sources')
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=300)
    a = p.parse_args()
    require(30 <= a.timeout <= 600, 'Prospective whole limit outside30..600s')
    return build(a)


if __name__ == '__main__':
    raise SystemExit(main())
