#!/usr/bin/env python3
"""Exercise guest number entry, real isolated checking and independent cold recovery.

Raw pen input only; exported bytes/pixels are passive independent observations.
Fast functional units do not establish canonical RTL timing or cached-state parity.
"""
import argparse,filecmp,json,os,resource,shutil,struct
from pathlib import Path
from check_course_math_workflow import CourseMathWorkflow,Input,decode,idle,require,visible_pixels,T,sha
from number_pad_reference import pad_matches

class NumberEntryWorkflow(CourseMathWorkflow):
    def execute(self):
        disk=self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        live=self.session('live',disk)
        require(live.inspect()['machine']['cycle']==0,'new CPU must start at reset')
        self.report.update(schema='lemma-number-entry-workflow/1',scope=__doc__,identity=live.identity)
        self.phase(live,'new-cold-Ready',1000000000,lambda st:idle(st)and st['panel_completed']>=1 and any(r[0]==1056 for r in self.rows(live)))
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        package=decode(self.packages[0])
        panel=self.click(live,stream,'COURSEactualpackage',320,140,text=package['nodes'][0]['body'])
        require(pad_matches(panel,False),'independent initial keypad pixels differ')
        for index in (1,2):self.click(live,stream,'authored-node-'+str(index),72,650,text=package['nodes'][index]['body'])
        self.click(live,stream,'USE-original-goal',360,650,mutation=True)
        self.click(live,stream,'numeric-5',640,260,mutation=True)
        self.click(live,stream,'select-D',124,225,mutation=True)
        self.click(live,stream,'clear-D',512,340,mutation=True)
        zero=self.checkpoint_record(live,'typed-zero-denominator')
        require(zero[3]['document']['answer'][:2]==[5,0]and zero[3]['document']['outcome']==0,'zero denominator gained evidence')
        zero_checked=self.check(live,stream,'actual-zero-denominator-Invalid',2)
        T.observe_transition(zero[3],zero_checked[3],'known-check')
        self.click(live,stream,'numeric-6',768,260,mutation=True)
        before=self.checkpoint_record(live,'before-check')
        verified=self.check(live,stream,'actual-5over6-Verified',1)
        require(verified[3]['document']['answer'][:2]==[5,6],'numeric entry did not construct5/6')
        T.observe_transition(before[3],verified[3],'known-check')
        self.click(live,stream,'append-9-to-D',768,300,mutation=True)
        edited=self.checkpoint_record(live,'edited-5over69')
        require(edited[3]['document']['answer'][:2]==[5,69],'decimal append differs')
        T.observe_transition(verified[3],edited[3],'edit')
        invalid=self.check(live,stream,'actual-5over69-Invalid',2)
        T.observe_transition(edited[3],invalid[3],'known-check')
        before_limit=self.checkpoint_record(live,'before-overflow')
        checks=len([r for r in self.rows(live)if r[0]==1113]);acks=len([r for r in self.rows(live)if r[0]==1057])
        panel=self.click(live,stream,'overflow-699-rejected',768,300)
        live.control({'action':'panel','path':str(panel)})
        require(pad_matches(panel,True),'guest did not render independent LIMIT99 pixels')
        limited=self.checkpoint_record(live,'after-overflow')
        require(limited[2]==before_limit[2]and filecmp.cmp(limited[1],before_limit[1],shallow=False),'overflow changed durable document/revision')
        require(len([r for r in self.rows(live)if r[0]==1113])==checks and len([r for r in self.rows(live)if r[0]==1057])==acks,'overflow invented checking or Saved')
        self.click(live,stream,'BACK-D-to6',768,340,mutation=True)
        restored=self.checkpoint_record(live,'backspaced')
        require(restored[3]['document']['answer'][:2]==[5,6]and restored[3]['document']['outcome']==0,'backspace retained stale evidence')
        again=self.check(live,stream,'actual-restored-Verified',1)
        T.observe_transition(restored[3],again[3],'known-check')
        self.click(live,stream,'authored-local-hint',172,245,mutation=True)
        assisted=self.checkpoint_record(live,'assisted')
        require(assisted[3]['document']['hints']==1,'assistance was not durably recorded')
        first=len(stream.events);stream.tick=live.inspect()['machine']['ticks']+10000
        stream.stroke('numeric-postcheck-ink',1,1,6,1900);live.admit(stream.events[first:])
        oldacks=len([r for r in self.rows(live)if r[0]==1057])
        self.phase(live,'actual-postcheck-raw-ink-Saved',300000000,lambda st:idle(st)and self.saved(live)and len([r for r in self.rows(live)if r[0]==1057])>oldacks and st['ticks']>=stream.events[-1][1]+200000)
        ink=self.checkpoint_record(live,'postcheck-ink');samples=[]
        for record in ink[4].values():
            if len(record.payload)>=128 and struct.unpack_from('<Q',record.payload)[0]==3552018807646930252 and struct.unpack_from('<Q',record.payload,16)[0]==3:
                count=struct.unpack_from('<Q',record.payload,48)[0]
                samples.extend(struct.unpack_from('<9Q',record.payload,128+i*72)for i in range(count))
        require(all(tuple(row)in samples for row in stream.events[first:]),'postcheck raw fields absent from guest durable ink')
        _,tick=self.raw(live,stream,320,140);old=live.inspect()['machine']['panel_completed']
        self.phase(live,'close-course',500000000,lambda st:idle(st)and self.saved(live)and st['panel_completed']>old and st['ticks']>=tick+25000000)
        panel,medium=live.export('closed-final');payload,record,records,sequence=self.record(medium)
        expected=visible_pixels(panel);live.close();self.sessions.remove(live)
        cold_disk=self.directory/'cold-input.raw';shutil.copyfile(medium,cold_disk)
        cold=self.session('cold',cold_disk);require(cold.inspect()['machine']['cycle']==0,'independent cold CPU not atreset')
        observed=self.directory/'cold-observed.ppm'
        def recovered(st):
            if not idle(st)or not any(r[0]==1056 for r in self.rows(cold)):return False
            cold.control({'action':'panel','path':str(observed)})
            return visible_pixels(observed)==expected
        self.phase(cold,'independent-new-CPU-cold-all-pixels',1000000000,recovered)
        cp,cm=cold.export('cold-final')
        require(visible_pixels(cp)==expected and filecmp.cmp(medium,cm,shallow=False),'cold plane/complete medium differs')
        require({k:r.payload for k,r in self.record(cm)[2].items()}=={k:r.payload for k,r in records.items()},'cold lost acknowledged objects')
        stream=Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        prior_checks=len([r for r in self.rows(cold)if r[0]==1113])
        panel=self.click(cold,stream,'cold-reopen-installed-body',320,140,text=package['nodes'][0]['body'])
        require(pad_matches(panel,False),'cold keypad was not reconstructed by guest')
        reopened=self.checkpoint_record(cold,'cold-reopened')
        require(reopened[2]==payload and filecmp.cmp(medium,reopened[1],shallow=False),'reopen changed acknowledged mathematics/history')
        require(len([r for r in self.rows(cold)if r[0]==1113])==prior_checks,'reopen manufactured a checking attempt')
        require(sha(self.args.disk)==self.original_medium_sha256,'original user medium changed')
        self.report.update(status='PASS_GUEST_NUMBER_ENTRY_CHECKING_COLD',numeric_entry=True,real_isolated_checks=['Invalid5/0','Verified5/6','Invalid5/69','Verified5/6'],overflow='unchanged durable bytes/no checking/no Saved',independent_cold={'all_controller_pixels_exact':True,'all_medium_bytes_exact':True,'all_objects_exact':True},hint_scope='authored local material; not live tutor')

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--disk',type=Path,required=True);p.add_argument('--package',action='append',type=Path,required=True)
    p.add_argument('--native-bundle',required=True);p.add_argument('--guest-build',required=True)
    p.add_argument('--guest-source-root',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True)
    a=p.parse_args();a.disk=a.disk.resolve();a.package=[x.resolve()for x in a.package]
    require(not a.work_dir.exists(),'unused output required');a.timeout=120;a.deadline=900;a.checkpoint_relation='independent cold only';a.durable_suffix_from=None
    os.environ['LEAN_NUM_THREADS']='2';resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
    actor=NumberEntryWorkflow(a)
    try:actor.execute()
    except BaseException as error:actor.report.update(status='FAIL',error=repr(error));raise
    finally:actor.close()
    print(actor.report['status'],actor.cycles,actor.report['elapsed_seconds'])
if __name__=='__main__':main()
