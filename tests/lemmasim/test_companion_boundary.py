from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from archive_companion_boundary import BOUNDARY_FILES, crc64, identity, log_frames, outbox_fields, validate_archive_files


class ObservationalPeerBoundary(unittest.TestCase):
    def outbox(self, writer=83, next_sequence=37, pending=0):
        body = struct.pack('<4Q', 0x313054554f434d4c, writer, next_sequence, pending)
        return body + struct.pack('<Q', crc64(body))

    def test_exact_atomic_metadata(self):
        outbox_fields(self.outbox(), 83, 36)

    def test_unacknowledged_different_writer_and_sequence_reject(self):
        for data in (self.outbox(pending=72), self.outbox(writer=84),
                     self.outbox(next_sequence=36), self.outbox(next_sequence=38)):
            with self.subTest(data=data):
                with self.assertRaises(ValueError): outbox_fields(data, 83, 36)

    def test_corrupt_or_incomplete_atomic_metadata_reject(self):
        data = self.outbox()
        for wrong in (data[:-1], data + b'\0', data[:-1] + bytes([data[-1] ^ 1])):
            with self.assertRaises(ValueError): outbox_fields(wrong, 83, 36)

    def test_prefix_cannot_hide_partial_tail(self):
        magic = struct.pack('<Q', 0x3130474f4c434d4c)
        frame = bytes(72)
        complete = magic + struct.pack('<Q', len(frame)) + frame
        self.assertEqual(log_frames(complete), [frame])
        for wrong in (complete[:-1], complete + b'\0', magic + struct.pack('<Q', 585) + bytes(585)):
            with self.assertRaises(ValueError): log_frames(wrong)

    def test_observation_rejects_symlink_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); regular = root / 'regular'; regular.write_bytes(b'original')
            link = root / 'link'; link.symlink_to(regular)
            self.assertEqual(identity(regular)[2], 8)
            with self.assertRaises(ValueError): identity(link)

    def test_cold_inventory_cannot_omit_or_add_an_input(self):
        exact = {name: {} for name in BOUNDARY_FILES}
        for wrong in ({}, {**exact, '../original-medium': {}},
                      {name: {} for name in BOUNDARY_FILES if name != 'peer/base.img'}):
            with self.assertRaisesRegex(ValueError, 'file inventory'):
                validate_archive_files('/unused', {'files': wrong})

    def test_cold_rejects_symbolic_parent_before_hash_or_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'elsewhere').mkdir()
            (root / 'peer').symlink_to(root / 'elsewhere', target_is_directory=True)
            files = {name: {'bytes': 0, 'sha256': '0' * 64} for name in BOUNDARY_FILES}
            # Ordered mapping makes the first inspected input the aliased base.
            files = {'peer/base.img': files.pop('peer/base.img'), **files}
            with self.assertRaisesRegex(ValueError, 'symbolic path'):
                validate_archive_files(root, {'files': files})

    def test_cold_rejects_non_integral_size_before_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'peer').mkdir(); (root / 'peer/base.img').write_bytes(b'')
            files = {'peer/base.img': {'bytes': True, 'sha256': '0' * 64}}
            files.update({name: {} for name in BOUNDARY_FILES if name not in files})
            with self.assertRaisesRegex(ValueError, 'metadata differs'):
                validate_archive_files(root, {'files': files})

    def test_cold_rejects_capacity_mismatch_before_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'peer').mkdir(); (root / 'peer/base.img').write_bytes(b'')
            files = {'peer/base.img': {'bytes': 268435457, 'sha256': '0' * 64}}
            files.update({name: {} for name in BOUNDARY_FILES if name not in files})
            with self.assertRaisesRegex(ValueError, 'declared bound'):
                validate_archive_files(root, {'files': files})


if __name__ == '__main__': unittest.main()
