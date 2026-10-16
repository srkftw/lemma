#!/usr/bin/env python3
"""Guest A/B installation -> actual trial notebook -> guest health confirmation
-> independent authenticated cold recovery, preserving every document byte.
Reuses the audited Product10 notebook; no fresh compilation/latest-course,
interrupted confirmation, watchdog, production-key or browser claim.
"""
import argparse
import filecmp
import hashlib
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

import lemmasim_auth as auth
import lemmasim_session as sessions
from check_development_auth_notebook import expected_home, guest_events, visible_pixels
from check_development_install_resume import metadata
from package_product_image import package as validate_package
from product_native import sha

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from store_oracle import recover


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'guest-build', 'guest-source-archive', 'package',
                 'tag', 'boot-medium', 'disk', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir()
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    began = time.monotonic()
    deadline = began + 21600
    used = 0
    processes = []
    report = {'status': 'RUNNING', 'scope': __doc__, 'phases': [],
              'bounds': {'whole_seconds': 21600, 'clocks': 3_500_000_000,
                         'install_clocks': 600_000_000, 'install_seconds': 3600,
                         'handoff_clocks': 200_000_000, 'handoff_seconds': 1800,
                         'ready_clocks': 1_100_000_000, 'ready_seconds': 7200,
                         'cold_clocks': 1_300_000_000, 'cold_seconds': 7200,
                         'automatic_restart': False}}

    def save():
        report.update(seconds=time.monotonic() - began, clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() < deadline and used <= 3_500_000_000, 'original whole bound')
        require(all(sha(ROOT / p) == h for p, h in report['host_inputs'].items()), 'consumed host changed')

    def call(live, value):
        guard()
        return sessions.request(live, value, 120)

    def launch(name, boot, disk, recovery):
        live = out / name
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'), '--public-development-key',
                'launch', '--prepared', str(args.prepared.resolve()), '--session-dir', str(live),
                '--boot-medium', str(boot), '--disk', str(disk), '--paused', '--headless',
                '--mode', 'laboratory', '--timeout', '120', '--host-threads', '1']
        if recovery:
            argv += ['--recovery']
        with (out / (name + '.log')).open('xb') as log:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        processes.append((process, live))
        until = time.monotonic() + 30
        while not (live / 'session.json').is_file():
            require(process.poll() is None and time.monotonic() < until, 'new immutable-ROM CPU did not open')
            time.sleep(.05)
        require(call(live, {'action': 'inspect'})['machine']['cycle'] == 0, 'fresh CPU did not start at0')
        return live

    def close(live):
        process = next(p for p, d in processes if d == live)
        call(live, {'action': 'destroy'})
        process.wait(timeout=10)
        require(process.returncode == 0, 'actual session did not close cleanly')
        processes.remove((process, live))

    def ready(live, name, cap, confirm):
        nonlocal used
        initial = call(live, {'action': 'inspect'})['machine']['cycle']
        started = time.monotonic()
        while True:
            guard()
            state = call(live, {'action': 'inspect'})['machine']
            delta = state['cycle'] - initial
            require(0 <= delta <= cap and time.monotonic() - started <= 7200,
                    'original cold/Ready clock or host bound: ' + name)
            rows = guest_events(live / 'uart.bin')
            health = [r for r in rows if r[0] == 0x473]
            require(not state['finished'] and not any(r[0] in (0x41f, 0xd4, 0xf4, 0x424) for r in rows)
                    and all(r[1] == 0 for r in health), 'actual guest/confirmation failure')
            idle = all(state[k] == 0 for k in ('event_queue', 'pen_queue', 'uart_queue',
                       'paper_busy', 'panel_pending_pixels', 'block_state', 'dma_outstanding'))
            if idle and state['panel_completed'] and any(r[0] == 0x420 for r in rows) and (health or not confirm):
                panel = out / (name + '.ppm')
                call(live, {'action': 'panel', 'path': str(panel)})
                if visible_pixels(panel) == (1650, 2200, expected):
                    report['phases'].append({'name': name, 'initial_cycle': initial,
                        'final_cycle': state['cycle'], 'clocks': delta,
                        'seconds': time.monotonic() - started, 'health_records': health})
                    save()
                    return state
            require(delta < cap and used < 3_500_000_000, 'original clock ceiling: ' + name)
            quantum = min(1_000_000, cap - delta, 3_500_000_000 - used)
            call(live, {'action': 'run', 'cycles': quantum})
            used += quantum
            with (out / 'progress.jsonl').open('a') as stream:
                stream.write(json.dumps({'phase': name, 'cycle': state['cycle'] + quantum,
                                        'host_seconds': time.monotonic() - started}) + '\n')

    try:
        prepared, _, _ = auth.prepared(args.prepared)
        report['host_inputs'] = {**prepared['host_scripts']}
        for name in ('scripts/lemmasim-auth', str(Path(__file__).relative_to(ROOT)),
                     'scripts/package_product_image.py'):
            report['host_inputs'][name] = sha(ROOT / name)
        report['prepared_sha256'] = sha(args.prepared / 'prepared.json')
        old = json.loads((args.package / 'package.json').read_text())
        fresh = validate_package(args.guest_build, out / 'revalidated-package', old['identity'], args.guest_source_archive)
        require(fresh['configuration'] == 'lemmasim-silicon-product-executed-bulk-notebook'
                and fresh['image_sha256'] == old['image_sha256'] == sha(args.package / 'image.bin'),
                'original genuine audited notebook package changed')
        report['compiled_package'] = fresh
        # Bind the modules actually imported by the package/pixel observers,
        # including lazily loaded validators. Do not guess their directories.
        for module in list(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if not name:
                continue
            source = Path(name).resolve()
            if source.suffix == '.py' and source.is_relative_to(ROOT):
                relative = source.relative_to(ROOT)
                if relative.parts[0] in ('scripts', 'conformance'):
                    report['host_inputs'][str(relative)] = sha(source)
        report['original_inputs'] = {str(p.resolve()): sha(p) for p in
                    (args.boot_medium, args.disk, args.package / 'image.bin', args.tag)}
        boot, disk = out / 'boot.raw', out / 'user.raw'
        shutil.copyfile(args.boot_medium, boot)
        shutil.copyfile(args.disk, disk)
        original_boot = boot.read_bytes()
        known = metadata(original_boot)
        require(known[3:5] == (0, 1001), 'declared known-good confirmed source required')
        _, sequence, records = recover(disk.read_bytes())
        require(sequence == 14, 'declared genuine Saved14 source required')
        expected = expected_home(records)
        report.update(source_store_sequence=sequence, expected_home_sha256=hashlib.sha256(expected).hexdigest())
        live = launch('trial', boot, disk, True)
        command = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'), '--public-development-key',
                   'install-resume', '--session-dir', str(live), '--package', str(args.package.resolve()),
                   '--tag', str(args.tag.resolve()), '--slot', '1', '--transaction', '2000',
                   '--cycles', '600000000', '--timeout', '3600', '--quantum', '100000']
        started = time.monotonic()
        with (out / 'install.stdout').open('xb') as log, (out / 'install.stderr').open('xb') as errors:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=errors, timeout=3605)
        used = call(live, {'action': 'inspect'})['machine']['cycle']
        require(completed.returncode == 0 and used <= 600_000_000 and time.monotonic() - started <= 3600,
                'actual bounded resumable notebook installation failed')
        result = json.loads((out / 'install.stdout').read_text())
        require(result['state'] == 'installed-trial' and result['sectors_sent'] == 724,
                'notebook trial publication receipt absent')
        report['phases'].append({'name': 'actual-resumable-notebook-installation', 'clocks': used,
                                 'seconds': time.monotonic() - started, 'receipt': result})
        save()
        client = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=1800,
                         cycles=200_000_000, quantum=100_000, transaction=4000))
        started = time.monotonic()
        handoff = client.send(3)
        used += client.used
        require(handoff['status'] == 0 and handoff['value'] == 0x80000000, 'authenticated trial handoff failed')
        report['phases'].append({'name': 'guest-attempt-publication-authenticated-trial-handoff',
                                 'clocks': client.used, 'seconds': time.monotonic() - started, 'receipt': handoff})
        save()
        ready(live, 'trial-Ready-guest-confirmation', 1_100_000_000, True)
        confirmed = out / 'confirmed.raw'
        call(live, {'action': 'export-boot-medium', 'path': str(confirmed)})
        row = metadata(confirmed.read_bytes())
        require(row[2] == known[2] + 3 and row[3:8] == (1, old['identity'], 2, 0, 0)
                and confirmed.read_bytes()[8 * 512:32776 * 512] == original_boot[8 * 512:32776 * 512],
                'guest confirmation did not preserve known-good image or exact attempt/confirm generations')
        require(filecmp.cmp(args.disk, disk, shallow=False), 'updated notebook changed any document byte')
        close(live)
        cold_boot, cold_disk = out / 'cold-boot.raw', out / 'cold-user.raw'
        shutil.copyfile(confirmed, cold_boot)
        shutil.copyfile(disk, cold_disk)
        cold = launch('independent-cold', cold_boot, cold_disk, False)
        ready(cold, 'confirmed-new-CPU-cold-all-pixels', 1_300_000_000, False)
        final_boot = out / 'cold-observed-boot.raw'
        call(cold, {'action': 'export-boot-medium', 'path': str(final_boot)})
        require(filecmp.cmp(confirmed, final_boot, shallow=False)
                and filecmp.cmp(args.disk, cold_disk, shallow=False),
                'independent confirmed cold changed boot/document bytes')
        close(cold)
        guard()
        require(all(sha(p) == h for p, h in report['original_inputs'].items()), 'original input changed')
        report.update(status='PASS_AUTHENTICATED_NOTEBOOK_AB_UPDATE_GUEST_CONFIRMATION_COLD',
            all_expected_pixels=True, all_document_bytes_unchanged=True, snapshot_cold_input=False,
            confirmed_metadata=list(row[:9]), confirmed_boot_sha256=sha(confirmed))
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        for process, live in processes:
            try:
                sessions.request(live, {'action': 'destroy'}, 5)
            except BaseException:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        report.update(seconds=time.monotonic() - began, clocks=used)
        if report['seconds'] > 21600 or used > 3_500_000_000:
            report.update(status='FAIL', bound_error=True)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error'), flush=True)
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
