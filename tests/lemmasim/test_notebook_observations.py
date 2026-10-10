"""Independent literal observer boundaries, separate from guest execution."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'conformance/lemmasim'))
from check_notebook_workflow import check_cold, device_events, join_chunks, visible_pixels
from notebook_input import generate


def sample(sequence, contact=True, epoch=2):
    return (sequence, sequence * 1000, 100, 200, 2048 if contact else 0,
            3 if contact else 2, 1, 0, epoch)


def chunk(lifecycle, samples):
    header = [0] * 16
    header[14] = lifecycle
    return tuple(header), samples


class NotebookObservations(unittest.TestCase):
    def test_unique_raw_count_excludes_only_declared_boundary_overlap(self):
        a, b, c, d, up = [sample(i) for i in range(1, 5)] + [sample(5, False)]
        self.assertEqual(join_chunks([chunk(1, [a, b, c]), chunk(6, [c, d, up])]),
                         [a, b, c, d, up])
        for wrong in [[chunk(1, [a, b, c]), chunk(6, [b, d, up])],
                      [chunk(1, [a, b, c]), chunk(6, [c, c, d, up])],
                      [chunk(3, [a, up]), chunk(6, [up, sample(6, False)])],
                      [chunk(1, [a, b, c])]]:
            with self.assertRaises(ValueError):
                join_chunks(wrong)

    def test_loss_inputs_use_device_events_and_real_boundaries(self):
        for name in ('loss-overflow', 'loss-disconnect', 'loss-watchdog'):
            raw, manifest = generate(name, 1650, 2200, 200000000, 100000, 200000000)
            samples = [struct.unpack_from('<9Q', raw, offset) for offset in range(0, len(raw), 72)]
            self.assertEqual([row[0] for row in samples], list(range(1, len(samples) + 1)))
            self.assertTrue(all(b[1] >= a[1] for a, b in zip(samples, samples[1:])))
            self.assertEqual(manifest['expected']['retained_raw_samples'], 50)
            loss = manifest['expected']['loss']
            if name == 'loss-overflow':
                burst = samples[loss['boundary_first_sequence'] - 1:loss['cancelled_last_sequence']]
                self.assertEqual(len(burst), 300)
                self.assertEqual(len({row[1] for row in burst}), 1)
            elif name == 'loss-disconnect':
                self.assertEqual(samples[loss['boundary_first_sequence'] - 1][5], 8)
            else:
                last = samples[loss['cancelled_last_sequence'] - 1]
                release = samples[loss['resync_release_sequence'] - 1]
                self.assertEqual(last[5] & 1, 1)
                self.assertGreater(release[1] - last[1], 10000000)

    def test_observers_reject_truncation_and_backward_device_time(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'observation'
            path.write_text('100 paper-complete 1 2 0\n200 paper-complete 2 2 0\n')
            self.assertEqual(len(device_events(path)), 2)
            for text in ('', '100 paper-complete 1 2\n',
                         '100 paper-complete 1 2 0\n99 pen-input 1 1 2\n'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    device_events(path)
            path.write_bytes(b'P6\n2 1\n255\n' + bytes(6))
            self.assertEqual(visible_pixels(path), (2, 1, bytes(6)))
            path.write_bytes(b'P6\n2 1\n255\n' + bytes(5))
            with self.assertRaises(ValueError):
                visible_pixels(path)

    def test_cold_boundary_requires_unchanged_bytes_and_fresh_refresh(self):
        # Literal observations test comparison logic only. They are not a
        # simulated CPU run and cannot establish cold guest recovery.
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            paths = [directory / name for name in ('before.raw', 'after.raw',
                     'before.ppm', 'after.ppm', 'serial', 'devices')]
            for path in paths[:2]:
                path.write_bytes(b'independent comparison input')
            for path in paths[2:4]:
                path.write_bytes(b'P6\n2 1\n255\n' + bytes(6))
            paths[4].write_text('K1 0000000000000420 0000000100000002 0000000000000001 0000000000000001 0000000000000001\n')
            paths[5].write_text('100 paper-complete 1 2 0\n')
            with patch('check_notebook_workflow.committed_bytes', return_value=(4, {'1/1': 'literal'}, 'literal')):
                self.assertEqual(check_cold(*paths)['committed_sequence'], 4)
                paths[3].write_bytes(b'P6\n2 1\n255\n' + bytes([1]) + bytes(5))
                with self.assertRaisesRegex(ValueError, 'visible pixels'):
                    check_cold(*paths)
                paths[3].write_bytes(paths[2].read_bytes())
                paths[5].write_text('100 paper-command 104 2 1\n')
                with self.assertRaisesRegex(ValueError, 'fresh controller redraw'):
                    check_cold(*paths)
            with patch('check_notebook_workflow.committed_bytes', side_effect=[
                    (4, {'1/1': 'before'}, 'before'), (3, {'1/1': 'after'}, 'after')]):
                with self.assertRaisesRegex(ValueError, 'committed document bytes'):
                    check_cold(*paths)


if __name__ == '__main__':
    unittest.main()
