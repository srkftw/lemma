#!/usr/bin/env python3
"""Cumulative Gate 4 bounded-iteration source/model/RV64 acceptance.

The driver consumes one deterministic ``core0-v0.3`` corpus through direct
Lean evaluation, the checked Core0 evaluator, and independently audited O0/O2
freestanding images.  It also runs the closed frontend rejection set and
adversarial structured-loop mutations before writing a PASS record.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import audit_core0
import gate4_corpus
from build_bounded_suite import build_bounded_suite
from build_core0 import invalidate_output_file, prepare_output_directory
from check_foundation_gate2 import (
    _corpus_cases,
    _manifest_root_map,
    _parse_reference_results,
    _result_digest,
    _run_host_driver,
)
from core0_common import Core0Error, load_json, run_bounded, sha256, write_json
from run_scalar_batch import ScalarBatchDescriptor, load_descriptor, run_batch


T = TypeVar("T")
ARTIFACT_FILES = (
    "image.elf",
    "program.ll",
    "program.opt.ll",
    "program.o",
    "bounded-suite-manifest.json",
    "bounded-suite-normalized.txt",
    "scalar-test-abi.json",
    "symbols.txt",
    "provenance.json",
    "audit.json",
    "program.o.stack-sizes.txt",
    "disassembly.txt",
)
REJECTION_FILES = (
    "CapturingCallback.lean",
    "DirectExternCallback.lean",
    "DynamicCallback.lean",
    "HiddenForbiddenCallback.lean",
    "LookalikeCombinator.lean",
    "NonliteralBudget.lean",
    "OverBudget.lean",
    "PolymorphicCallback.lean",
    "RecursiveCallback.lean",
    "V01BoundedLoop.lean",
    "V02BoundedLoop.lean",
)
BOUNDED_LEMMAS = (
    "executedIterations_le_budget",
    "boundedFoldU32_exhausted",
    "boundedFoldU32_zero",
)


class Gate4Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate4Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        raise Gate4Failure(category, context, str(error)) from error


def _hex(value: int) -> str:
    return f"0x{value:016x}"


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _artifact_inventory(root: Path, output: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for name in ARTIFACT_FILES:
        path = output / name
        if not path.is_file() or path.stat().st_size == 0:
            raise Core0Error(f"Gate 4 required artifact is missing or empty: {path}")
        inventory[name] = {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return inventory


def _validate_manifest_identity(
    manifest: object, *, suite_id: int, source_seed: int, runtime_seed: int
) -> dict[str, object]:
    value = audit_core0.validate_loop_suite_manifest(manifest)
    expected = {
        "suite_id": f"{suite_id:016x}",
        "source_seed": f"{source_seed:016x}",
        "runtime_seed": f"{runtime_seed:016x}",
    }
    for field, rendered in expected.items():
        if value.get(field) != rendered:
            raise Core0Error(f"Gate 4 manifest {field} differs from the corpus")
    return value


def _verify_profile_source_identity(
    *, root: Path, outputs: dict[str, Path], manifests: dict[str, object]
) -> dict[str, object]:
    if set(outputs) != {"O0", "O2"} or set(manifests) != {"O0", "O2"}:
        raise Core0Error("Gate 4 profile identity requires exact O0/O2 inputs")
    if manifests["O0"] != manifests["O2"]:
        raise Core0Error("Gate 4 O0/O2 bounded manifests are not identical")
    names = (
        "bounded-suite-manifest.json",
        "bounded-suite-normalized.txt",
        "scalar-test-abi.json",
        "symbols.txt",
    )
    hashes: dict[str, str] = {}
    for name in names:
        left, right = sha256(outputs["O0"] / name), sha256(outputs["O2"] / name)
        if left != right:
            raise Core0Error(f"Gate 4 O0/O2 checked source artifact differs: {name}")
        hashes[name] = left
    provenances = {
        profile: load_json(output / "provenance.json")
        for profile, output in outputs.items()
    }
    if any(not isinstance(value, dict) for value in provenances.values()):
        raise Core0Error("Gate 4 O0/O2 provenance is malformed")
    fields = (
        "artifact_category", "source_commit", "dirty_tree", "dirty_paths",
        "compiler_route", "target", "source_inputs", "elaborated_inputs",
        "export_configuration",
    )
    differing = [
        field for field in fields
        if provenances["O0"].get(field) != provenances["O2"].get(field)
    ]
    if differing:
        raise Core0Error(
            "Gate 4 O0/O2 provenance does not identify one source snapshot: "
            + ", ".join(differing)
        )
    return {
        "profiles": ["O0", "O2"],
        "identical_checked_source_artifacts": hashes,
        "identical_provenance_fields": list(fields),
        "source_commit": provenances["O0"].get("source_commit"),
        "dirty_tree": provenances["O0"].get("dirty_tree"),
    }


def _load_batches(
    *, corpus_dir: Path, manifest: object,
    expected_cases: dict[int, tuple[str, tuple[int, ...], str]],
    suite_id: int, source_seed: int, runtime_seed: int,
) -> tuple[ScalarBatchDescriptor, ...]:
    roots = _manifest_root_map(manifest)
    paths = sorted((corpus_dir / "batches").glob("batch-*.json"))
    if len(paths) != len(gate4_corpus.ROOT_SPECS):
        raise Core0Error("Gate 4 batch file count differs from the exact root catalog")
    descriptors: list[ScalarBatchDescriptor] = []
    seen_cases: set[int] = set()
    seen_batches: set[int] = set()
    for path in paths:
        descriptor = load_descriptor(path)
        if (
            descriptor.suite_id != suite_id
            or descriptor.source_seed != source_seed
            or descriptor.runtime_seed != runtime_seed
        ):
            raise Core0Error(f"Gate 4 batch identity differs from corpus: {path.name}")
        if descriptor.batch_id in seen_batches:
            raise Core0Error(f"duplicate Gate 4 batch ID {_hex(descriptor.batch_id)}")
        seen_batches.add(descriptor.batch_id)
        expected_root = roots.get(descriptor.root)
        if expected_root is None:
            raise Core0Error(f"Gate 4 batch root is absent from manifest: {descriptor.root}")
        root_id, args, result = expected_root
        if (
            descriptor.root_id != root_id
            or descriptor.signature.args != args
            or descriptor.signature.result != result
        ):
            raise Core0Error(f"Gate 4 batch signature differs from manifest: {descriptor.root}")
        for case in descriptor.cases:
            if case.case_id in seen_cases:
                raise Core0Error(f"Gate 4 case {_hex(case.case_id)} occurs in multiple batches")
            seen_cases.add(case.case_id)
            if expected_cases.get(case.case_id) != (
                descriptor.root, case.args, case.expected_result_type
            ):
                raise Core0Error(f"Gate 4 batch case {_hex(case.case_id)} differs from corpus")
        descriptors.append(descriptor)
    if seen_cases != set(expected_cases):
        raise Core0Error("Gate 4 batches do not cover the exact corpus")
    if seen_batches != set(range(1, len(descriptors) + 1)):
        raise Core0Error("Gate 4 batch IDs are not canonical and contiguous")
    return tuple(descriptors)


@dataclass(frozen=True)
class Gate4Rejection:
    name: str
    path: Path
    diagnostic_code: str
    required_fragments: tuple[str, ...]


def _load_rejections(path: Path, root: Path) -> tuple[Gate4Rejection, ...]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("Gate 4 rejection manifest is not an object")
    _exact_keys(
        raw, {"schema_version", "profile", "legacy_profiles", "cases"},
        "Gate 4 rejection manifest",
    )
    if (
        raw.get("schema_version") != 1
        or raw.get("profile") != gate4_corpus.PROFILE
        or raw.get("legacy_profiles") != ["core0-v0.1", "core0-v0.2"]
    ):
        raise Core0Error("Gate 4 rejection manifest has wrong profile identities")
    values = raw.get("cases")
    if not isinstance(values, list) or len(values) != len(REJECTION_FILES):
        raise Core0Error("Gate 4 rejection manifest lacks its exact 11 cases")
    quarantine = (root / "examples/foundation/gate4-reject").resolve()
    records: list[Gate4Rejection] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for index, (item, expected_file) in enumerate(zip(values, REJECTION_FILES, strict=True)):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 4 rejection #{index} is not an object")
        _exact_keys(
            item, {"name", "path", "diagnostic_code", "required_fragments"},
            f"Gate 4 rejection #{index}",
        )
        name, relative = item.get("name"), item.get("path")
        code, fragments = item.get("diagnostic_code"), item.get("required_fragments")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"Gate 4 rejection #{index} has invalid/duplicate name")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise Core0Error(f"Gate 4 rejection {name} has invalid path")
        fixture = (root / relative).resolve()
        try:
            fixture.relative_to(quarantine)
        except ValueError as error:
            raise Core0Error(f"Gate 4 rejection escapes quarantine: {relative}") from error
        if fixture.name != expected_file or not fixture.is_file() or fixture in paths:
            raise Core0Error(f"Gate 4 rejection {name} has missing/out-of-order fixture")
        if not isinstance(code, str) or not code:
            raise Core0Error(f"Gate 4 rejection {name} has invalid diagnostic code")
        if (
            not isinstance(fragments, list) or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
            or len(set(fragments)) != len(fragments)
        ):
            raise Core0Error(f"Gate 4 rejection {name} has invalid fragments")
        names.add(name)
        paths.add(fixture)
        records.append(Gate4Rejection(name, fixture, code, tuple(fragments)))
    discovered = set(quarantine.glob("*.lean"))
    if paths != discovered:
        raise Core0Error(
            "Gate 4 rejection manifest/file set differs: "
            f"untested={sorted(path.name for path in discovered - paths)!r}, "
            f"stale={sorted(path.name for path in paths - discovered)!r}"
        )
    return tuple(records)


def _run_rejections(
    cases: tuple[Gate4Rejection, ...], *, root: Path, output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for case in cases:
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str((output_dir / case.name).resolve())
        result = run_bounded(
            ("lake", "env", "lean", str(case.path.relative_to(root))),
            cwd=root, timeout_seconds=timeout_seconds, env=environment,
        )
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = output_dir / f"{case.name}.txt"
        log.write_text(output, encoding="utf-8")
        marker = f"Core0[{case.diagnostic_code}]"
        if result.returncode == 0:
            raise Core0Error(f"Gate 4 negative fixture unexpectedly passed: {case.name}")
        error_lines = [
            line for line in output.splitlines()
            if re.search(r"(?:^|:\s)error:", line) is not None
        ]
        if len(error_lines) != 1 or "error: Core0[" not in error_lines[0] or marker not in output:
            raise Core0Error(
                f"Gate 4 rejection {case.name} did not emit exactly one total {marker} "
                f"diagnostic: {error_lines!r}"
            )
        absent = [fragment for fragment in case.required_fragments if fragment not in output]
        if absent:
            raise Core0Error(
                f"Gate 4 rejection {case.name} lacked intended diagnostics: {absent!r}"
            )
        unrelated = [
            fragment for fragment in
            ("lean.unknownIdentifier", "declaration uses 'sorry'", "Aborting evaluation")
            if fragment in output
        ]
        if unrelated:
            raise Core0Error(
                f"Gate 4 rejection {case.name} also had unrelated failures: {unrelated!r}"
            )
        records.append(
            {
                "name": case.name,
                "path": str(case.path.relative_to(root)),
                "source_sha256": sha256(case.path),
                "returncode": result.returncode,
                "diagnostic_code": case.diagnostic_code,
                "required_fragments": list(case.required_fragments),
                "diagnostic_log": str(log.relative_to(root)),
                "diagnostic_sha256": sha256(log),
            }
        )
    return records


def _replace_once(source: str, before: str, after: str, context: str) -> str:
    count = source.count(before)
    if count != 1:
        raise Core0Error(
            f"Gate 4 mutation {context} anchor occurs {count} times, expected one"
        )
    return source.replace(before, after, 1)


def _mutate_definition(
    ir: str, symbol: str, before: str, after: str, context: str
) -> str:
    body = audit_core0._ir_definition_body(ir, symbol)
    mutated = _replace_once(body, before, after, context)
    return _replace_once(ir, body, mutated, f"{context}/definition")


def _expect_loop_rejection(
    *, name: str, kind: str, manifest: dict[str, object], original: str,
    mutant: str, required_fragment: str,
) -> dict[str, object]:
    if original == mutant:
        raise Core0Error(f"Gate 4 loop mutation {name} made no change")
    try:
        audit_core0.validate_loop_pre_semantics(manifest, mutant)
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error(f"Gate 4 loop mutation {name} unexpectedly passed")
    if required_fragment not in diagnostic:
        raise Core0Error(
            f"Gate 4 loop mutation {name} failed for wrong reason: {diagnostic}"
        )
    return {
        "name": name,
        "kind": kind,
        "status": "detected",
        "required_diagnostic": required_fragment,
        "diagnostic": diagnostic,
        "mutant_ir_sha256": hashlib.sha256(mutant.encode("utf-8")).hexdigest(),
    }


def _run_loop_mutations(
    manifest: dict[str, object], pre_ir: str
) -> list[dict[str, object]]:
    symbol = "core0_user_1"
    mutations = (
        (
            "wrong-static-budget", "budget-guard",
            "%loop.within-budget0 = icmp ule i32 %arg0, 16",
            "%loop.within-budget0 = icmp ule i32 %arg0, 15",
            "LLVM budget differs from source literal",
        ),
        (
            "wrong-budget-predicate", "budget-guard",
            "%loop.within-budget0 = icmp ule i32 %arg0, 16",
            "%loop.within-budget0 = icmp ult i32 %arg0, 16",
            "lacks one exact budget guard",
        ),
        (
            "index-starts-at-one", "loop-index",
            "%loop.index3 = phi i32 [ 0, %loop.preheader.0 ],",
            "%loop.index3 = phi i32 [ 1, %loop.preheader.0 ],",
            "index phi",
        ),
        (
            "stale-accumulator-phi", "loop-accumulator",
            "[ %loop.next-accumulator6, %loop.body.3 ]",
            "[ %arg1, %loop.body.3 ]",
            "accumulator phi",
        ),
        (
            "swapped-callback-arguments", "callback-abi",
            "@core0_user_0(i32 signext %loop.index3, i32 signext %loop.accumulator4)",
            "@core0_user_0(i32 signext %loop.accumulator4, i32 signext %loop.index3)",
            "callback call",
        ),
        (
            "wrong-index-increment", "loop-index",
            "%loop.next-index7 = add i32 %loop.index3, 1",
            "%loop.next-index7 = add i32 %loop.index3, 2",
            "index increment",
        ),
        (
            "missing-backedge", "loop-backedge",
            "br label %loop.header.2\nloop.done.4:",
            "br label %loop.done.4\nloop.done.4:",
            "backedge",
        ),
        (
            "missing-exhaustion-tag", "outcome-encoding",
            "%loop.exhausted-tag2 = or i64 %loop.exhausted-initial1, 9223372036854775808",
            "%loop.exhausted-tag2 = add i64 %loop.exhausted-initial1, 9223372036854775808",
            "exhaustion tag",
        ),
        (
            "exhaustion-reaches-callback", "exhaustion-control-flow",
            "br label %loop.outcome.5\nloop.header.2:",
            "br label %loop.body.3\nloop.header.2:",
            "exhaustion path reaches its callback",
        ),
    )
    records: list[dict[str, object]] = []
    for name, kind, before, after, diagnostic in mutations:
        mutant = _mutate_definition(pre_ir, symbol, before, after, name)
        records.append(
            _expect_loop_rejection(
                name=name,
                kind=kind,
                manifest=manifest,
                original=pre_ir,
                mutant=mutant,
                required_fragment=diagnostic,
            )
        )

    def expect_manifest_rejection(
        name: str, kind: str, mutant: dict[str, object], required: str
    ) -> None:
        try:
            audit_core0.validate_loop_suite_manifest(mutant)
        except Core0Error as error:
            diagnostic = str(error)
        else:
            raise Core0Error(f"Gate 4 manifest mutation {name} unexpectedly passed")
        if required not in diagnostic:
            raise Core0Error(
                f"Gate 4 manifest mutation {name} failed for wrong reason: {diagnostic}"
            )
        records.append(
            {
                "name": name,
                "kind": kind,
                "status": "detected",
                "required_diagnostic": required,
                "diagnostic": diagnostic,
            }
        )

    wrong_iteration_budget = copy.deepcopy(manifest)
    wrong_iteration_budget["iterations"][0]["static_budget"] = 15
    expect_manifest_rejection(
        "tampered-iteration-budget", "manifest-binding", wrong_iteration_budget,
        "iteration sites differ",
    )
    wrong_iteration_callback = copy.deepcopy(manifest)
    wrong_iteration_callback["iterations"][0]["callback"] = (
        f"{gate4_corpus.BASE}.sumChangedStep"
    )
    expect_manifest_rejection(
        "tampered-iteration-callback", "manifest-binding", wrong_iteration_callback,
        "iteration sites differ",
    )
    missing_iteration = copy.deepcopy(manifest)
    missing_iteration["iterations"].pop()
    expect_manifest_rejection(
        "incomplete-iteration-catalog", "manifest-closure", missing_iteration,
        "iteration sites differ",
    )
    missing_function = copy.deepcopy(manifest)
    missing_function["functions"].pop()
    expect_manifest_rejection(
        "incomplete-function-closure", "manifest-closure", missing_function,
        "exact 14-function closure",
    )

    unsupported = copy.deepcopy(manifest)
    unsupported["contract_version"] = "core0-v9.9"
    try:
        audit_core0.validate_loop_suite_manifest(unsupported)
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error("Gate 4 unsupported profile mutation unexpectedly passed")
    if "unsupported Core0 contract" not in diagnostic:
        raise Core0Error(
            f"Gate 4 profile mutation failed for wrong reason: {diagnostic}"
        )
    records.append(
        {
            "name": "unsupported-contract-version",
            "kind": "profile-version",
            "status": "detected",
            "required_diagnostic": "unsupported Core0 contract",
            "diagnostic": diagnostic,
        }
    )
    return records


def _check_changed_body_witness(
    cases: dict[int, tuple[str, tuple[int, ...], str]],
    results: dict[int, tuple[str, int]],
) -> dict[str, object]:
    left_name = f"{gate4_corpus.BASE}.sumFold"
    right_name = f"{gate4_corpus.BASE}.sumFoldChanged"
    by_root: dict[str, dict[tuple[int, ...], tuple[str, int]]] = {}
    for case_id, (root_name, arguments, _result_type) in cases.items():
        by_root.setdefault(root_name, {})[arguments] = results[case_id]
    left, right = by_root.get(left_name), by_root.get(right_name)
    if left is None or right is None or set(left) != set(right):
        raise Core0Error("Gate 4 changed-body roots do not have identical target inputs")
    witnesses = [
        {
            "count": arguments[0],
            "initial": arguments[1],
            "left": _hex(left[arguments][1]),
            "right": _hex(right[arguments][1]),
        }
        for arguments in sorted(left)
        if 0 < arguments[0] <= 16 and left[arguments] != right[arguments]
    ]
    if not witnesses:
        raise Core0Error("Gate 4 target results do not witness the changed callback body")
    return {
        "left": left_name,
        "right": right_name,
        "identical_inputs": len(left),
        "distinct_success_results": len(witnesses),
        "first_witness": witnesses[0],
    }


def _expected_results(corpus: dict[str, object]) -> dict[int, tuple[str, int]]:
    values = corpus.get("cases")
    if not isinstance(values, list):
        raise Core0Error("Gate 4 corpus lacks cases while deriving Python oracle")
    result: dict[int, tuple[str, int]] = {}
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 4 corpus case #{index} is malformed")
        result[int(str(item["case_id"]), 16)] = (
            str(item["expected_result_type"]), int(str(item["expected_value"]), 16)
        )
    return result


def _check_bounded_lemmas(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    probe = root / "examples/foundation/BoundedLemmas.lean"
    text, command = _run_host_driver(
        root=root,
        source=probe,
        output_prefix=work / "bounded-lemmas-axioms",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    if "sorryAx" in text:
        raise Core0Error("Gate 4 bounded lemmas depend on sorryAx")
    source = root / "Lemma/Core0/Bounded.lean"
    source_text = source.read_text(encoding="utf-8")
    records: list[dict[str, object]] = []
    for name in BOUNDED_LEMMAS:
        full_name = f"Lemma.Core0.Bounded.{name}"
        dependency = re.search(
            rf"'{re.escape(full_name)}' depends on axioms:\s*\[([^\]]*)\]", text
        )
        no_dependencies = f"'{full_name}' does not depend on any axioms" in text
        if dependency is None and not no_dependencies:
            raise Core0Error(f"cannot parse axiom dependencies for {full_name}")
        axioms = (
            [] if dependency is None else
            [item.strip() for item in dependency.group(1).split(",") if item.strip()]
        )
        if set(axioms) - {"propext", "Classical.choice", "Quot.sound"}:
            raise Core0Error(f"Gate 4 lemma {full_name} has unexpected axioms: {axioms!r}")
        statement = re.search(rf"(?ms)^theorem {re.escape(name)}\b(.*?) := by", source_text)
        if statement is None:
            raise Core0Error(f"cannot extract theorem statement for {full_name}")
        records.append(
            {
                "theorem": full_name,
                "statement": " ".join(f"theorem {name}{statement.group(1)}".split()),
                "axioms": axioms,
            }
        )
    return {
        "source": str(source.relative_to(root)),
        "source_sha256": sha256(source),
        "dependency_probe": command,
        "theorems": records,
        "scope": "local source-semantics facts; not a compiler-correctness proof",
    }


def _check_pinned_semantics(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    source = root / "examples/foundation/BoundedPinnedSemantics.lean"
    text, command = _run_host_driver(
        root=root,
        source=source,
        output_prefix=work / "bounded-pinned-semantics",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    expected = {
        "sum-zero": 10,
        "sum-four": 16,
        "sum-body-changed": 20,
        "sum-exhausted": gate4_corpus.exhaustion(10),
        "nested-four": 32,
        "maximum": 32640,
        "maximum-plus-one": gate4_corpus.exhaustion(9),
    }
    matches = re.findall(r"PINNED_BOUNDED:([a-z0-9-]+):([0-9]+)", text)
    observed = {name: int(value, 10) for name, value in matches}
    if len(matches) != len(expected) or observed != expected:
        raise Core0Error(
            f"Gate 4 pinned source semantics differ from contract: {observed!r}"
        )
    return {
        "source": str(source.relative_to(root)),
        "source_sha256": sha256(source),
        "command": command,
        "results": observed,
    }


def check_gate4(
    *, root: Path, work: Path, clean: bool, timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    invalidate_output_file(work / "gate4-results.json", root)
    prepare_output_directory(work, root, clean=clean)

    corpus_dir = work / "corpus"
    corpus = _stage(
        "corpus-generation-failure",
        gate4_corpus.PROFILE,
        lambda: gate4_corpus.generate(corpus_dir),
    )
    gate4_corpus.validate_corpus(corpus)
    suite_id = int(str(corpus["suite_id"]), 16)
    source_seed = int(str(corpus["source_seed"]), 16)
    runtime_seed = int(str(corpus["runtime_seed"]), 16)
    cases = _corpus_cases(corpus)
    expected_ids = set(cases)
    python_results = _expected_results(corpus)

    # The source fixtures intentionally live outside the Lake library.  Building
    # O0 first performs and records their canonical source-to-olean elaboration,
    # so generated direct/model imports cannot depend on stale local oleans.
    outputs: dict[str, Path] = {}
    manifests: dict[str, object] = {}
    profiles: dict[str, dict[str, object]] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = work / profile
        outputs[profile] = output
        build_record = _stage(
            "compile-or-link-failure",
            profile,
            lambda profile=profile, output=output, index=index: build_bounded_suite(
                root=root,
                output_dir=output,
                opt_level=profile,
                suite_id=suite_id,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
                clean=False,
                build_lean=index == 0,
                timeout_seconds=timeout_seconds,
            ),
        )
        manifest = _stage(
            "manifest-rejection",
            profile,
            lambda output=output: _validate_manifest_identity(
                load_json(output / "bounded-suite-manifest.json"),
                suite_id=suite_id,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
            ),
        )
        manifests[profile] = manifest
        audit_record = _stage(
            "provenance-or-closure-rejection",
            profile,
            lambda output=output: audit_core0.audit(
                output, root, policy=audit_core0.TEST_LOOP_SUITE_POLICY
            ),
        )
        profiles[profile] = {
            "build": build_record,
            "audit": audit_record,
            "artifacts": _artifact_inventory(root, output),
        }

    direct_text, direct_command = _stage(
        "direct-source-failure",
        gate4_corpus.PROFILE,
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "DirectEval.lean",
            output_prefix=work / "direct-source",
            execute=True,
            timeout_seconds=timeout_seconds,
        ),
    )
    direct_results = _stage(
        "direct-source-protocol-failure",
        gate4_corpus.PROFILE,
        lambda: _parse_reference_results(
            direct_text, source=True, expected_ids=expected_ids
        ),
    )
    if direct_results != python_results:
        mismatch = next(
            case_id for case_id in sorted(expected_ids)
            if direct_results[case_id] != python_results[case_id]
        )
        raise Gate4Failure(
            "independent-model-mismatch",
            f"direct/{_hex(mismatch)}",
            f"source={direct_results[mismatch]!r}, python={python_results[mismatch]!r}",
        )

    model_text, model_command = _stage(
        "checked-model-failure",
        gate4_corpus.PROFILE,
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "ModelEval.lean",
            output_prefix=work / "checked-model",
            execute=False,
            timeout_seconds=timeout_seconds,
        ),
    )
    model_results = _stage(
        "checked-model-protocol-failure",
        gate4_corpus.PROFILE,
        lambda: _parse_reference_results(
            model_text, source=False, expected_ids=expected_ids
        ),
    )
    if model_results != python_results:
        mismatch = next(
            case_id for case_id in sorted(expected_ids)
            if model_results[case_id] != python_results[case_id]
        )
        raise Gate4Failure(
            "checked-model-mismatch",
            f"model/{_hex(mismatch)}",
            f"checked={model_results[mismatch]!r}, python={python_results[mismatch]!r}",
        )
    if direct_results != model_results:
        raise Gate4Failure(
            "source-model-mismatch", gate4_corpus.PROFILE,
            "direct source and checked Core0 results differ",
        )

    profile_identity = _stage(
        "profile-source-identity-rejection",
        "O0/O2",
        lambda: _verify_profile_source_identity(
            root=root, outputs=outputs, manifests=manifests
        ),
    )
    if _manifest_root_map(manifests["O0"]) != _manifest_root_map(manifests["O2"]):
        raise Gate4Failure("manifest-rejection", "O0/O2", "root manifests differ")
    descriptors = _stage(
        "batch-manifest-rejection",
        gate4_corpus.PROFILE,
        lambda: _load_batches(
            corpus_dir=corpus_dir,
            manifest=manifests["O0"],
            expected_cases=cases,
            suite_id=suite_id,
            source_seed=source_seed,
            runtime_seed=runtime_seed,
        ),
    )

    target_witnesses: dict[str, dict[str, object]] = {}
    for profile in ("O0", "O2"):
        target_results: dict[int, tuple[str, int]] = {}
        run_records: list[dict[str, object]] = []
        for descriptor in descriptors:
            record = _stage(
                "target-execution-failure",
                f"{profile}/batch-{descriptor.batch_id}",
                lambda descriptor=descriptor, profile=profile: run_batch(
                    root=root,
                    image=outputs[profile] / "image.elf",
                    output_dir=outputs[profile] / "runs",
                    descriptor=descriptor,
                    timeout_seconds=qemu_timeout,
                ),
            )
            run_records.append(record)
            values = record.get("results")
            if not isinstance(values, list):
                raise Gate4Failure("protocol-failure", profile, "result array is missing")
            for value in values:
                if not isinstance(value, dict):
                    raise Gate4Failure("protocol-failure", profile, "result row is malformed")
                case_id = int(str(value["case_id"]), 16)
                if case_id in target_results:
                    raise Gate4Failure(
                        "protocol-failure", profile, f"duplicate case {_hex(case_id)}"
                    )
                target_results[case_id] = (
                    str(value["result_type"]), int(str(value["value"]), 16)
                )
        if set(target_results) != expected_ids:
            raise Gate4Failure(
                "protocol-failure", profile, "target result IDs differ from corpus"
            )
        if target_results != python_results:
            mismatch = next(
                case_id for case_id in sorted(expected_ids)
                if target_results[case_id] != python_results[case_id]
            )
            root_name, arguments, _result = cases[mismatch]
            raise Gate4Failure(
                "lowering-or-codegen-mismatch",
                f"{profile}/{_hex(mismatch)}",
                f"root={root_name}, args={arguments!r}, "
                f"target={target_results[mismatch]!r}, python={python_results[mismatch]!r}",
            )
        witness = _check_changed_body_witness(cases, target_results)
        target_witnesses[profile] = witness
        profiles[profile]["target"] = {
            "qemu_boots": len(descriptors),
            "case_count": len(target_results),
            "result_sha256": _result_digest(target_results),
            "changed_body_witness": witness,
            "run_records": [
                {
                    "batch_id": record["descriptor"]["batch_id"],
                    "root": record["descriptor"]["root"],
                    "cases": len(record["results"]),
                    "uart_sha256": record["uart_sha256"],
                }
                for record in run_records
            ],
        }

    rejection_cases = _stage(
        "rejection-manifest-failure",
        gate4_corpus.PROFILE,
        lambda: _load_rejections(
            root / "examples/foundation/gate4-reject/rejections.json", root
        ),
    )
    rejection_records = _stage(
        "frontend-rejection-failure",
        gate4_corpus.PROFILE,
        lambda: _run_rejections(
            rejection_cases,
            root=root,
            output_dir=work / "rejections",
            timeout_seconds=timeout_seconds,
        ),
    )
    loop_mutations = _stage(
        "loop-mutation-detection-failure",
        "O0/program.ll",
        lambda: _run_loop_mutations(
            manifests["O0"], outputs["O0"].joinpath("program.ll").read_text(encoding="utf-8")
        ),
    )
    lemmas = _stage(
        "bounded-lemma-check-failure",
        "Lemma.Core0.Bounded",
        lambda: _check_bounded_lemmas(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )
    pinned_semantics = _stage(
        "pinned-source-semantics-failure",
        gate4_corpus.PROFILE,
        lambda: _check_pinned_semantics(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )

    provenance = load_json(outputs["O0"] / "provenance.json")
    if not isinstance(provenance, dict):
        raise Gate4Failure("provenance-rejection", "O0", "provenance is malformed")
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "gate": 4,
        "source_commit": provenance.get("source_commit"),
        "contract_version": gate4_corpus.PROFILE,
        "test_abi": gate4_corpus.TEST_ABI,
        "suite_id": corpus["suite_id"],
        "seeds": {
            "source_generation": corpus["source_seed"],
            "runtime_inputs": corpus["runtime_seed"],
            "algorithm": "SplitMix64-v1 with exact bounded-count boundary pool",
        },
        "corpus": {
            "path": str((corpus_dir / "gate4-cases.json").relative_to(root)),
            "sha256": sha256(corpus_dir / "gate4-cases.json"),
            "roots": len(corpus["roots"]),
            "distinct_cases_per_profile": len(cases),
            "batches_per_profile": len(descriptors),
            "maximum_budget": corpus["maximum_budget"],
            "iteration_order": corpus["iteration_order"],
            "outcome_encoding": corpus["outcome_encoding"],
        },
        "comparisons": {
            "python_independent_model": {
                "cases": len(python_results),
                "result_sha256": _result_digest(python_results),
            },
            "direct_source": {
                "cases": len(direct_results),
                "result_sha256": _result_digest(direct_results),
                "command": direct_command,
            },
            "checked_core0_model": {
                "cases": len(model_results),
                "result_sha256": _result_digest(model_results),
                "command": model_command,
            },
            "shared_assumption": (
                "direct and checked-model paths share the pinned Lean elaborator/type checker; "
                "the independent Python model shares only the documented Gate 4 arithmetic contract"
            ),
        },
        "profiles": profiles,
        "profile_source_identity": profile_identity,
        "target_changed_body_witnesses": target_witnesses,
        "loop_mutations": loop_mutations,
        "bounded_lemmas": lemmas,
        "pinned_source_semantics": pinned_semantics,
        "negative_cases": {
            "core0-v0.3": rejection_records,
            "older-profile-loop-rejections": [
                record for record in rejection_records
                if record["name"] in {"v01-bounded-loop", "v02-bounded-loop"}
            ],
        },
        "counts": {
            "roots": len(corpus["roots"]),
            "cases_per_profile": len(cases),
            "batches_per_profile": len(descriptors),
            "qemu_boots_per_profile": len(descriptors),
            "qemu_boots_total": len(descriptors) * 2,
            "source_model_python_matches": len(cases),
            "source_model_target_matches": len(cases) * 2,
            "loop_ir_mutants_detected": sum(
                record["kind"] not in {"manifest-binding", "manifest-closure", "profile-version"}
                for record in loop_mutations
            ),
            "manifest_mutants_detected": sum(
                record["kind"] in {"manifest-binding", "manifest-closure"}
                for record in loop_mutations
            ),
            "profile_mutants_detected": sum(
                record["kind"] == "profile-version" for record in loop_mutations
            ),
            "frontend_rejections": len(rejection_records),
            "legacy_profile_rejections": 2,
            "bounded_lemmas_checked": len(BOUNDED_LEMMAS),
            "pinned_source_probes": len(pinned_semantics["results"]),
        },
        "limitations": [
            "Finite differential tests and local lemmas are not a compiler-correctness proof.",
            "This gate adds bounded scalar iteration, not interrupts or a managed Lean runtime.",
            "This result does not complete G1 or G2.",
        ],
    }
    write_json(work / "gate4-results.json", report)
    return report
