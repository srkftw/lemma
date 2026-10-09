"""Focused host tests for the exhaustive UInt8 source/model comparison."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_gate2_exhaustive as exhaustive  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class Gate2ExhaustiveTests(unittest.TestCase):
    def test_closed_root_set_and_exact_pair_count(self) -> None:
        self.assertEqual(exhaustive.PAIR_COUNT, 65_536)
        self.assertEqual(exhaustive.EXPECTED_BYTES, 327_680)
        self.assertEqual(
            [operation for operation, _, _ in exhaustive.ROOTS],
            ["u8-add", "u8-sub", "u8-lt", "u8-le", "u8-eq"],
        )
        self.assertEqual(
            [result for _, _, result in exhaustive.ROOTS],
            ["u8", "u8", "bool", "bool", "bool"],
        )

    def test_direct_driver_has_no_core0_import_or_evaluator(self) -> None:
        source = (ROOT / exhaustive.SOURCE_DRIVER).read_text(encoding="utf-8")
        imports = [line for line in source.splitlines() if line.startswith("import ")]
        self.assertEqual(imports, ["import examples.foundation.Conformance"])
        self.assertNotIn("Lemma.Core0", source)
        self.assertNotIn("checkAndLower", source)
        self.assertNotIn("evalProgram", source)
        for _, root, _ in exhaustive.ROOTS:
            self.assertIn(root, source)

    def test_model_support_uses_checked_frontend_and_semantics(self) -> None:
        source = (ROOT / exhaustive.MODEL_SUPPORT).read_text(encoding="utf-8")
        self.assertIn("Lemma.Core0.checkAndLower", source)
        self.assertIn("Lemma.Core0.evalProgram", source)
        self.assertNotIn("native_decide", source)
        self.assertNotIn("sorry", source)

    def test_model_driver_has_fixed_order_and_unbounded_lean_heartbeat_only(self) -> None:
        driver = exhaustive._render_model_driver(Path("/tmp/model result.bin"))
        self.assertEqual(driver.count("#core0_exhaustive_u8_model"), 1)
        self.assertIn("set_option maxHeartbeats 0", driver)
        positions = [driver.index(root) for _, root, _ in exhaustive.ROOTS]
        self.assertEqual(positions, sorted(positions))

    def test_first_mismatch_maps_to_exact_root_x_y(self) -> None:
        source = bytearray(exhaustive.EXPECTED_BYTES)
        model = bytearray(source)
        root_index, x, y = 3, 17, 249
        index = root_index * exhaustive.PAIR_COUNT + x * 256 + y
        model[index] = 1
        self.assertEqual(
            exhaustive._first_mismatch(bytes(source), bytes(model)),
            (root_index, x, y, 0, 1),
        )
        with self.assertRaisesRegex(
            Core0Error,
            r"operation=u8-le, .*x=17, y=249, direct-source=0, checked-model=1",
        ):
            exhaustive._validate_and_describe(bytes(source), bytes(model))

    def test_length_and_boolean_canonicality_fail_closed(self) -> None:
        good = bytes(exhaustive.EXPECTED_BYTES)
        with self.assertRaisesRegex(Core0Error, "direct-source.*expected 327680"):
            exhaustive._validate_and_describe(good[:-1], good)
        noncanonical = bytearray(good)
        bool_offset = 2 * exhaustive.PAIR_COUNT
        noncanonical[bool_offset] = 2
        with self.assertRaisesRegex(Core0Error, "Bool matrix is noncanonical"):
            exhaustive._validate_and_describe(bytes(noncanonical), bytes(noncanonical))

    def test_early_failure_removes_stale_pass_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output = directory / "output"
            output.mkdir()
            stale = output / "exhaustive-u8.json"
            stale.write_text('{"status":"pass"}\n', encoding="utf-8")
            with self.assertRaisesRegex(Core0Error, "missing exhaustive UInt8 inputs"):
                exhaustive.run_exhaustive(directory / "not-a-repository", output, 1.0)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
