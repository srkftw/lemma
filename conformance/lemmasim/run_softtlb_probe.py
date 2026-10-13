#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded actual guest data-translation probe; never certifies total continuation.

Guest PTE mutation and both SFENCE operations come from the audited Lean ELF.
The host supplies clocks and private VM ownership, reads results and preserves
all archives. It never writes a guest PTE or instruction or flushes a CPU cache.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,signal,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(Path(__file__).resolve().parent))
from lemmasim_fast import QMP,CPU
from check_logical_softtlb import decode

def sha(p):
 s=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):s.update(b)
 return s.hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
class Machine:
 def __init__(self,args,path):
  self.args=args;self.path=path;path.mkdir();self.socketdir=tempfile.TemporaryDirectory(prefix='lemma-tlb-',dir='/tmp');sock=Path(self.socketdir.name)/'qmp';self.log=(path/'machine.log').open('xb');self.qmp=None
  binding='lemma-silicon-fast-softtlb' if args.logical else 'lemma-silicon-fast'
  self.argv=[str(args.qemu),'-machine',binding,'-cpu',CPU,'-m','128M','-smp','1','-bios','none','-kernel',str(args.guest_elf),'-dtb',str(args.dtb),'-display','none','-monitor','none','-serial','file:'+str(path/'uart.bin'),'-qmp','unix:'+str(sock)+',server=on,wait=off','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031','-global','lemma-paper-pen.raw-output='+str(path/'input.bin')]
  (path/'argv.json').write_text(json.dumps(self.argv,indent=2)+'\n');self.process=subprocess.Popen(self.argv,stdout=self.log,stderr=self.log,start_new_session=True)
  try:self.qmp=QMP(sock,self.process,args.timeout)
  except BaseException:self.close();raise
 def get(self,p):return self.qmp.execute('qom-get',{'path':'/machine/lemma-hardware','property':p})
 def state(self):return {'virtual_ns':int(self.get('virtual-time')),'registers':self.qmp.execute('human-monitor-command',{'command-line':'info registers'}),'status':self.qmp.execute('query-status'),'devices':json.loads(self.get('device-state'))}
 def run(self,ns):
  require(ns>int(self.get('virtual-time')),'Non-increasing declared boundary');started=time.monotonic()
  self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':str(ns)});self.qmp.execute('cont')
  while self.qmp.execute('query-status')['running']:
   if time.monotonic()-started>=self.args.timeout:
    self.qmp.execute('stop');(self.path/'timeout-state.json').write_text(json.dumps(self.state(),indent=2)+'\n');raise TimeoutError('Declared host bound exceeded')
   time.sleep(.001)
  state=self.state();(self.path/('boundary-'+str(ns)+'.json')).write_text(json.dumps(state,indent=2)+'\n');require(state['virtual_ns']==ns,'Exact instruction-clock boundary missed: '+str(state['virtual_ns'])+' != '+str(ns));return {'state':state,'host_seconds':time.monotonic()-started}
 def save(self,pair):
  args={'filename':str(pair)}
  if self.args.logical:args['cache-filename']=str(pair.with_suffix('.tlb'))
  self.qmp.execute('lemma-save-machine-softtlb' if self.args.logical else 'lemma-save-machine',args)
  return decode(pair.with_suffix('.tlb'),pair) if self.args.logical else None
 def load(self,pair):
  args={'filename':str(pair)}
  if self.args.logical:args['cache-filename']=str(pair.with_suffix('.tlb'))
  self.qmp.execute('lemma-load-machine-softtlb' if self.args.logical else 'lemma-load-machine',args)
 def results(self):
  # QEMU's physical read-only monitor observes words already written by guest.
  text=self.qmp.execute('human-monitor-command',{'command-line':'xp /2gx 0x82105000'})
  (self.path/'guest-result-words.txt').write_text(text)
  words=[int(x,16) for x in re.findall(r'0x([0-9a-fA-F]{16})',text)]
  require(re.match(r'^(?:00000000)?82105000:',text) and len(words)==2,'Unsupported physical observation format: '+repr(text))
  return {'stale':words[0],'fenced':words[1],'raw':text,'uart_hex':(self.path/'uart.bin').read_bytes().hex()}
 def close(self):
  if getattr(self,'process',None):
   if self.process.poll() is None:
    try:
     if self.qmp:self.qmp.execute('quit')
     self.process.wait(timeout=5)
    except BaseException:
     if self.process.poll() is None:os.killpg(self.process.pid,signal.SIGKILL)
     self.process.wait(timeout=5)
  if self.qmp:self.qmp.close();self.qmp=None
  self.log.close();self.socketdir.cleanup()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qemu',type=Path,required=True);p.add_argument('--guest-elf',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--logical',action='store_true');p.add_argument('--start-ns',type=int,default=1000000);p.add_argument('--end-ns',type=int,default=300000000);p.add_argument('--timeout',type=float,default=120);a=p.parse_args()
 for k in ['qemu','guest_elf','dtb','work_dir']:setattr(a,k,getattr(a,k).resolve())
 require(0<a.start_ns<a.end_ns<(1<<63) and a.start_ns%8==a.end_ns%8==0 and 0<a.timeout<=600,'Invalid declared bounds');a.work_dir.mkdir()
 r={'status':'RUNNING','scope':'actual guest-issued stale data translation and SFENCE; total QEMU continuation remains GAP_CONFIRMED','logical_sidecar':a.logical,'plan':{'start_ns':a.start_ns,'end_ns':a.end_ns,'host_seconds_per_interval':a.timeout,'external_events':[],'medium':'absent, independently constructed per process; no storage operations'},'inputs':{k:{'path':str(getattr(a,k)),'sha256':sha(getattr(a,k))} for k in ['qemu','guest_elf','dtb']},'observer_sha256':sha(__file__),'decoder_sha256':sha(Path(__file__).with_name('check_logical_softtlb.py'))}
 path=a.work_dir/'result.json';path.write_text(json.dumps(r,indent=2)+'\n');owners=[]
 try:
  original=Machine(a,a.work_dir/'original');owners.append(original);r['original_prefix']=original.run(a.start_ns)
  require((original.path/'uart.bin').read_bytes()==b'W','Actual warmed guest/PTE marker missing or suffix already advanced');pair=a.work_dir/'boundary.vmstate';cache=original.save(pair)
  if cache:
   (a.work_dir/'boundary-decoded.json').write_text(json.dumps(cache,indent=2)+'\n');r['boundary_sidecar']={'sha256':sha(pair.with_suffix('.tlb')),'bytes':pair.with_suffix('.tlb').stat().st_size,'boundary_ns':cache['boundary_ns']}
  r['ordinary_boundary']={'sha256':sha(pair),'bytes':pair.stat().st_size};fork=Machine(a,a.work_dir/'fork');owners.append(fork);require(int(fork.get('virtual-time'))==0,'Fork was already run');fork.load(pair)
  require(int(fork.get('virtual-time'))==a.start_ns,'Restore boundary changed');r['original_suffix']=original.run(a.end_ns);r['fork_suffix']=fork.run(a.end_ns)
  r['original_results']=original.results();r['fork_results']=fork.results()
  r['original_final_sidecar']=original.save(a.work_dir/'original-final.vmstate');r['fork_final_sidecar']=fork.save(a.work_dir/'fork-final.vmstate')
  require(r['original_results']['stale']==111 and r['original_results']['fenced']==222,'Original genuine guest did not retain stale read then obey SFENCE')
  expected=111 if a.logical else 222
  require(r['fork_results']['stale']==expected and r['fork_results']['fenced']==222,'Fork data result differs from declared narrower property')
  r['status']='PASS_LOGICAL_DATA_TRANSLATION_SUFFIX' if a.logical else 'GAP_CONFIRMED_ACTUAL_GUEST_DATA_TRANSLATION'
 except BaseException as e:r['status']='FAIL';r['error']=repr(e)
 finally:
  for m in owners:m.close()
  r['owners_reaped']=all(m.process.poll() is not None for m in owners);path.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'error':r.get('error'),'results':[r.get('original_results'),r.get('fork_results')]}),flush=True)
 return 0 if r['status']!='FAIL' else 1
if __name__=='__main__':raise SystemExit(main())
