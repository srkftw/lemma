#!/usr/bin/env python3
"""Actual retained-capture HELLO/effect observer sensitivity; no CPU rerun."""
import argparse
import json
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from archive_companion_boundary import crc64, log_frames, outbox_fields
from check_guest_usb_link import decode_capture, require, sha
from observe_usb_workflow_wire import durable_effects_match, initial_receipt_sequence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workflow', 'initial-peer', 'initial-outbox', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned fixture output')
    out.mkdir(); began = time.monotonic()
    report = {'status': 'FAIL', 'scope': __doc__, 'host_seconds_bound': 60, 'rejected': []}
    def rejects(label, function, expected):
        require(time.monotonic() - began < 60, 'retained observer fixture bound')
        try: function()
        except ValueError as error:
            require(expected in str(error), 'negative rejected for an unrelated reason: ' + label)
            report['rejected'].append({'label': label, 'error': str(error)})
        else: raise ValueError('retained observer admitted: ' + label)
    try:
        raw = args.workflow / 'live/usb.raw'
        before = sha(raw)
        prior, initial_sequence = initial_receipt_sequence(args.initial_peer, args.initial_outbox, 83)
        require(initial_sequence == 7, 'different initial outbox reference')
        wire = decode_capture(raw, probe=False, writer=83, initial_sequence=initial_sequence)
        actual = log_frames((args.workflow / 'peer/opaque.log').read_bytes())
        durable_effects_match(wire, prior, actual)
        rejects('default sequence1 is not this admitted baseline',
                lambda: decode_capture(raw, probe=False, writer=83, initial_sequence=1), 'actual hello identity')
        rejects('different declared writer',
                lambda: decode_capture(raw, probe=False, writer=84, initial_sequence=7), 'actual hello identity')
        # Change one actual recorded data CRC; no source-policy or receipt byte
        # is fed back to a guest. The private tape is only an observer mutant.
        rows = raw.read_text().splitlines()
        for index, row in enumerate(rows):
            fields = row.split(' ', 3)
            if len(fields) == 4 and fields[3].startswith('SEND c34c4d435553423031'):
                changed = bytearray.fromhex(fields[3][5:]); changed[-1] ^= 1
                fields[3] = 'SEND ' + changed.hex(); rows[index] = ' '.join(fields); break
        else: raise ValueError('actual HELLO packet not found')
        wrong = out / 'bad-hello-crc.raw'; wrong.write_text('\n'.join(rows) + '\n')
        rejects('corrupt actual HELLO CRC',
                lambda: decode_capture(wrong, probe=False, writer=83, initial_sequence=7), 'data CRC16')
        rejects('extra persisted effect', lambda: durable_effects_match(wire, prior, actual + actual[-1:]),
                'accepted wire effects')
        rejects('missing persisted effect', lambda: durable_effects_match(wire, prior, actual[:-1]),
                'accepted wire effects')
        value = (args.initial_outbox / 'outbox').read_bytes()
        corrupt = value[:-1] + bytes([value[-1] ^ 1])
        rejects('corrupt initial outbox CRC', lambda: outbox_fields(corrupt, 83, 6), 'pending or corrupt')
        body = struct.pack('<4Q', 0x313054554f434d4c, 83, 1, 0)
        wrong_sequence = body + struct.pack('<Q', crc64(body))
        rejects('checksum-valid wrong initial outbox',
                lambda: outbox_fields(wrong_sequence, 83, 6), 'exact peer high-water')
        body = struct.pack('<4Q', 0x313054554f434d4c, 84, 7, 0)
        wrong_writer = body + struct.pack('<Q', crc64(body))
        rejects('checksum-valid wrong outbox writer',
                lambda: outbox_fields(wrong_writer, 83, 6), 'exact peer high-water')
        require(sha(raw) == before, 'retained original capture changed')
        report.update(status='PASS', original_capture={'path': str(raw.resolve()), 'sha256': before},
            actual_transactions=len(wire['transactions']), initial_sequence=initial_sequence,
            exact_durable_effects=72, original_unchanged=True)
    except BaseException as error: report['error'] = repr(error)
    report.update(host_seconds=time.monotonic() - began, fixture_sha256=sha(__file__),
                  observer_sha256=sha(ROOT / 'scripts/observe_usb_workflow_wire.py'),
                  decoder_sha256=sha(ROOT / 'scripts/check_guest_usb_link.py'))
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'error': report.get('error')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
