import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import closed_inline as ci
from core0_common import Core0Error

class UserWordInlineTests(unittest.TestCase):
 def setUp(self):
  base=Path(__file__).parent/'fixtures'
  data=json.loads((base/'closed-inline-user-words.json').read_text())
  self.ir=(base/'closed-inline-user-words.ll').read_text()
  self.unit={'configuration':'lemmasim-silicon-managed-notebook','role':'user','image_key':'notebook',
   'contract_version':'core0-user-v0.2','functions':data['functions'],'used_execution_ops':data['used_execution_ops'],
   'checked_inline':{'literal_contract':ci.LITERAL,'wrapper_contract':ci.WRAPPER,'literals':[],'wrappers':[],
    'user_wrapper_contract':ci.USER_WRAPPER,'user_wrappers':data['wrappers']}}
 def test_exact_checked_virtual_words_are_qualified(self):
  self.assertEqual(ci.validate(self.ir,self.unit,optimized=False)['user_word_wrappers'],2)
 def test_selected_profile_role_and_image_authority(self):
  for field,value in [('configuration','lemmasim-silicon-power-notebook'),('role','kernel'),
    ('image_key','store'),('contract_version','core0-user-v0.1')]:
   u=copy.deepcopy(self.unit);u[field]=value
   with self.subTest(field=field),self.assertRaises(Core0Error):ci.validate(self.ir,u,optimized=False)
 def test_catalog_omission_duplicate_contract_and_operation(self):
  mutations=[]
  u=copy.deepcopy(self.unit);u['checked_inline']['user_wrappers']=[];mutations.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['user_wrappers']*=2;mutations.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['user_wrapper_contract']=ci.WRAPPER;mutations.append(u)
  u=copy.deepcopy(self.unit);u['checked_inline']['user_wrappers'][0]['operation']='execution.virtual-read8';mutations.append(u)
  u=copy.deepcopy(self.unit);u['used_execution_ops']=[];mutations.append(u)
  u=copy.deepcopy(self.unit);u['functions'][0]['effects']=['checked-access','physical-read'];mutations.append(u)
  u=copy.deepcopy(self.unit);u['functions'][0]['args']=['u32'];mutations.append(u)
  for u in mutations:
   with self.subTest(unit=u),self.assertRaises(Core0Error):ci.validate(self.ir,u,optimized=False)
 def test_complete_range_alignment_error_width_and_value_guards(self):
  for old,new in [('and i64 %arg0, 7','and i64 %arg0, 3'),('icmp uge i64 %arg0, 65536','icmp sge i64 %arg0, 65536'),
    ('1073741816','1073741824'),('load volatile i64','load i64'),('store volatile i64','store i64'),
    ('align 8','align 4'),('[ 8, %execution.mem.0.misaligned.2 ]','[ 7, %execution.mem.0.misaligned.2 ]'),
    ('store volatile i64 %arg1','store volatile i64 0')]:
   self.assertIn(old,self.ir)
   with self.subTest(change=old),self.assertRaises(Core0Error):ci.validate(self.ir.replace(old,new),self.unit,optimized=False)
 def test_no_extra_inline_action_or_byte_authority(self):
  bad=self.ir+'\ndefine { i64, i64 } @rogue(i64 %arg0) nounwind alwaysinline {\nentry:\nret { i64, i64 } zeroinitializer\n}\n'
  with self.assertRaises(Core0Error):ci.validate(bad,self.unit,optimized=False)
  with self.assertRaises(Core0Error):ci.validate(bad,self.unit,optimized=True)

if __name__=='__main__':unittest.main()
