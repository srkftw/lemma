"""Exact public software-family admission; no simulated guest-success fixtures."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_guest as guest
import silicon_guest_bundle as bundle
from usb_closure_recovery_deployment import SOFTWARE_DEPLOYMENT

class ClosureRecoveryBundleTests(unittest.TestCase):
    def test_schema8_selects_exact_compiler_software_contract(self):
        schema,version,configs=bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,closure_recovery=True)
        self.assertEqual(schema,'lemmasim-native-bundle/8')
        self.assertEqual(bundle.usb_software_deployment(schema,version,configs),
                         {**SOFTWARE_DEPLOYMENT,'configurations':configs})
        self.assertEqual(guest.configurations(bundle.USB_CLOCKED_PROFILE)['usb-clocked-closure-retry-bulk-notebook'],
                         'lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook')
        self.assertIn('usb-clocked-closure-retry-bulk-notebook',guest.NOTEBOOK_WORKLOADS)

    def test_historical_sums_and_clocked_deployments_remain_separate(self):
        self.assertEqual(bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,recovery=True),
                         (bundle.SCHEMA_USB_RECOVERY,bundle.USB_RECOVERY_SOFTWARE['contract_version'],bundle.USB_RECOVERY_CONFIGURATIONS))
        self.assertEqual(bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE),
                         bundle.USB_NATIVE_DEPLOYMENTS[bundle.USB_CLOCKED_PROFILE])
        self.assertEqual(bundle.USB_RECOVERY_SOFTWARE['user_profiles']['arithmetic'],'core0-user-v0.3')
        self.assertEqual(bundle.USB_CLOSURE_RECOVERY_SOFTWARE['user_profiles']['arithmetic'],'core0-user-v0.7')

    def test_mixed_flag_schema_or_hardware_fails_before_pack(self):
        for kwargs in ({'recovery':True,'closure_recovery':True},
                       {'recovery':True,'schema':bundle.SCHEMA_USB_CLOSURE_RECOVERY},
                       {'closure_recovery':True,'schema':bundle.SCHEMA_USB_RECOVERY},
                       {'schema':'lemmasim-native-bundle/99'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,**kwargs)
        for profile in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.11.0','unknown/0.13.0'):
            with self.subTest(profile=profile),self.assertRaises(ValueError):
                bundle.usb_native_deployment(profile,closure_recovery=True)
        with self.assertRaises(ValueError):
            bundle.bundle(SimpleNamespace(profile=bundle.USB_CLOCKED_PROFILE,
                usb_recovery_deployment=True,usb_closure_recovery_deployment=True))

    def test_foreign_software_or_config_cannot_acquire_schema8(self):
        selected=bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,closure_recovery=True)
        original={'schema':selected[0],'profile':bundle.USB_CLOCKED_PROFILE,
                  'software_deployment':bundle.usb_software_deployment(*selected)}
        self.assertEqual(bundle.bundle_configurations(original),bundle.USB_CLOSURE_RECOVERY_CONFIGURATIONS)
        for name in ('arithmetic','old-config','old-schema','old-profile'):
            wrong=copy.deepcopy(original)
            if name=='arithmetic':wrong['software_deployment']['user_profiles']['arithmetic']='core0-user-v0.3'
            elif name=='old-config':wrong['software_deployment']['configurations']=bundle.USB_RECOVERY_CONFIGURATIONS
            elif name=='old-schema':wrong['schema']=bundle.SCHEMA_USB_RECOVERY
            else:wrong['profile']='lemma-silicon-dev/0.11.0'
            with self.subTest(name=name),self.assertRaises(ValueError):bundle.bundle_configurations(wrong)

    def test_static_pass_does_not_replace_real_native_control_marker(self):
        for runtime in ({'status':'PASS'}, {'status':'PASS','runtime_control_contracts':{}},
                        {'runtime_control_contracts':{'usb_recovery':'lemma-usb-live-recovery/99'}}):
            with self.subTest(runtime=runtime),self.assertRaises(ValueError):bundle.require_recovery_runtime(runtime)
        bundle.require_recovery_runtime({'runtime_control_contracts':{'usb_recovery':'lemma-usb-live-recovery/1'}})

if __name__=='__main__':unittest.main()
