#!/usr/bin/env python3
"""Focused actual-artifact String/implementation-authority rejection checks."""
import argparse,copy,re,sys
from pathlib import Path
from core0_common import Core0Error,load_json,sha256,write_json
import managed_string as payload
import arithmetic_string_identity as identity

def check(directory,output):
 unit=load_json(directory/'unit.json');pre=(directory/'program.ll').read_text();post=(directory/'program.opt.ll').read_text()
 baseline={stage:{'source':payload.validate(ir,unit,optimized=optimized),'implementation':identity.validate(ir,unit,optimized=optimized)} for stage,ir,optimized in [('pre',pre,False),('post',post,True)]}
 if not all(all(r.values()) for r in baseline.values()):raise Core0Error('Selected exact String authority absent')
 rejected=[]
 def reject(name,fn):
  try:fn()
  except Core0Error as e:rejected.append({'name':name,'error':str(e)});return
  raise Core0Error('Actual artifact mutation accepted: '+name)
 def meta(name,change,observer=identity.contract):
  u=copy.deepcopy(unit);change(u);reject(name,lambda:observer(u))
 for key in ('implementation','lowering','runtime','resources'):
  meta('wrong_'+key,lambda u,key=key:u[identity.FIELD][key].__setitem__('id',u[identity.FIELD][key]['id']+1))
 for label,key,value in [('old_profile','contract_version','core0-user-v0.5'),('old_configuration','configuration','lemmasim-silicon-array-bulk-notebook'),('wrong_role','role','kernel'),('wrong_image','image_key','notebook')]:
  meta(label,lambda u,key=key,value=value:u.__setitem__(key,value))
 for key in ('maximum_utf8_bytes','slots','string_payload_bytes','option_payload_bytes'):
  meta('wrong_'+key,lambda u,key=key:u[payload.FIELD].__setitem__(key,u[payload.FIELD][key]+1),payload.contract)
 rows=unit[payload.FIELD]['functions'];parse=next(i for i,r in enumerate(rows) if r['source']==payload.PREFIX+'parse')
 meta('genuine_utf8_validation_removed',lambda u:u[payload.FIELD]['functions'][parse].__setitem__('genuine_ir',u[payload.FIELD]['functions'][parse]['genuine_ir'].replace('ByteArray.validateUTF8','ByteArray.size')),payload.contract)
 decode=next(i for i,r in enumerate(rows) if r['source']==payload.PREFIX+'decode')
 meta('genuine_consume_changed',lambda u:u[payload.FIELD]['functions'][decode].__setitem__('genuine_ir',u[payload.FIELD]['functions'][decode]['genuine_ir'].replace('String.toByteArray','String.utf8ByteSize')),payload.contract)
 root=next(i for i,r in enumerate(unit['functions']) if r['source']==payload.GENERATED+payload.ENTRY)
 meta('generated_effects_removed',lambda u:u['functions'][root].__setitem__('effects',[]),lambda u:identity.validate(pre,u,optimized=False))
 meta('generated_width_changed',lambda u:u['functions'][root].__setitem__('args',['u32','u32']),payload.contract)
 names={r['source']:r['symbol'] for r in unit['functions']}
 from audit_kernel import _ir_definition_body
 for stage,ir,optimized in [('pre',pre,False),('post',post,True)]:
  for source,label in [('Lemma.User.Runtime.ManagedString.utf8Step','UTF8_scalar_validation'),('Lemma.User.Runtime.ManagedString.fromByteArray','constructor_ownership'),('Lemma.User.Runtime.ManagedString.releaseOption','graph_lifetime'),('Lemma.User.Runtime.ManagedString.toByteArray','conversion_ownership'),('Lemma.User.Runtime.Arena.release','real_allocator_reclamation')]:
   symbol=names[source];body=_ir_definition_body(ir,symbol)
   if not body:raise Core0Error('Actual body mutation anchor absent: '+source)
   changed=ir.replace(body,body+'\n  %unreviewed = add i64 0, 1',1)
   reject(stage+'_'+label,lambda changed=changed,optimized=optimized:identity.validate(changed,unit,optimized=optimized))
  reject(stage+'_host_runtime',lambda ir=ir,optimized=optimized:identity.validate(ir.replace('@lemma_exec_syscall','@lean_string_to_utf8'),unit,optimized=optimized))
  reject(stage+'_global_state',lambda ir=ir,optimized=optimized:identity.validate('@unreviewed = private global i64 0\n'+ir,unit,optimized=optimized))
 # Changing a real pure width operation must also be detected independently of
 # target runtime helpers, so a full UInt64 return cannot quietly truncate.
 symbol=names[payload.GENERATED+payload.PREFIX+'decoded'];body=_ir_definition_body(pre,symbol)
 changed,count=re.subn(r'\bshl i64\b','lshr i64',body,count=1)
 if count!=1:raise Core0Error('Actual full-width decode anchor absent')
 reject('decoded_full_width_changed',lambda:identity.validate(pre.replace(body,changed,1),unit,optimized=False))
 result={'status':'PASS','scope':'Actual genuine selected User6 source + complete pre/post implementation/resource/ownership authority; linked isolated execution separate','inputs':{n:sha256(directory/n) for n in ('unit.json','program.ll','program.opt.ll','program.o')},'baseline':baseline,'rejected_actual_mutations':rejected};write_json(output,result);print('MANAGED_STRING_SELECTED_AUDIT:PASS',len(rejected),'actual artifact mutations')
def main():
 p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise Core0Error('Output already exists')
 check(a.directory,a.output)
if __name__=='__main__':
 try:main()
 except (Core0Error,OSError,ValueError) as e:print('MANAGED_STRING_SELECTED_AUDIT:FAIL',e,file=sys.stderr);raise SystemExit(1)
