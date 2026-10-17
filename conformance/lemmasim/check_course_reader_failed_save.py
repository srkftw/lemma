#!/usr/bin/env python3
"""Actual guest failed reader Save, then cold recovery of observed backing bytes.

The fault is a modeled first-FLUSH failure, not a claim of a new POSIX failure.
No document/reader bytes enter the machine from this observer. Failed barriers
do not imply rollback: cold recovery must follow the actual exported medium.
"""
import argparse
import filecmp
import json
import resource
import struct
import time
from pathlib import Path

from check_course_reader_recovery import ReaderRecovery, READER_OBJECT
from check_course_math_workflow import Input, decode, require, sha
from course_pixel_oracle import course_body_matches, label_matches
from number_pad_reference import pad_matches


class FailedReaderSave(ReaderRecovery):
    def __init__(self, args):
        super().__init__(args)
        self.report.update(schema='lemma-course-reader-failed-save/1', scope=__doc__)

    def session(self, name, disk, fail_flush=None):
        return super().session(name, disk, 1 if name == 'failed' else fail_flush)

    def wait_failure(self, session, stream, old_panel, tick):
        before = session.inspect()['machine']['cycle']
        start = time.monotonic()
        panel = self.directory / 'failed-status.ppm'
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            used = state['cycle'] - before
            require(0 <= used <= 150_000_000 and self.cycles <= 2_800_000_000 and
                    time.monotonic() - start <= 2400 and time.monotonic() < self.deadline,
                    'original failed-Save bounds')
            rows = self.rows(session)
            require(not state['finished'] and not any(row[0] in (1055, 1108, 212, 244) for row in rows),
                    'unrelated actual guest failure')
            require(not any(row[0] == 1057 for row in rows), 'failed barrier manufactured a Saved acknowledgment')
            failed = [row for row in rows if row[0] == 1060]
            if failed:
                require(failed[-1] == (1060, 227, 1, 1, READER_OBJECT),
                        'Failed did not preserve actual Store transport error/object identity')
                if (self.idle(state) and state['panel_completed'] > old_panel and
                        state['ticks'] >= tick + 200000):
                    session.control({'action': 'panel', 'path': str(panel)})
                    if label_matches(panel, 'FAILED'):
                        break
            require(used < 150_000_000 and self.cycles < 2_800_000_000, 'failed-Save clock ceiling')
            quantum = min(1_000_000, 150_000_000 - used, 2_800_000_000 - self.cycles)
            session.run(quantum)
            delta = session.inspect()['machine']['cycle'] - state['cycle']
            require(delta == quantum if self.backend == 'rtl' else delta > 0, 'admitted clock progress')
            self.cycles += delta
        self.report['phases'].append(dict(name='actual-reader-Failed-without-Saved',
            initial_cycle=before, final_cycle=state['cycle'], clocks=used,
            host_seconds=time.monotonic() - start, clock_cap=150_000_000, host_cap=2400))
        self.progress()
        return panel

    def execute(self):
        payload, workspace, original, sequence = self.record(self.args.disk)
        require(sequence == 38 and workspace['current']['origin'] == 'Unknown' and
                workspace['document']['outcome'] == 5, 'actual acknowledged Reader18 Saved38 input required')
        old_reader = original[1, READER_OBJECT].payload
        require(len(old_reader) == 128 and struct.unpack('<16Q', old_reader)[7:10] == (5, 5, 1),
                'actual acknowledged example5/revision1 required')
        package = decode(self.packages[0])
        live = self.cold('failed', self.args.disk)
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.view(live, stream, 'acknowledged-example5', 320, 140, package['nodes'][4]['body'], course=True)
        self.view(live, stream, 'unsaved-node6', 72, 650, package['nodes'][5]['body'])
        old_panel = live.inspect()['machine']['panel_completed']
        _, tick = self.raw(live, stream, 1370, 64)
        self.wait_failure(live, stream, old_panel, tick)
        panel, observed = live.export('failed-observed')
        after_payload, after_workspace, records, observed_sequence = self.record(observed)
        require(after_payload == payload and after_workspace == workspace and set(records) == set(original),
                'failed reader Save changed document authority/history or object keys')
        require(all(records[key].payload == record.payload for key, record in original.items()
                    if key != (1, READER_OBJECT)), 'failed reader Save changed another committed object')
        require(observed_sequence in (38, 39), 'unexpected observed persistence sequence')
        reader = records[1, READER_OBJECT].payload
        expected = list(struct.unpack('<16Q', old_reader))
        if observed_sequence == 39:
            expected[7:10] = [6, 6, 2]
        require(len(reader) == 128 and list(struct.unpack('<16Q', reader)) == expected,
                'actual recovery bytes disagree with the observed failed transaction')
        require(label_matches(panel, 'FAILED') and course_body_matches(panel, package['nodes'][5]['body']) and
                pad_matches(panel, False), 'failed Save lost the open view or Failed pixels')
        live.close()
        self.sessions.remove(live)
        cold = self.cold('after-failure', observed)
        stream = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.view(cold, stream, 'observed-reader-reopened', 320, 140,
                  package['nodes'][expected[7] - 1]['body'], course=True)
        _, recovered = cold.export('failed-cold-reopened')
        require(filecmp.cmp(observed, recovered, shallow=False), 'cold changed observed backing bytes')
        recovered_payload, recovered_workspace, recovered_records, recovered_sequence = self.record(recovered)
        require(recovered_payload == payload and recovered_workspace == workspace and
                recovered_sequence == observed_sequence and recovered_records[1, READER_OBJECT].payload == reader,
                'independent cold lost actual observed persistence or original authority')
        require(not any(row[0] in (0x41f, 0x421, 0x423, 0x424, 1113, 1109)
                        for row in self.rows(cold)), 'readonly cold formatted/saved/checked')
        require(sha(self.args.disk) == self.original_medium_sha256, 'acknowledged opaque source changed')
        self.report.update(status='PASS_REAL_GUEST_READER_FAILED_SAVE_OBSERVED_BYTES_COLD_RECOVERY',
            original_acknowledged_sequence=38, failed_live_saved_acknowledgments=0,
            observed_recovery_sequence=observed_sequence,
            unacknowledged_reader_observed=observed_sequence == 39, recovered_node=expected[7],
            rollback_assumed=False, authority_history_learner_ink_packages_unchanged=True,
            all_home_pixels=3_630_000, all_medium_bytes=268_435_456)


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
    actor = FailedReaderSave(args)
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
