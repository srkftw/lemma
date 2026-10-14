#!/usr/bin/env python3
"""Source-bound Action equivalence and genuine RV64 IPC borrowing component.

No CPU timing, full-image or completed course installation claim is made here.
"""
import argparse,fcntl,json,os,re,resource,shutil,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256,write_json

def source_inputs(root):
 names={'flake.nix','flake.lock','lean-toolchain','lakefile.toml','lake-manifest.json','tooling/toolchain-lock.json','scripts/check_ipc_rpc_borrow.py','scripts/core0_common.py'}
 pending=['tests/kernel/IPCRPCBaseReuse.lean','tests/kernel/IPCRPCBaseLower.lean']
 while pending:
  name=pending.pop()
  if name in names:continue
  names.add(name);path=root/name
  if not path.is_file():raise Core0Error('missing exact source '+name)
  for line in path.read_text().splitlines():
   if not line.startswith('import '):continue
   for module in line[7:].split():
    if module.startswith('Lemma.'):
     if not re.fullmatch(r'Lemma(?:\.[A-Za-z0-9_]+)+',module):raise Core0Error('unsupported source import')
     pending.append(module.replace('.','/')+'.lean')
    elif module=='tests.kernel.IPCCallBaseReuse':pending.append('tests/kernel/IPCCallBaseReuse.lean')
    elif not any(module==n or module.startswith(n+'.') for n in ('Lean','Init','Std')):raise Core0Error('unaccounted module '+module)
 return {name:sha256(root/name) for name in sorted(names)}

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
 root=Path(__file__).resolve().parents[1];out=a.output_dir.resolve()
 if out.exists() or not out.is_relative_to(root/'build/kernel'):p.error('unused build/kernel component output required')
 out.mkdir(parents=True);started=time.monotonic();commands=[];result={'status':'FAIL','scope':'hosted actual Lean Actions plus genuine kernel-v0.4 LLVM/RV64 component; CPU timing/full image/course installation NOT_RUN','bounds':{'aggregate_host_seconds':600,'action_fixture_seconds':240,'other_command_seconds':120},'commands':commands}
 os.environ['LEAN_NUM_THREADS']='2';result['host_environment']={'LEAN_NUM_THREADS':'2','lean_worker_threads':2}
 resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30));resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
 def run(label,argv,env=None):
  remaining=600-(time.monotonic()-started)
  if remaining<=0:raise Core0Error('original600s aggregate component bound')
  record=run_bounded(argv,cwd=root,env=env,timeout_seconds=min(240 if label=='actions' else 120,remaining))
  (out/(label+'.stdout.log')).write_bytes(record.stdout);(out/(label+'.stderr.log')).write_bytes(record.stderr)
  commands.append({'label':label,'argv':list(argv),'returncode':record.returncode,'wall_seconds':record.elapsed_seconds})
  if record.returncode:raise Core0Error('actual '+label+' failed; original logs retained')
  return record.stdout
 try:
  tools=require_tools(('lake','lean','opt','llc','llvm-nm','llvm-readelf'));result['tools']=tools
  versions={name:run('version-'+name,[tool,'--version']).decode().strip() for name,tool in tools.items()};result['versions']=versions
  if '4.34.1' not in versions['lean'] or '20.1.8' not in versions['llc']:raise Core0Error('pinned tools differ')
  with (root/'build/task006-lake.lock').open('a+b') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);before=source_inputs(root);archive=out/'consumed-source-root';archive.mkdir()
   for name,digest in before.items():
    if sha256(root/name)!=digest:raise Core0Error('source changed before archive '+name)
    dest=archive/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,dest)
   write_json(out/'source-inputs.json',before);result.update(source_inputs=before,source_count=len(before))
   run('build',[tools['lake'],'build','Lemma.Kernel.IPC','Lemma.Compiler.CFGLower'])
   model=Path('.lake/build/lib/lean/tests/kernel/IPCCallBaseReuse.olean');model.parent.mkdir(parents=True,exist_ok=True)
   run('compile-reused-model',[tools['lake'],'env','lean','-j2','-o',str(model),'tests/kernel/IPCCallBaseReuse.lean'])
   fixture=run('actions',[tools['lake'],'env','lean','-j2','tests/kernel/IPCRPCBaseReuse.lean'])
   if fixture.count(b'IPC_RPC_BORROW_ACTIONS:PASS')!=2:raise Core0Error('both ordinary and expanded real fixtures required')
   result['action_observation']=fixture.decode().strip()
   env=dict(os.environ,LEMMA_IPC_RPC_FIXTURE_DIR=str(out/'component'))
   run('lower',[tools['lake'],'env','lean','-j2','tests/kernel/IPCRPCBaseLower.lean'],env)
   if source_inputs(root)!=before:raise Core0Error('source changed during exact capture')
  component=out/'component/rpc';ll=component/'production.ll';opt=component/'production.opt.ll';obj=component/'production.o'
  run('opt',[tools['opt'],'-S','-passes=default<O2>','-verify-each',str(ll),'-o',str(opt)])
  run('object',[tools['llc'],'-mtriple=riscv64-unknown-none-elf','-mattr=+m,-a,-f,-d,-c','-relocation-model=static','-filetype=obj',str(opt),'-o',str(obj)])
  undefined=run('undefined',[tools['llvm-nm'],'--undefined-only',str(obj)]).decode().split()
  if undefined!=['U','lemma_exec_firmware_call']:raise Core0Error('unaccounted runtime/helper boundary '+repr(undefined))
  run('elf',[tools['llvm-readelf'],'-h','-A','-r',str(obj)])
  result.update(status='PASS_IPC_RPC_BORROW_COMPONENT',artifacts={n:sha256(component/n) for n in ('production.ll','production.opt.ll','production.o','production-unit.json','production-symbols.txt')},unresolved_boundary=['lemma_exec_firmware_call'])
 except BaseException as e:result['error']=repr(e);raise
 finally:
  result['wall_seconds']=time.monotonic()-started;result['child_peak_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss;write_json(out/'result.json',result)
 print(result['status'],result['wall_seconds'])
if __name__=='__main__':main()
