#!/usr/bin/env python3
"""Same binary, same genuine guest and exact prefix/suffix; host pool only."""
import argparse,hashlib,json,os,selectors,signal,subprocess,time
from pathlib import Path
import silicon_guest
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()
def require(v,s):
 if not v:raise ValueError(s)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True)
 p.add_argument('--cycles',type=int,default=2000000);p.add_argument('--profile',default='lemma-silicon-dev/0.5.0');p.add_argument('--workload',default='ble')
 a=p.parse_args();out=a.work_dir.resolve()
 if out.exists() or not out.is_relative_to(ROOT/'build') or not 100000<=a.cycles<=10000000:p.error('unused bounded work directory required')
 out.mkdir(parents=True);result={'schema':'lemmasim-native-host-pool-evidence/1','status':'FAIL','scope':'same exact generated scalar RTL and genuine guest, fixed target cycles; host worker-pool resource/time comparison only'};started=time.monotonic()
 try:
  data=silicon_guest.prepared(a.workload,a.profile);guest=data['workloads'][a.workload];result['prepared_identity']=data
  for workers in (0,1):
   directory=out/f'workers-{workers}';directory.mkdir();log=(directory/'errors.log').open('xb')
   command=[data['binary']['path'],'--rom',data['rom']['path'],'--image',guest['image']['path'],
    '--load',f"0x{silicon_guest.profile(a.profile)['dtb_base']:x}:{guest['dtb']['path']}",
    '--descriptor',guest['descriptor']['path'],'--uart-output',str(directory/'uart.bin'),'--session',
    '--fork-directory',str(directory),'--quiet-uart','--host-threads',str(workers),'--deadline','120']
   process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True,text=True,bufsize=1);ready=selectors.DefaultSelector();ready.register(process.stdout,selectors.EVENT_READ)
   def call(line):
    process.stdin.write(line+'\n');process.stdin.flush();require(ready.select(130),'bounded machine response failed');wire=process.stdout.readline();require(wire,'machine ended before response');reply=json.loads(wire);require(reply.get('ok'),reply.get('error','native command failed'));return reply['result']
   try:
    zero=call('inspect');require(zero['cycle']==0,'machine prefix was not cold');t=time.monotonic();prefix=call('run '+str(a.cycles));elapsed=time.monotonic()-t
    require(prefix['cycle']==a.cycles and not prefix['finished'],'fixed target prefix ended early')
    status=Path(f'/proc/{process.pid}/status').read_text().splitlines();resources={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status if line.startswith(('Threads:','VmRSS:','VmHWM:'))}
    call('snapshot '+str(directory/'prefix.chk'));before=call('inspect');suffix=call('run 100000');call('snapshot '+str(directory/'suffix.chk'))
    call('restore '+str(directory/'prefix.chk'));require(call('inspect')['cycle']==before['cycle'],'restore changed prefix boundary');call('run 100000');call('snapshot '+str(directory/'replay.chk'))
    require(sha(directory/'suffix.chk')==sha(directory/'replay.chk'),'same-host-pool authoritative suffix differs')
    result[f'workers_{workers}']={'argv':command,'prefix_seconds':elapsed,'cycles_per_second':a.cycles/elapsed,'resources':resources,'prefix':prefix,'suffix':suffix,'prefix_sha256':sha(directory/'prefix.chk'),'suffix_sha256':sha(directory/'suffix.chk'),'checkpoint_bytes':(directory/'prefix.chk').stat().st_size}
   finally:
    if process.poll() is None:
     try:call('destroy');process.wait(timeout=10)
     except BaseException:
      if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
      process.wait(timeout=10)
    ready.close();log.close()
  require(result['workers_0']['prefix_sha256']==result['workers_1']['prefix_sha256'] and result['workers_0']['suffix_sha256']==result['workers_1']['suffix_sha256'],'host-pool choice changed authoritative prefix or suffix bytes')
  result['status']='PASS';result['elapsed_ratio_default_over_one']=result['workers_0']['prefix_seconds']/result['workers_1']['prefix_seconds']
 except BaseException as e:result['error']=str(e);raise
 finally:
  result['host_seconds']=time.monotonic()-started;result['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'elapsed_ratio_default_over_one':result['elapsed_ratio_default_over_one'],'default':result['workers_0']['resources'],'one':result['workers_1']['resources']},indent=2))
if __name__=='__main__':main()
