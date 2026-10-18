#!/usr/bin/env python3
"""Short, host-only feedback. A pass does not qualify a guest or compiler.

Uses the runner's Python standard library without realizing the Nix toolchain.
Full acceptance still repeats these checks in its pinned environment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest


SUITES = ("tests/scaffold", "tests/core0", "tests/ci")


def run_suite(directory: Path, stream) -> dict:
    suite = unittest.TestLoader().discover(str(directory))
    expected = suite.countTestCases()
    if expected == 0:
        raise ValueError(f"Empty preflight suite: {directory}")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    passed = result.wasSuccessful() and result.testsRun == expected and not result.skipped
    return {"status": "PASS" if passed else "FAIL", "tests": result.testsRun,
            "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    report = {"schema_version": 1, "scope": "Host-only preflight; no target acceptance",
              "status": "FAIL", "suites": {}}
    try:
        with (args.output_dir / "scaffold-metadata.log").open("x") as stream:
            subprocess.run([sys.executable, str(root / "scripts/check_scaffold.py")],
                           cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=30, check=True)
        for name in SUITES:
            with (args.output_dir / (Path(name).name + ".log")).open("x") as stream:
                value = run_suite(root / name, stream)
            report["suites"][name] = value
            print(f"{name}: {value}", flush=True)
        if len(report["suites"]) != len(SUITES) or not report["suites"]:
            raise ValueError("Missing mandatory preflight suites")
        if all(value["status"] == "PASS" for value in report["suites"].values()):
            report["status"] = "PASS"
    except Exception as exc:
        report["error"] = str(exc)
        print(f"Preflight failed: {exc}", file=sys.stderr)
    report["elapsed_seconds"] = time.monotonic() - start
    (args.output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "PASS":
        for log in args.output_dir.glob("*.log"):
            print(f"{log.name}:\n{log.read_text()}", file=sys.stderr)
        return 1
    print("Host preflight passed; full pinned PR/main/manual acceptance remains required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
