#!/usr/bin/env python3
"""Real guest course annotation, idle explicit Save and independent cold reopen.

All input uses the public machine session API. This host observer supplies raw
pen samples and checks exported bytes/pixels; it never constructs guest ink,
recovers a journal for the guest, or supplies a mathematical result.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance/lemmasim"))
from check_live_notebook import Checker, Input, guest_events, idle, require, visible_pixels
from course_package import decode
from course_pixel_oracle import annotation_pixels, course_body_matches, label_matches
from inspect_notebook import MAGIC
from store_oracle import recover


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def rtl_idle(state):
    backing = state["backing_io"]
    require(all(type(backing[key]) is int and 0 <= backing[key] < 1 << 64
                for key in ("phase", "next_id", "completed", "durable_barrier", "observed_write")),
            "native backing counter schema")
    # Completed is retained after the first actual I/O. It is not Pending.
    owner = ((backing["phase"] == 0 and backing["next_id"] == 1 and
              backing["completed"] == backing["durable_barrier"] ==
              backing["observed_write"] == 0) or
             (backing["phase"] == 2 and backing["next_id"] == backing["completed"] + 1 and
              backing["durable_barrier"] <= backing["completed"] and
              backing["observed_write"] <= backing["completed"]))
    return (owner and all(state[key] == 0 for key in
            ("event_queue", "pen_queue", "uart_queue", "paper_busy",
             "panel_pending_pixels", "block_state", "dma_outstanding")) and
            all(backing[key] is False for key in
                ("retry_ready", "fork_suspended", "orphan", "poisoned")))


class CourseSave(Checker):
    profile = "lemma-silicon-dev/0.3.0"

    def __init__(self, args):
        self.backend = args.backend
        super().__init__(args)
        self.total = 0
        self.censuses = []
        self.frozen = {}
        self.body = decode(args.package.read_bytes())["nodes"][0]["body"]
        _, _, records = recover(args.disk.read_bytes())
        root = records[(1, 1)].payload
        require(len(root) == 64 and struct.unpack_from("<3Q", root) == (MAGIC, 1, 1),
                "source notebook root format")
        self.brush_q8 = struct.unpack_from("<Q", root, 32)[0]
        self.report.update(scope=__doc__, phases=[], source_medium_sha256=sha(args.disk),
                           package_sha256=sha(args.package),
                           claims="Fast functional units or exact RTL clocks by backend; "
                                  "no cross-backend timing/cache claim; no snapshots.")
        (self.directory / "predeclared.json").write_text(
            json.dumps(self.report, default=str, indent=2) + "\n")

    def launch(self, arguments, **kwargs):
        require(time.monotonic() < self.deadline, "campaign host resource deadline")
        if self.frozen:
            self.check_sources()
        census = self.directory / ("imports-" + str(len(self.censuses) + 1) + ".json")
        self.censuses.append(census)
        command = [sys.executable, str(ROOT / "scripts/host_import_census.py"),
                   str(census), str(ROOT / "scripts/lemmasim"), *arguments]
        self.commands.write(json.dumps(command) + "\n")
        self.commands.flush()
        return subprocess.Popen(command, cwd=ROOT, **kwargs)

    def census(self):
        result = {}
        for path in self.censuses:
            if path.is_file():
                result.update(json.loads(path.read_text()))
        for module in list(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if filename:
                path = Path(filename).resolve()
                if path.suffix == ".py" and path.is_relative_to(ROOT) and path.is_file():
                    result[str(path.relative_to(ROOT))] = sha(path)
        result[str(Path(__file__).relative_to(ROOT))] = sha(__file__)
        return result

    def check_sources(self):
        require(all(sha(ROOT / path) == digest for path, digest in self.frozen.items()),
                "actual consumed host source changed")
        for path in self.censuses:
            if path.is_file():
                require(set(json.loads(path.read_text())) <= set(self.frozen),
                        "unannounced CLI import outside initial closure")

    def session(self, name, disk, fail_flush=None):
        session = super().session(name, disk, fail_flush)
        deadline = min(self.deadline, time.monotonic() + 5)
        while not self.censuses[-1].is_file():
            require(time.monotonic() < deadline, "missing child import census")
            time.sleep(0.02)
        if not self.frozen:
            self.frozen = self.census()
            self.check_sources()
            (self.directory / "consumed-host-inputs.json").write_text(
                json.dumps(self.frozen, sort_keys=True, indent=2) + "\n")
        return session

    def rows(self, session):
        return guest_events(session.directory / ("uart.bin" if self.backend == "rtl" else "uart-0.bin"))

    def quiet(self, state):
        return rtl_idle(state) if self.backend == "rtl" else idle(state)

    def completed(self, state):
        return state["panel_completed"] if self.backend == "rtl" else state["devices"]["paper"]["completed"]

    def until(self, session, name, cap, host, predicate):
        start = session.inspect()["machine"]["cycle"]
        began = time.monotonic()
        while True:
            self.check_sources()
            state = session.inspect()["machine"]
            used, elapsed = state["cycle"] - start, time.monotonic() - began
            require(elapsed <= host and used <= cap and self.total + used <= 3000000000,
                    "predeclared phase/aggregate bound: " + name)
            require(not state["finished"] and not any(row[0] in
                    (0x41f, 0xd4, 0xf4, 0x454, 0x424) for row in self.rows(session)),
                    "actual guest fault/error: " + name)
            if predicate(state):
                self.total += used
                phase = dict(name=name, initial_cycle=start, final_cycle=state["cycle"],
                             clock_units=used, host_seconds=elapsed)
                self.report["phases"].append(phase)
                (self.directory / "progress.json").write_text(
                    json.dumps(self.report, default=str, indent=2) + "\n")
                print(json.dumps(phase), flush=True)
                return state
            require(used < cap, "predeclared target cap: " + name)
            session.run(min(1000000, cap - used))

    def tap(self, session, stream, x, y):
        stream.tick = session.inspect()["machine"]["ticks"] + 10000
        first = len(stream.events)
        stream.sample(x, y, 0, False)
        stream.sample(x, y, 2048, True)
        stream.sample(x, y, 0, False)
        rows = stream.events[first:]
        session.admit(rows)
        return rows

    def rendered(self, session, name, reference=None):
        minimum = self.completed(session.inspect()["machine"])
        observed = -1
        panel = self.directory / (name + ".ppm")

        def predicate(state):
            nonlocal observed
            completed = self.completed(state)
            if not self.quiet(state) or completed <= minimum or observed == completed:
                return False
            observed = completed
            session.control({"action": "panel", "path": str(panel)})
            return (label_matches(panel, "SAVED    ") and course_body_matches(panel, self.body) and
                    (reference is None or visible_pixels(panel) == reference))

        return predicate

    def execute(self):
        original = self.args.disk
        disk = self.directory / "input.raw"
        shutil.copyfile(original, disk)
        session = self.session("live", disk)
        require(session.inspect()["machine"]["cycle"] == 0, "fresh CPU required")
        self.report["identity"] = session.identity
        rtl = self.backend == "rtl"
        boot_host, course_host = (7200, 3600) if rtl else (180, 180)

        def cold_ready(machine, state):
            return (self.quiet(state) and self.completed(state) > 0 and
                    any(row[0] == 0x420 for row in self.rows(machine)))

        self.until(session, "independent-cold-input", 1000000000, boot_host,
                   lambda state: cold_ready(session, state))
        stream = Input(1650, 2200, 0, 100000, 0)
        self.tap(session, stream, 320, 140)
        self.until(session, "actual-course-body", 400000000, course_host,
                   self.rendered(session, "opened-course"))
        before_ack, first = len(self.rows(session)), len(stream.events)
        stream.tick = session.inspect()["machine"]["ticks"] + 10000
        stream.stroke("course annotation", 1, 1, 3, 1400)
        raw = stream.events[first:]
        expected_annotation = annotation_pixels(
            visible_pixels(self.directory / "opened-course.ppm"), raw, self.brush_q8)
        self.report["independent_annotation"] = dict(
            brush_q8=self.brush_q8, all_pixels=1650 * 2200,
            expected_rgb_sha256=hashlib.sha256(expected_annotation[2]).hexdigest())
        session.admit(raw)
        rendered = self.rendered(session, "annotated-course", expected_annotation)
        self.until(session, "annotation-ack-and-SAVED-course", 200000000, 1800 if rtl else 180,
                   lambda state: state["ticks"] >= raw[-1][1] + 200000 and
                   any(row[0] == 0x421 for row in self.rows(session)[before_ack:]) and rendered(state))
        before_panel, before_medium = session.export("before-explicit-save")
        _, floor, records = recover(before_medium.read_bytes())
        samples = []
        for record in records.values():
            payload = record.payload
            if len(payload) >= 128 and struct.unpack_from("<3Q", payload) == (MAGIC, 1, 3):
                count = struct.unpack_from("<Q", payload, 48)[0]
                require(1 <= count <= 384 and len(payload) == 128 + count * 72,
                        "actual durable raw envelope bounds")
                samples.extend(struct.unpack_from("<9Q", payload, 128 + i * 72) for i in range(count))
        require(all(tuple(row) in samples for row in raw), "new raw annotation is not durable")
        self.report["actual_raw_samples"] = raw
        first_ack = len(self.rows(session))
        save_rows = self.tap(session, stream, 1372, 64)
        expected = expected_annotation
        require(visible_pixels(before_panel) == expected, "independent complete annotation pixels")
        rendered = self.rendered(session, "explicit-save-controller", expected)
        self.until(session, "idle-explicit-Save-detail0-identical-course", 60000000, 600 if rtl else 120,
                   lambda state: state["ticks"] >= save_rows[-1][1] + 200000 and
                   (0x421, floor, 1, 1, 0) in self.rows(session)[first_ack:] and rendered(state))
        _, after_medium = session.export("after-explicit-save")
        require(before_medium.read_bytes() == after_medium.read_bytes(), "status Save changed acknowledged data")
        require((0x423, floor, 1, 1, 0) in self.rows(session)[first_ack:], "explicit Save never published Pending")
        self.report["explicit_save"] = dict(sequence=floor, pending_and_saved_detail0=True,
                                            course_and_all_pixels_unchanged=True, all_medium_bytes_unchanged=True)
        session.close()
        self.sessions.remove(session)
        cold_disk = self.directory / "cold.raw"
        shutil.copyfile(after_medium, cold_disk)
        cold = self.session("cold", cold_disk)
        require(cold.inspect()["machine"]["cycle"] == 0, "second independent cold CPU required")
        self.until(cold, "second-new-CPU-cold-recovery", 1000000000, boot_host,
                   lambda state: cold_ready(cold, state))
        self.tap(cold, Input(1650, 2200, 0, 100000, 0), 320, 140)
        self.until(cold, "cold-complete-course-and-annotation-pixels", 400000000, course_host,
                   self.rendered(cold, "cold-reopened-course", expected))
        _, medium = cold.export("cold-final")
        require(after_medium.read_bytes() == medium.read_bytes(), "cold reopen changed acknowledged medium")
        require(sha(original) == self.report["source_medium_sha256"], "source medium changed")
        self.report.update(status="PASS_REAL_COURSE_ANNOTATION_IDLE_SAVE_COLD_REOPEN",
                           total_clock_units=self.total, second_cold=True, no_snapshot=True,
                           complete_controller_pixels_exact=True, whole_medium_exact=True)

    def finish(self):
        errors = []
        for session in self.sessions:
            try:
                session.close()
            except BaseException as error:
                errors.append(repr(error))
        # The CLI writes its final import census at exit. A late import must
        # fail admission even if the last guest phase already completed.
        try:
            self.check_sources()
        except BaseException as error:
            errors.append(repr(error))
        self.commands.close()
        self.report.update(elapsed_seconds=time.monotonic() - self.started, cleanup_errors=errors,
                           consumed_host_current_equal=bool(self.frozen) and
                           all(sha(ROOT / path) == digest for path, digest in self.frozen.items()))
        if errors or not self.report["consumed_host_current_equal"]:
            self.report["status"] = "FAIL"
        (self.directory / "result.json").write_text(json.dumps(self.report, default=str, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("qemu", "rtl"), required=True)
    for name in ("disk", "package", "work-dir", "guest-source-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("native-bundle", "guest-build"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    args.disk, args.package = args.disk.resolve(), args.package.resolve()
    args.timeout, args.deadline = 120, (21600 if args.backend == "rtl" else 900)
    args.durable_suffix_from, args.checkpoint_relation = None, "independent cold recovery only"
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    actor = CourseSave(args)
    try:
        actor.execute()
    except BaseException as error:
        actor.report.update(status="FAIL", error=repr(error))
        raise
    finally:
        actor.finish()
    require(actor.report["status"] == "PASS_REAL_COURSE_ANNOTATION_IDLE_SAVE_COLD_REOPEN",
            "course Save observer failed during finalization; see result.json")


if __name__ == "__main__":
    main()
