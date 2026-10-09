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
                         validate_loop_stack_call_graph, _ir_definition_body, _structured_ir_blocks, _structured_successors, _structured_reachable)
from build_core0 import LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS, invalidate_output_file
from build_kernel import (BOOT_FILES, BOOT_OBJECTS, CONTRACTS, ROLE_MODULES, ROLE_ROOTS,
                          UNIT_FILES, USER_OBJECTS, artifact_category, configuration_modules,
                          configuration_roots, development_role, module_closure, source_inputs, startup_case, user_startup_case,
                          configuration_development_modules,
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
TASK_USER_IMAGES = tuple({"key": key, "id": index, "module": "Lemma.User.Development.Tasks." + module,
                          "source": "Lemma.User.Development.Tasks." + module + ".main", "args": ["u64"],
                          "symbol_prefix": "lemma_user_" + key + "_", "startup_case": "none",
                          "directory": "users/" + key}
                         for index, (key, module) in enumerate((("compute", "Compute"), ("sleeper", "Sleeper"), ("busy", "Busy")), 1))
TASK_FAULT_USER_IMAGES = (*TASK_USER_IMAGES, {
    "key": "fault", "id": 4, "module": "Lemma.User.Development.Tasks.Fault",
    "source": "Lemma.User.Development.Tasks.Fault.main", "args": ["u64"],
    "symbol_prefix": "lemma_user_fault_", "startup_case": "supervisor-csr", "directory": "users/fault"})
MANAGED_POLICY = "lemma-capabilities-v1"
CAPABILITY_USER_IMAGES = tuple({"key": key, "id": index, "module": module, "source": module + ".main", "args": ["u64"],
                               "symbol_prefix": "lemma_user_" + key + "_", "startup_case": "none", "directory": "users/" + key,
                               "boot_role": key}
                              for index, (key, module) in enumerate((("capabilities", "Lemma.User.Development.Capabilities"),
                                  ("peer", "Lemma.User.Development.CapabilitiesPeer"), ("busy", "Lemma.User.Development.Tasks.Busy"),
                                  ("tamper", "Lemma.User.Development.CapabilitiesTamper")), 1))
MULTI_USER_CONFIGURATIONS = {"tasks-development": TASK_USER_IMAGES, "tasks-fault-development": TASK_FAULT_USER_IMAGES,
                             "capabilities-development": CAPABILITY_USER_IMAGES}


def managed_fields(configuration: str, image: dict | None = None) -> dict:
    if configuration != "capabilities-development":
        return {}
    return {"managed_policy": MANAGED_POLICY, **({"boot_role": image["boot_role"]} if image is not None else {})}


def validate_managed_provenance(build: dict, provenance: dict, *, configuration: str, images: list[dict]) -> None:
    if configuration == "capabilities-development":
        expected = {"managed_policy": MANAGED_POLICY, "boot_roles": {row["key"]: row["boot_role"] for row in CAPABILITY_USER_IMAGES}}
        if (images != list(CAPABILITY_USER_IMAGES) or any("boot_role" in record for record in (build, provenance))
                or any(record.get(key) != value for record in (build, provenance) for key, value in expected.items())):
            raise Core0Error("managed policy/boot roles differ from the closed source-selected deployment")
    elif any(key in record for record in (build, provenance) for key in ("managed_policy", "boot_roles", "boot_role")):
        raise Core0Error("managed authority metadata appears outside its closed deployment")


def validate_standalone_managed_provenance(build: dict, provenance: dict, *, configuration: str, image: dict) -> None:
    expected=managed_fields(configuration,image)
    if configuration == "capabilities-development":
        if any("boot_roles" in record or any(record.get(key)!=value for key,value in expected.items()) for record in (build,provenance)):
            raise Core0Error("independent managed policy/boot role differs from its selected source")
    elif any(key in record for record in (build,provenance) for key in ("managed_policy","boot_role","boot_roles")):
        raise Core0Error("independent managed authority metadata appears outside its selected deployment")


def image_specs(configuration: str) -> tuple[dict, ...]:
    if not isinstance(configuration, str) or configuration not in MULTI_USER_CONFIGURATIONS:
        raise Core0Error("unknown closed multi-image configuration")
    return MULTI_USER_CONFIGURATIONS[configuration]


def image_spec(configuration: str, image_key: str) -> dict:
    matches = [row for row in image_specs(configuration) if row["key"] == image_key]
    if len(matches) != 1:
        raise Core0Error("unknown selected user image")
    return matches[0]


def development_modules(configuration: str, role: str) -> tuple[str, ...]:
    expected = (("Lemma.Kernel.Development.FaultEntry", "Lemma.Kernel.Development.TasksEntry", "Lemma.Kernel.Development.Pressure")
                if (configuration, role) == ("tasks-fault-development", "kernel") else
                ("Lemma.Kernel.Development.CapsEntry", "Lemma.Kernel.Development.CapAlias", "Lemma.Kernel.Development.TasksEntry",
                 "Lemma.Kernel.Development.CapabilityGeneration")
                if (configuration, role) == ("capabilities-development", "kernel") else
                (configuration_modules(configuration)[role],) if development_role(configuration, role) else ())
    if configuration_development_modules(configuration, role) != expected:
        raise Core0Error("selected role Development authority differs from its exact audited module catalog")
    return expected


def validate_image_case_provenance(build: dict, provenance: dict, *, configuration: str, images: list[dict]) -> None:
    if configuration == "tasks-fault-development":
        expected = {row["key"]: row["startup_case"] for row in image_specs(configuration)}
        if (images != list(image_specs(configuration)) or build.get("user_startup_cases") != expected
                or provenance.get("user_startup_cases") != expected):
            raise Core0Error("mixed-image startup cases are missing or differ from the closed registry")
    elif "user_startup_cases" in build or "user_startup_cases" in provenance:
        raise Core0Error("per-image mixed startup metadata appears outside its selected configuration")


def validate_user_image_catalog(value: object, *, configuration: str | None = None) -> dict:
    """Admit only the ordered Lean deployment catalog for the selected gate."""
    catalog = _object(value, "user image catalog")
    selected = catalog.get("configuration") if configuration is None else configuration
    images = image_specs(selected)
    expected = {"schema_version": 1, "contract_version": "lemma-user-image-catalog-v1",
                "configuration": selected, "stage": "supervisor", "image_count": len(images),
                "images": list(images), **managed_fields(selected)}
    # Exact equality also closes paths, IDs, per-image prefixes and source roots.
    if (type(catalog.get("schema_version")) is not int or type(catalog.get("image_count")) is not int
            or catalog != expected or any(type(row.get("id")) is not int for row in catalog.get("images", []))):
        raise Core0Error("closed user image registry/source/path catalog differs")
    return catalog


def selected_user_image(catalog: object, image_key: str) -> dict:
    catalog = validate_user_image_catalog(catalog)
    matches = [row for row in catalog["images"] if row["key"] == image_key]
    if len(matches) != 1:
        raise Core0Error("unknown selected user image")
    return matches[0]


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
                "Lemma.Kernel.Loader.releaseStackHandle", "Lemma.Kernel.Loader.teardown",
                "Lemma.Kernel.Process.validateFrame", "Lemma.Kernel.Process.validateStack",
                "Lemma.Kernel.Loader.kernelStackHandleOffset", "Lemma.Kernel.Loader.kernelStackSecondHandleOffset"}
    task_dispatch = {"tasks-development": "Lemma.Kernel.Development.TasksEntry.dispatch",
                     "tasks-fault-development": "Lemma.Kernel.Development.FaultEntry.dispatch",
                     "capabilities-development": "Lemma.Kernel.Development.CapsEntry.dispatch"}
    dispatch_edges = ({task_dispatch[unit["configuration"]]: ["Lemma.Kernel.Scheduler.dispatch"],
                       "Lemma.Kernel.Scheduler.dispatch": ["Lemma.Kernel.Task.capture"],
                       "Lemma.Kernel.Task.capture": ["Lemma.Kernel.Process.validateFrame"],
                       "Lemma.Kernel.Task.context": ["Lemma.Kernel.Process.validateStack"]}
                      if unit.get("configuration") in task_dispatch else
                      {"Lemma.Kernel.Process.dispatch": ["Lemma.Kernel.Process.validateFrame"]})
    required.update(dispatch_edges)
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
        "Lemma.Kernel.Process.validateFrame": ["Lemma.Kernel.Process.validateStack"],
        "Lemma.Kernel.Process.validateStack": ["Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue"],
        **dispatch_edges,
    }.items():
        calls = parse_definitions_and_calls(_ir_definition_body(pre_ir, by_source[caller]))[2]
        if not {by_source[callee] for callee in callees} <= calls:
            raise Core0Error("owned task-stack source call chain omits pair construction or validation")
    return {"pages": layout["task_kernel_stack_pages"], "bytes": layout["task_kernel_stack_bytes"],
            "construction": "owned-physically-contiguous-pair", "first_handle_offset": 2400, "second_handle_offset": 2480,
            "base_owned_task_frames": 15 + layout["task_kernel_stack_pages"],
            "source_functions": {source: by_source[source] for source in sorted(required)}}


def validate_call_precedes(body: str, before: str, after: str) -> dict:
    """Every reachable protected call must follow a particular emitted call.

    This checks the genuine pre-optimization CFG, including alternate paths and
    same-block instruction order. It does not infer successful return status.
    """
    blocks = _structured_ir_blocks(body)
    successors = _structured_successors(blocks)
    if "entry" not in blocks:
        raise Core0Error("ordered source call audit lacks the exact entry block")
    before_pattern = re.compile(r"\bcall\s+[^@\n]*@" + re.escape(before) + r"\(")
    after_pattern = re.compile(r"\bcall\s+[^@\n]*@" + re.escape(after) + r"\(")
    pending, seen, protected = [("entry", False)], set(), set()
    while pending:
        block, observed = pending.pop()
        if (block, observed) in seen:
            continue
        seen.add((block, observed))
        for index, line in enumerate(blocks[block]):
            if after_pattern.search(line):
                if not observed:
                    raise Core0Error("protected source call has a path before required checked lifecycle call")
                protected.add((block, index))
            if before_pattern.search(line):
                observed = True
        pending.extend((target, observed) for target in successors[block])
    if not protected:
        raise Core0Error("ordered source call audit found no reachable protected call")
    return {"before": before, "after": after, "protected_sites": [list(site) for site in sorted(protected)]}


def validate_checked_call_gate(body: str, checked: str, protected: str, *, component: str = "status", value: int = 0) -> dict:
    """Require an exact checked-result comparison before every protected call.

    The failed comparison branch must not reach the protected operation, and
    removing the successful edge must make every protected site unreachable.
    Only the structured aggregate ABI and literal equality are admitted.
    """
    if component not in {"status", "value"} or type(value) is not int:
        raise Core0Error("unknown checked source gate component/value")
    blocks = _structured_ir_blocks(body)
    successors = _structured_successors(blocks)
    checked_calls = re.findall(r"(%[A-Za-z0-9_.$-]+) = call \{ i64, i64 \} @" + re.escape(checked) + r"\([^\n]*\)", body)
    protected_blocks = {block for block, lines in blocks.items()
                        if any(re.search(r"\bcall\s+[^@\n]*@" + re.escape(protected) + r"\(", line) for line in lines)}
    if not checked_calls or not protected_blocks or "entry" not in blocks:
        raise Core0Error("checked source gate lacks genuine calls/entry")
    gates=[]
    for result in checked_calls:
        extracted = re.findall(r"(%[A-Za-z0-9_.$-]+) = extractvalue \{ i64, i64 \} " + re.escape(result)
                               + r", " + ("0" if component == "status" else "1") + r"$", body, re.M)
        if len(extracted) != 1:
            raise Core0Error("checked source gate lacks its exact aggregate extraction")
        operand=extracted[0];width="i64"
        if component == "status":
            narrowed=re.findall(r"(%[A-Za-z0-9_.$-]+) = trunc i64 " + re.escape(operand) + r" to i8$",body,re.M)
            if len(narrowed)!=1:
                raise Core0Error("checked source gate lacks its exact status narrowing")
            operand=narrowed[0];width="i8"
        comparisons=re.findall(r"(%[A-Za-z0-9_.$-]+) = icmp eq " + width + " " + re.escape(operand) + ", " + str(value) + r"$",body,re.M)
        for comparison in comparisons:
            for block, lines in blocks.items():
                if re.fullmatch(r"br i1 " + re.escape(comparison) + r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1]):
                    success,failure=successors[block]
                    reachable={site for site in protected_blocks if _structured_reachable(successors,success,site)}
                    if any(_structured_reachable(successors,failure,site) for site in protected_blocks):
                        raise Core0Error("failed checked source gate can reach protected operation")
                    removed={label:tuple(target for target in targets if (label,target)!=(block,success)) for label,targets in successors.items()}
                    dominated={site for site in reachable if not _structured_reachable(removed,"entry",site)}
                    gates.append({"block":block,"success":success,"failure":failure,"protected_blocks":sorted(dominated)})
    if not protected_blocks <= {site for gate in gates for site in gate["protected_blocks"]}:
        raise Core0Error("protected operation lacks an exact successful checked-result gate")
    validate_call_precedes(body,checked,protected)
    return {"checked":checked,"protected":protected,"component":component,"equals":value,"gates":gates}



def validate_boolean_gate(body: str, comparison: str, protected: str, *, success_when_true: bool = True) -> dict:
    """Require the true edge of one emitted predicate before protected calls."""
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    if "entry" not in blocks:
        raise Core0Error("boolean source gate lacks its exact entry block")
    branches=[block for block,lines in blocks.items() if re.fullmatch(
        r"br i1 "+re.escape(comparison)+r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1])]
    sites={block for block,lines in blocks.items() if any(re.search(
        r"\bcall\s+[^@\n]*@"+re.escape(protected)+r"\(",line) for line in lines)}
    if len(branches)!=1 or not sites:
        raise Core0Error("boolean source gate lacks one branch/protected operation")
    block=branches[0];success,failure=successors[block]
    if not success_when_true:
        success,failure=failure,success
    removed={label:tuple(target for target in targets if (label,target)!=(block,success))
             for label,targets in successors.items()}
    if any(_structured_reachable(successors,failure,site) or
           _structured_reachable(removed,"entry",site) or
           not _structured_reachable(successors,success,site) for site in sites):
        raise Core0Error("protected operation bypasses the exact successful boolean gate")
    return {"comparison":comparison,"success_when_true":success_when_true,"block":block,"success":success,"failure":failure,"protected_blocks":sorted(sites)}



def validate_h_endpoint_budget(body: str, by_source: dict[str,str]) -> dict:
    """Bind the compiled bounded count/limit to preallocation CFG guards."""
    objects="Lemma.Kernel.Objects.";var=r"%[A-Za-z0-9_.$-]+";label=r"[A-Za-z0-9_.$-]+"
    callback=by_source[objects+"endpointCountStep"]
    folds=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(callback)+
        r"\(i32 signext ("+var+r"), i32 signext 16, i64 ("+var+r"), i64 ("+var+r"), i64 0, i64 0, i64 0\)",body)
    if len(folds)!=1:
        raise Core0Error("endpoint budget lacks one exact 16-row count callback")
    result,index,accumulator,base=folds[0]
    values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 1$",body,re.M)
    statuses=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 0$",body,re.M)
    if len(values)!=1 or len(statuses)!=1:
        raise Core0Error("endpoint count callback lacks checked status/value extraction")
    narrowed=re.findall(r"("+var+r") = trunc i64 "+re.escape(statuses[0])+r" to i8$",body,re.M)
    if len(narrowed)!=1:
        raise Core0Error("endpoint count callback lacks UInt8 status")
    headers=re.findall(re.escape(index)+r" = phi i32 \[ 0, %("+label+r") \], \[ ("+var+r"), %("+label+r") \]",body)
    if len(headers)!=1:
        raise Core0Error("endpoint count index lacks exact zero-based bounded loop")
    preheader,next_index,latch=headers[0]
    if (re.search(re.escape(accumulator)+r" = phi i64 \[ 0, %"+re.escape(preheader)+r" \], \[ "+re.escape(values[0])+r", %"+re.escape(latch)+r" \]",body) is None
        or re.search(re.escape(next_index)+r" = add i32 "+re.escape(index)+r", 1$",body,re.M) is None
        or re.search(r"icmp ult i32 "+re.escape(index)+r", 16$",body,re.M) is None):
        raise Core0Error("endpoint count accumulator/increment/bound differs")
    outcomes=re.findall(r"("+var+r") = phi i64 \[ 0, %("+label+r") \], \[ "+re.escape(values[0])+r", %("+label+r") \], \[ "+re.escape(accumulator)+r", %("+label+r") \]",body)
    if len(outcomes)!=1:
        raise Core0Error("endpoint count lacks exact checked fold outcome")
    value,exhausted,stopped,done=outcomes[0]
    outcome_status=re.findall(r"("+var+r") = phi i8 \[ 9, %"+re.escape(exhausted)+r" \], \[ "+re.escape(narrowed[0])+r", %"+re.escape(stopped)+r" \], \[ 0, %"+re.escape(done)+r" \]",body)
    limits=re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[objects+"endpointCapacity"])+r"\(\)",body)
    comparisons=[]
    for limit in limits:
        comparisons.extend(re.findall(r"("+var+r") = icmp ult i64 "+re.escape(value)+r", "+re.escape(limit)+r"$",body,re.M))
    if len(outcome_status)!=1 or len(comparisons)!=1:
        raise Core0Error("endpoint preallocation guard differs from count < exact capacity")
    failed=re.findall(r"("+var+r") = call zeroext i1 @"+re.escape(by_source[objects+"failed"])+r"\(i8 zeroext "+re.escape(outcome_status[0])+r"\)",body)
    status_comparisons=[]
    for status in failed:
        status_comparisons.extend(re.findall(r"("+var+r") = icmp eq i1 "+re.escape(status)+r", 1$",body,re.M))
    if len(status_comparisons)!=1:
        raise Core0Error("endpoint budget lacks the exact checked fold-status guard")
    gates=[]
    for protected in [objects+"freeObjectStep","Lemma.Kernel.Memory.Frames.allocate"]:
        gates.append({"protected_source":protected,"limit":validate_boolean_gate(body,comparisons[0],by_source[protected]),
                      "status":validate_boolean_gate(body,status_comparisons[0],by_source[protected],success_when_true=False)})
    return {"capacity":4,"counted_rows":16,"counter_source":objects+"endpointCountStep","base_operand":base,
            "count_result":value,"checked_outcome_status":outcome_status[0],"preallocation_gates":gates}


def validate_h_alias(unit: dict, pre_ir: str, by_source: dict[str,str]) -> dict:
    prefix="Lemma.Kernel.Development.CapAlias."
    address="Lemma.Kernel.Memory.AddressSpace."
    access="Lemma.Kernel.Memory.Access."
    body=_ir_definition_body(pre_ir,by_source[prefix+"install"])
    var=r"%[A-Za-z0-9_.$-]+"
    base_calls=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[address+"base"])+r"\(i64 %arg0\)",body)
    if len(base_calls)!=1:
        raise Core0Error("H descriptor alias lacks one checked descriptor-derived base")
    base_values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(base_calls[0])+r", 1$",body,re.M)
    if len(base_values)!=1:
        raise Core0Error("H descriptor alias lacks exact base result extraction")
    base=base_values[0]
    table_calls=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[prefix+"checkedTable"])+r"\(i64 "+re.escape(base)+r", i64 ("+var+r"), i64 ([0-9]+)\)",body)
    if [int(row[2]) for row in table_calls]!=[0,7,8] or len({row[1] for row in table_calls})!=1:
        raise Core0Error("H alias table geometry/checked ownership differs")
    low_values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(table_calls[-1][0])+r", 1$",body,re.M)
    alias_values=re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[prefix+"aliasPage"])+r"\(\)",body)
    slots=[]
    for low in low_values:
        for page in alias_values:
            slots.extend(re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[address+"tableSlot"])+r"\(i64 "+re.escape(low)+r", i64 "+re.escape(page)+r"\)",body))
    writes=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[access+"write64"])+r"\(i64 ("+var+r"), i64 ("+var+r")\)",body)
    if len(writes)!=1 or writes[0][1] not in slots:
        raise Core0Error("H descriptor alias does not publish one exact owned low-table slot")
    ptes=[]
    for count,right in re.findall(r"("+var+r") = and i64 12, 63\n\s*("+var+r") = lshr i64 "+re.escape(base)+r", \1",body):
        for shift,left in re.findall(r"("+var+r") = and i64 10, 63\n\s*("+var+r") = shl i64 "+re.escape(right)+r", \1",body):
            ptes.extend(re.findall(r"("+var+r") = or i64 "+re.escape(left)+r", 199$",body,re.M))
    if writes[0][2] not in ptes or len(ptes)!=2:
        raise Core0Error("H descriptor alias PTE is not descriptorPPN plus exact S RW/NX/U0 flags")
    readbacks=[]
    for slot in slots:
        readbacks.extend(re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[access+"read64"])+r"\(i64 "+re.escape(slot)+r"\)",body))
    verified=[]
    for result in readbacks:
        for loaded in re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 1$",body,re.M):
            for pte in ptes:
                verified.extend(re.findall(r"("+var+r") = icmp eq i64 "+re.escape(loaded)+r", "+re.escape(pte)+r"$",body,re.M))
    if len(verified)!=1:
        raise Core0Error("H descriptor alias lacks one exact PTE readback comparison")
    readback_gate=validate_boolean_gate(body,verified[0],by_source[address+"flushCurrent"])
    for before in ("Lemma.Kernel.Task.prepared",address+"base",prefix+"checkedHeader",prefix+"checkedTable"):
        validate_call_precedes(body,by_source[before],by_source[access+"write64"])
    validate_call_precedes(body,by_source[access+"write64"],by_source[address+"flushCurrent"])
    return {"source":prefix+"install","symbol":by_source[prefix+"install"],"virtual_page":0x31000,"attack_va":0x31a00,
            "descriptor_header_offset":2560,"table_indices":[0,7,8],"pte_flags":199,"user_access":False,
            "writes":1,"descriptor_base_extraction":base,"pte_value":writes[0][2],"readback_comparisons":verified,"readback_gate":readback_gate}


def validate_h_legacy_console_denial(body: str, by_source: dict[str,str]) -> dict:
    console=by_source["Lemma.User.ABI.console"];legacy=by_source["Lemma.Kernel.Syscall.dispatchLegacy"]
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    values=re.findall(r"(%[A-Za-z0-9_.$-]+) = call i64 @"+re.escape(console)+r"\(\)",body)
    if len(values)!=1:
        raise Core0Error("managed dispatch lacks its exact legacy console selector")
    comparisons=re.findall(r"(%[A-Za-z0-9_.$-]+) = icmp eq i64 %arg1, "+re.escape(values[0])+r"$",body,re.M)
    if len(comparisons)!=1:
        raise Core0Error("managed legacy-console guard differs")
    branches=[block for block,lines in blocks.items() if re.fullmatch(r"br i1 "+re.escape(comparisons[0])+r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1])]
    if len(branches)!=1:
        raise Core0Error("managed legacy-console guard lacks exact successors")
    denied,ordinary=successors[branches[0]]
    protected={block for block,lines in blocks.items() if any("@"+legacy+"(" in line for line in lines)}
    if any(_structured_reachable(successors,denied,block) for block in protected) or len(blocks[denied])!=1 or len(successors[denied])!=1:
        raise Core0Error("managed console number2 can bypass capability lookup through legacy dispatch")
    merge=blocks[successors[denied][0]]
    if not any(re.search(r"phi i8 .*\[ 72, %"+re.escape(denied)+r" \]",line) for line in merge):
        raise Core0Error("managed legacy console does not return exact permission denial72")
    return {"legacy_console_number":2,"denied_status":72,"guard_block":branches[0],"denied_block":denied,"ordinary_block":ordinary}


def validate_managed_capability_graph(unit: dict, pre_ir: str) -> dict:
    """Bind H labels to actual compiled enrollment, gates and teardown paths.

    These are artifact/source constraints, not a proof of capability semantics.
    Target execution and the independent state model supply separate evidence.
    """
    if unit.get("configuration") != "capabilities-development" or unit.get("role") != "kernel":
        raise Core0Error("managed lifecycle audit requires the exact H kernel unit")
    by_source={}
    for row in unit["functions"]:
        source=re.sub(r"^_private\..*?\.[0-9]+\.","",row["source"])
        if source in by_source:
            raise Core0Error("managed lifecycle source identity is ambiguous after private authorization")
        by_source[source]=row["symbol"]
    caps="Lemma.Kernel.Capability."
    objects="Lemma.Kernel.Objects."
    task="Lemma.Kernel.Task."
    syscalls="Lemma.Kernel.Syscall."
    entry="Lemma.Kernel.Development.CapsEntry."
    alias="Lemma.Kernel.Development.CapAlias."
    generation="Lemma.Kernel.Development.CapabilityGeneration."
    address="Lemma.Kernel.Memory.AddressSpace."
    frames="Lemma.Kernel.Memory.Frames."
    userabi="Lemma.User.CapabilityABI."
    edges={
        entry+"boot":[objects+"init",task+"init",entry+"launch"],
        entry+"launch":[task+"prepareManaged",entry+"configure"],
        entry+"configure":[objects+"configureManagement",entry+"seedEndpoint",objects+"createEndpoint",entry+"initialGrants",task+"activateManaged"],
        entry+"seedEndpoint":[generation+"seedOneFree",generation+"seedResult"],
        entry+"initialGrants":[entry+"grant"],
        entry+"grant":[caps+"grantBoot"],
        entry+"createTamper":[task+"prepareManaged",entry+"grant",alias+"install",task+"activateManaged"],
        entry+"command":[entry+"createTamper",generation+"advance","Lemma.Kernel.Development.TasksEntry.command"],
        task+"prepareManaged":[task+"prepare",caps+"attach",task+"abort",task+"prepared"],
        task+"activateManaged":[task+"prepared",caps+"activate",task+"activate"],
        task+"activate":[task+"prepared",task+"checkedActivation"],
        task+"checkedActivation":[caps+"managed",caps+"requireActive"],
        task+"abort":[task+"inactiveDescriptor",task+"detachManaged","Lemma.Kernel.Loader.teardown"],
        task+"reapOne":[task+"detachManaged","Lemma.Kernel.Loader.teardown"],
        task+"detachManaged":[caps+"detach"],
        caps+"attach":[address+"base",objects+"register"],
        caps+"header":[address+"base",objects+"registryDescriptor"],
        caps+"managed":[address+"base",caps+"header",caps+"zeroHeaderStep"],
        caps+"requireActive":[caps+"header"],
        caps+"lookupEntry":[caps+"requireActive",objects+"resolve"],
        caps+"lookup":[caps+"lookupEntry",objects+"resolve",userabi+"rightsSubset"],
        caps+"grantBoot":[caps+"header",caps+"grant"],
        caps+"grant":[objects+"resolve",userabi+"rightsValid",caps+"freeSlot",objects+"nextSerial",caps+"publish"],
        caps+"freeSlot":[caps+"header",caps+"entryCount"],
        caps+"publish":[caps+"header",objects+"reference",objects+"publishSerial"],
        caps+"duplicate":[caps+"lookupEntry",userabi+"rightsSubset",caps+"grant"],
        caps+"transfer":[caps+"management",caps+"requireActive",caps+"lookupEntry",userabi+"rightsSubset",caps+"grant"],
        caps+"management":[caps+"lookup",objects+"resolve"],
        caps+"createEndpoint":[caps+"management",caps+"freeSlot",objects+"nextSerial",objects+"createEndpoint",caps+"publish"],
        caps+"close":[caps+"lookupEntry",caps+"requireActive",caps+"drop"],
        caps+"drop":[caps+"clearEntryStep",objects+"dereference"],
        caps+"revoke":[caps+"lookup",caps+"revokeKey"],
        caps+"revokeKey":[objects+"beginRevoke",caps+"revokeTaskStep",objects+"destroy"],
        caps+"revokeTaskStep":[objects+"registryDescriptor",caps+"header",caps+"revokeEntryStep"],
        caps+"revokeEntryStep":[caps+"drop"],
        caps+"detach":[address+"base",caps+"header",objects+"table",caps+"ownedObjectStep",caps+"detachEntryStep",objects+"clearManagement",objects+"unregister",caps+"clearHeaderStep"],
        caps+"ownedObjectStep":[caps+"revokeKey"],
        caps+"detachEntryStep":[caps+"drop"],
        objects+"init":[frames+"allocate",frames+"resolvePurpose",objects+"initStep"],
        objects+"table":[frames+"resolvePurpose",frames+"mappingCount"],
        objects+"resolve":[objects+"resolveState"],
        objects+"resolveState":[objects+"table",objects+"keyValid"],
        objects+"reference":[objects+"resolve"],
        objects+"dereference":[objects+"resolveRevoking",objects+"destroy"],
        objects+"destroy":[objects+"resolveRevoking",frames+"resolvePurpose",frames+"mappingCount",frames+"release"],
        objects+"createEndpoint":[address+"base",objects+"endpointCountStep",objects+"endpointCapacity",objects+"freeObjectStep",objects+"failed",frames+"allocate"],
        objects+"endpointCountStep":[objects+"get",objects+"live",objects+"revoking",userabi+"typeValid",userabi+"endpointType"],
        syscalls+"dispatch":[caps+"managed",syscalls+"dispatchManaged",syscalls+"dispatchLegacy"],
        syscalls+"dispatchManaged":[caps+"bootGrant",caps+"info",caps+"check",caps+"duplicate",caps+"close",caps+"revoke",syscalls+"capConsole",caps+"createEndpoint",caps+"transfer",caps+"scopedTarget",caps+"inspect",syscalls+"dispatchLegacy"],
        syscalls+"capConsole":[caps+"lookup",syscalls+"consoleRead",syscalls+"consoleWrite"],
        "Lemma.Kernel.Scheduler.dispatch":["Lemma.Kernel.Task.capture","Lemma.Kernel.Scheduler.call"],
        "Lemma.Kernel.Scheduler.call":[syscalls+"dispatch"],
        alias+"install":[task+"prepared",address+"base",alias+"checkedHeader",frames+"mappingCount",address+"owner",address+"root",alias+"checkedTable",address+"flushCurrent"],
        alias+"checkedTable":[frames+"resolvePurpose",frames+"mappingCount"],
        generation+"seedOneFree":[objects+"table",generation+"freeStep",objects+"maxGeneration"],
        generation+"advance":[objects+"nextSerial",objects+"table",objects+"maxSerial"],
    }
    constants={caps+"magic":0x31504143414d454c,caps+"headerOffset":2560,caps+"entriesOffset":2624,
               caps+"capacity":16,caps+"stride":64,caps+"active":1,caps+"constructing":2,
               objects+"magic":0x314a424f414d454c,objects+"capacity":16,objects+"endpointCapacity":4,objects+"registryCapacity":8,
               objects+"rows":256,objects+"stride":128,objects+"maxGeneration":0x0fffffffffffffff,
               objects+"maxSerial":0x0fffffffffffffff,objects+"consoleKey":16,objects+"managementKey":17,
               objects+"live":1,objects+"revoking":2,userabi+"endpointType":2,
               task+"managedOffset":120,alias+"aliasPage":0x31000,alias+"attackAddress":0x31a00,
               "Lemma.Platform.LemmaVM.Layout.capabilityControlValue":0x80400620,"Lemma.User.ABI.console":2}
    required=set(constants)|set(edges)|{callee for callees in edges.values() for callee in callees}
    if not required<=set(by_source):
        raise Core0Error("managed kernel lacks its genuine source lifecycle closure: "+str(sorted(required-set(by_source))))
    observed_edges=[]
    for caller,callees in edges.items():
        calls=parse_definitions_and_calls(_ir_definition_body(pre_ir,by_source[caller]))[2]
        for callee in callees:
            if by_source[callee] not in calls:
                raise Core0Error("managed source call edge is absent: "+caller+" -> "+callee)
            observed_edges.append([caller,callee])
    for source,value in constants.items():
        body=_ir_definition_body(pre_ir,by_source[source])
        if re.fullmatch(r"\s*entry:\s*ret i64 "+str(value)+r"\s*",body) is None:
            raise Core0Error("managed storage/generation source constant differs: "+source)
    ordered=[]
    for caller,before,after in [
        (task+"prepareManaged",task+"prepare",caps+"attach"),
        (task+"activateManaged",caps+"activate",task+"activate"),
        (task+"abort",task+"detachManaged","Lemma.Kernel.Loader.teardown"),
        (task+"reapOne",task+"detachManaged","Lemma.Kernel.Loader.teardown"),
        (entry+"configure",entry+"initialGrants",task+"activateManaged"),
        (entry+"configure",entry+"seedEndpoint",objects+"createEndpoint"),
        (entry+"createTamper",entry+"grant",alias+"install"),
        (entry+"createTamper",alias+"install",task+"activateManaged"),
        (caps+"header",address+"base",objects+"get"),
        (caps+"lookupEntry",caps+"requireActive",objects+"resolve"),
        (caps+"publish",objects+"reference",objects+"publishSerial"),
        (caps+"revokeKey",objects+"beginRevoke",objects+"destroy"),
    ]:
        ordered.append({"source":caller,**validate_call_precedes(_ir_definition_body(pre_ir,by_source[caller]),by_source[before],by_source[after])})
    gates=[]
    for protected in (syscalls+"dispatchManaged",syscalls+"dispatchLegacy"):
        gates.append({"source":syscalls+"dispatch",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"dispatch"]),by_source[caps+"managed"],by_source[protected])})
    gates.append({"source":syscalls+"dispatch",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"dispatch"]),by_source[caps+"managed"],by_source[syscalls+"dispatchManaged"],component="value",value=1)})
    for protected in (syscalls+"consoleRead",syscalls+"consoleWrite"):
        gates.append({"source":syscalls+"capConsole",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"capConsole"]),by_source[caps+"lookup"],by_source[protected])})
    # Only the capability wrapper may call the actual UART/copy routines from
    # the managed dispatcher; its legacy fallthrough rejects console number2.
    managed_body=_ir_definition_body(pre_ir,by_source[syscalls+"dispatchManaged"])
    if {by_source[syscalls+"consoleRead"],by_source[syscalls+"consoleWrite"]} & parse_definitions_and_calls(managed_body)[2]:
        raise Core0Error("managed dispatch directly bypasses capability-checked console wrapper")
    for row in re.findall(r"(?m)^.*\bcall[^@\n]*@([^ (]+)\(([^\n]*)\)$",managed_body):
        if row[0] in {by_source[source] for source in edges[syscalls+"dispatchManaged"] if source.startswith(caps)} and not row[1].startswith("i64 %arg0,"):
            raise Core0Error("managed syscall changed caller-local descriptor to a user-selected identity")
    endpoint_report=validate_h_endpoint_budget(_ir_definition_body(pre_ir,by_source[objects+"createEndpoint"]),by_source)
    # Bind the helper's status inversion; a count callback failure must never
    # be accepted as a successful preallocation result.
    failed_body=_ir_definition_body(pre_ir,by_source[objects+"failed"])
    if re.fullmatch(r"\s*entry:\s*%cmp0 = icmp eq i8 %arg0, 0\s*br i1 %cmp0, label %if.then.0, label %if.else.1\s*if.then.0:\s*br label %if.merge.2\s*if.else.1:\s*br label %if.merge.2\s*if.merge.2:\s*%if.result1 = phi i1 \[ 0, %if.then.0 \], \[ 1, %if.else.1 \]\s*ret i1 %if.result1\s*",failed_body) is None:
        raise Core0Error("endpoint count status helper differs from exact nonzero failure")
    alias_report=validate_h_alias(unit,pre_ir,by_source)
    denial_report=validate_h_legacy_console_denial(managed_body,by_source)
    launch_body=_ir_definition_body(pre_ir,by_source[entry+"launch"])
    tamper_body=_ir_definition_body(pre_ir,by_source[entry+"createTamper"])
    pattern=r"call \{ i64, i64 \} @"+re.escape(by_source[task+"prepareManaged"])+r"\(i64 ([0-9]+),"
    if re.findall(pattern,launch_body)!=["0","1","2"] or re.findall(pattern,tamper_body)!=["3"]:
        raise Core0Error("managed image preparation differs from exact source-selected boot roles")
    return {"endpoint_budget":endpoint_report,"alias":alias_report,"legacy_console_denial":denial_report,"managed_policy":MANAGED_POLICY,"storage":{"control":0x80400620,"header_offset":2560,"entries_offset":2624,"capacity":16,"entry_bytes":64,"object_capacity":16,"max_generation":0x0fffffffffffffff,"max_serial":0x0fffffffffffffff},
            "source_constants":{source:{"symbol":by_source[source],"value":value} for source,value in sorted(constants.items())},
            "source_call_edges":observed_edges,"ordered_cfg_calls":ordered,"checked_cfg_gates":gates,
            "limitations":["Compiled call/CFG/storage binding, not a proof of authority semantics or guest execution."]}


def validate_user_abi_data(section_text: str, data: bytes, symbol_text: str,
                           assembly: str, *, object_file: str) -> dict:
    """Account for the sole declarative initializer emitted by Lean startup.

    Compiled unit globals remain forbidden. This admits only the named input
    section of the startup object and its exact linked payload, not arbitrary
    writable data or additional target object symbols.
    """
    multi_file = re.fullmatch(r"users/(compute|sleeper|busy|fault|capabilities|peer|tamper)/(startup\.o|image\.elf)", object_file)
    if object_file not in {"user/startup.o", "user/image.elf"} and multi_file is None:
        raise Core0Error("user ABI data lacks its exact startup-object ownership")
    linked = object_file.endswith("/image.elf")
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
    owner = object_file.rsplit("/", 1)[0] + "/startup.o(.data.user_abi)"
    return {"source": "Lemma.User.ABI.version", "owned_input": owner,
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


def validate_unit(value: object, role: str, *, configuration: str = "normal", image_key: str | None = None) -> dict:
    unit = _object(value, f"{role} unit")
    multi_user = configuration in MULTI_USER_CONFIGURATIONS and role == "user"
    if (image_key is not None) != multi_user:
        raise Core0Error("per-image unit selection differs from its configuration/role")
    image = image_spec(configuration, image_key) if multi_user else None
    if multi_user and image is None:
        raise Core0Error("unknown per-image user unit selection")
    keys = {"schema_version", "artifact_category", "contract_version", "configuration", "role", "roots", "functions",
            "used_execution_ops", "used_device_ops", "used_loops"}
    case_field = {"startup_case"} if multi_user and configuration in {"tasks-fault-development", "capabilities-development"} else set()
    expected_managed = managed_fields(configuration, image)
    _keys(unit, keys | ({"image_key", "image_id"} if multi_user else set()) | case_field | set(expected_managed), "unit")
    if any(unit.get(key) != value for key, value in expected_managed.items()):
        raise Core0Error("unit managed policy/boot role differs")
    category = ("production" if configuration == "normal" else "development") + f"-{role}-unit"
    if (unit.get("schema_version") != (2 if multi_user else 1) or type(unit.get("schema_version")) is not int
            or unit.get("artifact_category") != category or unit.get("configuration") != configuration
            or unit.get("role") != role or unit.get("contract_version") != CONTRACTS[role]):
        raise Core0Error(f"{role} unit identity/version differs")
    if multi_user and (unit.get("image_key") != image_key or type(unit.get("image_id")) is not int or unit.get("image_id") != image["id"]):
        raise Core0Error("per-image user unit key/ID differs")
    if case_field and unit.get("startup_case") != image["startup_case"]:
        raise Core0Error("per-image user unit startup case differs from its closed registry")
    roots = _array(unit.get("roots"), f"{role} roots")
    expected = [(image["source"], image["args"])] if multi_user else [(source, list(args)) for source, args in configuration_roots(configuration)[role]]
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
        if configuration == "capabilities-development" and role == "user" and re.search(r"(?:^|\.[0-9]+\.)Lemma\.(?:Kernel|Compiler)\.", source):
            raise Core0Error("managed user source reaches privileged/compiler code")
        if ".Development." in source:
            allowed = (image["module"],) if multi_user else development_modules(configuration, role)
            if not any(re.search(r"(?:^|\.[0-9]+\.)" + re.escape(module) + r"\.", source) for module in allowed):
                raise Core0Error("development source escapes its exact selected module namespace")
        prefix = image["symbol_prefix"] if multi_user else "lemma_" + role + "_"
        if not isinstance(symbol, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_.$]+", symbol):
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


def validate_layout(value: object, *, configuration: str = "normal", image_key: str | None = None) -> dict:
    layout = _object(value, "layout")
    image = image_spec(configuration, image_key) if image_key is not None else None
    expected_managed = managed_fields(configuration, image)
    _keys(layout, {"schema_version", "contract_version", "configuration", "startup_case", "user_startup_case", "ram_base", "ram_limit",
                   "frame_bytes", "frame_count", "task_kernel_stack_pages", "task_kernel_stack_bytes", "context", "intervals", "user"} | set(expected_managed), "layout")
    if any(layout.get(key) != value for key, value in expected_managed.items()):
        raise Core0Error("layout managed policy/boot role differs")
    selected_case = image_spec(configuration, image_key)["startup_case"] if image_key is not None else user_startup_case(configuration)
    if type(layout.get("schema_version")) is not int or layout.get("schema_version") != 1 or layout.get("contract_version") != "lemma-kernel-layout-v1" or layout.get("configuration") != configuration or layout.get("startup_case") != startup_case(configuration) or layout.get("user_startup_case") != selected_case:
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
    multi = configuration in MULTI_USER_CONFIGURATIONS
    _keys(catalog, {"schema_version", "contract_version", "stage", "configuration", "startup_case", "user_startup_case", "symbols",
                    "user_images" if multi else "user_symbols"} | set(managed_fields(configuration)), "primitive catalog")
    if any(catalog.get(key) != value for key, value in managed_fields(configuration).items()):
        raise Core0Error("primitive catalog managed policy differs")
    expected_machine = MACHINE_SYMBOLS | (SUPERVISOR_SYMBOLS if stage == "supervisor" else set())
    if startup_case(configuration) == "machine-origin-probe":
        expected_machine |= {"lemma_machine_vector"}
    rows = [_object(row, "machine symbol") for row in _array(catalog.get("symbols"), "machine symbols")]
    if (type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != (2 if multi else 1)
            or catalog.get("contract_version") != "lemma-execution-v1" or catalog.get("stage") != stage
            or catalog.get("configuration") != configuration or catalog.get("startup_case") != startup_case(configuration) or catalog.get("user_startup_case") != user_startup_case(configuration)
            or {row.get("symbol") for row in rows} != expected_machine or len(rows) != len(expected_machine)):
        raise Core0Error("closed platform primitive catalog differs")
    for row in rows:
        _keys(row, {"symbol", "privilege", "effect"}, "machine symbol")
        if row.get("privilege") != ("M" if row["symbol"] in M_SYMBOLS else "S") or row.get("effect") != PRIMITIVE_EFFECTS[row["symbol"]]:
            raise Core0Error("machine primitive privilege/effect differs")
    expected_users = [{"key": row["key"], "id": row["id"], "startup_case": row["startup_case"], "symbols": user_primitive_rows(row["startup_case"]),
                       **({"boot_role": row["boot_role"]} if configuration == "capabilities-development" else {})}
                      for row in image_specs(configuration)] if multi else user_primitive_rows(user_startup_case(configuration))
    if (catalog.get("user_images" if multi else "user_symbols") != expected_users
            or multi and any(type(row.get("id")) is not int for row in catalog.get("user_images", []))):
        raise Core0Error("closed user primitive privilege/effect catalog differs")
    return expected_machine


def validate_user_primitive_catalog(value: object, image: dict, *, configuration: str = "tasks-development") -> dict:
    if image != image_spec(configuration, image.get("key")):
        raise Core0Error("per-image primitive authority differs from the closed selected image")
    expected = {"schema_version": 1, "contract_version": "lemma-user-execution-v1", "configuration": configuration,
                "image_key": image["key"], "image_id": image["id"], "startup_case": image["startup_case"],
                "symbols": user_primitive_rows(image["startup_case"]), **managed_fields(configuration, image)}
    catalog = _object(value, "per-image primitive catalog")
    if catalog != expected or type(catalog.get("schema_version")) is not int or type(catalog.get("image_id")) is not int:
        raise Core0Error("closed per-image user primitive catalog differs")
    return catalog


def validate_package_contract(value: object, *, configuration: str, catalog: dict | None = None) -> dict:
    image = {"id": 1, "entry": 0x10000, "text_va": 0x10000, "text_capacity": 0xf000,
             "data_va": 0x20000, "data_mem_bytes": 4096, "stack_va": 0x3fffc000, "stack_pages": 2, "flags": 0}
    multi = configuration in MULTI_USER_CONFIGURATIONS
    if multi:
        selected = validate_user_image_catalog(catalog, configuration=configuration)["images"]
        images = [{**image, "key": row["key"], "id": row["id"],
                   **({"boot_role": row["boot_role"]} if configuration == "capabilities-development" else {})} for row in selected]
    expected = {"schema_version": 2 if multi else 1, "configuration": configuration,
                "startup_case": startup_case(configuration), "user_startup_case": user_startup_case(configuration),
                "contract_version": "lemma-boot-package-v1", "magic": 0x31474b50414d454c,
                "version": 1, "image_count": len(images) if multi else 1, "header_bytes": 32, "descriptor_bytes": 96,
                "offset_encoding": "generated-label-differences", **({"images": images} if multi else {"image": image}),
                **managed_fields(configuration)}
    contract = _object(value, "boot package contract")
    if (contract != expected or any(type(contract.get(key)) is not int for key in ("schema_version", "magic", "version", "image_count", "header_bytes", "descriptor_bytes"))
            or any(type(row.get(key)) is not int for row in (contract.get("images", []) if multi else [contract.get("image", {})])
                   for key in image)):
        raise Core0Error("unknown/malformed boot package descriptor contract")
    return contract


def validate_package_payloads(package: bytes, contract: dict, payloads: list[tuple[bytes, bytes]]) -> list[dict]:
    """Bind every v1 descriptor to a separately audited image, in registry order."""
    count = contract["image_count"]
    minimum = 32 + count * 96
    if len(payloads) != count or len(package) < minimum or struct.unpack_from("<4Q", package) != (contract["magic"], 1, count, len(package)):
        raise Core0Error("boot package header/count/extent differs")
    images = contract.get("images", [contract.get("image")])
    occupied, last, reports = bytearray(len(package)), minimum, []
    occupied[:minimum] = b"\1" * minimum
    for index, (image, (text, data)) in enumerate(zip(images, payloads)):
        words = struct.unpack_from("<12Q", package, 32 + index * 96)
        ident, entry, text_va, text_offset, text_bytes, data_va, data_offset, data_bytes, memory, stack_va, pages, flags = words
        if ((ident, entry, text_va, data_va, memory, stack_va, pages, flags) !=
                (image["id"], image["entry"], image["text_va"], image["data_va"], image["data_mem_bytes"], image["stack_va"], image["stack_pages"], image["flags"])
                or not 0 < len(text) <= image["text_capacity"] or len(data) > memory
                or text_bytes != len(text) or data_bytes != len(data)
                or text_offset < last or text_offset % 8 or data_offset < text_offset + text_bytes or data_offset % 8
                or data_offset + data_bytes > len(package)):
            raise Core0Error("boot package descriptor/source image extents differ")
        for begin, raw in ((text_offset, text), (data_offset, data)):
            end = begin + len(raw)
            if end > len(package) or any(occupied[begin:end]) or package[begin:end] != raw:
                raise Core0Error("boot package image payload is overlapping, missing or changed")
            occupied[begin:end] = b"\1" * len(raw)
        last = data_offset + data_bytes
        reports.append({"id": ident, "key": image.get("key"), "text_offset": text_offset, "text_bytes": text_bytes,
                        "data_offset": data_offset, "data_bytes": data_bytes,
                        "text_sha256": hashlib.sha256(text).hexdigest(), "data_sha256": hashlib.sha256(data).hexdigest()})
    if any(byte for byte, used in zip(package, occupied) if not used):
        raise Core0Error("unaccounted nonzero boot package bytes outside audited payloads")
    if len(package) != last:
        raise Core0Error("boot package has an unexpected trailing extent")
    return reports


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
    validate_user_entry_source(user_assembly, user_root, user_case)
    return {"layout": CONTEXT_LAYOUT, "kernel_resume_status": 0x200000100, "saved_gpr_slots": 32,
            "fixed_frame_stores": 36, "temporary_spill_stores": 2, "shared_restore_loads": 35,
            "total_enter_loads": 37, "enter_machine_instructions": 91, "shared_restore_machine_instructions": 41,
            "enter_machine_sha256": hashlib.sha256(raw).hexdigest(), "restore_machine_sha256": SUPERVISOR_RESTORE_SHA256,
            "original_sp_and_t0_t1_preserved": True, "caller_satp_readback_saved": True,
            "kernel_resume_sie": 0, "kernel_resume_scratch": 0, "initial_user_argument": "a0:u64"}


def validate_user_entry_source(assembly: str, root: str, case: str) -> None:
    if case not in {"none", *USER_ATTACKS}:
        raise Core0Error("unknown user startup ABI case")
    prefix = [f"call {root}"] if case == "none" else ["mv gp, zero", "mv tp, zero", f"call {root}",
              "bnez a0, .Luser_exit", f"call {USER_ATTACKS[case][0]}", ".Luser_exit:"]
    expected = [*prefix, *(f"li a{register}, 0" for register in range(1, 7)), "li a7, 6",
                "ecall", ".Luser_exit_returned:", "j .Luser_exit_returned"]
    if _assembly_function(assembly, "_user_start") != expected:
        raise Core0Error("user startup does not forward its initial word to the exact Action root")


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


def validate_image_attack_object(section_text: str, symbol_text: str, raw: bytes, assembly: str,
                                *, configuration: str, image_key: str) -> dict:
    """Bind the sole G CSR exception to the selected Fault startup input."""
    image = image_spec(configuration, image_key)
    case = image["startup_case"]
    attacks = {symbol for symbol in defined_function_symbols(symbol_text) if symbol.startswith("lemma_user_attack_")}
    sections = re.findall(r"(?m)^.*\.text\.user_adversarial\s+.*$", section_text)
    if case == "none":
        if sections or attacks or raw or ".text.user_adversarial" in assembly:
            raise Core0Error("ordinary selected user startup object contains quarantined code")
        return {"case": "none", "privileged_instruction_exceptions": []}
    if (configuration, image_key, case) != ("tasks-fault-development", "fault", "supervisor-csr"):
        raise Core0Error("unknown per-image privileged instruction authority")
    symbol, effect, words = USER_ATTACKS[case]
    section = re.fullmatch(r"\s*\[\s*(\d+)\]\s+\.text\.user_adversarial\s+PROGBITS\s+0+\s+[0-9a-f]+\s+000008\s+00\s+AX\s+0\s+0\s+4\s*", sections[0]) if len(sections) == 1 else None
    rows = [line.split() for line in symbol_text.splitlines() if line.split() and line.split()[-1] == symbol]
    if (section is None or attacks != {symbol} or len(rows) != 1 or len(rows[0]) != 8
            or rows[0][1:] != ["0000000000000000", "8", "FUNC", "GLOBAL", "DEFAULT", section[1], symbol]
            or raw != struct.pack("<2I", *words)
            or _assembly_function(assembly, symbol) != ["csrr a0, sstatus", "ret"]):
        raise Core0Error("Fault startup object CSR section/symbol/bytes/source inventory differs")
    return {"case": case, "symbol": symbol, "effect": effect, "bytes": len(raw),
            "section": ".text.user_adversarial", "object": image["directory"] + "/startup.o",
            "raw_sha256": hashlib.sha256(raw).hexdigest(), "privileged_instruction_exceptions": [0]}


def _validate_readonly_pmp_lookup(ir: str, unit: dict, *, optimized: bool) -> tuple[set[int], list[dict]]:
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


def validate_readonly_pmp_lookup(ir: str, unit: dict, *, optimized: bool) -> tuple[set[int], list[dict]]:
    """Preserve PMP admission; add only two observed immutable H lookups."""
    if unit.get("configuration") != "capabilities-development" or unit.get("role") != "kernel" or not optimized:
        return _validate_readonly_pmp_lookup(ir,unit,optimized=optimized)
    lines=ir.splitlines();globals_=[line.strip() for line in lines if re.match(r"^\s*@",line)]
    if not globals_:
        return _validate_readonly_pmp_lookup(ir,unit,optimized=optimized)
    by_source={re.sub(r"^_private\..*?\.[0-9]+\.","",row["source"]):row for row in unit["functions"]}
    specs=[("Lemma.User.CapabilityABI.typeMask",[35,124,928,1056],["u64"],[]),
           ("Lemma.Kernel.Objects.initStep",[1,3,4],["u32","u32","u64","u64","u64","u64","u64"],["checked-access","physical-write"])]
    accepted_globals=[];sites=set();observed=[];owners=_line_functions(lines)
    from audit_memory import parse_ir_functions,_parse_blocks
    functions=parse_ir_functions(ir)
    for source,values,args,effects in specs:
        row=by_source.get(source)
        if row is None or row["args"]!=args or row["effects"]!=effects:
            raise Core0Error("H readonly lookup lacks its exact source/signature/effects")
        symbol=row["symbol"];table="switch.table."+symbol;count=len(values)
        expected=f"@{table} = private unnamed_addr constant [{count} x i64] ["+", ".join(f"i64 {value}" for value in values)+"], align 8"
        if globals_.count(expected)!=1 or len(re.findall(r"@"+re.escape(table)+r"(?![A-Za-z0-9_.$-])",ir))!=2:
            raise Core0Error("H readonly lookup exact global/content/use inventory differs")
        function=functions.get(symbol)
        types={"u32":"i32","u64":"i64"}
        if function is None or re.findall(r"\b(i1|i8|i32|i64)\b",re.search(r"@"+re.escape(symbol)+r"\(([^\n]*)\)",function.header).group(1))!=[types[t] for t in args]:
            raise Core0Error("H readonly lookup LLVM argument signature differs")
        body="\n".join(line.split(";",1)[0].rstrip() for line in function.body.splitlines())
        blocks=_parse_blocks(body,symbol);load="%switch.load = load i64, ptr %switch.gep, align 8"
        if source=="Lemma.User.CapabilityABI.typeMask":
            expected_blocks={"entry":["%switch.tableidx = add i64 %arg0, -1","%0 = icmp ult i64 %switch.tableidx, 4","br i1 %0, label %switch.lookup, label %if.merge.2"],
                             "switch.lookup":[f"%switch.gep = getelementptr inbounds nuw [4 x i64], ptr @{table}, i64 0, i64 %switch.tableidx",load,"br label %if.merge.2"],
                             "if.merge.2":["%if.result15 = phi i64 [ %switch.load, %switch.lookup ], [ 0, %entry ]","ret i64 %if.result15"]}
            if blocks!=expected_blocks or not re.search(r"\bi64 @"+re.escape(symbol)+r"\(i64 %arg0\)",function.header):
                raise Core0Error("H type-mask lookup lacks exact subtraction/bound guard/default/body")
        else:
            put=by_source.get("Lemma.Kernel.Objects.put",{}).get("symbol")
            if put is None or not re.search(r"define \{ i64, i64 \} @"+re.escape(symbol),function.header):
                raise Core0Error("H pinned-kind lookup lacks checked initialization source")
            if blocks.get("action.if.else.1")!=["%bin15 = add i64 %call1, 16","%0 = icmp ult i32 %arg0, 3","br i1 %0, label %switch.lookup, label %if.merge.5"] or blocks.get("switch.lookup")!=["%1 = zext nneg i32 %arg0 to i64",f"%switch.gep = getelementptr inbounds nuw [3 x i64], ptr @{table}, i64 0, i64 %1",load,"br label %if.merge.5"]:
                raise Core0Error("H pinned-kind lookup lacks exact bounded index/load block")
            merge=blocks.get("if.merge.5",[])
            if len(merge)<2 or merge[:2]!=["%if.result27 = phi i64 [ 0, %action.if.else.1 ], [ %switch.load, %switch.lookup ]",f"%action.call.result28 = call {{ i64, i64 }} @{put}(i64 %bin15, i64 %if.result27)"] or len(re.findall(r"%if\.result27(?![A-Za-z0-9_.$-])",body))!=2:
                raise Core0Error("H pinned-kind result escapes its sole object-kind publication")
            successors=_structured_successors(_structured_ir_blocks(body))
            without_guard={block:tuple(target for target in targets if (block,target)!=("action.if.else.1","switch.lookup")) for block,targets in successors.items()}
            if _structured_reachable(without_guard,"entry","switch.lookup") or _structured_reachable(successors,"if.merge.5","switch.lookup"):
                raise Core0Error("H pinned-kind lookup has a bound-guard bypass")
        located={i for i,line in enumerate(lines) if line.strip()==load and owners[i]==symbol}
        if len(located)!=1 or len(re.findall(r"%switch\.gep(?![A-Za-z0-9_.$-])",body))!=2 or len(re.findall(r"%switch\.load(?![A-Za-z0-9_.$-])",body))!=2:
            raise Core0Error("H readonly pointer/load use inventory differs")
        sites|=located;accepted_globals.append(expected)
        observed.append({"source":row["source"],"function":symbol,"global":table,"values":values,"element_bits":64,"alignment_bytes":8,"index_bound":count,"default":0,"guarded_loads":1,"readonly":True})
    filtered="\n".join("" if line.strip() in accepted_globals else line for line in lines)
    pmp_sites,pmp=_validate_readonly_pmp_lookup(filtered,unit,optimized=True)
    return sites|pmp_sites,[*pmp,*observed]


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


def validate_h_readonly_sections(section_text: str, symbol_text: str, relocation_text: str,
                                 constants: bytes, rodata: bytes, *, object_file: str, tables: list[dict]) -> dict:
    """Exact H object bytes and local symbols for the two admitted IR lookups."""
    if object_file!="kernel/program.o" or len(tables)!=3:
        raise Core0Error("H immutable tables lack their exact kernel object inventory")
    pmp=[0x20001fff,0x20041fff,0x20ffffff,0x0400001f];masks=[35,124,928,1056];kinds=[1,3,4]
    sources=["Lemma.Kernel.MachineServices.expectedPmp","Lemma.User.CapabilityABI.typeMask","Lemma.Kernel.Objects.initStep"]
    if any(re.sub(r"^_private\..*?\.[0-9]+\.","",row.get("source",""))!=source or row.get("values")!=values or row.get("readonly") is not True for row,source,values in zip(tables,sources,[pmp,masks,kinds])):
        raise Core0Error("H object immutable-table source/content provenance differs")
    def section(name,size,entry_size,flags):
        rows=re.findall(r"(?m)^\s*\[\s*(\d+)\]\s+"+re.escape(name)+r"\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+"+entry_size+r"\s+"+flags+r"\s+0\s+0\s+8\s*$",section_text)
        if len(rows)!=1 or int(rows[0][1],16)!=size:
            raise Core0Error("H immutable-table section size/flags/alignment differs")
        return rows[0][0]
    cst_section=section(".rodata.cst32",64,"20","AM")
    ro_section=section(".rodata",len(rodata),"00","A")
    if constants!=struct.pack("<8Q",*pmp,*masks):
        raise Core0Error("H combined PMP/type-mask immutable bytes differ")
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=="OBJECT" and line.split()[6]!="UND"]
    expected_names={".L"+row["global"] for row in tables}
    if {row[-1] for row in rows}!=expected_names or len(rows)!=3:
        raise Core0Error("H immutable object-symbol inventory differs")
    observed=[]
    for index,(table,values) in enumerate(zip(tables,[pmp,masks,kinds])):
        row=next(row for row in rows if row[-1]==".L"+table["global"])
        offset,size=int(row[1],16),int(row[2]);section_id=cst_section if index<2 else ro_section
        raw=constants if index<2 else rodata
        if row[4:7]!=["LOCAL","DEFAULT",section_id] or size!=len(values)*8 or offset%8 or offset+size>len(raw) or raw[offset:offset+size]!=struct.pack("<"+str(len(values))+"Q",*values) or index<2 and offset!=index*32:
            raise Core0Error("H immutable table symbol extent/ownership/bytes differs")
        current=None
        for line in relocation_text.splitlines():
            header=re.search(r"Relocation section '([^']+)'",line)
            if header:current=header[1]
            relocation=re.match(r"\s*([0-9a-f]+)\s+[0-9a-f]+\s+(R_RISCV_[A-Z0-9_]+)\s",line)
            if relocation and current==(".rela.rodata.cst32" if index<2 else ".rela.rodata") and int(relocation[1],16)<offset+size and offset<int(relocation[1],16)+(8 if relocation[2].endswith("64") else 4):
                raise Core0Error("H immutable table literal bytes contain a link relocation")
        observed.append({"source":table["source"],"symbol":row[-1],"section":".rodata.cst32" if index<2 else ".rodata","offset":offset,"bytes":size,"values":values,"sha256":hashlib.sha256(raw[offset:offset+size]).hexdigest(),"relocations":[]})
    return {"object":object_file,"configuration":"capabilities-development","readonly_tables":observed,
            "constant_section_bytes":64,"constant_section_sha256":hashlib.sha256(constants).hexdigest()}


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



def _artifact_inspector(root: Path, directory: Path, timeout: float, logs: list[dict]):
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise Core0Error("artifact inspection timeout must be finite and positive")
    tools = require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump", "llvm-objcopy"))
    pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
    store = pin.get("tools", {}).get("llvm", {}).get("store_path")
    if pin.get("status") != "pinned" or not isinstance(store, str) or any(not path.startswith(store + "/") for path in tools.values()):
        raise Core0Error("artifact inspection tools differ from the immutable LLVM output")
    def inspect(name: str, args: list[str], label: str) -> str:
        actual = [tools[name], *(["--elf-output-style=GNU"] if name == "llvm-readelf" else []), *args]
        result = run_bounded(actual, cwd=directory, timeout_seconds=timeout)
        logs.append({"argv": actual, "cwd": str(directory), "returncode": result.returncode})
        text = (result.stdout + result.stderr).decode(errors="strict")
        (directory / ("audit-" + label + ".txt")).write_text(text)
        if result.returncode:
            raise Core0Error(f"artifact inspection failed: {label}: {text}")
        return text
    return inspect


def inspect_linked_elf(inspect, *, name: str, image: str, expected: set[str], layout: dict,
                       user: bool, assembly: str, user_case: str = "none") -> tuple[dict, str, str, dict]:
    """One linked-code scanner shared by each boot and separately linked user ELF."""
    header = inspect("llvm-readelf", ["-h", image], name + "-header")
    if not all(token in header for token in ("ELF64", "little endian", "RISC-V")) or not re.search(r"Flags:\s+0x0(?:\s|$)", header):
        raise Core0Error("ELF ISA/class/endianness/float/compressed flags differ")
    attributes = inspect("llvm-readelf", ["-A", image], name + "-attributes")
    arch = re.search(r"rv64i[0-9p]+(?:_[a-z0-9p]+)+", attributes)
    if not arch or arch[0] != "rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0":
        raise Core0Error("ELF architecture attribute differs from integer-only profile")
    if inspect("llvm-nm", ["--undefined-only", image], name + "undefined").strip():
        raise Core0Error("final ELF contains undefined symbols")
    if relocation_types(inspect("llvm-readelf", ["-r", image], name + "-relocations")):
        raise Core0Error("final ELF contains runtime relocations")
    symbol_text = inspect("llvm-readelf", ["-s", "--wide", image], name + "-symbols")
    symbols = defined_function_symbols(symbol_text)
    if symbols != expected:
        raise Core0Error(f"{name} executable symbol provenance differs: missing {sorted(expected-symbols)}; unexpected {sorted(symbols-expected)}")
    addresses = numeric_symbols(inspect("llvm-nm", ["--defined-only", image], name + "-addresses"))
    segments = parse_load_segments(inspect("llvm-readelf", ["-l", "--wide", image], name + "-segments"))
    intervals = [(row["base"], row["limit"]) for row in layout["intervals"]] if not user else [(0x10000, 0x1f000), (0x20000, 0x21000)]
    if not segments:
        raise Core0Error("ELF load segment corpus is empty")
    if user and (len(segments) != 2 or segments[0]["virtual_address"] != 0x10000 or segments[0]["flags"] != "RE"
                 or segments[0]["memory_size"] != segments[0]["file_size"]
                 or segments[1]["virtual_address"] != 0x20000 or segments[1]["flags"] != "RW"
                 or segments[1]["file_size"] != 16 or segments[1]["memory_size"] != 4096):
        raise Core0Error("user ELF text RX/data RW initialized/BSS segment contract differs")
    for segment in segments:
        begin, size = segment["virtual_address"], segment["memory_size"]
        if (size == 0 or segment["file_size"] > size or "W" in segment["flags"] and "E" in segment["flags"]
                or not any(lo <= begin and begin + size <= hi for lo, hi in intervals) or segment["physical_address"] != begin):
            raise Core0Error("ELF PT_LOAD permissions or declared range differs")
    entry = re.search(r"Entry point address:\s*(0x[0-9a-fA-F]+)", header)
    required = 0x10000 if user else 0x80000000
    if not entry or int(entry[1], 16) != required:
        raise Core0Error("ELF entry point differs")
    for symbol in symbols:
        privilege = "U" if user else ("M" if symbol.startswith("lemma_firmware_") or symbol in M_SYMBOLS else "S")
        low, high = ((0x10000, 0x1f000) if user else (0x80000000, 0x80010000) if privilege == "M" else (0x80200000, 0x80300000))
        if symbol not in addresses or not low <= addresses[symbol] < high:
            raise Core0Error(f"{symbol} lies outside its source privilege range")
    machine = inspect("llvm-objdump", ["-d", "--no-show-raw-insn", image], name + "-disassembly")
    ranges = function_ranges(symbol_text)
    raw_machine = inspect("llvm-objdump", ["-d", image], name + "-raw-disassembly")
    attack = validate_user_attack_machine(raw_machine, ranges, assembly, user_case) if user else None
    validate_machine(machine, user=user, ranges=ranges, user_csr_pc=attack["base"] if user and user_case == "supervisor-csr" else None)
    record = {"entry": required, "segments": segments, "function_symbols": sorted(symbols),
              "function_ranges": {symbol: {"base": address, "bytes": size} for symbol, (address, size) in ranges.items()}}
    if user:
        begin, size = ranges["_user_start"]
        pcs = [int(match[1], 16) for line in machine.splitlines()
               if (match := re.match(r"\s*([0-9a-f]+):\s+ecall\s*$", line)) and begin <= int(match[1], 16) < begin + size]
        if len(pcs) != 1:
            raise Core0Error("user startup lacks its exact single exit ECALL")
        record.update(exit_ecall_pc=pcs[0], syscall_bridge=validate_user_syscall_bridge(assembly, raw_machine, ranges),
                      quarantined_startup=attack)
    return record, symbol_text, raw_machine, ranges


def audit_user_image(*, root: Path, output_dir: Path, catalog: dict, image_key: str,
                     optimization: str, timeout_seconds: float = 60) -> dict:
    """Reusable actual unit/object/ELF/stack audit for full and standalone images.

    The caller binds the registry, source snapshot and construction commands.
    This scanner independently checks every selected image's actual bytes.
    """
    image = selected_user_image(catalog, image_key)
    configuration, user_case = catalog["configuration"], image["startup_case"]
    if optimization not in OPT_PASSES or output_dir.name != image_key or output_dir.parent.name != "users":
        raise Core0Error("per-image audit path/optimization differs")
    logs = []
    inspect = _artifact_inspector(root, output_dir, timeout_seconds, logs)
    layout = validate_layout(load_json(output_dir / "layout.json"), configuration=configuration, image_key=image_key)
    validate_user_primitive_catalog(load_json(output_dir / "primitive-catalog.json"), image, configuration=configuration)
    unit = validate_unit(load_json(output_dir / "unit.json"), "user", configuration=configuration, image_key=image_key)
    ir = {kind: validate_ir((output_dir / file).read_text(), unit, optimized=kind == "optimized")
          for kind, file in (("pre", "program.ll"), ("optimized", "program.opt.ll"))}
    assembly = (output_dir / "startup.S").read_text()
    validate_user_entry_source(assembly, unit["roots"][0]["symbol"], user_case)
    primitive_symbols = {row["symbol"] for row in user_primitive_rows(user_case)}
    object_functions = {"startup.o": primitive_symbols, "program.o": set(ir["optimized"]["definitions"])}
    allowed_relocations = {"R_RISCV_BRANCH", "R_RISCV_JAL", "R_RISCV_PCREL_HI20", "R_RISCV_PCREL_LO12_I", "R_RISCV_PCREL_LO12_S",
                           "R_RISCV_CALL", "R_RISCV_CALL_PLT", "R_RISCV_64", "R_RISCV_32", "R_RISCV_ADD64", "R_RISCV_SUB64"}
    initializer, attack_object = None, None
    for obj, expected in object_functions.items():
        symbols = inspect("llvm-readelf", ["-s", "--wide", obj], obj + "-symbols")
        if defined_function_symbols(symbols) != expected or not relocation_types(inspect("llvm-readelf", ["-r", obj], obj + "-relocations")) <= allowed_relocations:
            raise Core0Error("user object executable source/relocation closure differs")
        section_text = inspect("llvm-readelf", ["-S", "--wide", obj], obj + "-sections")
        sections = alloc_section_names(section_text)
        allowed = ({".text", ".text.user_start", ".text.user_boundary", ".data.user_abi"}
                   | ({".text.user_adversarial"} if user_case != "none" else set())) if obj == "startup.o" else {".text", ".rodata", ".rodata.cst8", ".data", ".bss"}
        if not sections <= allowed:
            raise Core0Error("unaccounted allocated per-image user object section")
        if ".rodata.cst8" in sections:
            constant = re.search(r"(?m)^\s*\[\s*\d+\]\s+\.rodata\.cst8\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)\s+08\s+AM\s+0\s+0\s+8\s*$", section_text)
            if not constant or int(constant[1], 16) == 0 or int(constant[1], 16) % 8:
                raise Core0Error("user constant pool flags/entry size/alignment differ")
        if obj == "startup.o":
            attack_bytes = b""
            if user_case != "none":
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.text.user_adversarial", obj, "audit-attack-object.bin"], "attack-object-extract")
                attack_bytes = (output_dir / "audit-attack-object.bin").read_bytes()
            attack_object = validate_image_attack_object(section_text, symbols, attack_bytes, assembly,
                                                        configuration=configuration, image_key=image_key)
            inspect("llvm-objcopy", ["-O", "binary", "--only-section=.data.user_abi", obj, "audit-abi-object.bin"], "abi-object-extract")
            initializer = validate_user_abi_data(section_text, (output_dir / "audit-abi-object.bin").read_bytes(), symbols, assembly,
                                                object_file=image["directory"] + "/startup.o")
    expected_objects = {image["directory"] + "/" + obj for obj in ("startup.o", "program.o")}
    linked_objects = set(re.findall(r"([^\s()]+\.o)(?=[:(\s])", (output_dir / "image.map").read_text()))
    if linked_objects != expected_objects:
        raise Core0Error("per-image actual link map escapes its two declared objects")
    for symbol in primitive_symbols:
        if machine_frame(assembly, symbol):
            raise Core0Error("user entry/syscall consumes undeclared stack")
    frames = parse_stack_sizes(inspect("llvm-readelf", ["--stack-sizes", "program.o"], "stack-sizes"))
    if set(frames) != object_functions["program.o"]:
        raise Core0Error("per-image stack metadata differs from object code closure")
    validate_compiled_stack(inspect("llvm-objdump", ["-d", "--no-show-raw-insn", "program.o"], "stack-disassembly"), frames)
    primitives = {row["primitive_symbol"]: machine_frame(assembly, row["primitive_symbol"])
                  for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
    undefined = {line.split()[-1] for line in inspect("llvm-nm", ["--undefined-only", "program.o"], "stack-undefined").splitlines() if line.split()}
    if not undefined <= set(primitives):
        raise Core0Error("per-image object contains an unaccounted stack/runtime symbol")
    post = (output_dir / "program.opt.ll").read_text()
    _defs, _decls, calls = parse_definitions_and_calls(post)
    primitives.update({symbol: 0 for symbol in calls & OPTIMIZER_INTRINSICS})
    graph = weighted_stack_graph(post, frames, primitives)
    capacities = {"machine": 65536, "boot": 61440, "kernel-trap": layout["task_kernel_stack_bytes"], "user": layout["user"]["stack_pages"] * layout["frame_bytes"]}
    graph.update(entries=validate_stack_entries(unit, graph, capacities=capacities, vector_bytes=288),
                 function_bytes=dict(sorted(frames.items())), object_undefined_symbols=sorted(undefined), maximum_compiled_frame_bytes=max(frames.values()))
    elf, symbols, raw, ranges = inspect_linked_elf(inspect, name="user", image="image.elf", expected=primitive_symbols | set(ir["optimized"]["definitions"]),
                                                 layout=layout, user=True, assembly=assembly, user_case=user_case)
    for section, target in ((".text", "text.bin"), (".data", "data.bin")):
        actual = "audit-extracted-" + target
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=" + section, "image.elf", actual], target + "-extract")
        if (output_dir / actual).read_bytes() != (output_dir / target).read_bytes():
            raise Core0Error("per-image packaged payload differs from its independently extracted ELF section")
    text, data = (output_dir / "text.bin").read_bytes(), (output_dir / "data.bin").read_bytes()
    if not 0 < len(text) <= 0xf000 or len(data) != 16:
        raise Core0Error("per-image user text/initialized-data extent differs")
    initialized = validate_user_abi_data(inspect("llvm-readelf", ["-S", "--wide", "image.elf"], "user-sections"), data, symbols, assembly,
                                       object_file=image["directory"] + "/image.elf")
    if initializer is None or initialized["sha256"] != initializer["sha256"]:
        raise Core0Error("per-image linked initializer differs from its declared startup object")
    elf["initialized_data"] = initialized
    return {"image_key": image_key, "image_id": image["id"], "unit_ir": ir, "elf": elf, "stack_bounds": graph, **managed_fields(configuration,image),
            "image_sha256": sha256(output_dir / "image.elf"), "text_sha256": sha256(output_dir / "text.bin"),
            "data_sha256": sha256(output_dir / "data.bin"), "commands": logs,
            **({"startup_case": user_case, "object_quarantined_startup": attack_object} if configuration == "tasks-fault-development" else {})}


def validate_multi_commands(rows: object, *, root: Path, output_dir: Path, images: list[dict],
                            optimization: str, roles: dict, standalone: bool, configuration: str = "tasks-development") -> None:
    rows = _array(rows, "multi-image construction commands")
    if not rows or any(not isinstance(row, dict) or type(row.get("returncode")) is not int or row["returncode"] != 0
                       or not isinstance(row.get("argv"), list) or not row["argv"]
                       or any(not isinstance(arg, str) for arg in row["argv"]) or not isinstance(row.get("cwd"), str)
                       for row in rows):
        raise Core0Error("multi-image command corpus is empty, malformed or failed")
    base = str(output_dir.relative_to(root))
    def compile_unit(directory):
        return [("opt", ["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"], base + "/" + directory),
                ("llc", [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"], base + "/" + directory)]
    expected = [item for role in roles for item in compile_unit(role)]
    expected += [item for image in images for item in compile_unit(image["directory"])]
    for image in images:
        d = image["directory"]
        expected += [("clang", [*STARTUP_ARGUMENTS, d + "/startup.S", "-o", d + "/startup.o"], base),
                     ("ld.lld", ["-m", "elf64lriscv", "--no-relax", "-T", d + "/link.ld", "-Map=" + d + "/image.map", d + "/startup.o", d + "/program.o", "-o", d + "/image.elf"], base),
                     ("llvm-objcopy", ["-O", "binary", "--only-section=.text", d + "/image.elf", d + "/text.bin"], base),
                     ("llvm-objcopy", ["-O", "binary", "--only-section=.data", d + "/image.elf", d + "/data.bin"], base)]
    if not standalone:
        expected += [("clang", [*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"], base),
                     ("clang", [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"], base),
                     ("ld.lld", ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"], base)]
    def tool_name(path):
        name = Path(path).name
        return "clang" if name == "clang-20" else name
    actual = [(tool_name(row["argv"][0]), row["argv"][1:], row["cwd"]) for row in rows
              if tool_name(row["argv"][0]) in {"opt", "llc", "clang", "ld.lld", "llvm-objcopy"} and row["argv"][1:] != ["--version"]]
    if actual != expected:
        raise Core0Error("multi-image actual tool/arguments/working-directory closure differs")
    pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
    stores = {name: pin["tools"]["llvm"]["store_path"] for name in ("opt", "llc", "llvm-objcopy")}
    stores.update({"clang": pin["tools"]["llvm"]["outputs"]["clang_unwrapped"]["store_path"], "ld.lld": pin["tools"]["lld"]["store_path"],
                   "lean": pin["tools"]["lean"]["store_path"], "lake": pin["tools"]["lean"]["store_path"]})
    for row in rows:
        name = tool_name(row["argv"][0])
        if name in stores and not row["argv"][0].startswith(stores[name] + "/"):
            raise Core0Error("multi-image compiler executable differs from its pinned store")
    source_path = pin["tools"]["lean"]["source_path"]
    nix = [row["argv"][1:] for row in rows if Path(row["argv"][0]).name == "nix"]
    if nix != [["build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION], ["path-info", "--json", source_path]]:
        raise Core0Error("multi-image immutable Lean source realization commands differ")
    consumers = {"CatalogExport.lean": "import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n"}
    for image in images:
        consumers[image["directory"] + "/Export.lean"] = (f'import {image["module"]}\nimport Lemma.Compiler.KernelExport\n\n'
                                                          f'#lemma_export_user_image "{image["key"]}" [{image["source"]}]\n')
    if standalone:
        consumers["UserFilesExport.lean"] = f'import Lemma.Compiler.KernelExport\n\n#lemma_export_user_files "{images[0]["key"]}"\n'
    else:
        consumers["BootExport.lean"] = "import Lemma.Compiler.KernelExport\n\n#lemma_export_boot_files\n"
        for role, module in configuration_modules(configuration).items():
            consumers[role + "/Export.lean"] = (f'import {module}\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "{role}" ['
                                                + ", ".join(source for source, _ in roles[role]) + "]\n")
    for path, contents in consumers.items():
        if (output_dir / path).read_text() != contents:
            raise Core0Error("genuine Lean export consumer differs from its exact selected roots")
    exports = [row for row in rows if Path(row["argv"][0]).name == "lake" and row["argv"][1:3] == ["env", "lean"]]
    expected_exports = [base + "/CatalogExport.lean", *(base + "/" + role + "/Export.lean" for role in roles),
                        *(base + "/" + image["directory"] + "/Export.lean" for image in images),
                        base + ("/UserFilesExport.lean" if standalone else "/BootExport.lean")]
    if [row["argv"][3:] for row in exports] != [[path] for path in expected_exports] or any(row["cwd"] != "." for row in exports):
        raise Core0Error("genuine Lean elaboration invocation/working-directory evidence differs")


def audit_standalone_user(*, root: Path, output_dir: Path, timeout_seconds: float = 60) -> dict:
    try:
        relative = output_dir.resolve().relative_to((root / "build/user").resolve())
    except ValueError as error:
        raise Core0Error("independent user audit must stay inside build/user") from error
    if not relative.parts:
        raise Core0Error("refusing to audit the whole build/user evidence root")
    result_path = output_dir / "audit.json"
    invalidate_output_file(result_path, root)
    invalidate_output_file(output_dir / "audit-failure.json", root)
    logs = []
    try:
        build = _object(load_json(output_dir / "user-build.json"), "independent user build")
        provenance = _object(load_json(output_dir / "user-provenance.json"), "independent user provenance")
        catalog = validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"))
        image = selected_user_image(catalog, provenance.get("image_key"))
        configuration = catalog["configuration"]
        key, directory = image["key"], image["directory"]
        validate_standalone_managed_provenance(build, provenance, configuration=configuration, image=image)
        identity = {"schema_version": 2, "artifact_category": "development-user-image", "configuration": configuration,
                    "image_key": key, "image_id": image["id"], "stage": "supervisor", "startup_case": "normal", "user_startup_case": image["startup_case"],
                    **managed_fields(configuration, image)}
        if (any(build.get(field) != value or provenance.get(field) != value for field, value in identity.items())
                or type(build.get("schema_version")) is not int or type(provenance.get("schema_version")) is not int
                or type(build.get("image_id")) is not int or type(provenance.get("image_id")) is not int
                or build.get("status") != "BUILT" or build.get("provenance_sha256") != sha256(output_dir / "user-provenance.json")):
            raise Core0Error("independent user build/provenance identity differs")
        optimization = provenance.get("optimization")
        if optimization not in OPT_PASSES or build.get("optimization") != optimization:
            raise Core0Error("independent user optimization differs")
        source_snapshot = source_inputs(root)
        if provenance.get("source_inputs") != source_snapshot:
            raise Core0Error("independent user complete source inventory is missing/stale")
        closure = module_closure(root, image["module"], allow_development=True,
                                 forbid_user_privileged_imports=configuration == "capabilities-development")
        if configuration == "capabilities-development" and any(path.startswith(("Lemma/Kernel/", "Lemma/Compiler/")) for path in closure):
            raise Core0Error("managed user target dependency closure contains privileged/compiler code")
        if (any("/Development/" in path and path != image["module"].replace(".", "/") + ".lean" for path in closure)
                or provenance.get("target_module_closures") != {"users": {key: closure}}):
            raise Core0Error("independent user selected source dependency closure differs")
        generated = ["user-image-catalog.json", *(directory + "/" + name for name in ("startup.S", "link.ld", "layout.json", "primitive-catalog.json"))]
        if (provenance.get("generated_by_lean") != generated
                or provenance.get("linked_inputs") != {"users": {key: [directory + "/startup.o", directory + "/program.o"]}}
                or provenance.get("unit_contracts") != {"users": {key: CONTRACTS["user"]}}):
            raise Core0Error("independent user selected generated/linked/contract inventory differs")
        artifacts = _object(provenance.get("artifacts"), "independent user artifacts")
        mandatory = set(generated) | {"CatalogExport.lean", "UserFilesExport.lean"} | {directory + "/" + name for name in
                    (*UNIT_FILES, "Export.lean", "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map", "text.bin", "data.bin")}
        if build.get("artifacts") != artifacts or not mandatory <= set(artifacts):
            raise Core0Error("independent user mandatory artifact inventory differs")
        for name, digest in artifacts.items():
            path = output_dir / name
            if (not path.resolve().is_relative_to(output_dir.resolve()) or not path.is_file() or sha256(path) != digest
                    or name.endswith((".o", ".elf")) and name not in {directory + "/startup.o", directory + "/program.o", directory + "/image.elf"}):
                raise Core0Error("independent user artifact is stale, foreign or escapes selected output")
        pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
        realization = _object(provenance.get("lean_source_realization"), "independent Lean source realization")
        expected = validate_lean_source_realization(pin["tools"]["lean"], str(realization.get("source_path")) + "\n",
                    {str(realization.get("source_path")): {"narHash": realization.get("narHash"), "narSize": realization.get("narSize")}})
        uint_source = Path(expected["source_path"]) / "src/Init/Data/UInt/Basic.lean"
        expected.update(uint_source=str(uint_source), uint_source_sha256=LEAN_UINT_SOURCE_SHA256)
        if realization != expected or build.get("lean_source_realization") != expected or not uint_source.is_file() or sha256(uint_source) != LEAN_UINT_SOURCE_SHA256:
            raise Core0Error("independent user immutable Lean source evidence differs")
        validate_multi_commands(provenance.get("commands"), root=root, output_dir=output_dir, images=[image], optimization=optimization, roles={}, standalone=True, configuration=configuration)
        observed = audit_user_image(root=root, output_dir=output_dir / directory, catalog=catalog, image_key=key,
                                    optimization=optimization, timeout_seconds=timeout_seconds)
        logs.extend(observed["commands"])
        if source_inputs(root) != source_snapshot:
            raise Core0Error("independent user source changed during audit")
        record = {**identity, "status": "PASS", "optimization": optimization, "source_commit": provenance["source_commit"],
                  "dirty_paths": provenance["dirty_paths"], "source_inputs": source_snapshot, "lean_source_realization": realization,
                  "user_image_catalog_sha256": sha256(output_dir / "user-image-catalog.json"), "provenance_sha256": sha256(output_dir / "user-provenance.json"),
                  **observed, "limitations": ["Independent user artifact/source audit; no kernel was built and no target execution is established."]}
        write_json(result_path, record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 2, "status": "FAIL", "error": str(error), "commands": logs})
        raise

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
    logs = []
    try:
        tools = require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump", "llvm-objcopy"))
    except Core0Error as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": str(error), "commands": logs})
        raise

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
        multi = configuration in MULTI_USER_CONFIGURATIONS
        catalog = validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"), configuration=configuration) if multi else None
        images = catalog["images"] if multi else []
        roles = configuration_roots(configuration)
        category = artifact_category(configuration)
        if (type(build.get("schema_version")) is not int or type(provenance.get("schema_version")) is not int
                or build.get("schema_version") != (2 if multi else 1) or provenance.get("schema_version") != (2 if multi else 1)):
            raise Core0Error("build/provenance schema differs from selected configuration")
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
        validate_image_case_provenance(build, provenance, configuration=configuration, images=images)
        validate_managed_provenance(build, provenance, configuration=configuration, images=images)
        if build.get("startup_case") != case or provenance.get("startup_case") != case or build.get("user_startup_case") != user_case or provenance.get("user_startup_case") != user_case:
            raise Core0Error("build/provenance generated startup case differs")
        generated = (["startup.S", "link.ld", "layout.json", "primitive-catalog.json", "boot-package.S", "package-contract.json", "user-image-catalog.json"]
                     + [image["directory"] + "/" + name for image in images for name in ("startup.S", "link.ld", "layout.json", "primitive-catalog.json")]) if multi else list(BOOT_FILES)
        linked = {"boot": list(BOOT_OBJECTS), **({"users": {image["key"]: [image["directory"] + "/startup.o", image["directory"] + "/program.o"] for image in images}} if multi else {"user": list(USER_OBJECTS)})}
        contracts = {role: CONTRACTS[role] for role in roles}
        if multi:
            contracts["users"] = {image["key"]: CONTRACTS["user"] for image in images}
        if provenance.get("unit_contracts") != contracts:
            raise Core0Error("exact selected per-unit contract inventory differs")
        if provenance.get("generated_by_lean") != generated or provenance.get("linked_inputs") != linked:
            raise Core0Error("unexpected code-generation or linked-object closure")
        artifacts = _object(provenance.get("artifacts"), "artifact hashes")
        for name, digest in artifacts.items():
            path = output_dir / name
            if path.resolve().parent != output_dir.resolve() and output_dir.resolve() not in path.resolve().parents:
                raise Core0Error("artifact path escapes output")
            if not isinstance(digest, str) or not path.is_file() or sha256(path) != digest:
                raise Core0Error(f"missing/stale artifact: {name}")
        mandatory = set(generated) | set(BOOT_OBJECTS) | {"image.elf", "image.map", "platform.dtb", "platform.dts"}
        mandatory |= {role + "/" + name for role in roles for name in (*UNIT_FILES, "program.opt.ll")}
        if multi:
            mandatory |= {image["directory"] + "/" + name for image in images for name in
                          (*UNIT_FILES, "Export.lean", "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map", "text.bin", "data.bin")}
        else:
            mandatory |= set(USER_OBJECTS) | {"user/image.elf", "user/image.map", "user-text.bin", "user-data.bin"}
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
            allowed = development_modules(configuration, role)
            closure = module_closure(root, module, allow_development=bool(allowed), development_modules=allowed)
            if any("/Development/" in path and path not in {selected.replace(".", "/") + ".lean" for selected in allowed} for path in closure):
                raise Core0Error("dependency imports another configuration's development module")
            if closure != provenance.get("target_module_closures", {}).get(role):
                raise Core0Error("production import closure missing/stale")
        if multi:
            expected_users = {image["key"]: module_closure(root, image["module"], allow_development=True,
                              forbid_user_privileged_imports=configuration == "capabilities-development") for image in images}
            if configuration == "capabilities-development" and any(path.startswith(("Lemma/Kernel/", "Lemma/Compiler/")) for closure in expected_users.values() for path in closure):
                raise Core0Error("managed user target dependency closure contains privileged/compiler code")
            if any("/Development/" in path and path != image["module"].replace(".", "/") + ".lean"
                   for image in images for path in expected_users[image["key"]]):
                raise Core0Error("per-image dependency imports another development module")
            if provenance.get("target_module_closures") != {**{role: module_closure(root, module, allow_development=development_role(configuration, role), development_modules=development_modules(configuration, role)) for role, module in configuration_modules(configuration).items()}, "users": expected_users}:
                raise Core0Error("exact full per-image source dependency inventory differs")
        command_rows = _array(provenance.get("commands"), "build commands")
        if not command_rows or any(not isinstance(row, dict) or row.get("returncode") != 0 for row in command_rows):
            raise Core0Error("build command corpus empty, malformed or failed")
        lake_commands = [row["argv"][0] for row in command_rows if isinstance(row.get("argv"), list)
                         and row["argv"] and Path(row["argv"][0]).name == "lake"]
        if not lake_commands or any(not path.startswith(lean_pin["store_path"] + "/") for path in lake_commands):
            raise Core0Error("genuine Lean elaboration must use the immutable pinned Lake executable")
        nix_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                        and row["argv"] and Path(row["argv"][0]).name == "nix"]
        if nix_commands != [["build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION],
                            ["path-info", "--json", lean_pin["source_path"]]]:
            raise Core0Error("Lean source realization command evidence is missing or differs")
        compile_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                            and row["argv"] and Path(row["argv"][0]).name in {"llc", "opt", "ld.lld", "clang", "clang-20", "llvm-objcopy"}
                            and row["argv"][1:] != ["--version"]]
        expected_commands = []
        for _role in roles:
            expected_commands += [["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"],
                                  [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"]]
        if multi:
            for image in images:
                expected_commands += [["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"],
                                      [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"]]
            for image in images:
                d = image["directory"]
                expected_commands += [[*STARTUP_ARGUMENTS, d + "/startup.S", "-o", d + "/startup.o"],
                                      ["-m", "elf64lriscv", "--no-relax", "-T", d + "/link.ld", "-Map=" + d + "/image.map", d + "/startup.o", d + "/program.o", "-o", d + "/image.elf"],
                                      ["-O", "binary", "--only-section=.text", d + "/image.elf", d + "/text.bin"],
                                      ["-O", "binary", "--only-section=.data", d + "/image.elf", d + "/data.bin"]]
            expected_commands += [[*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"],
                                  [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"],
                                  ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"]]
        else:
            expected_commands += [[*STARTUP_ARGUMENTS, "user-startup.S", "-o", "user/startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "user-link.ld", "-Map=user/image.map", *USER_OBJECTS, "-o", "user/image.elf"],
                              ["-O", "binary", "--only-section=.text", "user/image.elf", "user-text.bin"],
                              ["-O", "binary", "--only-section=.data", "user/image.elf", "user-data.bin"],
                              [*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"],
                              [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"]]
        if multi:
            validate_multi_commands(command_rows, root=root, output_dir=output_dir, images=images, optimization=optimization, roles=roles, standalone=False, configuration=configuration)
        if compile_commands != expected_commands:
            raise Core0Error("actual compiler/link command closure differs")
        for map_file, allowed in ((("image.map", BOOT_OBJECTS),) if multi else (("image.map", BOOT_OBJECTS), ("user/image.map", USER_OBJECTS))):
            objects = set(re.findall(r"([^\s()]+\.o)(?=[:(\s])", (output_dir / map_file).read_text()))
            if objects != set(allowed):
                raise Core0Error(f"actual linked input map differs: {map_file}: {sorted(objects)}")
        units = {role: validate_unit(load_json(output_dir / role / "unit.json"), role, configuration=configuration) for role in roles}
        layout = validate_layout(load_json(output_dir / "layout.json"), configuration=configuration)
        expected_machine = validate_catalog(load_json(output_dir / "primitive-catalog.json"), configuration=configuration, stage=stage)
        validate_platform_evidence(sha256(output_dir / "platform.dtb"), (output_dir / "platform.dts").read_text())
        ir = {role: {kind: validate_ir((output_dir / role / filename).read_text(), unit, optimized=kind == "optimized")
                     for kind, filename in (("pre", "program.ll"), ("optimized", "program.opt.ll"))} for role, unit in units.items()}
        task_stack = validate_owned_task_stack(layout, units["kernel"], (output_dir / "kernel/program.ll").read_text())
        managed_capabilities = (validate_managed_capability_graph(units["kernel"], (output_dir / "kernel/program.ll").read_text())
                                if configuration == "capabilities-development" else None)
        object_functions = {
            "startup.o": expected_machine, "boot-package.o": set(),
            **({} if multi else {"user/startup.o": {row["symbol"] for row in user_primitive_rows(user_case)}}),
            **{role + "/program.o": set(ir[role]["optimized"]["definitions"]) for role in roles},
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
                if configuration == "capabilities-development":
                    inspect("llvm-objcopy", ["-O", "binary", "--only-section=.rodata", object_file, "audit-kernel-h-rodata.bin"], "h-rodata-extract")
                    table_report = validate_h_readonly_sections(
                        (output_dir / ("audit-" + label + "-sections.txt")).read_text(), object_symbols,
                        (output_dir / ("audit-" + label + "-relocations.txt")).read_text(),
                        (output_dir / "audit-kernel-pmp-table.bin").read_bytes(),
                        (output_dir / "audit-kernel-h-rodata.bin").read_bytes(), object_file=object_file, tables=tables)
                else:
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
        startup = (output_dir / "startup.S").read_text()
        user_source = output_dir / (images[0]["directory"] + "/startup.S" if multi else "user-startup.S")
        user_startup = user_source.read_text()
        user_audits = {image["key"]: audit_user_image(root=root, output_dir=output_dir / image["directory"], catalog=catalog,
                                                   image_key=image["key"], optimization=optimization, timeout_seconds=timeout_seconds)
                       for image in images}
        for value in user_audits.values():
            logs.extend(value["commands"])
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
        specs = [("boot", "image.elf", expected_machine | {row["symbol"] for role in ("firmware", "kernel") for row in units[role]["functions"]}, False)]
        if not multi:
            specs.append(("user", "user/image.elf", {row["symbol"] for row in user_primitive_rows(user_case)} | set(ir["user"]["optimized"]["definitions"]), True))
        for name, image_file, expected, user in specs:
            info, symbol_text, raw_machine, ranges = inspect_linked_elf(inspect, name=name, image=image_file, expected=expected,
                                                                      layout=layout, user=user, assembly=user_startup, user_case=user_case)
            inspections[name] = info
            if not user:
                machine = (output_dir / "audit-boot-disassembly.txt").read_text()
                info["startup"] = validate_startup_case(machine, ranges, case)
                root_symbol = (load_json(output_dir / images[0]["directory"] / "unit.json")["roots"][0]["symbol"] if multi else units["user"]["roots"][0]["symbol"])
                info["context_abi"] = validate_context_abi(startup, raw_machine, ranges, user_startup, root_symbol, user_case)
            else:
                initialized = validate_user_abi_data(inspect("llvm-readelf", ["-S", "--wide", image_file], "user-sections"),
                                                     (output_dir / "user-data.bin").read_bytes(), symbol_text, user_startup, object_file=image_file)
                if user_abi_object is None or initialized["sha256"] != user_abi_object["sha256"]:
                    raise Core0Error("linked user initializer differs from its accounted startup object")
                info["initialized_data"] = initialized
        if multi:
            inspections["users"] = {key: value["elf"] for key, value in user_audits.items()}
        package_contract = validate_package_contract(load_json(output_dir / "package-contract.json"), configuration=configuration, catalog=catalog)
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=.boot_package", "image.elf", "audit-package.bin"], "package-extract")
        if multi:
            payloads = [((output_dir / image["directory"] / "text.bin").read_bytes(), (output_dir / image["directory"] / "data.bin").read_bytes()) for image in images]
            package_images = validate_package_payloads((output_dir / "audit-package.bin").read_bytes(), package_contract, payloads)
        else:
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
        record = {"schema_version": 2 if multi else 1, "status": "PASS", "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                  "stage": stage, "optimization": optimization, "source_commit": provenance["source_commit"],
                  "dirty_paths": provenance["dirty_paths"], "image_sha256": sha256(output_dir / "image.elf"),
                  "lean_source_realization": realization,
                  "boot_package_sha256": sha256(output_dir / "audit-package.bin"),
                  "unit_ir": ir, "readonly_optimizer_object_sections": readonly_objects, "elf": inspections, "commands": logs,
                  "stack_bounds": {"capacities": capacities, "roles": stacks, "dynamic_stack": False},
                  "task_kernel_stack": task_stack,
                  "limitations": ["Artifact/source closure audit, not S/U execution or compiler-correctness proof.",
                                   ("bootstrap-m invokes maintained kernel code in M mode; separately linked user bytes are not yet a running task."
                                    if stage == "bootstrap-m" else "Supervisor artifact audit does not establish a running isolated user task.")]}
        if multi:
            record["user_images"] = {image["key"]: {"id": image["id"], "module": image["module"], "source": image["source"],
                                    **{key: user_audits[image["key"]][key] for key in ("image_sha256", "text_sha256", "data_sha256", "stack_bounds")},
                                    "text_bytes": (output_dir / image["directory"] / "text.bin").stat().st_size,
                                    "data_bytes": (output_dir / image["directory"] / "data.bin").stat().st_size,
                                    **managed_fields(configuration,image),
                                    **({"startup_case": image["startup_case"], "object_quarantined_startup": user_audits[image["key"]]["object_quarantined_startup"]}
                                       if configuration == "tasks-fault-development" else {})} for image in images}
            record["unit_ir"]["users"] = {key: value["unit_ir"] for key, value in user_audits.items()}
            record["stack_bounds"]["roles"]["users"] = {key: value["stack_bounds"] for key, value in user_audits.items()}
            record["package_images"] = package_images
            record["user_image_catalog_sha256"] = sha256(output_dir / "user-image-catalog.json")
            if configuration == "tasks-fault-development":
                record["user_startup_cases"] = {image["key"]: image["startup_case"] for image in images}
            if configuration == "capabilities-development":
                record.update(managed_policy=MANAGED_POLICY, boot_roles={image["key"]: image["boot_role"] for image in images}, managed_capabilities=managed_capabilities)
        else:
            record["user_image_sha256"] = sha256(output_dir / "user/image.elf")
        if source_inputs(root) != source_hashes:
            raise Core0Error("compiler/production source changed during artifact audit")
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
        directory = (root / ns.output_dir).resolve()
        if (directory / "user-build.json").exists():
            if (directory / "build.json").exists():
                raise Core0Error("ambiguous boot/independent-user build category")
            record = audit_standalone_user(root=root, output_dir=directory, timeout_seconds=ns.timeout)
        else:
            record = audit(root=root, output_dir=directory, timeout_seconds=ns.timeout)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"KERNEL AUDIT FAIL: {error}", file=sys.stderr)
        return 1
    print(f"KERNEL AUDIT PASS: {record['stage']}, {record['optimization']}; source {record['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
