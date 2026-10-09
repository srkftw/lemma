#!/usr/bin/env python3
"""Observe real user faults, page reuse and late loader rollback in one live VM."""
from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import struct

from core0_common import Core0Error, repo_root, sha256, write_json
from run_kernel import Session, transport
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import MASK, satp
from check_kernel_tasks import Trace


class LifecycleTrace(Trace):
    keys = ("compute", "sleeper", "busy", "fault")
    configuration = "tasks-fault-development"

    def __init__(self, session):
        super().__init__(session)
        self.owners, self.physical, self.faults, self.pressures = set(), {}, [], []
        self.pending_pressure = None
        attack = self.users["fault"].get("quarantined_startup", {})
        if attack.get("case") != "supervisor-csr" or attack.get("bytes") != 8:
            raise Core0Error("lifecycle requires the exact audited Fault-only CSR startup")
        self.fault_pc = attack["fault_pc"]
        payload = (session.image.parent / "users/fault/text.bin").read_bytes()
        offset = self.fault_pc - 0x10000
        self.fault_word = int.from_bytes(payload[offset:offset + 4], "little")
        if self.fault_word != 0x10002573:
            raise Core0Error("Fault instruction differs from the actual audited CSR opcode")

    def observe(self, event):
        tag, a, b, c, d = event
        if tag == 0xfe:
            task = self._task(a)
            if (self.current is not None or task["dispatches"] or a in self.physical
                    or b % 4096 or (c - 32) % 4096
                    or not 0x82000000 <= b < 0x82200000
                    or not 0x82000020 <= c < 0x82200000
                    or b == c - 32 or d < 2 or d in self.owners
                    or any(({b, c - 32} & {row[2], row[3] - 32}) for id, row in self.physical.items()
                           if id in self.live() and id != a)):
                raise Core0Error("creation lacks fresh checked private owner/data/stack observations")
            self.owners.add(d)
            self.physical[a] = list(event)
        elif tag == 0xe8:
            task = self._task(a)
            if (self.current != a or task["image"] != 3 or task["start"]
                    or (b, c, d) != (task["nonce"], 0, 0) or a not in self.physical):
                raise Core0Error("Fault did not observe fresh zeroed BSS/stack before writing new secrets")
            task["start"] = True
            task["zero_before_write"] = list(event)
        elif tag == 0xd4:
            task = self._task(self.current)
            if (task["image"] != 3 or not task["start"] or "architectural_fault" in task
                    or (a, b, c, d) != (2, self.fault_pc, self.fault_word, 0x200000020)):
                raise Core0Error("fault lacks actual illegal-instruction cause/PC/opcode/U status")
            task["architectural_fault"] = list(event)
            self.faults.append({"task": self.current, "record": list(event)})
        elif tag == 0xf2 and b == 5:
            task = self._task(a)
            if (self.current != a or task["image"] != 3 or "architectural_fault" not in task
                    or c < self.irq or d != self.fault_pc or task["reasons"][5]):
                raise Core0Error("fault return lacks the current checked architectural trap")
            self.current, self.irq = None, c
            task["reasons"][5] += 1
            task["state"] = 6
        elif tag == 0xf4 and d == 2:
            task = self._task(a)
            if (self.current is not None or task["image"] != 3 or task["terminal"] is not None
                    or not task["start"] or "architectural_fault" not in task
                    or task["reasons"][5] != 1 or (b, c) != (44, task["nonce"])):
                raise Core0Error("contained Fault termination differs or runs on the outgoing stack")
            task["terminal"], task["complete"], task["state"] = list(event), True, 6
        elif tag == 0xe9:
            if (self.current is not None or self.pending_pressure is None
                    or a != self.pending_pressure["image"] or b != 38
                    or c != self.remaining or d != c - self.pending_pressure["held"] - 1
                    or "failure" in self.pending_pressure):
                raise Core0Error("late quota failure lacks measured complete rollback to held-frame baseline")
            self.pending_pressure["failure"] = list(event)
        elif tag == 0xea:
            row = self.pending_pressure
            if (self.current is not None or row is None or "failure" not in row
                    or "cleanup" in row
                    or a < 2 or a in self.owners or b != row["held"] or c != b or d != self.remaining):
                raise Core0Error("quota pressure lost held sentinels/owner identity or failed complete cleanup")
            self.owners.add(a)
            row["cleanup"] = list(event)
            self.pressures.append(dict(row))
        else:
            if tag == 0xf3 and a not in self.physical:
                raise Core0Error("user dispatch preceded its checked construction observation")
            super().observe(event)

    def pressure(self, image, nonce):
        pages = (self.images[self.keys[image]]["text_bytes"] + 4095) // 4096
        self.pending_pressure = {"image": image, "nonce": nonce, "held": 17 - pages}
        before = len(self.tasks)
        self.command(0x34, image, nonce, status=38, value=0)
        if (len(self.tasks) != before or "cleanup" not in self.pending_pressure
                or self.creation_queue):
            raise Core0Error("failed loader construction published a task or lacks actual rollback evidence")
        self.pending_pressure = None


def check(session):
    startup = validate_positive_records([session.record() for _ in range(4)])
    kernel, ready = session.record(), session.record()
    if (kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0)
            or ready != (0xf0, 1, 8, 512, 10000)):
        raise Core0Error("G startup differs from actual checked root/task table/quantum")
    trace = LifecycleTrace(session)
    nonces = []
    while len(nonces) < 32:
        value = secrets.randbits(64)
        if value not in nonces and value not in {0, MASK, 0x61972a5fb3e804dc, 0x89e4c13572ba06df}:
            nonces.append(value)
    for image in range(3):
        trace.expect_create(image, nonces[image])
    transport._write_all(session.process, struct.pack("<5Q", 0x30, *nonces[:3], 0),
                         deadline=session.deadline, capture=session.capture, context="launching G peers")
    trace.until(lambda: len(trace.physical) == 3)
    initial = list(trace.tasks)
    busy = initial[2]
    trace.until(lambda: len(trace.tasks[busy]["preempt_irqs"]) >= 3)
    _, first = trace.command(0x31, busy)
    if len(first) != 1 or first[0][4] == 0:
        raise Core0Error("G Busy peer lacks actual independent loop progress")

    def create(image, nonce):
        trace.expect_create(image, nonce)
        ack, _ = trace.command(0x33, image, nonce)
        id = ack[3]
        if id not in trace.tasks or id not in trace.physical or trace.tasks[id]["nonce"] != nonce:
            raise Core0Error("creation ACK differs from actual fresh private task")
        return id

    # Actual faults recur while the same noncooperative peer remains live.
    fault_ids = []
    for nonce in nonces[3:7]:
        id = create(3, nonce)
        fault_ids.append(id)
        trace.until(lambda: trace.tasks[id]["reaped"])
        trace.command(0x31, id, status=74, value=0)
        trace.command(0x32, id, 0x55, status=74, value=0)
    trace.until(lambda: all(trace.tasks[id]["reaped"] for id in initial[:2]))
    _, second = trace.command(0x31, busy)
    if len(second) != 1 or second[0][4] <= first[0][4]:
        raise Core0Error("Busy stopped progressing across unrelated real faults")

    # After ordinary peer exit, force actual reuse of the same physical data
    # and stack pages; every fresh UserFault checks zeros before writing again.
    for nonce in nonces[7:15]:
        id = create(3, nonce)
        fault_ids.append(id)
        trace.until(lambda: trace.tasks[id]["reaped"])
        trace.command(0x31, id, status=74, value=0)
    pairs = {}
    reused = []
    for id in fault_ids:
        physical = trace.physical[id]
        pair = tuple(physical[2:4])
        if pair in pairs:
            prior = pairs[pair]
            if trace.tasks[prior]["nonce"] == trace.tasks[id]["nonce"]:
                raise Core0Error("page-reuse witness repeated a prior secret")
            reused.append([prior, id, *pair])
        pairs[pair] = id
    if not reused:
        raise Core0Error("no actual same data/stack physical-page reuse was observed")
    for image in range(4):
        trace.pressure(image, nonces[15 + image])
        trace.command(0x31, 0)
    # The slots/owners survive quota exhaustion and ordinary/faulted restart.
    recovered_fault = create(3, nonces[19])
    trace.until(lambda: trace.tasks[recovered_fault]["reaped"])
    normal = [create(0, nonces[20]), create(1, nonces[21])]
    trace.until(lambda: all(trace.tasks[id]["reaped"] for id in normal))
    _, third = trace.command(0x31, busy)
    if len(third) != 1 or third[0][4] <= second[0][4]:
        raise Core0Error("surviving peer failed to progress across quota rollback and recovered tasks")
    if not any(row[0] in {0xf9, 0xfb} and row[1] in normal for row in trace.events):
        raise Core0Error("unrelated ordinary peers did not finish after rollback")
    for id in normal:
        trace.command(0x31, id, status=74, value=0)
        trace.command(0x32, id, 0x55, status=74, value=0)
    trace.command(0x33, 4, nonces[22], status=81, value=0)
    trace.command(0x34, 4, nonces[23], status=81, value=0)
    trace.command(0x34, 0, nonces[24], 1, status=16, value=0)
    trace.command(0x32, busy, 0x55, value=busy)
    trace.until(lambda: trace.tasks[busy]["reaped"])
    trace.command(0x31, 0, value=499)
    if ([row["image"] for row in trace.pressures] != list(range(4))
            or len(trace.faults) != 13 or len(trace.tasks) != 18):
        raise Core0Error("G lifecycle lacks the exact complete fault and rollback corpus")
    if trace.live() or trace.creation_queue or trace.current is not None or trace.remaining != 499:
        raise Core0Error("G left an active task, unpublished construction or leaked owned pages")
    return {"protocol": "lifecycle-G-v1", "startup": startup, "kernel_root": list(kernel),
            "ready": list(ready), "runtime_nonces": nonces,
            "tasks": {str(id): {**task, "reasons": dict(task["reasons"])} for id, task in trace.tasks.items()},
            "checked_physical_creation": trace.physical, "actual_same_page_reuse": reused,
            "architectural_faults": trace.faults, "fault_instruction": trace.fault_word,
            "late_quota_rollbacks": trace.pressures, "noncooperative_survivor": busy,
            "busy_counter_queries": [first[0], second[0], third[0]],
            "actual_machine_interrupts": trace.irq, "queries": trace.queries,
            "acknowledgments": trace.acks, "final_remaining_frames": trace.remaining,
            "guest_lifetime": "one continuous Action.loop VM; no process restart"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root()
        paths = ("scripts/check_kernel_lifecycle.py", "scripts/check_kernel_tasks.py",
                 "scripts/check_kernel_supervisor.py", "scripts/check_kernel_user.py", "scripts/check_kernel.py",
                 "scripts/run_kernel.py", "scripts/run_device_session.py", "scripts/run_monitor_session.py")
        runners = {path: sha256(root / path) for path in paths}
        with Session(root=root, image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session)
            if {path: sha256(root / path) for path in paths} != runners:
                raise Core0Error("G observation runner changed during guest execution")
            session.finish(observed)
        try:
            from check_kernel import validate_session
            validate_session(session.output_dir / "result.json", session.image)
        except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
            session.report.update(status="FAIL", error=str(error), failure_category="post-cleanup-wire-evidence")
            write_json(session.output_dir / "result.json.tmp", session.report)
            (session.output_dir / "result.json.tmp").replace(session.output_dir / "result.json")
            raise
        print("PASS: actual faults/restarts, zero-on-physical-reuse and late quota rollback observed")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
