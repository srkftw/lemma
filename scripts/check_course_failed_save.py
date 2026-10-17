"""Real course ink, failed first backing FLUSH and independent durable-only cold recovery.
Host observer only. The declared fail-FLUSH knob fails before backing writeback;
this case makes no claim about actual OS partial-write or barrier failures.
"""
from pathlib import Path
import argparse
import json
import resource
import shutil
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'conformance/lemmasim')]
from check_course_save import CourseSave, Input, require, visible_pixels, sha
from course_pixel_oracle import annotation_pixels, course_body_matches, label_matches, ROWS

class FailedCourse(CourseSave):

    def until(self, session, name, cap, host, predicate):
        if name != 'expected-failed-FLUSH-visible-course':
            return super().until(session, name, cap, host, predicate)
        start = session.inspect()['machine']['cycle']
        began = time.monotonic()
        while True:
            self.check_sources()
            state = session.inspect()['machine']
            used = state['cycle'] - start
            elapsed = time.monotonic() - began
            require(elapsed <= host and used <= cap and (self.total + used <= 3000000000), 'predeclared failure/aggregate bound')
            require(not state['finished'] and (not any((row[0] in (0x41f, 0xd4, 0xf4, 0x454) for row in self.rows(session)))), 'unexpected guest fault during expected FLUSH failure')
            if predicate(state):
                self.total += used
                phase = dict(name=name, initial_cycle=start, final_cycle=state['cycle'], clock_units=used, host_seconds=elapsed)
                self.report['phases'].append(phase)
                print(json.dumps(phase), flush=True)
                return state
            require(used < cap, 'predeclared failed FLUSH cap')
            session.run(min(1000000, cap - used))

    def execute(self):
        original = self.args.disk
        disk = self.directory / 'input.raw'
        shutil.copyfile(original, disk)
        live = self.session('live', disk, fail_flush=1)
        require(live.inspect()['machine']['cycle'] == 0, 'new live CPU required')
        self.report['identity'] = live.identity
        boot = lambda machine, s: self.quiet(s) and self.completed(s) > 0 and any((row[0] == 0x420 for row in self.rows(machine)))
        self.until(live, 'independent-cold-input', 1000000000, 180, lambda s: boot(live, s))
        stream = Input(1650, 2200, 0, 100000, 0)
        self.tap(live, stream, 320, 140)
        self.until(live, 'actual-course-body', 400000000, 180, self.rendered(live, 'opened-course'))
        baseline = visible_pixels(self.directory / 'opened-course.ppm')
        before = len(self.rows(live))
        first = len(stream.events)
        stream.tick = live.inspect()['machine']['ticks'] + 10000
        stream.stroke('failed course annotation', 1, 1, 3, 1400)
        raw = stream.events[first:]
        expected = annotation_pixels(baseline, raw, self.brush_q8)
        pixels = bytearray(expected[2])
        # The nine status cells change to FAILED. Every other expected
        # course, prior-ink and provisional-annotation pixel remains compared.
        for y in range(15):
            for x in range(108):
                glyph = ROWS['FAILED   '[x // 12]]
                within = x % 12
                black = within < 9 and glyph[y // 3][within // 3] == '1'
                at = ((132 + y) * 1650 + 24 + x) * 3
                pixels[at:at + 3] = bytes([0 if black else 255]) * 3
        expected = (1650, 2200, bytes(pixels))
        minimum = self.completed(live.inspect()['machine'])
        panel = self.directory / 'failed-course.ppm'
        observed = -1

        def failed(s):
            nonlocal observed
            rows = self.rows(live)[before:]
            require(not any((row[0] == 0x421 for row in rows)), 'manufactured Saved after failed barrier')
            if not (any((row[0] == 0x424 for row in rows)) and s['ticks'] >= raw[-1][1] + 200000 and self.quiet(s) and (self.completed(s) > minimum) and (self.completed(s) != observed)):
                return False
            observed = self.completed(s)
            live.control({'action': 'panel', 'path': str(panel)})
            return label_matches(panel, 'FAILED   ') and course_body_matches(panel, self.body) and (visible_pixels(panel) == expected)
        live.admit(raw)
        self.until(live, 'expected-failed-FLUSH-visible-course', 200000000, 180, failed)
        _, medium = live.export('failed-durable')
        require(medium.read_bytes() == original.read_bytes(), 'fail-before-writeback changed durable bytes')
        self.report['actual_raw_samples'] = raw
        live.close()
        self.sessions.remove(live)
        cold_disk = self.directory / 'cold.raw'
        shutil.copyfile(medium, cold_disk)
        cold = self.session('cold', cold_disk)
        require(cold.inspect()['machine']['cycle'] == 0, 'independent cold CPU required')
        self.until(cold, 'cold-after-failed-FLUSH', 1000000000, 180, lambda s: boot(cold, s))
        self.tap(cold, Input(1650, 2200, 0, 100000, 0), 320, 140)
        self.until(cold, 'cold-original-complete-course-and-acknowledged-ink', 400000000, 180, self.rendered(cold, 'cold-reopened-course', baseline))
        _, final = cold.export('cold-final')
        require(final.read_bytes() == original.read_bytes(), 'cold changed original acknowledged bytes')
        require(sha(original) == self.report['source_medium_sha256'], 'original medium changed')
        self.report.update(status='PASS_REAL_FAILED_FLUSH_COURSE_INK_COLD', total_clock_units=self.total, no_snapshot=True, no_saved_after_failure=True, complete_failed_controller_pixels_exact=True, cold_original_pixels_exact=True, whole_durable_medium_exact=True, fault_scope='declared injected fail-before-writeback FLUSH, not actual OS failure')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--backend', choices=('qemu',), default='qemu')
    for name in ('disk', 'package', 'work-dir', 'guest-source-root'):
        p.add_argument('--' + name, type=Path, required=True)
    for name in ('native-bundle', 'guest-build'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    a.disk = a.disk.resolve()
    a.package = a.package.resolve()
    a.backend = 'qemu'
    a.timeout = 120
    a.deadline = 900
    a.durable_suffix_from = None
    a.checkpoint_relation = 'independent cold only'
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = FailedCourse(a)
    actor.report["scope"] = __doc__
    try:
        actor.execute()
    except BaseException as e:
        actor.report.update(status='FAIL', error=repr(e))
        raise
    finally:
        actor.finish()
    require(actor.report['status'] == 'PASS_REAL_FAILED_FLUSH_COURSE_INK_COLD', 'failed course observer finalization failed')
if __name__ == '__main__':
    main()
