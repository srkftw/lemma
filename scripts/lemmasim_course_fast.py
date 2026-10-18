"""Raw local-owner transport for the negotiated fast UART, below Lean policy.

Only bounded command framing and bytes cross this adapter. The existing guest
installer checks packages and alone publishes Store data and durable receipts.
"""
import hashlib
import json
from pathlib import Path
import struct

from lemmasim_course import CANONICAL_CONFIGURATIONS, frame
from lemmasim_session import bounded, request


def send(args):
    directory = args.session_dir.resolve()
    metadata = json.loads((directory/'session.json').read_text())
    if (metadata.get('schema') != 'lemmasim-live/1' or
            metadata.get('mode') not in ('developer', 'laboratory') or
            metadata.get('backend') != 'qemu'):
        raise ValueError('Fast course command requires a Developer/Laboratory fast session')
    identity = metadata.get('identity', {})
    if (identity.get('profile') not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.14.0') or
            identity.get('adapter') != 'lemmasim-fast-adapter/5'):
        raise ValueError('Fast course command requires negotiated canonical/multimodal raw UART1')
    argv = metadata.get('argv', [])
    if not isinstance(argv, list) or argv.count('-kernel') != 1:
        raise ValueError('Fast course session lacks an exact development guest image')
    index = argv.index('-kernel')+1
    if index >= len(argv) or not isinstance(argv[index], str):
        raise ValueError('Malformed fast guest image argument')
    image = Path(argv[index])
    build = json.loads((image.parent/'build.json').read_text())
    configuration=build.get('configuration')
    expected_profile=('lemma-silicon-dev/0.14.0' if configuration in ('lemmasim-silicon-multimodal-notebook','lemmasim-silicon-multimodal-parameterized-notebook') else
                      'lemma-silicon-dev/0.3.0' if configuration in CANONICAL_CONFIGURATIONS else None)
    if (expected_profile is None or identity.get('profile')!=expected_profile or
            hashlib.sha256(image.read_bytes()).hexdigest() != identity.get('guest')):
        raise ValueError('Fast course command requires the exact admitted course guest')
    # Observe the actual private control owner as well as its launch metadata.
    # This enables a byte port, never a host assertion of guest configuration.
    observed = request(directory, {'action': 'inspect'}, timeout=120)
    if observed.get('identity') != identity or observed.get('running') is not False:
        raise ValueError('Pause the exact fast session before a course command')
    uart = observed.get('machine', {}).get('devices', {}).get('uart_ingress', {})
    if uart.get('enabled') is not True:
        raise ValueError('Actual fast raw UART is disabled')
    operation = {'course-install': 1, 'course-load': 2, 'course-delete-probe': 3}[args.command]
    payload = b''
    if operation == 1:
        path = args.package.resolve()
        if not 128 <= path.stat().st_size <= 32768:
            raise ValueError('Package bytes must be within128..32768')
        payload = path.read_bytes()
        if not 128 <= len(payload) <= 32768:
            raise ValueError('Package changed outside its raw transport bound')
        # Untrusted header declarations: the guest validates all bytes/CRC,
        # immutable edition authority and publication. No host installation.
        package_identity, edition = struct.unpack_from('<2Q', payload, 24)
        crc = struct.unpack_from('<Q', payload, 80)[0]
        transaction = args.transaction
    else:
        package_identity, edition, crc = args.identity, args.edition, args.crc
        transaction = args.node if operation == 2 else args.transaction
    packet = frame(operation, package_identity, edition, len(payload), transaction, crc)+payload
    current = observed['machine']['cycle']
    cycle = bounded(args.cycle if args.cycle is not None else current,
                    current, (1 << 64)-1, 'Event cycle')
    if cycle*10 > (1 << 63)-11:
        raise ValueError('Fast course delivery exceeds the canonical nanosecond clock bound')
    # Validate complete queue capacity before admitting a multi-chunk command.
    # Other local owners may still race; their actual admission errors retain
    # the session's fail-closed capture/quarantine behavior.
    if type(uart.get('pending')) is not int or not 0 <= uart['pending'] <= 65536:
        raise ValueError('Malformed actual UART queue state')
    if len(packet) > 65536-uart['pending']:
        raise ValueError('Raw UART command exceeds currently available queue capacity')
    chunks = []
    for offset in range(0, len(packet), 4096):
        result = request(directory, dict(action='inject', kind='uart', cycle=cycle,
                         hex=packet[offset:offset+4096].hex()), timeout=120)
        chunks.append(dict(offset=offset, bytes=min(4096, len(packet)-offset), boundary=result))
    return dict(status='RAW_COMMAND_ADMITTED', operation=operation,
                identity=package_identity, edition=edition, bytes=len(payload),
                expected_crc32=crc, transaction_or_node=transaction, chunks=chunks,
                receipt='Admission only. Read the actual guest K1/4b1 outcome; the adapter issues no durable receipt.')
