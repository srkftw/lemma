import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from ble_peer_state import PeerState,parse_response

class CompletePeerState(unittest.TestCase):
 def test_canonical_complete_state_and_restore_framing(self):
  action,state=parse_response('TX 5 0 - | STATE 262 ACCEPTED 1 DUPLICATES 0 PENDING 2 0102')
  self.assertEqual(action,'TX 5 0 -')
  self.assertEqual(state,PeerState(262,1,0,bytes([1,2])))
  self.assertEqual(state.restore_command(),'RESTORE 262 1 0 0102')
 def test_missing_duplicate_unknown_or_noncanonical_fields(self):
  good='STATUS | STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 0 -'
  for bad in [good.replace(' ACCEPTED 0',''),good+' | STATE 0',good.replace('STATUS','BLEPEER/1'),
    good.replace('ACCEPTED 0','ACCEPTED 00'),good.replace('STATE 0','STATE -1'),good+'\n']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):parse_response(bad)
 def test_actual_shape_bounds_are_fail_closed(self):
  for bad in ['STATUS | STATE 256 ACCEPTED 0 DUPLICATES 0 PENDING 0 -',
    'STATUS | STATE 12 ACCEPTED 0 DUPLICATES 0 PENDING 0 -',
    'STATUS | STATE 0 ACCEPTED 9223372036854775808 DUPLICATES 0 PENDING 0 -',
    'STATUS | STATE 0 ACCEPTED 0 DUPLICATES 9223372036854775808 PENDING 0 -',
    'STATUS | STATE 0 ACCEPTED 1 DUPLICATES 0 PENDING 28 '+'00'*28,
    'STATUS | STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 1 01',
    'TX 5 0 - | STATE 0 ACCEPTED 0 DUPLICATES 0 PENDING 0 -',
    'STATUS | STATE 0 ACCEPTED 1 DUPLICATES 0 PENDING 1 AA']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):parse_response(bad)

if __name__=='__main__':unittest.main()
