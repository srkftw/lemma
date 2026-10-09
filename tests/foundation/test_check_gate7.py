#!/usr/bin/env python3
"""Gate 7 checker failure classification and fail-closed source policies."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_foundation_gate7 as checker
import gate7_corpus as corpus
import run_trap_case
from core0_common import CommandResult, Core0Error, write_json


POLICY = ("'approvedEcallResume' depends on axioms: [propext]\n"
          "'approvedBreakpointResume' depends on axioms: [propext, Quot.sound]\n"
          "TRAP_POLICY_PROBES:20\n")


class TrapCheckerTests(unittest.TestCase):
    def test_exact_source_rejection_manifest_and_fixture_set(self):
        cases = checker._load_rejections(ROOT)
        self.assertEqual(len(cases), 4)
        self.assertEqual([case["name"] for case in cases], list(checker.REJECTION_NAMES))

    def test_rejection_manifest_cannot_weaken_diagnostic_or_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "examples/foundation/gate7-reject"
            directory.mkdir(parents=True)
            original = json.loads((ROOT / "examples/foundation/gate7-reject/rejections.json").read_text())
            for name in checker.REJECTION_FILES:
                (directory / name).write_text("fixture")
            write_json(directory / "rejections.json", original)
            checker._load_rejections(root)
            for key, value in (("required_fragments", ["anything"]), ("path", "../escape.lean"), ("diagnostic_code", "anything")):
                raw = json.loads(json.dumps(original))
                raw["cases"][0][key] = value
                write_json(directory / "rejections.json", raw)
                with self.assertRaises(Core0Error):
                    checker._load_rejections(root)

    def test_policy_markers_and_conditional_axioms_are_exact(self):
        self.assertEqual(len(checker._parse_policy_output(POLICY)), 2)
        for text in (POLICY.replace(":20", ":19"), POLICY + "TRAP_POLICY_PROBES:20\n",
                     POLICY.replace("Quot.sound", "sorryAx"), POLICY.replace("propext", "untrustedAxiom"),
                     POLICY.replace("approvedEcallResume", "otherTheorem")):
            with self.assertRaises(Core0Error):
                checker._parse_policy_output(text)

    def test_failure_categories_do_not_call_timeout_or_exit_mismatch_a_mutant(self):
        for category in ("target-timeout", "target-exit-mismatch", "protocol-mismatch", "emulator-stderr"):
            with self.assertRaises(checker.Gate7Failure) as caught:
                checker._stage("mutation-behavior-failure", "O2/mutant", lambda: (_ for _ in ()).throw(run_trap_case.TrapRunFailure(category, "bad")))
            self.assertEqual(caught.exception.category, category)

    def test_frontend_requires_actual_success_command_and_exact_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "examples/foundation/TrapFrontendProbes.lean"
            source.parent.mkdir(parents=True)
            source.write_text("frontend source")
            work = root / "build/probes"
            good = CommandResult((), 0, (checker.FRONTEND_MARKER + "\n").encode(), b"", 0)
            with mock.patch.object(checker, "run_bounded", return_value=good):
                self.assertEqual(len(checker._run_frontend_probe(root=root, work=work, timeout_seconds=1)["checks"]), 8)
            for code, text in ((1, checker.FRONTEND_MARKER), (0, ""), (0, checker.FRONTEND_MARKER * 2)):
                with mock.patch.object(checker, "run_bounded", return_value=CommandResult((), code, text.encode(), b"", 0)):
                    with self.assertRaises(Core0Error):
                        checker._run_frontend_probe(root=root, work=work, timeout_seconds=1)

    def test_build_failure_invalidates_existing_pass_before_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "build/foundation/gate7"
            work.mkdir(parents=True)
            write_json(work / checker.RESULT_FILE, {"status": "PASS"})
            with mock.patch.object(checker, "build_trap_suite", side_effect=Core0Error("build rejected")):
                with self.assertRaisesRegex(checker.Gate7Failure, "compile-or-link-failure"):
                    checker.check_gate7(root=root, work=work, clean=False, timeout_seconds=1, qemu_timeout=1)
            self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_refuses_to_clean_outside_build_subtree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "not-build"
            work.mkdir()
            (work / "precious").write_text("preserve")
            with self.assertRaises(checker.Gate7Failure):
                checker.check_gate7(root=root, work=work, clean=True, timeout_seconds=1, qemu_timeout=1)
            self.assertEqual((work / "precious").read_text(), "preserve")

    def test_mutation_delta_only_one_exact_restore_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control, mutant = root / "control", root / "mutant"
            control.mkdir(); mutant.mkdir()
            for name in checker.SOURCE_ARTIFACTS + ("program.opt.ll", "program.o"):
                (control / name).write_text("same")
                (mutant / name).write_text("same")
            (control / "startup.S").write_text("  ld s3, 144(sp)\n  ld s4, 152(sp)\n")
            (mutant / "startup.S").write_text("  ld s3, 152(sp)\n  ld s4, 152(sp)\n")
            common = {"contract_version": corpus.PROFILE, "source": "unchanged"}
            for path, identity, matches in ((control, "none", 0), (mutant, "restore-s3-from-s4", 1)):
                write_json(path / "trap-suite-manifest.json", dict(common, restore_mutation={
                    "identity": identity, "production_selectable": False,
                    "transform_stage": "structured-machine-restore", "match_count": matches}))
            with mock.patch.object(checker, "_source_inputs", return_value={"source": "hash"}):
                result = checker._verify_mutation(control, mutant, root)
                self.assertEqual(result["expected_context_mask"], 0x40000)
                (mutant / "program.ll").write_text("different program")
                with self.assertRaisesRegex(Core0Error, "program.ll"):
                    checker._verify_mutation(control, mutant, root)
                (mutant / "program.ll").write_text("same")
                (mutant / "startup.S").write_text("  ld s3, 152(sp)\n  ld s4, 160(sp)\n")
                with self.assertRaisesRegex(Core0Error, "exactly one"):
                    checker._verify_mutation(control, mutant, root)


if __name__ == "__main__":
    unittest.main()
