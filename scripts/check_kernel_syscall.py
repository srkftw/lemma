#!/usr/bin/env python3
"""Bounded E observations of ordinary U syscalls and complete binary UART data.

K1 controls and notifications are parsed only at call boundaries. Binary output
is read at its exact announced length; its interior bytes are never searched for
control markers. These host checks are observations, not compiler proofs.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import secrets
import struct

from core0_common import Core0Error, repo_root, sha256, write_json
from run_kernel import Session, RECORD_BYTES, parse_record, transport
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import MASK, USER_STATUS, mix, satp, task_frame_overhead

DEFAULT_SEEDS = (0x4c454d4d41453101, 0, MASK)
E1_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
          20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
          40, 41, 42, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 421}


def payload(seed: int, length: int) -> bytes:
    if type(seed) is not int or not 0 <= seed <= MASK or type(length) is not int or not 2 <= length <= 256:
        raise Core0Error("binary dataset requires unsigned64 seed and 2..256 bytes")
    return bytes(0 if index == 0 else 255 if index == 1 else
                 ((seed >> (((index - 2) % 8) * 8)) & 255) ^ ((index * 17) & 255)
                 for index in range(length))


def validate_notification(event: tuple[int, ...], installed: int, ranges: dict) -> None:
    if (len(event) != 5 or event[0:2] != (0xdf, 0x8000000000000001)
            or type(event[2]) is not int or event[2] % 4 or event[3:] != (USER_STATUS, installed)
            or not any(isinstance(row, dict) and type(row.get("base")) is int and type(row.get("bytes")) is int
                       and row["base"] <= event[2] < row["base"] + row["bytes"] for row in ranges.values())):
        raise Core0Error("syscall IRQ notification lacks actual owned U context")


def validate_wire_segments(received: bytes, records: list, segments: list) -> None:
    """Require every raw byte to belong to one complete observed wire event."""
    if not segments or not records:
        raise Core0Error("mixed UART evidence requires controls and a nonempty segment inventory")
    offset, observed = 0, []
    for row in segments:
        if (not isinstance(row, dict) or type(row.get("offset")) is not int or row["offset"] != offset
                or type(row.get("bytes")) is not int or row["bytes"] <= 0):
            raise Core0Error("mixed UART segment coverage is missing, overlapping or unordered")
        end = offset + row["bytes"]
        raw = received[offset:end]
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row.get("sha256"):
            raise Core0Error("mixed UART segment is incomplete or changed")
        if row.get("kind") == "record":
            value = list(parse_record(raw))
            if row.get("values") != value:
                raise Core0Error("mixed UART control differs from its actual raw bytes")
            observed.append(value)
        elif row.get("kind") == "payload":
            if not 2 <= len(raw) <= 256 or raw[:2] != b"\0\xff" or row.get("hex") != raw.hex():
                raise Core0Error("mixed UART binary payload lacks exact bounded raw bytes")
        else:
            raise Core0Error("unknown mixed UART segment kind")
        offset = end
    if offset != len(received) or observed != records:
        raise Core0Error("mixed UART raw coverage/control sequence differs")


class MixedWire:
    def __init__(self, session: Session):
        self.session = session
        self.segments = []
        # Existing supervisor startup checks use the maintained record reader.
        raw = bytes(session.capture.received)
        if len(raw) != RECORD_BYTES * len(session.records):
            raise Core0Error("startup raw bytes do not match complete K1 controls")
        for index, record in enumerate(session.records):
            piece = raw[index * RECORD_BYTES:(index + 1) * RECORD_BYTES]
            if list(parse_record(piece)) != record:
                raise Core0Error("startup control/raw identity differs")
            self._segment(index * RECORD_BYTES, piece, "record", values=record)

    def _segment(self, offset: int, raw: bytes, kind: str, **fields):
        self.segments.append({"offset": offset, "bytes": len(raw), "kind": kind,
                              "sha256": hashlib.sha256(raw).hexdigest(), **fields})

    def read(self, expected_payload: bytes | None = None):
        session = self.session
        offset = len(session.capture.received)
        first = transport._read_exact(session.process, 1, deadline=session.deadline,
                                      capture=session.capture, context="reading syscall wire boundary")
        if first == b"K":
            raw = first + transport._read_exact(session.process, RECORD_BYTES - 1, deadline=session.deadline,
                                                capture=session.capture, context="reading syscall K1 control")
            record = parse_record(raw)
            session.records.append(list(record))
            self._segment(offset, raw, "record", values=list(record))
            return record
        if expected_payload is None or first != b"\0" or not 2 <= len(expected_payload) <= 256:
            raise Core0Error("unexpected binary byte at a syscall control boundary")
        raw = first + transport._read_exact(session.process, len(expected_payload) - 1, deadline=session.deadline,
                                            capture=session.capture, context="reading complete syscall binary payload")
        if raw != expected_payload or raw[:2] != b"\0\xff":
            raise Core0Error("actual syscall binary payload differs from independent expected bytes")
        self._segment(offset, raw, "payload", hex=raw.hex())
        return raw

    def send(self, raw: bytes):
        transport._write_all(self.session.process, raw, deadline=self.session.deadline,
                             capture=self.session.capture, context="sending fresh syscall input")


def validate_input_reads(rows: dict, positions: dict, *, seed: int, input_bytes: bytes) -> dict:
    """Separate the observed first crossing call from any completion reads."""
    first = rows[(0xe4, 43)]
    if len(input_bytes) != 16 or first[:3] != (0xe4, 43, 0) or first[4] != seed or not 9 <= first[3] <= 16:
        raise Core0Error("first successful input call did not itself cross the page boundary")
    keys = sorted(key for key in rows if key[0] == 0xe4 and 430 <= key[1] <= 436)
    if [key[1] for key in keys] != list(range(430, 430 + len(keys))):
        raise Core0Error("input completion identifiers are missing or unordered")
    total, previous, completion = first[3], positions[(0xe4, 43)], []
    for key in keys:
        event = rows[key]
        remaining = 16 - total
        if (event[:3] != (0xe4, key[1], 0) or event[4] != seed or not 1 <= event[3] <= remaining
                or not previous < positions[key] < positions[(0xe2, 44)]):
            raise Core0Error("input completion lacks a positive bounded actual count in recovery order")
        completion.append({"case_id": key[1], "requested_bytes": remaining, "actual_bytes": event[3]})
        total += event[3]; previous = positions[key]
    if total != len(input_bytes):
        raise Core0Error("actual first and completion reads did not receive the entire independent payload")
    return {"short_read_bytes": first[3], "completion_reads": completion, "complete_input_bytes": total,
            "successful_cross_page_input": {"pointer": 0x40ff8, "requested_bytes": 32,
                                             "actual_bytes": first[3], "spanned_pages": 2}}


def validate_cases(events: list[tuple[int, ...]], *, seed: int, identity: int, input_bytes: bytes) -> dict:
    if not events or len(events) > 128:
        raise Core0Error("syscall case corpus must be finite and nonempty")
    rows, positions = {}, {}
    for index, event in enumerate(events):
        if len(event) != 5 or any(type(word) is not int or not 0 <= word <= MASK for word in event) or event[4] != seed:
            raise Core0Error("syscall control lacks exact unsigned words/runtime seed")
        key = event[:2]
        if key in rows:
            raise Core0Error("syscall case/control repeated")
        rows[key], positions[key] = event, index
    required = {(0xe0, 1), (0xee, 0)} | {(0xe1, case) for case in E1_IDS}
    required |= {(0xe2, case) for case in (40, 44, 62)} | {(0xe3, 42)}
    required |= {(0xe4, case) for case in (420, 43)} | {(0xe5, case) for case in (50, 51, 42, 52)}
    completions = {key for key in rows if key[0] == 0xe4 and 430 <= key[1] <= 436}
    if set(rows) - completions != required or rows[(0xe0, 1)] != (0xe0, 1, 0, identity, seed) or rows[(0xee, 0)] != (0xee, 0, 0, mix(seed), seed):
        raise Core0Error("syscall controls omit cases or differ from actual identity/final result")
    fixed = {1: (0, identity), 3: (17, 0), 4: (0, 0), 5: (22, 0), 6: (22, 0), 7: (22, 0), 20: (0, 0x40000),
             21: (73, 0), 22: (71, 0), 23: (71, 0), 24: (71, 0), 25: (16, 0), 26: (74, 0),
             27: (0, 0x41000), 28: (0, 0x41000), 29: (74, 0), 30: (0, 0x40000), 31: (0, 0x40000),
             32: (0, 0x40000), 33: (16, 0), 40: (0, 16), 41: (74, 0), 42: (74, 0), 44: (0, 16),
             45: (0, 0), 46: (0, 0), 47: (16, 0), 48: (16, 0), 49: (71, 0), 50: (71, 0),
             51: (71, 0), 52: (71, 0), 53: (72, 0), 54: (74, 0), 55: (74, 0), 56: (74, 0),
             57: (74, 0), 58: (17, 0), 59: (16, 0), 60: (0, identity), 61: (12, 0), 62: (0, 256),
             63: (0, 0x41000), 64: (0, 0x41000)}
    for case, expected in fixed.items():
        if rows[(0xe1, case)][2:4] != expected:
            raise Core0Error(f"actual syscall status/value differs for case {case}")
    for case in (2, 8, 9, 10, 11, 12, 13, 421):
        if rows[(0xe1, case)][2] != 0 or rows[(0xe1, case)][3] == 0:
            raise Core0Error("time/sleep lacks its actual nonzero successful result")
    for before, sleep, after, ticks in ((8, 9, 10, 1000), (11, 12, 13, 1000000)):
        if (not positions[(0xe1, before)] < positions[(0xe1, sleep)] < positions[(0xe1, after)]
                or not rows[(0xe1, before)][3] + ticks <= rows[(0xe1, sleep)][3] <= rows[(0xe1, after)][3]):
            raise Core0Error("actual monotonic time/deadline sequence differs")
    for case, length in ((40, 16), (44, 16), (62, 256)):
        if rows[(0xe2, case)] != (0xe2, case, 0, length, seed):
            raise Core0Error("binary ready record differs from exact output length")
    if rows[(0xe3, 42)] != (0xe3, 42, 0, 17, seed) or rows[(0xe4, 420)] != (0xe4, 420, 0, 1, seed):
        raise Core0Error("actual input readiness/ACK counts differ")
    reads = validate_input_reads(rows, positions, seed=seed, input_bytes=input_bytes)
    for case, expected in ((50, 0), (51, seed), (42, seed ^ 0x0123456789abcdef), (52, 0)):
        if rows[(0xe5, case)] != (0xe5, case, 0, expected, seed):
            raise Core0Error("actual zeroing/nonce/all-or-nothing destination witness differs")
    ordered = [(0xe1, 61), (0xe3, 42), (0xe4, 420), (0xe1, 421), (0xe1, 42), (0xe5, 42),
               (0xe1, 63), (0xe4, 43), (0xe2, 44), (0xe1, 44), (0xe1, 64)]
    if any(positions[left] >= positions[right] for left, right in zip(ordered, ordered[1:])):
        raise Core0Error("input readiness/rejection/nonconsumption/recovery order differs")
    if positions[(0xe0, 1)] != 0 or positions[(0xee, 0)] != len(events) - 1:
        raise Core0Error("syscall startup/final controls occur out of order")
    return {"case_count": len(E1_IDS), "control_count": len(events), "actual_status_values": [list(row) for row in events],
            "maximum_copy_bytes": 256, "sleep_evidence": "deadline-validation-only", **reads}


def check(session: Session, *, seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    if (session.binding.get("configuration") != "user-syscall-development" or session.binding.get("stage") != "supervisor"
            or not seeds or len(seeds) > 8 or any(type(seed) is not int or not 0 <= seed <= MASK for seed in seeds)):
        raise Core0Error("E checker requires exact syscall development image and bounded runtime seeds")
    startup = validate_positive_records([session.record() for _ in range(4)])
    kernel = session.record()
    if kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0):
        raise Core0Error("installed kernel root/baseline differs")
    user = session.binding.get("elf", {}).get("user", {})
    ranges = user.get("function_ranges", {})
    syscall_pc = user.get("syscall_bridge", {}).get("ecall_pc")
    if type(syscall_pc) is not int or not isinstance(ranges, dict) or not ranges:
        raise Core0Error("audited ordinary user syscall ECALL/function ranges missing")
    def user_pc(pc):
        return type(pc) is int and pc % 4 == 0 and any(row["base"] <= pc < row["base"] + row["bytes"] for row in ranges.values())
    if not user_pc(syscall_pc):
        raise Core0Error("ordinary syscall PC escapes audited user code")
    text_file = session.image.parent / "user-text.bin"
    text_hash, text_bytes = sha256(text_file), text_file.stat().st_size
    if not 0 < text_bytes <= 0xf000:
        raise Core0Error("user E text length is outside the loader envelope")
    before_teardown = 500 - task_frame_overhead(session) - (text_bytes + 4095) // 4096
    wire, cases, descriptors = MixedWire(session), [], set()
    for seed in seeds:
        wire.send(struct.pack("<5Q", 1, seed, 0, 0, 0))
        loaded = wire.read()
        if (not isinstance(loaded, tuple) or loaded[0] != 0xd0 or loaded[1] < 512 or loaded[1] in descriptors
                or loaded[2] == kernel[1] or loaded[3:] != (0x10000, text_bytes)):
            raise Core0Error("syscall run lacks fresh owned user load facts")
        descriptors.add(loaded[1]); installed = satp(loaded[2])
        inputs = b"\0\xff" + secrets.token_bytes(14)
        notifications, events, binary = [], [], []
        def next_event(expected_payload=None):
            event = wire.read(expected_payload)
            while isinstance(event, tuple) and event[0] == 0xdf:
                if len(notifications) >= 128:
                    raise Core0Error("syscall notification corpus exceeded its finite bound")
                validate_notification(event, installed, ranges)
                notifications.append(list(event)); event = wire.read(expected_payload)
            return event
        for _ in range(128):
            event = next_event()
            if not isinstance(event, tuple) or event[0] not in {0xe0, 0xe1, 0xe2, 0xe3, 0xe4, 0xe5, 0xee}:
                raise Core0Error("unexpected syscall test control or premature fault/exit")
            events.append(event)
            if event[0] == 0xe2:
                expected = payload(seed, {40: 16, 62: 256}.get(event[1], 16)) if event[1] in {40, 62} else inputs if event[1] == 44 else None
                if expected is None or event[2:] != (0, len(expected), seed) or next_event(expected) != expected:
                    raise Core0Error("syscall ready/payload boundary differs")
                binary.append({"case_id": event[1], "bytes": len(expected), "sha256": hashlib.sha256(expected).hexdigest()})
            elif event[0] == 0xe3:
                if event != (0xe3, 42, 0, 17, seed) or sum(row[0] == 0xe3 for row in events) != 1:
                    raise Core0Error("syscall input readiness differs or repeats")
                wire.send(b"\xa5" + inputs)
            elif event[0] == 0xee:
                break
        else:
            raise Core0Error("syscall finite corpus did not reach its final record")
        observed = validate_cases(events, seed=seed, identity=loaded[1], input_bytes=inputs)
        terminal = next_event()
        if terminal != (0xd1, 8, syscall_pc, USER_STATUS, installed):
            raise Core0Error("ordinary library exit lacks actual user ECALL/PC/status/SATP")
        returned = wire.read()
        if returned != (0xd2, (seed & 15) + 1, mix(seed), before_teardown, 500):
            raise Core0Error("syscall exit/data/complete frame teardown differs")
        cases.append({"runtime_seed": seed, "input_hex": inputs.hex(), "input_sha256": hashlib.sha256(inputs).hexdigest(),
                      "loaded": list(loaded), "supervisor_notifications": notifications, "binary_outputs": binary,
                      "exit_trap": list(terminal), "returned": list(returned), **observed})
    validate_wire_segments(bytes(session.capture.received), session.records, wire.segments)
    if sha256(text_file) != text_hash:
        raise Core0Error("user E text changed during observation")
    session.report.update(wire_format="kernel-mixed-uart-v1", wire_segments=wire.segments)
    return {"protocol": "user-E-syscalls-v1", "supervisor_startup": startup, "kernel_address_space": list(kernel),
            "fresh_user_runs": len(cases), "cases": cases, "user_text_sha256": text_hash,
            "actual_user_supervisor_notifications": sum(len(case["supervisor_notifications"]) for case in cases),
            "baseline_available_frames": 500, "scheduling": "not_run", "blocking_sleep": "not_run"}


def runner_inputs(root):
    return {name: sha256(root / name) for name in ("scripts/check_kernel_syscall.py", "scripts/check_kernel_supervisor.py",
            "scripts/check_kernel_user.py", "scripts/run_kernel.py", "scripts/run_device_session.py", "scripts/run_monitor_session.py")}


def validate_after_cleanup(session: Session) -> None:
    """Cleanup may drain stdout; revalidate the complete retained transcript."""
    try:
        raw = (session.output_dir / "received.bin").read_bytes()
        if sha256(session.output_dir / "received.bin") != session.report.get("raw_artifacts", {}).get("received.bin"):
            raise Core0Error("retained syscall UART bytes differ from actual cleanup hash")
        validate_wire_segments(raw, session.report["records"], session.report.get("wire_segments"))
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        session.report.update(status="FAIL", error=str(error), failure_category="post-cleanup-wire-evidence")
        temporary = session.output_dir / "result.json.tmp"
        write_json(temporary, session.report)
        temporary.replace(session.output_dir / "result.json")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root, runners = repo_root(), runner_inputs(repo_root())
        with Session(root=root, image=args.image, output_dir=args.output_dir, timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session, seeds=tuple(args.seed) if args.seed is not None else DEFAULT_SEEDS)
            if runner_inputs(root) != runners:
                raise Core0Error("syscall observation runner changed during the run")
            session.finish(observed)
        validate_after_cleanup(session)
        print(f"PASS: {observed['fresh_user_runs']} fresh U syscall corpora, actual binary data/return/reclamation; QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__": raise SystemExit(main())
