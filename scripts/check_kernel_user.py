#!/usr/bin/env python3
"""Bounded positive Sv39 user execution and teardown observations.

Every result is bound to a freshly audited normal image. This initial protocol
observes its separately linked U program, actual traps/data and frame recovery;
adversarial isolation cases and scheduling require their own later evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from core0_common import Core0Error, repo_root, sha256
from run_kernel import Session
from check_kernel_supervisor import check as check_supervisor

MASK = 2**64 - 1
USER_STATUS = 0x200000020
DEFAULT_ARGUMENTS = (0, 7, MASK)


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in (
        "scripts/check_kernel_user.py", "scripts/check_kernel_supervisor.py", "scripts/run_kernel.py",
        "scripts/run_device_session.py", "scripts/run_monitor_session.py")}


def satp(root: int) -> int:
    if type(root) is not int or not 0x82000000 <= root < 0x82200000 or root % 4096:
        raise Core0Error("reported address-space root is outside the aligned owned frame pool")
    return 0x8000000000000000 | (root >> 12)


def mix(argument: int) -> int:
    return ((argument ^ 0x4c454d4d41) * 17 + 3) & MASK


def task_frame_overhead(session: Session) -> int:
    stack = session.binding.get("task_kernel_stack", {})
    if (not isinstance(stack, dict) or type(stack.get("pages")) is not int or stack["pages"] != 2
            or type(stack.get("bytes")) is not int or stack["bytes"] != 4096 * stack["pages"]
            or stack.get("construction") != "owned-physically-contiguous-pair"
            or stack.get("base_owned_task_frames") != 15 + stack["pages"]):
        raise Core0Error("task accounting lacks audited owned two-page kernel stack construction")
    return stack["base_owned_task_frames"]


def _word_record(value: tuple[int, ...]) -> None:
    if len(value) != 5 or any(type(word) is not int or not 0 <= word <= MASK for word in value):
        raise Core0Error("user observation must contain exactly five unsigned64 words")


def check(session: Session, *, arguments: tuple[int, ...] = DEFAULT_ARGUMENTS) -> dict:
    if not arguments or len(arguments) > 16 or any(type(word) is not int or not 0 <= word <= MASK for word in arguments):
        raise Core0Error("user observation requires 1..16 unsigned64 runtime arguments")
    startup = check_supervisor(session)
    kernel = session.record()
    _word_record(kernel)
    if kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0):
        raise Core0Error(f"installed kernel address-space facts differ: {kernel}")
    user = session.binding.get("elf", {}).get("user", {})
    exit_pc = user.get("exit_ecall_pc")
    ranges = user.get("function_ranges")
    if type(exit_pc) is not int or not isinstance(ranges, dict) or not ranges:
        raise Core0Error("audited user exit PC/function ranges are missing")
    text_file = session.image.parent / "user-text.bin"
    text_digest, text_bytes = sha256(text_file), text_file.stat().st_size
    if not 0 < text_bytes <= 0xf000:
        raise Core0Error("audited user text size is outside the fixed loader format")

    def user_pc(pc: int) -> bool:
        return pc % 4 == 0 and any(isinstance(row, dict) and type(row.get("base")) is int and type(row.get("bytes")) is int
                                  and row["base"] <= pc < row["base"] + row["bytes"] for row in ranges.values())

    if not user_pc(exit_pc):
        raise Core0Error("audited exit ECALL PC lies outside user executable function ranges")
    cases, descriptors = [], set()
    text_pages = (text_bytes + 4095) // 4096
    overhead = task_frame_overhead(session)
    remaining_before = 500 - (overhead + text_pages)
    for argument in arguments:
        loaded = session.command(1, argument, 0, 0, 0)
        _word_record(loaded)
        if (loaded[0] != 0xd0 or loaded[1] < 512 or loaded[1] in descriptors or loaded[3:] != (0x10000, text_bytes)
                or loaded[2] == kernel[1]):
            raise Core0Error(f"fresh user descriptor/root/entry/text facts differ: {loaded}")
        descriptors.add(loaded[1])
        installed = satp(loaded[2])
        forwarded = []
        terminal = session.record()
        _word_record(terminal)
        while terminal[0] == 0xdf:
            if len(forwarded) >= 32 or terminal[1] != 0x8000000000000001 or not user_pc(terminal[2]) or terminal[3:] != (USER_STATUS, installed):
                raise Core0Error(f"actual U-mode supervisor notification context differs: {terminal}")
            forwarded.append(list(terminal))
            terminal = session.record()
            _word_record(terminal)
        if terminal != (0xd1, 8, exit_pc, USER_STATUS, installed):
            raise Core0Error(f"actual U exit trap origin/PC/status/address space differs: {terminal}")
        returned = session.record()
        _word_record(returned)
        if returned != (0xd2, 0, mix(argument), remaining_before, 500):
            raise Core0Error(f"actual U data/return/frame teardown differs for argument {argument}: {returned}")
        cases.append({"runtime_argument": argument, "loaded": list(loaded), "supervisor_notifications": forwarded,
                      "exit_trap": list(terminal), "returned_and_torn_down": list(returned)})
    if sha256(text_file) != text_digest:
        raise Core0Error("user text reference changed during guest observation")
    return {"protocol": "user-D-positive-v1", "supervisor_startup": startup, "kernel_address_space": list(kernel),
            "user_text_sha256": text_digest, "user_text_bytes": text_bytes, "user_text_pages": text_pages,
            "task_frames_before_teardown": overhead + text_pages, "baseline_available_frames": 500,
            "fresh_user_runs": len(cases), "cases": cases,
            "actual_user_supervisor_notifications": sum(len(case["supervisor_notifications"]) for case in cases),
            "adversarial_fault_cases": "not_run", "scheduling": "not_run"}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--arg", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root()
        runners = runner_inputs(root)
        with Session(root=root, image=args.image, output_dir=args.output_dir, timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session, arguments=tuple(args.arg) if args.arg is not None else DEFAULT_ARGUMENTS)
            if runner_inputs(root) != runners:
                raise Core0Error("user acceptance runner changed during observation")
            session.finish(observed)
        print(f"PASS: {observed['fresh_user_runs']} actual Sv39 U runs, exit traps/data and frame recovery; QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
