# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from pathlib import Path
import json
import hashlib
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_geometry_export import validate
from silicon_gds_geometry import layer_mapping, cardinal_angle, main as geometry_main
from silicon_pen_process import klayout_report_counts, OwnedProcessStop, klayout_original_process


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
    def test_inputs_only_exit_follows_final_source_and_deadline_refusal(self):
        # Exercise the actual formerly premature-return branch. Only source
        # admission is isolated; no fixture is presented as physical evidence.
        for failure in ('source_change', 'deadline'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); out = root/'build/process'
                source = root/'source'; source.write_text('before')
                args = SimpleNamespace(work_dir=out, route=root/'route', klayout_verified_gds=root/'verified',
                    klayout_prepare_from=None,
                    klayout_rules_source=root/'rules', klayout_bin=root/'tool', process_seconds=180,
                    whole_seconds=400, process_drc_only=False, drc_step_microns=None,
                    direct_import_extraction=False, connectivity_only_extraction=False,
                    continue_from_drc_attempt=None, question='Unit control-flow fault only', klayout_inputs_only=True)
                def admitted(*values):
                    values[-1]['source_inputs'] = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
                    if failure == 'source_change': source.write_text('after')
                    return root/'unused.gds', root/'unused-deck', root/'unused-default'
                clock = patch('silicon_pen_process.time.monotonic', side_effect=[0, 501, 501]) if failure == 'deadline' else patch('silicon_pen_process.time.monotonic', side_effect=time.monotonic)
                with patch('silicon_pen_process.ROOT', root), patch('silicon_pen_process.resource.setrlimit'), \
                     patch('silicon_pen_process.admit_original_klayout_inputs', side_effect=admitted), clock:
                    self.assertEqual(klayout_original_process(args), 1)
                result = json.loads((out/'result.json').read_text())
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(result['commands'], [])
                self.assertFalse(result['source_seal_equal'] if failure == 'source_change' else result['original_whole_deadline_met'])

    def test_fractional_or_nonfinite_master_rotation_cannot_be_truncated(self):
        for angle in [0, 90, 180, 270, 360, -90]:
            self.assertEqual(cardinal_angle(angle), angle % 360)
        for angle in [.1, 90.1, -.1, float('nan'), float('inf'), True, '90']:
            with self.subTest(angle=angle), self.assertRaises(ValueError): cardinal_angle(angle)

    def test_source_change_after_admission_downgrades_component_and_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); source = out/'source'; source.write_text('before')
            config = out/'config.json'
            config.write_text(json.dumps({'schema': 'lemma-native-gds-geometry-inputs/1',
                'output_directory': str(out), 'source_inputs': {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}}))
            def changed(_):
                source.write_text('after')
                return {'status': 'PASS_FIXTURE_CHECK_ONLY'}
            with patch('silicon_gds_geometry.check', side_effect=changed), self.assertRaises(ValueError):
                geometry_main(config)
            result = json.loads((out/'geometry.json').read_text())
            self.assertEqual(result['status'], 'FAIL')
            self.assertFalse(result['source_seal_equal'])

    def test_owned_cleanup_kills_an_actual_TERM_ignoring_child(self):
        child = subprocess.Popen([sys.executable, '-c',
            "import signal,time; signal.signal(signal.SIGTERM, lambda *_:None); print('READY',flush=True); time.sleep(30)"],
            stdout=subprocess.PIPE, start_new_session=True, text=True)
        try:
            self.assertTrue(select.select([child.stdout], [], [], 2)[0])
            self.assertEqual(child.stdout.readline().strip(), 'READY')
            guard = OwnedProcessStop(); guard.stop({child.pid}); time.sleep(.55)
            self.assertIsNone(child.poll())
            guard.stop({child.pid})
            self.assertEqual(child.wait(timeout=2), -signal.SIGKILL)
            self.assertTrue(guard.killed)
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=2)
            child.stdout.close()

    def test_zero_report_needs_complete_original_deck_and_top_binding(self):
        valid = "<report-database><generator>drc: script='/original/deck.drc'</generator><top-cell>lemma_pen</top-cell><categories/><items/></report-database>"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'report.lyrdb'
            path.write_text(valid)
            self.assertFalse(klayout_report_counts(path, 'lemma_pen', Path('/original/deck.drc')))
            for text in [valid.replace('lemma_pen', 'inverter'), valid.replace('<items/>', ''),
                         valid.replace('/original/deck.drc', '/wrong/deck.drc'),
                         valid.replace('report-database', 'unrelated'), valid[:-12]]:
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(Exception):
                    klayout_report_counts(path, 'lemma_pen', Path('/original/deck.drc'))

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
