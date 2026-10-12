#!/usr/bin/env python3
"""Observe ordinary RV64 ink/save through the independent opaque Lean peer.

Host stimulus uses public raw pen input and lifecycle controls. Offline oracles
observe records/pixels only; they never feed recovered documents to the guest.
The lost reply ordinal is preselected from a completed equal-size root edit,
then its actual final Barrier/outbox/receipt is independently checked.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

from check_live_notebook import (Checker, Input, ROOT, committed_bytes, generate,
                                 guest_events, idle, observe_workflow, require,
                                 sha, visible_pixels)


def crc64(raw):
    value=0
    for byte in raw:
        value ^= byte << 56
        for _ in range(8):
            value=((value<<1) ^ (0x42f0e1eba9ea3693 if value>>63 else 0)) & ((1<<64)-1)
    return value


def backing_records(path, pending=False):
    raw=Path(path).read_bytes()
    require(len(raw)>=72 and raw[:8]==b'LMIOLOG1','missing actual backing capture')
    rows=[];position=72
    while position<len(raw):
        require(position+8<=len(raw),'truncated captured operation length')
        n=struct.unpack_from('<Q',raw,position)[0];position+=8
        if n==0:
            require(pending and position==len(raw),'capture has unresolved or incomplete operations')
            return rows,True
        require(64<=n<=2097216 and position+n<=len(raw),'captured operation bound')
        data=raw[position:position+n];position+=n
        require(struct.unpack_from('<Q',data,n-8)[0]==crc64(data[:-8]),'captured outcome CRC')
        fields=struct.unpack_from('<7Q',data)
        requested=fields[4] if fields[2]==1 else 0
        require(n==64+requested+fields[5],'captured prefix length')
        rows.append(fields)
    return rows,False


def outbox(path):
    raw=Path(path).read_bytes()
    require(len(raw)>=40 and struct.unpack_from('<Q',raw,len(raw)-8)[0]==crc64(raw[:-8]),'outbox CRC')
    magic,writer,sequence,n=struct.unpack_from('<4Q',raw)
    require(magic==0x313054554f434d4c and n==len(raw)-40,'outbox bounds')
    frame=raw[32:-8]
    if frame:
        require(struct.unpack_from('<Q',frame,len(frame)-8)[0]==crc64(frame[:-8]),'pending frame CRC')
        fields=struct.unpack_from('<8Q',frame)
        require(fields[:2]==(0x313030504d434d4c,1) and fields[3:5]==(writer,sequence),'pending frame identity')
        return writer,sequence,fields
    return writer,sequence,None


def peer_records(path):
    raw=Path(path).read_bytes();require(raw[:8]==struct.pack('<Q',0x3130474f4c434d4c),'peer log identity')
    rows=[];position=8
    while position<len(raw):
        require(position+8<=len(raw),'peer length truncation')
        n=struct.unpack_from('<Q',raw,position)[0];position+=8
        require(72<=n<=584 and position+n<=len(raw),'peer complete receipt bound')
        data=raw[position:position+n];position+=n
        require(struct.unpack_from('<Q',data,n-8)[0]==crc64(data[:-8]),'peer receipt CRC')
        fields=struct.unpack_from('<8Q',data)
        require(fields[:2]==(0x313030504d434d4c,1) and fields[2] in (1,2),'peer receipt type')
        rows.append(fields)
    return rows


class CompanionChecker(Checker):
    profile='lemma-silicon-dev/0.3.0'

    def __init__(self,args):
        super().__init__(args)
        self.peer=self.directory/'peer'
        self.peer_socket=self.directory/'peer.sock'
        self.client=self.directory/'client'
        self.server=None;self.server_log=None;self.server_generation=0
        self.report.update(schema='lemmasim-guest-companion-backing-observations/1',
            scope='actual RV64 notebook journal through hosted Lean opaque peer; development transport, not USB or asynchronous companion controller',
            checkpoint_relation='not exercised; QEMU omitted cached-state continuation remains open')
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))]=sha(__file__)

    def launch(self,args,**kwargs):
        args=list(args)
        if args and args[0]=='session':
            i=args.index('--disk');del args[i:i+2]
            args+=['--companion',str(self.peer),'--companion-prepared',str(self.args.peer_prepared.resolve()),
                   '--companion-socket',str(self.peer_socket),'--companion-state',str(self.client)]
        return super().launch(args,**kwargs)

    def start_peer(self,drop=0):
        self.server_log=(self.directory/f'peer-{self.server_generation}.log').open('xb')
        self.server_generation+=1
        args=['companion','serve','--prepared',str(self.args.peer_prepared.resolve()),
              '--directory',str(self.peer),'--socket',str(self.peer_socket)]
        if drop:args+=['--drop-reply',str(drop),'--exit-after-reply',str(drop)]
        self.server=self.launch(args,stdout=self.server_log,stderr=self.server_log,start_new_session=True)
        deadline=min(self.deadline,time.monotonic()+15)
        while not self.peer_socket.exists():
            require(self.server.poll() is None,'peer launch failed')
            require(time.monotonic()<deadline,'peer launch resource bound')
            time.sleep(0.01)

    def stop_peer(self):
        if self.server is not None:
            if self.server.poll() is None:os.killpg(self.server.pid,signal.SIGTERM)
            try:self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(self.server.pid,signal.SIGKILL);self.server.wait(timeout=5)
            self.server=None
        if self.server_log is not None:self.server_log.close();self.server_log=None

    def action(self,session,stream,action):
        before=session.inspect()['machine'];first=len(stream.events)
        stream.tick=before['ticks']+10000;started=time.monotonic()
        if action['kind']=='stroke':
            stream.stroke(action['name'],1,1,action['raw_samples'],2200//3 if action['name']=='a' else 1100)
        else:stream.tool(action['button'],action['name'])
        session.admit(stream.events[first:]);after=session.settle(stream.events[-1][1])
        self.report['interactions'].append({'name':action['name'],'host_seconds':time.monotonic()-started,
            'initial_cycle':before['cycle'],'final_cycle':after['cycle'],
            'virtual_seconds':(after['virtual_ns']-before['virtual_ns'])/1e9})
        return before,after

    def execute(self):
        self.command(['companion','init','--directory',str(self.peer),'--base',str(self.args.disk.resolve()),'--writer','17'])
        self.report['source_medium']={'path':str(self.args.disk.resolve()),'sha256':sha(self.args.disk)}
        self.report['peer_preparation']=json.loads(self.args.peer_prepared.read_text())
        self.start_peer()
        live=self.session('live',self.args.disk)
        self.report['identity']=live.identity;self.report['boot']=live.boot()
        _,fixture=generate('basic',1650,2200,0,100000,0)
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events);live.settle(stream.events[-1][1])
        for action in fixture['actions']:
            self.action(live,stream,action)
        panel,medium=live.export('acknowledged')
        self.report['workflow']=observe_workflow(medium,live.directory/'input-0.bin',live.directory/'uart-0.bin',panel,stream,fixture['expected'])
        # Clean explicit Save may correctly have no medium work. A brush edit
        # always publishes a new equal-size root through the actual guest store.
        # Four edits cycle 256 -> 512 -> 1024 -> 2048 -> 256; the final edit
        # therefore restores exactly the original expected bytes and pixels.
        save_start=live.inspect()['machine']['storage']['backing_next_id']
        self.action(live,stream,{'kind':'tool','button':6,'name':'calibrate brush root publication'})
        rows,_=backing_records(live.directory/'backing-0.io')
        pattern=[row for row in rows if row[0]>=save_start]
        require(pattern and pattern[-1][2]==2 and all(row[6]==0 for row in pattern),'completed root edit does not end with actual barrier')
        require(all(row[2] in (1,2) for row in pattern),'root edit has unaccounted transport operations')
        self.report['predeclared_lost_reply']={'ordinal':len(pattern),'prior_equal_size_root_operations':[list(row) for row in pattern]}
        for width in (1024,2048):
            start=live.inspect()['machine']['storage']['backing_next_id']
            self.action(live,stream,{'kind':'tool','button':6,'name':f'brush root {width}'})
            current=[row for row in backing_records(live.directory/'backing-0.io')[0] if row[0]>=start]
            require([(row[2],row[4],row[5],row[6]) for row in current]==[(row[2],row[4],row[5],row[6]) for row in pattern],
                    'equal-size root edits have different predeclared operation shapes')
        before=live.inspect()['machine'];saved_before=sum(row[0]==0x421 for row in guest_events(live.directory/'uart-0.bin'))
        self.stop_peer();self.start_peer(drop=len(pattern))
        stream.tick=before['ticks']+10000;first=len(stream.events);stream.tool(6,'brush root 256 with final durable receipt lost')
        live.admit(stream.events[first:])
        failure=None;started=time.monotonic()
        while live.inspect()['machine']['cycle']-before['cycle']<self.args.action_seconds*100000000:
            try:live.run(1000000)
            except RuntimeError as error:failure=str(error);break
        require(failure is not None and 'persistence unresolved' in failure,'lost reply did not pause unresolved guest completion')
        self.server.wait(timeout=5)
        pending=live.inspect()['machine'];writer,sequence,frame=outbox(self.client/'outbox')
        require(frame is not None and frame[2]==2 and frame[5:8]==(0,0,0),'actual lost acknowledgment was not the preselected final barrier')
        require(pending['storage']['backing_phase']==1 and pending['storage']['backing_poisoned']==1,'ambiguous machine pending state lost')
        require(sum(row[0]==0x421 for row in guest_events(live.directory/'uart-0.bin'))==saved_before,'guest manufactured Saved before reconciliation')
        capture,pending_tail=backing_records(live.directory/'backing-0.io',True)
        require(pending_tail,'ambiguous capture was presented as a complete outcome')
        peer_before=peer_records(self.peer/'opaque.log');size_before=(self.peer/'opaque.log').stat().st_size
        require(sum(row[3:5]==(writer,sequence) and row[2]==2 for row in peer_before)==1,'peer did not retain exactly one actual barrier receipt')
        self.report['lost_ack']={'status':'PASS','writer':writer,'transaction':sequence,'host_seconds':time.monotonic()-started,
            'machine':pending,'error':failure,'guest_saved_before_reconciliation':False,'peer_bytes':size_before,
            'complete_captured_outcomes':len(capture),'captured_pending':True}
        try:live.snapshot('rejected-pending')
        except (ValueError,RuntimeError) as error:self.report['pending_snapshot_rejected']=str(error)
        else:raise ValueError('pending external snapshot unexpectedly succeeded')
        live.close();self.sessions.remove(live);self.stop_peer();self.start_peer()
        cold=self.session('cold',self.args.disk)
        require((self.peer/'opaque.log').stat().st_size==size_before,'reconciliation appended a duplicate transaction')
        new_writer,new_sequence,new_pending=outbox(self.client/'outbox')
        require((new_writer,new_sequence,new_pending)==(writer,sequence+1,None),'restart did not reconcile durable receipt/outbox')
        self.report['cold_boot']=cold.boot()
        expected_pixels=visible_pixels(panel)
        waiting=self.directory/'cold-wait.ppm'
        def display_complete(state):
            if not idle(state):return False
            cold.control({'action':'panel','path':str(waiting)})
            return visible_pixels(waiting)==expected_pixels
        cold.wait(display_complete,self.args.action_seconds,quantum=5000000)
        cold_panel,cold_medium=cold.export('cold')
        original=committed_bytes(medium);recovered=committed_bytes(cold_medium)
        require(original[1:]==recovered[1:] and recovered[0]==original[0]+4,'cold guest lost bytes or did not recover the actual final unacknowledged publication')
        require(visible_pixels(cold_panel)==expected_pixels,'cold complete controller display differs')
        require((self.peer/'opaque.log').stat().st_size==size_before,'cold recovery unexpectedly rewrote peer data')
        self.report['cold_recovery']={'status':'PASS','new_cpu':True,'all_committed_objects_equal':True,
            'prior_sequence':original[0],'recovered_sequence':recovered[0],'complete_controller_pixels_equal':True,
            'medium_sha256':sha(cold_medium),'peer_duplicate_effects':0}
        cold.close();self.sessions.remove(cold);self.stop_peer()
        self.report['status']='PASS'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disk',type=Path,required=True);p.add_argument('--peer-prepared',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--boot-seconds',type=int,default=40);p.add_argument('--action-seconds',type=int,default=20)
    p.add_argument('--deadline',type=int,default=900)
    args=p.parse_args();args.durable_suffix_from=None;args.checkpoint_relation='not-exercised'
    require(args.disk.is_file() and args.disk.stat().st_size==268435456,'use an existing genuine guest-initialized 256MiB medium')
    checker=CompanionChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:
        for session in reversed(checker.sessions):session.close()
        checker.stop_peer();checker.commands.close()
        checker.report['host_seconds']=time.monotonic()-checker.started
        (checker.directory/'result.json').write_text(json.dumps(checker.report,indent=2,default=str)+'\n')
    print(json.dumps(checker.report,indent=2,default=str))


if __name__=='__main__':main()
