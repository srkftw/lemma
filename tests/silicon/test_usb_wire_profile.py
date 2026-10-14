import copy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_profile as binding
import silicon_guest as guest
import silicon_guest_bundle as bundle


class USBWireProfile(unittest.TestCase):
    def test_explicit_hardware_and_closed_workload_selection(self):
        profile = binding.profile('lemma-silicon-dev/0.11.0')
        self.assertEqual((profile['descriptor']['abi'], profile['descriptor_features'],
                          profile['paper_version'], profile['usb_phy_enabled']), (12, 15, 3, 1))
        self.assertEqual(guest.configurations(profile['profile']), bundle.USB_WIRE_CONFIGURATIONS)
        self.assertNotEqual(guest.prepared_path(profile['profile']), guest.prepared_path('lemma-silicon-dev/0.8.0'))
        self.assertEqual(binding.configuration_profile('lemmasim-silicon-usb-wire-bulk-notebook'), profile['profile'])

    def test_clock_features_or_witness_mutation_reject(self):
        profile = binding.profile('lemma-silicon-dev/0.11.0')
        for key, value in [('usb_phy_enabled', 0), ('usb_phy_version', 2),
                           ('usb_phy_sample_hz', 47000000), ('usb_phy_bit_hz', 13000000),
                           ('boot_nv_enabled', 1), ('paper_version', 2), ('descriptor_features', 31)]:
            wrong = copy.deepcopy(profile); wrong[key] = value
            with self.subTest(key=key), patch.object(binding.json, 'loads', return_value=wrong):
                with self.assertRaises(ValueError): binding.profile('lemma-silicon-dev/0.11.0')

    def test_historical_binding_bytes_do_not_acquire_phy(self):
        names = ['Binding', 'BindingFull', 'BindingPower', 'BindingSafety', 'BindingBLE',
                 'BindingUSB', 'BindingProduct', 'BindingUSBNext', 'BindingProductNext', 'BindingProductExecuted']
        for index, name in enumerate(names, 1):
            profile = binding.profile(f'lemma-silicon-dev/0.{index}.0')
            self.assertEqual(binding.lean_text(profile),
                (binding.ROOT / f'Lemma/Platform/Silicon/{name}.lean').read_text())
            self.assertEqual(binding.constants(profile)['usb_phy_enabled'], 0)

    def test_bundle_schema_profile_and_deployment_cannot_mix(self):
        wire = {'schema': bundle.SCHEMA_USB_WIRE, 'profile': bundle.USB_WIRE_PROFILE,
                'software_deployment': {'contract_version': bundle.USB_WIRE_DEPLOYMENT,
                                        'configurations': bundle.USB_WIRE_CONFIGURATIONS}}
        self.assertEqual(bundle.bundle_configurations(wire), bundle.USB_WIRE_CONFIGURATIONS)
        for key, value in [('schema', bundle.SCHEMA_USB_NEXT), ('profile', bundle.USB_NEXT_PROFILE),
                           ('software_deployment', {'contract_version': bundle.USB_NEXT_DEPLOYMENT,
                                                    'configurations': bundle.USB_NEXT_CONFIGURATIONS})]:
            wrong = copy.deepcopy(wire); wrong[key] = value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): bundle.bundle_configurations(wrong)

    def test_explicit_role_archives_preserve_default_and_never_infer_root(self):
        self.assertEqual(bundle.usb_archive_roots(SimpleNamespace()), (None, None))
        notebook, initializer = Path('/declared/notebook'), Path('/declared/initializer')
        self.assertEqual(bundle.usb_archive_roots(SimpleNamespace(guest_source_root=notebook)),
                         (notebook, notebook))
        self.assertEqual(bundle.usb_archive_roots(SimpleNamespace(guest_source_root=notebook,
                         initializer_guest_source_root=initializer)), (notebook, initializer))
        with self.assertRaisesRegex(ValueError, 'requires explicit notebook'):
            bundle.usb_archive_roots(SimpleNamespace(initializer_guest_source_root=initializer))
        with self.assertRaisesRegex(ValueError, 'only USB'):
            bundle.bundle(SimpleNamespace(profile='lemma-silicon-dev/0.3.0',
                          initializer_guest_source_root=initializer))


if __name__ == '__main__':
    unittest.main()
