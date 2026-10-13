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
import re
import shutil
import struct
import time
from check_math_session import MathChecker
from check_live_notebook import Input,idle,require,sha,visible_pixels
from store_oracle import recover

MANAGED_OOM_CONFIGURATION='lemmasim-silicon-power-arithmetic-oom-development'

def managed_oom_route(unit,ir):
    """Inspect real emitted calls independently of target events and catalog labels.

    The whole image still passes its ordinary strict audit at public startup.
    This observer additionally refuses to call a scalar allocation failure a
    managed constructor failure. It does not execute or interpret target code.
    """
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    require(unit.get('contract_version')=='core0-user-v0.2' and
            unit.get('role')=='user' and unit.get('image_key')=='arithmetic' and
            unit.get('configuration')==MANAGED_OOM_CONFIGURATION,
            'managed OOM requires the exact User2 Arithmetic Laboratory unit')
    names={r['source']:r['symbol'] for r in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),
            'duplicate emitted source or symbol identity')
    def suffix(name):
        rows=[s for s in names if s.endswith(name)]
        require(len(rows)==1,'missing or ambiguous managed OOM source: '+name)
        return rows[0]
    p='Lemma.User.Runtime.Arena.';m='Lemma.User.Runtime.ManagedRecords.'
    entry='Lemma.Mathematics.ManagedRational.compareFiveSix'
    generated=entry+'.__lemma_managed_v02.'
    main='Lemma.Services.Arithmetic.Server.main'
    step=suffix('Lemma.Services.Arithmetic.Server.step')
    process=suffix('Lemma.Services.Arithmetic.Server.process')
    pressure=suffix('Lemma.Services.Arithmetic.Server.pressureStep')
    positive=suffix('Lemma.Mathematics.ManagedSubmission.positiveRational')
    allocate=suffix('Lemma.User.Runtime.Arena.allocate')
    routes=[(main,step),(step,process),(process,'Lemma.Mathematics.ManagedSubmission.check'),
      ('Lemma.Mathematics.ManagedSubmission.check',positive),
      (positive,generated+entry),(generated+entry,generated+'Lemma.Mathematics.ManagedRational.make'),
      (generated+'Lemma.Mathematics.ManagedRational.make',m+'allocate'),
      (m+'allocate',p+'newBytes'),(p+'newBytes',allocate),
      (main,pressure),(pressure,p+'newBox'),(p+'newBox',allocate),(allocate,p+'exhausted')]
    required={s for pair in routes for s in pair}|{p+'capacity'}
    require(required<=set(names),'managed OOM emitted constructor/runtime closure missing')
    bodies={s:_ir_definition_body(ir,names[s]) for s in required}
    require(all(body is not None for body in bodies.values()),'managed OOM emitted function body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
                'managed OOM emitted call route missing: '+caller+' -> '+callee)
    def call(caller,callee,args):
        require(len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[callee])+r'\('+args+r'\)',bodies[caller]))==1,
                'managed OOM constructor/helper arguments differ: '+caller)
    call(generated+'Lemma.Mathematics.ManagedRational.make',m+'allocate',r'i64 1, i64 24')
    call(m+'allocate',p+'newBytes',r'i64 %arg1')
    call(positive,generated+entry,r'i64 %arg0, i64 %arg1')
    require(re.search(r'icmp eq i64 %arg0, 1',bodies['Lemma.Mathematics.ManagedSubmission.check']) and
            re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
            re.search(r'i32 signext 31, i64',bodies[main]) and
            re.search(r'icmp eq i64 %arg0, 1',bodies[main]),
            'managed OOM exact goal/budget/pressure mode path differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[p+'exhausted']) and
            re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[p+'capacity']),
            'managed OOM arena capacity/exhaustion code differs')
    return {'contract':'core0-user-v0.2','constructor':'Lemma.Mathematics.ManagedRational.Fraction.mk',
      'shape':1,'bytes':24,'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

SUMS_OOM_CONFIGURATION='lemmasim-silicon-sums-arithmetic-oom-development'

def sums_oom_route(unit,ir):
    from audit_kernel import _ir_definition_body,parse_definitions_and_calls
    from managed_sums import validate as validate_sums
    require(unit.get('contract_version')=='core0-user-v0.3' and unit.get('role')=='user' and
      unit.get('image_key')=='arithmetic' and unit.get('configuration')==SUMS_OOM_CONFIGURATION,
      'sum OOM requires the exact User3 isolated Laboratory unit')
    require(validate_sums(ir,unit,optimized=False) is not None,'ordinary sum/tag/layout closure absent')
    names={row['source']:row['symbol'] for row in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),'duplicate emitted source/symbol')
    def suffix(name):
        matches=[source for source in names if source.endswith(name)]
        require(len(matches)==1,'missing or ambiguous sum OOM source: '+name)
        return matches[0]
    server='Lemma.Services.Arithmetic.ServerV3.';p='Lemma.User.Runtime.Arena.'
    m='Lemma.User.Runtime.ManagedSums.';source='Lemma.Mathematics.ManagedResult.'
    entry=source+'compareFiveSix';generated=entry+'.__lemma_managed_sums_v03.'
    main=server+'main';step=suffix(server+'step');process=suffix(server+'processV3')
    pressure=suffix(server+'pressureStep');submission='Lemma.Mathematics.ManagedSumSubmission.'
    positive=suffix(submission+'positiveRational');allocate=suffix(p+'allocate')
    routes=[(main,step),(step,process),(process,submission+'check'),(submission+'check',positive),
      (positive,generated+entry),(generated+entry,generated+source+'compare'),
      (generated+source+'compare',m+'allocate'),(m+'allocate',p+'newBytes'),
      (p+'newBytes',allocate),(main,pressure),(pressure,p+'newBox'),
      (p+'newBox',allocate),(allocate,p+'exhausted')]
    required={source for pair in routes for source in pair}|{p+'capacity'}
    require(required<=set(names),'sum OOM constructor/runtime path missing')
    bodies={source:_ir_definition_body(ir,names[source]) for source in required}
    require(all(body is not None for body in bodies.values()),'sum OOM emitted body missing')
    for caller,callee in routes:
        require(names[callee] in parse_definitions_and_calls(bodies[caller])[2],
                'sum OOM emitted route missing: '+caller+' -> '+callee)
    require(re.search(r'icmp eq i64 %arg0, 1',bodies[submission+'check']) and
      re.search(r'icmp ult i64 %arg2, 8',bodies[positive]) and
      re.search(r'i32 signext 31, i64',bodies[main]) and
      re.search(r'icmp eq i64 %arg0, 1',bodies[main]),'sum OOM goal/budget/pressure mode differs')
    require(re.fullmatch(r'\s*entry:\s*ret i8 237\s*',bodies[p+'exhausted']) and
      re.fullmatch(r'\s*entry:\s*ret i64 31\s*',bodies[p+'capacity']),
      'sum OOM actual capacity/failure differs')
    return {'contract':'core0-user-v0.3','constructor':'Lemma.Mathematics.ManagedResult.Comparison.unequal',
      'shape':1,'tag':1,'bytes':16,'arena_capacity':31,'actual_failure_code':237,
      'emitted_routes':[list(pair) for pair in routes]}

def managed_oom_artifacts(directory,*,sums=False):
    from managed_records import validate as validate_records
    if sums:
        from managed_sums import validate as validate_records
    configuration=SUMS_OOM_CONFIGURATION if sums else MANAGED_OOM_CONFIGURATION
    server='Lemma.Services.Arithmetic.ServerV3' if sums else 'Lemma.Services.Arithmetic.Server'
    directory=Path(directory).resolve();arithmetic=directory/'users/arithmetic'
    unit=json.loads((arithmetic/'unit.json').read_text())
    catalog=json.loads((directory/'user-image-catalog.json').read_text())
    audit=json.loads((directory/'audit.json').read_text())
    expected={'id':3,'key':'arithmetic','directory':'users/arithmetic',
      'source':server+'.main','module':server,
      'boot_role':'arithmetic-server','args':['u64']}
    rows=[r for r in catalog.get('images',[]) if r.get('key')=='arithmetic']
    require(catalog.get('configuration')==configuration and
            catalog.get('stage')=='supervisor' and len(rows)==1 and
            all(rows[0].get(k)==v for k,v in expected.items()),
            'managed OOM exact separately linked Arithmetic catalog differs')
    require(audit.get('status')=='PASS' and audit.get('configuration')==configuration and
            audit.get('image_sha256')==sha(directory/'image.elf') and
            audit['user_images']['arithmetic']['image_sha256']==sha(arithmetic/'image.elf'),
            'managed OOM requires the exact audited combined and Arithmetic ELF bytes')
    pre=(arithmetic/'program.ll').read_text();optimized=(arithmetic/'program.opt.ll').read_text()
    require(validate_records(pre,unit,optimized=False) is not None and
            validate_records(optimized,unit,optimized=True) is not None,
            'managed OOM genuine ordinary source/checked helper closure absent')
    result=sums_oom_route(unit,pre) if sums else managed_oom_route(unit,pre)
    files=[directory/'audit.json',directory/'image.elf',directory/'user-image-catalog.json',
      arithmetic/'image.elf',arithmetic/'unit.json',arithmetic/'program.ll',arithmetic/'program.opt.ll']
    result['artifacts']={str(p.relative_to(directory)):sha(p) for p in files}
    return result

class IsolationChecker(MathChecker):
    def __init__(self,args):
        super().__init__(args)
        self.allowed_error=False
        self.report.update(schema='lemmasim-arithmetic-isolation/1',case=args.case,
            scope='actual scalar Lean isolated arithmetic process and copied IPC; managed source constructors/proof kernel/full verifier remain unfinished')
        self.report['observer_sources']['scripts/check_arithmetic_isolation.py']=sha(Path(__file__))
        if args.require_managed_constructor or args.require_sums_constructor:
            self.report['scope']='actual ordinary Lean payload constructor OOM in isolated RV64 Arithmetic; bounded checked heap, pen/Save/cold recovery; general managed language/proof kernel remain unfinished'
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
        if self.args.require_managed_constructor or self.args.require_sums_constructor:
            self.report['managed_constructor_admission']=managed_oom_artifacts(self.args.guest_build,sums=self.args.require_sums_constructor)
        original=sha(self.args.disk);disk=self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        live=self.session('live',disk);self.report['identity']=live.identity
        if self.args.require_managed_constructor or self.args.require_sums_constructor:
            require(live.identity['guest']==self.report['managed_constructor_admission']['artifacts']['image.elf'],
                    'live machine did not consume the admitted managed OOM ELF')
        self.report['boot']=live.boot()
        rows=self.rows(live);mode={'oom':1,'fault':2,'stall':3}[self.args.case]
        start=[r for r in rows if r[0]==0x456]
        require(start==[(0x456,mode,31 if mode==1 else 0,3 if self.args.require_sums_constructor else 1,10000000)],'server did not execute actual declared mode/object pressure/deadline')
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events)
        self.click(live,stream,'open course before isolated fault',320,140)
        prior_panel,prior_medium=live.export('before-check')
        prior_bytes,prior,_,_=self.record(prior_medium)
        require(prior['outcome']==0 and not prior['history'],'initial course already had manufactured evidence')
        if self.args.require_managed_constructor or self.args.require_sums_constructor:
            require(prior['goal']==1 and prior['answer']==[0,1,0,0,0] and prior['budget']==8,
                    'managed OOM submitted object would not execute the admitted ordinary constructor')
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
            if self.args.require_managed_constructor or self.args.require_sums_constructor:
                result_rows=[r for r in self.rows(live) if r[0]==0x455 and r[1:3]==request[1:3]]
                require(len(result_rows)==1 and result_rows[0][3:]==(237,0),
                        'managed constructor OOM reply is not the actual submitted request/revision')
                self.report['managed_constructor_failure']={'status':'PASS','actual_status':237,
                  'goal':prior['goal'],'answer':prior['answer'],'budget':prior['budget'],
                  'actual_server_reply':result_rows[0],'live_slots':31,'no_evidence':True,'record_unchanged':True}
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
        if self.args.require_managed_constructor or self.args.require_sums_constructor:
            require(all(sha(Path(self.args.guest_build)/name)==digest for name,digest in
                        self.report['managed_constructor_admission']['artifacts'].items()),
                    'admitted managed OOM artifacts changed during real observations')
        self.report['status']='PASS'
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('oom','fault','stall'),required=True)
    parser.add_argument('--disk',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--native-bundle',required=True);parser.add_argument('--guest-build',required=True)
    parser.add_argument('--require-managed-constructor',action='store_true',
        help='fail unless exact User2 Lab artifact and emitted real constructor allocator path qualify OOM')
    parser.add_argument('--require-sums-constructor',action='store_true',
        help='fail unless exact User3 Lab artifact and genuine sum tags/layout/allocator path qualify OOM')
    parser.add_argument('--timeout',type=int,default=300);parser.add_argument('--boot-seconds',type=int,default=60)
    parser.add_argument('--action-seconds',type=int,default=30);parser.add_argument('--deadline',type=int,default=1200)
    args=parser.parse_args();args.checkpoint_relation='not-exercised';args.durable_suffix_from=None
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600 and 1<=args.deadline<=2400,'invalid predeclared resource bounds')
    require(not (args.require_managed_constructor and args.require_sums_constructor),'select one exact managed constructor contract')
    require(not (args.require_managed_constructor or args.require_sums_constructor) or args.case=='oom','managed constructor admission requires the OOM case')
    checker=IsolationChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:checker.close()
    print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))
if __name__=='__main__':main()
