"""Host patch/admission controls. They do not establish CPU/guest execution."""
from pathlib import Path
import importlib.util,tempfile,unittest,json,hashlib,difflib
ROOT=Path(__file__).resolve().parents[2]
def module():
    spec=importlib.util.spec_from_file_location('tci_helpers',ROOT/'tooling/lemmasim/tci/patch_tci_helpers.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class TypedHelperPatch(unittest.TestCase):
    def fixture(self,root):
        m=module();source=root/'source';source.mkdir();(source/'VERSION').write_text('11.1.1\n');tools=root/'tools';tools.mkdir();m.HERE=tools
        patch=[];sources={}
        for name in ['first.h','last.c']:
            before='/* metadata-only fixture before '+name+' */\n';after=before+'/* fixture after */\n';(source/name).write_text(before);patch+=difflib.unified_diff(before.splitlines(True),after.splitlines(True),'a/'+name,'b/'+name);sources[name]={'before':hashlib.sha256(before.encode()).hexdigest(),'after':hashlib.sha256(after.encode()).hexdigest()}
        p=tools/'tci-typed-helpers.patch';p.write_text(''.join(patch));(tools/'typed_helpers.json').write_text(json.dumps({'patch_sha256':m.sha(p),'sources':sources}));return m,source,tools
    def test_exact_fixture_patch_is_real_filesystem_operation(self):
        with tempfile.TemporaryDirectory() as name:
            m,source,tools=self.fixture(Path(name));result=m.apply(source)
            for rel,value in result['sources'].items():self.assertEqual(m.sha(source/rel),value['after'])
    def test_late_source_corruption_rejects_before_first_mutation(self):
        with tempfile.TemporaryDirectory() as name:
            m,source,tools=self.fixture(Path(name));(source/'last.c').write_text('corrupt');before={p.name:p.read_bytes() for p in source.iterdir()}
            with self.assertRaisesRegex(ValueError,'before any mutation'):m.apply(source)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
    def test_changed_patch_rejects_before_source_mutation(self):
        with tempfile.TemporaryDirectory() as name:
            m,source,tools=self.fixture(Path(name));(tools/'tci-typed-helpers.patch').write_text('corrupt');before={p.name:p.read_bytes() for p in source.iterdir()}
            with self.assertRaisesRegex(ValueError,'patch identity differs'):m.apply(source)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
    def test_wrong_version_rejects_before_source_mutation(self):
        with tempfile.TemporaryDirectory() as name:
            m,source,tools=self.fixture(Path(name));(source/'VERSION').write_text('11.1.2\n');before={p.name:p.read_bytes() for p in source.iterdir()}
            with self.assertRaisesRegex(ValueError,'Exact QEMU11.1.1'):m.apply(source)
            self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
if __name__=='__main__':unittest.main()
