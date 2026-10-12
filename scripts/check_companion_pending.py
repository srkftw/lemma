#!/usr/bin/env python3
"""Actual guest ink while an external durable receipt is unresolved.

Raw pen/public lifecycle stimulus, independent frame/medium/pixel observers.
No host document state enters the machine. Declared limits remain load-bearing.
"""
import argparse
import json
from pathlib import Path
import struct
import time

from check_companion_session import CompanionChecker, crc64, outbox, peer_records
from check_live_notebook import (Input, ROOT, committed_bytes, generate,
                                guest_events, idle, observe_workflow, require,
                                sha, visible_pixels)


def timed_records(path):
    raw=Path(path).read_bytes();require(raw[:8]==b'LMIOLOG2' and len(raw)>=72,'missing timed capture')
    position=72;pending=None;rows=[]
    while position<len(raw):
        require(position+16<=len(raw),'timed entry header truncated')
        tag,n=struct.unpack_from('<2Q',raw,position);position+=16
        require(tag in (0,1) and n<=3145888 and position+n<=len(raw),'timed entry bound')
        data=raw[position:position+n];position+=n
        require(n>=48 and struct.unpack_from('<Q',data,n-8)[0]==crc64(data[:-8]),'timed entry CRC')
        if tag==0:
            require(pending is None,'more than one admitted external operation')
            fields=struct.unpack_from('<5Q',data);require(fields[2]<=2 and n==48+(fields[4] if fields[2]==1 else 0),'submission fields')
            pending=(fields,data[40:-8])
        else:
            require(n>=80 and pending is not None,'completion without submission')
            fields=struct.unpack_from('<7Q',data);completed=struct.unpack_from('<Q',data,n-16)[0]
            require(fields[:5]==pending[0] and completed>=fields[1],'completion identity/time')
            requested=fields[4] if fields[2]==1 else 0
            require(n==80+requested+fields[5] and data[56:56+requested]==pending[1],'completion prefix bound')
            require(struct.unpack_from('<Q',data,n-24)[0]==crc64(data[:-24]),'outcome CRC')
            rows.append((fields,completed));pending=None
    return rows,pending


class PendingChecker(CompanionChecker):
    def __init__(self,args):
        super().__init__(args)
        self.report.update(schema='lemmasim-guest-companion-pending-observations/1',
            scope='actual RV64 raw ink while same-ID opaque backing receipt remains pending; explicit development retry, not USB')
        self.report['observer_sources'][str(Path(__file__).relative_to(ROOT))]=sha(__file__)

    def execute(self):
        self.command(['companion','init','--directory',str(self.peer),'--base',str(self.args.disk.resolve()),'--writer','17'])
        self.report['source_medium']={'path':str(self.args.disk.resolve()),'sha256':sha(self.args.disk)}
        self.report['peer_preparation']=json.loads(self.args.peer_prepared.read_text());self.start_peer()
        live=self.session('live',self.args.disk);self.report['identity']=live.identity;self.report['boot']=live.boot()
        _,fixture=generate('basic',1650,2200,0,100000,0)
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events);live.settle(stream.events[-1][1])
        for action in fixture['actions']:self.action(live,stream,action)
        start=live.inspect()['machine']['storage']['backing_next_id']
        self.action(live,stream,{'kind':'tool','button':6,'name':'calibrate equal-size root'})
        rows,pending=timed_records(live.directory/'backing-0.io');pattern=[row[0] for row in rows if row[0][0]>=start]
        require(pending is None and pattern and pattern[-1][2]==2 and all(row[6]==0 for row in pattern),'calibration final barrier')
        self.report['predeclared_lost_reply']={'ordinal':len(pattern),'operation_shape':[(row[2],row[4]) for row in pattern]}
        for step in (2,3):self.action(live,stream,{'kind':'tool','button':6,'name':f'root cycle step{step}'})
        self.stop_peer();self.start_peer(drop=len(pattern));before=live.inspect()['machine']
        first=len(stream.events);stream.tick=before['ticks']+10000;stream.tool(6,'root cycle step4 lost final ACK');live.admit(stream.events[first:])
        started=time.monotonic();saved_before=sum(row[0]==0x421 for row in guest_events(live.directory/'uart-0.bin'))
        pending=live.wait(lambda state:state['storage'].get('retry_ready')==1,self.args.action_seconds,quantum=1000000)
        self.server.wait(timeout=5);writer,sequence,frame=outbox(self.client/'outbox')
        require(frame is not None and frame[2]==2,'selected lost receipt is not an actual barrier')
        require(pending['storage']['backing_phase']==1 and not pending['storage']['backing_poisoned'],'known pending became an invented result or poison')
        require(sum(row[0]==0x421 for row in guest_events(live.directory/'uart-0.bin'))==saved_before,'Saved preceded receipt reconciliation')
        try:live.snapshot('rejected-pending')
        except (RuntimeError,ValueError) as error:self.report['pending_snapshot_rejected']=str(error)
        else:raise ValueError('external pending snapshot unexpectedly admitted')
        peer_size=(self.peer/'opaque.log').stat().st_size
        require(sum(row[3:5]==(writer,sequence) and row[2]==2 for row in peer_records(self.peer/'opaque.log'))==1,'missing/duplicated actual durable barrier receipt')
        first=len(stream.events);stream.tick=pending['ticks']+10000;stream.stroke('offline',1,1,25,1600,brush=512);live.admit(stream.events[first:])
        final_tick=stream.events[-1][1];wait_panel=self.directory/'pending-ink.ppm'
        def ink_present(state):
            if state['ticks']<final_tick+2000000 or state['devices']['pen']['count'] or state['devices']['paper']['status']&1:return False
            live.control({'action':'panel','path':str(wait_panel)});width,height,pixels=visible_pixels(wait_panel)
            sample=stream.events[first];x=sample[2]*(width-1)//65535;y=sample[3]*(height-1)//65535
            return any(pixels[(py*width+px)*3:(py*width+px)*3+3]==bytes(3) for py in range(y-2,y+3) for px in range(x-2,x+3))
        ink=live.wait(ink_present,self.args.action_seconds,quantum=1000000)
        require(ink['cycle']>pending['cycle'] and ink['storage']['backing_phase']==1 and not ink['storage']['backing_poisoned'],'CPU did not retain pending while processing ink')
        require(sum(row[0]==0x421 for row in guest_events(live.directory/'uart-0.bin'))==saved_before,'provisional offline ink manufactured Saved')
        rows,active=timed_records(live.directory/'backing-0.io');require(active is not None and active[0][2]==2,'pending capture submission lost')
        self.report['pending_ink']={'status':'PASS','host_seconds':time.monotonic()-started,'initial_cycle':pending['cycle'],'final_cycle':ink['cycle'],
            'raw_samples':25,'controller_contact_dark':True,'guest_saved':False,'writer':writer,'transaction':sequence,'peer_bytes':peer_size}
        self.stop_peer();self.start_peer();live.control({'action':'companion-retry'});live.settle(final_tick)
        self.action(live,stream,{'kind':'tool','button':7,'name':'save all real pending ink after receipt'})
        panel,medium=live.export('acknowledged');expected=dict(fixture['expected']);expected['visible_strokes']={'1/1':['a','b','offline']}
        self.report['workflow']=observe_workflow(medium,live.directory/'input-0.bin',live.directory/'uart-0.bin',panel,stream,expected)
        rows,active=timed_records(live.directory/'backing-0.io');require(active is None and all(row[0][6]==0 for row in rows),'reconciled capture lacks real completion')
        require(sum(row[3:5]==(writer,sequence) and row[2]==2 for row in peer_records(self.peer/'opaque.log'))==1,'explicit retry duplicated effect')
        live.close();self.sessions.remove(live);self.stop_peer();self.start_peer();cold=self.session('cold',self.args.disk)
        self.report['cold_boot']=cold.boot();target=visible_pixels(panel);wait_panel=self.directory/'cold-wait.ppm'
        def cold_display(state):
            if not idle(state):return False
            cold.control({'action':'panel','path':str(wait_panel)});return visible_pixels(wait_panel)==target
        cold.wait(cold_display,self.args.action_seconds,quantum=5000000);cold_panel,cold_medium=cold.export('cold')
        require(committed_bytes(medium)==committed_bytes(cold_medium),'cold exact acknowledged object bytes differ')
        require(visible_pixels(cold_panel)==target,'cold full controller pixels differ')
        self.report['cold_recovery']={'status':'PASS','exact_acknowledged_bytes':True,'complete_controller_pixels_equal':True,'new_cpu':True}
        cold.close();self.sessions.remove(cold);self.stop_peer();self.report['status']='PASS'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disk',type=Path,required=True);p.add_argument('--peer-prepared',type=Path,required=True)
    p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('--boot-seconds',type=int,default=40)
    p.add_argument('--action-seconds',type=int,default=20);p.add_argument('--deadline',type=int,default=900)
    args=p.parse_args();args.durable_suffix_from=None;args.checkpoint_relation='not-exercised';checker=PendingChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:
        for session in reversed(checker.sessions):session.close()
        checker.stop_peer();checker.commands.close();checker.report['host_seconds']=time.monotonic()-checker.started
        (checker.directory/'result.json').write_text(json.dumps(checker.report,indent=2,default=str)+'\n')
    print(json.dumps(checker.report,indent=2,default=str))


if __name__=='__main__':main()
