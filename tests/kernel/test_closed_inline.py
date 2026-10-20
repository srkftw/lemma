import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import closed_inline as ci
from core0_common import Core0Error

class ClosedInlineTests(unittest.TestCase):
 def setUp(self):
  self.unit={'configuration':'lemmasim-silicon-power-notebook','role':'kernel','contract_version':'core0-kernel-v0.4',
   'functions':[{'source':'Lemma.Constant','symbol':'lemma_kernel_literal','args':[],'effects':[]},
    {'source':'Lemma.Kernel.Memory.Access.read64','symbol':'lemma_kernel_access','args':['u64'],'effects':['checked-access','physical-read']}],
   'used_execution_ops':[{'stable_id':'execution.physical-read64','primitive_symbol':None,'returnkind':'word'}],
   'checked_inline':{'literal_contract':ci.LITERAL,'wrapper_contract':ci.WRAPPER,
    'literals':[{'source':'Lemma.Constant','symbol':'lemma_kernel_literal','type':'u64','value':23}],
    'wrappers':[{'source':'Lemma.Kernel.Memory.Access.read64','symbol':'lemma_kernel_access','operation':'execution.physical-read64'}]}}
  self.ir='define i64 @lemma_kernel_literal() nounwind alwaysinline {\nentry:\n  ret i64 23\n}\n'+(Path(__file__).parent/'fixtures/closed-inline-physical-read64.ll').read_text()
 def test_complete_existing_guard_and_literal_are_qualified(self):
  self.assertEqual(ci.validate(self.ir,self.unit,optimized=False)['physical_wrappers'],1)
 def test_catalog_absent_incomplete_duplicated_or_forged_rejects(self):
  cases=[]
  u=copy.deepcopy(self.unit);del u['checked_inline'];cases.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['literals']=[];cases.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['wrappers']=[];cases.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['literals']*=2;cases.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['literals'][0]['value']=24;cases.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['wrappers'][0]['operation']='execution.virtual-read64';cases.append(u)
  u=copy.deepcopy(self.unit);u['functions'][1]['effects']=['checked-access'];cases.append(u)
  u=copy.deepcopy(self.unit);u['configuration']='normal';cases.append(u)
  u=copy.deepcopy(self.unit);u['used_execution_ops'][0]['returnkind']='checked';cases.append(u)
  for u in cases:
   with self.subTest(unit=u),self.assertRaises(Core0Error):ci.validate(self.ir,u,optimized=False)
 def test_range_width_alignment_return_and_error_mutations_reject(self):
  changes=[('and i64 %arg0, 7','and i64 %arg0, 3'),('2149580800','2149580799'),
   ('2150629368','2150629376'),('load volatile i64','load i64'),('align 8','align 4'),
   ('[ 8, %execution.mem.0.misaligned.2 ]','[ 7, %execution.mem.0.misaligned.2 ]'),
   ('i64 %execution.mem.0.value.27, 1','i64 0, 1')]
  for old,new in changes:
   self.assertIn(old,self.ir)
   with self.subTest(change=old),self.assertRaises(Core0Error):ci.validate(self.ir.replace(old,new),self.unit,optimized=False)
 def test_extra_inline_policy_and_changed_literal_abi_reject(self):
  for ir in [self.ir+'\ndefine i64 @rogue(i64 %arg0) nounwind alwaysinline {\nentry:\nret i64 %arg0\n}\n',
    self.ir.replace('@lemma_kernel_literal()','@lemma_kernel_literal(i64 %arg0)'),
    self.ir.replace('ret i64 23','ret i64 24')]:
   with self.assertRaises(Core0Error):ci.validate(ir,self.unit,optimized=False)
 def test_optimized_attribute_groups_cannot_grant_unlisted_authority(self):
  bad='define i64 @rogue(i64 %arg0) #3 {\nentry:\nret i64 %arg0\n}\nattributes #3 = { nounwind alwaysinline }\n'
  with self.assertRaises(Core0Error):ci.validate(bad,self.unit,optimized=True)
 def test_closed_school24_metadata_keeps_exact_existing_physical_guards(self):
  from school_deployment import configurations_for,software_deployment_for
  for configuration in configurations_for(24)[:2]:
   unit=copy.deepcopy(self.unit);unit.update(configuration=configuration,contract_version='core0-kernel-v0.9',
    software_deployment=software_deployment_for(configuration))
   unit['checked_inline'].update(user_wrapper_contract=ci.USER_WRAPPER,user_wrappers=[])
   self.assertEqual(ci.validate(self.ir,unit,optimized=False)['physical_wrappers'],1)
   for field,value in [('software_deployment',software_deployment_for('lemmasim-silicon-school-notebook')),
                       ('contract_version','core0-kernel-v0.10'),('role','user'),
                       ('configuration',configuration+'-unknown')]:
    changed=copy.deepcopy(unit);changed[field]=value
    with self.subTest(configuration=configuration,field=field),self.assertRaises(Core0Error):
     ci.validate(self.ir,changed,optimized=False)

if __name__=='__main__':unittest.main()
