#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cover the demonstrated router fixed-via enclosure gap on actual DEF routes.

Checks intrinsic fixed-via metal/cut unions against the original process simple
enclosure rules. Additional same-net wire metal can only increase enclosure.
Generated DEF arrays require explicit admission against the original generator
and every individual cut's enclosure. Unfamiliar clauses fail closed. This is
an independent sufficient check of this subset, never complete process DRC.
"""
from pathlib import Path
import argparse
import json
import re
from collections import Counter
from silicon_enclosure import Rect, check_fixed, file_sha, read_tech, require


def generated_arrays(source, layers, vias):
    """Resolve the exact OpenROAD DEF5.8 zero-origin generated-array subset."""
    section = re.search(r'^[ \t]*VIAS\s+(\d+)\s*;(.*?)^[ \t]*END VIAS\s*$', source, re.M | re.S)
    if section is None:
        require(not re.search(r'^[ \t]*VIAS\b', source, re.M), 'incomplete generated DEF vias')
        return []
    records = [r.strip() for r in section[2].split(';') if r.strip()]
    require(len(records) == int(section[1]) and len(records) <= 1024, 'generated DEF via count differs')
    generators = {v['name']: v for v in vias if v['kind'] == 'generated'}
    names = {v['name'] for v in vias}
    result = []
    pattern = (r'-\s+(\S+)\s+\+ VIARULE (\S+)\s+\+ CUTSIZE (\d+) (\d+)\s+'
               r'\+ LAYERS (\S+) (\S+) (\S+)\s+\+ CUTSPACING (\d+) (\d+)\s+'
               r'\+ ENCLOSURE (\d+) (\d+) (\d+) (\d+)\s+\+ ROWCOL (\d+) (\d+)')
    for record in records:
        match = re.fullmatch(pattern, record)
        require(match is not None, 'unsupported generated DEF via clauses')
        name, rule = match[1], match[2]
        require(name not in names and rule in generators, 'shadowed/unknown generated DEF via')
        names.add(name)
        gen = generators[rule]
        lower, cut, upper = match[5], match[6], match[7]
        require((lower, cut, upper) == (gen['lower'], gen['cut'], gen['upper']), 'generated DEF layer binding differs')
        cw, ch = int(match[3]), int(match[4])
        sx, sy = int(match[8]), int(match[9])
        ex1, ey1, ex2, ey2 = (int(match[i]) for i in range(10, 14))
        rows, cols = int(match[14]), int(match[15])
        require(1 <= rows <= 256 and 1 <= cols <= 256 and rows * cols <= 4096, 'generated DEF array bound')
        require(len(gen['shapes'][cut]) == 1 and (cw, ch) == gen['shapes'][cut][0].size,
                'generated DEF cut size differs from original generator')
        require(gen['pitch'] is not None and cw + sx >= gen['pitch'][0] and ch + sy >= gen['pitch'][1],
                'generated DEF cut pitch below original generator')
        width, height = cols * cw + (cols - 1) * sx, rows * ch + (rows - 1) * sy
        require(width % 2 == 0 and height % 2 == 0, 'generated DEF half-dbu origin unsupported')
        hull = Rect(-width // 2, -height // 2, width // 2, height // 2)
        cuts = [Rect(hull.x0 + col * (cw + sx), hull.y0 + row * (ch + sy),
                     hull.x0 + col * (cw + sx) + cw, hull.y0 + row * (ch + sy) + ch)
                for row in range(rows) for col in range(cols)]
        result.append({'name': name, 'kind': 'fixed', 'cut': cut, 'lower': lower, 'upper': upper,
                       'shapes': {cut: cuts, lower: [hull.expanded(ex1, ey1)], upper: [hull.expanded(ex2, ey2)]}})
    return result


def audit(tech, routed, allow_generated=False):
    text, layers, vias = read_tech(tech)
    source = Path(routed).read_text()
    if allow_generated:
        arrays = generated_arrays(source, layers, vias)
    else:
        require(not re.search(r'^[ \t]*VIAS\s+[1-9]', source, re.M),
                'generated DEF via geometry requires separate admission')
        arrays = []
    checks = check_fixed(layers, vias + arrays)
    failed = [row for row in checks if not row['original_enclosure_met']]
    definitions = {v['name']: v for v in vias + arrays if v['kind'] == 'fixed'}
    require(re.search(r'UNITS DISTANCE MICRONS 1000\s*;', source), 'unknown DEF units')
    match = re.search(r'^NETS\s+(\d+)\s*;(.*?)^END NETS\s*$', source, re.M | re.S)
    require(match is not None and int(match[1]) > 0, 'missing nonempty routed NETS')
    counts = Counter()
    routes = 0
    allowed = {'ROUTED', 'FIXED', 'COVER', 'NEW', 'RECT', 'TAPER',
               'N', 'S', 'E', 'W', 'FN', 'FS', 'FE', 'FW'}
    if allow_generated:
        allowed |= {'SHAPE', 'STRIPE', 'FOLLOWPIN'}
    metal = set(re.findall(r'^LAYER\s+(\S+)\s*$', text, re.M)) - set(layers)
    records = [r for r in match[2].split(';') if r.strip()]
    require(len(records) == int(match[1]), 'DEF net count differs')
    if allow_generated:
        special = re.search(r'^SPECIALNETS\s+(\d+)\s*;(.*?)^END SPECIALNETS\s*$', source, re.M | re.S)
        require(special is not None, 'generated power-grid geometry requires SPECIALNETS')
        power = [r for r in special[2].split(';') if r.strip()]
        require(len(power) == int(special[1]) and len(power) > 0, 'DEF special-net count differs')
        records += power
    for record in records:
        start = re.search(r'\+\s+(?:ROUTED|FIXED|COVER)\s+', record)
        if start is None:
            continue
        # The emitted OpenROAD subset has no post-routing properties. Reject
        # unknown identifiers, rather than overlooking an unclassified via.
        body = record[start.start():]
        for token in re.findall(r'[^\s()]+', body):
            if token in definitions:
                counts[token] += 1
            elif token in allowed or token in metal or token in {'+', '*'}:
                pass
            else:
                require(re.fullmatch(r'-?\d+', token), 'unknown routed token ' + token)
        routes += 1
    require(routes > 0 and sum(counts.values()) > 0, 'empty routed via corpus')
    # Requiring the entire admitted fixed library to satisfy the rules is
    # deliberately conservative: unused bad geometry is rejected as well.
    return {'status': 'FAIL' if failed else 'PASS_FIXED_VIA_INTRINSIC_ENCLOSURE',
            'scope': __doc__, 'technology_sha256': file_sha(tech),
            'routed_def_sha256': file_sha(routed), 'routed_nets': routes,
            'via_instances': sum(counts.values()), 'via_counts': dict(counts),
            'fixed_definition_rule_checks': len(checks), 'violations': failed,
            'generated_array_definitions': len(arrays),
            'specialnet_geometry_checked': allow_generated,
            'uncovered': ['cell/macro internal cuts', 'wire spacing/width/area',
                          'connectivity', 'antenna', 'all other process rules']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--technology', type=Path, required=True)
    p.add_argument('--routed-def', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(not args.output.exists(), 'unused report required')
    report = audit(args.technology, args.routed_def)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], report['via_instances'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
