#!/usr/bin/env python3
"""Record the actual CI checkout separately from the PR head and merge base.

This is orchestration provenance, not an acceptance result or a toolchain audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("Missing or malformed source commit")
    return value


def identity(root: Path, env: dict[str, str], event: dict) -> dict:
    commit = sha(git(root, "rev-parse", "HEAD"))
    expected = sha(env["GITHUB_SHA"])
    if commit != expected or git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("CI requires the exact clean event checkout")
    name = env["GITHUB_EVENT_NAME"]
    if name not in {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("Unsupported CI event")
    parents = re.findall(r"^parent ([0-9a-f]{40})$", git(root, "cat-file", "-p", "HEAD"), re.M)
    pr = None
    if name == "pull_request":
        request = event["pull_request"]
        number = event["number"]
        if type(number) is not int or number <= 0:
            raise ValueError("Missing PR identity")
        base, head = sha(request["base"]["sha"]), sha(request["head"]["sha"])
        if parents != [base, head]:
            raise ValueError("PR checkout is not the event's synthetic merge candidate")
        pr = {"number": number, "base": base, "head": head}
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        if not env[key].isdigit() or int(env[key]) <= 0:
            raise ValueError("Missing CI run identity")
    return {
        "schema_version": 1,
        "scope": "CI checkout provenance; no acceptance result",
        "repository": env["GITHUB_REPOSITORY"],
        "event": name,
        "ref": env["GITHUB_REF"],
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
        "job": env["GITHUB_JOB"],
        "checkout": {"commit": commit, "tree": git(root, "rev-parse", "HEAD^{tree}"),
                     "parents": parents, "clean": True},
        "pull_request": pr,
        "runner": {"os": env.get("RUNNER_OS"), "arch": env.get("RUNNER_ARCH"),
                   "python": platform.python_version()},
        "inputs": {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                   for path in ("flake.nix", "flake.lock", "lean-toolchain",
                                "tooling/toolchain-lock.json")},
        "dependency_cache": "No project or Actions dependency cache restored; Nix may use upstream binary substitutes",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    value = identity(root, dict(os.environ), event)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(f"CI checkout: {value['checkout']['commit']} ({value['event']}); PR head: {value['pull_request']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
