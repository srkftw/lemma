#!/usr/bin/env python3
"""Bounded host transport for the ordinary guest Buffer command client."""
from __future__ import annotations

import struct
import hashlib
import json
import math
import os
import select
import signal
import subprocess
import re
import time
from pathlib import Path

from buffer_transport import HEADER_BYTES, MAX_PAYLOAD, decode_uart, input_envelope, validate_input_envelope
from build_kernel import source_inputs
from core0_common import Core0Error, sha256, write_json
from run_kernel import RECORD_BYTES, Session, transport


def _partial_frame_needed(tail: bytes) -> int:
    """Read only the unobserved part of this exact prefix/header/body."""
    if len(tail) < 2 and b"K1".startswith(tail):
        return 2 - len(tail)
    if tail.startswith(b"K1"):
        return 88 - len(tail)
    if len(tail) < 4 and b"LMO1".startswith(tail):
        return 4 - len(tail)
    if tail.startswith(b"LMO1"):
        if len(tail) < 8:
            return 8 - len(tail)
        return 8 + struct.unpack("<BBH", tail[4:8])[2] - len(tail)
    raise Core0Error("unknown partial UART prefix during bounded cleanup")


def _known_complete_prefix(events: list[dict], captured_bytes: int) -> int:
    """Locate the contiguous prefix already parsed by BufferSession.event.

    This cursor avoids reparsing live capture during the stop budget. The
    complete post-kill decode still checks every frame and its actual value.
    """
    if not isinstance(events, list) or type(captured_bytes) is not int or captured_bytes < 0:
        raise Core0Error("parsed UART prefix inventory is malformed")
    prefix = 0
    for event in events:
        if (not isinstance(event, dict) or type(event.get("offset")) is not int
                or type(event.get("bytes")) is not int or event["offset"] != prefix
                or type(event.get("kind")) is not str
                or (event["kind"] == "kernel" and event["bytes"] != RECORD_BYTES)
                or (event["kind"] == "client" and not 8 + HEADER_BYTES <= event["bytes"] <= 8 + MAX_PAYLOAD)
                or event.get("kind") not in {"kernel", "client"}
                or not 0 < event["bytes"] <= captured_bytes - prefix):
            raise Core0Error("parsed UART prefix is not a bounded contiguous frame sequence")
        prefix += event["bytes"]
    return prefix


def _quiesce_uart(process, capture, deadline, record, *, budget=5, max_cycles=64,
                  known_complete_bytes=0):
    """Freeze an owned process group at a fully captured UART boundary.

    Stop notifications are consumed, never child exits. Partial frames are
    completed by the live guest; every byte stays in the original capture.
    The ordinary Session still owns the final kill/wait and complete decode.
    """
    if (type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 5
            or type(max_cycles) is not int or not 0 < max_cycles <= 64
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or type(known_complete_bytes) is not int
            or not 0 <= known_complete_bytes <= len(capture.received)):
        raise Core0Error("UART quiescence bounds must be finite, at most five seconds and 64 cycles")
    started = time.monotonic()
    finish_by = min(deadline, started + budget)
    record.update(status="RUNNING", process_group=process.pid, budget_seconds=budget,
                  max_cycles=max_cycles, captured_bytes_before=len(capture.received), cycles=0, resumes=0,
                  started_monotonic=started, original_deadline=deadline,
                  effective_deadline=finish_by, observed_stops=[])

    def remaining():
        value = finish_by - time.monotonic()
        if value <= 0:
            raise Core0Error("bounded UART cleanup deadline expired")
        return value

    validated = known_complete_bytes
    for cycle in range(1, max_cycles + 1):
        remaining()
        if process.poll() is not None or os.getpgid(process.pid) != process.pid:
            raise Core0Error("UART cleanup lost its live owned process group")
        # A prior stop is not evidence of the signal requested by this cycle.
        # WSTOPPED consumes only a stop notification, never a child exit.
        if os.waitid(os.P_PID, process.pid, os.WSTOPPED | os.WNOHANG) is not None:
            raise Core0Error("UART cleanup found a preexisting stop notification")
        os.killpg(process.pid, signal.SIGSTOP)
        record["cycles"] = cycle
        while True:
            remaining()
            stopped = os.waitid(os.P_PID, process.pid, os.WSTOPPED | os.WNOHANG)
            if stopped is not None:
                if stopped.si_pid != process.pid or stopped.si_code != os.CLD_STOPPED or stopped.si_status != signal.SIGSTOP:
                    raise Core0Error("UART cleanup did not observe its fresh group stop")
                record["observed_stops"].append({"pid": stopped.si_pid, "code": stopped.si_code,
                                                  "signal": stopped.si_status})
                break
            if process.poll() is not None:
                raise Core0Error("guest exited before UART boundary stop")
            select.select([], [], [], min(0.002, remaining()))
        # SIGSTOP stops the entire Linux thread group. Drain both nonblocking
        # pipes only after the fresh stop has been observed and consumed.
        transport._drain_after_exit(process.stdout, capture.received)
        transport._drain_after_exit(process.stderr, capture.stderr)
        if len(capture.received) > 131072 * 200:
            raise Core0Error("UART cleanup exceeds the finite service capture budget")
        events, tail = decode_uart(bytes(capture.received[validated:]), allow_partial=True)
        validated += sum(event["bytes"] for event in events)
        remaining()
        if not tail:
            record.update(status="PASS", final_group_stop_observed=True,
                          stop_code=stopped.si_code, stop_signal=stopped.si_status,
                          frozen_boundary_bytes=len(capture.received), partial_bytes=0,
                          frozen_stderr_bytes=len(capture.stderr), frozen_monotonic=time.monotonic(),
                          frozen_stdout_sha256=hashlib.sha256(capture.received).hexdigest(),
                          frozen_stderr_sha256=hashlib.sha256(capture.stderr).hexdigest())
            return
        needed = _partial_frame_needed(tail)
        if not 0 < needed <= 200:
            raise Core0Error("partial UART frame lacks a bounded exact remainder")
        if cycle == max_cycles:
            raise Core0Error("UART cleanup stop-cycle budget exhausted")
        os.killpg(process.pid, signal.SIGCONT)
        record["resumes"] += 1
        transport._read_exact(process, needed, deadline=finish_by, capture=capture,
                              context="completing an actual UART frame before cleanup")
    raise Core0Error("UART cleanup stop-cycle budget exhausted")


def validate_quiescence(report: dict, rawstdout: bytes, rawstderr: bytes) -> dict:
    """Require the recorded live stop and unchanged complete post-kill bytes."""
    facts = report.get("uart_quiescence")
    if not isinstance(facts, dict):
        raise Core0Error("Buffer report lacks its UART quiescence evidence")
    numeric = ("budget_seconds", "started_monotonic", "original_deadline", "effective_deadline", "frozen_monotonic")
    if any(type(facts.get(key)) not in (int, float) or not math.isfinite(facts[key]) for key in numeric):
        raise Core0Error("Buffer quiescence time bounds are malformed")
    integer = ("process_group", "max_cycles", "captured_bytes_before", "cycles", "resumes",
               "stop_code", "stop_signal", "frozen_boundary_bytes", "frozen_stderr_bytes", "partial_bytes")
    if any(type(facts.get(key)) is not int for key in integer):
        raise Core0Error("Buffer quiescence integer facts are malformed")
    if (report.get("cleanup_errors", []) != []
            or facts.get("status") != "PASS" or facts.get("final_group_stop_observed") is not True
            or facts.get("post_kill_boundary_unchanged") is not True
            or facts.get("post_kill_stderr_unchanged") is not True
            or type(report.get("pid")) is not int or report["pid"] <= 0
            or facts["process_group"] != report["pid"]
            or not 0 < facts["budget_seconds"] <= 5 or not 0 < facts["max_cycles"] <= 64
            or not 0 < facts["cycles"] <= facts["max_cycles"] or facts["resumes"] != facts["cycles"] - 1
            or facts["stop_code"] != os.CLD_STOPPED or facts["stop_signal"] != signal.SIGSTOP
            or facts["partial_bytes"] != 0
            or not 0 <= facts["captured_bytes_before"] <= facts["frozen_boundary_bytes"] <= 131072 * 200
            or facts["frozen_boundary_bytes"] != len(rawstdout) or facts["frozen_stderr_bytes"] != len(rawstderr)
            or facts.get("frozen_stdout_sha256") != hashlib.sha256(rawstdout).hexdigest()
            or facts.get("frozen_stderr_sha256") != hashlib.sha256(rawstderr).hexdigest()
            or facts["effective_deadline"] != min(facts["original_deadline"], facts["started_monotonic"] + facts["budget_seconds"])
            or not facts["started_monotonic"] <= facts["frozen_monotonic"] < facts["effective_deadline"]):
        raise Core0Error("Buffer report lacks its bounded unchanged frozen UART boundary")
    stops = facts.get("observed_stops")
    expected = {"pid": report["pid"], "code": os.CLD_STOPPED, "signal": signal.SIGSTOP}
    if (not isinstance(stops, list) or len(stops) != facts["cycles"]
            or any(not isinstance(stop, dict) or stop != expected
                   or any(type(value) is not int for value in stop.values()) for stop in stops)):
        raise Core0Error("Buffer report lacks fresh consumed stop evidence for every cycle")
    _, tail = decode_uart(rawstdout)
    if tail:
        raise Core0Error("Buffer frozen UART boundary is incomplete")
    return facts


class BufferSession(Session):
    CONFIGURATIONS = ("service-normal", "service-development")
    RUNNER_PATHS = ("scripts/run_buffer_session.py", "scripts/buffer_transport.py",
                    "scripts/buffer-cli.py",
                    "scripts/run_kernel.py", "scripts/run_device_session.py",
                    "scripts/run_monitor_session.py")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.events = []
        self.responses = []
        self.report["wire_format"] = "kernel-buffer-uart-v1"

    def __enter__(self):
        try:
            self.runner_inputs = {name: sha256(self.root / name) for name in self.RUNNER_PATHS}
            self.report["runner_inputs"] = self.runner_inputs
        except (Core0Error, OSError) as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise
        super().__enter__()
        if self.binding.get("configuration") not in self.CONFIGURATIONS:
            error = Core0Error("Buffer transport requires its closed service deployment")
            self.__exit__(type(error), error, error.__traceback__)
            raise error
        return self

    def event(self) -> dict:
        before = len(self.capture.received)
        def read(count):
            return transport._read_exact(self.process, count, deadline=self.deadline,
                                         capture=self.capture, context="reading guest Buffer frame")
        prefix = read(2)
        if prefix == b"K1":
            raw = prefix + read(86)
        elif prefix == b"LM":
            header = prefix + read(6)
            if header[:4] != b"LMO1":
                raise Core0Error("unknown guest output frame")
            category, reserved, length = struct.unpack("<BBH", header[4:])
            if category != 1 or reserved or not 64 <= length <= 192:
                raise Core0Error("malformed guest output envelope")
            raw = header + read(length)
        else:
            raise Core0Error("unknown guest UART prefix")
        parsed, tail = decode_uart(raw)
        if len(parsed) != 1 or tail:
            raise Core0Error("guest frame parser did not consume one exact frame")
        event = {**parsed[0], "offset": before}
        self.events.append(event)
        if event["kind"] == "kernel":
            self.records.append(event["value"])
        else:
            self.responses.append(event["value"])
        return event

    def record(self):
        event = self.event()
        if event["kind"] != "kernel":
            raise Core0Error("client output requires the mixed event consumer")
        return tuple(event["value"])

    def send(self, payload: bytes, *, diagnostic: bool = False):
        transport._write_all(self.process, input_envelope(payload, diagnostic=diagnostic),
                             deadline=self.deadline, capture=self.capture,
                             context="sending framed guest command bytes")

    def send_envelope(self, payload: bytes):
        validate_input_envelope(payload)
        transport._write_all(self.process, payload, deadline=self.deadline,
                             capture=self.capture, context="sending guest input envelope")

    def __exit__(self, exc_type, exc, traceback):
        quiescence_failure = None
        frozen = None
        try:
            if self.process is not None and self.process.poll() is None:
                quiescence = self.report.setdefault("uart_quiescence", {})
                parsed_prefix = _known_complete_prefix(self.events, len(self.capture.received))
                _quiesce_uart(self.process, self.capture, self.deadline, quiescence,
                              known_complete_bytes=parsed_prefix)
                frozen = (bytes(self.capture.received), bytes(self.capture.stderr))
        except BaseException as error:
            quiescence_failure = error
            self.success = False
            self.report.setdefault("uart_quiescence", {}).update(status="FAIL", error=str(error), error_type=type(error).__name__)
        effective = exc if exc is not None else quiescence_failure
        # All paths, including malformed frames and stop/deadline failure, pass
        # through the existing owner of process-group kill and child reaping.
        base_failure = None
        try:
            super().__exit__(exc_type if exc is not None else type(effective) if effective is not None else None,
                             effective, traceback if exc is not None else effective.__traceback__ if effective is not None else None)
        except BaseException as error:
            base_failure = error
            self.success = False
            self.report["status"] = "FAIL"
            self.report.setdefault("cleanup_errors", []).append({"stage": "base-session-cleanup", "error": str(error),
                                                                 "error_type": type(error).__name__})
            if effective is not None:
                self.report.update(error=str(effective), failure_category="observation-failure")
            else:
                self.report.update(error=str(error), failure_category="base-session-cleanup")
            # A base persistence/close failure can occur after its kill/wait;
            # an earlier failure must still stop the same owned live child.
            if self.process is not None:
                try:
                    if self.process.poll() is None:
                        transport._kill_and_reap(self.process, self.capture)
                except BaseException as cleanup_error:
                    self.report["cleanup_errors"].append({"stage": "base-cleanup-recovery", "error": str(cleanup_error),
                                                         "error_type": type(cleanup_error).__name__})
                finally:
                    try:
                        transport._close_process_streams(self.process)
                    except BaseException as close_error:
                        self.report["cleanup_errors"].append({"stage": "base-stream-close", "error": str(close_error),
                                                             "error_type": type(close_error).__name__})
                self.report.update(pid=self.capture.pid, returncode=self.capture.returncode,
                                   argv=list(self.capture.argv))
            # Retain the actual bytes even if the base failed before writing
            # its report. This is failure evidence, never a substitute PASS.
            try:
                for name, raw in (("sent.bin", self.capture.sent), ("received.bin", self.capture.received),
                                  ("stderr.bin", self.capture.stderr)):
                    (self.output_dir / name).write_bytes(raw)
                self.report["raw_artifacts"] = {name: sha256(self.output_dir / name)
                                                for name in ("sent.bin", "received.bin", "stderr.bin")}
            except BaseException as persistence_error:
                self.report["cleanup_errors"].append({"stage": "base-evidence-recovery", "error": str(persistence_error),
                                                     "error_type": type(persistence_error).__name__})
        if quiescence_failure is not None:
            self.report["status"] = "FAIL"
            self.report.setdefault("cleanup_errors", []).append({"stage": "uart-quiescence", "error": str(quiescence_failure),
                                                                 "error_type": type(quiescence_failure).__name__})
            if exc is None:
                self.report["failure_category"] = "uart-quiescence-failure"
        failure = None
        try:
            quiescence = self.report.get("uart_quiescence")
            if isinstance(quiescence, dict) and quiescence.get("status") == "PASS":
                if frozen is None or bytes(self.capture.received) != frozen[0]:
                    raise Core0Error("UART bytes changed after the observed frozen boundary")
                if bytes(self.capture.stderr) != frozen[1]:
                    raise Core0Error("UART stderr changed after the observed frozen boundary")
                quiescence["post_kill_boundary_unchanged"] = True
                quiescence["post_kill_stderr_unchanged"] = True
                validate_quiescence(self.report, bytes(self.capture.received), bytes(self.capture.stderr))
            all_events, tail = decode_uart(bytes(self.capture.received))
            if tail or all_events[:len(self.events)] != self.events:
                raise Core0Error("complete retained UART differs from observed frames")
            self.report.update(wire_events=all_events,
                               records=[event["value"] for event in all_events if event["kind"] == "kernel"],
                               responses=[event["value"] for event in all_events if event["kind"] == "client"],
                               observed_event_count=len(self.events), complete_raw_coverage=True)
            if self.report["status"] == "PASS":
                validate_quiescence(self.report, bytes(self.capture.received), bytes(self.capture.stderr))
                cleanup = self.report.get("cleanup", {})
                expected = {"explicit_host_stop": True, "process_group_killed": True,
                            "target_exited_before_cleanup": False, "process_reaped": True}
                if (self.report.get("returncode") != -9
                        or self.report.get("guest_live_before_cleanup") is not True
                        or not isinstance(cleanup, dict)
                        or any(cleanup.get(key) is not value for key, value in expected.items())
                        or type(self.report.get("pid")) is not int
                        or self.report["pid"] <= 0
                        or Path("/proc", str(self.report["pid"])).exists()):
                    raise Core0Error("Buffer observation lacks actual live kill/reap cleanup")
                self.validate_stderr()
                after_sources = source_inputs(self.root)
                after_runners = {name: sha256(self.root / name) for name in self.RUNNER_PATHS}
                self.report.update(source_inputs_after=after_sources, runner_inputs_after=after_runners,
                                   image_sha256_after=sha256(self.image),
                                   audit_sha256_after=sha256(self.image.parent / "audit.json"),
                                   provenance_sha256_after=sha256(self.image.parent / "provenance.json"))
                if (self.report["image_sha256_after"] != self.digest or after_sources != self.sources
                        or self.report["audit_sha256_after"] != self.report["audit_sha256"]
                        or self.report["provenance_sha256_after"] != self.report["provenance_sha256"]):
                    raise Core0Error("Buffer image/source changed during cleanup")
                if after_runners != self.runner_inputs:
                    raise Core0Error("Buffer observation runner changed during execution")
        except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
            failure = error
            self.report["status"] = "FAIL"
            self.report.setdefault("cleanup_errors", []).append({"stage": "post-cleanup-buffer-evidence", "error": str(error),
                                                                 "error_type": type(error).__name__})
            if exc is None and quiescence_failure is None and base_failure is None:
                self.report.update(error=str(error), failure_category="post-cleanup-buffer-evidence")
            if "wire_events" not in self.report:
                self.report["complete_raw_coverage"] = False
        temporary = self.output_dir / "result.json.tmp"
        try:
            write_json(temporary, self.report)
            temporary.replace(self.output_dir / "result.json")
        except BaseException:
            if exc is None:
                raise
            # The caller's original exception still propagates. Missing or
            # stale persisted evidence cannot pass the independent validator.
            return False
        if base_failure is not None and exc is None:
            raise effective if effective is not None else base_failure
        if failure is not None and exc is None:
            raise failure
        if quiescence_failure is not None and exc is None:
            raise quiescence_failure
        return False


class SiliconBufferSession(BufferSession):
    """The same bounded service transport, fed by the prepared RTL hart.

    The adapter supplies raw stdin bytes only. The live core executes the
    unchanged service protocol; existing task, IPC and byte oracles consume
    its actual output. A short success still requires a live guest and the
    inherited observed UART-boundary stop, group kill and complete replay.
    """
    CONFIGURATIONS = ("silicon-service-development",)
    RUNNER_PATHS = (*BufferSession.RUNNER_PATHS, "scripts/silicon_guest.py")
    PROGRESS = re.compile(rb"RTL progress cycles=([0-9]+) pc=0x([0-9a-f]+) privilege=([0-3]) "
                          rb"retired=([0-9]+) ticks=([0-9]+) timer_traps=([0-9]+) UART=([0-9]+) "
                          rb"fb_reads=([0-9]+) fb_writes=([0-9]+) panel_pixels=([0-9]+) panel_completed=([0-9]+)\n")

    def __enter__(self):
        try:
            from silicon_guest import prepared
            from silicon_profile import profile
            self.prepared = prepared("service")
            entry = self.prepared["workloads"]["service"]
            if Path(entry["image"]["path"]).resolve() != self.image:
                raise Core0Error("RTL service image differs from the prepared first-class backend")
            self.binding = json.loads(Path(entry["audit"]["path"]).read_text())
            if self.binding.get("status") != "PASS" or self.binding.get("configuration") not in self.CONFIGURATIONS:
                raise Core0Error("RTL service lacks its exact passing source/ELF audit")
            self.sources = source_inputs(self.root)
            self.runner_inputs = {name: sha256(self.root/name) for name in self.RUNNER_PATHS}
            self.digest = sha256(self.image)
            self.report.update(backend="rtl", profile=self.prepared["profile"],
                image_sha256=self.digest, audit_sha256=sha256(self.image.parent/"audit.json"),
                provenance_sha256=sha256(self.image.parent/"provenance.json"),
                source_inputs=self.sources, runner_inputs=self.runner_inputs,
                rtl_binary=self.prepared["binary"], rtl_build=self.prepared["rtl_build"],
                rom=self.prepared["rom"], rom_audit=self.prepared["rom_audit"],
                dtb_fixture=entry["dtb"], rtl_sources=self.prepared["rtl_sources"])
            argv = (self.prepared["binary"]["path"], "--image", str(self.image),
                "--rom", self.prepared["rom"]["path"], "--load", f"0x{profile()['dtb_base']:x}:"+entry["dtb"]["path"],
                "--uart-output", str(self.output_dir/"rtl-uart.bin"), "--uart-stdin",
                "--input-capture", str(self.output_dir/"input.events"),
                "--trace", str(self.output_dir/"trace.csv"), "--trace-limit", "10000",
                "--cycles", "1000000000", "--deadline", str(min(math.ceil(self.timeout)+5, 3600)))
            self.process = subprocess.Popen(argv, cwd=self.root, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
            self.capture.pid, self.capture.argv = self.process.pid, argv
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                os.set_blocking(stream.fileno(), False)
            self.deadline = time.monotonic()+self.timeout
            return self
        except BaseException as error:
            self.__exit__(type(error), error, error.__traceback__)
            raise

    def validate_stderr(self):
        from silicon_guest import prepared
        current = prepared("service")
        keys = ("profile", "profile_sha256", "binary", "rom", "rom_audit", "rtl_build", "rtl_sources")
        if ({key:current[key] for key in keys} != {key:self.prepared[key] for key in keys}
                or current["workloads"]["service"] != self.prepared["workloads"]["service"]):
            raise Core0Error("RTL service preparation changed through observation/cleanup")
        raw = bytes(self.capture.stderr)
        matches = list(self.PROGRESS.finditer(raw))
        if b"".join(match.group(0) for match in matches) != raw:
            raise Core0Error("RTL service emitted unexpected diagnostics or an incomplete progress line")
        self.report["rtl_progress"] = [{"cycles":int(m[1]), "pc":int(m[2],16),
            "privilege":int(m[3]), "retired":int(m[4]), "ticks":int(m[5]),
            "timer_traps":int(m[6]), "uart_bytes":int(m[7]),
            "fb_reads":int(m[8]), "fb_writes":int(m[9]),
            "panel_pixels":int(m[10]), "panel_completed":int(m[11])} for m in matches]
