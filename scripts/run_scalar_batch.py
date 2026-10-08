#!/usr/bin/env python3
"""Pack and run one versioned, typed Core0 scalar batch.

This is host-only orchestration.  The wire format deliberately transports every
scalar in a 64-bit slot, but the descriptor retains the exact Core0 signature.
Values are range-checked before packing so widening never silently changes the
guest function ABI.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from core0_common import (
    Core0Error,
    CommandResult,
    load_json,
    repo_root,
    require_tools,
    run_bounded,
    sha256,
    write_json,
)


MAGIC_BYTES = b"LEMMA002"
MAGIC_WORD = 0x323030414D4D454C
ABI_VERSION = 1
HEADER_WORDS = 16
HEADER_BYTES = HEADER_WORDS * 8
ARG_SLOTS = 16
RECORD_WORDS = 1 + ARG_SLOTS
RECORD_BYTES = RECORD_WORDS * 8
MAX_CASES = 29

TYPE_TAGS = {
    "bool": 1,
    "u8": 2,
    "u32": 3,
    "u64": 4,
}
TAG_TYPES = {tag: name for name, tag in TYPE_TAGS.items()}
TYPE_MAX = {
    "bool": 1,
    "u8": (1 << 8) - 1,
    "u32": (1 << 32) - 1,
    "u64": (1 << 64) - 1,
}
U64_MAX = TYPE_MAX["u64"]
IMAGE_ARTIFACT_PROFILES = {
    "test-frontend-suite": "core0-v0.1",
    "test-cfg-suite": "core0-v0.2",
}
LEAN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\Z")
HEX16 = rb"([0-9a-f]{16})"
BATCH_LINE = re.compile(
    rb"BATCH:" + HEX16 + rb":" + HEX16 + rb":" + HEX16 + rb":" + HEX16 + rb"\n\Z"
)
RESULT_LINE = re.compile(
    rb"RESULT:" + HEX16 + rb":" + HEX16 + rb":" + HEX16 + rb"\n\Z"
)
END_LINE = re.compile(rb"END:" + HEX16 + rb":" + HEX16 + rb"\n\Z")
MALFORMED_CASE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
TYPED_INPUT_ERROR = b"ERROR:TYPED-INPUT\n"
GUEST_FAILURE_RETURNCODE = 1


@dataclass(frozen=True)
class ScalarSignature:
    args: tuple[str, ...]
    result: str


@dataclass(frozen=True)
class ScalarCase:
    case_id: int
    args: tuple[int, ...]
    expected_result_type: str


@dataclass(frozen=True)
class ScalarBatchDescriptor:
    suite_id: int
    batch_id: int
    root: str
    root_id: int
    signature: ScalarSignature
    source_seed: int
    runtime_seed: int
    cases: tuple[ScalarCase, ...]


@dataclass(frozen=True)
class ParsedFixture:
    suite_id: int
    batch_id: int
    root_id: int
    signature: ScalarSignature
    source_seed: int
    runtime_seed: int
    cases: tuple[ScalarCase, ...]


@dataclass(frozen=True)
class ScalarResult:
    case_id: int
    result_type: str
    value: int


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    observed = set(value)
    if observed != expected:
        raise Core0Error(
            f"{context} fields differ from the schema: "
            f"missing={sorted(expected - observed)!r}, "
            f"unexpected={sorted(observed - expected)!r}"
        )


def _u64(value: object, field: str) -> int:
    if not isinstance(value, str):
        raise Core0Error(f"{field} must be a string-encoded UInt64")
    try:
        parsed = int(value, 0)
    except ValueError as error:
        raise Core0Error(f"{field} is not a UInt64: {value!r}") from error
    if parsed < 0 or parsed > U64_MAX:
        raise Core0Error(f"{field} is outside UInt64: {value!r}")
    return parsed


def _scalar_type(value: object, field: str) -> str:
    if not isinstance(value, str) or value not in TYPE_TAGS:
        raise Core0Error(
            f"{field} is not a supported scalar type; expected bool, u8, u32, or u64"
        )
    return value


def _validate_scalar(value: int, ty: str, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Core0Error(f"{field} is not an integer transport value")
    if value < 0 or value > TYPE_MAX[ty]:
        if ty == "bool":
            raise Core0Error(f"{field} has invalid Bool encoding {value}; expected 0 or 1")
        raise Core0Error(f"{field} value {value} is outside {ty}")


def validate_descriptor(descriptor: ScalarBatchDescriptor) -> None:
    """Validate dataclass instances as strictly as JSON-loaded descriptors."""
    if not isinstance(descriptor, ScalarBatchDescriptor):
        raise Core0Error("scalar batch descriptor has the wrong host representation")
    if LEAN_IDENTIFIER.fullmatch(descriptor.root) is None:
        raise Core0Error("scalar batch root is not a valid fully qualified Lean identity")
    for field, value in (
        ("suite id", descriptor.suite_id),
        ("batch id", descriptor.batch_id),
        ("root id", descriptor.root_id),
        ("source seed", descriptor.source_seed),
        ("runtime seed", descriptor.runtime_seed),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > U64_MAX:
            raise Core0Error(f"scalar batch {field} is outside UInt64")
    if len(descriptor.signature.args) > ARG_SLOTS:
        raise Core0Error(
            f"scalar batch signature has {len(descriptor.signature.args)} args; maximum is {ARG_SLOTS}"
        )
    for index, ty in enumerate(descriptor.signature.args):
        _scalar_type(ty, f"scalar batch signature arg #{index}")
    _scalar_type(descriptor.signature.result, "scalar batch signature result")
    if not descriptor.cases or len(descriptor.cases) > MAX_CASES:
        raise Core0Error(f"scalar batch case count is outside the supported range 1..{MAX_CASES}")
    seen_ids: set[int] = set()
    for case_index, case in enumerate(descriptor.cases):
        if (
            isinstance(case.case_id, bool)
            or not isinstance(case.case_id, int)
            or case.case_id < 0
            or case.case_id > U64_MAX
        ):
            raise Core0Error(f"scalar batch case #{case_index} id is outside UInt64")
        if case.case_id in seen_ids:
            raise Core0Error(f"duplicate scalar batch case id 0x{case.case_id:016x}")
        seen_ids.add(case.case_id)
        if case.expected_result_type != descriptor.signature.result:
            raise Core0Error(
                f"scalar batch case #{case_index} expected result type differs from root result"
            )
        if len(case.args) != len(descriptor.signature.args):
            raise Core0Error(
                f"scalar batch case #{case_index} argument count differs from root signature"
            )
        for arg_index, (arg, ty) in enumerate(
            zip(case.args, descriptor.signature.args, strict=True)
        ):
            _validate_scalar(arg, ty, f"scalar batch case #{case_index} arg #{arg_index}")


def parse_descriptor(value: object) -> ScalarBatchDescriptor:
    """Validate an exact host descriptor before it can influence target input."""
    if not isinstance(value, dict):
        raise Core0Error("scalar batch descriptor is not an object")
    _exact_keys(
        value,
        {
            "schema_version",
            "suite_id",
            "batch_id",
            "root",
            "root_id",
            "signature",
            "source_seed",
            "runtime_seed",
            "cases",
        },
        "scalar batch descriptor",
    )
    if value.get("schema_version") != 1 or isinstance(value.get("schema_version"), bool):
        raise Core0Error("scalar batch descriptor has an unsupported schema")

    root = value.get("root")
    if not isinstance(root, str) or LEAN_IDENTIFIER.fullmatch(root) is None:
        raise Core0Error("scalar batch root is not a valid fully qualified Lean identity")

    signature_value = value.get("signature")
    if not isinstance(signature_value, dict):
        raise Core0Error("scalar batch signature is not an object")
    _exact_keys(signature_value, {"args", "result"}, "scalar batch signature")
    arg_values = signature_value.get("args")
    if not isinstance(arg_values, list):
        raise Core0Error("scalar batch signature args are not an array")
    if len(arg_values) > ARG_SLOTS:
        raise Core0Error(
            f"scalar batch signature has {len(arg_values)} args; maximum is {ARG_SLOTS}"
        )
    arg_types = tuple(
        _scalar_type(arg, f"scalar batch signature arg #{index}")
        for index, arg in enumerate(arg_values)
    )
    result_type = _scalar_type(signature_value.get("result"), "scalar batch signature result")
    signature = ScalarSignature(arg_types, result_type)

    cases_value = value.get("cases")
    if not isinstance(cases_value, list):
        raise Core0Error("scalar batch cases are not an array")
    if not cases_value:
        raise Core0Error("scalar batch is empty")
    if len(cases_value) > MAX_CASES:
        raise Core0Error(f"scalar batch has {len(cases_value)} cases; maximum is {MAX_CASES}")

    cases: list[ScalarCase] = []
    case_ids: set[int] = set()
    for case_index, case_value in enumerate(cases_value):
        if not isinstance(case_value, dict):
            raise Core0Error(f"scalar batch case #{case_index} is not an object")
        _exact_keys(
            case_value,
            {"case_id", "args", "expected_result_type"},
            f"scalar batch case #{case_index}",
        )
        case_id = _u64(case_value.get("case_id"), f"scalar batch case #{case_index} id")
        if case_id in case_ids:
            raise Core0Error(f"duplicate scalar batch case id 0x{case_id:016x}")
        case_ids.add(case_id)
        expected_result_type = _scalar_type(
            case_value.get("expected_result_type"),
            f"scalar batch case #{case_index} expected result type",
        )
        if expected_result_type != signature.result:
            raise Core0Error(
                f"scalar batch case #{case_index} expected result type "
                f"{expected_result_type!r} differs from root result {signature.result!r}"
            )
        args_value = case_value.get("args")
        if not isinstance(args_value, list) or len(args_value) != len(signature.args):
            observed = len(args_value) if isinstance(args_value, list) else None
            raise Core0Error(
                f"scalar batch case #{case_index} has {observed!r} args; "
                f"root signature requires {len(signature.args)}"
            )
        args: list[int] = []
        for arg_index, (raw_arg, arg_type) in enumerate(zip(args_value, signature.args, strict=True)):
            arg = _u64(raw_arg, f"scalar batch case #{case_index} arg #{arg_index}")
            _validate_scalar(arg, arg_type, f"scalar batch case #{case_index} arg #{arg_index}")
            args.append(arg)
        cases.append(ScalarCase(case_id, tuple(args), expected_result_type))

    descriptor = ScalarBatchDescriptor(
        suite_id=_u64(value.get("suite_id"), "scalar batch suite id"),
        batch_id=_u64(value.get("batch_id"), "scalar batch id"),
        root=root,
        root_id=_u64(value.get("root_id"), "scalar batch root id"),
        signature=signature,
        source_seed=_u64(value.get("source_seed"), "scalar batch source seed"),
        runtime_seed=_u64(value.get("runtime_seed"), "scalar batch runtime seed"),
        cases=tuple(cases),
    )
    validate_descriptor(descriptor)
    return descriptor


def load_descriptor(path: Path) -> ScalarBatchDescriptor:
    return parse_descriptor(load_json(path))


def _packed_tags(arg_types: tuple[str, ...]) -> tuple[int, int]:
    encoded = bytes([*(TYPE_TAGS[ty] for ty in arg_types), *([0] * (ARG_SLOTS - len(arg_types)))])
    return int.from_bytes(encoded[:8], "little"), int.from_bytes(encoded[8:], "little")


def _unpack_tags(low: int, high: int, arg_count: int) -> tuple[str, ...]:
    if arg_count > ARG_SLOTS:
        raise Core0Error(f"wire argument count {arg_count} exceeds maximum {ARG_SLOTS}")
    encoded = low.to_bytes(8, "little") + high.to_bytes(8, "little")
    active = encoded[:arg_count]
    unused = encoded[arg_count:]
    if any(unused):
        raise Core0Error("wire signature has nonzero unused argument tags")
    types: list[str] = []
    for index, tag in enumerate(active):
        ty = TAG_TYPES.get(tag)
        if ty is None:
            raise Core0Error(f"wire signature argument #{index} has unknown type tag {tag}")
        types.append(ty)
    return tuple(types)


def pack_fixture(descriptor: ScalarBatchDescriptor) -> bytes:
    """Serialize an already validated descriptor to the exact v1 input format."""
    validate_descriptor(descriptor)
    low_tags, high_tags = _packed_tags(descriptor.signature.args)
    header = struct.pack(
        "<16Q",
        MAGIC_WORD,
        ABI_VERSION,
        HEADER_BYTES,
        RECORD_BYTES,
        descriptor.suite_id,
        descriptor.batch_id,
        descriptor.root_id,
        len(descriptor.cases),
        len(descriptor.signature.args),
        TYPE_TAGS[descriptor.signature.result],
        low_tags,
        high_tags,
        descriptor.source_seed,
        descriptor.runtime_seed,
        0,
        0,
    )
    records: list[bytes] = []
    for case in descriptor.cases:
        slots = (*case.args, *([0] * (ARG_SLOTS - len(case.args))))
        records.append(struct.pack("<17Q", case.case_id, *slots))
    fixture = header + b"".join(records)
    validate_fixture(fixture, descriptor)
    return fixture


def parse_fixture(data: bytes) -> ParsedFixture:
    """Decode and fail closed on every reserved/tag/slot invariant in a fixture."""
    if len(data) < HEADER_BYTES:
        raise Core0Error(
            f"scalar batch fixture is truncated: {len(data)} bytes, header is {HEADER_BYTES}"
        )
    words = struct.unpack("<16Q", data[:HEADER_BYTES])
    (
        magic,
        version,
        header_bytes,
        record_bytes,
        suite_id,
        batch_id,
        root_id,
        case_count,
        arg_count,
        result_tag,
        low_tags,
        high_tags,
        source_seed,
        runtime_seed,
        reserved0,
        reserved1,
    ) = words
    if magic != MAGIC_WORD or data[:8] != MAGIC_BYTES:
        raise Core0Error("scalar batch fixture has the wrong magic")
    if version != ABI_VERSION:
        raise Core0Error(f"scalar batch fixture has unsupported ABI version {version}")
    if header_bytes != HEADER_BYTES or record_bytes != RECORD_BYTES:
        raise Core0Error("scalar batch fixture declares the wrong header or record size")
    if reserved0 != 0 or reserved1 != 0:
        raise Core0Error("scalar batch fixture has nonzero reserved header words")
    if case_count == 0 or case_count > MAX_CASES:
        raise Core0Error(
            f"wire case count {case_count} is outside the supported range 1..{MAX_CASES}"
        )
    expected_size = HEADER_BYTES + case_count * RECORD_BYTES
    if len(data) != expected_size:
        raise Core0Error(
            f"scalar batch fixture length {len(data)} differs from declared exact length {expected_size}"
        )
    arg_types = _unpack_tags(low_tags, high_tags, arg_count)
    result_type = TAG_TYPES.get(result_tag)
    if result_type is None:
        raise Core0Error(f"wire result has unknown type tag {result_tag}")
    signature = ScalarSignature(arg_types, result_type)

    cases: list[ScalarCase] = []
    seen_ids: set[int] = set()
    for case_index in range(case_count):
        start = HEADER_BYTES + case_index * RECORD_BYTES
        case_id, *slots = struct.unpack("<17Q", data[start : start + RECORD_BYTES])
        if case_id in seen_ids:
            raise Core0Error(f"wire fixture has duplicate case id 0x{case_id:016x}")
        seen_ids.add(case_id)
        args = tuple(slots[:arg_count])
        if any(slots[arg_count:]):
            raise Core0Error(f"wire case #{case_index} has nonzero unused argument slots")
        for arg_index, (arg, arg_type) in enumerate(zip(args, arg_types, strict=True)):
            _validate_scalar(arg, arg_type, f"wire case #{case_index} arg #{arg_index}")
        cases.append(ScalarCase(case_id, args, result_type))
    return ParsedFixture(
        suite_id=suite_id,
        batch_id=batch_id,
        root_id=root_id,
        signature=signature,
        source_seed=source_seed,
        runtime_seed=runtime_seed,
        cases=tuple(cases),
    )


def validate_fixture(data: bytes, descriptor: ScalarBatchDescriptor) -> ParsedFixture:
    parsed = parse_fixture(data)
    expected = ParsedFixture(
        suite_id=descriptor.suite_id,
        batch_id=descriptor.batch_id,
        root_id=descriptor.root_id,
        signature=descriptor.signature,
        source_seed=descriptor.source_seed,
        runtime_seed=descriptor.runtime_seed,
        cases=descriptor.cases,
    )
    if parsed != expected:
        raise Core0Error("scalar batch fixture metadata or records differ from its host descriptor")
    return parsed


def validate_transcript(
    transcript: bytes, descriptor: ScalarBatchDescriptor
) -> tuple[ScalarResult, ...]:
    """Require the complete ordered UART transcript for one successful batch."""
    validate_descriptor(descriptor)
    lines = transcript.splitlines(keepends=True)
    expected_line_count = len(descriptor.cases) + 3
    if len(lines) != expected_line_count or any(not line.endswith(b"\n") for line in lines):
        raise Core0Error(
            "malformed or truncated scalar batch transcript: "
            + repr(transcript.decode("ascii", errors="backslashreplace"))
        )
    if lines[0] != b"LEMMA_SCALAR/1\n":
        raise Core0Error("scalar batch transcript has the wrong banner or leading noise")

    batch_match = BATCH_LINE.fullmatch(lines[1])
    if batch_match is None:
        raise Core0Error("scalar batch transcript has a malformed BATCH frame")
    batch_values = tuple(int(group, 16) for group in batch_match.groups())
    expected_batch = (
        descriptor.suite_id,
        descriptor.batch_id,
        descriptor.root_id,
        len(descriptor.cases),
    )
    if batch_values != expected_batch:
        raise Core0Error(
            f"target BATCH metadata {batch_values!r} differs from descriptor {expected_batch!r}"
        )

    expected_tag = TYPE_TAGS[descriptor.signature.result]
    results: list[ScalarResult] = []
    for index, (line, case) in enumerate(zip(lines[2:-1], descriptor.cases, strict=True)):
        result_match = RESULT_LINE.fullmatch(line)
        if result_match is None:
            raise Core0Error(f"scalar batch transcript RESULT #{index} is malformed")
        case_id, result_tag, result_value = (
            int(group, 16) for group in result_match.groups()
        )
        if case_id != case.case_id:
            raise Core0Error(
                f"target RESULT #{index} case id 0x{case_id:016x} is out of order; "
                f"expected 0x{case.case_id:016x}"
            )
        if result_tag != expected_tag:
            raise Core0Error(
                f"target RESULT #{index} type tag {result_tag} differs from expected {expected_tag}"
            )
        _validate_scalar(
            result_value,
            case.expected_result_type,
            f"target RESULT #{index}",
        )
        results.append(ScalarResult(case_id, case.expected_result_type, result_value))

    end_match = END_LINE.fullmatch(lines[-1])
    if end_match is None:
        raise Core0Error("scalar batch transcript has a malformed END frame")
    end_values = tuple(int(group, 16) for group in end_match.groups())
    expected_end = (descriptor.batch_id, len(descriptor.cases))
    if end_values != expected_end:
        raise Core0Error(
            f"target END metadata {end_values!r} differs from descriptor {expected_end!r}"
        )
    return tuple(results)


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def validate_image_binding(image: Path, descriptor: ScalarBatchDescriptor) -> None:
    """Bind a descriptor to the exact typed-suite metadata next to its image."""
    validate_descriptor(descriptor)
    directory = image.parent
    manifest = load_json(directory / "scalar-suite-manifest.json")
    abi = load_json(directory / "scalar-test-abi.json")
    provenance = load_json(directory / "provenance.json")
    build_record = load_json(directory / "build.json")
    if not isinstance(manifest, dict):
        raise Core0Error("image scalar-suite manifest is not an object")
    artifact_category = manifest.get("artifact_category")
    expected_profile = IMAGE_ARTIFACT_PROFILES.get(artifact_category)
    if expected_profile is None:
        raise Core0Error("image scalar-suite manifest has the wrong artifact category")
    if manifest.get("contract_version") != expected_profile:
        raise Core0Error("image scalar-suite manifest profile disagrees with its artifact category")
    if not isinstance(abi, dict) or abi.get("name") != "lemma-scalar-test-v1":
        raise Core0Error("image scalar test ABI manifest is missing or unsupported")
    if abi.get("contract_version") != expected_profile:
        raise Core0Error("image scalar test ABI profile disagrees with its artifact category")
    if (
        not isinstance(provenance, dict)
        or provenance.get("artifact_category") != artifact_category
        or not isinstance(build_record, dict)
        or build_record.get("artifact_category") != artifact_category
    ):
        raise Core0Error("image provenance/build category disagrees with the suite manifest")

    identities = (
        ("suite_id", descriptor.suite_id),
        ("source_seed", descriptor.source_seed),
        ("runtime_seed", descriptor.runtime_seed),
    )
    for field, expected in identities:
        rendered = f"{expected:016x}"
        if manifest.get(field) != rendered or abi.get(field) != rendered:
            raise Core0Error(f"image {field} differs from the scalar batch descriptor")

    roots = manifest.get("roots")
    if not isinstance(roots, list):
        raise Core0Error("image scalar-suite manifest has no root catalog")
    matching = [
        item
        for item in roots
        if isinstance(item, dict) and item.get("root_id") == descriptor.root_id
    ]
    if len(matching) != 1:
        raise Core0Error("descriptor root ID does not select exactly one image root")
    selected = matching[0]
    expected_signature = {
        "args": list(descriptor.signature.args),
        "result": descriptor.signature.result,
    }
    if selected.get("source") != descriptor.root or selected.get("signature") != expected_signature:
        raise Core0Error("descriptor root identity/signature differs from the selected image root")

    artifacts = build_record.get("artifacts")
    if not isinstance(artifacts, dict):
        raise Core0Error("image build record has no artifact hashes")
    for name in ("image.elf", "scalar-suite-manifest.json", "scalar-test-abi.json"):
        expected_digest = artifacts.get(name)
        path = directory / name
        if not isinstance(expected_digest, str) or expected_digest != sha256(path):
            raise Core0Error(f"image build-record hash mismatch for {name}")


def _descriptor_json(descriptor: ScalarBatchDescriptor) -> dict[str, object]:
    return {
        "schema_version": 1,
        "suite_id": f"0x{descriptor.suite_id:016x}",
        "batch_id": f"0x{descriptor.batch_id:016x}",
        "root": descriptor.root,
        "root_id": f"0x{descriptor.root_id:016x}",
        "signature": {
            "args": list(descriptor.signature.args),
            "result": descriptor.signature.result,
        },
        "source_seed": f"0x{descriptor.source_seed:016x}",
        "runtime_seed": f"0x{descriptor.runtime_seed:016x}",
        "cases": [
            {
                "case_id": f"0x{case.case_id:016x}",
                "args": [f"0x{arg:016x}" for arg in case.args],
                "expected_result_type": case.expected_result_type,
            }
            for case in descriptor.cases
        ],
    }


def _batch_identity_stem(descriptor: object) -> str | None:
    """Return a safe record identity before full descriptor validation, if possible."""
    if not isinstance(descriptor, ScalarBatchDescriptor):
        return None
    values = (descriptor.suite_id, descriptor.batch_id)
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > U64_MAX
        for value in values
    ):
        return None
    return f"{descriptor.suite_id:016x}-{descriptor.batch_id:016x}"


def _runtime_input_region(image: Path) -> tuple[int, int]:
    layout = load_json(image.parent / "layout.json")
    if not isinstance(layout, dict) or not isinstance(layout.get("input"), dict):
        raise Core0Error("layout.json does not declare the runtime-input region")
    input_start = layout["input"].get("start")
    input_size = layout["input"].get("size")
    if not isinstance(input_start, str) or not isinstance(input_size, str):
        raise Core0Error("layout runtime-input address/size are malformed")
    try:
        input_address = int(input_start, 0)
        input_capacity = int(input_size, 0)
    except ValueError as error:
        raise Core0Error("layout runtime-input address/size are malformed") from error
    if input_address < 0 or input_capacity < 0:
        raise Core0Error("layout runtime-input address/size are malformed")
    return input_address, input_capacity


def _qemu_argv(image: Path, fixture: Path, input_address: int) -> tuple[str, ...]:
    """Return the one pinned scalar-test QEMU invocation used by both test paths."""
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
        f"loader,file={fixture},addr=0x{input_address:x},force-raw=on",
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


def run_batch(
    *,
    root: Path,
    image: Path,
    output_dir: Path,
    descriptor: ScalarBatchDescriptor,
    timeout_seconds: float,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _batch_identity_stem(descriptor)
    record_path = output_dir / f"run-{stem}.json" if stem is not None else None
    # Invalidate a prior PASS before any image, metadata, capacity, tool, or
    # descriptor/process preflight whenever the closed identity itself is usable.
    if record_path is not None:
        record_path.unlink(missing_ok=True)
    validate_descriptor(descriptor)
    assert stem is not None and record_path is not None
    require_tools(("qemu-system-riscv64",))
    if not image.is_file():
        raise Core0Error(f"target image is missing: {image}")
    validate_image_binding(image, descriptor)
    input_address, input_capacity = _runtime_input_region(image)

    fixture_bytes = pack_fixture(descriptor)
    if len(fixture_bytes) > input_capacity:
        raise Core0Error(
            f"scalar batch fixture is {len(fixture_bytes)} bytes, exceeding input capacity {input_capacity}"
        )
    fixture = output_dir / f"input-{stem}.bin"
    fixture.write_bytes(fixture_bytes)
    uart_path = output_dir / f"uart-{stem}.bin"
    stderr_path = output_dir / f"qemu-{stem}.stderr"
    argv = _qemu_argv(image, fixture, input_address)
    result: CommandResult = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    uart_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    if result.returncode != 0:
        raise Core0Error(
            f"QEMU process failure: exited with {result.returncode}; stderr: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    if result.stderr:
        raise Core0Error(
            "QEMU process wrote unexpected stderr on a zero exit: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    results = validate_transcript(result.stdout, descriptor)
    record: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "abi": "LEMMA_SCALAR/1",
        "descriptor": _descriptor_json(descriptor),
        "fixture": _relative_or_absolute(fixture, root),
        "fixture_sha256": sha256(fixture),
        "image": _relative_or_absolute(image, root),
        "image_sha256": sha256(image),
        "qemu_argv": list(argv),
        "qemu_returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "uart": result.stdout.decode("ascii"),
        "uart_sha256": sha256(uart_path),
        "results": [
            {
                "case_id": f"0x{item.case_id:016x}",
                "result_type": item.result_type,
                "value": f"0x{item.value:016x}",
            }
            for item in results
        ],
    }
    write_json(record_path, record)
    return record


def run_malformed_fixture_for_test(
    *,
    root: Path,
    image: Path,
    output_dir: Path,
    binding_descriptor: ScalarBatchDescriptor,
    raw_fixture: bytes,
    case_name: str,
    announced: bool,
    timeout_seconds: float,
) -> dict[str, object]:
    """Run one deliberately malformed fixture and require guest rejection.

    This API is intentionally test-only and is not reachable from ``main``.  The
    valid descriptor binds the exact image, provenance, suite, roots, and seeds;
    only ``raw_fixture`` bypasses the normal host fixture parser so target-side
    rejection can be exercised.  A process error or merely nonzero exit is not
    accepted as the intended rejection: the SiFive test device must report guest
    failure code 1 with empty stderr.  ``announced`` selects one of two closed
    UART outcomes: either the sole error frame for a rejected header/signature,
    or the exact bound banner and BATCH frame followed by the error for a record
    rejected after announcement.  Neither outcome permits RESULT or END frames.
    """
    if not isinstance(case_name, str) or MALFORMED_CASE_NAME.fullmatch(case_name) is None:
        raise Core0Error(
            "malformed-fixture test case name must match [a-z0-9][a-z0-9_-]{0,63}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    identity = _batch_identity_stem(binding_descriptor)
    stem = f"{identity}-{case_name}" if identity is not None else None
    record_path = (
        output_dir / f"malformed-run-{stem}.json" if stem is not None else None
    )
    # As with normal runs, invalidate old evidence before tool, image, metadata,
    # layout, capacity, or process preflight can fail.
    if record_path is not None:
        record_path.unlink(missing_ok=True)
    validate_descriptor(binding_descriptor)
    assert stem is not None and record_path is not None

    if not isinstance(raw_fixture, bytes):
        raise Core0Error("malformed-fixture test input must be raw bytes")
    if not isinstance(announced, bool):
        raise Core0Error("malformed-fixture announced state must be a Boolean")
    if raw_fixture == pack_fixture(binding_descriptor):
        raise Core0Error(
            "malformed-fixture test input is the valid fixture for its binding descriptor"
        )

    require_tools(("qemu-system-riscv64",))
    if not image.is_file():
        raise Core0Error(f"target image is missing: {image}")
    validate_image_binding(image, binding_descriptor)
    input_address, input_capacity = _runtime_input_region(image)
    if len(raw_fixture) > input_capacity:
        raise Core0Error(
            f"malformed scalar fixture is {len(raw_fixture)} bytes, "
            f"exceeding input capacity {input_capacity}"
        )

    fixture = output_dir / f"malformed-input-{stem}.bin"
    fixture.write_bytes(raw_fixture)
    uart_path = output_dir / f"malformed-uart-{stem}.bin"
    stderr_path = output_dir / f"malformed-qemu-{stem}.stderr"
    argv = _qemu_argv(image, fixture, input_address)
    result: CommandResult = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    uart_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)

    if result.returncode != GUEST_FAILURE_RETURNCODE:
        raise Core0Error(
            "malformed fixture did not produce the exact guest failure termination: "
            f"QEMU exit {result.returncode}, expected {GUEST_FAILURE_RETURNCODE}"
        )
    if result.stderr:
        raise Core0Error(
            "QEMU wrote unexpected stderr during malformed-fixture guest rejection: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    expected_uart = TYPED_INPUT_ERROR
    if announced:
        expected_uart = (
            b"LEMMA_SCALAR/1\n"
            + (
                "BATCH:"
                f"{binding_descriptor.suite_id:016x}:"
                f"{binding_descriptor.batch_id:016x}:"
                f"{binding_descriptor.root_id:016x}:"
                f"{len(binding_descriptor.cases):016x}\n"
            ).encode("ascii")
            + TYPED_INPUT_ERROR
        )
    if result.stdout != expected_uart:
        raise Core0Error(
            "malformed fixture produced the wrong or misleading UART output: "
            + repr(result.stdout.decode("ascii", errors="backslashreplace"))
        )

    record: dict[str, object] = {
        "schema_version": 1,
        "status": "expected-guest-rejection",
        "reason": "typed-input",
        "announced": announced,
        "abi": "LEMMA_SCALAR/1",
        "case_name": case_name,
        "binding_descriptor": _descriptor_json(binding_descriptor),
        "fixture": _relative_or_absolute(fixture, root),
        "fixture_sha256": sha256(fixture),
        "image": _relative_or_absolute(image, root),
        "image_sha256": sha256(image),
        "qemu_argv": list(argv),
        "qemu_returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "uart": result.stdout.decode("ascii"),
        "uart_sha256": sha256(uart_path),
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
        record = run_batch(
            root=root,
            image=resolve(ns.image),
            output_dir=resolve(ns.output_dir),
            descriptor=descriptor,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"SCALAR BATCH RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(record["uart"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
