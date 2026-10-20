#!/usr/bin/env python3
"""Bound configured native objects, reproduce their link, then one MM2 object.

All retained objects are newly observed. The ordinary cold qemu_uart.nix recipe
remains reproducible; this action changes exactly its derived hardware unit.
"""
import argparse,hashlib,json,os,re,shutil,signal,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);a=p.parse_args()
root=Path.cwd();out=root/'mm2-reuse';out.mkdir();start=time.monotonic();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r={'schema':'lemma-native-mm2-retained-build/1','status':'FAIL','commands':[],'limits':{'whole_seconds':360,'combined_rss_bytes':1<<30,'minimum_available_bytes':2<<30,'output_bytes':12<<30},'peak_group_rss_bytes':0}
def require(v,m):
 if not v:raise ValueError(m)
def run(cmd,phase,env=None):
 require(time.monotonic()-start<360 and shutil.disk_usage(root).free>=2<<30,'original preflight bounds');begin=time.monotonic();proc=None;row={'phase':phase,'argv':list(map(str,cmd))}
 try:
  with (out/(phase+'.log')).open('wb') as log:
   proc=subprocess.Popen(row['argv'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
   while proc.poll() is None:
    rss=0
    for f in Path('/proc').glob('[0-9]*/stat'):
     try:
      fields=f.read_text().rsplit(')',1)[1].split()
      if int(fields[2])==proc.pid:rss+=max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE')
     except (OSError,ValueError,IndexError):pass
    available=next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    r['peak_group_rss_bytes']=max(r['peak_group_rss_bytes'],rss)
    require(rss<=1<<30 and available>=2<<30 and time.monotonic()-start<360,'original owned-process/whole bounds');time.sleep(.1)
   require(proc.returncode==0,'actual command failed: '+phase)
 finally:
  if proc and proc.poll() is None:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  row.update(seconds=time.monotonic()-begin,exit_code=proc.returncode if proc else None);r['commands'].append(row)
 return (out/(phase+'.log')).read_text()
def objects():return {str(p):sha(p) for p in sorted((root/'build').rglob('*')) if p.is_file() and p.suffix in ('.o','.a')}
try:
 binary=root/'build/qemu-system-riscv64';require(sha(binary)=='47c819aac5aba5cb6ce8f820f63f537e9fa08c7967b3aec9a4ecc75cca8a9526','exact retained pre-install logical2 build ELF required (installed ELF has separate Nix fixup identity)')
 bound=objects();require(len(bound)==1457,'complete observed native object/archive closure');(out/'retained-objects.json').write_text(json.dumps(bound,sort_keys=True,indent=2)+'\n')
 shutil.copyfile(binary,out/'baseline-original.qemu');baseline=sha(binary);binary.unlink()
 dry=run(['ninja','-C','build','-n','qemu-system-riscv64'],'baseline-plan');version={'libqmp.a.p/monitor_qmp-cmds-control.c.o','libsystem.a.p/system_vl.c.o'}
 require(set(re.findall(r'Compiling C object (\S+)',dry))<=version and 'Linking target qemu-system-riscv64' in dry,'unexpected baseline invalidation')
 env=os.environ.copy();current=env['out']+'/lib';old='/nix/store/1nirimaaikhpbkf7af763zp3fj8yg6z2-lemmasim-qemu-raw-uart-logical-v2-retained-11.1.1/lib'
 require(env.get('NIX_LDFLAGS','').count('-rpath '+current)==1,'exact Nix output RUNPATH injection');env['NIX_LDFLAGS']=env['NIX_LDFLAGS'].replace('-rpath '+current,'-rpath '+old)
 log=run(['ninja','-C','build','-j2','qemu-system-riscv64'],'baseline-link',env);require(not re.findall(r'Compiling C object (\S+)',log),'baseline recompiled retained bytes')
 require(sha(binary)==baseline and objects()==bound,'real baseline must reproduce byte-identical original ELF and objects');r['baseline_reproduced']=True
 names=['lemma_qemu.c','lemma_multimodal_qemu.inc.c','lemma_multimodal_v2.c','lemma_multimodal_v2.h','lemma_multimodal_checkpoint_valid.inc.c']
 old_sources={n:sha(root/'hw/riscv'/n) for n in names if (root/'hw/riscv'/n).is_file()};r['predecessor_sources']=old_sources
 log=run(['python3',a.inputs/'tooling/lemmasim/patch_multimodal_v2.py',root,'--mode','native','--host-source',a.inputs/'sim/host'],'apply-mm2')
 r['overlay']=json.loads(log);require(set(r['overlay']['files'])==set(names),'exact five-source overlay')
 binary.unlink();dry=run(['ninja','-C','build','-n','qemu-system-riscv64'],'changed-plan');expected='libqemu-riscv64-softmmu.a.p/hw_riscv_lemma_qemu.c.o';planned=set(re.findall(r'Compiling C object (\S+)',dry))
 require(expected in planned and planned<=version|{expected} and 'Linking target qemu-system-riscv64' in dry,'unexpected MM2 compiler dependencies')
 log=run(['ninja','-C','build','-j2','qemu-system-riscv64'],'changed-object-link');fresh=re.findall(r'Compiling C object (\S+)',log);require(fresh==[expected],'exactly one hardware object must compile')
 after=objects();changed=[n for n in bound if after.get(n)!=bound[n]];require(changed==[str(root/'build'/expected)] and set(after)==set(bound),'unrelated retained object changed')
 r.update(status='PASS_MM2_HARDWARE_OBJECT_AND_REAL_LINK',fresh_objects=1,reused_objects_and_archives=1456,changed_objects=changed,binary_sha256=sha(binary),execution_binding='lemma-silicon-fast-mm2-subset/0.1.0',profile='lemma-silicon-dev/0.14.0',controller_abi_available=[1,2],checkpoint_scope='ABI2 state not publicly admitted before real pending ring boundary tests')
except BaseException as e:r['error']=repr(e);raise
finally:
 r['seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n');print(r['status'],r.get('error',''),r['seconds'])
