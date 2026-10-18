#!/usr/bin/env python3
"""Fail-closed LLVM/object/ELF closure audit for the Core0 RV64 image."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import audit_device
import audit_memory
import audit_monitor
import audit_timer
import audit_trap
from build_core0 import LINK_ARGUMENTS, LLC_ARGUMENTS, STARTUP_ARGUMENTS
from core0_common import Core0Error, checked, load_json, repo_root, require_tools, sha256, write_json


REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "core0-manifest.json",
    "core0-normalized.txt",
    "symbols.txt",
    "provenance.json",
)

SCALAR_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "scalar-suite-manifest.json",
    "scalar-suite-normalized.txt",
    "scalar-test-abi.json",
    "symbols.txt",
    "provenance.json",
)

BOUNDED_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "bounded-suite-manifest.json",
    "bounded-suite-normalized.txt",
    "scalar-test-abi.json",
    "symbols.txt",
    "provenance.json",
)

MEMORY_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "memory-fixtures.json",
    "memory-suite-manifest.json",
    "memory-suite-normalized.txt",
    "memory-test-abi.json",
    "symbols.txt",
    "provenance.json",
)

DEVICE_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "device-contract.json",
    "device-suite-manifest.json",
    "device-suite-normalized.txt",
    "device-test-abi.json",
    "symbols.txt",
    "provenance.json",
)

TRAP_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "device-contract.json",
    "trap-suite-manifest.json",
    "trap-suite-normalized.txt",
    "trap-test-abi.json",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
    "provenance.json",
)

TIMER_SUITE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "device-contract.json",
    "timer-suite-manifest.json",
    "timer-suite-normalized.txt",
    "timer-test-abi.json",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
    "provenance.json",
)

MONITOR_IMAGE_REQUIRED_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "device-contract.json",
    "monitor-manifest.json",
    "monitor-normalized.txt",
    "monitor-abi.json",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
    "provenance.json",
)

RELEASE_POLICY = "release"
TEST_COMPILER_CONTROL_POLICY = "test-compiler-control"
TEST_COMPILER_MUTANT_POLICY = "test-compiler-mutant"
TEST_FRONTEND_SUITE_POLICY = "test-frontend-suite"
TEST_CFG_SUITE_POLICY = "test-cfg-suite"
TEST_LOOP_SUITE_POLICY = "test-loop-suite"
TEST_MEMORY_SUITE_POLICY = "test-memory-suite"
TEST_DEVICE_SUITE_POLICY = "test-device-suite"
TEST_TRAP_SUITE_POLICY = "test-trap-suite"
TEST_TIMER_SUITE_POLICY = "test-timer-suite"
TEST_MONITOR_IMAGE_POLICY = "test-monitor-image"
SCALAR_SUITE_POLICIES = frozenset(
    {TEST_FRONTEND_SUITE_POLICY, TEST_CFG_SUITE_POLICY, TEST_LOOP_SUITE_POLICY}
)
DISPATCH_SUITE_POLICIES = frozenset(
    {*SCALAR_SUITE_POLICIES, TEST_MEMORY_SUITE_POLICY}
)
STACK_SIZE_POLICIES = frozenset(
    {
        TEST_LOOP_SUITE_POLICY,
        TEST_MEMORY_SUITE_POLICY,
        TEST_DEVICE_SUITE_POLICY,
        TEST_TRAP_SUITE_POLICY,
        TEST_TIMER_SUITE_POLICY,
        TEST_MONITOR_IMAGE_POLICY,
    }
)
AUDIT_POLICIES = (
    RELEASE_POLICY,
    TEST_COMPILER_CONTROL_POLICY,
    TEST_COMPILER_MUTANT_POLICY,
    TEST_FRONTEND_SUITE_POLICY,
    TEST_CFG_SUITE_POLICY,
    TEST_LOOP_SUITE_POLICY,
    TEST_MEMORY_SUITE_POLICY,
    TEST_DEVICE_SUITE_POLICY,
    TEST_TRAP_SUITE_POLICY,
    TEST_TIMER_SUITE_POLICY,
    TEST_MONITOR_IMAGE_POLICY,
)
COMPILER_MUTATION_ARTIFACT = "compiler-mutation.json"
COMPILER_MUTATION_STAGE = "structured-llvm-pre-optimization"
COMPILER_MUTATION_FAULTS = frozenset(
    {
        "ult-as-ule",
        "ult-as-slt",
        "add-as-sub",
        "zext-as-sext",
        "trunc-high-half",
        "swap-call-args",
    }
)
MUTANT_CONTROL_IDENTICAL_ARTIFACTS = (
    "startup.S",
    "link.ld",
    "layout.json",
    "core0-manifest.json",
    "core0-normalized.txt",
    "symbols.txt",
)

FORBIDDEN_SYMBOL = re.compile(
    r"(^|[^A-Za-z0-9_])(lean_|malloc|calloc|realloc|free|memcpy|memmove|memset|"
    r"pthread|uv_|__div|__mod|__muldi3|__udiv|__umod|__atomic|__stack_chk)",
    re.IGNORECASE,
)
FORBIDDEN_IR_FLAGS = re.compile(r"\b(?:nsw|nuw|inbounds|disjoint)\b")
ALLOWED_EXTERNALS = {"core0_io_fence"}
ALLOWED_RELOCATIONS = {
    "R_RISCV_CALL_PLT",
    "R_RISCV_PCREL_HI20",
    "R_RISCV_PCREL_LO12_I",
}
SCALAR_O2_JUMP_TABLE_RELOCATION = "R_RISCV_64"
DEVICE_O2_JUMP_TABLE_RELOCATIONS = 23
TRAP_O2_JUMP_TABLE_RELOCATIONS = 23
TIMER_O2_JUMP_TABLE_RELOCATIONS = 43
EXPECTED_LINK_COMMAND = ["ld.lld", *LINK_ARGUMENTS, "-o", "image.elf", "startup.o", "program.o"]
EXPECTED_STARTUP_COMMAND = ["clang", *STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"]
EXPECTED_MACHINE_PRIMITIVES = [
    {
        "identity": "startup",
        "effect": "machine-state",
        "implementation": "Lemma.Machine.Primitives.startup",
    },
    {
        "identity": "io-fence",
        "effect": "ordered-mmio",
        "implementation": "Lemma.Machine.Primitives.ioFence",
    },
    {
        "identity": "uart16550",
        "effect": "bounded-ordered-mmio",
        "implementation": "Lemma.Machine.Harness.uartPutc/uartDrain",
    },
    {
        "identity": "runtime-input",
        "effect": "fixed-memory-read",
        "implementation": "Lemma.Machine.Harness.main",
    },
    {
        "identity": "sifive-test",
        "effect": "vm-termination-mmio",
        "implementation": "Lemma.Machine.Harness.exitSuccess/exitFailure",
    },
]
EXPECTED_SCALAR_MACHINE_PRIMITIVES = [
    {
        "identity": "startup",
        "effect": "machine-state",
        "implementation": "Lemma.Machine.Primitives.startup",
    },
    {
        "identity": "io-fence",
        "effect": "ordered-mmio",
        "implementation": "Lemma.Machine.Primitives.ioFence",
    },
    {
        "identity": "uart16550",
        "effect": "bounded-ordered-mmio",
        "implementation": "Lemma.Machine.Harness.uartPutc/uartDrain",
    },
    {
        "identity": "typed-runtime-input",
        "effect": "fixed-memory-read",
        "implementation": "Lemma.Machine.ScalarHarness.main",
    },
    {
        "identity": "sifive-test",
        "effect": "vm-termination-mmio",
        "implementation": "Lemma.Machine.Harness.exitSuccess/exitFailure",
    },
]
EXPECTED_DEVICE_MACHINE_PRIMITIVES = [
    {
        "identity": "startup",
        "effect": "machine-state",
        "implementation": "Lemma.Machine.Primitives.startup",
    },
    {
        "identity": "io-fence",
        "effect": "ordered-mmio",
        "implementation": "Lemma.Machine.Primitives.ioFence",
    },
    {
        "identity": "device-test-harness",
        "effect": "action-abi/status-coded-vm-termination",
        "implementation": "Lemma.Machine.DeviceHarness.main",
    },
    {
        "identity": "sifive-test",
        "effect": "vm-termination-mmio",
        "implementation": "Lemma.Machine.DeviceHarness.successBlock/failureBlock",
    },
]
MACHINE_IR_FUNCTIONS = {
    "core0_exit_failure",
    "core0_exit_success",
    "core0_uart_putc",
    "core0_uart_drain",
    "core0_put_hex64",
    "core0_main",
}
DEVICE_MACHINE_IR_FUNCTIONS = {"core0_main"}
DEVICE_MACHINE_ACCESS_SEQUENCE = (
    ("uart.lsr.read8", "core0_action_0", "lbu", 0x10000005),
    ("uart.thr.write8", "core0_action_0", "sb", 0x10000000),
    ("uart.lsr.read8", "core0_action_5", "lbu", 0x10000005),
    ("uart.rbr.read8", "core0_action_5", "lbu", 0x10000000),
    ("uart.lsr.read8", "core0_action_21", "lbu", 0x10000005),
    ("uart.fcr.enable-reset", "core0_action_24", "sb", 0x10000002),
)
DEVICE_MACHINE_DENIED_METADATA = Counter({
    "core0_action_8": 1,
    "core0_action_11": 1,
    "core0_action_13": 2,
    "core0_action_14": 2,
    "core0_action_15": 5,
    "core0_action_18": 1,
    "core0_action_20": 6,
})
TRAP_MACHINE_ACCESS_SEQUENCE = (
    ("uart.lsr.read8", "core0_action_0", "lbu", 0x10000005),
    ("uart.thr.write8", "core0_action_0", "sb", 0x10000000),
    ("uart.lsr.read8", "core0_action_12", "lbu", 0x10000005),
    ("uart.fcr.enable-reset", "core0_action_19", "sb", 0x10000002),
)
TRAP_MACHINE_DENIED_METADATA = Counter({
    "core0_action_5": 1,
    "core0_action_7": 12,
    "core0_action_9": 4,
    "core0_action_10": 1,
    "core0_action_17": 1,
    "core0_action_19": 3,
    "core0_action_22": 2,
})
TIMER_MACHINE_ACCESS_SEQUENCE = (
    ("uart.lsr.read8", "core0_action_0", "lbu", 0x10000005),
    ("uart.thr.write8", "core0_action_0", "sb", 0x10000000),
    ("uart.lsr.read8", "core0_action_13", "lbu", 0x10000005),
    ("uart.fcr.enable-reset", "core0_action_35", "sb", 0x10000002),
)
TIMER_MACHINE_DENIED_METADATA = Counter({
    "core0_action_5": 1,
    "core0_action_8": 1,
    "core0_action_16": 1,
    "core0_action_35": 4,
})
FINAL_ALLOC_SECTIONS = {".text", ".rodata", ".data", ".bss"}
LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
LLVM_IDENTIFIER = re.compile(r"[A-Za-z_.$][A-Za-z0-9_.$-]*")

SCALAR_TEST_ABI = "lemma-scalar-test-v1"
SCALAR_EXPORT_DRIVER = "examples/foundation/ScalarBuild.lean"
CFG_SCALAR_EXPORT_DRIVER = "examples/foundation/ScalarV2Build.lean"
LOOP_SCALAR_EXPORT_DRIVER = "examples/foundation/BoundedBuild.lean"
MEMORY_EXPORT_DRIVER = "examples/foundation/MemoryBuild.lean"
DEVICE_EXPORT_DRIVER = "examples/foundation/DeviceBuild.lean"
SCALAR_BASE = "Lemma.Examples.Foundation.Conformance"
SCALAR_SUPPORT = f"{SCALAR_BASE}.Support"
SCALAR_ABI_ROOT = f"{SCALAR_BASE}.abiNoInlineRoot"
SCALAR_ABI_CALLEE = f"{SCALAR_SUPPORT}.abiNoInlineCallee"

# This is deliberately independent of the corpus generator.  The audit accepts
# exactly the reviewed Gate 2 declaration closure, in dependency-first order;
# changing the generated corpus does not silently change this allowlist.
SCALAR_FUNCTION_CONTRACTS: tuple[
    tuple[str, tuple[str, ...], str, tuple[str, ...]], ...
] = (
    (f"{SCALAR_BASE}.constantU64", (), "u64", ()),
    (f"{SCALAR_BASE}.boolEq", ("bool", "bool"), "bool", ()),
    (f"{SCALAR_BASE}.boolSelect", ("bool", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.u8Add", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8Sub", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8Mul", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8And", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8Or", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8Xor", ("u8", "u8"), "u8", ()),
    (f"{SCALAR_BASE}.u8Eq", ("u8", "u8"), "bool", ()),
    (f"{SCALAR_BASE}.u8Lt", ("u8", "u8"), "bool", ()),
    (f"{SCALAR_BASE}.u8Le", ("u8", "u8"), "bool", ()),
    (f"{SCALAR_BASE}.u32Arithmetic", ("u32", "u32", "u32"), "u32", ()),
    (f"{SCALAR_BASE}.u32Bits", ("u32", "u32", "u32"), "u32", ()),
    (f"{SCALAR_BASE}.u32Comparisons", ("u32", "u32", "u32"), "u32", ()),
    (f"{SCALAR_BASE}.u64Arithmetic", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.u64Bits", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.u64Comparisons", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.u8ToU32", ("u8",), "u32", ()),
    (f"{SCALAR_BASE}.u8ToU64", ("u8",), "u64", ()),
    (f"{SCALAR_BASE}.u32ToU8", ("u32",), "u8", ()),
    (f"{SCALAR_BASE}.u32ToU64", ("u32",), "u64", ()),
    (f"{SCALAR_BASE}.u64ToU8", ("u64",), "u8", ()),
    (f"{SCALAR_BASE}.u64ToU32", ("u64",), "u32", ()),
    (f"{SCALAR_SUPPORT}.mixedLeaf", ("bool", "u8", "u32", "u64"), "u64", ()),
    (
        f"{SCALAR_BASE}.mixedWidthCall",
        ("bool", "u8", "u32", "u64"),
        "u64",
        (f"{SCALAR_SUPPORT}.mixedLeaf",),
    ),
    (f"{SCALAR_SUPPORT}.sharedLeaf", ("u64", "u64"), "u64", ()),
    (
        f"{SCALAR_SUPPORT}.sharedLeft",
        ("u64", "u64"),
        "u64",
        (f"{SCALAR_SUPPORT}.sharedLeaf",),
    ),
    (
        f"{SCALAR_SUPPORT}.sharedRight",
        ("u64", "u64"),
        "u64",
        (f"{SCALAR_SUPPORT}.sharedLeaf",),
    ),
    (
        f"{SCALAR_BASE}.sharedDiamond",
        ("u64", "u64"),
        "u64",
        (f"{SCALAR_SUPPORT}.sharedLeft", f"{SCALAR_SUPPORT}.sharedRight"),
    ),
    (
        SCALAR_ABI_CALLEE,
        ("u64", "u8", "u32", "bool", "u64", "u8", "u32", "bool", "u8", "u32"),
        "u64",
        (),
    ),
    (
        SCALAR_ABI_ROOT,
        ("u64", "u8", "u32", "bool", "u64", "u8", "u32", "bool", "u8", "u32"),
        "u64",
        (SCALAR_ABI_CALLEE,),
    ),
    (f"{SCALAR_BASE}.metamorphicAlphaOriginal", ("u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.metamorphicAlphaRenamed", ("u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.metamorphicInline", ("u64", "u64"), "u64", ()),
    (f"{SCALAR_SUPPORT}.extractedStep", ("u64", "u64"), "u64", ()),
    (
        f"{SCALAR_BASE}.metamorphicExtracted",
        ("u64", "u64"),
        "u64",
        (f"{SCALAR_SUPPORT}.extractedStep",),
    ),
    (f"{SCALAR_BASE}.metamorphicLetFlat", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.metamorphicLetNested", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.MovedA.metamorphicModule", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.MovedB.metamorphicModule", ("u64", "u64", "u64"), "u64", ()),
    (f"{SCALAR_BASE}.ImportBase.metamorphicImport", ("u32", "u32"), "u32", ()),
    (f"{SCALAR_BASE}.ImportExtra.metamorphicImport", ("u32", "u32"), "u32", ()),
)

# Preserve the exact declaration order from ScalarBuild.lean rather than deriving
# roots from dependency shape (some roots themselves contain direct calls).
SCALAR_ROOT_SOURCES = (
    *(source for source, _args, _result, _deps in SCALAR_FUNCTION_CONTRACTS[:24]),
    f"{SCALAR_BASE}.mixedWidthCall",
    f"{SCALAR_BASE}.sharedDiamond",
    SCALAR_ABI_ROOT,
    *(source for source, _args, _result, _deps in SCALAR_FUNCTION_CONTRACTS[32:35]),
    f"{SCALAR_BASE}.metamorphicExtracted",
    *(source for source, _args, _result, _deps in SCALAR_FUNCTION_CONTRACTS[37:]),
)

CFG_SCALAR_BASE = "Lemma.Examples.Foundation.ScalarV2"
CFG_SCALAR_SUPPORT = f"{CFG_SCALAR_BASE}.Support"
CFG_OPERATION_PARTS = (
    ("Complement", ("single",)),
    ("Shl", ("binary",)),
    ("Shr", ("binary",)),
    ("Div", ("binary",)),
    ("Rem", ("binary",)),
)


def _cfg_primitive_contract_rows() -> tuple[
    tuple[str, tuple[str, ...], str, tuple[str, ...]], ...
]:
    rows: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = []
    for ty in ("u8", "u32", "u64"):
        for operation, shape in CFG_OPERATION_PARTS:
            args = (ty,) if shape == ("single",) else (ty, ty)
            prefix = f"{CFG_SCALAR_BASE}.{ty}{operation}"
            rows.append((prefix + "Notation", args, ty, ()))
            rows.append((prefix + "Direct", args, ty, ()))
    return tuple(rows)


CFG_PRIMITIVE_FUNCTION_CONTRACTS = _cfg_primitive_contract_rows()
CFG_CHOOSE_U8 = f"{CFG_SCALAR_SUPPORT}.chooseU8"
CFG_CHOOSE_U32 = f"{CFG_SCALAR_SUPPORT}.chooseU32"
CFG_CHOOSE_U64 = f"{CFG_SCALAR_SUPPORT}.chooseU64"
CFG_FUNCTION_CONTRACTS = (
    *CFG_PRIMITIVE_FUNCTION_CONTRACTS,
    (CFG_CHOOSE_U8, ("bool", "bool", "u8", "u8", "u8"), "u8", ()),
    (
        f"{CFG_SCALAR_BASE}.cfgBool",
        ("bool", "bool", "u8", "u8", "u8"),
        "bool",
        (CFG_CHOOSE_U8,),
    ),
    (
        f"{CFG_SCALAR_BASE}.cfgU8",
        ("bool", "bool", "u8", "u8", "u8"),
        "u8",
        (CFG_CHOOSE_U8,),
    ),
    (CFG_CHOOSE_U32, ("bool", "bool", "u32", "u32", "u32"), "u32", ()),
    (
        f"{CFG_SCALAR_BASE}.cfgU32",
        ("bool", "bool", "u32", "u32", "u32"),
        "u32",
        (CFG_CHOOSE_U32,),
    ),
    (CFG_CHOOSE_U64, ("bool", "bool", "u64", "u64", "u64"), "u64", ()),
    (
        f"{CFG_SCALAR_BASE}.cfgU64",
        ("bool", "bool", "u64", "u64", "u64"),
        "u64",
        (CFG_CHOOSE_U64,),
    ),
    (
        f"{CFG_SCALAR_BASE}.nestedHelperCall",
        ("bool", "bool", "bool", "u64", "u64", "u64"),
        "u64",
        (CFG_CHOOSE_U64,),
    ),
    (f"{CFG_SCALAR_BASE}.u8LegacyArithmetic", ("u8", "u8", "u8"), "u8", ()),
    (f"{CFG_SCALAR_BASE}.u32LegacyArithmetic", ("u32", "u32", "u32"), "u32", ()),
    (f"{CFG_SCALAR_BASE}.u64LegacyArithmetic", ("u64", "u64", "u64"), "u64", ()),
    (
        f"{CFG_SCALAR_BASE}.u8LegacyCompare",
        ("bool", "bool", "u8", "u8", "u8"),
        "u8",
        (),
    ),
    (
        f"{CFG_SCALAR_BASE}.u32LegacyCompare",
        ("bool", "bool", "u32", "u32", "u32"),
        "u32",
        (),
    ),
    (
        f"{CFG_SCALAR_BASE}.u64LegacyCompare",
        ("bool", "bool", "u64", "u64", "u64"),
        "u64",
        (),
    ),
    (f"{CFG_SCALAR_BASE}.u8LegacyCasts", ("u8",), "u64", ()),
    (f"{CFG_SCALAR_BASE}.u32LegacyCasts", ("u32",), "u64", ()),
    (f"{CFG_SCALAR_BASE}.u64LegacyCasts", ("u64",), "u64", ()),
)
CFG_ROOT_SOURCES = (
    *(row[0] for row in CFG_PRIMITIVE_FUNCTION_CONTRACTS),
    f"{CFG_SCALAR_BASE}.cfgBool",
    f"{CFG_SCALAR_BASE}.cfgU8",
    f"{CFG_SCALAR_BASE}.cfgU32",
    f"{CFG_SCALAR_BASE}.cfgU64",
    f"{CFG_SCALAR_BASE}.nestedHelperCall",
    f"{CFG_SCALAR_BASE}.u8LegacyArithmetic",
    f"{CFG_SCALAR_BASE}.u32LegacyArithmetic",
    f"{CFG_SCALAR_BASE}.u64LegacyArithmetic",
    f"{CFG_SCALAR_BASE}.u8LegacyCompare",
    f"{CFG_SCALAR_BASE}.u32LegacyCompare",
    f"{CFG_SCALAR_BASE}.u64LegacyCompare",
    f"{CFG_SCALAR_BASE}.u8LegacyCasts",
    f"{CFG_SCALAR_BASE}.u32LegacyCasts",
    f"{CFG_SCALAR_BASE}.u64LegacyCasts",
)
CFG_USED_PRIMITIVES = frozenset(
    {
        *(
            f"{ty}.{op}"
            for ty in ("u8", "u32", "u64")
            for op in (
                "add",
                "sub",
                "mul",
                "and",
                "or",
                "xor",
                "ult",
                "ule",
                "eq",
                "complement",
                "shl",
                "lshr",
                "udiv",
                "urem",
            )
        ),
        "bool.eq",
        "u8.to-u32.zext",
        "u8.to-u64.zext",
        "u32.to-u8.trunc",
        "u32.to-u64.zext",
        "u64.to-u8.trunc",
        "u64.to-u32.trunc",
    }
)


def expected_program_command(
    optimization: str, policy: str = RELEASE_POLICY
) -> list[str]:
    return [
        "llc",
        *LLC_ARGUMENTS,
        *(
            ["-stack-size-section"]
            if policy in STACK_SIZE_POLICIES
            else []
        ),
        f"-{optimization}",
        "program.opt.ll",
        "-o",
        "program.o",
    ]


def _primitive_contracts() -> dict[str, dict[str, object]]:
    contracts: dict[str, dict[str, object]] = {}
    direct_names = {
        "u8": "UInt8",
        "u32": "UInt32",
        "u64": "UInt64",
    }
    operation_names = {
        "add": "add",
        "sub": "sub",
        "mul": "mul",
        "and": "land",
        "or": "lor",
        "xor": "xor",
    }
    for ty, lean_ty in direct_names.items():
        for stable_op, lean_op in operation_names.items():
            stable_id = f"{ty}.{stable_op}"
            contracts[stable_id] = {
                "stable_id": stable_id,
                "lean_identities": [f"{lean_ty}.{lean_op}"],
                "signature": {"args": [ty, ty], "result": ty},
                "effect": "pure",
            }
        for stable_op, lean_op in (("ult", "lt"), ("ule", "le")):
            stable_id = f"{ty}.{stable_op}"
            contracts[stable_id] = {
                "stable_id": stable_id,
                "lean_identities": [f"{lean_ty}.{lean_op}"],
                "signature": {"args": [ty, ty], "result": "bool"},
                "effect": "pure",
            }
        stable_id = f"{ty}.eq"
        contracts[stable_id] = {
            "stable_id": stable_id,
            "lean_identities": ["Eq"],
            "signature": {"args": [ty, ty], "result": "bool"},
            "effect": "pure",
        }
    contracts["bool.eq"] = {
        "stable_id": "bool.eq",
        "lean_identities": ["Eq"],
        "signature": {"args": ["bool", "bool"], "result": "bool"},
        "effect": "pure",
    }
    conversions = (
        ("u8", "u32", "zext", "UInt8.toUInt32"),
        ("u8", "u64", "zext", "UInt8.toUInt64"),
        ("u32", "u8", "trunc", "UInt32.toUInt8"),
        ("u32", "u64", "zext", "UInt32.toUInt64"),
        ("u64", "u8", "trunc", "UInt64.toUInt8"),
        ("u64", "u32", "trunc", "UInt64.toUInt32"),
    )
    for source, target, operation, identity in conversions:
        stable_id = f"{source}.to-{target}.{operation}"
        contracts[stable_id] = {
            "stable_id": stable_id,
            "lean_identities": [identity],
            "signature": {"args": [source], "result": target},
            "effect": "pure",
        }
    return contracts


PRIMITIVE_CONTRACTS = _primitive_contracts()


def _primitive_contracts_v02() -> dict[str, dict[str, object]]:
    contracts = dict(PRIMITIVE_CONTRACTS)
    for ty, lean_ty in (("u8", "UInt8"), ("u32", "UInt32"), ("u64", "UInt64")):
        for stable_op, lean_op in (
            ("shl", "shiftLeft"),
            ("lshr", "shiftRight"),
            ("udiv", "div"),
            ("urem", "mod"),
        ):
            stable_id = f"{ty}.{stable_op}"
            contracts[stable_id] = {
                "stable_id": stable_id,
                "lean_identities": [f"{lean_ty}.{lean_op}"],
                "signature": {"args": [ty, ty], "result": ty},
                "effect": "pure",
            }
        stable_id = f"{ty}.complement"
        contracts[stable_id] = {
            "stable_id": stable_id,
            "lean_identities": [f"{lean_ty}.complement"],
            "signature": {"args": [ty], "result": ty},
            "effect": "pure",
        }
    return contracts


PRIMITIVE_CONTRACTS_V02 = _primitive_contracts_v02()


LOOP_BASE = "Lemma.Examples.Foundation.Bounded"
LOOP_SUPPORT = f"{LOOP_BASE}.Support"
LOOP_FUNCTION_CONTRACTS: dict[
    str, tuple[tuple[str, ...], str, tuple[str, ...]]
] = {
    f"{LOOP_BASE}.sumStep": (("u32", "u32"), "u32", ()),
    f"{LOOP_BASE}.sumFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.sumStep",),
    ),
    f"{LOOP_BASE}.sumChangedStep": (("u32", "u32"), "u32", ()),
    f"{LOOP_BASE}.sumFoldChanged": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.sumChangedStep",),
    ),
    f"{LOOP_BASE}.bitMixStep": (("u32", "u32"), "u32", ()),
    f"{LOOP_BASE}.bitMixFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.bitMixStep",),
    ),
    f"{LOOP_SUPPORT}.nestedInnerStep": (("u32", "u32"), "u32", ()),
    f"{LOOP_BASE}.nestedOuterStep": (
        ("u32", "u32"), "u32", (f"{LOOP_SUPPORT}.nestedInnerStep",),
    ),
    f"{LOOP_BASE}.nestedFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.nestedOuterStep",),
    ),
    f"{LOOP_SUPPORT}.helperMix": (("u32", "u32"), "u32", ()),
    f"{LOOP_BASE}.helperStep": (
        ("u32", "u32"), "u32", (f"{LOOP_SUPPORT}.helperMix",),
    ),
    f"{LOOP_BASE}.helperFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.helperStep",),
    ),
    f"{LOOP_BASE}.zeroBudgetFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.sumStep",),
    ),
    f"{LOOP_BASE}.maxBudgetFold": (
        ("u32", "u32"), "u64", (f"{LOOP_BASE}.sumStep",),
    ),
}
LOOP_FUNCTION_BODIES = {
    f"{LOOP_BASE}.sumStep": "(bin add u32 (var 1 u32) (var 0 u32))",
    f"{LOOP_BASE}.sumFold": (
        f"(bounded-fold-u32 budget=16 callback={LOOP_BASE}.sumStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_BASE}.sumChangedStep": (
        "(bin add u32 (bin add u32 (var 1 u32) (var 0 u32)) (lit u32 1))"
    ),
    f"{LOOP_BASE}.sumFoldChanged": (
        f"(bounded-fold-u32 budget=16 callback={LOOP_BASE}.sumChangedStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_BASE}.bitMixStep": (
        "(let 2 count u32 (bin and u32 (bin add u32 (var 0 u32) (lit u32 5)) "
        "(lit u32 31)) (bin add u32 (bin shl u32 (bin xor u32 (var 1 u32) "
        "(var 0 u32)) (var 2 u32)) (lit u32 1831565813)))"
    ),
    f"{LOOP_BASE}.bitMixFold": (
        f"(bounded-fold-u32 budget=64 callback={LOOP_BASE}.bitMixStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_SUPPORT}.nestedInnerStep": (
        "(bin add u32 (bin add u32 (var 1 u32) (var 0 u32)) (lit u32 3))"
    ),
    f"{LOOP_BASE}.nestedOuterStep": (
        f"(cast trunc u64 u32 (bounded-fold-u32 budget=16 callback="
        f"{LOOP_SUPPORT}.nestedInnerStep count=(var 0 u32) initial=(var 1 u32)))"
    ),
    f"{LOOP_BASE}.nestedFold": (
        f"(bounded-fold-u32 budget=16 callback={LOOP_BASE}.nestedOuterStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_SUPPORT}.helperMix": (
        "(let 2 multiplied u32 (bin mul u32 (var 0 u32) (lit u32 2654435769)) "
        "(bin add u32 (bin xor u32 (var 1 u32) (var 2 u32)) (lit u32 2135587861)))"
    ),
    f"{LOOP_BASE}.helperStep": (
        f"(call {LOOP_SUPPORT}.helperMix u32 [(var 0 u32) (var 1 u32)])"
    ),
    f"{LOOP_BASE}.helperFold": (
        f"(bounded-fold-u32 budget=64 callback={LOOP_BASE}.helperStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_BASE}.zeroBudgetFold": (
        f"(bounded-fold-u32 budget=0 callback={LOOP_BASE}.sumStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
    f"{LOOP_BASE}.maxBudgetFold": (
        f"(bounded-fold-u32 budget=256 callback={LOOP_BASE}.sumStep "
        "count=(var 0 u32) initial=(var 1 u32))"
    ),
}
LOOP_ROOT_SOURCES = (
    f"{LOOP_BASE}.sumFold",
    f"{LOOP_BASE}.sumFoldChanged",
    f"{LOOP_BASE}.bitMixFold",
    f"{LOOP_BASE}.nestedFold",
    f"{LOOP_BASE}.helperFold",
    f"{LOOP_BASE}.zeroBudgetFold",
    f"{LOOP_BASE}.maxBudgetFold",
)
LOOP_USED_PRIMITIVES = frozenset(
    {
        "u32.add",
        "u32.mul",
        "u32.and",
        "u32.xor",
        "u32.shl",
        "u64.to-u32.trunc",
    }
)
LOOP_ITERATION_ORDER = (
    (16, f"{LOOP_BASE}.sumStep"),
    (16, f"{LOOP_BASE}.sumChangedStep"),
    (64, f"{LOOP_BASE}.bitMixStep"),
    (16, f"{LOOP_BASE}.nestedOuterStep"),
    (16, f"{LOOP_SUPPORT}.nestedInnerStep"),
    (64, f"{LOOP_BASE}.helperStep"),
    (0, f"{LOOP_BASE}.sumStep"),
    (256, f"{LOOP_BASE}.sumStep"),
)
LOOP_ITERATION_SITES = frozenset(LOOP_ITERATION_ORDER)

LOOP_OUTCOME_CONTRACT = {
    "type": "u64",
    "success": "zero-extended-u32",
    "exhaustion_tag": "0x8000000000000000",
    "exhaustion_payload": "initial-u32",
    "exhaustion_reserved_bits": "bits32-through62-zero",
    "callbacks_on_exhaustion": 0,
}
LOOP_CONTRACT = {
    "source_identity": "Lemma.Core0.Bounded.boundedFoldU32",
    "stable_id": "u32.bounded-fold",
    "validator": "Lemma.Compiler.LLVM.validateModule",
    "static_budget_type": "Nat",
    "static_budget_form": "canonical-standard-Nat-literal",
    "runtime_count": "u32",
    "counter": {"type": "u32", "order": "ascending-zero-based"},
    "accumulator": "u32",
    "maximum_budget": 256,
    "outcome": LOOP_OUTCOME_CONTRACT,
    "effect": "pure",
}


def _validate_audit_policy(policy: str) -> str:
    if policy not in AUDIT_POLICIES:
        raise Core0Error(
            f"unknown Core0 audit policy {policy!r}; expected one of {AUDIT_POLICIES!r}"
        )
    return policy


def validate_compiler_mutation_manifest(
    value: object, manifest: dict[str, object]
) -> dict[str, object]:
    """Validate the closed, test-only structured-LLVM mutation declaration."""
    if not isinstance(value, dict):
        raise Core0Error("compiler-mutation.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "artifact_category",
            "transform_stage",
            "production_selectable",
            "source_root",
            "fault",
            "target_source",
            "target_llvm",
            "match_count",
            "before",
            "after",
        },
        "compiler mutation manifest",
    )
    mutation_schema = value.get("schema_version")
    if (
        isinstance(mutation_schema, bool)
        or not isinstance(mutation_schema, int)
        or mutation_schema != 1
    ):
        raise Core0Error("compiler mutation manifest has an unsupported schema")
    if value.get("artifact_category") != TEST_COMPILER_MUTANT_POLICY:
        raise Core0Error("compiler mutation manifest has the wrong artifact category")
    if value.get("transform_stage") != COMPILER_MUTATION_STAGE:
        raise Core0Error("compiler mutation manifest has the wrong transform stage")
    if value.get("production_selectable") is not False:
        raise Core0Error("compiler mutation must be explicitly non-production-selectable")
    if value.get("source_root") != manifest.get("root"):
        raise Core0Error("compiler mutation source root differs from the Core0 manifest")

    fault = value.get("fault")
    if not isinstance(fault, str) or fault not in COMPILER_MUTATION_FAULTS:
        raise Core0Error(f"compiler mutation fault is outside the closed allowlist: {fault!r}")
    match_count = value.get("match_count")
    if isinstance(match_count, bool) or not isinstance(match_count, int) or match_count != 1:
        raise Core0Error("compiler mutation must record exactly one matched instruction")

    functions = manifest.get("functions")
    assert isinstance(functions, list)
    source_to_llvm = {
        str(function["source"]): str(function["llvm"])
        for function in functions
        if isinstance(function, dict)
    }
    target_source, target_llvm = value.get("target_source"), value.get("target_llvm")
    if (
        not isinstance(target_source, str)
        or not isinstance(target_llvm, str)
        or source_to_llvm.get(target_source) != target_llvm
    ):
        raise Core0Error(
            "compiler mutation target source/LLVM identity is absent or inconsistent"
        )
    before, after = value.get("before"), value.get("after")
    if (
        not isinstance(before, str)
        or not before
        or not isinstance(after, str)
        or not after
        or before == after
    ):
        raise Core0Error("compiler mutation before/after instructions are missing or unchanged")
    return value


def _expected_mutation_after(fault: str, before: str) -> str:
    replacements = {
        "ult-as-ule": (" = icmp ult ", " = icmp ule "),
        "ult-as-slt": (" = icmp ult ", " = icmp slt "),
        "add-as-sub": (" = add ", " = sub "),
    }
    replacement = replacements.get(fault)
    if replacement is not None:
        old, new = replacement
        if before.count(old) != 1 or "\n" in before or "\r" in before:
            raise Core0Error(f"compiler mutation {fault!r} has the wrong before instruction")
        return before.replace(old, new, 1)
    if fault == "zext-as-sext":
        match = re.fullmatch(
            r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = zext i32 .+ to i64", before
        )
        if match is None or "\n" in before or "\r" in before:
            raise Core0Error("compiler mutation 'zext-as-sext' has the wrong before instruction")
        return before.replace(" = zext ", " = sext ", 1)
    if fault == "trunc-high-half":
        match = re.fullmatch(
            r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = trunc i64 (.+) to i32", before
        )
        if match is None or "\n" in match.group(2) or "\r" in match.group(2):
            raise Core0Error("compiler mutation 'trunc-high-half' has the wrong before instruction")
        result, operand = match.groups()
        shifted = result + "_fault_high"
        return (
            f"%{shifted} = lshr i64 {operand}, 32\n"
            f"%{result} = trunc i64 %{shifted} to i32"
        )
    if fault == "swap-call-args":
        match = re.fullmatch(
            r"(.+ = call [^\s]+ @core0_user_[A-Za-z0-9_.$-]+\()"
            r"([^,()]+), ([^,()]+)(.*\))",
            before,
        )
        if match is None or "\n" in before or "\r" in before:
            raise Core0Error("compiler mutation 'swap-call-args' has the wrong before instruction")
        prefix, first, second, suffix = match.groups()
        first_type = first.split(" ", 1)[0]
        second_type = second.split(" ", 1)[0]
        if first_type != second_type or not first_type:
            raise Core0Error("compiler mutation 'swap-call-args' swaps unequal argument types")
        return f"{prefix}{second}, {first}{suffix}"
    raise Core0Error(f"compiler mutation fault is outside the closed allowlist: {fault!r}")


def validate_compiler_mutation_ir(value: dict[str, object], pre_ir: str) -> None:
    """Bind the mutation report to the exact changed instructions in program.ll."""
    fault = str(value["fault"])
    before = str(value["before"])
    after = str(value["after"])
    expected_after = _expected_mutation_after(fault, before)
    if after != expected_after:
        raise Core0Error(
            f"compiler mutation {fault!r} before/after relationship is malformed"
        )

    target_llvm = str(value["target_llvm"])
    definition = re.compile(
        rf"^define\s+[^\n]*@{re.escape(target_llvm)}\([^\n]*\)[^\n]*\{{\n"
        rf"(?P<body>.*?)^\}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(definition.finditer(pre_ir))
    if len(matches) != 1:
        raise Core0Error(
            "compiler mutation target does not have exactly one program.ll definition"
        )
    body_lines = [line.strip() for line in matches[0].group("body").splitlines()]
    after_lines = after.splitlines()
    occurrence_count = sum(
        body_lines[index : index + len(after_lines)] == after_lines
        for index in range(len(body_lines) - len(after_lines) + 1)
    )
    if occurrence_count != 1:
        raise Core0Error(
            "compiler mutation after-instruction sequence does not occur exactly once "
            "in its target function"
        )
    if before in body_lines:
        raise Core0Error("compiler mutation target still contains its reported before instruction")


def validate_mutant_control_delta(
    value: dict[str, object],
    mutant_ir: str,
    clean_ir: str,
) -> None:
    """Require the reported instruction replacement to be the sole pre-opt IR delta."""
    before = str(value["before"])
    after = str(value["after"])
    rendered_before = "  " + before
    rendered_after = "\n".join("  " + line for line in after.splitlines())
    target_llvm = str(value["target_llvm"])
    definition = re.compile(
        rf"^define\s+[^\n]*@{re.escape(target_llvm)}\([^\n]*\)[^\n]*\{{\n"
        rf"(?P<body>.*?)^\}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    definitions = list(definition.finditer(mutant_ir))
    if len(definitions) != 1:
        raise Core0Error(
            "compiler mutant sole-delta check cannot isolate its target definition"
        )
    match = definitions[0]
    body = match.group("body")
    if body.count(rendered_after) != 1:
        raise Core0Error(
            "compiler mutant does not contain exactly one rendered reported replacement"
        )
    reconstructed_body = body.replace(rendered_after, rendered_before, 1)
    reconstructed = (
        mutant_ir[: match.start("body")]
        + reconstructed_body
        + mutant_ir[match.end("body") :]
    )
    if reconstructed != clean_ir:
        raise Core0Error(
            "compiler mutant has an unreported pre-optimization IR delta from its clean control"
        )


def tool_text(name: str, args: list[str], root: Path) -> str:
    result = checked([name, *args], cwd=root, timeout_seconds=30)
    return result.stdout.decode("utf-8", errors="strict")


_LEXICAL_PARSE_MAX_CHARS = 131072


def _definition_call_sets(ir: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    definitions = frozenset(re.findall(r"^define\s+.*?@([A-Za-z0-9_.$-]+)\(", ir, re.MULTILINE))
    declarations = frozenset(re.findall(r"^declare\s+.*?@([A-Za-z0-9_.$-]+)\(", ir, re.MULTILINE))
    calls = frozenset(re.findall(r"\bcall\s+[^@\n]*@([A-Za-z0-9_.$-]+)\(", ir))
    return definitions, declarations, calls


@lru_cache(maxsize=2048)
def _definition_call_sets_cached(ir: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    # The complete immutable text is the key, including comments and literals.
    # This caches only the original three lexical regex results, never source
    # admission, a validator decision, machine state or execution evidence.
    return _definition_call_sets(ir)


def parse_definitions_and_calls(ir: str) -> tuple[set[str], set[str], set[str]]:
    # Large modules bypass retained storage. Ordinary repeated function bodies
    # fit the bounded cache; fresh sets preserve the original mutable API and
    # prevent one observer from changing another observer's lexical results.
    parsed = (_definition_call_sets_cached(ir) if len(ir) <= _LEXICAL_PARSE_MAX_CHARS
              else _definition_call_sets(ir))
    definitions, declarations, calls = parsed
    return set(definitions), set(declarations), set(calls)


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from the schema: "
            f"missing={sorted(expected - observed)!r}, unexpected={sorted(observed - expected)!r}"
        )


def _validate_signature(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} signature is not an object")
    _exact_keys(value, {"args", "result"}, f"{context} signature")
    args, result = value.get("args"), value.get("result")
    scalar_types = {"bool", "u8", "u32", "u64"}
    if (
        not isinstance(args, list)
        or any(not isinstance(arg, str) or arg not in scalar_types for arg in args)
        or not isinstance(result, str)
        or result not in scalar_types
    ):
        raise Core0Error(f"{context} has an invalid scalar signature")
    return value


def validate_core0_manifest(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("core0-manifest.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "contract_version",
            "root",
            "root_llvm",
            "root_abi",
            "functions",
            "used_primitives",
            "machine_primitives",
        },
        "Core0 target manifest",
    )
    if value.get("schema_version") != 1 or value.get("contract_version") != "core0-v0.1":
        raise Core0Error("Core0 target manifest has an unsupported schema or contract")
    root, root_llvm = value.get("root"), value.get("root_llvm")
    if not isinstance(root, str) or LEAN_IDENTIFIER.fullmatch(root) is None:
        raise Core0Error("Core0 target manifest root is not a valid Lean identity")
    if not isinstance(root_llvm, str) or LLVM_IDENTIFIER.fullmatch(root_llvm) is None:
        raise Core0Error("Core0 target manifest root_llvm is not a valid LLVM symbol")
    root_abi = _validate_signature(value.get("root_abi"), "Core0 target root ABI")
    if root_abi != {"args": ["u64", "u64", "u64"], "result": "u64"}:
        raise Core0Error("Core0 target manifest root ABI is not the freestanding harness ABI")

    functions = value.get("functions")
    if not isinstance(functions, list) or not functions:
        raise Core0Error("Core0 target manifest has an empty or malformed function list")
    seen_sources: set[str] = set()
    seen_symbols: set[str] = set()
    source_to_symbol: dict[str, str] = {}
    for index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(f"Core0 target function #{index} is not an object")
        _exact_keys(
            function,
            {"source", "llvm", "signature", "dependencies", "body"},
            f"Core0 target function #{index}",
        )
        source, symbol = function.get("source"), function.get("llvm")
        dependencies, body = function.get("dependencies"), function.get("body")
        if not isinstance(source, str) or LEAN_IDENTIFIER.fullmatch(source) is None:
            raise Core0Error(f"Core0 target function #{index} has an invalid source identity")
        if not isinstance(symbol, str) or LLVM_IDENTIFIER.fullmatch(symbol) is None:
            raise Core0Error(f"Core0 target function {source} has an invalid LLVM symbol")
        if source in seen_sources or symbol in seen_symbols:
            raise Core0Error("Core0 target manifest has duplicate source or LLVM symbols")
        _validate_signature(function.get("signature"), f"Core0 target function {source}")
        if (
            not isinstance(dependencies, list)
            or any(
                not isinstance(dependency, str)
                or LEAN_IDENTIFIER.fullmatch(dependency) is None
                for dependency in dependencies
            )
            or len(set(dependencies)) != len(dependencies)
        ):
            raise Core0Error(f"Core0 target function {source} has malformed dependencies")
        missing_dependencies = [dependency for dependency in dependencies if dependency not in seen_sources]
        if missing_dependencies:
            raise Core0Error(
                f"Core0 target function {source} is not dependency-first: {missing_dependencies!r}"
            )
        if (
            not isinstance(body, str)
            or not body.startswith("(")
            or not body.endswith(")")
            or "\n" in body
        ):
            raise Core0Error(f"Core0 target function {source} lacks a normalized typed body")
        seen_sources.add(source)
        seen_symbols.add(symbol)
        source_to_symbol[source] = symbol
    if functions[-1].get("source") != root or source_to_symbol.get(root) != root_llvm:
        raise Core0Error("Core0 target root/source/LLVM mapping is inconsistent")

    primitives = value.get("used_primitives")
    if not isinstance(primitives, list):
        raise Core0Error("Core0 target primitive manifest is malformed")
    seen_primitives: set[str] = set()
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise Core0Error(f"Core0 target primitive #{index} is not an object")
        stable_id = primitive.get("stable_id")
        if not isinstance(stable_id, str) or stable_id in seen_primitives:
            raise Core0Error(f"Core0 target primitive #{index} has an invalid or duplicate ID")
        expected = PRIMITIVE_CONTRACTS.get(stable_id)
        if expected is None or primitive != expected:
            raise Core0Error(f"Core0 target primitive contract is unknown or malformed: {stable_id!r}")
        seen_primitives.add(stable_id)
    if value.get("machine_primitives") != EXPECTED_MACHINE_PRIMITIVES:
        raise Core0Error("Core0 target machine-primitive contracts differ from the exact allowlist")
    return value


def _scalar_abi_extension(ty: str) -> str:
    return {
        "bool": "zeroext",
        "u8": "zeroext",
        "u32": "signext",
        "u64": "none",
    }[ty]


def _scalar_signature(args: tuple[str, ...], result: str) -> dict[str, object]:
    return {"args": list(args), "result": result}


def _validate_scalar_u64_hex(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{16}", value) is None:
        raise Core0Error(f"{context} is not a canonical 16-digit UInt64 hexadecimal value")
    return value


def validate_scalar_export_configuration(
    value: object, manifest: dict[str, object], root: Path
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("scalar-suite provenance lacks exporter configuration")
    _exact_keys(
        value,
        {"driver", "generation_command", "environment"},
        "scalar exporter configuration",
    )
    expected_driver = {
        "core0-v0.1": SCALAR_EXPORT_DRIVER,
        "core0-v0.2": CFG_SCALAR_EXPORT_DRIVER,
        "core0-v0.3": LOOP_SCALAR_EXPORT_DRIVER,
    }.get(str(manifest.get("contract_version")))
    if expected_driver is None:
        raise Core0Error("scalar exporter configuration has an unsupported Core0 contract")
    expected_command = [
        "lake",
        "env",
        "lean",
        str((root / expected_driver).resolve()),
    ]
    if value.get("driver") != expected_driver:
        raise Core0Error("scalar exporter configuration names the wrong Lean driver")
    if value.get("generation_command") != expected_command:
        raise Core0Error("scalar exporter generation command differs from the executed driver")
    environment = value.get("environment")
    if not isinstance(environment, dict):
        raise Core0Error("scalar exporter configuration environment is not an object")
    expected_environment = {
        "LEMMA_SCALAR_RUNTIME_SEED": str(int(str(manifest["runtime_seed"]), 16)),
        "LEMMA_SCALAR_SOURCE_SEED": str(int(str(manifest["source_seed"]), 16)),
        "LEMMA_SCALAR_SUITE_ID": str(int(str(manifest["suite_id"]), 16)),
    }
    _exact_keys(
        environment,
        set(expected_environment),
        "scalar exporter configuration environment",
    )
    if environment != expected_environment:
        raise Core0Error(
            "scalar exporter configuration values differ from the checked suite manifest"
        )
    return value


def validate_memory_export_configuration(
    value: object, manifest: dict[str, object], root: Path
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("memory-suite provenance lacks exporter configuration")
    _exact_keys(
        value,
        {"driver", "generation_command", "environment"},
        "memory exporter configuration",
    )
    expected_command = [
        "lake",
        "env",
        "lean",
        str((root / MEMORY_EXPORT_DRIVER).resolve()),
    ]
    if value.get("driver") != MEMORY_EXPORT_DRIVER:
        raise Core0Error("memory exporter configuration names the wrong Lean driver")
    if value.get("generation_command") != expected_command:
        raise Core0Error("memory exporter generation command differs from the executed driver")
    environment = value.get("environment")
    if not isinstance(environment, dict):
        raise Core0Error("memory exporter configuration environment is not an object")
    expected_environment = {
        "LEMMA_MEMORY_RUNTIME_SEED": str(int(str(manifest["runtime_seed"]), 16)),
        "LEMMA_MEMORY_SOURCE_SEED": str(int(str(manifest["source_seed"]), 16)),
        "LEMMA_MEMORY_SUITE_ID": str(int(str(manifest["suite_id"]), 16)),
    }
    _exact_keys(
        environment,
        set(expected_environment),
        "memory exporter configuration environment",
    )
    if environment != expected_environment:
        raise Core0Error(
            "memory exporter configuration values differ from the checked suite manifest"
        )
    return value


def validate_device_export_configuration(
    value: object, manifest: dict[str, object], root: Path
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("device-suite provenance lacks exporter configuration")
    _exact_keys(
        value,
        {"driver", "generation_command", "environment"},
        "device exporter configuration",
    )
    expected_command = [
        "lake",
        "env",
        "lean",
        str((root / DEVICE_EXPORT_DRIVER).resolve()),
    ]
    if value.get("driver") != DEVICE_EXPORT_DRIVER:
        raise Core0Error("device exporter configuration names the wrong Lean driver")
    if value.get("generation_command") != expected_command:
        raise Core0Error("device exporter generation command differs from the executed driver")
    environment = value.get("environment")
    if not isinstance(environment, dict):
        raise Core0Error("device exporter configuration environment is not an object")
    expected_environment = {
        "LEMMA_DEVICE_RUNTIME_SEED": str(int(str(manifest["runtime_seed"]), 16)),
        "LEMMA_DEVICE_SOURCE_SEED": str(int(str(manifest["source_seed"]), 16)),
        "LEMMA_DEVICE_SUITE_ID": str(int(str(manifest["suite_id"]), 16)),
    }
    _exact_keys(
        environment,
        set(expected_environment),
        "device exporter configuration environment",
    )
    if environment != expected_environment:
        raise Core0Error(
            "device exporter configuration values differ from the checked suite manifest"
        )
    return value


def _validate_device_action_signature(
    value: object, context: str
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} signature is not an object")
    _exact_keys(value, {"args"}, f"{context} signature")
    args = value.get("args")
    scalar_types = {"bool", "u8", "u32", "u64"}
    if (
        not isinstance(args, list)
        or any(not isinstance(arg, str) or arg not in scalar_types for arg in args)
    ):
        raise Core0Error(f"{context} has an invalid Action signature")
    return value


def _validate_device_dependency_list(
    value: object, context: str
) -> list[str]:
    if (
        not isinstance(value, list)
        or any(
            not isinstance(item, str) or LEAN_IDENTIFIER.fullmatch(item) is None
            for item in value
        )
        or len(value) != len(set(value))
    ):
        raise Core0Error(f"{context} is not a unique Lean-identity array")
    return value


def _validate_device_catalog_array(
    value: object, context: str, *, required: bool = True, unique: bool = True
) -> list[dict[str, object]]:
    if not isinstance(value, list) or (required and not value):
        raise Core0Error(f"device suite {context} is empty or malformed")
    result: list[dict[str, object]] = []
    stable_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise Core0Error(f"device suite {context} entry #{index} is not an object")
        stable_id = item.get("stable_id")
        if (
            not isinstance(stable_id, str)
            or not stable_id
            or (unique and stable_id in stable_ids)
        ):
            raise Core0Error(
                f"device suite {context} entry #{index} has an invalid or duplicate stable ID"
            )
        stable_ids.add(stable_id)
        result.append(item)
    return result


def validate_device_suite_manifest(value: object) -> dict[str, object]:
    """Validate the generic v0.5 suite envelope and complete function closure.

    The device-specific operation/IR proof remains the responsibility of the
    independent Gate 6 audit.  This central audit still binds every scalar and
    Action definition used to form the ELF, checks dependency closure, and pins
    the machine boundary exactly.
    """
    if not isinstance(value, dict):
        raise Core0Error("device-suite-manifest.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "artifact_category",
            "contract_version",
            "test_abi",
            "suite_id",
            "source_seed",
            "runtime_seed",
            "checked_result",
            "memory_contract",
            "device_contract",
            "roots",
            "scalar_functions",
            "action_functions",
            "used_primitives",
            "used_memory_ops",
            "used_device_ops",
            "action_iterations",
            "machine_primitives",
        },
        "device suite manifest",
    )
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("device suite manifest has an unsupported schema")
    if value.get("artifact_category") != TEST_DEVICE_SUITE_POLICY:
        raise Core0Error("device suite manifest has the wrong artifact category")
    if value.get("contract_version") != "core0-v0.5":
        raise Core0Error("device suite manifest has an unsupported Core0 contract")
    if value.get("test_abi") != "lemma-device-session-v1":
        raise Core0Error("device suite manifest has an unsupported test ABI")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        _validate_scalar_u64_hex(value.get(field), f"device suite manifest {field}")
    if value.get("checked_result") != audit_memory.CHECKED_RESULT_CONTRACT:
        raise Core0Error("device suite checked-result contract differs from the direct ABI")
    if value.get("memory_contract") != audit_memory.MEMORY_CONTRACT:
        raise Core0Error("device suite memory contract differs from the fixed-RAM contract")
    device_contract = value.get("device_contract")
    if not isinstance(device_contract, dict):
        raise Core0Error("device suite device contract is not an object")
    if (
        device_contract.get("schema_version") != 1
        or device_contract.get("contract_version") != "core0-v0.5"
        or device_contract.get("machine") != "qemu-virt-rv64-single-hart"
        or device_contract.get("interrupt_use") != "none; Gate 6 is polling-only"
        or device_contract.get("general_ram_api_access") is not False
    ):
        raise Core0Error("device suite contract differs from the polling-only v0.5 machine")

    scalar_functions = value.get("scalar_functions")
    action_functions = value.get("action_functions")
    if not isinstance(scalar_functions, list) or not scalar_functions:
        raise Core0Error("device suite scalar function closure is empty or malformed")
    if not isinstance(action_functions, list) or not action_functions:
        raise Core0Error("device suite Action function closure is empty or malformed")

    scalar_sources: set[str] = set()
    action_sources: set[str] = set()
    llvm_symbols: set[str] = set()
    scalar_signatures: dict[str, dict[str, object]] = {}
    action_signatures: dict[str, dict[str, object]] = {}
    for index, function in enumerate(scalar_functions):
        context = f"device scalar function #{index}"
        if not isinstance(function, dict):
            raise Core0Error(f"{context} is not an object")
        _exact_keys(
            function,
            {"source", "llvm", "signature", "dependencies", "body", "noinline"},
            context,
        )
        source, symbol = function.get("source"), function.get("llvm")
        if (
            not isinstance(source, str)
            or LEAN_IDENTIFIER.fullmatch(source) is None
            or source in scalar_sources
        ):
            raise Core0Error(f"{context} has an invalid or duplicate source identity")
        if (
            not isinstance(symbol, str)
            or LLVM_IDENTIFIER.fullmatch(symbol) is None
            or symbol in llvm_symbols
        ):
            raise Core0Error(f"{context} has an invalid or duplicate LLVM identity")
        signature = _validate_signature(function.get("signature"), context)
        dependencies = _validate_device_dependency_list(
            function.get("dependencies"), f"{context} dependencies"
        )
        if any(dependency not in scalar_sources for dependency in dependencies):
            raise Core0Error(f"{context} dependencies are not dependency-first and closed")
        if (
            not isinstance(function.get("body"), str)
            or not function["body"]
            or "\n" in str(function["body"])
            or "\r" in str(function["body"])
            or function.get("noinline") is not True
        ):
            raise Core0Error(f"{context} lacks a normalized noinline checked body")
        scalar_sources.add(source)
        llvm_symbols.add(symbol)
        scalar_signatures[source] = signature

    effect_order = (
        "checked-access",
        "fixed-ram-read",
        "fixed-ram-write",
        "mmio-read",
        "mmio-write",
        "io-order",
    )
    for index, function in enumerate(action_functions):
        context = f"device Action function #{index}"
        if not isinstance(function, dict):
            raise Core0Error(f"{context} is not an object")
        _exact_keys(
            function,
            {
                "source",
                "llvm",
                "signature",
                "scalar_dependencies",
                "action_dependencies",
                "direct_effects",
                "transitive_effects",
                "body",
                "noinline",
            },
            context,
        )
        source, symbol = function.get("source"), function.get("llvm")
        if (
            not isinstance(source, str)
            or LEAN_IDENTIFIER.fullmatch(source) is None
            or source in scalar_sources
            or source in action_sources
        ):
            raise Core0Error(f"{context} has an invalid or duplicate source identity")
        if (
            not isinstance(symbol, str)
            or LLVM_IDENTIFIER.fullmatch(symbol) is None
            or symbol in llvm_symbols
        ):
            raise Core0Error(f"{context} has an invalid or duplicate LLVM identity")
        signature = _validate_device_action_signature(function.get("signature"), context)
        scalar_dependencies = _validate_device_dependency_list(
            function.get("scalar_dependencies"), f"{context} scalar dependencies"
        )
        action_dependencies = _validate_device_dependency_list(
            function.get("action_dependencies"), f"{context} Action dependencies"
        )
        if any(dependency not in scalar_sources for dependency in scalar_dependencies):
            raise Core0Error(f"{context} scalar dependency closure is incomplete")
        if any(dependency not in action_sources for dependency in action_dependencies):
            raise Core0Error(f"{context} Action dependencies are not dependency-first and closed")
        for field in ("direct_effects", "transitive_effects"):
            effects = function.get(field)
            if (
                not isinstance(effects, list)
                or any(effect not in effect_order for effect in effects)
                or effects != [effect for effect in effect_order if effect in effects]
            ):
                raise Core0Error(f"{context} {field} is not a canonical effect set")
        if (
            not isinstance(function.get("body"), str)
            or not function["body"]
            or "\n" in str(function["body"])
            or "\r" in str(function["body"])
            or function.get("noinline") is not True
        ):
            raise Core0Error(f"{context} lacks a normalized noinline checked body")
        action_sources.add(source)
        llvm_symbols.add(symbol)
        action_signatures[source] = signature

    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], dict):
        raise Core0Error("device suite must contain exactly one root")
    root = roots[0]
    _exact_keys(root, {"root_id", "source", "llvm", "signature"}, "device suite root")
    root_id, root_source, root_symbol = (
        root.get("root_id"), root.get("source"), root.get("llvm")
    )
    if isinstance(root_id, bool) or not isinstance(root_id, int) or root_id <= 0:
        raise Core0Error("device suite root ID is not a positive integer")
    if (
        not isinstance(root_source, str)
        or LEAN_IDENTIFIER.fullmatch(root_source) is None
        or not isinstance(root_symbol, str)
        or LLVM_IDENTIFIER.fullmatch(root_symbol) is None
    ):
        raise Core0Error("device suite root source/LLVM identity is malformed")
    root_signature = _validate_device_action_signature(
        root.get("signature"), "device suite root"
    )
    if root_signature != {"args": []}:
        raise Core0Error("device suite root does not have the zero-argument Action ABI")
    root_entries = [
        function
        for function in action_functions
        if isinstance(function, dict) and function.get("source") == root_source
    ]
    if (
        len(root_entries) != 1
        or root_source not in action_signatures
        or root_symbol != root_entries[0].get("llvm")
        or root_signature != action_signatures[root_source]
    ):
        raise Core0Error("device suite root is not bound to its Action function closure")

    primitives = _validate_device_catalog_array(
        value.get("used_primitives"), "primitive closure"
    )
    for primitive in primitives:
        stable_id = str(primitive["stable_id"])
        if primitive != PRIMITIVE_CONTRACTS_V02.get(stable_id):
            raise Core0Error(
                f"device suite primitive contract is unknown or malformed: {stable_id!r}"
            )
    memory_ops = _validate_device_catalog_array(
        value.get("used_memory_ops"), "memory-operation closure"
    )
    for operation in memory_ops:
        stable_id = str(operation["stable_id"])
        if operation != audit_memory.MEMORY_OPS.get(stable_id):
            raise Core0Error(
                f"device suite memory-operation contract is unknown or malformed: {stable_id!r}"
            )
    _validate_device_catalog_array(
        value.get("used_device_ops"), "device-operation closure"
    )
    iterations = _validate_device_catalog_array(
        value.get("action_iterations"), "Action-iteration closure", unique=False
    )
    for index, site in enumerate(iterations):
        budget, callback = site.get("static_budget"), site.get("callback")
        if (
            isinstance(budget, bool)
            or not isinstance(budget, int)
            or not 0 <= budget <= 1_000_000
            or not isinstance(callback, str)
            or callback not in action_sources
        ):
            raise Core0Error(f"device Action-iteration entry #{index} is malformed")
    if value.get("machine_primitives") != EXPECTED_DEVICE_MACHINE_PRIMITIVES:
        raise Core0Error(
            "device suite machine-primitive contracts differ from the exact allowlist"
        )
    return value


def validate_device_test_abi(
    value: object, manifest: dict[str, object]
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("device-test-abi.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "contract_version",
            "name",
            "byte_order",
            "ready",
            "requests_per_session",
            "poll_budget",
            "request",
            "response",
            "commands",
            "statuses",
            "terminal_rules",
            "suite_id",
            "source_seed",
            "runtime_seed",
        },
        "device test ABI",
    )
    expected_scalars = {
        "schema_version": 1,
        "contract_version": "core0-v0.5",
        "name": "lemma-device-session-v1",
        "byte_order": "little-endian",
        "ready": "LEMMA_DEVICE/1\nREADY\n",
        "requests_per_session": 2,
        "poll_budget": 1_000_000,
        "suite_id": manifest["suite_id"],
        "source_seed": manifest["source_seed"],
        "runtime_seed": manifest["runtime_seed"],
    }
    if any(value.get(field) != expected for field, expected in expected_scalars.items()):
        raise Core0Error("device test ABI differs from the v0.5 session envelope")
    if (
        not isinstance(value.get("request"), dict)
        or not isinstance(value.get("response"), dict)
        or not isinstance(value.get("terminal_rules"), dict)
        or not isinstance(value.get("commands"), list)
        or not value["commands"]
        or any(not isinstance(item, dict) for item in value["commands"])
        or not isinstance(value.get("statuses"), list)
        or not value["statuses"]
        or any(not isinstance(item, dict) for item in value["statuses"])
    ):
        raise Core0Error("device test ABI request/response catalog is malformed")
    return value


def validate_device_manifest_companions(
    manifest: dict[str, object], normalized_text: str, symbols_text: str
) -> None:
    roots = manifest["roots"]
    scalar_functions = manifest["scalar_functions"]
    action_functions = manifest["action_functions"]
    memory_ops = manifest["used_memory_ops"]
    device_ops = manifest["used_device_ops"]
    iterations = manifest["action_iterations"]
    assert all(
        isinstance(items, list)
        for items in (
            roots,
            scalar_functions,
            action_functions,
            memory_ops,
            device_ops,
            iterations,
        )
    )
    lines = [f"contract={manifest['contract_version']}"]
    for root in roots:
        assert isinstance(root, dict) and isinstance(root["signature"], dict)
        signature = json.dumps(root["signature"], separators=(",", ":"))
        lines.append(
            f"root={root['root_id']};source={root['source']};signature={signature}"
        )
    for function in scalar_functions:
        assert isinstance(function, dict)
        lines.append(f"scalar={function['source']};body={function['body']}")
    for function in action_functions:
        assert isinstance(function, dict)
        direct = "[" + ",".join(str(item) for item in function["direct_effects"]) + "]"
        transitive = (
            "[" + ",".join(str(item) for item in function["transitive_effects"]) + "]"
        )
        lines.append(
            f"action={function['source']};direct={direct};transitive={transitive};"
            f"body={function['body']}"
        )
    # The manifest intentionally sorts memory operations while the normalized
    # companion preserves first-use order.  Bind the exact operation multiset
    # without inventing an order that is not represented in the manifest.
    prefix_lines = list(lines)
    memory_lines = []
    for operation in memory_ops:
        assert isinstance(operation, dict)
        memory_lines.append(f"memory-op={operation['stable_id']}")
    suffix_lines = []
    for operation in device_ops:
        assert isinstance(operation, dict)
        suffix_lines.append(f"device-op={operation['stable_id']}")
    for site in iterations:
        assert isinstance(site, dict)
        suffix_lines.append(
            f"action-iteration={site['stable_id']};budget={site['static_budget']};"
            f"callback={site['callback']}"
        )
    actual_lines = normalized_text.splitlines()
    actual_memory_start = len(prefix_lines)
    actual_memory_stop = actual_memory_start + len(memory_lines)
    if (
        not normalized_text.endswith("\n")
        or actual_lines[:actual_memory_start] != prefix_lines
        or sorted(actual_lines[actual_memory_start:actual_memory_stop])
        != sorted(memory_lines)
        or actual_lines[actual_memory_stop:] != suffix_lines
    ):
        raise Core0Error(
            "device-suite-normalized.txt does not match the checked device manifest"
        )
    symbol_lines = [
        f"source={function['source']};llvm={function['llvm']}"
        for function in [*scalar_functions, *action_functions]
        if isinstance(function, dict)
    ]
    if symbols_text != "\n".join(symbol_lines) + "\n":
        raise Core0Error("symbols.txt does not match the device source-to-LLVM mapping")


def validate_memory_test_abi(
    value: object, manifest: dict[str, object]
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("memory-test-abi.json is not an object")
    expected = {
        "schema_version": 1,
        "contract_version": "core0-v0.4",
        "name": "lemma-memory-test-v1",
        "result_tag": "checked-result-v1",
        "physical_result_words": ["status:i64", "value:i64"],
        "byte_order": "little-endian",
        "magic_bytes": "4c454d4d41303035",
        "magic_word": "0x353030414d4d454c",
        "version": 1,
        "header_bytes": 128,
        "control_bytes": 256,
        "maximum_arguments": 16,
        "tags": {"bool": 1, "u8": 2, "u32": 3, "u64": 4},
        "header_words": [
            "magic", "version", "header_bytes", "control_bytes", "suite_id",
            "case_id", "root_id", "argument_count", "argument_tags_0_7",
            "argument_tags_8_15", "source_seed", "runtime_seed",
            "reserved_zero", "reserved_zero", "reserved_zero", "reserved_zero",
        ],
        "argument_layout": "16xu64; unused slots zero",
        "transport_rules": (
            "Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; "
            "reject before truncation"
        ),
        "output_protocol": {
            "banner": "LEMMA_MEMORY/1\n",
            "case": "CASE:<suite16>:<case16>:<root16>\n",
            "outcome": "OUTCOME:<case16>:<status16>:<value16>\n",
            "region": "REGION:<id2>:<length16>:<little-endian-i64-words>\n",
            "canary": "CANARY:<id2>:<low16>:<high16>\n",
            "end": "END:<case16>\n",
        },
        "suite_id": manifest["suite_id"],
        "source_seed": manifest["source_seed"],
        "runtime_seed": manifest["runtime_seed"],
    }
    _exact_keys(value, set(expected), "memory test ABI")
    if value != expected:
        raise Core0Error("memory test ABI differs from the exact v0.4 transport contract")
    return value


def validate_memory_manifest_companions(
    manifest: dict[str, object], normalized_text: str, symbols_text: str
) -> None:
    roots = manifest.get("roots")
    scalar_functions = manifest.get("scalar_functions")
    action_functions = manifest.get("action_functions")
    memory_ops = manifest.get("used_memory_ops")
    iterations = manifest.get("action_iterations")
    if not all(
        isinstance(value, list)
        for value in (roots, scalar_functions, action_functions, memory_ops, iterations)
    ):
        raise Core0Error("memory manifest companion inputs are malformed")
    assert isinstance(roots, list)
    assert isinstance(scalar_functions, list)
    assert isinstance(action_functions, list)
    assert isinstance(memory_ops, list)
    assert isinstance(iterations, list)
    lines = [f"contract={manifest['contract_version']}"]
    for root in roots:
        if not isinstance(root, dict) or not isinstance(root.get("signature"), dict):
            raise Core0Error("memory manifest has a malformed root companion")
        signature = json.dumps(root["signature"], separators=(",", ":"))
        lines.append(
            f"root={root['root_id']};source={root['source']};signature={signature}"
        )
    for function in scalar_functions:
        if not isinstance(function, dict):
            raise Core0Error("memory manifest has a malformed scalar companion")
        lines.append(f"scalar={function['source']};body={function['body']}")
    for function in action_functions:
        if not isinstance(function, dict):
            raise Core0Error("memory manifest has a malformed Action companion")
        direct = "[" + ",".join(str(item) for item in function["direct_effects"]) + "]"
        transitive = (
            "[" + ",".join(str(item) for item in function["transitive_effects"]) + "]"
        )
        lines.append(
            f"action={function['source']};direct={direct};transitive={transitive};"
            f"body={function['body']}"
        )
    by_id = {
        str(operation["stable_id"]): operation
        for operation in memory_ops
        if isinstance(operation, dict)
    }
    operation_order = (
        "ram.read8", "ram.read32", "ram.read64", "ram.write8", "ram.write32",
        "ram.write64", "ram.check-read-range", "ram.check-write-range",
    )
    if set(by_id) != set(operation_order):
        raise Core0Error("memory normalized operation closure differs from v0.4")
    lines.extend(f"memory-op={stable_id}" for stable_id in operation_order)
    for site in iterations:
        if not isinstance(site, dict):
            raise Core0Error("memory manifest has a malformed iteration companion")
        lines.append(
            f"action-iteration={site['stable_id']};budget={site['static_budget']};"
            f"callback={site['callback']}"
        )
    if normalized_text != "\n".join(lines) + "\n":
        raise Core0Error(
            "memory-suite-normalized.txt does not match the checked memory manifest"
        )
    functions = [*scalar_functions, *action_functions]
    symbol_lines = []
    for function in functions:
        if not isinstance(function, dict):
            raise Core0Error("memory manifest has a malformed symbol companion")
        symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
    if symbols_text != "\n".join(symbol_lines) + "\n":
        raise Core0Error("symbols.txt does not match the memory source-to-LLVM mapping")


def validate_scalar_export_command_log(
    configuration: dict[str, object], command_argv: list[object]
) -> None:
    expected = configuration.get("generation_command")
    if expected not in command_argv:
        raise Core0Error(
            "provenance command log omits the exact scalar exporter invocation"
        )


def validate_scalar_suite_manifest(value: object) -> dict[str, object]:
    """Validate the closed 37-root Gate 2 suite and its 43-function closure."""
    if not isinstance(value, dict):
        raise Core0Error("scalar-suite-manifest.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "artifact_category",
            "contract_version",
            "test_abi",
            "suite_id",
            "source_seed",
            "runtime_seed",
            "roots",
            "functions",
            "used_primitives",
            "machine_primitives",
        },
        "scalar suite manifest",
    )
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("scalar suite manifest has an unsupported schema")
    if value.get("artifact_category") != TEST_FRONTEND_SUITE_POLICY:
        raise Core0Error("scalar suite manifest has the wrong artifact category")
    if value.get("contract_version") != "core0-v0.1":
        raise Core0Error("scalar suite manifest has an unsupported Core0 contract")
    if value.get("test_abi") != SCALAR_TEST_ABI:
        raise Core0Error("scalar suite manifest has an unsupported typed test ABI")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        _validate_scalar_u64_hex(value.get(field), f"scalar suite manifest {field}")

    function_contract = {
        source: (args, result, dependencies)
        for source, args, result, dependencies in SCALAR_FUNCTION_CONTRACTS
    }
    functions = value.get("functions")
    if not isinstance(functions, list) or len(functions) != len(SCALAR_FUNCTION_CONTRACTS):
        raise Core0Error(
            "scalar suite manifest must contain the exact 43-function dependency closure"
        )
    source_symbols: dict[str, str] = {}
    seen_symbols: set[str] = set()
    for index, (function, contract) in enumerate(
        zip(functions, SCALAR_FUNCTION_CONTRACTS)
    ):
        expected_source = contract[0]
        if not isinstance(function, dict) or function.get("source") != expected_source:
            raise Core0Error(f"scalar suite function #{index} has the wrong source identity")
        symbol = function.get("llvm")
        if (
            not isinstance(symbol, str)
            or LLVM_IDENTIFIER.fullmatch(symbol) is None
            or symbol in seen_symbols
        ):
            raise Core0Error(f"scalar suite function {expected_source} has an invalid/duplicate LLVM symbol")
        source_symbols[expected_source] = symbol
        seen_symbols.add(symbol)
    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(SCALAR_ROOT_SOURCES):
        raise Core0Error(
            "scalar suite manifest must contain the exact 37-root declaration catalog"
        )
    for index, (root, expected_source) in enumerate(zip(roots, SCALAR_ROOT_SOURCES)):
        if not isinstance(root, dict):
            raise Core0Error(f"scalar suite root #{index} is not an object")
        _exact_keys(
            root,
            {
                "root_id",
                "source",
                "llvm",
                "signature",
                "return_extension",
                "parameter_extensions",
            },
            f"scalar suite root #{index}",
        )
        args, result, _dependencies = function_contract[expected_source]
        expected_id = index + 1
        expected_symbol = source_symbols[expected_source]
        if type(root.get("root_id")) is not int or root.get("root_id") != expected_id:
            raise Core0Error(f"scalar suite root #{index} has a non-canonical root ID")
        if root.get("source") != expected_source or root.get("llvm") != expected_symbol:
            raise Core0Error(f"scalar suite root #{index} has the wrong source/symbol identity")
        signature = _validate_signature(root.get("signature"), f"scalar suite root {expected_source}")
        if signature != _scalar_signature(args, result):
            raise Core0Error(f"scalar suite root {expected_source} has the wrong signature")
        if root.get("return_extension") != _scalar_abi_extension(result):
            raise Core0Error(f"scalar suite root {expected_source} has the wrong return extension")
        if root.get("parameter_extensions") != [
            _scalar_abi_extension(arg) for arg in args
        ]:
            raise Core0Error(
                f"scalar suite root {expected_source} has the wrong parameter extensions"
            )

    for index, (function, contract) in enumerate(
        zip(functions, SCALAR_FUNCTION_CONTRACTS)
    ):
        source, args, result, dependencies = contract
        if not isinstance(function, dict):
            raise Core0Error(f"scalar suite function #{index} is not an object")
        _exact_keys(
            function,
            {
                "source",
                "llvm",
                "signature",
                "dependencies",
                "body",
                "return_extension",
                "parameter_extensions",
                "noinline",
            },
            f"scalar suite function #{index}",
        )
        if function.get("source") != source or function.get("llvm") != source_symbols[source]:
            raise Core0Error(f"scalar suite function #{index} has the wrong source/symbol identity")
        signature = _validate_signature(function.get("signature"), f"scalar suite function {source}")
        if signature != _scalar_signature(args, result):
            raise Core0Error(f"scalar suite function {source} has the wrong signature")
        if function.get("dependencies") != list(dependencies):
            raise Core0Error(f"scalar suite function {source} has the wrong dependency closure")
        body = function.get("body")
        if (
            not isinstance(body, str)
            or not body.startswith("(")
            or not body.endswith(")")
            or "\n" in body
            or "\r" in body
        ):
            raise Core0Error(f"scalar suite function {source} lacks a normalized typed body")
        if function.get("return_extension") != _scalar_abi_extension(result):
            raise Core0Error(f"scalar suite function {source} has the wrong return extension")
        if function.get("parameter_extensions") != [
            _scalar_abi_extension(arg) for arg in args
        ]:
            raise Core0Error(
                f"scalar suite function {source} has the wrong parameter extensions"
            )
        if function.get("noinline") is not True:
            raise Core0Error(f"scalar suite function {source} is not pinned noinline")

    primitives = value.get("used_primitives")
    if not isinstance(primitives, list) or len(primitives) != len(PRIMITIVE_CONTRACTS):
        raise Core0Error("scalar suite primitive manifest is not the complete Core0 allowlist")
    seen_primitives: set[str] = set()
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise Core0Error(f"scalar suite primitive #{index} is not an object")
        stable_id = primitive.get("stable_id")
        if not isinstance(stable_id, str) or stable_id in seen_primitives:
            raise Core0Error(f"scalar suite primitive #{index} has an invalid or duplicate ID")
        expected = PRIMITIVE_CONTRACTS.get(stable_id)
        if expected is None or primitive != expected:
            raise Core0Error(f"scalar suite primitive contract is unknown or malformed: {stable_id!r}")
        seen_primitives.add(stable_id)
    if seen_primitives != set(PRIMITIVE_CONTRACTS):
        raise Core0Error("scalar suite primitive manifest does not cover the exact allowlist")
    if value.get("machine_primitives") != EXPECTED_SCALAR_MACHINE_PRIMITIVES:
        raise Core0Error(
            "scalar suite machine-primitive contracts differ from the exact allowlist"
        )
    return value


def validate_cfg_suite_manifest(value: object) -> dict[str, object]:
    """Validate the closed 44-root/47-function `core0-v0.2` Gate 3 suite."""
    if not isinstance(value, dict):
        raise Core0Error("structured scalar-suite manifest is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "artifact_category",
            "contract_version",
            "test_abi",
            "suite_id",
            "source_seed",
            "runtime_seed",
            "cfg_validation",
            "roots",
            "functions",
            "used_primitives",
            "machine_primitives",
        },
        "structured scalar-suite manifest",
    )
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("structured scalar-suite manifest has an unsupported schema")
    if value.get("artifact_category") != TEST_CFG_SUITE_POLICY:
        raise Core0Error("structured scalar-suite manifest has the wrong artifact category")
    if value.get("contract_version") != "core0-v0.2":
        raise Core0Error("structured scalar-suite manifest has an unsupported Core0 contract")
    if value.get("test_abi") != SCALAR_TEST_ABI:
        raise Core0Error("structured scalar-suite manifest has an unsupported typed test ABI")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        _validate_scalar_u64_hex(value.get(field), f"structured scalar manifest {field}")
    if value.get("cfg_validation") != {
        "validator": "Lemma.Compiler.LLVM.validateModule",
        "source_conditionals": "branch-phi",
        "division": "zero-guarded",
        "shift_counts": "masked-to-width",
    }:
        raise Core0Error("structured scalar-suite CFG contract differs from the closed profile")

    functions = value.get("functions")
    if not isinstance(functions, list) or len(functions) != len(CFG_FUNCTION_CONTRACTS):
        raise Core0Error("structured scalar suite lacks its exact 47-function closure")
    source_symbols: dict[str, str] = {}
    for index, (function, contract) in enumerate(zip(functions, CFG_FUNCTION_CONTRACTS)):
        source, args, result, dependencies = contract
        if not isinstance(function, dict):
            raise Core0Error(f"structured scalar function #{index} is not an object")
        _exact_keys(
            function,
            {
                "source",
                "llvm",
                "signature",
                "dependencies",
                "body",
                "return_extension",
                "parameter_extensions",
                "noinline",
            },
            f"structured scalar function #{index}",
        )
        expected_symbol = f"core0_user_{index}"
        if function.get("source") != source or function.get("llvm") != expected_symbol:
            raise Core0Error(f"structured scalar function #{index} has wrong source/symbol")
        if _validate_signature(
            function.get("signature"), f"structured function {source}"
        ) != _scalar_signature(args, result):
            raise Core0Error(f"structured scalar function {source} has wrong signature")
        if function.get("dependencies") != list(dependencies):
            raise Core0Error(f"structured scalar function {source} has wrong dependencies")
        body = function.get("body")
        if (
            not isinstance(body, str)
            or not body.startswith("(")
            or not body.endswith(")")
            or "\n" in body
            or "\r" in body
        ):
            raise Core0Error(f"structured scalar function {source} lacks normalized body")
        if function.get("return_extension") != _scalar_abi_extension(result):
            raise Core0Error(f"structured scalar function {source} has wrong return extension")
        if function.get("parameter_extensions") != [
            _scalar_abi_extension(arg) for arg in args
        ]:
            raise Core0Error(f"structured scalar function {source} has wrong parameter extensions")
        if function.get("noinline") is not True:
            raise Core0Error(f"structured scalar function {source} is not pinned noinline")
        source_symbols[source] = expected_symbol

    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(CFG_ROOT_SOURCES):
        raise Core0Error("structured scalar suite lacks its exact 44-root catalog")
    contracts = {
        source: (args, result)
        for source, args, result, _dependencies in CFG_FUNCTION_CONTRACTS
    }
    for index, (root, source) in enumerate(zip(roots, CFG_ROOT_SOURCES)):
        if not isinstance(root, dict):
            raise Core0Error(f"structured scalar root #{index} is not an object")
        _exact_keys(
            root,
            {
                "root_id",
                "source",
                "llvm",
                "signature",
                "return_extension",
                "parameter_extensions",
            },
            f"structured scalar root #{index}",
        )
        args, result = contracts[source]
        if (
            type(root.get("root_id")) is not int
            or root.get("root_id") != index + 1
            or root.get("source") != source
            or root.get("llvm") != source_symbols[source]
        ):
            raise Core0Error(f"structured scalar root #{index} has wrong canonical identity")
        if _validate_signature(
            root.get("signature"), f"structured root {source}"
        ) != _scalar_signature(args, result):
            raise Core0Error(f"structured scalar root {source} has wrong signature")
        if root.get("return_extension") != _scalar_abi_extension(result):
            raise Core0Error(f"structured scalar root {source} has wrong return extension")
        if root.get("parameter_extensions") != [
            _scalar_abi_extension(arg) for arg in args
        ]:
            raise Core0Error(f"structured scalar root {source} has wrong parameter extensions")

    primitives = value.get("used_primitives")
    if not isinstance(primitives, list) or len(primitives) != len(CFG_USED_PRIMITIVES):
        raise Core0Error("structured scalar primitive manifest has the wrong size")
    seen: set[str] = set()
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise Core0Error(f"structured scalar primitive #{index} is not an object")
        stable_id = primitive.get("stable_id")
        if not isinstance(stable_id, str) or stable_id in seen:
            raise Core0Error(f"structured scalar primitive #{index} has invalid identity")
        if stable_id not in CFG_USED_PRIMITIVES or primitive != PRIMITIVE_CONTRACTS_V02.get(stable_id):
            raise Core0Error(f"structured scalar primitive is unknown/malformed: {stable_id!r}")
        seen.add(stable_id)
    if seen != CFG_USED_PRIMITIVES:
        raise Core0Error("structured scalar suite does not cover the exact primitive set")
    if value.get("machine_primitives") != EXPECTED_SCALAR_MACHINE_PRIMITIVES:
        raise Core0Error("structured suite machine primitives differ from exact allowlist")
    return value


def _expected_loop_iteration(budget: int, callback: str) -> dict[str, object]:
    return {
        "stable_id": "u32.bounded-fold",
        "source_identity": "Lemma.Core0.Bounded.boundedFoldU32",
        "static_budget": budget,
        "static_budget_type": "Nat",
        "static_budget_form": "canonical-standard-Nat-literal",
        "callback": callback,
        "runtime_signature": {"args": ["u32", "u32"], "result": "u64"},
        "callback_signature": {"args": ["u32", "u32"], "result": "u32"},
        "maximum_budget": 256,
        "counter": {"type": "u32", "order": "ascending-zero-based"},
        "accumulator": "u32",
        "outcome": LOOP_OUTCOME_CONTRACT,
        "effect": "pure",
    }


def validate_loop_suite_manifest(value: object) -> dict[str, object]:
    """Validate the closed seven-root/14-function Core0 v0.3 loop suite."""
    if not isinstance(value, dict):
        raise Core0Error("bounded-suite-manifest.json is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "artifact_category",
            "contract_version",
            "test_abi",
            "suite_id",
            "source_seed",
            "runtime_seed",
            "loop_contract",
            "roots",
            "functions",
            "used_primitives",
            "iterations",
            "machine_primitives",
        },
        "bounded suite manifest",
    )
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("bounded suite manifest has an unsupported schema")
    if value.get("artifact_category") != TEST_LOOP_SUITE_POLICY:
        raise Core0Error("bounded suite manifest has the wrong artifact category")
    if value.get("contract_version") != "core0-v0.3":
        raise Core0Error("bounded suite manifest has an unsupported Core0 contract")
    if value.get("test_abi") != SCALAR_TEST_ABI:
        raise Core0Error("bounded suite manifest has an unsupported typed test ABI")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        _validate_scalar_u64_hex(value.get(field), f"bounded suite manifest {field}")
    if value.get("loop_contract") != LOOP_CONTRACT:
        raise Core0Error("bounded suite loop contract differs from the exact v0.3 contract")

    functions = value.get("functions")
    expected_order = tuple(LOOP_FUNCTION_CONTRACTS)
    if not isinstance(functions, list) or len(functions) != len(expected_order):
        raise Core0Error("bounded suite lacks its exact 14-function closure")
    source_symbols: dict[str, str] = {}
    for index, (function, source) in enumerate(zip(functions, expected_order, strict=True)):
        if not isinstance(function, dict):
            raise Core0Error(f"bounded suite function #{index} is not an object")
        _exact_keys(
            function,
            {
                "source", "llvm", "signature", "dependencies", "body",
                "return_extension", "parameter_extensions", "noinline",
            },
            f"bounded suite function #{index}",
        )
        args, result, dependencies = LOOP_FUNCTION_CONTRACTS[source]
        symbol = function.get("llvm")
        if (
            function.get("source") != source
            or symbol != f"core0_user_{index}"
            or not isinstance(symbol, str)
        ):
            raise Core0Error(f"bounded suite function #{index} has wrong source/symbol")
        if _validate_signature(
            function.get("signature"), f"bounded suite function {source}"
        ) != _scalar_signature(args, result):
            raise Core0Error(f"bounded suite function {source} has the wrong signature")
        if function.get("dependencies") != list(dependencies):
            raise Core0Error(f"bounded suite function {source} has the wrong dependencies")
        if function.get("body") != LOOP_FUNCTION_BODIES[source]:
            raise Core0Error(f"bounded suite function {source} has the wrong normalized body")
        if function.get("return_extension") != _scalar_abi_extension(result):
            raise Core0Error(f"bounded suite function {source} has the wrong return extension")
        if function.get("parameter_extensions") != [
            _scalar_abi_extension(arg) for arg in args
        ]:
            raise Core0Error(f"bounded suite function {source} has wrong parameter extensions")
        if function.get("noinline") is not True:
            raise Core0Error(f"bounded suite function {source} is not pinned noinline")
        source_symbols[source] = symbol

    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(LOOP_ROOT_SOURCES):
        raise Core0Error("bounded suite lacks its exact seven-root catalog")
    for index, (root, source) in enumerate(zip(roots, LOOP_ROOT_SOURCES, strict=True)):
        if not isinstance(root, dict):
            raise Core0Error(f"bounded suite root #{index} is not an object")
        _exact_keys(
            root,
            {
                "root_id", "source", "llvm", "signature", "return_extension",
                "parameter_extensions",
            },
            f"bounded suite root #{index}",
        )
        if (
            type(root.get("root_id")) is not int
            or root.get("root_id") != index + 1
            or root.get("source") != source
            or root.get("llvm") != source_symbols[source]
            or root.get("signature") != {"args": ["u32", "u32"], "result": "u64"}
            or root.get("return_extension") != "none"
            or root.get("parameter_extensions") != ["signext", "signext"]
        ):
            raise Core0Error(f"bounded suite root #{index} differs from its exact contract")

    primitives = value.get("used_primitives")
    if not isinstance(primitives, list) or len(primitives) != len(LOOP_USED_PRIMITIVES):
        raise Core0Error("bounded suite primitive manifest has the wrong size")
    seen_primitives: set[str] = set()
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise Core0Error(f"bounded suite primitive #{index} is not an object")
        stable_id = primitive.get("stable_id")
        if not isinstance(stable_id, str) or stable_id in seen_primitives:
            raise Core0Error(f"bounded suite primitive #{index} has invalid identity")
        if (
            stable_id not in LOOP_USED_PRIMITIVES
            or primitive != PRIMITIVE_CONTRACTS_V02.get(stable_id)
        ):
            raise Core0Error(f"bounded suite primitive is unknown/malformed: {stable_id!r}")
        seen_primitives.add(stable_id)
    if seen_primitives != LOOP_USED_PRIMITIVES:
        raise Core0Error("bounded suite does not cover its exact primitive set")

    iterations = value.get("iterations")
    expected_iterations = [
        _expected_loop_iteration(budget, callback)
        for budget, callback in LOOP_ITERATION_ORDER
    ]
    if iterations != expected_iterations:
        raise Core0Error("bounded suite iteration sites differ from the exact source catalog")
    if value.get("machine_primitives") != EXPECTED_SCALAR_MACHINE_PRIMITIVES:
        raise Core0Error("bounded suite machine primitives differ from the exact allowlist")
    return value


def validate_bounded_manifest_companions(
    manifest: dict[str, object], normalized_text: str, symbols_text: str
) -> None:
    roots = manifest["roots"]
    functions = manifest["functions"]
    primitives = manifest["used_primitives"]
    iterations = manifest["iterations"]
    if not all(isinstance(value, list) for value in (roots, functions, primitives, iterations)):
        raise Core0Error("bounded manifest companion inputs are malformed")
    normalized_lines = [f"contract={manifest['contract_version']}"]
    for index, root in enumerate(roots):
        if not isinstance(root, dict) or not isinstance(root.get("signature"), dict):
            raise Core0Error(f"bounded manifest root #{index} is malformed")
        signature = json.dumps(root["signature"], separators=(",", ":"))
        normalized_lines.append(
            f"root={root['root_id']};source={root['source']};signature={signature}"
        )
    symbol_lines: list[str] = []
    for index, function in enumerate(functions):
        if not isinstance(function, dict) or not isinstance(function.get("signature"), dict):
            raise Core0Error(f"bounded manifest function #{index} is malformed")
        signature = json.dumps(function["signature"], separators=(",", ":"))
        normalized_lines.append(
            f"function={function['source']};signature={signature};body={function['body']}"
        )
        symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
    for index, primitive in enumerate(primitives):
        if not isinstance(primitive, dict):
            raise Core0Error(f"bounded manifest primitive #{index} is malformed")
        normalized_lines.append(f"primitive={primitive['stable_id']}")
    for index, iteration in enumerate(iterations):
        if not isinstance(iteration, dict):
            raise Core0Error(f"bounded manifest iteration #{index} is malformed")
        normalized_lines.append(
            f"iteration={iteration['stable_id']};budget={iteration['static_budget']};"
            f"callback={iteration['callback']}"
        )
    if normalized_text != "\n".join(normalized_lines) + "\n":
        raise Core0Error(
            "bounded-suite-normalized.txt does not match the parsed bounded manifest"
        )
    if symbols_text != "\n".join(symbol_lines) + "\n":
        raise Core0Error("symbols.txt does not match the bounded source-to-LLVM mapping")


def validate_scalar_test_abi(
    value: object, manifest: dict[str, object]
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("scalar-test-abi.json is not an object")
    contract_version = manifest.get("contract_version")
    if contract_version not in {"core0-v0.1", "core0-v0.2", "core0-v0.3"}:
        raise Core0Error("scalar test ABI suite manifest has an unsupported Core0 contract")
    expected_fields = {
        "contract_version",
        "schema_version",
        "name",
        "byte_order",
        "magic_bytes",
        "magic_word",
        "version",
        "header_bytes",
        "record_bytes",
        "maximum_arguments",
        "maximum_cases",
        "tags",
        "header_words",
        "record_layout",
        "transport_rules",
        "output_protocol",
        "suite_id",
        "source_seed",
        "runtime_seed",
    }
    _exact_keys(value, expected_fields, "scalar test ABI manifest")
    static = {
        "contract_version": contract_version,
        "schema_version": 1,
        "name": SCALAR_TEST_ABI,
        "byte_order": "little-endian",
        "magic_bytes": "4c454d4d41303032",
        "magic_word": "0x323030414d4d454c",
        "version": 1,
        "header_bytes": 128,
        "record_bytes": 136,
        "maximum_arguments": 16,
        "maximum_cases": 29,
        "tags": {"bool": 1, "u8": 2, "u32": 3, "u64": 4},
        "header_words": [
            "magic",
            "version",
            "header_bytes",
            "record_bytes",
            "suite_id",
            "batch_id",
            "root_id",
            "case_count",
            "argument_count",
            "result_tag",
            "argument_tags_0_7",
            "argument_tags_8_15",
            "source_seed",
            "runtime_seed",
            "reserved_zero",
            "reserved_zero",
        ],
        "record_layout": "case_id:u64,arguments:16xu64; unused slots zero",
        "transport_rules": (
            "Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; "
            "reject before truncation; zero-extend narrow results to u64"
        ),
        "output_protocol": {
            "banner": "LEMMA_SCALAR/1\n",
            "batch": "BATCH:<suite16>:<batch16>:<root16>:<count16>\n",
            "result": "RESULT:<case16>:<tag16>:<value16>\n",
            "end": "END:<batch16>:<count16>\n",
            "hex": "lowercase fixed-width",
        },
    }
    for field, expected in static.items():
        observed = value.get(field)
        if isinstance(expected, int) and type(observed) is not int:
            raise Core0Error(f"scalar test ABI {field} has the wrong JSON type")
        if observed != expected:
            raise Core0Error(f"scalar test ABI {field} differs from the closed wire contract")
    tags = value.get("tags")
    if not isinstance(tags, dict) or any(type(item) is not int for item in tags.values()):
        raise Core0Error("scalar test ABI tags have the wrong JSON types")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        observed = _validate_scalar_u64_hex(value.get(field), f"scalar test ABI {field}")
        if observed != manifest.get(field):
            raise Core0Error(f"scalar test ABI {field} differs from the suite manifest")
    return value


def validate_scalar_manifest_companions(
    manifest: dict[str, object], normalized_text: str, symbols_text: str
) -> None:
    roots = manifest["roots"]
    functions = manifest["functions"]
    primitives = manifest["used_primitives"]
    assert isinstance(roots, list) and isinstance(functions, list) and isinstance(primitives, list)
    normalized_lines = [f"contract={manifest['contract_version']}"]
    for root in roots:
        assert isinstance(root, dict) and isinstance(root["signature"], dict)
        signature = json.dumps(root["signature"], separators=(",", ":"))
        normalized_lines.append(
            f"root={root['root_id']};source={root['source']};signature={signature}"
        )
    symbol_lines: list[str] = []
    for function in functions:
        assert isinstance(function, dict) and isinstance(function["signature"], dict)
        signature = json.dumps(function["signature"], separators=(",", ":"))
        normalized_lines.append(
            f"function={function['source']};signature={signature};body={function['body']}"
        )
        symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
    for primitive in primitives:
        assert isinstance(primitive, dict)
        normalized_lines.append(f"primitive={primitive['stable_id']}")
    expected_normalized = "\n".join(normalized_lines) + "\n"
    expected_symbols = "\n".join(symbol_lines) + "\n"
    if normalized_text != expected_normalized:
        raise Core0Error(
            "scalar-suite-normalized.txt does not match the parsed scalar manifest"
        )
    if symbols_text != expected_symbols:
        raise Core0Error("symbols.txt does not match the scalar source-to-LLVM mapping")


def _llvm_scalar_type(ty: str) -> str:
    return {"bool": "i1", "u8": "i8", "u32": "i32", "u64": "i64"}[ty]


def _llvm_scalar_return(ty: str) -> str:
    extension = _scalar_abi_extension(ty)
    prefix = "" if extension == "none" else extension + " "
    return prefix + _llvm_scalar_type(ty)


def _llvm_scalar_parameter(ty: str) -> str:
    extension = _scalar_abi_extension(ty)
    suffix = "" if extension == "none" else " " + extension
    return _llvm_scalar_type(ty) + suffix


@lru_cache(maxsize=2)
def _ir_definition_index(ir: str) -> dict[str, tuple[str, ...]] | None:
    """Index the exact existing header/body boundary once per immutable IR text.

    Only lexical identifiers use the index. Malformed/nested definition
    boundaries and other requested symbol spellings retain the original exact
    regular-expression path. Duplicate bodies remain separate so extraction
    still requires precisely one definition. Two texts bound retained storage.
    """
    pattern = re.compile(
        r"(?P<header>^define\s+[^\n]*\{\n)(?P<body>.*?)^\}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(ir))
    if len(matches) != len(re.findall(r"^define\s", ir, re.MULTILINE)):
        return None
    index: dict[str, list[str]] = {}
    for match in matches:
        header = match.group("header")
        for symbol in set(re.findall(r"@([A-Za-z_.$][A-Za-z0-9_.$-]*)\(", header)):
            # Apply the previous symbol-specific header rule to the complete
            # captured header, including aggregate results and attributes.
            exact = rf"define\s+[^\n]*@{re.escape(symbol)}\([^\n]*\)[^\n]*\{{\n"
            if re.fullmatch(exact, header):
                index.setdefault(symbol, []).append(match.group("body"))
    return {symbol: tuple(bodies) for symbol, bodies in index.items()}


def _ir_definition_body(ir: str, symbol: str) -> str:
    if re.fullmatch(r"[A-Za-z_.$][A-Za-z0-9_.$-]*", symbol):
        index = _ir_definition_index(ir)
        if index is not None:
            bodies = index.get(symbol, ())
            if len(bodies) != 1:
                raise Core0Error(f"LLVM IR does not contain exactly one definition of {symbol}")
            return bodies[0]
    pattern = re.compile(
        rf"^define\s+[^\n]*@{re.escape(symbol)}\([^\n]*\)[^\n]*\{{\n"
        rf"(?P<body>.*?)^\}}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(ir))
    if len(matches) != 1:
        raise Core0Error(f"LLVM IR does not contain exactly one definition of {symbol}")
    return matches[0].group("body")


def validate_scalar_pre_abi(
    manifest: dict[str, object], pre_ir: str
) -> dict[str, object]:
    """Bind every source definition and direct call to the reviewed LP64 attributes."""
    functions = manifest["functions"]
    roots = manifest["roots"]
    if not isinstance(functions, list) or not isinstance(roots, list):
        raise Core0Error("scalar manifest function/root arrays are malformed")
    root_symbols = {
        str(root["llvm"]) for root in roots if isinstance(root, dict)
    }
    by_symbol: dict[str, dict[str, object]] = {}
    source_to_symbol: dict[str, str] = {}
    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(f"scalar manifest function #{function_index} is malformed")
        symbol = str(function["llvm"])
        source = str(function["source"])
        signature = function["signature"]
        if not isinstance(signature, dict):
            raise Core0Error(f"scalar manifest function {source} signature is malformed")
        args = signature["args"]
        result = signature["result"]
        if not isinstance(args, list) or not isinstance(result, str):
            raise Core0Error(f"scalar manifest function {source} signature is malformed")
        return_text = _llvm_scalar_return(result)
        parameters = ", ".join(
            f"{_llvm_scalar_parameter(arg)} %arg{index}"
            for index, arg in enumerate(args)
        )
        header = re.compile(
            rf"^define (?P<linkage>internal )?{re.escape(return_text)} "
            rf"@{re.escape(symbol)}\({re.escape(parameters)}\) nounwind noinline "
            rf'"disable\-tail\-calls"="true" \{{$',
            re.MULTILINE,
        )
        matches = list(header.finditer(pre_ir))
        if len(matches) != 1:
            raise Core0Error(
                f"pre_optimization IR definition for {source} lacks its exact LP64 ABI/noinline header"
            )
        if matches[0].group("linkage") is not None:
            raise Core0Error(
                f"dedicated scalar ABI function {source} is not externally/default-CC callable"
            )
        by_symbol[symbol] = function
        source_to_symbol[source] = symbol

    call_pattern = re.compile(
        r"\bcall\s+(?P<return>(?:(?:zeroext|signext)\s+)?i(?:1|8|32|64))\s+"
        r"@(?P<callee>[A-Za-z_.$][A-Za-z0-9_.$-]*)\((?P<args>[^)]*)\)"
    )
    call_counts = {symbol: 0 for symbol in by_symbol}
    for line in pre_ir.splitlines():
        target_match = re.search(
            r"\bcall\s+[^@\n]*@([A-Za-z_.$][A-Za-z0-9_.$-]*)\(", line
        )
        if target_match is None or target_match.group(1) not in by_symbol:
            continue
        match = call_pattern.search(line)
        if match is None or match.group("callee") != target_match.group(1):
            raise Core0Error(f"pre_optimization scalar call is not parseable: {line.strip()}")
        callee = match.group("callee")
        function = by_symbol[callee]
        signature = function["signature"]
        if not isinstance(signature, dict):
            raise Core0Error(f"scalar manifest callee {callee} signature is malformed")
        expected_args = signature["args"]
        expected_result = signature["result"]
        if not isinstance(expected_args, list) or not isinstance(expected_result, str):
            raise Core0Error(f"scalar manifest callee {callee} signature is malformed")
        if match.group("return") != _llvm_scalar_return(expected_result):
            raise Core0Error(
                f"pre_optimization call to {callee} has the wrong LP64 return attribute"
            )
        rendered_args = [] if not match.group("args") else match.group("args").split(", ")
        if len(rendered_args) != len(expected_args):
            raise Core0Error(f"pre_optimization call to {callee} has the wrong arity")
        for index, (rendered, expected_ty) in enumerate(zip(rendered_args, expected_args)):
            prefix = _llvm_scalar_parameter(expected_ty) + " "
            if not rendered.startswith(prefix):
                raise Core0Error(
                    f"pre_optimization call to {callee} argument #{index} has the wrong LP64 attribute"
                )
            operand = rendered[len(prefix) :]
            if re.fullmatch(r"(?:%[A-Za-z_.$][A-Za-z0-9_.$-]*|-?[0-9]+)", operand) is None:
                raise Core0Error(
                    f"pre_optimization call to {callee} argument #{index} is not a scalar operand"
                )
        call_counts[callee] += 1

    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(f"scalar manifest function #{function_index} is malformed")
        symbol = str(function["llvm"])
        dependencies = function["dependencies"]
        if not isinstance(dependencies, list):
            raise Core0Error(f"scalar manifest function {symbol} dependencies are malformed")
        expected_callees = {source_to_symbol[str(dependency)] for dependency in dependencies}
        body = _ir_definition_body(pre_ir, symbol)
        _definitions, _declarations, observed_callees = parse_definitions_and_calls(body)
        observed_user_callees = observed_callees & set(by_symbol)
        if observed_user_callees != expected_callees:
            raise Core0Error(
                f"pre_optimization call graph for {function['source']} differs from its manifest: "
                f"{sorted(observed_user_callees)!r} != {sorted(expected_callees)!r}"
            )

    main_body = _ir_definition_body(pre_ir, "core0_main")
    _definitions, _declarations, main_calls = parse_definitions_and_calls(main_body)
    if main_calls & set(by_symbol) != root_symbols:
        raise Core0Error("typed scalar harness call closure differs from the exact root catalog")
    for root_symbol in root_symbols:
        if len(re.findall(rf"\bcall\s+[^\n]*@{re.escape(root_symbol)}\(", main_body)) != 1:
            raise Core0Error(
                f"typed scalar harness does not call root {root_symbol} exactly once"
            )
    unused = sorted(symbol for symbol, count in call_counts.items() if count == 0)
    if unused:
        raise Core0Error(f"scalar suite contains functions with no typed call site: {unused!r}")
    return {
        "function_count": len(functions),
        "root_count": len(roots),
        "call_site_count": sum(call_counts.values()),
        "call_sites_by_symbol": call_counts,
    }


def validate_scalar_post_noinline(
    manifest: dict[str, object], post_ir: str
) -> None:
    functions = manifest["functions"]
    if not isinstance(functions, list):
        raise Core0Error("scalar manifest function array is malformed")
    attribute_groups = {
        int(identifier): body
        for identifier, body in re.findall(
            r"^attributes #(\d+) = \{([^\n]*)\}$", post_ir, re.MULTILINE
        )
    }
    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(f"scalar manifest function #{function_index} is malformed")
        symbol = str(function["llvm"])
        header = re.search(
            rf"^define\s+[^\n]*@{re.escape(symbol)}\([^\n]*\)(?P<suffix>[^\n]*)\{{$",
            post_ir,
            re.MULTILINE,
        )
        if header is None:
            raise Core0Error(f"optimized IR removed required noinline scalar function {symbol}")
        group = re.search(r"#(\d+)(?:\s|$)", header.group("suffix"))
        inline_noinline = re.search(r"\bnoinline\b", header.group("suffix")) is not None
        grouped_noinline = (
            group is not None
            and re.search(
                r"\bnoinline\b", attribute_groups.get(int(group.group(1)), "")
            )
            is not None
        )
        if not inline_noinline and not grouped_noinline:
            raise Core0Error(f"optimized scalar function {symbol} lost its noinline attribute")


def _structured_ir_blocks(body: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in body.splitlines():
        label = re.fullmatch(r"([A-Za-z_.$][A-Za-z0-9_.$-]*):", raw_line.strip())
        if label is not None:
            current = label.group(1)
            if current in blocks:
                raise Core0Error(f"structured LLVM repeats block label {current!r}")
            blocks[current] = []
        elif raw_line.strip():
            if current is None:
                raise Core0Error("structured LLVM instruction precedes its first block label")
            blocks[current].append(raw_line.strip())
    if not blocks:
        raise Core0Error("structured LLVM function has no parseable blocks")
    return blocks


def _structured_successors(blocks: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
    """Parse the closed branch syntax rendered by Lemma's structured LLVM IR."""
    successors: dict[str, tuple[str, ...]] = {}
    for label, lines in blocks.items():
        if not lines:
            raise Core0Error(f"structured LLVM block {label!r} is empty")
        terminator = lines[-1]
        conditional = re.fullmatch(
            r"br i1 [^,]+, label %([A-Za-z_.$][A-Za-z0-9_.$-]*), label %"
            r"([A-Za-z_.$][A-Za-z0-9_.$-]*)",
            terminator,
        )
        jump = re.fullmatch(
            r"br label %([A-Za-z_.$][A-Za-z0-9_.$-]*)", terminator
        )
        if conditional is not None:
            successors[label] = conditional.groups()
        elif jump is not None:
            successors[label] = (jump.group(1),)
        else:
            successors[label] = ()
    unknown = {
        target
        for targets in successors.values()
        for target in targets
        if target not in blocks
    }
    if unknown:
        raise Core0Error(
            f"structured LLVM branches to unknown blocks: {sorted(unknown)!r}"
        )
    return successors


def _structured_predecessors(
    successors: dict[str, tuple[str, ...]],
) -> dict[str, set[str]]:
    predecessors = {label: set() for label in successors}
    for source, targets in successors.items():
        for target in targets:
            predecessors[target].add(source)
    return predecessors


def _structured_reachable(
    successors: dict[str, tuple[str, ...]], start: str, target: str
) -> bool:
    pending = [start]
    visited: set[str] = set()
    while pending:
        label = pending.pop()
        if label == target:
            return True
        if label in visited:
            continue
        visited.add(label)
        pending.extend(successors.get(label, ()))
    return False


def _normalized_shift_count_arguments(
    normalized: str,
) -> dict[tuple[str, str], list[str]]:
    """Map each closed source shift to the LLVM parameter carrying its count.

    The exact Gate 3 source catalog admits direct parameter operands for shifts.
    Rejecting any other normalized shape keeps this independent audit fail-closed
    instead of guessing how an arbitrary source expression maps to SSA.
    """
    result: dict[tuple[str, str], list[str]] = {}
    pattern = re.compile(
        r"\(bin (shl|lshr) (u8|u32|u64) "
        r"\(var [0-9]+ (?:u8|u32|u64)\) "
        r"\(var ([0-9]+) \2\)\)"
    )
    for operation, source_ty, variable in pattern.findall(normalized):
        llvm_ty = {"u8": "i8", "u32": "i32", "u64": "i64"}[source_ty]
        result.setdefault((operation, llvm_ty), []).append(f"%arg{variable}")
    return result


def validate_cfg_pre_semantics(
    manifest: dict[str, object], pre_ir: str
) -> dict[str, object]:
    """Independently audit v0.2 source CFGs and poison-sensitive operations."""
    functions = manifest["functions"]
    assert isinstance(functions, list)
    division_records: list[dict[str, object]] = []
    shift_records: list[dict[str, object]] = []
    source_branch_functions = 0
    for function in functions:
        assert isinstance(function, dict)
        symbol = str(function["llvm"])
        source = str(function["source"])
        normalized = str(function["body"])
        body = _ir_definition_body(pre_ir, symbol)
        if re.search(r"\bselect\b", body):
            raise Core0Error(f"v0.2 source function {source} contains eager LLVM select")
        blocks = _structured_ir_blocks(body)
        successors = _structured_successors(blocks)
        predecessors = _structured_predecessors(successors)
        normalized_shift_counts = _normalized_shift_count_arguments(normalized)
        if "(ite " in normalized:
            source_branch_functions += 1
            if "br i1 " not in body or not any(
                re.search(r"\bphi\s+i(?:1|8|32|64)\b", line)
                for lines in blocks.values()
                for line in lines
            ):
                raise Core0Error(
                    f"v0.2 source conditional {source} lacks branch/phi lowering"
                )

        guard_edges: list[tuple[str, str, str, str, str]] = []
        for guard_block, lines in blocks.items():
            for index, line in enumerate(lines):
                match = re.fullmatch(
                    r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = icmp eq "
                    r"(i(?:8|32|64)) ([^,]+), 0",
                    line,
                )
                if match is None or index + 1 >= len(lines):
                    continue
                branch = re.fullmatch(
                    rf"br i1 %{re.escape(match.group(1))}, label %"
                    r"([A-Za-z_.$][A-Za-z0-9_.$-]*), label %"
                    r"([A-Za-z_.$][A-Za-z0-9_.$-]*)",
                    lines[index + 1],
                )
                if branch is not None:
                    guard_edges.append(
                        (
                            guard_block,
                            match.group(2),
                            match.group(3),
                            branch.group(1),
                            branch.group(2),
                        )
                    )

        definitions: dict[str, tuple[str, int, str, str, str]] = {}
        for block, lines in blocks.items():
            for index, line in enumerate(lines):
                definition = re.fullmatch(
                    r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = and "
                    r"(i(?:8|32|64)) ([^,]+), ([0-9]+)",
                    line,
                )
                if definition is not None:
                    definitions[definition.group(1)] = (
                        block,
                        index,
                        definition.group(2),
                        definition.group(3).strip(),
                        definition.group(4),
                    )

        for block, lines in blocks.items():
            for index, line in enumerate(lines):
                dangerous = re.fullmatch(
                    r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = (udiv|urem) "
                    r"(i(?:8|32|64)) ([^,]+), (.+)",
                    line,
                )
                if dangerous is not None:
                    operation, ty, divisor = dangerous.group(1, 2, 4)
                    matching_guards = [
                        edge for edge in guard_edges
                        if edge[1] == ty and edge[2] == divisor and edge[4] == block
                    ]
                    if len(matching_guards) != 1:
                        raise Core0Error(
                            f"{source} {operation} in %{block} is not the unique false "
                            "successor of an exact divisor-zero guard"
                        )
                    if matching_guards[0][3] == block:
                        raise Core0Error(f"{source} {operation} executes on the zero edge")
                    guard_block = matching_guards[0][0]
                    if _structured_reachable(successors, matching_guards[0][3], block):
                        raise Core0Error(
                            f"{source} {operation} block %{block} is reachable from "
                            "the divisor-zero successor"
                        )
                    if predecessors[block] != {guard_block}:
                        raise Core0Error(
                            f"{source} {operation} block %{block} has an unguarded "
                            f"predecessor set {sorted(predecessors[block])!r}; expected "
                            f"only %{guard_block}"
                        )
                    division_records.append(
                        {
                            "source": source,
                            "operation": operation,
                            "type": ty,
                            "guard_block": matching_guards[0][0],
                            "nonzero_block": block,
                        }
                    )
                shift = re.fullmatch(
                    r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = (shl|lshr) "
                    r"(i(?:8|32|64)) [^,]+, %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
                    line,
                )
                if shift is not None:
                    operation, ty, count_name = shift.groups()
                    definition = definitions.get(count_name)
                    expected_mask = {"i8": "7", "i32": "31", "i64": "63"}[ty]
                    expected_counts = normalized_shift_counts.get((operation, ty), [])
                    if (
                        definition is None
                        or definition[0] != block
                        or definition[1] >= index
                        or definition[2] != ty
                        or definition[3] not in expected_counts
                        or definition[4] != expected_mask
                    ):
                        raise Core0Error(
                            f"{source} {operation} count is not produced by the exact "
                            f"same-block source-count `{ty} and {expected_mask}` mask"
                        )
                    expected_counts.remove(definition[3])
                    shift_records.append(
                        {
                            "source": source,
                            "operation": operation,
                            "type": ty,
                            "block": block,
                            "mask": int(expected_mask),
                            "source_count": definition[3],
                        }
                    )
        remaining_shift_counts = {
            f"{operation}/{ty}": values
            for (operation, ty), values in normalized_shift_counts.items()
            if values
        }
        if remaining_shift_counts:
            raise Core0Error(
                f"{source} normalized shifts lack exact emitted masks: "
                f"{remaining_shift_counts!r}"
            )
    if not division_records or not shift_records or source_branch_functions == 0:
        raise Core0Error("v0.2 structured suite lacks division, shifts, or source conditionals")
    observed_divisions = {str(record["operation"]) for record in division_records}
    observed_shifts = {str(record["operation"]) for record in shift_records}
    if observed_divisions != {"udiv", "urem"} or observed_shifts != {"shl", "lshr"}:
        raise Core0Error("v0.2 structured suite does not cover every dangerous operation")
    return {
        "source_selects": 0,
        "source_branch_functions": source_branch_functions,
        "guarded_division_remainder": division_records,
        "masked_shifts": shift_records,
    }


def _only_matching_line(
    lines: list[str], pattern: str, context: str
) -> re.Match[str]:
    matches = [match for line in lines if (match := re.fullmatch(pattern, line))]
    if len(matches) != 1:
        raise Core0Error(f"{context} expected exactly one `{pattern}` instruction")
    return matches[0]


def validate_loop_pre_semantics(
    manifest: dict[str, object], pre_ir: str
) -> dict[str, object]:
    """Audit each v0.3 source iteration against the exact structured loop CFG."""
    functions = manifest.get("functions")
    if not isinstance(functions, list):
        raise Core0Error("bounded suite function manifest is malformed")
    source_to_symbol = {
        str(function["source"]): str(function["llvm"])
        for function in functions
        if isinstance(function, dict)
    }
    site_pattern = re.compile(
        r"\(bounded-fold-u32 budget=([0-9]+) "
        r"callback=([A-Za-z_][A-Za-z0-9_.]*) "
        r"count=\(var 0 u32\) initial=\(var 1 u32\)\)"
    )
    records: list[dict[str, object]] = []
    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(
                f"bounded suite function #{function_index} is malformed during loop audit"
            )
        source = str(function["source"])
        symbol = str(function["llvm"])
        normalized = str(function["body"])
        sites = site_pattern.findall(normalized)
        if "(bounded-fold-u32 " in normalized and len(sites) != 1:
            raise Core0Error(
                f"bounded source function {source} has a non-canonical count/initial site"
            )
        if not sites:
            continue
        if len(sites) != 1:
            raise Core0Error(f"bounded source function {source} has multiple loop sites")
        budget_text, callback = sites[0]
        budget = int(budget_text, 10)
        if not 0 <= budget <= 256:
            raise Core0Error(f"bounded source function {source} budget is outside 0..256")
        callback_symbol = source_to_symbol.get(callback)
        if callback_symbol is None:
            raise Core0Error(
                f"bounded source function {source} callback {callback} is outside the closure"
            )
        body = _ir_definition_body(pre_ir, symbol)
        if re.search(r"\bselect\b", body):
            raise Core0Error(f"bounded source function {source} contains eager LLVM select")
        blocks = _structured_ir_blocks(body)
        successors = _structured_successors(blocks)
        predecessors = _structured_predecessors(successors)

        guards: list[tuple[str, re.Match[str]]] = []
        for label, lines in blocks.items():
            for line in lines:
                match = re.fullmatch(
                    r"%(loop\.within-budget[0-9]+) = icmp ule i32 (%arg0), ([0-9]+)",
                    line,
                )
                if match is not None:
                    guards.append((label, match))
        if len(guards) != 1:
            raise Core0Error(f"bounded source function {source} lacks one exact budget guard")
        guard_label, guard = guards[0]
        if int(guard.group(3), 10) != budget:
            raise Core0Error(
                f"bounded source function {source} LLVM budget differs from source literal"
            )
        guard_lines = blocks[guard_label]
        branch = _only_matching_line(
            guard_lines,
            rf"br i1 %{re.escape(guard.group(1))}, label %"
            r"(loop\.preheader\.[0-9]+), label %(loop\.exhausted\.[0-9]+)",
            f"bounded source function {source} budget guard",
        )
        preheader, exhausted = branch.group(1), branch.group(2)
        if successors[guard_label] != (preheader, exhausted):
            raise Core0Error(f"bounded source function {source} inverts its budget edges")
        if predecessors.get(guard_label) != set():
            raise Core0Error(
                f"bounded source function {source} budget guard is not the entry block"
            )

        preheader_lines = blocks.get(preheader)
        exhausted_lines = blocks.get(exhausted)
        if preheader_lines is None or exhausted_lines is None:
            raise Core0Error(f"bounded source function {source} lacks budget successor blocks")
        if predecessors.get(preheader) != {guard_label} or predecessors.get(exhausted) != {
            guard_label
        }:
            raise Core0Error(
                f"bounded source function {source} budget successors have bypass predecessors"
            )
        header_jump = _only_matching_line(
            preheader_lines,
            r"br label %(loop\.header\.[0-9]+)",
            f"bounded source function {source} preheader",
        )
        header = header_jump.group(1)
        exhausted_initial = _only_matching_line(
            exhausted_lines,
            r"%(loop\.exhausted-initial[0-9]+) = zext i32 %arg1 to i64",
            f"bounded source function {source} exhaustion payload",
        ).group(1)
        exhausted_tag = _only_matching_line(
            exhausted_lines,
            rf"%(loop\.exhausted-tag[0-9]+) = or i64 "
            rf"%{re.escape(exhausted_initial)}, (?:9223372036854775808|-9223372036854775808)",
            f"bounded source function {source} exhaustion tag",
        ).group(1)
        outcome_jump = _only_matching_line(
            exhausted_lines,
            r"br label %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
            f"bounded source function {source} exhausted edge",
        )
        outcome = outcome_jump.group(1)

        header_lines = blocks.get(header)
        if header_lines is None:
            raise Core0Error(f"bounded source function {source} lacks a loop header")
        index_phi = _only_matching_line(
            header_lines,
            rf"%(loop\.index[0-9]+) = phi i32 \[ 0, %{re.escape(preheader)} \], "
            r"\[ %(loop\.next-index[0-9]+), %(loop\.body\.[0-9]+) \]",
            f"bounded source function {source} index phi",
        )
        index, next_index, body_label = index_phi.groups()
        accumulator_phi = _only_matching_line(
            header_lines,
            rf"%(loop\.accumulator[0-9]+) = phi i32 \[ %arg1, %{re.escape(preheader)} \], "
            rf"\[ %(loop\.next-accumulator[0-9]+), %{re.escape(body_label)} \]",
            f"bounded source function {source} accumulator phi",
        )
        accumulator, next_accumulator = accumulator_phi.groups()
        continue_name = _only_matching_line(
            header_lines,
            rf"%(loop\.continue[0-9]+) = icmp ult i32 %{re.escape(index)}, %arg0",
            f"bounded source function {source} runtime-count comparison",
        ).group(1)
        continue_branch = _only_matching_line(
            header_lines,
            rf"br i1 %{re.escape(continue_name)}, label %{re.escape(body_label)}, "
            r"label %(loop\.done\.[0-9]+)",
            f"bounded source function {source} loop branch",
        )
        done = continue_branch.group(1)

        body_lines = blocks.get(body_label)
        if body_lines is None:
            raise Core0Error(f"bounded source function {source} lacks a loop body")
        if _structured_reachable(successors, exhausted, body_label):
            raise Core0Error(
                f"bounded source function {source} exhaustion path reaches its callback"
            )
        if re.fullmatch(r"loop\.outcome\.[0-9]+", outcome) is None:
            raise Core0Error(
                f"bounded source function {source} exhausted edge does not target its outcome"
            )
        _only_matching_line(
            body_lines,
            rf"%{re.escape(next_accumulator)} = call signext i32 "
            rf"@{re.escape(callback_symbol)}\(i32 signext %{re.escape(index)}, "
            rf"i32 signext %{re.escape(accumulator)}\)",
            f"bounded source function {source} callback call",
        )
        _only_matching_line(
            body_lines,
            rf"%{re.escape(next_index)} = add i32 %{re.escape(index)}, 1",
            f"bounded source function {source} index increment",
        )
        _only_matching_line(
            body_lines,
            rf"br label %{re.escape(header)}",
            f"bounded source function {source} backedge",
        )
        callback_calls = re.findall(
            rf"\bcall signext i32 @{re.escape(callback_symbol)}\(", body
        )
        if len(callback_calls) != 1:
            raise Core0Error(
                f"bounded source function {source} must contain exactly one direct callback call"
            )

        done_lines = blocks.get(done)
        if done_lines is None:
            raise Core0Error(f"bounded source function {source} lacks a done block")
        loop_value = _only_matching_line(
            done_lines,
            rf"%(loop\.value[0-9]+) = zext i32 %{re.escape(accumulator)} to i64",
            f"bounded source function {source} successful outcome",
        ).group(1)
        _only_matching_line(
            done_lines,
            rf"br label %{re.escape(outcome)}",
            f"bounded source function {source} done edge",
        )
        outcome_lines = blocks.get(outcome)
        if outcome_lines is None:
            raise Core0Error(f"bounded source function {source} lacks an outcome block")
        _only_matching_line(
            outcome_lines,
            rf"%(loop\.result[0-9]+) = phi i64 "
            rf"\[ %{re.escape(loop_value)}, %{re.escape(done)} \], "
            rf"\[ %{re.escape(exhausted_tag)}, %{re.escape(exhausted)} \]",
            f"bounded source function {source} outcome phi",
        )

        if predecessors.get(header) != {preheader, body_label}:
            raise Core0Error(
                f"bounded source function {source} loop header has the wrong predecessor set"
            )
        if predecessors.get(body_label) != {header} or predecessors.get(done) != {header}:
            raise Core0Error(
                f"bounded source function {source} loop body/done has a bypass predecessor"
            )
        backedge_sources = {
            block for block, targets in successors.items() if header in targets and block != preheader
        }
        if backedge_sources != {body_label}:
            raise Core0Error(
                f"bounded source function {source} does not have exactly one body backedge"
            )
        if predecessors.get(outcome) != {done, exhausted}:
            raise Core0Error(
                f"bounded source function {source} outcome has the wrong predecessor set"
            )
        records.append(
            {
                "source": source,
                "llvm": symbol,
                "budget": budget,
                "callback": callback,
                "callback_llvm": callback_symbol,
                "guard_block": guard_label,
                "header_block": header,
                "body_block": body_label,
                "outcome_block": outcome,
                "counter": "u32-ascending-zero-based",
                "accumulator": "u32",
                "exhaustion_callback_reachable": False,
            }
        )
    if len(records) != len(LOOP_ITERATION_SITES):
        raise Core0Error(
            "bounded suite emitted the wrong number of source loop CFGs: "
            f"{len(records)} != {len(LOOP_ITERATION_SITES)}"
        )
    if {(int(row["budget"]), str(row["callback"])) for row in records} != LOOP_ITERATION_SITES:
        raise Core0Error("bounded LLVM loop sites differ from the closed source site catalog")
    return {"loop_count": len(records), "loops": records}


def validate_v03_scalar_domains(
    manifest: dict[str, object], pre_ir: str
) -> dict[str, object]:
    """Retain v0.2 shift/division premises inside every v0.3 callback/helper."""
    functions = manifest.get("functions")
    if not isinstance(functions, list):
        raise Core0Error("bounded suite function manifest is malformed")
    shifts: list[dict[str, object]] = []
    divisions: list[dict[str, object]] = []
    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(
                f"bounded suite function #{function_index} is malformed during domain audit"
            )
        source = str(function["source"])
        body = _ir_definition_body(pre_ir, str(function["llvm"]))
        blocks = _structured_ir_blocks(body)
        successors = _structured_successors(blocks)
        predecessors = _structured_predecessors(successors)
        masks: dict[str, tuple[str, int, str, str]] = {}
        guards: list[tuple[str, str, str, str, str]] = []
        for block, lines in blocks.items():
            for index, line in enumerate(lines):
                mask = re.fullmatch(
                    r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = and "
                    r"(i(?:8|32|64)) ([^,]+), (7|31|63)",
                    line,
                )
                if mask is not None:
                    masks[mask.group(1)] = (
                        block, index, mask.group(2), mask.group(4)
                    )
                zero = re.fullmatch(
                    r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = icmp eq "
                    r"(i(?:8|32|64)) ([^,]+), 0",
                    line,
                )
                if zero is not None and index + 1 < len(lines):
                    branch = re.fullmatch(
                        rf"br i1 %{re.escape(zero.group(1))}, label %"
                        r"([A-Za-z_.$][A-Za-z0-9_.$-]*), label %"
                        r"([A-Za-z_.$][A-Za-z0-9_.$-]*)",
                        lines[index + 1],
                    )
                    if branch is not None:
                        guards.append(
                            (block, zero.group(2), zero.group(3), branch.group(1), branch.group(2))
                        )
        for block, lines in blocks.items():
            for index, line in enumerate(lines):
                shift = re.fullmatch(
                    r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = (shl|lshr) "
                    r"(i(?:8|32|64)) [^,]+, %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
                    line,
                )
                if shift is not None:
                    operation, ty, count_name = shift.groups()
                    definition = masks.get(count_name)
                    expected_mask = {"i8": "7", "i32": "31", "i64": "63"}[ty]
                    if (
                        definition is None
                        or definition[0] != block
                        or definition[1] >= index
                        or definition[2] != ty
                        or definition[3] != expected_mask
                    ):
                        raise Core0Error(
                            f"{source} {operation} count is not produced by an exact "
                            f"same-block `{ty} and {expected_mask}` mask"
                        )
                    shifts.append(
                        {
                            "source": source,
                            "operation": operation,
                            "type": ty,
                            "block": block,
                            "mask": int(expected_mask),
                        }
                    )
                dangerous = re.fullmatch(
                    r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = (udiv|urem) "
                    r"(i(?:8|32|64)) [^,]+, (.+)",
                    line,
                )
                if dangerous is not None:
                    operation, ty, divisor = dangerous.groups()
                    matching = [
                        guard for guard in guards
                        if guard[1] == ty and guard[2] == divisor and guard[4] == block
                    ]
                    if len(matching) != 1:
                        raise Core0Error(
                            f"{source} {operation} is not the false successor of its exact zero guard"
                        )
                    guard = matching[0]
                    if _structured_reachable(successors, guard[3], block):
                        raise Core0Error(
                            f"{source} {operation} is reachable from its divisor-zero edge"
                        )
                    if predecessors[block] != {guard[0]}:
                        raise Core0Error(
                            f"{source} {operation} block has an unguarded predecessor"
                        )
                    divisions.append(
                        {
                            "source": source,
                            "operation": operation,
                            "type": ty,
                            "guard_block": guard[0],
                            "nonzero_block": block,
                        }
                    )
    if not shifts:
        raise Core0Error("bounded suite lacks its required masked shift callback")
    return {"masked_shifts": shifts, "guarded_division_remainder": divisions}


def validate_optimizer_disjoint(
    post_ir: str, *, expected_exhaustion_tags: int
) -> dict[str, object]:
    """Inventory every optimizer-inferred ``or disjoint`` and prove its premise.

    LLVM's ``disjoint`` spelling is poison-producing if the operands overlap.  The
    pinned optimizer currently infers it for hexadecimal digit construction and,
    for Gate 4, for the exhaustion tag.  Keep both in a closed set and record the
    local range fact that proves each inference sound.
    """
    definitions, _declarations, _calls = parse_definitions_and_calls(post_ir)
    records: list[dict[str, object]] = []
    exhaustion_tags = 0
    token_count = len(re.findall(r"\bdisjoint\b", post_ir))
    instruction = re.compile(
        r"^\s*%([A-Za-z_.$][A-Za-z0-9_.$-]*) = or disjoint i64 "
        r"%([A-Za-z_.$][A-Za-z0-9_.$-]*), "
        r"(48|9223372036854775808|-9223372036854775808)\s*$"
    )
    for symbol in sorted(definitions):
        body = _ir_definition_body(post_ir, symbol)
        for line in body.splitlines():
            if re.search(r"\bdisjoint\b", line) is None:
                continue
            match = instruction.fullmatch(line)
            if match is None:
                raise Core0Error(
                    f"optimized IR contains an unaudited disjoint instruction: {line.strip()}"
                )
            result, operand, constant = match.groups()
            if constant in {"9223372036854775808", "-9223372036854775808"}:
                producer = re.search(
                    rf"^\s*%{re.escape(operand)} = zext i32 "
                    r"[^\n]+ to i64\s*$",
                    body,
                    re.MULTILINE,
                )
                if producer is None:
                    raise Core0Error(
                        "optimized exhaustion-tag disjoint operand is not proven by "
                        "an exact i32-to-i64 zero extension"
                    )
                exhaustion_tags += 1
                records.append(
                    {
                        "function": symbol,
                        "result": result,
                        "kind": "exhaustion-tag",
                        "premise": "zext-u32-clears-bits-32-through-63; tag-uses-bit-63",
                        "constant": "0x8000000000000000",
                    }
                )
                continue
            low_nibble = re.search(
                rf"^\s*%{re.escape(operand)} = (?:and i64 [^\n]+, 15|"
                r"lshr i64 [^\n]+, 60)\s*$",
                body,
                re.MULTILINE,
            )
            if low_nibble is None:
                raise Core0Error(
                    "optimized hexadecimal disjoint operand is not proven to be a low nibble"
                )
            records.append(
                {
                    "function": symbol,
                    "result": result,
                    "kind": "hexadecimal-digit",
                    "premise": "low-nibble-bits-0-through-3; ascii-0x30-bits-4-and-5",
                    "constant": "0x30",
                }
            )
    if len(records) != token_count:
        raise Core0Error(
            "optimized IR disjoint inventory does not cover every poison-sensitive token"
        )
    if exhaustion_tags != expected_exhaustion_tags:
        raise Core0Error(
            "optimized IR exhaustion-tag disjoint count differs from the exact root "
            f"catalog: {exhaustion_tags} != {expected_exhaustion_tags}"
        )
    return {
        "instruction_count": len(records),
        "exhaustion_tag_count": exhaustion_tags,
        "all_operands_proven_disjoint": True,
        "instructions": records,
    }


def validate_memory_optimizer_flags(post_ir: str, optimization: str) -> dict[str, object]:
    """Close the pinned optimizer's Gate 5 poison-sensitive flag inventory.

    The source renderer emits none of these flags.  At O2 LLVM converts proven
    region-base additions to disjoint ORs, creates five bounded switch tables,
    and retains the existing hexadecimal formatter idiom.  This audit accepts
    only that exact inventory and checks that every non-format OR either feeds
    an ``inttoptr`` address (possibly through one other OR) or is the one
    byte-packing expression whose shifted/high and zero-extended/low bytes do
    not overlap.
    """
    token_counts = {
        flag: len(re.findall(rf"\b{flag}\b", post_ir))
        for flag in ("nsw", "nuw", "inbounds", "disjoint")
    }
    if optimization == "O0":
        if any(token_counts.values()):
            raise Core0Error(
                f"O0 memory IR unexpectedly contains optimizer flags: {token_counts!r}"
            )
        return {"optimization": optimization, "counts": token_counts, "records": []}

    inbounds_pattern = re.compile(
        r"^\s*%switch\.gep = getelementptr inbounds \[(3|4) x i64\], "
        r"ptr @switch\.table\.core0_action_(6|11), i64 0, i64 %[A-Za-z0-9_.$-]+\s*$"
    )
    inbounds_lines = [
        line for line in post_ir.splitlines() if re.search(r"\binbounds\b", line)
    ]
    if len(inbounds_lines) != 5 or any(
        inbounds_pattern.fullmatch(line) is None for line in inbounds_lines
    ):
        raise Core0Error(
            "O2 memory IR inbounds inventory differs from the five closed switch-table GEPs"
        )
    expected_tables = {
        "6": (3, [2155876352, 2164260864, 2155884544]),
        "11": (4, [2155876352, 2164260864, 2155884544, 2155892736]),
    }
    for suffix, (size, values) in expected_tables.items():
        rendered = ", ".join(f"i64 {value}" for value in values)
        declaration = (
            f"@switch.table.core0_action_{suffix} = private unnamed_addr constant "
            f"[{size} x i64] [{rendered}], align 8"
        )
        if post_ir.count(declaration) != 1:
            raise Core0Error(f"O2 memory switch table {suffix} differs from its closed bases")

    definitions, _declarations, _calls = parse_definitions_and_calls(post_ir)
    records: list[dict[str, object]] = []
    hexadecimal_count = 0
    address_count = 0
    address_intermediate_count = 0
    byte_pack_count = 0
    or_pattern = re.compile(
        r"^\s*%([A-Za-z_.$][A-Za-z0-9_.$-]*) = or disjoint i64 ([^,]+), (.+?)\s*$"
    )
    for symbol in sorted(definitions):
        body = _ir_definition_body(post_ir, symbol)
        matches = [
            match for line in body.splitlines()
            if "or disjoint i64" in line and (match := or_pattern.fullmatch(line))
        ]
        if len(matches) != len(
            [line for line in body.splitlines() if "or disjoint i64" in line]
        ):
            raise Core0Error(f"O2 memory function {symbol} has an unparseable disjoint OR")
        results = {match.group(1) for match in matches}
        address_results = {
            result
            for result in results
            if re.search(rf"\binttoptr i64 %{re.escape(result)} to ptr\b", body)
        }
        changed = True
        while changed:
            changed = False
            for match in matches:
                result, left, right = match.groups()
                if result not in address_results:
                    continue
                for operand in (left.strip(), right.strip()):
                    if operand.startswith("%") and operand[1:] in results:
                        before = len(address_results)
                        address_results.add(operand[1:])
                        changed = changed or len(address_results) != before
        for match in matches:
            result, left, right = match.groups()
            if right in {"48", "9223372036854775808", "-9223372036854775808"}:
                if right != "48":
                    raise Core0Error("Gate 5 O2 unexpectedly contains an exhaustion-tag OR")
                operand = left.removeprefix("%")
                producer = re.search(
                    rf"^\s*%{re.escape(operand)} = (?:and i64 [^\n]+, 15|"
                    r"lshr i64 [^\n]+, 60)\s*$",
                    body,
                    re.MULTILINE,
                )
                if producer is None:
                    raise Core0Error("Gate 5 hexadecimal disjoint operand is not a low nibble")
                hexadecimal_count += 1
                kind = "hexadecimal-digit"
            elif result in address_results:
                kind = "checked-address" if ".address." in result else "checked-address-stage"
                if kind == "checked-address":
                    address_count += 1
                else:
                    address_intermediate_count += 1
            elif result == "bin81":
                high = left.removeprefix("%")
                low = right.removeprefix("%")
                high_match = re.search(
                    rf"^\s*%{re.escape(high)} = shl nuw nsw i64 "
                    r"%([A-Za-z0-9_.$-]+), 8\s*$",
                    body,
                    re.MULTILINE,
                )
                low_match = re.search(
                    rf"^\s*%{re.escape(low)} = zext i8 [^\n]+ to i64\s*$",
                    body,
                    re.MULTILINE,
                )
                if high_match is None or low_match is None or re.search(
                    rf"^\s*%{re.escape(high_match.group(1))} = zext i8 [^\n]+ to i64\s*$",
                    body,
                    re.MULTILINE,
                ) is None:
                    raise Core0Error("Gate 5 byte-pack disjoint operands lack exact byte ranges")
                byte_pack_count += 1
                kind = "two-byte-pack"
            else:
                raise Core0Error(
                    f"O2 memory IR contains an unaudited disjoint OR in {symbol}: %{result}"
                )
            records.append({"function": symbol, "result": result, "kind": kind})
    if (
        len(records) != 54
        or hexadecimal_count != 16
        or address_count != 35
        or address_intermediate_count != 2
        or byte_pack_count != 1
        or token_counts["disjoint"] != len(records)
    ):
        raise Core0Error(
            "O2 memory disjoint inventory differs from the closed 16/35/2/1 catalog"
        )
    return {
        "optimization": optimization,
        "counts": token_counts,
        "inbounds_switch_tables": len(inbounds_lines),
        "hexadecimal_digits": hexadecimal_count,
        "checked_addresses": address_count,
        "checked_address_stages": address_intermediate_count,
        "two_byte_packs": byte_pack_count,
        "all_disjoint_operands_classified": True,
        "records": records,
    }


def _disassembly_function(disassembly: str, symbol: str) -> str:
    marker = f"<{symbol}>:"
    parts = disassembly.split(marker, 1)
    if len(parts) != 2:
        raise Core0Error(f"disassembly lacks required scalar ABI symbol {symbol}")
    return parts[1].split("\n\n", 1)[0]


def _parse_assembly_offset(text: str) -> int:
    try:
        return int(text, 0)
    except ValueError as error:
        raise Core0Error(f"cannot parse audited RISC-V stack offset {text!r}") from error


def _stack_frame_size(body: str, symbol: str, *, required: bool) -> int:
    match = re.search(r"\baddi\s+sp,\s*sp,\s*(-(?:0x[0-9a-f]+|[0-9]+))\b", body)
    if match is None:
        if required:
            raise Core0Error(f"scalar ABI caller {symbol} has no inspectable stack frame")
        return 0
    size = -_parse_assembly_offset(match.group(1))
    if size <= 0 or size % 16 != 0:
        raise Core0Error(
            f"scalar ABI function {symbol} has a non-16-byte-aligned frame size: {size}"
        )
    return size


def validate_scalar_abi_disassembly(
    manifest: dict[str, object], disassembly: str, optimization: str
) -> dict[str, object]:
    functions = manifest["functions"]
    assert isinstance(functions, list)
    source_to_symbol = {
        str(function["source"]): str(function["llvm"])
        for function in functions
        if isinstance(function, dict)
    }
    caller = source_to_symbol.get(SCALAR_ABI_ROOT)
    callee = source_to_symbol.get(SCALAR_ABI_CALLEE)
    if caller is None or callee is None:
        raise Core0Error("scalar ABI anchor source identities are absent from the manifest")
    caller_body = _disassembly_function(disassembly, caller)
    callee_body = _disassembly_function(disassembly, callee)
    frame_size = _stack_frame_size(caller_body, caller, required=True)
    call = re.search(
        rf"\b(?:jal|jalr)\b[^\n]*<{re.escape(callee)}>", caller_body
    )
    if call is None:
        raise Core0Error(
            f"{optimization} disassembly lacks a real link-register call from {caller} to {callee}"
        )
    before_call = caller_body[: call.start()]
    after_call = caller_body[call.end() :]
    if re.search(
        rf"\baddi\s+sp,\s*sp,\s*(?:0x{frame_size:x}|{frame_size})\b", after_call
    ) is None:
        raise Core0Error(
            f"{optimization} scalar ABI caller does not restore its aligned frame after the call"
        )

    incoming_registers: dict[int, str] = {}
    for register, raw_offset in re.findall(
        r"\bld\s+([a-z][a-z0-9]*),\s*(0x[0-9a-f]+|[0-9]+)\(sp\)", before_call
    ):
        incoming_registers[_parse_assembly_offset(raw_offset)] = register
    expected_incoming = {
        frame_size: 0,
        frame_size + 8: 8,
    }
    aliases = {"sp"}
    aliases.update(
        re.findall(r"\bmv\s+([a-z][a-z0-9]*),\s*sp\b", before_call)
    )
    outgoing: dict[int, str] = {}
    for register, raw_offset, base in re.findall(
        r"\bsd\s+([a-z][a-z0-9]*),\s*(0x[0-9a-f]+|[0-9]+)\(([a-z][a-z0-9]*)\)",
        before_call,
    ):
        if base in aliases:
            outgoing[_parse_assembly_offset(raw_offset)] = register
    for incoming_offset, outgoing_offset in expected_incoming.items():
        register = incoming_registers.get(incoming_offset)
        if register is None or outgoing.get(outgoing_offset) != register:
            raise Core0Error(
                f"{optimization} scalar ABI call does not pass argument "
                f"{8 + outgoing_offset // 8} through stack offset {outgoing_offset}"
            )

    callee_frame = _stack_frame_size(callee_body, callee, required=False)
    callee_load_offsets = {
        _parse_assembly_offset(offset)
        for offset in re.findall(
            r"\bld\s+[a-z][a-z0-9]*,\s*(0x[0-9a-f]+|[0-9]+)\(sp\)", callee_body
        )
    }
    required_callee_offsets = {callee_frame, callee_frame + 8}
    if not required_callee_offsets <= callee_load_offsets:
        raise Core0Error(
            f"{optimization} scalar ABI callee does not consume stack-passed arguments 8/9"
        )
    return {
        "caller": caller,
        "callee": callee,
        "caller_frame_bytes": frame_size,
        "caller_frame_alignment": 16,
        "stack_argument_offsets": [0, 8],
        "callee_stack_load_offsets": sorted(required_callee_offsets),
        "real_call": True,
    }


def validate_cfg_machine_disassembly(disassembly: str) -> dict[str, object]:
    """Require native integer operations for the v0.2 scalar closure."""
    counts = {
        "unsigned_divide": len(re.findall(r"\bdivu(?:w)?\b", disassembly)),
        "unsigned_remainder": len(re.findall(r"\bremu(?:w)?\b", disassembly)),
        "left_shift": len(re.findall(r"\bsll(?:i|w|iw)?\b", disassembly)),
        "logical_right_shift": len(re.findall(r"\bsrl(?:i|w|iw)?\b", disassembly)),
    }
    missing = [name for name, count in counts.items() if count == 0]
    if missing:
        raise Core0Error(
            "structured scalar machine code lacks native operations: " + ", ".join(missing)
        )
    return {"native_integer_instruction_counts": counts}


def _machine_backward_branches(body: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    pattern = re.compile(
        r"^\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s+.*?"
        r"(?:0x)?([0-9a-f]+)\s+<[^>]+>\s*$",
        re.MULTILINE,
    )
    for address, mnemonic, target in pattern.findall(body):
        if not (mnemonic == "j" or mnemonic.startswith("b")):
            continue
        source_value, target_value = int(address, 16), int(target, 16)
        if target_value < source_value:
            records.append(
                {
                    "instruction": mnemonic,
                    "source": f"0x{source_value:x}",
                    "target": f"0x{target_value:x}",
                }
            )
    return records


def validate_loop_machine_disassembly(
    manifest: dict[str, object], disassembly: str, optimization: str
) -> dict[str, object]:
    """Require retained native loops and direct callback calls for positive budgets."""
    functions = manifest.get("functions")
    if not isinstance(functions, list):
        raise Core0Error("bounded suite function manifest is malformed in machine audit")
    source_to_symbol = {
        str(function["source"]): str(function["llvm"])
        for function in functions
        if isinstance(function, dict)
    }
    loop_functions: dict[str, tuple[int, str]] = {}
    pattern = re.compile(
        r"\(bounded-fold-u32 budget=([0-9]+) callback=([A-Za-z_][A-Za-z0-9_.]*) "
    )
    for function_index, function in enumerate(functions):
        if not isinstance(function, dict):
            raise Core0Error(
                f"bounded suite function #{function_index} is malformed in machine audit"
            )
        matches = pattern.findall(str(function["body"]))
        if matches:
            if len(matches) != 1:
                raise Core0Error("bounded machine audit found multiple sites in one function")
            loop_functions[str(function["source"])] = (
                int(matches[0][0], 10), matches[0][1]
            )
    records: list[dict[str, object]] = []
    for source, (budget, callback) in loop_functions.items():
        symbol = source_to_symbol[source]
        callback_symbol = source_to_symbol[callback]
        body = _disassembly_function(disassembly, symbol)
        call_rows = re.findall(
            rf"\b(?:jal|jalr)\b[^\n]*<{re.escape(callback_symbol)}>", body
        )
        backedges = _machine_backward_branches(body)
        if budget > 0:
            if len(call_rows) != 1:
                raise Core0Error(
                    f"{optimization} machine loop {source} lacks exactly one direct "
                    f"callback call to {callback_symbol}"
                )
            if len(backedges) != 1:
                raise Core0Error(
                    f"{optimization} machine loop {source} does not retain exactly one "
                    f"backward branch"
                )
        records.append(
            {
                "source": source,
                "llvm": symbol,
                "budget": budget,
                "callback": callback,
                "callback_llvm": callback_symbol,
                "direct_callback_calls": len(call_rows),
                "backward_branches": backedges,
                "requires_runtime_backedge": budget > 0,
            }
        )
    if len(records) != len(LOOP_ITERATION_SITES):
        raise Core0Error("machine loop inventory differs from the source loop closure")
    dynamic_stack = re.findall(
        r"\b(?:add|sub|and)\s+sp,\s*sp,\s*(?!-?(?:0x[0-9a-f]+|[0-9]+)\b)[^\n]+",
        disassembly,
    )
    if dynamic_stack:
        raise Core0Error(
            f"{optimization} machine code contains dynamic stack adjustment: {dynamic_stack!r}"
        )
    return {
        "optimization": optimization,
        "loop_functions": records,
        "positive_budget_loops_with_backedges": sum(
            bool(record["requires_runtime_backedge"]) and bool(record["backward_branches"])
            for record in records
        ),
        "dynamic_stack_adjustments": [],
    }


def validate_loop_stack_call_graph(
    post_ir: str, stack_sizes: dict[str, int]
) -> dict[str, object]:
    """Prove the emitted direct-call graph acyclic and bound its frame-chain sum."""
    definitions, _declarations, _calls = parse_definitions_and_calls(post_ir)
    if set(stack_sizes) != definitions:
        raise Core0Error("stack-size closure differs from optimized LLVM definitions")
    if re.search(r"\balloca\b", post_ir):
        raise Core0Error("bounded-loop optimized LLVM contains stack allocation")
    graph: dict[str, set[str]] = {}
    for symbol in definitions:
        body = _ir_definition_body(post_ir, symbol)
        _defs, _decls, calls = parse_definitions_and_calls(body)
        graph[symbol] = calls & definitions

    visiting: set[str] = set()
    memo: dict[str, tuple[int, tuple[str, ...]]] = {}

    def longest(symbol: str) -> tuple[int, tuple[str, ...]]:
        existing = memo.get(symbol)
        if existing is not None:
            return existing
        if symbol in visiting:
            raise Core0Error(f"bounded-loop machine direct-call graph contains cycle at {symbol}")
        visiting.add(symbol)
        children = [longest(child) for child in sorted(graph[symbol])]
        visiting.remove(symbol)
        child_size, child_path = max(children, default=(0, ()), key=lambda row: row[0])
        result = (stack_sizes[symbol] + child_size, (symbol, *child_path))
        memo[symbol] = result
        return result

    paths = {symbol: longest(symbol) for symbol in sorted(definitions)}
    maximum, chain = max(paths.values(), key=lambda row: row[0])
    if maximum >= 0x10000:
        raise Core0Error(
            f"bounded-loop maximum direct-call frame chain is not under 64 KiB: {maximum}"
        )
    return {
        "acyclic": True,
        "dynamic_alloca": False,
        "node_count": len(graph),
        "edge_count": sum(len(children) for children in graph.values()),
        "maximum_frame_chain_bytes": maximum,
        "maximum_frame_chain": list(chain),
        "stack_limit_bytes": 0x10000,
        "frame_chains": {
            symbol: {"bytes": size, "chain": list(path)}
            for symbol, (size, path) in sorted(paths.items())
        },
        "edges": {symbol: sorted(children) for symbol, children in sorted(graph.items())},
    }


def validate_manifest_companions(
    manifest: dict[str, object], normalized_text: str, symbols_text: str
) -> None:
    functions = manifest["functions"]
    primitives = manifest["used_primitives"]
    assert isinstance(functions, list) and isinstance(primitives, list)
    normalized_lines = [
        f"contract={manifest['contract_version']}",
        f"root={manifest['root']}",
    ]
    symbol_lines: list[str] = []
    for function in functions:
        assert isinstance(function, dict)
        signature = function["signature"]
        dependencies = function["dependencies"]
        assert isinstance(signature, dict) and isinstance(dependencies, list)
        args = ",".join(signature["args"])
        deps = ",".join(dependencies)
        normalized_lines.append(
            f"function={function['source']};signature=({args})->{signature['result']};"
            f"deps=[{deps}];body={function['body']}"
        )
        symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
    for primitive in primitives:
        assert isinstance(primitive, dict)
        normalized_lines.append(f"primitive={primitive['stable_id']}")
    expected_normalized = "\n".join(normalized_lines) + "\n"
    expected_symbols = "\n".join(symbol_lines) + "\n"
    if normalized_text != expected_normalized:
        raise Core0Error("core0-normalized.txt does not match the parsed target manifest")
    if symbols_text != expected_symbols:
        raise Core0Error("symbols.txt does not match the parsed source-to-LLVM mapping")


def defined_function_symbols(readelf_text: str) -> set[str]:
    result: set[str] = set()
    for line in readelf_text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].endswith(":") and fields[3] == "FUNC" and fields[6] != "UND":
            result.add(fields[7])
    return result


def alloc_section_names(readelf_text: str) -> set[str]:
    result: set[str] = set()
    pattern = re.compile(
        r"^\s*\[\s*\d+\]\s+(\S+)\s+\S+\s+[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+"
        r"[0-9a-fA-F]+\s+\S+\s+([A-Z]*)\s+"
    )
    for line in readelf_text.splitlines():
        match = pattern.match(line)
        if match is not None and "A" in match.group(2):
            result.add(match.group(1))
    return result


def numeric_symbols(nm_text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in nm_text.splitlines():
        fields = line.split()
        if len(fields) == 3 and re.fullmatch(r"[0-9a-fA-F]+", fields[0]):
            result[fields[2]] = int(fields[0], 16)
    return result


def parse_load_segments(text: str) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    pattern = re.compile(
        r"^\s*LOAD\s+0x[0-9a-fA-F]+\s+"
        r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+"
        r"(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.+?)\s+0x[0-9a-fA-F]+\s*$"
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        segments.append(
            {
                "virtual_address": int(match.group(1), 16),
                "physical_address": int(match.group(2), 16),
                "file_size": int(match.group(3), 16),
                "memory_size": int(match.group(4), 16),
                "flags": "".join(match.group(5).split()),
            }
        )
    if not segments:
        raise Core0Error("ELF has no parseable PT_LOAD segments")
    return segments


def relocation_types(text: str) -> set[str]:
    return set(re.findall(r"\bR_RISCV_[A-Z0-9_]+\b", text))


def parse_stack_sizes(text: str) -> dict[str, int]:
    """Parse ``llvm-readelf --stack-sizes`` using its closed two-column form."""
    result: dict[str, int] = {}
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*([0-9]+)\s+([A-Za-z_.$][A-Za-z0-9_.$-]*)\s*", line
        )
        if match is None:
            continue
        symbol = match.group(2)
        if symbol in result:
            raise Core0Error(f"stack-size metadata repeats function {symbol}")
        size = int(match.group(1), 10)
        if size < 0 or size >= 1 << 32:
            raise Core0Error(f"stack-size metadata for {symbol} is out of range")
        result[symbol] = size
    if not result:
        raise Core0Error("program.o has no parseable LLVM stack-size metadata")
    return result


def _device_machine_instructions(disassembly: str) -> list[dict[str, object]]:
    instructions: list[dict[str, object]] = []
    function: str | None = None
    function_pattern = re.compile(
        r"^([0-9a-fA-F]+) <([A-Za-z_.$][A-Za-z0-9_.$-]*)>:$"
    )
    instruction_pattern = re.compile(
        r"^\s*([0-9a-fA-F]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$"
    )
    for line in disassembly.splitlines():
        function_match = function_pattern.fullmatch(line.strip())
        if function_match is not None:
            function = function_match.group(2)
            continue
        instruction_match = instruction_pattern.fullmatch(line)
        if instruction_match is None:
            continue
        if function is None:
            raise Core0Error("device disassembly has an instruction outside a function")
        instructions.append(
            {
                "address": int(instruction_match.group(1), 16),
                "mnemonic": instruction_match.group(2),
                "operands": instruction_match.group(3),
                "function": function,
            }
        )
    if not instructions:
        raise Core0Error("device disassembly has no parseable instructions")
    return instructions


def _device_machine_integer(text: str, context: str) -> int:
    try:
        return int(text, 0)
    except ValueError as error:
        raise Core0Error(f"{context} has a malformed immediate {text!r}") from error


def _device_machine_call_target(
    instructions: list[dict[str, object]], index: int
) -> int | None:
    if index < 0 or index + 1 >= len(instructions):
        return None
    upper, jump = instructions[index], instructions[index + 1]
    if (
        upper["mnemonic"] != "auipc"
        or jump["mnemonic"] != "jalr"
        or upper["function"] != jump["function"]
    ):
        return None
    upper_match = re.fullmatch(
        r"ra,\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))",
        str(upper["operands"]),
    )
    if upper_match is None:
        return None
    jump_text = str(jump["operands"])
    jump_match = re.match(
        r"([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))\(ra\)(?:\s|$)",
        jump_text,
    )
    if jump_match is None:
        return None
    encoded_upper = _device_machine_integer(
        upper_match.group(1), "device AUIPC"
    )
    if encoded_upper < 0 or encoded_upper >= 1 << 20:
        return None
    if encoded_upper & (1 << 19):
        encoded_upper -= 1 << 20
    lower = _device_machine_integer(jump_match.group(1), "device JALR")
    if lower < -(1 << 11) or lower >= 1 << 11:
        return None
    return (int(upper["address"]) + (encoded_upper << 12) + lower) & ~1


def validate_device_machine_disassembly(
    disassembly: str,
    symbol_addresses: dict[str, int],
    *,
    expected_access_sequence: tuple[tuple[str, str, str, int], ...] =
        DEVICE_MACHINE_ACCESS_SEQUENCE,
    expected_denied_metadata: Counter[str] = DEVICE_MACHINE_DENIED_METADATA,
    optimization: str | None = None,
    ignored_functions: frozenset[str] = frozenset(),
    ignored_address_ranges: tuple[tuple[int, int], ...] = (),
) -> dict[str, object]:
    """Close a profile's compiled UART sites at the final RV64 instruction level."""
    if optimization not in {None, "O0", "O2"}:
        raise Core0Error(f"unsupported machine UART optimization profile: {optimization!r}")
    fence_address = symbol_addresses.get("core0_io_fence")
    if fence_address is None:
        raise Core0Error("device ELF lacks the core0_io_fence machine primitive")
    instructions = _device_machine_instructions(disassembly)

    def is_ignored(instruction: dict[str, object]) -> bool:
        address = int(instruction["address"])
        return (
            instruction["function"] in ignored_functions
            or any(start <= address < stop for start, stop in ignored_address_ranges)
        )

    fence_instructions = [
        instruction
        for instruction in instructions
        if instruction["function"] == "core0_io_fence"
    ]
    if [instruction["mnemonic"] for instruction in fence_instructions] != [
        "fence",
        "ret",
    ]:
        raise Core0Error(
            "core0_io_fence machine body is not exactly fence iorw,iorw followed by ret"
        )
    fence_operands = str(fence_instructions[0]["operands"])
    if fence_operands not in {"", "iorw, iorw"}:
        raise Core0Error("core0_io_fence has a noncanonical predecessor/successor mask")

    uart_base_materializations: list[int] = []
    denied_metadata: Counter[str] = Counter()

    def is_denied_region_metadata(index: int) -> bool:
        # O0 retains the general RAM guard's device-table case as scalar
        # metadata.  This exact sequence spills base, length, device class,
        # and denied width/permission bits, then leaves the case block.  It
        # does not dereference the device address.  O2 removes these cases.
        if index < 3 or index + 7 >= len(instructions):
            return False
        chunk = instructions[index - 3:index + 8]
        if len({item["function"] for item in chunk}) != 1:
            return False
        if any(
            int(right["address"]) != int(left["address"]) + 4
            for left, right in zip(chunk, chunk[1:])
        ):
            return False
        for item, register, value in zip(chunk[:3], ("a0", "a1", "a2"), (0, 2, 256)):
            match = re.fullmatch(
                rf"{register},\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))",
                str(item["operands"]),
            )
            if item["mnemonic"] != "li" or match is None or _device_machine_integer(
                match.group(1), "denied UART region metadata"
            ) != value:
                return False
        if str(chunk[3]["operands"]).split(",", 1)[0] != "a3":
            return False
        stack_slot: int | None = None
        for offset, register in ((4, "a3"), (5, "a2"), (6, "a1"), (8, "a1"), (9, "a0")):
            item = chunk[offset]
            match = re.fullmatch(
                rf"{register},\s*(0x[0-9a-fA-F]+|[0-9]+)\(sp\)",
                str(item["operands"]),
            )
            if item["mnemonic"] != "sd" or match is None:
                return False
            slot = _device_machine_integer(match.group(1), "denied UART metadata stack slot")
            if stack_slot is None:
                stack_slot = slot
            expected_offset = {4: 0, 5: 8, 6: 16, 8: 24, 9: 32}[offset]
            if slot != stack_slot + expected_offset:
                return False
        return (
            chunk[7]["mnemonic"] == "mv"
            and re.fullmatch(r"a1,\s*a0", str(chunk[7]["operands"])) is not None
            and chunk[10]["mnemonic"] == "j"
        )

    for index, instruction in enumerate(instructions):
        if is_ignored(instruction):
            continue
        if instruction["mnemonic"] != "lui":
            continue
        match = re.fullmatch(
            r"([a-z][a-z0-9]*),\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))",
            str(instruction["operands"]),
        )
        if match is not None and _device_machine_integer(
            match.group(2), "device LUI"
        ) == 0x10000:
            # Every materialization of the UART base must be accounted for.
            # Filtering candidates by the following opcode would hide an extra
            # wide access or pointer arithmetic from the exact-site audit.
            if is_denied_region_metadata(index):
                denied_metadata[str(instruction["function"])] += 1
            else:
                uart_base_materializations.append(index)

    expected_metadata = Counter(expected_denied_metadata) if optimization != "O2" else Counter()
    if (
        (optimization is not None and denied_metadata != expected_metadata)
        or (
            optimization is None
            and denied_metadata
            and denied_metadata != Counter(expected_denied_metadata)
        )
    ):
        raise Core0Error(
            "machine UART denied-region metadata differs from the exact optimization closure: "
            f"{dict(denied_metadata)!r} != {dict(expected_metadata)!r}"
        )

    records: list[dict[str, object]] = []
    approved_access_indices: set[int] = set()
    memory_operand = re.compile(
        r"([a-z][a-z0-9]*),\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))"
        r"\(([a-z][a-z0-9]*)\)"
    )
    for base_index in uart_base_materializations:
        base_instruction = instructions[base_index]
        base_match = re.fullmatch(
            r"([a-z][a-z0-9]*),\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))",
            str(base_instruction["operands"]),
        )
        assert base_match is not None
        base_register = base_match.group(1)
        access_index = base_index + 1
        fixed_write = False
        if (
            access_index < len(instructions)
            and instructions[access_index]["mnemonic"] == "li"
        ):
            fixed_write = True
            access_index += 1
        if access_index >= len(instructions):
            raise Core0Error("UART base materialization lacks its byte access")
        access = instructions[access_index]
        if (
            access["function"] != base_instruction["function"]
            or access["mnemonic"] not in {"lbu", "sb"}
        ):
            raise Core0Error(
                "UART base materialization is not consumed by an exact lbu/sb access"
            )
        access_match = memory_operand.fullmatch(str(access["operands"]))
        if access_match is None or access_match.group(3) != base_register:
            raise Core0Error("UART byte access does not use its fixed base register")
        value_register = access_match.group(1)
        offset = _device_machine_integer(
            access_match.group(2), "device byte access"
        )
        address = 0x10000000 + offset
        mnemonic = str(access["mnemonic"])
        if mnemonic == "lbu" and offset == 5 and not fixed_write:
            operation = "uart.lsr.read8"
        elif mnemonic == "lbu" and offset == 0 and not fixed_write:
            operation = "uart.rbr.read8"
        elif mnemonic == "sb" and offset == 0 and not fixed_write:
            operation = "uart.thr.write8"
        elif mnemonic == "sb" and offset == 2 and fixed_write:
            value_instruction = instructions[base_index + 1]
            value_match = re.fullmatch(
                r"([a-z][a-z0-9]*),\s*([+-]?(?:0x[0-9a-fA-F]+|[0-9]+))",
                str(value_instruction["operands"]),
            )
            if (
                value_match is None
                or value_match.group(1) != value_register
                or _device_machine_integer(value_match.group(2), "device FCR write") != 7
            ):
                raise Core0Error("UART FCR machine write does not use fixed value 0x07")
            operation = "uart.fcr.enable-reset"
        else:
            raise Core0Error(
                f"machine code contains an unknown UART byte access {mnemonic} +{offset}"
            )

        before_index = base_index - 2
        if (
            mnemonic == "sb"
            and offset == 0
            and _device_machine_call_target(instructions, before_index) != fence_address
            and base_index > 0
            and instructions[base_index - 1]["mnemonic"] == "ld"
            and re.fullmatch(
                rf"{re.escape(value_register)},\s*"
                r"(?:0x[0-9a-fA-F]+|[0-9]+)\(sp\)",
                str(instructions[base_index - 1]["operands"]),
            )
            is not None
        ):
            # O0 reloads the already-checked transmit byte from its fixed stack
            # slot after the before-fence and immediately before materializing
            # the UART base.
            before_index -= 1
        after_index = access_index + 1
        if (
            mnemonic == "lbu"
            and after_index < len(instructions)
            and instructions[after_index]["mnemonic"] == "sd"
            and re.fullmatch(
                rf"{re.escape(value_register)},\s*"
                r"(?:0x[0-9a-fA-F]+|[0-9]+)\(sp\)",
                str(instructions[after_index]["operands"]),
            )
            is not None
        ):
            # At O0 the direct checked-result lowering spills the freshly read
            # byte to its fixed stack slot before making the after-fence call.
            # No computation or second memory-mapped access is permitted here.
            after_index += 1
        if (
            _device_machine_call_target(instructions, before_index) != fence_address
            or _device_machine_call_target(instructions, after_index) != fence_address
        ):
            raise Core0Error(
                f"machine UART access {operation} is not bracketed by exact "
                "core0_io_fence calls"
            )
        records.append(
            {
                "operation": operation,
                "function": str(access["function"]),
                "instruction": mnemonic,
                "address": f"0x{address:08x}",
                "fence_before": True,
                "fence_after": True,
            }
        )
        approved_access_indices.add(access_index)

    # This is intentionally a bounded straight-line inference pass over the
    # pinned emitted instruction forms, not a general RV64 dataflow proof.
    # Track constant registers and UART-derived aliases within each function;
    # require every inferred UART dereference to be one of the approved sites.
    # The exact audited fence body has no register clobbers.  Other calls may
    # clobber caller-saved registers.  Unknown transformations of a known UART
    # value reject instead of silently discarding its provenance.
    known: dict[str, tuple[int, bool]] = {}
    current_function: str | None = None
    inferred_accesses: set[int] = set()
    caller_saved = {"ra", *(f"a{i}" for i in range(8)), *(f"t{i}" for i in range(7))}
    memory_mnemonics = {
        "lb", "lbu", "lh", "lhu", "lw", "lwu", "ld",
        "sb", "sh", "sw", "sd",
    }
    nonwriting_mnemonics = {
        "beq", "bne", "blt", "bge", "bltu", "bgeu",
        "beqz", "bnez", "blez", "bgez", "bltz", "bgtz",
        "j", "jr", "ret", "fence", "nop", "unimp", "ebreak", "ecall",
    }
    mask64 = (1 << 64) - 1

    def record_constant(register: str, value: int, uart_derived: bool = False) -> None:
        if register == "zero":
            return
        value &= mask64
        known[register] = (
            value,
            uart_derived or 0x10000000 <= value < 0x10000100,
        )

    def register_value(register: str) -> tuple[int, bool] | None:
        return (0, False) if register == "zero" else known.get(register)

    for index, instruction in enumerate(instructions):
        if instruction["function"] != current_function:
            current_function = str(instruction["function"])
            known.clear()
        if is_ignored(instruction):
            continue
        mnemonic = str(instruction["mnemonic"])
        operands = str(instruction["operands"])
        parts = [part.strip() for part in operands.split(",")]
        if mnemonic in memory_mnemonics:
            match = memory_operand.fullmatch(operands)
            if match is None:
                raise Core0Error("machine memory instruction has an unsupported operand shape")
            value_register, offset_text, base_register = match.groups()
            base = register_value(base_register)
            if base is not None:
                offset = _device_machine_integer(offset_text, "device inferred memory offset")
                address = (base[0] + offset) & mask64
                if base[1] or 0x10000000 <= address < 0x10000100:
                    if index not in approved_access_indices:
                        raise Core0Error(
                            "machine code contains an additional, wide, or aliased UART access "
                            f"at 0x{int(instruction['address']):x}"
                        )
                    inferred_accesses.add(index)
            if mnemonic.startswith("l"):
                known.pop(value_register, None)
            continue
        if mnemonic in {"jalr", "jal", "call", "tail"}:
            target = _device_machine_call_target(instructions, index - 1)
            if target != fence_address:
                for register in caller_saved:
                    known.pop(register, None)
            continue
        if mnemonic in nonwriting_mnemonics:
            continue
        if mnemonic in {"lui", "li"} and len(parts) == 2:
            immediate = _device_machine_integer(parts[1], "device inferred immediate")
            if mnemonic == "lui":
                immediate = (immediate & ((1 << 20) - 1)) << 12
                if immediate & (1 << 31):
                    immediate -= 1 << 32
            record_constant(parts[0], immediate)
            continue
        if mnemonic == "mv" and len(parts) == 2:
            source = register_value(parts[1])
            if source is None:
                known.pop(parts[0], None)
            else:
                record_constant(parts[0], *source)
            continue
        if mnemonic == "addi" and len(parts) == 3:
            source = register_value(parts[1])
            if source is None:
                known.pop(parts[0], None)
            else:
                immediate = _device_machine_integer(parts[2], "device inferred ADDI")
                record_constant(parts[0], source[0] + immediate, source[1])
            continue
        if mnemonic in {"add", "sub"} and len(parts) == 3:
            left, right = register_value(parts[1]), register_value(parts[2])
            if left is not None and right is not None:
                result = left[0] + right[0] if mnemonic == "add" else left[0] - right[0]
                record_constant(parts[0], result, left[1] or right[1])
                continue
        if any(known.get(part, (0, False))[1] for part in parts[1:]):
            raise Core0Error(
                f"machine UART pointer has unsupported transformation `{mnemonic}`"
            )
        if parts:
            known.pop(parts[0], None)

    if inferred_accesses != approved_access_indices:
        raise Core0Error("machine UART register-use inference does not cover every approved site")

    observed = tuple(
        (
            str(record["operation"]),
            str(record["function"]),
            str(record["instruction"]),
            int(str(record["address"]), 16),
        )
        for record in records
    )
    if observed != expected_access_sequence:
        raise Core0Error(
            "machine UART access sequence differs from the exact profile closure: "
            f"{observed!r} != {expected_access_sequence!r}"
        )
    return {
        "access_count": len(records),
        "byte_accesses_only": True,
        "ordered_fence_calls": 2 * len(records),
        "denied_region_metadata_materializations": sum(denied_metadata.values()),
        "register_use_audit": {
            "inferred_uart_accesses": len(inferred_accesses),
            "all_inferred_accesses_are_approved": True,
            "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof",
        },
        "fence_implementation": "fence iorw,iorw; ret",
        "accesses": records,
    }


def hex_field(mapping: object, section: str, field: str) -> int:
    if not isinstance(mapping, dict) or not isinstance(mapping.get(section), dict):
        raise Core0Error(f"layout.json lacks a {section!r} region")
    value = mapping[section].get(field)
    if not isinstance(value, str):
        raise Core0Error(f"layout.json {section}.{field} is not a hexadecimal string")
    try:
        return int(value, 0)
    except ValueError as error:
        raise Core0Error(f"layout.json {section}.{field} is malformed: {value!r}") from error


def audit(
    directory: Path,
    root: Path,
    *,
    policy: str = RELEASE_POLICY,
    expected_fault: str | None = None,
    expected_target_source: str | None = None,
    clean_control_directory: Path | None = None,
) -> dict[str, object]:
    """Audit one complete image under an explicit release or test policy.

    The default remains the public release audit.  Test compiler controls and
    mutants, and the typed frontend suite, must opt in by keyword so test-only
    artifacts cannot become release artifacts through directory contents alone.
    """
    policy = _validate_audit_policy(policy)
    expected_mutation = expected_fault is not None or expected_target_source is not None
    if policy != TEST_COMPILER_MUTANT_POLICY and expected_mutation:
        raise Core0Error("only the test-compiler-mutant audit accepts expected fault selectors")
    if expected_fault is not None and (
        not isinstance(expected_fault, str) or expected_fault not in COMPILER_MUTATION_FAULTS
    ):
        raise Core0Error(
            f"expected compiler fault is outside the closed allowlist: {expected_fault!r}"
        )
    if (
        expected_target_source is not None
        and (
            not isinstance(expected_target_source, str)
            or LEAN_IDENTIFIER.fullmatch(expected_target_source) is None
        )
    ):
        raise Core0Error(
            f"expected compiler-fault target is not a Lean identity: {expected_target_source!r}"
        )
    if policy == TEST_COMPILER_MUTANT_POLICY:
        if clean_control_directory is None:
            raise Core0Error("test-compiler-mutant audit requires a clean-control directory")
        clean_control_directory = clean_control_directory.resolve()
        if clean_control_directory == directory.resolve():
            raise Core0Error("compiler mutant and clean control must be different directories")
    elif clean_control_directory is not None:
        raise Core0Error("only the test-compiler-mutant audit accepts a clean-control directory")
    require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump"))
    if not directory.is_dir():
        raise Core0Error(f"artifact directory is missing: {directory}")
    mutation_path = directory / COMPILER_MUTATION_ARTIFACT
    if policy == TEST_COMPILER_MUTANT_POLICY:
        required_artifacts = (*REQUIRED_ARTIFACTS, COMPILER_MUTATION_ARTIFACT)
    elif policy == TEST_MONITOR_IMAGE_POLICY:
        required_artifacts = MONITOR_IMAGE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy == TEST_TIMER_SUITE_POLICY:
        required_artifacts = TIMER_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy == TEST_TRAP_SUITE_POLICY:
        required_artifacts = TRAP_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy == TEST_DEVICE_SUITE_POLICY:
        required_artifacts = DEVICE_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy == TEST_MEMORY_SUITE_POLICY:
        required_artifacts = MEMORY_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy == TEST_LOOP_SUITE_POLICY:
        required_artifacts = BOUNDED_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    elif policy in SCALAR_SUITE_POLICIES:
        required_artifacts = SCALAR_SUITE_REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    else:
        required_artifacts = REQUIRED_ARTIFACTS
        if mutation_path.exists():
            raise Core0Error(
                f"{policy} audit rejects the test-only {COMPILER_MUTATION_ARTIFACT}"
            )
    paths = {name: directory / name for name in required_artifacts}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise Core0Error("missing audit artifacts: " + ", ".join(missing))
    empty = [name for name, path in paths.items() if path.stat().st_size == 0]
    if empty:
        raise Core0Error("empty audit artifacts: " + ", ".join(empty))

    clean_control_report: dict[str, object] | None = None
    if clean_control_directory is not None:
        clean_control_report = audit(
            clean_control_directory,
            root,
            policy=TEST_COMPILER_CONTROL_POLICY,
        )

    scalar_test_abi: dict[str, object] | None = None
    memory_ir_audit: dict[str, object] | None = None
    trap_test_abi: dict[str, object] | None = None
    trap_ir_audit: dict[str, object] | None = None
    timer_test_abi: dict[str, object] | None = None
    timer_ir_audit: dict[str, object] | None = None
    monitor_abi: dict[str, object] | None = None
    monitor_ir_audit: dict[str, object] | None = None
    if policy == TEST_MONITOR_IMAGE_POLICY:
        manifest = audit_monitor.validate_monitor_manifest(
            load_json(paths["monitor-manifest.json"])
        )
        monitor_abi = audit_monitor.validate_monitor_abi(
            load_json(paths["monitor-abi.json"]), manifest
        )
        device_contract = load_json(paths["device-contract.json"])
        if device_contract != manifest["device_contract"]:
            raise Core0Error(
                "device-contract.json does not match the checked monitor manifest"
            )
        audit_monitor.validate_monitor_companions(
            manifest,
            paths["monitor-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy == TEST_TIMER_SUITE_POLICY:
        manifest = audit_timer.validate_timer_suite_manifest(
            load_json(paths["timer-suite-manifest.json"])
        )
        timer_test_abi = audit_timer.validate_timer_test_abi(
            load_json(paths["timer-test-abi.json"]), manifest
        )
        device_contract = load_json(paths["device-contract.json"])
        if device_contract != manifest["device_contract"]:
            raise Core0Error(
                "device-contract.json does not match the checked timer manifest"
            )
        audit_timer.validate_timer_manifest_companions(
            manifest,
            paths["timer-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy == TEST_TRAP_SUITE_POLICY:
        manifest = audit_trap.validate_trap_suite_manifest(
            load_json(paths["trap-suite-manifest.json"])
        )
        trap_test_abi = audit_trap.validate_trap_test_abi(
            load_json(paths["trap-test-abi.json"]), manifest
        )
        device_contract = load_json(paths["device-contract.json"])
        if device_contract != manifest["device_contract"]:
            raise Core0Error(
                "device-contract.json does not match the checked trap manifest"
            )
        audit_trap.validate_trap_manifest_companions(
            manifest,
            paths["trap-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy == TEST_DEVICE_SUITE_POLICY:
        manifest = validate_device_suite_manifest(
            load_json(paths["device-suite-manifest.json"])
        )
        validate_device_test_abi(
            load_json(paths["device-test-abi.json"]), manifest
        )
        device_contract = load_json(paths["device-contract.json"])
        if device_contract != manifest["device_contract"]:
            raise Core0Error(
                "device-contract.json does not match the checked device manifest"
            )
        validate_device_manifest_companions(
            manifest,
            paths["device-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy == TEST_MEMORY_SUITE_POLICY:
        manifest = audit_memory.validate_memory_suite_manifest(
            load_json(paths["memory-suite-manifest.json"])
        )
        validate_memory_test_abi(
            load_json(paths["memory-test-abi.json"]), manifest
        )
        validate_memory_manifest_companions(
            manifest,
            paths["memory-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy == TEST_LOOP_SUITE_POLICY:
        manifest = validate_loop_suite_manifest(
            load_json(paths["bounded-suite-manifest.json"])
        )
        scalar_test_abi = validate_scalar_test_abi(
            load_json(paths["scalar-test-abi.json"]), manifest
        )
        validate_bounded_manifest_companions(
            manifest,
            paths["bounded-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    elif policy in SCALAR_SUITE_POLICIES:
        raw_scalar_manifest = load_json(paths["scalar-suite-manifest.json"])
        manifest = (
            validate_scalar_suite_manifest(raw_scalar_manifest)
            if policy == TEST_FRONTEND_SUITE_POLICY
            else validate_cfg_suite_manifest(raw_scalar_manifest)
        )
        scalar_test_abi = validate_scalar_test_abi(
            load_json(paths["scalar-test-abi.json"]), manifest
        )
        validate_scalar_manifest_companions(
            manifest,
            paths["scalar-suite-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    else:
        manifest = validate_core0_manifest(load_json(paths["core0-manifest.json"]))
        validate_manifest_companions(
            manifest,
            paths["core0-normalized.txt"].read_text(encoding="utf-8"),
            paths["symbols.txt"].read_text(encoding="utf-8"),
        )
    mutation_manifest: dict[str, object] | None = None
    if policy == TEST_COMPILER_MUTANT_POLICY:
        mutation_manifest = validate_compiler_mutation_manifest(
            load_json(paths[COMPILER_MUTATION_ARTIFACT]), manifest
        )
        if expected_fault is not None and mutation_manifest.get("fault") != expected_fault:
            raise Core0Error(
                "compiler mutation fault differs from the requested test build: "
                f"{mutation_manifest.get('fault')!r} != {expected_fault!r}"
            )
        if (
            expected_target_source is not None
            and mutation_manifest.get("target_source") != expected_target_source
        ):
            raise Core0Error(
                "compiler mutation target differs from the requested test build: "
                f"{mutation_manifest.get('target_source')!r} != {expected_target_source!r}"
            )

    provenance_obj = load_json(paths["provenance.json"])
    if not isinstance(provenance_obj, dict):
        raise Core0Error("provenance.json is not an object")
    provenance_schema = provenance_obj.get("schema_version")
    if (
        isinstance(provenance_schema, bool)
        or not isinstance(provenance_schema, int)
        or provenance_schema not in {1, 2}
    ):
        raise Core0Error("provenance.json has an unsupported schema")
    has_provenance_category = "artifact_category" in provenance_obj
    provenance_category = provenance_obj.get("artifact_category")
    has_compiler_fault = "compiler_fault" in provenance_obj
    if provenance_schema == 1:
        if policy != RELEASE_POLICY:
            raise Core0Error(
                "historical provenance schema 1 is accepted only by the release audit"
            )
        if has_provenance_category:
            raise Core0Error(
                "historical provenance schema 1 must use its implicit release category"
            )
    elif provenance_category != policy:
        raise Core0Error(
            "provenance artifact category differs from the selected audit policy: "
            f"{provenance_category!r} != {policy!r}"
        )
    if policy != TEST_COMPILER_MUTANT_POLICY:
        if has_compiler_fault:
            raise Core0Error(f"{policy} provenance rejects compiler-fault metadata")
    else:
        compiler_fault = provenance_obj.get("compiler_fault")
        if not isinstance(compiler_fault, dict):
            raise Core0Error("mutant provenance lacks compiler-fault metadata")
        _exact_keys(
            compiler_fault,
            {"manifest_path", "manifest_sha256", "program_ll_sha256"},
            "compiler-fault provenance",
        )
        if compiler_fault.get("manifest_path") != COMPILER_MUTATION_ARTIFACT:
            raise Core0Error("compiler-fault provenance names the wrong manifest path")
        for field, artifact_name in (
            ("manifest_sha256", COMPILER_MUTATION_ARTIFACT),
            ("program_ll_sha256", "program.ll"),
        ):
            digest = compiler_fault.get(field)
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise Core0Error(f"compiler-fault provenance {field} is not a SHA-256")
            actual_digest = sha256(paths[artifact_name])
            if digest != actual_digest:
                raise Core0Error(
                    f"compiler-fault provenance hash mismatch for {artifact_name}: "
                    f"{digest} != {actual_digest}"
                )
    source_commit = provenance_obj.get("source_commit")
    if not isinstance(source_commit, str) or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise Core0Error("provenance lacks a full Git source commit")
    scalar_export_configuration: dict[str, object] | None = None
    memory_export_configuration: dict[str, object] | None = None
    device_export_configuration: dict[str, object] | None = None
    trap_export_configuration: dict[str, object] | None = None
    timer_export_configuration: dict[str, object] | None = None
    if policy in SCALAR_SUITE_POLICIES:
        scalar_export_configuration = validate_scalar_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif policy == TEST_MEMORY_SUITE_POLICY:
        memory_export_configuration = validate_memory_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif policy == TEST_DEVICE_SUITE_POLICY:
        device_export_configuration = validate_device_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif policy == TEST_TRAP_SUITE_POLICY:
        trap_export_configuration = audit_trap.validate_trap_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif policy == TEST_TIMER_SUITE_POLICY:
        timer_export_configuration = audit_timer.validate_timer_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif "export_configuration" in provenance_obj:
        raise Core0Error(
            f"{policy} provenance rejects exporter configuration"
        )
    if policy in {
        TEST_TRAP_SUITE_POLICY,
        TEST_TIMER_SUITE_POLICY,
        TEST_MONITOR_IMAGE_POLICY,
    }:
        qemu_dtb_command = [
            "qemu-system-riscv64",
            "-machine", "virt,acpi=off,dumpdtb=platform.dtb",
            "-accel", "tcg",
            "-cpu", "rv64",
            "-smp", "1",
            "-m", "128M",
            "-bios", "none",
            "-nodefaults",
            "-nic", "none",
            "-display", "none",
            "-serial", "none",
            "-monitor", "none",
            "-no-reboot",
            "-seed", "1",
        ]
        expected_emulator_artifacts = [
            {
                "path": "platform.dtb",
                "sha256": sha256(paths["platform.dtb"]),
                "source": "pinned QEMU virt machine dumpdtb",
                "generation_command": qemu_dtb_command,
            },
            {
                "path": "platform.dts",
                "sha256": sha256(paths["platform.dts"]),
                "source": "dtc decompilation of platform.dtb",
                "generation_command": [
                    "dtc", "-I", "dtb", "-O", "dts", "-o",
                    "platform.dts", "platform.dtb",
                ],
            },
        ]
        if provenance_obj.get("emulator_artifacts") != expected_emulator_artifacts:
            raise Core0Error(f"{policy} provenance emulator artifact/hash/command closure differs")
        audit_device.validate_platform_evidence(
            sha256(paths["platform.dtb"]),
            paths["platform.dts"].read_text(encoding="utf-8"),
        )
        audit_device.validate_toolchain_lock(
            load_json(root / "tooling/toolchain-lock.json")
        )
        tools = provenance_obj.get("tools")
        qemu_tool = tools.get("qemu-system-riscv64") if isinstance(tools, dict) else None
        if (
            not isinstance(qemu_tool, dict)
            or not isinstance(qemu_tool.get("version"), str)
            or "QEMU emulator version 11.1.1" not in qemu_tool["version"]
        ):
            raise Core0Error(f"{policy} provenance does not identify pinned QEMU 11.1.1")
    optimization = provenance_obj.get("optimization")
    if optimization not in {"O0", "O2"}:
        raise Core0Error("provenance optimization profile is missing or unsupported")
    dirty_tree, dirty_paths = provenance_obj.get("dirty_tree"), provenance_obj.get("dirty_paths")
    if (
        not isinstance(dirty_tree, bool)
        or not isinstance(dirty_paths, list)
        or any(not isinstance(path, str) or not path for path in dirty_paths)
        or dirty_tree != bool(dirty_paths)
    ):
        raise Core0Error("provenance dirty-tree identity is malformed or inconsistent")
    source_inputs = provenance_obj.get("source_inputs")
    if not isinstance(source_inputs, list) or not source_inputs:
        raise Core0Error("provenance source-input manifest is empty or malformed")
    observed_sources: set[str] = set()
    for item in source_inputs:
        if not isinstance(item, dict):
            raise Core0Error("malformed source-input provenance entry")
        source_path, source_digest = item.get("path"), item.get("sha256")
        if (
            not isinstance(source_path, str)
            or not source_path
            or Path(source_path).is_absolute()
            or not isinstance(source_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None
        ):
            raise Core0Error(f"malformed source-input provenance entry: {item!r}")
        resolved_source = (root / source_path).resolve()
        try:
            resolved_source.relative_to(root.resolve())
        except ValueError as error:
            raise Core0Error(f"source-input path escapes the repository: {source_path}") from error
        if source_path in observed_sources:
            raise Core0Error(f"duplicate source-input provenance entry: {source_path}")
        if not resolved_source.is_file():
            raise Core0Error(f"source-input file is missing: {source_path}")
        actual_source_digest = sha256(resolved_source)
        if actual_source_digest != source_digest:
            raise Core0Error(
                f"source-input hash mismatch for {source_path}: "
                f"{source_digest} != {actual_source_digest}"
            )
        observed_sources.add(source_path)
    if policy == TEST_TRAP_SUITE_POLICY:
        required_trap_sources = {
            "examples/foundation/TrapBuild.lean",
            "examples/foundation/TrapConformance.lean",
            "Lemma/Compiler/Test/TrapExport.lean",
            "Lemma/Machine/TrapPrimitives.lean",
            "Lemma/Machine/TrapLayout.lean",
            "scripts/build_trap_suite.py",
            "scripts/audit_core0.py",
            "scripts/audit_trap.py",
            "scripts/check_foundation.py",
            "scripts/gate7_corpus.py",
            "scripts/run_trap_case.py",
            "scripts/check_foundation_gate7.py",
            "examples/foundation/TrapFrontendProbes.lean",
            "examples/foundation/TrapPolicyProbes.lean",
            "examples/foundation/gate7-reject/HiddenExternTrap.lean",
            "examples/foundation/gate7-reject/PureTrapResult.lean",
            "examples/foundation/gate7-reject/StoredTrapContinuation.lean",
            "examples/foundation/gate7-reject/V05Trap.lean",
            "examples/foundation/gate7-reject/rejections.json",
        }
        missing_trap_sources = required_trap_sources - observed_sources
        if missing_trap_sources:
            raise Core0Error(
                "trap provenance omits required source/checker inputs: "
                + repr(sorted(missing_trap_sources))
            )
    elif policy == TEST_TIMER_SUITE_POLICY:
        required_timer_sources = {
            "examples/foundation/TimerBuild.lean",
            "examples/foundation/TimerConformance.lean",
            "examples/foundation/DeviceConformanceSupport.lean",
            "examples/foundation/TrapConformance.lean",
            "examples/foundation/TimerFrontendProbes.lean",
            "examples/foundation/TimerPolicyProbes.lean",
            "examples/foundation/gate8-reject/HiddenExternTimer.lean",
            "examples/foundation/gate8-reject/PureTimerResult.lean",
            "examples/foundation/gate8-reject/StoredTimerContinuation.lean",
            "examples/foundation/gate8-reject/V06Timer.lean",
            "examples/foundation/gate8-reject/rejections.json",
            "Lemma/Compiler/Test/TimerExport.lean",
            "Lemma/Core0/Timer.lean",
            "Lemma/Core0/TimerModel.lean",
            "Lemma/Machine/TimerPrimitives.lean",
            "Lemma/Machine/TrapPrimitives.lean",
            "Lemma/Machine/TrapLayout.lean",
            "scripts/build_core0.py",
            "scripts/core0_common.py",
            "scripts/build_timer_suite.py",
            "scripts/audit_core0.py",
            "scripts/audit_device.py",
            "scripts/audit_memory.py",
            "scripts/audit_timer.py",
            "scripts/audit_trap.py",
            "scripts/check_foundation.py",
            "scripts/gate8_corpus.py",
            "scripts/run_timer_case.py",
            "scripts/run_trap_case.py",
            "scripts/check_foundation_gate8.py",
            "docs/audits/timers-core0-v07.html",
        }
        # Historical consumed-source archives keep their original document
        # paths and bytes; current builds consume the mapped HTML edition.
        if not (root / "docs/document-map.json").is_file():
            required_timer_sources = {name[:-5] + ".md" if name.startswith("docs/") and name.endswith(".html") else name
                                        for name in required_timer_sources}
        missing_timer_sources = required_timer_sources - observed_sources
        if missing_timer_sources:
            raise Core0Error(
                "timer provenance omits required source/checker inputs: "
                + repr(sorted(missing_timer_sources))
            )
    elif policy == TEST_MONITOR_IMAGE_POLICY:
        required_monitor_sources = {
            "examples/foundation/MonitorBuild.lean",
            "examples/foundation/MonitorProtocol.lean",
            "examples/foundation/Monitor.lean",
            "examples/foundation/MonitorPolicyProbes.lean",
            "examples/foundation/DeviceConformanceSupport.lean",
            "examples/foundation/TrapConformance.lean",
            "examples/foundation/TimerConformance.lean",
            "examples/foundation/TimerFrontendProbes.lean",
            "examples/foundation/TimerPolicyProbes.lean",
            "examples/foundation/gate8-reject/HiddenExternTimer.lean",
            "examples/foundation/gate8-reject/PureTimerResult.lean",
            "examples/foundation/gate8-reject/StoredTimerContinuation.lean",
            "examples/foundation/gate8-reject/V06Timer.lean",
            "examples/foundation/gate8-reject/rejections.json",
            "Lemma/Compiler/Test/MonitorExport.lean",
            "Lemma/Compiler/Test/TimerExport.lean",
            "Lemma/Core0/Timer.lean",
            "Lemma/Core0/TimerModel.lean",
            "Lemma/Machine/TimerPrimitives.lean",
            "Lemma/Machine/TrapPrimitives.lean",
            "Lemma/Machine/TrapLayout.lean",
            "scripts/build_core0.py",
            "scripts/core0_common.py",
            "scripts/build_monitor.py",
            "scripts/audit_core0.py",
            "scripts/audit_device.py",
            "scripts/audit_memory.py",
            "scripts/audit_monitor.py",
            "scripts/audit_timer.py",
            "scripts/audit_trap.py",
            "scripts/check_foundation.py",
            "scripts/gate6_corpus.py",
            "scripts/run_device_session.py",
            "scripts/gate8_corpus.py",
            "scripts/run_timer_case.py",
            "scripts/run_trap_case.py",
            "scripts/check_foundation_gate8.py",
            "scripts/gate9_corpus.py",
            "scripts/run_monitor_session.py",
            "scripts/check_foundation_gate9.py",
            "scripts/qualify_foundation.py",
            "docs/audits/timers-core0-v07.html",
            "docs/audits/monitor-core0-v07.html",
        }
        # Historical consumed-source archives keep their original document
        # paths and bytes; current builds consume the mapped HTML edition.
        if not (root / "docs/document-map.json").is_file():
            required_monitor_sources = {name[:-5] + ".md" if name.startswith("docs/") and name.endswith(".html") else name
                                        for name in required_monitor_sources}
        missing_monitor_sources = required_monitor_sources - observed_sources
        if missing_monitor_sources:
            raise Core0Error(
                "monitor provenance omits required source/checker inputs: "
                + repr(sorted(missing_monitor_sources))
            )
    expected_elaboration_commands: list[list[str]] = []
    if provenance_schema == 2:
        elaborated_inputs = provenance_obj.get("elaborated_inputs")
        if not isinstance(elaborated_inputs, list) or not elaborated_inputs:
            raise Core0Error("schema-2 provenance lacks elaborated Lean input identities")
        seen_elaboration_sources: set[str] = set()
        seen_oleans: set[str] = set()
        for index, item in enumerate(elaborated_inputs):
            if not isinstance(item, dict):
                raise Core0Error(f"elaborated Lean input #{index} is not an object")
            _exact_keys(
                item,
                {
                    "source",
                    "source_sha256",
                    "olean",
                    "olean_sha256",
                    "generation_command",
                },
                f"elaborated Lean input #{index}",
            )
            source_name, olean_name = item.get("source"), item.get("olean")
            source_digest, olean_digest = item.get("source_sha256"), item.get("olean_sha256")
            generation_command = item.get("generation_command")
            if (
                not isinstance(source_name, str)
                or Path(source_name).is_absolute()
                or not source_name.endswith(".lean")
                or not isinstance(olean_name, str)
                or Path(olean_name).is_absolute()
                or not olean_name.startswith(".lake/build/lib/lean/")
                or not olean_name.endswith(".olean")
                or not isinstance(source_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None
                or not isinstance(olean_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", olean_digest) is None
            ):
                raise Core0Error(f"elaborated Lean input #{index} has malformed identities")
            if source_name in seen_elaboration_sources or olean_name in seen_oleans:
                raise Core0Error("duplicate elaborated Lean source or olean identity")
            expected_command = ["lake", "env", "lean", "-o", olean_name, source_name]
            if generation_command != expected_command:
                raise Core0Error(
                    f"elaborated Lean input {source_name} has an unexpected generation command"
                )
            if source_name not in observed_sources or olean_name not in observed_sources:
                raise Core0Error(
                    f"elaborated Lean input {source_name} is absent from source-input hashes"
                )
            for name, digest in ((source_name, source_digest), (olean_name, olean_digest)):
                actual = sha256(root / name)
                if digest != actual:
                    raise Core0Error(
                        f"elaborated Lean input hash mismatch for {name}: {digest} != {actual}"
                    )
            seen_elaboration_sources.add(source_name)
            seen_oleans.add(olean_name)
            expected_elaboration_commands.append(expected_command)
        if policy == TEST_TRAP_SUITE_POLICY and [
            item.get("source") for item in elaborated_inputs
        ] != [
            "examples/core0/Positive.lean",
            "Lemma/Platform/LemmaVM/ConsoleDevice.lean",
            "examples/foundation/DeviceConformanceSupport.lean",
            "examples/foundation/TrapConformance.lean",
        ]:
            raise Core0Error(
                "trap provenance elaboration sequence differs from the exact checked inputs"
            )
        if policy == TEST_TIMER_SUITE_POLICY and [
            item.get("source") for item in elaborated_inputs
        ] != [
            "examples/core0/Positive.lean",
            "Lemma/Platform/LemmaVM/ConsoleDevice.lean",
            "examples/foundation/DeviceConformanceSupport.lean",
            "examples/foundation/TrapConformance.lean",
            "examples/foundation/TimerConformance.lean",
        ]:
            raise Core0Error(
                "timer provenance elaboration sequence differs from the exact checked inputs"
            )
        if policy == TEST_MONITOR_IMAGE_POLICY and [
            item.get("source") for item in elaborated_inputs
        ] != [
            "examples/core0/Positive.lean",
            "Lemma/Platform/LemmaVM/ConsoleDevice.lean",
            "examples/foundation/DeviceConformanceSupport.lean",
            "examples/foundation/TrapConformance.lean",
            "examples/foundation/TimerConformance.lean",
            "examples/foundation/MonitorProtocol.lean",
            "examples/foundation/Monitor.lean",
        ]:
            raise Core0Error(
                "monitor provenance elaboration sequence differs from the exact checked inputs"
            )
    linked = provenance_obj.get("linked_inputs")
    if not isinstance(linked, list) or len(linked) != 2:
        raise Core0Error("provenance must name exactly the two linked objects")
    if not isinstance(optimization, str):
        raise Core0Error("provenance optimization identity is malformed")
    program_input_details = {
        RELEASE_POLICY: {
            "kind": "core0-llvm",
            "source": "program.ll generated from the checked elaborated Core0 program",
            "purpose": "compiled Core0 application and freestanding machine harness",
        },
        TEST_COMPILER_CONTROL_POLICY: {
            "kind": "test-compiler-control-llvm",
            "source": "program.ll generated by the unmodified checked Core0 lowering",
            "purpose": "test-only clean compiler control and freestanding machine harness",
        },
        TEST_COMPILER_MUTANT_POLICY: {
            "kind": "test-compiler-mutant-llvm",
            "source": (
                "program.ll generated by the quarantined Lean compiler-fault transform "
                "recorded in compiler-mutation.json"
            ),
            "purpose": "test-only compiler mutant and freestanding machine harness",
        },
        TEST_FRONTEND_SUITE_POLICY: {
            "kind": "test-frontend-suite-llvm",
            "source": (
                "program.ll generated from the deduplicated checked Core0 root suite "
                "and typed scalar batch harness"
            ),
            "purpose": (
                "test-only multi-root frontend conformance, RV64 LP64 ABI, and "
                "freestanding batch execution"
            ),
        },
        TEST_CFG_SUITE_POLICY: {
            "kind": "test-cfg-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.2 suite through "
                "validated structured control-flow lowering and the typed scalar harness"
            ),
            "purpose": (
                "test-only structured CFG, total scalar-operation semantics, and "
                "freestanding source/model/RV64 comparison"
            ),
        },
        TEST_LOOP_SUITE_POLICY: {
            "kind": "test-loop-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.3 bounded-iteration "
                "suite through validated structured loop lowering and the typed scalar harness"
            ),
            "purpose": (
                "test-only runtime-counted bounded iteration, stack measurement, and "
                "freestanding source/model/RV64 comparison"
            ),
        },
        TEST_MEMORY_SUITE_POLICY: {
            "kind": "test-memory-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.4 Action suite through "
                "validated fixed-region memory lowering and the bounded memory harness"
            ),
            "purpose": (
                "test-only checked ordinary-RAM access, explicit effects, canary "
                "observation, and freestanding source/model/RV64 comparison"
            ),
        },
        TEST_DEVICE_SUITE_POLICY: {
            "kind": "test-device-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.5 Action suite through "
                "validated ordered-MMIO lowering and the status-only device harness"
            ),
            "purpose": (
                "test-only compiled UART polling, framing, multi-request dispatch, "
                "bounded timeout behavior, and freestanding QEMU interaction"
            ),
        },
        TEST_TRAP_SUITE_POLICY: {
            "kind": "test-trap-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.6 Action suite through "
                "validated synchronous-trap lowering and the trap test harness"
            ),
            "purpose": (
                "test-only M-mode synchronous-trap dispatch, full-context preservation, "
                "fatal containment, and freestanding QEMU interaction"
            ),
        },
        TEST_TIMER_SUITE_POLICY: {
            "kind": "test-timer-suite-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.7 Action suite through "
                "validated machine-timer and asynchronous-interrupt lowering"
            ),
            "purpose": (
                "test-only machine-timer policy, asynchronous M-mode interrupt dispatch, "
                "bounded event-ring behavior, and freestanding QEMU interaction"
            ),
        },
        TEST_MONITOR_IMAGE_POLICY: {
            "kind": "test-monitor-image-llvm",
            "source": (
                "program.ll generated from the checked Core0 v0.7 monitor Action suite "
                "through validated device, trap, and machine-timer lowering"
            ),
            "purpose": (
                "test-only bounded binary monitor protocol, compiled command policies, "
                "asynchronous timer dispatch, and freestanding QEMU interaction"
            ),
        },
    }[policy]
    if policy in {TEST_TIMER_SUITE_POLICY, TEST_MONITOR_IMAGE_POLICY}:
        startup_input_details = {
            "kind": "lean-structured-timer-startup",
            "generation_command": EXPECTED_STARTUP_COMMAND,
            "source": "startup.S generated by Lemma.Machine.TimerPrimitives",
            "purpose": (
                "M-mode entry, machine-timer initialization and fenced MMIO/CSR leaves, "
                "full asynchronous/synchronous trap context handling, timer probe, "
                "fatal containment, and I/O fence"
            ),
        }
    elif policy == TEST_TRAP_SUITE_POLICY:
        startup_input_details = {
            "kind": "lean-structured-trap-startup",
            "generation_command": EXPECTED_STARTUP_COMMAND,
            "source": "startup.S generated by Lemma.Machine.TrapPrimitives",
            "purpose": (
                "M-mode entry, full synchronous-trap context save/restore, "
                "trap probes/fatal finishers, and I/O fence"
            ),
        }
    else:
        startup_input_details = {
            "kind": "lean-structured-startup",
            "generation_command": EXPECTED_STARTUP_COMMAND,
            "source": "startup.S generated by Lemma.Machine.Primitives",
            "purpose": "M-mode entry, BSS clearing, a0/a1 boot-input preservation, and I/O fence",
        }
    expected_input_details: dict[str, dict[str, object]] = {
        "startup.o": startup_input_details,
        "program.o": {
            "kind": program_input_details["kind"],
            "generation_command": expected_program_command(optimization, policy),
            "source": program_input_details["source"],
            "purpose": program_input_details["purpose"],
        },
    }
    expected_inputs = {
        name: str(details["kind"]) for name, details in expected_input_details.items()
    }
    observed_inputs: dict[str, str] = {}
    for item in linked:
        if not isinstance(item, dict):
            raise Core0Error("malformed linked-input provenance entry")
        name, kind, digest = item.get("path"), item.get("kind"), item.get("sha256")
        generation_command = item.get("generation_command")
        source = item.get("source")
        purpose = item.get("purpose")
        if not isinstance(name, str) or Path(name).name != name:
            raise Core0Error(f"linked input must be a local basename, got {name!r}")
        if not isinstance(kind, str) or not isinstance(digest, str):
            raise Core0Error(f"linked input {name!r} lacks kind/hash provenance")
        if (
            not isinstance(generation_command, list)
            or not generation_command
            or any(not isinstance(arg, str) or not arg for arg in generation_command)
            or not isinstance(source, str)
            or not source
            or not isinstance(purpose, str)
            or not purpose
        ):
            raise Core0Error(f"linked input {name!r} lacks generation/source/purpose provenance")
        if name not in expected_inputs or expected_inputs[name] != kind:
            raise Core0Error(f"unexpected linked object or provenance kind: {name!r} ({kind!r})")
        expected_details = expected_input_details[name]
        for field in ("generation_command", "source", "purpose"):
            if item.get(field) != expected_details[field]:
                raise Core0Error(f"linked input {name!r} has unexpected {field} provenance")
        actual = sha256(directory / name)
        if digest != actual:
            raise Core0Error(f"linked input hash mismatch for {name}: {digest} != {actual}")
        observed_inputs[name] = kind
    if observed_inputs != expected_inputs:
        raise Core0Error("linked-input provenance is incomplete")
    if provenance_obj.get("link_command") != EXPECTED_LINK_COMMAND:
        raise Core0Error("provenance link command differs from the exact two-object link")
    commands = provenance_obj.get("commands")
    if not isinstance(commands, list) or any(not isinstance(command, dict) for command in commands):
        raise Core0Error("provenance command log is missing or malformed")
    from build_actions import admitted_commands
    commands = admitted_commands(commands, root=root, output_dir=directory)
    # Historical Core0 command relations use executable names; producer
    # receipts retain the actual pinned absolute executable paths.
    commands = [{**row, "argv": [Path(row["argv"][0]).name.replace("clang-20", "clang"), *row["argv"][1:]]}
                if row.get("admitted_route") else row for row in commands]
    command_argv = [command.get("argv") for command in commands]
    if scalar_export_configuration is not None:
        validate_scalar_export_command_log(
            scalar_export_configuration, command_argv
        )
    if memory_export_configuration is not None:
        validate_scalar_export_command_log(
            memory_export_configuration, command_argv
        )
    if device_export_configuration is not None:
        validate_scalar_export_command_log(
            device_export_configuration, command_argv
        )
    if trap_export_configuration is not None:
        validate_scalar_export_command_log(
            trap_export_configuration, command_argv
        )
    if timer_export_configuration is not None:
        validate_scalar_export_command_log(
            timer_export_configuration, command_argv
        )
    if (
        trap_export_configuration is not None
        or timer_export_configuration is not None
        or policy == TEST_MONITOR_IMAGE_POLICY
    ):
        for platform_command in (
            qemu_dtb_command,
            [
                "dtc", "-I", "dtb", "-O", "dts", "-o",
                "platform.dts", "platform.dtb",
            ],
        ):
            if platform_command not in command_argv:
                raise Core0Error(
                    f"{policy} provenance command log omits a pinned platform command"
                )
    for expected_command in expected_elaboration_commands:
        if expected_command not in command_argv:
            raise Core0Error(
                f"provenance command log omits Lean elaboration command: {expected_command!r}"
            )
    for expected_command in (
        expected_program_command(optimization, policy),
        EXPECTED_STARTUP_COMMAND,
        EXPECTED_LINK_COMMAND,
    ):
        if expected_command not in command_argv:
            raise Core0Error(f"provenance command log omits exact command: {expected_command!r}")

    pre_ir = paths["program.ll"].read_text(encoding="utf-8")
    post_ir = paths["program.opt.ll"].read_text(encoding="utf-8")
    if mutation_manifest is not None:
        validate_compiler_mutation_ir(mutation_manifest, pre_ir)
        if clean_control_directory is None:
            raise Core0Error("compiler mutant lacks its resolved clean-control directory")
        for name in MUTANT_CONTROL_IDENTICAL_ARTIFACTS:
            mutant_digest = sha256(directory / name)
            control_digest = sha256(clean_control_directory / name)
            if mutant_digest != control_digest:
                raise Core0Error(
                    f"compiler mutant {name} differs from its immutable clean control"
                )
        clean_ir_path = clean_control_directory / "program.ll"
        if not clean_ir_path.is_file():
            raise Core0Error("compiler mutant clean control lacks program.ll")
        validate_mutant_control_delta(
            mutation_manifest,
            pre_ir,
            clean_ir_path.read_text(encoding="utf-8"),
        )
    if policy in {
        TEST_MEMORY_SUITE_POLICY,
        TEST_DEVICE_SUITE_POLICY,
        TEST_TRAP_SUITE_POLICY,
        TEST_TIMER_SUITE_POLICY,
        TEST_MONITOR_IMAGE_POLICY,
    }:
        scalar_functions = manifest.get("scalar_functions")
        action_functions = manifest.get("action_functions")
        if not isinstance(scalar_functions, list) or not isinstance(action_functions, list):
            raise Core0Error(f"{policy} target manifest function arrays are malformed")
        manifest_functions = [*scalar_functions, *action_functions]
    else:
        manifest_functions = manifest["functions"]
        if not isinstance(manifest_functions, list):
            raise Core0Error("target manifest function array is malformed")
    manifest_user_symbols = {
        str(function["llvm"])
        for function in manifest_functions
        if isinstance(function, dict)
    }
    machine_ir_functions = (
        DEVICE_MACHINE_IR_FUNCTIONS
        if policy in {
            TEST_DEVICE_SUITE_POLICY,
            TEST_TRAP_SUITE_POLICY,
            TEST_TIMER_SUITE_POLICY,
            TEST_MONITOR_IMAGE_POLICY,
        }
        else MACHINE_IR_FUNCTIONS
    )
    expected_pre_definitions = manifest_user_symbols | machine_ir_functions
    scalar_abi_ir: dict[str, object] | None = None
    if policy == TEST_MONITOR_IMAGE_POLICY:
        monitor_ir_audit = audit_monitor.validate_monitor_ir(
            manifest, pre_ir, post_ir, optimization
        )
        source_identity = audit_monitor.SOURCE_IDENTITY
        root_llvm = None
    elif policy == TEST_TIMER_SUITE_POLICY:
        timer_ir_audit = audit_timer.validate_timer_ir(
            manifest, pre_ir, post_ir, optimization
        )
        source_identity = audit_timer.SOURCE_IDENTITY
        root_llvm = None
    elif policy == TEST_TRAP_SUITE_POLICY:
        trap_ir_audit = audit_trap.validate_trap_ir(
            manifest, pre_ir, post_ir, optimization
        )
        source_identity = audit_trap.SOURCE_IDENTITY
        root_llvm = None
    elif policy == TEST_DEVICE_SUITE_POLICY:
        source_identity = "Lemma Gate 6 compiled UART device session"
        root_llvm = None
    elif policy == TEST_MEMORY_SUITE_POLICY:
        memory_ir_audit = audit_memory.validate_memory_pre_ir(manifest, pre_ir)
        source_identity = "Lemma Gate 5 checked fixed-memory suite"
        root_llvm = None
    elif policy in SCALAR_SUITE_POLICIES:
        scalar_abi_ir = validate_scalar_pre_abi(manifest, pre_ir)
        validate_scalar_post_noinline(manifest, post_ir)
        if policy == TEST_CFG_SUITE_POLICY:
            scalar_abi_ir["structured_semantics"] = validate_cfg_pre_semantics(
                manifest, pre_ir
            )
            source_identity = "Lemma Gate 3 structured scalar suite"
        elif policy == TEST_LOOP_SUITE_POLICY:
            scalar_abi_ir["bounded_iteration"] = validate_loop_pre_semantics(
                manifest, pre_ir
            )
            scalar_abi_ir["scalar_domains"] = validate_v03_scalar_domains(
                manifest, pre_ir
            )
            source_identity = "Lemma Gate 4 bounded iteration suite"
        else:
            source_identity = "Lemma Gate 2 typed scalar suite"
        root_llvm: str | None = None
    else:
        source_identity = str(manifest["root"])
        root_llvm = str(manifest["root_llvm"])
    ir_findings: dict[str, object] = {}
    for label, ir in (("pre_optimization", pre_ir), ("post_optimization", post_ir)):
        if f'source_filename = "{source_identity}"' not in ir:
            raise Core0Error(f"{label} IR source identity differs from the target manifest")
        if 'target triple = "riscv64-unknown-unknown-elf"' not in ir:
            raise Core0Error(f"{label} IR has the wrong or missing target triple")
        if 'target datalayout = "e-m:e-p:64:64-i64:64-i128:128-n32:64-S128"' not in ir:
            raise Core0Error(f"{label} IR has the wrong or missing data layout")
        inferred_flags = sorted(set(FORBIDDEN_IR_FLAGS.findall(ir)))
        # The Lean renderer must not assert poison-sensitive premises.  The pinned
        # optimizer may infer nsw/nuw from ranges and bounded harness loops; those
        # are recorded as optimizer output.  This profile emits no GEP, so an
        # optimized `inbounds` remains unexpected.
        if label == "pre_optimization" and inferred_flags:
            raise Core0Error(f"{label} IR contains unjustified flags: {inferred_flags}")
        if (
            label == "post_optimization"
            and "inbounds" in inferred_flags
            and policy not in {
                TEST_MEMORY_SUITE_POLICY,
                TEST_DEVICE_SUITE_POLICY,
                TEST_TRAP_SUITE_POLICY,
                TEST_TIMER_SUITE_POLICY,
                TEST_MONITOR_IMAGE_POLICY,
            }
        ):
            raise Core0Error("optimized IR unexpectedly contains an inbounds promise")
        definitions, declarations, calls = parse_definitions_and_calls(ir)
        if re.search(r"\b(?:invoke|callbr)\b|\basm\b", ir):
            raise Core0Error(f"{label} IR contains indirect control flow or inline assembly")
        for line in ir.splitlines():
            stripped = line.strip()
            is_call = re.match(
                r"^(?:%[A-Za-z0-9_.$-]+\s*=\s*)?(?:(?:musttail|tail|notail)\s+)?call\b",
                stripped,
            ) is not None
            if is_call and re.search(
                r"\bcall\b[^@\n]*@[A-Za-z0-9_.$-]+\(", line
            ) is None:
                raise Core0Error(f"{label} IR contains an indirect or unparseable call: {stripped}")
        expected_externals = set(ALLOWED_EXTERNALS)
        if policy == TEST_TRAP_SUITE_POLICY:
            expected_externals.update(audit_trap.TRAP_EXTERNALS)
        elif policy == TEST_TIMER_SUITE_POLICY:
            expected_externals.update(audit_timer.TIMER_EXTERNALS)
            expected_externals.update(
                str(item["llvm_symbol"])
                for item in manifest["used_trap_ops"]
                if isinstance(item, dict)
            )
        elif policy == TEST_MONITOR_IMAGE_POLICY:
            expected_externals.update(audit_monitor.MONITOR_EXTERNALS)
        if (
            policy in {
                TEST_FRONTEND_SUITE_POLICY,
                TEST_CFG_SUITE_POLICY,
            }
            and label == "post_optimization"
            and optimization == "O2"
        ):
            expected_externals.add("llvm.umax.i64")
        if (
            policy == TEST_TIMER_SUITE_POLICY
            and label == "post_optimization"
            and optimization == "O2"
        ):
            expected_externals.add("llvm.umin.i64")
        if declarations != expected_externals:
            raise Core0Error(
                f"{label} IR external declarations differ from the exact machine-primitive "
                f"allowlist: {sorted(declarations)}"
            )
        unresolved_calls = calls - definitions
        if unresolved_calls != expected_externals:
            raise Core0Error(f"{label} IR has unresolved calls: {sorted(unresolved_calls)}")
        forbidden = sorted(name for name in definitions | calls if FORBIDDEN_SYMBOL.search(name))
        if forbidden:
            raise Core0Error(f"{label} IR contains forbidden runtime symbols: {forbidden}")
        if label == "pre_optimization" and definitions != expected_pre_definitions:
            raise Core0Error(
                "pre_optimization IR function closure differs from the manifest and "
                f"machine allowlist: {sorted(definitions)!r}"
            )
        if label == "post_optimization":
            if policy in SCALAR_SUITE_POLICIES or policy in {
                TEST_MEMORY_SUITE_POLICY,
                TEST_DEVICE_SUITE_POLICY,
                TEST_TRAP_SUITE_POLICY,
                TEST_TIMER_SUITE_POLICY,
                TEST_MONITOR_IMAGE_POLICY,
            }:
                required_post_definitions = manifest_user_symbols | {"core0_main"}
            else:
                if root_llvm is None:
                    raise Core0Error("non-suite manifest lacks its LLVM root identity")
                required_post_definitions = {root_llvm, "core0_main"}
            if (
                not definitions <= expected_pre_definitions
                or not required_post_definitions <= definitions
            ):
                raise Core0Error(
                    "post_optimization IR created an unknown function or removed a required root: "
                    f"{sorted(definitions)!r}"
                )
        ir_findings[label] = {
            "definitions": sorted(definitions),
            "calls": sorted(calls),
            "external_declarations": sorted(declarations),
            "poison_sensitive_flags": {
                flag: len(re.findall(rf"\b{flag}\b", ir))
                for flag in ("nsw", "nuw", "inbounds", "disjoint")
            },
        }
        if label == "post_optimization":
            if policy == TEST_MEMORY_SUITE_POLICY:
                ir_findings[label]["optimizer_flags"] = validate_memory_optimizer_flags(
                    ir, optimization
                )
            elif policy in {
                TEST_DEVICE_SUITE_POLICY,
                TEST_TRAP_SUITE_POLICY,
                TEST_TIMER_SUITE_POLICY,
                TEST_MONITOR_IMAGE_POLICY,
            }:
                flag_counts = {
                    flag: len(re.findall(rf"\b{flag}\b", ir))
                    for flag in ("nsw", "nuw", "inbounds", "disjoint")
                }
                if optimization == "O0" and any(flag_counts.values()):
                    raise Core0Error(
                        "O0 device IR unexpectedly contains optimizer flags: "
                        f"{flag_counts!r}"
                    )
                ir_findings[label]["optimizer_flag_inventory"] = {
                    "optimization": optimization,
                    "counts": flag_counts,
                }
            else:
                ir_findings[label]["optimizer_disjoint"] = validate_optimizer_disjoint(
                    ir,
                    expected_exhaustion_tags=(
                        len(LOOP_ROOT_SOURCES)
                        if policy == TEST_LOOP_SUITE_POLICY and optimization == "O2"
                        else 0
                    ),
                )

    elf = paths["image.elf"]
    header = tool_text("llvm-readelf", ["-h", str(elf)], root)
    programs = tool_text("llvm-readelf", ["-l", str(elf)], root)
    relocations = tool_text("llvm-readelf", ["-r", str(elf)], root)
    dynamic = tool_text("llvm-readelf", ["-d", str(elf)], root)
    attributes = tool_text("llvm-readelf", ["-A", str(elf)], root)
    sections = tool_text("llvm-readelf", ["--wide", "-S", "-s", str(elf)], root)
    undefined = tool_text("llvm-nm", ["--undefined-only", str(elf)], root)
    disassembly = tool_text("llvm-objdump", ["-d", "--no-show-raw-insn", str(elf)], root)
    symbols = tool_text("llvm-nm", ["--defined-only", "--numeric-sort", str(elf)], root)

    required_header = (
        "Class:                             ELF64",
        "Data:                              2's complement, little endian",
        "Type:                              EXEC",
        "Machine:                           RISC-V",
        "Entry point address:               0x80000000",
        "Flags:                             0x0",
    )
    for expected in required_header:
        if expected not in header:
            raise Core0Error(f"ELF header check failed: missing {expected!r}")
    if " INTERP " in programs or " DYNAMIC " in programs:
        raise Core0Error("ELF contains an interpreter or dynamic segment")
    gnu_stack = next(
        (line for line in programs.splitlines() if line.lstrip().startswith("GNU_STACK")),
        None,
    )
    if gnu_stack is None or re.search(r"\sRW\s+0x", gnu_stack) is None or " E " in gnu_stack:
        raise Core0Error("ELF lacks an explicit non-executable RW GNU_STACK segment")

    layout = load_json(paths["layout.json"])
    image_start = hex_field(layout, "image", "start")
    image_size = hex_field(layout, "image", "size")
    image_stop = image_start + image_size
    layout_contract = {
        ("ram", "start"): 0x80000000,
        ("ram", "size"): 0x08000000,
        ("image", "start"): 0x80000000,
        ("image", "size"): 0x007F0000,
        ("stack", "start"): 0x807F0000,
        ("stack", "size"): 0x00010000,
        ("input", "start"): 0x81000000,
        ("input", "size"): 0x00001000,
        ("uart_16550", "base"): 0x10000000,
        ("uart_16550", "size"): 0x00000100,
        ("sifive_test", "base"): 0x00100000,
    }
    for (region, field), expected_value in layout_contract.items():
        observed_value = hex_field(layout, region, field)
        if observed_value != expected_value:
            raise Core0Error(
                f"layout.json {region}.{field} differs from LemmaVM v0.1: "
                f"0x{observed_value:x} != 0x{expected_value:x}"
            )
    load_segments = parse_load_segments(programs)
    lowest = min(load_segments, key=lambda item: int(item["virtual_address"]))
    if lowest["virtual_address"] != image_start or "E" not in str(lowest["flags"]):
        raise Core0Error(
            "lowest PT_LOAD is not executable at the QEMU reset destination "
            f"0x{image_start:x}: {lowest}"
        )
    for segment in load_segments:
        virtual = int(segment["virtual_address"])
        physical = int(segment["physical_address"])
        memory_size = int(segment["memory_size"])
        flags = str(segment["flags"])
        if virtual != physical:
            raise Core0Error(f"PT_LOAD VMA/LMA mismatch: {segment}")
        if virtual < image_start or virtual + memory_size > image_stop:
            raise Core0Error(f"PT_LOAD lies outside the declared image envelope: {segment}")
        if "W" in flags and "E" in flags:
            raise Core0Error(f"PT_LOAD is writable and executable: {segment}")
    alloc_sections = alloc_section_names(sections)
    required_alloc_sections = {".text", ".bss"}
    if policy not in {
        TEST_DEVICE_SUITE_POLICY,
        TEST_TRAP_SUITE_POLICY,
        TEST_TIMER_SUITE_POLICY,
        TEST_MONITOR_IMAGE_POLICY,
    }:
        required_alloc_sections.add(".rodata")
    if not required_alloc_sections <= alloc_sections:
        raise Core0Error(f"ELF is missing required allocated sections: {sorted(alloc_sections)!r}")
    unexpected_alloc_sections = alloc_sections - FINAL_ALLOC_SECTIONS
    if unexpected_alloc_sections:
        raise Core0Error(
            "ELF contains an unexpected allocated/orphan section: "
            + repr(sorted(unexpected_alloc_sections))
        )
    start_match = re.search(r"^([0-9a-fA-F]+)\s+\S\s+_start$", symbols, re.MULTILINE)
    if start_match is None or int(start_match.group(1), 16) != image_start:
        raise Core0Error("_start is missing or does not equal the QEMU reset destination")
    symbol_addresses = numeric_symbols(symbols)
    stack_start = hex_field(layout, "stack", "start")
    stack_size = hex_field(layout, "stack", "size")
    input_start = hex_field(layout, "input", "start")
    if not isinstance(layout, dict) or layout.get("schema_version") != 1:
        raise Core0Error("layout.json has an unsupported schema")
    stack_layout = layout.get("stack")
    input_layout = layout.get("input")
    if (
        not isinstance(stack_layout, dict)
        or stack_layout.get("alignment") != 16
        or not isinstance(input_layout, dict)
        or input_layout.get("alignment") != 8
    ):
        raise Core0Error("layout.json has the wrong stack or runtime-input alignment")
    expected_layout_symbols = {
        "__stack_bottom": stack_start,
        "__stack_top": stack_start + stack_size,
        "__core0_input": input_start,
    }
    for name, expected_address in expected_layout_symbols.items():
        if symbol_addresses.get(name) != expected_address:
            raise Core0Error(
                f"ELF symbol {name} does not match layout.json: "
                f"{symbol_addresses.get(name)!r} != 0x{expected_address:x}"
            )
    trap_layout_audit: dict[str, object] | None = None
    trap_startup_audit: dict[str, object] | None = None
    timer_layout_audit: dict[str, object] | None = None
    timer_startup_audit: dict[str, object] | None = None
    monitor_layout_audit: dict[str, object] | None = None
    monitor_startup_audit: dict[str, object] | None = None
    if policy == TEST_MONITOR_IMAGE_POLICY:
        monitor_layout_audit = audit_trap.validate_trap_layout(layout, symbol_addresses)
        monitor_startup_audit = audit_monitor.validate_monitor_startup_assembly(
            paths["startup.S"].read_text(encoding="utf-8"), manifest, layout
        )
    elif policy == TEST_TIMER_SUITE_POLICY:
        timer_layout_audit = audit_trap.validate_trap_layout(layout, symbol_addresses)
        timer_startup_audit = audit_timer.validate_timer_startup_assembly(
            paths["startup.S"].read_text(encoding="utf-8"), manifest, layout
        )
    elif policy == TEST_TRAP_SUITE_POLICY:
        trap_layout_audit = audit_trap.validate_trap_layout(layout, symbol_addresses)
        trap_startup_audit = audit_trap.validate_trap_startup_assembly(
            paths["startup.S"].read_text(encoding="utf-8"), manifest, layout
        )
    bss_start = symbol_addresses.get("__bss_start")
    bss_end = symbol_addresses.get("__bss_end")
    if (
        bss_start is None
        or bss_end is None
        or bss_start % 16 != 0
        or bss_end % 16 != 0
        or symbol_addresses.get("__boot_hartid") != bss_start
        or symbol_addresses.get("__boot_dtb") != bss_start + 8
        or bss_end < bss_start + 16
        or symbol_addresses.get("__image_end") != bss_end
    ):
        raise Core0Error("ELF BSS/boot-input symbols violate the exact startup layout")
    if "There are no relocations in this file." not in relocations:
        raise Core0Error("final ELF still contains relocations")
    if dynamic.strip() and "There is no dynamic section in this file." not in dynamic:
        raise Core0Error("final ELF has a dynamic dependency section")
    if re.search(r"\.(?:dynamic|dynsym|dynstr)\b", sections):
        raise Core0Error("final ELF contains a dynamic-linking section")
    if undefined.strip():
        raise Core0Error("final ELF has undefined symbols:\n" + undefined)
    if "stack_align" not in attributes or "16-bytes" not in attributes:
        raise Core0Error("ELF attributes do not establish 16-byte stack alignment")
    arch_match = re.search(r"Value: (rv64[^\n]+)", attributes)
    if arch_match is None:
        raise Core0Error("ELF RISC-V architecture attribute is missing")
    arch = arch_match.group(1)
    if re.search(r"(?:^|_)[afdcv](?:\d|_|$)", arch):
        raise Core0Error(f"ELF advertises a forbidden non-integer extension: {arch}")
    if (
        policy not in {
            TEST_TRAP_SUITE_POLICY,
            TEST_TIMER_SUITE_POLICY,
            TEST_MONITOR_IMAGE_POLICY,
        }
        and re.search(r"\b(?:gp|f[0-9]+|v[0-9]+)\b", disassembly)
    ):
        raise Core0Error("disassembly uses gp, floating-point, or vector registers")
    if FORBIDDEN_SYMBOL.search(sections + disassembly):
        raise Core0Error("ELF symbol/disassembly inventory contains a forbidden runtime symbol")
    start_disassembly = disassembly.split("<_start>:", 1)
    if len(start_disassembly) != 2:
        raise Core0Error("disassembly lacks the generated _start body")
    start_body = start_disassembly[1].split("<core0_io_fence>:", 1)[0]
    startup_patterns = (
        (
            r"\bcsrw\s+mie,\s*zero",
            r"\bcsrci\s+mstatus,\s*0x8",
            r"\bauipc\s+sp,",
            r"\baddi\s+sp,\s*sp,",
            r"\bmv\s+s0,\s*a0",
            r"\bmv\s+s1,\s*a1",
            r"\bsd\s+zero,",
            r"\bsd\s+s0,",
            r"\bsd\s+s1,",
            r"\bcsrw\s+mtvec,",
            r"\bcsrw\s+mscratch,",
            r"<core0_main>",
            r"\bwfi\b",
        )
        if policy in {
            TEST_TRAP_SUITE_POLICY,
            TEST_TIMER_SUITE_POLICY,
            TEST_MONITOR_IMAGE_POLICY,
        }
        else (
            r"\bauipc\s+sp,",
            r"\bmv\s+sp,\s*sp",
            r"\bmv\s+s0,\s*a0",
            r"\bmv\s+s1,\s*a1",
            r"\bsd\s+zero,",
            r"\bsd\s+s0,",
            r"\bsd\s+s1,",
            r"<core0_main>",
            r"\bwfi\b",
        )
    )
    if any(re.search(pattern, start_body) is None for pattern in startup_patterns):
        raise Core0Error("generated startup disassembly lacks a required entry/BSS/boot invariant")
    fence_body_parts = disassembly.split("<core0_io_fence>:", 1)
    if len(fence_body_parts) != 2:
        raise Core0Error("disassembly lacks core0_io_fence")
    fence_body = fence_body_parts[1].split("\n\n", 1)[0]
    if re.search(r"\bfence\b", fence_body) is None or re.search(r"\bret\b", fence_body) is None:
        raise Core0Error("core0_io_fence does not lower to a fence followed by return")
    device_machine_audit: dict[str, object] | None = None
    trap_machine_audit: dict[str, object] | None = None
    timer_machine_audit: dict[str, object] | None = None
    monitor_machine_audit: dict[str, object] | None = None
    if policy == TEST_DEVICE_SUITE_POLICY:
        device_machine_audit = validate_device_machine_disassembly(
            disassembly, symbol_addresses, optimization=optimization
        )
    elif policy == TEST_TRAP_SUITE_POLICY:
        trap_program_symbols = set(ir_findings["post_optimization"]["definitions"])
        trap_program_start = min(symbol_addresses[name] for name in trap_program_symbols)
        device_machine_audit = validate_device_machine_disassembly(
            disassembly,
            symbol_addresses,
            expected_access_sequence=TRAP_MACHINE_ACCESS_SEQUENCE,
            expected_denied_metadata=TRAP_MACHINE_DENIED_METADATA,
            optimization=optimization,
            ignored_functions=frozenset(audit_trap.TRAP_STARTUP_FUNCTIONS),
            ignored_address_ranges=((symbol_addresses["_start"], trap_program_start),),
        )
        trap_machine_audit = audit_trap.validate_trap_machine_disassembly(
            disassembly,
            symbol_addresses,
            trap_program_symbols,
            paths["startup.S"].read_text(encoding="utf-8"),
        )
        if trap_layout_audit is None or trap_startup_audit is None:
            raise Core0Error("trap layout/startup audit evidence is missing")
        trap_machine_audit["layout"] = trap_layout_audit
        trap_machine_audit["startup"] = trap_startup_audit
    elif policy == TEST_MONITOR_IMAGE_POLICY:
        monitor_program_symbols = set(ir_findings["post_optimization"]["definitions"])
        monitor_program_start = min(
            symbol_addresses[name] for name in monitor_program_symbols
        )
        if not audit_monitor.MONITOR_MACHINE_ACCESS_SEQUENCE:
            raise Core0Error("monitor final UART access sequence has not been pinned")
        if not audit_monitor.MONITOR_MACHINE_DENIED_METADATA:
            raise Core0Error("monitor denied-UART metadata inventory has not been pinned")
        device_machine_audit = validate_device_machine_disassembly(
            disassembly,
            symbol_addresses,
            expected_access_sequence=audit_monitor.MONITOR_MACHINE_ACCESS_SEQUENCE,
            expected_denied_metadata=audit_monitor.MONITOR_MACHINE_DENIED_METADATA,
            optimization=optimization,
            ignored_functions=frozenset(audit_monitor.MONITOR_STARTUP_FUNCTIONS),
            ignored_address_ranges=((symbol_addresses["_start"], monitor_program_start),),
        )
        monitor_machine_audit = audit_monitor.validate_monitor_machine_disassembly(
            disassembly,
            symbol_addresses,
            monitor_program_symbols,
            paths["startup.S"].read_text(encoding="utf-8"),
            manifest,
            optimization,
        )
        if monitor_layout_audit is None or monitor_startup_audit is None:
            raise Core0Error("monitor layout/startup audit evidence is missing")
        monitor_machine_audit["layout"] = monitor_layout_audit
        monitor_machine_audit["startup"] = monitor_startup_audit
    elif policy == TEST_TIMER_SUITE_POLICY:
        timer_program_symbols = set(ir_findings["post_optimization"]["definitions"])
        timer_program_start = min(
            symbol_addresses[name] for name in timer_program_symbols
        )
        device_machine_audit = validate_device_machine_disassembly(
            disassembly,
            symbol_addresses,
            expected_access_sequence=TIMER_MACHINE_ACCESS_SEQUENCE,
            expected_denied_metadata=TIMER_MACHINE_DENIED_METADATA,
            optimization=optimization,
            ignored_functions=frozenset(audit_timer.TIMER_STARTUP_FUNCTIONS),
            ignored_address_ranges=((symbol_addresses["_start"], timer_program_start),),
        )
        timer_machine_audit = audit_timer.validate_timer_machine_disassembly(
            disassembly,
            symbol_addresses,
            timer_program_symbols,
            paths["startup.S"].read_text(encoding="utf-8"),
            manifest,
            optimization,
        )
        if timer_layout_audit is None or timer_startup_audit is None:
            raise Core0Error("timer layout/startup audit evidence is missing")
        timer_machine_audit["layout"] = timer_layout_audit
        timer_machine_audit["startup"] = timer_startup_audit
    scalar_abi_machine: dict[str, object] | None = None
    if policy == TEST_FRONTEND_SUITE_POLICY:
        scalar_abi_machine = validate_scalar_abi_disassembly(
            manifest, disassembly, optimization
        )
    elif policy == TEST_CFG_SUITE_POLICY:
        scalar_abi_machine = validate_cfg_machine_disassembly(disassembly)
    elif policy == TEST_LOOP_SUITE_POLICY:
        scalar_abi_machine = validate_loop_machine_disassembly(
            manifest, disassembly, optimization
        )

    map_text = paths["image.map"].read_text(encoding="utf-8", errors="strict")
    for name in expected_inputs:
        if name not in map_text:
            raise Core0Error(f"link map does not mention {name}")
    if ".a(" in map_text or re.search(r"\.(?:so|a)\b", map_text):
        raise Core0Error("link map contains an archive or shared library")

    object_inventories = {
        name: tool_text(
            "llvm-readelf", ["--wide", "-S", "-s", str(directory / name)], root
        )
        for name in expected_inputs
    }
    post_definitions = set(ir_findings["post_optimization"]["definitions"])
    object_function_symbols = {
        name: defined_function_symbols(inventory)
        for name, inventory in object_inventories.items()
    }
    if object_function_symbols["program.o"] != post_definitions:
        raise Core0Error(
            "program.o defined-function closure differs from optimized LLVM: "
            + repr(sorted(object_function_symbols["program.o"]))
        )
    if policy == TEST_MONITOR_IMAGE_POLICY:
        expected_startup_functions = audit_monitor.MONITOR_STARTUP_FUNCTIONS
    elif policy == TEST_TIMER_SUITE_POLICY:
        expected_startup_functions = audit_timer.TIMER_STARTUP_FUNCTIONS
    elif policy == TEST_TRAP_SUITE_POLICY:
        expected_startup_functions = audit_trap.TRAP_STARTUP_FUNCTIONS
    else:
        expected_startup_functions = {"_start", "core0_io_fence"}
    if object_function_symbols["startup.o"] != expected_startup_functions:
        raise Core0Error(
            "startup.o defined-function closure differs from the exact primitive allowlist: "
            + repr(sorted(object_function_symbols["startup.o"]))
        )
    stack_sizes_text: str | None = None
    stack_sizes: dict[str, int] | None = None
    stack_and_call_graph: dict[str, object] | None = None
    has_stack_sizes = ".stack_sizes" in object_inventories["program.o"]
    if policy in STACK_SIZE_POLICIES:
        if not has_stack_sizes:
            raise Core0Error(f"{policy} program.o lacks LLVM stack-size sections")
        if ".stack_sizes" not in sections:
            raise Core0Error(f"{policy} final ELF lacks its linked stack-size section")
        stack_sizes_text = tool_text(
            "llvm-readelf", ["--stack-sizes", str(directory / "program.o")], root
        )
        stack_sizes = parse_stack_sizes(stack_sizes_text)
        if set(stack_sizes) != object_function_symbols["program.o"]:
            raise Core0Error(
                "program.o stack-size function set differs from its defined-function closure: "
                + repr(sorted(set(stack_sizes) ^ object_function_symbols["program.o"]))
            )
        oversized_frames = {
            symbol: size for symbol, size in stack_sizes.items() if size > 0x10000
        }
        if oversized_frames:
            raise Core0Error(
                "program.o declares a stack frame larger than the 64-KiB stack: "
                + repr(oversized_frames)
            )
        stack_and_call_graph = validate_loop_stack_call_graph(post_ir, stack_sizes)
        if policy in {
            TEST_TRAP_SUITE_POLICY,
            TEST_TIMER_SUITE_POLICY,
            TEST_MONITOR_IMAGE_POLICY,
        }:
            frame_chains = stack_and_call_graph.get("frame_chains")
            foreground_chain = (
                frame_chains.get("core0_main")
                if isinstance(frame_chains, dict)
                else None
            )
            dispatcher_symbol = (
                audit_trap.DISPATCH_SYMBOL
                if policy == TEST_TRAP_SUITE_POLICY
                else str(manifest["roots"][1]["llvm"])
            )
            foreground_symbol = (
                audit_trap.FOREGROUND_SYMBOL
                if policy == TEST_TRAP_SUITE_POLICY
                else str(manifest["roots"][0]["llvm"])
            )
            dispatcher_chain = (
                frame_chains.get(dispatcher_symbol)
                if isinstance(frame_chains, dict)
                else None
            )
            if (
                not isinstance(foreground_chain, dict)
                or isinstance(foreground_chain.get("bytes"), bool)
                or not isinstance(foreground_chain.get("bytes"), int)
                or foreground_chain["bytes"] > 65520
            ):
                raise Core0Error(
                    f"{policy} foreground compiled call chain exceeds its 65,520-byte capacity"
                )
            if (
                not isinstance(dispatcher_chain, dict)
                or isinstance(dispatcher_chain.get("bytes"), bool)
                or not isinstance(dispatcher_chain.get("bytes"), int)
                or dispatcher_chain["bytes"] > 16048
            ):
                raise Core0Error(
                    f"{policy} dispatcher compiled call chain exceeds its 16,048-byte capacity"
                )
            stack_and_call_graph["foreground"] = {
                **foreground_chain,
                "machine_entry": "core0_main",
                "checked_root": foreground_symbol,
                "capacity_bytes": 65520,
                "stack_region_bytes": 65536,
                "low_canary_bytes": 16,
            }
            stack_and_call_graph["trap_dispatcher"] = {
                **dispatcher_chain,
                "checked_root": dispatcher_symbol,
                "capacity_bytes": 16048,
                "trap_frame_bytes": 288,
                "outgoing_argument_bytes": 16,
                "usable_trap_stack_bytes": 16352,
            }
        if policy == TEST_LOOP_SUITE_POLICY:
            if not isinstance(scalar_abi_machine, dict):
                raise Core0Error("bounded-loop machine audit record is missing")
            scalar_abi_machine["stack_and_call_graph"] = stack_and_call_graph
    elif has_stack_sizes or ".stack_sizes" in sections:
        raise Core0Error(f"{policy} program.o unexpectedly contains Gate-4 stack metadata")
    final_function_symbols = defined_function_symbols(sections)
    expected_final_functions = post_definitions | expected_startup_functions
    if final_function_symbols != expected_final_functions:
        raise Core0Error(
            "final ELF defined-function closure differs from its two input objects: "
            + repr(sorted(final_function_symbols))
        )

    object_undefined = {
        name: tool_text("llvm-nm", ["--undefined-only", str(directory / name)], root).splitlines()
        for name in expected_inputs
    }
    if policy in {
        TEST_TRAP_SUITE_POLICY,
        TEST_TIMER_SUITE_POLICY,
        TEST_MONITOR_IMAGE_POLICY,
    }:
        dispatcher_symbol = (
            audit_trap.DISPATCH_SYMBOL
            if policy == TEST_TRAP_SUITE_POLICY
            else str(manifest["roots"][1]["llvm"])
        )
        startup_allowed = {
            "core0_main",
            dispatcher_symbol,
            "__boot_hartid",
            "__bss_start",
            "__bss_end",
            "__stack_top",
            "__trap_stack_top",
            "__trap_probe_context",
        }
    else:
        startup_allowed = {
            "core0_main", "__boot_hartid", "__bss_start", "__bss_end", "__stack_top"
        }
    startup_names = {
        line.split()[-1]
        for line in object_undefined["startup.o"]
        if line.strip()
    }
    if startup_names != startup_allowed:
        raise Core0Error(
            "startup object undefined-symbol closure differs from the exact allowlist: "
            + repr(sorted(startup_names))
        )
    program_names = {
        line.split()[-1]
        for line in object_undefined["program.o"]
        if line.strip()
    }
    expected_program_names = set(ALLOWED_EXTERNALS)
    if policy == TEST_TRAP_SUITE_POLICY:
        expected_program_names.update(audit_trap.TRAP_EXTERNALS)
    elif policy == TEST_TIMER_SUITE_POLICY:
        expected_program_names.update(audit_timer.TIMER_EXTERNALS)
        expected_program_names.update(
            str(item["llvm_symbol"])
            for item in manifest["used_trap_ops"]
            if isinstance(item, dict)
        )
    elif policy == TEST_MONITOR_IMAGE_POLICY:
        expected_program_names.update(audit_monitor.MONITOR_EXTERNALS)
    if program_names != expected_program_names:
        raise Core0Error(
            "LLVM program object undefined-symbol closure differs from the exact allowlist: "
            + repr(sorted(program_names))
        )

    object_relocations: dict[str, dict[str, object]] = {}
    for name in expected_inputs:
        relocation_text = tool_text("llvm-readelf", ["-r", str(directory / name)], root)
        observed = relocation_types(relocation_text)
        allowed_relocations = set(ALLOWED_RELOCATIONS)
        if policy in {
            TEST_TRAP_SUITE_POLICY,
            TEST_TIMER_SUITE_POLICY,
            TEST_MONITOR_IMAGE_POLICY,
        } and name == "startup.o":
            allowed_relocations.add("R_RISCV_JAL")
        if name == "program.o" and (
            policy in STACK_SIZE_POLICIES
            or (policy in DISPATCH_SUITE_POLICIES and optimization == "O2")
        ):
            # Stack metadata and O2 scalar root dispatch both use
            # narrowly audited local absolute-address relocations.
            allowed_relocations.add(SCALAR_O2_JUMP_TABLE_RELOCATION)
        expected_jump_table_relocations = 0
        if (
            policy in DISPATCH_SUITE_POLICIES
            and name == "program.o"
            and optimization == "O2"
        ):
            manifest_roots = manifest["roots"]
            if not isinstance(manifest_roots, list):
                raise Core0Error("scalar manifest root array is malformed")
            expected_jump_table_relocations = len(manifest_roots)
        elif (
            policy == TEST_DEVICE_SUITE_POLICY
            and name == "program.o"
            and optimization == "O2"
        ):
            expected_jump_table_relocations = DEVICE_O2_JUMP_TABLE_RELOCATIONS
        elif (
            policy == TEST_TRAP_SUITE_POLICY
            and name == "program.o"
            and optimization == "O2"
        ):
            expected_jump_table_relocations = TRAP_O2_JUMP_TABLE_RELOCATIONS
        elif (
            policy == TEST_TIMER_SUITE_POLICY
            and name == "program.o"
            and optimization == "O2"
        ):
            expected_jump_table_relocations = TIMER_O2_JUMP_TABLE_RELOCATIONS
        elif (
            policy == TEST_MONITOR_IMAGE_POLICY
            and name == "program.o"
            and optimization == "O2"
        ):
            if audit_monitor.MONITOR_O2_JUMP_TABLE_RELOCATIONS < 0:
                raise Core0Error("monitor O2 jump-table relocation count has not been pinned")
            expected_jump_table_relocations = (
                audit_monitor.MONITOR_O2_JUMP_TABLE_RELOCATIONS
            )
        forbidden_relocations = observed - allowed_relocations
        if forbidden_relocations:
            raise Core0Error(
                f"{name} contains an unexpected relocation type: {sorted(forbidden_relocations)}"
            )
        if "R_RISCV_RELAX" in relocation_text:
            raise Core0Error(f"{name} contains relaxation relocations despite the no-relax policy")
        if name == "program.o" and SCALAR_O2_JUMP_TABLE_RELOCATION in observed:
            current_section: str | None = None
            jump_table_rows: list[str] = []
            stack_size_rows: list[str] = []
            for line in relocation_text.splitlines():
                section_match = re.match(r"Relocation section '([^']+)'", line)
                if section_match is not None:
                    current_section = section_match.group(1)
                if SCALAR_O2_JUMP_TABLE_RELOCATION in line:
                    if (
                        policy in STACK_SIZE_POLICIES
                        and current_section == ".rela.stack_sizes"
                        and re.search(
                        r"\bR_RISCV_64\b.*\s\.L0\s+\+ 0\s*$", line
                        ) is not None
                    ):
                        stack_size_rows.append(line)
                    elif (
                        (
                            policy in DISPATCH_SUITE_POLICIES
                            or policy in {
                                TEST_DEVICE_SUITE_POLICY,
                                TEST_TRAP_SUITE_POLICY,
                                TEST_TIMER_SUITE_POLICY,
                                TEST_MONITOR_IMAGE_POLICY,
                            }
                        )
                        and optimization == "O2"
                        and current_section == ".rela.rodata"
                        and re.search(
                            r"\bR_RISCV_64\b.*\s\.L0\s+\+ 0\s*$", line
                        ) is not None
                    ):
                        jump_table_rows.append(line)
                    else:
                        raise Core0Error(
                            "program.o R_RISCV_64 relocation is neither exact stack-size "
                            "metadata nor an allowed O2 local jump-table entry"
                        )
            expected_stack_rows = (
                len(object_function_symbols["program.o"])
                if policy in STACK_SIZE_POLICIES
                else 0
            )
            if len(stack_size_rows) != expected_stack_rows:
                raise Core0Error(
                    "program.o stack-size relocation count differs from its exact "
                    f"function closure: {len(stack_size_rows)} != "
                    f"{expected_stack_rows}"
                )
            if len(jump_table_rows) != expected_jump_table_relocations:
                raise Core0Error(
                    "suite O2 jump-table relocation count differs from the exact "
                    f"closed inventory: {len(jump_table_rows)} != "
                    f"{expected_jump_table_relocations}"
                )
        object_relocations[name] = {
            "types": sorted(observed),
            "text": relocation_text,
        }

    linked_objects = {
        Path(match).name
        for match in re.findall(r"(?:^|\s)([^\s:()]+\.o):\(", map_text, re.MULTILINE)
    }
    if linked_objects != set(expected_inputs):
        raise Core0Error(
            "link map object closure differs from provenance: " + repr(sorted(linked_objects))
        )

    hashes = {name: sha256(path) for name, path in sorted(paths.items())}
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "artifact_category": policy,
        "provenance_schema_version": provenance_schema,
        "directory": str(directory.relative_to(root)),
        "source_commit": source_commit,
        "dirty_tree": dirty_tree,
        "optimization": optimization,
        "hashes": hashes,
        "manifest": manifest,
        "linked_inputs": linked,
        "ir": ir_findings,
        "elf": {
            "entry": "0x80000000",
            "machine": "RISC-V",
            "class": "ELF64",
            "endianness": "little",
            "flags": "0x0 (integer/soft-float LP64; no RVC)",
            "dynamic_dependencies": [],
            "undefined_symbols": [],
            "final_relocations": [],
            "load_segments": load_segments,
            "allocated_sections": sorted(alloc_sections),
            "defined_function_symbols": sorted(final_function_symbols),
            "riscv_arch": arch,
        },
        "object_defined_function_symbols": {
            name: sorted(functions) for name, functions in object_function_symbols.items()
        },
        "object_undefined_symbols": {
            "startup.o": sorted(startup_names),
            "program.o": sorted(program_names),
        },
        "object_relocation_types": {
            name: findings["types"] for name, findings in object_relocations.items()
        },
    }
    if stack_sizes is not None:
        report["stack_sizes"] = {
            "section": ".stack_sizes",
            "function_bytes": dict(sorted(stack_sizes.items())),
            "maximum_frame_bytes": max(stack_sizes.values()),
        }
        if stack_and_call_graph is not None:
            report["stack_sizes"]["call_graph"] = stack_and_call_graph
    if mutation_manifest is not None:
        report["compiler_mutation"] = mutation_manifest
        if clean_control_directory is None or clean_control_report is None:
            raise Core0Error("compiler mutant clean-control audit record is missing")
        report["clean_control"] = {
            "directory": str(clean_control_directory.relative_to(root)),
            "program_ll_sha256": sha256(clean_control_directory / "program.ll"),
            "audit_status": clean_control_report.get("status"),
            "artifact_category": clean_control_report.get("artifact_category"),
        }
    if scalar_test_abi is not None:
        if scalar_abi_ir is None or scalar_abi_machine is None:
            raise Core0Error("scalar ABI audit evidence is incomplete")
        report["scalar_test_abi"] = scalar_test_abi
        report["scalar_abi_audit"] = {
            "pre_optimization": scalar_abi_ir,
            "machine_code": scalar_abi_machine,
        }
    if memory_ir_audit is not None:
        report["memory_ir_audit"] = memory_ir_audit
    if device_machine_audit is not None:
        report["device_machine_audit"] = device_machine_audit
    if trap_test_abi is not None:
        report["trap_test_abi"] = trap_test_abi
    if trap_ir_audit is not None:
        report["trap_ir_audit"] = trap_ir_audit
    if trap_machine_audit is not None:
        report["trap_machine_audit"] = trap_machine_audit
    if timer_test_abi is not None:
        report["timer_test_abi"] = timer_test_abi
    if timer_ir_audit is not None:
        report["timer_ir_audit"] = timer_ir_audit
    if timer_machine_audit is not None:
        report["timer_machine_audit"] = timer_machine_audit
    if monitor_abi is not None:
        report["monitor_abi"] = monitor_abi
    if monitor_ir_audit is not None:
        report["monitor_ir_audit"] = monitor_ir_audit
    if monitor_machine_audit is not None:
        report["monitor_machine_audit"] = monitor_machine_audit
    write_json(directory / "audit.json", report)
    inventory = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
    (directory / "sha256sums.txt").write_text(inventory, encoding="ascii")
    for name, content in (
        ("elf-header.txt", header),
        ("elf-program-headers.txt", programs),
        ("elf-relocations.txt", relocations),
        ("elf-dynamic.txt", dynamic),
        ("elf-attributes.txt", attributes),
        ("elf-sections-symbols.txt", sections),
        ("elf-defined-symbols.txt", symbols),
        ("disassembly.txt", disassembly),
    ):
        (directory / name).write_text(content, encoding="utf-8")
    if stack_sizes_text is not None:
        (directory / "program.o.stack-sizes.txt").write_text(
            stack_sizes_text, encoding="utf-8"
        )
    for name, findings in object_relocations.items():
        (directory / f"{name}.relocations.txt").write_text(
            str(findings["text"]), encoding="utf-8"
        )
    for name, inventory_text in object_inventories.items():
        (directory / f"{name}.sections-symbols.txt").write_text(
            inventory_text, encoding="utf-8"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument(
        "--policy",
        choices=AUDIT_POLICIES,
        default=RELEASE_POLICY,
        help="release by default; all test-only policies require an explicit selection",
    )
    parser.add_argument(
        "--expected-fault",
        choices=sorted(COMPILER_MUTATION_FAULTS),
        help="bind a mutant audit to the requested closed fault ID",
    )
    parser.add_argument(
        "--expected-target-source",
        help="bind a mutant audit to the requested Lean source declaration",
    )
    parser.add_argument(
        "--clean-control-dir",
        type=Path,
        help="required clean-control artifact directory for a mutant sole-delta audit",
    )
    ns = parser.parse_args()
    root = repo_root()
    directory = (root / ns.artifact_dir).resolve() if not ns.artifact_dir.is_absolute() else ns.artifact_dir
    clean_control = None
    if ns.clean_control_dir is not None:
        clean_control = (
            (root / ns.clean_control_dir).resolve()
            if not ns.clean_control_dir.is_absolute()
            else ns.clean_control_dir.resolve()
        )
    try:
        report = audit(
            directory,
            root,
            policy=ns.policy,
            expected_fault=ns.expected_fault,
            expected_target_source=ns.expected_target_source,
            clean_control_directory=clean_control,
        )
    except Core0Error as error:
        print(f"CORE0 AUDIT FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
