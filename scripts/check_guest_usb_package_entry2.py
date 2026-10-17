#!/usr/bin/env python3
"""Cold-open acknowledged recovery16 mathematics, then bounded course close.

Uses the existing native machine, USB host and independent hosted-Lean peer.
Raw input alone changes the guest. Offline document/pixel oracles never supply
recovery or display state to it. This is a changed-source usability case, not
completion of the retained lost-ACK campaign or a speedup measurement.
"""
from pathlib import Path
import argparse
import json
import os
import signal
import struct
import subprocess
import sys
import time
import check_guest_usb_notebook as base
from silicon_guest_bundle import prepared

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from inspect_notebook import inspect_page
from workspace_oracle import observe as observe_workspace
from course_package import decode as decode_package
from course_pixel_oracle import course_body_matches, label_matches
from number_pad_reference import pad_matches

PROFILE = 'lemma-silicon-dev/0.13.0'
ROLE = 'usb-clocked-package-entry2-bulk-notebook'
WORKSPACE = (1, 0x504b000000000001)
PACKAGE = (1, 0x4350000100000001)
BASE_SHA = '5e3d138686d1e0704f3100dd26c978af622c7e813e1fbcccfb18762eb28fa869'


class Live(base.NativeUSBSession):
    def __init__(self, checker):
        self.checker, self.name = checker, 'cold'
        self.directory = checker.out / self.name
        self.log = (checker.out / 'cold.log').open('xb')
        self.view_generation = self.view = None
        args = checker.args
        cmd = [sys.executable, str(ROOT / 'scripts/lemmasim'), 'session', '--backend', 'rtl',
            '--profile', PROFILE, '--workload', ROLE, '--native-bundle', str(args.native_bundle.resolve()),
            '--session-dir', str(self.directory), '--mode', 'laboratory', '--headless', '--paused',
            '--timeout', '120', '--quantum', '1000', '--trace-limit', '0', '--usb-recovery',
            '--usb-host-prepared', str(args.host_prepared.resolve()), '--usb-peer-directory', str(checker.peer),
            '--usb-peer-socket', str(checker.socket), '--usb-host-state', str(checker.outbox)]
        self.argv = cmd
        self.process = subprocess.Popen(cmd, cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        checker.sessions.append(self)
        end = time.monotonic() + 60
        while not (self.directory / 'session.json').exists():
            base.require(self.process.poll() is None and time.monotonic() < end, 'exact Entry2 session startup')
            time.sleep(.02)
        initial = self.control({'action': 'inspect'})
        base.require(initial['running'] is False and initial['machine']['cycle'] == 0 and
            not initial['machine']['usb']['configured'] and
            initial['identity'].get('usb_recovery_contract') == 'lemma-usb-live-recovery/1' and
            initial['identity']['runtime']==checker.native_data['binary']['sha256'] and
            (self.directory/'usb.raw').read_text().splitlines()[0]=='LMUSBRW3 '+checker.native_snapshot_identity,
            'new CPU must begin cold, unconfigured, with real recovery control')
        self.identity, self.start = initial['identity'], initial['machine']

    def control(self, value):
        self.checker.guard()
        if value.get('action') == 'run':
            self.checker.cycles += value['cycles']
            base.require(self.checker.cycles <= 1600000000, 'prospective1.6B aggregate clock bound')
        return super().control(value)

    def wait(self, label, predicate, cycles, seconds, quantum=5000000, **kwargs):
        initial = self.machine()['cycle']; started = time.monotonic()
        def bounded(state, rows):
            base.require(state['cycle'] - initial <= cycles and time.monotonic() - started <= seconds,
                         'original phase bound before accepting completion: ' + label)
            self.checker.guard()
            return predicate(state, rows)
        return super().wait(label, bounded, cycles, seconds, quantum=quantum, **kwargs)


class Checker(base.Checker):
    def __init__(self, args):
        base.require(base.sha(base.__file__) == BASE_SHA, 'original shared lifecycle/oracles changed')
        data=prepared(args.native_bundle, 'rtl', ROLE, PROFILE)
        plan=json.loads(args.plan.read_text())
        native=json.loads(Path(data['rtl_build']['path']).read_text())
        base.require(base.sha(args.native_bundle/'bundle.json')==plan['native_bundle_sha256'] and
            native['snapshot_identity']==plan['native_snapshot_identity'] and
            data['binary']['sha256']==plan['native_binary_sha256'] and
            data['workloads'][ROLE]['image']['sha256']==plan['notebook_image_sha256'],
            'prospective exact current native/guest artifact identities differ')
        self.native_data=data;self.native_snapshot_identity=native['snapshot_identity']
        super().__init__(args)
        self.cycles = 0
        self.source_files = {str(path): base.sha(path) for path in (
            args.source / 'cold-peer/base.img', args.source / 'cold-peer/opaque.log',
            args.source / 'cold-peer/peer.json', args.source / 'cold-outbox/outbox',
            args.source / 'math-assisted.raw')}
        self.report.update(schema='lemma-clocked-package-entry2-close/1', status='RUNNING', scope=__doc__,
            original_sources=self.source_files, plan_sha256=base.sha(args.plan),
            entry2_observer_sha256=base.sha(__file__),
            bounds={'whole_seconds':14400, 'aggregate_cycles':1600000000, 'cold_cycles':1000000000,
                'cold_seconds':7200, 'open_cycles':400000000, 'open_seconds':3600,
                'close_cycles':200000000, 'close_seconds':3600},
            not_qualified=['original lost-ACK campaign completion or comparable speedup',
                'new math check, new Save, second cold, full course pixel-plane comparison',
                'Product ROM, browser peer, full USB/radio conformance, fast timing or arbitrary cached checkpoints'])

    def guard(self):
        base.require(time.monotonic() - self.started <= 14400, 'prospective whole host bound')

    def sample_resources(self):
        super().sample_resources()
        own = int(next(row.split()[1] for row in Path('/proc/self/status').read_text().splitlines() if row.startswith('VmRSS:')))
        own += sum(item.get('last_sample', {}).get('sampled_resident_kib', 0) for item in self.report.get('host_resources', {}).values())
        sizes = [p.stat().st_size for p in self.out.rglob('*') if p.is_file() and not p.is_symlink()]
        base.require(own <= 4 * 1024 * 1024 and sum(sizes) <= 12 << 30 and max(sizes, default=0) <= 1 << 30,
                     'declared owned RSS/output/file bound')
        self.report['sampled_owned_peak_rss_kib'] = max(self.report.get('sampled_owned_peak_rss_kib', 0), own)
        self.guard()

    def materialize(self, label):
        path = self.out / (label + '.raw')
        base.materialize_observation(self.peer, path)
        return path

    def tap(self, live, stream, x, y):
        stream.tick = live.machine()['ticks'] + 10000; first = len(stream.events)
        stream.sample(x, y, 2048, True); stream.sample(x, y, 0, False)
        live.admit(stream.events[first:])

    def execute(self):
        plan = json.loads(self.args.plan.read_text())
        base.require(plan['status'] == 'PREDECLARED_NOT_RUN' and plan['source_files'] == self.source_files,
                     'prospective exact source boundary differs')
        base.copy_opaque_peer(self.args.source / 'cold-peer', self.peer, self.args.source / 'cold-outbox', self.outbox)
        before = self.materialize('before')
        base.require(base.sha(before) == self.source_files[str(self.args.source / 'math-assisted.raw')],
                     'copied opaque peer differs from actually acknowledged Saved23 medium')
        _, sequence, records = base.recover(before.read_bytes())
        package_raw = records[PACKAGE].payload; package = decode_package(package_raw)
        workspace = observe_workspace(records[WORKSPACE].payload, 1, WORKSPACE[1], [package_raw])
        document = workspace['document']
        base.require(sequence == 23 and document['answer'] == [5,6,0,0,0] and document['outcome'] == 1 and
            document['hints'] > 0 and document['evidence_revision'] == document['revision'] and
            workspace['current']['node'] == 3 and document['learner']['understanding'] == 'uncertain',
            'source must be actual acknowledged original fraction/evidence/assistance')
        expected = bytearray(base.empty_pixels(1650, 2200))
        for obj, _, visible in inspect_page(records[(1,257)].payload, 257):
            if not visible: continue
            payload = records[(1,obj)].payload
            base.require(len(payload) == 344 and struct.unpack_from('<3Q', payload) == (0x314b4e49414d454c,1,3),
                         'independent stroke oracle scope differs')
            samples = [struct.unpack_from('<9Q', payload, 128 + 72*i) for i in range(3)]
            for x,y in base.expected_stroke(samples)[1]: expected[(y*1650+x)*3:(y*1650+x)*3+3] = bytes(3)
        expected = bytes(expected); peer_before = base.sha(self.peer / 'opaque.log')
        self.start_peer(); live = Live(self); self.report['argv'] = live.argv; self.report['identity'] = live.identity
        self.update(); state = live.boot(expected)
        base.require(state['usb']['configured'], 'guest cold path did not enumerate/configure actual USB')
        live.control({'action':'panel', 'path':str(self.out/'cold-home.ppm')})
        stream = base.Input(1650,2200,state['ticks']+10000,100000,0)
        previous = state['panel_completed']; self.tap(live, stream,320,140)
        path = self.out / 'course.ppm'
        def opened(state, rows):
            if not (state['paper_busy'] == state['pen_queue'] == state['event_queue'] == state['panel_pending_pixels'] == 0 and state['panel_completed'] > previous): return False
            live.control({'action':'panel','path':str(path)})
            return course_body_matches(path, package['nodes'][2]['body']) and pad_matches(path,False) and label_matches(path,'VERIFIED',24,260)
        state = live.wait('cold-open-acknowledged-course-evidence', opened,400000000,3600)
        previous = state['panel_completed']; self.tap(live, stream,320,140)
        live.wait('close-all-original-home-pixels',lambda state,rows: state['panel_completed'] > previous and live.panel_matches(state,expected),200000000,3600)
        live.control({'action':'panel','path':str(self.out/'closed-home.ppm')})
        after = self.materialize('after')
        base.require(base.sha(after) == base.sha(before) and base.sha(self.peer/'opaque.log') == peer_before,
                     'read-only cold/open/close changed any medium byte or durable peer effect')
        base.require(not any(row[0] in (0x421,0x41f,1113) for row in live.records()), 'read-only case saved/formatted/rechecked')
        base.require(all(base.sha(path) == sha for path,sha in self.source_files.items()), 'original source changed')
        base.require(live.machine()['cycle'] == self.cycles, 'actual completed clock total differs')
        self.report.update(status='PASS_COLD_ACKNOWLEDGED_MATH_COURSE_CLOSE_200M',
            actual_cycles=self.cycles, source_sequence=sequence, source_workspace=workspace,
            all_home_pixels=True, all_medium_bytes_unchanged=True, raw_events=stream.events,
            course_pixel_scope='independent body/keypad/Verified regions only')
        self.update()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native-bundle','host-prepared','source','plan','work-dir'): parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args(); args.source=args.source.resolve(); args.profile=PROFILE
    args.rtl_source_root=args.guest_source_root=None
    args.cold_cycles=1000000000;args.cold_deadline=7200;args.ink_cycles=0
    args.action_cycles=400000000;args.action_deadline=3600
    def cancel(signum,frame): raise KeyboardInterrupt('owned supervisor cancellation')
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    checker=Checker(args)
    try: checker.execute()
    except BaseException as error:
        checker.report.update(status='FAIL',error=repr(error))
        for live in checker.sessions:
            try:
                checker.report['failed_boundary'] = live.control({'action':'inspect'})
                snapshot = checker.out / 'failed.snapshot'
                live.control({'action':'snapshot','path':str(snapshot)})
                checker.report['failed_snapshot_sha256'] = base.sha(snapshot/'machine.chk')
            except BaseException as capture_error:
                checker.report['failure_export_error'] = repr(capture_error)
    finally: checker.close()
    return 0 if checker.report['status'].startswith('PASS_') else 1

if __name__=='__main__': raise SystemExit(main())
