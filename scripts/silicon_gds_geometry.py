#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""KLayout host adapter: original GDS/DEF versus independent native mask union.

Invoke with the pinned KLayout Python runtime, -b -r this-file -rd config_path=.
Geometry equivalence is not connected layout/netlist comparison or process DRC.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from silicon_geometry_export import validate, require


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def layer_mapping(path):
    """Bind each actual original drawing/pin mapping; unknowns fail closed."""
    draw, pins = {}, {}
    for line in Path(path).read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line: continue
        fields = line.split()
        require(len(fields) == 4, 'unqualified original layer map row')
        name, kinds, layer, datatype = fields
        if name == 'NAME' or not (name.startswith('Metal') or name.startswith('Via') or name.startswith('Top')):
            continue
        kinds = set(kinds.split(',')); value = (int(layer), int(datatype))
        if kinds & {'NET', 'SPNET', 'VIA'}:
            require(value[1] == 0 and (name not in draw or draw[name] == value), 'ambiguous drawing map')
            draw[name] = value
        if 'PIN' in kinds and value[1] == 2:
            require(name not in pins, 'ambiguous original pin-purpose map')
            pins[name] = value
    require(set(draw) == {'Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5',
                          'Via1', 'Via2', 'Via3', 'Via4', 'TopMetal1', 'TopMetal2', 'TopVia1', 'TopVia2'},
            'full original metal/cut map required')
    return draw, pins


def fingerprint(layout, cell, cache=None):
    if cache is None: cache = {}
    index = cell.cell_index()
    if index in cache: return cache[index]
    local, children = [], []
    for layer in layout.layer_indexes():
        info = layout.get_info(layer)
        local.extend((info.layer, info.datatype, shape.to_s()) for shape in cell.shapes(layer).each())
    for inst in cell.each_inst():
        children.append((fingerprint(layout, layout.cell(inst.cell_index), cache), inst.cplx_trans.to_s(),
                         str(inst.a), str(inst.b), int(inst.na), int(inst.nb)))
    value = hashlib.sha256(json.dumps([sorted(local), sorted(children)], separators=(',', ':')).encode()).hexdigest()
    cache[index] = value
    return value


def check(config):
    import pya
    out = Path(config['output_directory'])
    native = json.loads(Path(config['native_geometry']).read_text())
    native_receipt = json.loads(Path(config['native_receipt']).read_text())
    require(native_receipt['status'] == 'PASS_READ_ONLY_NATIVE_WIRE_RECT_CUT_POWER_PORT_EXPORT_NOT_LVS_OR_PROCESS_DRC'
            and native_receipt['source_seal_equal'] and native_receipt['byte_identical_original_roundtrip'] and
            native_receipt['native_sha256'] == sha(config['native_geometry']) and
            native_receipt['source_inputs'][config['source_odb']] == sha(config['source_odb']),
            'actual native source/geometry/ABI producer required')
    counts = validate(native)
    expected = json.loads(Path(config['native_instances']).read_text())
    prior = json.loads(Path(config['master_relation']).read_text())
    master_producer = json.loads(Path(config['master_producer']).read_text())
    require(master_producer['status'] == 'PASS_NATIVE_ORIGINAL_GDS_MASTER_TRANSFORM_SOURCE_PILOT_ONLY' and
            master_producer['source_seal_equal'] and
            master_producer['source_inputs'][config['source_odb']] == sha(config['source_odb']) and
            master_producer['source_inputs'][config['routed_def']] == sha(config['routed_def']),
            'original native master/transform source geometry differs')
    require(prior['status'] == 'PASS_ACTUAL_ORIGINAL_GDS_MASTER_AND_TRANSFORM_RELATION_ONLY',
            'actual original master/transform component required')
    options = pya.LoadLayoutOptions(); cfg = options.lefdef_config
    cfg.dbu = .001; cfg.map_file = config['layer_map']; cfg.read_lef_with_def = False
    cfg.lef_files = config['lef_files']; cfg.macro_resolution_mode = 2
    cfg.macro_layout_files = config['original_gds']; options.lefdef_config = cfg
    layout = pya.Layout(); layout.read(config['routed_def'], options)
    top = layout.cell(native['top'])
    require(top is not None and layout.dbu == .001 and expected['top'] == native['top'], 'actual top/units')
    masters = {item['master'] for item in expected['instances']}
    source_layouts = []
    for name in config['original_gds']:
        ly = pya.Layout(); ly.read(name); require(ly.dbu == .001, 'original GDS units'); source_layouts.append(ly)
    for name in masters:
        matches = [(ly, ly.cell(name)) for ly in source_layouts if ly.cell(name) is not None]
        require(len(matches) == 1 and layout.cell(name) is not None, 'missing/ambiguous GDS master '+name)
        original = fingerprint(*matches[0])
        require(original == prior['master_hashes'][name] == fingerprint(layout, layout.cell(name)),
                'actual source hierarchical GDS master changed: '+name)
    orientations = {'R0': (0, False), 'MX': (0, True), 'MY': (180, True), 'R180': (180, False),
                    'R90': (90, False), 'R270': (270, False), 'MXR90': (90, True), 'MYR90': (270, True)}
    instances = Counter((r['master'], *orientations[r['orientation']], *r['origin']) for r in expected['instances'])
    observed = Counter()
    for inst in top.each_inst():
        name = layout.cell(inst.cell_index).name
        if name not in masters: continue
        tr = inst.cplx_trans
        require(tr.mag == 1 and not inst.is_regular_array(), 'nonunit/unqualified physical master transform')
        observed[name, int(tr.angle)%360, bool(tr.is_mirror()), tr.disp.x, tr.disp.y] += 1
    require(observed == instances, 'actual full physical master placement/transform relation')
    draw, pins = layer_mapping(config['layer_map'])
    expected_regions = {value: pya.Region() for value in set(draw.values()) | set(pins.values())}
    native_pg = defaultdict(list)
    for net in native['nets']:
        for shape in net['shapes']:
            require(shape['layer'] in draw, 'unmapped actual native wire/cut/PG layer '+shape['layer'])
            if shape['kind'] == 'decoder_rect_witness': continue
            key = draw[shape['layer']]
            expected_regions[key].insert(pya.Box(*shape['rect_nm']))
            if shape['kind'] == 'special_wire': native_pg[shape['layer']].append(shape['rect_nm'])
    for port in native['ports']:
        for shape in port['shapes']:
            require(shape['layer'] in draw and shape['layer'] in pins, 'unmapped actual native port mask')
            box = pya.Box(*shape['rect_nm'])
            expected_regions[draw[shape['layer']]].insert(box)
            expected_regions[pins[shape['layer']]].insert(box)
    actual_regions = {key: pya.Region() for key in expected_regions}
    ignored, via_cells, wire_shapes = Counter(), set(), 0
    def visit(cell, transform):
        nonlocal wire_shapes
        for layer in layout.layer_indexes():
            info = layout.get_info(layer); key = (info.layer, info.datatype)
            for shape in cell.shapes(layer).each():
                if shape.is_text():
                    # Names and COMPONENT/DIEAREA labels carry metadata, not
                    # a conducting mask. Exact master text is checked above.
                    ignored['text:'+str(key)] += 1; continue
                if key not in actual_regions:
                    require(key in {(189, 0), (189, 4)}, 'unqualified imported nonrouting mask '+str(key))
                    ignored['original_component_or_diearea:'+str(key)] += 1; continue
                if shape.is_box(): polygon = pya.Polygon(shape.box)
                elif shape.is_path(): polygon = shape.path.polygon()
                elif shape.is_polygon(): polygon = shape.polygon
                else: raise ValueError('unqualified imported geometry kind')
                actual_regions[key].insert(polygon.transformed(transform)); wire_shapes += 1
        for inst in cell.each_inst():
            child = layout.cell(inst.cell_index)
            if child.name in masters:
                require(cell.cell_index() == top.cell_index(), 'unexpected master under routing cell')
                continue
            require(not inst.is_regular_array() and inst.cplx_trans.mag == 1, 'unqualified via cell array/magnification')
            via_cells.add(child.name)
            visit(child, transform*inst.cplx_trans)
    visit(top, pya.ICplxTrans())
    differences = []
    rows = []
    for key in sorted(expected_regions):
        want, actual = expected_regions[key], actual_regions[key]
        want.merge(); actual.merge(); diff = want ^ actual
        rows.append({'GDS_layer_datatype': list(key), 'native_union_area_nm2': want.area(),
                     'GDS_union_area_nm2': actual.area(), 'XOR_area_nm2': diff.area(),
                     'XOR_polygons': diff.count()})
        if not diff.is_empty():
            differences.append({'GDS_layer_datatype': list(key), 'native_only_area_nm2': (want-actual).area(),
                                'GDS_only_area_nm2': (actual-want).area(), 'XOR_bbox_nm': str(diff.bbox())})
    # Always retain measured per-layer differences; an import omission is an
    # actual failed relation, never silently dropped because the map omits it.
    (out/'mask-differences.json').write_text(json.dumps({'layers': rows, 'differences': differences}, indent=2)+'\n')
    require(not differences, 'actual native versus imported route/PG/port mask union differs')
    negatives = []
    def reject(label, wanted, changed):
        require(not (wanted ^ changed).is_empty(), 'consequential mask negative accepted: '+label)
        negatives.append(label)
    # Mutate the real imported geometry unions. These test the exact comparison
    # operation with missing cut, extra conductor, and widened PG rather than a
    # separate nominal rectangle fixture.
    cuts = actual_regions[draw['Via1']]
    first = next(cuts.each())
    reject('deleted_actual_Via1_cut', expected_regions[draw['Via1']], cuts-pya.Region(first))
    metal = actual_regions[draw['Metal2']]
    bbox = metal.bbox()
    reject('added_actual_mapped_conductor', expected_regions[draw['Metal2']],
           metal+pya.Region(pya.Box(bbox.right+1000, bbox.top+1000, bbox.right+1200, bbox.top+1200)))
    pg = max(native_pg['TopMetal2'], key=lambda r: (r[2]-r[0])*(r[3]-r[1]))
    pg_box = pya.Box(pg[0]-1, pg[1]-1, pg[2]+1, pg[3]+1)
    reject('widened_actual_TopMetal2_PG', expected_regions[draw['TopMetal2']],
           actual_regions[draw['TopMetal2']]+pya.Region(pg_box))
    # Independent masks for purpose2 ports must also survive streamout/import.
    port_key = next(key for key in pins.values() if not actual_regions[key].is_empty())
    reject('deleted_actual_port_mask', expected_regions[port_key], pya.Region())
    result = {'status': 'PASS_ORIGINAL_GDS_MASTER_TRANSFORM_AND_NATIVE_ROUTED_MASK_UNION_ONLY',
              'scope': __doc__, 'native_geometry': counts, 'top_instances': sum(instances.values()),
              'original_masters': len(masters), 'actual_routing_shapes_imported': wire_shapes,
              'actual_via_cells': sorted(via_cells), 'layers': rows, 'negatives': negatives,
              'original_map_metadata_shapes': dict(ignored),
              'not_checked': ['net-connected transistor LVS', 'process DRC/EOL/area/density/antenna',
                              'IR/EM', 'pads/package/board', 'GDS streamout/readback',
                              'BLOCKAGE/LEFOBS are router constraints, not conducting masks; original map omits BLOCKAGE']}
    return result


def main(config_path):
    config_file = Path(config_path).resolve(); config = json.loads(config_file.read_text())
    out = Path(config['output_directory']); result_path = out/'geometry.json'
    require(out.is_dir() and not result_path.exists(), 'unused component output required')
    start = time.monotonic()
    r = {'status': 'FAIL', 'scope': __doc__}
    try:
        require(config['schema'] == 'lemma-native-gds-geometry-inputs/1' and config['source_inputs'] and
                all(sha(name) == digest for name, digest in config['source_inputs'].items()), 'actual source closure')
        r.update(check(config))
    except BaseException as error:
        r['error'] = repr(error)
    finally:
        r.update(seconds=time.monotonic()-start, source_seal_equal=all(sha(name) == digest
                 for name, digest in config.get('source_inputs', {}).items()))
        result_path.write_text(json.dumps(r, indent=2)+'\n')
    require(r['status'].startswith('PASS_'), r.get('error', 'geometry relation failed'))


if __name__ == '__main__':
    if 'config_path' not in globals():
        raise ValueError('Use pinned KLayout -b -r scripts/silicon_gds_geometry.py -rd config_path=...')
    main(config_path)
