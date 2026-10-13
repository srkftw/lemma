"""Opt-in authority, negative profile mutation and historical-binding checks."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_profile as binding

class BLEBinding(unittest.TestCase):
 def test_opt_in_descriptor_and_discovery(self):
  p=binding.profile('lemma-silicon-dev/0.5.0')
  import struct
  words=struct.unpack('<32Q',binding.descriptor(p,4096))
  self.assertEqual(words[1],6);self.assertEqual(words[21],7)
  self.assertEqual(words[3],sum(words[:3]+words[4:])&((1<<64)-1))
  text=binding.dts(p)
  self.assertIn('riscv,ndev = <15>',text)
  self.assertIn('reg = <0x0 0x10010600 0x0 0x400>',text)
  self.assertIn('lemma,manual-context = <1>',text)
  self.assertEqual(binding.configuration_profile('lemmasim-silicon-ble-link-probe'),p['profile'])
 def test_fixed_authority_mutations_reject(self):
  original=binding.profile('lemma-silicon-dev/0.5.0')
  for key,value in [('plic_sources',14),('descriptor_features',3),('ble_enabled',0),('power_safety',0)]:
   p=copy.deepcopy(original);p[key]=value
   with patch.object(Path,'read_text',return_value=json.dumps(p)):
    with self.assertRaises(ValueError):binding.profile('lemma-silicon-dev/0.5.0')
  for key,value in [('base',0x10010500),('span',0x1000),('irq',14),('payload_max',28),('clocks_per_bit',99)]:
   p=copy.deepcopy(original);p['devices']['ble'][key]=value
   with patch.object(Path,'read_text',return_value=json.dumps(p)):
    with self.assertRaises(ValueError):binding.profile('lemma-silicon-dev/0.5.0')
 def test_historical_lean_and_discovery_unchanged(self):
  for version,name,abi in [('0.1.0','Binding',2),('0.2.0','BindingFull',3),('0.3.0','BindingPower',4),('0.4.0','BindingSafety',5)]:
   p=binding.profile('lemma-silicon-dev/'+version)
   self.assertEqual(binding.lean_text(p),(ROOT/f'Lemma/Platform/Silicon/{name}.lean').read_text())
   self.assertNotIn('lemma-ble@',binding.dts(p));self.assertEqual(p['descriptor']['abi'],abi)
   self.assertEqual(binding.constants(p)['ble_enabled'],0)
 def test_selected_container_authority_is_not_global(self):
  import struct,tempfile
  import lemmasim_session as session
  with tempfile.TemporaryDirectory() as temporary:
   runtime=object.__new__(session.RTL);runtime.checkpoint_identity='a'*64
   path=Path(temporary)/'state'
   for profile,allowed in [('lemma-silicon-dev/0.3.0',(1,2)),('lemma-silicon-dev/0.4.0',(3,)),('lemma-silicon-dev/0.5.0',(5,))]:
    runtime.identity={'profile':profile}
    for version in range(6):
     path.write_bytes(b'LMSSRTL1'+struct.pack('<Q',version)+b'a'*64+struct.pack('<4Q',16,1,0,0)+struct.pack('<2Q',0,7)+b'\0')
     if version in allowed:runtime.preflight_checkpoint(path,7)
     else:
      with self.assertRaises(ValueError):runtime.preflight_checkpoint(path,7)
 def test_opaque_bounded_raw_cli_events(self):
  from lemmasim_session import external_command
  self.assertEqual(external_command({'action':'inject','kind':'ble-rx','level':1},30)[0],'inject 30 ble-rx 1')
  with self.assertRaises(ValueError):external_command({'action':'inject','kind':'ble-rx','level':2},30)
if __name__=='__main__':unittest.main()
