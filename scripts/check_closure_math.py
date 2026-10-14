#!/usr/bin/env python3
"""Real raw-pen closure math IPC, acknowledged Save and independent cold CPUs.

The host supplies only input samples and independently inspects actual guest
records/events/pixels. It never injects a request, answer or trusted result.
"""
import argparse,hashlib,json,shutil,struct
from pathlib import Path
from check_math_session import MathChecker
from check_arithmetic_isolation import IsolationChecker
from check_live_notebook import Input,require,sha,visible_pixels,guest_events,idle
from store_oracle import recover
from arithmetic_closure_identity import REGISTRY

IDS=tuple(REGISTRY[k]['id'] for k in ('implementation','lowering','runtime','resources'))

def admitted(record):
 require(record['format']=='lemma-mathematical-submission/8','Require actual Document8')
 metadata=record['execution']['history'][:record['attempts']]
 require(all(e['origin']=='IsolatedClosure' and e['status']==0 and e['budget']==h['budget']
  for e,h in zip(metadata,record['history'])),'Actual attempt lacks closed Protocol7 execution identity')
 require(record['execution']['active']==metadata[-1],'Applicable closure identity differs from latest actual attempt')
 return metadata

class ClosureMathChecker(MathChecker):
 def __init__(self,args):
  super().__init__(args)
  self.report.update(schema='lemma-closure-mathematics-integration/1',scope=__doc__)
  if args.guest_source_root is not None:
   self.report['bounds']['guest_source_root']=str(args.guest_source_root.resolve())
  self.report['observer_sources']['scripts/check_closure_math.py']=sha(Path(__file__))
 def press(self,session,stream,name,column,row=3):
  result=super().press(session,stream,name,column,row)
  if name=='edit answer invalidates applicability':
   _,medium=session.export('edited-closure-execution');_,record,_,_=self.record(medium)
   require(record['outcome']==0 and record['evidence_revision']==0 and record['execution']['active']=={'origin':'Unknown'}
    and record['history']==self.report['verified']['history'] and record['execution']['history']==self.report['verified']['execution']['history'],
    'Actual edit retained applicability or rewrote immutable history')
   self.report['edited_execution_applicability']={'status':'PASS','active_unknown':True,'old_attempts_exact':True}
  return result
 def live_workflow(self):
  result=super().live_workflow();_,record,_,_=self.record(result[2]);metadata=admitted(record)
  rows=guest_events(self.directory/'live/uart-0.bin');requests=[r for r in rows if r[0]==0x459];replies=[r for r in rows if r[0]==0x455]
  reclaimed=[r for r in rows if r[0]==0x45d]
  require(len(requests)==len(replies)==len(reclaimed)==len(metadata)==5,'Actual IPC/count observations differ from durable attempts')
  for h,e,q,r,c in zip(record['history'],metadata,requests,replies,reclaimed):
   require(q[1:4]==(e['request'],h['revision'],h['goal']) and r[1:]==(e['request'],h['revision'],0,h['outcome'])
    and c==(0x45d,e['request'],0,0,0),'Real request/reply/reclamation differs from immutable attempt')
  require([r for r in rows if r[0]==0x45c]==[(0x45c,*IDS)] and (0x456,0,0,7,10000000) in rows,'Actual Protocol7 handshake/start mode differs')
  self.report['closure_execution']={'status':'PASS','protocol':7,'document':8,'request_bytes':160,'reply_bytes':128,
   'original_goal_revision_domain_assumptions_bound':True,'actual_requests':requests,'actual_replies':replies,
   'actual_post_request_live_counts':reclaimed,'normal_graphs_reclaimed':True,'identities':IDS,
   'rational_cross_products':'ordinary dynamically selected3capture closures',
   'polynomial':'original exact coefficient equality in Q[x]; no sampling'}
  return result
 def execute(self):
  super().execute();self.report['status']='FAIL'
  disk=self.directory/'zero-input.raw';shutil.copyfile(self.args.disk,disk)
  zero=self.session('zero-denominator',disk);self.report['zero_boot']=zero.boot()
  require(zero.identity==self.report['identity'],'Zero case changed guest/artifact authority')
  stream=Input(1650,2200,zero.inspect()['machine']['ticks']+10000,100000,0)
  stream.sample(825,160,0,False);zero.admit(stream.events)
  self.click(zero,stream,'open zero-denominator course',320,140)
  even=self.press(zero,stream,'check actual even numerator0/1',1,4)
  require(even[2:]==(1,2,even[1]),'Even selector branch changed exact0/1 result')
  self.wait_label(zero,'SAVED',24,132);_,even_medium=zero.export('even-numerator-saved')
  _,even_record,_,_=self.record(even_medium);even_metadata=admitted(even_record)
  require(even_record['answer'][:2]==[0,1] and len(even_metadata)==1 and even_record['outcome']==2,
   'Actual even-selector rational attempt differs')
  self.report['even_numerator_closure']={'status':'PASS','record':even_record,
   'scope':'real admitted0/1 uses selector0 and ordinary dynamically selected closures; exact resultInvalid'}
  self.press(zero,stream,'select actual denominator',8)
  self.press(zero,stream,'decrement actual denominator tozero',22)
  checked=self.press(zero,stream,'check actual zero denominator',1,4)
  require(checked[2:]==(1,2,checked[1]),'Zero denominator gained Verified or resource outcome')
  self.wait_label(zero,'SAVED',24,132);_,medium=zero.export('zero-denominator-saved')
  payload,record,_,_=self.record(medium);metadata=admitted(record)
  require(record['answer'][:2]==[0,0] and len(metadata)==2 and record['outcome']==2
   and record['history'][:1]==even_record['history']
   and record['execution']['history'][:1]==even_record['execution']['history'][:1],
   'Actual zero denominator record differs or rewrote prior even-selector attempt')
  rows=self.rows(zero);q=[r for r in rows if r[0]==0x459];r=[r for r in rows if r[0]==0x455]
  require(len(q)==len(r)==2 and r[-1][1:]==(metadata[-1]['request'],record['revision'],0,2)
   and all((0x45d,e['request'],0,0,0) in rows for e in metadata),
   'Even/zero side-condition reply/reclamation not actual')
  self.report['even_numerator_closure'].update(actual_request=q[0],actual_reply=r[0],
   actual_reclaimed=(0x45d,metadata[0]['request'],0,0,0))
  self.report['zero_denominator']={'status':'PASS','actual_request':q[-1],'actual_reply':r[-1],
   'acknowledged_document_sha256':hashlib.sha256(payload).hexdigest(),'record':record,
   'scope':'admitted exact/1 zero-denominator preflight; closure application intentionally not reached'}
  zero.close();self.sessions.remove(zero);require(sha(self.args.disk)==self.report['medium_source']['sha256'],'Original medium changed')
  self.report['status']='PASS'

class ClosureFailureChecker(IsolationChecker):
 def __init__(self,args):
  super().__init__(args);self.report.update(schema='lemma-closure-mathematics-isolation/1',scope=__doc__)
  self.report['observer_sources']['scripts/check_closure_math.py']=sha(Path(__file__))
  self.report['observer_sources']['scripts/closure_frame_boundary.py']=sha(Path(__file__).with_name('closure_frame_boundary.py'))
  if getattr(args,'migration_reader',None) is not None:
   self.report['bounds']['migration_reader']=str(args.migration_reader.resolve())
 def execute(self):
  original_hash=sha(self.args.disk);disk=self.directory/'failure-input.raw';shutil.copyfile(self.args.disk,disk)
  live=self.session('failure',disk);self.report['identity']=live.identity;self.report['boot']=live.boot()
  mode=1 if self.args.case=='oom' else 2;expected=237 if mode==1 else 96
  rows=self.rows(live)
  require([r for r in rows if r[0]==0x456]==[(0x456,mode,31 if mode==1 else 0,7,10000000)] and
   [r for r in rows if r[0]==0x45c]==[(0x45c,*IDS)],'Actual selected closure failure/pressure/authority differs')
  stream=Input(1650,2200,live.inspect()['machine']['ticks']+10000,100000,0)
  stream.sample(825,160,0,False);live.admit(stream.events)
  self.click(live,stream,'open actual failure course',320,140);self.wait_label(live,'SAVED',24,132)
  _,prior_medium=live.export('before-check');prior_bytes,prior,_,_=self.record(prior_medium)
  require(prior['format']=='lemma-mathematical-submission/8' and prior['answer']==[0,1,0,0,0]
   and prior['goal']==1 and prior['budget']==8 and prior['outcome']==0 and not prior['history']
   and prior['execution']['active']=={'origin':'Unknown'},'Failure fixture would not reach admitted ordinary allocation')
  self.allowed_error=True;tick=self.raw_click(live,stream,40,245)
  live.wait(lambda s:any(r[0]==0x459 for r in self.rows(live)),self.args.action_seconds,quantum=10000)
  request=[r for r in self.rows(live) if r[0]==0x459][-1]
  live.wait(lambda s:any(r[0]==0x454 and r[1]==expected for r in self.rows(live)),self.args.action_seconds,quantum=100000)
  self.settle(live,tick);self.wait_label(live,'SAVED',24,132)
  _,error_medium=live.export('after-error');require(self.record(error_medium)[0]==prior_bytes,'Verifier failure mutated acknowledged mathematical bytes')
  rows=self.rows(live)
  require(not any(r[0]==0x450 and r[3]!=0 for r in rows),'Verifier failure manufactured evidence')
  if mode==1:
   require((0x455,request[1],request[2],237,0) in rows and (0x45d,request[1],31,1,237) in rows,
    'Actual31-slot ordinary closure allocation failure/reclamation not observed')
  else:
   servers=[r[1] for r in rows if r[0]==0xf1 and r[2]==2]
   reaps=[r for r in rows if r[0]==0xf6]
   require(len(servers)==1 and len(reaps)==1 and reaps[0][1]==servers[0]
    and reaps[0][2]<reaps[0][3] and reaps[0][4]==0
    and any(r[0]==0xd4 and r[1]==13 and r[3]==0x500000 for r in rows),
    'Actual unmapped User page fault/dead verifier teardown not observed')
   self.report['actual_verifier_teardown']={'status':'PASS','arithmetic_descriptor':servers[0],
    'actual_reap':reaps[0],'returned_owned_frames':reaps[0][3]-reaps[0][2]}
  self.report['failed_request']={'status':'PASS','actual_request':request,'actual_error':expected,
   'no_attempt_or_evidence':True,'acknowledged_document_unchanged':True,'live_slots':31 if mode==1 else None}
  first,ink_tick=self.ink(live,stream,'actual ink after closure verifier failure')
  self.settle(live,ink_tick);self.wait_label(live,'SAVED',24,132);panel,medium=live.export('post-failure-ink')
  require(self.record(medium)[0]==prior_bytes,'Writing after failure changed mathematics')
  _,_,records=recover(medium.read_bytes());samples=[]
  for key,record in records.items():
   if key[1]>0x10000 and len(record.payload)>=128:
    count=struct.unpack_from('<Q',record.payload,48)[0]
    samples.extend(struct.unpack_from('<9Q',record.payload,128+i*72) for i in range(count))
  require(all(s in samples for s in stream.events[first:]),'Post-failure input not reconstructed/durably stored by guest')
  # A real Saved frame can precede queued guest tile uploads. The retained
  # original failure/private checkpoint proves this condition. Advance one
  # declared virtual second, then require actual guest queue/bounds quiescence
  # and controller Saved before comparing the complete visible cold image.
  from closure_frame_boundary import inspect_queue
  before=live.inspect()['machine'];live.run(100000000)
  self.wait_label(live,'SAVED',24,132)
  queue=inspect_queue(live,self.args.migration_reader,'post-failure-display-boundary')
  require(queue['quiet'],'Actual guest display queue did not settle within declared1s fence')
  panel,medium=live.export('post-failure-settled-ink');after=live.inspect()['machine']
  require(self.record(medium)[0]==prior_bytes,'Display fence changed mathematical bytes')
  self.report['post_failure_display_fence']={'status':'PASS','virtual_progress_cycles':100000000,
   'before_completed':before['devices']['paper']['completed'],
   'after_completed':after['devices']['paper']['completed'],'actual_private_queue':queue,
   'scope':'Source-bound1s actual display progress +realqueue0; completepixelcriterion unchanged'}
  live.close();self.sessions.remove(live);disk=self.directory/'cold-input.raw';shutil.copyfile(medium,disk)
  cold=self.session('cold',disk);self.report['cold_boot']=cold.boot();self.wait_label(cold,'SAVED',24,132)
  require(cold.identity==self.report['identity'],'Cold failure continuation changed source/artifact identity')
  cold_panel,cold_medium=cold.export('cold-failure-notebook')
  require(visible_pixels(cold_panel)==visible_pixels(panel) and self.record(cold_medium)[0]==prior_bytes,
   'Independent cold lost post-failure complete pixels/math bytes')
  self.report['post_failure_ink_cold']={'status':'PASS','all_actual_raw_samples':True,'actual_saved':True,
   'new_cpu':True,'complete_pixels_exact':True,'mathematical_bytes_exact':True}
  cold.close();self.sessions.remove(cold);require(sha(self.args.disk)==original_hash,'Original medium changed')
  self.report['status']='PASS'

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('disk','work-dir'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--native-bundle',required=True);p.add_argument('--guest-build',required=True)
 p.add_argument('--guest-source-root',type=Path);p.add_argument('--case',choices=('workflow','oom','fault'),default='workflow')
 p.add_argument('--migration-reader',type=Path,help='OOM/fault: exact QEMU11.1.1 scripts/analyze-migration.py for read-only private queue fence')
 p.add_argument('--timeout',type=int,default=300);p.add_argument('--boot-seconds',type=int,default=90)
 p.add_argument('--action-seconds',type=int,default=60);p.add_argument('--deadline',type=int,default=1800)
 a=p.parse_args();a.checkpoint_relation='not-exercised';a.durable_suffix_from=None
 for name in ('require_execution_identity','require_sums_identity','require_bytes_identity','require_array_identity','require_string_identity',
              'require_managed_constructor','require_sums_constructor','require_bytes_payload','require_array_payload','require_string_payload'):setattr(a,name,False)
 require(1<=a.timeout<=3600 and 1<=a.boot_seconds<=600 and 1<=a.action_seconds<=600 and 1<=a.deadline<=7200,'Invalid declared bounds')
 require(a.case=='workflow' or a.migration_reader is not None,'Failure actor requires pinned read-only private queue inspector')
 checker=ClosureMathChecker(a) if a.case=='workflow' else ClosureFailureChecker(a)
 try:checker.execute()
 except BaseException as e:checker.report['status']='FAIL';checker.report['error']=str(e);raise
 finally:checker.close()
 print(json.dumps({'status':checker.report['status'],'work_dir':str(checker.directory)}))
if __name__=='__main__':main()
