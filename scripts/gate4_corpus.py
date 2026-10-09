#!/usr/bin/env python3
"""Deterministic source/model/RV64 corpus for ``core0-v0.3`` bounded folds.

The Python model is deliberately separate from both the direct Lean source
oracle and the checked-Core0 evaluator.  It fixes the finite Gate 4 algorithms,
the zero-based iteration order, UInt32 wrapping, and the tagged exhaustion
encoding used by the acceptance driver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = 1
PROFILE = "core0-v0.3"
TEST_ABI = "lemma-scalar-test-v1"
DEFAULT_SOURCE_SEED = 0x4C454D4D41343034
DEFAULT_RUNTIME_SEED = 0x52554E54494D4534
U32_MASK = (1 << 32) - 1
U64_MASK = (1 << 64) - 1
EXHAUSTION_TAG = 1 << 63
MAXIMUM_BUDGET = 256
BASE = "Lemma.Examples.Foundation.Bounded"
COUNTS = (0, 1, 2, 3, 7, 15, 16, 17, 31, 63, 64, 65, 255, 256, 257, U32_MASK)


class CorpusError(ValueError):
    """Raised when Gate 4 corpus data does not match its closed contract."""


@dataclass(frozen=True)
class RootSpec:
    name: str
    budget: int
    callback: str
    operation: str
    covers: tuple[str, ...]

    @property
    def signature(self) -> dict[str, object]:
        return {"args": ["u32", "u32"], "result": "u64"}


ROOT_SPECS = (
    RootSpec(
        f"{BASE}.sumFold", 16, f"{BASE}.sumStep", "sum",
        ("runtime-count", "summation", "ordinary-budget"),
    ),
    RootSpec(
        f"{BASE}.sumFoldChanged", 16, f"{BASE}.sumChangedStep", "sum-changed",
        ("runtime-count", "changed-body-witness", "ordinary-budget"),
    ),
    RootSpec(
        f"{BASE}.bitMixFold", 64, f"{BASE}.bitMixStep", "bit-mix",
        ("runtime-count", "bit-mix", "v0.2-scalar-body"),
    ),
    RootSpec(
        f"{BASE}.nestedFold", 16, f"{BASE}.nestedOuterStep", "nested",
        ("runtime-count", "nested-bounded-iteration", "ordinary-budget"),
    ),
    RootSpec(
        f"{BASE}.helperFold", 64, f"{BASE}.helperStep", "helper",
        ("runtime-count", "closed-helper-body", "cross-module-helper"),
    ),
    RootSpec(
        f"{BASE}.zeroBudgetFold", 0, f"{BASE}.sumStep", "sum",
        ("runtime-count", "zero-static-budget", "exhaustion"),
    ),
    RootSpec(
        f"{BASE}.maxBudgetFold", 256, f"{BASE}.sumStep", "sum",
        ("runtime-count", "maximum-static-budget", "255-256-257-boundary"),
    ),
)
TARGET_CASE_COUNT = len(ROOT_SPECS) * len(COUNTS)


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
    return f"0x{value & U64_MASK:016x}"


def _u32(value: int) -> int:
    return value & U32_MASK


def exhaustion(initial: int) -> int:
    return EXHAUSTION_TAG | _u32(initial)


def _sum_step(index: int, accumulator: int) -> int:
    return _u32(accumulator + index)


def _sum_changed_step(index: int, accumulator: int) -> int:
    return _u32(accumulator + index + 1)


def _bit_mix_step(index: int, accumulator: int) -> int:
    count = _u32(index + 5) & 31
    shifted = _u32((accumulator ^ index) << count)
    return _u32(shifted + 0x6D2B79F5)


def _nested_inner_step(index: int, accumulator: int) -> int:
    return _u32(accumulator + index + 3)


def _nested_outer_step(index: int, accumulator: int) -> int:
    # Successful outer execution has index 0..15, so this inner site never
    # exhausts its independent static budget of sixteen.
    return model_fold(16, index, accumulator, _nested_inner_step) & U32_MASK


def _helper_step(index: int, accumulator: int) -> int:
    multiplied = _u32(index * 0x9E3779B9)
    return _u32((accumulator ^ multiplied) + 0x7F4A7C15)


STEPS = {
    "sum": _sum_step,
    "sum-changed": _sum_changed_step,
    "bit-mix": _bit_mix_step,
    "nested": _nested_outer_step,
    "helper": _helper_step,
}


def model_fold(budget: int, count: int, initial: int, step) -> int:
    """Independent finite model; exhaustion is semantic, not host timeout/fuel."""
    count = _u32(count)
    initial = _u32(initial)
    if count > budget:
        return exhaustion(initial)
    accumulator = initial
    for index in range(count):
        accumulator = step(index, accumulator)
    return accumulator


def model_root(spec: RootSpec, count: int, initial: int) -> int:
    return model_fold(spec.budget, count, initial, STEPS[spec.operation])


def _initials(runtime_seed: int) -> tuple[int, ...]:
    rng = SplitMix64(runtime_seed)
    fixed = [
        0,
        U32_MASK,
        1,
        0x80000000,
        0x7FFFFFFF,
        0x55555555,
        0xAAAAAAAA,
        U32_MASK - 1,
    ]
    while len(fixed) < len(COUNTS):
        candidate = rng.next() & U32_MASK
        if candidate not in fixed:
            fixed.append(candidate)
    return tuple(fixed)


def _count_label(count: int) -> str:
    return {
        0: "count-zero",
        1: "count-one",
        2: "count-several-two",
        3: "count-several-three",
        7: "count-several-seven",
        15: "count-sixteen-minus-one",
        16: "count-sixteen",
        17: "count-sixteen-plus-one",
        31: "count-thirty-two-minus-one",
        63: "count-sixty-four-minus-one",
        64: "count-sixty-four",
        65: "count-sixty-four-plus-one",
        255: "maximum-budget-minus-one",
        256: "maximum-budget",
        257: "maximum-budget-plus-one",
        U32_MASK: "count-u32-maximum",
    }[count]


def _suite_id(source_seed: int, runtime_seed: int) -> str:
    catalog = [
        {
            "name": spec.name,
            "budget": spec.budget,
            "callback": spec.callback,
            "operation": spec.operation,
            "covers": list(spec.covers),
        }
        for spec in ROOT_SPECS
    ]
    data = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "profile": PROFILE,
            "test_abi": TEST_ABI,
            "source_seed": _hex64(source_seed),
            "runtime_seed": _hex64(runtime_seed),
            "catalog": catalog,
            "counts": list(COUNTS),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _hex64(int.from_bytes(hashlib.sha256(data).digest()[:8], "little"))


def build_corpus(
    *,
    source_seed: int = DEFAULT_SOURCE_SEED,
    runtime_seed: int = DEFAULT_RUNTIME_SEED,
) -> dict[str, object]:
    if not 0 <= source_seed <= U64_MASK or not 0 <= runtime_seed <= U64_MASK:
        raise CorpusError("source and runtime seeds must be UInt64 values")
    initials = _initials(runtime_seed)
    order = list(ROOT_SPECS)
    rng = SplitMix64(source_seed)
    for index in range(len(order) - 1, 0, -1):
        selected = rng.next() % (index + 1)
        order[index], order[selected] = order[selected], order[index]
    cases: list[dict[str, object]] = []
    case_id = 1
    for spec in order:
        for count, initial in zip(COUNTS, initials, strict=True):
            expected = model_root(spec, count, initial)
            cases.append(
                {
                    "case_id": _hex64(case_id),
                    "root": spec.name,
                    "signature": spec.signature,
                    "args": [
                        {"type": "u32", "value": _hex64(count)},
                        {"type": "u32", "value": _hex64(initial)},
                    ],
                    "expected_result_type": "u64",
                    "expected_value": _hex64(expected),
                    "expected_outcome": "success" if count <= spec.budget else "exhausted",
                    "covers": [_count_label(count), *spec.covers],
                }
            )
            case_id += 1
    corpus: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "test_abi": TEST_ABI,
        "suite_id": _suite_id(source_seed, runtime_seed),
        "source_seed": _hex64(source_seed),
        "runtime_seed": _hex64(runtime_seed),
        "maximum_budget": MAXIMUM_BUDGET,
        "iteration_order": "ascending-zero-based",
        "outcome_encoding": {
            "success": "zero-extended-u32",
            "exhausted": "bit63-or-unchanged-initial-u32",
            "reserved_bits": "bits32-through62-zero",
        },
        "case_count": len(cases),
        "roots": [
            {
                "name": spec.name,
                "signature": spec.signature,
                "static_budget": spec.budget,
                "callback": spec.callback,
                "operation": spec.operation,
                "case_count": len(COUNTS),
                "covers": list(spec.covers),
            }
            for spec in ROOT_SPECS
        ],
        "metamorphic_pairs": [
            {
                "name": "sum-body-change",
                "left": f"{BASE}.sumFold",
                "right": f"{BASE}.sumFoldChanged",
                "relation": "same-inputs-at-least-one-distinct-success-result",
            }
        ],
        "cases": cases,
    }
    validate_corpus(corpus)
    return corpus


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CorpusError(
            f"{context} fields differ from schema: missing={sorted(expected-observed)!r}, "
            f"unexpected={sorted(observed-expected)!r}"
        )


def _parse_hex(value: object, context: str) -> int:
    if not isinstance(value, str) or len(value) != 18 or not value.startswith("0x"):
        raise CorpusError(f"{context} is not a canonical string-encoded UInt64")
    try:
        parsed = int(value, 16)
    except ValueError as error:
        raise CorpusError(f"{context} is not hexadecimal") from error
    if _hex64(parsed) != value:
        raise CorpusError(f"{context} is not lowercase canonical UInt64")
    return parsed


def validate_corpus(value: object) -> None:
    if not isinstance(value, dict):
        raise CorpusError("Gate 4 corpus is not an object")
    _exact_keys(
        value,
        {
            "schema_version", "profile", "test_abi", "suite_id", "source_seed",
            "runtime_seed", "maximum_budget", "iteration_order", "outcome_encoding",
            "case_count", "roots", "metamorphic_pairs", "cases",
        },
        "Gate 4 corpus",
    )
    if value.get("schema_version") != 1 or value.get("profile") != PROFILE:
        raise CorpusError("Gate 4 corpus has an unsupported schema/profile")
    if value.get("test_abi") != TEST_ABI:
        raise CorpusError("Gate 4 corpus has the wrong typed test ABI")
    source_seed = _parse_hex(value.get("source_seed"), "source_seed")
    runtime_seed = _parse_hex(value.get("runtime_seed"), "runtime_seed")
    if value.get("suite_id") != _suite_id(source_seed, runtime_seed):
        raise CorpusError("Gate 4 suite_id is stale or inconsistent")
    if value.get("maximum_budget") != MAXIMUM_BUDGET:
        raise CorpusError("Gate 4 maximum budget differs from 256")
    if value.get("iteration_order") != "ascending-zero-based":
        raise CorpusError("Gate 4 iteration order differs from the contract")
    if value.get("outcome_encoding") != {
        "success": "zero-extended-u32",
        "exhausted": "bit63-or-unchanged-initial-u32",
        "reserved_bits": "bits32-through62-zero",
    }:
        raise CorpusError("Gate 4 outcome encoding differs from the contract")

    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(ROOT_SPECS):
        raise CorpusError("Gate 4 root catalog is incomplete")
    for index, (root, spec) in enumerate(zip(roots, ROOT_SPECS, strict=True)):
        if not isinstance(root, dict):
            raise CorpusError(f"Gate 4 root #{index} is not an object")
        _exact_keys(
            root,
            {"name", "signature", "static_budget", "callback", "operation", "case_count", "covers"},
            f"Gate 4 root #{index}",
        )
        if root != {
            "name": spec.name,
            "signature": spec.signature,
            "static_budget": spec.budget,
            "callback": spec.callback,
            "operation": spec.operation,
            "case_count": len(COUNTS),
            "covers": list(spec.covers),
        }:
            raise CorpusError(f"Gate 4 root #{index} differs from the closed catalog")
    expected_pair = [{
        "name": "sum-body-change",
        "left": f"{BASE}.sumFold",
        "right": f"{BASE}.sumFoldChanged",
        "relation": "same-inputs-at-least-one-distinct-success-result",
    }]
    if value.get("metamorphic_pairs") != expected_pair:
        raise CorpusError("Gate 4 changed-body witness catalog differs")

    cases = value.get("cases")
    if not isinstance(cases, list) or len(cases) != TARGET_CASE_COUNT:
        raise CorpusError(f"Gate 4 corpus must have exactly {TARGET_CASE_COUNT} cases")
    if value.get("case_count") != TARGET_CASE_COUNT:
        raise CorpusError("Gate 4 case_count differs from the case array")
    by_name = {spec.name: spec for spec in ROOT_SPECS}
    vectors: dict[str, list[tuple[int, int, int]]] = {name: [] for name in by_name}
    ids: set[int] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise CorpusError(f"Gate 4 case #{index} is not an object")
        _exact_keys(
            case,
            {
                "case_id", "root", "signature", "args", "expected_result_type",
                "expected_value", "expected_outcome", "covers",
            },
            f"Gate 4 case #{index}",
        )
        case_id = _parse_hex(case.get("case_id"), f"case #{index} id")
        if case_id == 0 or case_id in ids:
            raise CorpusError(f"Gate 4 case #{index} has a zero/duplicate ID")
        ids.add(case_id)
        root_name = case.get("root")
        if not isinstance(root_name, str) or root_name not in by_name:
            raise CorpusError(f"Gate 4 case #{index} names an unknown root")
        spec = by_name[root_name]
        if case.get("signature") != spec.signature or case.get("expected_result_type") != "u64":
            raise CorpusError(f"Gate 4 case #{index} has the wrong signature/result type")
        args = case.get("args")
        if not isinstance(args, list) or len(args) != 2:
            raise CorpusError(f"Gate 4 case #{index} has the wrong argument count")
        numbers: list[int] = []
        for arg_index, argument in enumerate(args):
            if not isinstance(argument, dict):
                raise CorpusError(f"Gate 4 case #{index} arg #{arg_index} is not an object")
            _exact_keys(argument, {"type", "value"}, f"Gate 4 case #{index} arg #{arg_index}")
            number = _parse_hex(argument.get("value"), f"Gate 4 case #{index} arg #{arg_index}")
            if argument.get("type") != "u32" or number > U32_MASK:
                raise CorpusError(f"Gate 4 case #{index} arg #{arg_index} is outside u32")
            numbers.append(number)
        count, initial = numbers
        expected = _parse_hex(case.get("expected_value"), f"Gate 4 case #{index} expected")
        if expected != model_root(spec, count, initial):
            raise CorpusError(f"Gate 4 case #{index} differs from the independent model")
        outcome = "success" if count <= spec.budget else "exhausted"
        if case.get("expected_outcome") != outcome:
            raise CorpusError(f"Gate 4 case #{index} has the wrong outcome class")
        if outcome == "success":
            if expected & EXHAUSTION_TAG or expected > U32_MASK:
                raise CorpusError(f"Gate 4 success case #{index} is not zero-extended u32")
        else:
            if expected != exhaustion(initial) or expected & 0x7FFFFFFF00000000:
                raise CorpusError(f"Gate 4 exhausted case #{index} violates tag/reserved bits")
        covers = case.get("covers")
        if not isinstance(covers, list) or covers != [_count_label(count), *spec.covers]:
            raise CorpusError(f"Gate 4 case #{index} has wrong coverage labels")
        vectors[root_name].append((count, initial, expected))
    if ids != set(range(1, TARGET_CASE_COUNT + 1)):
        raise CorpusError("Gate 4 case IDs are not the canonical contiguous range")
    for spec in ROOT_SPECS:
        observed = vectors[spec.name]
        if len(observed) != len(COUNTS) or {row[0] for row in observed} != set(COUNTS):
            raise CorpusError(f"Gate 4 root {spec.name} lacks exact count boundaries")
        if {row[1] for row in observed}.isdisjoint({0}) or U32_MASK not in {row[1] for row in observed}:
            raise CorpusError(f"Gate 4 root {spec.name} lacks initial-value boundaries")
    left = [(c, i, v) for c, i, v in vectors[f"{BASE}.sumFold"]]
    right = [(c, i, v) for c, i, v in vectors[f"{BASE}.sumFoldChanged"]]
    if [(c, i) for c, i, _ in left] != [(c, i) for c, i, _ in right]:
        raise CorpusError("Gate 4 changed-body roots do not use identical inputs")
    if not any(c > 0 and c <= 16 and lv != rv for (c, _i, lv), (_c, _j, rv) in zip(left, right)):
        raise CorpusError("Gate 4 changed-body witness has no distinct successful result")


def _case_values(case: dict[str, object]) -> tuple[int, int]:
    args = case["args"]
    assert isinstance(args, list)
    return tuple(int(str(arg["value"]), 16) for arg in args)  # type: ignore[return-value]


def render_direct_driver(corpus: dict[str, object]) -> str:
    validate_corpus(corpus)
    lines = [
        "import examples.foundation.BoundedConformance",
        "",
        "/- Generated direct-source oracle; no Core0 checker/evaluator import. -/",
        f"-- profile: {PROFILE}",
        f"-- suite_id: {corpus['suite_id']}",
        "",
        "private def gate4Emit (caseId : Nat) (value : UInt64) : IO Unit :=",
        '  IO.println s!"LEAN_TYPED_SOURCE:{caseId}:u64:{value.toNat}"',
        "",
    ]
    cases = corpus["cases"]
    assert isinstance(cases, list)
    chunks: list[str] = []
    for chunk_index, start in enumerate(range(0, len(cases), 48)):
        name = f"gate4DirectChunk{chunk_index}"
        chunks.append(name)
        lines.append(f"private def {name} : IO Unit := do")
        for case in cases[start : start + 48]:
            assert isinstance(case, dict)
            count, initial = _case_values(case)
            case_id = int(str(case["case_id"]), 16)
            lines.append(
                f"  gate4Emit {case_id} ({case['root']} ({count} : UInt32) ({initial} : UInt32))"
            )
        lines.append("")
    lines.append("def main : IO Unit := do")
    lines.extend(f"  {name}" for name in chunks)
    lines.append("")
    return "\n".join(lines)


def render_model_driver(corpus: dict[str, object]) -> str:
    validate_corpus(corpus)
    lines = [
        "import Lemma.Compiler.Test.BoundedEval",
        "import examples.foundation.BoundedConformance",
        "",
        f"-- profile: {PROFILE}",
        f"-- suite_id: {corpus['suite_id']}",
        "",
    ]
    cases = corpus["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        count, initial = _case_values(case)
        case_id = int(str(case["case_id"]), 16)
        lines.append(
            f'#core0_eval_typed_v03 {case["root"]} "{case_id}" "{count}" "{initial}"'
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
    (output_dir / "gate4-cases.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "DirectEval.lean").write_text(render_direct_driver(corpus), encoding="utf-8")
    (output_dir / "ModelEval.lean").write_text(render_model_driver(corpus), encoding="utf-8")
    batches = output_dir / "batches"
    if batches.exists():
        shutil.rmtree(batches)
    batches.mkdir()
    all_cases = corpus["cases"]
    assert isinstance(all_cases, list)
    grouped = {spec.name: [] for spec in ROOT_SPECS}
    for case in all_cases:
        assert isinstance(case, dict)
        grouped[str(case["root"])].append(case)
    for batch_id, spec in enumerate(ROOT_SPECS, 1):
        descriptor = {
            "schema_version": 1,
            "suite_id": corpus["suite_id"],
            "batch_id": _hex64(batch_id),
            "root": spec.name,
            "root_id": _hex64(batch_id),
            "signature": spec.signature,
            "source_seed": corpus["source_seed"],
            "runtime_seed": corpus["runtime_seed"],
            "cases": [
                {
                    "case_id": case["case_id"],
                    "args": [argument["value"] for argument in case["args"]],
                    "expected_result_type": "u64",
                }
                for case in grouped[spec.name]
            ],
        }
        (batches / f"batch-{batch_id:04d}.json").write_text(
            json.dumps(descriptor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return corpus


def _seed(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid UInt64 seed: {text}") from error
    if not 0 <= value <= U64_MASK:
        raise argparse.ArgumentTypeError(f"UInt64 seed is out of range: {text}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-seed", type=_seed, default=DEFAULT_SOURCE_SEED)
    parser.add_argument("--runtime-seed", type=_seed, default=DEFAULT_RUNTIME_SEED)
    ns = parser.parse_args()
    try:
        corpus = generate(ns.output_dir, source_seed=ns.source_seed, runtime_seed=ns.runtime_seed)
    except (CorpusError, OSError) as error:
        parser.exit(1, f"Gate 4 corpus generation failed: {error}\n")
    print(
        f"generated {corpus['case_count']} typed {PROFILE} cases across "
        f"{len(corpus['roots'])} roots for {corpus['suite_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
