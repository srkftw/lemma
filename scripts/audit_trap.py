#!/usr/bin/env python3
"""Independent fail-closed checks for the Gate 7 synchronous-trap profile."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

import audit_device
import audit_memory
from core0_common import Core0Error


CONTRACT_VERSION = "core0-v0.6"
ARTIFACT_CATEGORY = "test-trap-suite"
TEST_ABI = "lemma-sync-trap-test-v1"
SOURCE_IDENTITY = "Lemma Gate 7 synchronous trap conformance"
FOREGROUND_SOURCE = "Lemma.Examples.Foundation.Trap.foreground"
FOREGROUND_SYMBOL = "core0_action_17"
DISPATCH_SOURCE = "Lemma.Examples.Foundation.Trap.dispatch"
DISPATCH_SYMBOL = "core0_action_20"
RESTORE_ENVIRONMENT = "LEMMA_TRAP_RESTORE_MUTATION"

TRAP_EXTERNALS = {
    "core0_trap_ecall",
    "core0_trap_breakpoint",
    "core0_trap_unexpected_ecall",
    "core0_trap_illegal_instruction",
}
TRAP_STARTUP_FUNCTIONS = {
    "_start",
    "core0_io_fence",
    "core0_trap_vector",
    "core0_trap_fatal_dispatch",
    "core0_trap_double_fault",
    *TRAP_EXTERNALS,
}

TRAP_CONTRACT: dict[str, object] = {
    "schema_version": 1,
    "profile": "m-mode-sync-trap-v1",
    "privileged_spec": "RISC-V Privileged Architecture 20240411; Machine ISA 1.13",
    "privileged_spec_sha256":
        "538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d",
    "frame_bytes": 288,
    "call_alignment": 16,
    "outgoing_argument_bytes": 16,
    "integer_registers": 31,
    "hart_count": 1,
    "nested": False,
    "latch": "mscratch=trap-stack-top in foreground; zero during dispatch",
    "cpu_extensions_disabled": ["Smrnmi", "Smdbltrp"],
    "qemu_feature_normalization": {
        "source": "target/riscv/tcg/tcg-cpu.c",
        "sha256": "562e89fd688a921f9d48d718c60af73b51a7effaf5ec0577b67d0b177d99a7b9",
        "lines": "1630-1646",
    },
    "csr_snapshots": ["mstatus", "mepc", "mcause", "mtval", "mie"],
    "dispatcher_arguments": [
        "cause", "pc", "mstatus", "tval", "mie", "ecall-site", "ecall-resume",
        "breakpoint-site", "breakpoint-resume",
    ],
    "authorized_sites": [
        {
            "cause": 11, "site": "__trap_ecall_site",
            "resume": "__trap_ecall_resume", "instruction_bytes": 4,
        },
        {
            "cause": 3, "site": "__trap_breakpoint_site",
            "resume": "__trap_breakpoint_resume", "instruction_bytes": 4,
        },
    ],
    "fatal_status": 18,
    "double_fault_status": 19,
    "context_mismatch_status": 20,
    "premises": [
        "fixed aligned RAM frame/stack accesses do not fault",
        "authorized M-mode continuation; MPRV=0; MIE=0 through return",
        "no NMI; synchronous faults in latch entry/tail window are not classified exhaustively",
        "compiled code uses neither gp nor tp; no relaxation; no floating/vector state",
    ],
}

TRAP_ABI: dict[str, object] = {
    "schema_version": 1,
    "contract_version": CONTRACT_VERSION,
    "name": TEST_ABI,
    "byte_order": "little-endian",
    "ready": "LEMMA_DEVICE/1\nREADY\n",
    "runtime_fixture_address": "0x0000000081000000",
    "runtime_fixture_bytes": 24,
    "runtime_fields": ["seed:u64@0", "count:u64@8", "scenario:u64@16"],
    "maximum_count": 64,
    "response_bytes": 24,
    "response_magic": "LMS6",
    "result_ids": [0x7101, 0x7102, 0x7103, 0x7104],
    "fatal_ids": [0x7001, 0x7002, 0x7003, 0x7004, 0x7005],
    "context_failure_id": 0x71FF,
    "scenarios": {
        "0": "control-and-interrupted-fold",
        "1": "unauthorized-ecall",
        "2": "illegal-instruction",
        "4": "nested-ecall-in-compiled-dispatch",
    },
}

MACHINE_PRIMITIVES = [
    {"identity": "trap-startup", "effect": "machine-state",
     "implementation": "Lemma.Machine.TrapPrimitives.startup"},
    {"identity": "trap-entry-return", "effect": "machine-state",
     "implementation": "Lemma.Machine.TrapPrimitives.vector"},
    {"identity": "trap-register-probes", "effect": "sync-trap/context-check",
     "implementation": "Lemma.Machine.TrapPrimitives.ecallProbe/breakpointProbe"},
    {"identity": "trap-fatal-fixtures", "effect": "sync-trap",
     "implementation": "Lemma.Machine.TrapPrimitives.unexpectedEcall/illegalInstruction"},
    {"identity": "trap-fatal-finishers", "effect": "vm-termination-mmio",
     "implementation": "Lemma.Machine.TrapPrimitives.fatalDispatch/doubleFault"},
    {"identity": "io-fence", "effect": "ordered-mmio",
     "implementation": "Lemma.Machine.Primitives.ioFence"},
    {"identity": "status-test-harness", "effect": "action-abi/status-coded-vm-termination",
     "implementation": "Lemma.Machine.DeviceHarness.main"},
]

TRAP_OPS = [
    ("trap.unexpected-ecall", "core0_trap_unexpected_ecall",
     "Lemma.Core0.Memory.Action.trapUnexpectedEcall"),
    ("trap.illegal-instruction", "core0_trap_illegal_instruction",
     "Lemma.Core0.Memory.Action.trapIllegalInstruction"),
    ("trap.ecall", "core0_trap_ecall", "Lemma.Core0.Memory.Action.trapEcall"),
    ("trap.breakpoint", "core0_trap_breakpoint",
     "Lemma.Core0.Memory.Action.trapBreakpoint"),
]

SCALAR_FUNCTIONS = (
    ("Lemma.Core0.Memory.RegionId.input", (), "u8"),
    ("Lemma.Examples.Foundation.Device.Support.readyLength", (), "u32"),
    ("Lemma.Examples.Foundation.Device.Support.readyByte", ("u32",), "u8"),
    ("Lemma.Core0.Memory.Status.ok", (), "u8"),
    ("Lemma.Examples.Foundation.Device.Support.pollBudget", (), "u32"),
    ("Lemma.Core0.Memory.Status.iterationStop", (), "u8"),
    ("Lemma.Core0.Memory.Status.txTimeout", (), "u8"),
    ("Lemma.Core0.Device.UART.lsrErrorMask", (), "u8"),
    ("Lemma.Core0.Device.UART.lsrThrEmpty", (), "u8"),
    ("Lemma.Core0.Memory.Status.lineError", (), "u8"),
    ("Lemma.Core0.Memory.RegionId.events", (), "u8"),
    ("Lemma.Core0.Memory.Status.contextMismatch", (), "u8"),
    ("Lemma.Core0.Memory.Status.invalidLength", (), "u8"),
    ("Lemma.Core0.Memory.Status.malformedFrame", (), "u8"),
    ("Lemma.Core0.Memory.RegionId.scratch", (), "u8"),
    ("Lemma.Examples.Foundation.Trap.denialStatus", ("u32",), "u8"),
    ("Lemma.Core0.Memory.RegionId.stack", (), "u8"),
    ("Lemma.Core0.Memory.RegionId.image", (), "u8"),
    ("Lemma.Core0.Memory.RegionId.uart", (), "u8"),
    ("Lemma.Core0.Memory.RegionId.finisher", (), "u8"),
    ("Lemma.Examples.Foundation.Trap.mix", ("u32", "u64"), "u64"),
    ("Lemma.Examples.Foundation.Device.Support.responseByte", ("u32", "u8", "u64", "u64"), "u8"),
    ("Lemma.Core0.Memory.RegionId.output", (), "u8"),
    ("Lemma.Core0.Device.UART.lsrTransmitterEmpty", (), "u8"),
    ("Lemma.Examples.Foundation.Trap.resumeAddress", ("u64",) * 9, "u64"),
    ("Lemma.Core0.Memory.Status.unexpectedTrap", (), "u8"),
)

PRIMITIVE_CONTRACTS = (
    ("u8.eq", ("u8", "u8"), "bool", ("Eq",)),
    ("u32.eq", ("u32", "u32"), "bool", ("Eq",)),
    ("u64.add", ("u64", "u64"), "u64", ("UInt64.add",)),
    ("u8.to-u64.zext", ("u8",), "u64", ("UInt8.toUInt64",)),
    ("u64.to-u8.trunc", ("u64",), "u8", ("UInt64.toUInt8",)),
    ("u8.and", ("u8", "u8"), "u8", ("UInt8.land",)),
    ("u64.eq", ("u64", "u64"), "bool", ("Eq",)),
    ("u64.ule", ("u64", "u64"), "bool", ("UInt64.le",)),
    ("u64.to-u32.trunc", ("u64",), "u32", ("UInt64.toUInt32",)),
    ("u32.ule", ("u32", "u32"), "bool", ("UInt32.le",)),
    ("u32.to-u64.zext", ("u32",), "u64", ("UInt32.toUInt64",)),
    ("u64.xor", ("u64", "u64"), "u64", ("UInt64.xor",)),
    ("u64.mul", ("u64", "u64"), "u64", ("UInt64.mul",)),
    ("u64.shl", ("u64", "u64"), "u64", ("UInt64.shiftLeft",)),
    ("u64.lshr", ("u64", "u64"), "u64", ("UInt64.shiftRight",)),
    ("u8.or", ("u8", "u8"), "u8", ("UInt8.lor",)),
    ("u64.and", ("u64", "u64"), "u64", ("UInt64.land",)),
)

ACTION_FUNCTIONS = (
    ("Lemma.Examples.Foundation.Device.Support.transmitPollStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (), ("mmio-read", "mmio-write", "io-order"), ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendByte", ("u8",), ("Lemma.Examples.Foundation.Device.Support.transmitPollStep",), (), ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.readyStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), ("Lemma.Examples.Foundation.Device.Support.sendByte",), (), ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendReady", (), ("Lemma.Examples.Foundation.Device.Support.readyStep",), (), ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Trap.writeEvent", ("u64", "u64"), (), ("checked-access", "fixed-ram-write"), ("checked-access", "fixed-ram-write")),
    ("Lemma.Examples.Foundation.Trap.controlStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (), (), ()),
    ("Lemma.Examples.Foundation.Trap.denial", ("u32",), ("Lemma.Examples.Foundation.Trap.controlStep",), ("checked-access", "fixed-ram-read", "fixed-ram-write"), ("checked-access", "fixed-ram-read", "fixed-ram-write")),
    ("Lemma.Examples.Foundation.Trap.denialStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), ("Lemma.Examples.Foundation.Trap.denial",), (), ("checked-access", "fixed-ram-read", "fixed-ram-write")),
    ("Lemma.Examples.Foundation.Trap.denialBattery", (), ("Lemma.Examples.Foundation.Trap.denialStep",), ("checked-access", "fixed-ram-read", "fixed-ram-write"), ("checked-access", "fixed-ram-read", "fixed-ram-write")),
    ("Lemma.Examples.Foundation.Device.Support.responseStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), ("Lemma.Examples.Foundation.Device.Support.sendByte",), ("checked-access", "fixed-ram-write"), ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendResponse", ("u8", "u64", "u64"), ("Lemma.Examples.Foundation.Device.Support.responseStep",), (), ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.drainPollStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (), ("mmio-read", "io-order"), ("mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.drain", (), ("Lemma.Examples.Foundation.Device.Support.drainPollStep",), (), ("mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Trap.resultFrames", ("u64", "u64", "u64", "u64"), ("Lemma.Examples.Foundation.Device.Support.sendResponse", "Lemma.Examples.Foundation.Device.Support.drain"), (), ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Trap.interruptedStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (), ("sync-trap", "machine-state"), ("sync-trap", "machine-state")),
    ("Lemma.Examples.Foundation.Trap.runFolds", ("u64", "u32"), ("Lemma.Examples.Foundation.Trap.denialBattery", "Lemma.Examples.Foundation.Trap.resultFrames", "Lemma.Examples.Foundation.Device.Support.sendResponse", "Lemma.Examples.Foundation.Device.Support.drain", "Lemma.Examples.Foundation.Trap.interruptedStep", "Lemma.Examples.Foundation.Trap.controlStep"), ("checked-access", "fixed-ram-read"), ("checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write", "io-order", "sync-trap", "machine-state")),
    ("Lemma.Examples.Foundation.Trap.selectScenario", ("u64", "u64", "u64"), ("Lemma.Examples.Foundation.Trap.runFolds",), ("sync-trap", "machine-state"), ("checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write", "io-order", "sync-trap", "machine-state")),
    (FOREGROUND_SOURCE, (), ("Lemma.Examples.Foundation.Device.Support.sendReady", "Lemma.Examples.Foundation.Trap.writeEvent", "Lemma.Examples.Foundation.Trap.selectScenario"), ("checked-access", "fixed-ram-read", "mmio-write", "io-order"), ("checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write", "io-order", "sync-trap", "machine-state")),
    ("Lemma.Examples.Foundation.Trap.recordSnapshot", ("u64",) * 5, ("Lemma.Examples.Foundation.Trap.writeEvent",), (), ("checked-access", "fixed-ram-write")),
    ("Lemma.Examples.Foundation.Trap.fatalDiagnostic", ("u64",) * 5, ("Lemma.Examples.Foundation.Device.Support.sendResponse", "Lemma.Examples.Foundation.Device.Support.drain"), (), ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    (DISPATCH_SOURCE, ("u64",) * 9, ("Lemma.Examples.Foundation.Trap.recordSnapshot", "Lemma.Examples.Foundation.Trap.writeEvent", "Lemma.Examples.Foundation.Trap.fatalDiagnostic"), ("checked-access", "fixed-ram-read", "sync-trap", "machine-state"), ("checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write", "io-order", "sync-trap", "machine-state")),
)

EFFECT_ORDER = (
    "checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write",
    "io-order", "sync-trap", "machine-state",
)

ITERATIONS = (
    (21, "Lemma.Examples.Foundation.Device.Support.readyStep"),
    (1000000, "Lemma.Examples.Foundation.Device.Support.transmitPollStep"),
    (64, "Lemma.Examples.Foundation.Trap.interruptedStep"),
    (64, "Lemma.Examples.Foundation.Trap.controlStep"),
    (14, "Lemma.Examples.Foundation.Trap.denialStep"),
    (0, "Lemma.Examples.Foundation.Trap.controlStep"),
    (24, "Lemma.Examples.Foundation.Device.Support.responseStep"),
    (1000000, "Lemma.Examples.Foundation.Device.Support.drainPollStep"),
)


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Core0Error(f"{context} is not an object")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Core0Error(f"{context} is not an array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise Core0Error(
            f"{context} keys differ: missing={sorted(expected - set(value))!r}, "
            f"unexpected={sorted(set(value) - expected)!r}"
        )


def _hex64(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{16}", value) is None:
        raise Core0Error(f"{context} is not a canonical 64-bit hexadecimal identity")
    return value


def _body_calls(body: str, prefix: str) -> list[str]:
    return list(dict.fromkeys(re.findall(rf"\({re.escape(prefix)} ([A-Za-z0-9_.]+)", body)))


def _body_direct_effects(body: str) -> list[str]:
    effects: set[str] = set()
    if "(action.check-read-range" in body or "(action.check-write-range" in body:
        effects.add("checked-access")
    if re.search(r"\(action\.load", body):
        effects.update(("checked-access", "fixed-ram-read"))
    if re.search(r"\(action\.store", body):
        effects.update(("checked-access", "fixed-ram-write"))
    if "(action.uart-read-" in body:
        effects.update(("mmio-read", "io-order"))
    if re.search(r"\(action\.uart-(?:write|enable)", body):
        effects.update(("mmio-write", "io-order"))
    if "(action.trap " in body:
        effects.update(("sync-trap", "machine-state"))
    return [effect for effect in EFFECT_ORDER if effect in effects]


def _validate_functions(manifest: Mapping[str, object]) -> dict[str, object]:
    scalars = _list(manifest.get("scalar_functions"), "trap scalar functions")
    actions = _list(manifest.get("action_functions"), "trap Action functions")
    if len(scalars) != len(SCALAR_FUNCTIONS) or len(actions) != len(ACTION_FUNCTIONS):
        raise Core0Error("trap function closure has the wrong cardinality")
    scalar_sources = {source for source, _args, _result in SCALAR_FUNCTIONS}
    for index, (raw, (source, args, result)) in enumerate(zip(scalars, SCALAR_FUNCTIONS)):
        function = _mapping(raw, f"trap scalar function {index}")
        _exact_keys(function, {"source", "llvm", "signature", "dependencies", "body", "noinline"}, f"trap scalar function {source}")
        if function.get("source") != source or function.get("llvm") != f"core0_scalar_{index}":
            raise Core0Error("trap scalar function source/LLVM closure differs")
        signature = _mapping(function.get("signature"), f"trap scalar signature {source}")
        if signature != {"args": list(args), "result": result}:
            raise Core0Error(f"trap scalar signature differs for {source}")
        body = function.get("body")
        dependencies = function.get("dependencies")
        if not isinstance(body, str) or not isinstance(dependencies, list) or function.get("noinline") is not True:
            raise Core0Error(f"trap scalar function metadata is malformed for {source}")
        if dependencies != _body_calls(body, "call") or any(dep not in scalar_sources for dep in dependencies):
            raise Core0Error(f"trap scalar dependency metadata is stale for {source}")

    by_source: dict[str, Mapping[str, object]] = {}
    for index, (raw, contract) in enumerate(zip(actions, ACTION_FUNCTIONS)):
        source, args, dependencies, direct, transitive = contract
        function = _mapping(raw, f"trap Action function {index}")
        _exact_keys(function, {"source", "llvm", "signature", "scalar_dependencies", "action_dependencies", "direct_effects", "transitive_effects", "body", "noinline"}, f"trap Action function {source}")
        if function.get("source") != source or function.get("llvm") != f"core0_action_{index}":
            raise Core0Error("trap Action function source/LLVM closure differs")
        if function.get("signature") != {"args": list(args)} or function.get("noinline") is not True:
            raise Core0Error(f"trap Action signature/preservation differs for {source}")
        body = function.get("body")
        if not isinstance(body, str) or not body.startswith("(action."):
            raise Core0Error(f"trap Action body is malformed for {source}")
        body_action_dependencies = set(_body_calls(body, "action.call")) | set(
            re.findall(r"\bcallback=([A-Za-z0-9_.]+)", body)
        )
        if (
            function.get("action_dependencies") != list(dependencies)
            or body_action_dependencies != set(dependencies)
        ):
            raise Core0Error(f"trap Action dependency metadata is stale for {source}")
        if function.get("direct_effects") != list(direct) or _body_direct_effects(body) != list(direct):
            raise Core0Error(f"trap Action direct effects are stale for {source}")
        if function.get("transitive_effects") != list(transitive):
            raise Core0Error(f"trap Action transitive effects differ for {source}")
        scalar_dependencies = function.get("scalar_dependencies")
        body_scalar_dependencies = _body_calls(body, "call")
        if (
            not isinstance(scalar_dependencies, list)
            or len(scalar_dependencies) != len(set(scalar_dependencies))
            or set(scalar_dependencies) != set(body_scalar_dependencies)
        ):
            raise Core0Error(f"trap Action scalar dependency metadata is stale for {source}")
        if any(dependency not in scalar_sources for dependency in scalar_dependencies):
            raise Core0Error(f"trap Action function {source} references an unknown scalar")
        by_source[source] = function
    for source, _args, dependencies, direct, transitive in ACTION_FUNCTIONS:
        present = set(direct)
        for dependency in dependencies:
            present.update(_list(by_source[dependency].get("transitive_effects"), "callee effects"))
        computed = [effect for effect in EFFECT_ORDER if effect in present]
        if computed != list(transitive):
            raise Core0Error(f"trap Action transitive closure is inconsistent for {source}")
    return {"scalar_functions": len(scalars), "action_functions": len(actions)}


def validate_trap_suite_manifest(value: object) -> dict[str, object]:
    manifest = _mapping(value, "trap-suite manifest")
    _exact_keys(manifest, set(audit_device.TOP_LEVEL_KEYS) | {"trap_contract", "used_trap_ops", "restore_mutation"}, "trap-suite manifest")
    for field, expected in (("schema_version", 1), ("artifact_category", ARTIFACT_CATEGORY), ("contract_version", CONTRACT_VERSION), ("test_abi", TEST_ABI)):
        if manifest.get(field) != expected:
            raise Core0Error(f"trap-suite manifest {field} differs")
    identities = {field: _hex64(manifest.get(field), f"trap-suite {field}") for field in ("suite_id", "source_seed", "runtime_seed")}
    if identities != {
        "suite_id": "76a7494d1d0037c1", "source_seed": "4c454d4d41373037",
        "runtime_seed": "52554e54494d4537",
    }:
        raise Core0Error("trap-suite fixed identities differ")
    if manifest.get("checked_result") != audit_device.CHECKED_RESULT:
        raise Core0Error("trap-suite checked-result ABI differs")
    audit_device._validate_memory_boundary(manifest.get("memory_contract"))
    audit_device.validate_device_contract(_mapping(manifest.get("device_contract"), "device contract"))
    if manifest.get("trap_contract") != TRAP_CONTRACT:
        raise Core0Error("trap machine contract differs from its closed v0.6 contract")
    roots = [
        {"root_id": 1, "source": FOREGROUND_SOURCE, "llvm": FOREGROUND_SYMBOL, "signature": {"args": []}},
        {"root_id": 2, "source": DISPATCH_SOURCE, "llvm": DISPATCH_SYMBOL, "signature": {"args": ["u64"] * 9}},
    ]
    if manifest.get("roots") != roots:
        raise Core0Error("trap-suite root closure differs")
    expected_trap_ops = [
        {"stable_id": stable_id, "llvm_symbol": symbol, "source_identity": source,
         "effects": ["sync-trap", "machine-state"], "arguments": [],
         "result": "u64-context-mask"}
        for stable_id, symbol, source in TRAP_OPS
    ]
    if manifest.get("used_trap_ops") != expected_trap_ops:
        raise Core0Error("trap operation closure differs")
    expected_memory = [audit_memory.MEMORY_OPS[name] for name in sorted({
        "ram.read8", "ram.read32", "ram.read64", "ram.write8", "ram.write32",
        "ram.write64", "ram.check-write-range",
    })]
    if manifest.get("used_memory_ops") != expected_memory:
        raise Core0Error("trap memory-operation closure differs")
    expected_device = [audit_device.DEVICE_OPS[name] for name in (
        "uart.enable-reset-fifo", "uart.write-byte", "uart.read-status",
    )]
    if manifest.get("used_device_ops") != expected_device:
        raise Core0Error("trap device-operation closure differs")
    if manifest.get("machine_primitives") != MACHINE_PRIMITIVES:
        raise Core0Error("trap machine-primitive closure differs")
    expected_primitives = [
        {
            "stable_id": stable_id,
            "signature": {"args": list(args), "result": result},
            "lean_identities": list(identities),
            "effect": "pure",
        }
        for stable_id, args, result, identities in PRIMITIVE_CONTRACTS
    ]
    primitives = _list(manifest.get("used_primitives"), "trap primitive catalog")
    if primitives != expected_primitives:
        raise Core0Error("trap scalar primitive identity/signature closure differs")
    iterations = _list(manifest.get("action_iterations"), "trap Action iterations")
    observed_iterations: list[tuple[int, str]] = []
    for item in iterations:
        iteration = _mapping(item, "trap Action iteration")
        fixed = {
            "stable_id": "action.u64.bounded-fold",
            "source_identity": "Lemma.Core0.Memory.Action.boundedFoldU64",
            "maximum_budget": 1000000,
            "counter": {"type": "u32", "order": "ascending-zero-based"},
            "accumulator": "u64", "contexts": 4, "outcome": "checked-result-v1",
            "exhaustion": {"status": 9, "value": "initial", "callbacks": 0},
        }
        if any(iteration.get(key) != expected for key, expected in fixed.items()):
            raise Core0Error("trap Action iteration contract differs")
        budget, callback = iteration.get("static_budget"), iteration.get("callback")
        if isinstance(budget, bool) or not isinstance(budget, int) or not isinstance(callback, str):
            raise Core0Error("trap Action iteration selector is malformed")
        observed_iterations.append((budget, callback))
    if observed_iterations != list(ITERATIONS):
        raise Core0Error("trap Action iteration site closure differs")
    _validate_functions(manifest)
    mutation = _mapping(manifest.get("restore_mutation"), "trap restore mutation")
    _exact_keys(mutation, {"identity", "production_selectable", "transform_stage", "match_count"}, "trap restore mutation")
    identity = mutation.get("identity")
    expected_count = {"none": 0, "restore-s3-from-s4": 1}.get(identity)
    if expected_count is None or mutation != {
        "identity": identity, "production_selectable": False,
        "transform_stage": "structured-machine-restore", "match_count": expected_count,
    }:
        raise Core0Error("trap restore mutation is outside the exact test-only quarantine")
    return dict(manifest)


def validate_trap_test_abi(value: object, manifest: Mapping[str, object]) -> dict[str, object]:
    abi = _mapping(value, "trap test ABI")
    if dict(abi) != TRAP_ABI:
        raise Core0Error("trap test ABI differs from lemma-sync-trap-test-v1")
    if manifest.get("contract_version") != abi.get("contract_version") or manifest.get("test_abi") != abi.get("name"):
        raise Core0Error("trap test ABI does not match the suite manifest")
    return dict(abi)


def validate_trap_manifest_companions(
    manifest: Mapping[str, object], normalized: str, symbols: str
) -> None:
    if not normalized.endswith("\n") or normalized.splitlines()[0] != f"contract={CONTRACT_VERSION}":
        raise Core0Error("trap normalized companion has the wrong contract or boundary")
    lines = normalized.splitlines()
    expected_roots = [
        f'root=1;source={FOREGROUND_SOURCE};signature={{"args":[]}}',
        f'root=2;source={DISPATCH_SOURCE};signature={{"args":["u64","u64","u64","u64","u64","u64","u64","u64","u64"]}}',
    ]
    if [line for line in lines if line.startswith("root=")] != expected_roots:
        raise Core0Error("trap normalized root closure differs")
    symbol_lines: list[str] = []
    for kind in ("scalar_functions", "action_functions"):
        prefix = "scalar" if kind == "scalar_functions" else "action"
        for raw in _list(manifest.get(kind), kind):
            function = _mapping(raw, kind)
            symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
            if prefix == "scalar":
                expected = f"scalar={function['source']};body={function['body']}"
            else:
                direct = "[" + ",".join(function["direct_effects"]) + "]"
                transitive = "[" + ",".join(function["transitive_effects"]) + "]"
                expected = f"action={function['source']};direct={direct};transitive={transitive};body={function['body']}"
            if lines.count(expected) != 1:
                raise Core0Error(f"trap normalized {prefix} body/effects drifted for {function['source']}")
    if symbols.splitlines() != symbol_lines:
        raise Core0Error("trap symbols companion differs from the exact source/LLVM closure")
    for prefix, values in (
        ("memory-op=", [item["stable_id"] for item in manifest["used_memory_ops"]]),
        ("device-op=", [item["stable_id"] for item in manifest["used_device_ops"]]),
        ("trap-op=", [item["stable_id"] for item in manifest["used_trap_ops"]]),
    ):
        if Counter(line for line in lines if line.startswith(prefix)) != Counter(prefix + value for value in values):
            raise Core0Error(f"trap normalized {prefix[:-1]} closure differs")
    expected_iterations = Counter(
        f"action-iteration=action.u64.bounded-fold;budget={budget};callback={callback}"
        for budget, callback in ITERATIONS
    )
    if Counter(line for line in lines if line.startswith("action-iteration=")) != expected_iterations:
        raise Core0Error("trap normalized iteration closure differs")


def validate_trap_export_configuration(
    value: object, manifest: Mapping[str, object], root: Path
) -> dict[str, object]:
    configuration = _mapping(value, "trap-suite exporter configuration")
    _exact_keys(configuration, {"driver", "generation_command", "environment"}, "trap-suite exporter configuration")
    driver = "examples/foundation/TrapBuild.lean"
    expected_command = ["lake", "env", "lean", str((root / driver).resolve())]
    environment = _mapping(configuration.get("environment"), "trap-suite exporter environment")
    _exact_keys(environment, {RESTORE_ENVIRONMENT}, "trap-suite exporter environment")
    mutation = _mapping(manifest.get("restore_mutation"), "trap restore mutation")
    expected_value = "0" if mutation.get("identity") == "none" else "1"
    if configuration.get("driver") != driver or configuration.get("generation_command") != expected_command or environment.get(RESTORE_ENVIRONMENT) != expected_value:
        raise Core0Error("trap exporter configuration is not bound to the selected restore profile")
    return dict(configuration)


def validate_trap_ir(
    manifest: Mapping[str, object], pre_ir: str, post_ir: str, optimization: str
) -> dict[str, object]:
    # Gate 5's memory proof is deliberately unaware of later machine effects.
    # Erase only the independently audited UART/fence/trap instructions from a
    # proof view; all checked-RAM CFG, guards, operands, and accesses are left
    # byte-for-byte intact for its generic denial-path analysis.
    memory_view_lines: list[str] = []
    for line in pre_ir.splitlines():
        if "call void @core0_io_fence()" in line:
            memory_view_lines.append("")
            continue
        trap_call = re.match(
            r"^(\s*)(%[A-Za-z0-9_.$-]+) = call i64 @core0_trap_[A-Za-z0-9_]+\(\).*$",
            line,
        )
        if trap_call is not None:
            memory_view_lines.append(f"{trap_call.group(1)}{trap_call.group(2)} = add i64 0, 0")
            continue
        scalar_call = re.match(
            r"^(\s*)(%[A-Za-z0-9_.$-]+) = call "
            r"(?:(?:zeroext|signext) )?i(8|32|64) @core0_scalar_[0-9]+\(.*$",
            line,
        )
        if scalar_call is not None:
            bits = scalar_call.group(3)
            memory_view_lines.append(
                f"{scalar_call.group(1)}{scalar_call.group(2)} = add i{bits} 0, 0"
            )
            continue
        if "inttoptr (i64 268435" in line:
            load = re.match(r"^(\s*)(%[A-Za-z0-9_.$-]+) = load volatile i8,", line)
            memory_view_lines.append(
                f"{load.group(1)}{load.group(2)} = add i8 0, 0" if load is not None else ""
            )
            continue
        memory_view_lines.append(line)
    memory = audit_memory.validate_memory_pre_ir(
        manifest, "\n".join(memory_view_lines) + "\n", require_volatile=True
    )
    expected_low_level = (
        "uart.lsr.read8", "uart.thr.write8", "uart.lsr.read8", "uart.fcr.enable-reset",
    )
    device_findings: dict[str, object] = {}
    for label, ir in (("pre", pre_ir), ("post", post_ir)):
        lines = ir.splitlines()
        functions = audit_device._line_functions(lines)
        operations: list[str] = []
        access_indices: set[int] = set()
        if label == "pre":
            for index, line in enumerate(lines):
                marker = audit_device.SITE_MARKER.fullmatch(line)
                if marker is None:
                    continue
                following = audit_device._nonblank_after(lines, index, 3)
                if len(following) != 3:
                    raise Core0Error("trap UART source site is truncated")
                (before_i, before), (access_i, access), (after_i, after) = following
                if before_i != index + 1 or access_i != index + 2 or after_i != index + 3:
                    raise Core0Error("trap UART fence/access bracket is not contiguous")
                if audit_device.FENCE_CALL.fullmatch(before) is None or audit_device.FENCE_CALL.fullmatch(after) is None:
                    raise Core0Error("trap UART source site lacks immediate fences")
                operation = audit_device._access_op(access)
                if operation != marker.group(2) or functions[index] != functions[access_i]:
                    raise Core0Error("trap UART source marker differs from its physical access")
                operations.append(operation)
                access_indices.add(access_i)
            if "lemma.uart-site=" not in ir:
                raise Core0Error("trap pre-optimization IR lacks UART source markers")
        else:
            for index in audit_device._direct_physical_access_indices(lines):
                address = audit_device.DIRECT_ADDRESS.search(lines[index])
                if address is None or not audit_device.UART_BASE <= int(address.group(1)) < audit_device.UART_BASE + audit_device.UART_SPAN:
                    continue
                operation = audit_device._access_op(lines[index], optimized=True)
                if operation is None:
                    raise Core0Error("optimized trap UART access is not volatile i8 align 1")
                if index == 0 or index + 1 >= len(lines) or audit_device.FENCE_CALL.fullmatch(lines[index - 1]) is None or audit_device.FENCE_CALL.fullmatch(lines[index + 1]) is None:
                    raise Core0Error("optimized trap UART access lacks immediate fences")
                operations.append(operation)
                access_indices.add(index)
            if "lemma.uart-site=" in ir:
                raise Core0Error("optimized trap IR retained source-only UART markers")
        if tuple(operations) != expected_low_level:
            raise Core0Error(f"{label} trap UART operation sequence differs")
        audit_device._validate_constant_pointers(lines, functions, access_indices)
        device_findings[label] = {"operations": operations, "accesses": len(operations)}

    parsed = audit_memory.parse_ir_functions(pre_ir)
    parsed_post = audit_memory.parse_ir_functions(post_ir)
    trap_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    symbol_by_stable = {stable: symbol for stable, symbol, _source in TRAP_OPS}
    for raw in manifest["action_functions"]:
        function = _mapping(raw, "trap Action function")
        body = str(function["body"])
        llvm = str(function["llvm"])
        ir_function = parsed.get(llvm)
        post_function = parsed_post.get(llvm)
        if ir_function is None or post_function is None:
            raise Core0Error(f"trap pre/post optimization IR omits @{llvm}")
        for stable, symbol in symbol_by_stable.items():
            source_count = body.count(f"(action.trap {stable} ")
            llvm_count = len(re.findall(rf"\bcall i64 @{re.escape(symbol)}\(\)", ir_function.body))
            post_count = len(re.findall(rf"\bcall i64 @{re.escape(symbol)}\(\)", post_function.body))
            if source_count != llvm_count or source_count != post_count:
                raise Core0Error(f"trap pre/post lowering call count differs for {llvm}/{stable}")
            source_counts[stable] += source_count
            trap_counts[symbol] += llvm_count
    expected_counts = Counter({"trap.ecall": 3, "trap.breakpoint": 1, "trap.unexpected-ecall": 1, "trap.illegal-instruction": 1})
    if source_counts != expected_counts:
        raise Core0Error(f"trap source operation site closure differs: {dict(source_counts)!r}")
    return {
        "memory": memory,
        "device": device_findings,
        "trap_calls": dict(sorted(trap_counts.items())),
        "optimization": optimization,
    }


def _hex_field(layout: Mapping[str, object], section: str, field: str) -> int:
    region = _mapping(layout.get(section), f"trap layout {section}")
    value = region.get(field)
    if not isinstance(value, str):
        raise Core0Error(f"trap layout {section}.{field} is not hexadecimal")
    try:
        return int(value, 0)
    except ValueError as error:
        raise Core0Error(f"trap layout {section}.{field} is malformed") from error


def validate_trap_layout(layout_value: object, symbol_addresses: Mapping[str, int]) -> dict[str, object]:
    layout = _mapping(layout_value, "trap layout")
    expected_regions = {
        "trap_stack": (0x80810000, 0x4000),
        "trap_probe_context": (0x80815000, 0x1000),
        "trap_probe_stack": (0x80818000, 0x1000),
    }
    for name, (start, size) in expected_regions.items():
        region = _mapping(layout.get(name), f"trap layout {name}")
        if _hex_field(layout, name, "start") != start or _hex_field(layout, name, "size") != size or region.get("alignment") != 16 or region.get("ordinary_ram_access") is not False:
            raise Core0Error(f"trap layout region {name} differs")
    if layout.get("trap_stack_pointer") != "0x0000000080813ff0" or layout.get("trap_probe_sp") != "0x0000000080818800":
        raise Core0Error("trap stack/probe pointer differs")
    expected_frame = {
        "bytes": 288, "alignment": 16, "x1_offset": 0, "x2_offset": 8,
        "x31_offset": 240, "mstatus_offset": 248, "mepc_offset": 256,
        "mcause_offset": 264, "mtval_offset": 272, "mie_offset": 280,
    }
    if layout.get("trap_frame") != expected_frame:
        raise Core0Error("trap frame layout differs")
    if layout.get("trap_stack_capacity") != {
        "reserved_bytes": 16384, "canary_bytes": 32, "usable_bytes": 16352,
        "trap_frame_bytes": 288, "outgoing_call_bytes": 16,
        "maximum_compiled_call_chain_bytes": 16048,
    }:
        raise Core0Error("trap stack capacity proof differs")
    if layout.get("trap_probe_capacity") != {
        "reserved_bytes": 4096, "canary_bytes": 32, "writable_bytes_above_sp": 2032,
        "snapshot_bytes": 248, "caller_context_bytes": 128,
        "private_context_reserved_bytes": 4096,
    }:
        raise Core0Error("trap probe capacity proof differs")
    expected_symbols = {
        "__trap_stack_bottom": 0x80810000, "__trap_stack_top": 0x80813FF0,
        "__trap_probe_context": 0x80815000, "__trap_probe_sp": 0x80818800,
        "__trap_probe_bottom": 0x80818000, "__trap_probe_top": 0x80818FF0,
    }
    for name, address in expected_symbols.items():
        if symbol_addresses.get(name) != address:
            raise Core0Error(f"trap ELF symbol {name} differs from layout")
    canaries = _list(layout.get("trap_canaries"), "trap canaries")
    expected_canaries = (
        ("foreground-low", 0x807F0000, 0x4C4D370000000001, 0x4C4D370000000002),
        ("foreground-high", 0x80800000, 0x4C4D370000000011, 0x4C4D370000000012),
        ("trap-low", 0x80810000, 0x4C4D370000000021, 0x4C4D370000000022),
        ("trap-high", 0x80813FF0, 0x4C4D370000000031, 0x4C4D370000000032),
        ("probe-low", 0x80818000, 0x4C4D370000000041, 0x4C4D370000000042),
        ("probe-high", 0x80818FF0, 0x4C4D370000000051, 0x4C4D370000000052),
    )
    observed = []
    for raw in canaries:
        item = _mapping(raw, "trap canary")
        try:
            observed.append((item.get("name"), int(str(item.get("address")), 0), int(str(item.get("word0")), 0), int(str(item.get("word1")), 0)))
        except ValueError as error:
            raise Core0Error("trap canary has malformed hexadecimal fields") from error
        if item.get("bytes") != 16:
            raise Core0Error("trap canary does not reserve exactly sixteen bytes")
    if tuple(observed) != expected_canaries:
        raise Core0Error("trap canary layout/value closure differs")
    return {"regions": expected_regions, "frame_bytes": 288, "canaries": len(canaries)}


REGISTERS = (
    "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1", "a0", "a1",
    "a2", "a3", "a4", "a5", "a6", "a7", "s2", "s3", "s4", "s5", "s6",
    "s7", "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6",
)


def _asm_body(assembly: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}:\n(.*?)^\.size {re.escape(name)},", assembly, re.MULTILINE | re.DOTALL)
    if match is None:
        raise Core0Error(f"startup.S lacks a closed {name} function")
    return match.group(1)


def _asm_instructions(body: str) -> list[str]:
    return [line.strip() for line in body.splitlines() if line.startswith("  ")]


def _expected_trap_vector(mutation: str) -> list[str]:
    if mutation not in {"none", "restore-s3-from-s4"}:
        raise Core0Error(f"unknown trap restore mutation: {mutation!r}")
    prefix = [
        "csrrw sp, mscratch, sp", "beqz sp, core0_trap_double_fault",
        "addi sp, sp, -288", "sd t0, 32(sp)", "csrrw t0, mscratch, zero",
        "sd t0, 8(sp)",
    ]
    saves = [
        f"sd {register}, {(number - 1) * 8}(sp)"
        for number, register in enumerate(REGISTERS, 1)
        if register not in {"sp", "t0"}
    ]
    csrs = [
        "csrr t0, mstatus", "sd t0, 248(sp)", "csrr t0, mepc", "sd t0, 256(sp)",
        "csrr t0, mcause", "sd t0, 264(sp)", "csrr t0, mtval", "sd t0, 272(sp)",
        "csrr t0, mie", "sd t0, 280(sp)",
    ]
    dispatch = [
        "mv gp, zero", "mv tp, zero", "ld a0, 264(sp)", "ld a1, 256(sp)",
        "ld a2, 248(sp)", "ld a3, 272(sp)", "ld a4, 280(sp)",
        "la a5, __trap_ecall_site", "la a6, __trap_ecall_resume",
        "la a7, __trap_breakpoint_site", "la t0, __trap_breakpoint_resume",
        "addi sp, sp, -16", "sd t0, 0(sp)", f"call {DISPATCH_SYMBOL}",
        "addi sp, sp, 16", "bnez a0, core0_trap_fatal_dispatch", "csrw mepc, a1",
        "ld t0, 248(sp)", "csrw mstatus, t0", "ld t0, 280(sp)", "csrw mie, t0",
    ]
    restores: list[str] = []
    for number, register in enumerate(REGISTERS, 1):
        if register in {"sp", "t0"}:
            continue
        offset = (number - 1) * 8
        if register == "s3" and mutation == "restore-s3-from-s4":
            offset = 152
        restores.append(f"ld {register}, {offset}(sp)")
    suffix = [
        "ld t0, 32(sp)", "addi sp, sp, 288", "csrw mscratch, sp",
        "ld sp, -280(sp)", "mret",
    ]
    return prefix + saves + csrs + dispatch + restores + suffix


def validate_trap_vector_instructions(vector: Sequence[str], mutation: str) -> None:
    """Reject every machine-entry source sequence except the selected closed profile."""
    if list(vector) != _expected_trap_vector(mutation):
        raise Core0Error("trap vector differs from the exact full-context/CSR/latch sequence")


def validate_trap_site_symbols(symbol_addresses: Mapping[str, int]) -> None:
    """Bind direct-mode alignment and the two authorized four-byte continuations."""
    for site, resume in (
        ("__trap_ecall_site", "__trap_ecall_resume"),
        ("__trap_breakpoint_site", "__trap_breakpoint_resume"),
    ):
        if site not in symbol_addresses or symbol_addresses.get(resume) != symbol_addresses[site] + 4:
            raise Core0Error(f"trap approved site/resume pair {site} is not exactly four bytes")
    for site in ("__trap_unexpected_ecall_site", "__trap_illegal_instruction_site"):
        if site not in symbol_addresses:
            raise Core0Error(f"trap fatal site {site} is missing")
    vector = symbol_addresses.get("core0_trap_vector")
    if isinstance(vector, bool) or not isinstance(vector, int) or vector % 4 != 0:
        raise Core0Error("trap vector is not four-byte aligned for direct mtvec mode")


def validate_stackless_fatal_body(name: str, status: int, body: Sequence[str]) -> None:
    loop = {
        "core0_trap_fatal_dispatch": ".Ltrap_fatal_halt",
        "core0_trap_double_fault": ".Ltrap_double_halt",
    }.get(name)
    if loop is None or status not in {18, 19}:
        raise Core0Error("unknown trap fatal finisher contract")
    code = status * 65536 + 0x3333
    expected = [
        "li t0, 1048576",
        f"li t1, {code}",
        "fence iorw, iorw",
        "sw t1, 0(t0)",
        "fence iorw, iorw",
        f"j {loop}",
    ]
    if list(body) != expected or any("sp" in instruction for instruction in body):
        raise Core0Error(f"{name} is not the exact stackless fatal finisher")


def validate_compiled_register_reservation(compiled_bodies: Mapping[str, str]) -> None:
    offenders = sorted(
        name for name, body in compiled_bodies.items()
        if re.search(r"\b(?:gp|tp)\b", body)
    )
    if offenders:
        raise Core0Error(f"compiled trap program uses reserved gp/tp registers: {offenders!r}")
    privileged: list[tuple[str, str]] = []
    instruction_pattern = re.compile(
        r"^[ \t]*[0-9a-f]+:[ \t]+([a-z][a-z0-9.]*)[ \t]*(.*?)$",
        re.MULTILINE,
    )
    for name, body in compiled_bodies.items():
        for mnemonic, operands in instruction_pattern.findall(body):
            if (
                mnemonic.startswith(("csr", "sfence", "hfence"))
                or mnemonic in {"ecall", "ebreak", "mret", "sret", "uret", "wfi"}
            ):
                privileged.append((name, f"{mnemonic} {operands}".strip()))
    if privileged:
        raise Core0Error(
            "compiled trap program contains privileged/CSR instructions: "
            + repr(privileged)
        )


def validate_trap_startup_assembly(
    assembly: str, manifest: Mapping[str, object], layout: Mapping[str, object]
) -> dict[str, object]:
    if assembly.count(".option norelax") != 1 or assembly.count(".option norvc") != 1 or ".note.GNU-stack" not in assembly:
        raise Core0Error("trap startup lacks exact no-relax/no-RVC/non-executable-stack policy")
    globals_seen = set(re.findall(r"^\.globl ([A-Za-z0-9_.$]+)$", assembly, re.MULTILINE))
    if globals_seen != TRAP_STARTUP_FUNCTIONS:
        raise Core0Error("trap startup global-function closure differs")
    mutation = _mapping(manifest.get("restore_mutation"), "trap restore mutation").get("identity")
    if not isinstance(mutation, str):
        raise Core0Error("trap restore mutation identity is malformed")
    vector = _asm_instructions(_asm_body(assembly, "core0_trap_vector"))
    validate_trap_vector_instructions(vector, mutation)

    start = _asm_instructions(_asm_body(assembly, "_start"))
    required_start = (
        "csrw mie, zero", "csrci mstatus, 8", "la sp, __stack_top",
        "la t0, core0_trap_vector", "csrw mtvec, t0", "la t0, __trap_stack_top",
        "csrw mscratch, t0", "call core0_main", "wfi",
    )
    if any(start.count(instruction) != 1 for instruction in required_start):
        raise Core0Error("trap startup entry lacks an exact interrupt/vector/latch invariant")
    if start[:2] != ["csrw mie, zero", "csrci mstatus, 8"]:
        raise Core0Error("trap startup does not mask mie/MIE before all boot work")
    ordered_entry = [
        "la t0, core0_trap_vector",
        "csrw mtvec, t0",
        "la t0, __trap_stack_top",
        "csrw mscratch, t0",
        "call core0_main",
    ]
    if [start.index(instruction) for instruction in ordered_entry] != sorted(
        start.index(instruction) for instruction in ordered_entry
    ):
        raise Core0Error("trap startup vector/latch/compiled-entry order differs")
    if start.index("csrw mie, zero") > start.index("call core0_main") or start.index("csrw mscratch, t0") > start.index("call core0_main"):
        raise Core0Error("trap startup enables compiled execution before vector/latch setup")

    for probe, instruction in (("ecall", "ecall"), ("breakpoint", "ebreak")):
        body = _asm_body(assembly, f"core0_trap_{probe}")
        instructions = _asm_instructions(body)
        caller_registers = (
            ("ra", 0), ("sp", 8), ("gp", 16), ("tp", 24), ("s0", 32),
            ("s1", 40), ("s2", 48), ("s3", 56), ("s4", 64), ("s5", 72),
            ("s6", 80), ("s7", 88), ("s8", 96), ("s9", 104),
            ("s10", 112), ("s11", 120),
        )
        caller_save = ["la t0, __trap_probe_context"] + [
            f"sd {register}, {offset}(t0)" for register, offset in caller_registers
        ]
        sentinel_words = [
            (
                int(str(layout.get("trap_probe_sp")), 0)
                if register == "sp"
                else 0x3753000000000000 | (number << 16) | number
            )
            for number, register in enumerate(REGISTERS, 1)
        ]
        sentinel_loads = [
            f"li {register}, {word}"
            for register, word in zip(REGISTERS, sentinel_words)
        ]
        snapshots = [
            f"sd {register}, {(number - 1) * 8}(sp)"
            for number, register in enumerate(REGISTERS, 1)
        ]
        register_checks: list[str] = []
        for number, register in enumerate(REGISTERS, 1):
            offset = (number - 1) * 8
            expected_word = sentinel_words[number - 1]
            register_checks.extend((
                f"ld t0, {offset}(sp)",
                f"li t1, {expected_word}",
                f"beq t0, t1, .Ltrap_{probe}_x{number}_ok",
                f"li t2, {1 << (number - 1)}",
                "or a0, a0, t2",
            ))
        canary_checks: list[str] = []
        for index, canary in enumerate(_list(layout.get("trap_canaries"), "trap canaries")):
            item = _mapping(canary, "trap canary")
            address = int(str(item["address"]), 0)
            for word in range(2):
                value = int(str(item[f"word{word}"]), 0)
                canary_checks.extend((
                    f"li t0, {address + word * 8}",
                    "ld t1, 0(t0)",
                    f"li t2, {value}",
                    f"beq t1, t2, .Ltrap_{probe}_canary{index}_{word}_ok",
                    f"li t2, {1 << (31 + index)}",
                    "or a0, a0, t2",
                ))
        caller_restore = ["la t0, __trap_probe_context"] + [
            f"ld {register}, {offset}(t0)"
            for register, offset in caller_registers
            if register != "sp"
        ] + ["ld sp, 8(t0)", "ret"]
        expected_probe = (
            caller_save
            + sentinel_loads
            + [instruction]
            + snapshots
            + ["li a0, 0"]
            + register_checks
            + canary_checks
            + caller_restore
        )
        if instructions != expected_probe:
            raise Core0Error(
                f"trap {probe} probe differs from the exact load/trigger/snapshot/check/restore phases"
            )

    for name, status in (("core0_trap_fatal_dispatch", 18), ("core0_trap_double_fault", 19)):
        body = _asm_instructions(_asm_body(assembly, name))
        validate_stackless_fatal_body(name, status, body)
    if _asm_instructions(_asm_body(assembly, "core0_trap_unexpected_ecall")) != ["ecall", "j core0_trap_fatal_dispatch"]:
        raise Core0Error("unexpected-ecall fixture is not an exact fatal architectural site")
    if _asm_instructions(_asm_body(assembly, "core0_trap_illegal_instruction")) != [".word 0x0000000b", "j core0_trap_fatal_dispatch"]:
        raise Core0Error("illegal-instruction fixture is not an exact fatal architectural site")
    return {"restore_mutation": mutation, "frame_bytes": 288, "integer_registers": 31, "csr_snapshots": 5, "probe_registers": 31, "canaries": 6}


def validate_trap_machine_disassembly(
    disassembly: str,
    symbol_addresses: Mapping[str, int],
    program_functions: set[str],
    startup_assembly: str,
) -> dict[str, object]:
    def instructions_between(start: int, stop: int) -> list[tuple[int, str, str]]:
        result: list[tuple[int, str, str]] = []
        pattern = re.compile(
            r"^[ \t]*([0-9a-f]+):[ \t]+([a-z][a-z0-9.]*)[ \t]*([^\n]*?)[ \t]*$",
            re.MULTILINE,
        )
        for address_text, mnemonic, operands in pattern.findall(disassembly):
            address = int(address_text, 16)
            if start <= address < stop:
                result.append((address, mnemonic, operands))
        return result

    machine_functions = sorted(
        (
            int(symbol_addresses[name]),
            name,
        )
        for name in TRAP_STARTUP_FUNCTIONS
        if name in symbol_addresses
    )
    if {name for _address, name in machine_functions} != TRAP_STARTUP_FUNCTIONS:
        raise Core0Error("trap machine-code function symbols are incomplete")
    function_instructions: dict[str, list[tuple[int, str, str]]] = {}
    for index, (start, name) in enumerate(machine_functions):
        stop = machine_functions[index + 1][0] if index + 1 < len(machine_functions) else min(
            (address for symbol, address in symbol_addresses.items() if address > start and symbol in program_functions),
            default=start + 0x100000,
        )
        function_instructions[name] = instructions_between(start, stop)

    def parse_offset(text: str) -> int:
        sign = -1 if text.startswith("-") else 1
        raw = text[1:] if sign < 0 else text
        return sign * int(raw, 0)

    memory_pattern = re.compile(
        r"^(sd|ld)\s+([a-z][a-z0-9]*),\s*(-?(?:0x[0-9a-f]+|[0-9]+))\(([a-z][a-z0-9]*)\)$"
    )

    def assembly_memory(name: str) -> list[tuple[str, str, int, str]]:
        result: list[tuple[str, str, int, str]] = []
        for instruction in _asm_instructions(_asm_body(startup_assembly, name)):
            match = memory_pattern.fullmatch(instruction)
            if match is not None:
                result.append((match.group(1), match.group(2), parse_offset(match.group(3)), match.group(4)))
        return result

    def machine_memory_rows(name: str) -> list[tuple[int, str, str, int, str]]:
        result: list[tuple[int, str, str, int, str]] = []
        for address, mnemonic, operands in function_instructions[name]:
            match = memory_pattern.fullmatch(f"{mnemonic} {operands}")
            if match is not None:
                result.append(
                    (
                        address,
                        match.group(1),
                        match.group(2),
                        parse_offset(match.group(3)),
                        match.group(4),
                    )
                )
        return result

    def machine_memory(name: str) -> list[tuple[str, str, int, str]]:
        return [row[1:] for row in machine_memory_rows(name)]

    validate_trap_site_symbols(symbol_addresses)
    vector_match = re.search(r"<core0_trap_vector>:\n(.*?)\n\n[0-9a-f]+ <core0_trap_fatal_dispatch>:", disassembly, re.DOTALL)
    if vector_match is None:
        raise Core0Error("trap disassembly lacks a bounded vector body")
    vector = vector_match.group(1)
    for pattern in (
        r"\bcsrrw\s+sp, mscratch, sp", r"\baddi\s+sp, sp, -0x120",
        r"\bcsrrw\s+t0, mscratch, zero", rf"<{DISPATCH_SYMBOL}>",
        r"\bcsrw\s+mepc, a1", r"\bcsrw\s+mstatus, t0", r"\bcsrw\s+mie, t0",
        r"\bcsrw\s+mscratch, sp", r"\bmret\b", r"<core0_trap_double_fault>",
        r"<core0_trap_fatal_dispatch>",
    ):
        if re.search(pattern, vector) is None:
            raise Core0Error(f"trap vector machine code lacks architectural pattern {pattern!r}")
    for register in REGISTERS:
        if register == "sp":
            continue
        if re.search(rf"\bsd\s+{register},", vector) is None or re.search(rf"\bld\s+{register},", vector) is None:
            raise Core0Error(f"trap vector machine code does not save/restore {register}")
    for name in ("core0_trap_vector", "core0_trap_ecall", "core0_trap_breakpoint"):
        expected_memory = assembly_memory(name)
        observed_memory = machine_memory(name)
        if observed_memory != expected_memory:
            raise Core0Error(
                f"{name} machine memory-access slots/order differ from startup.S"
            )
    for name, site, resume in (
        ("core0_trap_ecall", "__trap_ecall_site", "__trap_ecall_resume"),
        ("core0_trap_breakpoint", "__trap_breakpoint_site", "__trap_breakpoint_resume"),
    ):
        rows = machine_memory_rows(name)
        if (
            len(rows) != 106
            or any(row[0] >= symbol_addresses[site] for row in rows[:16])
            or rows[16][0] != symbol_addresses[resume]
            or any(row[0] < symbol_addresses[resume] for row in rows[16:])
        ):
            raise Core0Error(
                f"{name} machine save/trigger/immediate-snapshot phase order differs"
            )

    assembly_csrs = [
        re.sub(r"\s+", "", instruction)
        for instruction in _asm_instructions(_asm_body(startup_assembly, "core0_trap_vector"))
        if instruction.startswith(("csrr ", "csrw ", "csrrw "))
    ]
    machine_csrs = [
        re.sub(r"\s+", "", f"{mnemonic} {operands}")
        for _address, mnemonic, operands in function_instructions["core0_trap_vector"]
        if mnemonic in {"csrr", "csrw", "csrrw"}
    ]
    if machine_csrs != assembly_csrs:
        raise Core0Error("trap vector machine CSR sequence differs from startup.S")

    def privileged_rows(name: str) -> list[tuple[int, str, str]]:
        return [
            (address, mnemonic, re.sub(r"\s+", "", operands))
            for address, mnemonic, operands in function_instructions[name]
            if (
                mnemonic.startswith(("csr", "sfence", "hfence"))
                or mnemonic in {"ecall", "ebreak", "mret", "sret", "uret", "wfi"}
            )
        ]

    start_privileged = [
        (mnemonic, operands)
        for _address, mnemonic, operands in privileged_rows("_start")
    ]
    if start_privileged != [
        ("csrw", "mie,zero"),
        ("csrci", "mstatus,0x8"),
        ("csrw", "mtvec,t0"),
        ("csrw", "mscratch,t0"),
        ("wfi", ""),
    ]:
        raise Core0Error("trap startup machine privileged-instruction closure differs")
    vector_privileged = [
        (mnemonic, operands)
        for _address, mnemonic, operands in privileged_rows("core0_trap_vector")
    ]
    expected_vector_privileged = [
        (instruction.split(None, 1)[0], re.sub(r"\s+", "", instruction.split(None, 1)[1]))
        for instruction in _asm_instructions(
            _asm_body(startup_assembly, "core0_trap_vector")
        )
        if instruction.startswith("csr")
    ] + [("mret", "")]
    if vector_privileged != expected_vector_privileged:
        raise Core0Error("trap vector machine privileged-instruction closure differs")
    trigger_contract = {
        "core0_trap_ecall": ("__trap_ecall_site", "ecall"),
        "core0_trap_breakpoint": ("__trap_breakpoint_site", "ebreak"),
        "core0_trap_unexpected_ecall": ("__trap_unexpected_ecall_site", "ecall"),
    }
    for name, (site, mnemonic) in trigger_contract.items():
        if privileged_rows(name) != [(symbol_addresses[site], mnemonic, "")]:
            raise Core0Error(f"{name} machine trap-instruction closure differs")
    illegal_address = symbol_addresses["__trap_illegal_instruction_site"]
    if re.search(
        rf"^[ \t]*{illegal_address:x}:[ \t]+<unknown>[ \t]*$",
        disassembly,
        re.MULTILINE,
    ) is None:
        raise Core0Error("illegal-instruction fixture is not emitted at its closed site")
    for name in (
        "core0_io_fence",
        "core0_trap_fatal_dispatch",
        "core0_trap_double_fault",
        "core0_trap_illegal_instruction",
    ):
        if privileged_rows(name):
            raise Core0Error(f"{name} contains an unauthorized privileged instruction")
    expected_stack_adjustments = [-288, -16, 16, 288]
    observed_stack_adjustments: list[int] = []
    for _address, mnemonic, operands in function_instructions["core0_trap_vector"]:
        match = re.fullmatch(
            r"sp,\s*sp,\s*(-?(?:0x[0-9a-f]+|[0-9]+))", operands
        )
        if mnemonic == "addi" and match is not None:
            observed_stack_adjustments.append(parse_offset(match.group(1)))
    if observed_stack_adjustments != expected_stack_adjustments:
        raise Core0Error("trap vector machine stack-adjustment sequence differs")
    if not function_instructions["core0_trap_vector"] or function_instructions["core0_trap_vector"][-1][1] != "mret":
        raise Core0Error("trap vector machine tail does not terminate in mret")

    start_machine = function_instructions["_start"]
    for csr, expected_target in (
        ("mtvec", symbol_addresses["core0_trap_vector"]),
        ("mscratch", symbol_addresses["__trap_stack_top"]),
    ):
        csr_index = next(
            (
                index for index, (_address, mnemonic, operands) in enumerate(start_machine)
                if mnemonic == "csrw" and operands == f"{csr}, t0"
            ),
            None,
        )
        if csr_index is None or csr_index < 2:
            raise Core0Error(f"trap startup machine code lacks direct {csr} setup")
        auipc_address, auipc_mnemonic, auipc_operands = start_machine[csr_index - 2]
        _addi_address, addi_mnemonic, addi_operands = start_machine[csr_index - 1]
        auipc_match = re.fullmatch(r"t0,\s*(-?(?:0x[0-9a-f]+|[0-9]+))", auipc_operands)
        addi_match = re.fullmatch(r"t0,\s*t0,\s*(-?(?:0x[0-9a-f]+|[0-9]+))", addi_operands)
        if auipc_mnemonic != "auipc" or addi_mnemonic != "addi" or auipc_match is None or addi_match is None:
            raise Core0Error(f"trap startup {csr} target is not a resolved PC-relative address")
        loaded_target = (
            auipc_address
            + (parse_offset(auipc_match.group(1)) << 12)
            + parse_offset(addi_match.group(1))
        ) & 0xFFFFFFFFFFFFFFFF
        if loaded_target != expected_target:
            raise Core0Error(
                f"trap startup machine {csr} target differs: 0x{loaded_target:x} != 0x{expected_target:x}"
            )

    for name, upper in (("core0_trap_fatal_dispatch", "0x123"), ("core0_trap_double_fault", "0x133")):
        body = function_instructions[name]
        if [mnemonic for _address, mnemonic, _operands in body] != [
            "lui", "lui", "addiw", "fence", "sw", "fence", "j",
        ]:
            raise Core0Error(f"{name} machine body is not the exact stackless finisher")
        if body[0][2] != "t0, 0x100" or body[1][2] != f"t1, {upper}" or body[2][2] != "t1, t1, 0x333" or body[4][2] != "t1, 0x0(t0)":
            raise Core0Error(f"{name} machine finisher address/status code differs")
        jump_address = body[-1][0]
        jump_match = re.match(r"0x([0-9a-f]+)\b", body[-1][2])
        if jump_match is None or int(jump_match.group(1), 16) != jump_address:
            raise Core0Error(f"{name} machine finisher lacks its terminal self-loop")
        if any(re.search(r"\bsp\b", operands) for _address, _mnemonic, operands in body):
            raise Core0Error(f"{name} machine finisher unexpectedly uses the stack")
    function_headers = list(re.finditer(r"^[0-9a-f]+ <([A-Za-z0-9_.$]+)>:$", disassembly, re.MULTILINE))
    compiled_bodies: dict[str, str] = {}
    for index, match in enumerate(function_headers):
        name = match.group(1)
        stop = function_headers[index + 1].start() if index + 1 < len(function_headers) else len(disassembly)
        if name in program_functions:
            compiled_bodies[name] = disassembly[match.end():stop]
    if set(compiled_bodies) != program_functions:
        raise Core0Error("trap disassembly omits a compiled-program function")
    validate_compiled_register_reservation(compiled_bodies)
    if re.search(r"\b(?:f[0-9]+|v[0-9]+)\b", disassembly):
        raise Core0Error("trap image uses floating-point or vector registers")
    return {
        "approved_resume_pairs": 2,
        "direct_mtvec_target": f"0x{symbol_addresses['core0_trap_vector']:x}",
        "compiled_gp_tp_free": True,
        "compiled_privileged_instructions": 0,
        "compiled_functions": len(compiled_bodies),
        "machine_slot_sequences": {
            name: len(machine_memory(name))
            for name in ("core0_trap_vector", "core0_trap_ecall", "core0_trap_breakpoint")
        },
        "machine_csr_operations": len(machine_csrs),
        "fatal_stackless_self_loops": 2,
    }
