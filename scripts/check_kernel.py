#!/usr/bin/env python3
"""Bounded clean-source acceptance of the implemented Task 003 A-D prefix.

Existing builders, artifact audits and guest checkers supply every result.
This orchestrator neither implements target policy nor qualifies later gates.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib
import io
import math
import os
from pathlib import Path
import re
import signal
import sys
import time

from build_core0 import prepare_output_directory
from build_kernel import build, source_inputs
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from run_kernel import RECORD_BYTES, parse_record

QUARANTINE = ("user-isolation-development", "user-csr-development", "user-nx-development",
              "user-kernel-fetch-development", "user-misaligned-development")


def stop_controller_children(*, defer_qemu: bool = False) -> list[dict]:
    """Kill and reap only this Linux controller's own live child processes.

    Tool commands use independent process groups. An exception raised during
    communicate() must not leave those groups running after this controller
    reports interruption; ordinary completion still uses the existing helpers.
    """
    own_pid = os.getpid()
    children = Path(f"/proc/{own_pid}/task/{own_pid}/children")
    pids = [int(value) for value in children.read_text().split()]
    rows = []
    for pid in pids:
        if defer_qemu:
            try:
                argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            except FileNotFoundError:
                argv = []
            if any(Path(os.fsdecode(word)).name == "qemu-system-riscv64" for word in argv if word):
                # The maintained guest runner owns this Popen's wait status
                # and records live/stop/reap facts during context unwinding.
                rows.append({"pid": pid, "deferred_to_guest_runner": True})
                continue
        row = {"pid": pid, "explicit_host_stop": False, "process_reaped": False}
        try:
            group = os.getpgid(pid)
            if group == pid:
                os.killpg(group, signal.SIGKILL)
                row["process_group_killed"] = True
            else:
                os.kill(pid, signal.SIGKILL)
                row["process_group_killed"] = False
            row["explicit_host_stop"] = True
        except ProcessLookupError:
            row["already_exited"] = True
        try:
            waited, status = os.waitpid(pid, 0)
            row.update(process_reaped=waited == pid, returncode=os.waitstatus_to_exitcode(status))
        except ChildProcessError:
            row["already_reaped"] = True
        rows.append(row)
    return rows


def matrix() -> tuple[tuple[str, str, str], ...]:
    return tuple((configuration, stage, optimization) for optimization in ("O0", "O2")
                 for configuration, stage in (("normal", "bootstrap-m"), ("normal", "supervisor"),
                                               ("frames-development", "bootstrap-m"),
                                               ("machine-origin-development", "bootstrap-m"),
                                               *((case, "supervisor") for case in QUARANTINE)))


def source_identity(root: Path) -> dict:
    def git(*args):
        result = run_bounded(("git", *args), cwd=root, timeout_seconds=30)
        if result.returncode:
            raise Core0Error("Git source identity command failed")
        return result.stdout.decode().strip()
    commit, tree, dirty = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}"), git("status", "--porcelain=v1", "--untracked-files=all")
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(r"[0-9a-f]{40}", tree) or dirty:
        raise Core0Error("Task003 qualification requires an exact committed clean source revision")
    return {"commit": commit, "tree": tree, "clean": True}


def acceptance_inputs(root: Path) -> dict:
    paths = {root / ".github/workflows/core0.yml", root / "scripts/check_kernel.py", root / "scripts/run_kernel.py",
             root / "scripts/run_device_session.py", root / "scripts/run_monitor_session.py"}
    paths.update((root / "scripts").glob("check_kernel_*.py"))
    paths.update((root / "tests/kernel").rglob("*.py"))
    return {str(path.relative_to(root)): sha256(path) for path in sorted(paths)}


def validate_session(path: Path, image: Path, *, machine_origin: bool = False) -> dict:
    value = load_json(path)
    if not isinstance(value, dict) or value.get("status") != "PASS" or value.get("image_sha256") != sha256(image):
        raise Core0Error(f"missing/failing or unbound guest observation: {path}")
    if value.get("audit_sha256") != sha256(image.parent / "audit.json") or value.get("provenance_sha256") != sha256(image.parent / "provenance.json"):
        raise Core0Error("guest audit/provenance binding differs")
    provenance = load_json(image.parent / "provenance.json")
    if not isinstance(value.get("source_inputs"), dict) or not value["source_inputs"] or value["source_inputs"] != provenance.get("source_inputs"):
        raise Core0Error("guest source hash inventory is missing or differs")
    cleanup = value.get("cleanup", {})
    if not isinstance(cleanup, dict) or cleanup.get("process_reaped") is not True or type(value.get("pid")) is not int or Path("/proc", str(value["pid"])).exists():
        raise Core0Error("guest process lacks observed cleanup/reaping")
    if machine_origin:
        if (value.get("returncode") != 48 or value.get("trace_observed") is not True or value.get("actual_trap", {}).get("cause") != 11
                or cleanup.get("explicit_host_stop") is not False or value.get("target_exited_before_cleanup") is not True):
            raise Core0Error("machine-origin fixture lacks its actual trap and fatal48 exit")
    elif (value.get("returncode") != -9 or value.get("guest_live_before_cleanup") is not True
          or cleanup.get("explicit_host_stop") is not True or cleanup.get("process_group_killed") is not True
          or cleanup.get("target_exited_before_cleanup") is not False
          or not isinstance(value.get("records"), list) or not value["records"]):
        raise Core0Error("positive guest lacks records, live observation and explicit cleanup")
    raw = value.get("raw_artifacts")
    if not isinstance(raw, dict) or not {"received.bin", "sent.bin", "stderr.bin"} <= set(raw):
        raise Core0Error("guest raw evidence inventory is missing")
    for name, digest in raw.items():
        if not isinstance(name, str) or Path(name).name != name or sha256(path.parent / name) != digest:
            raise Core0Error("guest raw evidence is missing or changed")
    if (path.parent / "stderr.bin").read_bytes():
        raise Core0Error("unexpected guest stderr")
    received = (path.parent / "received.bin").read_bytes()
    if machine_origin:
        from check_kernel_supervisor import validate_machine_origin_trace
        trace = path.parent / "qemu-interrupt-trace.txt"
        if received or (path.parent / "sent.bin").read_bytes() or "qemu-interrupt-trace.txt" not in raw:
            raise Core0Error("machine-origin raw UART/trace evidence differs")
        validate_machine_origin_trace(trace.read_text(), expected_pc=value["audited_ecall_pc"])
    elif (len(received) != RECORD_BYTES * len(value["records"])
          or [list(parse_record(received[index:index+RECORD_BYTES])) for index in range(0, len(received), RECORD_BYTES)] != value["records"]):
        raise Core0Error("raw guest packet bytes differ from recorded observations")
    return value


def check(*, root: Path, work_dir: Path, clean: bool, timeout: float, qemu_timeout: float, deadline: float) -> dict:
    try:
        relative = work_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("Task003 evidence must be a build/kernel subdirectory") from error
    if not relative.parts:
        raise Core0Error("refusing to replace all kernel evidence")
    if any(isinstance(number, bool) or not math.isfinite(number) or number <= 0 for number in (timeout, qemu_timeout, deadline)) or deadline > 2400:
        raise Core0Error("timeouts must be finite/positive and cumulative deadline at most40minutes")
    prepare_output_directory(work_dir, root, clean=clean)
    started = time.monotonic(); finish_by = started + deadline
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "kernel-A-D-clean-acceptance",
              "started_at": datetime.now(timezone.utc).isoformat(), "required_gate_prefix": "A-D", "highest_exercised_gate": "not_run",
              "later_gates": {gate: "not_run" for gate in "EFGHIJK"}, "deadline_seconds": deadline,
              "invocations": [], "images": [], "observations": []}
    logs = work_dir / "logs"; logs.mkdir()

    def remaining() -> float:
        left = finish_by - time.monotonic()
        if left <= 0:
            raise Core0Error("cumulative Task003 acceptance deadline expired")
        return left

    def cli(module_name: str, args: list[str], label: str, *, session_count: int = 1) -> None:
        # Run the maintained CLI in this process so an external TERM unwinds
        # its Session context and kills/reaps QEMU before reporting failure.
        if remaining() < session_count * qemu_timeout + 120:
            raise Core0Error("insufficient remaining deadline for a complete bounded guest protocol")
        argv = [str(root / "scripts" / (module_name + ".py")), *args]
        previous = sys.argv; captured = io.StringIO(); begin = time.monotonic(); result = None
        try:
            sys.argv = argv
            with redirect_stdout(captured), redirect_stderr(captured):
                result = importlib.import_module(module_name).main()
        finally:
            sys.argv = previous
            log = logs / (label + ".log"); log.write_text(captured.getvalue())
            report["invocations"].append({"execution": "in-process maintained CLI", "argv": argv,
                                          "returncode": result, "elapsed_seconds": time.monotonic() - begin,
                                          "log": str(log.relative_to(root)), "log_sha256": sha256(log)})
        if type(result) is not int or result != 0:
            raise Core0Error(f"maintained checker failed: {label}; see {log}")

    try:
        require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld", "llvm-objdump", "qemu-system-riscv64", "dtc"))
        identity, sources, consumers = source_identity(root), source_inputs(root), acceptance_inputs(root)
        report.update(source=identity, source_inputs=sources, acceptance_inputs=consumers)
        for label, argv in (("lake-build", ("lake", "build")),
                            ("kernel-host", (sys.executable, "-m", "unittest", "discover", "-s", "tests/kernel", "-v"))):
            result = run_bounded(argv, cwd=root, timeout_seconds=min(timeout, remaining()))
            log = logs / (label + ".log"); log.write_bytes(result.stdout + result.stderr)
            report["invocations"].append({"execution": "subprocess", "argv": list(result.argv), "returncode": result.returncode,
                                          "log": str(log.relative_to(root)), "log_sha256": sha256(log)})
            if result.returncode:
                raise Core0Error(f"required {label} command failed")
            if label == "kernel-host":
                count = re.search(rb"Ran ([0-9]+) tests?", result.stdout + result.stderr)
                if not count or int(count[1]) <= 0:
                    raise Core0Error("kernel host corpus is missing or empty")
                report["host_tests"] = int(count[1])
        plan = matrix()
        if len(plan) != 18 or len(set(plan)) != 18:
            raise Core0Error("required Task003 configuration matrix is incomplete")
        for configuration, stage, optimization in plan:
            label = f"{configuration}-{stage}-{optimization}"
            directory = work_dir / label
            built = build(root=root, output_dir=directory, opt_level=optimization, stage=stage,
                          configuration=configuration, timeout_seconds=min(timeout, remaining()))
            image = directory / "image.elf"
            if built.get("status") != "BUILT" or not image.is_file() or not image.stat().st_size:
                raise Core0Error("required image/build report is missing")
            provenance = load_json(directory / "provenance.json")
            if provenance.get("source_commit") != identity["commit"] or provenance.get("dirty_paths") or provenance.get("source_inputs") != sources:
                raise Core0Error("fresh image source identity differs from clean acceptance source")
            if configuration == "normal" and stage == "bootstrap-m":
                checkers = (("check_kernel_bootinfo", [], "bootinfo", 3),)
            elif configuration == "normal":
                checkers = (("check_kernel_user", [], "user", 1),)
            elif configuration == "frames-development":
                checkers = (("check_kernel_frames", [], "frames", 1),
                            ("check_kernel_frames", ["--address-space"], "address-space", 1),
                            ("check_kernel_loader", [], "loader", 1))
            elif configuration == "machine-origin-development":
                checkers = (("check_kernel_supervisor", ["--case", "machine-origin"], "machine-origin", 1),)
            else:
                checkers = (("check_kernel_isolation", [], "isolation", 1),)
            for module, extra, role, count in checkers:
                output = work_dir / (label + "-" + role)
                cli(module, ["--image", str(image), "--output-dir", str(output), "--timeout", str(qemu_timeout), *extra],
                    label + "-" + role, session_count=count)
                value = load_json(output / "result.json")
                if role == "bootinfo":
                    if value.get("status") != "PASS" or [row.get("kind") for row in value.get("cases", [])] != ["ordinary", "reserved-pool", "root-cells"]:
                        raise Core0Error("bootinfo result corpus is missing/incomplete")
                    for row in value["cases"]:
                        child = Path(row["result"])
                        if row.get("result_sha256") != sha256(child):
                            raise Core0Error("bootinfo child report hash differs")
                        validate_session(child, image)
                else:
                    validate_session(output / "result.json", image, machine_origin=role == "machine-origin")
                report["observations"].append({"configuration": configuration, "stage": stage, "optimization": optimization,
                                               "role": role, "result": str((output / "result.json").relative_to(root)),
                                               "sha256": sha256(output / "result.json"), "status": "PASS"})
            artifact_audit = load_json(directory / "audit.json")
            if artifact_audit.get("status") != "PASS" or artifact_audit.get("source_commit") != identity["commit"] or artifact_audit.get("image_sha256") != sha256(image):
                raise Core0Error("mandatory full artifact audit is missing or stale")
            report["images"].append({"configuration": configuration, "stage": stage, "optimization": optimization,
                                     "image": str(image.relative_to(root)), "sha256": sha256(image),
                                     "audit_sha256": sha256(directory / "audit.json"), "provenance_sha256": sha256(directory / "provenance.json")})
        if len(report["images"]) != 18 or len(report["observations"]) != 22:
            raise Core0Error("Task003 image/observation matrix did not complete")
        if source_identity(root) != identity or source_inputs(root) != sources or acceptance_inputs(root) != consumers:
            raise Core0Error("acceptance source/consumer changed during qualification")
        remaining(); report.update(status="PASS", highest_exercised_gate="D")
        report["limitations"] = ["Fresh clean acceptance of the implemented A-D prefix; not completion of Task003.",
                                  "Gates E-J and full-milestone GateK remain unfinished.",
                                  "Legacy and Task002 cumulative acceptance are separate mandatory workflow jobs."]
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report.update(elapsed_seconds=time.monotonic() - started, finished_at=datetime.now(timezone.utc).isoformat())
        write_json(work_dir / "result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--work-dir", type=Path, default=Path("build/kernel/qualification"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--qemu-timeout", type=float, default=90)
    parser.add_argument("--deadline", type=float, default=2400)
    args = parser.parse_args()
    interruption = None
    def terminate(_signum, _frame):
        nonlocal interruption
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        stopped = stop_controller_children(defer_qemu=True)
        interruption = {"signal": _signum, "children": stopped}
        output = (repo_root() / args.work_dir).resolve()
        if output.is_dir() and output.is_relative_to((repo_root() / "build/kernel").resolve()):
            write_json(output / "interruption-cleanup.json", interruption)
        raise Core0Error("Task003 acceptance interrupted by host termination")
    previous = signal.signal(signal.SIGTERM, terminate)
    previous_alarm = signal.signal(signal.SIGALRM, terminate)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    try:
        if math.isfinite(args.deadline) and 0 < args.deadline <= 2400:
            signal.setitimer(signal.ITIMER_REAL, args.deadline)
        root = repo_root()
        value = check(root=root, work_dir=(root / args.work_dir).resolve(), clean=args.clean,
                      timeout=args.timeout, qemu_timeout=args.qemu_timeout, deadline=args.deadline)
        print(f"PASS: clean Task003 A-D prefix, {len(value['images'])} images, {len(value['observations'])} checker reports")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1
    finally:
        if interruption is not None:
            # After maintained guest contexts unwind, reap any unowned child
            # left by interruption during process construction or a tool call.
            interruption["remaining_children_after_unwind"] = stop_controller_children()
            output = (repo_root() / args.work_dir).resolve()
            if output.is_dir() and output.is_relative_to((repo_root() / "build/kernel").resolve()):
                write_json(output / "interruption-cleanup.json", interruption)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_alarm)
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
