#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Genuine checked RV64 BLE PIO/IRQ probe, sampled packet peer, captured suffix.

Manual unauthenticated LE1M context only. No connection, RF, full Bluetooth,
USB or notebook companion durability. Pending continuation has its own checker.
"""
import argparse,csv,hashlib,json,os,shutil,signal,subprocess,sys,time
from pathlib import Path
from lemmasim_session import request
from check_ble_wire_peer import encode
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from check_notebook_workflow import guest_events

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()
def require(value,message):
 if not value:raise ValueError(message)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--boot-cycles',type=int,default=20000000);p.add_argument('--deadline',type=int,default=360)
 args=p.parse_args();out=args.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused work-dir under build required')
 if not 1000000<=args.boot_cycles<=30000000 or not 60<=args.deadline<=900:p.error('bounded cycle/host deadline differs')
 out.mkdir(parents=True);directory=out/'session';started=time.monotonic();deadline=started+args.deadline
 command=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.5.0',
  '--workload','ble','--session-dir',str(directory),'--mode','laboratory','--headless','--paused','--timeout','120','--quantum','1000',
  '--ble-peer',shutil.which('nix'),'--ble-peer-arg=develop','--ble-peer-arg=--no-write-lock-file','--ble-peer-arg=--command',
  '--ble-peer-arg=lake','--ble-peer-arg=env','--ble-peer-arg=lean','--ble-peer-arg=--run',
  '--ble-peer-arg=sim/radio/ble_peer.lean','--ble-drop-packets','1']
 result={'schema':'lemma-ble-whole-machine-evidence/1','status':'FAIL','scope':'checked privileged RV64 manual LE1M PIO/IRQ15 exchange, actual hosted Lean policy, real lost sampled ACK and resolved-policy exact native outcome-tape fork','argv':command}
 commands=(out/'commands.jsonl').open('x');log=(out/'launch.log').open('xb');process=None
 def control(value):
  require(time.monotonic()<deadline,'declared whole-machine host bound exceeded');commands.write(json.dumps(value)+'\n');commands.flush()
  return request(directory,value,timeout=min(130,deadline-time.monotonic()))
 def inspect():return control({'action':'inspect'})['machine']
 def run(n):return control({'action':'run','cycles':n})
 def records():return [row for row in guest_events(directory/'uart.bin') if 0x450<=row[0]<=0x453]
 def rejected(value,needle):
  before=inspect();tape=sha(directory/'ble.outcomes')
  try:control(value)
  except RuntimeError as e:require(needle in str(e),'unexpected rejection: '+str(e));message=str(e)
  else:raise ValueError('operation outside admitted state was accepted')
  require(inspect()==before and sha(directory/'ble.outcomes')==tape,'rejected operation changed machine or external capture')
  return message
 try:
  process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  startup=min(deadline,time.monotonic()+60)
  while not (directory/'session.json').exists():
   require(process.poll() is None,'source-bound public startup failed; see launch.log');require(time.monotonic()<startup,'owner startup bound');time.sleep(0.02)
  first=control({'action':'inspect'});result['identity']=first['identity'];result['initial']=first['machine']
  require(first['machine']['cycle']==0 and first['machine']['ble']['pending_external']==1,'cold live peer startup was not represented as Pending')
  before=inspect();tape=sha(directory/'ble.outcomes');t=time.monotonic()
  control({'action':'snapshot','path':str(out/'startup-pending')})
  require(inspect()==before and sha(directory/'ble.outcomes')==tape,'startup Pending snapshot polled/drained/mutated original work')
  result['startup_pending_snapshot']={'seconds':time.monotonic()-t,'cycle':before['cycle']}
  result['source_validated_public_startup']=True
  snapshot=None
  while snapshot is None:
   state=inspect();require(not state['finished'] and state['cycle']<args.boot_cycles,'guest did not reach first packet wire bound')
   require(not any(row[0] in (0x452,0x453) for row in records()),'guest ended before in-flight snapshot')
   if state['ble']['peer_tx_active'] and state['ble']['accepted_replies']==2 and not state['ble']['pending_external']:
    snapshot=out/'inflight';t=time.monotonic();control({'action':'snapshot','path':str(snapshot)});result['snapshot_seconds']=time.monotonic()-t;result['snapshot_state']=state
    require(inspect()==state,'snapshot polled/drained/mutated live machine')
   else:run(1000)
  while not any(row[0]==0x452 for row in records()):
   state=inspect();require(not state['finished'] and state['cycle']<args.boot_cycles and not any(row[0]==0x453 for row in records()),'real guest failed/exhausted link retry')
   run(10000)
  final=inspect();result['final']=final;result['guest_records']=records()
  require([row[1] for row in records() if row[0]==0x450]==[0,1],'guest retry attempts differ from lost ACK scenario')
  require(len([row for row in records() if row[0]==0x451 and row[1]==15])==1,'actual guest did not consume IRQ15 decoded ACK once')
  require(final['ble']['chip_tx_packets']==2 and final['ble']['peer_rx_packets']==2 and final['ble']['peer_tx_packets']==2 and final['ble']['chip_rx_packets']==1 and final['ble']['dropped_packets']==1,'actual packet/controller counts differ')
  require('ACCEPTED 1 DUPLICATES 1 PENDING 12 4c4d434d5030303101000200' in final['ble']['accepted_state'],'genuine hosted Lean retained wrong opaque bytes/dedup state')
  require(not final['ble']['chip_crc_errors'] and not final['ble']['peer_crc_errors'],'valid packets caused controller CRC errors')
  rows=list(csv.DictReader((directory/'ble-wire.csv').open()))
  chip=''.join(row['bit'] for row in rows if row['endpoint']=='chip');peer=''.join(row['bit'] for row in rows if row['endpoint']=='peer')
  payload=list(bytes.fromhex('4c4d434d5030303101000200'));expected_chip=encode(2,payload)*2;expected_peer=encode(5,[])*2
  require(chip==expected_chip and peer==expected_peer,'whole-machine generated samples differ from independent CRC/whitening reference')
  delivered=[row['delivered'] for row in rows if row['endpoint']=='peer']
  require(delivered==['0']*len(encode(5,[]))+['1']*len(encode(5,[])),'wire fault did not drop exactly one complete ACK packet')
  result['independent_sample_vector']={'chip_bits':len(chip),'peer_bits':len(peer),'chip_sha256':hashlib.sha256(chip.encode()).hexdigest(),'peer_sha256':hashlib.sha256(peer.encode()).hexdigest()}
  finish=out/'live-complete';control({'action':'snapshot','path':str(finish)});original_tape=directory/'ble.outcomes';original_hash=sha(original_tape)
  before_uart=(directory/'uart.bin').stat().st_size;control({'action':'restore','path':str(snapshot)});restored=inspect()
  require(restored['ble']['fork_suspended'] and restored['cycle']==result['snapshot_state']['cycle'],'no-tape fork did not remain suspended')
  result['no_tape_rejection']=rejected({'action':'run','cycles':1},'captured outcomes')
  # A request-frame mutation with a valid framing shape must still be rejected
  # against the exact previously accepted checkpoint outcome before advancing.
  bad=out/'wrong-context.outcomes';wire=bytearray(original_tape.read_bytes());needle=b'PENDING 12 4c4d434d5030303101000200';at=wire.find(needle);require(at>=0,'captured opaque prefix absent');wire[at+len(needle)-1]=ord('1');bad.write_bytes(wire)
  result['wrong_context_rejection']=rejected({'action':'ble-outcomes','path':str(bad)},'exact accepted checkpoint outcome')
  t=time.monotonic();control({'action':'ble-outcomes','path':str(original_tape)});run(final['cycle']-restored['cycle']);replay=out/'replay-complete';control({'action':'snapshot','path':str(replay)});result['replay_seconds']=time.monotonic()-t
  require(sha(finish/'machine.chk')==sha(replay/'machine.chk'),'resolved in-flight native outcome-tape suffix state differs')
  require(sha(original_tape)==original_hash,'isolated suffix consulted/mutated original capture')
  result['exact_suffix']={'cycles':final['cycle']-restored['cycle'],'checkpoint_bytes':(replay/'machine.chk').stat().st_size,'checkpoint_sha256':sha(replay/'machine.chk'),'original_tape_sha256':original_hash,'replayed_uart_sha256':hashlib.sha256((directory/'uart.bin').read_bytes()[before_uart:]).hexdigest()}
  result['status']='PASS'
 except BaseException as e:result['error']=str(e);raise
 finally:
  if process is not None:
   if process.poll() is None:
    try:control({'action':'destroy'});process.wait(timeout=10)
    except BaseException:
     if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
     try:process.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
   result['owner_exit_code']=process.returncode
  commands.close();log.close();result['host_seconds']=time.monotonic()-started;result['observer_sha256']=sha(__file__)
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'cycles':result['final']['cycle'],'host_seconds':result['host_seconds']},indent=2))
if __name__=='__main__':main()
