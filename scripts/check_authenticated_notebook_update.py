#!/usr/bin/env python3
"""Guest A/B installation -> actual trial notebook -> guest health confirmation
-> independent authenticated cold recovery, preserving every document byte.
The original Saved14 case remains fixed. The additive Saved38 Reader18 case
uses an audited four-role image and raw COURSE input after independent cold.
The fixed Saved32 case adds the corrected revision-bound hint publication image.
These cases do not claim interrupted confirmation, production keys or browser boot.
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
    parser.add_argument('--case',choices=('saved14-notebook','saved38-course-reader',
                        'saved38-course-reader-pool-read','saved32-course-hint-publication'),
                        default='saved14-notebook')
    parser.add_argument('--expected-home',type=Path)
    parser.add_argument('--expected-course',type=Path)
    args = parser.parse_args()
    hint_publication = args.case == 'saved32-course-hint-publication'
    reader = hint_publication or args.case in ('saved38-course-reader','saved38-course-reader-pool-read')
    pool_read = args.case == 'saved38-course-reader-pool-read'
    require(not reader or args.expected_home is not None and args.expected_course is not None,
            'Reader18 requires independent complete home/course references')
    whole_seconds = 32400 if reader else 21600
    total_cap = 4_300_000_000 if reader else 3_500_000_000
    install_cap, install_seconds = (900_000_000,7200) if reader else (600_000_000,3600)
    handoff_cap, handoff_seconds = (300_000_000,3600) if reader else (200_000_000,1800)
    ready_cap, ready_seconds = (1_200_000_000,9000) if reader else (1_100_000_000,7200)
    cold_cap, cold_seconds = (1_500_000_000,11200) if reader else (1_300_000_000,7200)
    # Separate fixed workloads retain the original payload-size checks. The
    # audited getter refinement adds exactly one sector to the Product image;
    # it receives the same original Reader18 execution/deadline ceilings.
    sectors, sequence_expected = (1057 if pool_read else 1056,38) if reader else (724,14)
    if hint_publication:
        sectors, sequence_expected = 1058, 32
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    began = time.monotonic()
    deadline = began + whole_seconds
    used = 0
    processes = []
    report = {'status': 'RUNNING', 'scope': __doc__, 'phases': [],
              'case':args.case,
              'bounds': {'whole_seconds': whole_seconds, 'clocks': total_cap,
                         'install_clocks': install_cap, 'install_seconds': install_seconds,
                         'handoff_clocks': handoff_cap, 'handoff_seconds': handoff_seconds,
                         'ready_clocks': ready_cap, 'ready_seconds': ready_seconds,
                         'cold_clocks': cold_cap, 'cold_seconds': cold_seconds,
                         'course_clocks':400_000_000 if reader else 0,
                         'course_seconds':3600 if reader else 0,
                         'automatic_restart': False},
              'bound_basis': ('New1056-sector payload versus original724; installation ceiling900M is the prior600M ceiling scaled1.5, handoff300M scaled1.5; four real processes and Source38 recovery get explicit1.2B/1.5B bounds. Whole4.3B/32400s uses the observed final319 runtime16M/118.192s lower throughput as a prospective host allowance. No earlier failure is reclassified.' if reader else 'Original fixed Saved14/724-sector case')}
    if pool_read:
        report['bound_basis'] = ('Separate audited1057-sector getter-refinement image; '
            'all original Reader18/Saved38 clock, host and resource ceilings retained. '
            'The original1056-sector case remains unchanged; no deadline increase.')
    if hint_publication:
        report['bound_basis'] = ('Separate audited1058-sector hint-publication image and actual '
            'Saved32 medium; all original Reader18 clock, host and resource ceilings retained. '
            'Original724/1056/1057-sector cases stay strict. Complete home/course references '
            'come from the qualified current guest fast cold/reopen; no snapshot cold input.')


    def save():
        report.update(seconds=time.monotonic() - began, clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() < deadline and used <= total_cap, 'original whole bound')
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
            require(0 <= delta <= cap and time.monotonic() - started <= (ready_seconds if confirm else cold_seconds),
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
            require(delta < cap and used < total_cap, 'original clock ceiling: ' + name)
            quantum = min(1_000_000, cap - delta, total_cap - used)
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
        require(fresh['configuration'] == ('lemmasim-silicon-product-course-reader-bulk-notebook' if reader else 'lemmasim-silicon-product-executed-bulk-notebook')
                and fresh['image_sha256'] == old['image_sha256'] == sha(args.package / 'image.bin'),
                'original genuine audited notebook package changed')
        report['compiled_package'] = fresh
        require(fresh['sectors'] == sectors, 'declared audited payload sector count differs')
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
        require(sequence == sequence_expected, 'declared genuine source sequence required')
        if reader:
            width,height,expected = visible_pixels(args.expected_home)
            require((width,height)==(1650,2200),'canonical complete home reference required')
            report['original_inputs'].update({str(p.resolve()):sha(p) for p in (args.expected_home,args.expected_course)})
        else: expected = expected_home(records)
        report.update(source_store_sequence=sequence, expected_home_sha256=hashlib.sha256(expected).hexdigest())
        live = launch('trial', boot, disk, True)
        command = [sys.executable, str(ROOT / 'scripts/lemmasim-auth'), '--public-development-key',
                   'install-resume', '--session-dir', str(live), '--package', str(args.package.resolve()),
                   '--tag', str(args.tag.resolve()), '--slot', '1', '--transaction', '2000',
                   '--cycles', str(install_cap), '--timeout', str(install_seconds), '--quantum', '100000']
        started = time.monotonic()
        with (out / 'install.stdout').open('xb') as log, (out / 'install.stderr').open('xb') as errors:
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=errors, timeout=install_seconds+5)
        used = call(live, {'action': 'inspect'})['machine']['cycle']
        require(completed.returncode == 0 and used <= install_cap and time.monotonic() - started <= install_seconds,
                'actual bounded resumable notebook installation failed')
        result = json.loads((out / 'install.stdout').read_text())
        require(result['state'] == 'installed-trial' and result['sectors_sent'] == sectors,
                'notebook trial publication receipt absent')
        report['phases'].append({'name': 'actual-resumable-notebook-installation', 'clocks': used,
                                 'seconds': time.monotonic() - started, 'receipt': result})
        save()
        client = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=handoff_seconds,
                         cycles=handoff_cap, quantum=100_000, transaction=4000))
        started = time.monotonic()
        handoff = client.send(3)
        used += client.used
        require(handoff['status'] == 0 and handoff['value'] == 0x80000000, 'authenticated trial handoff failed')
        report['phases'].append({'name': 'guest-attempt-publication-authenticated-trial-handoff',
                                 'clocks': client.used, 'seconds': time.monotonic() - started, 'receipt': handoff})
        save()
        ready(live, 'trial-Ready-guest-confirmation', ready_cap, True)
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
        ready(cold, 'confirmed-new-CPU-cold-all-pixels', cold_cap, False)
        final_boot = out / 'cold-observed-boot.raw'
        call(cold, {'action': 'export-boot-medium', 'path': str(final_boot)})
        require(filecmp.cmp(confirmed, final_boot, shallow=False)
                and filecmp.cmp(args.disk, cold_disk, shallow=False),
                'independent confirmed cold changed boot/document bytes')
        if reader:
            initial=call(cold,{'action':'inspect'})['machine'];started=time.monotonic()
            tick=initial['ticks']+10000
            for at,pressure,flags in ((tick,2048,3),(tick+100000,0,2)):
                call(cold,{'action':'inject','kind':'pen','cycle':at*10,
                           'words':[at,12718,4173,pressure,flags,1,0]})
            expected_course=visible_pixels(args.expected_course)
            require(expected_course[:2]==(1650,2200),'canonical complete course reference required')
            while True:
                guard();state=call(cold,{'action':'inspect'})['machine'];delta=state['cycle']-initial['cycle']
                require(0<=delta<=400_000_000 and time.monotonic()-started<=3600,'original Reader18 COURSE bound')
                rows=guest_events(cold/'uart.bin')
                require(not state['finished'] and not any(r[0]in(0x41f,0xd4,0xf4,0x424,0x454)for r in rows),'actual course/guest failure')
                idle=all(state[k]==0 for k in('event_queue','pen_queue','paper_busy','panel_pending_pixels','block_state','dma_outstanding'))
                if idle and state['panel_completed']>initial['panel_completed']:
                    panel=out/('cold-reader-example3.ppm' if hint_publication else 'cold-reader-example5.ppm');call(cold,{'action':'panel','path':str(panel)})
                    if visible_pixels(panel)==expected_course:break
                require(delta<400_000_000 and used<total_cap,'original Reader18 COURSE clock ceiling')
                quantum=min(1_000_000,400_000_000-delta,total_cap-used)
                call(cold,{'action':'run','cycles':quantum});used+=quantum
            require(filecmp.cmp(args.disk,cold_disk,shallow=False),'read-only course open changed any original document byte')
            report['phases'].append({'name':'authenticated-cold-raw-COURSE-saved-example3' if hint_publication else 'authenticated-cold-raw-COURSE-saved-example5','clocks':delta,
                'seconds':time.monotonic()-started,'all_controller_pixels':3630000,'raw_samples':2})
            report['reader_scope']='Actual guest Reader18/Store/course decoding and saved node5; no new arithmetic check, tutor or third cold claimed'
            if hint_publication:
                report['reader_scope']='Actual corrected guest/Store/course decoding and saved node3; full current fast frame reference. No new arithmetic submission, live tutor or third cold claimed.'
        close(cold)
        guard()
        require(all(sha(p) == h for p, h in report['original_inputs'].items()), 'original input changed')
        report.update(status=('PASS_AUTHENTICATED_COURSE_IMAGE_UPDATE_CONFIRM_COLD_READER' if reader else 'PASS_AUTHENTICATED_NOTEBOOK_AB_UPDATE_GUEST_CONFIRMATION_COLD'),
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
        if report['seconds'] > whole_seconds or used > total_cap:
            report.update(status='FAIL', bound_error=True)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report.get('error'), flush=True)
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
