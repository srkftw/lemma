#!/usr/bin/env python3
"""Actual guest Store initialization through USB6 and an independent durable peer.

This verifies guest-authored journal roots and write receipts. It is not notebook
Ready/Save, cold document recovery, a physical USB PHY, or USB checkpoint closure.
"""
import argparse,json,os,signal,struct,subprocess,sys,threading,time
from pathlib import Path
from check_guest_usb_link import ROOT,crc64,decode_capture,guest_events,initialize,opaque,request,require,sha,validate
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from store_oracle import root_slot

def opaque_log(path):
 b=Path(path).read_bytes();require(b[:8]==struct.pack('<Q',0x3130474f4c434d4c),'independent peer log identity');rows=[];p=8
 while p<len(b):
  require(p+8<=len(b),'peer log length prefix');n=int.from_bytes(b[p:p+8],'little');p+=8
  require(72<=n<=584 and p+n<=len(b),'peer receipt bounds');f,payload=opaque(b[p:p+n]);p+=n;rows.append((f,payload))
 return rows

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host-prepared',type=Path,required=True);p.add_argument('--rtl-source-root',type=Path);p.add_argument('--guest-source-root',type=Path);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--lost-write-ack',action='store_true');p.add_argument('--cycles',type=int,default=120000000);p.add_argument('--deadline',type=int,default=900);a=p.parse_args()
 out=a.work_dir.resolve();require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused owned output');out.mkdir(parents=True)
 require(1<=a.cycles<=250000000 and 30<=a.deadline<=1800,'explicit bounded workload')
 started=time.monotonic();end=started+a.deadline;directory=out/'session';peer=out/'peer';sock=out/'peer.sock';state=out/'outbox';prepared=a.host_prepared.resolve();companion=prepared.parent/'companion/prepared.json';validate(companion);initialize(peer,writer=83)
 report={'schema':'lemma-usb-store-initialize-evidence/1','status':'FAIL','scope':__doc__,'cycle_bound':a.cycles,'host_bound_seconds':a.deadline,'lost_write_ack_requested':a.lost_write_ack,'host_prepared':{'path':str(prepared),'sha256':sha(prepared)}}
 owner=server=first_server=None;restart_thread=None;errors=[];logs=[];server_commands=[];commands=(out/'commands.jsonl').open('x');launch=(out/'launch.log').open('xb')
 def records():return guest_events(directory/'uart.bin') if (directory/'uart.bin').exists() else []
 def start_peer(drop=False):
  nonlocal server
  log=(out/('peer-'+str(len(logs))+'.log')).open('xb');logs.append(log)
  cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'companion','serve','--prepared',str(companion),'--directory',str(peer),'--socket',str(sock)]
  # Blank media mount performs two reads. The first guest format write is the
  # third actual opaque response; the independent log below checks this premise.
  if drop:cmd+=['--drop-reply','3','--exit-after-reply','3']
  server_commands.append(cmd);server=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);limit=time.monotonic()+15
  while not sock.exists():require(server.poll() is None and time.monotonic()<limit,'independent peer startup');time.sleep(.005)
  return server
 def control(q):
  require(time.monotonic()<end,'host bound exceeded');commands.write(json.dumps(q)+'\n');commands.flush();return request(directory,q,timeout=min(130,end-time.monotonic()))
 try:
  first_server=start_peer(a.lost_write_ack)
  if a.lost_write_ack:
   def restart():
    try:
     require(first_server.wait(timeout=a.deadline)==0,'lost-write-response peer exit')
     observed=opaque_log(peer/'opaque.log');require(len(observed)==1 and observed[0][0][2:6]==(1,83,1,4096) and len(observed[0][1])==512,'lost response was not first persisted guest write')
     before=records();require(not any(r[0]==0x41f for r in before),'guest acknowledged initialization before reconciliation')
     report['lost_ack_boundary']={'guest_records':before,'peer_log_sha256':sha(peer/'opaque.log'),'outbox_sha256':sha(state/'outbox'),'persisted_write_sequence':1};start_peer();report['peer_restarted']=True
    except BaseException as e:errors.append(str(e))
   restart_thread=threading.Thread(target=restart,daemon=True);restart_thread.start()
  cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.6.0','--workload','initializer','--session-dir',str(directory),'--mode','laboratory','--headless','--paused','--timeout','120','--quantum','1000','--usb-host-prepared',str(prepared),'--usb-peer-directory',str(peer),'--usb-peer-socket',str(sock),'--usb-host-state',str(state)]
  if a.rtl_source_root is not None:cmd+=['--rtl-source-root',str(a.rtl_source_root.resolve())]
  if a.guest_source_root is not None:cmd+=['--guest-source-root',str(a.guest_source_root.resolve())]
  report['argv']=cmd;owner=subprocess.Popen(cmd,cwd=ROOT,stdout=launch,stderr=subprocess.STDOUT,start_new_session=True);limit=time.monotonic()+60
  while not (directory/'session.json').exists():require(owner.poll() is None and time.monotonic()<limit,'source-bound public initializer startup');time.sleep(.02)
  initial=control({'action':'inspect'});report['identity']=initial['identity'];report['initial']=initial['machine'];require(initial['machine']['cycle']==0,'initializer did not start cold at reset');report['source_validated_public_startup']=True
  while not any(r[0]==0x41f for r in records()):
   notebook_ids={r[1] for r in records() if r[0]==0xf1 and r[2]==1}
   exited=[r for r in records() if r[0]==0xf4 and r[1] in notebook_ids and r[2]!=0]
   require(not exited,'actual initializer task exited before acknowledgment: '+str(exited))
   current=control({'action':'inspect'})['machine'];require(not current['finished'] and current['cycle']<a.cycles,'initializer failed or selected cycle bound exhausted');require(not errors,'peer restart failed: '+str(errors))
   control({'action':'run','cycles':min(2000000,a.cycles-current['cycle'])})
  report['final']=control({'action':'inspect'})['machine'];events=records();acks=[r for r in events if r[0]==0x41f];require(acks==[(0x41f,0,0,0,0)],'unexpected actual guest format acknowledgment');report['guest_records']=events
  wire=decode_capture(directory/'usb.raw',probe=False,writer=83);report['wire']=wire;transactions=wire['transactions'];require([t['request'][2] for t in transactions]==[0,0,1,2,1,2,1,2],'actual guest mount/format operation sequence')
  rows=opaque_log(peer/'opaque.log');require([f[4] for f,_ in rows]==list(range(1,7)) and [f[2] for f,_ in rows]==[1,2,1,2,1,2],'peer duplicated or omitted durable format effects')
  require([f[5] for f,_ in rows]==[4096,0,0,0,512,0],'guest wrote outside root/sentinel format locations')
  written={f[5]:payload for f,payload in rows if f[2]==1};require(written[4096]==bytes(512),'guest format sentinel differs')
  left=root_slot(written[0],524288);right=root_slot(written[512],524288);require(left is not None and left==right and left.generation==1 and left.checkpoint_count==left.checkpoint_tail==left.sequence==0,'actual guest journal roots invalid or inconsistent')
  require(written[0]==written[512],'guest root slot bytes differ');report['independent_root']={k:getattr(left,k) for k in left.__dataclass_fields__};report['root_sha256']=sha_bytes(written[0]);report['peer_log_sha256']=sha(peer/'opaque.log')
  outbox=(state/'outbox').read_bytes();require(len(outbox)==40 and struct.unpack('<4Q',outbox[:32])==(0x313054554f434d4c,83,7,0) and crc64(outbox[:-8])==int.from_bytes(outbox[-8:],'little'),'hosted policy retained unresolved or wrong receipt state');report['outbox_sha256']=sha(state/'outbox')
  if a.lost_write_ack:require(report.get('peer_restarted') and not errors,'lost ACK restart did not reconcile')
  report['status']='PASS'
 except BaseException as e:
  report['error']=str(e)
  try:
   if owner and owner.poll() is None:report['failure_machine']=control({'action':'inspect'})['machine']
   report['failure_guest_records']=records()
   if (peer/'opaque.log').exists():report['failure_peer_log_sha256']=sha(peer/'opaque.log');report['failure_peer_log_bytes']=(peer/'opaque.log').stat().st_size
  except BaseException as observer_error:report['failure_observer_error']=str(observer_error)
  raise
 finally:
  if owner and owner.poll() is None:
   try:control({'action':'destroy'});owner.wait(timeout=10)
   except BaseException:os.killpg(owner.pid,signal.SIGTERM);owner.wait(timeout=10)
  if server and server.poll() is None:os.killpg(server.pid,signal.SIGTERM);server.wait(timeout=10)
  if first_server and first_server.poll() is None:os.killpg(first_server.pid,signal.SIGTERM);first_server.wait(timeout=10)
  if restart_thread:restart_thread.join(timeout=10)
  for log in logs:log.close()
  commands.close();launch.close();report['owner_exit_code']=owner.returncode if owner else None;report['peer_argv']=server_commands;report['host_seconds']=time.monotonic()-started;report['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'cycle':report['final']['cycle'],'host_seconds':report['host_seconds']}))
def sha_bytes(b):
 import hashlib
 return hashlib.sha256(b).hexdigest()
if __name__=='__main__':main()
