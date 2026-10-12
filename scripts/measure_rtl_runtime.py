#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded, alternating RTL harness measurements; no timing normalization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_machine_runtime import sha, validate_build, validate_guest, Session


def measured(argv, output):
    with output.open('wb') as log:
        begin = time.monotonic()
        process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=log,
                                   start_new_session=True)
        try:
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    process.returncode = os.waitstatus_to_exitcode(status)
                    break
                if time.monotonic() - begin > 130:
                    raise RuntimeError('Measurement exceeded bounded host deadline')
                time.sleep(.02)
            elapsed = time.monotonic() - begin
            if process.returncode:
                raise RuntimeError('Measured process failed: ' + str(process.returncode))
            return {'seconds': elapsed, 'peak_rss_kib': usage.ru_maxrss,
                    'cpu_seconds': usage.ru_utime + usage.ru_stime}
        finally:
            if process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                _, status, _ = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-binary', type=Path, required=True)
    parser.add_argument('--rtl-build', type=Path, required=True)
    parser.add_argument('--guest', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAIL', 'scope': 'bounded monitor workload; host-paced RTL, no realtime claim',
              'observer_sha256': sha(__file__), 'workload_cycles': 1000000}
    try:
        current, build = validate_build(args.rtl_build.resolve())
        report.update({'current_build_sha256': sha(args.rtl_build / 'build.json'),
                       'current_binary_sha256': sha(current), 'old_binary_sha256': sha(args.old_binary),
                       'guest': validate_guest(args.guest), 'rom_sha256': sha(args.rom),
                       'input_sha256': sha(args.input), 'rows': []})
        binaries = [('task005', args.old_binary.resolve()), ('task006', current)]
        relation = None
        for repeat in range(3):
            for name, binary in binaries:
                directory = out / (name + '-' + str(repeat))
                directory.mkdir()
                argv = [str(binary), '--image', str(args.guest / 'image.elf'),
                        '--rom', str(args.rom), '--uart-input', str(args.input),
                        '--uart-output', str(directory / 'uart.bin'), '--quiet-uart',
                        '--cycles', '1000000', '--observer-cycle', '1000000',
                        '--deadline', '120', '--report', str(directory / 'report.json')]
                row = measured(argv, directory / 'process.log')
                guest = json.loads((directory / 'report.json').read_text())
                observed = {key: guest[key] for key in
                            ['cycles', 'retired', 'traps', 'timer_traps', 'finish_code']}
                observed['uart_sha256'] = sha(directory / 'uart.bin')
                if relation is None:
                    relation = observed
                if observed != relation:
                    raise ValueError('Old/current bounded workload observations differ')
                row.update({'backend': name, 'repeat': repeat, 'argv': argv,
                            'observation': observed, 'cycles_per_second': 1000000 / row['seconds']})
                report['rows'].append(row)
        report['medians'] = {name: {field: statistics.median(
            row[field] for row in report['rows'] if row['backend'] == name)
            for field in ['seconds', 'cycles_per_second', 'peak_rss_kib']}
            for name, _ in binaries}
        report['throughput_ratio'] = (report['medians']['task006']['cycles_per_second'] /
                                      report['medians']['task005']['cycles_per_second'])
        report['boot_to_ready'] = {}
        for name, binary in binaries:
            directory = out / (name + '-ready')
            directory.mkdir()
            argv = [str(binary), '--image', str(args.guest / 'image.elf'),
                    '--rom', str(args.rom), '--uart-output', str(directory / 'uart.bin'),
                    '--quiet-uart', '--cycles', '1000000', '--deadline', '120',
                    '--uart-stop-hex', b'LEMMA_MONITOR/1\nREADY\n'.hex(),
                    '--report', str(directory / 'report.json')]
            row = measured(argv, directory / 'process.log')
            row['cycles'] = json.loads((directory / 'report.json').read_text())['cycles']
            if (directory / 'uart.bin').read_bytes() != b'LEMMA_MONITOR/1\nREADY\n':
                raise ValueError('Boot did not reach the exact guest READY banner')
            report['boot_to_ready'][name] = row
        if args.checkpoint:
            session = Session(current, args.guest, args.rom, out / 'resumed')
            try:
                initial = session.call('restore ' + str(args.checkpoint.resolve()))
                final = session.call('run 1000000')
                report['resumed'] = {'checkpoint_sha256': sha(args.checkpoint),
                    'initial': initial, 'final': final, 'restore_seconds': session.rows[-2]['seconds'],
                    'suffix_seconds': session.rows[-1]['seconds'],
                    'suffix_cycles': final['cycle'] - initial['cycle'],
                    'memory_latency': initial['memory_latency'],
                    'scope': 'checkpoint profile may include explicit memory waits; not normalized to zero-wait old run'}
            finally:
                session.close()
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'result.json')


if __name__ == '__main__':
    main()
