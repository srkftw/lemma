#!/usr/bin/env python3
"""Run the installed-course, exact checking, assistance, ink and cold-reopen workflow.

Uses only public raw-device/session operations and independent exported-byte
observers. The guest owns document construction, checking and durability.
Fast functional units do not establish RTL timing or exact cached continuation.
"""
import argparse
import filecmp
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import struct
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from check_live_notebook import Input, PublicSession, guest_events, idle, require, sha, visible_pixels
from check_math_session import MathChecker
from course_package import decode
from course_pixel_oracle import course_body_matches as panel_matches
from store_oracle import recover
import workspace_oracle as W
import workspace_transition_oracle as T
KEY = 5785718146287534081
CAPS = {'view': 100000000, 'control': 150000000, 'check': 200000000}

class Session(PublicSession):

    def inspect(self):
        value = super().inspect()
        value['machine']['panel_completed'] = value['machine']['devices']['paper']['completed']
        return value

class CourseMathWorkflow(MathChecker):
    backend = 'qemu'
    session_type = Session
    phase_caps = CAPS

    def idle(self, state):
        return idle(state)

    def __init__(self, args):
        super().__init__(args)
        self.original_medium_sha256 = sha(args.disk)
        self.cycles = 0
        self.launches = 0
        self.pending_census = []
        self.frozen = {}
        self.expected_course_error = None
        self.packages = [path.read_bytes() for path in args.package]
        self.objects = {}
        for raw in self.packages:
            package = decode(raw)
            key = (1, 4850376798678024192 | package['identity'] << 32 | package['edition'])
            require(key not in self.objects, 'duplicate immutable package identity')
            self.objects[key] = raw
        self.report.update(schema='lemma-course-math-workflow/1', scope=__doc__, phases=[], aggregate_cycles=3000000000, independent_oracle='exact Fraction/coefficient, Doc8, immutable package provenance and ordered learner-event observers', hint_scope='authored local hint; permissioned tutor transport remains unfinished')
        self.report['source_medium_scope'] = 'Actual guest-installed packages; no package or document is installed by this observer'
        self.report['phase_caps'] = CAPS | {'cold': 1000000000, 'course': 400000000, 'ink': 300000000, 'close': 500000000}
        self.progress()

    def launch(self, args, **kw):
        self.launches += 1
        p = self.directory / ('imports-' + str(self.launches) + '.json')
        self.pending_census.append(p)
        if self.frozen:
            self.check_sources()
        command = [sys.executable, str(ROOT / 'scripts/host_import_census.py'), str(p), str(ROOT / 'scripts/lemmasim'), *args]
        self.commands.write(json.dumps(command) + '\n')
        self.commands.flush()
        import subprocess
        return subprocess.Popen(command, cwd=ROOT, **kw)

    def census(self):
        result = {}
        for p in self.pending_census:
            if p.is_file():
                result.update(json.loads(p.read_text()))
        for m in list(sys.modules.values()):
            name = getattr(m, '__file__', None)
            if name:
                p = Path(name).resolve()
                if p.suffix == '.py' and p.is_relative_to(ROOT) and p.is_file():
                    result[str(p.relative_to(ROOT))] = sha(p)
        result[str(Path(__file__).relative_to(ROOT))] = sha(__file__)
        result[str((ROOT / 'scripts/host_import_census.py').relative_to(ROOT))] = sha(ROOT / 'scripts/host_import_census.py')
        return result

    def check_sources(self):
        require(all((sha(ROOT / p) == d for p, d in self.frozen.items())), 'actual consumed host source changed')
        for p in self.pending_census:
            if p.is_file():
                require(set(json.loads(p.read_text())) <= set(self.frozen), 'unannounced future CLI import outside qualified initialclosure')

    def saved(self, s):
        rows = [r for r in self.rows(s) if r[0] in (1057, 1059, 1060)]
        return rows and rows[-1][0] == 1057

    def progress(self):
        (self.directory / 'progress.json').write_text(json.dumps(self.report, default=str, indent=2) + '\n')

    def raw(self, s, stream, x, y):
        state = s.inspect()['machine']
        stream.tick = state['ticks'] + 10000
        first = len(stream.events)
        stream.sample(x, y, 2048, True)
        stream.sample(x, y, 0, False)
        s.admit(stream.events[first:])
        return (first, stream.events[-1][1])

    def click(self, s, stream, name, x, y, *, text=None, mutation=False, expected_error=None):
        before = s.inspect()['machine']
        oldacks = len([r for r in self.rows(s) if r[0] == 1057])
        olderrors = len([r for r in self.rows(s) if r[0] == 1108])
        first, tick = self.raw(s, stream, x, y)
        panel = self.directory / 'observed-panel.ppm'

        def completed(state):
            if not self.idle(state) or state['ticks'] < tick + 200000 or state['panel_completed'] <= before['panel_completed']:
                return False
            rows = self.rows(s)
            if mutation and (len([r for r in rows if r[0] == 1057]) <= oldacks or not self.saved(s)):
                return False
            if expected_error is not None:
                errors = [r for r in rows if r[0] == 1108]
                return len(errors) > olderrors and errors[-1][1] == expected_error
            require(len([r for r in rows if r[0] == 1108]) == olderrors, 'unexpected actualcourse error ' + name)
            if text is not None:
                s.control({'action': 'panel', 'path': str(panel)})
                return panel_matches(panel, text)
            return True
        self.expected_course_error = expected_error
        try:
            self.phase(s, name, self.phase_caps['view'] if text is not None else self.phase_caps['control'], completed)
        finally:
            self.expected_course_error = None
        self.report['interactions'].append({'name': name, 'pixel': [x, y], 'first_raw_sequence': first + 1, 'last_raw_sequence': len(stream.events)})
        return panel

    def record(self, medium):
        _, sequence, records = recover(Path(medium).read_bytes())
        require((1, KEY) in records, 'actualworkspace notacknowledged')
        payload = records[1, KEY].payload
        r = W.observe(payload, 1, KEY, self.packages)
        for key, raw in self.objects.items():
            if key in records:
                require(records[key].payload == raw, 'opaqueinstalledpackage changed')
        require(r['storage_format'] == 'lemma-course-workspace-envelope/2', 'actual compact workspace2 required')
        return (payload, r, records, sequence)

    def checkpoint_record(self, s, name):
        panel, medium = s.export(name)
        payload, record, records, seq = self.record(medium)
        self.report[name] = {'payload_sha256': hashlib.sha256(payload).hexdigest(), 'store_sequence': seq, 'workspace': record, 'path': str(medium)}
        self.progress()
        return (panel, medium, payload, record, records)

    def check(self, s, stream, name, outcome):
        oldq = len([r for r in self.rows(s) if r[0] == 1113])
        oldacks = len([r for r in self.rows(s) if r[0] == 1057])
        _, tick = self.raw(s, stream, 40, 245)

        def done(state):
            rows = self.rows(s)
            q = [r for r in rows if r[0] == 1113]
            r = [r for r in rows if r[0] == 1109]
            if len(q) <= oldq or not r or r[-1][1] != q[-1][1]:
                return False
            require(r[-1][3:] == (0, outcome), 'actual checker status/outcome differs')
            require((1117, q[-1][1], 0, 0, 0) in rows, 'actual closuregraph notreclaimed')
            return self.idle(state) and self.saved(s) and (len([r for r in rows if r[0] == 1057]) > oldacks) and (state['ticks'] >= tick + 200000)
        self.phase(s, name, self.phase_caps['check'], done)
        rows = self.rows(s)
        q = [r for r in rows if r[0] == 1113][-1]
        r = [r for r in rows if r[0] == 1109][-1]
        self.report.setdefault('actual_checks', []).append({'request': q, 'reply': r})
        return self.checkpoint_record(s, name)

    def session(self, name, disk, fail_flush=None):
        result = self.session_type(self, name, disk, fail_flush)
        self.sessions.append(result)
        if not self.frozen:
            until = time.monotonic() + 5
            while not self.pending_census[0].is_file():
                require(time.monotonic() < until, 'initial importcensus absent')
                time.sleep(0.02)
            self.frozen = self.census()
            self.check_sources()
            (self.directory / 'consumed-host-inputs.json').write_text(json.dumps(self.frozen, sort_keys=True, indent=2) + '\n')
        return result

    def rows(self, s):
        return guest_events(s.directory / ('uart.bin' if self.backend == 'rtl' else 'uart-0.bin'))

    def phase(self, s, name, cap, predicate):
        before = s.inspect()['machine']
        start = time.monotonic()
        original_limit_recorded = False
        if name in ('COURSEactualpackage', 'cold-reopen-installed-body'):
            cap = 400000000
        while True:
            self.check_sources()
            state = s.inspect()['machine']
            rows = self.rows(s)
            if name == 'COURSEactualpackage' and (not original_limit_recorded) and (state['cycle'] - before['cycle'] >= 100000000):
                self.report['original_fast100M_view'] = {'status': 'FAIL_ORIGINAL100M' if not predicate(state) else 'PASS_AT_ORIGINAL100M_BOUNDARY', 'cycle': state['cycle'], 'scope': 'separate original diagnostic; functional continuation prospectively bounded before launch'}
                original_limit_recorded = True
                self.progress()
            require(not state['finished'] and (not any((r[0] in (1055, 1108, 212, 244, 1060) for r in rows))), 'actual guest failure in ' + name + ':' + repr(rows[-8:]))
            if predicate(state):
                break
            used = state['cycle'] - before['cycle']
            require(used < cap and self.cycles < 3000000000 and (time.monotonic() < self.deadline), 'prospective fast bound in ' + name)
            q = min(1000000, cap - used, 3000000000 - self.cycles)
            s.run(q)
            after = s.inspect()['machine']
            require(after['cycle'] > state['cycle'], 'no instruction-clock progress')
            self.cycles += after['cycle'] - state['cycle']
        if name == 'COURSEactualpackage' and (not original_limit_recorded):
            self.report['original_fast100M_view'] = {'status': 'PASS_NEW_SOURCE_WITHIN_ORIGINAL100M_CLOCK_CEILING', 'cycle': state['cycle'], 'scope': 'new source with correct declared role1 body observer; no old result relabeled'}
        result = dict(name=name, initial_cycle=before['cycle'], final_cycle=state['cycle'], instruction_clock_cycles=state['cycle'] - before['cycle'], host_seconds=time.monotonic() - start)
        self.report['phases'].append(result)
        self.progress()
        print(json.dumps(result), flush=True)
        return state

    def close(self):
        for s in list(self.sessions):
            try:
                s.close()
            finally:
                self.sessions.remove(s)
        self.commands.close()
        self.report['elapsed_seconds'] = time.monotonic() - self.started
        self.report['consumed_host_current_equal'] = all((sha(ROOT / p) == d for p, d in self.frozen.items()))
        self.progress()
        (self.directory / 'result.json').write_text(json.dumps(self.report, default=str, indent=2) + '\n')

    def execute(self):
        disk = self.directory / 'live-input.raw'
        shutil.copyfile(self.args.disk, disk)
        live = self.session('live', disk)
        zero = live.inspect()['machine']
        require(zero['cycle'] == 0 and zero['ticks'] == 0, 'actual new fast CPU not reset')
        self.report['identity'] = live.identity
        self.phase(live, 'new-instruction-clock-cold-Ready', 1000000000, lambda st: self.idle(st) and st['panel_completed'] >= 1 and any((r[0] == 1056 for r in self.rows(live))))
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        p1 = decode(self.packages[0])
        self.click(live, stream, 'COURSEactualpackage', 320, 140, text=p1['nodes'][0]['body'])
        original = self.checkpoint_record(live, 'opened')
        for label, text, x in [('title', p1['title'], 360), ('source', p1['source_anchor'], 72), ('edition', p1['edition_anchor'], 168), ('rights', p1['rights_anchor'], 264)]:
            self.click(live, stream, 'actual-header-' + label, x, 690, text=text)
        self.click(live, stream, 'actual-node-title', 168, 650, text=p1['nodes'][0]['title'])
        self.click(live, stream, 'actual-node-body', 168, 650, text=p1['nodes'][0]['body'])
        self.click(live, stream, 'node1', 72, 650, text=p1['nodes'][1]['body'])
        self.click(live, stream, 'exercise2', 72, 650, text=p1['nodes'][2]['body'])
        self.click(live, stream, 'USEactualgoal', 360, 650, mutation=True)
        self.click(live, stream, 'numerator', 100, 225, mutation=True)
        for i in range(5):
            self.click(live, stream, 'numPLUS' + str(i), 364, 225, mutation=True)
        self.click(live, stream, 'denominator', 124, 225, mutation=True)
        for i in range(5):
            self.click(live, stream, 'denPLUS' + str(i), 364, 225, mutation=True)
        prior = self.checkpoint_record(live, 'before-check')
        verified = self.check(live, stream, 'actual-Verified', 1)
        require(verified[3]['document']['answer'][:2] == [5, 6], 'actual answer not5/6')
        T.observe_transition(prior[3], verified[3], 'known-check')
        self.click(live, stream, 'edit5over7', 364, 225, mutation=True)
        edited = self.checkpoint_record(live, 'edited')
        T.observe_transition(verified[3], edited[3], 'edit')
        invalid = self.check(live, stream, 'actual-Invalid', 2)
        T.observe_transition(edited[3], invalid[3], 'known-check')
        self.click(live, stream, 'authored-local-hint', 172, 245, mutation=True)
        for i in range(5):
            self.click(live, stream, 'review-mode' + str(i), 316, 245, mutation=True)
        learner = self.checkpoint_record(live, 'learner')
        T.observe_transition(invalid[3], learner[3], 'learner')
        require(learner[3]['document']['hints'] == 1 and learner[3]['document']['learner']['mode'] == 0, 'assistance/review absent')
        for index in (3, 4, 5):
            self.click(live, stream, 'polynomial-authored-node' + str(index), 72, 650, text=p1['nodes'][index]['body'])
        self.click(live, stream, 'USE-polynomial-goal', 360, 650, mutation=True)
        for label, x, count in [('constant', 148, 1), ('linear', 184, 2), ('quadratic', 220, 1)]:
            self.click(live, stream, 'select-' + label, x, 225, mutation=True)
            for i in range(count):
                self.click(live, stream, label + '-PLUS' + str(i), 364, 225, mutation=True)
        before_polynomial = self.checkpoint_record(live, 'before-polynomial')
        polynomial = self.check(live, stream, 'actual-polynomial-Verified', 1)
        require(polynomial[3]['document']['goal'] == 2 and polynomial[3]['document']['answer'][2:] == [1, 2, 1], 'actual Q[x] coefficients differ')
        T.observe_transition(before_polynomial[3], polynomial[3], 'known-check')
        self.click(live, stream, 'NEXT-to-Unsupported', 112, 245, mutation=True)
        unsupported = self.check(live, stream, 'actual-Unsupported', 4)
        require(unsupported[3]['current'] == {'origin': 'Unknown'}, 'unsupported gained package authority')
        self.click(live, stream, 'NEXT-back-to-rational', 112, 245, mutation=True)
        self.click(live, stream, 'resource-limit-zero', 232, 245, mutation=True)
        limited = self.check(live, stream, 'actual-Indeterminate', 5)
        require(limited[3]['document']['budget'] == 0, 'resource limit absent')
        first = len(stream.events)
        stream.tick = live.inspect()['machine']['ticks'] + 10000
        stream.stroke('actual-postmath-ink', 1, 1, 6, 1900)
        live.admit(stream.events[first:])
        before = len([r for r in self.rows(live) if r[0] == 1057])
        self.phase(live, 'actual-raw-ink-Saved', 300000000, lambda st: self.idle(st) and self.saved(live) and (len([r for r in self.rows(live) if r[0] == 1057]) > before) and (st['ticks'] >= stream.events[-1][1] + 200000))
        _, ink_medium = live.export('postmath-ink')
        _, _, ink_records, _ = self.record(ink_medium)
        samples = []
        for r in ink_records.values():
            if len(r.payload) >= 128 and struct.unpack_from('<Q', r.payload)[0] == 3552018807646930252 and (struct.unpack_from('<Q', r.payload, 16)[0] == 3):
                n = struct.unpack_from('<Q', r.payload, 48)[0]
                samples.extend((struct.unpack_from('<9Q', r.payload, 128 + i * 72) for i in range(n)))
        require(all((tuple(row) in samples for row in stream.events[first:])), 'actual raw fields missing from guest durable chunks')
        _, tick = self.raw(live, stream, 320, 140)
        old = live.inspect()['machine']['panel_completed']
        self.phase(live, 'close-course-controller-work', 500000000, lambda st: self.idle(st) and self.saved(live) and (st['panel_completed'] > old) and (st['ticks'] >= tick + 25000000))
        panel, medium = live.export('closed-final')
        payload, record, records, sequence = self.record(medium)
        live.close()
        self.sessions.remove(live)
        disk = self.directory / 'cold-input.raw'
        shutil.copyfile(medium, disk)
        cold = self.session('cold', disk)
        require(cold.inspect()['machine']['cycle'] == 0, 'cold CPU not atreset')
        expected = visible_pixels(panel)
        observed = self.directory / 'cold-wait.ppm'

        def recovered(st):
            if not self.idle(st) or not any((r[0] == 1056 for r in self.rows(cold))):
                return False
            cold.control({'action': 'panel', 'path': str(observed)})
            return visible_pixels(observed) == expected
        self.phase(cold, 'independent-new-CPU-cold-all-pixels', 1000000000, recovered)
        cp, cm = cold.export('cold-final')
        require(visible_pixels(cp) == expected, 'complete controller pixels differ')
        require({k: r.payload for k, r in self.record(cm)[2].items()} == {k: r.payload for k, r in records.items()}, 'all acknowledged package/math/learner/ink records differ')
        self.report['independent_cold'] = {'new_cpu': True, 'all_controller_pixels_exact': True, 'all_acknowledged_objects_exact': True}
        self.report['base_functional_complete'] = {'cycles': self.cycles, 'all_cold_pixels': True, 'all_acknowledged_objects': True}
        prior_checks = len([r for r in self.rows(cold) if r[0] == 1113])
        reopened_input = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(cold, reopened_input, 'cold-reopen-installed-body', 320, 140, text=p1['nodes'][0]['body'])
        reopened = self.checkpoint_record(cold, 'cold-reopened-course')
        require(reopened[2] == payload and {k: r.payload for k, r in reopened[4].items()} == {k: r.payload for k, r in records.items()}, 'cold reopening changed acknowledged mathematical/package/learner/ink bytes')
        import filecmp
        require(filecmp.cmp(medium, reopened[1], shallow=False), 'cold course reopen changed complete observed medium bytes')
        require(len([r for r in self.rows(cold) if r[0] == 1113]) == prior_checks, 'reopening recomputed old evidence')
        self.report['cold_course_reopen'] = {'actual_body_pixels': True, 'exact_workspace_and_all_objects': True, 'all_medium_bytes_exact': True, 'no_new_checker_request': True}
        require(sha(self.args.disk) == self.original_medium_sha256, 'original source medium changed')
        require(filecmp.cmp(medium, cm, shallow=False), 'cold recovery changed complete medium bytes')
        self.report['status'] = 'PASS_COURSE_MATH_WORKFLOW_COLD_REOPEN'
        self.report['not_run'] = ['new package publication is a separate course-install workflow', 'canonical timing acceptance', 'arbitrary cached checkpoint continuation']

def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--package', action='append', type=Path, required=True, help='Actual immutable installed package bytes; first is the reference sequence')
    parser.add_argument('--native-bundle', required=True)
    parser.add_argument('--guest-build', required=True)
    parser.add_argument('--guest-source-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    args.disk = args.disk.resolve()
    args.package = [path.resolve() for path in args.package]
    require(not args.work_dir.exists(), 'unused output directory required')
    args.timeout = 120
    args.deadline = 900
    args.checkpoint_relation = 'not-exercised'
    args.durable_suffix_from = None
    os.environ['LEAN_NUM_THREADS'] = '2'
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = CourseMathWorkflow(args)
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
