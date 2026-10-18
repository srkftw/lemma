"""Actual new four-role host archive capacity; historical bounds remain unchanged."""
from pathlib import Path
import sys,tempfile,hashlib,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest_bundle as m
class Capacity(unittest.TestCase):
 def test_actual2049file_catalog_is_new_schema_only(self):
  with tempfile.TemporaryDirectory() as name:
   r=Path(name);files={};h=hashlib.sha256(b'x').hexdigest()
   for i in range(2049):
    key='artifact-'+str(i);(r/key).write_bytes(b'x');files[key]=dict(sha256=h,bytes=1,executable=False)
   (r/'bundle.json').write_text('{}')
   m.inventory(r,dict(schema='lemmasim-native-multimodal-fast/1',files=files))
   with self.assertRaisesRegex(ValueError,'Invalid bundle file inventory'):m.inventory(r,dict(schema=m.SCHEMA,files=files))
 def test_new4097file_catalog_rejects_before_file_access(self):
  with tempfile.TemporaryDirectory() as name:
   with self.assertRaisesRegex(ValueError,'Invalid bundle file inventory'):m.inventory(Path(name),dict(schema='lemmasim-native-multimodal-fast/1',files={str(i):{} for i in range(4097)}))
 def test_new256MiB_ceiling_rejects_without_sparse_or_real_payload(self):
  with tempfile.TemporaryDirectory() as name:
   with self.assertRaisesRegex(ValueError,'exceeds byte bound'):m.inventory(Path(name),dict(schema='lemmasim-native-multimodal-fast/1',files={'oversized':dict(sha256='0'*64,bytes=256*1024*1024+1,executable=False)}))
if __name__=='__main__':unittest.main(verbosity=2)
