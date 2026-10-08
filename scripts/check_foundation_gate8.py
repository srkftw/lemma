#!/usr/bin/env python3
"""Gate 8 acceptance: genuine checked-source builds and actual timer IRQs."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar

import audit_core0
import gate8_corpus as corpus
import run_timer_case
from build_core0 import invalidate_output_file, prepare_output_directory
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json

RESULT_FILE = "gate8-results.json"
SOURCE_ARTIFACTS = ("program.ll", "startup.S", "link.ld", "layout.json", "device-contract.json",
    "timer-suite-manifest.json", "timer-suite-normalized.txt", "timer-test-abi.json", "symbols.txt")
FRONTEND_MARKER = "Gate 8 frontend/lowering probe passed (7 timer ops, canonical Bool ABI, transitive effects, stale metadata/effect and legacy-profile rejections)"
POLICY_MARKER = "TIMER_POLICY_PROBES:26 MODEL_PROBES:6 CONDITIONAL_LEMMAS:6"
LEMMA_NAMES = ("valid_nextDeadline_greater", "valid_nextDeadline_noWrap",
    "enqueue_counts_one_hardware_interrupt", "enqueue_keeps_skipped_separate",
    "enqueue_preserves_capacity", "enqueue_overflow_accounting")
REJECTION_FILES = ("V06Timer.lean", "StoredTimerContinuation.lean", "HiddenExternTimer.lean", "PureTimerResult.lean")
REJECTION_NAMES = ("v06-timer", "stored-timer-continuation", "hidden-extern-timer", "pure-timer-result")
REJECTION_CODES = ("unsupported-primitive", "unsupported-expression", "unsupported-declaration", "unsupported-type")
REJECTION_FRAGMENTS = (
    ("timer operation `timer.read-time` requires `core0-v0.7`; `core0-v0.6` does not admit timer/interrupt operations", "dependency path: root"),
    ("Action result continuation must be an immediate lambda; stored/dynamic continuations are rejected", "dependency path: root"),
    ("Action declaration `forbidden` has an arbitrary @[extern] implementation", "dependency path: root -> forbidden"),
    ("effectful declaration result is not the exact Lemma.Core0.Memory.Action type", "dependency path: root"),
)
T = TypeVar("T")


class Gate8Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category, self.context, self.detail = category, context, detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate8Failure:
        raise
    except run_timer_case.TimerRunFailure as error:
        raise Gate8Failure(error.category, context, str(error)) from error
    except (Core0Error, OSError, ValueError, UnicodeError, TypeError) as error:
        raise Gate8Failure(category, context, str(error)) from error


def build_timer_suite(**kwargs: object) -> dict[str, object]:
    from build_timer_suite import build_timer_suite as build
    return build(**kwargs)


def _verify_profiles(outputs: dict[str, Path], root: Path) -> dict[str, object]:
    artifacts = {profile: {name: sha256(directory / name) for name in SOURCE_ARTIFACTS}
                 for profile, directory in outputs.items()}
    if artifacts["O0"] != artifacts["O2"]:
        raise Core0Error("timer O0/O2 do not use byte-identical checked source/startup/ABI")
    inputs = {profile: run_timer_case.source_inputs(directory, root)
              for profile, directory in outputs.items()}
    if inputs["O0"] != inputs["O2"]:
        raise Core0Error("timer O0/O2 source input hashes differ")
    return {"same_checked_source": True, "checked_source_artifacts": artifacts["O0"],
            "source_inputs": inputs["O0"], "runtime_fixture_not_a_build_input": True}


def _verify_mutation(control: Path, mutant: Path, root: Path, mutation: int) -> dict[str, object]:
    corpus.validate_mutation(mutation)
    if mutation == 0:
        raise Core0Error("mutation comparison requires a real test-only defect")
    same = tuple(name for name in SOURCE_ARTIFACTS if name not in ("startup.S", "timer-suite-manifest.json")) + ("program.opt.ll", "program.o")
    for name in same:
        if (control / name).read_bytes() != (mutant / name).read_bytes():
            raise Core0Error(f"timer mutant unexpectedly changes {name}")
    clean_text, bad_text = ((directory / "startup.S").read_text(encoding="utf-8") for directory in (control, mutant))
    if mutation == 1:
        pattern = re.compile(r"(?m)^(\s*ld\s+s3,\s*)144(\(sp\)\s*)$")
        expected, count = pattern.subn(r"\g<1>152\g<2>", clean_text)
    else:
        start = clean_text.find("core0_timer_set_compare:\n")
        stop = clean_text.find(".size core0_timer_set_compare,", start)
        if start < 0 or stop < 0:
            raise Core0Error("timer arming control lacks its exact function boundary")
        body = clean_text[start:stop]
        pattern = re.compile(r"(?m)^(\s*sd\s+)a0(,\s*0\(t0\)\s*)$")
        replacement, count = pattern.subn(r"\g<1>t1\g<2>", body)
        expected = clean_text[:start] + replacement + clean_text[stop:]
    if count != 1 or expected != bad_text:
        raise Core0Error("timer mutant is not the exact single approved structured-machine delta")
    manifests = []
    for directory, selected in ((control, 0), (mutant, mutation)):
        raw = load_json(directory / "timer-suite-manifest.json")
        if not isinstance(raw, dict):
            raise Core0Error("timer mutation manifest is not an object")
        raw = raw.copy()
        if raw.pop("timer_mutation", None) != run_timer_case.mutation_metadata(selected):
            raise Core0Error("timer mutation metadata differs from its quarantined transformation")
        manifests.append(raw)
    if manifests[0] != manifests[1] or run_timer_case.source_inputs(control, root) != run_timer_case.source_inputs(mutant, root):
        raise Core0Error("timer mutation changed source/checked metadata beyond its permitted machine delta")
    return dict(run_timer_case.mutation_metadata(mutation), checked_source_and_compiled_program_identical=True)


def _load_rejections(root: Path) -> tuple[dict[str, object], ...]:
    directory = root / "examples/foundation/gate8-reject"
    raw = load_json(directory / "rejections.json")
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "profile", "legacy_profile", "cases"} or raw.get("schema_version") != 1 or raw.get("profile") != corpus.PROFILE or raw.get("legacy_profile") != "core0-v0.6":
        raise Core0Error("timer rejection manifest identity differs")
    expected = [{"name": name, "path": f"examples/foundation/gate8-reject/{file}",
                 "diagnostic_code": code, "required_fragments": list(fragments)}
                for name, file, code, fragments in zip(REJECTION_NAMES, REJECTION_FILES, REJECTION_CODES, REJECTION_FRAGMENTS, strict=True)]
    if raw.get("cases") != expected or {path.name for path in directory.glob("*.lean")} != set(REJECTION_FILES):
        raise Core0Error("timer rejection file/diagnostic catalog differs")
    for file in REJECTION_FILES:
        source = directory / file
        if not source.is_file() or not source.resolve().is_relative_to(directory.resolve()):
            raise Core0Error("missing/escaped timer rejection fixture")
    return tuple(expected)


def _run_rejections(*, root: Path, work: Path, timeout_seconds: float) -> list[dict[str, object]]:
    work.mkdir(parents=True, exist_ok=True)
    records = []
    for case in _load_rejections(root):
        argv = ("lake", "env", "lean", str(case["path"]))
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str(work / str(case["name"]))
        result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds, env=environment)
        text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = work / f"{case['name']}.txt"
        log.write_text(text, encoding="utf-8")
        errors = [line for line in text.splitlines() if re.search(r"(?:^|:\s)error:", line)]
        if result.returncode == 0 or len(errors) != 1 or f"error: Core0[{case['diagnostic_code']}]" not in errors[0] or any(fragment not in text for fragment in case["required_fragments"]):
            raise Core0Error(f"timer source rejection {case['name']} lacks exactly its intended diagnostic")
        if any(fragment in text for fragment in ("lean.unknownIdentifier", "declaration uses 'sorry'", "Aborting evaluation", "unknown declaration")):
            raise Core0Error(f"timer source rejection {case['name']} has unrelated failures")
        records.append(dict(case, argv=list(argv), returncode=result.returncode,
            source_sha256=sha256(root / str(case["path"])), diagnostic_log=str(log.relative_to(root)),
            diagnostic_sha256=sha256(log)))
    return records


def _parse_policy_output(text: str) -> list[dict[str, object]]:
    if re.findall(r"(?m)^TIMER_POLICY_PROBES:\d+ MODEL_PROBES:\d+ CONDITIONAL_LEMMAS:\d+$", text) != [POLICY_MARKER] or "sorryAx" in text:
        raise Core0Error("timer policy/model probes did not complete exactly 26/6/6")
    records = []
    for index, name in enumerate(LEMMA_NAMES):
        quoted = rf"'(?:Lemma\.Core0\.Timer\.Model\.)?{name}'"
        matches = re.findall(quoted + r" (?:depends on axioms:\s*\[([^\]]*)\]|(does not depend on any axioms))", text)
        if len(matches) != 1:
            raise Core0Error(f"missing/duplicate timer axiom report for {name}")
        axioms = [item.strip() for item in matches[0][0].split(",") if item.strip()]
        expected = [] if index == 0 else ["propext"]
        if axioms != expected:
            raise Core0Error(f"timer conditional lemma axiom set differs for {name}")
        records.append({"theorem": name, "axioms": axioms})
    return records


def _run_probes(*, root: Path, work: Path, timeout_seconds: float) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    records = {}
    for name, file, marker in (("policy", "TimerPolicyProbes.lean", POLICY_MARKER),
                               ("frontend", "TimerFrontendProbes.lean", FRONTEND_MARKER)):
        relative = f"examples/foundation/{file}"
        source = root / relative
        before = sha256(source)
        text_source = source.read_text(encoding="utf-8")
        if any(re.search(rf"\b{token}\b", text_source) for token in ("sorry", "admit", "native_decide")):
            raise Core0Error("timer probe uses a forbidden proof device")
        if name == "policy" and len(re.findall(r"(?m)^#guard\s", text_source)) != 32:
            raise Core0Error("timer policy/model source no longer contains exactly 32 guard probes")
        argv = ("lake", "env", "lean", relative)
        result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = work / f"timer-{name}.txt"
        log.write_text(output, encoding="utf-8")
        if result.returncode != 0 or output.count(marker) != 1 or "sorryAx" in output or "declaration uses 'sorry'" in output or before != sha256(source):
            raise Core0Error(f"timer {name} probe failed, changed source, or lacked its exact success marker")
        record = {"source": relative, "source_sha256": before, "argv": list(argv),
            "returncode": result.returncode, "log": str(log.relative_to(root)), "log_sha256": sha256(log),
            "scope": "source/frontend/finite-model observations, not hardware or compiler correctness proof"}
        if name == "policy":
            record.update(policy_probes=26, model_probes=6, conditional_lemmas=_parse_policy_output(output))
        records[name] = record
    return records


def _target(*, root: Path, output: Path, case: corpus.TimerCase, work: Path,
            timeout: float, mutation: int = 0) -> dict[str, object]:
    record = run_timer_case.run_case(root=root, image=output / "image.elf", case=case,
        output_dir=work, timeout_seconds=timeout, mutation=mutation)
    if record != load_json(work / run_timer_case.RESULT_FILE) or record.get("status") != "PASS":
        raise Core0Error("timer returned/persisted run record differs or is not PASS")
    if record.get("image_sha256") != sha256(output / "image.elf") or record.get("runtime_input") != {key: getattr(case, key) for key in ("seed", "goal", "period", "scenario")}:
        raise Core0Error("timer target record is not bound to current image/runtime input")
    fixture = work / "runtime-input.bin"
    if fixture.read_bytes() != corpus.fixture_bytes(case) or record.get("fixture_sha256") != sha256(fixture):
        raise Core0Error("timer runtime fixture bytes/hash differ")
    for name in ("uart.bin", "stderr.bin"):
        if record.get("raw_artifacts", {}).get(name) != sha256(work / name):
            raise Core0Error("timer raw retained artifact hash differs")
    if (work / "stderr.bin").read_bytes():
        raise Core0Error("timer QEMU stderr is not empty")
    observed = run_timer_case.validate_transcript(case, (work / "uart.bin").read_bytes(),
        record["returncode"], record["machine"], mutation=mutation)
    if any(record.get(key) != value for key, value in observed.items()):
        raise Core0Error("timer outcome differs from independent retained transcript revalidation")
    return record


def check_gate8(*, root: Path, work: Path, clean: bool, timeout_seconds: float,
                qemu_timeout: float) -> dict[str, object]:
    root, work = root.resolve(), work.resolve()
    _stage("work-directory-failure", str(work), lambda: (
        invalidate_output_file(work / RESULT_FILE, root),
        invalidate_output_file(work / (RESULT_FILE + ".tmp"), root),
        prepare_output_directory(work, root, clean=clean)))
    for name, value in (("build", timeout_seconds), ("qemu", qemu_timeout)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float("inf"):
            raise Gate8Failure("harness-input-failure", name, "timeout must be finite and positive")
    started = datetime.now(timezone.utc).isoformat()
    corpus_path = work / "corpus/gate8-cases.json"
    write_json(corpus_path, corpus.corpus_manifest())
    profiles, outputs = {}, {}
    for index, profile in enumerate(("O0", "O2")):
        output = outputs[profile] = work / profile
        build = _stage("compile-or-link-failure", profile, lambda: build_timer_suite(root=root,
            output_dir=output, opt_level=profile, mutation=0, clean=False,
            build_lean=index == 0, timeout_seconds=timeout_seconds))
        if build != load_json(output / "build.json") or build.get("optimization") != profile:
            raise Gate8Failure("build-record-rejection", profile, "returned/persisted profile differs")
        audit = _stage("machine-audit-rejection", profile,
            lambda: audit_core0.audit(output, root, policy=corpus.ARTIFACT_CATEGORY))
        _stage("image-binding-rejection", profile,
            lambda: run_timer_case.validate_image_binding(output / "image.elf", root=root))
        targets = [_stage("target-failure", f"{profile}/{case.name}", lambda case=case: _target(
            root=root, output=output, case=case, work=work / "runs" / profile / case.name,
            timeout=qemu_timeout)) for case in (*corpus.POSITIVE_CASES, *corpus.NEGATIVE_CASES)]
        mutants = {}
        for mutation, case in corpus.MUTANT_CASES.items():
            mutant_output = work / "mutants" / profile / corpus.MUTATION_IDENTITIES[mutation]
            bad_build = _stage("mutant-compile-or-link-failure", f"{profile}/{mutation}", lambda: build_timer_suite(
                root=root, output_dir=mutant_output, opt_level=profile, mutation=mutation,
                clean=False, build_lean=False, timeout_seconds=timeout_seconds))
            if bad_build != load_json(mutant_output / "build.json"):
                raise Gate8Failure("mutant-build-record-rejection", profile, "mutant build return/persisted record differs")
            bad_audit = _stage("mutant-machine-audit-rejection", f"{profile}/{mutation}",
                lambda: audit_core0.audit(mutant_output, root, policy=corpus.ARTIFACT_CATEGORY))
            delta = _stage("mutation-delta-rejection", f"{profile}/{mutation}",
                lambda: _verify_mutation(output, mutant_output, root, mutation))
            control = _stage("mutant-control-failure", f"{profile}/{mutation}", lambda: _target(
                root=root, output=output, case=case,
                work=work / "runs" / profile / (case.name + "-clean-control"), timeout=qemu_timeout))
            target = _stage("mutation-behavior-failure", f"{profile}/{mutation}", lambda: _target(
                root=root, output=mutant_output, case=case,
                work=work / "runs" / profile / (case.name + "-mutant"), timeout=qemu_timeout, mutation=mutation))
            expected = "verified-behavioral-context-mismatch" if mutation == 1 else "verified-missing-hardware-interrupt"
            if control.get("outcome") != "verified-positive" or target.get("outcome") != expected:
                raise Gate8Failure("mutation-behavior-failure", profile, "mutant lacks an unchanged successful control and exact behavioral failure")
            mutants[str(mutation)] = {"build": bad_build, "audit": bad_audit, "delta": delta,
                                      "clean_control": control, "target": target}
        profiles[profile] = {"build": build, "audit": audit, "target_cases": targets, "mutations": mutants}
    identity = _stage("profile-source-identity-rejection", "O0/O2", lambda: _verify_profiles(outputs, root))
    rejections = _stage("frontend-rejection-failure", corpus.PROFILE,
        lambda: _run_rejections(root=root, work=work / "rejections", timeout_seconds=timeout_seconds))
    probes = _stage("source-probe-failure", corpus.PROFILE,
        lambda: _run_probes(root=root, work=work / "probes", timeout_seconds=timeout_seconds))
    _stage("final-source-binding-failure", "O0/O2", lambda: _verify_profiles(outputs, root))
    observed_irqs = sum(record["stats"]["irq_count"] for profile in profiles.values()
                        for record in profile["target_cases"] if record["outcome"] == "verified-positive")
    report = {"schema_version": 1, "status": "pass", "gate": 8, "profile": corpus.PROFILE,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {"path": str(corpus_path.relative_to(root)), "sha256": sha256(corpus_path)},
        "profiles": profiles, "profile_source_identity": identity,
        "negative_cases": {corpus.PROFILE: rejections}, "source_probes": probes,
        "counts": {"profiles": 2, "positive_cases_per_profile": len(corpus.POSITIVE_CASES),
            "negative_cases_per_profile": len(corpus.NEGATIVE_CASES),
            "qemu_boots_total": 2 * (len(corpus.POSITIVE_CASES) + len(corpus.NEGATIVE_CASES) + 2 * len(corpus.MUTANT_CASES)),
            "observed_hardware_irqs_positive_cases": observed_irqs,
            "behavioral_restore_mutants_detected": 2, "disabled_arming_mutants_detected": 2,
            "frontend_rejections": len(rejections), "direct_policy_probes": 26,
            "finite_model_probes": 6, "conditional_model_lemmas": 6, "frontend_probe_commands": 1},
        "limitations": ["Pinned QEMU single-hart M-mode timer tests; no physical-board or hard-real-time claim.",
            "Fixed aligned RAM and non-nested no-NMI entry/return premises remain explicit.",
            "ISR formatting is deferred; ring overflow drops events and records losses separately from hardware entries.",
            "Checked M-mode accesses are not page-table isolation or protection against arbitrary privileged code.",
            "Local models/lemmas and finite target tests do not prove compiler/hardware correctness or complete G1/G2."],
    }
    temporary = work / (RESULT_FILE + ".tmp")
    write_json(temporary, report)
    temporary.replace(work / RESULT_FILE)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=Path("build/foundation/gate8"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--qemu-timeout", type=float, default=60)
    args = parser.parse_args()
    root = repo_root()
    work = args.work_dir if args.work_dir.is_absolute() else root / args.work_dir
    try:
        report = check_gate8(root=root, work=work, clean=args.clean,
            timeout_seconds=args.timeout, qemu_timeout=args.qemu_timeout)
    except (Core0Error, OSError, ValueError) as error:
        print(f"GATE 8 FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
