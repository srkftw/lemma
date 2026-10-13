#!/usr/bin/env python3
"""Bounded genuine maintained IPC-borrow lowering and independent fault fixture.

This qualifies a source component, not an RTL guest, complete image or timing.
All generated LLVM/objects stay under an unused ignored build directory.
"""
import argparse,copy,json,time
from pathlib import Path
from core0_common import Core0Error,require_tools,sha256,run_bounded
from check_silicon import command
from check_ble_packet import validate_object_attributes
from ipc_poll_borrow import (_poll_rows,validate_reachable_helpers,
                            validate_ipc_poll_borrow,task_lookup_record_allowed_callers)
ROOT=Path(__file__).resolve().parents[1]

def mutate_body(ir,symbol,old,new):
 start=ir.rfind('define ',0,ir.index('@'+symbol+'('));end=ir.index('\n}',start)+2
 text=ir[start:end]
 if old not in text:raise Core0Error('missing independently selected body mutation')
 return ir[:start]+text.replace(old,new,1)+ir[end:]

def mutations(unit,ir):
 _,names=_poll_rows(unit);rejected=[]
 selected=[('lookup-zero','Lemma.Kernel.Task.lookupRecord','icmp eq i64 %arg0, 0','icmp eq i64 %arg0, 1'),
  ('scan-priority','Lemma.Kernel.Task.findStep','icmp ult i64','icmp ule i64'),
  ('poll-error','Lemma.Kernel.IPC.pollAt','icmp eq i1','icmp ne i1'),
  ('pending-self','Lemma.Kernel.IPCStorage.pendingAt','i64 %arg0)','i64 %arg1)'),
  ('task-live-row','Lemma.Kernel.Task.pollIPCStep','icmp eq i64','icmp ne i64')]
 for label,source,old,new in selected:
  bad=mutate_body(ir,names[source],old,new)
  try:validate_ipc_poll_borrow(unit,bad)
  except Core0Error:rejected.append(label)
  else:raise Core0Error('admitted changed IPC/lookup body: '+label)
 for label,field,value in [('role','role','user')]:
  bad=copy.deepcopy(unit);bad[field]=value
  try:validate_ipc_poll_borrow(bad,ir)
  except Core0Error:rejected.append(label)
  else:raise Core0Error('admitted changed borrow role')
 for source in ('Lemma.Kernel.Task.lookupRecord','Lemma.Kernel.Task.findStep','Lemma.Kernel.IPC.pollAt'):
  bad=copy.deepcopy(unit);bad['functions']=[f for f in bad['functions'] if f['symbol']!=names[source]]
  try:validate_ipc_poll_borrow(bad,ir)
  except Core0Error:rejected.append('missing:'+source)
  else:raise Core0Error('admitted incomplete borrow inventory')
 return rejected

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work-dir',type=Path,required=True)
 parser.add_argument('--timeout',type=int,default=180);args=parser.parse_args();out=args.work_dir.resolve()
 if not 30<=args.timeout<=600:parser.error('timeout must be30..600seconds')
 if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('work-dir must be unused under build/')
 out.mkdir(parents=True);started=time.monotonic();result={'schema_version':1,'status':'FAIL',
  'scope':'genuine maintained checked Lean IPC bodies, independent original-source finiteRAM faults and RV64 objects; no full-image/RTL timing claim'}
 names=['scripts/check_kernel_ipc_poll_borrow.py','scripts/ipc_poll_borrow.py','scripts/audit_kernel.py',
  'scripts/core0_common.py','scripts/check_silicon.py','scripts/check_ble_packet.py',
  'tests/kernel/IPCPolledBaseLower.lean','tests/kernel/IPCPolledBaseReuse.lean','flake.nix','flake.lock',
  'lakefile.toml','lean-toolchain','tooling/toolchain-lock.json']
 names+=sorted(str(p.relative_to(ROOT)) for p in (ROOT/'Lemma').rglob('*.lean'))
 try:
  before={n:sha256(ROOT/n) for n in names};result['source_inputs']=before
  tools=require_tools(['lean','lake','opt','llc','llvm-nm','llvm-readobj']);result['tools']={}
  for name,path in tools.items():
   observed=run_bounded([path,'--version'],cwd=ROOT,timeout_seconds=30)
   if observed.returncode or not path.startswith('/nix/store/') or not observed.stdout.strip():raise Core0Error('missing pinned tool identity')
   result['tools'][name]={'path':path,'sha256':sha256(Path(path)),'version':observed.stdout.decode().splitlines()[:4]}
  commands=[];result['commands']=commands
  def run(argv,log):
   remaining=args.timeout-(time.monotonic()-started)
   if remaining<=0:raise Core0Error('predeclared total component deadline exceeded')
   commands.append(command(argv,out/log,remaining))
  run([tools['lake'],'build','Lemma.Kernel.Task','Lemma.Compiler.CFGLower'],'build.log')
  run(['env','LEMMA_IPC_POLL_FIXTURE_DIR='+str(out/'lowered'),tools['lake'],'env','lean','tests/kernel/IPCPolledBaseLower.lean'],'lowering.log')
  if (out/'lowering.log').read_text().count('IPC_POLL_PRODUCTION_COMPILE:PASS')!=3:raise Core0Error('missing genuine full/partial lowering observations')
  reports={}
  for label in ('full','pending','poll'):
   d=out/'lowered'/label;unit=json.loads((d/'production-unit.json').read_text());ir=(d/'production.ll').read_text()
   reports[label]=validate_reachable_helpers(unit,ir)
   allowed=task_lookup_record_allowed_callers(unit,ir)
   expected={'Lemma.Kernel.Task.lookup','Lemma.Kernel.Task.contextAt'}
   if label=='full':expected.add('Lemma.Kernel.Task.pollIPCStep')
   if allowed!=expected:raise Core0Error('partial/public closure improperly changed Task lookup authority')
   if label=='full':result['rejected_mutations']=mutations(unit,ir)
   run([tools['opt'],'-passes=default<O2>','-S',str(d/'production.ll'),'-o',str(d/'production.opt.ll')],label+'-opt.log')
   run([tools['llc'],'-mtriple=riscv64-unknown-elf','-mattr=+m,-a,-f,-d,-c','-target-abi=lp64','-filetype=obj',str(d/'production.opt.ll'),'-o',str(d/'production.o')],label+'-object.log')
   run([tools['llvm-nm'],'--undefined-only',str(d/'production.o')],label+'-undefined.log')
   undefined=(out/(label+'-undefined.log')).read_text().split()
   if undefined not in ([],['U','lemma_exec_firmware_call']):raise Core0Error('unaccounted IPC target runtime dependency')
   run([tools['llvm-readobj'],'--file-header','--arch-specific',str(d/'production.o')],label+'-attributes.log')
   validate_object_attributes((out/(label+'-attributes.log')).read_text())
  result['genuine_guards']=reports
  run([tools['lake'],'env','lean','tests/kernel/IPCPolledBaseReuse.lean'],'faults.log')
  observed=(out/'faults.log').read_text()
  if observed.count('IPC_BORROW_FAULTS:PASS')!=2 or 'cases952 ' not in observed or 'cases1720 ' not in observed:
   raise Core0Error('independent original-source fault corpus incomplete')
  if {n:sha256(ROOT/n) for n in names}!=before:raise Core0Error('consumed source changed during component qualification')
  result.update(status='PASS',fault_cases=2672,
   artifacts={str(p.relative_to(out)):sha256(p) for p in sorted(out.rglob('*')) if p.is_file()})
 except BaseException as error:result['error']=repr(error)
 result['seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ('status','seconds','error') if k in result}))
 return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
