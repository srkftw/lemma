#!/usr/bin/env python3
"""Host-only scope routing and stale aggregate report regressions."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_foundation as driver


class FoundationDriverTests(unittest.TestCase):
    def invoke(self, root, arguments):
        with (
            mock.patch.object(driver, "repo_root", return_value=root),
            mock.patch.object(sys, "argv", ["check-foundation", *arguments]),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            return driver.main()

    def test_phase9_routes_only_to_the_monitor_checker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(driver, "check_gate9", return_value={"counts": {}}) as gate9,
                mock.patch.object(driver, "check_gate8") as gate8,
            ):
                self.assertEqual(self.invoke(root, ["--phase", "9"]), 0)
                gate8.assert_not_called()
                self.assertEqual(gate9.call_args.kwargs["work"], root / "build/foundation/check")

    def test_all_runs_every_gate_in_dependency_order(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            work = root / "build/foundation/check"
            work.mkdir(parents=True)
            observed = []
            for gate in range(1, 10):
                def result(*, selected=gate, **kwargs):
                    observed.append(selected)
                    return {"gate": selected, "status": "pass"}
                stack.enter_context(mock.patch.object(driver, f"check_gate{gate}", side_effect=result))
            self.assertEqual(self.invoke(root, ["--all"]), 0)
            self.assertEqual(observed, list(range(1, 10)))
            report = json.loads((work / "all-results.json").read_text())
            self.assertEqual([item["gate"] for item in report["gates"]], observed)

    def test_early_failure_invalidates_an_old_successful_aggregate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/foundation/check"
            work.mkdir(parents=True)
            (work / "all-results.json").write_text('{"status":"pass"}\n')
            failure = driver.Gate1Failure("compile-failure", "injected", "early qualification failure")
            with mock.patch.object(driver, "check_gate1", side_effect=failure):
                self.assertEqual(self.invoke(root, ["--all"]), 1)
            self.assertFalse((work / "all-results.json").exists())
            report = json.loads((work / "check-failure.json").read_text())
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["failure_category"], "compile-failure")
            self.assertEqual(report["failure_context"], "injected")


if __name__ == "__main__":
    unittest.main()
