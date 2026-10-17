from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_usb_fork_failure_observation import failed_rows


class UnsuccessfulAutosaveOracleTests(unittest.TestCase):
    def test_error_status_is_not_the_pending_sequence(self):
        failed_rows([(0x423,12,1,1,65548),(0x424,227,1,1,65548)])
        with self.assertRaises(ValueError):
            failed_rows([(0x423,12,1,1,65548),(0x424,12,1,1,65548)])

    def test_saved_extra_effect_and_wrong_object_or_identity_reject(self):
        valid=[(0x423,12,1,1,65548),(0x424,227,1,1,65548)]
        cases=[valid+[(0x421,12,1,1,65548)],valid+[(0x423,11,1,1,0)],
               [(0x423,12,1,1,65548),(0x424,227,1,1,0)],
               [(0x423,12,2,1,65548),(0x424,227,2,1,65548)],[],valid[:1]]
        for rows in cases:
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):failed_rows(rows)


if __name__=='__main__':unittest.main()
