#!/usr/bin/env python3
"""Inspect actual qualified IPC LLVM and reject changed borrow witnesses."""
import argparse,copy,json,re,time
from pathlib import Path
from core0_common import Core0Error,sha256,write_json
from audit_kernel import _ir_definition_body
from ipc_call_borrow import validate_ipc_call_borrow
from ipc_poll_borrow import validate_reachable_helpers

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--component',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('refuse retained receipt')
 started=time.monotonic();u=json.loads((a.component/'production-unit.json').read_text());ir=(a.component/'production.ll').read_text()
 result={'status':'FAIL','scope':'original genuine LLVM/component observer only; no recompilation, CPU or install claim'}
 try:
  qualified=validate_reachable_helpers(u,ir)
  if qualified['pending']['call_borrow'] is None:raise Core0Error('new complete call/pending route not actually inspected')
  names={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row['symbol'] for row in u['functions']}
  source='Lemma.Kernel.IPC.callBeginWithLimit';body=_ir_definition_body(ir,names[source]);line=next(l for l in body.splitlines() if 'sub i64' in l)
  missing=_ir_definition_body(ir,names['Lemma.Kernel.IPCStorage.prepareAt'])
  live=next(l for l in missing.splitlines() if 'call { i64, i64 } @'+names['Lemma.Kernel.IPCStorage.pendingAt']+'(' in l)
  cases={'wrong-base':ir.replace(line,line.replace('sub i64','add i64'),1),
    'cross-descriptor':ir.replace('call { i64, i64 } @'+names['Lemma.Kernel.IPCStorage.prepareAt']+'(i64 %arg1,','call { i64, i64 } @'+names['Lemma.Kernel.IPCStorage.prepareAt']+'(i64 %arg2,',1),
    'missing-live-pending-binding':ir.replace(live,live.replace('i64 %arg1','i64 0'),1)}
  extra=copy.deepcopy(u);extra['functions'].append({'source':'Lemma.Kernel.IPC.unapprovedBorrow','symbol':'unapproved_borrow','args':['u64','u64'],'effects':['checked-access','physical-read']})
  cases['unapproved-caller']=(ir+'\ndefine { i64, i64 } @unapproved_borrow(i64 %arg0, i64 %arg1) nounwind noinline "disable-tail-calls"="true" {\nentry:\n  %result = call { i64, i64 } @'+names['Lemma.Kernel.IPCStorage.packetAt']+'(i64 %arg0, i64 %arg1, i64 1)\n  ret { i64, i64 } %result\n}\n',extra)
  negatives={}
  for label,value in cases.items():
   changed,unit=value if isinstance(value,tuple) else (value,u)
   if changed==ir:raise Core0Error('negative did not actually change genuine observer input')
   try:validate_reachable_helpers(unit,changed)
   except Core0Error as e:negatives[label]=str(e)
   else:raise Core0Error('borrow witness mutation admitted:'+label)
  result.update(status='PASS_CLOSED_IPC_CALL_BORROW_OBSERVERS',component_sha256={name:sha256(a.component/name) for name in ('production.ll','production-unit.json','production.o')},qualification=qualified,negative_rejections=negatives,observer_sha256={name:sha256(Path(__file__).with_name(name)) for name in ('ipc_call_borrow.py','ipc_poll_borrow.py','audit_kernel.py','check_ipc_call_borrow_observer.py')})
 finally:
  result['wall_seconds']=time.monotonic()-started;write_json(a.output,result)
 print(result['status'])
if __name__=='__main__':main()
