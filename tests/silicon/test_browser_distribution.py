"""Host distribution integrity only; these are not machine acceptance fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('local_browser_distribution', ROOT / 'sim/browser/serve_local.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DistributionIntegrity(unittest.TestCase):
    def fixture(self, root):
        files = {}
        for name in ['serve.py', 'tools/lemmasim_browser.py', 'tools/silicon_guest_bundle.py',
                     'bundle/bundle.json', 'README.md', 'NOTICE.txt']:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            files[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                           'bytes': path.stat().st_size}
        manifest = {'schema': 'lemma-local-browser-distribution/1', 'files': files,
                    'source_bundle_sha256': files['bundle/bundle.json']['sha256']}
        (root / 'package.json').write_text(json.dumps(manifest))
        return manifest

    def test_missing_changed_and_unlisted_bytes_are_rejected(self):
        for change in ['missing', 'changed', 'unlisted']:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                MODULE.verify_package(root)
                path = root / 'tools/lemmasim_browser.py'
                if change == 'missing':
                    path.unlink()
                elif change == 'changed':
                    path.write_bytes(b'X' * path.stat().st_size)
                else:
                    (root / 'unexpected').write_bytes(b'not served')
                with self.assertRaises(ValueError):
                    MODULE.verify_package(root)

    def test_traversal_and_symlinks_do_not_admit_external_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            manifest['files']['../outside'] = manifest['files'].pop('NOTICE.txt')
            (root / 'package.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Invalid distribution path'):
                MODULE.verify_package(root)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            path = root / 'NOTICE.txt'
            path.unlink()
            path.symlink_to(root / 'README.md')
            with self.assertRaises(ValueError):
                MODULE.verify_package(root)

    def test_contradictory_original_machine_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            manifest['source_bundle_sha256'] = '0' * 64
            (root / 'package.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'contradicts'):
                MODULE.verify_package(root)


if __name__ == '__main__':
    unittest.main()
