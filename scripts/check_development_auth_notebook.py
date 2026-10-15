#!/usr/bin/env python3
"""Real RTL public-development-key ROM -> guest-installed product notebook ->
raw pen/Saved -> independent authenticated cold recovery, all pixels/bytes.
Host only transports opaque sectors/raw input and observes output. Public test
key; no production identity, full update/power, course or browser qualification.
"""
import argparse,hashlib,json,os,shutil,struct,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
import lemmasim_auth as auth
import lemmasim_session as sessions
from product_native import sha
from package_product_image import package as validate_package
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from store_oracle import recover
from inspect_notebook import inspect_page
from notebook_pixels import empty_pixels
from notebook_input import Input
from check_canonical_pen_pixels import expected_stroke
from check_live_notebook import guest_events,visible_pixels

def require(v,m):
 if not v:raise RuntimeError(m)
def expected_home(records):
 root=records[1,1].payload;require(struct.unpack_from('<3Q',root)==(0x314b4e49414d454c,1,1),'source root format');pages=struct.unpack_from('<Q',root,24)[0];require(1<=pages<=64,'valid retained notebook page count')
 pixels=bytearray(empty_pixels(1650,2200))
 for obj,stroke,visible in inspect_page(records[1,257].payload,257):
  if not visible:continue
  raw=records[1,obj].payload;count=struct.unpack_from('<Q',raw,48)[0];require(0<count<=384 and len(raw)==128+72*count,'actual raw format')
  samples=[struct.unpack_from('<9Q',raw,128+72*i)for i in range(count)]
  for x,y in expected_stroke(samples)[1]:pixels[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
 return bytes(pixels)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--public-development-key',action='store_true',required=True)
 for name in ('prepared','guest-build','guest-source-archive','package','tag','disk','work-dir'):p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=a.work_dir.resolve();require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused ignored output required');out.mkdir();started=time.monotonic();end=started+21600;processes=[];total=0;report={'status':'FAIL','scope':__doc__,'bounds':{'whole_seconds':21600,'install_cycles':600000000,'install_seconds':3600,'ready_each_cycles':1300000000,'ready_each_seconds':7200,'raw_save_cycles':300000000,'raw_save_seconds':3600,'aggregate_cycles':3500000000,'automatic_restart':False},'phases':[],'receipts':[]}
 def update():(out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
 def launch(name,boot,disk,recovery):
  live=out/name;argv=[sys.executable,str(ROOT/'scripts/lemmasim_auth.py'),'--public-development-key','launch','--prepared',str(a.prepared.resolve()),'--session-dir',str(live),'--boot-medium',str(boot),'--disk',str(disk),'--paused','--headless','--mode','laboratory','--timeout','120','--host-threads','1']
  if recovery:argv+=['--recovery']
  log=(out/(name+'.log')).open('xb');proc=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);processes.append((proc,live,log));deadline=time.monotonic()+30
  while not(live/'session.json').is_file():require(proc.poll() is None and time.monotonic()<deadline,'new native session did not open');time.sleep(.05)
  return live
 def call(live,value):require(time.monotonic()<end,'original whole deadline');return sessions.request(live,value,120)
 def phase(live,label,cap,seconds,predicate):
  nonlocal total
  begin=call(live,{'action':'inspect'})['machine']['cycle'];t=time.monotonic()
  while True:
   st=call(live,{'action':'inspect'})['machine'];rows=guest_events(live/'uart.bin');require(not st['finished'] and not any(r[0] in (0x41f,0xd4,0xf4,0x424)for r in rows),'format/fault/exit/failedSave in '+label)
   if predicate(st,rows):break
   used=st['cycle']-begin;require(used<cap and time.monotonic()-t<seconds and total<3500000000,'original target/host bound: '+label);n=min(1000000,cap-used,3500000000-total);call(live,{'action':'run','cycles':n});total+=n
  report['phases'].append({'name':label,'initial_cycle':begin,'final_cycle':st['cycle'],'cycles':st['cycle']-begin,'seconds':time.monotonic()-t});update();print(label,st['cycle'],flush=True);return st
 def idle(st):return all(st[k]==0 for k in ('event_queue','pen_queue','uart_queue','paper_busy','panel_pending_pixels','block_state','dma_outstanding'))
 def full(live,st,expected):
  if not idle(st) or st['panel_completed']==0:return False
  panel=out/(live.name+'-observed.ppm');call(live,{'action':'panel','path':str(panel)});return visible_pixels(panel)==(1650,2200,expected)
 def close(live):
  proc,_,log=next(r for r in processes if r[1]==live)
  if proc.poll() is None:call(live,{'action':'destroy'})
  proc.wait(timeout=10);require(proc.returncode==0,'owned session close failed');log.close();processes.remove((proc,live,log))
 try:
  data,_,_=auth.prepared(a.prepared);report['prepared_manifest_sha256']=sha(a.prepared/'prepared.json');report['consumed_host_sources']={**data['host_scripts'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),'scripts/package_product_image.py':sha(ROOT/'scripts/package_product_image.py')}
  # Requalify the original ordinary Lean/LLVM/ELF source closure; no fresh
  # compilation is inferred, and packaging never writes the running medium.
  old=json.loads((a.package/'package.json').read_text());fresh=validate_package(a.guest_build,out/'revalidated-owner-package',old['identity'],a.guest_source_archive);wire=(a.package/'image.bin').read_bytes();require(fresh['image_sha256']==old['image_sha256']==hashlib.sha256(wire).hexdigest(),'audited opaque image differs');report['compiled_package']=fresh
  report['original_inputs']={str(a.disk.resolve()):sha(a.disk),str(a.tag.resolve()):sha(a.tag),str((a.package/'image.bin').resolve()):sha(a.package/'image.bin')};boot=out/'boot.raw';disk=out/'user.raw'
  with boot.open('xb')as f:f.truncate(auth.product.BOOT_BYTES);f.flush();os.fsync(f.fileno())
  shutil.copyfile(a.disk,disk);_,seq,before=recover(disk.read_bytes());require(seq==11,'declared original Saved11 medium required');expected=expected_home(before);report['original_store_sequence']=seq;report['expected_home_sha256']=hashlib.sha256(expected).hexdigest();live=launch('live',boot,disk,True);c=auth.RecoveryClient(SimpleNamespace(session_dir=live,timeout=3600,cycles=600000000,quantum=100000,transaction=1));report['beacon']=c.beacon();identity=c.call({'action':'inspect'})['identity'];auth.product.install_extent(old,wire,identity);install_start=time.monotonic()
  for i in range(len(wire)//512):
   receipt=c.send(1,slot=0,relative=i,identity=old['identity'],payload=wire[i*512:i*512+512]);require(receipt['status']==0,'actual image sector receipt failed');report['receipts'].append(receipt)
   if i%32==0:update()
  for op,kw in [(5,{'slot':0,'identity':old['identity'],'payload':a.tag.read_bytes()}),(2,{'slot':0,'identity':old['identity']})]:
   receipt=c.send(op,**kw);report['receipts'].append(receipt);require(receipt['status']==0,'actual tag/publication failed')
  receipt=c.send(3);report['receipts'].append(receipt);require(receipt['status']==0 and receipt['value']==0x80000000,'actual authenticated handoff absent');total+=c.used;require(time.monotonic()-install_start<3600,'original install host bound');report['install']={'cycles':c.used,'seconds':time.monotonic()-install_start,'payload_sectors':len(wire)//512,'running_image_preloaded':False};update()
  ready=phase(live,'authenticated-product-canonical-Ready',1300000000,7200,lambda st,rows:any(r[0]==0x420 for r in rows) and full(live,st,expected))
  initial=out/'ready-user.raw';call(live,{'action':'export-medium','path':str(initial)});require(initial.read_bytes()==a.disk.read_bytes(),'cold load changed acknowledged documents')
  stream=Input(1650,2200,ready['ticks']+10000,100000,0);stream.sample(825,160,0,False);stream.stroke('authenticated-product-writing',1,1,3,1600)
  for row in stream.events:call(live,{'action':'inject','kind':'pen','cycle':row[1]*10,'words':list(row[1:8])})
  newink=expected_stroke(stream.events[1:])[1];desired=bytearray(expected)
  for x,y in newink:desired[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
  saved=phase(live,'actual-raw-ink-and-acknowledged-Save',300000000,3600,lambda st,rows:any(r[0]==0x421 and r[1]>=seq+3 for r in rows) and full(live,st,bytes(desired)))
  ack=out/'acknowledged-user.raw';nv=out/'acknowledged-boot.raw';call(live,{'action':'export-medium','path':str(ack)});call(live,{'action':'export-boot-medium','path':str(nv)});_,afterseq,after=recover(ack.read_bytes());require(afterseq==seq+3 and expected_home(after)==bytes(desired),'actual committed raw/page/root differs');require(all(after[k].payload==v.payload for k,v in before.items()if k not in ((1,1),(1,257))),'new writing changed older objects');report['raw_pen']={'samples':stream.events,'raster_points':len(newink),'store_sequence':afterseq,'acknowledged_medium_sha256':sha(ack),'all_old_raw_objects_exact':True};close(live)
  coldboot=out/'cold-boot.raw';colddisk=out/'cold-user.raw';shutil.copyfile(nv,coldboot);shutil.copyfile(ack,colddisk);cold=launch('cold',coldboot,colddisk,False);phase(cold,'new-CPU-authenticated-cold-all-pixels',1300000000,7200,lambda st,rows:any(r[0]==0x420 for r in rows) and full(cold,st,bytes(desired)));recovered=out/'recovered-user.raw';call(cold,{'action':'export-medium','path':str(recovered)});require(sha(recovered)==sha(ack),'independent cold changed any acknowledged byte');close(cold)
  require(all(sha(n)==h for n,h in report['original_inputs'].items()),'original input changed');require(all(sha(ROOT/n)==h for n,h in report['consumed_host_sources'].items()),'consumed host source changed');report.update(status='PASS_ACTUAL_AUTHENTICATED_NOTEBOOK_RAW_SAVE_INDEPENDENT_COLD',snapshot_restore=False,all_expected_controller_pixels=True,all_acknowledged_bytes=True,total_cycles=total,not_qualified=['production identity/entropy/antirollback','interrupted authenticated update/power campaign','latest managed course/checking image','browser authenticated boot'])
 except BaseException as e:report['error']=repr(e)
 finally:
  for proc,live,log in processes:
   try:
    if proc.poll()is None:sessions.request(live,{'action':'destroy'},5)
   except BaseException:pass
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
   log.close()
  report['seconds']=time.monotonic()-started
  if report['seconds']>21600:report['status']='FAIL';report['deadline_exceeded']=True
  (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'],report.get('error'));return 0 if report['status'].startswith('PASS_')else 1
if __name__=='__main__':raise SystemExit(main())
