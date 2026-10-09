#!/usr/bin/env python3
"""Host-only helpers for the bounded Core0 build and execution harness."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


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
    process = subprocess.Popen(
        list(argv),
        cwd=cwd,
        env=None if env is None else dict(env),
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(input=stdin, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        # Kill the process group so QEMU children cannot survive a harness failure.
        try:
            os.killpg(process.pid, 9)
        except ProcessLookupError:
            pass
        stdout, stderr = process.communicate()
        elapsed = time.monotonic() - started
        raise Core0Error(
            f"command timed out after {elapsed:.3f}s: {' '.join(argv)}"
        ) from error
    elapsed = time.monotonic() - started
    return CommandResult(tuple(argv), process.returncode, stdout, stderr, elapsed)


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
