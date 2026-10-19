#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cover the demonstrated router fixed-via enclosure gap on actual DEF routes.

Checks intrinsic fixed-via metal/cut unions against the original process simple
enclosure rules. Additional same-net wire metal can only increase enclosure.
No generated DEF vias or unfamiliar route clauses are silently admitted. This
is an independent sufficient check of this subset, never complete process DRC.
"""
from pathlib import Path
import argparse
import json
import re
from collections import Counter
from silicon_enclosure import check_fixed, file_sha, read_tech, require


def audit(tech, routed):
    text, layers, vias = read_tech(tech)
    checks = check_fixed(layers, vias)
    failed = [row for row in checks if not row['original_enclosure_met']]
    definitions = {v['name']: v for v in vias if v['kind'] == 'fixed'}
    source = Path(routed).read_text()
    require(re.search(r'UNITS DISTANCE MICRONS 1000\s*;', source), 'unknown DEF units')
    require(not re.search(r'^[ \t]*VIAS\s+[1-9]', source, re.M),
            'generated DEF via geometry requires separate admission')
    match = re.search(r'^NETS\s+(\d+)\s*;(.*?)^END NETS\s*$', source, re.M | re.S)
    require(match is not None and int(match[1]) > 0, 'missing nonempty routed NETS')
    counts = Counter()
    routes = 0
    allowed = {'ROUTED', 'FIXED', 'COVER', 'NEW', 'RECT', 'TAPER',
               'N', 'S', 'E', 'W', 'FN', 'FS', 'FE', 'FW'}
    metal = set(re.findall(r'^LAYER\s+(\S+)\s*$', text, re.M)) - set(layers)
    records = [r for r in match[2].split(';') if r.strip()]
    require(len(records) == int(match[1]), 'DEF net count differs')
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
