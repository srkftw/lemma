#!/usr/bin/env python3
"""Bounded Linux supervisor retaining a protected workspace's flock lease.

The worker owns one child process group, becomes its descendants' subreaper,
and terminates/reaps that work on deadline, cancellation or parent death. It
never searches for or signals unrelated jobs. Tool stdout/stderr pass through;
the result protocol uses a separate inherited pipe.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

_cancelled = 0


def _cancel(number, _frame):
    global _cancelled
    _cancelled = number


def _identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (pid, fields[19])
    except (OSError, IndexError):
        return None


def _descendants():
    """Snapshot only this worker's descendants, including adopted children."""
    parents, identities = {}, {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit(): continue
        try:
            fields = (path/"stat").read_text().rsplit(")", 1)[1].split()
            pid = int(path.name)
            parents[pid], identities[pid] = int(fields[1]), (pid, fields[19])
        except (OSError, ValueError, IndexError): continue
    result, pending = [], [os.getpid()]
    while pending:
        parent = pending.pop()
        children = [pid for pid, ppid in parents.items() if ppid == parent]
        pending.extend(children)
        result.extend(identities[pid] for pid in children)
    return result


def _kill(identity):
    if identity is not None and _identity(identity[0]) == identity:
        try: os.kill(identity[0], signal.SIGKILL)
        except ProcessLookupError: pass


def _cleanup(process, identity):
    # WNOWAIT keeps the group leader's PID reserved until the group has been
    # stopped, so this group ID cannot identify a later unrelated process.
    if _identity(process.pid) == identity:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
    deadline = time.monotonic()+5
    while True:
        children = _descendants()
        for child in reversed(children): _kill(child)
        # Reap the immediate child first, preserving subprocess's true result.
        if process.returncode is None:
            try: process.wait(timeout=0.05)
            except subprocess.TimeoutExpired: pass
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0: break
            except ChildProcessError: break
        if not _descendants(): return
        if time.monotonic() >= deadline:
            # Do not release the lease while an uninterruptible writer remains.
            # Continued bounded scans retain ownership until it exits.
            deadline = time.monotonic()+5
        time.sleep(0.02)


def supervise(args):
    global _cancelled
    libc = ctypes.CDLL(None, use_errno=True)
    # Linux PR_SET_PDEATHSIG and PR_SET_CHILD_SUBREAPER. Fail before launching
    # the tool if independent cleanup cannot be established.
    signal.signal(signal.SIGTERM, _cancel)
    signal.signal(signal.SIGINT, _cancel)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0 or libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "cannot establish action-worker ownership")
    os.fstat(args.lease_fd)
    if os.getppid() != args.parent_pid or _cancelled:
        return {"kind":"cancelled", "returncode":128+(_cancelled or signal.SIGTERM)}
    process = subprocess.Popen(args.command, stdin=sys.stdin.buffer,
                               stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                               start_new_session=True, pass_fds=(args.lease_fd,))
    identity = _identity(process.pid)
    deadline = time.monotonic()+args.timeout
    result = None
    try:
        while True:
            if _cancelled:
                result = {"kind":"cancelled", "returncode":128+_cancelled}
                break
            observation = os.waitid(os.P_PID, process.pid, os.WEXITED|os.WNOHANG|os.WNOWAIT)
            if observation is not None:
                # Keep the unreaped leader until _cleanup has stopped any
                # surviving descendants in its process group.
                result = {"kind":"completed", "returncode":
                          observation.si_status if observation.si_code == os.CLD_EXITED else -observation.si_status}
                break
            if time.monotonic() >= deadline:
                result = {"kind":"timeout", "returncode":124}
                break
            time.sleep(0.02)
    finally:
        _cleanup(process, identity)
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--lease-fd",type=int,required=True)
    parser.add_argument("--result-fd",type=int,required=True)
    parser.add_argument("--parent-pid",type=int,required=True)
    parser.add_argument("--timeout",type=float,required=True)
    parser.add_argument("command",nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]: args.command = args.command[1:]
    try:
        if not args.command: raise ValueError("action worker requires a command")
        result = supervise(args)
    except BaseException as error:
        result = {"kind":"worker-error", "returncode":125, "error":str(error)}
    try:
        os.write(args.result_fd,(json.dumps(result)+"\n").encode())
    except OSError:
        pass  # The original caller may have been killed; cleanup still ran.
    finally:
        os.close(args.result_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
