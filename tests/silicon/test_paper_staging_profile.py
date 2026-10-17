import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import silicon_profile


class StagingProfile(unittest.TestCase):
    def test_historical_constants_and_lean_bindings_remain_exact(self):
        names = ('Binding', 'BindingFull', 'BindingPower', 'BindingSafety',
                 'BindingBLE', 'BindingUSB', 'BindingProduct')
        for minor, name in enumerate(names, 1):
            with self.subTest(minor=minor):
                p = silicon_profile.profile('lemma-silicon-dev/0.' + str(minor) + '.0')
                c = silicon_profile.constants(p)
                self.assertEqual((c['paper_version'], c['paper_stage_offset']), (1, 2048))
                self.assertEqual(silicon_profile.lean_text(p),
                                 (silicon_profile.ROOT / 'Lemma/Platform/Silicon' / (name + '.lean')).read_text())

    def test_complete_modern_window_is_disjoint_from_active_neighbors(self):
        for minor, abi, features in ((8, 9, 15), (9, 10, 31)):
            with self.subTest(minor=minor):
                p = silicon_profile.profile('lemma-silicon-dev/0.' + str(minor) + '.0')
                c = silicon_profile.constants(p)
                self.assertEqual((c['paper_version'], c['paper_stage_offset']), (2, 3584))
                self.assertEqual((p['descriptor']['abi'], p['descriptor_features']), (abi, features))
                begin = c['paper_base'] + c['paper_stage_offset']
                end = begin + 512
                self.assertEqual(end, c['paper_base'] + c['paper_span'])
                for device in ('ble', 'usb', 'pen', 'boot_nv'):
                    if not c.get(device + '_span', 0):
                        continue
                    a, b = c[device + '_base'], c[device + '_base'] + c[device + '_span']
                    self.assertTrue(end <= a or b <= begin, device + ' overlaps staged bytes')
                self.assertEqual((c['ble_payload_max'], c['usb_payload_max'], c['pen_fifo']), (27, 64, 256))

    def test_incompatible_modern_stage_or_descriptor_is_rejected(self):
        original = silicon_profile.profile('lemma-silicon-dev/0.8.0')
        mutations = [('paper_stage_offset', 2048), ('paper_stage_offset', 3585),
                     ('paper_stage_offset', 4096), ('paper_version', 1)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'binding.json'
            for key, value in mutations:
                data = copy.deepcopy(original)
                data[key] = value
                path.write_text(json.dumps(data))
                with self.subTest(key=key, value=value), patch.object(silicon_profile, 'USB_NEXT_PROFILE', path):
                    with self.assertRaises(ValueError):
                        silicon_profile.profile('lemma-silicon-dev/0.8.0')
            data = copy.deepcopy(original)
            data['descriptor']['abi'] = 7
            path.write_text(json.dumps(data))
            with patch.object(silicon_profile, 'USB_NEXT_PROFILE', path):
                with self.assertRaises(ValueError):
                    silicon_profile.profile('lemma-silicon-dev/0.8.0')


if __name__ == '__main__':
    unittest.main()
