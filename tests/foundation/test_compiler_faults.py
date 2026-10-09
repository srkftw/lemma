"""Fail-closed host tests for the quarantined Gate 1 compiler-fault path."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_core0  # noqa: E402
import build_core0  # noqa: E402
import check_foundation  # noqa: E402
import core0_common  # noqa: E402
import run_core0  # noqa: E402


CORPUS_PATH = ROOT / "tests" / "foundation" / "compiler_faults.json"
SOURCE_ROOT = "Lemma.Examples.Foundation.CompilerFaults.entry"
TARGET_SOURCE = "Lemma.Examples.Foundation.CompilerFaults.strictLt"
TARGET_LLVM = "core0_user_Lemma_Examples_Foundation_CompilerFaults_strictLt"


def mutation_fixture() -> tuple[dict[str, object], dict[str, object]]:
    core0_manifest: dict[str, object] = {
        "root": SOURCE_ROOT,
        "functions": [{"source": TARGET_SOURCE, "llvm": TARGET_LLVM}],
    }
    mutation: dict[str, object] = {
        "schema_version": 1,
        "artifact_category": "test-compiler-mutant",
        "transform_stage": "structured-llvm-pre-optimization",
        "production_selectable": False,
        "source_root": SOURCE_ROOT,
        "fault": "ult-as-ule",
        "target_source": TARGET_SOURCE,
        "target_llvm": TARGET_LLVM,
        "match_count": 1,
        "before": "%cmp = icmp ult i64 %x, %y",
        "after": "%cmp = icmp ule i64 %x, %y",
    }
    return core0_manifest, mutation


class CompilerFaultCorpusLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    def load(self, document: object) -> check_foundation.CompilerFaultCorpus:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "compiler_faults.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return check_foundation.load_compiler_fault_corpus(path)

    def test_valid_closed_corpus_loads(self) -> None:
        corpus = self.load(self.document)
        self.assertEqual(corpus.root, SOURCE_ROOT)
        self.assertEqual(len(corpus.cases), 6)

    def test_invalid_descriptor_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["cases"][0]["args"][1] = 7
        with self.assertRaisesRegex(
            core0_common.Core0Error, "must be a string-encoded UInt64"
        ):
            self.load(document)

    def test_duplicate_descriptors_are_rejected(self) -> None:
        mutations = (
            ("name", self.document["cases"][0]["name"], "duplicate name"),
            ("case_id", self.document["cases"][0]["case_id"], "duplicate compiler-fault case id"),
            ("fault", self.document["cases"][0]["fault"], "duplicate compiler fault ID"),
        )
        for field, duplicate, diagnostic in mutations:
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["cases"][1][field] = duplicate
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    self.load(document)

    def test_unknown_fault_and_wrong_target_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["cases"][0]["fault"] = "invented-fault"
        with self.assertRaisesRegex(core0_common.Core0Error, "unknown closed fault ID"):
            self.load(document)

        document = copy.deepcopy(self.document)
        document["cases"][0]["target_source"] = SOURCE_ROOT
        with self.assertRaisesRegex(core0_common.Core0Error, "wrong exact target source"):
            self.load(document)


class MutantOutcomeTests(unittest.TestCase):
    def classify(self, **changes: object) -> str:
        arguments: dict[str, object] = {
            "compiled": True,
            "linked": True,
            "audited": True,
            "booted": True,
            "protocol_valid": True,
            "oracle": 0x22,
            "observed": 0x11,
            "expected_mutant": 0x11,
        }
        arguments.update(changes)
        return check_foundation.classify_mutant_outcome(**arguments)

    def test_only_complete_pipeline_with_expected_mismatch_is_verified(self) -> None:
        failures = {
            "compiled": "compile-failure",
            "linked": "link-failure",
            "audited": "audit-failure",
            "booted": "boot-failure",
            "protocol_valid": "protocol-failure",
        }
        for field, category in failures.items():
            with self.subTest(field=field):
                self.assertEqual(self.classify(**{field: False}), category)
        self.assertEqual(self.classify(observed=None), "missing-result")
        self.assertEqual(self.classify(observed=0x22), "non-distinguishing-mutant")
        self.assertEqual(self.classify(observed=0x33), "unexpected-wrong-result")
        self.assertEqual(self.classify(), "verified-behavioral-mismatch")

    def test_oracle_equality_never_counts_even_if_declared_as_mutant_value(self) -> None:
        self.assertEqual(
            self.classify(observed=0x22, expected_mutant=0x22),
            "non-distinguishing-mutant",
        )

    def test_negative_fixture_requires_its_intended_diagnostic(self) -> None:
        with self.assertRaisesRegex(
            core0_common.Core0Error, "lacked intended diagnostic fragments"
        ):
            check_foundation.require_intended_rejection(
                returncode=1,
                output="unrelated parser failure",
                required_fragments=("exactly one is required",),
            )
        with self.assertRaisesRegex(core0_common.Core0Error, "unexpectedly passed"):
            check_foundation.require_intended_rejection(
                returncode=0,
                output="exactly one is required",
                required_fragments=("exactly one is required",),
            )
        check_foundation.require_intended_rejection(
            returncode=1,
            output="compiler fault matched 0 instructions; exactly one is required",
            required_fragments=("matched 0 instructions", "exactly one is required"),
        )

    def test_real_stage_wrapper_preserves_distinct_failure_categories(self) -> None:
        cases = (
            ("build", "command failed: lake env lean fixture", "compile-failure"),
            ("build", "command failed: ld.lld image", "link-failure"),
            ("audit", "provenance hash mismatch", "provenance-or-closure-rejection"),
            ("run", "command timed out after 1s", "timeout"),
            ("run", "malformed or truncated target transcript", "protocol-failure"),
            ("run", "QEMU exited with 7", "boot-failure"),
        )
        for stage, diagnostic, category in cases:
            with self.subTest(stage=stage, diagnostic=diagnostic):
                with self.assertRaises(check_foundation.Gate1Failure) as raised:
                    check_foundation._pipeline_stage(
                        stage,
                        "fixture",
                        lambda diagnostic=diagnostic: (_ for _ in ()).throw(
                            core0_common.Core0Error(diagnostic)
                        ),
                    )
                self.assertEqual(raised.exception.category, category)
                self.assertEqual(raised.exception.context, "fixture")


class ProcessFailureTests(unittest.TestCase):
    def test_valid_result_frame_cannot_hide_nonzero_qemu_exit(self) -> None:
        case_id = 0x1234
        transcript = b"LEMMA_CORE0/1\nRESULT:0000000000001234:0000000000000011\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            image = artifacts / "image.elf"
            image.write_bytes(b"not-an-elf")
            (artifacts / "layout.json").write_text(
                json.dumps({"input": {"start": "0x81000000", "size": "0x1000"}}),
                encoding="utf-8",
            )
            process = core0_common.CommandResult(
                ("qemu-system-riscv64",),
                7,
                transcript,
                b"injected failure after result",
                0.01,
            )
            with mock.patch.object(run_core0, "require_tools", return_value={}), mock.patch.object(
                run_core0, "run_bounded", return_value=process
            ):
                with self.assertRaisesRegex(core0_common.Core0Error, "QEMU exited with 7"):
                    run_core0.run_case(
                        root=root,
                        image=image,
                        output_dir=root / "runs",
                        case_id=case_id,
                        args=(0, 7, 7),
                        timeout_seconds=1.0,
                    )
            self.assertFalse((root / "runs" / f"run-{case_id:016x}.json").exists())


class CompilerMutationManifestTests(unittest.TestCase):
    def test_minimal_valid_manifest_is_accepted(self) -> None:
        manifest, mutation = mutation_fixture()
        self.assertIs(
            audit_core0.validate_compiler_mutation_manifest(mutation, manifest), mutation
        )

    def test_forged_or_incomplete_quarantine_fields_are_rejected(self) -> None:
        manifest, mutation = mutation_fixture()
        forged = copy.deepcopy(mutation)
        forged["production_selectable"] = True
        with self.assertRaisesRegex(core0_common.Core0Error, "non-production-selectable"):
            audit_core0.validate_compiler_mutation_manifest(forged, manifest)

        incomplete = copy.deepcopy(mutation)
        del incomplete["after"]
        with self.assertRaisesRegex(core0_common.Core0Error, "fields differ from the schema"):
            audit_core0.validate_compiler_mutation_manifest(incomplete, manifest)

    def test_unknown_closed_id_and_target_mismatches_are_rejected(self) -> None:
        manifest, mutation = mutation_fixture()
        unknown = copy.deepcopy(mutation)
        unknown["fault"] = "not-in-the-closed-set"
        with self.assertRaisesRegex(core0_common.Core0Error, "outside the closed allowlist"):
            audit_core0.validate_compiler_mutation_manifest(unknown, manifest)

        for field, value in (
            ("target_source", SOURCE_ROOT),
            ("target_llvm", "core0_user_forged"),
        ):
            with self.subTest(field=field):
                mismatched = copy.deepcopy(mutation)
                mismatched[field] = value
                with self.assertRaisesRegex(
                    core0_common.Core0Error, "identity is absent or inconsistent"
                ):
                    audit_core0.validate_compiler_mutation_manifest(mismatched, manifest)

        wrong_root = copy.deepcopy(mutation)
        wrong_root["source_root"] = TARGET_SOURCE
        with self.assertRaisesRegex(core0_common.Core0Error, "source root differs"):
            audit_core0.validate_compiler_mutation_manifest(wrong_root, manifest)

    def test_reported_replacement_must_be_the_sole_control_delta(self) -> None:
        _manifest, mutation = mutation_fixture()
        clean = (
            "define i64 @core0_user_Lemma_Examples_Foundation_CompilerFaults_strictLt"
            "(i64 %x, i64 %y) {\n"
            "entry:\n"
            "  %cmp = icmp ult i64 %x, %y\n"
            "  ret i64 34\n"
            "}\n"
        )
        mutant = clean.replace(
            "  %cmp = icmp ult i64 %x, %y",
            "  %cmp = icmp ule i64 %x, %y",
        )
        audit_core0.validate_mutant_control_delta(mutation, mutant, clean)
        with self.assertRaisesRegex(core0_common.Core0Error, "unreported"):
            audit_core0.validate_mutant_control_delta(
                mutation,
                mutant.replace("  ret i64 34", "  ret i64 17"),
                clean,
            )


class QuarantinePolicyTests(unittest.TestCase):
    def test_audit_policy_selection_is_closed(self) -> None:
        for policy in audit_core0.AUDIT_POLICIES:
            with self.subTest(policy=policy):
                self.assertEqual(audit_core0._validate_audit_policy(policy), policy)
        with self.assertRaisesRegex(core0_common.Core0Error, "unknown Core0 audit policy"):
            audit_core0._validate_audit_policy("forged-policy")

    def test_build_artifact_policy_combinations_are_closed(self) -> None:
        build_core0._validate_artifact_request("release", None)
        build_core0._validate_artifact_request("test-compiler-control", None)
        build_core0._validate_artifact_request(
            "test-compiler-mutant", build_core0.COMPILER_FAULT_MANIFEST
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "forbid"):
            build_core0._validate_artifact_request(
                "release", build_core0.COMPILER_FAULT_MANIFEST
            )
        with self.assertRaisesRegex(core0_common.Core0Error, "require"):
            build_core0._validate_artifact_request("test-compiler-mutant", None)
        with self.assertRaisesRegex(core0_common.Core0Error, "unsupported artifact category"):
            build_core0._validate_artifact_request("forged-policy", None)

    def test_production_build_cli_rejects_fault_selectors_before_tool_checks(self) -> None:
        attempts = (
            ["build_core0.py", "--artifact-category", "test-compiler-mutant"],
            ["build_core0.py", "--compiler-fault", "ult-as-ule"],
        )
        for argv in attempts:
            with self.subTest(option=argv[1]), mock.patch.object(sys, "argv", argv), mock.patch.object(
                build_core0, "require_tools"
            ) as require_tools, redirect_stderr(io.StringIO()) as stderr:
                with self.assertRaises(SystemExit) as raised:
                    build_core0.main()
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("unrecognized arguments", stderr.getvalue())
                require_tools.assert_not_called()


if __name__ == "__main__":
    unittest.main()
