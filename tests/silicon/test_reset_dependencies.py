"""ROM recipe dependencies include the real process runner and lease worker."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from action_cache import ActionCache
import silicon_reset_rom as rom
from core0_common import Core0Error


class ResetHostDependencyTests(unittest.TestCase):
    def fixture(self, root):
        files = {'lakefile.toml':'name = "fixture"\n', 'lake-manifest.json':'{"packages": []}',
                 'lean-toolchain':'fixture', rom.SOURCE:'import Lean\nimport Lemma.Machine.Primitives\n',
                 'Lemma/Machine/Primitives.lean':'namespace Fixture\nend Fixture\n',
                 'selected.json':'{"profile":"fixture"}'}
        files.update({name:'fixture source '+name for name in rom.HOST_INPUTS})
        for name, contents in files.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
        return rom.source_inputs(root, root/'selected.json')

    def test_runner_and_worker_mutation_cannot_reuse_prior_rom_action(self):
        for helper in ('scripts/core0_common.py', 'scripts/action_worker.py'):
            with self.subTest(helper=helper), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);inputs=self.fixture(root);calls=[]
                cache=ActionCache(root);output=root/'result'
                def producer(workspace):
                    calls.append(True)
                    # This is a dependency/admission fixture, not ROM compilation.
                    payload=b''.join(path.read_bytes() for _,path in sorted(workspace.inputs.items()))
                    workspace.outputs['payload'].write_bytes(hashlib.sha256(payload).digest())
                    return {'scope':'host dependency fixture; no target production'}
                request={'schema':'reset-host-dependency-fixture/1'}
                first=cache.run(request,inputs,{'payload':output},producer)
                warm=cache.run(request,inputs,{'payload':output},producer)
                self.assertEqual(warm['status'],'reused');self.assertEqual(len(calls),1)
                (root/helper).write_text('changed consumed process implementation')
                changed=cache.run(request,inputs,{'payload':output},producer)
                self.assertEqual(changed['status'],'fresh');self.assertEqual(len(calls),2)
                self.assertNotEqual(first['action_key'],changed['action_key'])

    def test_foreign_or_edited_loaded_host_source_rejects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=self.fixture(root)
            with self.assertRaisesRegex(Core0Error,'changed after import'):
                rom.validate_loaded_sources(inputs)


if __name__ == '__main__':
    unittest.main()
