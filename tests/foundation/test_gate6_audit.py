#!/usr/bin/env python3
"""Focused positive and mutation tests for the independent Gate 6 audit."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_device  # noqa: E402
from core0_common import Core0Error  # noqa: E402


IDENTITIES = {
    "suite_id": "4c454d4d41363036",
    "source_seed": "534f555243453036",
    "runtime_seed": "52554e54494d4536",
}


def _memory_contract() -> dict[str, object]:
    statuses = [
        {"code": code, "name": name}
        for code, name in enumerate(
            (
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
            )
        )
    ]
    return {
        "byte_order": "little-endian",
        "guard_order": [
            "lookup", "class", "permission", "width", "bounds", "alignment"
        ],
        "successful_access_volatile": True,
        "regions": [
            {
                "id": 128,
                "name": "uart16550",
                "base": audit_device.UART_BASE,
                "length": audit_device.UART_SPAN,
                "alignment": 8,
                "widths": [],
                "read": False,
                "write": False,
                "kind": "device",
                "purpose": "device MMIO; excluded from ordinary RAM operations",
                "interval_valid": True,
            },
            {
                "id": 129,
                "name": "sifive-test",
                "base": audit_device.FINISHER_BASE,
                "length": audit_device.FINISHER_SPAN,
                "alignment": 8,
                "widths": [],
                "read": False,
                "write": False,
                "kind": "device",
                "purpose": "VM termination MMIO; excluded from ordinary RAM operations",
                "interval_valid": True,
            },
        ],
        "statuses": statuses,
    }


def _direct_body_tokens(source: str) -> list[str]:
    base = "Lemma.Examples.Foundation.Device"
    exact = {
        f"{base}.Support.transmitPollStep": [
            "(action.uart-read-status (status %0) (value %1))",
            "(action.uart-write-byte (var 0 u8) (status %2))",
        ],
        f"{base}.Support.receivePollStep": [
            "(action.uart-read-status (status %0) (value %1))",
            "(action.uart-read-byte (status %2) (value %3))",
        ],
        f"{base}.Support.receiveIntoStep": [
            "(action.store8 (lit u8 1) (lit u64 0) (lit u8 0) (status %0))"
        ],
        f"{base}.Support.responseStep": [
            "(action.store8 (lit u8 1) (lit u64 0) (lit u8 0) (status %0))"
        ],
        f"{base}.dispatchAdd64": [
            "(action.load64 (lit u8 1) (lit u64 0) (status %0) (value %1))"
        ],
        f"{base}.dispatchXor64": [
            "(action.load64 (lit u8 1) (lit u64 0) (status %0) (value %1))"
        ],
        f"{base}.dispatchTxStress": [
            "(action.load32 (lit u8 1) (lit u64 0) (status %0) (value %1))"
        ],
        f"{base}.handleRequest": [
            "(action.load8 (lit u8 1) (lit u64 0) (status %0) (value %1))"
        ],
        f"{base}.Support.drainPollStep": [
            "(action.uart-read-status (status %0) (value %1))"
        ],
        audit_device.ROOT_SOURCE: ["(action.uart-enable-reset-fifo (status %0))"],
    }
    return exact.get(source, [])


def _action_body(source: str, dependencies: tuple[str, ...]) -> str:
    if source == audit_device.BRANCH_SOURCE:
        send_response = "Lemma.Examples.Foundation.Device.Support.sendResponse"
        scratch = "(call Lemma.Core0.Memory.RegionId.scratch u8 [])"

        def readback(status: int, value: int) -> str:
            return (
                f"(action.load8 {scratch} (lit u64 64) "
                f"(status %{status}) (value %{value}) "
                f"(action.call {send_response} [(lit u8 0) (var 0 u64) "
                f"(bin add u64 (bin shl u64 (var {value} u64) "
                "(lit u64 8)) (var 2 u64))]))"
            )

        return (
            f"(action.load8 {scratch} "
            "(lit u64 16) (status %1) (value %2) "
            "(action.ite (cmp eq u8 (var 1 u8) (lit u8 0)) "
            f"(action.store8 {scratch} (lit u64 64) (lit u8 60) (status %3) "
            "(action.ite (cmp eq u64 (var 2 u64) (lit u64 0)) "
            f"(action.store8 {scratch} (lit u64 64) (lit u8 90) (status %4) "
            f"{readback(5, 6)}) "
            "(action.ite (cmp eq u64 (var 2 u64) (lit u64 1)) "
            f"(action.bind (action.call {audit_device.SEND_BYTE_SOURCE} "
            f"[(lit u8 165)]) (status %7) (value %8) {readback(9, 10)}) "
            "(action.done (lit u8 14) (lit u64 0))))) "
            "(action.done (var 1 u8) (lit u64 0))))"
        )
    pieces = [f"(action.call {dependency} [])" for dependency in dependencies]
    pieces.extend(_direct_body_tokens(source))
    if not pieces:
        return "(action.done (lit u8 0) (lit u64 0))"
    return "(action.bind " + " ".join(pieces) + ")"


def closed_manifest_fixture() -> dict[str, object]:
    functions: list[dict[str, object]] = []
    for index, contract in enumerate(audit_device.ACTION_CONTRACTS):
        source, args, dependencies, direct, transitive = contract
        functions.append(
            {
                "source": source,
                "llvm": f"core0_action_{index}",
                "signature": {"args": list(args)},
                "scalar_dependencies": [],
                "action_dependencies": list(dependencies),
                "direct_effects": list(direct),
                "transitive_effects": list(transitive),
                "body": _action_body(source, dependencies),
                "noinline": True,
            }
        )
    iterations = []
    for budget, callback in audit_device.ITERATION_CONTRACTS:
        iterations.append(
            {
                "stable_id": "action.u64.bounded-fold",
                "source_identity": "Lemma.Core0.Memory.Action.boundedFoldU64",
                "static_budget": budget,
                "callback": callback,
                "maximum_budget": 1000000,
                "counter": {"type": "u32", "order": "ascending-zero-based"},
                "accumulator": "u64",
                "contexts": 4,
                "outcome": "checked-result-v1",
                "exhaustion": {"status": 9, "value": "initial", "callbacks": 0},
            }
        )
    return {
        "schema_version": 1,
        "artifact_category": audit_device.ARTIFACT_CATEGORY,
        "contract_version": audit_device.CONTRACT_VERSION,
        "test_abi": audit_device.TEST_ABI,
        **IDENTITIES,
        "checked_result": copy.deepcopy(audit_device.CHECKED_RESULT),
        "memory_contract": _memory_contract(),
        "device_contract": copy.deepcopy(audit_device.DEVICE_CONTRACT),
        "roots": [
            {
                "root_id": 1,
                "source": audit_device.ROOT_SOURCE,
                "llvm": audit_device.ROOT_SYMBOL,
                "signature": {"args": []},
            }
        ],
        "scalar_functions": [],
        "action_functions": functions,
        "used_primitives": [],
        "used_memory_ops": [
            copy.deepcopy(operation)
            for operation in audit_device.MEMORY_OPS.values()
        ],
        "used_device_ops": [
            copy.deepcopy(operation)
            for operation in audit_device.DEVICE_OPS.values()
        ],
        "action_iterations": iterations,
        "machine_primitives": copy.deepcopy(audit_device.MACHINE_PRIMITIVES),
    }


def abi_fixture() -> dict[str, object]:
    return {**copy.deepcopy(audit_device.ABI_FIXED), **IDENTITIES}


def normalized_fixture(manifest: dict[str, object]) -> str:
    lines = [f"contract={audit_device.CONTRACT_VERSION}"]
    lines.append(
        f'root=1;source={audit_device.ROOT_SOURCE};signature={{"args":[]}}'
    )
    for function in manifest["action_functions"]:
        assert isinstance(function, dict)
        direct = "[" + ",".join(function["direct_effects"]) + "]"
        transitive = "[" + ",".join(function["transitive_effects"]) + "]"
        lines.append(
            f"action={function['source']};direct={direct};transitive={transitive};"
            f"body={function['body']}"
        )
    lines.extend(f"device-op={stable_id}" for stable_id in audit_device.DEVICE_OPS)
    return "\n".join(lines) + "\n"


def _access_lines(*, optimized: bool) -> list[str]:
    accesses = (
        ("%uart.lsr.byte.0 = load volatile i8", audit_device.UART_LSR, 1),
        ("store volatile i8 %byte", audit_device.UART_THR, 1),
        ("%uart.lsr.byte.2 = load volatile i8", audit_device.UART_LSR, 1),
        ("%uart.rbr.byte.3 = load volatile i8", audit_device.UART_RBR, 1),
        ("%uart.lsr.byte.4 = load volatile i8", audit_device.UART_LSR, 1),
        ("store volatile i8 7", audit_device.UART_FCR, 1),
    )
    result = []
    for prefix, address, emitted_alignment in accesses:
        alignment = (address & -address) if optimized else emitted_alignment
        result.append(
            f"  {prefix}, ptr inttoptr (i64 {address} to ptr), align {alignment}"
        )
    return result


def ir_fixture(*, markers: bool, optimized: bool = False) -> str:
    lines = [
        "declare void @core0_io_fence() nounwind",
        "",
        "define void @core0_action_0(i8 %byte) nounwind noinline {",
        "entry:",
    ]
    for site, (operation, access) in enumerate(
        zip(audit_device.LOW_LEVEL_SITE_SEQUENCE, _access_lines(optimized=optimized))
    ):
        if markers:
            lines.append(f"  ; lemma.uart-site={site};op={operation}")
        lines.extend(("  call void @core0_io_fence()", access, "  call void @core0_io_fence()"))
    lines.extend(
        (
            "  ret void",
            "}",
            "",
            "define { i64, i64 } @core0_action_13(i64 %arg0) nounwind noinline {",
            "entry:",
            f"  %branch.value = load volatile i8, ptr inttoptr (i64 {0x80801010} to ptr), align 1",
            "  %mem.0.value.0 = zext i8 %branch.value to i64",
            "  store volatile i8 60, ptr inttoptr "
            f"(i64 {audit_device.BRANCH_MARKER_ADDRESS} to ptr), align 1",
        )
    )
    if optimized:
        lines.extend(
            (
                "  switch i8 %branch.value, label %branch.default [",
                "    i8 0, label %branch.zero",
                "    i8 1, label %branch.one",
                "  ]",
            )
        )
    else:
        lines.extend(
            (
                "  %cmp29 = icmp eq i8 %branch.value, 0",
                "  br i1 %cmp29, label %branch.zero, label %branch.check-one",
                "branch.check-one:",
                "  %cmp64 = icmp eq i8 %branch.value, 1",
                "  br i1 %cmp64, label %branch.one, label %branch.default",
            )
        )
    marker_alignment = 64 if optimized else 1
    send_value = -91 if optimized else 165
    lines.extend(
        (
            "branch.zero:",
            "  store volatile i8 90, ptr inttoptr "
            f"(i64 {audit_device.BRANCH_MARKER_ADDRESS} to ptr), align {marker_alignment}",
            "  br label %branch.zero.readback",
            "branch.zero.readback:",
            "  %false.loaded = load volatile i8, ptr inttoptr "
            f"(i64 {audit_device.BRANCH_MARKER_ADDRESS} to ptr), align {marker_alignment}",
            "  %false.wide = zext i8 %false.loaded to i64",
            "  br label %branch.zero.response",
            "branch.zero.response:",
            "  %false.value = phi i64 [ %false.wide, %branch.zero.readback ]",
            "  %false.shift = shl i64 %false.value, 8",
            "  %false.encoded = add i64 %false.shift, %mem.0.value.0",
            "  %false.response = call { i64, i64 } "
            "@core0_action_10(i8 zeroext 0, i64 %arg0, i64 %false.encoded)",
            "  br label %branch.merge",
            "branch.one:",
            "  %branch.send = call { i64, i64 } "
            f"@core0_action_1(i8 zeroext {send_value})",
            "  br label %branch.one.readback",
            "branch.one.readback:",
            "  %true.loaded = load volatile i8, ptr inttoptr "
            f"(i64 {audit_device.BRANCH_MARKER_ADDRESS} to ptr), align {marker_alignment}",
            "  %true.wide = zext i8 %true.loaded to i64",
            "  br label %branch.one.response",
            "branch.one.response:",
            "  %true.value = phi i64 [ %true.wide, %branch.one.readback ]",
            "  %true.shift = shl i64 %true.value, 8",
            "  %true.encoded = add i64 %true.shift, %mem.0.value.0",
            "  %true.response = call { i64, i64 } "
            "@core0_action_10(i8 zeroext 0, i64 %arg0, i64 %true.encoded)",
            "  br label %branch.merge",
            "branch.default:",
            "  br label %branch.merge",
            "branch.merge:",
            "  ret { i64, i64 } zeroinitializer",
            "}",
            "",
        )
    )
    return "\n".join(lines)


class DeviceManifestAuditTests(unittest.TestCase):
    def test_closed_manifest_abi_and_normalized_companion(self) -> None:
        manifest = closed_manifest_fixture()
        report = audit_device.validate_device_suite_manifest(
            manifest, normalized=normalized_fixture(manifest)
        )
        self.assertEqual(report["action_functions"], 22)
        self.assertEqual(report["source_device_operations"], 6)
        self.assertEqual(report["device_operations"], 4)
        branch = report["branch_effects"]
        self.assertEqual(branch["source_function"], audit_device.BRANCH_SOURCE)
        self.assertTrue(branch["separate_subtrees"])
        self.assertEqual(branch["readback"], audit_device.BRANCH_READBACK)
        self.assertTrue(branch["common_sentinel_before_selection"])
        self.assertTrue(branch["branch_local_readbacks"])
        self.assertTrue(branch["readbacks_encoded"])
        abi = audit_device.validate_device_test_abi(abi_fixture(), manifest)
        self.assertEqual(abi["requests_per_session"], 2)

    def test_source_readbacks_require_sentinel_offset_and_observed_value(self) -> None:
        body = _action_body(
            audit_device.BRANCH_SOURCE,
            (audit_device.SEND_BYTE_SOURCE, "Lemma.Examples.Foundation.Device.Support.sendResponse"),
        )
        mutations = {
            "wrong-sentinel": body.replace("(lit u8 60)", "(lit u8 61)", 1),
            "wrong-readback-offset": body.replace(
                "(lit u64 64) (status %5)", "(lit u64 63) (status %5)", 1
            ),
            "constant-false-response": body.replace("(var 6 u64)", "(lit u64 90)", 1),
            "constant-true-response": body.replace("(var 10 u64)", "(lit u64 60)", 1),
            "wrong-encoding-shift": body.replace("(lit u64 8)", "(lit u64 7)", 1),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name), self.assertRaises(Core0Error):
                audit_device.validate_branch_source_placement(mutated)

    def test_exact_device_catalog_rejects_duplicate_unknown_and_wrong_address(self) -> None:
        for mutate in ("duplicate", "unknown", "wrong-address"):
            with self.subTest(mutate=mutate):
                manifest = closed_manifest_fixture()
                operations = manifest["used_device_ops"]
                assert isinstance(operations, list)
                if mutate == "duplicate":
                    operations.append(copy.deepcopy(operations[0]))
                elif mutate == "unknown":
                    assert isinstance(operations[0], dict)
                    operations[0]["stable_id"] = "uart.read-any-address"
                else:
                    assert isinstance(operations[0], dict)
                    operations[0]["address"] = "0x0000000010000004"
                with self.assertRaises(Core0Error):
                    audit_device.validate_device_suite_manifest(manifest)

    def test_rejects_stale_direct_transitive_and_dependency_metadata(self) -> None:
        for field in ("direct_effects", "transitive_effects", "action_dependencies"):
            with self.subTest(field=field):
                manifest = closed_manifest_fixture()
                functions = manifest["action_functions"]
                assert isinstance(functions, list) and isinstance(functions[0], dict)
                target = 1 if field == "action_dependencies" else 0
                assert isinstance(functions[target], dict)
                functions[target][field] = []
                with self.assertRaises(Core0Error):
                    audit_device.validate_device_suite_manifest(manifest)

    def test_rejects_generic_or_interrupt_device_source(self) -> None:
        for token in ("(action.mmio-read 268435456)", "(action.uart-read-any)", "action.wfi"):
            with self.subTest(token=token):
                manifest = closed_manifest_fixture()
                functions = manifest["action_functions"]
                assert isinstance(functions, list) and isinstance(functions[0], dict)
                functions[0]["body"] = str(functions[0]["body"]) + token
                with self.assertRaises(Core0Error):
                    audit_device.validate_device_suite_manifest(manifest)

    def test_rejects_changed_poll_budget_and_public_internal_status(self) -> None:
        manifest = closed_manifest_fixture()
        iterations = manifest["action_iterations"]
        assert isinstance(iterations, list) and isinstance(iterations[1], dict)
        iterations[1]["maximum_budget"] = 999999
        with self.assertRaises(Core0Error):
            audit_device.validate_device_suite_manifest(manifest)

        abi = abi_fixture()
        statuses = abi["statuses"]
        assert isinstance(statuses, list) and isinstance(statuses[1], dict)
        statuses[1]["public"] = True
        with self.assertRaises(Core0Error):
            audit_device.validate_device_test_abi(abi, closed_manifest_fixture())


class DeviceIRAuditTests(unittest.TestCase):
    def test_pre_and_both_optimized_profiles_pass(self) -> None:
        manifest = closed_manifest_fixture()
        pre = ir_fixture(markers=True)
        self.assertEqual(
            (pre_report := audit_device.validate_device_pre_ir(manifest, pre))["site_ids"],
            list(range(6)),
        )
        self.assertTrue(pre_report["branch_effects"]["exclusive_reachability"])
        self.assertTrue(pre_report["branch_effects"]["sentinel_dominates_selection"])
        self.assertTrue(pre_report["branch_effects"]["readbacks_encoded"])
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                post = ir_fixture(markers=False, optimized=optimized)
                report = audit_device.validate_device_post_ir(manifest, post)
                self.assertEqual(report["accesses"], 6)
                self.assertEqual(
                    report["branch_effects"]["dispatch"],
                    "switch" if optimized else "conditional-branches",
                )

    def test_ir_readbacks_reject_stale_initialization_address_and_encoding(self) -> None:
        for optimized in (False, True):
            control = ir_fixture(markers=not optimized, optimized=optimized)
            mutations = {
                "wrong-sentinel": control.replace("store volatile i8 60", "store volatile i8 61", 1),
                "wrong-readback-address": control.replace(
                    "%false.loaded = load volatile i8, ptr inttoptr "
                    f"(i64 {audit_device.BRANCH_MARKER_ADDRESS}",
                    "%false.loaded = load volatile i8, ptr inttoptr "
                    f"(i64 {audit_device.BRANCH_MARKER_ADDRESS + 1}", 1
                ),
                "wrong-shift": control.replace("shl i64 %false.value, 8", "shl i64 %false.value, 7", 1),
                "constant-response": control.replace("i64 %false.encoded)", "i64 23040)", 1),
                "missing-selector": control.replace("add i64 %true.shift, %mem.0.value.0", "add i64 %true.shift, 0", 1),
            }
            for name, mutated in mutations.items():
                with self.subTest(optimized=optimized, name=name), self.assertRaises(Core0Error):
                    audit_device.validate_branch_ir_placement(mutated, optimized=optimized)

    def test_required_manifest_and_ir_mutation_matrix(self) -> None:
        manifest = closed_manifest_fixture()
        records = audit_device.audit_mutation_matrix(
            manifest,
            ir_fixture(markers=True),
            ir_fixture(markers=False),
        )
        names = {record["name"] for record in records}
        required = {
            "wrong-manifest-device-address",
            "wrong-device-address",
            "wrong-device-width",
            "nonvolatile-device-access",
            "missing-before-fence",
            "reordered-before-fence",
            "duplicate-site-id",
            "duplicate-device-op",
            "stale-transitive-effects",
            "optimized-wrong-device-address",
            "optimized-nonvolatile-device-access",
            "optimized-missing-before-fence",
            "optimized-invalid-device-alignment",
            "duplicate-physical-device-operation",
            "optimized-duplicate-physical-device-operation",
            "misplaced-branch-effects",
            "misplaced-pre-branch-effects",
            "misplaced-post-branch-effects",
        }
        self.assertEqual(names, required)
        self.assertEqual(len(records), len(required))
        self.assertTrue(all(record["diagnostic"] for record in records))

    def test_rejects_unmarked_and_generic_uart_access(self) -> None:
        pre = ir_fixture(markers=True)
        extra = (
            "  %generic = load volatile i8, ptr inttoptr "
            f"(i64 {audit_device.UART_BASE + 1} to ptr), align 1\n"
        )
        mutated = pre.replace("  ret void\n", extra + "  ret void\n")
        with self.assertRaises(Core0Error):
            audit_device.validate_device_pre_ir(mutated)

        pointer = (
            f"  %generic = inttoptr i64 {audit_device.UART_BASE + 1} to ptr\n"
        )
        mutated = pre.replace("  ret void\n", pointer + "  ret void\n")
        with self.assertRaises(Core0Error):
            audit_device.validate_device_pre_ir(mutated)

    def test_pre_ir_never_accepts_strengthened_alignment(self) -> None:
        pre = ir_fixture(markers=True).replace(
            f"i64 {audit_device.UART_THR} to ptr), align 1",
            f"i64 {audit_device.UART_THR} to ptr), align {audit_device.UART_THR}",
            1,
        )
        with self.assertRaises(Core0Error):
            audit_device.validate_device_pre_ir(pre)


class DeviceBoundaryAuditTests(unittest.TestCase):
    def test_real_harness_is_entry_and_finisher_glue_only(self) -> None:
        source = (ROOT / "Lemma/Machine/DeviceHarness.lean").read_text(encoding="utf-8")
        report = audit_device.validate_device_harness_source(source)
        self.assertEqual(report, {"action_calls": 1, "finisher_stores": 2, "uart_accesses": 0})
        for injection in (
            "\nprivate def uartPoll := .load .i8 (int64 268435456) 1 true\n",
            "\nprivate def formatResponse := readyByte\n",
            "\nprivate def secondRoot := .abiCall none .checkedResult none root #[]\n",
        ):
            with self.subTest(injection=injection):
                with self.assertRaises(Core0Error):
                    audit_device.validate_device_harness_source(source + injection)

    def test_pinned_dtb_uart_node_and_toolchain(self) -> None:
        dts = """
/dts-v1/;
/ {
  soc {
    serial@10000000 {
      interrupts = <0x0a>;
      clock-frequency = "", "8@";
      reg = <0x00 0x10000000 0x00 0x100>;
      compatible = "ns16550a";
    };
  };
};
"""
        audit_device.validate_platform_evidence(audit_device.PINNED_DTB_SHA256, dts)
        for old, new in (
            ("<0x0a>", "<0x0b>"),
            ('"", "8@"', "<0x384001>"),
            ("0x10000000", "0x10000100"),
            ('"ns16550a"', '"other-uart"'),
        ):
            with self.subTest(old=old):
                with self.assertRaises(Core0Error):
                    audit_device.validate_platform_evidence(
                        audit_device.PINNED_DTB_SHA256, dts.replace(old, new, 1)
                    )
        with self.assertRaises(Core0Error):
            audit_device.validate_platform_evidence("0" * 64, dts)

        lock: dict[str, object] = {
            "schema_version": 1,
            "status": "pinned",
            "note": "fixture",
            "lock_basis": {},
            "hash_conventions": {},
            "tools": {
                "qemu": {
                    "version": "11.1.1",
                    "revision": "c3d48b7d1e89604920e5b81b91140c2ad39a1943",
                    "source_sha256": audit_device.PINNED_QEMU_SOURCE_SRI,
                    "verified_machine": "virt",
                    "verified": True,
                }
            },
            "auxiliary_tools": {},
            "target": {},
        }
        audit_device.validate_toolchain_lock(lock)
        for key, value in (
            ("revision", "bad"),
            ("source_sha256", "bad"),
            ("verified_machine", "sifive_u"),
            ("verified", False),
        ):
            with self.subTest(key=key):
                mutated = copy.deepcopy(lock)
                tools = mutated["tools"]
                assert isinstance(tools, dict) and isinstance(tools["qemu"], dict)
                tools["qemu"][key] = value
                with self.assertRaises(Core0Error):
                    audit_device.validate_toolchain_lock(mutated)

    def test_polling_only_device_contract_is_exact(self) -> None:
        for field, value in (
            ("interrupt_use", "PLIC interrupt 10"),
            ("general_ram_api_access", True),
        ):
            with self.subTest(field=field):
                contract = copy.deepcopy(audit_device.DEVICE_CONTRACT)
                contract[field] = value
                with self.assertRaises(Core0Error):
                    audit_device.validate_device_contract(contract)


if __name__ == "__main__":
    unittest.main()
