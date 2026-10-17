"""Host archive isolation checks; inert fixtures never represent target boot."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import product_bundle as bundle


class ProductBundle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'bundle'
        self.root.mkdir()
        self.data = {'native_build': '/unavailable/original/native',
                     'native_source_archive': '/unavailable/original/native-source',
                     'rom_build': '/unavailable/original/rom',
                     'rom_source_archive': '/unavailable/original/rom-source',
                     'authentication': 'fixture public development key only'}
        names = ['run.py', 'components/prepared.json', 'host/scripts/lemmasim_auth.py',
                 *('components/' + name for name in bundle.PREPARED_FILES)]
        files = {}
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.data) if name.endswith('prepared.json') else 'inert fixture')
            files[name] = bundle.sha(path)
        self.manifest = {'schema': bundle.SCHEMA, 'user_media_included': False, 'files': files}
        self.seal()

    def seal(self):
        (self.root / 'bundle.json').write_text(json.dumps(self.manifest))

    def test_relocation_changes_only_four_paths_without_editing_original(self):
        moved = self.root.with_name('relocated')
        self.root.rename(moved)
        before = {str(p.relative_to(moved)): bundle.sha(p) for p in moved.rglob('*') if p.is_file()}
        with bundle.relocated(moved) as prepared:
            data = json.loads((prepared / 'prepared.json').read_text())
            self.assertEqual(data['native_build'], str(moved / 'components/native'))
            self.assertEqual(data['rom_source_archive'], str(moved / 'components/rom-source/consumed-source-root'))
            self.assertEqual(data['authentication'], self.data['authentication'])
            self.assertEqual((prepared / 'descriptor.bin').read_text(), 'inert fixture')
        self.assertFalse(prepared.exists())
        self.assertEqual(before, {str(p.relative_to(moved)): bundle.sha(p) for p in moved.rglob('*') if p.is_file()})

    def test_changed_file_and_unindexed_code_reject(self):
        target = self.root / 'host/scripts/lemmasim_auth.py'
        target.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed'): bundle.verify(self.root)
        target.write_text('inert fixture')
        extra = self.root / 'host/scripts/unindexed.py'
        extra.write_text('unindexed')
        with self.assertRaisesRegex(ValueError, 'unindexed'): bundle.verify(self.root)

    def test_removed_index_entry_does_not_allow_unverified_code(self):
        del self.manifest['files']['host/scripts/lemmasim_auth.py']
        self.seal()
        with self.assertRaisesRegex(ValueError, 'unindexed'): bundle.verify(self.root)

    def test_traversal_and_symlinked_component_reject(self):
        self.manifest['files']['../private-medium'] = '0' * 64
        self.seal()
        with self.assertRaisesRegex(ValueError, 'invalid'): bundle.verify(self.root)
        del self.manifest['files']['../private-medium']
        self.seal()
        path = self.root / 'components/descriptor.bin'
        path.unlink()
        path.symlink_to(self.root / 'run.py')
        with self.assertRaisesRegex(ValueError, 'symlinked'): bundle.verify(self.root)


if __name__ == '__main__':
    unittest.main()
