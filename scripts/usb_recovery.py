#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Identity binding for an explicitly selected raw USB process reconnect.

This host boundary neither interprets guest records nor reconciles receipts.
The digest names the immutable process/source closure and persistent namespace;
it is not authentication and intentionally excludes changing medium/outbox bytes.
"""
import hashlib
import json
from pathlib import Path

CONTRACT = 'lemma-usb-live-recovery/1'


def binding(prepared, directory, socket, outbox, helper):
    from lemmasim_usb_pending import validate
    from lemmasim_companion import peer_info
    prepared, directory, socket, outbox, helper = (
        Path(path).resolve() for path in (prepared, directory, socket, outbox, helper))
    host = validate(prepared)
    if (host.get('schema'), host.get('policy_version')) != (
            'lemma-usb-host-dev/4', 'lemma-usb-pending-policy/4'):
        raise ValueError('USB recovery requires the exact validated Pending policy4')
    peer = peer_info(directory)
    if (directory / 'base.img').stat().st_size != 268435456:
        raise ValueError('USB recovery peer capacity differs')
    identity = {
        'contract': CONTRACT,
        'policy_manifest_sha256': hashlib.sha256(prepared.read_bytes()).hexdigest(),
        'policy_binary_sha256': host['binary']['sha256'],
        'peer_directory': str(directory), 'socket': str(socket),
        'outbox': str(outbox), 'writer': peer['writer'], 'capacity_bytes': 268435456,
        'raw_io_helper': str(helper),
        'raw_io_helper_sha256': hashlib.sha256(helper.read_bytes()).hexdigest(),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()
    return digest, identity
