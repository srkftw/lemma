"""Recovery4 packages grant only their four-role software and live control."""
import copy
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import silicon_guest as guest
import silicon_guest_bundle as bundle
from package_companion_deployment import SOFTWARE_DEPLOYMENT

class PackageRecoveryBundleTests(unittest.TestCase):
    def test_schema9_exact_four_role_pair_and_live_control(self):
        selected=bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,package_recovery=True)
        self.assertEqual(selected[0],'lemmasim-native-bundle/9')
        original={'schema':selected[0],'profile':bundle.USB_CLOCKED_PROFILE,
                  'software_deployment':bundle.usb_software_deployment(*selected)}
        self.assertEqual(original['software_deployment'],{**SOFTWARE_DEPLOYMENT,'configurations':selected[2]})
        self.assertEqual(bundle.bundle_configurations(original),bundle.USB_PACKAGE_RECOVERY_CONFIGURATIONS)
        self.assertIn('usb-clocked-package-retry-bulk-notebook',guest.NOTEBOOK_WORKLOADS)
        for name in ('role','config','schema','profile','version'):
            wrong=copy.deepcopy(original)
            if name=='role':wrong['software_deployment']['user_profiles'].pop('course')
            elif name=='config':wrong['software_deployment']['configurations']=bundle.USB_CLOSURE_RECOVERY_CONFIGURATIONS
            elif name=='schema':wrong['schema']=bundle.SCHEMA_USB_CLOSURE_RECOVERY
            elif name=='profile':wrong['profile']='lemma-silicon-dev/0.3.0'
            else:wrong['software_deployment']['contract_version']='lemma-package-clocked-recovery4-deployment-v2'
            with self.subTest(name=name),self.assertRaises(ValueError):bundle.bundle_configurations(wrong)
        for runtime in ({'status':'PASS'}, {'runtime_control_contracts':{'usb_recovery':'lemma-usb-live-recovery/2'}}):
            with self.assertRaises(ValueError):bundle.require_recovery_runtime(runtime)

    def test_mixed_selection_cannot_acquire_other_schema(self):
        for kwargs in ({'package_recovery':True,'recovery':True},
                       {'package_recovery':True,'closure_recovery':True},
                       {'package_recovery':True,'schema':bundle.SCHEMA_USB_CLOSURE_RECOVERY},
                       {'recovery':True,'schema':bundle.SCHEMA_USB_PACKAGE_RECOVERY},
                       {'closure_recovery':True,'schema':bundle.SCHEMA_USB_PACKAGE_RECOVERY}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                bundle.usb_native_deployment(bundle.USB_CLOCKED_PROFILE,**kwargs)
        with self.assertRaises(ValueError):
            bundle.usb_native_deployment('lemma-silicon-dev/0.11.0',package_recovery=True)

if __name__=='__main__':unittest.main()
