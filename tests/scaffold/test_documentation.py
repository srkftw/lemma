"""HTML policy regressions: hooks, current navigation, and immutable exceptions."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_documentation as policy

HTML = '<!doctype html><html><head><meta charset="utf-8"><title>Fixture</title></head><body><h1 id="stable">Fixture</h1>{}</body></html>'

class DocumentationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name, target in policy.HOOKS.items():
            self.write(name, '<!-- Read ' + target + ' in full. -->\n')
            self.write(target, HTML.format(''))
        self.write('docs/evidence/history/frozen.md', 'immutable original source\n')
        self.write('docs/document-map.json', json.dumps({
            'schema': 'lemma-document-map/v1',
            'exceptions': {**{name: 'functional entry' for name in policy.HOOKS},
                           'docs/evidence/history/frozen.md': 'immutable'},
            'documents': [{'original': 'guide.md', 'current': 'docs/contributor-guide.html'},
                          {'original': 'docs/evidence/history/frozen.md', 'exception': 'immutable',
                           'original_sha256': hashlib.sha256(b'immutable original source\n').hexdigest()}]}))
    def tearDown(self): self.temporary.cleanup()
    def write(self, name, text):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    def test_valid_html_and_minimal_hooks(self): self.assertEqual(policy.validate(self.root), [])
    def test_wrapped_narrative_markdown_is_not_an_exception(self):
        self.write('docs/new-notes.md', '<!-- hidden prose -->')
        self.assertTrue(any('Unapproved narrative Markdown' in e for e in policy.validate(self.root)))
    def test_readme_html_cannot_regress_landing_selection(self):
        self.write('.github/README.html', HTML.format('project prose'))
        self.assertTrue(any('Automatically selected README' in e for e in policy.validate(self.root)))
    def test_contributing_html_cannot_regress_observed_landing_selection(self):
        self.write('docs/CONTRIBUTING.html', HTML.format('raw guide prose'))
        self.assertTrue(any('Automatically selected CONTRIBUTING' in e for e in policy.validate(self.root)))
    def test_missing_agent_hook_or_rendered_hook_prose_reject(self):
        (self.root / 'AGENTS.md').unlink()
        self.assertTrue(any('Missing agent/template' in e for e in policy.validate(self.root)))
        self.write('AGENTS.md', 'Read docs/contributor-guide.html')
        self.assertTrue(any('minimal raw-readable comment' in e for e in policy.validate(self.root)))
    def test_current_link_and_anchor_are_checked(self):
        for link in ('missing.html', '#absent'):
            with self.subTest(link=link):
                self.write('docs/contributor-guide.html', HTML.format('<a href="' + link + '">link</a>'))
                self.assertTrue(any('broken current link' in e or 'missing current anchor' in e
                                    for e in policy.validate(self.root)))
    def test_pinned_remote_url_is_preserved_without_network(self):
        self.write('docs/contributor-guide.html', HTML.format('<a href="https://example.invalid/old.md#original">history</a>'))
        self.assertEqual(policy.validate(self.root), [])
    def test_historical_evidence_bytes_are_not_relabelled(self):
        self.write('docs/evidence/history/frozen.md', 'changed')
        self.assertTrue(any('Changed immutable historical' in e for e in policy.validate(self.root)))
    def test_duplicate_anchors_and_missing_utf8_reject(self):
        self.write('docs/contributor-guide.html', HTML.format('<p id="stable">duplicate</p>').replace('<meta charset="utf-8">', ''))
        errors = policy.validate(self.root)
        self.assertTrue(any('duplicate anchor' in e for e in errors))
        self.assertTrue(any('UTF-8' in e for e in errors))

class ConsumedContractTests(unittest.TestCase):
    def test_current_contracts_remain_consumed_and_missing_contract_rejects(self):
        from unittest.mock import patch
        import build_kernel
        sources = build_kernel.source_inputs(ROOT)
        name = 'docs/contracts/006-notebook-control-backlog-v2.html'
        self.assertIn(name, sources)
        self.assertIn('docs/document-map.json', sources)
        original = Path.is_file
        with patch.object(Path, 'is_file', lambda path: False if path == ROOT / name else original(path)):
            with self.assertRaisesRegex(build_kernel.Core0Error, 'Missing required current contract'):
                build_kernel.source_inputs(ROOT)
    def test_new_registry_requires_its_actual_contract(self):
        from unittest.mock import patch
        import build_kernel
        original = Path.is_file
        for name, message in (("docs/contracts/009-core0-kernel-v0.10.html", "Missing required Integrated15 dependency"),
                              ("docs/contracts/009-school-submission-v2.html", "Missing School dependency")):
            with self.subTest(contract=name), patch.object(Path, 'is_file', lambda path: False if path == ROOT / name else original(path)):
                with self.assertRaisesRegex(build_kernel.Core0Error, message):
                    build_kernel.source_inputs(ROOT)
        # A retained v1 registry consumes its original contract; removing the
        # current v2 contract cannot silently retarget that archived cohort.
        registry = ROOT / 'scripts/school_deployment.py'
        original_read = Path.read_text
        legacy_registry = registry.read_text().replace('lemma-school-notebook-deployment/2',
                                                     'lemma-school-notebook-deployment/1')
        def read_legacy(path, *args, **kwargs):
            return legacy_registry if path == registry else original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read_legacy):
            self.assertIn('docs/contracts/009-school-submission-v1.html', build_kernel.source_inputs(ROOT))
            missing = ROOT / 'docs/contracts/009-school-submission-v1.html'
            with patch.object(Path, 'is_file', lambda path: False if path == missing else original(path)):
                with self.assertRaisesRegex(build_kernel.Core0Error, 'Missing School dependency'):
                    build_kernel.source_inputs(ROOT)
    def test_historical_archive_paths_remain_original(self):
        from unittest.mock import patch
        import build_kernel
        original = Path.is_file
        def archived(path):
            if path == ROOT / 'docs/document-map.json' or path == ROOT / 'docs/contributor-guide.html': return False
            # The preserved historical layout also predates the new deployment
            # and its mandatory current HTML/specification dependency closure.
            if path in (ROOT / 'scripts/multimodal_deployment.py', ROOT / 'scripts/integrated_deployment.py', ROOT / 'scripts/school_deployment.py'): return False
            if str(path).endswith('.html') and 'docs/contracts/' in str(path): return False
            if str(path).endswith('.md') and 'docs/contracts/' in str(path): return True
            return original(path)
        with patch.object(Path, 'is_file', archived), patch.object(build_kernel, 'sha256', return_value='fixture-hash'):
            sources = build_kernel.source_inputs(ROOT)
        self.assertIn('docs/contracts/006-notebook-control-backlog-v2.md', sources)
        self.assertNotIn('docs/contracts/006-notebook-control-backlog-v2.html', sources)

class DistributionDocumentationTests(unittest.TestCase):
    @staticmethod
    def module(name, relative):
        spec = importlib.util.spec_from_file_location(name, ROOT / relative)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module
    def test_generated_usage_is_html_and_never_readme(self):
        for name in ('package_native', 'package_browser'):
            module = __import__(name)
            document = policy.Document(module.USAGE_HTML)
            self.assertTrue(module.USAGE_HTML.startswith('<!doctype html>'))
            self.assertTrue(document.charset)
            self.assertIn("/ 'usage.html'", (ROOT / 'scripts' / (name + '.py')).read_text())
    def test_new_browser_schema_requires_html_while_legacy_bytes_remain_valid(self):
        verifier = self.module('local_browser_docs', 'sim/browser/serve_local.py')
        for version, document in ((1, 'README.md'), (2, 'usage.html')):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                names = ['serve.py', 'tools/lemmasim_browser.py', 'tools/silicon_guest_bundle.py',
                         'bundle/bundle.json', document, 'NOTICE.txt']
                files = {}
                for name in names:
                    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'original')
                    files[name] = {'bytes': 8, 'sha256': hashlib.sha256(b'original').hexdigest()}
                data = {'schema': 'lemma-local-browser-distribution/' + str(version), 'files': files,
                        'source_bundle_sha256': files['bundle/bundle.json']['sha256']}
                (root / 'package.json').write_text(json.dumps(data))
                self.assertEqual(verifier.verify_package(root), data)
                (root / document).unlink()
                with self.assertRaises(ValueError): verifier.verify_package(root)

if __name__ == '__main__': unittest.main()
