"""Focused regression tests for the central Gate 6 audit policy."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0  # noqa: E402
import core0_common  # noqa: E402


def device_manifest() -> dict[str, object]:
    scalar_source = "Fixture.scalar"
    action_source = "Fixture.action"
    return {
        "schema_version": 1,
        "artifact_category": audit_core0.TEST_DEVICE_SUITE_POLICY,
        "contract_version": "core0-v0.5",
        "test_abi": "lemma-device-session-v1",
        "suite_id": "0000000000000001",
        "source_seed": "0000000000000002",
        "runtime_seed": "0000000000000003",
        "checked_result": copy.deepcopy(
            audit_core0.audit_memory.CHECKED_RESULT_CONTRACT
        ),
        "memory_contract": copy.deepcopy(audit_core0.audit_memory.MEMORY_CONTRACT),
        "device_contract": {
            "schema_version": 1,
            "contract_version": "core0-v0.5",
            "machine": "qemu-virt-rv64-single-hart",
            "interrupt_use": "none; Gate 6 is polling-only",
            "general_ram_api_access": False,
        },
        "roots": [
            {
                "root_id": 1,
                "source": action_source,
                "llvm": "core0_action_0",
                "signature": {"args": []},
            }
        ],
        "scalar_functions": [
            {
                "source": scalar_source,
                "llvm": "core0_scalar_0",
                "signature": {"args": [], "result": "u8"},
                "dependencies": [],
                "body": "(lit u8 0)",
                "noinline": True,
            }
        ],
        "action_functions": [
            {
                "source": action_source,
                "llvm": "core0_action_0",
                "signature": {"args": []},
                "scalar_dependencies": [scalar_source],
                "action_dependencies": [],
                "direct_effects": ["mmio-read", "io-order"],
                "transitive_effects": ["mmio-read", "io-order"],
                "body": "(action.done (lit u8 0) (lit u64 0))",
                "noinline": True,
            }
        ],
        "used_primitives": [
            copy.deepcopy(audit_core0.PRIMITIVE_CONTRACTS_V02["u8.eq"])
        ],
        "used_memory_ops": [
            copy.deepcopy(audit_core0.audit_memory.MEMORY_OPS["ram.read8"])
        ],
        "used_device_ops": [{"stable_id": "uart.read-status"}],
        "action_iterations": [
            {
                "stable_id": "action.u64.bounded-fold",
                "static_budget": 1,
                "callback": action_source,
            }
        ],
        "machine_primitives": copy.deepcopy(
            audit_core0.EXPECTED_DEVICE_MACHINE_PRIMITIVES
        ),
    }


def device_disassembly() -> str:
    """Complete six-site fixture with real RV64 call/address spellings."""
    fence = 0x80000100
    lines = [
        "80000100 <core0_io_fence>:",
        "80000100: fence",
        "80000104: ret",
    ]
    functions = (
        ("core0_action_0", (("lbu", 5), ("sb", 0))),
        ("core0_action_4", (("lbu", 5), ("lbu", 0))),
        ("core0_action_19", (("lbu", 5),)),
        ("core0_action_21", (("sb", 2),)),
    )
    address = 0x80000200
    for function, sites in functions:
        lines.append(f"{address:x} <{function}>:")
        for mnemonic, offset in sites:
            instructions = [
                "auipc ra, 0",
                f"jalr {fence - address}(ra)",
                "lui t0, 65536",
            ]
            if offset == 2:
                instructions.append("li t1, 7")
            instructions.append(f"{mnemonic} t1, {offset}(t0)")
            after_address = address + 4 * len(instructions)
            instructions.extend(("auipc ra, 0", f"jalr {fence - after_address}(ra)"))
            for instruction in instructions:
                lines.append(f"{address:x}: {instruction}")
                address += 4
        lines.append(f"{address:x}: ret")
        address += 4
    return "\n".join(lines) + "\n"


def denied_uart_metadata() -> str:
    lines: list[str] = []
    address = 0x80000400
    for action, count in ((6, 1), (9, 1), (11, 2), (12, 2), (13, 5), (16, 1), (18, 6)):
        lines.append(f"{address:x} <core0_action_{action}>:")
        for _ in range(count):
            for instruction in (
                "li a0, 0", "li a1, 2", "li a2, 256", "lui a3, 65536",
                "sd a3, 136(sp)", "sd a2, 144(sp)", "sd a1, 152(sp)",
                "mv a1, a0", "sd a1, 160(sp)", "sd a0, 168(sp)",
                "j 0x80000800",
            ):
                lines.append(f"{address:x}: {instruction}")
                address += 4
    return "\n".join(lines) + "\n"


class DeviceAuditPolicyTests(unittest.TestCase):
    def test_policy_is_explicit_and_requests_stack_metadata(self) -> None:
        self.assertIn(
            audit_core0.TEST_DEVICE_SUITE_POLICY, audit_core0.AUDIT_POLICIES
        )
        self.assertEqual(
            set(audit_core0.DEVICE_MACHINE_IR_FUNCTIONS), {"core0_main"}
        )
        command = audit_core0.expected_program_command(
            "O2", audit_core0.TEST_DEVICE_SUITE_POLICY
        )
        self.assertIn("-stack-size-section", command)

    def test_manifest_accepts_combined_scalar_action_closure(self) -> None:
        manifest = device_manifest()
        self.assertIs(
            audit_core0.validate_device_suite_manifest(manifest), manifest
        )

    def test_manifest_rejects_machine_primitive_substitution(self) -> None:
        manifest = device_manifest()
        manifest["machine_primitives"][-1]["implementation"] = "Fixture.escape"
        with self.assertRaisesRegex(
            core0_common.Core0Error, "exact allowlist"
        ):
            audit_core0.validate_device_suite_manifest(manifest)

    def test_manifest_rejects_open_action_dependency(self) -> None:
        manifest = device_manifest()
        manifest["action_functions"][0]["action_dependencies"] = ["Fixture.missing"]
        with self.assertRaisesRegex(
            core0_common.Core0Error, "dependency"
        ):
            audit_core0.validate_device_suite_manifest(manifest)

    def test_export_configuration_is_bound_to_manifest_identities(self) -> None:
        manifest = device_manifest()
        configuration = {
            "driver": audit_core0.DEVICE_EXPORT_DRIVER,
            "generation_command": [
                "lake",
                "env",
                "lean",
                str((ROOT / audit_core0.DEVICE_EXPORT_DRIVER).resolve()),
            ],
            "environment": {
                "LEMMA_DEVICE_RUNTIME_SEED": "3",
                "LEMMA_DEVICE_SOURCE_SEED": "2",
                "LEMMA_DEVICE_SUITE_ID": "1",
            },
        }
        self.assertIs(
            audit_core0.validate_device_export_configuration(
                configuration, manifest, ROOT
            ),
            configuration,
        )
        configuration["environment"]["LEMMA_DEVICE_RUNTIME_SEED"] = "4"
        with self.assertRaisesRegex(
            core0_common.Core0Error, "differ from the checked suite manifest"
        ):
            audit_core0.validate_device_export_configuration(
                configuration, manifest, ROOT
            )

    def test_machine_audit_accepts_complete_six_site_closure(self) -> None:
        report = audit_core0.validate_device_machine_disassembly(
            device_disassembly(), {"core0_io_fence": 0x80000100}
        )
        self.assertEqual(report["access_count"], 6)
        self.assertTrue(report["byte_accesses_only"])

    def test_machine_audit_rejects_unaccounted_uart_base(self) -> None:
        control = device_disassembly()
        anchor = "80000200 <core0_action_0>:\n"
        additions = {
            "wide-load": "80000000: lui t0, 65536\n80000004: lw t1, 0(t0)\n",
            "wide-store": "80000000: lui t0, 65536\n80000004: sw t1, 0(t0)\n",
            "separated-byte-access": (
                "80000000: lui t0, 65536\n"
                "80000004: addi t0, t0, 0\n"
                "80000008: lbu t1, 5(t0)\n"
            ),
            "unused-base": "80000000: lui t0, 65536\n80000004: nop\n",
        }
        for name, addition in additions.items():
            with self.subTest(name=name):
                mutated = control.replace(anchor, anchor + addition, 1)
                with self.assertRaisesRegex(
                    core0_common.Core0Error, "exact lbu/sb access"
                ):
                    audit_core0.validate_device_machine_disassembly(
                        mutated, {"core0_io_fence": 0x80000100}
                    )

    def test_machine_audit_accounts_exact_denied_region_metadata(self) -> None:
        report = audit_core0.validate_device_machine_disassembly(
            device_disassembly() + denied_uart_metadata(),
            {"core0_io_fence": 0x80000100},
        )
        self.assertEqual(report["access_count"], 6)
        self.assertEqual(report["denied_region_metadata_materializations"], 18)

    def test_machine_audit_rejects_reused_and_aliased_uart_pointer(self) -> None:
        control = device_disassembly()
        anchor = "80000230: ret\n"
        additions = {
            "direct-duplicate": ("sb t1, 0(t0)",),
            "wide-reuse": ("sw t1, 0(t0)",),
            "mv-alias": ("mv t2, t0", "sb t1, 0(t2)"),
            "addi-alias": ("addi t2, t0, 5", "lbu t1, 0(t2)"),
            "derived-outside-window": ("addi t2, t0, 256", "lbu t1, 0(t2)"),
            "literal-pointer": ("li t2, 268435456", "ld t1, 0(t2)"),
        }
        for name, instructions in additions.items():
            with self.subTest(name=name):
                addition = "".join(
                    f"{0x80000230 + 4 * index:x}: {instruction}\n"
                    for index, instruction in enumerate(instructions)
                )
                mutated = control.replace(anchor, addition + anchor, 1)
                with self.assertRaisesRegex(
                    core0_common.Core0Error, "additional, wide, or aliased UART access"
                ):
                    audit_core0.validate_device_machine_disassembly(
                        mutated, {"core0_io_fence": 0x80000100}
                    )

    def test_machine_audit_rejects_unknown_uart_pointer_transformation(self) -> None:
        mutated = device_disassembly().replace(
            "80000230: ret\n", "80000230: xor t2, t0, t1\n80000234: ret\n", 1
        )
        with self.assertRaisesRegex(
            core0_common.Core0Error, "unsupported transformation"
        ):
            audit_core0.validate_device_machine_disassembly(
                mutated, {"core0_io_fence": 0x80000100}
            )

    def test_machine_audit_rejects_changed_or_partial_denied_metadata(self) -> None:
        control = device_disassembly() + denied_uart_metadata()
        for name, mutated in (
            ("ordinary-class", control.replace("li a1, 2", "li a1, 0", 1)),
            ("allowed-permission", control.replace("li a0, 0", "li a0, 1", 1)),
            ("wrong-stack-slot", control.replace("sd a2, 144(sp)", "sd a2, 152(sp)", 1)),
            ("wrong-function", control.replace("<core0_action_6>:", "<core0_action_7>:", 1)),
        ):
            with self.subTest(name=name):
                with self.assertRaises(core0_common.Core0Error):
                    audit_core0.validate_device_machine_disassembly(
                        mutated, {"core0_io_fence": 0x80000100}
                    )


if __name__ == "__main__":
    unittest.main()
