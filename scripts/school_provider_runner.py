#!/usr/bin/env python3
"""Byte-transport declarations for the bounded owner-local QEMU adapter.

The Lean registry admits resources and leases. A reported ready-to-launch
adapter is distinct from the actual UART READY bytes retained by this helper.
"""
from __future__ import annotations

from pathlib import Path

from check_school_worker import READY
from core0_common import Core0Error, sha256, write_json


def configure(command, image: Path, artifacts: list[str], workers: list[str], *, now: int):
    """Declare the real configured -smp1/-m128M adapter envelope, no scheduler."""
    node = command("node-config", node="local", version=1, provider="local", profile="core0-v0.5",
                   capabilities=["school-linear-worker/1"], maxWorkers=4,
                   memoryBytes=536870912, storageBytes=268435456, now=now)
    generation = command("status", now=now)["generation"]
    rows = {}
    for worker in workers:
        config = command("worker-config", worker=worker, node="local", version=1, controller="owner",
                         profile="core0-v0.5", imageSha256=sha256(image), cpuSlots=1,
                         memoryBytes=134217728, inputBytes=88, outputBytes=48, scratchBytes=16384,
                         capabilities=["school-linear-worker/1"], now=now)
        health = command("worker-health", worker=worker, configVersion=1, generation=generation,
                         status="ready", artifacts=artifacts,
                         reason="Authorized local adapter ready-to-launch report; this is not an observed live VM READY or remote attestation.",
                         now=now)
        rows[worker] = {"config": config, "reportedHealth": health}
    return {"node": node, "workers": rows, "generation": generation,
            "scope": "Owner-reported one-host QEMU adapter; 1 vCPU/128MiB per guest, 4 concurrent slots, "
                     "512MiB aggregate declared VM RAM, 256MiB conservative concurrent CAS-closure reservation. "
                     "No cgroup/disk quota, remote membership, physical availability or live-VM attestation claim."}


def report(command, worker: str, generation: int, artifacts: list[str], *, status: str, reason: str, now: int):
    return command("worker-health", worker=worker, configVersion=1, generation=generation,
                   status=status, reason=reason, artifacts=artifacts, now=now)


def observe_ready(session, directory: Path, image: Path, worker: str):
    """Retain only bytes read from a real Session after its READY was checked."""
    received = bytes(session.received)
    if not received.startswith(READY):
        raise Core0Error("provider observation has no actual versioned UART READY bytes")
    argv = session.argv
    if argv[argv.index("-smp")+1] != "1" or argv[argv.index("-m")+1] != "128M":
        raise Core0Error("actual QEMU command differs from declared provider CPU/RAM envelope")
    raw = directory / "provider-ready.bin"
    raw.write_bytes(received[:len(READY)])
    receipt = directory / "provider-ready.json"
    write_json(receipt, {"schema": "lemma-school-provider-ready-observation/1", "worker": worker,
                        "origin": "actual-rv64-uart-observation", "pid": session.process.pid,
                        "command": argv, "imageSha256": sha256(image), "readyBytes": len(READY),
                        "readySha256": sha256(raw), "observerSha256": sha256(Path(__file__)),
                        "scope": "Observed exact UART READY at this process boundary; adapter health and future capacity remain authorized reports."})
    return [raw, receipt]


def verify_recorded_ready(directory: Path):
    raw = directory / "responses.bin"
    if not raw.read_bytes().startswith(READY):
        raise Core0Error("retained provider execution stream lacks actual UART READY")
    return {"path": str(raw), "sha256": sha256(raw), "observedReadyBytes": len(READY),
            "scope": "Actual bytes from completed process; no assertion that that process remains alive."}
