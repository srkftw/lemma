#!/usr/bin/env python3
"""Host-only helpers for the bounded Core0 build and execution harness."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
import shutil
import subprocess
import signal
import sys
import threading
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

LOADED_SOURCE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class Core0Error(RuntimeError):
    pass


REQUIRED_TOOLS = (
    "lean",
    "lake",
    "opt",
    "llc",
    "clang",
    "ld.lld",
    "llvm-nm",
    "llvm-objdump",
    "llvm-readelf",
    "qemu-system-riscv64",
    "dtc",
)


def require_tools(names: Iterable[str] = REQUIRED_TOOLS) -> dict[str, str]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for name in names:
        path = shutil.which(name)
        if path is None:
            missing.append(name)
        else:
            resolved[name] = str(Path(path).resolve())
    if missing:
        raise Core0Error("missing required tools: " + ", ".join(sorted(missing)))
    return resolved


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> object:
    if not path.is_file():
        raise Core0Error(f"required JSON file is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Core0Error(f"invalid JSON in {path}: {error}") from error


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float


LEASE_FD: ContextVar[int | None] = ContextVar("lemma_action_lease_fd", default=None)
LEASE_WORKER_PATH: ContextVar[Path | None] = ContextVar("lemma_action_worker_path",default=None)
LEASE_WORKER_SHA256: ContextVar[str | None] = ContextVar("lemma_action_worker_sha256",default=None)


@contextmanager
def action_lease(fd: int, *, worker_path: Path | None = None):
    """Retain this already-locked FD across owned compiler process lifetimes.

    Lock contexts must close their FD, rather than explicitly LOCK_UN, so a
    killed caller cannot release the inherited worker's remaining ownership.
    """
    os.fstat(fd)
    source = Path(worker_path) if worker_path is not None else Path(__file__).with_name("action_worker.py")
    payload = source.read_bytes()
    with tempfile.TemporaryDirectory(prefix="lemma-action-worker-") as temporary:
        frozen = Path(temporary)/"action_worker.py"
        frozen.write_bytes(payload)
        frozen.chmod(0o444)
        tokens = (LEASE_FD.set(fd),LEASE_WORKER_PATH.set(frozen),
                  LEASE_WORKER_SHA256.set(hashlib.sha256(payload).hexdigest()))
        try:
            yield
        finally:
            LEASE_WORKER_SHA256.reset(tokens[2])
            LEASE_WORKER_PATH.reset(tokens[1])
            LEASE_FD.reset(tokens[0])


def _worker_descendants(parent: int) -> list[tuple[int, str]]:
    parents, identities = {}, {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit(): continue
        try:
            fields = (path/"stat").read_text().rsplit(")", 1)[1].split()
            pid = int(path.name)
            parents[pid], identities[pid] = int(fields[1]), (pid, fields[19])
        except (OSError, ValueError, IndexError): continue
    result, pending = [], [parent]
    while pending:
        owner = pending.pop()
        children = [pid for pid, ppid in parents.items() if ppid == owner]
        pending.extend(children)
        result.extend(identities[pid] for pid in children)
    return result


def _stop_bounded(process: subprocess.Popen, *, leased: bool) -> tuple[bytes, bytes]:
    if not leased:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        return process.communicate()
    # The worker receives cancellation and stops its separate owned tool group.
    try: process.send_signal(signal.SIGTERM)
    except ProcessLookupError: pass
    try:
        return process.communicate(timeout=7)
    except subprocess.TimeoutExpired:
        # Independently verify descendants before the last-resort stop. Numeric
        # PIDs alone never authorize signals to later unrelated processes.
        descendants = _worker_descendants(process.pid)
        for pid, start in reversed(descendants):
            try:
                current = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                if current[19] == start: os.kill(pid, signal.SIGKILL)
            except (OSError, IndexError): pass
        try:
            return process.communicate(timeout=7)
        except subprocess.TimeoutExpired as error:
            # An uninterruptible descendant may still hold writable state after
            # SIGKILL. The supervisor must retain the lease until it can reap
            # that writer. Bound the caller's wait without killing ownership.
            try:
                fields = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")",1)[1].split()
                process._lemma_cleanup_worker = {"pid":process.pid,"start_ticks":fields[19],
                    "boot_id":Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
            except (OSError,IndexError):
                process._lemma_cleanup_worker = {"pid":process.pid,"start_ticks":None,"boot_id":None}
            threading.Thread(target=process.wait,daemon=True,name="lemma-action-worker-reaper").start()
            return error.output or b"", error.stderr or b""


def _timeout_error(argv: Sequence[str], started: float, stdout: bytes, stderr: bytes,
                   cleanup_worker: dict | None = None) -> Core0Error:
    elapsed = time.monotonic()-started
    error = Core0Error(f"command timed out after {elapsed:.3f}s: {' '.join(argv)}")
    # Callers can preserve the actual partial observations in their ordinary
    # failure receipts without parsing or manufacturing a successful result.
    error.argv = tuple(argv)
    error.stdout = stdout
    error.stderr = stderr
    error.elapsed_seconds = elapsed
    error.cleanup_worker = cleanup_worker
    error.cleanup_pending = cleanup_worker is not None
    return error


def run_bounded(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    stdin: bytes | None = None,
) -> CommandResult:
    if not argv:
        raise Core0Error("refusing to execute an empty command")
    started = time.monotonic()
    lease = LEASE_FD.get()
    result_read, result_write = (None, None)
    actual, descriptors = list(argv), ()
    if lease is not None:
        worker = LEASE_WORKER_PATH.get()
        if worker is None: raise Core0Error("protected action is missing its immutable worker snapshot")
        result_read, result_write = os.pipe()
        actual = [sys.executable, str(worker),
                  "--lease-fd",str(lease),"--result-fd",str(result_write),
                  "--parent-pid",str(os.getpid()),"--timeout",str(timeout_seconds),"--",*argv]
        descriptors = (lease,result_write)
    try:
        process = subprocess.Popen(actual,cwd=cwd,env=None if env is None else dict(env),
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,pass_fds=descriptors)
    except BaseException:
        if result_read is not None: os.close(result_read)
        raise
    finally:
        if result_write is not None: os.close(result_write)
    try:
        try:
            stdout, stderr = process.communicate(input=stdin,timeout=timeout_seconds+(7 if lease is not None else 0))
        except subprocess.TimeoutExpired as error:
            stdout, stderr = _stop_bounded(process,leased=lease is not None)
            raise _timeout_error(argv,started,stdout,stderr,getattr(process,"_lemma_cleanup_worker",None)) from error
        except BaseException:
            _stop_bounded(process,leased=lease is not None)
            raise
        returncode = process.returncode
        if result_read is not None:
            try:
                protocol = json.loads(os.read(result_read,4096))
            except (OSError,ValueError) as error:
                raise Core0Error("action worker did not return a complete execution result") from error
            if protocol.get("kind") == "timeout":
                raise _timeout_error(argv,started,stdout,stderr)
            if protocol.get("kind") != "completed" or type(protocol.get("returncode")) is not int:
                raise Core0Error("action worker failed: " + str(protocol))
            returncode = protocol["returncode"]
    finally:
        if result_read is not None: os.close(result_read)
    elapsed = time.monotonic() - started
    return CommandResult(tuple(argv), returncode, stdout, stderr, elapsed)


def checked(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float = 60.0,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    result = run_bounded(argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    if result.returncode != 0:
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise Core0Error(
            f"command failed with exit {result.returncode}: {' '.join(argv)}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return result


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
