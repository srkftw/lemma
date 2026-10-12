#!/usr/bin/env python3
"""Read-only qualification of actual arithmetic IPC against durable history.

This observer consumes retained guest UART and independently recovered medium
bytes. It supplies no result, packet, instruction or document to the guest.
"""
import argparse
import json
from pathlib import Path
import struct

from check_live_notebook import guest_events, require, sha
from math_oracle import inspect as inspect_math
from store_oracle import recover


def validate(rows, history):
    require(all(len(row) == 5 and all(type(x) is int and 0 <= x < 2**64 for x in row) for row in rows),
            'malformed actual guest trace')
    rows = [tuple(row) for row in rows]
    require(not any(row[0] in (0xd4, 0xf4, 0x454) for row in rows), 'normal checker or notebook failed')
    images = [row for row in rows if row[0] == 0xf1]
    require(sorted((row[2], row[3]) for row in images) == [(0, 0), (1, 2), (2, 0)] and
            len({row[1] for row in images}) == 3 and all(row[1] and row[4] for row in images),
            'three genuine isolated image indices/arguments were not observed')
    require([row for row in rows if row[0] == 0x456] == [(0x456, 0, 0, 1, 10_000_000)],
            'actual normal arithmetic startup/deadline differs')
    requests = [row for row in rows if row[0] == 0x459]
    replies = [row for row in rows if row[0] == 0x455]
    require(len(requests) == len(replies) == len(history) and len(history) > 0,
            'missing or extra actual IPC request/reply versus durable attempt')
    require(len({row[1] for row in requests}) == len(requests) and all(row[1] and row[4] for row in requests),
            'request or actual transaction identity missing/reused')
    observed = []
    for request, attempt in zip(requests, history):
        matching = [row for row in replies if row[1] == request[1]]
        require(len(matching) == 1, 'reply missing or transaction duplicated')
        reply = matching[0]
        require((request[2], request[3]) == (attempt['revision'], attempt['goal']) and
                (reply[2], reply[3], reply[4]) == (attempt['revision'], 0, attempt['outcome']),
                'isolated reply differs from independently checked revision/domain/history')
        require(any(row[0] == 0x450 and row[1:] ==
                    (attempt['revision'], attempt['goal'], attempt['outcome'], attempt['revision']) for row in rows),
                'reply was not published with its exact original revision')
        observed.append(dict(request=request[1], transaction=request[4], revision=request[2],
                             goal=request[3], status=reply[3], outcome=reply[4]))
    return observed


def validate_isolation(rows, case, expected_raw, stored_raw):
    """Qualify the retained actual suffix, including complete raw tuple counts."""
    require(case in ('oom', 'fault', 'stall'), 'unknown isolation case')
    require(all(len(row) == 5 and all(type(x) is int and 0 <= x < 2**64 for x in row)
                for row in rows), 'malformed actual isolation trace')
    rows = [tuple(row) for row in rows]
    mode = {'oom': 1, 'fault': 2, 'stall': 3}[case]
    images = [row for row in rows if row[0] == 0xf1]
    require(sorted((row[2], row[3]) for row in images) == [(0, 0), (1, 2), (2, mode)] and
            len({row[1] for row in images}) == 3 and all(row[1] and row[4] for row in images),
            'actual isolated deployment differs')
    require([row for row in rows if row[0] == 0x456] ==
            [(0x456, mode, 31 if case == 'oom' else 0, 1, 10_000_000)],
            'actual server mode/deadline/pressure differs')
    require(not any(row[0] == 0x424 or row[0] == 0x41f or
                    (row[0] == 0x450 and row[3] != 0) for row in rows),
            'failure lost storage or manufactured evidence')
    require([row[1] for row in rows if row[0] == 0x454] ==
            [{'oom': 237, 'fault': 96, 'stall': 93}[case]], 'actual terminal error differs')
    server = next(row[1] for row in images if row[2] == 2)
    deaths = [row for row in rows if row[0] == 0xf4]
    faults = [row for row in rows if row[0] == 0xd4]
    if case == 'fault':
        require(deaths and all(row[1] == server for row in deaths) and faults and
                all(row[1] == 13 and row[3] == 0x500000 for row in faults) and
                any(row[0] == 0xf6 for row in rows), 'checker death/reap isolation differs')
    else:
        require(not deaths and not faults, 'another process faulted')
    if case == 'oom':
        require(any(row[0] == 0x455 and row[3:] == (237, 0) for row in rows),
                'no actual owned-object OOM')
    if case == 'stall':
        requests = [row for row in rows if row[0] == 0x459]
        require(len(requests) == 3 and requests[1][2] < requests[2][2],
                'edited original request revisions missing')
        require(len([row for row in rows if row[0] == 0x458 and row[1:] == (1, 94, 0, 0)]) == 2,
                'automatic and explicit cancellation were not consumed')
        edit = next((i for i, row in enumerate(rows) if row[0] == 0x450 and
                     row[1:] == (requests[2][2], requests[2][3], 0, 0)), -1)
        require(edit >= 0, 'actual edited revision did not clear applicability')
        for number, request in enumerate(requests[:2]):
            require(any(row[0] == 0x45b and row[1:3] == request[1:3] for row in rows) and
                    any(row[0] == 0x45a and row[1:3] == request[1:3] and
                        row[3] in (80, 83) and row[4] == 3 for row in rows),
                    'real accepted request/retired late reply missing')
            if number == 1:
                require(next(i for i, row in enumerate(rows) if row[0] == 0x45a and
                             row[1:3] == request[1:3]) > edit,
                        'selected late reply preceded the actual edited revision')
    expected_raw, stored_raw = [tuple(row) for row in expected_raw], [tuple(row) for row in stored_raw]
    require(len(expected_raw) == (12 if case == 'stall' else 6) and
            all(len(row) == 9 for row in expected_raw) and
            len({row[0] for row in expected_raw}) == len(expected_raw),
            'declared actual six-sample raw strokes differ')
    require(stored_raw == expected_raw, 'missing, reordered, duplicated or modified durable raw tuple')
    return dict(actual_terminal_error={'oom': 237, 'fault': 96, 'stall': 93}[case],
                actual_raw_samples=len(stored_raw), exact_order_and_multiplicity=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--isolation-case', choices=('oom', 'fault', 'stall'))
    args = parser.parse_args()
    require(not args.output.exists(), 'use an unused evidence path')
    root = args.work_dir.resolve()
    result = json.loads((root / 'result.json').read_text())
    require(result['status'] == 'PASS', 'complete connected course/cold/failure campaign did not pass')
    if args.isolation_case:
        require(result.get('case') == args.isolation_case, 'retained isolation case differs')
        medium = root / ('cancelled.raw' if args.isolation_case == 'stall' else 'final.raw')
        uart, raw = root / 'live/uart-0.bin', root / 'live/input-0.bin'
        captured = raw.read_bytes()
        require(len(captured) % 72 == 0, 'malformed raw capture')
        rows = [struct.unpack_from('<9Q', captured, offset) for offset in range(0, len(captured), 72)]
        require([row[0] for row in rows] == list(range(1, len(rows)+1)), 'raw sequence changed')
        # The declared two or one strokes use row1700..1708 on canonical2200
        # pixels. These literal raw bounds separate them from every course UI
        # contact without deriving guest ink from the notebook implementation.
        expected = [row for row in rows if 50664 <= row[3] <= 50962]
        _, _, records = recover(medium.read_bytes())
        stored = []
        for key, record in sorted(records.items()):
            if key[0] == 1 and key[1] > 0x10000:
                require(len(record.payload) >= 128, 'short actual ink object')
                count = struct.unpack_from('<Q', record.payload, 48)[0]
                require(1 <= count <= 384 and len(record.payload) == 128 + count*72,
                        'malformed actual ink count')
                stored.extend(struct.unpack_from('<9Q', record.payload, 128 + i*72) for i in range(count))
        observed = validate_isolation(guest_events(uart), args.isolation_case, expected, stored)
        evidence = dict(schema='lemma-isolated-arithmetic-retained-observation/1', status='PASS',
                        case=args.isolation_case, identity=result['identity'], observations=observed,
                        scope='read-only actual trace/ingress/durable raw tuple qualification; no new target execution',
                        sources={str(Path(__file__).resolve()): sha(Path(__file__))},
                        inputs={str(path): sha(path) for path in (root / 'result.json', medium, uart, raw)})
        args.output.write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(dict(status='PASS', actual_raw_samples=len(stored), output=str(args.output))))
        return
    medium = root / 'closed-course.raw'
    _, _, records = recover(medium.read_bytes())
    require((1, 0x8001) in records, 'actual guest course record missing')
    record = inspect_math(records[1, 0x8001].payload, 1, 0x8001)
    require(record == result['final_record'], 'actual recovered record differs from campaign')
    uart = root / 'live/uart-0.bin'
    observed = validate(guest_events(uart), record['history'])
    evidence = dict(schema='lemma-isolated-arithmetic-trace/1', status='PASS',
                    scope='actual separately linked scalar arithmetic IPC and durable exact history; not managed language or proof-kernel closure',
                    identity=result['identity'], requests=observed,
                    sources={str(Path(__file__).resolve()): sha(Path(__file__))},
                    inputs={str(path): sha(path) for path in (root / 'result.json', medium, uart)})
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(dict(status='PASS', actual_requests=len(observed), output=str(args.output))))


if __name__ == '__main__':
    main()
