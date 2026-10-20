# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import hashlib
import io
import tarfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_filler_source import all_row_plan, lef_masters
from silicon_filler_geometry import report_gaps, original_pg_rectangles, insertion_source_binding
from silicon_row_filler import require_reserve, source_changes


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
    def test_original_multirect_power_pin_preserves_all_fingers_and_rejects_unknowns(self):
        body = '  PIN VDD\n    USE POWER ;\n    PORT\n      LAYER Metal1 ;\n        RECT 0 3.56 3.36 4 ;\n        RECT 2.405 2.585 2.665 4 ;\n        RECT 0.81 2.14 1.07 4 ;\n    END\n  END VDD\n'
        self.assertEqual(original_pg_rectangles(body, 'VDD'),
                         [(0, 3560, 3360, 4000), (2405, 2585, 2665, 4000), (810, 2140, 1070, 4000)])
        for changed in (body.replace('Metal1', 'Metal2'), body.replace('POWER', 'GROUND'),
                        body.replace('2.405', '2.4051'), body.replace('RECT 0.81', 'POLYGON 0.81'),
                        body.replace('        RECT 0 3.56 3.36 4 ;', ''),
                        body.replace('      LAYER Metal1 ;', '      LAYER Metal1 ;\n      LAYER Metal2 ;')):
            # Removing a complete known rectangle is a source-identity failure,
            # rather than a reason to reject all legitimate multi-rect ports.
            if changed == body.replace('        RECT 0 3.56 3.36 4 ;', ''):
                self.assertNotEqual(original_pg_rectangles(changed, 'VDD'), original_pg_rectangles(body, 'VDD'))
            else:
                with self.subTest(changed=changed), self.assertRaises(ValueError): original_pg_rectangles(changed, 'VDD')

    def test_completed_insertion_code_requires_exact_original_capsule_and_literal_physics(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory); archive_path = prepared/'source-closure.tar.gz'
            missing_script = Path(__file__).resolve().parents[2]/'scripts/silicon_fixture_archived.py'
            raw = b'original closed producer code\n'; digest = hashlib.sha256(raw).hexdigest()
            with tarfile.open(archive_path, 'w:gz') as archive:
                entry = tarfile.TarInfo('inputs/007-'+missing_script.name); entry.size = len(raw)
                archive.addfile(entry, io.BytesIO(raw))
            produced = {'source_archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                        'source_inputs': {str(missing_script): digest}}
            self.assertEqual(insertion_source_binding(produced, prepared)[0]['original_sha256'], digest)
            for bad in ({'source_inputs': {str(missing_script): '0'*64}},
                        {'source_archive_sha256': '0'*64},
                        {'source_inputs': {str(prepared/'changed.odb'): digest}}):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    insertion_source_binding(dict(produced, **bad), prepared)
            with tarfile.open(archive_path, 'w:gz') as archive:
                for index, data in enumerate((raw, b'different alleged original')):
                    entry = tarfile.TarInfo(f'inputs/{index:03d}-'+missing_script.name); entry.size = len(data)
                    archive.addfile(entry, io.BytesIO(data))
            produced['source_archive_sha256'] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): insertion_source_binding(produced, prepared)

    def test_changed_or_missing_source_is_a_reportable_failed_seal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source'; path.write_bytes(b'first')
            inputs = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(source_changes(inputs), [])
            path.write_bytes(b'changed')
            self.assertEqual(source_changes(inputs), [{'path': str(path), 'reason': 'changed'}])
            path.unlink()
            self.assertEqual(source_changes(inputs)[0]['path'], str(path))
            self.assertIn('FileNotFoundError', source_changes(inputs)[0]['reason'])

    def test_admission_adds_literal_owned_cap_and_reserve_without_shift_precedence(self):
        cap, reserve = 1 << 30, 8 << 30
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

    def test_two_extra_macro_right_sites_preserve_functional_cells_and_left_sites(self):
        text, native, masters = fixture(); result = all_row_plan(text, native, masters, macro_right_extra_sites=2)
        self.assertEqual(result['schema'], 'lemma-original-row-filler-plan/2')
        self.assertEqual(result['outward_rounded_macro_sites'], 5)
        covered = {site for cell in result['fillers'] for site in range(cell['location'][0]//480,
                   cell['location'][0]//480+cell['sites'])}
        self.assertEqual(covered, {0, 1, 4, 5, 13, 14})
        for changed in (1, -2, True, 2.0):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                all_row_plan(text, native, masters, macro_right_extra_sites=changed)
        native['instances'].append({'name': 'old_fixed', 'master': 'logic', 'orientation': 'R0',
                                    'location': [5280, 0], 'origin': [5280, 0]})
        result = all_row_plan(text, native, masters, macro_right_extra_sites=2)
        self.assertEqual(result['functional_instances'], 3)
        self.assertEqual(result['macro_right_well_keepout']['preserved_functional_cells_in_spacer_keepout'], ['old_fixed'])
        self.assertEqual(result['outward_rounded_macro_sites'], 3)

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
