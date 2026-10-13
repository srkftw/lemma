"""Profile/transport boundaries; real controller/guest evidence is separate."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_profile as binding
import silicon_guest as guest
class PaperExecutedProfile(unittest.TestCase):
 def test_exact_additive_profile_and_raw_selector(self):
  p=binding.profile('lemma-silicon-dev/0.10.0');c=binding.constants(p)
  self.assertEqual((p['descriptor']['abi'],p['descriptor_features'],c['paper_version'],c['paper_stage_offset']),(11,31,3,3584))
  self.assertEqual(p['paper_executed_registers'],dict(sequence=192,x=200,y=208,width=216,height=224,mode=232))
  self.assertEqual((p['frame_pool_bytes'],p['ram_bytes'],c['pen_fifo']),(33554432,134217728,256))
  self.assertIn('lemma,executed-refresh = <192 200 208 216 224 232>;',binding.dts(p))
  self.assertIn('"lemma,paper-v3"',binding.dts(p))
  self.assertEqual(binding.lean_text(p),(binding.ROOT/'Lemma/Platform/Silicon/BindingProductExecuted.lean').read_text())
  self.assertEqual(guest.configurations(p['profile']),{'product-executed-bulk-notebook':'lemmasim-silicon-product-executed-bulk-notebook'})
  self.assertEqual(guest.prepared_path(p['profile']).name,'rtl-prepared-0.10.0.json')
 def test_preexisting_paper_versions_remain_selectable(self):
  for minor,name in ((8,'BindingUSBNext'),(9,'BindingProductNext')):
   p=binding.profile('lemma-silicon-dev/0.'+str(minor)+'.0')
   self.assertEqual((p['paper_version'],p['paper_stage_offset']),(2,3584))
   self.assertNotIn('lemma,executed-refresh',binding.dts(p))
   self.assertEqual(binding.lean_text(p),(binding.ROOT/'Lemma/Platform/Silicon'/ (name+'.lean')).read_text())
 def test_mixed_version_or_executed_geometry_is_rejected(self):
  original=binding.profile('lemma-silicon-dev/0.10.0')
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'profile.json'
   changes=[('paper_version',2),('paper_stage_offset',2048),('descriptor_features',15),('paper_executed_registers',dict(sequence=192,x=200,y=208,width=216,height=224,mode=240)),('paper_executed_registers',dict(sequence=112,x=120,y=128,width=136,height=144,mode=152))]
   for key,value in changes:
    data=copy.deepcopy(original);data[key]=value;path.write_text(json.dumps(data))
    with self.subTest(key=key,value=value),patch.object(binding,'PRODUCT_EXECUTED_PROFILE',path):
     with self.assertRaises(ValueError):binding.profile('lemma-silicon-dev/0.10.0')
if __name__=='__main__':unittest.main()
