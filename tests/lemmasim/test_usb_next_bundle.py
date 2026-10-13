from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_guest_bundle as bundle


class USBNextPackage(unittest.TestCase):
    def manifest(self):
        return {'schema': bundle.SCHEMA_USB_NEXT, 'profile': bundle.USB_NEXT_PROFILE,
                'backends': {'rtl': {}}, 'host_dependencies': {'rtl': {}},
                'software_deployment': {'contract_version': bundle.USB_NEXT_DEPLOYMENT,
                                        'configurations': dict(bundle.USB_NEXT_CONFIGURATIONS)}}

    def test_schema4_roles_are_closed_and_return_an_independent_map(self):
        selected = bundle.bundle_configurations(self.manifest())
        self.assertEqual(selected, bundle.USB_NEXT_CONFIGURATIONS)
        selected['usb-next-bulk-notebook'] = 'lemmasim-silicon-usb-bulk-notebook'
        self.assertNotEqual(selected, bundle.USB_NEXT_CONFIGURATIONS)
        bad = self.manifest()
        bad['software_deployment']['configurations'] = selected
        with self.assertRaisesRegex(ValueError, 'authority'):
            bundle.bundle_configurations(bad)

    def test_no_fast_product_or_legacy_deployment_authority(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(bundle, 'inventory') as inventory:
            for backend, profile in (('qemu', bundle.USB_NEXT_PROFILE),
                                     ('rtl', 'lemma-silicon-dev/0.9.0')):
                with self.subTest(backend=backend, profile=profile), self.assertRaises(ValueError):
                    bundle.prepared_usb_next(Path(directory), self.manifest(), backend,
                                             'usb-next-bulk-notebook', profile)
            bad = self.manifest()
            bad['backends']['qemu'] = {}
            with self.assertRaises(ValueError):
                bundle.prepared_usb_next(Path(directory), bad, 'rtl',
                                         'usb-next-bulk-notebook', bundle.USB_NEXT_PROFILE)
            inventory.assert_not_called()
        bad = self.manifest()
        bad['schema'] = bundle.SCHEMA_WITH_SOFTWARE_DEPLOYMENT
        with self.assertRaises(ValueError):
            bundle.bundle_configurations(bad)

    def test_schema4_original_digest_must_name_the_inventory_version(self):
        digest = 'a' * 64
        original = '/original/compiled/source.sv'
        m = self.manifest()
        m['origins'] = {original: {digest: 'backend-sources/' + digest}}
        m['files'] = {'backend-sources/' + digest: {'sha256': digest, 'bytes': 1, 'executable': False}}
        self.assertEqual(bundle.origin_destination(m, original, digest), 'backend-sources/' + digest)
        with self.assertRaises(ValueError):
            bundle.origin_destination(m, original, 'b' * 64)
        m['files']['backend-sources/' + digest]['sha256'] = 'b' * 64
        with self.assertRaises(ValueError):
            bundle.origin_destination(m, original, digest)


if __name__ == '__main__':
    unittest.main()
