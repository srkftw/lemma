"""Host preparation authority boundaries; these do not claim guest execution."""
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest as guest

class NativeArchiveAdmission(unittest.TestCase):
    def test_only_explicit_usb_archive_is_admitted(self):
        for profile in (None,'lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.5.0','lemma-silicon-dev/0.7.0'):
            with self.assertRaisesRegex(ValueError,'only USB6'):
                guest.native_source_archive(Path('/missing'),Path('/missing'),profile)

    def test_duplicate_metadata_and_escaping_source_paths_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'metadata.json';p.write_text('{"schema":1,"schema":2}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                guest._read_unique_json(p)
        for path in ('../escape','a/../../escape','/outside/escape',''):
            with self.assertRaises(ValueError):guest._native_relative(path)

    def test_preparation_requires_bound_explicit_archive_and_preserves_current_guest_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile.json';profile.write_text('{}')
            def artifact(name):
                p=root/name;p.write_text('{}');return guest.identified(p)
            entry={key:artifact('build.json' if key=='build' else key) for key in ('image','build','provenance','audit','dtb','descriptor')}
            Path(entry['build']['path']).write_text('{"optimization":"O2"}')
            entry['build']=guest.identified(entry['build']['path'])
            original=root/'changed-source';original.write_bytes(b'original')
            sources={str(original):guest.sha(original)}
            evidence={'schema':'lemma-explicit-rtl-source-archive/1','inputs':1}
            data={'schema_version':1,'profile':'lemma-silicon-dev/0.6.0','profile_sha256':guest.sha(profile),
                  **{key:artifact(key) for key in ('binary','rom','rom_audit','rtl_build')},
                  'rtl_sources':sources,'rtl_source_archive':evidence,'workloads':{'initializer':entry}}
            prepared=root/'prepared.json';prepared.write_text(json.dumps(data));original.write_bytes(b'changed')
            with patch.object(guest,'prepared_path',return_value=prepared),patch.object(guest,'profile_path',return_value=profile),patch.object(guest,'native_source_archive',return_value=({},sources,evidence)) as native,patch.object(guest,'verify_guest_build') as target:
                with self.assertRaisesRegex(ValueError,'explicit --rtl-source-root'):
                    guest.prepared('initializer',data['profile'])
                native.assert_not_called();target.assert_not_called()
                self.assertEqual(guest.prepared('initializer',data['profile'],rtl_source_root=root),data)
                # No archived source root is passed to the target checker: only
                # the exact native backend is archived; the new guest is current.
                target.assert_called_once_with(root,'lemmasim-silicon-usb-initialize','O2')
                native.return_value=({},sources,{'schema':'wrong'})
                with self.assertRaisesRegex(ValueError,'identity changed'):
                    guest.prepared('initializer',data['profile'],rtl_source_root=root)
                del data['rtl_source_archive'];prepared.write_text(json.dumps(data));target.reset_mock()
                with self.assertRaisesRegex(ValueError,'source/dependency changed'):
                    guest.prepared('initializer',data['profile'])
                target.assert_not_called()

if __name__=='__main__':unittest.main()
