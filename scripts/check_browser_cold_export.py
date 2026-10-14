#!/usr/bin/env python3
"""Passively qualify exported canonical cold Ready; tape admission stays separate.

This observer never supplies state to a machine. It checks the actual snapshot,
all controller pixels and unchanged durable bytes. A malformed outcome tape
remains a failure even when the independently observed cold boot succeeded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'conformance/lemmasim'))
from check_companion_pending import timed_records
from check_companion_session import crc64 as bitwise_crc
from check_live_notebook import visible_pixels
from store_oracle import recover
from math_oracle import inspect as inspect_math


def require(value, message):
    if not value:
        raise ValueError(message)


def crc64(raw):
    # Independently checked against the existing bitwise oracle, including
    # the published CRC-64/ECMA-182 check value. Avoid minutes of bitwise work
    # over unchanged observational 128MiB RAM images.
    mask = (1 << 64) - 1
    table = []
    for byte in range(256):
        x = byte << 56
        for _ in range(8):
            x = ((x << 1) ^ (0x42f0e1eba9ea3693 if x >> 63 else 0)) & mask
        table.append(x)
    value = 0
    for byte in raw:
        value = ((value << 8) ^ table[(value >> 56) ^ byte]) & mask
    return value


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def exported(path, identity):
    raw = Path(path).read_bytes()
    require(len(raw) <= 805306368 and raw[:8] == b'LMSSRTL1' and
            struct.unpack_from('<Q', raw, 8)[0] == 2 and
            raw[16:80].decode() == identity, 'canonical snapshot version/identity')
    wn, mn, wc, mc = struct.unpack_from('<4Q', raw, 80)
    require(112 + wn + mn == len(raw) and 0 < mn <= 67108864,
            'complete wrapper/generated-model bounds')
    require(crc64(memoryview(raw)[112:112+wn]) == wc and
            crc64(memoryview(raw)[112+wn:]) == mc, 'complete snapshot CRC')
    fields = struct.unpack_from('<43Q', raw, 112)
    at = 112 + (43+3+4+5)*8
    def vector(expected=None):
        nonlocal at
        n = struct.unpack_from('<Q', raw, at)[0]
        at += 8
        require(n <= wn and at+n <= 112+wn and
                (expected is None or n == expected), 'wrapper vector bound')
        result = memoryview(raw)[at:at+n]
        at += n
        return result
    uart = bytes(vector())
    vector()  # Observational stop marker.
    vector(134217728)
    vector(4096)
    vector(7260000)
    visible = vector(3630000)
    return fields, uart, bytes(visible)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'bundle', 'reference-medium', 'reference-pixels'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--result-name', default='cold-result-a3.json')
    args = p.parse_args()
    out = args.directory
    require(Path(args.result_name).name == args.result_name,
            'result must be a nonescaping filename')
    destination = out / args.result_name
    require(not destination.exists(), 'preserve previous observations')
    start = time.monotonic()
    result = {'schema':'lemma-browser-cold-export/1', 'status':'FAIL',
              'scope':__doc__, 'observer_sha256':sha(__file__)}
    try:
        for raw in (b'', b'123456789', bytes(range(256)), bytes(range(256))*17):
            require(crc64(raw) == bitwise_crc(raw), 'CRC observer independent relation')
        require(crc64(b'123456789') == 0x6c40df5f0b497347, 'CRC published check value')
        plan = json.loads((out/'plan.json').read_text())
        observation = json.loads((out/'browser-observation-a1.json').read_text())
        manifest = json.loads((args.bundle/'bundle.json').read_text())
        require(sha(args.bundle/'bundle.json') == plan['bundle_sha256'] and
                manifest['profile'] == 'lemma-silicon-dev/0.3.0', 'original browser bundle')
        require(observation['initial_cycle'] == '0' and not observation['restored'] and
                observation['medium_name'] == plan['private_medium'], 'actual cold origin')
        require(observation['ready_cycle'] <= int(plan['max_cycles']) and
                observation['ready_host_seconds'] <= plan['max_host_seconds'] and
                observation['heap_bytes'] <= plan['max_wasm_heap_bytes'], 'original cold bounds')
        fields, uart, gray = exported(out/'ready.chk', plan['implementation'])
        require(fields[1] == observation['ready_cycle'] and fields[10] == 0 and
                fields[14] == 1 and fields[27] == fields[35] == fields[38] == 0,
                'actual snapshot Ready boundary/in-flight storage')
        rows = [tuple(int(x,16) for x in match) for match in re.findall(
            rb'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})', uart)]
        require(any(r[0] == 0x420 for r in rows) and
                any(r[0] == 0x425 and r[1] == fields[14] for r in rows) and
                not any(r[0] in (0x41f,0x423,0x424,0xd4,0xf4) for r in rows),
                'actual guest Ready/publication; no format, save, failure or fault')
        width, height, pixels = visible_pixels(args.reference_pixels)
        require((width,height) == (1650,2200) and len(pixels) == 10890000,
                'complete independently derived canonical reference')
        rgb = bytearray(10890000)
        for i, value in enumerate(gray):
            require(value <= 15, 'controller Gray4 value')
            rgb[3*i:3*i+3] = bytes([value*17])*3
        require(rgb == pixels, 'all3.63M controller pixels')
        require(sha(out/'ready.raw') == sha(args.reference_medium) == plan['input_sha256'],
                'cold changed acknowledged or unacknowledged medium bytes')
        _, sequence, records = recover((out/'ready.raw').read_bytes())
        document = inspect_math(records[1,0x8001].payload,1,0x8001)
        result.update(status='PASS_COLD_READY_MEDIA_AND_ALL_PIXELS',
            snapshot_sha256=sha(out/'ready.chk'), medium_sha256=plan['input_sha256'],
            complete_pixels=3630000, reference_pixels_sha256=sha(args.reference_pixels),
            ready_cycle=fields[1], ready_host_seconds=observation['ready_host_seconds'],
            simulation_call_seconds=observation['simulation_call_seconds'],
            heap_bytes=observation['heap_bytes'], actual_guest_rows=rows,
            sequence=sequence, document=document, medium_unchanged=True,
            snapshot_after_actual_cold_only=True, replay_qualified=False)
        # Keep tape validity load-bearing. This does not reinterpret corrupt
        # lengths, truncate entries or claim a successful replay from them.
        try:
            outcomes, pending = timed_records(out/'ready.io')
            require(pending is None and len(outcomes) == 250 and
                    all(row[0][2] == 0 and row[0][4:7] == (512,512,0) for row in outcomes),
                    'actual cold tape must contain250 complete successful READs')
            result['outcome_tape'] = {'status':'PASS', 'complete_reads':len(outcomes)}
        except ValueError as error:
            result['outcome_tape'] = {'status':'FAIL', 'error':str(error),
                'sha256':sha(out/'ready.io'), 'bytes':(out/'ready.io').stat().st_size}
    except (OSError,ValueError,KeyError,IndexError,struct.error) as error:
        result.update(status='FAIL', error=str(error))
    result['observer_host_seconds'] = time.monotonic()-start
    destination.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result.get(key) for key in
        ('status','error','ready_cycle','ready_host_seconds','outcome_tape','observer_host_seconds')}))
    return 0 if result['status']=='PASS_COLD_READY_MEDIA_AND_ALL_PIXELS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
