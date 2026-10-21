#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact padded SRAM input-delay geometry; no timing or process qualification.

The admitted predecessor is retained completed geometry. Reusing it never reruns
legalization or resizer repair, and never imports an old SPEF onto changed nets.
"""
import json
from collections import defaultdict
from pathlib import Path

from silicon_enclosure import require
from silicon_synth import ROOT, sha

SOURCE_ODB_SHA = 'e7eb9ca00cfc2879b66c4a6096f43e68d9f8bcd563c2b3b37a9dd3252adfad0c'
GEOMETRY_ODB_SHA = '1c1e617d8c4d64d63182926f37d40fb8ecac420489e5e1668fefe0603e195978'
ASSESSMENT_PATH = 'build/silicon/task009-launch-full-padding-completed-a1/result.json'
ASSESSMENT_SHA = 'b50011db4e5eb9a16c15ff892b28188a8f55e909e41d02044f7cdeabb60c06a9'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
MASTER = 'sg13g2_dlygate4sd3_1'
# Exact completed all-nine-case inventory: positive setup margins at these31
# SRAM inputs only. All147 failing control endpoints remain unmodified.
ENDPOINTS = tuple(sorted([f'pen_sram_lane0/A_DIN[{bit}]' for bit in
                         list(range(17)) + [51, 52] + list(range(54, 64))] +
                        ['pen_sram_lane1/A_DIN[25]', 'pen_sram_lane1/A_DIN[28]']))


def endpoint_cells():
    return {endpoint: [f'task009_hold_{index}_{stage}' for stage in range(
        2 if endpoint in ('pen_sram_lane0/A_DIN[1]', 'pen_sram_lane0/A_DIN[2]') else 1)]
        for index, endpoint in enumerate(ENDPOINTS)}


def admit(directory):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT / 'build'), 'ignored retained geometry required')
    assessment = ROOT / ASSESSMENT_PATH
    require(sha(assessment) == ASSESSMENT_SHA, 'completed padding assessment differs')
    result = json.loads(assessment.read_text())
    require(result['status'] == 'PASS_COMPLETED_FULL_PADDING_33DELAYCELL_SOURCE_GEOMETRY_POWER_BOOLEAN_ASSESSMENT_NOT_ROUTED'
            and result['source_seal_equal'], 'completed source-sealed geometry assessment required')
    geometry = directory / 'legalized.odb'
    require(sha(geometry) == GEOMETRY_ODB_SHA, 'exact completed padded33-cell geometry required')
    # These are the actual inputs of the independently completed assessment;
    # the first producer's11.197s observer failure remains a separate receipt.
    for name, digest in result['source_inputs'].items():
        require(sha(Path(name)) == digest, 'completed geometry source differs: ' + name)
    require(any(Path(name).resolve() == geometry for name in result['source_inputs']),
            'geometry not bound by completed assessment')
    return geometry, assessment, [Path(name) for name in result['source_inputs']]


def padding(block):
    """Original global one-site L/R constraint on actual row-oriented cells."""
    rows = defaultdict(list)
    core = block.getCoreArea()
    for inst in block.getInsts():
        if inst.getMaster().getHeight() != 3780:
            continue
        box = inst.getBBox()
        require(box.xMin() >= core.xMin() and box.xMax() <= core.xMax() and
                box.yMin() >= core.yMin() and box.yMax() <= core.yMax(), 'stdcell outside core')
        rows[box.yMin()].append((box.xMin(), box.xMax(), inst.getName()))
    bad = []
    for y, cells in rows.items():
        cells.sort()
        for left, right in zip(cells, cells[1:]):
            gap = right[0] - left[1]
            if gap < 960:
                bad.append((left[2], right[2], y, gap))
    require(not bad, 'original1/1padding violated: ' + repr(bad[:5]))
    return {'rows': len(rows), 'stdcells': sum(map(len, rows.values())),
            'violating_pairs': 0, 'required_gap_DBU': 960}


def assess(source, geometry, lib, output, *, fixed_geometry=None):
    """Check actual endpoint chains, native PG, fixed geometry and padding.

    fixed_geometry enforces every pre-route instance/terminal/port/PG/OBS on
    the final routed database. Only signal wire shapes may change in routing.
    """
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_buffered_pins import assess as boolean_assess, buffer_kind

    require(sha(source) == SOURCE_ODB_SHA and sha(lib) == LIB_SHA,
            'original selected115 layout and original public Liberty required')
    old_db, new_db = odb.dbDatabase.create(), odb.dbDatabase.create()
    odb.read_db(old_db, str(source))
    odb.read_db(new_db, str(geometry))
    old_block, block = old_db.getChip().getBlock(), new_db.getChip().getBlock()
    before, after = snapshot(old_block), snapshot(block)
    chains = endpoint_cells()
    added = {name for names in chains.values() for name in names}
    require(len(chains) == 31 and len(added) == 33, 'exact input-delay inventory required')
    expected = {key: value[0] for key, value in before[0].items()}
    for endpoint, names in chains.items():
        inst, pin = endpoint.split('/')
        prior = expected[(inst, pin)]
        expected[(inst, pin)] = names[-1] + '_out'
        for name in names:
            cell = block.findInst(name)
            require(cell is not None and cell.getMaster().getName() == MASTER,
                    'wrong/missing input-delay master: ' + name)
            require(buffer_kind(MASTER, lib.read_text()) == ('X', 0), 'original delay not noninverting')
            for terminal, net in [('A', prior), ('X', name + '_out'),
                                  ('VDD', 'VDDlogic'), ('VSS', 'VSS')]:
                iterm = cell.findITerm(terminal)
                require(iterm is not None and iterm.getNet() is not None and
                        iterm.getNet().getName() == net, 'input-delay bit/chain/supply changed: ' + name)
            prior = name + '_out'
    require({key: val[0] for key, val in after[0].items() if key[0] not in added} == expected,
            'an old signal, power or BIST terminal changed beyond31 declared SRAM inputs')
    require(set(after[1]) == set(before[1]) | added and
            all(after[1][name][0] == before[1][name][0] for name in before[1]),
            'old cell/master or added33-cell inventory changed')
    require(after[2:] == before[2:], '668 physical ports, native PG shapes or OBS changed')
    fixed = [inst.getName() for inst in old_block.getInsts() if inst.isFixed()]
    require(all(after[1][name] == before[1][name] for name in fixed), 'fixed macro/cell moved')
    if fixed_geometry is not None:
        reference = odb.dbDatabase.create()
        odb.read_db(reference, str(fixed_geometry))
        require(sha(fixed_geometry) == GEOMETRY_ODB_SHA and
                snapshot(reference.getChip().getBlock()) == after,
                'routing moved or reconnected the admitted padded geometry')
    result = padding(block)
    launch, nand = block.findInst('task009_accept_launch').getBBox(), block.findInst('_08961_').getBBox()
    require(nand.yMin() == launch.yMin() and launch.xMin() - nand.xMax() == 960,
            'actual NAND-to-launch original padding gap differs')
    # Consequential in-memory negative; restore before endpoint qualification.
    cell = block.findInst('task009_accept_launch')
    saved = (cell.getOrient(), tuple(cell.getLocation()))
    other = block.findInst('_08961_')
    cell.setOrient(other.getOrient())
    cell.setLocation(*other.getLocation())
    try:
        padding(block)
    except ValueError:
        pass
    else:
        raise ValueError('actual overlapping padding negative was accepted')
    cell.setOrient(saved[0])
    cell.setLocation(*saved[1])
    padding(block)
    boolean_path = output.with_name(output.stem + '-boolean.json')
    boolean_assess(source, geometry, lib, boolean_path)
    result.update(status='PASS_EXACT_PADDED33_INPUT_DELAY_GEOMETRY_BOOLEAN_POWER_RELATION',
        scope='Geometry/functional endpoint relation only; no process DRC, timing, fabrication or memory closure',
        source_ODB_sha256=sha(source), geometry_ODB_sha256=sha(geometry),
        fixed_geometry_ODB_sha256=sha(fixed_geometry) if fixed_geometry else None,
        endpoint_count=31, added_cells=33, fixed_instances=len(fixed),
        old_ports=len(before[2]), old_PG_shapes=sum(before[3].values()), old_OBS=len(before[4]),
        old_cells_moved=sum(before[1][name] != after[1][name] for name in before[1]),
        NAND_launch_gap_DBU=launch.xMin()-nand.xMax(),
        unresolved_control_endpoints=147,
        actual_padding_negative='REJECTED',
        actual_bit_supply_BIST_port_negatives=json.loads(boolean_path.read_text())['negative_cases'])
    output.write_text(json.dumps(result, indent=2) + '\n')
    return result
