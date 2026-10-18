#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded literal circuit/model comparison; no guest or physical qualification claim."""
import argparse,hashlib,json,subprocess,time,os,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run_bounded(cmd,log,timeout):
 process=subprocess.Popen([str(v) for v in cmd],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  status=process.wait(timeout=timeout)
  if status:raise subprocess.CalledProcessError(status,cmd)
 finally:
  if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
  process.wait(timeout=10)
def main():
 p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);a=p.parse_args()
 out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 inputs=['sim/host/lemma_multimodal.c','sim/host/lemma_multimodal.h','sim/rtl/lemma_multimodal.sv','sim/rtl/tests/multimodal_tb.cpp','tooling/silicon/sim.nix','flake.lock','scripts/check_multimodal_controller.py']
 before={v:hashlib.sha256((ROOT/v).read_bytes()).hexdigest() for v in inputs}
 commands=[['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(ROOT/'sim/host'),'-c',ROOT/'sim/host/lemma_multimodal.c','-o',out/'model.o'],['verilator','--cc','--exe','--build','-j','2','-Wno-fatal','--top-module','lemma_multimodal','--Mdir',out/'obj','-CFLAGS','-std=c++17 -I'+str(ROOT/'sim/host'),'-LDFLAGS',out/'model.o',ROOT/'sim/rtl/lemma_multimodal.sv',ROOT/'sim/rtl/tests/multimodal_tb.cpp'],[out/'obj/Vlemma_multimodal']]
 versions={name:subprocess.run([name,'--version'],check=True,capture_output=True,text=True,timeout=15).stdout.splitlines()[0] for name in ('cc','verilator')}
 result={'tools':versions,'schema':'lemma-multimodal-literal/v1','scope':'standalone synthetic converter/control/PCM RTL versus functional circuit model and separately written arithmetic assertions; no guest/SoC/physical/full sensor claim','source':before,'commands':[[str(v) for v in cmd] for cmd in commands],'timeout_per_operation':a.timeout,'result':'FAIL'}
 started=time.monotonic()
 try:
  for i,cmd in enumerate(commands):
   with (out/f'command{i}.log').open('w') as log:run_bounded(cmd,log,a.timeout)
  if before!={v:hashlib.sha256((ROOT/v).read_bytes()).hexdigest() for v in inputs}:raise RuntimeError('consumed sources changed')
  output=(out/'command2.log').read_text();
  if not output.startswith('PASS synthetic-aperture/1 checks='):raise RuntimeError('missing exact nonempty protocol')
  result.update(result='PASS',observation=output.strip())
 except Exception as e:result['error']=str(e);raise
 finally:
  result['elapsed_seconds']=time.monotonic()-started;result['raw_logs']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('command*.log'))};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
