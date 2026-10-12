#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only Linux evdev tablet transport; no gesture or notebook commands."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import platform
import select
import signal
import struct
import threading
from typing import Callable

EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SYN_REPORT, SYN_DROPPED = 0, 3
ABS_X, ABS_Y, ABS_PRESSURE, ABS_TILT_X, ABS_TILT_Y = 0, 1, 24, 26, 27
BTN_TOOL_PEN, BTN_TOOL_RUBBER = 0x140, 0x141
BTN_STYLUS3, BTN_TOUCH, BTN_STYLUS, BTN_STYLUS2 = 0x149, 0x14a, 0x14b, 0x14c
INPUT_EVENT = struct.Struct('@llHHi')
ABS_INFO = struct.Struct('=6i')
MAX_FRAME_EVENTS, MAX_CAPTURE_BYTES, MAX_CAPTURE_FRAMES = 128, 256*1024*1024, 1000000


def _ioctl_read(fd: int, number: int, length: int) -> bytes:
    # Linux x86_64 asm-generic _IOC_READ, input.h EVIOCG* requests.
    value = bytearray(length)
    fcntl.ioctl(fd, (2 << 30) | (length << 16) | (ord('E') << 8) | number, value, True)
    return bytes(value)


def _bits(value: bytes) -> set[int]:
    return {i for i in range(len(value)*8) if value[i//8] & (1 << (i%8))}


@dataclass(frozen=True)
class Axis:
    minimum: int
    maximum: int
    fuzz: int = 0
    flat: int = 0
    resolution: int = 0

    def __post_init__(self):
        if self.maximum <= self.minimum or min(self.fuzz, self.flat, self.resolution) < 0:
            raise ValueError('Invalid reported tablet axis range')

    def normalize(self, value: int, maximum: int) -> int:
        if not self.minimum <= value <= self.maximum:
            raise ValueError('Tablet sample outside reported axis range')
        return (value-self.minimum)*maximum//(self.maximum-self.minimum)


@dataclass(frozen=True)
class Capabilities:
    name: str
    axes: dict[int, Axis]
    keys: frozenset[int]
    reported_axes: frozenset[int] | None = None

    def __post_init__(self):
        if not {ABS_X, ABS_Y} <= self.axes.keys() or BTN_TOUCH not in self.keys:
            raise ValueError('Tablet must report absolute X/Y and contact')
        if not {BTN_TOOL_PEN, BTN_TOOL_RUBBER} & self.keys:
            raise ValueError('Selected input does not report a pen/eraser tool')

    def report(self) -> dict:
        return {'schema': 'lemma-linux-tablet-capabilities/1', 'name': self.name,
                'host_binding': 'linux-evdev-x86_64/1',
                'axes': {str(k): vars(v) for k, v in self.axes.items()}, 'keys': sorted(self.keys),
                'reported_absolute_axes': sorted(self.reported_axes or self.axes),
                'untransported_absolute_axes': sorted(set(self.reported_axes or self.axes)-{ABS_X,ABS_Y,ABS_PRESSURE}),
                'pressure_reported': ABS_PRESSURE in self.axes,
                'pressure_wire_when_absent': 0, 'pressure_when_absent': 'UNAVAILABLE',
                'tilt_reported': ABS_TILT_X in self.axes or ABS_TILT_Y in self.axes,
                'tilt_transport': 'UNSUPPORTED_BY_PEN_V1',
                'normalization': 'integer (value-min)*wire_max/(max-min); x/y max65535, pressure max4095',
                'physical_registration': 'UNVERIFIED', 'gesture_interpretation': False}


def probe(fd: int) -> Capabilities:
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or INPUT_EVENT.size != 24:
        raise RuntimeError('Tablet adapter currently supports Linux x86_64 evdev only')
    types = _bits(_ioctl_read(fd, 0x20, 4))
    if not {EV_KEY, EV_ABS} <= types:
        raise ValueError('Selected device has no absolute pen event interface')
    abs_bits = _bits(_ioctl_read(fd, 0x20+EV_ABS, 8))
    axes = {}
    for code in (ABS_X, ABS_Y, ABS_PRESSURE, ABS_TILT_X, ABS_TILT_Y):
        if code in abs_bits:
            _, low, high, fuzz, flat, resolution = ABS_INFO.unpack(_ioctl_read(fd, 0x40+code, ABS_INFO.size))
            axes[code] = Axis(low, high, fuzz, flat, resolution)
    keys = frozenset(_bits(_ioctl_read(fd, 0x20+EV_KEY, 96)))
    name = _ioctl_read(fd, 0x06, 256).split(b'\0', 1)[0].decode('utf-8', errors='replace')
    return Capabilities(name, axes, keys, frozenset(abs_bits))


def current_state(fd: int, capabilities: Capabilities) -> tuple[dict[int, int], set[int]]:
    axes = {code: ABS_INFO.unpack(_ioctl_read(fd, 0x40+code, ABS_INFO.size))[0]
            for code in capabilities.axes}
    return axes, _bits(_ioctl_read(fd, 0x18, 96)) & capabilities.keys


@dataclass(frozen=True)
class Packet:
    x: int
    y: int
    pressure: int
    flags: int
    tool: int
    buttons: int
    raw_events: tuple[tuple[int, int, int, int, int], ...] = ()
    reason: str = 'sample'

    def words(self, ticks: int) -> list[int]:
        if isinstance(ticks, bool) or not isinstance(ticks, int) or not 0 <= ticks < 1 << 64:
            raise ValueError('A tablet packet requires authoritative virtual ticks')
        return [ticks, self.x, self.y, self.pressure, self.flags, self.tool, self.buttons]


class Decoder:
    def __init__(self, capabilities: Capabilities, axes: dict[int, int], keys: set[int]):
        self.capabilities = capabilities
        self.axes, self.keys = dict(axes), set(keys)
        self.pending = []
        self.dropping = False
        self.last_packet = self.packet()  # Validate reported initial state before transport.

    def packet(self, reason='sample', raw=()) -> Packet:
        c = self.capabilities
        x = c.axes[ABS_X].normalize(self.axes[ABS_X], 65535)
        y = c.axes[ABS_Y].normalize(self.axes[ABS_Y], 65535)
        pressure = c.axes[ABS_PRESSURE].normalize(self.axes[ABS_PRESSURE], 4095) if ABS_PRESSURE in c.axes else 0
        tool = 2 if BTN_TOOL_RUBBER in self.keys else 1 if BTN_TOOL_PEN in self.keys else 0
        flags = (1 if BTN_TOUCH in self.keys else 0) | (2 if tool else 0)
        buttons = sum(1 << bit for bit, key in enumerate((BTN_STYLUS, BTN_STYLUS2, BTN_STYLUS3)) if key in self.keys)
        return Packet(x, y, pressure, flags, tool, buttons, tuple(raw), reason)

    def loss(self, reason, raw=()) -> Packet:
        # A malformed unfinished frame must still signal loss with the last
        # validated coordinates; invalid axes cannot suppress cancellation.
        try:
            p = self.packet()
        except ValueError:
            p = self.last_packet
        return Packet(p.x, p.y, 0, 8, 0, 0, tuple(raw), reason)

    def resynchronize(self, axes, keys):
        self.axes, self.keys = dict(axes), set(keys)
        self.pending.clear()
        self.dropping = False
        self.last_packet = self.packet()

    def feed(self, event) -> Packet | None:
        seconds, micros, kind, code, value = event
        if not 0 <= micros < 1000000:
            raise ValueError('Malformed evdev timestamp')
        if kind == EV_SYN and code == SYN_DROPPED:
            self.pending.clear()
            self.dropping = True
            return self.loss('SYN_DROPPED', [event])
        if self.dropping:
            return None
        self.pending.append(tuple(event))
        if len(self.pending) > MAX_FRAME_EVENTS:
            raise ValueError('Tablet frame exceeds bounded event count')
        if kind == EV_ABS and code in self.capabilities.axes:
            self.axes[code] = value
        elif kind == EV_KEY and code in self.capabilities.keys:
            if value not in (0, 1, 2):
                raise ValueError('Malformed tablet key value')
            if value:
                self.keys.add(code)
            else:
                self.keys.discard(code)
        elif kind == EV_SYN and code == SYN_REPORT:
            packet = self.packet(raw=self.pending)
            self.last_packet = packet
            self.pending.clear()
            return packet
        return None


class TabletBridge:
    """Serial bounded raw transport. The sink assigns virtual time and records injection."""
    def __init__(self, device: Path | str, emit_packet: Callable[[Packet], None], record_path: Path | None = None):
        self.device, self.emit_packet, self.record_path = Path(device), emit_packet, record_path
        self.capabilities = None
        self.error = None
        self._stop = threading.Event()
        self._thread = None
        self._fd = -1
        self._capture = None
        self._frames = 0

    def _publish(self, packet):
        if self._capture:
            row = json.dumps({'kind': 'raw-tablet-frame', **vars(packet)}, separators=(',', ':'))+'\n'
            if self._frames >= MAX_CAPTURE_FRAMES or self._capture.tell()+len(row.encode()) > MAX_CAPTURE_BYTES:
                raise ValueError('Raw tablet capture exhausted')
            self._capture.write(row)
            self._frames += 1
        self.emit_packet(packet)

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Tablet bridge already started')
        self._fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            self.capabilities = probe(self._fd)
            axes, keys = current_state(self._fd, self.capabilities)
            self._decoder = Decoder(self.capabilities, axes, keys)
            if self.record_path:
                self._capture = Path(self.record_path).open('x', encoding='utf-8')
                self._capture.write(json.dumps({'kind': 'capabilities', 'device': str(self.device),
                                                **self.capabilities.report()})+'\n')
            self._thread = threading.Thread(target=self._read, name='LemmaSim raw tablet', daemon=True)
            self._thread.start()
            return self.capabilities.report()
        except Exception:
            os.close(self._fd)
            self._fd = -1
            if self._capture:
                self._capture.close()
            self._thread = None
            raise

    def _read(self):
        pending = bytearray()
        reason = 'adapter-cancel'
        try:
            while not self._stop.is_set():
                if not select.select([self._fd], [], [], 0.1)[0]:
                    continue
                try:
                    data = os.read(self._fd, INPUT_EVENT.size*64)
                except BlockingIOError:
                    continue
                if not data:
                    reason = 'truncated-event-disconnect' if pending else 'device-disconnect'
                    break
                pending.extend(data)
                while len(pending) >= INPUT_EVENT.size:
                    event = INPUT_EVENT.unpack(pending[:INPUT_EVENT.size])
                    del pending[:INPUT_EVENT.size]
                    if not 0 <= event[1] < 1000000:
                        raise ValueError('Malformed evdev timestamp')
                    if self._decoder.dropping and event[2:4] == (EV_SYN, SYN_REPORT):
                        axes, keys = current_state(self._fd, self.capabilities)
                        self._decoder.resynchronize(axes, keys)
                        packet = self._decoder.packet('reported-state-after-drop', [event])
                    else:
                        packet = self._decoder.feed(event)
                    if packet is not None:
                        self._publish(packet)
        except Exception as error:
            self.error = str(error)
            reason = 'device-or-transport-error'
        finally:
            try:
                self._publish(self._decoder.loss(reason))
            except Exception as error:
                self.error = self.error or str(error)
            if self._capture:
                self._capture.flush()
                self._capture.close()
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(5)
            if self._thread.is_alive():
                raise TimeoutError('Tablet sink did not finish within teardown bound')

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()


def session_sink(directory, rpc):
    """Literal device admission; the machine records the final admitted event."""
    def emit(packet):
        # At most four host seconds for both RPCs; pacing never supplies ticks.
        state = rpc(directory, {'action': 'clock', 'source': 'tablet'}, timeout=2)['machine']
        rpc(directory, {'action': 'inject', 'kind': 'pen',
                        'words': packet.words(state['ticks']), 'source': 'tablet'}, timeout=2)
    return emit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Read device names only; do not read input streams')
    parser.add_argument('--device', type=Path)
    parser.add_argument('--session-dir', '--session', dest='session_dir', type=Path)
    parser.add_argument('--record', type=Path)
    args = parser.parse_args()
    if args.list:
        print(json.dumps([{'device': '/dev/input/'+p.parent.parent.name,
                           'name': p.read_text().strip()} for p in sorted(Path('/sys/class/input').glob('event*/device/name'))], indent=2))
        return
    if not args.device or not args.session_dir:
        parser.error('Specify --device and --session-dir, or --list')
    from lemmasim_session import request
    stop = threading.Event()
    for kind in (signal.SIGTERM, signal.SIGINT):
        signal.signal(kind, lambda *_: stop.set())
    bridge = TabletBridge(args.device, session_sink(args.session_dir, request), args.record)
    try:
        print(json.dumps(bridge.start(), indent=2), flush=True)
        while bridge.alive and not stop.wait(0.1):
            continue
    finally:
        bridge.close()
    if bridge.error:
        raise RuntimeError(bridge.error)


if __name__ == '__main__':
    main()
