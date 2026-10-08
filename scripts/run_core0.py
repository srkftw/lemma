#!/usr/bin/env python3
"""Run one bounded LemmaVM Core0 case and validate its complete UART frame."""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

from core0_common import Core0Error, load_json, require_tools, repo_root, run_bounded, sha256, write_json


INPUT_MAGIC = 0x313030414D4D454C  # little-endian bytes: LEMMA001
FRAME = re.compile(
    rb"LEMMA_CORE0/1\nRESULT:([0-9a-f]{16}):([0-9a-f]{16})\n"
)


def parse_u64(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid UInt64: {text}") from error
    if value < 0 or value > 0xFFFFFFFFFFFFFFFF:
        raise argparse.ArgumentTypeError(f"UInt64 out of range: {text}")
    return value


def validate_transcript(transcript: bytes, expected_case_id: int) -> int:
    match = FRAME.fullmatch(transcript)
    if match is None:
        raise Core0Error(
            "malformed or truncated target transcript: "
            + repr(transcript.decode("ascii", errors="backslashreplace"))
        )
    case_id = int(match.group(1), 16)
    if case_id != expected_case_id:
        raise Core0Error(
            f"target returned case id 0x{case_id:016x}, expected 0x{expected_case_id:016x}"
        )
    return int(match.group(2), 16)


def run_case(
    *,
    root: Path,
    image: Path,
    output_dir: Path,
    case_id: int,
    args: tuple[int, int, int],
    timeout_seconds: float,
) -> dict[str, object]:
    require_tools(("qemu-system-riscv64",))
    if not image.is_file():
        raise Core0Error(f"target image is missing: {image}")
    layout = load_json(image.parent / "layout.json")
    if not isinstance(layout, dict) or not isinstance(layout.get("input"), dict):
        raise Core0Error("layout.json does not declare the runtime-input region")
    input_start = layout["input"].get("start")
    input_size = layout["input"].get("size")
    if not isinstance(input_start, str) or not isinstance(input_size, str):
        raise Core0Error("layout runtime-input address/size are malformed")
    input_address = int(input_start, 0)
    input_capacity = int(input_size, 0)
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture = output_dir / f"input-{case_id:016x}.bin"
    fixture.write_bytes(struct.pack("<QQQQQ", INPUT_MAGIC, case_id, *args))
    if fixture.stat().st_size > input_capacity:
        raise Core0Error("runtime fixture exceeds the declared input region")
    argv = (
        "qemu-system-riscv64",
        "-machine", "virt,acpi=off",
        "-accel", "tcg",
        "-cpu", "rv64",
        "-smp", "1",
        "-m", "128M",
        "-bios", "none",
        "-kernel", str(image),
        "-device", f"loader,file={fixture},addr=0x{input_address:x},force-raw=on",
        "-nodefaults",
        "-nic", "none",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-no-reboot",
        "-seed", "1",
    )
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds)
    transcript_path = output_dir / f"uart-{case_id:016x}.bin"
    transcript_path.write_bytes(result.stdout)
    stderr_path = output_dir / f"qemu-{case_id:016x}.stderr"
    stderr_path.write_bytes(result.stderr)
    if result.returncode != 0:
        raise Core0Error(
            f"QEMU exited with {result.returncode}; stderr: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    if result.stderr:
        raise Core0Error(
            "QEMU wrote unexpected stderr on a successful run: "
            + result.stderr.decode("utf-8", errors="replace")
        )
    value = validate_transcript(result.stdout, case_id)
    record: dict[str, object] = {
        "schema_version": 1,
        "case_id": f"0x{case_id:016x}",
        "args": [f"0x{value_:016x}" for value_ in args],
        "result": f"0x{value:016x}",
        "fixture": str(fixture.relative_to(root)),
        "fixture_sha256": sha256(fixture),
        "image": str(image.relative_to(root)),
        "image_sha256": sha256(image),
        "qemu_argv": list(argv),
        "qemu_returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "uart": result.stdout.decode("ascii"),
        "uart_sha256": sha256(transcript_path),
    }
    write_json(output_dir / f"run-{case_id:016x}.json", record)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--case-id", type=parse_u64, required=True)
    parser.add_argument("--arg", type=parse_u64, action="append", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    ns = parser.parse_args()
    if len(ns.arg) != 3:
        parser.error("exactly three --arg values are required")
    root = repo_root()
    try:
        record = run_case(
            root=root,
            image=(root / ns.image).resolve() if not ns.image.is_absolute() else ns.image,
            output_dir=(root / ns.output_dir).resolve()
            if not ns.output_dir.is_absolute()
            else ns.output_dir,
            case_id=ns.case_id,
            args=tuple(ns.arg),
            timeout_seconds=ns.timeout,
        )
    except Core0Error as error:
        print(f"CORE0 RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(record["uart"], end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
