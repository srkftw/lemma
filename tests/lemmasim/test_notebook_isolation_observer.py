"""Literal negative boundaries for the independent actual-run observer.

These fixtures test observer decisions, not execution or task containment.
Only fresh real QEMU/guest observations can establish the integration result.
"""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'conformance/lemmasim'))
from check_notebook_isolation import delayed_dma_observation, serial_observations


def literal():
    client, handle, base = 19, 8207, 0x8200f000
    rows = [(0x433, 0, handle, base, 0), (0x434, 0, 1, 0, 7500),
            (0x436, 0, 100000, 0, 0),
            (0x42f, client, 16, 17, 0)]
    values = {1: (72, 0), 2: (80, 0), 3: (72, 0), 4: (72, 0),
              5: (81, 0), 7: (80, 0), 101: (0, 128), 102: (0, 128),
              106: (0, 128), 201: (220, 3), 202: (220, 3), 206: (220, 3),
              298: (0, 19), 299: (0, 202700000), 300: (232, 3)}
    for key, value in values.items():
        if key == 298:
            rows.append((0x423, 4, 1, 1, 65537))
        rows.append((0x430, client, key, *value))
    # Attempt observation precedes actual queued-transaction observation.
    a = next(i for i, row in enumerate(rows) if row[0:3] == (0x430, client, 298))
    b = next(i for i, row in enumerate(rows) if row[0:3] == (0x430, client, 299))
    rows[a], rows[b] = rows[b], rows[a]
    rows += [(0x421, 5, 1, 1, 3), (0x432, client, 0x400000, 420000000, 0),
             (0x433, 1, handle, base, 2), (0x434, 1, 1, 0, 7400),
             (0x436, 1, 420000100, 2, 0),
             (0xd4, 13, 0x1000240, 0x400000, 0x20),
             (0xf4, client, 44, client, 13), (0xf6, client, 7400, 7442, 0),
             (0x433, 2, handle, base, 2), (0x434, 2, 1, 0, 7442),
             (0x436, 2, 420020000, 2, 0),
             (0x421, 8, 1, 1, 6)]
    return rows


class IsolationObserver(unittest.TestCase):
    def test_literal_requires_real_rejections_fault_cleanup_and_continuation(self):
        value = serial_observations(literal())
        self.assertEqual(value['client'], 19)
        self.assertTrue(value['dma_request_outstanding_at_fault'])
        self.assertEqual(value['actual_replies']['201'], [220, 3])
        self.assertEqual(value['actual_replies']['300'][0], 232)
        without_pending = [(tag, a, b, 0 if tag == 0x436 else c, 0 if tag == 0x433 else d)
                           for tag, a, b, c, d in literal()]
        self.assertFalse(serial_observations(without_pending)['dma_request_outstanding_at_fault'])

    def test_success_in_place_of_denial_is_a_behavioral_failure(self):
        for target in (1, 7, 201, 300):
            rows = [(tag, a, b, 0 if tag == 0x430 and b == target else c, d)
                    for tag, a, b, c, d in literal()]
            with self.assertRaisesRegex(ValueError, 'rejection differs'):
                serial_observations(rows)

    def test_foreign_chunk_must_reach_ipc_before_real_ink_ack(self):
        rows = [row for row in literal() if row[0] != 0x423]
        with self.assertRaisesRegex(ValueError, 'pending notebook commit'):
            serial_observations(rows)
        rows = literal()
        ack = next(row for row in rows if row[0] == 0x421)
        rows.remove(ack)
        rows.insert(0, ack)
        with self.assertRaisesRegex(ValueError, 'pending notebook commit'):
            serial_observations(rows)

    def test_fault_must_be_user_and_reclaimed_with_same_dma_frame(self):
        changes = [((0xd4, 13, 0x1000240, 0x400000, 0x120), 'supervisor provenance'),
                   ((0x433, 2, 8208, 0x8200f000, 2), 'identity changed'),
                   ((0x434, 2, 4, 0, 7442), 'purpose'),
                   ((0xf6, 19, 7400, 7400, 0), 'recover')]
        for replacement, message in changes:
            rows = [replacement if row[0] == replacement[0] and
                    (row[0] not in (0x433, 0x434) or row[1] == replacement[1]) else row
                    for row in literal()]
            with self.assertRaisesRegex(ValueError, message):
                serial_observations(rows)

    def test_missing_post_fault_ack_and_normal_return_fail_closed(self):
        rows = literal()
        rows.pop()
        with self.assertRaisesRegex(ValueError, 'fresh ink'):
            serial_observations(rows)
        rows = literal() + [(0x435, 19, 0, 0, 0)]
        with self.assertRaisesRegex(ValueError, 'returned instead'):
            serial_observations(rows)
        rows = literal() + [literal()[3]]
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            serial_observations(rows)

    def test_actual_device_interval_must_bracket_fault_and_completed_reap(self):
        media = [(41000000000, 'write-delay-begin', 8192, 512, 0),
                 (44000000000, 'write-delay-end', 8192, 512, 0),
                 (44000000000, 'write-volatile', 8192, 512, 1)]
        observed = serial_observations(literal())
        value = delayed_dma_observation(observed, media)
        self.assertLess(value['write_start_ns'], value['fault_ns'])
        self.assertLess(value['reaped_ns'], value['write_complete_ns'])
        failures = [([], 'missing'),
                    (media + [media[0]], 'duplicate'),
                    ([media[0], (44000000000, 'write-delay-end', 8704, 512, 0), media[2]], 'identity'),
                    ([(43000000000, 'write-delay-begin', 8192, 512, 0),
                      (46000000000, 'write-delay-end', 8192, 512, 0),
                      (46000000000, 'write-volatile', 8192, 512, 1)], 'outside'),
                    (media[:2], 'never consumed')]
        for events, message in failures:
            with self.assertRaisesRegex(ValueError, message):
                delayed_dma_observation(observed, events)
        no_write = copy.deepcopy(observed)
        no_write['dma_timing']['1'][1] = 0
        with self.assertRaisesRegex(ValueError, 'outside writable'):
            delayed_dma_observation(no_write, media)


if __name__ == '__main__':
    unittest.main()
