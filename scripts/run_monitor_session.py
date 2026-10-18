#!/usr/bin/env python3
"""Fresh interactive RV64 monitor sessions, with deferred independent oracles."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import audit_monitor
import audit_timer
import gate9_corpus as corpus
import run_device_session as transport
from audit_core0 import MONITOR_IMAGE_REQUIRED_ARTIFACTS
from build_core0 import invalidate_output_file, prepare_output_directory
from core0_common import Core0Error, load_json, repo_root, require_tools, sha256, write_json
from run_timer_case import image_machine_info
from run_trap_case import _validate_hash_catalog

RESULT_FILE = "run.json"
BUILD_ARTIFACTS = frozenset(MONITOR_IMAGE_REQUIRED_ARTIFACTS)
AUDIT_ARTIFACTS = BUILD_ARTIFACTS
SOURCE_ARTIFACTS = ("program.ll", "startup.S", "link.ld", "layout.json", "device-contract.json",
    "monitor-manifest.json", "monitor-normalized.txt", "monitor-abi.json", "symbols.txt")
REQUIRED_SOURCE_INPUTS = frozenset({
    "examples/foundation/MonitorBuild.lean", "examples/foundation/Monitor.lean",
    "examples/foundation/MonitorProtocol.lean", "examples/foundation/MonitorPolicyProbes.lean",
    "examples/foundation/TimerConformance.lean", "examples/foundation/TrapConformance.lean",
    "examples/foundation/DeviceConformanceSupport.lean", "Lemma/Compiler/Test/MonitorExport.lean",
    "Lemma/Core0/Timer.lean", "Lemma/Core0/TimerModel.lean", "Lemma/Machine/TimerPrimitives.lean",
    "Lemma/Machine/TrapPrimitives.lean", "Lemma/Machine/TrapLayout.lean",
    "scripts/build_core0.py", "scripts/core0_common.py", "scripts/build_monitor.py",
    "scripts/audit_core0.py", "scripts/audit_monitor.py", "scripts/audit_timer.py",
    "scripts/audit_trap.py", "scripts/audit_device.py", "scripts/audit_memory.py",
    "scripts/check_foundation.py", "scripts/gate9_corpus.py", "scripts/run_monitor_session.py",
    "scripts/check_foundation_gate9.py", "scripts/run_device_session.py", "scripts/gate6_corpus.py",
    "scripts/qualify_foundation.py",
    "scripts/run_timer_case.py", "scripts/gate8_corpus.py", "scripts/run_trap_case.py",
    "docs/audits/monitor-core0-v07.html", "docs/audits/timers-core0-v07.html",
})


class MonitorRunFailure(Core0Error):
    def __init__(self, category: str, detail: str, report: dict[str, object] | None = None):
        self.category, self.detail, self.report = category, detail, report
        super().__init__(f"{category}: {detail}")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"monitor {label} is not an object")
    return value


def _same(actual: object, expected: object, label: str) -> None:
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise Core0Error(f"monitor {label} differs")


def source_inputs(directory: Path, root: Path) -> dict[str, str]:
    provenance = _object(load_json(directory / "provenance.json"), "provenance")
    entries = provenance.get("source_inputs")
    if not isinstance(entries, list) or not entries:
        raise Core0Error("monitor provenance lacks source inputs")
    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise Core0Error("monitor source input is malformed")
        name, digest = entry["path"], entry["sha256"]
        if (not isinstance(name, str) or not name or Path(name).is_absolute() or name in result
                or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
            raise Core0Error("monitor source input is unsafe/duplicate")
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or sha256(path) != digest:
            raise Core0Error(f"monitor source input is stale or escaped: {name}")
        result[name] = digest
    required = REQUIRED_SOURCE_INPUTS
    if not (root / "docs/document-map.json").is_file():
        required = frozenset(name[:-5] + ".md" if name.startswith("docs/") and name.endswith(".html") else name
                             for name in required)
    if not required <= result.keys():
        raise Core0Error("monitor provenance omits required source/machine/compiler/host inputs")
    return result


def _validate_audit(audit: dict[str, object], manifest: dict[str, object], directory: Path,
                    optimization: str) -> None:
    # Recompute the pure, pinned source/LLVM closure, not just the exporter or
    # report's declaration that a check passed. No guest or QEMU is running yet.
    expected_ir = audit_monitor.validate_monitor_ir(manifest,
        (directory / "program.ll").read_text(encoding="utf-8"),
        (directory / "program.opt.ll").read_text(encoding="utf-8"), optimization)
    _same(audit.get("monitor_ir_audit"), expected_ir, "complete source/IR/role evidence")
    machine = _object(audit.get("monitor_machine_audit"), "machine evidence")
    compiled = len(manifest["scalar_functions"]) + len(manifest["action_functions"])
    fixed = {"mutation": "none", "compiled_functions": compiled,
        "compiled_gp_tp_free": True, "compiled_privileged_instructions": 0,
        "approved_resume_pairs": 2, "fatal_stackless_self_loops": 2,
        "startup_functions": 16, "timer_functions": 7, "timer_mmio_accesses": 3,
        "timer_mmio_width_bits": 64, "timer_fence_operations": 14,
        "machine_csr_operations": 28,
        "timer_machine_body_sha256": audit_timer.TIMER_MACHINE_BODY_SHA256,
        "timer_start_machine_body_sha256": audit_monitor.MONITOR_START_MACHINE_BODY_SHA256[optimization],
        "timer_probe": {"iterations": 65536, "caller_saves": 16, "snapshot_registers": 31,
            "memory_slots": 106, "mie_window": "after sentinels, bounded counter only, before snapshots"},
        "startup": {"mutation": "none", "startup_compare_parked": True,
            "timer_functions": 7, "timer_mmio_width_bits": 64, "timer_probe_iterations": 65536,
            "probe_registers": 31, "csr_roles": ["mstatus.MIE", "mie.MTIE", "mip.MTIP"],
            "synchronous_trap_substrate": "exact core0-v0.6 structured sequence"},
        "layout": {"frame_bytes": 288, "canaries": 6, "regions": {
            "trap_stack": [0x80810000, 0x4000], "trap_probe_context": [0x80815000, 0x1000],
            "trap_probe_stack": [0x80818000, 0x1000]}},
        "machine_csr_by_function": {"_start": 5, "core0_trap_vector": 12,
            "core0_trap_ecall": 1, "core0_trap_breakpoint": 1, "core0_trap_unexpected_ecall": 1,
            "core0_timer_read_pending": 1, "core0_irq_save_disable": 1, "core0_irq_restore": 2,
            "core0_timer_set_interrupt": 2, "core0_timer_probe": 2},
    }
    slots = dict.fromkeys(audit_timer.TIMER_STARTUP_FUNCTIONS, 0)
    slots.update({"_start": 16, "core0_trap_vector": 75, "core0_trap_ecall": 106,
        "core0_trap_breakpoint": 106, "core0_timer_probe": 106,
        "core0_timer_read_time": 1, "core0_timer_set_compare": 1})
    fixed["machine_slot_sequences"] = slots
    fixed["timer_mmio_machine"] = {
        "access_count": 3, "width_bits": 64, "compiled_program_accesses": 0,
        "all_inferred_accesses_are_approved": True,
        "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof",
        "accesses": [{"function": function, "instruction": instruction, "address": address,
            "machine_address": pc, "width_bits": 64} for function, instruction, address, pc in (
                ("_start", "sd", "0x02004000", "0x80000194"),
                ("core0_timer_read_time", "ld", "0x0200bff8", "0x800017bc"),
                ("core0_timer_set_compare", "sd", "0x02004000", "0x800017d4"))]}
    for name, expected in fixed.items():
        _same(machine.get(name), expected, f"machine {name} evidence")
    sequence = audit_monitor.MONITOR_MACHINE_ACCESS_SEQUENCE
    accesses = [{"operation": operation, "function": function, "instruction": instruction,
        "address": f"0x{address:08x}", "fence_before": True, "fence_after": True}
        for operation, function, instruction, address in sequence]
    count = len(accesses)
    _same(audit.get("device_machine_audit"), {"access_count": count,
        "byte_accesses_only": True, "ordered_fence_calls": 2 * count,
        "denied_region_metadata_materializations":
            sum(audit_monitor.MONITOR_MACHINE_DENIED_METADATA.values()) if optimization == "O0" else 0,
        "register_use_audit": {"inferred_uart_accesses": count,
            "all_inferred_accesses_are_approved": True,
            "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
        "fence_implementation": "fence iorw,iorw; ret", "accesses": accesses}, "final UART inventory")
    elf = _object(audit.get("elf"), "ELF evidence")
    for name, expected in (("entry", "0x80000000"), ("machine", "RISC-V"), ("class", "ELF64"),
        ("endianness", "little"), ("dynamic_dependencies", []), ("undefined_symbols", []), ("final_relocations", [])):
        _same(elf.get(name), expected, f"ELF {name}")
    program = sorted(["core0_main"] + [function["llvm"] for kind in ("scalar_functions", "action_functions")
                                     for function in manifest[kind]])
    startup = sorted(audit_timer.TIMER_STARTUP_FUNCTIONS)
    _same(audit.get("object_defined_function_symbols"), {"program.o": program, "startup.o": startup}, "two-object function closure")
    _same(elf.get("defined_function_symbols"), sorted(program + startup), "final function closure")
    stack = _object(audit.get("stack_sizes"), "stack evidence")
    graph = _object(stack.get("call_graph"), "stack call graph")
    if graph.get("acyclic") is not True or graph.get("dynamic_alloca") is not False:
        raise Core0Error("monitor lacks an acyclic static stack call graph")
    _same(graph.get("stack_limit_bytes"), 65536, "stack limit")
    frames = _object(graph.get("frame_chains"), "stack frame chains")
    for key, entry, root, capacity, extras in (
        ("foreground", "core0_main", manifest["roots"][0]["llvm"], 65520,
            {"machine_entry": "core0_main", "stack_region_bytes": 65536, "low_canary_bytes": 16}),
        ("trap_dispatcher", manifest["roots"][1]["llvm"], manifest["roots"][1]["llvm"], 16048,
            {"trap_frame_bytes": 288, "outgoing_argument_bytes": 16, "usable_trap_stack_bytes": 16352}),
    ):
        record = _object(graph.get(key), f"{key} resource chain")
        size, chain = record.get("bytes"), record.get("chain")
        if (type(size) is not int or not 0 <= size <= capacity or not isinstance(chain, list)
                or not chain or chain[0] != entry or root not in chain
                or any(not isinstance(symbol, str) or symbol not in program for symbol in chain)):
            raise Core0Error(f"monitor {key} resource chain is oversized, absent or unbound")
        _same(record.get("checked_root"), root, f"{key} checked root")
        _same(record.get("capacity_bytes"), capacity, f"{key} capacity")
        for name, expected in extras.items():
            _same(record.get(name), expected, f"{key} {name}")
        _same(frames.get(entry), {"bytes": size, "chain": chain}, f"{key} frame binding")


def validate_image_binding(image: Path, *, root: Path | None = None) -> dict[str, object]:
    root = repo_root() if root is None else root.resolve()
    directory = image.parent
    if image.name != "image.elf" or not image.is_file():
        raise Core0Error("monitor requires the built image.elf")
    manifest = _object(load_json(directory / "monitor-manifest.json"), "manifest")
    abi = _object(load_json(directory / "monitor-abi.json"), "ABI")
    build = _object(load_json(directory / "build.json"), "build")
    audit = _object(load_json(directory / "audit.json"), "audit")
    provenance = _object(load_json(directory / "provenance.json"), "provenance")
    audit_monitor.validate_monitor_manifest(manifest)
    audit_monitor.validate_monitor_abi(abi, manifest)
    audit_monitor.validate_monitor_companions(manifest,
        (directory / "monitor-normalized.txt").read_text(encoding="utf-8"),
        (directory / "symbols.txt").read_text(encoding="utf-8"))
    for label, value, schema in (("build", build, 1), ("audit", audit, 1), ("provenance", provenance, 2)):
        if value.get("artifact_category") != corpus.ARTIFACT_CATEGORY or type(value.get("schema_version")) is not int or value["schema_version"] != schema:
            raise Core0Error(f"monitor {label} schema/category identity differs")
    if build.get("status") != "pass" or audit.get("status") != "pass":
        raise Core0Error("monitor lacks a successful build and audit")
    _validate_hash_catalog(directory, build.get("artifacts"), BUILD_ARTIFACTS, "monitor build")
    _validate_hash_catalog(directory, audit.get("hashes"), AUDIT_ARTIFACTS, "monitor audit")
    commit, optimization = provenance.get("source_commit"), provenance.get("optimization")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Core0Error("monitor provenance lacks a full commit")
    dirty, paths = provenance.get("dirty_tree"), provenance.get("dirty_paths")
    if (not isinstance(dirty, bool) or not isinstance(paths, list) or dirty != bool(paths)
            or any(not isinstance(name, str) or not name for name in paths)):
        raise Core0Error("monitor dirty-tree identity differs")
    if (optimization not in ("O0", "O2") or build.get("optimization") != optimization
            or audit.get("optimization") != optimization or audit.get("source_commit") != commit
            or audit.get("dirty_tree") is not dirty or audit.get("provenance_schema_version") != 2):
        raise Core0Error("monitor build/audit/provenance source identities differ")
    source_inputs(directory, root)
    linked = provenance.get("linked_inputs")
    if not isinstance(linked, list) or len(linked) != 2 or build.get("linked_inputs") != linked or audit.get("linked_inputs") != linked:
        raise Core0Error("monitor linked-object identities differ")
    kinds = {"startup.o": "lean-structured-timer-startup", "program.o": "test-monitor-image-llvm"}
    seen: set[str] = set()
    for entry in linked:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or entry["path"] not in kinds or entry["path"] in seen:
            raise Core0Error("monitor linked-object catalog differs")
        name = entry["path"]
        if entry.get("kind") != kinds[name] or entry.get("sha256") != sha256(directory / name):
            raise Core0Error("monitor linked-object kind/hash differs")
        seen.add(name)
    _same(audit.get("manifest"), manifest, "audit manifest binding")
    _same(audit.get("monitor_abi"), abi, "audit ABI binding")
    _validate_audit(audit, manifest, directory, optimization)
    return {"manifest": manifest, "abi": abi, "source_commit": commit, "optimization": optimization,
            "audit_sha256": sha256(directory / "audit.json")}


def qemu_argv(image: Path) -> tuple[str, ...]:
    return ("qemu-system-riscv64", "-machine", "virt,acpi=off", "-accel", "tcg", "-cpu",
        "rv64,smrnmi=false,smdbltrp=false", "-smp", "1", "-m", "128M", "-bios", "none",
        "-kernel", str(image), "-nodefaults", "-nic", "none", "-display", "none",
        "-serial", "stdio", "-monitor", "none", "-no-reboot", "-seed", "1")


def validate_transcript(scenario: corpus.Scenario, sent: bytes, received: bytes, returncode: int,
                        machine: dict[str, object]) -> dict[str, object]:
    corpus.validate_scenario(scenario)
    expected_sent = b"".join(request.encode() for request in scenario.requests) + scenario.terminal_input
    if sent != expected_sent:
        raise MonitorRunFailure("runtime-input-mismatch", "retained sent stream differs from the fresh scenario")
    if type(returncode) is not int or returncode != scenario.expected_exit:
        raise MonitorRunFailure("target-exit-mismatch", f"expected {scenario.expected_exit}, got {returncode}")
    if not received.startswith(corpus.READY) or len(received) != len(corpus.READY) + len(scenario.requests) * corpus.RESPONSE_BYTES:
        raise MonitorRunFailure("protocol-mismatch", "READY/response count/truncation/extra output differs")
    if not scenario.requests:
        return {"outcome": "verified-terminal-rejection", "expected_exit": scenario.expected_exit, "responses": []}
    oracle = corpus.Oracle(machine["executable_ranges"])
    responses = []
    for index, request in enumerate(scenario.requests):
        start = len(corpus.READY) + index * corpus.RESPONSE_BYTES
        try:
            response = corpus.parse_response(received[start:start + corpus.RESPONSE_BYTES])
        except Core0Error as error:
            raise MonitorRunFailure("protocol-mismatch", str(error)) from error
        try:
            oracle.accept(request, response)
        except Core0Error as error:
            raise MonitorRunFailure("behavior-mismatch", f"request {index}/{request.request_id}: {error}") from error
        responses.append({"index": index, "status": response.status,
            "request_id": response.request_id, "values": list(response.values)})
    try:
        summary = oracle.finish(integration=scenario.integration, terminal=scenario.expected_exit != 0)
    except Core0Error as error:
        raise MonitorRunFailure("behavior-mismatch", str(error)) from error
    return {"outcome": "verified-monitor-session" if scenario.expected_exit == 0 else "verified-terminal-rejection",
            "expected_exit": scenario.expected_exit,
            "responses": responses, "summary": summary}


SUCCESS_RECORD_FIELDS = frozenset({
    "schema_version", "status", "profile", "artifact_category", "test_abi",
    "scenario", "image", "started_at", "timeout_seconds", "image_sha256",
    "binding", "machine", "ready_observed_before_input", "first_input_after_ready",
    "stdin_open_until_exit", "outcome", "expected_exit", "responses",
    "single_pid", "single_elf", "semantic_validation_after_exit", "pid",
    "returncode", "argv", "raw_artifacts", "elapsed_seconds", "finished_at",
})


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise Core0Error(f"monitor retained {label} is not an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise Core0Error(f"monitor retained {label} is not an ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise Core0Error(f"monitor retained {label} is not UTC-aware")
    return parsed


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_success_record(
    *,
    root: Path,
    image: Path,
    run_directory: Path,
    scenario: corpus.Scenario,
    record: dict[str, object],
    expected_timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Independently validate one persisted successful monitor process record."""
    root, image, run_directory = root.resolve(), image.resolve(), run_directory.resolve()
    corpus.validate_scenario(scenario)
    expected_fields = set(SUCCESS_RECORD_FIELDS)
    if scenario.requests:
        expected_fields.add("summary")
    if set(record) != expected_fields:
        raise Core0Error("monitor successful retained-record fields differ")
    if (
        type(record.get("schema_version")) is not int
        or record["schema_version"] != 1
        or record.get("status") != "PASS"
        or record.get("profile") != corpus.PROFILE
        or record.get("artifact_category") != corpus.ARTIFACT_CATEGORY
        or record.get("test_abi") != corpus.TEST_ABI
        or record.get("scenario") != scenario.name
        or record.get("image") != str(image)
        or record.get("image_sha256") != sha256(image)
    ):
        raise Core0Error("monitor successful retained-record identity differs")
    if (
        type(record.get("expected_exit")) is not int
        or record["expected_exit"] != scenario.expected_exit
        or type(record.get("returncode")) is not int
        or record["returncode"] != scenario.expected_exit
        or type(record.get("pid")) is not int
        or record["pid"] <= 0
    ):
        raise Core0Error("monitor successful retained-record process identity differs")
    timeout = record.get("timeout_seconds")
    elapsed = record.get("elapsed_seconds")
    if (
        not _finite_number(timeout)
        or timeout <= 0
        or not _finite_number(elapsed)
        or elapsed < 0
    ):
        raise Core0Error("monitor successful retained-record timing differs")
    if expected_timeout_seconds is not None:
        if (
            not _finite_number(expected_timeout_seconds)
            or timeout != expected_timeout_seconds
        ):
            raise Core0Error("monitor successful retained-record timeout differs")
    started = _timestamp(record.get("started_at"), "start")
    finished = _timestamp(record.get("finished_at"), "finish")
    if finished < started:
        raise Core0Error("monitor successful retained-record timestamps differ")
    expected_input_observed = True if scenario.requests or scenario.terminal_input else None
    if (
        record.get("ready_observed_before_input") is not True
        or record.get("first_input_after_ready") is not expected_input_observed
        or record.get("stdin_open_until_exit") is not True
        or record.get("semantic_validation_after_exit") is not True
        or record.get("single_pid") is not True
        or record.get("single_elf") is not True
    ):
        raise Core0Error("monitor successful retained-record process evidence differs")
    expected_argv = list(qemu_argv(image))
    if record.get("argv") != expected_argv:
        raise Core0Error("monitor successful retained-record QEMU command differs")
    expected_binding = validate_image_binding(image, root=root)
    _same(record.get("binding"), expected_binding, "successful retained binding")
    expected_machine = image_machine_info(image, root=root)
    _same(record.get("machine"), expected_machine, "successful retained ELF machine evidence")
    raw_catalog = _object(record.get("raw_artifacts"), "successful raw catalog")
    if set(raw_catalog) != {"sent.bin", "received.bin", "stderr.bin"}:
        raise Core0Error("monitor successful retained raw catalog differs")
    raw: dict[str, bytes] = {}
    for name in ("sent.bin", "received.bin", "stderr.bin"):
        path = run_directory / name
        if not path.is_file() or raw_catalog.get(name) != sha256(path):
            raise Core0Error(f"monitor successful retained raw evidence is missing/stale: {name}")
        raw[name] = path.read_bytes()
    if raw["stderr.bin"]:
        raise Core0Error("monitor successful retained emulator stderr is nonempty")
    observed = validate_transcript(
        scenario, raw["sent.bin"], raw["received.bin"], record["returncode"],
        expected_machine,
    )
    for key, value in observed.items():
        _same(record.get(key), value, f"successful retained transcript {key}")
    return observed


def run_session(*, root: Path, image: Path, output_dir: Path, scenario: corpus.Scenario,
                timeout_seconds: float = 20.0, clean: bool = False) -> dict[str, object]:
    root, image, output_dir = root.resolve(), image.resolve(), output_dir.resolve()
    invalidate_output_file(output_dir / RESULT_FILE, root)
    invalidate_output_file(output_dir / (RESULT_FILE + ".tmp"), root)
    prepare_output_directory(output_dir, root, clean=clean)
    capture = transport._Capture()
    process = None
    started = time.monotonic()
    report: dict[str, object] = {"schema_version": 1, "status": "FAIL", "profile": corpus.PROFILE,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
        "scenario": getattr(scenario, "name", "<invalid>"), "image": str(image),
        "started_at": datetime.now(timezone.utc).isoformat(), "timeout_seconds": timeout_seconds}
    category = "image-or-harness-rejection"
    try:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds < float("inf"):
            raise Core0Error("monitor timeout must be finite and positive")
        corpus.validate_scenario(scenario)
        binding = validate_image_binding(image, root=root)
        machine = image_machine_info(image, root=root)
        report.update(image_sha256=sha256(image), binding=binding, machine=machine)
        require_tools(("qemu-system-riscv64",))
        argv = qemu_argv(image)
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
        capture.pid, capture.argv = process.pid, argv
        for stream in (process.stdin, process.stdout, process.stderr):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
        deadline = time.monotonic() + timeout_seconds
        category = "target-process-failure"
        ready = transport._read_exact(process, len(corpus.READY), deadline=deadline,
            capture=capture, context="reading monitor READY")
        if ready != corpus.READY:
            raise MonitorRunFailure("protocol-mismatch", "incorrect monitor READY banner")
        report["ready_observed_before_input"] = True
        report["first_input_after_ready"] = None
        for index, request in enumerate(scenario.requests):
            if index == 0:
                report["first_input_after_ready"] = True
            transport._write_all(process, request.encode(), deadline=deadline, capture=capture,
                context=f"sending monitor request {index}")
            frame = transport._read_exact(process, corpus.RESPONSE_BYTES, deadline=deadline,
                capture=capture, context=f"reading monitor response {index}")
            # Cheap structural/ID checks only. In particular, do not execute the
            # independent 128*quanta mix while the guest awaits the next byte.
            try:
                response = corpus.parse_response(frame)
            except Core0Error as error:
                raise MonitorRunFailure("protocol-mismatch", str(error)) from error
            if response.request_id != request.request_id:
                raise MonitorRunFailure("protocol-mismatch", "monitor echoed a different request ID")
        if scenario.terminal_input:
            report["first_input_after_ready"] = True
            transport._write_all(process, scenario.terminal_input, deadline=deadline,
                capture=capture, context="sending terminal monitor bytes")
        # Keep stdin open: bounded target RX failure, not host EOF, is tested.
        report["stdin_open_until_exit"] = True
        capture.returncode = transport._wait_and_collect(process, deadline=deadline,
            capture=capture, read_stdout=True)
        if capture.stderr:
            raise MonitorRunFailure("emulator-stderr", "QEMU emitted unexpected stderr")
        report.update(validate_transcript(scenario, bytes(capture.sent), bytes(capture.received),
            capture.returncode, machine))
        if report["image_sha256"] != sha256(image):
            raise Core0Error("monitor ELF changed during its session")
        source_inputs(image.parent, root)
        report.update(status="PASS", single_pid=True, single_elf=True,
            semantic_validation_after_exit=True)
    except (Core0Error, OSError, ValueError, TypeError, UnicodeError) as error:
        if process is not None:
            transport._kill_and_reap(process, capture)
            report["cleanup"] = {"process_group_killed": True, "process_reaped": process.poll() is not None}
        failure_category = error.category if isinstance(error, MonitorRunFailure) else (
            "target-timeout" if "timed out" in str(error) else category)
        report.update(status="FAIL", failure_category=failure_category, error=str(error))
        failure = error
    else:
        failure = None
    finally:
        if process is not None:
            transport._close_process_streams(process)
        raw = {"sent.bin": bytes(capture.sent), "received.bin": bytes(capture.received),
               "stderr.bin": bytes(capture.stderr)}
        for name, data in raw.items():
            (output_dir / name).write_bytes(data)
        report.update(pid=capture.pid, returncode=capture.returncode, argv=list(capture.argv),
            raw_artifacts={name: sha256(output_dir / name) for name in raw},
            elapsed_seconds=round(time.monotonic() - started, 6),
            finished_at=datetime.now(timezone.utc).isoformat())
        write_json(output_dir / (RESULT_FILE + ".tmp"), report)
        (output_dir / (RESULT_FILE + ".tmp")).replace(output_dir / RESULT_FILE)
    if failure is not None:
        raise MonitorRunFailure(str(report["failure_category"]), str(report["error"]), report) from failure
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=sorted(corpus.SCENARIO_BY_NAME), required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--clean", action="store_true")
    ns = parser.parse_args()
    root = repo_root()
    resolve = lambda path: path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        report = run_session(root=root, image=resolve(ns.image), output_dir=resolve(ns.output_dir),
            scenario=corpus.SCENARIO_BY_NAME[ns.scenario], timeout_seconds=ns.timeout, clean=ns.clean)
    except Core0Error as error:
        print(f"MONITOR SESSION FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
