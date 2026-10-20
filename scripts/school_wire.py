"""Bounded guest console framing only; no school/document policy."""
import re
import struct

MAX_OBSERVATION = 16 * 1048576
MAX_PAYLOAD = 96
_START = re.compile(rb'(?:^|\n)K1 000000000000072e (?:[0-9a-f]{16} ){3}[0-9a-f]{16}\r?(?=\n)')
_WIRE = re.compile(rb'(?:^|\n)K1 0000000000000740 ((?:[0-9a-f]{16} ){3}[0-9a-f]{16})\r?(?=\n)')
_K1 = re.compile(rb'K1 ((?:[0-9a-f]{16} ){4}[0-9a-f]{16})\r?')
_S1 = re.compile(rb'S1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]+)\r?')

def frames(data):
    """Yield ordered diagnostic records or exact outgoing byte chunks.

    An incomplete final line remains incomplete; consumers cannot mistake it
    for a completed stream. Unknown historical diagnostic lines are ignored.
    A complete malformed S1 frame fails closed rather than losing its bytes.
    """
    if not isinstance(data, bytes) or len(data) > MAX_OBSERVATION:
        raise ValueError('guest console observation exceeds16MiB')
    wire = False
    for match in _WIRE.finditer(data):
        if tuple(int(x, 16) for x in match[1].split()) != (1, 96, 230, 256):
            raise ValueError('unsupported guest school wire capability')
        wire = True
    # Only a complete fresh start resets an abandoned partial stream. A bad
    # frame in the latest attempt remains an error; bytes are never repaired.
    starts = list(_START.finditer(data))
    if starts:
        data = data[starts[-1].start():]
    for line in data.split(b'\n')[:-1]:
        old = _K1.fullmatch(line)
        if old:
            values = tuple(int(x, 16) for x in old[1].split())
            if values[0] == 0x72f:
                _, queue, packed, a, b = values
                count = packed >> 48
                if not 1 <= count <= 16:
                    raise ValueError('invalid legacy chunk length')
                yield ('chunk', queue, packed & ((1 << 48)-1), struct.pack('<2Q', a, b)[:count])
            else:
                yield ('record', *values)
        elif line.startswith(b'S1'):
            if not wire:
                raise ValueError('S1 chunk has no admitted guest wire capability')
            match = _S1.fullmatch(line)
            if match is None or len(line.rstrip(b'\r')) > 229:
                raise ValueError('malformed S1 guest chunk')
            queue, packed = (int(x, 16) for x in match.groups()[:2])
            count, offset = packed >> 48, packed & ((1 << 48)-1)
            if (queue >> 48 != 0x5351 or queue & ((1 << 48)-1) == 0 or
                    not 1 <= count <= MAX_PAYLOAD or offset >= 262144 or
                    count > 262144-offset or len(match[3]) != count*2):
                raise ValueError('invalid bounded S1 guest chunk')
            yield ('chunk', queue, offset, bytes.fromhex(match[3].decode('ascii')))
