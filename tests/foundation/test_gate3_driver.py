#!/usr/bin/env python3
"""Focused command-level tests for the cumulative Gate 3 driver."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_foundation_gate3 as gate3  # noqa: E402
from core0_common import CommandResult, Core0Error  # noqa: E402


def _result(argv: tuple[str, ...], stdout: str) -> CommandResult:
    return CommandResult(argv, 0, stdout.encode("utf-8"), b"", 0.0)


class PinnedLeanSourceRealizationTests(unittest.TestCase):
    def _fixture(self, temporary: str) -> tuple[Path, Path, Path]:
        root = Path(temporary)
        source_root = root / "nix-store" / "lean-source"
        lean_prefix = root / "lean-prefix"
        header = lean_prefix / "include" / "lean" / "lean.h"
        header.parent.mkdir(parents=True)
        header.write_text("pinned header fixture\n", encoding="utf-8")

        lock_path = root / "tooling" / "toolchain-lock.json"
        lock_path.parent.mkdir()
        lock_path.write_text(
            json.dumps(
                {
                    "tools": {
                        "lean": {
                            "version": gate3.PINNED_LEAN_VERSION,
                            "revision": gate3.PINNED_LEAN_REVISION,
                            "source_ref": "pinned-source-fixture",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return root, source_root, lean_prefix

    def test_pinned_source_is_realized_before_its_file_and_hash_are_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, source_root, lean_prefix = self._fixture(temporary)
            uint_source = source_root / "src" / "Init" / "Data" / "UInt" / "Basic.lean"
            calls: list[tuple[str, ...]] = []

            def checked(
                argv: tuple[str, ...],
                *,
                cwd: Path,
                timeout_seconds: float,
            ) -> CommandResult:
                command = tuple(argv)
                calls.append(command)
                self.assertEqual(cwd, root)
                self.assertEqual(timeout_seconds, 17.0)
                if command == ("lean", "--version"):
                    return _result(
                        command, f"Lean (version {gate3.PINNED_LEAN_VERSION}, fixture)\n"
                    )
                if command == ("lean", "--githash"):
                    return _result(command, gate3.PINNED_LEAN_REVISION + "\n")
                if command[:2] == ("nix", "build"):
                    self.assertFalse(uint_source.exists())
                    uint_source.parent.mkdir(parents=True)
                    uint_source.write_text("pinned UInt fixture\n", encoding="utf-8")
                    return _result(command, str(source_root) + "\n")
                if command[:2] == ("nix", "eval"):
                    self.fail("an eval-only lookup does not realize the pinned source")
                if command == ("lean", "--print-prefix"):
                    return _result(command, str(lean_prefix) + "\n")
                self.fail(f"unexpected command: {command!r}")

            def digest(path: Path) -> str:
                if path == uint_source:
                    return gate3.PINNED_UINT_SOURCE_SHA256
                if path == lean_prefix / "include" / "lean" / "lean.h":
                    return gate3.PINNED_LEAN_HEADER_SHA256
                return "a" * 64

            with mock.patch.object(gate3, "checked", side_effect=checked), mock.patch.object(
                gate3, "sha256", side_effect=digest
            ):
                provenance = gate3._pinned_lean_provenance(
                    root=root, timeout_seconds=17.0
                )

            source_command = calls[2]
            self.assertEqual(
                source_command[:6],
                (
                    "nix",
                    "build",
                    "--no-link",
                    "--print-out-paths",
                    "--impure",
                    "--expr",
                ),
            )
            self.assertIn("in pkgs.lean4.src", source_command[6])
            self.assertIn('builtins.getFlake ("git+file://" + toString ./.)', source_command[6])
            self.assertNotIn("builtins.getFlake (toString ./.)", source_command[6])
            self.assertNotIn("src.outPath", source_command[6])
            self.assertFalse(any(command[:2] == ("nix", "eval") for command in calls))
            self.assertTrue(uint_source.is_file())
            self.assertEqual(provenance["uint_source"], str(uint_source))
            self.assertEqual(provenance["commands"][2], list(source_command))

    def test_source_realization_rejects_zero_multiple_or_relative_outputs(self) -> None:
        cases = (
            ("", "exactly one output path; observed 0"),
            ("/nix/store/one\n/nix/store/two\n", "exactly one output path; observed 2"),
            ("relative-source\n", "returned a non-absolute path"),
        )
        for stdout, diagnostic in cases:
            with self.subTest(stdout=stdout), tempfile.TemporaryDirectory() as temporary:
                root, _source_root, _lean_prefix = self._fixture(temporary)

                def checked(
                    argv: tuple[str, ...],
                    *,
                    cwd: Path,
                    timeout_seconds: float,
                ) -> CommandResult:
                    command = tuple(argv)
                    if command == ("lean", "--version"):
                        return _result(
                            command,
                            f"Lean (version {gate3.PINNED_LEAN_VERSION}, fixture)\n",
                        )
                    if command == ("lean", "--githash"):
                        return _result(command, gate3.PINNED_LEAN_REVISION + "\n")
                    if command[:2] == ("nix", "build"):
                        return _result(command, stdout)
                    self.fail(f"unexpected command after invalid realization: {command!r}")

                with mock.patch.object(gate3, "checked", side_effect=checked):
                    with self.assertRaisesRegex(Core0Error, diagnostic):
                        gate3._pinned_lean_provenance(
                            root=root, timeout_seconds=17.0
                        )

    def test_realization_cannot_return_an_unmaterialized_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root, source_root, _lean_prefix = self._fixture(temporary)

            def checked(
                argv: tuple[str, ...],
                *,
                cwd: Path,
                timeout_seconds: float,
            ) -> CommandResult:
                command = tuple(argv)
                if command == ("lean", "--version"):
                    return _result(
                        command, f"Lean (version {gate3.PINNED_LEAN_VERSION}, fixture)\n"
                    )
                if command == ("lean", "--githash"):
                    return _result(command, gate3.PINNED_LEAN_REVISION + "\n")
                if command[:2] == ("nix", "build"):
                    return _result(command, str(source_root) + "\n")
                self.fail(f"unexpected command after missing source output: {command!r}")

            with mock.patch.object(gate3, "checked", side_effect=checked):
                with self.assertRaisesRegex(Core0Error, "pinned UInt source is missing"):
                    gate3._pinned_lean_provenance(root=root, timeout_seconds=17.0)


if __name__ == "__main__":
    unittest.main()
