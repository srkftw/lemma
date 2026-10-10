#!/usr/bin/env python3
"""Bounded observations of quarantined U faults, recovery and a paused peer.

This host checker reads actual trap/data/frame records from a freshly audited
development image. It does not install mappings or implement guest policy.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from build_kernel import user_startup_case
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import MASK, USER_STATUS, _word_record, mix, satp, task_frame_overhead
from core0_common import Core0Error, load_json, repo_root, sha256
from run_kernel import Session

CONFIGURATIONS = {"user-isolation-development", "user-csr-development", "user-nx-development",
                  "user-kernel-fetch-development", "user-misaligned-development"}
ISOLATION_ARGUMENTS = (1, 0, 2, 7, 3, 0, 4, 7)
TYPED_ARGUMENTS = (7, 0, 7)
SENTINEL = 0x0123456789abcdef
ATTACKS = {
    1: ("readMetadata", 13, 0x30000), 2: ("writeText", 15, 0x10000),
    3: ("readGuard", 13, 0x3fffb000), 4: ("readForeign", 13, 0x40000),
}


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in (
        "scripts/check_kernel_isolation.py", "scripts/check_kernel_supervisor.py", "scripts/check_kernel_user.py",
        "scripts/run_kernel.py", "scripts/run_device_session.py", "scripts/run_monitor_session.py")}


def check(session: Session, *, arguments: tuple[int, ...] | None = None) -> dict:
    configuration = session.binding.get("configuration")
    if (configuration not in CONFIGURATIONS or session.binding.get("stage") != "supervisor"
            or session.binding.get("startup_case") != "normal"
            or session.binding.get("user_startup_case") != user_startup_case(configuration)):
        raise Core0Error("isolation acceptance requires its exact quarantined supervisor configuration")
    isolation = configuration == "user-isolation-development"
    arguments = (ISOLATION_ARGUMENTS if isolation else TYPED_ARGUMENTS) if arguments is None else arguments
    if (not arguments or len(arguments) > 32 or any(type(word) is not int or not 0 <= word <= MASK for word in arguments)
            or isolation and arguments != ISOLATION_ARGUMENTS or not isolation and arguments != TYPED_ARGUMENTS):
        raise Core0Error("isolation corpus must exercise all four faults and normal continuations; typed probes require three fresh7/0/7 instances")
    startup = validate_positive_records([session.record() for _ in range(4)])
    kernel = session.record(); _word_record(kernel)
    if kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0):
        raise Core0Error(f"installed kernel address-space facts differ: {kernel}")
    overhead = task_frame_overhead(session)
    initial_text_pages = ((session.image.parent / "user-text.bin").stat().st_size + 4095) // 4096
    baseline, victim, peer = (500 - overhead - initial_text_pages - 1 if isolation else 500), None, None
    if isolation:
        victim = session.record(); _word_record(victim)
        if (victim[0] != 0xd5 or victim[1] < 512 or victim[2] == kernel[1] or victim[3] != 0x40000
                or victim[4] in {kernel[1], victim[2]}):
            raise Core0Error(f"paused victim descriptor/root/private mapping differs: {victim}")
        satp(victim[2]); satp(victim[4])
        peer = session.record(); _word_record(peer)
        if peer != (0xd6, 2, SENTINEL, baseline, 0):
            raise Core0Error(f"paused victim ownership/sentinel/frame facts differ: {peer}")
    user = session.binding.get("elf", {}).get("user", {})
    ranges, exit_pc = user.get("function_ranges"), user.get("exit_ecall_pc")
    if not isinstance(ranges, dict) or not ranges or type(exit_pc) is not int:
        raise Core0Error("audited U function ranges/exit PC are missing")
    text_file = session.image.parent / "user-text.bin"
    text_digest, text_bytes = sha256(text_file), text_file.stat().st_size
    if not 0 < text_bytes <= 0xf000:
        raise Core0Error("audited U text is empty or exceeds the loader format")
    unit = load_json(session.image.parent / "user/unit.json")
    by_source = {row["source"]: row["symbol"] for row in unit["functions"]}

    def in_range(pc: int, row: object) -> bool:
        return (type(pc) is int and pc % 4 == 0 and isinstance(row, dict)
                and type(row.get("base")) is int and type(row.get("bytes")) is int
                and row["base"] <= pc < row["base"] + row["bytes"])

    def user_pc(pc: int) -> bool:
        return any(in_range(pc, row) for row in ranges.values())

    if not user_pc(exit_pc):
        raise Core0Error("audited user exit is outside executable function ranges")
    typed = user.get("quarantined_startup", {})
    if not isolation and (typed.get("case") != user_startup_case(configuration) or type(typed.get("fault_pc")) is not int):
        raise Core0Error("typed probe lacks exact audited attack PC/case")
    cases, descriptors = [], {victim[1]} if victim else set()
    pages = (text_bytes + 4095) // 4096
    remaining_before = baseline - (overhead + pages)
    for argument in arguments:
        loaded = session.command(1, argument, 0, 0, 0); _word_record(loaded)
        forbidden_roots = {kernel[1]} | ({victim[2], victim[4]} if victim else set())
        if (loaded[0] != 0xd0 or loaded[1] < 512 or loaded[1] in descriptors
                or loaded[2] in forbidden_roots or loaded[3:] != (0x10000, text_bytes)):
            raise Core0Error(f"fresh attacker descriptor/root/entry/text facts differ: {loaded}")
        descriptors.add(loaded[1]); installed = satp(loaded[2]); forwarded = []
        terminal = session.record(); _word_record(terminal)
        while terminal[0] == 0xdf:
            # A typed jump may deliver an interrupt at a non-executable target
            # before the precise synchronous fetch fault. Its subsequent trap
            # must still match this case's exact audited cause/PC/address.
            if (len(forwarded) >= 32 or terminal[1] != 0x8000000000000001 or isolation and not user_pc(terminal[2])
                    or terminal[3:] != (USER_STATUS, installed)):
                raise Core0Error(f"actual U supervisor notification context differs: {terminal}")
            forwarded.append(list(terminal)); terminal = session.record(); _word_record(terminal)
        fault = not isolation or argument in ATTACKS
        context = None
        if fault:
            if terminal[0] != 0xd4 or terminal[4] != USER_STATUS:
                raise Core0Error(f"actual U fault/status record differs: {terminal}")
            if isolation:
                suffix, cause, stval = ATTACKS[argument]
                symbol = by_source.get("Lemma.User.Development.Isolation." + suffix)
                if symbol not in ranges or not in_range(terminal[2], ranges[symbol]) or terminal[1] != cause or terminal[3] != stval:
                    raise Core0Error(f"isolation fault cause/operation PC/address differs: {terminal}")
            elif configuration == "user-csr-development":
                if terminal[1:3] != (2, typed["fault_pc"]) or terminal[3] not in {0, 0x10002573}:
                    raise Core0Error(f"typed supervisor CSR denial differs: {terminal}")
            elif configuration == "user-nx-development":
                if terminal[1:4] != (12, 0x20000, 0x20000):
                    raise Core0Error(f"NX fetch must be an instruction page fault at data20000: {terminal}")
            elif configuration == "user-kernel-fetch-development":
                if terminal[1:4] != (12, 0x80200000, 0x80200000):
                    raise Core0Error(f"kernel fetch must be a contained instruction page fault: {terminal}")
            elif terminal[1:4] != (2, 0x10002, 0) or typed["fault_pc"] != 0x10002:
                raise Core0Error(f"pinned compressed-capable CPU must report the audited illegal halfword at10002: {terminal}")
            context = session.record(); _word_record(context)
            if context != (0xdc, terminal[1], terminal[2], USER_STATUS, installed):
                raise Core0Error(f"fault continuation context/SATP differs: {context}")
        elif terminal != (0xd1, 8, exit_pc, USER_STATUS, installed):
            raise Core0Error(f"ordinary continuation exit differs: {terminal}")
        returned = session.record(); _word_record(returned)
        expected_data = 0 if isolation and fault else mix(argument)
        if returned != (0xd2, 44 if fault else 0, expected_data, remaining_before, baseline):
            raise Core0Error(f"actual fault/normal data and teardown differ: {returned}")
        victim_after = None
        if victim:
            victim_after = session.record(); _word_record(victim_after)
            if victim_after != (0xd7, victim[1], SENTINEL, baseline, 0):
                raise Core0Error(f"paused victim changed or attacker frames leaked: {victim_after}")
        cases.append({"runtime_argument": argument, "loaded": list(loaded), "supervisor_notifications": forwarded,
                      "fault": fault, "terminal_trap": list(terminal), "fault_return_context": list(context) if context else None,
                      "returned_and_torn_down": list(returned), "paused_victim_after": list(victim_after) if victim_after else None})
    if sha256(text_file) != text_digest:
        raise Core0Error("audited user text changed during isolation observation")
    return {"protocol": "user-D-isolation-v1", "configuration": configuration, "supervisor_startup": startup,
            "kernel_address_space": list(kernel), "paused_victim": list(victim) if victim else None,
            "paused_victim_initial": list(peer) if peer else None, "baseline_available_frames": baseline,
            "user_text_sha256": text_digest, "user_text_bytes": text_bytes, "user_text_pages": pages,
            "fresh_attacker_runs": len(cases), "actual_faults": sum(case["fault"] for case in cases), "cases": cases,
            "actual_user_supervisor_notifications": sum(len(case["supervisor_notifications"]) for case in cases),
            "scheduling": "not_run"}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root(); runners = runner_inputs(root)
        with Session(root=root, image=args.image, output_dir=args.output_dir, timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session)
            if runner_inputs(root) != runners:
                raise Core0Error("isolation checker/transport changed during observation")
            session.finish(observed)
        print(f"PASS: {observed['actual_faults']} actual U faults and recovery, {observed['fresh_attacker_runs']} runs; QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
