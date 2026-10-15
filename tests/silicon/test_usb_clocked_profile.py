"""Clock/CDC discovery and package authority; no guest execution claim."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_profile as binding
import silicon_guest as guest
import silicon_guest_bundle as bundle


class USBClockedProfile(unittest.TestCase):
    def test_bound_clocked_profile_does_not_read_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json'
            path.write_text(json.dumps({'schema_version':1,'profile':bundle.USB_CLOCKED_PROFILE,'dtb_base':0x87e00000}))
            item=guest.identified(path)
            data={'profile':bundle.USB_CLOCKED_PROFILE,'profile_sha256':item['sha256'],'binding_profile':item}
            with patch.object(guest,'profile',side_effect=AssertionError('ROOT fallback')):
                self.assertEqual(guest.prepared_profile(data)['dtb_base'],0x87e00000)
                data.pop('binding_profile');data['rtl_source_archive']={'selected_profile':item}
                self.assertEqual(guest.prepared_profile(data)['profile'],bundle.USB_CLOCKED_PROFILE)

    def test_bound_clocked_profile_rejects_missing_corrupt_or_wrong_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json'
            path.write_text(json.dumps({'schema_version':1,'profile':bundle.USB_CLOCKED_PROFILE}))
            item=guest.identified(path)
            data={'profile':bundle.USB_CLOCKED_PROFILE,'profile_sha256':item['sha256'],'binding_profile':item}
            path.write_text('{}')
            with self.assertRaises(ValueError):guest.prepared_profile(data)
            path.unlink()
            with self.assertRaises(ValueError):guest.prepared_profile(data)
            for body in ('{"schema_version":1,"profile":"lemma-silicon-dev/0.11.0"}',
                         '{"schema_version":1,"profile":"lemma-silicon-dev/0.13.0","profile":"lemma-silicon-dev/0.13.0"}'):
                path.write_text(body);data['binding_profile']=guest.identified(path);data['profile_sha256']=data['binding_profile']['sha256']
                with self.assertRaises(ValueError):guest.prepared_profile(data)

    def test_clocked_profile_requires_explicit_bound_bytes(self):
        with patch.object(guest,'profile',side_effect=AssertionError('ROOT fallback')):
            with self.assertRaisesRegex(ValueError,'archived selected profile'):
                guest.prepared_profile({'profile':bundle.USB_CLOCKED_PROFILE})

    def test_historical_profile_reader_keeps_its_original_path(self):
        with patch.object(guest,'profile',return_value={'old':True}) as current:
            self.assertEqual(guest.prepared_profile({'profile':bundle.USB_WIRE_PROFILE}),{'old':True})
            current.assert_called_once_with(bundle.USB_WIRE_PROFILE)

    def test_clock_cdc_and_readback_facts_are_closed(self):
        p = binding.profile(bundle.USB_CLOCKED_PROFILE)
        self.assertEqual((p['descriptor']['abi'], p['descriptor_features'],
                          p['usb_phy_version'], p['paper_version']), (14, 15, 2, 3))
        self.assertEqual((p['clock_hz'], p['timebase_hz'], p['usb_phy_sample_hz'],
                          p['usb_phy_bit_hz'], p['usb_clocked_quantum_hz']),
                         (100000000, 10000000, 48000000, 12000000, 2400000000))
        self.assertEqual(p['usb_clocked_registers'],
                         dict(phy_version=176, phy_nominal_hz=184, controller_nominal_hz=192,
                              cdc_version=200, fifo_bytes=208, packet_bytes=216))
        # Profile13 exposes four explicitly selected software deployments.
        # A prepared bundle still grants only its own exact two role names.
        normal = {
            'usb-clocked-bulk-notebook': 'lemmasim-silicon-usb-clocked-bulk-notebook',
            'usb-clocked-bulk-initializer': 'lemmasim-silicon-usb-clocked-bulk-initialize',
        }
        recovery = {
            'usb-clocked-retry-bulk-notebook': 'lemmasim-silicon-usb-clocked-retry-bulk-notebook',
            'usb-clocked-retry-bulk-initializer': 'lemmasim-silicon-usb-clocked-retry-bulk-initialize',
        }
        closure_recovery = {
            'usb-clocked-closure-retry-bulk-notebook': 'lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook',
            'usb-clocked-closure-retry-bulk-initializer': 'lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize',
        }
        self.assertEqual(bundle.USB_CLOCKED_CONFIGURATIONS, normal)
        self.assertEqual(bundle.USB_RECOVERY_CONFIGURATIONS, recovery)
        self.assertEqual(bundle.USB_CLOSURE_RECOVERY_CONFIGURATIONS, closure_recovery)
        self.assertEqual(guest.configurations(p['profile']), {**normal, **recovery, **closure_recovery, **bundle.USB_PACKAGE_RECOVERY_CONFIGURATIONS})
        self.assertNotEqual(guest.prepared_path(p['profile']), guest.prepared_path(bundle.USB_WIRE_PROFILE))
        for key, value in [('usb_clocked_enabled', 0), ('usb_clocked_quantum_hz', 100000000),
                           ('usb_clocked_ppm_bound', 0), ('usb_clocked_cdc_version', 0),
                           ('usb_clocked_fifo_bytes', 64), ('usb_clocked_packet_bytes', 64),
                           ('usb_phy_version', 1), ('usb_phy_sample_hz', 100000000),
                           ('clock_hz', 48000000), ('paper_version', 2)]:
            bad = copy.deepcopy(p); bad[key] = value
            with self.subTest(key=key), patch.object(binding.json, 'loads', return_value=bad):
                with self.assertRaises(ValueError): binding.profile(p['profile'])

    def test_old_lean_bindings_remain_exact_and_without_clocked_fields(self):
        names = ['Binding', 'BindingFull', 'BindingPower', 'BindingSafety', 'BindingBLE',
                 'BindingUSB', 'BindingProduct', 'BindingUSBNext', 'BindingProductNext',
                 'BindingProductExecuted', 'BindingUSBWire', 'BindingWiFiCommon']
        for number, name in enumerate(names, 1):
            p = binding.profile(f'lemma-silicon-dev/0.{number}.0')
            self.assertEqual(binding.lean_text(p),
                             (binding.ROOT / f'Lemma/Platform/Silicon/{name}.lean').read_text())
            self.assertEqual(binding.constants(p)['usb_clocked_enabled'], 0)
            self.assertNotIn('usb_clocked_', binding.lean_text(p))

    def test_clocked_bundle_cannot_inherit_wire_or_other_role_authority(self):
        manifest = {'schema': bundle.SCHEMA_USB_CLOCKED, 'profile': bundle.USB_CLOCKED_PROFILE,
                    'software_deployment': {'contract_version': bundle.USB_CLOCKED_DEPLOYMENT,
                                            'configurations': dict(bundle.USB_CLOCKED_CONFIGURATIONS)}}
        self.assertEqual(bundle.bundle_configurations(manifest), bundle.USB_CLOCKED_CONFIGURATIONS)
        for key, value in [('schema', bundle.SCHEMA_USB_WIRE), ('profile', bundle.USB_WIRE_PROFILE),
                           ('software_deployment', {'contract_version': bundle.USB_WIRE_DEPLOYMENT,
                                                    'configurations': bundle.USB_WIRE_CONFIGURATIONS})]:
            bad = copy.deepcopy(manifest); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): bundle.bundle_configurations(bad)
        bad = copy.deepcopy(manifest)
        bad['software_deployment']['configurations']['usb-clocked-bulk-initializer'] = 'lemmasim-silicon-usb-wire-bulk-initialize'
        with self.assertRaises(ValueError): bundle.bundle_configurations(bad)


if __name__ == '__main__':
    unittest.main()
