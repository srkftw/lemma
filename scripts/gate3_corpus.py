#!/usr/bin/env python3
"""Deterministic `core0-v0.2` scalar/CFG corpus and Lean oracle drivers.

This is host-only orchestration.  It emits invocations of ordinary elaborated
Lean declarations; it never constructs checked Core0 or LLVM IR itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCHEMA_VERSION = 1
PROFILE = "core0-v0.2"
TEST_ABI = "lemma-scalar-test-v1"
TARGET_CASE_COUNT = 708
DEFAULT_SOURCE_SEED = 0x4C454D4D41333033
DEFAULT_RUNTIME_SEED = 0x52554E54494D4533
U64_MASK = (1 << 64) - 1
HEX64 = re.compile(r"0x[0-9a-f]{16}\Z")
TYPES = ("bool", "u8", "u32", "u64")
TYPE_MAX = {
    "bool": 1,
    "u8": (1 << 8) - 1,
    "u32": (1 << 32) - 1,
    "u64": U64_MASK,
}
WIDTHS = {"u8": 8, "u32": 32, "u64": 64}
BOUNDARIES = {
    "bool": (0, 1),
    "u8": (0, 1, 2, 0x7F, 0x80, 0xFE, 0xFF, 0x55),
    "u32": (
        0,
        1,
        2,
        0x7FFFFFFF,
        0x80000000,
        0xFFFFFFFE,
        0xFFFFFFFF,
        0x55555555,
        0xAAAAAAAA,
    ),
    "u64": (
        0,
        1,
        2,
        0x7FFFFFFFFFFFFFFF,
        0x8000000000000000,
        0xFFFFFFFFFFFFFFFE,
        0xFFFFFFFFFFFFFFFF,
        0x5555555555555555,
        0xAAAAAAAAAAAAAAAA,
    ),
}


class CorpusError(ValueError):
    """Raised when a Gate 3 corpus fails closed validation."""


@dataclass(frozen=True)
class RootSpec:
    name: str
    args: tuple[str, ...]
    result: str
    case_count: int
    covers: tuple[str, ...]
    operation: str
    width: int
    form: str

    @property
    def signature(self) -> dict[str, object]:
        return {"args": list(self.args), "result": self.result}


BASE = "Lemma.Examples.Foundation.ScalarV2"
TYPE_PARTS = (("u8", 8, "u8"), ("u32", 32, "u32"), ("u64", 64, "u64"))
OPERATIONS = (
    ("complement", "Complement", 8),
    ("shl", "Shl", 18),
    ("lshr", "Shr", 18),
    ("udiv", "Div", 18),
    ("urem", "Rem", 18),
)


def _primitive_name(type_part: str, operation_part: str, form: str) -> str:
    return f"{BASE}.{type_part}{operation_part}{form}"


def _catalog() -> tuple[RootSpec, ...]:
    roots: list[RootSpec] = []
    for ty, width, type_part in TYPE_PARTS:
        for operation, operation_part, count in OPERATIONS:
            args = (ty,) if operation == "complement" else (ty, ty)
            for form in ("Notation", "Direct"):
                roots.append(
                    RootSpec(
                        name=_primitive_name(type_part, operation_part, form),
                        args=args,
                        result=ty,
                        case_count=count,
                        covers=(
                            f"{ty}.{operation}",
                            "notation" if form == "Notation" else "direct-identity",
                        ),
                        operation=operation,
                        width=width,
                        form=form.lower(),
                    )
                )
    for result, ty, width in (
        ("bool", "u8", 8),
        ("u8", "u8", 8),
        ("u32", "u32", 32),
        ("u64", "u64", 64),
    ):
        roots.append(
            RootSpec(
                name=f"{BASE}.cfg{result[0].upper() + result[1:]}",
                args=("bool", "bool", ty, ty, ty),
                result=result,
                case_count=24,
                covers=(
                    "structured-cfg",
                    "branch-dependent-dangerous-operation",
                    "helper-call",
                    f"{result}-result",
                ),
                operation="cfg",
                width=width,
                form="helper",
            )
        )
    roots.append(
        RootSpec(
            name=f"{BASE}.nestedHelperCall",
            args=("bool", "bool", "bool", "u64", "u64", "u64"),
            result="u64",
            case_count=24,
            covers=(
                "structured-cfg",
                "nested-conditional",
                "branch-dependent-dangerous-operation",
                "cross-module-helper-call",
            ),
            operation="nested-cfg",
            width=64,
            form="helper",
        )
    )
    for ty, width, type_part in TYPE_PARTS:
        roots.append(
            RootSpec(
                name=f"{BASE}.{type_part}LegacyArithmetic",
                args=(ty, ty, ty),
                result=ty,
                case_count=12,
                covers=(
                    "retained-v0.1",
                    *(f"{ty}.{operation}" for operation in ("add", "sub", "mul", "and", "or", "xor")),
                ),
                operation="legacy-arithmetic",
                width=width,
                form="retained-v0.1",
            )
        )
    for ty, width, type_part in TYPE_PARTS:
        roots.append(
            RootSpec(
                name=f"{BASE}.{type_part}LegacyCompare",
                args=("bool", "bool", ty, ty, ty),
                result=ty,
                case_count=12,
                covers=(
                    "retained-v0.1",
                    "bool.eq",
                    f"{ty}.eq",
                    f"{ty}.ult",
                    f"{ty}.ule",
                ),
                operation="legacy-compare",
                width=width,
                form="retained-v0.1",
            )
        )
    cast_coverage = {
        "u8": ("u8.to-u32.zext", "u8.to-u64.zext"),
        "u32": ("u32.to-u8.trunc", "u32.to-u64.zext"),
        "u64": ("u64.to-u8.trunc", "u64.to-u32.trunc"),
    }
    for ty, width, type_part in TYPE_PARTS:
        roots.append(
            RootSpec(
                name=f"{BASE}.{type_part}LegacyCasts",
                args=(ty,),
                result="u64",
                case_count=12,
                covers=("retained-v0.1", *cast_coverage[ty]),
                operation="legacy-casts",
                width=width,
                form="retained-v0.1",
            )
        )
    return tuple(roots)


ROOT_SPECS = _catalog()


def _retained_primitive_witnesses() -> tuple[tuple[str, str], ...]:
    witnesses: list[tuple[str, str]] = []
    for ty, _, type_part in TYPE_PARTS:
        arithmetic_root = f"{BASE}.{type_part}LegacyArithmetic"
        compare_root = f"{BASE}.{type_part}LegacyCompare"
        witnesses.extend(
            (f"{ty}.{operation}", arithmetic_root)
            for operation in ("add", "sub", "mul", "and", "or", "xor")
        )
        witnesses.extend(
            (f"{ty}.{operation}", compare_root)
            for operation in ("ult", "ule", "eq")
        )
    witnesses.append(("bool.eq", f"{BASE}.u8LegacyCompare"))
    witnesses.extend(
        (
            ("u8.to-u32.zext", f"{BASE}.u8LegacyCasts"),
            ("u8.to-u64.zext", f"{BASE}.u8LegacyCasts"),
            ("u32.to-u8.trunc", f"{BASE}.u32LegacyCasts"),
            ("u32.to-u64.zext", f"{BASE}.u32LegacyCasts"),
            ("u64.to-u8.trunc", f"{BASE}.u64LegacyCasts"),
            ("u64.to-u32.trunc", f"{BASE}.u64LegacyCasts"),
        )
    )
    return tuple(witnesses)


RETAINED_PRIMITIVE_WITNESSES = _retained_primitive_witnesses()


def _metamorphic_pairs() -> tuple[tuple[str, str, str], ...]:
    pairs: list[tuple[str, str, str]] = []
    for ty, _, type_part in TYPE_PARTS:
        for operation, operation_part, _ in OPERATIONS:
            pairs.append(
                (
                    f"{ty}.{operation}.notation-direct",
                    _primitive_name(type_part, operation_part, "Notation"),
                    _primitive_name(type_part, operation_part, "Direct"),
                )
            )
    return tuple(pairs)


METAMORPHIC_PAIRS = _metamorphic_pairs()


class SplitMix64:
    def __init__(self, seed: int):
        self.state = seed & U64_MASK

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & U64_MASK
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & U64_MASK
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & U64_MASK
        return (value ^ (value >> 31)) & U64_MASK


def _hex64(value: int) -> str:
    return f"0x{value:016x}"


def _seed_for(seed: int, label: str) -> int:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    return seed ^ int.from_bytes(digest[:8], "little")


def _shuffle(values: Sequence[RootSpec], seed: int) -> list[RootSpec]:
    shuffled = list(values)
    rng = SplitMix64(seed)
    for index in range(len(shuffled) - 1, 0, -1):
        selected = rng.next() % (index + 1)
        shuffled[index], shuffled[selected] = shuffled[selected], shuffled[index]
    return shuffled


def _append_unique(
    values: list[tuple[tuple[int, ...], str]], vector: Iterable[int], label: str
) -> None:
    item = tuple(vector)
    if all(existing != item for existing, _ in values):
        values.append((item, label))


def _primitive_edges(spec: RootSpec) -> list[tuple[tuple[int, ...], str]]:
    ty = spec.args[0]
    maximum = TYPE_MAX[ty]
    width = spec.width
    alternate = maximum // 3
    high_bit = 1 << (width - 1)
    values: list[tuple[tuple[int, ...], str]] = []
    if spec.operation == "complement":
        labels = (
            "minimum",
            "one",
            "two",
            "signed-boundary-minus-one",
            "high-bit",
            "maximum-minus-one",
            "maximum",
            "alternating",
        )
        for value, label in zip(BOUNDARIES[ty][:8], labels, strict=True):
            _append_unique(values, (value,), f"edge:{label}")
        return values
    if spec.operation in ("shl", "lshr"):
        for vector, label in (
            ((0, 0), "zero-value-zero-count"),
            ((maximum, 0), "maximum-value-zero-count"),
            ((0, maximum), "zero-value-very-large-count"),
            ((1, width - 1), "shift-count-width-minus-one"),
            ((1, width), "shift-count-width"),
            ((1, width + 1), "shift-count-width-plus-one"),
            ((maximum, width - 1), "maximum-shift-width-minus-one"),
            ((maximum, width), "maximum-shift-width"),
            ((maximum, width + 1), "maximum-shift-width-plus-one"),
            ((alternate, width - 1), "alternate-shift-width-minus-one"),
            ((alternate, width), "alternate-shift-width"),
            ((alternate, width + 1), "alternate-shift-width-plus-one"),
            ((high_bit, maximum), "high-bit-very-large-count"),
            ((2, maximum), "small-value-very-large-count"),
        ):
            _append_unique(values, vector, f"edge:{label}")
        return values
    if spec.operation in ("udiv", "urem"):
        for vector, label in (
            ((0, 0), "zero-numerator-zero-divisor"),
            ((0, 1), "zero-numerator-unit-divisor"),
            ((0, maximum), "zero-numerator-maximum-divisor"),
            ((1, 0), "unit-numerator-zero-divisor"),
            ((1, 1), "unit-by-unit"),
            ((1, maximum), "unit-by-maximum"),
            ((maximum, 0), "maximum-numerator-zero-divisor"),
            ((maximum, 1), "maximum-by-unit"),
            ((maximum, maximum), "maximum-by-maximum"),
            ((maximum, 2), "maximum-by-two"),
            ((maximum, maximum - 1), "maximum-by-maximum-minus-one"),
            ((high_bit, 2), "high-bit-by-two"),
            ((alternate, 3), "alternate-by-three"),
            ((2, high_bit), "small-by-high-bit"),
        ):
            _append_unique(values, vector, f"edge:{label}")
        return values
    raise AssertionError(f"unexpected primitive operation {spec.operation}")


def _cfg_edges(spec: RootSpec) -> list[tuple[tuple[int, ...], str]]:
    maximum = (1 << spec.width) - 1
    alternate = maximum // 3
    values: list[tuple[tuple[int, ...], str]] = []
    if spec.operation == "cfg":
        for arithmetic in (0, 1):
            for quotient in (0, 1):
                stem = f"a{arithmetic}-q{quotient}"
                for vector, label in (
                    ((0, 0, 0), "zero-divisor-zero-count"),
                    ((maximum, 0, spec.width), "maximum-zero-divisor-width"),
                    ((0, 1, spec.width + 1), "zero-numerator-width-plus-one"),
                    ((maximum, maximum, maximum), "maximums-very-large-count"),
                    ((1, maximum, spec.width - 1), "unit-maximum-width-minus-one"),
                    ((alternate, 2, spec.width + 1), "alternate-two-width-plus-one"),
                ):
                    _append_unique(
                        values,
                        (arithmetic, quotient, *vector),
                        f"edge:cfg-{stem}-{label}",
                    )
        return values
    if spec.operation == "nested-cfg":
        for selector in range(8):
            outer = (selector >> 2) & 1
            arithmetic = (selector >> 1) & 1
            quotient = selector & 1
            stem = f"o{outer}-a{arithmetic}-q{quotient}"
            count = spec.width + 1 if selector % 2 == 0 else maximum
            low_count = 0 if selector == 0 else spec.width - 1
            for vector, label in (
                ((0, 0, low_count), "zero-divisor-low-count"),
                ((maximum, 0, spec.width), "maximum-zero-divisor-width"),
                ((alternate, maximum, count), "alternate-maximum-large-count"),
            ):
                _append_unique(
                    values,
                    (outer, arithmetic, quotient, *vector),
                    f"edge:nested-{stem}-{label}",
                )
        return values
    raise AssertionError(f"unexpected CFG operation {spec.operation}")


def _retained_edges(spec: RootSpec) -> list[tuple[tuple[int, ...], str]]:
    ty = next(ty for ty in spec.args if ty != "bool")
    maximum = TYPE_MAX[ty]
    high_bit = 1 << (spec.width - 1)
    alternate = maximum // 3
    inverse_alternate = (2 * maximum) // 3
    values: list[tuple[tuple[int, ...], str]] = []
    if spec.operation == "legacy-arithmetic":
        vectors = (
            ((0, 0, 0), "all-zero"),
            ((maximum, maximum, maximum), "all-maximum"),
            ((1, 2, 3), "small-distinct"),
            ((maximum, 0, 1), "maximum-zero-one"),
            ((0, maximum, 1), "zero-maximum-one"),
            ((1, 0, maximum), "one-zero-maximum"),
            ((high_bit, maximum, alternate), "high-bit-maximum-alternate"),
            ((maximum - 1, high_bit, 2), "maximum-minus-one-high-bit-two"),
            ((alternate, inverse_alternate, maximum - 1), "alternating-patterns"),
            ((2, maximum - 1, high_bit), "two-maximum-minus-one-high-bit"),
            ((high_bit, 1, maximum), "high-bit-one-maximum"),
            ((maximum, high_bit, 0), "maximum-high-bit-zero"),
        )
    elif spec.operation == "legacy-compare":
        vectors = (
            ((0, 0, 0, 0, 0), "bool-equal-all-zero"),
            ((0, 1, 0, maximum, 0), "bool-unequal-zero-maximum"),
            ((1, 0, maximum, 0, maximum), "bool-unequal-maximum-zero"),
            ((1, 1, maximum, maximum, maximum), "bool-equal-all-maximum"),
            ((0, 0, 1, 1, 0), "integer-equal"),
            ((1, 1, 0, 1, 1), "integer-less"),
            ((0, 0, maximum, 1, maximum), "integer-less-or-equal-third"),
            ((1, 1, high_bit, high_bit, 0), "high-bit-equal"),
            ((0, 1, alternate, inverse_alternate, maximum), "alternating-unequal-bools"),
            ((1, 0, maximum - 1, maximum, 0), "near-maximum-unequal-bools"),
            ((0, 0, 2, 1, 2), "third-equality-boundary"),
            ((1, 1, 1, 2, 1), "ordered-small-values"),
        )
    elif spec.operation == "legacy-casts":
        vectors = tuple(
            ((value,), label)
            for value, label in (
                (0, "minimum"),
                (1, "one"),
                (2, "two"),
                (3, "three"),
                (maximum // 4, "quarter-minus-one"),
                (maximum // 4 + 1, "quarter"),
                (alternate, "alternating-low"),
                (high_bit - 1, "high-bit-minus-one"),
                (high_bit, "high-bit"),
                (inverse_alternate, "alternating-high"),
                (maximum - 1, "maximum-minus-one"),
                (maximum, "maximum"),
            )
        )
    else:
        raise AssertionError(f"unexpected retained operation {spec.operation}")
    for vector, label in vectors:
        _append_unique(values, vector, f"edge:retained-{label}")
    return values


def _vectors(spec: RootSpec, seed: int) -> list[tuple[tuple[int, ...], str]]:
    if spec.operation in ("cfg", "nested-cfg"):
        values = _cfg_edges(spec)
    elif spec.operation.startswith("legacy-"):
        values = _retained_edges(spec)
    else:
        values = _primitive_edges(spec)
    rng = SplitMix64(seed)
    while len(values) < spec.case_count:
        vector = tuple(rng.next() & TYPE_MAX[ty] for ty in spec.args)
        _append_unique(values, vector, "seeded-runtime")
    if len(values) != spec.case_count:
        raise AssertionError(
            f"edge catalog for {spec.name} exceeds its {spec.case_count}-case allocation"
        )
    return values


def _suite_id(source_seed: int, runtime_seed: int) -> str:
    catalog = [
        [spec.name, list(spec.args), spec.result, spec.case_count, list(spec.covers)]
        for spec in ROOT_SPECS
    ]
    encoded = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "profile": PROFILE,
            "test_abi": TEST_ABI,
            "source_seed": _hex64(source_seed),
            "runtime_seed": _hex64(runtime_seed),
            "catalog": catalog,
            "retained_primitive_coverage": list(RETAINED_PRIMITIVE_WITNESSES),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _hex64(int.from_bytes(hashlib.sha256(encoded).digest()[:8], "little"))


def build_corpus(
    *,
    source_seed: int = DEFAULT_SOURCE_SEED,
    runtime_seed: int = DEFAULT_RUNTIME_SEED,
) -> dict[str, object]:
    if not 0 <= source_seed <= U64_MASK or not 0 <= runtime_seed <= U64_MASK:
        raise CorpusError("source and runtime seeds must be UInt64 values")
    if sum(spec.case_count for spec in ROOT_SPECS) != TARGET_CASE_COUNT:
        raise AssertionError("internal Gate 3 root distribution does not total 708")

    specs = {spec.name: spec for spec in ROOT_SPECS}
    paired_vectors: dict[str, list[tuple[tuple[int, ...], str]]] = {}
    for pair_name, left, right in METAMORPHIC_PAIRS:
        left_spec, right_spec = specs[left], specs[right]
        if (
            left_spec.args,
            left_spec.result,
            left_spec.case_count,
            left_spec.operation,
        ) != (
            right_spec.args,
            right_spec.result,
            right_spec.case_count,
            right_spec.operation,
        ):
            raise AssertionError(f"metamorphic pair {pair_name} has inconsistent descriptors")
        vectors = _vectors(
            left_spec,
            _seed_for(runtime_seed, "metamorphic:" + pair_name),
        )
        paired_vectors[left] = vectors
        paired_vectors[right] = vectors

    cases: list[dict[str, object]] = []
    next_case_id = 1
    for spec in _shuffle(ROOT_SPECS, source_seed):
        vectors = paired_vectors.get(spec.name)
        if vectors is None:
            vectors = _vectors(
                spec,
                _seed_for(runtime_seed, "root:" + spec.name),
            )
        for vector, edge_label in vectors:
            cases.append(
                {
                    "case_id": _hex64(next_case_id),
                    "root": spec.name,
                    "signature": spec.signature,
                    "args": [
                        {"type": ty, "value": _hex64(value)}
                        for ty, value in zip(spec.args, vector, strict=True)
                    ],
                    "expected_result_type": spec.result,
                    "covers": [edge_label, *spec.covers],
                }
            )
            next_case_id += 1

    corpus: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "test_abi": TEST_ABI,
        "suite_id": _suite_id(source_seed, runtime_seed),
        "source_seed": _hex64(source_seed),
        "runtime_seed": _hex64(runtime_seed),
        "case_count": len(cases),
        "roots": [
            {
                "name": spec.name,
                "signature": spec.signature,
                "case_count": spec.case_count,
                "covers": list(spec.covers),
            }
            for spec in ROOT_SPECS
        ],
        "primitive_coverage": [
            {
                "stable_id": f"{ty}.{operation}",
                "notation_root": _primitive_name(type_part, operation_part, "Notation"),
                "direct_root": _primitive_name(type_part, operation_part, "Direct"),
            }
            for ty, _, type_part in TYPE_PARTS
            for operation, operation_part, _ in OPERATIONS
        ],
        "retained_primitive_coverage": [
            {"stable_id": stable_id, "witness_root": witness_root}
            for stable_id, witness_root in RETAINED_PRIMITIVE_WITNESSES
        ],
        "metamorphic_pairs": [
            {"name": name, "left": left, "right": right}
            for name, left, right in METAMORPHIC_PAIRS
        ],
        "cases": cases,
    }
    validate_corpus(corpus)
    return corpus


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CorpusError(
            f"{context} fields differ from schema: "
            f"missing={sorted(expected - observed)!r}, unexpected={sorted(observed - expected)!r}"
        )


def _parse_hex64(value: object, context: str) -> int:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise CorpusError(f"{context} must be a canonical string-encoded UInt64")
    return int(value, 16)


def _validate_signature(value: object, context: str) -> tuple[tuple[str, ...], str]:
    if not isinstance(value, dict):
        raise CorpusError(f"{context} is not an object")
    _exact_keys(value, {"args", "result"}, context)
    args, result = value.get("args"), value.get("result")
    if (
        not isinstance(args, list)
        or any(not isinstance(ty, str) or ty not in TYPES for ty in args)
        or not isinstance(result, str)
        or result not in TYPES
    ):
        raise CorpusError(f"{context} contains an unknown scalar type")
    return tuple(args), result


def _expected_primitive_coverage() -> list[dict[str, str]]:
    return [
        {
            "stable_id": f"{ty}.{operation}",
            "notation_root": _primitive_name(type_part, operation_part, "Notation"),
            "direct_root": _primitive_name(type_part, operation_part, "Direct"),
        }
        for ty, _, type_part in TYPE_PARTS
        for operation, operation_part, _ in OPERATIONS
    ]


def _expected_retained_primitive_coverage() -> list[dict[str, str]]:
    return [
        {"stable_id": stable_id, "witness_root": witness_root}
        for stable_id, witness_root in RETAINED_PRIMITIVE_WITNESSES
    ]


def validate_corpus(value: object) -> None:
    if not isinstance(value, dict):
        raise CorpusError("Gate 3 corpus is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "profile",
            "test_abi",
            "suite_id",
            "source_seed",
            "runtime_seed",
            "case_count",
            "roots",
            "primitive_coverage",
            "retained_primitive_coverage",
            "metamorphic_pairs",
            "cases",
        },
        "Gate 3 corpus",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CorpusError("Gate 3 corpus has an unsupported schema")
    if value.get("profile") != PROFILE or value.get("test_abi") != TEST_ABI:
        raise CorpusError("Gate 3 corpus profile/test ABI is unsupported")
    source_seed = _parse_hex64(value.get("source_seed"), "source_seed")
    runtime_seed = _parse_hex64(value.get("runtime_seed"), "runtime_seed")
    if value.get("suite_id") != _suite_id(source_seed, runtime_seed):
        raise CorpusError("Gate 3 suite_id is stale or inconsistent with seeds/catalog/profile")
    if value.get("case_count") != TARGET_CASE_COUNT:
        raise CorpusError(f"Gate 3 corpus must contain exactly {TARGET_CASE_COUNT} cases")

    expected_specs = {spec.name: spec for spec in ROOT_SPECS}
    roots = value.get("roots")
    if not isinstance(roots, list):
        raise CorpusError("Gate 3 roots must be an array")
    observed_roots: dict[str, int] = {}
    for index, item in enumerate(roots):
        if not isinstance(item, dict):
            raise CorpusError(f"Gate 3 root #{index} is not an object")
        _exact_keys(item, {"name", "signature", "case_count", "covers"}, f"Gate 3 root #{index}")
        name = item.get("name")
        if not isinstance(name, str) or name not in expected_specs or name in observed_roots:
            raise CorpusError(f"Gate 3 root #{index} is unknown or duplicated")
        spec = expected_specs[name]
        if _validate_signature(item.get("signature"), f"Gate 3 root {name} signature") != (
            spec.args,
            spec.result,
        ):
            raise CorpusError(f"Gate 3 root {name} signature differs from the exact catalog")
        if item.get("case_count") != spec.case_count:
            raise CorpusError(f"Gate 3 root {name} has the wrong case allocation")
        if item.get("covers") != list(spec.covers):
            raise CorpusError(f"Gate 3 root {name} coverage labels differ from the exact catalog")
        observed_roots[name] = 0
    if set(observed_roots) != set(expected_specs):
        raise CorpusError("Gate 3 root catalog is incomplete")

    if value.get("primitive_coverage") != _expected_primitive_coverage():
        raise CorpusError("Gate 3 primitive coverage catalog is incomplete or reordered")
    if value.get("retained_primitive_coverage") != _expected_retained_primitive_coverage():
        raise CorpusError("Gate 3 retained-v0.1 primitive catalog is incomplete or reordered")

    pairs = value.get("metamorphic_pairs")
    expected_pairs = [
        {"name": name, "left": left, "right": right}
        for name, left, right in METAMORPHIC_PAIRS
    ]
    if pairs != expected_pairs:
        raise CorpusError("Gate 3 metamorphic pair catalog is incomplete or reordered")

    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != TARGET_CASE_COUNT:
        raise CorpusError(f"Gate 3 corpus must contain exactly {TARGET_CASE_COUNT} case objects")
    ids: set[int] = set()
    root_vectors: dict[str, list[tuple[int, tuple[int, ...]]]] = {
        name: [] for name in expected_specs
    }
    unique_vectors: set[tuple[str, tuple[int, ...]]] = set()
    expected_case_keys = {
        "case_id",
        "root",
        "signature",
        "args",
        "expected_result_type",
        "covers",
    }
    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            raise CorpusError(f"Gate 3 case #{index} is not an object")
        _exact_keys(item, expected_case_keys, f"Gate 3 case #{index}")
        case_id = _parse_hex64(item.get("case_id"), f"Gate 3 case #{index} id")
        if case_id == 0 or case_id in ids:
            raise CorpusError(f"Gate 3 case #{index} has a zero or duplicate case ID")
        ids.add(case_id)
        name = item.get("root")
        if not isinstance(name, str) or name not in expected_specs:
            raise CorpusError(f"Gate 3 case #{index} names an unknown root")
        spec = expected_specs[name]
        if _validate_signature(item.get("signature"), f"Gate 3 case #{index} signature") != (
            spec.args,
            spec.result,
        ):
            raise CorpusError(f"Gate 3 case #{index} signature differs from its root")
        if item.get("expected_result_type") != spec.result:
            raise CorpusError(f"Gate 3 case #{index} has the wrong expected result type")
        args = item.get("args")
        if not isinstance(args, list) or len(args) != len(spec.args):
            raise CorpusError(f"Gate 3 case #{index} has the wrong argument count")
        vector: list[int] = []
        for arg_index, (argument, expected_type) in enumerate(zip(args, spec.args, strict=True)):
            if not isinstance(argument, dict):
                raise CorpusError(f"Gate 3 case #{index} argument #{arg_index} is not an object")
            _exact_keys(argument, {"type", "value"}, f"Gate 3 case #{index} argument #{arg_index}")
            if argument.get("type") != expected_type:
                raise CorpusError(f"Gate 3 case #{index} argument #{arg_index} has the wrong type")
            number = _parse_hex64(
                argument.get("value"), f"Gate 3 case #{index} argument #{arg_index} value"
            )
            if number > TYPE_MAX[expected_type]:
                raise CorpusError(
                    f"Gate 3 case #{index} argument #{arg_index} is outside {expected_type}"
                )
            vector.append(number)
        covers = item.get("covers")
        if (
            not isinstance(covers, list)
            or len(covers) != len(spec.covers) + 1
            or not isinstance(covers[0], str)
            or (not covers[0].startswith("edge:") and covers[0] != "seeded-runtime")
            or covers[1:] != list(spec.covers)
        ):
            raise CorpusError(f"Gate 3 case #{index} has invalid coverage labels")
        vector_key = (name, tuple(vector))
        if vector_key in unique_vectors:
            raise CorpusError(f"Gate 3 case #{index} duplicates a (root,args) vector")
        unique_vectors.add(vector_key)
        observed_roots[name] += 1
        root_vectors[name].append((case_id, tuple(vector)))

    if ids != set(range(1, TARGET_CASE_COUNT + 1)):
        raise CorpusError("Gate 3 case IDs must be the complete canonical 1..708 range")
    if observed_roots != {spec.name: spec.case_count for spec in ROOT_SPECS}:
        raise CorpusError("Gate 3 root coverage/case distribution is incomplete")

    for spec in ROOT_SPECS:
        vectors = [vector for _, vector in root_vectors[spec.name]]
        for arg_index, ty in enumerate(spec.args):
            seen = {vector[arg_index] for vector in vectors}
            if 0 not in seen or TYPE_MAX[ty] not in seen:
                raise CorpusError(
                    f"Gate 3 root {spec.name} lacks min/max coverage for argument #{arg_index}"
                )
        if spec.operation in ("shl", "lshr"):
            counts = {vector[1] for vector in vectors}
            required = {spec.width - 1, spec.width, spec.width + 1, TYPE_MAX[spec.args[1]]}
            if not required.issubset(counts):
                raise CorpusError(f"Gate 3 shift root {spec.name} lacks required count edges")
        if spec.operation in ("udiv", "urem"):
            if not any(vector[0] == 0 for vector in vectors) or not any(
                vector[1] == 0 for vector in vectors
            ):
                raise CorpusError(f"Gate 3 division root {spec.name} lacks zero edges")
        if spec.operation in ("cfg", "nested-cfg"):
            divisor_index = len(spec.args) - 2
            count_index = len(spec.args) - 1
            divisors = {vector[divisor_index] for vector in vectors}
            counts = {vector[count_index] for vector in vectors}
            required_counts = {
                spec.width - 1,
                spec.width,
                spec.width + 1,
                TYPE_MAX[spec.args[count_index]],
            }
            if 0 not in divisors or not required_counts.issubset(counts):
                raise CorpusError(f"Gate 3 CFG root {spec.name} lacks dangerous-operation edges")

    for pair_name, left, right in METAMORPHIC_PAIRS:
        left_vectors = [vector for _, vector in sorted(root_vectors[left])]
        right_vectors = [vector for _, vector in sorted(root_vectors[right])]
        if left_vectors != right_vectors:
            raise CorpusError(f"metamorphic pair {pair_name} does not use identical input vectors")


def _case_values(case: dict[str, object]) -> list[tuple[str, int]]:
    args = case["args"]
    assert isinstance(args, list)
    values: list[tuple[str, int]] = []
    for argument in args:
        assert isinstance(argument, dict)
        values.append((str(argument["type"]), int(str(argument["value"]), 16)))
    return values


def _lean_literal(ty: str, value: int) -> str:
    if ty == "bool":
        return "true" if value else "false"
    names = {"u8": "UInt8", "u32": "UInt32", "u64": "UInt64"}
    return f"({value} : {names[ty]})"


def render_direct_driver(corpus: dict[str, object]) -> str:
    validate_corpus(corpus)
    lines = [
        "import examples.foundation.ScalarV2Conformance",
        "",
        "/- Generated direct-source oracle: deliberately no Core0 import/evaluator. -/",
        f"-- profile: {PROFILE}",
        f"-- suite_id: {corpus['suite_id']}",
        f"-- source_seed: {corpus['source_seed']}",
        f"-- runtime_seed: {corpus['runtime_seed']}",
        "",
        "private def gate3EmitNat (caseId : Nat) (tag : String) (value : Nat) : IO Unit :=",
        '  IO.println s!"LEAN_TYPED_SOURCE:{caseId}:{tag}:{value}"',
        "",
        "private def gate3EmitBool (caseId : Nat) (value : Bool) : IO Unit :=",
        '  gate3EmitNat caseId "bool" (if value then 1 else 0)',
        "",
        "private def gate3EmitU8 (caseId : Nat) (value : UInt8) : IO Unit :=",
        '  gate3EmitNat caseId "u8" value.toNat',
        "",
        "private def gate3EmitU32 (caseId : Nat) (value : UInt32) : IO Unit :=",
        '  gate3EmitNat caseId "u32" value.toNat',
        "",
        "private def gate3EmitU64 (caseId : Nat) (value : UInt64) : IO Unit :=",
        '  gate3EmitNat caseId "u64" value.toNat',
        "",
    ]
    emitters = {
        "bool": "gate3EmitBool",
        "u8": "gate3EmitU8",
        "u32": "gate3EmitU32",
        "u64": "gate3EmitU64",
    }
    cases = corpus["cases"]
    assert isinstance(cases, list)
    chunk_names: list[str] = []
    for chunk_index, start in enumerate(range(0, len(cases), 64)):
        chunk_name = f"gate3DirectChunk{chunk_index}"
        chunk_names.append(chunk_name)
        lines.append(f"private def {chunk_name} : IO Unit := do")
        for case in cases[start : start + 64]:
            assert isinstance(case, dict)
            case_id = int(str(case["case_id"]), 16)
            root = str(case["root"])
            result_type = str(case["expected_result_type"])
            arguments = " ".join(
                _lean_literal(ty, number) for ty, number in _case_values(case)
            )
            lines.append(f"  {emitters[result_type]} {case_id} ({root} {arguments})")
        lines.append("")
    lines.append("def main : IO Unit := do")
    for chunk_name in chunk_names:
        lines.append(f"  {chunk_name}")
    lines.append("")
    return "\n".join(lines)


def render_model_driver(corpus: dict[str, object]) -> str:
    validate_corpus(corpus)
    lines = [
        "import Lemma.Compiler.Test.ScalarV2Eval",
        "import examples.foundation.ScalarV2Conformance",
        "",
        f"-- profile: {PROFILE}",
        f"-- suite_id: {corpus['suite_id']}",
        f"-- source_seed: {corpus['source_seed']}",
        f"-- runtime_seed: {corpus['runtime_seed']}",
        "",
    ]
    cases = corpus["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        case_id = int(str(case["case_id"]), 16)
        values = " ".join(f'"{number}"' for _, number in _case_values(case))
        lines.append(
            f'#core0_eval_typed_v02 {case["root"]} "{case_id}" {values}'
        )
    lines.append("")
    return "\n".join(lines)


def generate(
    output_dir: Path,
    *,
    source_seed: int = DEFAULT_SOURCE_SEED,
    runtime_seed: int = DEFAULT_RUNTIME_SEED,
) -> dict[str, object]:
    corpus = build_corpus(source_seed=source_seed, runtime_seed=runtime_seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "gate3-cases.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "DirectEval.lean").write_text(render_direct_driver(corpus), encoding="utf-8")
    (output_dir / "ModelEval.lean").write_text(render_model_driver(corpus), encoding="utf-8")
    batches_dir = output_dir / "batches"
    if batches_dir.exists():
        shutil.rmtree(batches_dir)
    batches_dir.mkdir()
    cases = corpus["cases"]
    assert isinstance(cases, list)
    root_ids = {spec.name: index + 1 for index, spec in enumerate(ROOT_SPECS)}
    grouped: dict[str, list[dict[str, object]]] = {spec.name: [] for spec in ROOT_SPECS}
    for case in cases:
        assert isinstance(case, dict)
        grouped[str(case["root"])].append(case)
    batch_id = 1
    for spec in ROOT_SPECS:
        for start in range(0, len(grouped[spec.name]), 29):
            chunk = grouped[spec.name][start : start + 29]
            descriptor = {
                "schema_version": 1,
                "suite_id": corpus["suite_id"],
                "batch_id": _hex64(batch_id),
                "root": spec.name,
                "root_id": _hex64(root_ids[spec.name]),
                "signature": spec.signature,
                "source_seed": corpus["source_seed"],
                "runtime_seed": corpus["runtime_seed"],
                "cases": [
                    {
                        "case_id": case["case_id"],
                        "args": [argument["value"] for argument in case["args"]],
                        "expected_result_type": case["expected_result_type"],
                    }
                    for case in chunk
                ],
            }
            (batches_dir / f"batch-{batch_id:04d}.json").write_text(
                json.dumps(descriptor, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            batch_id += 1
    return corpus


def _seed_argument(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid UInt64 seed: {text}") from error
    if not 0 <= value <= U64_MASK:
        raise argparse.ArgumentTypeError(f"UInt64 seed is out of range: {text}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-seed", type=_seed_argument, default=DEFAULT_SOURCE_SEED)
    parser.add_argument("--runtime-seed", type=_seed_argument, default=DEFAULT_RUNTIME_SEED)
    args = parser.parse_args()
    try:
        corpus = generate(
            args.output_dir,
            source_seed=args.source_seed,
            runtime_seed=args.runtime_seed,
        )
    except (CorpusError, OSError) as error:
        parser.exit(1, f"Gate 3 corpus generation failed: {error}\n")
    print(
        f"generated {corpus['case_count']} typed {PROFILE} cases across "
        f"{len(corpus['roots'])} roots for {corpus['suite_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
