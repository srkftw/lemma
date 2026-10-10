#!/usr/bin/env python3
"""Host-only bounded transport for the continuously running maintained kernel.

Success requires fresh, independently checked guest records before explicit
host cleanup. Waiting past a deadline is always failure. A live guest is killed
and reaped after the finite observation protocol, never labelled a normal exit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import time

from audit_kernel import audit
from build_kernel import source_inputs
from core0_common import Core0Error, repo_root, require_tools, sha256, write_json
from build_core0 import prepare_output_directory
import run_device_session as transport
from run_monitor_session import qemu_argv

RECORD_BYTES = 88
RECORD = re.compile(rb"K1(?: [0-9a-f]{16}){5}\n")


def parse_record(raw: bytes) -> tuple[int, ...]:
    if len(raw) != RECORD_BYTES or not RECORD.fullmatch(raw):
        raise Core0Error(f"malformed kernel record: {raw!r}")
    return tuple(int(word, 16) for word in raw.split()[1:])


class Session:
    def __init__(self, *, root: Path, image: Path, output_dir: Path,
                 timeout: float = 30, clean: bool = False, dtb: Path | None = None):
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
            raise Core0Error("kernel observation timeout must be finite and positive")
        self.root, self.image, self.output_dir = root.resolve(), image.resolve(), output_dir.resolve()
        self.dtb = dtb.resolve() if dtb is not None else None
        prepare_output_directory(self.output_dir, self.root, clean=clean)
        self.timeout = timeout
        self.process = None
        self.capture = transport._Capture()
        self.records = []
        self.success = False
        self.started = time.monotonic()
        self.report = {"schema_version": 1, "status": "FAIL", "artifact_category": "kernel-guest-observation",
                       "image": str(self.image), "started_at": datetime.now(timezone.utc).isoformat(),
                       "timeout_seconds": timeout}

    def __enter__(self):
        try:
            self.binding = audit(root=self.root, output_dir=self.image.parent)
            if self.binding.get("status") != "PASS":
                raise Core0Error("kernel image lacks passing fresh artifact audit")
            self.sources = source_inputs(self.root)
            self.digest = sha256(self.image)
            self.report.update(image_sha256=self.digest,
                               audit_sha256=sha256(self.image.parent / "audit.json"),
                               provenance_sha256=sha256(self.image.parent / "provenance.json"),
                               transport_sha256=sha256(Path(__file__)), source_inputs=self.sources)
            if self.dtb is not None:
                self.dtb_digest = sha256(self.dtb)
                self.report.update(dtb_fixture=str(self.dtb), dtb_fixture_sha256=self.dtb_digest)
            tools = require_tools(("qemu-system-riscv64",))
            argv = (tools["qemu-system-riscv64"], *qemu_argv(self.image)[1:])
            if self.dtb is not None:
                argv += ("-dtb", str(self.dtb))
            self.process = subprocess.Popen(argv, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
            self.capture.pid, self.capture.argv = self.process.pid, argv
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
            self.deadline = time.monotonic() + self.timeout
            return self
        except Exception as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def record(self) -> tuple[int, ...]:
        raw = transport._read_exact(self.process, RECORD_BYTES, deadline=self.deadline,
                                    capture=self.capture, context="reading fresh kernel record")
        value = parse_record(raw)
        self.records.append(list(value))
        return value

    def command(self, command: int, a: int = 0, b: int = 0, c: int = 0, d: int = 0) -> tuple[int, ...]:
        words = (command, a, b, c, d)
        if any(type(word) is not int or not 0 <= word < 2 ** 64 for word in words):
            raise Core0Error("command words must be unsigned64 integers")
        transport._write_all(self.process, struct.pack("<5Q", *words), deadline=self.deadline,
                             capture=self.capture, context=f"sending kernel command {command}")
        return self.record()

    def finish(self, observed: dict[str, object]):
        if not self.records or self.process.poll() is not None:
            raise Core0Error("kernel success protocol requires observed records and a live guest")
        if self.capture.stderr:
            raise Core0Error("QEMU produced unexpected stderr")
        if sha256(self.image) != self.digest or source_inputs(self.root) != self.sources:
            raise Core0Error("image/source changed during kernel observation")
        if self.dtb is not None and sha256(self.dtb) != self.dtb_digest:
            raise Core0Error("DTB fixture changed during kernel observation")
        self.report.update(observed=observed, guest_live_before_cleanup=True)
        self.success = True

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self.report.update(error=str(exc), failure_category="observation-failure")
        if self.process is not None:
            was_live = self.process.poll() is None
            transport._kill_and_reap(self.process, self.capture)
            self.report.update(cleanup={"explicit_host_stop": was_live,
                                        "process_group_killed": was_live and self.capture.returncode == -9,
                                        "target_exited_before_cleanup": not was_live,
                                        "process_reaped": self.process.poll() is not None})
            transport._close_process_streams(self.process)
        if self.success and exc is None:
            self.report["status"] = "PASS"
        for name, raw in (("sent.bin", self.capture.sent), ("received.bin", self.capture.received),
                          ("stderr.bin", self.capture.stderr)):
            (self.output_dir / name).write_bytes(raw)
        self.report.update(pid=self.capture.pid, returncode=self.capture.returncode, argv=list(self.capture.argv),
                           records=self.records, elapsed_seconds=round(time.monotonic() - self.started, 6),
                           finished_at=datetime.now(timezone.utc).isoformat(),
                           raw_artifacts={name: sha256(self.output_dir / name)
                                          for name in ("sent.bin", "received.bin", "stderr.bin")})
        temporary = self.output_dir / "result.json.tmp"
        write_json(temporary, self.report)
        temporary.replace(self.output_dir / "result.json")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        with Session(root=repo_root(), image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            record = session.record()
            if record[0] != 0x0a or record[2:] != (0, 512, 0x82000000) or not 0x87e00000 <= record[1] < 0x88000000:
                raise Core0Error(f"bootstrap boot facts differ: {record}")
            session.finish({"protocol": "bootstrap-A-v1", "boot": list(record),
                            "user_execution": "not_run", "allocator_behavior": "not_run"})
        print("PASS: fresh bootstrap facts observed; continuous QEMU explicitly killed and reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
