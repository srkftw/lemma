"""Host source admission and read-only imports; no guest execution claim."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_wasm import archived_build


class PortableSourceRecompilation(unittest.TestCase):
    def test_import_is_read_only_and_missing_sources_never_use_live_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);original=directory/'original';archive=directory/'wasm-sources'
            generator=archive/'scripts/silicon_profile.py';generator.parent.mkdir(parents=True)
            generator.write_text("def profile(name): return {'name':name}\n"
                                 "def constants(p): return {'entry':4096}\n")
            # This real file deliberately exists outside the archive. Its
            # bytes cannot supply an omitted original input.
            model=original/'model.sv';model.parent.mkdir();model.write_text('module original; endmodule\n')
            copied=archive/'model.sv';copied.write_bytes(model.read_bytes())
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            header='// Generated from the same authoritative binding as RTL and Lean.\n#pragma once\nconstexpr uint64_t BINDING_ENTRY = 4096ULL;\n'
            build={'profile':'lemma-silicon-dev/0.3.0','sha256':{str(model):sha(model)},
                   'configuration_includes':{},'verilator_runtime_inputs':{},
                   'host_binding_sha256':hashlib.sha256(header.encode()).hexdigest(),
                   'snapshot_identity':'a'*64}
            manifest={'wasm_project_root':str(original),'wasm_project_inputs':{
                name:{'path':'wasm-sources/'+name,'sha256':sha(archive/name)}
                for name in ('scripts/silicon_profile.py','model.sv')}}
            (directory/'wasm-build.json').write_text(json.dumps(build))
            def save(): (directory/'bundle.json').write_text(json.dumps(manifest))
            save();before={p.relative_to(directory):p.read_bytes() for p in directory.rglob('*') if p.is_file()}
            with patch('lemmasim_browser.validated_bundle',return_value=(directory,{})):
                _,resolve,actual,_=archived_build(directory,'lemma-silicon-dev/0.3.0')
                self.assertEqual(actual,header);self.assertEqual(resolve(model),copied)
                self.assertEqual({p.relative_to(directory):p.read_bytes() for p in directory.rglob('*') if p.is_file()},before)
                del manifest['wasm_project_inputs']['model.sv'];save()
                with self.assertRaisesRegex(ValueError,'Missing original portable input'):
                    archived_build(directory,'lemma-silicon-dev/0.3.0')
                self.assertEqual(model.read_text(),'module original; endmodule\n')
                with self.assertRaisesRegex(ValueError,'complete matching source bundle'):
                    archived_build(directory,'lemma-silicon-dev/0.4.0')


if __name__=='__main__':unittest.main()
