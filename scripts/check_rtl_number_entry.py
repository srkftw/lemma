#!/usr/bin/env python3
"""Run the shared raw number-entry/check/save/cold workflow on canonical RTL.

The guest, input sequence and independent byte/pixel oracles are shared with
check_number_entry_workflow. Only real backend observation, clock accounting
and prospectively declared host/clock bounds differ. No timing-parity claim.
"""
import argparse
import json
from pathlib import Path
import resource
import time

from check_live_notebook import PublicSession, require
from check_course_save import rtl_idle
from check_number_entry_workflow import NumberEntryWorkflow

AGGREGATE_CLOCKS = 5_000_000_000
HOST_SECONDS = 36_000


class RTLNumberEntry(NumberEntryWorkflow):
    backend = 'rtl'
    session_type = PublicSession

    def idle(self, state):
        return rtl_idle(state)

    def phase(self, session, name, cap, predicate):
        if name in ('new-cold-Ready', 'independent-new-CPU-cold-all-pixels'):
            host = 7200
        elif name in ('COURSEactualpackage', 'cold-reopen-installed-body'):
            cap, host = 400_000_000, 3600
        elif name == 'close-course':
            host = 3600
        elif name == 'disconnect-preserves-visible-course-and-keypad':
            host = 3600
        elif name.startswith('actual-') and name.endswith(('-Invalid', '-Verified')):
            host = 2400
        else:
            host = 1800
        before = session.inspect()['machine']
        start = time.monotonic()
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            elapsed = time.monotonic() - start
            used = state['cycle'] - before['cycle']
            require(0 <= used <= cap and self.cycles <= AGGREGATE_CLOCKS and
                    elapsed <= host and time.monotonic() < self.deadline,
                    'prospective exact RTL phase/aggregate bound: ' + name)
            rows = self.rows(session)
            require(not state['finished'] and
                    not any(row[0] in (1055, 1108, 212, 244, 1060) for row in rows),
                    'actual guest failure in ' + name + ':' + repr(rows[-8:]))
            if predicate(state):
                break
            require(used < cap and self.cycles < AGGREGATE_CLOCKS,
                    'exact RTL phase/aggregate clock ceiling: ' + name)
            quantum = min(1_000_000, cap - used, AGGREGATE_CLOCKS - self.cycles)
            session.run(quantum)
            after = session.inspect()['machine']
            require(after['cycle'] - state['cycle'] == quantum,
                    'canonical RTL did not execute the requested clocks')
            self.cycles += quantum
        result = dict(name=name, initial_cycle=before['cycle'],
                      final_cycle=state['cycle'], rtl_clocks=used,
                      host_seconds=elapsed, clock_cap=cap, host_cap=host)
        self.report['phases'].append(result)
        self.progress()
        print(json.dumps(result), flush=True)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('disk', 'work-dir', 'guest-source-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--package', action='append', type=Path, required=True)
    for name in ('native-bundle', 'guest-build'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    args.disk = args.disk.resolve()
    args.package = [path.resolve() for path in args.package]
    args.backend, args.timeout, args.deadline = 'rtl', 120, HOST_SECONDS
    args.durable_suffix_from = None
    args.checkpoint_relation = 'independent cold only; exact same guest; no fast timing claim'
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = RTLNumberEntry(args)
    actor.report.update(scope=__doc__, aggregate_cycles=AGGREGATE_CLOCKS,
        clock_unit='canonical RTL clocks', aggregate_host_seconds=HOST_SECONDS,
        workload_bound_basis='Same connected raw-input case as fast. Real canonical cold493M, '
        'course194M and failed-save/cold1.402B observations bound these phases independently. '
        'The longer numeric case has two cold boots, four isolated checks and bounded '
        'mutating/view controls.5B/36000s is declared before its first target clock; '
        'no historical fast or RTL deadline changes.')
    try:
        actor.execute()
        require(actor.report['status'] == 'PASS_GUEST_NUMBER_ENTRY_CHECKING_COLD',
                'shared complete workflow did not pass')
        actor.report['status'] = 'PASS_EXACT_RTL_NUMBER_ENTRY_CHECKING_COLD'
    except BaseException as error:
        actor.report.update(status='FAIL', error=repr(error))
        raise
    finally:
        actor.report['scope'] = __doc__
        actor.close()
    print(actor.report['status'], actor.cycles, actor.report['elapsed_seconds'])


if __name__ == '__main__':
    main()
