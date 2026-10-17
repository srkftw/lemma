"""Cold outcome observer negatives; not guest execution evidence."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_browser_cold_export import crc64, validate_read_tape, cold_page_read_offsets
from store_oracle import ROOT, RECORD, COMMIT, MASK, fnv
from inspect_notebook import MAGIC


def page_fixture(*, entries=((65537,1,1),(65538,2,0),(65539,3,1)),
                 chunk_page=1, width=1650, root_version=1, raw_sequence=1):
    """Literal, independently checksummed sectors; no target codec imported."""
    def sector(words):
        prefix = struct.pack('<'+'Q'*len(words),*words)
        check = fnv(prefix)
        return prefix+struct.pack('<2Q',check,check^MASK)+bytes(496-len(prefix))
    image = bytearray(4096*512)
    image[:512] = sector([ROOT,1,1,4096,0,8,2044,0,0,0])
    image[512:1024] = image[:512]
    page = struct.pack('<16Q',MAGIC,2,2,1,len(entries),0,0,*([0]*9))
    page += b''.join(struct.pack('<3Q',*entry) for entry in entries)
    payloads = [(1,struct.pack('<8Q',MAGIC,root_version,1,1,512,0,0,0)),(257,page)]
    for object_id,stroke in ((65537,1),(65538,2),(65539,3)):
        payload = struct.pack('<16Q',MAGIC,1,3,chunk_page,stroke,0,3,512,
                              1,65535,65535,4095,width,2200,3,0)
        payload += b''.join(struct.pack('<9Q',raw_sequence+i,100+i,1000,2000,
                            0 if i == 2 else 1024,2 if i == 2 else 3,1,0,1)
                            for i in range(3))
        payloads.append((object_id,payload))
    cursor = 8
    positions = {}
    for sequence,(object_id,payload) in enumerate(payloads,1):
        positions[object_id] = cursor
        count = (len(payload)+511)//512
        header = sector([RECORD,1,1,1,object_id,sequence,sequence,len(payload),1,count,fnv(payload)])
        image[cursor*512:(cursor+1)*512] = header
        image[(cursor+1)*512:(cursor+1)*512+len(payload)] = payload
        image[(cursor+1+count)*512:(cursor+2+count)*512] = sector(
            [COMMIT,1,1,1,object_id,sequence,sequence,len(payload),1,fnv(payload),
             struct.unpack_from('<Q',header,88)[0]])
        cursor += count+2
    return bytes(image),positions,cursor


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

    def test_indexed_page_complete_mount_and_visible_order(self):
        image,positions,tail = page_fixture()
        expected = [0,512]+[sector*512 for sector in range(8,tail+1)]
        for object_id in (1,257,65537,65539):
            expected += [positions[object_id]*512,(positions[object_id]+1)*512]
        self.assertEqual(cold_page_read_offsets(image),expected)
        # Erased ink remains part of mount validation, but is never loaded
        # for redraw. Index order, rather than physical sector order, wins.
        image,positions,tail = page_fixture(entries=((65539,3,1),(65537,1,1)))
        suffix = cold_page_read_offsets(image)[2+(tail-8+1):]
        self.assertEqual(suffix,[p*512 for key in (1,257,65539,65537)
                                for p in (positions[key],positions[key]+1)])

    def test_checksummed_invalid_page_reference_is_rejected(self):
        for changes in ({'entries':((65537,1,1),(65537,1,1))},
                        {'entries':((65540,4,1),)},
                        {'entries':((65537,9,1),)},
                        {'chunk_page':2},{'width':1404},{'root_version':2},
                        {'raw_sequence':0}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                cold_page_read_offsets(page_fixture(**changes)[0])


if __name__ == '__main__':
    unittest.main()
