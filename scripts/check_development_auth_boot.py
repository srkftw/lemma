#!/usr/bin/env python3
"""Actual shared RTL machine: guest install -> valid-CRC bad-MAC rejection ->
correct tag/publication -> authenticated handoff -> real RV64 SHA/HMAC payload.
Public development key only. This is not full notebook/update/power acceptance.
"""
import argparse,hashlib,hmac,json,os,struct,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
import lemmasim_auth as auth
import lemmasim_session as sessions
from product_native import sha
ROOT=Path(__file__).resolve().parents[1]
def require(value,message):
 if not value:raise RuntimeError(message)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--package',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--public-development-key',action='store_true',required=True);a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
 out.mkdir(parents=True);started=time.monotonic();deadline=started+1800;process=None;live=out/'live';r={'status':'FAIL','scope':__doc__,'bounds':{'whole_seconds':1800,'target_cycles':200000000,'command_quantum':100000,'automatic_restart':False},'receipts':[]}
 try:
  data,_,_=auth.prepared(a.prepared);r['prepared_sha256']=sha(a.prepared/'prepared.json');r['host_inputs']={**data['host_scripts'],str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))};package=json.loads((a.package/'package.json').read_text());wire=(a.package/'image.bin').read_bytes();require(sha(a.package/'image.bin')==package['image_sha256'],'changed actual compiled package');r['package']=package
  medium=out/'boot.raw'
  with medium.open('xb') as f:f.truncate(auth.product.BOOT_BYTES);f.flush();os.fsync(f.fileno())
  argv=[sys.executable,str(ROOT/'scripts/lemmasim_auth.py'),'--public-development-key','launch','--prepared',str(a.prepared.resolve()),'--session-dir',str(live),'--boot-medium',str(medium),'--recovery','--paused','--headless','--mode','laboratory','--timeout','120','--host-threads','1'];r['launch_argv']=argv
  log=(out/'session.log').open('xb');process=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while not (live/'session.json').is_file():
   require(process.poll() is None and time.monotonic()-started<30,'actual product session did not open');time.sleep(.05)
  c=auth.RecoveryClient(SimpleNamespace(session_dir=live,timeout=1800,cycles=200000000,quantum=100000,transaction=1));r['beacon']=c.beacon();r['identity']=c.call({'action':'inspect'})['identity'];auth.product.install_extent(package,wire,r['identity'])
  def send(operation,**kw):
   require(time.monotonic()<deadline,'original whole deadline');row=c.send(operation,**kw);r['receipts'].append({'operation':operation,**row});r['cycles']=c.used;(out/'progress.json').write_text(json.dumps(r,indent=2)+'\n');return row
  for i in range(len(wire)//512):require(send(1,slot=0,relative=i,identity=package['identity'],payload=wire[i*512:i*512+512])['status']==0,'actual payload write rejected')
  bad=(a.package/'slot0-bad-mac-valid-crc.tag').read_bytes();good=(a.package/'slot0.tag').read_bytes();require(len(bad)==len(good)==512 and bad[:48]==good[:48] and bad[48:80]!=good[48:80],'bad-MAC independent control missing')
  import zlib
  require(struct.unpack_from('<Q',bad,504)[0]==zlib.crc32(bad[:504]),'negative tag must pass CRC')
  require(send(5,slot=0,identity=package['identity'],payload=bad)['status']==0,'bad-MAC structure/barrier receipt absent')
  before=out/'before-publication.raw';c.call({'action':'export-boot-medium','path':str(before)})
  rejected=send(2,slot=0,identity=package['identity']);require(rejected['status']==240,'CRC-valid bad MAC was not rejected by actual ROM')
  after=out/'after-rejection.raw';c.call({'action':'export-boot-medium','path':str(after)});require(before.read_bytes()==after.read_bytes(),'rejected publication altered medium');require(after.read_bytes()[:1024]==bytes(1024),'rejected image gained boot metadata')
  r['bad_MAC']={'valid_transport_and_sector_CRC':True,'actual_ROM_status':240,'all_boot_medium_bytes_unchanged':True,'no_metadata_publication':True};print('ACTUAL_BAD_MAC_REJECTED',c.used,flush=True)
  require(send(5,slot=0,identity=package['identity'],payload=good)['status']==0,'correct tag barrier absent');require(send(2,slot=0,identity=package['identity'])['status']==0,'correct actual MAC publication failed')
  receipt=send(4,slot=0,identity=package['identity']);require(receipt['status']==0 and receipt['value']==1,'fresh barrier/authenticated status receipt absent')
  boot=send(3);require(boot['status']==0 and boot['value']==0x80000000,'authenticated actual handoff failed');cursor=c.cursor;uart=live/'uart.bin'
  while len(uart.read_bytes())-cursor<776:
   require(time.monotonic()<deadline and c.used<200000000,'actual payload deadline');count=min(100000,200000000-c.used);c.call({'action':'run','cycles':count});c.used+=count
  observed=uart.read_bytes()[cursor:];require(len(observed)==776 and observed[-8:]==struct.pack('<Q',0x31444e45414d454c),'actual payload length/end differs');cases=[]
  for i,n in enumerate([0,1,55,56,57,63,64,65,129,4096,3,8]):
   magic,case,status,count=struct.unpack_from('<4Q',observed,i*64);message=bytes((j*37+11)%256 for j in range(n)) if i<10 else b'abc' if i==10 else b'Hi There';expected=hashlib.sha256(message).digest() if i<11 else hmac.new(b'\x0b'*20,message,hashlib.sha256).digest();actual=observed[i*64+32:i*64+64]
   require((magic,case,status,count)==(0x31414853414d454c,i if i<10 else i+90,0,n) and actual==expected,'real authenticated RV64 digest differs');cases.append({'case':case,'bytes':n,'digest':actual.hex()})
  final=out/'acknowledged-boot.raw';c.call({'action':'export-boot-medium','path':str(final)});r.update(status='PASS_ACTUAL_RTL_DEVELOPMENT_AUTH_INSTALL_HANDOFF',cycles=c.used,actual_payload=cases,acknowledged_boot_sha256=sha(final),acknowledged_boot_path=str(final),not_qualified=['production key/entropy/trust state/antirollback','independent cold authenticated fallback','full OS/notebook/documents','interrupted tag/payload/confirmation/power campaign','browser auth boot'])
  require(all(sha(ROOT/n)==h for n,h in r['host_inputs'].items()),'actual auth observer source changed')
 except BaseException as e:r['error']=repr(e)
 finally:
  if process is not None:
   try:
    if process.poll() is None:sessions.request(live,{'action':'destroy'},5)
   except BaseException:pass
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
   r['launcher_reaped']=process.returncode is not None
  r['seconds']=time.monotonic()-started
  if r['seconds']>1800:r['status']='FAIL';r['deadline_error']=True
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({'status':r['status'],'seconds':r['seconds'],'error':r.get('error')},indent=2));return 0 if r['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
