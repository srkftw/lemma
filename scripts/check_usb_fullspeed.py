#!/usr/bin/env python3
"""Qualify the registered full-speed digital USB codec and packet controller.

Literal circuitry, not electrical USB qualification, whole-machine guest
acceptance, standard transaction timing, or full USB conformance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

from check_silicon import command, device_build

ROOT = Path(__file__).resolve().parents[1]
SPEC = {'url': 'https://www.usb.org/document-library/usb-20-specification',
        'base_pdf_sha256': 'd39698a33486c399124af92bd02e4f978fd9a836b5cf4e52e6e4633eb1d89f61',
        'sections': ['7.1.8', '7.1.9', '7.1.9.1', '7.1.10', '7.1.11', '7.1.7.5', '8.3.5']}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--jobs', type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('work-dir must be unused under build/')
    if not 30 <= args.timeout <= 300:
        parser.error('timeout must be30..300seconds')
    out.mkdir(parents=True)
    started = time.monotonic()
    result = {'schema': 'lemma-usb-fullspeed-evidence/1', 'status': 'FAIL',
              'scope': 'two distinct literal registered digital PHYs + packet controller; '
                       'independent source/waveform/CRC vectors and exact six state cuts; '
                       'no electrical, whole-guest or complete USB timing claim',
              'primary_specification': SPEC}
    names = ['sim/rtl/lemma_usb_fs_phy.sv', 'sim/rtl/lemma_usb_device.sv',
             'conformance/silicon/USBFullSpeed.sv', 'tests/usb/fs_phy.cpp',
             'scripts/check_usb_fullspeed.py', 'scripts/check_silicon.py',
             'tooling/silicon/sim.nix', 'flake.lock']
    try:
        before = {name: sha(ROOT / name) for name in names}
        result['source_inputs'] = before
        source_copy = out / 'consumed'; source_copy.mkdir()
        for name in names:
            dest = source_copy / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        obj = out / 'obj'; obj.mkdir()
        states = out / 'states'; states.mkdir()
        argv = ['verilator', '--cc', '--exe', '--build', '--savable', '--threads', '1',
                '-Wall', '-j', str(args.jobs), '--top-module', 'USBFullSpeed',
                '--Mdir', str(obj), '-CFLAGS', '-std=c++17 -O2 -Wall -Wextra -Werror',
                *[str(ROOT / name) for name in names[:4]]]
        built, tools = device_build(argv, out / 'tools.json', out / 'build.log', args.timeout)
        ran = command([str(obj / 'VUSBFullSpeed'), str(states)], out / 'simulation.log', 30)
        log = (out / 'simulation.log').read_text()
        if log.count('USB_FS_LITERAL_PASS ') != 1 or 'FAIL' in log:
            raise RuntimeError('missing actual digital USB result')
        pairs = [(f'cut-{cut}-suffix-live', f'cut-{cut}-suffix-fork') for cut in (12, 70, 98, 560)]
        pairs += [('mid-reset-suffix-live', 'mid-reset-suffix-fork'),
                  ('held-rx-suffix-live', 'held-rx-suffix-fork')]
        for left, right in pairs:
            if sha(states / left) != sha(states / right):
                raise RuntimeError('complete generated state suffix differs')
        if before != {name: sha(ROOT / name) for name in names}:
            raise RuntimeError('consumed USB wire source changed')
        result.update(status='PASS', commands=[built, ran], tool_inputs=tools,
                      compiled_binary_sha256=sha(obj / 'VUSBFullSpeed'), observation=log.strip(),
                      snapshots={path.name: {'bytes': path.stat().st_size, 'sha256': sha(path)}
                                 for path in sorted(states.iterdir())})
    except BaseException as error:
        result['error'] = str(error)
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        result['resources'] = {'largest_reaped_child_peak_rss_kib': usage.ru_maxrss,
                               'reaped_children_user_seconds': usage.ru_utime,
                               'reaped_children_system_seconds': usage.ru_stime}
        result['host_seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'result': str(out / 'result.json'),
                      'host_seconds': result['host_seconds']}, indent=2))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
