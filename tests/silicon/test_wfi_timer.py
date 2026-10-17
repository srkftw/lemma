"""Diagnostic record/admission negatives. Fixtures never execute a guest."""
import copy, struct, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import check_guest_wfi_timer as c
from core0_common import Core0Error

class WfiTimerOracle(unittest.TestCase):
 def fixture(self):
  words=[0]*4096;words[:8]=[c.MAGIC,1,0x30,c.DONE,4,22,22,0x534543414c4c0001]
  frames=[];before=100;status=0xa00000800
  for i,ticks in enumerate(c.INTERVALS):
   deadline=before+ticks+7;now=deadline+2;after=now+20
   words[32+16*i:48+16*i]=[i,ticks,before,deadline,after,i,i+1,0,1,1,after+60,i+1,0,0,0,0]
   frames += [0x8000000000000007,0,0x80200204,status,0x282,now,i,now+10]
   before=after+80
  return words,frames,{'lemma_exec_wait_interrupt':(0x80200200,12)},status
 def validate(self,words,frames,ranges,status):
  return c.validate_records(struct.pack('<4096Q',*words),struct.pack('<32Q',*frames),1,ranges,status)
 def test_complete_literal_rows_and_explicit_spurious_count(self):
  words,frames,ranges,status=self.fixture();r=self.validate(words,frames,ranges,status)
  self.assertEqual((r['WFI_calls'],r['spurious_or_nonnotification_returns']),(8,0))
  words[40]=5;r=self.validate(words,frames,ranges,status)
  self.assertEqual((r['WFI_calls'],r['spurious_or_nonnotification_returns']),(12,4))
 def test_actual_frame_deadline_pending_and_completion_fail_closed(self):
  words,frames,ranges,status=self.fixture()
  for index,value in [(3,0),(5,0),(32,2),(33,2),(35,words[34]),(36,0),(38,2),(39,2),(40,0),(41,0),(43,9),(44,1),(4000,1)]:
   with self.subTest(record=index),self.assertRaises(Core0Error):
    candidate=words.copy();candidate[index]=value;self.validate(candidate,frames,ranges,status)
  for index,value in [(0,9),(1,1),(2,0x80000100),(3,status|2),(4,0x82),(5,0),(6,1),(7,0)]:
   with self.subTest(frame=index),self.assertRaises(Core0Error):
    candidate=frames.copy();candidate[index]=value;self.validate(words,candidate,ranges,status)
 def test_absent_partial_and_wrong_boot_records_reject(self):
  words,frames,ranges,status=self.fixture();raw=struct.pack('<4096Q',*words);trace=struct.pack('<32Q',*frames)
  for data,f in [(b'',trace),(raw[:-8],trace),(raw,trace[:-8]),(raw,b'')]:
   with self.assertRaises(Core0Error):c.validate_records(data,f,1,ranges,status)
  with self.assertRaises(Core0Error):c.validate_records(raw,trace,2,ranges,status)
 def test_empty_malformed_or_cross_privilege_unit_rejects(self):
  for data in ({},None,{'schema_version':True}, {'schema_version':1.0}):
   with self.assertRaises(Core0Error):c.validate_unit(data,'kernel')

if __name__=='__main__':unittest.main()
