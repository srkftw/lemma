#!/usr/bin/env python3
"""Literal RTL power edges, UART admission/quota and one exact native suffix.
No guest-driver, notebook, physical or arbitrary cached-state qualification.
"""
import argparse
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time

from check_native_power import run
from product_native import EXECUTED_PROFILE, ROOT, native, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl-build', type=Path, required=True)
    parser.add_argument('--native-source-archive', type=Path)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    started = time.monotonic()
    result = {'status': 'FAIL', 'scope': __doc__}
    try:
        build = args.rtl_build.resolve()
        checked = native(build, args.native_source_archive, EXECUTED_PROFILE)
        result['native_validation'] = checked['validation']
        manifest = checked['manifest']
        source = ROOT / 'tests/lemmasim/native_pen_uart_resync.cpp'
        result['fixture_sha256'] = sha(source)
        result['checker_sha256'] = sha(__file__)
        version = subprocess.check_output(['verilator', '-V'], text=True, timeout=30)
        roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$', version, re.M))
        if len(roots) != 1:
            raise ValueError('one pinned Verilator root required')
        prefix = Path(roots.pop())
        compiler = Path(shutil.which('c++') or '').resolve()
        if not str(compiler).startswith('/nix/store/') or not compiler.is_file():
            raise ValueError('run in the pinned silicon Nix shell')
        result['compiler'] = {'path': str(compiler), 'sha256': sha(compiler)}
        obj = build / 'obj'
        names = ['machine_runtime.o', 'backing_io.o', 'backing_io_posix.o', 'backing_peer.o',
                 'ble_peer_transport.o', 'usb_transport.o', 'verilated.o', 'verilated_save.o',
                 'verilated_threads.o', 'verilated_dpi.o', 'Vlemma_soc__ALL.a']
        result['compiled_inputs'] = {str(obj / n): sha(obj / n) for n in names}
        origin = ROOT if args.native_source_archive is None else args.native_source_archive.resolve()
        binary = out / 'test'
        run([compiler, '-O2', '-UNDEBUG', '-std=c++17', '-Wall', '-Wextra', '-Werror',
             '-I', origin / 'sim/rtl/host', '-I', obj, '-isystem', prefix / 'include',
             '-isystem', prefix / 'include/vltstd', source, *[obj / n for n in names],
             '-pthread', '-o', binary], out / 'compile.log', 90)
        run([binary, out], out / 'run.log', 60)
        marker = ('PASS raw brownout exact8 release pen cancellation retains current/future '
                  'UART recovery bytes and quota; observational snapshot exact suffix')
        if marker not in (out / 'run.log').read_text():
            raise RuntimeError('missing actual circuit/admission/exact-suffix result')
        for name in ('retained.snap', 'original-suffix.snap', 'fork-suffix.snap'):
            if not 112 < (out / name).stat().st_size < 768 * 1024 * 1024:
                raise RuntimeError('missing bounded authoritative snapshot')
        native(build, args.native_source_archive, EXECUTED_PROFILE)
        if sha(source) != result['fixture_sha256'] or sha(__file__) != result['checker_sha256']:
            raise RuntimeError('consumed fixture/checker source changed')
        if any(sha(p) != h for p, h in result['compiled_inputs'].items()):
            raise RuntimeError('consumed generated/native object changed')
        result.update(status='PASS_RAW_RESET_UART_QUOTA_EXACT_NATIVE_SUFFIX',
                      binary_sha256=manifest['binary_sha256'], snapshot_identity=manifest['snapshot_identity'],
                      test_binary_sha256=sha(binary),
                      artifacts={p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                                 for p in out.iterdir() if p.suffix in ('.snap', '.log')})
    except BaseException as error:
        result['error'] = repr(error)
    finally:
        result['seconds'] = time.monotonic() - started
        result['max_completed_child_rss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        if result['seconds'] > 180:
            result.update(status='FAIL', bound_error=True)
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result.get(k) for k in ('status', 'seconds', 'error')}))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
