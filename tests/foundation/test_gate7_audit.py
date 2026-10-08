#!/usr/bin/env python3
"""Focused fail-closed mutation tests for the Gate 7 trap audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_trap  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class TrapVectorAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = audit_trap._expected_trap_vector("none")

    def test_clean_and_declared_restore_mutant_are_exactly_separated(self) -> None:
        mutant = audit_trap._expected_trap_vector("restore-s3-from-s4")
        self.assertEqual(len(self.clean), len(mutant))
        self.assertEqual(
            [(left, right) for left, right in zip(self.clean, mutant) if left != right],
            [("ld s3, 144(sp)", "ld s3, 152(sp)")],
        )
        audit_trap.validate_trap_vector_instructions(self.clean, "none")
        audit_trap.validate_trap_vector_instructions(
            mutant, "restore-s3-from-s4"
        )
        with self.assertRaisesRegex(Core0Error, "full-context"):
            audit_trap.validate_trap_vector_instructions(mutant, "none")
        with self.assertRaisesRegex(Core0Error, "full-context"):
            audit_trap.validate_trap_vector_instructions(
                self.clean, "restore-s3-from-s4"
            )

    def test_omitted_or_duplicated_register_save_rejects(self) -> None:
        save = "sd s7, 176(sp)"
        self.assertIn(save, self.clean)
        for mutated in (
            [instruction for instruction in self.clean if instruction != save],
            [*self.clean[: self.clean.index(save)], save, *self.clean[self.clean.index(save):]],
        ):
            with self.subTest(length=len(mutated)):
                with self.assertRaisesRegex(Core0Error, "full-context"):
                    audit_trap.validate_trap_vector_instructions(mutated, "none")

    def test_wrong_restore_offset_rejects_outside_declared_mutant(self) -> None:
        mutated = list(self.clean)
        mutated[mutated.index("ld s3, 144(sp)")] = "ld s3, 136(sp)"
        for profile in ("none", "restore-s3-from-s4"):
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(Core0Error, "full-context"):
                    audit_trap.validate_trap_vector_instructions(mutated, profile)

    def test_unknown_csr_rejects(self) -> None:
        mutated = list(self.clean)
        mutated[mutated.index("csrr t0, mstatus")] = "csrr t0, 0x7ff"
        with self.assertRaisesRegex(Core0Error, "full-context"):
            audit_trap.validate_trap_vector_instructions(mutated, "none")

    def test_ninth_argument_slot_and_alignment_are_closed(self) -> None:
        for before, after in (
            ("sd t0, 0(sp)", "sd t0, 8(sp)"),
            ("addi sp, sp, -16", "addi sp, sp, -8"),
            ("addi sp, sp, 16", "addi sp, sp, 8"),
        ):
            mutated = list(self.clean)
            mutated[mutated.index(before)] = after
            with self.subTest(instruction=before):
                with self.assertRaisesRegex(Core0Error, "full-context"):
                    audit_trap.validate_trap_vector_instructions(mutated, "none")


class TrapMachineContractTests(unittest.TestCase):
    def test_authorized_continuations_are_exactly_plus_four(self) -> None:
        symbols = {
            "core0_trap_vector": 0x800001A0,
            "__trap_ecall_site": 0x80000630,
            "__trap_ecall_resume": 0x80000634,
            "__trap_breakpoint_site": 0x80001034,
            "__trap_breakpoint_resume": 0x80001038,
            "__trap_unexpected_ecall_site": 0x8000178C,
            "__trap_illegal_instruction_site": 0x80001794,
        }
        audit_trap.validate_trap_site_symbols(symbols)
        for field, value in (
            ("__trap_ecall_resume", 0x80000638),
            ("__trap_breakpoint_resume", 0x8000103A),
            ("core0_trap_vector", 0x800001A2),
        ):
            mutated = dict(symbols)
            mutated[field] = value
            with self.subTest(field=field):
                with self.assertRaises(Core0Error):
                    audit_trap.validate_trap_site_symbols(mutated)

    def test_fatal_finishers_reject_stack_call_or_missing_self_loop(self) -> None:
        valid = [
            "li t0, 1048576",
            "li t1, 1192755",
            "fence iorw, iorw",
            "sw t1, 0(t0)",
            "fence iorw, iorw",
            "j .Ltrap_fatal_halt",
        ]
        audit_trap.validate_stackless_fatal_body(
            "core0_trap_fatal_dispatch", 18, valid
        )
        mutations = (
            ["addi sp, sp, -16", *valid],
            [*valid[:-1], "call core0_main"],
            [*valid[:-1], "ret"],
        )
        for body in mutations:
            with self.subTest(body=body[-1]):
                with self.assertRaisesRegex(Core0Error, "stackless fatal"):
                    audit_trap.validate_stackless_fatal_body(
                        "core0_trap_fatal_dispatch", 18, body
                    )

    def test_compiled_program_rejects_gp_tp_and_privileged_instructions(self) -> None:
        audit_trap.validate_compiled_register_reservation(
            {"core0_action_0": "80002000: add a0, a1, a2\n"}
        )
        mutations = (
            ("80002000: mv gp, a0\n", "reserved gp/tp"),
            ("80002000: mv a0, tp\n", "reserved gp/tp"),
            ("80002000: csrr a0, 0x300\n", "privileged/CSR"),
            ("80002000: ecall\n", "privileged/CSR"),
            ("80002000: mret\n", "privileged/CSR"),
        )
        for body, diagnostic in mutations:
            with self.subTest(body=body.strip()):
                with self.assertRaisesRegex(Core0Error, diagnostic):
                    audit_trap.validate_compiled_register_reservation(
                        {"core0_action_0": body}
                    )


if __name__ == "__main__":
    unittest.main()
