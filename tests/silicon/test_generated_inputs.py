# SPDX-License-Identifier: Apache-2.0
"""Stable generated prerequisite bytes must preserve incremental-build timestamps."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import silicon_compute as compute
from action_cache import write_if_changed


class GeneratedInputTests(unittest.TestCase):
    def test_equal_header_is_not_replaced_but_changed_header_is(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'generated' / 'identity.h'
            write_if_changed(path, b'#define ID "first"\n')
            before = path.stat()
            write_if_changed(path, b'#define ID "first"\n')
            self.assertEqual((path.stat().st_ino, path.stat().st_mtime_ns),
                             (before.st_ino, before.st_mtime_ns))
            write_if_changed(path, b'#define ID "second"\n')
            self.assertEqual(path.read_bytes(), b'#define ID "second"\n')
            self.assertNotEqual(path.stat().st_ino, before.st_ino)

    def test_source_manifest_keeps_equal_binding_files_unchanged(self):
        # Use the actual profile/generator and host source closure. The upstream
        # core itself is outside this generator test; no Verilator is invoked.
        with tempfile.TemporaryDirectory() as temporary:
            dependency = Path(temporary) / 'deps' / 'cvw'
            (dependency / 'config' / 'shared').mkdir(parents=True)
            with patch.object(compute, 'sources', return_value=[]):
                first = compute.source_manifest(dependency)
                directory = Path(first['host_include_dir'])
                files = [directory / name for name in
                         ('lemma_silicon_binding.sv', 'lemma_silicon_binding.h')]
                identities = {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                              for path in files}
                second = compute.source_manifest(dependency)
                self.assertEqual(first, second)
                self.assertEqual(identities, {path: (path.stat().st_ino, path.stat().st_mtime_ns)
                                              for path in files})
                # A consumed profile value alters both generated interfaces.
                selected = dict(compute.profile())
                selected['clock_hz'] += 1
                with patch.object(compute, 'profile', return_value=selected):
                    changed = compute.source_manifest(dependency)
                self.assertNotEqual(first['sha256'], changed['sha256'])
                self.assertNotEqual(first['host_binding_sha256'], changed['host_binding_sha256'])


if __name__ == '__main__':
    unittest.main()
