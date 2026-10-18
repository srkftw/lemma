#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run an actual elaborated Lean M-mode controller probe; independent raw oracle.
This is a bounded component workload, never full workbook/consumer/P2 acceptance.
"""
import argparse,hashlib,json,os,signal,struct,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from lemmasim_fast import QMP,CPU

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--raw-uart',action='store_true');p.add_argument('--qemu',type=Path,required=True);p.add_argument('--guest',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=120);a=p.parse_args()
 out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
 inputs={name:{'path':str(path.resolve()),'sha256':digest(path)} for name,path in [('qemu',a.qemu),('guest',a.guest),('dtb',a.dtb),('observer',Path(__file__))]}
 report={'schema':'lemma-multimodal-guest-probe/v1','result':'FAIL','scope':'actual Lean M-mode converter+PCM component; no workbook,headband-link,full image/raw sensor,consumer realtime,checkpoint or physical claim','inputs':inputs,'limits':{'wall_seconds':a.timeout,'virtual_cycles_100MHz':5000000},'stimuli':[{'stream':i,'converter_input':100+i,'reference':10,'quality':0,'origin':'SYNTHETIC'} for i in range(8)]}
 q=None;control=None;start=time.monotonic()
 try:
  with tempfile.TemporaryDirectory(prefix='lemma-mm-qmp-') as temporary:
   socket=Path(temporary)/'qmp.sock'
   cmd=[str(a.qemu.resolve()),'-machine','lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1','-bios','none','-kernel',str(a.guest.resolve()),'-dtb',str(a.dtb.resolve()),'-display','none','-monitor','none','-serial','file:'+str(out/'uart.bin'),'-qmp',f'unix:{socket},server=on,wait=off','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031','-global','lemma-paper-pen.multimodal-audio-output='+str(out/'audio.bin')]
   report['command']=cmd
   with (out/'machine.log').open('wb') as log:
    q=subprocess.Popen(cmd,stdout=log,stderr=log,start_new_session=True);control=QMP(socket,q,min(15,a.timeout))
    if a.raw_uart:
     version=control.execute('qom-get',{'path':'/machine/lemma-hardware','property':'raw-uart-version'})
     if version!='lemma-raw-uart/1':raise ValueError('actual raw UART version differs')
     control.execute('qom-set',{'path':'/machine/lemma-hardware','property':'enable-raw-uart','value':version})
     report['raw_uart']=json.loads(control.execute('qom-get',{'path':'/machine/lemma-hardware','property':'raw-uart-state'}))
     if report['raw_uart'].get('enabled') is not True:raise ValueError('actual raw UART negotiation failed')
    for i in range(8):control.execute('qom-set',{'path':'/machine/lemma-hardware','property':'multimodal-stimulus','value':f'{i} {100+i} 10 0'})
    control.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':'50000000'})
    control.execute('cont');deadline=start+a.timeout
    while True:
     if time.monotonic()>deadline:raise TimeoutError('original probe wall deadline')
     event=control.read()
     if event.get('event')=='STOP':break
    report['controller_state']=json.loads(control.execute('qom-get',{'path':'/machine/lemma-hardware','property':'multimodal-state'}))
    control.execute('pmemsave',{'val':0x80410000,'size':640,'filename':str(out/'records.bin')})
    control.execute('quit');q.wait(timeout=10)
   words=struct.unpack('<80Q',(out/'records.bin').read_bytes());report['header']=words[:8];report['records']=[words[16+8*i:24+8*i] for i in range(8)]
   if words[0]!=0x4c4d4d50 or words[6]!=0:raise AssertionError(f'guest marker/status {words[0]:x}/{words[6]}; retained actual prefix')
   if (words[1],words[3],words[4],words[5])!=(511,8,1,0):raise AssertionError('guest feature/count/consumption/cancel result')
   expected=[90,546,552,564,(1<<24)|312,79,192,194]
   for i,data in enumerate(expected):
    row=report['records'][i]
    if row[0]!=data or row[2]-row[1]!=3 or row[4:]!=(1,2,1,1):raise AssertionError(f'independent stream{i} expected {data} availability3 seq/epoch/config/selector1/2/1/1 got {row}')
   audio=(out/'audio.bin').read_bytes()
   if audio[:8]!=b'LMPCM001' or len(audio)!=32:raise AssertionError('exact single digital PCM consumption record missing')
   tick,position,value=struct.unpack('<3Q',audio[8:]);report['pcm']={'tick':tick,'position':position,'signed_sample':value if value<1<<63 else value-(1<<64)}
   if (position,value)!=(1,32767):raise AssertionError('independent signed16 gain2 clipping DAC sample')
   if b'LMMP' not in (out/'uart.bin').read_bytes():raise AssertionError('guest terminal UART protocol absent')
   if any(digest(v['path'])!=v['sha256'] for v in inputs.values()):raise AssertionError('consumed input changed')
   report['result']='PASS'
 except Exception as e:report['error']=str(e);raise
 finally:
  if control is not None:control.close()
  if q is not None:
   if q.poll() is None:os.killpg(q.pid,signal.SIGKILL)
   q.wait(timeout=10)
  report['elapsed_seconds']=time.monotonic()-start;report['outputs']={v.name:digest(v) for v in out.iterdir() if v.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('command','inputs')},indent=2))
if __name__=='__main__':main()
