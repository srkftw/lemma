"""Fail-closed qualifier boundary tests; genuine LLVM mutation run is separate."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from core0_common import Core0Error
from check_legacy_record_reader import legacy_route

class LegacyReaderBoundary(unittest.TestCase):
    def test_empty_evidence_rejected(self):
        with self.assertRaises(Core0Error):legacy_route('',{})

    def test_incompatible_metadata_rejected(self):
        unit={'configuration':'lemmasim-silicon-power-notebook','role':'user',
              'image_key':'notebook','contract_version':'core0-user-v0.1','functions':[]}
        for field,value in [('configuration','lemmasim-bringup'),('role','kernel'),
                            ('image_key','arithmetic'),('contract_version','core0-user-v0.2')]:
            with self.subTest(field=field):
                with self.assertRaisesRegex(Core0Error,'incompatible'):
                    legacy_route('',{**unit,field:value})

    def test_empty_source_closure_rejected(self):
        for config,profile in [('lemmasim-silicon-power-notebook','core0-user-v0.1'),
                               ('lemmasim-silicon-managed-notebook','core0-user-v0.2')]:
            with self.subTest(configuration=config):
                with self.assertRaisesRegex(Core0Error,'actual selected source closure'):
                    legacy_route('',{'configuration':config,'role':'user','image_key':'notebook',
                                     'contract_version':profile,'functions':[]})
if __name__=='__main__':unittest.main()
