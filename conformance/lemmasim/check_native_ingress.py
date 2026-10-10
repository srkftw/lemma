#!/usr/bin/env python3
"""Independently match native QMP pointer commands, captured raw, and ingress.

This offline observer neither draws pixels nor parses/restores notebook media.
Only validated captured input supplies the fixture for the separate guest ink
and cold-recovery observer. Pressure here is explicitly synthetic mouse input.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

SCHEMA = 1
DEVICE = 'lemma-hardware'
SOURCE = 'qmp-native-pointer'
MAX_COMMANDS = 10000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scale_axis(value: int) -> int:
    """Literal pinned QEMU integer scale, input0..32767/output0..65535."""
    if type(value) is not int or not 0 <= value <= 32767:
        raise ValueError('native absolute coordinate outside literal QMP range')
    return value * 65535 // 32767


def command_rows(path: Path) -> list[dict]:
    plan = json.loads(path.read_text())
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'source', 'device', 'commands'}:
        raise ValueError('unknown native command manifest fields')
    if plan['schema_version'] != SCHEMA or plan['source'] != SOURCE or plan['device'] != DEVICE:
        raise ValueError('unknown native command source/device identity')
    rows = plan['commands']
    if not isinstance(rows, list) or not 3 <= len(rows) <= MAX_COMMANDS:
        raise ValueError('empty/unbounded native command stream')
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {'x', 'y', 'down'} or type(row['down']) is not bool:
            raise ValueError('native command must contain exactly x/y/left down')
        scale_axis(row['x']); scale_axis(row['y'])
        if row['down'] != (0 < index < len(rows) - 1):
            raise ValueError('native fixture must have release, one contact run, final release')
    if (rows[-1]['x'], rows[-1]['y']) != (rows[-2]['x'], rows[-2]['y']):
        raise ValueError('final native release must retain the last contact coordinates')
    return rows


def captured_rows(path: Path, commands: list[dict]) -> list[tuple[int, ...]]:
    raw = path.read_bytes()
    if not raw or len(raw) != len(commands) * 72:
        raise ValueError('missing, extra or truncated captured native raw input')
    rows = [struct.unpack_from('<9Q', raw, offset) for offset in range(0, len(raw), 72)]
    for index, (actual, command) in enumerate(zip(rows, commands), 1):
        ordinal, ticks, x, y, pressure, flags, tool, buttons, epoch = actual
        expected = (scale_axis(command['x']), scale_axis(command['y']),
                    2047 if command['down'] else 0, 7 if command['down'] else 6, 1, 0, 1)
        if ordinal != index or ticks > ((1 << 63) - 1) // 100:
            raise ValueError('invalid native capture ordinal or guest timestamp')
        if index > 1 and ticks < rows[index - 2][1]:
            raise ValueError('backward native capture guest time')
        if (x, y, pressure, flags, tool, buttons, epoch) != expected:
            raise ValueError(f'native capture differs from literal QMP command{index}')
    return rows


def ingress_rows(path: Path, samples: list[tuple[int, ...]]) -> tuple[dict, dict]:
    accepted, rejected = {}, {}
    previous_time = 0
    ingress_order = []
    text = path.read_text()
    if not text.strip():
        raise ValueError('empty actual device ingress trace')
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 5:
            raise ValueError('truncated actual device trace')
        try:
            timestamp, a, b, c = (int(fields[i]) for i in (0, 2, 3, 4))
        except ValueError as error:
            raise ValueError('malformed actual device trace number') from error
        if min(timestamp, a, b, c) < 0 or timestamp < previous_time:
            raise ValueError('backward/negative actual device trace')
        previous_time = timestamp
        event = fields[1]
        if event == 'pen-watchdog-loss':
            raise ValueError('native contact was lost before release')
        if event not in ('pen-input', 'pen-input-rejected'):
            continue
        if not 1 <= a <= len(samples) or a in accepted or a in rejected:
            raise ValueError('duplicated or invalid actual native ingress ordinal')
        # Native sync samples the same monotonic10MHz clock as trace emission.
        # The raw timestamp is its floor-to-ticks value, not a host schedule.
        if not samples[a - 1][1] * 100 <= timestamp < (samples[a - 1][1] + 1) * 100:
            raise ValueError('actual native ingress differs from captured guest time')
        if not c:
            raise ValueError('actual native ingress omitted controller epoch')
        ingress_order.append(a)
        if event == 'pen-input':
            if not b:
                raise ValueError('accepted native input omitted controller sequence')
            accepted[a] = {'sequence': b, 'epoch': c, 'time_ns': timestamp}
        else:
            if a != 1 or b:
                raise ValueError('ordinary native input was rejected outside initial release')
            rejected[a] = {'epoch': c, 'time_ns': timestamp}
    if ingress_order != list(range(1, len(samples) + 1)):
        raise ValueError('missing, out-of-order or truncated actual native ingress')
    retained = [accepted[i] for i in range(2, len(samples) + 1)]
    if any(current['sequence'] != previous['sequence'] + 1 or current['epoch'] != previous['epoch']
           for previous, current in zip(retained, retained[1:])):
        raise ValueError('native stroke crossed controller sequence/epoch boundary')
    return accepted, rejected


def check(raw: Path, commands: Path, devices: Path, *, geometry=(1650, 2200)) -> tuple[dict, dict]:
    if len(geometry) != 2 or any(type(n) is not int or not 32 <= n <= 4096 for n in geometry):
        raise ValueError('invalid native fixture geometry')
    planned = command_rows(commands)
    samples = captured_rows(raw, planned)
    accepted, rejected = ingress_rows(devices, samples)
    identity = {'raw_sha256': sha(raw), 'commands_sha256': sha(commands), 'devices_sha256': sha(devices)}
    fixture = {'schema_version': 1, 'profile': 'lemmasim-virt/0.1.0', 'workflow': 'native-pointer',
               'geometry': list(geometry),
               'raw_coordinate_maximum': [65535, 65535], 'pressure_maximum': 4095,
               'input_samples': len(samples), 'input_sha256': identity['raw_sha256'],
               'source': 'native QMP absolute pointer; synthetic pressure; actual captured guest ticks',
               'native_command_sha256': identity['commands_sha256'],
               'actions': [{'kind': 'stroke', 'namespace': 1, 'page': 1, 'name': 'native-pointer-stroke',
                            'first_sequence': 2, 'last_sequence': len(samples), 'brush_q8': 512}],
               'expected': {'pages': {'1': [1]}, 'final_view': {'namespace': 1, 'page': 1},
                            'visible_strokes': {'1/1': ['native-pointer-stroke']},
                            'retained_raw_samples': len(samples) - 1}}
    result = {'schema_version': 1, 'status': 'PASS',
              'scope': 'native commands/captured raw/controller ingress only; guest ink/pixels/store/cold observed separately',
              'identity': identity, 'geometry': list(geometry), 'captured_samples': len(samples),
              'retained_stroke_samples': len(samples) - 1, 'accepted_ordinals': sorted(accepted),
              'initial_resync_release_rejected': 1 in rejected,
              'first_stroke_ingress': accepted[2], 'last_stroke_ingress': accepted[len(samples)],
              'first_guest_ticks': samples[0][1], 'last_guest_ticks': samples[-1][1]}
    return result, fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--commands', type=Path, required=True)
    parser.add_argument('--devices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1650)
    parser.add_argument('--height', type=int, default=2200)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        result, fixture = check(args.raw, args.commands, args.devices, geometry=(args.width, args.height))
        (args.output / 'fixture.json').write_text(json.dumps(fixture, indent=2, sort_keys=True) + '\n')
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {'schema_version': 1, 'status': 'FAIL', 'error': str(error)}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
