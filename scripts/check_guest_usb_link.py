#!/usr/bin/env python3
"""Independent actual checked RV64 USB6 control/owned buffer/opaque peer probe.

No notebook/physical PHY/full USB/checkpoint claims. The decoder only observes
captured packets and retained peer bytes; nothing is supplied to guest policy.
"""
import argparse,hashlib,json,os,signal,struct,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from lemmasim_session import request
from lemmasim_companion import initialize,validate
from check_notebook_workflow import guest_events

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def crc64(b):
 r=0
 for v in b:
  r^=v<<56
  for _ in range(8):r=((r<<1)^(0x42f0e1eba9ea3693 if r>>63 else 0))&((1<<64)-1)
 return r
def reverse(v,n):return int(f'{v:0{n}b}'[::-1],2)
def wirecrc(data,width,polynomial):
 r=(1<<width)-1;mask=r
 for v in data:
  for bit in range(8):
   top=(r>>(width-1))^((v>>bit)&1)
   r=(r<<1)&mask
   if top:r^=polynomial
 return reverse(r^mask,width)
def packet(p):
 require(p and len(p)<=67 and ((p[0]>>4)^(p[0]&15))==15,'PID/packet bound')
 if p[0] in (0xc3,0x4b):
  require(len(p)>=3 and wirecrc(p[1:-2],16,0x8005)==int.from_bytes(p[-2:],'little'),'data CRC16')
  return ('data',p[0]==0x4b,p[1:-2])
 if p[0] in (0x2d,0xe1,0x69):
  require(len(p)==3,'token length');v=int.from_bytes(p[1:],'little');r=31
  for bit in range(11):
   top=(r>>4)^((v>>bit)&1);r=(r<<1)&31
   if top:r^=5
  require(reverse(r^31,5)==v>>11,'token CRC5')
  return ('token',p[0],v&127,(v>>7)&15)
 require(p[0] in (0xd2,0x5a,0x1e) and len(p)==1,'handshake shape')
 return ('handshake',p[0])
def opaque(b):
 require(len(b)>=72 and len(b)<=584 and len(b)%8==0 and crc64(b[:-8])==int.from_bytes(b[-8:],'little'),'opaque frame CRC/bound')
 f=struct.unpack('<8Q',b[:64]);require(f[:2]==(0x313030504d434d4c,1) and len(b)==72+(f[6] if f[2] in (1,3) else 0),'opaque header length')
 return f,b[64:-8]
def decode_capture(path):
 rows=Path(path).read_text().splitlines();require(rows and rows[0].startswith('LMUSBRW1 ') and len(rows[0].split()[1])==64,'raw capture identity')
 issued={};last=0;cycle=0;setups=[];requests=[];responses=[];req=bytearray();resp=bytearray();token=None;pending_out=None;pending_in=None;in_one=False;out_one=False;controls=[];counts={'host_packets':0,'controller_packets':0,'nak':0}
 for row in rows[1:]:
  fields=row.split(' ',3);require(len(fields)==4,'raw capture framing');tick,kind,key=map(int,fields[:3]);frame=fields[3]
  require(tick>=cycle and kind in (0,1),'accepted capture ordering');cycle=tick
  if kind==0:
   require(key==last+1 and key not in issued,'stable raw request ID');last=key;issued[key]=frame
  else:
   require(key in issued,'reply without request');command=issued.pop(key)
   if command.startswith('SEND '):
    require(frame=='SENT','send accepted bytes reply');p=bytes.fromhex(command[5:]);d=packet(p);counts['host_packets']+=1
    if d[0]=='token':token=d
    elif d[0]=='data':
     require(token and token[0]=='token' and token[1] in (0x2d,0xe1),'OUT data token context')
     if token[1]==0x2d:
      require(token[3]==0 and not d[1] and len(d[2])==8,'SETUP payload');setups.append(int.from_bytes(d[2],'little'))
     elif token[3]==2:
      require(pending_out is None,'unresolved bulk OUT handshake');pending_out=d
    elif d==('handshake',0xd2) and pending_in is not None:
     require(pending_in[1]==in_one,'ACKed bulk IN toggle');in_one=not in_one;req.extend(pending_in[2])
     if len(pending_in[2])<64:requests.append(bytes(req));req.clear()
     pending_in=None
   elif command=='RECV':
    require(frame.startswith('RX '),'raw controller reply');d=packet(bytes.fromhex(frame[3:]));counts['controller_packets']+=1
    if token and (token[1]==0x2d or (token[1]==0xe1 and token[3]==0)):
     require(d==('handshake',0xd2),'control SETUP/OUT status handshake')
    if d[0]=='data' and token and token[1]==0x69 and token[3]==1:
     require(pending_in is None,'unresolved bulk IN ACK');pending_in=d
    elif d[0]=='data' and token and token[1]==0x69 and token[3]==0:
     require(d[1],'control did not start DATA1');controls.append(d[2])
    if pending_out is not None:
     require(d in (('handshake',0xd2),('handshake',0x5a)),'bulk OUT handshake')
     require(pending_out[1]==out_one,'pending bulk OUT toggle')
     if d==('handshake',0xd2):
      out_one=not out_one;resp.extend(pending_out[2])
      if len(pending_out[2])<64:responses.append(bytes(resp));resp.clear()
     pending_out=None
    if d==('handshake',0x5a):counts['nak']+=1
   elif command=='USBHOST/1 PACKET_BYTES_DEV':require(frame=='OPEN','raw handshake')
   elif command.startswith('RESET '):require(command=='RESET 5000000' and frame=='RESET_DONE','real root reset duration')
   elif command.startswith('WAIT '):require(frame=='WAIT_DONE','virtual wait completion')
   else:raise ValueError('unadmitted raw command')
 require(not req and not resp and pending_in is None and pending_out is None,'incomplete observed opaque frame')
 require(controls==[bytes([18,1,0,2,0,0,0,64,0,0,0,0,0,1,0,0,0,1]),b'',bytes([9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,129,2,64,0,0,7,5,2,2,64,0,0]),b'',b'\x01'],'actual guest-produced control descriptor/status bytes')
 expected=[0x0012000001000680,0x0000000000070500,0x0020000002000680,0x0000000000010900,0x0001000000000880]
 require(setups==expected,'actual standard request sequence changed')
 require(len(requests)==len(responses)==3,'actual opaque transaction count')
 require(requests[0]==b'LMCUSB01' and len(responses[0])==32,'actual hello')
 hello=struct.unpack('<4Q',responses[0]);require(hello==(0x3130425355434d4c,73,1,268435456),'actual hello identity')
 barrier,_=opaque(requests[1]);receipt,_=opaque(responses[1]);read,_=opaque(requests[2]);data,body=opaque(responses[2])
 require(barrier==(0x313030504d434d4c,1,2,73,1,0,0,0),'actual guest barrier request')
 require(receipt==(0x313030504d434d4c,1,3,73,1,0,0,0),'actual durable barrier receipt')
 require(read==(0x313030504d434d4c,1,0,73,0,0,512,0),'actual guest read request')
 require(data==(0x313030504d434d4c,1,3,73,0,0,512,0) and body==bytes(512),'actual opaque read bytes')
 return {'rows':len(rows)-1,'last_cycle':cycle,'counts':counts,'requests':[b.hex() for b in requests],'responses_sha256':[hashlib.sha256(b).hexdigest() for b in responses],'pending_raw_request':issued,'sha256':sha(path)}
def peer_log(path):
 b=Path(path).read_bytes();require(b[:8]==struct.pack('<Q',0x3130474f4c434d4c),'durable peer log identity');pos=8;rows=[]
 while pos<len(b):
  require(pos+8<=len(b),'truncated peer receipt length');n=int.from_bytes(b[pos:pos+8],'little');pos+=8;require(pos+n<=len(b),'truncated durable peer receipt');f,_=opaque(b[pos:pos+n]);rows.append(f);pos+=n
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--host-prepared',type=Path,required=True);p.add_argument('--lost-ack',action='store_true');p.add_argument('--cycles',type=int,default=60000000);p.add_argument('--deadline',type=int,default=900);a=p.parse_args()
 out=a.work_dir.resolve();require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused owned output');out.mkdir(parents=True)
 started=time.monotonic();end=started+a.deadline;directory=out/'session';peer=out/'peer';sock=out/'peer.sock';state=out/'outbox';initialize(peer,writer=73)
 prepared=a.host_prepared.resolve();companion=prepared.parent/'companion/prepared.json';validate(companion)
 report={'schema':'lemma-usb-rv64-peer-evidence/1','status':'FAIL','scope':'actual checked privileged RV64 USB6 enumeration/owned-buffer negatives/barrier/read over decoded packet circuit and independent hosted Lean durable opaque peer; no notebook Save/fullUSB/PHY/checkpoint claim','cycle_bound':a.cycles,'host_bound_seconds':a.deadline,'lost_ack_requested':a.lost_ack}
 owner=None;server=None;server_logs=[];server_commands=[];command_log=(out/'commands.jsonl').open('x');launch=(out/'launch.log').open('xb');restart_error=[];restart_thread=None
 def start_peer(drop=0):
  nonlocal server
  log=(out/('peer-'+str(len(server_logs))+'.log')).open('xb');server_logs.append(log)
  cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'companion','serve','--prepared',str(companion),'--directory',str(peer),'--socket',str(sock)]
  if drop:cmd+=['--drop-reply','1','--exit-after-reply','1']
  server_commands.append(cmd);server=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  bound=time.monotonic()+15
  while not sock.exists():require(server.poll() is None and time.monotonic()<bound,'independent peer startup');time.sleep(.005)
  return server
 def control(q):
  require(time.monotonic()<end,'host bound exceeded');command_log.write(json.dumps(q)+'\n');command_log.flush();return request(directory,q,timeout=min(130,end-time.monotonic()))
 def records():return [r for r in guest_events(directory/'uart.bin') if 0x460<=r[0]<=0x465]
 try:
  first_server=start_peer(1 if a.lost_ack else 0)
  if a.lost_ack:
   def restart():
    try:
     require(first_server.wait(timeout=a.deadline)==0,'lost-reply peer exit');report['lost_ack_before_reconciliation']={'records':records(),'peer_receipts':peer_log(peer/'opaque.log'),'outbox_sha256':sha(state/'outbox')}
     require(not any(r[0]==0x462 for r in records()),'guest acknowledged before lost receipt reconciliation');start_peer();report['peer_restarted']=True
    except BaseException as e:restart_error.append(str(e))
   restart_thread=threading.Thread(target=restart,daemon=True);restart_thread.start()
  cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.6.0','--workload','usb','--session-dir',str(directory),'--mode','laboratory','--headless','--paused','--timeout','120','--quantum','1000','--usb-host-prepared',str(prepared),'--usb-peer-directory',str(peer),'--usb-peer-socket',str(sock),'--usb-host-state',str(state)]
  report['argv']=cmd;owner=subprocess.Popen(cmd,cwd=ROOT,stdout=launch,stderr=subprocess.STDOUT,start_new_session=True);bound=time.monotonic()+60
  while not (directory/'session.json').exists():require(owner.poll() is None and time.monotonic()<bound,'source-bound public machine startup failed');time.sleep(.02)
  initial=control({'action':'inspect'});report['identity']=initial['identity'];report['initial']=initial['machine'];require(initial['machine']['cycle']==0,'machine was not cold paused at reset');report['source_validated_public_startup']=True
  while not any(r[0]==0x464 for r in records()):
   machine=control({'action':'inspect'})['machine'];require(not machine['finished'] and machine['cycle']<a.cycles,'actual USB guest failed or selected scenario cycle bound exhausted');require(not restart_error,'peer restart failed: '+str(restart_error));control({'action':'run','cycles':min(250000,a.cycles-machine['cycle'])})
  final=control({'action':'inspect'})['machine'];report['final']=final;report['guest_records']=records();codes=[r[0] for r in records()];require(codes==[0x460,0x461,0x465,0x462,0x463,0x464],'actual guest receipt order/owned-head rejection check')
  require(records()[1][1:]==(524288,16,64,0),'actual capacity discovery');require(records()[3][1:]==(1,5,0,0),'guest accepted wrong durable barrier');require(records()[4][1:4]==(2,1,0),'guest accepted wrong read completion');require(records()[5][1:]==(1,16,64,0),'actual guest final scope')
  report['raw_packets']=decode_capture(directory/'usb.raw');rows=peer_log(peer/'opaque.log');require(rows==[(0x313030504d434d4c,1,2,73,1,0,0,0)],'independent peer duplicated or changed durable barrier effect');report['durable_receipts']=[list(r) for r in rows]
  b=(state/'outbox').read_bytes();require(len(b)==40 and struct.unpack('<4Q',b[:32])==(0x313054554f434d4c,73,2,0) and crc64(b[:-8])==int.from_bytes(b[-8:],'little'),'durable outbox failed to reconcile exactly one sequence');report['outbox_sha256']=sha(state/'outbox')
  if a.lost_ack:require(report.get('peer_restarted') and not restart_error,'lost ACK peer restart did not complete')
  report['status']='PASS'
 except BaseException as e:report['error']=str(e);raise
 finally:
  if owner:
   if owner.poll() is None:
    try:control({'action':'destroy'});owner.wait(timeout=10)
    except BaseException:os.killpg(owner.pid,signal.SIGTERM);owner.wait(timeout=10)
   report['owner_exit_code']=owner.returncode
  if server and server.poll() is None:os.killpg(server.pid,signal.SIGTERM);server.wait(timeout=10)
  if 'first_server' in locals() and first_server.poll() is None:os.killpg(first_server.pid,signal.SIGTERM);first_server.wait(timeout=10)
  if restart_thread:restart_thread.join(timeout=10)
  for log in server_logs:log.close()
  command_log.close();launch.close();report['host_seconds']=time.monotonic()-started;report['peer_argv']=server_commands;report['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'cycle':report['final']['cycle'],'seconds':report['host_seconds']}))
if __name__=='__main__':main()
