#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound three original-Lib control launch buffers on padded pen geometry.

Only the declared three driver-output nets change. Every original cell,
functional sink, physical port, native PG shape and obstruction stays exact.
No old SPEF is admitted onto changed control nets.
"""
import json
import time
from pathlib import Path
from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE_SHA = '8204bdf8b53c877e2607c7bca3f4f8f6ee64a9d88c05f9f77c4e30b73a0b8c19'
GEOMETRY_SHA = 'bf1e40834d01a528b9a059261c2bbd10379723dc4264fd467e82883649497eb5'
PREPARATION_SHA = '31ed54f1b0099e9a34a02b27c0c9ec792a6540b7777f9896ec7ba58c2a64d97b'
RECEIPT_SHA = '5500a42f9854e6f537f629cacd87a974dd7d2e4bdabedfe185b3dea7112d51bb'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
DRIVERS = (('_06985_', 'sg13g2_a22oi_1', '_01836_'),
           ('_06987_', 'sg13g2_nor3_2', 'sample_ready'),
           ('_08592_', 'sg13g2_nand3_1', '_02989_'))


def admit(directory):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT / 'build'), 'ignored retained control geometry required')
    receipt, prep, geometry = (directory / name for name in ('result.json', 'preparation.json', 'unrouted.odb'))
    require(sha(receipt) == RECEIPT_SHA and sha(prep) == PREPARATION_SHA and
            sha(geometry) == GEOMETRY_SHA, 'exact finite-qualified three-control geometry required')
    result = json.loads(receipt.read_text())
    require(result['status'] == 'PASS_PRIVATE_THREE_BUF8_FUNCTION_GEOMETRY_POWER_PADDED_PRECURSOR_NOT_TIMING'
            and result['source_seal_equal'], 'completed source-sealed control geometry required')
    for name, digest in result['source_inputs'].items():
        require(sha(Path(name)) == digest, 'qualified control source differs: ' + name)
    # The original public gate functions were executed for all4^4 inputs,
    # including X/Z; their outputs are never Z. An inverted buffer rejects.
    require(result['commands'][1]['exit_code'] == 0 and result['commands'][3]['exit_code'] != 0,
            'actual original-model positive and negative execution required')
    return geometry, receipt, [Path(name) for name in result['source_inputs']] + [prep]


def assess(source, geometry, lib, output, *, fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_buffered_pins import buffer_kind
    from silicon_sram_input_hold import padding
    require(sha(source) == SOURCE_SHA and sha(lib) == LIB_SHA,
            'exact padded30 source and original public Liberty required')
    started = time.monotonic()
    old_db, new_db = odb.dbDatabase.create(), odb.dbDatabase.create()
    odb.read_db(old_db, str(source))
    odb.read_db(new_db, str(geometry))
    old_block, block = old_db.getChip().getBlock(), new_db.getChip().getBlock()
    before = snapshot(old_block)
    after = snapshot(block)
    print('Control source/candidate full geometry read', time.monotonic() - started, flush=True)
    added = {f'task009_control_launch_{index}' for index in range(3)}
    changes = {(name, 'Y'): f'task009_control_launch_{index}_driver'
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
            name = f'task009_control_launch_{index}'
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
                'routing changed the qualified three-control physical geometry')
    negatives = []
    cell = block.findInst('task009_control_launch_0')
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
    print('Control full geometry and consequential pin negatives checked', time.monotonic() - started, flush=True)
    result.update(status='PASS_EXACT_THREE_CONTROL_LAUNCH_BUFFER_RELATION_AND_ORIGINAL_PADDING',
        scope='Finite original gate/buffer function and physical endpoint relation only; no timing/process/fullLVS qualification',
        source_ODB_sha256=sha(source), geometry_ODB_sha256=sha(geometry),
        fixed_geometry_ODB_sha256=sha(fixed_geometry) if fixed_geometry else None,
        added_original_buf8=3, old_cells_moved=0, old_ports=len(before[2]),
        native_PG_shapes=sum(before[3].values()), old_OBS=len(before[4]),
        original33_SRAM_delaycells_preserved=True, source_bound_finite_four_state_fixture=RECEIPT_SHA,
        negatives=negatives, assessment_seconds=time.monotonic() - started)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result
