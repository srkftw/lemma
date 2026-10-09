#!/usr/bin/env python3
"""Fresh-boot, bounded Gate 7 QEMU execution with exact transcript checks."""
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

import gate7_corpus as corpus
from audit_core0 import (TRAP_MACHINE_ACCESS_SEQUENCE, TRAP_MACHINE_DENIED_METADATA,
                         TRAP_SUITE_REQUIRED_ARTIFACTS)
from audit_trap import TRAP_CONTRACT
from build_core0 import TRAP_SUITE_GENERATED_BY_LEAN, invalidate_output_file, prepare_output_directory
from core0_common import Core0Error, checked, load_json, repo_root, require_tools, sha256, write_json

RESULT_FILE = "run.json"
SITE_SYMBOLS = ("__trap_ecall_site", "__trap_ecall_resume", "__trap_breakpoint_site",
                "__trap_breakpoint_resume", "__trap_unexpected_ecall_site",
                "__trap_illegal_instruction_site")
BUILD_ARTIFACTS = frozenset(TRAP_SUITE_GENERATED_BY_LEAN) | {
    "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map",
    "platform.dtb", "platform.dts", "provenance.json",
}
AUDIT_ARTIFACTS = frozenset(TRAP_SUITE_REQUIRED_ARTIFACTS)
REQUIRED_SOURCE_INPUTS = frozenset({
    "examples/foundation/TrapBuild.lean", "examples/foundation/TrapConformance.lean",
    "examples/foundation/DeviceConformanceSupport.lean",
    "Lemma/Compiler/Test/TrapExport.lean", "Lemma/Machine/TrapPrimitives.lean",
    "Lemma/Machine/TrapLayout.lean", "scripts/build_core0.py", "scripts/core0_common.py",
    "scripts/build_trap_suite.py", "scripts/audit_core0.py", "scripts/audit_trap.py",
    "scripts/check_foundation.py", "scripts/gate7_corpus.py", "scripts/run_trap_case.py",
    "scripts/check_foundation_gate7.py", "examples/foundation/TrapFrontendProbes.lean",
    "examples/foundation/TrapPolicyProbes.lean",
    "examples/foundation/gate7-reject/HiddenExternTrap.lean",
    "examples/foundation/gate7-reject/PureTrapResult.lean",
    "examples/foundation/gate7-reject/StoredTrapContinuation.lean",
    "examples/foundation/gate7-reject/V05Trap.lean",
    "examples/foundation/gate7-reject/rejections.json",
})


class TrapRunFailure(Core0Error):
    def __init__(self, category: str, detail: str, report: dict[str, object] | None = None):
        self.category, self.detail, self.report = category, detail, report
        super().__init__(f"{category}: {detail}")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{label} is not an object")
    return value


def _validate_hash_catalog(directory: Path, value: object, expected: frozenset[str],
                           label: str) -> dict[str, object]:
    hashes = _object(value, f"{label} artifact hashes")
    if set(hashes) != expected:
        raise Core0Error(f"trap {label} artifact catalog differs: missing={sorted(expected - hashes.keys())!r}, "
                         f"unexpected={sorted(hashes.keys() - expected)!r}")
    for name, digest in hashes.items():
        path = directory / name
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise Core0Error(f"malformed trap {label} artifact hash: {name}")
        if not path.is_file() or path.stat().st_size == 0 or path.resolve().parent != directory.resolve():
            raise Core0Error(f"missing, empty or escaped trap {label} artifact: {name}")
        if sha256(path) != digest:
            raise Core0Error(f"stale trap {label} artifact: {name}")
    return hashes


def _validate_source_binding(provenance: dict[str, object], audit: dict[str, object],
                             build: dict[str, object], directory: Path, root: Path) -> None:
    if provenance.get("schema_version") != 2 or isinstance(provenance.get("schema_version"), bool):
        raise Core0Error("trap provenance must use schema 2")
    commit = provenance.get("source_commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise Core0Error("trap provenance lacks a full source commit")
    optimization = provenance.get("optimization")
    if optimization not in ("O0", "O2") or build.get("optimization") != optimization or audit.get("optimization") != optimization:
        raise Core0Error("trap build/audit/provenance optimization identities differ")
    dirty, paths = provenance.get("dirty_tree"), provenance.get("dirty_paths")
    if not isinstance(dirty, bool) or not isinstance(paths, list) or any(not isinstance(path, str) or not path for path in paths) or dirty != bool(paths):
        raise Core0Error("trap provenance dirty-tree identity is malformed")
    if audit.get("schema_version") != 1 or isinstance(audit.get("schema_version"), bool) or audit.get("provenance_schema_version") != 2:
        raise Core0Error("trap machine audit schema identity differs")
    if audit.get("source_commit") != commit or audit.get("dirty_tree") is not dirty:
        raise Core0Error("trap machine audit source identity differs from provenance")
    entries = provenance.get("source_inputs")
    if not isinstance(entries, list) or not entries:
        raise Core0Error("trap provenance lacks source inputs")
    observed: set[str] = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise Core0Error("malformed trap provenance source input")
        name, digest = item["path"], item["sha256"]
        if not isinstance(name, str) or not name or Path(name).is_absolute() or name in observed or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise Core0Error("unsafe/duplicate trap provenance source input")
        source = (root / name).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file() or sha256(source) != digest:
            raise Core0Error(f"stale or escaped trap source input: {name}")
        observed.add(name)
    if not REQUIRED_SOURCE_INPUTS <= observed:
        raise Core0Error("trap provenance omits required source/compiler/machine/host inputs")
    linked = provenance.get("linked_inputs")
    if not isinstance(linked, list) or len(linked) != 2 or build.get("linked_inputs") != linked or audit.get("linked_inputs") != linked:
        raise Core0Error("trap build/audit/provenance linked object identities differ")
    expected_kinds = {"startup.o": "lean-structured-trap-startup", "program.o": "test-trap-suite-llvm"}
    observed_objects: set[str] = set()
    for item in linked:
        if not isinstance(item, dict) or item.get("path") not in expected_kinds:
            raise Core0Error("trap provenance names an unexpected linked object")
        name = item["path"]
        if name in observed_objects or item.get("kind") != expected_kinds[name] or item.get("sha256") != sha256(directory / name):
            raise Core0Error("trap linked object kind/hash identity differs")
        observed_objects.add(name)


def _validate_trap_audit(audit: dict[str, object], manifest: dict[str, object],
                          abi: dict[str, object], optimization: object) -> None:
    if manifest.get("trap_contract") != TRAP_CONTRACT:
        raise Core0Error("trap manifest machine contract differs from the closed audit contract")
    machine = _object(audit.get("trap_machine_audit"), "trap machine audit evidence")
    if machine.get("approved_resume_pairs") != 2 or machine.get("compiled_gp_tp_free") is not True or machine.get("fatal_stackless_self_loops") != 2:
        raise Core0Error("trap machine audit lacks required resume/register/fatal invariants")
    if type(machine.get("compiled_privileged_instructions")) is not int or machine["compiled_privileged_instructions"] != 0:
        raise Core0Error("trap machine audit lacks compiled privileged-instruction exclusion")
    expected_slots = {"core0_trap_vector": 75, "core0_trap_ecall": 106,
                      "core0_trap_breakpoint": 106}
    if machine.get("machine_slot_sequences") != expected_slots or machine.get("machine_csr_operations") != 11:
        raise Core0Error("trap machine audit full-context slot/CSR counts differ")
    compiled = machine.get("compiled_functions")
    if type(compiled) is not int or compiled != 48:
        raise Core0Error("trap machine audit compiled function closure differs")
    expected_startup = {"restore_mutation": manifest["restore_mutation"]["identity"],
        "frame_bytes": 288, "integer_registers": 31, "csr_snapshots": 5,
        "probe_registers": 31, "canaries": 6}
    if machine.get("startup") != expected_startup:
        raise Core0Error("trap machine audit startup/context evidence differs")
    layout = _object(machine.get("layout"), "trap machine audit layout evidence")
    if layout.get("frame_bytes") != 288 or layout.get("canaries") != 6:
        raise Core0Error("trap machine audit frame/canary evidence differs")
    ir = _object(audit.get("trap_ir_audit"), "trap machine audit IR evidence")
    expected_calls = {"core0_trap_ecall": 3, "core0_trap_breakpoint": 1,
                      "core0_trap_unexpected_ecall": 1, "core0_trap_illegal_instruction": 1}
    if ir.get("optimization") != optimization or ir.get("trap_calls") != expected_calls:
        raise Core0Error("trap machine audit IR profile/call catalog differs")
    if not isinstance(ir.get("memory"), dict) or not ir["memory"]:
        raise Core0Error("trap machine audit lacks checked-RAM evidence")
    operations = ["uart.lsr.read8", "uart.thr.write8", "uart.lsr.read8", "uart.fcr.enable-reset"]
    expected_device = {label: {"operations": operations, "accesses": 4} for label in ("pre", "post")}
    if ir.get("device") != expected_device:
        raise Core0Error("trap machine audit UART operation evidence differs")
    device = _object(audit.get("device_machine_audit"), "trap final UART machine audit")
    expected_accesses = [{"operation": operation, "function": function,
        "instruction": instruction, "address": f"0x{address:08x}",
        "fence_before": True, "fence_after": True}
        for operation, function, instruction, address in TRAP_MACHINE_ACCESS_SEQUENCE]
    count = len(expected_accesses)
    denied = sum(TRAP_MACHINE_DENIED_METADATA.values()) if optimization == "O0" else 0
    expected_device_machine = {"access_count": count, "byte_accesses_only": True,
        "ordered_fence_calls": 2 * count,
        "denied_region_metadata_materializations": denied,
        "register_use_audit": {"inferred_uart_accesses": count,
            "all_inferred_accesses_are_approved": True,
            "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
        "fence_implementation": "fence iorw,iorw; ret", "accesses": expected_accesses}
    if device != expected_device_machine:
        raise Core0Error("trap final UART machine audit sequence/count/ordering evidence differs")
    if audit.get("trap_test_abi") != abi:
        raise Core0Error("trap machine audit is not bound to the current trap ABI")


def validate_image_binding(image: Path, *, mutant: bool = False, root: Path | None = None) -> dict[str, object]:
    directory = image.parent
    root = repo_root() if root is None else root.resolve()
    if image.resolve() != (directory / "image.elf").resolve() or not image.is_file():
        raise Core0Error("trap runner requires the built image.elf")
    manifest = _object(load_json(directory / "trap-suite-manifest.json"), "trap manifest")
    abi = _object(load_json(directory / "trap-test-abi.json"), "trap ABI")
    build = _object(load_json(directory / "build.json"), "build record")
    provenance = _object(load_json(directory / "provenance.json"), "provenance")
    audit = _object(load_json(directory / "audit.json"), "machine audit")
    for value in (manifest, build, provenance, audit):
        if value.get("artifact_category") != corpus.ARTIFACT_CATEGORY:
            raise Core0Error("trap image has the wrong artifact category")
    if build.get("status") != "pass" or audit.get("status") != "pass":
        raise Core0Error("trap image lacks a successful build and machine audit")
    if build.get("schema_version") != 1 or isinstance(build.get("schema_version"), bool):
        raise Core0Error("trap build record schema identity differs")
    if manifest.get("contract_version") != corpus.PROFILE or manifest.get("test_abi") != corpus.TEST_ABI:
        raise Core0Error("trap manifest has the wrong profile/ABI")
    roots = manifest.get("roots")
    if not isinstance(roots, list) or len(roots) != 2:
        raise Core0Error("trap manifest does not contain the exact foreground/dispatcher roots")
    for item, name, arguments in zip(roots, ("foreground", "dispatch"), ([], ["u64"] * 9), strict=True):
        if not isinstance(item, dict) or item.get("source") != f"Lemma.Examples.Foundation.Trap.{name}" or item.get("signature") != {"args": arguments}:
            raise Core0Error("trap root source identity/signature differs")
    operations = manifest.get("used_trap_ops")
    expected_operations = {
        "trap.ecall": ("core0_trap_ecall", "trapEcall"),
        "trap.breakpoint": ("core0_trap_breakpoint", "trapBreakpoint"),
        "trap.unexpected-ecall": ("core0_trap_unexpected_ecall", "trapUnexpectedEcall"),
        "trap.illegal-instruction": ("core0_trap_illegal_instruction", "trapIllegalInstruction"),
    }
    if not isinstance(operations, list) or len(operations) != 4:
        raise Core0Error("trap manifest lacks its closed four-operation catalog")
    observed_operations = {}
    for item in operations:
        if not isinstance(item, dict) or not isinstance(item.get("stable_id"), str) or item["stable_id"] in observed_operations:
            raise Core0Error("malformed/duplicate trap operation")
        observed_operations[item["stable_id"]] = item
    expected_catalog = {identifier: {"stable_id": identifier, "llvm_symbol": symbol,
                        "source_identity": f"Lemma.Core0.Memory.Action.{source}",
                        "effects": ["sync-trap", "machine-state"], "arguments": [], "result": "u64-context-mask"}
                        for identifier, (symbol, source) in expected_operations.items()}
    if observed_operations != expected_catalog:
        raise Core0Error("trap operation source/effect/ABI catalog differs")
    expected_abi = {
        "schema_version": 1, "contract_version": corpus.PROFILE, "name": corpus.TEST_ABI,
        "byte_order": "little-endian", "ready": corpus.READY.decode("ascii"),
        "runtime_fixture_address": "0x0000000081000000", "runtime_fixture_bytes": 24,
        "runtime_fields": ["seed:u64@0", "count:u64@8", "scenario:u64@16"],
        "maximum_count": 64, "response_bytes": 24, "response_magic": "LMS6",
        "result_ids": list(corpus.RESULT_IDS), "fatal_ids": list(corpus.FATAL_IDS),
        "context_failure_id": corpus.MUTANT_ID,
        "scenarios": {"0": "control-and-interrupted-fold", "1": "unauthorized-ecall",
                      "2": "illegal-instruction", "4": "nested-ecall-in-compiled-dispatch"},
    }
    if abi != expected_abi:
        raise Core0Error("trap ABI differs from the closed runner contract")
    expected_mutation = {"identity": "restore-s3-from-s4" if mutant else "none",
                         "production_selectable": False, "transform_stage": "structured-machine-restore",
                         "match_count": 1 if mutant else 0}
    if manifest.get("restore_mutation") != expected_mutation:
        raise Core0Error("trap image restore mutation does not match the requested execution")
    if audit.get("manifest") != manifest:
        raise Core0Error("machine audit is not bound to the current trap manifest")
    _validate_hash_catalog(directory, build.get("artifacts"), BUILD_ARTIFACTS, "build")
    _validate_hash_catalog(directory, audit.get("hashes"), AUDIT_ARTIFACTS, "machine audit")
    _validate_source_binding(provenance, audit, build, directory, root)
    _validate_trap_audit(audit, manifest, abi, build.get("optimization"))
    return {"manifest": manifest, "abi": abi, "build": build,
            "provenance": provenance, "audit_sha256": sha256(directory / "audit.json")}


def symbol_addresses(image: Path, *, root: Path) -> dict[str, int]:
    output = checked(("llvm-nm", "--defined-only", "--numeric-sort", str(image)),
                     cwd=root, timeout_seconds=30).stdout.decode("ascii")
    found: dict[str, int] = {}
    for line in output.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]+)\s+\S\s+(\S+)", line.strip())
        if match and match[2] in SITE_SYMBOLS:
            if match[2] in found:
                raise Core0Error(f"duplicate trap site symbol: {match[2]}")
            found[match[2]] = int(match[1], 16)
    if set(found) != set(SITE_SYMBOLS):
        raise Core0Error("ELF does not contain the exact required trap site/resume symbols")
    for prefix in ("ecall", "breakpoint"):
        if found[f"__trap_{prefix}_resume"] != found[f"__trap_{prefix}_site"] + 4:
            raise Core0Error("authorized trap site/resume are not exactly four bytes apart")
    return found


def parse_frames(data: bytes) -> list[dict[str, int]]:
    if len(data) % 24:
        raise TrapRunFailure("protocol-mismatch", "truncated or extra trap response bytes")
    frames = []
    for offset in range(0, len(data), 24):
        frame = data[offset:offset + 24]
        if frame[:4] != b"LMS6" or frame[4] != 1 or frame[6:8] != b"\x08\x00":
            raise TrapRunFailure("protocol-mismatch", "invalid trap response framing/version/flags")
        status = frame[5]
        if status not in (0, 18, 20):
            raise TrapRunFailure("protocol-mismatch", f"unexpected framed trap status {status}")
        identifier, value = struct.unpack_from("<QQ", frame, 8)
        frames.append({"id": identifier, "status": status, "value": value})
    return frames


def validate_transcript(case: corpus.TrapCase, stdout: bytes, returncode: int,
                        symbols: dict[str, int], *, mutant: bool = False) -> dict[str, object]:
    expected_exit = corpus.expected_exit(case, mutant=mutant)
    if not stdout.startswith(corpus.READY):
        raise TrapRunFailure("protocol-mismatch", "missing or incorrect READY banner")
    frames = parse_frames(stdout[len(corpus.READY):])
    if returncode != expected_exit:
        raise TrapRunFailure("target-exit-mismatch", f"expected exit {expected_exit}, got {returncode}")
    if mutant:
        expected = [{"id": corpus.MUTANT_ID, "status": 20, "value": corpus.MUTANT_MASK}]
        outcome = "verified-behavioral-context-mismatch"
    elif expected_exit == 0:
        values = (corpus.checksum(case.seed, case.count), 2 * case.count, corpus.DENIAL_COUNT, 0)
        expected = [dict(id=identifier, status=0, value=value)
                    for identifier, value in zip(corpus.RESULT_IDS, values, strict=True)]
        outcome = "verified-positive"
    elif expected_exit == 18:
        if len(frames) != 5 or [frame["id"] for frame in frames] != list(corpus.FATAL_IDS) or any(frame["status"] != 18 for frame in frames):
            raise TrapRunFailure("diagnostic-mismatch", "fatal trap did not emit the exact five diagnostic frames")
        cause, pc, mstatus, mtval, mie = (frame["value"] for frame in frames)
        site = "__trap_unexpected_ecall_site" if case.scenario == 1 else "__trap_illegal_instruction_site"
        if cause != (11 if case.scenario == 1 else 2) or pc != symbols[site]:
            raise TrapRunFailure("diagnostic-mismatch", "fatal cause/PC differs from the actual ELF trap site")
        if mstatus & 0x21888 != 0x1800 or mie != 0:
            raise TrapRunFailure("diagnostic-mismatch", "fatal CSR snapshot violates the synchronous M-mode contract")
        if mtval not in ((0,) if case.scenario == 1 else (0, 0x0000000B)):
            raise TrapRunFailure("diagnostic-mismatch", "fatal mtval differs from the permitted ECALL/illegal-word value")
        return {"outcome": "verified-fatal-diagnostic", "frames": frames, "expected_exit": expected_exit,
                "diagnostic_site": site, "diagnostic_pc": pc,
                "mstatus_check": "(mstatus & 0x21888) == 0x1800", "mie": mie}
    else:
        expected = []
        outcome = "verified-nested-fatal" if expected_exit == 19 else "verified-semantic-rejection"
    if frames != expected:
        raise TrapRunFailure("behavior-mismatch", f"trap responses differ: expected {expected!r}, got {frames!r}")
    return {"outcome": outcome, "frames": frames, "expected_exit": expected_exit}


def qemu_argv(image: Path, fixture: Path) -> tuple[str, ...]:
    return ("qemu-system-riscv64", "-machine", "virt,acpi=off", "-accel", "tcg", "-cpu", "rv64",
            "-smp", "1", "-m", "128M", "-bios", "none", "-kernel", str(image), "-nodefaults",
            "-nic", "none", "-display", "none", "-serial", "stdio", "-monitor", "none",
            "-no-reboot", "-seed", "1", "-device",
            f"loader,file={fixture},addr=0x{corpus.FIXTURE_ADDRESS:x},force-raw=on")


def run_case(*, root: Path, image: Path, case: corpus.TrapCase, output_dir: Path,
             timeout_seconds: float = 20.0, mutant: bool = False, clean: bool = False) -> dict[str, object]:
    """Run one image, retaining raw evidence even for timeout/protocol failure."""
    root, image, output_dir = root.resolve(), image.resolve(), output_dir.resolve()
    invalidate_output_file(output_dir / RESULT_FILE, root)
    invalidate_output_file(output_dir / (RESULT_FILE + ".tmp"), root)
    prepare_output_directory(output_dir, root, clean=clean)
    started = datetime.now(timezone.utc).isoformat()
    report: dict[str, object] = {"schema_version": 1, "status": "FAIL", "case": case.name,
                                "started_at": started, "timeout_seconds": timeout_seconds,
                                "artifact_category": corpus.ARTIFACT_CATEGORY, "mutant": mutant}
    stdout, stderr = b"", b""
    process: subprocess.Popen[bytes] | None = None
    start_clock = time.monotonic()
    try:
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or not 0 < timeout_seconds < float("inf"):
            raise TrapRunFailure("harness-input-failure", "timeout must be finite and positive")
        corpus.validate_case(case)
        corpus.expected_exit(case, mutant=mutant)
        binding = validate_image_binding(image, mutant=mutant, root=root)
        require_tools(("qemu-system-riscv64", "llvm-nm"))
        symbols = symbol_addresses(image, root=root)
        # This fixture is deliberately generated only after the build/audit hash
        # closure has been validated, and it contains no expected answer.
        fixture = output_dir / "runtime-input.bin"
        fixture.write_bytes(corpus.fixture_bytes(case))
        argv = qemu_argv(image, fixture)
        report.update(image=str(image), image_sha256=sha256(image), argv=list(argv),
                      fixture=str(fixture), fixture_sha256=sha256(fixture),
                      fixture_created_after_image_binding=True,
                      runtime_input={"seed": case.seed, "count": case.count, "scenario": case.scenario},
                      symbols=symbols, binding=binding)
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        report["pid"] = process.pid
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report.update(returncode=process.returncode, timeout_cleanup={"process_group_killed": True,
                          "process_reaped": process.poll() is not None})
            raise TrapRunFailure("target-timeout", "QEMU exceeded the execution deadline") from error
        report["returncode"] = process.returncode
        if stderr:
            raise TrapRunFailure("emulator-stderr", "QEMU emitted unexpected stderr; see stderr.bin")
        observed = validate_transcript(case, stdout, process.returncode, symbols, mutant=mutant)
        report.update(observed, status="PASS")
    except (Core0Error, OSError, ValueError, UnicodeError) as error:
        category = error.category if isinstance(error, TrapRunFailure) else "image-or-harness-rejection"
        report.update(outcome=category, detail=str(error))
        raise TrapRunFailure(category, str(error), report) from error
    finally:
        # communicate() reaps all normal/timeout executions; this also covers a
        # validation exception after launch without leaving a QEMU process alive.
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            report["returncode"] = process.returncode
            report["exception_cleanup_reaped"] = True
        (output_dir / "uart.bin").write_bytes(stdout)
        (output_dir / "stderr.bin").write_bytes(stderr)
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=time.monotonic() - start_clock,
                      raw_artifacts={name: sha256(output_dir / name) for name in ("uart.bin", "stderr.bin")})
        temporary = output_dir / (RESULT_FILE + ".tmp")
        write_json(temporary, report)
        temporary.replace(output_dir / RESULT_FILE)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--count", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--scenario", type=lambda v: int(v, 0), default=0)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--mutant", action="store_true")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        report = run_case(root=repo_root(), image=args.image,
                          case=corpus.TrapCase("single-case", args.seed, args.count, args.scenario),
                          output_dir=args.output_dir, timeout_seconds=args.timeout,
                          mutant=args.mutant, clean=args.clean)
    except (Core0Error, OSError, ValueError) as error:
        print(f"TRAP RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
