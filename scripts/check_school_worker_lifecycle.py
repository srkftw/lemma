#!/usr/bin/env python3
"""Observe bounded host lifecycle intervals for the real RV64 school worker.

No target code is rebuilt or inferred here. Every first result is read from a
fresh QEMU process and checked against the independent signed-integer oracle.
Clock boundaries are host observations, not cycle-accurate guest stage timings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import statistics
import struct
import subprocess
import sys
import time

from check_school_worker import READY, Session, audit, encode, reference
from core0_common import Core0Error, repo_root, sha256, write_json


def evidence(path: Path):
    return {"path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size}


class TimedSession(Session):
    """Reuse the maintained wire reader/termination, bracket actual Popen only."""

    def __init__(self, image: Path, directory: Path):
        self.directory = directory
        self.sent = bytearray()
        self.received = bytearray()
        self.buffer = bytearray()
        self.stderr_file = (directory / "qemu-stderr.log").open("wb")
        self.argv = ["qemu-system-riscv64", "-machine", "virt,acpi=off", "-accel", "tcg", "-cpu", "rv64",
                     "-smp", "1", "-m", "128M", "-bios", "none", "-nodefaults", "-nic", "none",
                     "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot", "-seed", "1",
                     "-kernel", str(image.resolve())]
        self.started = time.monotonic()
        self.creation_start_ns = time.monotonic_ns()
        self.process = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr_file, start_new_session=True)
        self.creation_return_ns = time.monotonic_ns()


def original_production(directory: Path):
    """Retain original recorded command clocks; do not invent total build time."""
    commands_path = directory / "commands.json"
    commands = json.loads(commands_path.read_text())
    invocations = [{"argv": row["argv"], "seconds": row["elapsed_seconds"]}
                   for row in commands if "elapsed_seconds" in row]
    actions = []
    for path in sorted((directory / "action-receipts").glob("*.json")):
        row = json.loads(path.read_text())
        producer = row["producer"]
        recorded = producer["executed"]["commands"]
        if producer.get("result") != "success" or any(command["returncode"] != 0 for command in recorded):
            raise Core0Error("original worker action producer did not succeed")
        actions.append({"receipt": evidence(path), "admissionStatus": row["status"],
                        "action": producer["request"]["action"]["kind"],
                        "producerStartedUnixSeconds": producer["started_at"],
                        "producerCompletedUnixSeconds": producer["completed_at"],
                        "producerCommandSeconds": sum(command["elapsed_seconds"] for command in recorded),
                        "originalRequestedDirectory": producer["provenance"]["requested_cwd"]})
    if not invocations or len(actions) != 4:
        raise Core0Error("missing original worker production timing receipts")
    return {"build": evidence(directory / "build.json"), "commands": evidence(commands_path),
            "actions": evidence(directory / "actions.json"), "recordedInvocationCommands": invocations,
            "recordedInvocationCommandSecondsSum": sum(row["seconds"] for row in invocations),
            "originalActionProducers": actions,
            "scope": "Valid reused production: original command intervals and original action-producer clocks; "
                     "not a fresh build, cold-cache compile measurement, or an end-to-end build wall duration."}


def prepare(image: Path, parameters: Path, request_id: int):
    if image.stat().st_size > 16 * 1024 * 1024 or parameters.stat().st_size > 65536:
        raise Core0Error("lifecycle package exceeds declared observer input bound")
    image_bytes, parameter_bytes = image.read_bytes(), parameters.read_bytes()
    params = json.loads(parameter_bytes)
    if (params.get("schema"), params.get("profile"), params.get("scale"), params.get("dimensions")) != (
            "lemma-linear-parameters/v1", "school-linear-q10-v1", 1024, 2):
        raise Core0Error("unsupported parameter profile")
    quantized = params.get("quantized")
    if (not isinstance(quantized, list) or len(quantized) != 3 or
            any(type(value) is not int for value in quantized) or type(params.get("version")) is not int):
        raise Core0Error("malformed quantized parameter artifact")
    words = [1, 1, params["version"], *quantized, 768, 512, 3]
    expected_status, expected_score = reference(words)
    if expected_status != 0:
        raise Core0Error("parameter artifact rejected by independent acceptance oracle")
    return {"imageSha256": hashlib.sha256(image_bytes).hexdigest(),
            "parametersSha256": hashlib.sha256(parameter_bytes).hexdigest(),
            "imageBytes": len(image_bytes), "parameterBytes": len(parameter_bytes),
            "words": words, "expectedScoreQ20": expected_score,
            "request": encode(request_id, words)}


def trial(image: Path, parameters: Path, directory: Path, request_id: int):
    directory.mkdir()
    clocks = {"preparationStart": time.monotonic_ns()}
    prepared = prepare(image, parameters, request_id)
    clocks["preparationComplete"] = time.monotonic_ns()
    session = TimedSession(image, directory)
    clocks.update({"popenStart": session.creation_start_ns, "popenReturn": session.creation_return_ns})
    try:
        clocks["readyReadStart"] = time.monotonic_ns()
        ready = session.read(len(READY))
        clocks["readyReadComplete"] = time.monotonic_ns()
        if ready != READY:
            raise Core0Error("actual lifecycle READY differs from versioned worker protocol")
        frame = prepared.pop("request")
        session.sent.extend(frame)
        clocks["attachmentWriteStart"] = time.monotonic_ns()
        session.process.stdin.write(frame)
        session.process.stdin.flush()
        clocks["attachmentFlushReturn"] = time.monotonic_ns()
        clocks["firstReplyReadStart"] = time.monotonic_ns()
        response = session.read(48)
        clocks["firstReplyReadComplete"] = time.monotonic_ns()
        if (response[:8] != b"LMS8\x01\x00\x20\x00" or
                struct.unpack_from("<Q", response, 8)[0] != request_id):
            raise Core0Error("malformed or misrouted actual first lifecycle result")
        generation, fence, model, score = struct.unpack_from("<QQQq", response, 16)
        if (generation, fence, model, score) != (*prepared["words"][:3], prepared["expectedScoreQ20"]):
            raise Core0Error("actual first lifecycle result differs from independent integer expectation")
        status_file = Path(f"/proc/{session.process.pid}/status")
        memory = status_file.read_text() if status_file.exists() else ""
        high_water = re.search(r"^VmHWM:\s*(\d+) kB", memory, re.M)
        (directory / "first-request.bin").write_bytes(frame)
        (directory / "first-response.bin").write_bytes(response)
        exit_response = session.request(999999, [], command=2)
        if exit_response["status"] != 0:
            raise Core0Error("actual worker exit command rejected")
        session.close(success=True)
    except BaseException:
        session.close(success=False)
        write_json(directory / "failed-clock-boundaries.json", clocks)
        raise
    durations = {}
    for name, start, end in [
            ("packagePreparation", "preparationStart", "preparationComplete"),
            ("processCreationPopen", "popenStart", "popenReturn"),
            ("readinessObservedAfterPopen", "readyReadStart", "readyReadComplete"),
            ("requestAttachmentWriteFlush", "attachmentWriteStart", "attachmentFlushReturn"),
            ("firstReplyRead", "firstReplyReadStart", "firstReplyReadComplete"),
            ("creationToReady", "popenStart", "readyReadComplete"),
            ("requestStartToFirstResult", "attachmentWriteStart", "firstReplyReadComplete"),
            ("creationToFirstResult", "popenStart", "firstReplyReadComplete"),
            ("preparationToFirstResult", "preparationStart", "firstReplyReadComplete")]:
        durations[name] = (clocks[end] - clocks[start]) / 1e9
    row = {"result": "PASS", "requestId": request_id, "argv": session.argv, "pid": session.process.pid,
           "hostMonotonicNanosecondBoundaries": clocks, "seconds": durations,
           "actual": {"generation": generation, "fence": fence, "model": model, "scoreQ20": score},
           "independentIntegerOracleExact": True,
           "emulatorPeakRssKiBObservedAtResult": int(high_water.group(1)) if high_water else None,
           **prepared, "artifacts": {name: evidence(directory / name) for name in
               ("first-request.bin", "first-response.bin", "requests.bin", "responses.bin", "qemu-stderr.log")}}
    write_json(directory / "trial.json", row)
    return row


def check(directory: Path, image: Path, parameters: Path, runs: int):
    directory.mkdir(parents=True, exist_ok=False)
    root = repo_root()
    source_names = ["scripts/check_school_worker_lifecycle.py", "scripts/check_school_worker.py",
                    "scripts/core0_common.py", "scripts/build_actions.py", "scripts/audit_core0.py",
                    "scripts/audit_device.py"]
    sources = {name: sha256(root / name) for name in source_names}
    # Audit first, and deliberately pre-read both files. No cache is dropped;
    # each trial is cold only with respect to its new process and guest RAM.
    audited = audit(image.parent)
    initial = prepare(image, parameters, 1000)
    production = original_production(image.parent)
    executable = Path(shutil.which("qemu-system-riscv64") or "")
    if not executable.is_file():
        raise Core0Error("QEMU executable unavailable")
    version = subprocess.check_output([str(executable), "--version"], timeout=10).decode()
    rows = [trial(image, parameters, directory / f"run-{number:02d}", 1000 + number)
            for number in range(1, runs + 1)]
    if (sha256(image), sha256(parameters)) != (initial["imageSha256"], initial["parametersSha256"]):
        raise Core0Error("worker lifecycle inputs changed during trials")
    if sources != {name: sha256(root / name) for name in source_names}:
        raise Core0Error("worker lifecycle observer inputs changed during trials")
    if audited["imageSha256"] != initial["imageSha256"]:
        raise Core0Error("audited image differs from observed lifecycle image")
    clock = time.get_clock_info("monotonic")
    summary = {name: {"minimum": min(row["seconds"][name] for row in rows),
                      "median": statistics.median(row["seconds"][name] for row in rows),
                      "maximum": max(row["seconds"][name] for row in rows)} for name in rows[0]["seconds"]}
    report = {"schema": "lemma-school-worker-lifecycle/v1", "result": "PASS", "runs": rows,
              "summarySeconds": summary, "image": evidence(image), "parameters": evidence(parameters),
              "workerAudit": evidence(image.parent / "worker-audit.json"),
              "originalProduction": production, "sourceInputs": sources,
              "workerSourceInputs": audited["sourceInputs"],
              "invocation": [sys.executable, *sys.argv], "cwd": str(root),
              "host": {"platform": platform.platform(), "python": sys.version,
                       "pythonExecutable": evidence(Path(sys.executable).resolve()),
                       "qemuExecutable": evidence(executable.resolve()), "qemuVersion": version,
                       "clock": {"implementation": clock.implementation, "resolutionSeconds": clock.resolution,
                                 "monotonic": clock.monotonic, "adjustable": clock.adjustable}},
              "boundaryDefinitions": {
                  "packagePreparation": "Read/hash existing image and parameter bytes, validate parameter schema, prepare exact runtime request; no compile or school-network download.",
                  "processCreationPopen": "Host monotonic_ns immediately before subprocess.Popen and immediately after it returns; includes Python/OS child creation, not exec-to-main CPU cycles.",
                  "readinessObservedAfterPopen": "Host read start after Popen return through receiving the exact real UART READY bytes; child execution can already overlap Popen.",
                  "requestAttachmentWriteFlush": "Host write of actual 88-byte frame and pipe flush return. Parameters are in this runtime frame; flush is not a guest attachment acknowledgement.",
                  "firstReplyRead": "Host read start through all 48 actual response bytes. Guest inference can overlap the write/flush interval and response bytes may already be buffered.",
                  "firstResult": "First successful exact integer inference response, not first generated token; oracle validation occurs after this clock endpoint."},
              "cacheScope": f"{runs} sequential fresh QEMU processes and fresh 128MiB guest RAM allocations; image/parameter bytes pre-read and audit completed before trials. Host filesystem/page caches and QEMU executable cache are warm or uncontrolled; no cache drop or physical cold boot.",
              "scope": "Finite two-feature synthetic worker on shared host TCG. Host observation boundaries are not exclusive guest stages, CPU-cycle measurements, native RV64 performance, large-model loading or a first-token benchmark."}
    write_json(directory / "lifecycle-evidence.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=5, choices=range(3, 11))
    args = parser.parse_args()
    try:
        report = check(args.work_dir, args.image, args.parameters, args.runs)
    except (Core0Error, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        if args.work_dir.exists():
            write_json(args.work_dir / "lifecycle-failure.json", {"result": "FAIL", "error": str(error)})
        raise SystemExit(str(error)) from error
    print(json.dumps({"result": report["result"], "runs": len(report["runs"]),
                      "summarySeconds": report["summarySeconds"],
                      "receipt": str(args.work_dir / "lifecycle-evidence.json")}))


if __name__ == "__main__":
    main()
