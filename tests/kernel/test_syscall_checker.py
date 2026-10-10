"""Host parser and mutation fixtures, never actual user execution evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import create_autospec, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_kernel_syscall import (MixedWire, validate_wire_segments, validate_notification,
                                  validate_after_cleanup, validate_input_reads, payload)
from check_kernel_user import USER_STATUS, satp
from run_kernel import Session, transport
from core0_common import Core0Error, sha256
from audit_kernel import validate_user_syscall_bridge, USER_SYSCALL_WORDS


def record(words):
    return ('K1' + ''.join(f' {word:016x}' for word in words) + '\n').encode()


class SyscallCheckerTests(unittest.TestCase):
    def input_reads(self, first, counts):
        seed = 7
        rows = {(0xe4, 43): (0xe4, 43, 0, first, seed), (0xe2, 44): (0xe2, 44, 0, 16, seed)}
        positions = {(0xe4, 43): 0, (0xe2, 44): len(counts) + 1}
        for index, count in enumerate(counts):
            key = (0xe4, 430 + index)
            rows[key] = (*key, 0, count, seed); positions[key] = index + 1
        return rows, positions

    def test_first_crossing_count_is_separate_from_complete_payload(self):
        for first, counts in [(16, []), (14, [2]), (9, [1, 2, 4])]:
            rows, positions = self.input_reads(first, counts)
            observed = validate_input_reads(rows, positions, seed=7, input_bytes=payload(7, 16))
            self.assertEqual(observed['successful_cross_page_input']['actual_bytes'], first)
            self.assertEqual(observed['complete_input_bytes'], 16)
            self.assertEqual([row['actual_bytes'] for row in observed['completion_reads']], counts)
        for first, counts in [(1, [15]), (8, [8]), (17, []), (14, []), (14, [0, 2]), (14, [3])]:
            rows, positions = self.input_reads(first, counts)
            with self.assertRaises(Core0Error):validate_input_reads(rows, positions, seed=7, input_bytes=payload(7, 16))
        for mutate in [lambda rows, positions: rows.update({(0xe4, 430): (0xe4, 430, 12, 2, 7)}),
                       lambda rows, positions: rows.update({(0xe4, 430): (0xe4, 430, 0, 2, 8)}),
                       lambda rows, positions: positions.update({(0xe4, 430): 2}),
                       lambda rows, positions: rows.update({(0xe4, 431): rows.pop((0xe4, 430))})]:
            rows, positions = self.input_reads(14, [2]); mutate(rows, positions)
            with self.assertRaises(Core0Error):validate_input_reads(rows, positions, seed=7, input_bytes=payload(7, 16))

    def session(self):
        session = create_autospec(Session, instance=True)
        session.capture = SimpleNamespace(received=bytearray(), sent=bytearray())
        session.records = []; session.process = object(); session.deadline = 1.0
        return session

    def reader(self, raw):
        position = 0
        def read(process, count, *, deadline, capture, context):
            nonlocal position
            piece = raw[position:position + count]
            if len(piece) != count: raise Core0Error('fixture stream ended before complete packet')
            position += count; capture.received.extend(piece)
            return piece
        return read

    def test_binary_interior_k1_and_irq_boundaries_are_distinct_complete_segments(self):
        session = self.session(); wire = MixedWire(session)
        ready = (0xe2, 40, 0, 96, 7)
        irq = (0xdf, 0x8000000000000001, 0x10004, USER_STATUS, satp(0x8200d000))
        binary = b'\0\xff' + record(irq) + b'\0\xff\nK1\0'
        self.assertEqual(len(binary), 96)
        raw = record(ready) + record(irq) + binary
        with patch.object(transport, '_read_exact', autospec=True, side_effect=self.reader(raw)):
            self.assertEqual(wire.read(), ready)
            self.assertEqual(wire.read(binary), irq)
            self.assertEqual(wire.read(binary), binary)
        validate_wire_segments(bytes(session.capture.received), session.records, wire.segments)
        self.assertEqual(len(session.records), 2)
        self.assertEqual([row['kind'] for row in wire.segments], ['record', 'record', 'payload'])
        for mutate in [lambda rows: rows.pop(), lambda rows: rows[1].update(offset=0),
                       lambda rows: rows[2].update(hex='00ff'), lambda rows: rows[0].update(values=[0]*5)]:
            rows = copy.deepcopy(wire.segments); mutate(rows)
            with self.assertRaises(Core0Error): validate_wire_segments(raw, session.records, rows)

    def test_unexpected_partial_and_wrong_binary_payload_fail_closed(self):
        for raw, expected in [(b'\0\xff', None), (b'K1 ', None), (b'\0\xffbad', b'\0\xffgood')]:
            session = self.session(); wire = MixedWire(session)
            with patch.object(transport, '_read_exact', autospec=True, side_effect=self.reader(raw)):
                with self.assertRaises(Core0Error): wire.read(expected)
        with self.assertRaises(Core0Error): validate_wire_segments(b'', [], [])

    def test_stdout_suffix_drained_only_during_cleanup_cannot_leave_pass_report(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            session = self.session(); session.output_dir = Path(temporary)
            wire = MixedWire(session); event = (0xe1, 1, 0, 524, 7)
            raw = record(event)
            with patch.object(transport, '_read_exact', autospec=True, side_effect=self.reader(raw)):
                wire.read()
            validate_wire_segments(raw, session.records, wire.segments)
            # Model a byte arriving only when the real Session cleanup drains.
            (session.output_dir/'received.bin').write_bytes(raw+b'!')
            session.report = {'status':'PASS', 'wire_segments':wire.segments, 'records':session.records,
                              'raw_artifacts':{'received.bin':sha256(session.output_dir/'received.bin')},
                              'cleanup':{'explicit_host_stop':True,'process_group_killed':True,'process_reaped':True,
                                         'target_exited_before_cleanup':False},'returncode':-9}
            with self.assertRaises(Core0Error): validate_after_cleanup(session)
            final = json.loads((session.output_dir/'result.json').read_text())
            self.assertEqual(final['status'],'FAIL')
            self.assertEqual(final['returncode'],-9)
            self.assertEqual((session.output_dir/'received.bin').read_bytes(),raw+b'!')

    def test_notification_requires_real_origin_pc_status_and_installed_address_space(self):
        installed = satp(0x8200d000); ranges = {'user': {'base': 0x10000, 'bytes': 32}}
        event = (0xdf, 0x8000000000000001, 0x10004, USER_STATUS, installed)
        validate_notification(event, installed, ranges)
        for index, value in [(1, 8), (2, 0x10002), (2, 0x80200000), (3, USER_STATUS | 0x100), (4, 0)]:
            bad = list(event); bad[index] = value
            with self.assertRaises(Core0Error): validate_notification(tuple(bad), installed, ranges)

    def test_register_bridge_rejects_misrouting_and_changed_ecall_opcode(self):
        symbol = 'lemma_exec_syscall'; ranges = {symbol: (0x10080, 32)}
        source = symbol + ':\n' + '\n'.join('  ' + line for line in [
            'mv a7, a0', 'mv a0, a1', 'mv a1, a2', 'mv a2, a3', 'mv a3, a4', 'mv a4, a5', 'ecall', 'ret']) + '\n.size ' + symbol + ', . - ' + symbol + '\n'
        raw = ''.join(f' {0x10080 + index*4:x}: {word:08x} instruction\n' for index, word in enumerate(USER_SYSCALL_WORDS))
        self.assertEqual(validate_user_syscall_bridge(source, raw, ranges)['ecall_pc'], 0x10098)
        for text, machine in [(source.replace('mv a7, a0', 'mv a6, a0'), raw),
                              (source, raw.replace('00000073', '00008067'))]:
            with self.assertRaises(Core0Error): validate_user_syscall_bridge(text, machine, ranges)
        self.assertEqual(payload(0, 16)[:2], b'\0\xff')
        self.assertNotEqual(payload(0, 16), payload(7, 16))


if __name__ == '__main__': unittest.main()
