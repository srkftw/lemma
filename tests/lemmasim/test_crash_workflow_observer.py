"""Fixed literal crash observations, not target/device acceptance results."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'conformance/lemmasim'))
import check_crash_workflow as checker
from inspect_notebook import inspect
from store_oracle import COMMIT, RECORD, ROOT, MASK, fnv


def sector(fields):
    prefix = struct.pack('<' + 'Q' * len(fields), *fields)
    check = fnv(prefix)
    return prefix + struct.pack('<QQ', check, check ^ MASK) + bytes(512 - len(prefix) - 16)


def sample(sequence, contact=True):
    return (sequence, sequence * 1000, 100, 200, 2048 if contact else 0,
            3 if contact else 2, 1, 0, 1)


def chunk(stroke, rows, lifecycle=3):
    return struct.pack('<16Q', checker.MAGIC, 1, 3, 1, stroke, 0, len(rows), 512, 1,
                       65535, 65535, 4095, 1650, 2200, lifecycle, 0) + b''.join(struct.pack('<9Q', *row) for row in rows)


def page(entries, edits):
    return (struct.pack('<16Q', checker.MAGIC, 2, 2, 1, len(entries), len(edits), len(edits), *([0] * 9))
            + b''.join(struct.pack('<3Q', *entry) for entry in entries)
            + b''.join(struct.pack('<2Q', *edit) for edit in edits))


def catalog():
    return struct.pack('<8Q', checker.MAGIC, 1, 1, 1, 512, 0, 0, 0)


def append(image, cursor, sequence, obj, payload):
    count = (len(payload) + 511) // 512
    header = sector([RECORD, 1, 1, 1, obj, sequence, sequence, len(payload), 1, count, fnv(payload)])
    image[cursor * 512:(cursor + 1) * 512] = header
    image[(cursor + 1) * 512:(cursor + 1) * 512 + len(payload)] = payload
    check = struct.unpack_from('<Q', header, 88)[0]
    image[(cursor + count + 1) * 512:(cursor + count + 2) * 512] = sector(
        [COMMIT, 1, 1, 1, obj, sequence, sequence, len(payload), 1, fnv(payload), check])
    return cursor + count + 2


def guest(tag, a, b=1, c=1, d=1):
    return ('K1 ' + ' '.join(f'{word:016x}' for word in (tag, a, b, c, d)) + '\n').encode()


class CrashWorkflowObserver(unittest.TestCase):
    def setup_fixture(self, root):
        base = bytearray(4096 * 512)
        base[:512] = sector([ROOT, 1, 1, 4096, 0, 8, 2044, 0, 0, 0])
        base[512:1024] = base[:512]
        cursor = append(base, 8, 1, 65537, chunk(1, [sample(100), sample(101), sample(102, False)]))
        cursor = append(base, cursor, 2, 257, page([(65537, 1, 1)], [(1, 1)]))
        cursor = append(base, cursor, 3, 1, catalog())
        (root / 'baseline.raw').write_bytes(base)
        inspect(root / 'baseline.raw', root / 'export')
        (root / 'baseline.serial').write_bytes(guest(0x420, 1) + guest(0x421, 3))
        (root / 'fault.raw').write_bytes(base)
        (root / 'fault.serial').write_bytes(guest(0x420, 1) + guest(0x423, 4, d=65540))
        rows = [sample(1, False), sample(2), sample(3), sample(4, False)]
        raw = b''.join(struct.pack('<9Q', *row) for row in rows)
        (root / 'input.bin').write_bytes(raw)
        fixture = {'schema_version': 1, 'profile': 'lemmasim-virt/0.1.0',
                   'input_sha256': hashlib.sha256(raw).hexdigest(), 'input_samples': 4,
                   'raw_coordinate_maximum': [65535, 65535], 'pressure_maximum': 4095,
                   'geometry': [1650, 2200], 'actions': [{'kind': 'stroke', 'namespace': 1,
                    'page': 1, 'name': 'new', 'first_sequence': 2, 'last_sequence': 4}]}
        (root / 'input.json').write_text(json.dumps(fixture))
        (root / 'devices.trace').write_text(''.join(f'{row[1] * 100} pen-input {i} {i} 1\n' for i, row in enumerate(rows, 1)))
        writes = [cursor * 512, (cursor + 1) * 512, (cursor + 3) * 512]
        (root / 'media.trace').write_text('0 medium-open 32768 1 0\n' + ''.join(
            f'{i} write-volatile {offset} 512 {i}\n' for i, offset in enumerate(writes, 1))
            + '4 flush-begin 1 0 3\n4 power-cut-before-flush 1 0 3\n')
        case = {'schema_version': 1, 'fault': 'cut-before-flush', 'ordinal': 1,
                'phase': 'payload', 'operation': 'append', 'record_header_sector': cursor,
                'record_payload_sectors': 1, 'record_publication_sector': cursor + 2}
        (root / 'case.json').write_text(json.dumps(case))
        return base, cursor, rows, case

    def check(self, root):
        return checker.check(root / 'export', root / 'baseline.serial', root / 'fault.raw',
                             root / 'fault.serial', root / 'input.bin', root / 'input.json',
                             root / 'devices.trace', root / 'media.trace', root / 'case.json')

    def test_previous_ack_survives_real_named_boundary_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.setup_fixture(root)
            result = self.check(root)
            self.assertEqual(result['recovered_sequence'], 3)
            self.assertEqual(result['baseline_immutable_chunks_preserved'], 1)
            self.assertEqual(result['boundary']['phase'], 'payload')

    def test_early_ack_and_changed_immutable_ink_are_rejected_behaviorally(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base, cursor, _, _ = self.setup_fixture(root)
            (root / 'fault.serial').write_bytes(guest(0x421, 6, d=2))
            with self.assertRaisesRegex(ValueError, 'acknowledged document work absent'):
                self.check(root)
            (root / 'fault.serial').write_bytes(guest(0x420, 1))
            # A fully checksummed record replacement, not just a changed hash,
            # must still fail preservation of the earlier acknowledged writing.
            append(base, cursor, 4, 65537, chunk(1, [sample(200), sample(201), sample(202, False)]))
            (root / 'fault.raw').write_bytes(base)
            with self.assertRaisesRegex(ValueError, 'immutable ink lost/changed'):
                self.check(root)

    def test_new_chunk_exact_raw_subset_and_unacknowledged_whole_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base, cursor, rows, _ = self.setup_fixture(root)
            end = append(base, cursor, 4, 65540, chunk(2, rows[1:]))
            end = append(base, end, 5, 257, page([(65537, 1, 1), (65540, 2, 1)], [(1, 1), (1, 2)]))
            append(base, end, 6, 1, catalog())
            (root / 'fault.raw').write_bytes(base)
            result = self.check(root)
            self.assertEqual(result['recovered_sequence'], 6)
            self.assertEqual(result['new_wholly_valid_chunks'][0]['raw_action'], 'new')
            altered = list(rows[1:])
            altered[1] = (*altered[1][:2], 101, *altered[1][3:])
            # All record checksums remain valid; provenance must catch this.
            append(base, cursor, 4, 65540, chunk(2, altered))
            (root / 'fault.raw').write_bytes(base)
            with self.assertRaisesRegex(ValueError, 'exact original raw FIFO'):
                self.check(root)

    def test_boundaries_require_literal_root_slot_and_torn_half_sector(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trace'
            case = {'schema_version': 1, 'fault': 'tear-flush', 'ordinal': 1,
                    'operation': 'checkpoint', 'phase': 'checkpoint-root'}
            path.write_text('0 medium-open 32768 1 0\n1 write-volatile 512 512 1\n2 flush-begin 1 0 1\n2 sector-torn-durable 1 256 1\n2 power-cut-torn-flush 1 0 1\n')
            self.assertEqual(checker.medium_boundary(path, case, 1)['write_offsets'], [512])
            path.write_text(path.read_text().replace('write-volatile 512', 'write-volatile 0'))
            with self.assertRaisesRegex(ValueError, 'exact independent publication slot'):
                checker.medium_boundary(path, case, 1)

    def test_plan_names_actual_latest_record_offsets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base, cursor, rows, _ = self.setup_fixture(root)
            append(base, cursor, 4, 65540, chunk(2, rows[1:]))
            (root / 'reference.raw').write_bytes(base)
            writes = [cursor * 512, (cursor + 1) * 512, (cursor + 3) * 512]
            (root / 'reference.trace').write_text('0 medium-open 32768 1 0\n' + ''.join(
                f'{i} write-volatile {offset} 512 {i}\n' for i, offset in enumerate(writes, 1))
                + f'4 flush-begin 1 0 3\n5 flush-durable 1 0 0\n6 write-volatile {(cursor + 2) * 512} 512 1\n7 flush-begin 2 1 1\n8 flush-durable 2 0 0\n')
            result = checker.plan(root / 'reference.raw', root / 'reference.trace', root / 'export')
            self.assertEqual([(case['ordinal'], case['phase']) for case in result['cases']], [(1, 'payload'), (2, 'publication')])

    def test_checkpoint_early_ack_and_silent_failed_flush_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.setup_fixture(root)
            case = {'schema_version': 1, 'fault': 'cut-before-flush', 'ordinal': 1,
                    'operation': 'checkpoint', 'phase': 'checkpoint-root'}
            (root / 'case.json').write_text(json.dumps(case))
            (root / 'media.trace').write_text('0 medium-open 32768 1 0\n1 write-volatile 512 512 1\n2 flush-begin 1 0 1\n2 power-cut-before-flush 1 0 1\n')
            (root / 'fault.serial').write_bytes(guest(0x421, 3, d=0))
            with self.assertRaisesRegex(ValueError, 'checkpoint ACK preceded durable'):
                self.check(root)
            case['fault'] = 'fail-flush'
            (root / 'case.json').write_text(json.dumps(case))
            (root / 'media.trace').write_text('0 medium-open 32768 1 0\n1 write-volatile 512 512 1\n2 flush-begin 1 0 1\n2 flush-failed 1 0 1\n')
            (root / 'fault.serial').write_bytes(guest(0x420, 1))
            with self.assertRaisesRegex(ValueError, 'lacked guest Save failed'):
                self.check(root)
            (root / 'fault.serial').write_bytes(guest(0x424, 230, d=0))
            self.assertEqual(self.check(root)['status'], 'PASS')

    def test_torn_payload_requires_actual_incomplete_body_and_preserves_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base, cursor, rows, case = self.setup_fixture(root)
            complete = bytearray(base)
            append(complete, cursor, 4, 65540, chunk(2, rows[1:]))
            base[cursor * 512:cursor * 512 + 256] = complete[cursor * 512:cursor * 512 + 256]
            (root / 'fault.raw').write_bytes(base)
            case.update(fault='tear-flush', record_namespace=1, record_object=65540)
            (root / 'case.json').write_text(json.dumps(case))
            trace = (root / 'media.trace').read_text().replace(
                '4 power-cut-before-flush 1 0 3\n',
                f'4 sector-torn-durable {cursor} 256 3\n4 power-cut-torn-flush 1 0 3\n')
            (root / 'media.trace').write_text(trace)
            observed = self.check(root)
            self.assertEqual(observed['recovered_sequence'], 3)
            self.assertIs(observed['torn_payload_incomplete_append_rejected'], True)
            # A host-written fault label with no stable header is insufficient.
            base[cursor * 512:(cursor + 1) * 512] = bytes(512)
            (root / 'fault.raw').write_bytes(base)
            with self.assertRaisesRegex(ValueError, 'lacked a stable new header'):
                self.check(root)


if __name__ == '__main__':
    unittest.main()
