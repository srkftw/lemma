#!/usr/bin/env python3
"""Qualify one isolated append-copy mutation using the ordinary Buffer checker.

This host controller writes no target source. The inner checker must retain an
actual byte-reference FAIL; only the bound final-byte counterexample qualifies
the outer negative. Setup failures, timeouts and early guest exits do not.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import signal
import time

from build_core0 import prepare_output_directory
from build_kernel import source_inputs
from check_kernel import stop_controller_children, validate_session
from check_kernel_buffer import (RUNNERS as POSITIVE_RUNNERS, check as check_positive,
                                 validate_reference_failure, validate_replay)
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json
from run_buffer_session import BufferSession, validate_quiescence

SERVER = "Lemma/Services/Buffer/Server.lean"
RUNNERS = (*POSITIVE_RUNNERS, "scripts/check_kernel_buffer_negative.py")
BEFORE = "  .bind (Protocol.copy (incoming + 128) (page slot + offset) count) fun s _ => if s = 0 then\n"
AFTER = "  .bind (Protocol.copy (incoming + 128) (page slot + offset) (if operation = 4 then if 0 < count then count - 1 else count else count)) fun s _ => if s = 0 then\n"
CLEANUP = {"explicit_host_stop": True, "process_group_killed": True,
           "target_exited_before_cleanup": False, "process_reaped": True}


def append_truncated_source(original: str) -> str:
    """Return exactly the closed append mutation, without changing a file."""
    if original.count(BEFORE) != 1 or AFTER in original:
        raise Core0Error("Server copy does not match the closed append mutation")
    return original.replace(BEFORE, AFTER, 1)


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in RUNNERS}


def source_binding(root: Path, expected_commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise Core0Error("append mutation requires an exact forty-digit committed revision")

    def git(*args):
        result = run_bounded(("git", *args), cwd=root, timeout_seconds=30)
        if result.returncode:
            raise Core0Error("Git append mutation binding command failed")
        return result.stdout

    if git("rev-parse", "HEAD").decode().strip() != expected_commit:
        raise Core0Error("append mutation worktree HEAD differs from the selected committed revision")
    if git("status", "--porcelain=v1", "--untracked-files=all").decode().splitlines() != [" M " + SERVER]:
        raise Core0Error("isolated negative worktree must change only the unstaged Server source")
    original = git("show", expected_commit + ":" + SERVER)
    if (root / SERVER).read_bytes() != append_truncated_source(original.decode()).encode():
        raise Core0Error("Server differs beyond the canonical append count mutation")
    sources = source_inputs(root)
    if not sources or SERVER not in sources:
        raise Core0Error("append mutation lacks the complete bound source inventory")
    # A Git status alone cannot reveal ignored extra Lean inputs or the contents
    # behind a symlink. Bind every actual input to a regular committed blob.
    entries = {}
    for row in git("ls-tree", "-rz", "HEAD").split(b"\0"):
        if row:
            metadata, name = row.split(b"\t", 1)
            entries[name.decode()] = metadata.decode().split()
    for name, digest in sources.items():
        entry = entries.get(name)
        if not entry or entry[:2] not in (["100644", "blob"], ["100755", "blob"]):
            raise Core0Error("negative source inventory contains an uncommitted or nonregular input")
        content = original if name == SERVER else (root / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != entry[2] or digest != sha256(root / name):
            raise Core0Error("negative source inventory differs from the committed control tree")
    baseline = {**sources, SERVER: hashlib.sha256(original).hexdigest()}
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise Core0Error("committed append-control tree identity is malformed")
    return {"commit": expected_commit, "tree": tree, "source_inputs": sources,
            "control_source_inputs": baseline,
            "mutation": {"path": SERVER, "before_sha256": baseline[SERVER], "after_sha256": sources[SERVER],
                         "changes": "append-positive-count-copy-minus-one-only",
                         "unchanged": ["write-operation2", "reported-count", "logical-length", "status", "bounds"]}}


def artifact_binding(image: Path, sources: dict, commit: str, dirty_paths: list,
                     optimization: str) -> dict:
    provenance, audit = (load_json(image.parent / name) for name in ("provenance.json", "audit.json"))
    if (optimization not in {"O0", "O2"}
            or (provenance.get("configuration"), provenance.get("stage"), provenance.get("optimization"))
            != ("service-normal", "supervisor", optimization)
            or provenance.get("source_commit") != commit or provenance.get("dirty_paths") != dirty_paths
            or provenance.get("source_inputs") != sources
            or (audit.get("status"), audit.get("configuration"), audit.get("stage"))
            != ("PASS", "service-normal", "supervisor")
            or audit.get("source_commit") != commit or audit.get("dirty_paths") != dirty_paths
            or audit.get("optimization") != optimization or audit.get("image_sha256") != sha256(image)):
        raise Core0Error("Buffer image lacks exact normal profile, source, revision or optimization binding")
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts or "image.elf" not in artifacts:
        raise Core0Error("Buffer image provenance lacks actual artifact hashes")
    for name, digest in artifacts.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                or sha256(image.parent / name) != digest):
            raise Core0Error("Buffer compiled artifact changed from audited provenance")
    return {"image": str(image), "image_sha256": sha256(image), "audit_sha256": sha256(image.parent / "audit.json"),
            "provenance_sha256": sha256(image.parent / "provenance.json"), "artifacts": artifacts}


def positive_control(path: Path, binding: dict, root: Path, optimization: str) -> dict:
    value = load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("image"), str):
        raise Core0Error("passing Buffer control report lacks its actual image")
    image = Path(value["image"])
    if not image.is_absolute():
        raise Core0Error("passing Buffer control image path must be absolute")
    value = validate_session(path, image)
    artifacts = artifact_binding(image, binding["control_source_inputs"], binding["commit"], [], optimization)
    expected = {name: sha256(root / name) for name in POSITIVE_RUNNERS}
    transport = {name: expected[name] for name in BufferSession.RUNNER_PATHS}
    if (value.get("source_inputs") != binding["control_source_inputs"]
            or value.get("source_inputs_after") != binding["control_source_inputs"]
            or value.get("service_runner_inputs") != expected or value.get("service_runner_inputs_after") != expected
            or value.get("runner_inputs") != transport or value.get("runner_inputs_after") != transport
            or value.get("acceptance_checker_sha256") != expected["scripts/check_kernel_buffer.py"]):
        raise Core0Error("positive Buffer control uses different source or observation logic")
    replayed = validate_replay(root, image, value, path.parent)
    if (replayed != value.get("observed") or replayed.get("complete_semantic_replay") is not True
            or replayed.get("protocol") != "buffer-service-J-v1"):
        raise Core0Error("positive Buffer control lacks the same complete semantic replay")
    return {"path": str(path), "sha256": sha256(path), **artifacts,
            "selected_committed_control": binding["commit"], "reported_source_commit": binding["commit"],
            "reported_dirty_paths": [], "source_inputs": value["source_inputs"], "runner_inputs": expected}


def validate_failed_session(path: Path, image: Path, *, binding: dict, runners: dict,
                            optimization: str, root: Path) -> dict:
    retained_hash = sha256(path)
    value = load_json(path)
    if (not isinstance(value, dict) or value.get("status") != "FAIL"
            or value.get("image") != str(image)
            or value.get("failure_category") != "observation-failure"
            or value.get("service_failure_category") != "buffer-byte-reference"
            or not isinstance(value.get("error"), str)
            or not value["error"].startswith("independent Buffer reference mismatch: ")
            or value.get("service_error") != value["error"] or value.get("service_error_type") != "Core0Error"
            or value.get("timeout_seconds") != 60 or value.get("guest_live_before_cleanup") is not True):
        raise Core0Error("inner Buffer checker did not fail on the actual live byte-reference counterexample")
    if (value.get("cleanup") != CLEANUP or any(type(flag) is not bool for flag in value["cleanup"].values())
            or value.get("returncode") != -9 or type(value.get("pid")) is not int or value["pid"] <= 0
            or Path("/proc", str(value["pid"])).exists()):
        raise Core0Error("negative guest lacks actual live explicit kill, reap and absent PID")
    artifacts = artifact_binding(image, binding["source_inputs"], binding["commit"], [" M " + SERVER], optimization)
    expected = {name: runners[name] for name in POSITIVE_RUNNERS}
    transport = {name: expected[name] for name in BufferSession.RUNNER_PATHS}
    if (any(value.get(name) != artifacts[name] for name in ("image_sha256", "audit_sha256", "provenance_sha256"))
            or value.get("source_inputs") != binding["source_inputs"]
            or value.get("runner_inputs") != transport or value.get("service_runner_inputs") != expected
            or value.get("negative_runner_inputs") != runners
            or value.get("acceptance_checker_sha256") != expected["scripts/check_kernel_buffer.py"]):
        raise Core0Error("failed Buffer guest image/source/runner binding differs")
    raw = value.get("raw_artifacts")
    if not isinstance(raw, dict) or set(raw) != {"received.bin", "sent.bin", "stderr.bin"}:
        raise Core0Error("negative Buffer raw evidence inventory is missing or unexpected")
    for name, digest in raw.items():
        if sha256(path.parent / name) != digest:
            raise Core0Error("negative Buffer raw bytes changed after failure")
    if (path.parent / "stderr.bin").read_bytes():
        raise Core0Error("negative Buffer guest retained unexpected QEMU stderr")
    if value.get("cleanup_errors"):
        raise Core0Error("negative Buffer guest retained a cleanup failure")
    validate_quiescence(value, (path.parent / "received.bin").read_bytes(),
                        (path.parent / "stderr.bin").read_bytes())
    facts = validate_reference_failure(root, image, value, path.parent)
    expected_bytes, actual_bytes = (bytes.fromhex(facts[name]) for name in ("expected_data_hex", "actual_data_hex"))
    if (facts.get("protocol") != "buffer-service-J-byte-failure-v1"
            or facts.get("complete_semantic_replay") is not True
            or facts.get("failed_rpc") != value.get("failed_rpc")
            or type(facts.get("replayed_wire_events")) is not int
            or facts["replayed_wire_events"] != len(value.get("wire_events", []))
            or len(expected_bytes) != 128 or expected_bytes[-1] != 255
            or actual_bytes != expected_bytes[:-1] + b"\0"):
        raise Core0Error("negative Buffer replay lacks the exact distinguishing append byte divergence")
    if sha256(path) != retained_hash:
        raise Core0Error("inner failed Buffer report changed during validation")
    return {"path": str(path), "sha256": retained_hash, "status": "FAIL", "error": value["error"],
            "pid": value["pid"], "returncode": value["returncode"], "cleanup": value["cleanup"],
            "raw_artifacts": raw, "artifacts": artifacts, "observed": facts}


def _publish(output_dir: Path, report: dict) -> None:
    temporary = output_dir / "result.json.tmp"
    write_json(temporary, report)
    temporary.replace(output_dir / "result.json")


def run(*, root: Path, image: Path, output_dir: Path, control: Path, expected_commit: str,
        timeout: float = 60, clean: bool = False) -> dict:
    root, image, output_dir, control = (path.resolve() for path in (root, image, output_dir, control))
    try:
        relative = output_dir.relative_to(root / "build/kernel")
    except ValueError as error:
        raise Core0Error("Buffer negative output must be a build/kernel subdirectory") from error
    if not relative.parts or isinstance(timeout, bool) or not math.isfinite(timeout) or timeout != 60:
        raise Core0Error("Buffer negative requires a dedicated output and exactly sixty-second finite observation")
    # Cleaning evidence must not delete any selected input/control artifact.
    if any(path == output_dir or output_dir in path.parents for path in (image, control)):
        raise Core0Error("Buffer negative output overlaps its image or positive control")
    control_read_error = None
    if control.is_file():
        try:
            control_report = load_json(control)
        except (Core0Error, OSError, ValueError, TypeError) as error:
            control_read_error, control_report = str(error), None
        if isinstance(control_report, dict) and isinstance(control_report.get("image"), str):
            control_image = Path(control_report["image"]).resolve()
            if control_image == output_dir or output_dir in control_image.parents:
                raise Core0Error("Buffer negative output overlaps its positive control image")
    prepare_output_directory(output_dir, root, clean=clean)
    begin = time.monotonic()
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "K-buffer-append-negative",
              "protocol": "append-truncated-K-v1", "image": str(image), "timeout_seconds": timeout,
              "started_at": datetime.now(timezone.utc).isoformat(), "inner_positive_checker_status": "not_run"}
    _publish(output_dir, report)
    try:
        if control_read_error is not None:
            raise Core0Error("positive Buffer control is unreadable: " + control_read_error)
        binding, runners = source_binding(root, expected_commit), runner_inputs(root)
        optimization = load_json(image.parent / "provenance.json").get("optimization")
        artifact_binding(image, binding["source_inputs"], expected_commit, [" M " + SERVER], optimization)
        control_binding = positive_control(control, binding, root, optimization)
        report.update(source=binding, runner_inputs=runners, positive_control=control_binding)
        try:
            with BufferSession(root=root, image=image, output_dir=output_dir / "inner-session", timeout=timeout) as session:
                session.report.update(service_runner_inputs={name: runners[name] for name in POSITIVE_RUNNERS},
                                      negative_runner_inputs=runners,
                                      acceptance_checker_sha256=runners["scripts/check_kernel_buffer.py"])
                try:
                    check_positive(session)
                except Core0Error:
                    session.report["guest_live_before_cleanup"] = session.process.poll() is None
                    raise
                raise Core0Error("append mutant unexpectedly completed the ordinary positive Buffer checker")
        except Core0Error:
            pass  # Only the retained exact failure below may qualify.
        failed = validate_failed_session(output_dir / "inner-session/result.json", image, binding=binding,
                                         runners=runners, optimization=optimization, root=root)
        if (source_binding(root, expected_commit) != binding or runner_inputs(root) != runners
                or positive_control(control, binding, root, optimization) != control_binding):
            raise Core0Error("negative source, runners or clean positive control changed during observation")
        # Revalidate raw/artifact/report hashes after the final control replay.
        if validate_failed_session(output_dir / "inner-session/result.json", image, binding=binding,
                                   runners=runners, optimization=optimization, root=root) != failed:
            raise Core0Error("retained negative evidence changed through final validation")
        report.update(status="PASS", inner_positive_checker_status="FAIL", inner_session=failed,
                      source_unchanged_after=True, runners_unchanged_after=True,
                      observed_expected_failure="successful-append128-read128-final-FF-to-00")
    except (Core0Error, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        report.update(error=str(error), failure_category="buffer-negative-evidence-failure")
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=time.monotonic() - begin)
        _publish(output_dir, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--positive-control", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    previous = {}

    def interrupted(signum, _frame):
        stop_controller_children(defer_qemu=True)
        raise Core0Error(f"Buffer negative controller interrupted by signal {signum}")

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupted)
        report = run(root=repo_root(), image=args.image, output_dir=args.output_dir, control=args.positive_control,
                     expected_commit=args.expected_commit, timeout=args.timeout, clean=args.clean)
        if report["status"] != "PASS":
            raise Core0Error(report.get("error", "Buffer negative failed"))
        print("PASS: canonical append mutation reproduced exact byte divergence; inner FAIL retained and guest reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1
    finally:
        stop_controller_children()
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
