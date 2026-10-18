#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual RV64 Lean converter probe on integrated CVW/SoC, bounded independent oracle."""
import argparse,hashlib,json,os,signal,struct,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--rtl-build',type=Path,required=True);p.add_argument('--guest',type=Path,required=True);p.add_argument('--rom',type=Path,required=True);p.add_argument('--binding',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);a=p.parse_args();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 binary=a.rtl_build.resolve()/'obj/lemma-rtl';m=json.loads((a.rtl_build/'build.json').read_text());
 if m.get('profile')!='lemma-silicon-dev/0.14.0' or m.get('binary_sha256')!=digest(binary):raise ValueError('unadmitted RTL/profile binary')
 if a.rom.read_bytes()!=struct.pack('<6I',0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067):raise ValueError('reset ROM not fixed structured Lean handoff')
 paths={'rtl':binary,'rtl_production':a.rtl_build/'build.json','guest':a.guest,'rom':a.rom,'dtb':a.binding/'platform.dtb','descriptor':a.binding/'descriptor.bin','observer':Path(__file__)}
 inputs={name:{'path':str(path.resolve()),'sha256':digest(path)} for name,path in paths.items()}
 events=''.join(f'0 multimodal {i} {100+i} 10 0\n' for i in range(8));(out/'stimuli.events').write_text(events)
 cmd=[str(binary),'--image',str(a.guest.resolve()),'--rom',str(a.rom.resolve()),'--load','0x87e00000:'+str((a.binding/'platform.dtb').resolve()),'--descriptor',str((a.binding/'descriptor.bin').resolve()),'--events',str(out/'stimuli.events'),'--uart-output',str(out/'uart.bin'),'--quiet-uart','--uart-stop','LMMP','--cycles','5000000','--deadline',str(a.timeout),'--ram-dump','0x80410000:640:'+str(out/'records.bin'),'--multimodal-pcm-output',str(out/'audio.bin'),'--report',str(out/'machine-report.json')]
 report={'schema':'lemma-multimodal-rtl-guest-probe/v1','scope':'actual genuinely elaborated Lean M-mode component on integrated CVW CPU+controllers; scalar apertures/DMA-independent probe, not full notebook/P2/physical or consumer claim','result':'FAIL','inputs':inputs,'command':cmd,'limits':{'wall_seconds':a.timeout,'rtl_cycles':5000000},'stimuli':events}
 start=time.monotonic();process=None
 try:
  with (out/'machine.log').open('w') as log:
   process=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);status=process.wait(timeout=a.timeout)
   if status:raise RuntimeError('RTL command exited '+str(status))
  words=struct.unpack('<80Q',(out/'records.bin').read_bytes());report['header']=words[:8];report['records']=[words[16+8*i:24+8*i] for i in range(8)]
  if words[0]!=0x4c4d4d50 or words[6]!=0:raise AssertionError(f'guest marker/status {words[0]:x}/{words[6]}')
  if (words[1],words[3],words[4],words[5])!=(511,8,1,0):raise AssertionError('feature/record/consumption/cancel receipt')
  expected=[90,546,552,564,(1<<24)|312,79,192,194]
  for i,data in enumerate(expected):
   row=report['records'][i]
   if row[0]!=data or row[2]-row[1]!=3 or row[4:]!=(1,2,1,1):raise AssertionError(f'independent stream{i} oracle: {row}')
  audio=(out/'audio.bin').read_bytes()
  if audio[:8]!=b'LMPCM001' or len(audio)!=32:raise AssertionError('single actual DAC consumption record absent')
  tick,position,value=struct.unpack('<3Q',audio[8:]);report['pcm']={'tick':tick,'position':position,'signed_sample':value if value<1<<63 else value-(1<<64)}
  if (position,value)!=(1,32767):raise AssertionError('signed16 gain/clipping DAC oracle')
  if any(digest(v['path'])!=v['sha256'] for v in inputs.values()):raise AssertionError('consumed input changed')
  report['result']='PASS'
 except Exception as e:report['error']=str(e);raise
 finally:
  if process is not None:
   if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
   process.wait(timeout=10)
  report['elapsed_seconds']=time.monotonic()-start;report['outputs']={v.name:digest(v) for v in out.iterdir() if v.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('command','inputs')},indent=2))
if __name__=='__main__':main()
