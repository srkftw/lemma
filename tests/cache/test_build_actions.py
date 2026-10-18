"""Exercise consumed import closures and private Lake state without target builds."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_actions import (_imports, controlled_environment, lean_source_inputs,
                           lean_workspace)
from core0_common import Core0Error, sha256


class BuildDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.write("lake-manifest.json", json.dumps({"packages": []}))
        self.write("lakefile.toml", 'name = "fixture"\n')
        self.write("lean-toolchain", "fixture-toolchain\n")

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def inventory(self, roots):
        return {name: sha256(path) for name, path in lean_source_inputs(self.root, roots).items()}

    def fixture(self):
        self.write("Shared/Core.lean", "def value : Nat := 1\n")
        self.write("Compiler/Registry.lean", "def roots : Nat := 2\n")
        self.write("Compiler/Lower.lean", "import Shared.Core\ndef lower : Nat := value\n")
        self.write("Compiler/Host.lean", "import Compiler.Lower\nimport Compiler.Registry\ndef exportRoot : Nat := roots\n")
        self.write("Unrelated.lean", "def irrelevant : Nat := 0\n")
        return self.write("App.lean", "import Shared.Core\nimport Compiler.Host\ndef main : Nat := value\n")

    def test_selected_application_and_compiler_host_closure_excludes_unrelated(self):
        source = self.fixture()
        before = self.inventory([source])
        self.assertEqual(set(before), {"lake-manifest.json", "lakefile.toml", "lean-toolchain", "App.lean",
                                       "Shared/Core.lean", "Compiler/Host.lean", "Compiler/Lower.lean", "Compiler/Registry.lean"})
        self.write("Unrelated.lean", "def irrelevant : Nat := 3\n")
        self.assertEqual(before, self.inventory([source]))
        self.write("Compiler/Lower.lean", "import Shared.Core\ndef lower : Nat := value + 1\n")
        changed = self.inventory([source])
        self.assertNotEqual(before["Compiler/Lower.lean"], changed["Compiler/Lower.lean"])
        self.assertEqual(before["App.lean"], changed["App.lean"])
        self.write("App.lean", "import Shared.Core\nimport Compiler.Host\ndef main : Nat := value + 2\n")
        application = self.inventory([source])
        self.assertNotEqual(changed["App.lean"], application["App.lean"])

    def test_consumed_configuration_and_generated_registry_change_identity(self):
        source = self.fixture()
        before = self.inventory([source])
        for name in ("lake-manifest.json", "lakefile.toml", "lean-toolchain", "Compiler/Registry.lean"):
            old = (self.root / name).read_text()
            # JSON remains valid while its bytes differ.
            self.write(name, old + "\n")
            after = self.inventory([source])
            self.assertNotEqual(before[name], after[name], name)
            self.write(name, old)

    def test_actual_kernel_export_closure_includes_host_lowering_and_catalog(self):
        closure = lean_source_inputs(ROOT, [ROOT / "Lemma/Compiler/KernelExport.lean"])
        for name in ("Lemma/Compiler/KernelExport.lean", "Lemma/Compiler/CFGLower.lean",
                     "Lemma/Compiler/Format.lean", "Lemma/Compiler/DeploymentCatalog.lean",
                     "Lemma/Platform/RiscV/ExecutionPrimitives.lean"):
            self.assertIn(name, closure)
            self.assertTrue(closure[name].is_file())
        self.assertFalse(any(name.startswith("Lemma/Compiler/Test/") for name in closure))
        self.assertGreater(len(closure), 10)

    def test_unknown_import_external_package_and_missing_source_fail_closed(self):
        source = self.write("App.lean", "import Unknown.Library\n")
        with self.assertRaisesRegex(Core0Error, "unknown Lean import"):
            self.inventory([source])
        with self.assertRaises((Core0Error, OSError)):
            self.inventory([self.root / "Missing.lean"])
        self.write("lake-manifest.json", json.dumps({"packages": [{"name": "undeclared"}]}))
        with self.assertRaisesRegex(Core0Error, "external Lake package"):
            self.inventory([source])

    def test_local_sources_cannot_shadow_pinned_upstream_namespaces(self):
        for namespace in ("Lean","Init","Std","Lake"):
            with self.subTest(namespace=namespace):
                imported = self.write(namespace+"/Override.lean","def shadow : Nat := 1\n")
                source = self.write("App.lean",f"import {namespace}.Override\n")
                with self.assertRaisesRegex(Core0Error,"pinned Lean namespace"):
                    self.inventory([source])
                with self.assertRaisesRegex(Core0Error,"pinned Lean namespace"):
                    self.inventory([imported])

    def test_nested_comments_strings_and_unsupported_import_headers(self):
        source = '''/- outer /- nested -/ comment -/
import Shared.Core -- comment
import Compiler.Host

def literal := "/- this string is not an unterminated comment"
'''
        self.assertEqual(_imports(source), ["Shared.Core", "Compiler.Host"])
        for source in ("public import Shared.Core\n", "import «Escaped.Module»\n", "import\n  Shared.Core\n", "/- unterminated"):
            with self.assertRaises(Core0Error, msg=source):
                _imports(source)

    def test_inherited_search_path_flags_and_plugin_environment_are_cleared(self):
        with patch.dict(os.environ, {"LEAN_PATH": "/foreign/olean", "LEAN_SRC_PATH": "/foreign/source",
                                     "CFLAGS": "-include foreign.h", "LD_PRELOAD": "/foreign.so"}):
            environment = controlled_environment({"lean": "/nix/tool/bin/lean", "lake": "/nix/tool/bin/lake"})
        self.assertFalse({"LEAN_PATH", "LEAN_SRC_PATH", "CFLAGS", "LD_PRELOAD"} & set(environment))
        self.assertEqual(environment["LEAN_NUM_THREADS"], "2")
        self.assertEqual(environment["PATH"], "/nix/tool/bin")

    def test_private_lake_inventory_rejects_foreign_olean_and_fresh_discards_state(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        cache = self.root / "cache"
        # Identity substitution avoids requiring Lean here. Actual private-tree
        # copy, inventory admission, foreign file detection and cleanup execute.
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            with lean_workspace(self.root, cache, {"lean": "fixture-lean", "lake": "fixture-lake"}, inputs) as tree:
                valid = tree / ".lake/build/lib/lean/App.olean"
                valid.parent.mkdir(parents=True)
                valid.write_bytes(b"retained compiled bytes")
                private_tree = tree
            with lean_workspace(self.root, cache, {"lean": "fixture-lean", "lake": "fixture-lake"}, inputs) as tree:
                self.assertEqual(valid.read_bytes(), b"retained compiled bytes")
                self.assertNotEqual(tree, self.root)
                self.assertEqual((tree / "App.lean").read_bytes(), source.read_bytes())
            foreign = private_tree / ".lake/build/lib/lean/Foreign.olean"
            foreign.write_bytes(b"foreign compiled dependency")
            with lean_workspace(self.root, cache, {"lean": "fixture-lean", "lake": "fixture-lake"}, inputs) as tree:
                self.assertFalse(foreign.exists())
                self.assertFalse(valid.exists())
                valid.parent.mkdir(parents=True)
                valid.write_bytes(b"replacement compiled bytes")
            with lean_workspace(self.root, cache, {"lean": "fixture-lean", "lake": "fixture-lake"}, inputs, fresh=True):
                self.assertFalse(valid.exists())
        self.assertFalse((self.root / ".lake").exists())


if __name__ == "__main__":
    unittest.main()
