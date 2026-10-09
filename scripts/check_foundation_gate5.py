#!/usr/bin/env python3
"""Cumulative Gate 5 checked-memory source/model/RV64 acceptance.

The driver builds the closed ``core0-v0.4`` Action suite at O0 and O2, audits
the checked source envelope and emitted memory guards, and executes every case
in a fresh QEMU boot.  The canonical PASS report is written only after all
positive, negative, proof, and adversarial checks succeed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import audit_core0
import audit_memory
import gate5_corpus
import run_memory_case
from build_core0 import invalidate_output_file, prepare_output_directory
from build_memory_suite import build_memory_suite
from check_foundation_gate2 import _run_host_driver
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json


T = TypeVar("T")

ARTIFACT_FILES = (
    "image.elf",
    "image.map",
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "layout.json",
    "memory-fixtures.json",
    "memory-suite-manifest.json",
    "memory-suite-normalized.txt",
    "memory-test-abi.json",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
    "provenance.json",
    "build.json",
    "audit.json",
    "sha256sums.txt",
    "program.o.stack-sizes.txt",
    "disassembly.txt",
)

# Every artifact below is emitted from the same checked Lean source envelope,
# before the selected optimization pass.  Requiring byte identity rules out an
# O0/O2 profile accidentally compiling a different declaration snapshot.
CHECKED_SOURCE_ARTIFACTS = (
    "program.ll",
    "startup.S",
    "link.ld",
    "layout.json",
    "memory-fixtures.json",
    "memory-suite-manifest.json",
    "memory-suite-normalized.txt",
    "memory-test-abi.json",
    "symbols.txt",
)

REJECTION_FILES = (
    "CapturingActionCallback.lean",
    "DynamicActionCallback.lean",
    "NonliteralActionBudget.lean",
    "OverActionBudget.lean",
    "StoredLoadContinuation.lean",
    "HiddenExternAction.lean",
    "RecursiveAction.lean",
    "LookalikeAction.lean",
    "ActionParameter.lean",
    "PureResultAction.lean",
    "V01Action.lean",
    "V02Action.lean",
    "V03Action.lean",
    "UnsafeAction.lean",
)

MEMORY_LEMMAS = (
    "regionTable_valid",
    "orderedBounds_intervalContained",
    "orderedBounds_physicalInterval",
    "rejectedStore_preservesMemory",
    "rejectedStore_preservesEvents",
)
MEMORY_LEMMA_NAMESPACE = "Lemma.Core0.Memory"

PINNED_MEMORY_RESULTS: dict[str, tuple[int, int, int]] = {
    "roundtrip32": (0, 0x78563412, 2),
    "last-valid64": (0, 0, 1),
    "one-past": (7, 0, 0),
    "misaligned32": (8, 0, 0),
    "oob-before-alignment": (7, 0, 0),
    "read-only-write": (5, 0, 0),
    "reserved-image": (2, 0, 0),
    "device-uart": (3, 0, 0),
    "unknown-region": (1, 0, 0),
    "maximum-offset": (7, 0, 0),
    "event-byte-width": (6, 0, 0),
    "range-preflight": (7, 0, 0),
    "empty-range-at-end": (0, 0, 0),
    "fold-budget": (9, 0, 0),
    "fill-four": (0, 168, 4),
    "checksum-four": (0, 168, 8),
    "copy-seed": (0, 46, 4),
    "overlap-copy": (0, 46, 12),
}


class Gate5Failure(Core0Error):
    """One classified Gate 5 acceptance failure."""

    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate5Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        raise Gate5Failure(category, context, str(error)) from error


def _target_stage(profile: str, case_id: int, action: Callable[[], T]) -> T:
    context = f"{profile}/0x{case_id:016x}"
    try:
        return action()
    except Gate5Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        detail = str(error)
        lowered = detail.lower()
        if "timed out" in lowered:
            category = "target-timeout"
        elif any(
            marker in lowered
            for marker in ("transcript", "case frame", "outcome frame", "canary", "end frame")
        ):
            category = "target-protocol-failure"
        elif any(
            marker in lowered
            for marker in ("image binding", "bound image", "build hash", "manifest", "artifact")
        ):
            category = "target-artifact-binding-failure"
        elif "qemu process" in lowered or "unexpected stderr" in lowered:
            category = "target-process-failure"
        else:
            category = "target-execution-failure"
        raise Gate5Failure(category, context, detail) from error


def _hex(value: int) -> str:
    return f"0x{value:016x}"


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _artifact_inventory(root: Path, output: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for name in ARTIFACT_FILES:
        path = output / name
        if not path.is_file() or path.stat().st_size == 0:
            raise Core0Error(f"Gate 5 required artifact is missing or empty: {path}")
        inventory[name] = {
            "path": _relative(path, root),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return inventory


def _validate_manifest_identity(
    manifest: object,
    *,
    suite_id: int,
    source_seed: int,
    runtime_seed: int,
) -> dict[str, object]:
    value = audit_memory.validate_memory_suite_manifest(manifest)
    expected_identity = {
        "suite_id": f"{suite_id:016x}",
        "source_seed": f"{source_seed:016x}",
        "runtime_seed": f"{runtime_seed:016x}",
    }
    for field, rendered in expected_identity.items():
        if value.get(field) != rendered:
            raise Core0Error(f"Gate 5 manifest {field} differs from the corpus")

    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != len(gate5_corpus.ROOT_SPECS):
        raise Core0Error("Gate 5 manifest does not contain the exact 26-root catalog")
    for root_id, (entry, spec) in enumerate(
        zip(roots, gate5_corpus.ROOT_SPECS, strict=True), 1
    ):
        if not isinstance(entry, dict):
            raise Core0Error(f"Gate 5 manifest root #{root_id} is malformed")
        if (
            entry.get("root_id") != root_id
            or entry.get("source") != spec.name
            or entry.get("signature") != {"args": list(spec.args)}
        ):
            raise Core0Error(f"Gate 5 manifest root #{root_id} differs from the corpus")
    return value


def _verify_profile_source_identity(
    *, root: Path, outputs: Mapping[str, Path], manifests: Mapping[str, object]
) -> dict[str, object]:
    if set(outputs) != {"O0", "O2"} or set(manifests) != {"O0", "O2"}:
        raise Core0Error("Gate 5 profile identity requires exact O0/O2 inputs")
    if manifests["O0"] != manifests["O2"]:
        raise Core0Error("Gate 5 O0/O2 memory manifests are not identical")

    hashes: dict[str, str] = {}
    for name in CHECKED_SOURCE_ARTIFACTS:
        left = sha256(outputs["O0"] / name)
        right = sha256(outputs["O2"] / name)
        if left != right:
            raise Core0Error(f"Gate 5 O0/O2 checked source artifact differs: {name}")
        hashes[name] = left

    provenances = {
        profile: load_json(output / "provenance.json")
        for profile, output in outputs.items()
    }
    if any(not isinstance(value, dict) for value in provenances.values()):
        raise Core0Error("Gate 5 O0/O2 provenance is malformed")
    fields = (
        "artifact_category",
        "source_commit",
        "dirty_tree",
        "dirty_paths",
        "compiler_route",
        "target",
        "source_inputs",
        "elaborated_inputs",
        "export_configuration",
    )
    differing = [
        field
        for field in fields
        if provenances["O0"].get(field) != provenances["O2"].get(field)
    ]
    if differing:
        raise Core0Error(
            "Gate 5 O0/O2 provenance does not identify one source snapshot: "
            + ", ".join(differing)
        )
    return {
        "profiles": ["O0", "O2"],
        "identical_checked_source_artifacts": hashes,
        "identical_provenance_fields": list(fields),
        "source_commit": provenances["O0"].get("source_commit"),
        "dirty_tree": provenances["O0"].get("dirty_tree"),
        "dirty_paths": provenances["O0"].get("dirty_paths"),
    }


@dataclass(frozen=True)
class ExpectedCase:
    root: str
    root_id: int
    status: int
    value: int
    event_count: int
    event_sha256: str
    final_memory_sha256: str


def _expected_cases(corpus: Mapping[str, object]) -> dict[int, ExpectedCase]:
    raw_cases = corpus.get("cases")
    if not isinstance(raw_cases, list):
        raise Core0Error("Gate 5 corpus cases are malformed")
    result: dict[int, ExpectedCase] = {}
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict) or not isinstance(item.get("expected"), dict):
            raise Core0Error(f"Gate 5 corpus case #{index} is malformed")
        expected = item["expected"]
        assert isinstance(expected, dict)
        case_id = int(str(item.get("case_id")), 16)
        value = int(str(expected.get("value")), 16)
        record = ExpectedCase(
            root=str(item.get("root")),
            root_id=int(item.get("root_id", 0)),
            status=int(expected.get("status", -1)),
            value=value,
            event_count=int(expected.get("event_count", -1)),
            event_sha256=str(expected.get("event_sha256")),
            final_memory_sha256=str(expected.get("final_memory_sha256")),
        )
        if case_id in result:
            raise Core0Error(f"Gate 5 corpus repeats case {_hex(case_id)}")
        result[case_id] = record
    if set(result) != set(range(1, gate5_corpus.TARGET_CASE_COUNT + 1)):
        raise Core0Error("Gate 5 corpus case IDs are not the exact contiguous set")
    return result


def _load_descriptors(
    *,
    corpus_dir: Path,
    manifest: Mapping[str, object],
    expected_cases: Mapping[int, ExpectedCase],
    suite_id: int,
    source_seed: int,
    runtime_seed: int,
) -> tuple[run_memory_case.MemoryCaseDescriptor, ...]:
    roots = manifest.get("roots")
    if not isinstance(roots, list):
        raise Core0Error("Gate 5 manifest root catalog is malformed")
    manifest_roots = {
        int(entry["root_id"]): entry
        for entry in roots
        if isinstance(entry, dict) and type(entry.get("root_id")) is int
    }
    paths = sorted((corpus_dir / "descriptors").glob("case-*.json"))
    if len(paths) != gate5_corpus.TARGET_CASE_COUNT:
        raise Core0Error("Gate 5 descriptor file count differs from the exact 52-case corpus")
    descriptors: list[run_memory_case.MemoryCaseDescriptor] = []
    seen: set[int] = set()
    for path in paths:
        descriptor = run_memory_case.load_descriptor(path)
        if descriptor.case_id in seen:
            raise Core0Error(f"Gate 5 descriptor repeats case {_hex(descriptor.case_id)}")
        seen.add(descriptor.case_id)
        if (
            descriptor.suite_id != suite_id
            or descriptor.source_seed != source_seed
            or descriptor.runtime_seed != runtime_seed
        ):
            raise Core0Error(f"Gate 5 descriptor identity differs from corpus: {path.name}")
        expected = expected_cases.get(descriptor.case_id)
        if expected is None:
            raise Core0Error(f"Gate 5 descriptor has unknown case {_hex(descriptor.case_id)}")
        if descriptor.root != expected.root or descriptor.root_id != expected.root_id:
            raise Core0Error(f"Gate 5 descriptor selects the wrong root: {path.name}")
        root = manifest_roots.get(descriptor.root_id)
        if root is None or root.get("source") != descriptor.root:
            raise Core0Error(f"Gate 5 descriptor root is absent from manifest: {path.name}")
        if root.get("signature") != {"args": list(descriptor.signature.args)}:
            raise Core0Error(f"Gate 5 descriptor signature differs from manifest: {path.name}")

        # Recompute the oracle from the independent finite model instead of
        # merely trusting the expected fields serialized in the corpus.
        spec = gate5_corpus.ROOT_SPECS[descriptor.root_id - 1]
        outcome, model = gate5_corpus.evaluate(spec, descriptor)
        if (
            outcome.status,
            outcome.value,
            len(model.events),
            gate5_corpus._event_digest(model.events),
            model.digest(),
        ) != (
            expected.status,
            expected.value,
            expected.event_count,
            expected.event_sha256,
            expected.final_memory_sha256,
        ):
            raise Core0Error(f"Gate 5 descriptor oracle differs from corpus: {path.name}")
        descriptors.append(descriptor)
    if seen != set(expected_cases):
        raise Core0Error("Gate 5 descriptors do not cover the exact corpus")
    return tuple(descriptors)


@dataclass(frozen=True)
class Gate5Rejection:
    name: str
    path: Path
    diagnostic_code: str
    required_fragments: tuple[str, ...]


def _load_rejections(path: Path, root: Path) -> tuple[Gate5Rejection, ...]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("Gate 5 rejection manifest is not an object")
    _exact_keys(
        raw,
        {"schema_version", "profile", "legacy_profiles", "cases"},
        "Gate 5 rejection manifest",
    )
    if (
        raw.get("schema_version") != 1
        or raw.get("profile") != gate5_corpus.PROFILE
        or raw.get("legacy_profiles") != ["core0-v0.1", "core0-v0.2", "core0-v0.3"]
    ):
        raise Core0Error("Gate 5 rejection manifest has wrong profile identities")
    values = raw.get("cases")
    if not isinstance(values, list) or len(values) != len(REJECTION_FILES):
        raise Core0Error("Gate 5 rejection manifest lacks its exact 14 cases")

    quarantine = (root / "examples/foundation/gate5-reject").resolve()
    records: list[Gate5Rejection] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for index, (item, expected_file) in enumerate(zip(values, REJECTION_FILES, strict=True)):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 5 rejection #{index} is not an object")
        _exact_keys(
            item,
            {"name", "path", "diagnostic_code", "required_fragments"},
            f"Gate 5 rejection #{index}",
        )
        name, relative = item.get("name"), item.get("path")
        code, fragments = item.get("diagnostic_code"), item.get("required_fragments")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"Gate 5 rejection #{index} has an invalid/duplicate name")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise Core0Error(f"Gate 5 rejection {name} has an invalid path")
        fixture = (root / relative).resolve()
        try:
            fixture.relative_to(quarantine)
        except ValueError as error:
            raise Core0Error(f"Gate 5 rejection escapes quarantine: {relative}") from error
        if fixture.name != expected_file or not fixture.is_file() or fixture in paths:
            raise Core0Error(f"Gate 5 rejection {name} has missing/out-of-order fixture")
        if not isinstance(code, str) or not code:
            raise Core0Error(f"Gate 5 rejection {name} has invalid diagnostic code")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
            or len(set(fragments)) != len(fragments)
        ):
            raise Core0Error(f"Gate 5 rejection {name} has invalid fragments")
        names.add(name)
        paths.add(fixture)
        records.append(Gate5Rejection(name, fixture, code, tuple(fragments)))
    discovered = set(quarantine.glob("*.lean"))
    if paths != discovered:
        raise Core0Error(
            "Gate 5 rejection manifest/file set differs: "
            f"untested={sorted(item.name for item in discovered - paths)!r}, "
            f"stale={sorted(item.name for item in paths - discovered)!r}"
        )
    return tuple(records)


def _run_rejections(
    cases: tuple[Gate5Rejection, ...],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for case in cases:
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str((output_dir / case.name).resolve())
        argv = ("lake", "env", "lean", str(case.path.relative_to(root)))
        result = run_bounded(
            argv, cwd=root, timeout_seconds=timeout_seconds, env=environment
        )
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = output_dir / f"{case.name}.txt"
        log.write_text(output, encoding="utf-8")
        marker = f"Core0[{case.diagnostic_code}]"
        if result.returncode == 0:
            raise Core0Error(f"Gate 5 negative fixture unexpectedly passed: {case.name}")
        error_lines = [
            line
            for line in output.splitlines()
            if re.search(r"(?:^|:\s)error:", line) is not None
        ]
        if len(error_lines) != 1 or "error: Core0[" not in error_lines[0] or marker not in output:
            raise Core0Error(
                f"Gate 5 rejection {case.name} did not emit exactly one total {marker} "
                f"diagnostic: {error_lines!r}"
            )
        missing = [fragment for fragment in case.required_fragments if fragment not in output]
        if missing:
            raise Core0Error(
                f"Gate 5 rejection {case.name} lacked intended diagnostics: {missing!r}"
            )
        unrelated = [
            fragment
            for fragment in (
                "lean.unknownIdentifier",
                "declaration uses 'sorry'",
                "Aborting evaluation",
                "unknown declaration",
            )
            if fragment in output
        ]
        if unrelated:
            raise Core0Error(
                f"Gate 5 rejection {case.name} also had unrelated failures: {unrelated!r}"
            )
        records.append(
            {
                "name": case.name,
                "path": str(case.path.relative_to(root)),
                "source_sha256": sha256(case.path),
                "argv": list(argv),
                "returncode": result.returncode,
                "diagnostic_code": case.diagnostic_code,
                "required_fragments": list(case.required_fragments),
                "diagnostic_log": _relative(log, root),
                "diagnostic_sha256": sha256(log),
            }
        )
    return records


def _check_memory_lemmas(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    probe = root / "examples/foundation/MemoryLemmas.lean"
    text, command = _run_host_driver(
        root=root,
        source=probe,
        output_prefix=work / "memory-lemmas-axioms",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    lemma_source = root / "Lemma/Core0/MemoryLemmas.lean"
    source_text = lemma_source.read_text(encoding="utf-8")
    if "sorryAx" in text:
        raise Core0Error("Gate 5 memory lemmas depend on sorryAx")
    forbidden_source = [
        token
        for token in ("sorry", "admit", "native_decide")
        if re.search(rf"\b{re.escape(token)}\b", source_text)
    ]
    if forbidden_source:
        raise Core0Error(
            f"Gate 5 memory lemma source contains forbidden proof devices: {forbidden_source!r}"
        )

    theorem_records: list[dict[str, object]] = []
    for name in MEMORY_LEMMAS:
        full_name = f"{MEMORY_LEMMA_NAMESPACE}.{name}"
        dependency = re.search(
            rf"'{re.escape(full_name)}' depends on axioms:\s*\[([^\]]*)\]", text
        )
        no_dependencies = f"'{full_name}' does not depend on any axioms" in text
        if dependency is None and not no_dependencies:
            raise Core0Error(f"cannot parse axiom dependencies for {full_name}")
        axioms = (
            []
            if dependency is None
            else [item.strip() for item in dependency.group(1).split(",") if item.strip()]
        )
        if set(axioms) - {"propext", "Classical.choice", "Quot.sound"}:
            raise Core0Error(f"Gate 5 lemma {full_name} has unexpected axioms: {axioms!r}")
        statement = re.search(rf"(?ms)^theorem {re.escape(name)}\b(.*?) := by", source_text)
        if statement is None:
            raise Core0Error(f"cannot extract theorem statement for {full_name}")
        theorem_records.append(
            {
                "theorem": full_name,
                "statement": " ".join(f"theorem {name}{statement.group(1)}".split()),
                "axioms": axioms,
            }
        )
    return {
        "source": str(lemma_source.relative_to(root)),
        "source_sha256": sha256(lemma_source),
        "model_source": "Lemma/Core0/MemoryModel.lean",
        "model_source_sha256": sha256(root / "Lemma/Core0/MemoryModel.lean"),
        "dependency_probe": command,
        "theorems": theorem_records,
        "scope": (
            "local finite-model catalog, interval, and rejection-preservation facts; "
            "not a compiler-correctness proof"
        ),
    }


def _check_pinned_memory_semantics(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    source = root / "examples/foundation/MemoryPinnedSemantics.lean"
    text, command = _run_host_driver(
        root=root,
        source=source,
        output_prefix=work / "pinned-memory-semantics",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    matches = re.findall(
        r"PINNED_MEMORY:([a-z0-9-]+):([0-9]+):([0-9]+):([0-9]+)", text
    )
    observed: dict[str, tuple[int, int, int]] = {}
    for name, status, value, events in matches:
        if name in observed:
            raise Core0Error(f"pinned memory probe repeated {name}")
        observed[name] = (int(status, 10), int(value, 10), int(events, 10))
    if len(matches) != len(PINNED_MEMORY_RESULTS) or observed != PINNED_MEMORY_RESULTS:
        raise Core0Error(
            "pinned memory semantics differ from the explicit Gate 5 contract: "
            f"observed={observed!r}"
        )
    return {
        "source": str(source.relative_to(root)),
        "source_sha256": sha256(source),
        "source_action_module": "examples/foundation/MemoryConformance.lean",
        "source_action_module_sha256": sha256(
            root / "examples/foundation/MemoryConformance.lean"
        ),
        "model_source": "Lemma/Core0/MemoryModel.lean",
        "model_source_sha256": sha256(root / "Lemma/Core0/MemoryModel.lean"),
        "command": command,
        "results": {
            name: {"status": values[0], "value": values[1], "events": values[2]}
            for name, values in observed.items()
        },
        "interpretation": (
            "the executable finite-memory model evaluates the original elaborated Action "
            "declarations and records events only for successful physical loads/stores"
        ),
    }


def _run_mutation_matrix(
    manifest: Mapping[str, object], pre_ir: str
) -> dict[str, object]:
    manifest_mutants = audit_memory.manifest_mutations(manifest)
    ir_mutants = audit_memory.ir_mutations(pre_ir)
    records = audit_memory.audit_mutation_matrix(manifest, pre_ir)
    expected_count = len(manifest_mutants) + len(ir_mutants)
    if len(records) != expected_count:
        raise Core0Error(
            f"Gate 5 mutation matrix returned {len(records)} records; expected {expected_count}"
        )
    identities = [
        (
            "manifest" if index < len(manifest_mutants) else "pre-optimization-ir",
            str(record.get("name")),
        )
        for index, record in enumerate(records)
    ]
    if len(set(identities)) != len(identities):
        raise Core0Error("Gate 5 mutation matrix repeats a mutant within one audit layer")
    return {
        "manifest_mutants_detected": len(manifest_mutants),
        "ir_mutants_detected": len(ir_mutants),
        "total_mutants_detected": len(records),
        "records": [
            {
                "layer": "manifest" if index < len(manifest_mutants) else "pre-optimization-ir",
                "status": "detected",
                **record,
            }
            for index, record in enumerate(records)
        ],
    }


def _result_digest(results: Mapping[int, tuple[int, int]]) -> str:
    payload = "".join(
        f"{case_id:016x}:{status:02x}:{value:016x}\n"
        for case_id, (status, value) in sorted(results.items())
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _post_state_result_digest(results: Mapping[int, str]) -> str:
    payload = "".join(
        f"{case_id:016x}:{digest}\n" for case_id, digest in sorted(results.items())
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _validate_target_post_state(
    *,
    profile: str,
    descriptor: run_memory_case.MemoryCaseDescriptor,
    record: Mapping[str, object],
    expected: ExpectedCase,
) -> str:
    """Reparse and bind the complete target bytes, then compare the model digest."""
    context = f"{profile}/{_hex(descriptor.case_id)}"
    uart = record.get("uart")
    if not isinstance(uart, str):
        raise Gate5Failure(
            "target-record-binding-failure", context, "run record lacks its UART transcript"
        )
    try:
        _outcome, regions, _canaries = run_memory_case.validate_transcript(
            uart.encode("ascii"), descriptor
        )
        observed = run_memory_case.final_memory_sha256(regions)
    except (UnicodeEncodeError, Core0Error, ValueError) as error:
        raise Gate5Failure("target-protocol-failure", context, str(error)) from error

    region_records = [
        {
            "id": region.region_id,
            "name": str(run_memory_case.REGIONS_BY_ID[region.region_id]["name"]),
            "bytes": len(region.data),
            "sha256": hashlib.sha256(region.data).hexdigest(),
        }
        for region in regions
    ]
    if (
        record.get("final_memory_sha256") != observed
        or record.get("post_state_bytes") != sum(len(region.data) for region in regions)
        or record.get("regions") != region_records
    ):
        raise Gate5Failure(
            "target-record-binding-failure",
            context,
            "run record post-state metadata differs from its complete UART region frames",
        )
    if observed != expected.final_memory_sha256:
        raise Gate5Failure(
            "lowering-or-codegen-mismatch",
            context,
            f"root={descriptor.root}, args={descriptor.args!r}, target post-memory="
            f"{observed}, independent-model={expected.final_memory_sha256}",
        )
    return observed


def _run_target_profile(
    *,
    root: Path,
    profile: str,
    output: Path,
    descriptors: tuple[run_memory_case.MemoryCaseDescriptor, ...],
    expected_cases: Mapping[int, ExpectedCase],
    qemu_timeout: float,
) -> dict[str, object]:
    results: dict[int, tuple[int, int]] = {}
    post_states: dict[int, str] = {}
    run_records: list[dict[str, object]] = []
    image = output / "image.elf"
    image_hash = sha256(image)
    runs = output / "runs"
    for descriptor in descriptors:
        record = _target_stage(
            profile,
            descriptor.case_id,
            lambda descriptor=descriptor: run_memory_case.run_case(
                root=root,
                image=image,
                output_dir=runs,
                descriptor=descriptor,
                timeout_seconds=qemu_timeout,
            ),
        )
        expected = expected_cases[descriptor.case_id]
        outcome = record.get("outcome")
        if not isinstance(outcome, dict):
            raise Gate5Failure(
                "target-protocol-failure",
                f"{profile}/{_hex(descriptor.case_id)}",
                "run record lacks an outcome object",
            )
        try:
            observed = (int(outcome["status"]), int(str(outcome["value"]), 16))
        except (KeyError, TypeError, ValueError) as error:
            raise Gate5Failure(
                "target-protocol-failure",
                f"{profile}/{_hex(descriptor.case_id)}",
                f"run outcome is malformed: {outcome!r}",
            ) from error
        wanted = (expected.status, expected.value)
        if observed != wanted:
            raise Gate5Failure(
                "lowering-or-codegen-mismatch",
                f"{profile}/{_hex(descriptor.case_id)}",
                f"root={descriptor.root}, args={descriptor.args!r}, "
                f"target={observed!r}, independent-model={wanted!r}",
            )
        post_state = _validate_target_post_state(
            profile=profile,
            descriptor=descriptor,
            record=record,
            expected=expected,
        )
        if descriptor.case_id in results:
            raise Gate5Failure(
                "target-protocol-failure",
                profile,
                f"duplicate target result for {_hex(descriptor.case_id)}",
            )

        expected_canaries = [
            {"id": item[0], "low": _hex(item[1]), "high": _hex(item[2])}
            for item in run_memory_case.expected_canary_words(descriptor)
        ]
        if record.get("canaries") != expected_canaries or len(expected_canaries) != 10:
            raise Gate5Failure(
                "canary-integrity-failure",
                f"{profile}/{_hex(descriptor.case_id)}",
                "run record does not preserve all ten exact boundary canaries",
            )
        if (
            record.get("descriptor") != run_memory_case.descriptor_json(descriptor)
            or record.get("image_sha256") != image_hash
            or record.get("qemu_returncode") != 0
        ):
            raise Gate5Failure(
                "target-record-binding-failure",
                f"{profile}/{_hex(descriptor.case_id)}",
                "run record is not bound to its descriptor, image, and zero QEMU exit",
            )
        results[descriptor.case_id] = observed
        post_states[descriptor.case_id] = post_state
        run_records.append(
            {
                "case_id": _hex(descriptor.case_id),
                "root": descriptor.root,
                "status": observed[0],
                "value": _hex(observed[1]),
                "canaries_verified": len(expected_canaries),
                "post_state_bytes": record.get("post_state_bytes"),
                "final_memory_sha256": post_state,
                "uart_sha256": record.get("uart_sha256"),
                "elapsed_seconds": record.get("elapsed_seconds"),
            }
        )
    if set(results) != set(expected_cases):
        raise Gate5Failure(
            "target-protocol-failure", profile, "target result IDs differ from the exact corpus"
        )
    oracle = {
        case_id: (expected.status, expected.value)
        for case_id, expected in expected_cases.items()
    }
    if results != oracle:
        raise Gate5Failure(
            "lowering-or-codegen-mismatch", profile, "target results differ from the oracle"
        )
    expected_post_states = {
        case_id: expected.final_memory_sha256
        for case_id, expected in expected_cases.items()
    }
    if post_states != expected_post_states:
        raise Gate5Failure(
            "lowering-or-codegen-mismatch",
            profile,
            "target complete post-memory states differ from the independent model",
        )
    return {
        "fresh_qemu_boots": len(run_records),
        "case_count": len(results),
        "model_matches": len(results),
        "post_state_model_matches": len(post_states),
        "post_state_bytes_per_boot": sum(
            int(spec["length"]) for spec in run_memory_case.REGION_SPECS
        ),
        "canaries_per_boot": len(run_memory_case.CANARY_SPECS),
        "canary_observations": len(run_records) * len(run_memory_case.CANARY_SPECS),
        "result_sha256": _result_digest(results),
        "post_state_result_sha256": _post_state_result_digest(post_states),
        "image_sha256": image_hash,
        "run_records": run_records,
    }


def check_gate5(
    *,
    root: Path,
    work: Path,
    clean: bool,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    """Execute the complete Gate 5 acceptance and return its PASS record."""
    _stage(
        "work-directory-failure",
        _relative(work, root),
        lambda: (
            invalidate_output_file(work / "gate5-results.json", root),
            prepare_output_directory(work, root, clean=clean),
        ),
    )

    corpus_dir = work / "corpus"
    corpus = _stage(
        "corpus-generation-failure",
        gate5_corpus.PROFILE,
        lambda: gate5_corpus.generate(corpus_dir),
    )
    _stage(
        "corpus-validation-failure",
        gate5_corpus.PROFILE,
        lambda: gate5_corpus.validate_corpus(corpus),
    )
    if corpus.get("root_count") != 26 or corpus.get("case_count") != 52:
        raise Gate5Failure(
            "corpus-validation-failure",
            gate5_corpus.PROFILE,
            "Gate 5 requires exactly 26 roots and 52 cases",
        )
    suite_id = int(str(corpus["suite_id"]), 16)
    source_seed = int(str(corpus["source_seed"]), 16)
    runtime_seed = int(str(corpus["runtime_seed"]), 16)
    expected_cases = _stage(
        "independent-model-failure",
        gate5_corpus.PROFILE,
        lambda: _expected_cases(corpus),
    )

    outputs: dict[str, Path] = {}
    manifests: dict[str, dict[str, object]] = {}
    profiles: dict[str, dict[str, object]] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = work / profile
        outputs[profile] = output
        build_record = _stage(
            "compile-or-link-failure",
            profile,
            lambda profile=profile, output=output, index=index: build_memory_suite(
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
                load_json(output / "memory-suite-manifest.json"),
                suite_id=suite_id,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
            ),
        )
        manifests[profile] = manifest
        pre_ir_audit = _stage(
            "memory-pre-ir-rejection",
            profile,
            lambda output=output, manifest=manifest: audit_memory.validate_memory_pre_ir(
                manifest,
                (output / "program.ll").read_text(encoding="utf-8"),
                require_volatile=True,
            ),
        )
        artifact_audit = _stage(
            "provenance-or-closure-rejection",
            profile,
            lambda output=output: audit_core0.audit(
                output, root, policy=audit_core0.TEST_MEMORY_SUITE_POLICY
            ),
        )
        if artifact_audit.get("memory_ir_audit") != pre_ir_audit:
            raise Gate5Failure(
                "audit-composition-failure",
                profile,
                "artifact audit and standalone memory pre-IR audit records differ",
            )
        inventory = _stage(
            "artifact-inventory-failure",
            profile,
            lambda output=output: _artifact_inventory(root, output),
        )
        profiles[profile] = {
            "build": build_record,
            "audit": artifact_audit,
            "memory_pre_ir_audit": pre_ir_audit,
            "artifacts": inventory,
        }

    profile_identity = _stage(
        "profile-source-identity-rejection",
        "O0/O2",
        lambda: _verify_profile_source_identity(
            root=root, outputs=outputs, manifests=manifests
        ),
    )
    descriptors = _stage(
        "descriptor-manifest-rejection",
        gate5_corpus.PROFILE,
        lambda: _load_descriptors(
            corpus_dir=corpus_dir,
            manifest=manifests["O0"],
            expected_cases=expected_cases,
            suite_id=suite_id,
            source_seed=source_seed,
            runtime_seed=runtime_seed,
        ),
    )

    rejection_cases = _stage(
        "rejection-manifest-failure",
        gate5_corpus.PROFILE,
        lambda: _load_rejections(
            root / "examples/foundation/gate5-reject/rejections.json", root
        ),
    )
    rejection_records = _stage(
        "frontend-rejection-failure",
        gate5_corpus.PROFILE,
        lambda: _run_rejections(
            rejection_cases,
            root=root,
            output_dir=work / "rejections",
            timeout_seconds=timeout_seconds,
        ),
    )
    memory_lemmas = _stage(
        "memory-lemma-check-failure",
        MEMORY_LEMMA_NAMESPACE,
        lambda: _check_memory_lemmas(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )
    pinned_semantics = _stage(
        "pinned-memory-semantics-failure",
        gate5_corpus.PROFILE,
        lambda: _check_pinned_memory_semantics(
            root=root, work=work, timeout_seconds=timeout_seconds
        ),
    )
    mutation_matrix = _stage(
        "memory-mutation-detection-failure",
        "O0/program.ll",
        lambda: _run_mutation_matrix(
            manifests["O0"], outputs["O0"].joinpath("program.ll").read_text(encoding="utf-8")
        ),
    )

    for profile in ("O0", "O2"):
        profiles[profile]["target"] = _run_target_profile(
            root=root,
            profile=profile,
            output=outputs[profile],
            descriptors=descriptors,
            expected_cases=expected_cases,
            qemu_timeout=qemu_timeout,
        )

    provenance = _stage(
        "provenance-rejection",
        "O0",
        lambda: load_json(outputs["O0"] / "provenance.json"),
    )
    if not isinstance(provenance, dict):
        raise Gate5Failure("provenance-rejection", "O0", "provenance is malformed")
    oracle_results = {
        case_id: (expected.status, expected.value)
        for case_id, expected in expected_cases.items()
    }
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "gate": 5,
        "source_commit": provenance.get("source_commit"),
        "contract_version": gate5_corpus.PROFILE,
        "test_abi": gate5_corpus.TEST_ABI,
        "checked_result": audit_memory.CHECKED_RESULT_CONTRACT,
        "suite_id": corpus["suite_id"],
        "seeds": {
            "source_generation": corpus["source_seed"],
            "runtime_inputs": corpus["runtime_seed"],
            "algorithm": (
                "closed Gate 5 catalog with deterministic SHA-256 fixture streams keyed "
                "by suite, case, runtime seed, and region/canary label"
            ),
        },
        "corpus": {
            "path": _relative(corpus_dir / "gate5-cases.json", root),
            "sha256": sha256(corpus_dir / "gate5-cases.json"),
            "roots": len(gate5_corpus.ROOT_SPECS),
            "distinct_cases_per_profile": len(expected_cases),
            "fresh_boots_per_profile": len(descriptors),
            "descriptor_count": len(descriptors),
            "memory_contract": corpus["memory_contract"],
            "reachable_status_codes": sorted(
                {expected.status for expected in expected_cases.values()}
            ),
            "unreachable_catalogued_status_codes": [4],
        },
        "independent_model": {
            "implementation": "scripts/gate5_corpus.py::FiniteMemory/evaluate",
            "cases": len(oracle_results),
            "result_sha256": _result_digest(oracle_results),
            "post_state_result_sha256": _post_state_result_digest(
                {
                    case_id: expected.final_memory_sha256
                    for case_id, expected in expected_cases.items()
                }
            ),
            "event_observations": sum(
                expected.event_count for expected in expected_cases.values()
            ),
            "shared_assumption": (
                "the Python oracle independently implements the documented finite-memory "
                "contract; the pinned Lean model evaluates the original elaborated Action syntax"
            ),
        },
        "profiles": profiles,
        "profile_source_identity": profile_identity,
        "mutation_matrix": mutation_matrix,
        "memory_lemmas": memory_lemmas,
        "pinned_memory_semantics": pinned_semantics,
        "negative_cases": {
            "core0-v0.4": rejection_records,
            "legacy_profile_action_rejections": [
                record
                for record in rejection_records
                if record["name"] in {"v01-action", "v02-action", "v03-action"}
            ],
        },
        "counts": {
            "roots": len(gate5_corpus.ROOT_SPECS),
            "cases_per_profile": len(expected_cases),
            "fresh_qemu_boots_per_profile": len(descriptors),
            "qemu_boots_total": len(descriptors) * 2,
            "independent_model_target_matches": len(expected_cases) * 2,
            "complete_post_state_target_matches": len(expected_cases) * 2,
            "ordinary_region_bytes_per_boot": sum(
                int(spec["length"]) for spec in run_memory_case.REGION_SPECS
            ),
            "ordinary_region_bytes_observed": (
                len(descriptors)
                * 2
                * sum(int(spec["length"]) for spec in run_memory_case.REGION_SPECS)
            ),
            "canaries_per_boot": len(run_memory_case.CANARY_SPECS),
            "canary_observations": len(descriptors) * 2 * len(run_memory_case.CANARY_SPECS),
            "audited_pre_ir_accesses_per_profile": profiles["O0"][
                "memory_pre_ir_audit"
            ]["access_count"],
            "audited_pre_ir_range_checks_per_profile": profiles["O0"][
                "memory_pre_ir_audit"
            ]["range_check_count"],
            "manifest_mutants_detected": mutation_matrix["manifest_mutants_detected"],
            "ir_mutants_detected": mutation_matrix["ir_mutants_detected"],
            "frontend_rejections": len(rejection_records),
            "legacy_profile_rejections": 3,
            "memory_lemmas_checked": len(MEMORY_LEMMAS),
            "pinned_memory_probes": len(PINNED_MEMORY_RESULTS),
        },
        "security_interpretation": (
            "checked ordinary-RAM access inside one trusted M-mode image; this is not "
            "hardware isolation against arbitrary privileged machine code"
        ),
        "limitations": [
            "Finite differential tests and local model lemmas are not a compiler-correctness proof.",
            "The region API enforces checked access in compiled Core0 code, not an M-mode protection boundary.",
            "Gate 5 does not add compiled device drivers, traps, interrupts, a scheduler, or a managed runtime.",
            "This result does not complete G1 or G2.",
        ],
    }
    _stage(
        "evidence-write-failure",
        _relative(work / "gate5-results.json", root),
        lambda: write_json(work / "gate5-results.json", report),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir", type=Path, default=Path("build/foundation/check/gate5")
    )
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--qemu-timeout", type=float, default=10.0)
    ns = parser.parse_args()
    root = repo_root()
    work = (
        (root / ns.work_dir).resolve()
        if not ns.work_dir.is_absolute()
        else ns.work_dir.resolve()
    )
    try:
        report = check_gate5(
            root=root,
            work=work,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
            qemu_timeout=ns.qemu_timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FOUNDATION GATE 5 CHECK FAIL: {error}", file=sys.stderr)
        return 1
    counts = report.get("counts")
    if not isinstance(counts, dict):
        print("FOUNDATION GATE 5 CHECK FAIL: PASS report lacks counts", file=sys.stderr)
        return 1
    print(
        "FOUNDATION GATE 5 PASS: "
        f"{counts['roots']} roots; {counts['cases_per_profile']} cases/profile; "
        f"{counts['qemu_boots_total']} fresh QEMU boots; "
        f"{counts['canary_observations']} canary observations"
    )
    print(f"evidence: {work / 'gate5-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
