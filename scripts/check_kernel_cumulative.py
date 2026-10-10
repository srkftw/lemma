#!/usr/bin/env python3
"""Fresh, bounded clean-source Task003 F-I or service-J acceptance lane.

The A-E controller remains a separate mandatory regression lane. Each selected
case here builds a new production artifact and runs its maintained observer;
old reports, missing cases and stale inputs cannot satisfy this controller.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib
import io
import math
from pathlib import Path
import signal
import sys
import time

from build_core0 import prepare_output_directory
from build_kernel import build, source_inputs
from check_kernel import (acceptance_inputs, source_identity,
                          stop_controller_children, validate_session)
from core0_common import (Core0Error, load_json, repo_root, require_tools,
                         sha256, write_json)


LANES = {
    "F-I": (
        ("F", "tasks-development", "check_kernel_tasks", "preemptive-tasks-F-v1", 120),
        ("G", "tasks-fault-development", "check_kernel_lifecycle", "lifecycle-G-v1", 120),
        ("H", "capabilities-development", "check_kernel_capabilities", "capabilities-H-v1", 120),
        ("I", "ipc-development", "check_kernel_ipc", "ipc-I-v1", 180),
    ),
    "J": (
        ("J-normal", "service-normal", "check_kernel_buffer", "buffer-service-J-v1", 300),
        ("J-development", "service-development", "check_kernel_buffer", "buffer-service-J-v1", 300),
    ),
}


def plan(lane: str) -> tuple:
    if lane not in LANES:
        raise Core0Error("unknown closed Task003 acceptance lane")
    return tuple((*case, optimization) for case in LANES[lane]
                 for optimization in ("O0", "O2"))


def _check_deadline(finish_by):
    if finish_by is not None and time.monotonic() >= finish_by:
        raise Core0Error("Task003 cumulative lane deadline expired")


def validate_lane(path: Path, root: Path, *, finish_by=None) -> dict:
    """Require every mandatory bound artifact and observed session again."""
    _check_deadline(finish_by)
    value = load_json(path)
    if (not isinstance(value, dict)
            or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or value.get("artifact_category") != "kernel-clean-cumulative-lane"
            or type(value.get("deadline_seconds")) not in (int, float)
            or not math.isfinite(value["deadline_seconds"]) or not 0 < value["deadline_seconds"] <= 2400
            or type(value.get("elapsed_seconds")) not in (int, float)
            or not math.isfinite(value["elapsed_seconds"]) or not 0 <= value["elapsed_seconds"] <= value["deadline_seconds"]
            or value.get("status") != "PASS"
            or value.get("source") != source_identity(root)
            or value.get("source_inputs") != source_inputs(root)
            or value.get("acceptance_inputs") != acceptance_inputs(root)
            or value.get("source_unchanged_after") is not True
            or value.get("acceptance_unchanged_after") is not True):
        raise Core0Error("lane result is missing, failing or bound to different source")
    expected = plan(value.get("lane"))
    rows = value.get("cases")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise Core0Error("mandatory Task003 case corpus is incomplete")
    for row, case in zip(rows, expected):
        _check_deadline(finish_by)
        gate, configuration, module, protocol, _, optimization = case
        if (not isinstance(row, dict) or (row.get("gate"), row.get("configuration"), row.get("optimization"))
                != (gate, configuration, optimization) or row.get("checker") != module
                or type(row.get("returncode")) is not int or row["returncode"] != 0):
            raise Core0Error("lane case identity or actual checker result differs")
        image, observed = Path(row["image"]), Path(row["result"])
        for key, artifact in (("image_sha256", image), ("result_sha256", observed),
                              ("audit_sha256", image.parent / "audit.json"),
                              ("provenance_sha256", image.parent / "provenance.json"),
                              ("log_sha256", Path(row["log"]))):
            if not artifact.is_file() or sha256(artifact) != row.get(key):
                raise Core0Error("mandatory lane evidence is missing or changed")
        provenance = load_json(image.parent / "provenance.json")
        if (provenance.get("source_commit") != value["source"]["commit"]
                or provenance.get("dirty_paths") != []
                or provenance.get("source_inputs") != value["source_inputs"]
                or (provenance.get("configuration"), provenance.get("optimization"), provenance.get("stage"))
                != (configuration, optimization, "supervisor")):
            raise Core0Error("fresh lane artifact has stale or different provenance")
        session = validate_session(observed, image)
        _check_deadline(finish_by)
        if session.get("observed", {}).get("protocol") != protocol:
            raise Core0Error("lane session did not execute the required maintained protocol")
    _check_deadline(finish_by)
    return value


def check(*, root: Path, work_dir: Path, lane: str, clean: bool,
          timeout: float, deadline: float) -> dict:
    root = root.resolve()
    work_dir = (root / work_dir).resolve()
    if (any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in (timeout, deadline))
            or timeout > 600 or deadline > 2400):
        raise Core0Error("finite build timeout<=600 and lane deadline<=2400 required")
    try:
        relative = work_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("lane evidence must be a build/kernel subdirectory") from error
    if not relative.parts:
        raise Core0Error("refusing to replace all kernel evidence")
    cases = plan(lane)
    identity = source_identity(root)
    prepare_output_directory(work_dir, root, clean=clean)
    logs = work_dir / "logs"; logs.mkdir()
    started = time.monotonic(); finish_by = started + deadline
    report = {"schema_version": 1, "status": "FAIL", "lane": lane,
              "artifact_category": "kernel-clean-cumulative-lane",
              "started_at": datetime.now(timezone.utc).isoformat(),
              "deadline_seconds": deadline, "cases": [], "source": identity}

    def remaining():
        left = finish_by - time.monotonic()
        if left <= 0:
            raise Core0Error("Task003 cumulative lane deadline expired")
        return left

    try:
        require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld",
                       "llvm-objdump", "qemu-system-riscv64", "dtc"))
        sources, consumers = source_inputs(root), acceptance_inputs(root)
        report.update(source_inputs=sources, acceptance_inputs=consumers)
        for gate, configuration, module_name, protocol, guest_bound, optimization in cases:
            if remaining() < guest_bound + 60:
                raise Core0Error("insufficient deadline for the complete next guest protocol")
            label = gate + "-" + optimization
            artifact, observed = work_dir / label, work_dir / (label + "-run")
            result = build(root=root, output_dir=artifact, opt_level=optimization,
                           stage="supervisor", configuration=configuration,
                           timeout_seconds=min(timeout, remaining()))
            image = artifact / "image.elf"
            if result.get("status") != "BUILT" or not image.is_file() or not image.stat().st_size:
                raise Core0Error("fresh lane build did not produce a complete image")
            provenance = load_json(artifact / "provenance.json")
            if (provenance.get("source_commit") != identity["commit"] or provenance.get("dirty_paths")
                    or provenance.get("source_inputs") != sources):
                raise Core0Error("lane image source differs from its clean controller source")
            module = importlib.import_module(module_name)
            argv = [str(module.__file__), "--image", str(image), "--output-dir", str(observed),
                    "--timeout", str(min(guest_bound, remaining()))]
            previous, captured, code = sys.argv, io.StringIO(), None
            try:
                sys.argv = argv
                with redirect_stdout(captured), redirect_stderr(captured):
                    code = module.main()
            finally:
                sys.argv = previous
                log = logs / (label + ".log"); log.write_text(captured.getvalue())
            row = {"gate": gate, "configuration": configuration, "optimization": optimization,
                   "checker": module_name, "argv": argv, "returncode": code,
                   "image": str(image), "image_sha256": sha256(image),
                   "audit_sha256": sha256(artifact / "audit.json"),
                   "provenance_sha256": sha256(artifact / "provenance.json"),
                   "result": str(observed / "result.json"),
                   "log": str(log), "log_sha256": sha256(log)}
            report["cases"].append(row)
            if type(code) is not int or code != 0:
                raise Core0Error(f"fresh {label} actual guest protocol failed")
            session = validate_session(observed / "result.json", image)
            if session.get("observed", {}).get("protocol") != protocol:
                raise Core0Error("actual lane protocol identity differs")
            row.update(result_sha256=sha256(observed / "result.json"),
                       records=len(session["records"]), status="PASS")
            remaining()
        if source_identity(root) != identity or source_inputs(root) != sources or acceptance_inputs(root) != consumers:
            raise Core0Error("lane source or acceptance consumers changed during execution")
        remaining()
        report.update(status="PASS", source_unchanged_after=True, acceptance_unchanged_after=True)
    except Exception as error:
        report.update(error=str(error))
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(work_dir / "result.json.tmp", report)
        (work_dir / "result.json.tmp").replace(work_dir / "result.json")
    if report["status"] == "PASS":
        try:
            validate_lane(work_dir / "result.json", root, finish_by=finish_by)
            remaining()
            report["elapsed_seconds"] = time.monotonic() - started
            write_json(work_dir / "result.json.tmp", report)
            (work_dir / "result.json.tmp").replace(work_dir / "result.json")
            remaining()
        except Exception as error:
            report.update(status="FAIL", error=str(error), failure_category="mandatory-lane-evidence",
                          elapsed_seconds=time.monotonic() - started)
            write_json(work_dir / "result.json.tmp", report)
            (work_dir / "result.json.tmp").replace(work_dir / "result.json")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=tuple(LANES), required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--deadline", type=float, default=2400)
    args = parser.parse_args()

    def interrupted(number, _):
        stop_controller_children(defer_qemu=True)
        raise Core0Error(f"cumulative kernel controller interrupted by signal{number}")

    old = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    for number in old:
        signal.signal(number, interrupted)
    try:
        value = check(root=repo_root(), work_dir=args.work_dir, lane=args.lane,
                      clean=args.clean, timeout=args.timeout, deadline=args.deadline)
        print(value["status"] + ": " + value.get("error", "fresh clean " + args.lane + " acceptance"))
        return 0 if value["status"] == "PASS" else 1
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print("FAIL: " + str(error)); return 1
    finally:
        for number, handler in old.items():
            signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
