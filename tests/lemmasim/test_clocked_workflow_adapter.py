"""Host registration/oracle inheritance only; no notebook execution claim."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import check_guest_usb_clocked_notebook as clocked
import check_guest_usb_notebook as base
import supervise_usb_clocked_notebook as supervisor

class ClockedAdapter(unittest.TestCase):
    def test_only_exact_bundle_deployment_is_registered(self):
        good=dict(profile=clocked.NAME,native_bundle=Path('/selected'),rtl_source_root=None,guest_source_root=None)
        self.assertTrue(clocked.source_authority_valid(SimpleNamespace(**good)))
        for field,value in (('profile','lemma-silicon-dev/0.11.0'),('native_bundle',None),
                            ('rtl_source_root',Path('/native')),('guest_source_root',Path('/guest'))):
            changed={**good,field:value}
            with self.subTest(field=field):self.assertFalse(clocked.source_authority_valid(SimpleNamespace(**changed)))

    def test_ready_pixels_records_and_full_scenario_are_inherited(self):
        self.assertIs(clocked.ClockedLive.panel_matches,base.NativeUSBSession.panel_matches)
        self.assertIs(clocked.ClockedLive.wait,base.NativeUSBSession.wait)
        self.assertIs(clocked.ClockedChecker.execute,base.Checker.execute)
        self.assertIs(clocked.ClockedChecker.close,base.Checker.close)

    def test_running_wire_sources_are_exact_and_unmodified(self):
        self.assertEqual(base.sha(base.__file__),clocked.BASE_SHA256)
        self.assertEqual(supervisor.supervisor.digest(supervisor.supervisor.__file__),supervisor.BASE_SUPERVISOR_SHA256)
        self.assertNotIn(clocked.NAME,base.PROFILE_WORKLOADS)

    def test_original_bounds_and_supervision_are_preserved(self):
        self.assertEqual(base.WIRE_MAX_TREE_RSS_KIB,4194304)
        self.assertEqual(base.WIRE_MAX_DISK_BYTES,12000000000)
        self.assertEqual(supervisor.supervisor.MAX_SECONDS,65000)

if __name__=='__main__':unittest.main()
