#!/usr/bin/env python3
"""Observe checked caller-local capabilities through actual managed U syscalls."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import secrets
import struct

from core0_common import Core0Error, repo_root, sha256, write_json
from run_kernel import Session, transport
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import satp
from check_kernel_tasks import Trace, in_ranges

MAX_SERIAL = (1 << 60) - 1
BASIC = {1:80, 2:80, 3:81, 4:72, 5:0, 6:72, 7:72, 8:16, 9:16,
         10:0, 11:0, 12:72, 13:0, 14:80, 15:0, 16:80, 17:0,
         18:0, 19:72, 20:0, 21:0, 22:0, 23:0, 24:0, 25:72, 26:72, 27:0, 28:72,
         120:89, 121:89, 200:0, 201:0, 202:0, 203:90, 210:89, 211:0, 212:80,
         213:0, 214:0, 215:0, 216:80, 217:0, 218:0,219:0,220:0,221:0}
CASE_ORDER = [*range(1,29), *range(100,114),120,121,*range(150,163),
              200,201,202,203,150,151,152,*range(210,222)]
PEER_ORDER = [*range(1,15),20,21,22,23,30,31]


class CapabilityTrace(Trace):
    keys = ("capabilities", "peer", "busy", "tamper")
    configuration = "capabilities-development"
    arithmetic_required = False

    def __init__(self, session):
        super().__init__(session)
        if session.binding.get("managed_policy") != "lemma-capabilities-v1":
            raise Core0Error("H requires the exact source-selected managed policy")
        self.remaining = 498
        self.grants, self.aliases, self.seed, self.queue = {}, {}, None, None
        self.endpoint_frames = 0
        self.cases, self.peer_cases, self.snapshots = [], [], {}
        self.handles, self.endpoint_cleanup, self.exhaustion = {}, 0, []
        self.tamper_faults, self.ready_for_serial, self.serial_advance = [], None, None
        self.corpus_serials, self.endpoint_releases, self.owner_death_cleanup = set(), set(), None

    def publication(self, handle):
        serial = handle >> 4
        if handle < 16 or not 0 < serial <= MAX_SERIAL or serial in self.corpus_serials:
            raise Core0Error("successful publication lacks a fresh legal global serial")
        self.corpus_serials.add(serial)

    def release_endpoint(self, case):
        # A peer can observe revocation before the owner's later User log.
        # Apply the one proven release at whichever causal witness comes first.
        if case not in self.endpoint_releases:
            if self.endpoint_frames <= 0:
                raise Core0Error("endpoint release exceeded observed owned queue pages")
            self.endpoint_releases.add(case)
            self.endpoint_frames -= 1
            self.remaining += 1

    def exit_pcs(self, user):
        return {user["exit_ecall_pc"], user["syscall_bridge"]["ecall_pc"]}

    def observe(self, event):
        tag, a, b, c, d = event
        if tag == 0xb5:
            if (self.seed is not None or self.tasks or (a, b, c, d) != (3, 1, MAX_SERIAL, 0)):
                raise Core0Error("object retirement fixture lacks its actual free-slot generation seed")
            self.seed = list(event)
        elif tag == 0xb4:
            expected = 497 - sum(19 + (self.images[key]["text_bytes"] + 4095) // 4096 for key in self.keys[:3])
            if (self.queue is not None or self.seed is None or self.tasks or a < 512
                    or b != (MAX_SERIAL << 4) | self.seed[1] or c != expected or d):
                raise Core0Error("initial shared endpoint lacks the measured one-frame queue allocation")
            self.queue = list(event)
            self.endpoint_frames, self.remaining = 1, 497
        elif tag == 0xb1:
            if (a in self.tasks or b < 16 or b >> 4 > MAX_SERIAL or c not in {1, 2, 3}
                    or any(b == row[2] for rows in self.grants.values() for row in rows)
                    or b % 16 != len(self.grants.get(a, []))):
                raise Core0Error("initial grant lacks fresh caller-local serial/slot before publication")
            self.grants.setdefault(a, []).append(list(event))
            if self.ready_for_serial is None:
                self.publication(b)
        elif tag == 0xb2:
            base = b - 2560
            if (a in self.tasks or a in self.aliases or d != 0x31a00 or base % 4096
                    or base != 0x82000000 + (a % 512) * 4096
                    or c != ((base >> 12) << 10) | 0xc7):
                raise Core0Error("tamper witness does not alias the actual protected descriptor cap header")
            self.aliases[a] = list(event)
        elif tag == 0xf1:
            roles = ((1,34),(3,928),(2,124)) if b == 0 else ((1,34),(2,36)) if b == 1 else () if b == 2 else ((1,2),)
            rows = self.grants.get(a, [])
            if (tuple((r[3],r[4]) for r in rows) != roles or self.queue is None
                    or b == 3 and a not in self.aliases):
                raise Core0Error("task publication preceded its exact reviewed boot grants or protected alias")
            super().observe(event)
        elif tag == 0x100:
            task = self._task(a)
            rows = self.grants[a]
            if (self.current != a or task["image"] != 0 or task["start"]
                    or (b,c,d) != (task["nonce"],rows[0][2],rows[1][2])):
                raise Core0Error("Tester identity/runtime nonce/caller-local grants differ")
            task["start"] = True
        elif tag == 0x110:
            task = self._task(a)
            expected = BASIC.get(b, 0 if 100 <= b <= 112 or 150 <= b <= 162 else 89 if b == 113 else None)
            if self.current != a or task["image"] != 0 or not task["start"] or expected is None or c != expected:
                raise Core0Error("actual managed Tester syscall reply differs from the complete authority corpus")
            if len(self.cases)>=len(CASE_ORDER) or b!=CASE_ORDER[len(self.cases)]:
                raise Core0Error("actual Tester syscall cases are omitted, duplicated or reordered")
            if c and d:
                raise Core0Error("failed capability operation returned unexpected authority/result")
            if b == 11 and d != 1 | (2 << 8) or b == 213 and d != 1 or b in {217,221} and d != 2:
                raise Core0Error("attenuated info, retired-slot count or transfer reference count differs")
            grant = b in {10,15,18,21,22,200,201,202,214,215,219,220} or 100 <= b <= 112
            if grant:
                self.publication(d)
                self.handles[b] = d
                if b in {215,220}:
                    field = "received_transfer" if b == 215 else "owner_death_alias"
                    for peer in self.tasks.values():
                        if field in peer and peer[field][2] != d:
                            raise Core0Error("peer alias differs from the actual scoped transfer reply")
            elif b not in {11,213,217,221} and d:
                raise Core0Error("successful non-publication returned an unexpected value")
            if b == 15 and (d == self.handles[10] or d % 16 != self.handles[10] % 16):
                raise Core0Error("same caller-local slot reuse lacks a new serial and stale denial")
            if b in {200,201,202,214,219}:
                self.endpoint_frames += 1
                self.remaining -= 1
            elif b in {211,218}:
                self.release_endpoint(b)
            elif self.endpoint_cleanup and 150 <= b <= 152:
                self.endpoint_frames -= 1
                self.remaining += 1
                self.endpoint_cleanup -= 1
            self.cases.append(list(event))
        elif tag == 0x120:
            task = self._task(a)
            expected = 0 if 1 <= b <= 14 or b in {20,23} else 72 if b in {21,22} else 80 if b in {30,31} else None
            if self.current != a or task["image"] != 1 or expected is None or c != expected or c and d:
                raise Core0Error("actual separate Peer authority checks differ")
            if len(self.peer_cases)>=len(PEER_ORDER) or b!=PEER_ORDER[len(self.peer_cases)]:
                raise Core0Error("actual Peer syscall cases are omitted, duplicated or reordered")
            if 1 <= b <= 14:
                self.publication(d)
            elif d:
                raise Core0Error("Peer non-publication returned an unexpected value")
            if b == 30:
                self.release_endpoint(218)
            elif b == 31 and self.owner_death_cleanup is None:
                raise Core0Error("peer stale denial preceded the observed owner-death queue cleanup")
            self.peer_cases.append(list(event))
        elif tag == 0x122:
            task = self._task(a)
            if (self.current != a or task["image"] != 1 or task["start"]
                    or (b,c,d) != (task["nonce"],self.grants[a][1][2],14)
                    or len([r for r in self.peer_cases if r[1] == a]) != 14):
                raise Core0Error("Peer table-full state lacks fourteen actual duplicate replies")
            task["start"] = True
        elif tag in {0x124,0x125}:
            task = self._task(a)
            case = 215 if tag == 0x124 else 220
            field = "received_transfer" if tag == 0x124 else "owner_death_alias"
            if (self.current != a or task["image"] != 1 or field in task or b < 16
                    or b >> 4 > MAX_SERIAL or c != 15 or d
                    or case in self.handles and b != self.handles[case]):
                raise Core0Error("received transfer does not resolve only in the intended peer's local table")
            task[field] = list(event)
        elif tag == 0x12f:
            task = self._task(a)
            if (self.current != a or task["image"] != 1 or "owner_death_alias" not in task
                    or self.owner_death_cleanup is None
                    or (b,c,d) != (task["nonce"],0,0)):
                raise Core0Error("Peer completion lacks successful restricted transfer and actual revocation")
            task["complete"] = True
        elif tag == 0x140:
            task = self._task(a)
            objects, frames = d >> 32, d & 0xffffffff
            refs = {1:29,2:29,3:2,4:2,5:2,6:2,7:15,8:15}
            if (self.current != a or task["image"] != 0 or b not in range(1,9) or b in self.snapshots
                    or objects != 3 + self.endpoint_frames or frames != self.remaining or c != refs[b]):
                raise Core0Error("failed-publication snapshot disagrees with actual object/page accounting")
            self.snapshots[b] = list(event)
            if b in {2,4,6,8} and self.snapshots[b-1][3:] != list(event)[3:]:
                raise Core0Error("failed publication changed source refs, object count or physical pages")
            if b == 4:
                self.endpoint_cleanup = 3
        elif tag == 0x160:
            task = self._task(a)
            if self.current != a or task["image"] != 3 or task["start"] or (b,c,d) != (task["nonce"],80,0):
                raise Core0Error("Tamper did not reject the old/foreign handle through actual checked lookup")
            task["start"] = True
        elif tag == 0xd4:
            task = self._task(self.current)
            if (task["image"] != 3 or not task["start"] or "fault" in task
                    or a != 15 or c != 0x31a00 or d != 0x200000020
                    or not in_ranges(b,self.users["tamper"]["function_ranges"])):
                raise Core0Error("cap-table store lacks an actual contained U store-page fault")
            payload = (self.session.image.parent / "users/tamper/text.bin").read_bytes()
            word = int.from_bytes(payload[b-0x10000:b-0x10000+4],"little")
            if word & 0x7f != 0x23 or word >> 12 & 7 != 3:
                raise Core0Error("cap-table fault PC is not an actual audited 64-bit store instruction")
            task["fault"] = list(event)
            self.tamper_faults.append({"task":self.current,"record":list(event),"instruction":word})
        elif tag == 0xf2 and b == 5:
            task = self._task(a)
            if self.current != a or "fault" not in task or c < self.irq or d != task["fault"][2] or task["reasons"][5]:
                raise Core0Error("tamper return lacks the current captured architectural fault")
            self.current,self.irq = None,c
            task["reasons"][5] += 1
            task["state"] = 6
        elif tag == 0xf4 and d == 15:
            task = self._task(a)
            if self.current is not None or task["terminal"] is not None or task["reasons"][5] != 1 or (b,c) != (44,task["nonce"]):
                raise Core0Error("tamper fault did not terminate on the restored kernel stack")
            task["terminal"],task["complete"],task["state"] = list(event),True,6
        elif tag == 0x1fe:
            task = self._task(a)
            if (self.current != a or task["image"] != 0 or self.ready_for_serial
                    or (b,c,d) != (task["nonce"],0,0) or self.corpus_serials != set(range(1,45))):
                raise Core0Error("serial phase began without the checked Tester lifecycle")
            self.ready_for_serial = list(event)
        elif tag == 0xb3:
            if (self.current is not None or self.serial_advance is not None or self.pending_ack != (0x36,0)
                    or not 0 < a <= MAX_SERIAL or (b,c,d) != (MAX_SERIAL,MAX_SERIAL,0)):
                raise Core0Error("serial exhaustion lacks a monotonic trusted one-publication advance")
            self.serial_advance = list(event)
        elif tag == 0x1fd:
            task = self._task(a)
            if (self.current != a or task["image"] != 0 or self.serial_advance is None or self.exhaustion
                    or b >> 4 != MAX_SERIAL or c != MAX_SERIAL or d):
                raise Core0Error("last legal capability serial was absent or wrapped")
            self.exhaustion.append(list(event))
        elif tag == 0x1ff:
            task = self._task(a)
            if (self.current != a or task["image"] != 0 or not self.exhaustion
                    or (b,c,d) != (task["nonce"],91,self.exhaustion[0][2])):
                raise Core0Error("actual exhausted publication did not reject without reusing the last handle")
            self.exhaustion.append(list(event))
            task["complete"] = True
        elif tag == 0xf6 and self._task(a)["image"] == 0:
            task = self._task(a)
            peer_aliases = [peer.get("owner_death_alias") for peer in self.tasks.values() if peer["image"] == 1]
            if (self.current is not None or task["stats"] is None or d or b != self.remaining
                    or c != b + task["pages"] + 1 or self.endpoint_frames != 1
                    or self.owner_death_cleanup is not None or len(peer_aliases) != 1
                    or peer_aliases[0] is None or peer_aliases[0][2] != self.handles.get(220)):
                raise Core0Error("owner death failed to sweep the surviving peer alias and reclaim exactly one queue")
            self.remaining,task["reaped"] = c,True
            self.endpoint_frames = 0
            self.owner_death_cleanup = list(event)
        else:
            super().observe(event)


def check(session):
    startup = validate_positive_records([session.record() for _ in range(4)])
    kernel,ready,managed = session.record(),session.record(),session.record()
    if (kernel[0] != 0xd3 or kernel[2:] != (satp(kernel[1]),500,0)
            or ready != (0xf0,1,8,512,10000) or managed != (0xb0,1,16,16,498)):
        raise Core0Error("managed startup does not bind actual owned table/object baseline")
    trace = CapabilityTrace(session)
    nonces = [secrets.randbits(64) for _ in range(3)]
    if len(set(nonces)) != 3 or any(n in {0,(1<<64)-1} for n in nonces):
        raise Core0Error("runtime nonce generation failed its distinct nonzero corpus")
    for image,nonce in enumerate(nonces): trace.expect_create(image,nonce)
    transport._write_all(session.process,struct.pack("<5Q",0x30,*nonces,0),
                         deadline=session.deadline,capture=session.capture,context="launching managed capability tasks")
    trace.until(lambda: len(trace.tasks)==3)
    initial = list(trace.tasks); tester,peer,busy = initial
    trace.until(lambda: trace.ready_for_serial is not None and "owner_death_alias" in trace.tasks[peer]
                and len(trace.tasks[busy]["preempt_irqs"])>=3)
    _,first = trace.command(0x31,busy)
    if len(first)!=1 or not first[0][4]: raise Core0Error("Busy lacked actual progress during authority tests")
    tampered=[]; argument=0
    for _ in range(2):
        trace.expect_create(3,argument)
        ack,_=trace.command(0x33,3,argument)
        id=ack[3]; tampered.append(id)
        trace.until(lambda: trace.tasks[id]["reaped"])
        trace.command(0x31,id,status=74,value=0)
        trace.command(0x32,id,0x55,status=74,value=0)
        argument=trace.grants[id][0][2]
    _,second=trace.command(0x31,busy)
    if len(second)!=1 or second[0][4]<=first[0][4]: raise Core0Error("unrelated Busy stopped during protected-table faults")
    trace.command(0x36,1,status=16,value=0)
    trace.command(0x36,0,value=MAX_SERIAL)
    trace.until(lambda: trace.tasks[tester]["reaped"])
    trace.until(lambda: trace.tasks[peer]["reaped"])
    trace.command(0x31,tester,status=74,value=0)
    trace.command(0x32,busy,0x55,value=busy)
    trace.until(lambda: trace.tasks[busy]["reaped"])
    trace.command(0x31,0,value=498)
    counts=Counter(row[2] for row in trace.cases)
    expected=Counter({number:1 for number in BASIC})
    expected.update({number:1 for number in range(100,114)})
    expected.update({number:2 if number<=152 else 1 for number in range(150,163)})
    if (counts!=expected or Counter(row[2] for row in trace.peer_cases)!=Counter(PEER_ORDER)
            or set(trace.snapshots)!=set(range(1,9)) or len(trace.tamper_faults)!=2
            or len(trace.exhaustion)!=2 or trace.endpoint_frames or trace.endpoint_cleanup
            or trace.owner_death_cleanup is None or trace.corpus_serials!=set(range(1,45))
            or trace.live() or trace.current is not None or trace.creation_queue or trace.remaining!=498):
        raise Core0Error("H missing actual syscall cases or left authority, queue pages or live tasks")
    return {"protocol":"capabilities-H-v1","startup":startup,"kernel_root":list(kernel),
            "ready":list(ready),"managed_ready":list(managed),"runtime_nonces":nonces,
            "tasks":{str(id):{**task,"reasons":dict(task["reasons"])} for id,task in trace.tasks.items()},
            "boot_grants":trace.grants,"protected_capability_aliases":trace.aliases,
            "object_generation_seed":trace.seed,"actual_shared_queue_allocation":trace.queue,
            "tester_syscall_replies":trace.cases,"peer_syscall_replies":trace.peer_cases,
            "unchanged_rollback_snapshots":trace.snapshots,"actual_cap_table_faults":trace.tamper_faults,
            "exact_successful_publication_serials":sorted(trace.corpus_serials),
            "owner_death_queue_and_remote_alias_cleanup":trace.owner_death_cleanup,
            "monotonic_serial_advance":trace.serial_advance,"last_grant_and_actual_exhaustion":trace.exhaustion,
            "busy_counter_queries":[first[0],second[0]],"actual_machine_interrupts":trace.irq,
            "final_remaining_frames":trace.remaining,"guest_lifetime":"one continuous VM"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True); parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--timeout",type=float,default=120); parser.add_argument("--clean",action="store_true")
    args=parser.parse_args()
    try:
        root=repo_root()
        paths=("scripts/check_kernel_capabilities.py","scripts/check_kernel_tasks.py","scripts/check_kernel_supervisor.py",
               "scripts/check_kernel_user.py","scripts/check_kernel.py","scripts/run_kernel.py",
               "scripts/run_device_session.py","scripts/run_monitor_session.py")
        runners={path:sha256(root/path) for path in paths}
        with Session(root=root,image=args.image,output_dir=args.output_dir,timeout=args.timeout,clean=args.clean) as session:
            session.report.update(runner_inputs=runners,acceptance_checker_sha256=sha256(Path(__file__)))
            observed=check(session)
            if {path:sha256(root/path) for path in paths}!=runners: raise Core0Error("H runner changed while guest was live")
            session.finish(observed)
        try:
            from check_kernel import validate_session
            validate_session(session.output_dir/"result.json",session.image)
        except (Core0Error,OSError,ValueError,TypeError,KeyError) as error:
            session.report.update(status="FAIL",error=str(error),failure_category="post-cleanup-wire-evidence")
            write_json(session.output_dir/"result.json.tmp",session.report)
            (session.output_dir/"result.json.tmp").replace(session.output_dir/"result.json"); raise
        print("PASS: real caller-local grants, rights, transfer/revoke, hardware isolation and bounded exhaustion observed")
        return 0
    except (Core0Error,OSError,ValueError,TypeError,KeyError,IndexError) as error:
        print(f"FAIL: {error}"); return 1


if __name__=="__main__": raise SystemExit(main())
