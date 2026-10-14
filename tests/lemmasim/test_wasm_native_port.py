"""Portable producer admission scope, separate from actual state continuation."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest
import silicon_wasm


class NativePortableAdmission(unittest.TestCase):
    def test_unqualified_profiles_reject_before_native_inputs_or_build(self):
        with mock.patch.object(silicon_guest,'native_source_archive',side_effect=AssertionError('input access')):
            for profile in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.14.0'):
                with self.subTest(profile=profile):
                    with self.assertRaisesRegex(ValueError,'Clocked13 only'):
                        silicon_wasm.archived_native_build('/unused','/unused',profile)

    def test_missing_explicit_producer_does_not_consult_current_profile(self):
        with mock.patch.object(silicon_guest,'profile',side_effect=AssertionError('mutable profile fallback')):
            with self.assertRaises(FileNotFoundError):
                silicon_wasm.archived_native_build('/nonexistent/clocked-native','/nonexistent/clocked-source',
                                                  'lemma-silicon-dev/0.13.0')


if __name__=='__main__':unittest.main()
