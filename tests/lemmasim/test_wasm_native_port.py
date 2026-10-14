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
            for profile in ('lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.14.0'):
                with self.subTest(profile=profile):
                    with self.assertRaisesRegex(ValueError,'Clocked13 only'):
                        silicon_wasm.archived_native_build('/unused','/unused',profile)

    def test_canonical_missing_archive_does_not_consult_current_profile(self):
        with mock.patch.object(silicon_guest,'profile',side_effect=AssertionError('mutable profile fallback')):
            with self.assertRaises(FileNotFoundError):
                silicon_wasm.archived_native_build('/nonexistent/canonical-native',
                    '/nonexistent/canonical-source','lemma-silicon-dev/0.3.0')

    def test_canonical_old_archive_rejects_before_source_validation(self):
        import check_native_evaluation
        with mock.patch.object(silicon_guest,'_read_unique_json',return_value={
                'schema':'lemma-original-native-component-archive/1'}), \
                mock.patch.object(check_native_evaluation,'original_native',side_effect=AssertionError('old source access')):
            with self.assertRaisesRegex(ValueError,'complete v2 native archive'):
                silicon_wasm.archived_native_build('/unused','/unused','lemma-silicon-dev/0.3.0')

    def test_missing_explicit_producer_does_not_consult_current_profile(self):
        with mock.patch.object(silicon_guest,'profile',side_effect=AssertionError('mutable profile fallback')):
            with self.assertRaises(FileNotFoundError):
                silicon_wasm.archived_native_build('/nonexistent/clocked-native','/nonexistent/clocked-source',
                                                  'lemma-silicon-dev/0.13.0')


if __name__=='__main__':unittest.main()
