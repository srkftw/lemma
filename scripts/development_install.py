"""Host-only bounded opaque recovery transport; every decision has a ROM receipt.

This module neither opens BootNV/user media nor interprets image metadata. The
version2 Lean ROM supplies fresh authenticated confirmed/trial receipts. A
timeout, failed barrier, malformed image or MAC error is never installation
success. Retrying is an explicit new command, with a new cumulative budget.
"""
import hashlib
import json
from pathlib import Path


def load_package(directory, tag_path, sha):
    directory = Path(directory)
    package = json.loads((directory / 'package.json').read_text())
    image = directory / 'image.bin'
    size = image.stat().st_size
    if (package.get('schema') != 'lemma-product-image/1'
            or package.get('status') != 'PASS'
            or not 512 <= size <= 16 * 1024 * 1024 or size % 512
            or type(package.get('identity')) is not int
            or not 0 < package['identity'] < 1 << 64
            or sha(image) != package.get('image_sha256')):
        raise ValueError('Unchanged bounded opaque compiled image package required')
    wire = image.read_bytes()
    if len(wire) != size or hashlib.sha256(wire).hexdigest() != package['image_sha256']:
        raise ValueError('Image changed during opaque transport admission')
    tag_path = Path(tag_path)
    if tag_path.stat().st_size != 512:
        raise ValueError('Exact slot-specific512-byte development tag required')
    tag = tag_path.read_bytes()
    if len(tag) != 512:
        raise ValueError('Development tag changed during transport admission')
    return package, wire, tag


def resume(client, package, wire, tag, slot):
    """Use one client's original whole-operation host/cycle/transaction bounds.

    215 is the ROM's no-valid-metadata recovery result;217 is a nonmatching
    image receipt. Only these permit staging, still subject to the ROM's own
    inactive-slot rule. All other failures stop before any new payload request.
    A matching status includes the guest's real barrier and complete image/MAC
    validation. No missing response is inferred from on-disk bytes.
    """
    if type(slot) is not int or slot not in (0, 1):
        raise ValueError('Slot0 or1 required')
    if not wire or len(wire) % 512 or len(wire) > 16 * 1024 * 1024 or len(tag) != 512:
        raise ValueError('Bounded complete opaque sectors required')
    rows = []

    def send(operation, **kw):
        row = client.send(operation, slot=slot, identity=package['identity'], **kw)
        rows.append({'operation': operation, **row})
        return row

    def matching(row):
        return row['status'] == 0 and type(row['value']) is int and row['value'] in (1, 2)

    before = send(4)
    if matching(before):
        return {'state': 'reconciled-confirmed' if before['value'] == 1 else 'reconciled-trial',
                'receipts': rows, 'sectors_sent': 0,
                'durability': 'fresh authenticated Lean ROM status/barrier receipt'}
    if before['status'] not in (215, 217) or before['value'] != 0:
        raise RuntimeError('ROM status forbids resumed staging: ' + json.dumps(before))
    for index in range(len(wire) // 512):
        row = send(1, relative=index, payload=wire[index * 512:(index + 1) * 512])
        if row['status']:
            raise RuntimeError('ROM rejected resumed payload sector: ' + json.dumps(row))
    for operation, payload in ((5, {'payload': tag}), (2, {})):
        row = send(operation, **payload)
        if row['status']:
            raise RuntimeError('ROM rejected resumed tag/publication: ' + json.dumps(row))
    after = send(4)
    if not matching(after):
        raise RuntimeError('No fresh authenticated installation receipt: ' + json.dumps(after))
    return {'state': 'installed-confirmed' if after['value'] == 1 else 'installed-trial',
            'receipts': rows, 'sectors_sent': len(wire) // 512,
            'durability': 'fresh authenticated Lean ROM status/barrier receipt'}
