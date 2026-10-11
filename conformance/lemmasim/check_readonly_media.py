#!/usr/bin/env python3
"""Observe a real failed guest mount without interpreting or repairing its disk."""
from __future__ import annotations
import hashlib
from pathlib import Path
from check_notebook_workflow import device_events, guest_events, visible_pixels

# Independently authored literal rows, not imported guest glyph/transition code.
ROWS = {
    'R': ('110', '101', '110', '101', '101'),
    'E': ('111', '100', '110', '100', '111'),
    'A': ('010', '101', '111', '101', '101'),
    'D': ('110', '101', '101', '101', '110'),
    ' ': ('000',) * 5,
    'O': ('111', '101', '101', '101', '111'),
    'N': ('101', '111', '111', '111', '101'),
    'L': ('100', '100', '100', '100', '111'),
    'Y': ('101', '101', '010', '010', '010'),
}


def check(disk: Path, initial_sha256: str, serial: Path, devices: Path,
          medium: Path, visible: Path) -> dict:
    digest = hashlib.sha256(disk.read_bytes()).hexdigest()
    if digest != initial_sha256:
        raise ValueError('failed mount changed the original damaged/unknown media bytes')
    events = guest_events(serial)
    failures = [row for row in events if row[0] == 0x424]
    ready = [row for row in events if row[0] == 0x420]
    if (len(failures) != 1 or not failures[0][1] or failures[0][4] or len(ready) != 1 or
            any(row[0] in (0x41f, 0x421, 0x423) for row in events)):
        raise ValueError('failed mount lacked the genuine read-only guest state or published/formatted data')
    transitions = device_events(devices)
    completed = [row for row in transitions if row[1] == 'paper-complete']
    if len(completed) != 1 or completed[0][2] != ready[0][4]:
        raise ValueError('read-only guest page did not complete its real controller refresh')
    rows = [line.split() for line in medium.read_text().splitlines()]
    if (not rows or any(len(row) != 5 or not row[0].isdigit() for row in rows) or
            any(row[1] in ('write-volatile', 'write-failed', 'pending-full', 'sector-torn-durable') for row in rows)):
        raise ValueError('failed mount submitted block writes or lacks actual medium observations')
    width, height, pixels = visible_pixels(visible)
    if (width, height) not in ((1650, 2200), (1404, 1872)):
        raise ValueError('read-only output geometry differs')
    for index, character in enumerate('READ ONLY'):
        for y in range(15):
            for x in range(12):
                black = x < 9 and ROWS[character][y // 3][x // 3] == '1'
                offset = ((132 + y) * width + 24 + index * 12 + x) * 3
                if pixels[offset:offset + 3] != bytes([0 if black else 255]) * 3:
                    raise ValueError('controller pixels do not contain the guest READ ONLY label')
    paths = (disk, serial, devices, medium, visible)
    return {'schema_version': 1, 'status': 'PASS',
            'scope': 'real failed guest mount, no formatting/writes, unchanged disk and guest-rendered READ ONLY pixels',
            'guest_mount_failure': list(failures[0]), 'initial_media_sha256': initial_sha256,
            'visible_pixels_sha256': hashlib.sha256(pixels).hexdigest(),
            'artifact_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
