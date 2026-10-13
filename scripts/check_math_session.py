#!/usr/bin/env python3
"""Observe actual RV64 course/check/edit/save/cold recovery through raw pen.

The host supplies raw samples and independently observes durable bytes and
controller pixels. It never submits a mathematical answer through an RPC,
constructs guest evidence, or implements live document recovery.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from check_live_notebook import Checker, Input, ROOT, guest_events, idle, require, sha, visible_pixels
from math_oracle import inspect as inspect_math
from store_oracle import recover


class MathChecker(Checker):
    profile = 'lemma-silicon-dev/0.3.0'

    def __init__(self, args):
        require(args.disk.is_file() and args.disk.stat().st_size == 256*1024*1024,
                'provide an initialized real guest 256MiB medium; this checker never formats')
        super().__init__(args)
        self.report['bounds']['disk'] = str(args.disk.resolve())
        self.report.update(schema='lemmasim-guest-exact-course-observations/1',
            scope='actual elaborated Lean RV64 bounded exact course/record/ink workflow; '
                  'managed source language, proof kernel and complete G5–G7 remain unfinished; isolated arithmetic is qualified only by an observed server path',
            medium_source={'path':str(args.disk.resolve()), 'sha256':sha(args.disk)})
        for path in (Path(__file__),ROOT/'conformance/lemmasim/math_oracle.py'):
            self.report['observer_sources'][str(path.relative_to(ROOT))] = sha(path)

    def rows(self, session):
        return guest_events(session.directory/'uart-0.bin')

    def course_rows(self, session):
        return [row for row in self.rows(session) if row[0] == 0x450]

    def settle(self, session, tick, completed=None):
        def done(state):
            commits = [row for row in self.rows(session) if row[0] in (0x421,0x423,0x424)]
            require(not any(row[0] in (0x41f,0x454,0xd4,0xf4) for row in self.rows(session)),
                    'course formatted, rejected its loaded record or faulted')
            return (state['ticks'] >= tick+2000000 and idle(state) and
                    (completed is None or state['devices']['paper']['completed'] > completed) and
                    (not commits or commits[-1][0] == 0x421))
        return session.wait(done,self.args.action_seconds,quantum=1000000)

    def click(self, session, stream, name, x, y, course=True):
        started = time.monotonic()
        before = session.inspect()['machine']
        count = len(self.course_rows(session))
        first = len(stream.events)
        stream.tick = before['ticks']+10000
        stream.sample(x,y,2048,True);stream.sample(x,y,0,False)
        session.admit(stream.events[first:])
        if course:
            session.wait(lambda state: len(self.course_rows(session))>count,
                         self.args.action_seconds,quantum=1000000)
        after = self.settle(session,stream.events[-1][1],before['devices']['paper']['completed'])
        self.report['interactions'].append({'name':name,'raw_pixel':[x,y],
            'first_raw_sequence':first+1,'last_raw_sequence':len(stream.events),
            'initial_cycle':before['cycle'],'final_cycle':after['cycle'],
            'host_seconds':time.monotonic()-started,
            'virtual_seconds':(after['virtual_ns']-before['virtual_ns'])/1000000000})
        return self.course_rows(session)[-1] if course else None

    def press(self, session, stream, name, column, row=3):
        return self.click(session,stream,name,24+column*12+4,160+row*20+5)

    def record(self, medium):
        _,sequence,records = recover(Path(medium).read_bytes())
        require((1,0x8001) in records,'actual guest did not durably publish course record')
        payload = records[1,0x8001].payload
        return payload,inspect_math(payload,1,0x8001),records,sequence

    def label(self, panel, text, x, y):
        # Authored literal rows are independent of the guest's packed font.
        width,height,pixels=visible_pixels(panel)
        patterns={'V':('101','101','101','101','010'),'E':('111','100','110','100','111'),
                  'R':('110','101','110','101','101'),'I':('111','010','010','010','111'),
                  'F':('111','100','110','100','100'),'D':('110','101','101','101','110'),
                  'C':('111','100','100','100','111'),'O':('111','101','101','101','111'),
                  'U':('101','101','101','101','111'),'S':('111','100','111','001','111'),
                  'A':('010','101','111','101','101'),'P':('111','101','111','100','100'),
                  'N':('101','111','111','111','101'),'G':('111','100','101','101','111'),
                  'T':('111','010','010','010','010'),'M':('101','111','111','101','101'),
                  'L':('100','100','100','100','111'),'W':('101','101','101','111','111')}
        for index,char in enumerate(text):
            for row,pattern in enumerate(patterns[char]):
                for col,bit in enumerate(pattern):
                    offset=((y+row*3+1)*width+x+index*12+col*3+1)*3
                    require(pixels[offset:offset+3]==bytes([0 if bit=='1' else 255])*3,
                            text+' label did not reach controller pixels')

    def wait_label(self, session, text, x, y):
        panel=self.directory/(session.directory.name+'-label-wait.ppm')
        def completed(state):
            if not idle(state):return False
            session.control({'action':'panel','path':str(panel)})
            try:self.label(panel,text,x,y)
            except ValueError:return False
            return True
        return session.wait(completed,self.args.action_seconds,quantum=5000000)

    def reuse_live(self):
        origin=self.args.durable_suffix_from.resolve()
        report=json.loads((origin/'result.json').read_text())
        require(report['schema']=='lemmasim-guest-exact-course-observations/1' and
                report['profile']==self.profile and report['status']=='FAIL' and
                report['error']=='closing course lost original full ink display',
                'suffix requires the retained specific footer-observer failure')
        require(report['medium_source']['sha256']==sha(self.args.disk),
                'suffix original medium differs')
        for name in ('verified.ppm','course-final.ppm','closed-course.ppm','ink-baseline.ppm','live/uart-0.bin'):
            require(sha(origin/name)==report['artifacts'][name]['sha256'],
                    'retained real guest artifact changed: '+name)
        original_observer=origin/'original-check_math_session.py'
        require(sha(original_observer)==report['observer_sources']['scripts/check_math_session.py'],
                'retained original observer identity differs')
        rows=guest_events(origin/'live/uart-0.bin')
        require(not any(row[0] in (0xf4,0xd4,0x454,0x41f) for row in rows) and
                rows[-1][0]==0x421 and rows[-1][4]==0x8001,
                'retained guest did not acknowledge actual final mathematical bytes')
        _,verified,_,_=self.record(origin/'verified.raw')
        final_bytes,final,records,_=self.record(origin/'closed-course.raw')
        require(verified==report['verified'] and final==report['final_record'] and
                [entry['outcome'] for entry in final['history']]==[1,2,5,1,4] and final['hints']==1,
                'retained actual semantic workflow differs')
        require(self.record(origin/'course-final.raw')[0]==final_bytes,
                'closing changed acknowledged mathematical bytes')
        _,_,before=recover((origin/'ink-baseline.raw').read_bytes())
        require({key:value.payload for key,value in before.items() if key[1]>0x10000}==
                {key:value.payload for key,value in records.items() if key[1]>0x10000},
                'retained actual raw ink changed')
        self.label(origin/'verified.ppm','VERIFIED',24,260)
        self.label(origin/'course-final.ppm','UNSUPPORTED',24,260)
        self.label(origin/'ink-baseline.ppm','PENDING',24,132)
        self.label(origin/'closed-course.ppm','SAVED',24,132)
        width,height,before_pixels=visible_pixels(origin/'ink-baseline.ppm')
        observed_width,observed_height,after_pixels=visible_pixels(origin/'closed-course.ppm')
        require((width,height)==(observed_width,observed_height),'retained panel dimensions differ')
        for y in range(height):
            if 132<=y<148:
                require(before_pixels[y*width*3:(y*width+24)*3]==after_pixels[y*width*3:(y*width+24)*3] and
                    before_pixels[(y*width+132)*3:(y+1)*width*3]==after_pixels[(y*width+132)*3:(y+1)*width*3],
                    'non-status controller pixels differ')
            else:
                require(before_pixels[y*width*3:(y+1)*width*3]==after_pixels[y*width*3:(y+1)*width*3],
                        'non-status controller pixels differ')
        for key in ('identity','boot','interactions','verified','final_record'):
            self.report[key]=report[key]
        self.report['reused_acknowledged_workflow']={'path':str(origin),'result_sha256':sha(origin/'result.json'),
            'original_status':'FAIL','original_failure':report['error'],
            'independent_correction':'Actual original panel still showed PENDING; actual closed panel shows SAVED. '
                'All pixels outside the status text and all raw ink bytes match exactly. '
                'Verified/unsupported pixels and all immutable mathematical history are independently rechecked.'}
        return sha(self.args.disk),origin/'closed-course.ppm',origin/'closed-course.raw',final_bytes,origin/'course-final.ppm'

    def live_workflow(self):
        disk = self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        original_hash = sha(self.args.disk)
        live = self.session('live',disk);self.report['identity']=live.identity
        self.report['boot']=live.boot()
        stream = Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False)
        stream.stroke('independent raw annotation',1,1,6,1700)
        live.admit(stream.events);self.settle(live,stream.events[-1][1])
        self.wait_label(live,'SAVED',24,132)
        ink_panel,ink_medium = live.export('ink-baseline')
        _,_,ink_records = recover(ink_medium.read_bytes())
        raw_before = {key:record.payload for key,record in ink_records.items() if key[1]>0x10000}
        require(raw_before,'annotation never reached guest ink')
        self.label(ink_panel,'COURSE',288,132)

        self.click(live,stream,'open original course',320,140)
        for _ in range(5):self.press(live,stream,'edit numerator +1',27)
        self.press(live,stream,'select denominator',8)
        for _ in range(5):self.press(live,stream,'edit denominator +1',27)
        checked=self.press(live,stream,'check actual 5/6',1,4)
        require(checked[2:] == (1,1,checked[1]),'5/6 did not produce revision-bound guest Verified')
        self.press(live,stream,'explicit authored local hint',12,4)
        verified_panel,verified_medium=live.export('verified')
        verified_bytes,verified,_,_=self.record(verified_medium)
        require(verified['answer'][:2]==[5,6] and verified['outcome']==1 and verified['hints']==1,
                'typed answer, exact result or explicit assistance differs')
        self.label(verified_panel,'VERIFIED',24,260)
        self.report['verified']=verified

        edited=self.press(live,stream,'edit answer invalidates applicability',27)
        require(edited[3:]==(0,0),'editing retained current trusted applicability')
        if getattr(self.args,'require_execution_identity',False):
            _,edited_medium=live.export('edited-execution')
            _,edited_record,_,_=self.record(edited_medium)
            require(edited_record['outcome']==0 and edited_record['evidence_revision']==0 and
                    edited_record['execution']['active']=={'origin':'Unknown'} and
                    edited_record['history']==verified['history'] and
                    edited_record['execution']['history']==verified['execution']['history'],
                    'actual edit retained applicable execution or changed immutable attempt identity')
            self.report['edited_execution_applicability']={'status':'PASS','active_unknown':True,
                'old_attempt_identity_preserved':True,'actual_durable_guest_record':True}
        self.press(live,stream,'check actual invalid 5/7',1,4)
        self.press(live,stream,'bounded resource zero',17,4)
        self.press(live,stream,'check Indeterminate',1,4)
        self.press(live,stream,'next polynomial goal',7,4)
        self.press(live,stream,'restore arithmetic budget',17,4)
        self.press(live,stream,'select polynomial constant',10)
        self.press(live,stream,'constant +1',27)
        self.press(live,stream,'select polynomial linear term',13)
        self.press(live,stream,'linear +1',27)
        self.press(live,stream,'linear +1',27)
        self.press(live,stream,'select polynomial quadratic term',16)
        self.press(live,stream,'quadratic +1',27)
        polynomial=self.press(live,stream,'check actual polynomial identity',1,4)
        require(polynomial[2:]==(2,1,polynomial[1]),'actual polynomial identity was not guest Verified')
        self.press(live,stream,'next unsupported goal',7,4)
        unsupported=self.press(live,stream,'check Unsupported',1,4)
        require(unsupported[2]==3 and unsupported[3]==4,'unsupported goal was fabricated successful')
        # The guest emits its barrier receipt before publishing the Saved
        # footer. An older completed course refresh is insufficient: require
        # the actual controller-produced Saved frame within the same bound.
        before_saved=live.inspect()['machine']
        provisional_panel,provisional_medium=live.export('course-before-saved')
        provisional_bytes=self.record(provisional_medium)[0]
        already_saved=True
        try:self.label(provisional_panel,'SAVED',24,132)
        except ValueError:
            already_saved=False
            self.label(provisional_panel,'PENDING',24,132)
        after_saved=self.wait_label(live,'SAVED',24,132)
        if not already_saved:
            require(after_saved['devices']['paper']['completed']>before_saved['devices']['paper']['completed'],
                    'Saved footer did not complete a new controller refresh')
        active_panel,medium=live.export('course-final')
        final_bytes,final,records,sequence=self.record(medium)
        require(final_bytes==provisional_bytes,'Saved status publication changed acknowledged mathematical bytes')
        if not already_saved:
            w,h,before_pixels=visible_pixels(provisional_panel)
            aw,ah,after_pixels=visible_pixels(active_panel)
            require((w,h)==(aw,ah),'status publication changed controller dimensions')
            for y in range(h):
                for x in range(w):
                    if 24<=x<132 and 132<=y<148:continue
                    at=(y*w+x)*3
                    require(before_pixels[at:at+3]==after_pixels[at:at+3],
                            'status publication changed course or ink controller pixels')
        self.report['saved_status_publication']={'status':'PASS','observed_pending_after_barrier':not already_saved,
            'before_completed':before_saved['devices']['paper']['completed'],
            'after_completed':after_saved['devices']['paper']['completed'],
            'virtual_ticks':after_saved['ticks']-before_saved['ticks'],
            'acknowledged_math_unchanged':True,'original_action_seconds':self.args.action_seconds}
        require([entry['outcome'] for entry in final['history']]==[1,2,5,1,4] and final['hints']==1,
                'verified/invalid/limited/unsupported history or assistance differs')
        require({key:record.payload for key,record in records.items() if key[1]>0x10000}==raw_before,
                'mathematical course changed original raw ink')
        if getattr(self.args,'require_execution_identity',False):
            require(final['format']=='lemma-mathematical-submission/3' and 'execution' in final,
                    'new execution authority requires actual2496-byte v3 record')
            metadata=final['execution']['history'][:final['attempts']]
            require(len(metadata)==5 and all(entry['origin']=='IsolatedManaged' and entry['status']==0 for entry in metadata),
                    'new attempts lack exact isolated implementation/resource identity')
            requests=[row for row in self.rows(live) if row[0]==0x459]
            replies=[row for row in self.rows(live) if row[0]==0x455]
            require(len(requests)==len(replies)==len(metadata),'actual isolated request/reply count differs from durable history')
            for attempt,entry,request,reply in zip(final['history'],metadata,requests,replies):
                require((request[1],request[2],request[3])==(entry['request'],attempt['revision'],attempt['goal']) and
                        (reply[1],reply[2],reply[3],reply[4])==(entry['request'],attempt['revision'],0,attempt['outcome']),
                        'durable execution request/revision/resource outcome differs from actual server')
                require(entry['budget']==attempt['budget'],'durable resource budget differs')
            require(any(row[0]==0x45c and tuple(row[1:])==(0x0002000100000001,0x0002000000000001,
                    0x0001000000000001,0x000100000000001f) for row in self.rows(live)),
                    'actual isolated server did not report exact named execution contracts')
            require(final['execution']['active']==metadata[-1],'current execution applicability differs')
            self.report['execution_identity']={'status':'PASS','format_bytes':len(final_bytes),
                'actual_isolated_requests':len(requests),'actual_request_revision_outcome_bound':True,
                'known_attempts':len(metadata),'identity_kind':'closed implementation-version authority; not artifact hash',
                'semantic_and_heap_resources_separate':True}
        self.report['final_record']=final
        self.click(live,stream,'close course restores raw notebook',320,140,False)
        self.wait_label(live,'SAVED',24,132)
        restored_panel,restored_medium=live.export('closed-course')
        require(visible_pixels(ink_panel)==visible_pixels(restored_panel),'closing course lost original full ink display')
        require(self.record(restored_medium)[0]==final_bytes,'closing changed acknowledged mathematical bytes')
        live.close();self.sessions.remove(live)

        return original_hash,restored_panel,restored_medium,final_bytes,active_panel

    def execute(self):
        if self.args.durable_suffix_from:
            original_hash,restored_panel,restored_medium,final_bytes,active_panel=self.reuse_live()
        else:
            original_hash,restored_panel,restored_medium,final_bytes,active_panel=self.live_workflow()
        cold_disk=self.directory/'cold-input.raw';shutil.copyfile(restored_medium,cold_disk)
        cold=self.session('cold',cold_disk);self.report['cold_boot']=cold.boot()
        require(cold.identity==self.report['identity'],'cold machine changed the admitted artifact identities')
        self.wait_label(cold,'SAVED',24,132)
        cold_panel,cold_medium=cold.export('cold-notebook')
        require(visible_pixels(cold_panel)==visible_pixels(restored_panel),'independent cold notebook display differs')
        cold_stream=Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        cold_stream.sample(825,160,0,False);cold.admit(cold_stream.events)
        self.click(cold,cold_stream,'cold reopen actual durable course',320,140)
        reopened_panel,reopened_medium=cold.export('cold-course')
        require(self.record(reopened_medium)[0]==final_bytes and visible_pixels(reopened_panel)==visible_pixels(active_panel),
                'cold recovered course bytes or complete controller display differs')
        self.report['cold_recovery']={'status':'PASS','actual_new_cpu':True,
            'math_sha256':hashlib.sha256(final_bytes).hexdigest(),
            'complete_controller_pixels':True,'raw_ink_preserved':True}
        cold.close();self.sessions.remove(cold)

        failed_disk=self.directory/'failed-input.raw';shutil.copyfile(restored_medium,failed_disk)
        failed=self.session('failed',failed_disk,1);failed.boot()
        failed_stream=Input(1650,2200,failed.inspect()['machine']['ticks']+10000,100000,0)
        failed_stream.sample(825,160,0,False);failed.admit(failed_stream.events)
        self.click(failed,failed_stream,'open before failed save',320,140)
        first=len(failed_stream.events);failed_stream.tick=failed.inspect()['machine']['ticks']+10000
        failed_stream.sample(24+27*12+4,225,2048,True);failed_stream.sample(24+27*12+4,225,0,False)
        failed.admit(failed_stream.events[first:])
        failed.wait(lambda state:any(row[0]==0x424 for row in self.rows(failed)) and idle(state),self.args.action_seconds)
        # Failure publication follows its diagnostic receipt just as Saved
        # does. Require the controller's actual Failed footer within the
        # original bound, rather than a still-visible previous Saved frame.
        failure_frame=self.wait_label(failed,'FAILED',24,132)
        _,failed_medium=failed.export('failed-save')
        require(self.record(failed_medium)[0]==final_bytes and
            not any(row[0]==0x421 for row in self.rows(failed)), 'failed course barrier fabricated Saved or changed acknowledged record')
        self.report['failed_save']={'status':'PASS','no_false_saved':True,'acknowledged_math_unchanged':True,
            'actual_failed_controller_label':True,'completed':failure_frame['devices']['paper']['completed']}
        failed.close();self.sessions.remove(failed)
        require(sha(self.args.disk)==original_hash,'checker mutated original user medium')
        self.report['status']='PASS'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--native-bundle',help='Validated immutable native runtime bundle for every public session')
    parser.add_argument('--guest-build',help='Current genuinely compiled and audited notebook guest; requires native bundle')
    parser.add_argument('--require-execution-identity',action='store_true',help='Require actual protocol2 request/reply identities in every new durablev3 attempt')
    parser.add_argument('--durable-suffix-from',type=Path,help='Reuse independently rechecked actual acknowledged course workflow; run only new cold/failure CPUs')
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--boot-seconds',type=int,default=60)
    parser.add_argument('--action-seconds',type=int,default=30)
    parser.add_argument('--deadline',type=int,default=2400)
    args=parser.parse_args();args.checkpoint_relation='not-exercised'
    require(not args.guest_build or args.native_bundle,'guest-build requires native-bundle')
    require(not args.require_execution_identity or not args.durable_suffix_from,'execution identities require actual new live requests')
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600
            and 1<=args.deadline<=7200,'invalid declared resource bounds')
    checker=MathChecker(args)
    try:checker.execute()
    except BaseException as error:
        checker.report['error']=str(error)
        raise
    finally:checker.close()
    print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))


if __name__=='__main__':main()
