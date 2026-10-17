#!/usr/bin/env python3
"""Bounded ordinary Lean manual-link policy and separately hosted opaque peer.

This produces RV64 objects and checks hosted peer behavior; it does not claim
actual guest/controller execution, Bluetooth establishment or durable receipts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from check_ble_packet import validate_object_attributes
from check_silicon import command
from ble_peer_state import PeerState,parse_response

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--work-dir',type=Path,required=True)
 parser.add_argument('--timeout',type=int,default=300)
 args=parser.parse_args();out=args.work_dir.resolve()
 if not 30<=args.timeout<=600:parser.error('timeout must be30..600seconds')
 if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('work-dir must be unused under build/')
 out.mkdir(parents=True);start=time.monotonic()
 result={'schema':'lemma-ble-manual-link-evidence/1','status':'FAIL',
   'scope':'Genuine scalar Lean checked LLVM/RV64 object and hosted Lean opaque peer; whole controller/guest and persistence separate'}
 names=['scripts/check_ble_link.py','scripts/ble_peer_state.py','scripts/check_ble_packet.py','scripts/check_silicon.py','tests/radio/Link.lean',
   'sim/radio/ble_peer.lean','flake.lock','flake.nix','lakefile.toml','lean-toolchain','tooling/toolchain-lock.json']
 names+=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'Lemma').rglob('*.lean'))
 try:
  before={n:sha(ROOT/n) for n in names};result['source_inputs']=before
  commands=[]
  def run(argv,log,timeout=args.timeout):
   commands.append(command(['nix','develop','--no-write-lock-file','--command',*argv],out/log,timeout))
  query="\n".join(['import hashlib,json,shutil,subprocess','from pathlib import Path','tools={}',
    "for name in ('lean','lake','llvm-as','llc','llvm-nm','llvm-readobj','llvm-objdump'):",
    '    found=shutil.which(name)',"    if not found:raise RuntimeError('missing tool '+name)",
    '    path=Path(found).resolve()',
    "    tools[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),",
    "      'version':subprocess.check_output([found,'--version'],text=True).splitlines()[:4]}",
    f"Path({str(out/'tools.json')!r}).write_text(json.dumps(tools,indent=2)+'\\n')"])
  run(['python3','-c',query],'tools.log',60)
  tools=json.loads((out/'tools.json').read_text());result['tools']=tools
  if set(tools)!={'lean','lake','llvm-as','llc','llvm-nm','llvm-readobj','llvm-objdump'}:
   raise RuntimeError('incomplete link tool inventory')
  for value in tools.values():
   if not value['path'].startswith('/nix/store/') or not value['version'] or sha(value['path'])!=value['sha256']:
    raise RuntimeError('link tool identity differs')
  def tool(name,argv,log,timeout=60):
   commands.append(command([tools[name]['path'],*argv],out/log,timeout))
  run(['lake','build','Lemma.Compiler.CFGLower','Lemma.Radio.BLE.Link'],'build.log')
  run(['env','LEMMA_BLE_LINK_OUT='+str(out/'link.ll'),'lake','env','lean','tests/radio/Link.lean'],'lowering.log')
  log=(out/'lowering.log').read_text()
  for marker in ['BLE_LINK_LOWERING ordinary guarded Lean transitions PASS; actual guest execution separate',
    'BLE_LINK_HOST semantic lost-ACK/duplicate/credit/next-sequence/exhaustion/cancel/invalid state PASS; not RV64 execution']:
   if log.count(marker)!=1:raise RuntimeError('missing/duplicate genuine link observation')
  tool('llvm-as',[str(out/'link.ll'),'-o',str(out/'link.bc')],'assemble.log')
  tool('llc',['-mtriple=riscv64-unknown-elf','-mattr=+m','-filetype=obj','-O=2',str(out/'link.bc'),'-o',str(out/'link.o')],'object.log')
  tool('llvm-nm',['--undefined-only',str(out/'link.o')],'undefined.log',30)
  if (out/'undefined.log').read_text().strip():raise RuntimeError('unknown link object runtime dependency')
  tool('llvm-readobj',['--file-header','--arch-specific',str(out/'link.o')],'attributes.log',30)
  validate_object_attributes((out/'attributes.log').read_text())
  tool('llvm-objdump',['--disassemble','--reloc',str(out/'link.o')],'disassembly.log',30)
  payload='4c4d434d5030303101000200'
  inputs=f'RX 2 12 {payload}\nSTATUS\nRX 2 12 {payload}\nSTATUS\nCREDIT\nRX 14 12 {payload}\nSTATUS\nCANCEL\nRX 14 12 {payload}\nQUIT\n'
  (out/'peer-input.txt').write_text(inputs)
  peer=subprocess.run(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean'],
    cwd=ROOT,input=inputs,text=True,capture_output=True,timeout=90)
  (out/'peer-output.txt').write_text(peer.stdout);(out/'peer-errors.txt').write_text(peer.stderr)
  data=bytes.fromhex(payload)
  expected=[('BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT',PeerState(0,0,0,b'')),
    ('TX 5 0 -',PeerState(262,1,0,data)),('STATUS',PeerState(262,1,0,data)),
    ('TX 5 0 -',PeerState(518,1,1,data)),('STATUS',PeerState(518,1,1,data)),
    ('CREDIT 1',PeerState(518,1,1,b'')),('TX 9 0 -',PeerState(261,2,1,data)),
    ('STATUS',PeerState(261,2,1,data)),('ERROR 200 FROZEN',PeerState(9,2,1,data)),
    ('ERROR 199 CONTEXT',PeerState(9,2,1,data))]
  if peer.returncode or [parse_response(line) for line in peer.stdout.splitlines()]!=expected or peer.stderr.count('OPAQUE_RX ')!=2:
   raise RuntimeError('actual hosted opaque peer lost-ACK/credit/cancellation behavior differs')
  # Cache the complete retry response; do not query, flush or drain the original
  # peer to take a snapshot. A fresh process is bound privately before use.
  cached=expected[3][1]
  suffix=f'CREDIT\nRX 14 12 {payload}\nSTATUS\nCANCEL\nRX 14 12 {payload}\nQUIT\n'
  fork=subprocess.run(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean','--private-restore'],
    cwd=ROOT,input=cached.restore_command()+'\n'+suffix,text=True,capture_output=True,timeout=30)
  (out/'private-fork-output.txt').write_text(fork.stdout);(out/'private-fork-errors.txt').write_text(fork.stderr)
  actual=[parse_response(line) for line in fork.stdout.splitlines()]
  if fork.returncode or actual!=[expected[0],('RESTORED PRIVATE_CONTEXT',cached),*expected[5:]] or fork.stderr.count('OPAQUE_RX ')!=1:
   raise RuntimeError('actual private hosted peer continuation differs from original suffix')
  bad=['RESTORE 256 0 0 -','RESTORE 12 0 0 -',f'RESTORE 0 {1<<63} 0 -',
    f'RESTORE 0 0 {1<<63} -','RESTORE 0 1 0 '+'00'*28,'RESTORE 0 0 0 01']
  rejected=[]
  for line in bad:
   failed=subprocess.run(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean','--private-restore'],
    cwd=ROOT,input=line+'\n',text=True,capture_output=True,timeout=30)
   observed=[parse_response(text) for text in failed.stdout.splitlines()]
   if failed.returncode!=2 or observed!=[expected[0],('ERROR 197 RESTORE',PeerState(0,0,0,b''))]:
    raise RuntimeError('malformed private state was admitted or changed default peer')
   rejected.append(line)
  live_restore=subprocess.run(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run','sim/radio/ble_peer.lean'],
    cwd=ROOT,input='RESTORE 0 0 0 -\nSTATUS\nQUIT\n',text=True,capture_output=True,timeout=30)
  if live_restore.returncode or [parse_response(line) for line in live_restore.stdout.splitlines()]!=[
    expected[0],('ERROR 197 COMMAND',PeerState(0,0,0,b'')),('STATUS',PeerState(0,0,0,b''))]:
   raise RuntimeError('ordinary live peer accepted a restore command')
  (out/'private-state-negatives.json').write_text(json.dumps({'rejected':rejected,'live_restore_rejected':True},indent=2)+'\n')
  if {n:sha(ROOT/n) for n in names}!=before:raise RuntimeError('consumed source changed during link qualification')
  result.update(status='PASS',commands=commands,peer={'accepted':2,'duplicates':1,'cancellation_frozen':True,
    'trust':'open manual development context; no connection/security/durable receipt',
    'complete_accepted_response_state':True,'actual_private_fork_exact_suffix':True,'malformed_restore_rejections':6},
    artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 except BaseException as error:result['error']=str(error)
 finally:
  result['host_seconds']=time.monotonic()-start
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'path':str(out/'result.json'),'host_seconds':result['host_seconds']}))
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
