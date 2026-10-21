#!/usr/bin/env python3
"""Real host regressions for evidence identity and fail-closed preflight suites."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import ci_preflight
import ci_source


class SourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "--quiet", "--initial-branch=main")
        self.git("config", "user.name", "CI test fixture")
        self.git("config", "user.email", "ci-fixture@example.invalid")
        for path in ("flake.nix", "flake.lock", "lean-toolchain", "tooling/toolchain-lock.json"):
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text("literal fixture: " + path + "\n")
        (self.root / ".gitignore").write_text("build/\n")
        self.commit("base fixture")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.root), *arguments],
                                       text=True, stderr=subprocess.STDOUT).strip()

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "--quiet", "-m", message)

    def environment(self, event="push"):
        return {"GITHUB_SHA": self.git("rev-parse", "HEAD"),
                "GITHUB_EVENT_NAME": event, "GITHUB_REPOSITORY": "srkftw/lemma",
                "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": "fixture",
                "RUNNER_OS": "Linux", "RUNNER_ARCH": "X64"}

    def merge_candidate(self):
        self.git("checkout", "--quiet", "-b", "feature")
        (self.root / "feature").write_text("head\n")
        self.commit("feature fixture")
        head = self.git("rev-parse", "HEAD")
        self.git("checkout", "--quiet", "main")
        (self.root / "main-change").write_text("new base\n")
        self.commit("base advance fixture")
        base = self.git("rev-parse", "HEAD")
        self.git("merge", "--quiet", "--no-ff", "--no-edit", "feature")
        return {"number": 5, "pull_request": {"base": {"sha": base}, "head": {"sha": head}}}

    def test_clean_push_and_manual_identity_bind_actual_git_and_pin_bytes(self):
        for event in ("push", "workflow_dispatch"):
            with self.subTest(event=event):
                value = ci_source.identity(self.root, self.environment(event), {})
                self.assertEqual(value["checkout"], {
                    "commit": self.base, "tree": self.git("rev-parse", "HEAD^{tree}"),
                    "parents": [], "clean": True})
                self.assertIsNone(value["pull_request"])
                self.assertEqual(value["event"], event)
                self.assertEqual(value["inputs"], {
                    path: hashlib.sha256((self.root / path).read_bytes()).hexdigest()
                    for path in ("flake.nix", "flake.lock", "lean-toolchain", "tooling/toolchain-lock.json")})
                self.assertNotIn("status", value)
                self.assertIn("no acceptance result", value["scope"])

    def test_pr_checkout_is_the_actual_merge_with_distinct_head_and_base(self):
        event = self.merge_candidate()
        value = ci_source.identity(self.root, self.environment("pull_request"), event)
        self.assertEqual(value["checkout"]["parents"],
                         [event["pull_request"]["base"]["sha"], event["pull_request"]["head"]["sha"]])
        self.assertEqual(value["pull_request"], {
            "number": 5, "base": event["pull_request"]["base"]["sha"],
            "head": event["pull_request"]["head"]["sha"]})
        self.assertNotEqual(value["checkout"]["commit"], value["pull_request"]["head"])

    def test_mismatched_head_dirty_or_missing_pin_reject(self):
        env = self.environment()
        env["GITHUB_SHA"] = "0" * 40
        with self.assertRaises(ValueError):
            ci_source.identity(self.root, env, {})
        untracked = self.root / "untracked"
        untracked.write_text("dirty\n")
        with self.assertRaises(ValueError):
            ci_source.identity(self.root, self.environment(), {})
        untracked.unlink()
        (self.root / "flake.nix").write_text("tracked change\n")
        with self.assertRaises(ValueError):
            ci_source.identity(self.root, self.environment(), {})
        self.git("checkout", "--", "flake.nix")
        (self.root / "flake.lock").unlink()
        self.commit("missing input fixture")
        with self.assertRaises(FileNotFoundError):
            ci_source.identity(self.root, self.environment(), {})

    def test_nonmerge_wrong_parents_and_invalid_pr_identity_reject(self):
        nonmerge = {"number": 5, "pull_request": {"base": {"sha": self.base}, "head": {"sha": self.base}}}
        with self.assertRaises(ValueError):
            ci_source.identity(self.root, self.environment("pull_request"), nonmerge)
        event = self.merge_candidate()
        for number in (0, -1, True, "5"):
            malformed = dict(event, number=number)
            with self.subTest(number=number), self.assertRaises(ValueError):
                ci_source.identity(self.root, self.environment("pull_request"), malformed)
        wrong = {"number": 5, "pull_request": {
            "base": event["pull_request"]["head"], "head": event["pull_request"]["base"]}}
        with self.assertRaises(ValueError):
            ci_source.identity(self.root, self.environment("pull_request"), wrong)

    def test_unknown_event_bad_sha_or_missing_run_identity_reject(self):
        for changes in ({"GITHUB_EVENT_NAME": "merge_group"}, {"GITHUB_SHA": "not-a-sha"},
                        {"GITHUB_RUN_ID": "0"}, {"GITHUB_RUN_ATTEMPT": "-1"},
                        {"GITHUB_RUN_ID": ""}):
            env = dict(self.environment(), **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ci_source.identity(self.root, env, {})
        env = self.environment()
        del env["GITHUB_RUN_ID"]
        with self.assertRaises(KeyError):
            ci_source.identity(self.root, env, {})

    def test_ignored_old_reports_do_not_supply_current_source_evidence(self):
        output = self.root / "build/old-PASS.json"
        output.parent.mkdir()
        output.write_text('{"status":"PASS","commit":"stale"}\n')
        value = ci_source.identity(self.root, self.environment(), {})
        self.assertEqual(value["checkout"]["commit"], self.base)
        self.assertNotIn("status", value)
        self.assertNotIn("stale", str(value))

    def test_source_cli_writes_exclusive_provenance_and_preserves_existing_file(self):
        script = self.root / "scripts/ci_source.py"
        script.parent.mkdir()
        shutil.copyfile(ROOT / "scripts/ci_source.py", script)
        self.commit("source CLI fixture")
        env = dict(os.environ, **self.environment())
        event = self.root / "build/event.json"
        event.parent.mkdir()
        event.write_text("{}\n")
        env["GITHUB_EVENT_PATH"] = str(event)
        output = self.root / "build/ci/source.json"
        command = [sys.executable, str(script), "--output", str(output)]
        first = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = output.read_bytes()
        value = json.loads(original)
        self.assertEqual(value["checkout"]["commit"], env["GITHUB_SHA"])
        self.assertNotIn("status", value)
        second = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), original)
        env["GITHUB_SHA"] = "0" * 40
        rejected = self.root / "build/ci/rejected.json"
        invalid = subprocess.run([sys.executable, str(script), "--output", str(rejected)],
                                 cwd=self.root, env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse(rejected.exists())


class PreflightSuiteTests(unittest.TestCase):
    sequence = 0

    def run_fixture(self, body, *, allowed_skips=None):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            type(self).sequence += 1
            name = f"test_ci_preflight_fixture_{type(self).sequence}"
            (directory / (name + ".py")).write_text("import unittest\n" + body)
            self.addCleanup(sys.modules.pop, name, None)
            stream = io.StringIO()
            options = {} if allowed_skips is None else {"allowed_skips": allowed_skips(name)}
            value = ci_preflight.run_suite(directory, stream, **options)
            return value, stream.getvalue()

    def test_real_successful_suite_reports_nonempty_execution(self):
        value, log = self.run_fixture("class Fixture(unittest.TestCase):\n"
                                      "    def test_literal(self): self.assertEqual(3 + 4, 7)\n")
        self.assertEqual(value, {"status": "PASS", "tests": 1, "failures": 0, "errors": 0, "skipped": 0})
        self.assertIn("Ran 1 test", log)

    def test_real_failure_error_skip_and_import_error_are_failures(self):
        bodies = (
            ("    def test_failure(self): self.fail('literal failure')\n", "failures"),
            ("    def test_error(self): raise RuntimeError('literal error')\n", "errors"),
            ("    @unittest.skip('fixture skip')\n    def test_skip(self): pass\n", "skipped"),
        )
        for body, field in bodies:
            with self.subTest(field=field):
                value, _ = self.run_fixture("class Fixture(unittest.TestCase):\n" + body)
                self.assertEqual(value["status"], "FAIL")
                self.assertEqual(value[field], 1)
        value, _ = self.run_fixture("raise ImportError('missing fixture dependency')\n")
        self.assertEqual(value["status"], "FAIL")
        self.assertEqual(value["errors"], 1)

    def test_empty_or_missing_suite_never_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaises(ValueError):
                ci_preflight.run_suite(directory, io.StringIO())
            with self.assertRaises((ImportError, ValueError)):
                ci_preflight.run_suite(directory / "missing", io.StringIO())

    def test_exact_optional_missing_input_is_reported_unavailable(self):
        value, _ = self.run_fixture(
            "class Fixture(unittest.TestCase):\n"
            "    def test_required(self): self.assertEqual(3 + 4, 7)\n"
            "    @unittest.skip('retained input absent')\n"
            "    def test_skip(self): pass\n",
            allowed_skips=lambda module: {f"{module}.Fixture.test_skip": "retained input absent"})
        self.assertEqual(value["status"], "PASS")
        self.assertEqual(value["executed"], 1)
        self.assertEqual(value["unexpected_skips"], [])
        self.assertEqual(len(value["optional_retained_unavailable"]), 1)
        self.assertEqual(value["optional_retained_unavailable"][0]["disposition"], "unavailable")
        self.assertIn("not qualified", value["scope"])

    def test_wrong_optional_identity_reason_or_all_skipped_never_passes(self):
        body = ("class Fixture(unittest.TestCase):\n"
                "    def test_required(self): pass\n"
                "    @unittest.skip('retained input absent')\n"
                "    def test_skip(self): pass\n")
        for allowance in (
            lambda module: {f"{module}.Fixture.test_skip": "different reason"},
            lambda module: {f"{module}.Fixture.test_other": "retained input absent"},
            lambda module: {},
        ):
            value, _ = self.run_fixture(body, allowed_skips=allowance)
            self.assertEqual(value["status"], "FAIL")
            self.assertEqual(len(value["unexpected_skips"]), 1)
        value, _ = self.run_fixture(
            "class Fixture(unittest.TestCase):\n"
            "    @unittest.skip('retained input absent')\n"
            "    def test_skip(self): pass\n",
            allowed_skips=lambda module: {f"{module}.Fixture.test_skip": "retained input absent"})
        self.assertEqual(value["status"], "FAIL")
        self.assertEqual(value["executed"], 0)

    def test_preflight_keeps_exact_host_only_scopes(self):
        self.assertEqual(ci_preflight.SUITES, ("tests/scaffold", "tests/core0", "tests/ci"))

    def cli_fixture(self, directory, *, skip=False, empty=False):
        root = Path(directory)
        (root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/ci_preflight.py", root / "scripts/ci_preflight.py")
        (root / "scripts/check_scaffold.py").write_text("raise SystemExit(0)\n")
        for name in ("scaffold", "core0", "ci"):
            suite = root / "tests" / name
            suite.mkdir(parents=True)
            if empty and name == "core0":
                continue
            decoration = "    @unittest.skip('literal skip')\n" if skip and name == "core0" else ""
            (suite / ("test_literal_" + name + ".py")).write_text(
                "import unittest\nclass Fixture(unittest.TestCase):\n" + decoration
                + "    def test_literal(self): self.assertEqual(2 + 3, 5)\n")
        output = root / "build/preflight"
        command = [sys.executable, str(root / "scripts/ci_preflight.py"), "--output-dir", str(output)]
        run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=5)
        return run, output, command

    def test_preflight_cli_persists_success_and_cannot_overwrite_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, output, command = self.cli_fixture(temporary)
            self.assertEqual(run.returncode, 0, run.stderr)
            original = (output / "result.json").read_bytes()
            value = json.loads(original)
            self.assertEqual(value["status"], "PASS")
            self.assertEqual(set(value["suites"]), set(ci_preflight.SUITES))
            self.assertTrue(all(suite["tests"] == 1 for suite in value["suites"].values()))
            self.assertTrue(all((output / (name + ".log")).is_file()
                                for name in ("scaffold-metadata", "scaffold", "core0", "ci")))
            repeat = subprocess.run(command, cwd=temporary, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertEqual((output / "result.json").read_bytes(), original)

    def test_preflight_cli_returns_failure_and_keeps_logs_for_skip_or_empty(self):
        for fault in ("skip", "empty"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                run, output, _ = self.cli_fixture(temporary, **{fault: True})
                self.assertNotEqual(run.returncode, 0)
                value = json.loads((output / "result.json").read_text())
                self.assertEqual(value["status"], "FAIL")
                self.assertTrue((output / "scaffold-metadata.log").is_file())
                self.assertTrue((output / "core0.log").is_file())
                self.assertIn("core0.log:", run.stderr)
                if fault == "skip":
                    self.assertEqual(value["suites"]["tests/core0"]["skipped"], 1)
                else:
                    self.assertIn("Empty preflight suite", value["error"])


if __name__ == "__main__":
    unittest.main()
