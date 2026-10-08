#!/usr/bin/env python3
"""Focused freshness and cross-profile identity tests for the Gate 2 driver."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_core0  # noqa: E402
import check_foundation_gate2 as gate2  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class Gate2ProfileIdentityTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[dict[str, Path], dict[str, object]]:
        outputs = {profile: root / profile for profile in ("O0", "O2")}
        manifest: dict[str, object] = {"schema_version": 1, "roots": []}
        provenance = {
            "artifact_category": "test-frontend-suite",
            "source_commit": "1" * 40,
            "dirty_tree": False,
            "dirty_paths": [],
            "compiler_route": "checked",
            "target": {"abi": "lp64"},
            "source_inputs": [{"path": "source.lean", "sha256": "2" * 64}],
            "elaborated_inputs": [{"source": "source.lean", "olean_sha256": "3" * 64}],
            "export_configuration": {"environment": {"seed": "4"}},
        }
        for output in outputs.values():
            output.mkdir()
            (output / "scalar-suite-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            (output / "scalar-suite-normalized.txt").write_text(
                "checked-body\n", encoding="utf-8"
            )
            (output / "scalar-test-abi.json").write_text("{}\n", encoding="utf-8")
            (output / "symbols.txt").write_text("source=llvm\n", encoding="utf-8")
            (output / "provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
        return outputs, manifest

    def test_exact_source_snapshot_is_accepted_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs, manifest = self._fixture(root)
            result = gate2._verify_profile_source_identity(
                root=root,
                outputs=outputs,
                manifests={"O0": manifest, "O2": copy.deepcopy(manifest)},
            )
            self.assertEqual(result["source_commit"], "1" * 40)
            self.assertEqual(
                set(result["identical_checked_source_artifacts"]),
                {
                    "scalar-suite-manifest.json",
                    "scalar-suite-normalized.txt",
                    "scalar-test-abi.json",
                    "symbols.txt",
                },
            )

    def test_body_and_provenance_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs, manifest = self._fixture(root)
            (outputs["O2"] / "scalar-suite-normalized.txt").write_text(
                "different-body\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(Core0Error, "checked source artifact differs"):
                gate2._verify_profile_source_identity(
                    root=root,
                    outputs=outputs,
                    manifests={"O0": manifest, "O2": copy.deepcopy(manifest)},
                )

            (outputs["O2"] / "scalar-suite-normalized.txt").write_text(
                "checked-body\n", encoding="utf-8"
            )
            provenance = json.loads(
                (outputs["O2"] / "provenance.json").read_text(encoding="utf-8")
            )
            provenance["source_inputs"][0]["sha256"] = "9" * 64
            (outputs["O2"] / "provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            with self.assertRaisesRegex(Core0Error, "one source snapshot"):
                gate2._verify_profile_source_identity(
                    root=root,
                    outputs=outputs,
                    manifests={"O0": manifest, "O2": copy.deepcopy(manifest)},
                )


class SafeResultInvalidationTests(unittest.TestCase):
    def test_only_an_exact_file_below_build_may_be_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            safe = root / "build" / "gate2" / "gate2-results.json"
            safe.parent.mkdir(parents=True)
            safe.write_text("pass", encoding="utf-8")
            build_core0.invalidate_output_file(safe, root)
            self.assertFalse(safe.exists())

            outside = root / "outside" / "gate2-results.json"
            outside.parent.mkdir()
            outside.write_text("unrelated", encoding="utf-8")
            with self.assertRaisesRegex(Core0Error, "outside"):
                build_core0.invalidate_output_file(outside, root)
            self.assertEqual(outside.read_text(encoding="utf-8"), "unrelated")


if __name__ == "__main__":
    unittest.main()
