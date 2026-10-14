#!/usr/bin/env python3
"""Actual Doc7→8 migration preserves acknowledged Bytes/Array/String histories.

Only raw pen enters the guest. A matching isolated Protocol7 check appends the
new closed execution authority, and independent cold CPUs must preserve all
old mathematical, learner, raw-ink and execution bytes. No host publication.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct

from check_math_session import MathChecker
from check_live_notebook import Input, ROOT, require, sha, visible_pixels


class MigrationChecker(MathChecker):
    def __init__(self, args):
        super().__init__(args)
        if args.guest_source_root is not None:
            self.report['bounds']['guest_source_root'] = str(args.guest_source_root.resolve())
        self.report['schema'] = 'lemma-closure-document-migration/1'
        self.report['scope'] = __doc__
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))

    def execute(self):
        original_hash = sha(self.args.disk)
        original, before, records, sequence = self.record(self.args.disk)
        source_version = 7
        destination_version = source_version + 1
        previous_attempts = 7
        origins = ['IsolatedBytes'] * 5 + ['IsolatedArray','IsolatedString']
        outcomes = [1, 2, 5, 1, 4, 4, 4]
        require(before['format'] == 'lemma-mathematical-submission/' + str(source_version) and
                before['attempts'] == previous_attempts and before['hints'] == 1 and
                before['goal'] == 3 and
                [entry['outcome'] for entry in before['history']] == outcomes and
                [entry['origin'] for entry in before['execution']['history'][:previous_attempts]] == origins,
                'require the independently acknowledged complete prior course history')
        expected = bytearray(original)
        struct.pack_into('<Q', expected, 8, destination_version)
        struct.pack_into('<Q', expected, 1864, destination_version - 2)
        untouched = {key: value.payload for key, value in records.items() if key != (1, 0x8001)}
        self.report['original'] = {'sequence': sequence, 'document_sha256': sha_bytes(original),
                                   'record': before}
        disk = self.directory / 'migration-input.raw'
        shutil.copyfile(self.args.disk, disk)
        live = self.session('migration', disk)
        self.report['identity'] = live.identity
        self.report['boot'] = live.boot()
        self.wait_label(live, 'SAVED', 24, 132)
        initial_panel, initial_medium = live.export('initial-notebook')
        require(self.record(initial_medium)[0] == original,
                'cold boot changed the acknowledged document before opening')
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(live, stream, 'open actual old course', 320, 140)
        self.wait_label(live, 'SAVED', 24, 132)
        course_panel, upgraded_medium = live.export('guest-upgraded-course')
        upgraded, after, upgraded_records, upgraded_sequence = self.record(upgraded_medium)
        require(upgraded == bytes(expected), 'migration changed bytes beyond the two declared version words')
        require(after['execution'] == before['execution'] and after['history'] == before['history'] and
                after['learner'] == before['learner'], 'migration reclassified older evidence or assistance')
        require({key: value.payload for key, value in upgraded_records.items() if key != (1, 0x8001)} == untouched,
                'migration changed existing raw ink or another object')
        require(upgraded_sequence == sequence + 1 and
                any(row == (0x421, upgraded_sequence, 1, 1, 0x8001) for row in self.rows(live)),
                'migration lacks its actual durable publication')
        self.report['migration'] = {'status': 'PASS', 'sequence': upgraded_sequence,
            'source_version': source_version, 'destination_version': destination_version,
            'exact_changed_word_offsets': [8, 1864], 'old_known_execution_preserved': True,
            'history_assistance_and_other_objects_exact': True, 'document_sha256': sha_bytes(upgraded)}
        self.click(live, stream, 'close migrated course', 320, 140, False)
        self.wait_label(live, 'SAVED', 24, 132)
        closed_panel, closed_medium = live.export('migrated-closed')
        require(visible_pixels(closed_panel) == visible_pixels(initial_panel),
                'migration changed any complete notebook controller pixel')
        require(self.record(closed_medium)[0] == upgraded, 'closing changed the migrated record')
        self.click(live, stream, 'reopen migrated course', 320, 140)
        self.wait_label(live, 'SAVED', 24, 132)
        reopened_panel, reopened_medium = live.export('migrated-reopened')
        require(visible_pixels(reopened_panel) == visible_pixels(course_panel) and
                self.record(reopened_medium)[0] == upgraded,
                'reopening changed migrated course pixels or evidence')
        count = len([row for row in self.rows(live) if row[0] == 0x459])
        new_origin = 'IsolatedClosure'
        checked = self.press(live, stream, 'actual new ' + new_origin + ' check of retained unsupported goal', 1, 4)
        require(checked[2] == 3 and checked[3] == 4, 'new check falsely verified the unsupported goal')
        self.wait_label(live, 'SAVED', 24, 132)
        _, checked_medium = live.export('mixed-execution-history')
        current_bytes, current, current_records, _ = self.record(checked_medium)
        require(current['format'] == 'lemma-mathematical-submission/' + str(destination_version) and
                current['attempts'] == previous_attempts + 1 and
                current['history'][:previous_attempts] == before['history'] and
                current['execution']['history'][:previous_attempts] == before['execution']['history'][:previous_attempts],
                'new check rewrote historical mathematical or implementation evidence')
        new = current['execution']['history'][previous_attempts]
        require(new['origin'] == new_origin and new['status'] == 0 and
                current['execution']['active'] == new,
                'new check lacks its real admitted execution identity')
        requests = [row for row in self.rows(live) if row[0] == 0x459]
        replies = [row for row in self.rows(live) if row[0] == 0x455]
        require(len(requests) == count + 1 and len(replies) == 1 and
                requests[-1][1:4] == (new['request'], current['revision'], current['goal']) and
                replies[-1][1:] == (new['request'], current['revision'], 0, 4),
                'new durable result differs from actual guest request/reply')
        require(any(row[0] == 0x45c and tuple(row[1:]) ==
                    (0x0007000100000001, 0x0007000000000001,
                     0x0001000500000001, 0x000500000000001f)
                    for row in self.rows(live)),
                'actual server did not publish exact Closure execution contracts')
        require({key: value.payload for key, value in current_records.items() if key != (1, 0x8001)} == untouched,
                'new checking changed original notebook objects')
        self.report['mixed_execution'] = {'status': 'PASS', 'actual_request': requests[-1],
            'actual_reply': replies[-1], 'record': current, 'document_sha256': sha_bytes(current_bytes)}
        self.click(live, stream, 'close after new check', 320, 140, False)
        self.wait_label(live, 'SAVED', 24, 132)
        final_panel, final_medium = live.export('final-notebook')
        require(visible_pixels(final_panel) == visible_pixels(initial_panel), 'checking changed notebook pixels')
        live.close()
        self.sessions.remove(live)
        cold_disk = self.directory / 'cold-input.raw'
        shutil.copyfile(final_medium, cold_disk)
        cold = self.session('cold', cold_disk)
        self.report['cold_boot'] = cold.boot()
        require(cold.identity == self.report['identity'], 'independent cold artifact identities changed')
        self.wait_label(cold, 'SAVED', 24, 132)
        cold_panel, cold_medium = cold.export('cold-notebook')
        require(visible_pixels(cold_panel) == visible_pixels(final_panel) and
                self.record(cold_medium)[0] == current_bytes,
                'independent cold lost mixed evidence or complete notebook pixels')
        cold_stream = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(cold, cold_stream, 'cold reopen mixed-history course', 320, 140)
        self.wait_label(cold, 'SAVED', 24, 132)
        _, recovered_medium = cold.export('cold-course')
        require(self.record(recovered_medium)[0] == current_bytes, 'cold course reopen rewrote execution history')
        self.report['cold_recovery'] = {'status': 'PASS', 'new_cpu': True,
            'mixed_history_exact': True, 'all_controller_pixels_exact': True}
        cold.close()
        self.sessions.remove(cold)
        require(sha(self.args.disk) == original_hash, 'observer mutated the original acknowledged medium')
        self.report['status'] = 'PASS'


def sha_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', type=Path, required=True)
    parser.add_argument('--native-bundle', required=True)
    parser.add_argument('--guest-build', help='Explicit current source-qualified guest override; retain the prepared native machine')
    parser.add_argument('--guest-source-root', type=Path,
                        help='Complete exact consumed-source archive for the selected guest')
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--destination-runtime', choices=('closure',), default='closure',
                        help='Real Doc7→8 mixed-history Closure migration')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--boot-seconds', type=int, default=60)
    parser.add_argument('--action-seconds', type=int, default=30)
    parser.add_argument('--deadline', type=int, default=1200)
    args = parser.parse_args()
    args.durable_suffix_from = None
    args.checkpoint_relation = 'not-exercised'
    require(1 <= args.timeout <= 3600 and 1 <= args.boot_seconds <= 600 and
            1 <= args.action_seconds <= 600 and 1 <= args.deadline <= 2400,
            'invalid predeclared resource bounds')
    checker = MigrationChecker(args)
    try:
        checker.execute()
    except BaseException as error:
        checker.report['status'] = 'FAIL'
        checker.report['error'] = str(error)
        raise
    finally:
        checker.close()
    print(json.dumps({'status': checker.report['status'], 'work_dir': str(checker.directory)}))


if __name__ == '__main__':
    main()
