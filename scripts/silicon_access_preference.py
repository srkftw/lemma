#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact two-instance host-only AP preference correction on the retained327 layout.

No cells, shared APs, via alternatives or pin-access patterns are edited. This is
an input to a later source-bound router execution, not route/process closure.
The original full baseline PA remains necessary; regeneration would erase this
preference. Run apply() in the exact pinned OpenROAD Python interpreter.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from silicon_access_metadata import validate, require
from silicon_enclosure import Rect, covers

SOURCE_ODB = 'e24b92cdd6626337461ddfb73f5ae0eef53de1f2cfd931ee46abbdc930ad8a78'
SOURCE_METADATA = '53a25b62cf9b3ca147a5c9cc97572cf7905e0492b2978984ce06823117237c03'
TECH_LEF = 'fb6f0aa5647efc822ad6551a11b57002a278d7d3f98ac20a12cb9f7a65e81d2d'
TARGETS = {'_12224_': {'net': '_05224_', 'origin': [451680, 272160], 'pin': [454440, 272565, 454790, 273125], 'OBS': [454520, 271595, 456040, 272725]},
           '_12280_': {'net': '_05266_', 'origin': [331680, 514080], 'pin': [334440, 514485, 334790, 515045], 'OBS': [334520, 513515, 336040, 514645]}}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inputs(source, metadata, tech):
    require(sha(source) == SOURCE_ODB and sha(metadata) == SOURCE_METADATA and sha(tech) == TECH_LEF, 'reviewed source identity')
    data = json.loads(Path(metadata).read_text())
    validate(data, tech)
    return data

def unused_output(source, output):
    source, output = Path(source).resolve(strict=True), Path(output)
    require(not output.exists() and not output.is_symlink(), 'existing output')
    require(output.resolve() != source, 'source/output alias')
    require(output.parent.resolve(strict=True).is_dir(), 'output directory')

def geometry(name, point):
    require(name in TARGETS and point['id'] in (1, 2, 4), 'unreviewed pin/AP')
    require(point['owner'] == {'kind': 'master_pin', 'lib': 'sg13g2_stdcell', 'master': 'sg13g2_a21o_1', 'mterm': 'A2', 'mpin_id': 1}, 'actual pin owner')
    require(point['layer'] == 'Metal1' and point['directions'] == ['UP'] and point['segments'] == [], 'actual AP binding')
    require(len(point['via_groups']) == 1 and len(point['via_groups'][0]) == 1, 'actual via alternatives')
    via = point['via_groups'][0][0]
    require(via['kind'] == 'tech_via' and via['id'] == 7 and via['name'] == 'Via1_YY', 'original fixed Via1_YY')
    t = TARGETS[name]; x, y = (u + v for u, v in zip(t['origin'], point['point_nm']))
    shapes = {b['layer']: Rect(*(value + (x if i % 2 == 0 else y) for i, value in enumerate(b['box_nm']))) for b in via['boxes']}
    require(set(shapes) == {'Metal1', 'Via1', 'Metal2'}, 'via layer binding')
    require(covers(shapes['Metal1'], [Rect(*t['pin'])]), 'Via1 outside original M1 pin')
    metal, obs = shapes['Metal2'], Rect(*t['OBS'])
    require(not (metal.x0 < obs.x1 and obs.x0 < metal.x1 and metal.y0 < obs.y1 and obs.y0 < metal.y1), 'Via1 intersects actual PG clearance')
    require(x % 480 == 0 and y % 5 == 0, 'original track/manufacturing grid')
    return {'point_nm': [x, y], 'M2_vertical_PG_clearance_nm': metal.y0 - obs.y1}

def apply(source, metadata, tech, output):
    import odb
    from silicon_acceptance_launch import snapshot
    source, metadata, tech, output = map(Path, (source, metadata, tech, output))
    unused_output(source, output)
    data = inputs(source, metadata, tech)
    aps = {a['id']: a for a in data['access_points']}
    for name in TARGETS:
        require(geometry(name, aps[4])['M2_vertical_PG_clearance_nm'] == 110, 'reviewed clearance')
    db = odb.dbDatabase.create(); odb.read_db(db, str(source))
    block = db.getChip().getBlock(); before = snapshot(block)
    point = odb.dbAccessPoint.getAccessPoint(block, 4)
    pin = point.getMPin(); master = pin.getMaster()
    require(list(point.getPoint()) == [2880, 820] and pin.getId() == 1 and pin.getMTerm().getName() == 'A2' and master.getName() == 'sg13g2_a21o_1', 'actual source AP4')
    changes = []
    # Resolve and validate the complete set before the first setter.
    resolved = []
    for name, target in TARGETS.items():
        inst = block.findInst(name); term = inst.findITerm('A2')
        require(inst.getMaster().getId() == master.getId() and inst.getMaster().getLib().getId() == master.getLib().getId() and inst.getPinAccessIdx() == 0 and inst.getOrient() == 'R0' and list(inst.getLocation()) == target['origin'], 'actual instance/pattern')
        require(term.getMTerm().getId() == pin.getMTerm().getId() and term.getNet().getName() == target['net'] and [a.getId() for a in term.getPrefAccessPoints()] == [1], 'actual original preferred binding')
        resolved.append(term)
        changes.append({'instance': name, 'terminal': 'A2', 'instance_id': inst.getId(), 'iterm_id': term.getId(), 'net_id': term.getNet().getId(), 'mpin_id': pin.getId(), 'old': 1, 'new': 4})
    for term in resolved:
        term.setAccessPoint(pin, point)
    require(snapshot(block) == before, 'fixed geometry/PG/OBS/ports/netlist changed')
    require(sha(source) == SOURCE_ODB, 'source changed before serialization')
    odb.write_db(db, str(output))
    readback = odb.dbDatabase.create(); odb.read_db(readback, str(output))
    require(snapshot(readback.getChip().getBlock()) == before, 'readback fixed geometry changed')
    for change in changes:
        term = readback.getChip().getBlock().findInst(change['instance']).findITerm('A2')
        require([a.getId() for a in term.getPrefAccessPoints()] == [4], 'preferred readback')
    # Public IDs source-bind the independent serializer check; no private memory.
    fields = {'layer_id': point.getLayer().getId(), 'lib_id': master.getLib().getId(), 'master_id': master.getId(), 'mpin_id': pin.getId(), 'bpin_id': 0}
    return {'changes': changes, 'AP4_owner_serialization_ids': fields, 'fixed_geometry_PG_OBS_ports_preserved': True, 'source_ODB_sha256': sha(source), 'candidate_ODB_sha256': sha(output)}

def metadata_relation(before, after, tech):
    require(validate(before, tech) == validate(after, tech), 'metadata counts or representations changed')
    for key in before:
        if key != 'instance_terminals':
            require(before[key] == after[key], 'shared metadata changed: ' + key)
    require(len(before['instance_terminals']) == len(after['instance_terminals']), 'instance terminal count')
    found = []
    for old, new in zip(before['instance_terminals'], after['instance_terminals']):
        expected = dict(old)
        if old['instance'] in TARGETS and old['terminal'] == 'A2':
            require(old['preferred'] == [1], 'old preference'); expected['preferred'] = [4]
            found.append((old['instance'], old['terminal']))
        require(new == expected, 'unexpected instance metadata change')
    require(set(found) == {(name, 'A2') for name in TARGETS} and len(found) == 2, 'two exact preferred changes')
    return found

def serialization_relation(old, new, changes, ids):
    """Exact pinned little-endian ODB relation, including private reverse refs.

    Source dbAccessPoint.cpp writes point, five dbIds, six bools then a dbVector
    of ITerm IDs. Source dbITerm.h writes nine32-bit fields then its pin/AP map.
    Reject ambiguous prefixes, unreviewed endian/schema or any other byte change.
    """
    require(sys.byteorder == 'little' and len(changes) == 2, 'pinned serialization platform')
    prefix = struct.pack('<iiIIIII', 2880, 820, *(ids[k] for k in ('layer_id', 'lib_id', 'master_id', 'mpin_id', 'bpin_id'))) + bytes([0, 0, 0, 0, 1, 0])
    require(old.count(prefix) == new.count(prefix) == 1, 'ambiguous AP4 serialized record')
    at = old.index(prefix) + len(prefix)
    require(new.index(prefix) + len(prefix) == at, 'AP4 record moved')
    old_count = struct.unpack_from('<I', old, at)[0]
    require(old_count <= 45104, 'reverse reference count bound')
    end = at + 4 + 4 * old_count
    original_ids = list(struct.unpack_from('<' + 'I' * old_count, old, at + 4))
    appended = [c['iterm_id'] for c in changes]
    require(all(i not in original_ids for i in appended) and len(set(appended)) == 2, 'unexpected old reverse references')
    expect = old[:at] + struct.pack('<I', old_count + 2) + old[at + 4:end] + struct.pack('<II', *appended) + old[end:]
    require(len(expect) == len(new), 'unexpected serialization length')
    diffs = [i for i, (a, b) in enumerate(zip(expect, new)) if a != b]
    require(len(diffs) == 2, 'unexpected serialized field differences')
    bound = []
    for offset in diffs:
        require(expect[offset:offset + 4] == struct.pack('<I', 1) and new[offset:offset + 4] == struct.pack('<I', 4), 'preferred word change')
        require(expect[offset - 8:offset] == struct.pack('<II', 1, 1), 'single pin/AP map binding')
        net, inst = struct.unpack_from('<II', expect, offset - 36)
        matches = [c for c in changes if c['net_id'] == net and c['instance_id'] == inst]
        require(len(matches) == 1, 'serialized preferred instance/net binding')
        bound.append(matches[0]['instance'])
    require(set(bound) == set(TARGETS) and len(bound) == 2, 'two serialized instance fields')
    return {'AP4_reverse_refs_before': old_count, 'AP4_reverse_refs_appended': appended, 'AP4_reverse_vector_offset': at, 'preferred_word_offsets': diffs, 'other_bytes_identical': True, 'ODB_length_delta': len(new) - len(old)}
