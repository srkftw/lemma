#!/usr/bin/env python3
"""Fail-closed LLVM/object/ELF closure audit for the Core0 RV64 image."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

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

RELEASE_POLICY = "release"
TEST_COMPILER_CONTROL_POLICY = "test-compiler-control"
TEST_COMPILER_MUTANT_POLICY = "test-compiler-mutant"
TEST_FRONTEND_SUITE_POLICY = "test-frontend-suite"
TEST_CFG_SUITE_POLICY = "test-cfg-suite"
SCALAR_SUITE_POLICIES = frozenset({TEST_FRONTEND_SUITE_POLICY, TEST_CFG_SUITE_POLICY})
AUDIT_POLICIES = (
    RELEASE_POLICY,
    TEST_COMPILER_CONTROL_POLICY,
    TEST_COMPILER_MUTANT_POLICY,
    TEST_FRONTEND_SUITE_POLICY,
    TEST_CFG_SUITE_POLICY,
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
FORBIDDEN_IR_FLAGS = re.compile(r"\b(?:nsw|nuw|inbounds)\b")
ALLOWED_EXTERNALS = {"core0_io_fence"}
ALLOWED_RELOCATIONS = {
    "R_RISCV_CALL_PLT",
    "R_RISCV_PCREL_HI20",
    "R_RISCV_PCREL_LO12_I",
}
SCALAR_O2_JUMP_TABLE_RELOCATION = "R_RISCV_64"
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
MACHINE_IR_FUNCTIONS = {
    "core0_exit_failure",
    "core0_exit_success",
    "core0_uart_putc",
    "core0_uart_drain",
    "core0_put_hex64",
    "core0_main",
}
FINAL_ALLOC_SECTIONS = {".text", ".rodata", ".data", ".bss"}
LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
LLVM_IDENTIFIER = re.compile(r"[A-Za-z_.$][A-Za-z0-9_.$-]*")

SCALAR_TEST_ABI = "lemma-scalar-test-v1"
SCALAR_EXPORT_DRIVER = "examples/foundation/ScalarBuild.lean"
CFG_SCALAR_EXPORT_DRIVER = "examples/foundation/ScalarV2Build.lean"
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


def expected_program_command(optimization: str) -> list[str]:
    return [
        "llc",
        *LLC_ARGUMENTS,
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


def parse_definitions_and_calls(ir: str) -> tuple[set[str], set[str], set[str]]:
    definitions = set(re.findall(r"^define\s+.*?@([A-Za-z0-9_.$-]+)\(", ir, re.MULTILINE))
    declarations = set(re.findall(r"^declare\s+.*?@([A-Za-z0-9_.$-]+)\(", ir, re.MULTILINE))
    calls = set(re.findall(r"\bcall\s+[^@\n]*@([A-Za-z0-9_.$-]+)\(", ir))
    return definitions, declarations, calls


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
    expected_driver = (
        CFG_SCALAR_EXPORT_DRIVER
        if manifest.get("contract_version") == "core0-v0.2"
        else SCALAR_EXPORT_DRIVER
    )
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


def validate_scalar_test_abi(
    value: object, manifest: dict[str, object]
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("scalar-test-abi.json is not an object")
    contract_version = manifest.get("contract_version")
    if contract_version not in {"core0-v0.1", "core0-v0.2"}:
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


def _ir_definition_body(ir: str, symbol: str) -> str:
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
    assert isinstance(functions, list) and isinstance(roots, list)
    root_symbols = {
        str(root["llvm"]) for root in roots if isinstance(root, dict)
    }
    by_symbol: dict[str, dict[str, object]] = {}
    source_to_symbol: dict[str, str] = {}
    for function in functions:
        assert isinstance(function, dict)
        symbol = str(function["llvm"])
        source = str(function["source"])
        signature = function["signature"]
        assert isinstance(signature, dict)
        args = signature["args"]
        result = signature["result"]
        assert isinstance(args, list) and isinstance(result, str)
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
        assert isinstance(signature, dict)
        expected_args = signature["args"]
        expected_result = signature["result"]
        assert isinstance(expected_args, list) and isinstance(expected_result, str)
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

    for function in functions:
        assert isinstance(function, dict)
        symbol = str(function["llvm"])
        dependencies = function["dependencies"]
        assert isinstance(dependencies, list)
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
    assert isinstance(functions, list)
    attribute_groups = {
        int(identifier): body
        for identifier, body in re.findall(
            r"^attributes #(\d+) = \{([^\n]*)\}$", post_ir, re.MULTILINE
        )
    }
    for function in functions:
        assert isinstance(function, dict)
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
    if policy in SCALAR_SUITE_POLICIES:
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
    if policy in SCALAR_SUITE_POLICIES:
        scalar_export_configuration = validate_scalar_export_configuration(
            provenance_obj.get("export_configuration"), manifest, root
        )
    elif "export_configuration" in provenance_obj:
        raise Core0Error(
            f"{policy} provenance rejects scalar exporter configuration"
        )
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
    linked = provenance_obj.get("linked_inputs")
    if not isinstance(linked, list) or len(linked) != 2:
        raise Core0Error("provenance must name exactly the two linked objects")
    assert isinstance(optimization, str)
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
    }[policy]
    expected_input_details: dict[str, dict[str, object]] = {
        "startup.o": {
            "kind": "lean-structured-startup",
            "generation_command": EXPECTED_STARTUP_COMMAND,
            "source": "startup.S generated by Lemma.Machine.Primitives",
            "purpose": "M-mode entry, BSS clearing, a0/a1 boot-input preservation, and I/O fence",
        },
        "program.o": {
            "kind": program_input_details["kind"],
            "generation_command": expected_program_command(optimization),
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
    command_argv = [command.get("argv") for command in commands]
    if scalar_export_configuration is not None:
        validate_scalar_export_command_log(
            scalar_export_configuration, command_argv
        )
    for expected_command in expected_elaboration_commands:
        if expected_command not in command_argv:
            raise Core0Error(
                f"provenance command log omits Lean elaboration command: {expected_command!r}"
            )
    for expected_command in (
        expected_program_command(optimization),
        EXPECTED_STARTUP_COMMAND,
        EXPECTED_LINK_COMMAND,
    ):
        if expected_command not in command_argv:
            raise Core0Error(f"provenance command log omits exact command: {expected_command!r}")

    pre_ir = paths["program.ll"].read_text(encoding="utf-8")
    post_ir = paths["program.opt.ll"].read_text(encoding="utf-8")
    if mutation_manifest is not None:
        validate_compiler_mutation_ir(mutation_manifest, pre_ir)
        assert clean_control_directory is not None
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
    manifest_functions = manifest["functions"]
    assert isinstance(manifest_functions, list)
    manifest_user_symbols = {
        str(function["llvm"])
        for function in manifest_functions
        if isinstance(function, dict)
    }
    expected_pre_definitions = manifest_user_symbols | MACHINE_IR_FUNCTIONS
    scalar_abi_ir: dict[str, object] | None = None
    if policy in SCALAR_SUITE_POLICIES:
        scalar_abi_ir = validate_scalar_pre_abi(manifest, pre_ir)
        validate_scalar_post_noinline(manifest, post_ir)
        if policy == TEST_CFG_SUITE_POLICY:
            scalar_abi_ir["structured_semantics"] = validate_cfg_pre_semantics(
                manifest, pre_ir
            )
            source_identity = "Lemma Gate 3 structured scalar suite"
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
        if label == "post_optimization" and "inbounds" in inferred_flags:
            raise Core0Error("optimized IR unexpectedly contains an inbounds promise")
        definitions, declarations, calls = parse_definitions_and_calls(ir)
        if re.search(r"\b(?:invoke|callbr)\b|\basm\b", ir):
            raise Core0Error(f"{label} IR contains indirect control flow or inline assembly")
        for line in ir.splitlines():
            if re.search(r"\bcall\b", line) and re.search(
                r"\bcall\b[^@\n]*@[A-Za-z0-9_.$-]+\(", line
            ) is None:
                raise Core0Error(f"{label} IR contains an indirect or unparseable call: {line.strip()}")
        expected_externals = set(ALLOWED_EXTERNALS)
        if (
            policy in SCALAR_SUITE_POLICIES
            and label == "post_optimization"
            and optimization == "O2"
        ):
            expected_externals.add("llvm.umax.i64")
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
            if policy in SCALAR_SUITE_POLICIES:
                required_post_definitions = manifest_user_symbols | {"core0_main"}
            else:
                assert root_llvm is not None
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
                for flag in ("nsw", "nuw", "inbounds")
            },
        }

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
    if not {".text", ".rodata", ".bss"} <= alloc_sections:
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
    if re.search(r"\b(?:gp|f[0-9]+|v[0-9]+)\b", disassembly):
        raise Core0Error("disassembly uses gp, floating-point, or vector registers")
    if FORBIDDEN_SYMBOL.search(sections + disassembly):
        raise Core0Error("ELF symbol/disassembly inventory contains a forbidden runtime symbol")
    start_disassembly = disassembly.split("<_start>:", 1)
    if len(start_disassembly) != 2:
        raise Core0Error("disassembly lacks the generated _start body")
    start_body = start_disassembly[1].split("<core0_io_fence>:", 1)[0]
    startup_patterns = (
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
    if any(re.search(pattern, start_body) is None for pattern in startup_patterns):
        raise Core0Error("generated startup disassembly lacks a required entry/BSS/boot invariant")
    fence_body_parts = disassembly.split("<core0_io_fence>:", 1)
    if len(fence_body_parts) != 2:
        raise Core0Error("disassembly lacks core0_io_fence")
    fence_body = fence_body_parts[1].split("\n\n", 1)[0]
    if re.search(r"\bfence\b", fence_body) is None or re.search(r"\bret\b", fence_body) is None:
        raise Core0Error("core0_io_fence does not lower to a fence followed by return")
    scalar_abi_machine: dict[str, object] | None = None
    if policy == TEST_FRONTEND_SUITE_POLICY:
        assert isinstance(optimization, str)
        scalar_abi_machine = validate_scalar_abi_disassembly(
            manifest, disassembly, optimization
        )
    elif policy == TEST_CFG_SUITE_POLICY:
        scalar_abi_machine = validate_cfg_machine_disassembly(disassembly)

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
    if object_function_symbols["startup.o"] != {"_start", "core0_io_fence"}:
        raise Core0Error(
            "startup.o defined-function closure differs from the exact primitive allowlist: "
            + repr(sorted(object_function_symbols["startup.o"]))
        )
    final_function_symbols = defined_function_symbols(sections)
    expected_final_functions = post_definitions | {"_start", "core0_io_fence"}
    if final_function_symbols != expected_final_functions:
        raise Core0Error(
            "final ELF defined-function closure differs from its two input objects: "
            + repr(sorted(final_function_symbols))
        )

    object_undefined = {
        name: tool_text("llvm-nm", ["--undefined-only", str(directory / name)], root).splitlines()
        for name in expected_inputs
    }
    startup_allowed = {"core0_main", "__boot_hartid", "__bss_start", "__bss_end", "__stack_top"}
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
    if program_names != ALLOWED_EXTERNALS:
        raise Core0Error(
            "LLVM program object undefined-symbol closure differs from the exact allowlist: "
            + repr(sorted(program_names))
        )

    object_relocations: dict[str, dict[str, object]] = {}
    for name in expected_inputs:
        relocation_text = tool_text("llvm-readelf", ["-r", str(directory / name)], root)
        observed = relocation_types(relocation_text)
        allowed_relocations = set(ALLOWED_RELOCATIONS)
        expected_jump_table_relocations = 0
        if (
            policy in SCALAR_SUITE_POLICIES
            and name == "program.o"
            and optimization == "O2"
        ):
            allowed_relocations.add(SCALAR_O2_JUMP_TABLE_RELOCATION)
            manifest_roots = manifest["roots"]
            assert isinstance(manifest_roots, list)
            expected_jump_table_relocations = len(manifest_roots)
        forbidden_relocations = observed - allowed_relocations
        if forbidden_relocations:
            raise Core0Error(
                f"{name} contains an unexpected relocation type: {sorted(forbidden_relocations)}"
            )
        if "R_RISCV_RELAX" in relocation_text:
            raise Core0Error(f"{name} contains relaxation relocations despite the no-relax policy")
        if policy in SCALAR_SUITE_POLICIES and name == "program.o":
            current_section: str | None = None
            jump_table_rows: list[str] = []
            for line in relocation_text.splitlines():
                section_match = re.match(r"Relocation section '([^']+)'", line)
                if section_match is not None:
                    current_section = section_match.group(1)
                if SCALAR_O2_JUMP_TABLE_RELOCATION in line:
                    if current_section != ".rela.rodata" or re.search(
                        r"\bR_RISCV_64\b.*\s\.L0\s+\+ 0\s*$", line
                    ) is None:
                        raise Core0Error(
                            "scalar suite R_RISCV_64 relocation is not a local O2 root-dispatch jump-table entry"
                        )
                    jump_table_rows.append(line)
            if len(jump_table_rows) != expected_jump_table_relocations:
                raise Core0Error(
                    "scalar suite root-dispatch jump-table relocation count differs from "
                    f"the exact root closure: {len(jump_table_rows)} != "
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
    if mutation_manifest is not None:
        report["compiler_mutation"] = mutation_manifest
        assert clean_control_directory is not None and clean_control_report is not None
        report["clean_control"] = {
            "directory": str(clean_control_directory.relative_to(root)),
            "program_ll_sha256": sha256(clean_control_directory / "program.ll"),
            "audit_status": clean_control_report.get("status"),
            "artifact_category": clean_control_report.get("artifact_category"),
        }
    if scalar_test_abi is not None:
        assert scalar_abi_ir is not None and scalar_abi_machine is not None
        report["scalar_test_abi"] = scalar_test_abi
        report["scalar_abi_audit"] = {
            "pre_optimization": scalar_abi_ir,
            "machine_code": scalar_abi_machine,
        }
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
