#!/usr/bin/env python3
"""Fail-closed host artifact audit for the versioned production kernel package.

This checks declared source/object/privilege closure and actual ELF artifacts.
It is neither a compiler-correctness proof nor evidence of S/U execution.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
import re
import struct
import sys

from audit_core0 import (alloc_section_names, defined_function_symbols, numeric_symbols, parse_definitions_and_calls,
                         parse_load_segments, relocation_types, parse_stack_sizes,
                         validate_loop_stack_call_graph, _ir_definition_body)
from build_core0 import LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS, invalidate_output_file
from build_kernel import (BOOT_FILES, BOOT_OBJECTS, CONTRACTS, ROLE_MODULES, ROLE_ROOTS,
                          UNIT_FILES, USER_OBJECTS, artifact_category, configuration_modules,
                          configuration_roots, development_role, module_closure, source_inputs, startup_case, user_startup_case,
                          validate_configuration_stage, validate_lean_source_realization,
                          LEAN_SOURCE_EXPRESSION, LEAN_UINT_SOURCE_SHA256)
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from audit_device import (_access_op, _valid_access_alignment, _line_functions, DIRECT_ADDRESS, FENCE_CALL, SITE_MARKER,
                          validate_platform_evidence)

MACHINE_SYMBOLS = {
    "_start", "core0_io_fence", "lemma_exec_read_time", "lemma_exec_set_machine_compare",
    "lemma_exec_forward_supervisor", "lemma_exec_firmware_call", "lemma_exec_syscall",
    "lemma_exec_install_satp", "lemma_exec_fence_instruction", "lemma_exec_enter_user",
    "lemma_exec_wait_interrupt", "lemma_machine_fatal", "lemma_machine_double_fault",
    "lemma_supervisor_fatal", "lemma_supervisor_double_fault",
    "lemma_exec_supervisor_pending",
}
SUPERVISOR_SYMBOLS = {"lemma_machine_vector", "lemma_supervisor_vector", "lemma_supervisor_start"}
M_SYMBOLS = {"_start", "lemma_exec_read_time", "lemma_exec_set_machine_compare",
             "lemma_exec_forward_supervisor", "lemma_machine_fatal", "lemma_machine_double_fault", "lemma_machine_vector"}
EXECUTION_OPERATIONS = {
    "physicalRead8": ("physical-read8", None, 0, "word", {"firmware", "kernel"}),
    "physicalRead64": ("physical-read64", None, 0, "word", {"firmware", "kernel"}),
    "physicalWrite8": ("physical-write8", None, 0, "word", {"firmware", "kernel"}),
    "physicalWrite64": ("physical-write64", None, 0, "word", {"firmware", "kernel"}),
    "virtualRead8": ("virtual-read8", None, 0, "word", {"user"}),
    "virtualRead64": ("virtual-read64", None, 0, "word", {"user"}),
    "virtualWrite8": ("virtual-write8", None, 0, "word", {"user"}),
    "virtualWrite64": ("virtual-write64", None, 0, "word", {"user"}),
    "readTime": ("read-time", "lemma_exec_read_time", 0, "word", {"firmware"}),
    "setMachineCompare": ("set-machine-compare", "lemma_exec_set_machine_compare", 1, "word", {"firmware"}),
    "forwardSupervisor": ("forward-supervisor", "lemma_exec_forward_supervisor", 1, "word", {"firmware"}),
    "firmwareCall": ("firmware-call", "lemma_exec_firmware_call", 6, "checked", {"kernel"}),
    "syscall": ("syscall", "lemma_exec_syscall", 6, "checked", {"user"}),
    "installSatp": ("install-satp", "lemma_exec_install_satp", 1, "word", {"kernel"}),
    "fenceInstruction": ("fence-instruction", "lemma_exec_fence_instruction", 0, "word", {"kernel"}),
    "enterUser": ("enter-user", "lemma_exec_enter_user", 1, "word", {"kernel"}),
    "waitInterrupt": ("wait-interrupt", "lemma_exec_wait_interrupt", 0, "word", {"kernel"}),
    "readSupervisorPending": ("supervisor-pending", "lemma_exec_supervisor_pending", 0, "word", {"kernel"}),
}
INTEGER_INSTRUCTIONS = set("add addi addiw addw sub subw mul mulh mulhsu mulhu mulw div divu divw divuw rem remu remw remuw and andi or ori xor xori sll slli sllw slliw srl srli srlw srliw sra srai sraw sraiw slt slti sltu sltiu lui auipc ld lw lwu lh lhu lb lbu sd sw sh sb jal jalr beq bne blt bge bltu bgeu j jr ret mv li nop neg negw not seqz snez sltz sgtz sext.w zext.w beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu fence fence.i sfence.vma csrrw csrrs csrrc csrrwi csrrsi csrrci csrr csrw csrs csrc csrwi csrsi csrci rdcycle rdtime rdinstret wfi mret sret ecall".split())
KNOWN_CSRS = {"mstatus", "mie", "mip", "mcause", "mepc", "mtval", "mtvec", "mscratch", "medeleg", "mideleg",
              "mcounteren", "scounteren", "sstatus", "sie", "sip", "scause", "sepc", "stval", "stvec", "sscratch",
              "satp", "pmpcfg0", "pmpaddr0", "pmpaddr1", "pmpaddr2", "pmpaddr3", "pmpaddr4"}
# These integer optimizer intrinsics have no guest runtime and must disappear
# into the audited integer object closure. No memory intrinsic/helper is allowed.
OPTIMIZER_INTRINSICS = {f"llvm.{operation}.i{width}" for operation in ("umin", "umax", "smin", "smax") for width in (8, 32, 64)}
ROLE_EFFECTS = {
    "firmware": set("checked-access physical-read physical-write mmio-read mmio-write io-order machine-state timer-state interrupt-state".split()),
    "kernel": set("checked-access physical-read physical-write mmio-read mmio-write io-order machine-state firmware-call address-space instruction-sync privilege-transition wait-state interrupt-state may-diverge".split()),
    "user": set("checked-access virtual-read virtual-write user-syscall privilege-transition io-order may-diverge".split()),
}
PRIMITIVE_EFFECTS = {
    "_start": "boot/privilege/pmp/delegation", "core0_io_fence": "io-order",
    "lemma_machine_vector": "machine-trap/context", "lemma_supervisor_vector": "supervisor-trap/context",
    "lemma_exec_read_time": "machine-timer-read", "lemma_exec_set_machine_compare": "machine-timer-write",
    "lemma_exec_forward_supervisor": "supervisor-notification", "lemma_exec_firmware_call": "private-firmware-call",
    "lemma_exec_syscall": "user-syscall", "lemma_exec_install_satp": "address-space/invalidation",
    "lemma_exec_fence_instruction": "instruction-synchronization", "lemma_exec_enter_user": "sanitized-context-return",
    "lemma_exec_wait_interrupt": "interrupt-wait", "lemma_machine_fatal": "fatal-diagnostic",
    "lemma_machine_double_fault": "fatal-diagnostic", "lemma_supervisor_fatal": "fatal-diagnostic",
    "lemma_supervisor_double_fault": "fatal-diagnostic",
    "lemma_supervisor_start": "boot-supervisor-entry",
    "lemma_exec_supervisor_pending": "supervisor-notification-read",
}
CONTEXT_LAYOUT = {"bytes": 288, "kernel_resume_base": 0x80500000, "boot_stack_floor": 0x80501000,
                  "pc_offset": 256, "status_offset": 264, "translation_offset": 272, "scratch_offset": 280}
# Actual relocation-free RV64 body, independently inspected and decoded against
# complete caller/U states. These fingerprints certify artifact identity only.
ENTER_USER_SHA256 = "e5e9881a4880bb062e631ba2a400af5bdea00526dbfc298a263de563e61250ca"
SUPERVISOR_RESTORE_SHA256 = "c6a293d9390c5d362c93068d083a5f4419eb56b650cf13753f4fcd7c76ac1792"
GPR_NAMES = "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()
USER_ATTACKS = {
    "supervisor-csr": ("lemma_user_attack_supervisor_csr", "adversarial-supervisor-csr-read", (0x10002573, 0x00008067)),
    "execute-data": ("lemma_user_attack_execute_data", "adversarial-nx-fetch", (0x000202b7, 0x00028067)),
    "execute-kernel": ("lemma_user_attack_kernel_fetch", "adversarial-kernel-fetch", (0x40100293, 0x01529293, 0x00028067)),
    "execute-misaligned": ("lemma_user_attack_misaligned", "adversarial-illegal-halfword-fetch", (0x000102b7, 0x0022829b, 0x00028067)),
}
USER_ABI_INITIAL_DATA = struct.pack("<2Q", 0, 1)
USER_SYSCALL_WORDS = (0x00050893, 0x00058513, 0x00060593, 0x00068613,
                      0x00070693, 0x00078713, 0x00000073, 0x00008067)


def machine_frame(source: str, symbol: str) -> int:
    """Account the fixed local storage of an already audited typed primitive."""
    match = re.search(rf"^{re.escape(symbol)}:\n(.*?)^\.size {re.escape(symbol)},", source, re.M | re.S)
    if match is None:
        raise Core0Error(f"missing generated machine primitive body: {symbol}")
    body, writes = match[1], []
    for line in body.splitlines():
        instruction = re.match(r"\s*([a-z][a-z0-9.]*)\s+(.*)$", line)
        if instruction is None:
            continue
        operation, operands = instruction.groups()
        fields = [part.strip() for part in operands.split(",")]
        if fields[0] != "sp" or operation in {"sd", "sw", "sh", "sb", "beq", "bne", "blt", "bge", "bltu", "bgeu", "beqz", "bnez"}:
            continue
        writes.append(line.strip())
    sanctioned = {
        "lemma_exec_enter_user": ["addi sp, sp, -16", "addi sp, sp, 16", "mv sp, a0", "ld sp, 16(sp)"],
        "lemma_machine_vector": ["csrrw sp, mscratch, sp", "addi sp, sp, -288", "mv sp, a1", "ld sp, 16(sp)"],
        "lemma_supervisor_vector": ["csrrw sp, sscratch, sp", "addi sp, sp, -288", "mv sp, a1", "ld sp, 16(sp)"],
    }
    if symbol in sanctioned:
        if writes != sanctioned[symbol]:
            raise Core0Error(f"typed context stack switches differ from the closed symbol inventory: {symbol}")
    elif any(re.fullmatch(r"addi sp, sp, -?[0-9]+", line) is None for line in writes):
        raise Core0Error(f"unaccounted generated stack-pointer write: {symbol}")
    amounts = [int(value) for line in writes if (match := re.fullmatch(r"addi sp, sp, (-?[0-9]+)", line))
               for value in (match[1],)]
    if any(amount % 16 for amount in amounts):
        raise Core0Error("typed primitive stack allocation violates 16-byte alignment")
    return sum(-amount for amount in amounts if amount < 0)


def validate_compiled_stack(machine: str, frames: dict[str, int]) -> None:
    """Reject SP writes which cannot be reconciled with LLVM's fixed frames."""
    current = None
    allocations = {symbol: 0 for symbol in frames}
    for line in machine.splitlines():
        label = re.fullmatch(r"([0-9a-fA-F]+) <([A-Za-z_.$][A-Za-z0-9_.$-]*)>:", line.strip())
        if label:
            # LLVM retains local PC-relative labels inside a function. They
            # are not a new executable function or a new stack allocation.
            if label[2] in frames:
                current = label[2]
            elif not label[2].startswith(".L"):
                current = None
            continue
        instruction = re.match(r"\s*[0-9a-fA-F]+:\s+([a-z][a-z0-9.]*)\s+(.*)$", line)
        if instruction is None:
            continue
        operation, operands = instruction.groups()
        words = [word.strip() for word in operands.split(",")]
        if not words or words[0] != "sp" or operation in {"sd", "sw", "sh", "sb"}:
            continue
        if (current not in frames or operation != "addi" or len(words) != 3 or words[1] != "sp"
                or not re.fullmatch(r"-?(?:0x[0-9a-f]+|[0-9]+)", words[2])):
            raise Core0Error(f"unaccounted compiled stack-pointer write: {line.strip()}")
        amount = int(words[2], 16 if "0x" in words[2] else 10)
        if amount % 16:
            raise Core0Error("compiled stack adjustment violates 16-byte alignment")
        if amount < 0:
            allocations[current] += -amount
    if allocations != frames:
        raise Core0Error("compiled fixed stack allocation differs from LLVM frame metadata")


def weighted_stack_graph(ir: str, frames: dict[str, int], primitive_frames: dict[str, int]) -> dict:
    """Reuse the legacy closure/cycle audit and add closed external frame costs."""
    base = validate_loop_stack_call_graph(ir, frames)
    if any(type(size) is not int or size < 0 or size % 16 for size in frames.values()):
        raise Core0Error("LLVM stack frames must be nonnegative aligned byte counts")
    if re.search(r"\b(?:alloca|llvm\.stacksave|llvm\.stackrestore|invoke|callbr)\b", ir):
        raise Core0Error("dynamic/explicit stack allocation or unsupported call boundary")
    calls = {}
    for symbol in frames:
        body = _ir_definition_body(ir, symbol)
        for line in body.splitlines():
            instruction = re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:(?:tail|musttail|notail)\s+)?call\b", line)
            if instruction and not re.search(r"@[A-Za-z0-9_.$-]+\(", line):
                raise Core0Error("indirect stack call is not statically bounded")
        _defined, _declared, called = parse_definitions_and_calls(body)
        unknown = called - set(frames) - set(primitive_frames)
        if unknown:
            raise Core0Error(f"unaccounted external frame below {symbol}: {sorted(unknown)}")
        calls[symbol] = sorted(called)
    memo = {}
    def longest(symbol):
        if symbol in primitive_frames:
            return primitive_frames[symbol], [symbol]
        if symbol not in memo:
            size, path = max((longest(child) for child in calls[symbol]), default=(0, []), key=lambda row: row[0])
            memo[symbol] = frames[symbol] + size, [symbol, *path]
        return memo[symbol]
    for symbol in sorted(frames):
        longest(symbol)
    return {"compiled_graph": base, "primitive_frames": dict(sorted(primitive_frames.items())),
            "weighted_frame_chains": {name: {"bytes": size, "chain": path} for name, (size, path) in sorted(memo.items())}}


def validate_stack_entries(unit: dict, graph: dict, *, capacities: dict[str, int], vector_bytes: int) -> list[dict]:
    entries = []
    for index, root in enumerate(unit["roots"]):
        role = unit["role"]
        domain, extra = (("machine", vector_bytes) if role == "firmware" else
                         ("user", 0) if role == "user" else ("boot", 0) if index == 0 else ("kernel-trap", vector_bytes))
        chain = graph["weighted_frame_chains"].get(root["symbol"])
        if not isinstance(chain, dict):
            raise Core0Error("source root lacks emitted stack chain")
        total, capacity = chain["bytes"] + extra, capacities[domain]
        if total >= capacity:
            raise Core0Error(f"{root['source']} requires {total} bytes against strict {capacity}-byte {domain} stack")
        entries.append({"source": root["source"], "symbol": root["symbol"], "domain": domain,
                        "compiled_and_primitive_chain_bytes": chain["bytes"], "vector_bytes": extra,
                        "total_bytes": total, "capacity_bytes": capacity, "margin_bytes": capacity - total,
                        "chain": chain["chain"]})
    return entries


def validate_owned_task_stack(layout: dict, unit: dict, pre_ir: str) -> dict:
    """Bind the capacity to genuine reachable construction and cleanup code."""
    by_source = {}
    for row in unit["functions"]:
        source = re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"])
        by_source[source] = row["symbol"]
    required = {"Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue",
                "Lemma.Kernel.Memory.Frames.allocateContiguous2", "Lemma.Kernel.Loader.allocateStack",
                "Lemma.Kernel.Loader.installStackPair", "Lemma.Kernel.Loader.storedStack", "Lemma.Kernel.Loader.stackPair",
                "Lemma.Kernel.Loader.releaseStackHandle", "Lemma.Kernel.Loader.teardown", "Lemma.Kernel.Process.dispatch",
                "Lemma.Kernel.Loader.kernelStackHandleOffset", "Lemma.Kernel.Loader.kernelStackSecondHandleOffset"}
    if not required <= set(by_source):
        raise Core0Error("8-KiB stack lacks its genuine pair construction/validation/teardown source closure")
    for source, value in (("Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue", layout["task_kernel_stack_bytes"]),
                          ("Lemma.Kernel.Loader.kernelStackHandleOffset", 2400),
                          ("Lemma.Kernel.Loader.kernelStackSecondHandleOffset", 2480)):
        body = _ir_definition_body(pre_ir, by_source[source])
        if re.fullmatch(r"\s*entry:\s*ret i64 " + str(value) + r"\s*", body) is None:
            raise Core0Error("task-stack source constant differs from its exact emitted UInt64 value")
    for caller, callees in {
        "Lemma.Kernel.Loader.allocateStack": ["Lemma.Kernel.Memory.Frames.allocateContiguous2"],
        "Lemma.Kernel.Loader.installStackPair": ["Lemma.Kernel.Loader.stackPair"],
        "Lemma.Kernel.Loader.teardown": ["Lemma.Kernel.Loader.storedStack", "Lemma.Kernel.Loader.releaseStackHandle"],
        "Lemma.Kernel.Loader.storedStack": ["Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue"],
        "Lemma.Kernel.Process.dispatch": ["Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue"],
    }.items():
        calls = parse_definitions_and_calls(_ir_definition_body(pre_ir, by_source[caller]))[2]
        if not {by_source[callee] for callee in callees} <= calls:
            raise Core0Error("owned task-stack source call chain omits pair construction or validation")
    return {"pages": layout["task_kernel_stack_pages"], "bytes": layout["task_kernel_stack_bytes"],
            "construction": "owned-physically-contiguous-pair", "first_handle_offset": 2400, "second_handle_offset": 2480,
            "base_owned_task_frames": 15 + layout["task_kernel_stack_pages"],
            "source_functions": {source: by_source[source] for source in sorted(required)}}


def validate_user_abi_data(section_text: str, data: bytes, symbol_text: str,
                           assembly: str, *, object_file: str) -> dict:
    """Account for the sole declarative initializer emitted by Lean startup.

    Compiled unit globals remain forbidden. This admits only the named input
    section of the startup object and its exact linked payload, not arbitrary
    writable data or additional target object symbols.
    """
    if object_file not in {"user/startup.o", "user/image.elf"}:
        raise Core0Error("user ABI data lacks its exact startup-object ownership")
    linked = object_file == "user/image.elf"
    section, address, alignment = (".data", 0x20000, 4096) if linked else (".data.user_abi", 0, 8)
    rows = re.findall(r"(?m)^\s*\[\s*(\d+)\]\s+" + re.escape(section)
                      + r"\s+PROGBITS\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)\s+00\s+([A-Z]*)\s+0\s+0\s+(\d+)\s*$", section_text)
    if (len(rows) != 1 or int(rows[0][1], 16) != address or int(rows[0][2], 16) != 16
            or set(rows[0][3]) != {"W", "A"} or len(rows[0][3]) != 2 or int(rows[0][4]) != alignment
            or data != USER_ABI_INITIAL_DATA):
        raise Core0Error("user ABI initializer section/bytes/permissions/alignment differ")
    objects = [line for line in symbol_text.splitlines() if len(line.split()) >= 8
               and line.split()[0].endswith(":") and line.split()[3] == "OBJECT" and line.split()[6] != "UND"]
    expected = '.section .data.user_abi, "aw", @progbits\n.balign 8\n.quad 0\n.quad 1\n.option pop\n'
    if objects or assembly.count(expected) != 1 or len(re.findall(r"(?m)^\.section \.data", assembly)) != 1:
        raise Core0Error("user ABI initializer generated source or object-symbol closure differs")
    return {"source": "Lemma.User.ABI.version", "owned_input": "user/startup.o(.data.user_abi)",
            "section": section, "virtual_address": address, "bytes": 16, "alignment": alignment,
            "words": [0, 1], "writable": True, "executable": False,
            "sha256": hashlib.sha256(data).hexdigest()}


def user_primitive_rows(case: str) -> list[dict]:
    if case not in {"none", *USER_ATTACKS}:
        raise Core0Error("unknown user startup case")
    rows = [{"symbol": "_user_start", "privilege": "U", "effect": "user-entry/exit"},
            {"symbol": "lemma_exec_syscall", "privilege": "U", "effect": "user-syscall"}]
    if case in USER_ATTACKS:
        symbol, effect, _ = USER_ATTACKS[case]
        rows.append({"symbol": symbol, "privilege": "U", "effect": effect})
    return rows


def _object(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} must be an object")
    return value


def _array(value: object, context: str) -> list:
    if not isinstance(value, list):
        raise Core0Error(f"{context} must be an array")
    return value


def _integer(value: object, context: str) -> int:
    if type(value) is not int or value < 0:
        raise Core0Error(f"{context} must be a nonnegative integer")
    return value


def _keys(value: dict, expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise Core0Error(f"{context} fields differ from the closed schema")


def validate_unit(value: object, role: str, *, configuration: str = "normal") -> dict:
    unit = _object(value, f"{role} unit")
    _keys(unit, {"schema_version", "artifact_category", "contract_version", "configuration", "role", "roots", "functions",
                 "used_execution_ops", "used_device_ops", "used_loops"}, "unit")
    category = ("production" if configuration == "normal" else "development") + f"-{role}-unit"
    if (unit.get("schema_version") != 1 or type(unit.get("schema_version")) is not int
            or unit.get("artifact_category") != category or unit.get("configuration") != configuration
            or unit.get("role") != role or unit.get("contract_version") != CONTRACTS[role]):
        raise Core0Error(f"{role} unit identity/version differs")
    roots = _array(unit.get("roots"), f"{role} roots")
    expected = [(source, list(args)) for source, args in configuration_roots(configuration)[role]]
    if [(row.get("source"), row.get("args")) for row in roots if isinstance(row, dict)] != expected or len(roots) != len(expected):
        raise Core0Error(f"{role} exact production roots/signatures differ")
    for index, raw in enumerate(roots, 1):
        row = _object(raw, "root")
        _keys(row, {"id", "source", "symbol", "args"}, "root")
        if type(row.get("id")) is not int or row["id"] != index:
            raise Core0Error("root identifiers differ from the exact export order")
    functions = _array(unit.get("functions"), f"{role} functions")
    if not functions:
        raise Core0Error(f"{role} function corpus is empty")
    symbols, sources = set(), set()
    for raw in functions:
        row = _object(raw, "function")
        _keys(row, {"source", "symbol", "args", "effects"}, "function")
        source, symbol = row.get("source"), row.get("symbol")
        production_identity = isinstance(source, str) and (
            source.startswith("Lemma.") or re.fullmatch(r"_private\.(Lemma(?:\.[A-Za-z0-9_]+)+)\.[0-9]+\.\1\.[A-Za-z0-9_.$]+", source) is not None)
        if not production_identity or any(token in source.lower() for token in (".test.", "examples", "mutation")):
            raise Core0Error("function lacks a production Lean source identity")
        if ".Development." in source:
            module = configuration_modules(configuration)[role]
            if not development_role(configuration, role) or not re.search(r"(?:^|\.[0-9]+\.)" + re.escape(module) + r"\.", source):
                raise Core0Error("development source escapes its exact selected module namespace")
        if not isinstance(symbol, str) or not re.fullmatch("lemma_" + role + r"_[A-Za-z0-9_.$]+", symbol):
            raise Core0Error(f"function symbol lacks role prefix: {symbol}")
        if symbol in symbols or source in sources:
            raise Core0Error("duplicate function source/symbol")
        symbols.add(symbol); sources.add(source)
        if any(ty not in {"bool", "u8", "u32", "u64"} for ty in _array(row.get("args"), "function args")):
            raise Core0Error("unadmitted argument type")
        effects = _array(row.get("effects"), "function effects")
        if any(not isinstance(effect, str) for effect in effects) or len(effects) != len(set(effects)) or not set(effects) <= ROLE_EFFECTS[role]:
            raise Core0Error("function effect catalog escapes role authority")
    for root in roots:
        if not any(row["source"] == root["source"] and row["symbol"] == root["symbol"] and row["args"] == root["args"] for row in functions):
            raise Core0Error("root/function signature or symbol mismatch")
    seen = set()
    for raw in _array(unit.get("used_execution_ops"), "execution catalog"):
        row = _object(raw, "execution operation")
        _keys(row, {"stable_id", "source_identity", "primitive_symbol", "arguments", "returnkind"}, "execution operation")
        identity = row.get("source_identity")
        suffix = identity.rsplit(".", 1)[-1] if isinstance(identity, str) else ""
        if suffix not in EXECUTION_OPERATIONS or identity != "Lemma.Core0.Execution.Op." + suffix:
            raise Core0Error("unknown execution operation identity")
        stable, primitive, argc, result, roles = EXECUTION_OPERATIONS[suffix]
        if (role not in roles or row.get("stable_id") != "execution." + stable or row.get("primitive_symbol") != primitive
                or row.get("arguments") != ["u64"] * argc or row.get("returnkind") != result or suffix in seen):
            raise Core0Error(f"execution operation contract/privilege differs: {suffix}")
        seen.add(suffix)
    callbacks = set()
    by_source = {row["source"]: row for row in functions}
    for raw in _array(unit.get("used_loops"), "Action loop catalog"):
        row = _object(raw, "Action loop")
        callback = row.get("callback")
        if (set(row) != {"stable_id", "callback"} or row.get("stable_id") != "action.loop" or role == "firmware"
                or not isinstance(callback, str) or callback not in by_source or by_source[callback]["args"] != []
                or callback in callbacks):
            raise Core0Error("Action loop has an unknown/duplicate/nonclosed callback or unauthorized role")
        callbacks.add(callback)
    if bool(callbacks) != any("may-diverge" in row["effects"] for row in functions):
        raise Core0Error("Action loop catalog and may-diverge effect closure disagree")
    device = _array(unit.get("used_device_ops"), "device catalog")
    if role == "user" and device:
        raise Core0Error("ordinary user code cannot have device authority")
    device_ids = set()
    expected_devices = {
        "uart.read-status": ("uartReadStatus", "uart.lsr.read8", 5, "read", None),
        "uart.read-byte": ("uartReadByte", "uart.rbr.read8", 0, "read", None),
        "uart.write-byte": ("uartWriteByte", "uart.thr.write8", 0, "write", None),
        "uart.enable-reset-fifo": ("uartEnableAndResetFifo", "uart.fcr.enable-reset", 2, "write", 7),
    }
    if role == "kernel" and unit["contract_version"] == "core0-kernel-v0.2":
        expected_devices["uart.enable-reset-fifo-trigger14"] = (
            "uartEnableAndResetFifo14", "uart.fcr.enable-reset-trigger14", 2, "write", 199)
    for raw in device:
        row = _object(raw, "device operation")
        _keys(row, {"stable_id", "source_identity", "lowering_id", "base", "offset", "width_bytes", "access", "fixed_value",
                    "volatile", "fence_before", "fence_after", "sites"}, "device operation")
        stable = row.get("stable_id")
        if stable not in expected_devices or stable in device_ids:
            raise Core0Error("unknown/duplicate production device operation")
        constructor, lowering, offset, access, value = expected_devices[stable]
        if (any(type(row.get(key)) is not int for key in ("base", "offset", "width_bytes"))
                or value is not None and type(row.get("fixed_value")) is not int
                or any(row.get(key) is not True for key in ("volatile", "fence_before", "fence_after"))
                or any(row.get(key) != expected for key, expected in {
            "source_identity": "Lemma.Core0.Memory.Action." + constructor,
            "lowering_id": lowering, "base": 0x10000000, "offset": offset,
            "width_bytes": 1, "access": access, "fixed_value": value,
            "volatile": True, "fence_before": True, "fence_after": True}.items())):
            raise Core0Error("compiled device operation differs from pinned UART contract")
        sites = _array(row.get("sites"), "device sites")
        if not sites or any(not isinstance(site, dict) or type(site.get("site")) is not int or site["site"] < 0 or site.get("symbol") not in symbols for site in sites):
            raise Core0Error("device site/source-function binding missing")
        for site in sites:
            _keys(site, {"site", "symbol"}, "device site")
        if stable == "uart.enable-reset-fifo-trigger14" and (
                len(sites) != 1 or not any(function["source"] == "Lemma.Platform.LemmaVM.ConsoleDevice.initialize14"
                                         and function["symbol"] == sites[0]["symbol"] and function["args"] == []
                                         for function in functions)):
            raise Core0Error("trigger14 FIFO site lacks its sole closed production initializer")
        device_ids.add(stable)
    return unit


def validate_layout(value: object, *, configuration: str = "normal") -> dict:
    layout = _object(value, "layout")
    _keys(layout, {"schema_version", "contract_version", "configuration", "startup_case", "user_startup_case", "ram_base", "ram_limit",
                   "frame_bytes", "frame_count", "task_kernel_stack_pages", "task_kernel_stack_bytes", "context", "intervals", "user"}, "layout")
    if type(layout.get("schema_version")) is not int or layout.get("schema_version") != 1 or layout.get("contract_version") != "lemma-kernel-layout-v1" or layout.get("configuration") != configuration or layout.get("startup_case") != startup_case(configuration) or layout.get("user_startup_case") != user_startup_case(configuration):
        raise Core0Error("unknown kernel layout version")
    if (layout.get("ram_base"), layout.get("ram_limit"), layout.get("frame_bytes"), layout.get("frame_count")) != (0x80000000, 0x88000000, 4096, 512):
        raise Core0Error("pinned RAM/frame contract differs")
    if (type(layout.get("task_kernel_stack_pages")) is not int or type(layout.get("task_kernel_stack_bytes")) is not int
            or layout["task_kernel_stack_pages"] != 2 or layout["task_kernel_stack_bytes"] != layout["frame_bytes"] * layout["task_kernel_stack_pages"]):
        raise Core0Error("owned two-page kernel stack construction contract differs")
    if layout.get("context") != CONTEXT_LAYOUT:
        raise Core0Error("fixed supervisor context/stack contract differs")
    expected = {"firmware": (0x80000000, 0x80010000), "firmware-private": (0x80100000, 0x80110000),
                "supervisor": (0x80200000, 0x80300000), "metadata": (0x80400000, 0x80500000),
                "supervisor-stack": (0x80500000, 0x80510000), "boot-package": (0x80600000, 0x80700000),
                "frame-pool": (0x82000000, 0x82200000), "dtb-reserve": (0x87e00000, 0x88000000)}
    rows = _array(layout.get("intervals"), "layout intervals")
    observed = {}
    for raw in rows:
        row = _object(raw, "interval")
        name = row.get("name")
        if not isinstance(name, str) or name in observed:
            raise Core0Error("duplicate/invalid layout interval")
        observed[name] = (_integer(row.get("base"), "base"), _integer(row.get("limit"), "limit"))
    if observed != expected:
        raise Core0Error("authoritative reserved-region contract differs")
    user = _object(layout.get("user"), "user layout")
    if user != {"text_base": 0x10000, "text_limit": 0x1f000, "data_base": 0x20000, "data_bytes": 4096,
                "stack_base": 0x3fffc000, "stack_pages": 2}:
        raise Core0Error("user virtual layout differs")
    return layout


def validate_catalog(value: object, *, configuration: str, stage: str) -> set[str]:
    validate_configuration_stage(configuration, stage)
    catalog = _object(value, "primitive catalog")
    _keys(catalog, {"schema_version", "contract_version", "stage", "configuration", "startup_case", "user_startup_case", "symbols", "user_symbols"}, "primitive catalog")
    expected_machine = MACHINE_SYMBOLS | (SUPERVISOR_SYMBOLS if stage == "supervisor" else set())
    if startup_case(configuration) == "machine-origin-probe":
        expected_machine |= {"lemma_machine_vector"}
    rows = [_object(row, "machine symbol") for row in _array(catalog.get("symbols"), "machine symbols")]
    if (type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != 1
            or catalog.get("contract_version") != "lemma-execution-v1" or catalog.get("stage") != stage
            or catalog.get("configuration") != configuration or catalog.get("startup_case") != startup_case(configuration) or catalog.get("user_startup_case") != user_startup_case(configuration)
            or {row.get("symbol") for row in rows} != expected_machine or len(rows) != len(expected_machine)):
        raise Core0Error("closed platform primitive catalog differs")
    for row in rows:
        _keys(row, {"symbol", "privilege", "effect"}, "machine symbol")
        if row.get("privilege") != ("M" if row["symbol"] in M_SYMBOLS else "S") or row.get("effect") != PRIMITIVE_EFFECTS[row["symbol"]]:
            raise Core0Error("machine primitive privilege/effect differs")
    if catalog.get("user_symbols") != user_primitive_rows(user_startup_case(configuration)):
        raise Core0Error("closed user primitive privilege/effect catalog differs")
    return expected_machine


def validate_startup_case(text: str, ranges: dict[str, tuple[int, int]], case: str) -> dict:
    if case not in {"normal", "machine-origin-probe"} or "_start" not in ranges:
        raise Core0Error("unknown/missing startup case function")
    begin, size = ranges["_start"]
    pcs = [int(match[1], 16) for line in text.splitlines()
           if (match := re.match(r"\s*([0-9a-f]+):\s+ecall\s*$", line)) and begin <= int(match[1], 16) < begin + size]
    if len(pcs) != (1 if case == "machine-origin-probe" else 0):
        raise Core0Error("startup ECALL inventory differs from the exact generated case")
    return {"case": case, "start_ecall_pcs": pcs}


def _assembly_function(text: str, symbol: str) -> list[str]:
    bodies = re.findall(r"(?ms)^" + re.escape(symbol) + r":\n(.*?)^\.size " + re.escape(symbol) + r",[^\n]*$", text)
    if len(bodies) != 1:
        raise Core0Error(f"generated boundary @{symbol} is missing/duplicated")
    return [line.strip() for line in bodies[0].splitlines() if line.strip() and not line.strip().startswith("#")]


def _raw_function(text: str, ranges: dict[str, tuple[int, int]], symbol: str) -> bytes:
    if symbol not in ranges:
        raise Core0Error(f"machine boundary @{symbol} is missing")
    begin, size = ranges[symbol]
    words = {}
    for line in text.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+\S+", line)
        if match and begin <= (address := int(match[1], 16)) < begin + size:
            if address in words:
                raise Core0Error("machine boundary contains duplicate instruction bytes")
            words[address] = int(match[2], 16)
    if set(words) != set(range(begin, begin + size, 4)):
        raise Core0Error("machine boundary raw instruction byte coverage differs")
    return b"".join(struct.pack("<I", words[address]) for address in sorted(words))


def validate_enter_user_machine(raw: bytes) -> dict:
    if len(raw) != 91 * 4 or hashlib.sha256(raw).hexdigest() != ENTER_USER_SHA256:
        raise Core0Error("actual caller context save/U restore machine bytes differ")
    words = struct.unpack("<91I", raw)
    stores = sum(word & 0x7f == 0x23 for word in words)
    loads = sum(word & 0x7f == 0x03 for word in words)
    if stores != 38 or loads != 37 or words[-1] != 0x10200073:
        raise Core0Error("actual context load/store/return inventory differs")
    return {"instructions": 91, "stores": stores, "loads": loads, "sha256": hashlib.sha256(raw).hexdigest()}


def validate_context_abi(assembly: str, raw_machine: str, ranges: dict[str, tuple[int, int]],
                         user_assembly: str, user_root: str, user_case: str = "none") -> dict:
    restore = ["ld t0, 272(sp)", "csrw satp, t0", "sfence.vma zero, zero", "ld t0, 256(sp)",
               "csrw sepc, t0", "ld t0, 264(sp)", "csrw sstatus, t0"]
    restore += [f"ld {register}, {index * 8}(sp)" for index, register in enumerate(GPR_NAMES) if index and register not in {"sp", "t0"}]
    restore += ["ld t0, 280(sp)", "csrw sscratch, t0", "ld t0, 40(sp)", "ld sp, 16(sp)", "sret"]
    expected = ["addi sp, sp, -16", "sd t0, 0(sp)", "sd t1, 8(sp)", "li t0, 2152726528", "sd zero, 0(t0)"]
    expected += [f"sd {register}, {index * 8}(t0)" for index, register in enumerate(GPR_NAMES) if index and register not in {"sp", "t0", "t1"}]
    expected += ["addi t1, sp, 16", "sd t1, 16(t0)", "ld t1, 0(sp)", "sd t1, 40(t0)", "ld t1, 8(sp)",
                 "sd t1, 48(t0)", "sd ra, 256(t0)", "li t1, 8589934848", "sd t1, 264(t0)",
                 "csrr t1, satp", "sd t1, 272(t0)", "sd zero, 280(t0)", "addi sp, sp, 16", "mv sp, a0", *restore]
    if _assembly_function(assembly, "lemma_exec_enter_user") != expected:
        raise Core0Error("generated caller context save/U restore differs from the closed ABI")
    raw = _raw_function(raw_machine, ranges, "lemma_exec_enter_user")
    validate_enter_user_machine(raw)
    if "lemma_supervisor_vector" in ranges:
        vector = _assembly_function(assembly, "lemma_supervisor_vector")
        if vector[-len(restore):] != restore or hashlib.sha256(_raw_function(raw_machine, ranges, "lemma_supervisor_vector")[-41 * 4:]).hexdigest() != SUPERVISOR_RESTORE_SHA256:
            raise Core0Error("supervisor vector does not share the complete trusted restore ABI")
    if user_case not in {"none", *USER_ATTACKS}:
        raise Core0Error("unknown user startup ABI case")
    user_prefix = [f"call {user_root}"] if user_case == "none" else ["mv gp, zero", "mv tp, zero", f"call {user_root}",
                   "bnez a0, .Luser_exit", f"call {USER_ATTACKS[user_case][0]}", ".Luser_exit:"]
    user_start = [*user_prefix, *(f"li a{register}, 0" for register in range(1, 7)), "li a7, 6",
                  "ecall", ".Luser_exit_returned:", "j .Luser_exit_returned"]
    if _assembly_function(user_assembly, "_user_start") != user_start:
        raise Core0Error("user startup does not forward its initial word to the exact Action root")
    return {"layout": CONTEXT_LAYOUT, "kernel_resume_status": 0x200000100, "saved_gpr_slots": 32,
            "fixed_frame_stores": 36, "temporary_spill_stores": 2, "shared_restore_loads": 35,
            "total_enter_loads": 37, "enter_machine_instructions": 91, "shared_restore_machine_instructions": 41,
            "enter_machine_sha256": hashlib.sha256(raw).hexdigest(), "restore_machine_sha256": SUPERVISOR_RESTORE_SHA256,
            "original_sp_and_t0_t1_preserved": True, "caller_satp_readback_saved": True,
            "kernel_resume_sie": 0, "kernel_resume_scratch": 0, "initial_user_argument": "a0:u64"}


def validate_user_syscall_bridge(assembly: str, raw_machine: str, ranges: dict[str, tuple[int, int]]) -> dict:
    symbol = "lemma_exec_syscall"
    expected = ["mv a7, a0", "mv a0, a1", "mv a1, a2", "mv a2, a3", "mv a3, a4", "mv a4, a5", "ecall", "ret"]
    packed = struct.pack("<8I", *USER_SYSCALL_WORDS)
    if _assembly_function(assembly, symbol) != expected or _raw_function(raw_machine, ranges, symbol) != packed:
        raise Core0Error("user syscall register transport/ECALL/return differs from the declared ABI")
    base, size = ranges[symbol]
    return {"symbol": symbol, "base": base, "bytes": size, "ecall_pc": base + 24,
            "number_register": "a7", "argument_registers": ["a0", "a1", "a2", "a3", "a4"],
            "result_registers": ["a0:status", "a1:value"], "raw_sha256": hashlib.sha256(packed).hexdigest()}


def validate_user_attack_machine(raw_machine: str, ranges: dict[str, tuple[int, int]],
                                 assembly: str, case: str) -> dict:
    attacks = {symbol for symbol in ranges if symbol.startswith("lemma_user_attack_")}
    if case == "none":
        if attacks or ".text.user_adversarial" in assembly:
            raise Core0Error("ordinary user artifact contains quarantined attack code")
        return {"case": "none", "privileged_instruction_exceptions": []}
    if case not in USER_ATTACKS:
        raise Core0Error("unknown quarantined user attack")
    symbol, effect, words = USER_ATTACKS[case]
    packed = struct.pack(f"<{len(words)}I", *words)
    if attacks != {symbol} or _raw_function(raw_machine, ranges, symbol) != packed:
        raise Core0Error("quarantined user attack symbol/opcode/size inventory differs")
    expected = {"supervisor-csr": ["csrr a0, sstatus", "ret"], "execute-data": ["li t0, 131072", "jalr zero, 0(t0)"],
                "execute-kernel": ["li t0, 2149580800", "jalr zero, 0(t0)"],
                "execute-misaligned": ["li t0, 65538", "jalr zero, 0(t0)"]}[case]
    if _assembly_function(assembly, symbol) != expected or len(re.findall(r'(?m)^\.section \.text\.user_adversarial,\s*"ax",\s*@progbits$', assembly)) != 1:
        raise Core0Error("quarantined user attack generated source/section differs")
    base, size = ranges[symbol]
    if case == "execute-misaligned":
        # The pinned CPU supports compressed instructions. 0x10002 is aligned
        # for that hardware, but selects the illegal zero upper halfword of
        # the audited first, uncompressed `mv gp, zero` startup instruction.
        if ranges.get("_user_start", (None, None))[0] != 0x10000 or _raw_function(raw_machine, ranges, "_user_start")[:4] != struct.pack("<I", 0x00000193):
            raise Core0Error("illegal-halfword fixture lacks its exact audited startup word/target")
    return {"case": case, "symbol": symbol, "effect": effect, "base": base, "bytes": size,
            "raw_sha256": hashlib.sha256(packed).hexdigest(),
            "fault_pc": {"supervisor-csr": base, "execute-data": 0x20000,
                         "execute-kernel": 0x80200000, "execute-misaligned": 0x10002}[case],
            "privileged_instruction_exceptions": [base] if case == "supervisor-csr" else []}


def validate_readonly_pmp_lookup(ir: str, unit: dict, *, optimized: bool) -> tuple[set[int], list[dict]]:
    """Admit only LLVM's observed immutable lookup for the fixed PMP policy.

    The closed three-block body proves the table index is below four before
    its sole load. No other global, pointer derivation, use, or load is admitted.
    """
    lines = ir.splitlines()
    globals_ = [line.strip() for line in lines if re.match(r"^\s*@", line)]
    if not globals_:
        return set(), []
    source = "Lemma.Kernel.MachineServices.expectedPmp"
    rows = [row for row in unit["functions"] if row["source"] == source]
    if not optimized or unit["role"] != "kernel" or len(rows) != 1 or rows[0]["args"] != ["u64"] or rows[0]["effects"]:
        raise Core0Error("IR global lacks the exact pure kernel PMP source authority")
    symbol = rows[0]["symbol"]
    table = "switch.table." + symbol
    values = [0x20001fff, 0x20041fff, 0x20ffffff, 0x0400001f]
    expected_global = f"@{table} = private unnamed_addr constant [4 x i64] [" + ", ".join(f"i64 {value}" for value in values) + "], align 8"
    if globals_ != [expected_global] or len(re.findall(r"@" + re.escape(table) + r"(?![A-Za-z0-9_.$-])", ir)) != 2:
        raise Core0Error("readonly PMP table global/content/use inventory differs")
    from audit_memory import parse_ir_functions, _parse_blocks
    functions = parse_ir_functions(ir)
    function = functions.get(symbol)
    if function is None or not re.search(r"\bi64 @" + re.escape(symbol) + r"\(i64 %arg0\)", function.header):
        raise Core0Error("readonly PMP lookup LLVM signature differs")
    load = "%switch.load = load i64, ptr %switch.gep, align 8"
    expected_blocks = {
        "entry": ["%0 = icmp ult i64 %arg0, 4", "br i1 %0, label %switch.lookup, label %if.merge.2"],
        "switch.lookup": [f"%switch.gep = getelementptr inbounds nuw [4 x i64], ptr @{table}, i64 0, i64 %arg0",
                          load, "br label %if.merge.2"],
        "if.merge.2": ["%if.result7 = phi i64 [ %switch.load, %switch.lookup ], [ 262655, %entry ]", "ret i64 %if.result7"],
    }
    blocks = _parse_blocks("\n".join(line.split(";", 1)[0] for line in function.body.splitlines()), symbol)
    if blocks != expected_blocks:
        raise Core0Error("readonly PMP lookup lacks its exact dominating bound guard/body")
    owners = _line_functions(lines)
    load_sites = {index for index, line in enumerate(lines) if line.strip() == load and owners[index] == symbol}
    if len(load_sites) != 1:
        raise Core0Error("readonly PMP lookup load inventory differs")
    return load_sites, [{"source": source, "function": symbol, "global": table, "values": values,
                         "element_bits": 64, "alignment_bytes": 8, "index_bound": 4, "default": 262655,
                         "guarded_loads": 1, "readonly": True}]


def validate_pmp_constant_section(section_text: str, raw: bytes, *, object_file: str, tables: list[dict]) -> dict:
    values = [0x20001fff, 0x20041fff, 0x20ffffff, 0x0400001f]
    if (object_file != "kernel/program.o" or len(tables) != 1
            or tables[0].get("source") != "Lemma.Kernel.MachineServices.expectedPmp"
            or tables[0].get("values") != values or tables[0].get("readonly") is not True):
        raise Core0Error("32-byte constant section lacks its exact kernel PMP IR provenance")
    section_rows = re.findall(r"(?m)^.*\.rodata\.cst32\s+.*$", section_text)
    expected = r"\s*\[\s*\d+\]\s+\.rodata\.cst32\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+000020\s+20\s+AM\s+0\s+0\s+8\s*"
    if len(section_rows) != 1 or not re.fullmatch(expected, section_rows[0]) or raw != struct.pack("<4Q", *values):
        raise Core0Error("PMP constant section size/flags/alignment/little-endian bytes differ")
    return {"object": object_file, "section": ".rodata.cst32", "bytes": 32, "flags": "AM", "alignment": 8,
            "source": tables[0]["source"], "values": values}


def _kernel_access_op(line: str, unit: dict, *, optimized: bool = False) -> str | None:
    """Keep the new closed FCR byte outside every legacy device recognizer."""
    ordinary = _access_op(line, optimized=optimized)
    if ordinary is not None:
        return ordinary
    if unit.get("role") != "kernel" or unit.get("contract_version") != "core0-kernel-v0.2":
        return None
    value = r"(?:199|-57)" if optimized else "199"
    store = re.fullmatch(r"store volatile i8 " + value +
                         r", ptr inttoptr \(i64 268435458 to ptr\), align ([0-9]+)", line.strip())
    if store and _valid_access_alignment(0x10000002, int(store[1]), optimized=optimized):
        return "uart.fcr.enable-reset-trigger14"
    return None


def validate_kernel_uart_initialize(ir: str, unit: dict, *, optimized: bool) -> None:
    """Bind the closed FIFO site to the first boot service and one direct call."""
    operations = [row for row in unit["used_device_ops"] if row["stable_id"] == "uart.enable-reset-fifo-trigger14"]
    if not operations:
        return
    by_source = {row["source"]: row["symbol"] for row in unit["functions"]}
    initialize = by_source.get("Lemma.Platform.LemmaVM.ConsoleDevice.initialize14")
    boot = by_source.get("Lemma.Kernel.Entry.bootServices")
    if initialize is None or boot is None:
        raise Core0Error("trigger14 FIFO lacks its exact initializer/boot source closure")
    if not optimized:
        body = _ir_definition_body(ir, boot)
        calls = re.findall(r"(?m)^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:tail )?call\s+[^\n]*?@([-A-Za-z0-9_.$]+)\(", body)
        if not calls or calls[0] != initialize or calls.count(initialize) != 1:
            raise Core0Error("boot services do not initialize the FIFO once before their first effect")
        total = len(re.findall(r"(?m)^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:tail )?call\s+[^\n]*?@" + re.escape(initialize) + r"\(", ir))
        if total != 1:
            raise Core0Error("compiled boot closure contains an additional FIFO reset")


def validate_ir(ir: str, unit: dict, *, optimized: bool) -> dict:
    definitions, declarations, calls = parse_definitions_and_calls(ir)
    functions = {row["symbol"] for row in unit["functions"]}
    primitives = {row["primitive_symbol"] for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
    if unit["role"] != "user":
        primitives.add("core0_io_fence")
    intrinsic = OPTIMIZER_INTRINSICS if optimized else set()
    if (not definitions or (definitions != functions if not optimized else not definitions <= functions)
            or not declarations <= primitives | intrinsic or not calls <= functions | primitives | intrinsic):
        raise Core0Error("LLVM definitions/declarations/calls escape the closed unit catalog")
    if re.search(r"\basm\b|\binvoke\b|\bcallbr\b|\bblockaddress\b|\bcomdat\b|\bthread_local\b", ir):
        raise Core0Error("unsupported LLVM control/runtime construct")
    for line in ir.splitlines():
        call_instruction = re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:(?:tail|musttail|notail)\s+)?call\b", line)
        if call_instruction and not re.search(r"@[-A-Za-z0-9_.$]+\(", line):
            raise Core0Error("indirect or unparseable LLVM call")
    if 'target triple = "riscv64-unknown-unknown-elf"' not in ir:
        raise Core0Error("LLVM target triple differs")
    if not optimized:
        types = {"bool": "i1", "u8": "i8", "u32": "i32", "u64": "i64"}
        for row in unit["functions"]:
            matches = re.findall(r"(?m)^define\s+[^\n]*@" + re.escape(row["symbol"]) + r"\(([^\n]*)\)", ir)
            if len(matches) != 1 or re.findall(r"\b(i1|i8|i32|i64)\b", matches[0]) != [types[ty] for ty in row["args"]]:
                raise Core0Error("source manifest/LLVM function argument signature differs")
        by_source = {row["source"]: row["symbol"] for row in unit["functions"]}
        for loop in unit["used_loops"]:
            callback = re.escape(by_source[loop["callback"]])
            if not re.search(r"(?m)^define \{ i64, i64 \} @" + callback + r"\(\)", ir) or not re.search(r"\bcall \{ i64, i64 \} @" + callback + r"\(\)", ir):
                raise Core0Error("Action loop callback is not a closed direct checked-Action call in LLVM")
    for operation in unit["used_execution_ops"]:
        symbol = operation["primitive_symbol"]
        if symbol is None or symbol not in declarations:
            continue
        expected_result = "{ i64, i64 }" if operation["returnkind"] == "checked" else "i64"
        expected_args = ", ".join("i64" for _ in operation["arguments"])
        expected = "declare " + expected_result + " @" + symbol + "(" + expected_args + ")"
        if not _primitive_declaration_matches(ir, expected):
            raise Core0Error("LLVM execution primitive calling convention differs")
    if "core0_io_fence" in declarations and not _primitive_declaration_matches(ir, "declare void @core0_io_fence()"):
        raise Core0Error("LLVM IO fence calling convention differs")
    validate_kernel_uart_initialize(ir, unit, optimized=optimized)
    lines = ir.splitlines()
    readonly_load_sites, readonly_tables = validate_readonly_pmp_lookup(ir, unit, optimized=optimized)
    line_functions = _line_functions(lines)
    expected_sites = {(site["site"], site["symbol"], operation["lowering_id"])
                      for operation in unit["used_device_ops"] for site in operation["sites"]}
    observed_sites = set()
    actual_device_operations = []
    memory_operations = {row["source_identity"].rsplit(".", 1)[-1] for row in unit["used_execution_ops"]
                         if row["primitive_symbol"] is None}
    memory_access_counts = {"read8": 0, "read64": 0, "write8": 0, "write64": 0}
    for index, line in enumerate(lines):
        marker = SITE_MARKER.fullmatch(line)
        if marker and not optimized:
            if index + 3 >= len(lines) or FENCE_CALL.fullmatch(lines[index+1]) is None or FENCE_CALL.fullmatch(lines[index+3]) is None:
                raise Core0Error("compiled UART site lacks its contiguous IO fence pair")
            operation = _kernel_access_op(lines[index+2], unit)
            site = (int(marker[1]), line_functions[index], marker[2])
            if operation != marker[2] or site in observed_sites:
                raise Core0Error("compiled UART site is duplicated or its access differs")
            observed_sites.add(site)
        address = DIRECT_ADDRESS.search(line)
        if address and 0x10000000 <= int(address[1]) < 0x10000100 and ("load " in line or line.lstrip().startswith("store ")):
            operation = _kernel_access_op(line, unit, optimized=optimized)
            if (operation is None or index == 0 or index + 1 >= len(lines) or
                    FENCE_CALL.fullmatch(lines[index-1]) is None or FENCE_CALL.fullmatch(lines[index+1]) is None):
                raise Core0Error("UART IR access width/address/volatility/fences differ")
            if unit["role"] == "user":
                raise Core0Error("U-mode unit has physical MMIO")
            actual_device_operations.append(operation)
        elif re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:load|store)\b", line):
            if index in readonly_load_sites:
                continue
            match = re.search(r"\b(load|store) volatile i(8|64)\b", line)
            if not match:
                raise Core0Error("unknown/nonvolatile target RAM access type")
            direction = "Read" if match[1] == "load" else "Write"
            operation_name = ("virtual" if unit["role"] == "user" else "physical") + direction + match[2]
            if operation_name not in memory_operations:
                raise Core0Error("target RAM access lacks its exact source execution-operation authority")
            memory_access_counts[direction.lower() + match[2]] += 1
    if not optimized and observed_sites != expected_sites:
        raise Core0Error("source/device site catalog disagrees with emitted LLVM")
    from collections import Counter
    if Counter(actual_device_operations) != Counter(op for _, _, op in expected_sites):
        raise Core0Error("LLVM removed/duplicated/unaccounted compiled UART operation")
    return {"definitions": sorted(definitions), "calls": sorted(calls), "declarations": sorted(declarations),
            "optimizer_intrinsics": sorted(declarations & intrinsic), "device_operations": actual_device_operations,
            "memory_access_counts": memory_access_counts, "readonly_optimizer_tables": readonly_tables}


def _primitive_declaration_matches(ir: str, expected: str) -> bool:
    """Keep the generated primitive ABI and its opaque side effects exact.

    The exporter marks these boundaries nounwind. LLVM may intern that single
    attribute and add local_unnamed_addr; memory/purity or alternate calling
    convention annotations are not admitted at this boundary.
    """
    declarations = re.findall(r"(?m)^" + re.escape(expected) + r"(?: local_unnamed_addr)? (nounwind|#[0-9]+)$", ir)
    if len(declarations) != 1:
        return False
    attribute = declarations[0]
    if attribute == "nounwind":
        return True
    groups = re.findall(r"(?m)^attributes " + re.escape(attribute) + r" = \{([^\n]*)\}$", ir)
    return len(groups) == 1 and groups[0].strip() == "nounwind"


def function_ranges(symbol_text: str) -> dict[str, tuple[int, int]]:
    ranges = {}
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].endswith(":") and fields[3] == "FUNC" and fields[6] != "UND":
            name, address, size = fields[7], int(fields[1], 16), int(fields[2], 0)
            if name in ranges or size <= 0 or size % 4 or address % 4:
                raise Core0Error("duplicate/empty/unaligned integer function range")
            ranges[name] = (address, size)
    ordered = sorted(ranges.values())
    if not ordered or any(left + size > right for (left, size), (right, _) in zip(ordered, ordered[1:])):
        raise Core0Error("empty/overlapping executable function range corpus")
    return ranges


def validate_machine(text: str, *, user: bool = False,
                     ranges: dict[str, tuple[int, int]] | None = None, user_csr_pc: int | None = None) -> None:
    if user_csr_pc is not None and (not user or type(user_csr_pc) is not int):
        raise Core0Error("CSR exception lacks exact user instruction address")
    found = 0
    expected = None if ranges is None else {address for begin, size in ranges.values() for address in range(begin, begin+size, 4)}
    observed = set()
    for line in text.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if not match:
            continue
        address = int(match[1], 16)
        if ranges is not None and not any(begin <= address < begin+size for begin, size in ranges.values()):
            continue  # source-bound object constant pools are not FUNC bytes
        if address in observed or expected is not None and address not in expected:
            raise Core0Error("duplicate/unaligned instruction inside a function range")
        observed.add(address)
        instruction, operands = match[2], match[3]
        found += 1
        if instruction not in INTEGER_INSTRUCTIONS:
            raise Core0Error(f"unknown/noninteger/compressed machine instruction: {instruction}")
        allowed_csr = address == user_csr_pc and instruction == "csrr" and operands.replace(" ", "") == "a0,sstatus"
        if user and (instruction.startswith("csr") and not allowed_csr or instruction in {"mret", "sret", "wfi", "sfence.vma"}):
            raise Core0Error("ordinary user image contains privileged machine instructions")
        if instruction.startswith("csr"):
            names = re.findall(r"\b(?:[ms][a-z][a-z0-9]+|satp|pmp[a-z0-9]+)\b", operands)
            if not names or not set(names) <= KNOWN_CSRS:
                raise Core0Error("unknown CSR in platform code")
    if not found:
        raise Core0Error("empty machine instruction corpus")
    if expected is not None and observed != expected:
        raise Core0Error("disassembly does not cover every four-byte function instruction")


def audit(*, root: Path, output_dir: Path, timeout_seconds: float = 60) -> dict:
    try:
        output_relative = output_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("kernel audit output must be an ignored build/kernel subdirectory") from error
    if not output_relative.parts:
        raise Core0Error("refusing to audit/write the whole build/kernel root")
    result_path = output_dir / "audit.json"
    invalidate_output_file(result_path, root)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": "audit timeout must be finite and positive", "commands": []})
        raise Core0Error("audit timeout must be finite and positive")
    tools = require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump", "llvm-objcopy"))
    logs = []

    def inspect(name: str, args: list[str], label: str) -> str:
        # require_tools resolves Nix's llvm-readelf symlink to llvm-readobj.
        # Set the GNU table format explicitly rather than relying on argv[0].
        actual = [tools[name], *(["--elf-output-style=GNU"] if name == "llvm-readelf" else []), *args]
        result = run_bounded(actual, cwd=output_dir, timeout_seconds=timeout_seconds)
        logs.append({"argv": actual, "returncode": result.returncode})
        text = (result.stdout + result.stderr).decode(errors="strict")
        (output_dir / ("audit-" + label + ".txt")).write_text(text)
        if result.returncode != 0:
            raise Core0Error(f"artifact inspection failed: {label}: {text}")
        return text

    try:
        build = _object(load_json(output_dir / "build.json"), "build report")
        provenance = _object(load_json(output_dir / "provenance.json"), "provenance")
        configuration = provenance.get("configuration")
        category = artifact_category(configuration)
        pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
        llvm_store = pin.get("tools", {}).get("llvm", {}).get("store_path")
        if pin.get("status") != "pinned" or not isinstance(llvm_store, str) or any(not path.startswith(llvm_store + "/") for path in tools.values()):
            raise Core0Error("artifact inspection tools differ from the immutable LLVM store output")
        realization = _object(provenance.get("lean_source_realization"), "Lean source realization")
        lean_pin = _object(pin.get("tools", {}).get("lean"), "locked Lean input")
        expected_realization = validate_lean_source_realization(
            lean_pin, str(realization.get("source_path")) + "\n",
            {str(realization.get("source_path")): {"narHash": realization.get("narHash"), "narSize": realization.get("narSize")}})
        uint_source = Path(expected_realization["source_path"]) / "src/Init/Data/UInt/Basic.lean"
        expected_realization.update(uint_source=str(uint_source), uint_source_sha256=LEAN_UINT_SOURCE_SHA256)
        if (realization != expected_realization or build.get("lean_source_realization") != realization
                or not uint_source.is_file() or sha256(uint_source) != LEAN_UINT_SOURCE_SHA256):
            raise Core0Error("realized Lean audit input is missing, stale or differs from its immutable source")
        if build.get("status") != "BUILT" or build.get("artifact_category") != category or build.get("configuration") != configuration or provenance.get("artifact_category") != category or build.get("provenance_sha256") != sha256(output_dir / "provenance.json"):
            raise Core0Error("build/provenance identity missing or stale")
        stage, optimization = provenance.get("stage"), provenance.get("optimization")
        if stage not in {"bootstrap-m", "supervisor"} or optimization not in OPT_PASSES or build.get("stage") != stage or build.get("optimization") != optimization:
            raise Core0Error("build execution stage/profile differs")
        validate_configuration_stage(configuration, stage)
        case, user_case = startup_case(configuration), user_startup_case(configuration)
        if build.get("startup_case") != case or provenance.get("startup_case") != case or build.get("user_startup_case") != user_case or provenance.get("user_startup_case") != user_case:
            raise Core0Error("build/provenance generated startup case differs")
        if provenance.get("generated_by_lean") != list(BOOT_FILES) or provenance.get("linked_inputs") != {"boot": list(BOOT_OBJECTS), "user": list(USER_OBJECTS)}:
            raise Core0Error("unexpected code-generation or linked-object closure")
        artifacts = _object(provenance.get("artifacts"), "artifact hashes")
        for name, digest in artifacts.items():
            path = output_dir / name
            if path.resolve().parent != output_dir.resolve() and output_dir.resolve() not in path.resolve().parents:
                raise Core0Error("artifact path escapes output")
            if not isinstance(digest, str) or not path.is_file() or sha256(path) != digest:
                raise Core0Error(f"missing/stale artifact: {name}")
        mandatory = set(BOOT_FILES) | set(BOOT_OBJECTS) | set(USER_OBJECTS) | {"image.elf", "user/image.elf", "image.map", "user/image.map", "user-text.bin", "user-data.bin", "platform.dtb", "platform.dts"}
        mandatory |= {role + "/" + name for role in ROLE_ROOTS for name in (*UNIT_FILES, "program.opt.ll")}
        if not mandatory <= set(artifacts):
            raise Core0Error("mandatory artifact hash inventory is incomplete")
        source_hashes = _object(provenance.get("source_inputs"), "source input hashes")
        if source_hashes != source_inputs(root):
            raise Core0Error("complete current compiler/production source hash inventory differs")
        for name, digest in source_hashes.items():
            path = root / name
            if not path.is_file() or sha256(path) != digest:
                raise Core0Error(f"current source differs from built input: {name}")
        for role, module in configuration_modules(configuration).items():
            closure = module_closure(root, module, allow_development=development_role(configuration, role))
            if any("/Development/" in path and path != module.replace(".", "/") + ".lean" for path in closure):
                raise Core0Error("dependency imports another configuration's development module")
            if closure != provenance.get("target_module_closures", {}).get(role):
                raise Core0Error("production import closure missing/stale")
        command_rows = _array(provenance.get("commands"), "build commands")
        if not command_rows or any(not isinstance(row, dict) or row.get("returncode") != 0 for row in command_rows):
            raise Core0Error("build command corpus empty, malformed or failed")
        nix_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                        and row["argv"] and Path(row["argv"][0]).name == "nix"]
        if nix_commands != [["build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION],
                            ["path-info", "--json", lean_pin["source_path"]]]:
            raise Core0Error("Lean source realization command evidence is missing or differs")
        compile_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                            and row["argv"] and Path(row["argv"][0]).name in {"llc", "opt", "ld.lld", "clang", "clang-20", "llvm-objcopy"}
                            and row["argv"][1:] != ["--version"]]
        expected_commands = []
        for _role in ROLE_ROOTS:
            expected_commands += [["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"],
                                  [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"]]
        expected_commands += [[*STARTUP_ARGUMENTS, "user-startup.S", "-o", "user/startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "user-link.ld", "-Map=user/image.map", *USER_OBJECTS, "-o", "user/image.elf"],
                              ["-O", "binary", "--only-section=.text", "user/image.elf", "user-text.bin"],
                              ["-O", "binary", "--only-section=.data", "user/image.elf", "user-data.bin"],
                              [*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"],
                              [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"]]
        if compile_commands != expected_commands:
            raise Core0Error("actual compiler/link command closure differs")
        for map_file, allowed in (("image.map", BOOT_OBJECTS), ("user/image.map", USER_OBJECTS)):
            objects = set(re.findall(r"([^\s()]+\.o)(?=[:(\s])", (output_dir / map_file).read_text()))
            if objects != set(allowed):
                raise Core0Error(f"actual linked input map differs: {map_file}: {sorted(objects)}")
        units = {role: validate_unit(load_json(output_dir / role / "unit.json"), role, configuration=configuration) for role in ROLE_ROOTS}
        layout = validate_layout(load_json(output_dir / "layout.json"), configuration=configuration)
        expected_machine = validate_catalog(load_json(output_dir / "primitive-catalog.json"), configuration=configuration, stage=stage)
        validate_platform_evidence(sha256(output_dir / "platform.dtb"), (output_dir / "platform.dts").read_text())
        ir = {role: {kind: validate_ir((output_dir / role / filename).read_text(), unit, optimized=kind == "optimized")
                     for kind, filename in (("pre", "program.ll"), ("optimized", "program.opt.ll"))} for role, unit in units.items()}
        task_stack = validate_owned_task_stack(layout, units["kernel"], (output_dir / "kernel/program.ll").read_text())
        object_functions = {
            "startup.o": expected_machine, "user/startup.o": {row["symbol"] for row in user_primitive_rows(user_case)}, "boot-package.o": set(),
            **{role + "/program.o": set(ir[role]["optimized"]["definitions"]) for role in ROLE_ROOTS},
        }
        allowed_relocations = {"R_RISCV_BRANCH", "R_RISCV_JAL", "R_RISCV_PCREL_HI20", "R_RISCV_PCREL_LO12_I", "R_RISCV_PCREL_LO12_S",
                               "R_RISCV_CALL", "R_RISCV_CALL_PLT", "R_RISCV_64", "R_RISCV_32", "R_RISCV_ADD64", "R_RISCV_SUB64"}
        readonly_objects = []
        user_abi_object = None
        for object_file, expected_functions in object_functions.items():
            label = object_file.replace("/", "-")
            object_symbols = inspect("llvm-readelf", ["-s", "--wide", object_file], label + "-symbols")
            if defined_function_symbols(object_symbols) != expected_functions:
                raise Core0Error(f"object executable source closure differs: {object_file}")
            relocs = relocation_types(inspect("llvm-readelf", ["-r", object_file], label + "-relocations"))
            if not relocs <= allowed_relocations:
                raise Core0Error(f"unknown/relaxed relocation in {object_file}: {sorted(relocs-allowed_relocations)}")
            sections = alloc_section_names(inspect("llvm-readelf", ["-S", "--wide", object_file], label + "-sections"))
            if object_file == "user/startup.o" and (".text.user_adversarial" in sections) != (user_case != "none"):
                raise Core0Error("user attack case/object section presence differs")
            allowed_sections = ({".boot_package"} if object_file == "boot-package.o" else
                                {".text", ".text.firmware", ".text.platform"} if object_file == "startup.o" else
                                {".text", ".text.user_start", ".text.user_boundary", ".data.user_abi"} | ({".text.user_adversarial"} if user_case != "none" else set()) if object_file == "user/startup.o" else
                                {".text", ".rodata", ".rodata.cst8", ".data", ".bss"})
            if object_file == "user/startup.o":
                if ".data.user_abi" not in sections:
                    raise Core0Error("user startup lacks its sole declared initialized-data section")
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.data.user_abi", object_file, "audit-user-abi-object.bin"], "user-abi-object-extract")
                user_abi_object = validate_user_abi_data(
                    (output_dir / ("audit-" + label + "-sections.txt")).read_text(),
                    (output_dir / "audit-user-abi-object.bin").read_bytes(), object_symbols,
                    (output_dir / "user-startup.S").read_text(), object_file=object_file)
            tables = ir["kernel"]["optimized"]["readonly_optimizer_tables"] if object_file == "kernel/program.o" else []
            if object_file == "kernel/program.o" and bool(tables) != (".rodata.cst32" in sections):
                raise Core0Error("kernel PMP IR table/object constant section presence differs")
            if ".rodata.cst32" in sections:
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.rodata.cst32", object_file, "audit-kernel-pmp-table.bin"], "pmp-table-extract")
                table_report = validate_pmp_constant_section(
                    (output_dir / ("audit-" + label + "-sections.txt")).read_text(),
                    (output_dir / "audit-kernel-pmp-table.bin").read_bytes(), object_file=object_file, tables=tables)
                table_report["sha256"] = sha256(output_dir / "audit-kernel-pmp-table.bin")
                readonly_objects.append(table_report)
                allowed_sections.add(".rodata.cst32")
            if ".rodata.cst8" in sections:
                section_text = (output_dir / ("audit-" + label + "-sections.txt")).read_text()
                constant = re.search(r"(?m)^\s*\[\s*\d+\]\s+\.rodata\.cst8\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)\s+08\s+AM\s+0\s+0\s+8\s*$", section_text)
                if not constant or int(constant[1], 16) == 0 or int(constant[1], 16) % 8:
                    raise Core0Error("integer constant pool has unexpected flags/entry size/alignment")
            # Clang may create an empty default .text section before selecting
            # the generated DATA-only package section. It must contain no bytes.
            if object_file == "boot-package.o" and ".text" in sections:
                section_text = (output_dir / ("audit-" + label + "-sections.txt")).read_text()
                match = re.search(r"\[\s*\d+\]\s+\.text\s+\S+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)", section_text)
                if not match or int(match[1], 16) != 0:
                    raise Core0Error("boot package object has executable text bytes")
                sections.remove(".text")
            if not sections <= allowed_sections or object_file == "boot-package.o" and sections != {".boot_package"}:
                raise Core0Error(f"unaccounted allocated object section in {object_file}: {sorted(sections)}")
        intervals = {row["name"]: row for row in layout["intervals"]}
        capacities = {"machine": intervals["firmware-private"]["limit"] - intervals["firmware-private"]["base"],
                      "boot": intervals["supervisor-stack"]["limit"] - layout["context"]["boot_stack_floor"],
                      "kernel-trap": layout["task_kernel_stack_bytes"], "user": layout["user"]["stack_pages"] * layout["frame_bytes"]}
        if capacities != {"machine": 65536, "boot": 61440, "kernel-trap": 8192, "user": 8192}:
            raise Core0Error("authoritative stack capacities differ")
        startup, user_startup = (output_dir / "startup.S").read_text(), (output_dir / "user-startup.S").read_text()
        for vector in ("lemma_machine_vector", "lemma_supervisor_vector"):
            if vector in expected_machine and machine_frame(startup, vector) != layout["context"]["bytes"]:
                raise Core0Error("typed vector stack allocation differs from the context layout")
        if machine_frame(user_startup, "_user_start") or machine_frame(user_startup, "lemma_exec_syscall"):
            raise Core0Error("user entry/syscall bridge consumes undeclared stack")
        stacks = {}
        for role, unit in units.items():
            object_file = role + "/program.o"
            frames = parse_stack_sizes(inspect("llvm-readelf", ["--stack-sizes", object_file], role + "-stack-sizes"))
            if set(frames) != object_functions[object_file]:
                raise Core0Error("stack metadata differs from the actual executable object closure")
            validate_compiled_stack(inspect("llvm-objdump", ["-d", "--no-show-raw-insn", object_file], role + "-stack-disassembly"), frames)
            primitive_source = user_startup if role == "user" else startup
            primitives = {row["primitive_symbol"]: machine_frame(primitive_source, row["primitive_symbol"])
                          for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
            if unit["used_device_ops"]:
                primitives["core0_io_fence"] = machine_frame(primitive_source, "core0_io_fence")
            undefined = {line.split()[-1] for line in inspect("llvm-nm", ["--undefined-only", object_file], role + "-stack-undefined").splitlines() if line.split()}
            if not undefined <= set(primitives):
                raise Core0Error(f"object has an unaccounted external stack/runtime symbol: {sorted(undefined - set(primitives))}")
            post_ir = (output_dir / role / "program.opt.ll").read_text()
            _definitions, _declarations, called = parse_definitions_and_calls(post_ir)
            for intrinsic in called & OPTIMIZER_INTRINSICS:
                primitives[intrinsic] = 0
            graph = weighted_stack_graph(post_ir, frames, primitives)
            graph.update(entries=validate_stack_entries(unit, graph, capacities=capacities, vector_bytes=288),
                         function_bytes=dict(sorted(frames.items())), object_undefined_symbols=sorted(undefined),
                         maximum_compiled_frame_bytes=max(frames.values()))
            stacks[role] = graph
        inspections = {}
        for name, image, expected, user in (("boot", "image.elf", expected_machine | {row["symbol"] for role in ("firmware", "kernel") for row in units[role]["functions"]}, False),
                                           ("user", "user/image.elf", {row["symbol"] for row in user_primitive_rows(user_case)} | {row["symbol"] for row in units["user"]["functions"]}, True)):
            header = inspect("llvm-readelf", ["-h", image], name + "-header")
            if not all(token in header for token in ("ELF64", "little endian", "RISC-V")) or not re.search(r"Flags:\s+0x0(?:\s|$)", header):
                raise Core0Error("ELF ISA/class/endianness/float/compressed flags differ")
            attributes = inspect("llvm-readelf", ["-A", image], name + "-attributes")
            arch = re.search(r"rv64i[0-9p]+(?:_[a-z0-9p]+)+", attributes)
            # LLVM 20 records Zmmul explicitly as the multiplication subset
            # already implied by M. It adds no instruction beyond RV64IM.
            if not arch or arch[0] != "rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0":
                raise Core0Error("ELF architecture attribute differs from integer-only profile")
            if inspect("llvm-nm", ["--undefined-only", image], name + "undefined").strip():
                raise Core0Error("final ELF contains undefined symbols")
            relocations = inspect("llvm-readelf", ["-r", image], name + "-relocations")
            if relocation_types(relocations):
                raise Core0Error("final ELF contains runtime relocations")
            symbol_text = inspect("llvm-readelf", ["-s", "--wide", image], name + "-symbols")
            symbols = defined_function_symbols(symbol_text)
            if symbols != expected:
                raise Core0Error(f"{name} executable symbol provenance differs: missing {sorted(expected-symbols)}; unexpected {sorted(symbols-expected)}")
            addresses = numeric_symbols(inspect("llvm-nm", ["--defined-only", image], name + "-addresses"))
            segments = parse_load_segments(inspect("llvm-readelf", ["-l", "--wide", image], name + "-segments"))
            intervals = [(row["base"], row["limit"]) for row in layout["intervals"]] if not user else [(0x10000, 0x1f000), (0x20000, 0x21000)]
            for segment in segments:
                begin, size = segment["virtual_address"], segment["memory_size"]
                if size == 0 or segment["file_size"] > size or "W" in segment["flags"] and "E" in segment["flags"] or not any(lo <= begin and begin + size <= hi for lo, hi in intervals):
                    raise Core0Error("ELF PT_LOAD permissions or declared range differs")
                if segment["physical_address"] != begin:
                    raise Core0Error("unexpected load address alias")
            entry_match = re.search(r"Entry point address:\s*(0x[0-9a-fA-F]+)", header)
            required_entry = 0x10000 if user else 0x80000000
            if not entry_match or int(entry_match[1], 16) != required_entry:
                raise Core0Error("ELF entry point differs")
            for symbol in symbols:
                privilege = "U" if user else ("M" if symbol.startswith("lemma_firmware_") or symbol in M_SYMBOLS else "S")
                low, high = ((0x10000, 0x1f000) if user else (0x80000000, 0x80010000) if privilege == "M" else (0x80200000, 0x80300000))
                if symbol not in addresses or not low <= addresses[symbol] < high:
                    raise Core0Error(f"{symbol} lies outside its source privilege range")
            machine = inspect("llvm-objdump", ["-d", "--no-show-raw-insn", image], name + "-disassembly")
            ranges = function_ranges(symbol_text)
            attack = None
            if user:
                raw_user_machine = inspect("llvm-objdump", ["-d", image], "user-raw-disassembly")
                attack = validate_user_attack_machine(raw_user_machine, ranges, (output_dir / "user-startup.S").read_text(), user_case)
            validate_machine(machine, user=user, ranges=ranges, user_csr_pc=attack["base"] if user and user_case == "supervisor-csr" else None)
            inspections[name] = {"entry": required_entry, "segments": segments, "function_symbols": sorted(symbols),
                                 "function_ranges": {symbol: {"base": address, "bytes": size} for symbol, (address, size) in ranges.items()}}
            if not user:
                inspections[name]["startup"] = validate_startup_case(machine, ranges, case)
                raw_machine = inspect("llvm-objdump", ["-d", image], "boot-raw-disassembly")
                inspections[name]["context_abi"] = validate_context_abi(
                    (output_dir / "startup.S").read_text(), raw_machine, ranges,
                    (output_dir / "user-startup.S").read_text(), units["user"]["roots"][0]["symbol"], user_case)
            else:
                initialized_data = validate_user_abi_data(
                    inspect("llvm-readelf", ["-S", "--wide", image], "user-sections"),
                    (output_dir / "user-data.bin").read_bytes(), symbol_text,
                    (output_dir / "user-startup.S").read_text(), object_file=image)
                if user_abi_object is None or initialized_data["sha256"] != user_abi_object["sha256"]:
                    raise Core0Error("linked user initializer differs from its accounted startup object")
                inspections[name]["initialized_data"] = initialized_data
                begin, size = ranges["_user_start"]
                exit_pcs = [int(match[1], 16) for line in machine.splitlines()
                            if (match := re.match(r"\s*([0-9a-f]+):\s+ecall\s*$", line)) and begin <= int(match[1], 16) < begin + size]
                if len(exit_pcs) != 1:
                    raise Core0Error("user startup lacks its exact single exit ECALL")
                inspections[name]["exit_ecall_pc"] = exit_pcs[0]
                inspections[name]["syscall_bridge"] = validate_user_syscall_bridge(
                    (output_dir / "user-startup.S").read_text(), raw_user_machine, ranges)
                inspections[name]["quarantined_startup"] = attack
        package_contract = _object(load_json(output_dir / "package-contract.json"), "package contract")
        if package_contract != {"schema_version": 1, "configuration": configuration, "startup_case": case, "user_startup_case": user_case, "contract_version": "lemma-boot-package-v1", "magic": 0x31474b50414d454c,
                                "version": 1, "image_count": 1, "header_bytes": 32, "descriptor_bytes": 96,
                                "image": {"id": 1, "entry": 0x10000, "text_va": 0x10000, "text_capacity": 0xf000,
                                          "data_va": 0x20000, "data_mem_bytes": 4096, "stack_va": 0x3fffc000, "stack_pages": 2, "flags": 0},
                                "offset_encoding": "generated-label-differences"}:
            raise Core0Error("unknown/malformed boot package descriptor contract")
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=.boot_package", "image.elf", "audit-package.bin"], "package-extract")
        package = (output_dir / "audit-package.bin").read_bytes()
        if len(package) < 128:
            raise Core0Error("boot package is missing header/descriptor")
        header = struct.unpack_from("<4Q", package)
        descriptor = struct.unpack_from("<12Q", package, 32)
        text, data = (output_dir / "user-text.bin").read_bytes(), (output_dir / "user-data.bin").read_bytes()
        image_id, entry, text_va, text_offset, text_bytes, data_va, data_offset, data_bytes, data_memory, stack_va, stack_pages, flags = descriptor
        if (header != (0x31474b50414d454c, 1, 1, len(package)) or image_id != 1 or entry != 0x10000 or text_va != 0x10000
                or data_va != 0x20000 or data_memory != 4096 or stack_va != 0x3fffc000 or stack_pages != 2 or flags != 0
                or text_offset < 128 or text_bytes != len(text) or data_bytes != len(data) or data_offset < text_offset + text_bytes
                or data_offset + data_bytes > len(package) or package[text_offset:text_offset+text_bytes] != text
                or package[data_offset:data_offset+data_bytes] != data):
            raise Core0Error("package descriptor/raw user image binding differs")
        record = {"schema_version": 1, "status": "PASS", "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                  "stage": stage, "optimization": optimization, "source_commit": provenance["source_commit"],
                  "dirty_paths": provenance["dirty_paths"], "image_sha256": sha256(output_dir / "image.elf"),
                  "lean_source_realization": realization,
                  "user_image_sha256": sha256(output_dir / "user/image.elf"), "boot_package_sha256": sha256(output_dir / "audit-package.bin"),
                  "unit_ir": ir, "readonly_optimizer_object_sections": readonly_objects, "elf": inspections, "commands": logs,
                  "stack_bounds": {"capacities": capacities, "roles": stacks, "dynamic_stack": False},
                  "task_kernel_stack": task_stack,
                  "limitations": ["Artifact/source closure audit, not S/U execution or compiler-correctness proof.",
                                   ("bootstrap-m invokes maintained kernel code in M mode; separately linked user bytes are not yet a running task."
                                    if stage == "bootstrap-m" else "Supervisor artifact audit does not establish a running isolated user task.")]}
        write_json(result_path, record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": str(error), "commands": logs})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    ns = parser.parse_args()
    root = repo_root()
    try:
        record = audit(root=root, output_dir=(root / ns.output_dir).resolve(), timeout_seconds=ns.timeout)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"KERNEL AUDIT FAIL: {error}", file=sys.stderr)
        return 1
    print(f"KERNEL AUDIT PASS: {record['stage']}, {record['optimization']}; source {record['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
