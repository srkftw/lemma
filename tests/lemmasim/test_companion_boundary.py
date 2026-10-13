from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from archive_companion_boundary import crc64, identity, log_frames, outbox_fields


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


if __name__ == '__main__': unittest.main()
