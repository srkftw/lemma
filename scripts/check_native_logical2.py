#!/usr/bin/env python3
"""Fresh-process native continuation observer for the separately selected logical2 binding."""
from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess,sys,time,struct,traceback,tempfile
sys.path.insert(0,str(Path('scripts').resolve()))
sys.path.insert(0,str(Path('conformance/lemmasim').resolve()))
from lemmasim_fast import QMP,CPU
from multimodal_native_bundle import prepared_archive
from check_notebook_workflow import guest_events
from notebook_input import Input
from native_logical_relation import compare_machine,compare_logical
parser=argparse.ArgumentParser(description='Actual maintained native logical2 continuation; no host guest policy.')
parser.add_argument('--qemu',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
parser.add_argument('--medium',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--cut',choices=['ready','converter','storage'],default='ready');parser.add_argument('--timeout',type=int,default=300)
a=parser.parse_args()
if not 1<=a.timeout<=900:parser.error('timeout must be1..900 seconds')
root=a.output_dir.resolve();root.mkdir(parents=True,exist_ok=False)
start=time.monotonic();deadline=start+a.timeout;live=[];sockets=[]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
bundle=a.bundle.resolve();entry=prepared_archive(bundle,'qemu','notebook','lemma-silicon-dev/0.14.0')['workloads']['notebook'];binary=a.qemu.resolve();medium=a.medium.resolve()
report={'schema':'lemma-native-logical-checkpoint/2','status':'FAIL','scope':'Actual maintained guest, Ready, activeconverter or pendingstorage cut, blockedUART, freshprocess native logical2 continuation and coherently forged malformedcandidate. Publiccheckpointguard stays until separately qualified full path.','limits':{'whole_seconds':a.timeout,'boot_ns':4000000000,'suffix_ns':4001000000 if a.cut=='storage' else 1000000,'output_bytes':2<<30,'owned_rss_bytes':1<<30},'inputs':{str(p):sha(p) for p in [binary,bundle/'bundle.json',medium,Path(__file__),Path(__file__).with_name('native_logical_relation.py'),Path('conformance/lemmasim/check_notebook_workflow.py'),Path('conformance/lemmasim/notebook_input.py')]}}
def require(v,m):
 if not v:raise RuntimeError(m)
def resources():
 total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
 report['output_bytes']=total
 require(total<=2<<30,'Original2GiB output budget')
 rss=0
 for pid in {os.getpid()}|{p.pid for p,q,log in live if p.poll() is None}:
  try:rss+=int(Path('/proc',str(pid),'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
  except FileNotFoundError:pass
 report['peak_owned_rss_bytes']=max(report.get('peak_owned_rss_bytes',0),rss)
 require(rss<=1<<30,'Original1GiB combined owned RSS budget')

def launch(name,backing):
 resources()
 d=root/name;d.mkdir();disk=d/'medium.raw';subprocess.run(['cp','--reflink=auto','--sparse=always',str(backing),str(disk)],check=True);disk.chmod(0o600)
 socket_directory=tempfile.TemporaryDirectory(prefix='lemma-l2-',dir='/tmp');sockets.append(socket_directory);socket_path=Path(socket_directory.name)/'qmp.sock'
 argv=[str(binary),'-machine','lemma-silicon-fast-softtlb','-cpu',CPU,'-m','128M','-smp','1','-bios','none','-kernel',entry['image']['path'],'-dtb',entry['dtb']['path'],'-display','none','-monitor','none','-serial','file:'+str(d/'uart.bin'),'-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-global','lemma-fast-block.medium='+str(disk),'-qmp','unix:'+str(socket_path)+',server=on,wait=off']
 if a.cut=='storage':argv+=['-global','lemma-fast-block.delay-write-ns=2000000000']
 log=(d/'machine.log').open('xb');p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);owned=[p,None,log];live.append(owned);q=QMP(socket_path,p,min(10,max(1,deadline-time.monotonic())));owned[1]=q;put(q,'enable-raw-uart','lemma-raw-uart/1');put(q,'enable-raw-uart-flow','lemma-raw-uart-flow/1');return q,d
def get(q,k):return q.execute('qom-get',{'path':'/machine/lemma-hardware','property':k})
def put(q,k,v):return q.execute('qom-set',{'path':'/machine/lemma-hardware','property':k,'value':v})
def storage(q):return json.loads(q.execute('qom-get',{'path':'/machine/lemma-block','property':'storage-state'}))
def observed(q):return {**{k:get(q,k) for k in ['virtual-time','device-state','multimodal-state','raw-uart-state','execution-state']},'storage':storage(q)}
def run(q,until):
 resources();require(time.monotonic()<deadline,'original whole deadline');put(q,'run-until',str(until));q.execute('cont')
 while q.execute('query-status')['running']:
  resources();require(time.monotonic()<deadline,'original whole deadline');time.sleep(.005)
def save(q,d,name):
 resources()
 m=d/(name+'.qemu');t=d/(name+'.tlb');q.execute('lemma-save-machine-softtlb',{'filename':str(m),'cache-filename':str(t)});return m,t
def export(q,d,name):
 resources()
 p=d/name;q.execute('qom-set',{'path':'/machine/lemma-block','property':'export-medium','value':str(p)});return p
# Bind and retain the actual local Python module closure before machine launch.
# Artifacts/guest archives retain their independent original producer identities.
archive=root/'observer-source';archive.mkdir()
local_sources={}
repository=Path.cwd()
for module in list(sys.modules.values()):
 value=getattr(module,'__file__',None)
 if not value:continue
 path=Path(value).resolve()
 if path.suffix=='.py' and path.is_relative_to(repository) and path.is_file():
  relative=path.relative_to(repository);local_sources[str(relative)]=sha(path)
  target=archive/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
report['observer_source_closure']=local_sources
try:
 q,d=launch('original',medium)
 if a.cut=='storage':
  report['declared_storage_stimulus']={'first_write_delay_ns':2000000000,'scope':'actual first guest journal Save; no host request or acknowledgment synthesized'}
  for quantum in range(40):
   run(q,int(get(q,'virtual-time'))+100000000);pending=storage(q)
   if pending['kind']==1 and pending['media_deadline_ns']>int(get(q,'virtual-time')):break
  require(pending['kind']==1 and pending['media_deadline_ns']>int(get(q,'virtual-time')),'actual guest write did not reach declared media-delay boundary')
  report['pending_storage']=pending
 else:run(q,4000000000)
 events=guest_events(d/'uart.bin');report['boot_events']=events
 if a.cut!='storage':require(any(x[0]==0x420 for x in events) and any(x[0]==0x421 for x in events),'actual Ready/Save not observed')
 else:require(any(x[0]==0x423 for x in events) and not any(x[0]==0x421 for x in events),'storage boundary must be genuine unacknowledged guest Save')
 now=int(get(q,'virtual-time'))
 if a.cut!='storage':
  stream=Input(1650,2200,now//10+1,100,100);stream.sample(472,144,512,True);stream.sample(472,144,0,False)
  for event in stream.events:put(q,'external-event',' '.join(str(x) for x in [event[1]*10,*event[1:8]]))
 if a.cut=='converter':
  report['capture_guest_progress']=[]
  for quantum in range(10):
   run(q,int(get(q,'virtual-time'))+100000000)
   state=json.loads(get(q,'execution-state'));report['capture_guest_progress'].append(state)
   if any(x['state']==5 for x in state['mm_streams']):break
  require(any(x['state']==5 for x in state['mm_streams']),'actual Capture UI did not start acquisition within100M functional units')
  now=int(get(q,'virtual-time'))
 # Explicit extra raw UART stimuli are included; they are not guest packet or
 # acquisition claims. The controller must retain pending bytes at this cut.
 put(q,'external-uart-paced',str(now+10)+' 10 '+('00'*4096));run(q,now+1000000)
 report['after_raw_capture_tap']=observed(q);uart=json.loads(get(q,'raw-uart-state'));require(uart['blocked'] and uart['pending']>0 and not uart['timer_pending'],'no actual blockedflow cut')
 if a.cut=='converter':
  timer=json.loads(get(q,'execution-state'));require(timer['mm_timer_pending'],'actual active acquisition timer absent')
  run(q,timer['mm_timer_expires_ns']+8);report['inside_conversion']=observed(q)
  require(any(x['converting'] for x in json.loads(get(q,'execution-state'))['mm_streams']),'actual nexttimer+8ns did not retain conversion')
 active=[x for x in json.loads(get(q,'execution-state'))['mm_streams'] if x['converting']]
 report['active_mm_streams']=active;report['active_mm_qualified']=bool(active)
 before=observed(q);cut,tlb=save(q,d,'cut');cutmedium=export(q,d,'cut-medium.raw');require(observed(q)==before,'capture/export changed digital state');uart_start=(d/'uart.bin').stat().st_size
 suffix_start=int(get(q,'virtual-time'));until=(pending['media_deadline_ns']+2000000000 if a.cut=='storage' else suffix_start+1000000)
 require(0<=until-suffix_start<=report['limits']['suffix_ns'],'prospective virtual suffix bound');report['actual_suffix_ns']=until-suffix_start
 run(q,until);left=observed(q);leftmain,lefttlb=save(q,d,'suffix');leftmedium=export(q,d,'suffix-medium.raw');leftuart=(d/'uart.bin').read_bytes()[uart_start:]
 if a.cut=='storage':require(any(x[0]==0x421 for x in guest_events(d/'uart.bin')),'pending Save did not later acknowledge after actual media completion')
 f,fd=launch('fork',cutmedium);f.execute('lemma-load-machine-softtlb',{'filename':str(cut),'cache-filename':str(tlb)});require(observed(f)==before,'loaded Ready/blocked boundary differs');fork_start=(fd/'uart.bin').stat().st_size;run(f,until);right=observed(f);rightmain,righttlb=save(f,fd,'suffix');rightmedium=export(f,fd,'suffix-medium.raw');require(left==right,'suffix controller observation differs');require(leftuart==(fd/'uart.bin').read_bytes()[fork_start:],'suffix actual UART bytes differ');require(sha(leftmedium)==sha(rightmedium),'suffix durable medium differs')
 report['controller_and_uart_suffix_equal']=True;report['durable_suffix_equal']=True
 relation=compare_machine(leftmain.read_bytes(),rightmain.read_bytes());translations=compare_logical(lefttlb.read_bytes(),righttlb.read_bytes(),leftmain.read_bytes(),rightmain.read_bytes())
 # Forge the outer file bindings coherently so the actual required UART
 # VMState validation, after partial candidate load, must reject blocked+noFlow.
 bad=bytearray(cut.read_bytes());marker=b'\x11lemma-paper-pen/1'+struct.pack('>II',0,5);require(bad.count(marker)==1,'exact parent section marker');at=bad.index(marker)+len(marker);require(bad[at:at+3]==b'\x01\x01\x01','actual enabled/flow/blocked prefix');bad[at+1]=0;badpath=root/'malformed.qemu';badpath.write_bytes(bad);cache=bytearray(tlb.read_bytes());length=struct.unpack_from('<Q',cache,16)[0];cache[24+length:24+length+32]=hashlib.sha256(bad).digest();cache[-32:]=hashlib.sha256(cache[:-32]).digest();badcache=root/'malformed.tlb';badcache.write_bytes(cache)
 original_before=observed(q);c,cd=launch('malformed-candidate',cutmedium)
 try:c.execute('lemma-load-machine-softtlb',{'filename':str(badpath),'cache-filename':str(badcache)})
 except RuntimeError as error:report['malformed_rejection']=str(error)
 else:raise RuntimeError('malformed blocked state accepted')
 require(observed(q)==original_before,'rejected candidate changed original')
 report.update(status='PASS_ACTUAL_NATIVE_LOGICAL2_SUFFIX',capture_nonmutating=True,loaded_boundary_equal=True,vmstate_relation=relation,logical_translation_relation=translations,durable_suffix_sha256=sha(leftmedium),actual_uart_suffix_equal=True,malformed_candidate_rejected=True,original_unchanged=True,cut={'bytes':cut.stat().st_size,'sha256':sha(cut),'logical_bytes':tlb.stat().st_size,'logical_sha256':sha(tlb),'backing_sha256':sha(cutmedium)},final=left)
except BaseException as error:report['error']=repr(error);report['observer_traceback']=traceback.format_exc()
finally:
 for p,q,log in live:
  try:
   if p.poll() is None and q is not None:q.execute('quit')
  except BaseException:pass
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  if q is not None:q.close()
  log.close()
 for socket_directory in sockets:socket_directory.cleanup()
 report['owned_processes_reaped']=all(p.poll() is not None for p,q,log in live);report['seconds']=time.monotonic()-start;(root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],report.get('error',''))
sys.exit(0 if report['status'].startswith('PASS') else 1)
