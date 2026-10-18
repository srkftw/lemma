"""Host producer failures only; no RV64 or browser execution is inferred."""
from pathlib import Path
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def module(name):
    spec=importlib.util.spec_from_file_location('tci_'+name,ROOT/'tooling/lemmasim/tci'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class TciProducer(unittest.TestCase):
    def test_public_archive_checksum_rejects_before_extraction(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'source.tar').write_bytes(b'corrupted public source')
            with self.assertRaisesRegex(ValueError,'identity differs'):
                builder.acquire(dict(filename='source.tar',sha256='0'*64),p,p)

    def test_unsafe_archive_cannot_escape_source_root(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);archive=p/'bad.tar';out=p/'out';out.mkdir()
            with tarfile.open(archive,'w') as t:
                entry=tarfile.TarInfo('../escaped');entry.size=1;t.addfile(entry,io.BytesIO(b'x'))
            with self.assertRaises(tarfile.OutsideDestinationError):builder.extract(archive,out)
            self.assertFalse((p/'escaped').exists())

    def test_fresh_staging_floor_rejects_without_output(self):
        builder=module('build')
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)/'unused'
            with patch.object(builder.shutil,'disk_usage',return_value=type('Disk',(),dict(free=4*1024**3-1))()):
                with self.assertRaisesRegex(RuntimeError,'4GiB'):builder.build(type('Args',(),dict(work_dir=out))())
            self.assertFalse(out.exists())

    def test_other_qemu_version_does_not_mutate_sources(self):
        patcher=module('patch_wasm')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'VERSION').write_text('11.1.2\n');before={q.name:q.read_bytes() for q in p.iterdir()}
            with self.assertRaisesRegex(ValueError,'exact QEMU11.1.1'):patcher.apply(p,ROOT/'tooling/lemmasim/tci/lemma_browser_control.inc.c')
            self.assertEqual(before,{q.name:q.read_bytes() for q in p.iterdir()})

    def test_changed_first_upstream_anchor_rejects(self):
        patcher=module('patch_wasm')
        with tempfile.TemporaryDirectory() as name:
            p=Path(name);(p/'VERSION').write_text('11.1.1\n');(p/'meson.build').write_text('changed upstream input\n')
            with self.assertRaisesRegex(ValueError,'anchor differs: meson.build'):patcher.apply(p,ROOT/'tooling/lemmasim/tci/lemma_browser_control.inc.c')
            self.assertEqual((p/'meson.build').read_text(),'changed upstream input\n')

if __name__=='__main__':unittest.main()
