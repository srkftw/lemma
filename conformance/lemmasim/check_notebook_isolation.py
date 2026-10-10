#!/usr/bin/env python3
"""Observe real ordinary-client rejections, CPU fault and surviving notebook.

Offline evidence only: this checker imports no guest authorization/recovery or
rasterizer function and cannot feed repaired bytes or application state to QEMU.
The untouched second notebook must already exist in the input medium. DMA
ownership continuity is distinct from a request being outstanding at death.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from check_notebook_workflow import device_events, guest_events, join_chunks, visible_pixels
from inspect_notebook import inspect_page
from store_oracle import recover


def serial_observations(events):
    def single(tag):
        rows = [(index, row) for index, row in enumerate(events) if row[0] == tag]
        if len(rows) != 1:
            raise ValueError(f'missing or duplicate guest observation {tag:#x}')
        return rows[0]
    _, start = single(0x42f)
    identity = start[1]
    if not identity or not start[2] or not start[3] or start[4]:
        raise ValueError('invalid isolated-client boot observation')
    expected = {1: (72, 0), 2: (80, 0), 3: (72, 0), 4: (72, 0),
                5: (81, 0), 7: (80, 0), 101: (0, 128), 102: (0, 128),
                106: (0, 128), 201: (220, 3), 202: (220, 3), 206: (220, 3)}
    replies = {}
    for row in events:
        if row[0] != 0x430:
            continue
        _, client, test, status, value = row
        if client != identity or test in replies:
            raise ValueError('wrong sender or duplicate isolation reply')
        replies[test] = (status, value)
    if set(replies) != set(expected) | {298, 299, 300}:
        raise ValueError('missing or unexpected actual rejection corpus')
    if any(replies[test] != result for test, result in expected.items()) or replies[300][0] != 232 or replies[298][0] or not replies[298][1] or replies[299][0] or replies[299][1] < 202700000:
        raise ValueError('real capability, namespace framing, or staging-owner rejection differs')
    attempted = [index for index, row in enumerate(events) if row[0:3] == (0x430, identity, 299)]
    queued = [index for index, row in enumerate(events) if row[0:3] == (0x430, identity, 298)]
    if len(attempted) != 1 or len(queued) != 1 or not attempted[0] < queued[0]:
        raise ValueError('foreign chunk did not enter real IPC after its timed attempt')
    preceding = [(index, row) for index, row in enumerate(events[:attempted[0]]) if row[0] in (0x421, 0x423, 0x424)]
    first_ink_ack = [index for index, row in enumerate(events) if row[0] == 0x421 and row[2:4] == (1, 1) and row[4]]
    if not preceding or preceding[-1][1][0] != 0x423 or not first_ink_ack or not queued[0] < first_ink_ack[0]:
        raise ValueError('foreign chunk was not queued during a pending notebook commit')
    planned_index, planned = single(0x432)
    if planned[1] != identity or planned[2] != 0x400000 or planned[3] < 420000000 or planned[4]:
        raise ValueError('unmapped fault precondition differs')
    if any(row[0] == 0x435 for row in events):
        raise ValueError('unmapped User load returned instead of faulting')
    fault_index, fault = single(0xd4)
    if not planned_index < fault_index or fault[1] != 13 or fault[3] != 0x400000:
        raise ValueError('missing actual User load page fault')
    if not 0x1000000 <= fault[2] < 0x1080000 or fault[4] & 256:
        raise ValueError('fault was outside isolated User text or carried supervisor provenance')
    reaps = [(index, row) for index, row in enumerate(events) if row[0] == 0xf4 and row[1] == identity]
    cleaned = [(index, row) for index, row in enumerate(events) if row[0] == 0xf6 and row[1] == identity]
    if len(reaps) != 1 or reaps[0][1][2:] != (44, identity, 13):
        raise ValueError('faulting client did not enter ordinary task teardown')
    if len(cleaned) != 1 or not fault_index < reaps[0][0] < cleaned[0][0]:
        raise ValueError('faulting client was not actually reaped after its fault')
    _, clean = cleaned[0]
    if not 0 <= clean[2] < clean[3] <= 8192 or clean[4]:
        raise ValueError('reaping did not recover the faulting client owned frames')
    dma, ownership, timing = {}, {}, {}
    for row in events:
        if row[0] not in (0x433, 0x434, 0x436):
            continue
        target = dma if row[0] == 0x433 else ownership if row[0] == 0x434 else timing
        if row[1] in target:
            raise ValueError('duplicate DMA ownership phase')
        target[row[1]] = row[2:]
    if set(dma) != {0, 1, 2} or set(ownership) != {0, 1, 2} or set(timing) != {0, 1, 2}:
        raise ValueError('missing boot, fault, or post-reap DMA ownership observation')
    handle, base, _ = dma[0]
    if not handle or base % 4096 or not 0x82000000 <= base < 0x84000000:
        raise ValueError('invalid retained DMA queue frame')
    for phase in range(3):
        if dma[phase][:2] != (handle, base) or dma[phase][2] not in (0, 1, 2, 5):
            raise ValueError('DMA frame identity changed during ordinary-client death')
        if ownership[phase][:2] != (1, 0) or not 0 <= ownership[phase][2] <= 8192:
            raise ValueError('DMA kernel purpose or mapping ownership changed')
        if timing[phase][1:] != (dma[phase][2], 0):
            raise ValueError('kernel phase time differs from its actual outstanding request')
    if not timing[0][0] < planned[3] <= timing[1][0] < timing[2][0]:
        raise ValueError('kernel fault and reaping times do not follow the actual User load')
    if ownership[2][2] != clean[3] or ownership[2][2] <= ownership[1][2]:
        raise ValueError('post-reap DMA observation does not follow actual frame reclamation')
    acknowledgements = [(index, row) for index, row in enumerate(events)
                        if row[0] == 0x421 and row[2:4] == (1, 1) and row[4]]
    if not any(index < planned_index for index, _ in acknowledgements):
        raise ValueError('notebook has no acknowledged ink before isolated-client fault')
    if not any(index > cleaned[0][0] for index, _ in acknowledgements):
        raise ValueError('store and notebook did not acknowledge fresh ink after client reaping')
    states = [row for row in events if row[0] in (0x421, 0x423, 0x424)]
    if not states or states[-1][0] != 0x421 or any(row[0] in (0x41f, 0x424) for row in events):
        raise ValueError('isolation run ended pending/failed or formatted its input medium')
    return {'client': identity, 'actual_replies': {str(k): list(v) for k, v in replies.items()},
            'foreign_chunk_queued_during_notebook_commit': True,
            'fault': list(fault), 'reap': list(clean),
            'dma': {str(k): list(v) for k, v in dma.items()},
            'dma_timing': {str(k): list(v) for k, v in timing.items()},
            'dma_request_outstanding_at_fault': bool(dma[1][2]),
            'post_fault_acknowledgements': [list(row) for index, row in acknowledgements if index > cleaned[0][0]]}


def delayed_dma_observation(observed, media_events):
    """Match a real pending write interval against compiled fault/reap times.

    The hardware timer intentionally has not yet consumed the guest DMA iovec
    between begin/end. Merely retaining a driver pending bit cannot pass this.
    """
    begun = [(time, a, b) for time, event, a, b, _ in media_events if event == 'write-delay-begin']
    ended = [(time, a, b) for time, event, a, b, _ in media_events if event == 'write-delay-end']
    if len(begun) != 1 or len(ended) != 1:
        raise ValueError('missing or duplicate actual delayed-write interval')
    start, offset, size = begun[0]
    end, final_offset, final_size = ended[0]
    if (offset, size) != (final_offset, final_size) or offset % 512 or not size or size % 512:
        raise ValueError('delayed write identity or sector alignment differs')
    # This exact optional Lab policy is part of the test run identity.
    if start < 40000000000 or end - start < 3000000000:
        raise ValueError('actual delayed-write interval differs from its declared Lab policy')
    if any(event == 'write-delay-drained' for _, event, _, _, _ in media_events):
        raise ValueError('delayed DMA was drained by host pause/reset instead of its virtual timer')
    timing = observed['dma_timing']
    for phase in ('1', '2'):
        now, kind, reserved = timing[phase]
        if not start < now * 100 < end or kind != 2 or reserved:
            raise ValueError('client fault or post-reap observation occurred outside writable DMA interval')
    # Actual durable publication of the second stroke must proceed only after
    # the delayed request completes; serial ACK itself is also checked above.
    writes = [(time, a, b) for time, event, a, b, _ in media_events if event == 'write-volatile']
    if not any(time >= end and (a, b) == (offset, size) for time, a, b in writes):
        raise ValueError('delayed request never consumed its retained guest DMA after reaping')
    return {'write_start_ns': start, 'write_complete_ns': end, 'offset': offset,
            'bytes': size, 'fault_ns': timing['1'][0] * 100,
            'reaped_ns': timing['2'][0] * 100,
            'scope': 'actual writable device interval brackets User fault and completed client reaping'}


def check(before_disk, after_disk, serial, devices, media, visible, input_file, manifest_file):
    observed = serial_observations(guest_events(serial))
    delayed = delayed_dma_observation(observed, device_events(media))
    _, before_sequence, before = recover(before_disk.read_bytes())
    _, after_sequence, after = recover(after_disk.read_bytes())
    previous = {key: record for key, record in before.items() if key[0] == 2}
    current = {key: record for key, record in after.items() if key[0] == 2}
    if not previous or not any(record.kind == 1 and len(record.payload) >= 128 and
                               struct.unpack_from('<Q', record.payload, 16)[0] == 3
                               for record in previous.values()):
        raise ValueError('input medium has no second notebook with saved writing')
    # Physical sector addresses can legitimately move during checkpointing;
    # object/transaction/sequence/kind and document bytes remain unchanged.
    signature = lambda records: {key: (r.transaction, r.sequence, r.kind, r.payload) for key, r in records.items()}
    if signature(previous) != signature(current):
        raise ValueError('faulting client or first notebook changed the other notebook')
    if any(ns not in (1, 2) for ns, _ in after) or after_sequence <= before_sequence:
        raise ValueError('namespace framing bypass or no actual notebook publication')
    if observed['post_fault_acknowledgements'][-1][1] != after_sequence:
        raise ValueError('latest document publication lacks post-fault durable acknowledgement')
    manifest = json.loads(manifest_file.read_text())
    raw = input_file.read_bytes()
    if (manifest.get('schema_version') != 1 or manifest.get('profile') != 'lemmasim-virt/0.1.0' or
            manifest.get('workflow') != 'basic' or manifest.get('input_samples') != 51 or len(raw) != 51 * 72 or
            manifest.get('clock_hz') != 10000000 or hashlib.sha256(raw).hexdigest() != manifest['input_sha256']):
        raise ValueError('isolation input must be the unchanged ordinary two-stroke fixture')
    samples = [struct.unpack_from('<9Q', raw, offset) for offset in range(0, len(raw), 72)]
    events = device_events(devices)
    ingress = {}
    completions = []
    for time, event, a, b, c in events:
        if event == 'pen-input':
            if a in ingress or not 1 <= a <= len(samples) or not b or not c or time < samples[a - 1][1] * 100:
                raise ValueError('invalid actual raw FIFO ingress')
            ingress[a] = (b, c)
        elif event == 'pen-input-rejected' and a != 1:
            raise ValueError('isolation run dropped ordinary writing input')
        elif event == 'paper-complete':
            completions.append((time, a))
    if set(ingress) != set(range(1, len(samples) + 1)) - {1} and set(ingress) != set(range(1, len(samples) + 1)):
        raise ValueError('missing raw FIFO ingress')
    if not completions or any(b[1] <= a[1] for a, b in zip(completions, completions[1:])):
        raise ValueError('missing or reordered controller-visible refresh')
    page = after.get((1, 257))
    if page is None or page.kind != 1:
        raise ValueError('continued notebook did not publish its real page')
    entries = inspect_page(page.payload, 257)
    grouped = {}
    for object_id, stroke, visible_flag in entries:
        record = after.get((1, object_id))
        if record is None:
            raise ValueError('page published missing ink')
        if record.sequence <= before_sequence:
            continue
        payload = record.payload
        if record.kind != 1 or len(payload) < 128:
            raise ValueError('continued ink is not a complete versioned record')
        header = struct.unpack_from('<16Q', payload)
        if (header[0:3] != (0x314B4E49414D454C, 1, 3) or header[3:5] != (1, stroke) or
                not 1 <= header[6] <= 384 or len(payload) != 128 + header[6] * 72 or visible_flag != 1 or
                list(header[9:11]) != manifest['raw_coordinate_maximum'] or header[11] != manifest['pressure_maximum'] or
                list(header[12:14]) != manifest['geometry']):
            raise ValueError('continued ink lost its identity or device provenance')
        values = [struct.unpack_from('<9Q', payload, 128 + i * 72) for i in range(header[6])]
        grouped.setdefault(stroke, []).append((header, values))
    retained = [set(join_chunks(chunks)) for chunks in grouped.values()]
    actions = [row for row in manifest['actions'] if row['kind'] == 'stroke']
    if (len(actions) != 2 or [(row['namespace'], row['page'], row['first_sequence'], row['last_sequence'], row['raw_samples'])
                              for row in actions] != [(1, 1, 2, 26, 25), (1, 1, 27, 51, 25)] or
            manifest['expected']['retained_raw_samples'] != 50):
        raise ValueError('isolation fixture is not the literal ordinary two-stroke workflow')
    expected = [set((ingress[i][0], *samples[i - 1][1:8], ingress[i][1])
                    for i in range(action['first_sequence'], action['last_sequence'] + 1)) for action in actions]
    if len(retained) != len(expected) or any(sum(actual == wanted for actual in retained) != 1 for wanted in expected):
        raise ValueError('fresh raw writing did not become wholly indexed guest ink across the client fault')
    width, height, pixels = visible_pixels(visible)
    if [width, height] != manifest['geometry'] or not any(time >= samples[-1][1] * 100 for time, _ in completions):
        raise ValueError('final guest writing did not complete its actual visible refresh')
    for action in actions:
        sample = samples[action['first_sequence'] - 1]
        x, y = sample[2] * (width - 1) // 65535, sample[3] * (height - 1) // 65535
        if not any(pixels[(py * width + px) * 3:(py * width + px) * 3 + 3] == bytes(3)
                   for py in range(y - 2, y + 3) for px in range(x - 2, x + 3)):
            raise ValueError('surviving writing lacks actual controller-visible black pixels')
    paths = (before_disk, after_disk, serial, devices, media, visible, input_file, manifest_file)
    return {'schema_version': 1, 'status': 'PASS',
            'scope': 'actual ordinary User rejection replies, User page fault/reaping during writable DMA, retained kernel DMA ownership, continued guest ink commit/pixels and unchanged second notebook',
            **observed, 'before_sequence': before_sequence, 'committed_sequence': after_sequence,
            'active_dma_death': delayed,
            'fresh_retained_raw_samples': sum(len(value) for value in retained),
            'unchanged_notebook2_records': len(previous),
            'artifact_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before-disk', 'after-disk', 'serial', 'devices', 'media', 'visible', 'input', 'manifest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to overwrite retained isolation observation')
    try:
        result = check(args.before_disk, args.after_disk, args.serial, args.devices, args.media, args.visible, args.input, args.manifest)
    except (ValueError, OSError, KeyError, struct.error) as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'fresh_retained_raw_samples', 'dma_request_outstanding_at_fault', 'error') if key in result}))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
