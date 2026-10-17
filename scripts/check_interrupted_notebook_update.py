#!/usr/bin/env python3
"""Guest update interruption followed by independent immutable-ROM cold recovery.

The original payload case stages sixteen sectors, obtains a fresh STATUS
barrier, then brownouts before tag/publication. The metadata case transfers the
complete fixed image/tag and captures a real partial metadata pwrite/EFBIG
before brownout. Neither qualifies in-flight brownout, confirmation interruption
or production trust. Both compare every acknowledged document byte/home pixel.
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

import development_install
import lemmasim_auth as auth
import lemmasim_session as sessions
from check_development_install_resume import metadata
from check_live_notebook import guest_events, visible_pixels
from product_native import sha
from check_companion_pending import timed_records

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def interruption_spec(cut):
    # Distinct prospectively fixed workloads. The original sixteen-sector
    # case keeps every original ceiling. Metadata needs the whole1059-sector
    # payload and real authentication, bounded by prior observed full installs.
    if cut == 'payload':
        return 16, 300000000, 2400, 1800000000, 14400
    if cut == 'metadata':
        return 1059, 900000000, 7200, 2400000000, 21600
    raise ValueError('unknown interruption workload')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('prepared', 'known-package', 'package', 'tag', 'boot-medium',
                 'disk', 'expected-home', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--public-development-key', action='store_true', required=True)
    parser.add_argument('--cut',choices=('payload','metadata'),default='payload',
                        help='metadata: complete actual payload/tag, failed real partial metadata pwrite, then brownout/cold')
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
    sectors, transfer_clocks, transfer_seconds, aggregate, whole_seconds = interruption_spec(args.cut)
    deadline = began + whole_seconds
    used = 0
    processes = []
    report = {'schema': 'lemma-interrupted-notebook-update/1', 'status': 'RUNNING',
              'scope': __doc__, 'cut':args.cut, 'phases': [], 'bounds': {'whole_seconds': whole_seconds,
              'aggregate_RTL_clocks': aggregate, 'partial_clocks': transfer_clocks,
              'partial_seconds': transfer_seconds, 'cold_clocks': 1500000000,
              'cold_seconds': 11200, 'per_process_AS_bytes': 4 << 30,
              'file_bytes': 1 << 30, 'automatic_restart': False}}

    def save():
        report.update(seconds=time.monotonic() - began, clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() < deadline and used <= aggregate, 'prospective whole bound')
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
            if args.cut=='metadata':argv+=['--boot-write-limit',report['fault_environment']]
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
        if args.cut=='metadata':
            chosen=[i for i in (0,1) if struct.unpack_from('<64Q',original,i*512)==old_metadata]
            require(len(chosen)==1,'unique actual current metadata sector required')
            destination=1-chosen[0]
            report.update(schema='lemma-interrupted-notebook-update/2',
                scope='Complete actual1059-sector inactive payload/tag, real scoped partial metadata pwrite/EFBIG, no publication receipt, brownout and independent normal ROM known13 cold. In-flight brownout/barrier/confirmation matrix and production trust remain open.',
                fault_environment=f'0:1024:{destination*512+256}',metadata_destination=destination)
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
        client = auth.RecoveryClient(SimpleNamespace(session_dir=live, timeout=transfer_seconds,
            cycles=transfer_clocks-200, quantum=100000, transaction=100))
        report['beacon'] = client.beacon()
        auth.product.install_extent(package, wire, client.call({'action': 'inspect'})['identity'])
        receipts = []
        for index in range(sectors):
            row = client.send(1, 0, index, package['identity'], wire[index * 512:(index + 1) * 512])
            require(row['status'] == 0, 'actual inactive payload staging WRITE failed')
            receipts.append(row)
        if args.cut=='payload':
            status = client.send(4, 0, identity=package['identity'])
            require(status['status'] == 217 and status['value'] == 0,
                    'incomplete untagged payload obtained an installation receipt')
            tape=live/'boot.nvio'
            require(tape.read_bytes()[8:72].decode()==prepared['runtime_identity'],'actual BootNV capture identity')
            io,pending=timed_records(tape,b'LMNVLOG2')
            writes=[r for r,t in io if r[2]==1]
            barriers=[r for r,t in io if r[2]==2]
            require(pending is None and len(writes)==16 and len(barriers)==1 and
                    all(r[6]==0 for r,t in io) and barriers[0][0]>writes[-1][0],
                    'staging writes lack actual later successful STATUS barrier')
            report['staging_durability']={'write_operations':16,'status_barriers':1,
                'barrier_id':barriers[0][0],'last_write_id':writes[-1][0],
                'semantics':'Sector transport responses alone are not durable installation receipts.'}
        else:
            tag=client.send(5,0,identity=package['identity'],payload=args.tag.read_bytes())
            require(tag['status']==0,'actual complete candidate tag receipt failed')
            before_publish=call(live,{'action':'inspect'})['machine']['boot_backing']
            status=client.send(2,0,identity=package['identity'])
            require(status['status']==212 and status['value']==0,'torn metadata obtained a publication receipt')
            after_publish=call(live,{'action':'inspect'})['machine']['boot_backing']
            tape=live/'boot.nvio'
            require(tape.read_bytes()[8:72].decode()==prepared['runtime_identity'],'actual BootNV capture identity')
            io,pending=timed_records(tape,b'LMNVLOG2')
            failed=[r for r,t in io if r[6]]
            publication=[r for r,t in io if r[0]>=before_publish['next_id']]
            # finishInstall first barriers payload/tag, then verifies image
            # bytes. That success cannot make the later torn metadata durable.
            barriers=[r for r in publication if r[2]==2]
            require(pending is None and len(failed)==1 and
                    failed[0][2:]==(1,destination*512,512,256,27) and
                    failed[0][0]==after_publish['completed'] and
                    len(barriers)==1 and barriers[0][6]==0 and barriers[0][0]<failed[0][0] and
                    after_publish['durable_barrier']==barriers[0][0] and
                    [r for r in publication if r[2]==1]==failed and
                    io[-1][0]==failed[0], 'actual partial metadata pwrite/error/barrier capture differs')
            report['metadata_failure']={'tag':tag,'publish':status,'actual_failed_IO':list(failed[0]),
                'durable_barrier_before':before_publish['durable_barrier'],
                'payload_tag_barrier_during_validation':barriers[0][0],
                'durable_barrier_after':after_publish['durable_barrier']}
        used += client.used
        require(used <= transfer_clocks and time.monotonic() - began <= transfer_seconds,
                'prospective partial-transfer bound')
        partial = boot_bytes(live, 'actual-partial')
        start, end = 8 * 512, (8 + sectors) * 512
        expected=bytearray(original);expected[start:end]=wire[:sectors*512]
        if args.cut=='metadata':
            expected[2*512:3*512]=args.tag.read_bytes()
            at=destination*512
            header=struct.unpack_from('<9Q',partial,at)
            require(header[:5]==old_metadata[:2]+(old_metadata[2]+1,)+old_metadata[3:5] and
                    header[5:]==(0,package['identity'],0,3), 'actual torn metadata header differs')
            # Only the independently recorded partial256-byte write may differ.
            # These observed bytes never enter a machine or medium as input.
            expected[at:at+256]=partial[at:at+256]
            require(partial[at:at+256]!=original[at:at+256], 'failed write was silently rolled back')
        require(partial==bytes(expected) and metadata(partial)==old_metadata,
                'actual staging changed known image, authoritative metadata or bytes outside admitted effects')
        before = call(live, {'action': 'inspect'})['machine']
        call(live, {'action': 'inject', 'kind': 'brownout', 'level': 1})
        call(live, {'action': 'run', 'cycles': 200})
        used += 200
        unsafe = call(live, {'action': 'inspect'})['machine']
        require(used <= transfer_clocks and time.monotonic() - began <= transfer_seconds,
                'prospective partial-transfer/reset bound')
        require(unsafe['cycle'] == before['cycle'] + 200 and unsafe['power']['domain_reset'] == 1
                and unsafe['power']['reset_cause'] == 5 and unsafe['power']['watchdog_armed'] == 0
                and unsafe['boot_backing']['reset_origin'] > before['boot_backing']['reset_origin'],
                'actual brownout cancellation/reset origin differs')
        require(boot_bytes(live, 'actual-brownout') == partial,
                'brownout changed acknowledged staging or confirmed metadata')
        report['partial'] = {'receipts': receipts, 'uninstalled_status': status,
                             'before': before, 'brownout': unsafe, 'sectors': sectors}
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
        report.update(status=('PASS_PARTIAL_NOTEBOOK_UPDATE_BROWNOUT_INDEPENDENT_CONFIRMED_COLD' if args.cut=='payload'
                             else 'PASS_REAL_TORN_METADATA_PUBLISH_BROWNOUT_INDEPENDENT_CONFIRMED_COLD'),
                      all_home_pixels=3630000, all_user_bytes=268435456,
                      qualification=('Between-barrier payload interruption only' if args.cut=='payload' else
                                     'Real partial-pwrite metadata publication failure then brownout')+
                                    '; no full update-interruption matrix or production trust claim')
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
