#!/usr/bin/env python3
"""Bounded actual S-mode bridge observations and isolated M-origin rejection.

The positive case observes the maintained kernel through Session. The negative
case has its own terminating, trace-bound QEMU protocol; it cannot relabel a
timeout or an unexpected live guest as successful rejection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import subprocess
import time

from audit_kernel import audit
from build_core0 import prepare_output_directory
from build_kernel import source_inputs
from core0_common import Core0Error, repo_root, require_tools, sha256, write_json
from run_kernel import Session
from run_monitor_session import qemu_argv
import run_device_session as transport

S_WITNESS = 0x534543414c4c0001
PMP_CONFIGURATION = 0x1b1b1f1818
MEDELEG = 0xb1ff
MIDELEG = 0x1446
TRACE_EVENT = re.compile(
    r"riscv_cpu_do_interrupt: hart:([0-9]+), async:([01]), cause:((?:0x)?[0-9a-f]{1,16}), "
    r"epc:((?:0x)?[0-9a-f]{1,16}), tval:((?:0x)?[0-9a-f]{1,16}), desc=([a-z_]+)"
)


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in (
        "scripts/check_kernel_supervisor.py", "scripts/run_kernel.py",
        "scripts/run_device_session.py", "scripts/run_monitor_session.py")}


def validate_positive_records(records: list[tuple[int, ...]]) -> dict:
    if len(records) != 4 or any(len(row) != 5 or any(type(word) is not int or not 0 <= word < 2**64 for word in row) for row in records):
        raise Core0Error("supervisor record corpus must contain exactly four unsigned64 records")
    boot, call, irq, invalid = records
    if boot[0] != 0xa or boot[2:] != (1, 512, 0x82000000) or not 0x87e00000 <= boot[1] < 0x88000000:
        raise Core0Error(f"supervisor boot facts differ: {boot}")
    if call != (0xc0, S_WITNESS, PMP_CONFIGURATION, MEDELEG, MIDELEG):
        raise Core0Error(f"supervisor firmware witness/CSR readbacks differ: {call}")
    if irq[0] != 0xc1 or irq[1] == 2**64 - 1 or irq[2] != irq[1] + 1 or irq[3:] != (1, 0):
        raise Core0Error(f"actual timer forwarding/acknowledgement differs: {irq}")
    if invalid[:4] != (0xc2, 17, 22, 22) or invalid[4] == 0:
        raise Core0Error(f"invalid call/deadline rejection or valid rearm differs: {invalid}")
    return {"protocol": "supervisor-C-v1", "boot": list(boot), "firmware_witness_and_csrs": list(call),
            "timer_notification_and_acknowledgement": list(irq), "call_rejections_and_valid_rearm": list(invalid),
            "actual_irq_delta": 1, "supervisor_pending_before_ack": 1, "supervisor_pending_after_ack": 0,
            "valid_rearm_deadline": invalid[4], "user_execution": "not_run", "scheduling": "not_run"}


def check(session: Session) -> dict:
    if (session.binding.get("configuration"), session.binding.get("stage"), session.binding.get("startup_case")) != ("normal", "supervisor", "normal"):
        raise Core0Error("supervisor acceptance requires the exact normal supervisor image")
    return validate_positive_records([session.record() for _ in range(4)])


def validate_machine_origin_trace(text: str, *, expected_pc: int) -> dict:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1 or not (event := TRACE_EVENT.fullmatch(lines[0])):
        raise Core0Error("machine-origin trace must contain exactly one actual trap event")
    hart, asynchronous, cause, pc, value = (int(event[index], 10 if index <= 2 else 16) for index in range(1, 6))
    if (hart, asynchronous, cause, pc, value, event[6]) != (0, 0, 11, expected_pc, 0, "machine_ecall"):
        raise Core0Error("machine-origin trap cause/origin/PC/value differs from audited probe")
    return {"hart": hart, "asynchronous": asynchronous, "cause": cause, "epc": pc, "tval": value, "description": event[6]}


def run_machine_origin(*, root: Path, image: Path, output_dir: Path, timeout: float = 20, clean: bool = False) -> dict:
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise Core0Error("machine-origin timeout must be finite and positive")
    root, image, output_dir = root.resolve(), image.resolve(), output_dir.resolve()
    prepare_output_directory(output_dir, root, clean=clean)
    started = time.monotonic()
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "development-machine-origin-rejection",
              "protocol": "machine-origin-C-v1", "image": str(image), "timeout_seconds": timeout,
              "started_at": datetime.now(timezone.utc).isoformat()}
    process = None
    capture = transport._Capture()
    trace = output_dir / "qemu-interrupt-trace.txt"
    try:
        binding = audit(root=root, output_dir=image.parent)
        if (binding.get("status"), binding.get("configuration"), binding.get("stage"), binding.get("startup_case")) != ("PASS", "machine-origin-development", "bootstrap-m", "machine-origin-probe"):
            raise Core0Error("machine-origin rejection requires its exact audited development image")
        pcs = binding.get("elf", {}).get("boot", {}).get("startup", {}).get("start_ecall_pcs")
        if not isinstance(pcs, list) or len(pcs) != 1 or type(pcs[0]) is not int:
            raise Core0Error("audited machine-origin ECALL PC is missing")
        sources, runners, digest = source_inputs(root), runner_inputs(root), sha256(image)
        report.update(image_sha256=digest, audit_sha256=sha256(image.parent / "audit.json"),
                      provenance_sha256=sha256(image.parent / "provenance.json"), source_inputs=sources,
                      runner_inputs=runners, audited_ecall_pc=pcs[0])
        tools = require_tools(("qemu-system-riscv64",))
        argv = (tools["qemu-system-riscv64"], *qemu_argv(image)[1:], "-d", "int", "-D", str(trace))
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
        capture.pid, capture.argv = process.pid, argv
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        capture.returncode = transport._wait_and_collect(process, deadline=time.monotonic() + timeout,
                                                        capture=capture, read_stdout=True)
        if capture.returncode != 48 or capture.received or capture.stderr:
            raise Core0Error("machine-origin rejection requires fatal exit 48 and empty stdout/stderr")
        event = validate_machine_origin_trace(trace.read_text(), expected_pc=pcs[0])
        if sha256(image) != digest or source_inputs(root) != sources or runner_inputs(root) != runners:
            raise Core0Error("image/source/runner changed during machine-origin observation")
        report.update(status="PASS", actual_trap=event, observed_fatal_exit=48, target_exited_before_cleanup=True)
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        report.update(error=str(error), failure_category="machine-origin-observation-failure")
    finally:
        if process is not None:
            was_live = process.poll() is None
            transport._kill_and_reap(process, capture)
            report["cleanup"] = {"explicit_host_stop": was_live, "process_reaped": process.poll() is not None}
            transport._close_process_streams(process)
        for name, raw in (("sent.bin", capture.sent), ("received.bin", capture.received), ("stderr.bin", capture.stderr)):
            (output_dir / name).write_bytes(raw)
        report.update(pid=capture.pid, returncode=capture.returncode, argv=list(capture.argv),
                      elapsed_seconds=round(time.monotonic() - started, 6), finished_at=datetime.now(timezone.utc).isoformat(),
                      raw_artifacts={name: sha256(output_dir / name) for name in ("sent.bin", "received.bin", "stderr.bin")})
        report["trace_observed"] = trace.is_file()
        if trace.is_file():
            report["raw_artifacts"][trace.name] = sha256(trace)
        write_json(output_dir / "result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case", choices=("supervisor", "machine-origin"), default="supervisor")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root()
        if args.case == "machine-origin":
            report = run_machine_origin(root=root, image=args.image, output_dir=args.output_dir, timeout=args.timeout, clean=args.clean)
            if report["status"] != "PASS":
                raise Core0Error(report["error"])
        else:
            runners = runner_inputs(root)
            with Session(root=root, image=args.image, output_dir=args.output_dir, timeout=args.timeout, clean=args.clean) as session:
                session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
                observed = check(session)
                if runner_inputs(root) != runners:
                    raise Core0Error("supervisor acceptance runner changed during observation")
                session.finish(observed)
        print(f"PASS: actual {args.case} Gate C observation; QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
