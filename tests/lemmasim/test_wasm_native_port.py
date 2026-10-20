"""Portable producer admission scope, separate from actual state continuation."""
from pathlib import Path
import sys
import unittest
from unittest import mock
import copy
import hashlib
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest
import silicon_wasm


class NativePortableAdmission(unittest.TestCase):
    def test_unqualified_profiles_reject_before_native_inputs_or_build(self):
        with mock.patch.object(silicon_guest,'native_source_archive',side_effect=AssertionError('input access')) as inputs:
            for profile in ('lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.14.0'):
                with self.subTest(profile=profile):
                    with self.assertRaisesRegex(ValueError,'Native-to-portable source admission'):
                        silicon_wasm.archived_native_build('/unused','/unused',profile)
            inputs.assert_not_called()

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


class RelocatedClockedPort(unittest.TestCase):
    """Path binding after native admission; inert sources are never executed."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.old=self.base/'absent-original';self.current=self.base/'current'
        self.current.mkdir();self.archive=self.base/'archive/source';self.archive.mkdir(parents=True)
        content={'sim/rtl/lemma_soc.sv':b'inert top fixture','custom/cvw/src/cvw.sv':b'inert core fixture',
            'custom/cvw/config/shared/config.vh':b'configuration fixture','generated/lemma_silicon_binding.h':b'header fixture',
            'sim/rtl/host/machine_runtime.cpp':b'host fixture','flake.lock':b'lock fixture','scripts/silicon_profile.py':b'generator fixture'}
        self.hashes={name:hashlib.sha256(raw).hexdigest()for name,raw in content.items()}
        for name,raw in content.items():
            p=self.archive/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.manifest={'top':'lemma_soc','sources':[str(self.old/name)for name in ('sim/rtl/lemma_soc.sv','custom/cvw/src/cvw.sv')],
            'include_dirs':[str(self.old/'custom/cvw/config/shared')],
            'host_include_dir':str(self.old/'generated'),'host_binding_sha256':self.hashes['generated/lemma_silicon_binding.h'],
            'sha256':{str(self.old/name):self.hashes[name]for name in ('sim/rtl/lemma_soc.sv','custom/cvw/src/cvw.sv')},
            'configuration_includes':{str(self.old/'custom/cvw/config/shared/config.vh'):self.hashes['custom/cvw/config/shared/config.vh']},
            'host_runtime':{str(self.old/'sim/rtl/host/machine_runtime.cpp'):self.hashes['sim/rtl/host/machine_runtime.cpp']},
            'host_toolchain_inputs':{'flake.lock':self.hashes['flake.lock']},
            'binding_generator_inputs':{'scripts/silicon_profile.py':self.hashes['scripts/silicon_profile.py']},
            'snapshot_identity':'1'*64}
        self.inputs={str(self.old/name):h for name,h in self.hashes.items()}
        self.root=mock.patch.object(silicon_wasm,'ROOT',self.current);self.root.start();self.addCleanup(self.root.stop)

    def admit(self):
        with mock.patch.object(silicon_guest,'native_source_archive',return_value=(self.manifest,self.inputs,{'fixture':'already admitted'})):
            return silicon_wasm.archived_native_build(self.base/'build',self.archive,'lemma-silicon-dev/0.13.0')

    def test_explicit_aliases_do_not_mutate_original_or_read_old_checkout(self):
        before=copy.deepcopy(self.manifest);m,resolve,header,e=self.admit()
        self.assertFalse(self.old.exists());self.assertEqual(self.manifest,before)
        self.assertEqual(header,'header fixture');self.assertEqual(e['schema'],'lemma-wasm-native-source-port/2')
        self.assertEqual(e['original_repository_root'],str(self.old))
        self.assertEqual(m['host_runtime'],{'sim/rtl/host/machine_runtime.cpp':self.hashes['sim/rtl/host/machine_runtime.cpp']})
        for name in m['sources']:
            self.assertTrue(Path(name).is_relative_to(self.current))
            self.assertTrue(resolve(name).is_relative_to(self.archive))

    def test_missing_archive_header_cannot_fall_back_to_current_shadow(self):
        name='generated/lemma_silicon_binding.h';shadow=self.current/name;shadow.parent.mkdir();shadow.write_bytes((self.archive/name).read_bytes())
        (self.archive/name).unlink()
        with self.assertRaises(FileNotFoundError):self.admit()

    def test_include_directory_cannot_escape_the_original_prefix(self):
        self.manifest['include_dirs']=[str(self.base/'outside')]
        with self.assertRaisesRegex(ValueError,'Unarchived native portable input'):self.admit()


if __name__=='__main__':unittest.main()
