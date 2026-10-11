"""Orchestration boundaries; fresh pinned Lean execution is checked separately."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
spec = importlib.util.spec_from_file_location('lemma_store_cache_check',
                                            ROOT / 'conformance/lemmasim/check_store_cache.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class StoreCacheDependencies(unittest.TestCase):
    def fixture(self, directory):
        root, output = directory / 'source', directory / 'output'
        root.mkdir()
        output.mkdir()
        store = root / 'Lemma/Services/Store'
        store.mkdir(parents=True)
        (store / 'Engine.lean').write_text('import Lemma.Services.Store.Index\n')
        (store / 'Index.lean').write_text('def indexVersion := 1\n')
        (root / 'lakefile.toml').write_text('name = "lemma"\n[[lean_lib]]\nname = "Lemma"\n')
        (root / 'lean-toolchain').write_text('leanprover/lean4:v4.34.1\n')
        old = root / '.lake/build/lib/lean/Lemma/Services/Store/Engine.olean'
        old.parent.mkdir(parents=True)
        old.write_bytes(b'old-object-must-not-be-reused')
        return root, output, old

    def emitted(self, output):
        store = output / 'dependencies/.lake/build/lib/lean/Lemma/Services/Store'
        store.mkdir(parents=True)
        for name in ('Engine', 'Index'):
            (store / (name + '.olean')).write_bytes(('fresh-' + name).encode())

    def test_private_build_does_not_reuse_or_modify_outer_lake_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output, old = self.fixture(Path(directory))
            inherited = {'LEAN_PATH': str(old.parent), 'LEAN_SRC_PATH': str(root), 'KEEP': 'value'}
            def build(argv, log, env):
                self.assertEqual(argv, ['lake', '--no-cache', '-d', str(output / 'dependencies'),
                                        'build', 'Lemma.Services.Store.Engine'])
                self.assertEqual(log, output / 'dependencies.log')
                self.assertEqual(env, {'KEEP': 'value'})
                self.emitted(output)
            with patch.object(checker, 'ROOT', root), patch.object(checker, 'command', side_effect=build) as run:
                lake, env, observed = checker.prepare_dependencies(output, inherited)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(lake[-1], str(output / 'dependencies'))
            self.assertEqual(env, {'KEEP': 'value'})
            self.assertEqual(set(observed['sources']), {'Lemma/Services/Store/Engine.lean',
                                                       'Lemma/Services/Store/Index.lean'})
            self.assertEqual(len(observed['objects']), 2)
            self.assertEqual(old.read_bytes(), b'old-object-must-not-be-reused')
            self.assertEqual(inherited['LEAN_PATH'], str(old.parent))

    def test_success_exit_without_actual_engine_object_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output, _ = self.fixture(Path(directory))
            with patch.object(checker, 'ROOT', root), patch.object(checker, 'command'):
                with self.assertRaisesRegex(ValueError, 'actual Engine object'):
                    checker.prepare_dependencies(output, {})

    def test_changed_copied_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output, _ = self.fixture(Path(directory))
            def altered(*_):
                self.emitted(output)
                (output / 'dependencies/Lemma/Services/Store/Index.lean').write_text('def indexVersion := 2\n')
            with patch.object(checker, 'ROOT', root), patch.object(checker, 'command', side_effect=altered):
                with self.assertRaisesRegex(ValueError, 'differs from maintained source'):
                    checker.prepare_dependencies(output, {})

    def test_reusing_private_outputs_is_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root, output, _ = self.fixture(Path(directory))
            (output / 'dependencies').mkdir()
            with patch.object(checker, 'ROOT', root), patch.object(checker, 'command') as run:
                with self.assertRaises(FileExistsError):
                    checker.prepare_dependencies(output, {})
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
