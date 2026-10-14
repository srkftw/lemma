"""Cold outcome observer negatives; not guest execution evidence."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_browser_cold_export import crc64, validate_read_tape


class ColdReadOutcomes(unittest.TestCase):
    identity = 'a'*64
    medium = bytes(range(256))*2

    def tape(self, *, returned=None, identity=None, ordinal=1, offset=0, completed=5):
        request = struct.pack('<5Q',ordinal,3,0,offset,512)
        request += struct.pack('<Q',crc64(request))
        outcome = struct.pack('<7Q',ordinal,3,0,offset,512,512,0)
        outcome += self.medium if returned is None else returned
        outcome += struct.pack('<Q',crc64(outcome))
        outcome += struct.pack('<Q',completed)
        outcome += struct.pack('<Q',crc64(outcome))
        return (b'LMIOLOG2'+(identity or self.identity).encode()+
                struct.pack('<2Q',0,len(request))+request+
                struct.pack('<2Q',1,len(outcome))+outcome)

    def test_complete_bytes_and_crc_correct_semantic_negatives(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'read.io'
            path.write_bytes(self.tape())
            self.assertEqual(validate_read_tape(path,self.identity,self.medium,[0],5),1)
            for name, wire in {
                    'changed returned byte':self.tape(returned=b'\xff'+self.medium[1:]),
                    'wrong implementation':self.tape(identity='b'*64),
                    'wrong request ordinal':self.tape(ordinal=2),
                    'wrong sector':self.tape(offset=512),
                    'future completion':self.tape(completed=6),
                    'missing completion':self.tape()[:136],
                    'empty corpus':b'LMIOLOG2'+self.identity.encode(),
                }.items():
                with self.subTest(name=name):
                    path.write_bytes(wire)
                    with self.assertRaises(ValueError):
                        validate_read_tape(path,self.identity,self.medium,[0],5)


if __name__ == '__main__':
    unittest.main()
