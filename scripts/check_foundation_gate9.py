#!/usr/bin/env python3
"""Gate 9 acceptance for one compiled Lean interactive bare-metal monitor."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import audit_core0
import gate9_corpus as corpus
import run_monitor_session as runner
from build_core0 import invalidate_output_file, prepare_output_directory
from check_foundation_gate8 import _run_rejections
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json

RESULT_FILE = "gate9-results.json"
POLICY_MARKER = "MONITOR_POLICY_PROBES:50 FRONTEND_LOWERING:1"
T = TypeVar("T")


class Gate9Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category, self.context, self.detail = category, context, detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate9Failure:
        raise
    except runner.MonitorRunFailure as error:
        raise Gate9Failure(error.category, context, str(error)) from error
    except (Core0Error, OSError, ValueError, UnicodeError, TypeError) as error:
        raise Gate9Failure(category, context, str(error)) from error


def build_monitor_image(**kwargs: object) -> dict[str, object]:
    from build_monitor import build_monitor_image as build
    return build(**kwargs)


def _run_probes(*, root: Path, work: Path, timeout_seconds: float,
                manifest: dict[str, object]) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    name = "examples/foundation/MonitorPolicyProbes.lean"
    source = root / name
    before = sha256(source)
    text = source.read_text(encoding="utf-8")
    if len(re.findall(r"(?m)^#guard\s", text)) != 50 or any(
        re.search(rf"\b{token}\b", text) for token in ("sorry", "admit", "native_decide")):
        raise Core0Error("monitor policy probe source count/proof-device boundary differs")
    argv = ("lake", "env", "lean", name)
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    log = work / "monitor-policy-frontend.txt"
    log.write_text(output, encoding="utf-8")
    frontend = (f"Monitor genuine v0.7 frontend/lowering passed: {len(manifest['scalar_functions'])} scalar functions, "
                f"{len(manifest['action_functions'])} Action functions, 7 timer/2 trap/4 UART operations")
    if (result.returncode != 0 or output.count(POLICY_MARKER) != 1 or output.count(frontend) != 1
            or before != sha256(source) or "sorryAx" in output or "declaration uses 'sorry'" in output):
        raise Core0Error("monitor source/frontend probes failed, changed source, or lacked exact completion markers")
    return {"source": name, "source_sha256": before, "argv": list(argv),
        "returncode": result.returncode, "policy_probes": 50, "frontend_lowering": 1,
        "log": str(log.relative_to(root)), "log_sha256": sha256(log),
        "scope": "direct source predicates/encoding/frontend observations, not hardware or compiler proof"}


def _target(*, root: Path, output: Path, work: Path, scenario: corpus.Scenario,
            timeout_seconds: float) -> dict[str, object]:
    record = runner._object(runner.run_session(
        root=root, image=output / "image.elf", output_dir=work,
        scenario=scenario, timeout_seconds=timeout_seconds,
    ), "returned successful record")
    persisted = runner._object(
        load_json(work / runner.RESULT_FILE), "persisted successful record"
    )
    runner._same(record, persisted, "returned/persisted successful record")
    runner.validate_success_record(
        root=root,
        image=output / "image.elf",
        run_directory=work,
        scenario=scenario,
        record=record,
        expected_timeout_seconds=timeout_seconds,
    )
    return record


def _verify_profiles(outputs: dict[str, Path], root: Path) -> dict[str, object]:
    hashes = {profile: {name: sha256(output / name) for name in runner.SOURCE_ARTIFACTS}
              for profile, output in outputs.items()}
    inputs = {profile: runner.source_inputs(output, root) for profile, output in outputs.items()}
    if hashes["O0"] != hashes["O2"] or inputs["O0"] != inputs["O2"]:
        raise Core0Error("monitor O0/O2 checked source/startup/ABI/source-input hashes differ")
    return {"same_checked_source": True, "source_artifacts": hashes["O0"], "source_inputs": inputs["O0"],
        "no_loader_fixture": True, "all_runtime_inputs_post_boot_uart": True}


def _session_counts(targets: list[dict[str, object]]) -> dict[str, int]:
    return {"fresh_qemu_boots": len(targets),
        "mixed_sessions": sum(corpus.SCENARIO_BY_NAME[record["scenario"]].integration for record in targets),
        "terminal_sessions": sum(record["expected_exit"] != 0 for record in targets),
        "active_terminal_cleanup_sessions": sum(record["scenario"] == "active-truncated-payload" for record in targets),
        "handled_requests": sum(record.get("summary", {}).get("handled_requests", 0) for record in targets),
        "actual_hardware_irqs": sum(record.get("summary", {}).get("observed_hardware_irqs", 0) for record in targets),
        "synchronous_recoveries": sum(record.get("summary", {}).get("synchronous_recoveries", 0) for record in targets),
        "retained_records_checked": sum(record.get("summary", {}).get("records_checked", 0) for record in targets)}


def _completion_counts(profiles: dict[str, object], *, stress: bool = False
                       ) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    scenarios = corpus.selected_scenarios(stress=stress)
    if set(profiles) != {"O0", "O2"}:
        raise Gate9Failure("empty-or-incomplete-corpus", "completion", "exact O0/O2 profiles are required")
    targets = []
    for profile in ("O0", "O2"):
        if not isinstance(profiles[profile], dict):
            raise Gate9Failure("empty-or-incomplete-corpus", profile, "profile is not an object")
        records = profiles[profile].get("targets")
        if (not isinstance(records, list) or any(not isinstance(record, dict) for record in records)
                or [record.get("scenario") for record in records] != [scenario.name for scenario in scenarios]):
            raise Gate9Failure("empty-or-incomplete-corpus", profile, "selected session sequence differs")
        for record, scenario in zip(records, scenarios, strict=True):
            if (type(record.get("schema_version")) is not int or record["schema_version"] != 1
                    or record.get("status") != "PASS"
                    or type(record.get("expected_exit")) is not int
                    or record["expected_exit"] != scenario.expected_exit
                    or type(record.get("returncode")) is not int
                    or record["returncode"] != scenario.expected_exit):
                raise Gate9Failure("incomplete-session-evidence", profile, "target status/expected exit differs")
            if scenario.requests:
                summary = record.get("summary")
                if (not isinstance(summary, dict)
                        or any(type(summary.get(key)) is not int or summary[key] < 0 for key in (
                            "handled_requests", "observed_hardware_irqs", "synchronous_recoveries", "records_checked"))
                        or summary["handled_requests"] != len(scenario.requests)
                        or len(record.get("responses", [])) != len(scenario.requests)):
                    raise Gate9Failure("incomplete-session-evidence", scenario.name, "mandatory validated responses/summary are absent")
            if scenario.integration:
                if (summary["observed_hardware_irqs"] < 338
                        or type(summary.get("hardware_work_commands")) is not int or summary["hardware_work_commands"] < 3
                        or summary["synchronous_recoveries"] != 5 or summary["records_checked"] < 48
                        or summary.get("observed_overflow") is not True or summary.get("observed_ring_wrap") is not True):
                    raise Gate9Failure("missing-hardware-integration-evidence", scenario.name,
                        "mixed summary lacks required real IRQ work/trap/overflow/wrap/retained-record evidence")
        targets.extend(records)
    active_terminal = [record for record in targets if record["scenario"] == "active-truncated-payload"]
    if len(active_terminal) != 2 or any(
        record.get("outcome") != "verified-terminal-rejection"
        or record["summary"].get("active_at_terminal_input") is not True
        or record["summary"]["observed_hardware_irqs"] < 1 for record in active_terminal):
        raise Gate9Failure("missing-active-terminal-cleanup-evidence", "completion",
            "both active timer prefixes must validate START then terminate with exact truncation status")
    normal_names = {scenario.name for scenario in corpus.SCENARIOS}
    normal = [record for record in targets if record["scenario"] in normal_names]
    extended = [record for record in targets if record["scenario"] not in normal_names]
    total_counts, normal_counts, stress_counts = (_session_counts(records) for records in (targets, normal, extended))
    expected_mixed = 12 if stress else 4
    if (total_counts["fresh_qemu_boots"] != (26 if stress else 18)
            or normal_counts["fresh_qemu_boots"] != 18 or normal_counts["mixed_sessions"] != 4
            or stress_counts["fresh_qemu_boots"] != (8 if stress else 0)
            or total_counts["mixed_sessions"] != expected_mixed):
        raise Gate9Failure("empty-or-incomplete-corpus", "completion", "normal/stress session counts differ")
    if total_counts["actual_hardware_irqs"] < 338 * expected_mixed or total_counts["synchronous_recoveries"] < 5 * expected_mixed:
        raise Gate9Failure("missing-hardware-integration-evidence", "completion", "aggregate hardware/trap lower bounds differ")
    return total_counts, normal_counts, stress_counts


def check_gate9(*, root: Path, work: Path, clean: bool, timeout_seconds: float,
                qemu_timeout: float, stress: bool = False) -> dict[str, object]:
    root, work = root.resolve(), work.resolve()
    _stage("work-directory-failure", str(work), lambda: (
        invalidate_output_file(work / RESULT_FILE, root),
        invalidate_output_file(work / (RESULT_FILE + ".tmp"), root),
        prepare_output_directory(work, root, clean=clean)))
    for name, value in (("build", timeout_seconds), ("qemu", qemu_timeout)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float("inf"):
            raise Gate9Failure("harness-input-failure", name, "timeout must be finite and positive")
    if type(stress) is not bool:
        raise Gate9Failure("harness-input-failure", "stress", "stress selection must be a boolean")
    scenarios = _stage("runtime-corpus-rejection", "selection", lambda: corpus.selected_scenarios(stress=stress))
    started = datetime.now(timezone.utc).isoformat()
    corpus_path = work / "corpus/gate9-cases.json"
    write_json(corpus_path, corpus.corpus_manifest(stress=stress))
    profiles, outputs = {}, {}
    for index, optimization in enumerate(("O0", "O2")):
        output = outputs[optimization] = work / optimization
        build = _stage("compile-or-link-failure", optimization, lambda: build_monitor_image(
            root=root, output_dir=output, opt_level=optimization, clean=False,
            build_lean=index == 0, timeout_seconds=timeout_seconds))
        if build != load_json(output / "build.json") or build.get("optimization") != optimization:
            raise Gate9Failure("build-record-rejection", optimization, "returned/persisted optimization differs")
        audit = _stage("machine-audit-rejection", optimization,
            lambda: audit_core0.audit(output, root, policy=corpus.ARTIFACT_CATEGORY))
        binding = _stage("image-binding-rejection", optimization,
            lambda: runner.validate_image_binding(output / "image.elf", root=root))
        targets = [_stage("target-failure", f"{optimization}/{scenario.name}", lambda scenario=scenario: _target(
            root=root, output=output, work=work / "runs" / optimization / scenario.name,
            scenario=scenario, timeout_seconds=qemu_timeout)) for scenario in scenarios]
        pids = [record["pid"] for record in targets]
        if len(set(pids)) != len(targets) or len({record["image_sha256"] for record in targets}) != 1:
            raise Gate9Failure("fresh-session-rejection", optimization, "sessions reused a PID or changed ELF")
        streams = [(work / "runs" / optimization / scenario.name / "sent.bin").read_bytes()
                   for scenario in scenarios if scenario.integration]
        if len(streams) < 2 or len(set(streams)) != len(streams):
            raise Gate9Failure("runtime-corpus-rejection", optimization, "mixed streams are empty or identical")
        profiles[optimization] = {"build": build, "audit": audit, "binding": binding, "targets": targets,
            "same_elf_differing_streams": True, "fresh_processes": len(pids)}
    shared = _stage("source-profile-rejection", "O0/O2", lambda: _verify_profiles(outputs, root))
    probes = _stage("source-probe-failure", "monitor policy/frontend", lambda: _run_probes(
        root=root, work=work / "probes", timeout_seconds=timeout_seconds,
        manifest=load_json(outputs["O0"] / "monitor-manifest.json")))
    rejections = _stage("source-rejection-failure", "retained Gate8 fixtures", lambda: _run_rejections(
        root=root, work=work / "rejections", timeout_seconds=timeout_seconds))
    _stage("source-profile-rejection", "final source recheck", lambda: _verify_profiles(outputs, root))
    counts, normal_counts, stress_counts = _stage("incomplete-session-evidence", "completion",
        lambda: _completion_counts(profiles, stress=stress))
    if len(rejections) != 4:
        raise Gate9Failure("empty-or-incomplete-corpus", "completion", "mandatory source rejections are missing")
    counts.update(source_rejections=len(rejections), policy_probes=50, frontend_lowering=1)
    report = {"schema_version": 1, "status": "PASS", "gate": 9, "profile": corpus.PROFILE,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(corpus_path.relative_to(root)), "corpus_sha256": sha256(corpus_path),
        "profiles": profiles, "source_binding": shared, "source_probes": probes,
        "source_rejections": rejections, "counts": counts,
        "normal_counts": normal_counts, "stress_counts": stress_counts,
        "stress": corpus.stress_manifest(stress=stress),
        "limitations": ["single-hart pinned QEMU M-mode only", "no scheduler, managed runtime or physical-board claim",
            "tests/audits are not a compiler correctness or real-time latency proof"]}
    write_json(work / (RESULT_FILE + ".tmp"), report)
    (work / (RESULT_FILE + ".tmp")).replace(work / RESULT_FILE)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=Path("build/foundation/gate9-check"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--qemu-timeout", type=float, default=20.0)
    parser.add_argument("--stress", action="store_true")
    ns = parser.parse_args()
    root = repo_root()
    work = ns.work_dir.resolve() if ns.work_dir.is_absolute() else (root / ns.work_dir).resolve()
    try:
        report = check_gate9(root=root, work=work, clean=ns.clean,
            timeout_seconds=ns.timeout, qemu_timeout=ns.qemu_timeout, stress=ns.stress)
    except Core0Error as error:
        print(f"GATE 9 FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
