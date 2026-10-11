# SPDX-License-Identifier: Apache-2.0
"""Short RTL monitor inputs and independent existing Core0 monitor oracle.

Only input bytes and offline observations are produced here. The simulator
still executes every instruction, CSR operation and timer interaction.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from gate9_corpus import Oracle, Request, READY, RESPONSE_BYTES, parse_response, words


def requests():
    return (
        Request(1, 1),
        Request(3, 2, words(0, 0xffffffffffffffff, 5, 0)),
        Request(3, 3, words(1, 0xabc, 0xdef, 0)),
        Request(4, 4, words(0, 32, 165)),
        Request(5, 5, words(0, 32)),
        Request(6, 6, words(0)),
        Request(7, 7, words(100000)),
        Request(3, 8, words(3, 0x123, 2, 0)),
        Request(8, 9),
        Request(9, 10, words(0, 0)),
        Request(10, 11),
    )


def fixture(directory: Path):
    path = directory / 'monitor-input.bin'
    path.write_bytes(b''.join(request.encode() for request in requests()))
    return {'status': 'INPUT_ONLY', 'scope': '11 raw monitor requests; no execution claim'}


def observe(capture: Path):
    uart = (capture / 'uart.bin').read_bytes()
    if not uart.startswith(READY):
        raise ValueError('actual monitor Ready absent')
    uart = uart[len(READY):]
    corpus = requests()
    if len(uart) != len(corpus) * RESPONSE_BYTES:
        raise ValueError('missing or extra actual monitor responses')
    oracle = Oracle([])  # This short corpus does not request PC-bearing ring records.
    for index, request in enumerate(corpus):
        oracle.accept(request, parse_response(uart[index * RESPONSE_BYTES:(index + 1) * RESPONSE_BYTES]))
    result = oracle.finish(integration=False)
    stats = json.loads((capture / 'host-report.json').read_text())
    if not isinstance(stats,dict) or any(type(stats.get(key)) is not int or stats[key]<0
        for key in ('finish_code','timer_traps','traps')) or type(stats.get('finished')) is not bool or \
        not isinstance(stats.get('privilege_cycles'),list) or len(stats['privilege_cycles'])!=4 or \
        any(type(value) is not int or value<0 for value in stats['privilege_cycles']):
        raise ValueError('malformed or missing actual monitor hardware observations')
    if stats['finish_code'] != 0x5555 or not stats['finished'] or \
       stats['timer_traps'] < 3 or stats['traps'] < stats['timer_traps'] + 1 or \
       stats['privilege_cycles'][3] <= 0:
        raise ValueError('actual M-mode trap/timer/finisher observations absent')
    return {'status': 'PASS', 'observations': result, 'hardware': stats,
            'scope': '11 independent monitor responses and RTL trap/timer; not M/S/U or notebook acceptance'}
