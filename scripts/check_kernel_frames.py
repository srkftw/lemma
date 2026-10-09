#!/usr/bin/env python3
"""Actual guest checks of the maintained frame API through development transport."""
from __future__ import annotations
import argparse
from pathlib import Path
from core0_common import Core0Error, repo_root, sha256
from run_kernel import Session


def frame_boot(session: Session):
    boot = session.record()
    if boot[0] != 0xa or boot[2:] != (0, 512, 0x82000000):
        raise Core0Error(f"frame development boot differs: {boot}")
    return boot


def command_reader(session: Session, calls: list):
    def command(number, a=0, b=0, c=0, d=0, status=0, value=None):
        record = session.command(number, a, b, c, d)
        if record[:3] != (0xb0, number, status):
            raise Core0Error(f"frame result/status differs: request{(number,a,b,c,d)}, result{record}")
        if value is not None and record[3] != value:
            raise Core0Error(f"frame result value differs: expected{value}, got{record}")
        calls.append({"request": [number,a,b,c,d], "response": list(record)})
        return record[3], record[4]
    return command


def check(session: Session) -> dict[str, object]:
    boot = frame_boot(session)
    calls = []
    command = command_reader(session, calls)
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


def check_address_space(session: Session) -> dict[str, object]:
    """Real guest construction/walk/ownership; U-mode faults run separately."""
    boot = frame_boot(session)
    calls = []
    command = command_reader(session, calls)
    command(0, value=512)
    command(11, 0, status=32, value=0)
    command(11, 0xffffffffffffffff, status=32, value=0)
    descriptor, remaining = command(11, 2)
    if remaining != 500:
        raise Core0Error("address-space construction did not acquire exactly descriptor plus 11 tables")
    command(6, 2, value=11)
    command(6, 1, value=1)
    root, _ = command(16, descriptor)
    if not 0x82000000 <= root < 0x82200000 or root % 4096:
        raise Core0Error("address-space root is outside the owned aligned frame pool")
    command(17, descriptor, value=0x8000000000000000 | (root >> 12))
    descriptor_pa, _ = command(5, 1, descriptor)
    command(8, descriptor_pa + 40, value=11)
    data, _ = command(1, 2, 4)
    physical, _ = command(5, 2, data)
    command(4, 2, data, 0, 0x0123456789abcdef, value=0)
    command(12, descriptor, 0x20000, data, 3, value=data)
    command(13, descriptor, 0x20000, 1, value=physical)
    command(13, descriptor, 0x20000, 2, value=physical)
    command(13, descriptor, 0x20007, 1, value=physical + 7)
    command(8, physical, value=0x0123456789abcdef)
    # Quarantined corruption fixtures exercise the guest walk, not CPU faults.
    middle_handle, _ = command(8, descriptor_pa + 128 + 7 * 8)
    middle, _ = command(5, 2, middle_handle)
    low_handle, _ = command(8, descriptor_pa + 128 + 8 * 8)
    low, _ = command(5, 2, low_handle)
    for pte_address, mask in ((root, 0x40), (middle, 0x8000000000000000),
                              (low + 32 * 8, 0x8), (low + 32 * 8, 0x4000000000000000)):
        original_pte, _ = command(8, pte_address)
        command(9, pte_address, original_pte | mask, value=0)
        command(13, descriptor, 0x20000, 1, status=75, value=0)
        command(9, pte_address, original_pte, value=0)
        command(13, descriptor, 0x20000, 1, value=physical)
    command(13, descriptor, 0x20000, 4, status=72, value=0)
    command(13, descriptor, 0x20000, 3, status=72, value=0)
    command(2, 2, data, status=35, value=0)
    command(12, descriptor, 0x20000, data, 3, status=73, value=0)
    command(12, descriptor, 0x40000, data, 7, status=72, value=0)
    command(12, descriptor, 0x40000, data, 5, status=72, value=0)
    for va in (0xffff, 0x20001, 0x40000000, 0xffffff8000000000,
               0x10000000, 0x10000fff, 0x00100000):
        command(12, descriptor, va, data, 3, status=71, value=0)
    command(12, descriptor, 0x30000, data, 3, status=75, value=0)
    command(13, descriptor, 0x30000, 1, status=74, value=0)
    foreign, _ = command(1, 3, 4)
    command(12, descriptor, 0x40000, foreign, 3, status=34, value=0)
    command(2, 3, foreign, value=0)
    kernel, _ = command(1, 2, 1)
    command(12, descriptor, 0x40000, kernel, 3, status=72, value=0)
    command(2, 2, kernel, value=0)
    text, _ = command(1, 2, 3)
    text_physical, _ = command(5, 2, text)
    command(12, descriptor, 0x10000, text, 3, status=72, value=0)
    command(12, descriptor, 0x10000, text, 5, value=text)
    command(13, descriptor, 0x10000, 1, value=text_physical)
    command(13, descriptor, 0x10000, 4, value=text_physical)
    command(13, descriptor, 0x10000, 2, status=72, value=0)
    readonly, _ = command(1, 2, 4)
    readonly_physical, _ = command(5, 2, readonly)
    command(12, descriptor, 0x50000, readonly, 1, value=readonly)
    command(13, descriptor, 0x50000, 1, value=readonly_physical)
    command(13, descriptor, 0x50000, 2, status=72, value=0)
    command(14, descriptor, 0x50000, value=readonly)
    command(2, 2, readonly, value=0)
    command(14, descriptor, 0x20000, value=data)
    command(13, descriptor, 0x20000, 1, status=74, value=0)
    command(14, descriptor, 0x20000, status=74, value=0)
    command(2, 2, data, value=0)
    command(12, descriptor, 0x20000, data, 3, status=34, value=0)
    # Generic low-user mappings allocate one additional owned L0 lazily.
    lazy, _ = command(1, 2, 4)
    lazy_physical, _ = command(5, 2, lazy)
    command(12, descriptor, 0x00400000, lazy, 3, value=lazy)
    command(8, descriptor_pa + 40, value=12)
    command(13, descriptor, 0x00400000, 2, value=lazy_physical)
    # Destruction removes aliases before releasing their last owner reference.
    command(12, descriptor, 0x00401000, lazy, 3, value=lazy)
    # Explicit trusted-shadow fixture; this is not an installed SATP witness.
    command(9, 0x80400600, root, value=0)
    command(15, descriptor, status=77, value=0)
    command(9, 0x80400600, 0, value=0)
    command(15, descriptor, value=0)
    command(16, descriptor, status=34, value=0)
    command(5, 2, text, status=34, value=0)
    command(5, 2, lazy, status=34, value=0)
    command(0, value=512)
    # The reusable standard supervisor root cannot acquire U mappings.
    kernel_descriptor, _ = command(11, 1)
    kernel_data, _ = command(1, 1, 4)
    command(12, kernel_descriptor, 0x20000, kernel_data, 3, status=72, value=0)
    command(2, 1, kernel_data, value=0)
    command(15, kernel_descriptor, value=0)
    command(0, value=512)
    # A genuine mid-batch quota failure must unwind its descriptor and tables.
    held = [command(1, 2, 4)[0] for _ in range(22)]
    command(11, 2, status=38, value=0)
    command(6, 2, value=22)
    command(6, 1, value=0)
    command(8, 0x80400500, value=0)
    command(0, value=490)
    for handle in held:
        command(2, 2, handle, value=0)
    command(0, value=512)
    # A failed lazy table allocation leaves the supplied leaf owned/unmapped.
    full_descriptor, _ = command(11, 2)
    full_pa, _ = command(5, 1, full_descriptor)
    held = [command(1, 2, 4)[0] for _ in range(21)]
    command(6, 2, value=32)
    command(12, full_descriptor, 0x00400000, held[0], 3, status=38, value=0)
    command(8, full_pa + 40, value=11)
    command(13, full_descriptor, 0x00400000, 1, status=74, value=0)
    for handle in held:
        command(2, 2, handle, value=0)
    command(15, full_descriptor, value=0)
    command(0, value=512)
    return {"protocol": "address-space-D-api-v1", "boot": list(boot), "calls": calls,
            "base_table_frames": 11, "final_remaining": 512,
            "rollback": ["actual create quota failure", "actual lazy-L0 quota failure"],
            "coverage": "guest table construction, complete owned walk, pinning, aliases, teardown and generations",
            "active_root_fixture": "trusted bookkeeping rejection only",
            "pte_corruption_fixtures": "four guest-walk rejections; not architectural U-mode faults",
            "architecture_user_execution": "not covered; separate Gate D U-mode boots required"}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--address-space", action="store_true",
                        help="run bounded Gate D address-space API cases instead of Gate B retirement cases")
    args = parser.parse_args()
    try:
        with Session(root=repo_root(), image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            session.report["acceptance_checker_sha256"] = sha256(Path(__file__))
            session.finish(check_address_space(session) if args.address_space else check(session))
        print("PASS: actual address-space construction, walks, ownership and rollback" if args.address_space else
              "PASS: actual frame ownership, zero-reuse, quota, global exhaustion and recovery")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
