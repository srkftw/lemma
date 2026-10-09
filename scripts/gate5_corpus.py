#!/usr/bin/env python3
"""Closed deterministic Gate 5 checked-memory corpus and independent model."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import run_memory_case
from core0_common import Core0Error


SCHEMA_VERSION = 1
PROFILE = run_memory_case.PROFILE
TEST_ABI = run_memory_case.TEST_ABI
RESULT_TAG = run_memory_case.RESULT_TAG
BASE = "Lemma.Examples.Foundation.Memory"
DEFAULT_SOURCE_SEED = 0x4C454D4D41353035
DEFAULT_RUNTIME_SEED = 0x52554E54494D4535
U64_MASK = (1 << 64) - 1

STATUS_NAMES = {
    0: "ok",
    1: "unknown-region",
    2: "reserved-region",
    3: "device-region",
    4: "read-denied",
    5: "write-denied",
    6: "width-denied",
    7: "out-of-bounds",
    8: "misaligned",
    9: "budget-exceeded",
}


class CorpusError(Core0Error):
    pass


@dataclass(frozen=True)
class RootSpec:
    leaf: str
    args: tuple[str, ...]
    operation: str
    covers: tuple[str, ...]

    @property
    def name(self) -> str:
        return f"{BASE}.{self.leaf}"

    @property
    def signature(self) -> dict[str, object]:
        return {"args": list(self.args), "result": RESULT_TAG}


ROOT_SPECS = (
    RootSpec("load8Value", ("u8", "u64"), "load8", ("read", "width-1")),
    RootSpec("load32Value", ("u8", "u64"), "load32", ("read", "width-4", "little-endian")),
    RootSpec("load64Value", ("u8", "u64"), "load64", ("read", "width-8", "little-endian")),
    RootSpec("store8Status", ("u8", "u64", "u8"), "store8", ("write", "width-1")),
    RootSpec("store32Status", ("u8", "u64", "u32"), "store32", ("write", "width-4")),
    RootSpec("store64Status", ("u8", "u64", "u64"), "store64", ("write", "width-8")),
    RootSpec("roundTrip8", ("u8", "u64", "u8"), "roundtrip8", ("round-trip", "width-1")),
    RootSpec("roundTrip32", ("u8", "u64", "u32"), "roundtrip32", ("round-trip", "width-4")),
    RootSpec("roundTrip64", ("u8", "u64", "u64"), "roundtrip64", ("round-trip", "width-8")),
    RootSpec("eventWidth", ("bool", "u64", "u64"), "event-width", ("permitted-widths", "event-buffer")),
    RootSpec("overlapLow32", ("u8", "u64", "u64"), "overlap-low", ("overlap", "little-endian")),
    RootSpec("overlapHigh32", ("u8", "u64", "u64"), "overlap-high", ("overlap", "little-endian")),
    RootSpec("overlapByte", ("u8", "u64", "u32"), "overlap-byte", ("overlap", "edge-bytes")),
    RootSpec("readRange", ("u8", "u64", "u64"), "read-range", ("overflow-safe-range",)),
    RootSpec("writeRange", ("u8", "u64", "u64"), "write-range", ("overflow-safe-range",)),
    RootSpec("overflowBounds", ("bool", "u8", "u64", "u64"), "overflow", ("u64-maximum", "no-wrapped-address")),
    RootSpec("alignment", ("bool", "u8", "u64"), "alignment", ("natural-alignment",)),
    RootSpec("reservedDenied", ("bool", "u8", "u64"), "reserved", ("image-denied", "stack-denied")),
    RootSpec("deviceDenied", ("bool", "u8", "u64"), "device", ("mmio-excluded",)),
    RootSpec("unknownDenied", ("u8", "u64"), "unknown", ("forged-region-id",)),
    RootSpec(
        "helperCopyNonOverlap",
        ("u8", "u64", "u8", "u64"),
        "helper-copy",
        ("transitive-effects", "nonoverlap-copy"),
    ),
    RootSpec("branchWrite", ("bool", "u64", "u8"), "branch-write", ("chosen-branch-effect",)),
    RootSpec("foldWrite", ("u32", "u64", "u8"), "fold-write", ("effectful-fold", "budget-16")),
    RootSpec("bufferFill", ("u8", "u64", "u32", "u8"), "fill", ("source-buffer-fill",)),
    RootSpec("byteChecksum", ("u8", "u64", "u32"), "checksum", ("source-byte-checksum",)),
    RootSpec(
        "overlapCopy",
        ("u8", "u64", "u8", "u64", "u32"),
        "overlap-copy",
        ("source-memmove", "both-directions"),
    ),
)

# Root 13 deliberately has one compound byte-edge case; root 23 has three cases
# for zero, exact-budget, and exhausted iteration.  All others have two.
CASE_ARGUMENTS: tuple[tuple[tuple[int, ...], ...], ...] = (
    ((1, 0), (1, 0xFFF)),
    ((1, 0), (1, 0xFFC)),
    ((1, 0), (2, 0xFF8)),
    ((1, 0x20, 0xA5), (2, 0x300, 0x5A)),
    ((1, 0x24, 0x89ABCDEF), (1, 1, 0x11223344)),
    ((1, 0x28, 0x0123456789ABCDEF), (1, 0xFF9, 0xFEDCBA9876543210)),
    ((1, 0x30, 0xD3), (3, 0xFFF, 0x7E)),
    ((3, 0x40, 0xDEADBEEF), (3, 0xFFC, 0x10203040)),
    ((3, 0x48, 0x1122334455667788), (4, 0x20, 0xFEDCBA9876543210)),
    ((0, 0x28, 0xAABBCCDD), (1, 0x2C, 0x5A)),
    ((1, 0x50, 0x1122334455667788), (3, 0x50, 0xFEDCBA9876543210)),
    ((1, 0x58, 0x1122334455667788), (3, 0x58, 0xFEDCBA9876543210)),
    ((1, 0x60, 0xA1B2C3D4),),
    ((1, 0xFF8, 8), (1, 0xFF9, 8)),
    ((3, 0xFFF, 1), (2, 0x100, 1)),
    ((0, 1, U64_MASK, 0), (1, 3, U64_MASK, 0x0123456789ABCDEF)),
    ((0, 1, 2), (1, 3, 4)),
    ((0, 0x70, 0x7EFFF0), (1, 0x71, 0)),
    ((0, 0x80, 0), (1, 0x81, 0)),
    ((0, 0), (0xFF, U64_MASK)),
    ((1, 0x100, 1, 0x180), (2, 0x300, 3, 0x100)),
    ((1, 0x200, 0x5A), (0, 0x200, 0xA5)),
    ((0, 0x240, 0x10), (16, 0x240, 0xF8), (17, 0x240, 0x20)),
    ((1, 0x300, 32, 0x3C), (1, 0xFFA, 8, 0x77)),
    ((1, 0, 0), (2, 0x300, 64)),
    ((1, 0x400, 1, 0x408, 16), (1, 0x408, 1, 0x400, 16)),
)

TARGET_CASE_COUNT = sum(len(group) for group in CASE_ARGUMENTS)
assert len(ROOT_SPECS) == 26
assert len(CASE_ARGUMENTS) == len(ROOT_SPECS)
assert TARGET_CASE_COUNT == 52


@dataclass(frozen=True)
class MemoryEvent:
    kind: str
    region: int
    offset: int
    width: int
    value: int


@dataclass(frozen=True)
class ModelOutcome:
    status: int
    value: int


class FiniteMemory:
    def __init__(self, descriptor: run_memory_case.MemoryCaseDescriptor):
        self.descriptor = descriptor
        self.memory = {
            region_id: bytearray(run_memory_case.initial_region_bytes(descriptor, region_id))
            for region_id in (1, 2, 3, 4)
        }
        self.events: list[MemoryEvent] = []

    def _status(self, region: int, offset: int, width: int, write: bool) -> int:
        spec = run_memory_case.REGIONS_BY_ID.get(region)
        if spec is None:
            return 1
        kind = spec["kind"]
        if kind == "reserved":
            return 2
        if kind == "device":
            return 3
        if write and not spec["writable"]:
            return 5
        if not write and not spec["readable"]:
            return 4
        if width not in spec["widths"]:
            return 6
        length = int(spec["length"])
        # Width is validated before subtraction; offset is compared to the
        # remaining length, never added to width.
        if width > length or offset > length - width:
            return 7
        if offset % width != 0:
            return 8
        return 0

    def load(self, region: int, offset: int, width: int) -> ModelOutcome:
        status = self._status(region, offset, width, False)
        value = 0
        if status == 0:
            value = int.from_bytes(self.memory[region][offset : offset + width], "little")
            self.events.append(MemoryEvent("read", region, offset, width, value))
        return ModelOutcome(status, value)

    def store(self, region: int, offset: int, width: int, value: int) -> ModelOutcome:
        status = self._status(region, offset, width, True)
        masked = value & ((1 << (width * 8)) - 1)
        if status == 0:
            self.memory[region][offset : offset + width] = masked.to_bytes(width, "little")
            self.events.append(MemoryEvent("write", region, offset, width, masked))
        return ModelOutcome(status, 0)

    def check_range(self, region: int, offset: int, length: int, write: bool) -> int:
        spec = run_memory_case.REGIONS_BY_ID.get(region)
        if spec is None:
            status = 1
        elif spec["kind"] == "reserved":
            status = 2
        elif spec["kind"] == "device":
            status = 3
        elif write and not spec["writable"]:
            status = 5
        elif not write and not spec["readable"]:
            status = 4
        else:
            region_length = int(spec["length"])
            status = 7 if length > region_length or offset > region_length - length else 0
        return status

    def digest(self) -> str:
        hasher = hashlib.sha256()
        for region_id in (1, 2, 3, 4):
            hasher.update(bytes([region_id]))
            hasher.update(self.memory[region_id])
        return hasher.hexdigest()


def _sum(values: list[int]) -> int:
    return sum(values) & U64_MASK


def _copy(
    memory: FiniteMemory,
    source_region: int,
    source_offset: int,
    destination_region: int,
    destination_offset: int,
    count: int,
) -> ModelOutcome:
    status = memory.check_range(source_region, source_offset, count, False)
    if status != 0:
        return ModelOutcome(status, 0)
    status = memory.check_range(destination_region, destination_offset, count, True)
    if status != 0:
        return ModelOutcome(status, 0)
    backwards = (
        source_region == destination_region
        and destination_offset > source_offset
        and destination_offset < source_offset + count
    )
    indices = range(count - 1, -1, -1) if backwards else range(count)
    copied: list[int] = [0] * count
    accumulator = 0
    for index in indices:
        loaded = memory.load(source_region, source_offset + index, 1)
        if loaded.status != 0:
            return ModelOutcome(loaded.status, accumulator)
        stored = memory.store(destination_region, destination_offset + index, 1, loaded.value)
        if stored.status != 0:
            return ModelOutcome(stored.status, accumulator)
        copied[index] = loaded.value
        accumulator = (accumulator + loaded.value) & U64_MASK
    return ModelOutcome(0, _sum(copied))


def evaluate(
    spec: RootSpec, descriptor: run_memory_case.MemoryCaseDescriptor
) -> tuple[ModelOutcome, FiniteMemory]:
    memory = FiniteMemory(descriptor)
    args = descriptor.args
    op = spec.operation
    if op.startswith("load") and op in {"load8", "load32", "load64"}:
        width = {"load8": 1, "load32": 4, "load64": 8}[op]
        outcome = memory.load(args[0], args[1], width)
    elif op.startswith("store") and op in {"store8", "store32", "store64"}:
        width = {"store8": 1, "store32": 4, "store64": 8}[op]
        outcome = memory.store(args[0], args[1], width, args[2])
    elif op.startswith("roundtrip"):
        width = {"roundtrip8": 1, "roundtrip32": 4, "roundtrip64": 8}[op]
        stored = memory.store(args[0], args[1], width, args[2])
        outcome = stored if stored.status != 0 else memory.load(args[0], args[1], width)
    elif op == "event-width":
        use_byte, offset, value = args
        outcome = memory.store(4, offset, 1 if use_byte else 4, value)
    elif op in {"overlap-low", "overlap-high"}:
        region, offset, value = args
        stored = memory.store(region, offset, 8, value)
        delta = 0 if op == "overlap-low" else 4
        outcome = stored if stored.status != 0 else memory.load(region, offset + delta, 4)
    elif op == "overlap-byte":
        region, offset, value = args
        stored = memory.store(region, offset, 4, value)
        if stored.status != 0:
            outcome = stored
        else:
            first = memory.load(region, offset, 1)
            last = memory.load(region, offset + 3, 1)
            outcome = (
                first
                if first.status != 0
                else last
                if last.status != 0
                else ModelOutcome(0, first.value | (last.value << 8))
            )
    elif op in {"read-range", "write-range"}:
        status = memory.check_range(args[0], args[1], args[2], op == "write-range")
        outcome = ModelOutcome(status, 0)
    elif op == "overflow":
        write, region, offset, value = args
        outcome = memory.store(region, offset, 8, value) if write else memory.load(region, offset, 1)
    elif op == "alignment":
        wide, region, offset = args
        outcome = memory.load(region, offset, 8 if wide else 4)
    elif op in {"reserved", "device"}:
        write, region, offset = args
        outcome = (
            memory.store(region, offset, 1, 0xAA if op == "reserved" else 0x55)
            if write
            else memory.load(region, offset, 1)
        )
    elif op == "unknown":
        outcome = memory.load(args[0], args[1], 1)
    elif op == "helper-copy":
        outcome = _copy(memory, args[0], args[1], args[2], args[3], 16)
    elif op == "branch-write":
        to_scratch, offset, value = args
        stored = memory.store(1 if to_scratch else 3, offset, 1, value)
        outcome = stored if stored.status != 0 else ModelOutcome(0, value)
    elif op == "fold-write":
        count, offset, value = args
        if count > 16:
            outcome = ModelOutcome(9, 0)
        else:
            values: list[int] = []
            outcome = ModelOutcome(0, 0)
            for index in range(count):
                byte = (value + index) & 0xFF
                stored = memory.store(1, offset + index, 1, byte)
                if stored.status != 0:
                    outcome = ModelOutcome(stored.status, _sum(values))
                    break
                values.append(byte)
            else:
                outcome = ModelOutcome(0, _sum(values))
    elif op == "fill":
        region, offset, count, value = args
        status = memory.check_range(region, offset, count, True)
        if status != 0:
            outcome = ModelOutcome(status, 0)
        elif count > 256:
            outcome = ModelOutcome(9, 0)
        else:
            accumulator = 0
            outcome = ModelOutcome(0, 0)
            for index in range(count):
                stored = memory.store(region, offset + index, 1, value)
                if stored.status != 0:
                    outcome = ModelOutcome(stored.status, accumulator)
                    break
                accumulator = (accumulator + value) & U64_MASK
            else:
                outcome = ModelOutcome(0, accumulator)
    elif op == "checksum":
        region, offset, count = args
        status = memory.check_range(region, offset, count, False)
        if status != 0:
            outcome = ModelOutcome(status, 0)
        elif count > 256:
            outcome = ModelOutcome(9, 0)
        else:
            values = []
            outcome = ModelOutcome(0, 0)
            for index in range(count):
                loaded = memory.load(region, offset + index, 1)
                if loaded.status != 0:
                    outcome = ModelOutcome(loaded.status, _sum(values))
                    break
                values.append(loaded.value)
            else:
                outcome = ModelOutcome(0, _sum(values))
    elif op == "overlap-copy":
        source_region, source_offset, destination_region, destination_offset, count = args
        read_status = memory.check_range(source_region, source_offset, count, False)
        if read_status != 0:
            outcome = ModelOutcome(read_status, 0)
        else:
            write_status = memory.check_range(destination_region, destination_offset, count, True)
            if write_status != 0:
                outcome = ModelOutcome(write_status, 0)
            elif count > 256:
                outcome = ModelOutcome(9, 0)
            else:
                # `_copy` repeats the pure preflights, which emit no events and
                # therefore leave the observable source semantics unchanged.
                outcome = _copy(
                    memory,
                    source_region,
                    source_offset,
                    destination_region,
                    destination_offset,
                    count,
                )
    else:
        raise CorpusError(f"unimplemented independent model operation: {op}")
    return outcome, memory


def _event_digest(events: list[MemoryEvent]) -> str:
    payload = json.dumps(
        [asdict(event) for event in events], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _suite_id(source_seed: int, runtime_seed: int) -> int:
    catalog = [
        {
            "name": spec.name,
            "signature": spec.signature,
            "operation": spec.operation,
            "covers": list(spec.covers),
            "arguments": [list(values) for values in CASE_ARGUMENTS[index]],
        }
        for index, spec in enumerate(ROOT_SPECS)
    ]
    payload = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "profile": PROFILE,
            "test_abi": TEST_ABI,
            "source_seed": source_seed,
            "runtime_seed": runtime_seed,
            "catalog": catalog,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")


def _descriptor(
    *,
    suite_id: int,
    case_id: int,
    root_id: int,
    spec: RootSpec,
    args: tuple[int, ...],
    source_seed: int,
    runtime_seed: int,
) -> run_memory_case.MemoryCaseDescriptor:
    return run_memory_case.MemoryCaseDescriptor(
        suite_id=suite_id,
        case_id=case_id,
        root=spec.name,
        root_id=root_id,
        signature=run_memory_case.MemorySignature(spec.args),
        source_seed=source_seed,
        runtime_seed=runtime_seed,
        args=args,
    )


def build_corpus(
    *, source_seed: int = DEFAULT_SOURCE_SEED, runtime_seed: int = DEFAULT_RUNTIME_SEED
) -> dict[str, object]:
    for label, value in (("source", source_seed), ("runtime", runtime_seed)):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MASK:
            raise CorpusError(f"{label} seed is outside UInt64")
    suite_id = _suite_id(source_seed, runtime_seed)
    cases: list[dict[str, object]] = []
    case_id = 1
    for root_id, (spec, vectors) in enumerate(zip(ROOT_SPECS, CASE_ARGUMENTS, strict=True), 1):
        for args in vectors:
            descriptor = _descriptor(
                suite_id=suite_id,
                case_id=case_id,
                root_id=root_id,
                spec=spec,
                args=args,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
            )
            run_memory_case.validate_descriptor(descriptor)
            outcome, model = evaluate(spec, descriptor)
            cases.append(
                {
                    "case_id": f"0x{case_id:016x}",
                    "root": spec.name,
                    "root_id": root_id,
                    "signature": spec.signature,
                    "args": [
                        {"type": ty, "value": f"0x{value:016x}"}
                        for ty, value in zip(spec.args, args, strict=True)
                    ],
                    "expected": {
                        "status": outcome.status,
                        "status_name": STATUS_NAMES[outcome.status],
                        "value": f"0x{outcome.value:016x}",
                        "event_count": len(model.events),
                        "event_sha256": _event_digest(model.events),
                        "final_memory_sha256": model.digest(),
                    },
                    "events": [asdict(event) for event in model.events],
                    "covers": [*spec.covers, STATUS_NAMES[outcome.status]],
                }
            )
            case_id += 1
    corpus: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "test_abi": TEST_ABI,
        "result_tag": RESULT_TAG,
        "suite_id": f"0x{suite_id:016x}",
        "source_seed": f"0x{source_seed:016x}",
        "runtime_seed": f"0x{runtime_seed:016x}",
        "root_count": len(ROOT_SPECS),
        "case_count": len(cases),
        "fresh_boots_per_profile": len(cases),
        "memory_contract": run_memory_case.expected_memory_contract(),
        "status_codes": [
            {"code": code, "name": name} for code, name in STATUS_NAMES.items()
        ],
        "roots": [
            {
                "root_id": index,
                "name": spec.name,
                "signature": spec.signature,
                "operation": spec.operation,
                "case_count": len(CASE_ARGUMENTS[index - 1]),
                "covers": list(spec.covers),
            }
            for index, spec in enumerate(ROOT_SPECS, 1)
        ],
        "cases": cases,
    }
    validate_corpus(corpus)
    return corpus


def _parse_hex(value: object, context: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0x[0-9a-f]{16}", value) is None:
        raise CorpusError(f"{context} is not canonical UInt64")
    return int(value, 16)


def validate_corpus(value: object) -> None:
    if not isinstance(value, dict):
        raise CorpusError("Gate 5 corpus is not an object")
    _expected_keys = {
        "schema_version",
        "profile",
        "test_abi",
        "result_tag",
        "suite_id",
        "source_seed",
        "runtime_seed",
        "root_count",
        "case_count",
        "fresh_boots_per_profile",
        "memory_contract",
        "status_codes",
        "roots",
        "cases",
    }
    if set(value) != _expected_keys:
        raise CorpusError("Gate 5 corpus fields differ from the closed schema")
    if (
        value.get("schema_version") != 1
        or value.get("profile") != PROFILE
        or value.get("test_abi") != TEST_ABI
        or value.get("result_tag") != RESULT_TAG
    ):
        raise CorpusError("Gate 5 corpus has the wrong schema/profile/ABI")
    source_seed = _parse_hex(value.get("source_seed"), "source_seed")
    runtime_seed = _parse_hex(value.get("runtime_seed"), "runtime_seed")
    suite_id = _parse_hex(value.get("suite_id"), "suite_id")
    if suite_id != _suite_id(source_seed, runtime_seed):
        raise CorpusError("Gate 5 suite ID is stale or inconsistent")
    if value.get("memory_contract") != run_memory_case.expected_memory_contract():
        raise CorpusError("Gate 5 corpus memory contract differs from the fixed layout")
    if value.get("status_codes") != [
        {"code": code, "name": name} for code, name in STATUS_NAMES.items()
    ]:
        raise CorpusError("Gate 5 status catalog differs")
    roots = value.get("roots")
    if not isinstance(roots, list) or len(roots) != 26 or value.get("root_count") != 26:
        raise CorpusError("Gate 5 root catalog must contain exactly 26 roots")
    for index, (root, spec) in enumerate(zip(roots, ROOT_SPECS, strict=True), 1):
        expected = {
            "root_id": index,
            "name": spec.name,
            "signature": spec.signature,
            "operation": spec.operation,
            "case_count": len(CASE_ARGUMENTS[index - 1]),
            "covers": list(spec.covers),
        }
        if root != expected:
            raise CorpusError(f"Gate 5 root #{index} differs from the closed catalog")
    cases = value.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != TARGET_CASE_COUNT
        or value.get("case_count") != TARGET_CASE_COUNT
        or value.get("fresh_boots_per_profile") != TARGET_CASE_COUNT
    ):
        raise CorpusError("Gate 5 requires exactly 52 cases/fresh boots per profile")
    observed_statuses: set[int] = set()
    observed_ids: set[int] = set()
    expected_index = 0
    for root_id, (spec, vectors) in enumerate(zip(ROOT_SPECS, CASE_ARGUMENTS, strict=True), 1):
        for args in vectors:
            case = cases[expected_index]
            if not isinstance(case, dict):
                raise CorpusError(f"Gate 5 case #{expected_index} is malformed")
            expected_keys = {
                "case_id",
                "root",
                "root_id",
                "signature",
                "args",
                "expected",
                "events",
                "covers",
            }
            if set(case) != expected_keys:
                raise CorpusError(f"Gate 5 case #{expected_index} fields differ")
            case_id = _parse_hex(case["case_id"], f"case #{expected_index} id")
            if case_id in observed_ids:
                raise CorpusError("Gate 5 corpus has duplicate case IDs")
            observed_ids.add(case_id)
            if case.get("root") != spec.name or case.get("root_id") != root_id:
                raise CorpusError(f"Gate 5 case #{expected_index} selects the wrong root")
            if case.get("signature") != spec.signature:
                raise CorpusError(f"Gate 5 case #{expected_index} has the wrong signature")
            raw_args = case.get("args")
            expected_args = [
                {"type": ty, "value": f"0x{number:016x}"}
                for ty, number in zip(spec.args, args, strict=True)
            ]
            if raw_args != expected_args:
                raise CorpusError(f"Gate 5 case #{expected_index} arguments differ")
            descriptor = _descriptor(
                suite_id=suite_id,
                case_id=case_id,
                root_id=root_id,
                spec=spec,
                args=args,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
            )
            outcome, model = evaluate(spec, descriptor)
            expected_result = {
                "status": outcome.status,
                "status_name": STATUS_NAMES[outcome.status],
                "value": f"0x{outcome.value:016x}",
                "event_count": len(model.events),
                "event_sha256": _event_digest(model.events),
                "final_memory_sha256": model.digest(),
            }
            if case.get("expected") != expected_result:
                raise CorpusError(f"Gate 5 case #{expected_index} differs from the independent model")
            expected_events = [asdict(event) for event in model.events]
            if case.get("events") != expected_events:
                raise CorpusError(f"Gate 5 case #{expected_index} event trace differs")
            if case.get("covers") != [*spec.covers, STATUS_NAMES[outcome.status]]:
                raise CorpusError(f"Gate 5 case #{expected_index} coverage labels differ")
            observed_statuses.add(outcome.status)
            expected_index += 1
    if observed_ids != set(range(1, TARGET_CASE_COUNT + 1)):
        raise CorpusError("Gate 5 case IDs are not canonical and contiguous")
    # `read-denied` is part of the closed outcome ABI but is deliberately not
    # reachable in this layout: ordinary regions are R or RW, while the
    # reserved/device class checks precede permissions.  A finite corpus must
    # not pretend to observe status 4 without adding a write-only RAM region.
    expected_observed_statuses = set(STATUS_NAMES) - {4}
    if observed_statuses != expected_observed_statuses:
        raise CorpusError(
            "Gate 5 corpus status coverage differs from the reachable table: "
            f"{observed_statuses!r}"
        )


def generate(
    output_dir: Path,
    *, source_seed: int = DEFAULT_SOURCE_SEED,
    runtime_seed: int = DEFAULT_RUNTIME_SEED,
) -> dict[str, object]:
    corpus = build_corpus(source_seed=source_seed, runtime_seed=runtime_seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "gate5-cases.json").write_text(
        json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    descriptors = output_dir / "descriptors"
    if descriptors.exists():
        shutil.rmtree(descriptors)
    descriptors.mkdir()
    suite_id = int(str(corpus["suite_id"]), 16)
    source_seed_value = int(str(corpus["source_seed"]), 16)
    runtime_seed_value = int(str(corpus["runtime_seed"]), 16)
    cases = corpus["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        root_id = int(case["root_id"])
        spec = ROOT_SPECS[root_id - 1]
        raw_args = case["args"]
        assert isinstance(raw_args, list)
        descriptor = _descriptor(
            suite_id=suite_id,
            case_id=int(str(case["case_id"]), 16),
            root_id=root_id,
            spec=spec,
            args=tuple(int(str(item["value"]), 16) for item in raw_args),
            source_seed=source_seed_value,
            runtime_seed=runtime_seed_value,
        )
        path = descriptors / f"case-{descriptor.case_id:04d}.json"
        path.write_text(
            json.dumps(run_memory_case.descriptor_json(descriptor), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-seed", type=lambda text: int(text, 0), default=DEFAULT_SOURCE_SEED)
    parser.add_argument("--runtime-seed", type=lambda text: int(text, 0), default=DEFAULT_RUNTIME_SEED)
    ns = parser.parse_args()
    try:
        corpus = generate(
            ns.output_dir.resolve(), source_seed=ns.source_seed, runtime_seed=ns.runtime_seed
        )
    except (CorpusError, Core0Error, OSError, ValueError) as error:
        print(f"GATE 5 CORPUS FAIL: {error}", file=__import__("sys").stderr)
        return 1
    print(json.dumps(corpus, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
