#!/usr/bin/env python3
"""Observe notebook crash evidence offline; never repair or feed media to a guest.

The independent store oracle validates record publication/recovery. This checker
adds prior guest ACK witnesses, exported immutable ink, page ancestry, raw FIFO
provenance, and device-level fault boundaries. It does not run an application or
supply recovered objects, pixels, or formatted media to the running machine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from store_oracle import RECORD, fnv, recover

MAGIC = 0x314B4E49414D454C
FAULT_EVENTS = {
    'cut-before-flush': 'power-cut-before-flush',
    'cut-after-flush': 'power-cut-after-flush',
    'tear-flush': 'power-cut-torn-flush',
    'fail-flush': 'flush-failed',
}
PHASES = {'payload', 'publication', 'checkpoint-segment', 'checkpoint-root'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def observations(path: Path) -> list[tuple[int, str, int, int, int]]:
    rows = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 5:
            raise ValueError('truncated device/media observation')
        time, event, a, b, c = fields
        row = (int(time), event, int(a), int(b), int(c))
        if min(row[0], row[2], row[3], row[4]) < 0 or rows and row[0] < rows[-1][0]:
            raise ValueError('negative or backward device/media observation')
        rows.append(row)
    if not rows:
        raise ValueError('empty device/media observation')
    return rows


def guest_observations(path: Path) -> list[tuple[int, ...]]:
    rows = [tuple(int(word, 16) for word in row) for row in re.findall(
        rb'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})',
        path.read_bytes())]
    if not rows:
        raise ValueError('missing compiled guest observations')
    return rows


@dataclass(frozen=True)
class Page:
    entries: tuple[tuple[int, int, int], ...]
    edits: tuple[tuple[int, int], ...]
    cursor: int


@dataclass(frozen=True)
class Chunk:
    header: tuple[int, ...]
    samples: tuple[tuple[int, ...], ...]


@dataclass
class Notebook:
    roots: dict[int, tuple[int, ...]]
    pages: dict[tuple[int, int], Page]
    chunks: dict[tuple[int, int], Chunk]
    payloads: dict[tuple[int, int], bytes]


def notebook(payloads: dict[tuple[int, int], bytes]) -> Notebook:
    """Literal envelope/editor checks, independent of the guest codecs."""
    result = Notebook({}, {}, {}, payloads)
    for (ns, obj), data in payloads.items():
        if not ns or not obj or len(data) < 64:
            raise ValueError('short or unnamed notebook object')
        h = struct.unpack_from('<8Q', data)
        from math_oracle import MAGIC as MATH_MAGIC, inspect as inspect_math
        if h[0] == MATH_MAGIC:
            inspect_math(data, ns, obj)
            continue
        if h[0] != MAGIC:
            raise ValueError('unknown notebook magic')
        if h[2] == 1:
            if h[1] != 1 or obj != 1 or len(data) != 64 or not 1 <= h[3] <= 64 or h[4] not in (256, 512, 1024, 2048) or any(h[5:]):
                raise ValueError('invalid notebook catalog')
            result.roots[ns] = h
        elif h[2] == 2:
            if h[1] not in (1, 2) or obj != 256 + h[3] or not 1 <= h[3] <= 64 or h[4] > 512 or h[5] > 512 or h[6] > h[5]:
                raise ValueError('invalid page identity/bounds')
            size = 20608 if h[1] == 1 else 128 + h[4] * 24 + h[5] * 16
            if len(data) != size or any(data[56:128]):
                raise ValueError('invalid page size/reserved fields')
            entries = tuple(struct.unpack_from('<3Q', data, 128 + i * 24) for i in range(h[4]))
            edit_base = 12416 if h[1] == 1 else 128 + h[4] * 24
            edits = tuple(struct.unpack_from('<2Q', data, edit_base + i * 16) for i in range(h[5]))
            if len({entry[0] for entry in entries}) != len(entries) or any(obj <= 65536 or not stroke or flag not in (0, 1) for obj, stroke, flag in entries):
                raise ValueError('invalid or duplicate indexed chunk')
            if any(kind not in (1, 2) or not stroke for kind, stroke in edits):
                raise ValueError('unknown edit operation')
            visible = {}
            for kind, stroke in edits[:h[6]]:
                visible[stroke] = int(kind == 1)
            if any(visible.get(stroke) != flag for _, stroke, flag in entries):
                raise ValueError('page flags disagree with independently applied edits')
            result.pages[ns, h[3]] = Page(entries, edits, h[6])
        elif h[2] == 3:
            if h[1] != 1 or obj <= 65536 or len(data) < 128:
                raise ValueError('invalid raw chunk identity')
            header = struct.unpack_from('<16Q', data)
            if not 1 <= header[3] <= 64 or not header[4] or header[5] or header[15] or not 1 <= header[6] <= 384 or len(data) != 128 + header[6] * 72:
                raise ValueError('invalid raw chunk envelope')
            if not 256 <= header[7] <= 8192 or header[8] != 1 or min(header[9:14]) == 0 or header[14] not in (1, 3, 4, 6):
                raise ValueError('unknown brush/calibration/lifecycle')
            samples = tuple(struct.unpack_from('<9Q', data, 128 + i * 72) for i in range(header[6]))
            if any(not s[0] or not s[8] or s[2] > header[9] or s[3] > header[10] or s[4] > header[11] or s[5] & ~7 or s[6] > 2 or s[7] & ~7 for s in samples):
                raise ValueError('invalid original raw sample')
            if any(b[0] != a[0] + 1 or b[1] < a[1] or b[8] != a[8] for a, b in zip(samples, samples[1:])):
                raise ValueError('raw chunk crosses an input boundary')
            if any(not (s[5] & 1) for s in samples[:-1]) or bool(samples[-1][5] & 1) == bool(header[14] & 2):
                raise ValueError('raw chunk contact lifecycle contradicts its samples')
            result.chunks[ns, obj] = Chunk(header, samples)
        else:
            raise ValueError('unknown notebook object kind')
    for (ns, page_id), page in result.pages.items():
        # A new page may be committed just before its catalog update; it remains
        # a valid unacknowledged document transaction. Baseline checks below
        # separately require its previously acknowledged catalog to survive.
        strokes: dict[int, list[Chunk]] = {}
        for obj, stroke, _ in page.entries:
            chunk = result.chunks.get((ns, obj))
            if chunk is None or chunk.header[3:5] != (page_id, stroke):
                raise ValueError('page references absent or contradictory ink')
            strokes.setdefault(stroke, []).append(chunk)
        for chunks in strokes.values():
            if chunks[0].header[14] not in (1, 3) or not chunks[0].samples[0][5] & 1:
                raise ValueError('indexed stroke has no valid original start')
            for previous, current in zip(chunks, chunks[1:]):
                if previous.header[14] & 2 or current.header[14] not in (4, 6) or previous.samples[-1] != current.samples[0] or len(current.samples) < 2 or previous.header[7:14] != current.header[7:14]:
                    raise ValueError('indexed continuation lost its exact original boundary')
    return result


def baseline_export(directory: Path) -> tuple[dict, Notebook]:
    manifest = json.loads((directory / 'result.json').read_text())
    if manifest.get('schema_version') != 1 or manifest.get('status') != 'OBSERVED' or not manifest.get('objects'):
        raise ValueError('missing prior independently exported committed objects')
    payloads = {}
    for item in manifest['objects']:
        key = (item['namespace'], item['object'])
        name = item['export']
        if key in payloads or Path(name).name != name or not isinstance(item['sequence'], int) or not 0 < item['sequence'] <= manifest['committed_sequence']:
            raise ValueError('duplicate/invalid baseline export identity')
        payload = (directory / name).read_bytes()
        if len(payload) != item['bytes'] or sha(payload) != item['sha256'] or len(payload) < 24 or struct.unpack_from('<Q', payload, 16)[0] != item['kind']:
            raise ValueError('baseline export bytes changed')
        payloads[key] = payload
    return manifest, notebook(payloads)


def retained_baseline(before: Notebook, after: Notebook) -> None:
    """Fault cases append/checkpoint; undo/erase have their separate workflow.

    Immutable chunks, indexed stroke ancestry, and prior applied edit operations
    must survive. Mutable root/page bytes may validly gain an unacknowledged
    appended stroke; byte equality would incorrectly reject that admitted case.
    """
    for key, chunk in before.chunks.items():
        if after.payloads.get(key) != before.payloads[key]:
            raise ValueError(f'previously acknowledged immutable ink lost/changed: {key}')
    for ns, root in before.roots.items():
        if ns not in after.roots or after.roots[ns][3] < root[3]:
            raise ValueError('previously acknowledged notebook/catalog lost')
    for key, old in before.pages.items():
        new = after.pages.get(key)
        if new is None or tuple(entry[:2] for entry in new.entries[:len(old.entries)]) != tuple(entry[:2] for entry in old.entries):
            raise ValueError('previously acknowledged page/stroke ancestry lost')
        if new.edits[:len(old.edits)] != old.edits or new.cursor < old.cursor:
            raise ValueError('previously acknowledged editing history lost in append/checkpoint fault')


def raw_provenance(input_file: Path, manifest_file: Path, device_file: Path) -> tuple[dict, dict[tuple[int, ...], tuple[int, int, str]]]:
    manifest = json.loads(manifest_file.read_text())
    data = input_file.read_bytes()
    if manifest.get('schema_version') != 1 or manifest.get('profile') != 'lemmasim-virt/0.1.0' or not data or len(data) % 72 or sha(data) != manifest.get('input_sha256'):
        raise ValueError('unknown, empty, or changed raw fixture')
    samples = [struct.unpack_from('<9Q', data, i) for i in range(0, len(data), 72)]
    if len(samples) != manifest.get('input_samples') or [s[0] for s in samples] != list(range(1, len(samples) + 1)) or any(b[1] < a[1] for a, b in zip(samples, samples[1:])):
        raise ValueError('raw fixture sequence/time/count contradiction')
    if ('first_tick' in manifest and manifest['first_tick'] != samples[0][1] or
            'last_tick' in manifest and manifest['last_tick'] != samples[-1][1]):
        raise ValueError('raw fixture timing metadata differs from actual serialized samples')
    actions = {}
    for action in manifest['actions']:
        if action['kind'] == 'stroke':
            for seq in range(action['first_sequence'], action['last_sequence'] + 1):
                if not 1 <= seq <= len(samples) or seq in actions:
                    raise ValueError('overlapping/invalid raw stroke actions')
                actions[seq] = (action['namespace'], action['page'], action['name'])
    admitted, observed = {}, set()
    for time, event, a, b, epoch in observations(device_file):
        if event not in ('pen-input', 'pen-input-rejected'):
            continue
        if a != len(observed) + 1 or not 1 <= a <= len(samples) or time < samples[a - 1][1] * 100 or not epoch:
            raise ValueError('duplicate, early, or invalid actual device ingress')
        observed.add(a)
        if event == 'pen-input-rejected':
            if b:
                raise ValueError('rejected input has a fabricated controller sequence')
        elif not b:
            raise ValueError('accepted input has no controller sequence')
        elif a in actions:
            sample = (b, *samples[a - 1][1:8], epoch)
            if sample in admitted:
                raise ValueError('ambiguous actual original sample')
            admitted[sample] = actions[a]
    # A device-level cut may precede later fixture ingress. Missing suffix input
    # is reported, not silently treated as a complete live/replay session.
    if not observed or observed != set(range(1, max(observed) + 1)):
        raise ValueError('actual cut-run ingress has an unexplained missing prefix')
    manifest = dict(manifest, observed_input_prefix=max(observed))
    return manifest, admitted


def medium_boundary(path: Path, case: dict, baseline_generation: int) -> dict:
    if case.get('schema_version') != 1 or case.get('fault') not in FAULT_EVENTS or case.get('phase') not in PHASES or case.get('operation') not in ('append', 'checkpoint') or not isinstance(case.get('ordinal'), int) or case['ordinal'] < 1:
        raise ValueError('unknown fault-case identity')
    if case['phase'].startswith('checkpoint-') != (case['operation'] == 'checkpoint'):
        raise ValueError('fault operation and phase disagree')
    rows = observations(path)
    if rows[0][1:] != ('medium-open', rows[0][2], 1, 0):
        raise ValueError('missing actual fresh durable-filter open')
    pending, prior_durable, seen_flush, target, faults = {}, 0, 0, None, []
    for time, event, a, b, count in rows:
        if event == 'write-volatile':
            if a % 512 or b % 512 or not 1 <= b <= 65536:
                raise ValueError('invalid modeled block write')
            for offset in range(a, a + b, 512):
                pending[offset] = True
            if count != len(pending):
                raise ValueError('pending sector count disagrees with actual writes')
        elif event == 'flush-begin':
            if a != seen_flush + 1 or b != prior_durable or count != len(pending):
                raise ValueError('flush ordinal/pending state contradiction')
            seen_flush = a
            if a == case['ordinal']:
                target = {'ordinal': a, 'virtual_ns': time, 'write_offsets': sorted(pending), 'prior_durable_flush': b}
        elif event == 'flush-durable':
            if a != seen_flush or b or count:
                raise ValueError('invalid durability observation')
            prior_durable = a
            pending.clear()
        if event in FAULT_EVENTS.values():
            faults.append((event, a))
    expected = (FAULT_EVENTS[case['fault']], case['ordinal'])
    if faults != [expected] or target is None:
        raise ValueError('declared device fault absent, repeated, or at a different actual flush')
    offsets = target['write_offsets']
    phase = case['phase']
    if not offsets:
        raise ValueError('named persistence boundary has no pending device writes')
    if phase == 'checkpoint-root':
        # The next generation alternates publication slots; old slot/segment
        # remain untouched. These are byte offsets, not notebook record IDs.
        expected_slot = (baseline_generation % 2) * 512
        if offsets != [expected_slot]:
            raise ValueError('checkpoint root switch did not write its exact independent publication slot')
    elif any(offset < 4096 for offset in offsets):
        raise ValueError('record/segment boundary unexpectedly writes a root or reservation')
    elif phase in ('payload', 'publication'):
        header, sectors, publication = (case.get(key) for key in
            ('record_header_sector', 'record_payload_sectors', 'record_publication_sector'))
        if not isinstance(header, int) or not isinstance(sectors, int) or not isinstance(publication, int) or header < 8 or not 0 <= sectors <= 64 or publication != header + sectors + 1:
            raise ValueError('record boundary lacks its exact independently observed sector layout')
        expected_offsets = ([publication * 512] if phase == 'publication' else
                            [sector * 512 for sector in range(header, header + sectors + 1)] + [(publication + 1) * 512])
        if offsets != expected_offsets:
            raise ValueError('named record phase does not match actual payload/publication write offsets')
    elif phase == 'checkpoint-segment':
        start, length = case.get('replacement_segment_start'), case.get('replacement_segment_length')
        if not isinstance(start, int) or not isinstance(length, int) or start < 8 or length < 1 or len(offsets) < 3 or any(not start * 512 <= offset < (start + length) * 512 for offset in offsets):
            raise ValueError('checkpoint payload did not stay within the declared inactive segment')
    if case['fault'] == 'tear-flush':
        torn = [(a, b) for _, event, a, b, _ in rows if event == 'sector-torn-durable']
        if torn != [(min(offsets) // 512, 256)]:
            raise ValueError('torn fault lacks actual first-sector half-write observation')
    target.update(fault=case['fault'], phase=phase, observation=expected[0])
    return target


def plan(reference_disk: Path, reference_media: Path, baseline_dir: Path) -> dict:
    """Name fault ordinals from a successful actual block trace and disk.

    Only independently recovered *latest* records are named. Earlier mutable
    revisions and ordinary no-write mount/close flushes are deliberately omitted.
    Use one append reference and one checkpoint reference from the same baseline.
    """
    baseline, _ = baseline_export(baseline_dir)
    root, sequence, records = recover(reference_disk.read_bytes())
    if sequence < baseline['committed_sequence'] or root.generation < baseline['store_generation']:
        raise ValueError('reference does not extend the acknowledged baseline')
    rows = observations(reference_media)
    if any(event in FAULT_EVENTS.values() for _, event, _, _, _ in rows):
        raise ValueError('fault plan requires a successful reference device trace')
    groups = []
    pending: set[int] = set()
    current = None
    ordinal = 0
    for time, event, a, b, count in rows:
        if event == 'write-volatile':
            if a % 512 or b % 512 or not 1 <= b <= 65536:
                raise ValueError('invalid reference block write')
            pending.update(range(a, a + b, 512))
            if len(pending) != count:
                raise ValueError('reference pending sector count differs')
        elif event == 'flush-begin':
            if a != ordinal + 1 or current is not None:
                raise ValueError('reference flush ordering differs')
            ordinal = a
            current = {'ordinal': a, 'virtual_ns': time, 'write_offsets': sorted(pending)}
        elif event == 'flush-durable':
            if current is None or a != current['ordinal'] or b or count:
                raise ValueError('reference lacks matching successful durability completion')
            groups.append(current)
            current = None
            pending.clear()
    if current is not None or pending or not groups:
        raise ValueError('reference ends with incomplete block work')
    cases = []
    for group in groups:
        offsets = group['write_offsets']
        identity = {'schema_version': 1, 'ordinal': group['ordinal']}
        found = False
        for (ns, obj), record in records.items():
            sectors = (len(record.payload) + 511) // 512
            publication = record.sector + sectors + 1
            payload = [sector * 512 for sector in range(record.sector, record.sector + sectors + 1)] + [(publication + 1) * 512]
            phase = ('payload' if offsets == payload else
                     'publication' if offsets == [publication * 512] else None)
            if phase:
                cases.append(dict(identity, operation='append', phase=phase,
                                  record_namespace=ns, record_object=obj,
                                  record_sequence=record.sequence,
                                  record_header_sector=record.sector,
                                  record_payload_sectors=sectors,
                                  record_publication_sector=publication))
                found = True
                break
        if found:
            continue
        if root.generation == baseline['store_generation'] + 1:
            slot = (baseline['store_generation'] % 2) * 512
            if offsets == [slot]:
                cases.append(dict(identity, operation='checkpoint', phase='checkpoint-root'))
            elif len(offsets) >= 3 and all(root.start * 512 <= offset < (root.start + root.length) * 512 for offset in offsets):
                cases.append(dict(identity, operation='checkpoint', phase='checkpoint-segment',
                                  replacement_segment_start=root.start,
                                  replacement_segment_length=root.length))
    if not cases:
        raise ValueError('no actual named record/checkpoint flush boundaries')
    return {'schema_version': 1, 'status': 'OBSERVED',
            'scope': 'named actual flush ordinals; this plan is not fault acceptance',
            'baseline_generation': baseline['store_generation'],
            'reference_generation': root.generation, 'reference_sequence': sequence,
            'fault_choices': sorted(FAULT_EVENTS), 'cases': cases,
            'unnamed_flush_ordinals': [group['ordinal'] for group in groups
                                      if group['ordinal'] not in {case['ordinal'] for case in cases}],
            'reference_disk_sha256': sha(reference_disk.read_bytes()),
            'reference_media_sha256': sha(reference_media.read_bytes())}


def check(baseline_dir: Path, baseline_serial: Path, disk: Path, serial: Path,
          input_file: Path, input_manifest: Path, devices: Path, media: Path,
          case_file: Path) -> dict:
    case = json.loads(case_file.read_text())
    exported, before = baseline_export(baseline_dir)
    old_events = guest_observations(baseline_serial)
    old_states = [row for row in old_events if row[0] in (0x421, 0x423, 0x424)]
    if not old_states or old_states[-1][0] != 0x421 or old_states[-1][1] != exported['committed_sequence']:
        raise ValueError('baseline export lacks its final genuine guest 421 ACK witness')
    image = disk.read_bytes()
    root, sequence, records = recover(image)
    if sequence < exported['committed_sequence'] or root.generation < exported['store_generation']:
        raise ValueError('previously acknowledged store sequence/generation disappeared')
    after = notebook({key: record.payload for key, record in records.items() if record.kind == 1})
    retained_baseline(before, after)
    fixture, admitted = raw_provenance(input_file, input_manifest, devices)
    new_chunks = []
    for key, chunk in after.chunks.items():
        if key in before.chunks:
            continue
        if list(chunk.header[9:11]) != fixture['raw_coordinate_maximum'] or chunk.header[11] != fixture['pressure_maximum'] or list(chunk.header[12:14]) != fixture['geometry']:
            raise ValueError('new committed ink changed raw fixture calibration')
        provenance = [admitted.get(sample) for sample in chunk.samples]
        if None in provenance or len(set(provenance)) != 1 or provenance[0][:2] != (key[0], chunk.header[3]):
            raise ValueError('new committed chunk is not an exact original raw FIFO stroke subset')
        new_chunks.append({'namespace': key[0], 'object': key[1], 'stroke': chunk.header[4],
                           'raw_action': provenance[0][2], 'samples': len(chunk.samples),
                           'lifecycle': chunk.header[14], 'sha256': sha(after.payloads[key])})
    events = guest_observations(serial)
    if any(row[0] == 0x41f for row in events):
        raise ValueError('fault/recovery run unexpectedly formatted its nonempty medium')
    acknowledgements = [row[1:] for row in events if row[0] == 0x421]
    if any(ack[0] > sequence or ack[0] < exported['committed_sequence'] or ack[2] not in after.roots or (ack[2], ack[1]) not in after.pages for ack in acknowledgements):
        raise ValueError('guest acknowledged document work absent from stable recovered media')
    for ack_sequence, page_id, ns, stroke in acknowledgements:
        if stroke and (records[(ns, 1)].sequence < ack_sequence or
                       not any(entry[1] == stroke for entry in after.pages[ns, page_id].entries)):
            raise ValueError('guest stroke ACK preceded its recovered catalog/index publication')
    if any(b[0] < a[0] for a, b in zip(acknowledgements, acknowledgements[1:])):
        raise ValueError('guest ACK sequence moved backward')
    boundary = medium_boundary(media, case, exported['store_generation'])
    torn_payload_rejected = None
    if case['fault'] == 'tear-flush' and case['phase'] == 'payload':
        offset = case['record_header_sector'] * 512
        header = image[offset:offset + 512]
        fields = struct.unpack_from('<13Q', header)
        if (fields[:3] != (RECORD, 1, root.generation) or fields[11] != fnv(header[:88])
                or fields[12] != fields[11] ^ ((1 << 64) - 1) or any(header[104:])
                or fields[6] <= sequence or fields[7] > 32768
                or fields[9] != case['record_payload_sectors']
                or (case.get('record_namespace'), case.get('record_object')) != fields[3:5]):
            raise ValueError('torn payload lacked a stable new header excluded from committed recovery')
        payload = image[offset + 512:offset + 512 + fields[7]]
        if fnv(payload) == fields[10]:
            raise ValueError('torn payload did not exercise the actual incomplete-body checksum boundary')
        torn_payload_rejected = True
    if case['operation'] == 'checkpoint' and any(ack[3] == 0 for ack in acknowledgements) and root.generation <= exported['store_generation']:
        raise ValueError('checkpoint ACK preceded durable replacement root publication')
    # Failed flush must be visible to the guest; a cut exits the process before
    # any completion and therefore cannot require a subsequent guest marker.
    if case['fault'] == 'fail-flush' and not any(row[0] == 0x424 for row in events):
        raise ValueError('failed flush lacked guest Save failed/read-only observation')
    paths = (disk, baseline_serial, serial, input_file, input_manifest, devices, media, case_file)
    return {'schema_version': 1, 'status': 'PASS',
            'scope': 'offline independent stable-media/ACK/raw provenance observation; actual cold guest boot and visible comparison remain separate',
            'case': case, 'boundary': boundary, 'baseline_image_sha256': exported['image_sha256'],
            'baseline_sequence': exported['committed_sequence'], 'recovered_sequence': sequence,
            'baseline_generation': exported['store_generation'], 'recovered_generation': root.generation,
            'baseline_immutable_chunks_preserved': len(before.chunks),
            'baseline_pages_preserved': len(before.pages), 'new_wholly_valid_chunks': new_chunks,
            'guest_document_acknowledgements': acknowledgements,
            'torn_payload_incomplete_append_rejected': torn_payload_rejected,
            'observed_raw_fixture_prefix': fixture['observed_input_prefix'],
            'unobserved_raw_fixture_suffix': fixture['input_samples'] - fixture['observed_input_prefix'],
            'artifact_sha256': {str(path): sha(path.read_bytes()) for path in paths},
            'baseline_export_sha256': sha((baseline_dir / 'result.json').read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--reference-disk', type=Path)
    parser.add_argument('--reference-media', type=Path)
    for name in ('baseline-export', 'baseline-serial', 'disk', 'serial', 'input', 'input-manifest', 'devices', 'media', 'case', 'output'):
        parser.add_argument('--' + name, type=Path, required=name in ('baseline-export', 'output'))
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to overwrite retained crash observation')
    try:
        if args.plan:
            if not args.reference_disk or not args.reference_media:
                parser.error('--plan requires --reference-disk and --reference-media')
            result = plan(args.reference_disk, args.reference_media, args.baseline_export)
        else:
            for name in ('baseline_serial', 'disk', 'serial', 'input', 'input_manifest', 'devices', 'media', 'case'):
                if getattr(args, name) is None:
                    parser.error('--' + name.replace('_', '-') + ' is required for fault checking')
            result = check(args.baseline_export, args.baseline_serial, args.disk, args.serial,
                           args.input, args.input_manifest, args.devices, args.media, args.case)
    except (ValueError, KeyError, OSError, struct.error) as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    if result['status'] == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
