"""Observe opaque persistence prefixes without assuming failed writes roll back."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_guest_usb_notebook import materialize_observation
from check_guest_usb_link import crc64


def receipt(sequence, kind, offset=0, payload=b''):
    prefix = struct.pack('<8Q', 0x313030504d434d4c, 1, kind, 83, sequence,
                         offset, len(payload), 0) + payload
    raw = prefix + struct.pack('<Q', crc64(prefix))
    return struct.pack('<Q', len(raw)) + raw


class OpaqueMediumObservation(unittest.TestCase):
    def peer(self, root, rows):
        peer = root / 'peer'; peer.mkdir()
        with (peer / 'base.img').open('xb') as p: p.truncate(268435456)
        (peer / 'peer.json').write_text(json.dumps({'schema': 'lemma-companion-backing-dev/1',
                  'writer': 83, 'base': str(peer / 'base.img')}))
        (peer / 'opaque.log').write_bytes(struct.pack('<Q', 0x3130474f4c434d4c) + b''.join(rows))
        return peer

    def test_observed_unacknowledged_write_is_retained_without_barrier(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); payload = bytes(range(256)) * 2
            peer = self.peer(root, [receipt(1, 1, 4096, payload)])
            output = root / 'observed.raw'
            summary = materialize_observation(peer, output)
            self.assertEqual(summary, {'writer': 83, 'persisted_sequence': 1, 'bytes': 268435456})
            with output.open('rb') as p:
                p.seek(4096); self.assertEqual(p.read(512), payload)
            # The source is neither mutated nor interpreted as a document.
            with (peer / 'base.img').open('rb') as p:
                p.seek(4096); self.assertEqual(p.read(512), bytes(512))
            with self.assertRaises(ValueError): materialize_observation(peer, output)

    def test_duplicate_effect_sequence_and_barrier_payload_rejected(self):
        for rows in ([receipt(1, 2), receipt(1, 2)], [receipt(1, 2, 0, bytes(8))]):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); peer = self.peer(root, rows)
                with self.assertRaises(ValueError): materialize_observation(peer, root / 'bad.raw')

    def test_truncated_base_is_not_silently_padded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); peer = self.peer(root, [receipt(1, 2)])
            with (peer / 'base.img').open('r+b') as p: p.truncate(268435455)
            output = root / 'bad.raw'
            with self.assertRaises(ValueError): materialize_observation(peer, output)
            self.assertFalse(output.exists())


if __name__ == '__main__': unittest.main()
