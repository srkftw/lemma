#!/usr/bin/env python3
"""Independent fail-closed audit helpers for Core0 v0.4 checked memory.

This module deliberately does not import :mod:`audit_core0`.  Gate 5's source,
manifest, and LLVM checks can therefore be exercised in isolation, including by
the mutation tests which are expected to reject a compiler that emits a valid but
unsafe memory-access CFG.

The audit is intentionally narrower than a general LLVM analyser.  It accepts the
closed IR spelling emitted by Lemma's structured lowering and proves the relevant
facts about that spelling: exact region/effect metadata, the direct two-register
checked-result ABI, overflow-safe guard order, and absence of a path from any
denial edge to an ordinary-RAM load or store.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from core0_common import Core0Error


CONTRACT_VERSION = "core0-v0.4"
ARTIFACT_CATEGORY = "test-memory-suite"
TEST_ABI = "lemma-memory-test-v1"
CHECKED_RESULT_TAG = "checked-result-v1"

EFFECT_ORDER = (
    "checked-access",
    "fixed-ram-read",
    "fixed-ram-write",
)

CHECKED_RESULT_CONTRACT = {
    "logical_status": "u8",
    "logical_value": "u64",
    "llvm": "{ i64, i64 }",
    "rv64": "a0=status-zero-extended,a1=value",
    "status_high_bits_zero": True,
}

GUARD_ORDER = (
    "lookup",
    "class",
    "permission",
    "width",
    "bounds",
    "alignment",
)

# This catalog is copied from the reviewed Core0 v0.4 contract, not learned from
# the artifact being audited.  In particular, device IDs remain visible so the
# checker can prove they are denied before pointer construction.
REGIONS: tuple[dict[str, object], ...] = (
    {
        "id": 0x01,
        "name": "scratch",
        "base": 0x80801000,
        "length": 0x1000,
        "alignment": 8,
        "widths": [1, 4, 8],
        "read": True,
        "write": True,
        "kind": "ordinary",
        "purpose": "ordinary checked scratch RAM",
        "interval_valid": True,
    },
    {
        "id": 0x02,
        "name": "input-records",
        "base": 0x81000000,
        "length": 0x1000,
        "alignment": 8,
        "widths": [1, 4, 8],
        "read": True,
        "write": False,
        "kind": "ordinary",
        "purpose": "host-provided immutable input records",
        "interval_valid": True,
    },
    {
        "id": 0x03,
        "name": "output",
        "base": 0x80803000,
        "length": 0x1000,
        "alignment": 8,
        "widths": [1, 4, 8],
        "read": True,
        "write": True,
        "kind": "ordinary",
        "purpose": "checked output buffer",
        "interval_valid": True,
    },
    {
        "id": 0x04,
        "name": "events",
        "base": 0x80805000,
        "length": 0x1000,
        "alignment": 8,
        "widths": [4, 8],
        "read": True,
        "write": True,
        "kind": "ordinary",
        "purpose": "fixed-capacity event storage",
        "interval_valid": True,
    },
    {
        "id": 0x70,
        "name": "image",
        "base": 0x80000000,
        "length": 0x007F0000,
        "alignment": 8,
        "widths": [],
        "read": False,
        "write": False,
        "kind": "reserved",
        "purpose": "loaded image envelope; denied to the general RAM API",
        "interval_valid": True,
    },
    {
        "id": 0x71,
        "name": "stack",
        "base": 0x807F0000,
        "length": 0x00010000,
        "alignment": 8,
        "widths": [],
        "read": False,
        "write": False,
        "kind": "reserved",
        "purpose": "machine stack; denied to the general RAM API",
        "interval_valid": True,
    },
    {
        "id": 0x80,
        "name": "uart16550",
        "base": 0x10000000,
        "length": 0x100,
        "alignment": 8,
        "widths": [],
        "read": False,
        "write": False,
        "kind": "device",
        "purpose": "device MMIO; excluded from ordinary RAM operations",
        "interval_valid": True,
    },
    {
        "id": 0x81,
        "name": "sifive-test",
        "base": 0x00100000,
        "length": 0x1000,
        "alignment": 8,
        "widths": [],
        "read": False,
        "write": False,
        "kind": "device",
        "purpose": "VM termination MMIO; excluded from ordinary RAM operations",
        "interval_valid": True,
    },
)

STATUSES: tuple[dict[str, object], ...] = (
    {"code": 0, "name": "ok"},
    {"code": 1, "name": "unknown-region"},
    {"code": 2, "name": "reserved-region"},
    {"code": 3, "name": "device-region"},
    {"code": 4, "name": "read-denied"},
    {"code": 5, "name": "write-denied"},
    {"code": 6, "name": "width-denied"},
    {"code": 7, "name": "out-of-bounds"},
    {"code": 8, "name": "misaligned"},
    {"code": 9, "name": "budget-exceeded"},
)

MEMORY_CONTRACT = {
    "byte_order": "little-endian",
    "guard_order": list(GUARD_ORDER),
    # Volatility is an observability decision for modeled ordinary-RAM events.
    # It does not classify these regions as MMIO and implies no hardware fence.
    "successful_access_volatile": True,
    "regions": [copy.deepcopy(region) for region in REGIONS],
    "statuses": [copy.deepcopy(status) for status in STATUSES],
}

MEMORY_OPS: dict[str, dict[str, object]] = {}
for _access, _effect, _constructor in (
    ("read", "fixed-ram-read", "load"),
    ("write", "fixed-ram-write", "store"),
):
    for _bits in (8, 32, 64):
        _stable_id = f"ram.{_access}{_bits}"
        MEMORY_OPS[_stable_id] = {
            "stable_id": _stable_id,
            "source_identity": f"Lemma.Core0.Memory.Action.{_constructor}{_bits}",
            "access": _access,
            "width": _bits,
            "range": False,
            "effect": _effect,
        }
for _access, _effect, _constructor in (
    ("read", "checked-access", "checkReadRange"),
    ("write", "checked-access", "checkWriteRange"),
):
    _stable_id = f"ram.check-{_access}-range"
    MEMORY_OPS[_stable_id] = {
        "stable_id": _stable_id,
        "source_identity": f"Lemma.Core0.Memory.Action.{_constructor}",
        "access": _access,
        "width": None,
        "range": True,
        "effect": _effect,
    }

ACTION_FOLD_STABLE_ID = "action.u64.bounded-fold"
ACTION_FOLD_IDENTITY = "Lemma.Core0.Memory.Action.boundedFoldU64"

MEMORY_NAMESPACE = "Lemma.Examples.Foundation.Memory"

# Gate 5 is a closed conformance suite rather than an open plugin surface.  Pin
# its public roots here so dropping a case (or substituting an easier one) cannot
# be hidden by a self-consistent manifest.  Helper Action functions are pinned
# separately below; their normalized bodies are still checked independently.
CLOSED_ROOTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("load8Value", ("u8", "u64")),
    ("load32Value", ("u8", "u64")),
    ("load64Value", ("u8", "u64")),
    ("store8Status", ("u8", "u64", "u8")),
    ("store32Status", ("u8", "u64", "u32")),
    ("store64Status", ("u8", "u64", "u64")),
    ("roundTrip8", ("u8", "u64", "u8")),
    ("roundTrip32", ("u8", "u64", "u32")),
    ("roundTrip64", ("u8", "u64", "u64")),
    ("eventWidth", ("bool", "u64", "u64")),
    ("overlapLow32", ("u8", "u64", "u64")),
    ("overlapHigh32", ("u8", "u64", "u64")),
    ("overlapByte", ("u8", "u64", "u32")),
    ("readRange", ("u8", "u64", "u64")),
    ("writeRange", ("u8", "u64", "u64")),
    ("overflowBounds", ("bool", "u8", "u64", "u64")),
    ("alignment", ("bool", "u8", "u64")),
    ("reservedDenied", ("bool", "u8", "u64")),
    ("deviceDenied", ("bool", "u8", "u64")),
    ("unknownDenied", ("u8", "u64")),
    ("helperCopyNonOverlap", ("u8", "u64", "u8", "u64")),
    ("branchWrite", ("bool", "u64", "u8")),
    ("foldWrite", ("u32", "u64", "u8")),
    ("bufferFill", ("u8", "u64", "u32", "u8")),
    ("byteChecksum", ("u8", "u64", "u32")),
    ("overlapCopy", ("u8", "u64", "u8", "u64", "u32")),
)

FOLD_CALLBACK_SIGNATURE = (
    "u32",
    "u32",
    "u64",
    "u64",
    "u64",
    "u64",
    "u64",
)

CLOSED_ACTION_HELPERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Support.copyStep", FOLD_CALLBACK_SIGNATURE),
    ("Support.copyExactly16", ("u8", "u64", "u8", "u64")),
    ("Support.incrementingWriteStep", FOLD_CALLBACK_SIGNATURE),
    ("Support.fillStep", FOLD_CALLBACK_SIGNATURE),
    ("Support.checksumStep", FOLD_CALLBACK_SIGNATURE),
)

CLOSED_ACTION_ITERATIONS: tuple[tuple[int, str], ...] = (
    (16, f"{MEMORY_NAMESPACE}.Support.copyStep"),
    (16, f"{MEMORY_NAMESPACE}.Support.incrementingWriteStep"),
    (256, f"{MEMORY_NAMESPACE}.Support.fillStep"),
    (256, f"{MEMORY_NAMESPACE}.Support.checksumStep"),
    (256, f"{MEMORY_NAMESPACE}.Support.copyStep"),
)


def _pure_primitive(
    stable_id: str,
    lean_identity: str,
    arguments: Sequence[str],
    result: str,
) -> dict[str, object]:
    return {
        "stable_id": stable_id,
        "lean_identities": [lean_identity],
        "signature": {"args": list(arguments), "result": result},
        "effect": "pure",
    }


CLOSED_USED_PRIMITIVES: tuple[dict[str, object], ...] = (
    _pure_primitive("u8.eq", "Eq", ("u8", "u8"), "bool"),
    _pure_primitive("bool.eq", "Eq", ("bool", "bool"), "bool"),
    _pure_primitive("u64.to-u8.trunc", "UInt64.toUInt8", ("u64",), "u8"),
    _pure_primitive("u64.to-u32.trunc", "UInt64.toUInt32", ("u64",), "u32"),
    _pure_primitive("u64.add", "UInt64.add", ("u64", "u64"), "u64"),
    _pure_primitive("u64.shl", "UInt64.shiftLeft", ("u64", "u64"), "u64"),
    _pure_primitive("u64.or", "UInt64.lor", ("u64", "u64"), "u64"),
    _pure_primitive("u8.to-u64.zext", "UInt8.toUInt64", ("u8",), "u64"),
    _pure_primitive("u64.ult", "UInt64.lt", ("u64", "u64"), "bool"),
    _pure_primitive("u32.to-u64.zext", "UInt32.toUInt64", ("u32",), "u64"),
    _pure_primitive("u32.sub", "UInt32.sub", ("u32", "u32"), "u32"),
    _pure_primitive("u32.to-u8.trunc", "UInt32.toUInt8", ("u32",), "u8"),
    _pure_primitive("u8.add", "UInt8.add", ("u8", "u8"), "u8"),
)

PRIMITIVE_SOURCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("u8.eq", re.compile(r"\(cmp eq u8\b")),
    ("bool.eq", re.compile(r"\(cmp eq bool\b")),
    ("u64.to-u8.trunc", re.compile(r"\(cast trunc u64 u8\b")),
    ("u64.to-u32.trunc", re.compile(r"\(cast trunc u64 u32\b")),
    ("u64.add", re.compile(r"\(bin add u64\b")),
    ("u64.shl", re.compile(r"\(bin shl u64\b")),
    ("u64.or", re.compile(r"\(bin or u64\b")),
    ("u8.to-u64.zext", re.compile(r"\(cast zext u8 u64\b")),
    ("u64.ult", re.compile(r"\(cmp ult u64\b")),
    ("u32.to-u64.zext", re.compile(r"\(cast zext u32 u64\b")),
    ("u32.sub", re.compile(r"\(bin sub u32\b")),
    ("u32.to-u8.trunc", re.compile(r"\(cast trunc u32 u8\b")),
    ("u8.add", re.compile(r"\(bin add u8\b")),
)

CLOSED_MACHINE_PRIMITIVES: tuple[dict[str, str], ...] = (
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
        "identity": "memory-test-dispatch",
        "effect": "fixed-input-read/canary-observation",
        "implementation": "Lemma.Machine.MemoryHarness.main",
    },
    {
        "identity": "sifive-test",
        "effect": "vm-termination-mmio",
        "implementation": "Lemma.Machine.Harness.exitSuccess/exitFailure",
    },
)
SUITE_FIELDS = {
    "schema_version",
    "artifact_category",
    "contract_version",
    "test_abi",
    "suite_id",
    "source_seed",
    "runtime_seed",
    "checked_result",
    "memory_contract",
    "roots",
    "scalar_functions",
    "action_functions",
    "used_primitives",
    "used_memory_ops",
    "action_iterations",
    "machine_primitives",
}

ACTION_FUNCTION_FIELDS = {
    "source",
    "llvm",
    "signature",
    "scalar_dependencies",
    "action_dependencies",
    "direct_effects",
    "transitive_effects",
    "body",
    "noinline",
}

ROOT_FIELDS = {"root_id", "source", "llvm", "signature"}
SCALAR_TYPES = {"bool", "u8", "u32", "u64"}
IDENTIFIER = re.compile(r"[A-Za-z_.$][A-Za-z0-9_.$-]*")
LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
FORBIDDEN_IR_FLAGS = re.compile(r"\b(?:nuw|nsw|inbounds|disjoint)\b")


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from the schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _canonical_effects(values: Iterable[str]) -> list[str]:
    value_set = set(values)
    unknown = value_set - set(EFFECT_ORDER)
    if unknown:
        raise Core0Error(f"unknown memory effect names: {sorted(unknown)!r}")
    if ("fixed-ram-read" in value_set or "fixed-ram-write" in value_set) and (
        "checked-access" not in value_set
    ):
        raise Core0Error("RAM read/write effect omits checked-access")
    return [effect for effect in EFFECT_ORDER if effect in value_set]


def _validate_effect_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise Core0Error(f"{context} is not an effect-name array")
    canonical = _canonical_effects(value)
    if value != canonical:
        raise Core0Error(f"{context} is not in canonical effect order")
    return canonical


def _validate_signature(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} signature is not an object")
    _exact_keys(value, {"args"}, f"{context} signature")
    args = value.get("args")
    if (
        not isinstance(args, list)
        or any(not isinstance(arg, str) or arg not in SCALAR_TYPES for arg in args)
        or len(args) > 16
    ):
        raise Core0Error(f"{context} has an invalid scalar argument signature")
    return value


def _validate_hex_word(value: object, context: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{16}", value) is None:
        raise Core0Error(f"{context} is not a canonical 16-digit lowercase hex word")


def _validate_region_catalog(value: object) -> None:
    if value != [copy.deepcopy(region) for region in REGIONS]:
        raise Core0Error("memory region catalog differs from the exact core0-v0.4 contract")
    for region in REGIONS:
        base = int(region["base"])
        length = int(region["length"])
        if length <= 0 or base < 0 or base >= 2**64 or length > 2**64 - base:
            raise Core0Error(f"reviewed region {region['name']} has an invalid interval")
        if base % int(region["alignment"]) != 0:
            raise Core0Error(f"reviewed region {region['name']} violates its alignment")


def _body_direct_effects(body: str) -> list[str]:
    effects: set[str] = set()
    if re.search(r"\(action\.(?:load(?:8|32|64)|store(?:8|32|64)|check-(?:read|write)-range)\b", body):
        effects.add("checked-access")
    if re.search(r"\(action\.load(?:8|32|64)\b", body):
        effects.add("fixed-ram-read")
    if re.search(r"\(action\.store(?:8|32|64)\b", body):
        effects.add("fixed-ram-write")
    return _canonical_effects(effects)


def _body_action_dependencies(body: str) -> list[str]:
    result: list[str] = []
    for pattern in (
        r"\(action\.call\s+([A-Za-z_][A-Za-z0-9_.]*)\b",
        r"\(action\.bounded-fold-u64\s+budget=[0-9]+\s+callback=([A-Za-z_][A-Za-z0-9_.]*)\b",
    ):
        for dependency in re.findall(pattern, body):
            if dependency not in result:
                result.append(dependency)
    return result


def _body_action_call_sites(body: str) -> list[str]:
    """Return every direct Action call/fold callback source site, with multiplicity."""
    result: list[str] = []
    pattern = re.compile(
        r"\(action\.call\s+([A-Za-z_][A-Za-z0-9_.]*)\b|"
        r"\(action\.bounded-fold-u64\s+budget=[0-9]+\s+"
        r"callback=([A-Za-z_][A-Za-z0-9_.]*)\b"
    )
    for match in pattern.finditer(body):
        result.append(match.group(1) or match.group(2))
    return result


def _body_action_iterations(body: str) -> list[tuple[int, str]]:
    return [
        (int(budget), callback)
        for budget, callback in re.findall(
            r"\(action\.bounded-fold-u64\s+budget=([0-9]+)\s+"
            r"callback=([A-Za-z_][A-Za-z0-9_.]*)\b",
            body,
        )
    ]


def _expected_action_iteration(budget: int, callback: str) -> dict[str, object]:
    return {
        "stable_id": ACTION_FOLD_STABLE_ID,
        "source_identity": ACTION_FOLD_IDENTITY,
        "static_budget": budget,
        "callback": callback,
        "maximum_budget": 256,
        "counter": {"type": "u32", "order": "ascending-zero-based"},
        "accumulator": "u64",
        "contexts": 4,
        "outcome": CHECKED_RESULT_TAG,
        "exhaustion": {"status": 9, "value": "initial", "callbacks": 0},
    }


def _body_scalar_dependencies(body: str) -> list[str]:
    result: list[str] = []
    for dependency in re.findall(
        r"(?<!action\.)\(call\s+([A-Za-z_][A-Za-z0-9_.]*)\s+", body
    ):
        if dependency not in result:
            result.append(dependency)
    return result


def _body_memory_op_ids(body: str) -> set[str]:
    result: set[str] = set()
    for access, bits in re.findall(r"\(action\.(load|store)(8|32|64)\b", body):
        result.add(f"ram.{'read' if access == 'load' else 'write'}{bits}")
    for access in re.findall(r"\(action\.check-(read|write)-range\b", body):
        result.add(f"ram.check-{access}-range")
    return result


def validate_effect_closure(manifest: Mapping[str, object]) -> dict[str, object]:
    """Validate normalized source sites and the exact transitive Action effects."""
    scalar_functions = manifest.get("scalar_functions")
    action_functions = manifest.get("action_functions")
    roots = manifest.get("roots")
    if not isinstance(scalar_functions, list):
        raise Core0Error("memory suite scalar_functions is not an array")
    if not isinstance(action_functions, list) or not action_functions:
        raise Core0Error("memory suite action_functions is empty or malformed")
    if not isinstance(roots, list) or not roots:
        raise Core0Error("memory suite roots is empty or malformed")

    scalar_sources: set[str] = set()
    for index, function in enumerate(scalar_functions):
        if not isinstance(function, dict):
            raise Core0Error(f"scalar function #{index} is not an object")
        source = function.get("source")
        body = function.get("body")
        if not isinstance(source, str) or LEAN_IDENTIFIER.fullmatch(source) is None:
            raise Core0Error(f"scalar function #{index} has an invalid source identity")
        if source in scalar_sources:
            raise Core0Error(f"duplicate scalar function source {source}")
        scalar_sources.add(source)
        if not isinstance(body, str) or "(action." in body:
            raise Core0Error(
                f"scalar function {source} contains an Action/effect source site"
            )

    by_source: dict[str, dict[str, object]] = {}
    by_symbol: dict[str, dict[str, object]] = {}
    function_order: dict[str, int] = {}
    observed_ops: set[str] = set()
    observed_iterations: list[dict[str, object]] = []
    for index, function in enumerate(action_functions):
        if not isinstance(function, dict):
            raise Core0Error(f"Action function #{index} is not an object")
        _exact_keys(function, ACTION_FUNCTION_FIELDS, f"Action function #{index}")
        source, symbol, body = (
            function.get("source"),
            function.get("llvm"),
            function.get("body"),
        )
        if not isinstance(source, str) or LEAN_IDENTIFIER.fullmatch(source) is None:
            raise Core0Error(f"Action function #{index} has an invalid source identity")
        if not isinstance(symbol, str) or IDENTIFIER.fullmatch(symbol) is None:
            raise Core0Error(f"Action function {source} has an invalid LLVM symbol")
        if source in by_source or symbol in by_symbol:
            raise Core0Error("memory suite repeats an Action source identity or LLVM symbol")
        if not isinstance(body, str) or not body.startswith("(action.") or "\n" in body:
            raise Core0Error(f"Action function {source} lacks one normalized Action body")
        _validate_signature(function.get("signature"), f"Action function {source}")
        if function.get("noinline") is not True:
            raise Core0Error(f"Action function {source} is not pinned noinline")
        scalar_dependencies = function.get("scalar_dependencies")
        action_dependencies = function.get("action_dependencies")
        if not isinstance(scalar_dependencies, list) or any(
            not isinstance(item, str) for item in scalar_dependencies
        ):
            raise Core0Error(f"Action function {source} scalar dependencies are malformed")
        if not isinstance(action_dependencies, list) or any(
            not isinstance(item, str) for item in action_dependencies
        ):
            raise Core0Error(f"Action function {source} Action dependencies are malformed")
        if scalar_dependencies != _body_scalar_dependencies(body):
            raise Core0Error(
                f"Action function {source} scalar dependency/source-site closure differs"
            )
        if action_dependencies != _body_action_dependencies(body):
            raise Core0Error(
                f"Action function {source} Action dependency/source-site closure differs"
            )
        direct = _validate_effect_list(
            function.get("direct_effects"), f"Action function {source} direct effects"
        )
        if direct != _body_direct_effects(body):
            raise Core0Error(f"Action function {source} direct effects differ from its source sites")
        _validate_effect_list(
            function.get("transitive_effects"),
            f"Action function {source} transitive effects",
        )
        observed_ops.update(_body_memory_op_ids(body))
        for budget, callback in _body_action_iterations(body):
            if not 0 <= budget <= 256:
                raise Core0Error(
                    f"Action function {source} has an out-of-contract fold budget {budget}"
                )
            observed_iterations.append(_expected_action_iteration(budget, callback))
        by_source[source] = function
        by_symbol[symbol] = function
        function_order[source] = index

    for source, function in by_source.items():
        scalar_dependencies = function["scalar_dependencies"]
        action_dependencies = function["action_dependencies"]
        assert isinstance(scalar_dependencies, list)
        assert isinstance(action_dependencies, list)
        unknown_scalars = set(scalar_dependencies) - scalar_sources
        if unknown_scalars:
            raise Core0Error(
                f"Action function {source} has unknown scalar dependencies: "
                f"{sorted(unknown_scalars)!r}"
            )
        for dependency in action_dependencies:
            if dependency not in by_source:
                raise Core0Error(
                    f"Action function {source} has unknown Action dependency {dependency}"
                )
            if function_order[dependency] >= function_order[source]:
                raise Core0Error(
                    f"Action dependency graph is not dependency-first and acyclic: "
                    f"{source} -> {dependency}"
                )

    computed: dict[str, list[str]] = {}
    for function in action_functions:
        assert isinstance(function, dict)
        source = str(function["source"])
        closure = set(function["direct_effects"])
        dependencies = function["action_dependencies"]
        assert isinstance(dependencies, list)
        for dependency in dependencies:
            closure.update(computed[str(dependency)])
        expected = _canonical_effects(closure)
        if function["transitive_effects"] != expected:
            raise Core0Error(
                f"Action function {source} transitive effect closure differs: "
                f"{function['transitive_effects']!r} != {expected!r}"
            )
        computed[source] = expected

    seen_root_ids: set[int] = set()
    seen_root_sources: set[str] = set()
    for index, root in enumerate(roots):
        if not isinstance(root, dict):
            raise Core0Error(f"memory root #{index} is not an object")
        _exact_keys(root, ROOT_FIELDS, f"memory root #{index}")
        root_id = root.get("root_id")
        source = root.get("source")
        if type(root_id) is not int or root_id != index + 1 or root_id in seen_root_ids:
            raise Core0Error(f"memory root #{index} has a noncanonical root ID")
        if not isinstance(source, str) or source not in by_source or source in seen_root_sources:
            raise Core0Error(f"memory root #{index} is not an exact Action function root")
        function = by_source[source]
        if root.get("llvm") != function["llvm"] or root.get("signature") != function["signature"]:
            raise Core0Error(f"memory root {source} differs from its Action function")
        seen_root_ids.add(root_id)
        seen_root_sources.add(source)

    used_ops = manifest.get("used_memory_ops")
    if not isinstance(used_ops, list):
        raise Core0Error("memory suite used_memory_ops is not an array")
    expected_ops = [copy.deepcopy(MEMORY_OPS[stable_id]) for stable_id in sorted(observed_ops)]
    if used_ops != expected_ops:
        raise Core0Error("memory operation manifest differs from normalized source sites")

    action_iterations = manifest.get("action_iterations")
    if action_iterations != observed_iterations:
        raise Core0Error("Action iteration manifest differs from normalized source sites")

    return {
        "action_function_count": len(action_functions),
        "root_count": len(roots),
        "memory_operations": sorted(observed_ops),
        "action_iteration_count": len(observed_iterations),
        "effect_closure": computed,
    }


def _validate_closed_gate5_suite(manifest: Mapping[str, object]) -> None:
    """Pin the real Gate 5 suite independently of its self-description."""
    roots = manifest.get("roots")
    scalar_functions = manifest.get("scalar_functions")
    action_functions = manifest.get("action_functions")
    used_memory_ops = manifest.get("used_memory_ops")
    action_iterations = manifest.get("action_iterations")
    used_primitives = manifest.get("used_primitives")
    machine_primitives = manifest.get("machine_primitives")
    assert isinstance(roots, list)
    assert isinstance(scalar_functions, list)
    assert isinstance(action_functions, list)
    assert isinstance(used_memory_ops, list)
    assert isinstance(action_iterations, list)
    assert isinstance(used_primitives, list)
    assert isinstance(machine_primitives, list)

    expected_roots = [
        {
            "root_id": index,
            "source": f"{MEMORY_NAMESPACE}.{leaf}",
            "signature": {"args": list(arguments)},
        }
        for index, (leaf, arguments) in enumerate(CLOSED_ROOTS, start=1)
    ]
    observed_roots = [
        {
            "root_id": root.get("root_id"),
            "source": root.get("source"),
            "signature": root.get("signature"),
        }
        for root in roots
        if isinstance(root, dict)
    ]
    if observed_roots != expected_roots:
        raise Core0Error("memory suite differs from the exact 26-root Gate 5 catalog")

    if scalar_functions:
        raise Core0Error("closed Gate 5 memory suite unexpectedly contains scalar functions")
    if len(action_functions) != 31:
        raise Core0Error(
            f"closed Gate 5 memory suite has {len(action_functions)} Action functions, "
            "expected 31"
        )
    expected_action_signatures = {
        f"{MEMORY_NAMESPACE}.{leaf}": {"args": list(arguments)}
        for leaf, arguments in (*CLOSED_ROOTS, *CLOSED_ACTION_HELPERS)
    }
    observed_action_signatures = {
        str(function["source"]): function["signature"]
        for function in action_functions
        if isinstance(function, dict)
    }
    if observed_action_signatures != expected_action_signatures:
        raise Core0Error("memory suite differs from the exact 31-function Action catalog")

    if len(used_memory_ops) != 8 or {
        operation.get("stable_id")
        for operation in used_memory_ops
        if isinstance(operation, dict)
    } != set(MEMORY_OPS):
        raise Core0Error("closed Gate 5 memory suite does not exercise all 8 memory operations")

    expected_iterations = [
        _expected_action_iteration(budget, callback)
        for budget, callback in CLOSED_ACTION_ITERATIONS
    ]
    if action_iterations != expected_iterations:
        raise Core0Error("memory suite differs from the exact 5-site Action iteration catalog")

    if used_primitives != [copy.deepcopy(row) for row in CLOSED_USED_PRIMITIVES]:
        raise Core0Error("closed Gate 5 scalar primitive catalog differs from its allowlist")
    normalized_bodies = "\n".join(
        str(function["body"])
        for function in action_functions
        if isinstance(function, dict)
    )
    observed_primitive_sites = {
        stable_id
        for stable_id, pattern in PRIMITIVE_SOURCE_PATTERNS
        if pattern.search(normalized_bodies)
    }
    if observed_primitive_sites != {
        str(row["stable_id"]) for row in CLOSED_USED_PRIMITIVES
    }:
        raise Core0Error(
            "closed Gate 5 scalar primitive manifest differs from normalized source sites"
        )
    if machine_primitives != [copy.deepcopy(row) for row in CLOSED_MACHINE_PRIMITIVES]:
        raise Core0Error("closed Gate 5 machine primitive catalog differs from its allowlist")


def validate_memory_suite_manifest(
    value: object, *, require_closed_suite: bool = True
) -> dict[str, object]:
    """Validate the closed v0.4 envelope, region/status catalog, and effects."""
    if not isinstance(value, dict):
        raise Core0Error("memory-suite manifest is not an object")
    _exact_keys(value, SUITE_FIELDS, "memory-suite manifest")
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("memory-suite manifest has an unsupported schema")
    if value.get("artifact_category") != ARTIFACT_CATEGORY:
        raise Core0Error("memory-suite manifest has the wrong artifact category")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise Core0Error("memory-suite manifest has an unsupported Core0 contract")
    if value.get("test_abi") != TEST_ABI:
        raise Core0Error("memory-suite manifest has an unsupported test ABI")
    for field in ("suite_id", "source_seed", "runtime_seed"):
        _validate_hex_word(value.get(field), f"memory-suite {field}")
    if value.get("checked_result") != CHECKED_RESULT_CONTRACT:
        raise Core0Error("checked-result contract differs from the exact v0.4 ABI")
    memory_contract = value.get("memory_contract")
    if not isinstance(memory_contract, dict):
        raise Core0Error("memory_contract is not an object")
    _exact_keys(
        memory_contract,
        {"byte_order", "guard_order", "successful_access_volatile", "regions", "statuses"},
        "memory contract",
    )
    if memory_contract != MEMORY_CONTRACT:
        raise Core0Error("memory contract differs from the exact core0-v0.4 contract")
    _validate_region_catalog(memory_contract["regions"])
    if not isinstance(value.get("used_primitives"), list):
        raise Core0Error("memory-suite used_primitives is not an array")
    if not isinstance(value.get("action_iterations"), list):
        raise Core0Error("memory-suite action_iterations is not an array")
    if not isinstance(value.get("machine_primitives"), list):
        raise Core0Error("memory-suite machine_primitives is not an array")
    validate_effect_closure(value)
    if require_closed_suite:
        _validate_closed_gate5_suite(value)
    return value


@dataclass(frozen=True)
class IRFunction:
    name: str
    header: str
    body: str
    blocks: dict[str, list[str]]


@dataclass(frozen=True)
class Definition:
    block: str
    index: int
    line: str


@dataclass(frozen=True)
class AccessRecord:
    function: str
    block: str
    index: int
    stem: str
    access: str
    bits: int
    volatile: bool
    value_operand: str | None


@dataclass(frozen=True)
class SourceMemorySite:
    """One normalized Action memory operation, in lowering/site order.

    The exporter renders each scalar operand as one balanced parenthesized
    expression.  Keeping those expressions intact lets the LLVM audit bind the
    stable ``mem.<site>`` spelling back to direct source arguments and literals
    without pretending to be a second implementation of arbitrary Core0 scalar
    lowering.
    """

    index: int
    access: str
    bits: int | None
    region: str
    offset: str
    value: str | None = None
    length: str | None = None


def _parse_blocks(body: str, function: str) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        label = re.fullmatch(r"([A-Za-z_.$][A-Za-z0-9_.$-]*):", line)
        if label is not None:
            current = label.group(1)
            if current in blocks:
                raise Core0Error(f"LLVM function {function} repeats block %{current}")
            blocks[current] = []
            continue
        if current is None:
            raise Core0Error(f"LLVM function {function} has an instruction before a block label")
        blocks[current].append(line)
    if not blocks:
        raise Core0Error(f"LLVM function {function} has no parseable blocks")
    return blocks


def parse_ir_functions(ir: str) -> dict[str, IRFunction]:
    """Parse the closed one-line function headers rendered by Lemma's emitter."""
    pattern = re.compile(
        r"^(?P<header>define\s+[^\n]+@(?P<name>[A-Za-z_.$][A-Za-z0-9_.$-]*)"
        r"\([^\n]*\)[^\n]*\{)\n(?P<body>.*?)^\}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    functions: dict[str, IRFunction] = {}
    for match in pattern.finditer(ir):
        name = match.group("name")
        if name in functions:
            raise Core0Error(f"LLVM IR repeats function definition @{name}")
        body = match.group("body")
        functions[name] = IRFunction(
            name=name,
            header=match.group("header"),
            body=body,
            blocks=_parse_blocks(body, name),
        )
    return functions


def _successors(function: IRFunction) -> dict[str, tuple[str, ...]]:
    successors: dict[str, tuple[str, ...]] = {}
    for label, lines in function.blocks.items():
        if not lines:
            raise Core0Error(f"LLVM function {function.name} has empty block %{label}")
        terminator = lines[-1]
        conditional = re.fullmatch(
            r"br i1 (%[A-Za-z_.$][A-Za-z0-9_.$-]*|true|false), label %"
            r"([A-Za-z_.$][A-Za-z0-9_.$-]*), label %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
            terminator,
        )
        jump = re.fullmatch(r"br label %([A-Za-z_.$][A-Za-z0-9_.$-]*)", terminator)
        if conditional is not None:
            successors[label] = (conditional.group(2), conditional.group(3))
        elif jump is not None:
            successors[label] = (jump.group(1),)
        elif terminator.startswith("ret ") or terminator == "unreachable":
            successors[label] = ()
        else:
            raise Core0Error(
                f"LLVM function {function.name} block %{label} has an unsupported terminator"
            )
    unknown = {
        target
        for targets in successors.values()
        for target in targets
        if target not in successors
    }
    if unknown:
        raise Core0Error(
            f"LLVM function {function.name} branches to unknown blocks {sorted(unknown)!r}"
        )
    return successors


def _predecessors(successors: Mapping[str, Sequence[str]]) -> dict[str, set[str]]:
    result = {block: set() for block in successors}
    for block, targets in successors.items():
        for target in targets:
            result[target].add(block)
    return result


def _reachable(successors: Mapping[str, Sequence[str]], start: str, target: str) -> bool:
    pending = [start]
    visited: set[str] = set()
    while pending:
        block = pending.pop()
        if block == target:
            return True
        if block in visited:
            continue
        visited.add(block)
        pending.extend(successors.get(block, ()))
    return False


def _reachable_blocks(successors: Mapping[str, Sequence[str]], start: str) -> set[str]:
    pending = [start]
    visited: set[str] = set()
    while pending:
        block = pending.pop()
        if block in visited:
            continue
        visited.add(block)
        pending.extend(successors.get(block, ()))
    return visited


def _dominators(function: IRFunction) -> dict[str, set[str]]:
    successors = _successors(function)
    blocks = list(function.blocks)
    entry = blocks[0]
    predecessors = _predecessors(successors)
    reachable = _reachable_blocks(successors, entry)
    dominators: dict[str, set[str]] = {}
    for block in blocks:
        dominators[block] = {block} if block == entry else set(reachable)
    changed = True
    while changed:
        changed = False
        for block in blocks[1:]:
            if block not in reachable:
                continue
            incoming = [dominators[pred] for pred in predecessors[block] if pred in reachable]
            new = {block} | (set.intersection(*incoming) if incoming else set())
            if new != dominators[block]:
                dominators[block] = new
                changed = True
    return dominators


def _definitions(function: IRFunction) -> dict[str, Definition]:
    result: dict[str, Definition] = {}
    for block, lines in function.blocks.items():
        for index, line in enumerate(lines):
            match = re.match(r"%(?P<name>[A-Za-z_.$][A-Za-z0-9_.$-]*)\s*=", line)
            if match is None:
                continue
            name = match.group("name")
            if name in result:
                raise Core0Error(f"LLVM function {function.name} repeats SSA definition %{name}")
            result[name] = Definition(block, index, line)
    return result


def _parse_int(text: str) -> int | None:
    text = text.strip()
    try:
        return int(text, 0)
    except ValueError:
        return None


def _definition_operand(definitions: Mapping[str, Definition], operand: str) -> Definition | None:
    operand = operand.strip()
    if not operand.startswith("%"):
        return None
    return definitions.get(operand[1:])


def _dominates_instruction(
    definition: Definition,
    target_block: str,
    target_index: int,
    dominators: Mapping[str, set[str]],
) -> bool:
    if definition.block == target_block:
        return definition.index < target_index
    return definition.block in dominators[target_block]


def _constant_i64_values(
    operand: str,
    definitions: Mapping[str, Definition],
    *,
    seen: frozenset[str] = frozenset(),
) -> set[int] | None:
    literal = _parse_int(operand)
    if literal is not None:
        return {literal & ((1 << 64) - 1)}
    if not operand.startswith("%") or operand[1:] in seen:
        return None
    name = operand[1:]
    definition = definitions.get(name)
    if definition is None:
        return None
    next_seen = seen | {name}
    zext = re.fullmatch(rf"%{re.escape(name)} = zext i8 (.+) to i64", definition.line)
    if zext is not None:
        values = _constant_i64_values(zext.group(1), definitions, seen=next_seen)
        return None if values is None else {value & 0xFF for value in values}
    select = re.fullmatch(
        rf"%{re.escape(name)} = select i1 [^,]+, i64 ([^,]+), i64 (.+)",
        definition.line,
    )
    if select is not None:
        left = _constant_i64_values(select.group(1), definitions, seen=next_seen)
        right = _constant_i64_values(select.group(2), definitions, seen=next_seen)
        return None if left is None or right is None else left | right
    phi = re.fullmatch(rf"%{re.escape(name)} = phi i64 (.+)", definition.line)
    if phi is not None:
        values: set[int] = set()
        incoming = re.findall(r"\[\s*([^,]+),\s*%[A-Za-z_.$][A-Za-z0-9_.$-]*\s*\]", phi.group(1))
        if not incoming:
            return None
        for candidate in incoming:
            resolved = _constant_i64_values(candidate, definitions, seen=next_seen)
            if resolved is None:
                return None
            values.update(resolved)
        return values
    return None


def _status_word_is_zero_extended(
    operand: str,
    definitions: Mapping[str, Definition],
    *,
    seen: frozenset[str] = frozenset(),
) -> bool:
    """Recognize the closed status-word provenance accepted by the v0.4 ABI."""
    literal = _parse_int(operand)
    if literal is not None:
        return 0 <= literal <= 0xFF
    if not operand.startswith("%") or operand[1:] in seen:
        return False
    name = operand[1:]
    definition = definitions.get(name)
    if definition is None:
        return False
    next_seen = seen | {name}
    if re.fullmatch(
        rf"%{re.escape(name)} = zext i8 (?:%[A-Za-z_.$][A-Za-z0-9_.$-]*|[0-9]+) to i64",
        definition.line,
    ):
        return True
    select = re.fullmatch(
        rf"%{re.escape(name)} = select i1 [^,]+, i64 ([^,]+), i64 (.+)",
        definition.line,
    )
    if select is not None:
        return all(
            _status_word_is_zero_extended(candidate, definitions, seen=next_seen)
            for candidate in select.groups()
        )
    bitwise = re.fullmatch(
        rf"%{re.escape(name)} = (?:or|and|xor) i64 "
        r"([^,]+), (.+)",
        definition.line,
    )
    if bitwise is not None:
        return all(
            _status_word_is_zero_extended(candidate.strip(), definitions, seen=next_seen)
            for candidate in bitwise.groups()
        )
    phi = re.fullmatch(rf"%{re.escape(name)} = phi i64 (.+)", definition.line)
    if phi is not None:
        incoming = re.findall(
            r"\[\s*([^,]+),\s*%[A-Za-z_.$][A-Za-z0-9_.$-]*\s*\]",
            phi.group(1),
        )
        return bool(incoming) and all(
            _status_word_is_zero_extended(candidate, definitions, seen=next_seen)
            for candidate in incoming
        )
    extraction = re.fullmatch(
        rf"%{re.escape(name)} = extractvalue \{{ i64, i64 \}} "
        r"%[A-Za-z_.$][A-Za-z0-9_.$-]*, 0",
        definition.line,
    )
    # An index-zero value from another already-validated Action result preserves
    # the same zero-extension invariant through a direct aggregate call.
    return extraction is not None


def _membership_values(
    operand: str,
    definitions: Mapping[str, Definition],
    *,
    seen: frozenset[str] = frozenset(),
) -> tuple[str, set[int]] | None:
    """Evaluate the closed i1 spelling used for region-ID membership guards."""
    if not operand.startswith("%") or operand[1:] in seen:
        return None
    name = operand[1:]
    definition = definitions.get(name)
    if definition is None:
        return None
    next_seen = seen | {name}
    comparison = re.fullmatch(
        rf"%{re.escape(name)} = icmp eq i8 (%[A-Za-z_.$][A-Za-z0-9_.$-]*), ([0-9]+)",
        definition.line,
    )
    if comparison is not None:
        value = int(comparison.group(2))
        if not 0 <= value <= 255:
            return None
        return comparison.group(1), {value}
    identity = re.fullmatch(
        rf"%{re.escape(name)} = (?:or i1 "
        r"(%[A-Za-z_.$][A-Za-z0-9_.$-]*), false|and i1 "
        r"(%[A-Za-z_.$][A-Za-z0-9_.$-]*), true)",
        definition.line,
    )
    if identity is not None:
        return _membership_values(
            identity.group(1) or identity.group(2), definitions, seen=next_seen
        )
    boolean = re.fullmatch(
        rf"%{re.escape(name)} = (or|and) i1 "
        r"(%[A-Za-z_.$][A-Za-z0-9_.$-]*), (%[A-Za-z_.$][A-Za-z0-9_.$-]*)",
        definition.line,
    )
    if boolean is None:
        return None
    left = _membership_values(boolean.group(2), definitions, seen=next_seen)
    right = _membership_values(boolean.group(3), definitions, seen=next_seen)
    if left is None or right is None or left[0] != right[0]:
        return None
    values = left[1] | right[1] if boolean.group(1) == "or" else left[1] & right[1]
    return left[0], values


def _guard_branch(
    function: IRFunction,
    condition: str,
    access_block: str,
) -> tuple[str, str, str]:
    successors = _successors(function)
    matches: list[tuple[str, str, str]] = []
    for block, lines in function.blocks.items():
        branch = re.fullmatch(
            rf"br i1 %{re.escape(condition)}, label %"
            r"([A-Za-z_.$][A-Za-z0-9_.$-]*), label %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
            lines[-1],
        )
        if branch is not None:
            matches.append((block, branch.group(1), branch.group(2)))
    if len(matches) != 1:
        raise Core0Error(
            f"LLVM function {function.name} does not branch exactly once on %{condition}"
        )
    block, true_target, false_target = matches[0]
    if not _reachable(successors, true_target, access_block):
        raise Core0Error(
            f"LLVM function {function.name} guard %{condition} true edge cannot reach access"
        )
    if _reachable(successors, false_target, access_block):
        raise Core0Error(
            f"LLVM function {function.name} guard %{condition} denied edge reaches memory access"
        )
    return block, true_target, false_target


def _return_statuses(
    function: IRFunction,
    start: str,
    definitions: Mapping[str, Definition],
) -> set[int]:
    reachable = _reachable_blocks(_successors(function), start)
    statuses: set[int] = set()
    for block in reachable:
        for line in function.blocks[block]:
            match = re.fullmatch(
                r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = insertvalue \{ i64, i64 \} "
                r"poison, i64 ([^,]+), 0",
                line,
            )
            if match is None:
                continue
            values = _constant_i64_values(match.group(1), definitions)
            if values is not None:
                statuses.update(values)
    return statuses


def _expected_region_ids(access: str, width_bytes: int) -> tuple[set[int], set[int], set[int], set[int]]:
    known = {int(region["id"]) for region in REGIONS}
    ordinary = {int(region["id"]) for region in REGIONS if region["kind"] == "ordinary"}
    permitted = {
        int(region["id"])
        for region in REGIONS
        if region["kind"] == "ordinary" and bool(region[access])
    }
    width_allowed = {
        int(region["id"])
        for region in REGIONS
        if region["kind"] == "ordinary" and width_bytes in region["widths"]
    }
    return known, ordinary, permitted, width_allowed


def _named_definition(definitions: Mapping[str, Definition], name: str, context: str) -> Definition:
    definition = definitions.get(name)
    if definition is None:
        raise Core0Error(f"{context} lacks required SSA value %{name}")
    return definition


def _semantic_name(
    definitions: Mapping[str, Definition], stem: str, suffix: str, context: str
) -> str:
    """Resolve ``mem.<site>.<suffix>`` with the emitter's optional SSA serial."""
    prefix = stem + suffix
    matches = [
        name
        for name in definitions
        if name == prefix or re.fullmatch(re.escape(prefix) + r"\.[0-9]+", name)
    ]
    if len(matches) != 1:
        raise Core0Error(
            f"{context} does not define exactly one semantic %{prefix}[.<ssa>] value"
        )
    return matches[0]


def _phi_constants(
    definition: Definition, llvm_type: str
) -> dict[str, int] | None:
    match = re.fullmatch(
        rf"%[A-Za-z_.$][A-Za-z0-9_.$-]* = phi {re.escape(llvm_type)} (.+)",
        definition.line,
    )
    if match is None:
        return None
    incoming = re.findall(
        r"\[\s*(-?(?:0x[0-9A-Fa-f]+|[0-9]+)),\s*%"
        r"([A-Za-z_.$][A-Za-z0-9_.$-]*)\s*\]",
        match.group(1),
    )
    if not incoming:
        return None
    result: dict[str, int] = {}
    for value, predecessor in incoming:
        if predecessor in result:
            return None
        result[predecessor] = int(value, 0)
    return result


def _parse_accesses(function: IRFunction) -> list[AccessRecord]:
    records: list[AccessRecord] = []
    for block, lines in function.blocks.items():
        for index, line in enumerate(lines):
            load = re.fullmatch(
                r"%[A-Za-z_.$][A-Za-z0-9_.$-]* = load (volatile )?"
                r"i(8|32|64), ptr %([A-Za-z_.$][A-Za-z0-9_.$-]*), align ([0-9]+)",
                line,
            )
            store = re.fullmatch(
                r"store (volatile )?i(8|32|64) ([^,]+), ptr "
                r"%([A-Za-z_.$][A-Za-z0-9_.$-]*), align ([0-9]+)",
                line,
            )
            if load is None and store is None:
                continue
            if load is not None:
                access = "read"
                bits = int(load.group(2))
                pointer = load.group(3)
                alignment = int(load.group(4))
                value_operand = None
                volatile = load.group(1) is not None
            else:
                assert store is not None
                access = "write"
                bits = int(store.group(2))
                value_operand = store.group(3).strip()
                pointer = store.group(4)
                alignment = int(store.group(5))
                volatile = store.group(1) is not None
            if alignment != bits // 8:
                raise Core0Error(
                    f"LLVM function {function.name} {access}{bits} has wrong access alignment"
                )
            stem_match = re.fullmatch(r"(mem\.[0-9]+\.)pointer(?:\.[0-9]+)?", pointer)
            if stem_match is None:
                raise Core0Error(
                    f"LLVM function {function.name} memory access lacks a stable mem.<site>.pointer"
                )
            records.append(
                AccessRecord(
                    function=function.name,
                    block=block,
                    index=index,
                    stem=stem_match.group(1),
                    access=access,
                    bits=bits,
                    volatile=volatile,
                    value_operand=value_operand,
                )
            )
    return records


def _reject_unmodeled_memory_instructions(
    function: IRFunction, records: Sequence[AccessRecord]
) -> None:
    """Reject accesses that evade the stable checked-memory spelling.

    Site-count equality alone is insufficient: a faulty lowerer could retain all
    expected checked accesses while adding a second, unguarded load or store in a
    spelling the structured parser ignores.
    """
    audited = {(record.block, record.index) for record in records}
    for block, lines in function.blocks.items():
        for index, line in enumerate(lines):
            memory_instruction = (
                re.search(r"(?:^|=\s)(?:load|atomicrmw|cmpxchg)\b", line) is not None
                or re.match(r"^(?:store|fence)\b", line) is not None
            )
            if memory_instruction and (block, index) not in audited:
                raise Core0Error(
                    f"LLVM function {function.name} contains an unaudited memory "
                    f"instruction in %{block}: {line}"
                )


def _branch_targets(function: IRFunction, condition: str) -> tuple[str, str, str]:
    matches: list[tuple[str, str, str]] = []
    for block, lines in function.blocks.items():
        branch = re.fullmatch(
            rf"br i1 %{re.escape(condition)}, label %"
            r"([A-Za-z_.$][A-Za-z0-9_.$-]*), label %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
            lines[-1],
        )
        if branch is not None:
            matches.append((block, branch.group(1), branch.group(2)))
    if len(matches) != 1:
        raise Core0Error(
            f"LLVM function {function.name} does not branch exactly once on %{condition}"
        )
    return matches[0]


def _statuses_from_edge(
    function: IRFunction,
    start: str,
    definitions: Mapping[str, Definition],
    status_phi: Mapping[str, int] | None,
) -> set[int]:
    if status_phi is None:
        return _return_statuses(function, start, definitions)
    successors = _successors(function)
    return {
        status
        for predecessor, status in status_phi.items()
        if _reachable(successors, start, predecessor)
    }


def _validate_dispatch_guards(
    function: IRFunction,
    definitions: Mapping[str, Definition],
    record: AccessRecord,
    context: str,
    *,
    range_site: bool = False,
) -> tuple[str, list[str], dict[str, int]] | None:
    """Validate the emitter's exact eight-way region dispatch and metadata phis.

    Returns ``None`` for the compact explicit-boolean spelling used by some unit
    fixtures.  The production spelling is an ID dispatch followed by exact phis.
    """
    dispatch_names = [
        name
        for name in definitions
        if re.fullmatch(re.escape(record.stem + "region-known") + r"\.[0-9]+", name)
    ]
    if not dispatch_names:
        return None
    expected_ids = [int(region["id"]) for region in REGIONS]
    by_id: dict[int, tuple[str, str, str, str]] = {}
    region_operand: str | None = None
    for name in dispatch_names:
        definition = definitions[name]
        match = re.fullmatch(
            rf"%{re.escape(name)} = icmp eq i8 "
            r"(%[A-Za-z_.$][A-Za-z0-9_.$-]*|[0-9]+), ([0-9]+)",
            definition.line,
        )
        if match is None:
            raise Core0Error(f"{context} region lookup contains a malformed ID comparison")
        operand, region_text = match.groups()
        region_id = int(region_text)
        if region_id in by_id:
            raise Core0Error(f"{context} region lookup compares ID {region_id} twice")
        if region_operand is None:
            region_operand = operand
        elif operand != region_operand:
            raise Core0Error(f"{context} region lookup compares different runtime IDs")
        block, true_target, false_target = _branch_targets(function, name)
        by_id[region_id] = (name, block, true_target, false_target)
    if list(by_id) != expected_ids:
        raise Core0Error(
            f"{context} region lookup order/catalog differs: {list(by_id)!r} != {expected_ids!r}"
        )
    assert region_operand is not None
    for left, right in zip(expected_ids, expected_ids[1:]):
        if by_id[left][3] != definitions[by_id[right][0]].block:
            raise Core0Error(f"{context} region lookup false-edge chain is malformed")
    successors = _successors(function)
    if _reachable(successors, by_id[expected_ids[-1]][3], record.block):
        raise Core0Error(f"{context} unknown-region path reaches memory access")

    metadata_targets: set[str] = set()
    region_predecessors: dict[int, str] = {}
    for region_id in expected_ids:
        true_target = by_id[region_id][2]
        targets = successors[true_target]
        if len(targets) != 1:
            raise Core0Error(f"{context} region {region_id} does not enter one metadata join")
        metadata_targets.add(targets[0])
        region_predecessors[region_id] = true_target
    if len(metadata_targets) != 1:
        raise Core0Error(f"{context} region lookup does not converge at one metadata join")

    metadata_expectations: tuple[tuple[str, str, dict[int, int]], ...] = (
        ("base", "i64", {int(r["id"]): int(r["base"]) for r in REGIONS}),
        ("length", "i64", {int(r["id"]): int(r["length"]) for r in REGIONS}),
        (
            "class",
            "i8",
            {
                int(r["id"]): {"ordinary": 0, "reserved": 1, "device": 2}[str(r["kind"])]
                for r in REGIONS
            },
        ),
        (
            "permission-ok",
            "i1",
            {
                int(r["id"]): int(str(r["kind"]) == "ordinary" and bool(r[record.access]))
                for r in REGIONS
            },
        ),
        (
            "width-ok",
            "i1",
            {
                int(r["id"]): (
                    1
                    if range_site
                    else int(
                        str(r["kind"]) == "ordinary"
                        and record.bits // 8 in r["widths"]
                    )
                )
                for r in REGIONS
            },
        ),
    )
    semantic_names: dict[str, str] = {}
    for suffix, llvm_type, expected_by_id in metadata_expectations:
        name = _semantic_name(definitions, record.stem, suffix, context)
        semantic_names[suffix] = name
        incoming = _phi_constants(definitions[name], llvm_type)
        expected_by_predecessor = {
            region_predecessors[region_id]: value
            for region_id, value in expected_by_id.items()
        }
        if incoming != expected_by_predecessor:
            raise Core0Error(f"{context} {suffix} metadata phi differs from the region catalog")

    class_ok = _semantic_name(definitions, record.stem, "class-ok", context)
    if definitions[class_ok].line != (
        f"%{class_ok} = icmp eq i8 %{semantic_names['class']}, 0"
    ):
        raise Core0Error(f"{context} class guard does not admit exactly ordinary RAM")
    class_block, _class_true, class_false = _guard_branch(
        function, class_ok, record.block
    )
    permission_name = semantic_names["permission-ok"]
    permission_block, _permission_true, permission_false = _guard_branch(
        function, permission_name, record.block
    )
    width_name = semantic_names["width-ok"]
    width_block, _width_true, width_false = _guard_branch(
        function, width_name, record.block
    )

    status_name = _semantic_name(definitions, record.stem, "status", context)
    status_phi = _phi_constants(definitions[status_name], "i8")
    if status_phi is None:
        raise Core0Error(f"{context} lacks the exact checked-status outcome phi")
    reserved_name = _semantic_name(
        definitions, record.stem, "class-is-reserved", context
    )
    if definitions[reserved_name].line != (
        f"%{reserved_name} = icmp eq i8 %{semantic_names['class']}, 1"
    ):
        raise Core0Error(
            f"{context} reserved/device classifier does not test class 1"
        )
    reserved_block, reserved_true, reserved_false = _branch_targets(
        function, reserved_name
    )
    if reserved_block != class_false:
        raise Core0Error(
            f"{context} reserved/device classifier is not the class-denied control edge"
        )
    if _statuses_from_edge(function, reserved_true, definitions, status_phi) != {2}:
        raise Core0Error(f"{context} reserved control edge does not return status 2")
    if _statuses_from_edge(function, reserved_false, definitions, status_phi) != {3}:
        raise Core0Error(f"{context} device control edge does not return status 3")
    expected_edge_statuses = (
        (by_id[expected_ids[-1]][3], {1}, "unknown-region"),
        (class_false, {2, 3}, "class"),
        (permission_false, {4 if record.access == "read" else 5}, "permission"),
        (width_false, {6}, "width"),
    )
    for start, expected, label in expected_edge_statuses:
        observed = _statuses_from_edge(function, start, definitions, status_phi)
        if observed != expected:
            raise Core0Error(
                f"{context} {label} denial statuses differ: "
                f"{sorted(observed)!r} != {sorted(expected)!r}"
            )
    return region_operand, [by_id[expected_ids[0]][1], class_block, permission_block, width_block], status_phi


def _validate_one_access(
    function: IRFunction,
    record: AccessRecord,
    *,
    require_volatile: bool,
) -> dict[str, object]:
    definitions = _definitions(function)
    dominators = _dominators(function)
    context = f"LLVM function {function.name} {record.stem[:-1]}"
    width = record.bits // 8
    if record.volatile != require_volatile:
        expectation = "volatile" if require_volatile else "nonvolatile"
        raise Core0Error(f"{context} ordinary-RAM access is not exactly {expectation}")

    pointer_name = _semantic_name(definitions, record.stem, "pointer", context)
    address_name = _semantic_name(definitions, record.stem, "address", context)
    pointer = definitions[pointer_name]
    expected_pointer = (
        rf"%{re.escape(pointer_name)} = inttoptr i64 %{re.escape(address_name)} to ptr"
    )
    if re.fullmatch(expected_pointer, pointer.line) is None:
        raise Core0Error(f"{context} pointer is not derived from its checked address")
    if not _dominates_instruction(pointer, record.block, record.index, dominators):
        raise Core0Error(f"{context} pointer does not dominate its memory access")

    address = definitions[address_name]
    address_match = re.fullmatch(
        rf"%{re.escape(address_name)} = add i64 ([^,]+), (.+)", address.line
    )
    if address_match is None:
        raise Core0Error(f"{context} address is not an unflagged base-plus-offset addition")
    if FORBIDDEN_IR_FLAGS.search(address.line):
        raise Core0Error(f"{context} address addition carries a forbidden LLVM flag")

    remaining_name = _semantic_name(definitions, record.stem, "remaining", context)
    remaining = definitions[remaining_name]
    remaining_match = re.fullmatch(
        rf"%{re.escape(remaining_name)} = sub i64 ([^,]+), {width}", remaining.line
    )
    if remaining_match is None:
        raise Core0Error(
            f"{context} does not subtract the validated width from the region length"
        )
    if FORBIDDEN_IR_FLAGS.search(remaining.line):
        raise Core0Error(f"{context} remaining-length subtraction carries a forbidden flag")

    length_name = _semantic_name(definitions, record.stem, "length-ok", context)
    length_guard = definitions[length_name]
    length_uge = re.fullmatch(
        rf"%{re.escape(length_name)} = icmp uge i64 "
        rf"{re.escape(remaining_match.group(1))}, {width}",
        length_guard.line,
    )
    length_ule = re.fullmatch(
        rf"%{re.escape(length_name)} = icmp ule i64 {width}, "
        rf"{re.escape(remaining_match.group(1))}",
        length_guard.line,
    )
    if length_uge is None and length_ule is None:
        raise Core0Error(f"{context} lacks the exact width-before-subtraction guard")

    offset_name = _semantic_name(definitions, record.stem, "offset-ok", context)
    offset_guard = definitions[offset_name]
    offset_match = re.fullmatch(
        rf"%{re.escape(offset_name)} = icmp ule i64 ([^,]+), %{re.escape(remaining_name)}",
        offset_guard.line,
    )
    if offset_match is None:
        raise Core0Error(f"{context} lacks the exact offset-within-remaining guard")
    offset_operand = offset_match.group(1)
    address_left = address_match.group(1).strip()
    address_right = address_match.group(2).strip()
    address_operands = (address_left, address_right)
    if offset_operand not in address_operands:
        raise Core0Error(f"{context} bounds-checks a different offset from its address")
    if address_left == offset_operand and address_right == offset_operand:
        raise Core0Error(f"{context} address does not have a distinct region base")
    base_operand = address_right if address_left == offset_operand else address_left

    mask_name = _semantic_name(definitions, record.stem, "alignment-mask", context)
    mask = definitions[mask_name]
    if mask.line != f"%{mask_name} = and i64 {offset_operand}, {width - 1}":
        raise Core0Error(f"{context} alignment mask differs from width minus one")
    aligned_name = _semantic_name(definitions, record.stem, "alignment-ok", context)
    aligned = definitions[aligned_name]
    if aligned.line != f"%{aligned_name} = icmp eq i64 %{mask_name}, 0":
        raise Core0Error(f"{context} lacks the exact zero alignment comparison")

    dispatch = _validate_dispatch_guards(function, definitions, record, context)
    status_phi: dict[str, int] | None = None
    if dispatch is not None:
        region_operand, guard_blocks, status_phi = dispatch
    else:
        known, ordinary, permitted, width_allowed = _expected_region_ids(record.access, width)
        membership_expectations = (
            ("region-known", known, {1}),
            ("class-ok", ordinary, {2, 3}),
            ("permission-ok", permitted, {4 if record.access == "read" else 5}),
            ("width-ok", width_allowed, {6}),
        )
        guard_blocks = []
        region_operand = None
        for suffix, expected_ids, expected_statuses in membership_expectations:
            name = _semantic_name(definitions, record.stem, suffix, context)
            membership = _membership_values("%" + name, definitions)
            if membership is None or membership[1] != expected_ids:
                raise Core0Error(
                    f"{context} %{name} does not encode the exact {suffix} region-ID set"
                )
            if region_operand is None:
                region_operand = membership[0]
            elif membership[0] != region_operand:
                raise Core0Error(f"{context} region guards inspect different runtime IDs")
            block, _true, false = _guard_branch(function, name, record.block)
            statuses = _return_statuses(function, false, definitions)
            if statuses != expected_statuses:
                raise Core0Error(
                    f"{context} {suffix} denial statuses differ: "
                    f"{sorted(statuses)!r} != {sorted(expected_statuses)!r}"
                )
            guard_blocks.append(block)

    for name, statuses in (
        (length_name, {7}),
        (offset_name, {7}),
        (aligned_name, {8}),
    ):
        block, _true, false = _guard_branch(function, name, record.block)
        if _statuses_from_edge(function, false, definitions, status_phi) != statuses:
            raise Core0Error(f"{context} %{name} has the wrong denial status")
        guard_blocks.append(block)

    # Dominance establishes the required semantic order even when unrelated
    # bookkeeping instructions appear between the named guards.
    for previous, following in zip(guard_blocks, guard_blocks[1:]):
        if previous not in dominators[following] or previous == following:
            raise Core0Error(f"{context} memory guards are not in the required order")
    if guard_blocks[-1] not in dominators[record.block]:
        raise Core0Error(f"{context} alignment guard does not dominate the access")

    length_block, length_true, _length_false = _guard_branch(
        function, length_name, record.block
    )
    if length_true not in dominators[remaining.block]:
        raise Core0Error(f"{context} subtracts width before proving length >= width")
    if not _dominates_instruction(remaining, offset_guard.block, offset_guard.index, dominators):
        raise Core0Error(f"{context} offset guard does not consume a dominating remainder")
    if not _dominates_instruction(address, pointer.block, pointer.index, dominators):
        raise Core0Error(f"{context} address does not dominate pointer construction")
    if guard_blocks[-1] not in dominators[address.block]:
        raise Core0Error(f"{context} constructs its address before all guards pass")

    # The unsafe wrap-prone spelling is forbidden even if another guard happens
    # to coexist.  The only accepted addition involving the offset is base+offset.
    wrap = re.compile(
        rf"= add(?:\s+(?:nuw|nsw))* i64 (?:{re.escape(offset_operand)}, {width}|"
        rf"{width}, {re.escape(offset_operand)})$"
    )
    for definition in definitions.values():
        if wrap.search(definition.line):
            raise Core0Error(f"{context} uses wrap-prone offset-plus-width validation")

    del length_block  # The true successor, not the spelling of the block name, matters.
    return {
        "function": function.name,
        "site": record.stem[:-1],
        "access": record.access,
        "width_bits": record.bits,
        "volatile": record.volatile,
        "region_operand": region_operand,
        "base_operand": base_operand,
        "offset_operand": offset_operand,
        "value_operand": record.value_operand,
        "guard_blocks": guard_blocks,
        "denied_path_access": False,
    }


SOURCE_MEMORY_OPERATION = re.compile(
    r"\(action\.(load(?:8|32|64)|store(?:8|32|64)|check-(?:read|write)-range)\b"
)


def _normalized_operand_at(body: str, start: int, context: str) -> tuple[str, int]:
    """Read one balanced normalized scalar expression starting at ``start``."""
    while start < len(body) and body[start].isspace():
        start += 1
    if start >= len(body) or body[start] != "(":
        raise Core0Error(f"{context} lacks a parenthesized normalized operand")
    depth = 0
    for index in range(start, len(body)):
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
            if depth == 0:
                return body[start : index + 1], index + 1
            if depth < 0:
                break
    raise Core0Error(f"{context} has an unbalanced normalized operand")


def _source_memory_sites(body: str) -> list[SourceMemorySite]:
    """Recover normalized memory operands in the lowerer's stable site order."""
    sites: list[SourceMemorySite] = []
    for match in SOURCE_MEMORY_OPERATION.finditer(body):
        operation = match.group(1)
        context = f"normalized {operation} site #{len(sites)}"
        operand_count = 3 if operation.startswith("store") or operation.startswith("check-") else 2
        operands: list[str] = []
        position = match.end()
        for _ in range(operand_count):
            operand, position = _normalized_operand_at(body, position, context)
            operands.append(operand)
        if operation.startswith("load"):
            sites.append(
                SourceMemorySite(
                    index=len(sites),
                    access="read",
                    bits=int(operation.removeprefix("load")),
                    region=operands[0],
                    offset=operands[1],
                )
            )
        elif operation.startswith("store"):
            sites.append(
                SourceMemorySite(
                    index=len(sites),
                    access="write",
                    bits=int(operation.removeprefix("store")),
                    region=operands[0],
                    offset=operands[1],
                    value=operands[2],
                )
            )
        else:
            sites.append(
                SourceMemorySite(
                    index=len(sites),
                    access="read" if operation == "check-read-range" else "write",
                    bits=None,
                    region=operands[0],
                    offset=operands[1],
                    length=operands[2],
                )
            )
    return sites


def _direct_source_operand(
    expression: str,
    signature: Sequence[str],
    expected_type: str,
    context: str,
) -> str | None:
    """Map a direct source argument/literal to its exact LLVM operand.

    Bound Action variables and computed scalar expressions intentionally return
    ``None``.  Their general semantic lowering is outside this focused audit;
    callers expose coverage so evidence cannot imply they were checked here.
    """
    variable = re.fullmatch(r"\(var ([0-9]+) (bool|u8|u32|u64)\)", expression)
    if variable is not None:
        index = int(variable.group(1))
        source_type = variable.group(2)
        if source_type != expected_type:
            raise Core0Error(
                f"{context} source operand has type {source_type}, expected {expected_type}"
            )
        if index >= len(signature):
            return None
        if signature[index] != source_type:
            raise Core0Error(
                f"{context} source argument type differs from its function signature"
            )
        return f"%arg{index}"
    literal = re.fullmatch(r"\(lit (u8|u32|u64) ([0-9]+)\)", expression)
    if literal is not None:
        source_type, value_text = literal.groups()
        if source_type != expected_type:
            raise Core0Error(
                f"{context} source literal has type {source_type}, expected {expected_type}"
            )
        width = {"u8": 8, "u32": 32, "u64": 64}[source_type]
        value = int(value_text)
        if not 0 <= value < 1 << width:
            raise Core0Error(f"{context} source literal is outside {source_type}")
        return str(value)
    return None


def _bind_direct_source_operand(
    expression: str,
    observed: str,
    signature: Sequence[str],
    expected_type: str,
    context: str,
) -> bool:
    expected = _direct_source_operand(expression, signature, expected_type, context)
    if expected is None:
        return False
    if observed != expected:
        raise Core0Error(
            f"{context} LLVM operand differs from normalized source: "
            f"{observed} != {expected}"
        )
    return True


def _expected_access_counts(body: str) -> dict[tuple[str, int], int]:
    result: dict[tuple[str, int], int] = {}
    for operation, bits in re.findall(r"\(action\.(load|store)(8|32|64)\b", body):
        key = ("read" if operation == "load" else "write", int(bits))
        result[key] = result.get(key, 0) + 1
    return result


def _expected_range_counts(body: str) -> dict[str, int]:
    result = {"read": 0, "write": 0}
    for access in re.findall(r"\(action\.check-(read|write)-range\b", body):
        result[access] += 1
    return {access: count for access, count in result.items() if count}


def _range_stems(function: IRFunction) -> list[str]:
    definitions = _definitions(function)
    candidates = {
        match.group(1)
        for name in definitions
        if (
            match := re.fullmatch(r"(mem\.[0-9]+\.)length-ok(?:\.[0-9]+)?", name)
        )
    }
    pointer_stems = {
        match.group(1)
        for name in definitions
        if (match := re.fullmatch(r"(mem\.[0-9]+\.)pointer(?:\.[0-9]+)?", name))
    }
    return sorted(candidates - pointer_stems, key=lambda stem: int(stem.split(".")[1]))


def _validate_one_range(
    function: IRFunction,
    stem: str,
) -> dict[str, object]:
    definitions = _definitions(function)
    dominators = _dominators(function)
    context = f"LLVM function {function.name} {stem[:-1]} range"
    length_name = _semantic_name(definitions, stem, "length-ok", context)
    remaining_name = _semantic_name(definitions, stem, "remaining", context)
    offset_name = _semantic_name(definitions, stem, "offset-ok", context)
    length = definitions[length_name]
    remaining = definitions[remaining_name]
    offset = definitions[offset_name]
    remaining_match = re.fullmatch(
        rf"%{re.escape(remaining_name)} = sub i64 ([^,]+), (.+)", remaining.line
    )
    if remaining_match is None or FORBIDDEN_IR_FLAGS.search(remaining.line):
        raise Core0Error(f"{context} lacks unflagged region-length-minus-requested-length")
    region_length, requested_length = (
        remaining_match.group(1).strip(),
        remaining_match.group(2).strip(),
    )
    if length.line != (
        f"%{length_name} = icmp ule i64 {requested_length}, {region_length}"
    ):
        raise Core0Error(f"{context} does not validate length before subtraction")
    offset_match = re.fullmatch(
        rf"%{re.escape(offset_name)} = icmp ule i64 ([^,]+), %{re.escape(remaining_name)}",
        offset.line,
    )
    if offset_match is None:
        raise Core0Error(f"{context} lacks offset-within-remaining validation")
    offset_operand = offset_match.group(1).strip()
    offset_block, offset_true, _offset_false = _branch_targets(function, offset_name)

    # The permission status distinguishes read-range from write-range without
    # trusting the source manifest's effect label.
    status_name = _semantic_name(definitions, stem, "status", context)
    status_phi = _phi_constants(definitions[status_name], "i8")
    if status_phi is None:
        raise Core0Error(f"{context} lacks a checked-status outcome phi")
    permission_name = _semantic_name(definitions, stem, "permission-ok", context)
    _permission_block, _permission_true, permission_false = _branch_targets(
        function, permission_name
    )
    permission_statuses = _statuses_from_edge(
        function, permission_false, definitions, status_phi
    )
    if permission_statuses == {4}:
        access = "read"
    elif permission_statuses == {5}:
        access = "write"
    else:
        raise Core0Error(f"{context} has an invalid range permission status")

    pseudo = AccessRecord(
        function=function.name,
        block=offset_true,
        index=0,
        stem=stem,
        access=access,
        bits=0,
        volatile=False,
        value_operand=None,
    )
    dispatch = _validate_dispatch_guards(
        function, definitions, pseudo, context, range_site=True
    )
    if dispatch is None:
        raise Core0Error(f"{context} does not use the exact region metadata dispatch")
    region_operand, guard_blocks, dispatch_status_phi = dispatch
    if dispatch_status_phi != status_phi:
        raise Core0Error(f"{context} has inconsistent range status phis")
    for name, expected in ((length_name, {7}), (offset_name, {7})):
        block, _true, false = _guard_branch(function, name, offset_true)
        if _statuses_from_edge(function, false, definitions, status_phi) != expected:
            raise Core0Error(f"{context} %{name} has the wrong denial status")
        guard_blocks.append(block)
    for previous, following in zip(guard_blocks, guard_blocks[1:]):
        if previous not in dominators[following] or previous == following:
            raise Core0Error(f"{context} guards are not in required order")
    _length_block, length_true, _length_false = _guard_branch(
        function, length_name, offset_true
    )
    if length_true not in dominators[remaining.block]:
        raise Core0Error(f"{context} subtracts before its length guard passes")
    if not _dominates_instruction(remaining, offset.block, offset.index, dominators):
        raise Core0Error(f"{context} offset guard does not consume its remainder")
    if any(
        re.fullmatch(re.escape(stem + suffix) + r"(?:\.[0-9]+)?", name)
        for suffix in ("alignment-mask", "alignment-ok", "address", "pointer")
        for name in definitions
    ):
        raise Core0Error(f"{context} incorrectly constructs an address or alignment access")
    wrap = re.compile(
        rf"= add(?:\s+(?:nuw|nsw))* i64 (?:{re.escape(offset_operand)}, "
        rf"{re.escape(requested_length)}|{re.escape(requested_length)}, "
        rf"{re.escape(offset_operand)})$"
    )
    if any(wrap.search(definition.line) for definition in definitions.values()):
        raise Core0Error(f"{context} uses wrap-prone offset-plus-length validation")
    return {
        "function": function.name,
        "site": stem[:-1],
        "access": access,
        "requested_length": requested_length,
        "offset_operand": offset_operand,
        "region_operand": region_operand,
        "guard_blocks": guard_blocks,
        "denied_path_access": False,
    }


def validate_checked_result_ir(
    manifest: Mapping[str, object], pre_ir: str
) -> dict[str, object]:
    """Check direct aggregate returns/calls and the RV64 two-word result spelling."""
    functions = parse_ir_functions(pre_ir)
    action_functions = manifest.get("action_functions")
    if not isinstance(action_functions, list):
        raise Core0Error("memory manifest action_functions is malformed")
    action_symbols = {
        str(function["llvm"])
        for function in action_functions
        if isinstance(function, dict) and "llvm" in function
    }
    action_by_source = {
        str(function["source"]): str(function["llvm"])
        for function in action_functions
        if isinstance(function, dict) and "source" in function and "llvm" in function
    }
    if re.search(r"\b(?:sret|byval)\b", pre_ir):
        raise Core0Error("checked-result ABI must not use sret/byval memory passing")
    if re.search(r"\bcall\s+\{ i64, i64 \}\s+%", pre_ir):
        raise Core0Error("checked-result ABI contains an indirect Action call")

    aggregate_calls = 0
    aggregate_returns = 0
    for entry in action_functions:
        if not isinstance(entry, dict):
            raise Core0Error("memory manifest contains a malformed Action function")
        symbol = str(entry["llvm"])
        function = functions.get(symbol)
        if function is None:
            raise Core0Error(f"pre-optimization IR lacks Action function @{symbol}")
        header = re.match(
            rf"^define (?:internal )?\{{ i64, i64 \}} @{re.escape(symbol)}\(([^)]*)\)",
            function.header,
        )
        if header is None:
            raise Core0Error(
                f"Action function @{symbol} does not directly return {{ i64, i64 }}"
            )
        signature = entry.get("signature")
        if not isinstance(signature, dict) or not isinstance(signature.get("args"), list):
            raise Core0Error(f"Action function @{symbol} has a malformed signature")
        expected_arguments = []
        for index, argument in enumerate(signature["args"]):
            if argument == "bool":
                expected_arguments.append(f"i1 zeroext %arg{index}")
            elif argument == "u8":
                expected_arguments.append(f"i8 zeroext %arg{index}")
            elif argument == "u32":
                expected_arguments.append(f"i32 signext %arg{index}")
            elif argument == "u64":
                expected_arguments.append(f"i64 %arg{index}")
            else:
                raise Core0Error(f"Action function @{symbol} has an unsupported argument type")
        if header.group(1) != ", ".join(expected_arguments):
            raise Core0Error(
                f"Action function @{symbol} LLVM parameters differ from its scalar signature"
            )
        definitions = _definitions(function)
        observed_callees: list[str] = []
        function_return_count = 0
        for block, lines in function.blocks.items():
            for index, line in enumerate(lines):
                if "alloca { i64, i64 }" in line or re.search(
                    r"(?:load|store)(?: volatile)? \{ i64, i64 \}", line
                ):
                    raise Core0Error(
                        f"Action function @{symbol} spills checked-result through memory"
                    )
                status = re.fullmatch(
                    r"%([A-Za-z_.$][A-Za-z0-9_.$-]*) = insertvalue "
                    r"\{ i64, i64 \} poison, i64 ([^,]+), 0",
                    line,
                )
                if status is not None:
                    if not _status_word_is_zero_extended(status.group(2), definitions):
                        raise Core0Error(
                            f"Action function @{symbol} does not zero-extend status to i64"
                        )
                insertion = re.search(
                    r"\binsertvalue \{ i64, i64 \} .+, i64 .+, ([0-9]+)$", line
                )
                if insertion is not None and int(insertion.group(1)) not in (0, 1):
                    raise Core0Error(
                        f"Action function @{symbol} uses a noncanonical checked-result index"
                    )
                extraction = re.search(
                    r"\bextractvalue \{ i64, i64 \} .+, ([0-9]+)$", line
                )
                if extraction is not None and int(extraction.group(1)) not in (0, 1):
                    raise Core0Error(
                        f"Action function @{symbol} uses a noncanonical checked-result extract"
                    )
                call = re.search(
                    r"\bcall \{ i64, i64 \} @([A-Za-z_.$][A-Za-z0-9_.$-]*)\(", line
                )
                if call is not None:
                    aggregate_calls += 1
                    observed_callees.append(call.group(1))
                    if call.group(1) not in action_symbols:
                        raise Core0Error(
                            f"Action function @{symbol} calls unmanifested aggregate callee "
                            f"@{call.group(1)}"
                        )
                elif re.search(
                    r"(?:^|=\s)(?:(?:musttail|notail|tail)\s+)?call\b", line
                ):
                    raise Core0Error(
                        f"Action function @{symbol} contains a non-direct or non-Action call"
                    )
                if line.startswith("ret { i64, i64 } "):
                    aggregate_returns += 1
                    function_return_count += 1
                    returned = re.fullmatch(
                        r"ret \{ i64, i64 \} %([A-Za-z_.$][A-Za-z0-9_.$-]*)",
                        line,
                    )
                    if returned is None or returned.group(1) not in definitions:
                        raise Core0Error(
                            f"Action function @{symbol} does not return a checked SSA aggregate"
                        )
                    complete_name = returned.group(1)
                    complete = re.fullmatch(
                        rf"%{re.escape(complete_name)} = insertvalue "
                        r"\{ i64, i64 \} %([A-Za-z_.$][A-Za-z0-9_.$-]*), "
                        r"i64 .+, 1",
                        definitions[complete_name].line,
                    )
                    if complete is None or complete.group(1) not in definitions:
                        raise Core0Error(
                            f"Action function @{symbol} does not put result value in word 1"
                        )
                    partial_name = complete.group(1)
                    partial = re.fullmatch(
                        rf"%{re.escape(partial_name)} = insertvalue "
                        r"\{ i64, i64 \} poison, i64 (.+), 0",
                        definitions[partial_name].line,
                    )
                    if partial is None or not _status_word_is_zero_extended(
                        partial.group(1), definitions
                    ):
                        raise Core0Error(
                            f"Action function @{symbol} does not put zero-extended status in word 0"
                        )
            if not lines[-1].startswith(("ret ", "br ", "unreachable")):
                raise Core0Error(f"Action function @{symbol} block %{block} lacks a terminator")
        if function_return_count == 0:
            raise Core0Error(
                f"Action function @{symbol} has no checked-result return"
            )
        expected_callees: list[str] = []
        for dependency in _body_action_call_sites(str(entry.get("body", ""))):
            callee = action_by_source.get(dependency)
            if callee is None:
                raise Core0Error(
                    f"Action function @{symbol} references unknown source callee {dependency}"
                )
            expected_callees.append(callee)
        if Counter(observed_callees) != Counter(expected_callees):
            raise Core0Error(
                f"Action function @{symbol} LLVM call-site closure differs from source"
            )
    return {
        "action_function_count": len(action_functions),
        "aggregate_call_count": aggregate_calls,
        "aggregate_return_count": aggregate_returns,
        "sret": False,
        "direct_calls": True,
    }


def validate_memory_pre_ir(
    manifest: Mapping[str, object],
    pre_ir: str,
    *,
    require_volatile: bool = True,
) -> dict[str, object]:
    """Audit every source Action load/store in pre-optimization LLVM.

    ``require_volatile`` is explicit so the policy is testable.  The v0.4 suite
    must call this with its manifest value, which is exactly ``True``.
    """
    if FORBIDDEN_IR_FLAGS.search(pre_ir):
        raise Core0Error("pre-optimization memory IR contains a forbidden LLVM flag")
    checked_result = validate_checked_result_ir(manifest, pre_ir)
    functions = parse_ir_functions(pre_ir)
    action_functions = manifest.get("action_functions")
    if not isinstance(action_functions, list):
        raise Core0Error("memory manifest action_functions is malformed")
    records: list[dict[str, object]] = []
    range_records: list[dict[str, object]] = []
    source_binding_counts = {
        "region": 0,
        "offset": 0,
        "store_value": 0,
        "range_length": 0,
    }
    source_site_count = 0
    for entry in action_functions:
        if not isinstance(entry, dict):
            raise Core0Error("memory manifest contains a malformed Action function")
        source, symbol, body = str(entry["source"]), str(entry["llvm"]), str(entry["body"])
        function = functions.get(symbol)
        if function is None:
            raise Core0Error(f"pre-optimization IR lacks Action function @{symbol}")
        signature_object = entry.get("signature")
        if not isinstance(signature_object, dict) or not isinstance(
            signature_object.get("args"), list
        ):
            raise Core0Error(f"Action function {source} has a malformed signature")
        signature = [str(argument) for argument in signature_object["args"]]
        source_sites = _source_memory_sites(body)
        source_site_count += len(source_sites)
        source_by_index = {site.index: site for site in source_sites}
        observed_site_indices: set[int] = set()
        accesses = _parse_accesses(function)
        _reject_unmodeled_memory_instructions(function, accesses)
        observed_counts: dict[tuple[str, int], int] = {}
        for access in accesses:
            site_index = int(access.stem.split(".")[1])
            site = source_by_index.get(site_index)
            if (
                site is None
                or site.bits is None
                or site.access != access.access
                or site.bits != access.bits
            ):
                raise Core0Error(
                    f"Action function {source} LLVM {access.stem[:-1]} does not match "
                    "its normalized memory site"
                )
            if site_index in observed_site_indices:
                raise Core0Error(
                    f"Action function {source} repeats LLVM memory site {site_index}"
                )
            observed_site_indices.add(site_index)
            key = (access.access, access.bits)
            observed_counts[key] = observed_counts.get(key, 0) + 1
            record = _validate_one_access(
                function,
                access,
                require_volatile=require_volatile,
            )
            binding = {
                "region": _bind_direct_source_operand(
                    site.region,
                    str(record["region_operand"]),
                    signature,
                    "u8",
                    f"Action function {source} site {site_index} region",
                ),
                "offset": _bind_direct_source_operand(
                    site.offset,
                    str(record["offset_operand"]),
                    signature,
                    "u64",
                    f"Action function {source} site {site_index} offset",
                ),
                "store_value": False,
            }
            if access.access == "write":
                if site.value is None or access.value_operand is None:
                    raise Core0Error(
                        f"Action function {source} site {site_index} lacks a store value"
                    )
                binding["store_value"] = _bind_direct_source_operand(
                    site.value,
                    access.value_operand,
                    signature,
                    f"u{access.bits}",
                    f"Action function {source} site {site_index} store value",
                )
            for binding_name, audited in binding.items():
                if audited:
                    source_binding_counts[binding_name] += 1
            record["source_site"] = site_index
            record["source_direct_binding"] = binding
            records.append(record)
        expected_counts = _expected_access_counts(body)
        if observed_counts != expected_counts:
            raise Core0Error(
                f"Action function {source} LLVM memory-site closure differs from source: "
                f"{observed_counts!r} != {expected_counts!r}"
            )
        observed_ranges: dict[str, int] = {}
        for stem in _range_stems(function):
            site_index = int(stem.split(".")[1])
            site = source_by_index.get(site_index)
            if site is None or site.bits is not None:
                raise Core0Error(
                    f"Action function {source} LLVM {stem[:-1]} range does not match "
                    "its normalized memory site"
                )
            if site_index in observed_site_indices:
                raise Core0Error(
                    f"Action function {source} repeats LLVM memory site {site_index}"
                )
            observed_site_indices.add(site_index)
            range_record = _validate_one_range(function, stem)
            if site.access != range_record["access"]:
                raise Core0Error(
                    f"Action function {source} site {site_index} range access differs "
                    "from normalized source"
                )
            if site.length is None:
                raise Core0Error(
                    f"Action function {source} site {site_index} lacks a range length"
                )
            range_binding = {
                "region": _bind_direct_source_operand(
                    site.region,
                    str(range_record["region_operand"]),
                    signature,
                    "u8",
                    f"Action function {source} site {site_index} range region",
                ),
                "offset": _bind_direct_source_operand(
                    site.offset,
                    str(range_record["offset_operand"]),
                    signature,
                    "u64",
                    f"Action function {source} site {site_index} range offset",
                ),
                "range_length": _bind_direct_source_operand(
                    site.length,
                    str(range_record["requested_length"]),
                    signature,
                    "u64",
                    f"Action function {source} site {site_index} range length",
                ),
            }
            for binding_name, audited in range_binding.items():
                if audited:
                    source_binding_counts[binding_name] += 1
            range_record["source_site"] = site_index
            range_record["source_direct_binding"] = range_binding
            range_records.append(range_record)
            access = str(range_record["access"])
            observed_ranges[access] = observed_ranges.get(access, 0) + 1
        expected_ranges = _expected_range_counts(body)
        if observed_ranges != expected_ranges:
            raise Core0Error(
                f"Action function {source} LLVM range-site closure differs from source: "
                f"{observed_ranges!r} != {expected_ranges!r}"
            )
        expected_site_indices = set(range(len(source_sites)))
        if observed_site_indices != expected_site_indices:
            raise Core0Error(
                f"Action function {source} LLVM memory-site numbering differs from "
                f"normalized source: {sorted(observed_site_indices)!r} != "
                f"{sorted(expected_site_indices)!r}"
            )
    if not records:
        raise Core0Error("memory suite pre-optimization IR contains no audited RAM access")
    return {
        "access_count": len(records),
        "loads": sum(record["access"] == "read" for record in records),
        "stores": sum(record["access"] == "write" for record in records),
        "range_check_count": len(range_records),
        "read_ranges": sum(record["access"] == "read" for record in range_records),
        "write_ranges": sum(record["access"] == "write" for record in range_records),
        "source_memory_site_count": source_site_count,
        "direct_source_bindings": source_binding_counts,
        "volatile_policy": require_volatile,
        "accesses": records,
        "range_checks": range_records,
        "checked_result": checked_result,
    }


@dataclass(frozen=True)
class AuditMutation:
    name: str
    category: str
    manifest: dict[str, object] | None = None
    ir: str | None = None


def manifest_mutations(manifest: Mapping[str, object]) -> list[AuditMutation]:
    """Return one narrowly scoped mutation for every manifest/effect invariant."""
    result: list[AuditMutation] = []

    def add(name: str, category: str, mutate) -> None:  # type: ignore[no-untyped-def]
        value = copy.deepcopy(dict(manifest))
        mutate(value)
        result.append(AuditMutation(name, category, manifest=value))

    add("profile-version", "manifest", lambda value: value.__setitem__("contract_version", "core0-v0.3"))
    add(
        "region-base",
        "manifest",
        lambda value: value["memory_contract"]["regions"][0].__setitem__("base", 0x10000000),  # type: ignore[index]
    )
    add(
        "region-permission",
        "manifest",
        lambda value: value["memory_contract"]["regions"][1].__setitem__("write", True),  # type: ignore[index]
    )
    add(
        "region-width",
        "manifest",
        lambda value: value["memory_contract"]["regions"][3]["widths"].append(1),  # type: ignore[index,union-attr]
    )
    add(
        "region-kind",
        "manifest",
        lambda value: value["memory_contract"]["regions"][6].__setitem__("kind", "ordinary"),  # type: ignore[index]
    )
    add(
        "status-code",
        "manifest",
        lambda value: value["memory_contract"]["statuses"][7].__setitem__("code", 6),  # type: ignore[index]
    )
    add(
        "guard-order",
        "manifest",
        lambda value: value["memory_contract"]["guard_order"].reverse(),  # type: ignore[index,union-attr]
    )
    add(
        "volatile-policy",
        "manifest",
        lambda value: value["memory_contract"].__setitem__("successful_access_volatile", False),  # type: ignore[index,union-attr]
    )
    add(
        "checked-result-abi",
        "manifest",
        lambda value: value["checked_result"].__setitem__("llvm", "ptr"),  # type: ignore[index,union-attr]
    )
    add(
        "memory-op-identity",
        "source-closure",
        lambda value: value["used_memory_ops"][0].__setitem__("source_identity", "Forged.load"),  # type: ignore[index]
    )
    action_functions = manifest.get("action_functions", [])
    if isinstance(action_functions, list):
        direct_index = next(
            (
                index
                for index, function in enumerate(action_functions)
                if isinstance(function, dict) and function.get("direct_effects")
            ),
            None,
        )
    else:
        direct_index = None
    if direct_index is not None:
        add(
            "direct-effect",
            "effect",
            lambda value: value["action_functions"][direct_index].__setitem__("direct_effects", []),  # type: ignore[index]
        )
    if isinstance(action_functions, list) and len(action_functions) > 1:
        transitive_index = next(
            (
                index
                for index, function in enumerate(action_functions)
                if isinstance(function, dict)
                and function.get("action_dependencies")
                and function.get("transitive_effects")
            ),
            None,
        )
    else:
        transitive_index = None
    if transitive_index is not None:
        add(
            "transitive-effect",
            "effect",
            lambda value: value["action_functions"][transitive_index].__setitem__("transitive_effects", []),  # type: ignore[index]
        )
        add(
            "action-dependency",
            "source-closure",
            lambda value: value["action_functions"][transitive_index].__setitem__("action_dependencies", []),  # type: ignore[index]
        )
    roots = manifest.get("roots")
    if isinstance(roots, list) and len(roots) == len(CLOSED_ROOTS):
        add(
            "closed-root-catalog",
            "source-closure",
            lambda value: value["roots"][0]["signature"]["args"].append("u64"),  # type: ignore[index,union-attr]
        )
    if isinstance(action_functions, list) and len(action_functions) == 31:
        add(
            "closed-action-cardinality",
            "source-closure",
            lambda value: value["action_functions"].pop(),  # type: ignore[index,union-attr]
        )
    used_memory_ops = manifest.get("used_memory_ops")
    if isinstance(used_memory_ops, list) and len(used_memory_ops) == len(MEMORY_OPS):
        add(
            "closed-memory-operation-cardinality",
            "source-closure",
            lambda value: value["used_memory_ops"].pop(),  # type: ignore[index,union-attr]
        )
    action_iterations = manifest.get("action_iterations")
    if isinstance(action_iterations, list) and action_iterations:
        add(
            "action-iteration-contract",
            "source-closure",
            lambda value: value["action_iterations"][0].__setitem__("static_budget", 0),  # type: ignore[index]
        )
    used_primitives = manifest.get("used_primitives")
    if isinstance(used_primitives, list) and len(used_primitives) == len(CLOSED_USED_PRIMITIVES):
        add(
            "closed-scalar-primitive-catalog",
            "source-closure",
            lambda value: value["used_primitives"][0].__setitem__("stable_id", "forged"),  # type: ignore[index]
        )
    machine_primitives = manifest.get("machine_primitives")
    if isinstance(machine_primitives, list) and len(machine_primitives) == len(CLOSED_MACHINE_PRIMITIVES):
        add(
            "closed-machine-primitive-catalog",
            "manifest",
            lambda value: value["machine_primitives"][0].__setitem__("effect", "pure"),  # type: ignore[index]
        )
    return result


def _replace_first(source: str, before: str, after: str, name: str) -> str:
    count = source.count(before)
    if count < 1:
        raise Core0Error(f"cannot construct {name} mutation: anchor is absent")
    return source.replace(before, after, 1)


def _replace_in_function(
    ir: str,
    function: IRFunction,
    before: str,
    after: str,
    name: str,
) -> str:
    mutated_body = _replace_first(function.body, before, after, name)
    return _replace_first(ir, function.body, mutated_body, name)


def ir_mutations(ir: str) -> list[AuditMutation]:
    """Construct the closed compiler-defect matrix used by Gate 5 tests."""
    result: list[AuditMutation] = []

    def add(name: str, category: str, mutated: str) -> None:
        if mutated == ir:
            raise Core0Error(f"IR mutation {name} did not change its input")
        result.append(AuditMutation(name, category, ir=mutated))

    functions = parse_ir_functions(ir)
    selected: tuple[IRFunction, AccessRecord] | None = None
    for function in functions.values():
        accesses = _parse_accesses(function)
        if accesses:
            selected = function, accesses[0]
            break
    if selected is None:
        raise Core0Error("cannot build memory IR mutations without a load/store site")
    function, access = selected
    definitions = _definitions(function)
    context = f"mutation site {function.name}/{access.stem[:-1]}"
    width = access.bits // 8

    access_line = function.blocks[access.block][access.index]
    if " volatile " not in " " + access_line + " ":
        raise Core0Error(f"{context} is unexpectedly nonvolatile")
    add(
        "nonvolatile-access",
        "access",
        _replace_first(ir, access_line, access_line.replace(" volatile ", " ", 1), "nonvolatile-access"),
    )
    alternate_bits = 32 if access.bits == 64 else 64
    add(
        "wrong-access-width",
        "access",
        _replace_first(
            ir,
            access_line,
            access_line.replace(f"i{access.bits}", f"i{alternate_bits}", 1),
            "wrong-access-width",
        ),
    )
    access_alignment = access.bits // 8
    wrong_access_alignment = 2 if access_alignment == 1 else 1
    add(
        "wrong-access-alignment",
        "access",
        _replace_first(
            ir,
            access_line,
            access_line.replace(
                f"align {access_alignment}", f"align {wrong_access_alignment}", 1
            ),
            "wrong-access-alignment",
        ),
    )
    pointer_name = _semantic_name(definitions, access.stem, "pointer", context)
    add(
        "unaudited-extra-access",
        "source-closure",
        _replace_first(
            ir,
            access_line,
            f"%audit.unmodeled = load volatile i8, ptr %{pointer_name}, align 1\n  "
            + access_line,
            "unaudited-extra-access",
        ),
    )

    store_selected: tuple[IRFunction, AccessRecord] | None = None
    for candidate in functions.values():
        for candidate_access in _parse_accesses(candidate):
            if candidate_access.access == "write":
                store_selected = candidate, candidate_access
                break
        if store_selected is not None:
            break
    if store_selected is not None:
        store_function, store_access = store_selected
        assert store_access.value_operand is not None
        store_line = store_function.blocks[store_access.block][store_access.index]
        replacement_value = "0" if store_access.value_operand != "0" else "1"
        store_prefix = f"i{store_access.bits} {store_access.value_operand}, ptr"
        replacement_prefix = f"i{store_access.bits} {replacement_value}, ptr"
        if store_prefix not in store_line:
            raise Core0Error("cannot locate the selected store value operand")
        add(
            "wrong-source-store-value",
            "source-closure",
            _replace_in_function(
                ir,
                store_function,
                store_line,
                store_line.replace(store_prefix, replacement_prefix, 1),
                "wrong-source-store-value",
            ),
        )

    remaining_name = _semantic_name(definitions, access.stem, "remaining", context)
    length_name = _semantic_name(definitions, access.stem, "length-ok", context)
    offset_name = _semantic_name(definitions, access.stem, "offset-ok", context)
    mask_name = _semantic_name(definitions, access.stem, "alignment-mask", context)
    aligned_name = _semantic_name(definitions, access.stem, "alignment-ok", context)
    address_name = _semantic_name(definitions, access.stem, "address", context)
    permission_name = _semantic_name(definitions, access.stem, "permission-ok", context)
    width_name = _semantic_name(definitions, access.stem, "width-ok", context)
    class_name = _semantic_name(definitions, access.stem, "class-ok", context)

    length_line = definitions[length_name].line
    if " icmp ule " in length_line:
        wrong_length = length_line.replace(" icmp ule ", " icmp ugt ", 1)
    elif " icmp uge " in length_line:
        wrong_length = length_line.replace(" icmp uge ", " icmp ult ", 1)
    else:
        raise Core0Error(f"{context} has an unsupported length guard")
    add(
        "wrong-length-guard",
        "guard",
        _replace_first(ir, length_line, wrong_length, "wrong-length-guard"),
    )
    offset_line = definitions[offset_name].line
    add(
        "wrong-bounds-comparison",
        "guard",
        _replace_first(
            ir,
            offset_line,
            offset_line.replace(" icmp ule ", " icmp uge ", 1),
            "wrong-bounds-comparison",
        ),
    )
    mask_line = definitions[mask_name].line
    mask_match = re.fullmatch(r"(.+ = and i64 .+, )([0-9]+)", mask_line)
    if mask_match is None:
        raise Core0Error(f"{context} has an unsupported alignment mask")
    wrong_mask = (int(mask_match.group(2)) ^ 1) if width > 1 else 1
    add(
        "wrong-alignment-mask",
        "guard",
        _replace_first(
            ir,
            mask_line,
            mask_match.group(1) + str(wrong_mask),
            "wrong-alignment-mask",
        ),
    )
    remaining_line = definitions[remaining_name].line
    add(
        "subtraction-replaced-by-add",
        "guard",
        _replace_first(
            ir,
            remaining_line,
            remaining_line.replace(" = sub i64 ", " = add i64 ", 1),
            "subtraction-replaced-by-add",
        ),
    )
    offset_match = re.fullmatch(
        rf"%{re.escape(offset_name)} = icmp ule i64 ([^,]+), %{re.escape(remaining_name)}",
        offset_line,
    )
    if offset_match is None:
        raise Core0Error(f"{context} has an unsupported offset guard")
    wrap_line = f"%{access.stem}wrap-mutation = add i64 {offset_match.group(1)}, {width}"
    add(
        "wrap-prone-offset-plus-width",
        "guard",
        _replace_first(
            ir,
            remaining_line,
            wrap_line + "\n  " + remaining_line,
            "wrap-prone-offset-plus-width",
        ),
    )

    class_block, class_true, class_false = _branch_targets(function, class_name)
    permission_block, permission_true, permission_false = _branch_targets(
        function, permission_name
    )
    width_block, width_true, width_false = _branch_targets(function, width_name)
    aligned_block, aligned_true, aligned_false = _branch_targets(function, aligned_name)
    del class_block, permission_block, width_block, aligned_block
    permission_branch = (
        f"br i1 %{permission_name}, label %{permission_true}, label %{permission_false}"
    )
    add(
        "permission-bypass",
        "guard",
        _replace_first(
            ir,
            permission_branch,
            f"br i1 %{permission_name}, label %{permission_true}, label %{permission_true}",
            "permission-bypass",
        ),
    )
    aligned_branch = f"br i1 %{aligned_name}, label %{aligned_true}, label %{aligned_false}"
    add(
        "denied-path-access",
        "guard",
        _replace_first(
            ir,
            aligned_branch,
            f"br i1 %{aligned_name}, label %{aligned_true}, label %{aligned_true}",
            "denied-path-access",
        ),
    )

    class_branch = f"br i1 %{class_name}, label %{class_true}, label %{class_false}"
    width_branch = f"br i1 %{width_name}, label %{width_true}, label %{width_false}"
    reordered = _replace_first(
        ir,
        class_branch,
        f"br i1 %{class_name}, label %{permission_true}, label %{class_false}",
        "guard-order",
    )
    reordered = _replace_first(
        reordered,
        width_branch,
        f"br i1 %{width_name}, label %{class_true}, label %{width_false}",
        "guard-order",
    )
    reordered = _replace_first(
        reordered,
        permission_branch,
        f"br i1 %{permission_name}, label %{width_true}, label %{permission_false}",
        "guard-order",
    )
    add("guard-order", "guard", reordered)

    address_line = definitions[address_name].line
    replacement_offset = "0" if offset_match.group(1) != "0" else "1"
    offset_operand = offset_match.group(1)
    offset_selection_body = function.body
    for original_line in (offset_line, mask_line, address_line):
        replacement_line = original_line.replace(
            offset_operand, replacement_offset
        )
        if replacement_line == original_line:
            raise Core0Error(
                "cannot construct wrong-source-offset-selection mutation: "
                f"{offset_operand} is absent"
            )
        offset_selection_body = _replace_first(
            offset_selection_body,
            original_line,
            replacement_line,
            "wrong-source-offset-selection",
        )
    add(
        "wrong-source-offset-selection",
        "source-closure",
        _replace_first(
            ir,
            function.body,
            offset_selection_body,
            "wrong-source-offset-selection",
        ),
    )
    add(
        "forbidden-nuw",
        "poison",
        _replace_first(
            ir,
            address_line,
            address_line.replace(" = add i64 ", " = add nuw i64 ", 1),
            "forbidden-nuw",
        ),
    )

    dispatch_names = [
        name
        for name in definitions
        if re.fullmatch(re.escape(access.stem + "region-known") + r"\.[0-9]+", name)
    ]
    if dispatch_names:
        lookup_line = definitions[dispatch_names[0]].line
        lookup_match = re.fullmatch(r"(.+ = icmp eq i8 .+, )([0-9]+)", lookup_line)
        assert lookup_match is not None
        add(
            "wrong-region-lookup",
            "guard",
            _replace_first(
                ir,
                lookup_line,
                lookup_match.group(1) + "255",
                "wrong-region-lookup",
            ),
        )
        dispatch_operand_match = re.fullmatch(
            rf"%{re.escape(dispatch_names[0])} = icmp eq i8 "
            r"([^,]+), [0-9]+",
            lookup_line,
        )
        if dispatch_operand_match is None:
            raise Core0Error("cannot locate production region-dispatch operand")
        dispatch_operand = dispatch_operand_match.group(1).strip()
        replacement_region = "1" if dispatch_operand != "1" else "2"
        region_selection_body = function.body
        for dispatch_name in dispatch_names:
            dispatch_line = definitions[dispatch_name].line
            dispatch_match = re.fullmatch(
                rf"%{re.escape(dispatch_name)} = icmp eq i8 "
                rf"{re.escape(dispatch_operand)}, ([0-9]+)",
                dispatch_line,
            )
            if dispatch_match is None:
                raise Core0Error(
                    "cannot construct wrong-source-region-selection mutation"
                )
            region_selection_body = _replace_first(
                region_selection_body,
                dispatch_line,
                dispatch_line.replace(
                    f"i8 {dispatch_operand},",
                    f"i8 {replacement_region},",
                    1,
                ),
                "wrong-source-region-selection",
            )
        add(
            "wrong-source-region-selection",
            "source-closure",
            _replace_first(
                ir,
                function.body,
                region_selection_body,
                "wrong-source-region-selection",
            ),
        )

        if len(dispatch_names) < 2:
            raise Core0Error("production region dispatch has fewer than two IDs")
        first_block, first_true, first_false = _branch_targets(
            function, dispatch_names[0]
        )
        _second_block, second_true, _second_false = _branch_targets(
            function, dispatch_names[1]
        )
        first_route = function.blocks[first_block][-1]
        expected_first_route = (
            f"br i1 %{dispatch_names[0]}, label %{first_true}, label %{first_false}"
        )
        if first_route != expected_first_route:
            raise Core0Error("cannot locate first production region route")
        add(
            "wrong-region-true-route",
            "guard",
            _replace_in_function(
                ir,
                function,
                first_route,
                f"br i1 %{dispatch_names[0]}, label %{second_true}, "
                f"label %{first_false}",
                "wrong-region-true-route",
            ),
        )

        reserved_name = _semantic_name(
            definitions, access.stem, "class-is-reserved", context
        )
        reserved_block, reserved_true, reserved_false = _branch_targets(
            function, reserved_name
        )
        reserved_route = function.blocks[reserved_block][-1]
        expected_reserved_route = (
            f"br i1 %{reserved_name}, label %{reserved_true}, label %{reserved_false}"
        )
        if reserved_route != expected_reserved_route:
            raise Core0Error("cannot locate reserved/device control route")
        add(
            "reserved-device-control-inversion",
            "guard",
            _replace_in_function(
                ir,
                function,
                reserved_route,
                f"br i1 %{reserved_name}, label %{reserved_false}, "
                f"label %{reserved_true}",
                "reserved-device-control-inversion",
            ),
        )
        permission_line = definitions[permission_name].line
        permission_mutated = re.sub(r"\[\s*[01],", "[ 0,", permission_line, count=1)
        if permission_mutated == permission_line:
            permission_mutated = re.sub(r"\[\s*0,", "[ 1,", permission_line, count=1)
        add(
            "wrong-permission-metadata",
            "guard",
            _replace_first(
                ir,
                permission_line,
                permission_mutated,
                "wrong-permission-metadata",
            ),
        )
        width_line = definitions[width_name].line
        width_mutated = re.sub(r"\[\s*[01],", "[ 0,", width_line, count=1)
        if width_mutated == width_line:
            width_mutated = re.sub(r"\[\s*0,", "[ 1,", width_line, count=1)
        add(
            "wrong-width-metadata",
            "guard",
            _replace_first(ir, width_line, width_mutated, "wrong-width-metadata"),
        )

    range_selected: tuple[IRFunction, str] | None = None
    for candidate in functions.values():
        stems = _range_stems(candidate)
        if stems:
            range_selected = candidate, stems[0]
            break
    if range_selected is not None:
        range_function, range_stem = range_selected
        range_definitions = _definitions(range_function)
        range_context = f"range mutation site {range_function.name}/{range_stem[:-1]}"
        range_length_name = _semantic_name(
            range_definitions, range_stem, "length-ok", range_context
        )
        range_remaining_name = _semantic_name(
            range_definitions, range_stem, "remaining", range_context
        )
        range_offset_name = _semantic_name(
            range_definitions, range_stem, "offset-ok", range_context
        )
        range_length_line = range_definitions[range_length_name].line
        range_remaining_line = range_definitions[range_remaining_name].line
        range_offset_line = range_definitions[range_offset_name].line
        range_remaining = re.fullmatch(
            rf"%{re.escape(range_remaining_name)} = sub i64 ([^,]+), (.+)",
            range_remaining_line,
        )
        range_offset = re.fullmatch(
            rf"%{re.escape(range_offset_name)} = icmp ule i64 ([^,]+), "
            rf"%{re.escape(range_remaining_name)}",
            range_offset_line,
        )
        if range_remaining is None or range_offset is None:
            raise Core0Error(f"{range_context} has an unsupported range spelling")
        requested_length = range_remaining.group(2).strip()
        offset_operand = range_offset.group(1).strip()
        add(
            "range-wrong-length-guard",
            "guard",
            _replace_in_function(
                ir,
                range_function,
                range_length_line,
                range_length_line.replace(" icmp ule ", " icmp ugt ", 1),
                "range-wrong-length-guard",
            ),
        )
        add(
            "range-wrong-bounds-comparison",
            "guard",
            _replace_in_function(
                ir,
                range_function,
                range_offset_line,
                range_offset_line.replace(" icmp ule ", " icmp uge ", 1),
                "range-wrong-bounds-comparison",
            ),
        )
        add(
            "range-subtraction-replaced-by-add",
            "guard",
            _replace_in_function(
                ir,
                range_function,
                range_remaining_line,
                range_remaining_line.replace(" = sub i64 ", " = add i64 ", 1),
                "range-subtraction-replaced-by-add",
            ),
        )
        add(
            "range-wrap-prone-offset-plus-length",
            "guard",
            _replace_in_function(
                ir,
                range_function,
                range_remaining_line,
                f"%{range_stem}wrap-mutation = add i64 {offset_operand}, "
                f"{requested_length}\n  {range_remaining_line}",
                "range-wrap-prone-offset-plus-length",
            ),
        )
        add(
            "range-address-construction",
            "access",
            _replace_in_function(
                ir,
                range_function,
                range_remaining_line,
                f"%{range_stem}address.999999 = add i64 0, {offset_operand}\n  "
                + range_remaining_line,
                "range-address-construction",
            ),
        )

    status_match = re.search(
        r"(?P<line>%(?P<name>[A-Za-z_.$][A-Za-z0-9_.$-]*) = zext i8 [^\n]+ to i64)\n"
        r"\s+%[A-Za-z_.$][A-Za-z0-9_.$-]* = insertvalue \{ i64, i64 \} poison, "
        r"i64 %(?P=name), 0",
        ir,
    )
    if status_match is not None:
        status_line = status_match.group("line")
        add(
            "status-sign-extension",
            "abi",
            _replace_first(
                ir,
                status_line,
                status_line.replace(" = zext i8 ", " = sext i8 ", 1),
                "status-sign-extension",
            ),
        )
    status_insert = re.search(
        r"(?P<line>%[A-Za-z_.$][A-Za-z0-9_.$-]* = insertvalue "
        r"\{ i64, i64 \} poison, i64 [^,]+, 0)",
        ir,
    )
    if status_insert is not None:
        status_insert_line = status_insert.group("line")
        add(
            "checked-result-word-order",
            "abi",
            _replace_first(
                ir,
                status_insert_line,
                status_insert_line[:-1] + "1",
                "checked-result-word-order",
            ),
        )
    first_header = next(iter(functions.values())).header
    if " zeroext " in first_header:
        wrong_argument_header = first_header.replace(" zeroext ", " ", 1)
    elif " signext " in first_header:
        wrong_argument_header = first_header.replace(" signext ", " ", 1)
    else:
        wrong_argument_header = re.sub(
            r"i64 (%arg[0-9]+)", r"i32 signext \1", first_header, count=1
        )
    if wrong_argument_header != first_header:
        add(
            "argument-abi",
            "abi",
            _replace_first(ir, first_header, wrong_argument_header, "argument-abi"),
        )
    if first_header.startswith("define { i64, i64 } @"):
        add(
            "sret-result",
            "abi",
            _replace_first(
                ir,
                first_header,
                first_header.replace("define { i64, i64 } @", "define void @", 1),
                "sret-result",
            ),
        )
    call_match = re.search(r"call \{ i64, i64 \} @", ir)
    if call_match is not None:
        add(
            "indirect-action-call",
            "abi",
            ir[: call_match.start()]
            + call_match.group(0).replace(" @", " %")
            + ir[call_match.end() :],
        )
    direct_call = re.search(
        r"call \{ i64, i64 \} @([A-Za-z_.$][A-Za-z0-9_.$-]*)\(", ir
    )
    if direct_call is not None:
        original_callee = direct_call.group(1)
        replacement_callee = next(
            (name for name in functions if name != original_callee), None
        )
        if replacement_callee is not None:
            add(
                "wrong-direct-callee",
                "source-closure",
                ir[: direct_call.start(1)]
                + replacement_callee
                + ir[direct_call.end(1) :],
            )
    return result


def audit_mutation_matrix(
    manifest: Mapping[str, object],
    pre_ir: str,
    *,
    require_closed_suite: bool = True,
) -> list[dict[str, str]]:
    """Require every generated defect to fail in its intended audit layer."""
    records: list[dict[str, str]] = []
    for mutation in manifest_mutations(manifest):
        assert mutation.manifest is not None
        try:
            validate_memory_suite_manifest(
                mutation.manifest,
                require_closed_suite=require_closed_suite,
            )
        except Core0Error as error:
            records.append(
                {"name": mutation.name, "category": mutation.category, "diagnostic": str(error)}
            )
        else:
            raise Core0Error(f"memory manifest mutation {mutation.name} escaped detection")
    for mutation in ir_mutations(pre_ir):
        assert mutation.ir is not None
        try:
            validate_memory_pre_ir(
                manifest,
                mutation.ir,
                require_volatile=True,
            )
        except Core0Error as error:
            records.append(
                {"name": mutation.name, "category": mutation.category, "diagnostic": str(error)}
            )
        else:
            raise Core0Error(f"memory IR mutation {mutation.name} escaped detection")
    return records
