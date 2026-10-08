#!/usr/bin/env python3
"""Timer acceptance fail-closed orchestration and exact source checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_foundation_gate8 as checker
import gate8_corpus as corpus
import run_timer_case as runner
from core0_common import CommandResult, Core0Error, write_json


def policy_output():
    lines = []
    for index, name in enumerate(checker.LEMMA_NAMES):
        identity = f"'Lemma.Core0.Timer.Model.{name}'"
        lines.append(identity + (" does not depend on any axioms" if index == 0 else " depends on axioms: [propext]"))
    return "\n".join(lines) + "\n" + checker.POLICY_MARKER + "\n"


class TimerCheckerTests(unittest.TestCase):
    def test_exact_rejection_manifest_and_fixture_catalog(self):
        cases = checker._load_rejections(ROOT)
        self.assertEqual(len(cases), 4)
        self.assertEqual([case["name"] for case in cases], list(checker.REJECTION_NAMES))

    def test_policy_model_counts_and_actual_axiom_sets_are_closed(self):
        text = policy_output()
        self.assertEqual(len(checker._parse_policy_output(text)), 6)
        for bad in (text.replace("PROBES:26", "PROBES:25"), text + checker.POLICY_MARKER + "\n",
                    text.replace("[propext]", "[sorryAx]", 1),
                    text.replace("[propext]", "[Classical.choice]", 1),
                    text.replace(checker.LEMMA_NAMES[0], "wrongTheorem", 1)):
            with self.assertRaises(Core0Error):
                checker._parse_policy_output(bad)

    def test_timeout_process_protocol_and_audit_errors_never_count_as_mutants(self):
        for category in ("target-timeout", "target-exit-mismatch", "protocol-mismatch", "emulator-stderr"):
            with self.assertRaises(checker.Gate8Failure) as caught:
                checker._stage("mutation-behavior-failure", "O2/2",
                    lambda: (_ for _ in ()).throw(runner.TimerRunFailure(category, "wrong failure")))
            self.assertEqual(caught.exception.category, category)

    def test_old_success_is_invalidated_before_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "build/foundation/gate8"
            work.mkdir(parents=True)
            write_json(work / checker.RESULT_FILE, {"status": "pass"})
            with mock.patch.object(checker, "build_timer_suite", side_effect=Core0Error("build failed")):
                with self.assertRaisesRegex(checker.Gate8Failure, "compile-or-link-failure"):
                    checker.check_gate8(root=root, work=work, clean=False, timeout_seconds=1, qemu_timeout=1)
            self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_invalid_timeout_does_not_launch_or_reuse_a_prior_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "build/check"
            work.mkdir(parents=True)
            write_json(work / checker.RESULT_FILE, {"status": "pass"})
            with mock.patch.object(checker, "build_timer_suite") as build:
                with self.assertRaisesRegex(checker.Gate8Failure, "harness-input-failure"):
                    checker.check_gate8(root=root, work=work, clean=False, timeout_seconds=float("nan"), qemu_timeout=1)
                build.assert_not_called()
            self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_refuses_destructive_cleanup_outside_the_build_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "precious"
            work.mkdir()
            (work / "keep").write_text("retain")
            with self.assertRaises(checker.Gate8Failure):
                checker.check_gate8(root=root, work=work, clean=True, timeout_seconds=1, qemu_timeout=1)
            self.assertEqual((work / "keep").read_text(), "retain")

    def test_each_mutant_is_exactly_its_single_source_register_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control, mutant = root / "control", root / "mutant"
            control.mkdir(); mutant.mkdir()
            assembly = ("core0_trap_vector:\n  ld s3, 144(sp)\n"
                        "core0_timer_set_compare:\n  sd a0, 0(t0)\n"
                        ".size core0_timer_set_compare, . - core0_timer_set_compare\n")
            for name in checker.SOURCE_ARTIFACTS + ("program.opt.ll", "program.o"):
                (control / name).write_text("same")
                (mutant / name).write_text("same")
            (control / "startup.S").write_text(assembly)
            for selected in (1, 2):
                delta = assembly.replace("ld s3, 144(sp)", "ld s3, 152(sp)") if selected == 1 else assembly.replace("sd a0, 0(t0)", "sd t1, 0(t0)")
                (mutant / "startup.S").write_text(delta)
                for directory, identity in ((control, 0), (mutant, selected)):
                    write_json(directory / "timer-suite-manifest.json",
                        {"same_checked_source": True, "timer_mutation": runner.mutation_metadata(identity)})
                with mock.patch.object(runner, "source_inputs", return_value={"source": "hash"}):
                    result = checker._verify_mutation(control, mutant, root, selected)
                    self.assertEqual(result["match_count"], 1)
                    (mutant / "startup.S").write_text(delta + "extra instruction\n")
                    with self.assertRaisesRegex(Core0Error, "single approved"):
                        checker._verify_mutation(control, mutant, root, selected)

    def test_source_probe_success_marker_followed_by_failure_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "examples/foundation"
            directory.mkdir(parents=True)
            (directory / "TimerPolicyProbes.lean").write_text("#guard true\n" * 32)
            (directory / "TimerFrontendProbes.lean").write_text("frontend source")
            policy = CommandResult((), 0, policy_output().encode(), b"", 0)
            frontend = CommandResult((), 1, checker.FRONTEND_MARKER.encode(), b"", 0)
            with mock.patch.object(checker, "run_bounded", side_effect=(policy, frontend)):
                with self.assertRaisesRegex(Core0Error, "frontend probe failed"):
                    checker._run_probes(root=root, work=root / "build/probes", timeout_seconds=1)

    def test_expected_rejection_must_have_the_intended_error_not_just_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "examples/foundation/gate8-reject"
            directory.mkdir(parents=True)
            (directory / "rejections.json").write_text((ROOT / "examples/foundation/gate8-reject/rejections.json").read_text())
            for name in checker.REJECTION_FILES:
                (directory / name).write_text("fixture source")
            wrong = CommandResult((), 1, b"source:1:1: error: unknown declaration\n", b"", 0)
            with mock.patch.object(checker, "run_bounded", return_value=wrong):
                with self.assertRaisesRegex(Core0Error, "intended diagnostic"):
                    checker._run_rejections(root=root, work=root / "build/rejections", timeout_seconds=1)


if __name__ == "__main__":
    unittest.main()
