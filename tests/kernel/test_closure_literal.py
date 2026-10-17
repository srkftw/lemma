"""Doc8 object bytes/extent/role checks; genuine IR ownership qualifies separately."""
import copy,struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import validate_backend_jump_tables
from core0_common import Core0Error

def fixture():
 values=[1856,2496,2496,2496,2496,2496,2496]
 return dict(section_text=' [7] .rodata PROGBITS 00000000 000040 000038 00 A 0 0 8\n',
  symbol_text=' 1: 00000000 56 OBJECT LOCAL DEFAULT 7 .literal\n',relocation_text='',rodata=struct.pack('<7Q',*values),
  unit={'role':'user','image_key':'notebook','contract_version':'core0-user-v0.2',
   'configuration':'lemmasim-silicon-closure-bulk-notebook','functions':[]},
  optimized_ir='',optimization='O2',readonly_tables=[{'section':'.rodata','source':'Lemma.Applications.Notebook.openCourse',
   'values':values,'offset':0,'bytes':56,'literal_schema':'document-v8-length-v1'}])

class ClosureLiteral(unittest.TestCase):
 def test_exact_source_profile_shape_and_complete_bytes(self):
  data=fixture();self.assertEqual(validate_backend_jump_tables(**data)['literal_bytes'],56)
  for field,value in [('configuration','service-normal'),('image_key','arithmetic'),
                      ('contract_version','core0-user-v0.7'),('role','kernel')]:
   changed=copy.deepcopy(data);changed['unit'][field]=value
   with self.assertRaises(Core0Error):validate_backend_jump_tables(**changed)
 def test_wrong_word_shape_extent_permissions_and_trailing_bytes_reject(self):
  data=fixture();negatives=[]
  changed=copy.deepcopy(data);changed['readonly_tables'][0]['values'][1]=2497;negatives.append(changed)
  changed=copy.deepcopy(data);changed['readonly_tables'][0]['bytes']=48;negatives.append(changed)
  changed=copy.deepcopy(data);changed['rodata']=b'\x00'+changed['rodata'][1:];negatives.append(changed)
  changed=copy.deepcopy(data);changed['section_text']=changed['section_text'].replace('00 A ','00 AW ');negatives.append(changed)
  changed=copy.deepcopy(data);changed['section_text']=changed['section_text'].replace('000038','000040');changed['rodata']+=b'\x00'*8;negatives.append(changed)
  for changed in negatives:
   with self.assertRaises(Core0Error):validate_backend_jump_tables(**changed)
if __name__=='__main__':unittest.main()
