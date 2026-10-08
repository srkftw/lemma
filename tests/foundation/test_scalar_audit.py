#!/usr/bin/env python3
"""Focused fail-closed tests for the Gate 2 scalar artifact audit."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0  # noqa: E402
from core0_common import Core0Error  # noqa: E402


def manifest_fixture() -> dict[str, object]:
    functions: list[dict[str, object]] = []
    source_symbols: dict[str, str] = {}
    for index, (source, args, result, dependencies) in enumerate(
        audit_core0.SCALAR_FUNCTION_CONTRACTS
    ):
        symbol = f"gate2_fn_{index}"
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
        for source, args, result, _dependencies in audit_core0.SCALAR_FUNCTION_CONTRACTS
    }
    roots: list[dict[str, object]] = []
    for root_id, source in enumerate(audit_core0.SCALAR_ROOT_SOURCES, 1):
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
        "artifact_category": audit_core0.TEST_FRONTEND_SUITE_POLICY,
        "contract_version": "core0-v0.1",
        "test_abi": audit_core0.SCALAR_TEST_ABI,
        "suite_id": "0123456789abcdef",
        "source_seed": "4c454d4d41323032",
        "runtime_seed": "52554e54494d4532",
        "roots": roots,
        "functions": functions,
        "used_primitives": copy.deepcopy(list(audit_core0.PRIMITIVE_CONTRACTS.values())),
        "machine_primitives": copy.deepcopy(audit_core0.EXPECTED_SCALAR_MACHINE_PRIMITIVES),
    }


def abi_fixture(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": audit_core0.SCALAR_TEST_ABI,
        "byte_order": "little-endian",
        "magic_bytes": "4c454d4d41303032",
        "magic_word": "0x323030414d4d454c",
        "version": 1,
        "header_bytes": 128,
        "record_bytes": 136,
        "maximum_arguments": 16,
        "maximum_cases": 29,
        "tags": {"bool": 1, "u8": 2, "u32": 3, "u64": 4},
        "header_words": [
            "magic", "version", "header_bytes", "record_bytes", "suite_id",
            "batch_id", "root_id", "case_count", "argument_count", "result_tag",
            "argument_tags_0_7", "argument_tags_8_15", "source_seed", "runtime_seed",
            "reserved_zero", "reserved_zero",
        ],
        "record_layout": "case_id:u64,arguments:16xu64; unused slots zero",
        "transport_rules": (
            "Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; "
            "reject before truncation; zero-extend narrow results to u64"
        ),
        "output_protocol": {
            "banner": "LEMMA_SCALAR/1\n",
            "batch": "BATCH:<suite16>:<batch16>:<root16>:<count16>\n",
            "result": "RESULT:<case16>:<tag16>:<value16>\n",
            "end": "END:<batch16>:<count16>\n",
            "hex": "lowercase fixed-width",
        },
        "suite_id": manifest["suite_id"],
        "source_seed": manifest["source_seed"],
        "runtime_seed": manifest["runtime_seed"],
    }


def companions(manifest: dict[str, object]) -> tuple[str, str]:
    normalized = [f"contract={manifest['contract_version']}"]
    symbols: list[str] = []
    for root in manifest["roots"]:
        signature = json.dumps(root["signature"], separators=(",", ":"))
        normalized.append(
            f"root={root['root_id']};source={root['source']};signature={signature}"
        )
    for function in manifest["functions"]:
        signature = json.dumps(function["signature"], separators=(",", ":"))
        normalized.append(
            f"function={function['source']};signature={signature};body={function['body']}"
        )
        symbols.append(f"source={function['source']};llvm={function['llvm']}")
    for primitive in manifest["used_primitives"]:
        normalized.append(f"primitive={primitive['stable_id']}")
    return "\n".join(normalized) + "\n", "\n".join(symbols) + "\n"


def _call(signature: dict[str, object], symbol: str, result_name: str) -> str:
    args = signature["args"]
    result = signature["result"]
    rendered = ", ".join(
        f"{audit_core0._llvm_scalar_parameter(arg)} 0" for arg in args
    )
    return (
        f"  %{result_name} = call {audit_core0._llvm_scalar_return(result)} "
        f"@{symbol}({rendered})"
    )


def pre_ir_fixture(manifest: dict[str, object]) -> str:
    functions = manifest["functions"]
    by_source = {function["source"]: function for function in functions}
    lines: list[str] = []
    for function in functions:
        signature = function["signature"]
        parameters = ", ".join(
            f"{audit_core0._llvm_scalar_parameter(arg)} %arg{index}"
            for index, arg in enumerate(signature["args"])
        )
        lines.append(
            f"define {audit_core0._llvm_scalar_return(signature['result'])} "
            f"@{function['llvm']}({parameters}) nounwind noinline "
            '"disable-tail-calls"="true" {'
        )
        lines.append("entry:")
        for index, dependency in enumerate(function["dependencies"]):
            callee = by_source[dependency]
            lines.append(_call(callee["signature"], callee["llvm"], f"dep{index}"))
        lines.append(f"  ret {audit_core0._llvm_scalar_type(signature['result'])} 0")
        lines.append("}")
    lines.extend(
        [
            "define void @core0_exit_failure() {\nentry:\n  ret void\n}",
            "define void @core0_exit_success() {\nentry:\n  ret void\n}",
            "define void @core0_uart_putc() {\nentry:\n  ret void\n}",
            "define void @core0_uart_drain() {\nentry:\n  ret void\n}",
            "define void @core0_put_hex64() {\nentry:\n  ret void\n}",
            "define void @core0_main() {",
            "entry:",
        ]
    )
    for index, root in enumerate(manifest["roots"]):
        lines.append(_call(root["signature"], root["llvm"], f"root{index}"))
    lines.extend(["  ret void", "}"])
    return "\n".join(lines) + "\n"


def disassembly_fixture(manifest: dict[str, object]) -> str:
    symbols = {function["source"]: function["llvm"] for function in manifest["functions"]}
    caller = symbols[audit_core0.SCALAR_ABI_ROOT]
    callee = symbols[audit_core0.SCALAR_ABI_CALLEE]
    return f"""
0000000000001000 <{caller}>:
1000: addi sp, sp, -0x20
1004: sd ra, 0x18(sp)
1008: ld t0, 0x20(sp)
100c: ld t1, 0x28(sp)
1010: sd t0, 0x0(sp)
1014: sd t1, 0x8(sp)
1018: jalr -0x20(ra) <{callee}>
101c: ld ra, 0x18(sp)
1020: addi sp, sp, 0x20
1024: ret

0000000000002000 <{callee}>:
2000: ld t0, 0x0(sp)
2004: ld t1, 0x8(sp)
2008: add a0, t0, t1
200c: ret
"""


class ScalarAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = manifest_fixture()

    def test_exact_manifest_abi_and_companions_are_accepted(self) -> None:
        parsed = audit_core0.validate_scalar_suite_manifest(self.manifest)
        audit_core0.validate_scalar_test_abi(abi_fixture(parsed), parsed)
        normalized, symbols = companions(parsed)
        audit_core0.validate_scalar_manifest_companions(parsed, normalized, symbols)

    def test_manifest_rejects_root_catalog_tamper(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["roots"].pop()
        with self.assertRaisesRegex(Core0Error, "exact 37-root"):
            audit_core0.validate_scalar_suite_manifest(tampered)

    def test_manifest_rejects_duplicate_symbol(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["functions"][1]["llvm"] = tampered["functions"][0]["llvm"]
        with self.assertRaisesRegex(Core0Error, "invalid/duplicate LLVM symbol"):
            audit_core0.validate_scalar_suite_manifest(tampered)

    def test_manifest_rejects_abi_extension_tamper(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["functions"][3]["parameter_extensions"][0] = "signext"
        with self.assertRaisesRegex(Core0Error, "wrong parameter extensions"):
            audit_core0.validate_scalar_suite_manifest(tampered)

    def test_manifest_rejects_missing_noinline(self) -> None:
        tampered = copy.deepcopy(self.manifest)
        tampered["functions"][0]["noinline"] = False
        with self.assertRaisesRegex(Core0Error, "not pinned noinline"):
            audit_core0.validate_scalar_suite_manifest(tampered)

    def test_wire_abi_rejects_layout_and_seed_tamper(self) -> None:
        for field, value, diagnostic in (
            ("record_bytes", 128, "closed wire contract"),
            ("runtime_seed", "0000000000000000", "differs from the suite"),
            ("record_layout", "opaque", "closed wire contract"),
        ):
            with self.subTest(field=field):
                tampered = abi_fixture(self.manifest)
                tampered[field] = value
                with self.assertRaisesRegex(Core0Error, diagnostic):
                    audit_core0.validate_scalar_test_abi(tampered, self.manifest)

    def test_export_configuration_is_bound_to_manifest_seeds(self) -> None:
        value = {
            "driver": audit_core0.SCALAR_EXPORT_DRIVER,
            "generation_command": [
                "lake",
                "env",
                "lean",
                str((ROOT / audit_core0.SCALAR_EXPORT_DRIVER).resolve()),
            ],
            "environment": {
                "LEMMA_SCALAR_RUNTIME_SEED": str(
                    int(str(self.manifest["runtime_seed"]), 16)
                ),
                "LEMMA_SCALAR_SOURCE_SEED": str(
                    int(str(self.manifest["source_seed"]), 16)
                ),
                "LEMMA_SCALAR_SUITE_ID": str(
                    int(str(self.manifest["suite_id"]), 16)
                ),
            },
        }
        audit_core0.validate_scalar_export_configuration(value, self.manifest, ROOT)
        audit_core0.validate_scalar_export_command_log(
            value, [["unrelated"], value["generation_command"]]
        )
        with self.assertRaisesRegex(Core0Error, "omits the exact scalar exporter"):
            audit_core0.validate_scalar_export_command_log(value, [["unrelated"]])
        tampered = copy.deepcopy(value)
        tampered["environment"]["LEMMA_SCALAR_RUNTIME_SEED"] = "0"
        with self.assertRaisesRegex(Core0Error, "differ from the checked suite"):
            audit_core0.validate_scalar_export_configuration(
                tampered, self.manifest, ROOT
            )

    def test_pre_ir_abi_and_dynamic_symbols_are_accepted(self) -> None:
        finding = audit_core0.validate_scalar_pre_abi(
            self.manifest, pre_ir_fixture(self.manifest)
        )
        self.assertEqual(finding["root_count"], 37)
        self.assertEqual(finding["function_count"], 43)

    def test_pre_ir_rejects_call_site_extension_tamper(self) -> None:
        ir = pre_ir_fixture(self.manifest)
        target = self.manifest["roots"][3]["llvm"]
        old = f"call zeroext i8 @{target}(i8 zeroext 0, i8 zeroext 0)"
        tampered = ir.replace(old, f"call zeroext i8 @{target}(i8 signext 0, i8 zeroext 0)", 1)
        self.assertNotEqual(ir, tampered)
        with self.assertRaisesRegex(Core0Error, "argument #0 has the wrong LP64 attribute"):
            audit_core0.validate_scalar_pre_abi(self.manifest, tampered)

    def test_pre_ir_rejects_missing_disable_tail_calls(self) -> None:
        ir = pre_ir_fixture(self.manifest)
        tampered = ir.replace(' "disable-tail-calls"="true"', "", 1)
        with self.assertRaisesRegex(Core0Error, "exact LP64 ABI/noinline header"):
            audit_core0.validate_scalar_pre_abi(self.manifest, tampered)

    def test_disassembly_proves_real_aligned_stack_call(self) -> None:
        finding = audit_core0.validate_scalar_abi_disassembly(
            self.manifest, disassembly_fixture(self.manifest), "O2"
        )
        self.assertEqual(finding["caller_frame_bytes"], 32)
        self.assertEqual(finding["stack_argument_offsets"], [0, 8])

    def test_disassembly_rejects_tail_transfer_and_missing_stack_slot(self) -> None:
        fixture = disassembly_fixture(self.manifest)
        for tampered, diagnostic in (
            (fixture.replace("jalr", "jr", 1), "real link-register call"),
            (fixture.replace("sd t1, 0x8(sp)", "sd t1, 0x10(sp)", 1), "argument 9"),
        ):
            with self.subTest(diagnostic=diagnostic):
                with self.assertRaisesRegex(Core0Error, diagnostic):
                    audit_core0.validate_scalar_abi_disassembly(
                        self.manifest, tampered, "O2"
                    )


if __name__ == "__main__":
    unittest.main()
