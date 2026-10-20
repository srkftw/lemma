# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_enclosure import GeometryError
from silicon_fresh_margin import require_recipe, reviewed_grid, prepare, GRID_SHA, MACRO, require_macro_placement
from silicon_pen_physical import require_clock_layer_recipe, require_route_iterations, qualified_clock_layer_inputs
from silicon_synth import ROOT, sha


class FreshMarginTests(unittest.TestCase):
    def test_public_dbBox_coordinates_preserve_exact_macro_extent_and_orientation(self):
        # Pinned OpenDB Python exposes coordinates, not the C++ Rect dx/dy API.
        def instance(x=120000, y=100000, width=784480, height=118780,
                     orientation='R0', master=MACRO):
            return SimpleNamespace(
                getMaster=lambda: SimpleNamespace(getName=lambda: master),
                getBBox=lambda: SimpleNamespace(xMin=lambda: x, yMin=lambda: y,
                                                xMax=lambda: x + width, yMax=lambda: y + height),
                getOrient=lambda: orientation)
        require_macro_placement(instance(), 120000, 100000, 'R0')
        require_macro_placement(instance(y=600000, orientation='MX'), 120000, 600000, 'MX')
        for changes in ({'width': 784479}, {'height': 118779}, {'x': 120001},
                        {'y': 100001}, {'orientation': 'MX'}, {'master': 'other'}):
            with self.subTest(changes=changes), self.assertRaises(GeometryError):
                require_macro_placement(instance(**changes), 120000, 100000, 'R0')
        with self.assertRaises(GeometryError):
            require_macro_placement(None, 120000, 100000, 'R0')

    def recipe(self, **changes):
        args = dict(fresh_native_margin_grid=True, fresh_core_power_grid=True,
                    protect_sram_power_geometry=True, group_button_bus=True,
                    clock_min_routing_layer='Metal3', detail_route_iterations=8,
                    host_memory_gib=6, selected_implementation=False)
        args.update(changes)
        return SimpleNamespace(**args)

    def test_fresh_recipe_cannot_import_legacy_layout_or_remove_normal_repairs(self):
        require_recipe(self.recipe())
        for key in ('routed_eco_from', 'preserve_routed_netlist', 'selected_implementation',
                    'vss_clock_grid_source', 'defer_global_eco', 'power_margin_from',
                    'preferred_access_from', 'completed_fresh_grid_route_from',
                    'completed_hold_decode_route_from', 'hold_decode_from',
                    'capacity_launch_buffer_from', 'center_validation_cones'):
            with self.subTest(key=key), self.assertRaises(GeometryError):
                require_recipe(self.recipe(**{key: True}))
        for key, value in [('fresh_core_power_grid', False), ('protect_sram_power_geometry', False),
                           ('group_button_bus', False), ('clock_min_routing_layer', 'Metal2'),
                           ('detail_route_iterations', 3), ('host_memory_gib', 4)]:
            with self.subTest(key=key), self.assertRaises(GeometryError):
                require_recipe(self.recipe(**{key: value}))

    def test_fresh_clock_path_does_not_admit_old_guides(self):
        args = self.recipe()
        require_clock_layer_recipe(args)
        require_route_iterations(args)
        self.assertEqual(qualified_clock_layer_inputs(args), [])
        with self.assertRaises(GeometryError):
            require_clock_layer_recipe(self.recipe(routed_eco_from=Path('build/old327')))
        # The opt-in never weakens the legacy scope when absent.
        require_recipe(SimpleNamespace())

    def test_grid_generation_is_exact_prior_source_without_old_geometry(self):
        original = ROOT / 'tooling/silicon/pen-power-grid.tcl'
        before = original.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'grid.tcl'
            reviewed_grid(original, output)
            self.assertEqual(sha(output), GRID_SHA)
            self.assertEqual(original.read_bytes(), before)
            self.assertIn('-offset 10 -nets {VDDlogic}', output.read_text())
            self.assertIn('-offset 36.665 -nets {VDDARRAY}', output.read_text())
            self.assertIn('-offset 65.330 -nets {VSS}', output.read_text())
            # A previously owned output cannot be overwritten by a new plan.
            sealed = output.read_bytes()
            with self.assertRaises(GeometryError):
                reviewed_grid(original, output)
            self.assertEqual(output.read_bytes(), sealed)

    def test_grid_rejects_an_unrelated_power_or_via_change(self):
        original = ROOT / 'tooling/silicon/pen-power-grid.tcl'
        for before, after in [('width 0.33', 'width 0.32'), ('-cut_pitch 0.48', '-cut_pitch 0.41'),
                              ('-width 2.5 -pitch 80', '-width 2.5 -pitch 81')]:
            with self.subTest(change=before), tempfile.TemporaryDirectory() as directory:
                wrong = Path(directory) / 'wrong.tcl'
                wrong.write_text(original.read_text().replace(before, after))
                with self.assertRaises(GeometryError):
                    reviewed_grid(wrong, Path(directory) / 'output.tcl')

    def test_private_receipt_or_another_candidate_cannot_be_a_standard_admission(self):
        for status, candidate, candidate_only in [
                ('PASS_PRIVATE_HEAD_BYPASS_ACTUAL_MAPPING_FULLWIDTH_AND_FEEDBACK_GRAPH_ONLY', '97b077', True),
                ('PASS_ISOLATED_CANDIDATE_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING', 'wrong', True),
                ('PASS_MAINTAINED_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING', '97b077', False)]:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                mapping = Path(directory)
                (mapping / 'result.json').write_text(json.dumps(dict(
                    status=status, candidate_only=candidate_only,
                    candidate_source={'sha256': candidate})))
                with self.assertRaises(GeometryError):
                    prepare(mapping, ROOT / 'tooling/silicon/pen-power-grid.tcl', mapping / 'grid.tcl')
                self.assertFalse((mapping / 'grid.tcl').exists())


if __name__ == '__main__':
    unittest.main()
