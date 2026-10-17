#!/usr/bin/env python3
"""Partial inactive notebook payload -> real brownout -> independent ROM cold
boot of the confirmed notebook, preserving every acknowledged document byte.

Sixteen actual WRITE/BARRIER transactions precede interruption. No tag or trial
metadata is published. This qualifies an interruption between sector barriers,
not an in-flight write, metadata/confirmation interruption or production trust.
"""
import argparse
import filecmp
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import development_install
import lemmasim_auth as auth
import lemmasim_session as sessions
from check_development_install_resume import metadata
from check_live_notebook import guest_events, visible_pixels
from product_native import sha

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('prepared', 'known-package', 'package', 'tag', 'boot-medium',
                 'disk', 'expected-home', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    args = parser.parse_args()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda code, frame: (_ for _ in ()).throw(SystemExit(128 + code)))
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    for key, amount in ((resource.RLIMIT_AS, 4 << 30), (resource.RLIMIT_FSIZE, 1 << 30),
                        (resource.RLIMIT_CORE, 0)):
        resource.setrlimit(key, (amount, amount))
    began = time.monotonic()
    deadline = began + 14400
    used = 0
    processes = []
    report = {'schema': 'lemma-interrupted-notebook-update/1', 'status': 'RUNNING',
              'scope': __doc__, 'phases': [], 'bounds': {'whole_seconds': 14400,
              'aggregate_RTL_clocks': 1800000000, 'partial_clocks': 300000000,
              'partial_seconds': 2400, 'cold_clocks': 1500000000,
              'cold_seconds': 11200, 'per_process_AS_bytes': 4 << 30,
              'file_bytes': 1 << 30, 'automatic_restart': False}}

    def save():
        report.update(seconds=time.monotonic() - began, clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() < deadline and used <= 1800000000, 'prospective whole bound')
        require(all(sha(ROOT / path) == digest for path, digest in report['host_inputs'].items()),
                'consumed host source changed')

    def call(live, request):
        guard()
        return sessions.request(live, request, 120)

    def launch(name, recovery):
        live = out / name
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'), '--public-development-key',
                'launch', '--prepared', str(args.prepared.resolve()), '--session-dir', str(live),
                '--boot-medium', str(out / 'boot.raw'), '--disk', str(out / 'user.raw'),
                '--paused', '--headless', '--mode', 'laboratory', '--timeout', '120',
                '--host-threads', '1']
        if recovery:
            argv.append('--recovery')
        with (out / (name + '.log')).open('xb') as stream:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        processes.append((process, live))
        until = time.monotonic() + 30
        while not (live / 'session.json').is_file():
            require(process.poll() is None and time.monotonic() < until, 'actual ROM session launch failed')
            time.sleep(.05)
        state = call(live, {'action': 'inspect'})['machine']
        require(state['cycle'] == 0 and state['power']['reset_epoch'] == 0,
                'independent immutable-ROM CPU0 required')
        report['phases'].append({'name': name + '-CPU0', 'state': state})
        return live

    def close(live):
        process = next(p for p, path in processes if path == live)
        call(live, {'action': 'destroy'})
        process.wait(timeout=10)
        require(process.returncode == 0, 'owned session did not close cleanly')
        processes.remove((process, live))

    def boot_bytes(live, name):
        path = out / (name + '.raw')
        call(live, {'action': 'export-boot-medium', 'path': str(path)})
        return path.read_bytes()

    try:
        prepared, _, _ = auth.prepared(args.prepared)
        require(auth.watchdog_policy(prepared), 'exact current schema2 ROM required')
        package, wire, _ = development_install.load_package(args.package, args.tag, sha)
        require(package['identity'] == 0x000a000000000015 and len(wire) == 1059 * 512
                and package['image_sha256'] == 'db89cf1549d4b04894079c49c103151da327b1192386ebf5f2b8c9eb4c0998ca',
                'fixed audited1059-sector notebook15 package required')
        known = json.loads((args.known_package / 'package.json').read_text())
        known_wire = (args.known_package / 'image.bin').read_bytes()
        require(known['status'] == 'PASS' and known['identity'] == 0x000a000000000013
                and sha(args.known_package / 'image.bin') == known['image_sha256'] ==
                    '23c28a549c1144e05a81ec9f4d682e9a5a8320a8d39205ac164ed687251afdc1',
                'fixed previously qualified confirmed notebook13 package required')
        original = args.boot_medium.read_bytes()
        old_metadata = metadata(original)
        require(old_metadata[3:8] == (1, known['identity'], 2, 0, 0)
                and original[32776 * 512:32776 * 512 + len(known_wire)] == known_wire,
                'actual confirmed/no-trial source differs')
        require(visible_pixels(args.expected_home)[:2] == (1650, 2200)
                and args.disk.stat().st_size == 268435456, 'canonical complete references required')
        report['host_inputs'] = {**prepared['host_scripts']}
        for name in ('scripts/lemmasim-auth', 'scripts/check_development_install_resume.py',
                     'scripts/check_live_notebook.py', str(Path(__file__).relative_to(ROOT))):
            report['host_inputs'][name] = sha(ROOT / name)
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                source = Path(name).resolve()
                if source.suffix == '.py' and source.is_relative_to(ROOT):
                    relative = source.relative_to(ROOT)
                    if relative.parts[0] in ('scripts', 'conformance'):
                        report['host_inputs'][str(relative)] = sha(source)
        report['original_inputs'] = {str(path.resolve()): sha(path) for path in
            (args.boot_medium, args.disk, args.expected_home, args.known_package / 'package.json',
             args.known_package / 'image.bin', args.package / 'package.json',
             args.package / 'image.bin', args.tag)}
        report['prepared_sha256'] = sha(args.prepared / 'prepared.json')
        shutil.copyfile(args.boot_medium, out / 'boot.raw')
        shutil.copyfile(args.disk, out / 'user.raw')
        live = launch('partial', True)
        client = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=2400,
            cycles=299999800, quantum=100000, transaction=100))
        report['beacon'] = client.beacon()
        auth.product.install_extent(package, wire, client.call({'action': 'inspect'})['identity'])
        receipts = []
        for index in range(16):
            row = client.send(1, 0, index, package['identity'], wire[index * 512:(index + 1) * 512])
            require(row['status'] == 0, 'actual inactive payload WRITE/BARRIER failed')
            receipts.append(row)
        status = client.send(4, 0, identity=package['identity'])
        require(status['status'] == 217 and status['value'] == 0,
                'incomplete untagged payload obtained an installation receipt')
        used += client.used
        require(used <= 300000000 and time.monotonic() - began <= 2400,
                'prospective partial-transfer bound')
        partial = boot_bytes(live, 'actual-partial')
        start, end = 8 * 512, (8 + 16) * 512
        require(partial[:start] == original[:start] and partial[start:end] == wire[:16 * 512]
                and partial[end:] == original[end:] and metadata(partial) == old_metadata,
                'actual partial staging altered metadata, known image or bytes outside16sectors')
        before = call(live, {'action': 'inspect'})['machine']
        call(live, {'action': 'inject', 'kind': 'brownout', 'level': 1})
        call(live, {'action': 'run', 'cycles': 200})
        used += 200
        unsafe = call(live, {'action': 'inspect'})['machine']
        require(used <= 300000000 and time.monotonic() - began <= 2400,
                'prospective partial-transfer/reset bound')
        require(unsafe['cycle'] == before['cycle'] + 200 and unsafe['power']['domain_reset'] == 1
                and unsafe['power']['reset_cause'] == 5 and unsafe['power']['watchdog_armed'] == 0
                and unsafe['boot_backing']['reset_origin'] > before['boot_backing']['reset_origin'],
                'actual brownout cancellation/reset origin differs')
        require(boot_bytes(live, 'actual-brownout') == partial,
                'brownout changed acknowledged staging or confirmed metadata')
        report['partial'] = {'receipts': receipts, 'uninstalled_status': status,
                             'before': before, 'brownout': unsafe, 'sectors': 16}
        save()
        close(live)
        require((out / 'boot.raw').read_bytes() == partial and
                filecmp.cmp(args.disk, out / 'user.raw', shallow=False),
                'destroy after brownout changed observed persistence or user media')
        # Fresh CPU and power origin. Only the real observed BootNV/user media
        # survive; no checkpoint, recovery UART request or target RAM preload.
        cold = launch('independent-normal-cold', False)
        cold_started = time.monotonic()
        while True:
            state = call(cold, {'action': 'inspect'})['machine']
            require(state['cycle'] <= 1500000000 and time.monotonic() - cold_started <= 11200,
                    'original known-notebook cold bound')
            rows = guest_events(cold / 'uart.bin')
            require(not state['finished'] and not state['power']['watchdog_armed'] and
                    not any(row[0] in (0x41f, 0x424, 0xd4, 0xf4, 0x454) for row in rows),
                    'actual confirmed notebook failed or incomplete trial was selected')
            idle = all(state[k] == 0 for k in ('event_queue', 'pen_queue', 'uart_queue',
                       'paper_busy', 'panel_pending_pixels', 'block_state', 'dma_outstanding'))
            if idle and state['panel_completed'] and any(row[0] == 0x420 for row in rows):
                panel = out / 'recovered-home.ppm'
                call(cold, {'action': 'panel', 'path': str(panel)})
                if visible_pixels(panel) == visible_pixels(args.expected_home):
                    break
            require(state['cycle'] < 1500000000, 'original cold clock ceiling')
            amount = min(1000000, 1500000000 - state['cycle'])
            call(cold, {'action': 'run', 'cycles': amount})
            used += amount
            if state['cycle'] % 50000000 == 0:
                report['cold_progress'] = {'cycle': state['cycle'] + amount,
                                          'seconds': time.monotonic() - cold_started}
                save()
        call(cold, {'action': 'export-medium', 'path': str(out / 'recovered-user.raw')})
        require(filecmp.cmp(args.disk, out / 'recovered-user.raw', shallow=False)
                and boot_bytes(cold, 'recovered-boot') == partial,
                'normal cold recovery changed acknowledged documents, metadata or staging')
        report['phases'].append({'name': 'confirmed-notebook-cold-Ready', 'state': state,
                                  'seconds': time.monotonic() - cold_started})
        close(cold)
        guard()
        require(all(sha(Path(path)) == digest for path, digest in report['original_inputs'].items()),
                'original immutable inputs changed')
        report.update(status='PASS_PARTIAL_NOTEBOOK_UPDATE_BROWNOUT_INDEPENDENT_CONFIRMED_COLD',
                      all_home_pixels=3630000, all_user_bytes=268435456,
                      qualification='Between-barrier payload interruption only; no full update-interruption matrix or production trust claim')
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        for process, live in list(processes):
            try:
                sessions.request(live, {'action': 'destroy'}, 5)
                process.wait(timeout=5)
            except BaseException as error:
                report.setdefault('cleanup_errors', []).append(repr(error))
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
        report.update(seconds=time.monotonic() - began, clocks=used)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
