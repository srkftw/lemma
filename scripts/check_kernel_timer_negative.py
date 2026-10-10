#!/usr/bin/env python3
"""Observe the exact loss of preemption after an isolated call-5 timer mutation.

The maintained positive checker still fails. This controller accepts that
failure only after the three genuine user images have started and Busy remains
current without any scheduling interrupt. The failed inner Session and all raw
bytes are retained unchanged. No target source is written by this program.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import signal
import struct
import time
from types import SimpleNamespace

from build_core0 import prepare_output_directory
from build_kernel import source_inputs
from check_kernel import stop_controller_children, validate_session
from check_kernel_supervisor import validate_positive_records
from check_kernel_tasks import Trace, check as check_positive
from check_kernel_user import MASK, satp
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json
from run_kernel import RECORD_BYTES, Session, parse_record

FIRMWARE = "Lemma/Platform/RiscV/Firmware.lean"
READ_TIMEOUT = "device session timed out while reading fresh kernel record"
POSITIVE_RUNNERS = ("scripts/check_kernel_tasks.py", "scripts/check_kernel_supervisor.py",
                    "scripts/check_kernel_user.py", "scripts/check_kernel.py", "scripts/run_kernel.py",
                    "scripts/run_device_session.py", "scripts/run_monitor_session.py")
RUNNERS = (*POSITIVE_RUNNERS, "scripts/check_kernel_timer_negative.py")
BEFORE = """        if now ≤ 0xffffffffffffffff - payload then arm pc (now + payload)
"""
AFTER = """        if now ≤ 0xffffffffffffffff - payload then
          .bind (notify 0) fun s _ =>
          if failed s = true then .done s 0 else
          .bind (compare 0xffffffffffffffff) fun s _ =>
          if failed s = true then .done s 0 else
          .bind (write lastDeadlineAddress (now + payload)) fun s _ =>
          if failed s = true then .done s 0 else reply pc 0 (now + payload)
"""


def timer_disabled_source(original: str) -> str:
    """Return the single authorized source mutation, without writing a file."""
    if original.count(BEFORE) != 1 or AFTER in original:
        raise Core0Error("call5 success path does not match the closed timer mutation")
    return original.replace(BEFORE, AFTER, 1)


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in RUNNERS}


def source_binding(root: Path, expected_commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise Core0Error("timer mutation requires an exact forty-digit committed revision")

    def git(*args):
        result = run_bounded(("git", *args), cwd=root, timeout_seconds=30)
        if result.returncode:
            raise Core0Error("Git mutation binding command failed")
        return result.stdout

    if git("rev-parse", "HEAD").decode().strip() != expected_commit:
        raise Core0Error("timer mutation worktree HEAD differs from the selected F revision")
    dirty = git("status", "--porcelain=v1", "--untracked-files=all").decode().splitlines()
    if dirty != [" M " + FIRMWARE]:
        raise Core0Error("isolated negative worktree must change only the unstaged Firmware source")
    original = git("show", expected_commit + ":" + FIRMWARE)
    mutated = (root / FIRMWARE).read_bytes()
    if mutated != timer_disabled_source(original.decode()).encode():
        raise Core0Error("Firmware differs beyond the canonical call5 successful rearm mutation")
    sources = source_inputs(root)
    if not sources or FIRMWARE not in sources:
        raise Core0Error("timer mutation lacks its complete source inventory")
    entries = {}
    for row in git("ls-tree", "-rz", "HEAD").split(b"\0"):
        if row:
            metadata, name = row.split(b"\t", 1)
            entries[name.decode()] = metadata.decode().split()
    for name, digest in sources.items():
        entry = entries.get(name)
        if not entry or entry[:2] not in (["100644", "blob"], ["100755", "blob"]):
            raise Core0Error("timer source inventory contains an uncommitted or nonregular input")
        content = original if name == FIRMWARE else (root / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != entry[2] or digest != sha256(root / name):
            raise Core0Error("timer source inventory differs from the committed control tree")
    baseline = {**sources, FIRMWARE: hashlib.sha256(original).hexdigest()}
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise Core0Error("committed timer-control tree identity is malformed")
    return {"commit": expected_commit, "tree": tree, "source_inputs": sources,
            "control_source_inputs": baseline,
            "mutation": {"path": FIRMWARE, "before_sha256": baseline[FIRMWARE],
                         "after_sha256": sources[FIRMWARE], "changes": "call5-success-only",
                         "machine_compare": MASK, "reply_deadline": "actual-now-plus-payload",
                         "last_deadline": "actual-now-plus-payload",
                         "unchanged": ["call1", "arm", "timerInterrupt", "dispatch", "range-and-overflow-rejection"]}}


def positive_control(path: Path, binding: dict, root: Path, optimization: str) -> dict:
    value = load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("image"), str):
        raise Core0Error("passing F control report is missing its actual image")
    image = Path(value["image"])
    value = validate_session(path, image)
    provenance = load_json(image.parent / "provenance.json")
    audit = load_json(image.parent / "audit.json")
    if (value.get("source_inputs") != binding["control_source_inputs"]
            or provenance.get("source_inputs") != binding["control_source_inputs"]
            or provenance.get("source_commit") != binding["commit"] or provenance.get("dirty_paths") != []
            or (provenance.get("configuration"), provenance.get("stage"), provenance.get("optimization"))
            != ("tasks-development", "supervisor", optimization)
            or (audit.get("status"), audit.get("configuration"), audit.get("stage"))
            != ("PASS", "tasks-development", "supervisor")
            or audit.get("source_commit") != binding["commit"] or audit.get("dirty_paths") != []
            or value.get("observed", {}).get("protocol") != "preemptive-tasks-F-v1"
            or value.get("observed", {}).get("final_remaining_frames") != 499):
        raise Core0Error("positive F control does not bind the exact unchanged compiled source and profile")
    expected_runners = {name: sha256(root / name) for name in POSITIVE_RUNNERS}
    if (value.get("runner_inputs") != expected_runners
            or value.get("acceptance_checker_sha256") != expected_runners["scripts/check_kernel_tasks.py"]):
        raise Core0Error("positive F control uses different observation logic")
    tasks = value["observed"].get("tasks")
    if (not isinstance(tasks, dict) or not tasks
            or not any(task.get("image") == 0 and task.get("complete") is True
                       and task.get("arithmetic_preemptions") for task in tasks.values())):
        raise Core0Error("positive control lacks actual Compute arithmetic-loop preemption")
    return {"path": str(path), "sha256": sha256(path), "image": str(image),
            "image_sha256": value["image_sha256"], "audit_sha256": value["audit_sha256"],
            "provenance_sha256": value["provenance_sha256"], "source_inputs": value["source_inputs"],
            "reported_source_commit": provenance.get("source_commit"), "reported_dirty_paths": provenance.get("dirty_paths"),
            "selected_committed_control": binding["commit"],
            "source_binding": "exact-source-hashes-match-selected-commit", "runner_inputs": expected_runners}


def validate_stalled_runtime(records: list, sent: bytes, *, image: Path, audit: dict) -> dict:
    if (not isinstance(records, list) or len(records) < 15
            or any(not isinstance(row, list) or len(row) != 5
                   or any(type(word) is not int or not 0 <= word <= MASK for word in row) for row in records)
            or len(sent) != 40):
        raise Core0Error("timer negative lacks complete startup/task records and exactly one launch packet")
    command, *words = struct.unpack("<5Q", sent)
    nonces = words[:3]
    if command != 0x30 or words[3] != 0 or len(set(nonces)) != 3 or any(nonce in {0, MASK} for nonce in nonces):
        raise Core0Error("timer negative launch lacks three independent genuine image arguments")
    startup = validate_positive_records([tuple(row) for row in records[:4]])
    kernel, ready = tuple(records[4]), tuple(records[5])
    if kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0) or ready != (0xf0, 1, 8, 512, 10000):
        raise Core0Error("timer negative did not reach the ordinary F ready protocol")
    session = SimpleNamespace(binding=audit, image=image)
    trace = Trace(session)
    for index, nonce in enumerate(nonces):
        trace.expect_create(index, nonce)
    for row in records[6:]:
        trace.observe(tuple(row))
    if len(trace.tasks) != 3 or trace.creation_queue:
        raise Core0Error("timer negative did not publish all three requested image tasks")
    ids = list(trace.tasks)
    compute, sleeper, busy = (trace.tasks[id] for id in ids)
    if (not compute["start"] or compute["reasons"][2] != 1
            or not sleeper["start"] or sleeper["reasons"][3] != 1
            or busy["dispatches"] != 1 or trace.current != ids[2]
            or records[-1][:3] != [0xf3, ids[2], busy["root"]]
            or any(task["terminal"] is not None or task["reaped"] or task["reasons"][1] for task in trace.tasks.values())
            or compute["state"] != 2 or sleeper["state"] != 4 or busy["state"] != 3):
        raise Core0Error("timeout does not establish live Busy starvation after actual peer yield/sleep without preemption")
    return {"startup": startup, "kernel_root": list(kernel), "ready": list(ready),
            "task_ids": ids, "launch_nonces": nonces, "compute_yields": compute["reasons"][2],
            "sleeper_sleeps": sleeper["reasons"][3], "last_busy_dispatch": records[-1],
            "scheduling_interrupt_returns": 0, "compute_completion": "not_observed",
            "guest_state_at_deadline": "Busy-current-with-runnable-Compute-and-sleeping-Sleeper"}


def validate_failed_session(path: Path, image: Path, *, binding: dict, runners: dict) -> dict:
    value = load_json(path)
    if (not isinstance(value, dict) or value.get("status") != "FAIL" or value.get("error") != READ_TIMEOUT
            or value.get("failure_category") != "observation-failure" or value.get("timeout_seconds") != 8
            or value.get("guest_live_before_cleanup") is not True):
        raise Core0Error("inner positive checker did not fail specifically on the live missing-preemption deadline")
    expected_cleanup = {"explicit_host_stop": True, "process_group_killed": True,
                        "target_exited_before_cleanup": False, "process_reaped": True}
    if (value.get("cleanup") != expected_cleanup or any(type(flag) is not bool for flag in value["cleanup"].values())
            or value.get("returncode") != -9 or type(value.get("pid")) is not int or value["pid"] <= 0
            or Path("/proc", str(value["pid"])).exists()):
        raise Core0Error("negative guest was not alive until explicit kill, reaped and absent after cleanup")
    provenance = load_json(image.parent / "provenance.json")
    audit = load_json(image.parent / "audit.json")
    if (value.get("image_sha256") != sha256(image)
            or value.get("audit_sha256") != sha256(image.parent / "audit.json")
            or value.get("provenance_sha256") != sha256(image.parent / "provenance.json")
            or value.get("source_inputs") != binding["source_inputs"]
            or provenance.get("source_inputs") != binding["source_inputs"]
            or (provenance.get("configuration"), provenance.get("stage")) != ("tasks-development", "supervisor")
            or (audit.get("status"), audit.get("configuration"), audit.get("stage")) != ("PASS", "tasks-development", "supervisor")
            or value.get("runner_inputs") != runners):
        raise Core0Error("failed guest image/audit/provenance/source/runner binding differs")
    raw = value.get("raw_artifacts")
    if not isinstance(raw, dict) or set(raw) != {"received.bin", "sent.bin", "stderr.bin"}:
        raise Core0Error("negative guest raw evidence inventory is missing or unexpected")
    for name, digest in raw.items():
        if sha256(path.parent / name) != digest:
            raise Core0Error("negative guest raw bytes changed after the observed failure")
    if (path.parent / "stderr.bin").read_bytes():
        raise Core0Error("timer negative has unexpected QEMU stderr")
    received = (path.parent / "received.bin").read_bytes()
    records = value.get("records")
    if (not isinstance(records, list) or len(received) != RECORD_BYTES * len(records)
            or [list(parse_record(received[i:i+RECORD_BYTES])) for i in range(0, len(received), RECORD_BYTES)] != records):
        raise Core0Error("negative raw transcript has incomplete, unexplained or unvalidated trailing bytes")
    facts = validate_stalled_runtime(records, (path.parent / "sent.bin").read_bytes(), image=image, audit=audit)
    return {"path": str(path), "sha256": sha256(path), "status": "FAIL", "error": value["error"],
            "pid": value["pid"], "returncode": value["returncode"], "cleanup": value["cleanup"],
            "raw_artifacts": raw, "record_count": len(records), "observed": facts}


def run(*, root: Path, image: Path, output_dir: Path, control: Path,
        expected_commit: str, timeout: float = 8, clean: bool = False) -> dict:
    root, image, output_dir, control = (path.resolve() for path in (root, image, output_dir, control))
    try:
        relative = output_dir.relative_to(root / "build/kernel")
    except ValueError as error:
        raise Core0Error("timer negative output must be a build/kernel subdirectory") from error
    if not relative.parts or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout != 8:
        raise Core0Error("timer negative requires a dedicated output and exactly eight-second live observation")
    prepare_output_directory(output_dir, root, clean=clean)
    begin = time.monotonic()
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "development-F-timer-disabled-negative",
              "protocol": "timer-disabled-F-v1", "image": str(image), "timeout_seconds": timeout,
              "started_at": datetime.now(timezone.utc).isoformat(), "inner_positive_checker_status": "not_run"}
    try:
        binding, runners = source_binding(root, expected_commit), runner_inputs(root)
        provenance = load_json(image.parent / "provenance.json")
        if provenance.get("source_inputs") != binding["source_inputs"]:
            raise Core0Error("mutant image was not constructed from the exactly bound mutation source")
        control_binding = positive_control(control, binding, root, provenance.get("optimization"))
        report.update(source=binding, runner_inputs=runners, positive_control=control_binding)
        try:
            with Session(root=root, image=image, output_dir=output_dir / "inner-session", timeout=timeout) as session:
                session.report.update(runner_inputs=runners, acceptance_checker_sha256=runners["scripts/check_kernel_tasks.py"],
                                      protocol="positive-F-checker-on-timer-disabled-image")
                try:
                    check_positive(session)
                except Core0Error:
                    session.report["guest_live_before_cleanup"] = session.process.poll() is None
                    raise
                raise Core0Error("timer-disabled image unexpectedly completed the positive F protocol")
        except Core0Error:
            # The exact failure text, runtime prefix and cleanup are checked
            # only after Session has retained its complete unmodified failure.
            pass
        failed = validate_failed_session(output_dir / "inner-session/result.json", image, binding=binding, runners=runners)
        if (source_binding(root, expected_commit) != binding or runner_inputs(root) != runners
                or positive_control(control, binding, root, provenance.get("optimization")) != control_binding):
            raise Core0Error("negative mutation source, runner or positive control changed during the observation")
        report.update(status="PASS", inner_positive_checker_status="FAIL", inner_session=failed,
                      source_unchanged_after=True, runners_unchanged_after=True,
                      observed_expected_failure="missing-preemption-after-genuine-three-image-startup")
    except (Core0Error, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        report.update(error=str(error), failure_category="timer-negative-evidence-failure")
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic() - begin)
        temporary = output_dir / "result.json.tmp"
        write_json(temporary, report)
        temporary.replace(output_dir / "result.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--positive-control", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--timeout", type=float, default=8)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    previous = {}

    def interrupted(signum, _frame):
        stop_controller_children(defer_qemu=True)
        raise Core0Error(f"timer negative controller interrupted by signal {signum}")

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupted)
        report = run(root=repo_root(), image=args.image, output_dir=args.output_dir, control=args.positive_control,
                     expected_commit=args.expected_commit, timeout=args.timeout, clean=args.clean)
        if report["status"] != "PASS":
            raise Core0Error(report.get("error", "timer negative failed"))
        print("PASS: bound timer mutation lost preemption; failed live guest retained, killed and reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1
    finally:
        stop_controller_children()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
