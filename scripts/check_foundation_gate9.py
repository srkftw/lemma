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
    record = runner.run_session(root=root, image=output / "image.elf", output_dir=work,
        scenario=scenario, timeout_seconds=timeout_seconds)
    if record != load_json(work / runner.RESULT_FILE) or record.get("status") != "PASS":
        raise Core0Error("monitor returned/persisted run differs or is not PASS")
    if record.get("image_sha256") != sha256(output / "image.elf"):
        raise Core0Error("monitor run is not bound to the current ELF")
    if (type(record.get("pid")) is not int or record["pid"] <= 0
            or record.get("ready_observed_before_input") is not True
            or record.get("stdin_open_until_exit") is not True
            or record.get("semantic_validation_after_exit") is not True
            or record.get("single_pid") is not True or record.get("single_elf") is not True):
        raise Core0Error("monitor session lacks its fresh single-process/post-boot input/exit evidence")
    if (scenario.requests or scenario.terminal_input) and record.get("first_input_after_ready") is not True:
        raise Core0Error("monitor requests were not written after READY")
    if record.get("binding", {}).get("audit_sha256") != sha256(output / "audit.json"):
        raise Core0Error("monitor record binds a stale audit")
    for name in ("sent.bin", "received.bin", "stderr.bin"):
        if record.get("raw_artifacts", {}).get(name) != sha256(work / name):
            raise Core0Error(f"monitor retained raw evidence differs: {name}")
    if (work / "stderr.bin").read_bytes():
        raise Core0Error("monitor emulator stderr is not empty")
    observed = runner.validate_transcript(scenario, (work / "sent.bin").read_bytes(),
        (work / "received.bin").read_bytes(), record["returncode"], record["machine"])
    if any(record.get(key) != value for key, value in observed.items()):
        raise Core0Error("monitor result differs from independent retained transcript revalidation")
    return record


def _verify_profiles(outputs: dict[str, Path], root: Path) -> dict[str, object]:
    hashes = {profile: {name: sha256(output / name) for name in runner.SOURCE_ARTIFACTS}
              for profile, output in outputs.items()}
    inputs = {profile: runner.source_inputs(output, root) for profile, output in outputs.items()}
    if hashes["O0"] != hashes["O2"] or inputs["O0"] != inputs["O2"]:
        raise Core0Error("monitor O0/O2 checked source/startup/ABI/source-input hashes differ")
    return {"same_checked_source": True, "source_artifacts": hashes["O0"], "source_inputs": inputs["O0"],
        "no_loader_fixture": True, "all_runtime_inputs_post_boot_uart": True}


def check_gate9(*, root: Path, work: Path, clean: bool, timeout_seconds: float,
                qemu_timeout: float) -> dict[str, object]:
    root, work = root.resolve(), work.resolve()
    _stage("work-directory-failure", str(work), lambda: (
        invalidate_output_file(work / RESULT_FILE, root),
        invalidate_output_file(work / (RESULT_FILE + ".tmp"), root),
        prepare_output_directory(work, root, clean=clean)))
    for name, value in (("build", timeout_seconds), ("qemu", qemu_timeout)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float("inf"):
            raise Gate9Failure("harness-input-failure", name, "timeout must be finite and positive")
    started = datetime.now(timezone.utc).isoformat()
    corpus_path = work / "corpus/gate9-cases.json"
    write_json(corpus_path, corpus.corpus_manifest())
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
            scenario=scenario, timeout_seconds=qemu_timeout)) for scenario in corpus.SCENARIOS]
        pids = [record["pid"] for record in targets]
        if len(set(pids)) != len(targets) or len({record["image_sha256"] for record in targets}) != 1:
            raise Gate9Failure("fresh-session-rejection", optimization, "sessions reused a PID or changed ELF")
        streams = [(work / "runs" / optimization / scenario.name / "sent.bin").read_bytes()
                   for scenario in corpus.MIXED_SCENARIOS]
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
    targets = [record for profile in profiles.values() for record in profile["targets"]]
    mixed = [record for record in targets if record["scenario"] in {scenario.name for scenario in corpus.MIXED_SCENARIOS}]
    active_terminal = [record for record in targets if record["scenario"] == "active-truncated-payload"]
    if len(active_terminal) != 2 or any(
        record.get("outcome") != "verified-terminal-rejection" or record.get("expected_exit") != 15
        or record.get("returncode") != 15 or len(record.get("responses", [])) != 1
        or record.get("summary", {}).get("active_at_terminal_input") is not True
        or type(record.get("summary", {}).get("observed_hardware_irqs")) is not int
        or record["summary"]["observed_hardware_irqs"] < 1 for record in active_terminal):
        raise Gate9Failure("missing-active-terminal-cleanup-evidence", "completion",
            "both active timer prefixes must validate START then terminate with exact truncation status")
    for record in mixed:
        summary = record.get("summary")
        if (not isinstance(summary, dict) or type(summary.get("observed_hardware_irqs")) is not int
                or summary["observed_hardware_irqs"] < 338
                or type(summary.get("hardware_work_commands")) is not int or summary["hardware_work_commands"] < 3
                or summary.get("synchronous_recoveries") != 5
                or summary.get("observed_overflow") is not True or summary.get("observed_ring_wrap") is not True):
            raise Gate9Failure("missing-hardware-integration-evidence", str(record.get("scenario")),
                "mixed summary lacks required real IRQ work/trap/overflow/wrap evidence")
    counts = {"fresh_qemu_boots": len(targets), "mixed_sessions": len(mixed),
        "terminal_sessions": sum(record["expected_exit"] != 0 for record in targets),
        "active_terminal_cleanup_sessions": len(active_terminal),
        "handled_requests": sum(record.get("summary", {}).get("handled_requests", 0) for record in targets),
        "actual_hardware_irqs": sum(record.get("summary", {}).get("observed_hardware_irqs", 0) for record in targets),
        "synchronous_recoveries": sum(record.get("summary", {}).get("synchronous_recoveries", 0) for record in targets),
        "retained_records_checked": sum(record.get("summary", {}).get("records_checked", 0) for record in targets),
        "source_rejections": len(rejections), "policy_probes": 50, "frontend_lowering": 1}
    if len(targets) != 2 * len(corpus.SCENARIOS) or len(mixed) != 4 or len(rejections) != 4:
        raise Gate9Failure("empty-or-incomplete-corpus", "completion", "mandatory sessions/probes are missing")
    if counts["actual_hardware_irqs"] < 1352 or counts["synchronous_recoveries"] < 20:
        raise Gate9Failure("missing-hardware-integration-evidence", "completion", "aggregate hardware/trap lower bounds differ")
    report = {"schema_version": 1, "status": "PASS", "gate": 9, "profile": corpus.PROFILE,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "corpus": str(corpus_path.relative_to(root)), "corpus_sha256": sha256(corpus_path),
        "profiles": profiles, "source_binding": shared, "source_probes": probes,
        "source_rejections": rejections, "counts": counts,
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
    ns = parser.parse_args()
    root = repo_root()
    work = ns.work_dir.resolve() if ns.work_dir.is_absolute() else (root / ns.work_dir).resolve()
    try:
        report = check_gate9(root=root, work=work, clean=ns.clean,
            timeout_seconds=ns.timeout, qemu_timeout=ns.qemu_timeout)
    except Core0Error as error:
        print(f"GATE 9 FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
