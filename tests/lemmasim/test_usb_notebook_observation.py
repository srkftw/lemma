"""Old autosave output cannot replace the newly admitted explicit Save."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_guest_usb_notebook import explicit_save_completed, initial_publication_completed


class ExplicitSaveObservation(unittest.TestCase):
    def test_ready_or_unrelated_saved_is_not_initial_root_acknowledgment(self):
        ready=(0x420,1650 | (2200 << 32),1,1,1)
        pending=(0x423,2,1,1,1);saved=(0x421,2,1,1,0)
        self.assertTrue(initial_publication_completed([ready,pending,saved]))
        for rows in ([ready],[ready,pending],[(0x423,1,1,1,257),(0x421,1,1,1,0)],
                     [pending,(0x421,1,1,1,0)],[pending,(0x421,2,2,1,0)],
                     [pending,(0x421,2,1,2,0)],[pending,(0x421,2,1,1,3)],
                     [pending,saved,(0x424,227,1,1,65539)]):
            with self.subTest(rows=rows):
                self.assertFalse(initial_publication_completed(rows))

    def test_new_matching_pending_and_saved_are_required(self):
        old = [(0x423, 7, 1, 1, 0), (0x421, 7, 1, 1, 0)]
        begin = len(old)
        self.assertFalse(explicit_save_completed(old, begin))
        pending, saved = (0x423, 7, 1, 1, 0), (0x421, 7, 1, 1, 0)
        self.assertTrue(explicit_save_completed(old + [pending, saved], begin))
        self.assertTrue(explicit_save_completed(old + [pending, saved, (0xf3, 1, 0, 0, 0)], begin))
        for new in ([saved], [pending], [saved, pending],
                    [pending, (0x421, 8, 1, 1, 0)],
                    [(0x423, 7, 2, 1, 0), saved],
                    [pending, (0x421, 7, 1, 2, 0)],
                    [pending, (0x421, 7, 1, 1, 1)],
                    [pending, (0x424, 24, 1, 1, 0), saved]):
            with self.subTest(new=new):
                self.assertFalse(explicit_save_completed(old + new, begin))


if __name__ == '__main__': unittest.main()
