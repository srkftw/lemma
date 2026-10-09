#!/usr/bin/env python3
"""Gate 7: fresh checked-source builds, audited traps, and QEMU observations.

This is a bounded synchronous-trap conformance check, not a compiler or
hardware correctness proof.  A final PASS is published only after both
optimization profiles, exact source rejections, local policy probes, and the
behaviorally detected restore mutation have succeeded.
"""
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
import gate7_corpus as corpus
import run_trap_case
from build_core0 import invalidate_output_file, prepare_output_directory
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json

RESULT_FILE = "gate7-results.json"
FRONTEND_MARKER = "Gate 7 frontend/lowering probe passed (4 trap ops, transitive effects, stale metadata/effect and legacy-profile rejections)"
SOURCE_ARTIFACTS = ("program.ll", "startup.S", "link.ld", "layout.json", "device-contract.json",
                    "trap-suite-manifest.json", "trap-suite-normalized.txt", "trap-test-abi.json", "symbols.txt")
REJECTION_FILES = ("V05Trap.lean", "StoredTrapContinuation.lean", "HiddenExternTrap.lean", "PureTrapResult.lean")
REJECTION_CODES = ("unsupported-primitive", "unsupported-expression", "unsupported-declaration", "unsupported-type")
REJECTION_NAMES = ("v05-trap", "stored-trap-continuation", "hidden-extern-trap", "pure-trap-result")
REJECTION_FRAGMENTS = (
    ("trap operation `trap.ecall` requires `core0-v0.6`; `core0-v0.5` does not admit synchronous traps", "dependency path: root"),
    ("Action result continuation must be an immediate lambda; stored/dynamic continuations are rejected", "dependency path: root"),
    ("Action declaration `forbidden` has an arbitrary @[extern] implementation", "dependency path: root -> forbidden"),
    ("effectful declaration result is not the exact Lemma.Core0.Memory.Action type", "dependency path: root"),
)
T = TypeVar("T")


class Gate7Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category, self.context, self.detail = category, context, detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate7Failure:
        raise
    except run_trap_case.TrapRunFailure as error:
        raise Gate7Failure(error.category, context, str(error)) from error
    except (Core0Error, OSError, ValueError, UnicodeError, TypeError) as error:
        raise Gate7Failure(category, context, str(error)) from error


def build_trap_suite(**kwargs: object) -> dict[str, object]:
    # Lazy import also keeps pure checker/corpus unit tests independent of
    # optional build tools; the actual acceptance always executes this builder.
    from build_trap_suite import build_trap_suite as build
    return build(**kwargs)


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{name} is not an object")
    return value


def _source_inputs(directory: Path, root: Path) -> dict[str, str]:
    provenance = _object(load_json(directory / "provenance.json"), "provenance")
    entries = provenance.get("source_inputs")
    if not isinstance(entries, list) or not entries:
        raise Core0Error("trap provenance lacks source inputs")
    result: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise Core0Error("malformed provenance source input")
        path, digest = item["path"], item["sha256"]
        if not isinstance(path, str) or Path(path).is_absolute() or not isinstance(digest, str) or path in result:
            raise Core0Error("unsafe/duplicate provenance source input")
        source = (root / path).resolve()
        if not source.is_relative_to(root.resolve()) or sha256(source) != digest:
            raise Core0Error(f"stale or escaped trap source input: {path}")
        result[path] = digest
    required = {"examples/foundation/TrapConformance.lean", "examples/foundation/TrapBuild.lean",
                "Lemma/Compiler/Test/TrapExport.lean", "Lemma/Machine/TrapPrimitives.lean",
                "Lemma/Machine/TrapLayout.lean", "scripts/gate7_corpus.py", "scripts/run_trap_case.py",
                "scripts/check_foundation_gate7.py"}
    if not required <= result.keys():
        raise Core0Error("trap provenance omits required source/compiler/machine/host inputs")
    return result


def _verify_profiles(outputs: dict[str, Path], root: Path) -> dict[str, object]:
    identities = {name: {file: sha256(path / file) for file in SOURCE_ARTIFACTS}
                  for name, path in outputs.items()}
    if identities["O0"] != identities["O2"]:
        raise Core0Error("O0/O2 do not use byte-identical checked source/startup/ABI envelopes")
    inputs = {name: _source_inputs(path, root) for name, path in outputs.items()}
    if inputs["O0"] != inputs["O2"]:
        raise Core0Error("O0/O2 source input hashes differ")
    return {"checked_source_artifacts": identities["O0"], "source_inputs": inputs["O0"],
            "same_checked_source": True, "runtime_fixture_not_a_build_input": True}


def _verify_mutation(control: Path, mutant: Path, root: Path) -> dict[str, object]:
    exact_same = tuple(file for file in SOURCE_ARTIFACTS if file not in ("startup.S", "trap-suite-manifest.json")) + ("program.opt.ll", "program.o")
    for name in exact_same:
        if (control / name).read_bytes() != (mutant / name).read_bytes():
            raise Core0Error(f"restore mutant unexpectedly changed {name}")
    clean_text = (control / "startup.S").read_text(encoding="utf-8")
    mutant_text = (mutant / "startup.S").read_text(encoding="utf-8")
    pattern = re.compile(r"(?m)^(\s*ld\s+s3,\s*)144(\(sp\)\s*)$")
    expected, count = pattern.subn(r"\g<1>152\g<2>", clean_text)
    if count != 1 or expected != mutant_text:
        raise Core0Error("restore mutant is not exactly one ld s3,144(sp) -> ld s3,152(sp) delta")
    clean_manifest = _object(load_json(control / "trap-suite-manifest.json"), "control manifest").copy()
    mutant_manifest = _object(load_json(mutant / "trap-suite-manifest.json"), "mutant manifest").copy()
    clean_meta, mutant_meta = clean_manifest.pop("restore_mutation", None), mutant_manifest.pop("restore_mutation", None)
    if clean_manifest != mutant_manifest:
        raise Core0Error("restore mutation changed checked source manifest beyond its quarantined metadata")
    for metadata, identity, matches in ((clean_meta, "none", 0), (mutant_meta, "restore-s3-from-s4", 1)):
        if metadata != {"identity": identity, "production_selectable": False,
                        "transform_stage": "structured-machine-restore", "match_count": matches}:
            raise Core0Error("restore mutation metadata differs from the exact test-only transformation")
    if _source_inputs(control, root) != _source_inputs(mutant, root):
        raise Core0Error("restore mutant/control source provenance differs")
    return {"identity": "restore-s3-from-s4", "production_selectable": False,
            "match_count": 1, "only_machine_delta": "ld s3,144(sp) -> ld s3,152(sp)",
            "checked_source_and_compiled_program_identical": True,
            "expected_context_mask": corpus.MUTANT_MASK}


def _load_rejections(root: Path) -> tuple[dict[str, object], ...]:
    directory = root / "examples/foundation/gate7-reject"
    raw = _object(load_json(directory / "rejections.json"), "Gate 7 rejection manifest")
    if set(raw) != {"schema_version", "profile", "legacy_profile", "cases"} or raw.get("schema_version") != 1 or raw.get("profile") != corpus.PROFILE or raw.get("legacy_profile") != "core0-v0.5":
        raise Core0Error("Gate 7 rejection manifest identity differs")
    expected = [{"name": name, "path": f"examples/foundation/gate7-reject/{file}",
                 "diagnostic_code": code, "required_fragments": list(fragments)}
                for name, file, code, fragments in zip(REJECTION_NAMES, REJECTION_FILES, REJECTION_CODES, REJECTION_FRAGMENTS, strict=True)]
    if raw.get("cases") != expected or {path.name for path in directory.glob("*.lean")} != set(REJECTION_FILES):
        raise Core0Error("Gate 7 rejection manifest/file/diagnostic catalog differs")
    for file in REJECTION_FILES:
        path = directory / file
        if not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
            raise Core0Error("missing/escaped Gate 7 rejection fixture")
    return tuple(expected)


def _run_rejections(*, root: Path, work: Path, timeout_seconds: float) -> list[dict[str, object]]:
    cases = _load_rejections(root)
    work.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases:
        argv = ("lake", "env", "lean", str(case["path"]))
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str(work / str(case["name"]))
        result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds, env=environment)
        text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = work / f"{case['name']}.txt"
        log.write_text(text, encoding="utf-8")
        errors = [line for line in text.splitlines() if re.search(r"(?:^|:\s)error:", line)]
        marker = f"Core0[{case['diagnostic_code']}]"
        if result.returncode == 0 or len(errors) != 1 or marker not in errors[0] or "error: Core0[" not in errors[0]:
            raise Core0Error(f"source rejection {case['name']} did not fail with exactly the intended diagnostic")
        if any(fragment not in text for fragment in case["required_fragments"]):
            raise Core0Error(f"source rejection {case['name']} lacks intended diagnostic details")
        if any(fragment in text for fragment in ("lean.unknownIdentifier", "declaration uses 'sorry'", "Aborting evaluation", "unknown declaration")):
            raise Core0Error(f"source rejection {case['name']} has unrelated failures")
        records.append(dict(case, argv=list(argv), returncode=result.returncode,
                            source_sha256=sha256(root / str(case["path"])),
                            diagnostic_log=str(log.relative_to(root)), diagnostic_sha256=sha256(log)))
    return records


def _parse_policy_output(text: str) -> list[dict[str, object]]:
    if re.findall(r"(?m)^TRAP_POLICY_PROBES:(\d+)\s*$", text) != ["20"] or "sorryAx" in text:
        raise Core0Error("direct source policy probes did not complete exactly 20 checks")
    records = []
    for name in ("approvedEcallResume", "approvedBreakpointResume"):
        match = re.search(rf"'{name}' depends on axioms:\s*\[([^\]]*)\]", text)
        no_axioms = f"'{name}' does not depend on any axioms" in text
        if match is None and not no_axioms:
            raise Core0Error(f"missing axiom report for conditional policy lemma {name}")
        axioms = [] if match is None else [item.strip() for item in match[1].split(",") if item.strip()]
        if set(axioms) - {"propext", "Classical.choice", "Quot.sound"}:
            raise Core0Error(f"unexpected axiom in conditional policy lemma {name}")
        records.append({"theorem": name, "axioms": axioms,
                        "premise": "(mstatus & 0x21888) == 0x1800"})
    return records


def _run_policy_probes(*, root: Path, work: Path, timeout_seconds: float) -> dict[str, object]:
    relative = "examples/foundation/TrapPolicyProbes.lean"
    source = root / relative
    text_source = source.read_text(encoding="utf-8")
    if any(re.search(rf"\b{token}\b", text_source) for token in ("sorry", "admit", "native_decide")):
        raise Core0Error("conditional policy lemma source uses a forbidden proof device")
    if len(re.findall(r"(?m)^#guard\s", text_source)) != 20:
        raise Core0Error("direct policy source no longer contains exactly 20 guard probes")
    argv = ("lake", "env", "lean", relative)
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    work.mkdir(parents=True, exist_ok=True)
    log = work / "trap-policy.txt"
    log.write_text(output, encoding="utf-8")
    if result.returncode != 0:
        raise Core0Error(f"direct Lean source policy probes failed: {output}")
    lemmas = _parse_policy_output(output)
    return {"source": relative, "source_sha256": sha256(source), "argv": list(argv),
            "returncode": result.returncode, "probe_count": 20, "conditional_lemmas": lemmas,
            "log": str(log.relative_to(root)), "log_sha256": sha256(log),
            "scope": "direct Lean source/local policy facts; not a target compiler or hardware proof"}


def _run_frontend_probe(*, root: Path, work: Path, timeout_seconds: float) -> dict[str, object]:
    relative = "examples/foundation/TrapFrontendProbes.lean"
    source = root / relative
    before = sha256(source)
    argv = ("lake", "env", "lean", relative)
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    work.mkdir(parents=True, exist_ok=True)
    log = work / "trap-frontend.txt"
    log.write_text(text, encoding="utf-8")
    if result.returncode != 0 or text.count(FRONTEND_MARKER) != 1 or "sorryAx" in text or "declaration uses 'sorry'" in text:
        raise Core0Error("Gate 7 frontend/lowering/model probe did not complete its exact success marker")
    if before != sha256(source):
        raise Core0Error("frontend probe source changed during execution")
    return {"source": relative, "source_sha256": before, "argv": list(argv),
            "returncode": result.returncode, "log": str(log.relative_to(root)), "log_sha256": sha256(log),
            "checks": ["four exact trap identities and no-argument i64 lowerings",
                       "transitive effects through calls, branches and fold callback",
                       "historical non-trap effect rendering preserved",
                       "stale trap-operation metadata rejected", "stale transitive effects rejected",
                       "forged legacy profile rejected", "RAM model refuses real trap execution",
                       "UART model refuses real trap execution"],
            "scope": "actual checked frontend/lowering and finite-model refusal; not target trap execution"}


def _target(*, root: Path, output: Path, case: corpus.TrapCase, work: Path,
            timeout: float, mutant: bool = False) -> dict[str, object]:
    record = run_trap_case.run_case(root=root, image=output / "image.elf", case=case,
                                   output_dir=work, timeout_seconds=timeout, mutant=mutant)
    if record != load_json(work / run_trap_case.RESULT_FILE) or record.get("status") != "PASS":
        raise Core0Error("returned/persisted target run record differs or is not PASS")
    if record.get("image_sha256") != sha256(output / "image.elf") or record.get("runtime_input") != {"seed": case.seed, "count": case.count, "scenario": case.scenario}:
        raise Core0Error("target record is not bound to the current image/runtime input")
    if (work / "runtime-input.bin").read_bytes() != corpus.fixture_bytes(case):
        raise Core0Error("target fixture differs from the runtime case")
    for file in ("uart.bin", "stderr.bin"):
        if record.get("raw_artifacts", {}).get(file) != sha256(work / file):
            raise Core0Error("target raw artifact hash differs")
    if (work / "stderr.bin").read_bytes():
        raise Core0Error("target QEMU stderr is not empty")
    observed = run_trap_case.validate_transcript(case, (work / "uart.bin").read_bytes(),
                                               record["returncode"], record["symbols"], mutant=mutant)
    if any(record.get(key) != value for key, value in observed.items()):
        raise Core0Error("target outcome differs from independent transcript revalidation")
    return record


def check_gate7(*, root: Path, work: Path, clean: bool, timeout_seconds: float,
                qemu_timeout: float) -> dict[str, object]:
    root, work = root.resolve(), work.resolve()
    _stage("work-directory-failure", str(work), lambda: (
        invalidate_output_file(work / RESULT_FILE, root),
        invalidate_output_file(work / (RESULT_FILE + ".tmp"), root),
        prepare_output_directory(work, root, clean=clean)))
    started = datetime.now(timezone.utc).isoformat()
    corpus_path = work / "corpus" / "gate7-cases.json"
    write_json(corpus_path, corpus.corpus_manifest())
    profiles: dict[str, dict[str, object]] = {}
    outputs: dict[str, Path] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = outputs[profile] = work / profile
        build = _stage("compile-or-link-failure", profile, lambda: build_trap_suite(
            root=root, output_dir=output, opt_level=profile, mutation=0, clean=False,
            build_lean=index == 0, timeout_seconds=timeout_seconds))
        if build != load_json(output / "build.json") or build.get("optimization") != profile:
            raise Gate7Failure("build-record-rejection", profile, "returned/persisted build profile differs")
        audit = _stage("machine-audit-rejection", profile, lambda: audit_core0.audit(output, root, policy=corpus.ARTIFACT_CATEGORY))
        if audit.get("status") != "pass" or audit.get("artifact_category") != corpus.ARTIFACT_CATEGORY or not isinstance(audit.get("trap_machine_audit"), dict):
            raise Gate7Failure("machine-audit-rejection", profile, "trap-specific audit is absent/not successful")
        _stage("image-binding-rejection", profile, lambda: run_trap_case.validate_image_binding(output / "image.elf"))
        target = [_stage("target-failure", f"{profile}/{case.name}", lambda case=case: _target(
            root=root, output=output, case=case, work=work / "runs" / profile / case.name, timeout=qemu_timeout))
            for case in (*corpus.POSITIVE_CASES, *corpus.NEGATIVE_CASES)]
        mutant_output = work / "mutants" / profile
        mutant_build = _stage("mutant-compile-or-link-failure", profile, lambda: build_trap_suite(
            root=root, output_dir=mutant_output, opt_level=profile, mutation=1, clean=False,
            build_lean=False, timeout_seconds=timeout_seconds))
        if mutant_build != load_json(mutant_output / "build.json"):
            raise Gate7Failure("mutant-build-record-rejection", profile, "returned/persisted mutant build differs")
        mutant_audit = _stage("mutant-machine-audit-rejection", profile,
            lambda: audit_core0.audit(mutant_output, root, policy=corpus.ARTIFACT_CATEGORY))
        if mutant_audit.get("status") != "pass" or not isinstance(mutant_audit.get("trap_machine_audit"), dict):
            raise Gate7Failure("mutant-machine-audit-rejection", profile, "mutant did not remain a valid audited ELF")
        delta = _stage("mutation-delta-rejection", profile, lambda: _verify_mutation(output, mutant_output, root))
        control = _stage("mutant-control-failure", profile, lambda: _target(root=root, output=output,
            case=corpus.MUTANT_CASE, work=work / "runs" / profile / "restore-clean-control", timeout=qemu_timeout))
        mutant = _stage("mutation-behavior-failure", profile, lambda: _target(root=root, output=mutant_output,
            case=corpus.MUTANT_CASE, work=work / "runs" / profile / "restore-mutant", timeout=qemu_timeout, mutant=True))
        if control.get("outcome") != "verified-positive" or mutant.get("outcome") != "verified-behavioral-context-mismatch":
            raise Gate7Failure("mutation-behavior-failure", profile, "restore mutation was not detected by the live context checker")
        profiles[profile] = {"build": build, "audit": audit, "target_cases": target,
                             "restore_mutation": {"build": mutant_build, "audit": mutant_audit,
                                                  "delta": delta, "clean_control": control, "target": mutant}}
    identity = _stage("profile-source-identity-rejection", "O0/O2", lambda: _verify_profiles(outputs, root))
    rejections = _stage("frontend-rejection-failure", corpus.PROFILE,
                        lambda: _run_rejections(root=root, work=work / "rejections", timeout_seconds=timeout_seconds))
    probes = _stage("source-policy-probe-failure", corpus.PROFILE,
                    lambda: _run_policy_probes(root=root, work=work / "probes", timeout_seconds=timeout_seconds))
    frontend = _stage("frontend-probe-failure", corpus.PROFILE,
                      lambda: _run_frontend_probe(root=root, work=work / "probes", timeout_seconds=timeout_seconds))
    # Revalidate source hashes after all executions: a source edit during this
    # acceptance must not publish a stale successful record.
    _stage("final-source-binding-failure", "O0/O2", lambda: _verify_profiles(outputs, root))
    report: dict[str, object] = {
        "schema_version": 1, "status": "pass", "gate": 7, "profile": corpus.PROFILE,
        "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "corpus": {"path": str(corpus_path.relative_to(root)), "sha256": sha256(corpus_path)},
        "profiles": profiles, "profile_source_identity": identity,
        "negative_cases": {corpus.PROFILE: rejections}, "source_policy_probes": probes,
        "frontend_probe": frontend,
        "counts": {"profiles": 2, "positive_cases_per_profile": len(corpus.POSITIVE_CASES),
                   "negative_cases_per_profile": len(corpus.NEGATIVE_CASES),
                   "qemu_boots_total": 2 * (len(corpus.POSITIVE_CASES) + len(corpus.NEGATIVE_CASES) + 2),
                   "resumable_traps_per_profile": sum(2 * case.count for case in corpus.POSITIVE_CASES),
                   "software_denials_per_positive_case": corpus.DENIAL_COUNT,
                   "frontend_rejections": len(rejections), "direct_policy_probes": 20,
                   "conditional_policy_lemmas": 2, "frontend_probe_commands": 1,
                   "behavioral_restore_mutants_detected": 2},
        "limitations": ["Synchronous traps only; no interrupts, scheduler, NMI handling, or userspace isolation.",
                        "Fault-free validated entry/return-tail and fixed aligned RAM are explicit premises.",
                        "Compiled M-mode code remains trusted; checked RAM denials are not protection against arbitrary privileged code.",
                        "Finite source probes and local policy lemmas are not a compiler/hardware correctness proof.",
                        "Pinned QEMU observations do not claim physical-board validation or completion of G1/G2."],
    }
    temporary = work / (RESULT_FILE + ".tmp")
    write_json(temporary, report)
    temporary.replace(work / RESULT_FILE)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=Path("build/foundation/gate7"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--qemu-timeout", type=float, default=30)
    args = parser.parse_args()
    root = repo_root()
    work = args.work_dir if args.work_dir.is_absolute() else root / args.work_dir
    try:
        report = check_gate7(root=root, work=work, clean=args.clean, timeout_seconds=args.timeout, qemu_timeout=args.qemu_timeout)
    except (Core0Error, OSError, ValueError) as error:
        print(f"GATE 7 FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
