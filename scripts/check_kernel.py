#!/usr/bin/env python3
"""Bounded clean-source acceptance of the implemented Task 003 A-E prefix.

Existing builders, artifact audits and guest checkers supply every result.
This orchestrator neither implements target policy nor qualifies later gates.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time

from build_core0 import prepare_output_directory
from build_kernel import build, source_inputs
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from run_kernel import RECORD_BYTES, parse_record, validate_reaped_process

ROW_SUPERVISORS: dict[int, subprocess.Popen] = {}

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
                                               *((case, "supervisor") for case in QUARANTINE),
                                               ("user-syscall-development", "supervisor")))


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
    paths = {root / ".github/workflows/core0.yml", root / "scripts/check_kernel.py", root / "scripts/kernel_row_supervisor.py", root / "scripts/run_kernel.py",
             root / "scripts/run_device_session.py", root / "scripts/run_monitor_session.py", root / "scripts/host_prerequisites.py",
             *(root / "scripts" / name for name in ("buffer_transport.py", "run_buffer_session.py", "buffer-cli.py", "buffer_reference.py"))}
    paths.update((root / "scripts").glob("check_kernel_*.py"))
    paths.update((root / "tests/kernel").rglob("*.py"))
    paths.update((root / "tests/kernel").rglob("*.json"))
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
    validate_reaped_process(value)
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
    elif value.get("wire_format") == "kernel-mixed-uart-v1":
        if provenance.get("configuration") != "user-syscall-development" or value.get("observed", {}).get("protocol") != "user-E-syscalls-v1":
            raise Core0Error("mixed UART grammar is scoped to the exact E syscall observation")
        from check_kernel_syscall import validate_wire_segments
        validate_wire_segments(received, value["records"], value.get("wire_segments"))
    elif value.get("wire_format") == "kernel-buffer-uart-v1":
        from run_buffer_session import validate_quiescence
        validate_quiescence(value, received, (path.parent / "stderr.bin").read_bytes())
        if value.get("observed", {}).get("protocol") == "architectural-containment-K-v1":
            from check_kernel_architecture import CONFIGURATIONS, validate_replay, runner_inputs
            root = repo_root()
            if (provenance.get("configuration") not in CONFIGURATIONS
                    or value.get("architecture_runner_inputs") != runner_inputs(root)
                    or value.get("architecture_runner_inputs_after") != value["architecture_runner_inputs"]
                    or value.get("source_inputs_after") != value["source_inputs"]
                    or value.get("image_sha256_after") != value["image_sha256"]
                    or value.get("audit_sha256_after") != value["audit_sha256"]
                    or value.get("provenance_sha256_after") != value["provenance_sha256"]
                    or value.get("observed", {}).get("complete_semantic_replay") is not True
                    or validate_replay(root, image.resolve(), value, path.parent) != value["observed"]):
                raise Core0Error("architecture full semantic/site/source replay differs")
        elif (provenance.get("configuration") not in {"service-normal", "service-development"}
                or value.get("observed", {}).get("protocol") != "buffer-service-J-v1"
                or value.get("observed", {}).get("complete_semantic_replay") is not True):
            raise Core0Error("Buffer UART grammar requires its exact source-bound complete J observation")
        else:
            from check_kernel_buffer import validate_replay, runner_inputs
            root = repo_root()
            if (value.get("service_runner_inputs") != runner_inputs(root)
                    or value.get("service_runner_inputs_after") != value["service_runner_inputs"]):
                raise Core0Error("service acceptance runner/reference inventory is missing or changed")
            replayed = validate_replay(root, image, value, path.parent)
            if replayed != value["observed"]:
                raise Core0Error("service complete semantic replay differs from retained observations")
    elif value.get("wire_format") is not None:
        raise Core0Error("unknown guest UART evidence format")
    elif (len(received) != RECORD_BYTES * len(value["records"])
          or [list(parse_record(received[index:index+RECORD_BYTES])) for index in range(0, len(received), RECORD_BYTES)] != value["records"]):
        raise Core0Error("raw guest packet bytes differ from recorded observations")
    return value


def row_checkers(row: tuple[str, str, str]) -> tuple:
    configuration, stage, _ = row
    if configuration == "normal" and stage == "bootstrap-m":
        return (("check_kernel_bootinfo", [], "bootinfo", 3),)
    if configuration == "normal":
        return (("check_kernel_user", [], "user", 1),)
    if configuration == "frames-development":
        return (("check_kernel_frames", [], "frames", 1),
                ("check_kernel_frames", ["--address-space"], "address-space", 1),
                ("check_kernel_loader", [], "loader", 1))
    if configuration == "machine-origin-development":
        return (("check_kernel_supervisor", ["--case", "machine-origin"], "machine-origin", 1),)
    if configuration == "user-syscall-development":
        return (("check_kernel_syscall", [], "syscall", 1),)
    return (("check_kernel_isolation", [], "isolation", 1),)


def protocol_guard(left: float, qemu_timeout: float, session_count: int) -> None:
    if left < session_count * qemu_timeout + 120:
        raise Core0Error("insufficient remaining deadline for a complete bounded guest protocol")


def execute_row(*, root: Path, work_dir: Path, index: int, identity: dict,
                sources: dict, consumers: dict, timeout: float, qemu_timeout: float,
                finish_by: float, cache_dir: Path) -> dict:
    """One real process owns one row's existing fresh build and guest CLIs."""
    if type(index) is not int or not 0 <= index < len(matrix()):
        raise Core0Error("row index is outside the fixed Task003 matrix")
    configuration, stage, optimization = matrix()[index]
    report = {"schema": "lemma-kernel-matrix-row/v1", "status": "FAIL", "index": index,
              "row": list(matrix()[index]), "source": identity, "source_inputs": sources,
              "acceptance_inputs": consumers, "finish_by": finish_by, "cache_dir": str(cache_dir),
              "invocations": [], "images": [], "observations": []}
    row_result_path = work_dir / "rows" / f"{index:02d}" / "result.json"
    logs = work_dir / "logs"; logs.mkdir(exist_ok=True)
    started = time.monotonic()

    def remaining() -> float:
        left = finish_by - time.monotonic()
        if left <= 0:
            raise Core0Error("cumulative Task003 acceptance deadline expired")
        return left

    def cli(module_name: str, args: list[str], label: str, *, session_count: int = 1) -> None:
        # Run the maintained CLI in this process so an external TERM unwinds
        # its Session context and kills/reaps QEMU before reporting failure.
        protocol_guard(remaining(), qemu_timeout, session_count)
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
        if source_identity(root) != identity or source_inputs(root) != sources or acceptance_inputs(root) != consumers:
            raise Core0Error("row source/consumer differs from clean acceptance source")
        label = f"{configuration}-{stage}-{optimization}"
        directory = work_dir / label
        built = build(root=root, output_dir=directory, opt_level=optimization, stage=stage,
                      configuration=configuration, timeout_seconds=min(timeout, remaining()),
                      fresh=True, cache_dir=cache_dir)
        image = directory / "image.elf"
        if built.get("status") != "BUILT" or not image.is_file() or not image.stat().st_size:
            raise Core0Error("required image/build report is missing")
        provenance = load_json(directory / "provenance.json")
        if provenance.get("source_commit") != identity["commit"] or provenance.get("dirty_paths") or provenance.get("source_inputs") != sources:
            raise Core0Error("fresh image source identity differs from clean acceptance source")
        checkers = row_checkers(matrix()[index])
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
            if role == "syscall":
                from check_kernel_syscall import DEFAULT_SEEDS
                observed = value.get("observed", {})
                if (observed.get("protocol") != "user-E-syscalls-v1" or observed.get("fresh_user_runs") != 3
                        or [case.get("runtime_seed") for case in observed.get("cases", [])] != list(DEFAULT_SEEDS)):
                    raise Core0Error("E runtime seed/instance corpus is incomplete")
            report["observations"].append({"configuration": configuration, "stage": stage, "optimization": optimization,
                                           "role": role, "result": str((output / "result.json").relative_to(root)),
                                           "sha256": sha256(output / "result.json"), "status": "PASS", "qemu_sessions": count,
                                           "syscall_user_instances": value.get("observed", {}).get("fresh_user_runs", 0) if role == "syscall" else 0})
        artifact_audit = load_json(directory / "audit.json")
        if artifact_audit.get("status") != "PASS" or artifact_audit.get("source_commit") != identity["commit"] or artifact_audit.get("image_sha256") != sha256(image):
            raise Core0Error("mandatory full artifact audit is missing or stale")
        report["images"].append({"configuration": configuration, "stage": stage, "optimization": optimization,
                                 "image": str(image.relative_to(root)), "sha256": sha256(image),
                                 "audit_sha256": sha256(directory / "audit.json"), "provenance_sha256": sha256(directory / "provenance.json")})

        if source_identity(root) != identity or source_inputs(root) != sources or acceptance_inputs(root) != consumers:
            raise Core0Error("row source/consumer changed during qualification")
        remaining(); report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        write_json(row_result_path, report)
    return report


def merge_rows(report: dict, rows: list[dict], indices: tuple[int, ...], *,
               prerequisites: list[dict] | None = None, complete: bool = False) -> None:
    """Publish by fixed matrix index, never by process completion order."""
    expected = set(indices)
    seen = set()
    for row in rows:
        index = row.get("index")
        if type(index) is not int or index not in expected or index in seen or row.get("row") != list(matrix()[index]):
            raise Core0Error("duplicate, unexpected or mismatched matrix row result")
        seen.add(index)
        profile = dict(zip(("configuration", "stage", "optimization"), matrix()[index]))
        if row.get("status") != "PASS" or len(row.get("images", [])) != 1:
            raise Core0Error("matrix row did not complete its fresh image")
        if any(any(item.get(key) != value for key, value in profile.items()) for item in row["images"] + row.get("observations", [])):
            raise Core0Error("matrix image/observation belongs to another row")
        wanted = [(role, count, 3 if role == "syscall" else 0) for _, _, role, count in row_checkers(matrix()[index])]
        actual = [(item.get("role"), item.get("qemu_sessions"), item.get("syscall_user_instances")) for item in row.get("observations", [])]
        if actual != wanted or any(item.get("status") != "PASS" for item in row["observations"]):
            raise Core0Error("matrix row observation coverage differs")
    if complete and seen != expected:
        raise Core0Error("matrix row results are incomplete")
    ordered = sorted(rows, key=lambda row: row["index"])
    report["images"] = [item for row in ordered for item in row["images"]]
    report["observations"] = [item for row in ordered for item in row["observations"]]
    report["matrix_rows"] = [row["supervision"] for row in ordered if "supervision" in row]
    report["invocations"] = [*(prerequisites or []), *(item for row in ordered for item in row["invocations"])]


def validate_row_result(root: Path, work_dir: Path, request: dict, request_path: Path,
                        expected_request_sha256: str, supervisor_path: Path, *, expected_supervisor_pid: int | None = None) -> dict:
    """Admit only a completed, reaped and exactly bound subprocess result."""
    supervisor = load_json(supervisor_path)
    if (supervisor.get("schema") != "lemma-kernel-row-supervisor/v1" or supervisor.get("status") != "PASS"
            or type(supervisor.get("child_returncode")) is not int or supervisor.get("child_returncode") != 0 or supervisor.get("cleanup_complete") is not True):
        raise Core0Error("matrix row supervisor did not establish successful cleanup")
    if sha256(request_path) != expected_request_sha256:
        raise Core0Error("matrix row request changed while executing")
    if (supervisor.get("reason") != "child-exited" or supervisor.get("deadline_monotonic") != request["finish_by"]
            or supervisor.get("supervisor_sha256") != request["acceptance_inputs"]["scripts/kernel_row_supervisor.py"]
            or supervisor.get("argv") != row_command(root, request_path)
            or supervisor.get("cleanup", {}).get("remaining") != []):
        raise Core0Error("matrix supervisor launch, source, deadline or cleanup binding differs")
    from kernel_row_supervisor import process_identity, same_process
    owned = supervisor.get("owned_processes")
    owner, child = supervisor.get("owner"), supervisor.get("child_identity")
    if (not isinstance(owned, list) or not owned or not isinstance(owner, dict) or not isinstance(child, dict)
            or expected_supervisor_pid is not None and owner.get("pid") != expected_supervisor_pid
            or not any(same_process(child, identity) for identity in owned)):
        raise Core0Error("matrix supervisor ownership/reap corpus differs")
    for identity in [owner, *owned]:
        if (not isinstance(identity, dict) or type(identity.get("pid")) is not int
                or not isinstance(identity.get("start_ticks"), str)
                or same_process(identity, process_identity(identity["pid"]))):
            raise Core0Error("matrix supervisor or owned descendant is malformed or still present")
    result_path = request_path.with_name("result.json")
    row = load_json(result_path)
    if (row.get("schema") != "lemma-kernel-matrix-row/v1" or row.get("status") != "PASS"
            or any(row.get(key) != request[key] for key in
                   ("index", "row", "source", "source_inputs", "acceptance_inputs", "finish_by", "cache_dir"))
            or row.get("request_sha256") != expected_request_sha256):
        raise Core0Error("matrix row result is incomplete or differs from its immutable request")
    # A child exit code alone cannot substitute for artifact and raw-observation
    # admission. Recheck all retained result identities in the parent as well.
    for item in row["images"]:
        image = root / item["image"]
        if not image.resolve().is_relative_to(work_dir) or sha256(image) != item["sha256"]:
            raise Core0Error("matrix row image escaped or changed")
        for filename, key in (("audit.json", "audit_sha256"), ("provenance.json", "provenance_sha256")):
            if sha256(image.parent / filename) != item[key]:
                raise Core0Error("matrix row audit/provenance changed")
    if len(row["images"]) != 1:
        raise Core0Error("matrix row image corpus differs")
    image = root / row["images"][0]["image"]
    for item in row["observations"]:
        path = root / item["result"]
        if not path.resolve().is_relative_to(work_dir) or sha256(path) != item["sha256"]:
            raise Core0Error("matrix row observation escaped or changed")
        value = load_json(path)
        if item["role"] == "bootinfo":
            if value.get("status") != "PASS" or [case.get("kind") for case in value.get("cases", [])] != ["ordinary", "reserved-pool", "root-cells"]:
                raise Core0Error("bootinfo child result corpus differs")
            for case in value["cases"]:
                child = Path(case["result"])
                if not child.resolve().is_relative_to(work_dir) or sha256(child) != case["result_sha256"]:
                    raise Core0Error("bootinfo child report changed")
                validate_session(child, image)
        else:
            validate_session(path, image, machine_origin=item["role"] == "machine-origin")
    for invocation in row["invocations"]:
        path = root / invocation["log"]
        if not path.resolve().is_relative_to(work_dir) or sha256(path) != invocation["log_sha256"] or invocation["returncode"] != 0:
            raise Core0Error("matrix row invocation log changed or failed")
    row["supervision"] = {"index": row["index"], "row": row["row"], "status": "PASS",
                          "request": str(request_path.relative_to(root)), "request_sha256": expected_request_sha256,
                          "result": str(result_path.relative_to(root)), "result_sha256": sha256(result_path),
                          "supervisor": str(supervisor_path.relative_to(root)), "supervisor_sha256": sha256(supervisor_path),
                          "cache_dir": request["cache_dir"], "slot": request["slot"], "cleanup_complete": True}
    merge_rows({}, [row], (row["index"],), complete=True)
    return row


def row_command(root: Path, request_path: Path) -> list[str]:
    return [sys.executable, str(root / "scripts/check_kernel.py"), "--row-request", str(request_path)]


def run_matrix_rows(*, root: Path, work_dir: Path, indices: tuple[int, ...], jobs: int,
                    identity: dict, sources: dict, consumers: dict, timeout: float,
                    qemu_timeout: float, finish_by: float, progress=None) -> list[dict]:
    """Bounded process pool; partial callers provide diagnostic scope separately.

    Every row still resets its slot's protected Lake state and executes all
    target actions fresh. Only this coordinator owns the pipe writers. Their
    closure cancels row supervisors even if the coordinator itself is killed.
    """
    if (type(jobs) is not int or jobs not in (1, 2) or not indices or len(set(indices)) != len(indices)
            or any(type(index) is not int or not 0 <= index < len(matrix()) for index in indices)):
        raise Core0Error("invalid bounded matrix process plan")
    if (not math.isfinite(finish_by) or finish_by <= time.monotonic() or
            finish_by - time.monotonic() > 2400 or
            any(isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in (timeout, qemu_timeout))):
        raise Core0Error("invalid matrix process deadline or command bounds")
    if ROW_SUPERVISORS:
        raise Core0Error("matrix process pools cannot share a controller")
    queued = list(indices); active = {}; results = []; records = []
    (work_dir / "rows").mkdir(exist_ok=True)
    helper = root / "scripts/kernel_row_supervisor.py"

    def start(index, slot):
        directory = work_dir / "rows" / f"{index:02d}"
        directory.mkdir()
        request = {"schema": "lemma-kernel-row-request/v1", "root": str(root), "work_dir": str(work_dir),
                   "index": index, "row": list(matrix()[index]), "slot": slot,
                   "source": identity, "source_inputs": sources, "acceptance_inputs": consumers,
                   "timeout": timeout, "qemu_timeout": qemu_timeout, "finish_by": finish_by,
                   "cache_dir": str(work_dir / "cache" / f"slot-{slot}")}
        path = directory / "request.json"; write_json(path, request)
        receipt = directory / "supervisor.json"
        command = row_command(root, path)
        digest = sha256(path)
        read_fd, write_fd = os.pipe()
        try:
            log = (directory / "supervisor.log").open("wb")
        except BaseException:
            os.close(read_fd); os.close(write_fd)
            raise
        blocked = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGALRM})
        process = None
        try:
            argv = [sys.executable, str(helper), "--parent-pid", str(os.getpid()), "--control-fd", str(read_fd),
                    "--deadline", str(finish_by), "--receipt", str(receipt), "--", *command]
            process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       pass_fds=(read_fd,), start_new_session=True)
            record = {"index": index, "slot": slot, "request": request, "path": path,
                      "request_sha256": digest, "receipt": receipt, "write_fd": write_fd,
                      "log": log, "process": process, "command": argv}
            active[slot] = record; records.append(record); ROW_SUPERVISORS[process.pid] = process
        except BaseException:
            os.close(write_fd)
            if process is not None:
                process.wait(timeout=12)
            log.close()
            raise
        finally:
            os.close(read_fd)
            # A queued signal can only unwind after ownership registration.
            # The helper explicitly unblocks its inherited mask before its row.
            signal.pthread_sigmask(signal.SIG_SETMASK, blocked)

    def close_control(record):
        if record["write_fd"] is not None:
            os.close(record["write_fd"]); record["write_fd"] = None

    try:
        while queued or active:
            if time.monotonic() >= finish_by:
                raise Core0Error("cumulative Task003 acceptance deadline expired")
            for slot in range(jobs):
                if queued and slot not in active:
                    start(queued.pop(0), slot)
            completed = [slot for slot, record in active.items() if record["process"].poll() is not None]
            for slot in completed:
                record = active[slot]; process = record["process"]
                process.wait(); close_control(record); record["log"].close()
                ROW_SUPERVISORS.pop(process.pid, None)
                del active[slot]
                if process.returncode != 0:
                    raise Core0Error(f"matrix row{record['index']} supervisor failed; see {record['receipt']}")
                row = validate_row_result(root, work_dir, record["request"], record["path"],
                                          record["request_sha256"], record["receipt"], expected_supervisor_pid=process.pid)
                results.append(row)
                if progress is not None:
                    progress(results)
            if active:
                time.sleep(min(0.02, max(0.001, finish_by - time.monotonic())))
        merge_rows({}, results, indices, complete=True)
        return sorted(results, key=lambda row: row["index"])
    finally:
        # Never kill a supervisor before it has cleaned its independently
        # sessioned descendants. EOF requests graceful unwind followed by its
        # verified identity-based KILL/reap phase (5+3 seconds maximum).
        for record in active.values():
            close_control(record)
        cleanup_errors = []
        for record in active.values():
            process = record["process"]
            try:
                process.wait(timeout=12)
                receipt = load_json(record["receipt"])
                if receipt.get("cleanup_complete") is not True:
                    cleanup_errors.append(str(record["receipt"]))
            except (subprocess.TimeoutExpired, OSError, ValueError) as error:
                cleanup_errors.append(f"{record['receipt']}: {error}")
            finally:
                record["log"].close()
                if process.poll() is not None:
                    ROW_SUPERVISORS.pop(process.pid, None)
        for record in records:
            if record["slot"] not in active or active[record["slot"]] is not record:
                try:
                    if load_json(record["receipt"]).get("cleanup_complete") is not True:
                        cleanup_errors.append(str(record["receipt"]))
                except (OSError, ValueError) as error:
                    cleanup_errors.append(f"{record['receipt']}: {error}")
        write_json(work_dir / "rows" / "execution.json", {
            "schema": "lemma-kernel-matrix-processes/v1", "jobs": jobs, "indices": list(indices),
            "finish_by": finish_by, "cleanup_complete": not cleanup_errors,
            "cleanup_errors": cleanup_errors,
            "rows": [{"index": record["index"], "slot": record["slot"], "argv": record["command"],
                      "request": str(record["path"].relative_to(root)), "request_sha256": record["request_sha256"],
                      "supervisor": str(record["receipt"].relative_to(root)),
                      "supervisor_sha256": sha256(record["receipt"]) if record["receipt"].is_file() else None,
                      "log_sha256": sha256(record["path"].with_name("supervisor.log")),
                      "returncode": record["process"].poll()} for record in records]})
        if cleanup_errors:
            raise Core0Error("matrix supervisor cleanup failed: " + "; ".join(cleanup_errors))


def row_main(path: Path) -> int:
    request = load_json(path)
    root = repo_root(); work_dir = Path(request["work_dir"]); index = request["index"]
    if (request.get("schema") != "lemma-kernel-row-request/v1" or request.get("root") != str(root)
            or type(index) is not int or not 0 <= index < len(matrix()) or request.get("row") != list(matrix()[index])
            or not work_dir.is_absolute() or not work_dir.resolve().is_relative_to(root / "build/kernel")
            or work_dir.resolve() == root / "build/kernel" or type(request.get("slot")) is not int or request.get("slot") not in (0, 1)
            or path.resolve() != work_dir / "rows" / f"{index:02d}" / "request.json"
            or request["cache_dir"] != str(work_dir / "cache" / f"slot-{request['slot']}")):
        raise Core0Error("invalid fixed matrix row request")
    finish_by = request["finish_by"]
    if (isinstance(finish_by, bool) or not math.isfinite(finish_by) or not 0 < finish_by-time.monotonic() <= 2400
            or any(isinstance(request[key], bool) or not math.isfinite(request[key]) or request[key] <= 0
                   for key in ("timeout", "qemu_timeout"))):
        raise Core0Error("invalid row deadline or command bounds")
    digest = sha256(path)
    def interrupt(number, _frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        raise Core0Error(f"matrix row interrupted by host signal{number}")
    signal.signal(signal.SIGTERM, interrupt); signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, finish_by-time.monotonic()))
    try:
        value = execute_row(root=root, work_dir=work_dir, index=index, identity=request["source"],
                            sources=request["source_inputs"], consumers=request["acceptance_inputs"],
                            timeout=request["timeout"], qemu_timeout=request["qemu_timeout"],
                            finish_by=finish_by, cache_dir=Path(request["cache_dir"]))
        value["request_sha256"] = digest
        write_json(path.with_name("result.json"), value)
        return 0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def check(*, root: Path, work_dir: Path, clean: bool, timeout: float, qemu_timeout: float, deadline: float,
          host_prerequisite: Path | None = None, jobs: int = 1) -> dict:
    try:
        relative = work_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("Task003 evidence must be a build/kernel subdirectory") from error
    if not relative.parts:
        raise Core0Error("refusing to replace all kernel evidence")
    if any(isinstance(number, bool) or not math.isfinite(number) or number <= 0 for number in (timeout, qemu_timeout, deadline)) or deadline > 2400:
        raise Core0Error("timeouts must be finite/positive and cumulative deadline at most40minutes")
    if type(jobs) is not int or jobs not in (1, 2):
        raise Core0Error("Task003 matrix jobs must be1or2")
    prepare_output_directory(work_dir, root, clean=clean)
    started = time.monotonic(); finish_by = started + deadline
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "kernel-A-E-clean-acceptance",
              "started_at": datetime.now(timezone.utc).isoformat(), "required_gate_prefix": "A-E", "highest_exercised_gate": "not_run",
              "later_gates": {gate: "not_run" for gate in "FGHIJK"}, "deadline_seconds": deadline, "jobs": jobs,
              "invocations": [], "images": [], "observations": []}
    logs = work_dir / "logs"; logs.mkdir()

    def remaining() -> float:
        left = finish_by - time.monotonic()
        if left <= 0:
            raise Core0Error("cumulative Task003 acceptance deadline expired")
        return left


    try:
        require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld", "llvm-objdump", "qemu-system-riscv64", "dtc"))
        identity, sources, consumers = source_identity(root), source_inputs(root), acceptance_inputs(root)
        report.update(source=identity, source_inputs=sources, acceptance_inputs=consumers)
        for label, argv in (("lake-build", ("lake", "build")),
                            ("kernel-host", (sys.executable, "-m", "unittest", "discover", "-s", "tests/kernel", "-v"))):
            if label == "kernel-host" and host_prerequisite is not None:
                from host_prerequisites import validate as validate_host_prerequisite
                validate_host_prerequisite(root, host_prerequisite)
                retained = work_dir / "host-prerequisite"
                retained.mkdir()
                shutil.copyfile(host_prerequisite, retained / "receipt.json")
                shutil.copyfile(host_prerequisite.parent / "kernel-host.log", retained / "kernel-host.log")
                admission = validate_host_prerequisite(root, retained / "receipt.json")
                report["invocations"].append({"label": label, **admission})
                report["host_tests"] = admission["test_count"]
                continue
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
        if len(plan) != 20 or len(set(plan)) != 20:
            raise Core0Error("required Task003 configuration matrix is incomplete")
        prerequisites = list(report["invocations"])
        run_matrix_rows(root=root, work_dir=work_dir, indices=tuple(range(len(plan))), jobs=jobs,
                        identity=identity, sources=sources, consumers=consumers, timeout=timeout,
                        qemu_timeout=qemu_timeout, finish_by=finish_by,
                        progress=lambda rows: merge_rows(report, rows, tuple(range(len(plan))), prerequisites=prerequisites))
        if len(report["images"]) != 20 or len(report["observations"]) != 24:
            raise Core0Error("Task003 image/observation matrix did not complete")
        sessions = sum(row["qemu_sessions"] for row in report["observations"])
        syscall_instances = sum(row["syscall_user_instances"] for row in report["observations"])
        if sessions != 28 or syscall_instances != 6:
            raise Core0Error("Task003 observed process/user-instance matrix is incomplete")
        if source_identity(root) != identity or source_inputs(root) != sources or acceptance_inputs(root) != consumers:
            raise Core0Error("acceptance source/consumer changed during qualification")
        remaining(); report.update(status="PASS", highest_exercised_gate="E", qemu_sessions=sessions, syscall_user_instances=syscall_instances)
        report["limitations"] = ["Fresh clean acceptance of the implemented A-E prefix; not completion of Task003.",
                                  "A-E prefix alone does not qualify Gates F-K; their evidence is separate.",
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
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=1, help="Bounded independent matrix processes")
    parser.add_argument("--row-request", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--qemu-timeout", type=float, default=90)
    parser.add_argument("--deadline", type=float, default=2400)
    parser.add_argument("--host-prerequisite", type=Path,
                        help="Validate an exact ordinary kernel-host receipt; Lake and all target qualification remain fresh")
    args = parser.parse_args()
    if args.row_request is not None:
        try:
            return row_main(args.row_request)
        except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
            print(f"FAIL: {error}")
            return 1
    interruption = None
    def terminate(_signum, _frame):
        nonlocal interruption
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        stopped = ([{"deferred_to_row_supervisors": sorted(ROW_SUPERVISORS)}] if ROW_SUPERVISORS
                   else stop_controller_children(defer_qemu=True))
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
                      timeout=args.timeout, qemu_timeout=args.qemu_timeout, deadline=args.deadline,
                      host_prerequisite=(root / args.host_prerequisite).resolve() if args.host_prerequisite else None, jobs=args.jobs)
        print(f"PASS: clean Task003 A-E prefix, {len(value['images'])} images, {len(value['observations'])} checker reports")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1
    finally:
        if interruption is not None:
            # After maintained guest contexts unwind, reap any unowned child
            # left by interruption during process construction or a tool call.
            interruption["remaining_children_after_unwind"] = (
                [{"supervisors_still_own_cleanup": sorted(ROW_SUPERVISORS)}] if ROW_SUPERVISORS else stop_controller_children())
            output = (repo_root() / args.work_dir).resolve()
            if output.is_dir() and output.is_relative_to((repo_root() / "build/kernel").resolve()):
                write_json(output / "interruption-cleanup.json", interruption)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_alarm)
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
