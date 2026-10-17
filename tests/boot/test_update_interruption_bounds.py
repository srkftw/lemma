"""Keep the original payload qualification independent of the larger new case."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_interrupted_notebook_update import interruption_spec


class InterruptionBounds(unittest.TestCase):
    def test_original_sixteen_sector_protocol_is_not_enlarged(self):
        self.assertEqual(interruption_spec('payload'),
                         (16, 300000000, 2400, 1800000000, 14400))

    def test_new_whole_payload_case_keeps_an_independent_declared_bound(self):
        sectors, transfer, seconds, aggregate, whole = interruption_spec('metadata')
        self.assertEqual(sectors, 1059)
        self.assertEqual((transfer, seconds, aggregate, whole),
                         (900000000, 7200, 2400000000, 21600))
        with self.assertRaises(ValueError):
            interruption_spec('extend-a-failed-run')
