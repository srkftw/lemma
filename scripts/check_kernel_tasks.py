#!/usr/bin/env python3
"""Observe real preemptive, separately linked U tasks in a bounded live guest.

The arithmetic reference is host-only. Every accepted scheduling, sleep and
reclamation fact comes from fresh complete K1 records and an independently
audited image. A timeout, missing timer progress, or unexpected record fails.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from pathlib import Path
import secrets
import struct
import re

from core0_common import Core0Error, repo_root, sha256, write_json
from run_kernel import Session, transport
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import MASK, satp

MAX_RECORDS = 16384
IMAGE_KEYS = ("compute", "sleeper", "busy")


def compute_round(acc: int, nonce: int) -> int:
    a, b = nonce ^ 0x1375a94f2468bace, (nonce + 0x8420feca97531bdf) & MASK
    c = ((nonce * 17) & MASK) ^ (nonce >> 13)
    for _ in range(32):
        for index in range(4096):
            acc = (((((acc + a + index) & MASK) ^ b) * 3) + (c ^ nonce)) & MASK
    return acc


def sleeper_result(nonce: int) -> int:
    acc = nonce
    for index in range(4):
        acc = ((acc * 5 + nonce) & MASK) ^ ((index + 0xabcdef0123456789) & MASK)
    return acc


def in_ranges(pc: int, ranges: dict) -> bool:
    return (type(pc) is int and pc % 4 == 0 and isinstance(ranges, dict) and bool(ranges)
            and any(isinstance(row, dict) and type(row.get("base")) is int
                    and type(row.get("bytes")) is int and row["bytes"] > 0
                    and row["base"] <= pc < row["base"] + row["bytes"]
                    for row in ranges.values()))


def validate_sleeping_idle(rows: list, sleepers: list[int]) -> None:
    if (not sleepers or len(set(sleepers)) != len(sleepers)
            or not any(row["record"][3] == 1
                       and row["live_task_states"] == {str(id): 4 for id in sleepers}
                       for row in rows)):
        raise Core0Error("all-sleeping task set lacks an actual pending-after-WFI timer witness")


def arithmetic_ranges(unit: dict, functions: dict, disassembly: str) -> list[dict]:
    by_source = {re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"]): row["symbol"]
                 for row in unit["functions"]}
    churn = by_source.get("Lemma.User.Development.Tasks.Compute.churn")
    round = by_source.get("Lemma.User.Development.Tasks.Compute.chunk")
    if churn not in functions or round not in functions:
        raise Core0Error("genuine Compute arithmetic declarations lack actual ELF function ranges")
    begin, end = functions[round]["base"], functions[round]["base"] + functions[round]["bytes"]
    calls, branches = [], []
    for line in disassembly.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+([a-z][a-z0-9.]*)\s+(.+)", line)
        if not match:
            continue
        pc, opcode, operands = int(match[1], 16), match[2], match[3]
        if not begin <= pc < end:
            continue
        if opcode in {"jal", "jalr", "call"} and "<" + churn + ">" in operands:
            calls.append(pc)
        if opcode in {"j", "beqz", "bnez", "beq", "bne", "blt", "bltu", "bge", "bgeu", "blez", "bgtz"}:
            target = re.search(r"(?:^|,\s*)(0x[0-9a-f]+)\s*<", operands)
            if target and begin <= int(target[1], 16) < pc:
                branches.append((int(target[1], 16), pc))
    loops = [(pc - target + 4, target, pc, call) for target, pc in branches for call in calls if target <= call <= pc]
    if not loops:
        raise Core0Error("Compute object lacks its actual churn-call-containing backward loop")
    size, target, branch, call = min(loops)
    return [{"symbol": churn, **functions[churn]},
            {"symbol": round, "base": target, "bytes": size, "call_pc": call, "backedge_pc": branch}]


class Trace:
    keys = IMAGE_KEYS
    configuration = "tasks-development"
    arithmetic_required = True
    busy_root = "Lemma.User.Development.Tasks.Busy.main"
    busy_callback = "Lemma.User.Development.Tasks.Busy.tick"

    def __init__(self, session: Session):
        self.session = session
        self.tasks, self.creation_queue = {}, deque()
        self.current, self.remaining, self.irq, self.now = None, 499, 0, 0
        self.idle, self.events, self.queries, self.acks = [], [], [], []
        self.pending_ack = None
        audit = session.binding
        self.users = audit.get("elf", {}).get("users", {})
        self.images = audit.get("user_images", {})
        if (set(self.users) != set(self.keys) or set(self.images) != set(self.keys)
                or audit.get("configuration") != self.configuration
                or audit.get("stage") != "supervisor"):
            raise Core0Error("task observation requires its exact supervisor development registry")
        for index, key in enumerate(self.keys):
            image = self.images[key]
            if (image.get("id") != index + 1 or type(image.get("text_bytes")) is not int
                    or not 0 < image["text_bytes"] <= 0xf000
                    or not in_ranges(self.users[key].get("syscall_bridge", {}).get("ecall_pc"),
                                     self.users[key].get("function_ranges"))):
                raise Core0Error("per-image ID/text/ordinary syscall artifact binding differs")
        unit_path = session.image.parent / "users" / "busy" / "unit.json"
        import json
        unit = json.loads(unit_path.read_text())
        # The genuine elaborated source closure, including the loop, must be
        # present. Absence of the syscall declaration is checked structurally,
        # rather than inferred from a task that merely happened not to call it.
        execution = unit.get("used_execution_ops")
        actions = unit.get("functions")
        loops = unit.get("used_loops")
        rendered = json.dumps(unit, sort_keys=True)
        if (not isinstance(execution, list) or not execution or not isinstance(actions, list) or not actions
                or not isinstance(loops, list) or len(loops) != 1
                or loops[0].get("callback") != self.busy_callback
                or "syscall" in str(execution).lower() or "Lemma.User.Syscall" in rendered
                or self.busy_root not in rendered
                or self.busy_callback not in rendered):
            raise Core0Error("Busy genuine reachable closure has a syscall or lacks its maintained loop")
        self.busy_unit = {"path": str(unit_path), "sha256": sha256(unit_path),
                          "execution_requirements": execution,
                          "action_declarations": actions, "genuine_loops": loops}
        self.arithmetic, self.arithmetic_binding = [], {}
        if self.arithmetic_required:
            compute_dir = session.image.parent / "users" / "compute"
            compute_unit = json.loads((compute_dir / "unit.json").read_text())
            self.arithmetic = arithmetic_ranges(compute_unit, self.users["compute"]["function_ranges"],
                                                 (compute_dir / "audit-user-disassembly.txt").read_text())
            self.arithmetic_binding = {name: sha256(compute_dir / name)
                                       for name in ("unit.json", "audit-user-disassembly.txt")}

    def exit_pcs(self, user):
        return {user["exit_ecall_pc"]}

    def expect_create(self, image: int, nonce: int):
        self.creation_queue.append((image, nonce))

    def live(self):
        return {id for id, task in self.tasks.items() if not task["reaped"]}

    def read(self):
        if len(self.session.records) >= MAX_RECORDS:
            raise Core0Error("F observation exhausted its finite record budget")
        event = self.session.record()
        self.observe(event)
        self.events.append(list(event))
        return event

    def observe(self, event):
        tag, a, b, c, d = event
        if tag == 0xf1:
            if (self.current is not None or not self.creation_queue
                    or (b, c) != self.creation_queue.popleft()
                    or a < 512 or a in self.tasks or not 0 <= b < len(self.keys)
                    or d % 4096 or not 0x82000000 <= d < 0x82200000
                    or any(task["root"] == d for id, task in self.tasks.items() if id in self.live())):
                raise Core0Error("creation lacks a fresh generation ID, distinct owned root or requested image/nonce")
            key = self.keys[b]
            pages = 17 + (self.images[key]["text_bytes"] + 4095) // 4096
            self.remaining -= pages
            if self.remaining < 0:
                raise Core0Error("task construction exceeded observed physical capacity")
            self.tasks[a] = {"image": b, "key": key, "nonce": c, "root": d, "pages": pages,
                             "dispatches": 0, "reasons": Counter(), "preempt_irqs": [],
                             "rounds": [], "wakes": [], "start": False, "complete": False,
                             "acc": c, "terminal": None, "stats": None, "reaped": False, "state": 2,
                             "arithmetic_preemptions": []}
        elif tag == 0xf3:
            task = self._task(a)
            if self.current is not None or b != task["root"] or c != task["dispatches"] + 1 or d < self.now:
                raise Core0Error("dispatch/root/counter/monotonic hardware time differs")
            if task["terminal"] is not None:
                raise Core0Error("a terminating task was dispatched again")
            task["dispatches"] = c
            task["state"] = 3
            self.current, self.now = a, d
        elif tag == 0xf2:
            task = self._task(a)
            user = self.users[task["key"]]
            if (self.current != a or b not in {1, 2, 3, 4} or c < self.irq or b == 1 and c <= self.irq
                    or not in_ranges(d, user["function_ranges"])):
                raise Core0Error("return lacks actual current U context, valid cause/PC or monotonic M IRQ count")
            if (b == 4 and d not in self.exit_pcs(user)
                    or b in {2, 3} and d != user["syscall_bridge"]["ecall_pc"]):
                raise Core0Error("yield/sleep/exit did not originate at the audited ordinary ECALL")
            if task["key"] == "busy" and b != 1:
                raise Core0Error("noncooperative Busy returned without a real SSIP preemption")
            self.irq, self.current = c, None
            task["reasons"][b] += 1
            task["state"] = 4 if b == 3 else 6 if b == 4 else 2
            if b == 1:
                task["preempt_irqs"].append(c)
                if task["image"] == 0 and in_ranges(d, {str(i): row for i, row in enumerate(self.arithmetic)}):
                    task["arithmetic_preemptions"].append(list(event))
        elif tag == 0xf4:
            task = self._task(a)
            if self.current is not None or task["terminal"] is not None or d not in {8, 0x100}:
                raise Core0Error("unexpected task fault, duplicate exit or reclamation on the outgoing U stack")
            if d == 8:
                if not task["complete"] or b != 0 or c != task["nonce"] or task["reasons"][4] != 1:
                    raise Core0Error("ordinary task exit differs from independently checked computation/private data")
            elif task["key"] != "busy" or b != 0x55 or c != task["nonce"]:
                raise Core0Error("trusted Busy termination lacks expected code and initialized private word")
            task["terminal"] = list(event)
            task["state"] = 6
        elif tag == 0xf5:
            task = self._task(a)
            if (task["terminal"] is None or task["stats"] is not None
                    or (b, c, d) != (task["reasons"][1], task["reasons"][2], task["dispatches"])):
                raise Core0Error("task lifecycle counters differ from complete observed scheduling transitions")
            task["stats"] = list(event)
        elif tag == 0xf6:
            task = self._task(a)
            if (self.current is not None or task["stats"] is None or d != 0
                    or b != self.remaining or c != b + task["pages"]):
                raise Core0Error("inactive task teardown failed to reclaim its actual complete owned page set")
            self.remaining, task["reaped"] = c, True
        elif tag == 0xf7:
            if self.current is not None or self.pending_ack is None or (a, d) != self.pending_ack:
                raise Core0Error("unexpected or unmatched trusted control acknowledgment")
            self.acks.append(list(event))
        elif tag == 0xfc:
            task = self._task(a)
            if self.current is not None or b not in {2, 4, 5} or c != task["nonce"]:
                raise Core0Error("live task query differs from inactive state/private address-space data")
            self.queries.append(list(event))
        elif tag == 0xfd:
            if self.current is not None or b < self.irq or c not in {0, 1} or not a < d:
                raise Core0Error("idle WFI observation lacks actual pending/time/armed deadline facts")
            self.irq = b
            self.idle.append({"record": list(event), "live_task_states":
                              {str(id): self.tasks[id]["state"] for id in self.live()}})
        elif tag in {0xf8, 0xf9, 0xfa, 0xfb}:
            task = self._task(a)
            if self.current != a or task["key"] == "busy":
                raise Core0Error("user output does not belong to the currently executing separate image")
            nonce = task["nonce"]
            if tag == 0xf8:
                if task["start"] or (b, c, d) != (task["image"] + 1, nonce, nonce):
                    raise Core0Error("user startup identity/nonce/independent private data differs")
                task["start"] = True
            elif tag == 0xf9:
                if not task["start"] or task["image"] != 0 or b != len(task["rounds"]) or b >= 8 or d != nonce:
                    raise Core0Error("compute progress is absent, duplicated, or reordered")
                task["acc"] = compute_round(task["acc"], nonce)
                if c != task["acc"]:
                    raise Core0Error("live registers/arithmetic/private state differ from independent host reference")
                task["rounds"].append(list(event))
            elif tag == 0xfb:
                if (not task["start"] or task["image"] != 1 or len(task["wakes"]) >= 4
                        or d != nonce or b > c or b == 0
                        or task["wakes"] and b <= task["wakes"][-1][2]):
                    raise Core0Error("sleeping task woke before its real deadline or lacks distinct ordered wakes")
                task["wakes"].append(list(event))
            else:
                result = task["acc"] if task["image"] == 0 else sleeper_result(nonce)
                guard = nonce ^ (0x1375a94f2468bace if task["image"] == 0 else 0xe6b1c0387294a5df)
                if (not task["start"] or task["complete"] or (b, c, d) != (result, guard, nonce)
                        or task["image"] == 0 and len(task["rounds"]) != 8
                        or task["image"] == 1 and (len(task["wakes"]) != 4 or task["reasons"][3] != 4)):
                    raise Core0Error("completion lacks exact rounds/wakes/live stack canary/result")
                task["acc"], task["complete"] = result, True
                if task["image"] == 0 and not task["arithmetic_preemptions"]:
                    raise Core0Error("Compute completed without an actual interruption inside its compiled arithmetic loop")
        else:
            raise Core0Error(f"unexpected F record, including fatal/error/fault: {event}")

    def _task(self, id):
        if id not in self.tasks or self.tasks[id]["reaped"]:
            raise Core0Error("record resolved an unknown, stale or already reclaimed task identity")
        return self.tasks[id]

    def until(self, predicate):
        while not predicate():
            self.read()

    def command(self, command: int, a=0, b=0, c=0, d=0, *, status=0, value=None):
        self.pending_ack = (command, a)
        start = len(self.queries)
        transport._write_all(self.session.process, struct.pack("<5Q", command, a, b, c, d),
                             deadline=self.session.deadline, capture=self.session.capture,
                             context=f"sending F control {command}")
        while True:
            event = self.read()
            if event[0] == 0xf7:
                self.pending_ack = None
                if event[2] != status or value is not None and event[3] != value:
                    raise Core0Error(f"actual control status/value differs: {event}")
                if command == 0x31 and status == 0 and event[3] != self.remaining:
                    raise Core0Error("query frame baseline differs from actual creation/reclamation sequence")
                return event, self.queries[start:]


def check(session: Session) -> dict:
    startup = validate_positive_records([session.record() for _ in range(4)])
    kernel, ready = session.record(), session.record()
    if (kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0)
            or ready != (0xf0, 1, 8, 512, 10000)):
        raise Core0Error("F startup kernel root/allocator/task table/quantum differs")
    trace = Trace(session)
    nonces = []
    while len(nonces) < 12:
        value = secrets.randbits(64)
        if value not in nonces and value not in {0, MASK}:
            nonces.append(value)
    for index in range(3):
        trace.expect_create(index, nonces[index])
    transport._write_all(session.process, struct.pack("<5Q", 0x30, *nonces[:3], 0),
                         deadline=session.deadline, capture=session.capture, context="launching three independent U images")
    trace.until(lambda: len(trace.tasks) == 3)
    initial = list(trace.tasks)
    busy = initial[2]
    trace.until(lambda: all(trace.tasks[id]["reaped"] for id in initial[:2])
                and len(set(trace.tasks[busy]["preempt_irqs"])) >= 3)
    _, first = trace.command(0x31, busy)
    if len(first) != 1 or first[0][4] == 0:
        raise Core0Error("Busy did not execute its independently audited syscall-free loop")
    before = len(trace.tasks[busy]["preempt_irqs"])
    trace.until(lambda: len(trace.tasks[busy]["preempt_irqs"]) >= before + 2)
    _, second = trace.command(0x31, busy)
    if len(second) != 1 or second[0][4] <= first[0][4]:
        raise Core0Error("Busy private counter did not progress across actual timer-driven context switches")
    first_preempt = next(i for i, row in enumerate(trace.events) if row[:3] == [0xf2, busy, 1])
    if not any(row[0] in {0xf9, 0xfb} and row[1] in initial[:2] for row in trace.events[first_preempt + 1:]):
        raise Core0Error("peers made no actual user progress while the noncooperative task was alive")

    # Invalid image, malformed arguments, unsupported command and stale IDs
    # must reject without allocation and without poisoning the live scheduler.
    trace.command(0x33, 3, 0, status=81, value=0)
    trace.command(0x31, busy, 1, status=16, value=0)
    trace.command(0x7f, 0, status=17, value=0)
    for id in initial[:2]:
        trace.command(0x31, id, status=74, value=0)
        trace.command(0x32, id, 0x55, status=74, value=0)
    trace.command(0x31, 0)

    # Fill all eight actual slots, reject the ninth, then reclaim every page.
    filled = [busy]
    for nonce in nonces[3:10]:
        trace.expect_create(2, nonce)
        ack, _ = trace.command(0x33, 2, nonce)
        if ack[3] not in trace.tasks or trace.tasks[ack[3]]["nonce"] != nonce:
            raise Core0Error("create ACK differs from its actual published TaskID")
        filled.append(ack[3])
    trace.command(0x33, 2, nonces[10], status=38, value=0)
    trace.until(lambda: all(trace.tasks[id]["dispatches"] >= 2 for id in filled))
    _, rows = trace.command(0x31, 0)
    if {row[1] for row in rows} != set(filled) or any(row[4] == 0 for row in rows):
        raise Core0Error("full task table lacks eight distinct actually executing private user contexts")
    for id in filled:
        trace.command(0x32, id, 0x55, value=id)
        trace.until(lambda: trace.tasks[id]["reaped"])
        trace.command(0x31, id, status=74, value=0)
    trace.command(0x31, 0, value=499)

    # With no Busy left, two sleepers force genuine all-sleeping S WFI idle.
    idle_begin = len(trace.idle)
    sleepers = []
    for nonce in nonces[10:12]:
        trace.expect_create(1, nonce)
        ack, _ = trace.command(0x33, 1, nonce)
        sleepers.append(ack[3])
    trace.until(lambda: all(trace.tasks[id]["reaped"] for id in sleepers))
    validate_sleeping_idle(trace.idle[idle_begin:], sleepers)
    trace.command(0x31, 0, value=499)
    if trace.creation_queue or trace.live() or trace.current is not None or trace.remaining != 499:
        raise Core0Error("F completed with unpublished construction, a live task or a physical page leak")
    tasks = {}
    for id, task in trace.tasks.items():
        tasks[str(id)] = {**task, "reasons": dict(task["reasons"])}
    return {"protocol": "preemptive-tasks-F-v1", "startup": startup, "kernel_root": list(kernel),
            "ready": list(ready), "runtime_nonces": nonces, "tasks": tasks,
            "noncooperative_task_id": busy, "busy_counter_queries": [first[0], second[0]],
            "actual_machine_interrupts": trace.irq, "idle_observations": trace.idle,
            "queries": trace.queries, "acknowledgments": trace.acks,
            "owned_task_table_baseline": 499, "final_remaining_frames": trace.remaining,
            "arithmetic_machine_ranges": trace.arithmetic, "arithmetic_source_machine_binding": trace.arithmetic_binding,
            "busy_genuine_unit": trace.busy_unit, "guest_lifetime": "continuous Action.loop"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        root = repo_root()
        runner_paths = ("scripts/check_kernel_tasks.py", "scripts/check_kernel_supervisor.py",
                        "scripts/check_kernel_user.py", "scripts/check_kernel.py", "scripts/run_kernel.py",
                        "scripts/run_device_session.py", "scripts/run_monitor_session.py")
        runners = {name: sha256(root / name) for name in runner_paths}
        with Session(root=root, image=args.image, output_dir=args.output_dir,
                     timeout=args.timeout, clean=args.clean) as session:
            session.report.update(runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session)
            if {name: sha256(root / name) for name in runner_paths} != runners:
                raise Core0Error("F observation runner changed during guest execution")
            session.finish(observed)
        try:
            from check_kernel import validate_session
            validate_session(session.output_dir / "result.json", session.image)
        except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
            session.report.update(status="FAIL", error=str(error), failure_category="post-cleanup-wire-evidence")
            temporary = session.output_dir / "result.json.tmp"
            write_json(temporary, session.report)
            temporary.replace(session.output_dir / "result.json")
            raise
        print("PASS: actual preemption, private contexts, sleep/idle and complete task-page reclamation observed")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
