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
import tarfile
import time
import xml.etree.ElementTree as ET
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silicon_gds_geometry import sha, cardinal_angle, fingerprint, layer_mapping
from silicon_geometry_export import require


def source_inputs_unchanged(inputs):
    try:
        return all(sha(name) == digest for name, digest in inputs.items())
    except OSError:
        return False


def original_pg_rectangles(body, name):
    """All literal original Metal1 pin rectangles, including internal fingers.

    This classifies source-declared power metal; it does not merge supplies or
    waive a spacing rule. Unknown layers, polygons and fractional DBU reject.
    """
    require(name in ('VDD', 'VSS'), 'literal original supply name required')
    pin = re.search(r'^  PIN '+re.escape(name)+r'\n(.*?)^  END '+re.escape(name)+r'$', body, re.M | re.S)
    require(pin is not None and re.search(r'(?m)^\s*USE '+('POWER' if name == 'VDD' else 'GROUND')+r' ;$', pin[1]),
            'original core PG pin/use identity')
    ports = re.findall(r'(?ms)^\s*PORT\s*\n(.*?)^\s*END\s*$', pin[1])
    require(len(ports) == 1, 'one literal original PG PORT required')
    lines = [line.strip() for line in ports[0].splitlines() if line.strip()]
    require(lines and lines[0] == 'LAYER Metal1 ;', 'original core PG Metal1 interface')
    result = []
    for line in lines[1:]:
        match = re.fullmatch(r'RECT ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) ;', line)
        require(match is not None, 'unqualified original PG geometry')
        coords = [Decimal(value)*1000 for value in match.groups()]
        require(all(value == int(value) for value in coords) and coords[0] < coords[2] and coords[1] < coords[3],
                'integer nonempty original PG rectangle')
        result.append(tuple(map(int, coords)))
    require(result and len(set(result)) == len(result), 'all unique original PG rectangles required')
    return result


def insertion_source_binding(produced, prepared):
    """Bind completed insertion inputs without relabeling its old code producer.

    New observer code may differ only when the exact old script bytes remain in
    its original sealed source capsule. Physical inputs and tools stay literal.
    """
    archive_path = prepared/'source-closure.tar.gz'
    require(sha(archive_path) == produced['source_archive_sha256'], 'original insertion source capsule differs')
    scripts = Path(__file__).resolve().parent
    archived = None
    reused = []
    for name, digest in produced['source_inputs'].items():
        path = Path(name)
        if path.exists() and sha(path) == digest: continue
        require(path.parent == scripts and path.suffix == '.py', 'insertion physical/tool input changed')
        if archived is None:
            import hashlib
            with tarfile.open(archive_path, 'r:gz') as archive:
                archived = [(Path(member.name).name, hashlib.sha256(archive.extractfile(member).read()).hexdigest())
                            for member in archive.getmembers() if member.isfile()]
        require([value for label, value in archived if label.endswith('-'+path.name)] == [digest],
                'exact original insertion script absent or ambiguous in source capsule')
        reused.append({'path': name, 'original_sha256': digest, 'binding': 'Original completed producer capsule; no fresh insertion'})
    return reused


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


def original_filler_regions(source, plan):
    """Bound all new physical-only masks to the original spacer source."""
    import pya
    orientations = {'R0': (0, False), 'MX': (0, True)}
    # Fillers have only these two original Metal1 supply rails, with actual
    # contacts and well/tap layers retained through the exact source masters.
    filler_wells = pya.Region(); filler_pg = {'VDDlogic': pya.Region(), 'VSS': pya.Region()}
    templates = {}
    for name in {record['master'] for record in plan['fillers']}:
        cell = source.cell(name); width = int(name.rsplit('_', 1)[1])*480
        local = pya.Region(cell.begin_shapes_rec(source.find_layer(8, 0))); local.merge()
        vdd, vss = pya.Region(pya.Box(0, 3560, width, 4000)), pya.Region(pya.Box(0, -220, width, 220))
        require((local^(vdd+vss)).is_empty(), 'original filler contains unknown non-PG Metal1')
        templates[name] = (vdd, vss, pya.Region(cell.begin_shapes_rec(source.find_layer(31, 0))))
    for record in plan['fillers']:
        vdd, vss, well = templates[record['master']]
        a, mirror = orientations[record['orientation']]; tr = pya.ICplxTrans(1, a, mirror, *record['origin'])
        filler_pg['VDDlogic'].insert(vdd.transformed(tr)); filler_pg['VSS'].insert(vss.transformed(tr))
        filler_wells.insert(well.transformed(tr))
    filler_wells.merge()
    for region in filler_pg.values(): region.merge()
    require((filler_pg['VDDlogic'] & filler_pg['VSS']).is_empty(), 'opposite filler supplies intersect')
    return filler_wells, filler_pg



def original_layer_bounds(layout, top, layer):
    """Exact original-mask extents without flattening repeated SRAM geometry.

    Bounding boxes commute with cardinal isometries and array translations.
    This proves conservative source separation only, not mask connectivity.
    """
    import pya
    cache = {}; active = set(); cells = shapes = arrays = 0
    def visit(cell):
        nonlocal cells, shapes, arrays
        key = cell.cell_index()
        if key in cache: return cache[key]
        require(key not in active, 'cyclic original mask hierarchy')
        active.add(key); cells += 1; result = pya.Box()
        for shape in cell.shapes(layer).each():
            if shape.is_text(): continue
            require(shape.is_box() or shape.is_path() or shape.is_polygon(), 'unknown original mask shape')
            result += shape.bbox(); shapes += 1
        for inst in cell.each_inst():
            tr = inst.cplx_trans
            require(tr.mag == 1, 'nonunit original mask hierarchy')
            cardinal_angle(tr.angle)
            child = visit(layout.cell(inst.cell_index))
            if child.empty(): continue
            box = child.transformed(tr)
            if inst.is_regular_array():
                require(type(inst.na) is int and type(inst.nb) is int and inst.na > 0 and inst.nb > 0,
                        'invalid original mask array')
                arrays += 1
                for i in (0, inst.na-1):
                    for j in (0, inst.nb-1):
                        result += box.moved(i*inst.a.x+j*inst.b.x, i*inst.a.y+j*inst.b.y)
            else: result += box
        active.remove(key); cache[key] = result; return result
    result = visit(top)
    require(not result.empty(), 'empty original mask layer')
    return {'bbox_nm': [result.left, result.bottom, result.right, result.top],
            'unique_cells': cells, 'literal_shapes': shapes, 'source_arrays': arrays,
            'relation': 'Exact cardinal-unit hierarchy/array source mask extents; no flattening or connectivity inference'}


def observe_metal1(basis, layout, source, original, filler_pg, out):
    """Retain actual direct/clearance masks and source-conservative owners."""
    import pya
    orientations = {'R0': (0, False), 'MX': (0, True)}
    started = time.monotonic()
    def phase(name, **values):
        record = dict(phase=name, seconds=time.monotonic()-started, **values)
        (out/'Metal1-phase.json').write_text(json.dumps(record, indent=2)+'\n')
        print('METAL1_PHASE', json.dumps(record), flush=True)
    def retain_regions(stem, groups):
        retained = pya.Layout(); retained.dbu = .001; cell = retained.create_cell('observed_filler_metal1_conflicts')
        layers = []
        for index, name in enumerate(('VDDlogic', 'VSS')):
            for offset, (regions, relation) in enumerate(groups):
                layer = 100+4*index+offset
                cell.shapes(retained.layer(layer, 0)).insert(regions[name])
                layers.append({'layer': layer, 'datatype': 0, 'supply': name, 'relation': relation})
        retained.write(str(out/(stem+'.gds')))
        (out/(stem+'.json')).write_text(json.dumps({'dbu_um': .001, 'layers': layers,
            'source_scope': 'Exact diagnostic masks; original chip GDS is unchanged; not processDRC/LVS',
            'sha256': sha(out/(stem+'.gds'))}, indent=2)+'\n')
    phase('begin')
    tech = Path(basis['lef_files'][0]).read_text()
    table = re.search(r'^LAYER Metal1\n(.*?)^END Metal1$', tech, re.M | re.S)
    require(table is not None and re.search(r'WIDTH 0\.30\s+0\.18\s+0\.22\s+0\.22', table[1]),
            'original width/PRL Metal1 rule identity differs')
    signal_m1 = pya.Region(); opposing_pg = {'VDDlogic': pya.Region(), 'VSS': pya.Region()}
    old_known_pg = {'VDDlogic': pya.Region(), 'VSS': pya.Region()}
    native = json.loads(Path(basis['native_geometry']).read_text()); native_m1_records = []
    for net in native['nets']:
        for shape in net['shapes']:
            if shape['layer'] != 'Metal1' or shape['kind'] == 'decoder_rect_witness': continue
            polygon = pya.Box(*shape['rect_nm'])
            if net['name'] in opposing_pg:
                opposing_pg[net['name']].insert(polygon); old_known_pg[net['name']].insert(polygon)
            else:
                signal_m1.insert(polygon); native_m1_records.append((net['name'], tuple(shape['rect_nm'])))
    del native; gc.collect()
    phase('native_conductors_loaded', native_Metal1_records=len(native_m1_records))
    # Original standard-cell PG boxes are literal in the pinned LEF. Removing
    # them here only classifies same-net abutment, never suppresses process rules.
    lef = Path(basis['lef_files'][1]).read_text(); body_cache = {}; body_pg_cache = {}
    for record in original['instances']:
        master = record['master']; cell = layout.cell(master)
        if master not in body_cache:
            local = pya.Region(cell.begin_shapes_rec(layout.find_layer(8, 0)))
            body_pg_cache[master] = {}
            if source.cell(master) is not None:
                body = re.search(r'^MACRO '+re.escape(master)+r'\n(.*?)^END '+re.escape(master)+r'$', lef, re.M | re.S)
                require(body is not None, 'original standard-cell LEF identity')
                pg = pya.Region()
                for name in ('VDD', 'VSS'):
                    one = pya.Region()
                    for coords in original_pg_rectangles(body[1], name): one.insert(pya.Box(*coords))
                    # Only actual source-GDS metal within a declared power
                    # port contributes to the known old baseline, never an
                    # abstract LEF rectangle in otherwise empty space.
                    body_pg_cache[master]['VDDlogic' if name == 'VDD' else 'VSS'] = local & one
                    pg.insert(one)
                local -= pg
            # All SRAM Metal1 stays conservative signal/unknown-net here. A
            # source-side same-supply alias could otherwise hide a real short.
            local.merge(); body_cache[master] = local
        angle, mirror = orientations[record['orientation']]
        transform = pya.ICplxTrans(1, angle, mirror, *record['origin'])
        signal_m1.insert(body_cache[master].transformed(transform))
    phase('original_master_signal_regions_collected', masters=len(body_cache))
    signal_m1.merge()
    spacing = []; margin_regions = {}; direct_regions = {}; introduced_margin_regions = {}; introduced_direct_regions = {}
    for name, region in filler_pg.items():
        margin_regions[name] = region.sized(220) & signal_m1
        direct_regions[name] = region & signal_m1
    retain_regions('Metal1-initial-failed-regions', [(margin_regions, 'conservative220nm_clearance'),
                   (direct_regions, 'positive_area_conductor_intersection')])
    phase('exact_failed_masks_retained', areas={name: region.area() for name, region in margin_regions.items()})
    # Only old power geometry within220nm of a failed point can contribute to
    # this attribution. Preserve the complete candidate failure masks above;
    # cropping a baseline never removes a candidate failure or changes DRC.
    # This avoids merging every old core power finger across the full chip.
    roi = {name: region.sized(220) for name, region in margin_regions.items()}
    for name in old_known_pg:
        complete_native = old_known_pg[name].sized(220) & margin_regions[name]
        old_known_pg[name] &= roi[name]
        require(((old_known_pg[name].sized(220) & margin_regions[name])^complete_native).is_empty(),
                'actual native PG ROI changed the complete failed-point baseline')
    for record in original['instances']:
        angle, mirror = orientations[record['orientation']]; x, y = record['origin']
        transform = pya.ICplxTrans(1, angle, mirror, x, y)
        inverse = pya.ICplxTrans(1, angle, mirror, -x, y if mirror else -y)
        for name, local in body_pg_cache[record['master']].items():
            clipped = local & roi[name].transformed(inverse)
            if not clipped.is_empty(): old_known_pg[name].insert(clipped.transformed(transform))
    for region in old_known_pg.values(): region.merge()
    phase('known_original_PG_ROI_ready')
    for name, region in filler_pg.items():
        collision = margin_regions[name]; direct = direct_regions[name]
        old_margin = old_known_pg[name].sized(220)
        introduced_margin_regions[name] = collision-old_margin
        introduced_direct_regions[name] = direct-old_known_pg[name]
        require(introduced_margin_regions[name].area()+(collision & old_margin).area() == collision.area() and
                introduced_direct_regions[name].area()+(direct & old_known_pg[name]).area() == direct.area(),
                'exact old/new metal relation must partition every observed failed area')
        other = opposing_pg['VSS' if name == 'VDDlogic' else 'VDDlogic']; other.merge()
        wrong_supply = region.sized(220) & other
        spacing.append({'net': name, 'conservative_margin_nm': 220,
                        'signal_conflict_area_nm2': collision.area(),
                        'positive_area_conductor_intersection_nm2': direct.area(), 'opposite_native_supply_conflict_area_nm2': wrong_supply.area(),
                        'opposite_native_supply_scope': 'VDDlogic versus VSS only; VDDARRAY remains in the conservative other-conductor set',
                        'already_within_known_original_PG_clearance_nm2': (collision & old_margin).area(),
                        'newly_introduced_clearance_area_nm2': introduced_margin_regions[name].area(),
                        'newly_introduced_positive_area_intersection_nm2': introduced_direct_regions[name].area(),
                        'baseline_scope': 'Actual native PG plus source-GDS metal within literal original core PG ports; SRAM internal power remains unassigned',
                        'signal_conflict_bbox_nm': str(collision.bbox()) if not collision.is_empty() else None})
    # Preserve exact failed geometry and conservative ownership, so a failed
    # checker does not force another complete import merely to diagnose it.
    # SRAM source metal has no net assignment here: a geometric intersection
    # is not silently promoted to an independently established signal short.
    owners = []
    def attribute(identity, region):
        for supply, failed in margin_regions.items():
            overlap = region & failed
            if overlap.is_empty(): continue
            direct = region & direct_regions[supply]
            owners.append(dict(identity, new_filler_supply=supply,
                conservative220nm_intersection_area_nm2=overlap.area(),
                positive_area_conductor_intersection_nm2=direct.area(),
                newly_introduced_clearance_area_nm2=(region & introduced_margin_regions[supply]).area(),
                newly_introduced_positive_area_intersection_nm2=(region & introduced_direct_regions[supply]).area(),
                intersection_bbox_nm=str(overlap.bbox())))
    for name, box in native_m1_records:
        attribute({'source_kind': 'native_net_conductor', 'net': name, 'rect_nm': list(box)},
                  pya.Region(pya.Box(*box)))
    all_failed = margin_regions['VDDlogic']+margin_regions['VSS']
    for record in original['instances']:
        master = record['master']; angle, mirror = orientations[record['orientation']]
        x, y = record['origin']; inverse = pya.ICplxTrans(1, angle, mirror, -x, y if mirror else -y)
        local = body_cache[master] & all_failed.transformed(inverse)
        if local.is_empty(): continue
        region = local.transformed(pya.ICplxTrans(1, angle, mirror, x, y))
        attribute({'source_kind': 'original_core_metal_excluding_literal_PG_ports'
                   if source.cell(master) is not None else 'original_SRAM_metal_net_unassigned',
                   'instance': record['name'], 'master': master, 'origin_nm': record['origin'],
                   'orientation': record['orientation']}, region)
    (out/'Metal1-conflict-owners.json').write_text(json.dumps(owners, indent=2)+'\n')
    retain_regions('Metal1-conflict-regions', [(margin_regions, 'conservative220nm_clearance'),
            (direct_regions, 'positive_area_conductor_intersection'),
            (introduced_margin_regions, 'newly_introduced_clearance_against_known_original_PG'),
            (introduced_direct_regions, 'newly_introduced_positive_area_against_known_original_PG')])
    phase('complete', owners=len(owners))
    return spacing


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
            insertion['source_odb_sha256'] == sha(basis['source_odb']),
            'source-bound real native filler/wire/PG insertion required')
    historical_code = insertion_source_binding(produced, prepared)
    plan = json.loads((prepared/'row-plan.json').read_text())
    require(insertion['plan_sha256'] == sha(prepared/'row-plan.json') and
            len(plan['fillers']) == (40264 if plan['schema'] == 'lemma-original-row-filler-plan/3' else
                                     40336 if plan['schema'] == 'lemma-original-row-filler-plan/2' else 40349),
            'exact native filler plan')
    original = json.loads(Path(basis['native_instances']).read_text())
    expected = original['instances']+plan['fillers']; masters = {cell['master'] for cell in expected}
    options = pya.LoadLayoutOptions(); cfg = options.lefdef_config
    cfg.dbu = .001; cfg.map_file = basis['layer_map']; cfg.read_lef_with_def = False
    cfg.lef_files = basis['lef_files']; cfg.macro_resolution_mode = 2; cfg.macro_layout_files = basis['original_gds']
    options.lefdef_config = cfg
    closed = config.get('completed_gds_prefix')
    if closed:
        prior = Path(closed); prefix = json.loads((prior/'prefix-geometry.json').read_text())
        producer = json.loads((prior/'result.json').read_text())
        require(producer['source_seal_equal'] and not producer['resource_errors'] and
                prefix['status'] == 'PASS_ACTUAL_ORIGINAL_FILLER_MASTER_AND_ROUTING_MASK_PREFIX_NOT_PROCESS_DRC' and
                prefix['source_seal_equal'] and prefix['GDS_sha256'] == sha(prior/'filled.gds') and
                json.loads((prior/'config.json').read_text())['preparation'] == str(prepared),
                'exact completed original-GDS prefix required; failed whole is not promoted')
        layout = pya.Layout(); layout.read(str(prior/'filled.gds'))
    else:
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
    stream = Path(closed)/'filled.gds' if closed else out/'filled.gds'
    if not closed: layout.write(str(stream))
    require(stream.read_bytes()[-4:] == bytes((0, 4, 4, 0)), 'complete filled GDS ENDLIB')
    prefix = {'status': 'PASS_ACTUAL_ORIGINAL_FILLER_MASTER_AND_ROUTING_MASK_PREFIX_NOT_PROCESS_DRC',
              'original_master_hashes': actual_hashes, 'actual_original_instances': sum(actual.values()),
              'unchanged_routing_mask_union': union, 'unchanged_routing_shapes': new_shapes,
              'GDS_sha256': sha(stream), 'GDS_bytes': stream.stat().st_size,
              'stream_reused_from': str(stream) if closed else None,
              'historical_insertion_code_binding': historical_code,
              'source_seal_equal': all(sha(name) == digest for name, digest in config['source_inputs'].items())}
    require(prefix['source_seal_equal'], 'filled GDS prefix source changed')
    (out/'prefix-geometry.json').write_text(json.dumps(prefix, indent=2)+'\n')
    del baseline_layout, old_regions, new_regions; gc.collect()
    filler_wells, filler_pg = original_filler_regions(source, plan)
    gaps = report_gaps(config['partial_process_report']); uncovered = []
    witnesses = pya.Region()
    for text, box in gaps: witnesses.insert(pya.Box(*box))
    # A single exact Boolean difference replaces3717 repeated differences
    # against the same large region. Only a nonempty result needs per-witness
    # attribution; a zero result proves every inserted witness is covered.
    missing_all = witnesses-filler_wells
    if not missing_all.is_empty():
        for text, box in gaps:
            missing = pya.Region(pya.Box(*box)) & missing_all
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
    # A retained original gap does not prevent the independent new-metal
    # collision check. Accumulate both outcomes; neither becomes a pass.
    # Net-aware new Metal1 checks include real routed segments/via landings and
    # original functional-master metal, not just the abstract native row rail.
    # Use a conservative220nm rectangle margin: the original Metal1 table's
    # .30um-width row requires.22um at its longer PRL columns. These new.44um
    # rails do not justify dropping that width rule to the180nm minimum.
    spacing = observe_metal1(basis, layout, source, original, filler_pg, out)
    result['new_filler_Metal1_rule_subset'] = spacing
    (out/'filler-source-observation.json').write_text(json.dumps(result, indent=2)+'\n')
    metal_ok = all(row['signal_conflict_area_nm2'] == row['opposite_native_supply_conflict_area_nm2'] == 0
                   for row in spacing)
    # Consequential negatives use the actual new rail and original partial gap.
    first_rail = next(filler_pg['VDDlogic'].each())
    require(not (pya.Region(first_rail) & filler_pg['VDDlogic']).is_empty(), 'actual same-metal short control')
    gap = pya.Region(pya.Box(*gaps[0][1]))
    require(not (gap-(filler_wells-gap)).is_empty(), 'removed actual well bridge negative')
    result['negative_cases'] = ['actual_filler_rail_as_signal_short', 'removed_actual_original_well_bridge']
    result.update(status='PASS_ACTUAL_ORIGINAL_ALLROW_FILLER_GDS_AND_OLD_GAP_COVERAGE_NOT_PROCESS_DRC'
                  if not uncovered and metal_ok else 'FAIL_FILLER_GAP_OR_METAL_SUBSET',
                  failures=(['some actual original partial NW.b corridors remain uncovered'] if uncovered else [])+
                           ([] if metal_ok else ['new filler Metal1 conflicts with actual signal or opposite supply']),
                  GDS_sha256=sha(stream), GDS_bytes=stream.stat().st_size)
    return result


def main(config_path):
    config = json.loads(Path(config_path).read_text()); out = Path(config['output_directory']); start = time.monotonic()
    result = {'status': 'FAIL'}
    try:
        require(source_inputs_unchanged(config['source_inputs']), 'filler geometry input seal')
        result = check(config)
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        result.update(seconds=time.monotonic()-start,
                      source_seal_equal=source_inputs_unchanged(config['source_inputs']))
        if not result['source_seal_equal']: result['status'] = 'FAIL'
        (out/'geometry.json').write_text(json.dumps(result, indent=2)+'\n')
    require(result['status'].startswith('PASS_'), result.get('error') or
            '; '.join(result.get('failures', [])) or 'filler geometry failed')


if __name__ == '__main__':
    main(config_path)
