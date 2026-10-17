#!/usr/bin/env python3
"""Actual packaged ROM protocol continuation with a partially received frame.

Uses an existing local bundle, blank private BootNV and genuine Lean ROM. No
kernel preload, notebook recovery or general checkpoint/timing claim is made.
"""
from pathlib import Path
import argparse
import ctypes
import filecmp
import hashlib
import json
import os
import resource
import signal
import struct
import subprocess
import sys
import time
import zlib

import lemmasim_auth as auth
from supervise_usb_notebook import descendants, identity

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    bundle, out = args.bundle.resolve(), args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        raise ValueError('unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
        raise RuntimeError('owned descendant reaping unavailable')
    started = time.monotonic()
    deadline = started + 600
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda code, frame: (_ for _ in ()).throw(SystemExit(128 + code)))
    processes, tracked = [], {}
    host_inputs = {}
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.suffix == '.py' and path.is_relative_to(ROOT):
                host_inputs[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'status': 'RUNNING', 'scope': __doc__, 'commands': [],
              'bounds': {'host_seconds': 600, 'per_process_AS_bytes': 4 << 30,
                         'file_bytes': 1 << 30, 'suffix_clocks': 200000,
                         'whole_RTL_clocks': 10000000, 'automatic_restart': False,
                         'sampled_owned_RSS_bytes': 2 << 30, 'minimum_available_bytes': 2 << 30,
                         'output_bytes': 2 << 30}, 'host_inputs': host_inputs,
              'bundle_manifest_sha256': hashlib.sha256((bundle / 'bundle.json').read_bytes()).hexdigest()}
    (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        if time.monotonic() >= deadline:
            raise TimeoutError('original whole host deadline')
        if any(hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest for name, digest in host_inputs.items()):
            raise RuntimeError('consumed host observer changed')
        for process, _ in processes:
            for row in descendants(process.pid):
                tracked[row['pid']] = row
        rss = 0
        for row in tracked.values():
            if identity(row['pid']) == row:
                try:
                    rss += int(Path('/proc', str(row['pid']), 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
                except FileNotFoundError:
                    pass
        report['sampled_owned_peak_RSS_bytes'] = max(report.get('sampled_owned_peak_RSS_bytes', 0), rss)
        available = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if rss > 2 << 30 or available < 2 << 30:
            raise RuntimeError('original sampled memory bound')
        if sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) > 2 << 30:
            raise RuntimeError('original2GiB output ceiling')

    def command(name, argv):
        guard()
        with (out / (name + '.log')).open('xb') as log:
            result = subprocess.run([sys.executable, '-I', str(bundle / 'run.py'), *argv],
                cwd='/tmp', stdout=log, stderr=subprocess.STDOUT,
                timeout=min(120, deadline - time.monotonic()))
        report['commands'].append({'name': name, 'returncode': result.returncode})
        if result.returncode:
            raise RuntimeError('packaged command failed: ' + name)
        return (out / (name + '.log')).read_text()

    def control(live, name, request):
        return json.loads(command(name, ['control', '--session-dir', str(live),
                                        '--request', json.dumps(request)]))

    def launch(name, restore=None):
        live = out / name
        argv = ['--public-development-key', 'launch', '--session-dir', str(live),
                '--mode', 'developer', '--paused', '--headless', '--host-threads', '1']
        argv += ['--boot-medium', str(out / 'boot.raw'), '--recovery'] if restore is None else ['--restore', str(restore)]
        with (out / (name + '-launch.log')).open('xb') as log:
            process = subprocess.Popen([sys.executable, '-I', str(bundle / 'run.py'), *argv],
                cwd='/tmp', stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((process, live))
        until = min(deadline, time.monotonic() + 120)
        while not (live / 'session.json').is_file():
            guard()
            if process.poll() is not None or time.monotonic() >= until:
                raise RuntimeError('actual packaged session launch failed')
            time.sleep(.1)
        return live

    def close(live, name):
        process = next(p for p, session in processes if session == live)
        control(live, name, {'action': 'destroy'})
        process.wait(timeout=10)
        if process.returncode:
            raise RuntimeError('packaged owner did not exit cleanly')
        processes.remove((process, live))

    try:
        command('create', ['--public-development-key', 'create-medium', '--boot-medium', str(out / 'boot.raw')])
        before = hashlib.sha256((out / 'boot.raw').read_bytes()).hexdigest()
        live = launch('original')
        zero = control(live, 'CPU0', {'action': 'inspect'})['machine']
        if (zero['cycle'], zero['pc'], zero['retired']) != (0, 0, 0):
            raise RuntimeError('fresh immutable-ROM CPU0 absent')
        capacity = json.loads(command('capacity', ['--public-development-key', 'capacity',
            '--session-dir', str(live), '--cycles', '10000000', '--timeout', '120', '--transaction', '100']))
        if capacity['receipts'] != [{'transaction': 100, 'status': 0, 'value': 0x200010008}]:
            raise RuntimeError('actual development ROM capacity differs')
        # A real request crosses guest RAM parser state and future raw UART
        # admission. No debugger memory writes, fences, drain or flush.
        wire = auth.frame(101, 0)
        control(live, 'partial-admission', {'action': 'inject', 'kind': 'uart', 'hex': wire[:37].hex()})
        control(live, 'partial-run', {'action': 'run', 'cycles': 100000})
        prefix = (live / 'uart.bin').read_bytes()
        if len(prefix) != 80:
            raise RuntimeError('partial request received an unexpected reply')
        state = control(live, 'partial-state', {'action': 'inspect'})['machine']
        control(live, 'future-admission', {'action': 'inject', 'kind': 'uart',
            'cycle': state['cycle'] + 50000, 'hex': wire[37:].hex()})
        cut = control(live, 'queued-state', {'action': 'inspect'})['machine']
        if cut['cycle'] != state['cycle'] or not (cut['event_queue'] or cut['uart_queue']):
            raise RuntimeError('actual future UART work was not retained before cut')
        control(live, 'pending-snapshot', {'action': 'snapshot', 'path': str(out / 'pending')})
        if control(live, 'unchanged-after-snapshot', {'action': 'inspect'})['machine'] != cut:
            raise RuntimeError('observational snapshot mutated machine')
        control(live, 'original-suffix', {'action': 'run', 'cycles': 200000})
        control(live, 'original-final', {'action': 'snapshot', 'path': str(out / 'original-final')})
        original_state = control(live, 'original-state', {'action': 'inspect'})['machine']
        suffix = (live / 'uart.bin').read_bytes()[len(prefix):]
        if len(suffix) != 40:
            raise RuntimeError('missing actual complete suffix response')
        # Independent little-endian/CRC decoder of the guest reply, separate
        # from the ROM and maintained recovery client's receipt parser.
        response, transaction, status, value, crc = struct.unpack('<5Q', suffix)
        if (response, transaction, status, value) != (0x3154504345524d4c, 101, 0, 0x200010008) or crc != zlib.crc32(suffix[:32]):
            raise RuntimeError('actual guest suffix receipt differs')
        close(live, 'original-destroy')
        fork = launch('private-fork', out / 'pending')
        restored = control(fork, 'restored-boundary', {'action': 'inspect'})['machine']
        if restored['cycle'] != cut['cycle']:
            raise RuntimeError('private restore advanced boundary')
        control(fork, 'fork-suffix', {'action': 'run', 'cycles': 200000})
        control(fork, 'fork-final', {'action': 'snapshot', 'path': str(out / 'fork-final')})
        if not filecmp.cmp(out / 'original-final/machine.chk', out / 'fork-final/machine.chk', shallow=False):
            raise RuntimeError('complete authoritative pending-protocol suffix differs')
        envelope_keys = ('identity', 'boundary', 'automatic', 'quantum', 'external_event_cursor',
                         'virtual_cycle', 'virtual_ns', 'medium_policy', 'files')
        original_envelope = json.loads((out / 'original-final/snapshot.json').read_text())
        fork_envelope = json.loads((out / 'fork-final/snapshot.json').read_text())
        if any(original_envelope[key] != fork_envelope[key] for key in envelope_keys):
            raise RuntimeError('session authority or external-event cursor differs')
        if (fork / 'uart.bin').read_bytes() != suffix:
            raise RuntimeError('actual applicable guest UART suffix differs')
        control(fork, 'fork-boot-export', {'action': 'export-boot-medium', 'path': str(out / 'fork-boot.raw')})
        close(fork, 'fork-destroy')
        if before != hashlib.sha256((out / 'boot.raw').read_bytes()).hexdigest() or not filecmp.cmp(out / 'boot.raw', out / 'fork-boot.raw', shallow=False):
            raise RuntimeError('original/private medium differs')
        command('verify-after', ['--verify-only'])
        if hashlib.sha256((bundle / 'bundle.json').read_bytes()).hexdigest() != report['bundle_manifest_sha256']:
            raise RuntimeError('immutable bundle changed')
        report.update(status='PASS_BUNDLED_ROM_PARTIAL_FRAME_QUEUED_UART_EXACT_PRIVATE_SUFFIX',
            cut=cut, final=original_state, original_RTL_clocks=original_state['cycle'],
            fork_suffix_clocks=200000, suffix_bytes=len(suffix),
            complete_checkpoint_bytes=(out / 'original-final/machine.chk').stat().st_size,
            full_authoritative_checkpoint_equal=True, original_and_private_boot_equal=True,
            equal_session_envelope_keys=envelope_keys)
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        for process, live in processes:
            try:
                auth.sessions.request(live, {'action': 'destroy'}, 5)
                process.wait(timeout=10)
            except BaseException as error:
                report.setdefault('cleanup_errors', []).append(repr(error))
        until = time.monotonic() + 20
        while True:
            remaining = [row for row in tracked.values() if identity(row['pid']) == row]
            if not remaining:
                break
            for row in remaining:
                try:
                    os.kill(row['pid'], signal.SIGTERM if time.monotonic() < until else signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if time.monotonic() >= until + 5:
                report['owned_survivors'] = remaining
                report['status'] = 'FAIL'
                break
            time.sleep(.1)
            while True:
                try:
                    if os.waitpid(-1, os.WNOHANG)[0] == 0:
                        break
                except ChildProcessError:
                    break
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
