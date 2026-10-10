#!/usr/bin/env python3
"""Check actual guest/device/store notebook observations against raw inputs.

This is an independent offline evidence checker. It never draws the notebook,
repairs media, or supplies documents to a guest. A run without every required
observation fails, and cold reopening/replay must be exercised separately.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from store_oracle import recover

MAGIC = 0x314B4E49414D454C


def device_events(path: Path) -> list[tuple[int, str, int, int, int]]:
    observations = []
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 5:
            raise ValueError('truncated device observation')
        time, event, a, b, c = fields
        observation = (int(time), event, int(a), int(b), int(c))
        if observation[0] < 0 or (observations and observation[0] < observations[-1][0]):
            raise ValueError('backward device observation time')
        observations.append(observation)
    if not observations:
        raise ValueError('empty device observations')
    return observations


def guest_events(path: Path) -> list[tuple[int, int, int, int, int]]:
    return [tuple(int(word, 16) for word in row) for row in
            re.findall(rb'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})', path.read_bytes())]


def visible_pixels(path: Path) -> tuple[int, int, bytes]:
    ppm = path.read_bytes()
    header = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', ppm)
    if not header:
        raise ValueError('missing real controller visible output')
    width, height = map(int, header.groups())
    pixels = ppm[header.end():]
    if not width or not height or len(pixels) != width * height * 3:
        raise ValueError('visible geometry/byte length differs')
    return width, height, pixels


def check_toolbar_pixels(width: int, height: int, pixels: bytes) -> None:
    """Independent visible examples for the nine guest controls.

    Literal3x5 rows are independent of production Lean glyph constants and
    transitions. These points observe controller output; they never draw a
    host toolbar or provide pixels to the guest.
    """
    if not 512 <= width <= 4096 or not 320 <= height <= 4096 or len(pixels) != width * height * 3:
        raise ValueError('toolbar observation geometry or length differs')
    glyphs = (
        ('101', '101', '111', '101', '101'),  # H: notebook/home
        ('010', '100', '111', '100', '010'),  # previous
        ('010', '001', '111', '001', '010'),  # next/add
        ('101', '101', '101', '101', '111'),  # U: undo
        ('110', '101', '110', '101', '101'),  # R: redo
        ('111', '100', '110', '100', '111'),  # E: stroke erase
        ('101', '101', '101', '111', '111'),  # W: brush width
        ('111', '100', '111', '001', '111'),  # S: short Save
        ('111', '100', '100', '100', '111'),  # C: explicit Compact
    )
    for button, rows in enumerate(glyphs):
        for row, pattern in enumerate(rows):
            for column, bit in enumerate(pattern):
                x = button * (width // 9) + 24 + column * 12 + 1
                y = 36 + row * 12 + 1
                offset = (y * width + x) * 3
                expected = bytes([0 if bit == '1' else 255]) * 3
                if pixels[offset:offset + 3] != expected:
                    raise ValueError(f'guest nine-tool toolbar glyph differs at control{button}/cell{column},{row}')


def join_chunks(chunks: list[tuple[tuple[int, ...], list[tuple[int, ...]]]]) -> list[tuple[int, ...]]:
    """Independent literal lifecycle/duplication rules, without raster code."""
    if not chunks:
        raise ValueError('empty stroke history')
    samples = []
    for index, (header, current) in enumerate(chunks):
        lifecycle = header[14]
        if not current or lifecycle not in ((1, 3) if index == 0 else (4, 6)):
            raise ValueError('missing stroke start or unsupported continuation boundary')
        if index:
            if chunks[index - 1][0][14] & 2 or current[0] != samples[-1]:
                raise ValueError('continuation does not repeat exactly the prior final raw sample')
            current = current[1:]
        if not current:
            raise ValueError('continuation contains no new raw input')
        if not samples and not (current[0][5] & 1):
            raise ValueError('stroke began without an original contact sample')
        if any(not (sample[5] & 1) for sample in current[:-1]):
            raise ValueError('stroke crossed a pen-up boundary')
        if lifecycle & 2 and (current[-1][5] & 1):
            raise ValueError('completed stroke has no original pen-up')
        if samples and current[0][0] != samples[-1][0] + 1:
            raise ValueError('stroke crossed an unexplained controller sequence boundary')
        samples.extend(current)
    if not chunks[-1][0][14] & 2 or len(set(samples)) != len(samples):
        raise ValueError('unfinished stroke or duplicate raw sample beyond the declared continuation boundary')
    return samples


def check(disk: Path, input_file: Path, manifest_file: Path, device_file: Path,
          serial_file: Path, visible_file: Path) -> dict:
    manifest = json.loads(manifest_file.read_text())
    raw = input_file.read_bytes()
    if manifest.get('schema_version') != 1 or manifest.get('profile') != 'lemmasim-virt/0.1.0':
        raise ValueError('unknown raw fixture identity')
    if not raw or len(raw) % 72 or hashlib.sha256(raw).hexdigest() != manifest['input_sha256']:
        raise ValueError('incomplete or changed raw input')
    samples = [struct.unpack_from('<9Q', raw, offset) for offset in range(0, len(raw), 72)]
    if len(samples) != manifest['input_samples']:
        raise ValueError('raw input count differs')
    ingress, rejected = {}, {}
    completed = []
    observations = device_events(device_file)
    loss_expected = manifest['expected'].get('loss')
    watchdogs = []
    for time, event, a, b, c in observations:
        if event in ('pen-input', 'pen-input-rejected'):
            if a in ingress or a in rejected or not 1 <= a <= len(samples):
                raise ValueError('duplicated or invalid ingress observation')
            if time < samples[a - 1][1] * 100:
                raise ValueError('input arrived before its recorded virtual deadline')
        if event == 'pen-input':
            if not b or not c:
                raise ValueError('duplicated or invalid ingress observation')
            ingress[a] = (b, c)
        elif event == 'pen-input-rejected':
            if b or not c:
                raise ValueError('rejected input has fabricated controller sequence')
            rejected[a] = c
        if event == 'pen-watchdog-loss':
            watchdogs.append((time, a, b))
        if event == 'paper-complete':
            completed.append((time, a))
    if not completed or any(b[1] <= a[1] for a, b in zip(completed, completed[1:])):
        raise ValueError('missing or out-of-order actual display completions')
    if set(ingress) | set(rejected) != set(range(1, len(samples) + 1)):
        raise ValueError('missing or truncated raw device ingress')
    if loss_expected:
        boundary = loss_expected['boundary_first_sequence']
        release = loss_expected['resync_release_sequence']
        allowed = {1, release} | set(range(boundary, loss_expected['cancelled_last_sequence'] + 1))
        if set(rejected) - allowed:
            raise ValueError('unexpected rejection outside the declared loss boundary')
        if loss_expected['kind'] == 'watchdog':
            if not watchdogs:
                raise ValueError('lost pen-up did not assert the actual watchdog loss boundary')
        elif boundary not in rejected:
            # The overflow occurs after 256 accepted samples in its same-time
            # burst, while disconnect rejects its first boundary event.
            if loss_expected['kind'] != 'overflow' or not (set(rejected) & allowed - {1, release}):
                raise ValueError('declared input loss did not reach the actual device')
    elif watchdogs or set(rejected) - {1}:
        raise ValueError('workflow admitted a lost contact or rejected ordinary input')
    expected_samples = {}
    actions = [action for action in manifest['actions'] if action['kind'] == 'stroke']
    for action in actions:
        identity = (action['namespace'], action['name'])
        expected_samples[identity] = set()
        for sequence in range(action['first_sequence'], action['last_sequence'] + 1):
            if sequence not in ingress:
                raise ValueError(f'writing input {sequence} never entered the device FIFO')
            sample = samples[sequence - 1]
            guest_sequence, epoch = ingress[sequence]
            expected_samples[identity].add((guest_sequence, *sample[1:8], epoch))

    root, sequence, records = recover(disk.read_bytes())
    pages, chunks, roots = {}, {}, {}
    for (namespace, object_id), record in records.items():
        if record.kind == 2:
            continue
        data = record.payload
        if len(data) < 64:
            raise ValueError('short document header')
        fields = struct.unpack_from('<8Q', data)
        if fields[0] != MAGIC or (fields[1] != 1 and not (fields[1] == 2 and fields[2] == 2)):
            raise ValueError('unknown document format')
        if fields[2] == 1:
            if object_id != 1 or len(data) != 64 or not 1 <= fields[3] <= 64:
                raise ValueError('invalid notebook root')
            roots[namespace] = fields[3]
        elif fields[2] == 2:
            expected_bytes = 20608 if fields[1] == 1 else 128 + fields[4] * 24 + fields[5] * 16
            if len(data) != expected_bytes or object_id != 256 + fields[3] or fields[4] > 512 or fields[5] > 512 or fields[6] > fields[5]:
                raise ValueError('invalid page index')
            entries = [struct.unpack_from('<3Q', data, 128 + index * 24) for index in range(fields[4])]
            edit_offset = 12416 if fields[1] == 1 else 128 + fields[4] * 24
            if fields[1] == 2 and any(data[56:128]):
                raise ValueError('nonzero mandatory page reserved fields')
            edits = [struct.unpack_from('<2Q', data, edit_offset + index * 16) for index in range(fields[5])]
            visibility = {}
            for kind, stroke in edits[:fields[6]]:
                if kind not in (1, 2) or not stroke:
                    raise ValueError('unknown editing operation')
                visibility[stroke] = int(kind == 1)
            if any(not stroke or flag not in (0, 1) or visibility.get(stroke) != flag for _, stroke, flag in entries):
                raise ValueError('recovered flags disagree with independent edit replay')
            pages[namespace, fields[3]] = (entries, edits, fields[6])
        elif fields[2] == 3:
            if len(data) < 128:
                raise ValueError('short raw chunk')
            header = struct.unpack_from('<16Q', data)
            if not 1 <= header[6] <= 384 or len(data) != 128 + header[6] * 72 or header[8] != 1 or header[14] & ~7:
                raise ValueError('invalid raw ink envelope')
            if header[5] or header[15] or not 1 <= header[3] <= 64 or not header[4] or not 256 <= header[7] <= 8192:
                raise ValueError('invalid raw ink identity, brush, or reserved words')
            if list(header[9:11]) != manifest['raw_coordinate_maximum'] or header[11] != manifest['pressure_maximum']:
                raise ValueError('raw ink lost its original device calibration')
            if list(header[12:14]) != manifest['geometry']:
                raise ValueError('raw ink lost its original screen geometry')
            chunk_samples = [struct.unpack_from('<9Q', data, 128 + index * 72) for index in range(header[6])]
            if any(sample[2] > header[9] or sample[3] > header[10] or sample[4] > header[11]
                   or sample[5] & ~7 or sample[6] > 2 or sample[7] & ~7 for sample in chunk_samples):
                raise ValueError('raw ink retained invalid or disconnected device input')
            if any(b[0] != a[0] + 1 or b[1] < a[1] or b[8] != a[8] for a, b in zip(chunk_samples, chunk_samples[1:])):
                raise ValueError('raw chunk joined an unexplained input boundary')
            chunks[namespace, object_id] = (header, chunk_samples)
        else:
            raise ValueError('unknown record kind')

    for ns, expected_pages in manifest['expected']['pages'].items():
        namespace = int(ns)
        if roots.get(namespace) != max(expected_pages):
            raise ValueError('notebook page count differs from raw workflow')
        if sorted(page for observed_ns, page in pages if observed_ns == namespace) != expected_pages:
            raise ValueError('created/opened pages differ from raw workflow')
    actual_strokes = {}
    stroke_chunks = {}
    visible_strokes = {}
    for (namespace, page), (entries, edits, cursor) in pages.items():
        visible_strokes[namespace, page] = set()
        for object_id, stroke_id, visible in entries:
            if (namespace, object_id) not in chunks:
                raise ValueError('published index references absent chunk')
            header, chunk_samples = chunks[namespace, object_id]
            if (header[3], header[4]) != (page, stroke_id):
                raise ValueError('indexed chunk identity contradicts page/stroke')
            stroke_chunks.setdefault((namespace, stroke_id), []).append((header, chunk_samples))
            if visible:
                visible_strokes[namespace, page].add(stroke_id)
        expected_edits = manifest['expected'].get('required_edit_history', {}).get(f'{namespace}/{page}')
        if expected_edits is not None and (len(edits), cursor) != (expected_edits, expected_edits):
            raise ValueError('undo/redo/erase edit history differs')
    for identity, items in stroke_chunks.items():
        actual_strokes[identity] = set(join_chunks(items))
    names = {}
    for identity, expected in expected_samples.items():
        matches = [stroke_id for (ns, stroke_id), observed in actual_strokes.items()
                   if ns == identity[0] and observed == expected]
        if len(matches) != 1:
            raise ValueError(f'raw stroke {identity} not retained exactly once')
        names[identity] = matches[0]
        action = next(row for row in actions if (row['namespace'], row['name']) == identity)
        brushes = {header[7] for header, _ in stroke_chunks[identity[0], matches[0]]}
        if brushes != {action.get('brush_q8', 512)}:
            raise ValueError('guest brush selection was not retained with the original stroke')
    if len(actual_strokes) != len(expected_samples):
        raise ValueError('unexpected retained stroke or host/application shortcut')
    for identity, expected_names in manifest['expected']['visible_strokes'].items():
        ns, page = map(int, identity.split('/'))
        if visible_strokes.get((ns, page)) != {names[ns, name] for name in expected_names}:
            raise ValueError('visible stroke IDs differ after editing/reopening')
    retained = sum(len(value) for value in actual_strokes.values())
    if retained != manifest['expected']['retained_raw_samples']:
        raise ValueError('retained raw workload count differs')
    events = guest_events(serial_file)
    if not any(row[0] == 0x420 for row in events):
        raise ValueError('guest page-ready observation absent')
    acknowledgements = [row[1:] for row in events if row[0] == 0x421]
    if not acknowledgements or any(ack[0] > sequence for ack in acknowledgements):
        raise ValueError('missing or contradictory durable document acknowledgements')
    states = [row for row in events if row[0] in (0x421, 0x423, 0x424)]
    if states[-1][0] != 0x421 or acknowledgements[-1][0] != sequence:
        raise ValueError('workflow ended with pending, failed, or unacknowledged document publication')
    width, height, pixels = visible_pixels(visible_file)
    if [width, height] != manifest['geometry']:
        raise ValueError('visible geometry/byte length differs')
    check_toolbar_pixels(width, height, pixels)
    final_view = manifest['expected']['final_view']
    selected = [action for action in actions if action['namespace'] == final_view['namespace']
                and action['page'] == final_view['page']
                and action['name'] in manifest['expected']['visible_strokes'][f"{final_view['namespace']}/{final_view['page']}"]]
    if not selected:
        raise ValueError('fixture has no final visible writing')
    for action in selected:
        sample = samples[action['first_sequence'] - 1]
        x, y = sample[2] * (width - 1) // 65535, sample[3] * (height - 1) // 65535
        # Known contact centers must leave actual black controller pixels. This
        # literal neighborhood observes pixels; it is not a host brush algorithm.
        observed = any(pixels[(py * width + px) * 3:(py * width + px) * 3 + 3] == b'\0\0\0'
                       for py in range(max(160, y - 2), min(height, y + 3))
                       for px in range(max(0, x - 2), min(width, x + 3)))
        if not observed:
            raise ValueError('retained writing did not produce actual visible controller pixels')
    if loss_expected:
        before = expected_samples[1, 'before loss']
        after = expected_samples[1, 'after loss']
        if {sample[8] for sample in before} & {sample[8] for sample in after}:
            raise ValueError('writing resumed without a new controller epoch after input loss')
        for key in ('cancelled_pixel', 'joining_pixel'):
            x, y = loss_expected[key]
            if any(pixels[(py * width + px) * 3:(py * width + px) * 3 + 3] == b'\0\0\0'
                   for py in range(y - 2, y + 3) for px in range(x - 2, x + 3)):
                raise ValueError('cancelled input tail or fabricated connecting line remained on actual visible paper')
    return {'schema_version': 1, 'status': 'PASS',
            'scope': 'raw device input to genuine guest committed ink/edit bytes and real display observations; cold restart/replay separate',
            'workflow': manifest['workflow'], 'store_generation': root.generation,
            'committed_sequence': sequence, 'retained_unique_raw_samples': retained,
            'stroke_count': len(actual_strokes), 'page_count': len(pages),
            'notebooks': sorted(roots), 'guest_document_acknowledgements': acknowledgements,
            'guest_toolbar_literal_cells': 135,
            'loss_boundary': loss_expected, 'rejected_ingress': sorted(rejected),
            'paper_completions': completed,
            'artifact_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (disk, input_file, manifest_file, device_file, serial_file, visible_file)}}


def committed_bytes(path: Path) -> tuple[int, dict[str, str], str]:
    """Observe committed bytes; this never supplies recovery data to the guest."""
    _, sequence, records = recover(path.read_bytes())
    observations = {}
    digest = hashlib.sha256()
    for (namespace, object_id), record in sorted(records.items()):
        identity = struct.pack('<4Q', namespace, object_id, record.kind, len(record.payload))
        digest.update(identity)
        digest.update(record.payload)
        observations[f'{namespace}/{object_id}'] = hashlib.sha256(identity + record.payload).hexdigest()
    if not observations:
        raise ValueError('cold comparison has no committed document records')
    return sequence, observations, digest.hexdigest()


def check_cold(before_disk: Path, after_disk: Path, before_visible: Path,
               after_visible: Path, cold_serial: Path, cold_devices: Path) -> dict:
    """Compare a new CPU/guest boot's observations with an acknowledged view.

    The caller launches a real new process from retained durable media and,
    when needed, navigates to the same page through raw input. No RAM snapshot,
    retained panel state, parsed document object, or host drawing enters it.
    """
    before_sequence, before_records, before_digest = committed_bytes(before_disk)
    after_sequence, after_records, after_digest = committed_bytes(after_disk)
    if (before_sequence, before_records) != (after_sequence, after_records):
        raise ValueError('cold guest reopening changed or lost committed document bytes')
    before = visible_pixels(before_visible)
    after = visible_pixels(after_visible)
    if before != after:
        raise ValueError('cold guest redraw does not reproduce the same actual visible pixels')
    observations = device_events(cold_devices)
    completions = [row for row in observations if row[1] == 'paper-complete']
    if not completions or any(b[2] <= a[2] for a, b in zip(completions, completions[1:])):
        raise ValueError('cold guest did not complete a fresh controller redraw')
    events = guest_events(cold_serial)
    ready = [row for row in events if row[0] == 0x420]
    if len(ready) != 1 or ready[0][4] not in {row[2] for row in completions}:
        raise ValueError('cold guest page-ready refresh did not reach actual controller completion')
    if ready[0][1] != before[0] | (before[1] << 32):
        raise ValueError('cold guest ready geometry differs from the compared display')
    if any(row[0] in (0x41f, 0x423, 0x424) for row in events):
        raise ValueError('cold reopening formatted, republished, or failed instead of reading the saved document')
    paths = (before_disk, after_disk, before_visible, after_visible, cold_serial, cold_devices)
    return {'schema_version': 1, 'status': 'PASS',
            'scope': 'independent comparison of cold guest committed bytes and exact controller-visible pixels',
            'committed_sequence': after_sequence, 'committed_document_sha256': after_digest,
            'committed_record_sha256': after_records, 'visible_pixels_sha256': hashlib.sha256(after[2]).hexdigest(),
            'geometry': list(after[:2]), 'cold_paper_completions': [list(row) for row in completions],
            'artifact_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('disk', 'input', 'manifest', 'devices', 'serial', 'visible', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to overwrite retained workflow result')
    try:
        result = check(args.disk, args.input, args.manifest, args.devices, args.serial, args.visible)
    except (ValueError, OSError, KeyError, struct.error) as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'workflow', 'retained_unique_raw_samples', 'page_count', 'notebooks', 'error') if key in result}))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
