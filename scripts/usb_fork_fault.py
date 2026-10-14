#!/usr/bin/env python3
"""Versioned, injected USB disconnect fork input, never historical replay.

Only the idle reversible WAIT of a fully acknowledged Wire11 checkpoint is
admitted. The unchanged native raw bridge receives one genuinely captured EOF;
the adapter binds its distinct fault provenance before any virtual advancement.
"""
import json
from pathlib import Path
import re

from archive_companion_boundary import validate_archive_files, outbox_fields
from check_guest_usb_link import require, sha
from silicon_guest_bundle import prepared

SCHEMA = 'lemma-usb-fork-disconnect-fault/1'
PROFILE = 'lemma-silicon-dev/0.11.0'
MAX_SUFFIX = 1800000000
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211
MASK = (1 << 64) - 1


def chain(data, value=FNV_OFFSET):
    for byte in data:
        value = ((value ^ byte) * FNV_PRIME) & MASK
    return value


def file_record(path):
    path = Path(path).absolute()
    require(not any(c in str(path) for c in ('\n', '\r')) and
            path.resolve() == path and not path.is_symlink() and path.is_file(),
            'fault authority requires a regular non-symbolic path')
    return {'path': str(path), 'sha256': sha(path)}


def checked_file(item, limit=None):
    require(isinstance(item, dict) and set(item) == {'path', 'sha256'}, 'fault file authority shape')
    path = Path(item['path'])
    require(path.is_absolute() and file_record(path) == item and
            (limit is None or path.stat().st_size <= limit), 'fault file authority changed')
    return path


def prefix(path, implementation, cycle):
    raw = Path(path).read_bytes()
    require(74 <= len(raw) <= 64 << 20 and raw.endswith(b'\n'), 'fault prefix byte bound')
    lines = raw.splitlines(keepends=True)
    require(lines[0] == f'LMUSBRP1 {implementation}\n'.encode() and
            lines[1] == f'HORIZON {cycle}\n'.encode() and
            lines[-1].startswith(b'CHECKSUM '), 'fault prefix identity or horizon')
    rows = lines[2:-1]
    value, next_id, active, active_frame, previous = FNV_OFFSET, 1, 0, '', 0
    for wire in rows:
        text = wire.decode('ascii'); parts = text[:-1].split(' ', 3)
        require(len(parts) == 4 and all(re.fullmatch(r'0|[1-9][0-9]*', part) for part in parts[:3]),
                'fault prefix canonical row fields')
        tick, tag, key = map(int, parts[:3]); frame = parts[3]
        require(previous <= tick < cycle and len(frame) <= 160 and frame and
                wire == f'{tick} {tag} {key} {frame}\n'.encode(), 'fault prefix row order')
        if tag == 0:
            require(not active and key == next_id and tick % 1000 == 0,
                    'fault prefix request namespace')
            active, active_frame, next_id = key, frame, next_id + 1
        else:
            require(tag == 1 and active == key, 'fault prefix is terminal or has unmatched reply')
            active, active_frame = 0, ''
        previous = tick; value = chain(wire, value)
    require(lines[-1] == f'CHECKSUM {chain(f"{cycle} 3 0 HORIZON\n".encode(), value)}\n'.encode(),
            'fault prefix checksum')
    require(active and active_frame == 'WAIT 100000', 'fault may cancel only retained idle WAIT100000')
    return rows, {'accepted_rows': len(rows), 'accepted_hash': value,
                  'pending_command': active, 'command': active_frame, 'next_id': next_id}


def private_files(directory):
    directory = Path(directory).resolve()
    return {name: file_record(directory / name) for name in
            ('peer/base.img', 'peer/opaque.log', 'peer/peer.json', 'outbox/outbox')}


def validate(path, parent, state, identity):
    path = Path(path).absolute()
    require(path.resolve() == path and not path.is_symlink() and path.stat().st_size <= 32768,
            'fault sidecar path or bound')
    data = json.loads(path.read_text())
    require(set(data) == {'schema', 'scope', 'native_bundle', 'parent_snapshot', 'parent_tape',
            'acknowledged_boundary', 'private_directory', 'private_files', 'capture', 'fault', 'bridge'} and
            data['schema'] == SCHEMA and data['scope'] == 'injected disconnect fault fork',
            'not a versioned injected disconnect fault sidecar')
    require(identity['backend'] == 'rtl' and identity['profile'] == PROFILE,
            'fork fault only admits exact Wire11 RTL')
    parent = Path(parent).resolve()
    require(data['parent_snapshot'] == {'path': str(parent),
            'manifest': file_record(parent / 'snapshot.json'), 'machine': file_record(parent / 'machine.chk')},
            'fault parent checkpoint authority differs')
    metadata = json.loads((parent / 'snapshot.json').read_text())
    require(metadata['schema'] == 'lemmasim-session/1' and metadata['identity'] == identity and
            metadata['virtual_cycle'] == state['cycle'] and
            metadata['files'] == [{'path': 'machine.chk', 'bytes': (parent / 'machine.chk').stat().st_size,
                                  'sha256': sha(parent / 'machine.chk')}], 'fault parent inventory or identity')
    bundle_path = checked_file(data['native_bundle'], 4 << 20)
    require(bundle_path.name == 'bundle.json', 'fault native bundle metadata name')
    native = prepared(bundle_path.parent, 'rtl', 'usb-wire-bulk-notebook', PROFILE)
    require(native['binary']['sha256'] == identity['runtime'], 'fault selected native binary differs')
    build = json.loads(Path(native['rtl_build']['path']).read_text())
    implementation = build['snapshot_identity']
    require(state['snapshot_identity'] == implementation, 'fault implementation differs')
    usb = state['usb']
    require(state['isolated_medium'] is True and usb['fork_suspended'] is True and
            usb['attached'] == usb['connected'] == usb['configured'] == 1 and usb['terminal'] == 0 and
            usb['command'] == 'WAIT 100000' and usb['rx_head_mask'] == usb['tx_queued_mask'] ==
            usb['queued_packets'] == usb['incoming_bytes'] == usb['outgoing_bytes'] == 0 and
            usb['next_poll'] == state['cycle'] and state['cycle'] < usb['wait_until'] and
            state['cycle'] % 1000 == 0 and state['paper_busy'] == state['panel_pending_pixels'] ==
            state['memory_pending'] == state['dma_outstanding'] == 0,
            'fault is not at an isolated empty-packet idle WAIT boundary')
    parent_tape = checked_file(data['parent_tape'], 64 << 20)
    rows, logical = prefix(parent_tape, implementation, state['cycle'])
    require(all(usb[key] == logical[key] for key in ('accepted_rows', 'accepted_hash',
            'pending_command', 'command')), 'fault parent accepted prefix differs')
    boundary_path = checked_file(data['acknowledged_boundary'], 32768)
    boundary = json.loads(boundary_path.read_text()); validate_archive_files(boundary_path.parent, boundary)
    require(boundary['profile'] == PROFILE and boundary['status'] == 'PASS' and
            (boundary['saved_sequence'], boundary['high_water']) == (11, 72),
            'fault has no acknowledged Saved11 receipt state')
    reference = (boundary_path.parent / 'reference.raw').read_bytes().splitlines(keepends=True)
    require(reference[0] == f'LMUSBRW2 {implementation}\n'.encode() and reference[1:] == rows,
            'fault parent raw prefix differs from complete acknowledged transaction observation')
    private = Path(data['private_directory']).resolve()
    actual_private = private_files(private)
    require(data['private_files'] == actual_private, 'fault private opaque state changed')
    for name, item in actual_private.items():
        if name != 'peer/peer.json':
            require(item['sha256'] == boundary['files'][name]['sha256'], 'fault private receipt bytes differ')
    original_peer = json.loads((boundary_path.parent / 'peer/peer.json').read_text())
    expected_peer = {**original_peer, 'base': str(private / 'peer/base.img')}
    require((private / 'peer/peer.json').read_bytes() ==
            (json.dumps(expected_peer, indent=2) + '\n').encode(),
            'fault private peer metadata differs beyond its exact owned base path')
    outbox_fields((private / 'outbox/outbox').read_bytes(), boundary['writer'], boundary['high_water'])
    captured_path = checked_file(data['capture'], 32768)
    captured = json.loads(captured_path.read_text())
    require(captured['schema'] == 'lemma-private-usb-eof/1' and captured['status'] == 'PASS' and
            captured['fault'] == 'USB process disconnected read' and
            captured['actual_request'] == {'id': 1, 'frame': 'USBHOST/2 PACKET_BYTES_DEV'} and
            captured['private_directory'] == str(private) and
            captured['before'] == captured['after'] == actual_private and
            captured['reply_count'] == captured['opaque_operations_issued'] == 0 and
            captured['owned_children_reaped'] is True,
            'fault lacks a genuine private EOF with no operation or receipt')
    for item in captured['inputs'].values(): checked_file(item)
    for item in captured['outputs'].values(): checked_file(item)
    require(captured['inputs']['native_bundle'] == data['native_bundle'],
            'private EOF used another native transport authority')
    from lemmasim_usb_pending import validate as validate_host
    validate_host(checked_file(captured['inputs']['host_prepared'], 32768))
    bundle = json.loads(bundle_path.read_text())
    for name in ('usb_transport.cpp', 'usb_transport.h'):
        original = bundle['original_repository_root'] + '/sim/usb/' + name
        origins = bundle['origins'].get(original, {})
        require(len(origins) == 1 and captured['inputs'][name] ==
                file_record(bundle_path.parent / next(iter(origins.values()))),
                'private EOF transport does not come from exact native archive')
    log = checked_file(captured['outputs']['log'], 4096).read_text().splitlines()
    require(len(log) == 3 and log[0] == 'REQUEST 1 USBHOST/2 PACKET_BYTES_DEV' and
            re.fullmatch(r'CHILD [1-9][0-9]*', log[1]) and
            log[2] == 'FAULT USB process disconnected read', 'private EOF observation differs')
    fault = data['fault']
    require(set(fault) == {'kind', 'cycle', 'request_id', 'frame', 'horizon'} and
            fault['kind'] == 'private-transport-eof' and fault['cycle'] == state['cycle'] and
            fault['request_id'] == usb['pending_command'] and fault['frame'] == captured['fault'] and
            type(fault['horizon']) is int and state['cycle'] < fault['horizon'] <= state['cycle'] + MAX_SUFFIX,
            'fault injection request, boundary or finite horizon differs')
    injected = f"{fault['cycle']} 2 {fault['request_id']} {fault['frame']}\n".encode()
    value = chain(injected, logical['accepted_hash'])
    horizon = fault['horizon']
    expected = (f'LMUSBRP1 {implementation}\nHORIZON {horizon}\n'.encode() + b''.join(rows) + injected +
                f'CHECKSUM {chain(f"{horizon} 3 0 HORIZON\n".encode(), value)}\n'.encode())
    bridge = checked_file(data['bridge'], 64 << 20)
    require(bridge.read_bytes() == expected, 'fault bridge changed inherited raw prefix or injected outcome')
    return data, bridge
