#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently bind retained TCI objects, reproduce their link, then rebuild UART.

The original producer did not record intermediate object hashes. Its receipt is
immutable. A successful observation below records the retained bytes now and
requires their real link to reproduce both original outputs. This is a distinct
retained-closure assessment, never retroactive fresh-object provenance.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import build as producer

ACTIVE_GROUPS = set()
GROUP_LOCK = Lock()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def available():
    return next(int(row.split()[1]) * 1024 for row in Path('/proc/meminfo').read_text().splitlines()
                if row.startswith('MemAvailable:'))


def inventory(paths):
    return {str(p.resolve()): {'sha256': producer.sha(p), 'bytes': p.stat().st_size}
            for p in sorted(set(paths))}


def unchanged(values):
    return all(Path(name).is_file() and Path(name).stat().st_size == item['bytes']
               and producer.sha(name) == item['sha256'] for name, item in values.items())


def run(argv, cwd, out, phase, env, deadline, report):
    require(available() >= 2 << 30 and shutil.disk_usage(out).free >= 2 << 30,
            '2GiB available-memory/free-space floor')
    start = time.monotonic()
    row = {'phase': phase, 'argv': argv, 'working_directory': str(cwd)}
    child = None
    try:
        with (out / (phase + '.log')).open('wb') as log:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            with GROUP_LOCK:
                ACTIVE_GROUPS.add(child.pid)
            while child.poll() is None:
                rss = 0
                with GROUP_LOCK:
                    groups = set(ACTIVE_GROUPS)
                for stat in Path('/proc').glob('[0-9]*/stat'):
                    try:
                        fields = stat.read_text().rsplit(')', 1)[1].split()
                        if int(fields[2]) in groups:
                            rss += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
                    except (OSError, ValueError, IndexError):
                        pass
                report['peak_tree_rss_bytes'] = max(report.get('peak_tree_rss_bytes', 0), rss)
                if time.monotonic() >= deadline or rss > 6 << 30 or available() < 2 << 30 \
                        or shutil.disk_usage(out).free < 2 << 30:
                    raise RuntimeError('Original time/resource budget reached')
                time.sleep(.25)
            row['exit_code'] = child.returncode
            require(child.returncode == 0, 'Actual compiler/link command failed: ' + phase)
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            row['exit_code'] = child.returncode
        if child is not None:
            with GROUP_LOCK:
                ACTIVE_GROUPS.discard(child.pid)
        row['seconds'] = time.monotonic() - start
        report['commands'].append(row)


def retained(a):
    receipt = a.receipt.resolve()
    base = receipt.parent
    original = producer.read(receipt)
    require(original.get('result') == 'BUILT_WASM64_QEMU_TCI' and original.get('exit_code') == 0
            and original.get('production_mode') == 'fresh-upstream-objects-and-real-link/1',
            'Expected completed whole-object predecessor')
    source = base / 'source'
    producer.retained_source_identity(original, base / 'source-inputs.json', source)
    commands = producer.read(base / 'commands.json')
    compile_rows = commands['compile']
    require(len(compile_rows) == original['fresh_object_count'] == 1047,
            'Complete1047-object predecessor closure required')
    objects = {row['output']: Path(row['argv'][row['argv'].index('-o') + 1]) for row in compile_rows}
    require(len(objects) == 1047 and len(set(objects.values())) == 1047,
            'Object names or actual outputs alias')
    for p in objects.values():
        require(p.is_file() and p.parent == base, 'Retained object absent/outside original output')
    bound = inventory([receipt, base / 'commands.json', base / 'source-inputs.json',
                       base / 'generated-build-inputs.json', base / 'retained-link-inputs.json',
                       *objects.values()])
    generated = producer.read(base / 'generated-build-inputs.json')
    external = producer.read(base / 'retained-link-inputs.json')
    for values in (generated, external):
        require(all(Path(p).is_file() and producer.sha(p) == digest for p, digest in values.items()),
                'Actual retained generated/header/SDK closure differs')
        bound.update(inventory([Path(p) for p in values]))
    require(producer.sha(base / 'generated-build-inputs.json') == original['generated_build_inputs_sha256']
            and producer.sha(base / 'retained-link-inputs.json') == original['retained_link_inputs_sha256'],
            'Original generated/SDK inventory identity differs')
    used = {Path(arg) for arg in commands['link'] if arg.endswith(('.o', '.a'))}
    archives = []
    members = set()
    for name, argv in commands['archives']:
        require(argv[0] == 'emar' and argv[1] in ('csrDT', 'csrD'), 'Unknown retained archive command')
        archive = Path(argv[2])
        require(archive.is_file() and archive.parent == base, 'Retained archive absent')
        archives.append(archive)
        members.update(Path(arg) for arg in argv[3:] if arg.endswith('.o'))
    require(set(objects.values()) == {p for p in used if p.suffix == '.o'} | members,
            'Recorded link/archive commands do not cover exact1047 objects')
    require(used == {p for p in used if p.suffix == '.o'} | set(archives) | {Path(p) for p in external},
            'Unexpected or omitted link input')
    bound.update(inventory(archives))
    for name, item in original['outputs'].items():
        require(unchanged({str(base / name): item}), 'Original compiler output differs')
        bound.update(inventory([base / name]))
    return base, original, source, commands, objects, bound


def observe(a):
    out = a.output_dir.resolve()
    out.mkdir(exist_ok=False)
    start = time.monotonic()
    report = {'schema': 'lemma-tci-retained-object-observation/1', 'status': 'FAIL',
              'scope': __doc__, 'commands': [], 'bounds': {'whole_seconds': a.timeout,
                'tree_rss_bytes': 6 << 30, 'minimum_available_bytes': 2 << 30,
                'minimum_free_bytes': 2 << 30}}
    try:
        base, original, source, commands, objects, bound = retained(a)
        initial = inventory([Path(__file__), producer.HERE / 'build.py', producer.HERE / 'shell.nix'])
        report.update(predecessor={'path': str(a.receipt.resolve()), 'sha256': producer.sha(a.receipt)},
                      inputs=initial, observed_inputs=bound, observed_object_count=len(objects),
                      original_source_closure_sha256=original['source_closure_sha256'])
        producer.write(out / 'observed-inputs.json', bound)
        env = os.environ.copy()
        env.update(EMCC_CORES='1', BINARYEN_CORES='1', EM_CACHE=str(out / 'emcache'))
        subprocess.run(['cp', '-a', '--reflink=auto', str(base / 'emcache'), str(out / 'emcache')], check=True)
        link = [str(out / 'qemu-system-riscv64.js') if arg == str(base / 'qemu-system-riscv64.js') else arg
                for arg in commands['link']]
        run(link, Path(commands['working_directory']), out, 'baseline-real-link', env,
            start + a.timeout, report)
        for name, item in original['outputs'].items():
            require(unchanged({str(out / name): item}), 'Baseline real link differs from original output: ' + name)
        require(unchanged(bound) and unchanged(initial), 'Observed closure changed during baseline link')
        producer.retained_source_identity(original, base / 'source-inputs.json', source)
        report.update(status='PASS_NEWLY_OBSERVED_RETAINED_CLOSURE_AND_BYTE_IDENTICAL_LINK',
                      outputs=original['outputs'], observed_inputs_sha256=producer.sha(out / 'observed-inputs.json'))
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['seconds'] = time.monotonic() - start
        producer.write(out / 'result.json', report)
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


def build(a):
    out = a.output_dir.resolve()
    out.mkdir(exist_ok=False)
    start = time.monotonic()
    report = {'schema': 'lemma-tci-public-build/1', 'result': 'FAIL',
              'producer_input_root': str(producer.ROOT), 'commands': [],
              'production_mode': 'incremental-flow-objects-and-real-link/1',
              'scope': 'Three fresh UART/frontend/serial objects and a fresh real Wasm link. Other objects are a newly observed retained closure whose baseline link reproduced original outputs; not retroactive fresh-object provenance, guest execution, timing or browser responsiveness.',
              'limits': {'whole_seconds': a.timeout, 'jobs': 2, 'tree_rss_bytes': 6 << 30,
                         'minimum_free_bytes': 2 << 30, 'minimum_available_bytes': 2 << 30}}
    try:
        initial = producer.sources()
        base, original, source, commands, objects, bound = retained(a)
        observation = producer.read(a.observation)
        require(observation.get('status') == 'PASS_NEWLY_OBSERVED_RETAINED_CLOSURE_AND_BYTE_IDENTICAL_LINK'
                and observation['predecessor']['sha256'] == producer.sha(a.receipt)
                and observation['observed_inputs'] == bound, 'Passed independent retained closure differs')
        require(producer.sha(a.observation.parent / 'observed-inputs.json') == observation['observed_inputs_sha256'],
                'Retained observation inventory differs')
        overlay = a.overlay.resolve()
        manifest = producer.read(overlay / 'source-inputs.json')
        overlay_files = {str(overlay / name): item for name, item in manifest.items()}
        # Frozen source archives use plain SHA maps; never infer current root bytes.
        require(unchanged(overlay_files), 'Frozen UART flow overlay differs')
        report.update(inputs=initial, direct_helpers=original.get('direct_helpers', False),
                      predecessor={'receipt': str(a.receipt.resolve()), 'sha256': producer.sha(a.receipt),
                                   'source_closure_sha256': original['source_closure_sha256'],
                                   'outputs': original['outputs']},
                      retained_closure_observation={'path': str(a.observation.resolve()),
                        'sha256': producer.sha(a.observation), 'scope': observation['scope']},
                      reused_object_count=1044, fresh_object_count=3,
                      retained_inputs=bound, overlay_inputs=overlay_files)
        producer.write(out / 'retained-inputs.json', bound)
        copy = out / 'source'
        subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(copy)], check=True)
        require(producer.identity(copy) == producer.read(base / 'source-inputs.json'),
                'Copied original complete source differs')
        run(['python3', str(overlay / 'tooling/lemmasim/patch_uart_flow.py'), str(copy),
             '--header', str(overlay / 'sim/host/lemma_uart_ingress.h'),
             '--implementation', str(overlay / 'sim/host/lemma_uart_qemu.inc.c')],
            producer.ROOT, out, 'apply-frozen-flow-overlay', os.environ.copy(), start + a.timeout, report)
        current = producer.identity(copy)
        previous = producer.read(base / 'source-inputs.json')
        changed = {name for name in current.keys() | previous.keys() if current.get(name) != previous.get(name)}
        require(changed == {'hw/riscv/lemma_qemu.c', 'hw/riscv/lemma_uart_ingress.h',
                            'hw/riscv/lemma_uart_qemu.inc.c', 'chardev/char-fe.c', 'hw/char/serial.c'},
                'Exact five-source flow overlay differs')
        producer.write(out / 'source-inputs.json', current)
        report['changed_sources'] = {name: {'before': previous[name], 'after': current[name]} for name in sorted(changed)}
        selected = {'libqemu-riscv64-softmmu.a.p/hw_riscv_lemma_qemu.c.o',
                    'libchardev.a.p/chardev_char-fe.c.o', 'libsystem.a.p/hw_char_serial.c.o'}
        # A header change may invalidate an unexpected translation unit. Check
        # every retained compiler depfile rather than trusting the chosen two.
        dependents = set()
        for name, obj in objects.items():
            dep = Path(str(obj) + '.d')
            require(dep.is_file(), 'Actual compiler depfile absent: ' + str(dep))
            words = dep.read_text().replace('\\\n', ' ').split()
            if any(str(source / path) in words for path in changed):
                dependents.add(name)
        require(dependents == selected, 'Changed source/header dependency closure differs from exact three objects')
        report['dependency_affected_objects'] = sorted(dependents)
        env = os.environ.copy()
        env.update(EMCC_CORES='1', BINARYEN_CORES='1', EM_CACHE=str(out / 'emcache'))
        subprocess.run(['cp', '-a', '--reflink=auto', str(base / 'emcache'), str(out / 'emcache')], check=True)
        fresh = {}
        compile_commands = []
        for number, row in enumerate(x for x in commands['compile'] if x['output'] in selected):
            old_obj = objects[row['output']]
            new_obj = out / ('flow-' + str(number) + '.o')
            fresh[str(old_obj)] = str(new_obj)
            argv = [arg.replace(str(source), str(copy)).replace(str(old_obj), str(new_obj)) for arg in row['argv']]
            compile_commands.append({'output': row['output'], 'argv': argv})
        require(len(compile_commands) == 3, 'Three real compiler commands required')
        link = [fresh.get(arg, str(out / 'qemu-system-riscv64.js')
                if arg == str(base / 'qemu-system-riscv64.js') else arg) for arg in commands['link']]
        require(all(link.count(name) == 1 for name in fresh.values()), 'Fresh objects absent/duplicated in real link')
        producer.write(out / 'commands.json', {'working_directory': commands['working_directory'],
                       'compile': compile_commands, 'link': link})
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(run, row['argv'], Path(commands['working_directory']), out,
                    'compile-' + str(i), env, start + a.timeout, report)
                    for i, row in enumerate(compile_commands)]
            for job in jobs:
                job.result()
        run(link, Path(commands['working_directory']), out, 'real-wasm-link', env, start + a.timeout, report)
        require(unchanged(bound) and producer.identity(source) == previous and producer.identity(copy) == current
                and producer.sources() == initial, 'Source/retained closure changed during fresh flow production')
        require(unchanged(overlay_files), 'Frozen UART overlay changed during production')
        report['fresh_object_inputs'] = inventory([Path(name) for name in fresh.values()])
        report['retained_inputs_sha256'] = producer.sha(out / 'retained-inputs.json')
        report.update(producer.completed_build_metadata(out, copy, out), result='BUILT_WASM64_QEMU_TCI')
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['elapsed_seconds'] = time.monotonic() - start
        producer.write(out / 'build.json', report)
        print(report['result'], report.get('error'), report['elapsed_seconds'])
    return 0 if report['result'] == 'BUILT_WASM64_QEMU_TCI' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('observe')
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=300)
    p = sub.add_parser('build')
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--observation', type=Path, required=True)
    p.add_argument('--overlay', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=900)
    a = parser.parse_args()
    require(30 <= a.timeout <= 900, 'Whole budget outside30..900seconds')
    return observe(a) if a.action == 'observe' else build(a)


if __name__ == '__main__':
    raise SystemExit(main())
