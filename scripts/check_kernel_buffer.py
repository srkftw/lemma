#!/usr/bin/env python3
"""Bounded real-guest Buffer service observation; the byte oracle is host-only.

No generated expected transcript establishes a guest pass. All complete UART
frames, including a cleanup suffix, are replayed through the same task/authority
and application checker before a successful report is published.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import math
import secrets
import struct

from core0_common import Core0Error, repo_root, sha256, write_json
from run_buffer_session import BufferSession
from run_kernel import transport
from buffer_transport import command, decode_uart, input_envelope
from buffer_reference import BufferReference, Request, MASK, PUBLIC_ALLOCATION_ERRORS
from check_kernel_tasks import Trace, in_ranges
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import satp

MAX_EVENTS = 131072
POLICY = "lemma-buffer-service-v1"
RUNNERS = ("scripts/check_kernel_buffer.py", "scripts/check_kernel_tasks.py",
           "scripts/check_kernel_supervisor.py", "scripts/check_kernel_user.py",
           "scripts/check_kernel.py", "scripts/run_buffer_session.py",
           "scripts/buffer_transport.py", "scripts/buffer_reference.py", "scripts/buffer-cli.py",
           "scripts/run_kernel.py", "scripts/run_device_session.py", "scripts/run_monitor_session.py")


def pattern(seed, owner, count):
    return bytes(((((seed ^ owner) >> ((i % 8) * 8)) ^ (i * 37)) & 255) for i in range(count))


def digest(data):
    value = 1469598103934665603
    for byte in data:
        value = ((value * 1099511628211) & MASK) ^ byte
    return value


def require_service_binding(audit):
    graph = audit.get("managed_service")
    edges = graph.get("source_call_edges") if isinstance(graph, dict) else None
    required = {("Lemma.Kernel.Objects.destroy", "Lemma.Kernel.Objects.withdrawService"),
                ("Lemma.Kernel.Objects.beginRevoke", "Lemma.Kernel.Objects.withdrawService"),
                ("Lemma.Kernel.Directory.discover", "Lemma.Kernel.Capability.grantDiscovered"),
                ("Lemma.Kernel.KernelInput.read", "Lemma.Kernel.Memory.UserCopy.validateWrite"),
                ("Lemma.Kernel.KernelInput.read", "Lemma.Kernel.Memory.UserCopy.copyToUser")}
    if (not isinstance(graph, dict) or graph.get("managed_policy") != POLICY
            or not isinstance(edges, list) or not edges
            or any(not isinstance(e, list) or len(e) != 2 or any(type(x) is not str for x in e) for e in edges)
            or not required <= {tuple(e) for e in edges}
            or not graph.get("checked_cfg_gates")):
        raise Core0Error("J lacks actual service binding/input/discovery source and CFG audit")
    return graph


class ServiceTrace(Trace):
    configurations = ("service-normal", "service-development")
    development_configurations = ("service-development",)
    arithmetic_required = False
    busy_root = "Lemma.Applications.CPUBound.main"
    busy_callback = "Lemma.Applications.CPUBound.tick"

    def __init__(self, session):
        cfg = session.binding.get("configuration")
        if cfg not in self.configurations:
            raise Core0Error("J requires its exact service configuration")
        self.configuration = cfg
        self.keys = ("server", "cli", "peer", "busy") + (("fault",) if cfg in self.development_configurations else ())
        super().__init__(session)
        if session.binding.get("managed_policy") != POLICY:
            raise Core0Error("J deployment policy differs")
        self.service_binding = require_service_binding(session.binding)
        self.remaining = 497
        self.grants, self.serials, self.endpoints, self.backings = {}, set(), {}, {}
        self.publications, self.actor_events, self.accepts, self.replies = [], [], [], []
        self.active_accept, self.faults, self.expiries, self.releases = {}, [], [], []
        self.foreign, self.peer_state, self.pending_expiry = {}, {}, None
        self.model = None
        self.cli, self.server, self.epoch = None, None, 0
        self.pending_rpc, self.rpc_pairs, self.actions = None, [], []
        self.discovery_handles, self.armed, self.intercept = {}, None, None
        self.intercept_time = None
        self.allowed_deaths = set()
        self.restart_witnesses, self.completed_actions = [], []
        self.actual_buffer_releases, self.new_allocations = [], {}
        self.pending_ack_action = None
        self.frame_samples = []
        self.diagnostic_frame_samples = []
        self.last_user_returns = {}
        self.busy_math = []
        unit = json.loads((session.image.parent / "users/busy/unit.json").read_text())
        symbols = [row["symbol"] for row in unit["functions"] if row["source"] == self.busy_callback]
        if len(symbols) != 1 or symbols[0] not in self.users["busy"]["function_ranges"]:
            raise Core0Error("ordinary CPU arithmetic callback lacks a genuine ELF range")
        self.busy_math_range = {symbols[0]: self.users["busy"]["function_ranges"][symbols[0]]}
        self.expect_create(1, 1); self.expect_create(2, 2); self.expect_create(3, 3); self.expect_create(0, 1)

    def role(self, name):
        rows = [id for id in self.live() if self.tasks[id]["key"] == name]
        if len(rows) != 1:
            raise Core0Error(f"J lacks one live full {name} descriptor")
        return rows[0]

    def actual_user(self, id, names):
        task = self._task(id)
        if self.current != id or task["key"] not in names:
            raise Core0Error("service output does not belong to the current separately linked User")
        return task

    def exit_pcs(self, user):
        return {user["exit_ecall_pc"], user["syscall_bridge"]["ecall_pc"]}

    def begin_action(self, action, *, retain=True):
        if not isinstance(action, dict) or type(action.get("index")) is not int or action["index"] < 7:
            raise Core0Error("service action lacks exact wire position")
        if retain:
            self.actions.append(action)
        kind = action.get("kind")
        if kind == "rpc":
            if self.pending_rpc is not None:
                raise Core0Error("overlapping CLI request")
            self.pending_rpc = action
        elif kind == "diagnostic":
            number, a, b, c, d = action["words"]
            if self.configuration not in self.development_configurations or self.pending_ack is not None:
                raise Core0Error("diagnostic authority outside development or overlapping acknowledgment")
            self.pending_ack = (number, a)
            self.pending_ack_action = action
            if number == 0x33:
                self.expect_create(4, b)
            elif number == 0x32:
                self.allowed_deaths.add(a)
            elif number == 0x40:
                self.allowed_deaths.add(self.role("server")); self.expect_create(0, self.epoch + 1)
            elif number == 0x41:
                if a != self.cli:
                    raise Core0Error("restart arm differs from full CLI identity")
                self.expect_create(0, self.epoch + 1)
        elif kind not in {"normal-diagnostic-discard", "malformed-envelope"}:
            raise Core0Error("unknown service input action")

    def observe(self, event):
        if len(event) != 5 or any(type(x) is not int or not 0 <= x <= MASK for x in event):
            raise Core0Error("service control is not five exact unsigned words")
        tag, a, b, c, d = event
        if tag in {0xb4, 0xf1, 0xf6} and self.unsettled_frame_samples():
            raise Core0Error("deferred diagnostic frame sample crossed an unrelated frame effect")
        if tag == 0xb4:
            if self.current is not None or a < 512 or b < 16 or a in self.endpoints or d:
                raise Core0Error("service Endpoint allocation identity/order differs")
            pending_pages = sum(19 + (self.images[self.keys[i]]["text_bytes"] + 4095)//4096
                                for i, _ in self.creation_queue)
            if c != self.remaining - pending_pages - 1:
                raise Core0Error("service queue allocation lacks exact actual one-frame accounting")
            self.endpoints[a] = b; self.remaining -= 1
        elif tag == 0xb1:
            rows = self.grants.setdefault(a, [])
            if self.current is not None or a in self.tasks or b < 16 or b % 16 != len(rows) or b >> 4 in self.serials:
                raise Core0Error("service boot grant lacks fresh slot/serial before activation")
            self.serials.add(b >> 4); rows.append(list(event))
        elif tag == 0xf1:
            roles = (((1, 2), (2, 8)), ((1, 3), (4, 1024)), ((1, 2), (4, 1024)), (), ((1, 2), (4, 1024)))
            if not 0 <= b < len(self.keys) or tuple((r[3], r[4]) for r in self.grants.get(a, [])) != roles[b]:
                raise Core0Error("service publication lacks least-rights role grants")
            if b == 0 and a not in self.endpoints:
                raise Core0Error("Server activation precedes its real queue")
            super().observe(event)
            if b == 1:
                if self.cli is not None: raise Core0Error("CLI replaced without a permitted input rebind")
                self.cli = a
        elif tag == 0x300:
            task = self._task(a)
            if (self.current is not None or task["key"] != "server" or b != self.endpoints.get(a)
                    or c != self.epoch + 1 or task["nonce"] != c or d != self.cli):
                raise Core0Error("service publication differs from activated Server/Endpoint/monotonic epoch/CLI")
            if self.server is not None and not self.tasks[self.server]["reaped"]:
                raise Core0Error("replacement published before old Server was fully reaped")
            self.server, self.epoch = a, c
            if self.model is None: self.model = BufferReference(c)
            else: self.model.restarted(c)
            self.foreign.clear(); self.publications.append(list(event))
        elif tag == 0xf2:
            task = self._task(a); user = self.users[task["key"]]
            if (self.current != a or b not in {1, 2, 3, 4, 5, 6} or c < self.irq
                    or b == 1 and c <= self.irq or not in_ranges(d, user["function_ranges"])):
                raise Core0Error("service return lacks current task/actual IRQ/linked PC")
            if b in {2, 3, 6} and d != user["syscall_bridge"]["ecall_pc"]:
                raise Core0Error("service yield/sleep/IPC block lacks its audited ECALL")
            if task["key"] == "busy" and b != 1:
                raise Core0Error("ordinary CPU loop cooperated or faulted")
            if b == 4:
                raise Core0Error("continuous service actor unexpectedly exited")
            if b == 5 and not any(r["task"] == a for r in self.faults) and not (self.intercept and self.intercept[1] == a):
                raise Core0Error("fault return lacks an actual fault or checked restart interception")
            self.current = None; self.irq = c; task["reasons"][b] += 1
            task["state"] = 4 if b == 3 else 5 if b == 6 else 6 if b == 5 else 2
            self.last_user_returns[a] = {"record": list(event), "index": len(self.session.events) - 1}
            if b == 1:
                task["preempt_irqs"].append(c)
                if task["key"] == "busy" and in_ranges(d, self.busy_math_range): self.busy_math.append(list(event))
        elif tag == 0xd4:
            if self.current is None: raise Core0Error("User fault without current actor")
            task = self.actual_user(self.current, {"fault"})
            if a != 15 or c != 0x10000 or d != 0x200000020 or not in_ranges(b, self.users["fault"]["function_ranges"]):
                raise Core0Error("Buffer fault is not actual U text store-pagefault15")
            disassembly = (self.session.image.parent / "users/fault/audit-user-disassembly.txt").read_text()
            import re
            if not re.search(rf"(?m)^\s*{b:x}:\s+sd\s", disassembly):
                raise Core0Error("Buffer fault PC is not an audited actual SD instruction")
            if not any(row[0] == 0x344 and row[1] == self.current for row in self.actor_events):
                raise Core0Error("contained fault preceded real buffer read/write witness")
            self.faults.append({"task": self.current, "record": list(event), "index": len(self.events)})
        elif tag == 0xf4:
            task = self._task(a)
            if self.current is not None or task["terminal"] is not None or c != (0 if task["key"] == "cli" else task["nonce"]):
                raise Core0Error("service termination lacks inactive identity/private data")
            if d == 15:
                if task["key"] != "fault" or b != 44 or not any(r["task"] == a for r in self.faults):
                    raise Core0Error("actual U fault was not contained with code44")
            elif d == 0:
                if b or a not in self.allowed_deaths:
                    raise Core0Error("trusted service termination lacks diagnostic authorization")
            else: raise Core0Error("unexpected service terminal cause")
            task["terminal"] = list(event); task["state"] = 6
        elif tag == 0xf6:
            task = self._task(a)
            queues = int(a in self.endpoints)
            pages = len(self.backings.get(a, set())) if task["key"] == "server" else 0
            if (self.current is not None or task["stats"] is None or b != self.remaining
                    or c != b + task["pages"] + queues + pages or d):
                raise Core0Error("service teardown leaked/double-freed owned task/queue/backing pages")
            self.remaining = c; task["reaped"] = True
            self.endpoints.pop(a, None); self.backings.pop(a, None)
        elif tag == 0x310:
            task = self.actual_user(a, {"cli"})
            if task["start"] or (b, c, d) != (1, self.grants[a][0][2], self.grants[a][1][2]):
                raise Core0Error("ordinary CLI startup differs from actual identity/grants")
            task["start"] = True
        elif tag == 0x320:
            task = self.actual_user(a, {"server"})
            if task["start"] or a != self.server or (b, c, d) != (self.epoch, self.grants[a][1][2], self.grants[a][0][2]):
                raise Core0Error("Server startup differs from its actual publication/local grants")
            task["start"] = True
        elif tag == 0x321:
            self.actual_user(a, {"server"})
            if a in self.active_accept or c not in self.live() or self.tasks[c]["key"] not in {"cli", "peer", "fault"} or d < 16:
                raise Core0Error("Server acceptance lacks one live authenticated Caller/Reply")
            key = (a, b, c)
            if any(tuple(row[1:4]) == key for row in self.accepts):
                raise Core0Error("duplicate full Server/request/Caller acceptance")
            if d >> 4 in self.serials: raise Core0Error("Server Reply alias reused a publication serial")
            if d % 16 != 2:
                raise Core0Error("Server Reply alias is outside its sole free slot2")
            self.serials.add(d >> 4); self.active_accept[a] = {"key": key, "record": list(event), "index": len(self.session.events) - 1, "response": None,
                                                            "actual_backing_count": len(self.backings.get(a, ()))}
            if c == self.cli:
                if not self.pending_rpc or self.pending_rpc["words"][0] > 6 or self.pending_rpc.get("server_key"):
                    raise Core0Error("Server accepted an unrequested or duplicate CLI operation")
                self.pending_rpc["server_key"] = list(key)
                self.pending_rpc["reference"] = deepcopy(self.model)
                self.pending_rpc["actual_backing_count"] = len(self.backings.get(a, ()))
            self.accepts.append(list(event))
        elif tag in {0x322, 0x324}:
            self.actual_user(a, {"server"})
            if b % 4096 or not 0x40000 <= b < 0x44000:
                raise Core0Error("Server backing is outside four real allocation VAs")
            pages = self.backings.setdefault(a, set())
            if tag == 0x322:
                if a not in self.active_accept or c not in ({0} | set(PUBLIC_ALLOCATION_ERRORS)):
                    raise Core0Error("backing allocation lacks accepted call/public actual status")
                self.active_accept[a]["allocation"] = list(event)
                if c == 0:
                    if d != b or b in pages: raise Core0Error("Server allocated an already live backing page")
                    pages.add(b); self.remaining -= 1
                    self.new_allocations[(a, b)] = {"caller": self.active_accept[a]["key"][2],
                                                    "request": self.active_accept[a]["key"][1],
                                                    "record": list(event), "claimed": False}
                elif d: raise Core0Error("failed actual page allocation returned an address")
            else:
                if c or d != b or b not in pages: raise Core0Error("Server release lacks a live real backing page")
                pages.remove(b); self.remaining += 1; self.releases.append(list(event))
                self.release_at_syscall_record(a, b)
            self.reconcile_frame_sample(event)
        elif tag == 0x323:
            self.actual_user(a, {"server"}); accepted = self.active_accept.get(a)
            if not accepted or accepted["key"][1] != b or accepted["response"] is not None or c not in (0, *range(200, 209)) or not 64 <= d <= 192:
                raise Core0Error("Server response lacks exact accepted request/public application result")
            accepted["response"] = list(event)
            self.settle_destroy_at_response(a, accepted)
        elif tag == 0x327:
            self.actual_user(a, {"server"}); accepted = self.active_accept.get(a)
            if not accepted or accepted["key"][1] != b or not accepted["response"] or c not in {0, 80} or d:
                raise Core0Error("Server Reply result lacks one accepted response/one-shot result")
            self.replies.append({**accepted, "result": list(event)})
            del self.active_accept[a]
        elif tag == 0x325:
            self.actual_user(a, {"server"})
            releases = [r for r in self.actual_buffer_releases if r["server"] == a
                        and r["va"] == 0x40000 + (b & 3) * 4096 and r["kind"] is None]
            if (self.pending_expiry is not None or len(releases) != 1 or not self.releases
                    or self.releases[-1][1:3] != [a, 0x40000 + (b & 3) * 4096]):
                raise Core0Error("lease expiry lacks its actual prior page release")
            if (b not in self.foreign or self.foreign[b]["owner"] != c) and not (
                    c == self.cli and self.model and b in self.model.buffers):
                raise Core0Error("lease expiry lacks its witnessed live full owner/handle")
            self.pending_expiry = list(event)

        elif tag == 0x326:
            self.actual_user(a, {"server"})
            previous = self.pending_expiry
            if not previous or a != previous[1] or b < previous[4] or c != previous[2] & 3 or d != previous[2] >> 2:
                raise Core0Error("lease expiry lacks actual deadline/time/slot/generation facts")
            releases = [r for r in self.actual_buffer_releases if r["server"] == a
                        and r["va"] == 0x40000 + c * 4096 and r["kind"] is None]
            if len(releases) != 1:
                raise Core0Error("lease expiry lost its unmatched actual page release")
            self._foreign_release(previous[2], previous[3], allow_cli=True)
            releases[0].update(kind="expiry", owner=previous[3], handle=previous[2], confirmed=True)
            accepted = self.active_accept.get(a)
            if accepted:
                if accepted["response"] is not None or accepted.get("allocation"):
                    raise Core0Error("lease scan followed the accepted application effect")
                accepted["actual_backing_count"] = len(self.backings.get(a, ()))
                if accepted["key"][2] == self.cli:
                    action = self.pending_rpc
                    if not action or action.get("server_key") != list(accepted["key"]):
                        raise Core0Error("accepted lease scan lost its exact CLI request")
                    action["reference"] = deepcopy(self.model)
                    action["actual_backing_count"] = accepted["actual_backing_count"]
            self.expiries.append({"release": previous, "time": list(event)}); self.pending_expiry = None
        elif 0x331 <= tag <= 0x33c or 0x340 <= tag <= 0x346:
            self.observe_actor(event)
        elif tag == 0x301:
            if self.configuration != "service-development" or self.current is not None or (a, b, c, d) != (self.server, self.cli, 0, 0) or self.armed:
                raise Core0Error("restart arm lacks idle full CLI/Server identities")
            if self.pending_ack != (0x41, self.cli):
                raise Core0Error("restart arm lacks its actual protected input")
            self.armed = list(event)
        elif tag == 0x302:
            if not self.armed or (a, b) != tuple(self.armed[1:3]) or self.current != a or c < 16 or d == 0:
                raise Core0Error("restart interception lacks actual matching delivered Reply/waiting transaction")
            if not self.pending_rpc or self.pending_rpc.get("expected_transport") != 96:
                raise Core0Error("interception has no actual outstanding CLI call")
            self.intercept = list(event); self.allowed_deaths.add(a)
        elif tag == 0x303:
            if not self.intercept or a != self.intercept[1] or self.current != a or not d < c or not in_ranges(b, self.users["server"]["function_ranges"]):
                raise Core0Error("restart interception lacks live actual User PC/unexpired deadline")
            if self.intercept_time is not None:
                raise Core0Error("duplicate restart deadline witness")
            self.intercept_time = list(event)
        elif tag == 0x304:
            if not self.intercept or not self.intercept_time or (a, b, c, d) != (self.intercept[1], self.intercept[3], 0, self.epoch) or not self.tasks[a]["reaped"]:
                raise Core0Error("pending restart lacks old reclamation and new successful epoch")
            self.restart_witnesses.append({"arm": self.armed, "accepted": self.intercept, "deadline": self.intercept_time, "replacement": list(event)})
            self.armed, self.intercept, self.intercept_time = None, None, None
        elif tag == 0xfc:
            task = self._task(a)
            if self.current is not None or b not in {2, 4, 5} or c != (0 if task["key"] == "cli" else task["nonce"]):
                raise Core0Error("service query lacks inactive full task/private initialization")
            self.queries.append(list(event))
        elif tag == 0xf7:
            super().observe(event)
            action = self.pending_ack_action
            if not action or b != action.get("expected_status", 0):
                raise Core0Error("diagnostic returned unexpected actual status")
            if a == 0x31:
                self.record_frame_sample(event, action)
            if a == 0x33 and b == 0 and (c not in self.tasks or self.tasks[c]["key"] != "fault" or self.tasks[c]["nonce"] != action["words"][2]):
                raise Core0Error("Fault creation acknowledgment lacks exact published full identity")
            if a == 0x40 and b == 0 and c != self.epoch:
                raise Core0Error("restart acknowledgment differs from actual published epoch")
            self.completed_actions.append(action)
            self.pending_ack = self.pending_ack_action = None
        else:
            super().observe(event)
            if tag == 0xf3:
                self.last_user_returns.pop(a, None)

    def unsettled_frame_samples(self):
        return [row for row in self.diagnostic_frame_samples
                if row["status"] == "deferred" and row["reconciliation"] is None]

    def record_frame_sample(self, event, action):
        """Keep the real sample; one pending syscall record may explain its lag."""
        tag, number, status, count, target = event
        row = {"record": list(event), "index": len(self.session.events) - 1,
               "input_index": action["index"], "record_accounting_at_query": self.remaining,
               "status": "exact", "acceptance": None, "server_return": None,
               "reconciliation": None, "settled": False}
        if count != self.remaining:
            accepted = self.active_accept.get(self.server)
            returned = self.last_user_returns.get(self.server)
            bridge = self.users["server"]["syscall_bridge"]["ecall_pc"]
            if (status != 0 or not 0 <= count <= 512 or not accepted
                    or accepted["response"] is not None or not returned
                    or returned["record"][2] != 1 or returned["record"][4] != bridge + 4
                    or self.tasks[self.server]["state"] != 2
                    or returned["index"] < accepted["index"]):
                raise Core0Error("diagnostic frame discrepancy lacks an unresolved full Server request at syscall return")
            row.update(status="deferred", acceptance=list(accepted["key"]),
                       server_return=deepcopy(returned))
        else:
            row["settled"] = (not self.active_accept and self.pending_expiry is None
                              and all(r["confirmed"] for r in self.actual_buffer_releases)
                              and all(r["claimed"] for r in self.new_allocations.values()))
        self.diagnostic_frame_samples.append(row)

    def reconcile_frame_sample(self, event):
        """The next matching actual backing effect must explain the exact sample."""
        pending = self.unsettled_frame_samples()
        if not pending:
            return
        tag, server, va, status, value = event
        accepted = self.active_accept.get(server)
        for row in pending:
            if (status != 0 or value != va or not accepted
                    or list(accepted["key"]) != row["acceptance"]
                    or accepted["response"] is not None or self.remaining != row["record"][3]):
                raise Core0Error("deferred diagnostic frame sample lacks its next exact same-request backing effect")
        for row in pending:
            row["reconciliation"] = {"record": list(event), "index": len(self.session.events) - 1,
                                     "resulting_remaining_frames": self.remaining,
                                     "acceptance": list(accepted["key"])}

    def require_settled_frame_samples(self):
        if self.unsettled_frame_samples():
            raise Core0Error("service contains unresolved diagnostic frame samples")
        for row in self.diagnostic_frame_samples:
            if row["status"] == "deferred" and not any(
                    later["status"] == "exact" and later["settled"]
                    and later["index"] > row["reconciliation"]["index"]
                    for later in self.diagnostic_frame_samples):
                raise Core0Error("reconciled diagnostic frame sample lacks a fresh exact settled query")

    def release_at_syscall_record(self, server, va):
        """Count the real page now; wait for expiry or Destroy evidence."""
        accepted = self.active_accept.get(server)
        self.actual_buffer_releases.append({"server": server, "owner": None, "handle": None,
                                            "va": va, "request": None, "kind": None,
                                            "acceptance": list(accepted["key"]) if accepted else None,
                                            "confirmed": False})

    def settle_destroy_at_response(self, server, accepted):
        releases = [r for r in self.actual_buffer_releases if r["server"] == server and r["kind"] is None]
        if not releases:
            return
        if (len(releases) != 1 or self.pending_expiry is not None
                or releases[0]["acceptance"] != list(accepted["key"])
                or accepted["response"] != [0x323, server, accepted["key"][1], 0, 64]):
            raise Core0Error("unmatched page release lacks its exact successful Destroy response")
        release = releases[0]
        va = release["va"]
        owner = accepted["key"][2]
        if owner == self.cli:
            action = self.pending_rpc
            if (not action or action["words"][0] != 6
                    or action.get("server_key") != list(accepted["key"])):
                raise Core0Error("CLI page release has no actual destroy request")
            handle = action["words"][2]
            op, epoch, requested_handle, offset, length = action["words"]
            request = Request(op, epoch or action["epoch"], requested_handle, offset, length,
                              bytes.fromhex(action["data_hex"]))
            reference = action.get("reference")
            if (not isinstance(reference, BufferReference) or reference.expected_status(request) != 0
                    or handle not in self.model.buffers or va != 0x40000 + (handle & 3)*4096):
                raise Core0Error("CLI destroy released another buffer slot")
            self.model.released(handle)
        else:
            handles = [h for h, row in self.foreign.items() if row["owner"] == owner
                       and va == 0x40000 + (h & 3)*4096]
            if len(handles) != 1:
                raise Core0Error("actor destroy lacks one live authenticated owner/slot")
            handle = handles[0]
            self._foreign_release(handle, owner)
        release.update(kind="destroy", owner=owner, handle=handle,
                       request=accepted["key"][1], confirmed=owner == self.cli)

    def require_settled_releases(self):
        if self.pending_expiry is not None or any(not r["confirmed"] for r in self.actual_buffer_releases):
            raise Core0Error("service contains unmatched or unconfirmed actual page releases")
        self.require_settled_frame_samples()

    def service_quiescent(self, peer):
        return (self.tasks[self.server]["state"] == 5 and self.tasks[peer]["state"] == 4
                and not self.active_accept and self.pending_expiry is None
                and all(r["confirmed"] for r in self.actual_buffer_releases)
                and all(row["claimed"] for (owner, _), row in self.new_allocations.items()
                        if owner == self.server))

    def settle_reference_failure(self):
        """Observe background completion after a received byte-error response."""
        before, inputs = len(self.session.events), len(self.actions)
        try:
            failure = self.session.report.get("failed_rpc")
            if (self.session.report.get("service_failure_category") != "buffer-byte-reference"
                    or not self.pending_rpc or not isinstance(failure, dict)
                    or failure.get("input") != self.public_action(self.pending_rpc)):
                raise Core0Error("background settlement lacks the actual failed CLI byte response")
            # That response has completed the input even though its bytes fail.
            # Keep the failed pair and original exception; send no new input.
            self.pending_rpc = None
            self.until(lambda: self.service_quiescent(self.role("peer")))
            if len(self.actions) != inputs:
                raise Core0Error("failed-response settlement added an external input")
            self.session.report["service_failure_settlement"] = {
                "status": "PASS", "events_before": before, "events_after": len(self.session.events),
                "input_actions": inputs, "quiescent": True}
        except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
            self.session.report["service_failure_settlement"] = {
                "status": "FAIL", "events_before": before, "events_after": len(self.session.events),
                "input_actions": inputs, "error_type": type(error).__name__, "error": str(error)}

    def _foreign_release(self, handle, owner, *, allow_cli=False):
        if handle in self.foreign and self.foreign[handle]["owner"] == owner:
            del self.foreign[handle]
            if self.model and handle in self.model.foreign: self.model.released(handle)
        elif allow_cli and owner == self.cli and self.model and handle in self.model.buffers:
            self.model.released(handle)
        else: raise Core0Error("buffer release lacks a witnessed live full owner/handle")

    def observe_actor(self, event):
        tag, a, b, c, d = event
        peer = tag < 0x340
        task = self.actual_user(a, {"peer"} if peer else {"fault"})
        state = self.peer_state.setdefault(a, {"round": 0, "persistent": 0, "temporary": 0})
        if tag in {0x331, 0x340}:
            if b != self.epoch or d != task["nonce"] or c < 16: raise Core0Error("ordinary actor discovery differs from current epoch/local capability")
            key = (a, b)
            old = self.discovery_handles.get(key)
            if old is not None and old != c: raise Core0Error("exact discovery reuse consumed a new local capability")
            if c % 16 != 2:
                raise Core0Error("actor discovery is outside its exact first free local slot")
            if old is None:
                if c >> 4 in self.serials:
                    raise Core0Error("actor discovery reused another published capability serial")
                self.serials.add(c >> 4)
            self.discovery_handles[key] = c; task["start"] = True
        elif tag in {0x332, 0x335, 0x341}:
            capacity = 128 if tag == 0x332 else 64
            if c != capacity or d != self.epoch or not task["start"] or b in self.foreign:
                raise Core0Error("ordinary actor creation lacks its actual capacity/epoch/fresh handle")
            va = 0x40000 + (b & 3) * 4096
            if va not in self.backings.get(self.server, set()): raise Core0Error("actor handle lacks real Server backing")
            allocation = self.new_allocations.get((self.server, va))
            if not allocation or allocation["caller"] != a or allocation["claimed"]:
                raise Core0Error("actor creation lacks its actual authenticated new allocation")
            if tag == 0x341:
                request = allocation["request"]
                accepted = self.accepted_result(self.server, request, a)
                phase = state.get("fault_phase", 0)
                if (state["temporary"] or state.get("fault_create") is not None
                        or request != state.get("next_create", 1) or not 1 <= request <= 255 or request % 2 != 1
                        or phase not in {0, 2}
                        or not accepted or accepted["response"] != [0x323, self.server, request, 0, 64]):
                    raise Core0Error("Fault creation lacks its exact bounded successful Create response")
                if phase == 2:
                    old = state.get("released_fault_handle")
                    if (not state.get("seen_global_denial", False) or old is None
                            or b & 3 != old & 3 or b >> 2 <= old >> 2):
                        raise Core0Error("Fault replacement lacks the released slot's fresh post-denial generation")
                state["fault_create"] = {"request": request, "handle": b, "phase": phase}
                state["fault_phase"] = 1 if phase == 0 else 3
                state["next_create"] = request + 2
            allocation["claimed"] = True
            self.model.foreign_created(b); self.foreign[b] = {"owner": a, "epoch": d, "capacity": c}
            state["persistent" if tag == 0x332 else "temporary"] = b
        elif tag in {0x333, 0x334, 0x336, 0x342}:
            length = 32 if tag in {0x333, 0x334} else 16
            if b not in self.foreign or self.foreign[b]["owner"] != a or c != digest(pattern(task["nonce"], a, length)):
                raise Core0Error("actual independent actor binary bytes differ from host pattern")
            if tag in {0x333, 0x334} and b != state["persistent"] or tag == 0x336 and b != state["temporary"]:
                raise Core0Error("Peer binary witness uses another live handle")
            if tag == 0x334:
                if d != state["round"]: raise Core0Error("Peer read/round reordered")
            elif d != length: raise Core0Error("ordinary actor binary count differs")
            if tag == 0x342:
                creation = state.get("fault_create")
                if (not creation or creation["phase"] != 2 or creation["handle"] != b
                        or state.get("fault_phase") != 3 or state.get("released_fault_handle") is None
                        or not state.get("seen_global_denial", False)):
                    raise Core0Error("Fault binary witness preceded its own actual global denial")
                for request, payload_bytes in ((257, 64), (258, 80)):
                    accepted = self.accepted_result(self.server, request, a)
                    if not accepted or accepted["response"] != [0x323, self.server, request, 0, payload_bytes]:
                        raise Core0Error("Fault binary witness lacks its actual final Write/Read replies")
        elif tag == 0x337:
            if b != state["temporary"] or c != self.epoch or d != state["round"]:
                raise Core0Error("Peer temporary destroy identity/epoch/round differs")
            releases = [r for r in self.actual_buffer_releases if r["server"] == self.server
                        and r["kind"] == "destroy" and r["owner"] == a and r["handle"] == b
                        and not r["confirmed"]]
            if len(releases) != 1:
                raise Core0Error("Peer destroy lacks its actual page-release witness")
            accepted = self.accepted_result(self.server, releases[0]["request"], a)
            if not accepted or accepted["response"] != [0x323, self.server, releases[0]["request"], 0, 64]:
                raise Core0Error("Peer destroy lacks its exact authenticated successful response")
            releases[0]["confirmed"] = True; state["temporary"] = 0
        elif tag in {0x338, 0x343, 0x346}:
            if c != 204 or peer and d != self.epoch: raise Core0Error("actual global quota denial differs")
            accepted = self.accepted_result(self.server, b, a)
            if not accepted or not accepted["response"] or accepted["response"][3] != 204:
                raise Core0Error("quota witness lacks actual authenticated Server denial")
            if accepted.get("actual_backing_count") != 4:
                raise Core0Error("global denial lacks four actual live backing pages")
            if not peer:
                if (b != state.get("next_create", 1) or not 1 <= b <= 255 or b % 2 != 1
                        or accepted["response"] != [0x323, self.server, b, 204, 64]):
                    raise Core0Error("Fault denial lacks its exact next bounded Create request")
                phase = state.get("fault_phase", 0)
                creation = state.get("fault_create")
                if tag == 0x343:
                    if (phase != 1 or not creation or creation["phase"] != 0
                            or d != state["temporary"] or d != creation["handle"]
                            or d not in self.foreign or self.foreign[d]["owner"] != a):
                        raise Core0Error("Fault quota witness lacks its retained pre-denial buffer")
                    state["seen_global_denial"] = True
                    state["denial_request"] = b
                    state["fault_phase"] = 4
                elif (phase not in {0, 2} or d != phase or state["temporary"]
                        or creation is not None):
                    raise Core0Error("Fault retry denial differs from its acquiring/replacement phase")
                state["next_create"] = b + 2
        elif tag == 0x339:
            if b not in {80, 83, 96, 200, 201} or not c <= self.epoch or d != state["persistent"]:
                raise Core0Error("Peer reconnect lacks actual old tuple/declared transport or stale error")
            state["old"] = (c, d); state["persistent"] = 0; state["temporary"] = 0
        elif tag == 0x33a:
            old = state.get("old")
            if not old or b != old[1] or d != self.epoch or c != (200 if old[0] < d else 201): raise Core0Error("Peer old tuple was not rejected after real loss")
        elif tag == 0x33b:
            if not b <= c or b == 0 or d != state["round"]: raise Core0Error("Peer sleep returned before actual deadline")
        elif tag == 0x33c:
            if b != state["round"] + 1 or c != state["persistent"] or d != self.epoch: raise Core0Error("Peer round lacks actual retained buffer")
            state["round"] = b
        elif tag == 0x344:
            if (b not in self.foreign or self.foreign[b]["owner"] != a or c != self.epoch or d != task["nonce"]
                    or not state.get("seen_global_denial", False)
                    or not any(row[0] == 0x342 and row[1:3] == [a, b] for row in self.actor_events)):
                raise Core0Error("faulting actor did not verify its own actual buffer")
        elif tag == 0x345:
            creation = state.get("fault_create")
            if (not creation or creation["phase"] != 0 or creation["handle"] != b
                    or state["temporary"] != b or c != self.epoch or d != state.get("denial_request", 0) + 1
                    or not 2 <= d <= 256 or d % 2 != 0 or not state.get("seen_global_denial", False)
                    or state.get("fault_phase") != 4):
                raise Core0Error("Fault destroy identity/epoch/request preceded its own held-buffer denial")
            accepted = self.accepted_result(self.server, d, a)
            if not accepted or accepted["response"] != [0x323, self.server, d, 0, 64]:
                raise Core0Error("Fault retry destroy lacks its actual successful full-caller response")
            releases = [r for r in self.actual_buffer_releases if r["server"] == self.server
                        and r["kind"] == "destroy" and r["owner"] == a and r["handle"] == b and r["request"] == d
                        and r["va"] == 0x40000 + (b & 3)*4096 and not r["confirmed"]]
            if len(releases) != 1 or b in self.foreign:
                raise Core0Error("Fault retry destroy lacks its exact unconfirmed real page release")
            releases[0]["confirmed"] = True
            state["temporary"] = 0
            state["fault_create"] = None
            state["released_fault_handle"] = b
            state["fault_phase"] = 2
            state["next_create"] = d + 1
        else: raise Core0Error("unknown service actor record")
        self.actor_events.append(list(event))

    def accepted_result(self, server, request, caller):
        live = self.active_accept.get(server)
        if live and live["key"] == (server, request, caller):
            return live
        return next((r for r in reversed(self.replies) if r["key"] == (server, request, caller)), None)

    def client(self, response):
        if self.current != self.cli or self.pending_rpc is None:
            raise Core0Error("client frame has no current CLI/external command")
        action = self.pending_rpc
        words = action["words"]
        op, requested_epoch, handle, offset, length = words
        if response["operation"] != op: raise Core0Error("CLI response operation differs from actual input")
        if op <= 6:
            resolved_epoch = requested_epoch or action["epoch"]
            expected_transport = action.get("expected_transport", 0)
            if expected_transport:
                if (response["transport_status"] != expected_transport or response["epoch"] != resolved_epoch
                        or response["application_status"] or any(response[k] for k in ("handle", "length", "count", "detail")) or response["data_hex"]):
                    raise Core0Error("pending restart transport completion differs")
            else:
                request = Request(op, resolved_epoch, handle, offset, length, bytes.fromhex(action["data_hex"]))
                alloc_failure = response["application_status"] == 208
                if alloc_failure:
                    allocations = [r for r in self.replies if r["key"][2] == self.cli and r.get("allocation")]
                    live = self.active_accept.get(self.server)
                    if live and live["key"][2] == self.cli and live.get("allocation"): allocations.append(live)
                    if not allocations or allocations[-1]["allocation"][3] != response["detail"]:
                        raise Core0Error("allocation208 lacks actual guest allocator failure")
                server_key = action.get("server_key")
                accepted = self.accepted_result(*server_key) if server_key else None
                if (not accepted or not accepted["response"] or accepted["response"][3:] !=
                        [response["application_status"], 64 + len(bytes.fromhex(response["data_hex"]))]):
                    raise Core0Error("CLI output lacks its preceding actual accepted Server response")
                reference = action.get("reference")
                if not isinstance(reference, BufferReference):
                    raise Core0Error("CLI response lacks authenticated pre-operation reference")
                try:
                    # Another caller may have returned from create before its
                    # own Console creation witness. The Server's actual page
                    # inventory accounts for those opaque, unclaimed handles.
                    actual_global_full = (request.operation == 1 and reference.expected_status(request) == 0
                                          and action["actual_backing_count"] == 4)
                    if actual_global_full:
                        if (response["operation"], response["epoch"], response["handle"], response["length"],
                            response["count"], response["detail"], response["application_status"],
                            response["transport_status"], response["data_hex"]) != (1, reference.epoch, 0, 0, 0, 0, 204, 0, ""):
                            raise Core0Error("actual four-page inventory did not reject global creation")
                    else:
                        reference.accept(request, response, allocation_failure=alloc_failure)
                except Core0Error as error:
                    failure = {"input": self.public_action(action), "response": response,
                               "error": str(error), "index": len(self.session.events)}
                    expected_bytes = (reference.buffers.get(request.handle, {}).get("data", b"")
                                      [request.offset:request.offset+request.length])
                    byte_mismatch = (request.operation == 3 and request.length == len(bytes.fromhex(response["data_hex"]))
                                     and expected_bytes != bytes.fromhex(response["data_hex"]))
                    self.session.report.update(service_failure_category=("buffer-byte-reference" if byte_mismatch else "buffer-response-reference"),
                                               failed_rpc=failure)
                    raise Core0Error(f"independent Buffer reference mismatch: {error}") from error
                if request.operation == 1 and not response["application_status"]:
                    allocation = self.new_allocations.get((server_key[0], 0x40000+(response["handle"]&3)*4096))
                    if not allocation or allocation["caller"] != self.cli or allocation["claimed"]:
                        raise Core0Error("CLI creation lacks its actual fresh authenticated page allocation")
                    allocation["claimed"] = True
                self.model.buffers = reference.buffers
                for slot, generation in reference.generations.items():
                    self.model.generations[slot] = max(generation, self.model.generations.get(slot, 0))
                self.model.operations += 1
        elif response["application_status"] or response["transport_status"] or response["data_hex"] or response["length"] or response["count"]:
            raise Core0Error("ordinary informational response exposes service data/error")
        elif op == 7 and (response["epoch"], response["handle"], response["detail"]) != (0, 0, 1): raise Core0Error("help/version differs")
        elif op == 8 and (response["epoch"], response["handle"], response["detail"]) != (0, 0, len(self.live())): raise Core0Error("active managed count differs from full observed identities")
        elif op == 9:
            if (response["epoch"], response["handle"]) != (0, 0) or not 0 <= response["detail"] <= 512:
                raise Core0Error("actual frame query is outside the authoritative allocator capacity")
            self.frame_samples.append({"value": response["detail"], "record_accounting_at_output": self.remaining,
                                       "index": len(self.session.events),
                                       "ordering": "allocation effect may precede its User record; exact inactive teardown is checked separately"})
        elif op == 10:
            key = (self.cli, self.epoch)
            old = self.discovery_handles.get(key)
            if response["epoch"] != self.epoch or response["handle"] < 16 or response["detail"] or old is not None and old != response["handle"]:
                raise Core0Error("repeat CLI discovery changed exact local capability")
            if response["handle"] % 16 != 2:
                raise Core0Error("CLI discovery is outside its exact first free local slot")
            if old is None:
                if response["handle"] >> 4 in self.serials:
                    raise Core0Error("CLI discovery reused another published capability serial")
                self.serials.add(response["handle"] >> 4)
            self.discovery_handles[key] = response["handle"]
        self.rpc_pairs.append({"input": self.public_action(action), "response": response, "index": len(self.session.events)})
        self.completed_actions.append(self.public_action(action))
        self.pending_rpc = None

    @staticmethod
    def public_action(action):
        return {key: value for key, value in action.items() if key != "reference"}

    def read(self):
        if len(self.session.events) >= MAX_EVENTS: raise Core0Error("service finite event budget exhausted")
        event = self.session.event()
        if event["kind"] == "kernel":
            self.observe(tuple(event["value"])); self.events.append(event["value"])
        else: self.client(event["value"])
        self.session.report["service_progress"] = self.snapshot()
        return event

    def snapshot(self):
        return {"protocol": "buffer-service-J-v1", "configuration": self.configuration,
                "actions": [self.public_action(action) for action in self.actions], "rpc_pairs": self.rpc_pairs,
                "tasks": {str(id): {**t, "reasons": {str(reason): count for reason, count in t["reasons"].items()}} for id, t in self.tasks.items()},
                "publications": self.publications, "boot_grants": {str(id): rows for id, rows in self.grants.items()},
                "actor_events": self.actor_events, "server_acceptance": self.accepts,
                "server_replies": [{**row, "key": list(row["key"])} for row in self.replies], "actual_expiries": self.expiries,
                "actual_backings": {str(k): sorted(v) for k, v in self.backings.items()},
                "faults": self.faults, "restarts": self.restart_witnesses, "diagnostic_acknowledgments": self.acks,
                "queries": self.queries, "buffer_releases": self.actual_buffer_releases, "actual_frame_samples": self.frame_samples,
                "diagnostic_frame_samples": self.diagnostic_frame_samples, "remaining_frames": self.remaining, "machine_interrupts": self.irq,
                "busy_math_preemptions": self.busy_math, "busy_unit": self.busy_unit,
                "compiled_service_evidence": self.service_binding}

    def rpc(self, operation, epoch=None, handle=0, offset=0, length=0, data=b"", *, expected_transport=0):
        selected_epoch = self.epoch if epoch is None else epoch
        words = [operation, selected_epoch, handle, offset, length]
        action = {"kind": "rpc", "index": len(self.session.events), "words": words,
                  "data_hex": data.hex(), "epoch": self.epoch, "expected_transport": expected_transport}
        self.begin_action(action)
        self.session.send_envelope(command(*words, data=data))
        count = len(self.rpc_pairs)
        self.until(lambda: len(self.rpc_pairs) == count + 1)
        return self.rpc_pairs[-1]["response"]

    def diagnostic(self, number, a=0, b=0, c=0, d=0, *, expected_status=0):
        words = [number, a, b, c, d]
        self.begin_action({"kind": "diagnostic", "index": len(self.session.events), "words": words, "expected_status": expected_status})
        self.session.send(struct.pack("<5Q", *words), diagnostic=True)
        before = len(self.acks)
        self.until(lambda: len(self.acks) == before + 1)
        result = self.acks[-1]; self.pending_ack = None
        if result[2] != expected_status: raise Core0Error("diagnostic returned unexpected actual status")
        if number == 0x31:
            sample = self.diagnostic_frame_samples[-1]
            if sample["status"] == "deferred":
                # This waits under the existing finite session deadline/event
                # budget. The old ACK remains the sample; it is never rewritten.
                self.until(lambda: sample["reconciliation"] is not None)
        return result

    def ignored_diagnostic(self):
        if self.configuration != "service-normal":
            raise Core0Error("normal diagnostic-drop witness requires normal service")
        words = [0x40, 0, 0, 0, 0]
        action = {"kind": "normal-diagnostic-discard", "index": len(self.session.events), "words": words}
        self.begin_action(action)
        self.session.send(struct.pack("<5Q", *words), diagnostic=True)
        before = self.epoch
        reply = self.rpc(10, epoch=0)
        if reply["epoch"] != before or self.epoch != before:
            raise Core0Error("normal input admitted trusted development restart")

    def malformed_header(self):
        # Invalid header has no declared opaque body. Only the header scanner
        # may resume at the following complete valid ordinary envelope.
        raw = b"LMI1" + struct.pack("<BBH", 1, 1, 0)
        action = {"kind": "malformed-envelope", "index": len(self.session.events), "raw_hex": raw.hex()}
        self.begin_action(action)
        transport._write_all(self.session.process, raw, deadline=self.session.deadline,
                             capture=self.session.capture, context="sending invalid bounded input header")
        self.rpc(7, epoch=0)


def input_bytes(action):
    kind = action.get("kind")
    if kind == "rpc":
        if (not isinstance(action.get("words"), list) or len(action["words"]) != 5
                or any(type(w) is not int or not 0 <= w <= MASK for w in action["words"])
                or not isinstance(action.get("data_hex"), str)
                or type(action.get("epoch")) is not int or not 0 < action["epoch"] <= MASK
                or action.get("expected_transport", 0) not in (0, 96)):
            raise Core0Error("retained CLI action shape differs")
        return command(*action["words"], data=bytes.fromhex(action["data_hex"]))
    if kind in {"diagnostic", "normal-diagnostic-discard"}:
        words = action.get("words")
        if not isinstance(words, list) or len(words) != 5 or any(type(w) is not int or not 0 <= w <= MASK for w in words):
            raise Core0Error("retained diagnostic action shape differs")
        if kind == "normal-diagnostic-discard" and words != [0x40, 0, 0, 0, 0]:
            raise Core0Error("normal discarded input differs from its declared complete frame")
        return input_envelope(struct.pack("<5Q", *words), diagnostic=True)
    if kind == "malformed-envelope":
        raw = bytes.fromhex(action.get("raw_hex", ""))
        if raw != b"LMI1" + struct.pack("<BBH", 1, 1, 0):
            raise Core0Error("retained malformed-header fixture changed")
        return raw
    raise Core0Error("unknown retained service action")


def startup(events):
    if len(events) < 7 or any(e["kind"] != "kernel" for e in events[:7]):
        raise Core0Error("J lacks seven actual startup controls")
    records = [tuple(e["value"]) for e in events[:7]]
    supervisor = validate_positive_records(records[:4])
    root, ready, managed = records[4:]
    if (root[0] != 0xd3 or root[2:] != (satp(root[1]), 500, 0)
            or ready != (0xf0, 1, 8, 512, 10000) or managed != (0xb0, 1, 16, 16, 497)):
        raise Core0Error("J startup stable root/table/objects/input-owned-frame baseline differs")
    return {"supervisor": supervisor, "kernel_root": list(root), "ready": list(ready), "managed": list(managed)}


def qualification(trace):
    """Derive coverage from checked actual inputs/results, never a PASS label."""
    trace.require_settled_releases()
    rows = trace.rpc_pairs
    if len(rows) < 300 or trace.pending_rpc is not None or trace.pending_ack is not None or trace.creation_queue or trace.pending_expiry is not None:
        raise Core0Error("service corpus incomplete or contains unfinished input/construction")
    responses = [r["response"] for r in rows]
    statuses = {r["application_status"] for r in responses}
    if not {0, 200, 201, 202, 203, 205, 206} <= statuses:
        raise Core0Error("ordinary status/epoch/foreign/stale/quota/bounds/malformed cases are missing")
    if not any(r["input"]["words"][0] == 4 and r["input"]["words"][1] != r["input"]["epoch"]
               and r["input"]["words"][3] == 1 and r["response"]["application_status"] == 206 for r in rows):
        raise Core0Error("malformed-field precedence over mismatched epoch is unobserved")
    if not {7, 8, 9, 10} <= {r["operation"] for r in responses}:
        raise Core0Error("practical help/instances/frames/discovery commands are missing")
    binary = [(r["input"], r["response"]) for r in rows if r["input"]["words"][0] == 4
              and r["input"]["words"][4] == 128 and r["response"]["application_status"] == 0]
    if not binary or any(not bytes.fromhex(a["data_hex"]).endswith(b"\xff") for a, _ in binary):
        raise Core0Error("distinguishing actual 128-byte append with final FF is missing")
    payloads = [bytes.fromhex(r["input"]["data_hex"]) for r in rows
                if r["input"]["words"][0] in {2, 4} and r["response"]["application_status"] == 0]
    if not any(all(marker in data for marker in (b"\x00\xff", b"LMI1", b"LMO1", b"K1", "λ".encode())) for data in payloads):
        raise Core0Error("binary/UTF8/embedded framing payload was not actually round-tripped")
    if len(trace.busy_math) < 3 or not any(row[0] == 0x334 for row in trace.actor_events):
        raise Core0Error("ordinary CPU arithmetic preemption and concurrent Peer progress are missing")
    if not any(row[0] == 0x337 for row in trace.actor_events):
        raise Core0Error("ordinary Peer creation/destroy cycle is missing")
    if not any(a["kind"] == "malformed-envelope" for a in trace.actions):
        raise Core0Error("actual malformed input recovery witness is missing")
    if trace.configuration == "service-normal":
        if (not any(a["kind"] == "normal-diagnostic-discard" for a in trace.actions)
                or len(trace.publications) != 1 or trace.epoch != 1 or trace.acks or trace.faults
                or len(trace.live()) != 4):
            raise Core0Error("normal service admitted diagnostic authority or lost an ordinary task")
    else:
        dead = {r["task"] for r in trace.faults}
        if (not dead or not any(row[0] == 0x343 for row in trace.actor_events)
                or not any(e["release"][3] in dead for e in trace.expiries)
                or not trace.restart_witnesses
                or not any(r["response"]["transport_status"] == 96 for r in rows)
                or not any(row[0] == 0x33a and row[3] == 200 for row in trace.actor_events)
                or trace.live() or trace.current is not None or trace.remaining != 497):
            raise Core0Error("development global-denial/fault/lease/pending-restart/reconnect/final-reclaim observations are missing")
        counters = [r[4] for r in trace.queries if trace.tasks[r[1]]["key"] == "busy"]
        if len(counters) < 2 or not 0 < counters[0] < counters[-1]:
            raise Core0Error("ordinary CPU actual private counter failed to grow")
    return {"ordinary_commands": len(rows), "application_statuses": sorted(statuses),
            "actual_binary_append_cases": len(binary), "actual_math_preemptions": len(trace.busy_math),
            "actual_global_denials": sum(r[0] in {0x338, 0x343} for r in trace.actor_events),
            "actual_faults": len(trace.faults), "actual_lease_expiries": len(trace.expiries),
            "actual_pending_restarts": len(trace.restart_witnesses), "final_remaining_frames": trace.remaining}


def check(session):
    initial = [session.event() for _ in range(7)]
    initial_facts = startup(initial)
    trace = ServiceTrace(session)
    try:
        trace.until(lambda: len(trace.tasks) == 4 and len(trace.publications) == 1
                    and all(t["start"] for t in trace.tasks.values() if t["key"] != "busy")
                    and any(r[0] == 0x334 for r in trace.actor_events))
        trace.rpc(7, epoch=0); trace.rpc(8, epoch=0); trace.rpc(9, epoch=0); trace.rpc(10, epoch=0)
        trace.malformed_header()
        # Runtime binary is deliberately opaque to both framing layers.
        prefix = b"\x00\xffLMI1LMO1K1" + "λ".encode()
        payload = prefix + secrets.token_bytes(128 - len(prefix))
        appended = secrets.token_bytes(127) + b"\xff"
        first = trace.rpc(1, length=256)["handle"]
        trace.rpc(2, handle=first, length=128, data=payload)
        trace.rpc(4, handle=first, length=128, data=appended)
        trace.rpc(3, handle=first, length=128)
        trace.rpc(3, handle=first, offset=128, length=128)
        trace.rpc(4, handle=first, length=1, data=b"\xff")
        trace.rpc(3, handle=first, offset=128, length=128)
        trace.rpc(3, handle=first, offset=MASK, length=1)
        trace.rpc(1, length=4097)
        trace.rpc(1, handle=4, length=64)
        trace.rpc(5, handle=first, offset=1)
        trace.rpc(4, handle=first, offset=1, length=1, data=b"\x00")
        trace.rpc(4, epoch=MASK, handle=first, offset=1, length=1, data=b"\x00")
        second = trace.rpc(1, length=64)["handle"]
        trace.rpc(1, length=64)
        peer = trace.role("peer")
        trace.until(lambda: trace.peer_state[peer]["persistent"] in trace.foreign)
        foreign = trace.peer_state[peer]["persistent"]
        trace.rpc(5, handle=foreign)
        trace.rpc(5, epoch=MASK, handle=first)
        if trace.configuration == "service-development":
            # The third caller is launched only after real full storage and
            # an actual temporary write, not after a guessed sleep interval.
            trace.until(lambda: len(trace.backings.get(trace.server, ())) == 4
                        and any(r[0] == 0x336 and r[2] == trace.peer_state[peer]["temporary"] for r in trace.actor_events))
            nonce = secrets.randbits(64) or 1
            ack = trace.diagnostic(0x33, 4, nonce)
            fault = ack[3]
            trace.until(lambda: trace.tasks[fault]["reaped"])
            if not any(r[0] == 0x343 and r[1] == fault for r in trace.actor_events):
                raise Core0Error("third caller missed actual full-storage denial")
            live_handle = next((h for h, r in trace.foreign.items() if r["owner"] == fault), None)
            if live_handle is None or 0x40000+(live_handle&3)*4096 not in trace.backings.get(trace.server, ()):
                raise Core0Error("dead caller's real backing was prematurely reclaimed by Kernel task teardown")
            # Renew live owners while the dead caller's declared ten-second
            # lease expires through ordinary Server time and release syscalls.
            while not any(e["release"][3] == fault for e in trace.expiries):
                trace.rpc(5, handle=first)
                trace.rpc(3, handle=first, offset=128, length=128)
                trace.rpc(5, handle=second)
                before = trace.now
                trace.until(lambda: trace.now >= before + 1000000)
            if first not in trace.model.buffers or second not in trace.model.buffers:
                raise Core0Error("dead-caller expiry also expired a renewed live CLI buffer")
        trace.rpc(6, handle=second)
        trace.rpc(5, handle=second)
        replacement = trace.rpc(1, length=64)["handle"]
        if replacement == second:
            raise Core0Error("destroy/recreate reused a stale exact Buffer handle")
        trace.rpc(6, handle=replacement)
        if trace.configuration == "service-normal":
            trace.ignored_diagnostic()
        else:
            busy = trace.role("busy")
            trace.diagnostic(0x31, busy)
            before = len(trace.busy_math)
            trace.until(lambda: len(trace.busy_math) >= before + 2)
            trace.diagnostic(0x31, busy)
            old_epoch = trace.epoch
            old_first = first
            trace.diagnostic(0x41, trace.cli)
            trace.rpc(5, handle=first, expected_transport=96)
            trace.until(lambda: trace.restart_witnesses and trace.epoch == old_epoch + 1)
            trace.rpc(5, epoch=old_epoch, handle=old_first)
            trace.until(lambda: any(r[0] == 0x33a and r[4] == trace.epoch for r in trace.actor_events))
            first = trace.rpc(1, length=256)["handle"]
            empty = trace.rpc(3, handle=first, length=0)
            if empty["length"] != 0:
                raise Core0Error("new service epoch retained old buffer data")
            trace.rpc(2, handle=first, length=128, data=payload)
            trace.rpc(3, handle=first, length=128)
        # There is no 256-command application limit. Discovery reuses the
        # same attenuated local capability throughout this ordinary stream.
        while len(trace.rpc_pairs) < 305:
            op = (8, 9, 10, 5)[len(trace.rpc_pairs) % 4]
            trace.rpc(op, epoch=0 if op in {8, 9, 10} else None, handle=first if op == 5 else 0)
        trace.rpc(3, handle=first, length=128)
        trace.until(lambda: len(trace.busy_math) >= 3 and any(r[0] == 0x337 for r in trace.actor_events))
        # Both images finish at observed receive/sleep states with no pending
        # buffer effect. Every subsequent cleanup frame is still replayed.
        trace.until(lambda: trace.service_quiescent(peer))
        if trace.configuration == "service-development":
            for id in sorted(trace.live(), key=lambda value: trace.tasks[value]["key"] != "server"):
                trace.diagnostic(0x32, id)
                trace.until(lambda id=id: trace.tasks[id]["reaped"])
            trace.diagnostic(0x31, 0)
        checked = qualification(trace)
        result = {**trace.snapshot(), "startup": initial_facts, "qualification": checked,
                  "lifetime": "continuous ordinary User service; explicit host stop after observed protocol"}
        session.report["service_progress"] = result
        return result
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        session.report.update(service_error_type=type(error).__name__, service_error=str(error))
        if isinstance(error, Core0Error) and session.report.get("service_failure_category") == "buffer-byte-reference":
            trace.settle_reference_failure()
        session.report["service_progress"] = trace.snapshot()
        raise


def replay_aftercleanup(session):
    return validate_replay(session.root, session.image, session.report, session.output_dir)


def _replay(root, image, report, directory, observed, *, expected_byte_failure=False):
    raw = (directory / "received.bin").read_bytes()
    events, tail = decode_uart(raw)
    if (tail or events != report.get("wire_events") or report.get("complete_raw_coverage") is not True
            or len(events) > MAX_EVENTS or report.get("wire_format") != "kernel-buffer-uart-v1"):
        raise Core0Error("retained service frames have missing, changed or unbounded complete raw coverage")
    if not isinstance(observed, dict) or observed.get("protocol") != "buffer-service-J-v1":
        raise Core0Error("retained service observation protocol differs")
    actions = observed.get("actions")
    if not isinstance(actions, list) or not actions:
        raise Core0Error("service replay lacks actual external inputs")
    settlement = report.get("service_failure_settlement") if expected_byte_failure else None
    if expected_byte_failure and (not isinstance(settlement, dict) or set(settlement) != {
            "status", "events_before", "events_after", "input_actions", "quiescent"}
            or settlement.get("status") != "PASS" or settlement.get("quiescent") is not True
            or any(type(settlement.get(k)) is not int for k in ("events_before", "events_after", "input_actions"))
            or not 7 < settlement["events_before"] <= settlement["events_after"] <= len(events)
            or settlement["input_actions"] != len(actions)):
        raise Core0Error("failed byte observation lacks completed bounded background settlement")
    before = -1
    for action in actions:
        if (not isinstance(action, dict) or type(action.get("index")) is not int
                or not 7 <= action["index"] < len(events) or action["index"] < before):
            raise Core0Error("service action positions are unordered or outside actual wire")
        before = action["index"]
    if b"".join(input_bytes(a) for a in actions) != (directory / "sent.bin").read_bytes():
        raise Core0Error("actual retained input bytes differ from ordered service actions")
    binding = json.loads((image.parent / "audit.json").read_text())
    offline = SimpleNamespace(root=root, image=image, binding=binding, report={}, events=events[:7], records=[])
    facts = startup(events)
    trace = ServiceTrace(offline)
    cursor, reproduced = 0, None
    input_keys = {"kind", "index", "words", "data_hex", "epoch", "expected_transport", "expected_status", "raw_hex"}
    for index, event in enumerate(events[7:], 7):
        while cursor < len(actions) and actions[cursor]["index"] == index:
            if reproduced is not None:
                raise Core0Error("failed byte observation has additional unvalidated host commands")
            trace.begin_action({key: deepcopy(value) for key, value in actions[cursor].items() if key in input_keys})
            cursor += 1
        offline.events.append(event)
        if event["kind"] == "kernel":
            trace.observe(tuple(event["value"])); trace.events.append(event["value"])
        else:
            try:
                trace.client(event["value"])
            except Core0Error:
                if not expected_byte_failure or reproduced is not None:
                    raise
                reproduced = _reference_byte_counterexample(trace, event["value"], report)
                if index + 1 != settlement["events_before"]:
                    raise Core0Error("background settlement does not start at the actual failed response")
                # This already observed output completed the external request.
                # No further client frame is accepted without a new input;
                # background frames drained at cleanup still undergo all normal
                # current-task, authority, page and actor semantic checks.
                trace.pending_rpc = None
        if expected_byte_failure and index + 1 == settlement["events_after"]:
            if reproduced is None or not trace.service_quiescent(trace.role("peer")):
                raise Core0Error("background settlement lacks its actual receive/sleep boundary")
    if cursor != len(actions):
        raise Core0Error("service replay missed retained external actions")
    if expected_byte_failure and (reproduced is None or trace.pending_rpc or trace.pending_ack or trace.creation_queue):
        raise Core0Error("failed session did not reproduce exactly the declared byte counterexample")
    if expected_byte_failure:
        trace.require_settled_releases()
    return trace, facts, events, reproduced


def validate_replay(root, image, report, directory):
    """Re-execute full positive semantics, including frames drained at cleanup."""
    trace, facts, events, _ = _replay(root, image, report, directory, report.get("observed"))
    return {**trace.snapshot(), "startup": facts, "qualification": qualification(trace),
            "complete_semantic_replay": True, "replayed_wire_events": len(events)}


def _reference_byte_counterexample(trace, response, report):
    action = trace.pending_rpc
    reference = action.get("reference") if action else None
    if (report.get("status") != "FAIL" or report.get("service_failure_category") != "buffer-byte-reference"
            or trace.session.report.get("service_failure_category") != "buffer-byte-reference"
            or trace.configuration != "service-normal" or not isinstance(reference, BufferReference)
            or action["words"][0] != 3 or action["words"][4] != 128 or action.get("expected_transport")):
        raise Core0Error("failure is not the sole ordinary successful 128-byte read counterexample")
    _, requested_epoch, handle, offset, count = action["words"]
    request = Request(3, requested_epoch or action["epoch"], handle, offset, count)
    if reference.expected_status(request):
        raise Core0Error("failed read lacks ordinary live ownership and valid bounds")
    row = reference.buffers[handle]
    expected = row["data"][offset:offset+count]
    actual = bytes.fromhex(response["data_hex"])
    if ((response["operation"], response["epoch"], response["handle"], response["length"], response["count"],
         response["detail"], response["application_status"], response["transport_status"]) !=
            (3, reference.epoch, handle, len(row["data"]), count, row["capacity"], 0, 0)
            or len(expected) != 128 or not expected.endswith(b"\xff")
            or actual != expected[:-1]+b"\x00"):
        raise Core0Error("failure is not the distinguishing final-byte append/read mismatch")
    appends = [r for r in trace.rpc_pairs if r["input"]["words"][0] == 4 and r["input"]["words"][2] == handle
               and r["input"]["words"][4] == 128 and bytes.fromhex(r["input"]["data_hex"]).endswith(b"\xff")
               and (r["response"]["application_status"], r["response"]["transport_status"], r["response"]["count"]) == (0, 0, 128)]
    if not appends or appends[-1]["response"]["length"] - 128 != offset:
        raise Core0Error("counterexample lacks actual successful preceding distinguishing append")
    failure = trace.session.report.get("failed_rpc")
    if failure != report.get("failed_rpc"):
        raise Core0Error("reproduced actual request/response/error differs from retained inner failure")
    return {"failed_rpc": failure, "expected_data_hex": expected.hex(), "actual_data_hex": actual.hex(),
            "actual_append": appends[-1]}


def validate_reference_failure(root, image, report, directory):
    """Validate an expected negative without relabeling the inner failed run.

    Cleanup/source/mutation/control binding is the outer controller's separate
    responsibility. This function proves only complete raw/input replay and the
    same checker's exact successful append/read byte counterexample.
    """
    trace, facts, events, reproduced = _replay(root, image, report, directory,
                                              report.get("service_progress"), expected_byte_failure=True)
    return {"protocol": "buffer-service-J-byte-failure-v1", **reproduced,
            "complete_semantic_replay": True, "replayed_wire_events": len(events),
            "startup": facts, "snapshot": trace.snapshot()}


def runner_inputs(root):
    return {name: sha256(root / name) for name in RUNNERS}


def validate_timeout(timeout):
    if (type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0 < timeout <= 300):
        raise Core0Error("Buffer observation requires a finite timeout greater than zero and at most 300 seconds")
    return timeout


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    session = None
    try:
        validate_timeout(args.timeout)
        root = repo_root()
        runners = runner_inputs(root)
        with BufferSession(root=root, image=args.image, output_dir=args.output_dir,
                           timeout=args.timeout, clean=args.clean) as session:
            session.report.update(service_runner_inputs=runners, acceptance_checker_sha256=sha256(Path(__file__)))
            observed = check(session)
            session.finish(observed)
        replayed = replay_aftercleanup(session)
        after = runner_inputs(root)
        if after != runners:
            raise Core0Error("service observation/checker/reference changed through complete cleanup replay")
        session.report.update(observed=replayed, service_runner_inputs_after=after)
        temporary = session.output_dir / "result.json.tmp"
        write_json(temporary, session.report); temporary.replace(session.output_dir / "result.json")
        print(f"PASS: {replayed['qualification']['ordinary_commands']} actual ordinary Buffer commands; complete raw semantics replayed and QEMU reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError, KeyError) as error:
        if session is not None and session.output_dir.exists():
            was_pass = session.report.get("status") == "PASS"
            session.report.update(status="FAIL", error=str(error), service_error_type=type(error).__name__)
            if was_pass:
                session.report["service_failure_category"] = "post-cleanup-semantic-replay"
            temporary = session.output_dir / "result.json.tmp"
            write_json(temporary, session.report); temporary.replace(session.output_dir / "result.json")
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
