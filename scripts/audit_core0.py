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

RELEASE_POLICY = "release"
TEST_COMPILER_CONTROL_POLICY = "test-compiler-control"
TEST_COMPILER_MUTANT_POLICY = "test-compiler-mutant"
AUDIT_POLICIES = (
    RELEASE_POLICY,
    TEST_COMPILER_CONTROL_POLICY,
    TEST_COMPILER_MUTANT_POLICY,
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
    """Audit one complete image under an explicit release or quarantined-test policy.

    The default remains the public release audit.  Test compiler controls and
    mutants must opt in by keyword so mutation-bearing artifacts cannot become
    release artifacts through directory contents alone.
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
    root_llvm = str(manifest["root_llvm"])
    ir_findings: dict[str, object] = {}
    for label, ir in (("pre_optimization", pre_ir), ("post_optimization", post_ir)):
        if f'source_filename = "{manifest["root"]}"' not in ir:
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
        if declarations != ALLOWED_EXTERNALS:
            raise Core0Error(
                f"{label} IR external declarations differ from the exact machine-primitive "
                f"allowlist: {sorted(declarations)}"
            )
        unresolved_calls = calls - definitions
        if unresolved_calls != ALLOWED_EXTERNALS:
            raise Core0Error(f"{label} IR has unresolved calls: {sorted(unresolved_calls)}")
        forbidden = sorted(name for name in definitions | calls if FORBIDDEN_SYMBOL.search(name))
        if forbidden:
            raise Core0Error(f"{label} IR contains forbidden runtime symbols: {forbidden}")
        if label == "pre_optimization" and definitions != expected_pre_definitions:
            raise Core0Error(
                "pre_optimization IR function closure differs from the manifest and "
                f"machine allowlist: {sorted(definitions)!r}"
            )
        if label == "post_optimization" and (
            not definitions <= expected_pre_definitions
            or not {root_llvm, "core0_main"} <= definitions
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
        forbidden_relocations = observed - ALLOWED_RELOCATIONS
        if forbidden_relocations:
            raise Core0Error(
                f"{name} contains an unexpected relocation type: {sorted(forbidden_relocations)}"
            )
        if "R_RISCV_RELAX" in relocation_text:
            raise Core0Error(f"{name} contains relaxation relocations despite the no-relax policy")
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
        help="release by default; test compiler policies are explicit and quarantined",
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
