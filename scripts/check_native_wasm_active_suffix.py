#!/usr/bin/env python3
"""A finite active native/Wasm continuation from their separately qualified
own901M archives. Raw controls execute the real arithmetic/checker/Store path.
Every authoritative byte remains load-bearing except the two already declared
implementation-identity headers. No cross-restore, QEMU cached continuation,
all-ISA coverage or arbitrary-boundary completeness is claimed.
"""
import argparse
import filecmp
import json
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time

import lemmasim_session as sessions
from check_browser_cold_export import exported, sha
from check_companion_pending import timed_records
from check_live_notebook import visible_pixels

ROOT = Path(__file__).resolve().parents[1]
NATIVE = '600e93eb1981b3eb5432840c0fd8e169b4d5cfd04f89e8164450d1c70b159bba'
WASM = '84d52d610d2819e294b1c130b362e1289c48dfe31285225140029e9168c8e5a5'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def outcome_window(path, identity, first, last, end):
    """Keep original complete recorded entries, including their original CRCs."""
    raw = Path(path).read_bytes()
    require(len(raw) <= 16 << 20 and raw[:8] == b'LMIOLOG2' and
            raw[8:72].decode() == identity, 'original actual outcome identity/size')
    rows, pending = timed_records(path)
    selected = [(fields, completed) for fields, completed in rows if first <= fields[0] <= last]
    require([fields[0] for fields, _ in selected] == list(range(first, last + 1)) and
            all(fields[1] <= completed <= end for fields, completed in selected),
            'actual contiguous suffix outcome identities/boundaries')
    require(all(fields[1] > end for fields, _ in rows if fields[0] > last) and
            (pending is None or pending[0][0] > last and pending[0][1] > end),
            'omitted operation already admitted at the selected cut')
    at, selected_bytes = 72, bytearray()
    while at < len(raw):
        tag, size = struct.unpack_from('<2Q', raw, at)
        end_record = at + 16 + size
        identity_id = struct.unpack_from('<Q', raw, at + 16)[0]
        if first <= identity_id <= last:
            selected_bytes.extend(raw[at:end_record])
        at = end_record
    return bytes(selected_bytes), selected


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('native-bundle', 'native-start', 'origin-plan', 'origin-proof',
                 'browser-end', 'browser-state', 'browser-medium', 'browser-pixels',
                 'browser-outcomes', 'raw-capture', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, lambda code, frame: (_ for _ in ()).throw(SystemExit(128 + code)))
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    began, used = time.monotonic(), 0
    report = {'status': 'RUNNING', 'scope': __doc__, 'bounds': {
        'whole_seconds': 9000, 'active_clocks': 600000000, 'active_seconds': 7200,
        'observer_seconds': 180, 'per_process_AS_bytes': 4 << 30, 'file_bytes': 1 << 30}}
    process = None
    live = out / 'native'

    def save():
        report.update(seconds=time.monotonic() - began, RTL_clocks=used)
        (out / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')

    def guard():
        require(time.monotonic() - began <= 9000 and used <= 600000000, 'whole bound')
        require(all(sha(ROOT / name) == digest for name, digest in report['host_inputs'].items()),
                'actual consumed observer/launcher source changed')

    def call(request):
        guard()
        return sessions.request(live, request, 120)

    try:
        origin = json.loads(args.origin_plan.read_text())
        proof = json.loads(args.origin_proof.read_text())
        start = proof['cuts']['suffix901M']
        require(proof['status'] == 'PASS_SAME_RTL_NATIVE_WASM_COLD_COURSE_AND_EXACT_SUFFIX' and
                origin['native_identity'] == NATIVE and origin['Wasm_snapshot_identity'] == WASM and
                start['cycle'] == 901000000 and start['only_excluded_state_bytes'] == [16, 80] and
                start['only_excluded_tape_bytes'] == [8, 72] and start['original_CRC_valid'] and
                sha(args.native_start / 'machine.chk') == start['native_sha256'],
                'actual previously qualified separate native/Wasm start relation required')
        state = json.loads(args.browser_state.read_text())['state']
        endpoint = int(state['cycle'])
        require(endpoint == 1338250000 and endpoint - start['cycle'] <= 600000000 and
                state['event_queue'] == '0' and state['backing_io']['phase'] == '2' and
                state['backing_io']['next_id'] == str(int(state['backing_io']['completed']) + 1),
                'fixed actual current-hint math/Store endpoint required')
        captures = json.loads(args.raw_capture.read_text())
        require(captures['schema'] == 'lemmasim-browser-raw-capture/1', 'actual raw capture schema')
        events = []
        for line in captures['events']:
            fields = line.split()
            require(len(fields) == 9 and fields[1] == 'pen' and
                    all(word.isdecimal() and int(word) < 1 << 64 for word in fields[:1] + fields[2:]),
                    'actual bounded raw pen fields')
            if int(fields[0]) <= endpoint:
                events.append(line)
        original_events = Path(origin['events'])
        require(sha(original_events) == origin['event_sha256'] and
                events[:2] == original_events.read_text().splitlines() and len(events) == 20,
                'original first two events or actual eighteen new controls differ')
        require(all(901000000 < int(line.split()[0]) <= endpoint for line in events[2:]),
                'selected new control outside actual suffix')
        report['input_files'] = {str(path.resolve()): sha(path) for path in
            (args.origin_plan, args.origin_proof, args.native_start / 'machine.chk',
             args.browser_end, args.browser_state, args.browser_medium, args.browser_pixels,
             args.browser_outcomes, args.raw_capture)}
        report['host_inputs'] = {}
        for module in list(sys.modules.values()):
            file = getattr(module, '__file__', None)
            if file:
                source = Path(file).resolve()
                if source.suffix == '.py' and source.is_relative_to(ROOT):
                    relative = source.relative_to(ROOT)
                    if relative.parts[0] in ('scripts', 'conformance'):
                        report['host_inputs'][str(relative)] = sha(source)
        report['host_inputs']['scripts/lemmasim'] = sha(ROOT / 'scripts/lemmasim')
        report.update(origin_proof_sha256=sha(args.origin_proof), start_cycle=901000000,
                      endpoint=endpoint, raw_suffix=events[2:], scope_limit=__doc__)
        preflight = time.monotonic()
        wf, wu, wv = exported(args.browser_end, WASM)
        require(wf[1] == endpoint and wf[0] == 20 and wf[7] == int(state['retired']),
                'browser original CRC/state disagrees with its actual visible cut')
        report['browser_preflight_seconds'] = time.monotonic() - preflight
        save()
        argv = [sys.executable, '-B', str(ROOT / 'scripts/lemmasim'), 'session', '--backend', 'rtl',
                '--profile', 'lemma-silicon-dev/0.3.0', '--native-bundle', str(args.native_bundle.resolve()),
                '--restore', str(args.native_start.resolve()), '--session-dir', str(live),
                '--mode', 'laboratory', '--paused', '--headless', '--timeout', '120']
        with (out / 'launch.log').open('xb') as log:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        until = time.monotonic() + 30
        while not (live / 'session.json').is_file():
            require(process.poll() is None and time.monotonic() < until, 'private native restore failed')
            time.sleep(.05)
        initial = call({'action': 'inspect'})['machine']
        require(initial['cycle'] == 901000000 and initial['snapshot_identity'] == NATIVE and
                initial['retired'] == start['retired'] and initial['event_queue'] == 0 and
                initial['isolated_medium'] is True, 'exact own-backend private starting state')
        for line in events[2:]:
            fields = line.split()
            call({'action': 'inject', 'kind': 'pen', 'cycle': int(fields[0]),
                  'words': [int(word) for word in fields[2:]]})
        active_started = time.monotonic()
        while True:
            current = call({'action': 'inspect'})['machine']
            require(time.monotonic() - active_started <= 7200 and not current['finished'],
                    'active execution host/guest bound')
            if current['cycle'] == endpoint:
                break
            amount = min(1000000, endpoint - current['cycle'])
            require(amount > 0, 'fixed RTL endpoint exceeded')
            call({'action': 'run', 'cycles': amount})
            after = call({'action': 'inspect'})['machine']
            require(after['cycle'] == current['cycle'] + amount, 'exact actual RTL clocks')
            used += amount
            if used % 50000000 == 0:
                report['active_progress'] = {'cycle': after['cycle'], 'retired': after['retired'],
                                              'seconds': time.monotonic() - active_started}
                save()
        require(current['retired'] == int(state['retired']) and current['retired'] > initial['retired'],
                'actual nonempty instruction suffix differs')
        checkpoint = out / 'native-end'
        call({'action': 'snapshot', 'path': str(checkpoint)})
        require(call({'action': 'inspect'})['machine'] == current, 'snapshot mutated machine')
        call({'action': 'panel', 'path': str(out / 'native-end.pgm')})
        call({'action': 'export-medium', 'path': str(out / 'native-end.raw')})
        observer_started = time.monotonic()
        nf, nu, nv = exported(checkpoint / 'machine.chk', NATIVE)
        native_raw, wasm_raw = (checkpoint / 'machine.chk').read_bytes(), args.browser_end.read_bytes()
        require(native_raw[:16] + native_raw[80:] == wasm_raw[:16] + wasm_raw[80:] and
                nf == wf and nu == wu and nv == wv, 'full authoritative state/CRC/UART/visible bytes differ')
        require(filecmp.cmp(out / 'native-end.raw', args.browser_medium, shallow=False) and
                visible_pixels(out / 'native-end.pgm') == visible_pixels(args.browser_pixels),
                'all actual backing/controller pixels differ')
        rgb = bytes(channel for value in wv for channel in (value * 17,) * 3)
        require(visible_pixels(args.browser_pixels) == (1650, 2200, rgb),
                'browser snapshot differs from independent controller export')
        first, last = start['actual_outcome_count'] + 1, current['backing_io']['completed']
        require(last == int(state['backing_io']['completed']) and last > first and
                current['backing_io']['phase'] == 2, 'real new completed I/O suffix absent')
        capture_paths = sorted(live.glob('backing.io.fork-1-*'))
        require(len(capture_paths) == 1, 'one actual privately restored native outcome tape required')
        native_io, native_rows = outcome_window(capture_paths[0], NATIVE, first, last, endpoint)
        wasm_io, wasm_rows = outcome_window(args.browser_outcomes, WASM, first, last, endpoint)
        require(native_io == wasm_io and native_rows == wasm_rows and
                any(fields[2] == 1 for fields, _ in native_rows) and
                any(fields[2] == 2 for fields, _ in native_rows),
                'exact real WRITE/BARRIER outcome bytes/times/order differ')
        require(time.monotonic() - observer_started <= 180, 'original complete observer bound')
        require(all(sha(Path(path)) == digest for path, digest in report['input_files'].items()),
                'original input changed')
        report.update(status='PASS_NATIVE_WASM_ACTIVE_MATH_STORE_EXACT_SUFFIX',
                      retired_in_suffix=current['retired'] - initial['retired'],
                      first_outcome=first, last_outcome=last, exact_outcomes=len(native_rows),
                      native_snapshot_sha256=sha(checkpoint / 'machine.chk'),
                      wasm_snapshot_sha256=sha(args.browser_end), original_CRC_valid=True,
                      only_excluded_state_bytes=[16, 80], only_excluded_tape_bytes=[8, 72],
                      all_medium_bytes=268435456, all_controller_pixels=3630000,
                      active_seconds=time.monotonic() - active_started,
                      observer_seconds=time.monotonic() - observer_started)
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        if process is not None:
            try:
                sessions.request(live, {'action': 'destroy'}, 5)
                process.wait(timeout=5)
            except BaseException as error:
                report['cleanup_error'] = repr(error)
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
        report.update(seconds=time.monotonic() - began, RTL_clocks=used)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
