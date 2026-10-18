"""Actual unittest receipts must reject source/tool changes and omitted coverage."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import host_prerequisites as prerequisite
from core0_common import Core0Error


class HostPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'checkout'
        self.root.mkdir()
        self.write('.gitignore', 'build/\n__pycache__/\n*.pyc\n')
        self.write('docs/contracts/fixture.md', 'expected contract bytes')
        self.write('tooling/toolchain-lock.json', json.dumps({'auxiliary_tools': {'python': {
            'verified': True, 'version': platform.python_version(),
            'store_path': str(Path(sys.executable).resolve().parent)}}}))
        self.write('tests/kernel/test_behavior.py', '''import unittest
from pathlib import Path
class Behavior(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(Path('docs/contracts/fixture.md').read_text(), 'expected contract bytes')
''')
        for args in (('init', '-q'), ('add', '.'), ('-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')):
            subprocess.run(('git', *args), cwd=self.root, check=True, capture_output=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def produce(self, name='receipt'):
        directory = self.root / 'build' / name
        result = prerequisite.produce(self.root, directory, timeout=10)
        return directory / 'receipt.json', result

    def test_actual_nonempty_execution_and_explicit_reuse_preserve_original(self):
        path, original = self.produce()
        self.assertEqual(original['status'], 'PASS')
        self.assertEqual(original['test_count'], 1)
        self.assertEqual(original['argv'], [str(Path(sys.executable).resolve()), *prerequisite.CORPUS])
        reused = prerequisite.validate(self.root, path)
        self.assertEqual(reused['execution'], 'validated-reuse')
        self.assertEqual(reused['test_count'], 1)
        self.assertEqual(reused['producer_receipt_id'], original['producer_receipt_id'])
        self.assertEqual(reused['original_started_at'], original['started_at'])
        self.assertNotIn('argv', reused)  # It did not execute the original command again.
        self.write('build/unrelated-output', 'ignored output')
        prerequisite.validate(self.root, path)
        with self.assertRaises(Core0Error):
            prerequisite.produce(self.root, path.parent, timeout=10)

    def test_identical_source_after_commit_retains_original_producer_provenance(self):
        self.write('publication-note.md', 'already consumed exact untracked source bytes')
        path, original = self.produce()
        subprocess.run(('git', 'add', 'publication-note.md'), cwd=self.root, check=True, capture_output=True)
        subprocess.run(('git', '-c', 'user.name=fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'same bytes new publication'),
                       cwd=self.root, check=True, capture_output=True)
        admitted = prerequisite.validate(self.root, path)
        self.assertEqual(admitted['original_source_commit'], original['source']['commit'])
        head = subprocess.check_output(('git', 'rev-parse', 'HEAD'), cwd=self.root).decode().strip()
        tree = subprocess.check_output(('git', 'rev-parse', 'HEAD^{tree}'), cwd=self.root).decode().strip()
        self.assertNotEqual(head, admitted['original_source_commit'])
        self.assertNotEqual(tree, admitted['original_source_tree'])
        self.assertEqual(admitted['execution'], 'validated-reuse')

    def test_contract_helper_added_file_and_changed_source_invalidate(self):
        path, _ = self.produce()
        for name in ('docs/contracts/fixture.md', 'new-compiler-helper.py'):
            previous = (self.root / name).read_bytes() if (self.root / name).exists() else None
            self.write(name, 'changed dependency')
            with self.assertRaisesRegex(Core0Error, 'source/tool/checkout/environment'):
                prerequisite.validate(self.root, path)
            if previous is None:
                (self.root / name).unlink()
            else:
                (self.root / name).write_bytes(previous)
        prerequisite.validate(self.root, path)

    def test_controlled_environment_tool_pin_and_relocation_are_not_omitted(self):
        path, _ = self.produce()
        with patch.dict(os.environ, {'LEAN_PATH': '/injected', 'LD_PRELOAD': '/injected.so'}):
            prerequisite.validate(self.root, path)
        with patch.dict(os.environ, {'PATH': '/irrelevant-unused:' + os.environ['PATH']}):
            prerequisite.validate(self.root, path)
        pin = self.root / 'tooling/toolchain-lock.json'
        original = pin.read_bytes()
        self.write('tooling/toolchain-lock.json', json.dumps({'auxiliary_tools': {'python': {'verified': False}}}))
        with self.assertRaises(Core0Error):
            prerequisite.validate(self.root, path)
        pin.write_bytes(original)
        other = Path(self.temporary.name) / 'relocated'
        shutil.copytree(self.root, other, ignore=shutil.ignore_patterns('build'))
        with self.assertRaises(Core0Error):
            prerequisite.validate(other, path)

    def test_log_corruption_and_forged_tool_identity_are_rejected(self):
        path, _ = self.produce()
        log = path.parent / 'kernel-host.log'
        original_log = log.read_bytes()
        log.write_bytes(original_log + b'changed')
        with self.assertRaises(Core0Error):
            prerequisite.validate(self.root, path)
        log.write_bytes(original_log)
        value = json.loads(path.read_text())
        value['tool']['sha256'] = '0' * 64
        value['producer_receipt_id'] = hashlib.sha256(prerequisite.encoded(
            {key: item for key, item in value.items() if key != 'producer_receipt_id'})).hexdigest()
        path.write_text(json.dumps(value))
        with self.assertRaises(Core0Error):
            prerequisite.validate(self.root, path)

    def test_expected_negative_fixture_stdout_after_runner_summary_is_not_failure(self):
        self.write('tests/kernel/test_behavior.py', 'import unittest\nclass T(unittest.TestCase):\n'
                   ' def test_expected_rejection(self):\n'
                   '  with self.assertRaises(ValueError): int("invalid")\n'
                   '  print("FAIL: expected negative fixture observation")\n')
        path, original = self.produce()
        self.assertEqual(original['status'], 'PASS')
        self.assertIn('FAIL: expected negative fixture observation', (path.parent / 'kernel-host.log').read_text())
        self.assertEqual(prerequisite.validate(self.root, path)['test_count'], 1)

    def test_mutable_external_helper_and_git_cannot_enter_the_closed_tool_path(self):
        external = Path(self.temporary.name) / 'external-bin'
        external.mkdir()
        helper = external / 'external-helper'
        helper.write_text(f'#!{Path(sys.executable).resolve()}\nraise SystemExit(0)\n')
        helper.chmod(0o755)
        self.write('tests/kernel/test_behavior.py', 'import unittest, subprocess\nclass T(unittest.TestCase):\n'
                   ' def test_external(self): subprocess.run(["external-helper"], check=True)\n')
        with patch.dict(os.environ, {'PATH': str(external) + os.pathsep + os.environ['PATH']}):
            self.assertNotIn(str(external), prerequisite.environment_identity()['PATH'].split(os.pathsep))
            with self.assertRaises(Core0Error):
                prerequisite.produce(self.root, self.root / 'build' / 'external', timeout=10)
            failed = json.loads((self.root / 'build/external/receipt.json').read_text())
            self.assertEqual(failed['status'], 'FAIL')
            self.assertIn('FileNotFoundError', (self.root / 'build/external/kernel-host.log').read_text())
            mutable_git = external / 'git'
            mutable_git.write_bytes(Path(shutil.which('git')).resolve().read_bytes())
            mutable_git.chmod(0o755)
            with self.assertRaisesRegex(Core0Error, 'mutable/non-Nix Git'):
                prerequisite.git_identity()

    def test_real_skipped_empty_and_defective_corpora_cannot_publish_pass(self):
        fixtures = {
            'skipped': 'import unittest\nclass T(unittest.TestCase):\n @unittest.skip("explicit omission")\n def test_omitted(self): pass\n',
            'empty': 'def no_test_cases(): pass\n',
            'defective': 'import unittest\nclass T(unittest.TestCase):\n def test_defect(self): self.assertEqual(1, 2)\n',
        }
        for name, source in fixtures.items():
            with self.subTest(name=name):
                self.write('tests/kernel/test_behavior.py', source)
                directory = self.root / 'build' / name
                with self.assertRaises(Core0Error):
                    prerequisite.produce(self.root, directory, timeout=10)
                failed = json.loads((directory / 'receipt.json').read_text())
                self.assertEqual(failed['status'], 'FAIL')
                with self.assertRaises(Core0Error):
                    prerequisite.validate(self.root, directory / 'receipt.json')

    def test_malformed_receipt_and_unignored_output_fail_closed(self):
        path, _ = self.produce()
        path.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(Core0Error):
            prerequisite.validate(self.root, path)
        with self.assertRaises(Core0Error):
            prerequisite.produce(self.root, self.root / 'retained-source-output', timeout=10)


if __name__ == '__main__':
    unittest.main()
