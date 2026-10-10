#!/usr/bin/env python3
"""Gate 10 host qualification for an already successful Gate 9 monitor run.

The qualifier consumes (and independently revalidates) a fresh Gate 9 report,
rebuilds each optimization profile once, proves the intended artifacts are
reproducible, and exercises report/audit failure paths in isolated build
subdirectories.  It does not rerun the cumulative or legacy suites; those are
separate Gate 10 commands owned by the top-level acceptance workflow.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import audit_core0
import check_foundation_gate8 as gate8_checker
import check_foundation_gate9 as gate9_checker
import gate9_corpus as gate9_corpus
import run_monitor_session as monitor_runner
from build_core0 import invalidate_output_file, prepare_output_directory
from core0_common import (
    Core0Error,
    checked,
    load_json,
    repo_root,
    run_bounded,
    sha256,
    write_json,
)


RESULT_FILE = "qualification-results.json"
FAILURE_FILE = "qualification-failure.json"
PROFILES = ("O0", "O2")
DETERMINISTIC_ARTIFACTS = (
    *monitor_runner.SOURCE_ARTIFACTS,
    "program.opt.ll",
    "program.o",
    "startup.o",
    "image.elf",
    "image.map",
    "platform.dtb",
    "platform.dts",
)
EXPECTED_GATE9_KEYS = {
    "schema_version", "status", "gate", "profile", "artifact_category", "test_abi",
    "started_at", "finished_at", "corpus", "corpus_sha256", "profiles",
    "source_binding", "source_probes", "source_rejections", "counts",
    "normal_counts", "stress_counts", "stress", "limitations",
}
T = TypeVar("T")


class QualificationFailure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category, self.context, self.detail = category, context, detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except QualificationFailure:
        raise
    except (
        Core0Error, OSError, ValueError, TypeError, AttributeError,
        UnicodeError, json.JSONDecodeError,
    ) as error:
        raise QualificationFailure(category, context, str(error)) from error


def build_monitor_image(**kwargs: object) -> dict[str, object]:
    from build_monitor import build_monitor_image as build
    return build(**kwargs)


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} is not an object")
    return value


def _array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Core0Error(f"{context} is not an array")
    return value


def _same(actual: object, expected: object, context: str) -> None:
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise Core0Error(f"{context} differs")


def _finite_positive(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError as error:
        raise Core0Error(f"qualification evidence escapes the repository: {path}") from error


def _build_subdirectory(path: Path, root: Path, context: str) -> Path:
    resolved, build_root = path.resolve(), (root / "build").resolve()
    try:
        relative = resolved.relative_to(build_root)
    except ValueError as error:
        raise Core0Error(f"{context} must be below {build_root}: {resolved}") from error
    if not relative.parts:
        raise Core0Error(f"{context} cannot be the build root")
    return resolved


def _artifact(root: Path, path: Path, role: str) -> dict[str, object]:
    if not path.is_file():
        raise Core0Error(f"mandatory qualification evidence is missing: {path}")
    return {
        "path": _relative(path, root),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "role": role,
    }


def _source_identity(root: Path) -> dict[str, object]:
    commit = checked(("git", "rev-parse", "HEAD"), cwd=root).stdout.decode().strip()
    tree = checked(("git", "rev-parse", "HEAD^{tree}"), cwd=root).stdout.decode().strip()
    status = checked(
        ("git", "status", "--porcelain", "--untracked-files=all"), cwd=root
    ).stdout.decode("utf-8", errors="replace")
    dirty_paths = sorted(
        line[3:] if len(line) >= 4 else line for line in status.splitlines() if line
    )
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or re.fullmatch(
        r"[0-9a-f]{40}", tree
    ) is None:
        raise Core0Error("qualification source lacks full Git commit/tree identities")
    if dirty_paths:
        raise Core0Error(
            "qualification requires committed clean source; dirty paths: "
            + repr(dirty_paths)
        )
    return {"commit": commit, "tree": tree, "clean": True, "dirty_paths": []}


def _repo_evidence_path(root: Path, value: object, context: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise Core0Error(f"{context} path is not repository-relative")
    path = (root / value).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise Core0Error(f"{context} path escapes the repository") from error
    if not path.is_file():
        raise Core0Error(f"{context} evidence is missing: {value}")
    return path


def _validate_probe_and_rejections(
    report: dict[str, object], root: Path, gate9_directory: Path
) -> dict[str, object]:
    probe = _object(report.get("source_probes"), "Gate 9 source probe")
    probe_source = _repo_evidence_path(root, probe.get("source"), "Gate 9 probe source")
    probe_log = _repo_evidence_path(root, probe.get("log"), "Gate 9 probe log")
    expected_probe_source = root / "examples/foundation/MonitorPolicyProbes.lean"
    expected_probe_log = gate9_directory / "probes/monitor-policy-frontend.txt"
    expected_frontend = (
        "Monitor genuine v0.7 frontend/lowering passed: 54 scalar functions, "
        "88 Action functions, 7 timer/2 trap/4 UART operations"
    )
    if (
        set(probe) != {
            "source", "source_sha256", "argv", "returncode", "policy_probes",
            "frontend_lowering", "log", "log_sha256", "scope",
        }
        or probe_source != expected_probe_source.resolve()
        or probe_log != expected_probe_log.resolve()
        or probe.get("argv") != [
            "lake", "env", "lean", "examples/foundation/MonitorPolicyProbes.lean"
        ]
        or probe.get("source_sha256") != sha256(probe_source)
        or probe.get("log_sha256") != sha256(probe_log)
        or type(probe.get("returncode")) is not int
        or probe["returncode"] != 0
        or type(probe.get("policy_probes")) is not int
        or probe["policy_probes"] != 50
        or type(probe.get("frontend_lowering")) is not int
        or probe["frontend_lowering"] != 1
        or probe.get("scope") != (
            "direct source predicates/encoding/frontend observations, not hardware "
            "or compiler proof"
        )
    ):
        raise Core0Error("Gate 9 retained source-probe identity differs")
    probe_text = probe_log.read_text(encoding="utf-8")
    source_text = probe_source.read_text(encoding="utf-8")
    if (
        probe_text.count(gate9_checker.POLICY_MARKER) != 1
        or probe_text.count(expected_frontend) != 1
        or "sorryAx" in probe_text
        or "declaration uses 'sorry'" in probe_text
        or len(re.findall(r"(?m)^#guard\s", source_text)) != 50
        or any(re.search(rf"\b{token}\b", source_text) for token in (
            "sorry", "admit", "native_decide",
        ))
    ):
        raise Core0Error("Gate 9 retained source-probe completion marker differs")

    rejections = _array(report.get("source_rejections"), "Gate 9 source rejections")
    expected_rejections = gate8_checker._load_rejections(root)
    if len(rejections) != len(expected_rejections):
        raise Core0Error("Gate 9 retained source-rejection corpus is incomplete")
    rejection_evidence = []
    for index, (raw, expected) in enumerate(
        zip(rejections, expected_rejections, strict=True)
    ):
        rejection = _object(raw, f"Gate 9 source rejection {index}")
        name = expected["name"]
        source = _repo_evidence_path(root, rejection.get("path"), f"{name} source")
        log = _repo_evidence_path(root, rejection.get("diagnostic_log"), f"{name} log")
        fragments = expected["required_fragments"]
        text = log.read_text(encoding="utf-8")
        errors = [
            line for line in text.splitlines()
            if re.search(r"(?:^|:\s)error:", line)
        ]
        expected_record = {
            **expected,
            "argv": ["lake", "env", "lean", expected["path"]],
            "returncode": rejection.get("returncode"),
            "source_sha256": rejection.get("source_sha256"),
            "diagnostic_log": rejection.get("diagnostic_log"),
            "diagnostic_sha256": rejection.get("diagnostic_sha256"),
        }
        if (
            rejection != expected_record
            or source != (root / expected["path"]).resolve()
            or log != (gate9_directory / "rejections" / f"{name}.txt").resolve()
            or rejection.get("source_sha256") != sha256(source)
            or rejection.get("diagnostic_sha256") != sha256(log)
            or type(rejection.get("returncode")) is not int
            or rejection["returncode"] == 0
            or any(not isinstance(fragment, str) or fragment not in text for fragment in fragments)
            or len(errors) != 1
            or f"error: Core0[{expected['diagnostic_code']}]" not in errors[0]
            or any(fragment in text for fragment in (
                "lean.unknownIdentifier", "declaration uses 'sorry'",
                "Aborting evaluation", "unknown declaration",
            ))
        ):
            raise Core0Error(f"Gate 9 retained source rejection differs: {name}")
        rejection_evidence.append(
            {"name": name, "source_sha256": sha256(source), "diagnostic_sha256": sha256(log)}
        )
    return {
        "probe_log_sha256": sha256(probe_log),
        "probe_source_sha256": sha256(probe_source),
        "rejections": rejection_evidence,
    }


def _revalidate_run(
    *,
    root: Path,
    output: Path,
    run_directory: Path,
    scenario: gate9_corpus.Scenario,
    expected_record: dict[str, object],
) -> dict[str, object]:
    record_path = run_directory / monitor_runner.RESULT_FILE
    record = _object(load_json(record_path), f"monitor run {scenario.name}")
    _same(record, expected_record, f"monitor retained report {scenario.name}")
    monitor_runner.validate_success_record(
        root=root,
        image=output / "image.elf",
        run_directory=run_directory,
        scenario=scenario,
        record=record,
    )
    raw_catalog = _object(record.get("raw_artifacts"), f"monitor raw catalog {scenario.name}")
    return {
        "scenario": scenario.name,
        "run_directory": _relative(run_directory, root),
        "report_sha256": sha256(record_path),
        "raw_artifacts": dict(raw_catalog),
        "returncode": record["returncode"],
        "expected_exit": scenario.expected_exit,
        "outcome": record["outcome"],
    }


def validate_gate9_bundle(
    *, root: Path, gate9_directory: Path, source: dict[str, object]
) -> dict[str, object]:
    report_path = gate9_directory / gate9_checker.RESULT_FILE
    report = _object(load_json(report_path), "Gate 9 result")
    if set(report) != EXPECTED_GATE9_KEYS:
        raise Core0Error(
            "Gate 9 result fields differ: "
            f"missing={sorted(EXPECTED_GATE9_KEYS - set(report))!r}, "
            f"unexpected={sorted(set(report) - EXPECTED_GATE9_KEYS)!r}"
        )
    if (
        type(report.get("schema_version")) is not int
        or report["schema_version"] != 1
        or report.get("status") != "PASS"
        or report.get("gate") != 9
        or report.get("profile") != gate9_corpus.PROFILE
        or report.get("artifact_category") != gate9_corpus.ARTIFACT_CATEGORY
        or report.get("test_abi") != gate9_corpus.TEST_ABI
    ):
        raise Core0Error("Gate 9 result identity/status differs")
    stress = _object(report.get("stress"), "Gate 9 stress declaration")
    enabled = stress.get("enabled")
    if type(enabled) is not bool:
        raise Core0Error("Gate 9 stress selection is not a boolean")
    _same(stress, gate9_corpus.stress_manifest(stress=enabled), "Gate 9 stress declaration")
    scenarios = gate9_corpus.selected_scenarios(stress=enabled)
    corpus_path = _repo_evidence_path(root, report.get("corpus"), "Gate 9 corpus")
    if corpus_path != (gate9_directory / "corpus/gate9-cases.json").resolve():
        raise Core0Error("Gate 9 corpus path is not inside the supplied result directory")
    if report.get("corpus_sha256") != sha256(corpus_path):
        raise Core0Error("Gate 9 corpus digest differs")
    _same(load_json(corpus_path), gate9_corpus.corpus_manifest(stress=enabled), "Gate 9 corpus")

    profiles = _object(report.get("profiles"), "Gate 9 profiles")
    if set(profiles) != set(PROFILES):
        raise Core0Error("Gate 9 result lacks exact O0/O2 profiles")
    profile_evidence: dict[str, object] = {}
    for optimization in PROFILES:
        profile = _object(profiles[optimization], f"Gate 9 {optimization} profile")
        if set(profile) != {
            "build", "audit", "binding", "targets", "same_elf_differing_streams",
            "fresh_processes",
        }:
            raise Core0Error(f"Gate 9 {optimization} profile fields differ")
        output = gate9_directory / optimization
        _same(profile["build"], load_json(output / "build.json"), f"Gate 9 {optimization} build")
        _same(profile["audit"], load_json(output / "audit.json"), f"Gate 9 {optimization} audit")
        binding = monitor_runner.validate_image_binding(output / "image.elf", root=root)
        _same(profile["binding"], binding, f"Gate 9 {optimization} image binding")
        if binding.get("source_commit") != source["commit"]:
            raise Core0Error(f"Gate 9 {optimization} image is not from the current commit")
        targets = _array(profile.get("targets"), f"Gate 9 {optimization} targets")
        if len(targets) != len(scenarios):
            raise Core0Error(f"Gate 9 {optimization} retained session count differs")
        replayed = []
        pids: set[int] = set()
        for scenario, raw_record in zip(scenarios, targets, strict=True):
            record = _object(raw_record, f"Gate 9 target {optimization}/{scenario.name}")
            replayed.append(
                _revalidate_run(
                    root=root,
                    output=output,
                    run_directory=gate9_directory / "runs" / optimization / scenario.name,
                    scenario=scenario,
                    expected_record=record,
                )
            )
            pid = record.get("pid")
            if type(pid) is not int or pid <= 0 or pid in pids:
                raise Core0Error(f"Gate 9 {optimization} retained session PID closure differs")
            pids.add(pid)
        if profile.get("fresh_processes") != len(scenarios) or profile.get(
            "same_elf_differing_streams"
        ) is not True:
            raise Core0Error(f"Gate 9 {optimization} fresh-session evidence differs")
        profile_evidence[optimization] = {
            "image_sha256": sha256(output / "image.elf"),
            "build_sha256": sha256(output / "build.json"),
            "audit_sha256": sha256(output / "audit.json"),
            "provenance_sha256": sha256(output / "provenance.json"),
            "sessions": replayed,
        }

    expected_source_binding = gate9_checker._verify_profiles(
        {optimization: gate9_directory / optimization for optimization in PROFILES}, root
    )
    _same(report.get("source_binding"), expected_source_binding, "Gate 9 source binding")
    counts, normal_counts, stress_counts = gate9_checker._completion_counts(
        profiles, stress=enabled
    )
    counts.update(source_rejections=4, policy_probes=50, frontend_lowering=1)
    _same(report.get("counts"), counts, "Gate 9 total counts")
    _same(report.get("normal_counts"), normal_counts, "Gate 9 normal counts")
    _same(report.get("stress_counts"), stress_counts, "Gate 9 stress counts")
    source_evidence = _validate_probe_and_rejections(report, root, gate9_directory)
    return {
        "report": _relative(report_path, root),
        "report_sha256": sha256(report_path),
        "stress": stress,
        "counts": counts,
        "normal_counts": normal_counts,
        "stress_counts": stress_counts,
        "profiles": profile_evidence,
        "source_evidence": source_evidence,
    }


def _normal_build(record: dict[str, object]) -> dict[str, object]:
    value = json.loads(json.dumps(record))
    value["output_directory"] = "$OUTPUT"
    artifacts = _object(value.get("artifacts"), "build artifacts")
    artifacts["provenance.json"] = "$INTENTIONAL_PROVENANCE_DIGEST"
    return value


def _normal_audit(record: dict[str, object]) -> dict[str, object]:
    value = json.loads(json.dumps(record))
    value["directory"] = "$OUTPUT"
    hashes = _object(value.get("hashes"), "audit hashes")
    hashes["provenance.json"] = "$INTENTIONAL_PROVENANCE_DIGEST"
    return value


def _normal_command(command: object, output: Path, root: Path) -> dict[str, object]:
    value = _object(command, "provenance command")
    if set(value) != {"argv", "cwd", "returncode", "elapsed_seconds", "stdout", "stderr"}:
        raise Core0Error("provenance command fields differ")
    if type(value.get("returncode")) is not int or value["returncode"] != 0:
        raise Core0Error("provenance command return code differs")
    cwd = value.get("cwd")
    output_display = _relative(output, root)
    normalized_cwd = "$OUTPUT" if cwd == output_display else cwd
    return {
        "argv": value.get("argv"),
        "cwd": normalized_cwd,
        "returncode": value.get("returncode"),
    }


def _compare_provenance(
    baseline: dict[str, object], rebuilt: dict[str, object],
    baseline_output: Path, rebuilt_output: Path, root: Path,
) -> dict[str, object]:
    stable_fields = set(baseline) - {"commands"}
    if set(rebuilt) - {"commands"} != stable_fields:
        raise Core0Error("rebuild provenance stable fields differ")
    for field in stable_fields:
        _same(rebuilt.get(field), baseline.get(field), f"rebuild provenance {field}")
    baseline_commands = _array(baseline.get("commands"), "baseline provenance commands")
    rebuilt_commands = _array(rebuilt.get("commands"), "rebuilt provenance commands")
    baseline_structure = [
        _normal_command(command, baseline_output, root) for command in baseline_commands
    ]
    rebuilt_structure = [
        _normal_command(command, rebuilt_output, root) for command in rebuilt_commands
    ]
    _same(rebuilt_structure, baseline_structure, "rebuild command structure")
    observations = []
    for index, (first, second) in enumerate(zip(baseline_commands, rebuilt_commands, strict=True)):
        first = _object(first, "baseline command")
        second = _object(second, "rebuilt command")
        observations.append({
            "index": index,
            "stdout_sha256": {
                "baseline": _bytes_sha256(str(first["stdout"]).encode()),
                "rebuilt": _bytes_sha256(str(second["stdout"]).encode()),
            },
            "stderr_sha256": {
                "baseline": _bytes_sha256(str(first["stderr"]).encode()),
                "rebuilt": _bytes_sha256(str(second["stderr"]).encode()),
            },
            "elapsed_seconds": {
                "baseline": first["elapsed_seconds"],
                "rebuilt": second["elapsed_seconds"],
            },
        })
    return {
        "stable_fields_equal": True,
        "command_structure_equal": True,
        "intentional_command_observation_differences": observations,
    }


def _bytes_sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _reproducibility_metadata(
    baseline: Path, rebuilt: Path, root: Path
) -> dict[str, object]:
    baseline_build = _object(load_json(baseline / "build.json"), "baseline build")
    rebuilt_build = _object(load_json(rebuilt / "build.json"), "rebuilt build")
    baseline_audit = _object(load_json(baseline / "audit.json"), "baseline audit")
    rebuilt_audit = _object(load_json(rebuilt / "audit.json"), "rebuilt audit")
    baseline_provenance = _object(
        load_json(baseline / "provenance.json"), "baseline provenance"
    )
    rebuilt_provenance = _object(
        load_json(rebuilt / "provenance.json"), "rebuilt provenance"
    )
    _same(
        _normal_build(rebuilt_build), _normal_build(baseline_build),
        "normalized build report",
    )
    _same(
        _normal_audit(rebuilt_audit), _normal_audit(baseline_audit),
        "normalized audit report",
    )
    provenance_comparison = _compare_provenance(
        baseline_provenance, rebuilt_provenance, baseline, rebuilt, root
    )
    if monitor_runner.source_inputs(baseline, root) != monitor_runner.source_inputs(
        rebuilt, root
    ):
        raise Core0Error("source-input provenance is not reproducible")
    return {
        "build": {
            "baseline_sha256": sha256(baseline / "build.json"),
            "rebuilt_sha256": sha256(rebuilt / "build.json"),
            "normalized_equal": True,
            "intentional_differences": [
                "output_directory", "artifacts.provenance.json"
            ],
        },
        "audit": {
            "baseline_sha256": sha256(baseline / "audit.json"),
            "rebuilt_sha256": sha256(rebuilt / "audit.json"),
            "normalized_equal": True,
            "intentional_differences": ["directory", "hashes.provenance.json"],
        },
        "provenance": {
            "baseline_sha256": sha256(baseline / "provenance.json"),
            "rebuilt_sha256": sha256(rebuilt / "provenance.json"),
            **provenance_comparison,
            "intentional_differences": [
                "commands[*].cwd", "commands[*].elapsed_seconds",
                "commands[*].stdout", "commands[*].stderr",
            ],
        },
    }


def rebuild_and_compare(
    *,
    root: Path,
    gate9_directory: Path,
    work: Path,
    timeout_seconds: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    results: dict[str, object] = {}
    evidence: list[dict[str, object]] = []
    for index, optimization in enumerate(PROFILES):
        baseline = gate9_directory / optimization
        rebuilt_output = work / "rebuild" / optimization
        build = build_monitor_image(
            root=root,
            output_dir=rebuilt_output,
            opt_level=optimization,
            clean=False,
            build_lean=index == 0,
            timeout_seconds=timeout_seconds,
        )
        _same(build, load_json(rebuilt_output / "build.json"), f"rebuilt {optimization} build")
        audit = audit_core0.audit(
            rebuilt_output, root, policy=audit_core0.TEST_MONITOR_IMAGE_POLICY
        )
        _same(audit, load_json(rebuilt_output / "audit.json"), f"rebuilt {optimization} audit")
        binding = monitor_runner.validate_image_binding(
            rebuilt_output / "image.elf", root=root
        )
        compared: dict[str, object] = {}
        for name in DETERMINISTIC_ARTIFACTS:
            original, repeated = baseline / name, rebuilt_output / name
            if not original.is_file() or not repeated.is_file():
                raise Core0Error(f"reproducibility artifact is missing: {optimization}/{name}")
            original_hash, repeated_hash = sha256(original), sha256(repeated)
            if original_hash != repeated_hash or original.read_bytes() != repeated.read_bytes():
                raise Core0Error(
                    f"{optimization} deterministic artifact is not reproducible: {name}"
                )
            compared[name] = {
                "baseline_sha256": original_hash,
                "rebuilt_sha256": repeated_hash,
                "bytes": original.stat().st_size,
                "identical": True,
            }
        metadata = _reproducibility_metadata(baseline, rebuilt_output, root)
        results[optimization] = {
            "rebuilt_directory": _relative(rebuilt_output, root),
            "binding": binding,
            "deterministic_artifacts": compared,
            "image_map_inspected_and_identical": True,
            "metadata": metadata,
        }
        for name in (
            *DETERMINISTIC_ARTIFACTS, "build.json", "audit.json", "provenance.json"
        ):
            evidence.append(
                _artifact(root, rebuilt_output / name, f"{optimization} rebuilt {name}")
            )
    return results, evidence


def _record_command(
    *, root: Path, directory: Path, name: str, evidence_role: str,
    argv: tuple[str, ...], timeout_seconds: float,
) -> tuple[object, dict[str, object]]:
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    stdout_path, stderr_path = directory / f"{name}.stdout.bin", directory / f"{name}.stderr.bin"
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    return result, {
        "argv": list(argv),
        "returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "stdout": _artifact(root, stdout_path, f"{evidence_role} stdout"),
        "stderr": _artifact(root, stderr_path, f"{evidence_role} stderr"),
    }


def _retain_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def stale_pass_experiments(
    *, root: Path, gate9_directory: Path, work: Path,
    timeout_seconds: float, qemu_timeout: float, stress: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    experiments: list[dict[str, object]] = []
    command_timeout = min(timeout_seconds, 60.0)

    phase_dir = work / "failure-experiments/stale-phase9"
    phase_dir.mkdir(parents=True)
    old_gate9 = (gate9_directory / gate9_checker.RESULT_FILE).read_bytes()
    (phase_dir / gate9_checker.RESULT_FILE).write_bytes(old_gate9)
    if {path.name for path in phase_dir.iterdir()} != {gate9_checker.RESULT_FILE}:
        raise Core0Error("stale Gate 9 experiment was not seeded with only the PASS report")
    phase_argv = (
        sys.executable, "scripts/check_foundation.py", "--phase", "9",
        "--work-dir", str(phase_dir), "--timeout", "nan",
        "--qemu-timeout", str(qemu_timeout),
        *(("--stress",) if stress else ()),
    )
    phase_result, phase_command = _record_command(
        root=root, directory=phase_dir, name="failure",
        evidence_role="stale Gate 9 command", argv=phase_argv,
        timeout_seconds=command_timeout,
    )
    if phase_result.returncode == 0 or (phase_dir / gate9_checker.RESULT_FILE).exists():
        raise Core0Error("early Gate 9 failure retained or replaced the stale PASS with success")
    failure_path = phase_dir / "check-failure.json"
    failure = _object(load_json(failure_path), "early Gate 9 failure")
    if (
        failure.get("status") != "fail"
        or failure.get("gate") != 9
        or failure.get("failure_category") != "harness-input-failure"
        or failure.get("failure_context") != "build"
        or "finite and positive" not in str(failure.get("failure_detail"))
    ):
        raise Core0Error("early Gate 9 failure classification differs")
    retained_old = phase_dir / "old-gate9-results.retained.json"
    _retain_bytes(retained_old, old_gate9)
    phase_record = {
        "id": "phase9-stale-pass",
        "passed": True,
        "old_pass_sha256": _bytes_sha256(old_gate9),
        "canonical_pass_absent": True,
        "observed_category": failure["failure_category"],
        "failure_report": _artifact(root, failure_path, "early Gate 9 failure report"),
        "retained_old_report": _artifact(root, retained_old, "retained old Gate 9 PASS input"),
        "command": phase_command,
    }
    experiments.append(phase_record)
    evidence.extend([
        phase_record["failure_report"], phase_record["retained_old_report"],
        phase_command["stdout"], phase_command["stderr"],
    ])

    scenario = gate9_corpus.selected_scenarios(stress=stress)[0]
    source_run = gate9_directory / "runs/O0" / scenario.name / monitor_runner.RESULT_FILE
    runner_dir = work / "failure-experiments/stale-runner"
    runner_dir.mkdir(parents=True)
    old_run = source_run.read_bytes()
    (runner_dir / monitor_runner.RESULT_FILE).write_bytes(old_run)
    if {path.name for path in runner_dir.iterdir()} != {monitor_runner.RESULT_FILE}:
        raise Core0Error("stale runner experiment was not seeded with only the PASS report")
    runner_argv = (
        sys.executable, "scripts/run_monitor_session.py",
        "--image", str(gate9_directory / "O0/image.elf"),
        "--output-dir", str(runner_dir), "--scenario", scenario.name,
        "--timeout", "nan",
    )
    runner_result, runner_command = _record_command(
        root=root, directory=runner_dir, name="failure",
        evidence_role="stale monitor runner command", argv=runner_argv,
        timeout_seconds=command_timeout,
    )
    failed_run_path = runner_dir / monitor_runner.RESULT_FILE
    failed_run = _object(load_json(failed_run_path), "early runner failure")
    if (
        runner_result.returncode == 0
        or failed_run.get("status") != "FAIL"
        or failed_run.get("failure_category") != "image-or-harness-rejection"
        or "finite and positive" not in str(failed_run.get("error"))
        or _bytes_sha256(old_run) == sha256(failed_run_path)
    ):
        raise Core0Error("early runner failure did not replace/classify the stale PASS")
    raw_records = {}
    for name in ("sent.bin", "received.bin", "stderr.bin"):
        raw_path = runner_dir / name
        if not raw_path.is_file() or failed_run.get("raw_artifacts", {}).get(name) != sha256(raw_path):
            raise Core0Error("failed runner did not retain exact raw evidence")
        raw_records[name] = _artifact(root, raw_path, f"failed runner {name}")
    retained_run = runner_dir / "old-run.retained.json"
    _retain_bytes(retained_run, old_run)
    runner_record = {
        "id": "runner-stale-pass",
        "passed": True,
        "old_pass_sha256": _bytes_sha256(old_run),
        "new_failure_sha256": sha256(failed_run_path),
        "observed_category": failed_run["failure_category"],
        "failure_report": _artifact(root, failed_run_path, "early runner failure report"),
        "retained_old_report": _artifact(root, retained_run, "retained old runner PASS input"),
        "raw_artifacts": raw_records,
        "command": runner_command,
    }
    experiments.append(runner_record)
    evidence.extend([
        runner_record["failure_report"], runner_record["retained_old_report"],
        *raw_records.values(), runner_command["stdout"], runner_command["stderr"],
    ])
    return experiments, evidence


def artifact_failure_experiments(
    *, root: Path, gate9_directory: Path, work: Path, timeout_seconds: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    evidence: list[dict[str, object]] = []
    experiments: list[dict[str, object]] = []
    original_output = gate9_directory / "O0"
    original_image_hash = sha256(original_output / "image.elf")
    command_timeout = min(timeout_seconds, 60.0)
    cases = (
        ("missing-program-object", "program.o", "missing"),
        ("tampered-program-ir", "program.ll", "tamper"),
    )
    for identifier, target, mode in cases:
        directory = work / "failure-experiments" / identifier / "artifact"
        shutil.copytree(original_output, directory)
        for stale in (directory / "audit.json", directory / "sha256sums.txt"):
            if stale.exists():
                stale.unlink()
        path = directory / target
        original_hash = sha256(path)
        if mode == "missing":
            path.unlink()
            changed_hash = None
        else:
            path.write_bytes(path.read_bytes() + b"\n; Gate 10 isolated tamper\n")
            changed_hash = sha256(path)
            if changed_hash == original_hash:
                raise Core0Error("isolated audit tamper did not change the artifact")
        argv = (
            sys.executable, "scripts/audit_core0.py", str(directory),
            "--policy", audit_core0.TEST_MONITOR_IMAGE_POLICY,
        )
        result, command = _record_command(
            root=root, directory=directory.parent, name="audit-failure",
            evidence_role=f"{identifier} audit command", argv=argv,
            timeout_seconds=command_timeout,
        )
        stderr_path = Path(command["stderr"]["path"])
        stderr = (root / stderr_path).read_text(encoding="utf-8", errors="replace")
        expected = (
            "missing audit artifacts: program.o"
            if mode == "missing"
            else "monitor pre-optimization LLVM closure differs"
        )
        if (
            result.returncode == 0
            or (directory / "audit.json").exists()
            or expected not in stderr
            or sha256(original_output / "image.elf") != original_image_hash
        ):
            raise Core0Error(f"isolated audit experiment did not fail closed: {identifier}")
        experiment_path = directory.parent / "experiment.json"
        experiment = {
            "id": identifier,
            "passed": True,
            "accepted_image_modified": False,
            "target": target,
            "mode": mode,
            "original_sha256": original_hash,
            "changed_sha256": changed_hash,
            "canonical_audit_absent": True,
            "command": command,
        }
        write_json(experiment_path, experiment)
        experiment["record"] = _artifact(root, experiment_path, f"{identifier} experiment")
        experiments.append(experiment)
        evidence.extend([experiment["record"], command["stdout"], command["stderr"]])

    scenario = gate9_corpus.SCENARIOS[0]
    source_run = gate9_directory / "runs/O0" / scenario.name
    directory = work / "failure-experiments/missing-raw-evidence"
    shutil.copytree(source_run, directory)
    record = _object(load_json(directory / monitor_runner.RESULT_FILE), "copied monitor run")
    missing = directory / "received.bin"
    missing_hash = sha256(missing)
    missing.unlink()
    try:
        _revalidate_run(
            root=root,
            output=gate9_directory / "O0",
            run_directory=directory,
            scenario=scenario,
            expected_record=record,
        )
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error("missing retained raw evidence was accepted")
    if "missing" not in diagnostic:
        raise Core0Error("missing retained raw evidence failed for an unrelated reason")
    raw_experiment_path = directory / "experiment.json"
    raw_experiment = {
        "id": "missing-raw-evidence",
        "passed": True,
        "removed": "received.bin",
        "removed_sha256": missing_hash,
        "canonical_pass_absent": True,
        "diagnostic": diagnostic,
    }
    retained_record = directory / "old-run.retained.json"
    (directory / monitor_runner.RESULT_FILE).replace(retained_record)
    write_json(raw_experiment_path, raw_experiment)
    raw_experiment["record"] = _artifact(
        root, raw_experiment_path, "missing raw evidence experiment"
    )
    raw_experiment["retained_old_report"] = _artifact(
        root, retained_record, "missing raw evidence retained old runner PASS input"
    )
    experiments.append(raw_experiment)
    evidence.extend([raw_experiment["record"], raw_experiment["retained_old_report"]])
    return experiments, evidence


def _mandatory_artifact_role_paths(
    root: Path, gate9_directory: Path, work: Path
) -> dict[str, str]:
    return {
        "input Gate 9 result": _relative(
            gate9_directory / gate9_checker.RESULT_FILE, root
        ),
        "O0 rebuilt image.elf": _relative(work / "rebuild/O0/image.elf", root),
        "O2 rebuilt image.elf": _relative(work / "rebuild/O2/image.elf", root),
        "early Gate 9 failure report": _relative(
            work / "failure-experiments/stale-phase9/check-failure.json", root
        ),
        "early runner failure report": _relative(
            work / "failure-experiments/stale-runner/run.json", root
        ),
        "missing-program-object experiment": _relative(
            work / "failure-experiments/missing-program-object/experiment.json", root
        ),
        "tampered-program-ir experiment": _relative(
            work / "failure-experiments/tampered-program-ir/experiment.json", root
        ),
        "missing raw evidence experiment": _relative(
            work / "failure-experiments/missing-raw-evidence/experiment.json", root
        ),
    }


def _validate_artifact_role_closure(
    artifacts: list[dict[str, object]], *, root: Path,
    gate9_directory: Path, work: Path,
) -> None:
    if len(artifacts) != 66:
        raise Core0Error("qualification artifact catalog has an incomplete closed count")
    paths: set[str] = set()
    role_paths: dict[str, str] = {}
    for artifact in artifacts:
        if set(artifact) != {"path", "bytes", "sha256", "role"}:
            raise Core0Error("qualification artifact record fields differ")
        path, role = artifact.get("path"), artifact.get("role")
        if (
            not isinstance(path, str) or not path or Path(path).is_absolute()
            or path in paths
        ):
            raise Core0Error("qualification artifact path is unsafe/duplicate")
        if not isinstance(role, str) or not role or role in role_paths:
            raise Core0Error("qualification artifact roles are duplicate")
        paths.add(path)
        role_paths[role] = path
    required = _mandatory_artifact_role_paths(root, gate9_directory, work)
    if any(role_paths.get(role) != path for role, path in required.items()):
        raise Core0Error("qualification mandatory evidence roles are absent")


def _qualification_artifact_catalog(
    *, root: Path, gate9_directory: Path, work: Path,
    rebuild_evidence: list[dict[str, object]],
    stale_evidence: list[dict[str, object]],
    artifact_evidence: list[dict[str, object]],
) -> list[dict[str, object]]:
    artifacts = [
        _artifact(
            root, gate9_directory / gate9_checker.RESULT_FILE, "input Gate 9 result"
        ),
        *[
            _artifact(
                root, gate9_directory / optimization / name,
                f"input Gate 9 {optimization} {name}",
            )
            for optimization in PROFILES
            for name in ("build.json", "audit.json", "provenance.json", "image.elf")
        ],
        *rebuild_evidence,
        *stale_evidence,
        *artifact_evidence,
    ]
    _validate_artifact_role_closure(
        artifacts, root=root, gate9_directory=gate9_directory, work=work
    )
    return artifacts


def validate_qualification_report(
    value: object, *, root: Path, work: Path
) -> dict[str, object]:
    report = _object(value, "qualification report")
    expected_keys = {
        "schema_version", "status", "task", "gate", "started_at", "finished_at",
        "source", "invocation", "gate9_input", "reproducibility",
        "failure_experiments", "artifacts", "counts", "limitations",
    }
    if set(report) != expected_keys:
        raise Core0Error("qualification report fields differ")
    if (
        type(report.get("schema_version")) is not int
        or report["schema_version"] != 1
        or report.get("status") != "PASS"
        or report.get("task") != "002-machine-foundation"
        or report.get("gate") != 10
    ):
        raise Core0Error("qualification report identity/status differs")
    source = _object(report.get("source"), "qualification source")
    if (
        set(source) != {"commit", "tree", "clean", "dirty_paths"}
        or
        source.get("clean") is not True
        or source.get("dirty_paths") != []
        or re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit"))) is None
        or re.fullmatch(r"[0-9a-f]{40}", str(source.get("tree"))) is None
    ):
        raise Core0Error("qualification report lacks clean full source identities")
    _same(source, _source_identity(root), "qualification final source identity")
    invocation = _object(report.get("invocation"), "qualification invocation")
    gate9_name, work_name = invocation.get("gate9_directory"), invocation.get("work_directory")
    if (
        set(invocation) != {
            "gate9_directory", "work_directory", "clean", "timeout_seconds",
            "qemu_timeout", "stress_selected_by_gate9_report",
        }
        or not isinstance(gate9_name, str)
        or not isinstance(work_name, str)
        or Path(gate9_name).is_absolute()
        or Path(work_name).is_absolute()
        or (root / work_name).resolve() != work.resolve()
        or type(invocation.get("clean")) is not bool
        or type(invocation.get("stress_selected_by_gate9_report")) is not bool
        or any(
            not _finite_positive(invocation.get(name))
            for name in ("timeout_seconds", "qemu_timeout")
        )
    ):
        raise Core0Error("qualification invocation paths differ")
    gate9_directory = _build_subdirectory(
        (root / gate9_name).resolve(), root, "qualification Gate 9 input"
    )
    if gate9_directory == work or gate9_directory in work.parents or work in gate9_directory.parents:
        raise Core0Error("qualification input and work directories are not disjoint")
    fresh_gate9 = validate_gate9_bundle(
        root=root,
        gate9_directory=gate9_directory,
        source=source,
    )
    _same(report.get("gate9_input"), fresh_gate9, "qualification Gate 9 revalidation")
    if invocation["stress_selected_by_gate9_report"] is not fresh_gate9["stress"]["enabled"]:
        raise Core0Error("qualification invocation stress binding differs")
    reproducibility = _object(report.get("reproducibility"), "qualification reproducibility")
    if set(reproducibility) != set(PROFILES):
        raise Core0Error("qualification report lacks exact O0/O2 reproducibility")
    for optimization in PROFILES:
        profile = _object(reproducibility[optimization], f"{optimization} reproducibility")
        if set(profile) != {
            "rebuilt_directory", "binding", "deterministic_artifacts",
            "image_map_inspected_and_identical", "metadata",
        }:
            raise Core0Error(f"{optimization} reproducibility fields differ")
        baseline = gate9_directory / optimization
        rebuilt = work / "rebuild" / optimization
        if profile.get("rebuilt_directory") != _relative(rebuilt, root):
            raise Core0Error(f"{optimization} rebuilt directory differs")
        deterministic = _object(
            profile.get("deterministic_artifacts"), f"{optimization} artifacts"
        )
        if set(deterministic) != set(DETERMINISTIC_ARTIFACTS):
            raise Core0Error(f"{optimization} reproducibility catalog is incomplete")
        for name in DETERMINISTIC_ARTIFACTS:
            comparison = _object(deterministic[name], f"{optimization}/{name} comparison")
            first, second = baseline / name, rebuilt / name
            expected = {
                "baseline_sha256": sha256(first),
                "rebuilt_sha256": sha256(second),
                "bytes": first.stat().st_size,
                "identical": True,
            }
            if first.read_bytes() != second.read_bytes():
                raise Core0Error(f"{optimization} reproducibility bytes changed: {name}")
            _same(comparison, expected, f"{optimization}/{name} comparison")
        if profile.get("image_map_inspected_and_identical") is not True:
            raise Core0Error(f"{optimization} image.map was not reproducibly inspected")
        binding = monitor_runner.validate_image_binding(rebuilt / "image.elf", root=root)
        _same(profile.get("binding"), binding, f"{optimization} rebuilt binding")
        metadata = _reproducibility_metadata(baseline, rebuilt, root)
        _same(profile.get("metadata"), metadata, f"{optimization} metadata")
    experiments = _array(report.get("failure_experiments"), "qualification experiments")
    expected_ids = {
        "phase9-stale-pass", "runner-stale-pass", "missing-program-object",
        "tampered-program-ir", "missing-raw-evidence",
    }
    if len(experiments) != len(expected_ids) or {
        _object(item, "qualification experiment").get("id") for item in experiments
    } != expected_ids or any(
        _object(item, "qualification experiment").get("passed") is not True
        for item in experiments
    ):
        raise Core0Error("qualification failure-path experiment closure differs")
    experiment_by_id = {
        _object(item, "qualification experiment")["id"]:
            _object(item, "qualification experiment")
        for item in experiments
    }
    expected_experiment_fields = {
        "phase9-stale-pass": {
            "id", "passed", "old_pass_sha256", "canonical_pass_absent",
            "observed_category", "failure_report", "retained_old_report", "command",
        },
        "runner-stale-pass": {
            "id", "passed", "old_pass_sha256", "new_failure_sha256",
            "observed_category", "failure_report", "retained_old_report",
            "raw_artifacts", "command",
        },
        "missing-program-object": {
            "id", "passed", "accepted_image_modified", "target", "mode",
            "original_sha256", "changed_sha256", "canonical_audit_absent",
            "command", "record",
        },
        "tampered-program-ir": {
            "id", "passed", "accepted_image_modified", "target", "mode",
            "original_sha256", "changed_sha256", "canonical_audit_absent",
            "command", "record",
        },
        "missing-raw-evidence": {
            "id", "passed", "removed", "removed_sha256", "canonical_pass_absent",
            "diagnostic", "record", "retained_old_report",
        },
    }
    if any(
        set(experiment_by_id[name]) != fields
        for name, fields in expected_experiment_fields.items()
    ):
        raise Core0Error("qualification experiment fields differ")
    phase, runner_failure = (
        experiment_by_id["phase9-stale-pass"],
        experiment_by_id["runner-stale-pass"],
    )
    missing, tampered, missing_raw = (
        experiment_by_id["missing-program-object"],
        experiment_by_id["tampered-program-ir"],
        experiment_by_id["missing-raw-evidence"],
    )
    if (
        phase.get("canonical_pass_absent") is not True
        or phase.get("observed_category") != "harness-input-failure"
        or runner_failure.get("observed_category") != "image-or-harness-rejection"
        or missing.get("accepted_image_modified") is not False
        or missing.get("canonical_audit_absent") is not True
        or (missing.get("target"), missing.get("mode")) != ("program.o", "missing")
        or tampered.get("accepted_image_modified") is not False
        or tampered.get("canonical_audit_absent") is not True
        or (tampered.get("target"), tampered.get("mode")) != ("program.ll", "tamper")
        or missing_raw.get("canonical_pass_absent") is not True
        or missing_raw.get("removed") != "received.bin"
    ):
        raise Core0Error("qualification experiment outcome differs")
    artifacts = _array(report.get("artifacts"), "qualification artifacts")
    if len(artifacts) != 66:
        raise Core0Error("qualification artifact catalog has an incomplete closed count")
    paths: set[str] = set()
    for raw in artifacts:
        artifact = _object(raw, "qualification artifact")
        if set(artifact) != {"path", "bytes", "sha256", "role"}:
            raise Core0Error("qualification artifact record fields differ")
        name = artifact.get("path")
        if not isinstance(name, str) or not name or name in paths or Path(name).is_absolute():
            raise Core0Error("qualification artifact path is unsafe/duplicate")
        paths.add(name)
        path = (root / name).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as error:
            raise Core0Error("qualification artifact escapes the repository") from error
        if (
            not path.is_file()
            or artifact.get("sha256") != sha256(path)
            or artifact.get("bytes") != path.stat().st_size
            or not isinstance(artifact.get("role"), str)
            or not artifact["role"]
        ):
            raise Core0Error(f"qualification artifact is missing/stale: {name}")
    role_paths = {
        _object(item, "qualification artifact")["role"]:
            _object(item, "qualification artifact")["path"]
        for item in artifacts
    }
    if len(role_paths) != len(artifacts):
        raise Core0Error("qualification artifact roles are duplicate")
    required_role_paths = _mandatory_artifact_role_paths(
        root, gate9_directory, work
    )
    if any(role_paths.get(role) != path for role, path in required_role_paths.items()):
        raise Core0Error("qualification mandatory evidence roles are absent")
    counts = _object(report.get("counts"), "qualification counts")
    if (
        set(counts) != {
            "replayed_gate9_sessions", "normal_sessions", "stress_sessions",
            "reproducible_profiles", "deterministic_artifacts_per_profile",
            "failure_path_experiments",
        }
        or counts.get("replayed_gate9_sessions") != fresh_gate9["counts"]["fresh_qemu_boots"]
        or counts.get("normal_sessions") != fresh_gate9["normal_counts"]["fresh_qemu_boots"]
        or counts.get("stress_sessions") != fresh_gate9["stress_counts"]["fresh_qemu_boots"]
        or counts.get("reproducible_profiles") != 2
        or counts.get("deterministic_artifacts_per_profile") != len(DETERMINISTIC_ARTIFACTS)
        or counts.get("failure_path_experiments") != 5
    ):
        raise Core0Error("qualification completion counts differ")
    return report


def qualify_foundation(
    *,
    root: Path,
    gate9_directory: Path,
    work: Path,
    clean: bool,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    root = root.resolve()
    gate9_directory = _build_subdirectory(gate9_directory, root, "Gate 9 directory")
    work = _build_subdirectory(work, root, "qualification work directory")
    if gate9_directory == work or gate9_directory in work.parents or work in gate9_directory.parents:
        raise Core0Error("qualification input and work directories must be disjoint")
    invalidate_output_file(work / RESULT_FILE, root)
    invalidate_output_file(work / (RESULT_FILE + ".tmp"), root)
    invalidate_output_file(work / FAILURE_FILE, root)
    invalidate_output_file(work / (FAILURE_FILE + ".tmp"), root)
    prepare_output_directory(work, root, clean=clean)
    for name, value in (("build", timeout_seconds), ("qemu", qemu_timeout)):
        if not _finite_positive(value):
            raise QualificationFailure(
                "harness-input-failure", name, "timeout must be finite and positive"
            )
    started = datetime.now(timezone.utc).isoformat()
    source = _stage("source-identity-rejection", "Git", lambda: _source_identity(root))
    gate9 = _stage(
        "gate9-evidence-rejection",
        str(gate9_directory),
        lambda: validate_gate9_bundle(
            root=root, gate9_directory=gate9_directory, source=source
        ),
    )
    reproducibility, rebuild_evidence = _stage(
        "reproducibility-rejection",
        "O0/O2",
        lambda: rebuild_and_compare(
            root=root,
            gate9_directory=gate9_directory,
            work=work,
            timeout_seconds=timeout_seconds,
        ),
    )
    stale, stale_evidence = _stage(
        "stale-pass-experiment-rejection",
        "phase9/runner",
        lambda: stale_pass_experiments(
            root=root,
            gate9_directory=gate9_directory,
            work=work,
            timeout_seconds=timeout_seconds,
            qemu_timeout=qemu_timeout,
            stress=bool(gate9["stress"]["enabled"]),
        ),
    )
    artifact_failures, artifact_evidence = _stage(
        "artifact-failure-experiment-rejection",
        "missing/tampered",
        lambda: artifact_failure_experiments(
            root=root,
            gate9_directory=gate9_directory,
            work=work,
            timeout_seconds=timeout_seconds,
        ),
    )
    artifacts = _qualification_artifact_catalog(
        root=root,
        gate9_directory=gate9_directory,
        work=work,
        rebuild_evidence=rebuild_evidence,
        stale_evidence=stale_evidence,
        artifact_evidence=artifact_evidence,
    )
    report = {
        "schema_version": 1,
        "status": "PASS",
        "task": "002-machine-foundation",
        "gate": 10,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "invocation": {
            "gate9_directory": _relative(gate9_directory, root),
            "work_directory": _relative(work, root),
            "clean": clean,
            "timeout_seconds": timeout_seconds,
            "qemu_timeout": qemu_timeout,
            "stress_selected_by_gate9_report": bool(gate9["stress"]["enabled"]),
        },
        "gate9_input": gate9,
        "reproducibility": reproducibility,
        "failure_experiments": [*stale, *artifact_failures],
        "artifacts": artifacts,
        "counts": {
            "replayed_gate9_sessions": gate9["counts"]["fresh_qemu_boots"],
            "normal_sessions": gate9["normal_counts"]["fresh_qemu_boots"],
            "stress_sessions": gate9["stress_counts"]["fresh_qemu_boots"],
            "reproducible_profiles": len(reproducibility),
            "deterministic_artifacts_per_profile": len(DETERMINISTIC_ARTIFACTS),
            "failure_path_experiments": len(stale) + len(artifact_failures),
        },
        "limitations": [
            "Qualification replays retained Gate 9 raw frames and does not duplicate its QEMU boots.",
            "Full cumulative, legacy, detached-worktree and CI execution are separate Gate 10 evidence.",
            "Reproducibility is same-profile only; O0 and O2 images are intentionally not compared.",
            "Tests and audits are not a proof of compiler correctness or physical-board support.",
        ],
    }
    temporary = work / (RESULT_FILE + ".tmp")
    write_json(temporary, report)
    persisted = load_json(temporary)
    _same(persisted, report, "transactional qualification report")
    validate_qualification_report(persisted, root=root, work=work)
    temporary.replace(work / RESULT_FILE)
    if not (work / RESULT_FILE).is_file() or temporary.exists():
        raise Core0Error("qualification result was not atomically published")
    return report


def _requested_work(argv: list[str], root: Path) -> Path | None:
    value: str | None = None
    for index, argument in enumerate(argv):
        if argument.startswith("--work-dir="):
            value = argument.split("=", 1)[1]
        elif argument == "--work-dir" and index + 1 < len(argv):
            value = argv[index + 1]
    if not value or value.startswith("-"):
        return None
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _publish_failure(work: Path, root: Path, error: object) -> None:
    work = _build_subdirectory(work, root, "qualification failure directory")
    invalidate_output_file(work / RESULT_FILE, root)
    invalidate_output_file(work / (RESULT_FILE + ".tmp"), root)
    failure = {
        "schema_version": 1,
        "status": "FAIL",
        "gate": 10,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "error": str(error),
    }
    if isinstance(error, QualificationFailure):
        failure.update(
            failure_category=error.category,
            failure_context=error.context,
            failure_detail=error.detail,
        )
    temporary = work / (FAILURE_FILE + ".tmp")
    write_json(temporary, failure)
    temporary.replace(work / FAILURE_FILE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate9-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--qemu-timeout", type=float, default=20.0)
    root = repo_root()
    raw_argv = sys.argv[1:]
    requested_work = _requested_work(raw_argv, root)
    try:
        ns = parser.parse_args(raw_argv)
    except SystemExit as error:
        if error.code and requested_work is not None:
            try:
                _publish_failure(requested_work, root, "invalid qualification CLI arguments")
            except (Core0Error, OSError, ValueError, TypeError):
                pass
        return int(error.code) if error.code is not None else 2
    resolve = lambda path: path.resolve() if path.is_absolute() else (root / path).resolve()
    work = resolve(ns.work_dir)
    try:
        report = qualify_foundation(
            root=root,
            gate9_directory=resolve(ns.gate9_dir),
            work=work,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
            qemu_timeout=ns.qemu_timeout,
        )
    except (
        Core0Error, OSError, ValueError, TypeError, AttributeError,
        UnicodeError, json.JSONDecodeError,
    ) as error:
        try:
            _publish_failure(work, root, error)
        except (Core0Error, OSError):
            pass
        print(f"FOUNDATION QUALIFICATION FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["counts"], sort_keys=True))
    print(f"evidence: {work / RESULT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
