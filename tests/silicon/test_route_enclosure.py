# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_enclosure import GeometryError, read_tech
from silicon_route_enclosure import audit


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


if __name__ == '__main__':
    unittest.main()
