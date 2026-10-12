#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual prepared Lean guest prefix: warm/cold clocks and exact reset replay.

This checks the machine lifecycle, not notebook readiness or cold recovery.
The public notebook workflow has its separate independent acceptance checker.
"""
import argparse
import json
import re
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lemmasim_fast import Fast, ADAPTER, CLOCK_SCHEMA, MAX_NS
from lemmasim_session import Session, digest, write_json
import check_fast_state_equivalence as observer


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--profile', default='lemma-silicon-dev/0.2.0')
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    directory = args.work_dir.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    plan = {'relation': 'exact wrapper clock state and all VMState bytes except two pinned named host statistics',
            'observer_sha256': digest(Path(observer.__file__)), 'adapter': ADAPTER,
            'scope': 'genuine Lean notebook image executing a bounded boot prefix; no notebook readiness claim'}
    write_json(directory / 'plan.json', plan)
    result = {'status': 'FAIL', **plan}
    machine = session = None
    try:
        live = directory / 'live'; live.mkdir()
        medium = directory / 'durable.raw'
        with medium.open('xb') as stream:
            stream.truncate(256 * 1024 * 1024)
        options = SimpleNamespace(workload='notebook', profile=args.profile, disk=medium,
            memory_latency=0, fail_flush=0, events=None, trace_limit=0, timeout=args.timeout,
            mode='laboratory', paused=True, quantum=100000)
        machine = Fast(options, live)
        session = Session(machine, live, options)
        result['identity'] = machine.identity
        require(machine.identity['runtime'] == observer.RUNTIME_SHA256, 'Unreviewed actual QEMU identity')
        first = machine.run_until_ns(1000004)
        require(first['ticks'] == 10000, 'Actual ACLINT clock differs at admitted warm cutpoint')
        prefix = directory / 'prefix'; session.snapshot(prefix)
        warm = session.dispatch({'action': 'warm-reset'})
        require(warm['virtual_ns'] == first['virtual_ns'] and warm['ticks'] == 0,
                'Warm reset must preserve session phase and reset actual MTIME')
        pc = re.search(r'^\s*pc\s+([0-9a-fA-F]{16})\s*$', warm['cpu_registers'], re.MULTILINE)
        require(pc is not None and int(pc[1], 16) == 0x1000, 'Warm reset did not enter the real reset ROM')
        after_warm = machine.run_until_ns(first['virtual_ns'] + 500000)
        require(after_warm['ticks'] == 5000, 'Actual ACLINT warm-reset phase did not resume from zero')
        cold = session.dispatch({'action': 'cold-cycle'})
        require(cold['virtual_ns'] == after_warm['virtual_ns'] and cold['local_virtual_ns'] == 0 and cold['ticks'] == 0,
                'Cold cycle regressed session time or retained the old guest clock')
        origin = cold['virtual_ns']
        machine.run_until_ns(origin + 500004)
        delivery = (origin + 800000 + 9) // 10
        words = [23111, 40, 50, 127, 3, 1, 0]
        admitted = session.dispatch({'action': 'inject', 'kind': 'pen', 'cycle': delivery, 'words': words})
        require(admitted['time_origin_ns'] == origin, 'Admission changed wrapper origin')
        session.snapshot(directory / 'pending-after-cold')
        end = machine.run_until_ns(origin + 1500000)['virtual_ns']
        baseline = machine.inspect()
        original = directory / 'final-original'; session.snapshot(original)
        capture = directory / 'closed.jsonl'
        shutil.copyfile(live / 'external.jsonl', capture)
        rows = [json.loads(row) for row in capture.read_text().splitlines()]
        require([row['request']['action'] for row in rows] == ['warm-reset', 'cold-cycle', 'inject'],
                'Actual lifecycle capture omitted or fabricated an action')
        require([row['virtual_ns'] for row in rows] == sorted(row['virtual_ns'] for row in rows),
                'Cold cycle made the captured virtual phases descend')
        replayed = session.replay(prefix, capture, None, end)['machine']
        require(replayed == baseline, 'Actual CPU/device/storage/clock inspection differs after reset replay')
        replay = directory / 'final-replayed'; session.snapshot(replay)
        state_result = observer.compare_checkpoints(original / 'machine.chk', replay / 'machine.chk')
        state_result['observer_sha256'] = digest(Path(observer.__file__))
        write_json(directory / 'state-equivalence.json', state_result)
        require(state_result['status'] == 'PASS', 'Authoritative checkpoint state differs after reset replay')
        require((machine.directory / f'input-{machine.generation}.bin').read_bytes() ==
                (live / 'input-1.bin').read_bytes(), 'Actual delivered raw sample suffix differs')
        unchanged = machine.inspect()
        try:
            machine.run_until_ns(MAX_NS)
        except ValueError:
            pass
        else:
            raise ValueError('Overflowing instruction phase was admitted')
        require(machine.inspect() == unchanged, 'Rejected overflow changed the real machine')
        invalid = directory / 'bad-clock'; invalid.mkdir()
        (invalid / 'clock.json').write_text(json.dumps({'schema': CLOCK_SCHEMA, 'time_origin_ns': True}))
        count = len(list(live.glob('machine-fork-*')))
        try:
            machine.restore_checkpoint(invalid / 'machine.chk', unchanged['virtual_ns'])
        except ValueError:
            pass
        else:
            raise ValueError('Malformed clock origin reached candidate VM creation')
        require(len(list(live.glob('machine-fork-*'))) == count and machine.inspect() == unchanged,
                'Malformed clock restore changed owned state')
        result.update(status='PASS', warm=warm, after_warm=after_warm, cold=cold,
                      final=baseline, capture_rows=rows, state_equivalence='state-equivalence.json',
                      negatives=['overflow rejected before admission', 'boolean origin rejected before candidate creation'])
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        result['error'] = str(error)
    finally:
        if session is not None:
            session.close()
        elif machine is not None:
            machine.close()
        write_json(directory / 'result.json', result)
    print(result['status'] + ': ' + str(directory / 'result.json'))
    return result['status'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
