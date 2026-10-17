#!/usr/bin/env python3
"""Real RTL ROM: partial inactive payload -> brownout -> resumed authenticated
installation -> independent recovery reconnect/status without rewriting bytes.
The small ordinary Lean CryptoProbe qualifies transport/update behavior only.
Attached opaque notebook media must remain byte-identical. No notebook Ready,
production identity, healthy-trial confirmation or lost-packet claim is made.
"""
import argparse
import filecmp
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace
import zlib

import development_install
import lemmasim_auth as auth
import lemmasim_session as sessions
from product_native import sha

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def metadata(raw):
    valid = []
    for sector in (0, 1):
        block = raw[sector * 512:(sector + 1) * 512]
        words = struct.unpack('<64Q', block)
        if (words[0:2] == (0x31444d42414d454c, 1) and 0 < words[2] < (1 << 64) - 1
                and words[3] < 2 and words[4] and words[8] == 3
                and not any(words[9:63]) and words[63] == zlib.crc32(block[:504])):
            valid.append((words[2], sector, words))
    require(valid, 'independent metadata observer found no valid known-good image')
    valid.sort(reverse=True)
    if len(valid) == 2 and valid[0][0] == valid[1][0]:
        require(valid[0][2] == valid[1][2], 'conflicting equal-generation metadata')
    return valid[0][2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'package', 'tag', 'boot-medium', 'disk', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'build'):
        parser.error('unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    started = time.monotonic()
    deadline = started + 3600
    used = 0
    process = None
    live = None
    report = {'status': 'FAIL', 'scope': __doc__, 'phases': [],
              'bounds': {'seconds': 3600, 'clocks': 300_000_000,
                         'quantum': 100_000, 'automatic_restart': False}}

    def save():
        report.update(seconds=time.monotonic() - started, clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def check():
        require(time.monotonic() < deadline and used <= 300_000_000, 'original whole bound')
        require(all(sha(ROOT / p) == h for p, h in report['host_inputs'].items()),
                'consumed host source changed')

    def close():
        nonlocal process
        if process is None:
            return
        try:
            if process.poll() is None:
                sessions.request(live, {'action': 'destroy'}, 5)
        except BaseException:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        process = None

    def launch(name):
        nonlocal process, live
        check()
        live = out / name
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'),
                '--public-development-key', 'launch', '--prepared', str(args.prepared.resolve()),
                '--session-dir', str(live), '--boot-medium', str(boot), '--disk', str(disk),
                '--recovery', '--paused', '--headless', '--mode', 'laboratory',
                '--timeout', '120', '--host-threads', '1']
        with (out / (name + '.log')).open('xb') as log:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        until = time.monotonic() + 30
        while not (live / 'session.json').is_file():
            require(process.poll() is None and time.monotonic() < until,
                    'actual immutable-ROM machine did not open')
            time.sleep(.05)
        return auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=120,
                    cycles=300_000_000 - used, quantum=100_000, transaction=1))

    def command(name):
        nonlocal used
        check()
        argv = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'),
                '--public-development-key', 'install-resume', '--session-dir', str(live),
                '--package', str(args.package.resolve()), '--tag', str(args.tag.resolve()),
                '--slot', '1', '--continue-recovery', '--transaction', '1000',
                '--cycles', str(300_000_000 - used), '--quantum', '100000',
                '--timeout', str(max(1, min(1200, int(deadline - time.monotonic()))))]
        before = sessions.request(live, {'action': 'inspect'}, 120)['machine']['cycle']
        began = time.monotonic()
        completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                   timeout=min(1205, max(1, deadline - time.monotonic())))
        (out / (name + '.stdout')).write_text(completed.stdout)
        (out / (name + '.stderr')).write_text(completed.stderr)
        after = sessions.request(live, {'action': 'inspect'}, 120)['machine']['cycle']
        used += after - before
        require(completed.returncode == 0, 'actual install-resume command failed: ' + completed.stderr[-1500:])
        result = json.loads(completed.stdout)
        require(result['cycles'] == after - before, 'command clock accounting differs')
        report['phases'].append({'name': name, 'clocks': after - before,
                                  'seconds': time.monotonic() - began, 'result': result})
        save()
        return result

    try:
        prepared, _, _ = auth.prepared(args.prepared)
        package, wire, tag = development_install.load_package(args.package, args.tag, sha)
        require(len(wire) == 22 * 512 and package['identity'] == 1001,
                'this bounded case requires the original audited22-sector CryptoProbe')
        source = Path(package['source'])
        source_result = source.parent.parent / 'result.json'
        require(sha(source) == package['source_sha256']
                and sha(source_result) == package['source_result_sha256']
                and json.loads(source_result.read_text())['status'] ==
                    'PASS_GENUINE_RV64_SHA256_HMAC_COMPONENT',
                'original genuine compiled/audited payload identity changed')
        report['host_inputs'] = {**prepared['host_scripts'],
            'scripts/lemmasim-auth': sha(ROOT / 'scripts/lemmasim-auth'),
            str(Path(__file__).relative_to(ROOT)): sha(__file__)}
        report['prepared_sha256'] = sha(args.prepared / 'prepared.json')
        report['inputs'] = {str(p.resolve()): sha(p) for p in
                            (args.boot_medium, args.disk, args.package / 'image.bin', args.tag)}
        boot, disk = out / 'boot.raw', out / 'user.raw'
        shutil.copyfile(args.boot_medium, boot)
        shutil.copyfile(args.disk, disk)
        original = boot.read_bytes()
        known = metadata(original)
        require(known[3:8] == (0, 1001, 2, 0, 0), 'known confirmed/no-trial source differs')
        client = launch('partial')
        report['initial_beacon'] = client.beacon()
        auth.product.install_extent(package, wire, client.call({'action': 'inspect'})['identity'])
        for index in range(7):
            row = client.send(1, 1, index, 1001, wire[index * 512:(index + 1) * 512])
            require(row['status'] == 0, 'actual partial payload write rejected')
        used += client.used
        partial = out / 'partial.raw'
        client.call({'action': 'export-boot-medium', 'path': str(partial)})
        raw = partial.read_bytes()
        offset = 32776 * 512
        require(raw[:offset] == original[:offset] and raw[offset:offset + 7 * 512] == wire[:7 * 512]
                and raw[offset + 7 * 512:] == original[offset + 7 * 512:]
                and metadata(raw) == known, 'partial staging altered confirmed image/metadata')
        boundary = client.call({'action': 'inspect'})['machine']
        uart_cursor = (live / 'uart.bin').stat().st_size
        client.call({'action': 'inject', 'kind': 'brownout', 'level': 1})
        client.call({'action': 'run', 'cycles': 32})
        used += 32
        unsafe = client.call({'action': 'inspect'})['machine']
        require(unsafe['power']['domain_reset'] == 1 and unsafe['power']['reset_cause'] == 5
                and unsafe['boot_backing']['reset_origin'] > boundary['boot_backing']['reset_origin'],
                'actual brownout reset/cause/boot-origin boundary missing')
        report['brownout'] = {'before': boundary, 'unsafe': unsafe,
                              'fresh_uart_cursor': uart_cursor}
        save()
        client.call({'action': 'inject', 'kind': 'brownout', 'level': 0})
        client.call({'action': 'run', 'cycles': 8})
        used += 8
        safe = client.call({'action': 'inspect'})['machine']
        require(safe['power']['domain_reset'] == 0 and safe['power']['reset_remaining'] == 0,
                'eight safe reset qualification clocks did not release')
        # At the release boundary the CPU is still at immutable reset entry.
        # Supply the actual owner request before that entry samples the UART.
        # Scheduling it16 clocks after release allowed normal confirmed boot.
        client.call({'action': 'inject', 'kind': 'uart', 'hex': '52'})
        # Observe only the newly emitted beacon, never the old pre-reset one.
        reconnect = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=120,
                         cycles=300_000_000 - used, quantum=100_000, transaction=500))
        reconnect.cursor = uart_cursor
        report['post_brownout_beacon'] = reconnect.beacon()
        used += reconnect.used
        report['brownout']['safe'] = safe
        resumed = command('resume-partial-after-brownout')
        require(resumed['state'] == 'installed-trial' and resumed['sectors_sent'] == 22,
                'partial resumed installation did not obtain actual trial receipt')
        acknowledged = out / 'acknowledged.raw'
        reconnect.call({'action': 'export-boot-medium', 'path': str(acknowledged)})
        accepted = acknowledged.read_bytes()
        record = metadata(accepted)
        require(record[3:8] == (0, 1001, 1, 1001, 0) and record[2] == known[2] + 1
                and accepted[8 * 512:32776 * 512] == original[8 * 512:32776 * 512]
                and accepted[offset:offset + len(wire)] == wire
                and filecmp.cmp(args.disk, disk, shallow=False),
                'actual installation changed known-good bytes/documents or trial identity')
        close()
        second = launch('independent-recovery')
        report['independent_beacon'] = second.beacon()
        used += second.used
        before = second.call({'action': 'inspect'})['machine']['boot_backing']['observed_write']
        reconciled = command('independent-reconnect-same-image')
        after = second.call({'action': 'inspect'})['machine']['boot_backing']['observed_write']
        require(reconciled['state'] == 'reconciled-trial' and reconciled['sectors_sent'] == 0
                and [r['operation'] for r in reconciled['receipts']] == [4]
                and before == after, 'retry rewrote an already-published image')
        final = out / 'reconciled.raw'
        second.call({'action': 'export-boot-medium', 'path': str(final)})
        require(filecmp.cmp(acknowledged, final, shallow=False)
                and filecmp.cmp(args.disk, disk, shallow=False), 'reconciliation changed backing bytes')
        check()
        require(all(sha(p) == h for p, h in report['inputs'].items()), 'original input changed')
        report.update(status='PASS_RTL_BROWNOUT_PARTIAL_INSTALL_RESUME_RECONNECT',
            documents_all_bytes_unchanged=True, confirmed_slot_all_bytes_unchanged=True,
            reconciled_boot_sha256=sha(final), no_retry_payload_or_tag_or_metadata_writes=True,
            not_qualified=['full notebook update/cold recovery', 'trial health confirmation',
                           'watchdog', 'interrupted metadata/confirmation', 'lost UART packet',
                           'production identity/entropy/antirollback', 'browser product boot'])
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        close()
        report.update(seconds=time.monotonic() - started, clocks=used, launcher_reaped=process is None)
        if report['seconds'] > 3600 or used > 300_000_000:
            report['status'] = 'FAIL'
            report['bound_error'] = True
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('status', 'seconds', 'clocks', 'error')}, indent=2))
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
