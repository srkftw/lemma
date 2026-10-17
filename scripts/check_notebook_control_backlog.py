#!/usr/bin/env python3
"""Real queued numeric taps, concurrent raw ink, checked result and cold recovery.

Only raw device input reaches the guest. Independent observers inspect original
exported media/pixels/UART; they never supply document or mathematical state.
"""
import argparse
import filecmp
import json
from pathlib import Path
import shutil
import signal
import struct
import time

from check_fresh_course_reader import FreshChooser, Input, decode, require, sha, visible_pixels
from check_canonical_pen_pixels import expected_stroke
from course_pixel_oracle import label_matches
from store_oracle import recover

ROOT = Path(__file__).resolve().parents[1]


class BacklogWorkflow(FreshChooser):
    def phase(self, session, name, cap, predicate):
        if not getattr(self, 'overflow_admitted', False) or session.directory.name != 'first':
            return super().phase(session, name, cap, predicate)
        if self.backend == 'rtl' and name == 'Close-course':
            cap = 500_000_000
        seconds = 3600 if self.backend == 'rtl' else 600
        before = session.inspect()['machine']['cycle']
        began = time.monotonic()
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            used = state['cycle'] - before
            require(0 <= used <= cap and self.cycles <= self.aggregate_cap and
                    time.monotonic() < self.deadline and time.monotonic() - began <= seconds,
                    'original overflow workflow phase/whole bound: ' + name)
            rows = self.rows(session)
            require(not state['finished'] and not any(row[0] in (1055, 1060, 212, 244) for row in rows),
                    'actual fault after controlled queue overflow')
            errors = [row for row in rows if row[0] == 1108]
            require(len(errors) <= 1 and all(row[1] == 242 for row in errors),
                    'unexpected error or duplicate overflow report')
            if predicate(state):
                break
            require(used < cap and self.cycles < self.aggregate_cap, 'original overflow clock ceiling')
            quantum = min(1_000_000, cap - used, self.aggregate_cap - self.cycles)
            session.run(quantum)
            after = session.inspect()['machine']['cycle']
            require(after - state['cycle'] == quantum if self.backend == 'rtl' else after > state['cycle'],
                    'actual execution progress after overflow')
            self.cycles += after - state['cycle']
        self.report['phases'].append({'name': name, 'initial_cycle': before, 'final_cycle': state['cycle'],
                                      'execution_units': used, 'phase_clock_cap': cap,
                                      'host_seconds': time.monotonic() - began, 'phase_host_cap': seconds,
                                      'declared_course_error': 242, 'actual_error_rows': errors})
        self.progress()
        return state

    def overflow(self, session, stream):
        before = self.checkpoint_record(session, 'before-overflow')
        state = session.inspect()['machine']
        first = len(stream.events)
        stream.tick = state['ticks'] + 10000
        old_interval = stream.interval
        stream.interval = 1000  # Explicit Laboratory queue-pressure input.
        for _ in range(12):
            stream.sample(172, 245, 2048, True)
            stream.sample(172, 245, 0, False)
        stream.interval = old_interval
        self.overflow_admitted = True
        session.admit(stream.events[first:])
        self.phase(session, 'controlled-eight-entry-overflow', 650_000_000,
                   lambda st: self.idle(st) and st['panel_completed'] > state['panel_completed'] and
                   st['ticks'] >= stream.events[-1][1] + 200000 and
                   len([row for row in self.rows(session) if row[0] == 1108 and row[1] == 242]) == 1)
        after = self.checkpoint_record(session, 'after-overflow')
        old, new = before[3]['document'], after[3]['document']
        require(new['revision'] == old['revision'] and new['answer'] == old['answer'] and
                new['history'] == old['history'] and new['outcome'] == old['outcome'] == 1 and
                new['hints'] == old['hints'] + 1, 'overflow corrupted the completed result or applied lost suffixes')
        first = len(stream.events)
        stream.tick = session.inspect()['machine']['ticks'] + 10000
        stream.stroke('writing-after-controlled-overflow', 1, 1, 3, 1800)
        samples = stream.events[first:]
        points = expected_stroke(samples)[1]
        oldacks = len([row for row in self.rows(session) if row[0] == 1057])
        session.admit(samples)
        panel = self.directory / 'overflow-writing-wait.ppm'

        def written(st):
            if not self.idle(st) or not self.saved(session) or st['ticks'] < samples[-1][1] + 200000 or \
                    len([row for row in self.rows(session) if row[0] == 1057]) <= oldacks:
                return False
            session.control({'action': 'panel', 'path': str(panel)})
            width, _, pixels = visible_pixels(panel)
            return all(pixels[(y * width + x) * 3:(y * width + x) * 3 + 3] == bytes(3) for x, y in points)

        self.phase(session, 'ordinary-ink-after-overflow-Saved', 300_000_000, written)
        self.click(session, stream, 'explicit-Save-after-overflow', 1370, 64, mutation=True)
        self.report['controlled_overflow'] = {'declared_error': 242, 'twelve_original_taps': True,
                                               'laboratory_pressure_interval_ticks': 1000,
                                               'completed_math_history_unchanged': True,
                                               'only_first_hint_applied': True,
                                               'new_ordinary_ink_samples': [list(x) for x in samples],
                                               'independent_black_pixels': len(points)}

    def execute(self):
        package = decode(self.args.package[0].read_bytes())
        _, original_sequence, original = recover(self.args.disk.read_bytes())
        require(original_sequence == 3 and len(original) == 3 and package['edition'] == 3,
                'actual guest-installed fresh edition3/sequence3 medium required')
        disk = self.directory / 'private.raw'
        shutil.copyfile(self.args.disk, disk)
        session = self.session('first', disk)
        require(session.inspect()['machine']['cycle'] == 0, 'actual cold CPU0 required')
        self.phase(session, 'cold-Ready', 1_000_000_000,
                   lambda st: self.idle(st) and st['panel_completed'] >= 1 and
                   any(row[0] == 1056 for row in self.rows(session)))
        stream = Input(1650, 2200, session.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(session, stream, 'open-chooser', 320, 140)
        self.click(session, stream, 'choose-edition2', 168, 670)
        self.click(session, stream, 'choose-edition3', 168, 670)
        self.click(session, stream, 'load-edition3', 264, 670, text=package['nodes'][0]['body'])
        self.click(session, stream, 'node2', 72, 650, text=package['nodes'][1]['body'])
        self.click(session, stream, 'exercise3', 72, 650, text=package['nodes'][2]['body'])
        self.click(session, stream, 'USE-original-goal', 360, 650, mutation=True)
        self.click(session, stream, 'select-numerator', 100, 225, mutation=True)
        self.click(session, stream, 'enter5', 640, 250, mutation=True)
        before = self.checkpoint_record(session, 'before-burst')
        require(before[3]['document']['answer'][:2] == [5, 1], 'actual starting operands5/1')
        require(all(before[4][key].payload == value.payload for key, value in original.items()),
                'course setup changed original package/root/page objects')
        initial = session.inspect()['machine']
        first = len(stream.events)
        stream.tick = initial['ticks'] + 10000
        # These are the actual four controls dropped by the old busy path.
        # No per-control waits or application RPCs occur between admissions.
        for x, y in ((124, 225), (512, 330), (768, 250), (40, 245)):
            stream.sample(x, y, 2048, True)
            stream.sample(x, y, 0, False)
        ink_start = len(stream.events)
        stream.stroke('ink-during-control-publication', 1, 1, 3, 1900)
        samples = stream.events[ink_start:]
        points = expected_stroke(samples)[1]
        session.admit(stream.events[first:])
        panel = self.directory / 'burst-wait.ppm'

        def complete(state):
            rows = self.rows(session)
            requests = [row for row in rows if row[0] == 1113]
            replies = [row for row in rows if row[0] == 1109]
            if not requests or not replies or replies[-1][1] != requests[-1][1]:
                return False
            require(replies[-1][3:] == (0, 1), 'burst did not check the actual5/6 as Verified')
            require((1117, requests[-1][1], 0, 0, 0) in rows, 'actual checker graph was not reclaimed')
            if not self.idle(state) or not self.saved(session) or state['ticks'] < samples[-1][1] + 200000:
                return False
            session.control({'action': 'panel', 'path': str(panel)})
            width, _, pixels = visible_pixels(panel)
            return (label_matches(panel, 'N 05 D 06 C0 00 C1 00 C2 00', 24, 200) and
                    label_matches(panel, 'VERIFIED Q EXACT', 24, 260) and
                    all(pixels[(y * width + x) * 3:(y * width + x) * 3 + 3] == bytes(3)
                        for x, y in points))

        # Four ordinary150M controls + the existing300M checker +300M ink
        # ceilings compose this new prospectively declared connected phase.
        self.phase(session, 'queued-four-controls-with-raw-ink', 1_200_000_000, complete)
        after = self.checkpoint_record(session, 'after-burst')
        document = after[3]['document']
        require(document['answer'][:2] == [5, 6] and document['outcome'] == 1 and
                document['evidence_revision'] == document['revision'] and document['attempts'] == 1 and
                after[3]['applicable_package_selection'], 'actual revision-bound burst result differs')
        chunks = []
        for record in after[4].values():
            payload = record.payload
            if len(payload) >= 128 and struct.unpack_from('<3Q', payload) == (0x314b4e49414d454c, 1, 3):
                count = struct.unpack_from('<Q', payload, 48)[0]
                require(len(payload) == 128 + 72 * count, 'actual raw chunk extent')
                chunks.append([struct.unpack_from('<9Q', payload, 128 + i * 72) for i in range(count)])
        require(chunks.count(samples) == 1, 'concurrent raw ink missing, changed or duplicated')
        self.report['queued_controls'] = {'raw_samples': [list(x) for x in stream.events[first:ink_start]],
                                          'ink_samples': [list(x) for x in samples],
                                          'independent_black_pixels': len(points),
                                          'workspace': after[3], 'whole_burst_cap': 1_200_000_000}
        self.click(session, stream, 'explicit-Save', 1370, 64, mutation=True)
        if self.args.with_overflow:
            self.overflow(session, stream)
        else:
            self.click(session, stream, 'Close-course', 320, 140)
        home, saved = session.export('closed')
        payload, workspace, records, sequence = self.record(saved)
        package_key = (1, 4850376798678024192 | package['identity'] << 32 | package['edition'])
        require(records[package_key].payload == original[package_key].payload,
                'queued workflow changed the installed immutable package')
        session.close()
        self.sessions.remove(session)
        cold_disk = self.directory / 'cold-input.raw'
        shutil.copyfile(saved, cold_disk)
        cold = self.session('second', cold_disk)
        require(cold.inspect()['machine']['cycle'] == 0, 'independent CPU0 cold required')
        self.phase(cold, 'second-cold-Ready', 1_000_000_000,
                   lambda st: self.idle(st) and st['panel_completed'] >= 1 and
                   any(row[0] == 1056 for row in self.rows(cold)))
        cp, cm = cold.export('second-ready')
        require(visible_pixels(cp) == visible_pixels(home) and filecmp.cmp(saved, cm, shallow=False),
                'complete independent cold pixels or durable bytes differ')
        second_stream = Input(1650, 2200, cold.inspect()['machine']['ticks'] + 10000, 100000, 0)
        self.click(cold, second_stream, 'cold-reopen-node3', 320, 140, text=package['nodes'][2]['body'])
        _, rm = cold.export('reopened')
        final = self.record(rm)
        require(final[0] == payload and final[1] == workspace and filecmp.cmp(saved, rm, shallow=False),
                'cold reopen changed exact evidence, learner history or backing')
        require(sha(self.args.disk) == self.original_medium_sha256, 'original source medium changed')
        self.report.update(status='PASS_QUEUED_GUEST_CONTROLS_CONCURRENT_INK_CHECK_SAVE_INDEPENDENT_COLD',
                           whole_execution_units=self.cycles, final_sequence=sequence,
                           all_cold_home_pixels=3630000, all_medium_bytes=268435456,
                           qualification='Connected guest workflow; fast clocks do not establish RTL timing or QEMU cached continuation')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('disk', 'package', 'native-bundle', 'work-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--guest-build', type=Path)
    parser.add_argument('--guest-source-root', type=Path)
    parser.add_argument('--backend', choices=('qemu', 'rtl'), default='qemu')
    parser.add_argument('--with-overflow', action='store_true',
                        help='Also overflow the guest queue, preserve its first durable action and write ordinary ink before cold recovery')
    args = parser.parse_args()
    if bool(args.guest_build) != bool(args.guest_source_root):
        parser.error('guest override requires its complete audited source archive')
    if args.work_dir.exists() or not args.work_dir.resolve().is_relative_to(ROOT / 'build'):
        parser.error('unused ignored output required')
    args.disk = args.disk.resolve()
    args.package = [args.package.resolve()]
    args.native_bundle = str(args.native_bundle.resolve())
    if args.guest_build:
        args.guest_build = str(args.guest_build.resolve())
    args.timeout = 120
    args.deadline = 43200 if args.backend == 'rtl' else 1800
    args.checkpoint_relation = 'independent cold only'
    args.durable_suffix_from = None
    args.with_hint_context = False
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda number, frame: (_ for _ in ()).throw(SystemExit(128 + number)))
    actor = BacklogWorkflow(args)
    actor.report.update(scope=__doc__, observer_sha256=sha(__file__))
    actor.progress()
    try:
        actor.execute()
    except BaseException as error:
        actor.report.update(status='FAIL', error=repr(error))
        raise
    finally:
        actor.close()
        (actor.directory / 'result.json').write_text(json.dumps(actor.report, default=str, indent=2) + '\n')
    print(actor.report['status'], actor.cycles, actor.report['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
