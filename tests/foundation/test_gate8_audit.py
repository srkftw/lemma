#!/usr/bin/env python3
"""Focused fail-closed mutation tests for the Gate 8 timer audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_timer  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class TimerMachineInstructionTests(unittest.TestCase):
    def test_privileged_namespace_is_deny_by_default(self) -> None:
        forbidden = (
            "csrr", "csrrs", "csrrc", "csrrw", "csrrwi", "csrrsi", "csrrci",
            "csrwi", "csrsi", "csrci", "sfence.vma", "hfence.gvma", "sinval.vma",
            "hinval.gvma", "ecall", "ebreak", "mret", "sret", "uret", "mnret",
            "dret", "wfi", "unimp",
        )
        for mnemonic in forbidden:
            with self.subTest(mnemonic=mnemonic):
                self.assertTrue(audit_timer._is_privileged_mnemonic(mnemonic))
        for mnemonic in ("add", "ld", "sd", "fence", "ret"):
            with self.subTest(mnemonic=mnemonic):
                self.assertFalse(audit_timer._is_privileged_mnemonic(mnemonic))

    def test_unknown_instruction_is_closed_to_declared_fixture_site(self) -> None:
        valid = "80000000:\taddi\ta0, a0, 0x1\n80000004:\t<unknown>\n"
        symbols = {"__trap_illegal_instruction_site": 0x80000004}
        audit_timer._validate_disassembly_inventory(valid, symbols)
        for mutated in (
            valid.replace("80000004", "80000008"),
            valid + "80000008:\t<unknown>\n",
            valid + "8000000c:\t@unparsed\ta0\n",
        ):
            with self.subTest(mutated=mutated.splitlines()[-1]):
                with self.assertRaises(Core0Error):
                    audit_timer._validate_disassembly_inventory(mutated, symbols)

    def test_action_20_and_dispatch_bodies_remain_distinct(self) -> None:
        disassembly = (
            "80001000 <core0_action_20>:\n"
            "80001000:\tadd\ta0, a0, a1\n\n"
            "80001004 <core0_action_39>:\n"
            "80001004:\txor\ta0, a0, a1\n\n"
            "80001008 <after>:\n"
            "80001008:\tret\n"
        )
        bodies = audit_timer._validate_compiled_program_bodies(
            disassembly,
            {"core0_action_20", "core0_action_39"},
            {"core0_action_20": 0x80001000, "core0_action_39": 0x80001004},
        )
        self.assertIn("add", bodies["core0_action_20"])
        self.assertIn("xor", bodies["core0_action_39"])

    def test_duplicate_compiled_header_rejects(self) -> None:
        disassembly = (
            "80001000 <core0_action_20>:\n80001000:\tadd\ta0, a0, a1\n\n"
            "80001004 <core0_action_20>:\n80001004:\tret\n"
        )
        with self.assertRaisesRegex(Core0Error, "exactly one body"):
            audit_timer._compiled_program_bodies(
                disassembly, {"core0_action_20"}, {"core0_action_20": 0x80001000}
            )

    def test_local_symbol_header_does_not_truncate_compiled_body(self) -> None:
        disassembly = (
            "80001000 <core0_action_20>:\n"
            "80001000:\tadd\ta0, a0, a1\n\n"
            "80001004 <.Lpcrel_hi0>:\n"
            "80001004:\tcsrrs\tt2, mstatus, t3\n\n"
            "80001008 <core0_action_39>:\n"
            "80001008:\tret\n"
        )
        with self.assertRaisesRegex(Core0Error, "privileged"):
            audit_timer._validate_compiled_program_bodies(
                disassembly,
                {"core0_action_20", "core0_action_39"},
                {"core0_action_20": 0x80001000, "core0_action_39": 0x80001008},
            )

    def test_each_original_compiled_body_rejects_reserved_or_system_ops(self) -> None:
        mutations = {
            "core0_action_20": ("mv", "gp, a0"),
            "core0_action_39": ("csrrs", "t2, mstatus, t3"),
            "core0_action_40": ("mnret", ""),
        }
        for target, (mnemonic, operands) in mutations.items():
            rows = []
            for index, name in enumerate(mutations):
                op, args = (mnemonic, operands) if name == target else ("add", "a0, a0, a1")
                rows.append(
                    f"8000{index:04x} <{name}>:\n"
                    f"8000{index:04x}:\t{op}\t{args}\n"
                )
            with self.subTest(target=target, mnemonic=mnemonic):
                with self.assertRaises(Core0Error):
                    audit_timer._validate_compiled_program_bodies(
                        "\n".join(rows),
                        set(mutations),
                        {name: 0x80000000 + index for index, name in enumerate(mutations)},
                    )


class TimerMachineBodyHashTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = {
            name: [(0x80000000 + index * 4, "addi", f"a0, a0, {index}")]
            for index, name in enumerate(sorted(audit_timer.TIMER_EXTERNALS))
        }
        self.expected = {
            name: audit_timer._machine_body_sha256(rows)
            for name, rows in self.clean.items()
        }
        self.mutant = dict(self.clean)
        self.mutant["core0_timer_set_compare"] = [
            (0x80000000, "sd", "t1, 0x0(t0)")
        ]
        self.mutant_digest = audit_timer._machine_body_sha256(
            self.mutant["core0_timer_set_compare"]
        )

    def _patch_contract(self):
        return (
            mock.patch.object(audit_timer, "TIMER_MACHINE_BODY_SHA256", self.expected),
            mock.patch.object(
                audit_timer,
                "DISABLE_ARMING_MACHINE_BODY_SHA256",
                self.mutant_digest,
            ),
        )

    def test_clean_and_declared_mutants_are_exactly_separated(self) -> None:
        first, second = self._patch_contract()
        with first, second:
            audit_timer._validate_timer_machine_body_hashes(self.clean, "none")
            audit_timer._validate_timer_machine_body_hashes(
                self.clean, "restore-s3-from-s4"
            )
            audit_timer._validate_timer_machine_body_hashes(
                self.mutant, "disable-timer-arming"
            )
            with self.assertRaises(Core0Error):
                audit_timer._validate_timer_machine_body_hashes(
                    self.mutant, "none"
                )
            with self.assertRaises(Core0Error):
                audit_timer._validate_timer_machine_body_hashes(
                    self.clean, "disable-timer-arming"
                )

    def test_non_memory_leaf_mutation_rejects(self) -> None:
        mutated = dict(self.clean)
        mutated["core0_irq_restore"] = [(0x80000000, "addi", "a0, a0, 99")]
        first, second = self._patch_contract()
        with first, second, self.assertRaisesRegex(Core0Error, "exact closed inventory"):
            audit_timer._validate_timer_machine_body_hashes(mutated, "none")

    def test_omitted_timer_leaf_rejects(self) -> None:
        omitted = dict(self.clean)
        omitted.pop("core0_timer_probe")
        first, second = self._patch_contract()
        with first, second, self.assertRaises(Core0Error):
            audit_timer._validate_timer_machine_body_hashes(omitted, "none")

    def test_unknown_mutation_identity_rejects(self) -> None:
        first, second = self._patch_contract()
        with first, second, self.assertRaisesRegex(Core0Error, "unknown timer machine mutation"):
            audit_timer._validate_timer_machine_body_hashes(self.clean, "surprise")


class TimerMachineMmioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean = {
            "_start": [
                (0x80000000, "lui", "t0, 0x2004"),
                (0x80000004, "sd", "t1, 0x0(t0)"),
            ],
            "core0_timer_read_time": [
                (0x80000008, "lui", "t0, 0x200c"),
                (0x8000000C, "addiw", "t0, t0, -0x8"),
                (0x80000010, "ld", "a0, 0x0(t0)"),
            ],
            "core0_timer_set_compare": [
                (0x80000014, "lui", "t0, 0x2004"),
                (0x80000018, "sd", "a0, 0x0(t0)"),
            ],
        }

    def test_exact_three_64_bit_timer_accesses_accept(self) -> None:
        report = audit_timer._validate_timer_mmio_machine_closure(self.clean)
        self.assertEqual(report["access_count"], 3)
        self.assertEqual(report["compiled_program_accesses"], 0)

    def test_compiled_action_direct_or_aliased_timer_access_rejects(self) -> None:
        for function, extra in (
            ("core0_action_20", [
                (0x80000100, "lui", "t0, 0x2004"),
                (0x80000104, "sd", "a0, 0x0(t0)"),
            ]),
            ("core0_action_39", [
                (0x80000100, "lui", "t0, 0x200c"),
                (0x80000104, "mv", "t1, t0"),
                (0x80000108, "addiw", "t1, t1, -0x8"),
                (0x8000010C, "ld", "a0, 0x0(t1)"),
            ]),
        ):
            mutated = dict(self.clean)
            mutated[function] = extra
            with self.subTest(function=function), self.assertRaisesRegex(
                Core0Error, "exact three"
            ):
                audit_timer._validate_timer_mmio_machine_closure(mutated)

    def test_wrong_width_or_timer_address_rejects(self) -> None:
        for replacement in (
            (0x80000018, "sw", "a0, 0x0(t0)"),
            (0x80000018, "sd", "a0, 0x8(t0)"),
        ):
            mutated = {name: list(rows) for name, rows in self.clean.items()}
            mutated["core0_timer_set_compare"][-1] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(Core0Error):
                audit_timer._validate_timer_mmio_machine_closure(mutated)

    def test_unknown_transform_of_timer_pointer_rejects(self) -> None:
        mutated = dict(self.clean)
        mutated["core0_action_20"] = [
            (0x80000100, "lui", "t0, 0x2004"),
            (0x80000104, "mul", "t1, t0, a0"),
        ]
        with self.assertRaisesRegex(Core0Error, "unsupported machine transform"):
            audit_timer._validate_timer_mmio_machine_closure(mutated)

    def test_branch_merge_cannot_hide_a_timer_pointer(self) -> None:
        mutated = dict(self.clean)
        mutated["core0_action_20"] = [
            (0x80000100, "lui", "t0, 0x2004"),
            (0x80000104, "beqz", "a0, 0x8000010c"),
            (0x80000108, "li", "t0, 0x0"),
            (0x8000010C, "sd", "a1, 0x0(t0)"),
        ]
        with self.assertRaisesRegex(Core0Error, "control-flow boundary"):
            audit_timer._validate_timer_mmio_machine_closure(mutated)

    def test_callee_saved_timer_pointer_cannot_cross_call(self) -> None:
        mutated = dict(self.clean)
        mutated["core0_action_20"] = [
            (0x80000100, "lui", "s0, 0x2004"),
            (0x80000104, "call", "0x80000200 <core0_action_39>"),
        ]
        mutated["core0_action_39"] = [
            (0x80000200, "sd", "a0, 0x0(s0)"),
            (0x80000204, "ret", ""),
        ]
        with self.assertRaisesRegex(Core0Error, "live across a machine call"):
            audit_timer._validate_timer_mmio_machine_closure(mutated)


class TimerRoleClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = {
            audit_timer.FOREGROUND_SOURCE: {"foreground-helper"},
            "foreground-helper": set(),
            audit_timer.DISPATCH_SOURCE: {audit_timer.INTERRUPT_SOURCE},
            audit_timer.INTERRUPT_SOURCE: {
                "Lemma.Examples.Foundation.Timer.readWord",
                "Lemma.Examples.Foundation.Timer.writeWord",
                "Lemma.Examples.Foundation.Timer.enqueue",
                "Lemma.Examples.Foundation.Timer.rearm",
            },
            "Lemma.Examples.Foundation.Timer.readWord": set(),
            "Lemma.Examples.Foundation.Timer.writeWord": set(),
            "Lemma.Examples.Foundation.Timer.enqueue": {
                "Lemma.Examples.Foundation.Timer.readWord",
                "Lemma.Examples.Foundation.Timer.writeWord",
                "Lemma.Examples.Foundation.Timer.increment",
            },
            "Lemma.Examples.Foundation.Timer.increment": {
                "Lemma.Examples.Foundation.Timer.readWord",
                "Lemma.Examples.Foundation.Timer.writeWord",
            },
            "Lemma.Examples.Foundation.Timer.rearm": {
                "Lemma.Examples.Foundation.Timer.readWord",
                "Lemma.Examples.Foundation.Timer.writeWord",
                "Lemma.Examples.Foundation.Timer.increment",
            },
        }

    def test_short_isr_and_foreground_separation_accept(self) -> None:
        report = audit_timer._validate_timer_role_closure(self.graph)
        self.assertTrue(report["foreground_excludes_interrupt_policy"])
        self.assertEqual(
            set(report["interrupt_action_closure"]),
            audit_timer.INTERRUPT_ACTION_CLOSURE,
        )

    def test_manual_foreground_interrupt_call_rejects(self) -> None:
        graph = {name: set(dependencies) for name, dependencies in self.graph.items()}
        graph[audit_timer.FOREGROUND_SOURCE].add(audit_timer.INTERRUPT_SOURCE)
        with self.assertRaisesRegex(Core0Error, "sole direct caller"):
            audit_timer._validate_timer_role_closure(graph)

    def test_isr_uart_or_unbounded_dependency_rejects(self) -> None:
        graph = {name: set(dependencies) for name, dependencies in self.graph.items()}
        graph["uart-helper"] = set()
        graph[audit_timer.INTERRUPT_SOURCE].add("uart-helper")
        with self.assertRaisesRegex(Core0Error, "short deferred-work ISR"):
            audit_timer._validate_timer_role_closure(graph)


if __name__ == "__main__":
    unittest.main()
