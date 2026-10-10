#!/usr/bin/env python3
"""Adversarial Gate 7 protocol/cleanup tests; no QEMU dependency."""
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
import gate7_corpus as corpus
import run_trap_case as runner
from core0_common import CommandResult, Core0Error, sha256, write_json


SYMBOLS = {"__trap_ecall_site": 0x80000600, "__trap_ecall_resume": 0x80000604,
           "__trap_breakpoint_site": 0x80001000, "__trap_breakpoint_resume": 0x80001004,
           "__trap_unexpected_ecall_site": 0x80001800, "__trap_illegal_instruction_site": 0x80001808}


def frame(identifier, value, status=0):
    return b"LMS6" + bytes((1, status, 8, 0)) + struct.pack("<QQ", identifier, value)


def positive(case):
    return corpus.READY + b"".join(frame(identifier, value) for identifier, value in zip(
        corpus.RESULT_IDS, (corpus.checksum(case.seed, case.count), 2 * case.count, 14, 0)))


def fatal(case, *, cause=None, pc=None, status=0xA00001800, tval=0, mie=0):
    values = (cause if cause is not None else (11 if case.scenario == 1 else 2),
              pc if pc is not None else SYMBOLS["__trap_unexpected_ecall_site" if case.scenario == 1 else "__trap_illegal_instruction_site"],
              status, tval, mie)
    return corpus.READY + b"".join(frame(identifier, value, 18) for identifier, value in zip(corpus.FATAL_IDS, values))


class TrapProtocolTests(unittest.TestCase):
    def test_positive_requires_actual_count_denials_context_and_checksum(self):
        for case in corpus.POSITIVE_CASES:
            self.assertEqual(runner.validate_transcript(case, positive(case), 0, SYMBOLS)["outcome"], "verified-positive")
        case = corpus.POSITIVE_CASES[4]
        good = positive(case)
        for index in range(4):
            bad = bytearray(good)
            bad[len(corpus.READY) + index * 24 + 16] ^= 1
            with self.assertRaisesRegex(runner.TrapRunFailure, "behavior-mismatch"):
                runner.validate_transcript(case, bytes(bad), 0, SYMBOLS)

    def test_fatal_uses_exact_elf_pc_cause_csrs_and_tval(self):
        for case in corpus.NEGATIVE_CASES[:2]:
            self.assertEqual(runner.validate_transcript(case, fatal(case), 18, SYMBOLS)["outcome"], "verified-fatal-diagnostic")
            for kwargs in ({"cause": 3}, {"pc": SYMBOLS["__trap_ecall_site"]}, {"status": 0x1808},
                           {"status": 0x1880}, {"status": 0x21800}, {"mie": 128}, {"tval": 0x1234}):
                with self.subTest(scenario=case.scenario, kwargs=kwargs):
                    with self.assertRaisesRegex(runner.TrapRunFailure, "diagnostic-mismatch"):
                        runner.validate_transcript(case, fatal(case, **kwargs), 18, SYMBOLS)
        illegal = corpus.NEGATIVE_CASES[1]
        runner.validate_transcript(illegal, fatal(illegal, tval=0xB), 18, SYMBOLS)
        with self.assertRaises(runner.TrapRunFailure):
            runner.validate_transcript(corpus.NEGATIVE_CASES[0], fatal(corpus.NEGATIVE_CASES[0], tval=0xB), 18, SYMBOLS)

    def test_exact_empty_payload_for_nested_and_semantic_exits(self):
        for case in corpus.NEGATIVE_CASES[2:]:
            code = corpus.expected_exit(case)
            runner.validate_transcript(case, corpus.READY, code, SYMBOLS)
            with self.assertRaises(runner.TrapRunFailure):
                runner.validate_transcript(case, corpus.READY + frame(0x7001, 11, 18), code, SYMBOLS)
            with self.assertRaisesRegex(runner.TrapRunFailure, "target-exit-mismatch"):
                runner.validate_transcript(case, corpus.READY, -11, SYMBOLS)

    def test_mutant_only_exact_context_failure_not_clean_fatal_or_protocol_error(self):
        case = corpus.MUTANT_CASE
        expected = corpus.READY + frame(0x71FF, 0x40000, 20)
        self.assertEqual(runner.validate_transcript(case, expected, 20, SYMBOLS, mutant=True)["outcome"], "verified-behavioral-context-mismatch")
        for data, code in ((positive(case), 0), (fatal(corpus.NEGATIVE_CASES[0]), 18),
                           (corpus.READY + frame(0x71FF, 0x80000, 20), 20),
                           (expected + frame(0x71FF, 0x40000, 20), 20)):
            with self.assertRaises(runner.TrapRunFailure):
                runner.validate_transcript(case, data, code, SYMBOLS, mutant=True)

    def test_protocol_is_not_prefix_or_permissive_decoder(self):
        case = corpus.POSITIVE_CASES[0]
        good = positive(case)
        bad_frames = (b"JUNK" + good, good[:-1], good + b"x", good.replace(b"LMS6", b"LMS7", 1),
                      good[:len(corpus.READY)] + frame(0x7101, 0, 10))
        for blob in bad_frames:
            with self.assertRaises(runner.TrapRunFailure):
                runner.validate_transcript(case, blob, 0, SYMBOLS)

    def test_site_symbols_require_exact_four_byte_resume_pairs(self):
        text = "\n".join(f"{value:016x} t {key}" for key, value in SYMBOLS.items()).encode()
        result = CommandResult(("llvm-nm",), 0, text, b"", 0.1)
        with mock.patch.object(runner, "checked", return_value=result):
            self.assertEqual(runner.symbol_addresses(Path("image.elf"), root=ROOT), SYMBOLS)
        for bad in (text.replace(b"80000604", b"80000608"), text + b"\n80000600 t __trap_ecall_site", text.splitlines()[0]):
            with mock.patch.object(runner, "checked", return_value=CommandResult((), 0, bad, b"", 0)):
                with self.assertRaises(Core0Error):
                    runner.symbol_addresses(Path("image.elf"), root=ROOT)


class TrapProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = self.root / "build" / "image" / "image.elf"
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b"test-image")
        self.output = self.root / "build" / "runs" / "case"
        self.case = corpus.POSITIVE_CASES[2]

    def tearDown(self):
        self.tmp.cleanup()

    def run_child(self, program, timeout=2):
        with mock.patch.object(runner, "validate_image_binding", return_value={}), \
             mock.patch.object(runner, "require_tools", return_value={}), \
             mock.patch.object(runner, "symbol_addresses", return_value=SYMBOLS), \
             mock.patch.object(runner, "qemu_argv", return_value=(sys.executable, "-c", program)):
            return runner.run_case(root=self.root, image=self.image, case=self.case,
                                   output_dir=self.output, timeout_seconds=timeout)

    def test_success_retains_exact_raw_fixture_and_transcript(self):
        report = self.run_child(f"import sys;sys.stdout.buffer.write(bytes.fromhex('{positive(self.case).hex()}'))")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual((self.output / "runtime-input.bin").read_bytes(), corpus.fixture_bytes(self.case))
        self.assertEqual((self.output / "uart.bin").read_bytes(), positive(self.case))
        self.assertEqual(json.loads((self.output / "run.json").read_text()), report)

    def test_stderr_rejects_otherwise_valid_result_and_retains_diagnostic(self):
        program = f"import sys;sys.stdout.buffer.write(bytes.fromhex('{positive(self.case).hex()}'));sys.stderr.write('QEMU fault\\n')"
        with self.assertRaisesRegex(runner.TrapRunFailure, "emulator-stderr"):
            self.run_child(program)
        report = json.loads((self.output / "run.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual((self.output / "stderr.bin").read_bytes(), b"QEMU fault\n")

    def test_timeout_kills_group_reaps_and_retains_partial_bytes(self):
        program = f"import sys,time;sys.stdout.buffer.write(bytes.fromhex('{corpus.READY.hex()}'));sys.stdout.flush();time.sleep(10)"
        with self.assertRaisesRegex(runner.TrapRunFailure, "target-timeout"):
            self.run_child(program, timeout=0.2)
        report = json.loads((self.output / "run.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["timeout_cleanup"], {"process_group_killed": True, "process_reaped": True})
        self.assertEqual((self.output / "uart.bin").read_bytes(), corpus.READY)
        with self.assertRaises(ProcessLookupError):
            os.kill(report["pid"], 0)

    def test_image_rejection_cannot_leave_prior_pass_report(self):
        self.output.mkdir(parents=True)
        (self.output / "run.json").write_text('{"status":"PASS"}')
        with mock.patch.object(runner, "validate_image_binding", side_effect=Core0Error("stale artifact")):
            with self.assertRaisesRegex(runner.TrapRunFailure, "image-or-harness-rejection"):
                runner.run_case(root=self.root, image=self.image, case=self.case, output_dir=self.output)
        self.assertEqual(json.loads((self.output / "run.json").read_text())["status"], "FAIL")
        self.assertFalse((self.output / "runtime-input.bin").exists())


class TrapBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.directory = self.root / "build/image"
        self.directory.mkdir(parents=True)
        self.image = self.directory / "image.elf"
        for name in runner.BUILD_ARTIFACTS - {"trap-suite-manifest.json", "trap-test-abi.json", "provenance.json"}:
            (self.directory / name).write_bytes(b"artifact:" + name.encode())
        for name in runner.REQUIRED_SOURCE_INPUTS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source:" + name)
        self.manifest = {"artifact_category": corpus.ARTIFACT_CATEGORY, "contract_version": corpus.PROFILE,
                         "test_abi": corpus.TEST_ABI,
                         "trap_contract": json.loads(json.dumps(runner.TRAP_CONTRACT)),
                         "roots": [{"source": "Lemma.Examples.Foundation.Trap.foreground", "signature": {"args": []}},
                                   {"source": "Lemma.Examples.Foundation.Trap.dispatch", "signature": {"args": ["u64"] * 9}}],
                         "restore_mutation": {"identity": "none", "production_selectable": False,
                                              "transform_stage": "structured-machine-restore", "match_count": 0}}
        ops = (("trap.ecall", "core0_trap_ecall", "trapEcall"),
               ("trap.breakpoint", "core0_trap_breakpoint", "trapBreakpoint"),
               ("trap.unexpected-ecall", "core0_trap_unexpected_ecall", "trapUnexpectedEcall"),
               ("trap.illegal-instruction", "core0_trap_illegal_instruction", "trapIllegalInstruction"))
        self.manifest["used_trap_ops"] = [{"stable_id": identifier, "llvm_symbol": symbol,
            "source_identity": f"Lemma.Core0.Memory.Action.{source}", "effects": ["sync-trap", "machine-state"],
            "arguments": [], "result": "u64-context-mask"} for identifier, symbol, source in ops]
        self.abi = {"schema_version": 1, "contract_version": corpus.PROFILE, "name": corpus.TEST_ABI,
            "byte_order": "little-endian", "ready": corpus.READY.decode(),
            "runtime_fixture_address": "0x0000000081000000", "runtime_fixture_bytes": 24,
            "runtime_fields": ["seed:u64@0", "count:u64@8", "scenario:u64@16"], "maximum_count": 64,
            "response_bytes": 24, "response_magic": "LMS6", "result_ids": list(corpus.RESULT_IDS),
            "fatal_ids": list(corpus.FATAL_IDS), "context_failure_id": corpus.MUTANT_ID,
            "scenarios": {"0": "control-and-interrupted-fold", "1": "unauthorized-ecall",
                          "2": "illegal-instruction", "4": "nested-ecall-in-compiled-dispatch"}}
        self.bind()

    def tearDown(self):
        self.tmp.cleanup()

    def bind(self):
        write_json(self.directory / "trap-suite-manifest.json", self.manifest)
        write_json(self.directory / "trap-test-abi.json", self.abi)
        linked = [{"path": name, "kind": kind, "sha256": sha256(self.directory / name)}
                  for name, kind in (("startup.o", "lean-structured-trap-startup"),
                                     ("program.o", "test-trap-suite-llvm"))]
        provenance = {"schema_version": 2, "artifact_category": corpus.ARTIFACT_CATEGORY,
            "source_commit": "1" * 40, "optimization": "O2", "dirty_tree": False,
            "dirty_paths": [], "linked_inputs": linked,
            "source_inputs": [{"path": name, "sha256": sha256(self.root / name)}
                              for name in sorted(runner.REQUIRED_SOURCE_INPUTS)]}
        write_json(self.directory / "provenance.json", provenance)
        hashes = {name: sha256(self.directory / name) for name in runner.BUILD_ARTIFACTS}
        write_json(self.directory / "build.json", {"schema_version": 1,
            "artifact_category": corpus.ARTIFACT_CATEGORY, "optimization": "O2",
            "status": "pass", "artifacts": hashes, "linked_inputs": linked})
        write_json(self.directory / "audit.json", {"schema_version": 1,
            "artifact_category": corpus.ARTIFACT_CATEGORY, "provenance_schema_version": 2,
            "source_commit": "1" * 40, "optimization": "O2", "dirty_tree": False,
            "linked_inputs": linked, "status": "pass", "manifest": self.manifest,
            "hashes": {name: hashes[name] for name in runner.AUDIT_ARTIFACTS},
            "trap_machine_audit": {"approved_resume_pairs": 2, "compiled_gp_tp_free": True,
                "compiled_functions": 50, "fatal_stackless_self_loops": 2,
                "compiled_privileged_instructions": 0,
                "machine_slot_sequences": {"core0_trap_vector": 75,
                    "core0_trap_ecall": 106, "core0_trap_breakpoint": 106},
                "machine_csr_operations": 11,
                "startup": {"restore_mutation": self.manifest["restore_mutation"]["identity"],
                    "frame_bytes": 288, "integer_registers": 31, "csr_snapshots": 5,
                    "probe_registers": 31, "canaries": 6},
                "layout": {"frame_bytes": 288, "canaries": 6}},
            "trap_ir_audit": {"optimization": "O2", "memory": {"guards_verified": True},
                "trap_calls": {"core0_trap_ecall": 3, "core0_trap_breakpoint": 1,
                    "core0_trap_unexpected_ecall": 1, "core0_trap_illegal_instruction": 1},
                "device": {label: {"operations": ["uart.lsr.read8", "uart.thr.write8",
                    "uart.lsr.read8", "uart.fcr.enable-reset"], "accesses": 4}
                    for label in ("pre", "post")}},
            "trap_test_abi": self.abi,
            "device_machine_audit": {"access_count": 4, "byte_accesses_only": True,
                "ordered_fence_calls": 8, "denied_region_metadata_materializations": 0,
                "register_use_audit": {"inferred_uart_accesses": 4,
                    "all_inferred_accesses_are_approved": True,
                    "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof"},
                "fence_implementation": "fence iorw,iorw; ret",
                "accesses": [{"operation": operation, "function": function,
                    "instruction": instruction, "address": f"0x{address:08x}",
                    "fence_before": True, "fence_after": True}
                    for operation, function, instruction, address in runner.TRAP_MACHINE_ACCESS_SEQUENCE]}})

    def validate(self, **kwargs):
        return runner.validate_image_binding(self.image, root=self.root, **kwargs)

    def replace_record(self, name, value):
        """Rebind a changed provenance only in build, not in the retained audit."""
        write_json(self.directory / name, value)
        build = json.loads((self.directory / "build.json").read_text())
        build["artifacts"][name] = sha256(self.directory / name)
        write_json(self.directory / "build.json", build)

    def test_hash_closure_and_correct_normal_mutant_selection(self):
        self.validate()
        with self.assertRaisesRegex(Core0Error, "mutation"):
            self.validate(mutant=True)
        (self.directory / "program.opt.ll").write_bytes(b"changed after audit")
        with self.assertRaisesRegex(Core0Error, "stale trap build"):
            self.validate()

    def test_rebound_wrong_abi_root_or_effect_still_rejected(self):
        self.abi["runtime_fixture_bytes"] = 32
        self.bind()
        with self.assertRaisesRegex(Core0Error, "ABI differs"):
            self.validate()
        self.abi["runtime_fixture_bytes"] = 24
        self.manifest["roots"][1]["signature"]["args"] = ["u64"] * 8
        self.bind()
        with self.assertRaisesRegex(Core0Error, "signature"):
            self.validate()
        self.manifest["roots"][1]["signature"]["args"] = ["u64"] * 9
        self.manifest["used_trap_ops"][0]["effects"] = []
        self.bind()
        with self.assertRaisesRegex(Core0Error, "catalog"):
            self.validate()

    def test_missing_required_build_hash_or_stale_audit_cannot_run(self):
        build = json.loads((self.directory / "build.json").read_text())
        del build["artifacts"]["program.opt.ll"]
        write_json(self.directory / "build.json", build)
        with self.assertRaisesRegex(Core0Error, "artifact catalog differs"):
            self.validate()
        self.bind()
        audit = json.loads((self.directory / "audit.json").read_text())
        audit["hashes"]["image.elf"] = "0" * 64
        write_json(self.directory / "audit.json", audit)
        with self.assertRaisesRegex(Core0Error, "stale trap machine audit"):
            self.validate()

    def test_artifact_catalog_matches_the_actual_build_and_audit(self):
        import audit_core0
        import build_core0
        self.assertEqual(runner.AUDIT_ARTIFACTS, set(audit_core0.TRAP_SUITE_REQUIRED_ARTIFACTS))
        self.assertEqual(runner.BUILD_ARTIFACTS, set(build_core0.TRAP_SUITE_GENERATED_BY_LEAN) | {
            "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map",
            "platform.dtb", "platform.dts", "provenance.json"})

    def test_every_required_file_must_exist_even_when_omitted_from_record(self):
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

    def test_all_audit_hashes_must_bind_current_artifacts(self):
        for name in runner.AUDIT_ARTIFACTS:
            with self.subTest(name=name):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["hashes"][name] = "0" * 64
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "stale trap machine audit"):
                    self.validate()
                self.bind()
        (self.directory / "program.opt.ll").write_bytes(b"changed optimized IR")
        build = json.loads((self.directory / "build.json").read_text())
        build["artifacts"]["program.opt.ll"] = sha256(self.directory / "program.opt.ll")
        write_json(self.directory / "build.json", build)
        with self.assertRaisesRegex(Core0Error, "stale trap machine audit"):
            self.validate()

    def test_missing_trap_specific_audit_or_abi_binding_is_rejected(self):
        for name in ("trap_machine_audit", "trap_ir_audit", "trap_test_abi", "device_machine_audit"):
            with self.subTest(name=name):
                audit = json.loads((self.directory / "audit.json").read_text())
                del audit[name]
                write_json(self.directory / "audit.json", audit)
                with self.assertRaises(Core0Error):
                    self.validate()
                self.bind()

    def test_empty_or_weakened_trap_audit_invariants_are_rejected(self):
        for name, value in (("trap_machine_audit", {}), ("trap_ir_audit", {}),
                            ("trap_machine_audit", {"verified": True}),
                            ("trap_ir_audit", {"optimization": "O0"})):
            with self.subTest(name=name, value=value):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit[name] = value
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "trap machine audit"):
                    self.validate()
                self.bind()
        audit = json.loads((self.directory / "audit.json").read_text())
        audit["trap_machine_audit"]["startup"]["restore_mutation"] = "restore-s3-from-s4"
        write_json(self.directory / "audit.json", audit)
        with self.assertRaisesRegex(Core0Error, "startup/context"):
            self.validate()

    def test_exact_factored_console_function_count_rejects_stale_or_open_counts(self):
        self.validate()
        for count in (48, 49, 51, True, 50.0, None):
            with self.subTest(count=count):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["trap_machine_audit"]["compiled_functions"] = count
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "trap machine audit compiled function closure"):
                    self.validate()
                self.bind()

    def test_final_machine_register_slot_csr_and_uart_invariants_are_closed(self):
        for field, value in (("compiled_privileged_instructions", 1),
                             ("compiled_privileged_instructions", False),
                             ("compiled_functions", 47),
                             ("machine_slot_sequences", {}), ("machine_csr_operations", 10)):
            with self.subTest(field=field, value=value):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["trap_machine_audit"][field] = value
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "trap machine audit"):
                    self.validate()
                self.bind()
        for field, value in (("access_count", 3), ("byte_accesses_only", False),
                             ("ordered_fence_calls", 7),
                             ("denied_region_metadata_materializations", 24),
                             ("register_use_audit", {}), ("accesses", [])):
            with self.subTest(field=field, value=value):
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["device_machine_audit"][field] = value
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "final UART machine audit"):
                    self.validate()
                self.bind()

    def test_denied_metadata_is_exactly_optimization_aware(self):
        self.assertEqual(sum(runner.TRAP_MACHINE_DENIED_METADATA.values()), 24)
        for optimization, denied in (("O0", 24), ("O2", 0)):
            with self.subTest(optimization=optimization):
                self.bind()
                provenance = json.loads((self.directory / "provenance.json").read_text())
                provenance["optimization"] = optimization
                self.replace_record("provenance.json", provenance)
                build = json.loads((self.directory / "build.json").read_text())
                build["optimization"] = optimization
                write_json(self.directory / "build.json", build)
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["hashes"]["provenance.json"] = sha256(self.directory / "provenance.json")
                audit["optimization"] = optimization
                audit["trap_ir_audit"]["optimization"] = optimization
                audit["device_machine_audit"]["denied_region_metadata_materializations"] = denied
                write_json(self.directory / "audit.json", audit)
                self.validate()
                audit["device_machine_audit"]["denied_region_metadata_materializations"] = 0 if denied else 24
                write_json(self.directory / "audit.json", audit)
                with self.assertRaisesRegex(Core0Error, "final UART machine audit"):
                    self.validate()

    def test_source_identity_requires_consistent_complete_provenance(self):
        for field, value in (("schema_version", 1), ("source_commit", "short"),
                             ("optimization", "O0"), ("dirty_tree", True),
                             ("source_inputs", []), ("linked_inputs", [])):
            with self.subTest(field=field):
                provenance = json.loads((self.directory / "provenance.json").read_text())
                provenance[field] = value
                self.replace_record("provenance.json", provenance)
                audit = json.loads((self.directory / "audit.json").read_text())
                audit["hashes"]["provenance.json"] = sha256(self.directory / "provenance.json")
                write_json(self.directory / "audit.json", audit)
                with self.assertRaises(Core0Error):
                    self.validate()
                self.bind()
        source = self.root / "examples/foundation/TrapConformance.lean"
        source.write_text("changed source after build and audit")
        with self.assertRaisesRegex(Core0Error, "stale or escaped trap source input"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
