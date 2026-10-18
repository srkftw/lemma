"""The public QEMU commands must preserve explicit target production controls."""
import importlib.machinery
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_fast


class CapturedBuild(Exception):
    pass


class BuildOptionForwarding(unittest.TestCase):
    def test_native_qemu_build_forwards_explicit_action_options(self):
        launcher = importlib.machinery.SourceFileLoader('lemmasim_cache_options', str(ROOT / 'scripts/lemmasim')).load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / 'build/lemmasim/qemu/bin/qemu-system-riscv64'
            binary.parent.mkdir(parents=True); binary.write_bytes(b'launcher fixture')
            commands = []
            def command(argv, timeout):
                if 'scripts/build_kernel.py' in argv:
                    commands.append(argv); raise CapturedBuild()
            args = SimpleNamespace(opt_level='O2', fresh=True, cache_dir=root/'cache')
            with patch.object(launcher, 'ROOT', root), patch.object(launcher, 'source_identity', return_value={'source_commit':'fixture', 'source_clean':True}), \
                    patch.object(launcher, 'backend_identity', return_value={'binary':{'path':str(binary)}}), patch.object(launcher, 'run_command', side_effect=command):
                with self.assertRaises(CapturedBuild):launcher.build(args)
            self.assertIn('--fresh', commands[0])
            self.assertEqual(commands[0][commands[0].index('--cache-dir')+1], str(root/'cache'))

    def test_matched_fast_qemu_build_forwards_explicit_action_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root/'build/lemmasim/qemu-fast-0.3.0'
            binary = output/'bin/qemu-system-riscv64'
            binary.parent.mkdir(parents=True);binary.write_bytes(b'matched fixture')
            commands = []
            def command(argv, **kwargs):
                if 'scripts/build_kernel.py' in argv:
                    commands.append(argv);raise CapturedBuild()
            args = SimpleNamespace(profile='lemma-silicon-dev/0.3.0',workload='notebook',
                                   guest_build=None,opt_level='O2',fresh=True,cache_dir=root/'cache')
            with patch.object(lemmasim_fast, 'ROOT', root), patch.object(lemmasim_fast, 'sources', return_value={'fixture':'fixed'}), \
                    patch.object(lemmasim_fast.guest, 'run_command', side_effect=command), \
                    patch.object(lemmasim_fast.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps({'output':str(output),'derivation':str(root/'fixture.drv')}))):
                with self.assertRaises(CapturedBuild):lemmasim_fast.build(args)
            self.assertIn('--fresh', commands[0])
            self.assertEqual(commands[0][commands[0].index('--cache-dir')+1], root/'cache')


if __name__ == '__main__':
    unittest.main()
