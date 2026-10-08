#!/usr/bin/env python3
"""Synthetic positive and mutation tests for the independent Gate 5 audit."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_memory  # noqa: E402
from core0_common import Core0Error  # noqa: E402


BASE = "Lemma.Examples.Foundation.Memory"
STATUS = f"{BASE}.statusEcho"
READER = f"{BASE}.load64Value"
WRITER = f"{BASE}.store32Status"
CALLER = f"{BASE}.combined"


def closed_manifest_fixture() -> dict[str, object]:
    functions = [
        {
            "source": STATUS,
            "llvm": "core0_action_0",
            "signature": {"args": ["u8", "u64"]},
            "scalar_dependencies": [],
            "action_dependencies": [],
            "direct_effects": [],
            "transitive_effects": [],
            "body": "(action.done (var 0 u8) (var 1 u64))",
            "noinline": True,
        },
        {
            "source": READER,
            "llvm": "core0_action_1",
            "signature": {"args": ["u8", "u64"]},
            "scalar_dependencies": [],
            "action_dependencies": [],
            "direct_effects": ["checked-access", "fixed-ram-read"],
            "transitive_effects": ["checked-access", "fixed-ram-read"],
            "body": (
                "(action.load64 (var 0 u8) (var 1 u64) "
                "(status %2) (value %3) (action.done (var 2 u8) (var 3 u64)))"
            ),
            "noinline": True,
        },
        {
            "source": WRITER,
            "llvm": "core0_action_2",
            "signature": {"args": ["u8", "u64", "u32"]},
            "scalar_dependencies": [],
            "action_dependencies": [],
            "direct_effects": ["checked-access", "fixed-ram-write"],
            "transitive_effects": ["checked-access", "fixed-ram-write"],
            "body": (
                "(action.store32 (var 0 u8) (var 1 u64) (var 2 u32) "
                "(status %3) (action.done (var 3 u8) (lit u64 0)))"
            ),
            "noinline": True,
        },
        {
            "source": CALLER,
            "llvm": "core0_action_3",
            "signature": {"args": ["u8", "u64", "u32"]},
            "scalar_dependencies": [],
            "action_dependencies": [READER, WRITER],
            "direct_effects": [],
            "transitive_effects": [
                "checked-access",
                "fixed-ram-read",
                "fixed-ram-write",
            ],
            "body": (
                f"(action.bind (action.call {READER} [(var 0 u8) (var 1 u64)]) "
                f"(status %3) (value %4) (action.call {WRITER} "
                "[(var 0 u8) (var 1 u64) (var 2 u32)]))"
            ),
            "noinline": True,
        },
    ]
    roots = [
        {
            "root_id": 1,
            "source": STATUS,
            "llvm": "core0_action_0",
            "signature": {"args": ["u8", "u64"]},
        },
        {
            "root_id": 2,
            "source": CALLER,
            "llvm": "core0_action_3",
            "signature": {"args": ["u8", "u64", "u32"]},
        },
    ]
    return {
        "schema_version": 1,
        "artifact_category": audit_memory.ARTIFACT_CATEGORY,
        "contract_version": audit_memory.CONTRACT_VERSION,
        "test_abi": audit_memory.TEST_ABI,
        "suite_id": "5a4f2c19d077b831",
        "source_seed": "4c454d4d41353035",
        "runtime_seed": "52554e54494d4535",
        "checked_result": copy.deepcopy(audit_memory.CHECKED_RESULT_CONTRACT),
        "memory_contract": copy.deepcopy(audit_memory.MEMORY_CONTRACT),
        "roots": roots,
        "scalar_functions": [],
        "action_functions": functions,
        "used_primitives": [],
        "used_memory_ops": [
            copy.deepcopy(audit_memory.MEMORY_OPS[stable_id])
            for stable_id in ("ram.read64", "ram.write32")
        ],
        "action_iterations": [],
        "machine_primitives": [],
    }


def _or_tree(stem: str, region_arg: str, ids: list[int]) -> tuple[list[str], str]:
    lines = [
        f"  %{stem}.eq.{region_id} = icmp eq i8 %{region_arg}, {region_id}"
        for region_id in ids
    ]
    current = f"%{stem}.eq.{ids[0]}"
    for index, region_id in enumerate(ids[1:], 1):
        name = f"{stem}.or.{index}"
        lines.append(f"  %{name} = or i1 {current}, %{stem}.eq.{region_id}")
        current = f"%{name}"
    return lines, current


def _result(status: int, stem: str, value: str = "0") -> list[str]:
    return [
        f"  %{stem}.status = insertvalue {{ i64, i64 }} poison, i64 {status}, 0",
        f"  %{stem}.result = insertvalue {{ i64, i64 }} %{stem}.status, i64 {value}, 1",
        f"  ret {{ i64, i64 }} %{stem}.result",
    ]


def _guarded_access_function(
    *,
    symbol: str,
    site: int,
    access: str,
    bits: int,
) -> str:
    if access not in {"read", "write"}:
        raise AssertionError(access)
    width = bits // 8
    prefix = f"mem.{site}"
    params = "i8 zeroext %arg0, i64 %arg1"
    if access == "write":
        params += f", i{bits} {'signext ' if bits == 32 else ''}%arg2"

    lines = [
        f'define {{ i64, i64 }} @{symbol}({params}) nounwind noinline "disable-tail-calls"="true" {{',
        "entry:",
    ]
    known_ids = [1, 2, 3, 4, 112, 113, 128, 129]
    known_lines, known_value = _or_tree(f"{prefix}.known", "arg0", known_ids)
    lines.extend(known_lines)
    lines.append(f"  %{prefix}.region-known = or i1 {known_value}, false")
    lines.append(
        f"  br i1 %{prefix}.region-known, label %{prefix}.known, label %{prefix}.unknown"
    )

    lines.append(f"{prefix}.known:")
    class_lines, class_value = _or_tree(f"{prefix}.class", "arg0", [1, 2, 3, 4])
    lines.extend(class_lines)
    lines.append(f"  %{prefix}.class-ok = or i1 {class_value}, false")
    lines.append(
        f"  br i1 %{prefix}.class-ok, label %{prefix}.ordinary, label %{prefix}.class-denied"
    )

    lines.append(f"{prefix}.ordinary:")
    permitted = [1, 2, 3, 4] if access == "read" else [1, 3, 4]
    permission_lines, permission_value = _or_tree(
        f"{prefix}.permission", "arg0", permitted
    )
    lines.extend(permission_lines)
    lines.append(f"  %{prefix}.permission-ok = or i1 {permission_value}, false")
    permission_denied = "read-denied" if access == "read" else "write-denied"
    lines.append(
        f"  br i1 %{prefix}.permission-ok, label %{prefix}.permission, "
        f"label %{prefix}.{permission_denied}"
    )

    lines.append(f"{prefix}.permission:")
    width_ids = [1, 2, 3] if width == 1 else [1, 2, 3, 4]
    width_lines, width_value = _or_tree(f"{prefix}.width", "arg0", width_ids)
    lines.extend(width_lines)
    lines.append(f"  %{prefix}.width-ok = or i1 {width_value}, false")
    lines.append(
        f"  br i1 %{prefix}.width-ok, label %{prefix}.width, label %{prefix}.width-denied"
    )

    lines.extend(
        [
            f"{prefix}.width:",
            f"  %{prefix}.length-ok = icmp uge i64 4096, {width}",
            f"  br i1 %{prefix}.length-ok, label %{prefix}.remaining-block, label %{prefix}.bounds-a",
            f"{prefix}.remaining-block:",
            f"  %{prefix}.remaining = sub i64 4096, {width}",
            f"  %{prefix}.offset-ok = icmp ule i64 %arg1, %{prefix}.remaining",
            f"  br i1 %{prefix}.offset-ok, label %{prefix}.offset, label %{prefix}.bounds-b",
            f"{prefix}.offset:",
            f"  %{prefix}.alignment-mask = and i64 %arg1, {width - 1}",
            f"  %{prefix}.alignment-ok = icmp eq i64 %{prefix}.alignment-mask, 0",
            f"  br i1 %{prefix}.alignment-ok, label %{prefix}.access, label %{prefix}.misaligned",
            f"{prefix}.access:",
            f"  %{prefix}.base.2 = select i1 %{prefix}.known.eq.2, i64 2164260864, i64 2155876352",
            f"  %{prefix}.base.3 = select i1 %{prefix}.known.eq.3, i64 2155884544, i64 %{prefix}.base.2",
            f"  %{prefix}.base = select i1 %{prefix}.known.eq.4, i64 2155892736, i64 %{prefix}.base.3",
            f"  %{prefix}.address = add i64 %{prefix}.base, %arg1",
            f"  %{prefix}.pointer = inttoptr i64 %{prefix}.address to ptr",
        ]
    )
    if access == "read":
        lines.extend(
            [
                f"  %{prefix}.loaded = load volatile i{bits}, ptr %{prefix}.pointer, align {width}",
                *(
                    [f"  %{prefix}.value = zext i{bits} %{prefix}.loaded to i64"]
                    if bits < 64
                    else []
                ),
                f"  %{prefix}.ok.status = insertvalue {{ i64, i64 }} poison, i64 0, 0",
                f"  %{prefix}.ok.result = insertvalue {{ i64, i64 }} %{prefix}.ok.status, i64 "
                f"%{prefix}.{'value' if bits < 64 else 'loaded'}, 1",
                f"  ret {{ i64, i64 }} %{prefix}.ok.result",
            ]
        )
    else:
        lines.append(
            f"  store volatile i{bits} %arg2, ptr %{prefix}.pointer, align {width}"
        )
        lines.extend(_result(0, f"{prefix}.ok"))

    lines.extend(
        [
            f"{prefix}.unknown:",
            *_result(1, f"{prefix}.unknown"),
            f"{prefix}.class-denied:",
            f"  %{prefix}.device.128 = icmp eq i8 %arg0, 128",
            f"  %{prefix}.device.129 = icmp eq i8 %arg0, 129",
            f"  %{prefix}.is-device = or i1 %{prefix}.device.128, %{prefix}.device.129",
            f"  br i1 %{prefix}.is-device, label %{prefix}.device-denied, label %{prefix}.reserved-denied",
            f"{prefix}.reserved-denied:",
            *_result(2, f"{prefix}.reserved-denied"),
            f"{prefix}.device-denied:",
            *_result(3, f"{prefix}.device-denied"),
            f"{prefix}.{permission_denied}:",
            *_result(4 if access == "read" else 5, f"{prefix}.{permission_denied}"),
            f"{prefix}.width-denied:",
            *_result(6, f"{prefix}.width-denied"),
            f"{prefix}.bounds-a:",
            *_result(7, f"{prefix}.bounds-a"),
            f"{prefix}.bounds-b:",
            *_result(7, f"{prefix}.bounds-b"),
            f"{prefix}.misaligned:",
            *_result(8, f"{prefix}.misaligned"),
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def valid_ir_fixture() -> str:
    status = """define { i64, i64 } @core0_action_0(i8 zeroext %arg0, i64 %arg1) nounwind noinline "disable-tail-calls"="true" {
entry:
  %status.word = zext i8 %arg0 to i64
  %status.partial = insertvalue { i64, i64 } poison, i64 %status.word, 0
  %result = insertvalue { i64, i64 } %status.partial, i64 %arg1, 1
  ret { i64, i64 } %result
}
"""
    reader = _guarded_access_function(
        symbol="core0_action_1", site=0, access="read", bits=64
    )
    writer = _guarded_access_function(
        symbol="core0_action_2", site=0, access="write", bits=32
    )
    caller = """define { i64, i64 } @core0_action_3(i8 zeroext %arg0, i64 %arg1, i32 signext %arg2) nounwind noinline "disable-tail-calls"="true" {
entry:
  %read.result = call { i64, i64 } @core0_action_1(i8 zeroext %arg0, i64 %arg1)
  %read.status = extractvalue { i64, i64 } %read.result, 0
  %read.value = extractvalue { i64, i64 } %read.result, 1
  %write.result = call { i64, i64 } @core0_action_2(i8 zeroext %arg0, i64 %arg1, i32 signext %arg2)
  %write.status = extractvalue { i64, i64 } %write.result, 0
  %write.value = extractvalue { i64, i64 } %write.result, 1
  %combined.status = or i64 %read.status, %write.status
  %combined.value = xor i64 %read.value, %write.value
  %partial = insertvalue { i64, i64 } poison, i64 %combined.status, 0
  %result = insertvalue { i64, i64 } %partial, i64 %combined.value, 1
  ret { i64, i64 } %result
}
"""
    return status + reader + writer + caller


def production_range_function(symbol: str, *, access: str = "read") -> str:
    """Render the production eight-ID dispatch for a dynamic range preflight."""
    if access not in {"read", "write"}:
        raise AssertionError(access)
    ids = [1, 2, 3, 4, 112, 113, 128, 129]
    bases = [2155876352, 2164260864, 2155884544, 2155892736, 2147483648, 2155806720, 268435456, 1048576]
    lengths = [4096, 4096, 4096, 4096, 8323072, 65536, 256, 4096]
    classes = [0, 0, 0, 0, 1, 1, 2, 2]
    permissions = [1, 1 if access == "read" else 0, 1, 1, 0, 0, 0, 0]
    region_blocks = [f"mem.0.region.{region_id}.{2 * index + 2}" for index, region_id in enumerate(ids)]
    lookup_blocks = ["entry", *[f"mem.0.lookup.next.{2 * index + 3}" for index in range(7)]]
    final_unknown = "mem.0.lookup.next.17"
    lines = [
        f'define {{ i64, i64 }} @{symbol}(i8 zeroext %arg0, i64 %arg1, i64 %arg2) nounwind noinline "disable-tail-calls"="true" {{'
    ]
    for index, region_id in enumerate(ids):
        lines.append(f"{lookup_blocks[index]}:")
        lines.append(f"  %mem.0.region-known.{index} = icmp eq i8 %arg0, {region_id}")
        false_target = final_unknown if index == 7 else f"mem.0.lookup.next.{2 * index + 3}"
        lines.append(
            f"  br i1 %mem.0.region-known.{index}, label %{region_blocks[index]}, "
            f"label %{false_target}"
        )
        lines.append(f"{region_blocks[index]}:")
        lines.append("  br label %mem.0.metadata.0")
    lines.extend([f"{final_unknown}:", "  br label %mem.0.outcome.1", "mem.0.metadata.0:"])

    def phi(name: str, ty: str, values: list[int]) -> str:
        incoming = ", ".join(
            f"[ {value}, %{block} ]" for value, block in zip(values, region_blocks)
        )
        return f"  %mem.0.{name} = phi {ty} {incoming}"

    lines.extend(
        [
            phi("base.8", "i64", bases),
            phi("length.9", "i64", lengths),
            phi("class.10", "i8", classes),
            phi("permission-ok.11", "i1", permissions),
            phi("width-ok.12", "i1", [1] * 8),
            "  %mem.0.class-ok.13 = icmp eq i8 %mem.0.class.10, 0",
            "  br i1 %mem.0.class-ok.13, label %mem.0.permission.18, label %mem.0.class-denied.19",
            "mem.0.class-denied.19:",
            "  %mem.0.class-is-reserved.14 = icmp eq i8 %mem.0.class.10, 1",
            "  br i1 %mem.0.class-is-reserved.14, label %mem.0.reserved.20, label %mem.0.device.21",
            "mem.0.reserved.20:",
            "  br label %mem.0.outcome.1",
            "mem.0.device.21:",
            "  br label %mem.0.outcome.1",
            "mem.0.permission.18:",
            "  br i1 %mem.0.permission-ok.11, label %mem.0.width.22, label %mem.0.permission-denied.23",
            "mem.0.permission-denied.23:",
            "  br label %mem.0.outcome.1",
            "mem.0.width.22:",
            "  br i1 %mem.0.width-ok.12, label %mem.0.length-guard.24, label %mem.0.width-denied.25",
            "mem.0.width-denied.25:",
            "  br label %mem.0.outcome.1",
            "mem.0.length-guard.24:",
            "  %mem.0.length-ok.15 = icmp ule i64 %arg2, %mem.0.length.9",
            "  br i1 %mem.0.length-ok.15, label %mem.0.subtract.26, label %mem.0.bounds-length-denied.27",
            "mem.0.bounds-length-denied.27:",
            "  br label %mem.0.outcome.1",
            "mem.0.subtract.26:",
            "  %mem.0.remaining.16 = sub i64 %mem.0.length.9, %arg2",
            "  %mem.0.offset-ok.17 = icmp ule i64 %arg1, %mem.0.remaining.16",
            "  br i1 %mem.0.offset-ok.17, label %mem.0.in-bounds.28, label %mem.0.bounds-offset-denied.29",
            "mem.0.bounds-offset-denied.29:",
            "  br label %mem.0.outcome.1",
            "mem.0.in-bounds.28:",
            "  br label %mem.0.outcome.1",
            "mem.0.outcome.1:",
            "  %mem.0.status.18 = phi i8 "
            "[ 1, %mem.0.lookup.next.17 ], [ 2, %mem.0.reserved.20 ], "
            "[ 3, %mem.0.device.21 ], "
            f"[ {4 if access == 'read' else 5}, %mem.0.permission-denied.23 ], "
            "[ 6, %mem.0.width-denied.25 ], [ 7, %mem.0.bounds-length-denied.27 ], "
            "[ 7, %mem.0.bounds-offset-denied.29 ], [ 0, %mem.0.in-bounds.28 ]",
            "  %action.result.status-word20 = zext i8 %mem.0.status.18 to i64",
            "  %action.result.partial21 = insertvalue { i64, i64 } poison, i64 %action.result.status-word20, 0",
            "  %action.result.complete22 = insertvalue { i64, i64 } %action.result.partial21, i64 0, 1",
            "  ret { i64, i64 } %action.result.complete22",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


class Gate5ManifestContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()

    def test_exact_contract_and_effect_closure_are_accepted(self) -> None:
        with self.assertRaisesRegex(Core0Error, "exact 26-root"):
            audit_memory.validate_memory_suite_manifest(self.manifest)
        self.assertEqual(
            audit_memory.validate_memory_suite_manifest(
                self.manifest, require_closed_suite=False
            ),
            self.manifest,
        )
        result = audit_memory.validate_effect_closure(self.manifest)
        self.assertEqual(result["action_function_count"], 4)
        self.assertEqual(result["root_count"], 2)
        self.assertEqual(result["memory_operations"], ["ram.read64", "ram.write32"])

    def test_exact_region_and_status_catalogs_are_closed(self) -> None:
        self.assertEqual(len(audit_memory.REGIONS), 8)
        self.assertEqual(len(audit_memory.STATUSES), 10)
        self.assertEqual(
            [region["id"] for region in audit_memory.REGIONS],
            [1, 2, 3, 4, 0x70, 0x71, 0x80, 0x81],
        )
        self.assertTrue(all(region["alignment"] == 8 for region in audit_memory.REGIONS))
        self.assertEqual(
            [status["name"] for status in audit_memory.STATUSES],
            [
                "ok",
                "unknown-region",
                "reserved-region",
                "device-region",
                "read-denied",
                "write-denied",
                "width-denied",
                "out-of-bounds",
                "misaligned",
                "budget-exceeded",
            ],
        )

    def test_all_manifest_and_effect_mutations_are_rejected(self) -> None:
        mutations = audit_memory.manifest_mutations(self.manifest)
        names = {mutation.name for mutation in mutations}
        self.assertEqual(
            names,
            {
                "profile-version",
                "region-base",
                "region-permission",
                "region-width",
                "region-kind",
                "status-code",
                "guard-order",
                "volatile-policy",
                "checked-result-abi",
                "memory-op-identity",
                "direct-effect",
                "transitive-effect",
                "action-dependency",
            },
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.name):
                assert mutation.manifest is not None
                with self.assertRaises(Core0Error):
                    audit_memory.validate_memory_suite_manifest(
                        mutation.manifest, require_closed_suite=False
                    )

    def test_scalar_function_cannot_hide_an_action_site(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["scalar_functions"] = [
            {"source": f"{BASE}.forgedPure", "body": "(action.store8 ...)"}
        ]
        with self.assertRaisesRegex(Core0Error, "contains an Action/effect"):
            audit_memory.validate_memory_suite_manifest(
                manifest, require_closed_suite=False
            )

    def test_action_fold_callback_and_iteration_manifest_are_transitive(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        callback = f"{BASE}.foldStep"
        fold = f"{BASE}.foldWrite"
        manifest["action_functions"].extend(  # type: ignore[union-attr]
            [
                {
                    "source": callback,
                    "llvm": "core0_action_4",
                    "signature": {
                        "args": ["u32", "u32", "u64", "u64", "u64", "u64", "u64"]
                    },
                    "scalar_dependencies": [],
                    "action_dependencies": [],
                    "direct_effects": ["checked-access", "fixed-ram-write"],
                    "transitive_effects": ["checked-access", "fixed-ram-write"],
                    "body": "(action.store8 (lit u8 1) (var 2 u64) (lit u8 90) (status %7) (action.done (var 7 u8) (var 2 u64)))",
                    "noinline": True,
                },
                {
                    "source": fold,
                    "llvm": "core0_action_5",
                    "signature": {"args": ["u32", "u64"]},
                    "scalar_dependencies": [],
                    "action_dependencies": [callback],
                    "direct_effects": [],
                    "transitive_effects": ["checked-access", "fixed-ram-write"],
                    "body": (
                        f"(action.bounded-fold-u64 budget=16 callback={callback} "
                        "count=(var 0 u32) initial=(var 1 u64) "
                        "ctx=[(lit u64 0) (lit u64 0) (lit u64 0) (lit u64 0)] "
                        "(status %2) (value %3) (action.done (var 2 u8) (var 3 u64)))"
                    ),
                    "noinline": True,
                },
            ]
        )
        manifest["roots"].append(  # type: ignore[union-attr]
            {
                "root_id": 3,
                "source": fold,
                "llvm": "core0_action_5",
                "signature": {"args": ["u32", "u64"]},
            }
        )
        manifest["used_memory_ops"].append(  # type: ignore[union-attr]
            copy.deepcopy(audit_memory.MEMORY_OPS["ram.write8"])
        )
        manifest["used_memory_ops"] = sorted(  # type: ignore[index]
            manifest["used_memory_ops"], key=lambda row: row["stable_id"]  # type: ignore[arg-type,index]
        )
        manifest["action_iterations"] = [
            audit_memory._expected_action_iteration(16, callback)
        ]
        result = audit_memory.validate_effect_closure(manifest)
        self.assertEqual(result["action_iteration_count"], 1)
        self.assertEqual(
            result["effect_closure"][fold],
            ["checked-access", "fixed-ram-write"],
        )

        forged = copy.deepcopy(manifest)
        forged["action_iterations"][0]["static_budget"] = 15  # type: ignore[index]
        with self.assertRaisesRegex(Core0Error, "iteration manifest differs"):
            audit_memory.validate_effect_closure(forged)


class Gate5CheckedIRTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()
        self.ir = valid_ir_fixture()

    def test_checked_result_is_direct_aggregate_without_sret(self) -> None:
        result = audit_memory.validate_checked_result_ir(self.manifest, self.ir)
        self.assertEqual(result["action_function_count"], 4)
        self.assertEqual(result["aggregate_call_count"], 2)
        self.assertFalse(result["sret"])
        self.assertTrue(result["direct_calls"])

    def test_unsafe_status_extension_is_rejected(self) -> None:
        mutated = self.ir.replace(
            "%status.word = zext i8 %arg0 to i64",
            "%status.word = sext i8 %arg0 to i64",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "zero-extend status"):
            audit_memory.validate_checked_result_ir(self.manifest, mutated)

    def test_sret_and_indirect_action_calls_are_rejected(self) -> None:
        sret = self.ir.replace(
            "i8 zeroext %arg0, i64 %arg1) nounwind noinline",
            "ptr sret({ i64, i64 }) %out, i8 zeroext %arg0, i64 %arg1) nounwind noinline",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "must not use sret"):
            audit_memory.validate_checked_result_ir(self.manifest, sret)
        indirect = self.ir.replace(
            "call { i64, i64 } @core0_action_1",
            "call { i64, i64 } %core0_action_1",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "indirect Action call"):
            audit_memory.validate_checked_result_ir(self.manifest, indirect)


class Gate5GuardDominanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = closed_manifest_fixture()
        self.ir = valid_ir_fixture()

    def test_valid_load_and_store_have_full_guard_chains(self) -> None:
        result = audit_memory.validate_memory_pre_ir(self.manifest, self.ir)
        self.assertEqual(result["access_count"], 2)
        self.assertEqual(result["loads"], 1)
        self.assertEqual(result["stores"], 1)
        self.assertTrue(result["volatile_policy"])
        self.assertTrue(
            all(not record["denied_path_access"] for record in result["accesses"])
        )
        self.assertEqual(result["source_memory_site_count"], 2)
        self.assertEqual(
            result["direct_source_bindings"],
            {"region": 2, "offset": 2, "store_value": 1, "range_length": 0},
        )

    def test_normalized_store_value_and_offset_selection_mutants_are_rejected(self) -> None:
        mutations = {mutation.name: mutation for mutation in audit_memory.ir_mutations(self.ir)}
        for name in (
            "wrong-source-store-value",
            "wrong-source-offset-selection",
        ):
            with self.subTest(mutation=name):
                mutation = mutations[name]
                assert mutation.ir is not None
                with self.assertRaisesRegex(Core0Error, "differs from normalized source"):
                    audit_memory.validate_memory_pre_ir(self.manifest, mutation.ir)

    def test_production_dispatch_and_dynamic_range_preflight_are_accepted(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["action_functions"].append(  # type: ignore[union-attr]
            {
                "source": f"{BASE}.readRange",
                "llvm": "core0_action_range",
                "signature": {"args": ["u8", "u64", "u64"]},
                "body": "(action.check-read-range (var 0 u8) (var 1 u64) (var 2 u64) (status %3) (action.done (var 3 u8) (lit u64 0)))",
            }
        )
        result = audit_memory.validate_memory_pre_ir(
            manifest,
            self.ir + production_range_function("core0_action_range"),
        )
        self.assertEqual(result["access_count"], 2)
        self.assertEqual(result["range_check_count"], 1)
        self.assertEqual(result["read_ranges"], 1)
        self.assertEqual(result["write_ranges"], 0)
        self.assertFalse(result["range_checks"][0]["denied_path_access"])

    def test_production_dispatch_metadata_and_range_guard_mutations_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["action_functions"].append(  # type: ignore[union-attr]
            {
                "source": f"{BASE}.readRange",
                "llvm": "core0_action_range",
                "signature": {"args": ["u8", "u64", "u64"]},
                "body": "(action.check-read-range (var 0 u8) (var 1 u64) (var 2 u64) (status %3) (action.done (var 3 u8) (lit u64 0)))",
            }
        )
        production = production_range_function("core0_action_range")
        wrong_permission = production.replace(
            "%mem.0.permission-ok.11 = phi i1 [ 1, %mem.0.region.1.2 ], [ 1, %mem.0.region.2.4 ]",
            "%mem.0.permission-ok.11 = phi i1 [ 1, %mem.0.region.1.2 ], [ 0, %mem.0.region.2.4 ]",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "permission-ok metadata phi"):
            audit_memory.validate_memory_pre_ir(manifest, self.ir + wrong_permission)
        unsafe_length = production.replace(
            "%mem.0.length-ok.15 = icmp ule i64 %arg2, %mem.0.length.9",
            "%mem.0.length-ok.15 = icmp ule i64 %arg1, %mem.0.length.9",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "validate length before subtraction"):
            audit_memory.validate_memory_pre_ir(manifest, self.ir + unsafe_length)

        combined_ir = self.ir + production
        range_mutations = {
            mutation.name: mutation
            for mutation in audit_memory.ir_mutations(combined_ir)
            if mutation.name.startswith("range-")
        }
        self.assertEqual(
            set(range_mutations),
            {
                "range-wrong-length-guard",
                "range-wrong-bounds-comparison",
                "range-subtraction-replaced-by-add",
                "range-wrap-prone-offset-plus-length",
                "range-address-construction",
            },
        )
        for name, mutation in range_mutations.items():
            with self.subTest(range_mutation=name):
                assert mutation.ir is not None
                with self.assertRaises(Core0Error):
                    audit_memory.validate_memory_pre_ir(manifest, mutation.ir)

    def test_production_region_selection_route_and_class_control_are_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["action_functions"].append(  # type: ignore[union-attr]
            {
                "source": f"{BASE}.readRange",
                "llvm": "core0_action_range",
                "signature": {"args": ["u8", "u64", "u64"]},
                "body": "(action.check-read-range (var 0 u8) (var 1 u64) (var 2 u64) (status %3) (action.done (var 3 u8) (lit u64 0)))",
            }
        )
        production = production_range_function("core0_action_range")
        wrong_region = production.replace("icmp eq i8 %arg0,", "icmp eq i8 1,")
        self.assertEqual(wrong_region.count("icmp eq i8 1,"), 8)
        with self.assertRaisesRegex(Core0Error, "differs from normalized source"):
            audit_memory.validate_memory_pre_ir(manifest, self.ir + wrong_region)

        wrong_route = production.replace(
            "br i1 %mem.0.region-known.0, label %mem.0.region.1.2, label %mem.0.lookup.next.3",
            "br i1 %mem.0.region-known.0, label %mem.0.region.2.4, label %mem.0.lookup.next.3",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "metadata phi differs"):
            audit_memory.validate_memory_pre_ir(manifest, self.ir + wrong_route)

        inverted_class = production.replace(
            "br i1 %mem.0.class-is-reserved.14, label %mem.0.reserved.20, label %mem.0.device.21",
            "br i1 %mem.0.class-is-reserved.14, label %mem.0.device.21, label %mem.0.reserved.20",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "reserved control edge"):
            audit_memory.validate_memory_pre_ir(manifest, self.ir + inverted_class)

    def test_nonvolatile_access_is_rejected_under_v04_policy(self) -> None:
        mutated = self.ir.replace("load volatile i64", "load i64", 1)
        with self.assertRaisesRegex(Core0Error, "not exactly volatile"):
            audit_memory.validate_memory_pre_ir(self.manifest, mutated)
        # The knob is explicit for unit-level policy testing; the manifest pins true.
        nonvolatile_manifest = copy.deepcopy(self.manifest)
        nonvolatile_manifest["action_functions"] = [
            function
            for function in nonvolatile_manifest["action_functions"]  # type: ignore[index]
            if function["source"] in {STATUS, READER}
        ]
        nonvolatile_manifest["roots"] = [nonvolatile_manifest["roots"][0]]  # type: ignore[index]
        nonvolatile_manifest["used_memory_ops"] = [
            copy.deepcopy(audit_memory.MEMORY_OPS["ram.read64"])
        ]
        reduced_ir = mutated.split(
            "define { i64, i64 } @core0_action_2", 1
        )[0]
        reduced_ir = reduced_ir.replace("core0_action_1", "core0_action_1")
        result = audit_memory.validate_memory_pre_ir(
            nonvolatile_manifest, reduced_ir, require_volatile=False
        )
        self.assertFalse(result["volatile_policy"])

    def test_width_must_be_validated_before_subtraction(self) -> None:
        mutated = self.ir.replace(
            "mem.0.width:\n  %mem.0.length-ok = icmp uge i64 4096, 8",
            "mem.0.width:\n  %mem.0.remaining = sub i64 4096, 8\n"
            "  %mem.0.length-ok = icmp uge i64 4096, 8",
            1,
        ).replace(
            "mem.0.remaining-block:\n  %mem.0.remaining = sub i64 4096, 8",
            "mem.0.remaining-block:",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "before proving length"):
            audit_memory.validate_memory_pre_ir(self.manifest, mutated)

    def test_wrong_bounds_and_alignment_are_rejected(self) -> None:
        bounds = self.ir.replace(
            "%mem.0.offset-ok = icmp ule i64 %arg1, %mem.0.remaining",
            "%mem.0.offset-ok = icmp uge i64 %arg1, %mem.0.remaining",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "offset-within-remaining"):
            audit_memory.validate_memory_pre_ir(self.manifest, bounds)
        alignment = self.ir.replace(
            "%mem.0.alignment-mask = and i64 %arg1, 7",
            "%mem.0.alignment-mask = and i64 %arg1, 3",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "alignment mask"):
            audit_memory.validate_memory_pre_ir(self.manifest, alignment)

    def test_denied_edges_cannot_reach_the_access(self) -> None:
        bypass = self.ir.replace(
            "br i1 %mem.0.permission-ok, label %mem.0.permission, label %mem.0.read-denied",
            "br i1 %mem.0.permission-ok, label %mem.0.permission, label %mem.0.access",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "denied edge reaches memory access"):
            audit_memory.validate_memory_pre_ir(self.manifest, bypass)

    def test_reserved_and_device_ids_are_not_ordinary_ram(self) -> None:
        class_bypass = self.ir.replace(
            "%mem.0.class.eq.4 = icmp eq i8 %arg0, 4",
            "%mem.0.class.eq.4 = icmp eq i8 %arg0, 128",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "class-ok region-ID set"):
            audit_memory.validate_memory_pre_ir(self.manifest, class_bypass)

    def test_offset_plus_width_and_poison_flags_are_rejected(self) -> None:
        wrap = self.ir.replace(
            "%mem.0.remaining = sub i64 4096, 8",
            "%mem.0.wrap = add i64 %arg1, 8\n  %mem.0.remaining = sub i64 4096, 8",
            1,
        )
        with self.assertRaisesRegex(Core0Error, "wrap-prone offset-plus-width"):
            audit_memory.validate_memory_pre_ir(self.manifest, wrap)
        flagged = self.ir.replace(
            "%mem.0.address = add i64", "%mem.0.address = add nuw i64", 1
        )
        with self.assertRaisesRegex(Core0Error, "forbidden LLVM flag"):
            audit_memory.validate_memory_pre_ir(self.manifest, flagged)

    def test_complete_applicable_ir_mutation_matrix_is_detected(self) -> None:
        mutations = audit_memory.ir_mutations(self.ir)
        names = {mutation.name for mutation in mutations}
        self.assertEqual(
            names,
            {
                "nonvolatile-access",
                "wrong-access-width",
                "wrong-access-alignment",
                "unaudited-extra-access",
                "wrong-source-store-value",
                "wrong-source-offset-selection",
                "wrong-length-guard",
                "wrong-bounds-comparison",
                "wrong-alignment-mask",
                "subtraction-replaced-by-add",
                "wrap-prone-offset-plus-width",
                "permission-bypass",
                "denied-path-access",
                "guard-order",
                "forbidden-nuw",
                "status-sign-extension",
                "checked-result-word-order",
                "argument-abi",
                "sret-result",
                "indirect-action-call",
                "wrong-direct-callee",
            },
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.name):
                assert mutation.ir is not None
                with self.assertRaises(Core0Error):
                    audit_memory.validate_memory_pre_ir(self.manifest, mutation.ir)

    def test_combined_mutation_driver_classifies_every_rejection(self) -> None:
        records = audit_memory.audit_mutation_matrix(
            self.manifest, self.ir, require_closed_suite=False
        )
        expected = len(audit_memory.manifest_mutations(self.manifest)) + len(
            audit_memory.ir_mutations(self.ir)
        )
        self.assertEqual(len(records), expected)
        self.assertTrue(all(record["diagnostic"] for record in records))


if __name__ == "__main__":
    unittest.main()
