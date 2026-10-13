#!/usr/bin/env python3
"""Qualify the native raw BLE peer process adapter against actual hosted Lean.

No target/runtime implementation enters the RV64 image. Packet/controller and
whole-machine guest integration have separate evidence.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from check_silicon import command
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--work-dir',type=Path,required=True)
 args=parser.parse_args();out=args.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('unused work-dir under build required')
 out.mkdir(parents=True);start=time.monotonic();result={'schema':'lemma-ble-peer-transport/1','status':'FAIL',
   'scope':'Native host raw process framing; actual hosted Lean logical peer, no RV64 guest/controller integration'}
 names=['scripts/check_ble_transport.py','scripts/check_silicon.py','sim/radio/ble_peer_transport.h',
   'sim/radio/ble_peer_transport.cpp','tests/radio/ble_transport.cpp','sim/radio/ble_peer.lean',
   'Lemma/Radio/BLE/Link.lean','Lemma/Radio/BLE/Packet.lean','Lemma/Core0/Memory.lean','Lemma/Core0/Device.lean',
   'flake.nix','flake.lock','lakefile.toml','lean-toolchain']
 try:
  before={name:sha(ROOT/name) for name in names};result['source_inputs']=before
  query="\n".join(['import hashlib,json,shutil,subprocess','from pathlib import Path','tools={}',
   "for name in ('g++','lean','lake','nix'):",
   ' found=shutil.which(name)'," if not found:raise RuntimeError('missing native peer tool '+name)",
   ' path=Path(found).resolve()'," tools[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),",
   "   'version':subprocess.check_output([found,'--version'],text=True).splitlines()[:3]}",
   f"Path({str(out/'tools.json')!r}).write_text(json.dumps(tools,indent=2)+'\\n')"])
  commands=[command(['nix','develop','--no-write-lock-file','--command','python3','-c',query],out/'tools.log',60)]
  tools=json.loads((out/'tools.json').read_text());result['tools']=tools
  if set(tools)!={'g++','lean','lake','nix'} or any(not value['path'].startswith('/nix/store/') or
    sha(value['path'])!=value['sha256'] or not value['version'] for value in tools.values()):
   raise RuntimeError('native peer tool identity differs')
  commands.append(command(['nix','develop','--no-write-lock-file','--command','lake','build','Lemma.Radio.BLE.Link'],out/'peer-build.log',300))
  commands.append(command(['nix','develop','--no-write-lock-file','--command',tools['g++']['path'],
   '-std=c++17','-Wall','-Wextra','-Werror','-O2',str(ROOT/'sim/radio/ble_peer_transport.cpp'),
   str(ROOT/'tests/radio/ble_transport.cpp'),'-o',str(out/'ble_transport')],out/'build.log',120))
  commands.append(command([str(out/'ble_transport'),tools['nix']['path'],'develop','--no-write-lock-file',
   '--command','lake','env','lean','--run','sim/radio/ble_peer.lean'],out/'observations.log',90))
  marker='BLE_PEER_TRANSPORT realLean nonblocking IDs/overlap/pending/private exact suffix/cancel/EOF/reap PASS'
  if (out/'observations.log').read_text().count(marker)!=1:raise RuntimeError('missing exact native adapter observation')
  if {name:sha(ROOT/name) for name in names}!=before:raise RuntimeError('native peer source changed during qualification')
  result.update(status='PASS',commands=commands,binary_sha256=sha(out/'ble_transport'),observations=[marker],
   artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()})
 except BaseException as error:result['error']=str(error)
 finally:
  result['host_seconds']=time.monotonic()-start
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'path':str(out/'result.json'),'host_seconds':result['host_seconds']}))
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
