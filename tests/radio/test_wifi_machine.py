"""Host profile/selector admission negatives, separate from actual guest execution."""
import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_profile as binding
import build_kernel

class CommonProfile(unittest.TestCase):
 def test_exact_closed_profile_and_target_selector(self):
  p=binding.profile('lemma-silicon-dev/0.12.0')
  self.assertEqual((p['descriptor']['abi'],p['descriptor_features'],p['plic_sources']),(13,47,18))
  self.assertEqual((p['frame_count'],p['frame_pool_bytes'],p['ram_bytes'],p['geometry']),(8192,33554432,134217728,[1650,2200]))
  self.assertNotIn('boot_nv',p['devices'])
  self.assertEqual(binding.configuration_profile('lemmasim-silicon-wifi-common-probe'),p['profile'])
  roots=build_kernel.configuration_roots('lemmasim-silicon-wifi-common-probe')
  self.assertEqual(roots['kernel'][0][0],'Lemma.Platform.Silicon.Development.WiFiCommonProbe.boot')
  self.assertTrue(build_kernel.development_role('lemmasim-silicon-wifi-common-probe','kernel'))
  self.assertFalse(build_kernel.development_role('lemmasim-silicon-wifi-common-probe','firmware'))
  with self.assertRaises(build_kernel.Core0Error):build_kernel.validate_configuration_stage('lemmasim-silicon-wifi-common-probe','bootstrap-m')
 def test_inherited_or_new_feature_mutations_fail_closed(self):
  p=binding.profile('lemma-silicon-dev/0.12.0')
  for key,v in [('descriptor_features',31),('plic_sources',17),('wifi_enabled',0),('wifi_version',2),('clock_hz',99999999),('usb_phy_bit_hz',13000000),('boot_nv_enabled',1),('frame_quota',128)]:
   wrong=copy.deepcopy(p);wrong[key]=v
   with self.subTest(key=key),patch.object(binding.json,'loads',return_value=wrong),self.assertRaises(ValueError):binding.profile(p['profile'])
  for key,v in [('base',0x10012000),('span',0x800),('irq',17),('payload_max',17),('sample_hz',19000000)]:
   wrong=copy.deepcopy(p);wrong['devices']['wifi'][key]=v
   with self.subTest(device=key),patch.object(binding.json,'loads',return_value=wrong),self.assertRaises(ValueError):binding.profile(p['profile'])
 def test_all_eleven_historical_generated_bindings_equal(self):
  names=['Binding','BindingFull','BindingPower','BindingSafety','BindingBLE','BindingUSB','BindingProduct','BindingUSBNext','BindingProductNext','BindingProductExecuted','BindingUSBWire']
  for number,name in enumerate(names,1):
   p=binding.profile(f'lemma-silicon-dev/0.{number}.0')
   self.assertEqual(binding.lean_text(p),(binding.ROOT/f'Lemma/Platform/Silicon/{name}.lean').read_text())
   self.assertEqual(binding.constants(p)['wifi_enabled'],0)
   wrong=copy.deepcopy(p);wrong['wifi_enabled']=1
   with patch.object(binding.json,'loads',return_value=wrong),self.assertRaises(ValueError):binding.profile(p['profile'])
 def test_generated_dt_binding_contains_new_exact_properties(self):
  p=binding.profile('lemma-silicon-dev/0.12.0');source=binding.dts(p,devices=True)
  for text in ('lemma-wifi-common@10013000','lemma,wifi-common-ofdm-data-v1','lemma,sample-hz = <20000000>','lemma,aligned-data-only = <1>','interrupts = <18>','riscv,ndev = <18>','lemma,phy-sample-hz = <48000000>'):
   self.assertIn(text,source)
  self.assertNotIn('lemma-boot-nv@',source)
if __name__=='__main__':unittest.main()
