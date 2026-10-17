from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from lemmasim_readonly import validate_lookup
class PowerSafetyLiteral(unittest.TestCase):
 def setUp(self):
  self.ir=(ROOT/'tests/kernel/fixtures/power-safety-length-generated.ll').read_text()
  self.unit={'configuration':'lemmasim-silicon-power-safety-probe','role':'kernel','functions':[{'symbol':'lemma_kernel_core0_scalar_31','source':'Lemma.Platform.LemmaSim.DescriptorDTB.literalLength','args':['u64'],'effects':[]}]}
 def test_genuine_length_table_and_unsigned_bound(self):
  rows=validate_lookup(self.ir,self.unit)[1]
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['index_bound'],75)
  self.assertEqual(rows[0]['values'][-1],15) # ASCII lemma,power-v2 plus NUL
 def test_missing_terminator_length_rejected(self):
  changed=self.ir.replace('i64 15], align 8','i64 14], align 8')
  self.assertNotEqual(changed,self.ir)
  with self.assertRaises(Core0Error):validate_lookup(changed,self.unit)
 def test_one_past_bound_rejected(self):
  changed=self.ir.replace(', 75\n',', 76\n')
  self.assertNotEqual(changed,self.ir)
  with self.assertRaises(Core0Error):validate_lookup(changed,self.unit)
