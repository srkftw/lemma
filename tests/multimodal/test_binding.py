# SPDX-License-Identifier: Apache-2.0
"""Binding metadata/negative closure tests; no execution or physical claim."""
import sys,struct,unittest,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as b
class Binding(unittest.TestCase):
 def test_separate_fixed_descriptor(self):
  p=b.profile('lemma-silicon-dev/0.14.0');old=b.profile('lemma-silicon-dev/0.3.0')
  self.assertEqual(b.descriptor(p,1234),b.descriptor(old,1234))
  words=struct.unpack('<32Q',b.descriptor(p,1234));self.assertEqual((words[1],words[2]),(4,256));self.assertEqual(words[3],sum(words[:3]+words[4:])&((1<<64)-1))
 def test_exact_extension_and_no_false_union(self):
  p=b.profile('lemma-silicon-dev/0.14.0');self.assertEqual(p['canonical'],'lemma-one-multimodal/0.2.0')
  self.assertEqual(p['devices']['multimodal'],dict(base=0x10014000,span=8192,irq=19,streams=9,fifo_records=16,record_bytes=64,clock_hz=100000000))
  for name in ('usb','ble','wifi','boot_nv'):self.assertNotIn(name,p['devices'])
  self.assertIn('lemma,multimodal-v1',b.dts(p));self.assertIn('lemma,extension-descriptor',b.dts(p));self.assertIn('lemma,physical-qualified = <0>',b.dts(p))
 def test_generated_lean_current_and_historical(self):
  for v in (1,2,3,4,5,6,7,8,9,10,11,12,13,14):
   p=b.profile(f'lemma-silicon-dev/0.{v}.0');self.assertEqual((ROOT/f'Lemma/Platform/Silicon/{b.binding_namespace(p)}.lean').read_text(),b.lean_text(p))
 def test_unsupported_version_fails(self):
  with self.assertRaisesRegex(ValueError,'unsupported'):b.profile('lemma-silicon-dev/0.99.0')
 def test_routed_consumer(self):
  import silicon_guest
  self.assertEqual(b.configuration_profile('lemmasim-silicon-multimodal-notebook'),'lemma-silicon-dev/0.14.0')
  self.assertEqual(silicon_guest.configurations('lemma-silicon-dev/0.14.0')['initializer'],'lemmasim-silicon-multimodal-initialize')
if __name__=='__main__':unittest.main()
