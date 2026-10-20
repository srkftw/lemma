#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fresh mapped pen input for the reviewed native420 power-margin recipe.

This path regenerates placement, clocks, power and signal routes. It never
imports the old327 layout, guides, cell names or RC. The original margin is
420nm; the275nm M2 router representation still requires independent native
wire/via/patch checking after routing. No physical closure is implied.
"""
from collections import Counter
import json
from pathlib import Path
import re

from silicon_enclosure import require
from silicon_synth import ROOT, sha

CANDIDATE_SHA = '97b077796078558fdc84ebcb36bcd7cffc70fd2056653a1269478d250dbedded'
GRID_SHA = 'b6a3315d233f16e01a6d7a30279867964cdece162a1839b6bed3e01b735fb38e'
LIB_SHA = '7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396'
MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
SUPPLIES = {'VDD!': 'VDDlogic', 'VDDARRAY!': 'VDDARRAY', 'VSS!': 'VSS'}


def require_recipe(args):
    if not getattr(args, 'fresh_native_margin_grid', False):
        return
    require(args.fresh_core_power_grid and args.protect_sram_power_geometry and
            args.group_button_bus and args.clock_min_routing_layer == 'Metal3' and
            args.detail_route_iterations == 8 and args.host_memory_gib == 6,
            'fresh native margin requires fresh full-PG grid, full button bus, clockM3,8iterations and6GiBAS')
    forbidden = ('selected_implementation', 'routed_eco_from', 'completed_eco_route_from',
                 'completed_power_grid_route_from', 'completed_fresh_grid_route_from',
                 'completed_well_fill_route_from', 'completed_hold_decode_route_from',
                 'preserve_routed_netlist', 'vss_clock_grid_source', 'defer_global_eco',
                 'center_validation_cones', 'acceptance_launch_buffer',
                 'padded_sram_input_delay_from', 'control_launch_buffer_from',
                 'capacity_launch_buffer_from', 'slew_launch_buffer_from',
                 'decode_launch_buffer_from', 'well_fill_from', 'two_load_launch_from',
                 'hold_decode_from', 'power_margin_from', 'preferred_access_from',
                 'preferred_access_preflight_only', 'protect_sram_power_edges')
    require(not any(getattr(args, name, False) for name in forbidden),
            'fresh native margin cannot import a prior layout, guides, ECO, selection or deferred repair')


def reviewed_grid(original_grid, output):
    """Generate only the already qualified b6a source; preserve old grid bytes."""
    grid = original_grid.read_text()
    line = 'add_pdn_stripe -grid pen_core -layer Metal5 -width 2.5 -pitch 80 -offset 10 -nets {VDDlogic VDDARRAY VSS}'
    replacement = '\n'.join(
        f'add_pdn_stripe -grid pen_core -layer Metal5 -width 2.5 -pitch 80 -offset {offset} -nets {{{net}}}'
        for net, offset in [('VDDlogic', '10'), ('VDDARRAY', '36.665'), ('VSS', '65.330')])
    require(grid.count(line) == 1 and not output.exists(), 'one original grid line and unused grid output required')
    output.write_text(grid.replace(line, replacement))
    require(sha(output) == GRID_SHA, 'fresh grid is not the exact reviewed VSS-only source')


def prepare(mapping, original_grid, output):
    """Consume the standard actual producer, then emit the exact reviewed grid."""
    from silicon_power_margin import corner_proof
    receipt = mapping / 'result.json'
    result = json.loads(receipt.read_text())
    require(result['status'] == 'PASS_ISOLATED_CANDIDATE_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING'
            and result['candidate_only'] and result['candidate_source']['sha256'] == CANDIDATE_SHA,
            'fresh margin requires actual standard97b077 candidate admission')
    require(sha(mapping / 'candidate.sv') == CANDIDATE_SHA and
            sha(mapping / 'mapped.v') == result['mapping']['mapped_verilog_sha256'] and
            sha(mapping / 'mapped.json') == result['mapping']['mapped_json_sha256'],
            'fresh mapped source or emitted netlist differs')
    require(result['mapping']['cells'] == 7095 and
            result['mapping']['cell_types'][MACRO] == 3 and
            result['mapping']['cell_types']['sg13g2_dfrbpq_1'] == 811,
            'fresh mapped full-width state/macro inventory differs')
    require(all(sha(ROOT / name) == digest for name, digest in result['source_inputs'].items()),
            'standard producer current source closure differs')
    require(all(sha(mapping / 'pdk' / name) == value['sha256']
                for name, value in result['collateral'].items()), 'standard producer collateral differs')
    reviewed_grid(original_grid, output)
    return {'version': 'lemma-pen-fresh-native420-grid/1',
            'mapping_receipt': {'path': str(receipt), 'sha256': sha(receipt)},
            'candidate_RTL_sha256': CANDIDATE_SHA, 'grid_source_sha256': GRID_SHA,
            'router_representation': corner_proof(),
            'scope': 'Fresh actual mapped97b077 source; no prior layout/cell/guide/RC substitution; native420 final check remains mandatory.'}


def observations(block, liberty):
    """Actual semantic pins and physical margins; no old ABC identifiers."""
    from silicon_buffered_pins import buffer_kind
    from silicon_power_margin import pg_geometry
    from silicon_sram_input_hold import padding
    require(block.getDbUnitsPerMicron() == 1000, 'original native database units required')
    terms = {term.getName(): term for term in block.getBTerms()}
    require(len(terms) == 668 and all(name in terms for name in SUPPLIES.values()) and
            sum(term.getSigType() not in ('POWER', 'GROUND') for term in terms.values()) == 665,
            'all665 functional and3 physical power ports required')

    def constant(net, trail=()):
        require(net is not None and net.getName() not in trail, 'constant chain missing or cyclic')
        drivers = [term for term in net.getITerms() if term.getMTerm().getIoType() == 'OUTPUT']
        require(len(drivers) == 1 and not list(net.getBTerms()), 'one physical constant driver required')
        driver = drivers[0]; inst = driver.getInst(); kind = inst.getMaster().getName()
        if kind in ('sg13g2_tiehi', 'sg13g2_tielo'):
            pin, value = ('L_HI', 1) if kind == 'sg13g2_tiehi' else ('L_LO', 0)
            require(driver.getMTerm().getName() == pin, 'wrong original tie output')
            return value
        rule = buffer_kind(kind, liberty)
        require(rule is not None, 'non-buffer constant-chain driver')
        output, inversion = rule
        require(driver.getMTerm().getName() == output, 'constant buffer output differs')
        return constant(inst.findITerm('A').getNet(), (*trail, net.getName())) ^ inversion

    fixed = [('pen_sram_lane0', 120000, 100000, 'R0'),
             ('pen_sram_lane1', 120000, 350000, 'R0'),
             ('pen_sram_lane2', 120000, 600000, 'MX')]
    macro_pins = bist = delay_mask = 0
    native = Counter()
    for name, x, y, orientation in fixed:
        inst = block.findInst(name)
        require(inst is not None and inst.getMaster().getName() == MACRO and
                inst.getBBox().xMin() == x and inst.getBBox().yMin() == y and
                inst.getBBox().dx() == 784480 and inst.getBBox().dy() == 118780 and
                inst.getOrient() == orientation,
                'original physical macro placement/master differs: ' + name)
        for term in inst.getITerms():
            pin = term.getMTerm().getName(); net = term.getNet()
            require(net is not None, 'unconnected actual macro pin: ' + pin)
            if pin in SUPPLIES:
                require(net.getName() == SUPPLIES[pin], 'macro supply retargeted: ' + pin)
                macro_pins += 1
                for layer, rect in term.getGeometries():
                    native[(layer.getName(), rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax())] += 1
            elif pin.startswith('A_BIST_'):
                require(constant(net) == 0, 'original BIST tie changed: ' + pin)
                bist += 1
            elif pin.startswith('A_DLY') or pin.startswith('A_BM['):
                require(constant(net) == 1, 'original delay/mask tie changed: ' + pin)
                delay_mask += 1
    require(macro_pins == 9 and bist == 423 and delay_mask == 195,
            'complete actual macro supply/test/delay/mask inventory required')
    all_power = 0
    for inst in block.getInsts():
        for term in inst.getITerms():
            kind = term.getMTerm().getSigType()
            if kind not in ('POWER', 'GROUND'):
                continue
            pin = term.getMTerm().getName()
            expected = SUPPLIES.get(pin, 'VSS' if pin == 'VSS' else 'VDDlogic' if pin == 'VDD' else None)
            require(expected is not None and term.getNet() is not None and term.getNet().getName() == expected,
                    'actual standard/macro power pin changed')
            all_power += 1
    _, metals, _ = pg_geometry(block)
    for (net, layer, a, b, c, d), count in metals.items():
        if layer in ('Metal2', 'Metal3', 'Metal4', 'Metal5'):
            native[(layer, a, b, c, d)] += count
    expected = Counter()
    for (layer, a, b, c, d), count in native.items():
        require(0 < min(c-a, d-b) < 10000, 'native PG width outside original spacing domain')
        z = 275 if layer == 'Metal2' else 420
        expected[(layer, a-z, b-z, c+z, d+z)] += count
    actual = Counter()
    for obstruction in block.getObstructions():
        require(obstruction.isExceptPGNetsObstruction(), 'unknown non-PG-exempt obstruction')
        box = obstruction.getBBox()
        actual[(box.getTechLayer().getName(), box.xMin(), box.yMin(), box.xMax(), box.yMax())] += 1
    require(actual == expected and sum(actual.values()) == 18718,
            'actual native PG/275M2+420other obstruction relation differs')
    result = padding(block)
    result.update(macro_power_pins=macro_pins, preserved_BIST_pins=bist,
                  original_delay_mask_pins=delay_mask, all_power_terminals=all_power,
                  physical_ports=len(terms), obstructions=sum(actual.values()))
    return result


def clock_window(tech, block, native_def):
    """Original Via4/process margin and actual VSS rail, including old400nm failure."""
    from silicon_power_clearance import rectangular_clearance
    from silicon_power_margin import pg_geometry
    via = tech.findVia('Via4_YX')
    require(via is not None, 'original Via4 source required')
    boxes = {q.getTechLayer().getName(): (q.xMin(), q.yMin(), q.xMax(), q.yMax())
             for q in via.getBoxes()}
    require(boxes.get('Metal4') == (-105, -145, 105, 145) and
            boxes.get('Metal5') == (-145, -100, 145, 100), 'original Via4 changed')
    stripes, _, _ = pg_geometry(block)
    rails = [row for row in stripes if row[0:2] == ('VSS', 'Metal5') and
             row[3] == 471640 and row[2] < 426240 < row[4] and row[5]-row[3] == 2500]
    require(len(rails) == 1 and stripes[rails[0]] == 1, 'actual reviewed shifted VSS rail missing')
    top = block.findInst('pen_sram_lane1').getBBox().yMax()
    require(top == 468780, 'fixed macro clock-channel edge moved')
    lo = top+420-boxes['Metal4'][1]
    hi = rails[0][3]-420-boxes['Metal5'][3]
    matches = re.findall(r'^TRACKS Y (\d+) DO (\d+) STEP (\d+) LAYER Metal5\b', native_def, re.M)
    require(len(matches) == 1, 'one actual original Metal5 track definition required')
    start, count, pitch = map(int, matches[0])
    require(pitch == 420 and count > 0, 'original Metal5 track pitch changed')
    legal = [start+i*pitch for i in range(count) if lo <= start+i*pitch <= hi]
    require(legal == [469560, 469980, 470400, 470820], 'actual legal source420nm Via4 window differs')
    # This exact native conductor pair caused the retained old400nm failure.
    require(rectangular_clearance([424660, 469040, 426340, 469240],
                                  [34680, 469640, 995880, 472140]) == 400 and
            rectangular_clearance([424660, 469040, 426340, 469240],
                                  [34680, 471640, 995880, 474140]) >= 420,
            'original failed-gap negative or source-shift positive changed')
    return {'physical_margin_nm': 420, 'legal_actual_M5_Via4_tracks_nm': legal,
            'retained_original_gap_negative_nm': 400,
            'scope': 'Actual PG/source-track feasibility, not a chosen signal route or process DRC pass.'}


def assess(geometry, liberty, output):
    """Read back the real fresh pre-route database and reject actual negatives."""
    from silicon_acceptance_launch import snapshot
    from silicon_power_margin import load
    require(sha(liberty) == LIB_SHA, 'original standard-cell Liberty required')
    db, block = load(geometry); before = snapshot(block); text = liberty.read_text()
    result = observations(block, text); negatives = []
    result['clock_via_window'] = clock_window(db.getTech(), block, geometry.with_suffix('.def').read_text())
    macro = block.findInst('pen_sram_lane0')
    for label, pin, wrong in [('wrong_array_supply', 'VDDARRAY!', 'VDDlogic'),
                              ('wrong_BIST_constant', 'A_BIST_EN', 'VDDlogic'),
                              ('wrong_delay_constant', 'A_DLY', 'VSS')]:
        term = macro.findITerm(pin); require(term is not None, 'negative must bind an actual semantic macro pin')
        saved = term.getNet(); term.disconnect(); term.connect(block.findNet(wrong))
        try:
            observations(block, text)
        except ValueError:
            negatives.append(label)
        else:
            raise ValueError('actual semantic pin negative accepted: ' + label)
        finally:
            term.disconnect(); term.connect(saved)
    cells = [cell for cell in block.getInsts() if cell.getMaster().getHeight() == 3780]
    require(len(cells) >= 2, 'actual padded standard cells required')
    saved = (cells[0].getOrient(), tuple(cells[0].getLocation()))
    cells[0].setOrient(cells[1].getOrient()); cells[0].setLocation(*cells[1].getLocation())
    try:
        observations(block, text)
    except ValueError:
        negatives.append('actual_padding_overlap')
    else:
        raise ValueError('actual padding overlap accepted')
    finally:
        cells[0].setOrient(saved[0]); cells[0].setLocation(*saved[1])
    require(snapshot(block) == before, 'actual negative controls failed to restore geometry/terminals')
    observations(block, text)
    result.update(status='PASS_FRESH_MAPPED_NATIVE_PG_PADDING_PIN_PRECURSOR_NOT_ROUTED',
                  geometry_sha256=sha(geometry), negative_controls=negatives,
                  scope='Actual fresh native pins/PG/OBS/padding readback only; no signal native420, routing, timing, process DRC or LVS result.')
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
