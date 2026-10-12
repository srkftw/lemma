#!/usr/bin/env python3
"""Bounded source/tool-bound LE1M packet circuitry and genuine Lean admission.

This is a reusable component qualification, not a complete Bluetooth connection,
SoC registration, guest companion Save, digital GFSK, RF or certification claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import resource
import re
import sys
import time
from check_silicon import command, device_build
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate_object_attributes(attributes):
 # The pinned executable resolves llvm-readelf to llvm-readobj, whose output
 # format follows argv[0]. Admit its exact ELF/ISA fields, not a loose name.
 required=['Format: elf64-littleriscv','Arch: riscv64','AddressSize: 64bit',
   'Class: 64-bit (0x2)','Type: Relocatable (0x1)','Machine: EM_RISCV (0xF3)']
 if any(attributes.count(field)!=1 for field in required):
  raise RuntimeError('BLE object is not an exact ELF64 relocatable RISC-V target')
 arches=re.findall(r'^\s*Value: (rv[^\s]+)\s*$',attributes,re.MULTILINE)
 if arches!=['rv64i2p1_m2p0_zmmul1p0']:
  raise RuntimeError('unexpected BLE object ISA attributes: '+repr(arches))
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--lane',choices=['rtl','lean','all'],default='all')
 p.add_argument('--timeout',type=int,default=300)
 p.add_argument('--jobs',type=int,choices=[1,2],default=2)
 a=p.parse_args()
 if not 30<=a.timeout<=600:p.error('timeout must be30..600seconds')
 out=a.work_dir.resolve()
 if not out.is_relative_to(ROOT/'build') or out.exists():p.error('work-dir must be unused under build/')
 out.mkdir(parents=True);started=time.monotonic();result={'schema':'lemma-ble-packet-evidence/1','status':'FAIL','lane':a.lane,
   'scope':'component sampled-bit digital framing/CRC/whitening + genuinely elaborated scalar/PIO code; full RV64 machine/controller integration separate'}
 names=['sim/rtl/lemma_ble_packet.sv','tests/radio/ble_packets.cpp','scripts/check_ble_packet.py','scripts/check_silicon.py','tooling/silicon/sim.nix','flake.lock']
 if a.lane in ['lean','all']:
  names+=['tests/radio/Packet.lean','lakefile.toml','lean-toolchain','flake.nix','tooling/toolchain-lock.json']
  names+=sorted(str(f.relative_to(ROOT)) for f in (ROOT/'Lemma').rglob('*.lean'))
 try:
  before={n:sha(ROOT/n) for n in names};result['source_inputs']=before
  commands=[]
  if a.lane in ['rtl','all']:
   obj=out/'obj';obj.mkdir();snapshots=out/'snapshots';snapshots.mkdir()
   argv=['verilator','--cc','--exe','--build','--savable','-j',str(a.jobs),'--top-module','lemma_ble_packet','--Mdir',str(obj),
      str(ROOT/'sim/rtl/lemma_ble_packet.sv'),str(ROOT/'tests/radio/ble_packets.cpp')]
   built,tools=device_build(argv,out/'tools.json',out/'build.log',a.timeout);commands.append(built)
   commands.append(command([str(obj/'Vlemma_ble_packet'),str(snapshots)],out/'simulation.log',30))
   expected=['BLE KAT official5.4 data bytes and two endpoints independently decoded PASS',
      'BLE corruption loss wrong-channel bounded-head reset power coexistence PASS',
      'BLE four arbitrary live TX/RX checkpoints exact30000-clock suffix PASS']
   text=(out/'simulation.log').read_text()
   if any(text.count(e)!=1 for e in expected) or 'FAIL' in text:raise RuntimeError('missing/duplicate actual BLE observations')
   result.update(tool_inputs=tools,observations=expected,compiled_binary_sha256=sha(obj/'Vlemma_ble_packet'),
      snapshots={f.name:sha(f) for f in sorted(snapshots.iterdir())})
   if len(result['snapshots'])!=12:raise RuntimeError('missing arbitrary-boundary controller state')
  if a.lane in ['lean','all']:
   query="\n".join([
     "import hashlib,json,shutil,subprocess", "from pathlib import Path", "tools={}",
     "for name in ('lean','lake','llvm-as','llc','llvm-nm','llvm-readelf','llvm-objdump'):",
     "    found=shutil.which(name)",
     "    if not found:raise RuntimeError('Missing lowering/audit tool '+name)",
     "    path=Path(found).resolve()",
     "    tools[name]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),",
     "                 'version':subprocess.check_output([found,'--version'],text=True).splitlines()[0]}",
     f"Path({str(out/'lean-tools.json')!r}).write_text(json.dumps(tools,indent=2)+'\\n')"])
   commands.append(command(['nix','develop','--no-write-lock-file','--command','python3','-c',query],out/'lean-tools.log',60))
   lean_tools=json.loads((out/'lean-tools.json').read_text())
   if set(lean_tools)!={'lean','lake','llvm-as','llc','llvm-nm','llvm-readelf','llvm-objdump'}:
    raise RuntimeError('incomplete lowering/audit tool inventory')
   for value in lean_tools.values():
    if not value['path'].startswith('/nix/store/') or not value['version'] or sha(value['path'])!=value['sha256']:
     raise RuntimeError('lowering/audit tool identity changed')
   result['lean_tool_inputs']=lean_tools
   commands.append(command(['nix','develop','--no-write-lock-file','--command','lake','build','Lemma.Compiler.CFGLower',
      'Lemma.Radio.BLE.Packet','Lemma.Radio.BLE.Controller'],out/'lean-build.log',a.timeout))
   commands.append(command(['nix','develop','--no-write-lock-file','--command','env','LEMMA_BLE_PROBE_OUT='+str(out/'llvm'),
      'lake','env','lean','tests/radio/Packet.lean'],out/'lean-probe.log',a.timeout))
   expected=['BLE_LOWERING:PASS ordinary source scalar/folds+privileged PIO; unprivileged rejection; full machine/RV64 integration separate',
      'BLE_HOST_MODEL:PASS official CRC/whitening vectors; static addresses;27-byte owned PIO and no-write backpressure/errors; not RV64 execution']
   text=(out/'lean-probe.log').read_text()
   if any(text.count(e)!=1 for e in expected):raise RuntimeError('missing genuine BLE lowering/independent semantic observations')
   for label in ['packet','controller']:
    commands.append(command(['nix','develop','--no-write-lock-file','--command','llvm-as',str(out/'llvm'/f'{label}.ll'),'-o',str(out/'llvm'/f'{label}.bc')],out/f'{label}-assemble.log',60))
    commands.append(command(['nix','develop','--no-write-lock-file','--command','llc','-mtriple=riscv64-unknown-elf','-mattr=+m','-filetype=obj','-O=2',str(out/'llvm'/f'{label}.bc'),'-o',str(out/'llvm'/f'{label}.o')],out/f'{label}-lower.log',60))
    commands.append(command([lean_tools['llvm-nm']['path'],'--undefined-only',str(out/'llvm'/f'{label}.o')],out/f'{label}-undefined.log',30))
    undefined=[line.split()[-1] for line in (out/f'{label}-undefined.log').read_text().splitlines() if line.strip()]
    if undefined!=(['core0_io_fence'] if label=='controller' else []):
     raise RuntimeError('unexpected RV64 helper/object dependency: '+repr(undefined))
    commands.append(command([lean_tools['llvm-readelf']['path'],'--file-header','--arch-specific',str(out/'llvm'/f'{label}.o')],out/f'{label}-attributes.log',30))
    attributes=(out/f'{label}-attributes.log').read_text()
    validate_object_attributes(attributes)
    commands.append(command([lean_tools['llvm-objdump']['path'],'--disassemble','--reloc',str(out/'llvm'/f'{label}.o')],out/f'{label}-disassembly.log',30))
   result['lean_observations']=expected;result['llvm_artifacts']={str(f.relative_to(out)):sha(f) for f in sorted((out/'llvm').iterdir())}
  if before!={n:sha(ROOT/n) for n in names}:raise RuntimeError('consumed BLE/Lean/tooling source changed during qualification')
  result['commands']=commands;result['status']='PASS'
 except BaseException as e:result['error']=str(e)
 finally:
  usage=resource.getrusage(resource.RUSAGE_CHILDREN)
  result['resources']={'largest_reaped_child_peak_rss_kib':usage.ru_maxrss,
    'reaped_children_user_seconds':usage.ru_utime,'reaped_children_system_seconds':usage.ru_stime,
    'scope':'Linux wait4 child statistics; largest child RSS is not summed concurrent machine memory'}
  result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'host_seconds':result['host_seconds']},indent=2))
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
