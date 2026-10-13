#!/usr/bin/env python3
"""Actual Doc5→6 guest migration and mixed execution-history continuation.

Supply a real acknowledged ByteArray course medium. The observer only copies
opaque media, delivers raw pen samples and inspects outputs. The guest alone
upgrades, checks and saves the document. QEMU instruction-clock functional
scope; this does not qualify RTL timing or arbitrary cached-state snapshots.
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
        self.report['schema'] = 'lemma-array-document-migration/1'
        self.report['scope'] = __doc__
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))

    def execute(self):
        original_hash = sha(self.args.disk)
        original, before, records, sequence = self.record(self.args.disk)
        require(before['format'] == 'lemma-mathematical-submission/5' and
                before['attempts'] == 5 and before['hints'] == 1 and
                [entry['outcome'] for entry in before['history']] == [1, 2, 5, 1, 4] and
                all(entry['origin'] == 'IsolatedBytes' for entry in
                    before['execution']['history'][:5]),
                'require the independently acknowledged complete ByteArray course history')
        expected = bytearray(original)
        struct.pack_into('<Q', expected, 8, 6)
        struct.pack_into('<Q', expected, 1864, 4)
        untouched = {key: value.payload for key, value in records.items() if key != (1, 0x8001)}
        self.report['original'] = {'sequence': sequence, 'document_sha256': sha_bytes(original),
                                   'record': before}
        reuse = Path(self.args.migrated_from).resolve() if self.args.migrated_from else None
        if reuse:
            old = json.loads((reuse / 'result.json').read_text())
            require(old['schema'] == self.report['schema'] and old['status'] == 'FAIL' and
                    old['error'] == "'learner'" and old['medium_source']['sha256'] == original_hash,
                    'reuse only the retained exact missing-v6-learner observer failure')
            require(sha(reuse / 'original-check_array_document_migration.py') ==
                    old['observer_sources']['scripts/check_array_document_migration.py'] and
                    sha(reuse / 'original-math_oracle.py') ==
                    old['observer_sources']['conformance/lemmasim/math_oracle.py'],
                    'retained original observer sources differ')
            for name, evidence in old['artifacts'].items():
                require(sha(reuse / name) == evidence['sha256'], 'retained actual artifact changed: ' + name)
            retained, parsed, retained_records, _ = self.record(reuse / 'guest-upgraded-course.raw')
            require(retained == bytes(expected) and parsed['learner'] == before['learner'] and
                    parsed['execution'] == before['execution'] and
                    {key:value.payload for key,value in retained_records.items() if key != (1,0x8001)} == untouched,
                    'retained actual migration did not preserve exact old history and objects')
            from check_live_notebook import guest_events
            require(any(row == (0x421, sequence + 1, 1, 1, 0x8001) for row in
                        guest_events(reuse / 'migration/uart-0.bin')),
                    'retained guest did not acknowledge the actual migration publication')
            self.report['retained_migration'] = {'path':str(reuse), 'original_status':'FAIL',
                'original_error':old['error'], 'result_sha256':sha(reuse / 'result.json'),
                'independent_observation':'Exact two-word upgrade; v6 now requires unchanged learner-policy/event validation',
                'actual_medium_sha256':sha(reuse / 'guest-upgraded-course.raw')}
        disk = self.directory / 'migration-input.raw'
        shutil.copyfile(reuse / 'guest-upgraded-course.raw' if reuse else self.args.disk, disk)
        live = self.session('migration', disk)
        self.report['identity'] = live.identity
        self.report['boot'] = live.boot()
        self.wait_label(live, 'SAVED', 24, 132)
        initial_panel, initial_medium = live.export('initial-notebook')
        require(self.record(initial_medium)[0] == (bytes(expected) if reuse else original),
                'cold boot changed the acknowledged document before opening')
        stream = Input(1650, 2200, live.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(live, stream, 'open actual migrated course' if reuse else 'open actual old ByteArray course', 320, 140)
        self.wait_label(live, 'SAVED', 24, 132)
        course_panel, upgraded_medium = live.export('guest-upgraded-course')
        upgraded, after, upgraded_records, upgraded_sequence = self.record(upgraded_medium)
        require(upgraded == bytes(expected), 'migration changed bytes beyond the two declared version words')
        require(after['execution'] == before['execution'] and after['history'] == before['history'] and
                after['learner'] == before['learner'], 'migration reclassified older evidence or assistance')
        require({key: value.payload for key, value in upgraded_records.items() if key != (1, 0x8001)} == untouched,
                'migration changed existing raw ink or another object')
        require(upgraded_sequence == sequence + 1 and
                (not any(row[0] == 0x421 for row in self.rows(live)) if reuse else
                 any(row == (0x421, upgraded_sequence, 1, 1, 0x8001) for row in self.rows(live))),
                'migration publication or already-upgraded no-publication semantics differ')
        self.report['migration'] = {'status': 'PASS', 'sequence': upgraded_sequence,
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
        checked = self.press(live, stream, 'actual new Array check of retained unsupported goal', 1, 4)
        require(checked[2] == 3 and checked[3] == 4, 'new check falsely verified the unsupported goal')
        self.wait_label(live, 'SAVED', 24, 132)
        _, checked_medium = live.export('mixed-execution-history')
        current_bytes, current, current_records, _ = self.record(checked_medium)
        require(current['format'] == 'lemma-mathematical-submission/6' and current['attempts'] == 6 and
                current['history'][:5] == before['history'] and
                current['execution']['history'][:5] == before['execution']['history'][:5],
                'new check rewrote historical mathematical or implementation evidence')
        new = current['execution']['history'][5]
        require(new['origin'] == 'IsolatedArray' and new['status'] == 0 and
                current['execution']['active'] == new,
                'new check lacks its real Array execution identity')
        requests = [row for row in self.rows(live) if row[0] == 0x459]
        replies = [row for row in self.rows(live) if row[0] == 0x455]
        require(len(requests) == count + 1 and len(replies) == 1 and
                requests[-1][1:4] == (new['request'], current['revision'], current['goal']) and
                replies[-1][1:] == (new['request'], current['revision'], 0, 4),
                'new durable result differs from actual guest request/reply')
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
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--migrated-from',
                        help='Independently validate retained missing-v6-learner failure, then continue its acknowledged medium')
    parser.add_argument('--timeout', type=int, default=300)
    parser.add_argument('--boot-seconds', type=int, default=60)
    parser.add_argument('--action-seconds', type=int, default=30)
    parser.add_argument('--deadline', type=int, default=1200)
    args = parser.parse_args()
    args.guest_build = None
    args.durable_suffix_from = None
    args.checkpoint_relation = 'not-exercised'
    require(1 <= args.timeout <= 3600 and 1 <= args.boot_seconds <= 600 and
            1 <= args.action_seconds <= 600 and 1 <= args.deadline <= 2400,
            'invalid predeclared resource bounds')
    checker = MigrationChecker(args)
    try:
        checker.execute()
    except BaseException as error:
        checker.report['error'] = str(error)
        raise
    finally:
        checker.close()
    print(json.dumps({'status': checker.report['status'], 'work_dir': str(checker.directory)}))


if __name__ == '__main__':
    main()
