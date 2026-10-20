# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_enclosure import GeometryError
from silicon_fresh_global import raw_relation, native_script


class CompletedFreshGlobalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = [[layer, x, y, 18.0, 18.0]
                for layer in ('Metal2', 'Metal3', 'Metal4', 'Metal5')
                for x in range(145) for y in range(118)]
        cls.new = {'schema': 'raw fixture', 'x_grid_DBU': list(range(145)),
                   'y_grid_DBU': list(range(118)), 'data': rows}
        cls.old = deepcopy(cls.new)
        cls.target = next(i for i, row in enumerate(rows) if row[:3] == ['Metal3', 125, 56])
        cls.old['data'][cls.target][4] = 19.0

    def test_complete_raw_map_preserves_capacity_and_old_failure(self):
        result = raw_relation(self.old, self.new)
        self.assertEqual(result['raw_cells'], 68440)
        self.assertEqual(result['original_raw_excess'], [['Metal3', 125, 56, 18.0, 19.0]])
        self.assertEqual(self.old['data'][self.target][4], 19.0)

    def test_no_capacity_increase_hidden_excess_or_partial_coverage(self):
        for name in ('capacity', 'excess', 'missing', 'duplicate', 'coerced_index', 'unknown_schema'):
            changed = deepcopy(self.new)
            if name == 'capacity':
                changed['data'][0][3] += 1
            elif name == 'excess':
                changed['data'][self.target][4] = 19.0
            elif name == 'missing':
                changed['data'].pop()
            elif name == 'duplicate':
                changed['data'][1] = changed['data'][0].copy()
            elif name == 'coerced_index':
                index = next(i for i, row in enumerate(changed['data']) if row[1] == 1)
                changed['data'][index][1] = True
            else:
                changed['extra'] = 'unadmitted'
            with self.subTest(name=name), self.assertRaises(GeometryError):
                raw_relation(self.old, changed)

    def test_original_marker_cannot_be_removed_from_the_comparison(self):
        old = deepcopy(self.old)
        old['data'][self.target][4] = 18.0
        with self.assertRaises(GeometryError):
            raw_relation(old, self.new)

    def test_native_pre_and_post_check_full_snapshot_and_original_driver_chains(self):
        script = native_script(Path('/source.odb'), Path('/current.odb'),
                               Path('/report.json'), Path('/source.lib'))
        compile(script, '<actual emitted native script>', 'exec')
        self.assertIn("snapshot(b)==snapshot(nb)", script)
        self.assertIn('from silicon_buffered_pins import assess as endpoints', script)
        self.assertIn("assess(Path('/current.odb')", script)
        self.assertNotIn('dbInst_destroy', script)


if __name__ == '__main__':
    unittest.main()
