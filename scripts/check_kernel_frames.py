#!/usr/bin/env python3
"""Actual guest checks of the maintained frame API through development transport."""
from __future__ import annotations
import argparse
from pathlib import Path
from core0_common import Core0Error, repo_root, sha256
from run_kernel import Session


def check(session: Session) -> dict[str, object]:
    boot = session.record()
    if boot[0] != 0xa or boot[2:] != (0, 512, 0x82000000):
        raise Core0Error(f"frame development boot differs: {boot}")
    calls = []
    def command(number, a=0, b=0, c=0, d=0, status=0, value=None):
        record = session.command(number, a, b, c, d)
        if record[:3] != (0xb0, number, status):
            raise Core0Error(f"frame result/status differs: request{(number,a,b,c,d)}, result{record}")
        if value is not None and record[3] != value:
            raise Core0Error(f"frame result value differs: expected{value}, got{record}")
        calls.append({"request": [number,a,b,c,d], "response": list(record)})
        return record[3], record[4]
    command(0, value=512)
    for address in (0x80000000, 0x80100000, 0x80300000, 0x10000000, 0x00100000,
                    0x81fff000, 0x82200000, 0xfffffffffffffff8):
        command(8, address, status=7, value=0)
        command(9, address, 99, status=7, value=0)
    for address in (0x80200000, 0x80600000, 0x87e00000):
        original, _ = command(8, address)
        command(9, address, 99, status=5, value=0)
        command(8, address, value=original)
    command(1, 0, 3, status=32, value=0)
    command(1, 0xffffffffffffffff, 3, status=32, value=0)
    command(1, 2, 0, status=32, value=0)
    command(1, 2, 6, status=32, value=0)
    handle, remaining = command(1, 2, 3)
    if remaining != 511 or handle // 512 == 0:
        raise Core0Error("allocation did not control the frame accounting/generation")
    physical, _ = command(5, 2, handle)
    if physical != 0x82000000 + (handle % 512) * 4096:
        raise Core0Error("frame handle resolved outside its unique owned slot")
    command(3, 2, handle, 0, value=0)
    command(4, 2, handle, 0, 0xdeadbeef01234567, value=0)
    command(3, 2, handle, 0, value=0xdeadbeef01234567)
    command(5, 3, handle, status=34, value=0)
    command(3, 3, handle, 0, status=34, value=0)
    command(4, 3, handle, 0, 99, status=34, value=0)
    command(3, 2, handle, 0, value=0xdeadbeef01234567)
    command(6, 2, value=1)
    command(6, 3, value=0)
    command(0, value=511)
    command(4, 2, handle, 4088, 0xa5a5a5a5a5a5a5a5, value=0)
    command(3, 2, handle, 4088, value=0xa5a5a5a5a5a5a5a5)
    command(3, 2, handle, 4096, status=7, value=0)
    command(4, 2, handle, 1, 99, status=8, value=0)
    for offset in range(0, 4096, 8):
        command(4, 2, handle, offset, 0x8000000000000000 | offset, value=0)
    command(2, 3, handle, status=34, value=0)
    command(2, 2, 0x80000000, status=34, value=0)
    command(2, 2, handle, value=0)
    command(2, 2, handle, status=34, value=0)
    command(0, value=512)
    replacement, _ = command(1, 3, 4)
    if replacement % 512 != handle % 512 or replacement <= handle:
        raise Core0Error("released low slot was not reused with a fresh generation")
    command(3, 2, handle, 0, status=34, value=0)
    for offset in range(0, 4096, 8):
        command(3, 3, replacement, offset, value=0)
    command(2, 3, replacement, value=0)
    same_owner, _ = command(1, 3, 4)
    if same_owner <= replacement:
        raise Core0Error("same-owner reuse did not advance the generation")
    command(3, 3, replacement, 0, status=34, value=0)
    command(2, 3, same_owner, value=0)
    command(10, 2, 3, 0, status=16, value=0)
    command(10, 2, 3, 33, status=16, value=0)
    batch, _ = command(10, 2, 3, 3, value=0x80400400)
    command(8, batch + 256, value=3)
    batch_handles = [command(8, batch + i * 8)[0] for i in range(3)]
    if len({handle % 512 for handle in batch_handles}) != 3:
        raise Core0Error("successful batch published duplicate slots")
    for handle in batch_handles:
        command(2, 2, handle, value=0)
    partial = [command(1, 2, 3)[0] for _ in range(31)]
    command(0, value=481)
    command(10, 2, 3, 2, status=38, value=0)
    command(8, 0x80400500, value=0)
    command(6, 2, value=31)
    command(0, value=481)
    for handle in partial:
        command(2, 2, handle, value=0)
    quota_handles = [command(1, 2, 3)[0] for _ in range(32)]
    if len({handle % 512 for handle in quota_handles}) != 32:
        raise Core0Error("allocator granted duplicate live physical slots")
    command(6, 2, value=32)
    command(1, 2, 3, status=38, value=0)
    command(0, value=480)
    all_handles = [command(1, 1, 2)[0] for _ in range(480)]
    slots = {handle % 512 for handle in quota_handles + all_handles}
    if slots != set(range(512)):
        raise Core0Error("global exhaustion does not correspond to exact unique frame ownership")
    command(0, value=0)
    command(1, 1, 2, status=33, value=0)
    command(2, 1, all_handles.pop(), value=0)
    command(0, value=1)
    command(10, 1, 2, 2, status=33, value=0)
    command(8, 0x80400500, value=0)
    command(6, 1, value=479)
    command(0, value=1)
    for handle in all_handles:
        command(2, 1, handle, value=0)
    for handle in quota_handles:
        command(2, 2, handle, value=0)
    command(0, value=512)
    recovered, _ = command(1, 2, 5)
    command(2, 2, recovered, value=0)
    command(0, value=512)
    # Deliberate metadata fixtures exist only in the development image. This
    # checks allocator bookkeeping, not an installed mapping or TLB invalidation.
    pinned, _ = command(1, 2, 3)
    pin_address = 0x80401000 + (pinned % 512) * 32 + 16
    command(9, pin_address, 1, value=0)
    command(2, 2, pinned, status=35, value=0)
    command(5, 2, pinned, value=0x82000000 + (pinned % 512) * 4096)
    command(0, value=511)
    command(9, pin_address, 0, value=0)
    command(2, 2, pinned, value=0)
    command(0, value=512)
    # Retirement runs last: the legitimate capacity is 511 after this fixture.
    max_generation = 0x007fffffffffffff
    command(9, 0x80401000 + 24, max_generation - 1, value=0)
    terminal, _ = command(1, 2, 3, value=max_generation * 512)
    command(2, 2, terminal, value=0)
    command(8, 0x80401000, value=0xffffffffffffffff)
    command(0, value=511)
    after_retirement, _ = command(1, 2, 3)
    if after_retirement % 512 != 1:
        raise Core0Error("allocator reused a retired generation slot")
    command(3, 2, terminal, 0, status=34, value=0)
    command(2, 2, after_retirement, value=0)
    command(0, value=511)
    return {"protocol": "frames-B-v1", "boot": list(boot), "calls": calls,
            "global_exhaustion_slots": len(slots), "zero_reuse_words": 512,
            "quota": 32, "restored_capacity_before_retirement": 512, "final_remaining": 511,
            "partial_batch_rollback": ["actual quota failure", "actual global exhaustion"],
            "generation_retirement": "one slot permanently retired at maximum generation",
            "mapping_release_test": "development bookkeeping guard only; installed mappings require Gate D",
            "reserved_physical_probe": "19 actual denied compiler-authority accesses"}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        with Session(root=repo_root(), image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            session.report["acceptance_checker_sha256"] = sha256(Path(__file__))
            session.finish(check(session))
        print("PASS: actual frame ownership, zero-reuse, quota, global exhaustion and recovery")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
