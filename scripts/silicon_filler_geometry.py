#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Original all-row spacer GDS/source relation; no full process/LVS claim.

Run under the bounded pinned KLayout owner, -b -r this-file -rd config_path=.
The actual filled DEF must come from the native source-preserving insertion.
"""
from collections import Counter
import gc
import json
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silicon_gds_geometry import sha, cardinal_angle, fingerprint, layer_mapping
from silicon_geometry_export import require


def report_gaps(path):
    root = ET.parse(path).getroot()
    require(root.tag == 'report-database' and root.findtext('top-cell') == 'lemma_pen', 'actual partial process top')
    result = []
    for item in root.findall('./items/item'):
        if item.findtext('category', '').strip("'") != 'NW.b': continue
        text = item.findtext('./values/value')
        values = [Decimal(value)*1000 for value in re.findall(r'-?\d+(?:\.\d+)?', text)]
        require(len(values) == 8 and all(value == int(value) for value in values) and
                values[0] == values[2] and values[4] == values[6], 'actual vertical native NW.b edge pair')
        values = list(map(int, values)); left, right = sorted((values[0], values[4]))
        lower = max(min(values[1:4:2]), min(values[5:8:2])); upper = min(max(values[1:4:2]), max(values[5:8:2]))
        require(left < right and lower <= upper, 'original vertical overlapping/tangent NW.b edges')
        # Twelve real original edge pairs meet at a common y coordinate. A
        # conservative one-native-DBU band on both sides requires actual new
        # well material, rather than silently accepting an empty rectangle.
        # This is a witness-coverage subset; original rule execution is separate.
        result.append((text, (left, lower if lower < upper else lower-1,
                             right, upper if lower < upper else upper+1)))
    require(len(result) == 3717, 'exact retained partial NW.b scope required')
    return result


def routed_regions(layout, top, masters, keys):
    """Same public original-map interpretation as the native mask relation."""
    import pya
    result = {key: pya.Region() for key in keys}
    shapes = 0
    def visit(cell, transform):
        nonlocal shapes
        for layer in layout.layer_indexes():
            info = layout.get_info(layer); key = info.layer, info.datatype
            for shape in cell.shapes(layer).each():
                if shape.is_text(): continue
                if key not in result:
                    require(key in {(189, 0), (189, 4)}, 'unqualified imported nonrouting mask')
                    continue
                require(shape.is_box() or shape.is_path() or shape.is_polygon(), 'unqualified actual routing shape')
                polygon = pya.Polygon(shape.box) if shape.is_box() else shape.path.polygon() if shape.is_path() else shape.polygon
                result[key].insert(polygon.transformed(transform)); shapes += 1
        for inst in cell.each_inst():
            child = layout.cell(inst.cell_index)
            if child.name in masters:
                require(cell.cell_index() == top.cell_index(), 'master nested under route cell')
                continue
            require(not inst.is_regular_array() and inst.cplx_trans.mag == 1, 'unqualified actual route array')
            visit(child, transform*inst.cplx_trans)
    visit(top, pya.ICplxTrans())
    for region in result.values(): region.merge()
    return result, shapes


def check(config):
    import pya
    out = Path(config['output_directory'])
    baseline = Path(config['baseline']); prepared = Path(config['preparation'])
    old = json.loads((baseline/'result.json').read_text()); basis = json.loads((baseline/'config.json').read_text())
    produced = json.loads((prepared/'result.json').read_text()); insertion = json.loads((prepared/'candidate/insertion.json').read_text())
    require(old['status'] == 'PASS_NATIVE_ORIGINAL_GDS_ROUTED_MASK_UNION_AND_STREAM_READBACK_NOT_NET_LVS_OR_PROCESS_DRC'
            and old['source_seal_equal'] and not old['resource_errors'] and
            old['geometry']['stream_readback']['sha256'] == sha(baseline/'layout.gds'), 'actual native/master/stream baseline')
    require(produced['status'] == 'PASS_SOURCE_BOUND_ORIGINAL_ALLROW_FILLER_INSERTION_AND_SIGNALS_NOT_PROCESS_DRC'
            and produced['source_seal_equal'] and not produced['resource_errors'] and produced['geometry'] == insertion and
            insertion['filled_odb_sha256'] == sha(prepared/'candidate/filled.odb') and
            insertion['filled_def_sha256'] == sha(prepared/'candidate/filled.def') and
            insertion['source_odb_sha256'] == sha(basis['source_odb']) and
            all(sha(name) == digest for name, digest in produced['source_inputs'].items()),
            'source-bound real native filler/wire/PG insertion required')
    plan = json.loads((prepared/'row-plan.json').read_text())
    require(insertion['plan_sha256'] == sha(prepared/'row-plan.json') and len(plan['fillers']) == 40349, 'exact native filler plan')
    original = json.loads(Path(basis['native_instances']).read_text())
    expected = original['instances']+plan['fillers']; masters = {cell['master'] for cell in expected}
    options = pya.LoadLayoutOptions(); cfg = options.lefdef_config
    cfg.dbu = .001; cfg.map_file = basis['layer_map']; cfg.read_lef_with_def = False
    cfg.lef_files = basis['lef_files']; cfg.macro_resolution_mode = 2; cfg.macro_layout_files = basis['original_gds']
    options.lefdef_config = cfg
    layout = pya.Layout(); layout.read(str(prepared/'candidate/filled.def'), options)
    top = layout.cell(original['top']); require(top is not None and layout.dbu == .001, 'actual filled top/units')
    source = pya.Layout(); source.read(basis['original_gds'][0]); require(source.dbu == .001, 'original standard GDS units')
    original_hashes = old['geometry']['original_master_hashes'] if 'original_master_hashes' in old['geometry'] else \
        json.loads(Path(basis['master_relation']).read_text())['master_hashes']
    actual_hashes = {}
    for master in masters:
        cell = layout.cell(master); require(cell is not None, 'missing actual original master')
        observed = fingerprint(layout, cell)
        if master in original_hashes: require(observed == original_hashes[master], 'old original master changed')
        else:
            original_cell = source.cell(master); require(original_cell is not None, 'missing original filler source')
            require(observed == fingerprint(source, original_cell), 'filler source geometry/text changed')
        actual_hashes[master] = observed
    orientations = {'R0': (0, False), 'MX': (0, True)}
    wanted = Counter((cell['master'], *orientations[cell['orientation']], *cell['origin']) for cell in expected)
    actual = Counter()
    for inst in top.each_inst():
        master = layout.cell(inst.cell_index).name
        if master not in masters: continue
        tr = inst.cplx_trans
        require(not inst.is_regular_array() and tr.mag == 1, 'nonunit filled master transform')
        actual[master, cardinal_angle(tr.angle), bool(tr.is_mirror()), tr.disp.x, tr.disp.y] += 1
    require(actual == wanted, 'all49386 actual original master/placement/transform records differ')
    draw, pins = layer_mapping(basis['layer_map']); keys = set(draw.values()) | set(pins.values())
    baseline_layout = pya.Layout(); baseline_layout.read(str(baseline/'layout.gds'))
    old_regions, old_shapes = routed_regions(baseline_layout, baseline_layout.cell(original['top']),
                                            {cell['master'] for cell in original['instances']}, keys)
    new_regions, new_shapes = routed_regions(layout, top, masters, keys)
    union = [{'layer_datatype': list(key), 'XOR_area_nm2': (old_regions[key]^new_regions[key]).area()}
             for key in sorted(keys)]
    require(all(row['XOR_area_nm2'] == 0 for row in union) and old_shapes == new_shapes,
            'native routing/PG/port masks changed beyond original filler masters')
    stream = out/'filled.gds'; layout.write(str(stream))
    require(stream.read_bytes()[-4:] == bytes((0, 4, 4, 0)), 'complete filled GDS ENDLIB')
    prefix = {'status': 'PASS_ACTUAL_ORIGINAL_FILLER_MASTER_AND_ROUTING_MASK_PREFIX_NOT_PROCESS_DRC',
              'original_master_hashes': actual_hashes, 'actual_original_instances': sum(actual.values()),
              'unchanged_routing_mask_union': union, 'unchanged_routing_shapes': new_shapes,
              'GDS_sha256': sha(stream), 'GDS_bytes': stream.stat().st_size,
              'source_seal_equal': all(sha(name) == digest for name, digest in config['source_inputs'].items())}
    require(prefix['source_seal_equal'], 'filled GDS prefix source changed')
    (out/'prefix-geometry.json').write_text(json.dumps(prefix, indent=2)+'\n')
    del baseline_layout, old_regions, new_regions; gc.collect()
    # Fillers have only these two original Metal1 supply rails, with actual
    # contacts and well/tap layers retained through the exact source masters.
    filler_wells = pya.Region(); filler_pg = {'VDDlogic': pya.Region(), 'VSS': pya.Region()}
    for record in plan['fillers']:
        cell = source.cell(record['master']); width = record['sites']*480
        local = pya.Region(cell.begin_shapes_rec(source.find_layer(8, 0))); local.merge()
        vdd, vss = pya.Region(pya.Box(0, 3560, width, 4000)), pya.Region(pya.Box(0, -220, width, 220))
        require((local^(vdd+vss)).is_empty(), 'original filler contains unknown non-PG Metal1')
        a, mirror = orientations[record['orientation']]; tr = pya.ICplxTrans(1, a, mirror, *record['origin'])
        filler_pg['VDDlogic'].insert(vdd.transformed(tr)); filler_pg['VSS'].insert(vss.transformed(tr))
        filler_wells.insert(pya.Region(cell.begin_shapes_rec(source.find_layer(31, 0))).transformed(tr))
    filler_wells.merge()
    for region in filler_pg.values(): region.merge()
    require((filler_pg['VDDlogic'] & filler_pg['VSS']).is_empty(), 'opposite filler supplies intersect')
    gaps = report_gaps(config['partial_process_report']); uncovered = []
    for text, box in gaps:
        missing = pya.Region(pya.Box(*box))-filler_wells
        if not missing.is_empty(): uncovered.append({'original_edge_pair': text, 'uncovered_area_nm2': missing.area(),
                                                     'uncovered_bbox_nm': str(missing.bbox())})
    (out/'remaining-original-NW-b-corridors.json').write_text(json.dumps(uncovered, indent=2)+'\n')
    # Preserve this actual geometry observation even if the later whole check
    # finds an uncovered original corridor or new signal-metal constraint.
    result = {'status': 'OBSERVED_ACTUAL_ORIGINAL_ALLROW_FILLER_GDS_NOT_PROCESS_DRC',
        'actual_original_masters': len(masters), 'actual_original_instances': sum(actual.values()),
        'original_filler_instances': len(plan['fillers']), 'original_master_hashes': actual_hashes,
        'unchanged_routing_shapes': new_shapes, 'unchanged_routing_mask_union': union,
        'partial_original_NW_b_corridors': len(gaps), 'uncovered_original_corridors': len(uncovered),
        'tangent_witness_policy': '12 actual touching-y edge pairs require new well coverage on both sides in a conservative1DBU band; no process rule is changed',
        'scope': 'Actual original source geometry and unchanged native route; partial old gap coverage is not fresh process DRC'}
    (out/'filler-source-observation.json').write_text(json.dumps(result, indent=2)+'\n')
    require(not uncovered, 'some actual original partial NW.b corridors remain uncovered')
    # Net-aware new Metal1 checks include real routed segments/via landings and
    # original functional-master metal, not just the abstract native row rail.
    # Use a conservative220nm rectangle margin: the original Metal1 table's
    # .30um-width row requires.22um at its longer PRL columns. These new.44um
    # rails do not justify dropping that width rule to the180nm minimum.
    tech = Path(basis['lef_files'][0]).read_text()
    table = re.search(r'^LAYER Metal1\n(.*?)^END Metal1$', tech, re.M | re.S)
    require(table is not None and re.search(r'WIDTH 0\.30\s+0\.18\s+0\.22\s+0\.22', table[1]),
            'original width/PRL Metal1 rule identity differs')
    signal_m1 = pya.Region(); opposing_pg = {'VDDlogic': pya.Region(), 'VSS': pya.Region()}
    native = json.loads(Path(basis['native_geometry']).read_text())
    for net in native['nets']:
        for shape in net['shapes']:
            if shape['layer'] != 'Metal1' or shape['kind'] == 'decoder_rect_witness': continue
            polygon = pya.Box(*shape['rect_nm'])
            if net['name'] in opposing_pg: opposing_pg[net['name']].insert(polygon)
            else: signal_m1.insert(polygon)
    del native; gc.collect()
    # Original standard-cell PG boxes are literal in the pinned LEF. Removing
    # them here only classifies same-net abutment, never suppresses process rules.
    lef = Path(basis['lef_files'][1]).read_text(); body_cache = {}
    for record in original['instances']:
        master = record['master']; cell = layout.cell(master)
        if master not in body_cache:
            local = pya.Region(cell.begin_shapes_rec(layout.find_layer(8, 0)))
            if source.cell(master) is not None:
                body = re.search(r'^MACRO '+re.escape(master)+r'\n(.*?)^END '+re.escape(master)+r'$', lef, re.M | re.S)
                require(body is not None, 'original standard-cell LEF identity')
                pg = pya.Region()
                for name in ('VDD', 'VSS'):
                    pin = re.search(r'^  PIN '+name+r'\n(.*?)^  END '+name+r'$', body[1], re.M | re.S)
                    require(pin is not None and 'LAYER Metal1' in pin[1], 'original core PG interface')
                    values = re.findall(r'RECT ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) ;', pin[1])
                    require(len(values) == 1, 'one original core PG rail rectangle')
                    coords = [Decimal(value)*1000 for value in values[0]]
                    require(all(value == int(value) for value in coords), 'integer original PG rail')
                    pg.insert(pya.Box(*map(int, coords)))
                local -= pg
            # All SRAM Metal1 stays conservative signal/unknown-net here. A
            # source-side same-supply alias could otherwise hide a real short.
            local.merge(); body_cache[master] = local
        angle, mirror = orientations[record['orientation']]
        signal_m1.insert(body_cache[master].transformed(pya.ICplxTrans(1, angle, mirror, *record['origin'])))
    signal_m1.merge()
    spacing = []
    for name, region in filler_pg.items():
        collision = region.sized(220) & signal_m1
        other = opposing_pg['VSS' if name == 'VDDlogic' else 'VDDlogic']; other.merge()
        wrong_supply = region.sized(220) & other
        spacing.append({'net': name, 'conservative_margin_nm': 220,
                        'signal_conflict_area_nm2': collision.area(), 'opposite_native_supply_conflict_area_nm2': wrong_supply.area(),
                        'signal_conflict_bbox_nm': str(collision.bbox()) if not collision.is_empty() else None})
    result['new_filler_Metal1_rule_subset'] = spacing
    (out/'filler-source-observation.json').write_text(json.dumps(result, indent=2)+'\n')
    require(all(row['signal_conflict_area_nm2'] == row['opposite_native_supply_conflict_area_nm2'] == 0
                for row in spacing), 'new filler Metal1 conflicts with actual signal or opposite supply')
    # Consequential negatives use the actual new rail and original partial gap.
    first_rail = next(filler_pg['VDDlogic'].each())
    require(not (pya.Region(first_rail) & filler_pg['VDDlogic']).is_empty(), 'actual same-metal short control')
    gap = pya.Region(pya.Box(*gaps[0][1]))
    require(not (gap-(filler_wells-gap)).is_empty(), 'removed actual well bridge negative')
    result['negative_cases'] = ['actual_filler_rail_as_signal_short', 'removed_actual_original_well_bridge']
    result.update(status='PASS_ACTUAL_ORIGINAL_ALLROW_FILLER_GDS_AND_OLD_GAP_COVERAGE_NOT_PROCESS_DRC',
                  GDS_sha256=sha(stream), GDS_bytes=stream.stat().st_size)
    return result


def main(config_path):
    config = json.loads(Path(config_path).read_text()); out = Path(config['output_directory']); start = time.monotonic()
    result = {'status': 'FAIL'}
    try:
        require(all(sha(name) == digest for name, digest in config['source_inputs'].items()), 'filler geometry input seal')
        result = check(config)
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        result.update(seconds=time.monotonic()-start,
                      source_seal_equal=all(sha(name) == digest for name, digest in config['source_inputs'].items()))
        if not result['source_seal_equal']: result['status'] = 'FAIL'
        (out/'geometry.json').write_text(json.dumps(result, indent=2)+'\n')
    require(result['status'].startswith('PASS_'), result.get('error', 'filler geometry source changed'))


if __name__ == '__main__':
    main(config_path)
