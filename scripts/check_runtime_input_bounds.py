#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused real-machine raw-adapter resource-bound failures and exact budget restore.

The guest does not execute these UART fixtures; they test bounded external event
admission at a paused machine boundary, never notebook or storage semantics.
"""
from __future__ import annotations
import argparse
import hashlib
import struct
import json
import shutil
from pathlib import Path
import subprocess
import sys
import time
from check_machine_runtime import Session, equal_observation, sha, validate_build, validate_guest
ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = 32 * 1024 * 1024
LINE = PAYLOAD + 8192


def retained_bytes(path):
    # Independent LMSSRTL1 v1 byte inventory: 33 scalar words, three drive
    # phase counters, four privilege counters and five tagged scalar words.
    # It neither parses guest records nor calls the runtime's state reader.
    result = {}
    with path.open('rb') as f:
        if f.read(8) != b'LMSSRTL1':
            raise ValueError('Unexpected checkpoint format in byte observer')
        f.seek(112 + 45 * 8)
        def u64():
            raw = f.read(8)
            if len(raw) != 8:
                raise ValueError('Short inventory word')
            return struct.unpack('<Q', raw)[0]
        for _ in range(2):
            f.seek(u64(), 1)  # UART observer window and stop marker
        for name in ('ram', 'rom', 'target_and_latch', 'visible'):
            n = u64()
            if n > 256 * 1024 * 1024:
                raise ValueError('Invalid inventory vector size')
            h = hashlib.sha256()
            left = n
            nonwhite = False
            while left:
                part = f.read(min(left, 1024 * 1024))
                if not part:
                    raise ValueError('Short inventory vector')
                h.update(part)
                if name == 'visible' and any(v != 15 for v in part):
                    nonwhite = True
                left -= len(part)
            result[name] = {'size': n, 'sha256': h.hexdigest()}
            if name == 'visible':
                result[name]['nonwhite'] = nonwhite
        for name, size, bound in (('boot_pages', 4096, 32768),
                                  ('overlay', 512, 32768), ('durable', 512, 524288)):
            count = u64()
            if count > bound:
                raise ValueError('Invalid inventory map count')
            h = hashlib.sha256()
            for _ in range(count):
                raw = f.read(8 + size)
                if len(raw) != 8 + size:
                    raise ValueError('Short inventory map')
                h.update(raw)
            result[name] = {'count': count, 'sha256': h.hexdigest()}
    return result

def saved_pen_words(path):
    with path.open('rb') as f:
        f.seek(112 + 45 * 8)
        def u64():
            return struct.unpack('<Q', f.read(8))[0]
        for _ in range(2):
            f.seek(u64(), 1)
        for _ in range(4):
            f.seek(u64(), 1)
        for size in (4096, 512, 512):
            f.seek(u64() * (8 + size), 1)
        f.seek(u64() * 16, 1)  # pending optical pixels
        f.seek(u64(), 1)       # pending UART bytes
        found = None
        count = u64()
        for _ in range(count):
            u64()
            kind = f.read(u64())
            words = u64()
            offset = f.tell()
            values = [u64() for _ in range(words)]
            if kind == b'pen':
                if words != 7:
                    raise ValueError('Unexpected saved pen word count')
                found = (offset, values)
            f.seek(u64(), 1)
        if found is None:
            raise ValueError('No saved pen event in malformed-queue fixture')
        return found


def malformed_saved_pen(source, destination, offset):
    shutil.copyfile(source, destination)
    with destination.open('r+b') as f:
        f.seek(80)
        wrapper, _model, checksum, _model_checksum = struct.unpack('<QQQQ', f.read(32))
        f.seek(offset)
        old = f.read(8)
        new = struct.pack('<Q', 65536)
        tail = 112 + wrapper - offset - 8
        if not 0 <= tail <= 1024:
            raise ValueError('Malformed fixture pen is not near wrapper end')
        # CRC64-ECMA is linear with a zero initial state. Leading zero delta
        # bytes have CRC zero; update only the changed word and its suffix.
        delta = 0
        for byte in bytes(a ^ b for a, b in zip(old, new)) + bytes(tail):
            delta ^= byte << 56
            for _ in range(8):
                delta = ((delta << 1) ^ (0x42f0e1eba9ea3693 if delta >> 63 else 0)) & ((1 << 64) - 1)
        f.seek(offset)
        f.write(new)
        f.seek(96)
        f.write(struct.pack('<Q', checksum ^ delta))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rtl-build', type=Path, required=True)
    p.add_argument('--monitor', type=Path, required=True)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    a = p.parse_args()
    for key in ('rtl_build', 'monitor', 'rom', 'work_dir'):
        setattr(a, key, getattr(a, key).resolve())
    a.work_dir.mkdir(exist_ok=False, parents=True)
    report = {'status': 'FAIL', 'scope': 'paused RTL external event admission; no guest workload verdict',
              'checks': [], 'observer_sha256': sha(__file__)}
    session = None
    try:
        binary, build = validate_build(a.rtl_build)
        report['runtime_identity'] = build['snapshot_identity']
        report['runtime_sha256'] = sha(binary)
        report['guest'] = validate_guest(a.monitor)
        fixtures = a.work_dir / 'events'
        fixtures.mkdir()
        big = fixtures / 'oversized-file.events'
        with big.open('xb') as f:
            f.truncate(256 * 1024 * 1024 + 1)
        line = fixtures / 'oversized-line.events'
        with line.open('wb') as f:
            f.write(b'#' + b'x' * LINE + b'\n')
        aggregate = fixtures / 'oversized-payload.events'
        with aggregate.open('wb') as f:
            for _ in range(2):
                f.write(b'1000000 uart ' + b'00' * (PAYLOAD // 4) + b'\n')
            f.write(b'1000000 uart 00\n')
        words = fixtures / 'oversized-words.events'
        words.write_text('1000000 pen 1 2 3 4 5 6 7 8\n')
        range_cases = []
        for field, value in enumerate((65536, 65536, 4096, 16, 3, 8), 1):
            values = [0, 1, 1, 1, 1, 0, 0]
            values[field] = value
            path = fixtures / f'pen-range-{field}.events'
            path.write_text('1000000 pen ' + ' '.join(map(str, values)) + '\n')
            range_cases.append((path, 'pen sample field outside admitted range'))
        for path, expected in [(big, 'regular file'), (line, 'event line exceeds'),
                               (aggregate, 'event payload budget exceeded'),
                               (words, 'event word bound exceeded'), *range_cases]:
            argv = [str(binary), '--image', str(a.monitor / 'image.elf'), '--rom', str(a.rom),
                    '--uart-output', str(a.work_dir / (path.stem + '.uart')), '--events', str(path),
                    '--cycles', '0', '--quiet-uart']
            begin = time.monotonic()
            run = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=120)
            (a.work_dir / (path.stem + '.stderr')).write_bytes(run.stderr)
            if run.returncode != 1 or expected.encode() not in run.stderr or run.stdout:
                raise ValueError('Raw event fixture did not fail closed: ' + path.name)
            report['checks'].append({'name': path.name, 'status': 'PASS', 'argv': argv,
                                     'exit_code': run.returncode, 'seconds': time.monotonic() - begin,
                                     'size': path.stat().st_size, 'sha256': sha(path)})
        full = fixtures / 'full-budget.events'
        with full.open('wb') as f:
            for _ in range(2):
                f.write(b'1000000 uart ' + b'00' * (PAYLOAD // 4) + b'\n')
        session = Session(binary, a.monitor, a.rom, a.work_dir / 'paused', ['--events', full, '--memory-latency', '3'])
        before = session.call('run 12')
        if before['memory_pending'] != 1 or before['memory_wait'] != 1:
            raise ValueError('Fixture lacks a real CPU memory beat under backpressure')
        if before['event_queue'] != 2 or before['cycle'] != 12 or before['uart_queue']:
            raise ValueError('Fixture did not create the intended paused external queue')
        bad = session.call('inject 1000000 uart 00', failure=True)
        if 'event payload budget exceeded' not in bad['error'] or session.call('inspect') != before:
            raise ValueError('Aggregate rejection changed paused machine state')
        oversized = session.call('x' * (1024 * 1024), failure=True)
        if 'command length exceeds' not in oversized['error'] or session.call('inspect') != before:
            raise ValueError('Oversized command changed paused machine state')
        first = a.work_dir / 'full-budget.chk'
        second = a.work_dir / 'restored-budget.chk'
        session.call('snapshot ' + str(first))
        restored = session.call('restore ' + str(first))
        if not equal_observation(before, restored):
            raise ValueError('Restore changed the exact external event queue')
        bad = session.call('inject 1000000 uart 00', failure=True)
        if 'event payload budget exceeded' not in bad['error']:
            raise ValueError('Restored payload budget was not reconstructed')
        session.call('snapshot ' + str(second))
        if sha(first) != sha(second):
            raise ValueError('Rejected restored admission changed exact checkpoint bytes')
        for field, value in enumerate((65536, 65536, 4096, 16, 3, 8), 1):
            values = [0, 1, 1, 1, 1, 0, 0]
            values[field] = value
            rejected = session.call('inject 1000000 pen ' + ' '.join(map(str, values)), failure=True)
            if 'pen sample field outside admitted range' not in rejected['error'] or session.call('inspect') != restored:
                raise ValueError('Invalid pen field admission normalized input or changed state')
        session.call('inject 1000000 pen 18446744073709551615 65535 65535 4095 15 2 7')
        queued = session.call('inspect')
        if queued['event_queue'] != 3:
            raise ValueError('Future pen/UART cancellation fixture not admitted')
        prewarm = a.work_dir / 'pre-warm.chk'
        session.call('snapshot ' + str(prewarm))
        word_offset, raw_words = saved_pen_words(prewarm)
        if raw_words != [(1 << 64) - 1, 65535, 65535, 4095, 15, 2, 7]:
            raise ValueError('Saved raw pen sample lost an admitted field or timestamp width')
        malformed = a.work_dir / 'crc-valid-bad-pen.chk'
        malformed_saved_pen(prewarm, malformed, word_offset + 8)
        bad = session.call('restore ' + str(malformed), failure=True)
        if 'pen sample field outside admitted range' not in bad['error'] or session.call('inspect') != queued:
            raise ValueError('CRC-valid out-of-range saved queue was accepted or changed state')
        report['checks'].append({'name': 'raw-pen-range-and-saved-preflight', 'status': 'PASS',
                                 'fields': ['x', 'y', 'pressure', 'flags', 'tool', 'buttons'],
                                 'timestamp': raw_words[0], 'malformed_sha256': sha(malformed)})
        warm = session.call('warm-reset 8')
        if warm['cycle'] != queued['cycle'] or any(warm[k] for k in ('event_queue', 'pen_queue', 'uart_queue', 'memory_pending', 'memory_wait')):
            raise ValueError('Warm reset retained scheduled or pending adapter input')
        reset = session.call('run 8')
        postwarm = a.work_dir / 'post-warm.chk'
        session.call('snapshot ' + str(postwarm))
        retained = retained_bytes(prewarm)
        if retained != retained_bytes(postwarm):
            raise ValueError('Reset clocks changed retained RAM/visible/durable/overlay bytes')
        report['warm_retention'] = {'status': 'PASS', 'inventory': retained,
                                  'reset_cycles': reset['cycle'] - warm['cycle'],
                                  'scope': 'real pending CPU request and queued future pen/UART cancellation; visible is white and overlay/durable maps are empty'}
        admitted = session.call(f'inject {reset["cycle"] + 1000} uart 00')
        if admitted['event_queue'] != 1:
            raise ValueError('Warm reset did not release scheduled UART payload budget')
        cold = session.call('cold-cycle')
        if cold['event_queue']:
            raise ValueError('Cold cycle retained external events')
        admitted = session.call(f'inject {cold["cycle"] + 1000} uart 00')
        if admitted['event_queue'] != 1:
            raise ValueError('Cold cycle did not release the consumed payload budget')
        session.close()
        session = None
        report['checks'].append({'name': 'paused-budget-snapshot-restore-and-release', 'status': 'PASS',
                                 'payload_hex_bytes': PAYLOAD, 'checkpoint_sha256': sha(first),
                                 'scope': 'full pending event budget, over-budget/overlong-command rejection, exact restore, warm future pen/UART cancellation and warm/cold budget release'})
        report['status'] = 'PASS'
    except Exception as e:
        report['error'] = str(e)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as e:
                report['cleanup_error'] = str(e)
        (a.work_dir / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(a.work_dir / 'result.json')
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
