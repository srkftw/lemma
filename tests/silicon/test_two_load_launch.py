# SPDX-License-Identifier: Apache-2.0
from argparse import Namespace
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_two_load_launch import SOURCE,admit,require_recipe,wire_loads,GEOMETRY_SHA
from silicon_synth import sha


class TwoLoadLaunch(unittest.TestCase):
    def test_current_actual_wire_loads_and_changed_source_rejection(self):
        source=SOURCE/'nom.spef'
        if not source.exists():self.skipTest('retained actual route is external to Git')
        loads=wire_loads(source)
        self.assertEqual([row['actual_nominal_total_pF']for row in loads],['0.558108','0.311153'])
        self.assertEqual([len(row['sink_cells'])for row in loads],[2,1])
        with tempfile.TemporaryDirectory()as directory:
            changed=Path(directory)/'wrong.spef';changed.write_text(source.read_text().replace('0.558108','0.058108',1))
            with self.assertRaises(ValueError):wire_loads(changed)

    def test_recipe_rejects_clock_capacity_and_mixed_implementation_changes(self):
        good=Namespace(two_load_launch_from=Path('qualified'),routed_eco_from=SOURCE,
            clock_min_routing_layer='Metal3',detail_route_iterations=8,host_memory_gib=6,selected_implementation=False)
        require_recipe(good)
        for name,value in(('routed_eco_from',None),('clock_min_routing_layer','Metal2'),
            ('detail_route_iterations',3),('host_memory_gib',4),('selected_implementation',True),
            ('well_fill_from',Path('old')),('preserve_routed_netlist',True),('completed_well_fill_route_from',SOURCE)):
            with self.subTest(name=name),self.assertRaises(ValueError):require_recipe(Namespace(**dict(vars(good),**{name:value})))

    def test_exact_completed_precursor_admission_preserves_original_producer(self):
        source=ROOT/'build/silicon/task009-two-load-launch-preflight-a2'
        if not source.exists():self.skipTest('retained actual precursor is external to Git')
        geometry,receipt,inputs=admit(source)
        self.assertEqual(sha(geometry),GEOMETRY_SHA)
        self.assertEqual(receipt.name,'result.json')
        self.assertIn(source/'source-closure.tar.gz',inputs)
        self.assertGreater(len(inputs),30)
        with self.assertRaises(ValueError):admit(source/'candidate')


if __name__=='__main__':unittest.main()
