#!/usr/bin/env python3
"""Closed real-U architectural containment observations and clean K matrix.

The singleton and managed observers share the maintained frozen UART engine.
Only the selected audited instruction site gains a halfword/privilege exception;
ordinary service actors retain their existing authority and byte checks.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import secrets
import signal
import struct
import sys
import time
from types import SimpleNamespace

from build_core0 import prepare_output_directory
from build_kernel import build, source_inputs
from check_kernel import acceptance_inputs, source_identity, stop_controller_children
from check_kernel_buffer import (ServiceTrace, input_bytes, startup, RUNNERS, MAX_EVENTS)
from check_kernel_supervisor import validate_positive_records
from check_kernel_tasks import in_ranges
from check_kernel_user import satp, mix, task_frame_overhead
from core0_common import Core0Error, load_json, repo_root, sha256, write_json
from buffer_transport import decode_uart
from run_buffer_session import BufferSession, validate_quiescence

PROTOCOL = "architectural-containment-K-v1"
USER_STATUS = 0x200000020
ARGUMENTS = (7, 0, 7)
CASES = {
    "halfword-ecall": ("lemma_user_attack_halfword_ecall", 8, 0, 0x00000073, 4),
    "return-supervisor": ("lemma_user_attack_supervisor_return", 2, 0x10200073, 0x10200073, 5),
    "return-machine": ("lemma_user_attack_machine_return", 2, 0x30200073, 0x30200073, 5),
}
CONFIGURATIONS = {prefix + case + "-development": case
                  for prefix in ("user-", "service-") for case in CASES}
SERVICE_CONFIGURATIONS = tuple(cfg for cfg in CONFIGURATIONS if cfg.startswith("service-"))
MATRIX = tuple((cfg, opt) for cfg in CONFIGURATIONS for opt in ("O0", "O2"))

# Closed source inventory for current four-page construction/teardown. This
# observer independently checks the actual unit's source identities; historical
# two-page evidence is retained separately and cannot satisfy the new fields.
CURRENT_QUAD_STACK_SOURCES = {
    'Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue',
    *('Lemma.Kernel.Loader.'+name for name in (
        'allocateStack','allocateStackQuad','installStackQuad','storedQuad','quadFrame','stackFrame',
        'validateExpandedStack','teardown','releaseStackHandle','stackCanary',
        'kernelStackHandleOffset','kernelStackSecondHandleOffset','kernelStackTopOffset',
        'kernelStackThirdHandleOffset','kernelStackFourthHandleOffset','kernelStackPagesOffset','kernelStackBaseOffset')),
    *('Lemma.Kernel.Memory.Frames.'+name for name in (
        'allocateContiguous4','resolvePurpose','mappingCount','runtimeCount','runtimeQuota','configure','init')),
    *('Lemma.Kernel.Memory.AddressSpace.'+name for name in (
        'create','buildRegistry','copyRegistryStep','base','validateRegistry','destroy','rollbackRegistry',
        'registryCount','registryList','expandedCapacity')),
    'Lemma.Kernel.Memory.Batch.allocate','Lemma.Kernel.BootServices.bootServices',
    'Lemma.Kernel.Process.validateFrame','Lemma.Kernel.Process.validateStack',
    'Lemma.Kernel.Development.ServiceEntry.dispatch','Lemma.Kernel.Scheduler.dispatch',
    'Lemma.Kernel.Task.capture','Lemma.Kernel.Task.context',
}


def runner_inputs(root):
    return {name: sha256(root / name) for name in (*RUNNERS, "scripts/check_kernel_architecture.py")}


def require_diagnostics(image, binding, managed):
    """Require the audited original-frame diagnostic and its actual source gates."""
    value = binding.get("architecture_diagnostics")
    p, q, t = "Lemma.Kernel.Process.", "Lemma.Kernel.Scheduler.", "Lemma.Kernel.Task."
    read, record = "Lemma.Kernel.Memory.Access.read64", "Lemma.Kernel.Console.record"
    context = "Lemma.Kernel.Memory.AddressSpace.context"
    required = {p+"validateFrame", read, record}
    required |= ({q+"dispatch", q+"reportFault", q+"failed", q+"finish", q+"returnKernel", t+"capture", t+"failed", context}
                 if managed else {p+"dispatch", p+"userTrap", p+"failed", p+"finish"})
    expected = [(q+"dispatch", t+"capture", q+"reportFault", q+"failed"),
                (t+"capture", p+"validateFrame", context, t+"failed"),
                (q+"reportFault", read, record, q+"failed"),
                (q+"reportFault", record, q+"finish", q+"failed")] if managed else [
                (p+"dispatch", p+"validateFrame", read, p+"failed")]
    if (not isinstance(value, dict) or any(type(value.get(k)) is not int for k in
            ("raw_status_offset", "diagnostic_tag", "termination_code"))
            or (value["raw_status_offset"], value["diagnostic_tag"], value["termination_code"]) != (264, 212, 44)
            or value.get("diagnostic_words") != ["cause", "pc", "stval", "original_hardware_status"]
            or value.get("halfword_ecall_return_reason") != (4 if managed else None)
            or value.get("hardware_fault_return_reason") != (5 if managed else None)
            or (managed and any(type(value.get(k)) is not int for k in
                ("halfword_ecall_return_reason", "hardware_fault_return_reason")))):
        raise Core0Error("architecture evidence lacks the exact original hardware-status diagnostic")
    sources = value.get("source_functions")
    kernel = load_json(image.parent / "kernel/unit.json")
    actual = {re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"]): row["symbol"] for row in kernel.get("functions", [])}
    if (not isinstance(sources, dict) or set(sources) != required
            or any(not isinstance(symbol, str) or not symbol.startswith("lemma_kernel_")
                   or actual.get(source) != symbol for source, symbol in sources.items())):
        raise Core0Error("architecture diagnostic source identities differ from the genuine kernel unit")
    gates = value.get("ownership_gates")
    if not isinstance(gates, list) or len(gates) != len(expected):
        raise Core0Error("architecture diagnostic ownership gates are missing or unexpected")
    for gate, (caller, checked, protected, failed) in zip(gates, expected):
        if not isinstance(gate, dict) or not isinstance(gate.get("gate"), dict):
            raise Core0Error("architecture diagnostic ownership gate is malformed")
        proof = gate.get("gate", {})
        if (gate.get("source") != caller or gate.get("checked") != sources[checked]
                or gate.get("protected") != sources[protected] or gate.get("failure_helper") != sources[failed]
                or gate.get("component") != "status" or type(gate.get("equals")) is not int or gate["equals"] != 0
                or proof.get("success_when_true") is not False
                or any(not isinstance(proof.get(k), str) or not proof[k] for k in ("comparison", "block", "success", "failure"))
                or not isinstance(proof.get("protected_blocks"), list) or not proof["protected_blocks"]
                or any(not isinstance(label, str) or not label for label in proof["protected_blocks"])):
            raise Core0Error("architecture diagnostic bypasses a required checked ownership/status gate")
    order = value.get("diagnostic_before_termination", {})
    if not isinstance(order, dict):
        raise Core0Error("architecture diagnostic ordering is malformed")
    sites = order.get("protected_sites")
    if (order.get("before") != sources[record] or order.get("after") != sources[(q if managed else p)+"finish"]
            or not isinstance(sites, list) or not sites
            or any(not isinstance(site, list) or len(site) != 2 or not isinstance(site[0], str) or not site[0]
                   or type(site[1]) is not int or site[1] < 0 for site in sites)):
        raise Core0Error("architecture diagnostic lacks checked record-before-termination ordering")
    return deepcopy(value)


def require_managed_task_stack(image, binding):
    """Require exact global/owner accounting and genuine owned-stack sources.

    The AS descriptor belongs to kernel owner1.  A managed instance therefore
    consumes19 global base frames while charging18 to its private owner;
    text pages are additional.  This is distinct from the legacy single-owner
    singleton accounting accepted by task_frame_overhead.
    """
    stack = binding.get("task_kernel_stack")
    numeric = {"pages":4,"bytes":16384,"usable_bytes":16352,"sentinel_bytes":32,
               "first_handle_offset":2400,"second_handle_offset":2480,"third_handle_offset":2488,
               "fourth_handle_offset":2496,"pages_offset":2504,"base_offset":2512,
               "base_owned_task_frames":18,"base_global_task_frames":19}
    if (not isinstance(stack, dict) or set(stack) != {*numeric,"construction","source_functions","sentinels_are_hardware_guards"}
            or any(type(stack.get(name)) is not int or stack[name] != value for name, value in numeric.items())
            or stack.get("construction") != "owned-physically-contiguous-four"
            or stack.get('sentinels_are_hardware_guards') is not False):
        raise Core0Error("managed architecture accounting lacks exact owned18/global19 four-page stack construction")
    required = CURRENT_QUAD_STACK_SOURCES
    sources = stack.get("source_functions")
    unit = load_json(image.parent / "kernel/unit.json")
    actual = {re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"]): row["symbol"]
              for row in unit.get("functions", [])}
    if (not isinstance(sources, dict) or set(sources) != required
            or any(not isinstance(symbol, str) or not symbol.startswith("lemma_kernel_")
                   or actual.get(source) != symbol for source, symbol in sources.items())):
        raise Core0Error("managed architecture owned-stack identities differ from the genuine kernel unit")
    return deepcopy(stack)


def require_case(image, binding):
    """Bind the closed case to genuine main, full attack bytes and actual site."""
    cfg = binding.get("configuration")
    if cfg not in CONFIGURATIONS or binding.get("stage") != "supervisor" or binding.get("status") != "PASS":
        raise Core0Error("architecture observer requires one of six exact supervisor configurations")
    case = CONFIGURATIONS[cfg]
    managed = cfg in SERVICE_CONFIGURATIONS
    diagnostic = require_diagnostics(image, binding, managed)
    if managed:
        require_managed_task_stack(image, binding)
    else:
        task_frame_overhead(SimpleNamespace(binding=binding))
    user = binding.get("elf", {}).get("users", {}).get("fault", {}) if managed else binding.get("elf", {}).get("user", {})
    row = user.get("quarantined_startup", {})
    site = row.get("instruction_site", {})
    symbol, cause, stval, opcode, reason = CASES[case]
    if (row.get("case") != case or row.get("symbol") != symbol
            or any(type(row.get(k)) is not int for k in ("base", "bytes", "fault_pc"))
            or not isinstance(site, dict) or set(site) != {"pc", "offset", "instruction_bits", "opcode"}
            or any(type(v) is not int for v in site.values())
            or site["instruction_bits"] != 32 or site["opcode"] != opcode
            or site["pc"] != row["fault_pc"] or site["pc"] != row["base"] + site["offset"]
            or not 0 <= site["offset"] <= row["bytes"] - 4):
        raise Core0Error("architecture case lacks its exact audited symbol-relative instruction site")
    directory = image.parent / ("users/fault" if managed else "user")
    unit = load_json(directory / "unit.json")
    roots = unit.get("roots")
    if (not isinstance(roots, list) or len(roots) != 1
            or roots[0].get("source") != "Lemma.User.Entry.main" or roots[0].get("args") != ["u64"]
            or unit.get("configuration") != cfg or unit.get("role") != "user"
            or not any(f.get("source") == "Lemma.User.Entry.main" and f.get("symbol") == roots[0].get("symbol")
                       for f in unit.get("functions", []))):
        raise Core0Error("architecture attack lacks the genuine maintained User main precondition")
    raw_path = directory / "text.bin" if managed else image.parent / "user-text.bin"
    raw = raw_path.read_bytes()
    if managed:
        metadata = binding.get("user_images", {}).get("fault", {})
        if (metadata.get("id") != 5 or metadata.get("source") != "Lemma.User.Entry.main"
                or metadata.get("module") != "Lemma.User.Entry" or metadata.get("boot_role") != "buffer-fault-client"
                or type(metadata.get("text_bytes")) is not int or metadata["text_bytes"] != len(raw)
                or metadata.get("text_sha256") != sha256(raw_path)
                or any(binding.get("elf", {}).get("users", {}).get(key, {}).get("quarantined_startup", {}).get("case") != "none"
                       for key in ("server", "cli", "peer", "busy"))):
            raise Core0Error("architecture package changed an ordinary actor or selected a different genuine fault image")
    begin = row["base"] - 0x10000
    if (not 0 <= begin <= len(raw) - row["bytes"]
            or hashlib.sha256(raw[begin:begin+row["bytes"]]).hexdigest() != row.get("raw_sha256")
            or struct.unpack_from("<I", raw, begin + site["offset"])[0] != opcode):
        raise Core0Error("architecture instruction site differs from actual linked User text")
    if case == "halfword-ecall":
        if (site["offset"] % 4 != 2 or site["offset"] < 2
                or raw[begin+site["offset"]-2:begin+site["offset"]+6] != struct.pack("<II", 0x00730013, 0)):
            raise Core0Error("halfword ECALL lacks its exact overlapping audited words")
    elif site["offset"] != 0 or row["bytes"] != 4:
        raise Core0Error("illegal return case is not its sole exact privileged word")
    return {"case": case, "configuration": cfg, "managed": managed,
            "site": deepcopy(row), "cause": cause, "stval": stval, "reason": reason,
            "architecture_diagnostics": diagnostic,
            "unit_sha256": sha256(directory / "unit.json"), "text_sha256": sha256(raw_path)}


class ArchitectureSession(BufferSession):
    CONFIGURATIONS = tuple(CONFIGURATIONS)
    RUNNER_PATHS = (*BufferSession.RUNNER_PATHS, "scripts/check_kernel_architecture.py")


def check_singleton(session):
    spec = require_case(session.image, session.binding)
    if spec["managed"]:
        raise Core0Error("singleton observer received a managed artifact")
    initial = validate_positive_records([session.record() for _ in range(4)])
    kernel = session.record()
    if kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]), 500, 0):
        raise Core0Error("singleton architecture stable kernel root/baseline differs")
    user = session.binding["elf"]["user"]
    text_bytes = (session.image.parent / "user-text.bin").stat().st_size
    before = 500 - task_frame_overhead(session) - (text_bytes + 4095)//4096
    ids, runs = set(), []
    for argument in ARGUMENTS:
        loaded = session.command(1, argument, 0, 0, 0)
        if (loaded[0] != 0xd0 or loaded[1] < 512 or loaded[1] in ids or loaded[2] == kernel[1]
                or loaded[3:] != (0x10000, text_bytes)):
            raise Core0Error("architecture instance lacks fresh identity/root/entry/real text")
        ids.add(loaded[1]); translation = satp(loaded[2])
        forwarded, trap = [], session.record()
        while trap[0] == 0xdf:
            if (len(forwarded) >= 32 or trap[1] != 0x8000000000000001
                    or trap[3:] != (USER_STATUS, translation)
                    or not (in_ranges(trap[2], user["function_ranges"]) or trap[2] == spec["site"]["fault_pc"])):
                raise Core0Error("architecture notification differs from exact saved User context")
            forwarded.append(list(trap)); trap = session.record()
        expected = (0xd4, spec["cause"], spec["site"]["fault_pc"], spec["stval"], USER_STATUS)
        if trap != expected:
            raise Core0Error(f"actual architectural trap/raw status differs: {trap}; expected {expected}")
        context = session.record()
        if context != (0xd1 if spec["cause"] == 8 else 0xdc, spec["cause"], trap[2], USER_STATUS, translation):
            raise Core0Error("architectural task termination lost actual status/PC/SATP")
        result = session.record()
        if result != (0xd2, 44, mix(argument), before, 500):
            raise Core0Error("architectural precondition/private data/full reclamation differs")
        runs.append({"argument": argument, "loaded": list(loaded), "notifications": forwarded,
                     "trap": list(trap), "context": list(context), "reclaimed": list(result)})
    return {"protocol": PROTOCOL, "configuration": spec["configuration"], "case": spec,
            "managed": False, "startup": initial, "kernel": list(kernel), "instances": runs}


class ArchitectureServiceTrace(ServiceTrace):
    configurations = SERVICE_CONFIGURATIONS
    development_configurations = SERVICE_CONFIGURATIONS

    def __init__(self, session):
        self.case = require_case(session.image, session.binding)
        super().__init__(session)

    def observe(self, event):
        if len(event) != 5 or any(type(x) is not int or not 0 <= x < 2**64 for x in event):
            raise Core0Error("architecture control is not five unsigned words")
        tag, a, b, c, d = event
        if tag == 0xd4:
            if self.current is None:
                raise Core0Error("architecture trap lacks a current task")
            task = self.actual_user(self.current, {"fault"})
            if (a, b, c, d) != (self.case["cause"], self.case["site"]["fault_pc"], self.case["stval"], USER_STATUS):
                raise Core0Error("managed architectural cause/site/stval/raw status differs")
            if any(row["task"] == self.current for row in self.faults):
                raise Core0Error("duplicate managed architectural trap")
            self.faults.append({"task": self.current, "record": list(event), "index": len(self.session.events)-1})
            return
        task = self.tasks.get(a)
        if tag == 0xf3 and task and task["key"] == "fault" and any(row["task"] == a for row in self.faults):
            raise Core0Error("architectural fault was resumed after its actual terminal trap")
        if tag == 0xf2 and task and task["key"] == "fault":
            site = self.case["site"]["fault_pc"]
            if (self.current != a or c < self.irq or b not in {1, self.case["reason"]}
                    or b == 1 and (c <= self.irq or any(row["task"] == a for row in self.faults))
                    or not (in_ranges(d, self.users["fault"]["function_ranges"]) or d == site)):
                raise Core0Error("architectural return lacks owned task/actual IRQ/exact linked PC")
            if b != 1 and (d != site or not any(row["task"] == a for row in self.faults)):
                raise Core0Error("architectural termination lacks its prior actual trap and exact reason")
            self.current = None; self.irq = c; task["reasons"][b] += 1
            task["state"] = 2 if b == 1 else 6
            if b == 1: task["preempt_irqs"].append(c)
            return
        if tag == 0xf4 and task and task["key"] == "fault":
            if (self.current is not None or task["terminal"] is not None
                    or (b, c, d) != (44, mix(task["nonce"]), self.case["cause"])
                    or task["reasons"][self.case["reason"]] != 1
                    or not any(row["task"] == a for row in self.faults)):
                raise Core0Error("managed architecture finish44/genuine private mix/reason differs")
            task["terminal"] = list(event); task["state"] = 6
            return
        super().observe(event)
        if tag == 0xf1:
            self.tasks[a]["created_wire"] = len(self.session.events)-1
        elif tag == 0xf6:
            self.tasks[a]["reaped_wire"] = len(self.session.events)-1

    def snapshot(self):
        return {**super().snapshot(), "protocol": PROTOCOL, "managed": True, "case": self.case}


def managed_qualification(trace):
    trace.require_settled_releases()
    faults = [t for t in trace.tasks.values() if t["key"] == "fault"]
    if (len(faults) != 3 or tuple(t["nonce"] for t in faults) != ARGUMENTS
            or len(trace.faults) != 3 or any(not t["reaped"] or t["terminal"] is None for t in faults)
            or trace.live() or trace.current is not None or trace.remaining != 497
            or trace.pending_rpc or trace.pending_ack or trace.creation_queue or trace.pending_expiry
            or len(trace.publications) != 1 or trace.epoch != 1 or trace.restart_witnesses):
        raise Core0Error("managed architecture lacks three contained fresh tasks and full final reclamation")
    for i, task in enumerate(faults):
        begin = task["reaped_wire"]
        end = faults[i+1]["created_wire"] if i+1 < len(faults) else len(trace.session.events)
        records = [e["value"] for e in trace.session.events[begin+1:end] if e["kind"] == "kernel"]
        rows = [r for r in trace.rpc_pairs if begin < r["input"]["index"] < r["index"] <= end]
        writes = [r for r in rows if r["input"]["words"][0] == 2 and r["input"]["words"][4] == 128
                  and r["response"]["application_status"] == 0 and r["response"]["transport_status"] == 0
                  and b"\x00\xff" in bytes.fromhex(r["input"]["data_hex"])]
        if (not writes or not any(r["input"]["words"][0] == 3 and r["response"]["count"] == 128
                                 and r["response"]["data_hex"] == w["input"]["data_hex"]
                                 and r["input"]["words"][2] == w["input"]["words"][2]
                                 and r["index"] > w["index"] for r in rows for w in writes)
                or not any(r[0] == 0x334 for r in records)
                or not any(r[0] == 0xf2 and trace.tasks[r[1]]["key"] == "busy" and r[2] == 1
                           and in_ranges(r[4], trace.busy_math_range) for r in records)):
            raise Core0Error("ordinary binary service/Peer/arithmetic preemption did not continue after each fault")
    return {"fresh_instances": 3, "actual_faults": 3, "ordinary_continuations": 3,
            "final_remaining_frames": 497, "actual_math_preemptions": len(trace.busy_math)}


def check_managed(session):
    facts = startup([session.event() for _ in range(7)])
    trace = ArchitectureServiceTrace(session)
    try:
        trace.until(lambda: len(trace.tasks) == 4 and len(trace.publications) == 1
                    and all(t["start"] for t in trace.tasks.values() if t["key"] != "busy")
                    and any(r[0] == 0x334 for r in trace.actor_events))
        for argument in ARGUMENTS:
            ack = trace.diagnostic(0x33, 4, argument)
            identity = ack[3]
            trace.until(lambda: trace.tasks[identity]["reaped"])
            math_before = len(trace.busy_math)
            peer_before = sum(r[0] == 0x334 for r in trace.actor_events)
            prefix = b"\x00\xffLMI1LMO1K1"
            payload = prefix + secrets.token_bytes(128 - len(prefix))
            handle = trace.rpc(1, length=128)["handle"]
            trace.rpc(2, handle=handle, length=128, data=payload)
            trace.rpc(3, handle=handle, length=128)
            trace.rpc(6, handle=handle)
            trace.rpc(10, epoch=0)
            trace.until(lambda: len(trace.busy_math) > math_before
                        and sum(r[0] == 0x334 for r in trace.actor_events) > peer_before)
        trace.until(lambda: trace.service_quiescent(trace.role("peer")))
        for identity in sorted(trace.live(), key=lambda n: trace.tasks[n]["key"] != "server"):
            trace.diagnostic(0x32, identity)
            trace.until(lambda identity=identity: trace.tasks[identity]["reaped"])
        trace.diagnostic(0x31, 0)
        return {**trace.snapshot(), "startup": facts, "qualification": managed_qualification(trace)}
    finally:
        session.report["architecture_progress"] = trace.snapshot()


def check(session):
    return check_managed(session) if session.binding.get("configuration") in SERVICE_CONFIGURATIONS else check_singleton(session)


def validate_replay(root, image, report, directory):
    events, tail = decode_uart((directory / "received.bin").read_bytes())
    if (tail or events != report.get("wire_events") or report.get("complete_raw_coverage") is not True
            or not events or len(events) > MAX_EVENTS or report.get("wire_format") != "kernel-buffer-uart-v1"):
        raise Core0Error("architecture replay requires all complete retained UART frames")
    binding = load_json(image.parent / "audit.json")
    spec = require_case(image, binding)
    observed = report.get("observed", {})
    if observed.get("protocol") != PROTOCOL or observed.get("configuration") != spec["configuration"]:
        raise Core0Error("architecture report/configuration identity differs")
    if not spec["managed"]:
        class Offline:
            def __init__(self):
                self.image, self.binding, self.root = image, binding, root
                self.events, self.commands, self.cursor = events, bytearray(), 0
            def record(self):
                if self.cursor >= len(events) or events[self.cursor]["kind"] != "kernel":
                    raise Core0Error("singleton replay lacks its next exact kernel record")
                result = tuple(events[self.cursor]["value"]); self.cursor += 1
                return result
            def command(self, *words):
                self.commands.extend(struct.pack("<5Q", *words))
                return self.record()
        offline = Offline(); replayed = check_singleton(offline)
        if offline.cursor != len(events) or bytes(offline.commands) != (directory / "sent.bin").read_bytes():
            raise Core0Error("singleton architecture has unexpected suffix/input bytes")
    else:
        actions = observed.get("actions")
        if (not isinstance(actions, list) or not actions
                or any(type(a.get("index")) is not int or not 7 <= a["index"] < len(events) for a in actions)
                or [a["index"] for a in actions] != sorted(a["index"] for a in actions)
                or b"".join(input_bytes(a) for a in actions) != (directory / "sent.bin").read_bytes()):
            raise Core0Error("managed architecture input actions differ from actual ordered bytes")
        offline = SimpleNamespace(root=root, image=image, binding=binding, report={}, events=events[:7], records=[])
        facts = startup(events); trace = ArchitectureServiceTrace(offline); cursor = 0
        keys = {"kind", "index", "words", "data_hex", "epoch", "expected_transport", "expected_status", "raw_hex"}
        for index, event in enumerate(events[7:], 7):
            while cursor < len(actions) and actions[cursor]["index"] == index:
                trace.begin_action({k: deepcopy(v) for k, v in actions[cursor].items() if k in keys}); cursor += 1
            offline.events.append(event)
            if event["kind"] == "kernel":
                trace.observe(tuple(event["value"])); trace.events.append(event["value"])
            else: trace.client(event["value"])
        if cursor != len(actions): raise Core0Error("managed architecture has unconsumed input actions")
        replayed = {**trace.snapshot(), "startup": facts, "qualification": managed_qualification(trace)}
    return {**replayed, "complete_semantic_replay": True, "replayed_wire_events": len(events)}


def observe(*, root, image, output_dir, timeout, clean=False):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise Core0Error("architecture guest timeout must be finite, positive and at most300 seconds")
    session = None
    try:
        with ArchitectureSession(root=root, image=image, output_dir=output_dir, timeout=timeout, clean=clean) as session:
            consumers = runner_inputs(root)
            session.report["architecture_runner_inputs"] = consumers
            session.finish(check(session))
        session.report["architecture_runner_inputs_after"] = runner_inputs(root)
        if session.report["architecture_runner_inputs_after"] != consumers:
            raise Core0Error("architecture observer inputs changed during execution")
        session.report["observed"] = validate_replay(root, image.resolve(), session.report, output_dir.resolve())
        return session.report
    except Exception as error:
        if session is not None:
            session.report.update(status="FAIL", error=str(error))
        raise
    finally:
        if session is not None:
            write_json(session.output_dir / "result.json.tmp", session.report)
            (session.output_dir / "result.json.tmp").replace(session.output_dir / "result.json")


def _check_deadline(finish_by):
    if finish_by is not None and time.monotonic() >= finish_by:
        raise Core0Error("architecture matrix absolute deadline expired")


def validate_architecture(path: Path, root: Path, *, finish_by=None) -> dict:
    """Revalidate every mandatory fresh clean K configuration/optimization."""
    from check_kernel import validate_session
    _check_deadline(finish_by)
    value = load_json(path)
    if (type(value.get("schema_version")) is not int or value["schema_version"] != 1 or value.get("artifact_category") != "kernel-K-clean-architecture"
            or type(value.get("deadline_seconds")) not in (int, float) or not math.isfinite(value["deadline_seconds"])
            or not 0 < value["deadline_seconds"] <= 2400
            or type(value.get("elapsed_seconds")) not in (int, float) or not math.isfinite(value["elapsed_seconds"])
            or not 0 <= value["elapsed_seconds"] <= value["deadline_seconds"]
            or value.get("status") != "PASS" or value.get("source") != source_identity(root)
            or value.get("source_inputs") != source_inputs(root) or value.get("acceptance_inputs") != acceptance_inputs(root)
            or value.get("source_unchanged_after") is not True or value.get("acceptance_unchanged_after") is not True
            or not isinstance(value.get("cases"), list) or len(value["cases"]) != len(MATRIX)):
        raise Core0Error("architecture matrix lacks exact clean source/all twelve cases")
    for row, (configuration, optimization) in zip(value["cases"], MATRIX):
        _check_deadline(finish_by)
        if (type(row.get("returncode")) is not int or
                (row.get("configuration"), row.get("optimization"), row.get("status"), row.get("returncode")) != (configuration, optimization, "PASS", 0)):
            raise Core0Error("architecture matrix configuration/actual result differs")
        image = Path(row["image"])
        for key, artifact in (("image_sha256", image), ("result_sha256", Path(row["result"])),
                              ("audit_sha256", image.parent / "audit.json"), ("provenance_sha256", image.parent / "provenance.json"),
                              ("log_sha256", Path(row["log"]))):
            if sha256(artifact) != row.get(key): raise Core0Error("architecture matrix artifact changed or is missing")
        provenance = load_json(image.parent / "provenance.json")
        if (provenance.get("source_commit") != value["source"]["commit"] or provenance.get("dirty_paths") != []
                or provenance.get("source_inputs") != value["source_inputs"]
                or (provenance.get("configuration"), provenance.get("optimization"), provenance.get("stage")) != (configuration, optimization, "supervisor")):
            raise Core0Error("architecture matrix contains stale/different source evidence")
        validate_session(Path(row["result"]), image)
        _check_deadline(finish_by)
    _check_deadline(finish_by)
    return value


def matrix(*, root, work_dir, clean, timeout, deadline):
    root = root.resolve(); work_dir = (root / work_dir).resolve()
    if (type(deadline) not in (int, float) or not math.isfinite(deadline) or not 0 < deadline <= 2400
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 600):
        raise Core0Error("architecture build timeout<=600/deadline<=2400 required")
    try: relative = work_dir.relative_to((root / "build/kernel").resolve())
    except ValueError as error: raise Core0Error("architecture evidence must stay in build/kernel") from error
    if not relative.parts: raise Core0Error("refusing to replace all kernel evidence")
    identity = source_identity(root); prepare_output_directory(work_dir, root, clean=clean)
    started = time.monotonic(); finish_by = started + deadline
    value = {"status": "FAIL", "schema_version": 1, "artifact_category": "kernel-K-clean-architecture",
             "deadline_seconds": deadline,
             "source": identity, "source_inputs": source_inputs(root), "acceptance_inputs": acceptance_inputs(root), "cases": []}
    def remaining():
        left = finish_by - time.monotonic()
        if left <= 0: raise Core0Error("architecture matrix absolute deadline expired")
        return left
    try:
        for cfg, opt in MATRIX:
            if remaining() < 180: raise Core0Error("insufficient deadline for complete next architectural observation")
            directory = work_dir / (cfg + "-" + opt); output = work_dir / (cfg + "-" + opt + "-run")
            row = {"configuration": cfg, "optimization": opt, "status": "RUNNING", "returncode": None,
                   "image": str(directory / "image.elf"), "result": str(output / "result.json")}
            value["cases"].append(row)
            result = build(root=root, output_dir=directory, opt_level=opt, stage="supervisor", configuration=cfg, timeout_seconds=min(timeout, remaining()))
            if result.get("status") != "BUILT": raise Core0Error("architecture build did not complete")
            image = directory / "image.elf"
            captured = io.StringIO(); code = None; log = work_dir / (cfg + "-" + opt + ".log")
            try:
                with redirect_stdout(captured), redirect_stderr(captured):
                    observed = observe(root=root, image=image, output_dir=output, timeout=min(120, remaining()))
                    code = 0 if observed.get("status") == "PASS" else 1
                    print(f"{observed['status']}: {cfg}/{opt}; {len(observed['records'])} actual records; complete architectural replay")
            except Exception as error:
                captured.write(f"FAIL: {type(error).__name__}: {error}\n")
                code = 1
                row.update(status="FAIL", error=str(error))
                raise
            finally:
                log.write_text(captured.getvalue())
                row.update(returncode=code, log=str(log), log_sha256=sha256(log))
            row.update(status="PASS", image_sha256=sha256(image), audit_sha256=sha256(directory / "audit.json"),
                       provenance_sha256=sha256(directory / "provenance.json"), result_sha256=sha256(output / "result.json"))
            if code != 0: raise Core0Error("architecture observation failed")
            remaining()
        if source_identity(root) != identity or source_inputs(root) != value["source_inputs"] or acceptance_inputs(root) != value["acceptance_inputs"]:
            raise Core0Error("architecture matrix source/acceptance inputs changed")
        value.update(status="PASS", source_unchanged_after=True, acceptance_unchanged_after=True)
        remaining()
    except Exception as error: value.update(error=str(error))
    finally:
        value["elapsed_seconds"] = time.monotonic()-started
        write_json(work_dir / "result.json.tmp", value); (work_dir / "result.json.tmp").replace(work_dir / "result.json")
    if value["status"] == "PASS":
        try:
            validate_architecture(work_dir / "result.json", root, finish_by=finish_by)
            remaining()
            value["elapsed_seconds"] = time.monotonic()-started
            write_json(work_dir / "result.json", value)
            remaining()
        except Exception as error:
            value.update(status="FAIL", error=str(error), elapsed_seconds=time.monotonic()-started)
            write_json(work_dir / "result.json", value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", type=Path); group.add_argument("--work-dir", type=Path)
    parser.add_argument("--output-dir", type=Path); parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300); parser.add_argument("--deadline", type=float, default=2400)
    args = parser.parse_args()
    def interrupted(number, _):
        stop_controller_children(defer_qemu=True)
        raise Core0Error(f"architecture controller interrupted by signal{number}")
    old = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    for number in old: signal.signal(number, interrupted)
    try:
        root = repo_root()
        if args.image is not None:
            if args.output_dir is None: raise Core0Error("focused architecture observer requires --output-dir")
            result = observe(root=root, image=args.image.resolve(), output_dir=(root/args.output_dir).resolve(), timeout=args.timeout, clean=args.clean)
        else:
            if args.output_dir is not None: raise Core0Error("matrix output is selected by --work-dir")
            result = matrix(root=root, work_dir=args.work_dir, clean=args.clean, timeout=args.timeout, deadline=args.deadline)
        print(result["status"] + ": " + result.get("error", "source-bound actual architectural containment"))
        return 0 if result["status"] == "PASS" else 1
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        print(f"FAIL: {error}"); return 1
    finally:
        stop_controller_children()
        for number, handler in old.items(): signal.signal(number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
