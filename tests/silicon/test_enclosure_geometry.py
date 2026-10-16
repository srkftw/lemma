# SPDX-License-Identifier: Apache-2.0
"""Independent geometry counterexamples for the pinned enclosure adapter."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_enclosure as geometry


class EnclosureGeometryTests(unittest.TestCase):
    def test_asymmetric_enclosure_is_rigid_orientation_invariant(self):
        cut = geometry.Rect(-95, -95, 95, 95)
        exact = geometry.Rect(-105, -145, 105, 145)
        short = geometry.Rect(-104, -145, 105, 145)
        for orientation in range(8):
            with self.subTest(orientation=orientation):
                c = cut.transformed(orientation)
                self.assertTrue(geometry.enclosure(
                    c, [exact.transformed(orientation)], 10, 50))
                self.assertFalse(geometry.enclosure(
                    c, [short.transformed(orientation)], 10, 50))

    def test_abutting_union_passes_but_same_bbox_notch_fails(self):
        target = geometry.Rect(0, 0, 100, 100)
        left = geometry.Rect(0, 0, 50, 100)
        self.assertTrue(geometry.covers(target, [left, geometry.Rect(50, 0, 100, 100)]))
        self.assertFalse(geometry.covers(target, [left, geometry.Rect(51, 0, 100, 100)]))
        self.assertFalse(geometry.covers(target, [
            geometry.Rect(0, 0, 100, 49), geometry.Rect(0, 50, 100, 100)]))

    def test_side_rules_check_each_cut_without_conflating_upper_and_lower(self):
        cuts = [geometry.Rect(0, 0, 10, 10), geometry.Rect(30, 0, 40, 10)]
        layers = {'Cut': {'rules': [('BELOW', 2, 4), ('ABOVE', 5, 7)]}}
        via = {'name': 'two', 'kind': 'fixed', 'cut': 'Cut',
               'lower': 'M1', 'upper': 'M2', 'shapes': {
                   'Cut': cuts, 'M1': [geometry.Rect(-2, -4, 42, 14)],
                   'M2': [geometry.Rect(-5, -7, 45, 17)]}}
        rows = geometry.check_fixed(layers, [via])
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row['original_enclosure_met'] for row in rows))
        via['shapes']['M2'] = [geometry.Rect(-5, -7, 44, 17)]
        rows = geometry.check_fixed(layers, [via])
        self.assertEqual([(row['side'], row['cut_index']) for row in rows
                          if not row['original_enclosure_met']], [('upper', 1)])

    def test_generated_minimum_enclosure_cannot_be_hidden_by_array_hull(self):
        layers = {'Cut': {'rules': [('BELOW', 2, 4), ('ABOVE', 5, 7)]}}
        via = {'name': 'array', 'kind': 'generated', 'cut': 'Cut',
               'lower': 'M1', 'upper': 'M2', 'shapes': {'Cut': [geometry.Rect(0, 0, 10, 10)]},
               'enclosures': {'M1': (2, 4), 'M2': (5, 7)}, 'pitch': (20, 20)}
        self.assertEqual(len(geometry.check_generators(layers, [via])), 2)
        via['enclosures']['M2'] = (5, 6)
        with self.assertRaisesRegex(geometry.GeometryError, 'minimum enclosure'):
            geometry.check_generators(layers, [via])

    def test_nonintegral_coordinates_and_degenerate_shapes_reject(self):
        self.assertEqual(geometry.dbu('-0.105'), -105)
        with self.assertRaises(geometry.GeometryError):
            geometry.dbu('0.0001')
        with self.assertRaises(geometry.GeometryError):
            geometry.Rect(0, 0, 0, 1)

    def test_truncated_or_zero_length_gds_rejects_without_looping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.gds'
            for data in (b'\0', b'\0\0\0\0', struct.pack('>HBB', 12, 3, 5) + b'\0'):
                with self.subTest(data=data):
                    path.write_bytes(data)
                    with self.assertRaises(geometry.GeometryError):
                        geometry.scan_gds_cuts(path, {(19, 0): 'Via1'})

    def test_complete_input_closure_rejects_one_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            held = {}
            for index in range(34):
                name = f'input-{index}.lef'
                data = f'original geometry {index}\n'.encode()
                (root / name).write_bytes(data)
                held[name] = hashlib.sha256(data).hexdigest()
            geometry.verify_inputs(root, held)
            (root / 'input-17.lef').write_bytes(b'changed rule\n')
            with self.assertRaisesRegex(geometry.GeometryError, 'input-17.lef'):
                geometry.verify_inputs(root, held)
            with self.assertRaisesRegex(geometry.GeometryError, 'incomplete'):
                geometry.verify_inputs(root, {})


if __name__ == '__main__':
    unittest.main()
