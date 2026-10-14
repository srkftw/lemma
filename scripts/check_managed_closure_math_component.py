#!/usr/bin/env python3
"""Inspect actual selected User7/legacy Notebook artifacts and fail-closed mutations.

No guest instructions, mathematical authority, record publication or successful
isolated request is inferred from these component checks.
"""
import argparse,copy,hashlib,json,re,sys
from pathlib import Path
from core0_common import Core0Error,sha256,write_json
import arithmetic_closure_identity as identity
import managed_closure
from audit_kernel import _ir_definition_body

def require(value,message):
 if not value:raise Core0Error(message)
def check(root):
 a=root/'arithmetic/users/arithmetic';u=json.loads((a/'unit.json').read_text())
 pre=(a/'program.ll').read_text();post=(a/'program.opt.ll').read_text()
 reports={};rejects=[]
 for optimized,ir in [(False,pre),(True,post)]:
  reports['post' if optimized else 'pre']={'managed':managed_closure.validate(ir,u,optimized=optimized),
   'authority':identity.validate(ir,u,optimized=optimized)}
 def reject(label,fn):
  try:fn()
  except (Core0Error,ValueError,KeyError,TypeError) as e:
   rejects.append({'name':label,'actual_error':str(e)});return
  raise Core0Error('Actual artifact mutation accepted: '+label)
 for key,value in [('maximum_captures',5),('maximum_targets',9),('slots',32),('cookie','0'),
                   ('initializer_policy','ignore static refcounts')]:
  changed=copy.deepcopy(u);changed['managed_closure'][key]=value
  reject('layout_'+key,lambda changed=changed:managed_closure.contract(changed))
 for key,value in [('owner','Lemma.Mathematics.ManagedClosureSubmission.product'),('captures',2),
                   ('genuine_ir',u['managed_closure']['adapters'][0]['genuine_ir'].replace('unbox x_1','unbox x_2',1))]:
  changed=copy.deepcopy(u);changed['managed_closure']['adapters'][0][key]=value
  reject('derived_adapter_'+key,lambda changed=changed:managed_closure.contract(changed))
 for key in ('implementation','lowering','runtime','resources'):
  changed=copy.deepcopy(u);changed[identity.FIELD][key]['id']+=1
  reject('authority_'+key,lambda changed=changed:identity.contract(changed))
 for profile in range(1,7):
  changed=copy.deepcopy(u);changed['contract_version']='core0-user-v0.'+str(profile)
  reject('legacy_profile'+str(profile),lambda changed=changed:managed_closure.contract(changed))
 names={identity.canonical(r['source']):r['symbol'] for r in u['functions']}
 for optimized,ir in [(False,pre),(True,post)]:
  for source in ['Lemma.User.Runtime.ManagedClosure.create','Lemma.User.Runtime.ManagedClosure.release',
                 'Lemma.User.Runtime.ManagedClosure.finish','Lemma.User.Runtime.Arena.allocate',
                 'Lemma.Services.Arithmetic.ServerV7.reclaimed']:
   body=_ir_definition_body(ir,names[source]);require(body is not None,'Mutation owner missing')
   changed=ir.replace(body,body+'\n  %unreviewed_semantic_change = add i64 31, 1',1)
   reject(('post_' if optimized else 'pre_')+source,
    lambda changed=changed,optimized=optimized:identity.validate(changed,u,optimized=optimized))
  reject(('post_' if optimized else 'pre_')+'foreign_runtime',
   lambda ir=ir,optimized=optimized:identity.validate(ir.replace('@lemma_exec_syscall','@lean_apply_1'),u,optimized=optimized))
 for name,profile in [('notebook1','core0-user-v0.1'),('notebook2','core0-user-v0.2')]:
  d=root/name/'users/notebook';unit=json.loads((d/'unit.json').read_text());ir=(d/'program.opt.ll').read_text()
  require(unit['contract_version']==profile and managed_closure.contract(unit) is None,'Legacy Notebook gained closure execution')
  sources={identity.canonical(r['source']):r['symbol'] for r in unit['functions']};accepted=[]
  for source in identity.NOTEBOOK_JUMPS:
   symbol=sources[source];require(identity.notebook_jump_spec(ir,unit,source,symbol) is not None,'Exact common current scalar selector missing')
   accepted.append(source)
   body=_ir_definition_body(ir,symbol);changed=ir.replace(body,body+'\n  %unreviewed_case_or_default = add i64 7, 1',1)
   require(identity.notebook_jump_spec(changed,unit,source,symbol) is None,'Changed current common switch body obtained new authority')
   rejects.append({'name':name+'_'+source,'actual_error':'No closed current switch admission; full auditor must reject unknown body'})
  reports[name]={'profile':profile,'closed_scalar_owners':accepted,
   'scope':'Common bounded dispatch only; this profile still rejects ordinary Closure execution'}
 artifacts={str(p.relative_to(root)):sha256(p) for p in root.rglob('*') if p.is_file() and p.suffix in ('.json','.ll','.o','.txt','.lean')}
 return {'status':'PASS','schema':'lemma-closure-math-component/1','scope':__doc__,
  'artifacts':artifacts,'baseline':reports,'rejected_actual_mutations':rejects}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 require(not a.output.exists(),'Retained component report exists');r=check(a.export_dir);write_json(a.output,r)
 print('CLOSURE_MATH_COMPONENT_AUDIT:PASS',len(r['rejected_actual_mutations']),'actual mutations/current scalar owner negatives')
if __name__=='__main__':main()
