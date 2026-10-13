#!/usr/bin/env python3
"""Crash both opaque peer and hosted Lean client before lost-write reconciliation."""
import argparse
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time

from check_usb_pending import require, sha, stop
from check_guest_usb_store import opaque_log
from lemmasim_companion import initialize
from lemmasim_usb_pending import validate

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'clock-proof', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned restart output')
    record = validate(args.prepared)
    clock_proof = json.loads(args.clock_proof.read_text())
    clock_binary = args.clock_proof.resolve().parent / 'rtl/Vlemma_usb_device'
    require(clock_proof['status'] == 'PASS' and clock_proof['wait_adapter_sha256'] == sha(clock_binary) and
        clock_proof['inputs']['sim/rtl/lemma_usb_device.sv'] == sha(ROOT / 'sim/rtl/lemma_usb_device.sv') and
        clock_proof['inputs']['tests/usb/pending_wait.cpp'] == sha(ROOT / 'tests/usb/pending_wait.cpp'),
        'clock adapter lacks unchanged actual circuit qualification')
    out.mkdir(); began = time.monotonic(); deadline = began + 180
    report = {'schema': 'lemma-usb-client-peer-restart/1', 'status': 'FAIL',
        'scope': 'data-bearing hosted Lean opaque write; both peers restart before acknowledgment; no RV64 guest claim',
        'bounds': {'host_seconds': 180, 'wait_clocks': 100000000}, 'commands': [],
        'prepared_sha256': sha(args.prepared), 'policy_binary_sha256': record['binary']['sha256'],
        'clock_proof_sha256': sha(args.clock_proof), 'wait_adapter_sha256': sha(clock_binary),
        'fixture_source_sha256': sha(ROOT / 'tests/usb/PendingRestart.lean')}
    procs, logs = [], []
    try:
        build_log = (out / 'build.log').open('xb'); logs.append(build_log)
        environment = dict(os.environ, LEAN_PATH=str(args.prepared.resolve().parent), CC=record['host_tools']['cc']['path'])
        lean, leanc = (record['host_tools'][key]['path'] for key in ('lean', 'leanc'))
        commands = [[lean, '-R', str(ROOT / 'tests/usb'), '-o', str(out / 'PendingRestart.olean'),
                    '-c', str(out / 'PendingRestart.c'), str(ROOT / 'tests/usb/PendingRestart.lean')],
            [leanc, '-O2', '-c', str(out / 'PendingRestart.c'), '-o', str(out / 'PendingRestart.o')],
            [leanc, '-O2', '-Wall', '-Wextra', '-Werror', '-Dinitialize_USBPendingPolicy=initialize_PendingRestart',
                '-Dlemma_usb_pending_main=lemma_usb_pending_restart_main', '-c', str(ROOT / 'sim/usb/pending_main.c'),
                '-o', str(out / 'fixture_main.o')],
            [leanc, *record['legacy_link_inputs'], str(args.prepared.parent / 'USBHostLibrary.o'),
                str(args.prepared.parent / 'USBPendingPolicy.o'), str(out / 'PendingRestart.o'),
                str(out / 'fixture_main.o'), '-o', str(out / 'restart-fixture')]]
        for command in commands:
            report['commands'].append(command)
            subprocess.run(command, cwd=ROOT, env=environment, stdout=build_log, stderr=subprocess.STDOUT,
                           check=True, timeout=max(0.01, deadline-time.monotonic()))
        report['fixture_binary_sha256'] = sha(out / 'restart-fixture')
        initialize(out / 'peer', writer=91); (out / 'outbox').mkdir(mode=0o700)
        legacy = json.loads(Path(record['legacy_prepared']['path']).read_text())
        companion = Path(legacy['companion_prepared']['path'])
        def peer(lost=False):
            log = (out / ('peer-' + str(len(procs)) + '.log')).open('xb'); logs.append(log)
            command = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'companion', 'serve',
                '--prepared', str(companion), '--directory', str(out / 'peer'), '--socket', str(out / 'peer.sock')]
            if lost: command += ['--drop-reply', '1', '--exit-after-reply', '1']
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            procs.append(process); until = min(deadline, time.monotonic() + 10)
            while not (out / 'peer.sock').exists():
                require(process.poll() is None and time.monotonic() < until, 'peer startup failed'); time.sleep(0.001)
            return process
        environment.update(LEMMA_POLICY4_SOCKET=str(out / 'peer.sock'), LEMMA_POLICY4_OUTBOX=str(out / 'outbox'),
            LEMMA_POLICY4_HELPER=str(ROOT / 'sim/companion/os_io.py'))
        def client():
            log = (out / ('client-' + str(len(procs)) + '.err')).open('xb'); logs.append(log)
            process = subprocess.Popen([str(out / 'restart-fixture')], env=environment, cwd=ROOT,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, start_new_session=True)
            procs.append(process); return process
        first_peer = peer(True); first = client()
        require(select.select([first.stdout], [], [], max(0, deadline-time.monotonic()))[0], 'first Pending deadline')
        request = first.stdout.readline().strip()
        require(request == 'WAIT 100000' and first_peer.wait(timeout=15) == 0, 'write reply was not lost before Pending')
        pending = (out / 'outbox/outbox').read_bytes()
        rows = opaque_log(out / 'peer/opaque.log')
        payload = bytes(index % 256 for index in range(512))
        require(len(rows) == 1 and rows[0][0][2:7] == (1, 91, 1, 8192, 512) and rows[0][1] == payload and
                int.from_bytes(pending[16:24], 'little') == 1 and int.from_bytes(pending[24:32], 'little') == 584,
                'lost write did not preserve actual data and pending outbox')
        report['before_crash'] = {'peer_effects': 1, 'pending_outbox_sha256': sha(out / 'outbox/outbox'),
            'pending_frame_bytes': 584, 'next_sequence': 1, 'actual_pending_command': request,
            'peer_log_sha256': sha(out / 'peer/opaque.log'), 'payload_sha256': sha_bytes(payload)}
        stop(first); report['first_client_exit_code'] = first.returncode
        second = client(); errors = []
        def restart():
            try: time.sleep(0.5); peer()
            except BaseException as error: errors.append(repr(error))
        thread = threading.Thread(target=restart); thread.start()
        clock = subprocess.Popen([str(clock_binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=build_log, text=True, start_new_session=True); procs.append(clock)
        ticks = 0
        with (out / 'raw.log').open('x') as raw:
            while True:
                require(select.select([second.stdout], [], [], max(0, deadline-time.monotonic()))[0], 'restarted client deadline')
                line = second.stdout.readline().strip(); raw.write(line + '\n'); raw.flush()
                if line.startswith('RESULT '): break
                require(line == 'WAIT 100000', 'unexpected retry boundary')
                clock.stdin.write(line + '\n'); clock.stdin.flush()
                require(select.select([clock.stdout], [], [], max(0, deadline-time.monotonic()))[0], 'controller clock deadline')
                reply = clock.stdout.readline().split()
                require(len(reply) == 3 and reply[0] == 'WAIT_DONE' and int(reply[2])-int(reply[1]) == 100000,
                    'retry did not clock the literal controller')
                ticks += 100000; require(ticks <= 100000000, 'retry exceeded Pending budget')
                second.stdin.write('WAIT_DONE\n'); second.stdin.flush()
        thread.join(timeout=15); require(not thread.is_alive() and not errors, 'peer restart failed')
        second.stdin.close(); second.wait(timeout=10); clock.stdin.close(); clock.wait(timeout=10)
        final = (out / 'outbox/outbox').read_bytes(); final_rows = opaque_log(out / 'peer/opaque.log')
        require(second.returncode == clock.returncode == 0 and line.startswith('RESULT ACK NEXT 2 ERROR 0 ') and
            len(final_rows) == 1 and final_rows == rows and int.from_bytes(final[16:24], 'little') == 2 and
            int.from_bytes(final[24:32], 'little') == 0, 'both-side restart duplicated or failed durable effect')
        report.update(status='PASS', result=line, actual_wait_clocks=ticks, durable_effects=1,
            exact_persisted_payload=True, same_writer_sequence=True, final_outbox_sha256=sha(out / 'outbox/outbox'))
    except BaseException as error: report['error'] = repr(error)
    finally:
        if 'thread' in locals(): thread.join(timeout=15)
        for process in procs: stop(process)
        for log in logs: log.close()
        report.update(host_seconds=time.monotonic() - began, observer_sha256=sha(__file__),
            owned_children_reaped=all(p.poll() is not None for p in procs))
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


def sha_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


if __name__ == '__main__': raise SystemExit(main())
