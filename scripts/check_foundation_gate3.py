#!/usr/bin/env python3
"""Cumulative Gate 3 structured-CFG scalar conformance acceptance.

The direct Lean source, checked Core0 model, and both audited freestanding RV64
images consume one deterministic ``core0-v0.2`` corpus.  The canonical PASS
record is written only after every comparison and negative check succeeds.
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
import gate3_corpus
from build_core0 import invalidate_output_file, prepare_output_directory
from build_scalar_v2_suite import build_scalar_v2_suite
from check_core0 import load_rejections, run_rejection_suite
from check_foundation_gate2 import (
    _check_metamorphic,
    _corpus_cases,
    _manifest_root_map,
    _parse_reference_results,
    _result_digest,
    _run_host_driver,
    _verify_profile_source_identity,
)
from core0_common import Core0Error, checked, load_json, run_bounded, sha256, write_json
from run_scalar_batch import ScalarBatchDescriptor, load_descriptor, run_batch


T = TypeVar("T")
SCALAR_LEMMAS = (
    "fixedWidthNormalize_lt",
    "fixedWidthNormalize_idempotent",
    "maskedShiftCount_lt",
    "shiftCountMask_eq_mod",
    "shiftCountMask_lt",
    "u8ToU32ToU8",
    "u8ToU64ToU8",
    "u32ToU64ToU32",
)
SCALAR_LEMMA_NAMESPACE = "Lemma.Core0.ScalarLemmas"
ARTIFACT_FILES = (
    "image.elf",
    "program.ll",
    "program.opt.ll",
    "scalar-suite-manifest.json",
    "scalar-suite-normalized.txt",
    "scalar-test-abi.json",
    "provenance.json",
    "audit.json",
)
PINNED_LEAN_VERSION = "4.34.1"
PINNED_LEAN_REVISION = "5045d0056413266e57c625dcd7c365b10e377c52"
PINNED_UINT_SOURCE_SHA256 = "d0f463c78f6c92585caffef53154cadd3c3e0f3b1681584f19e85d8e5da15c94"
PINNED_LEAN_HEADER_SHA256 = "866d80c309a9945b401e61fcf335a3b8545fb75c8b0a8b721fb1d3d3143d5d9c"


class Gate3Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate3Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        raise Gate3Failure(category, context, str(error)) from error


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
            raise Core0Error(f"Gate 3 required artifact is missing or empty: {path}")
        inventory[name] = {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return inventory


def _load_batches(
    *,
    corpus_dir: Path,
    manifest: object,
    expected_cases: dict[int, tuple[str, tuple[int, ...], str]],
    suite_id: int,
    source_seed: int,
    runtime_seed: int,
) -> tuple[ScalarBatchDescriptor, ...]:
    root_map = _manifest_root_map(manifest)
    paths = sorted((corpus_dir / "batches").glob("batch-*.json"))
    if not paths:
        raise Core0Error("Gate 3 generated no scalar batch descriptors")
    descriptors: list[ScalarBatchDescriptor] = []
    observed_cases: set[int] = set()
    observed_batches: set[int] = set()
    for path in paths:
        descriptor = load_descriptor(path)
        if (
            descriptor.suite_id != suite_id
            or descriptor.source_seed != source_seed
            or descriptor.runtime_seed != runtime_seed
        ):
            raise Core0Error(f"Gate 3 batch identity differs from corpus: {path.name}")
        if descriptor.batch_id in observed_batches:
            raise Core0Error(f"duplicate Gate 3 batch ID {_hex(descriptor.batch_id)}")
        observed_batches.add(descriptor.batch_id)
        manifest_root = root_map.get(descriptor.root)
        if manifest_root is None:
            raise Core0Error(f"Gate 3 batch root is absent from manifest: {descriptor.root}")
        root_id, args, result = manifest_root
        if (
            descriptor.root_id != root_id
            or descriptor.signature.args != args
            or descriptor.signature.result != result
        ):
            raise Core0Error(f"Gate 3 batch signature differs from manifest: {descriptor.root}")
        for case in descriptor.cases:
            if case.case_id in observed_cases:
                raise Core0Error(f"Gate 3 case {_hex(case.case_id)} occurs in multiple batches")
            observed_cases.add(case.case_id)
            if expected_cases.get(case.case_id) != (
                descriptor.root,
                case.args,
                case.expected_result_type,
            ):
                raise Core0Error(
                    f"Gate 3 batch case {_hex(case.case_id)} differs from the corpus"
                )
        descriptors.append(descriptor)
    if observed_cases != set(expected_cases):
        raise Core0Error(
            f"Gate 3 batches cover {len(observed_cases)} cases; "
            f"expected exactly {len(expected_cases)}"
        )
    if observed_batches != set(range(1, len(descriptors) + 1)):
        raise Core0Error("Gate 3 batch IDs are not the canonical contiguous sequence")
    return tuple(descriptors)


@dataclass(frozen=True)
class Gate3Rejection:
    name: str
    path: Path
    diagnostic_code: str
    required_fragments: tuple[str, ...]


@dataclass(frozen=True)
class Gate3Probe:
    name: str
    path: Path
    required_fragments: tuple[str, ...]


def _load_gate3_rejections(
    path: Path, root: Path
) -> tuple[tuple[Gate3Rejection, ...], tuple[Gate3Probe, ...]]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("Gate 3 rejection manifest is not an object")
    _exact_keys(
        raw,
        {"schema_version", "profile", "legacy_profile", "cases", "probes"},
        "Gate 3 rejection manifest",
    )
    if raw.get("schema_version") != 1:
        raise Core0Error("Gate 3 rejection manifest has an unsupported schema")
    if raw.get("profile") != gate3_corpus.PROFILE or raw.get("legacy_profile") != "core0-v0.1":
        raise Core0Error("Gate 3 rejection manifest has the wrong profile identities")
    values = raw.get("cases")
    if not isinstance(values, list) or not values:
        raise Core0Error("Gate 3 rejection manifest is empty")
    reject_root = (root / "examples/foundation/gate3-reject").resolve()
    names: set[str] = set()
    paths: set[Path] = set()
    cases: list[Gate3Rejection] = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 3 rejection #{index} is not an object")
        _exact_keys(
            item,
            {"name", "path", "diagnostic_code", "required_fragments"},
            f"Gate 3 rejection #{index}",
        )
        name = item.get("name")
        relative = item.get("path")
        diagnostic_code = item.get("diagnostic_code")
        fragments = item.get("required_fragments")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"Gate 3 rejection #{index} has an invalid/duplicate name")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise Core0Error(f"Gate 3 rejection {name} has an invalid source path")
        if not isinstance(diagnostic_code, str) or not diagnostic_code:
            raise Core0Error(f"Gate 3 rejection {name} has an invalid diagnostic code")
        fixture = (root / relative).resolve()
        try:
            fixture.relative_to(reject_root)
        except ValueError as error:
            raise Core0Error(f"Gate 3 rejection escapes its quarantine: {relative}") from error
        if fixture.suffix != ".lean" or not fixture.is_file() or fixture in paths:
            raise Core0Error(f"Gate 3 rejection {name} has a missing/duplicate Lean fixture")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
        ):
            raise Core0Error(f"Gate 3 rejection {name} has invalid diagnostic fragments")
        names.add(name)
        paths.add(fixture)
        cases.append(Gate3Rejection(name, fixture, diagnostic_code, tuple(fragments)))
    probe_values = raw.get("probes")
    if not isinstance(probe_values, list) or len(probe_values) != 1:
        raise Core0Error("Gate 3 rejection manifest must contain one profile probe")
    probes: list[Gate3Probe] = []
    for index, item in enumerate(probe_values):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 3 profile probe #{index} is not an object")
        _exact_keys(
            item,
            {"name", "path", "required_fragments"},
            f"Gate 3 profile probe #{index}",
        )
        name = item.get("name")
        relative = item.get("path")
        fragments = item.get("required_fragments")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"Gate 3 profile probe #{index} has an invalid/duplicate name")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise Core0Error(f"Gate 3 profile probe {name} has an invalid source path")
        fixture = (root / relative).resolve()
        try:
            fixture.relative_to(reject_root)
        except ValueError as error:
            raise Core0Error(f"Gate 3 profile probe escapes its quarantine: {relative}") from error
        if fixture.suffix != ".lean" or not fixture.is_file() or fixture in paths:
            raise Core0Error(f"Gate 3 profile probe {name} has a missing/duplicate Lean fixture")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
        ):
            raise Core0Error(f"Gate 3 profile probe {name} has invalid output fragments")
        names.add(name)
        paths.add(fixture)
        probes.append(Gate3Probe(name, fixture, tuple(fragments)))
    discovered = set(reject_root.glob("*.lean"))
    if paths != discovered:
        raise Core0Error(
            "Gate 3 rejection manifest/file set differs: "
            f"untested={sorted(str(value.relative_to(root)) for value in discovered - paths)!r}, "
            f"stale={sorted(str(value.relative_to(root)) for value in paths - discovered)!r}"
        )
    return tuple(cases), tuple(probes)


def _run_gate3_rejections(
    cases: tuple[Gate3Rejection, ...],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True)
    records: list[dict[str, object]] = []
    for case in cases:
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str((output_dir / case.name).resolve())
        result = run_bounded(
            ("lake", "env", "lean", str(case.path.relative_to(root))),
            cwd=root,
            timeout_seconds=timeout_seconds,
            env=environment,
        )
        combined = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = output_dir / f"{case.name}.txt"
        log.write_text(combined, encoding="utf-8")
        if result.returncode == 0:
            raise Core0Error(f"Gate 3 negative fixture unexpectedly passed: {case.name}")
        marker = f"Core0[{case.diagnostic_code}]"
        if combined.count("error: Core0[") != 1 or marker not in combined:
            raise Core0Error(
                f"Gate 3 rejection {case.name} did not emit exactly one {marker} diagnostic"
            )
        absent = [fragment for fragment in case.required_fragments if fragment not in combined]
        if absent:
            raise Core0Error(
                f"Gate 3 rejection {case.name} lacked intended diagnostics: {absent!r}"
            )
        records.append(
            {
                "name": case.name,
                "profile": gate3_corpus.PROFILE,
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


def _run_gate3_probes(
    probes: tuple[Gate3Probe, ...],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for probe in probes:
        result = run_bounded(
            ("lake", "env", "lean", str(probe.path.relative_to(root))),
            cwd=root,
            timeout_seconds=timeout_seconds,
        )
        combined = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = output_dir / f"{probe.name}.txt"
        log.write_text(combined, encoding="utf-8")
        if result.returncode != 0 or "error:" in combined:
            raise Core0Error(
                f"Gate 3 profile probe {probe.name} failed with rc={result.returncode}"
            )
        absent = [fragment for fragment in probe.required_fragments if fragment not in combined]
        if absent:
            raise Core0Error(
                f"Gate 3 profile probe {probe.name} lacked intended output: {absent!r}"
            )
        records.append(
            {
                "name": probe.name,
                "profile": "unsupported-version",
                "path": str(probe.path.relative_to(root)),
                "source_sha256": sha256(probe.path),
                "returncode": result.returncode,
                "required_fragments": list(probe.required_fragments),
                "output_log": str(log.relative_to(root)),
                "output_sha256": sha256(log),
            }
        )
    return records


def _expect_cfg_rejection(
    *,
    name: str,
    kind: str,
    manifest: dict[str, object],
    original: str,
    mutant: str,
    required_fragment: str,
) -> dict[str, object]:
    if original == mutant:
        raise Core0Error(f"Gate 3 CFG mutation {name} made no change")
    try:
        audit_core0.validate_cfg_pre_semantics(manifest, mutant)
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error(f"Gate 3 CFG mutation {name} unexpectedly passed")
    if required_fragment not in diagnostic:
        raise Core0Error(
            f"Gate 3 CFG mutation {name} failed for the wrong reason: {diagnostic}"
        )
    return {
        "name": name,
        "kind": kind,
        "status": "detected",
        "required_diagnostic": required_fragment,
        "diagnostic": diagnostic,
        "mutant_ir_sha256": hashlib.sha256(mutant.encode("utf-8")).hexdigest(),
    }


def _run_cfg_mutations(manifest: dict[str, object], pre_ir: str) -> list[dict[str, object]]:
    guard_pattern = re.compile(
        r"(icmp eq (i(?:8|32|64)) )([^,\n]+)(, 0\n\s+br i1 "
        r"%[A-Za-z_.$][A-Za-z0-9_.$-]*, label %"
        r"[A-Za-z_.$][A-Za-z0-9_.$-]*, label %"
        r"[A-Za-z_.$][A-Za-z0-9_.$-]*)"
    )
    guard_match = guard_pattern.search(pre_ir)
    if guard_match is None:
        raise Core0Error("Gate 3 clean IR has no mutable divisor-zero guard")
    wrong_guard = (
        pre_ir[: guard_match.start()]
        + guard_match.group(1)
        + "1"
        + guard_match.group(4)
        + pre_ir[guard_match.end() :]
    )

    edge_pattern = re.compile(
        r"(icmp eq i(?:8|32|64) [^,\n]+, 0\n\s+br i1 "
        r"%[A-Za-z_.$][A-Za-z0-9_.$-]*, label %)([A-Za-z_.$][A-Za-z0-9_.$-]*)"
        r"(, label %)([A-Za-z_.$][A-Za-z0-9_.$-]*)"
    )
    edge_match = edge_pattern.search(pre_ir)
    if edge_match is None:
        raise Core0Error("Gate 3 clean IR has no mutable divisor guard edge")
    inverted_guard = (
        pre_ir[: edge_match.start()]
        + edge_match.group(1)
        + edge_match.group(4)
        + edge_match.group(3)
        + edge_match.group(2)
        + pre_ir[edge_match.end() :]
    )
    containing_end = pre_ir.find("\n}", edge_match.end())
    if containing_end < 0:
        raise Core0Error("Gate 3 clean IR has an unterminated guarded function")
    guarded_suffix = pre_ir[edge_match.end() : containing_end]
    zero_jump_pattern = re.compile(
        rf"(^\s*{re.escape(edge_match.group(2))}:\n\s+br label %)"
        r"([A-Za-z_.$][A-Za-z0-9_.$-]*)",
        re.MULTILINE,
    )
    zero_jump_match = zero_jump_pattern.search(guarded_suffix)
    if zero_jump_match is None:
        raise Core0Error("Gate 3 clean IR has no mutable divisor-zero successor")
    zero_reaches_dangerous_suffix = (
        guarded_suffix[: zero_jump_match.start()]
        + zero_jump_match.group(1)
        + edge_match.group(4)
        + guarded_suffix[zero_jump_match.end() :]
    )
    zero_reaches_dangerous = (
        pre_ir[: edge_match.end()]
        + zero_reaches_dangerous_suffix
        + pre_ir[containing_end:]
    )

    if guard_match.start() != edge_match.start():
        raise Core0Error("Gate 3 divisor mutation anchors disagree")
    guard_line_start = pre_ir.rfind("\n", 0, guard_match.start()) + 1
    guard_line_prefix = pre_ir[guard_line_start : guard_match.start()]
    indentation_match = re.match(r"[ \t]*", guard_line_prefix)
    assert indentation_match is not None
    indentation = indentation_match.group(0)
    guarded_segment = pre_ir[guard_line_start : edge_match.end()]
    bypass_label = "audit.div.guard"
    bypass_name = "audit.divisor.zero"
    if f"%{bypass_name}" in pre_ir or f"{bypass_label}:" in pre_ir:
        raise Core0Error("Gate 3 clean IR unexpectedly contains audit mutation names")
    bypass_predecessor = (
        pre_ir[:guard_line_start]
        + f"{indentation}%{bypass_name} = icmp eq {guard_match.group(2)} "
        + f"{guard_match.group(3)}, 0\n"
        + f"{indentation}br i1 %{bypass_name}, label %{edge_match.group(4)}, "
        + f"label %{bypass_label}\n"
        + f"{bypass_label}:\n"
        + guarded_segment
        + pre_ir[edge_match.end() :]
    )

    mask_pattern = re.compile(
        r"(= and (i(?:8|32|64)) [^,\n]+, )(7|31|63)(\n\s+%"
        r"[A-Za-z_.$][A-Za-z0-9_.$-]* = (?:shl|lshr) )"
    )
    mask_match = mask_pattern.search(pre_ir)
    if mask_match is None:
        raise Core0Error("Gate 3 clean IR has no mutable shift-count mask")
    wrong_mask_value = str(int(mask_match.group(3)) - 1)
    wrong_mask = (
        pre_ir[: mask_match.start()]
        + mask_match.group(1)
        + wrong_mask_value
        + mask_match.group(4)
        + pre_ir[mask_match.end() :]
    )
    mask_input_pattern = re.compile(
        r"(= and (i(?:8|32|64)) )([^,\n]+)(, (?:7|31|63)\n\s+%"
        r"[A-Za-z_.$][A-Za-z0-9_.$-]* = (?:shl|lshr) )"
    )
    mask_input_match = mask_input_pattern.search(pre_ir)
    if mask_input_match is None:
        raise Core0Error("Gate 3 clean IR has no mutable shift-count source")
    wrong_count_source = (
        pre_ir[: mask_input_match.start()]
        + mask_input_match.group(1)
        + "0"
        + mask_input_match.group(4)
        + pre_ir[mask_input_match.end() :]
    )

    records = [
        _expect_cfg_rejection(
            name="wrong-divisor-guard-operand",
            kind="wrong-guard",
            manifest=manifest,
            original=pre_ir,
            mutant=wrong_guard,
            required_fragment="not the unique false successor",
        ),
        _expect_cfg_rejection(
            name="inverted-divisor-guard-edges",
            kind="wrong-guard",
            manifest=manifest,
            original=pre_ir,
            mutant=inverted_guard,
            required_fragment="not the unique false successor",
        ),
        _expect_cfg_rejection(
            name="zero-edge-reaches-dangerous-block",
            kind="wrong-guard",
            manifest=manifest,
            original=pre_ir,
            mutant=zero_reaches_dangerous,
            required_fragment="reachable from the divisor-zero successor",
        ),
        _expect_cfg_rejection(
            name="unguarded-dangerous-block-predecessor",
            kind="wrong-guard",
            manifest=manifest,
            original=pre_ir,
            mutant=bypass_predecessor,
            required_fragment="unguarded predecessor set",
        ),
        _expect_cfg_rejection(
            name="wrong-shift-count-mask",
            kind="wrong-count-handling",
            manifest=manifest,
            original=pre_ir,
            mutant=wrong_mask,
            required_fragment="same-block source-count",
        ),
        _expect_cfg_rejection(
            name="wrong-shift-count-source",
            kind="wrong-count-handling",
            manifest=manifest,
            original=pre_ir,
            mutant=wrong_count_source,
            required_fragment="same-block source-count",
        ),
    ]

    unsupported = copy.deepcopy(manifest)
    unsupported["contract_version"] = "core0-v9.9"
    try:
        audit_core0.validate_cfg_suite_manifest(unsupported)
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error("unsupported Core0 profile mutation unexpectedly passed")
    if "unsupported Core0 contract" not in diagnostic:
        raise Core0Error(f"unsupported profile failed for the wrong reason: {diagnostic}")
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


def _check_scalar_lemmas(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    source = root / "examples/foundation/ScalarV2Lemmas.lean"
    text, command = _run_host_driver(
        root=root,
        source=source,
        output_prefix=work / "scalar-lemmas-axioms",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    forbidden = ("sorryAx",)
    present_forbidden = [name for name in forbidden if name in text]
    if present_forbidden:
        raise Core0Error(
            f"Gate 3 scalar lemmas have forbidden axiom dependencies: {present_forbidden!r}"
        )
    theorem_records: list[dict[str, object]] = []
    lemma_source = root / "Lemma/Core0/ScalarLemmas.lean"
    lemma_text = lemma_source.read_text(encoding="utf-8")
    for name in SCALAR_LEMMAS:
        full_name = f"{SCALAR_LEMMA_NAMESPACE}.{name}"
        if full_name not in text:
            raise Core0Error(f"Gate 3 lemma output omits {full_name}")
        dependency_match = re.search(
            rf"'{re.escape(full_name)}' depends on axioms:\s*\[([^\]]*)\]", text
        )
        no_dependencies = (
            f"'{full_name}' does not depend on any axioms" in text
        )
        if dependency_match is None and not no_dependencies:
            raise Core0Error(f"cannot parse axiom dependencies for {full_name}")
        dependencies = (
            []
            if dependency_match is None
            else [
                item.strip()
                for item in dependency_match.group(1).split(",")
                if item.strip()
            ]
        )
        if set(dependencies) - {"propext", "Classical.choice", "Quot.sound"}:
            raise Core0Error(
                f"Gate 3 lemma {full_name} has unexpected axioms: {dependencies!r}"
            )
        statement_match = re.search(
            rf"(?ms)^theorem {re.escape(name)}\b(.*?) := by", lemma_text
        )
        if statement_match is None:
            raise Core0Error(f"cannot extract theorem statement for {full_name}")
        statement = " ".join(
            f"theorem {name}{statement_match.group(1)}".split()
        )
        theorem_records.append(
            {"theorem": full_name, "statement": statement, "axioms": dependencies}
        )
    return {
        "source": str(lemma_source.relative_to(root)),
        "source_sha256": sha256(lemma_source),
        "dependency_probe_source": str(source.relative_to(root)),
        "dependency_probe_source_sha256": sha256(source),
        "probe": command,
        "theorems": theorem_records,
        "scope": "local scalar invariants; not a proof of compiler correctness",
    }


def _pinned_lean_provenance(
    *, root: Path, timeout_seconds: float
) -> dict[str, object]:
    version_command = ("lean", "--version")
    version_result = checked(version_command, cwd=root, timeout_seconds=timeout_seconds)
    version = version_result.stdout.decode("utf-8", errors="strict").strip()
    if f"version {PINNED_LEAN_VERSION}" not in version:
        raise Core0Error(f"unexpected pinned Lean version: {version!r}")

    githash_command = ("lean", "--githash")
    githash_result = checked(githash_command, cwd=root, timeout_seconds=timeout_seconds)
    binary_githash = githash_result.stdout.decode("utf-8", errors="strict").strip()
    if binary_githash and binary_githash != PINNED_LEAN_REVISION:
        raise Core0Error(f"pinned Lean binary reports an unexpected git hash: {binary_githash}")

    source_expression = (
        'let flake = builtins.getFlake ("git+file://" + toString ./.); '
        "pkgs = import flake.inputs.nixpkgs { system = builtins.currentSystem; }; "
        "in pkgs.lean4.src"
    )
    source_command = (
        "nix",
        "build",
        "--no-link",
        "--print-out-paths",
        "--impure",
        "--expr",
        source_expression,
    )
    source_result = checked(source_command, cwd=root, timeout_seconds=timeout_seconds)
    source_outputs = [
        line.strip()
        for line in source_result.stdout.decode("utf-8", errors="strict").splitlines()
        if line.strip()
    ]
    if len(source_outputs) != 1:
        raise Core0Error(
            "pinned Lean source realization must return exactly one output path; "
            f"observed {len(source_outputs)}"
        )
    source_path = Path(source_outputs[0])
    if not source_path.is_absolute():
        raise Core0Error(
            f"pinned Lean source realization returned a non-absolute path: {source_path}"
        )
    source_root = source_path.resolve()
    uint_source = source_root / "src/Init/Data/UInt/Basic.lean"
    if not uint_source.is_file():
        raise Core0Error(f"pinned UInt source is missing: {uint_source}")
    uint_source_hash = sha256(uint_source)
    if uint_source_hash != PINNED_UINT_SOURCE_SHA256:
        raise Core0Error(
            "pinned UInt source hash differs from the audited revision: "
            f"{uint_source_hash}"
        )

    prefix_command = ("lean", "--print-prefix")
    prefix_result = checked(prefix_command, cwd=root, timeout_seconds=timeout_seconds)
    lean_prefix = Path(
        prefix_result.stdout.decode("utf-8", errors="strict").strip()
    ).resolve()
    lean_header = lean_prefix / "include/lean/lean.h"
    if not lean_header.is_file():
        raise Core0Error(f"pinned Lean runtime header is missing: {lean_header}")
    lean_header_hash = sha256(lean_header)
    if lean_header_hash != PINNED_LEAN_HEADER_SHA256:
        raise Core0Error(
            "pinned Lean runtime header hash differs from the audited revision: "
            f"{lean_header_hash}"
        )

    lock_path = root / "tooling/toolchain-lock.json"
    lock = load_json(lock_path)
    if not isinstance(lock, dict) or not isinstance(lock.get("tools"), dict):
        raise Core0Error("toolchain lock lacks its Lean identity")
    lean_lock = lock["tools"].get("lean")
    if not isinstance(lean_lock, dict):
        raise Core0Error("toolchain lock lacks its Lean entry")
    if (
        lean_lock.get("version") != PINNED_LEAN_VERSION
        or lean_lock.get("revision") != PINNED_LEAN_REVISION
    ):
        raise Core0Error("toolchain lock differs from the audited Lean version/revision")
    return {
        "lean_version": version,
        "lean_revision": PINNED_LEAN_REVISION,
        "binary_githash": binary_githash or None,
        "binary_githash_available": bool(binary_githash),
        "source_ref": lean_lock.get("source_ref"),
        "toolchain_lock": str(lock_path.relative_to(root)),
        "toolchain_lock_sha256": sha256(lock_path),
        "uint_source": str(uint_source),
        "uint_source_sha256": uint_source_hash,
        "lean_runtime_header": str(lean_header),
        "lean_runtime_header_sha256": lean_header_hash,
        "commands": [
            list(version_command),
            list(githash_command),
            list(source_command),
            list(prefix_command),
        ],
    }


def _check_pinned_semantics(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    source = root / "examples/foundation/ScalarV2PinnedSemantics.lean"
    text, command = _run_host_driver(
        root=root,
        source=source,
        output_prefix=work / "pinned-uint-semantics",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    expected = {
        "u8-div-zero": 0,
        "u8-rem-zero": (1 << 8) - 1,
        "u8-shl-width": 1,
        "u8-shl-width-plus-one": 2,
        "u8-shr-max-count": 1,
        "u8-complement": (1 << 8) - 1,
        "u32-div-zero": 0,
        "u32-rem-zero": (1 << 32) - 1,
        "u32-shl-width": 1,
        "u32-shl-width-plus-one": 2,
        "u32-shr-max-count": 1,
        "u32-complement": (1 << 32) - 1,
        "u64-div-zero": 0,
        "u64-rem-zero": (1 << 64) - 1,
        "u64-shl-width": 1,
        "u64-shl-width-plus-one": 2,
        "u64-shr-max-count": 1,
        "u64-complement": (1 << 64) - 1,
    }
    matches = re.findall(r"PINNED_UINT:([a-z0-9-]+):([0-9]+)", text)
    if len(matches) != len(expected):
        raise Core0Error(
            f"pinned UInt probe emitted {len(matches)} records; expected {len(expected)}"
        )
    observed: dict[str, int] = {}
    for name, raw_value in matches:
        if name in observed:
            raise Core0Error(f"pinned UInt probe repeated {name}")
        observed[name] = int(raw_value, 10)
    if observed != expected:
        raise Core0Error(
            "pinned UInt semantics differ from the explicit Gate 3 contract: "
            f"observed={observed!r}"
        )
    return {
        "source": str(source.relative_to(root)),
        "source_sha256": sha256(source),
        "command": command,
        "results": observed,
        "pinned_lean": _pinned_lean_provenance(
            root=root, timeout_seconds=timeout_seconds
        ),
        "interpretation": (
            "division by zero is zero; remainder by zero is the dividend; "
            "shift counts reduce modulo width; complement is fixed-width"
        ),
    }


def _validate_manifest_identity(
    manifest: object,
    *,
    suite_id: int,
    source_seed: int,
    runtime_seed: int,
) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise Core0Error("Gate 3 scalar-suite manifest is not an object")
    audit_core0.validate_cfg_suite_manifest(manifest)
    expected = {
        "suite_id": f"{suite_id:016x}",
        "source_seed": f"{source_seed:016x}",
        "runtime_seed": f"{runtime_seed:016x}",
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise Core0Error(f"Gate 3 manifest {field} differs from the corpus")
    return manifest


def check_gate3(
    *, root: Path, work: Path, clean: bool, timeout_seconds: float,
    qemu_timeout: float
) -> dict[str, object]:
    invalidate_output_file(work / "gate3-results.json", root)
    prepare_output_directory(work, root, clean=clean)

    corpus_dir = work / "corpus"
    corpus = _stage(
        "corpus-generation-failure",
        gate3_corpus.PROFILE,
        lambda: gate3_corpus.generate(corpus_dir),
    )
    gate3_corpus.validate_corpus(corpus)
    source_seed = int(str(corpus["source_seed"]), 16)
    runtime_seed = int(str(corpus["runtime_seed"]), 16)
    suite_id = int(str(corpus["suite_id"]), 16)
    expected_cases = _corpus_cases(corpus)
    expected_ids = set(expected_cases)

    profile_records: dict[str, dict[str, object]] = {}
    manifests: dict[str, object] = {}
    outputs: dict[str, Path] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = work / profile
        outputs[profile] = output
        build_record = _stage(
            "compile-or-link-failure",
            profile,
            lambda profile=profile, output=output, index=index: build_scalar_v2_suite(
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
                load_json(output / "scalar-suite-manifest.json"),
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
                output, root, policy="test-cfg-suite"
            ),
        )
        profile_records[profile] = {
            "build": build_record,
            "audit": audit_record,
            "artifacts": _artifact_inventory(root, output),
        }

    profile_source_identity = _stage(
        "profile-source-identity-rejection",
        "O0/O2",
        lambda: _verify_profile_source_identity(
            root=root, outputs=outputs, manifests=manifests
        ),
    )

    direct_text, direct_command = _stage(
        "direct-source-evaluation-failure",
        "direct-source",
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "DirectEval.lean",
            output_prefix=work / "direct-source",
            execute=True,
            timeout_seconds=timeout_seconds,
        ),
    )
    model_text, model_command = _stage(
        "checked-model-evaluation-failure",
        "checked-model",
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "ModelEval.lean",
            output_prefix=work / "checked-model",
            execute=False,
            timeout_seconds=timeout_seconds,
        ),
    )
    direct_results = _parse_reference_results(
        direct_text, source=True, expected_ids=expected_ids
    )
    model_results = _parse_reference_results(
        model_text, source=False, expected_ids=expected_ids
    )
    if direct_results != model_results:
        mismatch = next(
            case_id
            for case_id in sorted(expected_ids)
            if direct_results[case_id] != model_results[case_id]
        )
        root_name, arguments, _ = expected_cases[mismatch]
        raise Gate3Failure(
            "frontend-or-model-mismatch",
            _hex(mismatch),
            f"root={root_name}, args={arguments!r}, "
            f"direct={direct_results[mismatch]!r}, model={model_results[mismatch]!r}",
        )

    descriptors = _stage(
        "batch-manifest-rejection",
        "closed-corpus",
        lambda: _load_batches(
            corpus_dir=corpus_dir,
            manifest=manifests["O0"],
            expected_cases=expected_cases,
            suite_id=suite_id,
            source_seed=source_seed,
            runtime_seed=runtime_seed,
        ),
    )
    if _manifest_root_map(manifests["O0"]) != _manifest_root_map(manifests["O2"]):
        raise Gate3Failure("manifest-rejection", "O0/O2", "root manifests differ")

    for profile in ("O0", "O2"):
        target_results: dict[int, tuple[str, int]] = {}
        run_records: list[dict[str, object]] = []
        for descriptor in descriptors:
            record = _stage(
                "target-execution-failure",
                f"{profile}/batch-{descriptor.batch_id}",
                lambda descriptor=descriptor, profile=profile: run_batch(
                    root=root,
                    image=work / profile / "image.elf",
                    output_dir=work / profile / "runs",
                    descriptor=descriptor,
                    timeout_seconds=qemu_timeout,
                ),
            )
            run_records.append(record)
            values = record.get("results")
            if not isinstance(values, list):
                raise Gate3Failure("protocol-failure", profile, "result array is missing")
            for value in values:
                if not isinstance(value, dict):
                    raise Gate3Failure("protocol-failure", profile, "result row is malformed")
                case_id = int(str(value["case_id"]), 16)
                if case_id in target_results:
                    raise Gate3Failure(
                        "protocol-failure", profile, f"duplicate case {_hex(case_id)}"
                    )
                target_results[case_id] = (
                    str(value["result_type"]), int(str(value["value"]), 16)
                )
        if set(target_results) != expected_ids:
            raise Gate3Failure(
                "protocol-failure", profile, "target result IDs differ from corpus"
            )
        if target_results != direct_results:
            mismatch = next(
                case_id
                for case_id in sorted(expected_ids)
                if target_results[case_id] != direct_results[case_id]
            )
            root_name, arguments, _ = expected_cases[mismatch]
            raise Gate3Failure(
                "lowering-or-codegen-mismatch",
                f"{profile}/{_hex(mismatch)}",
                f"root={root_name}, args={arguments!r}, "
                f"source={direct_results[mismatch]!r}, target={target_results[mismatch]!r}",
            )
        profile_records[profile]["target"] = {
            "qemu_boots": len(descriptors),
            "case_count": len(target_results),
            "result_sha256": _result_digest(target_results),
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

    metamorphic = _stage(
        "metamorphic-mismatch",
        "notation/direct",
        lambda: _check_metamorphic(corpus, expected_cases, direct_results),
    )
    gate3_rejection_cases, gate3_probe_cases = _stage(
        "new-profile-rejection-manifest-failure",
        gate3_corpus.PROFILE,
        lambda: _load_gate3_rejections(
            root / "examples/foundation/gate3-reject/rejections.json", root
        ),
    )
    gate3_rejections = _stage(
        "new-profile-rejection-failure",
        gate3_corpus.PROFILE,
        lambda: _run_gate3_rejections(
            gate3_rejection_cases,
            root=root,
            output_dir=work / "rejections" / gate3_corpus.PROFILE,
            timeout_seconds=timeout_seconds,
        ),
    )
    gate3_probes = _stage(
        "unsupported-profile-probe-failure",
        "unsupported-version",
        lambda: _run_gate3_probes(
            gate3_probe_cases,
            root=root,
            output_dir=work / "rejections" / "profile-probes",
            timeout_seconds=timeout_seconds,
        ),
    )
    legacy_rejections = _stage(
        "legacy-profile-regression-failure",
        "core0-v0.1",
        lambda: run_rejection_suite(
            load_rejections(root / "tests/core0/rejections.json", root),
            root=root,
            output_dir=work / "rejections" / "core0-v0.1",
            timeout_seconds=timeout_seconds,
        ),
    )
    cfg_mutations = _stage(
        "cfg-mutation-detection-failure",
        "O0/program.ll",
        lambda: _run_cfg_mutations(
            manifests["O0"], (outputs["O0"] / "program.ll").read_text(encoding="utf-8")
        ),
    )
    scalar_lemmas = _stage(
        "scalar-lemma-check-failure",
        SCALAR_LEMMA_NAMESPACE,
        lambda: _check_scalar_lemmas(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )
    pinned_semantics = _stage(
        "pinned-source-semantics-failure",
        "UInt8/UInt32/UInt64",
        lambda: _check_pinned_semantics(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )

    provenance = load_json(outputs["O0"] / "provenance.json")
    if not isinstance(provenance, dict):
        raise Gate3Failure("provenance-rejection", "O0", "provenance is not an object")
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "gate": 3,
        "source_commit": provenance.get("source_commit"),
        "contract_version": gate3_corpus.PROFILE,
        "test_abi": gate3_corpus.TEST_ABI,
        "suite_id": corpus["suite_id"],
        "seeds": {
            "source_generation": corpus["source_seed"],
            "runtime_inputs": corpus["runtime_seed"],
            "algorithm": "SplitMix64-v1 with fixed scalar/CFG boundary pools",
        },
        "corpus": {
            "path": str((corpus_dir / "gate3-cases.json").relative_to(root)),
            "sha256": sha256(corpus_dir / "gate3-cases.json"),
            "roots": len(corpus["roots"]),
            "distinct_cases_per_profile": len(expected_cases),
            "batches_per_profile": len(descriptors),
            "primitive_coverage": corpus["primitive_coverage"],
        },
        "comparisons": {
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
                "direct and model paths share the pinned Lean elaborator/type checker; "
                "the direct path does not import or call the Core0 checker/evaluator"
            ),
        },
        "profiles": profile_records,
        "profile_source_identity": profile_source_identity,
        "metamorphic": metamorphic,
        "cfg_mutations": cfg_mutations,
        "scalar_lemmas": scalar_lemmas,
        "pinned_source_semantics": pinned_semantics,
        "negative_cases": {
            "core0-v0.2": gate3_rejections,
            "unsupported-profile-probes": gate3_probes,
            "core0-v0.1-regression": legacy_rejections,
        },
        "counts": {
            "roots": len(corpus["roots"]),
            "cases_per_profile": len(expected_cases),
            "batches_per_profile": len(descriptors),
            "qemu_boots_per_profile": len(descriptors),
            "qemu_boots_total": len(descriptors) * 2,
            "direct_source_model_matches": len(expected_cases),
            "source_model_target_matches": len(expected_cases) * 2,
            "metamorphic_pairs": len(metamorphic),
            "cfg_mutants_detected": sum(
                record["kind"] != "profile-version" for record in cfg_mutations
            ),
            "profile_mutants_detected": sum(
                record["kind"] == "profile-version" for record in cfg_mutations
            ),
            "new_profile_rejections": len(gate3_rejections),
            "unsupported_profile_probes": len(gate3_probes),
            "legacy_profile_rejections": len(legacy_rejections),
            "scalar_lemmas_checked": len(SCALAR_LEMMAS),
            "pinned_source_probes": len(pinned_semantics["results"]),
        },
        "limitations": [
            "Finite differential tests and local lemmas are not a compiler-correctness proof.",
            "This gate adds a scalar/CFG profile, not a managed Lean runtime.",
            "This result does not complete G1 or G2.",
        ],
    }
    write_json(work / "gate3-results.json", report)
    return report
