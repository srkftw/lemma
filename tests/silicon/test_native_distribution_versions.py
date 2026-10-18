"""Host version coexistence and contradictory archive rejection; no CPU fixture."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('native_local_versions', ROOT / 'sim/native/run_local.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeHostVersions(unittest.TestCase):
    def fixture(self, root):
        old = hashlib.sha256(b'compiled original').hexdigest()
        new = hashlib.sha256(b'current host only').hexdigest()
        payloads = {name: name.encode() for name in (
            'run.py', 'host/scripts/lemmasim', 'host/scripts/native_bundle_relocation.py',
            'host/scripts/lemmasim-course', 'host/scripts/lemmasim_course_fast.py', 'NOTICE.txt', 'README.md')}
        payloads['bundle/source/scripts/audit_kernel.py'] = b'compiled original'
        payloads['host/scripts/audit_kernel.py'] = b'current host only'
        payloads['bundle/bundle.json'] = json.dumps({'sources': {'scripts/audit_kernel.py': old}}).encode()
        files = {}
        for name, content in payloads.items():
            p = root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(content)
            files[name] = {'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
        data = {'schema': 'lemma-local-native-distribution/3', 'files': files,
                'source_bundle_sha256': files['bundle/bundle.json']['sha256'],
                'host_inputs': {'scripts/audit_kernel.py': new},
                'host_tool_versions': {'schema': 'lemma-native-host-tool-versions/1', 'differences': {
                    'scripts/audit_kernel.py': {'compiled_source': 'bundle/source/scripts/audit_kernel.py',
                                              'compiled_sha256': old, 'host_sha256': new}}}}
        return data

    def verify(self, root, data):
        (root / 'package.json').write_text(json.dumps(data))
        return MODULE.verify(root)

    def test_distinct_host_and_compiled_versions_both_remain_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = self.fixture(root)
            self.assertEqual(self.verify(root, data), data)
            self.assertEqual((root / 'bundle/source/scripts/audit_kernel.py').read_bytes(), b'compiled original')

    def test_html_distribution_successor_preserves_original_source_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = self.fixture(root)
            (root / 'README.md').rename(root / 'usage.html')
            data['files']['usage.html'] = data['files'].pop('README.md')
            data['schema'] = 'lemma-local-native-distribution/4'
            self.assertEqual(self.verify(root, data), data)
            data['schema'] = 'lemma-local-native-distribution/3'
            with self.assertRaises(ValueError): self.verify(root, data)

    def test_wrong_original_replacement_or_unversioned_mode_reject(self):
        for change in ('compiled', 'host', 'missing', 'old-schema'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); data = self.fixture(root)
                differences = data['host_tool_versions']['differences']
                if change == 'compiled': differences['scripts/audit_kernel.py']['compiled_sha256'] = '0' * 64
                elif change == 'host': differences['scripts/audit_kernel.py']['host_sha256'] = '0' * 64
                elif change == 'missing': differences.clear()
                else: data['schema'] = 'lemma-local-native-distribution/2'
                with self.assertRaises(ValueError): self.verify(root, data)

    def test_changed_or_missing_retained_compiled_bytes_reject(self):
        for remove in (False, True):
            with self.subTest(remove=remove), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); data = self.fixture(root)
                p = root / 'bundle/source/scripts/audit_kernel.py'
                if remove: p.unlink()
                else: p.write_bytes(b'replaced original')
                with self.assertRaises(ValueError): self.verify(root, data)


if __name__ == '__main__': unittest.main()
