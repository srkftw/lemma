#!/usr/bin/env python3
"""Guest parser rejection and actual late loader rollback through explicit probes.

Fixture requests use the guest's allocator and bounded development frame API.
The host supplies malformed package input bytes; maintained Lean validates them.
No user code is executed from the fixture, and no host creates guest mappings.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from check_kernel_frames import command_reader, frame_boot
from core0_common import Core0Error, repo_root, sha256
from run_kernel import Session

MAGIC = 0x31474b50414d454c


def runner_inputs(root: Path) -> dict[str, str]:
    return {name: sha256(root / name) for name in (
        "scripts/check_kernel_loader.py", "scripts/check_kernel_frames.py",
        "scripts/run_kernel.py", "scripts/run_device_session.py", "scripts/run_monitor_session.py")}


def valid_words() -> list[int]:
    return [MAGIC, 1, 1, 132,
            1, 0x10000, 0x10000, 128, 4, 0x20000, 132, 0, 4096,
            0x3fffc000, 2, 0]


def malformed_cases() -> list[tuple[str, list[int], int]]:
    cases = []
    for label, word, value, expected in (
        ("magic", 0, 0, 80), ("version", 1, 2, 80),
        ("empty corpus", 2, 0, 80), ("excess corpus", 2, 9, 80),
        ("short header", 3, 127, 83), ("outside frame", 3, 4097, 83),
        ("zero image id", 4, 0, 81), ("misaligned entry", 5, 0x10002, 81),
        ("entry outside text", 5, 0x10004, 81), ("text virtual layout", 6, 0x11000, 81),
        ("wrapped text file offset", 7, 2**64-1, 83), ("empty text", 8, 0, 81),
        ("excess text pages", 8, 0xf001, 81), ("data virtual layout", 9, 0x21000, 81),
        ("wrapped data file offset", 10, 2**64-1, 83), ("excess initialized data", 11, 4097, 83),
        ("data memory budget", 12, 8192, 81), ("stack guard layout", 13, 0x3fffb000, 81),
        ("stack page budget", 14, 3, 81), ("unsupported flags", 15, 1, 81)):
        words = valid_words(); words[word] = value
        cases.append((label, words, expected))
    words = valid_words(); words[3] = 136; words[8] = 8; words[10] = 132; words[11] = 4
    cases.append(("overlapping text/data payload", words, 83))
    header = [MAGIC, 1, 2, 232]
    descriptor = [1, 0x10000, 0x10000, 224, 4, 0x20000, 228, 0, 4096, 0x3fffc000, 2, 0]
    second = list(descriptor); second[3] = 228; second[6] = 232
    cases.append(("duplicate image ids", header + descriptor + second, 82))
    second[0] = 2; second[3] = 224
    cases.append(("overlapping image payloads", header + descriptor + second, 83))
    return cases


def check(session: Session) -> dict:
    if (session.binding.get("configuration"), session.binding.get("stage")) != ("frames-development", "bootstrap-m"):
        raise Core0Error("loader probes require the explicit frames-development bootstrap image")
    boot = frame_boot(session); calls = []; command = command_reader(session, calls)
    command(0, value=512)
    fixture, remaining = command(1, 1, 1)
    if remaining != 511:
        raise Core0Error("parser fixture did not use one real guest-owned frame")
    physical, _ = command(5, 1, fixture)
    if physical != 0x82000000 + fixture % 512 * 4096:
        raise Core0Error("parser fixture handle does not resolve to its owned physical frame")
    def put(words):
        for index, word in enumerate(words):
            command(4, 1, fixture, index * 8, word, value=0)
    put(valid_words())
    command(18, fixture, 0, value=physical+32)
    command(18, fixture, 1, status=81, value=0)
    checked = []
    corpus = malformed_cases()
    if not corpus or len({row[0] for row in corpus}) != len(corpus):
        raise Core0Error("malformed package corpus must be nonempty with unique roles")
    for label, words, expected in corpus:
        put(words)
        command(18, fixture, 0, status=expected, value=0)
        command(0, value=511)
        command(6, 1, value=1); command(6, 2, value=0)
        checked.append({"case": label, "actual_status": expected, "available_after": 511})
    command(2, 1, fixture, value=0)
    command(18, fixture, status=34, value=0)
    other, _ = command(1, 2, 1)
    command(18, other, status=34, value=0); command(2, 2, other, value=0)
    wrong_purpose, _ = command(1, 1, 4)
    command(18, wrong_purpose, status=40, value=0); command(2, 1, wrong_purpose, value=0)
    command(0, value=512)
    # The real immutable package, loaded without entering U, establishes the
    # actual image's resource cost; this does not infer a user execution pass.
    descriptor, during = command(19, 0, 2, 7)
    owner_pages, _ = command(6, 2)
    if owner_pages < 15 or during != 512-owner_pages-1:
        raise Core0Error("real loader did not allocate its charged pages plus kernel descriptor")
    command(20, descriptor, value=0)
    command(6, 2, value=0); command(6, 1, value=0); command(0, value=512)
    command(20, descriptor, status=34, value=0)
    command(19, 1, 2, status=81, value=0)
    command(19, 0, 1, status=32, value=0)
    # Leave one fewer owner-quota page than the observed complete load needs.
    held_count = 33-owner_pages
    if not 1 <= held_count <= 32:
        raise Core0Error("unsupported observed loader quota cost")
    held = [command(1, 2, 4)[0] for _ in range(held_count)]
    sentinel = 0xfeedface01234567
    command(4, 2, held[0], 0, sentinel, value=0)
    command(19, 0, 2, 11, status=38, value=0)
    command(6, 2, value=held_count); command(6, 1, value=0)
    command(0, value=512-held_count)
    command(3, 2, held[0], 0, value=sentinel)
    for handle in held:
        command(2, 2, handle, value=0)
    command(0, value=512)
    return {"protocol": "loader-D-v1", "boot": list(boot), "calls": calls,
            "malformed_packages": checked, "malformed_rejections": len(checked),
            "valid_fixture_validated_not_executed": True, "loaded_owner_pages": owner_pages,
            "actual_late_quota_rollback": {"held_pages": held_count, "status": 38,
                                            "preexisting_data_unchanged": True},
            "final_remaining": 512, "user_execution": "not covered; separate U-mode acceptance"}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root(); runners = runner_inputs(root)
        with Session(root=root, image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session)
            if runner_inputs(root) != runners:
                raise Core0Error("loader acceptance runner changed during observation")
            session.finish(observed)
        print("PASS: actual malformed package rejections and late loader rollback; QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
