#!/usr/bin/env python3
"""Reobserve retained Reader19 records without changing the failed campaign.

No machine is launched, medium repaired or original failure renamed. The
independent checker requires all three normal ink publications, including root.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from reader_reconciliation_oracle import observe, require, READER, WORKSPACE, PAGE, ROOT as ROOT_KEY, RAW
from store_oracle import recover
from check_live_notebook import guest_events
from check_guest_usb_notebook import opaque_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-directory', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    case, out = args.case_directory.resolve(), args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused owned output required')
    out.mkdir(parents=True)
    started = time.monotonic()
    result = {'status': 'FAIL', 'scope': __doc__, 'inputs': {}, 'negative_cases': []}

    def read(name):
        path = case / name
        require(not path.is_symlink() and path.is_file(), 'missing/symlinked retained input')
        data = path.read_bytes()
        result['inputs'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        return data

    try:
        original = json.loads(read('result.json'))
        require(original['status'] == 'FAIL' and original['error'] ==
                "ValueError('real reader24 plus exact offline raw/page durability')",
                'declared original observer failure required')
        _, prior_seq, before = recover(read('before.raw'))
        _, held_seq, held = recover(read('observed-unacknowledged-reader24.raw'))
        _, final_seq, final = recover(read('acknowledged.raw'))
        require((prior_seq, held_seq) == (23, 24), 'declared source23/held24 required')
        events = read('first/input.events').decode().splitlines()
        pens = [line.split() for line in events if line.split()[1] == 'pen']
        # Positions9..11 are the actual independently captured offline gesture.
        # Sequence/epoch are the original no-pen-reset case's controller values.
        samples = [(index, *map(int, row[2:]), 1)
                   for index, row in enumerate(pens, 1) if 9 <= index <= 11]
        result['records'] = observe(before, held, final, samples, final_seq)
        rows = guest_events(case / 'first/uart.bin')
        read('first/uart.bin')
        failure = rows.index((0x424, 227, 1, 1, READER[1]))
        reconciled = rows.index((0x421, 24, 1, 1, READER[1]))
        saved = rows.index((0x421, 27, 1, 1, 24))
        require(failure < reconciled < saved and not any(
                row[0] == 0x421 and row[1] >= 24 for row in rows[:failure]),
                'guest acknowledged uncertain bytes early or omitted ordered reconciliation')
        read('peer/opaque.log')
        effects = opaque_log(case / 'peer/opaque.log')
        lost = original['lost_final_barrier']['effects']
        first = next(i for i, (fields, _) in enumerate(effects) if fields[4] == lost[0][4])
        tail = effects[first:]
        require([list(fields) for fields, _ in tail[:6]] == lost and
                [fields[4] for fields, _ in tail] == list(range(lost[0][4], lost[0][4] + 25)) and
                [fields[2] for fields, _ in tail] == [1, 1, 1, 2, 1, 2, 2] + [1, 1, 1, 2, 1, 2] * 3 and
                sum(fields[4] == lost[-1][4] for fields, _ in effects) == 1,
                'lost effect duplicated or reader/reconciliation/three-record durability ordering differs')
        # Mutate actual recovered values privately. These expose the previously
        # omitted root, changed evidence, duplicate/missing ink and bad reader.
        for label, key, record, sequence in (
            ('missing-root-publication', ROOT_KEY, before[ROOT_KEY], 27),
            ('changed-root-content', ROOT_KEY, replace(final[ROOT_KEY], payload=bytes(64)), 27),
            ('missing-raw', RAW, None, 27),
            ('changed-raw-sample', RAW, replace(final[RAW], payload=final[RAW].payload[:-1] + b'\x01'), 27),
            ('changed-page-history', PAGE, replace(final[PAGE], payload=final[PAGE].payload[:-1] + b'\x01'), 27),
            ('changed-workspace', WORKSPACE, replace(final[WORKSPACE], payload=b'changed'), 27),
            ('changed-reader', READER, replace(final[READER], sequence=25), 27),
            ('old-two-record-expectation', ROOT_KEY, final[ROOT_KEY], 26),
        ):
            changed = dict(final)
            if record is None:
                del changed[key]
            else:
                changed[key] = record
            try:
                observe(before, held, changed, samples, sequence)
            except (ValueError, KeyError):
                result['negative_cases'].append({'case': label, 'status': 'REJECTED'})
            else:
                raise ValueError('actual record corruption accepted: ' + label)
        result.update(status='PASS_REOBSERVED_READER24_RAW25_PAGE26_ROOT27',
                      final_sequence=27, lost_barrier_effect_count=1,
                      retry_barrier_distinct=True, new_guest_execution=False,
                      original_campaign_status='FAIL_UNCHANGED', cold_recovery='NOT_RUN')
    except BaseException as error:
        result['error'] = repr(error)
    finally:
        result.update(seconds=time.monotonic() - started,
                      observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      oracle_sha256=hashlib.sha256((ROOT / 'conformance/lemmasim/reader_reconciliation_oracle.py').read_bytes()).hexdigest())
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], result.get('error', ''), flush=True)
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
