"""Tests for preparation metadata only; not compiler/OS tests."""
from pathlib import Path
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_scaffold import validate

class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'lemma'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__', 'build'))
    def tearDown(self):
        self.temp.cleanup()
    def change(self, relative, fn):
        p = self.root / relative
        obj = json.loads(p.read_text())
        fn(obj)
        p.write_text(json.dumps(obj))
    def test_baseline(self):
        self.assertEqual(validate(self.root), [])
    def test_missing_contract_fails(self):
        (self.root/'docs/contracts/CORE0.md').unlink()
        self.assertTrue(any('Missing required' in e for e in validate(self.root)))
    def test_unknown_dependency_fails(self):
        self.change('docs/plan/construction-units.json', lambda p: p['units'][0].update(depends_on=['not-real']))
        self.assertTrue(any('Unknown dependency' in e for e in validate(self.root)))
    def test_cycle_fails(self):
        self.change('docs/plan/construction-units.json', lambda p: p['units'][0].update(depends_on=['1.8']))
        self.assertTrue(any('cycle' in e for e in validate(self.root)))
    def test_gate_without_evidence_fails(self):
        self.change('docs/plan/construction-units.json', lambda p: p['gates'][0].update(status='passed'))
        self.assertTrue(any('lacks integration evidence' in e for e in validate(self.root)))
    def test_unit_without_evidence_fails(self):
        self.change('docs/plan/construction-units.json', lambda p: p['units'][0].update(status='passed'))
        self.assertTrue(any('evidence records' in e for e in validate(self.root)))
    def test_public_visibility_fails(self):
        self.change('repository.json', lambda p: p.update(intended_visibility='public'))
        self.assertTrue(any('visibility' in e for e in validate(self.root)))
    def test_false_toolchain_pin_fails(self):
        self.change('tooling/toolchain-lock.json', lambda p: p.update(status='pinned'))
        self.assertTrue(any('verified immutable identity' in e for e in validate(self.root)))
    def test_target_c_fails(self):
        p = self.root/'Lemma/Boot.c'
        p.parent.mkdir()
        p.write_text('void boot(void) {}\n')
        self.assertTrue(any('non-Lean target' in e for e in validate(self.root)))
    def test_malformed_json_fails(self):
        (self.root/'repository.json').write_text('{')
        self.assertTrue(any('Unreadable planning JSON' in e for e in validate(self.root)))

if __name__ == '__main__':
    unittest.main()
