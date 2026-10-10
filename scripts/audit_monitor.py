#!/usr/bin/env python3
"""Independent fail-closed checks for the Gate 9 interactive monitor image."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Mapping

import audit_device
import audit_memory
import audit_timer
import audit_trap
from core0_common import Core0Error


CONTRACT_VERSION = "core0-v0.7"
ARTIFACT_CATEGORY = "test-monitor-image"
TEST_ABI = "lemma-monitor-v1"
SOURCE_IDENTITY = "Lemma Gate 9 interactive monitor"
FOREGROUND_SOURCE = "Lemma.Examples.Foundation.Monitor.foreground"
DISPATCH_SOURCE = "Lemma.Examples.Foundation.Timer.dispatch"
INTERRUPT_SOURCE = audit_timer.INTERRUPT_SOURCE

TIMER_EXTERNALS = set(audit_timer.TIMER_EXTERNALS)
TRAP_EXTERNALS = {"core0_trap_ecall", "core0_trap_breakpoint"}
MONITOR_EXTERNALS = TIMER_EXTERNALS | TRAP_EXTERNALS
MONITOR_STARTUP_FUNCTIONS = set(audit_timer.TIMER_STARTUP_FUNCTIONS)


def _command(identifier: int, name: str, length: int, semantics: str) -> dict[str, object]:
    return {"id": identifier, "name": name, "payload_bytes": length,
            "semantics": semantics}


def _status(
    code: int, name: str, always_terminal: bool, wire_status: bool
) -> dict[str, object]:
    return {"code": code, "name": name, "always_terminal": always_terminal,
            "wire_status": wire_status}


COMMANDS = [
    _command(1, "HELLO", 0, "capability and version tuple"),
    _command(2, "STATUS", 0, "handled/error/recovery/checksum counters"),
    _command(3, "EVAL", 32, "bounded scalar evaluation and interrupt-aware mixing"),
    _command(4, "FILL", 24, "checked fill of the logical user buffer"),
    _command(5, "CHECKSUM", 16, "checked sum of actual user-buffer bytes"),
    _command(6, "TRAP_TEST", 8, "authorized ECALL or EBREAK recovery"),
    _command(7, "TIMER_START", 8, "validated real machine-timer start and probe"),
    _command(8, "TIMER_STOP", 0, "idempotent timer shutdown and stability check"),
    _command(9, "TICKS", 16, "critical-section timer statistics or ring access"),
    _command(10, "EXIT", 0, "timer shutdown, guard validation, response, and clean finish"),
]

STATUSES = [
    _status(0, "ok", False, True),
    _status(1, "unknown-region", False, True),
    _status(2, "reserved-region", False, True),
    _status(3, "device-region", False, True),
    _status(4, "read-denied", False, True),
    _status(5, "write-denied", False, True),
    _status(6, "width-denied", False, True),
    _status(7, "bounds-or-index", False, True),
    _status(8, "alignment", False, True),
    _status(9, "session-budget", True, True),
    _status(10, "internal-only", True, False),
    _status(11, "uart-tx-timeout", True, True),
    _status(12, "empty-rx-timeout", True, True),
    _status(13, "uart-line-error", True, True),
    _status(14, "malformed-header-or-argument", False, True),
    _status(15, "truncated-input", True, True),
    _status(16, "length-count-or-active-state", False, True),
    _status(17, "unsupported-command-selector-or-mode", False, True),
    _status(18, "unexpected-trap", True, False),
    _status(19, "double-fault", True, False),
    _status(20, "context-guard-or-state-integrity", False, True),
    _status(21, "required-hardware-event-absent-or-inactive", False, True),
    _status(22, "invalid-timer-period-or-deadline", False, True),
]

HELLO_CONTRACT = {
    "tag_u64": "0x31304e4f4d4d454c",
    "tag_bytes": "LEMMON01",
    "core0_version": 7,
    "machine_profile": 1,
    "command_bits": "0x3ff",
}

MEMORY_CONTRACT = {
    "protocol_scratch": "scratch[0..47]",
    "user_buffer": "scratch[256..4095]",
    "user_buffer_logical_bytes": 3840,
    "boot_initialization": "all 3840 user bytes are zeroed",
    "timer_state": "events[0..127]",
    "monitor_stats": [
        "events:u64@128=handledRequests",
        "events:u64@136=recoverableErrors",
        "events:u64@144=syncRecoveries",
        "events:u64@152=lastWorkChecksum",
    ],
    "private_shutdown_witness": "events:u64@160=stoppedWorkChecksum",
    "timer_guard_offset": 240,
}

MONITOR_CONTRACT: dict[str, object] = {
    "schema_version": 1,
    "profile": "bounded-uart-monitor-v1",
    "request": {
        "magic": "LMQ9", "version": 1, "header_bytes": 16,
        "maximum_payload_bytes": 32, "flags": 0, "request_id_bits": 64,
        "byte_order": "little-endian",
        "fields": ["magic:u8[4]@0", "version:u8@4", "command:u8@5",
                   "length:u8@6", "flags:u8@7", "request-id:u64@8",
                   "payload:u8[length]@16"],
    },
    "response": {
        "magic": "LMS9", "version": 1, "bytes": 48, "payload_bytes": 32,
        "flags": 0, "request_id_bits": 64, "byte_order": "little-endian",
        "fields": ["magic:u8[4]@0", "version:u8@4", "status:u8@5",
                   "length:u8@6", "flags:u8@7", "request-id:u64@8",
                   "values:u64[4]@16"],
    },
    "ready": "LEMMA_MONITOR/1\nREADY\n",
    "maximum_handled_requests": 256,
    "commands": COMMANDS,
    "statuses": STATUSES,
    "framing": {
        "bounded_request_order":
            "receive complete payload, increment handledRequests, then validate and dispatch",
        "oversize": "length>32 terminates status 16 without reply or counter increment",
        "invalid_header": "status 14 with zero values; continue",
        "wrong_known_length": "status 16 with zero values; continue",
        "unknown_command": "status 17 with zero values; continue",
        "truncated": "missing first byte status 12; partial header or payload status 15",
    },
    "memory": MEMORY_CONTRACT,
    "hello": HELLO_CONTRACT,
    "eval": {
        "selectors": ["0=wrapping-add", "1=xor", "2=fixed-mix",
                      "3=mix-until-real-irq-delta"],
        "maximum_fixed_quanta": 4096, "maximum_irq_delta": 256,
        "mix_steps_per_quantum": 128, "maximum_irq_quanta": 1000000,
    },
    "trap_test": {
        "modes": ["0=authorized-ecall", "1=authorized-ebreak"],
        "required_sync_recovery_delta": 1,
        "timer_interrupts_are_not_sync_recoveries": True,
    },
    "timer": {
        "minimum_period": 10000, "maximum_period": 1000000,
        "timer_start_requires_inactive": True,
        "timer_stop_is_idempotent": True,
        "ticks_modes": ["0=counters", "1=timing", "2=state",
                        "3=retained-record-peek", "4=retained-record-pop"],
        "foreground_may_call_interrupt_policy": False,
    },
    "exit": {
        "success_status": 0, "context_failure_status": 20,
        "successful_exit_is_the_only_ordinary_finish": True,
    },
    "source_policy_probes": {
        "marker": "MONITOR_POLICY_PROBES", "total": 50, "frontend_lowering": 1,
    },
}

MONITOR_ABI: dict[str, object] = {
    "schema_version": 1,
    "contract_version": CONTRACT_VERSION,
    "name": TEST_ABI,
    "byte_order": "little-endian",
    "ready": "LEMMA_MONITOR/1\nREADY\n",
    "request_magic": "LMQ9",
    "request_version": 1,
    "request_header_bytes": 16,
    "maximum_request_payload_bytes": 32,
    "request_flags": 0,
    "request_id_bits": 64,
    "response_magic": "LMS9",
    "response_version": 1,
    "response_bytes": 48,
    "response_payload_bytes": 32,
    "response_flags": 0,
    "response_id_bits": 64,
    "response_values": 4,
    "maximum_handled_requests": 256,
    "commands": COMMANDS,
    "statuses": STATUSES,
    "hello": HELLO_CONTRACT,
    "memory": MEMORY_CONTRACT,
    "monitor_contract": MONITOR_CONTRACT,
}

MACHINE_PRIMITIVES = [
    *audit_timer.MACHINE_PRIMITIVES[:-1],
    {"identity": "status-monitor-harness",
     "effect": "action-abi/status-coded-vm-termination",
     "implementation": "Lemma.Machine.DeviceHarness.main"},
]

# Filled only from genuine O0/O2 artifacts after source freeze.  These hashes
# make the complete source/body/dependency and LLVM closure explicit instead of
# accepting exporter-authored catalogs by shape alone.
MONITOR_MANIFEST_CANONICAL_SHA256 = (
    "d403581ee82835c0b06ecdeddd065b54f1e27780de4f64881317f731a443726e"
)
MONITOR_NORMALIZED_SHA256 = (
    "6900269b277fad3db2e521c59a7dc86f59c1eec69e4c13c179ac6bd3b29ef772"
)
MONITOR_IR_SHA256 = {
    "program.ll": "7dbfb15dbc71ccd9645ccd18e31c8ed38e97c690913179677a4fbbc3b525dac4",
    "O0": "eb9b158f22196bfce8d9bab11dae46c2e278f046141536e3a8c966647a70cdbe",
    "O2": "0d6b6a0c2bd6bf1d4a95b6e55cc067df325d57f99c80e94e227b80095ab6c1b2",
}
MONITOR_START_MACHINE_BODY_SHA256 = {
    "O0": "a1e489f383be3da3d9de86a132d78841ca85b95f4ffe7e75dccadb49460cddfe",
    "O2": "d94a54353af289708f428c376dc2f5d4478d5759dce204376429f87acb7c9927",
}
MONITOR_O2_JUMP_TABLE_RELOCATIONS = 40
MONITOR_MACHINE_ACCESS_SEQUENCE = (
    ("uart.lsr.read8", "core0_action_6", "lbu", 0x10000005),
    ("uart.thr.write8", "core0_action_6", "sb", 0x10000000),
    ("uart.lsr.read8", "core0_action_11", "lbu", 0x10000005),
    ("uart.lsr.read8", "core0_action_15", "lbu", 0x10000005),
    ("uart.rbr.read8", "core0_action_15", "lbu", 0x10000000),
    ("uart.fcr.enable-reset", "core0_action_80", "sb", 0x10000002),
)
MONITOR_MACHINE_DENIED_METADATA = Counter({
    "core0_action_0": 1,
    "core0_action_3": 1,
    "core0_action_18": 1,
    "core0_action_21": 1,
    "core0_action_23": 1,
    "core0_action_25": 4,
    "core0_action_29": 1,
    "core0_action_48": 1,
    "core0_action_76": 6,
    "core0_action_77": 1,
    "core0_action_84": 1,
})
MONITOR_MACHINE_CALLS_SOURCE = {
    "irq.restore": 8,
    "irq.save-disable": 10,
    "timer.probe": 1,
    "timer.read-pending": 2,
    "timer.read-time": 2,
    "timer.set-compare": 6,
    "timer.set-interrupt": 5,
    "trap.breakpoint": 1,
    "trap.ecall": 1,
}
MONITOR_MACHINE_CALLS_PRE = {
    "core0_irq_restore": 8,
    "core0_irq_save_disable": 10,
    "core0_timer_probe": 1,
    "core0_timer_read_pending": 2,
    "core0_timer_read_time": 2,
    "core0_timer_set_compare": 6,
    "core0_timer_set_interrupt": 5,
    "core0_trap_breakpoint": 1,
    "core0_trap_ecall": 1,
}
MONITOR_MACHINE_CALLS_POST = {
    "O0": dict(MONITOR_MACHINE_CALLS_PRE),
    "O2": {**MONITOR_MACHINE_CALLS_PRE, "core0_timer_set_compare": 5},
}
MONITOR_UART_IR_OPERATIONS = (
    "uart.lsr.read8",
    "uart.thr.write8",
    "uart.lsr.read8",
    "uart.lsr.read8",
    "uart.rbr.read8",
    "uart.fcr.enable-reset",
)
MONITOR_MACHINE_SLOT_COUNTS = {
    "_start": 16,
    "core0_io_fence": 0,
    "core0_irq_restore": 0,
    "core0_irq_save_disable": 0,
    "core0_timer_probe": 106,
    "core0_timer_read_pending": 0,
    "core0_timer_read_time": 1,
    "core0_timer_set_compare": 1,
    "core0_timer_set_interrupt": 0,
    "core0_trap_breakpoint": 106,
    "core0_trap_double_fault": 0,
    "core0_trap_ecall": 106,
    "core0_trap_fatal_dispatch": 0,
    "core0_trap_illegal_instruction": 0,
    "core0_trap_unexpected_ecall": 0,
    "core0_trap_vector": 75,
}


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Core0Error(f"{context} is not an object")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Core0Error(f"{context} is not an array")
    return value


def _canonical_sha256(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def _require_pinned(value: str, context: str) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise Core0Error(f"{context} has not been pinned from the genuine monitor artifact")


def _function_closure(manifest: Mapping[str, object]) -> dict[str, object]:
    scalars = _list(manifest.get("scalar_functions"), "monitor scalar functions")
    actions = _list(manifest.get("action_functions"), "monitor Action functions")
    scalar_sources: set[str] = set()
    scalar_by_source: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(scalars):
        function = _mapping(raw, f"monitor scalar function {index}")
        audit_timer._exact_keys(
            function, {"source", "llvm", "signature", "dependencies", "body", "noinline"},
            f"monitor scalar function {index}",
        )
        source, body = function.get("source"), function.get("body")
        if (not isinstance(source, str) or not source or source in scalar_sources
                or function.get("llvm") != f"core0_scalar_{index}"
                or function.get("noinline") is not True or not isinstance(body, str)):
            raise Core0Error("monitor scalar source/LLVM/preservation closure differs")
        signature = _mapping(function.get("signature"), f"monitor scalar signature {source}")
        args, result = signature.get("args"), signature.get("result")
        if (not isinstance(args, list)
                or any(arg not in {"bool", "u8", "u32", "u64"} for arg in args)
                or result not in {"bool", "u8", "u32", "u64"}):
            raise Core0Error(f"monitor scalar signature is outside Core0 for {source}")
        scalar_sources.add(source)
        scalar_by_source[source] = function
    for source, function in scalar_by_source.items():
        body = str(function["body"])
        dependencies = _list(function.get("dependencies"), f"{source} dependencies")
        if (dependencies != audit_timer._body_calls(body, "call")
                or any(dependency not in scalar_sources for dependency in dependencies)):
            raise Core0Error(f"monitor scalar dependency metadata is stale for {source}")

    action_sources: set[str] = set()
    action_by_source: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(actions):
        function = _mapping(raw, f"monitor Action function {index}")
        audit_timer._exact_keys(
            function,
            {"source", "llvm", "signature", "scalar_dependencies",
             "action_dependencies", "direct_effects", "transitive_effects", "body", "noinline"},
            f"monitor Action function {index}",
        )
        source, body = function.get("source"), function.get("body")
        if (not isinstance(source, str) or not source or source in action_sources
                or function.get("llvm") != f"core0_action_{index}"
                or function.get("noinline") is not True
                or not isinstance(body, str) or not body.startswith("(action.")):
            raise Core0Error("monitor Action source/LLVM/preservation closure differs")
        signature = _mapping(function.get("signature"), f"monitor Action signature {source}")
        args = signature.get("args")
        if not isinstance(args, list) or any(
            arg not in {"bool", "u8", "u32", "u64"} for arg in args
        ):
            raise Core0Error(f"monitor Action signature is outside Core0 for {source}")
        action_sources.add(source)
        action_by_source[source] = function
    graph: dict[str, set[str]] = {}
    for source, function in action_by_source.items():
        body = str(function["body"])
        action_dependencies = _list(
            function.get("action_dependencies"), f"{source} Action dependencies"
        )
        body_actions = set(audit_timer._body_calls(body, "action.call")) | set(
            re.findall(r"\bcallback=([A-Za-z0-9_.]+)", body)
        )
        if (len(action_dependencies) != len(set(action_dependencies))
                or set(action_dependencies) != body_actions
                or any(dependency not in action_sources for dependency in action_dependencies)):
            raise Core0Error(f"monitor Action dependency metadata is stale for {source}")
        graph[source] = set(str(item) for item in action_dependencies)
        scalar_dependencies = _list(
            function.get("scalar_dependencies"), f"{source} scalar dependencies"
        )
        if (len(scalar_dependencies) != len(set(scalar_dependencies))
                or set(scalar_dependencies) != set(audit_timer._body_calls(body, "call"))
                or any(dependency not in scalar_sources for dependency in scalar_dependencies)):
            raise Core0Error(f"monitor Action scalar dependency metadata is stale for {source}")
        for field in ("direct_effects", "transitive_effects"):
            effects = _list(function.get(field), f"{source} {field}")
            if len(effects) != len(set(effects)) or any(
                effect not in audit_timer.EFFECT_ORDER for effect in effects
            ):
                raise Core0Error(f"monitor Action {field} is outside the closed effect set")
        if function.get("direct_effects") != audit_timer._body_direct_effects(body):
            raise Core0Error(f"monitor Action direct effects are stale for {source}")
        computed = set(_list(function.get("direct_effects"), f"{source} direct effects"))
        for dependency in action_dependencies:
            computed.update(_list(
                action_by_source[str(dependency)].get("transitive_effects"),
                f"{dependency} transitive effects",
            ))
        expected_transitive = [
            effect for effect in audit_timer.EFFECT_ORDER if effect in computed
        ]
        if function.get("transitive_effects") != expected_transitive:
            raise Core0Error(f"monitor Action transitive effects are stale for {source}")

    def reachable(source: str) -> set[str]:
        if source not in graph:
            raise Core0Error(f"monitor role graph omits {source}")
        seen: set[str] = set()
        pending = [source]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            if current not in graph:
                raise Core0Error(f"monitor role graph references unknown Action {current}")
            seen.add(current)
            pending.extend(sorted(graph[current] - seen))
        return seen

    callers = {source for source, dependencies in graph.items()
               if INTERRUPT_SOURCE in dependencies}
    if callers != {DISPATCH_SOURCE}:
        raise Core0Error("monitor timer interrupt must have the dispatcher as its sole caller")
    interrupt_closure = reachable(INTERRUPT_SOURCE)
    if interrupt_closure != audit_timer.INTERRUPT_ACTION_CLOSURE:
        raise Core0Error("monitor short interrupt closure differs from Gate 8")
    foreground_closure = reachable(FOREGROUND_SOURCE)
    if foreground_closure & {DISPATCH_SOURCE, INTERRUPT_SOURCE}:
        raise Core0Error("monitor foreground can manually reach interrupt/dispatcher policy")
    dispatcher_closure = reachable(DISPATCH_SOURCE)
    if INTERRUPT_SOURCE not in dispatcher_closure:
        raise Core0Error("monitor dispatcher does not reach the interrupt policy")
    return {
        "scalar_functions": len(scalars),
        "action_functions": len(actions),
        "foreground_symbol": str(action_by_source.get(FOREGROUND_SOURCE, {}).get("llvm", "")),
        "dispatcher_symbol": str(action_by_source.get(DISPATCH_SOURCE, {}).get("llvm", "")),
        "interrupt_direct_caller": DISPATCH_SOURCE,
        "interrupt_action_closure": sorted(interrupt_closure),
        "foreground_action_closure": sorted(foreground_closure),
        "foreground_excludes_interrupt_policy": True,
    }


def validate_monitor_manifest(value: object) -> dict[str, object]:
    manifest = _mapping(value, "monitor manifest")
    audit_timer._exact_keys(
        manifest,
        set(audit_device.TOP_LEVEL_KEYS)
        | {"trap_contract", "timer_contract", "monitor_contract", "used_trap_ops",
           "used_timer_ops", "timer_mutation"},
        "monitor manifest",
    )
    expected_fields = {
        "schema_version": 1,
        "artifact_category": ARTIFACT_CATEGORY,
        "contract_version": CONTRACT_VERSION,
        "test_abi": TEST_ABI,
        "suite_id": "9d2c479b0810f351",
        "source_seed": "4c454d4d41393039",
        "runtime_seed": "4d4f4e49544f5231",
        "checked_result": audit_device.CHECKED_RESULT,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise Core0Error(f"monitor manifest {field} differs")
    audit_device._validate_memory_boundary(manifest.get("memory_contract"))
    audit_device.validate_device_contract(
        _mapping(manifest.get("device_contract"), "monitor device contract")
    )
    if manifest.get("trap_contract") != audit_timer.TRAP_CONTRACT:
        raise Core0Error("monitor trap contract differs")
    if manifest.get("timer_contract") != audit_timer.TIMER_CONTRACT:
        raise Core0Error("monitor timer contract differs")
    if manifest.get("monitor_contract") != MONITOR_CONTRACT:
        raise Core0Error("monitor protocol contract differs")
    functions = _function_closure(manifest)
    foreground_symbol, dispatcher_symbol = (
        functions["foreground_symbol"], functions["dispatcher_symbol"]
    )
    if manifest.get("roots") != [
        {"root_id": 1, "source": FOREGROUND_SOURCE, "llvm": foreground_symbol,
         "signature": {"args": []}},
        {"root_id": 2, "source": DISPATCH_SOURCE, "llvm": dispatcher_symbol,
         "signature": {"args": ["u64"] * 9}},
    ]:
        raise Core0Error("monitor root closure differs")
    timer_by_id = {str(item["stable_id"]): item for item in audit_timer.TIMER_OPS}
    used_timer = _list(manifest.get("used_timer_ops"), "monitor timer operations")
    if (len(used_timer) != len(timer_by_id)
            or len({str(_mapping(item, "timer operation").get("stable_id"))
                    for item in used_timer}) != len(timer_by_id)
            or any(timer_by_id.get(str(_mapping(item, "timer operation").get("stable_id"))) != item
                   for item in used_timer)):
        raise Core0Error("monitor timer operation closure differs")
    trap_by_id = {
        stable_id: {"stable_id": stable_id, "llvm_symbol": symbol,
                    "source_identity": source,
                    "effects": ["sync-trap", "machine-state"],
                    "arguments": [], "result": "u64-context-mask"}
        for stable_id, symbol, source in audit_trap.TRAP_OPS
        if symbol in TRAP_EXTERNALS
    }
    used_traps = _list(manifest.get("used_trap_ops"), "monitor trap operations")
    if (len(used_traps) != 2
            or {str(_mapping(item, "trap operation").get("stable_id"))
                for item in used_traps} != set(trap_by_id)
            or any(trap_by_id.get(str(_mapping(item, "trap operation").get("stable_id"))) != item
                   for item in used_traps)):
        raise Core0Error("monitor synchronous-trap operation closure differs")
    if manifest.get("machine_primitives") != MACHINE_PRIMITIVES:
        raise Core0Error("monitor machine-primitive closure differs")
    if manifest.get("timer_mutation") != {
        "identity": "none", "production_selectable": False,
        "transform_stage": "none", "match_count": 0, "expected_delta": None,
    }:
        raise Core0Error("monitor image is not bound to the clean timer startup")
    _require_pinned(MONITOR_MANIFEST_CANONICAL_SHA256, "monitor manifest closure")
    observed_digest = _canonical_sha256(manifest)
    if observed_digest != MONITOR_MANIFEST_CANONICAL_SHA256:
        raise Core0Error(
            "monitor exact source/body/dependency closure differs: " + observed_digest
        )
    return dict(manifest)


def validate_monitor_abi(value: object, manifest: Mapping[str, object]) -> dict[str, object]:
    abi = _mapping(value, "monitor ABI")
    if dict(abi) != MONITOR_ABI:
        raise Core0Error("monitor ABI differs from lemma-monitor-v1")
    if (manifest.get("contract_version") != abi.get("contract_version")
            or manifest.get("test_abi") != abi.get("name")
            or manifest.get("monitor_contract") != MONITOR_CONTRACT):
        raise Core0Error("monitor ABI is not bound to its manifest")
    return dict(abi)


def validate_monitor_companions(
    manifest: Mapping[str, object], normalized: str, symbols: str
) -> None:
    if not normalized.endswith("\n") or normalized.splitlines()[0] != (
        f"contract={CONTRACT_VERSION}"
    ):
        raise Core0Error("monitor normalized companion boundary differs")
    _require_pinned(MONITOR_NORMALIZED_SHA256, "monitor normalized closure")
    if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != MONITOR_NORMALIZED_SHA256:
        raise Core0Error("monitor normalized source closure differs")
    lines = normalized.splitlines()
    roots = _list(manifest.get("roots"), "monitor roots")
    expected_roots = [
        f"root={root['root_id']};source={root['source']};signature="
        + ('{"args":[]}' if index == 0 else
           '{"args":["u64","u64","u64","u64","u64","u64","u64","u64","u64"]}')
        for index, root in enumerate(roots)
    ]
    if [line for line in lines if line.startswith("root=")] != expected_roots:
        raise Core0Error("monitor normalized root closure differs")
    expected_symbols: list[str] = []
    for kind in ("scalar_functions", "action_functions"):
        for raw in _list(manifest.get(kind), kind):
            function = _mapping(raw, kind)
            expected_symbols.append(f"source={function['source']};llvm={function['llvm']}")
            if kind == "scalar_functions":
                expected = f"scalar={function['source']};body={function['body']}"
            else:
                direct = "[" + ",".join(function["direct_effects"]) + "]"
                transitive = "[" + ",".join(function["transitive_effects"]) + "]"
                expected = (f"action={function['source']};direct={direct};"
                            f"transitive={transitive};body={function['body']}")
            if lines.count(expected) != 1:
                raise Core0Error(f"monitor normalized body/effects drifted for {function['source']}")
    if symbols.splitlines() != expected_symbols:
        raise Core0Error("monitor symbols companion differs from the exact source/LLVM closure")
    if lines.count("monitor-abi=lemma-monitor-v1") != 1:
        raise Core0Error("monitor normalized companion omits its exact ABI")
    for prefix, field in (
        ("memory-op=", "used_memory_ops"), ("device-op=", "used_device_ops"),
        ("trap-op=", "used_trap_ops"), ("timer-op=", "used_timer_ops"),
    ):
        expected = Counter(
            prefix + str(_mapping(item, field)["stable_id"])
            for item in _list(manifest.get(field), field)
        )
        if Counter(line for line in lines if line.startswith(prefix)) != expected:
            raise Core0Error(f"monitor normalized {prefix[:-1]} closure differs")


def _validate_monitor_uart_ir(pre_ir: str, post_ir: str) -> dict[str, object]:
    findings: dict[str, object] = {}
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
                    raise Core0Error("monitor UART source site is truncated")
                (before_i, before), (access_i, access), (after_i, after) = following
                if (before_i, access_i, after_i) != (index + 1, index + 2, index + 3):
                    raise Core0Error("monitor UART fence/access bracket is not contiguous")
                if (audit_device.FENCE_CALL.fullmatch(before) is None
                        or audit_device.FENCE_CALL.fullmatch(after) is None):
                    raise Core0Error("monitor UART source site lacks immediate fences")
                operation = audit_device._access_op(access)
                if operation != marker.group(2) or functions[index] != functions[access_i]:
                    raise Core0Error("monitor UART marker differs from its physical access")
                operations.append(operation)
                access_indices.add(access_i)
            if "lemma.uart-site=" not in ir:
                raise Core0Error("monitor pre-optimization IR lacks UART source markers")
        else:
            for index in audit_device._direct_physical_access_indices(lines):
                address = audit_device.DIRECT_ADDRESS.search(lines[index])
                if (address is None
                        or not audit_device.UART_BASE <= int(address.group(1))
                        < audit_device.UART_BASE + audit_device.UART_SPAN):
                    continue
                operation = audit_device._access_op(lines[index], optimized=True)
                if operation is None:
                    raise Core0Error("optimized monitor UART access is not volatile i8 align 1")
                if (index == 0 or index + 1 >= len(lines)
                        or audit_device.FENCE_CALL.fullmatch(lines[index - 1]) is None
                        or audit_device.FENCE_CALL.fullmatch(lines[index + 1]) is None):
                    raise Core0Error("optimized monitor UART access lacks immediate fences")
                operations.append(operation)
                access_indices.add(index)
            if "lemma.uart-site=" in ir:
                raise Core0Error("optimized monitor IR retained source-only UART markers")
        if tuple(operations) != MONITOR_UART_IR_OPERATIONS:
            raise Core0Error(f"{label} monitor UART operation sequence differs")
        audit_device._validate_constant_pointers(lines, functions, access_indices)
        findings[label] = {
            "operations": operations,
            "accesses": len(operations),
            "functions": sorted({functions[index] for index in access_indices}),
        }
    return findings


def _validate_shutdown_work_witness(
    manifest: Mapping[str, object],
    pre_functions: Mapping[str, audit_memory.IRFunction],
    post_functions: Mapping[str, audit_memory.IRFunction],
    pre_ir: str,
    post_ir: str,
    optimization: str,
) -> dict[str, object]:
    """Bind the private STOP-work witness from checked Action source through LLVM."""
    action_by_source = {
        str(_mapping(item, "monitor Action function")["source"]):
            _mapping(item, "monitor Action function")
        for item in _list(manifest.get("action_functions"), "monitor Action functions")
    }
    stopped_source = "Lemma.Examples.Foundation.Monitor.stoppedWork"
    control_source = "Lemma.Examples.Foundation.Timer.controlStep"
    mix_source = "Lemma.Examples.Foundation.Timer.mixStep"
    write_source = "Lemma.Examples.Foundation.Timer.writeWord"
    stopped = action_by_source.get(stopped_source)
    control = action_by_source.get(control_source)
    mix = action_by_source.get(mix_source)
    write_word = action_by_source.get(write_source)
    if stopped is None or control is None or mix is None or write_word is None:
        raise Core0Error("monitor shutdown witness source functions are missing")
    stopped_body = str(stopped.get("body"))
    if (
        stopped_body.count(
            "(action.call Lemma.Examples.Foundation.Timer.writeWord "
            "[(lit u64 160)"
        ) != 1
        or stopped_body.count(
            "(action.bounded-fold-u64 budget=8 "
            "callback=Lemma.Examples.Foundation.Timer.controlStep count=(lit u32 8)"
        ) != 1
    ):
        raise Core0Error("monitor shutdown work/witness source policy differs")
    control_body = str(control.get("body"))
    if control_body.count(
        "(action.bounded-fold-u64 budget=128 "
        "callback=Lemma.Examples.Foundation.Timer.mixStep "
        "count=(call Lemma.Examples.Foundation.Timer.workQuantum u32 [])"
    ) != 1:
        raise Core0Error("monitor controlStep 128-step source policy differs")
    stopped_llvm = str(stopped.get("llvm"))
    control_llvm = str(control.get("llvm"))
    mix_llvm = str(mix.get("llvm"))
    write_llvm = str(write_word.get("llvm"))
    witness_counts: dict[str, int] = {}
    control_calls: dict[str, int] = {}
    mix_calls: dict[str, int] = {}
    loop_shapes: dict[str, str] = {}
    for label, profile, parsed, ir in (
        ("pre_optimization", "O0", pre_functions, pre_ir),
        ("post_optimization", optimization, post_functions, post_ir),
    ):
        function = parsed.get(stopped_llvm)
        if function is None:
            raise Core0Error(f"monitor {label} IR omits the shutdown work function")
        control_function = parsed.get(control_llvm)
        if control_function is None:
            raise Core0Error(f"monitor {label} IR omits the 128-step control function")
        pattern = rf"\bcall \{{ i64, i64 \}} @{re.escape(write_llvm)}\(i64 160, i64 "
        local_count = len(re.findall(pattern, function.body))
        whole_count = len(re.findall(pattern, ir))
        if local_count != 1 or whole_count != 1:
            raise Core0Error(
                f"monitor {label} IR does not retain the sole events+160 witness write"
            )
        witness_counts[label] = local_count
        local_control_calls = re.findall(
            rf"\bcall \{{ i64, i64 \}} @{re.escape(control_llvm)}"
            rf"\(i32 signext ([0-9A-Za-z_%.+-]+),",
            function.body,
        )
        expected_control_calls = 8 if profile == "O2" else 1
        if len(local_control_calls) != expected_control_calls:
            raise Core0Error(
                f"monitor {label} IR does not retain the eight-quanta STOP work"
            )
        if profile == "O2":
            if local_control_calls != [str(index) for index in range(8)]:
                raise Core0Error(
                    "optimized monitor STOP work is not the exact ordered eight-call chain"
                )
            loop_shapes[label] = "eight-ordered-unrolled-controlStep-calls"
        else:
            if (
                re.search(r"\bicmp ult i32 [^\n]+, 8\b", function.body) is None
                or re.search(r"\badd i32 [^\n]+, 1\b", function.body) is None
                or "br label %action.fold.header." not in function.body
            ):
                raise Core0Error(
                    f"monitor {label} STOP work lacks its bounded loop/backedge"
                )
            loop_shapes[label] = "bounded-eight-controlStep-loop"
        local_mix_calls = len(re.findall(
            rf"\bcall \{{ i64, i64 \}} @{re.escape(mix_llvm)}\(",
            control_function.body,
        ))
        if local_mix_calls != 1:
            raise Core0Error(
                f"monitor {label} controlStep does not retain its mixStep loop body"
            )
        if profile == "O2":
            if (
                re.search(r"\bicmp eq i32 [^\n]+, 128\b", control_function.body) is None
                or re.search(
                    r"br i1 [^\n]+, label %[A-Za-z0-9_.$-]+, "
                    r"label %action\.fold\.body\.\d+",
                    control_function.body,
                ) is None
            ):
                raise Core0Error(
                    "optimized monitor controlStep lacks its exact 128-iteration backedge"
                )
        elif (
            re.search(r"\bicmp ule i32 [^\n]+, 128\b", control_function.body) is None
            or re.search(r"\bicmp ult i32 [^\n]+", control_function.body) is None
            or "br label %action.fold.header." not in control_function.body
        ):
            raise Core0Error(
                f"monitor {label} controlStep lacks its bounded 128-step loop/backedge"
            )
        control_calls[label] = len(local_control_calls)
        mix_calls[label] = local_mix_calls
    return {
        "source": stopped_source,
        "callback": "Lemma.Examples.Foundation.Timer.controlStep",
        "bounded_quanta": 8,
        "region": "events",
        "offset": 160,
        "callee": write_source,
        "volatile_store_proved_by_memory_audit": True,
        "site_counts": {"source": 1, **witness_counts},
        "stopped_work_control_step_calls": control_calls,
        "control_step_mix_body_calls": mix_calls,
        "control_step_iterations": 128,
        "retained_loop_shape": loop_shapes,
    }


def validate_monitor_ir(
    manifest: Mapping[str, object], pre_ir: str, post_ir: str, optimization: str
) -> dict[str, object]:
    if optimization not in {"O0", "O2"}:
        raise Core0Error("monitor IR optimization profile is unsupported")
    for key in ("program.ll", optimization):
        _require_pinned(MONITOR_IR_SHA256.get(key, ""), f"monitor {key} IR closure")
    observed_pre = hashlib.sha256(pre_ir.encode("utf-8")).hexdigest()
    observed_post = hashlib.sha256(post_ir.encode("utf-8")).hexdigest()
    if observed_pre != MONITOR_IR_SHA256["program.ll"]:
        raise Core0Error("monitor pre-optimization LLVM closure differs")
    if observed_post != MONITOR_IR_SHA256[optimization]:
        raise Core0Error(f"monitor {optimization} optimized LLVM closure differs")
    memory = audit_memory.validate_memory_pre_ir(
        manifest, audit_timer._memory_proof_view(pre_ir), require_volatile=True
    )
    uart = _validate_monitor_uart_ir(pre_ir, post_ir)
    for address in (33603576, 33570816):
        if f"inttoptr (i64 {address}" in pre_ir or f"inttoptr (i64 {address}" in post_ir:
            raise Core0Error("compiled monitor contains direct machine-timer MMIO")
    source_closure = _function_closure(manifest)
    pre_functions = audit_memory.parse_ir_functions(pre_ir)
    post_functions = audit_memory.parse_ir_functions(post_ir)
    shutdown_work_witness = _validate_shutdown_work_witness(
        manifest, pre_functions, post_functions, pre_ir, post_ir, optimization
    )
    symbol_by_timer = {
        str(item["stable_id"]): str(item["llvm_symbol"])
        for item in audit_timer.TIMER_OPS
    }
    symbol_by_trap = {
        str(item["stable_id"]): str(item["llvm_symbol"])
        for item in _list(manifest.get("used_trap_ops"), "monitor trap operations")
    }
    source_counts: Counter[str] = Counter()
    pre_counts: Counter[str] = Counter()
    post_counts: Counter[str] = Counter()
    for raw in _list(manifest.get("action_functions"), "monitor Action functions"):
        function = _mapping(raw, "monitor Action function")
        llvm, body = str(function["llvm"]), str(function["body"])
        if llvm not in pre_functions or llvm not in post_functions:
            raise Core0Error(f"monitor pre/post IR omits @{llvm}")
        for stable_id, symbol in {**symbol_by_timer, **symbol_by_trap}.items():
            marker = "action.timer" if stable_id.startswith(("timer.", "irq.")) else "action.trap"
            source_count = body.count(f"({marker} {stable_id} ")
            pre_count = len(re.findall(
                rf"\bcall i64 @{re.escape(symbol)}\(", pre_functions[llvm].body
            ))
            post_count = len(re.findall(
                rf"\bcall i64 @{re.escape(symbol)}\(", post_functions[llvm].body
            ))
            if source_count != pre_count:
                raise Core0Error(
                    f"monitor source/pre-IR machine call count differs for {llvm}/{stable_id}"
                )
            source_counts[stable_id] += source_count
            pre_counts[symbol] += pre_count
            post_counts[symbol] += post_count
    required_ops = set(symbol_by_timer) | set(symbol_by_trap)
    if set(source_counts) != required_ops or any(source_counts[item] <= 0 for item in required_ops):
        raise Core0Error("monitor source machine-operation site closure is incomplete")
    bool_zext = len(re.findall(r"^\s*%[A-Za-z0-9_.$-]+ = zext i1 .* to i64$", pre_ir, re.MULTILINE))
    bool_machine_calls = len(re.findall(
        r"\bcall i64 @core0_(?:irq_restore|timer_set_interrupt)\(i64 %", pre_ir
    ))
    if re.search(r"sext i1 .* to i64", pre_ir):
        raise Core0Error("monitor Bool machine arguments use signed extension")
    optimizer_intrinsics = sorted(set(re.findall(r"declare [^@\n]+@(llvm\.[A-Za-z0-9_.]+)\(", post_ir)))
    observed_source = dict(sorted(source_counts.items()))
    observed_pre_counts = dict(sorted(pre_counts.items()))
    observed_post_counts = dict(sorted(post_counts.items()))
    if (
        observed_source != MONITOR_MACHINE_CALLS_SOURCE
        or observed_pre_counts != MONITOR_MACHINE_CALLS_PRE
        or observed_post_counts != MONITOR_MACHINE_CALLS_POST[optimization]
        or len(pre_functions) != 143
        or len(post_functions) != 143
        or bool_machine_calls != 13
        or bool_zext != 13
        or optimizer_intrinsics
    ):
        raise Core0Error("monitor exact pre/post LLVM inventory differs")
    return {
        "optimization": optimization,
        "pre_ir_sha256": observed_pre,
        "post_ir_sha256": observed_post,
        "definitions": {"pre": len(pre_functions), "post": len(post_functions)},
        "memory": memory,
        "uart": uart,
        "machine_calls": {
            "source": observed_source,
            "pre_optimization": observed_pre_counts,
            "post_optimization": observed_post_counts,
        },
        "bool_machine_arguments": {
            "calls": bool_machine_calls,
            "all_pre_ir_zext": bool_zext,
            "signed_extensions": 0,
        },
        "optimizer_intrinsics": optimizer_intrinsics,
        "machine_timer_mmio_in_program": 0,
        "source_role_closure": source_closure,
        "shutdown_work_witness": shutdown_work_witness,
    }


def validate_monitor_startup_assembly(
    assembly: str, manifest: Mapping[str, object], layout: Mapping[str, object]
) -> dict[str, object]:
    report = audit_timer.validate_timer_startup_assembly(assembly, manifest, layout)
    if report.get("mutation") != "none":
        raise Core0Error("monitor startup is not the clean timer/trap substrate")
    return report


def validate_monitor_machine_disassembly(
    disassembly: str,
    symbol_addresses: Mapping[str, int],
    program_functions: set[str],
    startup_assembly: str,
    manifest: Mapping[str, object],
    optimization: str,
) -> dict[str, object]:
    for profile in ("O0", "O2"):
        _require_pinned(
            MONITOR_START_MACHINE_BODY_SHA256.get(profile, ""),
            f"monitor {profile} _start machine closure",
        )
    report = audit_timer.validate_timer_machine_disassembly(
        disassembly,
        symbol_addresses,
        program_functions,
        startup_assembly,
        manifest,
        optimization,
        expected_start_body_sha256=MONITOR_START_MACHINE_BODY_SHA256,
    )
    if report.get("mutation") != "none":
        raise Core0Error("monitor final image is not the clean machine substrate")
    if (
        report.get("compiled_functions") != 142
        or report.get("compiled_privileged_instructions") != 0
        or report.get("startup_functions") != 16
        or report.get("machine_csr_operations") != 28
        or report.get("machine_slot_sequences") != MONITOR_MACHINE_SLOT_COUNTS
        or report.get("timer_mmio_accesses") != 3
        or report.get("timer_mmio_width_bits") != 64
    ):
        raise Core0Error("monitor final machine count/slot/CSR/MMIO closure differs")
    return report
