#!/usr/bin/env python3
"""Gate 10 qualification orchestration and fail-closed evidence tests."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0
import build_monitor
import gate9_corpus as corpus
import qualify_foundation as qualifier
import run_monitor_session as runner
from core0_common import CommandResult, Core0Error, sha256, write_json


class FoundationQualificationTests(unittest.TestCase):
    def test_reproducibility_catalog_and_provenance_closure_are_exact(self):
        self.assertEqual(
            qualifier.DETERMINISTIC_ARTIFACTS,
            (
                *runner.SOURCE_ARTIFACTS,
                "program.opt.ll",
                "program.o",
                "startup.o",
                "image.elf",
                "image.map",
                "platform.dtb",
                "platform.dts",
            ),
        )
        self.assertEqual(len(qualifier.DETERMINISTIC_ARTIFACTS), 16)
        self.assertIn(Path("scripts/qualify_foundation.py"), build_monitor.HOST_INPUTS)
        source = (ROOT / "scripts/audit_core0.py").read_text(encoding="utf-8")
        self.assertIn('"scripts/qualify_foundation.py"', source)

    def test_normalized_build_and_audit_only_hide_output_bound_fields(self):
        build = {
            "output_directory": "build/first",
            "artifacts": {"program.ll": "1", "provenance.json": "2"},
            "status": "PASS",
        }
        audit = {
            "directory": "build/first",
            "hashes": {"program.ll": "1", "provenance.json": "2"},
            "status": "PASS",
        }
        normalized_build = qualifier._normal_build(build)
        normalized_audit = qualifier._normal_audit(audit)
        self.assertEqual(build["output_directory"], "build/first")
        self.assertEqual(audit["directory"], "build/first")
        self.assertEqual(normalized_build["output_directory"], "$OUTPUT")
        self.assertEqual(
            normalized_build["artifacts"]["provenance.json"],
            "$INTENTIONAL_PROVENANCE_DIGEST",
        )
        self.assertEqual(normalized_audit["directory"], "$OUTPUT")
        self.assertEqual(
            normalized_audit["hashes"]["provenance.json"],
            "$INTENTIONAL_PROVENANCE_DIGEST",
        )

    @staticmethod
    def _command(cwd, *, elapsed=1.0, stdout="first", stderr=""):
        return {
            "argv": ["tool", "input", "-o", "output"],
            "cwd": cwd,
            "returncode": 0,
            "elapsed_seconds": elapsed,
            "stdout": stdout,
            "stderr": stderr,
        }

    def test_provenance_comparison_records_only_observational_differences(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "build/input/O0"
            rebuilt = root / "build/qualification/rebuild/O0"
            first = {
                "schema_version": 2,
                "source_commit": "a" * 40,
                "commands": [self._command("build/input/O0")],
            }
            second = {
                "schema_version": 2,
                "source_commit": "a" * 40,
                "commands": [
                    self._command(
                        "build/qualification/rebuild/O0",
                        elapsed=2.0,
                        stdout="second",
                    )
                ],
            }
            result = qualifier._compare_provenance(
                first, second, baseline, rebuilt, root
            )
            self.assertTrue(result["stable_fields_equal"])
            self.assertTrue(result["command_structure_equal"])
            self.assertEqual(
                len(result["intentional_command_observation_differences"]), 1
            )
            second["source_commit"] = "b" * 40
            with self.assertRaisesRegex(Core0Error, "source_commit"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            second["source_commit"] = "a" * 40
            second["commands"][0]["argv"] = ["different"]
            with self.assertRaisesRegex(Core0Error, "command structure"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            second["commands"][0] = self._command(
                "build/qualification/rebuild/O0"
            )
            second["commands"][0]["returncode"] = False
            with self.assertRaisesRegex(Core0Error, "return code"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_gate9_stress_mode_must_be_exact_and_boolean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            gate9.mkdir(parents=True)
            base = {key: None for key in qualifier.EXPECTED_GATE9_KEYS}
            base.update(
                schema_version=1,
                status="PASS",
                gate=9,
                profile=corpus.PROFILE,
                artifact_category=corpus.ARTIFACT_CATEGORY,
                test_abi=corpus.TEST_ABI,
            )
            for stress in ({"enabled": 1}, {"enabled": True}):
                with self.subTest(stress=stress):
                    base["stress"] = stress
                    write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, base)
                    with self.assertRaisesRegex(Core0Error, "stress"):
                        qualifier.validate_gate9_bundle(
                            root=root,
                            gate9_directory=gate9,
                            source={"commit": "a" * 40},
                        )
            base["schema_version"] = True
            base["stress"] = corpus.stress_manifest(stress=False)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, base)
            with self.assertRaisesRegex(Core0Error, "identity"):
                qualifier.validate_gate9_bundle(
                    root=root,
                    gate9_directory=gate9,
                    source={"commit": "a" * 40},
                )

    def test_probe_literal_counts_and_return_code_are_strict_integers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            source = root / "examples/foundation/MonitorPolicyProbes.lean"
            log = gate9 / "probes/monitor-policy-frontend.txt"
            source.parent.mkdir(parents=True)
            log.parent.mkdir(parents=True)
            source.write_text("#guard true\n" * 50, encoding="utf-8")
            log.write_text(
                "Monitor genuine v0.7 frontend/lowering passed: 54 scalar functions, "
                "85 Action functions, 7 timer/2 trap/4 UART operations\n"
                + qualifier.gate9_checker.POLICY_MARKER + "\n",
                encoding="utf-8",
            )
            probe = {
                "source": str(source.relative_to(root)),
                "source_sha256": sha256(source),
                "argv": ["lake", "env", "lean", str(source.relative_to(root))],
                "returncode": 0,
                "policy_probes": 50,
                "frontend_lowering": 1,
                "log": str(log.relative_to(root)),
                "log_sha256": sha256(log),
                "scope": "direct source predicates/encoding/frontend observations, not hardware or compiler proof",
            }
            for name, value in (
                ("returncode", False), ("frontend_lowering", True),
                ("policy_probes", True),
            ):
                with self.subTest(name=name):
                    changed = dict(probe)
                    changed[name] = value
                    with mock.patch.object(
                        qualifier.gate8_checker, "_load_rejections", return_value=()
                    ):
                        with self.assertRaisesRegex(Core0Error, "probe identity"):
                            qualifier._validate_probe_and_rejections(
                                {"source_probes": changed, "source_rejections": []},
                                root,
                                gate9,
                            )

    def test_missing_retained_raw_file_is_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "build/image"
            run = root / "build/run"
            output.mkdir(parents=True)
            run.mkdir(parents=True)
            (output / "image.elf").write_bytes(b"image")
            write_json(output / "audit.json", {"audit": "bound"})
            scenario = corpus.SCENARIOS[0]
            (run / "sent.bin").write_bytes(b"")
            (run / "stderr.bin").write_bytes(b"")
            binding = {"audit_sha256": sha256(output / "audit.json")}
            machine = {"executable_ranges": [[0x80000000, 0x80010000]], "symbols": {}}
            record = {
                "schema_version": 1,
                "status": "PASS",
                "profile": corpus.PROFILE,
                "artifact_category": corpus.ARTIFACT_CATEGORY,
                "test_abi": corpus.TEST_ABI,
                "scenario": scenario.name,
                "image": str((output / "image.elf").resolve()),
                "image_sha256": sha256(output / "image.elf"),
                "binding": binding,
                "machine": machine,
                "pid": 100,
                "returncode": scenario.expected_exit,
                "expected_exit": scenario.expected_exit,
                "argv": list(runner.qemu_argv(output / "image.elf")),
                "timeout_seconds": 20,
                "elapsed_seconds": 1,
                "started_at": "2026-10-08T00:00:00+00:00",
                "finished_at": "2026-10-08T00:00:01+00:00",
                "ready_observed_before_input": True,
                "stdin_open_until_exit": True,
                "semantic_validation_after_exit": True,
                "single_pid": True,
                "single_elf": True,
                "first_input_after_ready": True,
                "outcome": "verified-monitor-session",
                "responses": [],
                "summary": {},
                "raw_artifacts": {
                    "sent.bin": sha256(run / "sent.bin"),
                    "received.bin": "0" * 64,
                    "stderr.bin": sha256(run / "stderr.bin"),
                },
            }
            write_json(run / runner.RESULT_FILE, record)
            with mock.patch.object(runner, "validate_transcript") as replay, \
                 mock.patch.object(runner, "validate_image_binding", return_value=binding), \
                 mock.patch.object(runner, "image_machine_info", return_value=machine):
                with self.assertRaisesRegex(Core0Error, "missing/stale"):
                    qualifier._revalidate_run(
                        root=root,
                        output=output,
                        run_directory=run,
                        scenario=scenario,
                        expected_record=record,
                    )
                replay.assert_not_called()

    def test_invalid_timeout_removes_stale_pass_before_any_source_or_build_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            work.mkdir(parents=True)
            write_json(work / qualifier.RESULT_FILE, {"status": "PASS"})
            with mock.patch.object(qualifier, "_source_identity") as source:
                with self.assertRaisesRegex(
                    qualifier.QualificationFailure, "harness-input-failure.*build"
                ):
                    qualifier.qualify_foundation(
                        root=root,
                        gate9_directory=gate9,
                        work=work,
                        clean=False,
                        timeout_seconds=float("nan"),
                        qemu_timeout=20,
                    )
                source.assert_not_called()
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            self.assertFalse((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_malformed_cli_removes_stale_pass_when_work_directory_is_known(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            work.mkdir(parents=True)
            write_json(work / qualifier.RESULT_FILE, {"status": "PASS"})
            argv = [
                "qualify_foundation.py", "--gate9-dir", "build/gate9",
                "--work-dir", "build/qualification", "--timeout", "not-a-number",
            ]
            with (
                mock.patch.object(qualifier, "repo_root", return_value=root),
                mock.patch.object(sys, "argv", argv),
                mock.patch("sys.stderr"),
            ):
                self.assertEqual(qualifier.main(), 2)
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            failure = json.loads((work / qualifier.FAILURE_FILE).read_text())
            self.assertEqual((failure["status"], failure["gate"]), ("FAIL", 10))

    def test_help_is_side_effect_free_even_when_work_directory_is_named(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            work.mkdir(parents=True)
            result = b'{"status":"PASS"}\n'
            failure = b'{"status":"OLD"}\n'
            (work / qualifier.RESULT_FILE).write_bytes(result)
            (work / qualifier.FAILURE_FILE).write_bytes(failure)
            argv = [
                "qualify_foundation.py", "--help", "--work-dir",
                "build/qualification",
            ]
            with (
                mock.patch.object(qualifier, "repo_root", return_value=root),
                mock.patch.object(sys, "argv", argv),
                mock.patch("sys.stdout"),
            ):
                self.assertEqual(qualifier.main(), 0)
            self.assertEqual((work / qualifier.RESULT_FILE).read_bytes(), result)
            self.assertEqual((work / qualifier.FAILURE_FILE).read_bytes(), failure)

    def test_success_is_published_only_after_final_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, {"status": "PASS"})
            for optimization in qualifier.PROFILES:
                directory = gate9 / optimization
                directory.mkdir()
                for name in ("build.json", "audit.json", "provenance.json"):
                    write_json(directory / name, {"name": name})
                (directory / "image.elf").write_bytes(optimization.encode())
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            gate9_result = {
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            stale = [
                {"id": "phase9-stale-pass", "passed": True},
                {"id": "runner-stale-pass", "passed": True},
            ]
            failures = [
                {"id": "missing-program-object", "passed": True},
                {"id": "tampered-program-ir", "passed": True},
                {"id": "missing-raw-evidence", "passed": True},
            ]
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=gate9_result
                ),
                mock.patch.object(
                    qualifier,
                    "rebuild_and_compare",
                    return_value=({"O0": {}, "O2": {}}, []),
                ),
                mock.patch.object(
                    qualifier, "stale_pass_experiments", return_value=(stale, [])
                ),
                mock.patch.object(
                    qualifier,
                    "artifact_failure_experiments",
                    return_value=(failures, []),
                ),
                mock.patch.object(qualifier, "validate_qualification_report") as validate,
            ):
                report = qualifier.qualify_foundation(
                    root=root,
                    gate9_directory=gate9,
                    work=work,
                    clean=True,
                    timeout_seconds=1,
                    qemu_timeout=1,
                )
            validate.assert_called_once()
            self.assertEqual(report, json.loads((work / qualifier.RESULT_FILE).read_text()))
            self.assertFalse((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_validation_failure_never_publishes_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, {"status": "PASS"})
            for optimization in qualifier.PROFILES:
                directory = gate9 / optimization
                directory.mkdir()
                for name in ("build.json", "audit.json", "provenance.json"):
                    write_json(directory / name, {"name": name})
                (directory / "image.elf").write_bytes(optimization.encode())
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            gate9_result = {
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=gate9_result
                ),
                mock.patch.object(
                    qualifier,
                    "rebuild_and_compare",
                    return_value=({"O0": {}, "O2": {}}, []),
                ),
                mock.patch.object(
                    qualifier,
                    "stale_pass_experiments",
                    return_value=([{"id": "phase9-stale-pass"}, {"id": "runner-stale-pass"}], []),
                ),
                mock.patch.object(
                    qualifier,
                    "artifact_failure_experiments",
                    return_value=([{"id": "missing-program-object"}], []),
                ),
                mock.patch.object(
                    qualifier,
                    "validate_qualification_report",
                    side_effect=Core0Error("final evidence changed"),
                ),
            ):
                with self.assertRaisesRegex(Core0Error, "final evidence changed"):
                    qualifier.qualify_foundation(
                        root=root,
                        gate9_directory=gate9,
                        work=work,
                        clean=True,
                        timeout_seconds=1,
                        qemu_timeout=1,
                    )
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            self.assertTrue((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_final_validator_rejects_missing_mandatory_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            gate9 = root / "build/gate9"
            work.mkdir(parents=True)
            gate9.mkdir(parents=True)
            reproducibility = {}
            for optimization in qualifier.PROFILES:
                baseline = gate9 / optimization
                rebuilt = work / "rebuild" / optimization
                baseline.mkdir(parents=True)
                rebuilt.mkdir(parents=True)
                comparisons = {}
                for name in qualifier.DETERMINISTIC_ARTIFACTS:
                    first, second = baseline / name, rebuilt / name
                    first.write_bytes(name.encode())
                    second.write_bytes(name.encode())
                    comparisons[name] = {
                        "baseline_sha256": sha256(first),
                        "rebuilt_sha256": sha256(second),
                        "bytes": first.stat().st_size,
                        "identical": True,
                    }
                reproducibility[optimization] = {
                    "rebuilt_directory": str(rebuilt.relative_to(root)),
                    "binding": {},
                    "deterministic_artifacts": comparisons,
                    "image_map_inspected_and_identical": True,
                    "metadata": {},
                }
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            report = {
                "schema_version": 1,
                "status": "PASS",
                "task": "002-machine-foundation",
                "gate": 10,
                "started_at": "start",
                "finished_at": "finish",
                "source": source,
                "invocation": {
                    "gate9_directory": "build/gate9",
                    "work_directory": "build/qualification",
                    "clean": True,
                    "timeout_seconds": 1,
                    "qemu_timeout": 1,
                    "stress_selected_by_gate9_report": False,
                },
                "gate9_input": {"bound": True},
                "reproducibility": reproducibility,
                "failure_experiments": [
                    {
                        "id": "phase9-stale-pass", "passed": True,
                        "old_pass_sha256": "0" * 64, "canonical_pass_absent": True,
                        "observed_category": "harness-input-failure",
                        "failure_report": {}, "retained_old_report": {}, "command": {},
                    },
                    {
                        "id": "runner-stale-pass", "passed": True,
                        "old_pass_sha256": "0" * 64, "new_failure_sha256": "1" * 64,
                        "observed_category": "image-or-harness-rejection",
                        "failure_report": {}, "retained_old_report": {},
                        "raw_artifacts": {}, "command": {},
                    },
                    {
                        "id": "missing-program-object", "passed": True,
                        "accepted_image_modified": False, "target": "program.o",
                        "mode": "missing", "original_sha256": "0" * 64,
                        "changed_sha256": None, "canonical_audit_absent": True,
                        "command": {}, "record": {},
                    },
                    {
                        "id": "tampered-program-ir", "passed": True,
                        "accepted_image_modified": False, "target": "program.ll",
                        "mode": "tamper", "original_sha256": "0" * 64,
                        "changed_sha256": "1" * 64, "canonical_audit_absent": True,
                        "command": {}, "record": {},
                    },
                    {
                        "id": "missing-raw-evidence", "passed": True,
                        "removed": "received.bin", "removed_sha256": "0" * 64,
                        "canonical_pass_absent": True, "diagnostic": "missing",
                        "record": {}, "retained_old_report": {},
                    },
                ],
                "artifacts": [
                    {
                        "path": f"build/qualification/missing-{index}.bin",
                        "bytes": 1,
                        "sha256": "0" * 64,
                        "role": f"missing evidence {index}",
                    }
                    for index in range(66)
                ],
                "counts": {
                    "replayed_gate9_sessions": 18,
                    "normal_sessions": 18,
                    "stress_sessions": 0,
                    "reproducible_profiles": 2,
                    "deterministic_artifacts_per_profile": 16,
                    "failure_path_experiments": 5,
                },
                "limitations": [],
            }
            fresh = {
                "bound": True,
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            report["gate9_input"] = fresh
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=fresh
                ),
                mock.patch.object(
                    runner, "validate_image_binding", return_value={}
                ),
                mock.patch.object(
                    qualifier, "_reproducibility_metadata", return_value={}
                ),
            ):
                with self.assertRaisesRegex(Core0Error, "missing/stale"):
                    qualifier.validate_qualification_report(
                        report, root=root, work=work
                    )

    def test_audit_experiments_use_the_closed_monitor_policy(self):
        source = (ROOT / "scripts/qualify_foundation.py").read_text(encoding="utf-8")
        self.assertIn(
            '"--policy", audit_core0.TEST_MONITOR_IMAGE_POLICY', source
        )
        self.assertEqual(
            audit_core0.TEST_MONITOR_IMAGE_POLICY, corpus.ARTIFACT_CATEGORY
        )


if __name__ == "__main__":
    unittest.main()
