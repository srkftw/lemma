#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded RTL boot observation through an already paused public session.

PC samples are mapped using the actual source-bound ELF and elaboration symbol
map. Fixed sampling can alias; these counts are observations, not instruction
or cycle attribution. Unknown and zero pipeline PCs are retained. This tool
never generates guest records, resets the machine, or initializes storage.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from lemmasim_session import request


def require(value, message):
    if not value:
        raise ValueError(message)


def read_bounded(path, limit):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= limit, 'Missing or oversized file: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, 'File grew beyond its bound: ' + str(path))
    return data


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ranges(text, source_map):
    """Read literal FUNC ranges; source names are only presentation labels."""
    functions = []
    for row in text.splitlines():
        match = re.fullmatch(r'\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+\S+\s+\S+\s+(\d+)\s+(\S+)\s*', row)
        if match:
            start, length, _, name = match.groups()
            require(len(name) <= 1024, 'ELF function label exceeds bound')
            start, length = int(start, 16), int(length)
            if length:
                require(start + length <= 1 << 64, 'ELF function range overflows')
                functions.append((start, start + length, source_map.get(name, name)))
                require(len(functions) <= 65536, 'Too many ELF function ranges')
    require(functions, 'ELF contains no nonempty defined function ranges')
    return functions


def labels(pc, functions):
    if pc == 0:
        return ['unresolved:pc0']
    found = sorted({name for start, end, name in functions if start <= pc < end})
    require(len(found) <= 32, 'Too many overlapping PC symbol candidates')
    return found or ['unresolved:' + hex(pc)]


def symbols(build, output, readelf):
    manifest_data = read_bounded(build / 'build.json', 1 << 20)
    manifest = json.loads(manifest_data)
    artifacts = manifest.get('artifacts')
    require(manifest.get('status') == 'BUILT' and isinstance(artifacts, dict), 'Missing BUILT artifact manifest')
    identities = [{'path': str(build / 'build.json'), 'sha256': sha(manifest_data)}]

    def admitted(name, limit):
        data = read_bounded(build / name, limit)
        require(sha(data) == artifacts.get(name), 'Artifact hash mismatch: ' + name)
        identities.append({'path': str(build / name), 'sha256': sha(data)})
        return data

    sources = {}
    for role in ('kernel', 'firmware'):
        for row in admitted(role + '/symbols.txt', 2 << 20).decode().splitlines():
            match = re.fullmatch(r'source=(.+);llvm=(\S+)', row)
            require(match is not None, 'Malformed elaboration symbol map')
            source, name = match.groups()
            require(len(source) <= 1024 and len(name) <= 1024, 'Elaboration symbol label exceeds bound')
            require(name not in sources, 'Duplicate boot LLVM symbol label')
            sources[name] = source
    image = admitted('image.elf', 32 << 20)
    command = [readelf, '--symbols', '--wide', str(build / 'image.elf')]
    process = subprocess.run(command, capture_output=True, timeout=30, check=False)
    require(process.returncode == 0 and len(process.stdout) <= 8 << 20, 'readelf failed or output exceeds bound')
    (output / 'elf-symbols.txt').write_bytes(process.stdout)
    functions = ranges(process.stdout.decode(), sources)
    # U PCs use independently linked ELFs and may overlap across tasks. Preserve
    # every matching candidate, never guess task identity from a PC alone.
    users = sorted(name for name in artifacts if re.fullmatch(r'users/[A-Za-z0-9_-]+/image\.elf', name))
    require(len(users) <= 32, 'Too many user symbol images')
    user_functions = []
    for name in users:
        unit = str(Path(name).parent)
        mapping = {}
        for row in admitted(unit + '/symbols.txt', 2 << 20).decode().splitlines():
            match = re.fullmatch(r'source=(.+);llvm=(\S+)', row)
            require(match is not None, 'Malformed user elaboration symbol map')
            source, llvm = match.groups()
            require(len(source) <= 1024 and len(llvm) <= 1024, 'User elaboration symbol label exceeds bound')
            require(llvm not in mapping, 'Duplicate user LLVM symbol label')
            mapping[llvm] = source
        admitted(name, 32 << 20)
        decoded = subprocess.run([readelf, '--symbols', '--wide', str(build / name)],
                                 capture_output=True, timeout=30, check=False)
        require(decoded.returncode == 0 and len(decoded.stdout) <= 8 << 20, 'User readelf failed or exceeded bound')
        (output / (Path(unit).name + '-elf-symbols.txt')).write_bytes(decoded.stdout)
        user_functions += [(start, end, unit + ':' + label)
                           for start, end, label in ranges(decoded.stdout.decode(), mapping)]
    return sha(image), {'boot': functions, 'user': user_functions}, identities


def ready(serial, state, start_byte=0):
    data = read_bounded(serial, 2 << 20)
    require(0 <= start_byte <= len(data), 'UART output was truncated during observation')
    data = data[start_byte:]
    rows = re.findall(rb'K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})', data)
    return any(int(row[0], 16) == 0x420 for row in rows) and state['paper_busy'] == state['block_state'] == 0


def observe(args):
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    result = {'status': 'FAIL', 'observer_sha256': sha(read_bounded(__file__, 1 << 20)),
              'session_dir': str(args.session_dir.resolve()), 'guest_build': str(args.guest_build.resolve()),
              'bounds': {'cycles': args.cycles, 'quantum': args.quantum,
              'deadline_seconds': args.deadline, 'request_timeout_seconds': args.timeout},
              'sample_relation': 'PC and privilege at every declared quantum; all unknown PCs retained; no attribution or backend equivalence claim'}
    try:
        guest_sha, units, inputs = symbols(args.guest_build.resolve(), output, args.readelf)
        before = request(args.session_dir, {'action': 'inspect'}, args.timeout)
        require(before['running'] is False, 'Pause the public session before profiling')
        require(before['identity']['backend'] == 'rtl', 'This PC diagnostic requires the RTL backend')
        require(before['identity']['guest'] == guest_sha, 'Live guest differs from the source-bound ELF')
        result.update(identity=before['identity'], inputs=inputs, initial=before['machine'])
        initial = before['machine']['cycle']
        state, counts, samples, observed_ready = before['machine'], Counter(), 0, False
        result.update(last=state, samples=0, source_pc_samples={})
        serial = args.session_dir / 'uart.bin'
        serial_start = len(read_bounded(serial, 2 << 20)) if serial.exists() else 0
        result['uart_start_byte'] = serial_start
        with (output / 'samples.jsonl').open('x') as trace:
            while state['cycle'] - initial < args.cycles:
                require(time.monotonic() - started < args.deadline, 'Declared host deadline exceeded')
                require(not state['finished'], 'Guest finished before its boot milestone')
                amount = min(args.quantum, args.cycles - (state['cycle'] - initial))
                call_started = time.monotonic()
                next_state = request(args.session_dir, {'action': 'run', 'cycles': amount}, args.timeout)
                require(next_state['cycle'] == state['cycle'] + amount, 'Runtime interval did not complete exactly')
                phase = 'user' if next_state['privilege'] == 0 else 'boot'
                matched = labels(next_state['pc'], units[phase])
                trace.write(json.dumps({'seconds': time.monotonic() - call_started,
                            'requested_cycles': amount, 'machine': next_state, 'pc_labels': matched}, separators=(',', ':')) + '\n')
                trace.flush()
                require(trace.tell() <= 16 << 20, 'PC trace exceeds its 16 MiB resource bound')
                counts[' | '.join(matched)] += 1
                samples += 1
                state = next_state
                result.update(last=state, samples=samples, source_pc_samples=dict(counts.most_common()))
                observed_ready = ready(serial, state, serial_start)
                if observed_ready and 'ready_cycle' not in result:
                    result['ready_cycle'] = state['cycle']
                if args.require_ready and observed_ready:
                    break
        result.update(last=state, samples=samples, source_pc_samples=dict(counts.most_common()),
                      ready=observed_ready, uart_sha256=sha(read_bounded(serial, 2 << 20)),
                      wall_seconds=time.monotonic() - started)
        result['status'] = ('PASS' if observed_ready else 'FAIL_NOT_READY') if args.require_ready else 'OBSERVED_PREFIX'
        if args.snapshot_final is not None:
            # Preserve the observed boundary for a later bounded suffix. The
            # ordinary machine API saves in-flight state without boot, drain,
            # flush or reset; a readiness failure remains a readiness failure.
            saved = request(args.session_dir, {'action': 'snapshot',
                            'path': str(args.snapshot_final.resolve())}, args.timeout)
            require(saved['machine'] == state, 'Snapshot changed the observed RTL boundary')
            manifest = read_bounded(args.snapshot_final / 'snapshot.json', 32768)
            result['final_checkpoint'] = {'path': saved['snapshot'],
                'manifest_sha256': sha(manifest), 'cycle': state['cycle'],
                'boundary_unchanged': True}
        if args.require_ready:
            require(observed_ready, 'Real guest READY and idle controllers were not observed within the declared bound')
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as error:
        if not result['status'].startswith('FAIL'):
            result['status'] = 'FAIL'
        result['error'] = str(error)
    finally:
        result['wall_seconds'] = time.monotonic() - started
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['status'] in ('PASS', 'OBSERVED_PREFIX') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-dir', required=True, type=Path)
    parser.add_argument('--guest-build', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--cycles', type=int, default=100000000)
    parser.add_argument('--quantum', type=int, default=1000000)
    parser.add_argument('--deadline', type=int, default=600)
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--readelf', default='llvm-readelf')
    parser.add_argument('--require-ready', action='store_true')
    parser.add_argument('--snapshot-final', type=Path,
                        help='save this exact paused boundary to a new checkpoint directory, including when READY is absent')
    args = parser.parse_args()
    require(0 < args.cycles <= 1000000000 and 100000 <= args.quantum <= 10000000,
            'Cycles/quantum outside bounded diagnostic range')
    require((args.cycles + args.quantum - 1) // args.quantum <= 4096, 'Too many PC samples')
    require(0 < args.deadline <= 1800 and 0 < args.timeout <= 60, 'Host bounds outside diagnostic range')
    return observe(args)


if __name__ == '__main__':
    raise SystemExit(main())
