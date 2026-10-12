"""Independent artifact/RAM negatives; actual hardware runs are separate."""
import copy,struct,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from check_guest_counters import CSR_OPERATIONS,validate_csr_bytes,validate_records

class CounterArtifactTests(unittest.TestCase):
 def test_each_fixed_access_rejects_selector_and_abi_mutations(self):
  # Literal ISA encoding independent of the typed assembly renderer.
  code=bytearray();ranges={}
  for _,symbol,csr,write in CSR_OPERATIONS.values():
   word=(csr<<20)|((10 if write else 0)<<15)|((1 if write else 2)<<12)|((0 if write else 10)<<7)|0x73
   words=[word,0x513,0x8067] if write else [word,0x8067]
   ranges[symbol]=(0x80000000+len(code),4*len(words));code+=struct.pack('<'+'I'*len(words),*words)
  self.assertEqual(len(validate_csr_bytes(bytes(code),0x80000000,ranges)),9)
  for symbol,(address,size) in ranges.items():
   for delta in (0,1,size-4):
    bad=code[:];bad[address-0x80000000+delta]^=1
    with self.subTest(symbol=symbol,offset=delta),self.assertRaises(Core0Error):
     validate_csr_bytes(bytes(bad),0x80000000,ranges)
 def test_guest_semantic_record_failures_remain_load_bearing(self):
  rows=[0]*25
  rows[0]=0x4353524755455354;rows[1]=0x8000000000141100;rows[2:5]=[5,7,0]
  rows[5]=rows[8]=123456;rows[6]=rows[9]=789;rows[7]=20;rows[10]=21
  rows[11]=123457;rows[12]=790;rows[13]=rows[15]=1000;rows[14]=2001;rows[16]=2002
  rows[17]=3001;rows[19]=3002;rows[18]=rows[20]=4000;rows[21]=1;rows[22]=2
  rows[23]=0x4353525041535301
  self.assertEqual(validate_records(struct.pack('<25Q',*rows)),rows)
  for field,value in ((1,rows[1]|1),(2,7),(3,(1<<64)-1),(8,123457),(10,20),(15,1001),
                       (18,4001),(21,1<<63),(23,0),(24,5)):
   bad=rows[:];bad[field]=value
   with self.subTest(field=field),self.assertRaises(Core0Error):validate_records(struct.pack('<25Q',*bad))
  with self.assertRaises(Core0Error):validate_records(b'')

if __name__=='__main__':unittest.main()
