#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact Clocked13 logical/generated phase continuation, without guest traffic."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from check_native_usb_wire_pending import run_fixture
from silicon_guest import ROOT, native_source_archive, run_command, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build', 'rtl-source-root', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('unused work-dir under build required')
    out.mkdir(parents=True)
    started = time.monotonic()
    result = {'schema': 'lemma-native-usb-clock-evidence/1', 'status': 'FAIL',
              'scope': 'independent fractional clock phase + generated reset-domain state; '
                       'three exact same-backend suffixes and valid-checksum negative states; '
                       'no guest instructions, external peer, completed USB transaction or physical qualification',
              'bounds': {'host_seconds': 120, 'maximum_tree_rss_kib': 4194304,
                         'maximum_apparent_bytes': 12000000000}}
    try:
        machine, _, archive = native_source_archive(
            args.rtl_build, args.rtl_source_root, 'lemma-silicon-dev/0.13.0')
        version = subprocess.check_output(['verilator', '-V'], text=True, timeout=10)
        roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$', version, re.M))
        if len(roots) != 1:
            raise ValueError('ambiguous Verilator installation')
        prefix = Path(roots.pop())
        obj = args.rtl_build.resolve() / 'obj'
        names = ['machine_runtime.o', 'backing_io.o', 'backing_io_posix.o',
                 'backing_peer.o', 'ble_peer_transport.o', 'usb_transport.o',
                 'verilated.o', 'verilated_save.o', 'verilated_threads.o',
                 'verilated_dpi.o', 'Vlemma_soc__ALL.a']
        source = ROOT / 'tests/lemmasim/native_usb_clock.cpp'
        inputs = {str(obj / name): sha(obj / name) for name in names}
        inputs[str(source)] = sha(source)
        compiler = Path(shutil.which('c++')).resolve()
        if not str(compiler).startswith('/nix/store/'):
            raise ValueError('pinned host compiler required')
        binary = out / 'test'
        argv = ['c++', '-O2', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', args.rtl_source_root.resolve() / 'sim/rtl/host', '-I', obj,
                '-isystem', prefix / 'include', '-isystem', prefix / 'include/vltstd',
                source, *[obj / name for name in names], '-pthread', '-o', binary]
        run_command(argv, timeout=60, log=out / 'compile.log')
        result.update(native_archive=archive, native_binary_sha256=machine['binary_sha256'],
                      compiled_inputs=inputs, test_binary_sha256=sha(binary),
                      compiler={'path': str(compiler), 'sha256': sha(compiler),
                                'version': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]},
                      compile_argv=list(map(str, argv)))
        run_fixture([binary, out], out / 'run.log', 120)
        log = (out / 'run.log').read_text()
        if not log.endswith('NATIVE_USB_CLOCK_PASS complete fractional/generated reset-domain suffixes and valid-checksum phase/container negatives; no guest traffic claim\n'):
            raise ValueError('missing actual clock continuation result')
        rows = [json.loads(line) for line in log.splitlines() if line.startswith('{')]
        if len(rows) != 3 or {row['host_ppm'] for row in rows} != {-2500, 0, 2500}:
            raise ValueError('missing distinct clock continuation cases')
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError('compiled original clock inputs changed')
        native_source_archive(args.rtl_build, args.rtl_source_root, 'lemma-silicon-dev/0.13.0')
        total = sum(path.stat().st_size for path in out.rglob('*') if path.is_file())
        if total > 12000000000:
            raise ValueError('owned output disk bound exceeded')
        result.update(status='PASS', cases=rows, actual_apparent_bytes=total,
                      snapshots={p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                                 for p in sorted(out.glob('*.snap'))})
    except BaseException as error:
        result['error'] = repr(error)
    result['host_seconds'] = time.monotonic() - started
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(out / 'result.json'),
                      'host_seconds': result['host_seconds']}, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
