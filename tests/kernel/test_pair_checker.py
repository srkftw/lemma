"""Publication/adjacency host fixtures; actual allocator checks run in QEMU."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_kernel_frames import PAIR_RESULT, read_contiguous_pair
from core0_common import Core0Error


class PairPublicationTests(unittest.TestCase):
    def command(self, handles=(5*512,512+1), physical=(0x82000000,0x82001000)):
        def command(number,a=0,b=0,*args,**kwargs):
            if number==8:return handles[(a-PAIR_RESULT)//8],510
            if number==5:return physical[handles.index(b)],510
            raise AssertionError('unexpected fixture command')
        return command

    def test_independent_generations_are_accepted_but_wrong_slot_or_physical_mapping_rejected(self):
        self.assertEqual(read_contiguous_pair(self.command(),2)[0],(5*512,512+1))
        for command in [self.command(handles=(0,513)),self.command(handles=(2560,514)),
                        self.command(physical=(0x82000000,0x82002000)),self.command(handles=(511+512,1024))]:
            with self.assertRaises(Core0Error):read_contiguous_pair(command,2)


if __name__=='__main__':unittest.main()
