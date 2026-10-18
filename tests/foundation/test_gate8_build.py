#!/usr/bin/env python3
"""Focused tests for the closed Gate 8 build-driver interface."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_timer_suite  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class TimerBuildDriverTests(unittest.TestCase):
    def test_mutation_selector_is_closed_and_not_boolean(self) -> None:
        for mutation in (True, False, -1, 3, "1", None):
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(Core0Error, "integer 0, 1, or 2"):
                    build_timer_suite.build_timer_suite(
                        root=ROOT,
                        output_dir=ROOT / "build/foundation/not-created",
                        opt_level="O0",
                        mutation=mutation,  # type: ignore[arg-type]
                    )

    def test_each_test_only_selector_forwards_only_the_closed_environment(self) -> None:
        for mutation in (0, 1, 2):
            with self.subTest(mutation=mutation), mock.patch.object(
                build_timer_suite, "build", return_value={"status": "pass"}
            ) as invoke:
                result = build_timer_suite.build_timer_suite(
                    root=ROOT,
                    output_dir=ROOT / "build/foundation/mock",
                    opt_level="O2",
                    mutation=mutation,
                    clean=True,
                    build_lean=False,
                    timeout_seconds=17.0,
                )
                self.assertEqual(result, {"status": "pass"})
                kwargs = invoke.call_args.kwargs
                self.assertEqual(kwargs["artifact_category"], "test-timer-suite")
                self.assertEqual(
                    kwargs["export_environment"],
                    {"LEMMA_TIMER_MUTATION": str(mutation)},
                )
                self.assertEqual(kwargs["elaboration_sources"], build_timer_suite.ELABORATION_SOURCES)
                self.assertEqual(kwargs["additional_source_inputs"], build_timer_suite.HOST_INPUTS)

    def test_host_provenance_closes_transitive_auditors_and_runner(self) -> None:
        required = {
            Path("scripts/audit_core0.py"),
            Path("scripts/audit_timer.py"),
            Path("scripts/audit_trap.py"),
            Path("scripts/audit_device.py"),
            Path("scripts/audit_memory.py"),
            Path("scripts/run_timer_case.py"),
            Path("scripts/run_trap_case.py"),
            Path("scripts/check_foundation_gate8.py"),
            Path("examples/foundation/TimerFrontendProbes.lean"),
            Path("examples/foundation/TimerPolicyProbes.lean"),
            Path("docs/audits/timers-core0-v07.html"),
        }
        self.assertTrue(required <= set(build_timer_suite.HOST_INPUTS))


if __name__ == "__main__":
    unittest.main()
