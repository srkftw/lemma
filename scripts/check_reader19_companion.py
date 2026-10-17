"""Reader19 final-barrier loss, fresh offline pixels and exact cold recovery.

The original seq26 observer failure remains retained. This separate case requires
reader24/raw25/page26/root27 and visibly white-to-black offline controller pixels.
The independent record observer checks every original object and the exact new
page/history; all original time, cycle and resource ceilings remain unchanged.

One existing native Clocked13 machine and an independently persistent hosted
Lean peer. Host code supplies raw input and actual peer/owned-WAIT EOF, never
constructs a guest record, performs guest recovery or supplies notebook pixels.
"""
from pathlib import Path
import argparse,json,sys,os,signal,subprocess,time,struct,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'conformance/lemmasim')]
import check_guest_usb_notebook as S
from silicon_guest_bundle import prepared
from course_package import decode
from workspace_oracle import observe as workspace
from inspect_notebook import inspect_page
from course_pixel_oracle import course_body_matches,label_matches
from number_pad_reference import pad_matches
from reader_reconciliation_oracle import observe as observe_reconciliation
from lemmasim_usb_pending import validate as validate_host
from supervise_usb_notebook import descendants,alive
NAME='lemma-silicon-dev/0.13.0';ROLE='usb-clocked-reader-entry2-bulk-notebook';READER=(1,0x5244000000000001);WORKSPACE=(1,0x504b000000000001);PACKAGE=(1,0x4350000100000001)
BASE_SHA='5e3d138686d1e0704f3100dd26c978af622c7e813e1fbcccfb18762eb28fa869'
def host_sources():return {str(p.relative_to(ROOT)):S.sha(p)for d in ['scripts','conformance/lemmasim']for p in sorted((ROOT/d).rglob('*.py'))}
def raw_samples(record):
 p=record.payload;S.require(len(p)>=128 and struct.unpack_from('<3Q',p)==(0x314b4e49414d454c,1,3),'actual raw envelope');n=struct.unpack_from('<Q',p,48)[0];S.require(len(p)==128+n*72,'actual raw envelope extent');return [struct.unpack_from('<9Q',p,128+i*72)for i in range(n)]
def overlay(points):
 pixels=bytearray(S.empty_pixels(1650,2200))
 for x,y in points:pixels[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
 return bytes(pixels)
class Live(S.NativeUSBSession):
 def __init__(self,c,name,peer,outbox):
  self.checker,self.name=c,name;self.directory=c.out/name;self.view_generation=self.view=None;self.log=(c.out/(name+'.log')).open('xb');before=host_sources();a=c.args
  cmd=[sys.executable,'-B',str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile',NAME,'--workload',ROLE,'--native-bundle',str(a.native_bundle),'--session-dir',str(self.directory),'--mode','laboratory','--headless','--paused','--timeout','120','--quantum','1000','--trace-limit','0','--usb-recovery','--usb-host-prepared',str(a.host_prepared),'--usb-peer-directory',str(peer),'--usb-peer-socket',str(c.socket),'--usb-host-state',str(outbox)]
  self.argv=cmd;self.process=subprocess.Popen(cmd,cwd=ROOT,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','LEAN_NUM_THREADS':'2'});c.sessions.append(self);until=time.monotonic()+60
  while not(self.directory/'session.json').is_file():S.require(self.process.poll()is None and time.monotonic()<until,'real Reader19 session admission');time.sleep(.02)
  zero=self.control({'action':'inspect'});S.require(not zero['running']and zero['machine']['cycle']==0 and not zero['machine']['usb']['configured']and zero['identity']['runtime']==c.data['binary']['sha256']and zero['identity'].get('usb_recovery_contract')=='lemma-usb-live-recovery/1','actual cold/unconfigured recovery owner');S.require(before==host_sources(),'public source changed during startup');self.identity=zero['identity'];self.start=zero['machine'];c.report.setdefault('host_startup_source_versions',{})[name]=before;c.update()
 def control(self,value):
  self.checker.guard()
  if value.get('action')=='run':S.require(self.checker.cycles+value['cycles']<=5_000_000_000,'prospective5B aggregate ceiling');self.checker.cycles+=value['cycles']
  return super().control(value)
 def wait(self,label,predicate,cycles,seconds,quantum=5_000_000,*,allow_failed_save=False):
  initial=self.machine()['cycle'];began=time.monotonic()
  def bounded(state,rows):
   S.require(state['cycle']-initial<=cycles and time.monotonic()-began<=seconds,'prospective phase bound before accepting '+label);self.checker.guard();return predicate(state,rows)
  return super().wait(label,bounded,cycles,seconds,quantum=quantum,allow_failed_save=allow_failed_save)
class Checker(S.Checker):
 def __init__(self,a):
  S.require(S.sha(S.__file__)==BASE_SHA,'shared original raw lifecycle observer changed');self.data=prepared(a.native_bundle,'rtl',ROLE,NAME);self.native=json.loads(Path(self.data['rtl_build']['path']).read_text());super().__init__(a);self.cycles=0;self.original={str(a.source/n):S.sha(a.source/n)for n in ['cold-peer/base.img','cold-peer/opaque.log','cold-peer/peer.json','cold-outbox/outbox','math-assisted.raw']};self.actor_sha=S.sha(__file__)
  self.report.update(schema='lemma-reader19-companion-connected/2',status='RUNNING',scope=__doc__,bounds={'aggregate_cycles':5_000_000_000,'whole_seconds':43200,'cold_cycles_each':1_000_000_000,'cold_seconds_each':7200,'course_cycles_each':400_000_000,'course_seconds_each':3600,'navigation_cycles_each':150_000_000,'navigation_seconds_each':1800,'failure_cycles':200_000_000,'failure_seconds':3600,'offline_ink_cycles':200_000_000,'offline_ink_seconds':1800,'retry_cycles':800_000_000,'retry_seconds':7200,'owned_RSS_bytes':4<<30,'minimum_available_bytes':2<<30,'output_bytes':12<<30},original_sources=self.original,plan_sha256=S.sha(a.plan),actor_sha256=self.actor_sha,not_qualified=['full USB/radio conformance or production authentication','Product boot/browser peer/fast timing/general checkpoint continuation','new mathematical check or learning-gain result'])
 def guard(self):S.require(time.monotonic()-self.started<=43200 and S.sha(__file__)==self.actor_sha,'whole actor deadline/source identity')
 def sample_resources(self):
  super().sample_resources();own=int(next(x.split()[1]for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmRSS:')))*1024+sum(v.get('last_sample',{}).get('sampled_resident_kib',0)*1024 for v in self.report.get('host_resources',{}).values());sizes=[p.stat().st_size for p in self.out.rglob('*')if p.is_file()and not p.is_symlink()];available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:'));S.require(own<=4<<30 and available>=2<<30 and sum(sizes)<=12<<30 and max(sizes,default=0)<=1<<30,'declared owned RSS/available/disk/file bound');self.report['sampled_owned_peak_RSS_bytes']=max(self.report.get('sampled_owned_peak_RSS_bytes',0),own);self.guard()
 def tap(self,l,stream,x,y):
  stream.tick=l.machine()['ticks']+10000;at=len(stream.events);stream.sample(x,y,2048,True);stream.sample(x,y,0,False);l.admit(stream.events[at:]);return stream.events[-1][1]
 def materialize(self,name):
  p=self.out/(name+'.raw');S.materialize_observation(self.peer,p);return p,S.recover(p.read_bytes())
 def view(self,l,stream,name,node,*,first=False):
  old=l.machine()['panel_completed'];tick=self.tap(l,stream,320 if first else 72,140 if first else 650);p=self.out/(name+'.ppm')
  def completed(st,rs):
   if not(st['paper_busy']==st['pen_queue']==st['event_queue']==st['panel_pending_pixels']==0 and st['panel_completed']>old and st['ticks']>=tick+200000):return False
   l.control({'action':'panel','path':str(p)});return course_body_matches(p,self.pkg['nodes'][node-1]['body'])and pad_matches(p,False)and label_matches(p,'VERIFIED',24,260)
  return l.wait(name,completed,400_000_000 if first else 150_000_000,3600 if first else 1800)
 def execute(self):
  plan=json.loads(self.args.plan.read_text());S.require(plan['status']=='PREDECLARED_NOT_RUN'and plan['loss']=='final reader publication barrier6 reply after independent persistence','fixed prospective fault');S.require(S.sha(self.args.native_bundle/'bundle.json')==plan['native_bundle_sha256'] and S.sha(self.args.host_prepared)==plan['host_prepared_sha256'] and self.original==plan['source_files'] and self.actor_sha==plan['actor_sha256'],'prepared bundle/host/source/actor drift')
  S.copy_opaque_peer(self.args.source/'cold-peer',self.peer,self.args.source/'cold-outbox',self.outbox);before,(_,seq,original)=self.materialize('before');S.require(seq==23 and S.sha(before)==self.original[str(self.args.source/'math-assisted.raw')]and READER not in original,'actual Saved23 source/no preinstalled reader record');pkgbytes=original[PACKAGE].payload;self.pkg=decode(pkgbytes);old_workspace=original[WORKSPACE].payload;w=workspace(old_workspace,1,WORKSPACE[1],[pkgbytes]);S.require(w['current']['node']==3 and w['document']['answer']==[5,6,0,0,0]and w['document']['outcome']==1 and w['document']['hints']>0,'actual acknowledged math/assistance23')
  points=[]
  for obj,_,visible in inspect_page(original[1,257].payload,257):
   if visible:points+=S.expected_stroke(raw_samples(original[1,obj]))[1]
  self.start_peer();l=Live(self,'first',self.peer,self.outbox);self.report['identity']=l.identity;l.boot(overlay(points));stream=S.Input(1650,2200,l.machine()['ticks']+10000,100000,0);self.view(l,stream,'source3',3,first=True);self.view(l,stream,'browse4',4);self.view(l,stream,'browse5',5)
  read_only,(_,s0,objects)=self.materialize('before-reader-save');S.require(s0==23 and S.sha(read_only)==S.sha(before),'browsing wrote a durable byte');self.stop_peer();prefix=len(S.opaque_log(self.peer/'opaque.log'));saved=sum(r[0]==0x421 for r in l.records());first=self.start_peer(6);self.first_peer=first;self.tap(l,stream,1370,64);host=validate_host(self.args.host_prepared);binary=host.get('artifacts',{}).get('binary',host.get('binary',{}))['path'];eof={}
  def failed(st,rs):
   if first.poll()is not None and not eof:
    S.require(first.returncode==0,'private peer completed selected lost receipt');effects=S.opaque_log(self.peer/'opaque.log')[prefix:];S.require(len(effects)==6 and [f[2]for f,_ in effects]==[1,1,1,2,1,2]and sum(r[0]==0x421 for r in rs)==saved,'actual final reader-barrier selection/no premature Saved')
    if st['usb']['command'].startswith('WAIT ')and st['usb']['pending_command']:
     owned=[]
     for item in descendants(l.process.pid):
      try:args=(Path('/proc')/str(item['pid'])/'cmdline').read_bytes().split(bytes([0]))
      except FileNotFoundError:continue
      if args[0]==str(Path(binary).resolve()).encode():owned.append(item)
     S.require(len(owned)==1 and alive(owned[0]),'uniquely owned real policy4 WAIT child');os.kill(owned[0]['pid'],signal.SIGTERM);eof.update(cycle=st['cycle'],child=owned[0],effects=[list(f)for f,_ in effects],peer_log_sha256=S.sha(self.peer/'opaque.log'),outbox_sha256=S.sha(self.outbox/'outbox'));self.report['lost_final_barrier']=eof;self.update()
   if not(eof and st['usb']['terminal']and any(r[0]==0x424 and r[1]==227 for r in rs)):return False
   path=self.out/'failed-panel.ppm';l.control({'action':'panel','path':str(path)});return label_matches(path,'FAILED',24,132)
  state=l.wait('lost-reader-barrier-real-EOF-noSaved',failed,200_000_000,3600,quantum=1_000_000,allow_failed_save=True);uncertain,(_,us,urec)=self.materialize('observed-unacknowledged-reader24');S.require(us==24 and set(urec)==set(original)|{READER}and urec[WORKSPACE].payload==old_workspace and all(urec[k].payload==v.payload for k,v in original.items()),'failed barrier did not retain exact known+1/old objects');held=urec[READER].payload;f=struct.unpack('<16Q',held);S.require(len(held)==128 and f[4:8]==(self.pkg['identity'],self.pkg['edition'],struct.unpack_from('<Q',pkgbytes,80)[0],5),'actual held reader payload fields')
  stream.tick=state['ticks']+10000;at=len(stream.events);stream.stroke('offline-reader-held-ink',1,1,3,1800);samples=stream.events[at:];newpoints=S.expected_stroke(samples)[1]
  S.require(set(map(tuple,newpoints)).isdisjoint(map(tuple,points)),'new offline pixels must not overlap source ink');_,_,prior_pixels=l.pixels(state);S.require(all(prior_pixels[(y*1650+x)*3:(y*1650+x)*3+3]==bytes([255])*3 for x,y in newpoints),'actual prospective offline pixels must start white');l.admit(samples)
  self.report['offline_pixel_transition']={'source_white_pixels':len(newpoints),'row':1800,'disjoint_from_source':True}
  def ink(st,rs):
   if not(st['usb']['terminal']and sum(r[0]==0x421 for r in rs)==saved and st['ticks']>=stream.events[-1][1]+2000000 and st['paper_busy']==st['pen_queue']==st['event_queue']==st['panel_pending_pixels']==0):return False
   _,_,pixels=l.pixels(st);return all(pixels[(y*1650+x)*3:(y*1650+x)*3+3]==bytes(3)for x,y in newpoints)
  l.wait('offline-raw-ink-withoutSaved',ink,200_000_000,1800,allow_failed_save=True);S.require(S.sha(self.peer/'opaque.log')==eof['peer_log_sha256']and S.sha(self.outbox/'outbox')==eof['outbox_sha256'],'offline ink altered unresolved effects');self.start_peer();st=l.machine();attach={'action':'usb-reconnect','epoch':st['usb']['connection_epoch']+1,'next_request':st['usb']['next_request'],'binding':st['usb']['namespace_binding']};l.control(attach);after=l.machine();S.require(after['cycle']==st['cycle']and not after['usb']['configured'],'native attach must not configure USB');self.report['attach']=attach;self.tap(l,stream,1370,64)
  # Use raw published Save/page observations to wait before one final passive materialization.
  l.wait('real-remount-readEOF-readerSaved24-and-offline-ink-commit',lambda st,rs:any(r==(0x421,24,1,1,READER[1])for r in rs)and any(r==(0x421,27,1,1,24)for r in rs)and st['usb']['configured']and st['paper_busy']==st['pen_queue']==st['event_queue']==st['panel_pending_pixels']==0,800_000_000,7200,allow_failed_save=True)
  acknowledged,(_,final_seq,final_records)=self.materialize('acknowledged');S.require(final_seq==27 and final_records[READER].payload==held and final_records[WORKSPACE].payload==old_workspace and any(raw_samples(v)==samples for v in final_records.values()if len(v.payload)>=128 and struct.unpack_from('<3Q',v.payload)==(0x314b4e49414d454c,1,3)),'real reader24 plus exact offline raw/page/root durability');self.report['independent_records']=observe_reconciliation(original,urec,final_records,samples,final_seq)
  effects=S.opaque_log(self.peer/'opaque.log');first_ids=[f[4]for f,_ in effects[prefix:prefix+6]];S.require(first_ids==list(range(first_ids[0],first_ids[0]+6))and sum(f[4]==first_ids[-1]for f,_ in effects)==1,'lost final-barrier effect duplicated');self.report['reconciled']={'reader_sequence':24,'final_sequence':27,'exact128_reader':True,'exact_offline_raw':True,'no_duplicate_final_barrier':True}
  l.close();self.sessions.remove(l);self.stop_peer();cp=self.out/'cold-peer';co=self.out/'cold-outbox';S.copy_opaque_peer(self.peer,cp,self.outbox,co);self.peer=cp;self.outbox=co;self.start_peer();cold=Live(self,'second',cp,co);cold.boot(overlay(points+newpoints));coldraw,(_,cs,cr)=self.materialize('cold');S.require(cs==27 and S.sha(coldraw)==S.sha(acknowledged),'independent cold all256MiB bytes');stream2=S.Input(1650,2200,cold.machine()['ticks']+10000,100000,0);self.view(cold,stream2,'cold-saved-reader5',5,first=True);final,(_,fs,fr)=self.materialize('cold-reopened');S.require(fs==27 and S.sha(final)==S.sha(acknowledged)and fr[WORKSPACE].payload==old_workspace and all(S.sha(p)==h for p,h in self.original.items()),'cold reader mutated evidence/history/assistance/backing/original sources');self.report.update(status='PASS',qualified_scenario='READER19_FINAL_BARRIER_LOSS_UNIQUE_OFFLINE_INK_RAW_PAGE_ROOT_RECONCILIATION_INDEPENDENT_COLD',actual_cycles=self.cycles,cold_all_home_pixels=3630000,cold_all_medium_bytes=268435456,reader_node=5,new_math_check=False);self.update()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['native-bundle','host-prepared','source','plan','work-dir']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args()
 for n in ['native_bundle','host_prepared','source','plan','work_dir']:setattr(a,n,getattr(a,n).resolve())
 a.profile=NAME;a.rtl_source_root=a.guest_source_root=None;a.cold_cycles=1_000_000_000;a.cold_deadline=7200;a.ink_cycles=200_000_000;a.action_cycles=800_000_000;a.action_deadline=7200
 def terminate(sig,_frame):raise SystemExit(128+sig)
 signal.signal(signal.SIGTERM,terminate)
 actor=Checker(a)
 try:actor.execute()
 except BaseException as e:actor.report.update(status='FAIL',error=repr(e));raise
 finally:actor.close()
 print(actor.report['status'],actor.cycles,actor.report['host_seconds'],flush=True)
if __name__=='__main__':main()
