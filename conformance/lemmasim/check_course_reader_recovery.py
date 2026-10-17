#!/usr/bin/env python3
"""Actual guest node Save and independent cold reopen with authority unchanged.

Only raw input and public session operations reach the machine. Opaque source
media is privately copied; this observer never supplies document/reader bytes.
"""
import argparse
import filecmp
import hashlib
import json
import resource
import shutil
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'conformance/lemmasim')]
from check_course_browse_recovery import BrowseRecovery
from check_course_math_workflow import Input, decode, require, sha, visible_pixels
from course_pixel_oracle import course_body_matches, label_matches
from number_pad_reference import pad_matches

READER_OBJECT = 0x5244000000000001


class ReaderRecovery(BrowseRecovery):
    def __init__(self, args):
        super().__init__(args)
        self.report.update(schema='lemma-course-reader-connected/1', scope=__doc__,
            aggregate_cycles=2_800_000_000,
            scope_limit='Node-only bookmark; independent cold, not cached-state continuation or new mathematical authority.')

    def phase(self, session, name, cap, predicate):
        before = session.inspect()['machine']['cycle']
        began = time.monotonic()
        host_cap = 7200 if 'cold-Ready' in name else 3600
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            used, elapsed = state['cycle'] - before, time.monotonic() - began
            require(0 <= used <= cap and self.cycles <= 2_800_000_000 and
                    elapsed <= host_cap and time.monotonic() < self.deadline,
                    'prospective phase/aggregate bound before accepting ' + name)
            require(not state['finished'] and not any(row[0] in (1055, 1060, 1108, 212, 244)
                    for row in self.rows(session)), 'actual guest failure in ' + name)
            if predicate(state):
                break
            require(used < cap and self.cycles < 2_800_000_000, 'clock ceiling in ' + name)
            quantum = min(1_000_000, cap - used, 2_800_000_000 - self.cycles)
            session.run(quantum)
            delta = session.inspect()['machine']['cycle'] - state['cycle']
            require(delta == quantum if self.backend == 'rtl' else delta > 0,
                    'machine did not advance admitted clocks')
            self.cycles += delta
        result = dict(name=name, initial_cycle=before, final_cycle=state['cycle'],
                      clocks=used, host_seconds=elapsed, clock_cap=cap, host_cap=host_cap)
        self.report['phases'].append(result)
        self.progress()
        print(json.dumps(result), flush=True)
        return state

    def cold(self, name, source):
        disk = self.directory / (name + '-input.raw')
        shutil.copyfile(source, disk)
        session = self.session(name, disk)
        zero = session.inspect()['machine']
        require(zero['cycle'] == zero['ticks'] == 0 and not zero.get('isolated_medium', False),
                'independent CPU0 required, not checkpoint restore')
        self.phase(session, name + '-cold-Ready', 1_000_000_000,
            lambda state: self.idle(state) and state['panel_completed'] >= 1 and
            any(row[0] == 1056 for row in self.rows(session)))
        panel, medium = session.export(name + '-ready')
        require(filecmp.cmp(source, medium, shallow=False), 'cold changed backing bytes')
        require(visible_pixels(panel) == visible_pixels(self.args.expected_home),
                'complete independent cold home differs')
        return session

    def view(self, session, stream, name, x, y, body, *, course=False):
        old = session.inspect()['machine']['panel_completed']
        _, tick = self.raw(session, stream, x, y)
        panel = self.directory / (name + '.ppm')
        def complete(state):
            if (not self.idle(state) or state['panel_completed'] <= old or
                    state['ticks'] < tick + 200000):
                return False
            session.control({'action': 'panel', 'path': str(panel)})
            return (course_body_matches(panel, body) and pad_matches(panel, False) and
                    label_matches(panel, 'INDETERMINATE', 24, 260))
        self.phase(session, name, 400_000_000 if course else 150_000_000, complete)

    def execute(self):
        payload, workspace, old_records, sequence = self.record(self.args.disk)
        require(workspace['current']['origin'] == 'Unknown' and sequence == 37 and
                workspace['document']['outcome'] == 5,
                'this bounded fixture requires actual acknowledged Unknown37 input')
        known = [binding for binding in workspace['history'] if binding['origin'] == 'InstalledPackage']
        require(known and known[-1]['node'] == 3 and (1, READER_OBJECT) not in old_records,
                'actual history3 without a preinstalled bookmark required')
        package = decode(self.packages[0])
        require(len(package['nodes']) == 8 and package['nodes'][4]['kind'] == 2,
                'independent eight-node package/example5 required')
        live = self.cold('first', self.args.disk)
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.view(live, stream, 'history3', 320, 140, package['nodes'][2]['body'], course=True)
        self.view(live, stream, 'browse4', 72, 650, package['nodes'][3]['body'])
        self.view(live, stream, 'browse-example5', 72, 650, package['nodes'][4]['body'])
        _, before = live.export('before-reader-save')
        require(filecmp.cmp(self.args.disk, before, shallow=False), 'browsing changed a durable byte')
        self.click(live, stream, 'explicit-reader-Save', 1370, 64, mutation=True)
        panel, medium = live.export('reader-saved')
        after_payload, after, records, saved_sequence = self.record(medium)
        require(after_payload == payload and after == workspace and saved_sequence == sequence + 1,
                'reader Save changed workspace/applicability/evidence/history/learner state')
        require(set(records) == set(old_records) | {(1, READER_OBJECT)}, 'reader Save changed unrelated keys')
        require(all(records[key].payload == record.payload for key, record in old_records.items()),
                'reader Save changed an existing object')
        expected = (0x31524452434d454c, 1, 1, 1, package['identity'], package['edition'],
                    struct.unpack_from('<Q', self.packages[0], 80)[0], 5, 5, 1, 0, 0, 0, 0, 0, 0)
        record = records[1, READER_OBJECT].payload
        require(len(record) == 128 and struct.unpack('<16Q', record) == expected,
                'actual durable reader fields differ from independent package/source oracle')
        require((1057, saved_sequence, 1, 1, READER_OBJECT) in self.rows(live),
                'guest durable acknowledgment did not name actual reader object/sequence')
        require(course_body_matches(panel, package['nodes'][4]['body']) and pad_matches(panel, False),
                'Save closed or changed the actual example view')
        live.close()
        self.sessions.remove(live)
        cold = self.cold('second', medium)
        stream = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.view(cold, stream, 'saved-example5-reopened', 320, 140,
                  package['nodes'][4]['body'], course=True)
        _, recovered = cold.export('reader-reopened')
        require(filecmp.cmp(medium, recovered, shallow=False), 'readonly reopen changed backing bytes')
        cold_payload, cold_workspace, cold_records, cold_sequence = self.record(recovered)
        require(cold_payload == payload and cold_workspace == workspace and cold_sequence == saved_sequence and
                cold_records[1, READER_OBJECT].payload == record, 'cold lost acknowledged reader/authority')
        require(not any(row[0] in (0x41f, 0x421, 0x423, 0x424, 1113, 1109)
                        for row in self.rows(cold)), 'cold reader reopening formatted/saved/checked')
        require(sha(self.args.disk) == self.original_medium_sha256, 'original opaque source changed')
        self.report.update(status='PASS_REAL_GUEST_NODE_SAVE_INDEPENDENT_COLD_REOPEN',
            source_sequence=sequence, saved_sequence=saved_sequence, reader_node=5,
            reader_kind='authored example, not an exercise submission', reader_record=list(expected),
            unchanged_workspace_sha256=hashlib.sha256(payload).hexdigest(), reader_record_hex=record.hex(),
            all_home_pixels=3_630_000, all_medium_bytes=268_435_456,
            independent_course_body_pixels=122_880, independent_keypad_pixels=76_800,
            no_new_mathematical_check=True)


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
    args.timeout, args.deadline = 120, 21600 if args.backend == 'rtl' else 900
    args.checkpoint_relation, args.durable_suffix_from = 'independent cold only', None
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = ReaderRecovery(args)
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
