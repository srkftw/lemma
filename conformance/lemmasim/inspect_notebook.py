#!/usr/bin/env python3
"""Independent, offline evidence observer; never feeds recovery to a guest.

The store oracle is independent of production Lean. This observer validates the
versioned ink envelopes and exports retained bytes for inspection/comparison.
It does not supply a live notebook, draw pixels, or repair damaged media.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from store_oracle import recover
from math_oracle import MAGIC as MATH_MAGIC, inspect as inspect_math

MAGIC = 0x314B4E49414D454C

def inspect_page(payload: bytes, object_id: int) -> list[tuple[int, int, int]]:
    if len(payload) < 128:
        raise ValueError('page is shorter than its header')
    fields = struct.unpack_from('<16Q', payload)
    if fields[0] != MAGIC or fields[1] not in (1, 2) or fields[2] != 2:
        raise ValueError('unknown page format/version')
    if object_id != 256 + fields[3] or not 1 <= fields[3] <= 64:
        raise ValueError('invalid page index identity')
    count, edits, cursor = fields[4:7]
    if count > 512 or edits > 512 or cursor > edits:
        raise ValueError('invalid page/edit bounds')
    expected = 20608 if fields[1] == 1 else 128 + count * 24 + edits * 16
    if len(payload) != expected:
        raise ValueError('invalid page index length')
    if fields[1] == 2 and any(fields[7:]):
        raise ValueError('unknown mandatory page header field')
    entries = [struct.unpack_from('<3Q', payload, 128 + index * 24)
               for index in range(count)]
    if any(obj <= 65536 or not stroke or visible not in (0, 1)
           for obj, stroke, visible in entries):
        raise ValueError('invalid indexed ink identity')
    edit_offset = 12416 if fields[1] == 1 else 128 + count * 24
    operations = [struct.unpack_from('<2Q', payload, edit_offset + index * 16)
                  for index in range(edits)]
    if any(kind not in (1, 2) or not stroke for kind, stroke in operations):
        raise ValueError('invalid indexed edit operation')
    return entries

def inspect(image: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('refusing to overwrite retained observations')
    data = image.read_bytes()
    root, sequence, records = recover(data)
    output.mkdir(parents=True)
    observations = []
    raw_count = 0
    namespaces = set()
    for (namespace, object_id), record in sorted(records.items()):
        if record.kind == 2:
            continue
        payload = record.payload
        if len(payload) < 64:
            raise ValueError('notebook record is shorter than its header')
        fields = struct.unpack_from('<8Q', payload)
        if fields[0] == MATH_MAGIC:
            mathematical = inspect_math(payload, namespace, object_id)
            name = f'namespace-{namespace}-object-{object_id}.bin'
            (output / name).write_bytes(payload)
            observations.append({'namespace': namespace, 'object': object_id,
                'sequence': record.sequence, 'kind': fields[2], 'bytes': len(payload),
                'format': mathematical['format'], 'mathematical': mathematical,
                'sha256': hashlib.sha256(payload).hexdigest(), 'export': name})
            namespaces.add(namespace)
            continue
        if fields[0] != MAGIC:
            raise ValueError('unknown ink format/version')
        kind = fields[2]
        if kind == 1:
            if fields[1] != 1 or object_id != 1 or len(payload) != 64 or not 1 <= fields[3] <= 64:
                raise ValueError('invalid notebook root')
        elif kind == 2:
            entries = inspect_page(payload, object_id)
            if any((namespace, obj) not in records for obj, _, _ in entries):
                raise ValueError('published page references absent ink')
        elif kind == 3:
            if fields[1] != 1 or len(payload) < 128 or not 1 <= fields[6] <= 384 or len(payload) != 128 + fields[6] * 72:
                raise ValueError('invalid raw chunk count/length')
            if object_id <= 65536 or not fields[4]:
                raise ValueError('invalid raw chunk identity')
            previous = None
            for index in range(fields[6]):
                sample = struct.unpack_from('<9Q', payload, 128 + index * 72)
                if not sample[0] or not sample[8]:
                    raise ValueError('missing raw provenance')
                if previous and (sample[0] != previous[0] + 1 or sample[1] < previous[1] or sample[8] != previous[8]):
                    raise ValueError('unexplained input boundary inside stroke chunk')
                previous = sample
            raw_count += fields[6]
        else:
            raise ValueError('unknown mandatory ink record kind')
        name = f'namespace-{namespace}-object-{object_id}.bin'
        (output / name).write_bytes(payload)
        observations.append({'namespace': namespace, 'object': object_id,
                             'sequence': record.sequence, 'kind': kind, 'bytes': len(payload),
                             'sha256': hashlib.sha256(payload).hexdigest(), 'export': name})
        namespaces.add(namespace)
    if not observations:
        raise ValueError('empty notebook corpus cannot establish writing')
    result = {'schema_version': 1, 'status': 'OBSERVED',
              'scope': 'independent offline committed store/ink byte observation; no live recovery',
              'image_sha256': hashlib.sha256(data).hexdigest(), 'store_generation': root.generation,
              'committed_sequence': sequence, 'namespaces': sorted(namespaces),
              'retained_raw_samples_including_continuation_overlap': raw_count,
              'objects': observations}
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.disk, args.output_dir)
    print(json.dumps({key: result[key] for key in ('committed_sequence', 'namespaces', 'retained_raw_samples_including_continuation_overlap')}))

if __name__ == '__main__':
    main()
