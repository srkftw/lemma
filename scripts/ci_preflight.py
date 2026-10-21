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

# These tests consume external retained process inputs, not portable fixtures.
# Only this exact missing-input disposition is optional in hosted silicon CI.
# If an input is present its test still executes and must pass normally.
SILICON_RETAINED_SKIPS = {
    "test_filler_source.OriginalRowFillerTests.test_actual_original_report_retains_twelve_tangent_witnesses":
        "actual external process report not retained",
    "test_filler_source.OriginalRowFillerTests.test_actual_source_well_move_plan_preserves_nonowners_and_exact_padding_neighbors":
        "exact external physical source/owner proof not retained",
    "test_gds_geometry.NativeGdsGeometryTests.test_original_map_binds_every_routed_metal_cut_and_port_purpose":
        "original external PDK map not installed",
    "test_multimodal_v2_binding.BindingTests.test_archived_source_does_not_acquire_new_dependency":
        "optional retained local source archive",
    "test_sample_hold.OriginalProcessSampleHold.test_actual_nominal_and_negative_waveforms_keep_strict_observation_relation":
        "actual source-bound SPICE waveforms not retained",
    "test_two_load_launch.TwoLoadLaunch.test_current_actual_wire_loads_and_changed_source_rejection":
        "retained actual route is external to Git",
    "test_two_load_launch.TwoLoadLaunch.test_exact_completed_precursor_admission_preserves_original_producer":
        "retained actual precursor is external to Git",
    "test_well_fill_route.WellFillRoute.test_actual_retained_sources_are_admitted_without_rerouting_or_reexecution":
        "actual external layout producers not retained",
    "test_well_fill_route.WellFillRoute.test_exact_actual_spacer_serialization_and_consequential_negatives":
        "actual completed route not retained",
}


def run_suite(directory: Path, stream, *, allowed_skips: dict[str, str] | None = None) -> dict:
    suite = unittest.TestLoader().discover(str(directory))
    expected = suite.countTestCases()
    if expected == 0:
        raise ValueError(f"Empty preflight suite: {directory}")
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    unavailable = [{"test": test.id(), "reason": reason, "disposition": "unavailable"}
                   for test, reason in result.skipped
                   if allowed_skips is not None and allowed_skips.get(test.id()) == reason]
    executed = result.testsRun - len(result.skipped)
    passed = (result.wasSuccessful() and result.testsRun == expected and executed > 0
              and len(unavailable) == len(result.skipped))
    value = {"status": "PASS" if passed else "FAIL", "tests": result.testsRun,
             "failures": len(result.failures), "errors": len(result.errors),
             "skipped": len(result.skipped)}
    if allowed_skips is not None:
        value.update({"executed": executed, "optional_retained_unavailable": unavailable,
                      "unexpected_skips": [{"test": test.id(), "reason": reason}
                                           for test, reason in result.skipped
                                           if allowed_skips.get(test.id()) != reason],
                      "scope": "Host checks only; unavailable retained process inputs are not qualified"})
    return value


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
