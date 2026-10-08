"""Fail-closed unit tests for the host-only Core0 harness.

These tests do not substitute for a target build or QEMU differential run.  They
exercise failure paths whose accidental success could otherwise make that evidence
misleading.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_core0  # noqa: E402
import core0_common  # noqa: E402
import run_core0  # noqa: E402


VALID_CASE = 0x0123456789ABCDEF
VALID_RESULT = 0xFEDCBA9876543210
VALID_TRANSCRIPT = (
    b"LEMMA_CORE0/1\n"
    b"RESULT:0123456789abcdef:fedcba9876543210\n"
)


class TranscriptTests(unittest.TestCase):
    def test_complete_exact_frame_is_accepted(self) -> None:
        self.assertEqual(
            run_core0.validate_transcript(VALID_TRANSCRIPT, VALID_CASE),
            VALID_RESULT,
        )

    def test_truncated_frames_are_rejected(self) -> None:
        truncations = (
            b"",
            b"LEMMA_CORE0/1",
            b"LEMMA_CORE0/1\n",
            b"LEMMA_CORE0/1\nRESULT:",
            VALID_TRANSCRIPT[:-1],
            VALID_TRANSCRIPT[:-8],
        )
        for transcript in truncations:
            with self.subTest(transcript=transcript):
                with self.assertRaisesRegex(
                    core0_common.Core0Error, "malformed or truncated"
                ):
                    run_core0.validate_transcript(transcript, VALID_CASE)

    def test_noisy_or_duplicate_output_is_rejected(self) -> None:
        noisy = (
            b"reset\n" + VALID_TRANSCRIPT,
            VALID_TRANSCRIPT + b"extra",
            VALID_TRANSCRIPT + b"\n",
            VALID_TRANSCRIPT + VALID_TRANSCRIPT,
            VALID_TRANSCRIPT.replace(b"\n", b"\r\n"),
            VALID_TRANSCRIPT.upper(),
        )
        for transcript in noisy:
            with self.subTest(transcript=transcript):
                with self.assertRaises(core0_common.Core0Error):
                    run_core0.validate_transcript(transcript, VALID_CASE)

    def test_wrong_case_identifier_is_rejected(self) -> None:
        with self.assertRaisesRegex(core0_common.Core0Error, "target returned case id"):
            run_core0.validate_transcript(VALID_TRANSCRIPT, VALID_CASE + 1)


class BoundedProcessTests(unittest.TestCase):
    def test_timeout_kills_and_reaps_direct_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pid_file = directory / "pid"
            program = (
                "import os, pathlib, sys, time; "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "time.sleep(30)"
            )
            with self.assertRaisesRegex(core0_common.Core0Error, "timed out"):
                core0_common.run_bounded(
                    [sys.executable, "-c", program, str(pid_file)],
                    cwd=directory,
                    timeout_seconds=1.0,
                )
            self.assertTrue(pid_file.is_file(), "timed process never started")
            pid = int(pid_file.read_text(encoding="ascii"))
            # run_bounded calls communicate() after SIGKILL; the direct child must
            # therefore be absent from /proc rather than left as a zombie.
            for _ in range(20):
                if not Path(f"/proc/{pid}").exists():
                    break
                time.sleep(0.01)
            self.assertFalse(Path(f"/proc/{pid}").exists(), f"process {pid} was not reaped")

    def test_nonzero_exit_is_not_checked_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = core0_common.run_bounded(
                [sys.executable, "-c", "raise SystemExit(7)"],
                cwd=directory,
                timeout_seconds=5.0,
            )
            self.assertEqual(result.returncode, 7)
            with self.assertRaisesRegex(core0_common.Core0Error, "exit 7"):
                core0_common.checked(
                    [sys.executable, "-c", "raise SystemExit(7)"],
                    cwd=directory,
                    timeout_seconds=5.0,
                )


class RunCaseFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.image = self.artifacts / "image.elf"
        self.image.write_bytes(b"not-an-elf")
        (self.artifacts / "layout.json").write_text(
            json.dumps(
                {
                    "input": {
                        "start": "0x81000000",
                        "size": "0x1000",
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_nonzero_qemu_exit_is_rejected(self) -> None:
        failed = core0_common.CommandResult(
            ("qemu-system-riscv64",),
            9,
            VALID_TRANSCRIPT,
            b"injected qemu failure",
            0.01,
        )
        with mock.patch.object(run_core0, "require_tools", return_value={}), mock.patch.object(
            run_core0, "run_bounded", return_value=failed
        ):
            with self.assertRaisesRegex(core0_common.Core0Error, "QEMU exited with 9"):
                run_core0.run_case(
                    root=self.root,
                    image=self.image,
                    output_dir=self.root / "runs",
                    case_id=VALID_CASE,
                    args=(1, 2, 3),
                    timeout_seconds=1.0,
                )
        self.assertFalse((self.root / "runs" / f"run-{VALID_CASE:016x}.json").exists())

    def test_qemu_timeout_is_rejected_without_a_run_record(self) -> None:
        with mock.patch.object(run_core0, "require_tools", return_value={}), mock.patch.object(
            run_core0,
            "run_bounded",
            side_effect=core0_common.Core0Error("command timed out after 1.000s"),
        ):
            with self.assertRaisesRegex(core0_common.Core0Error, "timed out"):
                run_core0.run_case(
                    root=self.root,
                    image=self.image,
                    output_dir=self.root / "runs",
                    case_id=VALID_CASE,
                    args=(1, 2, 3),
                    timeout_seconds=1.0,
                )
        self.assertFalse((self.root / "runs" / f"run-{VALID_CASE:016x}.json").exists())

    def test_missing_layout_manifest_is_rejected(self) -> None:
        (self.artifacts / "layout.json").unlink()
        with mock.patch.object(run_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "required JSON file is missing"):
                run_core0.run_case(
                    root=self.root,
                    image=self.image,
                    output_dir=self.root / "runs",
                    case_id=VALID_CASE,
                    args=(1, 2, 3),
                    timeout_seconds=1.0,
                )


class FailClosedInputTests(unittest.TestCase):
    def test_missing_tool_is_an_error(self) -> None:
        with mock.patch.object(core0_common.shutil, "which", return_value=None):
            with self.assertRaisesRegex(core0_common.Core0Error, "missing required tools"):
                core0_common.require_tools(("tool-that-does-not-exist",))

    def test_missing_and_malformed_json_are_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with self.assertRaisesRegex(core0_common.Core0Error, "is missing"):
                core0_common.load_json(directory / "missing.json")
            malformed = directory / "malformed.json"
            malformed.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(core0_common.Core0Error, "invalid JSON"):
                core0_common.load_json(malformed)

    def test_empty_case_corpus_cannot_report_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary) / "must-not-be-created"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "check_core0.py"),
                    "--cases",
                    "tests/core0/fixtures/empty-cases.json",
                    "--work-dir",
                    str(work),
                ],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CORE0 CHECK FAIL: case corpus is empty", result.stderr)
            self.assertNotIn("CORE0 CHECK PASS", result.stdout + result.stderr)
            self.assertFalse(work.exists(), "empty corpus created build/evidence output")


class CorpusFixtureTests(unittest.TestCase):
    def test_positive_corpus_is_nonempty_well_formed_and_covers_boundaries(self) -> None:
        corpus = core0_common.load_json(ROOT / "tests/core0/cases.json")
        self.assertIsInstance(corpus, dict)
        self.assertEqual(corpus.get("schema_version"), 1)
        self.assertEqual(corpus.get("root"), "Lemma.Examples.Core0.Positive.entry")
        self.assertIsInstance(corpus.get("seed"), str)
        cases = corpus.get("cases")
        self.assertIsInstance(cases, list)
        self.assertTrue(cases, "the checked-in target corpus must not be empty")

        names: set[str] = set()
        identifiers: set[int] = set()
        coverage: set[str] = set()
        for case in cases:
            self.assertIsInstance(case, dict)
            name = case.get("name")
            self.assertIsInstance(name, str)
            self.assertTrue(name)
            self.assertNotIn(name, names)
            names.add(name)
            case_id = int(case.get("case_id"), 0)
            self.assertGreaterEqual(case_id, 0)
            self.assertLessEqual(case_id, 0xFFFFFFFFFFFFFFFF)
            self.assertNotIn(case_id, identifiers)
            identifiers.add(case_id)
            arguments = case.get("args")
            self.assertIsInstance(arguments, list)
            self.assertEqual(len(arguments), 3)
            for argument in arguments:
                value = int(argument, 0)
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, 0xFFFFFFFFFFFFFFFF)
            labels = case.get("covers")
            self.assertIsInstance(labels, list)
            coverage.update(labels)

        self.assertTrue(
            {
                "zero",
                "uint64-maximum",
                "uint64-wraparound",
                "uint32-truncation",
                "entry-then",
                "entry-else",
                "direct-call",
                "runtime-input",
                "uart-output",
            }
            <= coverage
        )

    def test_rejection_manifest_is_nonempty_and_points_to_real_fixtures(self) -> None:
        manifest = core0_common.load_json(ROOT / "tests/core0/rejections.json")
        self.assertIsInstance(manifest, dict)
        self.assertEqual(manifest.get("schema_version"), 1)
        cases = manifest.get("cases")
        self.assertIsInstance(cases, list)
        self.assertTrue(cases, "the rejection corpus must not be empty")
        paths: set[str] = set()
        for case in cases:
            self.assertIsInstance(case, dict)
            path = case.get("path")
            self.assertIsInstance(path, str)
            self.assertNotIn(path, paths)
            paths.add(path)
            self.assertTrue((ROOT / path).is_file(), path)
            fragments = case.get("required_fragments")
            self.assertIsInstance(fragments, list)
            self.assertTrue(fragments)
            self.assertTrue(all(isinstance(fragment, str) and fragment for fragment in fragments))


class AuditRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.directory = self.root / "audit"
        self.directory.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def populate_artifacts(self, ir: str | None = None) -> None:
        for name in audit_core0.REQUIRED_ARTIFACTS:
            if name != "provenance.json":
                (self.directory / name).write_text("fixture\n", encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "contract_version": "core0-v0.1",
            "root": "Fixture.entry",
            "root_llvm": "core0_user_0",
            "root_abi": {"args": ["u64", "u64", "u64"], "result": "u64"},
            "functions": [
                {
                    "source": "Fixture.entry",
                    "llvm": "core0_user_0",
                    "signature": {"args": ["u64", "u64", "u64"], "result": "u64"},
                    "dependencies": [],
                    "body": "(lit u64 0)",
                }
            ],
            "used_primitives": [],
            "machine_primitives": audit_core0.EXPECTED_MACHINE_PRIMITIVES,
        }
        (self.directory / "core0-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.directory / "core0-normalized.txt").write_text(
            "contract=core0-v0.1\n"
            "root=Fixture.entry\n"
            "function=Fixture.entry;signature=(u64,u64,u64)->u64;"
            "deps=[];body=(lit u64 0)\n",
            encoding="utf-8",
        )
        (self.directory / "symbols.txt").write_text(
            "source=Fixture.entry;llvm=core0_user_0\n", encoding="utf-8"
        )
        if ir is not None:
            (self.directory / "program.ll").write_text(ir, encoding="utf-8")
            (self.directory / "program.opt.ll").write_text(ir, encoding="utf-8")
        linked = []
        details = {
            "startup.o": {
                "kind": "lean-structured-startup",
                "generation_command": audit_core0.EXPECTED_STARTUP_COMMAND,
                "source": "startup.S generated by Lemma.Machine.Primitives",
                "purpose": "M-mode entry, BSS clearing, a0/a1 boot-input preservation, and I/O fence",
            },
            "program.o": {
                "kind": "core0-llvm",
                "generation_command": audit_core0.expected_program_command("O0"),
                "source": "program.ll generated from the checked elaborated Core0 program",
                "purpose": "compiled Core0 application and freestanding machine harness",
            },
        }
        for name, detail in details.items():
            linked.append(
                {
                    "path": name,
                    **detail,
                    "sha256": core0_common.sha256(self.directory / name),
                }
            )
        source = self.root / "source.lean"
        source.write_text("def fixture : UInt64 := 0\n", encoding="utf-8")
        (self.directory / "provenance.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_commit": "0" * 40,
                    "dirty_tree": False,
                    "dirty_paths": [],
                    "optimization": "O0",
                    "source_inputs": [
                        {
                            "path": "source.lean",
                            "sha256": core0_common.sha256(source),
                        }
                    ],
                    "linked_inputs": linked,
                    "link_command": audit_core0.EXPECTED_LINK_COMMAND,
                    "commands": [
                        {"argv": audit_core0.expected_program_command("O0")},
                        {"argv": audit_core0.EXPECTED_STARTUP_COMMAND},
                        {"argv": audit_core0.EXPECTED_LINK_COMMAND},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_missing_target_manifest_fails_before_tool_inspection(self) -> None:
        self.populate_artifacts()
        (self.directory / "core0-manifest.json").unlink()
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "missing audit artifacts"):
                audit_core0.audit(self.directory, self.root)

    def test_malformed_target_manifest_fails_before_tool_inspection(self) -> None:
        self.populate_artifacts()
        (self.directory / "core0-manifest.json").write_text("{", encoding="utf-8")
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "invalid JSON"):
                audit_core0.audit(self.directory, self.root)

    def test_target_manifest_without_checked_body_is_rejected(self) -> None:
        self.populate_artifacts()
        manifest = json.loads((self.directory / "core0-manifest.json").read_text())
        del manifest["functions"][0]["body"]
        (self.directory / "core0-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "fields differ from the schema"):
                audit_core0.audit(self.directory, self.root)

    def test_untracked_linked_object_is_rejected(self) -> None:
        self.populate_artifacts()
        foreign = self.directory / "foreign-runtime.o"
        foreign.write_bytes(b"statically resolved foreign object")
        provenance = json.loads((self.directory / "provenance.json").read_text())
        provenance["linked_inputs"].append(
            {
                "path": foreign.name,
                "kind": "foreign-runtime",
                "sha256": core0_common.sha256(foreign),
            }
        )
        (self.directory / "provenance.json").write_text(
            json.dumps(provenance), encoding="utf-8"
        )
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "exactly the two linked objects"):
                audit_core0.audit(self.directory, self.root)

    def test_tampered_source_provenance_is_rejected(self) -> None:
        self.populate_artifacts()
        provenance = json.loads((self.directory / "provenance.json").read_text())
        provenance["source_inputs"][0]["sha256"] = "f" * 64
        (self.directory / "provenance.json").write_text(
            json.dumps(provenance), encoding="utf-8"
        )
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "source-input hash mismatch"):
                audit_core0.audit(self.directory, self.root)

    def test_incomplete_object_provenance_is_rejected(self) -> None:
        self.populate_artifacts()
        provenance = json.loads((self.directory / "provenance.json").read_text())
        del provenance["linked_inputs"][0]["generation_command"]
        (self.directory / "provenance.json").write_text(
            json.dumps(provenance), encoding="utf-8"
        )
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(
                core0_common.Core0Error, "lacks generation/source/purpose provenance"
            ):
                audit_core0.audit(self.directory, self.root)

    def test_fully_defined_forbidden_runtime_is_rejected(self) -> None:
        fixture = (ROOT / "tests/core0/fixtures/foreign-runtime.ll").read_text(
            encoding="utf-8"
        )
        fixture = 'source_filename = "Fixture.entry"\n' + fixture
        definitions, declarations, calls = audit_core0.parse_definitions_and_calls(fixture)
        self.assertEqual(declarations, {"core0_io_fence"})
        self.assertIn("lemma_forbidden_foreign_runtime", definitions)
        self.assertIn("lean_alloc_object", definitions)
        self.assertIn("lemma_forbidden_foreign_runtime", calls)
        self.populate_artifacts(fixture)
        with mock.patch.object(audit_core0, "require_tools", return_value={}):
            with self.assertRaisesRegex(core0_common.Core0Error, "forbidden runtime symbols"):
                audit_core0.audit(self.directory, self.root)


if __name__ == "__main__":
    unittest.main()
