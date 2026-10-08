#!/usr/bin/env python3
"""Fail-closed source/profile rejection tests for Core0 v0.3 loops."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REJECT_ROOT = ROOT / "examples/foundation/gate4-reject"
MANIFEST = REJECT_ROOT / "rejections.json"
TIMEOUT_SECONDS = 30.0
EXPECTED_FILES = (
    "CapturingCallback.lean",
    "DirectExternCallback.lean",
    "DynamicCallback.lean",
    "HiddenForbiddenCallback.lean",
    "LookalikeCombinator.lean",
    "NonliteralBudget.lean",
    "OverBudget.lean",
    "PolymorphicCallback.lean",
    "RecursiveCallback.lean",
    "V01BoundedLoop.lean",
    "V02BoundedLoop.lean",
)


def load_manifest() -> dict[str, object]:
    with MANIFEST.open("r", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise AssertionError("Gate 4 rejection manifest is not an object")
    return value


def run_lean(path: Path) -> tuple[int, str]:
    if shutil.which("lake") is None:
        raise AssertionError("lake is unavailable; run inside the pinned Nix environment")
    completed = subprocess.run(
        ("lake", "env", "lean", str(path.relative_to(ROOT))),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    output = completed.stdout.decode("utf-8", errors="replace")
    output += completed.stderr.decode("utf-8", errors="replace")
    return completed.returncode, output


class Gate4ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest()

    def test_manifest_is_exact_and_closed_over_quarantine(self) -> None:
        self.assertEqual(
            set(self.manifest),
            {"schema_version", "profile", "legacy_profiles", "cases"},
        )
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["profile"], "core0-v0.3")
        self.assertEqual(self.manifest["legacy_profiles"], ["core0-v0.1", "core0-v0.2"])
        cases = self.manifest["cases"]
        self.assertIsInstance(cases, list)
        self.assertEqual(len(cases), 11)
        paths: list[Path] = []
        names: set[str] = set()
        for index, (case, expected_file) in enumerate(zip(cases, EXPECTED_FILES, strict=True)):
            self.assertIsInstance(case, dict)
            self.assertEqual(
                set(case), {"name", "path", "diagnostic_code", "required_fragments"}
            )
            self.assertIsInstance(case["name"], str)
            self.assertTrue(case["name"])
            self.assertNotIn(case["name"], names)
            names.add(case["name"])
            path = (ROOT / case["path"]).resolve()
            self.assertEqual(path.parent, REJECT_ROOT.resolve())
            self.assertEqual(path.name, expected_file)
            self.assertTrue(path.is_file())
            paths.append(path)
            fragments = case["required_fragments"]
            self.assertIsInstance(fragments, list)
            self.assertTrue(fragments)
            self.assertTrue(all(isinstance(fragment, str) and fragment for fragment in fragments))
            text = path.read_text(encoding="utf-8")
            command = (
                "#core0_check " if expected_file == "V01BoundedLoop.lean"
                else "#core0_check_v0_2 " if expected_file == "V02BoundedLoop.lean"
                else "#core0_check_v0_3 "
            )
            self.assertEqual(len(re.findall(rf"(?m)^{re.escape(command)}", text)), 1)
        self.assertEqual(set(paths), set(REJECT_ROOT.glob("*.lean")))

    def test_every_fixture_fails_with_one_total_intended_core0_error(self) -> None:
        for case in self.manifest["cases"]:
            with self.subTest(case=case["name"]):
                source = (ROOT / case["path"]).resolve()
                returncode, output = run_lean(source)
                self.assertNotEqual(returncode, 0, output)
                error_lines = [
                    line for line in output.splitlines()
                    if re.search(r"(?:^|:\s)error:", line) is not None
                ]
                self.assertEqual(len(error_lines), 1, output)
                marker = f"Core0[{case['diagnostic_code']}]"
                self.assertIn(marker, error_lines[0], output)
                for fragment in case["required_fragments"]:
                    self.assertIn(fragment, output)

    def test_legacy_profiles_are_explicit_distinct_rejections(self) -> None:
        by_name = {case["name"]: case for case in self.manifest["cases"]}
        for name, command in (
            ("v01-bounded-loop", "#core0_check root"),
            ("v02-bounded-loop", "#core0_check_v0_2 root"),
        ):
            text = (ROOT / by_name[name]["path"]).read_text(encoding="utf-8")
            self.assertIn(command, text)
            self.assertIn("requires core0-v0.3", "\n".join(by_name[name]["required_fragments"]))


if __name__ == "__main__":
    unittest.main()
