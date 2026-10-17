"""Independent wire oracle; no compiled-ROM or controller execution claim."""
import struct,sys,tempfile,time,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_product as product

class RecoveryWireTests(unittest.TestCase):
 def test_request_cannot_reuse_an_old_success_receipt(self):
  def reply(status):
   first=struct.pack('<4Q',0x3154504345524d4c,73,status,0)
   return first+struct.pack('<Q',zlib.crc32(first))
  with tempfile.TemporaryDirectory() as directory:
   uart=Path(directory)/'uart.bin';uart.write_bytes(reply(0))
   client=object.__new__(product.RecoveryClient)
   client.directory=Path(directory);client.next_id=73;client.cursor=0;client.used=0
   client.deadline=time.monotonic()+1;client.max_cycles=1;client.quantum=1
   calls=[]
   def call(request):
    calls.append(request)
    if request['action']=='inject':uart.write_bytes(uart.read_bytes()+reply(211))
   client.call=call
   self.assertEqual(client.send(0),{'transaction':73,'status':211,'value':0})
   self.assertEqual([r['action'] for r in calls],['inject'])
   uart.write_bytes(reply(0)[:-1]);calls.clear()
   with self.assertRaises(ValueError):client.send(0)
   self.assertEqual(calls,[])
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
 def test_profile_discovery_extent_before_install(self):
  wire=bytearray(512);struct.pack_into('<Q',wire,48,2873);struct.pack_into('<Q',wire,24,0x0007000300010001)
  product.install_extent({'discovery_bytes':2873,'compatibility':0x0007000300010001},wire,{'discovery_bytes':2873})
  for size in (None,39,2872,2874,3073,True,2873.0):
   with self.assertRaises(ValueError):product.install_extent({'discovery_bytes':2873},wire,{'discovery_bytes':size})
  for size in (2872,2874,None):
   with self.assertRaises(ValueError):product.install_extent({'discovery_bytes':size},wire,{'discovery_bytes':2873})
  struct.pack_into('<Q',wire,48,2874)
  with self.assertRaises(ValueError):product.install_extent({'discovery_bytes':2873,'compatibility':0x0007000300010001},wire,{'discovery_bytes':2873})
  with self.assertRaises(ValueError):product.install_extent({'discovery_bytes':2873},wire[:511],{'discovery_bytes':2873})

 def test_product_profile_compatibility_pairs_are_exact(self):
  for profile,compatibility in [('lemma-silicon-dev/0.7.0',0x0007000300010001),('lemma-silicon-dev/0.9.0',0x0009000300010001),('lemma-silicon-dev/0.10.0',0x000a000300010001)]:
   wire=bytearray(512);struct.pack_into('<Q',wire,24,compatibility);struct.pack_into('<Q',wire,48,2873)
   package={'discovery_bytes':2873,'compatibility':compatibility};identity={'discovery_bytes':2873,'profile':profile}
   product.install_extent(package,wire,identity)
   other=0x0009000300010001 if compatibility==0x0007000300010001 else 0x0007000300010001
   with self.assertRaisesRegex(ValueError,'compatibility'):product.install_extent(dict(package,compatibility=other),wire,identity)
   struct.pack_into('<Q',wire,24,other)
   with self.assertRaisesRegex(ValueError,'compatibility'):product.install_extent(package,wire,identity)

if __name__=='__main__':unittest.main()
