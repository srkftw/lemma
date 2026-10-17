"""Local component selection; these inert fixtures are never target images."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from product_archive import create


class ProductArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'prepared'
        self.source.mkdir(); self.output = self.root / 'archive'
        self.data = {'profile': 'fixture', 'runtime_identity': 'fixture', 'rom_sha256': 'fixture'}
        for role in ('native', 'rom'):
            build = self.root / role; build.mkdir()
            self.data[role + '_build'] = str(build)
            archive = self.root / (role + '-source/consumed-source-root'); archive.mkdir(parents=True)
            self.data[role + '_source_archive'] = str(archive)
            (archive / 'source.lean').write_text('inert fixture')
            (archive.parent / 'consumed-source-archive.json').write_text(json.dumps({'inputs': {'source.lean': 'fixture'}}))
        for role, names in [('native', ['build.json', 'obj/lemma-rtl', 'generated/lemma_runtime_identity.h']),
                            ('rom', ['build.json', 'component/rom.bin'])]:
            for name in names:
                path = Path(self.data[role + '_build']) / name
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text('inert fixture')
        for name in ('prepared.json', 'discovery.dts', 'discovery.dtb', 'descriptor.bin', 'DEPENDENCIES.txt'):
            (self.source / name).write_text(json.dumps(self.data) if name == 'prepared.json' else 'fixture')
        self.validations = []

    def validate(self, path):
        self.validations.append(path)
        return json.loads((path / 'prepared.json').read_text()), {}, {'manifest': {'artifacts': {'component/rom.bin': 'fixture'}}}

    def test_only_declared_components_and_no_neighbor_media_are_copied(self):
        (Path(self.data['rom_build']) / 'user-notebook.raw').write_bytes(b'user media')
        (self.source / 'boot.raw').write_bytes(b'private boot media')
        result = create(self.source, self.output, self.validate)
        self.assertEqual(self.validations, [self.source, self.output])
        self.assertFalse(result['user_media_included'])
        self.assertFalse(any(p.name in ('boot.raw', 'user-notebook.raw') for p in self.output.rglob('*')))
        relocated = json.loads((self.output / 'prepared.json').read_text())
        self.assertEqual(relocated['native_build'], str(self.output / 'native'))
        self.assertEqual((self.output / 'native/obj/lemma-rtl').stat().st_mode & 0o777, 0o755)

    def test_existing_output_and_missing_consumed_archive_fail_before_copy(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'Unused'): create(self.source, self.output, self.validate)
        self.output.rmdir(); self.data['native_source_archive'] = None
        (self.source / 'prepared.json').write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'both complete'): create(self.source, self.output, self.validate)
        self.assertFalse(self.output.exists())

    def test_symlink_cannot_add_an_undeclared_source(self):
        path = Path(self.data['rom_source_archive']) / 'source.lean'
        path.unlink(); path.symlink_to(self.source / 'boot.raw')
        (self.source / 'boot.raw').write_bytes(b'private media')
        with self.assertRaisesRegex(ValueError, 'Invalid/duplicate'): create(self.source, self.output, self.validate)
        self.assertFalse(self.output.exists())


if __name__ == '__main__': unittest.main()
