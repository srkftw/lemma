#!/usr/bin/env python3
"""Focused fail-closed tests for the Gate 9 monitor audit."""

from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_monitor  # noqa: E402
from core0_common import Core0Error  # noqa: E402


def _action(source: str, index: int, dependencies: list[str]) -> dict[str, object]:
    calls = " ".join(f"(action.call {dependency} [])" for dependency in dependencies)
    return {
        "source": source,
        "llvm": f"core0_action_{index}",
        "signature": {"args": []},
        "scalar_dependencies": [],
        "action_dependencies": dependencies,
        "direct_effects": [],
        "transitive_effects": [],
        "body": f"(action.done (lit u8 0) (lit u64 0) {calls})",
        "noinline": True,
    }


class MonitorProtocolContractTests(unittest.TestCase):
    def test_command_ids_lengths_and_response_shape_are_closed(self) -> None:
        self.assertEqual(
            [(item["id"], item["name"], item["payload_bytes"])
             for item in audit_monitor.COMMANDS],
            [
                (1, "HELLO", 0), (2, "STATUS", 0), (3, "EVAL", 32),
                (4, "FILL", 24), (5, "CHECKSUM", 16), (6, "TRAP_TEST", 8),
                (7, "TIMER_START", 8), (8, "TIMER_STOP", 0),
                (9, "TICKS", 16), (10, "EXIT", 0),
            ],
        )
        self.assertEqual(audit_monitor.MONITOR_ABI["response_bytes"], 48)
        self.assertEqual(audit_monitor.MONITOR_ABI["response_payload_bytes"], 32)
        self.assertEqual(audit_monitor.MONITOR_ABI["ready"], "LEMMA_MONITOR/1\nREADY\n")
        self.assertEqual(
            audit_monitor.MONITOR_ABI["monitor_contract"]["timer"]["minimum_period"],
            10000,
        )
        self.assertEqual(
            audit_monitor.MONITOR_ABI["monitor_contract"],
            audit_monitor.MONITOR_CONTRACT,
        )
        self.assertEqual(
            audit_monitor.HELLO_CONTRACT["tag_u64"], "0x31304e4f4d4d454c"
        )

    def test_context_dependent_statuses_are_not_claimed_always_terminal(self) -> None:
        by_code = {item["code"]: item for item in audit_monitor.STATUSES}
        self.assertFalse(by_code[16]["always_terminal"])
        self.assertFalse(by_code[20]["always_terminal"])
        self.assertFalse(by_code[10]["wire_status"])
        self.assertFalse(by_code[18]["wire_status"])
        self.assertFalse(by_code[19]["wire_status"])

    def test_abi_mutation_rejects(self) -> None:
        manifest = {
            "contract_version": audit_monitor.CONTRACT_VERSION,
            "test_abi": audit_monitor.TEST_ABI,
            "monitor_contract": audit_monitor.MONITOR_CONTRACT,
        }
        audit_monitor.validate_monitor_abi(copy.deepcopy(audit_monitor.MONITOR_ABI), manifest)
        for field, replacement in (
            ("request_magic", "BAD9"),
            ("maximum_request_payload_bytes", 33),
            ("response_bytes", 47),
            ("maximum_handled_requests", 257),
        ):
            mutated = copy.deepcopy(audit_monitor.MONITOR_ABI)
            mutated[field] = replacement
            with self.subTest(field=field), self.assertRaises(Core0Error):
                audit_monitor.validate_monitor_abi(mutated, manifest)
        mutated = copy.deepcopy(audit_monitor.MONITOR_ABI)
        mutated["monitor_contract"]["timer"]["minimum_period"] = 1
        with self.assertRaises(Core0Error):
            audit_monitor.validate_monitor_abi(mutated, manifest)


class MonitorShutdownWitnessTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> tuple[dict[str, object], dict[str, object], dict[str, object], str, str]:
        stopped_body = (
            "(action.bounded-fold-u64 budget=8 "
            "callback=Lemma.Examples.Foundation.Timer.controlStep count=(lit u32 8) "
            "(action.call Lemma.Examples.Foundation.Timer.writeWord [(lit u64 160) value])"
        )
        control_body = (
            "(action.bounded-fold-u64 budget=128 "
            "callback=Lemma.Examples.Foundation.Timer.mixStep "
            "count=(call Lemma.Examples.Foundation.Timer.workQuantum u32 [])"
        )
        manifest = {"action_functions": [
            {"source": "Lemma.Examples.Foundation.Monitor.stoppedWork",
             "llvm": "stopped", "body": stopped_body},
            {"source": "Lemma.Examples.Foundation.Timer.controlStep",
             "llvm": "control", "body": control_body},
            {"source": "Lemma.Examples.Foundation.Timer.mixStep",
             "llvm": "mix", "body": "(action.done)"},
            {"source": "Lemma.Examples.Foundation.Timer.writeWord",
             "llvm": "write", "body": "(action.done)"},
        ]}
        pre_stopped = "\n".join([
            "%c = call { i64, i64 } @control(i32 signext %i, i32 signext 8)",
            "%w = call { i64, i64 } @write(i64 160, i64 %value)",
            "%more = icmp ult i32 %i, 8",
            "%next = add i32 %i, 1",
            "br label %action.fold.header.5",
        ])
        pre_control = "\n".join([
            "%m = call { i64, i64 } @mix(i32 signext %i)",
            "%within = icmp ule i32 %count, 128",
            "%more = icmp ult i32 %i, %count",
            "br label %action.fold.header.2",
        ])
        post_stopped = "\n".join([
            *(f"%c{i} = call {{ i64, i64 }} @control(i32 signext {i}, i32 signext poison)"
              for i in range(8)),
            "%w = call { i64, i64 } @write(i64 160, i64 %value)",
        ])
        post_control = "\n".join([
            "%m = call { i64, i64 } @mix(i32 signext %i)",
            "%done = icmp eq i32 %next, 128",
            "br i1 %done, label %out, label %action.fold.body.3",
        ])
        ir_function = audit_monitor.audit_memory.IRFunction
        pre = {
            "stopped": ir_function("stopped", "", pre_stopped, {}),
            "control": ir_function("control", "", pre_control, {}),
        }
        post = {
            "stopped": ir_function("stopped", "", post_stopped, {}),
            "control": ir_function("control", "", post_control, {}),
        }
        return manifest, pre, post, pre_stopped + pre_control, post_stopped + post_control

    def test_profile_specific_work_and_witness_are_bound(self) -> None:
        manifest, pre, post, pre_ir, post_ir = self._fixture()
        report = audit_monitor._validate_shutdown_work_witness(
            manifest, pre, post, pre_ir, post_ir, "O2"
        )
        self.assertEqual(
            report["stopped_work_control_step_calls"],
            {"pre_optimization": 1, "post_optimization": 8},
        )
        self.assertEqual(report["control_step_iterations"], 128)
        self.assertTrue(report["volatile_store_proved_by_memory_audit"])

    def test_source_witness_offset_tamper_rejects(self) -> None:
        manifest, pre, post, pre_ir, post_ir = self._fixture()
        manifest["action_functions"][0]["body"] = str(
            manifest["action_functions"][0]["body"]
        ).replace("u64 160", "u64 168")
        with self.assertRaisesRegex(Core0Error, "source policy"):
            audit_monitor._validate_shutdown_work_witness(
                manifest, pre, post, pre_ir, post_ir, "O2"
            )

    def test_optimized_work_elimination_rejects(self) -> None:
        manifest, pre, post, pre_ir, post_ir = self._fixture()
        post_body = post["stopped"].body.replace(
            "%c7 = call { i64, i64 } @control(i32 signext 7, i32 signext poison)\n",
            "",
        )
        post["stopped"] = audit_monitor.audit_memory.IRFunction(
            "stopped", "", post_body, {}
        )
        with self.assertRaisesRegex(Core0Error, "eight-quanta"):
            audit_monitor._validate_shutdown_work_witness(
                manifest, pre, post, pre_ir, post_body + post["control"].body, "O2"
            )

    def test_optimized_128_step_backedge_tamper_rejects(self) -> None:
        manifest, pre, post, pre_ir, post_ir = self._fixture()
        post_control = post["control"].body.replace(", 128", ", 127")
        post["control"] = audit_monitor.audit_memory.IRFunction(
            "control", "", post_control, {}
        )
        with self.assertRaisesRegex(Core0Error, "128-iteration"):
            audit_monitor._validate_shutdown_work_witness(
                manifest, pre, post, pre_ir, post["stopped"].body + post_control, "O2"
            )

    def test_full_ir_path_requires_volatile_memory_validation(self) -> None:
        pre_ir = "; pre"
        post_ir = "; post"
        hashes = {
            "program.ll": hashlib.sha256(pre_ir.encode()).hexdigest(),
            "O0": hashlib.sha256(post_ir.encode()).hexdigest(),
        }
        with (
            mock.patch.object(audit_monitor, "MONITOR_IR_SHA256", hashes),
            mock.patch.object(
                audit_monitor.audit_memory,
                "validate_memory_pre_ir",
                side_effect=Core0Error("volatile sentinel"),
            ) as validator,
            self.assertRaisesRegex(Core0Error, "volatile sentinel"),
        ):
            audit_monitor.validate_monitor_ir({}, pre_ir, post_ir, "O0")
        self.assertTrue(validator.call_args.kwargs["require_volatile"])


class MonitorRoleClosureTests(unittest.TestCase):
    def _manifest(self) -> dict[str, object]:
        closure = sorted(audit_monitor.audit_timer.INTERRUPT_ACTION_CLOSURE)
        sources = [
            audit_monitor.FOREGROUND_SOURCE,
            audit_monitor.DISPATCH_SOURCE,
            *closure,
        ]
        sources = list(dict.fromkeys(sources))
        dependencies: dict[str, list[str]] = {source: [] for source in sources}
        dependencies[audit_monitor.DISPATCH_SOURCE] = [audit_monitor.INTERRUPT_SOURCE]
        dependencies[audit_monitor.INTERRUPT_SOURCE] = [
            source for source in closure if source != audit_monitor.INTERRUPT_SOURCE
        ]
        return {
            "scalar_functions": [],
            "action_functions": [
                _action(source, index, dependencies[source])
                for index, source in enumerate(sources)
            ],
        }

    def test_dispatch_is_the_only_interrupt_caller(self) -> None:
        result = audit_monitor._function_closure(self._manifest())
        self.assertEqual(result["interrupt_direct_caller"], audit_monitor.DISPATCH_SOURCE)
        self.assertTrue(result["foreground_excludes_interrupt_policy"])

    def test_manual_foreground_interrupt_dependency_rejects(self) -> None:
        manifest = self._manifest()
        foreground = manifest["action_functions"][0]
        foreground["action_dependencies"] = [audit_monitor.INTERRUPT_SOURCE]
        foreground["body"] = (
            f"(action.call {audit_monitor.INTERRUPT_SOURCE} [])"
        )
        with self.assertRaisesRegex(Core0Error, "sole caller|manually reach"):
            audit_monitor._function_closure(manifest)


class MonitorMachineWrapperTests(unittest.TestCase):
    @staticmethod
    def _clean_machine_report() -> dict[str, object]:
        return {
            "mutation": "none",
            "compiled_functions": 139,
            "compiled_privileged_instructions": 0,
            "startup_functions": 16,
            "machine_csr_operations": 28,
            "machine_slot_sequences": audit_monitor.MONITOR_MACHINE_SLOT_COUNTS,
            "timer_mmio_accesses": 3,
            "timer_mmio_width_bits": 64,
        }

    def test_machine_wrapper_forwards_independent_start_hashes(self) -> None:
        hashes = {"O0": "0" * 64, "O2": "1" * 64}
        with (
            mock.patch.object(audit_monitor, "MONITOR_START_MACHINE_BODY_SHA256", hashes),
            mock.patch.object(
                audit_monitor.audit_timer,
                "validate_timer_machine_disassembly",
                return_value=self._clean_machine_report(),
            ) as validator,
        ):
            report = audit_monitor.validate_monitor_machine_disassembly(
                "", {}, {"core0_main"}, "", {}, "O2"
            )
        self.assertEqual(report["mutation"], "none")
        self.assertEqual(
            validator.call_args.kwargs["expected_start_body_sha256"], hashes
        )

    def test_nonclean_machine_substrate_rejects(self) -> None:
        hashes = {"O0": "0" * 64, "O2": "1" * 64}
        with (
            mock.patch.object(audit_monitor, "MONITOR_START_MACHINE_BODY_SHA256", hashes),
            mock.patch.object(
                audit_monitor.audit_timer,
                "validate_timer_machine_disassembly",
                return_value={"mutation": "restore-s3-from-s4"},
            ),
            self.assertRaisesRegex(Core0Error, "not the clean"),
        ):
            audit_monitor.validate_monitor_machine_disassembly(
                "", {}, {"core0_main"}, "", {}, "O0"
            )


if __name__ == "__main__":
    unittest.main()
