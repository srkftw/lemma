#!/usr/bin/env python3
"""Connected native USB6 Surface-v2 notebook, durable peer and cold recovery.

Only raw pen input and raw transport faults enter the machine. Opaque peer
bytes are inspected offline, never interpreted or repaired for the guest.
The declared cold/action ceilings are resource bounds, not timing WCETs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time

from check_guest_usb_store import opaque_log
from check_guest_usb_link import ROOT, crc64, decode_capture, guest_events, request, require, sha
from lemmasim_companion import initialize, peer_info, validate as validate_companion
from lemmasim_usb import validate as validate_host
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_live_notebook import observe_workflow
from check_notebook_workflow import committed_bytes, visible_pixels
from check_canonical_pen_pixels import expected_stroke
from notebook_input import Input
from notebook_pixels import empty_pixels
from store_oracle import recover


def copy_opaque_peer(source, destination, outbox_source, outbox_destination):
    """Copy retained opaque media/receipts; no document parser is involved."""
    info = peer_info(source)
    rows = opaque_log(source / 'opaque.log')
    require(rows, 'source peer has no persistent receipt state')
    initialize(destination, base=source / 'base.img', writer=info['writer'])
    shutil.copyfile(source / 'opaque.log', destination / 'opaque.log')
    outbox = (outbox_source / 'outbox').read_bytes()
    require(len(outbox) == 40 and struct.unpack('<4Q', outbox[:32])[:2] ==
            (0x313054554f434d4c, info['writer']) and
            int.from_bytes(outbox[16:24], 'little') == rows[-1][0][4] + 1 and
            int.from_bytes(outbox[24:32], 'little') == 0 and
            crc64(outbox[:-8]) == int.from_bytes(outbox[-8:], 'little'),
            'source outbox has unresolved or corrupt external work')
    outbox_destination.mkdir(mode=0o700)
    (outbox_destination / 'outbox').write_bytes(outbox)
    # Both copies are completed before starting the independent peer/client.
    for p in (destination / 'opaque.log', outbox_destination / 'outbox'):
        with p.open('rb') as f: os.fsync(f.fileno())
    for p in (destination, outbox_destination):
        descriptor = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    return info['writer']


def owned_resources(process):
    """Sample only a child's current descendant tree, without global process scans.

    VmHWM is an individual process high-water mark; simultaneous resident bytes
    are sampled separately and are not described as a summed peak measurement.
    The result is host use, separate from the declared guest RAM/frame pool.
    """
    pending, seen, rows = [process.pid], set(), []
    while pending:
        pid = pending.pop()
        if pid in seen: continue
        seen.add(pid)
        require(len(seen) <= 64, 'owned child process count exceeded bound')
        path = Path('/proc') / str(pid)
        try:
            fields = {}
            for line in (path / 'status').read_text().splitlines():
                name, _, value = line.partition(':'); fields[name] = value.strip()
            rows.append({'pid': pid, 'resident_kib': int(fields.get('VmRSS', '0 kB').split()[0]),
                         'process_highwater_kib': int(fields.get('VmHWM', '0 kB').split()[0]),
                         'threads': int(fields.get('Threads', '0'))})
            pending.extend(int(p) for p in (path / 'task' / str(pid) / 'children').read_text().split())
        except (FileNotFoundError, ProcessLookupError):
            continue  # A child may exit between these observational reads.
    return {'processes': rows, 'sampled_resident_kib': sum(row['resident_kib'] for row in rows),
            'sampled_threads': sum(row['threads'] for row in rows)}


def explicit_save_completed(records, begin):
    """An earlier autosave cannot stand in for the newly admitted toolbar Save."""
    new = [row for row in records[begin:] if row[0] in (0x421, 0x423, 0x424)]
    pending = [i for i, row in enumerate(new) if row[0] == 0x423 and row[2:] == (1, 1, 0)]
    return bool(pending and new and new[-1][0] == 0x421 and
                new[-1][2:] == (1, 1, 0) and
                not any(row[0] == 0x424 for row in new) and
                any(new[i][1] == new[-1][1] for i in pending if i < len(new) - 1))


def initial_publication_completed(records):
    """The initial document-root receipt must precede the later fault scenario.

    Ready follows display acceptance while the independent Store call can still
    be pending. A later valid initial ACK is not an ACK for the new raw stroke.
    """
    commits = [row for row in records if row[0] in (0x421, 0x423, 0x424)]
    roots = [row for row in commits if row[0] == 0x423 and row[2:] == (1, 1, 1)]
    return bool(roots and commits and commits[-1] == (0x421, roots[-1][1], 1, 1, 0) and
                not any(row[0] == 0x424 for row in commits))


def materialize_observation(peer, output):
    """Observe every actually persisted prefix, including unacknowledged bytes.

    This private offline output is never attached to a live guest. A failed
    transaction is not assumed to roll back prior backing changes.
    """
    require(not output.exists(), 'opaque observation output already exists')
    base = peer / 'base.img'
    require(not base.is_symlink() and base.is_file() and base.stat().st_size == 268435456,
            'opaque base is not the complete declared backing medium')
    with base.open('rb') as source, output.open('xb') as target:
        copied = 0
        while True:
            b = source.read(1 << 20)
            if not b: break
            copied += len(b)
            if any(b): target.write(b)
            else: target.seek(len(b), os.SEEK_CUR)
        require(copied == 268435456, 'opaque base changed during observational copy')
        target.truncate(268435456)
        last = 0
        writer = peer_info(peer)['writer']
        for fields, payload in opaque_log(peer / 'opaque.log'):
            require(fields[2] in (1, 2) and fields[3] == writer and
                    fields[4] == last + 1 and fields[7] == 0,
                    'durable peer receipt ordering/identity differs')
            last = fields[4]
            if fields[2] == 1:
                require(len(payload) == fields[6] and fields[5] + len(payload) <= 268435456,
                        'actual persisted write outside medium')
                target.seek(fields[5]); target.write(payload)
            else:
                require(fields[5:7] == (0, 0) and not payload,
                        'barrier receipt contains invented backing data')
        target.flush(); os.fsync(target.fileno())
    return {'writer': writer, 'persisted_sequence': last,
            'bytes': output.stat().st_size}


class NativeUSBSession:
    def __init__(self, checker, name, peer, state):
        self.checker, self.name = checker, name
        self.directory = checker.out / name
        self.log = (checker.out / (name + '.log')).open('xb')
        self.view_generation, self.view = None, None
        args = checker.args
        cmd = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'session', '--backend', 'rtl',
               '--profile', args.profile, '--workload', 'usb-next-bulk-notebook' if args.profile=='lemma-silicon-dev/0.8.0' else 'usb-bulk-notebook',
               '--session-dir', str(self.directory), '--mode', 'laboratory', '--headless',
               '--paused', '--timeout', '120', '--quantum', '1000', '--trace-limit', '0',
               '--usb-host-prepared', str(args.host_prepared.resolve()),
               '--usb-peer-directory', str(peer), '--usb-peer-socket', str(checker.socket),
               '--usb-host-state', str(state)]
        if args.native_bundle is not None:
            cmd += ['--native-bundle', str(args.native_bundle.resolve())]
        else:
            cmd += ['--rtl-source-root', str(args.rtl_source_root.resolve()),
                    '--guest-source-root', str(args.guest_source_root.resolve())]
        self.argv = cmd
        self.process = subprocess.Popen(cmd, cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
        checker.sessions.append(self)
        end = time.monotonic() + 60
        while not (self.directory / 'session.json').exists():
            require(self.process.poll() is None and time.monotonic() < end,
                    'source-bound native USB notebook startup: ' + name)
            time.sleep(.02)
        initial = self.control({'action': 'inspect'})
        require(initial['running'] is False and initial['machine']['cycle'] == 0,
                'new native USB CPU did not start cold at reset')
        self.identity = initial['identity']
        self.start = initial['machine']

    def control(self, value):
        self.checker.commands.write(json.dumps({'session': self.name, 'request': value}) + '\n')
        self.checker.commands.flush()
        return request(self.directory, value, 130)

    def machine(self): return self.control({'action': 'inspect'})['machine']
    def records(self): return guest_events(self.directory / 'uart.bin')

    def pixels(self, state):
        generation = state['panel_completed']
        if self.view_generation != generation:
            p = self.directory / 'observed.ppm'
            self.control({'action': 'panel', 'path': str(p)})
            self.view = visible_pixels(p); self.view_generation = generation
        return self.view

    def wait(self, label, predicate, cycles, seconds, quantum=5000000, *, allow_failed_save=False):
        begin = self.machine()['cycle']; started = time.monotonic()
        while True:
            machine = self.machine()
            records = self.records()
            self.checker.sample_resources()
            require(not machine['finished'], label + ': native CPU finished')
            require(not any(r[0] in (0xff, 0xd4) for r in records), label + ': guest fatal/fault')
            require(allow_failed_save or not any(r[0] == 0x424 for r in records),
                    label + ': actual guest reported failed Save')
            task_ids = {r[1] for r in records if r[0] == 0xf1 and r[2] in (0, 1, 2)}
            require(not any(r[0] == 0xf4 and r[1] in task_ids for r in records),
                    label + ': selected Store/Notebook/Arithmetic task exited')
            require(not self.checker.restart_errors, 'peer restart failed: ' + str(self.checker.restart_errors))
            if predicate(machine, records):
                result = {'cycle': machine['cycle'], 'target_cycles': machine['cycle'] - begin,
                          'host_seconds': time.monotonic() - started, 'machine': machine}
                self.checker.report.setdefault('milestones', {})[self.name + '/' + label] = result
                self.checker.update(); return machine
            require(machine['cycle'] - begin < cycles and time.monotonic() - started < seconds,
                    label + ': predeclared cycle/host ceiling')
            self.checker.progress.write(json.dumps({'session': self.name, 'label': label,
                'cycle': machine['cycle'], 'host_seconds': time.monotonic() - started,
                'panel_completed': machine['panel_completed'], 'pc': machine['pc']}) + '\n')
            self.checker.progress.flush()
            require(self.checker.progress.tell() < 16 << 20, 'bounded progress trace exhausted')
            self.control({'action': 'run', 'cycles': min(quantum, cycles - (machine['cycle'] - begin))})

    def panel_matches(self, state, expected):
        return (state['paper_busy'] == state['pen_queue'] == state['event_queue'] ==
                state['panel_pending_pixels'] == 0 and state['panel_completed'] > 0 and
                self.pixels(state) == (1650, 2200, expected))

    def boot(self, expected):
        def ready(state, records):
            r = [row for row in records if row[0] == 0x420]
            full = [row for row in records if row[0] == 0x425]
            return (len(r) == 1 and r[0][1:4] == (1650 | (2200 << 32), 1, 1) and
                    full and full[-1][1] > 0 and state['panel_completed'] >= full[-1][1] and
                    self.panel_matches(state, expected))
        return self.wait('cold-ready', ready, self.checker.args.cold_cycles,
                         self.checker.args.cold_deadline)

    def admit(self, rows):
        for row in rows:
            self.control({'action': 'inject', 'kind': 'pen', 'cycle': row[1] * 10,
                          'words': list(row[1:8])})

    def close(self):
        if self.process.poll() is None:
            try: self.control({'action': 'destroy'}); self.process.wait(timeout=10)
            except BaseException:
                os.killpg(self.process.pid, signal.SIGTERM)
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL); self.process.wait(timeout=5)
        self.log.close()


class Checker:
    def __init__(self, args):
        self.args, self.out = args, args.work_dir.resolve()
        require(not self.out.exists() and self.out.is_relative_to(ROOT / 'build'), 'unused owned output')
        self.out.mkdir(parents=True)
        self.socket = self.out / 'peer.sock'
        self.peer, self.outbox = self.out / 'peer', self.out / 'outbox'
        self.sessions, self.peer_logs, self.peer_argv, self.restart_errors = [], [], [], []
        self.peer_process = self.first_peer = self.restart_thread = None
        self.peer_lock, self.closing = threading.Lock(), False
        self.commands = (self.out / 'commands.jsonl').open('x')
        self.progress = (self.out / 'progress.jsonl').open('x')
        self.started = time.monotonic()
        self.report = {'schema': 'lemma-usb-bulk-notebook-evidence/1', 'status': 'FAIL',
                       'scope': __doc__, 'bounds': {'cold_cycles': args.cold_cycles,
                         'cold_host_seconds': args.cold_deadline, 'ink_cycles': args.ink_cycles,
                         'redraw_save_cycles': args.action_cycles, 'action_host_seconds': args.action_deadline},
                       'bound_classification': 'resource ceilings declared before launching; not WCET',
                       'not_qualified': ['physical USB PHY/full USB', 'USB whole-machine snapshots',
                                         'browser hosted peer', 'owner authentication'],
                       'raw_capture_format': 'native-seven-text; sequence/epoch from actual guest raw objects',
                       'host_prepared': {'path': str(args.host_prepared.resolve()),
                                         'sha256': sha(args.host_prepared)},
                       'profile': args.profile,
                       'source_archives': ({'rtl': str(args.rtl_source_root.resolve()),
                                            'guest': str(args.guest_source_root.resolve())}
                                           if args.native_bundle is None else
                                           {'native_bundle': str(args.native_bundle.resolve()),
                                            'manifest_sha256': sha(args.native_bundle/'bundle.json')})}

    def update(self):
        self.report['host_seconds'] = time.monotonic() - self.started
        (self.out / 'result.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def sample_resources(self):
        for name, process in ([(s.name, s.process) for s in self.sessions] +
                              [('peer', self.peer_process)]):
            if process is None or process.poll() is not None: continue
            sample = owned_resources(process)
            observed = self.report.setdefault('host_resources', {}).setdefault(name, {})
            observed['sampled_tree_peak_resident_kib'] = max(
                observed.get('sampled_tree_peak_resident_kib', 0), sample['sampled_resident_kib'])
            observed['sampled_tree_peak_threads'] = max(
                observed.get('sampled_tree_peak_threads', 0), sample['sampled_threads'])
            observed['last_sample'] = sample
        self.report['observer_self_maxrss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def start_peer(self, drop=0):
        with self.peer_lock:
            require(not self.closing, 'campaign is closing; no new external peer')
            return self._start_peer(drop)

    def _start_peer(self, drop):
        companion = self.args.host_prepared.resolve().parent / 'companion/prepared.json'
        validate_companion(companion)
        log = (self.out / ('peer-' + str(len(self.peer_logs)) + '.log')).open('xb')
        self.peer_logs.append(log)
        cmd = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'companion', 'serve',
               '--prepared', str(companion), '--directory', str(self.peer), '--socket', str(self.socket)]
        if drop: cmd += ['--drop-reply', str(drop), '--exit-after-reply', str(drop)]
        self.peer_argv.append(cmd)
        self.peer_process = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
        end = time.monotonic() + 15
        while not self.socket.exists():
            require(self.peer_process.poll() is None and time.monotonic() < end, 'independent peer startup')
            time.sleep(.005)
        return self.peer_process

    def stop_peer(self):
        with self.peer_lock:
            if self.peer_process and self.peer_process.poll() is None:
                os.killpg(self.peer_process.pid, signal.SIGTERM)
                try: self.peer_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.peer_process.pid, signal.SIGKILL)
                    self.peer_process.wait(timeout=5)

    def action(self, live, stream, button, name, expected):
        current = live.machine(); stream.tick = current['ticks'] + 10000
        before_records = len(live.records())
        first = len(stream.events); stream.tool(button, name); live.admit(stream.events[first:])
        last_tick = stream.events[-1][1]
        return live.wait(name, lambda state, records: state['ticks'] >= last_tick + 2000000 and
                         (button != 7 or explicit_save_completed(records, before_records)) and
                         live.panel_matches(state, expected), self.args.action_cycles,
                         self.args.action_deadline)

    def execute(self):
        validate_host(self.args.host_prepared)
        writer = copy_opaque_peer(self.args.formatted_peer.resolve(), self.peer,
                                  self.args.formatted_outbox.resolve(), self.outbox)
        self.report['writer'] = writer
        before_medium = self.out / 'formatted-observation.raw'
        materialize_observation(self.peer, before_medium)
        _, sequence, objects = recover(before_medium.read_bytes())
        require(sequence == 0 and not objects, 'first notebook boot requires actual formatted empty journal')
        self.start_peer()
        live = NativeUSBSession(self, 'live', self.peer, self.outbox)
        self.report['identity'] = live.identity; self.report['live_argv'] = live.argv
        live.boot(empty_pixels(1650, 2200))
        # The caller's existing cold ceiling covers both Ready and the actual
        # initial root publication. Never schedule the lost-ACK scenario while
        # an earlier, unrelated durable receipt can still arrive.
        ready = self.report['milestones']['live/cold-ready']
        remaining_cycles = self.args.cold_cycles - ready['target_cycles']
        remaining_seconds = self.args.cold_deadline - ready['host_seconds']
        require(remaining_cycles > 0 and remaining_seconds > 0,
                'initial publication exhausted the original cold ceiling')
        live.wait('initial-publication-complete', lambda state, rows:
                  initial_publication_completed(rows) and live.panel_matches(state, empty_pixels(1650, 2200)),
                  remaining_cycles, remaining_seconds)
        self.stop_peer(); before_log = len(opaque_log(self.peer / 'opaque.log'))
        saved_before = sum(r[0] == 0x421 for r in live.records())
        # A344-byte raw chunk's Store-v1 append performs header/body/sentinel
        # writes, payload barrier, publication write and final barrier. The
        # actual peer log below independently validates this selected ordinal.
        self.first_peer = self.start_peer(drop=6)
        self.report['predeclared_lost_ack'] = {'completed_raw_reply_ordinal': 6,
            'operation_kinds': [1, 1, 1, 2, 1, 2], 'selected': 'final raw-chunk publication barrier',
            'before_peer_effects': before_log, 'before_saved_count': saved_before}
        def restart():
            try:
                require(self.first_peer.wait(timeout=self.args.action_deadline) == 0,
                        'selected lost-barrier peer did not exit')
                effects = opaque_log(self.peer / 'opaque.log')[before_log:]
                require(len(effects) == 6 and [f[2] for f, _ in effects] == [1, 1, 1, 2, 1, 2],
                        'selected lost ACK was not the declared actual journal barrier')
                ids = [f[4] for f, _ in effects]
                require(ids == list(range(ids[0], ids[0] + 6)), 'journal writer sequence changed')
                require(sum(r[0] == 0x421 for r in live.records()) == saved_before,
                        'Saved preceded lost-barrier reconciliation')
                self.report['lost_ack_boundary'] = {'receipt': list(effects[-1][0]),
                    'peer_log_sha256': sha(self.peer / 'opaque.log'),
                    'outbox_sha256': sha(self.outbox / 'outbox'), 'saved_count': saved_before}
                self.start_peer(); self.report['peer_restarted'] = True
            except BaseException as error:
                self.restart_errors.append(repr(error))
                self.report['restart_errors'] = list(self.restart_errors)
        self.restart_thread = threading.Thread(target=restart, daemon=True); self.restart_thread.start()
        stream = Input(1650, 2200, live.machine()['ticks'] + 10000, 100000, 0)
        stream.sample(825, 160, 0, False); stream.stroke('usb annotation', 1, 1, 3, 1200)
        live.admit(stream.events)
        expected, black = expected_stroke(stream.events[1:4])
        live.wait('raw-ink-reconciled', lambda state, rows: self.report.get('peer_restarted') and
                  sum(r[0] == 0x421 for r in rows) > saved_before and
                  live.panel_matches(state, expected), self.args.ink_cycles, self.args.action_deadline)
        self.action(live, stream, 3, 'undo', empty_pixels(1650, 2200))
        self.action(live, stream, 4, 'redo', expected)
        self.action(live, stream, 2, 'next-page', empty_pixels(1650, 2200, page=2))
        self.action(live, stream, 1, 'previous-page', expected)
        self.action(live, stream, 7, 'explicit-save', expected)
        acknowledged = self.out / 'acknowledged.raw'; materialize_observation(self.peer, acknowledged)
        panel = self.out / 'acknowledged.ppm'; live.control({'action': 'panel', 'path': str(panel)})
        wanted = {'pages': {'1': [1, 2]}, 'visible_strokes': {'1/1': ['usb annotation'], '1/2': []},
                  'required_edit_history': {'1/1': 1}}
        self.report['workflow'] = observe_workflow(acknowledged, live.directory / 'input.events',
                 live.directory / 'uart.bin', panel, stream, wanted, raw_format='native-seven-text')
        require(not self.restart_errors and self.report.get('peer_restarted'), 'lost ACK not reconciled')
        receipt = self.report['lost_ack_boundary']['receipt']
        require(sum(list(f) == receipt for f, _ in opaque_log(self.peer / 'opaque.log')) == 1,
                'retry duplicated the persisted barrier effect')
        self.report['live_wire'] = decode_capture(live.directory / 'usb.raw', probe=False, writer=writer)
        self.report['raw_input'] = {'events': stream.events, 'actions': stream.actions,
                                   'independent_black_points': black}
        live.close(); self.sessions.remove(live); self.stop_peer()
        self.start_peer(); cold = NativeUSBSession(self, 'cold', self.peer, self.outbox)
        require(cold.identity == live.identity, 'cold guest/native/controller artifact identities changed')
        cold.boot(expected)
        require(not any(r[0] in (0x41f, 0x423, 0x424) for r in cold.records()),
                'cold recovery formatted, republished or failed')
        recovered = self.out / 'cold.raw'; materialize_observation(self.peer, recovered)
        require(committed_bytes(recovered) == committed_bytes(acknowledged),
                'cold guest changed or lost acknowledged bytes')
        self.report['cold_recovery'] = {'status': 'PASS', 'new_cpu': True,
              'exact_acknowledged_bytes': True, 'complete_controller_pixels_equal': True,
              'clean_load_without_new_save': True, 'argv': cold.argv}
        # Disconnect before the next real guest append. Actual persistence is
        # inspected afterward; failed I/O is not interpreted as rollback.
        self.stop_peer(); failed_log = sha(self.peer / 'opaque.log')
        failed_saved = sum(r[0] == 0x421 for r in cold.records())
        offline = Input(1650, 2200, cold.machine()['ticks'] + 10000, 100000, 0)
        offline.sample(825, 160, 0, False); offline.stroke('disconnected annotation', 1, 1, 3, 1700)
        cold.admit(offline.events)
        _, offline_black = expected_stroke(offline.events[1:4])
        failed_expected = bytearray(empty_pixels(1650, 2200, status='FAILED'))
        for x, y in black + offline_black:
            failed_expected[(y * 1650 + x) * 3:(y * 1650 + x) * 3 + 3] = bytes(3)
        failure = cold.wait('unsuccessful-save', lambda state, rows: any(r[0] == 0x424 for r in rows) and
                 cold.panel_matches(state, bytes(failed_expected)),
                 self.args.action_cycles, self.args.action_deadline, allow_failed_save=True)
        require(sum(r[0] == 0x421 for r in cold.records()) == failed_saved,
                'disconnected write manufactured Saved')
        require(sha(self.peer / 'opaque.log') == failed_log,
                'disconnected absent peer unexpectedly retained new effects')
        failed_medium = self.out / 'after-failed-save.raw'; materialize_observation(self.peer, failed_medium)
        require(committed_bytes(failed_medium) == committed_bytes(acknowledged),
                'unsuccessful save corrupted acknowledged journal bytes')
        self.report['unsuccessful_save'] = {'status': 'PASS', 'new_saved_ack': False,
                   'retained_acknowledged_bytes': True, 'machine': failure,
                   'offline_ink_controller_pixels': offline_black,
                   'complete_failed_status_and_ink_pixels': True,
                   'guest_errors': [r for r in cold.records() if r[0] == 0x424]}
        self.report['status'] = 'PASS'

    def close(self):
        with self.peer_lock: self.closing = True
        for live in self.sessions:
            try: live.close()
            except BaseException as error: self.report.setdefault('cleanup_errors', []).append(repr(error))
        try: self.stop_peer()
        except BaseException as error: self.report.setdefault('cleanup_errors', []).append(repr(error))
        if self.first_peer and self.first_peer.poll() is None:
            try:
                os.killpg(self.first_peer.pid, signal.SIGTERM)
                try: self.first_peer.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(self.first_peer.pid, signal.SIGKILL); self.first_peer.wait(timeout=5)
            except BaseException as error: self.report.setdefault('cleanup_errors', []).append(repr(error))
        if self.restart_thread:
            self.restart_thread.join(timeout=10)
            if self.restart_thread.is_alive():
                self.report.setdefault('cleanup_errors', []).append('owned restart thread still running')
        for log in self.peer_logs: log.close()
        self.commands.close(); self.progress.close()
        if self.report.get('cleanup_errors'): self.report['status'] = 'FAIL'
        self.report['peer_argv'] = self.peer_argv; self.report['observer_sha256'] = sha(__file__)
        self.report['observer_self_maxrss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        self.report['reaped_children_maxrss_kib'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        files = [p.stat() for p in self.out.rglob('*') if p.is_file() and not p.is_symlink()]
        self.report['owned_disk'] = {'regular_files': len(files),
                                    'apparent_bytes': sum(p.st_size for p in files),
                                    'allocated_bytes': sum(p.st_blocks * 512 for p in files)}
        self.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('host-prepared', 'formatted-peer', 'formatted-outbox', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--profile', choices=('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0'), default='lemma-silicon-dev/0.6.0')
    parser.add_argument('--native-bundle', type=Path)
    parser.add_argument('--rtl-source-root', type=Path)
    parser.add_argument('--guest-source-root', type=Path)
    parser.add_argument('--cold-cycles', type=int, default=1600000000)
    parser.add_argument('--cold-deadline', type=int, default=7200)
    parser.add_argument('--ink-cycles', type=int, default=200000000)
    parser.add_argument('--action-cycles', type=int, default=1600000000)
    parser.add_argument('--action-deadline', type=int, default=7200)
    args = parser.parse_args()
    require((args.native_bundle is None and args.rtl_source_root is not None and args.guest_source_root is not None) or
            (args.profile=='lemma-silicon-dev/0.8.0' and args.native_bundle is not None and args.rtl_source_root is None and args.guest_source_root is None),
            'explicit complete source archives or one USB8 immutable bundle required')
    require(1 <= args.ink_cycles <= 200000000 and
            1 <= args.cold_cycles <= 1600000000 and 1 <= args.action_cycles <= 1600000000 and
            30 <= args.cold_deadline <= 7200 and 30 <= args.action_deadline <= 7200,
            'resource bounds exceed the declared workload ceilings')
    def cancel(signum, _frame):
        raise KeyboardInterrupt("explicit observer cancellation signal " + str(signum))
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    checker = Checker(args)
    try: checker.execute()
    except BaseException as error:
        checker.report['error'] = repr(error)
        for live in checker.sessions:
            try: checker.report.setdefault('failed_boundaries', {})[live.name] = live.control({'action': 'inspect'})
            except BaseException as observed: checker.report['failed_observation_error'] = repr(observed)
            # Preserve the real failed boundary before owned-process cleanup.
            # Snapshot/export are observational, never a poll, drain or replay.
            try:
                checkpoint = checker.out/(live.name+'-failure.snapshot')
                captured = live.control({'action':'snapshot','path':str(checkpoint)})
                checker.report.setdefault('failed_checkpoints',{})[live.name] = {
                    'path':str(checkpoint),'machine_sha256':sha(checkpoint/'machine.chk'),
                    'snapshot_sha256':sha(checkpoint/'snapshot.json'),'result':captured}
                tape = checker.out/(live.name+'-failure.usb.tape')
                live.control({'action':'export-usb-replay','path':str(tape)})
                checker.report['failed_checkpoints'][live.name]['tape']={'path':str(tape),'sha256':sha(tape)}
            except BaseException as observed:
                checker.report.setdefault('failed_checkpoint_errors',{})[live.name] = repr(observed)
        raise
    finally: checker.close()
    require(checker.report['status'] == 'PASS', 'owned process cleanup failed')
    print(json.dumps({'status': checker.report['status'], 'host_seconds': checker.report['host_seconds']}))


if __name__ == '__main__': main()
