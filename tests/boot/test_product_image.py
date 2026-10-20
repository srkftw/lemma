"""Independent artifact boundary tests; fixtures are not running target code."""
import copy,hashlib,json,struct,sys,tempfile,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from package_product_image import pack_elf,package
def image():
 elf=bytearray(8192);ident=b'\x7fELF\x02\x01\x01'+bytes(9)
 struct.pack_into('<16sHHIQQQIHHHHHH',elf,0,ident,2,243,1,0x80000000,64,0,0,64,56,2,0,0,0)
 struct.pack_into('<IIQQQQQQ',elf,64,1,5,4096,0x80000000,0x80000000,8,16,4096)
 struct.pack_into('<IIQQQQQQ',elf,120,1,6,8192,0x80400000,0x80400000,0,0x100000,4096)
 elf[4096:4104]=b'abcdefgh'
 dtb=struct.pack('>10I',0xd00dfeed,40,0,0,0,17,16,0,0,0)
 return elf,dtb
class ProductImageTests(unittest.TestCase):
 def test_integrated_binding_versions_cannot_be_substituted(self):
  for configuration,profile in (
   ('lemmasim-silicon-integrated-pcm-school-notebook','lemma-silicon-dev/0.15.0'),
   ('lemmasim-silicon-integrated-school-notebook','lemma-silicon-dev/0.16.0'),
   ('lemmasim-silicon-school-notebook','lemma-silicon-dev/0.14.0')):
   with self.subTest(configuration=configuration),tempfile.TemporaryDirectory() as directory:
    root=Path(directory);guest=root/'guest';guest.mkdir()
    (guest/'build.json').write_text(json.dumps({'status':'BUILT','configuration':configuration}))
    (guest/'audit.json').write_text(json.dumps({'status':'PASS','configuration':configuration}))
    (guest/'binding.json').write_text(json.dumps({'profile':profile}))
    with self.assertRaisesRegex(ValueError,'matching product configuration/profile'):
     package(guest,root/'rejected',23)
    self.assertFalse((root/'rejected').exists())
 def test_original_source_archive_is_required_and_complete(self):
  # A retained image has advanced current sources. Only the complete source
  # receipt bound to its original provenance authorizes archive reuse.
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);guest=root/'guest';guest.mkdir();archive=root/'consumed-source-root';archive.mkdir()
   elf,dtb=image();(guest/'image.elf').write_bytes(elf);(guest/'platform.dtb').write_bytes(dtb)
   digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
   (archive/'Lemma').mkdir();source=archive/'Lemma/Original.lean';source.write_text('def original : UInt64 := 7\n')
   inputs={'Lemma/Original.lean':digest(source)}
   (guest/'provenance.json').write_text(json.dumps({'source_inputs':inputs}))
   build={'status':'BUILT','configuration':'lemmasim-silicon-product-notebook',
    'artifacts':{n:digest(guest/n) for n in ('image.elf','platform.dtb')},'provenance_sha256':digest(guest/'provenance.json')}
   (guest/'build.json').write_text(json.dumps(build))
   (guest/'audit.json').write_text(json.dumps({'status':'PASS','configuration':build['configuration'],'image_sha256':digest(guest/'image.elf')}))
   (guest/'binding.json').write_text(json.dumps({'profile':'lemma-silicon-dev/0.7.0'}))
   receipt={'schema':'lemma-consumed-guest-source-archive/1','original_manifest_sha256':digest(guest/'provenance.json'),'inputs':inputs}
   manifest=root/'consumed-source-archive.json';manifest.write_text(json.dumps(receipt))
   row=package(guest,root/'good',23,archive)
   self.assertEqual(row['source_validation']['kind'],'explicit-consumed-source-archive')
   self.assertEqual(row['source_validation']['inputs'],1)
   for field,value in [('schema','other'),('original_manifest_sha256','0'*64),('inputs',{})]:
    changed=copy.deepcopy(receipt);changed[field]=value;manifest.write_text(json.dumps(changed))
    with self.assertRaises(ValueError):package(guest,root/'rejected',23,archive)
    self.assertFalse((root/'rejected').exists())
   manifest.write_text(json.dumps(receipt));original=source.read_bytes();source.write_bytes(original+b'-- changed\n')
   with self.assertRaises(ValueError):package(guest,root/'rejected',23,archive)
   source.unlink();outside=root/'outside';outside.write_bytes(original);source.symlink_to(outside)
   with self.assertRaises(ValueError):package(guest,root/'rejected',23,archive)
   source.unlink()
   with self.assertRaises(OSError):package(guest,root/'rejected',23,archive)
 def test_wire_bytes_bss_and_independent_crcs(self):
  elf,dtb=image();wire,row=pack_elf(elf,dtb,22);words=struct.unpack_from('<64Q',wire)
  self.assertEqual(words[:8],(0x31474d49414d454c,1,22,0x0007000300010001,2,0x80000000,40,zlib.crc32(dtb)))
  self.assertEqual(words[8:13],(4096,8,16,0x80000000,zlib.crc32(b'abcdefgh')))
  self.assertEqual(words[13:18],(4608,0,0x100000,0x80400000,0))
  self.assertEqual(words[63],zlib.crc32(wire[:504]));self.assertEqual(wire[512:552],dtb);self.assertEqual(wire[4096:4104],b'abcdefgh');self.assertEqual(row['sectors'],9)
 def test_versioned_compatibility_header_and_crc(self):
  elf,dtb=image()
  for compatibility in (0x0007000300010001,0x0009000300010001,0x000a000300010001):
   wire,row=pack_elf(elf,dtb,23,compatibility)
   self.assertEqual(struct.unpack_from('<Q',wire,24)[0],compatibility)
   self.assertEqual(row['compatibility'],compatibility)
   self.assertEqual(struct.unpack_from('<Q',wire,504)[0],zlib.crc32(wire[:504]))
  for compatibility in (0x0008000300010001,0x000b000300010001,0,True):
   with self.assertRaises(ValueError):pack_elf(elf,dtb,23,compatibility)
 def test_invalid_load_entry_and_discovery(self):
  elf,dtb=image()
  mutants=[]
  for offset,value,form in [(48,1,'<I'),(24,0x80010000,'<Q'),(64+8,9000,'<Q'),(64+24,0x80000001,'<Q'),(64+32,17,'<Q'),(64+40,7,'<Q'),(120+24,0x80000008,'<Q')]:
   bad=bytearray(elf);struct.pack_into(form,bad,offset,value);mutants.append(bytes(bad))
  for bad in mutants:
   with self.assertRaises(ValueError):pack_elf(bad,dtb,22)
  for bad in [dtb[:39],b'xxxx'+dtb[4:],dtb+bytes(3073-len(dtb)),dtb[:4]+struct.pack('>I',41)+dtb[8:]]:
   with self.assertRaises(ValueError):pack_elf(elf,bad,22)
  for identity in [0,-1,1<<64,True,1.5]:
   with self.assertRaises(ValueError):pack_elf(elf,dtb,identity)
if __name__=='__main__':unittest.main()
