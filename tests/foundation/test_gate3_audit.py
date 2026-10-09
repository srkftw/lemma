#!/usr/bin/env python3
"""Focused fail-closed tests for the Gate 3 structured-CFG audit."""

from __future__ import annotations

import copy
import sys
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0  # noqa: E402
from core0_common import Core0Error  # noqa: E402


def closed_manifest_fixture() -> dict[str, object]:
    """Construct the complete v0.2 manifest expected by the independent audit."""
    functions: list[dict[str, object]] = []
    source_symbols: dict[str, str] = {}
    for index, (source, args, result, dependencies) in enumerate(
        audit_core0.CFG_FUNCTION_CONTRACTS
    ):
        symbol = f"core0_user_{index}"
        source_symbols[source] = symbol
        functions.append(
            {
                "source": source,
                "llvm": symbol,
                "signature": {"args": list(args), "result": result},
                "dependencies": list(dependencies),
                "body": f"(lit {result} 0)",
                "return_extension": audit_core0._scalar_abi_extension(result),
                "parameter_extensions": [
                    audit_core0._scalar_abi_extension(arg) for arg in args
                ],
                "noinline": True,
            }
        )
    contracts = {
        source: (args, result)
        for source, args, result, _dependencies in audit_core0.CFG_FUNCTION_CONTRACTS
    }
    roots: list[dict[str, object]] = []
    for root_id, source in enumerate(audit_core0.CFG_ROOT_SOURCES, 1):
        args, result = contracts[source]
        roots.append(
            {
                "root_id": root_id,
                "source": source,
                "llvm": source_symbols[source],
                "signature": {"args": list(args), "result": result},
                "return_extension": audit_core0._scalar_abi_extension(result),
                "parameter_extensions": [
                    audit_core0._scalar_abi_extension(arg) for arg in args
                ],
            }
        )
    return {
        "schema_version": 1,
        "artifact_category": audit_core0.TEST_CFG_SUITE_POLICY,
        "contract_version": "core0-v0.2",
        "test_abi": audit_core0.SCALAR_TEST_ABI,
        "suite_id": "c3ba06c7f7e1475c",
        "source_seed": "4c454d4d41333033",
        "runtime_seed": "52554e54494d4533",
        "cfg_validation": {
            "validator": "Lemma.Compiler.LLVM.validateModule",
            "source_conditionals": "branch-phi",
            "division": "zero-guarded",
            "shift_counts": "masked-to-width",
        },
        "roots": roots,
        "functions": functions,
        "used_primitives": [
            copy.deepcopy(audit_core0.PRIMITIVE_CONTRACTS_V02[stable_id])
            for stable_id in sorted(audit_core0.CFG_USED_PRIMITIVES)
        ],
        "machine_primitives": copy.deepcopy(
            audit_core0.EXPECTED_SCALAR_MACHINE_PRIMITIVES
        ),
    }


def cfg_semantics_manifest_fixture() -> dict[str, object]:
    """Return the narrow manifest surface consumed by validate_cfg_pre_semantics."""
    return {
        "functions": [
            {
                "source": "fixture.udiv",
                "llvm": "fixture_udiv",
                "body": "(bin udiv u64 (var 0 u64) (var 1 u64))",
            },
            {
                "source": "fixture.urem",
                "llvm": "fixture_urem",
                "body": "(bin urem u64 (var 0 u64) (var 1 u64))",
            },
            {
                "source": "fixture.shl",
                "llvm": "fixture_shl",
                "body": "(bin shl u32 (var 0 u32) (var 1 u32))",
            },
            {
                "source": "fixture.lshr",
                "llvm": "fixture_lshr",
                "body": "(bin lshr u8 (var 0 u8) (var 1 u8))",
            },
            {
                "source": "fixture.conditional",
                "llvm": "fixture_conditional",
                "body": "(ite (var bool 0) (var u64 1) (var u64 2))",
            },
        ]
    }


def cfg_ir_fixture() -> str:
    return textwrap.dedent(
        """
        define i64 @fixture_udiv(i64 %arg0, i64 %arg1) {
        entry:
          %iszero = icmp eq i64 %arg1, 0
          br i1 %iszero, label %zero, label %nonzero
        zero:
          br label %merge
        nonzero:
          %quotient = udiv i64 %arg0, %arg1
          br label %merge
        merge:
          %result = phi i64 [ 0, %zero ], [ %quotient, %nonzero ]
          ret i64 %result
        }

        define i64 @fixture_urem(i64 %arg0, i64 %arg1) {
        entry:
          %iszero = icmp eq i64 %arg1, 0
          br i1 %iszero, label %zero, label %nonzero
        zero:
          br label %merge
        nonzero:
          %remainder = urem i64 %arg0, %arg1
          br label %merge
        merge:
          %result = phi i64 [ %arg0, %zero ], [ %remainder, %nonzero ]
          ret i64 %result
        }

        define i32 @fixture_shl(i32 %arg0, i32 %arg1) {
        entry:
          %masked = and i32 %arg1, 31
          %shifted = shl i32 %arg0, %masked
          ret i32 %shifted
        }

        define i8 @fixture_lshr(i8 %arg0, i8 %arg1) {
        entry:
          %masked = and i8 %arg1, 7
          %shifted = lshr i8 %arg0, %masked
          ret i8 %shifted
        }

        define i64 @fixture_conditional(i1 %condition, i64 %arg1, i64 %arg2) {
        entry:
          br i1 %condition, label %then, label %else
        then:
          br label %merge
        else:
          br label %merge
        merge:
          %result = phi i64 [ %arg1, %then ], [ %arg2, %else ]
          ret i64 %result
        }
        """
    ).lstrip()


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise AssertionError(f"mutation anchor occurs {source.count(before)} times: {before!r}")
    return source.replace(before, after, 1)


def replace_once_in_definition(
    ir: str, symbol: str, before: str, after: str
) -> str:
    body = audit_core0._ir_definition_body(ir, symbol)
    mutated_body = replace_once(body, before, after)
    return replace_once(ir, body, mutated_body)


class Gate3ManifestAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()

    def test_closed_v02_manifest_is_accepted(self) -> None:
        self.assertEqual(
            audit_core0.validate_cfg_suite_manifest(self.manifest), self.manifest
        )

    def test_unknown_or_regressed_profile_is_rejected(self) -> None:
        for profile in ("core0-v0.1", "core0-v0.3", "", None):
            with self.subTest(profile=profile):
                tampered = copy.deepcopy(self.manifest)
                tampered["contract_version"] = profile
                with self.assertRaisesRegex(Core0Error, "unsupported Core0 contract"):
                    audit_core0.validate_cfg_suite_manifest(tampered)

    def test_profile_field_cannot_be_omitted_or_duplicated_under_an_alias(self) -> None:
        missing = copy.deepcopy(self.manifest)
        del missing["contract_version"]
        with self.assertRaisesRegex(Core0Error, "fields differ from the schema"):
            audit_core0.validate_cfg_suite_manifest(missing)

        aliased = copy.deepcopy(self.manifest)
        aliased["profile"] = aliased["contract_version"]
        with self.assertRaisesRegex(Core0Error, "fields differ from the schema"):
            audit_core0.validate_cfg_suite_manifest(aliased)

    def test_cfg_contract_and_primitive_contract_tampering_are_rejected(self) -> None:
        cfg_tampered = copy.deepcopy(self.manifest)
        cfg_tampered["cfg_validation"]["division"] = "llvm-undefined-on-zero"
        with self.assertRaisesRegex(Core0Error, "CFG contract differs"):
            audit_core0.validate_cfg_suite_manifest(cfg_tampered)

        primitive_tampered = copy.deepcopy(self.manifest)
        shift = next(
            primitive
            for primitive in primitive_tampered["used_primitives"]
            if primitive["stable_id"] == "u64.shl"
        )
        shift["lean_identities"] = ["Custom.shiftLeft"]
        with self.assertRaisesRegex(Core0Error, "unknown/malformed"):
            audit_core0.validate_cfg_suite_manifest(primitive_tampered)


class Gate3StructuredSemanticsAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = cfg_semantics_manifest_fixture()
        self.ir = cfg_ir_fixture()

    def test_exact_guards_masks_and_branch_phi_are_accepted(self) -> None:
        result = audit_core0.validate_cfg_pre_semantics(self.manifest, self.ir)
        self.assertEqual(result["source_selects"], 0)
        self.assertEqual(result["source_branch_functions"], 1)
        self.assertEqual(
            {record["operation"] for record in result["guarded_division_remainder"]},
            {"udiv", "urem"},
        )
        self.assertEqual(
            {record["operation"] for record in result["masked_shifts"]},
            {"shl", "lshr"},
        )

    def test_guarding_the_dividend_instead_of_the_divisor_is_rejected(self) -> None:
        mutated = replace_once_in_definition(
            self.ir,
            "fixture_udiv",
            "%iszero = icmp eq i64 %arg1, 0",
            "%iszero = icmp eq i64 %arg0, 0",
        )
        with self.assertRaisesRegex(Core0Error, "exact divisor-zero guard"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_inverting_the_zero_and_nonzero_edges_is_rejected(self) -> None:
        mutated = replace_once_in_definition(
            self.ir,
            "fixture_udiv",
            "br i1 %iszero, label %zero, label %nonzero",
            "br i1 %iszero, label %nonzero, label %zero",
        )
        with self.assertRaisesRegex(Core0Error, "exact divisor-zero guard"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_zero_edge_cannot_flow_into_the_dangerous_block(self) -> None:
        mutated = replace_once_in_definition(
            self.ir,
            "fixture_udiv",
            "zero:\n  br label %merge",
            "zero:\n  br label %nonzero",
        )
        with self.assertRaisesRegex(Core0Error, "reachable from the divisor-zero"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_dangerous_block_cannot_have_a_guard_bypass_predecessor(self) -> None:
        mutated = replace_once_in_definition(
            self.ir,
            "fixture_udiv",
            "entry:\n  %iszero = icmp eq i64 %arg1, 0",
            "entry:\n"
            "  %bypass = icmp eq i64 %arg1, 0\n"
            "  br i1 %bypass, label %nonzero, label %guard\n"
            "guard:\n"
            "  %iszero = icmp eq i64 %arg1, 0",
        )
        with self.assertRaisesRegex(Core0Error, "unguarded predecessor set"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_hoisting_division_before_its_guard_is_rejected(self) -> None:
        mutated = replace_once_in_definition(
            self.ir,
            "fixture_udiv",
            "entry:\n  %iszero = icmp eq i64 %arg1, 0",
            "entry:\n  %quotient = udiv i64 %arg0, %arg1\n"
            "  %iszero = icmp eq i64 %arg1, 0",
        )
        mutated = replace_once_in_definition(
            mutated,
            "fixture_udiv",
            "nonzero:\n  %quotient = udiv i64 %arg0, %arg1",
            "nonzero:",
        )
        with self.assertRaisesRegex(Core0Error, "exact divisor-zero guard"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_wrong_shift_mask_is_rejected(self) -> None:
        mutated = replace_once(
            self.ir, "%masked = and i32 %arg1, 31", "%masked = and i32 %arg1, 63"
        )
        with self.assertRaisesRegex(Core0Error, "same-block source-count `i32 and 31` mask"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_masking_the_value_instead_of_the_source_count_is_rejected(self) -> None:
        mutated = replace_once(
            self.ir, "%masked = and i32 %arg1, 31", "%masked = and i32 %arg0, 31"
        )
        with self.assertRaisesRegex(Core0Error, "same-block source-count `i32 and 31` mask"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_raw_unmasked_shift_count_is_rejected(self) -> None:
        mutated = replace_once(
            self.ir,
            "%shifted = lshr i8 %arg0, %masked",
            "%shifted = lshr i8 %arg0, %arg1",
        )
        with self.assertRaisesRegex(Core0Error, "same-block source-count `i8 and 7` mask"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_mask_computed_only_in_a_predecessor_is_rejected(self) -> None:
        mutated = replace_once(
            self.ir,
            "entry:\n  %masked = and i32 %arg1, 31\n"
            "  %shifted = shl i32 %arg0, %masked",
            "entry:\n  %masked = and i32 %arg1, 31\n"
            "  br label %shift\n"
            "shift:\n  %shifted = shl i32 %arg0, %masked",
        )
        with self.assertRaisesRegex(Core0Error, "same-block source-count `i32 and 31` mask"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)

    def test_eager_select_for_a_source_conditional_is_rejected(self) -> None:
        mutated = replace_once(
            self.ir,
            "entry:\n  br i1 %condition, label %then, label %else\n"
            "then:\n  br label %merge\n"
            "else:\n  br label %merge\n"
            "merge:\n  %result = phi i64 [ %arg1, %then ], [ %arg2, %else ]\n"
            "  ret i64 %result",
            "entry:\n  %result = select i1 %condition, i64 %arg1, i64 %arg2\n"
            "  ret i64 %result",
        )
        with self.assertRaisesRegex(Core0Error, "contains eager LLVM select"):
            audit_core0.validate_cfg_pre_semantics(self.manifest, mutated)


if __name__ == "__main__":
    unittest.main()
