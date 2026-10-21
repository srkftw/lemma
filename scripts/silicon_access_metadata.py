#!/usr/bin/env python3
"""Host-only admission of the bounded original OpenDB access export cohort.

This checks metadata relations, not process DRC or route feasibility. The current
cohort has planar Metal2/3 points and upward Metal1 fixed-Via1 points, no segments.
Unexpected representations fail until independently qualified.
"""
from collections import Counter
from pathlib import Path
from silicon_enclosure import read_tech

class AccessMetadataError(ValueError):
    pass

def require(value, message):
    if not value:
        raise AccessMetadataError(message)

def validate(data, tech_lef):
    require(data['schema'] == 'lemma-opendb-access-export/1', 'schema')
    require(data['db_units_per_micron'] == 1000, 'database units')
    _, _, definitions = read_tech(Path(tech_lef))
    fixed = [v for v in definitions if v['kind'] == 'fixed']
    # The qualified original LEF reader preserves the fixed-via declaration
    # order as dbTechVia object IDs. Callers bind this exact source/tool cohort.
    vias = {v['name']: (i + 1, sorted((layer, tuple((r.x0, r.y0, r.x1, r.y1)))
             for layer, rects in v['shapes'].items() for r in rects))
            for i, v in enumerate(fixed)}
    aps = {a['id']: a for a in data['access_points']}
    require(len(aps) == len(data['access_points']) and aps, 'duplicate/empty AP IDs')
    types = {'OnGrid', 'HalfGrid', 'Center', 'EncOpt', 'NearbyGrid'}
    ordered = ['NORTH', 'EAST', 'SOUTH', 'WEST', 'UP', 'DOWN']
    direction_counts, via_counts = Counter(), Counter()
    for a in aps.values():
        require(type(a['id']) is int and a['id'] > 0, 'invalid AP ID')
        require(len(a['point_nm']) == 2 and all(type(x) is int and -(1 << 31) <= x < 1 << 31 for x in a['point_nm']), 'point')
        require(a['low_type'] in types and a['high_type'] in types, 'access type')
        directions = a['directions']
        require(directions and directions == [d for d in ordered if d in directions], 'direction enumeration/order')
        require(a['segments'] == [], 'unqualified nonempty segment representation')
        groups = a['via_groups']
        if a['layer'] == 'Metal1':
            require(directions == ['UP'] and len(groups) == 1 and 1 <= len(groups[0]) <= 2, 'Metal1 via/direction binding')
            names = []
            for via in groups[0]:
                require(via['kind'] == 'tech_via' and via['name'] in ('Via1_YY', 'Via1_XY'), 'unqualified via kind/name')
                expected_id, expected_boxes = vias[via['name']]
                require(type(via['id']) is int and via['id'] == expected_id, 'original tech-via ID')
                boxes = []
                for b in via['boxes']:
                    r = b['box_nm']
                    require(len(r) == 4 and all(type(x) is int for x in r) and r[0] < r[2] and r[1] < r[3], 'via rectangle')
                    boxes.append((b['layer'], tuple(r)))
                require(sorted(boxes) == expected_boxes, 'original fixed-via geometry/layers')
                names.append(via['name']); via_counts[via['name']] += 1
            require(len(set(names)) == len(names), 'duplicate via alternative')
        else:
            require(a['layer'] in ('Metal2', 'Metal3') and groups == [] and all(d in ordered[:4] for d in directions), 'planar layer/direction binding')
        direction_counts[(a['layer'], tuple(directions))] += 1
    patterns = {}
    membership = Counter()
    for p in data['master_pin_patterns']:
        key = (p['master'], p['mterm'], p['mpin_id'])
        require(key not in patterns and p['patterns'], 'duplicate/empty pattern owner')
        patterns[key] = p['patterns']
        for group in p['patterns']:
            require(len(group) == len(set(group)), 'duplicate pattern AP')
            for i in group:
                owner = aps[i]['owner']
                require(owner == {'kind': 'master_pin', 'lib': p['lib'], 'master': p['master'], 'mterm': p['mterm'], 'mpin_id': p['mpin_id']}, 'pattern AP owner')
                membership[i] += 1
    terminals = set()
    for t in data['instance_terminals']:
        key = (t['instance'], t['terminal'])
        require(key not in terminals, 'duplicate instance terminal')
        terminals.add(key)
        require(type(t['pattern_index']) is int and t['pattern_index'] >= 0, 'negative/noninteger pattern index')
        permitted, pins = [], set()
        for group in t['access']:
            require(group['mpin_id'] not in pins, 'duplicate instance master pin')
            pins.add(group['mpin_id'])
            choices = patterns[(t['master'], t['terminal'], group['mpin_id'])]
            require(t['pattern_index'] < len(choices) and group['ids'] == choices[t['pattern_index']], 'instance pattern binding')
            permitted.extend(group['ids'])
        require(len(t['preferred']) == len(set(t['preferred'])) and all(i in permitted for i in t['preferred']), 'preferred AP binding')
    bpins = set()
    for p in data['block_terminals']:
        key = (p['terminal'], p['bpin_id'])
        require(key not in bpins, 'duplicate block pin')
        bpins.add(key)
        for i in p['access']:
            require(aps[i]['owner'] == {'kind': 'block_pin', 'bterm': p['terminal'], 'bpin_id': p['bpin_id']}, 'block pin AP binding')
            membership[i] += 1
    require(set(membership) == set(aps) and all(n == 1 for n in membership.values()), 'unbound/shared ownership of AP')
    return {'access_points': len(aps), 'master_pin_patterns': len(patterns), 'instance_terminals': len(terminals), 'block_pins': len(bpins), 'via_objects': sum(via_counts.values()), 'via_names': dict(via_counts), 'segments': 0, 'direction_classes': [{'layer': layer, 'directions': list(dirs), 'count': count} for (layer, dirs), count in sorted(direction_counts.items())]}
