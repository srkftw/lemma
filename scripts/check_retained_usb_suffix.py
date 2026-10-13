#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay an admitted native USB suffix privately, without an external peer.

Snapshots and tapes must come from the same native implementation. This is a
captured same-backend continuation check, not cold recovery or a new commit.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from check_guest_usb_link import ROOT, guest_events, require, sha
from lemmasim_session import request


def checkpoint(path):
    """Validate the public checkpoint's complete declared local byte inventory."""
    require(not path.is_symlink() and path.is_dir(), 'checkpoint is not a directory')
    path = path.resolve()
    metadata = json.loads((path / 'snapshot.json').read_text())
    require(metadata['schema'] == 'lemmasim-session/1' and
            metadata['identity']['backend'] == 'rtl' and
            metadata['identity']['profile'] in ('lemma-silicon-dev/0.6.0',
                                                'lemma-silicon-dev/0.8.0'),
            'checkpoint is outside the declared native USB scope')
    require(metadata['files'] == [{'path': 'machine.chk',
                                  'bytes': (path / 'machine.chk').stat().st_size,
                                  'sha256': sha(path / 'machine.chk')}],
            'checkpoint bytes differ from its complete declared inventory')
    require({p.name for p in path.iterdir()} == {'snapshot.json', 'machine.chk'} and
            all(not p.is_symlink() for p in path.iterdir()),
            'checkpoint has unlisted or symbolic files')
    require(type(metadata['virtual_cycle']) is int and metadata['virtual_cycle'] >= 0,
            'checkpoint cycle is invalid')
    return metadata


def external_admissions(path, begin, end, cursor):
    """Retain exactly recorded pen requests; never construct replacement input."""
    if path is None: return []
    require(path.stat().st_size <= 16 << 20, 'external event log exceeds bound')
    selected = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        require(row['admission'] == 'applied' and type(row['cycle']) is int,
                'unaccepted external event cannot become an admission')
        if row['cycle'] < begin: continue
        require(begin <= row['cycle'] <= end and row['cursor'] == cursor + len(selected),
                'external event cursor or admission boundary differs')
        require(type(row['ordinal']) is int and row['ordinal'] >= 0 and
                (not selected or row['ordinal'] == selected[-1]['ordinal'] + 1),
                'external admission identities are out of order')
        command = row['request']
        require(command['action'] == 'inject' and command['kind'] == 'pen' and
                type(command['cycle']) is int and command['cycle'] >= row['cycle'] and
                len(command['words']) == 7 and
                all(type(word) is int and 0 <= word < 1 << 64 for word in command['words']),
                'recorded event is outside the raw pen suffix scope')
        require(not selected or row['cycle'] >= selected[-1]['cycle'],
                'external admissions are out of order')
        selected.append(row)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-bundle', 'snapshot', 'prefix-tape', 'tape', 'final-snapshot',
                 'work-dir'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--prefix-cycle', type=int, required=True)
    parser.add_argument('--external-log', type=Path)
    parser.add_argument('--expect-failed-save', type=int)
    parser.add_argument('--suffix-cycles', type=int, default=200000000)
    parser.add_argument('--group-cycles', type=int, default=5000000)
    parser.add_argument('--host-seconds', type=int, default=1800)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned output')
    out.mkdir(parents=True)
    started = time.monotonic(); deadline = started + args.host_seconds
    process = log = None; directory = out / 'private-fork'
    report = {'schema': 'lemma-retained-usb-suffix/1', 'status': 'FAIL',
              'scope': 'captured same-native USB suffix; no original peer contact or new durability',
              'bounds': {'suffix_cycles': args.suffix_cycles, 'group_cycles': args.group_cycles,
                         'host_seconds': args.host_seconds}, 'run_groups': []}

    def call(value):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'retained suffix host bound')
        return request(directory, value, timeout=min(130, remaining))

    def state(): return call({'action': 'inspect'})['machine']

    def rejected(value):
        before = state()
        try: call(value)
        except RuntimeError as error: text = str(error)
        else: raise ValueError('operation was unexpectedly admitted')
        require(state() == before, 'rejected operation changed authoritative state')
        return text

    def advance(target):
        while state()['cycle'] < target:
            before = state()['cycle']; count = min(args.group_cycles, target - before)
            now = time.monotonic(); result = call({'action': 'run', 'cycles': count})
            require(result['cycle'] == before + count, 'group did not reach its exact boundary')
            report['run_groups'].append({'cycles': count, 'final_cycle': result['cycle'],
                                         'host_seconds': time.monotonic() - now})
            (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    try:
        require(0 < args.group_cycles <= 5000000 and 0 < args.suffix_cycles <= 200000000 and
                0 < args.host_seconds <= 1800, 'suffix exceeds declared qualification bounds')
        initial, final = checkpoint(args.snapshot), checkpoint(args.final_snapshot)
        begin, end = initial['virtual_cycle'], final['virtual_cycle']
        require(initial['identity'] == final['identity'] and begin < end and
                end - begin <= args.suffix_cycles and begin <= args.prefix_cycle <= end,
                'checkpoint identities or suffix boundaries differ')
        rows = external_admissions(args.external_log, begin, end, initial['external_event_cursor'])
        profile = initial['identity']['profile']
        workload = 'usb-next-bulk-notebook' if profile.endswith('/0.8.0') else 'usb-bulk-notebook'
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'session', '--backend', 'rtl',
                '--profile', profile, '--workload', workload, '--native-bundle',
                str(args.native_bundle.resolve()), '--restore', str(args.snapshot.resolve()),
                '--mode', 'laboratory', '--headless', '--paused', '--session-dir', str(directory),
                '--timeout', '120', '--quantum', '1000']
        inputs = [args.snapshot / 'machine.chk', args.prefix_tape, args.tape,
                  args.final_snapshot / 'machine.chk']
        if args.external_log is not None: inputs.append(args.external_log)
        report.update(identity=initial['identity'], snapshot_cycle=begin, final_cycle=end,
                      input_files={str(p.resolve()): sha(p) for p in inputs}, private_argv=argv)
        log = (out / 'private-fork.log').open('xb')
        process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        startup_deadline = min(deadline, time.monotonic() + 60)
        while not (directory / 'session.json').exists():
            require(process.poll() is None and time.monotonic() < startup_deadline,
                    'source-bound private restore failed'); time.sleep(.02)
        require(state()['cycle'] == begin and state()['usb']['fork_suspended'],
                'restored external attachment was not suspended at its boundary')
        errors = [rejected({'action': 'run', 'cycles': 1})]
        call({'action': 'usb-outcomes', 'path': str(args.prefix_tape.resolve())})
        require(state()['usb']['replay_horizon'] == args.prefix_cycle,
                'prefix tape has a different authoritative horizon')
        errors.append(rejected({'action': 'run', 'cycles': args.prefix_cycle - begin + 1}))
        call({'action': 'usb-outcomes', 'path': str(args.tape.resolve())})
        require(state()['usb']['replay_horizon'] == end,
                'full tape has a different authoritative horizon')
        errors.append(rejected({'action': 'run', 'cycles': end - begin + 1}))
        call({'action': 'snapshot', 'path': str(out / 'restored')})
        require(sha(out / 'restored/machine.chk') == sha(args.snapshot / 'machine.chk'),
                'restore or tape admission mutated authoritative checkpoint bytes')
        for row in rows:
            advance(row['cycle']); call(row['request'])
        advance(end)
        call({'action': 'snapshot', 'path': str(out / 'private-final')})
        require(sha(out / 'private-final/machine.chk') == sha(args.final_snapshot / 'machine.chk'),
                'recorded exact suffix checkpoint differs')
        events = guest_events(directory / 'uart.bin')
        if args.expect_failed_save is not None:
            require(any(row[0:2] == (0x424, args.expect_failed_save) for row in events),
                    'actual suffix did not reproduce the required failed Save')
        call({'action': 'destroy'}); process.wait(timeout=10)
        require(process.returncode == 0, 'private owner did not terminate cleanly')
        report.update(status='PASS', exact_every_snapshot_byte=True,
                      rejections_before_advance=errors, actual_recorded_raw_admissions=rows,
                      actual_suffix_uart=events, private_pid=process.pid)
    except BaseException as error: report['error'] = repr(error)
    finally:
        if process is not None and process.poll() is None:
            try: call({'action': 'destroy'}); process.wait(timeout=10)
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
        if log is not None: log.close()
        report.update(host_seconds=time.monotonic() - started, observer_sha256=sha(__file__),
                      private_exit_code=process.returncode if process else None)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
