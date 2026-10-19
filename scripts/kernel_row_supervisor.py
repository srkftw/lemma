#!/usr/bin/env python3
"""Own one host acceptance row and reap its separate-session descendants.

The caller retains the sole writer of an inherited control pipe. EOF, caller
death, a signal, or the original absolute monotonic deadline cancels the row.
This Linux-only host supervisor supplies no target behavior or test result.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

SCHEMA = "lemma-kernel-row-supervisor/v1"


def process_identity(pid: int) -> dict | None:
    """Keep kernel start ticks so a recycled PID never grants signal authority."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": fields[19], "ppid": int(fields[1]),
                "pgid": int(fields[2]), "state": fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def same_process(left: dict | None, right: dict | None) -> bool:
    return (left is not None and right is not None and left["pid"] == right["pid"]
            and left["start_ticks"] == right["start_ticks"])


def process_inventory() -> dict[int, dict]:
    result = {}
    for entry in Path("/proc").iterdir():
        if entry.name.isdecimal():
            identity = process_identity(int(entry.name))
            if identity is not None:
                result[identity["pid"]] = identity
    return result


class Supervisor:
    def __init__(self, *, parent_pid: int, control_fd: int, deadline: float,
                 receipt: Path, command: list[str], term_grace: float = 5):
        self.parent_pid, self.control_fd = parent_pid, control_fd
        self.deadline, self.receipt = deadline, receipt
        self.command, self.term_grace = command, term_grace
        self.process = None
        self.child_identity = None
        self.owned = {}
        self.cancelled_signal = None
        self.started = time.monotonic()
        self.report = {"schema": SCHEMA, "status": "FAIL", "child_returncode": None,
                       "reason": "not-started", "cleanup_complete": False,
                       "argv": command, "deadline_monotonic": deadline,
                       "term_grace_seconds": term_grace,
                       "started_at": datetime.now(timezone.utc).isoformat(),
                       "owner": {**(process_identity(os.getpid()) or {}),
                                 "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()},
                       "expected_parent_pid": parent_pid,
                       "supervisor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def cancelled(self) -> str | None:
        if self.cancelled_signal is not None:
            return f"signal-{self.cancelled_signal}"
        if os.getppid() != self.parent_pid:
            return "parent-died"
        try:
            value = os.read(self.control_fd, 1)
        except BlockingIOError:
            value = None
        if value == b"":
            return "control-closed"
        if value is not None:
            return "control-message"
        if time.monotonic() >= self.deadline:
            return "deadline-expired"
        return None

    def inventory(self) -> dict[int, dict]:
        processes = process_inventory()
        # This dedicated process launches exactly one command. As subreaper it
        # owns both ordinary descendants and adopted separate-session orphans.
        parents, found = {os.getpid()}, {}
        while True:
            children = {pid: row for pid, row in processes.items()
                        if row["ppid"] in parents and pid not in found}
            if not children:
                break
            found.update(children)
            parents.update(children)
        for pid, row in found.items():
            previous = self.owned.get(pid)
            if previous is None or not same_process(previous, row):
                # A newly adopted child is owned independently of any older PID
                # entry; signals below always check this exact current identity.
                self.owned[pid] = row
        return {pid: processes[pid] for pid, row in self.owned.items()
                if same_process(row, processes.get(pid))}

    def reap(self, cleanup: dict) -> None:
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            code = os.waitstatus_to_exitcode(status)
            cleanup["reaped"].append({"pid": pid, "returncode": code,
                                      "start_ticks": self.owned.get(pid, {}).get("start_ticks")})
            if self.process is not None and pid == self.process.pid:
                self.process.returncode = code
                self.report["child_returncode"] = code

    def stop(self, *, grace: bool) -> dict:
        cleanup = {"term_groups": [], "term_pids": [], "killed": [], "reaped": [], "remaining": []}
        owned = self.inventory()
        if grace and owned:
            row = process_identity(self.process.pid) if self.process is not None else None
            if same_process(row, self.child_identity) and row["state"] != "Z":
                try:
                    if row["pgid"] == row["pid"]:
                        os.killpg(row["pid"], signal.SIGTERM)
                        cleanup["term_groups"].append(row)
                    else:
                        os.kill(row["pid"], signal.SIGTERM)
                        cleanup["term_pids"].append(row)
                except ProcessLookupError:
                    pass
            else:
                # An exited row cannot unwind contexts. Ask its surviving
                # owned descendants to stop before escalating individually.
                for row in owned.values():
                    current = process_identity(row["pid"])
                    if same_process(row, current) and current["state"] != "Z":
                        try:
                            os.kill(row["pid"], signal.SIGTERM)
                            cleanup["term_pids"].append(row)
                        except ProcessLookupError:
                            pass
            end = time.monotonic() + self.term_grace
            while time.monotonic() < end:
                self.inventory()
                self.reap(cleanup)
                if not self.inventory():
                    return cleanup
                time.sleep(.02)
        # Bounded cleanup remains available after the work deadline expires.
        # Re-snapshot before every signal; no process-name matching is used.
        end, killed = time.monotonic() + 3, set()
        while True:
            for pid, row in self.inventory().items():
                current = process_identity(pid)
                if same_process(row, current) and current["state"] != "Z":
                    try:
                        os.kill(pid, signal.SIGKILL)
                        identity = (pid, row["start_ticks"])
                        if identity not in killed:
                            cleanup["killed"].append(row)
                            killed.add(identity)
                    except ProcessLookupError:
                        pass
            self.reap(cleanup)
            remaining = self.inventory()
            if not remaining:
                return cleanup
            if time.monotonic() >= end:
                cleanup["remaining"] = list(remaining.values())
                return cleanup
            time.sleep(.02)

    def run(self) -> dict:
        previous_signals, previous_subreaper, previous_mask = {}, ctypes.c_int(), None
        libc, registered = ctypes.CDLL(None, use_errno=True), False
        original_parent = os.getppid()
        try:
            if (type(self.parent_pid) is not int or self.parent_pid <= 0 or self.control_fd < 3
                    or not self.command or not math.isfinite(self.deadline)
                    or not math.isfinite(self.term_grace) or not 0 <= self.term_grace <= 10):
                raise ValueError("invalid row-supervisor parent, descriptor, command or time bound")
            if not stat.S_ISFIFO(os.fstat(self.control_fd).st_mode):
                raise ValueError("row-supervisor control descriptor must be a pipe")
            os.set_blocking(self.control_fd, False)
            for number in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
                previous_signals[number] = signal.signal(number, self._cancel)
            if (libc.prctl(37, ctypes.byref(previous_subreaper), 0, 0, 0) != 0
                    or libc.prctl(36, 1, 0, 0, 0) != 0
                    or libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0):
                raise OSError(ctypes.get_errno(), "cannot establish row supervisor ownership")
            registered = True
            # The caller blocks termination while registering this Popen. Its
            # mask survives exec; release it only after our handlers and parent-
            # death ownership exist, so the actual row can unwind on TERM too.
            previous_mask = signal.pthread_sigmask(signal.SIG_UNBLOCK, set(previous_signals))
            if any(row["ppid"] == os.getpid() for row in process_inventory().values()):
                raise ValueError("row supervisor requires a dedicated process without existing children")
            if original_parent != self.parent_pid:
                self.report["reason"] = "parent-died"
            else:
                reason = self.cancelled()
                if reason is not None:
                    self.report["reason"] = reason
                else:
                    # The control reader stays in this supervisor only; callers
                    # must pass no other copy of its sole writer into this tree.
                    self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL,
                                                    start_new_session=True, close_fds=True)
                    self.child_identity = process_identity(self.process.pid)
                    if self.child_identity is None:
                        raise RuntimeError("row child identity unavailable before observed wait status")
                    self.report["child_identity"] = self.child_identity
                    while True:
                        self.inventory()
                        reason = self.cancelled()
                        if reason is not None:
                            self.report["reason"] = reason
                            break
                        observation = os.waitid(os.P_PID, self.process.pid,
                                                os.WEXITED | os.WNOHANG | os.WNOWAIT)
                        if observation is not None:
                            code = (observation.si_status if observation.si_code == os.CLD_EXITED
                                    else -observation.si_status)
                            self.report["child_returncode"] = code
                            survivors = {pid: row for pid, row in self.inventory().items()
                                         if pid != self.process.pid}
                            self.report["descendants_at_child_exit"] = list(survivors.values())
                            self.report["reason"] = ("child-left-descendants" if survivors else
                                                     "child-exited" if code == 0 else "child-failed")
                            break
                        time.sleep(.02)
        except BaseException as error:
            self.report.update(reason="supervisor-error", error=f"{type(error).__name__}: {error}")
        finally:
            # Further termination requests cannot interrupt ownership cleanup.
            for number in previous_signals:
                signal.signal(number, signal.SIG_IGN)
            cleanup = self.stop(grace=self.report["reason"] != "child-exited")
            self.report.update(cleanup=cleanup, cleanup_complete=not cleanup["remaining"],
                               owned_processes=list(self.owned.values()))
            if (self.report["reason"] == "child-exited" and self.report["child_returncode"] == 0
                    and self.report["cleanup_complete"]):
                self.report["status"] = "PASS"
            self.report.update(elapsed_seconds=time.monotonic() - self.started,
                               finished_at=datetime.now(timezone.utc).isoformat())
            self.receipt.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.receipt.with_name(self.receipt.name + ".tmp")
            temporary.write_text(json.dumps(self.report, indent=2, sort_keys=True) + "\n")
            temporary.replace(self.receipt)
            if registered:
                libc.prctl(1, 0, 0, 0, 0)
                libc.prctl(36, previous_subreaper.value, 0, 0, 0)
            if previous_mask is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            for number, handler in previous_signals.items():
                signal.signal(number, handler)
        return self.report

    def _cancel(self, number, _frame):
        if self.cancelled_signal is None:
            self.cancelled_signal = number


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--control-fd", type=int, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--term-grace", type=float, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    report = Supervisor(parent_pid=args.parent_pid, control_fd=args.control_fd,
                        deadline=args.deadline, receipt=args.receipt,
                        command=args.command, term_grace=args.term_grace).run()
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
