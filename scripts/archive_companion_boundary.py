#!/usr/bin/env python3
"""Observationally archive an acknowledged opaque peer/outbox boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import time

from check_guest_usb_link import crc64, decode_capture, require, sha
from check_guest_usb_notebook import materialize_observation
from check_guest_usb_store import opaque_log
from lemmasim_companion import initialize, peer_info

ROOT = Path(__file__).resolve().parents[1]


def identity(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode), 'boundary input must be a regular non-symbolic file')
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def outbox_fields(data, writer, high_water):
    require(len(data) == 40 and crc64(data[:-8]) == int.from_bytes(data[-8:], 'little'),
            'boundary outbox is pending or corrupt')
    require(struct.unpack('<4Q', data[:32]) == (0x313054554f434d4c, writer, high_water + 1, 0),
            'boundary outbox does not acknowledge the exact peer high-water')


def log_frames(data):
    require(data[:8] == struct.pack('<Q', 0x3130474f4c434d4c) and len(data) <= 64 << 20,
            'boundary peer journal identity or bound')
    offset, frames = 8, []
    while offset < len(data):
        require(offset + 8 <= len(data), 'boundary peer journal partial length')
        size = int.from_bytes(data[offset:offset + 8], 'little'); offset += 8
        require(72 <= size <= 584 and offset + size <= len(data), 'boundary peer journal partial frame')
        frames.append(data[offset:offset + size]); offset += size
    return frames


def capture(args):
    out = args.output.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned boundary output required')
    out.mkdir(parents=True)
    report = {'schema': 'lemma-companion-observational-boundary/1', 'status': 'FAIL',
              'scope': 'current acknowledged opaque boundary; no machine snapshot, drain, pause or peer request',
              'bounds': {'attempts': 3, 'host_seconds': 30}, 'attempts': []}
    began = time.monotonic()
    try:
        reference = args.reference_suffix.resolve()
        source = json.loads(reference.read_text())
        require(source.get('status') == 'PASS' and source.get('exact_every_snapshot_byte') is True and
                source['identity']['profile'] == 'lemma-silicon-dev/0.8.0', 'reference is not qualified native USB8 suffix')
        evidence = json.loads((ROOT / 'docs/evidence/006-usb8-recorded-suffix.json').read_text())
        declared = evidence['qualified']['queued_successful_receipt_and_later_raw_pen']
        require(sha(reference) == declared['sha256'], 'reference suffix receipt identity differs')
        require((0x421, args.saved_sequence, 1, 1, 3) in
                [tuple(row) for row in source['actual_suffix_uart']], 'reference has no admitted Saved receipt')
        for path, digest in source['input_files'].items():
            require(sha(path) == digest, 'reference input artifact changed')
        tapes = [Path(p) for p in source['input_files'] if Path(p).name == 'suffix-new.tape']
        require(len(tapes) == 1, 'reference tape identity missing')
        rows = tapes[0].read_text().splitlines()
        require(rows[0].startswith('LMUSBRP1 ') and rows[1] == 'HORIZON ' + str(source['captured_tape_horizon'])
                and rows[-1].startswith('CHECKSUM '), 'reference tape container changed')
        raw = out / 'reference.raw'
        raw.write_text(rows[0].replace('LMUSBRP1 ', 'LMUSBRW2 ', 1) + '\n' + '\n'.join(rows[2:-1]) + '\n')
        first = peer_info(args.initial_peer.resolve())
        prior = log_frames((args.initial_peer / 'opaque.log').read_bytes())
        initial_next = len(prior) + 1
        initial_writer = first['writer']
        wire = decode_capture(raw, probe=False, writer=initial_writer, initial_sequence=initial_next)
        requests = [bytes.fromhex(value) for value in wire['requests'][1:]]
        mutations = [value for value in requests if int.from_bytes(value[16:24], 'little') in (1, 2)]
        require(len(prior) + len(mutations) == args.high_water and args.high_water < (1 << 64) - 1,
                'declared high-water is not the exact captured acknowledged receipt prefix')
        expected_log = prior + mutations
        report.update(reference_suffix={'path': str(reference), 'sha256': sha(reference),
            'reference_final_cycle': source['final_cycle']}, saved_sequence=args.saved_sequence,
            high_water=args.high_water, writer=initial_writer, wire_transactions=len(wire['transactions']))
        peer = args.peer.resolve(); state = args.outbox.resolve() / 'outbox'
        inputs = (peer / 'peer.json', peer / 'base.img', peer / 'opaque.log', state)
        require(peer_info(peer)['writer'] == initial_writer, 'boundary peer writer differs')
        qualified = None
        for number in range(3):
            require(time.monotonic() - began < 30, 'boundary observation deadline')
            attempt = out / ('attempt-' + str(number)); attempt.mkdir()
            try:
                before = [identity(p) for p in inputs]
                metadata, log, outbox = inputs[0].read_bytes(), inputs[2].read_bytes(), state.read_bytes()
                outbox_fields(outbox, initial_writer, args.high_water)
                require(log_frames(log) == expected_log, 'later or missing peer mutation outside acknowledged prefix')
                require(len(opaque_log(peer / 'opaque.log')) == args.high_water, 'peer frame checksum/order mismatch')
                base = attempt / 'base.img'
                with inputs[1].open('rb') as src, base.open('xb') as dst:
                    require(os.fstat(src.fileno()).st_size == 268435456, 'opaque base capacity differs')
                    count = 0
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk: break
                        count += len(chunk)
                        if any(chunk): dst.write(chunk)
                        else: dst.seek(len(chunk), os.SEEK_CUR)
                    require(count == 268435456, 'opaque base copy changed size')
                    dst.truncate(count); dst.flush(); os.fsync(dst.fileno())
                require(before == [identity(p) for p in inputs] and
                        (metadata, log, outbox) == (inputs[0].read_bytes(), inputs[2].read_bytes(), state.read_bytes()),
                        'boundary changed during passive observation')
                qualified = (attempt, base, log, outbox, before)
                report['attempts'].append({'ordinal': number, 'status': 'QUALIFIED', 'identities': before})
                break
            except (ValueError, OSError) as error:
                report['attempts'].append({'ordinal': number, 'status': 'REJECTED', 'error': str(error)})
        require(qualified is not None, 'no fully acknowledged observational boundary')
        attempt, base, log, outbox, before = qualified
        initialize(out / 'peer', base=base, writer=initial_writer)
        (out / 'peer/opaque.log').write_bytes(log)
        (out / 'outbox').mkdir(mode=0o700)
        (out / 'outbox/outbox').write_bytes(outbox)
        medium = out / 'acknowledged.raw'
        materialize_observation(out / 'peer', medium)
        for path in (out / 'peer/opaque.log', out / 'outbox/outbox'):
            with path.open('rb') as handle: os.fsync(handle.fileno())
        for directory in (out / 'peer', out / 'outbox', out):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        report.update(status='PASS', boundary='current observational peer/outbox boundary; not the715M machine cut',
            files={str(p.relative_to(out)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
                for p in (out / 'peer/base.img', out / 'peer/opaque.log', out / 'peer/peer.json',
                          out / 'outbox/outbox', medium, raw)}, source_before_after_equal=True)
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['host_seconds'] = time.monotonic() - began
        report['observer_sha256'] = sha(__file__)
        (out / 'boundary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('peer', 'outbox', 'initial-peer', 'reference-suffix', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--saved-sequence', type=int, required=True)
    parser.add_argument('--high-water', type=int, required=True)
    return capture(parser.parse_args())


if __name__ == '__main__': raise SystemExit(main())
