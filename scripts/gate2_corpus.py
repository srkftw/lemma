#!/usr/bin/env python3
"""Deterministic typed corpus and independent Lean oracle drivers for Gate 2.

This is host-only test orchestration.  It emits calls to ordinary elaborated Lean
declarations; it does not construct Core0 or LLVM IR.
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
PROFILE = "core0-v0.1"
TEST_ABI = "lemma-scalar-test-v1"
TARGET_CASE_COUNT = 1024
DEFAULT_SOURCE_SEED = 0x4C454D4D41323032
DEFAULT_RUNTIME_SEED = 0x52554E54494D4532
U64_MASK = (1 << 64) - 1
HEX64 = re.compile(r"0x[0-9a-f]{16}\Z")
TYPES = ("bool", "u8", "u32", "u64")
TYPE_MAX = {
    "bool": 1,
    "u8": (1 << 8) - 1,
    "u32": (1 << 32) - 1,
    "u64": U64_MASK,
}
BOUNDARIES = {
    "bool": (0, 1),
    "u8": (0, 1, 2, 0x7F, 0x80, 0xFE, 0xFF),
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
    """Raised when a Gate 2 descriptor fails closed validation."""


@dataclass(frozen=True)
class RootSpec:
    name: str
    args: tuple[str, ...]
    result: str
    case_count: int
    covers: tuple[str, ...]

    @property
    def signature(self) -> dict[str, object]:
        return {"args": list(self.args), "result": self.result}


BASE = "Lemma.Examples.Foundation.Conformance"


def _root(
    short_name: str,
    args: Sequence[str],
    result: str,
    count: int,
    *covers: str,
) -> RootSpec:
    return RootSpec(f"{BASE}.{short_name}", tuple(args), result, count, tuple(covers))


ROOT_SPECS: tuple[RootSpec, ...] = (
    _root("constantU64", (), "u64", 1, "zero-argument", "literal"),
    _root("boolEq", ("bool", "bool"), "bool", 4, "bool", "bool.eq"),
    _root("boolSelect", ("bool", "u64", "u64"), "u64", 4, "bool-input", "conditional"),
    _root("u8Add", ("u8", "u8"), "u8", 64, "u8.add", "exhaustive-anchor"),
    _root("u8Sub", ("u8", "u8"), "u8", 64, "u8.sub", "exhaustive-anchor"),
    _root("u8Mul", ("u8", "u8"), "u8", 64, "u8.mul", "exhaustive-anchor"),
    _root("u8And", ("u8", "u8"), "u8", 64, "u8.and", "exhaustive-anchor"),
    _root("u8Or", ("u8", "u8"), "u8", 64, "u8.or", "exhaustive-anchor"),
    _root("u8Xor", ("u8", "u8"), "u8", 64, "u8.xor", "exhaustive-anchor"),
    _root("u8Eq", ("u8", "u8"), "bool", 64, "u8.eq", "exhaustive-anchor"),
    _root("u8Lt", ("u8", "u8"), "bool", 64, "u8.ult", "exhaustive-anchor"),
    _root("u8Le", ("u8", "u8"), "bool", 64, "u8.ule", "exhaustive-anchor"),
    _root("u32Arithmetic", ("u32", "u32", "u32"), "u32", 48, "u32.add", "u32.sub", "u32.mul"),
    _root("u32Bits", ("u32", "u32", "u32"), "u32", 48, "u32.and", "u32.or", "u32.xor"),
    _root("u32Comparisons", ("u32", "u32", "u32"), "u32", 48, "u32.eq", "u32.ult", "u32.ule"),
    _root("u64Arithmetic", ("u64", "u64", "u64"), "u64", 48, "u64.add", "u64.sub", "u64.mul"),
    _root("u64Bits", ("u64", "u64", "u64"), "u64", 48, "u64.and", "u64.or", "u64.xor"),
    _root("u64Comparisons", ("u64", "u64", "u64"), "u64", 48, "u64.eq", "u64.ult", "u64.ule"),
    _root("u8ToU32", ("u8",), "u32", 16, "u8.to-u32.zext"),
    _root("u8ToU64", ("u8",), "u64", 16, "u8.to-u64.zext"),
    _root("u32ToU8", ("u32",), "u8", 16, "u32.to-u8.trunc"),
    _root("u32ToU64", ("u32",), "u64", 16, "u32.to-u64.zext"),
    _root("u64ToU8", ("u64",), "u8", 16, "u64.to-u8.trunc"),
    _root("u64ToU32", ("u64",), "u32", 16, "u64.to-u32.trunc"),
    _root("mixedWidthCall", ("bool", "u8", "u32", "u64"), "u64", 4, "mixed-width", "cross-module-call"),
    _root("sharedDiamond", ("u64", "u64"), "u64", 7, "shared-dependency-diamond", "cross-module-call"),
    _root(
        "abiNoInlineRoot",
        ("u64", "u8", "u32", "bool", "u64", "u8", "u32", "bool", "u8", "u32"),
        "u64",
        4,
        "more-than-eight-args",
        "mixed-width-call-boundary",
    ),
    _root("metamorphicAlphaOriginal", ("u64", "u64"), "u64", 4, "metamorphic", "alpha-renaming"),
    _root("metamorphicAlphaRenamed", ("u64", "u64"), "u64", 4, "metamorphic", "alpha-renaming"),
    _root("metamorphicInline", ("u64", "u64"), "u64", 4, "metamorphic", "helper-extraction"),
    _root("metamorphicExtracted", ("u64", "u64"), "u64", 4, "metamorphic", "helper-extraction"),
    _root("metamorphicLetFlat", ("u64", "u64", "u64"), "u64", 4, "metamorphic", "let-nesting"),
    _root("metamorphicLetNested", ("u64", "u64", "u64"), "u64", 4, "metamorphic", "let-nesting"),
    RootSpec(
        f"{BASE}.MovedA.metamorphicModule",
        ("u64", "u64", "u64"),
        "u64",
        4,
        ("metamorphic", "module-reorganization"),
    ),
    RootSpec(
        f"{BASE}.MovedB.metamorphicModule",
        ("u64", "u64", "u64"),
        "u64",
        4,
        ("metamorphic", "module-reorganization"),
    ),
    RootSpec(
        f"{BASE}.ImportBase.metamorphicImport",
        ("u32", "u32"),
        "u32",
        4,
        ("metamorphic", "unreachable-host-import"),
    ),
    RootSpec(
        f"{BASE}.ImportExtra.metamorphicImport",
        ("u32", "u32"),
        "u32",
        4,
        ("metamorphic", "unreachable-host-import"),
    ),
)

METAMORPHIC_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("alpha-renaming", f"{BASE}.metamorphicAlphaOriginal", f"{BASE}.metamorphicAlphaRenamed"),
    ("helper-extraction", f"{BASE}.metamorphicInline", f"{BASE}.metamorphicExtracted"),
    ("let-nesting", f"{BASE}.metamorphicLetFlat", f"{BASE}.metamorphicLetNested"),
    ("module-reorganization", f"{BASE}.MovedA.metamorphicModule", f"{BASE}.MovedB.metamorphicModule"),
    ("unreachable-host-import", f"{BASE}.ImportBase.metamorphicImport", f"{BASE}.ImportExtra.metamorphicImport"),
)


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


def _boundary_vectors(types: tuple[str, ...]) -> list[tuple[int, ...]]:
    if not types:
        return [()]
    values: list[tuple[int, ...]] = []

    def add(vector: Iterable[int]) -> None:
        item = tuple(vector)
        if item not in values:
            values.append(item)

    add(0 for _ in types)
    add(TYPE_MAX[ty] for ty in types)
    longest = max(len(BOUNDARIES[ty]) for ty in types)
    for offset in range(longest):
        add(BOUNDARIES[ty][(offset + index) % len(BOUNDARIES[ty])] for index, ty in enumerate(types))
    for index, ty in enumerate(types):
        for value in BOUNDARIES[ty]:
            vector = [0] * len(types)
            vector[index] = value
            add(vector)
    if len(types) == 2 and types[0] == types[1]:
        for lhs in BOUNDARIES[types[0]]:
            for rhs in BOUNDARIES[types[1]]:
                add((lhs, rhs))
    return values


def _vectors(
    signature: tuple[str, ...], count: int, seed: int
) -> list[tuple[tuple[int, ...], bool]]:
    boundaries = _boundary_vectors(signature)
    if not signature:
        if count != 1:
            raise CorpusError("a zero-argument root can have only one unique input vector")
        return [((), True)]
    selected: list[tuple[int, ...]] = []
    boundary_set = set(boundaries)
    for vector in boundaries:
        if len(selected) == count:
            break
        selected.append(vector)
    rng = SplitMix64(seed)
    while len(selected) < count:
        vector = tuple(rng.next() & TYPE_MAX[ty] for ty in signature)
        if vector not in selected:
            selected.append(vector)
    return [(vector, vector in boundary_set) for vector in selected]


def _suite_id(source_seed: int, runtime_seed: int) -> str:
    catalog = [
        [spec.name, list(spec.args), spec.result, spec.case_count]
        for spec in ROOT_SPECS
    ]
    encoded = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "source_seed": _hex64(source_seed),
            "runtime_seed": _hex64(runtime_seed),
            "catalog": catalog,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    # The exact catalog/seeds are condensed to the UInt64 carried by the wire
    # header.  The full corpus file is retained and hashed separately.
    return _hex64(int.from_bytes(hashlib.sha256(encoded).digest()[:8], "little"))


def build_corpus(
    *,
    source_seed: int = DEFAULT_SOURCE_SEED,
    runtime_seed: int = DEFAULT_RUNTIME_SEED,
) -> dict[str, object]:
    if not 0 <= source_seed <= U64_MASK or not 0 <= runtime_seed <= U64_MASK:
        raise CorpusError("source and runtime seeds must be UInt64 values")
    if sum(spec.case_count for spec in ROOT_SPECS) != TARGET_CASE_COUNT:
        raise AssertionError("internal Gate 2 root distribution does not total 1024")

    specs = {spec.name: spec for spec in ROOT_SPECS}
    paired_vectors: dict[str, list[tuple[tuple[int, ...], bool]]] = {}
    for pair_name, left, right in METAMORPHIC_PAIRS:
        left_spec, right_spec = specs[left], specs[right]
        if (left_spec.args, left_spec.case_count) != (right_spec.args, right_spec.case_count):
            raise AssertionError(f"metamorphic pair {pair_name} has inconsistent descriptors")
        vectors = _vectors(
            left_spec.args,
            left_spec.case_count,
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
                spec.args,
                spec.case_count,
                _seed_for(runtime_seed, "root:" + spec.name),
            )
        for values, is_boundary in vectors:
            cases.append(
                {
                    "case_id": _hex64(next_case_id),
                    "root": spec.name,
                    "signature": spec.signature,
                    "args": [
                        {"type": ty, "value": _hex64(value)}
                        for ty, value in zip(spec.args, values, strict=True)
                    ],
                    "expected_result_type": spec.result,
                    "covers": ["boundary" if is_boundary else "seeded-runtime", *spec.covers],
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


def validate_corpus(value: object) -> None:
    if not isinstance(value, dict):
        raise CorpusError("Gate 2 corpus is not an object")
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
            "metamorphic_pairs",
            "cases",
        },
        "Gate 2 corpus",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise CorpusError("Gate 2 corpus has an unsupported schema")
    if value.get("profile") != PROFILE or value.get("test_abi") != TEST_ABI:
        raise CorpusError("Gate 2 corpus profile/test ABI is unsupported")
    source_seed = _parse_hex64(value.get("source_seed"), "source_seed")
    runtime_seed = _parse_hex64(value.get("runtime_seed"), "runtime_seed")
    if value.get("suite_id") != _suite_id(source_seed, runtime_seed):
        raise CorpusError("Gate 2 suite_id is stale or inconsistent with its seeds/catalog")
    if value.get("case_count") != TARGET_CASE_COUNT:
        raise CorpusError(f"Gate 2 corpus must contain exactly {TARGET_CASE_COUNT} cases")

    expected_specs = {spec.name: spec for spec in ROOT_SPECS}
    roots = value.get("roots")
    if not isinstance(roots, list):
        raise CorpusError("Gate 2 roots must be an array")
    observed_roots: dict[str, int] = {}
    for index, item in enumerate(roots):
        if not isinstance(item, dict):
            raise CorpusError(f"Gate 2 root #{index} is not an object")
        _exact_keys(item, {"name", "signature", "case_count", "covers"}, f"Gate 2 root #{index}")
        name = item.get("name")
        if not isinstance(name, str) or name not in expected_specs or name in observed_roots:
            raise CorpusError(f"Gate 2 root #{index} is unknown or duplicated")
        spec = expected_specs[name]
        if _validate_signature(item.get("signature"), f"Gate 2 root {name} signature") != (
            spec.args,
            spec.result,
        ):
            raise CorpusError(f"Gate 2 root {name} signature differs from the exact catalog")
        if item.get("case_count") != spec.case_count:
            raise CorpusError(f"Gate 2 root {name} has the wrong case allocation")
        covers = item.get("covers")
        if covers != list(spec.covers):
            raise CorpusError(f"Gate 2 root {name} coverage labels differ from the exact catalog")
        observed_roots[name] = 0
    if set(observed_roots) != set(expected_specs):
        raise CorpusError("Gate 2 root catalog is incomplete")

    pairs = value.get("metamorphic_pairs")
    if not isinstance(pairs, list):
        raise CorpusError("Gate 2 metamorphic_pairs must be an array")
    observed_pairs: set[tuple[str, str, str]] = set()
    for index, item in enumerate(pairs):
        if not isinstance(item, dict):
            raise CorpusError(f"metamorphic pair #{index} is not an object")
        _exact_keys(item, {"name", "left", "right"}, f"metamorphic pair #{index}")
        triple = (item.get("name"), item.get("left"), item.get("right"))
        if not all(isinstance(field, str) for field in triple):
            raise CorpusError(f"metamorphic pair #{index} has malformed identities")
        observed_pairs.add(triple)  # type: ignore[arg-type]
    if observed_pairs != set(METAMORPHIC_PAIRS) or len(pairs) != len(METAMORPHIC_PAIRS):
        raise CorpusError("Gate 2 metamorphic pair catalog is incomplete or duplicated")

    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != TARGET_CASE_COUNT:
        raise CorpusError(f"Gate 2 corpus must contain exactly {TARGET_CASE_COUNT} case objects")
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
            raise CorpusError(f"Gate 2 case #{index} is not an object")
        _exact_keys(item, expected_case_keys, f"Gate 2 case #{index}")
        case_id = _parse_hex64(item.get("case_id"), f"Gate 2 case #{index} id")
        if case_id == 0 or case_id in ids:
            raise CorpusError(f"Gate 2 case #{index} has a zero or duplicate case ID")
        ids.add(case_id)
        name = item.get("root")
        if not isinstance(name, str) or name not in expected_specs:
            raise CorpusError(f"Gate 2 case #{index} names an unknown root")
        spec = expected_specs[name]
        signature = _validate_signature(item.get("signature"), f"Gate 2 case #{index} signature")
        if signature != (spec.args, spec.result):
            raise CorpusError(f"Gate 2 case #{index} signature differs from its root")
        if item.get("expected_result_type") != spec.result:
            raise CorpusError(f"Gate 2 case #{index} has the wrong expected result type")
        args = item.get("args")
        if not isinstance(args, list) or len(args) != len(spec.args):
            raise CorpusError(f"Gate 2 case #{index} has the wrong argument count")
        vector: list[int] = []
        for arg_index, (argument, expected_type) in enumerate(zip(args, spec.args, strict=True)):
            if not isinstance(argument, dict):
                raise CorpusError(f"Gate 2 case #{index} argument #{arg_index} is not an object")
            _exact_keys(argument, {"type", "value"}, f"Gate 2 case #{index} argument #{arg_index}")
            if argument.get("type") != expected_type:
                raise CorpusError(f"Gate 2 case #{index} argument #{arg_index} has the wrong type")
            number = _parse_hex64(
                argument.get("value"), f"Gate 2 case #{index} argument #{arg_index} value"
            )
            if number > TYPE_MAX[expected_type]:
                raise CorpusError(
                    f"Gate 2 case #{index} argument #{arg_index} is outside {expected_type}"
                )
            vector.append(number)
        covers = item.get("covers")
        if (
            not isinstance(covers, list)
            or not covers
            or any(not isinstance(label, str) or not label for label in covers)
            or len(covers) != len(set(covers))
        ):
            raise CorpusError(f"Gate 2 case #{index} has invalid coverage labels")
        vector_key = (name, tuple(vector))
        if vector_key in unique_vectors:
            raise CorpusError(f"Gate 2 case #{index} duplicates a (root,args) vector")
        unique_vectors.add(vector_key)
        observed_roots[name] += 1
        root_vectors[name].append((case_id, tuple(vector)))

    if ids != set(range(1, TARGET_CASE_COUNT + 1)):
        raise CorpusError("Gate 2 case IDs must be the complete canonical 1..1024 range")
    expected_distribution = {spec.name: spec.case_count for spec in ROOT_SPECS}
    if observed_roots != expected_distribution:
        raise CorpusError("Gate 2 root coverage/case distribution is incomplete")
    for spec in ROOT_SPECS:
        if spec.args:
            vectors = [vector for _, vector in root_vectors[spec.name]]
            for arg_index, ty in enumerate(spec.args):
                seen = {vector[arg_index] for vector in vectors}
                if 0 not in seen or TYPE_MAX[ty] not in seen:
                    raise CorpusError(
                        f"Gate 2 root {spec.name} lacks min/max boundary coverage for argument #{arg_index}"
                    )
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
        "import examples.foundation.Conformance",
        "",
        "/- Generated direct-source oracle: deliberately no Core0 import/evaluator. -/",
        f"-- suite_id: {corpus['suite_id']}",
        f"-- source_seed: {corpus['source_seed']}",
        f"-- runtime_seed: {corpus['runtime_seed']}",
        "",
        "private def gate2EmitNat (caseId : Nat) (tag : String) (value : Nat) : IO Unit :=",
        '  IO.println s!"LEAN_TYPED_SOURCE:{caseId}:{tag}:{value}"',
        "",
        "private def gate2EmitBool (caseId : Nat) (value : Bool) : IO Unit :=",
        '  gate2EmitNat caseId "bool" (if value then 1 else 0)',
        "",
        "private def gate2EmitU8 (caseId : Nat) (value : UInt8) : IO Unit :=",
        '  gate2EmitNat caseId "u8" value.toNat',
        "",
        "private def gate2EmitU32 (caseId : Nat) (value : UInt32) : IO Unit :=",
        '  gate2EmitNat caseId "u32" value.toNat',
        "",
        "private def gate2EmitU64 (caseId : Nat) (value : UInt64) : IO Unit :=",
        '  gate2EmitNat caseId "u64" value.toNat',
        "",
    ]
    emitters = {"bool": "gate2EmitBool", "u8": "gate2EmitU8", "u32": "gate2EmitU32", "u64": "gate2EmitU64"}
    cases = corpus["cases"]
    assert isinstance(cases, list)
    chunk_size = 64
    chunk_names: list[str] = []
    for chunk_index, start in enumerate(range(0, len(cases), chunk_size)):
        chunk_name = f"gate2DirectChunk{chunk_index}"
        chunk_names.append(chunk_name)
        lines.append(f"private def {chunk_name} : IO Unit := do")
        for case in cases[start : start + chunk_size]:
            assert isinstance(case, dict)
            case_id = int(str(case["case_id"]), 16)
            root = str(case["root"])
            result_type = str(case["expected_result_type"])
            arguments = " ".join(_lean_literal(ty, number) for ty, number in _case_values(case))
            invocation = root + (" " + arguments if arguments else "")
            lines.append(f"  {emitters[result_type]} {case_id} ({invocation})")
        lines.append("")
    lines.append("def main : IO Unit := do")
    for chunk_name in chunk_names:
        lines.append(f"  {chunk_name}")
    lines.append("")
    return "\n".join(lines)


def render_model_driver(corpus: dict[str, object]) -> str:
    validate_corpus(corpus)
    lines = [
        "import Lemma.Compiler.Test.ScalarEval",
        "import examples.foundation.Conformance",
        "",
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
        suffix = " " + values if values else ""
        lines.append(f'#core0_eval_typed {case["root"]} "{case_id}"{suffix}')
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
    (output_dir / "gate2-cases.json").write_text(
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
        root_cases = grouped[spec.name]
        for start in range(0, len(root_cases), 29):
            chunk = root_cases[start : start + 29]
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
        parser.exit(1, f"Gate 2 corpus generation failed: {error}\n")
    print(
        f"generated {corpus['case_count']} typed cases across {len(corpus['roots'])} roots "
        f"for {corpus['suite_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
