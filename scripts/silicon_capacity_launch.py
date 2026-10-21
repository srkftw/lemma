#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact nominal-capacity launch precursor on the unselected104 pen layout.

This admits327 original noninverting buf8s at source-qualified padded sites.
Only declared internal nonclock/nonreset/nontristate driver outputs change;
every original sink, cell, port, PG shape and obstruction remains exact.
The37 excluded obligations and54 additional all-corner cap pins remain open.
No new wire-load, timing, process DRC or LVS claim follows from this relation.
"""
import json
import time
from pathlib import Path

from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE_SHA = '184edd0388271630c5dcb00ff4326f077ad861659870e303532b47954321f24a'
GEOMETRY_SHA = '5eb7e784ce0da5f94846df4737f27d59dfaadf58659d608a2d45d16d9c41b421'
PREPARATION_SHA = 'a8865235d81a645a1e39ce464dff1f9bb7205e86f7ab6593344738a78e9ae253'
RECEIPT_SHA = '48c7c36561d1b1897dfad0792e1402581e3f337e06522b738e34f5c728408d1f'
INVENTORY_SHA = 'b8cc944117cb273b28a9c9a88d796b90e48f184273eeebbaf390aacaf239c021'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
PRODUCER = ROOT / 'build/silicon/task009-capacity-drive-preflight-a1'


def admit(directory):
    directory = directory.resolve()
    require(directory == PRODUCER, 'exact retained327-source producer required')
    receipt, prep, inventory, geometry = (directory / name for name in
        ('result.json', 'preparation.json', 'inventory.json', 'unrouted.odb'))
    for path, digest in ((receipt, RECEIPT_SHA), (prep, PREPARATION_SHA),
                         (inventory, INVENTORY_SHA), (geometry, GEOMETRY_SHA)):
        require(sha(path) == digest, 'capacity producer bytes differ: ' + str(path))
    result = json.loads(receipt.read_text())
    require(result['status'] == 'PASS_SOURCE_BOUND_ACTUAL_CAP_INVENTORY_AND_ORIGINAL_BUFFER_PLACEMENT_PRECURSOR_NOT_TIMING'
            and result['source_seal_equal'], 'completed source-sealed finite producer required')
    for name, digest in result['source_inputs'].items():
        require(sha(Path(name)) == digest, 'finite capacity source differs: ' + name)
    require(result['commands'][1]['exit_code'] == 0 and result['commands'][3]['exit_code'] != 0,
            'executed original-model identity and inverted-buffer negative required')
    return geometry, receipt, [Path(name) for name in result['source_inputs']] + [prep, inventory]


def assess(source, geometry, lib, output, *, fixed_geometry=None):
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_buffered_pins import buffer_kind
    from silicon_sram_input_hold import padding
    require(sha(source) == SOURCE_SHA and sha(lib) == LIB_SHA,
            'exact104 source and original public Liberty required')
    prepared, _, _ = admit(PRODUCER)
    specs = json.loads((PRODUCER / 'preparation.json').read_text())['sites']
    require(len(specs) == 327 and len({s['new_cell'] for s in specs}) == 327,
            'exact327 single-driver source inventory required')
    started = time.monotonic()
    old_db, new_db = odb.dbDatabase.create(), odb.dbDatabase.create()
    odb.read_db(old_db, str(source))
    odb.read_db(new_db, str(geometry))
    old, block = old_db.getChip().getBlock(), new_db.getChip().getBlock()
    before, after = snapshot(old), snapshot(block)
    added = {row['new_cell'] for row in specs}
    expected = {key: value[0] for key, value in before[0].items()}
    expected.update({tuple(row['driver'][:2]): row['new_cell'] + '_driver' for row in specs})
    require({key: val for key, val in after[1].items() if key not in added} == before[1]
            and set(after[1]) == set(before[1]) | added,
            'old placement/master/33delay/three-control inventory changed')
    require(after[2:] == before[2:], '668 physical ports/nativePG/OBS changed')
    require(len(after[0]) == len(before[0]) + 4 * len(added), 'added terminal inventory differs')
    require(buffer_kind('sg13g2_buf_8', lib.read_text()) == ('X', 0),
            'original noninverting positive-unate buf8 function differs')

    def validate_terms():
        current = {(i.getName(), t.getMTerm().getName()):
                   t.getNet().getName() if t.getNet() else None
                   for i in block.getInsts() if i.getName() not in added for t in i.getITerms()}
        require(current == expected, 'original signal/bit/BIST/supply terminal changed')
        for row in specs:
            name = row['new_cell']
            cell = block.findInst(name)
            require(cell is not None and cell.getMaster().getName() == 'sg13g2_buf_8'
                    and tuple(cell.getLocation()) == tuple(row['xy_DBU'])
                    and cell.getOrient() == row['orientation'], 'new original buf8 site/master differs')
            for terminal, net in [('A', name + '_driver'), ('X', row['old_net']),
                                   ('VDD', 'VDDlogic'), ('VSS', 'VSS')]:
                pin = cell.findITerm(terminal)
                require(pin is not None and pin.getNet() is not None and pin.getNet().getName() == net,
                        'new launch bit/input/output/power binding differs')
            net = block.findNet(name + '_driver')
            require(not list(net.getBTerms()) and len(list(net.getITerms())) == 2,
                    'new launch input branch is not the exact two-terminal boundary')
    validate_terms()
    pad = padding(block)
    reference_db = odb.dbDatabase.create()
    odb.read_db(reference_db, str(fixed_geometry or prepared))
    require(sha(fixed_geometry or prepared) == GEOMETRY_SHA and
            snapshot(reference_db.getChip().getBlock()) == after,
            'candidate differs from exact source-qualified327 padded geometry')
    negatives = []
    for label, cell, terminal, wrong in [
        ('crossed_launch_input', specs[0]['new_cell'], 'A', 'VSS'),
        ('wrong_new_supply', specs[0]['new_cell'], 'VDD', 'VSS'),
        ('original_SRAM_bit_swap', 'pen_sram_lane0', 'A_DIN[32]',
         block.findInst('pen_sram_lane0').findITerm('A_DIN[33]').getNet().getName()),
        ('original_BIST_disconnect', 'pen_sram_lane0', 'A_BIST_DIN[32]', None)]:
        term = block.findInst(cell).findITerm(terminal)
        saved = term.getNet()
        term.disconnect()
        if wrong is not None:
            term.connect(block.findNet(wrong))
        try:
            validate_terms()
        except ValueError:
            negatives.append(label)
        else:
            raise ValueError('actual capacity negative accepted: ' + label)
        term.disconnect()
        term.connect(saved)
    validate_terms()
    output.write_text(json.dumps(dict(status='PASS_EXACT327_ORIGINAL_BUFFER_RELATION_AND_PADDING',
        scope=__doc__, source_ODB_sha256=sha(source), geometry_ODB_sha256=sha(geometry),
        finite_producer_sha256=RECEIPT_SHA, source_inventory_sha256=INVENTORY_SHA,
        added_original_buf8=327, old_cells_moved=0, old_ports=len(before[2]),
        native_PG_shapes=sum(before[3].values()), old_OBS=len(before[4]),
        original33_SRAM_delaycells_preserved=True, original3_control_buffers_preserved=True,
        expected_PG_terminals=18071, original_padding=pad, negatives=negatives,
        seconds=time.monotonic() - started), indent=2) + '\n')
