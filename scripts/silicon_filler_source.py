#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Original SG13G2 filler source, all-row plan and exact native insertion.

Source probes remain read-only. The explicit insertion function creates a
separate physical candidate and never promotes partial process findings.
"""
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from silicon_geometry_export import require
from silicon_gds_geometry import fingerprint

SELECTED_SOURCE_ODB = '43ffc744714d5f216227035ffa4eca2e77b87f27b61b4f39fa6296a4091f7852'
SELECTED_PLAN_SHA = 'f46d751c9d7fdcb30b601c46ffa104e48d39ae73ac1aaec60ce2382ab2799b39'
RIGHT_KEEPOUT_PLAN_SHA = '6004367eac69ec9a07937f2eefd4530a018fe58d15e41bceaaffa047f9dbcf54'
BILATERAL_KEEPOUT_PLAN_SHA = 'dcebfc0a34ad026c66c683b5b4f586110bcd96db3ec198a0f8e943ec83d7fdde'
REPAIRED_UNROUTED_ODB = 'cd1b0b572c7d844dc77560bfdf1141b6aae9d57a2ff3ef9eeaf53448a7a974d9'
REPAIRED_BILATERAL_PLAN_SHA = '993b940511465d3fb1c2f8af1266c8abc97b432d5eb7ceebf6e72e8fdb4dcd5d'


def filler_source_pair(source_sha,plan_sha):
    require((source_sha == SELECTED_SOURCE_ODB and plan_sha in
             (SELECTED_PLAN_SHA,RIGHT_KEEPOUT_PLAN_SHA,BILATERAL_KEEPOUT_PLAN_SHA)) or
            (source_sha == REPAIRED_UNROUTED_ODB and plan_sha == REPAIRED_BILATERAL_PLAN_SHA),
            'exact selected routed or source-proved32-move unrouted source/plan pair required')
    return source_sha == REPAIRED_UNROUTED_ODB



def lef_masters(text):
    """Literal original LEF dimensions/classes, in the selected1000 DBU/um."""
    result = {}
    for name, body in re.findall(r'^MACRO (\S+)\n(.*?)^END \1$', text, re.M | re.S):
        size = re.search(r'(?m)^\s*SIZE ([\d.]+) BY ([\d.]+) ;', body)
        kind = re.search(r'(?m)^\s*CLASS ([^;]+) ;', body)
        require(size is not None and kind is not None and name not in result,
                'unique original LEF master dimensions/class required')
        values = tuple(Decimal(value)*1000 for value in size.groups())
        require(all(value == int(value) and value > 0 for value in values), 'integer native master dimensions')
        result[name] = {'size_nm': tuple(map(int, values)), 'class': kind[1].strip(),
                        'pins': re.findall(r'^  PIN (\S+)', body, re.M)}
    require(result, 'original LEF masters required')
    return result


def all_row_plan(def_text, expected, masters, *, macro_right_extra_sites=0, macro_left_extra_sites=0):
    """Tile the actual free row sites with original physical CORE SPACER cells.

    Functional placements and their one-site left/right separation stay fixed.
    Spacers deliberately occupy unused sites, including those separating two
    functional cells. They have no signal pins; treating a physical spacer as
    another functional cell needing its own padding would defeat well filling.
    Macro exclusion rounds outward to native sites and never clips a macro.
    This is a plan, not a claim of placed/PG-connected or process-clean cells.
    """
    require(type(macro_right_extra_sites) is int and macro_right_extra_sites in (0, 2),
            'only original or exact reviewed two-site macro-right keepout')
    require(type(macro_left_extra_sites) is int and macro_left_extra_sites in (0, 2) and
            (not macro_left_extra_sites or macro_right_extra_sites == 2),
            'only reviewed bilateral two-site spacer keepout')
    require(expected['dbu_per_micron'] == 1000 and
            re.search(r'(?m)^UNITS DISTANCE MICRONS 1000 ;$', def_text), 'literal1000 DBU/um required')
    raw = re.findall(r'^ROW (\S+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY (\d+) STEP (\d+) (\d+) ;',
                     def_text, re.M)
    require(len(raw) == len(re.findall(r'(?m)^ROW ', def_text)) and raw, 'all actual rows must be understood')
    rows = []
    for name, site, x, y, orientation, nx, ny, dx, dy in raw:
        x, y, nx, ny, dx, dy = map(int, (x, y, nx, ny, dx, dy))
        require(site == 'CoreSite' and orientation in ('N', 'FS') and nx > 0 and
                (ny, dx, dy) == (1, 480, 0), 'original one-dimensional480nm CoreSite row required')
        rows.append({'name': name, 'x_nm': x, 'y_nm': y, 'sites': nx,
                     'orientation': {'N': 'R0', 'FS': 'MX'}[orientation]})
    require(len({row['name'] for row in rows}) == len(rows) and
            len({row['y_nm'] for row in rows}) == len(rows), 'unique unfragmented selected rows required')
    rows.sort(key=lambda row: row['y_nm'])
    require(all(b['y_nm']-a['y_nm'] == 3780 for a, b in zip(rows, rows[1:])), 'complete original3780nm rows')
    instances = expected['instances']
    require(len({cell['name'] for cell in instances}) == len(instances), 'duplicate native instance')
    by_y = {row['y_nm']: [] for row in rows}
    row_orientations = {row['y_nm']: row['orientation'] for row in rows}
    macros = []
    functional = []
    for cell in instances:
        master = masters[cell['master']]
        width, height = master['size_nm']; x, y = cell['location']
        require(cell['orientation'] in ('R0', 'MX'), 'selected source row/macro orientation required')
        require(cell['origin'] == [x, y+(height if cell['orientation'] == 'MX' else 0)],
                'actual origin/location/orientation relation differs')
        if master['class'] == 'BLOCK':
            macros.append((x, y, x+width, y+height, cell['name']))
        else:
            require(master['class'] == 'CORE' and height == 3780 and y in by_y,
                    'only original single-height functional cells in source')
            require(cell['orientation'] == row_orientations[y], 'functional cell differs from actual row orientation')
            by_y[y].append((x, x+width, cell['name']))
            functional.append(cell['name'])
    require(len(macros) == 3 and all('pen_sram_lane'+str(index) in {box[4] for box in macros}
                                   for index in range(3)), 'all three native SRAM exclusions required')
    for sites in (1, 2, 4, 8):
        master = masters['sg13g2_fill_'+str(sites)]
        require(master == {'size_nm': (480*sites, 3780), 'class': 'CORE SPACER', 'pins': ['VDD', 'VSS']},
                'original source filler dimensions/class/power interface differs')
    fill = []
    source_sites = blocked_sites = 0
    preserved_keepout_cells = set(); preserved_left_cells = set()
    for row in rows:
        x0, y0, count = row['x_nm'], row['y_nm'], row['sites']
        occupied = bytearray(count)
        cells = sorted(by_y[y0])
        require(all(b[0]-a[1] >= 960 for a, b in zip(cells, cells[1:])),
                'original functional one-site left/right padding differs')
        for left, right, name in cells:
            require((left-x0) % 480 == (right-x0) % 480 == 0 and x0 <= left < right <= x0+count*480,
                    'source functional cell off actual row/site')
            first, last = (left-x0)//480, (right-x0)//480
            require(not any(occupied[first:last]), 'overlapping original functional cells')
            occupied[first:last] = bytes([1])*(last-first); source_sites += last-first
        for left, bottom, right, top, name in macros:
            if y0+3780 <= bottom or y0 >= top: continue
            first = max(0, (left-x0)//480)
            last = min(count, (right-x0+479)//480)
            if last <= first: continue
            require(not any(occupied[first:last]), 'original functional cell overlaps actual macro exclusion')
            occupied[first:last] = bytes([2])*(last-first); blocked_sites += last-first
            # This is a physical-spacer keepout, not permission to displace or
            # mask a preexisting functional cell. Preserve those old cells and
            # their remaining original process obligations explicitly.
            extra_first = max(0, first-macro_left_extra_sites)
            for index in range(extra_first, first):
                if not occupied[index]: occupied[index] = 2; blocked_sites += 1
            for cell_left, cell_right, cell_name in cells:
                if cell_left < x0+first*480 and cell_right > x0+extra_first*480:
                    preserved_left_cells.add(cell_name)
            extra_last = min(count, last+macro_right_extra_sites)
            for index in range(last, extra_last):
                if not occupied[index]: occupied[index] = 2; blocked_sites += 1
            for cell_left, cell_right, cell_name in cells:
                if cell_left < x0+extra_last*480 and cell_right > x0+last*480:
                    preserved_keepout_cells.add(cell_name)
        start = 0
        while start < count:
            if occupied[start]: start += 1; continue
            end = start
            while end < count and not occupied[end]: end += 1
            cursor = start
            for size in (8, 4, 2, 1):
                while end-cursor >= size:
                    x = x0+480*cursor
                    fill.append({'name': f'task009_row_fill_{len(fill):06d}', 'master': f'sg13g2_fill_{size}',
                                 'location': [x, y0], 'origin': [x, y0+(3780 if row['orientation'] == 'MX' else 0)],
                                 'orientation': row['orientation'], 'row': row['name'], 'sites': size})
                    cursor += size
            require(cursor == end, 'unfilled native row site')
            start = end
    result = {'schema': 'lemma-original-row-filler-plan/'+('3' if macro_left_extra_sites else '2' if macro_right_extra_sites else '1'),
            'status': 'PLANNED_ORIGINAL_PHYSICAL_SPACERS_NOT_PLACED',
            'rows': rows, 'functional_instances': len(functional), 'macro_instances': len(macros),
            'all_row_sites': sum(row['sites'] for row in rows), 'functional_sites': source_sites,
            'outward_rounded_macro_sites': blocked_sites, 'filler_sites': sum(cell['sites'] for cell in fill),
            'fillers': fill, 'functional_placements_changed': 0, 'functional_padding_nm': 960,
            'physical_spacers_may_occupy_reserved_functional_padding': True,
            'remaining': ['actual original filler FEOL/PG source relation', 'native insertion and PG connectivity',
                          'signal/PG/OBS collision relation', 'complete original process rules and connected LVS']}
    if macro_right_extra_sites:
        result['macro_right_well_keepout'] = {'extra_sites': 2, 'site_nm': 480,
            'actual_macro_right_nm': 904480, 'original_filler_well_overhang_nm': 240,
            'original_NW_b_spacing_nm': 620, 'minimum_filler_bbox_left_nm': 905340,
            'actual_first_filler_bbox_left_nm': 905760, 'new_well_gap_nm': 1040,
            'preserved_functional_cells_in_spacer_keepout': sorted(preserved_keepout_cells),
            'scope': 'Actual322 macro-right seam correction; other fullprocess/LVS obligations remain'}
    if macro_left_extra_sites:
        result['macro_left_clearance_keepout'] = {'extra_sites': 2, 'site_nm': 480,
            'actual_macro_left_nm': 120000, 'original_SRAM_Metal1_left_local_nm': 60,
            'original_SRAM_NWell_left_local_nm': 0, 'original_filler_NWell_overhang_nm': 240,
            'maximum_filler_bbox_right_nm': 119040, 'minimum_Metal1_gap_nm': 1020,
            'minimum_NWell_gap_nm': 720, 'original_NW_b_spacing_nm': 620,
            'declared_conservative_Metal1_spacing_nm': 220,
            'preserved_functional_cells_in_spacer_keepout': sorted(preserved_left_cells),
            'scope': 'Exact original source extent correction for new left-edge spacer clearance; full process and six old right-edge wells remain'}
    return result


def signal_wire_identity(block):
    """Exact native wire opcode/data stream, including RECT, via and ITerm IDs."""
    result = {}
    for net in block.getNets():
        wire = net.getWire()
        if wire is None: continue
        digest = hashlib.sha256()
        for index in range(wire.length()):
            digest.update(struct.pack('<Bi', wire.getOpcode(index), wire.getData(index)))
        result[net.getName()] = (wire.length(), digest.hexdigest())
    return result


def insert_original_fillers(source, plan_path, output):
    """Pinned host-OpenDB correction; never routes or moves a functional cell.

    Execute only under the ordinary bounded EDA owner. The result is a separate
    unfinished physical candidate, not a replacement timing/process receipt.
    """
    import odb
    from silicon_acceptance_launch import snapshot
    from silicon_synth import sha
    source, plan_path, output = map(Path, (source, plan_path, output))
    plan_sha = sha(plan_path)
    unrouted = filler_source_pair(sha(source),plan_sha)
    plan = json.loads(plan_path.read_text())
    bilateral = plan_sha in (BILATERAL_KEEPOUT_PLAN_SHA,REPAIRED_BILATERAL_PLAN_SHA)
    keepout = bilateral or plan_sha == RIGHT_KEEPOUT_PLAN_SHA
    require(plan['schema'] == 'lemma-original-row-filler-plan/'+('3' if bilateral else '2' if keepout else '1') and
            plan['status'] == 'PLANNED_ORIGINAL_PHYSICAL_SPACERS_NOT_PLACED' and
            (plan['functional_instances'], plan['macro_instances'], len(plan['rows']),
             plan['all_row_sites'], plan['functional_sites'], plan['outward_rounded_macro_sites'],
             plan['filler_sites'], len(plan['fillers'])) ==
            ((9034, 3, 221, 478686, 69106, 160620, 248960, 40247) if unrouted else
             (9034, 3, 221, 478686, 69106, 160596, 248984, 40264) if bilateral else
             (9034, 3, 221, 478686, 69106, 160419, 249161, 40336) if keepout else
             (9034, 3, 221, 478686, 69106, 160230, 249350, 40349)),
            'exact selected all-row filler coverage required')
    output.mkdir(exist_ok=False)
    db = odb.dbDatabase.create(); odb.read_db(db, str(source))
    block = db.getChip().getBlock()
    before = snapshot(block); wires = signal_wire_identity(block)
    require(len(wires) == (0 if unrouted else 9703),'fresh32-move source must remain completely unrouted; selected source must retain original routes')
    require(len(before[1]) == 9037 and len(before[2]) == 668 and sum(before[3].values()) == 99128 and
            len(before[4]) == 18718 and not any(name.startswith('task009_row_fill_') for name in before[1]),
            'actual selected functional/macro/port/PG/OBS inventory differs')
    masters = {}
    for sites in (1, 2, 4, 8):
        name = 'sg13g2_fill_'+str(sites)
        matches = [lib.findMaster(name) for lib in db.getLibs() if lib.findMaster(name)]
        require(len(matches) == 1, 'original filler native master identity')
        master = matches[0]
        require((master.getWidth(), master.getHeight(), master.getType()) == (480*sites, 3780, 'CORE_SPACER') and
                {term.getName(): term.getSigType() for term in master.getMTerms()} ==
                {'VDD': 'POWER', 'VSS': 'GROUND'}, 'original native physical-only filler/PG type')
        masters[name] = master
    # Correct net names alone do not prove physical connection. Each new PG
    # pin must overlap its immutable existing native row rail. Full original
    # GDS metal spacing is a separate following check.
    rails = {}
    for net, layer, left, bottom, right, top in before[3]:
        if layer == 'Metal1': rails.setdefault(net, []).append((left, bottom, right, top))
    def validate_cell(record, cell):
        require(cell is not None and cell.getMaster().getName() == record['master'] and
                cell.getOrient() == record['orientation'] and list(cell.getLocation()) == record['location'] and
                list(cell.getOrigin()) == record['origin'], 'new physical filler master/site/orientation differs')
        if keepout and record['location'][0] >= 904480 and any(
                record['location'][1] < bottom+118780 and record['location'][1]+3780 > bottom
                for bottom in (100000, 350000, 600000)):
            require(record['location'][0]-240-904480 >= 620, 'new original filler violates actual macro NWell spacing')
        bbox_right = record['location'][0]+cell.getMaster().getWidth()
        if bilateral and bbox_right <= 120000 and any(
                record['location'][1] < bottom+118780 and record['location'][1]+3780 > bottom
                for bottom in (100000, 350000, 600000)):
            require(120000-(bbox_right+240) >= 620 and 120060-bbox_right >= 220,
                    'new original filler violates actual left NWell or Metal1 spacing')
        require({pin.getMTerm().getName() for pin in cell.getITerms()} == {'VDD', 'VSS'},
                'filler has unexpected signal pin')
        for pin in cell.getITerms():
            net = {'VDD': 'VDDlogic', 'VSS': 'VSS'}[pin.getMTerm().getName()]
            require(pin.getNet() is not None and pin.getNet().getName() == net, 'actual filler supply changed')
            shapes = list(pin.getGeometries())
            require(shapes and all(layer.getName() == 'Metal1' for layer, box in shapes),
                    'original filler row-rail interface differs')
            for layer, box in shapes:
                require(any(min(right, box.xMax()) > max(left, box.xMin()) and
                            min(top, box.yMax()) > max(bottom, box.yMin())
                            for left, bottom, right, top in rails[net]), 'filler PG pin misses actual native row rail')
    for record in plan['fillers']:
        require(block.findInst(record['name']) is None and record['master'] in masters,
                'duplicate/unqualified filler instance')
        cell = odb.dbInst_create(block, masters[record['master']], record['name'])
        cell.setOrient(record['orientation']); cell.setLocation(*record['location']); cell.setPlacementStatus('PLACED')
        cell.findITerm('VDD').connect(block.findNet('VDDlogic')); cell.findITerm('VSS').connect(block.findNet('VSS'))
        validate_cell(record, cell)
    after = snapshot(block)
    names = {record['name'] for record in plan['fillers']}
    require(len(names) == len(plan['fillers']) and set(after[1]) == set(before[1]) | names and
            {name: value for name, value in after[1].items() if name not in names} == before[1] and
            {key: value for key, value in after[0].items() if key[0] not in names} == before[0] and
            after[2:] == before[2:] and len(after[0]) == len(before[0])+2*len(names),
            'old functional/test/supply terminals, placement, nativePG, OBS or ports changed')
    require(signal_wire_identity(block) == wires, 'actual original signal wire opcode/RECT/via stream changed')
    negatives = []
    record = plan['fillers'][0]; cell = block.findInst(record['name'])
    for label in ('wrong_site', 'wrong_orientation', 'wrong_supply'):
        if label == 'wrong_site': cell.setLocation(record['location'][0]+480, record['location'][1])
        elif label == 'wrong_orientation':
            cell.setOrient('MX' if record['orientation'] == 'R0' else 'R0'); cell.setLocation(*record['location'])
        else: cell.findITerm('VDD').connect(block.findNet('VSS'))
        try: validate_cell(record, cell)
        except ValueError: negatives.append(label)
        else: raise ValueError('consequential actual filler negative admitted: '+label)
        cell.setOrient(record['orientation']); cell.setLocation(*record['location'])
        cell.findITerm('VDD').connect(block.findNet('VDDlogic')); validate_cell(record, cell)
    if keepout:
        # Exercise the actual observed unsafe seam independently of the exact
        # placement relation: the altered record and instance agree, but its
        # original well overhang leaves only80nm to the SRAM well edge.
        record = next(record for record in plan['fillers']
                      if record['location'][0] == 905760 and any(
                          record['location'][1] < bottom+118780 and record['location'][1]+3780 > bottom
                          for bottom in (100000, 350000, 600000)))
        cell = block.findInst(record['name'])
        unsafe = dict(record, location=[record['location'][0]-960, record['location'][1]],
                      origin=[record['origin'][0]-960, record['origin'][1]])
        cell.setLocation(*unsafe['location'])
        try: validate_cell(unsafe, cell)
        except ValueError as error:
            require(str(error) == 'new original filler violates actual macro NWell spacing',
                    'macro-right negative did not exercise the actual original well rule')
            negatives.append('actual_macro_right_80nm_well_gap')
        else: raise ValueError('actual unsafe macro-right spacer admitted')
        cell.setLocation(*record['location']); validate_cell(record, cell)
    if bilateral:
        record = next(record for record in plan['fillers']
                      if record['location'][0]+masters[record['master']].getWidth() == 119040 and any(
                          record['location'][1] < bottom+118780 and record['location'][1]+3780 > bottom
                          for bottom in (100000, 350000, 600000)))
        cell = block.findInst(record['name'])
        unsafe = dict(record, location=[record['location'][0]+480, record['location'][1]],
                      origin=[record['origin'][0]+480, record['origin'][1]])
        cell.setLocation(*unsafe['location'])
        try: validate_cell(unsafe, cell)
        except ValueError as error:
            require(str(error) == 'new original filler violates actual left NWell or Metal1 spacing',
                    'macro-left negative did not exercise actual source spacing')
            negatives.append('actual_macro_left_240nm_well_gap')
        else: raise ValueError('actual unsafe macro-left spacer admitted')
        cell.setLocation(*record['location']); validate_cell(record, cell)
    if unrouted:
        wire_net = next(net for net in block.getNets() if net.getSigType() not in ('POWER','GROUND'))
        wire = odb.dbWire_create(wire_net)
        require(signal_wire_identity(block) != wires,'new unadmitted signal route negative admitted')
        negatives.append('new_unadmitted_signal_wire'); odb.dbWire_destroy(wire)
    else:
        wire_net = next(net for net in block.getNets() if net.getWire() is not None)
        wire = wire_net.getWire(); wire.detach()
        require(signal_wire_identity(block) != wires, 'detached actual routed wire negative admitted')
        negatives.append('detached_actual_signal_wire'); wire.attach(wire_net)
    require(signal_wire_identity(block) == wires, 'negative did not restore exact native route')
    require(snapshot(block) == after, 'negative did not restore every placement/terminal/PG/port/OBS record')
    odb.write_db(db, str(output/'filled.odb')); odb.write_def(block, str(output/'filled.def'))
    result = {'status': 'PASS_ORIGINAL_ALLROW_FILLER_NATIVE_PLACEMENT_PG_OVERLAP_SIGNALS_UNCHANGED_NOT_PROCESS_DRC',
              'source_odb_sha256': sha(source), 'plan_sha256': sha(plan_path),
              'filled_odb_sha256': sha(output/'filled.odb'), 'filled_def_sha256': sha(output/'filled.def'),
              'old_placements_preserved': len(before[1]), 'old_ports_preserved': len(before[2]),
              'old_native_PG_shapes_preserved': sum(before[3].values()), 'old_OBS_preserved': len(before[4]),
              'original_signal_wire_streams_preserved': len(wires), 'explicitly_unrouted32_move_source':unrouted, 'original_fillers_added': len(names),
              'new_PG_terminals': 2*len(names), 'native_pin_correct_rail_overlap': True,
              'macro_right_spacer_keepout': plan.get('macro_right_well_keepout'),
              'macro_left_spacer_keepout': plan.get('macro_left_clearance_keepout'),
              'functional_padding_policy': 'Original960nm functional-cell separation remains; physical spacers fill unused sites',
              'negative_cases': negatives,
              'remaining': ['original GDS filler masks and all partial NW.b findings', 'new PG/signal geometry clearance',
                            'full original process rules', 'connected LVS', 'post-fill extraction/timing scope', 'IR/EM']}
    (output/'insertion.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def original_filler_probe(config, source_layouts, expected):
    """Read-only original-cell geometry on already observed partial NW.b gaps.

    Nothing is placed in the product database. This establishes the exact next
    row-well predecessor without treating a partial process report as complete.
    """
    import pya
    report = ET.parse(config['partial_process_report']).getroot()
    require(report.tag == 'report-database' and report.findtext('top-cell') == expected['top'],
            'actual selected-layout partial process report required')
    examples = [item.findtext('./values/value') for item in report.findall('./items/item')
                if item.findtext('category', '').strip("'") == 'NW.b']
    require(examples, 'actual partial NW.b findings required')
    lef = Path(config['lef_files'][1]).read_text()
    sizes = {}
    for name, body in re.findall(r'^MACRO (\S+)\n(.*?)^END \1$', lef, re.M|re.S):
        size = re.search(r'(?m)^\s*SIZE ([\d.]+) BY ([\d.]+) ;', body)
        require(size is not None, 'original standard-cell LEF size')
        sizes[name] = tuple(int(Decimal(value)*1000) for value in size.groups())
    def original_cell(name):
        matches = [(ly, ly.cell(name)) for ly in source_layouts if ly.cell(name) is not None]
        require(len(matches) == 1, 'exact original filler/standard-cell master required')
        return matches[0]
    @lru_cache(maxsize=None)
    def well(name):
        ly, cell = original_cell(name)
        layer = ly.find_layer(31, 0)
        require(layer is not None, 'original NWell31/0 required')
        region = pya.Region(cell.begin_shapes_rec(layer)); region.merge()
        return region
    filler = []
    for name in ('sg13g2_fill_1', 'sg13g2_fill_2', 'sg13g2_fill_4', 'sg13g2_fill_8'):
        ly, cell = original_cell(name)
        geometry = []
        for layer in ly.layer_indexes():
            info = ly.get_info(layer)
            for shape in cell.shapes(layer).each():
                geometry.append({'layer_datatype': [info.layer, info.datatype], 'shape': shape.to_s()})
        body = re.search(r'^MACRO '+name+r'\n(.*?)^END '+name+'$', lef, re.M|re.S)[1]
        require('CLASS CORE SPACER' in body and re.findall(r'^  PIN (\S+)', body, re.M) == ['VDD', 'VSS'],
                'original physical spacer with both PG pins required')
        require(not well(name).is_empty(), 'original source filler NWell required')
        filler.append({'master': name, 'LEF_size_nm': sizes[name],
                       'NWell_local_polygons_nm': [str(p) for p in well(name).each()],
                       'original_master_sha256': fingerprint(ly, cell), 'original_all_layer_geometry': geometry})
    orientation = {'R0': (0, False), 'MX': (0, True), 'MY': (180, True), 'R180': (180, False)}
    placed = []
    for inst in expected['instances']:
        if inst['master'] not in sizes or inst['orientation'] not in orientation: continue
        a, mirror = orientation[inst['orientation']]
        transform = pya.ICplxTrans(1, a, mirror, *inst['origin'])
        region = well(inst['master']).transformed(transform)
        if region.is_empty(): continue
        placed.append((inst, region, region.bbox()))
    rows = []
    for raw in examples[:3]:
        values = [int(Decimal(value)*1000) for value in re.findall(r'-?\d+(?:\.\d+)?', raw)]
        require(len(values) == 8 and values[0] == values[2] and values[4] == values[6], 'vertical partial NW.b example')
        left, right = sorted((values[0], values[4]))
        lower, upper = max(min(values[1:4:2]), min(values[5:8:2])), min(max(values[1:4:2]), max(values[5:8:2]))
        pairs = []
        for a, ar, aw in placed:
            if aw.right != left or aw.bottom > lower or aw.top < upper: continue
            for b, br, bw in placed:
                if bw.left != right or bw.bottom > lower or bw.top < upper: continue
                if a['location'][1] != b['location'][1] or a['orientation'] != b['orientation']: continue
                gap = b['location'][0]-(a['location'][0]+sizes[a['master']][0])
                if gap != 960: continue
                pairs.append((a, ar, aw, b, br, bw))
        require(len(pairs) == 1, 'unique original same-row960nm functional gap required')
        a, ar, aw, b, br, bw = pairs[0]
        x, y = a['location'][0]+sizes[a['master']][0], a['location'][1]
        require(sizes['sg13g2_fill_2'] == (960, 3780), 'original exact2site spacer size')
        angle, mirror = orientation[a['orientation']]
        origin = (x, y+3780) if mirror else (x, y)
        fill_well = well('sg13g2_fill_2').transformed(pya.ICplxTrans(1, angle, mirror, *origin))
        corridor = pya.Region(pya.Box(left, lower, right, upper))
        require((corridor-fill_well).is_empty() and (corridor-(ar+br)).area() > 0 and
                not (fill_well & ar).is_empty() and not (fill_well & br).is_empty(),
                'actual source filler must bridge both separated original wells')
        wrong_site = fill_well.transformed(pya.ICplxTrans(1, 0, False, 960, 0))
        wrong_orientation = well('sg13g2_fill_2').transformed(
            pya.ICplxTrans(1, angle, not mirror, x, y if mirror else y+3780))
        require(not corridor.is_empty() and not (corridor-wrong_site).is_empty() and
                not (corridor-wrong_orientation).is_empty(),
                'missing/wrong-site/wrong-orientation original filler negatives must reject')
        rows.append({'partial_original_edge_pair': raw, 'left_owner': a, 'right_owner': b,
                     'left_NWell_nm': str(aw), 'right_NWell_nm': str(bw), 'well_gap_nm': right-left,
                     'functional_bbox_gap_nm': 960, 'proposed_original_fill_2_origin_nm': origin,
                     'proposed_orientation': a['orientation'],
                     'fill_NWell_polygons_nm': [str(p) for p in fill_well.each()],
                     'source_filler_covers_actual_gap': True,
                     'negative_cases': ['missing_filler', 'shifted_one_gap', 'opposite_row_orientation']})
    return {'status': 'OBSERVED_ORIGINAL_FILLER_WELL_BRIDGE_GEOMETRY_ONLY_NOT_PLACED',
            'partial_report_NW_b_findings': len(examples), 'partial_report_is_not_full_DRC': True,
            'original_filler_sources': filler, 'first_3_actual_gap_bridges': rows,
            'not_checked': ['native filler placement/padding policy', 'actual filler PG connection',
                            'new signal/PG/OBS collisions', 'full process rules', 'LVS', 'timing']}


def macro_well_move_plan(def_text, expected, masters, owner_geometry):
    """Plan only the one-site repairs forced by actual old macro well edges.

    Neighbor propagation preserves the original960nm functional padding. This
    does not move a native cell or preserve stale routed endpoint geometry.
    """
    # Reuse the maintained actual-row/grid/macro/padding admission.
    rows = all_row_plan(def_text, expected, masters)['rows']
    require(owner_geometry['status'] == 'PASS_EXACT_ORIGINAL_FUNCTIONAL_SOURCE_OWNERS_OF93_NWELL_EDGES_NOT_MOVED'
            and len(owner_geometry['markers']) == 93, 'exact original source-owner proof required')
    source = {cell['name']: cell for cell in expected['instances']}
    shifts = {}; reasons = {}
    for marker in owner_geometry['markers']:
        require(marker['side'] in ('left', 'right'), 'unknown macro well side')
        delta = -480 if marker['side'] == 'left' else 480
        for owner in marker['source_edge_owners']:
            name = owner['instance']; require(name in source, 'missing original well owner')
            require(name not in shifts or shifts[name] == delta, 'conflicting source well directions')
            shifts[name] = delta; reasons[name] = 'actual_original_NW_b_source_owner'
    require(len(shifts) == 24 and sum(delta < 0 for delta in shifts.values()) == 18,
            'exact eighteen left and six right source owners required')
    by_y = {row['y_nm']: [] for row in rows}
    for cell in expected['instances']:
        if masters[cell['master']]['class'] == 'CORE': by_y[cell['location'][1]].append(cell)
    for cells in by_y.values(): cells.sort(key=lambda cell: cell['location'][0])
    changed = True
    while changed:
        changed = False
        for cells in by_y.values():
            for a, b in zip(cells, cells[1:]):
                old_gap = b['location'][0]-a['location'][0]-masters[a['master']]['size_nm'][0]
                require(old_gap >= 960, 'original functional padding differs')
                da, db = shifts.get(a['name'], 0), shifts.get(b['name'], 0)
                if old_gap+db-da >= 960: continue
                if db == -480 and da == 0: name, delta = a['name'], -480
                elif da == 480 and db == 0: name, delta = b['name'], 480
                else: raise ValueError('one-site well shifts require a different placement solution')
                shifts[name] = delta; reasons[name] = 'required_original960nm_padding_neighbor'; changed = True
    moved = []
    row_by_y = {row['y_nm']: row for row in rows}
    for name, delta in sorted(shifts.items()):
        old = source[name]; width, height = masters[old['master']]['size_nm']; x, y = old['location']; row = row_by_y[y]
        require(height == 3780 and row['x_nm'] <= x+delta and x+delta+width <= row['x_nm']+row['sites']*480,
                'well repair leaves original core sites')
        moved.append({'name': name, 'master': old['master'], 'orientation': old['orientation'],
            'from_location': old['location'], 'to_location': [x+delta, y], 'from_origin': old['origin'],
            'to_origin': [old['origin'][0]+delta, old['origin'][1]], 'delta_x_nm': delta, 'reason': reasons[name]})
    require(len(moved) == 32 and sum(record['reason'].endswith('padding_neighbor') for record in moved) == 8,
            'exact minimal one-site neighbor propagation differs')
    return {'schema': 'lemma-original-macro-well-move-plan/1',
        'status': 'PLANNED_SOURCE_BOUND32_FUNCTIONAL_SITE_MOVES_NOT_APPLIED',
        'moves': moved, 'functional_padding_nm': 960, 'original_source_owners': 24,
        'forced_padding_neighbors': 8, 'functional_cells_moved': 32,
        'clock_related_instances': sorted(name for name in shifts if name.startswith(('clkbuf', 'clkload'))),
        'scope': 'Source placement plan only; originalnetlist/ports/capacity unchanged. Any native application must remove stale signal routing and require fresh route/extraction/all9timing/process checks.'}


def place_macro_well_repairs(source, plan_path, native_instances, output):
    """Apply the exact32 source-proved site moves; explicitly invalidate routing."""
    import odb
    from collections import defaultdict
    from silicon_acceptance_launch import snapshot
    from silicon_sram_input_hold import padding
    from silicon_synth import sha
    source, plan_path, native_instances, output = map(Path, (source, plan_path, native_instances, output))
    require(sha(source) == SELECTED_SOURCE_ODB and
            sha(plan_path) == 'eacc87505e6baf3a8de4baac059c10bcb0fc6c60d5fac4ac7d7fc94b160f0b00' and
            sha(native_instances) == '0964432c4d7e79e4c56b197a1ea01c581065ad531bdc035ae87a019d74700b0b',
            'exact selected0.6 source/32-site plan/native inventory required')
    plan = json.loads(plan_path.read_text()); original = json.loads(native_instances.read_text())
    output.mkdir(exist_ok=False)
    db = odb.dbDatabase.create(); odb.read_db(db, str(source)); block = db.getChip().getBlock()
    before = snapshot(block); wires = signal_wire_identity(block)
    require(before[1] == {cell['name']: (cell['master'], cell['orientation'], tuple(cell['location']))
                          for cell in original['instances']} and len(before[1]) == 9037 and
            len(before[2]) == 668 and sum(before[3].values()) == 99128 and len(before[4]) == 18718 and len(wires) == 9703,
            'original functional/macro/port/PG/OBS/wire inventory changed')
    shifts = {record['name']: record['delta_x_nm'] for record in plan['moves']}
    require(len(shifts) == 32 and all(delta in (-480, 480) for delta in shifts.values()), 'exact32 one-site moves')
    for record in plan['moves']:
        cell = block.findInst(record['name'])
        require(cell is not None and cell.getMaster().getName() == record['master'] and
                cell.getOrient() == record['orientation'] and list(cell.getLocation()) == record['from_location'] and
                list(cell.getOrigin()) == record['from_origin'], 'original native moved-cell identity differs')
        cell.setLocation(*record['to_location'])
        require(list(cell.getOrigin()) == record['to_origin'], 'native move changed orientation/origin relation')
    expected_instances = {name: (master, orient, (location[0]+shifts.get(name, 0), location[1]))
                          for name, (master, orient, location) in before[1].items()}
    expected_terms = {key: (net, [(layer, a+shifts.get(key[0], 0), c, d+shifts.get(key[0], 0), e)
                                        for layer, a, c, d, e in boxes])
                      for key, (net, boxes) in before[0].items()}
    def validate():
        after = snapshot(block)
        require(after[0] == expected_terms and after[1] == expected_instances and after[2:] == before[2:],
                'native placement changed beyond exact32 x-translations, or signal/BIST/power/port/PG/OBS changed')
        result = padding(block)
        require(result['stdcells'] == 9034, 'functional inventory changed')
        return after, result
    after, pad = validate()
    macros = [cell.getBBox() for cell in block.getInsts() if cell.getMaster().getType() == 'BLOCK']
    require(len(macros) == 3, 'three unchanged full-depth SRAM macros')
    rails = defaultdict(list); pg_buckets = defaultdict(list)
    for (net, layer, a, c, d, e), count in before[3].items():
        if layer == 'Metal1': rails[net].append((a, c, d, e))
        if layer in ('Metal2', 'Metal3', 'Metal4', 'Metal5'):
            for xx in range((a-420)//50000, (d+420)//50000+1):
                for yy in range((c-420)//50000, (e+420)//50000+1):
                    pg_buckets[layer, xx, yy].append((a-420, c-420, d+420, e+420))
    # Include the actual fixed SRAM power-pin footprints as well as its
    # routed supply metal; a long pin rectangle is not an invisible obstacle.
    for macro in block.getInsts():
        if macro.getMaster().getType() != 'BLOCK': continue
        for term in macro.getITerms():
            if term.getSigType() not in ('POWER', 'GROUND'): continue
            for layer, q in term.getGeometries():
                if layer.getName() not in ('Metal2', 'Metal3', 'Metal4', 'Metal5'): continue
                a, c, d, e = q.xMin(), q.yMin(), q.xMax(), q.yMax()
                for xx in range((a-420)//50000, (d+420)//50000+1):
                    for yy in range((c-420)//50000, (e+420)//50000+1):
                        pg_buckets[layer.getName(), xx, yy].append((a-420, c-420, d+420, e+420))
    moved_PG_pins = checked_signal_pins = 0
    for name in shifts:
        cell = block.findInst(name); box = cell.getBBox()
        require(not any(min(box.xMax(), m.xMax()) > max(box.xMin(), m.xMin()) and
                        min(box.yMax(), m.yMax()) > max(box.yMin(), m.yMin()) for m in macros),
                'moved functional cell enters a fixed SRAM macro')
        for term in cell.getITerms():
            if term.getSigType() in ('POWER', 'GROUND'):
                require(term.getNet() is not None and term.getNet().getName() in ('VDDlogic', 'VSS'),
                        'moved cell supply changed')
                require(any(layer.getName() == 'Metal1' and
                            any(min(q.xMax(), d) > max(q.xMin(), a) and min(q.yMax(), e) > max(q.yMin(), c)
                                for a, c, d, e in rails[term.getNet().getName()])
                            for layer, q in term.getGeometries()), 'moved PG terminal misses its real native row rail')
                moved_PG_pins += 1
            else:
                for layer, q in term.getGeometries():
                    if layer.getName() not in ('Metal2', 'Metal3', 'Metal4', 'Metal5'): continue
                    a, c, d, e = q.xMin(), q.yMin(), q.xMax(), q.yMax()
                    for xx in range(a//50000, d//50000+1):
                        for yy in range(c//50000, e//50000+1):
                            require(not any(min(d, z) > max(a, x) and min(e, w) > max(c, y)
                                            for x, y, z, w in pg_buckets[layer.getName(), xx, yy]),
                                    'moved real signal pin enters original420nm native PG clearance')
                    checked_signal_pins += 1
    negatives = []
    neighbor = next(record for record in plan['moves'] if record['reason'].endswith('padding_neighbor'))
    cell = block.findInst(neighbor['name']); cell.setLocation(*neighbor['from_location'])
    try: padding(block)
    except ValueError: negatives.append('omit_actual_forced_padding_neighbor')
    else: raise ValueError('missing required original-padding neighbor move admitted')
    cell.setLocation(*neighbor['to_location']); validate()
    owner = next(record for record in plan['moves'] if record['reason'].endswith('source_owner'))
    cell = block.findInst(owner['name']); cell.setLocation(owner['to_location'][0]+480, owner['to_location'][1])
    try: validate()
    except ValueError: negatives.append('actual_well_owner_wrong_site')
    else: raise ValueError('wrong actual source-owner site admitted')
    cell.setLocation(*owner['to_location']); validate()
    pin = cell.findITerm('VDD'); require(pin is not None, 'actual moved original supply pin')
    saved = pin.getNet(); pin.connect(block.findNet('VSS'))
    try: validate()
    except ValueError: negatives.append('actual_moved_cell_wrong_supply')
    else: raise ValueError('wrong moved-cell supply admitted')
    pin.connect(saved); validate()
    # A placement repair cannot inherit old wire coordinates. All real
    # signal/clock routes are removed explicitly; the three native PG special
    # wires and every original endpoint/net binding remain unchanged.
    removed = 0
    for net in block.getNets():
        wire = net.getWire()
        if wire is not None:
            require(net.getSigType() not in ('POWER', 'GROUND'), 'unexpected nonspecial PG route')
            odb.dbWire_destroy(wire); removed += 1
    require(removed == 9703 and not signal_wire_identity(block), 'stale signal/clock routing remains')
    final, pad = validate()
    require(final == after, 'negative controls or route invalidation changed physical endpoint/PG state')
    odb.write_db(db, str(output/'unrouted.odb')); odb.write_def(block, str(output/'unrouted.def'))
    updated = json.loads(native_instances.read_text())
    for cell in updated['instances']:
        if cell['name'] in shifts:
            cell['location'][0] += shifts[cell['name']]; cell['origin'][0] += shifts[cell['name']]
    (output/'instances.json').write_text(json.dumps(updated, indent=2)+'\n')
    result = {'status': 'PASS_EXACT32_MACRO_WELL_SITE_REPAIRS_PG_AND_PADDING_UNROUTED_NOT_PROCESS_CLOSURE',
        'source_odb_sha256': sha(source), 'move_plan_sha256': sha(plan_path),
        'unrouted_odb_sha256': sha(output/'unrouted.odb'), 'unrouted_def_sha256': sha(output/'unrouted.def'),
        'native_instances_sha256': sha(output/'instances.json'), 'functional_cell_moves': 32,
        'source_owners': 24, 'required_padding_neighbors': 8, 'padding': pad,
        'moved_PG_terminals_with_real_rail_overlap': moved_PG_pins,
        'moved_signal_pin_shapes_checked420nm': checked_signal_pins,
        'old_ports': len(before[2]), 'old_native_PG_shapes': sum(before[3].values()), 'old_OBS': len(before[4]),
        'old_signal_clock_wire_streams_invalidated': removed,
        'all_signal_BIST_supply_bindings_and_masters_preserved': True,
        'clock_related_instances': plan['clock_related_instances'], 'negative_cases': negatives,
        'scope': 'Source-equivalent physical placement precursor only. No signal route, extraction, timing, fullprocess/LVS or selected implementation qualification.'}
    (output/'placement.json').write_text(json.dumps(result, indent=2)+'\n')
    return result
