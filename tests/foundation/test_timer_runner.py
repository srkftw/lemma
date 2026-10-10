#!/usr/bin/env python3
"""Adversarial timer protocol, process cleanup, and artifact-binding tests."""
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate8_corpus as corpus
import run_timer_case as runner
from audit_timer import DISABLE_ARMING_MACHINE_BODY_SHA256, TIMER_MACHINE_BODY_SHA256
from core0_common import CommandResult, Core0Error, sha256, write_json

MACHINE = {"executable_ranges": [[0x80000000, 0x80010000]],
    "symbols": {name: 0x80000100 + index * 4 for index, name in enumerate(sorted(runner.SITE_SYMBOLS))}}


def frame(identifier, value, status=0):
    return b"LMS6" + bytes((1, status, 8, 0)) + struct.pack("<QQ", identifier, value)


def positive_parts(case, *, head=None, quanta=None):
    count = case.goal
    head = head if head is not None else (37 if case.scenario == 4 else min(count, 16))
    quanta = quanta if quanta is not None else (0 if case.goal == 1 else 1)
    retained = min(head, 16)
    chronological = [{"sequence": index + 1, "time": (index + 1) * 10,
                      "pc": 0x80001000 + (index % 3) * 4, "cause": corpus.TIMER_CAUSE}
                     for index in range(head - retained, head)]
    start = (head - retained) % 16
    physical = chronological[-start:] + chronological[:-start] if start else chronological
    last = chronological[-1]
    stats = dict(zip(corpus.STAT_FIELDS, (
        corpus.checksum(case.seed, quanta), quanta, count, head, head, count - head,
        5 if case.scenario == 2 else 0, 0, 1, 0, 1, count, count, 0,
        last["sequence"], last["time"], count * 10, count * 10 + case.period,
        count * 10 + 100, 0, last["sequence"], last["time"], last["pc"], last["cause"],
    ), strict=True))
    return stats, physical


def transcript(stats, physical):
    values = [frame(identifier, stats[key]) for identifier, key in zip(corpus.STAT_IDS, corpus.STAT_FIELDS)]
    for index, record in enumerate(physical):
        values.extend(frame(corpus.RING_BASE_ID + index * 4 + offset, record[key])
                      for offset, key in enumerate(("sequence", "time", "pc", "cause")))
    return corpus.READY + b"".join(values)


class TimerProtocolTests(unittest.TestCase):
    def test_positive_matrix_validates_checksum_hardware_and_raw_ring(self):
        for case in corpus.POSITIVE_CASES:
            stats, records = positive_parts(case)
            observed = runner.validate_transcript(case, transcript(stats, records), 0, MACHINE)
            self.assertEqual(observed["outcome"], "verified-positive")
            self.assertEqual(observed["chronological_ring"][-1]["sequence"], stats["last_consumed_sequence"])

    def test_pending_deassertion_latency_is_not_an_oracle(self):
        case = corpus.POSITIVE_CASES[2]
        stats, records = positive_parts(case)
        stats["real_pending"] = 1
        runner.validate_transcript(case, transcript(stats, records), 0, MACHINE)
        stats["real_pending"] = 2
        with self.assertRaises(runner.TimerRunFailure):
            runner.validate_transcript(case, transcript(stats, records), 0, MACHINE)

    def test_each_primary_stat_invariant_is_required(self):
        case = corpus.POSITIVE_CASES[0]
        good, records = positive_parts(case)
        mutations = {"checksum": 1, "outer_quanta": 0, "irq_count": 255, "head": 15,
            "tail": 15, "overflow": 0, "maximum_catch_up": 2, "context_mask": 1,
            "pending_witness": 0, "before": 1, "after": 1, "guard_mask": 1,
            "last_consumed_sequence": 1, "last_consumed_time": 1, "last_isr_time": 1,
            "deadline": 1, "real_time": 1, "real_pending": 2, "last_ring_sequence": 1,
            "last_ring_time": 1, "last_ring_pc": 1, "last_ring_cause": 7,
            "spurious": case.goal + 1}
        for key, value in mutations.items():
            with self.subTest(key=key):
                stats = dict(good, **{key: value})
                with self.assertRaises(runner.TimerRunFailure):
                    runner.validate_transcript(case, transcript(stats, records), 0, MACHINE)

    def test_raw_ring_word_invariants_and_chronological_rotation(self):
        case = corpus.POSITIVE_CASES[-1]
        stats, records = positive_parts(case)
        observed = runner.validate_transcript(case, transcript(stats, records), 0, MACHINE)
        self.assertEqual([record["sequence"] for record in observed["chronological_ring"]], list(range(22, 38)))
        for field, value in (("sequence", 0), ("sequence", case.goal + 1),
                             ("time", stats["real_time"] + 1), ("pc", 0x80001002),
                             ("pc", 0x80800000), ("cause", 7)):
            with self.subTest(field=field, value=value):
                bad = [dict(record) for record in records]
                bad[0][field] = value
                with self.assertRaises(runner.TimerRunFailure):
                    runner.validate_transcript(case, transcript(stats, bad), 0, MACHINE)

    def test_scenario_specific_overflow_catchup_wrap_and_useful_work(self):
        catchup = corpus.POSITIVE_CASES[3]
        stats, records = positive_parts(catchup)
        stats["skipped"] = 0
        with self.assertRaisesRegex(runner.TimerRunFailure, "catch-up"):
            runner.validate_transcript(catchup, transcript(stats, records), 0, MACHINE)
        interleaved = corpus.POSITIVE_CASES[-1]
        stats, records = positive_parts(interleaved, head=16)
        with self.assertRaisesRegex(runner.TimerRunFailure, "wrap"):
            runner.validate_transcript(interleaved, transcript(stats, records), 0, MACHINE)
        stats, records = positive_parts(corpus.POSITIVE_CASES[0], head=256)
        with self.assertRaisesRegex(runner.TimerRunFailure, "overflow"):
            runner.validate_transcript(corpus.POSITIVE_CASES[0], transcript(stats, records), 0, MACHINE)

    def test_protocol_requires_whole_exact_ordered_frame_set(self):
        case = corpus.POSITIVE_CASES[2]
        stats, records = positive_parts(case)
        good = transcript(stats, records)
        for data in (good[:-1], good + b"x", b"JUNK" + good,
                     good.replace(b"LMS6", b"LMS7", 1), good + frame(0x9999, 0),
                     corpus.READY + good[len(corpus.READY) + 24:],
                     good.replace(struct.pack("<Q", 0x8200), struct.pack("<Q", 0x8201), 1)):
            with self.assertRaises(runner.TimerRunFailure):
                runner.validate_transcript(case, data, 0, MACHINE)

    def test_semantic_rejections_require_exact_exit_and_no_frames(self):
        for case in corpus.NEGATIVE_CASES:
            code = corpus.expected_exit(case)
            self.assertEqual(runner.validate_transcript(case, corpus.READY, code, MACHINE)["outcome"], "verified-semantic-rejection")
            with self.assertRaisesRegex(runner.TimerRunFailure, "target-exit-mismatch"):
                runner.validate_transcript(case, corpus.READY, -11, MACHINE)
            with self.assertRaises(runner.TimerRunFailure):
                runner.validate_transcript(case, corpus.READY + frame(0x81ff, 0, 21), code, MACHINE)

    def test_both_mutants_require_the_exact_behavioral_failure_not_timeout_or_fatal(self):
        for mutation, case in corpus.MUTANT_CASES.items():
            code = corpus.expected_exit(case, mutation=mutation)
            value = corpus.RESTORE_MASK if mutation == 1 else 0
            blob = corpus.READY + frame(corpus.FAILURE_ID, value, code)
            observed = runner.validate_transcript(case, blob, code, MACHINE, mutation=mutation)
            self.assertIn(observed["outcome"], ("verified-behavioral-context-mismatch", "verified-missing-hardware-interrupt"))
            for bad_blob, bad_code in ((blob, -9), (blob, 18), (corpus.READY, code),
                (corpus.READY + frame(corpus.FAILURE_ID, value + 1, code), code),
                (blob + frame(corpus.FAILURE_ID, value, code), code)):
                with self.assertRaises(runner.TimerRunFailure):
                    runner.validate_transcript(case, bad_blob, bad_code, MACHINE, mutation=mutation)


class TimerProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "build/image/image.elf"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"test-image")
        self.output = self.root / "build/runs/case"
        self.case = corpus.POSITIVE_CASES[2]
        self.blob = transcript(*positive_parts(self.case))

    def tearDown(self):
        self.tmp.cleanup()

    def run_child(self, program, timeout=2):
        with mock.patch.object(runner, "validate_image_binding", return_value={}), \
             mock.patch.object(runner, "require_tools", return_value={}), \
             mock.patch.object(runner, "image_machine_info", return_value=MACHINE), \
             mock.patch.object(runner, "qemu_argv", return_value=(sys.executable, "-c", program)):
            return runner.run_case(root=self.root, image=self.image, case=self.case,
                output_dir=self.output, timeout_seconds=timeout)

    def test_fresh_fixture_raw_output_and_transactional_success(self):
        report = self.run_child(f"import sys;sys.stdout.buffer.write(bytes.fromhex('{self.blob.hex()}'))")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual((self.output / "runtime-input.bin").read_bytes(), corpus.fixture_bytes(self.case))
        self.assertEqual(json.loads((self.output / "run.json").read_text()), report)
        self.assertFalse((self.output / "run.json.tmp").exists())

    def test_valid_frame_followed_by_process_failure_is_not_success(self):
        program = f"import sys;sys.stdout.buffer.write(bytes.fromhex('{self.blob.hex()}'));sys.exit(1)"
        with self.assertRaisesRegex(runner.TimerRunFailure, "target-exit-mismatch"):
            self.run_child(program)
        self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")

    def test_unexpected_stderr_is_retained_and_rejected(self):
        program = f"import sys;sys.stdout.buffer.write(bytes.fromhex('{self.blob.hex()}'));sys.stderr.write('emulator fault')"
        with self.assertRaisesRegex(runner.TimerRunFailure, "emulator-stderr"):
            self.run_child(program)
        self.assertEqual((self.output / "stderr.bin").read_bytes(), b"emulator fault")

    def test_timeout_kills_and_reaps_with_partial_evidence(self):
        program = f"import sys,time;sys.stdout.buffer.write(bytes.fromhex('{corpus.READY.hex()}'));sys.stdout.flush();time.sleep(10)"
        with self.assertRaisesRegex(runner.TimerRunFailure, "target-timeout"):
            self.run_child(program, timeout=0.1)
        report = json.loads((self.output / "run.json").read_text())
        self.assertEqual(report["timeout_cleanup"], {"process_group_killed": True, "process_reaped": True})
        self.assertEqual((self.output / "uart.bin").read_bytes(), corpus.READY)
        with self.assertRaises(ProcessLookupError):
            os.kill(report["pid"], 0)

    def test_binding_failure_replaces_an_old_pass(self):
        self.output.mkdir(parents=True)
        write_json(self.output / "run.json", {"status": "PASS"})
        with mock.patch.object(runner, "validate_image_binding", side_effect=Core0Error("stale image")):
            with self.assertRaisesRegex(runner.TimerRunFailure, "image-or-harness-rejection"):
                runner.run_case(root=self.root, image=self.image, case=self.case, output_dir=self.output)
        self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")


class TimerBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.directory = self.root / "build/image"
        self.directory.mkdir(parents=True)
        self.image = self.directory / "image.elf"
        for name in runner.BUILD_ARTIFACTS:
            (self.directory / name).write_bytes(("artifact:" + name).encode())
        for name in runner.REQUIRED_SOURCE_INPUTS:
            source = self.root / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("source:" + name)
        self.bind()

    def tearDown(self):
        self.tmp.cleanup()

    def bind(self, mutation=0, optimization="O2"):
        manifest = {"artifact_category": corpus.ARTIFACT_CATEGORY, "contract_version": corpus.PROFILE,
            "test_abi": corpus.TEST_ABI, "timer_mutation": runner.mutation_metadata(mutation),
            "roots": [{"source": f"Lemma.Examples.Foundation.Timer.{name}", "signature": {"args": args},
                       "llvm": symbol}
                      for name, args, symbol in (("foreground", [], "core0_action_35"),
                                                 ("dispatch", ["u64"] * 9, "core0_action_41"))]}
        abi = {"mock_complete_abi": True}
        linked = [{"path": name, "kind": kind, "sha256": sha256(self.directory / name)}
                  for name, kind in (("startup.o", "lean-structured-timer-startup"), ("program.o", "test-timer-suite-llvm"))]
        provenance = {"schema_version": 2, "artifact_category": corpus.ARTIFACT_CATEGORY,
            "source_commit": "1" * 40, "optimization": optimization, "dirty_tree": False, "dirty_paths": [],
            "linked_inputs": linked, "source_inputs": [{"path": name, "sha256": sha256(self.root / name)}
                                                       for name in sorted(runner.REQUIRED_SOURCE_INPUTS)]}
        write_json(self.directory / "timer-suite-manifest.json", manifest)
        write_json(self.directory / "timer-test-abi.json", abi)
        write_json(self.directory / "provenance.json", provenance)
        hashes = {name: sha256(self.directory / name) for name in runner.BUILD_ARTIFACTS}
        write_json(self.directory / "build.json", {"schema_version": 1, "status": "pass",
            "artifact_category": corpus.ARTIFACT_CATEGORY, "optimization": optimization, "artifacts": hashes,
            "linked_inputs": linked})
        operations = ["uart.lsr.read8", "uart.thr.write8", "uart.lsr.read8", "uart.fcr.enable-reset"]
        source_counts = {"timer.set-interrupt": 3, "timer.set-compare": 4,
            "timer.read-time": 3, "irq.save-disable": 4, "timer.probe": 1,
            "irq.restore": 3, "timer.read-pending": 2}
        lowered = {"core0_timer_set_interrupt": 3, "core0_timer_set_compare": 4,
            "core0_timer_read_time": 3, "core0_irq_save_disable": 4, "core0_timer_probe": 1,
            "core0_irq_restore": 3, "core0_timer_read_pending": 2}
        post_lowered = dict(lowered)
        if optimization == "O2":
            post_lowered["core0_timer_set_compare"] = 3
        slots = {"_start": 16, "core0_io_fence": 0, "core0_trap_vector": 75,
            "core0_trap_ecall": 106, "core0_trap_breakpoint": 106,
            "core0_trap_fatal_dispatch": 0, "core0_trap_double_fault": 0,
            "core0_trap_unexpected_ecall": 0, "core0_trap_illegal_instruction": 0,
            "core0_timer_read_time": 1, "core0_timer_set_compare": 1,
            "core0_timer_read_pending": 0, "core0_irq_save_disable": 0,
            "core0_irq_restore": 0, "core0_timer_set_interrupt": 0, "core0_timer_probe": 106}
        foreground = {"bytes": 3536, "chain": ["core0_main", "core0_action_35"],
            "machine_entry": "core0_main", "checked_root": "core0_action_35",
            "capacity_bytes": 65520, "stack_region_bytes": 65536, "low_canary_bytes": 16}
        dispatcher = {"bytes": 2048, "chain": ["core0_action_41"],
            "checked_root": "core0_action_41", "capacity_bytes": 16048,
            "trap_frame_bytes": 288, "outgoing_argument_bytes": 16, "usable_trap_stack_bytes": 16352}
        body_hashes = dict(TIMER_MACHINE_BODY_SHA256)
        if mutation == 2:
            body_hashes["core0_timer_set_compare"] = DISABLE_ARMING_MACHINE_BODY_SHA256
        machine = {"approved_resume_pairs": 2, "compiled_gp_tp_free": True,
            "compiled_privileged_instructions": 0, "compiled_functions": 82,
            "fatal_stackless_self_loops": 2, "startup_functions": 16, "timer_functions": 7,
            "timer_mmio_accesses": 3, "timer_mmio_width_bits": 64, "timer_fence_operations": 14,
            "machine_csr_operations": 28, "mutation": corpus.MUTATION_IDENTITIES[mutation],
            "timer_machine_body_sha256": body_hashes,
            "timer_start_machine_body_sha256": {
                "O0": "1d57c4b2fb78146d7acf3aacc0a91c53d363d17bc6dba495aaf6443abf62f071",
                "O2": "29e19ddeb78734da1067ec6bded4f9eb06d70e17a20870503afbce0d6525c0d7",
            }[optimization],
            "timer_mmio_machine": {"access_count": 3, "width_bits": 64,
                "compiled_program_accesses": 0, "all_inferred_accesses_are_approved": True,
                "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof",
                "accesses": [{"function": function, "instruction": instruction,
                    "address": address, "machine_address": machine_address, "width_bits": 64}
                    for function, instruction, address, machine_address in (
                        ("_start", "sd", "0x02004000", "0x80000194"),
                        ("core0_timer_read_time", "ld", "0x0200bff8", "0x800017bc"),
                        ("core0_timer_set_compare", "sd", "0x02004000", "0x800017d4"))]},
            "machine_slot_sequences": slots,
            "machine_csr_by_function": {"_start": 5, "core0_trap_vector": 12,
                "core0_trap_ecall": 1, "core0_trap_breakpoint": 1,
                "core0_trap_unexpected_ecall": 1, "core0_timer_read_pending": 1,
                "core0_irq_save_disable": 1, "core0_irq_restore": 2,
                "core0_timer_set_interrupt": 2, "core0_timer_probe": 2},
            "timer_probe": {"iterations": 65536, "caller_saves": 16, "snapshot_registers": 31,
                "memory_slots": 106, "mie_window": "after sentinels, bounded counter only, before snapshots"},
            "startup": {"mutation": corpus.MUTATION_IDENTITIES[mutation],
                "startup_compare_parked": True, "timer_functions": 7, "timer_mmio_width_bits": 64,
                "timer_probe_iterations": 65536, "probe_registers": 31,
                "csr_roles": ["mstatus.MIE", "mie.MTIE", "mip.MTIP"],
                "synchronous_trap_substrate": "exact core0-v0.6 structured sequence"},
            "layout": {"frame_bytes": 288, "canaries": 6,
                "regions": {"trap_stack": [0x80810000, 0x4000],
                    "trap_probe_context": [0x80815000, 0x1000], "trap_probe_stack": [0x80818000, 0x1000]}}}
        device = {"access_count": 4, "byte_accesses_only": True, "ordered_fence_calls": 8,
            "denied_region_metadata_materializations": 7 if optimization == "O0" else 0,
            "register_use_audit": {"inferred_uart_accesses": 4, "all_inferred_accesses_are_approved": True,
                "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
            "fence_implementation": "fence iorw,iorw; ret",
            "accesses": [{"operation": operation, "function": function, "instruction": instruction,
                          "address": address, "fence_before": True, "fence_after": True}
                         for operation, function, instruction, address in zip(operations,
                             ("core0_action_0", "core0_action_0", "core0_action_13", "core0_action_35"),
                             ("lbu", "sb", "lbu", "sb"),
                             ("0x10000005", "0x10000000", "0x10000005", "0x10000002"), strict=True)]}
        write_json(self.directory / "audit.json", {"schema_version": 1, "status": "pass",
            "artifact_category": corpus.ARTIFACT_CATEGORY, "optimization": optimization,
            "provenance_schema_version": 2, "source_commit": "1" * 40, "dirty_tree": False,
            "hashes": hashes, "linked_inputs": linked, "manifest": manifest, "timer_test_abi": abi,
            "timer_ir_audit": {"optimization": optimization,
                "timer_calls": {"source": source_counts, "pre_optimization": lowered, "post_optimization": post_lowered},
                "post_optimization_tail_merge": {
                    "function": "core0_action_38", "source_sites": 2, "machine_calls": 1,
                    "selector": "two-input phi from the mutually exclusive deadline branches",
                } if optimization == "O2" else None,
                "optimizer_intrinsics": {"llvm.umin.i64": 1 if optimization == "O2" else 0,
                    "function": "core0_scalar_27" if optimization == "O2" else None,
                    "upper_bound": 16 if optimization == "O2" else None},
                "machine_timer_mmio_in_program": 0,
                "bool_machine_arguments": {"calls": 6, "lowering": "canonical i1-to-i64 zext"},
                "uart": {label: {"operations": operations, "accesses": 4,
                    "functions": ["core0_action_0", "core0_action_13", "core0_action_35"]}
                    for label in ("pre", "post")},
                "memory": {"access_count": 2, "loads": 1, "stores": 1,
                    "source_memory_site_count": 2, "volatile_policy": True,
                    "accesses": [{"access": "read"}, {"access": "write"}], "checked_result": {"verified": True}}},
            "timer_machine_audit": machine, "device_machine_audit": device,
            "stack_sizes": {"call_graph": {"acyclic": True, "dynamic_alloca": False,
                "stack_limit_bytes": 65536, "foreground": foreground, "trap_dispatcher": dispatcher,
                "frame_chains": {"core0_main": {key: foreground[key] for key in ("bytes", "chain")},
                    "core0_action_41": {key: dispatcher[key] for key in ("bytes", "chain")}}}}})

    def validate(self, mutation=0):
        with mock.patch.object(runner, "_validate_manifest") as schema:
            result = runner.validate_image_binding(self.image, root=self.root, mutation=mutation)
            schema.assert_called_once()
            return result

    def test_complete_current_bundle_and_mutation_selection(self):
        self.validate()
        with self.assertRaisesRegex(Core0Error, "mutation"):
            self.validate(1)
        self.bind(1)
        self.validate(1)
        self.bind(2, "O0")
        self.validate(2)

    def test_each_required_artifact_and_hash_cannot_be_omitted(self):
        for name in runner.BUILD_ARTIFACTS:
            with self.subTest(name=name):
                contents = (self.directory / name).read_bytes()
                (self.directory / name).unlink()
                build = json.loads((self.directory / "build.json").read_text())
                del build["artifacts"][name]
                write_json(self.directory / "build.json", build)
                with self.assertRaises(Core0Error):
                    self.validate()
                (self.directory / name).write_bytes(contents)
                self.bind()

    def test_all_retained_audit_hashes_and_source_hashes_are_required(self):
        for name in runner.AUDIT_ARTIFACTS:
            audit = json.loads((self.directory / "audit.json").read_text())
            audit["hashes"][name] = "0" * 64
            write_json(self.directory / "audit.json", audit)
            with self.assertRaises(Core0Error):
                self.validate()
            self.bind()
        (self.root / "examples/foundation/TimerConformance.lean").write_text("changed source")
        with self.assertRaisesRegex(Core0Error, "stale or escaped"):
            self.validate()

    def test_missing_mandatory_timer_audit_evidence_is_not_success(self):
        for name in ("timer_ir_audit", "timer_machine_audit", "device_machine_audit", "stack_sizes"):
            audit = json.loads((self.directory / "audit.json").read_text())
            del audit[name]
            write_json(self.directory / "audit.json", audit)
            with self.assertRaises(Core0Error):
                self.validate()
            self.bind()

    def test_exact_factored_console_function_count_rejects_stale_or_open_counts(self):
        self.validate()
        for count in (80, 81, 83, True, 82.0, None):
            with self.subTest(count=count):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["timer_machine_audit"]["compiled_functions"] = count
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "machine compiled_functions"):
                    self.validate()
                self.bind()

    def test_weakened_final_machine_evidence_is_rejected(self):
        for path, value in (
            (("timer_machine_audit", "compiled_privileged_instructions"), 1),
            (("timer_machine_audit", "compiled_functions"), 79),
            (("timer_machine_audit", "compiled_gp_tp_free"), False),
            (("timer_machine_audit", "timer_mmio_width_bits"), 32),
            (("timer_machine_audit", "machine_slot_sequences", "core0_timer_probe"), 105),
            (("timer_machine_audit", "machine_csr_by_function", "core0_trap_vector"), 11),
            (("timer_machine_audit", "timer_probe", "iterations"), 65537),
            (("timer_machine_audit", "startup", "startup_compare_parked"), False),
            (("timer_machine_audit", "layout", "canaries"), 0),
            (("timer_machine_audit", "timer_mmio_accesses"), 3.0),
            (("timer_machine_audit", "timer_functions"), True),
            (("timer_machine_audit", "machine_csr_operations"), 11),
            (("timer_machine_audit", "timer_mmio_machine"), None),
            (("timer_machine_audit", "timer_mmio_machine", "access_count"), 3.0),
            (("timer_machine_audit", "timer_mmio_machine", "width_bits"), 32),
            (("timer_machine_audit", "timer_mmio_machine", "compiled_program_accesses"), 1),
            (("timer_machine_audit", "timer_mmio_machine", "all_inferred_accesses_are_approved"), False),
            (("timer_machine_audit", "timer_mmio_machine", "scope"), "unknown"),
            (("timer_machine_audit", "timer_mmio_machine", "accesses"), []),
        ):
            with self.subTest(path=path):
                audit = json.loads((self.directory / "audit.json").read_text())
                target = audit
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                write_json(self.directory / "audit.json", audit)
                with self.assertRaises(Core0Error):
                    self.validate()
                self.bind()

    def test_final_clint_sites_and_entry_body_cannot_be_forged(self):
        for optimization in ("O0", "O2"):
            self.bind(optimization=optimization)
            self.validate()
            good = json.loads((self.directory / "audit.json").read_text())
            for field, value in (("function", "core0_action_20"), ("instruction", "sw"),
                ("address", "0x02004008"), ("machine_address", "0x80000198"),
                ("width_bits", 32)):
                with self.subTest(optimization=optimization, field=field):
                    audit = json.loads(json.dumps(good))
                    audit["timer_machine_audit"]["timer_mmio_machine"]["accesses"][0][field] = value
                    write_json(self.directory / "audit.json", audit)
                    with self.assertRaisesRegex(Core0Error, "CLINT access inventory"):
                        self.validate()
            wrong_profile = "O0" if optimization == "O2" else "O2"
            self.bind(optimization=wrong_profile)
            wrong_hash = json.loads((self.directory / "audit.json").read_text())["timer_machine_audit"]["timer_start_machine_body_sha256"]
            for entry_hash in (None, "0" * 64, wrong_hash):
                with self.subTest(optimization=optimization, entry_hash=entry_hash):
                    audit = json.loads(json.dumps(good))
                    audit["timer_machine_audit"]["timer_start_machine_body_sha256"] = entry_hash
                    # Restore the profile-bound manifests too, not only audit.json.
                    self.bind(optimization=optimization)
                    write_json(self.directory / "audit.json", audit)
                    with self.assertRaisesRegex(Core0Error, "machine entry body"):
                        self.validate()
            self.bind()

    def test_final_primitive_body_hashes_are_complete_and_mutation_aware(self):
        for mutation in (0, 1, 2):
            self.bind(mutation=mutation)
            self.validate(mutation=mutation)
            good = json.loads((self.directory / "audit.json").read_text())
            expected = good["timer_machine_audit"]["timer_machine_body_sha256"]
            missing = dict(expected)
            del missing["core0_timer_probe"]
            incorrect = dict(expected, core0_timer_probe="0" * 64)
            extra = dict(expected, unknown_primitive="0" * 64)
            wrong_compare = dict(expected, core0_timer_set_compare=(
                TIMER_MACHINE_BODY_SHA256["core0_timer_set_compare"] if mutation == 2
                else DISABLE_ARMING_MACHINE_BODY_SHA256))
            for hashes in (None, {}, missing, incorrect, extra, wrong_compare):
                with self.subTest(mutation=mutation, hashes=hashes):
                    audit = json.loads(json.dumps(good))
                    audit["timer_machine_audit"]["timer_machine_body_sha256"] = hashes
                    write_json(self.directory / "audit.json", audit)
                    with self.assertRaisesRegex(Core0Error, "primitive bodies"):
                        self.validate(mutation=mutation)
            self.bind()

    def test_optimizer_tail_merge_and_intrinsic_are_exactly_profile_scoped(self):
        for optimization in ("O0", "O2"):
            self.bind(optimization=optimization)
            self.validate()
            good = json.loads((self.directory / "audit.json").read_text())
            for field, value in (
                ("optimizer_intrinsics", {}),
                ("optimizer_intrinsics", {"llvm.umin.i64": 1,
                    "function": "core0_scalar_27", "upper_bound": 17}),
                ("post_optimization_tail_merge", {}),
                ("post_optimization_tail_merge", {"function": "core0_action_38",
                    "source_sites": 2, "machine_calls": 2,
                    "selector": "two-input phi from the mutually exclusive deadline branches"}),
            ):
                with self.subTest(optimization=optimization, field=field, value=value):
                    audit = json.loads(json.dumps(good))
                    audit["timer_ir_audit"][field] = value
                    write_json(self.directory / "audit.json", audit)
                    with self.assertRaises(Core0Error):
                        self.validate()
            audit = json.loads(json.dumps(good))
            audit["timer_ir_audit"]["timer_calls"]["post_optimization"]["core0_timer_set_compare"] = (
                4 if optimization == "O2" else 3)
            write_json(self.directory / "audit.json", audit)
            with self.assertRaises(Core0Error):
                self.validate()
            self.bind()

    def test_ir_uart_denial_and_resource_evidence_cannot_be_weakened(self):
        for path, value in (
            (("timer_ir_audit", "timer_calls", "source", "timer.probe"), 0),
            (("timer_ir_audit", "bool_machine_arguments", "calls"), 5),
            (("timer_ir_audit", "machine_timer_mmio_in_program"), 1),
            (("timer_ir_audit", "memory", "volatile_policy"), False),
            (("timer_ir_audit", "uart", "post", "accesses"), 3),
            (("device_machine_audit", "ordered_fence_calls"), 7),
            (("device_machine_audit", "denied_region_metadata_materializations"), 7),
            (("device_machine_audit", "register_use_audit", "all_inferred_accesses_are_approved"), False),
            (("device_machine_audit", "accesses"), []),
            (("stack_sizes", "call_graph", "acyclic"), False),
            (("stack_sizes", "call_graph", "foreground", "bytes"), 65521),
            (("stack_sizes", "call_graph", "foreground", "checked_root"), "wrong_root"),
            (("stack_sizes", "call_graph", "trap_dispatcher", "capacity_bytes"), 65520),
        ):
            with self.subTest(path=path):
                audit = json.loads((self.directory / "audit.json").read_text())
                target = audit
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                write_json(self.directory / "audit.json", audit)
                with self.assertRaises(Core0Error):
                    self.validate()
                self.bind()
        self.bind(optimization="O0")
        self.validate()
        audit = json.loads((self.directory / "audit.json").read_text())
        audit["device_machine_audit"]["denied_region_metadata_materializations"] = 0
        write_json(self.directory / "audit.json", audit)
        with self.assertRaisesRegex(Core0Error, "denial"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
