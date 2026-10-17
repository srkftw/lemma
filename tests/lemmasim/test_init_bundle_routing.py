"""Actual CLI dispatch and fail-before-media boundaries; no guest fixture."""
from pathlib import Path
import os
import runpy
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class InitializationRouting(unittest.TestCase):
    def test_explicit_bundle_uses_matched_initializer_without_profile(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/lemmasim'))
        matched, legacy = Mock(), Mock()
        argv = ['lemmasim', 'init', '--native-bundle', '/declared/bundle',
                '--disk', '/declared/new.raw']
        with patch.object(sys, 'argv', argv), patch.dict(sys.modules, {
                'lemmasim_session': SimpleNamespace(initialize=matched)}), \
                patch.dict(namespace['main'].__globals__, initialize=legacy):
            self.assertEqual(namespace['main'](), 0)
        legacy.assert_not_called()
        matched.assert_called_once()
        args = matched.call_args.args[0]
        self.assertEqual(args.native_bundle, Path('/declared/bundle'))
        self.assertIsNone(args.profile)
        self.assertEqual(args.backend, 'qemu')

    def test_historical_default_still_uses_its_declared_initializer(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/lemmasim'))
        matched, legacy = Mock(), Mock()
        with patch.object(sys, 'argv', ['lemmasim', 'init', '--disk', '/declared/new.raw']), \
                patch.dict(sys.modules, {'lemmasim_session': SimpleNamespace(initialize=matched)}), \
                patch.dict(namespace['main'].__globals__, initialize=legacy):
            self.assertEqual(namespace['main'](), 0)
        legacy.assert_called_once()
        matched.assert_not_called()

    def test_missing_explicit_bundle_cannot_fallback_or_create_media(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            disk, session = root / 'new.raw', root / 'initializer'
            process = subprocess.Popen([str(ROOT / 'scripts/lemmasim'), 'init',
                '--native-bundle', str(root / 'missing'), '--disk', str(disk),
                '--session-dir', str(session), '--timeout', '3'], cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True)
            try:
                out, err = process.communicate(timeout=5)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, 0, out + err)
            self.assertFalse(disk.exists(), 'Bad explicit bundle created user media')
            self.assertFalse(session.exists(), 'Bad explicit bundle started a session')
            self.assertNotIn('Guest acknowledged', out)


if __name__ == '__main__':
    unittest.main()
