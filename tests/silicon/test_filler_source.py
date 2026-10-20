# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_filler_source import all_row_plan, lef_masters
from silicon_filler_geometry import report_gaps
from silicon_row_filler import require_reserve


def fixture():
    masters = {'logic': {'size_nm': (960, 3780), 'class': 'CORE', 'pins': ['A', 'Y', 'VDD', 'VSS']},
               'ram': {'size_nm': (960, 3780), 'class': 'BLOCK', 'pins': ['VDD!', 'VSS!']}}
    masters.update({f'sg13g2_fill_{size}': {'size_nm': (480*size, 3780), 'class': 'CORE SPACER',
                                        'pins': ['VDD', 'VSS']} for size in (1, 2, 4, 8)})
    cells = [{'name': 'a', 'master': 'logic', 'orientation': 'R0', 'origin': [960, 0], 'location': [960, 0]},
             {'name': 'b', 'master': 'logic', 'orientation': 'R0', 'origin': [2880, 0], 'location': [2880, 0]}]
    # A macro edge at5040 must round outward to5280, never produce a partial
    # or overlapping480nm spacer. Other two SRAMs lie outside this tiny row.
    for index, x in enumerate((4080, 10000, 12000)):
        cells.append({'name': f'pen_sram_lane{index}', 'master': 'ram', 'orientation': 'R0',
                      'origin': [x, 0], 'location': [x, 0]})
    return ('UNITS DISTANCE MICRONS 1000 ;\nROW ROW_0 CoreSite 0 0 N DO 15 BY 1 STEP 480 0 ;\n',
            {'dbu_per_micron': 1000, 'instances': cells}, masters)


class OriginalRowFillerTests(unittest.TestCase):
    def test_admission_adds_literal_owned_cap_and_reserve_without_shift_precedence(self):
        cap, reserve = 1 << 30, int(6.5*(1 << 30))
        require_reserve(cap+reserve)
        for available in (cap+reserve-1, cap, True, float(cap+reserve)):
            with self.subTest(available=available), self.assertRaises(ValueError): require_reserve(available)

    def test_actual_original_report_retains_twelve_tangent_witnesses(self):
        path = Path(__file__).resolve().parents[2]/'build/silicon/task009-selected-original-klayout-process-a1/main.lyrdb'
        if not path.exists(): self.skipTest('actual external process report not retained')
        rows = report_gaps(path)
        self.assertEqual(len(rows), 3717)
        self.assertEqual(sum(box[3]-box[1] == 2 for _, box in rows), 12)
        self.assertTrue(all(box[0] < box[2] and box[1] < box[3] for _, box in rows))

    def test_all_unoccupied_sites_and_only_original_physical_spacers(self):
        text, native, masters = fixture(); result = all_row_plan(text, native, masters)
        self.assertEqual(result['functional_instances'], 2)
        self.assertEqual(result['outward_rounded_macro_sites'], 3)
        self.assertEqual(result['filler_sites'], 8)
        covered = set()
        for cell in result['fillers']:
            first = cell['location'][0]//480
            covered.update(range(first, first+cell['sites']))
            self.assertEqual(cell['origin'], cell['location'])
            self.assertEqual(cell['orientation'], 'R0')
        self.assertEqual(covered, {0, 1, 4, 5, 11, 12, 13, 14})
        self.assertEqual(result['all_row_sites'], result['functional_sites']+
                         result['outward_rounded_macro_sites']+result['filler_sites'])

    def test_wrong_grid_orientation_padding_macro_and_filler_interface_refuse(self):
        mutations = [lambda n, m: n['instances'][0]['location'].__setitem__(0, 961),
                     lambda n, m: n['instances'][0].update(orientation='MX', origin=[960, 3780]),
                     lambda n, m: n['instances'][1].update(location=[2400, 0], origin=[2400, 0]),
                     lambda n, m: n['instances'][2].update(location=[960, 0], origin=[960, 0]),
                     lambda n, m: m['sg13g2_fill_2']['pins'].append('hidden_signal'),
                     lambda n, m: n['instances'].append(deepcopy(n['instances'][0]))]
        for mutate in mutations:
            text, native, masters = fixture(); mutate(native, masters)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): all_row_plan(text, native, masters)
        text, native, masters = fixture()
        with self.assertRaises(ValueError): all_row_plan(text.replace('STEP 480', 'STEP 481'), native, masters)

    def test_original_lef_requires_literal_native_dimensions_and_class(self):
        text = 'MACRO fill\n  CLASS CORE SPACER ;\n  SIZE 0.96 BY 3.78 ;\n  PIN VDD\n  PIN VSS\nEND fill\n'
        self.assertEqual(lef_masters(text)['fill'], {'size_nm': (960, 3780), 'class': 'CORE SPACER', 'pins': ['VDD', 'VSS']})
        for changed in [text.replace('0.96', '0.9601'), text.replace('  CLASS CORE SPACER ;\n', ''), text+text]:
            with self.subTest(changed=changed), self.assertRaises(ValueError): lef_masters(changed)


if __name__ == '__main__': unittest.main()
