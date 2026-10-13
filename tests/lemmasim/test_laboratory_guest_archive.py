"""Archive admission failures/forwarding; no synthetic positive guest claim."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest_bundle as bundle

CONFIG='lemmasim-silicon-array-arithmetic-oom-development'
STRING_CONFIG='lemmasim-silicon-string-arithmetic-oom-development'
PROFILE='lemma-silicon-dev/0.3.0'

class LaboratoryArchiveBoundary(unittest.TestCase):
    def test_scope_rejects_ordinary_modes_other_profiles_and_other_guest_before_io(self):
        for profile,configuration,mode in [(PROFILE,CONFIG,'student'),(PROFILE,CONFIG,'developer'),
            (PROFILE,CONFIG,None),('lemma-silicon-dev/0.2.0',CONFIG,'laboratory'),
            ('lemma-silicon-dev/0.8.0',CONFIG,'laboratory'),
            (PROFILE,'lemmasim-silicon-bytes-arithmetic-oom-development','laboratory')]:
            with self.subTest(profile=profile,configuration=configuration,mode=mode),self.assertRaisesRegex(ValueError,'canonical Laboratory Array OOM'):
                bundle.laboratory_guest_archive('/missing','/missing',profile,configuration,mode)

    def test_string_archive_requires_same_canonical_laboratory_boundaries_before_io(self):
        for profile,mode in [(PROFILE,'student'),(PROFILE,'developer'),(PROFILE,None),
                             ('lemma-silicon-dev/0.2.0','laboratory'),
                             ('lemma-silicon-dev/0.8.0','laboratory')]:
            with self.subTest(profile=profile,mode=mode),self.assertRaisesRegex(ValueError,'canonical Laboratory'):
                bundle.laboratory_guest_archive('/missing','/missing',profile,STRING_CONFIG,mode)
        with self.assertRaises(FileNotFoundError):
            bundle.laboratory_guest_archive('/missing','/missing',PROFILE,STRING_CONFIG,'laboratory')

    def test_missing_corrupt_unlisted_and_mismatched_archive_fail_before_tool_artifact_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);base=root/'build';base.mkdir();archive=root/'archive';archive.mkdir()
            contents=b'original source';digest=hashlib.sha256(contents).hexdigest()
            expected={'Lemma.lean':digest}
            for name,data in [('provenance.json',{'source_inputs':expected}),('build.json',{}),('audit.json',{})]:
                (base/name).write_text(json.dumps(data))
            def rejected(message):
                with self.assertRaisesRegex((ValueError,FileNotFoundError),message):
                    bundle.laboratory_guest_archive(base,archive,PROFILE,CONFIG,'laboratory')
            rejected('source-inputs')
            (archive/'source-inputs.json').write_text(json.dumps(expected));rejected('missing or unlisted')
            (archive/'Lemma.lean').write_bytes(b'corrupt');rejected('input changed')
            (archive/'Lemma.lean').write_bytes(contents);(archive/'extra').write_text('unlisted');rejected('missing or unlisted')
            (archive/'extra').unlink();(archive/'source-inputs.json').write_text('{}');rejected('original consumed inventory')
            (archive/'source-inputs.json').write_text(json.dumps(expected))
            (archive/'Lemma.lean').unlink();(archive/'Lemma.lean').symlink_to('/dev/null');rejected('Symlink')

    def test_native_constructors_forward_only_explicit_archive_without_spawning(self):
        import lemmasim_session,lemmasim_fast
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            for implementation,backend in [(lemmasim_session.RTL,'rtl'),(lemmasim_fast.Fast,'qemu')]:
                for source in (None,directory/'archive'):
                    args=SimpleNamespace(native_bundle=directory/'bundle',guest_build=directory/'guest',
                        guest_source_root=source,workload='notebook',profile=PROFILE,mode='laboratory')
                    data={'profile':PROFILE}
                    with patch.object(bundle,'prepared',return_value=data) as prepared,patch.object(bundle,'development_guest',side_effect=ValueError('stop before machine launch')) as override:
                        with self.assertRaisesRegex(ValueError,'stop before machine launch'):
                            implementation(args,directory)
                        prepared.assert_called_once_with(args.native_bundle,backend,'notebook',PROFILE)
                        expected={} if source is None else {'source_root':source}
                        override.assert_called_once_with(data,'notebook',directory,args.guest_build,'laboratory',**expected)

    def test_new_archive_path_bound_is_serializable_without_changing_its_admission_type(self):
        from check_arithmetic_isolation import IsolationChecker,MathChecker
        args=SimpleNamespace(guest_source_root=Path('/original/archive'),case='oom',
            require_managed_constructor=False,require_sums_constructor=False,require_array_payload=True)
        def existing(checker,args):
            checker.report={'bounds':{'guest_source_root':args.guest_source_root},'observer_sources':{}}
        with patch.object(MathChecker,'__init__',existing):
            checker=IsolationChecker(args)
            self.assertEqual(checker.report['bounds']['guest_source_root'],'/original/archive')
            self.assertIsInstance(args.guest_source_root,Path)
            json.dumps(checker.report)

class CanonicalArchiveBoundary(unittest.TestCase):
    def test_other_profile_or_role_cannot_reach_archive_io(self):
        for profile,role in [('lemma-silicon-dev/0.8.0','notebook'),
                             (PROFILE,'service'),(PROFILE,'initializer-any')]:
            with self.subTest(profile=profile,role=role),self.assertRaisesRegex(ValueError,'profile0.3 notebook or initializer'):
                bundle.canonical_guest_archive('/missing','/missing',profile,role)

    def test_failure_guest_wrong_role_and_freeform_configuration_reject_before_source_io(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            for config in (CONFIG,STRING_CONFIG,'lemmasim-silicon-array-bulk-initialize',
                           'lemmasim-silicon-array-bulk-notebook-any'):
                (base/'build.json').write_text(json.dumps({'configuration':config}))
                with self.subTest(configuration=config),self.assertRaisesRegex(ValueError,'exact ordinary deployment role'):
                    bundle.canonical_guest_archive(base,'/missing',PROFILE,'notebook')

    def test_admitted_normal_role_still_requires_original_complete_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)/'guest';base.mkdir()
            (base/'build.json').write_text(json.dumps({'configuration':'lemmasim-silicon-array-bulk-notebook'}))
            (base/'audit.json').write_text('{}')
            (base/'provenance.json').write_text(json.dumps({'source_inputs':{'Lemma.lean':'0'*64}}))
            with self.assertRaisesRegex(ValueError,'original consumed inventory'):
                bundle.canonical_guest_archive(base,'/missing',PROFILE,'notebook')

if __name__=='__main__':unittest.main()
