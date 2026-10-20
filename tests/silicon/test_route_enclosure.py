# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_enclosure import GeometryError, read_tech
from silicon_route_enclosure import audit
from silicon_power_ports import signal_bytes
from silicon_pen_physical import require_fresh_power_recipe, host_memory_budget, require_launch_recipe
from types import SimpleNamespace


TECH = '''UNITS
 DATABASE MICRONS 1000 ;
END UNITS
LAYER Metal1
 TYPE ROUTING ;
END Metal1
LAYER Via1
 TYPE CUT ;
 ENCLOSURE BELOW 0.01 0.05 ;
 ENCLOSURE ABOVE 0.01 0.05 ;
END Via1
LAYER Metal2
 TYPE ROUTING ;
END Metal2
  Via Via1_DC2L DEFAULT
 LAYER Metal1 ;
 RECT {edge} -0.145 0.52 0.145 ;
 LAYER Via1 ;
 RECT -0.095 -0.095 0.095 0.095 ;
 LAYER Metal2 ;
 RECT -0.145 -0.105 0.145 0.105 ;
  END Via1_DC2L
'''
DEF = '''VERSION 5.8 ;
UNITS DISTANCE MICRONS 1000 ;
NETS 1 ;
- actual + ROUTED Metal2 ( 5000 5000 ) Via1_DC2L
  NEW Metal2 ( 5000 5000 ) ( 5500 * ) ;
END NETS
END DESIGN
'''

GENERATOR = '''VIARULE via1Array GENERATE
 LAYER Metal1 ;
 ENCLOSURE 0.05 0.01 ;
 LAYER Metal2 ;
 ENCLOSURE 0.05 0.01 ;
 LAYER Via1 ;
 RECT -0.095 -0.095 0.095 0.095 ;
 SPACING 0.48 BY 0.48 ;
END via1Array
'''
ARRAY = '''VIAS 1 ;
- generated + VIARULE via1Array + CUTSIZE 190 190 + LAYERS Metal1 Via1 Metal2 + CUTSPACING 290 290 + ENCLOSURE 50 10 50 10 + ROWCOL 1 2 ;
END VIAS
SPECIALNETS 1 ;
- VDD + USE POWER + ROUTED Metal1 0 + SHAPE STRIPE ( 2000 2000 ) generated ;
END SPECIALNETS
'''


class RouteEnclosureTests(unittest.TestCase):
    def make(self, directory, edge, routed=DEF):
        tech, route = Path(directory) / 'tech.lef', Path(directory) / 'route.def'
        tech.write_text(TECH.format(edge=edge))
        route.write_text(routed)
        return tech, route

    def test_indented_via_end_is_included(self):
        with tempfile.TemporaryDirectory() as directory:
            tech, _ = self.make(directory, '-0.105')
            self.assertEqual([v['name'] for v in read_tech(tech)[2]], ['Via1_DC2L'])

    def test_actual_known_five_nm_failure_and_repaired_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            tech, route = self.make(directory, '-0.1')
            bad = audit(tech, route)
            self.assertEqual(bad['status'], 'FAIL')
            self.assertEqual(bad['violations'][0]['side'], 'lower')
            tech.write_text(TECH.format(edge='-0.105'))
            fixed = audit(tech, route)
            self.assertEqual(fixed['status'], 'PASS_FIXED_VIA_INTRINSIC_ENCLOSURE')
            self.assertEqual(fixed['via_instances'], 1)

    def test_unknown_via_and_generated_geometry_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            tech, route = self.make(directory, '-0.105', DEF.replace('Via1_DC2L', 'unclassifiedVia'))
            with self.assertRaisesRegex(GeometryError, 'unclassifiedVia'):
                audit(tech, route)
            route.write_text('VIAS 1 ;\n' + DEF)
            with self.assertRaisesRegex(GeometryError, 'generated DEF'):
                audit(tech, route)
            # A DEF definition can shadow a known technology via name. It
            # must not bypass admission merely by indenting the section.
            route.write_text('  VIAS 1 ;\n- Via1_DC2L + RECT Metal1 ( 0 0 ) ( 1 1 ) ;\nEND VIAS\n' + DEF)
            with self.assertRaisesRegex(GeometryError, 'generated DEF'):
                audit(tech, route)

    def test_empty_or_mismatched_route_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            for routed in (DEF.replace('NETS 1', 'NETS 0'), DEF.replace('NETS 1', 'NETS 2'),
                           DEF.replace(' Via1_DC2L', '')):
                tech, route = self.make(directory, '-0.105', routed)
                with self.assertRaises(GeometryError):
                    audit(tech, route)

    def test_explicit_generated_power_array_checks_each_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            tech, route = self.make(directory, '-0.105', ARRAY + DEF)
            tech.write_text(tech.read_text() + GENERATOR)
            fixed = audit(tech, route, allow_generated=True)
            self.assertEqual(fixed['status'], 'PASS_FIXED_VIA_INTRINSIC_ENCLOSURE')
            self.assertEqual(fixed['generated_array_definitions'], 1)
            self.assertTrue(fixed['specialnet_geometry_checked'])
            self.assertEqual(fixed['via_counts']['generated'], 1)
            # A5nm enclosure deficit is a physical violation, not a parser error.
            route.write_text((ARRAY + DEF).replace('ENCLOSURE 50 10 50 10', 'ENCLOSURE 45 10 50 10'))
            bad = audit(tech, route, allow_generated=True)
            self.assertEqual(bad['status'], 'FAIL')
            self.assertEqual([r['side'] for r in bad['violations']], ['lower', 'lower'])

    def test_generated_arrays_reject_pitch_shadow_and_unseen_clauses(self):
        with tempfile.TemporaryDirectory() as directory:
            tech, route = self.make(directory, '-0.105')
            tech.write_text(tech.read_text() + GENERATOR)
            for text, reason in ((ARRAY.replace('290 290', '220 220'), 'pitch'),
                    (ARRAY.replace('- generated +', '- Via1_DC2L +'), 'shadowed'),
                    (ARRAY.replace('ROWCOL 1 2', 'ROWCOL 1 2 + ORIGIN 10 0'), 'clauses'),
                    (ARRAY.replace('ROWCOL 1 2', 'ROWCOL 0 2'), 'bound')):
                with self.subTest(reason=reason):
                    route.write_text(text + DEF)
                    with self.assertRaisesRegex(GeometryError, reason):audit(tech, route, allow_generated=True)

    def test_power_interface_removes_only_exact_required_additions(self):
        old = 'module lemma_pen(\n    wdata);\n input [63:0] wdata;\nendmodule\n'
        new = old.replace('    wdata);', '    wdata,\n    VDDlogic,\n    VDDARRAY,\n    VSS);')
        new = new.replace(' input [63:0]', ' inout VDDlogic;\n inout VDDARRAY;\n inout VSS;\n input [63:0]')
        self.assertEqual(signal_bytes(new), old)
        for changed in (new.replace('    VSS);', '    extra,\n    VSS);'),
                        new.replace(' inout VSS;\n', ''), new + ' inout VDDlogic;\n'):
            with self.subTest(changed=changed), self.assertRaises(ValueError):signal_bytes(changed)

    def test_reloaded_power_export_retains_connections(self):
        suffix = 'module lemma_pen(\n    write,\n    addr,\n    wdata,\n    VDDlogic,\n    VDDARRAY,\n    VSS);\n'
        declarations = ' inout VDDlogic;\n inout VDDARRAY;\n inout VSS;\n'
        body = ' cell u (.VDD(VDDlogic), .VSS(VSS), .A(addr));\nendmodule\n'
        original = suffix + declarations + body
        reloaded = original.replace('    write,\n    addr,', '    write,\n    VDDlogic,\n    VDDARRAY,\n    VSS,\n    addr,').replace('    wdata,\n    VDDlogic,\n    VDDARRAY,\n    VSS);', '    wdata);')
        self.assertEqual(signal_bytes(reloaded, reloaded_power=True), signal_bytes(original))
        self.assertNotEqual(signal_bytes(reloaded.replace('.VDD(VDDlogic)', '.VDD(VSS)'), reloaded_power=True), signal_bytes(original))
        with self.assertRaises(ValueError):signal_bytes(reloaded.replace('    VSS,\n    addr,', '    extra,\n    VSS,\n    addr,'), reloaded_power=True)

    def test_fresh_power_recipe_rejects_historical_netlist_or_repair_bypass(self):
        valid = dict(fresh_core_power_grid=True, selected_implementation=False,
            routed_eco_from=None, completed_eco_route_from=None,
            completed_power_grid_route_from=None, preserve_routed_netlist=False,
            protect_sram_power_edges=False, protect_sram_power_geometry=True,
            defer_global_eco=False)
        require_fresh_power_recipe(SimpleNamespace(**valid))
        for key in ('selected_implementation', 'routed_eco_from', 'completed_eco_route_from',
                    'completed_power_grid_route_from', 'preserve_routed_netlist',
                    'protect_sram_power_edges', 'defer_global_eco'):
            with self.subTest(key=key), self.assertRaises(GeometryError):
                require_fresh_power_recipe(SimpleNamespace(**{**valid, key: True}))
        with self.assertRaises(GeometryError):
            require_fresh_power_recipe(SimpleNamespace(**{**valid, 'protect_sram_power_geometry': False}))

    def test_host_budget_keeps_legacy_floor_and_rejects_unadmitted_reduction(self):
        self.assertEqual(host_memory_budget(SimpleNamespace(host_memory_gib=6,
                         fresh_core_power_grid=False)), (6 << 30, 8 << 30))
        self.assertEqual(host_memory_budget(SimpleNamespace(host_memory_gib=4,
                         fresh_core_power_grid=True)), (4 << 30, 6 << 30))
        for size, fresh in ((4, False), (2, True), (8, True)):
            with self.subTest(size=size, fresh=fresh), self.assertRaises(GeometryError):
                host_memory_budget(SimpleNamespace(host_memory_gib=size, fresh_core_power_grid=fresh))

    def test_launch_eco_cannot_relabel_another_grid_or_bypass_its_exact_scope(self):
        valid = dict(acceptance_launch_buffer=True, routed_eco_from=Path('completed46'),
            detail_route_iterations=8, selected_implementation=False, preserve_routed_netlist=False,
            fresh_core_power_grid=False, vss_clock_grid_source=None, protect_sram_power_edges=False,
            protect_sram_power_geometry=False, completed_eco_route_from=None,
            completed_power_grid_route_from=None, completed_fresh_grid_route_from=None, defer_global_eco=False)
        require_launch_recipe(SimpleNamespace(**valid))
        for key in ('selected_implementation', 'preserve_routed_netlist', 'fresh_core_power_grid',
                    'vss_clock_grid_source', 'protect_sram_power_edges', 'protect_sram_power_geometry',
                    'completed_eco_route_from', 'completed_power_grid_route_from',
                    'completed_fresh_grid_route_from', 'defer_global_eco'):
            with self.subTest(key=key), self.assertRaises(GeometryError):
                require_launch_recipe(SimpleNamespace(**{**valid, key: True}))
        for changed in ({'routed_eco_from': None}, {'detail_route_iterations': 3}):
            with self.subTest(changed=changed), self.assertRaises(GeometryError):
                require_launch_recipe(SimpleNamespace(**{**valid, **changed}))


if __name__ == '__main__':
    unittest.main()
