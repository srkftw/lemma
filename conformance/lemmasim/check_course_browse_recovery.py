#!/usr/bin/env python3
"""Cold-reopen submitted-source history without changing current applicability.

The machine receives an opaque private copy of actual acknowledged storage and
raw pen samples. All workspace, history and pixel checks are passive observers.
"""
import argparse
import filecmp
import json
import resource
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'conformance/lemmasim')]
from check_course_math_workflow import CourseMathWorkflow, Input, decode, require, sha, visible_pixels
from check_live_notebook import PublicSession
from check_course_save import rtl_idle
from course_pixel_oracle import course_body_matches, label_matches
from number_pad_reference import pad_matches


class BrowseRecovery(CourseMathWorkflow):
    def __init__(self, args):
        self.backend = args.backend
        if self.backend == 'rtl':
            self.session_type = PublicSession
        super().__init__(args)
        self.report.update(schema='lemma-course-browse-history-connected/1', scope=__doc__,
            aggregate_cycles=1_400_000_000, expected_home_sha256=sha(args.expected_home),
            clock_scope='exact canonical RTL clocks' if self.backend == 'rtl' else 'fast functional units; no RTL timing parity',
            scope_limit='Restores the latest submitted-source location only; no independent arbitrary browse-position persistence, new proof authority or cached-state continuation claim.')

    def idle(self, state):
        return rtl_idle(state) if self.backend == 'rtl' else super().idle(state)

    def phase(self, session, name, cap, predicate):
        before = session.inspect()['machine']['cycle']
        began = time.monotonic()
        host_cap = 7200 if name == 'newCPU-cold-Ready' else 3600
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            used, elapsed = state['cycle'] - before, time.monotonic() - began
            require(0 <= used <= cap and self.cycles <= 1_400_000_000 and
                    elapsed <= host_cap and time.monotonic() < self.deadline,
                    'prospective phase/aggregate bound before accepting ' + name)
            rows = self.rows(session)
            require(not state['finished'] and not any(row[0] in (1055, 1060, 1108, 212, 244) for row in rows),
                    'actual guest failure in ' + name + ': ' + repr(rows[-8:]))
            if predicate(state):
                break
            require(used < cap and self.cycles < 1_400_000_000, 'clock ceiling in ' + name)
            quantum = min(1_000_000, cap - used, 1_400_000_000 - self.cycles)
            session.run(quantum)
            after = session.inspect()['machine']['cycle']
            delta = after - state['cycle']
            require(delta == quantum if self.backend == 'rtl' else delta > 0, 'machine did not advance admitted clocks')
            self.cycles += delta
        result = dict(name=name, initial_cycle=before, final_cycle=state['cycle'],
                      clocks=used, host_seconds=elapsed, clock_cap=cap, host_cap=host_cap)
        self.report['phases'].append(result)
        self.progress()
        print(json.dumps(result), flush=True)
        return state

    def execute(self):
        original, workspace, _, sequence = self.record(self.args.disk)
        require(workspace['current']['origin'] == 'Unknown', 'this case requires Unknown current applicability')
        known = [binding for binding in workspace['history'] if binding['origin'] == 'InstalledPackage']
        require(known, 'no known submitted source to recover')
        source = known[-1]
        matches = [decode(raw) for raw in self.packages
                   if (decode(raw)['identity'], decode(raw)['edition']) == (source['identity'], source['edition'])]
        require(len(matches) == 1 and 1 <= source['node'] <= len(matches[0]['nodes']), 'independent expected source/package missing')
        body = matches[0]['nodes'][source['node'] - 1]['body']
        outcome = workspace['document']['outcome']
        labels = ('UNCHECKED', 'VERIFIED', 'INVALID', 'NEEDS CLARIFICATION', 'UNSUPPORTED', 'INDETERMINATE')
        require(0 <= outcome < len(labels), 'unknown outcome')
        disk = self.directory / 'cold-input.raw'
        shutil.copyfile(self.args.disk, disk)
        live = self.session('cold', disk)
        zero = live.inspect()['machine']
        require(zero['cycle'] == zero['ticks'] == 0, 'actual CPU0 required')
        self.report.update(identity=live.identity, source_sequence=sequence, original_workspace=workspace)
        self.phase(live, 'newCPU-cold-Ready', 1_000_000_000,
                   lambda state: self.idle(state) and state['panel_completed'] >= 1 and any(row[0] == 1056 for row in self.rows(live)))
        panel, medium = live.export('cold-ready')
        require(filecmp.cmp(self.args.disk, medium, shallow=False), 'cold changed a backing byte')
        require(visible_pixels(panel) == visible_pixels(self.args.expected_home), 'complete cold home pixels differ')
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        _, tick = self.raw(live, stream, 320, 140)
        old = live.inspect()['machine']['panel_completed']
        observed = self.directory / 'observed.ppm'
        def opened(state):
            if not self.idle(state) or state['panel_completed'] <= old or state['ticks'] < tick + 200000:
                return False
            live.control({'action': 'panel', 'path': str(observed)})
            return (course_body_matches(observed, body) and pad_matches(observed, False) and
                    label_matches(observed, labels[outcome], 24, 260))
        self.phase(live, 'raw-COURSE-history-location', 400_000_000, opened)
        _, medium = live.export('reopened')
        payload, after, _, final_sequence = self.record(medium)
        require(payload == original and after == workspace and final_sequence == sequence and
                filecmp.cmp(self.args.disk, medium, shallow=False), 'reader changed applicability/evidence/history/learner/media')
        require(not any(row[0] in (0x41f, 0x421, 0x423, 0x424, 1113, 1109) for row in self.rows(live)),
                'readonly opening formatted/saved/checked')
        require(sha(self.args.disk) == self.original_medium_sha256, 'original opaque input changed')
        self.report.update(status='PASS_REAL_GUEST_HISTORY_BROWSE_COLD', historical_source=source,
                           current_applicability='Unknown unchanged', revision=workspace['document']['revision'],
                           store_sequence=sequence, all_home_pixels=3_630_000, all_medium_bytes=268_435_456,
                           independent_course_body_pixels=122_880, independent_keypad_pixels=76_800,
                           no_new_check_or_save=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('disk', 'expected-home', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--package', type=Path, action='append', required=True)
    parser.add_argument('--native-bundle', required=True)
    parser.add_argument('--guest-build')
    parser.add_argument('--guest-source-root', type=Path)
    parser.add_argument('--backend', choices=('qemu', 'rtl'), default='qemu')
    args = parser.parse_args()
    if bool(args.guest_build) != bool(args.guest_source_root):
        parser.error('--guest-build and --guest-source-root must be supplied together')
    args.disk = args.disk.resolve()
    args.package = [path.resolve() for path in args.package]
    args.timeout, args.deadline = 120, 10800 if args.backend == 'rtl' else 900
    args.checkpoint_relation, args.durable_suffix_from = 'independent cold only', None
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = BrowseRecovery(args)
    try:
        actor.execute()
    except BaseException as error:
        actor.report.update(status='FAIL', error=repr(error))
        raise
    finally:
        actor.close()
    print(actor.report['status'], actor.cycles, actor.report['elapsed_seconds'])


if __name__ == '__main__':
    main()
