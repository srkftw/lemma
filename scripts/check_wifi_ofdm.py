#!/usr/bin/env python3
"""Bounded, source/tool-bound Wi-Fi common OFDM DATA component qualification.
The component is a Wi-Fi6 construction dependency, not HE or complete Wi-Fi.
"""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from check_silicon import ROOT,sha,command,device_build

SOURCES=['sim/rtl/lemma_wifi_math.sv','sim/rtl/lemma_wifi_bcc_symbol.sv','sim/rtl/lemma_wifi_ofdm_data.sv',
 'tests/radio/WiFiDataProbe.sv','tests/radio/wifi_ofdm_data.cpp','scripts/check_wifi_ofdm.py',
 'scripts/check_silicon.py','tooling/silicon/sim.nix','flake.lock']
OBSERVATIONS=['WIFI common BCC known-answer + actual complex OFDM two-endpoint payload PASS',
 'WIFI error-correction corruption loss bounds reset power coexistence IRQ/head PASS',
 'WIFI six live CRC/BCC/IFFT/DFT/Viterbi checkpoints full-state exact suffix PASS']
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--guest-receipt',type=Path,help='Optional independently qualified RV64 purecodec result.json; copies only its guest-produced payload octets')
 p.add_argument('--timeout',type=int,default=300);p.add_argument('--jobs',type=int,choices=[1,2],default=2)
 a=p.parse_args();out=a.work_dir.resolve()
 if not out.is_relative_to(ROOT/'build') or out.exists():p.error('unused output under build/ required')
 if not 30<=a.timeout<=600:p.error('timeout must be30..600s')
 out.mkdir(parents=True);start=time.monotonic();result={'schema':'lemma-wifi-ofdm-data-evidence/1','status':'FAIL',
  'scope':'common legacy20MHz BPSK/r1/2 DATA coding and real complex sample component; HE/WiFi6 unfinished',
  'plan':{'build_seconds':a.timeout,'simulation_seconds':30,'jobs':a.jobs,'clock_hz':100000000,'sample_hz':20000000,'payload_max':16,'component_only':True}}
 try:
  before={n:sha(ROOT/n) for n in SOURCES};result['source_inputs']=before
  obj=out/'obj';obj.mkdir();states=out/'snapshots';states.mkdir()
  argv=['verilator','--cc','--exe','--build','--savable','-j',str(a.jobs),'--top-module','WiFiDataProbe','--Mdir',str(obj),
   *(str(ROOT/n) for n in SOURCES if n.endswith('.sv')),str(ROOT/'tests/radio/wifi_ofdm_data.cpp')]
  built,tools=device_build(argv,out/'tools.json',out/'build.log',a.timeout);result['commands']=[built];result['tools']=tools
  run=[str(obj/'VWiFiDataProbe'),str(states)]
  if a.guest_receipt:
   receipt=a.guest_receipt.resolve();guest=json.loads(receipt.read_text())
   if guest.get('schema')!='lemma-wifi-codec-guest/1' or guest.get('status')!='PASS_RTL_GUEST' or guest.get('guest',{}).get('status')!='PASS_RTL_GUEST':raise RuntimeError('guest payload provenance is not a completed actual RV64 codec run')
   info=guest['guest']['payloads'];payload=Path(info['path'])
   if info['bytes']!=32 or payload.stat().st_size!=32 or sha(payload)!=info['sha256']:raise RuntimeError('guest payload identity differs')
   run.append(str(payload));result['guest_payload_source']={'receipt':str(receipt),'receipt_sha256':sha(receipt),**info}
  result['commands'].append(command(run,out/'simulation.log',30))
  text=(out/'simulation.log').read_text()
  if a.guest_receipt and text.count('WIFI actual RV64-produced payload bytes two-endpoint complex waveform PASS')!=1:raise RuntimeError('actual guest payload waveform observation absent')
  if any(text.count(s)!=1 for s in OBSERVATIONS) or 'FAIL' in text:raise RuntimeError('missing or duplicated actual component observations')
  files={str(f.relative_to(out)):{'sha256':sha(f),'bytes':f.stat().st_size} for f in states.iterdir()}
  if len(files)!=42:raise RuntimeError('missing full generated or pending wire state')
  if before!={n:sha(ROOT/n) for n in SOURCES}:raise RuntimeError('consumed component sources changed')
  result.update(status='PASS_RTL_COMPONENT',observations=OBSERVATIONS,snapshots=files,binary_sha256=sha(obj/'VWiFiDataProbe'),
    remaining=['Final HE normative mandatory/optional closure','HE PPDU/242-tone data and full MAC','preamble/acquisition/clock/frequency/channel estimation','connected machine0.12/Lean driver integration','RF/physical timing/conformance'])
 except BaseException as e:result['error']=repr(e);raise
 finally:
  result['wall_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print('WIFI_OFDM:PASS_RTL_COMPONENT actual bounded complex samples; HE/WiFi6 remain incomplete')
if __name__=='__main__':main()
