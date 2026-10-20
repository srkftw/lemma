"""Separate host presentation of actual install and selection record formats."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_school_service import SchoolService,publication_observations


def row(tag,*words):
    return ('K1 '+' '.join(f'{v:016x}' for v in (tag,*words))+'\n').encode()


class PublicationReceipts(unittest.TestCase):
    def test_validated_selection_does_not_change_installation_refusal(self):
        failed=row(0x4b1,0xdf01,0,0x10324,123)
        selected=row(0x4b9,0,9007199254740993,0x10324,123)
        unrelated=row(0x4b1,9,4,0x10324,123)
        result=publication_observations(failed+selected+unrelated)
        self.assertEqual(result['installation']['status'],'223')
        self.assertEqual(result['installation']['state'],'failed')
        self.assertEqual(result['selectedPublication'],{
            'authority':'compiled-guest-report','state':'selected','status':'0',
            'identity':'804','edition':'1','sequence':'9007199254740993','crc32':'123'})
        self.assertIsNone(publication_observations(failed)['selectedPublication'])
        conflict=publication_observations(failed+row(0x4b9,0,7,0x20323,124))
        self.assertEqual(conflict['installation']['identity'],'804')
        self.assertEqual(conflict['selectedPublication']['identity'],'803')

    def test_malformed_latest_selection_clears_old_success_and_partial_does_not_publish(self):
        valid=row(0x4b9,0,7,0x10324,0)
        self.assertEqual(publication_observations(valid)['selectedPublication']['crc32'],'0')
        for bad in (row(0x4b9,256,7,0x10324,0),row(0x4b9,0,0,0x10324,0),
                    row(0x4b9,0,7,1,0),row(0x4b9,0,7,0x10000,0),
                    row(0x4b9,0,7,1<<48,0),row(0x4b9,0,7,0x10324,1<<32),
                    row(0x4b9,0,0x7fffffffffffffff,0x10324,0)):
            with self.subTest(bad=bad):
                self.assertIsNone(publication_observations(bad)['selectedPublication'])
                self.assertIsNone(publication_observations(valid+bad)['selectedPublication'])
        for text in (valid[:-1],b'prefix'+valid):
            self.assertIsNone(publication_observations(text)['selectedPublication'])
        failed=publication_observations(valid+row(0x4b9,223,0,0x10324,0))
        self.assertEqual(failed['selectedPublication']['state'],'failed')
        self.assertEqual(publication_observations(valid+valid[:-1])['selectedPublication']['sequence'],'7')
        for invalid in (None,'text',b'x'*(16*1048576+1)):
            with self.assertRaises(ValueError):publication_observations(invalid)

    def test_ordinary_native_observation_exposes_both_named_receipts(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);uart=directory/'uart.bin'
            uart.write_bytes(row(0x4b1,0xdf01,0,0x10324,123)+
                             row(0x4b9,0,139,0x10324,123)+row(0x4b1,9,139,0x10324,123))
            (directory/'session.json').write_text('{}')
            service=SchoolService(SimpleNamespace(directory=directory))
            try:
                with patch('lemmasim_school_service.uart_path',return_value=uart):
                    result=service.dispatch({'operation':'observation'})
                self.assertEqual(result['installation']['status'],'223')
                self.assertEqual(result['selectedPublication']['sequence'],'139')
                self.assertEqual(result['records']['0x4b1'][0],9)
            finally:service.close()


if __name__=='__main__':unittest.main()
