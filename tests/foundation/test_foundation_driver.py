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

    def test_stress_is_forwarded_only_to_the_monitor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(driver, "check_gate9", return_value={"counts": {}}) as gate9:
                self.assertEqual(self.invoke(root, ["--phase", "9", "--stress"]), 0)
                self.assertIs(gate9.call_args.kwargs["stress"], True)
            self.assertEqual(self.invoke(root, ["--phase", "8", "--stress"]), 2)

    def test_malformed_cli_invalidates_only_selected_canonical_reports(self):
        cases = (
            (["--all", "--timeout", "not-a-number"], "all-results.json"),
            (["--phase", "9", "--qemu-timeout", "invalid"], "gate9-results.json"),
            (["--phase", "8", "--stress"], "gate8-results.json"),
            (["--all", "--unknown-argument"], "all-results.json"),
            (["--all", "--phase", "9"], "all-results.json"),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (arguments, name) in enumerate(cases):
                with self.subTest(arguments=arguments):
                    work = root / "build" / str(index)
                    work.mkdir(parents=True)
                    (work / name).write_text('{"status":"pass"}\n')
                    (work / (name + ".tmp")).write_text('{"status":"pass"}\n')
                    (work / "unrelated.json").write_text("retain")
                    with mock.patch.object(driver, "check_gate1") as gate1:
                        self.assertEqual(self.invoke(root, [*arguments, "--work-dir", str(work)]), 2)
                        gate1.assert_not_called()
                    self.assertFalse((work / name).exists())
                    self.assertFalse((work / (name + ".tmp")).exists())
                    self.assertEqual((work / "unrelated.json").read_text(), "retain")
                    report = json.loads((work / "check-failure.json").read_text())
                    self.assertEqual(report["status"], "fail")
                    self.assertEqual(report["failure_category"], "harness-input-failure")
                    self.assertEqual(report["failure_context"], "CLI")

    def test_malformed_cli_honors_default_and_equals_work_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for extra in ([], ["--work-dir=build/equals"]):
                work = root / ("build/equals" if extra else "build/foundation/check")
                work.mkdir(parents=True)
                (work / "all-results.json").write_text('{"status":"pass"}\n')
                self.assertEqual(self.invoke(root, ["--all", *extra, "--timeout=bad"]), 2)
                self.assertFalse((work / "all-results.json").exists())
                self.assertTrue((work / "check-failure.json").is_file())

    def test_help_is_read_only_and_successful(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/foundation/check"
            work.mkdir(parents=True)
            old = b'{"status":"pass"}\n'
            (work / "all-results.json").write_bytes(old)
            self.assertEqual(self.invoke(root, ["--help", "--all"]), 0)
            self.assertEqual((work / "all-results.json").read_bytes(), old)
            self.assertFalse((work / "check-failure.json").exists())

    def test_malformed_cli_cannot_write_or_invalidate_outside_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for work in (root / "precious", root / "build"):
                work.mkdir(parents=True, exist_ok=True)
                old = b'{"status":"pass"}\n'
                (work / "all-results.json").write_bytes(old)
                self.assertEqual(self.invoke(root, ["--all", "--work-dir", str(work), "--timeout", "bad"]), 2)
                self.assertEqual((work / "all-results.json").read_bytes(), old)
                self.assertFalse((work / "check-failure.json").exists())

    def test_malformed_cli_does_not_follow_an_old_failure_temporary_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            precious = root / "keep"
            precious.write_text("retain")
            work = root / "build/probe"
            work.mkdir(parents=True)
            (work / "check-failure.json.tmp").symlink_to(precious)
            self.assertEqual(self.invoke(root, ["--all", "--work-dir", str(work), "--timeout", "bad"]), 2)
            self.assertEqual(precious.read_text(), "retain")
            self.assertFalse((work / "check-failure.json.tmp").exists())
            self.assertTrue((work / "check-failure.json").is_file())

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
