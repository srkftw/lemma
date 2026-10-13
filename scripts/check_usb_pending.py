#!/usr/bin/env python3
"""Qualify hosted Lean receipt Pending with real peer barriers and USB RTL clocks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import threading
import time

from check_guest_usb_store import opaque_log
from lemmasim_companion import initialize
from lemmasim_usb_pending import validate

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--verilator', type=Path)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    out, prepared = args.work_dir.resolve(), args.prepared.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'),
            'qualification requires an unused owned build directory')
    require(0 < args.timeout <= 600, 'qualification deadline outside resource contract')
    record = validate(prepared)
    out.mkdir(parents=True)
    began = time.monotonic()
    deadline = began + args.timeout
    report = {'schema': 'lemma-usb-pending4-properties/2', 'status': 'FAIL',
              'scope': 'hosted Lean opaque receipt policy, independent durable peer and literal USB RTL WAIT; no RV64 guest claim',
              'bounds': {'host_seconds': args.timeout, 'operation_wait_clocks': 100000000,
                         'restart_delay_seconds': 0.5}, 'cases': [], 'commands': [],
              'prepared_sha256': sha(prepared), 'policy_binary_sha256': record['binary']['sha256']}
    procs, handles, threads = [], [], []
    fixture_inputs = ('tests/usb/PendingExchange.lean', 'tests/usb/pending_wait.cpp',
                      'sim/rtl/lemma_usb_device.sv', 'scripts/check_usb_pending.py')
    report['inputs'] = {name: sha(ROOT / name) for name in fixture_inputs}

    def run(command, environment):
        report['commands'].append([str(x) for x in command])
        subprocess.run(command, cwd=ROOT, env=environment, check=True,
                       stdout=handles[0], stderr=subprocess.STDOUT,
                       timeout=max(0.01, deadline - time.monotonic()))

    try:
        handles.append((out / 'build.log').open('xb'))
        tools = record['host_tools']
        env = dict(os.environ, LEAN_PATH=str(prepared.parent), CC=tools['cc']['path'])
        env['PATH'] = ':'.join(str(Path(v['path']).parent) for v in tools.values()) + ':' + env.get('PATH', '')
        lean, leanc = tools['lean']['path'], tools['leanc']['path']
        run([lean, '-R', str(ROOT / 'tests/usb'), '-o', str(out / 'PendingExchange.olean'),
             '-c', str(out / 'PendingExchange.c'), str(ROOT / 'tests/usb/PendingExchange.lean')], env)
        run([leanc, '-O2', '-c', str(out / 'PendingExchange.c'), '-o', str(out / 'PendingExchange.o')], env)
        run([leanc, '-O2', '-Wall', '-Wextra', '-Werror', '-Dinitialize_USBPendingPolicy=initialize_PendingExchange',
             '-Dlemma_usb_pending_main=lemma_usb_pending_fixture_main', '-c',
             str(ROOT / 'sim/usb/pending_main.c'), '-o', str(out / 'fixture_main.o')], env)
        run([leanc, *record['legacy_link_inputs'], str(prepared.parent / 'USBHostLibrary.o'),
             str(prepared.parent / 'USBPendingPolicy.o'), str(out / 'PendingExchange.o'),
             str(out / 'fixture_main.o'), '-o', str(out / 'exchange-fixture')], env)
        verifier = str(args.verilator.resolve()) if args.verilator else shutil.which('verilator')
        require(verifier is not None and os.access(verifier, os.X_OK), 'Verilator unavailable')
        env['PATH'] = str(Path(verifier).parent) + ':' + env['PATH']
        report['verilator'] = {'path': str(Path(verifier).resolve()), 'sha256': sha(Path(verifier).resolve()),
            'version': subprocess.check_output([verifier, '--version'], text=True).strip()}
        run([verifier, '--cc', '--exe', '--build', '--top-module', 'lemma_usb_device',
             '-Wno-fatal', '-j', '2', '--Mdir', str(out / 'rtl'),
             str(ROOT / 'sim/rtl/lemma_usb_device.sv'), str(ROOT / 'tests/usb/pending_wait.cpp')], env)
        clock_binary = out / 'rtl/Vlemma_usb_device'
        report['wait_adapter_sha256'] = sha(clock_binary)
        report['fixture_binary_sha256'] = sha(out / 'exchange-fixture')
        original = json.loads(Path(record['legacy_prepared']['path']).read_text())
        companion = Path(original['companion_prepared']['path'])

        def start_peer(case, lost=False):
            log = (case / ('peer-' + str(len(procs)) + '.log')).open('xb')
            handles.append(log)
            command = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'companion', 'serve',
                '--prepared', str(companion), '--directory', str(case / 'peer'),
                '--socket', str(case / 'peer.sock'), '--drop-reply', str(int(lost)),
                '--exit-after-reply', str(int(lost))]
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            procs.append(process)
            until = min(deadline, time.monotonic() + 10)
            while not (case / 'peer.sock').exists():
                require(process.poll() is None and time.monotonic() < until, 'peer startup failed')
                time.sleep(0.001)
            return process

        for name, mode, spent in [('restart500', 'lost', 0), ('retry-old', 'old', 0),
                                  ('no-peer', 'absent', 0), ('shared-budget', 'absent', 99900000),
                                  ('malformed', 'invalid', 0)]:
            case = out / name
            case.mkdir()
            events, errors, waits = [], [], []
            restart = None
            if mode == 'old':
                shutil.copytree(out / 'restart500/peer', case / 'peer')
                info = json.loads((case / 'peer/peer.json').read_text())
                info['base'] = str(case / 'peer/base.img')
                (case / 'peer/peer.json').write_text(json.dumps(info))
                shutil.copytree(out / 'restart500/outbox', case / 'outbox')
                start_peer(case)
            else:
                initialize(case / 'peer', writer=91)
                (case / 'outbox').mkdir(mode=0o700)
                if mode == 'lost':
                    peer = start_peer(case, True)

                    def later():
                        try:
                            require(peer.wait(timeout=15) == 0, 'lost-reply peer did not exit')
                            events.append({'event': 'persisted_lost_reply_peer_exit',
                                           'host_seconds': time.monotonic() - began})
                            time.sleep(0.5)
                            start_peer(case)
                            events.append({'event': 'peer_restarted', 'host_seconds': time.monotonic() - began})
                        except BaseException as error:
                            errors.append(repr(error))
                    restart = threading.Thread(target=later)
                    threads.append(restart)
                    restart.start()
            helper = ROOT / 'sim/companion/os_io.py'
            if mode == 'invalid':
                helper = case / 'invalid-receipt.py'
                helper.write_text('import os,sys\nfrom pathlib import Path\n'
                    'if len(sys.argv)>1 and sys.argv[1]=="wire":\n'
                    ' with Path(' + repr(str(case / 'wire-calls')) + ').open("a") as f:f.write("wire\\n")\n'
                    ' print("00")\nelse:\n'
                    ' os.execv(sys.executable,[sys.executable,' + repr(str(ROOT / 'sim/companion/os_io.py')) + ']+sys.argv[1:])\n')
            environment = dict(env, LEMMA_POLICY4_SOCKET=str(case / 'peer.sock'),
                LEMMA_POLICY4_OUTBOX=str(case / 'outbox'), LEMMA_POLICY4_HELPER=str(helper),
                LEMMA_POLICY4_SPENT=str(spent))
            for label in ('lean', 'clock'):
                handle = (case / (label + '.err')).open('xb')
                handles.append(handle)
                command = out / 'exchange-fixture' if label == 'lean' else clock_binary
                process = subprocess.Popen([str(command)], env=environment, cwd=ROOT, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=handle, text=True, start_new_session=True)
                procs.append(process)
                if label == 'lean': client = process
                else: clock = process
            with (case / 'raw.log').open('x') as raw:
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0 and select.select([client.stdout], [], [], remaining)[0], 'host property deadline')
                    line = client.stdout.readline().strip()
                    raw.write(line + '\n'); raw.flush()
                    require(line, 'Lean fixture exited before result')
                    if line.startswith('RESULT '): break
                    words = line.split()
                    require(len(words) == 2 and words[0] == 'WAIT' and words[1] in ('1000', '100000'), 'unexpected raw boundary')
                    clock.stdin.write(line + '\n'); clock.stdin.flush()
                    require(select.select([clock.stdout], [], [], max(0, deadline-time.monotonic()))[0], 'controller deadline')
                    reply = clock.stdout.readline().strip().split()
                    require(len(reply) == 3 and reply[0] == 'WAIT_DONE' and int(reply[2])-int(reply[1]) == int(words[1]), 'actual controller clock mismatch')
                    waits.append({'command': line, 'controller_before': int(reply[1]), 'controller_after': int(reply[2])})
                    client.stdin.write('WAIT_DONE\n'); client.stdin.flush()
            for process in (client, clock):
                process.stdin.close(); process.wait(timeout=10)
                require(process.returncode == 0, 'property subprocess failure')
            if restart:
                restart.join(timeout=15)
                require(not restart.is_alive() and not errors, 'restart failed: ' + repr(errors))
            require(not (case / 'lean.err').read_text() and not (case / 'clock.err').read_text(), 'property stderr')
            rows = opaque_log(case / 'peer/opaque.log') if (case / 'peer/opaque.log').exists() else []
            data = (case / 'outbox/outbox').read_bytes()
            pending, next_sequence = int.from_bytes(data[24:32], 'little'), int.from_bytes(data[16:24], 'little')
            ticks = sum(int(row['command'].split()[1]) for row in waits)
            observation = {'name': name, 'result': line, 'actual_wait_clocks': ticks,
                'events': events, 'peer_effects': len(rows), 'outbox_next': next_sequence,
                'outbox_pending_bytes': pending, 'outbox_sha256': sha(case / 'outbox/outbox')}
            (case / 'waits.json').write_text(json.dumps(waits, indent=2) + '\n')
            (case / 'observation.json').write_text(json.dumps(observation, indent=2) + '\n')
            report['cases'].append(observation)
            if mode in ('lost', 'old'):
                require(line.startswith('RESULT ACK NEXT 2 ERROR 0 ') and len(rows) == 1 and pending == 0, 'durable result did not reconcile')
                if mode == 'lost': require(events and waits, 'real uncertainty was not exercised')
                else: require(not waits, 'old receipt unexpectedly retried')
            else:
                require(line.startswith('RESULT REJECT ') and pending == 72 and next_sequence == 1 and not rows, 'uncertain receipt created acknowledged success')
                if mode == 'absent':
                    require('USB opaque operation Pending budget' in line and ticks == 100000000-spent, 'shared Pending clock bound differs')
                else:
                    require('USB malformed durable receipt retry bound' in line and ticks == 200000 and
                            len((case / 'wire-calls').read_text().splitlines()) == 3, 'malformed retry precedence differs')
            for process in procs: stop(process)
        validate(prepared)
        require(report['inputs'] == {name: sha(ROOT / name) for name in fixture_inputs}, 'qualification sources changed')
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        for thread in threads: thread.join(timeout=15)
        for process in procs: stop(process)
        for handle in handles: handle.close()
        report['host_seconds'] = time.monotonic() - began
        report['owned_children_reaped'] = all(p.poll() is not None for p in procs)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
