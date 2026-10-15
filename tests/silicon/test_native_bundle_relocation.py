"""Provenance-location transformations only, not synthetic machine acceptance."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from native_bundle_relocation import relocated_manifest


class NativeLocationAliases(unittest.TestCase):
    def fixture(self):
        return {'schema': 'lemmasim-native-bundle/3', 'profile': 'lemma-silicon-dev/0.3.0',
                'sources': {'sim/profiles/profile.json': 'a' * 64},
                'backends': {'qemu': {'sources': {'scripts/backend.py': 'b' * 64}},
                             'rtl': {'binary': {'path': 'runtime/rtl/machine', 'sha256': 'e' * 64}}},
                'files': {'source/profile.json': {'sha256': 'a' * 64},
                          'old/profile.json': {'sha256': 'c' * 64},
                          'source/backend.py': {'sha256': 'b' * 64}},
                'origins': {'/original/sim/profiles/profile.json': {'a' * 64: 'source/profile.json', 'c' * 64: 'old/profile.json'},
                            '/original/scripts/backend.py': {'b' * 64: 'source/backend.py'}}}

    def test_all_original_versions_and_non_location_fields_survive(self):
        original = self.fixture()
        before = copy.deepcopy(original)
        with tempfile.TemporaryDirectory() as directory:
            changed, aliases = relocated_manifest(original, directory)
            self.assertEqual(original, before)
            for key, value in before.items():
                if key != 'origins':
                    self.assertEqual(changed[key], value)
            for key, value in before['origins'].items():
                self.assertEqual(changed['origins'][key], value)
            self.assertEqual(aliases[str(Path(directory) / 'sim/profiles/profile.json')],
                             before['origins']['/original/sim/profiles/profile.json'])

    def test_uninventoried_or_missing_source_versions_reject(self):
        for mutation in ('missing', 'wrong-digest'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                original = self.fixture()
                if mutation == 'missing':
                    del original['origins']['/original/scripts/backend.py']
                else:
                    original['files']['source/backend.py']['sha256'] = 'd' * 64
                with self.assertRaises(ValueError):
                    relocated_manifest(original, directory)

    def test_unsupported_profile_and_traversal_reject(self):
        for mutation in ('profile', 'traversal'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                original = self.fixture()
                if mutation == 'profile':
                    original['profile'] = 'lemma-silicon-dev/0.13.0'
                else:
                    original['sources']['../escape'] = 'd' * 64
                with self.assertRaises(ValueError):
                    relocated_manifest(original, directory)


if __name__ == '__main__':
    unittest.main()
