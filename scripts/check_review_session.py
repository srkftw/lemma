#!/usr/bin/env python3
"""Real guest historical migration, exact-assisted review and cold reopen.

Input must be the actual acknowledged course medium, never a host-constructed
learner record. Raw pen drives every guest edit and protocol transaction.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from check_math_session import MathChecker
from check_live_notebook import Input, idle, require, sha, visible_pixels


class ReviewChecker(MathChecker):
    def execute(self):
        original_hash=sha(self.args.disk)
        original_bytes,original,_,_=self.record(self.args.disk)
        require(original['format']=='lemma-mathematical-submission/'+str(self.args.source_record_version) and
                [entry['outcome'] for entry in original['history']]==[1,2,5,1,4] and original['hints']==1,
                'provide the retained actually acknowledged declared course workflow')
        self.report['schema']='lemmasim-guest-offline-review-observations/1'
        self.report['scope']='guest historical migration and bounded original offline review with uncertain understanding; no learning-gain or complete learner/tutor claim'
        self.report['declared_record_versions']={'source':self.args.source_record_version,
            'target':self.args.record_version}
        self.report['observer_sources']['scripts/check_review_session.py']=sha(Path(__file__))
        self.report['source_submission_sha256']=hashlib.sha256(original_bytes).hexdigest()
        disk=self.directory/'live-input.raw';shutil.copyfile(self.args.disk,disk)
        live=self.session('live',disk);self.report['identity']=live.identity;self.report['boot']=live.boot()
        self.wait_label(live,'SAVED',24,132)
        baseline_panel,baseline_medium=live.export('baseline')
        stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
        stream.sample(825,160,0,False);live.admit(stream.events)
        self.click(live,stream,'guest migrate actual historical course',320,140)
        _,migrated_medium=live.export('migrated')
        _,migrated,_,_=self.record(migrated_medium)
        require(migrated['format']=='lemma-mathematical-submission/'+str(self.args.record_version) and
                migrated['history']==original['history'] and migrated['answer']==original['answer'],
                'guest migration lost exact evidence or typed answer')
        if self.args.source_record_version==1:
            require(migrated['learner']['events'][-1]['kind']==6 and migrated['learner']['events'][-1]['value']==1,
                    'guest migration invented old anchored hint events')
        else:
            require(migrated['learner']==original['learner'],'v2 migration changed durable learner events/policy')
        if self.args.record_version in (3,4,5):
            if self.args.source_record_version in (3,4):
                require(self.args.record_version==self.args.source_record_version+1 and migrated['execution']==original['execution'],
                        'v3 migration relabeled old exact implementation/history')
            else:
                require(migrated['execution']['active']=={'origin':'Unknown'} and
                        all(entry=={'origin':'Unknown'} for entry in migrated['execution']['history']),
                        'migration invented old compiled execution or request identity')
        self.report['migration']=migrated
        self.press(live,stream,'return to fractions',7,4)
        self.press(live,stream,'select denominator',8)
        self.press(live,stream,'actual denominator7to6',21)
        checked=self.press(live,stream,'check actual assisted5/6',1,4)
        require(checked[2:]==(1,1,checked[1]),'assisted answer did not get exact revision-bound evidence')
        _,checked_medium=live.export('assisted')
        _,checked_record,_,_=self.record(checked_medium)
        require(checked_record['learner']['recommendation']=='practice' and
                checked_record['learner']['reason']=='assisted' and checked_record['learner']['understanding']=='uncertain',
                'baseline confused an assisted exact attempt with demonstrated understanding')
        if self.args.record_version in (3,4,5):
            execution=checked_record['execution']
            require(execution['active']['origin']==({3:'IsolatedManaged',4:'IsolatedSums',5:'IsolatedBytes'}[self.args.record_version]) and execution['active']['status']==0 and
                    execution['history'][len(original['history'])]==execution['active'] and
                    execution['history'][:len(original['history'])]==(original['execution']['history'][:len(original['history'])] if self.args.source_record_version in (3,4) else [{'origin':'Unknown'}]*len(original['history'])),
                    'new execution relabeled historical identities or lost current request')
            replies=[row for row in self.rows(live) if row[0]==0x455]
            require(len(replies)==1 and replies[0][1:]==(execution['active']['request'],checked_record['revision'],0,1),
                    'new migrated-record execution differs from actual isolated reply')
            self.report['execution_migration']={'status':'PASS','old_attempts_preserved':len(original['history']),'old_origin':original.get('execution',{}).get('active',{'origin':'Unknown'})['origin'],
                'new_attempt_known':True,'actual_request_revision_outcome_bound':True}
        for mode in range(1,5):
            self.press(live,stream,'explicit review mode'+str(mode),23,4)
            panel,medium=live.export('mode'+str(mode))
            _,record,_,_=self.record(medium)
            require(record['learner']['mode']==mode and record['outcome']==1 and
                    record['evidence_revision']==checked_record['evidence_revision'],
                    'override or disable changed submitted mathematical authority')
            self.label(panel,'REVIEW' if mode==4 else 'MANUAL',24,300)
        self.press(live,stream,'restore offline automatic review',23,4)
        # The barrier diagnostic precedes the Saved footer. Require its
        # actual controller pixels before comparing the independent cold
        # display, as for the original course workflow.
        self.wait_label(live,'SAVED',24,132)
        active_panel,active_medium=live.export('auto-review')
        final_bytes,final,records,_=self.record(active_medium)
        require(final['learner']['mode']==0 and final['learner']['recommendation']=='practice' and
                final['learner']['reason']=='assisted' and final['learner']['show_reason'] and
                [event['value'] for event in final['learner']['events'] if event['kind']==3]==[1,2,3,4,0],
                'ordered overrides/disable/automatic restoration were not durably retained')
        self.label(active_panel,'AUTO',24,300)
        self.label(active_panel,'UNCERTAIN',192,300)
        self.label(active_panel,'ASSISTED',24,280)
        if self.args.record_version in (3,4,5):
            require(final['execution']==checked_record['execution'],
                    'policy override/disable relabeled mathematical execution authority')
        self.report['learner']=final['learner']
        self.click(live,stream,'close course through COURSE',320,140,False)
        self.wait_label(live,'SAVED',24,132)
        closed_panel,closed_medium=live.export('closed')
        require(visible_pixels(closed_panel)==visible_pixels(baseline_panel),'review workflow changed complete raw notebook display')
        _,_,raw_before,_=self.record(baseline_medium)
        require({key:value.payload for key,value in records.items() if key[1]>0x10000}==
                {key:value.payload for key,value in raw_before.items() if key[1]>0x10000},'review changed original raw ink')
        live.close();self.sessions.remove(live)
        cold_disk=self.directory/'cold-input.raw';shutil.copyfile(closed_medium,cold_disk)
        cold=self.session('cold',cold_disk);require(cold.identity==self.report['identity'],'cold identities changed')
        self.report['cold_boot']=cold.boot();self.wait_label(cold,'SAVED',24,132)
        cold_panel,_=cold.export('cold-notebook');require(visible_pixels(cold_panel)==visible_pixels(closed_panel),'cold raw notebook differs')
        cold_stream=Input(1650,2200,cold.inspect()['machine']['ticks']+10000,100000,0)
        cold_stream.sample(825,160,0,False);cold.admit(cold_stream.events)
        self.click(cold,cold_stream,'cold reopen durable uncertain review',320,140)
        reopened_panel,reopened_medium=cold.export('cold-review')
        require(self.record(reopened_medium)[0]==final_bytes and visible_pixels(reopened_panel)==visible_pixels(active_panel),
                'cold record, reconstructed review or complete controller pixels differ')
        self.report['cold_recovery']={'status':'PASS','complete_controller_pixels':True,
            'math_sha256':hashlib.sha256(final_bytes).hexdigest(),'actual_new_cpu':True}
        cold.close();self.sessions.remove(cold)
        failed_disk=self.directory/'failed-input.raw';shutil.copyfile(closed_medium,failed_disk)
        failed=self.session('failed',failed_disk,1);failed.boot()
        failed_stream=Input(1650,2200,failed.inspect()['machine']['ticks']+10000,100000,0)
        failed_stream.sample(825,160,0,False);failed.admit(failed_stream.events)
        self.click(failed,failed_stream,'open before failed policy save',320,140)
        first=len(failed_stream.events);failed_stream.tick=failed.inspect()['machine']['ticks']+10000
        failed_stream.sample(304,245,2048,True);failed_stream.sample(304,245,0,False)
        failed.admit(failed_stream.events[first:])
        failed.wait(lambda state:any(row[0]==0x424 for row in self.rows(failed)) and idle(state),self.args.action_seconds)
        failure_frame=self.wait_label(failed,'FAILED',24,132)
        _,failed_medium=failed.export('failed-policy-save')
        require(self.record(failed_medium)[0]==final_bytes and not any(row[0]==0x421 for row in self.rows(failed)),
                'failed policy barrier fabricated acknowledged learner state')
        self.report['failed_save']={'status':'PASS','no_false_saved':True,'acknowledged_record_unchanged':True,'actual_failed_controller_label':True,
            'completed':failure_frame['devices']['paper']['completed']}
        failed.close();self.sessions.remove(failed)
        require(sha(self.args.disk)==original_hash,'review observer mutated original user medium')
        self.report['status']='PASS'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--record-version',type=int,choices=(2,3,4,5),default=2,help='Exact declared target submission record version')
    parser.add_argument('--source-record-version',type=int,choices=(1,2,3,4),default=1,help='Exact retained acknowledged source format')
    parser.add_argument('--native-bundle',help='Validated immutable native runtime bundle for every public session')
    parser.add_argument('--guest-build',help='Current genuinely compiled and audited notebook guest; requires native bundle')
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--boot-seconds',type=int,default=60)
    parser.add_argument('--action-seconds',type=int,default=30)
    parser.add_argument('--deadline',type=int,default=2400)
    args=parser.parse_args();args.durable_suffix_from=None;args.checkpoint_relation='not-exercised'
    require(not args.guest_build or args.native_bundle,'guest-build requires native-bundle')
    require(1<=args.timeout<=3600 and 1<=args.boot_seconds<=600 and 1<=args.action_seconds<=600 and 1<=args.deadline<=7200,
            'invalid declared resource bounds')
    checker=ReviewChecker(args)
    try:checker.execute()
    except BaseException as error:checker.report['error']=str(error);raise
    finally:checker.close()
    print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))


if __name__=='__main__':main()
