#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound three measured-slew launch buffers on native420 pen geometry.

Only the declared three driver-output nets change. Every original cell,
functional sink, physical port, native PG shape and obstruction stays exact.
No old SPEF is admitted onto changed control nets.
"""
import json
import time
from pathlib import Path
from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE_SHA = 'bed1d7890a40b0c1f9efbbb36b61b79a1df883af7da35cbf8a4a5ba1c61fe50f'
GEOMETRY_SHA = '3697bef3c5129996a8a0e96858f41c5275dbc6dc53eb485e104e8e8c88dacaef'
PREPARATION_SHA = '72785ec7dcba5cf8d513f401f7f0c477a8b038145e823cf7d05d687049aa3864'
RECEIPT_SHA = '479e13ad7414734043eaebaae393dc3cf211367b61f806167e8f6757051bc80c'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
DRIVERS = (('_08936_', 'sg13g2_nor4_2', '_03201_'),
           ('_08932_', 'sg13g2_nor4_1', '_03197_'),
           ('_06061_', 'sg13g2_inv_1', '_00983_'))


def admit(directory):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT / 'build'), 'ignored retained control geometry required')
    receipt, prep, geometry = (directory / name for name in ('result.json', 'preparation.json', 'unrouted.odb'))
    require(sha(receipt) == RECEIPT_SHA and sha(prep) == PREPARATION_SHA and
            sha(geometry) == GEOMETRY_SHA, 'exact finite-qualified three-slew geometry required')
    result = json.loads(receipt.read_text())
    require(result['status'] == 'PASS_PRIVATE_THREE_SLEW_BUF8_FUNCTION_GEOMETRY_POWER_PADDED_PRECURSOR_NOT_TIMING'
            and result['source_seal_equal'], 'completed source-sealed control geometry required')
    for name, digest in result['source_inputs'].items():
        require(sha(Path(name)) == digest, 'qualified control source differs: ' + name)
    # The original public gate functions were executed for all4^4 inputs,
    # including X/Z; their outputs are never Z. An inverted buffer rejects.
    require(result['commands'][1]['exit_code'] == 0 and result['commands'][3]['exit_code'] != 0 and
            not result['commands'][3]['timed_out'] and result['power']['all_power_terminals']==18077 and
            result['power']['macro_power_pins']==9 and result['power']['preserved_BIST_pins']==423,
            'actual original-model positive and negative execution required')
    return geometry, receipt, [Path(name) for name in result['source_inputs']] + [prep]


def assess(source, geometry, lib, output, *, fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_buffered_pins import buffer_kind
    from silicon_sram_input_hold import padding
    require(sha(source) == SOURCE_SHA and sha(lib) == LIB_SHA,
            'exact selectedzero-marker source and original public Liberty required')
    started = time.monotonic()
    old_db, new_db = odb.dbDatabase.create(), odb.dbDatabase.create()
    odb.read_db(old_db, str(source))
    odb.read_db(new_db, str(geometry))
    old_block, block = old_db.getChip().getBlock(), new_db.getChip().getBlock()
    before = snapshot(old_block)
    after = snapshot(block)
    print('Slew source/candidate full geometry read', time.monotonic() - started, flush=True)
    added = {f'task009_slew_launch_{index}' for index in range(3)}
    changes = {(name, 'Y'): f'task009_slew_launch_{index}_driver'
               for index, (name, _, _) in enumerate(DRIVERS)}

    expected = {key: value[0] for key, value in before[0].items()}
    expected.update(changes)
    require({key: val[0] for key, val in after[0].items() if key[0] not in added} == expected,
            'old functional/supply/BIST terminal changed beyond three declared outputs')
    require({key: val for key, val in after[1].items() if key not in added} == before[1] and
            set(after[1]) == set(before[1]) | added,
            'old cell/master/placement or original33 delaycells changed')
    require(after[2:] == before[2:], '668 physical ports/nativePG/OBS changed')
    require(len(after[0]) == len(before[0]) + 12, 'new cell terminal inventory differs')
    liberty = lib.read_text()
    require(buffer_kind('sg13g2_buf_8', liberty) == ('X', 0), 'original buf8 function differs')

    def validate_declared_pins():
        # Only these ITerms mutate during the actual negative controls below.
        # The full unchanged geometry/terminal relation is checked once above;
        # pin-only negatives cannot alter native metal, masters or placements.
        for index, (driver, kind, oldnet) in enumerate(DRIVERS):
            old = old_block.findInst(driver)
            require(old.getMaster().getName() == kind and old.findITerm('Y').getNet().getName() == oldnet,
                    'original driver identity differs')
            name = f'task009_slew_launch_{index}'
            cell = block.findInst(name)
            require(cell is not None and cell.getMaster().getName() == 'sg13g2_buf_8' and
                    block.findInst(driver).findITerm('Y').getNet().getName() == changes[(driver, 'Y')],
                    'three original noninverting buf8 only')
            for terminal, net in [('A', changes[(driver, 'Y')]), ('X', oldnet),
                                   ('VDD', 'VDDlogic'), ('VSS', 'VSS')]:
                pin = cell.findITerm(terminal)
                require(pin is not None and pin.getNet() is not None and pin.getNet().getName() == net,
                        'control launch input/output/power changed')
    validate_declared_pins()
    result = padding(block)
    if fixed_geometry is not None:
        ref_db = odb.dbDatabase.create()
        odb.read_db(ref_db, str(fixed_geometry))
        require(sha(fixed_geometry) == GEOMETRY_SHA and
                snapshot(ref_db.getChip().getBlock()) == after,
                'routing changed the qualified three-slew physical geometry')
    negatives = []
    cell = block.findInst('task009_slew_launch_0')
    for label, terminal, wrong in [('crossed_input', 'A', 'sample_ready'),
                                    ('wrong_new_supply', 'VDD', 'VSS')]:
        pin, saved = cell.findITerm(terminal), cell.findITerm(terminal).getNet()
        pin.disconnect()
        pin.connect(block.findNet(wrong))
        try:
            validate_declared_pins()
        except ValueError:
            negatives.append(label)
        else:
            raise ValueError('control launch negative accepted: ' + label)
        pin.disconnect()
        pin.connect(saved)
        validate_declared_pins()
    print('Slew full geometry and consequential pin negatives checked', time.monotonic() - started, flush=True)
    result.update(status='PASS_EXACT_THREE_SLEW_LAUNCH_BUFFER_RELATION_AND_ORIGINAL_PADDING',
        scope='Finite original gate/buffer function and physical endpoint relation only; no timing/process/fullLVS qualification',
        source_ODB_sha256=sha(source), geometry_ODB_sha256=sha(geometry),
        fixed_geometry_ODB_sha256=sha(fixed_geometry) if fixed_geometry else None,
        added_original_buf8=3, old_cells_moved=0, old_ports=len(before[2]),
        native_PG_shapes=sum(before[3].values()), old_OBS=len(before[4]),
        original33_SRAM_delaycells_preserved=True, source_bound_finite_four_state_fixture=RECEIPT_SHA,
        negatives=negatives, assessment_seconds=time.monotonic() - started)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result


def require_recipe(args):
    if not getattr(args,'slew_launch_buffer_from',None):return
    require(args.routed_eco_from and args.clock_min_routing_layer=='Metal3' and
            args.detail_route_iterations==8 and args.host_memory_gib==6 and
            not any(getattr(args,name,False) for name in
                ('selected_implementation','acceptance_launch_buffer','padded_sram_input_delay_from',
                 'control_launch_buffer_from','capacity_launch_buffer_from','power_margin_from',
                 'preferred_access_from','preferred_access_preflight_only','preserve_routed_netlist',
                 'fresh_core_power_grid','vss_clock_grid_source','protect_sram_power_edges',
                 'protect_sram_power_geometry','completed_eco_route_from','completed_power_grid_route_from',
                 'completed_fresh_grid_route_from','defer_global_eco','center_validation_cones','group_button_bus')),
            'three-slew launches require exactzero-route source/native420/full8/clockM3/6GiB, no other recipe')
