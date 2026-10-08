#!/usr/bin/env python3
"""Focused fail-closed tests for the Gate 4 loop/stack audit."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0  # noqa: E402
import check_foundation_gate4  # noqa: E402
from core0_common import Core0Error  # noqa: E402


def closed_manifest_fixture() -> dict[str, object]:
    functions: list[dict[str, object]] = []
    symbols: dict[str, str] = {}
    for index, (source, contract) in enumerate(
        audit_core0.LOOP_FUNCTION_CONTRACTS.items()
    ):
        args, result, dependencies = contract
        symbol = f"core0_user_{index}"
        symbols[source] = symbol
        functions.append(
            {
                "source": source,
                "llvm": symbol,
                "signature": {"args": list(args), "result": result},
                "dependencies": list(dependencies),
                "body": audit_core0.LOOP_FUNCTION_BODIES[source],
                "return_extension": audit_core0._scalar_abi_extension(result),
                "parameter_extensions": [
                    audit_core0._scalar_abi_extension(arg) for arg in args
                ],
                "noinline": True,
            }
        )
    roots = []
    for root_id, source in enumerate(audit_core0.LOOP_ROOT_SOURCES, 1):
        args, result, _dependencies = audit_core0.LOOP_FUNCTION_CONTRACTS[source]
        roots.append(
            {
                "root_id": root_id,
                "source": source,
                "llvm": symbols[source],
                "signature": {"args": list(args), "result": result},
                "return_extension": audit_core0._scalar_abi_extension(result),
                "parameter_extensions": [
                    audit_core0._scalar_abi_extension(arg) for arg in args
                ],
            }
        )
    return {
        "schema_version": 1,
        "artifact_category": audit_core0.TEST_LOOP_SUITE_POLICY,
        "contract_version": "core0-v0.3",
        "test_abi": audit_core0.SCALAR_TEST_ABI,
        "suite_id": "b1e51d2902bca153",
        "source_seed": "4c454d4d41343034",
        "runtime_seed": "52554e54494d4534",
        "loop_contract": copy.deepcopy(audit_core0.LOOP_CONTRACT),
        "roots": roots,
        "functions": functions,
        "used_primitives": [
            copy.deepcopy(audit_core0.PRIMITIVE_CONTRACTS_V02[stable_id])
            for stable_id in sorted(audit_core0.LOOP_USED_PRIMITIVES)
        ],
        "iterations": [
            audit_core0._expected_loop_iteration(budget, callback)
            for budget, callback in audit_core0.LOOP_ITERATION_ORDER
        ],
        "machine_primitives": copy.deepcopy(
            audit_core0.EXPECTED_SCALAR_MACHINE_PRIMITIVES
        ),
    }


def loop_ir_fixture(manifest: dict[str, object]) -> str:
    functions = manifest["functions"]
    if not isinstance(functions, list):
        raise AssertionError("fixture functions are malformed")
    source_symbols = {
        function["source"]: function["llvm"]
        for function in functions
        if isinstance(function, dict)
    }
    definitions: list[str] = []
    for function in functions:
        if not isinstance(function, dict):
            raise AssertionError("fixture function is malformed")
        source, symbol = str(function["source"]), str(function["llvm"])
        normalized = str(function["body"])
        site = audit_core0.re.search(
            r"\(bounded-fold-u32 budget=([0-9]+) callback=([A-Za-z0-9_.]+) ",
            normalized,
        )
        result = function["signature"]["result"]
        if site is None:
            definitions.append(
                f"define i32 @{symbol}(i32 %arg0, i32 %arg1) {{\n"
                "entry:\n  ret i32 %arg1\n}\n"
            )
            continue
        budget, callback = site.groups()
        callback_symbol = source_symbols[callback]
        tail = (
            "  %cast10 = trunc i64 %loop.result9 to i32\n  ret i32 %cast10"
            if result == "u32" else "  ret i64 %loop.result9"
        )
        definitions.append(
            f"define i{32 if result == 'u32' else 64} @{symbol}(i32 %arg0, i32 %arg1) {{\n"
            "entry:\n"
            f"  %loop.within-budget0 = icmp ule i32 %arg0, {budget}\n"
            "  br i1 %loop.within-budget0, label %loop.preheader.0, label %loop.exhausted.1\n"
            "loop.preheader.0:\n  br label %loop.header.2\n"
            "loop.exhausted.1:\n"
            "  %loop.exhausted-initial1 = zext i32 %arg1 to i64\n"
            "  %loop.exhausted-tag2 = or i64 %loop.exhausted-initial1, 9223372036854775808\n"
            "  br label %loop.outcome.5\n"
            "loop.header.2:\n"
            "  %loop.index3 = phi i32 [ 0, %loop.preheader.0 ], [ %loop.next-index7, %loop.body.3 ]\n"
            "  %loop.accumulator4 = phi i32 [ %arg1, %loop.preheader.0 ], [ %loop.next-accumulator6, %loop.body.3 ]\n"
            "  %loop.continue5 = icmp ult i32 %loop.index3, %arg0\n"
            "  br i1 %loop.continue5, label %loop.body.3, label %loop.done.4\n"
            "loop.body.3:\n"
            f"  %loop.next-accumulator6 = call signext i32 @{callback_symbol}(i32 signext %loop.index3, i32 signext %loop.accumulator4)\n"
            "  %loop.next-index7 = add i32 %loop.index3, 1\n"
            "  br label %loop.header.2\n"
            "loop.done.4:\n"
            "  %loop.value8 = zext i32 %loop.accumulator4 to i64\n"
            "  br label %loop.outcome.5\n"
            "loop.outcome.5:\n"
            "  %loop.result9 = phi i64 [ %loop.value8, %loop.done.4 ], [ %loop.exhausted-tag2, %loop.exhausted.1 ]\n"
            f"{tail}\n}}\n"
        )
    return "\n".join(definitions)


class Gate4ManifestAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()

    def test_exact_v03_manifest_is_accepted(self) -> None:
        self.assertEqual(
            audit_core0.validate_loop_suite_manifest(self.manifest), self.manifest
        )

    def test_budget_callback_closure_and_profile_tampering_are_rejected(self) -> None:
        mutations = []
        budget = copy.deepcopy(self.manifest)
        budget["iterations"][0]["static_budget"] = 15
        mutations.append((budget, "iteration sites differ"))
        callback = copy.deepcopy(self.manifest)
        callback["iterations"][0]["callback"] = "forged.callback"
        mutations.append((callback, "iteration sites differ"))
        closure = copy.deepcopy(self.manifest)
        closure["functions"].pop()
        mutations.append((closure, "exact 14-function closure"))
        profile = copy.deepcopy(self.manifest)
        profile["contract_version"] = "core0-v0.2"
        mutations.append((profile, "unsupported Core0 contract"))
        for value, diagnostic in mutations:
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(Core0Error, diagnostic):
                    audit_core0.validate_loop_suite_manifest(value)


class Gate4LoopSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()
        self.ir = loop_ir_fixture(self.manifest)

    def test_exact_eight_loop_cfgs_are_accepted(self) -> None:
        result = audit_core0.validate_loop_pre_semantics(self.manifest, self.ir)
        self.assertEqual(result["loop_count"], 8)
        self.assertTrue(
            all(not row["exhaustion_callback_reachable"] for row in result["loops"])
        )

    def test_complete_driver_mutation_matrix_is_detected(self) -> None:
        records = check_foundation_gate4._run_loop_mutations(self.manifest, self.ir)
        self.assertEqual(len(records), 14)
        self.assertEqual(sum(row["kind"] == "profile-version" for row in records), 1)
        self.assertEqual(
            sum(row["kind"] in {"manifest-binding", "manifest-closure"} for row in records),
            4,
        )


class Gate4OptimizerAndStackTests(unittest.TestCase):
    def test_machine_loop_requires_exactly_one_direct_call_and_backedge(self) -> None:
        manifest = closed_manifest_fixture()
        functions = manifest["functions"]
        if not isinstance(functions, list):
            raise AssertionError("fixture functions are malformed")
        symbols = {
            str(function["source"]): str(function["llvm"])
            for function in functions
            if isinstance(function, dict)
        }
        sections: list[str] = []
        for function in functions:
            if not isinstance(function, dict):
                raise AssertionError("fixture function is malformed")
            site = audit_core0.re.search(
                r"\(bounded-fold-u32 budget=([0-9]+) callback=([A-Za-z0-9_.]+) ",
                str(function["body"]),
            )
            if site is None:
                continue
            budget, callback = int(site.group(1)), site.group(2)
            symbol = str(function["llvm"])
            lines = [f"0000000000000100 <{symbol}>:"]
            if budget > 0:
                lines.extend(
                    (
                        f" 100: jal ra, 80 <{symbols[callback]}>",
                        f" 104: bne a0, a1, 100 <{symbol}+0x0>",
                    )
                )
            else:
                lines.append(" 100: ret")
            sections.append("\n".join(lines))
        disassembly = "\n\n".join(sections) + "\n\n"
        result = audit_core0.validate_loop_machine_disassembly(
            manifest, disassembly, "O2"
        )
        self.assertEqual(result["positive_budget_loops_with_backedges"], 7)

        duplicate = disassembly.replace(
            " 104: bne a0, a1, 100 <core0_user_1+0x0>",
            " 104: bne a0, a1, 100 <core0_user_1+0x0>\n"
            " 108: bne a0, a1, 100 <core0_user_1+0x0>",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "exactly one backward branch"):
            audit_core0.validate_loop_machine_disassembly(
                manifest, duplicate, "O2"
            )

    def test_disjoint_inventory_proves_exact_exhaustion_and_hex_ranges(self) -> None:
        ir = """
define i64 @loop(i32 %arg1) {
entry:
  %wide = zext i32 %arg1 to i64
  %tag = or disjoint i64 %wide, -9223372036854775808
  ret i64 %tag
}
define i64 @hex(i64 %value) {
entry:
  %nibble = and i64 %value, 15
  %ascii = or disjoint i64 %nibble, 48
  ret i64 %ascii
}
""".lstrip()
        result = audit_core0.validate_optimizer_disjoint(
            ir, expected_exhaustion_tags=1
        )
        self.assertEqual(result["instruction_count"], 2)
        self.assertTrue(result["all_operands_proven_disjoint"])

        unsafe = ir.replace("%wide = zext i32 %arg1 to i64", "%wide = add i64 0, 1")
        with self.assertRaisesRegex(Core0Error, "not proven"):
            audit_core0.validate_optimizer_disjoint(
                unsafe, expected_exhaustion_tags=1
            )

    def test_call_graph_uses_summed_frames_and_rejects_cycles(self) -> None:
        ir = """
define void @a() {
entry:
  call void @b()
  ret void
}
define void @b() {
entry:
  ret void
}
""".lstrip()
        result = audit_core0.validate_loop_stack_call_graph(ir, {"a": 32, "b": 48})
        self.assertEqual(result["maximum_frame_chain_bytes"], 80)
        cyclic = ir.replace("entry:\n  ret void\n}\n", "entry:\n  call void @a()\n  ret void\n}\n", 1)
        with self.assertRaisesRegex(Core0Error, "contains cycle"):
            audit_core0.validate_loop_stack_call_graph(
                cyclic, {"a": 32, "b": 48}
            )


if __name__ == "__main__":
    unittest.main()
