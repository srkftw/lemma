"""Host-only fail-closed admission of the pinned LLVM object report."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_ble_packet import validate_object_attributes

GOOD='''Format: elf64-littleriscv
Arch: riscv64
AddressSize: 64bit
Class: 64-bit (0x2)
Type: Relocatable (0x1)
Machine: EM_RISCV (0xF3)
Value: rv64i2p1_m2p0_zmmul1p0
'''

class ObjectAdmission(unittest.TestCase):
 def test_exact_pinned_report(self):validate_object_attributes(GOOD)
 def test_wrong_architecture_and_word_width(self):
  for before,after in [('Machine: EM_RISCV (0xF3)','Machine: EM_X86_64 (0x3E)'),
      ('Class: 64-bit (0x2)','Class: 32-bit (0x1)'),
      ('Type: Relocatable (0x1)','Type: Executable (0x2)')]:
   with self.subTest(after=after),self.assertRaises(RuntimeError):
    validate_object_attributes(GOOD.replace(before,after))
 def test_unadmitted_or_missing_isa(self):
  for after in ['rv64i2p1_m2p0_zmmul1p0_f2p2','rv32i2p1_m2p0','']:
   with self.subTest(after=after),self.assertRaises(RuntimeError):
    validate_object_attributes(GOOD.replace('rv64i2p1_m2p0_zmmul1p0',after))
 def test_duplicate_fields_fail_closed(self):
  for extra in ['Machine: EM_RISCV (0xF3)\n','Value: rv64i2p1_m2p0_zmmul1p0\n']:
   with self.subTest(extra=extra),self.assertRaises(RuntimeError):
    validate_object_attributes(GOOD+extra)

if __name__=='__main__':unittest.main()
