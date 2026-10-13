#!/usr/bin/env python3
"""Cold USB8 recovery from a frozen acknowledged peer, using hosted policy4."""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time

from check_guest_usb_notebook import Checker, NativeUSBSession, copy_opaque_peer, materialize_observation
from check_guest_usb_notebook import committed_bytes, expected_stroke, recover
from check_guest_usb_link import decode_capture, require, sha
from lemmasim_companion import validate as validate_companion
from lemmasim_usb_pending import validate

ROOT = Path(__file__).resolve().parents[1]


class ColdChecker(Checker):
    def _start_peer(self, drop):
        require(drop == 0, 'cold peer does not inject or manufacture an outcome')
        record = validate(self.args.host_prepared)
        legacy = json.loads(Path(record['legacy_prepared']['path']).read_text())
        companion = Path(legacy['companion_prepared']['path'])
        validate_companion(companion)
        log = (self.out / 'peer.log').open('xb'); self.peer_logs.append(log)
        command = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'companion', 'serve',
                   '--prepared', str(companion), '--directory', str(self.peer), '--socket', str(self.socket)]
        self.peer_argv.append(command)
        self.peer_process = subprocess.Popen(command, cwd=ROOT, stdout=log,
            stderr=subprocess.STDOUT, start_new_session=True)
        until = time.monotonic() + 15
        while not self.socket.exists():
            require(self.peer_process.poll() is None and time.monotonic() < until, 'private cold peer startup')
            time.sleep(0.005)
        return self.peer_process


def execute(args):
    require(args.expected_source_sha == sha(__file__), 'cold observer source differs from supervised manifest')
    args.profile = 'lemma-silicon-dev/0.8.0'
    args.cold_cycles, args.cold_deadline = 1600000000, 7200
    args.ink_cycles, args.action_cycles, args.action_deadline = 200000000, 1600000000, 7200
    checker = ColdChecker(args)
    checker.report.update(schema='lemma-usb8-acknowledged-cold/1',
        scope='new CPU cold recovery from current observational opaque receipt boundary; policy4 actual guest transport; no snapshot restore',
        observer_sha256=sha(__file__), status='RUNNING')
    before = time.monotonic()
    def cancelled(_signal, _frame): raise KeyboardInterrupt('explicit supervised cancellation')
    signal.signal(signal.SIGTERM, cancelled); signal.signal(signal.SIGINT, cancelled)
    try:
        directory = args.boundary.resolve()
        boundary_path = directory / 'boundary.json'
        boundary = json.loads(boundary_path.read_text())
        require(boundary['status'] == 'PASS' and boundary['source_before_after_equal'] is True and
                boundary['high_water'] == 36 and boundary['saved_sequence'] == 5,
                'unqualified acknowledged archive boundary')
        for name, identity in boundary['files'].items():
            path = directory / name
            require(path.is_file() and not path.is_symlink() and path.stat().st_size == identity['bytes'] and
                    sha(path) == identity['sha256'], 'acknowledged boundary file mismatch')
        reference = Path(boundary['reference_suffix']['path'])
        require(sha(reference) == boundary['reference_suffix']['sha256'], 'retained suffix receipt differs')
        expected_identity = json.loads(reference.read_text())['identity']
        validate(args.host_prepared)
        copy_opaque_peer(directory / 'peer', checker.peer, directory / 'outbox', checker.outbox)
        observed = checker.out / 'before.raw'; materialize_observation(checker.peer, observed)
        require(sha(observed) == boundary['files']['acknowledged.raw']['sha256'], 'private cold backing bytes differ')
        _, sequence, records = recover(observed.read_bytes())
        require(sequence == 5 and set(records) == {(1, 1), (1, 257), (1, 65539)} and
                records[(1, 1)].sequence == 5 and records[(1, 257)].sequence == 4 and
                records[(1, 65539)].sequence == 3, 'independent committed journal identity differs from Saved5')
        data = records[(1, 65539)].payload
        require(len(data) == 344 and struct.unpack_from('<3Q', data) == (0x314b4e49414d454c, 1, 3),
                'acknowledged raw ink format differs')
        samples = [struct.unpack_from('<9Q', data, 128 + 72 * index) for index in range(3)]
        expected, points = expected_stroke(samples)
        checker.report.update(boundary={'path': str(boundary_path), 'sha256': sha(boundary_path),
            'kind': boundary['boundary'], 'peer_high_water': 36, 'saved_sequence': 5},
            independently_observed_black_points=points, initial_peer_log_sha256=sha(checker.peer / 'opaque.log'),
            host_policy='lemma-usb-pending-policy/4')
        checker.start_peer()
        cold = NativeUSBSession(checker, 'cold', checker.peer, checker.outbox)
        require(cold.identity == expected_identity, 'cold machine changed admitted guest/native identities')
        checker.report['identity'] = cold.identity; checker.report['argv'] = cold.argv
        checker.update()
        cold.boot(expected)
        require(not any(row[0] in (0x41f, 0x423, 0x424) for row in cold.records()),
                'cold guest formatted, republished or failed instead of recovering')
        recovered = checker.out / 'after.raw'; materialize_observation(checker.peer, recovered)
        require(committed_bytes(recovered) == committed_bytes(observed) and sha(recovered) == sha(observed) and
                sha(checker.peer / 'opaque.log') == checker.report['initial_peer_log_sha256'],
                'cold guest changed acknowledged medium or peer receipt state')
        checker.report.update(status='PASS', new_cpu=True, restored_machine=False,
            exact_acknowledged_bytes=True, complete_controller_pixels_equal=True,
            clean_load_without_new_save=True, peer_receipt_state_unchanged=True,
            wire=decode_capture(cold.directory / 'usb.raw', probe=False,
                writer=boundary['writer'], initial_sequence=boundary['high_water'] + 1))
    except BaseException as error:
        checker.report.update(status='FAIL', error=repr(error))
        if checker.sessions:
            try: checker.report['failure_machine'] = checker.sessions[-1].machine()
            except BaseException as observer: checker.report['failure_observer_error'] = repr(observer)
    finally:
        for session in checker.sessions: session.close()
        checker.stop_peer()
        for log in checker.peer_logs: log.close()
        checker.commands.close(); checker.progress.close()
        checker.report.update(host_seconds=time.monotonic() - before,
            owned_children_reaped=all(s.process.poll() is not None for s in checker.sessions) and
                (checker.peer_process is None or checker.peer_process.poll() is not None))
        checker.update()
    return 0 if checker.report['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('launch', '_run'))
    for name in ('boundary', 'host-prepared', 'native-bundle', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-source-sha')
    args = parser.parse_args()
    if args.action == '_run': return execute(args)
    work = args.work_dir.resolve(); supervisor = work.with_name(work.name + '.supervision')
    require(not work.exists() and not supervisor.exists() and work.is_relative_to(ROOT / 'build'),
            'unused owned cold and supervision directories required')
    supervisor.mkdir(mode=0o700)
    started = time.time_ns()
    command = [sys.executable, str(Path(__file__).resolve()), '_run', '--expected-source-sha', sha(__file__)]
    for name in ('boundary', 'host_prepared', 'native_bundle', 'work_dir'):
        command += ['--' + name.replace('_', '-'), str(getattr(args, name).resolve())]
    manifest = {'schema': 'lemma-usb-cold-boundary-supervision/1', 'work_dir': str(work), 'argv': command,
        'supervisor_sha256': sha(ROOT / 'scripts/supervise_usb_notebook.py'),
        'observer_sha256': sha(ROOT / 'scripts/check_guest_usb_notebook.py'),
        'cold_observer_sha256': sha(__file__), 'base_observer_source': 'scripts/check_guest_usb_notebook.py',
        'started_unix_ns': started, 'absolute_deadline_unix_ns': started + 7400 * 1000000000,
        'whole_host_ceiling_seconds': 7400,
        'policy': {'automatic_restart': False, 'pause': 'no pause/drain to manufacture persistence',
                   'cold': '1.6Bcycles/7200seconds original ceiling;200seconds startup/cleanup overhead',
                   'external_wall_timeout': 'unchanged60s actual raw host timeout',
                   'cancellation': 'SIGTERM recorded supervisor; owned descendants only'}}
    path = supervisor / 'manifest.json'; path.write_text(json.dumps(manifest, indent=2) + '\n')
    log = (supervisor / 'supervisor.log').open('xb')
    process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/supervise_usb_notebook.py'), '_run', str(path)],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    log.close()
    from supervise_usb_notebook import identity
    print(json.dumps({'supervisor': identity(process.pid), 'manifest': str(path),
                      'absolute_deadline_unix_ns': manifest['absolute_deadline_unix_ns']}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
