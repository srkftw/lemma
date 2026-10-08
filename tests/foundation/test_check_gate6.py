#!/usr/bin/env python3
"""Focused host-only tests for the transactional Gate 6 acceptance driver."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_foundation_gate6  # noqa: E402
import gate6_corpus  # noqa: E402
import run_device_session  # noqa: E402
from core0_common import Core0Error, sha256, write_json  # noqa: E402


class Gate6DriverTests(unittest.TestCase):
    def test_closed_corpus_has_four_interactive_and_ten_terminal_sessions(self) -> None:
        manifest = check_foundation_gate6._validate_corpus(
            gate6_corpus.scenario_manifest()
        )
        scenarios = manifest["scenarios"]
        self.assertEqual(len(scenarios), 14)
        self.assertEqual(
            sum(bool(scenario.exchanges) for scenario in gate6_corpus.SCENARIOS), 4
        )
        self.assertEqual(
            sum(not scenario.exchanges for scenario in gate6_corpus.SCENARIOS), 10
        )
        self.assertEqual(
            sum(len(scenario.exchanges) for scenario in gate6_corpus.SCENARIOS), 8
        )

    def test_corpus_validation_rejects_tampered_terminal_status(self) -> None:
        manifest = gate6_corpus.scenario_manifest()
        manifest["scenarios"][-1]["expected_exit_status"] = 0
        with self.assertRaisesRegex(Core0Error, "closed corpus"):
            check_foundation_gate6._validate_corpus(manifest)

    def test_rejection_manifest_pins_all_five_fixtures(self) -> None:
        records = check_foundation_gate6._load_rejections(
            ROOT / "examples/foundation/gate6-reject/rejections.json", ROOT
        )
        self.assertEqual(len(records), 5)
        self.assertEqual(
            tuple(record.path.name for record in records),
            check_foundation_gate6.REJECTION_FILES,
        )

    def test_probe_parser_requires_exact_order_and_success(self) -> None:
        expected = ("first", "second")
        good = "PINNED_DEVICE:first:ok\nPINNED_DEVICE:second:ok\n"
        self.assertEqual(
            check_foundation_gate6._parse_probe_output(
                good, prefix="PINNED_DEVICE", expected_labels=expected
            ),
            ["first", "second"],
        )
        for bad in (
            "PINNED_DEVICE:first:ok\n",
            "PINNED_DEVICE:second:ok\nPINNED_DEVICE:first:ok\n",
            "PINNED_DEVICE:first:ok\nPINNED_DEVICE:second:failed\n",
        ):
            with self.subTest(output=bad):
                with self.assertRaises(Core0Error):
                    check_foundation_gate6._parse_probe_output(
                        bad, prefix="PINNED_DEVICE", expected_labels=expected
                    )

    def test_branch_structural_audit_requires_exclusive_source_and_cfg_placement(self) -> None:
        source_function = "Lemma.Examples.Foundation.Device.dispatchBranch"
        symbol = "core0_action_13"
        selector_0 = {
            "scratch_offset": 64,
            "stored_byte": 90,
            "send_byte_0xa5": False,
        }
        selector_1 = {"scratch_marker_store": False, "sent_byte": 165}

        def layer(dispatch: str) -> dict[str, object]:
            return {
                "source_function": source_function,
                "llvm_symbol": symbol,
                "dispatch": dispatch,
                "separate_successors": True,
                "selector_0_successor": "selector.zero",
                "selector_1_successor": "selector.one",
                "marker_store_block": "marker.store",
                "send_byte_block": "send.byte",
                "exclusive_reachability": True,
            }

        record = {
            "source_function": source_function,
            "llvm_symbol": symbol,
            "selector_0": selector_0,
            "selector_1": selector_1,
            "source": {
                "source_function": source_function,
                "llvm_symbol": symbol,
                "selector_0": selector_0,
                "selector_1": selector_1,
                "separate_subtrees": True,
            },
            "pre_ir": layer("conditional-branches"),
            "post_ir": layer("switch"),
        }
        self.assertIs(
            check_foundation_gate6._validate_branch_structural_audit(
                record, profile="O2"
            ),
            record,
        )
        tampered = copy.deepcopy(record)
        tampered["post_ir"]["exclusive_reachability"] = False
        with self.assertRaisesRegex(Core0Error, "CFG placement"):
            check_foundation_gate6._validate_branch_structural_audit(
                tampered, profile="O2"
            )

    def test_mutation_matrix_requires_source_and_both_ir_branch_mutants(self) -> None:
        records = [
            {"name": name, "category": "test", "diagnostic": "detected"}
            for name in sorted(check_foundation_gate6.REQUIRED_DEVICE_MUTATIONS)
        ]
        with mock.patch.object(
            check_foundation_gate6.audit_device,
            "audit_mutation_matrix",
            return_value=records,
        ):
            report = check_foundation_gate6._run_mutation_matrix({}, "pre", "post")
        self.assertEqual(report["total_mutants_detected"], 18)

        omitted = [
            record
            for record in records
            if record["name"] != "misplaced-post-branch-effects"
        ]
        with mock.patch.object(
            check_foundation_gate6.audit_device,
            "audit_mutation_matrix",
            return_value=omitted,
        ):
            with self.assertRaisesRegex(Core0Error, "misplaced-post-branch-effects"):
                check_foundation_gate6._run_mutation_matrix({}, "pre", "post")

    def test_stage_wraps_failure_with_category_and_context(self) -> None:
        def fail() -> None:
            raise Core0Error("broken device model")

        with self.assertRaises(check_foundation_gate6.Gate6Failure) as raised:
            check_foundation_gate6._stage("model-failure", "probe", fail)
        self.assertEqual(raised.exception.category, "model-failure")
        self.assertEqual(raised.exception.context, "probe")
        self.assertEqual(raised.exception.detail, "broken device model")

    def test_target_stage_distinguishes_protocol_binding_process_and_timeout(self) -> None:
        cases = (
            ("device READY frame differs", "target-protocol-failure"),
            ("device image binding is missing", "target-artifact-binding-failure"),
            ("device QEMU exit status differs", "target-process-failure"),
            ("device session timed out", "target-timeout"),
        )
        for detail, category in cases:
            with self.subTest(detail=detail):
                def fail(detail: str = detail) -> None:
                    raise Core0Error(detail)

                with self.assertRaises(check_foundation_gate6.Gate6Failure) as raised:
                    check_foundation_gate6._target_stage("O0", "case", fail)
                self.assertEqual(raised.exception.category, category)

    def test_profile_identity_catches_checked_source_drift(self) -> None:
        provenance = {
            "artifact_category": "test-device-suite",
            "source_commit": "a" * 40,
            "dirty_tree": False,
            "dirty_paths": [],
            "compiler_route": "route",
            "target": {"triple": "riscv64-unknown-unknown-elf"},
            "source_inputs": [],
            "elaborated_inputs": [],
            "export_configuration": {},
        }
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            outputs = {profile: base / profile for profile in ("O0", "O2")}
            for output in outputs.values():
                output.mkdir()
                for name in check_foundation_gate6.CHECKED_SOURCE_ARTIFACTS:
                    (output / name).write_text(f"checked:{name}\n", encoding="utf-8")
                write_json(output / "provenance.json", provenance)
            manifests = {"O0": {"root": 1}, "O2": {"root": 1}}
            report = check_foundation_gate6._verify_profile_source_identity(
                root=ROOT, outputs=outputs, manifests=manifests
            )
            self.assertEqual(set(report["profiles"]), {"O0", "O2"})

            (outputs["O2"] / "program.ll").write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(Core0Error, "program.ll"):
                check_foundation_gate6._verify_profile_source_identity(
                    root=ROOT, outputs=outputs, manifests=manifests
                )

    @staticmethod
    def _session_record(
        *, image: Path, run_dir: Path, scenario: gate6_corpus.Scenario
    ) -> dict[str, object]:
        paths = run_device_session._paths(run_dir, scenario)
        sent = check_foundation_gate6._expected_sent(scenario)
        received = check_foundation_gate6._expected_received(scenario)
        assert received is not None
        paths["sent"].write_bytes(sent)
        paths["received"].write_bytes(received)
        paths["stderr"].write_bytes(b"")
        pid = 43210
        now = datetime.now(timezone.utc).isoformat()
        record: dict[str, object] = {
            "schema_version": 1,
            "status": "pass",
            "profile": gate6_corpus.PROFILE,
            "test_abi": gate6_corpus.TEST_ABI,
            "scenario": scenario.name,
            "purpose": scenario.purpose,
            "image": check_foundation_gate6._relative(image, ROOT),
            "image_sha256": sha256(image),
            "qemu_pid": pid,
            "single_pid": True,
            "single_elf": True,
            "qemu_argv": list(run_device_session._qemu_argv(image)),
            "qemu_returncode": scenario.expected_exit_status,
            "expected_exit_status": scenario.expected_exit_status,
            "started_at": now,
            "finished_at": now,
            "elapsed_seconds": 0.1,
            "ready_hex": gate6_corpus.READY.hex(),
            "withhold_after_ready": scenario.withhold_after_ready,
            "suppress_output_after_ready": scenario.suppress_output_after_ready,
            "exchanges": [
                {
                    "index": index,
                    "pid": pid,
                    "image_sha256": sha256(image),
                    "prefix_hex": exchange.expected_prefix.hex(),
                    "response": asdict(exchange.expected_response),
                }
                for index, exchange in enumerate(scenario.exchanges)
            ],
            "sent": check_foundation_gate6._relative(paths["sent"], ROOT),
            "sent_sha256": sha256(paths["sent"]),
            "received": check_foundation_gate6._relative(paths["received"], ROOT),
            "received_sha256": sha256(paths["received"]),
            "stderr": check_foundation_gate6._relative(paths["stderr"], ROOT),
            "stderr_sha256": sha256(paths["stderr"]),
        }
        write_json(paths["record"], record)
        return record

    def test_session_record_rebinds_complete_bytes_pid_and_elf(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as raw:
            base = Path(raw)
            image = base / "image.elf"
            image.write_bytes(b"synthetic ELF identity")
            run_dir = base / "run"
            run_dir.mkdir()
            scenario = gate6_corpus.ARITHMETIC
            record = self._session_record(
                image=image, run_dir=run_dir, scenario=scenario
            )
            checked = check_foundation_gate6._validate_session_record(
                root=ROOT,
                profile="O0",
                image=image,
                output_dir=run_dir,
                scenario=scenario,
                record=record,
            )
            self.assertEqual(len(checked["exchanges"]), 2)

            tampered = copy.deepcopy(record)
            paths = run_device_session._paths(run_dir, scenario)
            paths["received"].write_bytes(paths["received"].read_bytes() + b"!")
            tampered["received_sha256"] = sha256(paths["received"])
            write_json(paths["record"], tampered)
            with self.assertRaisesRegex(Core0Error, "received-byte evidence"):
                check_foundation_gate6._validate_session_record(
                    root=ROOT,
                    profile="O0",
                    image=image,
                    output_dir=run_dir,
                    scenario=scenario,
                    record=tampered,
                )

    def test_branch_runtime_evidence_is_explicit_about_ram_observation_gap(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as raw:
            base = Path(raw)
            image = base / "image.elf"
            image.write_bytes(b"synthetic branch ELF")
            run_dir = base / "run"
            run_dir.mkdir()
            record = self._session_record(
                image=image,
                run_dir=run_dir,
                scenario=gate6_corpus.BRANCH_EFFECTS,
            )
            evidence = check_foundation_gate6._branch_runtime_evidence(record)
            self.assertEqual(
                [item["uart_prefix_hex"] for item in evidence["observations"]],
                ["", "a5"],
            )
            self.assertEqual(
                [item["response"]["value"] for item in evidence["observations"]],
                [0, 1],
            )
            self.assertIs(evidence["ram_marker_directly_read_back"], False)

    def test_early_rerun_failure_invalidates_stale_pass_record(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as raw:
            work = Path(raw)
            result = work / check_foundation_gate6.RESULT_FILE
            result.write_text('{"status":"pass"}\n', encoding="utf-8")
            (work / "retained.txt").write_text("force non-clean failure\n", encoding="utf-8")
            with self.assertRaises(check_foundation_gate6.Gate6Failure) as raised:
                check_foundation_gate6.check_gate6(
                    root=ROOT,
                    work=work,
                    clean=False,
                    timeout_seconds=1.0,
                    qemu_timeout=1.0,
                )
            self.assertEqual(raised.exception.category, "work-directory-failure")
            self.assertFalse(result.exists())

    def test_report_install_replaces_record_and_leaves_no_temporary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "gate6-results.json"
            path.write_text('{"status":"stale"}\n', encoding="utf-8")
            check_foundation_gate6._install_report(path, {"status": "pass", "gate": 6})
            self.assertEqual(json.loads(path.read_text()), {"status": "pass", "gate": 6})
            self.assertFalse(path.with_name(path.name + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
