#!/usr/bin/env python3
"""Real authenticated guest installation, two brownouts and stalled-trial
watchdog expiry -> ROM attempt-limit fallback -> known notebook recovery.
All media are private copies. The intentionally unhealthy trial is the existing
audited Lean CryptoProbe, whose maintained generated startup ends in WFI. Its
cryptographic self-test is not OS health. No image/document is host-installed.
Public development key only; production trust and the full failure matrix open.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import filecmp
import json
import resource
import shutil
import struct
import subprocess
import sys
import time

import lemmasim_auth as auth
import lemmasim_session as sessions
import development_install
from check_development_install_resume import metadata
from check_live_notebook import guest_events, visible_pixels
from product_native import sha

ROOT = Path(__file__).resolve().parents[1]
END = struct.pack('<Q', 0x31444e45414d454c)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'boot-medium', 'disk', 'known-package', 'package', 'tag', 'expected-home', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    deadline = started + 32400
    cap = 4_000_000_000
    processes = []
    report = {'status': 'RUNNING', 'scope': __doc__, 'phases': [],
              'bounds': {'seconds': 32400, 'RTL_clocks': cap, 'arm_clocks': 300000000,
                         'arm_seconds': 2400, 'watchdog_wait_seconds': 24000,
                         'fallback_clocks': 1500000000, 'fallback_seconds': 11200,
                         'per_process_AS_bytes': 4 << 30, 'file_bytes': 1 << 30},
              'checkpoint_status': 'NOT_RUN', 'functional_status': 'NOT_RUN'}

    def save():
        report['seconds'] = time.monotonic() - started
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() < deadline, 'prospective whole deadline')
        require(all(sha(ROOT / name) == digest for name, digest in report['host_inputs'].items()), 'host source drift')

    def call(live, request):
        guard()
        return sessions.request(live, request, 120)

    def state(live):
        value = call(live, {'action': 'inspect'})['machine']
        require(not value['finished'] and value['cycle'] <= cap, 'guest finish/whole RTL ceiling')
        return value

    def run(live, cycles):
        before = state(live)['cycle']
        require(cycles > 0 and before + cycles <= cap, 'prospective RTL run bound')
        call(live, {'action': 'run', 'cycles': cycles})
        value = state(live)
        require(value['cycle'] == before + cycles, 'exact RTL clocks')
        return value

    def launch(name, *, restore=None):
        live = out / name
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'), '--public-development-key',
                'launch', '--prepared', str(args.prepared.resolve()), '--session-dir', str(live),
                '--paused', '--headless', '--mode', 'laboratory', '--timeout', '120', '--host-threads', '1']
        if restore is None:
            argv += ['--boot-medium', str(out / 'boot.raw'), '--disk', str(out / 'user.raw'), '--recovery']
        else:
            argv += ['--restore', str(restore)]
        with (out / (name + '-launch.log')).open('xb') as stream:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((process, live))
        end = time.monotonic() + 30
        while not (live / 'session.json').exists():
            require(process.poll() is None and time.monotonic() < end, 'actual ROM session launch failed')
            time.sleep(.05)
        return live

    def close(live):
        process = next(p for p, path in processes if path == live)
        call(live, {'action': 'destroy'})
        process.wait(timeout=10)
        require(process.returncode == 0, 'owned session exit failed')
        processes.remove((process, live))

    def boot_bytes(live, name):
        path = out / (name + '.raw')
        call(live, {'action': 'export-boot-medium', 'path': str(path)})
        return path.read_bytes()

    def await_trial(live, attempt, cursor):
        initial = state(live)['cycle']
        began = time.monotonic()
        while True:
            value = state(live)
            require(value['cycle'] - initial <= 300000000 and time.monotonic() - began <= 2400,
                    'prospective authenticated trial/terminal bound')
            uart = (live / 'uart.bin').read_bytes()
            require(len(uart) >= cursor, 'UART capture unexpectedly truncated on reset')
            if value['power']['watchdog_armed'] == 1 and uart[cursor:].endswith(END):
                break
            run(live, 1000000)
        raw = boot_bytes(live, 'attempt-' + str(attempt))
        require(metadata(raw)[3:8] == (1, 0x000a000000000013, 0, 1001, attempt),
                'guest attempt publication/confirmed image differs')
        require(raw[32776*512:32776*512+len(known_wire)] == known_wire,
                'installation/attempt changed known notebook payload')
        # Observe a real quiescent WFI interval, not a debugger-modified CPU.
        before = run(live, 1000000)
        after = run(live, 1000000)
        require(before['power']['watchdog_remaining'] - after['power']['watchdog_remaining'] == 1000000,
                'independent watchdog did not count actual guest clocks')
        report['phases'].append({'name': 'authenticated-unhealthy-trial-' + str(attempt),
                                'cycle': after['cycle'], 'power': after['power'],
                                'quiescent_retired_delta': after['retired'] - before['retired'],
                                'actual_CryptoProbe_terminal_observed': True})
        save()
        return after

    try:
        prepared, _, _ = auth.prepared(args.prepared)
        require(auth.watchdog_policy(prepared), 'versioned watchdog ROM required')
        package, wire, tag = development_install.load_package(args.package, args.tag, sha)
        require(package['identity'] == 1001 and len(wire) == 22*512, 'fixed genuine unhealthy CryptoProbe required')
        source = Path(package['source'])
        source_result = source.parent.parent / 'result.json'
        require(sha(source) == package['source_sha256'] and sha(source_result) == package['source_result_sha256'] and
                json.loads(source_result.read_text())['status'] == 'PASS_GENUINE_RV64_SHA256_HMAC_COMPONENT',
                'genuine audited trial source differs')
        known = json.loads((args.known_package / 'package.json').read_text())
        known_wire = (args.known_package / 'image.bin').read_bytes()
        require(known['identity'] == 0x000a000000000013 and sha(args.known_package / 'image.bin') == known['image_sha256'],
                'fixed previously qualified known notebook13 package required')
        initial_boot = args.boot_medium.read_bytes()
        require(metadata(initial_boot)[3:8] == (1, known['identity'], 2, 0, 0) and
                initial_boot[32776*512:32776*512+len(known_wire)] == known_wire, 'actual confirmed/no-trial source differs')
        report['original_inputs'] = {str(p.resolve()): sha(p) for p in
            (args.boot_medium, args.disk, args.expected_home, args.package / 'image.bin', args.tag,
             args.known_package / 'image.bin')}
        report['host_inputs'] = {**prepared['host_scripts'], 'scripts/lemmasim-auth': sha(ROOT / 'scripts/lemmasim-auth'),
                                 str(Path(__file__).relative_to(ROOT)): sha(Path(__file__))}
        report['prepared_sha256'] = sha(args.prepared / 'prepared.json')
        shutil.copyfile(args.boot_medium, out / 'boot.raw')
        shutil.copyfile(args.disk, out / 'user.raw')
        live = launch('trial')
        require(state(live)['cycle'] == 0, 'new immutable-ROM CPU0 required')
        client = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=2400, cycles=300000000,
                                                     quantum=100000, transaction=100))
        report['beacon'] = client.beacon()
        auth.product.install_extent(package, wire, client.call({'action': 'inspect'})['identity'])
        for index in range(22):
            require(client.send(1, 0, index, 1001, wire[index*512:(index+1)*512])['status'] == 0,
                    'real inactive payload WRITE/BARRIER failed')
        require(client.send(5, 0, 0, 1001, tag)['status'] == 0, 'real tag publication failed')
        require(client.send(2, 0, 0, 1001)['status'] == 0, 'real authenticated trial metadata publication failed')
        report['installed_metadata'] = list(metadata(boot_bytes(live, 'installed')))
        cursor = (live / 'uart.bin').stat().st_size
        require(client.send(3)['status'] == 0, 'actual trial boot command failed')
        save()
        for attempt in (1, 2, 3):
            value = await_trial(live, attempt, cursor)
            if attempt < 3:
                cursor = (live / 'uart.bin').stat().st_size
                call(live, {'action': 'inject', 'kind': 'brownout', 'level': 1})
                unsafe = run(live, 200)
                require(unsafe['power']['reset_cause'] == 5 and unsafe['power']['domain_reset'] == 1 and
                        unsafe['power']['watchdog_armed'] == 0, 'actual brownout cancellation/reset boundary differs')
                call(live, {'action': 'inject', 'kind': 'brownout', 'level': 0})
                run(live, 8)
        began = time.monotonic()
        wait_start = value
        while value['power']['watchdog_remaining'] > 1:
            require(time.monotonic() - began <= 24000, 'prospective stalled watchdog host bound')
            require(value['power']['watchdog_armed'] == 1, 'trial watchdog unexpectedly disarmed')
            value = run(live, min(1000000, value['power']['watchdog_remaining'] - 1))
            if value['cycle'] % 50000000 == 0:
                report['watchdog_wait'] = {'initial': wait_start, 'current': value, 'seconds': time.monotonic() - began}
                save()
        require(value['power']['watchdog_armed'] == 1 and value['power']['watchdog_remaining'] == 1,
                'exact before-expiry boundary absent')
        snapshot = out / 'before-watchdog-expiry'
        call(live, {'action': 'snapshot', 'path': str(snapshot)})
        require(state(live) == value, 'snapshot mutated the supervised machine')
        edge = run(live, 1)
        require(edge['power']['reset_cause'] == 4 and edge['power']['reset_remaining'] == 8 and
                edge['power']['watchdog_armed'] == 0, 'actual watchdog expiry/reset edge differs')
        require(run(live, 7)['power']['reset_remaining'] == 1 and
                run(live, 1)['power']['reset_remaining'] == 0, 'exact eight-cycle reset duration differs')
        run(live, 55)
        end_snapshot = out / 'after-reset64'
        call(live, {'action': 'snapshot', 'path': str(end_snapshot)})
        fork = launch('private-reset-fork', restore=snapshot)
        require(state(fork)['cycle'] == value['cycle'], 'private fork changed exact boundary')
        run(fork, 64)
        fork_snapshot = out / 'fork-after-reset64'
        call(fork, {'action': 'snapshot', 'path': str(fork_snapshot)})
        require(filecmp.cmp(end_snapshot / 'machine.chk', fork_snapshot / 'machine.chk', shallow=False),
                'whole authoritative reset-edge suffix differs')
        close(fork)
        report['checkpoint_status'] = 'PASS_EXACT_PRIVATE_64_CLOCK_WATCHDOG_RESET_SUFFIX'
        report['watchdog_expiry'] = {'before': value, 'edge': edge, 'after64': state(live),
                                     'wait_seconds': time.monotonic() - began,
                                     'quiescent_retired_delta': value['retired'] - wait_start['retired']}
        save()
        initial = state(live)['cycle']
        began = time.monotonic()
        while True:
            value = state(live)
            require(value['cycle'] - initial <= 1500000000 and time.monotonic() - began <= 11200,
                    'original full notebook cold/fallback ceiling')
            rows = guest_events(live / 'uart.bin')
            require(not any(row[0] in (0x41f, 0x424, 0xd4, 0xf4, 0x454) for row in rows), 'actual known notebook failure')
            if (any(row[0] == 0x420 for row in rows) and value['panel_completed'] >= 1 and
                    all(value[k] == 0 for k in ('event_queue', 'pen_queue', 'paper_busy', 'panel_pending_pixels', 'block_state', 'dma_outstanding'))):
                path = out / 'fallback-observed.ppm'
                call(live, {'action': 'panel', 'path': str(path)})
                if visible_pixels(path) == visible_pixels(args.expected_home): break
            run(live, 1000000)
        require(value['power']['watchdog_armed'] == 0, 'confirmed fallback unexpectedly supervised as a trial')
        final_boot = boot_bytes(live, 'fallback-boot')
        require(metadata(final_boot)[3:8] == (1, known['identity'], 0, 1001, 3) and
                final_boot[32776*512:32776*512+len(known_wire)] == known_wire, 'actual attempt-limit fallback/known bytes differ')
        exported = out / 'fallback-user.raw'
        call(live, {'action': 'export-medium', 'path': str(exported)})
        require(filecmp.cmp(args.disk, exported, shallow=False), 'fallback changed an acknowledged user-media byte')
        close(live)
        require(all(sha(Path(p)) == digest for p, digest in report['original_inputs'].items()), 'original inputs changed')
        report.update(status='PASS_GUEST_AUTHENTICATED_TRIAL_WATCHDOG_BROWNOUT_FALLBACK_NOTEBOOK',
                      functional_status='PASS', all_home_pixels=3630000, all_user_bytes=268435456,
                      fallback_clocks=value['cycle'] - initial, actual_guest_recovery=True,
                      scope_limit='Unhealthy authenticated trial only; healthy watchdog confirmation, loader-hang supervision, full interruption matrix, production identity/entropy/antirollback remain open.')
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        for process, live in list(processes):
            try: call(live, {'action': 'destroy'}); process.wait(timeout=10)
            except BaseException as error:
                report.setdefault('cleanup_errors', []).append(repr(error))
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=10)
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
