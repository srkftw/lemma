# SPDX-License-Identifier: Apache-2.0
from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_well_fill_route import admit,require_recipe,require_predecessor_relations


class WellFillRoute(unittest.TestCase):
    def test_scoped_process_relation_preserves_failed_metal_and_rejects_new_findings(self):
        gds={'status':'FAIL','geometry':{'status':'FAIL_FILLER_GAP_OR_METAL_SUBSET',
             'new_filler_Metal1_rule_subset':[dict(net=net,newly_introduced_clearance_area_nm2=0,
                 positive_area_conductor_intersection_nm2=0,opposite_native_supply_conflict_area_nm2=0)
                 for net in ('VDDlogic','VSS')]}}
        nwell={'status':'PASS_SCOPED_ORIGINAL_NWELL_TABLE_ONLY_NOT_FULL_DRC',
               'results':[{'total':0,'category_counts':{}}]}
        require_predecessor_relations(gds,nwell)
        for change in ('new_metal','direct_short','unknown_supply','empty','relabeled_pass','boolean'):
            bad=deepcopy(gds);rows=bad['geometry']['new_filler_Metal1_rule_subset']
            if change=='new_metal':rows[0]['newly_introduced_clearance_area_nm2']=1
            elif change=='direct_short':rows[0]['positive_area_conductor_intersection_nm2']=1
            elif change=='unknown_supply':rows[0]['net']='VDDARRAY'
            elif change=='empty':rows.clear()
            elif change=='boolean':rows[0]['positive_area_conductor_intersection_nm2']=False
            else:bad['status']='PASS_FULL_PROCESS'
            with self.subTest(change=change),self.assertRaises(ValueError):require_predecessor_relations(bad,nwell)
        for changed in ({'total':1,'category_counts':{'NW.b':1}}, {'total':False,'category_counts':{}},
                        {'total':0,'category_counts':{'NW.b':1}}):
            with self.assertRaises(ValueError):require_predecessor_relations(gds,dict(nwell,results=[changed]))

    def test_recipe_preserves_clock_limits_and_requires_fresh_route(self):
        args=Namespace(well_fill_from=Path('exact'),routed_eco_from=Path('selected06'),
                       clock_min_routing_layer='Metal3',detail_route_iterations=8,host_memory_gib=6,
                       selected_implementation=False)
        require_recipe(args)
        for key,value in (('routed_eco_from',None),('clock_min_routing_layer','Metal2'),
                          ('detail_route_iterations',3),('host_memory_gib',4),
                          ('preserve_routed_netlist',True),('preferred_access_from',Path('old')),
                          ('decode_launch_buffer_from',Path('other'))):
            with self.subTest(key=key),self.assertRaises(ValueError):require_recipe(Namespace(**dict(vars(args),**{key:value})))

    def test_actual_retained_sources_are_admitted_without_rerouting_or_reexecution(self):
        directory=ROOT/'build/silicon/task009-repaired-spacer-insertion-a1'
        if not directory.exists():self.skipTest('actual external layout producers not retained')
        geometry,receipt,inputs=admit(directory)
        self.assertEqual(geometry,directory/'candidate/filled.odb')
        self.assertEqual(receipt,directory/'result.json')
        self.assertGreater(len(inputs),100)


if __name__=='__main__':unittest.main()
