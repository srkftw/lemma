#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit the exact actual327 conservative-margin/VSS-grid predecessor."""
import json
from pathlib import Path

from silicon_enclosure import require
from silicon_synth import ROOT, sha

PILOT = ROOT/'build/silicon/task009-327-native-margin-pilot-a1'
RECEIPT_SHA = 'f704c8f54ffd0bd59f87a79c1c3c8e30d733fe5cf3946a8f18377f5bb77ca96e'
GEOMETRY_SHA = '19bf987a14cb082f160a6ed9f864f082263c7f98cbdec66602e481acc7f170a8'
BINDING_SHA = 'c69b2d2174dcf2112904f305729bb968dbe574cad4b7df5861a81751053aa117'


def admit(directory):
    require(Path(directory).resolve()==PILOT,'exact actual327 new-grid producer required')
    receipt=PILOT/'result.json';require(sha(receipt)==RECEIPT_SHA,'new-grid receipt differs')
    r=json.loads(receipt.read_text())
    require(r['status']=='PASS_ACTUAL327_PG_AND_M2_ROUTING_REPRESENTATION_PREDECESSOR_NO_ROUTE'and r['source_seal_equal']and r['within_original_budget'],'completed new-grid source seal required')
    require(sha(PILOT/'routed.odb')==GEOMETRY_SHA,'actual new-grid geometry differs')
    binding=PILOT/'completed-input-binding.json';require(sha(binding)==BINDING_SHA,'separate completed helper binding differs')
    bound=json.loads(binding.read_text())
    require(bound['original_receipt_sha256']==RECEIPT_SHA and bound['status']=='ASSESSED_OMITTED_UNCHANGED_GIT_HELPERS_SEPARATELY_NOT_ORIGINAL_COMPLETE_INVENTORY','original input omission must stay explicit')
    paths=[]
    for path,digest in r['source_inputs'].items():
        actual=Path(bound['original_producer_source']['path'])if path==bound['original_producer_source']['original_input_path']else Path(path)
        require(sha(actual)==digest,'new-grid pilot input differs: '+path);paths.append(actual)
    for path,digest in bound['source_inputs'].items():require(sha(Path(path))==digest,'completed helper source differs: '+path)
    require(r['power_grid']['all_power_terminals']==18071 and r['geometry']['positive_rails_exact']and r['geometry']['VSS_via_relation_exact'],'real327 power relation required')
    require(sha(PILOT/'routed.def')==r['original_via_rule_subset']['routed_def_sha256']and
            json.loads((PILOT/'geometry.json').read_text())==r['geometry']and
            json.loads((PILOT/'power-grid-after-grid.json').read_text())==r['power_grid'], 'completed output geometry/PG reports differ')
    return PILOT/'routed.odb',receipt,paths+[binding]+[Path(p)for p in bound['source_inputs']]+[PILOT/n for n in ['geometry.json','routed.def','power-grid-after-grid.json']]


def require_recipe(args, *, selected_binding=False):
    if not getattr(args,'power_margin_from',None):return
    require(args.capacity_launch_buffer_from and args.routed_eco_from and args.clock_min_routing_layer=='Metal3'and args.detail_route_iterations==8 and args.host_memory_gib==6 and
            (not args.selected_implementation or selected_binding) and
            not(args.preferred_access_from or args.preferred_access_preflight_only),
            'new native420 margin requires exact327 clockM3/full8/default6GiB and fresh GRT/PA')


def bind_selected(args, selected):
    """Bind the selected implementation to the measured, complete recipe.

    Selection changes metadata, never the identity of an earlier route or
    runtime producer. Every retained preparation remains independently pinned.
    """
    require(selected['version']=='lemma-pen-sg13g2-native-margin-grid/1',
            'unknown selected native-margin implementation')
    expected=['--routed-eco-from','build/silicon/task009-three-control-launch-route-a1',
              '--capacity-launch-buffer-from','build/silicon/task009-capacity-drive-preflight-a1',
              '--clock-min-routing-layer','Metal3','--detail-route-iterations','8',
              '--power-margin-from',str(PILOT.relative_to(ROOT))]
    require(selected['launch']['flags']==expected,'selected native-margin recipe differs')
    require(args.selected_implementation and not any(getattr(args,name,False) for name in
            ('acceptance_launch_buffer','padded_sram_input_delay_from','control_launch_buffer_from',
             'preserve_routed_netlist','fresh_core_power_grid','vss_clock_grid_source',
             'protect_sram_power_edges','protect_sram_power_geometry','completed_eco_route_from',
             'completed_power_grid_route_from','completed_fresh_grid_route_from',
             'defer_global_eco','center_validation_cones','group_button_bus',
             'preferred_access_from','preferred_access_preflight_only')),
            'selected native margin cannot combine another implementation recipe')
    for name,path in [('routed_eco_from',ROOT/expected[1]),
                      ('capacity_launch_buffer_from',ROOT/expected[3]),('power_margin_from',PILOT)]:
        value=getattr(args,name,None)
        require(value is None or Path(value).resolve()==path,'selected native-margin predecessor differs: '+name)
        setattr(args,name,path)
    predecessor=selected['launch']['predecessor']
    require(predecessor['path']==expected[1] and
            sha(args.routed_eco_from/'result.json')==predecessor['receipt_sha256'] and
            sha(args.routed_eco_from/'routed.odb')==predecessor['routed_odb_sha256'],
            'selected native-margin powered predecessor differs')
    for entry in selected['launch']['sources']:
        require(sha(ROOT/entry['path'])==entry['sha256'],'selected native-margin source differs: '+entry['path'])
    geometry,receipt,_=admit(PILOT)
    require(selected['launch']['prepared_geometry']=={'path':str(geometry.relative_to(ROOT)),
            'sha256':sha(geometry)} and selected['launch']['preparation_receipt']=={
            'path':str(receipt.relative_to(ROOT)),'sha256':sha(receipt)},
            'selected native-margin preparation differs')
    args.clock_min_routing_layer='Metal3';args.detail_route_iterations=8;args.core_power_grid=True
    require_recipe(args,selected_binding=True)


def assess(source,geometry,lib,output,*,fixed_geometry=None):
    from silicon_acceptance_launch import snapshot
    from silicon_capacity_launch import SOURCE_SHA,LIB_SHA
    from silicon_power_margin import load
    from silicon_sram_input_hold import padding
    require(sha(source)==SOURCE_SHA and sha(lib)==LIB_SHA,'original actual104 source/Liberty required')
    prepared,receipt,_=admit(PILOT)
    require(fixed_geometry is None or Path(fixed_geometry)==prepared,'exact new-grid placement required')
    old_db,before=load(prepared);new_db,after=load(geometry)
    require(snapshot(before)==snapshot(after),'route changed a cell/terminal/port/nativePG/OBS from admitted new-grid geometry')
    result=padding(after)
    result.update(status='PASS_EXACT_ACTUAL327_NEW_GRID_GEOMETRY_PRESERVED_NOT_TIMING',source_predecessor=str(receipt),
                  prepared_ODB_sha256=GEOMETRY_SHA,actual_ODB_sha256=sha(geometry),
                  scope='Pilot proves original327 logic/positive rails/source-derived VSS shift; actual route must retain this exact geometry. Native wire420nm guard is separate and mandatory.')
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
