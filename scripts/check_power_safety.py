#!/usr/bin/env python3
"""Bounded Power-v2 circuit and old v1 regression; no guest/physical claim."""
from pathlib import Path
import argparse,hashlib,json,sys
from check_silicon import command,device_build
from silicon_profile import constants,profile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
 out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 report={'status':'FAIL','scope':'literal always-on Power-v2 circuitry and preserved Power-v1; separate from guest/fast/physical qualification'}
 try:
  names=['sim/rtl/lemma_power.sv','conformance/silicon/PowerControl.sv','conformance/silicon/PowerSafety.sv','sim/profiles/lemma-silicon-dev-0.3.0.json','scripts/silicon_profile.py','scripts/check_power_safety.py','scripts/check_silicon.py','tooling/silicon/sim.nix','flake.lock']
  before={n:sha(ROOT/n) for n in names};report['source_inputs']=before
  fields=constants(profile('lemma-silicon-dev/0.3.0'))
  binding=out/'binding.sv';binding.write_text('package lemma_silicon_binding;\n'+''.join(f"localparam logic[63:0] {k.upper()}=64'h{v:016x};\n" for k,v in fields.items())+'endpackage\n')
  rows=[]
  for top,markers in [('PowerControl',['POWER six independent BUSY sources malformed MMIO no false completion PASS','POWER raw edge guest decision exact cancel wake and W1C precedence PASS','POWER warm held-button epoch retention and cold control reset PASS']),('PowerSafety',['POWER2 watchdog expiry independent of guest progress exact8 reset clocks PASS','POWER2 terminal kick malformed writes and Power1 suspend wake retained PASS','POWER2 brownout priority actual domain reset unsafe hold8 good clocks PASS'])]:
   d=out/top;d.mkdir();obj=d/'obj'
   build,tools=device_build(['verilator','--binary','--timing','-j',str(a.jobs),'-Wno-fatal','--top-module',top,'--Mdir',str(obj),str(binding),str(ROOT/'sim/rtl/lemma_power.sv'),str(ROOT/f'conformance/silicon/{top}.sv')],d/'tools.json',d/'build.log',a.timeout)
   run=command([str(obj/f'V{top}')],d/'simulation.log',30)
   log=(d/'simulation.log').read_text()
   if any(log.count(m)!=1 for m in markers):raise ValueError('missing or duplicate circuit assertion markers')
   rows.append({'top':top,'status':'PASS','commands':[build,run],'tools':tools,'binary_sha256':sha(obj/f'V{top}'),'observations':markers})
  if before!={n:sha(ROOT/n) for n in names}:raise ValueError('consumed Power circuit sources changed')
  report.update(status='PASS',lanes=rows,binding_sha256=sha(binding))
 except Exception as e:report['error']=str(e)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'result':str(out/'result.json')}))
 return 0 if report['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
