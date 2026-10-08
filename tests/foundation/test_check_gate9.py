#!/usr/bin/env python3
"""Monitor acceptance orchestration, stale PASS, and retained-evidence checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_foundation_gate9 as checker
import gate9_corpus as corpus
import run_monitor_session as runner
from core0_common import CommandResult, Core0Error, sha256, write_json


class MonitorCheckerTests(unittest.TestCase):
    @staticmethod
    def completion_profiles(stress=False):
        profiles = {}
        for optimization in ("O0", "O2"):
            records = []
            for scenario in corpus.selected_scenarios(stress=stress):
                record = {"schema_version": 1, "scenario": scenario.name, "status": "PASS", "expected_exit": scenario.expected_exit,
                    "returncode": scenario.expected_exit, "responses": [{} for _ in scenario.requests]}
                if scenario.requests:
                    record["summary"] = {"handled_requests": len(scenario.requests), "observed_hardware_irqs": 0,
                        "synchronous_recoveries": 0, "records_checked": 0}
                if scenario.integration:
                    record["summary"].update(observed_hardware_irqs=338, synchronous_recoveries=5,
                        records_checked=48, hardware_work_commands=3, observed_overflow=True, observed_ring_wrap=True)
                if scenario.name == "active-truncated-payload":
                    record["outcome"] = "verified-terminal-rejection"
                    record["summary"].update(active_at_terminal_input=True, observed_hardware_irqs=1)
                records.append(record)
            profiles[optimization] = {"targets": records}
        return profiles

    def test_stress_completion_separates_normal_and_extra_counts(self):
        total, normal, stress = checker._completion_counts(self.completion_profiles())
        self.assertEqual(total["fresh_qemu_boots"], 18)
        self.assertEqual(total, normal)
        self.assertTrue(all(value == 0 for value in stress.values()))
        total, normal, stress = checker._completion_counts(self.completion_profiles(True), stress=True)
        self.assertEqual((total["fresh_qemu_boots"], normal["fresh_qemu_boots"], stress["fresh_qemu_boots"]), (26, 18, 8))
        self.assertEqual((total["mixed_sessions"], normal["mixed_sessions"], stress["mixed_sessions"]), (12, 4, 8))
        self.assertEqual(normal["handled_requests"], 1598)
        self.assertEqual(total["handled_requests"], normal["handled_requests"] + stress["handled_requests"])
        self.assertGreaterEqual(stress["actual_hardware_irqs"], 2704)

    def test_stress_missing_duplicate_or_weak_session_never_passes(self):
        for change in ("drop", "duplicate", "wrong-mode", "weak-irqs", "missing-summary", "missing-records", "failed-process"):
            with self.subTest(change=change):
                profiles = self.completion_profiles(True)
                records = profiles["O2"]["targets"]
                if change == "drop":
                    records.pop()
                elif change == "duplicate":
                    records[-1] = records[-2]
                elif change == "wrong-mode":
                    with self.assertRaises(checker.Gate9Failure):
                        checker._completion_counts(profiles)
                    continue
                elif change == "weak-irqs":
                    records[-1]["summary"]["observed_hardware_irqs"] = 337
                elif change == "missing-summary":
                    del records[-1]["summary"]
                elif change == "missing-records":
                    records[-1]["summary"]["records_checked"] = 47
                else:
                    records[-1]["returncode"] = -9
                with self.assertRaises(checker.Gate9Failure):
                    checker._completion_counts(profiles, stress=True)

    def test_unsupported_stress_selection_invalidates_old_pass_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate((0, 1, "stress", None, [], {})):
                work = root / "build" / str(index)
                work.mkdir(parents=True)
                write_json(work / checker.RESULT_FILE, {"status": "PASS"})
                with mock.patch.object(checker, "build_monitor_image") as build:
                    with self.assertRaisesRegex(checker.Gate9Failure, "harness-input-failure.*stress"):
                        checker.check_gate9(root=root, work=work, clean=False, timeout_seconds=1, qemu_timeout=1, stress=value)
                    build.assert_not_called()
                self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_transport_process_behavior_and_audit_errors_remain_distinct(self):
        for category in ("target-timeout", "target-exit-mismatch", "protocol-mismatch",
                         "behavior-mismatch", "emulator-stderr", "image-or-harness-rejection"):
            with self.assertRaises(checker.Gate9Failure) as caught:
                checker._stage("target-failure", "mixed", lambda: (_ for _ in ()).throw(
                    runner.MonitorRunFailure(category, "test failure")))
            self.assertEqual(caught.exception.category, category)

    def test_old_pass_is_invalidated_before_build_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "build/check"
            work.mkdir(parents=True)
            write_json(work / checker.RESULT_FILE, {"status": "PASS"})
            with mock.patch.object(checker, "build_monitor_image", side_effect=Core0Error("build failed")):
                with self.assertRaisesRegex(checker.Gate9Failure, "compile-or-link-failure"):
                    checker.check_gate9(root=root, work=work, clean=False, timeout_seconds=1, qemu_timeout=1)
            self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_invalid_timeout_invalidates_pass_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in (0, -1, True, float("nan"), float("inf")):
                work = root / "build" / str(abs(hash(str(value))))
                work.mkdir(parents=True)
                write_json(work / checker.RESULT_FILE, {"status": "PASS"})
                with mock.patch.object(checker, "build_monitor_image") as build:
                    with self.assertRaisesRegex(checker.Gate9Failure, "harness-input-failure"):
                        checker.check_gate9(root=root, work=work, clean=False, timeout_seconds=value, qemu_timeout=1)
                    build.assert_not_called()
                self.assertFalse((work / checker.RESULT_FILE).exists())

    def test_cleanup_cannot_delete_outside_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "precious"
            work.mkdir()
            (work / "keep").write_text("retain")
            with self.assertRaises(checker.Gate9Failure):
                checker.check_gate9(root=root, work=work, clean=True, timeout_seconds=1, qemu_timeout=1)
            self.assertEqual((work / "keep").read_text(), "retain")

    def test_actual_probe_source_has_frozen_count_and_marker(self):
        source = (ROOT / "examples/foundation/MonitorPolicyProbes.lean").read_text()
        self.assertEqual(sum(line.startswith("#guard ") for line in source.splitlines()), 50)
        self.assertIn(checker.POLICY_MARKER, source)

    def test_probe_marker_followed_by_failure_or_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "examples/foundation/MonitorPolicyProbes.lean"
            source.parent.mkdir(parents=True)
            source.write_text("#guard true\n" * 50)
            manifest = {"scalar_functions": [{}] * 54, "action_functions": [{}] * 85}
            frontend = "Monitor genuine v0.7 frontend/lowering passed: 54 scalar functions, 85 Action functions, 7 timer/2 trap/4 UART operations"
            good = frontend + "\n" + checker.POLICY_MARKER + "\n"
            for code, output in ((1, good), (0, good + checker.POLICY_MARKER),
                                 (0, good.replace("PROBES:50", "PROBES:49")), (0, good + "sorryAx")):
                with mock.patch.object(checker, "run_bounded", return_value=CommandResult((), code, output.encode(), b"", 0)):
                    with self.assertRaises(Core0Error):
                        checker._run_probes(root=root, work=root / "build/probes", timeout_seconds=1, manifest=manifest)

    def test_retained_raw_frames_are_revalidated_not_only_hashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output, work = root / "build/image", root / "build/run"
            output.mkdir(parents=True); work.mkdir(parents=True)
            (output / "image.elf").write_bytes(b"image")
            write_json(output / "audit.json", {"audit": "test"})
            scenario = corpus.Scenario("simple", (corpus.Request(1, 1), corpus.Request(10, 2)))
            machine = {"executable_ranges": [[0x80000000, 0x80010000]]}
            sent = b"".join(request.encode() for request in scenario.requests)
            received = corpus.READY + corpus.Response(0, 1, (0x31304E4F4D4D454C, 7, 1, 0x3FF)).encode() + corpus.Response(0, 2, (2, 0, 0, 0)).encode()
            for name, data in (("sent.bin", sent), ("received.bin", received), ("stderr.bin", b"")):
                (work / name).write_bytes(data)
            binding = {"audit_sha256": sha256(output / "audit.json")}
            record = {"schema_version": 1, "status": "PASS", "profile": corpus.PROFILE,
                "artifact_category": corpus.ARTIFACT_CATEGORY, "test_abi": corpus.TEST_ABI,
                "scenario": scenario.name, "image": str((output / "image.elf").resolve()),
                "started_at": "2026-10-08T00:00:00+00:00", "finished_at": "2026-10-08T00:00:00.1+00:00",
                "timeout_seconds": 1, "elapsed_seconds": 0.1,
                "pid": 100, "image_sha256": sha256(output / "image.elf"),
                "binding": binding, "machine": machine, "returncode": 0,
                "argv": list(runner.qemu_argv(output / "image.elf")),
                "ready_observed_before_input": True, "stdin_open_until_exit": True,
                "semantic_validation_after_exit": True, "single_pid": True, "single_elf": True,
                "first_input_after_ready": True, "raw_artifacts": {name: sha256(work / name)
                    for name in ("sent.bin", "received.bin", "stderr.bin")},
                **runner.validate_transcript(scenario, sent, received, 0, machine)}
            write_json(work / runner.RESULT_FILE, record)
            with mock.patch.object(runner, "run_session", return_value=record), \
                 mock.patch.object(runner, "validate_image_binding", return_value=binding), \
                 mock.patch.object(runner, "image_machine_info", return_value=machine):
                checker._target(root=root, output=output, work=work, scenario=scenario, timeout_seconds=1)
            (work / "received.bin").write_bytes(received[:-8] + corpus.words(99))
            record["raw_artifacts"]["received.bin"] = sha256(work / "received.bin")
            write_json(work / runner.RESULT_FILE, record)
            with mock.patch.object(runner, "run_session", return_value=record), \
                 mock.patch.object(runner, "validate_image_binding", return_value=binding), \
                 mock.patch.object(runner, "image_machine_info", return_value=machine):
                with self.assertRaisesRegex(Core0Error, "EXIT"):
                    checker._target(root=root, output=output, work=work, scenario=scenario, timeout_seconds=1)

    def test_profile_source_hashes_must_really_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = {profile: root / "build" / profile for profile in ("O0", "O2")}
            for output in outputs.values():
                output.mkdir(parents=True)
                for name in runner.SOURCE_ARTIFACTS:
                    (output / name).write_text("identical source")
            with mock.patch.object(runner, "source_inputs", return_value={"source": "hash"}):
                self.assertTrue(checker._verify_profiles(outputs, root)["same_checked_source"])
                (outputs["O2"] / "program.ll").write_text("different source")
                with self.assertRaisesRegex(Core0Error, "differ"):
                    checker._verify_profiles(outputs, root)


if __name__ == "__main__":
    unittest.main()
