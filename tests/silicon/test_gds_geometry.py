# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_geometry_export import validate
from silicon_gds_geometry import layer_mapping


def native_fixture():
    wire = {'kind': 'signal_wire_or_rect', 'layer': 'Metal2', 'rect_nm': [0, 0, 200, 1000]}
    witness = dict(wire, kind='decoder_rect_witness')
    return {'schema': 'lemma-opendb-native-geometry/1', 'db_units_per_micron': 1000,
            'top': 'fixture', 'nets': [
                {'name': 'signal', 'type': 'SIGNAL', 'iterms': [['real_cell', 'A']], 'bterms': ['port'],
                 'shapes': [wire, witness, {'kind': 'signal_via', 'layer': 'Via1', 'rect_nm': [0, 0, 190, 190]}],
                 'wire_shape_count': 1, 'wire_via_count': 1, 'RECT_count': 1, 'special_box_count': 0},
                {'name': 'VSS', 'type': 'GROUND', 'iterms': [['real_cell', 'VSS']], 'bterms': [],
                 'shapes': [{'kind': 'special_wire', 'layer': 'Metal2', 'rect_nm': [0, 1000, 4000, 2000]},
                            {'kind': 'special_via', 'layer': 'Via1', 'rect_nm': [1000, 1000, 1190, 1190]}],
                 'wire_shape_count': 0, 'wire_via_count': 0, 'RECT_count': 0, 'special_box_count': 2}],
            'ports': [{'terminal': 'port', 'net': 'signal',
                       'shapes': [{'kind': 'port', 'layer': 'Metal2', 'rect_nm': [0, 0, 200, 200]}]}]}


class NativeGdsGeometryTests(unittest.TestCase):
    def test_native_decoder_rect_full_dimensions_must_match(self):
        data = native_fixture()
        self.assertEqual(validate(data)['native_RECT_dimensions_bound'], 1)
        # Matching patch origins cannot conceal a truncated native patch.
        data['nets'][0]['shapes'][1]['rect_nm'] = [0, 0, 200, 995]
        with self.assertRaisesRegex(ValueError, 'RECT dimensions'): validate(data)

    def test_literal_units_rectangles_and_terminal_ownership(self):
        mutations = [lambda d: d.update(db_units_per_micron=1000.0),
                     lambda d: d['nets'][0]['shapes'][0]['rect_nm'].__setitem__(0, False),
                     lambda d: d['nets'][0].update(wire_via_count=True),
                     lambda d: d['ports'][0].update(net='wrong_net'),
                     lambda d: d['nets'][0]['iterms'].append(['real_cell', 'A']),
                     lambda d: d.update(unqualified='field')]
        for mutation in mutations:
            data = native_fixture(); mutation(data)
            with self.subTest(data=data), self.assertRaises(ValueError): validate(data)

    def test_original_map_binds_every_routed_metal_cut_and_port_purpose(self):
        original = Path(__file__).resolve().parents[2]/'build/silicon/task009-klayout-native-master-pilot-a3/sg13g2.map'
        if not original.exists(): self.skipTest('original external PDK map not installed')
        drawing, pins = layer_mapping(original)
        self.assertEqual(drawing['Via1'], (19, 0))
        self.assertEqual(drawing['TopVia2'], (133, 0))
        self.assertEqual(pins['Metal5'], (67, 2))


if __name__ == '__main__':
    unittest.main()
