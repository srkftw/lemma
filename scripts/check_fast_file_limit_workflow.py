#!/usr/bin/env python3
"""Real fast guest failed Save, opaque outcome replay and independent cold recovery.

Uses a private QEMU migration branch for the host fault. This does not qualify
arbitrary cached-state continuation or canonical RTL timing. No target policy,
ink, journal recovery or document construction runs in this observer.
"""
import argparse
import errno
import filecmp
import json
import os
from pathlib import Path
import resource
import shutil
import struct
import sys
import time

from check_live_notebook import Checker, Input, guest_events, idle, require, sha, visible_pixels
from check_fast_backing_replay import captured_entries
from check_canonical_pen_pixels import expected_stroke
from notebook_pixels import empty_pixels
from store_oracle import recover
import lemmasim_file_limit as fault


def write_prefixes(wire):
    """Opaque outcome bytes, after captured_entries checked every CRC/bound."""
    at = 72
    while at < len(wire):
        tag, size = struct.unpack_from('<2Q', wire, at); at += 16
        data = wire[at:at + size]; at += size
        if tag == 1:
            fields = struct.unpack_from('<7Q', data)
            if fields[2] == 1:
                start = 56 + fields[4]
                yield fields[3], data[start:start + fields[5]]


class FileLimitChecker(Checker):
    profile = 'lemma-silicon-dev/0.3.0'

    def launch(self, args, **kwargs):
        args = list(args)
        if getattr(self, 'replay_arguments', None) is not None and args[0] == 'session':
            at = args.index('--disk'); del args[at:at + 2]
            args += ['--restore', str(self.replay_arguments[0]),
                     '--backing-replay', str(self.replay_arguments[1])]
        return super().launch(args, **kwargs)

    def phase(self, session, name, cap, predicate):
        before = session.inspect()['machine']['cycle']; started = time.monotonic()
        while True:
            state = session.inspect()['machine']
            used = state['cycle'] - before
            require(0 <= used <= cap and time.monotonic() < self.deadline and
                    time.monotonic() - started < 180, 'predeclared phase/whole bound: ' + name)
            require(not state['finished'], 'guest stopped: ' + name)
            if predicate(state): break
            require(used < cap, 'predeclared execution ceiling: ' + name)
            session.run(min(1000000, cap - used))
        self.report['phases'].append({'name': name, 'execution_units': used,
                                     'seconds': time.monotonic() - started,
                                     'execution_cap': cap, 'host_cap': 180})
        self.report['execution_units'] += used
        require(self.report['execution_units'] <= 1000000000, 'aggregate execution ceiling')
        self.progress()
        return state

    def progress(self):
        (self.directory / 'progress.json').write_text(json.dumps(self.report, default=str, indent=2) + '\n')

    def execute(self):
        self.report.update(status='RUNNING', scope=__doc__, phases=[], execution_units=0,
                           relation='Exact admitted I/O, guest outputs, pixels and backing only; cached-state gap remains open')
        original = self.args.disk.read_bytes(); root, sequence, records = recover(original)
        require(sequence == 32 and root.checkpoint_count == root.checkpoint_tail == 0,
                'fixed actual acknowledged32 append-only source required')
        last = max(records.values(), key=lambda r: r.sequence)
        append = (last.sector + (len(last.payload) + 511) // 512 + 2) * 512
        require(original[append:append + 512] == bytes(512), 'first unused header is not empty')
        limit = append + 512 + 256
        self.report.update(source_sha256=sha(self.args.disk), sequence=sequence, byte_limit=limit,
                           helper_sha256=sha(Path(fault.__file__)), observer_sha256=sha(__file__))
        golden = bytearray(empty_pixels(1650, 2200, status='SAVED', namespace=1, page=1, brush=2))
        for record in records.values():
            p = record.payload
            if len(p) >= 128 and struct.unpack_from('<3Q', p) == (0x314b4e49414d454c, 1, 3):
                n = struct.unpack_from('<Q', p, 48)[0]
                require(len(p) == 128 + n * 72, 'source raw extent')
                samples = [struct.unpack_from('<9Q', p, 128 + i * 72) for i in range(n)]
                for x, y in expected_stroke(samples)[1]: golden[(y * 1650 + x) * 3:(y * 1650 + x) * 3 + 3] = bytes(3)
        disk = self.directory / 'base.raw'; shutil.copyfile(self.args.disk, disk)
        live = self.session('live', disk)
        def ready(s):
            return idle(s) and any(r[0] == 0x420 for r in guest_events(live.directory / 'uart-0.bin'))
        self.phase(live, 'first-cold-Ready', 300000000, ready)
        home, untouched = live.export('first-ready')
        require(visible_pixels(home) == (1650, 2200, bytes(golden)) and
                filecmp.cmp(untouched, self.args.disk, shallow=False), 'complete first home/backing')
        snapshot = live.snapshot('before-fault')
        live.control({'action': 'restore', 'path': str(snapshot)})
        _, native, observed = fault.owned_native(live.directory)
        active = fault.qemu_private_medium(live.directory, native).parent
        before = observed['machine']; first_id = before['storage']['backing_next_id']
        self.report['identity'] = observed['identity']
        token_path = self.directory / 'fault-token.json'
        token = self.command(['file-limit', 'apply', '--session-dir', str(live.directory),
                              '--bytes', str(limit), '--token', str(token_path)], True)
        require(live.inspect()['machine'] == before, 'fault admission advanced or changed VM state')
        stream = Input(1650, 2200, before['ticks'] + 10000, 100000, 0)
        stream.stroke('provisional-annotation', 1, 1, 3, 1800)
        expected = bytearray(golden)
        for x, y in expected_stroke(stream.events)[1]: expected[(y * 1650 + x) * 3:(y * 1650 + x) * 3 + 3] = bytes(3)
        failed = empty_pixels(1650, 2200, status='FAILED', namespace=1, page=1, brush=2)
        for y in range(132, 148):
            at = (y * 1650 + 24) * 3; end = (y * 1650 + 360) * 3
            expected[at:end] = failed[at:end]
        panel = self.directory / 'failed-wait.ppm'
        restored = False
        try:
            live.admit(stream.events)
            def failed_done(s):
                nonlocal restored
                rows = guest_events(next(active.glob('uart-*.bin')))
                require(not any(r[0] == 0x421 for r in rows), 'failed write manufactured Saved')
                if not (idle(s) and any(r[0] == 0x424 and r[1] == 227 for r in rows)): return False
                # RLIMIT_FSIZE also covers QEMU's screendump output. Clear
                # the real fault after observing Failed, before a large export.
                if not restored:
                    self.command(['file-limit', 'restore', '--token', str(token_path)], True)
                    restored = True
                live.control({'action': 'panel', 'path': str(panel)})
                return visible_pixels(panel) == (1650, 2200, bytes(expected))
            end = self.phase(live, 'actual-pwrite-EFBIG-Failed-ink', 150000000, failed_done)
        finally:
            if not restored:
                primary = sys.exc_info()[0] is not None
                try:
                    self.command(['file-limit', 'restore', '--token', str(token_path)], True)
                except BaseException as cleanup:
                    self.report['cleanup_error'] = repr(cleanup)
                    if not primary: raise
        failed_panel, medium = live.export('failed')
        wire, rows = captured_entries(next(active.glob('backing-*.io')), first_id)
        errors = [r for r in rows if r[0][6]]
        require(len(errors) == 1 and errors[0][0][2:] == (1, append + 512, 512, 256, errno.EFBIG),
                'actual partial pwrite error differs')
        actual = medium.read_bytes(); expected_bytes = bytearray(original)
        for offset, payload in write_prefixes(wire):
            expected_bytes[offset:offset + len(payload)] = payload
        require(actual == expected_bytes and actual != original, 'all observed persisted prefix bytes')
        _, seq, retained = recover(actual)
        require(seq == sequence and retained == records, 'unacknowledged prefix changed acknowledged records')
        tape = self.directory / 'selected.io'; tape.write_bytes(wire)
        external = self.directory / 'external.jsonl'; shutil.copyfile(live.directory / 'external.jsonl', external)
        suffix_uart = next(active.glob('uart-*.bin')).read_bytes()
        suffix_raw = next(active.glob('input-*.bin')).read_bytes()
        self.report['actual_fault'] = {'operations': len(rows), 'error': list(errors[0][0]),
            'all_medium_bytes': len(actual), 'changed_bytes': sum(a != b for a, b in zip(actual, original)),
            'all_controller_pixels': 3630000, 'Saved': False, 'token_cycle': token['cycle']}
        live.close(); self.sessions.remove(live)
        self.replay_arguments = (snapshot, tape)
        replay = self.session('replay', snapshot / 'durable.raw')
        replay_before = replay.inspect()['machine']; replay_started = time.monotonic()
        replay.control({'action': 'replay', 'snapshot': str(snapshot), 'capture': str(external), 'until_ns': end['virtual_ns']})
        replay_after = replay.inspect()['machine']
        replay_units = replay_after['cycle'] - replay_before['cycle']
        require(replay_after['virtual_ns'] == end['virtual_ns'] and 0 <= replay_units <= 150000000 and
                time.monotonic() - replay_started < 180, 'predeclared exact replay endpoint/bound')
        self.report['execution_units'] += replay_units
        require(self.report['execution_units'] <= 1000000000, 'aggregate including replay')
        self.report['phases'].append({'name': 'recorded-failure-replay', 'execution_units': replay_units,
            'seconds': time.monotonic() - replay_started, 'execution_cap': 150000000, 'host_cap': 180})
        rp, rm = replay.export('replayed')
        current = sorted(replay.directory.glob('machine-fork-*'))[-1]
        replay_wire, replay_rows = captured_entries(next(current.glob('backing-*.io')), first_id)
        require(replay_wire == wire and replay_rows == rows, 'every admitted recorded outcome/byte/boundary')
        require(next(current.glob('uart-*.bin')).read_bytes() == suffix_uart and
                next(current.glob('input-*.bin')).read_bytes() == suffix_raw, 'guest UART/raw replay suffix')
        require(filecmp.cmp(rm, medium, shallow=False) and visible_pixels(rp) == visible_pixels(failed_panel),
                'all replay backing/controller pixels')
        replay.close(); self.sessions.remove(replay); self.replay_arguments = None
        cold_disk = self.directory / 'cold-input.raw'; shutil.copyfile(medium, cold_disk)
        cold = self.session('cold', cold_disk)
        require(cold.inspect()['machine']['cycle'] == 0, 'independent cold CPU must start0')
        self.phase(cold, 'independent-cold-Ready', 300000000,
                   lambda s: idle(s) and any(r[0] == 0x420 for r in guest_events(cold.directory / 'uart-0.bin')))
        cp, cm = cold.export('cold-ready')
        require(visible_pixels(cp) == (1650, 2200, bytes(golden)) and filecmp.cmp(cm, medium, shallow=False),
                'complete cold home/backing; provisional ink must be absent')
        inputs = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        inputs.sample(1370, 64, 2048, True); inputs.sample(1370, 64, 0, False); cold.admit(inputs.events)
        self.phase(cold, 'explicit-Save32', 100000000,
                   lambda s: idle(s) and any(r[0] == 0x421 and r[1] == sequence for r in guest_events(cold.directory / 'uart-0.bin')))
        require(sha(self.args.disk) == self.report['source_sha256'], 'source medium changed')
        self.report.update(status='PASS_REAL_FAST_PWRITE_FAILURE_REPLAY_INDEPENDENT_COLD_SAVE32',
                           all_cold_home_pixels=3630000, all_backing_bytes=268435456)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('disk', 'native-bundle', 'work-dir'): p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args(); args.disk = args.disk.resolve(); args.native_bundle = str(args.native_bundle.resolve())
    args.timeout = 120; args.deadline = 900; args.checkpoint_relation = 'functional-I/O-only-cached-state-gap'; args.durable_suffix_from = None
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30)); resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    c = FileLimitChecker(args)
    try: c.execute()
    except BaseException as e: c.report.update(status='FAIL', error=repr(e)); raise
    finally:
        for s in reversed(c.sessions): s.close()
        c.commands.close(); c.report['seconds'] = time.monotonic() - c.started
        (c.directory / 'result.json').write_text(json.dumps(c.report, default=str, indent=2) + '\n')
    print(c.report['status'])


if __name__ == '__main__': main()
