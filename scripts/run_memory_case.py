#!/usr/bin/env python3
"""Pack and execute one fresh-boot Gate 5 checked-memory case.

This module is host-only orchestration.  It binds a closed typed descriptor to
one audited image, creates the two declared loader blobs, and validates the
complete UART transcript including all four ordinary-region post-states and
every boundary canary.  Expected semantic answers deliberately do not enter
either loader blob.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from core0_common import (
    CommandResult,
    Core0Error,
    load_json,
    repo_root,
    require_tools,
    run_bounded,
    sha256,
    write_json,
)


PROFILE = "core0-v0.4"
ARTIFACT_CATEGORY = "test-memory-suite"
TEST_ABI = "lemma-memory-test-v1"
RESULT_TAG = "checked-result-v1"
MAGIC_BYTES = b"LEMMA005"
MAGIC_WORD = 0x353030414D4D454C
ABI_VERSION = 1
HEADER_WORDS = 16
HEADER_BYTES = HEADER_WORDS * 8
ARG_SLOTS = 16
ARGUMENT_BYTES = ARG_SLOTS * 8
CONTROL_BYTES = HEADER_BYTES + ARGUMENT_BYTES
U64_MAX = (1 << 64) - 1

TYPE_TAGS = {"bool": 1, "u8": 2, "u32": 3, "u64": 4}
TYPE_MAX = {
    "bool": 1,
    "u8": (1 << 8) - 1,
    "u32": (1 << 32) - 1,
    "u64": U64_MAX,
}

REGION_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": 1,
        "name": "scratch",
        "kind": "ordinary",
        "base": 0x80801000,
        "length": 0x1000,
        "widths": (1, 4, 8),
        "alignment": 8,
        "readable": True,
        "writable": True,
        "purpose": "ordinary checked scratch RAM",
    },
    {
        "id": 2,
        "name": "input-records",
        "kind": "ordinary",
        "base": 0x81000000,
        "length": 0x1000,
        "widths": (1, 4, 8),
        "alignment": 8,
        "readable": True,
        "writable": False,
        "purpose": "host-provided immutable input records",
    },
    {
        "id": 3,
        "name": "output",
        "kind": "ordinary",
        "base": 0x80803000,
        "length": 0x1000,
        "widths": (1, 4, 8),
        "alignment": 8,
        "readable": True,
        "writable": True,
        "purpose": "checked output buffer",
    },
    {
        "id": 4,
        "name": "events",
        "kind": "ordinary",
        "base": 0x80805000,
        "length": 0x1000,
        "widths": (4, 8),
        "alignment": 8,
        "readable": True,
        "writable": True,
        "purpose": "fixed-capacity event storage",
    },
)

RESERVED_REGION_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": 0x70,
        "name": "image",
        "kind": "reserved",
        "base": 0x80000000,
        "length": 0x007F0000,
        "widths": (),
        "alignment": 8,
        "readable": False,
        "writable": False,
        "purpose": "loaded image envelope; denied to the general RAM API",
    },
    {
        "id": 0x71,
        "name": "stack",
        "kind": "reserved",
        "base": 0x807F0000,
        "length": 0x00010000,
        "widths": (),
        "alignment": 8,
        "readable": False,
        "writable": False,
        "purpose": "machine stack; denied to the general RAM API",
    },
)

DEVICE_REGION_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": 0x80,
        "name": "uart16550",
        "kind": "device",
        "base": 0x10000000,
        "length": 0x100,
        "widths": (),
        "alignment": 8,
        "readable": False,
        "writable": False,
        "purpose": "device MMIO; excluded from ordinary RAM operations",
    },
    {
        "id": 0x81,
        "name": "sifive-test",
        "kind": "device",
        "base": 0x00100000,
        "length": 0x1000,
        "widths": (),
        "alignment": 8,
        "readable": False,
        "writable": False,
        "purpose": "VM termination MMIO; excluded from ordinary RAM operations",
    },
)

REGIONS_BY_ID = {
    int(item["id"]): item
    for item in (*REGION_SPECS, *RESERVED_REGION_SPECS, *DEVICE_REGION_SPECS)
}

CANARY_SPECS: tuple[dict[str, object], ...] = (
    {
        "id": 1,
        "name": "image",
        "address": 0x807EFFF0,
        "purpose": "last image-envelope bytes",
    },
    {"id": 2, "name": "stack", "address": 0x807F0000, "purpose": "stack-bottom sentinel"},
    {
        "id": 3,
        "name": "scratch-low",
        "address": 0x80800FF0,
        "purpose": "scratch underflow sentinel",
    },
    {
        "id": 4,
        "name": "scratch-high",
        "address": 0x80802000,
        "purpose": "scratch overflow sentinel",
    },
    {
        "id": 5,
        "name": "output-low",
        "address": 0x80802FF0,
        "purpose": "output underflow sentinel",
    },
    {
        "id": 6,
        "name": "output-high",
        "address": 0x80804000,
        "purpose": "output overflow sentinel",
    },
    {
        "id": 7,
        "name": "events-low",
        "address": 0x80804FF0,
        "purpose": "events underflow sentinel",
    },
    {
        "id": 8,
        "name": "events-high",
        "address": 0x80806000,
        "purpose": "events overflow sentinel",
    },
    {
        "id": 9,
        "name": "input-low",
        "address": 0x80FFFFF0,
        "purpose": "input underflow sentinel",
    },
    {
        "id": 10,
        "name": "input-high",
        "address": 0x81001000,
        "purpose": "input overflow sentinel",
    },
)
CANARY_SIZE = 16
MACHINE_FIXTURE_START = 0x807EFFF0
MACHINE_FIXTURE_STOP = 0x80806010
MACHINE_FIXTURE_SIZE = MACHINE_FIXTURE_STOP - MACHINE_FIXTURE_START
INPUT_FIXTURE_START = 0x80FFFFF0
INPUT_FIXTURE_STOP = 0x81001010
INPUT_FIXTURE_SIZE = INPUT_FIXTURE_STOP - INPUT_FIXTURE_START

LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z")
HEX16 = rb"([0-9a-f]{16})"
CASE_LINE = re.compile(rb"CASE:" + HEX16 + rb":" + HEX16 + rb":" + HEX16 + rb"\n\Z")
OUTCOME_LINE = re.compile(rb"OUTCOME:" + HEX16 + rb":" + HEX16 + rb":" + HEX16 + rb"\n\Z")
CANARY_LINE = re.compile(rb"CANARY:([0-9a-f]{2}):" + HEX16 + rb":" + HEX16 + rb"\n\Z")
END_LINE = re.compile(rb"END:" + HEX16 + rb"\n\Z")
REGION_WORD_BYTES = 8
REGION_BYTES = 0x1000
REGION_PAYLOAD_HEX_BYTES = REGION_BYTES * 2
REGION_LINE = re.compile(
    rb"REGION:([0-9a-f]{2}):" + HEX16 +
    rb":([0-9a-f]{" + str(REGION_PAYLOAD_HEX_BYTES).encode("ascii") + rb"})\n\Z"
)


@dataclass(frozen=True)
class MemorySignature:
    args: tuple[str, ...]


@dataclass(frozen=True)
class MemoryCaseDescriptor:
    suite_id: int
    case_id: int
    root: str
    root_id: int
    signature: MemorySignature
    source_seed: int
    runtime_seed: int
    args: tuple[int, ...]


@dataclass(frozen=True)
class MemoryOutcome:
    status: int
    value: int


@dataclass(frozen=True)
class MemoryRegionObservation:
    region_id: int
    data: bytes


@dataclass(frozen=True)
class ParsedControl:
    suite_id: int
    case_id: int
    root_id: int
    signature: MemorySignature
    source_seed: int
    runtime_seed: int
    args: tuple[int, ...]


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _u64(value: object, context: str) -> int:
    if not isinstance(value, str):
        raise Core0Error(f"{context} must be a string-encoded UInt64")
    if re.fullmatch(r"0x[0-9a-f]{16}", value) is None:
        raise Core0Error(f"{context} is not canonical lowercase UInt64: {value!r}")
    parsed = int(value, 16)
    if not 0 <= parsed <= U64_MAX:
        raise Core0Error(f"{context} is outside UInt64")
    return parsed


def _scalar_type(value: object, context: str) -> str:
    if not isinstance(value, str) or value not in TYPE_TAGS:
        raise Core0Error(f"{context} is not bool, u8, u32, or u64")
    return value


def _validate_scalar(value: int, ty: str, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= TYPE_MAX[ty]:
        if ty == "bool":
            raise Core0Error(f"{context} has invalid Bool encoding; expected 0 or 1")
        raise Core0Error(f"{context} is outside {ty}")


def validate_descriptor(descriptor: MemoryCaseDescriptor) -> None:
    if not isinstance(descriptor, MemoryCaseDescriptor):
        raise Core0Error("memory descriptor has the wrong host representation")
    if LEAN_IDENTIFIER.fullmatch(descriptor.root) is None:
        raise Core0Error("memory descriptor root is not a fully qualified Lean identity")
    for label, value in (
        ("suite id", descriptor.suite_id),
        ("case id", descriptor.case_id),
        ("root id", descriptor.root_id),
        ("source seed", descriptor.source_seed),
        ("runtime seed", descriptor.runtime_seed),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
            raise Core0Error(f"memory descriptor {label} is outside UInt64")
    if descriptor.case_id == 0 or descriptor.root_id == 0:
        raise Core0Error("memory descriptor case/root IDs must be nonzero")
    if len(descriptor.signature.args) > ARG_SLOTS:
        raise Core0Error(f"memory root has more than {ARG_SLOTS} arguments")
    if len(descriptor.args) != len(descriptor.signature.args):
        raise Core0Error("memory descriptor argument count differs from its signature")
    for index, (ty, value) in enumerate(zip(descriptor.signature.args, descriptor.args, strict=True)):
        _scalar_type(ty, f"memory signature arg #{index}")
        _validate_scalar(value, ty, f"memory argument #{index}")


def parse_descriptor(value: object) -> MemoryCaseDescriptor:
    if not isinstance(value, dict):
        raise Core0Error("memory descriptor is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "test_abi",
            "suite_id",
            "case_id",
            "root",
            "root_id",
            "signature",
            "source_seed",
            "runtime_seed",
            "args",
        },
        "memory descriptor",
    )
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
        raise Core0Error("memory descriptor has an unsupported schema/test ABI")
    if value.get("test_abi") != TEST_ABI:
        raise Core0Error("memory descriptor has an unsupported schema/test ABI")
    root = value.get("root")
    if not isinstance(root, str):
        raise Core0Error("memory descriptor root is not a string")
    signature_value = value.get("signature")
    if not isinstance(signature_value, dict):
        raise Core0Error("memory descriptor signature is not an object")
    _exact_keys(signature_value, {"args", "result"}, "memory descriptor signature")
    raw_types = signature_value.get("args")
    if not isinstance(raw_types, list):
        raise Core0Error("memory descriptor argument types are not an array")
    types = tuple(
        _scalar_type(item, f"memory signature arg #{index}")
        for index, item in enumerate(raw_types)
    )
    if signature_value.get("result") != RESULT_TAG:
        raise Core0Error("memory descriptor result tag is not checked-result-v1")
    raw_args = value.get("args")
    if not isinstance(raw_args, list):
        raise Core0Error("memory descriptor arguments are not an array")
    descriptor = MemoryCaseDescriptor(
        suite_id=_u64(value.get("suite_id"), "memory suite id"),
        case_id=_u64(value.get("case_id"), "memory case id"),
        root=root,
        root_id=_u64(value.get("root_id"), "memory root id"),
        signature=MemorySignature(types),
        source_seed=_u64(value.get("source_seed"), "memory source seed"),
        runtime_seed=_u64(value.get("runtime_seed"), "memory runtime seed"),
        args=tuple(
            _u64(item, f"memory argument #{index}")
            for index, item in enumerate(raw_args)
        ),
    )
    validate_descriptor(descriptor)
    return descriptor


def load_descriptor(path: Path) -> MemoryCaseDescriptor:
    return parse_descriptor(load_json(path))


def descriptor_json(descriptor: MemoryCaseDescriptor) -> dict[str, object]:
    validate_descriptor(descriptor)
    return {
        "schema_version": 1,
        "test_abi": TEST_ABI,
        "suite_id": f"0x{descriptor.suite_id:016x}",
        "case_id": f"0x{descriptor.case_id:016x}",
        "root": descriptor.root,
        "root_id": f"0x{descriptor.root_id:016x}",
        "signature": {"args": list(descriptor.signature.args), "result": RESULT_TAG},
        "source_seed": f"0x{descriptor.source_seed:016x}",
        "runtime_seed": f"0x{descriptor.runtime_seed:016x}",
        "args": [f"0x{item:016x}" for item in descriptor.args],
    }


def _pack_tags(types: tuple[str, ...]) -> tuple[int, int]:
    if len(types) > ARG_SLOTS:
        raise Core0Error("memory signature exceeds the fixed tag table")
    encoded = bytes([*(TYPE_TAGS[item] for item in types), *([0] * (ARG_SLOTS - len(types)))])
    return int.from_bytes(encoded[:8], "little"), int.from_bytes(encoded[8:], "little")


def _unpack_tags(low: int, high: int, count: int) -> tuple[str, ...]:
    if count > ARG_SLOTS:
        raise Core0Error("memory control argument count exceeds 16")
    inverse = {tag: name for name, tag in TYPE_TAGS.items()}
    encoded = low.to_bytes(8, "little") + high.to_bytes(8, "little")
    if any(encoded[count:]):
        raise Core0Error("memory control has nonzero unused argument tags")
    result: list[str] = []
    for index, tag in enumerate(encoded[:count]):
        if tag not in inverse:
            raise Core0Error(f"memory control argument #{index} has unknown type tag {tag}")
        result.append(inverse[tag])
    return tuple(result)


def pack_control(descriptor: MemoryCaseDescriptor) -> bytes:
    validate_descriptor(descriptor)
    low, high = _pack_tags(descriptor.signature.args)
    header = struct.pack(
        "<16Q",
        MAGIC_WORD,
        ABI_VERSION,
        HEADER_BYTES,
        CONTROL_BYTES,
        descriptor.suite_id,
        descriptor.case_id,
        descriptor.root_id,
        len(descriptor.args),
        low,
        high,
        descriptor.source_seed,
        descriptor.runtime_seed,
        0,
        0,
        0,
        0,
    )
    slots = (*descriptor.args, *([0] * (ARG_SLOTS - len(descriptor.args))))
    result = header + struct.pack("<16Q", *slots)
    if len(result) != CONTROL_BYTES:
        raise AssertionError("internal memory control size mismatch")
    if parse_control(result) != ParsedControl(
        descriptor.suite_id,
        descriptor.case_id,
        descriptor.root_id,
        descriptor.signature,
        descriptor.source_seed,
        descriptor.runtime_seed,
        descriptor.args,
    ):
        raise Core0Error("packed memory control does not round-trip")
    return result


def parse_control(data: bytes) -> ParsedControl:
    if not isinstance(data, bytes) or len(data) != CONTROL_BYTES:
        raise Core0Error(f"memory control must be exactly {CONTROL_BYTES} bytes")
    words = struct.unpack("<16Q", data[:HEADER_BYTES])
    if data[:8] != MAGIC_BYTES or words[0] != MAGIC_WORD:
        raise Core0Error("memory control has the wrong magic")
    if words[1] != ABI_VERSION:
        raise Core0Error("memory control has an unsupported version")
    if words[2] != HEADER_BYTES or words[3] != CONTROL_BYTES:
        raise Core0Error("memory control declares the wrong size")
    if any(words[12:16]):
        raise Core0Error("memory control has nonzero reserved words")
    count = words[7]
    types = _unpack_tags(words[8], words[9], count)
    slots = struct.unpack("<16Q", data[HEADER_BYTES:])
    if any(slots[count:]):
        raise Core0Error("memory control has nonzero unused argument slots")
    args = tuple(slots[:count])
    for index, (arg, ty) in enumerate(zip(args, types, strict=True)):
        _validate_scalar(arg, ty, f"memory control argument #{index}")
    if words[5] == 0 or words[6] == 0:
        raise Core0Error("memory control has a zero case/root ID")
    return ParsedControl(
        suite_id=words[4],
        case_id=words[5],
        root_id=words[6],
        signature=MemorySignature(types),
        source_seed=words[10],
        runtime_seed=words[11],
        args=args,
    )


def _stream_bytes(descriptor: MemoryCaseDescriptor, label: str, size: int) -> bytes:
    validate_descriptor(descriptor)
    prefix = (
        f"lemma-memory-fixture-v1:{descriptor.suite_id:016x}:"
        f"{descriptor.case_id:016x}:{descriptor.runtime_seed:016x}:{label}:"
    ).encode("ascii")
    output = bytearray()
    counter = 0
    while len(output) < size:
        output.extend(hashlib.sha256(prefix + counter.to_bytes(8, "little")).digest())
        counter += 1
    return bytes(output[:size])


def canary_bytes(descriptor: MemoryCaseDescriptor) -> dict[str, bytes]:
    return {
        str(spec["name"]): _stream_bytes(descriptor, f"canary:{spec['name']}", CANARY_SIZE)
        for spec in CANARY_SPECS
    }


def initial_region_bytes(descriptor: MemoryCaseDescriptor, region_id: int) -> bytes:
    validate_descriptor(descriptor)
    spec = REGIONS_BY_ID.get(region_id)
    if spec is None or spec.get("kind") != "ordinary":
        raise Core0Error(f"cannot initialize non-RAM region ID {region_id}")
    data = bytearray(
        _stream_bytes(descriptor, f"region:{spec['name']}", int(spec["length"]))
    )
    if region_id == 2:
        data[:CONTROL_BYTES] = pack_control(descriptor)
    return bytes(data)


def pack_machine_fixture(descriptor: MemoryCaseDescriptor) -> bytes:
    data = bytearray(_stream_bytes(descriptor, "machine-envelope", MACHINE_FIXTURE_SIZE))
    for spec in REGION_SPECS:
        if int(spec["id"]) == 2:
            continue
        start = int(spec["base"]) - MACHINE_FIXTURE_START
        payload = initial_region_bytes(descriptor, int(spec["id"]))
        if start < 0 or start + len(payload) > len(data):
            raise Core0Error(f"region {spec['name']} is outside the machine fixture")
        data[start : start + len(payload)] = payload
    expected_canaries = canary_bytes(descriptor)
    for spec in CANARY_SPECS:
        address = int(spec["address"])
        if not MACHINE_FIXTURE_START <= address < MACHINE_FIXTURE_STOP:
            continue
        start = address - MACHINE_FIXTURE_START
        data[start : start + CANARY_SIZE] = expected_canaries[str(spec["name"])]
    return bytes(data)


def pack_input_fixture(descriptor: MemoryCaseDescriptor) -> bytes:
    data = bytearray(_stream_bytes(descriptor, "input-envelope", INPUT_FIXTURE_SIZE))
    input_spec = REGIONS_BY_ID[2]
    region_start = int(input_spec["base"]) - INPUT_FIXTURE_START
    payload = initial_region_bytes(descriptor, 2)
    data[region_start : region_start + len(payload)] = payload
    expected_canaries = canary_bytes(descriptor)
    for spec in CANARY_SPECS:
        address = int(spec["address"])
        if INPUT_FIXTURE_START <= address < INPUT_FIXTURE_STOP:
            start = address - INPUT_FIXTURE_START
            data[start : start + CANARY_SIZE] = expected_canaries[str(spec["name"])]
    return bytes(data)


def expected_canary_words(descriptor: MemoryCaseDescriptor) -> tuple[tuple[int, int, int], ...]:
    values = canary_bytes(descriptor)
    return tuple(
        (
            int(spec["id"]),
            int.from_bytes(values[str(spec["name"])][:8], "little"),
            int.from_bytes(values[str(spec["name"])][8:], "little"),
        )
        for spec in CANARY_SPECS
    )


def final_memory_sha256(regions: tuple[MemoryRegionObservation, ...]) -> str:
    """Hash the complete ordinary-region state with the model's exact framing."""
    expected_ids = tuple(int(spec["id"]) for spec in REGION_SPECS)
    if tuple(region.region_id for region in regions) != expected_ids:
        raise Core0Error("memory post-state regions are not the exact ordered ID catalog")
    hasher = hashlib.sha256()
    for region, spec in zip(regions, REGION_SPECS, strict=True):
        expected_length = int(spec["length"])
        if len(region.data) != expected_length:
            raise Core0Error(
                f"memory post-state region {region.region_id} has {len(region.data)} "
                f"bytes; expected {expected_length}"
            )
        hasher.update(bytes([region.region_id]))
        hasher.update(region.data)
    return hasher.hexdigest()


def _decode_region_words(payload: bytes, expected_length: int, region_id: int) -> bytes:
    if expected_length % REGION_WORD_BYTES != 0:
        raise Core0Error(f"memory transcript REGION {region_id} has a partial word")
    if len(payload) != expected_length * 2:
        raise Core0Error(f"memory transcript REGION {region_id} payload has the wrong size")
    decoded = bytearray()
    for start in range(0, len(payload), 16):
        decoded.extend(int(payload[start : start + 16], 16).to_bytes(8, "little"))
    if len(decoded) != expected_length:
        raise Core0Error(f"memory transcript REGION {region_id} did not decode completely")
    return bytes(decoded)


def validate_transcript(
    transcript: bytes, descriptor: MemoryCaseDescriptor
) -> tuple[
    MemoryOutcome,
    tuple[MemoryRegionObservation, ...],
    tuple[tuple[int, int, int], ...],
]:
    validate_descriptor(descriptor)
    lines = transcript.splitlines(keepends=True)
    expected_count = 4 + len(REGION_SPECS) + len(CANARY_SPECS)
    if len(lines) != expected_count or any(not line.endswith(b"\n") for line in lines):
        raise Core0Error("memory transcript is noisy, truncated, or has the wrong line count")
    if lines[0] != b"LEMMA_MEMORY/1\n":
        raise Core0Error("memory transcript has the wrong banner or leading noise")
    case_match = CASE_LINE.fullmatch(lines[1])
    if case_match is None:
        raise Core0Error("memory transcript has a malformed CASE frame")
    case_values = tuple(int(item, 16) for item in case_match.groups())
    if case_values != (descriptor.suite_id, descriptor.case_id, descriptor.root_id):
        raise Core0Error("memory transcript CASE identity differs from its descriptor")
    outcome_match = OUTCOME_LINE.fullmatch(lines[2])
    if outcome_match is None:
        raise Core0Error("memory transcript has a malformed OUTCOME frame")
    case_id, status, value = (int(item, 16) for item in outcome_match.groups())
    if case_id != descriptor.case_id:
        raise Core0Error("memory transcript OUTCOME case ID differs from its descriptor")
    if status > 0xFF:
        raise Core0Error("memory transcript status has nonzero high bits")
    if status > 9:
        raise Core0Error(f"memory transcript has unknown status code {status}")
    observed_regions: list[MemoryRegionObservation] = []
    for index, (line, spec) in enumerate(
        zip(lines[3 : 3 + len(REGION_SPECS)], REGION_SPECS, strict=True)
    ):
        match = REGION_LINE.fullmatch(line)
        if match is None:
            raise Core0Error(f"memory transcript REGION #{index} is malformed")
        region_id = int(match.group(1), 16)
        declared_length = int(match.group(2), 16)
        expected_id = int(spec["id"])
        expected_length = int(spec["length"])
        if region_id != expected_id or declared_length != expected_length:
            raise Core0Error(
                f"memory transcript REGION #{index} identity/length differs from the catalog"
            )
        observed_regions.append(
            MemoryRegionObservation(
                region_id,
                _decode_region_words(match.group(3), expected_length, region_id),
            )
        )
    # Validate the combined framing here as well as in the caller so malformed
    # region objects can never become ordinary run evidence.
    final_memory_sha256(tuple(observed_regions))
    observed_canaries: list[tuple[int, int, int]] = []
    canary_start = 3 + len(REGION_SPECS)
    for index, (line, expected) in enumerate(
        zip(
            lines[canary_start : canary_start + len(CANARY_SPECS)],
            expected_canary_words(descriptor),
            strict=True,
        )
    ):
        match = CANARY_LINE.fullmatch(line)
        if match is None:
            raise Core0Error(f"memory transcript CANARY #{index} is malformed")
        observed = tuple(int(item, 16) for item in match.groups())
        if observed != expected:
            raise Core0Error(
                f"memory transcript CANARY #{index} changed: {observed!r} != {expected!r}"
            )
        observed_canaries.append(observed)
    end_match = END_LINE.fullmatch(lines[-1])
    if end_match is None or int(end_match.group(1), 16) != descriptor.case_id:
        raise Core0Error("memory transcript has a malformed or mismatched END frame")
    return MemoryOutcome(status, value), tuple(observed_regions), tuple(observed_canaries)


def _manifest_region(spec: dict[str, object]) -> dict[str, object]:
    return {
        "id": spec["id"],
        "name": spec["name"],
        "base": spec["base"],
        "length": spec["length"],
        "alignment": spec["alignment"],
        "widths": list(spec["widths"]),
        "read": spec["readable"],
        "write": spec["writable"],
        "kind": spec["kind"],
        "purpose": spec["purpose"],
        "interval_valid": True,
    }


def _hex_addr(value: int) -> str:
    if not 0 <= value <= U64_MAX:
        raise Core0Error("memory contract address is outside UInt64")
    return f"0x{value:016x}"


def expected_memory_contract() -> dict[str, object]:
    return {
        "byte_order": "little-endian",
        "guard_order": ["lookup", "class", "permission", "width", "bounds", "alignment"],
        "successful_access_volatile": True,
        "regions": [
            _manifest_region(item)
            for item in (*REGION_SPECS, *RESERVED_REGION_SPECS, *DEVICE_REGION_SPECS)
        ],
        "statuses": [
            {"code": 0, "name": "ok"},
            {"code": 1, "name": "unknown-region"},
            {"code": 2, "name": "reserved-region"},
            {"code": 3, "name": "device-region"},
            {"code": 4, "name": "read-denied"},
            {"code": 5, "name": "write-denied"},
            {"code": 6, "name": "width-denied"},
            {"code": 7, "name": "out-of-bounds"},
            {"code": 8, "name": "misaligned"},
            {"code": 9, "name": "budget-exceeded"},
        ],
    }


def expected_fixture_contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "canaries": [
            {
                "id": item["id"],
                "name": item["name"],
                "start": _hex_addr(int(item["address"])),
                "size": CANARY_SIZE,
                "purpose": item["purpose"],
            }
            for item in CANARY_SPECS
        ],
        "fixtures": [
            {
                "name": "machine-memory",
                "start": _hex_addr(MACHINE_FIXTURE_START),
                "size": _hex_addr(MACHINE_FIXTURE_SIZE),
            },
            {
                "name": "runtime-input",
                "start": _hex_addr(INPUT_FIXTURE_START),
                "size": _hex_addr(INPUT_FIXTURE_SIZE),
            },
        ],
    }


def expected_machine_layout() -> dict[str, object]:
    return {
        "schema_version": 1,
        "ram": {"start": _hex_addr(0x80000000), "size": _hex_addr(0x08000000)},
        "image": {"start": _hex_addr(0x80000000), "size": _hex_addr(0x007F0000)},
        "stack": {
            "start": _hex_addr(0x807F0000),
            "size": _hex_addr(0x00010000),
            "alignment": 16,
        },
        "input": {
            "start": _hex_addr(0x81000000),
            "size": _hex_addr(0x00001000),
            "alignment": 8,
        },
        "uart_16550": {"base": _hex_addr(0x10000000), "size": _hex_addr(0x100)},
        "sifive_test": {"base": _hex_addr(0x00100000)},
    }


def expected_test_abi(descriptor: MemoryCaseDescriptor) -> dict[str, object]:
    validate_descriptor(descriptor)
    return {
        "schema_version": 1,
        "contract_version": PROFILE,
        "name": TEST_ABI,
        "result_tag": RESULT_TAG,
        "physical_result_words": ["status:i64", "value:i64"],
        "byte_order": "little-endian",
        "magic_bytes": MAGIC_BYTES.hex(),
        "magic_word": f"0x{MAGIC_WORD:016x}",
        "version": ABI_VERSION,
        "header_bytes": HEADER_BYTES,
        "control_bytes": CONTROL_BYTES,
        "maximum_arguments": ARG_SLOTS,
        "tags": dict(TYPE_TAGS),
        "header_words": [
            "magic",
            "version",
            "header_bytes",
            "control_bytes",
            "suite_id",
            "case_id",
            "root_id",
            "argument_count",
            "argument_tags_0_7",
            "argument_tags_8_15",
            "source_seed",
            "runtime_seed",
            "reserved_zero",
            "reserved_zero",
            "reserved_zero",
            "reserved_zero",
        ],
        "argument_layout": "16xu64; unused slots zero",
        "transport_rules": (
            "Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; "
            "reject before truncation"
        ),
        "output_protocol": {
            "banner": "LEMMA_MEMORY/1\n",
            "case": "CASE:<suite16>:<case16>:<root16>\n",
            "outcome": "OUTCOME:<case16>:<status16>:<value16>\n",
            "region": "REGION:<id2>:<length16>:<little-endian-i64-words>\n",
            "canary": "CANARY:<id2>:<low16>:<high16>\n",
            "end": "END:<case16>\n",
        },
        "suite_id": f"{descriptor.suite_id:016x}",
        "source_seed": f"{descriptor.source_seed:016x}",
        "runtime_seed": f"{descriptor.runtime_seed:016x}",
    }


def validate_image_binding(image: Path, descriptor: MemoryCaseDescriptor) -> None:
    validate_descriptor(descriptor)
    directory = image.parent
    paths = {
        name: directory / name
        for name in (
            "image.elf",
            "memory-suite-manifest.json",
            "memory-test-abi.json",
            "memory-fixtures.json",
            "layout.json",
            "provenance.json",
            "build.json",
        )
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise Core0Error("memory image binding is missing: " + ", ".join(missing))
    if image.resolve() != paths["image.elf"].resolve():
        raise Core0Error("memory runner image is not the bound image.elf artifact")
    manifest = load_json(paths["memory-suite-manifest.json"])
    abi = load_json(paths["memory-test-abi.json"])
    provenance = load_json(paths["provenance.json"])
    build = load_json(paths["build.json"])
    layout = load_json(paths["layout.json"])
    fixtures = load_json(paths["memory-fixtures.json"])
    if not isinstance(manifest, dict) or not isinstance(abi, dict):
        raise Core0Error("memory image manifest/ABI is malformed")
    if (
        manifest.get("artifact_category") != ARTIFACT_CATEGORY
        or manifest.get("contract_version") != PROFILE
        or manifest.get("test_abi") != TEST_ABI
    ):
        raise Core0Error("memory image manifest has the wrong category/profile/ABI")
    if manifest.get("memory_contract") != expected_memory_contract():
        raise Core0Error("memory image contract differs from the fixed v0.4 region/status table")
    expected_identity = {
        "suite_id": f"{descriptor.suite_id:016x}",
        "source_seed": f"{descriptor.source_seed:016x}",
        "runtime_seed": f"{descriptor.runtime_seed:016x}",
    }
    for field, rendered in expected_identity.items():
        if manifest.get(field) != rendered:
            raise Core0Error(f"memory image {field} differs from its descriptor")
    if abi != expected_test_abi(descriptor):
        raise Core0Error("memory test ABI differs from the exact control/outcome contract")
    roots = manifest.get("roots")
    if not isinstance(roots, list):
        raise Core0Error("memory image manifest lacks a root catalog")
    selected = [item for item in roots if isinstance(item, dict) and item.get("root_id") == descriptor.root_id]
    if len(selected) != 1:
        raise Core0Error("memory descriptor root ID does not select exactly one image root")
    # The suite manifest uses the compiler's ActionSignature (`args` only).
    # The descriptor and test-ABI file independently bind the physical result.
    expected_signature = {"args": list(descriptor.signature.args)}
    if selected[0].get("source") != descriptor.root or selected[0].get("signature") != expected_signature:
        raise Core0Error("memory descriptor root identity/signature differs from the image")
    if layout != expected_machine_layout():
        raise Core0Error("memory image layout differs from the fixed LemmaVM map")
    if fixtures != expected_fixture_contract():
        raise Core0Error("memory fixture/canary envelope differs from the fixed contract")
    if (
        not isinstance(provenance, dict)
        or provenance.get("artifact_category") != ARTIFACT_CATEGORY
        or not isinstance(build, dict)
        or build.get("artifact_category") != ARTIFACT_CATEGORY
    ):
        raise Core0Error("memory image provenance/build category is inconsistent")
    artifacts = build.get("artifacts")
    if not isinstance(artifacts, dict):
        raise Core0Error("memory image build record has no artifact hashes")
    for name in ("image.elf", "memory-suite-manifest.json", "memory-test-abi.json"):
        if artifacts.get(name) != sha256(paths[name]):
            raise Core0Error(f"memory image build hash differs for {name}")


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _qemu_argv(image: Path, machine_fixture: Path, input_fixture: Path) -> tuple[str, ...]:
    return (
        "qemu-system-riscv64",
        "-machine",
        "virt,acpi=off",
        "-accel",
        "tcg",
        "-cpu",
        "rv64",
        "-smp",
        "1",
        "-m",
        "128M",
        "-bios",
        "none",
        "-kernel",
        str(image),
        "-device",
        f"loader,file={machine_fixture},addr=0x{MACHINE_FIXTURE_START:x},force-raw=on",
        "-device",
        f"loader,file={input_fixture},addr=0x{INPUT_FIXTURE_START:x},force-raw=on",
        "-nodefaults",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-seed",
        "1",
    )


def run_case(
    *,
    root: Path,
    image: Path,
    output_dir: Path,
    descriptor: MemoryCaseDescriptor,
    timeout_seconds: float,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Invalidate a prior pass before validating a newly supplied case whenever
    # its record identity is usable.  A malformed rerun must not leave stale
    # success evidence behind.
    usable_identity = isinstance(descriptor, MemoryCaseDescriptor) and all(
        not isinstance(value, bool) and isinstance(value, int) and 0 <= value <= U64_MAX
        for value in (descriptor.suite_id, descriptor.case_id)
    )
    record_path = (
        output_dir / f"run-{descriptor.suite_id:016x}-{descriptor.case_id:016x}.json"
        if usable_identity
        else None
    )
    if record_path is not None:
        record_path.unlink(missing_ok=True)
    validate_descriptor(descriptor)
    stem = f"{descriptor.suite_id:016x}-{descriptor.case_id:016x}"
    assert record_path is not None
    require_tools(("qemu-system-riscv64",))
    if not image.is_file():
        raise Core0Error(f"memory target image is missing: {image}")
    validate_image_binding(image, descriptor)

    machine_bytes = pack_machine_fixture(descriptor)
    input_bytes = pack_input_fixture(descriptor)
    if len(machine_bytes) != MACHINE_FIXTURE_SIZE or len(input_bytes) != INPUT_FIXTURE_SIZE:
        raise Core0Error("memory loader fixture has an internal size mismatch")
    machine_path = output_dir / f"machine-{stem}.bin"
    input_path = output_dir / f"input-{stem}.bin"
    uart_path = output_dir / f"uart-{stem}.bin"
    stderr_path = output_dir / f"qemu-{stem}.stderr"
    machine_path.write_bytes(machine_bytes)
    input_path.write_bytes(input_bytes)
    argv = _qemu_argv(image, machine_path, input_path)
    result: CommandResult = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    uart_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    if result.returncode != 0:
        raise Core0Error(
            f"memory QEMU process failure: exited with {result.returncode}; stderr: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    if result.stderr:
        raise Core0Error(
            "memory QEMU wrote unexpected stderr on zero exit: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    outcome, observed_regions, observed_canaries = validate_transcript(
        result.stdout, descriptor
    )
    memory_digest = final_memory_sha256(observed_regions)
    record: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "abi": "LEMMA_MEMORY/1",
        "descriptor": descriptor_json(descriptor),
        "image": _relative(image, root),
        "image_sha256": sha256(image),
        "machine_fixture": _relative(machine_path, root),
        "machine_fixture_address": f"0x{MACHINE_FIXTURE_START:x}",
        "machine_fixture_sha256": sha256(machine_path),
        "input_fixture": _relative(input_path, root),
        "input_fixture_address": f"0x{INPUT_FIXTURE_START:x}",
        "input_fixture_sha256": sha256(input_path),
        "qemu_argv": list(argv),
        "qemu_returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "uart": result.stdout.decode("ascii"),
        "uart_sha256": sha256(uart_path),
        "outcome": {"status": outcome.status, "value": f"0x{outcome.value:016x}"},
        "post_state_encoding": "ordered-region-id + consecutive little-endian i64 words",
        "post_state_bytes": sum(len(region.data) for region in observed_regions),
        "final_memory_sha256": memory_digest,
        "regions": [
            {
                "id": region.region_id,
                "name": str(REGIONS_BY_ID[region.region_id]["name"]),
                "bytes": len(region.data),
                "sha256": hashlib.sha256(region.data).hexdigest(),
            }
            for region in observed_regions
        ],
        "canaries": [
            {"id": item[0], "low": f"0x{item[1]:016x}", "high": f"0x{item[2]:016x}"}
            for item in observed_canaries
        ],
    }
    write_json(record_path, record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    ns = parser.parse_args()
    root = repo_root()

    def resolve(path: Path) -> Path:
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    try:
        descriptor = load_descriptor(resolve(ns.descriptor))
        record = run_case(
            root=root,
            image=resolve(ns.image),
            output_dir=resolve(ns.output_dir),
            descriptor=descriptor,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"MEMORY CASE RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(record["uart"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
