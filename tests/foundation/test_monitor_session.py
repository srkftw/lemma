#!/usr/bin/env python3
"""Fail-closed monitor framing, live pipe, raw evidence and binding tests."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate9_corpus as corpus
import run_monitor_session as runner
import test_timer_runner as timer_fixture
from core0_common import Core0Error, sha256, write_json

MACHINE = {"executable_ranges": [[0x80000000, 0x80010000]], "symbols": {}}
SIMPLE = corpus.Scenario("simple", (corpus.Request(1, 1), corpus.Request(2, 2), corpus.Request(10, 3)))
RESPONSES = (corpus.Response(0, 1, (0x31304E4F4D4D454C, 7, 1, 0x3FF)),
             corpus.Response(0, 2, (2, 0, 0, 0)), corpus.Response(0, 3, (3, 0, 0, 0)))
SENT = b"".join(request.encode() for request in SIMPLE.requests)
RECEIVED = corpus.READY + b"".join(response.encode() for response in RESPONSES)


class MonitorTranscriptTests(unittest.TestCase):
    def test_exact_complete_session(self):
        report = runner.validate_transcript(SIMPLE, SENT, RECEIVED, 0, MACHINE)
        self.assertEqual(report["summary"]["handled_requests"], 3)
        self.assertEqual(report["outcome"], "verified-monitor-session")

    def test_banner_only_truncated_extra_and_fatal_frames_reject(self):
        for data in (corpus.READY, RECEIVED[:-1], RECEIVED + b"x", b"junk" + RECEIVED,
                     RECEIVED.replace(b"LMS9", b"LMS8", 1),
                     RECEIVED[:len(corpus.READY) + 5] + bytes((18,)) + RECEIVED[len(corpus.READY) + 6:]):
            with self.assertRaises(runner.MonitorRunFailure):
                runner.validate_transcript(SIMPLE, SENT, data, 0, MACHINE)

    def test_request_id_semantics_and_failed_process_never_count_as_success(self):
        for data, code in ((RECEIVED, False), (RECEIVED, -11), (RECEIVED, 18),
            (RECEIVED.replace(corpus.words(2, 0, 0, 0), corpus.words(99, 0, 0, 0), 1), 0)):
            with self.assertRaises(runner.MonitorRunFailure):
                runner.validate_transcript(SIMPLE, SENT, data, code, MACHINE)
        with self.assertRaisesRegex(runner.MonitorRunFailure, "runtime-input"):
            runner.validate_transcript(SIMPLE, SENT[:-1], RECEIVED, 0, MACHINE)

    def test_terminal_receive_failures_require_exact_process_and_no_response(self):
        for scenario in corpus.TERMINAL_SCENARIOS[:4]:
            result = runner.validate_transcript(scenario, scenario.terminal_input, corpus.READY,
                scenario.expected_exit, MACHINE)
            self.assertEqual(result["outcome"], "verified-terminal-rejection")
            for code in (0, -9, 18):
                with self.assertRaises(runner.MonitorRunFailure):
                    runner.validate_transcript(scenario, scenario.terminal_input, corpus.READY, code, MACHINE)
            with self.assertRaises(runner.MonitorRunFailure):
                runner.validate_transcript(scenario, scenario.terminal_input, RECEIVED, scenario.expected_exit, MACHINE)

    def test_active_terminal_prefix_is_checked_before_receive_failure_credit(self):
        scenario = corpus.SCENARIO_BY_NAME["active-truncated-payload"]
        sent = scenario.requests[0].encode() + scenario.terminal_input
        received = corpus.READY + corpus.Response(0, 0x9110, (1, 10000, 20000, 0)).encode()
        result = runner.validate_transcript(scenario, sent, received, 15, MACHINE)
        self.assertTrue(result["summary"]["active_at_terminal_input"])
        with self.assertRaises(runner.MonitorRunFailure):
            runner.validate_transcript(scenario, sent, corpus.READY, 15, MACHINE)

    def test_both_session_capacity_edges(self):
        for scenario in corpus.BUDGET_SCENARIOS:
            received = corpus.READY + b"".join(corpus.Response(0, request.request_id,
                (256, 0, 0, 0) if request.command == 10 else (0x31304E4F4D4D454C, 7, 1, 0x3FF)).encode()
                for request in scenario.requests)
            result = runner.validate_transcript(scenario, b"".join(request.encode() for request in scenario.requests),
                received, scenario.expected_exit, MACHINE)
            self.assertEqual(result["summary"]["handled_requests"], 256)
            with self.assertRaises(runner.MonitorRunFailure):
                runner.validate_transcript(scenario, b"".join(request.encode() for request in scenario.requests),
                    received + RESPONSES[0].encode(), scenario.expected_exit, MACHINE)


class MonitorRetainedRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "build/image/image.elf"
        self.run = self.root / "build/run"
        self.image.parent.mkdir(parents=True)
        self.run.mkdir(parents=True)
        self.image.write_bytes(b"image")
        for name, data in (
            ("sent.bin", SENT), ("received.bin", RECEIVED), ("stderr.bin", b""),
        ):
            (self.run / name).write_bytes(data)
        self.binding = {
            "manifest": {"closed": True}, "abi": {"closed": True},
            "source_commit": "1" * 40, "optimization": "O0",
            "audit_sha256": "2" * 64,
        }
        self.machine = {
            "executable_ranges": [[0x80000000, 0x80010000]],
            "symbols": {
                "__timer_probe_loop": 0x80001000,
                "__timer_probe_snapshot": 0x80001004,
                "__trap_breakpoint_resume": 0x80002004,
                "__trap_breakpoint_site": 0x80002000,
                "__trap_ecall_resume": 0x80003004,
                "__trap_ecall_site": 0x80003000,
                "core0_trap_vector": 0x80004000,
            },
        }
        observed = runner.validate_transcript(SIMPLE, SENT, RECEIVED, 0, self.machine)
        self.record = {
            "schema_version": 1,
            "status": "PASS",
            "profile": corpus.PROFILE,
            "artifact_category": corpus.ARTIFACT_CATEGORY,
            "test_abi": corpus.TEST_ABI,
            "scenario": SIMPLE.name,
            "image": str(self.image.resolve()),
            "started_at": "2026-10-08T00:00:00+00:00",
            "timeout_seconds": 20.0,
            "image_sha256": sha256(self.image),
            "binding": self.binding,
            "machine": self.machine,
            "ready_observed_before_input": True,
            "first_input_after_ready": True,
            "stdin_open_until_exit": True,
            **observed,
            "single_pid": True,
            "single_elf": True,
            "semantic_validation_after_exit": True,
            "pid": 123,
            "returncode": 0,
            "argv": list(runner.qemu_argv(self.image)),
            "raw_artifacts": {
                name: sha256(self.run / name)
                for name in ("sent.bin", "received.bin", "stderr.bin")
            },
            "elapsed_seconds": 2.0,
            "finished_at": "2026-10-08T00:00:02+00:00",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def validate(self, record=None):
        with mock.patch.object(
            runner, "validate_image_binding", return_value=self.binding
        ), mock.patch.object(
            runner, "image_machine_info", return_value=self.machine
        ):
            return runner.validate_success_record(
                root=self.root,
                image=self.image,
                run_directory=self.run,
                scenario=SIMPLE,
                record=self.record if record is None else record,
                expected_timeout_seconds=20.0,
            )

    def changed(self):
        return json.loads(json.dumps(self.record))

    def test_complete_record_recomputes_binding_machine_and_transcript(self):
        observed = self.validate()
        self.assertEqual(observed["summary"]["handled_requests"], 3)

    def test_deleted_required_fields_and_argv_reject(self):
        for name in ("schema_version", "binding", "machine", "argv", "summary"):
            with self.subTest(name=name):
                record = self.changed()
                del record[name]
                with self.assertRaisesRegex(Core0Error, "fields"):
                    self.validate(record)
        record = self.changed()
        record["argv"] = record["argv"][:-1]
        with self.assertRaisesRegex(Core0Error, "QEMU command"):
            self.validate(record)
        record = self.changed()
        record["unreviewed_evidence"] = True
        with self.assertRaisesRegex(Core0Error, "fields"):
            self.validate(record)

    def test_bool_version_and_exit_fields_reject(self):
        for name in ("schema_version", "expected_exit", "returncode"):
            with self.subTest(name=name):
                record = self.changed()
                record[name] = False if name != "schema_version" else True
                with self.assertRaises(Core0Error):
                    self.validate(record)

    def test_shrunk_binding_never_substitutes_for_fresh_validation(self):
        record = self.changed()
        record["binding"] = {"audit_sha256": self.binding["audit_sha256"]}
        with self.assertRaisesRegex(Core0Error, "binding"):
            self.validate(record)

    def test_widened_ranges_and_missing_symbols_never_replace_elf_evidence(self):
        record = self.changed()
        record["machine"]["executable_ranges"] = [[0x80000000, 0x90000000]]
        with self.assertRaisesRegex(Core0Error, "machine evidence"):
            self.validate(record)
        record = self.changed()
        del record["machine"]["symbols"]["core0_trap_vector"]
        with self.assertRaisesRegex(Core0Error, "machine evidence"):
            self.validate(record)

    def test_no_request_record_omits_summary_and_preserves_none_input_marker(self):
        scenario = corpus.SCENARIO_BY_NAME["missing-input"]
        sent, received = b"", corpus.READY
        (self.run / "sent.bin").write_bytes(sent)
        (self.run / "received.bin").write_bytes(received)
        record = self.changed()
        record.pop("summary")
        record.update(
            scenario=scenario.name,
            returncode=scenario.expected_exit,
            first_input_after_ready=None,
            **runner.validate_transcript(
                scenario, sent, received, scenario.expected_exit, self.machine
            ),
        )
        record["raw_artifacts"] = {
            name: sha256(self.run / name)
            for name in ("sent.bin", "received.bin", "stderr.bin")
        }
        with mock.patch.object(
            runner, "validate_image_binding", return_value=self.binding
        ), mock.patch.object(
            runner, "image_machine_info", return_value=self.machine
        ):
            runner.validate_success_record(
                root=self.root, image=self.image, run_directory=self.run,
                scenario=scenario, record=record, expected_timeout_seconds=20.0,
            )
            record["summary"] = {}
            with self.assertRaisesRegex(Core0Error, "fields"):
                runner.validate_success_record(
                    root=self.root, image=self.image, run_directory=self.run,
                    scenario=scenario, record=record, expected_timeout_seconds=20.0,
                )


class MonitorProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "build/image/image.elf"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"image")
        self.output = self.root / "build/runs/case"

    def tearDown(self):
        self.tmp.cleanup()

    def child(self, program, *, scenario=SIMPLE, timeout=2):
        with mock.patch.object(runner, "validate_image_binding", return_value={}), \
             mock.patch.object(runner, "image_machine_info", return_value=MACHINE), \
             mock.patch.object(runner, "source_inputs", return_value={}), \
             mock.patch.object(runner, "require_tools", return_value={}), \
             mock.patch.object(runner, "qemu_argv", return_value=(sys.executable, "-c", program)):
            return runner.run_session(root=self.root, image=self.image, output_dir=self.output,
                scenario=scenario, timeout_seconds=timeout, clean=True)

    def program(self, suffix=""):
        # Read requests only after emitting READY, and emit one response at a
        # time. The pipe capture proves real post-boot input, not cached output.
        return ("import os,sys;os.write(1," + repr(corpus.READY) + ");"
            + ";".join(f"assert sys.stdin.buffer.read({len(request.encode())}) == {request.encode()!r};os.write(1,{response.encode()!r})"
                        for request, response in zip(SIMPLE.requests, RESPONSES, strict=True)) + ";" + suffix)

    def test_live_post_ready_requests_atomic_report_and_raw_evidence(self):
        report = self.child(self.program())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual((self.output / "sent.bin").read_bytes(), SENT)
        self.assertEqual((self.output / "received.bin").read_bytes(), RECEIVED)
        self.assertEqual(report, json.loads((self.output / "run.json").read_text()))
        self.assertTrue(report["semantic_validation_after_exit"])
        self.assertFalse((self.output / "run.json.tmp").exists())

    def test_heavy_oracle_runs_only_after_process_is_reaped(self):
        original = runner.validate_transcript
        actual_popen = runner.subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            process = actual_popen(*args, **kwargs)
            children.append(process)
            return process
        def validate(*args, **kwargs):
            # The child has sent EXIT and exited before any independent oracle.
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].returncode, 0)
            with self.assertRaises(ChildProcessError):
                os.waitpid(children[0].pid, os.WNOHANG)
            return original(*args, **kwargs)
        with mock.patch.object(runner, "validate_transcript", side_effect=validate), \
             mock.patch.object(runner.subprocess, "Popen", side_effect=launch):
            report = self.child(self.program())
        self.assertTrue(report["semantic_validation_after_exit"])

    def test_valid_responses_followed_by_process_failure_are_rejected(self):
        with self.assertRaisesRegex(runner.MonitorRunFailure, "target-exit-mismatch"):
            self.child(self.program("sys.exit(1)"))
        self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")

    def test_unexpected_stderr_and_extra_stdout_are_retained_failures(self):
        with self.assertRaisesRegex(runner.MonitorRunFailure, "emulator-stderr"):
            self.child(self.program("sys.stderr.write('emulator fault')"))
        self.assertEqual((self.output / "stderr.bin").read_bytes(), b"emulator fault")
        with self.assertRaisesRegex(runner.MonitorRunFailure, "protocol-mismatch"):
            self.child(self.program("os.write(1,b'extra')"))

    def test_timeout_kills_reaps_and_retains_partial_ready(self):
        program = "import os,time;os.write(1," + repr(corpus.READY) + ");time.sleep(10)"
        with self.assertRaisesRegex(runner.MonitorRunFailure, "target-timeout"):
            self.child(program, timeout=0.1)
        report = json.loads((self.output / "run.json").read_text())
        self.assertTrue(report["cleanup"]["process_reaped"])
        self.assertEqual((self.output / "received.bin").read_bytes(), corpus.READY)
        with self.assertRaises(ProcessLookupError):
            os.kill(report["pid"], 0)

    def test_terminal_missing_input_keeps_stdin_open(self):
        program = "import os,select,sys;os.write(1," + repr(corpus.READY) + ");assert not select.select([0],[],[],0.05)[0];sys.exit(12)"
        report = self.child(program, scenario=corpus.SCENARIO_BY_NAME["missing-input"])
        self.assertTrue(report["stdin_open_until_exit"])
        self.assertEqual((self.output / "sent.bin").read_bytes(), b"")

    def test_binding_failure_invalidates_old_pass_without_launching(self):
        self.output.mkdir(parents=True)
        write_json(self.output / "run.json", {"status": "PASS"})
        with mock.patch.object(runner, "validate_image_binding", side_effect=Core0Error("stale audit")), \
             mock.patch.object(runner.subprocess, "Popen") as child:
            with self.assertRaises(runner.MonitorRunFailure):
                runner.run_session(root=self.root, image=self.image, output_dir=self.output,
                    scenario=SIMPLE, timeout_seconds=2)
            child.assert_not_called()
        self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")

    def test_nonfinite_timeouts_fail_before_launch_and_remove_old_pass(self):
        for timeout in (0, -1, True, float("nan"), float("inf")):
            with self.assertRaises(runner.MonitorRunFailure):
                self.child(self.program(), timeout=timeout)
            self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")


class MonitorBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.directory = self.root / "build/image"
        self.directory.mkdir(parents=True)
        self.image = self.directory / "image.elf"
        for name in runner.BUILD_ARTIFACTS:
            (self.directory / name).write_bytes(("artifact:" + name).encode())
        for name in runner.REQUIRED_SOURCE_INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source:" + name)
        # Identify the current HTML fixture; do not weaken the runner's
        # original-path handling for immutable historical source archives.
        write_json(self.root / "docs/document-map.json", {"schema": "lemma-document-map/v1"})
        self.bind()

    def tearDown(self):
        self.tmp.cleanup()

    def bind(self):
        manifest, abi = {"closed_manifest": True}, {"closed_abi": True}
        linked = [{"path": name, "kind": kind, "sha256": sha256(self.directory / name)}
            for name, kind in (("startup.o", "lean-structured-timer-startup"), ("program.o", "test-monitor-image-llvm"))]
        provenance = {"schema_version": 2, "artifact_category": corpus.ARTIFACT_CATEGORY,
            "source_commit": "1" * 40, "optimization": "O0", "dirty_tree": False, "dirty_paths": [],
            "linked_inputs": linked, "source_inputs": [{"path": name, "sha256": sha256(self.root / name)}
                for name in sorted(runner.REQUIRED_SOURCE_INPUTS)]}
        write_json(self.directory / "monitor-manifest.json", manifest)
        write_json(self.directory / "monitor-abi.json", abi)
        write_json(self.directory / "provenance.json", provenance)
        hashes = {name: sha256(self.directory / name) for name in runner.BUILD_ARTIFACTS}
        write_json(self.directory / "build.json", {"schema_version": 1, "status": "pass",
            "artifact_category": corpus.ARTIFACT_CATEGORY, "optimization": "O0", "linked_inputs": linked, "artifacts": hashes})
        write_json(self.directory / "audit.json", {"schema_version": 1, "status": "pass",
            "artifact_category": corpus.ARTIFACT_CATEGORY, "optimization": "O0", "linked_inputs": linked,
            "source_commit": "1" * 40, "dirty_tree": False, "provenance_schema_version": 2,
            "hashes": hashes, "manifest": manifest, "monitor_abi": abi})

    def validate(self):
        with mock.patch.object(runner.audit_monitor, "validate_monitor_manifest"), \
             mock.patch.object(runner.audit_monitor, "validate_monitor_abi"), \
             mock.patch.object(runner.audit_monitor, "validate_monitor_companions"), \
             mock.patch.object(runner, "_validate_audit"):
            return runner.validate_image_binding(self.image, root=self.root)

    def test_complete_current_bundle_binds_hashes_and_source(self):
        self.assertEqual(self.validate()["source_commit"], "1" * 40)

    def test_every_required_artifact_and_audit_hash_is_mandatory(self):
        for name in runner.BUILD_ARTIFACTS:
            with self.subTest(name=name):
                data = (self.directory / name).read_bytes()
                (self.directory / name).unlink()
                with self.assertRaises((Core0Error, OSError)):
                    self.validate()
                (self.directory / name).write_bytes(data)
                self.bind()
                audit = json.loads((self.directory / "audit.json").read_text())
                del audit["hashes"][name]
                write_json(self.directory / "audit.json", audit)
                with self.assertRaises(Core0Error):
                    self.validate()
                self.bind()

    def test_stale_sources_objects_and_audit_identity_reject(self):
        (self.root / "examples/foundation/Monitor.lean").write_text("modified")
        with self.assertRaisesRegex(Core0Error, "stale"):
            self.validate()
        self.bind()
        (self.directory / "program.o").write_bytes(b"modified object")
        with self.assertRaises(Core0Error):
            self.validate()
        self.bind()
        audit = json.loads((self.directory / "audit.json").read_text())
        audit["source_commit"] = "2" * 40
        write_json(self.directory / "audit.json", audit)
        with self.assertRaisesRegex(Core0Error, "identities"):
            self.validate()

    def test_forged_nonempty_ir_and_missing_machine_evidence_reject(self):
        manifest = {"scalar_functions": [], "action_functions": []}
        for evidence in ({}, {"monitor_ir_audit": {"verified": True}}):
            with mock.patch.object(runner.audit_monitor, "validate_monitor_ir", return_value={"actual_pinned_ir": True}):
                with self.assertRaises(Core0Error):
                    runner._validate_audit(evidence, manifest, self.directory, "O0")
        with mock.patch.object(runner.audit_monitor, "validate_monitor_ir", return_value={"actual_pinned_ir": True}):
            with self.assertRaisesRegex(Core0Error, "machine evidence"):
                runner._validate_audit({"monitor_ir_audit": {"actual_pinned_ir": True}}, manifest, self.directory, "O0")

    def test_complete_shared_machine_fixture_and_weakened_monitor_audits(self):
        # Reuse the independently spelled Gate 8 machine fixture: Gate 9 has
        # exactly that substrate, but a different checked function/entry/UART
        # closure and resource roots. Do not fabricate a minimal {verified:true}.
        fixture = timer_fixture.TimerBindingTests()
        fixture.setUp()
        try:
            inherited = json.loads((fixture.directory / "audit.json").read_text())
        finally:
            fixture.tearDown()
        manifest = {"scalar_functions": [{"llvm": "core0_scalar_0"}],
            "action_functions": [{"llvm": "core0_action_0"}, {"llvm": "core0_action_1"}],
            "roots": [{"llvm": "core0_action_0"}, {"llvm": "core0_action_1"}]}
        machine = inherited["timer_machine_audit"]
        machine["compiled_functions"] = 3
        machine["timer_start_machine_body_sha256"] = runner.audit_monitor.MONITOR_START_MACHINE_BODY_SHA256["O0"]
        sequence = runner.audit_monitor.MONITOR_MACHINE_ACCESS_SEQUENCE
        accesses = [{"operation": op, "function": fn, "instruction": insn,
            "address": f"0x{address:08x}", "fence_before": True, "fence_after": True}
            for op, fn, insn, address in sequence]
        device = {"access_count": 6, "byte_accesses_only": True, "ordered_fence_calls": 12,
            "denied_region_metadata_materializations": sum(runner.audit_monitor.MONITOR_MACHINE_DENIED_METADATA.values()),
            "register_use_audit": {"inferred_uart_accesses": 6, "all_inferred_accesses_are_approved": True,
                "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
            "fence_implementation": "fence iorw,iorw; ret", "accesses": accesses}
        program = ["core0_action_0", "core0_action_1", "core0_main", "core0_scalar_0"]
        startup = sorted(runner.audit_timer.TIMER_STARTUP_FUNCTIONS)
        graph = inherited["stack_sizes"]["call_graph"]
        graph["foreground"].update(checked_root="core0_action_0", chain=["core0_main", "core0_action_0"])
        graph["trap_dispatcher"].update(checked_root="core0_action_1", chain=["core0_action_1"])
        graph["frame_chains"] = {"core0_main": {key: graph["foreground"][key] for key in ("bytes", "chain")},
            "core0_action_1": {key: graph["trap_dispatcher"][key] for key in ("bytes", "chain")}}
        audit = {"monitor_ir_audit": {"actual_pinned_ir": True}, "monitor_machine_audit": machine,
            "device_machine_audit": device, "stack_sizes": {"call_graph": graph},
            "object_defined_function_symbols": {"program.o": program, "startup.o": startup},
            "elf": {"entry": "0x80000000", "machine": "RISC-V", "class": "ELF64",
                "endianness": "little", "dynamic_dependencies": [], "undefined_symbols": [],
                "final_relocations": [], "defined_function_symbols": sorted(program + startup)}}
        with mock.patch.object(runner.audit_monitor, "validate_monitor_ir", return_value={"actual_pinned_ir": True}):
            runner._validate_audit(audit, manifest, self.directory, "O0")
            for path, value in (
                (("monitor_machine_audit", "compiled_functions"), 2),
                (("monitor_machine_audit", "compiled_privileged_instructions"), 1),
                (("monitor_machine_audit", "compiled_gp_tp_free"), False),
                (("monitor_machine_audit", "timer_machine_body_sha256"), {}),
                (("monitor_machine_audit", "timer_start_machine_body_sha256"), "0" * 64),
                (("monitor_machine_audit", "machine_slot_sequences"), {}),
                (("monitor_machine_audit", "machine_csr_operations"), 11),
                (("monitor_machine_audit", "timer_mmio_machine", "compiled_program_accesses"), 1),
                (("device_machine_audit", "ordered_fence_calls"), 11),
                (("device_machine_audit", "denied_region_metadata_materializations"), 0),
                (("device_machine_audit", "accesses"), []),
                (("elf", "undefined_symbols"), ["foreign_helper"]),
                (("object_defined_function_symbols", "program.o"), program + ["foreign_helper"]),
                (("stack_sizes", "call_graph", "foreground", "bytes"), 65521),
                (("stack_sizes", "call_graph", "trap_dispatcher", "checked_root"), "wrong_root"),
            ):
                with self.subTest(path=path):
                    changed = json.loads(json.dumps(audit))
                    target = changed
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    with self.assertRaises(Core0Error):
                        runner._validate_audit(changed, manifest, self.directory, "O0")


if __name__ == "__main__":
    unittest.main()
