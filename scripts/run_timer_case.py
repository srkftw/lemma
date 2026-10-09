#!/usr/bin/env python3
"""Fresh bounded RV64 timer boots with strict hardware-event transcript checks."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import gate8_corpus as corpus
from audit_core0 import (TIMER_MACHINE_ACCESS_SEQUENCE, TIMER_MACHINE_DENIED_METADATA,
                         TIMER_SUITE_REQUIRED_ARTIFACTS, parse_load_segments)
from build_core0 import invalidate_output_file, prepare_output_directory
from core0_common import Core0Error, checked, load_json, repo_root, require_tools, sha256, write_json
from run_trap_case import _validate_hash_catalog

RESULT_FILE = "run.json"
BUILD_ARTIFACTS = frozenset({
    "program.ll", "program.opt.ll", "program.o", "startup.S", "startup.o", "link.ld",
    "image.elf", "image.map", "layout.json", "device-contract.json",
    "timer-suite-manifest.json", "timer-suite-normalized.txt", "timer-test-abi.json",
    "symbols.txt", "platform.dtb", "platform.dts", "provenance.json",
})
AUDIT_ARTIFACTS = frozenset(TIMER_SUITE_REQUIRED_ARTIFACTS)
REQUIRED_SOURCE_INPUTS = frozenset({
    "examples/foundation/TimerBuild.lean", "examples/foundation/TimerConformance.lean",
    "examples/foundation/TrapConformance.lean", "examples/foundation/DeviceConformanceSupport.lean",
    "examples/foundation/TimerFrontendProbes.lean", "examples/foundation/TimerPolicyProbes.lean",
    "Lemma/Core0/Timer.lean", "Lemma/Core0/TimerModel.lean",
    "Lemma/Compiler/Test/TimerExport.lean", "Lemma/Machine/TimerPrimitives.lean",
    "Lemma/Machine/TrapPrimitives.lean", "Lemma/Machine/TrapLayout.lean",
    "scripts/build_core0.py", "scripts/core0_common.py", "scripts/build_timer_suite.py",
    "scripts/audit_core0.py", "scripts/audit_timer.py", "scripts/audit_trap.py",
    "scripts/audit_device.py", "scripts/audit_memory.py",
    "scripts/check_foundation.py", "scripts/gate8_corpus.py", "scripts/run_timer_case.py",
    "scripts/run_trap_case.py", "scripts/check_foundation_gate8.py",
    "examples/foundation/gate8-reject/HiddenExternTimer.lean",
    "examples/foundation/gate8-reject/PureTimerResult.lean",
    "examples/foundation/gate8-reject/StoredTimerContinuation.lean",
    "examples/foundation/gate8-reject/V06Timer.lean",
    "examples/foundation/gate8-reject/rejections.json",
    "docs/audits/timers-core0-v07.md",
})
SITE_SYMBOLS = frozenset({"core0_trap_vector", "__timer_probe_loop", "__timer_probe_snapshot",
    "__trap_ecall_site", "__trap_ecall_resume", "__trap_breakpoint_site", "__trap_breakpoint_resume"})


class TimerRunFailure(Core0Error):
    def __init__(self, category: str, detail: str, report: dict[str, object] | None = None):
        self.category, self.detail, self.report = category, detail, report
        super().__init__(f"{category}: {detail}")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{label} is not an object")
    return value


def mutation_metadata(mutation: int) -> dict[str, object]:
    corpus.validate_mutation(mutation)
    if mutation == 0:
        stage, delta = "none", None
    elif mutation == 1:
        stage, delta = "structured-machine-restore", {"function": "core0_trap_vector",
            "before": "ld s3, 144(sp)", "after": "ld s3, 152(sp)"}
    else:
        stage, delta = "structured-machine-timer-arming", {"function": "core0_timer_set_compare",
            "before": "sd a0, 0(t0)", "after": "sd t1, 0(t0)"}
    return {"identity": corpus.MUTATION_IDENTITIES[mutation], "production_selectable": False,
            "transform_stage": stage, "match_count": 1 if mutation else 0, "expected_delta": delta}


def _validate_manifest(manifest: dict[str, object], abi: dict[str, object]) -> None:
    # The independent artifact auditor owns the complete closed schema. Import
    # lazily so pure protocol tests need no compiler or optional audit tools.
    from audit_timer import validate_timer_suite_manifest, validate_timer_test_abi
    validate_timer_suite_manifest(manifest)
    validate_timer_test_abi(abi, manifest)


def source_inputs(directory: Path, root: Path) -> dict[str, str]:
    provenance = _object(load_json(directory / "provenance.json"), "timer provenance")
    entries = provenance.get("source_inputs")
    if not isinstance(entries, list) or not entries:
        raise Core0Error("timer provenance lacks source inputs")
    result: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise Core0Error("malformed timer source input")
        name, digest = item["path"], item["sha256"]
        if not isinstance(name, str) or not name or Path(name).is_absolute() or name in result or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise Core0Error("unsafe/duplicate timer source input")
        source = (root / name).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file() or sha256(source) != digest:
            raise Core0Error(f"stale or escaped timer source input: {name}")
        result[name] = digest
    if not REQUIRED_SOURCE_INPUTS <= result.keys():
        raise Core0Error("timer provenance omits required source/compiler/machine/host inputs")
    return result


def _same_evidence(actual: object, expected: object, label: str) -> None:
    # JSON equality distinguishes booleans/floats from the required integer
    # counts (Python dictionary equality alone would accept True as 1).
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise Core0Error(f"timer audit {label} evidence differs")


def _validate_timer_audit(audit: dict[str, object], manifest: dict[str, object],
                          optimization: str) -> None:
    from audit_timer import (
        DISABLE_ARMING_MACHINE_BODY_SHA256,
        TIMER_MACHINE_BODY_SHA256,
        TIMER_OPS,
        TIMER_STARTUP_FUNCTIONS,
    )
    ir = _object(audit.get("timer_ir_audit"), "timer IR audit")
    source_counts = {"timer.set-interrupt": 3, "timer.set-compare": 4,
        "timer.read-time": 3, "irq.save-disable": 4, "timer.probe": 1,
        "irq.restore": 3, "timer.read-pending": 2}
    lowered_counts = {str(op["llvm_symbol"]): source_counts[str(op["stable_id"])]
                      for op in TIMER_OPS}
    post_counts = dict(lowered_counts)
    if optimization == "O2":
        post_counts["core0_timer_set_compare"] = 3
    _same_evidence(ir.get("optimization"), optimization, "IR optimization")
    _same_evidence(ir.get("timer_calls"), {"source": source_counts,
        "pre_optimization": lowered_counts, "post_optimization": post_counts},
        "source/pre/post timer operation closure")
    _same_evidence(ir.get("post_optimization_tail_merge"), {
        "function": "core0_action_38", "source_sites": 2, "machine_calls": 1,
        "selector": "two-input phi from the mutually exclusive deadline branches",
    } if optimization == "O2" else None, "exact optimizer compare tail merge")
    _same_evidence(ir.get("optimizer_intrinsics"), {
        "llvm.umin.i64": 1 if optimization == "O2" else 0,
        "function": "core0_scalar_27" if optimization == "O2" else None,
        "upper_bound": 16 if optimization == "O2" else None,
    }, "closed optimizer intrinsic")
    _same_evidence(ir.get("machine_timer_mmio_in_program"), 0, "compiled timer MMIO exclusion")
    _same_evidence(ir.get("bool_machine_arguments"),
        {"calls": 6, "lowering": "canonical i1-to-i64 zext"}, "canonical Bool ABI")
    operations = [entry[0] for entry in TIMER_MACHINE_ACCESS_SEQUENCE]
    expected_uart = {label: {"operations": operations, "accesses": 4,
        "functions": sorted({entry[1] for entry in TIMER_MACHINE_ACCESS_SEQUENCE})}
        for label in ("pre", "post")}
    _same_evidence(ir.get("uart"), expected_uart, "IR UART sequence")
    memory = _object(ir.get("memory"), "timer checked-RAM audit")
    access_count = memory.get("access_count")
    if (type(access_count) is not int or access_count <= 0
            or memory.get("volatile_policy") is not True
            or not isinstance(memory.get("accesses"), list)
            or len(memory["accesses"]) != access_count
            or any(not isinstance(entry, dict) or not entry for entry in memory["accesses"])
            or any(type(memory.get(key)) is not int or memory[key] < 0
                   for key in ("loads", "stores", "source_memory_site_count"))
            or memory["loads"] + memory["stores"] != access_count
            or memory["source_memory_site_count"] < access_count
            or not isinstance(memory.get("checked_result"), dict) or not memory["checked_result"]):
        raise Core0Error("timer audit lacks meaningful volatile checked-RAM evidence")
    machine = _object(audit.get("timer_machine_audit"), "timer final machine audit")
    invariants = {"approved_resume_pairs": 2, "compiled_gp_tp_free": True,
        "compiled_privileged_instructions": 0, "compiled_functions": 80,
        "fatal_stackless_self_loops": 2, "startup_functions": 16,
        "timer_functions": 7, "timer_mmio_accesses": 3,
        "timer_mmio_width_bits": 64, "timer_fence_operations": 14,
        "machine_csr_operations": 28,
        "mutation": manifest["timer_mutation"]["identity"]}
    for key, expected in invariants.items():
        _same_evidence(machine.get(key), expected, f"machine {key}")
    expected_body_hashes = dict(TIMER_MACHINE_BODY_SHA256)
    if manifest["timer_mutation"]["identity"] == "disable-timer-arming":
        expected_body_hashes["core0_timer_set_compare"] = DISABLE_ARMING_MACHINE_BODY_SHA256
    _same_evidence(machine.get("timer_machine_body_sha256"), expected_body_hashes,
        "complete final timer primitive bodies")
    _same_evidence(machine.get("timer_start_machine_body_sha256"), {
        "O0": "9a46933e45b7e67131862fb81f3eae09a6f23d80570d98195ea21c3f9e7c1653",
        "O2": "c28069c5eb66e5c6bfaad03ecbbf3f740d447d345ad671cdc08751b2c36a9407",
    }[optimization], "profile-specific complete machine entry body")
    _same_evidence(machine.get("timer_mmio_machine"), {
        "access_count": 3, "width_bits": 64, "compiled_program_accesses": 0,
        "all_inferred_accesses_are_approved": True,
        "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof",
        "accesses": [
            {"function": function, "instruction": instruction, "address": address,
             "machine_address": machine_address, "width_bits": 64}
            for function, instruction, address, machine_address in (
                ("_start", "sd", "0x02004000", "0x80000194"),
                ("core0_timer_read_time", "ld", "0x0200bff8", "0x800017bc"),
                ("core0_timer_set_compare", "sd", "0x02004000", "0x800017d4"),
            )
        ],
    }, "complete final machine CLINT access inventory")
    slots = dict.fromkeys(TIMER_STARTUP_FUNCTIONS, 0)
    slots.update({"_start": 16, "core0_trap_vector": 75,
        "core0_trap_ecall": 106, "core0_trap_breakpoint": 106,
        "core0_timer_probe": 106, "core0_timer_read_time": 1,
        "core0_timer_set_compare": 1})
    _same_evidence(machine.get("machine_slot_sequences"), slots, "full machine memory-slot closure")
    csr = {"_start": 5, "core0_trap_vector": 12, "core0_trap_ecall": 1,
        "core0_trap_breakpoint": 1, "core0_trap_unexpected_ecall": 1,
        "core0_timer_read_pending": 1, "core0_irq_save_disable": 1,
        "core0_irq_restore": 2, "core0_timer_set_interrupt": 2, "core0_timer_probe": 2}
    _same_evidence(machine.get("machine_csr_by_function"), csr, "full machine CSR closure")
    _same_evidence(machine.get("timer_probe"), {"iterations": 65536,
        "caller_saves": 16, "snapshot_registers": 31, "memory_slots": 106,
        "mie_window": "after sentinels, bounded counter only, before snapshots"},
        "bounded asynchronous probe")
    _same_evidence(machine.get("startup"), {
        "mutation": manifest["timer_mutation"]["identity"],
        "startup_compare_parked": True, "timer_functions": 7,
        "timer_mmio_width_bits": 64, "timer_probe_iterations": 65536,
        "probe_registers": 31, "csr_roles": ["mstatus.MIE", "mie.MTIE", "mip.MTIP"],
        "synchronous_trap_substrate": "exact core0-v0.6 structured sequence"},
        "startup shutdown/restore invariants")
    _same_evidence(machine.get("layout"), {"frame_bytes": 288, "canaries": 6,
        "regions": {"trap_stack": [0x80810000, 0x4000],
            "trap_probe_context": [0x80815000, 0x1000],
            "trap_probe_stack": [0x80818000, 0x1000]}}, "frame/canary layout")
    accesses = [{"operation": operation, "function": function,
        "instruction": instruction, "address": f"0x{address:08x}",
        "fence_before": True, "fence_after": True}
        for operation, function, instruction, address in TIMER_MACHINE_ACCESS_SEQUENCE]
    _same_evidence(audit.get("device_machine_audit"), {"access_count": 4,
        "byte_accesses_only": True, "ordered_fence_calls": 8,
        "denied_region_metadata_materializations":
            sum(TIMER_MACHINE_DENIED_METADATA.values()) if optimization == "O0" else 0,
        "register_use_audit": {"inferred_uart_accesses": 4,
            "all_inferred_accesses_are_approved": True,
            "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
        "fence_implementation": "fence iorw,iorw; ret", "accesses": accesses},
        "final UART byte access/fence/denial closure")
    stack = _object(audit.get("stack_sizes"), "timer stack audit")
    graph = _object(stack.get("call_graph"), "timer stack call graph")
    if graph.get("acyclic") is not True or graph.get("dynamic_alloca") is not False:
        raise Core0Error("timer audit lacks an acyclic static stack call graph")
    _same_evidence(graph.get("stack_limit_bytes"), 65536, "stack limit")
    frames = _object(graph.get("frame_chains"), "timer stack frame chains")
    for key, entry, root, extras in (
        ("foreground", "core0_main", manifest["roots"][0]["llvm"],
            {"capacity_bytes": 65520, "stack_region_bytes": 65536, "low_canary_bytes": 16,
             "machine_entry": "core0_main"}),
        ("trap_dispatcher", manifest["roots"][1]["llvm"], manifest["roots"][1]["llvm"],
            {"capacity_bytes": 16048, "trap_frame_bytes": 288,
             "outgoing_argument_bytes": 16, "usable_trap_stack_bytes": 16352}),
    ):
        record = _object(graph.get(key), f"timer {key} stack chain")
        size, chain = record.get("bytes"), record.get("chain")
        if (type(size) is not int or not 0 <= size <= extras["capacity_bytes"]
                or not isinstance(chain, list) or not chain or chain[0] != entry
                or root not in chain or any(not isinstance(name, str) or not name for name in chain)):
            raise Core0Error(f"timer audit {key} stack chain is missing, oversized or unbound")
        _same_evidence({name: record.get(name) for name in extras}, extras, f"{key} stack partition")
        _same_evidence(record.get("checked_root"), root, f"{key} checked root")
        _same_evidence(frames.get(entry), {"bytes": size, "chain": chain}, f"{key} frame-chain binding")


def validate_image_binding(image: Path, *, root: Path | None = None,
                           mutation: int = 0) -> dict[str, object]:
    corpus.validate_mutation(mutation)
    root = repo_root() if root is None else root.resolve()
    directory = image.parent
    if image.name != "image.elf" or not image.is_file():
        raise Core0Error("timer runner requires the built image.elf")
    manifest = _object(load_json(directory / "timer-suite-manifest.json"), "timer manifest")
    abi = _object(load_json(directory / "timer-test-abi.json"), "timer ABI")
    build = _object(load_json(directory / "build.json"), "timer build")
    provenance = _object(load_json(directory / "provenance.json"), "timer provenance")
    audit = _object(load_json(directory / "audit.json"), "timer audit")
    _validate_manifest(manifest, abi)
    for value in (manifest, build, provenance, audit):
        if value.get("artifact_category") != corpus.ARTIFACT_CATEGORY:
            raise Core0Error("timer image has the wrong artifact category")
    if manifest.get("contract_version") != corpus.PROFILE or manifest.get("test_abi") != corpus.TEST_ABI:
        raise Core0Error("timer image has the wrong profile or ABI")
    expected_roots = [("foreground", []), ("dispatch", ["u64"] * 9)]
    roots = manifest.get("roots")
    if not isinstance(roots, list) or len(roots) != 2:
        raise Core0Error("timer image lacks its exact two roots")
    for item, (name, args) in zip(roots, expected_roots, strict=True):
        if not isinstance(item, dict) or item.get("source") != f"Lemma.Examples.Foundation.Timer.{name}" or item.get("signature") != {"args": args}:
            raise Core0Error("timer root source identity/signature differs")
    if manifest.get("timer_mutation") != mutation_metadata(mutation):
        raise Core0Error("timer image mutation does not match the requested execution")
    for label, value, schema in (("build", build, 1), ("audit", audit, 1), ("provenance", provenance, 2)):
        if type(value.get("schema_version")) is not int or value["schema_version"] != schema:
            raise Core0Error(f"timer {label} schema identity differs")
    if build.get("status") != "pass" or audit.get("status") != "pass":
        raise Core0Error("timer image lacks a successful build and audit")
    _validate_hash_catalog(directory, build.get("artifacts"), BUILD_ARTIFACTS, "timer build")
    _validate_hash_catalog(directory, audit.get("hashes"), AUDIT_ARTIFACTS, "timer audit")
    commit, optimization = provenance.get("source_commit"), provenance.get("optimization")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Core0Error("timer provenance lacks a full source commit")
    dirty, paths = provenance.get("dirty_tree"), provenance.get("dirty_paths")
    if not isinstance(dirty, bool) or not isinstance(paths, list) or any(not isinstance(path, str) or not path for path in paths) or dirty != bool(paths):
        raise Core0Error("timer provenance dirty-tree identity differs")
    if optimization not in ("O0", "O2") or build.get("optimization") != optimization or audit.get("optimization") != optimization or audit.get("source_commit") != commit or audit.get("dirty_tree") is not dirty or audit.get("provenance_schema_version") != 2:
        raise Core0Error("timer build/audit/provenance source identities differ")
    source_inputs(directory, root)
    linked = provenance.get("linked_inputs")
    if not isinstance(linked, list) or len(linked) != 2 or build.get("linked_inputs") != linked or audit.get("linked_inputs") != linked:
        raise Core0Error("timer build/audit/provenance object identities differ")
    kinds = {"startup.o": "lean-structured-timer-startup", "program.o": "test-timer-suite-llvm"}
    seen: set[str] = set()
    for item in linked:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or item["path"] not in kinds or item["path"] in seen:
            raise Core0Error("timer provenance names an unknown/duplicate linked object")
        name = item["path"]
        if item.get("kind") != kinds[name] or item.get("sha256") != sha256(directory / name):
            raise Core0Error("timer linked object kind/hash differs")
        seen.add(name)
    if audit.get("manifest") != manifest or audit.get("timer_test_abi") != abi:
        raise Core0Error("timer audit does not bind the current manifest/ABI")
    _validate_timer_audit(audit, manifest, optimization)
    return {"manifest": manifest, "abi": abi, "build": build, "provenance": provenance,
            "audit_sha256": sha256(directory / "audit.json")}


def image_machine_info(image: Path, *, root: Path) -> dict[str, object]:
    output = checked(("llvm-nm", "--defined-only", "--numeric-sort", str(image)),
                     cwd=root, timeout_seconds=30).stdout.decode("ascii")
    symbols: dict[str, int] = {}
    for line in output.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+)\s+\S\s+(\S+)", line.strip())
        if match and match[2] in SITE_SYMBOLS:
            if match[2] in symbols:
                raise Core0Error("duplicate required timer symbol")
            symbols[match[2]] = int(match[1], 16)
    if symbols.keys() != SITE_SYMBOLS:
        raise Core0Error("timer ELF omits required trap/probe symbols")
    for prefix in ("ecall", "breakpoint"):
        if symbols[f"__trap_{prefix}_resume"] != symbols[f"__trap_{prefix}_site"] + 4:
            raise Core0Error("timer ELF synchronous continuation length differs")
    text = checked(("llvm-readelf", "--program-headers", "--wide", str(image)),
                   cwd=root, timeout_seconds=30).stdout.decode("ascii")
    segments = parse_load_segments(text)
    executable = []
    for segment in segments:
        if "E" in str(segment["flags"]):
            start, size = int(segment["virtual_address"]), int(segment["memory_size"])
            if "W" in str(segment["flags"]) or size <= 0 or not 0x80000000 <= start < start + size <= 0x807F0000:
                raise Core0Error("timer ELF executable segment is writable or outside the image")
            executable.append([start, start + size])
    if not executable:
        raise Core0Error("timer ELF has no executable range")
    return {"symbols": symbols, "executable_ranges": executable}


def parse_frames(data: bytes) -> list[dict[str, int]]:
    if len(data) % 24 or len(data) > 88 * 24:
        raise TimerRunFailure("protocol-mismatch", "truncated, extra or over-budget timer frames")
    frames = []
    for offset in range(0, len(data), 24):
        frame = data[offset:offset + 24]
        if frame[:4] != b"LMS6" or frame[4] != 1 or frame[6:8] != b"\x08\x00" or frame[5] not in (0, 20, 21):
            raise TimerRunFailure("protocol-mismatch", "invalid timer response framing/version/status")
        identifier, value = struct.unpack_from("<QQ", frame, 8)
        frames.append({"id": identifier, "status": frame[5], "value": value})
    return frames


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise TimerRunFailure("behavior-mismatch", detail)


def validate_transcript(case: corpus.TimerCase, stdout: bytes, returncode: int,
                        machine: dict[str, object], *, mutation: int = 0) -> dict[str, object]:
    exit_code = corpus.expected_exit(case, mutation=mutation)
    if not stdout.startswith(corpus.READY):
        raise TimerRunFailure("protocol-mismatch", "missing or incorrect READY banner")
    frames = parse_frames(stdout[len(corpus.READY):])
    if returncode != exit_code:
        raise TimerRunFailure("target-exit-mismatch", f"expected exit {exit_code}, got {returncode}")
    if mutation:
        expected = [{"id": corpus.FAILURE_ID, "status": exit_code,
                     "value": corpus.RESTORE_MASK if mutation == 1 else 0}]
        _require(frames == expected, "timer mutant lacks the exact live context/missing-event result")
        return {"outcome": "verified-behavioral-context-mismatch" if mutation == 1 else "verified-missing-hardware-interrupt",
                "expected_exit": exit_code, "frames": frames}
    if exit_code:
        _require(frames == [], "semantic timer rejection emitted unexpected frames")
        return {"outcome": "verified-semantic-rejection", "expected_exit": exit_code, "frames": frames}
    _require(len(frames) >= 24, "timer success omits its full stat frame set")
    _require([frame["id"] for frame in frames[:24]] == list(corpus.STAT_IDS) and all(frame["status"] == 0 for frame in frames),
             "timer stat/dump frame IDs or statuses differ")
    stats = dict(zip(corpus.STAT_FIELDS, (frame["value"] for frame in frames[:24]), strict=True))
    count, head, tail = stats["irq_count"], stats["head"], stats["tail"]
    _require(case.goal <= count < 1_000_000, "required hardware IRQ count was not observed")
    _require(0 < head <= count and tail == head and head + stats["overflow"] == count,
             "ring head/tail/drop accounting differs from hardware IRQ count")
    _require(stats["pending_witness"] == 1 and stats["context_mask"] == stats["guard_mask"] == 0,
             "pending/context/guard witnesses differ")
    # Pending deassertion may be delayed after the parked compare write. The
    # canonical observed bit is retained, not used as an immediate-clear oracle.
    _require(stats["before"] == stats["after"] == count and stats["real_pending"] in (0, 1),
             "timer continued delivering after shutdown or reported a noncanonical pending bit")
    _require(stats["maximum_catch_up"] <= 1 and stats["spurious"] <= count,
             "ISR catch-up bound or spurious accounting differs")
    _require(stats["last_consumed_time"] <= stats["last_isr_time"] <= stats["real_time"] <= corpus.MAXIMUM_TIME,
             "hardware/ISR/consumed time order differs")
    _require(stats["last_isr_time"] < stats["deadline"] <= corpus.MAXIMUM_TIME,
             "last programmed deadline does not advance nonwrapping beyond the ISR time")
    quanta = stats["outer_quanta"]
    _require(quanta <= corpus.MAXIMUM_QUANTA and (case.goal < 32 or quanta > 0),
             "useful foreground work was absent or exceeded its semantic budget")
    _require(stats["checksum"] == corpus.checksum(case.seed, quanta), "foreground checksum differs from independent fold")
    records = min(head, corpus.RING_CAPACITY)
    dump = frames[24:]
    _require(len(dump) == records * 4 and [frame["id"] for frame in dump] == list(range(corpus.RING_BASE_ID, corpus.RING_BASE_ID + records * 4)),
             "physical timer ring dump is incomplete, duplicated or misordered")
    physical = [dict(zip(("sequence", "time", "pc", "cause"),
        (frame["value"] for frame in dump[index:index + 4]), strict=True))
        for index in range(0, len(dump), 4)]
    start = (head - records) % corpus.RING_CAPACITY
    chronological = physical[start:] + physical[:start]
    ranges = machine.get("executable_ranges")
    if not isinstance(ranges, list) or not ranges:
        raise TimerRunFailure("image-or-harness-rejection", "ELF executable ranges are unavailable")
    previous_sequence, previous_time = 0, 0
    for record in chronological:
        _require(previous_sequence < record["sequence"] <= count and previous_time <= record["time"] <= stats["last_isr_time"],
                 "retained timer sequence/time does not progress monotonically")
        _require(record["pc"] % 4 == 0 and any(start <= record["pc"] < stop for start, stop in ranges),
                 "retained interrupted PC is unaligned or outside executable ELF memory")
        _require(record["cause"] == corpus.TIMER_CAUSE, "retained event is not a hardware machine-timer interrupt")
        previous_sequence, previous_time = record["sequence"], record["time"]
    last = chronological[-1]
    _require((stats["last_ring_sequence"], stats["last_ring_time"], stats["last_ring_pc"], stats["last_ring_cause"]) ==
             (last["sequence"], last["time"], last["pc"], last["cause"]), "last-ring fields do not match retained raw words")
    _require((stats["last_consumed_sequence"], stats["last_consumed_time"]) == (last["sequence"], last["time"]),
             "last consumed record does not match the drained ring")
    if case.scenario in (0, 2, 3):
        _require(stats["overflow"] > 0, "required bounded-ring overflow did not occur")
    if case.scenario == 2:
        _require(stats["skipped"] > 0, "forced catch-up did not record skipped nominal periods")
    if case.scenario == 4:
        _require(head > corpus.RING_CAPACITY, "interleaved foreground consumption did not wrap the ring")
    return {"outcome": "verified-positive", "expected_exit": 0, "frames": frames,
            "stats": stats, "physical_ring": physical, "chronological_ring": chronological,
            "independent_checksum": stats["checksum"]}


def qemu_argv(image: Path, fixture: Path) -> tuple[str, ...]:
    return ("qemu-system-riscv64", "-machine", "virt,acpi=off", "-accel", "tcg", "-cpu", "rv64",
        "-smp", "1", "-m", "128M", "-bios", "none", "-kernel", str(image), "-nodefaults",
        "-nic", "none", "-display", "none", "-serial", "stdio", "-monitor", "none",
        "-no-reboot", "-seed", "1", "-device",
        f"loader,file={fixture},addr=0x{corpus.FIXTURE_ADDRESS:x},force-raw=on")


def run_case(*, root: Path, image: Path, case: corpus.TimerCase, output_dir: Path,
             timeout_seconds: float = 60, mutation: int = 0, clean: bool = False) -> dict[str, object]:
    root, image, output_dir = root.resolve(), image.resolve(), output_dir.resolve()
    invalidate_output_file(output_dir / RESULT_FILE, root)
    invalidate_output_file(output_dir / (RESULT_FILE + ".tmp"), root)
    prepare_output_directory(output_dir, root, clean=clean)
    report: dict[str, object] = {"schema_version": 1, "status": "FAIL", "case": case.name,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "mutation": mutation,
        "started_at": datetime.now(timezone.utc).isoformat(), "timeout_seconds": timeout_seconds}
    stdout, stderr = b"", b""
    process: subprocess.Popen[bytes] | None = None
    started = time.monotonic()
    try:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds < float("inf"):
            raise TimerRunFailure("harness-input-failure", "timeout must be finite and positive")
        corpus.expected_exit(case, mutation=mutation)
        binding = validate_image_binding(image, root=root, mutation=mutation)
        require_tools(("qemu-system-riscv64", "llvm-nm", "llvm-readelf"))
        machine = image_machine_info(image, root=root)
        fixture = output_dir / "runtime-input.bin"
        fixture.write_bytes(corpus.fixture_bytes(case))
        argv = qemu_argv(image, fixture)
        report.update(image=str(image), image_sha256=sha256(image), argv=list(argv),
            fixture=str(fixture), fixture_sha256=sha256(fixture), fixture_created_after_image_binding=True,
            runtime_input={key: getattr(case, key) for key in ("seed", "goal", "period", "scenario")},
            machine=machine, binding=binding)
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        report["pid"] = process.pid
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report.update(returncode=process.returncode,
                timeout_cleanup={"process_group_killed": True, "process_reaped": process.poll() is not None})
            raise TimerRunFailure("target-timeout", "QEMU exceeded the execution deadline") from error
        report["returncode"] = process.returncode
        if stderr:
            raise TimerRunFailure("emulator-stderr", "QEMU emitted unexpected stderr; see stderr.bin")
        observed = validate_transcript(case, stdout, process.returncode, machine, mutation=mutation)
        report.update(observed, status="PASS")
    except (Core0Error, OSError, ValueError, UnicodeError, TypeError) as error:
        category = error.category if isinstance(error, TimerRunFailure) else "image-or-harness-rejection"
        report.update(outcome=category, detail=str(error))
        raise TimerRunFailure(category, str(error), report) from error
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report.update(returncode=process.returncode, exception_cleanup_reaped=True)
        (output_dir / "uart.bin").write_bytes(stdout)
        (output_dir / "stderr.bin").write_bytes(stderr)
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
            elapsed_seconds=time.monotonic() - started,
            raw_artifacts={name: sha256(output_dir / name) for name in ("uart.bin", "stderr.bin")})
        temporary = output_dir / (RESULT_FILE + ".tmp")
        write_json(temporary, report)
        temporary.replace(output_dir / RESULT_FILE)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    for field in ("seed", "goal", "period"):
        parser.add_argument(f"--{field}", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--scenario", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--mutation", type=int, choices=(0, 1, 2), default=0)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        report = run_case(root=repo_root(), image=args.image, output_dir=args.output_dir,
            case=corpus.TimerCase("single-case", args.seed, args.goal, args.period, args.scenario),
            mutation=args.mutation, timeout_seconds=args.timeout, clean=args.clean)
    except (Core0Error, OSError, ValueError) as error:
        print(f"TIMER RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
