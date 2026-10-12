from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from lemmasim_fast import copy_new


class PrivateMediumCopy(unittest.TestCase):
    def test_sparse_private_copy_preserves_tail_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'source';destination=Path(temporary)/'private'
            with source.open('xb') as stream:
                stream.write(b'first');stream.seek(4*1024*1024);stream.write(b'last')
            copy_new(source,destination)
            self.assertEqual(source.read_bytes(),destination.read_bytes())
            self.assertEqual(destination.stat().st_size,4*1024*1024+4)
            self.assertLess(destination.stat().st_blocks*512,2*1024*1024)
            with self.assertRaises(FileExistsError):copy_new(source,destination)
            self.assertEqual(source.read_bytes(),destination.read_bytes())
