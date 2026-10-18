#!/usr/bin/env python3
"""Focused tests for the closed Gate 9 monitor build interface."""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_core0  # noqa: E402
import build_monitor  # noqa: E402


class MonitorBuildDriverTests(unittest.TestCase):
    def test_monitor_api_has_no_fault_or_mutation_selector(self) -> None:
        parameters = inspect.signature(build_monitor.build_monitor_image).parameters
        self.assertEqual(
            set(parameters),
            {"root", "output_dir", "opt_level", "clean", "build_lean", "timeout_seconds"},
        )

    def test_monitor_build_forwards_only_the_closed_category(self) -> None:
        with mock.patch.object(
            build_monitor, "build", return_value={"status": "pass"}
        ) as invoke:
            result = build_monitor.build_monitor_image(
                root=ROOT,
                output_dir=ROOT / "build/foundation/mock-monitor",
                opt_level="O2",
                clean=True,
                build_lean=False,
                timeout_seconds=19.0,
            )
        self.assertEqual(result, {"status": "pass"})
        kwargs = invoke.call_args.kwargs
        self.assertEqual(kwargs["artifact_category"], "test-monitor-image")
        self.assertNotIn("export_environment", kwargs)
        self.assertNotIn("compiler_fault_manifest", kwargs)
        self.assertEqual(kwargs["elaboration_sources"], build_monitor.ELABORATION_SOURCES)
        self.assertEqual(kwargs["additional_source_inputs"], build_monitor._source_inputs(ROOT))

    def test_category_and_generated_catalog_are_closed(self) -> None:
        self.assertIn("test-monitor-image", build_core0.ARTIFACT_CATEGORIES)
        self.assertEqual(
            build_core0.MONITOR_IMAGE_GENERATED_BY_LEAN,
            (
                "program.ll", "startup.S", "link.ld", "layout.json",
                "device-contract.json", "monitor-manifest.json",
                "monitor-normalized.txt", "monitor-abi.json", "symbols.txt",
            ),
        )

    def test_provenance_envelope_contains_all_available_gate9_inputs(self) -> None:
        available = set(build_monitor._source_inputs(ROOT))
        required = {
            Path("scripts/build_monitor.py"),
            Path("scripts/audit_core0.py"),
            Path("scripts/audit_monitor.py"),
            Path("scripts/audit_timer.py"),
            Path("scripts/audit_trap.py"),
            Path("scripts/audit_device.py"),
            Path("scripts/audit_memory.py"),
            Path("scripts/gate6_corpus.py"),
            Path("scripts/run_device_session.py"),
            Path("scripts/run_timer_case.py"),
            Path("scripts/run_trap_case.py"),
            Path("scripts/gate9_corpus.py"),
            Path("scripts/run_monitor_session.py"),
            Path("scripts/check_foundation_gate9.py"),
            Path("examples/foundation/TimerFrontendProbes.lean"),
            Path("examples/foundation/TimerPolicyProbes.lean"),
            Path("examples/foundation/MonitorPolicyProbes.lean"),
            Path("docs/audits/timers-core0-v07.html"),
            Path("docs/audits/monitor-core0-v07.html"),
        }
        self.assertTrue(required <= available)
        self.assertTrue(all((ROOT / path).is_file() for path in available))


if __name__ == "__main__":
    unittest.main()
