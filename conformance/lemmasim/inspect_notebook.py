#!/usr/bin/env python3
"""Independent, offline evidence observer; never feeds recovery to a guest.

The store oracle is independent of production Lean. This observer validates the
small ink-v1 envelope and exports retained bytes for inspection/comparison.
It does not supply a live notebook, draw pixels, or repair damaged media.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from store_oracle import recover

MAGIC = 0x314B4E49414D454C

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
        if fields[:2] != (MAGIC, 1):
            raise ValueError('unknown ink format/version')
        kind = fields[2]
        if kind == 1:
            if object_id != 1 or len(payload) != 64 or not 1 <= fields[3] <= 64:
                raise ValueError('invalid notebook root')
        elif kind == 2:
            if len(payload) != 20608 or object_id != 256 + fields[3] or not 1 <= fields[3] <= 64:
                raise ValueError('invalid page index identity/length')
            if fields[4] > 512 or fields[5] > 512 or fields[6] > fields[5]:
                raise ValueError('invalid page/edit bounds')
            entries = [struct.unpack_from('<3Q', payload, 128 + index * 24)
                       for index in range(fields[4])]
            if any(obj <= 65536 or not stroke or visible not in (0, 1)
                   for obj, stroke, visible in entries):
                raise ValueError('invalid indexed ink identity')
            if any((namespace, obj) not in records for obj, _, _ in entries):
                raise ValueError('published page references absent ink')
        elif kind == 3:
            if len(payload) < 128 or not 1 <= fields[6] <= 384 or len(payload) != 128 + fields[6] * 72:
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
