#!/usr/bin/env python3
"""Actual fresh edition3 chooser, exact checking, reader Save and cold reopen.

Host-only stimulus and independent observations. The maintained Lean guest owns
course loading, revisions, checking, assistance, reader records and durability.
QEMU functional units do not establish canonical RTL timing or cached-state
continuation. This bounded case requires the original reference edition3
package already installed by the guest in an otherwise fresh acknowledged
sequence3 medium; it never installs or constructs a document on the host.
"""
from pathlib import Path
import argparse,json,time,shutil,filecmp,hashlib,os,signal,struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'conformance/lemmasim')]
from check_course_math_workflow import CourseMathWorkflow,Input,require,decode,visible_pixels
from check_live_notebook import PublicSession
from check_course_save import rtl_idle
from store_oracle import recover
from course_pixel_oracle import label_matches
from check_canonical_pen_pixels import expected_stroke
import workspace_transition_oracle as T
class FreshChooser(CourseMathWorkflow):
 def __init__(self,args):
  self.backend=args.backend
  if self.backend=='rtl':self.session_type=PublicSession
  # Existing canonical reader observations bound cold/open at1B/400M. The
  # common course checker already budgets500M for a complete Close redraw.
  # These limits select a new workload prospectively; none changes a retained
  # fast or browser run. Ordinary controls keep their existing150M ceiling.
  self.phase_caps={'view':400_000_000,'control':150_000_000,'check':300_000_000} if self.backend=='rtl' else {'view':100_000_000,'control':150_000_000,'check':200_000_000}
  self.aggregate_cap=6_000_000_000 if self.backend=='rtl' else 4_000_000_000
  self.clock_scope='canonical RTL clocks' if self.backend=='rtl' else 'fast functional instruction-clock units; no RTL timing parity'
  super().__init__(args)
  self.report.update(backend=self.backend,aggregate_cycles=self.aggregate_cap,clock_scope=self.clock_scope,phase_caps=self.phase_caps|{'cold':1_000_000_000,'close':500_000_000 if self.backend=='rtl' else 150_000_000,'presentation':100_000_000},phase_host_seconds={'cold':7200,'other':3600} if self.backend=='rtl' else {'all':600})
  self.progress()
 def idle(self,state):
  return rtl_idle(state) if self.backend=='rtl' else super().idle(state)
 def phase(self,s,name,cap,predicate):
  if self.backend=='rtl' and name=='Close-course':cap=500_000_000
  seconds=(7200 if name in ('cold-Ready','second-cold-Ready') else 3600) if self.backend=='rtl' else 600
  before=s.inspect()['machine']['cycle'];began=time.monotonic()
  while True:
   self.check_sources();state=s.inspect()['machine'];used=state['cycle']-before
   require(0<=used<=cap and self.cycles<=self.aggregate_cap and time.monotonic()<self.deadline and time.monotonic()-began<=seconds,'predeclared phase/whole bound: '+name)
   rows=self.rows(s);require(not state['finished'] and not any(r[0] in (1055,1060,1108,212,244)for r in rows),'actual guest fault: '+name+repr(rows[-8:]))
   if predicate(state):break
   require(used<cap and self.cycles<self.aggregate_cap,'predeclared clock ceiling: '+name)
   quantum=min(1_000_000,cap-used,self.aggregate_cap-self.cycles);s.run(quantum);after=s.inspect()['machine']['cycle'];require(after-state['cycle']==quantum if self.backend=='rtl' else after>state['cycle'],'actual execution progress');self.cycles+=after-state['cycle']
   if self.cycles//5_000_000!=(self.cycles-(after-state['cycle']))//5_000_000:
    self.report['running_phase']={'name':name,'cycle':after,'used':after-before,'host_seconds':time.monotonic()-began};self.progress()
  r={'name':name,'initial_cycle':before,'final_cycle':state['cycle'],'execution_units':used,'clock_scope':self.clock_scope,'host_seconds':time.monotonic()-began,'phase_clock_cap':cap,'phase_host_cap':seconds};self.report['phases'].append(r);self.progress();print(json.dumps(r),flush=True);return state
 def presentation(self,s,name,workspace,*,hint=False):
  document=workspace['document'];answer=document['answer'];outcome=document['outcome']
  labels=('UNCHECKED','VERIFIED Q EXACT','INVALID','NEEDS CLARIFICATION','UNSUPPORTED','INDETERMINATE RESOURCE LIMIT')
  wanted=f'N {answer[0]:02d} D {answer[1]:02d} C0 {answer[2]:02d} C1 {answer[3]:02d} C2 {answer[4]:02d}'
  hint_label=None
  if self.args.with_hint_context:
   learner=document['learner']
   require(not learner['show_reason'],'hint context case unexpectedly selected review explanation')
   applicable=document['goal'] in (1,2) and any(
    (event['revision'],event['goal'],event['kind'],event['value'])==
    (document['revision'],document['goal'],2,1)for event in learner['events'])
   hint_label=('HINT USE COMMON DENOMINATOR'if document['goal']==1 else'HINT MULTIPLY EACH TERM')if applicable else'READ ADD FRACTIONS THEN EXPAND'
  panel=self.directory/(name+'.ppm')
  def complete(state):
   if not self.idle(state):return False
   s.control({'action':'panel','path':str(panel)})
   return label_matches(panel,wanted,24,200) and label_matches(panel,labels[outcome],24,260) and (not hint or label_matches(panel,'HINT USE COMMON DENOMINATOR',24,280)) and (hint_label is None or label_matches(panel,hint_label.ljust(32),24,280))
  self.phase(s,name,100_000_000,complete)
  self.report.setdefault('controller_presentations',[]).append({'name':name,'revision':document['revision'],'answer':answer,'outcome':outcome,'all_answer_and_outcome_label_pixels':True,'hint_pixels':hint,'complete_hint_row':hint_label})
  self.progress()
 def check(self,s,stream,name,outcome):
  result=super().check(s,stream,name,outcome)
  self.presentation(s,name+'-controller-pixels',result[3])
  return result
 def execute(self):
  pkg=decode(self.args.package[0].read_bytes());_,seq,original=recover(self.args.disk.read_bytes());require(seq==3 and len(original)==3 and pkg['edition']==3,'actual installed3/no-workspace input')
  disk=self.directory/'private.raw';shutil.copyfile(self.args.disk,disk);s=self.session('first',disk);require(s.inspect()['machine']['cycle']==0,'actual coldCPU0')
  self.phase(s,'cold-Ready',1_000_000_000,lambda st:self.idle(st)and st['panel_completed']>=1 and any(r[0]==1056 for r in self.rows(s)))
  _,raw=s.export('cold-ready');require(filecmp.cmp(self.args.disk,raw,shallow=False),'cold backing changed')
  stream=Input(1650,2200,s.inspect()['machine']['ticks']+10000,100000,0)
  self.click(s,stream,'fresh-COURSE-chooser',320,140)
  panel,raw=s.export('chooser');require(label_matches(panel,'EDIT+',120,660)and label_matches(panel,'LOAD',216,660),'actual explicit edition chooser absent');_,initial_sequence,initial_records=recover(raw.read_bytes());workspace_key=(1,5785718146287534081)
  require(initial_sequence==4 and set(initial_records)==set(original)|{workspace_key} and all(initial_records[k].payload==v.payload for k,v in original.items()),'fresh chooser changed original objects or wrote an unexpected key')
  initial=self.record(raw)[1];require(initial['current']=={'origin':'Unknown'} and initial['document']['revision']==1 and initial['document']['outcome']==0 and initial['document']['attempts']==initial['document']['hints']==0 and initial['document']['answer']==[0,1,0,0,0] and not initial['applicable_package_selection'],'initial workspace manufactured selection/evidence/assistance')
  self.click(s,stream,'edition2',168,670);self.click(s,stream,'edition3',168,670)
  self.click(s,stream,'explicit-LOAD3',264,670,text=pkg['nodes'][0]['body'])
  self.click(s,stream,'node2',72,650,text=pkg['nodes'][1]['body']);self.click(s,stream,'exercise3',72,650,text=pkg['nodes'][2]['body'])
  self.click(s,stream,'USE-actual-edition3-goal',360,650,mutation=True)
  self.click(s,stream,'select-numerator',100,225,mutation=True);self.click(s,stream,'type5',640,250,mutation=True)
  self.click(s,stream,'select-denominator',124,225,mutation=True);self.click(s,stream,'clear-denominator',512,330,mutation=True);self.click(s,stream,'type6',768,250,mutation=True)
  before=self.checkpoint_record(s,'before-check');verified=self.check(s,stream,'actual-rational-Verified',1);require(verified[3]['document']['answer'][:2]==[5,6],'actual answer5/6');T.observe_transition(before[3],verified[3],'known-check')
  self.click(s,stream,'edit-to5over7',364,225,mutation=True);edited=self.checkpoint_record(s,'edited');T.observe_transition(verified[3],edited[3],'edit');self.presentation(s,'edited-unchecked-pixels',edited[3])
  invalid=self.check(s,stream,'actual-Invalid',2);T.observe_transition(edited[3],invalid[3],'known-check')
  self.click(s,stream,'authored-local-hint',172,245,mutation=True);hint=self.checkpoint_record(s,'hint');require(hint[3]['document']['hints']==1,'assistance absent');self.presentation(s,'hint-pixels',hint[3],hint=True)
  if self.args.with_limits:
   self.click(s,stream,'zero-denominator-field',124,225,mutation=True);self.click(s,stream,'clear-denominator-to-zero',512,330,mutation=True)
   zero=self.checkpoint_record(s,'zero-denominator-unchecked');require(zero[3]['document']['answer'][:2]==[5,0] and zero[3]['document']['outcome']==0,'actual division-by-zero submission')
   rejected=self.check(s,stream,'actual-division-zero-Invalid',2);T.observe_transition(zero[3],rejected[3],'known-check')
   self.click(s,stream,'NEXT-polynomial-template',112,245,mutation=True)
   if self.args.with_hint_context:
    next_goal=self.checkpoint_record(s,'polynomial-before-request');require(next_goal[3]['document']['hints']==1,'historical assistance was erased')
    self.presentation(s,'polynomial-no-borrowed-rational-hint',next_goal[3])
    self.click(s,stream,'authored-polynomial-hint',172,245,mutation=True)
    polynomial_hint=self.checkpoint_record(s,'polynomial-hint');require(polynomial_hint[3]['document']['hints']==2,'new actual polynomial assistance absent')
    self.presentation(s,'polynomial-current-authored-hint',polynomial_hint[3])
    self.check(s,stream,'polynomial-check-retains-same-revision-hint',2)
   self.click(s,stream,'NEXT-unsupported-template',112,245,mutation=True)
   unsupported=self.check(s,stream,'actual-Unsupported',4);require(unsupported[3]['current']=={'origin':'Unknown'} and unsupported[3]['document']['goal']==3,'unsupported template manufactured package authority')
   self.click(s,stream,'NEXT-back-to-rational',112,245,mutation=True);self.click(s,stream,'zero-checker-resource-budget',232,245,mutation=True)
   priority=self.check(s,stream,'zero-denominator-precedes-zero-budget',2);require(priority[3]['document']['answer'][1]==0 and priority[3]['document']['budget']==0,'actual invalid-input/resource precedence')
   self.click(s,stream,'select-denominator-for-resource-case',124,225,mutation=True);self.click(s,stream,'restore-positive-denominator',364,225,mutation=True)
   resource_input=self.checkpoint_record(s,'resource-input');require(resource_input[3]['document']['goal']==1 and resource_input[3]['document']['answer'][1]==1 and resource_input[3]['document']['budget']==0,'valid actual operands required for resource-only outcome')
   limited=self.check(s,stream,'actual-resource-Indeterminate',5);require(limited[3]['document']['budget']==0 and limited[3]['current']=={'origin':'Unknown'},'actual resource limit/current-source identity')
   self.report['controlled_failure_outcomes']={'division_by_zero':2,'unsupported':4,'invalid_input_precedes_budget':2,'valid_input_zero_semantic_budget':5,'workspace_preserved_for_annotation_and_Save':True};self.progress()
  self.click(s,stream,'explicit-reader-Save',1370,64,mutation=True);panel,raw=s.export('reader-saved');payload,workspace,records,seq=self.record(raw)
  key=(1,0x5244000000000001);require(key in records and len(records[key].payload)==128,'actual acknowledged reader record absent')
  fields=struct.unpack('<16Q',records[key].payload);require(fields[4:8]==(pkg['identity'],3,struct.unpack_from('<Q',self.args.package[0].read_bytes(),80)[0],3),'reader edition3/node3 binding differs')
  require(all(records[k].payload==v.payload for k,v in original.items()),'original package/root/page bytes changed')
  if self.args.with_ink:
   stream.tick=s.inspect()['machine']['ticks']+10000;first=len(stream.events);oldacks=len([r for r in self.rows(s) if r[0]==1057]);stream.stroke('postmath-raw-annotation',1,1,3,1900);samples=stream.events[first:];s.admit(samples)
   points=expected_stroke(samples)[1];ink_panel=self.directory/'annotation-wait.ppm'
   def annotated(state):
    if not(self.idle(state) and self.saved(s) and len([r for r in self.rows(s) if r[0]==1057])>oldacks and state['ticks']>=samples[-1][1]+200000):return False
    s.control({'action':'panel','path':str(ink_panel)});width,_,pixels=visible_pixels(ink_panel)
    return all(pixels[(y*width+x)*3:(y*width+x)*3+3]==bytes(3) for x,y in points)
   self.phase(s,'actual-raw-annotation-Saved',300_000_000,annotated)
   _,ink=s.export('annotation');_,ink_workspace,ink_records,seq=self.record(ink)
   chunks=[]
   for record in ink_records.values():
    p=record.payload
    if len(p)>=128 and struct.unpack_from('<3Q',p)==(0x314b4e49414d454c,1,3):
     n=struct.unpack_from('<Q',p,48)[0];require(len(p)==128+72*n,'raw chunk extent');chunks.append([struct.unpack_from('<9Q',p,128+72*i) for i in range(n)])
   require(chunks.count(samples)==1 and ink_workspace==workspace and ink_records[key].payload==records[key].payload,'exact raw annotation absent/duplicated or mathematical/reader bytes changed')
   self.report['raw_annotation']={'samples':[list(x) for x in samples],'independent_black_pixels':len(points),'sequence':seq,'workspace_and_reader_unchanged':True};self.progress()
  self.click(s,stream,'Close-course',320,140);home,saved=s.export('closed');saved_records=self.record(saved)[2]
  s.close();self.sessions.remove(s);cold_disk=self.directory/'cold-input.raw';shutil.copyfile(saved,cold_disk);c=self.session('second',cold_disk);require(c.inspect()['machine']['cycle']==0,'independent secondCPU0')
  self.phase(c,'second-cold-Ready',1_000_000_000,lambda st:self.idle(st)and st['panel_completed']>=1 and any(r[0]==1056 for r in self.rows(c)))
  cp,cm=c.export('second-ready');require(visible_pixels(cp)==visible_pixels(home),'all3.63M cold home pixels');require(filecmp.cmp(saved,cm,shallow=False),'all256MiB cold bytes')
  stream2=Input(1650,2200,c.inspect()['machine']['ticks']+10000,100000,0);self.click(c,stream2,'cold-reader-edition3-node3',320,140,text=pkg['nodes'][2]['body']);rp,rm=c.export('reopened');after=self.record(rm)
  require(after[0]==payload and after[1]==workspace and filecmp.cmp(saved,rm,shallow=False),'cold reader changed applicability/evidence/learner/medium')
  require(sha(self.args.disk)==self.original_medium_sha256,'original browser medium changed')
  self.report.update(status='PASS_FRESH_EDITION3_CHOOSER_CHECK_EDIT_HINT_SAVE_INDEPENDENT_COLD_READER',whole_execution_units=self.cycles,all_cold_home_pixels=3630000,all_medium_bytes=268435456,source_sequence=3,final_sequence=seq,reader_node=3,reader_edition=3,qualification=('Actual canonical RTL guest execution; no browser/fast-parity/full proof-kernel claim' if self.backend=='rtl' else 'Fast guest functional execution only; no RTL timing/browser/QEMU cached continuation/full proof-kernel claim'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
 parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
 for name in ('disk','package','native-bundle','work-dir'):parser.add_argument('--'+name,type=Path,required=True)
 parser.add_argument('--guest-build',type=Path)
 parser.add_argument('--guest-source-root',type=Path)
 parser.add_argument('--backend',choices=('qemu','rtl'),default='qemu')
 parser.add_argument('--with-ink',action='store_true',help='Also retain three raw samples and verify actual pixels before independent cold recovery')
 parser.add_argument('--with-limits',action='store_true',help='Also exercise displayed zero-denominator Invalid, Unsupported and zero-budget Indeterminate before ink/Save/cold reopen')
 parser.add_argument('--with-hint-context',action='store_true',help='With limits, require exact current-revision/goal hint rows, retaining historical assistance and exercising a separate polynomial hint')
 args=parser.parse_args()
 if args.with_hint_context and not args.with_limits:parser.error('hint-context scenario requires --with-limits')
 if bool(args.guest_build)!=bool(args.guest_source_root):parser.error('guest override requires its complete original audited source archive')
 if args.work_dir.exists() or not args.work_dir.resolve().is_relative_to(ROOT/'build'):parser.error('unused owned build output required')
 args.disk=args.disk.resolve();args.package=[args.package.resolve()];args.native_bundle=str(args.native_bundle.resolve())
 if args.guest_build:args.guest_build=str(args.guest_build.resolve())
 args.timeout=120;args.deadline=43200 if args.backend=='rtl' else 1800;args.checkpoint_relation='independent cold only';args.durable_suffix_from=None
 def terminate(sig,_frame):raise SystemExit(128+sig)
 signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
 actor=FreshChooser(args)
 actor.report.update(scope=__doc__,observer_sha256=sha(__file__))
 actor.progress()
 try:actor.execute()
 except BaseException as error:actor.report.update(status='FAIL',error=repr(error));raise
 finally:
  actor.close()
  (actor.directory/'result.json').write_text(json.dumps(actor.report,default=str,indent=2)+'\n')
 print(actor.report['status'],actor.cycles,actor.report['elapsed_seconds'],flush=True)

if __name__=='__main__':main()
