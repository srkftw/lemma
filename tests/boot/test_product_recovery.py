"""Independent wire oracle; no compiled-ROM or controller execution claim."""
import struct,sys,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_product as product

class RecoveryWireTests(unittest.TestCase):
 def test_request_words_and_both_crc_domains(self):
  payload=bytes((i*13+7)%256 for i in range(512))
  wire=product.frame(0x123456789abcdef0,1,1,32767,73,payload)
  self.assertEqual(len(wire),592)
  self.assertEqual(struct.unpack('<10Q',wire[:80]),(0x31564f4345524d4c,1,0x123456789abcdef0,1,1,32767,73,0,zlib.crc32(payload),zlib.crc32(wire[:72])))
  self.assertEqual(wire[80:],payload)
 def test_receipt_integrity_and_status_width(self):
  first=struct.pack('<4Q',0x3154504345524d4c,91,211,0)
  wire=first+struct.pack('<Q',zlib.crc32(first))
  self.assertEqual(product.receipt(wire),{'transaction':91,'status':211,'value':0})
  for index in (0,8,16,24,32,39):
   mutated=bytearray(wire);mutated[index]^=1
   with self.assertRaises(ValueError):product.receipt(mutated)
  first=struct.pack('<4Q',0x3154504345524d4c,91,256,0)
  with self.assertRaises(ValueError):product.receipt(first+struct.pack('<Q',zlib.crc32(first)))
 def test_bounded_request_rejections(self):
  for values in ((0,0),(1,5),(-1,0),(1<<64,0),(1.5,0)):
   with self.assertRaises(ValueError):product.frame(*values)
  for payload in (b'',bytes(511),bytes(513)):
   with self.assertRaises(ValueError):product.frame(1,1,payload=payload)
  with self.assertRaises(ValueError):product.frame(1,0,payload=bytes(512))
  for size in (0,39,41):
   with self.assertRaises(ValueError):product.receipt(bytes(size))
if __name__=='__main__':unittest.main()
