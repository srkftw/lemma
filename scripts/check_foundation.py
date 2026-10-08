#!/usr/bin/env python3
"""Fail-closed acceptance driver for the incremental Task 002 foundation gates.

Only gates whose complete construction and evidence checks exist are accepted by
this driver. Gate 1 exercises quarantined compiler faults; Gate 2 adds the
versioned typed multi-root source/model/RV64 conformance pipeline; Gate 3 adds
the versioned structured-CFG scalar path; Gate 4 adds checked runtime-counted,
statically bounded scalar iteration; Gate 5 adds checked ordinary-RAM actions
with an explicit finite-memory model. All routes use genuine Lean elaboration,
audited images, and QEMU. Gate 6 adds the explicitly versioned compiled UART
device session, ordered MMIO audit, and live two-request interaction.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import audit_core0
from build_core0 import build, invalidate_output_file, prepare_output_directory
from core0_common import (
    Core0Error,
    checked,
    load_json,
    repo_root,
    require_tools,
    run_bounded,
    sha256,
    write_json,
)
from run_core0 import run_case
from check_foundation_gate2 import Gate2Failure, check_gate2
from check_foundation_gate3 import Gate3Failure, check_gate3
from check_foundation_gate4 import Gate4Failure, check_gate4
from check_foundation_gate5 import Gate5Failure, check_gate5
from check_foundation_gate6 import Gate6Failure, check_gate6


U64_MAX = (1 << 64) - 1
REFERENCE_RESULT = re.compile(r"CORE0_REFERENCE:([0-9a-f]{16})")
LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
FAULT_IDS = (
    "ult-as-ule",
    "ult-as-slt",
    "add-as-sub",
    "zext-as-sext",
    "trunc-high-half",
    "swap-call-args",
)
EXPECTED_TARGETS = {
    "ult-as-ule": "Lemma.Examples.Foundation.CompilerFaults.strictLt",
    "ult-as-slt": "Lemma.Examples.Foundation.CompilerFaults.unsignedLt",
    "add-as-sub": "Lemma.Examples.Foundation.CompilerFaults.addPair",
    "zext-as-sext": "Lemma.Examples.Foundation.CompilerFaults.widen32",
    "trunc-high-half": "Lemma.Examples.Foundation.CompilerFaults.truncate32",
    "swap-call-args": "Lemma.Examples.Foundation.CompilerFaults.callOrder",
}
FOUNDATION_SOURCE = Path("examples/foundation/CompilerFaults.lean")
T = TypeVar("T")


class Gate1Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _pipeline_failure_category(stage: str, detail: str) -> str:
    lowered = detail.lower()
    if "timed out" in lowered:
        return "timeout"
    if stage == "build":
        if "ld.lld" in detail:
            return "link-failure"
        if "missing" in lowered or "omitted artifacts" in lowered or "incomplete" in lowered:
            return "artifact-failure"
        return "compile-failure"
    if stage == "audit":
        return "provenance-or-closure-rejection"
    if stage == "run":
        if (
            "malformed" in lowered
            or "truncated" in lowered
            or "case id" in lowered
            or "unexpected stderr" in lowered
        ):
            return "protocol-failure"
        if "missing" in lowered or "required json" in lowered:
            return "artifact-failure"
        return "boot-failure"
    return f"{stage}-failure"


def _pipeline_stage(stage: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate1Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        detail = str(error)
        raise Gate1Failure(
            _pipeline_failure_category(stage, detail), context, detail
        ) from error


@dataclass(frozen=True)
class CompilerFaultCase:
    name: str
    case_id: int
    fault_id: str
    target_source: str
    args: tuple[int, int, int]
    expected_clean: int
    expected_mutant: int
    covers: tuple[str, ...]


@dataclass(frozen=True)
class CompilerFaultCorpus:
    root: str
    cases: tuple[CompilerFaultCase, ...]


@dataclass(frozen=True)
class RejectionCase:
    name: str
    path: Path
    required_fragments: tuple[str, ...]


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from the schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _u64(value: object, context: str) -> int:
    if not isinstance(value, str):
        raise Core0Error(f"{context} must be a string-encoded UInt64")
    try:
        parsed = int(value, 0)
    except ValueError as error:
        raise Core0Error(f"{context} is not a UInt64: {value!r}") from error
    if parsed < 0 or parsed > U64_MAX:
        raise Core0Error(f"{context} is outside UInt64: {value!r}")
    return parsed


def load_compiler_fault_corpus(path: Path) -> CompilerFaultCorpus:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("compiler-fault corpus is not an object")
    _exact_keys(raw, {"schema_version", "root", "cases"}, "compiler-fault corpus")
    if raw.get("schema_version") != 1:
        raise Core0Error("compiler-fault corpus has an unsupported schema")
    root = raw.get("root")
    if not isinstance(root, str) or LEAN_IDENTIFIER.fullmatch(root) is None:
        raise Core0Error("compiler-fault corpus root is not a valid Lean identifier")
    values = raw.get("cases")
    if not isinstance(values, list):
        raise Core0Error("compiler-fault corpus cases must be an array")
    cases: list[CompilerFaultCase] = []
    names: set[str] = set()
    case_ids: set[int] = set()
    fault_ids: set[str] = set()
    expected_case_keys = {
        "name",
        "case_id",
        "fault",
        "target_source",
        "args",
        "expected_clean",
        "expected_mutant",
        "covers",
    }
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"compiler-fault case #{index} is not an object")
        _exact_keys(item, expected_case_keys, f"compiler-fault case #{index}")
        name = item.get("name")
        fault_id = item.get("fault")
        target_source = item.get("target_source")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"compiler-fault case #{index} has an empty or duplicate name")
        if not isinstance(fault_id, str) or fault_id not in FAULT_IDS:
            raise Core0Error(f"compiler-fault case {name} has an unknown closed fault ID")
        if fault_id in fault_ids:
            raise Core0Error(f"duplicate compiler fault ID: {fault_id}")
        if (
            not isinstance(target_source, str)
            or LEAN_IDENTIFIER.fullmatch(target_source) is None
            or target_source != EXPECTED_TARGETS[fault_id]
        ):
            raise Core0Error(f"compiler-fault case {name} has the wrong exact target source")
        case_id = _u64(item.get("case_id"), f"compiler-fault case {name} id")
        if case_id in case_ids:
            raise Core0Error(f"duplicate compiler-fault case id: 0x{case_id:016x}")
        raw_args = item.get("args")
        if not isinstance(raw_args, list) or len(raw_args) != 3:
            raise Core0Error(f"compiler-fault case {name} must contain exactly three args")
        args = tuple(_u64(value, f"compiler-fault case {name} arg") for value in raw_args)
        expected_clean = _u64(
            item.get("expected_clean"), f"compiler-fault case {name} clean result"
        )
        expected_mutant = _u64(
            item.get("expected_mutant"), f"compiler-fault case {name} mutant result"
        )
        if expected_clean == expected_mutant:
            raise Core0Error(f"compiler-fault case {name} is not behaviorally distinguishing")
        covers = item.get("covers")
        if (
            not isinstance(covers, list)
            or not covers
            or any(not isinstance(label, str) or not label for label in covers)
            or len(set(covers)) != len(covers)
        ):
            raise Core0Error(f"compiler-fault case {name} has invalid coverage labels")
        names.add(name)
        case_ids.add(case_id)
        fault_ids.add(fault_id)
        cases.append(
            CompilerFaultCase(
                name=name,
                case_id=case_id,
                fault_id=fault_id,
                target_source=target_source,
                args=args,
                expected_clean=expected_clean,
                expected_mutant=expected_mutant,
                covers=tuple(covers),
            )
        )
    if fault_ids != set(FAULT_IDS) or len(cases) != len(FAULT_IDS):
        raise Core0Error(
            "compiler-fault corpus must contain each closed fault exactly once: "
            f"observed={sorted(fault_ids)!r}"
        )
    return CompilerFaultCorpus(root=root, cases=tuple(cases))


def _safe_repo_lean_file(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise Core0Error(f"rejection fixture must be repository-relative: {value!r}")
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise Core0Error(f"rejection fixture escapes the repository: {value}") from error
    if resolved.suffix != ".lean" or not resolved.is_file():
        raise Core0Error(f"rejection fixture is missing or not Lean source: {value}")
    return resolved


def load_compiler_fault_rejections(path: Path, root: Path) -> tuple[RejectionCase, ...]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("compiler-fault rejection manifest is not an object")
    _exact_keys(raw, {"schema_version", "cases"}, "compiler-fault rejection manifest")
    if raw.get("schema_version") != 1:
        raise Core0Error("compiler-fault rejection manifest has an unsupported schema")
    values = raw.get("cases")
    if not isinstance(values, list) or not values:
        raise Core0Error("compiler-fault rejection manifest is empty")
    cases: list[RejectionCase] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"compiler-fault rejection #{index} is not an object")
        _exact_keys(
            item,
            {"name", "path", "required_fragments"},
            f"compiler-fault rejection #{index}",
        )
        name = item.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"compiler-fault rejection #{index} has an invalid name")
        fixture = _safe_repo_lean_file(root, item.get("path"))
        reject_root = (root / "examples/foundation/reject").resolve()
        try:
            fixture.relative_to(reject_root)
        except ValueError as error:
            raise Core0Error(f"compiler-fault rejection is outside {reject_root}: {fixture}") from error
        if fixture in paths:
            raise Core0Error(f"duplicate compiler-fault rejection fixture: {fixture}")
        fragments = item.get("required_fragments")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
        ):
            raise Core0Error(f"compiler-fault rejection {name} has invalid diagnostics")
        names.add(name)
        paths.add(fixture)
        cases.append(RejectionCase(name, fixture, tuple(fragments)))
    discovered = set(reject_root.glob("*.lean"))
    if paths != discovered:
        raise Core0Error(
            "compiler-fault rejection manifest/file set mismatch: "
            f"untested={sorted(str(value.relative_to(root)) for value in discovered - paths)!r}, "
            f"stale={sorted(str(value.relative_to(root)) for value in paths - discovered)!r}"
        )
    return tuple(cases)


def classify_mutant_outcome(
    *,
    compiled: bool,
    linked: bool,
    audited: bool,
    booted: bool,
    protocol_valid: bool,
    oracle: int,
    observed: int | None,
    expected_mutant: int,
) -> str:
    """Return the one precise outcome category used by Gate 1 evidence."""
    for completed, category in (
        (compiled, "compile-failure"),
        (linked, "link-failure"),
        (audited, "audit-failure"),
        (booted, "boot-failure"),
        (protocol_valid, "protocol-failure"),
    ):
        if not completed:
            return category
    if observed is None:
        return "missing-result"
    if observed == oracle:
        return "non-distinguishing-mutant"
    if observed != expected_mutant:
        return "unexpected-wrong-result"
    return "verified-behavioral-mismatch"


def require_intended_rejection(
    *, returncode: int, output: str, required_fragments: tuple[str, ...]
) -> None:
    """Accept a negative fixture only for its declared diagnostic reason."""
    if returncode == 0:
        raise Core0Error("negative fixture unexpectedly passed")
    absent = [fragment for fragment in required_fragments if fragment not in output]
    if absent:
        raise Core0Error(f"negative fixture lacked intended diagnostic fragments: {absent!r}")


def _run_compiler_fault_rejections(
    cases: tuple[RejectionCase, ...],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir()
    records: list[dict[str, object]] = []
    for case in cases:
        case_output = output_dir / case.name
        case_output.mkdir()
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str(case_output.resolve())
        result = run_bounded(
            ("lake", "env", "lean", str(case.path.relative_to(root))),
            cwd=root,
            timeout_seconds=timeout_seconds,
            env=environment,
        )
        combined = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode(
            "utf-8", errors="replace"
        )
        log_path = case_output / "diagnostic.txt"
        log_path.write_text(combined, encoding="utf-8")
        require_intended_rejection(
            returncode=result.returncode,
            output=combined,
            required_fragments=case.required_fragments,
        )
        records.append(
            {
                "name": case.name,
                "path": str(case.path.relative_to(root)),
                "source_sha256": sha256(case.path),
                "returncode": result.returncode,
                "required_fragments": list(case.required_fragments),
                "diagnostic_log": str(log_path.relative_to(root)),
                "diagnostic_sha256": sha256(log_path),
            }
        )
    return records


def _write_export_driver(
    path: Path, corpus: CompilerFaultCorpus, fault: CompilerFaultCase | None
) -> None:
    if fault is None:
        source = (
            "import Lemma.Compiler.Export\n"
            "import examples.foundation.CompilerFaults\n\n"
            f"#core0_export {corpus.root}\n"
        )
    else:
        source = (
            "import Lemma.Compiler.Test.Export\n"
            "import examples.foundation.CompilerFaults\n\n"
            f'#core0_export_fault "{fault.fault_id}" {corpus.root} {fault.target_source}\n'
        )
    path.write_text(source, encoding="utf-8")


def _evaluate_reference(
    corpus: CompilerFaultCorpus, *, root: Path, source_dir: Path, timeout_seconds: float
) -> list[int]:
    reference = source_dir / "Reference.lean"
    lines = ["import Lemma.Compiler.Export", "import examples.foundation.CompilerFaults", ""]
    for case in corpus.cases:
        args = " ".join(f'"{value}"' for value in case.args)
        lines.append(f"#core0_eval {corpus.root} {args}")
    lines.append("")
    reference.write_text("\n".join(lines), encoding="utf-8")
    result = checked(
        ("lake", "env", "lean", str(reference)),
        cwd=root,
        timeout_seconds=timeout_seconds,
    )
    stdout = result.stdout.decode("utf-8", errors="strict")
    stderr = result.stderr.decode("utf-8", errors="strict")
    (source_dir / "reference.stdout").write_text(stdout, encoding="utf-8")
    (source_dir / "reference.stderr").write_text(stderr, encoding="utf-8")
    matches = REFERENCE_RESULT.findall(stdout + stderr)
    if len(matches) != len(corpus.cases):
        raise Core0Error(
            f"Lean checked-model oracle produced {len(matches)} results for "
            f"{len(corpus.cases)} compiler-fault cases"
        )
    results = [int(value, 16) for value in matches]
    for case, observed in zip(corpus.cases, results, strict=True):
        if observed != case.expected_clean:
            raise Core0Error(
                f"checked-model oracle disagrees with the immutable corpus for {case.name}: "
                f"0x{observed:016x} != 0x{case.expected_clean:016x}"
            )
    return results


def _compile_foundation_source(*, root: Path, timeout_seconds: float) -> dict[str, object]:
    relative_olean = Path(".lake/build/lib/lean/examples/foundation/CompilerFaults.olean")
    (root / relative_olean).parent.mkdir(parents=True, exist_ok=True)
    command = (
        "lake",
        "env",
        "lean",
        "-o",
        str(relative_olean),
        str(FOUNDATION_SOURCE),
    )
    result = checked(
        command,
        cwd=root,
        timeout_seconds=timeout_seconds,
    )
    olean = root / relative_olean
    if not olean.is_file() or olean.stat().st_size == 0:
        raise Core0Error("foundation source elaboration did not produce a nonempty olean")
    return {
        "command": list(command),
        "returncode": result.returncode,
        "source": str(FOUNDATION_SOURCE),
        "source_sha256": sha256(root / FOUNDATION_SOURCE),
        "olean": str(relative_olean),
        "olean_sha256": sha256(olean),
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
    }


def _audit(
    directory: Path,
    root: Path,
    *,
    category: str,
    expected_fault: CompilerFaultCase | None = None,
    clean_control_directory: Path | None = None,
) -> dict[str, object]:
    """Call the explicit test audit policy without exposing it in release CLIs."""
    return audit_core0.audit(
        directory,
        root,
        policy=category,
        expected_fault=None if expected_fault is None else expected_fault.fault_id,
        expected_target_source=None if expected_fault is None else expected_fault.target_source,
        clean_control_directory=clean_control_directory,
    )


def _expect_audit_failure(
    name: str,
    action: Callable[[], object],
    required_fragments: tuple[str, ...],
) -> dict[str, object]:
    try:
        action()
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error(f"audit regression {name} unexpectedly passed")
    absent = [fragment for fragment in required_fragments if fragment not in diagnostic]
    if absent:
        raise Core0Error(
            f"audit regression {name} failed for an unrelated reason; "
            f"missing={absent!r}; diagnostic={diagnostic}"
        )
    return {"name": name, "status": "pass", "expected_failure": diagnostic}


def _run_audit_regressions(
    *,
    root: Path,
    work: Path,
    control_directory: Path,
    alternate_control_directory: Path,
    baseline_mutant: Path,
    stale_mutant: Path,
    baseline_case: CompilerFaultCase,
) -> list[dict[str, object]]:
    """Exercise policy separation plus forged, incomplete, stale, and tampered evidence."""
    regressions: list[dict[str, object]] = []
    regressions.append(
        _expect_audit_failure(
            "release-rejects-mutant",
            lambda: audit_core0.audit(baseline_mutant, root),
            ("release audit rejects", "compiler-mutation.json"),
        )
    )
    regressions.append(
        _expect_audit_failure(
            "mutant-rejects-control",
            lambda: audit_core0.audit(
                control_directory,
                root,
                policy="test-compiler-mutant",
                expected_fault=baseline_case.fault_id,
                expected_target_source=baseline_case.target_source,
                clean_control_directory=alternate_control_directory,
            ),
            ("missing audit artifacts", "compiler-mutation.json"),
        )
    )

    regression_root = work / "audit-regressions"
    regression_root.mkdir()

    def copied(name: str) -> Path:
        destination = regression_root / name
        shutil.copytree(baseline_mutant, destination)
        return destination

    def mutant_audit(directory: Path) -> dict[str, object]:
        return audit_core0.audit(
            directory,
            root,
            policy="test-compiler-mutant",
            expected_fault=baseline_case.fault_id,
            expected_target_source=baseline_case.target_source,
            clean_control_directory=control_directory,
        )

    forged = copied("forged-manifest")
    forged_manifest = load_json(forged / "compiler-mutation.json")
    assert isinstance(forged_manifest, dict)
    forged_manifest["production_selectable"] = True
    write_json(forged / "compiler-mutation.json", forged_manifest)
    regressions.append(
        _expect_audit_failure(
            "forged-manifest",
            lambda: mutant_audit(forged),
            ("non-production-selectable",),
        )
    )

    incomplete = copied("incomplete-manifest")
    incomplete_manifest = load_json(incomplete / "compiler-mutation.json")
    assert isinstance(incomplete_manifest, dict)
    del incomplete_manifest["after"]
    write_json(incomplete / "compiler-mutation.json", incomplete_manifest)
    regressions.append(
        _expect_audit_failure(
            "incomplete-manifest",
            lambda: mutant_audit(incomplete),
            ("fields differ from the schema", "after"),
        )
    )

    stale = copied("stale-manifest")
    shutil.copy2(stale_mutant / "compiler-mutation.json", stale / "compiler-mutation.json")
    stale_provenance = load_json(stale / "provenance.json")
    assert isinstance(stale_provenance, dict)
    stale_fault = stale_provenance.get("compiler_fault")
    assert isinstance(stale_fault, dict)
    stale_fault["manifest_sha256"] = sha256(stale / "compiler-mutation.json")
    write_json(stale / "provenance.json", stale_provenance)
    regressions.append(
        _expect_audit_failure(
            "stale-manifest",
            lambda: mutant_audit(stale),
            ("fault differs from the requested test build",),
        )
    )

    tampered_manifest = copied("tampered-manifest")
    tampered_value = load_json(tampered_manifest / "compiler-mutation.json")
    assert isinstance(tampered_value, dict)
    tampered_value["after"] = str(tampered_value["after"]).replace(" = sub ", " = xor ")
    write_json(tampered_manifest / "compiler-mutation.json", tampered_value)
    tampered_provenance = load_json(tampered_manifest / "provenance.json")
    assert isinstance(tampered_provenance, dict)
    tampered_fault = tampered_provenance.get("compiler_fault")
    assert isinstance(tampered_fault, dict)
    tampered_fault["manifest_sha256"] = sha256(tampered_manifest / "compiler-mutation.json")
    write_json(tampered_manifest / "provenance.json", tampered_provenance)
    regressions.append(
        _expect_audit_failure(
            "tampered-manifest",
            lambda: mutant_audit(tampered_manifest),
            ("before/after relationship is malformed",),
        )
    )

    tampered_ir = copied("tampered-program-ir")
    ir_path = tampered_ir / "program.ll"
    ir_path.write_text(ir_path.read_text(encoding="utf-8") + "; tampered\n", encoding="utf-8")
    regressions.append(
        _expect_audit_failure(
            "tampered-program-ir",
            lambda: mutant_audit(tampered_ir),
            ("compiler-fault provenance hash mismatch for program.ll",),
        )
    )
    return regressions


def check_gate1(
    *,
    root: Path,
    work: Path,
    corpus_path: Path,
    rejections_path: Path,
    clean: bool,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    # Invalidate the canonical PASS record before even descriptor/tool checks.
    # A failed rerun therefore cannot be mistaken for current evidence.
    invalidate_output_file(work / "gate1-results.json", root)
    # Validate the immutable descriptor before tool discovery or artifact creation.
    corpus = load_compiler_fault_corpus(corpus_path)
    rejections = load_compiler_fault_rejections(rejections_path, root)
    require_tools()
    prepare_output_directory(work, root, clean=clean)
    source_dir = work / "sources"
    source_dir.mkdir()

    _pipeline_stage(
        "host-build",
        "Lemma.Compiler.Test.Export",
        lambda: checked(
            ("lake", "build", "Lemma.Compiler.Test.Export"),
            cwd=root,
            timeout_seconds=timeout_seconds,
        ),
    )
    foundation_compilation = _pipeline_stage(
        "source-elaboration",
        str(FOUNDATION_SOURCE),
        lambda: _compile_foundation_source(
            root=root, timeout_seconds=timeout_seconds
        ),
    )
    rejection_records = _pipeline_stage(
        "negative-fixture",
        "closed compiler-fault rejections",
        lambda: _run_compiler_fault_rejections(
            rejections,
            root=root,
            output_dir=work / "rejections",
            timeout_seconds=timeout_seconds,
        ),
    )
    reference_values = _pipeline_stage(
        "oracle",
        corpus.root,
        lambda: _evaluate_reference(
            corpus, root=root, source_dir=source_dir, timeout_seconds=timeout_seconds
        ),
    )

    foundation_source = root / FOUNDATION_SOURCE
    control_driver = source_dir / "Control.lean"
    _write_export_driver(control_driver, corpus, None)
    control_directories: dict[str, Path] = {}
    control_records: list[dict[str, object]] = []
    for optimization in ("O0", "O2"):
        directory = work / f"control-{optimization}"
        control_directories[optimization] = directory
        _pipeline_stage(
            "build",
            f"control/{optimization}",
            lambda: build(
                root=root,
                output_dir=directory,
                opt_level=optimization,
                export_source=control_driver,
                build_lean=False,
                timeout_seconds=timeout_seconds,
                artifact_category="test-compiler-control",
                elaboration_sources=(foundation_source,),
            ),
        )
        audit = _pipeline_stage(
            "audit",
            f"control/{optimization}",
            lambda: _audit(directory, root, category="test-compiler-control"),
        )
        cases: list[dict[str, object]] = []
        for case, oracle in zip(corpus.cases, reference_values, strict=True):
            run = _pipeline_stage(
                "run",
                f"control/{optimization}/{case.fault_id}",
                lambda: run_case(
                    root=root,
                    image=directory / "image.elf",
                    output_dir=directory / "runs",
                    case_id=case.case_id,
                    args=case.args,
                    timeout_seconds=qemu_timeout,
                ),
            )
            observed = int(str(run["result"]), 0)
            if observed != oracle:
                raise Core0Error(
                    f"clean-control-mismatch[{optimization}/{case.fault_id}]: "
                    f"0x{observed:016x} != 0x{oracle:016x}"
                )
            cases.append(
                {
                    "name": case.name,
                    "fault_id": case.fault_id,
                    "case_id": f"0x{case.case_id:016x}",
                    "args": [f"0x{value:016x}" for value in case.args],
                    "oracle": f"0x{oracle:016x}",
                    "observed": f"0x{observed:016x}",
                    "run_record": str(
                        (directory / "runs" / f"run-{case.case_id:016x}.json").relative_to(root)
                    ),
                }
            )
        control_records.append(
            {
                "optimization": optimization,
                "artifact_category": audit.get("artifact_category"),
                "directory": str(directory.relative_to(root)),
                "image_sha256": sha256(directory / "image.elf"),
                "audit_sha256": sha256(directory / "audit.json"),
                "cases": cases,
            }
        )

    if sha256(control_directories["O0"] / "core0-manifest.json") != sha256(
        control_directories["O2"] / "core0-manifest.json"
    ):
        raise Core0Error("O0/O2 clean-control target manifests are not byte-identical")

    mutant_records: list[dict[str, object]] = []
    mutant_directories: dict[tuple[str, str], Path] = {}
    for case, oracle in zip(corpus.cases, reference_values, strict=True):
        driver = source_dir / f"Mutant-{case.fault_id}.lean"
        _write_export_driver(driver, corpus, case)
        for optimization in ("O0", "O2"):
            directory = work / f"mutant-{case.fault_id}-{optimization}"
            mutant_directories[(case.fault_id, optimization)] = directory
            _pipeline_stage(
                "build",
                f"mutant/{case.fault_id}/{optimization}",
                lambda: build(
                    root=root,
                    output_dir=directory,
                    opt_level=optimization,
                    export_source=driver,
                    build_lean=False,
                    timeout_seconds=timeout_seconds,
                    artifact_category="test-compiler-mutant",
                    compiler_fault_manifest="compiler-mutation.json",
                    elaboration_sources=(foundation_source,),
                ),
            )
            audit = _pipeline_stage(
                "audit",
                f"mutant/{case.fault_id}/{optimization}",
                lambda: _audit(
                    directory,
                    root,
                    category="test-compiler-mutant",
                    expected_fault=case,
                    clean_control_directory=control_directories[optimization],
                ),
            )
            run = _pipeline_stage(
                "run",
                f"mutant/{case.fault_id}/{optimization}",
                lambda: run_case(
                    root=root,
                    image=directory / "image.elf",
                    output_dir=directory / "runs",
                    case_id=case.case_id,
                    args=case.args,
                    timeout_seconds=qemu_timeout,
                ),
            )
            observed = int(str(run["result"]), 0)
            outcome = classify_mutant_outcome(
                compiled=True,
                linked=True,
                audited=True,
                booted=True,
                protocol_valid=True,
                oracle=oracle,
                observed=observed,
                expected_mutant=case.expected_mutant,
            )
            if outcome != "verified-behavioral-mismatch":
                raise Core0Error(
                    f"{outcome}[{optimization}/{case.fault_id}]: "
                    f"oracle=0x{oracle:016x}, observed=0x{observed:016x}, "
                    f"expected-mutant=0x{case.expected_mutant:016x}"
                )
            mutation = load_json(directory / "compiler-mutation.json")
            mutant_records.append(
                {
                    "name": case.name,
                    "fault_id": case.fault_id,
                    "target_source": case.target_source,
                    "optimization": optimization,
                    "case_id": f"0x{case.case_id:016x}",
                    "args": [f"0x{value:016x}" for value in case.args],
                    "oracle": f"0x{oracle:016x}",
                    "expected_mutant": f"0x{case.expected_mutant:016x}",
                    "observed": f"0x{observed:016x}",
                    "outcome": outcome,
                    "pipeline": {
                        "compiled": True,
                        "linked": True,
                        "audited": True,
                        "booted": True,
                        "protocol_valid": True,
                    },
                    "artifact_category": audit.get("artifact_category"),
                    "directory": str(directory.relative_to(root)),
                    "program_ll_sha256": sha256(directory / "program.ll"),
                    "image_sha256": sha256(directory / "image.elf"),
                    "mutation_manifest_sha256": sha256(directory / "compiler-mutation.json"),
                    "audit_sha256": sha256(directory / "audit.json"),
                    "mutation": mutation,
                    "run_record": str(
                        (directory / "runs" / f"run-{case.case_id:016x}.json").relative_to(root)
                    ),
                }
            )

    expected_mutants = len(FAULT_IDS) * 2
    if len(mutant_records) != expected_mutants or any(
        record["outcome"] != "verified-behavioral-mismatch" for record in mutant_records
    ):
        raise Core0Error("Gate 1 did not produce the complete verified mutant matrix")

    baseline_case = next(case for case in corpus.cases if case.fault_id == "add-as-sub")
    audit_regressions = _run_audit_regressions(
        root=root,
        work=work,
        control_directory=control_directories["O0"],
        alternate_control_directory=control_directories["O2"],
        baseline_mutant=mutant_directories[("add-as-sub", "O0")],
        stale_mutant=mutant_directories[("zext-as-sext", "O0")],
        baseline_case=baseline_case,
    )
    compiled_olean = root / str(foundation_compilation["olean"])
    if sha256(compiled_olean) != foundation_compilation["olean_sha256"]:
        raise Core0Error("repeated foundation elaboration changed the imported olean bytes")

    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "task": "002-machine-foundation",
        "gate": 1,
        "scope": "quarantined incorrect-compiler detection; not all of G1 or G2",
        "corpus": str(corpus_path.relative_to(root)),
        "corpus_sha256": sha256(corpus_path),
        "rejection_manifest": str(rejections_path.relative_to(root)),
        "rejection_manifest_sha256": sha256(rejections_path),
        "source": str(foundation_source.relative_to(root)),
        "source_sha256": sha256(foundation_source),
        "root": corpus.root,
        "foundation_elaboration": foundation_compilation,
        "closed_fault_ids": list(FAULT_IDS),
        "counts": {
            "clean_control_builds": 2,
            "clean_control_qemu_boots": len(corpus.cases) * 2,
            "mutant_builds": len(mutant_records),
            "mutant_qemu_boots": len(mutant_records),
            "verified_behavioral_mismatches": len(mutant_records),
            "total_fresh_qemu_boots": len(corpus.cases) * 2 + len(mutant_records),
            "intended_rejections": len(rejection_records),
            "audit_regressions": len(audit_regressions),
        },
        "oracle": {
            "kind": "unchanged checked-Core0 executable semantics",
            "reference_driver": str((source_dir / "Reference.lean").relative_to(root)),
            "reference_driver_sha256": sha256(source_dir / "Reference.lean"),
            "results": [f"0x{value:016x}" for value in reference_values],
        },
        "controls": control_records,
        "mutants": mutant_records,
        "negative_cases": rejection_records,
        "audit_regressions": audit_regressions,
        "quarantine": {
            "production_cli_fault_selector": False,
            "production_audit_accepts_mutants": False,
            "runtime_input_selects_fault": False,
            "transform_stage": "structured-llvm-pre-optimization",
        },
        "limitations": [
            "The finite fault suite demonstrates detection of six seeded defects; it is not a compiler-correctness proof.",
            "Gate 1 uses the checked Core0 evaluator as its unchanged oracle; direct elaborated-source comparison is a Gate 2 obligation.",
            "This gate does not complete G1 or G2.",
        ],
    }
    write_json(work / "gate1-results.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--phase", type=int)
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--work-dir", type=Path, default=Path("build/foundation/check"))
    parser.add_argument(
        "--compiler-faults",
        type=Path,
        default=Path("tests/foundation/compiler_faults.json"),
    )
    parser.add_argument(
        "--compiler-fault-rejections",
        type=Path,
        default=Path("tests/foundation/compiler_fault_rejections.json"),
    )
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--qemu-timeout", type=float, default=5.0)
    ns = parser.parse_args()
    if ns.phase is not None and ns.phase not in {1, 2, 3, 4, 5, 6}:
        parser.error("only completed phases 1 through 6 are implemented; later gates fail closed")
    root = repo_root()

    def resolve(path: Path) -> Path:
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    work = resolve(ns.work_dir)
    selected_gate = ns.phase if ns.phase is not None else 1
    try:
        # `--all` owns this one exact aggregate output. Remove an earlier PASS
        # before either child gate starts so a failed cumulative rerun is fail-closed.
        if ns.all:
            invalidate_output_file(work / "all-results.json", root)
        # A new invocation supersedes the prior diagnostic regardless of scope.
        invalidate_output_file(work / "check-failure.json", root)
        if ns.all:
            gate1 = check_gate1(
                root=root,
                work=work / "gate1",
                corpus_path=resolve(ns.compiler_faults),
                rejections_path=resolve(ns.compiler_fault_rejections),
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            selected_gate = 2
            gate2 = check_gate2(
                root=root,
                work=work / "gate2",
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            selected_gate = 3
            gate3 = check_gate3(
                root=root,
                work=work / "gate3",
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            selected_gate = 4
            gate4 = check_gate4(
                root=root,
                work=work / "gate4",
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            selected_gate = 5
            gate5 = check_gate5(
                root=root,
                work=work / "gate5",
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            selected_gate = 6
            gate6 = check_gate6(
                root=root,
                work=work / "gate6",
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
            report = {
                "schema_version": 1,
                "status": "pass",
                "gates": [gate1, gate2, gate3, gate4, gate5, gate6],
            }
            write_json(work / "all-results.json", report)
        elif ns.phase == 6:
            report = check_gate6(
                root=root,
                work=work,
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
        elif ns.phase == 5:
            report = check_gate5(
                root=root,
                work=work,
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
        elif ns.phase == 4:
            report = check_gate4(
                root=root,
                work=work,
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
        elif ns.phase == 3:
            report = check_gate3(
                root=root,
                work=work,
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
        elif ns.phase == 2:
            report = check_gate2(
                root=root,
                work=work,
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
        else:
            report = check_gate1(
                root=root,
                work=work,
                corpus_path=resolve(ns.compiler_faults),
                rejections_path=resolve(ns.compiler_fault_rejections),
                clean=ns.clean,
                timeout_seconds=ns.timeout,
                qemu_timeout=ns.qemu_timeout,
            )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        failure_record: dict[str, object] = {
            "schema_version": 1,
            "status": "fail",
            "gate": selected_gate,
            "error": str(error),
        }
        if isinstance(
            error,
            (
                Gate1Failure,
                Gate2Failure,
                Gate3Failure,
                Gate4Failure,
                Gate5Failure,
                Gate6Failure,
            ),
        ):
            failure_record["failure_category"] = error.category
            failure_record["failure_context"] = error.context
            failure_record["failure_detail"] = error.detail
        if work.is_dir():
            try:
                write_json(work / "check-failure.json", failure_record)
            except OSError:
                pass
        print(f"FOUNDATION CHECK FAIL: {error}", file=sys.stderr)
        return 1
    if ns.all:
        print("FOUNDATION GATES 1-6 PASS")
        print(f"evidence: {work / 'all-results.json'}")
    elif ns.phase == 6:
        counts = report["counts"]
        if not isinstance(counts, dict):
            raise Core0Error("Gate 6 PASS report lacks its count summary")
        print(
            "FOUNDATION GATE 6 PASS: "
            f"{counts['scenarios_per_profile']} scenarios/profile; "
            f"{counts['qemu_boots_total']} fresh QEMU boots; "
            f"{counts['runtime_requests_per_profile'] * 2} runtime requests"
        )
        print(f"evidence: {work / 'gate6-results.json'}")
    elif ns.phase == 5:
        counts = report["counts"]
        if not isinstance(counts, dict):
            raise Core0Error("Gate 5 PASS report lacks its count summary")
        print(
            "FOUNDATION GATE 5 PASS: "
            f"{counts['roots']} roots; {counts['cases_per_profile']} cases/profile; "
            f"{counts['qemu_boots_total']} fresh QEMU boots; "
            f"{counts['canary_observations']} canary observations"
        )
        print(f"evidence: {work / 'gate5-results.json'}")
    elif ns.phase == 4:
        counts = report["counts"]
        if not isinstance(counts, dict):
            raise Core0Error("Gate 4 PASS report lacks its count summary")
        print(
            "FOUNDATION GATE 4 PASS: "
            f"{counts['roots']} roots; {counts['cases_per_profile']} cases/profile; "
            f"{counts['qemu_boots_total']} QEMU boots"
        )
        print(f"evidence: {work / 'gate4-results.json'}")
    elif ns.phase == 3:
        counts = report["counts"]
        assert isinstance(counts, dict)
        print(
            "FOUNDATION GATE 3 PASS: "
            f"{counts['roots']} roots; {counts['cases_per_profile']} cases/profile; "
            f"{counts['qemu_boots_total']} QEMU boots"
        )
        print(f"evidence: {work / 'gate3-results.json'}")
    elif ns.phase == 2:
        counts = report["counts"]
        assert isinstance(counts, dict)
        print(
            "FOUNDATION GATE 2 PASS: "
            f"{counts['roots']} roots; {counts['cases_per_profile']} cases/profile; "
            f"{counts['qemu_boots_total']} QEMU boots"
        )
        print(f"evidence: {work / 'gate2-results.json'}")
    else:
        counts = report["counts"]
        assert isinstance(counts, dict)
        print(
            "FOUNDATION GATE 1 PASS: "
            f"{counts['clean_control_qemu_boots']} clean-control boots; "
            f"{counts['verified_behavioral_mismatches']} verified compiler-fault mismatches"
        )
        print(f"evidence: {work / 'gate1-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
