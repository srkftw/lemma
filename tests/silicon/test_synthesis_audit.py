# SPDX-License-Identifier: Apache-2.0
"""Fail-closed inventory checks for physical-feasibility netlists."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import silicon_synth


class SynthesisAuditTests(unittest.TestCase):
    def inspect(self, cells, *, memories=None, mapped=False, library=None):
        modules = {"slice": {"cells": cells}}
        if memories is not None:
            modules["slice"]["memories"] = memories
        modules.update(library or {})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "netlist.json"
            path.write_text(json.dumps({"modules": modules}))
            return silicon_synth.inspect_netlist(path, "slice", mapped)

    def test_residual_memory_is_not_a_completed_register_implementation(self):
        with self.assertRaisesRegex(RuntimeError, "Residual memory"):
            self.inspect({"gate": {"type": "$_AND_"}},
                         memories={"ram": {"width": 64, "size": 512}})

    def test_latches_and_unresolved_macros_are_rejected(self):
        for cell_type in ("$_DLATCH_P_", "$mem_v2", "unqualified_sram"):
            with self.subTest(cell_type=cell_type), self.assertRaises(RuntimeError):
                self.inspect({"instance": {"type": cell_type}})

    def test_mapped_cells_need_actual_library_definitions(self):
        with self.assertRaisesRegex(RuntimeError, "Unresolved/unmapped"):
            self.inspect({"gate": {"type": "sg13g2_and2_1"}}, mapped=True)
        result = self.inspect({"gate": {"type": "sg13g2_and2_1"}}, mapped=True,
                              library={"sg13g2_and2_1": {"attributes": {"blackbox": 1}}})
        self.assertEqual(result["cells"], 1)
        self.assertEqual(result["inferred_memory_bits"], 0)

    def test_expired_process_is_reaped_and_cannot_become_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "command.log"
            with self.assertRaises(silicon_synth.CommandFailure) as raised:
                silicon_synth.run([sys.executable, "-c", "import time; time.sleep(10)"],
                                  log, time.monotonic() + 0.1)
            record = raised.exception.record
            self.assertTrue(record["timed_out"])
            self.assertLess(record["seconds"], 5)
            self.assertNotEqual(record["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
