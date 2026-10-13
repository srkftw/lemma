"""Cold reopening observes retained bytes and redraw; it does not need a Save."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_retained_cold_recovery import cold_boundary


class RetainedColdBoundary(unittest.TestCase):
    def setUp(self):
        self.rows = [(0x425, 1, 1, 1, 0), (0x420, 1650 | (2200 << 32), 1, 1, 1)]
        self.state = {'panel_completed': 1, 'panel_sequence': 1, 'paper_busy': 0,
                      'panel_pending_pixels': 0, 'finished': False, 'block_state': 0,
                      'memory_pending': 0, 'dma_outstanding': 0, 'flushes': 0,
                      'backing_io': {'phase': 2, 'completed': 24, 'next_id': 25,
                         'poisoned': False, 'orphan': False, 'fork_suspended': False,
                         'observed_write': 0, 'durable_barrier': 0}}

    def test_completed_clean_reopen_does_not_require_new_save(self):
        self.assertEqual(cold_boundary(self.rows, self.state), 1)
        self.assertNotIn(0x421, [r[0] for r in self.rows])

    def test_ready_record_alone_does_not_establish_completed_redraw(self):
        for name, value in (('panel_completed', 0), ('panel_sequence', 2),
                            ('paper_busy', 1), ('panel_pending_pixels', 1)):
            s = copy.deepcopy(self.state); s[name] = value
            with self.assertRaises(ValueError): cold_boundary(self.rows, s)
        with self.assertRaises(ValueError): cold_boundary(self.rows[1:], self.state)

    def test_missing_or_contradictory_ready_rejected(self):
        for rows in (self.rows[:1], self.rows + [self.rows[1]],
                     [(0x425, 2, 1, 1, 0), self.rows[1]]):
            with self.assertRaises(ValueError): cold_boundary(rows, self.state)

    def test_failed_pending_or_republished_recovery_rejected(self):
        for name, value in (('finished', True), ('block_state', 1),
                            ('memory_pending', 1), ('dma_outstanding', 1), ('flushes', 1)):
            s = copy.deepcopy(self.state); s[name] = value
            with self.assertRaises(ValueError): cold_boundary(self.rows, s)
        for name, value in (('phase', 1), ('completed', 23), ('poisoned', True),
                            ('orphan', True), ('fork_suspended', True),
                            ('observed_write', 1), ('durable_barrier', 1)):
            s = copy.deepcopy(self.state); s['backing_io'][name] = value
            with self.assertRaises(ValueError): cold_boundary(self.rows, s)
        for code in (0x41f, 0x423, 0x424):
            with self.assertRaises(ValueError):
                cold_boundary(self.rows + [(code, 0, 0, 0, 0)], self.state)


if __name__ == '__main__': unittest.main()
