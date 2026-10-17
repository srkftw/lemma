"""Explicit archived guest admission is separate from normal current sources."""
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import silicon_guest as guest

class GuestArchiveAdmission(unittest.TestCase):
    def test_only_declared_usb_guest_configurations_are_admitted(self):
        for profile,configuration in ((None,'lemmasim-silicon-usb-initialize'),
            ('lemma-silicon-dev/0.3.0','lemmasim-silicon-power-initialize'),
            ('lemma-silicon-dev/0.6.0','unknown'),('lemma-silicon-dev/0.7.0','lemmasim-silicon-product-notebook')):
            with self.assertRaisesRegex(ValueError,'only USB6'):
                guest.guest_source_archive('/missing','/missing',configuration,'O2',profile)

    def test_bound_guest_never_falls_back_to_current_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=root/'profile.json';profile.write_text('{}')
            def artifact(name,contents='{}'):
                p=root/name;p.write_text(contents);return guest.identified(p)
            entry={key:artifact('build.json' if key=='build' else key, '{"optimization":"O2"}' if key=='build' else '{}')
                   for key in ('image','build','provenance','audit','dtb','descriptor')}
            evidence={'schema':'lemma-explicit-guest-source-archive/1','inputs':244}
            entry['guest_source_archive']=evidence
            data={'schema_version':1,'profile':'lemma-silicon-dev/0.6.0','profile_sha256':guest.sha(profile),
                  **{key:artifact(key) for key in ('binary','rom','rom_audit','rtl_build')},'rtl_sources':{},'workloads':{'initializer':entry}}
            prepared=root/'prepared.json';prepared.write_text(json.dumps(data))
            with patch.object(guest,'prepared_path',return_value=prepared),patch.object(guest,'profile_path',return_value=profile),patch.object(guest,'guest_source_archive',return_value=evidence) as archive,patch.object(guest,'verify_guest_build') as current:
                with self.assertRaisesRegex(ValueError,'explicit --guest-source-root'):
                    guest.prepared('initializer',data['profile'])
                archive.assert_not_called();current.assert_not_called()
                self.assertEqual(guest.prepared('initializer',data['profile'],guest_source_root=root),data)
                archive.assert_called_once_with(root,root,'lemmasim-silicon-usb-initialize','O2',data['profile'])
                current.assert_not_called()
                archive.return_value={'schema':'wrong'}
                with self.assertRaisesRegex(ValueError,'identity changed'):
                    guest.prepared('initializer',data['profile'],guest_source_root=root)
                del entry['guest_source_archive'];prepared.write_text(json.dumps(data));current.reset_mock()
                self.assertEqual(guest.prepared('initializer',data['profile']),data)
                current.assert_called_once_with(root,'lemmasim-silicon-usb-initialize','O2')
if __name__=='__main__':unittest.main()
