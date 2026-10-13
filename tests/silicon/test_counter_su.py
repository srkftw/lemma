"""Host oracle guards; these fixtures do not establish target execution."""
import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from core0_common import Core0Error
import check_guest_counter_su as c

class CounterSuOracle(unittest.TestCase):
 def test_enable_truth_table(self):
  # Literal truth table (M bit, S bit, expected U, expected S), independently
  # repeated for CY, TM, IR. Unselected enable bits must not grant access.
  for m,s,u,supervisor in [(0,0,False,False),(0,1,False,False),(1,0,False,True),(1,1,True,True)]:
   for op in range(3):
    self.assertEqual(c.permission(0,op,m<<op,s<<op),u)
    self.assertEqual(c.permission(1,op,m<<op,s<<op),supervisor)
    self.assertTrue(c.permission(3,op,0,0))
  for mode in (0,1,3):
   for op in (3,4,5,6,7):self.assertFalse(c.permission(mode,op,7,7))
  self.assertFalse(c.permission(0,8,7,7));self.assertTrue(c.permission(1,8,0,0))

 def test_literal_corpus_order_counts(self):
  rows=c.literal_cases()
  self.assertEqual(rows[:6],[(0,0,0,0),(0,1,0,0),(0,2,0,0),(1,0,0,0),(1,1,0,0),(1,2,0,0)])
  self.assertEqual(rows[48],(0,0,1,0));self.assertEqual(rows[383],(1,2,7,7))
  self.assertEqual(rows[384:390],[(0,3,7,7),(0,4,7,7),(0,5,7,7),(1,3,7,7),(1,4,7,7),(1,5,7,7)])
  self.assertEqual(rows[398:],[(3,0,0,0),(3,1,0,0),(3,2,0,0),(3,3,0,0),(3,4,0,0),(3,5,0,0)])
  self.assertEqual(sum(not c.permission(*r) for r in rows),255)
  self.assertEqual(sum(r[0]!=3 for r in rows),398)

 def test_fixed_actual_instruction_words(self):
  # Literal independent encodings of every declared fixed access. The audit
  # does not accept a mnemonic-only disassembly or a substituted CSR number.
  literal=[0x30102573,0xb0002573,0xb0051073,0xb0202573,0xb0251073,0x32002573,0x32051073,0x30602573,0x30651073,
           0xc0002573,0xc0102573,0xc0202573,0x10602573,0x10651073,0xc0051073,0xc0151073,0xc0251073]
  code=bytearray();ranges={};base=0x80000000
  for (_,symbol,_,write),word in zip(c.CSR_OPERATIONS.values(),literal,strict=True):
   ranges[symbol]=(base+len(code),12)
   code+=struct.pack('<3I',*([word,0x513,0x8067] if write else [0x513,word,0x8067]))
  ranges['lemma_counter_su_lower']=(base+len(code),16)
  code+=struct.pack('<4I',0x97,0x80e7,0x73,0x6f)
  checked=c.validate_csr_bytes(code,base,ranges)
  self.assertEqual(len(checked),17)
  bad=bytearray(code);offset=ranges['lemma_exec_read_counter_time'][0]-base+4
  bad[offset:offset+4]=struct.pack('<I',0xc0202573)
  with self.assertRaises(Core0Error):c.validate_csr_bytes(bad,base,ranges)
  bad=bytearray(code);bad[-8:-4]=struct.pack('<I',0x100073)
  with self.assertRaises(Core0Error):c.validate_csr_bytes(bad,base,ranges)

 def test_missing_or_partial_guest_records_reject(self):
  for raw in (b'',bytes(32760),bytes(32768)):
   with self.assertRaises(Core0Error):c.validate_records(raw,{'lemma_counter_su_lower':(0x80001000,16)})

if __name__=='__main__':unittest.main()
