#!/usr/bin/env python3
"""Create raw pen-controller inputs for the genuine guest notebook.

This host-only fixture supplies original device samples and their expected input
identity. It does not draw, serialize documents, call application functions, or
feed a guest recovery result. Times are 10 MHz monotonic virtual ticks; arrival
uses the modeled device's QEMU timer, never host sleeps.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path


class Input:
    def __init__(self, width: int, height: int, first: int, interval: int, gap: int):
        self.width, self.height = width, height
        self.tick, self.interval, self.gap = first, interval, gap
        self.events = []
        self.actions = []

    @staticmethod
    def raw(pixel: int, dimension: int) -> int:
        return (pixel * 65535 + dimension - 2) // (dimension - 1)

    def sample(self, x: int, y: int, pressure: int, contact: bool, *, flags: int | None = None):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError('fixture point outside queried geometry')
        self.events.append((len(self.events) + 1, self.tick, self.raw(x, self.width),
                            self.raw(y, self.height), pressure, (3 if contact else 2) if flags is None else flags,
                            1, 0, 1))
        self.tick += self.interval

    def stroke(self, name: str, page: int, namespace: int, count: int, row: int, brush: int = 512):
        if count < 3:
            raise ValueError('a stroke needs contact samples plus pen-up')
        start = len(self.events) + 1
        # A bounded triangle trace, retained as raw samples by the guest. Its
        # pressure changes independently of the integer display/raster algorithm.
        for index in range(count - 1):
            phase = index % 80
            x = self.width // 5 + (phase if phase < 40 else 80 - phase) * self.width // 160
            y = row + (index % 32) * 2
            self.sample(x, y, 1024 + (index % 16) * 192, True)
        self.sample(x, y, 0, False)
        self.actions.append({'kind': 'stroke', 'name': name, 'namespace': namespace,
                             'page': page, 'first_sequence': start,
                             'last_sequence': len(self.events), 'raw_samples': count,
                             'brush_q8': brush})
        self.tick += self.gap

    def tool(self, button: int, name: str):
        start = len(self.events) + 1
        x = (button * 2 + 1) * (self.width // 8) // 2
        self.sample(x, 64, 2048, True)
        self.sample(x, 64, 0, False)
        self.actions.append({'kind': 'tool', 'name': name, 'button': button,
                             'first_sequence': start, 'last_sequence': len(self.events)})
        self.tick += self.gap


def generate(workflow: str, width: int, height: int, first: int, interval: int, gap: int):
    stream = Input(width, height, first, interval, gap)
    # A release boundary is explicit even when the fresh device is resynchronizing.
    stream.sample(width // 2, 160, 0, False)
    if workflow == 'basic':
        stream.stroke('a', 1, 1, 25, height // 3)
        stream.stroke('b', 1, 1, 25, height // 2)
        expected = {'pages': {'1': [1]}, 'visible_strokes': {'1/1': ['a', 'b']},
                    'retained_raw_samples': 50, 'final_view': {'namespace': 1, 'page': 1}}
    elif workflow == 'editing':
        stream.stroke('a', 1, 1, 25, height // 3)
        stream.stroke('b', 1, 1, 25, height // 2)
        stream.tool(3, 'undo b')
        stream.tool(4, 'redo b')
        stream.tool(5, 'erase latest b')
        stream.tool(2, 'add page2')
        stream.tool(6, 'select width4')
        stream.stroke('c', 2, 1, 25, height // 3, brush=1024)
        stream.tool(0, 'create/open notebook2')
        stream.stroke('d', 1, 2, 25, height // 2, brush=1024)
        stream.tool(0, 'reopen notebook1 page1')
        stream.tool(7, 'save checkpoint')
        expected = {'pages': {'1': [1, 2], '2': [1]},
                    'visible_strokes': {'1/1': ['a'], '1/2': ['c'], '2/1': ['d']},
                    'retained_raw_samples': 100, 'final_view': {'namespace': 1, 'page': 1}, 'required_edit_history': {'1/1': 3}}
    elif workflow == 'workload':
        for page in range(1, 17):
            stream.stroke(f'page{page}', page, 1, 6250, height // 3)
            if page < 16:
                stream.tool(2, f'add page{page + 1}')
        stream.tool(7, 'save checkpoint')
        expected = {'pages': {'1': list(range(1, 17))},
                    'visible_strokes': {f'1/{page}': [f'page{page}'] for page in range(1, 17)},
                    'retained_raw_samples': 100000, 'final_view': {'namespace': 1, 'page': 16}}
    elif workflow in ('loss-overflow', 'loss-disconnect', 'loss-watchdog'):
        stream.stroke('before loss', 1, 1, 25, height // 3)
        # A short uncompleted contact remains in the guest's unsaved tail. Its
        # location is separate from both acknowledged strokes so literal pixels
        # can reveal a fabricated joining line or a failure to repaint it.
        cancelled_first = len(stream.events) + 1
        x, y = width * 3 // 4, height * 3 // 4
        for offset in range(8):
            stream.sample(x + offset, y + offset, 2048, True)
        boundary_first = len(stream.events) + 1
        if workflow == 'loss-overflow':
            # All 300 arrivals are due at one virtual instant. The QEMU timer
            # callback feeds the real 256-slot FIFO before guest execution resumes.
            tick = stream.tick
            for _ in range(300):
                stream.tick = tick
                stream.sample(x, y, 2048, True)
        elif workflow == 'loss-disconnect':
            stream.sample(x, y, 0, False, flags=8)
        else:
            # Omit pen-up and allow the device's declared one-second contact
            # watchdog to assert its out-of-band loss interrupt.
            stream.tick += 20000000
        boundary_last = len(stream.events)
        stream.actions.append({'kind': 'cancelled-contact', 'name': workflow,
                               'first_sequence': cancelled_first,
                               'last_sequence': boundary_last,
                               'boundary_first_sequence': boundary_first})
        stream.tick += stream.gap
        stream.sample(x, y, 0, False)
        resync_release = len(stream.events)
        stream.tick += stream.gap
        stream.stroke('after loss', 1, 1, 25, height // 2)
        expected = {'pages': {'1': [1]},
                    'visible_strokes': {'1/1': ['before loss', 'after loss']},
                    'retained_raw_samples': 50, 'final_view': {'namespace': 1, 'page': 1},
                    'loss': {'kind': workflow.removeprefix('loss-'),
                             'cancelled_first_sequence': cancelled_first,
                             'cancelled_last_sequence': boundary_last,
                             'boundary_first_sequence': boundary_first,
                             'resync_release_sequence': resync_release,
                             'cancelled_pixel': [x, y],
                             'joining_pixel': [(x + width // 5) // 2,
                                               (y + height // 2) // 2]}}
    else:
        raise ValueError('unknown workflow')
    payload = b''.join(struct.pack('<9Q', *event) for event in stream.events)
    return payload, {'schema_version': 1, 'profile': 'lemmasim-virt/0.1.0',
                     'workflow': workflow, 'geometry': [width, height],
                     'raw_coordinate_maximum': [65535, 65535], 'pressure_maximum': 4095,
                     'pressure_provenance': 'SYNTHETIC_RECORDED',
                     'physical_tablet_exercised': False, 'clock_hz': 10000000,
                     'first_tick': first, 'sample_interval_ticks': interval,
                     'action_gap_ticks': gap, 'last_tick': stream.events[-1][1],
                     'input_samples': len(stream.events),
                     'input_sha256': hashlib.sha256(payload).hexdigest(),
                     'actions': stream.actions, 'expected': expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow', choices=('basic', 'editing', 'workload',
                        'loss-overflow', 'loss-disconnect', 'loss-watchdog'), default='basic')
    parser.add_argument('--geometry', default='1650x2200')
    parser.add_argument('--first-tick', type=int, default=200000000)
    parser.add_argument('--sample-interval-ticks', type=int, default=100000)
    parser.add_argument('--action-gap-ticks', type=int, default=200000000)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.manifest.exists():
        parser.error('refusing to overwrite retained inputs')
    width, height = map(int, args.geometry.split('x'))
    if (width, height) not in ((1650, 2200), (1404, 1872)):
        parser.error('unsupported geometry fixture')
    if args.first_tick < 0 or not 1 <= args.sample_interval_ticks < 10000000 or args.action_gap_ticks < 0:
        parser.error('invalid monotonic timing; contact intervals must stay below watchdog')
    data, manifest = generate(args.workflow, width, height, args.first_tick,
                              args.sample_interval_ticks, args.action_gap_ticks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    args.manifest.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({key: manifest[key] for key in ('workflow', 'input_samples', 'input_sha256', 'last_tick')}))


if __name__ == '__main__':
    main()
