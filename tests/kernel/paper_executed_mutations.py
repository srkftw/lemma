"""Negative observations of actual maintained Paper3 emitted artifacts.

These never enter target compilation. Every replacement requires a real
production site, and every changed artifact must fail its narrow independent
observer. They do not prove the compiler or simulate a completed kernel.
"""
import copy,re
from core0_common import Core0Error
from paper_executed import canonical,validate
from lemmasim_readonly import validate_lookup
from audit_kernel import _ir_definition_body

def body_change(ir,row,old,new):
 body=_ir_definition_body(ir,row['symbol'])
 if body is None or old not in body:raise Core0Error('Paper3 mutation site absent: '+row['source']+' '+old)
 start=ir.index(body);return ir[:start]+body.replace(old,new,1)+ir[start+len(body):]

def mutations(unit,pre,post):
 rows={canonical(row['source']):row for row in unit['functions']};rejected=[]
 def require_reject(label,ir=pre,u=unit,optimized=False,readonly=False):
  try:(validate_lookup(ir,u) if readonly else validate(ir,u,optimized=optimized))
  except Core0Error:rejected.append(label);return
  raise Core0Error('Paper3 observer accepted actual artifact mutant: '+label)
 for label,key,value in [('role','role','user'),('configuration','configuration','lemmasim-silicon-product-next-bulk-notebook'),('profile','contract_version','core0-kernel-v0.6')]:
  u=copy.deepcopy(unit);u[key]=value;require_reject(label,u=u)
 for label,key,value in [('signature','args',['u32']),('effect','effects',[])]:
  u=copy.deepcopy(unit);next(r for r in u['functions'] if canonical(r['source']).endswith('BootHealthExecuted.fullRefresh'))[key]=value;require_reject(label,u=u)
 u=copy.deepcopy(unit);u['functions']=[r for r in u['functions'] if not canonical(r['source']).endswith('BootHealthExecuted.liveImage')];require_reject('missing-owned-service',u=u)
 u=copy.deepcopy(unit);u['functions'].append(copy.deepcopy(rows['Lemma.Platform.LemmaSim.BootHealthExecuted.step']));require_reject('duplicate-policy-row',u=u)
 source='Lemma.Platform.LemmaSim.BootHealthExecuted.fullRefresh'
 for label,old,new in [('executed-offset','i64 192','i64 120'),('mode-offset','i64 232','i64 152'),('quality-mode','i64 2','i64 1'),('full-width','1650','1649'),('full-height','2200','2199'),('sequence-equality','icmp eq i64','icmp ne i64')]:
  require_reject(label,body_change(pre,rows[source],old,new))
 for label,source,old,new in [('trial-only','Lemma.Platform.LemmaSim.BootHealthExecuted.step','icmp eq i64 %action.call.value3, 1','icmp eq i64 %action.call.value3, 0'),('owner-liveness','Lemma.Platform.LemmaSim.BootHealthExecuted.liveImage','icmp eq i64','icmp ne i64'),('attempt-before-IO','Lemma.Platform.LemmaSim.BootHealthExecuted.confirm','i64 2','i64 0'),('durable-barrier','Lemma.Boot.ProductExecuted.publishMetadata','i64 3','i64 1'),('discover-vector','Lemma.Platform.LemmaSim.DescriptorDTB.executedProperty','icmp eq i64 %arg1, 24','icmp eq i64 %arg1, 16')]:
  require_reject(label,body_change(pre,rows[source],old,new))
 # Add an unauthorized direct confirmation call to an unpinned pure kernel
 # predicate; exact caller identity must reject it independently of policy pins.
 row=rows['Lemma.Platform.LemmaSim.DeviceABI.paperSequenceOffset'];body=_ir_definition_body(pre,row['symbol'])
 call='  %unauthorized = call { i64, i64 } @'+rows['Lemma.Platform.LemmaSim.BootHealthExecuted.confirm']['symbol']+'(i64 1)\n'
 require_reject('foreign-confirm-caller',pre.replace(body,body.replace('entry:\n','entry:\n'+call,1),1))
 literal=rows['Lemma.Platform.LemmaSim.DescriptorDTB.literalWordExecuted'];body=_ir_definition_body(post,literal['symbol'])
 for label,old,new in [('post-code','i64 64','i64 63'),('post-index','i64 %arg1','i64 %arg0'),('post-bound','icmp ult i64 %arg1, 3','icmp ule i64 %arg1, 3')]:
  require_reject(label,body_change(post,literal,old,new),optimized=True)
  require_reject('readonly-'+label,body_change(post,literal,old,new),optimized=True,readonly=True)
 # Content/size changes keep the original real pool owner and code path.
 table='switch.table.'+literal['symbol'];line=next(line for line in post.splitlines() if line.startswith('@'+table+' = '))
 values=re.findall(r'i64 (-?\d+)',line)
 if len(values)!=3:raise Core0Error('Paper3 exact UTF8 pool has unexpected rows')
 for i,v in enumerate(values):
  changed=post.replace(line,line.replace('i64 '+v,'i64 '+str(int(v)^1),1),1)
  require_reject('readonly-content-'+str(i),changed,optimized=True,readonly=True)
 return rejected
