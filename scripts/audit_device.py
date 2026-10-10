#!/usr/bin/env python3
"""Fail-closed audit for the Gate 6 compiled UART device session.

This module is intentionally independent of :mod:`audit_core0`.  It checks the
closed ``core0-v0.5`` source/effect manifest, byte protocol, pinned QEMU/DTB
contract, the small machine harness boundary, and each physical UART access in
both pre-optimization and optimized LLVM.

The LLVM audit is deliberately strict.  Source-site markers are globally unique
and dense in pre-optimization IR.  Every marked site contains exactly one
volatile ``i8`` access with alignment one, immediately bracketed by calls to the
IO-fence primitive.  Optimized IR has no markers, so it is independently
classified from direction and physical address and must retain the same six
ordered, fenced accesses.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core0_common import Core0Error, load_json, repo_root, sha256


CONTRACT_VERSION = "core0-v0.5"
ARTIFACT_CATEGORY = "test-device-suite"
TEST_ABI = "lemma-device-session-v1"
ROOT_SOURCE = "Lemma.Examples.Foundation.Device.deviceSession"
ROOT_SYMBOL = "core0_action_24"
BRANCH_SOURCE = "Lemma.Examples.Foundation.Device.dispatchBranch"
BRANCH_SYMBOL = "core0_action_15"
SEND_BYTE_SOURCE = "Lemma.Examples.Foundation.Device.Support.sendByte"
SEND_BYTE_SYMBOL = "core0_action_2"
SEND_RESPONSE_SYMBOL = "core0_action_12"

UART_BASE = 0x10000000
UART_SPAN = 0x100
UART_RBR = UART_BASE
UART_THR = UART_BASE
UART_FCR = UART_BASE + 2
UART_LSR = UART_BASE + 5
FINISHER_BASE = 0x00100000
FINISHER_SPAN = 0x1000
BRANCH_MARKER_ADDRESS = 0x80801000 + 64

ORDINARY_RAM_RANGES = (
    (0x80801000, 0x1000),
    (0x81000000, 0x1000),
    (0x80803000, 0x1000),
    (0x80805000, 0x1000),
)

PINNED_DTB_SHA256 = "c9c27a1a5c9a652c5c9daa8109c5109d651dacf502b2b7c6081d63d99849d73f"
PINNED_QEMU_SOURCE_SRI = "sha256-B5/7/4pxEbvIkCIQfLq/O7/WFNX8nXzGdZkRlqyhJII="

EFFECT_ORDER = (
    "checked-access",
    "fixed-ram-read",
    "fixed-ram-write",
    "mmio-read",
    "mmio-write",
    "io-order",
)

CHECKED_RESULT = {
    "logical_status": "u8",
    "logical_value": "u64",
    "llvm": "{ i64, i64 }",
    "rv64": "a0=status-zero-extended,a1=value",
    "status_high_bits_zero": True,
}

DEVICE_CONTRACT: dict[str, object] = {
    "schema_version": 1,
    "contract_version": CONTRACT_VERSION,
    "machine": "qemu-virt-rv64-single-hart",
    "qemu": {
        "version": "11.1.1",
        "revision": "c3d48b7d1e89604920e5b81b91140c2ad39a1943",
        "source_archive_sha256":
            "079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482",
    },
    "dtb": {
        "node": "/soc/serial@10000000",
        "compatible": "ns16550a",
        "base": "0x0000000010000000",
        "span": 256,
        "clock_hz": 3686400,
        "interrupt": 10,
    },
    "register_file": {
        "shift": 0,
        "access_width_bytes": 1,
        "implemented_bytes": 8,
        "byte_order": "little-endian",
    },
    "registers": [
        {
            "name": "RBR",
            "offset": 0,
            "access": "read",
            "side_effect": "consume-rx-fifo-byte-and-clear-DR-when-empty",
        },
        {
            "name": "THR",
            "offset": 0,
            "access": "write",
            "side_effect": "clear-THRE-and-TEMT",
        },
        {
            "name": "FCR",
            "offset": 2,
            "access": "write",
            "initial_value": 7,
            "side_effect": "enable-fifo-and-clear-rx-tx",
        },
        {
            "name": "LSR",
            "offset": 5,
            "access": "read",
            "side_effect": "clear-BI-and-OE",
        },
    ],
    "lsr_bits": {
        "data_ready": 1,
        "error_mask": 30,
        "thr_empty": 32,
        "transmitter_empty": 64,
    },
    "compiler_access": {
        "type": "volatile-i8",
        "alignment": 1,
        "ordering": "fence iorw,iorw immediately before and after every operation",
    },
    "interrupt_use": "none; Gate 6 is polling-only",
    "general_ram_api_access": False,
}

DEVICE_OPS: dict[str, dict[str, object]] = {
    "uart.read-status": {
        "stable_id": "uart.read-status",
        "source_identity": "Lemma.Core0.Memory.Action.uartReadStatus",
        "access": "read",
        "base": "0x0000000010000000",
        "offset": 5,
        "address": "0x0000000010000005",
        "width_bits": 8,
        "alignment": 1,
        "volatile": True,
        "fence_before": True,
        "fence_after": True,
        "fixed_write_value": None,
        "side_effect": "observe-line-status-and-clear-BI-OE",
    },
    "uart.read-byte": {
        "stable_id": "uart.read-byte",
        "source_identity": "Lemma.Core0.Memory.Action.uartReadByte",
        "access": "read",
        "base": "0x0000000010000000",
        "offset": 0,
        "address": "0x0000000010000000",
        "width_bits": 8,
        "alignment": 1,
        "volatile": True,
        "fence_before": True,
        "fence_after": True,
        "fixed_write_value": None,
        "side_effect": "consume-rx-fifo-byte-and-update-DR",
    },
    "uart.write-byte": {
        "stable_id": "uart.write-byte",
        "source_identity": "Lemma.Core0.Memory.Action.uartWriteByte",
        "access": "write",
        "base": "0x0000000010000000",
        "offset": 0,
        "address": "0x0000000010000000",
        "width_bits": 8,
        "alignment": 1,
        "volatile": True,
        "fence_before": True,
        "fence_after": True,
        "fixed_write_value": None,
        "side_effect": "transmit-byte-and-clear-THRE-TEMT",
    },
    "uart.enable-reset-fifo": {
        "stable_id": "uart.enable-reset-fifo",
        "source_identity": "Lemma.Core0.Memory.Action.uartEnableAndResetFifo",
        "access": "write",
        "base": "0x0000000010000000",
        "offset": 2,
        "address": "0x0000000010000002",
        "width_bits": 8,
        "alignment": 1,
        "volatile": True,
        "fence_before": True,
        "fence_after": True,
        "fixed_write_value": 7,
        "side_effect": "enable-fifo-and-clear-rx-tx",
    },
}

MEMORY_OPS: dict[str, dict[str, object]] = {
    "ram.read8": {
        "stable_id": "ram.read8",
        "source_identity": "Lemma.Core0.Memory.Action.load8",
        "access": "read",
        "width": 8,
        "range": False,
        "effect": "fixed-ram-read",
    },
    "ram.read32": {
        "stable_id": "ram.read32",
        "source_identity": "Lemma.Core0.Memory.Action.load32",
        "access": "read",
        "width": 32,
        "range": False,
        "effect": "fixed-ram-read",
    },
    "ram.read64": {
        "stable_id": "ram.read64",
        "source_identity": "Lemma.Core0.Memory.Action.load64",
        "access": "read",
        "width": 64,
        "range": False,
        "effect": "fixed-ram-read",
    },
    "ram.write8": {
        "stable_id": "ram.write8",
        "source_identity": "Lemma.Core0.Memory.Action.store8",
        "access": "write",
        "width": 8,
        "range": False,
        "effect": "fixed-ram-write",
    },
}

MACHINE_PRIMITIVES = [
    {
        "identity": "startup",
        "effect": "machine-state",
        "implementation": "Lemma.Machine.Primitives.startup",
    },
    {
        "identity": "io-fence",
        "effect": "ordered-mmio",
        "implementation": "Lemma.Machine.Primitives.ioFence",
    },
    {
        "identity": "device-test-harness",
        "effect": "action-abi/status-coded-vm-termination",
        "implementation": "Lemma.Machine.DeviceHarness.main",
    },
    {
        "identity": "sifive-test",
        "effect": "vm-termination-mmio",
        "implementation": "Lemma.Machine.DeviceHarness.successBlock/failureBlock",
    },
]

# Dependency-first closure exported by the fixed Gate 6 root.  Each entry is
# source name, scalar argument types, direct Action dependencies, direct effects,
# and the exact transitive effect closure.
ACTION_CONTRACTS: tuple[
    tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...
] = (
    ("Lemma.Platform.LemmaVM.ConsoleDevice.transmitPollStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (),
     ("mmio-read", "mmio-write", "io-order"),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Platform.LemmaVM.ConsoleDevice.sendByte", ("u8",),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.transmitPollStep",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendByte", ("u8",),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.sendByte",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.readyStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.Support.sendByte",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendReady", (),
     ("Lemma.Examples.Foundation.Device.Support.readyStep",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (),
     ("mmio-read", "io-order"), ("mmio-read", "io-order")),
    ("Lemma.Platform.LemmaVM.ConsoleDevice.receiveByte", (),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep",), (),
     ("mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.receiveByte", (),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.receiveByte",), (),
     ("mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.receiveIntoStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.Support.receiveByte",),
     ("checked-access", "fixed-ram-write"),
     ("checked-access", "fixed-ram-write", "mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.receiveHeader", (),
     ("Lemma.Examples.Foundation.Device.Support.receiveIntoStep",), (),
     ("checked-access", "fixed-ram-write", "mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.receivePayload", ("u32",),
     ("Lemma.Examples.Foundation.Device.Support.receiveIntoStep",), (),
     ("checked-access", "fixed-ram-write", "mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.responseStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.Support.sendByte",),
     ("checked-access", "fixed-ram-write"),
     ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendResponse", ("u8", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.Support.responseStep",), (),
     ("checked-access", "fixed-ram-write", "mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.dispatchAdd64", ("u64",),
     ("Lemma.Examples.Foundation.Device.Support.sendResponse",),
     ("checked-access", "fixed-ram-read"), tuple(EFFECT_ORDER)),
    ("Lemma.Examples.Foundation.Device.dispatchXor64", ("u64",),
     ("Lemma.Examples.Foundation.Device.Support.sendResponse",),
     ("checked-access", "fixed-ram-read"), tuple(EFFECT_ORDER)),
    ("Lemma.Examples.Foundation.Device.dispatchBranch", ("u64",),
     ("Lemma.Examples.Foundation.Device.Support.sendResponse",
      "Lemma.Examples.Foundation.Device.Support.sendByte"),
     ("checked-access", "fixed-ram-read", "fixed-ram-write"), tuple(EFFECT_ORDER)),
    ("Lemma.Examples.Foundation.Device.Support.repeatedByteStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.Support.sendByte",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.sendRepeatedByte", ("u32", "u8"),
     ("Lemma.Examples.Foundation.Device.Support.repeatedByteStep",), (),
     ("mmio-read", "mmio-write", "io-order")),
    ("Lemma.Examples.Foundation.Device.dispatchTxStress", ("u64",),
     ("Lemma.Examples.Foundation.Device.Support.sendRepeatedByte",
      "Lemma.Examples.Foundation.Device.Support.sendResponse"),
     ("checked-access", "fixed-ram-read"), tuple(EFFECT_ORDER)),
    ("Lemma.Examples.Foundation.Device.dispatchRequest", ("u64", "u64", "u64"),
     ("Lemma.Examples.Foundation.Device.dispatchAdd64",
      "Lemma.Examples.Foundation.Device.dispatchXor64",
      "Lemma.Examples.Foundation.Device.dispatchBranch",
      "Lemma.Examples.Foundation.Device.dispatchTxStress",
      "Lemma.Examples.Foundation.Device.Support.sendResponse"), (), tuple(EFFECT_ORDER)),
    ("Lemma.Examples.Foundation.Device.handleRequest", (),
     ("Lemma.Examples.Foundation.Device.Support.receiveHeader",
      "Lemma.Examples.Foundation.Device.Support.receivePayload",
      "Lemma.Examples.Foundation.Device.dispatchRequest"),
     ("checked-access", "fixed-ram-read"), tuple(EFFECT_ORDER)),
    ("Lemma.Platform.LemmaVM.ConsoleDevice.drainPollStep",
     ("u32", "u32", "u64", "u64", "u64", "u64", "u64"), (),
     ("mmio-read", "io-order"), ("mmio-read", "io-order")),
    ("Lemma.Platform.LemmaVM.ConsoleDevice.drain", (),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.drainPollStep",), (),
     ("mmio-read", "io-order")),
    ("Lemma.Examples.Foundation.Device.Support.drain", (),
     ("Lemma.Platform.LemmaVM.ConsoleDevice.drain",), (),
     ("mmio-read", "io-order")),
    (ROOT_SOURCE, (),
     ("Lemma.Examples.Foundation.Device.Support.sendReady",
      "Lemma.Examples.Foundation.Device.handleRequest",
      "Lemma.Examples.Foundation.Device.Support.drain"),
     ("mmio-write", "io-order"), tuple(EFFECT_ORDER)),
)

ITERATION_CONTRACTS = (
    (21, "Lemma.Examples.Foundation.Device.Support.readyStep"),
    (1000000, "Lemma.Platform.LemmaVM.ConsoleDevice.transmitPollStep"),
    (16, "Lemma.Examples.Foundation.Device.Support.receiveIntoStep"),
    (1000000, "Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep"),
    (24, "Lemma.Examples.Foundation.Device.Support.responseStep"),
    (65535, "Lemma.Examples.Foundation.Device.Support.repeatedByteStep"),
    (1000000, "Lemma.Platform.LemmaVM.ConsoleDevice.drainPollStep"),
)

SOURCE_DEVICE_TOKENS = {
    "uart-read-status": "uart.read-status",
    "uart-read-byte": "uart.read-byte",
    "uart-write-byte": "uart.write-byte",
    "uart-enable-reset-fifo": "uart.enable-reset-fifo",
}
SOURCE_DEVICE_COUNTS = Counter({
    "uart.read-status": 3,
    "uart.read-byte": 1,
    "uart.write-byte": 1,
    "uart.enable-reset-fifo": 1,
})

LOW_LEVEL_SITE_SEQUENCE = (
    "uart.lsr.read8",
    "uart.thr.write8",
    "uart.lsr.read8",
    "uart.rbr.read8",
    "uart.lsr.read8",
    "uart.fcr.enable-reset",
)

LOW_LEVEL_TO_SOURCE = {
    "uart.lsr.read8": "uart.read-status",
    "uart.rbr.read8": "uart.read-byte",
    "uart.thr.write8": "uart.write-byte",
    "uart.fcr.enable-reset": "uart.enable-reset-fifo",
}

TOP_LEVEL_KEYS = {
    "schema_version", "artifact_category", "contract_version", "test_abi",
    "suite_id", "source_seed", "runtime_seed", "checked_result",
    "memory_contract", "device_contract", "roots", "scalar_functions",
    "action_functions", "used_primitives", "used_memory_ops",
    "used_device_ops", "action_iterations", "machine_primitives",
}

HEX64 = re.compile(r"[0-9a-f]{16}")
LEAN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
LLVM_SYMBOL = re.compile(r"core0_(?:action|scalar)_[0-9]+")
SITE_MARKER = re.compile(r"^\s*; lemma\.uart-site=([0-9]+);op=([a-z0-9.-]+)\s*$")
FENCE_CALL = re.compile(r"^\s*(?:tail )?call void @core0_io_fence\(\)(?: #[0-9]+)?\s*$")
DIRECT_ADDRESS = re.compile(r"inttoptr \(i64 ([0-9]+) to ptr\)")
CONSTANT_POINTER = re.compile(r"inttoptr (?:\()?i64 ([0-9]+) to ptr(?:\))?")


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Core0Error(f"{context} must be an object")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Core0Error(f"{context} must be an array")
    return value


def _string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise Core0Error(f"{context} must be a string")
    return value


def _expect_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise Core0Error(
            f"{context} keys differ: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )


def _unique_strings(value: object, context: str) -> list[str]:
    items = _list(value, context)
    if not all(isinstance(item, str) for item in items):
        raise Core0Error(f"{context} must contain only strings")
    result = [str(item) for item in items]
    if len(result) != len(set(result)):
        raise Core0Error(f"{context} contains duplicates")
    return result


def _canonical_id(value: object, context: str) -> str:
    text = _string(value, context)
    if HEX64.fullmatch(text) is None:
        raise Core0Error(f"{context} must be exactly 16 lowercase hexadecimal digits")
    return text


def _ordered_union(*effect_lists: Sequence[str]) -> list[str]:
    present = {effect for effects in effect_lists for effect in effects}
    unknown = present - set(EFFECT_ORDER)
    if unknown:
        raise Core0Error(f"unknown effects in closure: {sorted(unknown)}")
    return [effect for effect in EFFECT_ORDER if effect in present]


def validate_device_contract(contract: Mapping[str, object]) -> dict[str, object]:
    """Require the exact reviewed QEMU ``virt``/ns16550a device contract."""
    if dict(contract) != DEVICE_CONTRACT:
        raise Core0Error("device contract differs from the pinned QEMU/DTB ns16550a contract")
    return {
        "qemu_version": "11.1.1",
        "qemu_revision": "c3d48b7d1e89604920e5b81b91140c2ad39a1943",
        "dtb_node": "/soc/serial@10000000",
        "uart_base": UART_BASE,
    }


ABI_FIXED: dict[str, object] = {
    "schema_version": 1,
    "contract_version": CONTRACT_VERSION,
    "name": TEST_ABI,
    "byte_order": "little-endian",
    "ready": "LEMMA_DEVICE/1\nREADY\n",
    "requests_per_session": 2,
    "poll_budget": 1000000,
    "request": {
        "bytes": "16-byte-header + payload",
        "maximum_payload_bytes": 16,
        "magic_bytes": "4c4d5136",
        "magic_u32": "0x36514d4c",
        "fields": [
            "magic:u32@0", "version:u8@4", "command:u8@5", "length:u8@6",
            "flags:u8@7", "request_id:u64@8",
        ],
    },
    "response": {
        "bytes": 24,
        "magic_bytes": "4c4d5336",
        "magic_u32": "0x36534d4c",
        "fields": [
            "magic:u32@0", "version:u8@4", "status:u8@5", "length:u8@6=8",
            "flags:u8@7=0", "request_id:u64@8", "value:u64@16",
        ],
    },
    "commands": [
        {"code": 1, "name": "add64", "payload_bytes": 16},
        {"code": 2, "name": "xor64", "payload_bytes": 16},
        {
            "code": 3, "name": "branch", "payload_bytes": 1,
            "false_ram_marker": "scratch+64=0x5a", "true_uart_marker": 165,
        },
        {
            "code": 4, "name": "tx-stress", "payload_bytes": 4,
            "maximum_count": 65535, "byte": 85,
        },
    ],
    "statuses": [
        {"code": 0, "name": "ok"},
        {"code": 10, "name": "poll-again-internal", "public": False},
        {"code": 11, "name": "tx-timeout"},
        {"code": 12, "name": "rx-timeout"},
        {"code": 13, "name": "line-error"},
        {"code": 14, "name": "malformed-frame"},
        {"code": 15, "name": "truncated-frame"},
        {"code": 16, "name": "invalid-length"},
        {"code": 17, "name": "unsupported-command"},
    ],
    "terminal_rules": {
        "no_first_byte": 12,
        "partial_header_or_payload": 15,
        "unsupported_command_responds_and_continues": True,
        "internal_status_must_not_escape": 10,
    },
}


def validate_device_abi(
    abi: Mapping[str, object],
    manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    expected_keys = set(ABI_FIXED) | {"suite_id", "source_seed", "runtime_seed"}
    _expect_keys(abi, expected_keys, "device ABI")
    for key, expected in ABI_FIXED.items():
        if abi.get(key) != expected:
            raise Core0Error(f"device ABI field `{key}` differs from its closed contract")
    identities = {
        key: _canonical_id(abi.get(key), f"device ABI {key}")
        for key in ("suite_id", "source_seed", "runtime_seed")
    }
    if manifest is not None:
        for key, value in identities.items():
            if manifest.get(key) != value:
                raise Core0Error(f"device ABI {key} does not match the suite manifest")
    return {"requests_per_session": 2, "commands": 4, "statuses": 9, **identities}


def validate_device_test_abi(
    value: Mapping[str, object], manifest: Mapping[str, object]
) -> dict[str, object]:
    """Stable integration spelling used by the cumulative Gate 6 checker."""
    return validate_device_abi(value, manifest)


def _validate_memory_boundary(memory: object) -> None:
    contract = _mapping(memory, "memory contract")
    _expect_keys(
        contract,
        {"byte_order", "guard_order", "successful_access_volatile", "regions", "statuses"},
        "memory contract",
    )
    if (
        contract.get("byte_order") != "little-endian"
        or contract.get("guard_order")
        != ["lookup", "class", "permission", "width", "bounds", "alignment"]
        or contract.get("successful_access_volatile") is not True
    ):
        raise Core0Error("device suite changed the checked-memory byte/guard contract")
    regions = _list(contract.get("regions"), "memory regions")
    by_id: dict[int, Mapping[str, object]] = {}
    for raw in regions:
        region = _mapping(raw, "memory region")
        identifier = region.get("id")
        if isinstance(identifier, bool) or not isinstance(identifier, int):
            raise Core0Error("memory region id must be an integer")
        if identifier in by_id:
            raise Core0Error(f"memory region id {identifier} is duplicated")
        by_id[identifier] = region
        if region.get("kind") == "device":
            if identifier not in {0x80, 0x81}:
                raise Core0Error(f"undeclared device region {identifier} is present")
            if (
                region.get("widths") != []
                or region.get("read") is not False
                or region.get("write") is not False
            ):
                raise Core0Error(f"device region {identifier} can reach the general RAM API")
    for identifier, name, base, length in (
        (0x80, "uart16550", UART_BASE, UART_SPAN),
        (0x81, "sifive-test", FINISHER_BASE, 0x1000),
    ):
        region = by_id.get(identifier)
        if region is None:
            raise Core0Error(f"memory contract omits device region {identifier}")
        expected_subset = {
            "name": name,
            "base": base,
            "length": length,
            "widths": [],
            "read": False,
            "write": False,
            "kind": "device",
            "interval_valid": True,
        }
        if any(region.get(key) != value for key, value in expected_subset.items()):
            raise Core0Error(f"memory region {identifier} can reach the general RAM API")
    statuses = _list(contract.get("statuses"), "memory statuses")
    expected_statuses = [
        {"code": code, "name": name}
        for code, name in enumerate((
            "ok", "unknown-region", "reserved-region", "device-region", "read-denied",
            "write-denied", "width-denied", "out-of-bounds", "misaligned",
            "budget-exceeded",
        ))
    ]
    if statuses != expected_statuses:
        raise Core0Error("device suite changed the v0.4 checked-memory status catalog")


def _body_effects(body: str) -> list[str]:
    present: set[str] = set()
    if re.search(r"\(action\.(?:load8|load32|load64)\b", body):
        present.update(("checked-access", "fixed-ram-read"))
    if re.search(r"\(action\.(?:store8|store32|store64)\b", body):
        present.update(("checked-access", "fixed-ram-write"))
    if re.search(r"\(action\.check-(?:read|write)-range\b", body):
        present.add("checked-access")
    if re.search(r"\(action\.uart-(?:read-status|read-byte)\b", body):
        present.update(("mmio-read", "io-order"))
    if re.search(r"\(action\.uart-(?:write-byte|enable-reset-fifo)\b", body):
        present.update(("mmio-write", "io-order"))
    return [effect for effect in EFFECT_ORDER if effect in present]


def _body_action_dependencies(body: str) -> list[str]:
    dependencies: list[str] = []
    pattern = re.compile(
        r"\(action\.call ([A-Za-z_][A-Za-z0-9_.]+) \[|"
        r"callback=([A-Za-z_][A-Za-z0-9_.]+)"
    )
    for match in pattern.finditer(body):
        dependency = match.group(1) or match.group(2)
        if dependency not in dependencies:
            dependencies.append(dependency)
    return dependencies


def _source_device_counts(functions: Sequence[Mapping[str, object]]) -> Counter[str]:
    result: Counter[str] = Counter()
    token_pattern = re.compile(
        r"\(action\.(uart-(?:read-status|read-byte|write-byte|enable-reset-fifo))\b"
    )
    for function in functions:
        body = _string(function.get("body"), "Action body")
        for token in token_pattern.findall(body):
            result[SOURCE_DEVICE_TOKENS[token]] += 1
        if "Lemma.Core0.Memory.RegionId.uart" in body or "RegionId.finisher" in body:
            raise Core0Error("general checked-memory syntax names a device region")
        for suspicious in (
            "action.mmio", "action.device-read", "action.device-write",
            "action.interrupt", "action.csr", "action.wfi", "plic",
        ):
            if suspicious in body:
                raise Core0Error(f"generic device syntax `{suspicious}` is forbidden")
        closed_uart_body = token_pattern.sub("(action.closed-uart", body)
        if "(action.uart-" in closed_uart_body:
            raise Core0Error("Action body contains a UART operation outside the closed catalog")
    return result


def _parse_normalized_expr(text: str) -> list[object]:
    tokens = re.findall(r"[()\[\]]|[^()\[\]\s]+", text)

    def parse_at(index: int) -> tuple[object, int]:
        if index >= len(tokens):
            raise Core0Error("normalized Action expression is truncated")
        token = tokens[index]
        if token not in {"(", "["}:
            if token in {")", "]"}:
                raise Core0Error("normalized Action expression has an unmatched delimiter")
            return token, index + 1
        close = ")" if token == "(" else "]"
        values: list[object] = [] if token == "(" else ["[]"]
        index += 1
        while index < len(tokens) and tokens[index] != close:
            value, index = parse_at(index)
            values.append(value)
        if index >= len(tokens):
            raise Core0Error("normalized Action expression has an unterminated delimiter")
        return values, index + 1

    value, index = parse_at(0)
    if index != len(tokens) or not isinstance(value, list):
        raise Core0Error("normalized Action expression has trailing or non-list syntax")
    return value


def _walk_expr(value: object) -> list[list[object]]:
    if not isinstance(value, list):
        return []
    result = [value]
    for child in value:
        result.extend(_walk_expr(child))
    return result


def _expr_head(value: object, head: str) -> bool:
    return isinstance(value, list) and bool(value) and value[0] == head


def _selector_condition(value: object, literal: str) -> object | None:
    if (
        not isinstance(value, list)
        or len(value) != 5
        or value[:3] != ["cmp", "eq", "u64"]
        or value[4] != ["lit", "u64", literal]
    ):
        return None
    return value[3]


def _is_false_marker_store(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 5
        and value[0] == "action.store8"
        and value[1]
        == ["call", "Lemma.Core0.Memory.RegionId.scratch", "u8", ["[]"]]
        and value[2] == ["lit", "u64", "64"]
        and value[3] == ["lit", "u8", "90"]
    )


BRANCH_READBACK = {
    "scratch_offset": 64,
    "width_bits": 8,
    "sentinel_byte": 60,
    "false_marker_byte": 90,
    "response_shift": 8,
    "includes_selector": True,
    "selector_0_expected": 0x5a00,
    "selector_1_expected": 0x3c01,
}


def _is_scratch_readback(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 6
        and value[0] == "action.load8"
        and value[1] == ["call", "Lemma.Core0.Memory.RegionId.scratch", "u8", ["[]"]]
        and value[2] == ["lit", "u64", "64"]
    )


def _readback_response_encoded(readback: list[object], selector: object) -> bool:
    binder = readback[4]
    if not isinstance(binder, list) or len(binder) != 2 or binder[0] != "value":
        return False
    variable = str(binder[1]).removeprefix("%")
    expression = [
        "bin", "add", "u64",
        ["bin", "shl", "u64", ["var", variable, "u64"], ["lit", "u64", "8"]],
        selector,
    ]
    responses = [
        node for node in _walk_expr(readback[5])
        if _expr_head(node, "action.call")
        and len(node) == 3
        and node[1] == "Lemma.Examples.Foundation.Device.Support.sendResponse"
    ]
    return (
        len(responses) == 1
        and isinstance(responses[0][2], list)
        and len(responses[0][2]) == 4
        and responses[0][2][-1] == expression
    )


def _is_true_uart_call(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and value[0] == "action.call"
        and value[1] == SEND_BYTE_SOURCE
        and value[2] == ["[]", ["lit", "u8", "165"]]
    )


def validate_branch_source_placement(body: str) -> dict[str, object]:
    """Prove the two branch-only effects occupy opposite source subtrees."""
    tree = _parse_normalized_expr(body)
    nodes = _walk_expr(tree)
    markers = [node for node in nodes if _is_false_marker_store(node)]
    sentinels = [
        node for node in nodes
        if isinstance(node, list) and len(node) == 6
        and node[:3] == [
            "action.store8",
            ["call", "Lemma.Core0.Memory.RegionId.scratch", "u8", ["[]"]],
            ["lit", "u64", "64"],
        ]
        and node[3] == ["lit", "u8", "60"]
    ]
    readbacks = [node for node in nodes if _is_scratch_readback(node)]
    sends = [node for node in nodes if _is_true_uart_call(node)]
    zero_branches = [
        node
        for node in nodes
        if _expr_head(node, "action.ite")
        and len(node) == 4
        and _selector_condition(node[1], "0") is not None
    ]
    if len(markers) != 1 or len(sends) != 1 or len(zero_branches) != 1:
        raise Core0Error(
            "dispatchBranch must contain one selector-0 branch, one scratch+64 marker, "
            "and one sendByte(0xa5)"
        )
    zero = zero_branches[0]
    selector = _selector_condition(zero[1], "0")
    assert selector is not None
    false_nodes = _walk_expr(zero[2])
    remaining_nodes = _walk_expr(zero[3])
    one_branches = [
        node
        for node in remaining_nodes
        if _expr_head(node, "action.ite")
        and len(node) == 4
        and _selector_condition(node[1], "1") == selector
    ]
    if len(one_branches) != 1:
        raise Core0Error("dispatchBranch selector-1 continuation is absent or ambiguous")
    one = one_branches[0]
    true_nodes = _walk_expr(one[2])
    default_nodes = _walk_expr(one[3])
    if markers[0] not in false_nodes or sends[0] in false_nodes:
        raise Core0Error("dispatchBranch selector 0 does not exclusively own the RAM marker")
    if sends[0] not in true_nodes or markers[0] in true_nodes:
        raise Core0Error("dispatchBranch selector 1 does not exclusively own sendByte(0xa5)")
    if markers[0] in default_nodes or sends[0] in default_nodes:
        raise Core0Error("dispatchBranch default path contains a branch-only effect")
    if len(sentinels) != 1 or zero not in _walk_expr(sentinels[0][5]):
        raise Core0Error("dispatchBranch common scratch sentinel does not precede selection")
    if sentinels[0] in false_nodes or sentinels[0] in true_nodes:
        raise Core0Error("dispatchBranch sentinel initialization is branch-local")
    false_reads = [node for node in readbacks if node in false_nodes]
    true_reads = [node for node in readbacks if node in true_nodes]
    if len(readbacks) != 2 or len(false_reads) != 1 or len(true_reads) != 1:
        raise Core0Error("dispatchBranch must contain one scratch readback in each selected branch")
    if any(node in default_nodes for node in readbacks):
        raise Core0Error("dispatchBranch default path performs a readback")
    if false_reads[0] not in _walk_expr(markers[0]):
        raise Core0Error("dispatchBranch false readback does not follow its marker write")
    send_binds = [
        node for node in true_nodes
        if _expr_head(node, "action.bind") and len(node) == 5 and node[1] == sends[0]
    ]
    if len(send_binds) != 1 or true_reads[0] not in _walk_expr(send_binds[0][4]):
        raise Core0Error("dispatchBranch true readback does not follow its UART marker")
    if not all(_readback_response_encoded(readback, selector) for readback in readbacks):
        raise Core0Error("dispatchBranch response does not encode its actual readback and selector")
    return {
        "source_function": BRANCH_SOURCE,
        "llvm_symbol": BRANCH_SYMBOL,
        "selector_0": {
            "scratch_offset": 64,
            "stored_byte": 90,
            "send_byte_0xa5": False,
        },
        "selector_1": {
            "scratch_marker_store": False,
            "sent_byte": 165,
        },
        "separate_subtrees": True,
        "readback": dict(BRANCH_READBACK),
        "common_sentinel_before_selection": True,
        "branch_local_readbacks": True,
        "readbacks_encoded": True,
    }


def validate_effect_closure(manifest: Mapping[str, object]) -> dict[str, object]:
    raw_functions = _list(manifest.get("action_functions"), "Action functions")
    functions = [_mapping(raw, "Action function") for raw in raw_functions]
    if len(functions) != len(ACTION_CONTRACTS):
        raise Core0Error(
            f"device Action closure has {len(functions)} functions, expected {len(ACTION_CONTRACTS)}"
        )
    expected_sources = [entry[0] for entry in ACTION_CONTRACTS]
    actual_sources = [function.get("source") for function in functions]
    if actual_sources != expected_sources:
        raise Core0Error("device Action closure is not the exact dependency-first source closure")

    by_source: dict[str, Mapping[str, object]] = {}
    by_llvm: dict[str, str] = {}
    for index, (function, contract) in enumerate(zip(functions, ACTION_CONTRACTS)):
        source, args, dependencies, direct, transitive = contract
        _expect_keys(
            function,
            {
                "source", "llvm", "signature", "scalar_dependencies",
                "action_dependencies", "direct_effects", "transitive_effects",
                "body", "noinline",
            },
            f"Action function {source}",
        )
        if function.get("source") != source:
            raise Core0Error(f"Action function #{index} source differs")
        symbol = _string(function.get("llvm"), f"Action function {source} symbol")
        if symbol != f"core0_action_{index}" or LLVM_SYMBOL.fullmatch(symbol) is None:
            raise Core0Error(f"Action function `{source}` has an unexpected LLVM symbol")
        if symbol in by_llvm:
            raise Core0Error(f"Action LLVM symbol `{symbol}` is duplicated")
        by_llvm[symbol] = source
        signature = _mapping(function.get("signature"), f"Action function {source} signature")
        if signature != {"args": list(args)}:
            raise Core0Error(f"Action function `{source}` signature differs")
        declared_dependencies = _unique_strings(
            function.get("action_dependencies"), f"Action function {source} dependencies"
        )
        if declared_dependencies != list(dependencies):
            raise Core0Error(f"Action function `{source}` dependency closure differs")
        body = _string(function.get("body"), f"Action function {source} body")
        if not body.startswith("(action."):
            raise Core0Error(f"Action function `{source}` has no normalized Action body")
        body_dependencies = _body_action_dependencies(body)
        if body_dependencies != declared_dependencies:
            raise Core0Error(f"Action function `{source}` has stale dependency metadata")
        actual_direct = _unique_strings(
            function.get("direct_effects"), f"Action function {source} direct effects"
        )
        if actual_direct != list(direct) or actual_direct != _body_effects(body):
            raise Core0Error(f"Action function `{source}` has stale direct effects")
        actual_transitive = _unique_strings(
            function.get("transitive_effects"),
            f"Action function {source} transitive effects",
        )
        if actual_transitive != list(transitive):
            raise Core0Error(f"Action function `{source}` has stale transitive effects")
        if function.get("noinline") is not True:
            raise Core0Error(f"Action function `{source}` is not preserved for audit")
        _unique_strings(
            function.get("scalar_dependencies"), f"Action function {source} scalar dependencies"
        )
        by_source[source] = function

    for source, _args, dependencies, direct, transitive in ACTION_CONTRACTS:
        inherited = [
            _unique_strings(
                by_source[dependency].get("transitive_effects"),
                f"callee {dependency} transitive effects",
            )
            for dependency in dependencies
        ]
        computed = _ordered_union(list(direct), *inherited)
        if computed != list(transitive):
            raise Core0Error(f"Action function `{source}` transitive effect closure is inconsistent")

    counts = _source_device_counts(functions)
    if counts != SOURCE_DEVICE_COUNTS:
        raise Core0Error(
            f"source device operation counts differ: got {dict(counts)}, "
            f"expected {dict(SOURCE_DEVICE_COUNTS)}"
        )
    branch_function = by_source[BRANCH_SOURCE]
    if branch_function.get("llvm") != BRANCH_SYMBOL:
        raise Core0Error("dispatchBranch has an unexpected LLVM identity")
    branch_effects = validate_branch_source_placement(
        _string(branch_function.get("body"), "dispatchBranch body")
    )
    return {
        "action_functions": len(functions),
        "source_device_operations": sum(counts.values()),
        "root_effects": list(EFFECT_ORDER),
        "branch_effects": branch_effects,
    }


def _validate_manifest_companions(manifest: Mapping[str, object]) -> None:
    scalar_functions = _list(manifest.get("scalar_functions"), "scalar functions")
    scalar_sources: set[str] = set()
    scalar_symbols: set[str] = set()
    for raw in scalar_functions:
        function = _mapping(raw, "scalar function")
        _expect_keys(
            function,
            {"source", "llvm", "signature", "dependencies", "body", "noinline"},
            "scalar function",
        )
        source = _string(function.get("source"), "scalar source")
        symbol = _string(function.get("llvm"), f"scalar `{source}` symbol")
        if source in scalar_sources or symbol in scalar_symbols:
            raise Core0Error("scalar source or LLVM symbol is duplicated")
        if LEAN_NAME.fullmatch(source) is None or LLVM_SYMBOL.fullmatch(symbol) is None:
            raise Core0Error("scalar source/symbol identity is malformed")
        scalar_sources.add(source)
        scalar_symbols.add(symbol)
        if function.get("noinline") is not True or not isinstance(function.get("body"), str):
            raise Core0Error(f"scalar function `{source}` is not preserved with a body")

    primitives = _list(manifest.get("used_primitives"), "used primitives")
    primitive_ids: set[str] = set()
    for raw in primitives:
        primitive = _mapping(raw, "used primitive")
        _expect_keys(
            primitive, {"stable_id", "lean_identities", "signature", "effect"},
            "used primitive",
        )
        stable_id = _string(primitive.get("stable_id"), "primitive stable id")
        if stable_id in primitive_ids or primitive.get("effect") != "pure":
            raise Core0Error("primitive metadata is duplicated or effectful")
        primitive_ids.add(stable_id)
        identities = _unique_strings(primitive.get("lean_identities"), stable_id)
        if not identities or not isinstance(primitive.get("signature"), Mapping):
            raise Core0Error(f"primitive `{stable_id}` has no exact identity/signature")

    memory_ops = _list(manifest.get("used_memory_ops"), "used memory operations")
    actual_memory: dict[str, Mapping[str, object]] = {}
    for raw in memory_ops:
        operation = _mapping(raw, "used memory operation")
        stable_id = _string(operation.get("stable_id"), "memory operation stable id")
        if stable_id in actual_memory:
            raise Core0Error(f"memory operation `{stable_id}` is duplicated")
        actual_memory[stable_id] = operation
    if set(actual_memory) != set(MEMORY_OPS):
        raise Core0Error("device suite memory-operation catalog differs")
    for stable_id, expected in MEMORY_OPS.items():
        if dict(actual_memory[stable_id]) != expected:
            raise Core0Error(f"memory operation `{stable_id}` differs from its contract")

    iterations = _list(manifest.get("action_iterations"), "Action iterations")
    observed: list[tuple[int, str]] = []
    expected_keys = {
        "stable_id", "source_identity", "static_budget", "callback", "maximum_budget",
        "counter", "accumulator", "contexts", "outcome", "exhaustion",
    }
    for raw in iterations:
        iteration = _mapping(raw, "Action iteration")
        _expect_keys(iteration, expected_keys, "Action iteration")
        expected_static = {
            "stable_id": "action.u64.bounded-fold",
            "source_identity": "Lemma.Core0.Memory.Action.boundedFoldU64",
            "maximum_budget": 1000000,
            "counter": {"type": "u32", "order": "ascending-zero-based"},
            "accumulator": "u64",
            "contexts": 4,
            "outcome": "checked-result-v1",
            "exhaustion": {"status": 9, "value": "initial", "callbacks": 0},
        }
        if any(iteration.get(key) != value for key, value in expected_static.items()):
            raise Core0Error("Action iteration contract differs from v0.5")
        budget = iteration.get("static_budget")
        callback = iteration.get("callback")
        if isinstance(budget, bool) or not isinstance(budget, int) or not isinstance(callback, str):
            raise Core0Error("Action iteration budget/callback is malformed")
        observed.append((budget, callback))
    if observed != list(ITERATION_CONTRACTS):
        raise Core0Error("device Action iteration closure differs")


def validate_device_suite_manifest(
    manifest: Mapping[str, object],
    *,
    normalized: str | None = None,
) -> dict[str, object]:
    """Validate the exact Gate 6 source, device, ABI, and effect manifest."""
    _expect_keys(manifest, TOP_LEVEL_KEYS, "device suite manifest")
    for key, expected in (
        ("schema_version", 1),
        ("artifact_category", ARTIFACT_CATEGORY),
        ("contract_version", CONTRACT_VERSION),
        ("test_abi", TEST_ABI),
    ):
        if manifest.get(key) != expected:
            raise Core0Error(f"device manifest {key} differs")
    identities = {
        key: _canonical_id(manifest.get(key), f"device manifest {key}")
        for key in ("suite_id", "source_seed", "runtime_seed")
    }
    if manifest.get("checked_result") != CHECKED_RESULT:
        raise Core0Error("device manifest checked-result ABI differs")
    _validate_memory_boundary(manifest.get("memory_contract"))
    validate_device_contract(_mapping(manifest.get("device_contract"), "device contract"))

    roots = _list(manifest.get("roots"), "device roots")
    expected_root = {
        "root_id": 1,
        "source": ROOT_SOURCE,
        "llvm": ROOT_SYMBOL,
        "signature": {"args": []},
    }
    if roots != [expected_root]:
        raise Core0Error("device suite must expose only the fixed zero-argument deviceSession root")

    raw_ops = _list(manifest.get("used_device_ops"), "used device operations")
    by_id: dict[str, Mapping[str, object]] = {}
    for raw in raw_ops:
        operation = _mapping(raw, "used device operation")
        stable_id = _string(operation.get("stable_id"), "device operation stable id")
        if stable_id in by_id:
            raise Core0Error(f"device operation `{stable_id}` is duplicated")
        by_id[stable_id] = operation
    if set(by_id) != set(DEVICE_OPS) or len(raw_ops) != 4:
        raise Core0Error("device manifest is not closed over exactly four UART operations")
    for stable_id, expected in DEVICE_OPS.items():
        if dict(by_id[stable_id]) != expected:
            raise Core0Error(f"device operation `{stable_id}` differs from its exact contract")

    effects = validate_effect_closure(manifest)
    _validate_manifest_companions(manifest)
    if manifest.get("machine_primitives") != MACHINE_PRIMITIVES:
        raise Core0Error("device machine-primitive closure differs")

    if normalized is not None:
        validate_device_normalized(manifest, normalized)
    return {**identities, **effects, "device_operations": 4}


def validate_device_normalized(manifest: Mapping[str, object], normalized: str) -> None:
    if not normalized.endswith("\n"):
        raise Core0Error("device normalized companion must end in one line boundary")
    lines = normalized.splitlines()
    if not lines or lines[0] != f"contract={CONTRACT_VERSION}":
        raise Core0Error("device normalized companion has the wrong contract")
    root_line = f'root=1;source={ROOT_SOURCE};signature={{"args":[]}}'
    root_lines = [line for line in lines if line.startswith("root=")]
    if root_lines != [root_line]:
        raise Core0Error("device normalized companion has the wrong root")
    for raw in _list(manifest.get("action_functions"), "Action functions"):
        function = _mapping(raw, "Action function")
        direct = "[" + ",".join(_unique_strings(
            function.get("direct_effects"), "direct effects"
        )) + "]"
        transitive = "[" + ",".join(_unique_strings(
            function.get("transitive_effects"), "transitive effects"
        )) + "]"
        expected = (
            f"action={function['source']};direct={direct};transitive={transitive};"
            f"body={function['body']}"
        )
        if lines.count(expected) != 1:
            raise Core0Error(f"normalized Action body/effects drifted for `{function['source']}`")
    action_lines = [line for line in lines if line.startswith("action=")]
    if len(action_lines) != len(_list(manifest.get("action_functions"), "Action functions")):
        raise Core0Error("normalized companion contains an undeclared Action function")
    device_lines = [line for line in lines if line.startswith("device-op=")]
    if Counter(device_lines) != Counter(f"device-op={stable_id}" for stable_id in DEVICE_OPS):
        raise Core0Error("normalized device-operation catalog differs")


def validate_toolchain_lock(lock: Mapping[str, object]) -> None:
    _expect_keys(
        lock,
        {
            "schema_version", "status", "note", "lock_basis", "hash_conventions",
            "tools", "auxiliary_tools", "target",
        },
        "toolchain lock",
    )
    if lock.get("schema_version") != 1 or lock.get("status") != "pinned":
        raise Core0Error("toolchain lock is not the pinned schema")
    tools = _mapping(lock.get("tools"), "toolchain lock tools")
    qemu = _mapping(tools.get("qemu"), "toolchain lock QEMU")
    expected = _mapping(DEVICE_CONTRACT["qemu"], "expected QEMU")
    if qemu.get("version") != expected["version"] or qemu.get("revision") != expected["revision"]:
        raise Core0Error("toolchain lock QEMU identity differs from the device contract")
    if qemu.get("source_sha256") != PINNED_QEMU_SOURCE_SRI or qemu.get("verified") is not True:
        raise Core0Error("toolchain lock does not verify the pinned QEMU source archive")
    if qemu.get("verified_machine") != "virt":
        raise Core0Error("toolchain lock does not verify QEMU virt")


def _extract_dts_node(dts: str, node: str) -> str:
    marker = f"{node} {{"
    start = dts.find(marker)
    if start < 0:
        raise Core0Error(f"DTS omits `{node}`")
    brace = dts.find("{", start)
    depth = 0
    for index in range(brace, len(dts)):
        if dts[index] == "{":
            depth += 1
        elif dts[index] == "}":
            depth -= 1
            if depth == 0:
                return dts[start:index + 1]
    raise Core0Error(f"DTS node `{node}` is unterminated")


def validate_platform_evidence(dtb_sha256: str, dts: str) -> None:
    if dtb_sha256 != PINNED_DTB_SHA256:
        raise Core0Error("platform DTB hash differs from the pinned QEMU virt artifact")
    node = _extract_dts_node(dts, "serial@10000000")
    for required in (
        'compatible = "ns16550a";',
        "reg = <0x00 0x10000000 0x00 0x100>;",
        'clock-frequency = "", "8@";',
        "interrupts = <0x0a>;",
    ):
        if required not in node:
            raise Core0Error(f"pinned UART DTS node omits `{required}`")


def _strip_lean_comments_and_strings(source: str) -> str:
    output: list[str] = []
    index = 0
    block_depth = 0
    in_string = False
    escaped = False
    while index < len(source):
        pair = source[index:index + 2]
        char = source[index]
        if block_depth:
            if pair == "/-":
                block_depth += 1
                index += 2
            elif pair == "-/":
                block_depth -= 1
                index += 2
            else:
                output.append("\n" if char == "\n" else " ")
                index += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            output.append("\n" if char == "\n" else " ")
            index += 1
            continue
        if pair == "/-":
            block_depth = 1
            output.extend((" ", " "))
            index += 2
        elif pair == "--":
            while index < len(source) and source[index] != "\n":
                output.append(" ")
                index += 1
        elif char == '"':
            in_string = True
            output.append(" ")
            index += 1
        else:
            output.append(char)
            index += 1
    if block_depth or in_string:
        raise Core0Error("device harness source has an unterminated comment/string")
    return "".join(output)


def validate_device_harness_source(source: str) -> dict[str, int]:
    """Keep UART polling/framing out of the generated machine harness."""
    code = _strip_lean_comments_and_strings(source)
    forbidden = (
        "uart", "UART", "0x10000000", "268435456", "readyByte", "sendByte",
        "responseByte", "requestMagic", "responseMagic", "putHex", "format",
        ".load .i8", ".store .i8", ".uartRead8", ".uartWrite8",
        ".uartEnableAndResetFifo",
    )
    for token in forbidden:
        if token in code:
            raise Core0Error(f"device harness contains UART/formatting token `{token}`")
    for required in (
        "namespace Lemma.Machine.DeviceHarness",
        ".abiCall",
        ".checkedResult",
        ".extractResultStatus",
        ".extractResultValue",
        "testFinisherBase",
        "core0_io_fence",
    ):
        if required not in source:
            raise Core0Error(f"device harness omits required ABI/finisher token `{required}`")
    if code.count(".store .i32") != 2:
        raise Core0Error("device harness must contain exactly two status-coded finisher stores")
    if code.count(".abiCall") != 1:
        raise Core0Error("device harness must call the compiled Action root exactly once")
    exact_instruction_counts = {
        ".extractResultStatus": 1,
        ".extractResultValue": 1,
        ".icmp": 1,
        ".branch": 1,
        ".ptrFromInt": 2,
        ".call": 4,
        ".trunc": 1,
        ".bin": 2,
        ".jump": 3,
    }
    for constructor, expected in exact_instruction_counts.items():
        if code.count(constructor) != expected:
            raise Core0Error(
                f"device harness `{constructor}` count differs: "
                f"got {code.count(constructor)}, expected {expected}"
            )
    if code.count("def main ") != 1 or code.count("def functions ") != 1:
        raise Core0Error("device harness must expose exactly one machine entry function")
    definitions = re.findall(r"^(?:private\s+)?def\s+([A-Za-z0-9_]+)\b", code, re.MULTILINE)
    if definitions != [
        "value", "int32", "int64", "entryBlock", "successBlock", "failureBlock",
        "haltBlock", "main", "functions", "declarations",
    ]:
        raise Core0Error("device harness definition closure is not the minimal entry glue")
    return {"action_calls": 1, "finisher_stores": 2, "uart_accesses": 0}


@dataclass(frozen=True)
class DeviceSite:
    site_id: int
    op: str
    function: str
    line_number: int
    access_line: str


def _nonblank_after(lines: Sequence[str], index: int, count: int) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    cursor = index + 1
    while cursor < len(lines) and len(result) < count:
        if lines[cursor].strip():
            result.append((cursor, lines[cursor]))
        cursor += 1
    return result


def _valid_access_alignment(address: int, alignment: int, *, optimized: bool) -> bool:
    if alignment == 1:
        return True
    # LLVM may strengthen a byte access's alignment after seeing a constant
    # pointer.  That does not widen the operation.  Accept only a power-of-two
    # alignment actually satisfied by the fixed address, and only post-opt.
    inferred = address & -address
    return optimized and alignment == inferred


def _access_op(line: str, *, optimized: bool = False) -> str | None:
    address_match = DIRECT_ADDRESS.search(line)
    if address_match is None:
        return None
    address = int(address_match.group(1))
    stripped = line.strip()
    load = re.fullmatch(
        r"%[-A-Za-z0-9._]+ = load volatile i8, ptr inttoptr "
        r"\(i64 [0-9]+ to ptr\), align ([0-9]+)",
        stripped,
    )
    if load and _valid_access_alignment(address, int(load.group(1)), optimized=optimized):
        if address == UART_LSR:
            return "uart.lsr.read8"
        if address == UART_RBR:
            return "uart.rbr.read8"
        return None
    store = re.fullmatch(
        r"store volatile i8 (.+), ptr inttoptr \(i64 [0-9]+ to ptr\), align ([0-9]+)",
        stripped,
    )
    if store and _valid_access_alignment(
        address, int(store.group(2)), optimized=optimized
    ):
        value = store.group(1)
        if address == UART_THR:
            return "uart.thr.write8"
        if address == UART_FCR and value == "7":
            return "uart.fcr.enable-reset"
    return None


def _line_functions(lines: Sequence[str]) -> list[str]:
    result: list[str] = []
    current = "<module>"
    for line in lines:
        match = re.match(r"^define\b.*@([-A-Za-z0-9_.$]+)\(", line)
        if match:
            current = match.group(1)
        elif line == "}":
            current = "<module>"
        result.append(current)
    return result


def _direct_physical_access_indices(lines: Sequence[str]) -> list[int]:
    return [
        index for index, line in enumerate(lines)
        if (" load " in f" {line}" or line.lstrip().startswith("store "))
        and DIRECT_ADDRESS.search(line)
    ]


def _validate_constant_pointers(
    lines: Sequence[str],
    functions: Sequence[str],
    uart_access_indices: set[int],
) -> None:
    for index, line in enumerate(lines):
        for match in CONSTANT_POINTER.finditer(line):
            address = int(match.group(1))
            if UART_BASE <= address < UART_BASE + UART_SPAN:
                if index in uart_access_indices:
                    continue
                raise Core0Error(
                    f"generic/direct UART pointer 0x{address:016x} appears outside a declared site"
                )
            if FINISHER_BASE <= address < FINISHER_BASE + FINISHER_SPAN:
                if address == FINISHER_BASE and functions[index] == "core0_main":
                    continue
                raise Core0Error(
                    f"generic/direct finisher pointer 0x{address:016x} appears outside its harness"
                )
            if any(base <= address < base + size for base, size in ORDINARY_RAM_RANGES):
                continue
            raise Core0Error(
                f"constant physical pointer 0x{address:016x} is outside the closed memory map"
            )


def _llvm_function_lines(ir: str, symbol: str) -> list[str]:
    lines = ir.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(rf"^define\b.*@{re.escape(symbol)}\(", line)
        ),
        None,
    )
    if start is None:
        raise Core0Error(f"LLVM module omits branch function `{symbol}`")
    end = next((index for index in range(start + 1, len(lines)) if lines[index] == "}"), None)
    if end is None:
        raise Core0Error(f"LLVM branch function `{symbol}` is unterminated")
    return lines[start:end + 1]


def _llvm_blocks(function: Sequence[str]) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    label_pattern = re.compile(r"^([-A-Za-z0-9_.$]+):(?:\s*;.*)?$")
    for line in function[1:-1]:
        match = label_pattern.match(line)
        if match:
            current = match.group(1)
            if current in blocks:
                raise Core0Error(f"LLVM branch function repeats block `{current}`")
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line)
        elif line.strip():
            raise Core0Error("LLVM branch function has instructions before its entry block")
    if "entry" not in blocks:
        raise Core0Error("LLVM branch function has no entry block")
    return blocks


def _block_successors(blocks: Mapping[str, Sequence[str]]) -> dict[str, set[str]]:
    successors: dict[str, set[str]] = {}
    for label, lines in blocks.items():
        targets = set(re.findall(r"\blabel %([-A-Za-z0-9_.$]+)", "\n".join(lines)))
        unknown = targets - set(blocks)
        if unknown:
            raise Core0Error(f"LLVM branch block `{label}` targets unknown blocks {sorted(unknown)}")
        successors[label] = targets
    return successors


def _reachable(successors: Mapping[str, set[str]], start: str) -> set[str]:
    pending = [start]
    seen: set[str] = set()
    while pending:
        block = pending.pop()
        if block in seen:
            continue
        seen.add(block)
        pending.extend(successors.get(block, set()) - seen)
    return seen


def _conditional_successors(
    blocks: Mapping[str, Sequence[str]],
    successors: Mapping[str, set[str]],
    marker_block: str,
    send_block: str,
) -> tuple[str, str, str, str]:
    comparisons: list[tuple[str, str, str, int]] = []
    comparison_pattern = re.compile(
        r"^\s*(%[-A-Za-z0-9._]+) = icmp eq i(?:8|32|64) "
        r"(%[-A-Za-z0-9._]+), (-?[0-9]+)\s*$"
    )
    branch_pattern = re.compile(
        r"^\s*br i1 (%[-A-Za-z0-9._]+), label %([-A-Za-z0-9_.$]+), "
        r"label %([-A-Za-z0-9_.$]+)\s*$"
    )
    branches: dict[tuple[str, str], tuple[str, str]] = {}
    for label, lines in blocks.items():
        for line in lines:
            if match := comparison_pattern.match(line):
                comparisons.append((label, match.group(1), match.group(2), int(match.group(3))))
            if match := branch_pattern.match(line):
                branches[(label, match.group(1))] = (match.group(2), match.group(3))
    candidates: list[tuple[str, str, str, str]] = []
    for zero_block, zero_condition, operand, literal in comparisons:
        if literal != 0 or (zero_block, zero_condition) not in branches:
            continue
        zero_successor, nonzero_successor = branches[(zero_block, zero_condition)]
        nonzero_reachable = _reachable(successors, nonzero_successor)
        for one_block, one_condition, one_operand, one_literal in comparisons:
            if (
                one_literal == 1
                and one_operand == operand
                and one_block in nonzero_reachable
                and (one_block, one_condition) in branches
            ):
                one_successor, default_successor = branches[(one_block, one_condition)]
                zero_reachable = _reachable(successors, zero_successor)
                one_reachable = _reachable(successors, one_successor)
                default_reachable = _reachable(successors, default_successor)
                if (
                    marker_block in zero_reachable
                    and send_block not in zero_reachable
                    and send_block in one_reachable
                    and marker_block not in one_reachable
                    and marker_block not in default_reachable
                    and send_block not in default_reachable
                ):
                    candidates.append(
                        (zero_successor, one_successor, default_successor, "conditional-branches")
                    )
    if len(candidates) != 1:
        raise Core0Error("dispatchBranch LLVM selector-0/selector-1 CFG is absent or ambiguous")
    return candidates[0]


def _selector_successors(
    blocks: Mapping[str, Sequence[str]],
    successors: Mapping[str, set[str]],
    marker_block: str,
    send_block: str,
) -> tuple[str, str, str, str]:
    switch_candidates: list[tuple[str, str, str, str]] = []
    switch_pattern = re.compile(
        r"^\s*switch i(?:8|32|64) [^,]+, label %([-A-Za-z0-9_.$]+) \[\s*$"
    )
    case_pattern = re.compile(
        r"^\s*i(?:8|32|64) (-?[0-9]+), label %([-A-Za-z0-9_.$]+)\s*$"
    )
    for lines in blocks.values():
        default: str | None = None
        cases: dict[int, str] = {}
        for line in lines:
            if match := switch_pattern.match(line):
                default = match.group(1)
            elif default is not None and (match := case_pattern.match(line)):
                cases[int(match.group(1))] = match.group(2)
        if default is not None and 0 in cases and 1 in cases:
            switch_candidates.append((cases[0], cases[1], default, "switch"))
    if switch_candidates:
        if len(switch_candidates) != 1:
            raise Core0Error("dispatchBranch LLVM contains multiple selector switches")
        return switch_candidates[0]
    return _conditional_successors(blocks, successors, marker_block, send_block)


def _validate_scratch_pointer(
    function: Sequence[str], pointer_text: str, alignment: int, *, optimized: bool
) -> None:
    direct = re.fullmatch(r"inttoptr \(i64 ([0-9]+) to ptr\)", pointer_text)
    if direct:
        address = int(direct.group(1))
        if address != BRANCH_MARKER_ADDRESS or not _valid_access_alignment(
            address, alignment, optimized=optimized
        ):
            raise Core0Error("dispatchBranch scratch access has the wrong address/alignment")
        return
    if alignment != 1 or re.fullmatch(r"%[-A-Za-z0-9._]+", pointer_text) is None:
        raise Core0Error("dispatchBranch scratch pointer/alignment is unsupported")
    pointer = re.escape(pointer_text)
    pointer_definition = next(
        (
            candidate
            for candidate in function
            if re.match(rf"^\s*{pointer} = inttoptr i64 %[-A-Za-z0-9._]+ to ptr\s*$", candidate)
        ),
        None,
    )
    if pointer_definition is None:
        raise Core0Error("dispatchBranch marker pointer has no checked address definition")
    address_match = re.search(r"inttoptr i64 (%[-A-Za-z0-9._]+) to ptr", pointer_definition)
    assert address_match is not None
    address = re.escape(address_match.group(1))
    if not any(
        re.match(rf"^\s*{address} = add i64 %[-A-Za-z0-9._]+, 64\s*$", candidate)
        for candidate in function
    ):
        raise Core0Error("dispatchBranch marker pointer is not the checked offset 64")


def _validate_marker_store(
    function: Sequence[str], line: str, *, optimized: bool, byte: int = 90
) -> None:
    store = re.fullmatch(
        rf"\s*store volatile i8 {byte}, ptr (.+), align ([0-9]+)", line
    )
    if store is None:
        raise Core0Error("dispatchBranch marker is not one volatile i8 store")
    _validate_scratch_pointer(
        function, store.group(1), int(store.group(2)), optimized=optimized
    )


def _dominators(successors: Mapping[str, set[str]]) -> dict[str, set[str]]:
    reachable = _reachable(successors, "entry")
    predecessors = {label: set() for label in successors}
    for label, targets in successors.items():
        for target in targets:
            predecessors[target].add(label)
    dominators = {
        label: ({"entry"} if label == "entry" else set(reachable))
        for label in reachable
    }
    changed = True
    while changed:
        changed = False
        for label in reachable - {"entry"}:
            incoming = predecessors[label] & reachable
            common = set.intersection(*(dominators[parent] for parent in incoming)) if incoming else set()
            updated = {label} | common
            if updated != dominators[label]:
                dominators[label] = updated
                changed = True
    return dominators


def _sentinel_dominance(
    ir: str, blocks: Mapping[str, Sequence[str]], successors: Mapping[str, set[str]],
    sentinel: str, selected: Sequence[str],
) -> str:
    dominators = _dominators(successors)
    if all(sentinel in dominators.get(target, set()) for target in selected):
        return "direct"
    # Before optimization, checked-memory failure edges meet the successful
    # store at its status phi.  Verify the sole zero predecessor is the actual
    # sentinel store and that only the status-zero continuation selects a case.
    if not re.search(
        r"define zeroext i8 @core0_scalar_0\(\)[^{]*\{\s*entry:\s*ret i8 0\s*\}", ir
    ):
        raise Core0Error("dispatchBranch Status.ok scalar definition is not exactly zero")
    for label, lines in blocks.items():
        text = "\n".join(lines)
        for phi in re.finditer(r"(%[-A-Za-z0-9._]+) = phi i8 ([^\n]+)", text):
            entry_pattern = r"\[ ([0-9]+), %([-A-Za-z0-9_.$]+) \]"
            entries = re.findall(entry_pattern, phi.group(2))
            residue = re.sub(entry_pattern, "", phi.group(2)).replace(",", "").strip()
            if residue or not entries or any(int(status) > 8 for status, _ in entries) or [
                parent for status, parent in entries if int(status) == 0
            ] != [sentinel]:
                continue
            call = re.search(r"(%[-A-Za-z0-9._]+) = call zeroext i8 @core0_scalar_0\(\)", text)
            if call is None:
                continue
            comparison = re.search(
                rf"(%[-A-Za-z0-9._]+) = icmp eq i8 {re.escape(phi.group(1))}, {re.escape(call.group(1))}",
                text,
            )
            if comparison is None:
                continue
            branch = re.search(
                rf"br i1 {re.escape(comparison.group(1))}, label %([-A-Za-z0-9_.$]+), label %([-A-Za-z0-9_.$]+)",
                text,
            )
            if branch and all(
                label in dominators.get(target, set())
                and branch.group(1) in dominators.get(target, set())
                and target not in _reachable(successors, branch.group(2))
                for target in selected
            ):
                return "checked-success"
    raise Core0Error("dispatchBranch common sentinel does not dominate successful selection")


def _validate_readback_encoding(
    function: Sequence[str], load_name: str, selector_index: int, *, optimized: bool
) -> None:
    text = "\n".join(function)
    variable = r"%[-A-Za-z0-9._]+"
    wide = re.search(rf"({variable}) = zext i8 {re.escape(load_name)} to i64", text)
    if wide is None:
        raise Core0Error("dispatchBranch readback is not zero-extended")
    source = wide.group(1)
    phi = re.search(
        rf"({variable}) = phi i64 [^\n]*\[ {re.escape(source)}, %[-A-Za-z0-9_.$]+ \]", text
    )
    checked_readback = phi is not None
    if phi is not None:
        source = phi.group(1)
    elif not optimized:
        raise Core0Error("dispatchBranch checked readback value phi is absent")
    shift = re.search(rf"({variable}) = shl(?: nuw)?(?: nsw)? i64 {re.escape(source)}, (8|{variable})\s*$", text, re.MULTILINE)
    if shift is None:
        raise Core0Error("dispatchBranch readback response has no eight-bit shift")
    if shift.group(2) != "8" and re.search(
        rf"{re.escape(shift.group(2))} = and i64 8, 63\s*$", text, re.MULTILINE
    ) is None:
        raise Core0Error("dispatchBranch readback shift count differs from eight")
    encoded = shift.group(1)
    if checked_readback:
        addition = re.search(
            rf"({variable}) = add i64 {re.escape(encoded)}, %mem\.0\.value\.[0-9]+\s*$", text, re.MULTILINE
        )
        if addition is None:
            raise Core0Error("dispatchBranch response omits its runtime selector")
        encoded = addition.group(1)
    elif selector_index == 1:
        addition = re.search(
            rf"({variable}) = (?:or(?: disjoint)?|add(?: nuw)?(?: nsw)?) i64 {re.escape(encoded)}, 1\s*$", text, re.MULTILINE
        )
        if addition is None:
            raise Core0Error("dispatchBranch true response omits selector one")
        encoded = addition.group(1)
    # O2 may merge the two response calls through a phi.  Follow only phi
    # forwarding here; unrelated arithmetic cannot masquerade as the encoding.
    forwarded = {encoded}
    changed = True
    while changed:
        changed = False
        for phi in re.finditer(rf"({variable}) = phi i64 ([^\n]+)", text):
            incoming = set(re.findall(variable, phi.group(2)))
            if incoming & forwarded and phi.group(1) not in forwarded:
                forwarded.add(phi.group(1))
                changed = True
    calls = re.findall(r"call \{ i64, i64 \} @" + re.escape(SEND_RESPONSE_SYMBOL) + r"\([^\n]+\)", text)
    if not any(any(re.search(rf", i64 {re.escape(value)}\)$", call) for value in forwarded) for call in calls):
        raise Core0Error("dispatchBranch response does not consume its actual RAM readback")


def validate_branch_ir_placement(ir: str, *, optimized: bool) -> dict[str, object]:
    function = _llvm_function_lines(ir, BRANCH_SYMBOL)
    blocks = _llvm_blocks(function)
    successors = _block_successors(blocks)
    marker_sites: list[tuple[str, str]] = []
    sentinel_sites: list[tuple[str, str]] = []
    load_sites: list[tuple[str, str, str]] = []
    send_sites: list[tuple[str, str]] = []
    send_pattern = re.compile(
        r"\bcall \{ i64, i64 \} @" + re.escape(SEND_BYTE_SYMBOL) + r"\(i8 zeroext (?:165|-91)\)"
    )
    for label, lines in blocks.items():
        for line in lines:
            if re.search(r"\bstore volatile i8 90, ptr ", line):
                marker_sites.append((label, line))
            if re.search(r"\bstore volatile i8 60, ptr ", line):
                sentinel_sites.append((label, line))
            if load := re.fullmatch(
                r"\s*(%[-A-Za-z0-9._]+) = load volatile i8, ptr (.+), align ([0-9]+)", line
            ):
                load_sites.append((label, line, load.group(1)))
            if send_pattern.search(line):
                send_sites.append((label, line))
    if len(marker_sites) != 1 or len(send_sites) != 1 or len(sentinel_sites) != 1:
        raise Core0Error(
            "dispatchBranch LLVM must contain one common sentinel, one marker store, and one sendByte(0xa5) call"
        )
    marker_block, marker_line = marker_sites[0]
    send_block, _send_line = send_sites[0]
    _validate_marker_store(function, marker_line, optimized=optimized)
    sentinel_block, sentinel_line = sentinel_sites[0]
    _validate_marker_store(function, sentinel_line, optimized=optimized, byte=60)

    zero_successor, one_successor, default_successor, dispatch = _selector_successors(
        blocks, successors, marker_block, send_block
    )
    if len({zero_successor, one_successor, default_successor}) != 3:
        raise Core0Error("dispatchBranch selectors do not have separate CFG successors")

    zero_reachable = _reachable(successors, zero_successor)
    one_reachable = _reachable(successors, one_successor)
    default_reachable = _reachable(successors, default_successor)
    if marker_block not in zero_reachable or send_block in zero_reachable:
        raise Core0Error("dispatchBranch selector 0 CFG does not exclusively own the marker store")
    if send_block not in one_reachable or marker_block in one_reachable:
        raise Core0Error("dispatchBranch selector 1 CFG does not exclusively own sendByte(0xa5)")
    if marker_block in default_reachable or send_block in default_reachable:
        raise Core0Error("dispatchBranch default CFG reaches a branch-only effect")
    dominance_kind = _sentinel_dominance(
        ir, blocks, successors, sentinel_block, (zero_successor, one_successor, default_successor)
    )
    if sentinel_block in zero_reachable or sentinel_block in one_reachable:
        raise Core0Error("dispatchBranch sentinel initialization is not common before selection")
    false_reads = [site for site in load_sites if site[0] in zero_reachable]
    true_reads = [site for site in load_sites if site[0] in one_reachable]
    if len(load_sites) != 3 or len(false_reads) != 1 or len(true_reads) != 1:
        raise Core0Error("dispatchBranch LLVM must retain one exclusive RAM readback per branch")
    if false_reads[0] in true_reads or true_reads[0] in false_reads or any(
        site[0] in default_reachable for site in false_reads + true_reads
    ):
        raise Core0Error("dispatchBranch readbacks are not branch-local")
    for selector_index, (label, line, name) in enumerate((false_reads[0], true_reads[0])):
        load = re.fullmatch(
            r"\s*%[-A-Za-z0-9._]+ = load volatile i8, ptr (.+), align ([0-9]+)", line
        )
        assert load is not None
        _validate_scratch_pointer(function, load.group(1), int(load.group(2)), optimized=optimized)
        _validate_readback_encoding(function, name, selector_index, optimized=optimized)
        effect_block = marker_block if selector_index == 0 else send_block
        if label not in _reachable(successors, effect_block):
            raise Core0Error("dispatchBranch readback precedes its designated effect")
        if label == effect_block:
            effect_line = marker_line if selector_index == 0 else send_sites[0][1]
            if blocks[label].index(effect_line) >= blocks[label].index(line):
                raise Core0Error("dispatchBranch readback appears before its designated effect")
        elif selector_index == 0:
            _sentinel_dominance(ir, blocks, successors, effect_block, (label,))
        elif effect_block not in _dominators(successors).get(label, set()):
            raise Core0Error("dispatchBranch true UART marker does not dominate its readback")
    return {
        "source_function": BRANCH_SOURCE,
        "llvm_symbol": BRANCH_SYMBOL,
        "dispatch": dispatch,
        "separate_successors": True,
        "selector_0_successor": zero_successor,
        "selector_1_successor": one_successor,
        "marker_store_block": marker_block,
        "send_byte_block": send_block,
        "exclusive_reachability": True,
        "sentinel_store_block": sentinel_block,
        "sentinel_dominates_selection": True,
        "sentinel_dominance_kind": dominance_kind,
        "selector_0_readback_block": false_reads[0][0],
        "selector_1_readback_block": true_reads[0][0],
        "branch_local_readbacks": True,
        "readbacks_encoded": True,
    }


def _coerce_ir_input(
    manifest_or_ir: Mapping[str, object] | str,
    ir: str | None,
    context: str,
) -> str:
    if ir is None:
        return _string(manifest_or_ir, context)
    validate_device_suite_manifest(_mapping(manifest_or_ir, f"{context} manifest"))
    return _string(ir, context)


def validate_device_pre_ir(
    manifest_or_ir: Mapping[str, object] | str,
    pre_ir: str | None = None,
) -> dict[str, object]:
    """Audit pre-opt IR; accepts either ``(ir)`` or ``(manifest, ir)``."""
    ir = _coerce_ir_input(manifest_or_ir, pre_ir, "pre-optimization IR")
    if ir.count("declare void @core0_io_fence(") != 1:
        raise Core0Error("pre-optimization IR must declare the IO fence exactly once")
    lines = ir.splitlines()
    functions = _line_functions(lines)
    sites: list[DeviceSite] = []
    access_indices: set[int] = set()
    for index, line in enumerate(lines):
        marker = SITE_MARKER.fullmatch(line)
        if marker is None:
            continue
        following = _nonblank_after(lines, index, 3)
        if len(following) != 3:
            raise Core0Error("UART site is truncated")
        (before_index, before), (access_index, access), (after_index, after) = following
        if FENCE_CALL.fullmatch(before) is None:
            raise Core0Error(f"UART site {marker.group(1)} lacks its immediate before-fence")
        if FENCE_CALL.fullmatch(after) is None:
            raise Core0Error(f"UART site {marker.group(1)} lacks its immediate after-fence")
        actual_op = _access_op(access)
        declared_op = marker.group(2)
        if actual_op != declared_op:
            raise Core0Error(
                f"UART site {marker.group(1)} declares `{declared_op}` but emits `{actual_op}`"
            )
        if functions[index] == "<module>" or functions[access_index] != functions[index]:
            raise Core0Error("UART site crosses or appears outside a function")
        sites.append(DeviceSite(
            site_id=int(marker.group(1)),
            op=declared_op,
            function=functions[index],
            line_number=access_index + 1,
            access_line=access.strip(),
        ))
        access_indices.add(access_index)
        # Explicit names make accidental extra instructions between the bracket visible.
        if before_index != index + 1 or access_index != index + 2 or after_index != index + 3:
            raise Core0Error(f"UART site {marker.group(1)} bracket is not contiguous")
    if [site.site_id for site in sites] != list(range(len(sites))):
        raise Core0Error("UART source-site IDs are not globally unique and dense from zero")
    if tuple(site.op for site in sites) != LOW_LEVEL_SITE_SEQUENCE:
        raise Core0Error("UART source-site operation sequence differs from the closed lowering")
    direct = set(_direct_physical_access_indices(lines))
    uart_direct = {
        index for index in direct
        if (match := DIRECT_ADDRESS.search(lines[index])) is not None
        and UART_BASE <= int(match.group(1)) < UART_BASE + UART_SPAN
    }
    if uart_direct != access_indices:
        raise Core0Error("pre-optimization IR has an unmarked or missing physical UART access")
    _validate_constant_pointers(lines, functions, uart_direct)
    branch_effects = validate_branch_ir_placement(ir, optimized=False)
    return {
        "sites": len(sites),
        "site_ids": [site.site_id for site in sites],
        "operations": [site.op for site in sites],
        "functions": sorted({site.function for site in sites}),
        "branch_effects": branch_effects,
    }


def validate_device_post_ir(
    manifest_or_ir: Mapping[str, object] | str,
    post_ir: str | None = None,
) -> dict[str, object]:
    """Audit optimized IR; accepts either ``(ir)`` or ``(manifest, ir)``."""
    ir = _coerce_ir_input(manifest_or_ir, post_ir, "optimized IR")
    if ir.count("declare void @core0_io_fence(") != 1:
        raise Core0Error("optimized IR must retain exactly one IO-fence declaration")
    lines = ir.splitlines()
    functions = _line_functions(lines)
    access_indices: list[int] = []
    operations: list[str] = []
    for index in _direct_physical_access_indices(lines):
        address_match = DIRECT_ADDRESS.search(lines[index])
        assert address_match is not None
        address = int(address_match.group(1))
        if not UART_BASE <= address < UART_BASE + UART_SPAN:
            continue
        operation = _access_op(lines[index], optimized=True)
        if operation is None:
            raise Core0Error(
                f"optimized UART access at line {index + 1} is not volatile i8 align 1"
            )
        previous = index - 1
        following = index + 1
        if previous < 0 or FENCE_CALL.fullmatch(lines[previous]) is None:
            raise Core0Error(f"optimized UART access at line {index + 1} lacks before-fence")
        if following >= len(lines) or FENCE_CALL.fullmatch(lines[following]) is None:
            raise Core0Error(f"optimized UART access at line {index + 1} lacks after-fence")
        access_indices.append(index)
        operations.append(operation)
    if tuple(operations) != LOW_LEVEL_SITE_SEQUENCE:
        raise Core0Error("optimized IR changed, removed, duplicated, or reordered UART operations")
    _validate_constant_pointers(lines, functions, set(access_indices))
    if "lemma.uart-site=" in ir:
        raise Core0Error("optimized IR unexpectedly retained source-only UART site metadata")
    branch_effects = validate_branch_ir_placement(ir, optimized=True)
    return {
        "accesses": len(operations),
        "operations": operations,
        "branch_effects": branch_effects,
    }


def validate_device_ir(pre_ir: str, post_ir: str) -> dict[str, object]:
    pre = validate_device_pre_ir(pre_ir)
    post = validate_device_post_ir(post_ir)
    if pre["operations"] != post["operations"]:
        raise Core0Error("pre/post optimization UART operation sequences differ")
    return {"pre": pre, "post": post}


@dataclass(frozen=True)
class AuditMutation:
    name: str
    category: str
    manifest: dict[str, object] | None = None
    pre_ir: str | None = None
    post_ir: str | None = None


def manifest_mutations(manifest: Mapping[str, object]) -> list[AuditMutation]:
    duplicate = copy.deepcopy(dict(manifest))
    duplicate_ops = _list(duplicate["used_device_ops"], "mutated device operations")
    duplicate_ops.append(copy.deepcopy(duplicate_ops[0]))

    stale = copy.deepcopy(dict(manifest))
    functions = _list(stale["action_functions"], "mutated Action functions")
    target = next(
        _mapping(function, "mutated Action function")
        for function in functions
        if _mapping(function, "mutated Action function").get("source")
        == "Lemma.Platform.LemmaVM.ConsoleDevice.transmitPollStep"
    )
    target["transitive_effects"] = ["mmio-read", "mmio-write"]

    wrong_address = copy.deepcopy(dict(manifest))
    operations = _list(wrong_address["used_device_ops"], "mutated device operations")
    status = next(
        _mapping(operation, "mutated device operation")
        for operation in operations
        if _mapping(operation, "mutated device operation").get("stable_id")
        == "uart.read-status"
    )
    status["address"] = "0x0000000010000004"

    misplaced_branch = copy.deepcopy(dict(manifest))
    branch_functions = _list(
        misplaced_branch["action_functions"], "mutated Action functions"
    )
    branch = next(
        _mapping(function, "mutated Action function")
        for function in branch_functions
        if _mapping(function, "mutated Action function").get("source") == BRANCH_SOURCE
    )
    body = _string(branch.get("body"), "mutated dispatchBranch body")
    zero = "(cmp eq u64 (var 2 u64) (lit u64 0))"
    one = "(cmp eq u64 (var 2 u64) (lit u64 1))"
    if body.count(zero) != 1 or body.count(one) != 1:
        raise Core0Error("cannot construct branch-placement mutation from unknown source")
    branch["body"] = body.replace(zero, "__selector_zero__", 1).replace(
        one, zero, 1
    ).replace("__selector_zero__", one, 1)

    return [
        AuditMutation("duplicate-device-op", "manifest", manifest=duplicate),
        AuditMutation("stale-transitive-effects", "effects", manifest=stale),
        AuditMutation("wrong-manifest-device-address", "manifest", manifest=wrong_address),
        AuditMutation("misplaced-branch-effects", "branch-effects", manifest=misplaced_branch),
    ]


def _replace_once(text: str, old: str, new: str, name: str) -> str:
    if text.count(old) < 1:
        raise Core0Error(f"cannot construct `{name}` mutation: anchor is absent")
    return text.replace(old, new, 1)


def _misplace_branch_effects(ir: str, *, optimized: bool, name: str) -> str:
    report = validate_branch_ir_placement(ir, optimized=optimized)
    function_text = "\n".join(_llvm_function_lines(ir, BRANCH_SYMBOL))
    zero = _string(report.get("selector_0_successor"), f"{name} selector 0")
    one = _string(report.get("selector_1_successor"), f"{name} selector 1")
    if report.get("dispatch") == "switch":
        zero_case = f"i8 0, label %{zero}"
        one_case = f"i8 1, label %{one}"
        if function_text.count(zero_case) != 1 or function_text.count(one_case) != 1:
            raise Core0Error(f"cannot construct `{name}` from unknown switch spelling")
        mutated = function_text.replace(
            zero_case, "i8 0, label %__branch_swap__", 1
        ).replace(
            one_case, f"i8 1, label %{zero}", 1
        ).replace("i8 0, label %__branch_swap__", f"i8 0, label %{one}", 1)
        return ir.replace(function_text, mutated, 1)
    branch_pattern = re.compile(
        rf"^(\s*br i1 %[-A-Za-z0-9._]+, label %){re.escape(zero)}"
        rf"(, label %)([-A-Za-z0-9_.$]+)\s*$",
        re.MULTILINE,
    )
    matches = list(branch_pattern.finditer(function_text))
    if len(matches) != 1:
        raise Core0Error(f"cannot construct `{name}` from unknown conditional spelling")
    match = matches[0]
    replacement = (
        match.group(1) + match.group(3) + match.group(2) + zero
    )
    mutated = function_text[:match.start()] + replacement + function_text[match.end():]
    return ir.replace(function_text, mutated, 1)


def ir_mutations(pre_ir: str, post_ir: str | None = None) -> list[AuditMutation]:
    marker = "  ; lemma.uart-site=0;op=uart.lsr.read8\n"
    fenced_load = (
        "  call void @core0_io_fence()\n"
        "  %uart.lsr.byte.0 = load volatile i8, ptr inttoptr "
        "(i64 268435461 to ptr), align 1\n"
        "  call void @core0_io_fence()\n"
    )
    if marker + fenced_load not in pre_ir:
        raise Core0Error("cannot construct UART mutations from an unknown pre-IR spelling")
    wrong_address = _replace_once(
        pre_ir, "i64 268435461 to ptr", "i64 268435460 to ptr", "wrong-device-address"
    )
    wrong_width = _replace_once(
        pre_ir, "load volatile i8, ptr inttoptr", "load volatile i16, ptr inttoptr",
        "wrong-device-width",
    )
    nonvolatile = _replace_once(
        pre_ir, "load volatile i8, ptr inttoptr", "load i8, ptr inttoptr",
        "nonvolatile-device-access",
    )
    missing_fence = _replace_once(
        pre_ir, marker + "  call void @core0_io_fence()\n", marker,
        "missing-before-fence",
    )
    reordered = _replace_once(
        pre_ir,
        marker + fenced_load,
        marker
        + "  %uart.lsr.byte.0 = load volatile i8, ptr inttoptr "
          "(i64 268435461 to ptr), align 1\n"
        + "  call void @core0_io_fence()\n"
        + "  call void @core0_io_fence()\n",
        "reordered-before-fence",
    )
    duplicate_site = _replace_once(
        pre_ir, "lemma.uart-site=1;op=uart.thr.write8",
        "lemma.uart-site=0;op=uart.thr.write8", "duplicate-site-id",
    )
    duplicate_physical = _replace_once(
        pre_ir,
        marker + fenced_load,
        marker + fenced_load
        + fenced_load.replace("%uart.lsr.byte.0", "%uart.lsr.byte.duplicate"),
        "duplicate-physical-device-operation",
    )
    misplaced_branch = _misplace_branch_effects(
        pre_ir, optimized=False, name="misplaced-pre-branch-effects"
    )
    mutations = [
        AuditMutation("wrong-device-address", "pre-ir", pre_ir=wrong_address),
        AuditMutation("wrong-device-width", "pre-ir", pre_ir=wrong_width),
        AuditMutation("nonvolatile-device-access", "pre-ir", pre_ir=nonvolatile),
        AuditMutation("missing-before-fence", "pre-ir", pre_ir=missing_fence),
        AuditMutation("reordered-before-fence", "pre-ir", pre_ir=reordered),
        AuditMutation("duplicate-site-id", "pre-ir", pre_ir=duplicate_site),
        AuditMutation(
            "duplicate-physical-device-operation", "pre-ir", pre_ir=duplicate_physical
        ),
        AuditMutation(
            "misplaced-pre-branch-effects", "branch-effects", pre_ir=misplaced_branch
        ),
    ]
    if post_ir is None:
        return mutations

    post_wrong_address = _replace_once(
        post_ir, "i64 268435461 to ptr", "i64 268435460 to ptr",
        "optimized-wrong-device-address",
    )
    post_nonvolatile = _replace_once(
        post_ir, "load volatile i8, ptr inttoptr", "load i8, ptr inttoptr",
        "optimized-nonvolatile-device-access",
    )
    post_missing_fence = _replace_once(
        post_ir,
        "  call void @core0_io_fence()\n"
        "  %uart.lsr.byte.0 = load volatile i8, ptr inttoptr",
        "  %uart.lsr.byte.0 = load volatile i8, ptr inttoptr",
        "optimized-missing-before-fence",
    )
    post_invalid_alignment = _replace_once(
        post_ir,
        "i64 268435461 to ptr), align 1",
        "i64 268435461 to ptr), align 2",
        "optimized-invalid-device-alignment",
    )
    post_duplicate_physical = _replace_once(
        post_ir,
        fenced_load,
        fenced_load
        + fenced_load.replace("%uart.lsr.byte.0", "%uart.lsr.byte.duplicate"),
        "optimized-duplicate-physical-device-operation",
    )
    post_misplaced_branch = _misplace_branch_effects(
        post_ir, optimized=True, name="misplaced-post-branch-effects"
    )
    mutations.extend([
        AuditMutation(
            "optimized-wrong-device-address", "post-ir", post_ir=post_wrong_address
        ),
        AuditMutation(
            "optimized-nonvolatile-device-access", "post-ir", post_ir=post_nonvolatile
        ),
        AuditMutation(
            "optimized-missing-before-fence", "post-ir", post_ir=post_missing_fence
        ),
        AuditMutation(
            "optimized-invalid-device-alignment", "post-ir",
            post_ir=post_invalid_alignment,
        ),
        AuditMutation(
            "optimized-duplicate-physical-device-operation", "post-ir",
            post_ir=post_duplicate_physical,
        ),
        AuditMutation(
            "misplaced-post-branch-effects", "branch-effects",
            post_ir=post_misplaced_branch,
        ),
    ])
    return mutations


def audit_mutation_matrix(
    manifest: Mapping[str, object],
    pre_ir: str,
    post_ir: str | None = None,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for mutation in manifest_mutations(manifest):
        assert mutation.manifest is not None
        try:
            validate_device_suite_manifest(mutation.manifest)
        except Core0Error as error:
            records.append({
                "name": mutation.name,
                "category": mutation.category,
                "diagnostic": str(error),
            })
        else:
            raise Core0Error(f"device manifest mutation `{mutation.name}` escaped detection")
    for mutation in ir_mutations(pre_ir, post_ir):
        try:
            if mutation.pre_ir is not None:
                validate_device_pre_ir(mutation.pre_ir)
            elif mutation.post_ir is not None:
                validate_device_post_ir(mutation.post_ir)
            else:
                raise AssertionError("IR mutation has no payload")
        except Core0Error as error:
            records.append({
                "name": mutation.name,
                "category": mutation.category,
                "diagnostic": str(error),
            })
        else:
            raise Core0Error(f"device IR mutation `{mutation.name}` escaped detection")
    return records


def audit_device_directory(directory: Path, root: Path | None = None) -> dict[str, object]:
    root = repo_root() if root is None else root.resolve()
    directory = directory.resolve()
    required = (
        "device-suite-manifest.json", "device-suite-normalized.txt",
        "device-test-abi.json", "device-contract.json", "program.ll",
        "program.opt.ll", "platform.dtb", "platform.dts",
    )
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise Core0Error(f"device audit directory is missing artifacts: {missing}")
    manifest = _mapping(load_json(directory / "device-suite-manifest.json"), "manifest")
    normalized = (directory / "device-suite-normalized.txt").read_text(encoding="utf-8")
    abi = _mapping(load_json(directory / "device-test-abi.json"), "device ABI")
    contract = _mapping(load_json(directory / "device-contract.json"), "device contract")
    if manifest.get("device_contract") != contract:
        raise Core0Error("standalone and embedded device contracts differ")
    manifest_report = validate_device_suite_manifest(manifest, normalized=normalized)
    abi_report = validate_device_abi(abi, manifest)
    contract_report = validate_device_contract(contract)
    ir_report = validate_device_ir(
        (directory / "program.ll").read_text(encoding="utf-8"),
        (directory / "program.opt.ll").read_text(encoding="utf-8"),
    )
    harness_report = validate_device_harness_source(
        (root / "Lemma/Machine/DeviceHarness.lean").read_text(encoding="utf-8")
    )
    validate_platform_evidence(
        sha256(directory / "platform.dtb"),
        (directory / "platform.dts").read_text(encoding="utf-8"),
    )
    validate_toolchain_lock(_mapping(load_json(root / "tooling/toolchain-lock.json"), "lock"))
    branch_effects = {
        "source_function": BRANCH_SOURCE,
        "llvm_symbol": BRANCH_SYMBOL,
        "selector_0": {
            "scratch_offset": 64,
            "stored_byte": 90,
            "send_byte_0xa5": False,
        },
        "selector_1": {
            "scratch_marker_store": False,
            "sent_byte": 165,
        },
        "readback": dict(BRANCH_READBACK),
        "source": manifest_report["branch_effects"],
        "pre_ir": ir_report["pre"]["branch_effects"],
        "post_ir": ir_report["post"]["branch_effects"],
    }
    return {
        "manifest": manifest_report,
        "abi": abi_report,
        "contract": contract_report,
        "ir": ir_report,
        "harness": harness_report,
        "branch_effects": branch_effects,
        "platform_dtb_sha256": PINNED_DTB_SHA256,
    }


def audit_device_artifacts(
    directory: Path, root: Path | None = None
) -> dict[str, object]:
    """Stable integration alias for auditing one complete device build."""
    return audit_device_directory(directory, root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    ns = parser.parse_args()
    try:
        report = audit_device_directory(ns.directory)
    except (Core0Error, OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        print(f"DEVICE AUDIT FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
