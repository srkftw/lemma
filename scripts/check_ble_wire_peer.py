#!/usr/bin/env python3
"""Two distinct BLE packet circuits connected to a real hosted Lean link peer.

This checks an open manual LE1M hard-decision context. It is not a guest, a
Bluetooth connection, companion persistence, GFSK/RF or full5.4 qualification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import selectors
import subprocess
import time
from pathlib import Path
from check_silicon import command, device_build
from ble_peer_state import PeerState,parse_response

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
 if not value:raise RuntimeError(message)

# Independent diagram-position CRC and whitening reference; no RTL/Lean call.
def encode(header,payload):
 aa,init,channel=0xaa08192b,0xc4c181,16
 bits=[(aa&1)^(i&1) for i in range(8)]+[(aa>>i)&1 for i in range(32)]
 crc=[(init>>(23-i))&1 for i in range(24)]
 white=[((channel|64)>>i)&1 for i in range(7)]
 def append(bit):
  bits.append(bit^white[0]);old=white.pop(0);white.append(old);white[2]^=old
 for byte in [header,len(payload),*payload]:
  for i in range(8):
   bit=(byte>>i)&1;feedback=crc[0]^bit;crc.pop(0);crc.append(0)
   for exponent in [0,1,3,4,6,9,10]:crc[23-exponent]^=feedback
   append(bit)
 for bit in crc:append(bit)
 return ''.join(map(str,bits))

class Process:
 def __init__(self,argv,out,name,timeout=30):
  self.error=(out/(name+'-errors.log')).open('w')
  self.process=subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
    stderr=self.error,text=True,bufsize=1)
  self.selector=selectors.DefaultSelector();self.selector.register(self.process.stdout,selectors.EVENT_READ)
  self.timeout=timeout;self.transcript=[]
 def read(self):
  require(bool(self.selector.select(self.timeout)),'bounded external process response timed out')
  value=self.process.stdout.readline()
  require(value!='','external process ended before response')
  value=value.rstrip('\n');self.transcript.append({'response':value});return value
 def exchange(self,text):
  require(len(text)<=256 and '\n' not in text,'raw command outside bounded frame')
  self.transcript.append({'request':text});self.process.stdin.write(text+'\n');self.process.stdin.flush();return self.read()
 def close(self,out,name):
  if self.process.poll() is None:
   self.process.stdin.write('QUIT\n');self.process.stdin.flush()
   try:self.process.wait(timeout=10)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait();raise
  require(self.process.returncode==0,'external adapter or peer failed')
  self.selector.close();self.error.close()
  (out/(name+'-transcript.json')).write_text(json.dumps(self.transcript,indent=2)+'\n')
 def terminate(self):
  if self.process.poll() is None:self.process.kill();self.process.wait()
  self.selector.close();self.error.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--work-dir',type=Path,required=True)
 parser.add_argument('--timeout',type=int,default=300)
 args=parser.parse_args();out=args.work_dir.resolve()
 if not 30<=args.timeout<=600:parser.error('timeout must be30..600seconds')
 if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('unused work-dir under build required')
 out.mkdir(parents=True);started=time.monotonic();wire=peer=None
 result={'schema':'lemma-ble-wire-peer-evidence/1','status':'FAIL',
   'scope':'two independent RTL packet endpoints with hosted Lean manual SN/NESN peer; no actual RV64 guest, connection establishment, security or durable companion receipt'}
 names=['scripts/check_ble_wire_peer.py','scripts/ble_peer_state.py','scripts/check_silicon.py','sim/rtl/lemma_ble_packet.sv',
   'tests/radio/ble_link_wire.cpp','sim/radio/ble_peer.lean','Lemma/Radio/BLE/Link.lean',
   'Lemma/Radio/BLE/Packet.lean','flake.lock','flake.nix','lakefile.toml','lean-toolchain','tooling/silicon/sim.nix']
 try:
  before={name:sha(ROOT/name) for name in names};result['source_inputs']=before
  obj=out/'obj';obj.mkdir()
  build,tools=device_build(['verilator','--cc','--exe','--build','-j','2','--top-module','lemma_ble_packet',
   '--Mdir',str(obj),str(ROOT/'sim/rtl/lemma_ble_packet.sv'),str(ROOT/'tests/radio/ble_link_wire.cpp')],
   out/'tools.json',out/'build.log',args.timeout)
  command(['nix','develop','--no-write-lock-file','--command','lake','build','Lemma.Radio.BLE.Link'],out/'peer-build.log',args.timeout)
  wire=Process([str(obj/'Vlemma_ble_packet')],out,'wire')
  peer=Process(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean'],out,'peer')
  require(wire.read()=='BLEWIRE/1 RAW_CONTROLLER_SAMPLES','raw controller handshake differs')
  require(parse_response(peer.read())==('BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT',PeerState(0,0,0,b'')),
    'actual Lean peer trust handshake differs')
  payload=bytes.fromhex('4c4d434d5030303101000200')
  def policy(text,action,state):
   observed=parse_response(peer.exchange(text));require(observed==(action,state),'actual complete Lean peer response/state differs: '+repr(observed))
   return observed
  def transfer(side,header,data,drop_b=False,corrupt=0xffffffff):
   require(wire.exchange(f'TX {side} {header} '+(data.hex() if data else '-'))==f'TX {side} STARTED','TX controller admission differs')
   fields=wire.exchange(f'CLOCK 33000 0 {int(drop_b)} {corrupt}').split()
   require(len(fields)==6 and fields[0]=='CLOCK' and fields[2]=='A' and fields[4]=='B','invalid actual sample observation')
   expected=encode(header,list(data));actual=fields[3 if side=='A' else 5]
   require(actual==expected,'actual generated packet differs from independent CRC/whitening reference')
   return fields
  def peer_head():
   head=wire.exchange('RX B').split();require(len(head)==5 and head[:2]==['RX','B'],'peer CRC-validated head missing')
   answer,_=parse_response(peer.exchange(' '.join(['RX',*head[2:]])));require(wire.exchange('POP B')=='POP B DONE','controller head pop failed')
   words=answer.split();require(len(words)==4 and words[0]=='TX' and words[2:]==['0','-'],'Lean peer did not request bounded actual empty ACK')
   return int(words[1])
  # First packet is decoded and retained by the real peer, then its actual ACK
  # waveform is lost. No synthetic ACK or receive event is inserted.
  transfer('A',2,payload);require(peer_head()==5,'first Lean ACK sequence differs')
  transfer('B',5,b'',drop_b=True);require(wire.exchange('RX A')=='HEAD A NONE','lost ACK created a client head')
  policy('STATUS','STATUS',PeerState(262,1,0,payload))
  # Same-SN retry traverses both packet engines. Peer retains the bytes once.
  transfer('A',2,payload);require(peer_head()==5,'retry changed ACK sequence')
  transfer('B',5,b'');require(wire.exchange('RX A')=='RX A 5 0 -','actual retry ACK was not independently decoded')
  require(wire.exchange('POP A')=='POP A DONE','client ACK head pop failed')
  policy('STATUS','STATUS',PeerState(518,1,1,payload))
  policy('CREDIT','CREDIT 1',PeerState(518,1,1,b''))
  transfer('A',14,payload);require(peer_head()==9,'next acknowledged sequence differs')
  transfer('B',9,b'');require(wire.exchange('RX A')=='RX A 9 0 -','next ACK was not decoded')
  require(wire.exchange('POP A')=='POP A DONE','next ACK pop failed')
  policy('STATUS','STATUS',PeerState(261,2,1,payload))
  policy('CREDIT','CREDIT 1',PeerState(261,2,1,b''))
  # Corruption occurs after TX generation and before the receiving circuit.
  transfer('A',2,payload,corrupt=70);require(wire.exchange('RX B')=='HEAD B NONE','CRC corruption published an application head')
  policy('STATUS','STATUS',PeerState(261,2,1,b''))
  status=wire.exchange('STATUS B').split();require(len(status)==9 and int(status[7])==1,'actual receive circuit did not count CRC failure')
  transfer('A',2,payload);require(peer_head()==5,'correct retry after corruption differed')
  transfer('B',5,b'');require(wire.exchange('RX A')=='RX A 5 0 -','corrected packet ACK not decoded')
  policy('STATUS','STATUS',PeerState(262,3,1,payload))
  policy('CANCEL','ERROR 200 FROZEN',PeerState(10,3,1,payload))
  require(wire.exchange('RESET B')=='RESET B DONE','controller reset failed')
  require(wire.exchange('RX B')=='HEAD B NONE','reset retained queued receive data')
  policy('RX 2 12 '+payload.hex(),'ERROR 199 CONTEXT',PeerState(10,3,1,payload))
  wire.close(out,'wire');wire=None;peer.close(out,'peer');peer=None
  require((out/'peer-errors.log').read_text().count('OPAQUE_RX ')==3,'opaque payload was accepted more than declared')
  require({name:sha(ROOT/name) for name in names}==before,'consumed controller or Lean peer source changed')
  result.update(status='PASS',tool_inputs=tools,build=build,
   binary_sha256=sha(obj/'Vlemma_ble_packet'),observations={
    'actual_generated_packets':9,'opaque_accepted':3,'duplicate_ignored':1,
    'actual_ack_lost':True,'actual_crc_corruption_rejected':True,
    'reset_head_cleared':True,'explicit_cancel_frozen':True,'real_hosted_lean_peer':True},
   artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 except BaseException as error:
  result['error']=str(error)
 finally:
  for child in [wire,peer]:
   if child is not None:child.terminate()
  result['host_seconds']=time.monotonic()-started
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'host_seconds':result['host_seconds']}))
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
