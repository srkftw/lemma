"""Independent host oracle mutations for the declared DTB literal75 successor.

These compact object/assembly fixtures exercise the observer; actual generated
Power/Notebook objects are audited separately. They are not target programs.
"""
import copy,unittest
from test_backend_jump_tables import fixture
from audit_kernel import validate_backend_jump_tables
from core0_common import Core0Error

def power_literal_fixture():
 data=fixture();count=74
 cases=[*range(2,19),*range(32,53),*range(64,76)]
 data['unit']={'role':'kernel','configuration':'lemmasim-silicon-power-safety-probe','functions':[{'source':'Lemma.Platform.LemmaSim.DescriptorDTB.literalWord','symbol':'fw','args':['u64','u64'],'effects':[]}]}
 data['section_text']=data['section_text'].replace('000028 00 A','000250 00 A')
 data['rodata']=b'\0'*(count*8)
 for field,companion in [('relocation_text',False),('companion_relocations',True)]:
  data[field]=data[field].split("Relocation section '.rela.rodata'",1)[0]+"Relocation section '.rela.rodata' at offset 0:\n"
  for index in range(count):
   data[field]+=f'{index*8:08x} 0000000400000002 R_RISCV_64 00000024 '+('.LBB0_1' if companion else '.L0')+' + 0\n'
 data['assembly']=data['assembly'].split('.LJTI0_0:\n',1)[0].replace('addi a1, a1, -1','addi a1, a1, -2').replace('li a2, 4','li a2, 73').replace('a1','a0')
 data['assembly']+='.LJTI0_0:\n'+(' .quad .LBB0_1\n'*count)
 data['optimized_ir']='define i64 @fw(i64 %arg0, i64 %arg1) {\nentry:\n switch i64 %arg0, label %default [\n'+''.join(' i64 '+str(v)+', label %good\n' for v in cases)+']\ndefault:\n ret i64 0\ngood:\n ret i64 1\n}\n'
 return data

class PowerSafetyJump(unittest.TestCase):
 def test_exact_literal75_successor(self):
  report=validate_backend_jump_tables(**power_literal_fixture())
  self.assertEqual(report['jump_table_bytes'],592)
  self.assertEqual(report['jump_tables'][0]['guard']['bound'],74)
  self.assertEqual(report['jump_tables'][0]['guard']['minimum'],2)
 def test_domain_count_and_unsigned_bound_reject(self):
  data=power_literal_fixture()
  for field,old,new in [('optimized_ir','i64 75, label','i64 76, label'),('assembly','li a2, 73','li a2, 74'),('assembly','bltu a2','blt a2'),('assembly','addi a0, a0, -2','addi a0, a0, -1')]:
   bad=copy.deepcopy(data);bad[field]=bad[field].replace(old,new)
   self.assertNotEqual(bad[field],data[field])
   with self.subTest(field=field,new=new),self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
  bad=copy.deepcopy(data);bad['assembly']=bad['assembly'].replace(' .quad .LBB0_1\n','',1)
  with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
 def test_source_signature_effect_and_role_reject(self):
  data=power_literal_fixture()
  for field,new in [('source','Other.literalWord'),('args',['u64']),('effects',['mmio-read'])]:
   bad=copy.deepcopy(data);bad['unit']['functions'][0][field]=new
   with self.subTest(field=field),self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
  for role in ('firmware','user'):
   bad=copy.deepcopy(data);bad['unit']['role']=role
   with self.assertRaises(Core0Error):validate_backend_jump_tables(**bad)
