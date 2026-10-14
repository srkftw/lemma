"""Closed recovery package/CLI authority; real guest execution is separate."""
import copy
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_guest as guest
import silicon_guest_bundle as bundle


class RecoveryPackage(unittest.TestCase):
    def manifest(self):
        selected=bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,recovery=True)
        return {'schema':selected[0],'profile':bundle.USB_CLOCKED_PROFILE,
                'software_deployment':bundle.usb_software_deployment(*selected)}

    def test_new_schema_has_complete_identity_and_exact_distinct_pair(self):
        manifest=self.manifest()
        self.assertEqual(bundle.bundle_configurations(manifest),guest.USB_RECOVERY_CONFIGURATIONS)
        self.assertEqual(manifest['software_deployment']['user_profiles'],
            {'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.3'})
        selected=bundle.bundle_configurations(manifest);selected.clear()
        self.assertEqual(bundle.bundle_configurations(manifest),guest.USB_RECOVERY_CONFIGURATIONS)

    def test_historical_schema6_selection_is_unchanged(self):
        selected=bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE)
        self.assertEqual(selected,(bundle.SCHEMA_USB_CLOCKED,bundle.USB_CLOCKED_DEPLOYMENT,
                                  bundle.USB_CLOCKED_CONFIGURATIONS))
        manifest={'schema':selected[0],'profile':bundle.USB_CLOCKED_PROFILE,
                  'software_deployment':bundle.usb_software_deployment(*selected)}
        self.assertEqual(bundle.bundle_configurations(manifest),guest.USB_CLOCKED_CONFIGURATIONS)

    def test_wrong_profile_schema_roles_or_user_identity_reject(self):
        for key,value in [('profile','lemma-silicon-dev/0.11.0'),('schema',bundle.SCHEMA_USB_CLOCKED)]:
            bad=self.manifest();bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):bundle.bundle_configurations(bad)
        for changed in ['old roles','Store1','missing complete identity','extra field']:
            bad=self.manifest();software=bad['software_deployment']
            if changed=='old roles':software['configurations']=copy.deepcopy(bundle.USB_CLOCKED_CONFIGURATIONS)
            elif changed=='Store1':software['user_profiles']['store']='core0-user-v0.1'
            elif changed=='missing complete identity':del software['silicon_profile']
            else:software['unknown']=1
            with self.subTest(changed=changed),self.assertRaises(ValueError):bundle.bundle_configurations(bad)

    def test_missing_or_malformed_native_control_rejects(self):
        bundle.require_recovery_runtime({'runtime_control_contracts':dict(bundle.USB_RECOVERY_CONTROL)})
        for controls in [None,{},[],{'usb_recovery':True},{'usb_recovery':'lemma-usb-live-recovery/2'}]:
            with self.subTest(controls=controls),self.assertRaises(ValueError):
                bundle.require_recovery_runtime({'runtime_control_contracts':controls})

    def test_recovery_cli_requires_explicit_control_before_machine_launch(self):
        run=subprocess.run([str(ROOT/'scripts/lemmasim'),'session','--backend','rtl',
            '--profile',bundle.USB_CLOCKED_PROFILE,'--workload','usb-clocked-retry-bulk-notebook',
            '--session-dir','/unused/recovery','--paused'],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertNotEqual(run.returncode,0)
        self.assertIn('explicit --usb-recovery control contract',run.stdout+run.stderr)


if __name__=='__main__':unittest.main()
