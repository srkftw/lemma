#!/usr/bin/env python3
"""Observe bounded copied IPC through one real preemptive multi-user guest."""
from __future__ import annotations
import argparse
from collections import Counter
from pathlib import Path
import secrets
import struct

from core0_common import Core0Error, repo_root, sha256, write_json
from run_kernel import Session, transport
from check_kernel_supervisor import validate_positive_records
from check_kernel_user import satp, MASK
from check_kernel_tasks import Trace, in_ranges

A_ORDER = [*range(1, 7), *range(10, 16), *range(17, 24), *range(30, 40), *range(40, 62), 70]
# 60..61 are transfer/notification; delivered echo uses53,54 and ready55..59.
B_ORDER = [*range(1, 8), *range(80, 84)]
A_ERRORS = {1:80,2:81,3:72,4:16,5:71,6:12,14:92,15:92,17:71,19:98,23:12,
            31:99,33:94,34:97,35:12,37:93,38:12,47:93,52:94,56:71,57:98,58:100}
B_ERRORS = {82:72,83:83}
A_VALUE = {18:64,20:256,21:88,22:88,41:256,43:88,45:72,49:88,54:88,59:88}
B_VALUE = {1:72,3:256,5:88,7:64,80:72}
A_TRANSACTIONS = {30,36,40,42,44,46,48,50,53,55}
B_TRANSACTIONS = {2,4,6}
A_SERIALS = {30:9,36:10,40:12,42:13,44:14,46:15,48:16,50:17,53:18,55:19}
B_SERIALS = {2:2,4:3,6:4}


def digest(nonce: int, length: int, xor=0):
    value = 1469598103934665603
    for i in range(length):
        byte = ((nonce >> ((i % 8) * 8)) ^ (i * 37)) & 255
        value = ((value * 1099511628211) & MASK) ^ (byte ^ xor)
    return value


def require_ipc_binding(binding):
    graph=binding.get("managed_ipc")
    storage={"descriptor_metadata":3648,"descriptor_metadata_bytes":128,"packet":3776,
             "packet_bytes":256,"payload":3840,"payload_bytes":192,"queue_slots":4,
             "queue_header_bytes":128,"queue_slot_bytes":320,"reply_capacity":8}
    required_edges={("Lemma.Kernel.Task.completeBlocked","Lemma.Kernel.IPC.completeWait"),
                    ("Lemma.Kernel.Capability.retireReply","Lemma.Kernel.Objects.destroyReply"),
                    ("Lemma.Kernel.Scheduler.call","Lemma.Kernel.Task.block")}
    if not isinstance(graph,dict) or graph.get("managed_policy")!="lemma-ipc-v1" or graph.get("storage")!=storage:
        raise Core0Error("I requires actual source/CFG IPC storage audit, beyond its manifest policy")
    edges=graph.get("source_call_edges")
    publications=graph.get("state_publications")
    bridge=graph.get("blocked_bridge")
    if (not isinstance(edges,list) or not edges or any(not isinstance(row,list) or len(row)!=2 or any(type(value)is not str for value in row) for row in edges)
            or not required_edges.issubset({tuple(row) for row in edges})
            or not isinstance(publications,list) or not publications
            or not all(isinstance(row,dict) for row in publications)
            or not {"Lemma.Kernel.Task.block","Lemma.Kernel.Task.completeBlocked","Lemma.Kernel.IPCStorage.complete"}.issubset({row.get("source") for row in publications})
            or not isinstance(bridge,dict) or any(bridge.get(key)!=value for key,value in {"internal_status":254,"pc_advances":1,"reason":6}.items())
            or not graph.get("loaded_field_gates") or not graph.get("checked_cfg_gates")):
        raise Core0Error("I artifact lacks checked authority, block/wakeup generation and single-PC-advance evidence")
    return graph


class IPCTrace(Trace):
    keys = ("server", "clienta", "clientb", "busy", "fault")
    configuration = "ipc-development"
    arithmetic_required = False

    def __init__(self, session):
        super().__init__(session)
        if session.binding.get("managed_policy") != "lemma-ipc-v1":
            raise Core0Error("I requires its exact compiled IPC boot policy")
        self.ipc_binding=require_ipc_binding(session.binding)
        self.remaining = 498
        self.grants, self.endpoints, self.endpoint_releases = {}, [], set()
        self.cases, self.packets, self.payloads = {}, [], []
        self.snapshots, self.refs, self.server_accepts = {}, {}, {}
        self.server_replies, self.server_duplicates, self.server_invalid = {}, {}, {}
        self.faults, self.fault_calls, self.peer_death = [], {}, None
        self.ready, self.serials = {}, set()
        self.block_records = []

    def role(self, key):
        matches = [id for id, t in self.tasks.items() if t["key"] == key and not t["reaped"]]
        if len(matches) != 1:
            raise Core0Error(f"live role {key} lacks one full descriptor identity")
        return matches[0]

    def release_endpoint(self, role):
        if role not in self.endpoint_releases:
            self.endpoint_releases.add(role)
            self.remaining += 1

    def exit_pcs(self, user):
        return {user["exit_ecall_pc"], user["syscall_bridge"]["ecall_pc"]}

    def actual_user(self, id, keys):
        task = self._task(id)
        if self.current != id or task["key"] not in keys:
            raise Core0Error("IPC observation does not belong to the current separately linked User")
        return task

    def observe(self, event):
        tag,a,b,c,d = event
        if tag == 0xb4:
            pages = sum(19 + (self.images[key]["text_bytes"] + 4095)//4096 for key in self.keys[:4])
            expected = 498 - pages - len(self.endpoints) - 1
            if self.tasks or len(self.endpoints)>=3 or a<512 or b<16 or c!=expected or d:
                raise Core0Error("IPC queue lacks actual one-frame allocation before task publication")
            self.endpoints.append(list(event)); self.remaining -= 1
        elif tag == 0xb1:
            rows = self.grants.setdefault(a, [])
            serial = b >> 4
            if a in self.tasks or b<16 or b%16 != len(rows) or serial in self.serials:
                raise Core0Error("IPC grant lacks a fresh local slot/serial before task publication")
            self.serials.add(serial); rows.append(list(event))
        elif tag == 0xf1:
            roles = (((1,34),(2,8)), ((1,34),(2,20),(2,124),(3,928),(2,4)),
                     ((1,34),(2,20),(2,8)), (), ((1,34),(2,20)))
            if len(self.endpoints)!=3 or tuple((r[3],r[4]) for r in self.grants.get(a,[])) != roles[b]:
                raise Core0Error("IPC task publication lacks its exact prior boot-role authority")
            super().observe(event)
        elif tag == 0x220:
            task=self.actual_user(a,{"server"})
            if task["start"] or (b,c,d)!=(task["nonce"],self.grants[a][1][2],0):
                raise Core0Error("server start differs from its real nonce and local Endpoint")
            task["start"]=True
        elif tag == 0x240:
            task=self.actual_user(a,{"clienta","clientb"})
            if task["start"] or (b,c,d)!=(task["nonce"],self.grants[a][0][2],self.grants[a][1][2]):
                raise Core0Error("client start differs from independent nonce/local grants")
            task["start"]=True
        elif tag == 0x230:
            task=self.actual_user(a,{"clienta","clientb"})
            order=A_ORDER if task["key"]=="clienta" else B_ORDER
            errors=A_ERRORS if task["key"]=="clienta" else B_ERRORS
            values=A_VALUE if task["key"]=="clienta" else B_VALUE
            transactions=A_TRANSACTIONS if task["key"]=="clienta" else B_TRANSACTIONS
            rows=self.cases.setdefault(a,[])
            if not task["start"] or len(rows)>=len(order) or b!=order[len(rows)] or c!=errors.get(b,0):
                raise Core0Error(f"IPC actual client corpus differs at {event}")
            if c and d or b in values and d!=values[b] or b in transactions and not d:
                raise Core0Error("IPC public result exposes authority/error or wrong byte count/transaction")
            if b not in values and b not in transactions and b!=60 and not c and d:
                raise Core0Error("IPC successful void operation returned unexpected data")
            serials=A_SERIALS if task["key"]=="clienta" else B_SERIALS
            if b in serials and d!=serials[b]:
                raise Core0Error("failed IPC publication consumed or reused a transaction serial")
            if b==60:
                if d<16 or d%16!=3 or d>>4 in self.serials: raise Core0Error("transfer lacks fresh receiver-local capability")
                self.serials.add(d>>4)
            if b==70 or task["key"]=="clientb" and b==83: self.release_endpoint("probe")
            rows.append(list(event))
        elif tag == 0x231:
            task=self.actual_user(a,{"clienta","clientb"})
            requestbase=task["nonce"]*256
            own = task["key"]=="clienta" and b in {requestbase+16,requestbase+17,requestbase+18,requestbase+19}
            sender=a if own else self.role("server")
            if c!=sender or not 64<=d<=256: raise Core0Error("copied packet lacks full authenticated sender or valid actual length")
            self.packets.append(list(event))
        elif tag == 0x232:
            task=self.actual_user(a,{"clienta","clientb"}); base=task["nonce"]*256
            own=task["key"]=="clienta" and b in {base+16,base+17,base+18,base+19}
            nonce=task["nonce"] ^ (0x5a5a5a5a if own and b==base+19 else 0)
            length = {16:0,17:192,18:24,19:24}.get(b-base) if own else {1:192,2:24,3:8,257:24,513:24,769:24}.get(b-base) if task["key"]=="clienta" else {1:192,2:24,3:0}.get(b-base)
            if (length is None or c!=length or d!=digest(nonce,length,0 if own else 0xa5)
                    or not self.packets or self.packets[-1][1:3]!=[a,b] or self.packets[-1][4]!=64+length):
                raise Core0Error("actual binary payload/length differs from independent host reference")
            if any(row[1:3]==[a,b] for row in self.payloads): raise Core0Error("duplicate payload witness")
            self.payloads.append(list(event))
        elif tag == 0x233:
            self.actual_user(a,{"clienta"})
            if b not in {1,2,3,4} or b in self.snapshots or c!=6 or d!=self.remaining:
                raise Core0Error("IPC rejection changed bounded object/frame inventory")
            self.snapshots[b]=list(event)
        elif tag == 0x234:
            self.actual_user(a,{"clienta"})
            if b not in self.snapshots or b in self.refs or (c,d)!=(1,3):
                raise Core0Error("IPC rejection changed Endpoint references or blocked peer cap table")
            self.refs[b]=list(event)
        elif tag == 0x221:
            self.actual_user(a,{"server"})
            if b in self.server_accepts or c not in self.tasks or self.tasks[c]["reaped"] or d<16:
                raise Core0Error("server acceptance lacks one live authenticated caller and local Reply authority")
            caller=self.tasks[c]
            offsets={1,2,3,4,257,260,513,769} if caller["key"]=="clienta" else {1,2,3} if caller["key"]=="clientb" else set()
            ordinary=caller["key"] in {"clienta","clientb"} and b-caller["nonce"]*256 in offsets
            fault=caller["key"]=="fault" and b==caller["nonce"] and b%256 in {4,5}
            if not (ordinary or fault): raise Core0Error("server acceptance request differs from its authenticated expected caller")
            if d%16!=2 or d>>4 in self.serials: raise Core0Error("Reply capability reused a serial or wrong local server slot")
            self.serials.add(d>>4)
            self.server_accepts[b]={"record":list(event),"event_index":len(self.events)}
        elif tag in {0x222,0x223,0x224}:
            self.actual_user(a,{"server"})
            if b not in self.server_accepts or d:
                raise Core0Error("reply observation lacks prior server acceptance or has unexpected result")
            expected=80 if tag==0x223 or tag==0x222 and b%256==4 else 71 if tag==0x224 else 0
            target=self.server_replies if tag==0x222 else self.server_duplicates if tag==0x223 else self.server_invalid
            if c!=expected or b in target: raise Core0Error("invalid-memory retry, duplicate Reply or late Reply differs")
            target[b]={"record":list(event),"event_index":len(self.events)}
        elif tag in {0x2af,0x2bf}:
            task=self.actual_user(a,{"clienta"} if tag==0x2af else {"clientb"})
            if a in self.ready or (b,c,d)!=(task["nonce"],0,0): raise Core0Error("client completion witness differs")
            task["complete"]=True; self.ready[a]=list(event)
        elif tag == 0x250:
            task=self.actual_user(a,{"fault"})
            if task["start"] or (b,c)!=(task["nonce"],0) or d!=1 or b%256 not in {4,5}:
                raise Core0Error("late death actor lacks an actual outstanding Call")
            task["start"]=True; self.fault_calls[a]=list(event)
        elif tag == 0x251:
            task=self.actual_user(a,{"fault"})
            if self.peer_death is not None or (b,c,d)!=(task["nonce"],96,0) or b%256!=5:
                raise Core0Error("server death did not complete the actual pending Call once")
            task["complete"]=True; self.peer_death=list(event)
        elif tag == 0xd4:
            task=self.actual_user(self.current,{"server","fault"})
            if a!=15 or c!=0x10000 or d!=0x200000020 or not in_ranges(b,self.users[task["key"]]["function_ranges"]):
                raise Core0Error("death fixture lacks contained real U store-page fault")
            payload=(self.session.image.parent/"users"/task["key"]/"text.bin").read_bytes()
            word=int.from_bytes(payload[b-0x10000:b-0x10000+4],"little")
            if word&0x7f!=0x23 or word>>12&7!=3: raise Core0Error("faulting instruction is not an actual audited SD")
            task["fault"]=list(event)
            self.faults.append({"task":self.current,"record":list(event),"instruction":word,"event_index":len(self.events)})
        elif tag == 0xf2 and b in {5,6}:
            task=self._task(a); user=self.users[task["key"]]
            if self.current!=a or c<self.irq or task["key"]=="busy": raise Core0Error("IPC return lacks current real User context")
            if b==5:
                if "fault" not in task or d!=task["fault"][2] or task["reasons"][5]: raise Core0Error("fault return lacks captured architecture state")
                task["state"]=6
            else:
                if d!=user["syscall_bridge"]["ecall_pc"]: raise Core0Error("IPC block did not originate from audited ECALL")
                task["state"]=5; self.block_records.append(list(event))
            self.current,self.irq=None,c; task["reasons"][b]+=1
        elif tag == 0xf4:
            task=self._task(a)
            if self.current is not None or task["terminal"] is not None or c!=task["nonce"]:
                raise Core0Error("IPC task lifecycle runs on outgoing stack or lost private nonce")
            if d==15:
                if b!=44 or task["reasons"][5]!=1: raise Core0Error("User fault escaped contained termination")
                task["complete"]=True
            elif d==8:
                if b or not task["complete"] or task["reasons"][4]!=1: raise Core0Error("pending caller ordinary exit lacks checked death completion")
            elif d==0x100:
                if b!=0x55 or task["key"] not in {"clienta","clientb","busy"}: raise Core0Error("unexpected trusted termination")
            else: raise Core0Error("unexpected IPC task terminal cause")
            task["terminal"]=list(event); task["state"]=6
        elif tag == 0xf6:
            task=self._task(a)
            owned = "primary" if task["key"]=="server" else "inbox" if task["key"]=="clientb" else None
            queues=1 if owned and owned not in self.endpoint_releases else 0
            if self.current is not None or task["stats"] is None or b!=self.remaining or c!=b+task["pages"]+queues or d:
                raise Core0Error("IPC teardown leaked/double-freed task or Endpoint queue pages")
            if queues: self.endpoint_releases.add(owned)
            self.remaining=c; task["reaped"]=True
        else:
            super().observe(event)


def require_death_order(trace):
    caller_faults=[row for row in trace.faults if trace.tasks[row["task"]]["key"]=="fault"]
    if len(caller_faults)!=1: raise Core0Error("missing unique caller fault with outstanding IPC")
    caller=caller_faults[0]["task"]; request=trace.tasks[caller]["nonce"]
    accepted=trace.server_accepts.get(request)
    late=trace.server_replies.get(request)
    if (not accepted or accepted["record"][3]!=caller or accepted["event_index"]>=caller_faults[0]["event_index"]
            or not late or late["record"][3]!=80 or late["event_index"]<=caller_faults[0]["event_index"]):
        raise Core0Error("caller death was not actually after acceptance and before denied late Reply")
    server_faults=[row for row in trace.faults if trace.tasks[row["task"]]["key"]=="server"]
    if len(server_faults)!=1 or trace.peer_death is None: raise Core0Error("missing real server death and peer completion")
    death_request=trace.peer_death[2]
    if death_request not in trace.server_accepts or trace.server_accepts[death_request]["event_index"]>=server_faults[0]["event_index"]:
        raise Core0Error("server death lacks actual pending accepted Call")


def check(session):
    startup=validate_positive_records([session.record() for _ in range(4)])
    kernel,ready,managed=session.record(),session.record(),session.record()
    if (kernel[0]!=0xd3 or kernel[2:]!=(satp(kernel[1]),500,0)
            or ready!=(0xf0,1,8,512,10000) or managed!=(0xb0,1,16,16,498)):
        raise Core0Error("IPC startup does not bind real table/object/frame baseline")
    trace=IPCTrace(session)
    nonces=[]
    while len(nonces)<4:
        nonce=secrets.randbits(32)
        if nonce and nonce not in nonces: nonces.append(nonce)
    for image,nonce in enumerate(nonces): trace.expect_create(image,nonce)
    transport._write_all(session.process,struct.pack("<5Q",0x30,*nonces),deadline=session.deadline,
                         capture=session.capture,context="launching independent IPC Users")
    trace.until(lambda:len(trace.tasks)==4)
    server,clienta,clientb,busy=list(trace.tasks)
    trace.until(lambda:clienta in trace.ready and clientb in trace.ready and len(trace.tasks[busy]["preempt_irqs"])>=3)
    _,first=trace.command(0x31,busy)
    if len(first)!=1 or not first[0][4]: raise Core0Error("unrelated Busy made no real IPC-era progress")
    fault_nonces=[(secrets.randbits(32)<<8)|4,(secrets.randbits(32)<<8)|5]
    if any(not n for n in fault_nonces) or len(set(fault_nonces))!=2: raise Core0Error("bad runtime death-request corpus")
    for nonce in fault_nonces:
        trace.expect_create(4,nonce)
        ack,_=trace.command(0x33,4,nonce); caller=ack[3]
        trace.until(lambda:trace.tasks[caller]["reaped"])
        trace.command(0x31,caller,status=74,value=0)
        if nonce%256==4: trace.until(lambda:nonce in trace.server_replies)
    _,second=trace.command(0x31,busy)
    if len(second)!=1 or second[0][4]<=first[0][4]: raise Core0Error("unrelated Busy stalled during IPC death cleanup")
    for id in (clienta,clientb,busy):
        trace.command(0x32,id,0x55,value=id); trace.until(lambda:trace.tasks[id]["reaped"])
        trace.command(0x31,id,status=74,value=0)
    trace.command(0x31,0,value=498)
    require_death_order(trace)
    if (trace.live() or trace.current is not None or trace.creation_queue or trace.remaining!=498
            or trace.endpoint_releases!={"probe","primary","inbox"} or set(trace.snapshots)!={1,2,3,4}
            or set(trace.refs)!={1,2,3,4} or trace.serials!=set(range(1,29)) or len(trace.payloads)!=13
            or [row[2] for row in trace.cases[clienta]]!=A_ORDER or [row[2] for row in trace.cases[clientb]]!=B_ORDER
            or any(not trace.tasks[id]["reasons"][6] for id in (server,clienta,clientb))):
        raise Core0Error("I corpus omitted packets/rollback/blocks or leaked live authority/pages")
    for firstmark,secondmark in ((1,2),(3,4)):
        if trace.snapshots[firstmark][3:]!=trace.snapshots[secondmark][3:] or trace.refs[firstmark][3:]!=trace.refs[secondmark][3:]:
            raise Core0Error("failed IPC publication changed measured object/frame/reference inventory")
    for request in (nonces[1]*256+4,nonces[1]*256+260):
        case=47 if request==nonces[1]*256+4 else 52
        reply_row=next(row for row in trace.cases[clienta] if row[2]==case)
        index=trace.events.index(reply_row)
        if request not in trace.server_accepts or trace.server_accepts[request]["event_index"]>=index or request not in trace.server_replies:
            raise Core0Error("timeout/cancel was not independently observed after actual server acceptance")
    ready_request=nonces[1]*256+769
    ready_pointer=next(row for row in trace.cases[clienta] if row[2]==56)
    if ready_request not in trace.server_replies or trace.server_replies[ready_request]["event_index"]>=trace.events.index(ready_pointer):
        raise Core0Error("invalid ready-destination retry lacks prior actually committed server Reply")
    expected_requests={nonces[1]*256+x for x in (1,2,3,4,257,260,513,769)}|{nonces[2]*256+x for x in (1,2,3)}|set(fault_nonces)
    if (set(trace.server_accepts)!=expected_requests or set(trace.server_replies)!=expected_requests-{fault_nonces[1]}
            or set(trace.server_invalid)!={nonces[1]*256+2,nonces[2]*256+2}
            or set(trace.server_duplicates)!={nonces[1]*256+3,nonces[2]*256+3}):
        raise Core0Error("server acceptance/retry/one-use/late-reply corpus differs")
    return {"protocol":"ipc-I-v1","startup":startup,"kernel_root":list(kernel),"ready":list(ready),
            "managed_ready":list(managed),"compiled_ipc_evidence":trace.ipc_binding,"runtime_nonces":nonces,"death_request_nonces":fault_nonces,
            "tasks":{str(id):{**task,"reasons":dict(task["reasons"])} for id,task in trace.tasks.items()},
            "boot_grants":trace.grants,"actual_endpoint_allocations":trace.endpoints,
            "client_syscall_replies":trace.cases,"authenticated_packets":trace.packets,
            "independently_checked_binary_payloads":trace.payloads,"rollback_objects_frames":trace.snapshots,
            "rollback_references_peer_caps":trace.refs,"actual_block_records":trace.block_records,"exact_publication_serials":sorted(trace.serials),
            "server_acceptance":trace.server_accepts,"actual_replies":trace.server_replies,
            "duplicate_reply_rejections":trace.server_duplicates,"invalid_reply_memory":trace.server_invalid,
            "actual_user_faults":trace.faults,"server_death_completion":trace.peer_death,
            "busy_counter_queries":[first[0],second[0]],"actual_machine_interrupts":trace.irq,
            "final_remaining_frames":trace.remaining,"guest_lifetime":"one continuous VM"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image",type=Path,required=True);parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--timeout",type=float,default=180);parser.add_argument("--clean",action="store_true")
    args=parser.parse_args()
    try:
        root=repo_root()
        paths=("scripts/check_kernel_ipc.py","scripts/check_kernel_tasks.py","scripts/check_kernel_supervisor.py",
               "scripts/check_kernel_user.py","scripts/check_kernel.py","scripts/run_kernel.py",
               "scripts/run_device_session.py","scripts/run_monitor_session.py")
        runners={p:sha256(root/p) for p in paths}
        with Session(root=root,image=args.image,output_dir=args.output_dir,timeout=args.timeout,clean=args.clean) as session:
            session.report.update(runner_inputs=runners,acceptance_checker_sha256=sha256(Path(__file__)))
            observed=check(session)
            if {p:sha256(root/p) for p in paths}!=runners: raise Core0Error("I runner changed while VM was live")
            session.finish(observed)
        from check_kernel import validate_session
        try: validate_session(session.output_dir/"result.json",session.image)
        except (Core0Error,OSError,ValueError,TypeError,KeyError) as error:
            session.report.update(status="FAIL",error=str(error),failure_category="post-cleanup-wire-evidence")
            write_json(session.output_dir/"result.json.tmp",session.report)
            (session.output_dir/"result.json.tmp").replace(session.output_dir/"result.json"); raise
        print("PASS: copied capability IPC, real blocks, binary payloads and contained peer deaths observed")
        return 0
    except (Core0Error,OSError,ValueError,TypeError,KeyError,IndexError) as error:
        print(f"FAIL: {error}");return 1

if __name__=="__main__":raise SystemExit(main())
