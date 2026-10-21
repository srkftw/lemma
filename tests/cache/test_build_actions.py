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

    def test_rejected_export_retains_only_unchanged_previously_validated_compiled_bytes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            cache = self.root / "retained-cache"
            with lean_workspace(self.root, cache, tools, inputs) as tree:
                compiled = tree / ".lake/build/lib/lean/App.olean"
                compiled.parent.mkdir(parents=True)
                compiled.write_bytes(b"previous successful compiler output")
            with self.assertRaisesRegex(Core0Error, "rejected export"):
                with lean_workspace(self.root, cache, tools, inputs):
                    raise Core0Error("rejected export")
            with lean_workspace(self.root, cache, tools, inputs):
                self.assertEqual(compiled.read_bytes(), b"previous successful compiler output")

            for mutation in ("changed", "new", "fresh"):
                with self.subTest(mutation=mutation):
                    with self.assertRaisesRegex(Core0Error, "rejected export"):
                        with lean_workspace(self.root, cache, tools, inputs, fresh=mutation == "fresh"):
                            if mutation == "changed":
                                compiled.write_bytes(b"failed action changed compiled output")
                            elif mutation == "new":
                                (compiled.parent / "Foreign.olean").write_bytes(b"unadmitted compiled output")
                            raise Core0Error("rejected export")
                    with lean_workspace(self.root, cache, tools, inputs):
                        self.assertEqual(compiled.exists(), mutation == "new")
                        self.assertFalse((compiled.parent / "Foreign.olean").exists())
                        compiled.parent.mkdir(parents=True, exist_ok=True)
                        compiled.write_bytes(b"previous successful compiler output")

    def test_abrupt_pending_addition_rollback_preserves_only_exact_admitted_bytes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            cache = self.root / "abrupt-cache"
            with lean_workspace(self.root, cache, tools, inputs) as tree:
                compiled = tree / ".lake/build/lib/lean/App.olean"
                compiled.parent.mkdir(parents=True)
                compiled.write_bytes(b"previous successful compiler output")
            # A separate real process exits without Python finally. The parent
            # then takes the real lock and recovers only unadmitted additions.
            pid = os.fork()
            if pid == 0:
                with lean_workspace(self.root, cache, tools, inputs):
                    (compiled.parent / "RecoveryExecuted.setup.json").write_text("partial")
                    os._exit(17)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(status), 17)
            base = tree.parent
            self.assertTrue((base / "compiled-pending.json").is_file())
            with lean_workspace(self.root, cache, tools, inputs):
                self.assertEqual(compiled.read_bytes(), b"previous successful compiler output")
                self.assertFalse((compiled.parent / "RecoveryExecuted.setup.json").exists())
            self.assertFalse((base / "compiled-pending.json").exists())

    def test_pending_changed_or_deleted_baseline_and_bad_marker_invalidate(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        from core0_common import write_json
        for failure in ("changed", "deleted", "symlink", "malformed", "wrong-metadata"):
            with self.subTest(failure=failure), patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
                cache = self.root / ("pending-" + failure)
                with lean_workspace(self.root, cache, tools, inputs) as tree:
                    compiled = tree / ".lake/build/lib/lean/App.olean"
                    compiled.parent.mkdir(parents=True)
                    compiled.write_bytes(b"admitted")
                base = tree.parent
                marker = base / "compiled-pending.json"
                write_json(marker, {"schema": "lemma-lake-addition-rollback/1", "metadata_sha256": sha256(base / "compiled.json")})
                extra = compiled.parent / "extra.setup.json"
                extra.write_bytes(b"unadmitted")
                if failure == "changed": compiled.write_bytes(b"changed")
                elif failure == "deleted": compiled.unlink()
                elif failure == "symlink":
                    extra.unlink()
                    outside = self.write("outside-"+failure, "external-preserve")
                    extra.symlink_to(outside)
                elif failure == "malformed": marker.write_text("{partial")
                elif failure == "wrong-metadata":
                    write_json(marker, {"schema": "lemma-lake-addition-rollback/1", "metadata_sha256": "0"*64})
                with lean_workspace(self.root, cache, tools, inputs):
                    self.assertFalse(compiled.exists())
                    self.assertFalse(extra.exists())
                if failure == "symlink": self.assertEqual(outside.read_text(), "external-preserve")

    def test_pending_marker_symlink_rejects_without_touching_external_bytes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            cache = self.root / "pending-symlink"
            with lean_workspace(self.root, cache, tools, inputs) as tree: pass
            outside = self.write("outside-pending", "external-preserve")
            (tree.parent / "compiled-pending.json").symlink_to(outside)
            with self.assertRaisesRegex(Core0Error, "pending-state metadata.*symlink"):
                with lean_workspace(self.root, cache, tools, inputs): pass
            self.assertEqual(outside.read_text(), "external-preserve")

    def test_initial_failed_compilation_never_admits_new_compiled_bytes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            cache = self.root / "failed-initial-cache"
            with self.assertRaisesRegex(Core0Error, "failed preparation"):
                with lean_workspace(self.root, cache, tools, inputs) as tree:
                    compiled = tree / ".lake/build/lib/lean/App.olean"
                    compiled.parent.mkdir(parents=True)
                    compiled.write_bytes(b"incomplete compiler output")
                    raise Core0Error("failed preparation")
            with lean_workspace(self.root, cache, tools, inputs):
                self.assertFalse(compiled.exists())

    def test_compiled_root_symlink_is_unlinked_without_touching_external_bytes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        # Only tool identity is substituted. The actual private-tree traversal,
        # symlink admission and ordinary/fresh reset paths execute on disk.
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            for fresh in (False, True):
                with self.subTest(fresh=fresh):
                    cache = self.root / f"cache-{fresh}"
                    with lean_workspace(self.root, cache, tools, inputs) as tree:
                        original = tree / ".lake/build/lib/lean/App.olean"
                        original.parent.mkdir(parents=True)
                        original.write_bytes(b"original compiled bytes")
                    external = self.root / f"external-lake-{fresh}"
                    (tree / ".lake").rename(external)
                    (tree / ".lake").symlink_to(external, target_is_directory=True)
                    foreign = external / "build/lib/lean/App.olean"
                    foreign.write_bytes(b"corrupt external compiled bytes")
                    before = {p.relative_to(external): p.read_bytes()
                              for p in external.rglob("*") if p.is_file()}
                    with lean_workspace(self.root, cache, tools, inputs, fresh=fresh) as current:
                        self.assertEqual(current, tree)
                        self.assertFalse((current / ".lake").exists())
                        self.assertFalse((current / ".lake").is_symlink())
                        replacement = current / ".lake/build/lib/lean/App.olean"
                        replacement.parent.mkdir(parents=True)
                        replacement.write_bytes(b"new private compiled bytes")
                    self.assertEqual(before, {p.relative_to(external): p.read_bytes()
                                             for p in external.rglob("*") if p.is_file()})
                    self.assertFalse((tree / ".lake").is_symlink())
                    self.assertEqual(replacement.read_bytes(), b"new private compiled bytes")

    def test_workspace_root_symlink_rejects_before_traversing_or_rewriting_external_tree(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            cache = self.root / "cache"
            with lean_workspace(self.root, cache, tools, inputs) as tree:
                compiled = tree / ".lake/build/lib/lean/App.olean"
                compiled.parent.mkdir(parents=True)
                compiled.write_bytes(b"external compiled bytes")
            external = self.root / "external-tree"
            tree.rename(external)
            tree.symlink_to(external, target_is_directory=True)
            before = {p.relative_to(external): p.read_bytes()
                      for p in external.rglob("*") if p.is_file()}
            source.write_text(source.read_text() + "\ndef changed : Nat := 9\n")
            for fresh in (False, True):
                with self.subTest(fresh=fresh):
                    with self.assertRaisesRegex(Core0Error, "workspace root must not be a symlink"):
                        with lean_workspace(self.root, cache, tools, inputs, fresh=fresh):
                            self.fail("external workspace root was admitted")
                    self.assertTrue(tree.is_symlink())
                    self.assertEqual(before, {p.relative_to(external): p.read_bytes()
                                             for p in external.rglob("*") if p.is_file()})

    def test_compiled_metadata_symlink_rejects_before_read_and_write_without_external_changes(self):
        source = self.fixture()
        inputs = lean_source_inputs(self.root, [source])
        tools = {"lean": "fixture-lean", "lake": "fixture-lake"}
        with patch("action_cache.tool_identity", side_effect=lambda name: {"path": name, "sha256": "fixture-tool"}):
            for fresh in (False, True):
                with self.subTest(fresh=fresh):
                    cache = self.root / f"metadata-cache-{fresh}"
                    with lean_workspace(self.root, cache, tools, inputs) as tree:
                        pass
                    metadata = tree.parent / "compiled.json"
                    external = self.root / f"external-metadata-{fresh}"
                    external.write_bytes(b"external bytes must remain unchanged")
                    metadata.unlink()
                    metadata.symlink_to(external)
                    with self.assertRaisesRegex(Core0Error, "compiled-state metadata must not be a symlink"):
                        with lean_workspace(self.root, cache, tools, inputs, fresh=fresh):
                            self.fail("symlink metadata was admitted")
                    self.assertTrue(metadata.is_symlink())
                    self.assertEqual(external.read_bytes(), b"external bytes must remain unchanged")
                    metadata.unlink()
                    # A link introduced while the caller owns the tree must
                    # also reject before the final metadata write follows it.
                    with self.assertRaisesRegex(Core0Error, "compiled-state metadata must not be a symlink"):
                        with lean_workspace(self.root, cache, tools, inputs, fresh=fresh):
                            metadata.symlink_to(external)
                    self.assertTrue(metadata.is_symlink())
                    self.assertEqual(external.read_bytes(), b"external bytes must remain unchanged")


if __name__ == "__main__":
    unittest.main()
