import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import usb_fork_fault as fault
from lemmasim_session import Session


class PrefixTests(unittest.TestCase):
    def fixture(self, directory, rows, cycle=2000):
        wire=b''.join(rows);checksum=fault.chain(f'{cycle} 3 0 HORIZON\n'.encode(),fault.chain(wire))
        p=Path(directory)/'prefix';p.write_bytes(b'LMUSBRP1 '+b'0'*64+b'\n'+
            f'HORIZON {cycle}\n'.encode()+wire+f'CHECKSUM {checksum}\n'.encode());return p

    def test_only_an_active_WAIT_is_cancellable(self):
        with tempfile.TemporaryDirectory() as directory:
            path=self.fixture(directory,[b'1000 0 1 WAIT 100000\n'])
            _,data=fault.prefix(path,'0'*64,2000)
            self.assertEqual(data['command'],'WAIT 100000')
            self.assertEqual(data['pending_command'],1)
            for row in (b'1000 0 1 RECV\n',b'1000 0 1 SEND e10000\n',b'1000 0 1 RESET 5000000\n'):
                with self.subTest(row=row):
                    path=self.fixture(directory,[row])
                    with self.assertRaisesRegex(ValueError,'idle WAIT'):fault.prefix(path,'0'*64,2000)

    def test_terminal_completed_noncanonical_and_future_rows_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            for rows in ([b'1000 0 1 WAIT 100000\n',b'1001 1 1 WAIT_DONE\n'],
                         [b'1000 0 1 WAIT 100000\n',b'1001 2 1 USB process disconnected read\n'],
                         [b'01000 0 1 WAIT 100000\n'],[b'2000 0 1 WAIT 100000\n'],
                         [b'1000 0 2 WAIT 100000\n']):
                with self.subTest(rows=rows):
                    with self.assertRaises(ValueError):fault.prefix(self.fixture(directory,rows),'0'*64,2000)

    def test_corrupt_checksum_and_identity_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path=self.fixture(directory,[b'1000 0 1 WAIT 100000\n'])
            with self.assertRaisesRegex(ValueError,'identity'):fault.prefix(path,'1'*64,2000)
            path.write_bytes(path.read_bytes().replace(b'WAIT 100000',b'WAIT 100001'))
            with self.assertRaisesRegex(ValueError,'checksum'):fault.prefix(path,'0'*64,2000)


class APITests(unittest.TestCase):
    def test_unrestored_running_or_nonlaboratory_session_rejects_before_call(self):
        class NoCall:
            def call(self,_):raise AssertionError('machine called before scope guard')
        for mode,automatic,parent in [('developer',False,Path('/unused')),('laboratory',True,Path('/unused')),
                                      ('laboratory',False,None)]:
            s=Session.__new__(Session);s.machine=NoCall();s.mode=mode;s.automatic=automatic
            s.restored_parent=parent;s.capture_uncertain=False
            with self.assertRaisesRegex(ValueError,'paused restored Laboratory'):
                s.dispatch({'action':'usb-fault','path':'/unused'})


if __name__=='__main__':unittest.main()
