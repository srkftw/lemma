#!/usr/bin/env python3
"""Fail-closed source/profile rejection tests for the Core0 v0.2 scalar gate."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE3_REJECT_ROOT = ROOT / "examples" / "foundation" / "gate3-reject"
GATE3_MANIFEST = GATE3_REJECT_ROOT / "rejections.json"
LEGACY_MANIFEST = ROOT / "tests" / "core0" / "rejections.json"
LEAN_TIMEOUT_SECONDS = 30.0


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as source:
        return json.load(source)


def _relative_lean_path(value: object, *, parent: Path) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise AssertionError(f"fixture path must be nonempty and repository-relative: {value!r}")
    resolved = (ROOT / value).resolve()
    try:
        resolved.relative_to(parent.resolve())
    except ValueError as error:
        raise AssertionError(f"fixture escapes {parent.relative_to(ROOT)}: {value}") from error
    if resolved.suffix != ".lean" or not resolved.is_file():
        raise AssertionError(f"fixture is missing or is not Lean source: {value}")
    return resolved


def _run_lean(source: Path) -> tuple[int, str]:
    if shutil.which("lake") is None:
        raise AssertionError("lake is unavailable; run the profile tests in the pinned Nix environment")
    try:
        completed = subprocess.run(
            ("lake", "env", "lean", str(source.relative_to(ROOT))),
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=LEAN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"Lean profile fixture timed out: {source.relative_to(ROOT)}") from error
    output = completed.stdout.decode("utf-8", errors="replace")
    output += completed.stderr.decode("utf-8", errors="replace")
    return completed.returncode, output


def _required_fragments(value: object, *, context: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(fragment, str) or not fragment for fragment in value)
        or len(set(value)) != len(value)
    ):
        raise AssertionError(f"{context} has invalid required diagnostic fragments")
    return tuple(value)


def _require_intended_core0_rejection(
    *, returncode: int, output: str, code: str, fragments: tuple[str, ...], context: str
) -> None:
    if returncode == 0:
        raise AssertionError(f"negative fixture unexpectedly passed: {context}")
    marker = f"Core0[{code}]"
    if output.count("error: Core0[") != 1 or marker not in output:
        raise AssertionError(
            f"negative fixture did not fail with exactly one intended Core0 diagnostic "
            f"({context}, expected {marker!r}):\n{output}"
        )
    unrelated = (
        "lean.unknownIdentifier",
        "declaration uses 'sorry'",
        "Aborting evaluation",
    )
    present_unrelated = [fragment for fragment in unrelated if fragment in output]
    if present_unrelated:
        raise AssertionError(
            f"negative fixture also had unrelated failures ({context}): {present_unrelated!r}"
        )
    absent = [fragment for fragment in fragments if fragment not in output]
    if absent:
        raise AssertionError(
            f"negative fixture lacked intended diagnostics ({context}): {absent!r}\n{output}"
        )


class Gate3ProfileManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = _load_json(GATE3_MANIFEST)
        if not isinstance(raw, dict):
            raise AssertionError("Gate 3 rejection manifest is not an object")
        cls.manifest = raw

    def test_manifest_is_closed_and_all_fixtures_are_profile_scoped(self) -> None:
        self.assertEqual(
            set(self.manifest),
            {"schema_version", "profile", "legacy_profile", "cases", "probes"},
        )
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(self.manifest["profile"], "core0-v0.2")
        self.assertEqual(self.manifest["legacy_profile"], "core0-v0.1")

        cases = self.manifest["cases"]
        probes = self.manifest["probes"]
        self.assertIsInstance(cases, list)
        self.assertIsInstance(probes, list)
        self.assertGreaterEqual(len(cases), 7)
        self.assertEqual(len(probes), 1)

        names: set[str] = set()
        paths: set[Path] = set()
        for index, entry in enumerate(cases):
            self.assertIsInstance(entry, dict)
            self.assertEqual(
                set(entry),
                {"name", "path", "diagnostic_code", "required_fragments"},
            )
            name = entry["name"]
            code = entry["diagnostic_code"]
            self.assertIsInstance(name, str)
            self.assertTrue(name)
            self.assertNotIn(name, names)
            names.add(name)
            self.assertIn(
                code,
                {
                    "invalid-primitive-instance",
                    "unsupported-type",
                    "unsupported-declaration",
                },
            )
            _required_fragments(entry["required_fragments"], context=f"case #{index}")
            source = _relative_lean_path(entry["path"], parent=GATE3_REJECT_ROOT)
            self.assertNotIn(source, paths)
            paths.add(source)
            text = source.read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"(?m)^#core0_check_v0_2\s+", text)), 1)
            self.assertNotRegex(text, r"(?m)^#core0_check\s+")

        for index, entry in enumerate(probes):
            self.assertIsInstance(entry, dict)
            self.assertEqual(set(entry), {"name", "path", "required_fragments"})
            name = entry["name"]
            self.assertIsInstance(name, str)
            self.assertTrue(name)
            self.assertNotIn(name, names)
            names.add(name)
            _required_fragments(entry["required_fragments"], context=f"probe #{index}")
            source = _relative_lean_path(entry["path"], parent=GATE3_REJECT_ROOT)
            self.assertNotIn(source, paths)
            paths.add(source)

        self.assertEqual(paths, set(GATE3_REJECT_ROOT.glob("*.lean")))

    def test_v02_negative_fixtures_fail_for_the_exact_declared_reason(self) -> None:
        for entry in self.manifest["cases"]:
            with self.subTest(case=entry["name"]):
                source = _relative_lean_path(entry["path"], parent=GATE3_REJECT_ROOT)
                returncode, output = _run_lean(source)
                _require_intended_core0_rejection(
                    returncode=returncode,
                    output=output,
                    code=entry["diagnostic_code"],
                    fragments=_required_fragments(
                        entry["required_fragments"], context=entry["name"]
                    ),
                    context=str(source.relative_to(ROOT)),
                )

    def test_unsupported_profile_is_rejected_by_parser_and_model(self) -> None:
        probe = self.manifest["probes"][0]
        fragments = _required_fragments(
            probe["required_fragments"], context=probe["name"]
        )
        self.assertTrue(any("core0-v9.9" in fragment for fragment in fragments))
        self.assertFalse(any("core0-v0.3" in fragment for fragment in fragments))
        source = _relative_lean_path(probe["path"], parent=GATE3_REJECT_ROOT)
        returncode, output = _run_lean(source)
        self.assertEqual(returncode, 0, output)
        self.assertNotIn("error:", output)
        for fragment in fragments:
            self.assertIn(fragment, output)

    def test_v01_division_shift_and_complement_rejections_remain_separate(self) -> None:
        raw = _load_json(LEGACY_MANIFEST)
        self.assertIsInstance(raw, dict)
        self.assertEqual(raw.get("schema_version"), 1)
        cases = raw.get("cases")
        self.assertIsInstance(cases, list)
        by_name = {entry.get("name"): entry for entry in cases if isinstance(entry, dict)}
        expected_names = {"unsupported-division", "unsupported-shift", "unsupported-complement"}
        self.assertTrue(expected_names <= set(by_name))

        gate3_paths = {entry["path"] for entry in self.manifest["cases"]}
        for name in sorted(expected_names):
            with self.subTest(case=name):
                entry = by_name[name]
                self.assertNotIn(entry["path"], gate3_paths)
                source = _relative_lean_path(
                    entry["path"], parent=ROOT / "examples" / "core0" / "reject"
                )
                text = source.read_text(encoding="utf-8")
                self.assertEqual(len(re.findall(r"(?m)^#core0_check\s+", text)), 1)
                self.assertNotIn("#core0_check_v0_2", text)
                fragments = _required_fragments(
                    entry.get("required_fragments"), context=f"legacy case {name}"
                )
                code_match = re.search(r"Core0\[([^]]+)\]", fragments[0])
                self.assertIsNotNone(code_match)
                returncode, output = _run_lean(source)
                _require_intended_core0_rejection(
                    returncode=returncode,
                    output=output,
                    code=code_match.group(1),
                    fragments=fragments,
                    context=str(source.relative_to(ROOT)),
                )


if __name__ == "__main__":
    unittest.main()
