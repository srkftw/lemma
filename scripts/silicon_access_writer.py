#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact pinned DRT writer relation, never general AP normalization.

The 26Q2 BTerm update flag starts true even with -no_pin_access. Its first
write appends one literal copy of each existing BPin AP. Instance access,
preferences, original APs, owners, directions, segments and vias stay exact.
This relation admits only that source-bound serialization consequence.
"""
import argparse
import json
from pathlib import Path

from silicon_access_metadata import require


def relation(before, after):
    require(set(before) == set(after), 'router changed metadata fields')
    for key in before:
        if key not in ('access_points', 'block_terminals'):
            require(before[key] == after[key], 'router changed original ' + key)
    original, final = before['access_points'], after['access_points']
    require(final[:len(original)] == original, 'router changed/deleted original AP records')
    ids = [a['id'] for a in original]
    require(ids and len(ids) == len(set(ids)) and all(type(i) is int and i > 0 for i in ids), 'invalid original AP identity')
    original_by_id = {a['id']: a for a in original}
    added = final[len(original):]
    require([a['id'] for a in added] == list(range(max(ids)+1, max(ids)+1+len(added))), 'nonconsecutive/duplicate added AP identities')
    added_by_id = {a['id']: a for a in added}
    require(len(before['block_terminals']) == len(after['block_terminals']), 'router changed block pin inventory')
    used = set(); copied = 0; extended = 0
    owners = set()
    for old, new in zip(before['block_terminals'], after['block_terminals']):
        require(set(old) == set(new) == {'terminal', 'bpin_id', 'access'}, 'unexpected block pin fields')
        require((old['terminal'], old['bpin_id']) == (new['terminal'], new['bpin_id']), 'router changed/reordered BPin owner')
        owner_key = (old['terminal'], old['bpin_id'])
        require(owner_key not in owners, 'duplicate BPin owner'); owners.add(owner_key)
        old_ids = old['access']; new_ids = new['access']
        require(len(old_ids) == len(set(old_ids)), 'duplicate original BPin AP')
        require(new_ids[:len(old_ids)] == old_ids and len(new_ids) == 2*len(old_ids), 'expected exactly one BPin AP copy')
        expected_owner = {'kind':'block_pin', 'bterm':old['terminal'], 'bpin_id':old['bpin_id']}
        for old_id, new_id in zip(old_ids, new_ids[len(old_ids):]):
            require(old_id in original_by_id and new_id in added_by_id and new_id not in used, 'missing/shared/wrong added BPin AP')
            source, clone = original_by_id[old_id], added_by_id[new_id]
            require(source['owner'] == expected_owner and clone['owner'] == expected_owner, 'BPin AP owner changed')
            require({k:v for k,v in source.items() if k != 'id'} ==
                    {k:v for k,v in clone.items() if k != 'id'}, 'BPin copy changed point/layer/via/segment/direction')
            used.add(new_id); copied += 1
        extended += bool(old_ids)
    require(used == set(added_by_id) and copied == len(added), 'unbound extra AP records')
    return {'status':'PASS_PINNED_SINGLE_BPIN_WRITE_COPY_ONLY_ORIGINAL_ACCESS_EXACT',
            'original_access_points':len(original), 'literal_added_BPin_copies':copied,
            'extended_BPin_vectors':extended, 'block_pins':len(owners),
            'original_patterns_and_ITerms_exact':True,
            'scope':'Only the pinned first BTerm writer copy; no route geometry/process/timing qualification.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before',type=Path,required=True)
    p.add_argument('--after',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    require(not args.output.exists() and args.output.resolve() not in (args.before.resolve(),args.after.resolve()), 'unused distinct relation output required')
    result = relation(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
