#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact original-spacer/32-site well repair consumed by fresh pen routing.

This is a physical-only successor to selected0.6. The qualified NWell table
does not waive the inherited conservative Metal1 finding or full process/LVS.
Signal/clock routes and all extracted timing must be produced afresh.
"""
import json
import time
from collections import defaultdict
from pathlib import Path
from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE_SHA = '43ffc744714d5f216227035ffa4eca2e77b87f27b61b4f39fa6296a4091f7852'
GEOMETRY_SHA = 'c8516006ab3866f70b94526980ac4e1ec4c417411491cfcedd72b40bc0dcef4b'
INSERTION_SHA = '74a45045a992c547b811db021b8944fa1455bf3c12a1882b8509e99825ef9451'
GDS_SHA = '4918f653b3305a4a522e0810912c0e24a7b18e7b38d5a587b7205387928d0974'
NWELL_SHA = '540c530ad83e0032ae646071a798f279924d01b5b2865e496cf5003412f16698'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'


def admit(directory):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT/'build'), 'retained actual spacer producer required')
    receipt = directory/'result.json'
    geometry = directory/'candidate/filled.odb'
    require(sha(receipt) == INSERTION_SHA and sha(geometry) == GEOMETRY_SHA,
            'exact completed32-move/spacer insertion required')
    result = json.loads(receipt.read_text())
    require(result['status'] == 'PASS_SOURCE_BOUND_ORIGINAL_ALLROW_FILLER_INSERTION_AND_SIGNALS_NOT_PROCESS_DRC'
            and result['source_seal_equal'] and not result['resource_errors'] and result['original_whole_deadline_met'],
            'actual bounded native insertion did not finish')
    inputs = [Path(name) for name in result['source_inputs']]
    require(all(sha(path) == result['source_inputs'][str(path)] for path in inputs), 'insertion inputs differ')
    gds_dir = ROOT/'build/silicon/task009-repaired-spacer-gds-a1'
    nwell_dir = ROOT/'build/silicon/task009-repaired32-original-deep-nwell-a1'
    for path, digest in ((gds_dir/'result.json', GDS_SHA), (nwell_dir/'result.json', NWELL_SHA)):
        require(sha(path) == digest, 'original-GDS/NWell producer differs')
        observed = json.loads(path.read_text())
        require(observed['source_seal_equal'] and not observed['resource_errors'] and
                observed['original_whole_deadline_met'] and observed['owned_observed_PIDs_absent'],
                'source/resource/deadline/owned closure differs')
        for name, value in observed['source_inputs'].items():
            require(sha(Path(name)) == value, 'physical predecessor input differs: '+name)
            inputs.append(Path(name))
        inputs.append(path)
    require_predecessor_relations(json.loads((gds_dir/'result.json').read_text()),
                                 json.loads((nwell_dir/'result.json').read_text()))
    return geometry, receipt, list(dict.fromkeys(inputs))+[directory/'row-plan.json', directory/'candidate/filled.def']


def require_predecessor_relations(gds,nwell):
    # Admit only zero newly introduced metal/short area while preserving the
    # inherited overall conservative Metal1 failure as a failure.
    rows=gds['geometry']['new_filler_Metal1_rule_subset']
    require(gds['status']=='FAIL' and gds['geometry']['status']=='FAIL_FILLER_GAP_OR_METAL_SUBSET' and
            len(rows)==2 and {row['net']for row in rows}=={'VDDlogic','VSS'} and
            all(type(row[key])is int and row[key]==0 for row in rows for key in
                ('newly_introduced_clearance_area_nm2','positive_area_conductor_intersection_nm2',
                 'opposite_native_supply_conflict_area_nm2')),
            'new spacer metal clearance failed or inherited failure was relabeled')
    require(nwell['status']=='PASS_SCOPED_ORIGINAL_NWELL_TABLE_ONLY_NOT_FULL_DRC' and
            len(nwell['results'])==1 and type(nwell['results'][0]['total'])is int and
            nwell['results'][0]['total']==0 and nwell['results'][0]['category_counts']=={},
            'original full NWell table did not complete without findings')


def assess(source, geometry, lib, output, *, fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_filler_source import signal_wire_identity
    require(sha(source) == SOURCE_SHA and sha(lib) == LIB_SHA, 'exact source and original timing library required')
    started = time.monotonic()
    directory = ROOT/'build/silicon/task009-repaired-spacer-insertion-a1'
    plan = json.loads((directory/'row-plan.json').read_text())
    move_path = ROOT/'build/silicon/task009-macro-well-placement-a1/row-plan.json'
    require(sha(directory/'row-plan.json') == '993b940511465d3fb1c2f8af1266c8abc97b432d5eb7ceebf6e72e8fdb4dcd5d'
            and sha(move_path) == 'eacc87505e6baf3a8de4baac059c10bcb0fc6c60d5fac4ac7d7fc94b160f0b00',
            'literal spacer/site move plans required')
    shifts = {row['name']: row['delta_x_nm'] for row in json.loads(move_path.read_text())['moves']}
    old_db, db = odb.dbDatabase.create(), odb.dbDatabase.create()
    odb.read_db(old_db, str(source)); odb.read_db(db, str(geometry))
    before = snapshot(old_db.getChip().getBlock()); block = db.getChip().getBlock(); after = snapshot(block)
    added = {row['name']: row for row in plan['fillers']}
    expected_cells = {name: (master, orient, (loc[0]+shifts.get(name,0), loc[1]))
                      for name,(master,orient,loc) in before[1].items()}
    expected_terms = {key: (net, [(layer,a+shifts.get(key[0],0),b,c+shifts.get(key[0],0),d)
                                  for layer,a,b,c,d in boxes])
                      for key,(net,boxes) in before[0].items()}
    def validate():
        current = snapshot(block)
        require({name: value for name,value in current[1].items() if name not in added} == expected_cells and
                set(current[1]) == set(expected_cells)|set(added) and
                {key: value for key,value in current[0].items() if key[0] not in added} == expected_terms and
                current[2:] == before[2:] and len(current[0]) == len(before[0])+2*len(added),
                'functional/net/BIST/power/master/macro/port/PG/OBS changed beyond declared moves and physical spacers')
        rows = defaultdict(list)
        for name in expected_cells:
            cell = block.findInst(name)
            if cell.getMaster().getType() == 'BLOCK': continue
            box = cell.getBBox(); rows[box.yMin()].append((box.xMin(),box.xMax(),name))
        require(sum(map(len,rows.values())) == 9034, 'functional padding inventory changed')
        require(all(right[0]-left[1] >= 960 for cells in rows.values()
                    for left,right in zip(sorted(cells),sorted(cells)[1:])), 'original functional960nm padding violated')
        for name,record in added.items():
            cell = block.findInst(name)
            require(cell.getMaster().getType() == 'CORE_SPACER' and cell.getMaster().getName() == record['master'] and
                    list(cell.getLocation()) == record['location'] and cell.getOrient() == record['orientation'] and
                    {pin.getMTerm().getName(): pin.getNet().getName() if pin.getNet() else None for pin in cell.getITerms()}
                    == {'VDD':'VDDlogic','VSS':'VSS'}, 'original physical-only spacer changed')
    validate()
    if fixed_geometry is not None:
        require(sha(fixed_geometry) == GEOMETRY_SHA, 'exact physical precursor required')
        reference = odb.dbDatabase.create(); odb.read_db(reference, str(fixed_geometry))
        require(snapshot(reference.getChip().getBlock()) == after, 'routing changed qualified endpoint geometry')
    else:
        require(sha(geometry) == GEOMETRY_SHA and not signal_wire_identity(block), 'preparation must be exact and completely unrouted')
    pin = block.findInst(next(iter(added))).findITerm('VDD'); saved = pin.getNet()
    pin.connect(block.findNet('VSS'))
    try: validate()
    except ValueError: pass
    else: raise ValueError('actual new spacer wrong-supply negative admitted')
    pin.connect(saved); validate()
    moved=block.findInst(next(iter(shifts)));location=moved.getLocation()
    moved.setLocation(location[0]+480,location[1])
    try: validate()
    except ValueError: pass
    else: raise ValueError('actual moved functional-cell wrong site admitted')
    moved.setLocation(*location);validate()
    pin=next(pin for pin in moved.getITerms()if pin.getSigType()not in('POWER','GROUND')and pin.getNet()is not None)
    saved=pin.getNet();wrong=block.findNet('rdata[0]'if saved.getName()!='rdata[0]'else'rdata[1]')
    require(wrong is not None,'literal consequential signal negative net')
    pin.connect(wrong)
    try:validate()
    except ValueError:pass
    else:raise ValueError('actual old functional terminal retarget admitted')
    pin.connect(saved);validate()
    require(snapshot(block) == after, 'negative did not restore actual geometry')
    result = {'status':'PASS_EXACT32_MOVES_ORIGINAL_SPACERS_FUNCTIONAL_PADDING_AND_PG_RELATION_NOT_PROCESS_LVS',
        'source_ODB_sha256':sha(source),'geometry_ODB_sha256':sha(geometry),'fixed_geometry_ODB_sha256':sha(fixed_geometry)if fixed_geometry else None,
        'old_functional_and_macro_instances':9037,'functional_site_moves':32,'original_spacers':40247,
        'functional_padding_nm':960,'physical_spacer_padding_scope':'Only source-qualified physical CORE_SPACERs fill functional padding sites; all9034functional cells retain960nm separation',
        'original33_SRAM_delaycells_preserved':True,'ports':len(after[2]),'native_PG_shapes':sum(after[3].values()),
        'OBS':len(after[4]),'negative_cases':['actual_new_spacer_wrong_supply','actual_moved_functional_wrong_site','actual_old_functional_retarget'],'assessment_seconds':time.monotonic()-started,
        'remaining':'Inherited conservativeMetal1finding; fullprocess/LVS, freshsignal/clockroute andall3RC/9timingcorners remain separate'}
    output.write_text(json.dumps(result,indent=2)+'\n')
    return result


def require_recipe(args):
    if not getattr(args,'well_fill_from',None): return
    require(args.routed_eco_from and args.clock_min_routing_layer == 'Metal3' and args.detail_route_iterations == 8 and
            args.host_memory_gib == 6 and not args.selected_implementation and
            not any(getattr(args,name,False) for name in ('decode_launch_buffer_from','slew_launch_buffer_from',
                'acceptance_launch_buffer','padded_sram_input_delay_from','control_launch_buffer_from',
                'capacity_launch_buffer_from','power_margin_from','preferred_access_from','preferred_access_preflight_only',
                'preserve_routed_netlist','fresh_core_power_grid','vss_clock_grid_source','protect_sram_power_edges',
                'protect_sram_power_geometry','completed_eco_route_from','completed_power_grid_route_from',
                'completed_fresh_grid_route_from','defer_global_eco','center_validation_cones','group_button_bus')),
            'well/spacer successor requires exact0.6 predecessor/10ns/full8/clockM3/6GiB and fresh routing only')
