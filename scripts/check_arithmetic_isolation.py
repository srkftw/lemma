#!/usr/bin/env python3
"""Actual isolated RV64 arithmetic OOM/death/deadline/cancellation observations.

Raw pen is the only answer/editor stimulus. A separately linked Laboratory
server fills real owned objects, faults or withholds a reply. The observer never
writes a guest record/result or substitutes checker/kernel execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from check_math_session import MathChecker
from check_live_notebook import Input,idle,require,sha,visible_pixels
from store_oracle import recover

class IsolationChecker(MathChecker):
    def __init__(self,args):
        super().__init__(args)
        self.allowed_error=False
        self.report.update(schema='lemmasim-arithmetic-isolation/1',case=args.case,
            scope='actual scalar Lean isolated arithmetic process and copied IPC; managed source constructors/proof kernel/full verifier remain unfinished')
        self.report['observer_sources']['scripts/check_arithmetic_isolation.py']=sha(Path(__file__))
    def settle(self,session,tick,completed=None):
        def done(state):
            rows=self.rows(session)
            require(not any(r[0] in (0x41f,0x424) for r in rows),'guest formatted or storage failed')
            if not self.allowed_error:
                require(not any(r[0] in (0x454,0xd4,0xf4) for r in rows),'unexpected early checker/process failure')
            else:
                server=[r[1] for r in rows if r[0]==0xf1 and r[2]==2]
                require(len(server)==1,'third image identity missing or duplicated')
                require(all(r[1]==server[0] for r in rows if r[0]==0xf4),'another service died')
                require(all(self.args.case=='fault' and r[1]==13 and r[3]==0x500000 for r in rows if r[0]==0xd4),'unexpected architectural fault')
            commits=[r for r in rows if r[0] in (0x421,0x423,0x424)]
            return state['ticks']>=tick+2000000 and idle(state) and (not commits or commits[-1][0]==0x421) and (completed is None or state['devices']['paper']['completed']>completed)
        return session.wait(done,self.args.action_seconds,quantum=200000)
    def raw_click(self,session,stream,x,y):
        first=len(stream.events);stream.tick=session.inspect()['machine']['ticks']+10000
        stream.sample(x,y,2048,True);stream.sample(x,y,0,False)
        session.admit(stream.events[first:]);return stream.events[-1][1]
    def ink(self,session,stream,name):
        first=len(stream.events);stream.tick=session.inspect()['machine']['ticks']+10000
        stream.stroke(name,1,1,6,1700);session.admit(stream.events[first:]);return first,stream.events[-1][1]
    def execute(self):
        original=sha(self.args.disk);disk=self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        live=self.session('live',disk);self.report['identity']=live.identity;self.report['boot']=live.boot()
        rows=self.rows(live);mode={'oom':1,'fault':2,'stall':3}[self.args.case]
        start=[r for r in rows if r[0]==0x456]
        require(start==[(0x456,mode,31 if mode==1 else 0,1,10000000)],'server did not execute actual declared mode/object pressure/deadline')
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events)
        self.click(live,stream,'open course before isolated fault',320,140)
        prior_panel,prior_medium=live.export('before-check')
        prior_bytes,prior,_,_=self.record(prior_medium)
        require(prior['outcome']==0 and not prior['history'],'initial course already had manufactured evidence')
        self.allowed_error=True
        submitted=len([r for r in self.rows(live) if r[0]==0x459])
        tick=self.raw_click(live,stream,40,245)
        state=live.wait(lambda s:len([r for r in self.rows(live) if r[0]==0x459])>submitted,self.args.action_seconds,quantum=10000)
        request=[r for r in self.rows(live) if r[0]==0x459][-1]
        self.report['submission']={'actual_guest_request':request,'observed_tick':state['ticks'],'raw_tick':tick}
        expected={'oom':237,'fault':96,'stall':93}[self.args.case]
        def expected_error(state):
            require(not any(r[0]==0x424 for r in self.rows(live)),'actual Store failure while checker pending')
            return any(r[0]==0x454 and r[1]==expected for r in self.rows(live))
        live.wait(expected_error,self.args.action_seconds,quantum=100000)
        self.settle(live,stream.events[-1][1]);self.wait_label(live,'SAVED',24,132)
        _,error_medium=live.export('after-error')
        require(self.record(error_medium)[0]==prior_bytes,'checker failure mutated acknowledged math record')
        require(not any(r[0]==0x450 and r[3]!=0 for r in self.rows(live)),'checker failure manufactured trusted evidence')
        if self.args.case=='oom':
            require(any(r[0]==0x455 and r[3:]==(237,0) for r in self.rows(live)),'OOM was not returned by real owned-object allocation')
        if self.args.case=='fault':
            require(any(r[0]==0xd4 and r[1]==13 and r[3]==0x500000 for r in self.rows(live)),'unmapped user instruction never caused actual page fault')
            require(any(r[0]==0xf6 for r in self.rows(live)),'dead checker resources were not reaped')
        self.report['failed_request']={'status':'PASS','actual_error':expected,'math_sha256':hashlib.sha256(prior_bytes).hexdigest(),'no_new_evidence':True,'record_unchanged':True}
        # Ordinary ink remains available after each failure and survives cold.
        first,ink_tick=self.ink(live,stream,'ink after isolated checker failure')
        self.settle(live,ink_tick);self.wait_label(live,'SAVED',24,132)
        final_panel,final_medium=live.export('final')
        _,_,records=recover(final_medium.read_bytes());sample_sets=[]
        for key,record in records.items():
            if key[1]>0x10000 and len(record.payload)>=128:
                n=struct.unpack_from('<Q',record.payload,48)[0]
                sample_sets.append([struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(n)])
        actual_samples=[sample for group in sample_sets for sample in group]
        require(all(sample in actual_samples for sample in stream.events[first:]),'post-failure raw ink was not constructed and persisted by guest')
        require(self.record(final_medium)[0]==prior_bytes,'post-failure writing changed mathematical record')
        if self.args.case=='stall':
            live.wait(lambda state:any(r[0]==0x45a and r[1]==request[1] and r[3] in (80,83) and r[4]==3 for r in self.rows(live)),self.args.action_seconds,quantum=1000000)
            self.click(live,stream,'reopen before writing-priority cancellation',320,140)
            started=len([r for r in self.rows(live) if r[0]==0x459])
            errors=len([r for r in self.rows(live) if r[0]==0x454])
            cancels=len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])
            self.raw_click(live,stream,40,245)
            state=live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x459])>started,self.args.action_seconds,quantum=10000)
            automatic_request=[r for r in self.rows(live) if r[0]==0x459][-1]
            live.wait(lambda state:any(r[0]==0x45b and r[1]==automatic_request[1] and r[2]==automatic_request[2] and r[3]==3 for r in self.rows(live)),self.args.action_seconds,quantum=10000)
            before_ink=len([r for r in self.rows(live) if r[0]==0x423])
            first,ink_tick=self.ink(live,stream,'writing while checker delays reply')
            def automatic_cancel(state):
                rows=self.rows(live)
                require(not any(r[0]==0x424 for r in rows),'writing-priority cancellation failed to free the real IPC slot')
                return state['devices']['pen']['count']==0 and len([r for r in rows if r[0]==0x423])>before_ink and len([r for r in rows if r[0]==0x458 and r[1:3]==(1,94)])>cancels
            admitted=live.wait(automatic_cancel,self.args.action_seconds,quantum=10000)
            require(admitted['ticks']-state['ticks']<10000000,'raw writing did not cancel/admit Store within the unchanged checker deadline')
            self.settle(live,ink_tick);self.wait_label(live,'SAVED',24,132)
            _,automatic_medium=live.export('automatic-cancel-ink')
            require(self.record(automatic_medium)[0]==prior_bytes,'automatic cancellation changed mathematical evidence/history')
            _,_,automatic_records=recover(automatic_medium.read_bytes())
            stored=[]
            for key,record in automatic_records.items():
                if key[1]>0x10000 and len(record.payload)>=128:
                    count=struct.unpack_from('<Q',record.payload,48)[0]
                    stored.extend(struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(count))
            require(all(sample in stored for sample in stream.events[first:]),'writing-priority cancellation lost raw samples')
            self.report['while_stalled']={'status':'PASS','store_admission_tick':admitted['ticks'],'deadline_ticks':10000000,'raw_first_sequence':first+1,'raw_last_sequence':len(stream.events),'actual_consumed_terminal':94,'actual_guest_barrier_acknowledged':True}
            # Change a real submitted object after cancellation, before the old
            # server's predeclared twenty-second delay permits its reply.
            edited=self.press(live,stream,'edit numerator after cancelled check',27)
            require(edited[1]>automatic_request[2] and edited[3:]==(0,0),'edited submission retained old applicability')
            _,edited_medium=live.export('edited-before-late-reply')
            expected_math=self.record(edited_medium)[0]
            require(expected_math!=prior_bytes,'raw edit never changed the actual guest submission')
            require(not any(r[0]==0x45a and r[1]==automatic_request[1] for r in self.rows(live)),'selected delayed reply arrived before the edited-revision test boundary')
            def rejected_late_reply(state):
                require(not any(r[0]==0x424 for r in self.rows(live)),'late-reply boundary lost writing')
                return any(r[0]==0x45a and r[1]==automatic_request[1] and r[2]==automatic_request[2] and r[3] in (80,83) and r[4]==3 for r in self.rows(live))
            live.wait(rejected_late_reply,self.args.action_seconds,quantum=1000000)
            _,late_medium=live.export('late-reply-rejected')
            require(self.record(late_medium)[0]==expected_math and not any(r[0]==0x450 and r[3]!=0 for r in self.rows(live)),'late cancelled reply changed evidence or the edited record')
            self.report['stale_reply']={'status':'PASS','actual_request':automatic_request[1],'original_revision':automatic_request[2],'edited_revision':edited[1],'actual_retired_authority_rejection':True,'edited_record_unchanged':True}
            started=len([r for r in self.rows(live) if r[0]==0x459])
            cancels=len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])
            self.raw_click(live,stream,40,245)
            live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x459])>started,self.args.action_seconds,quantum=10000)
            close_tick=self.raw_click(live,stream,320,140)
            live.wait(lambda state:len([r for r in self.rows(live) if r[0]==0x458 and r[1:3]==(1,94)])>cancels,self.args.action_seconds,quantum=10000)
            self.settle(live,close_tick);self.wait_label(live,'SAVED',24,132)
            require(len([r for r in self.rows(live) if r[0]==0x454])==errors,'cancellation later published a terminal checker error')
            final_panel,final_medium=live.export('cancelled')
            require(self.record(final_medium)[0]==expected_math,'explicit cancellation changed edited mathematical evidence/history')
            self.report['cancellation']={'status':'PASS','actual_consumed_terminal':94,'record_unchanged':True,'reply_discarded':True}
            prior_bytes=expected_math
        live.close();self.sessions.remove(live)
        cold_disk=self.directory/'cold-input.raw';shutil.copyfile(final_medium,cold_disk)
        cold=self.session('cold',cold_disk);self.report['cold_boot']=cold.boot()
        require(cold.identity==self.report['identity'],'cold artifact identity changed')
        self.wait_label(cold,'SAVED',24,132);cold_panel,cold_medium=cold.export('cold-notebook')
        require(visible_pixels(cold_panel)==visible_pixels(final_panel),'cold complete controller output differs')
        require(self.record(cold_medium)[0]==prior_bytes,'cold recovered modified math/evidence')
        self.report['cold_recovery']={'status':'PASS','new_cpu':True,'complete_controller_pixels_equal':True,'acknowledged_math_unchanged':True,'raw_ink_preserved':True}
        cold.close();self.sessions.remove(cold)
        require(sha(self.args.disk)==original,'observer changed original medium')
        self.report['status']='PASS'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('oom','fault','stall'),required=True)
    parser.add_argument('--disk',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--native-bundle',required=True);parser.add_argument('--guest-build',required=True)
    parser.add_argument('--timeout',type=int,default=300);parser.add_argument('--boot-seconds',type=int,default=60)
    parser.add_argument('--action-seconds',type=int,default=30);parser.add_argument('--deadline',type=int,default=1200)
    args=parser.parse_args();args.checkpoint_relation='not-exercised';args.durable_suffix_from=None
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600 and 1<=args.deadline<=2400,'invalid predeclared resource bounds')
    checker=IsolationChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:checker.close()
    print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))
if __name__=='__main__':main()
