#!/usr/bin/env python3
"""Readable host terminal for the ordinary guest Buffer command client.

Run in the pinned development environment against an audited service image.
Commands become input bytes; all service work and authority checks run in U/S.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import math
import os
import select
import shlex
import signal
import sys
import time

from buffer_transport import command
from core0_common import Core0Error, repo_root
from run_buffer_session import BufferSession, transport

HELP = """help | version | ps | mem | discover
buffer create <capacity>
buffer write <handle> <offset> <text or hex:00ff>
buffer append <handle> <text or hex:00ff>
buffer read <handle> <offset> <length>
buffer status <handle>
buffer destroy <handle>
quit
Integers accept decimal or 0x prefixes. Binary operations carry at most 128 bytes.
The service is volatile; restarting it loses its contents."""


def number(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as error:
        raise Core0Error("expected a decimal or 0x-prefixed integer") from error
    if not 0 <= result < 2**64:
        raise Core0Error("integer is outside the unsigned 64-bit range")
    return result


def binary(value: str) -> bytes:
    try:
        data = bytes.fromhex(value[4:]) if value.startswith("hex:") else value.encode("utf-8")
    except ValueError as error:
        raise Core0Error("invalid hexadecimal bytes") from error
    if len(data) > 128:
        raise Core0Error("one operation can carry at most 128 bytes")
    return data


def encode(line: str, *, epoch: int) -> tuple[int, bytes]:
    parts = shlex.split(line)
    local = {"help": 7, "version": 7, "ps": 8, "mem": 9, "discover": 10}
    if len(parts) == 1 and parts[0] in local:
        operation = local[parts[0]]
        return operation, command(operation)
    if len(parts) < 2 or parts[0] != "buffer":
        raise Core0Error("unknown command; enter help")
    method = parts[1]
    if method == "create" and len(parts) == 3:
        return 1, command(1, epoch, length=number(parts[2]))
    if method in ("status", "destroy") and len(parts) == 3:
        operation = 5 if method == "status" else 6
        return operation, command(operation, epoch, number(parts[2]))
    if method == "read" and len(parts) == 5:
        return 3, command(3, epoch, number(parts[2]), number(parts[3]), number(parts[4]))
    if method == "write" and len(parts) == 5:
        data = binary(parts[4])
        return 2, command(2, epoch, number(parts[2]), number(parts[3]), len(data), data)
    if method == "append" and len(parts) == 4:
        data = binary(parts[3])
        return 4, command(4, epoch, number(parts[2]), 0, len(data), data)
    raise Core0Error("invalid command arguments; enter help")


@contextmanager
def prompt_deadline(deadline: float):
    """Interrupt a blocking host prompt at the existing guest-session deadline."""
    remaining = deadline - time.monotonic()
    if not math.isfinite(remaining) or remaining <= 0:
        raise TimeoutError("terminal session deadline expired while waiting for input")

    def expired(_signum, _frame):
        # TimeoutError must escape the recoverable malformed-command handler.
        raise TimeoutError("terminal session deadline expired while waiting for input")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, remaining)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def describe(value: dict) -> str:
    if value["transport_status"]:
        return f"transport error {value['transport_status']} (epoch {value['epoch']})"
    if value["application_status"]:
        return f"service error {value['application_status']} (epoch {value['epoch']}, detail {value['detail']})"
    if value["operation"] == 7:
        return f"Buffer protocol version {value['detail']}\n{HELP}"
    if value["operation"] == 8:
        return f"active managed instances: {value['detail']}"
    if value["operation"] == 9:
        return f"free physical frames: {value['detail']}"
    if value["operation"] == 10:
        return f"service epoch {value['epoch']}, caller-local endpoint {value['handle']}"
    text = (f"epoch {value['epoch']} handle {value['handle']} length {value['length']} "
            f"count {value['count']} capacity/detail {value['detail']}")
    if value["data_hex"]:
        data = bytes.fromhex(value["data_hex"])
        text += f"\nhex:{data.hex()}"
        try:
            text += f"\nutf8:{data.decode('utf-8')!r}"
        except UnicodeDecodeError:
            pass
    return text


def wait_for_service(session: BufferSession) -> None:
    """Wait for actual publication after UART/parser setup before first input."""
    while True:
        event = session.event()
        if event["kind"] != "kernel":
            raise Core0Error("guest replied before any terminal request")
        tag, server, endpoint, epoch, client = event["value"]
        if tag == 0x300:
            if server < 512 or client < 512 or server == client or endpoint < 16 or epoch != 1:
                raise Core0Error("ordinary service publication is malformed")
            session.report["terminal_ready"] = {"publication": event["value"],
                                                "wire_index": len(session.events) - 1,
                                                "before_first_input": not session.capture.sent}
            return


class TerminalInput:
    """One raw stdin reader; keep draining the guest while the operator pauses."""
    MAX_LINE_BYTES = 4096
    READ_BYTES = 4096

    def __init__(self, fd: int):
        if type(fd) is not int or fd < 0:
            raise Core0Error("terminal input requires a readable file descriptor")
        self.fd = fd
        self.buffer = bytearray()
        self.eof = False
        self.discarding = False
        self.stderr_open = True

    def _line(self) -> str | None:
        end = self.buffer.find(b"\n")
        if end < 0 and not self.eof:
            if len(self.buffer) > self.MAX_LINE_BYTES:
                self.buffer.clear()
                self.discarding = True
            return None
        if end < 0:
            if not self.buffer and not self.discarding:
                raise EOFError
            end = len(self.buffer)
        raw = bytes(self.buffer[:end])
        del self.buffer[:end + 1]
        oversized = self.discarding or len(raw) > self.MAX_LINE_BYTES
        self.discarding = False
        if oversized:
            raise ValueError(f"one terminal line can carry at most {self.MAX_LINE_BYTES} UTF-8 bytes")
        return raw.decode("utf-8")

    def readline(self, session: BufferSession, *, trace_kernel: bool = False) -> str:
        process = session.process
        if process.stdout is None or process.stderr is None:
            raise Core0Error("terminal guest lacks its stdout/stderr pipes")
        stdout_fd, stderr_fd = process.stdout.fileno(), process.stderr.fileno()
        while True:
            remaining = session.deadline - time.monotonic()
            if not math.isfinite(remaining) or remaining <= 0:
                raise TimeoutError("terminal session deadline expired while waiting for input")
            buffered = b"\n" in self.buffer or self.eof
            readers = [stdout_fd] + ([stderr_fd] if self.stderr_open else [])
            if not self.eof and not buffered:
                readers.append(self.fd)
            ready, _, _ = select.select(readers, [], [], 0 if buffered else min(remaining, 0.1))
            if stderr_fd in ready:
                self.stderr_open = transport._read_stderr(stderr_fd, session.capture)
            if stdout_fd in ready:
                event = session.event()
                if event["kind"] != "kernel":
                    raise Core0Error("guest replied while the terminal had no outstanding request")
                if trace_kernel:
                    print("K1", *(f"{word:016x}" for word in event["value"]))
                # One complete guest frame per turn: ready operator input
                # and already buffered lines must also get serviced, even
                # when the guest continuously produces kernel records.
            if process.poll() is not None:
                raise Core0Error(f"guest exited with {process.returncode} while waiting for terminal input")
            if self.fd in ready:
                chunk = os.read(self.fd, self.READ_BYTES)
                if chunk:
                    self.buffer.extend(chunk)
                    if b"\n" not in self.buffer and len(self.buffer) > self.MAX_LINE_BYTES:
                        self.buffer.clear()
                        self.discarding = True
                else:
                    self.eof = True
            line = self._line()
            if line is not None:
                return line


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--epoch", type=number, default=0,
                        help="explicit service epoch; 0 uses the guest client's current discovery")
    parser.add_argument("--trace-kernel", action="store_true")
    args = parser.parse_args()
    root = repo_root()
    output = args.output_dir or root / "build/kernel" / ("interactive-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
    try:
        with BufferSession(root=root, image=args.image, output_dir=output, timeout=args.timeout) as session:
            if session.binding.get("configuration") != "service-normal":
                raise Core0Error("this ordinary terminal requires service-normal")
            wait_for_service(session)
            terminal = TerminalInput(sys.stdin.fileno())
            requests = 0
            print(HELP)
            while True:
                try:
                    print("lemma> ", end="", flush=True)
                    line = terminal.readline(session, trace_kernel=args.trace_kernel).strip()
                except EOFError:
                    break
                except ValueError as error:
                    print(error, file=sys.stderr)
                    continue
                if line in ("quit", "exit"):
                    break
                if not line:
                    continue
                try:
                    operation, envelope = encode(line, epoch=args.epoch)
                except (Core0Error, ValueError) as error:
                    print(error, file=sys.stderr)
                    continue
                session.send_envelope(envelope)
                while True:
                    event = session.event()
                    if event["kind"] == "kernel":
                        if args.trace_kernel:
                            print("K1", *(f"{word:016x}" for word in event["value"]))
                        continue
                    value = event["value"]
                    if value["operation"] != operation:
                        raise Core0Error("guest command response operation differs")
                    print(describe(value))
                    requests += 1
                    break
            if requests:
                session.finish({"protocol": "buffer-interactive-terminal-v1", "commands": requests,
                                "scope": "operator interaction; not cumulative acceptance"})
        if requests and session.report["status"] != "PASS":
            raise Core0Error(session.report.get("error", "terminal evidence failed"))
        print(f"Transcript: {output / 'result.json'}")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
