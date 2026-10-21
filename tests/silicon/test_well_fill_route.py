# SPDX-License-Identifier: Apache-2.0
from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_well_fill_route import admit,require_recipe,require_predecessor_relations,spacer_serialization,completed_route_inputs,require_master_exports


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

    def test_literal_master_library_and_object_properties(self):
        before={'libraries':{'original':'a'*64},'properties':{'lib/master':'literal body'}}
        require_master_exports(before,deepcopy(before))
        for label in ('missing_library','changed_shape','changed_property','missing_property','float','extra_field'):
            bad=deepcopy(before)
            if label=='missing_library':bad['libraries'].clear()
            elif label=='changed_shape':bad['libraries']['original']='b'*64
            elif label=='changed_property':bad['properties']['lib/master']='other body'
            elif label=='missing_property':bad['properties'].clear()
            elif label=='float':bad['properties']['lib/master']=1.0
            else:bad['ignored']=True
            with self.subTest(label=label),self.assertRaises(ValueError):require_master_exports(before,bad)

    def test_exact_actual_spacer_serialization_and_consequential_negatives(self):
        route=ROOT/'build/silicon/task009-well-fill-route-a1'
        cdl=ROOT/'build/silicon/deps/ihp-open-pdk/ihp-sg13g2/libs.ref/sg13g2_stdcell/cdl/sg13g2_stdcell.cdl'
        plan_path=ROOT/'build/silicon/task009-repaired-spacer-insertion-a1/row-plan.json'
        if not(route/'routed.v').exists():self.skipTest('actual completed route not retained')
        original=(route/'pre-eco.v').read_text();actual=(route/'routed.v').read_text()
        plan=json.loads(plan_path.read_text());source=cdl.read_text()
        self.assertTrue(spacer_serialization(original,actual,plan,source)['functional_bytes_equal'])
        first=plan['fillers'][0];line=f" {first['master']} {first['name']} ();\n"
        for label,changed in [('missing',actual.replace(line,'',1)),('duplicate',actual+line),
            ('master',actual.replace(line,line.replace(first['master'],'sg13g2_inv_1'),1)),
            ('logic_pin',actual.replace(line,line.replace('();','(.A(clk));'),1)),
            ('unknown_name',actual.replace(line,line.replace(first['name'],'task009_row_fill_UNKNOWN'),1)),
            ('functional',actual.replace('input clk;','input WRONGclk;',1))]:
            self.assertNotEqual(changed,actual)
            with self.subTest(label=label),self.assertRaises(ValueError):spacer_serialization(original,changed,plan,source)
        with self.assertRaises(ValueError):spacer_serialization(original,actual,plan,source.replace('*.PININFO VDD:B VSS:B','Rbad VDD VSS 1',1))

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
        completed=ROOT/'build/silicon/task009-well-fill-route-a1'
        if(completed/'result.json').exists():
            relation,closed,history=completed_route_inputs(completed)
            self.assertTrue(relation['functional_bytes_equal'])
            self.assertEqual({Path(row['path']).name for row in history},{'silicon_pen_physical.py','silicon_well_fill_route.py'})
            self.assertTrue(any(path.name=='sg13g2_stdcell.cdl'for path in closed))


if __name__=='__main__':unittest.main()
