"""Host ownership/fault cleanup checks; these do not qualify guest execution."""
import hashlib
import json
import os
from pathlib import Path
import resource
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import lemmasim_file_limit as fault


class NativeFileLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        medium = self.directory / 'private.raw'
        medium.write_bytes(bytes(512))
        binary = Path('/proc/self/exe').resolve()
        self.manifest = {'mode': 'laboratory', 'backend': 'rtl',
                         'pid': os.getpid(), 'argv': [str(binary)]}
        self.write_manifest()
        self.native = fault.identity(os.getpid())
        self.observed = {'running': False, 'capture_uncertain': False,
                         'external_adapters': {},
                         'identity': {'profile': 'lemma-silicon-dev/0.3.0',
                                      'runtime': hashlib.sha256(binary.read_bytes()).hexdigest()},
                         'machine': {'cycle': 17, 'isolated_medium': True,
                                     'private_medium_path': str(medium),
                                     'snapshot_identity': '600e93eb1981b3eb5432840c0fd8e169b4d5cfd04f89e8164450d1c70b159bba'}}
        # Only the RPC observations/descendant inventory are synthetic. The
        # actual ownership, executable, file and process-start checks still run.
        self.addCleanup(patch.stopall)
        patch.object(fault, 'request', return_value=self.observed).start()
        patch.object(fault, 'descendants', return_value=[self.native]).start()

    def write_manifest(self):
        (self.directory / 'session.json').write_text(json.dumps(self.manifest))

    def token(self):
        return {'schema': 'lemma-native-file-limit/1', 'session': str(self.directory),
                'native': self.native, 'previous': [-1, -1], 'applied_soft': 64}

    def test_capture_uncertainty_blocks_new_fault_but_allows_cleanup(self):
        self.observed['capture_uncertain'] = True
        with self.assertRaisesRegex(ValueError, 'certain live backing'):
            fault.owned_native(self.directory)
        self.assertEqual(fault.owned_native(self.directory, restoring=True)[1], self.native)

    def test_replay_rejected_before_limit_or_token_mutation(self):
        self.manifest['argv'].extend(['--backing-replay', 'copied.io'])
        self.write_manifest()
        with patch.object(resource, 'prlimit') as syscall:
            with self.assertRaisesRegex(ValueError, 'outcome replay'):
                fault.apply(self.directory, 64, self.directory / 'token.json')
            syscall.assert_not_called()
        self.assertFalse((self.directory / 'token.json').exists())

    def test_symlinked_private_backing_is_rejected_before_resolution(self):
        alias = self.directory / 'alias.raw'
        alias.symlink_to(self.directory / 'private.raw')
        self.observed['machine']['private_medium_path'] = str(alias)
        with self.assertRaisesRegex(ValueError, 'must not be a symlink'):
            fault.owned_native(self.directory)

    def test_superseded_resource_policy_is_not_overwritten(self):
        with patch.object(resource, 'prlimit', return_value=(128, -1)) as syscall:
            with self.assertRaisesRegex(ValueError, 'superseded'):
                fault.restore(self.token())
            syscall.assert_called_once_with(self.native['pid'], resource.RLIMIT_FSIZE)

    def test_pending_fault_cleanup_is_idempotent(self):
        token = self.token()
        token['state'] = 'pending'
        self.observed['capture_uncertain'] = True
        with patch.object(resource, 'prlimit', return_value=(-1, -1)) as syscall:
            self.assertTrue(fault.restore(token)['restored'])
            syscall.assert_called_once_with(self.native['pid'], resource.RLIMIT_FSIZE)


class NativeFileLimitCommandTests(unittest.TestCase):
    def test_normal_launcher_forwards_bounded_fault_arguments(self):
        launcher = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/lemmasim'))
        args = ['apply', '--session-dir', '/private/session', '--bytes', '38656',
                '--token', '/private/pending.json']
        with patch.object(sys, 'argv', ['lemmasim', 'file-limit', *args]), \
                patch.object(fault, 'main', return_value=0) as command:
            self.assertEqual(launcher['main'](), 0)
            command.assert_called_once_with(args)

    def test_fault_cli_rejects_incomplete_input_before_process_lookup(self):
        with patch.object(fault, 'owned_native') as lookup, \
                patch('sys.stderr'), self.assertRaises(SystemExit) as raised:
            fault.main(['apply', '--bytes', '38656'])
        self.assertEqual(raised.exception.code, 2)
        lookup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
