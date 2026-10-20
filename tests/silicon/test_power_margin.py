# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_enclosure import GeometryError
from silicon_power_margin import corner_proof
from silicon_power_margin_route import require_recipe
from silicon_power_clearance import parse_paths, rectangular_clearance
from silicon_enclosure import Rect


class PowerMarginTests(unittest.TestCase):
    def test_conservative_original_rectangle_with_Euclidean_corners(self):
        proof=corner_proof()
        self.assertEqual(proof['worst_inside_corner_squared_nm2'],42050)
        self.assertLess(42050,210**2)
        # A smaller210nm rectangle is unsafe even when the original router
        # correctly enforces its full210nm diagonal distance.
        self.assertGreater(2*(380-210)**2,210**2)
        self.assertLess(380,420)
        for x in range(0,420,5):
            for y in range(0,420,5):
                self.assertLess(max(x-275,0)**2+max(y-275,0)**2,210**2)
        for parameters in [(210,210,420),(270,210,420),(275,200,420),(275,210,415)]:
            with self.subTest(parameters=parameters),self.assertRaises(GeometryError):
                corner_proof(*parameters)

    def test_real_native_margin_distinguishes_via_repair_and_clock_failures(self):
        power=[454940,272015,455620,272305]
        self.assertEqual(rectangular_clearance([454460,272700,454660,272990],power),395)
        self.assertEqual(rectangular_clearance([454460,272835,454660,273125],power),530)
        self.assertEqual(rectangular_clearance([424660,469040,426340,469240],[34680,469640,995880,472140]),400)

    def test_native_DEF_extension_patch_and_fixed_via_binding_grammar(self):
        widths={'Metal1':160,'Metal2':200}
        vias={'Via1_YY':{'shapes':{'Metal1':[Rect(-105,-145,105,145)],'Metal2':[Rect(-100,-145,100,145)]}}}
        context=(widths,vias,{})
        record='- n ( i p ) + ROUTED Metal2 ( 0 0 0 ) ( 1000 0 40 ) RECT ( -100 -100 100 100 ) Via1_YY'
        shapes,patches=parse_paths(record,context)
        self.assertEqual(shapes[0],('wire','Metal2',(0,-100,1040,100),None,None))
        self.assertEqual(shapes[1],('patch','Metal2',(900,-100,1100,100),None,None))
        self.assertEqual(patches,[('Metal2',(1000,0))])
        self.assertIn(('via','Metal1',(895,-145,1105,145),'Via1_YY',(1000,0)),shapes)
        for old,new in [('Via1_YY','UnknownVia'),('Metal2 (','Metal2 UNKNOWN ('),('1000 0 40','1000 1000 40'),('ROUTED','FIXED')]:
            with self.subTest(mutation=old),self.assertRaises(ValueError):parse_paths(record.replace(old,new),context)

    def test_new_grid_route_cannot_use_old_guides_or_weaken_constraints(self):
        valid=dict(power_margin_from=Path('build/pilot'),capacity_launch_buffer_from=Path('build/327'),
                   routed_eco_from=Path('build/104'),clock_min_routing_layer='Metal3',detail_route_iterations=8,
                   host_memory_gib=6,selected_implementation=False,preferred_access_from=None,
                   preferred_access_preflight_only=False)
        require_recipe(SimpleNamespace(**valid))
        for key,value in [('capacity_launch_buffer_from',None),('routed_eco_from',None),('clock_min_routing_layer','Metal2'),
                          ('detail_route_iterations',3),('host_memory_gib',4),('selected_implementation',True),
                          ('preferred_access_from',Path('build/oldguide')),('preferred_access_preflight_only',True)]:
            with self.subTest(key=key),self.assertRaises(GeometryError):require_recipe(SimpleNamespace(**{**valid,key:value}))


if __name__=='__main__':unittest.main()
