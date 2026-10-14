"""Raw command frame and exact deployment admission, not guest durability."""
import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_course import frame
from silicon_guest_bundle import development_configuration

class CourseCommand(unittest.TestCase):
 def test_literal_wire_frame_and_limits(self):
  wire=frame(1,65535,0xffffffff,32768,7,0xffffffff)
  self.assertEqual(len(wire),64)
  self.assertEqual(struct.unpack('<8Q',wire),(0x31504b43414d454c,1,1,65535,0xffffffff,32768,7,0xffffffff))
  self.assertEqual(struct.unpack('<8Q',frame(2,1,2,0,15,0))[-2:],(15,0))
  for args in ((1,0,1,128,1,0),(1,1,0,128,1,0),(1,1,1,32769,1,0),
               (1,1,1,128,0,0),(2,1,1,0,16,0),(3,1,1,1,1,0),(3,1,1,0,1,1<<32)):
   with self.subTest(args=args),self.assertRaises(ValueError):frame(*args)
 def test_exact_local_authority_and_historical_mode(self):
  course='lemmasim-silicon-course-bulk-notebook'
  for mode in ('developer','laboratory'):
   self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',course,mode),course)
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','notebook',course,'student')
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.3.0','initializer',course,'developer')
  with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.2.0','notebook',course,'developer')
  ordinary='lemmasim-silicon-array-bulk-notebook'
  self.assertEqual(development_configuration('lemma-silicon-dev/0.3.0','notebook',ordinary,'student'),ordinary)

if __name__=='__main__':unittest.main()
