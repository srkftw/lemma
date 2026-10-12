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

    def test_lvs_requires_the_final_top_level_match_without_property_errors(self):
        for suffix in ("\n", "\n.\n"):
            self.assertTrue(silicon_synth.lvs_matches(
                "Netlists match uniquely.\n\nFinal result: Circuits match uniquely." + suffix))
        for report in (
            "Netlists match uniquely.\nFinal result: Top level cell failed pin matching.\n",
            "Final result: Circuits match uniquely.\n.\n\nThe following cells had property errors:\n child\n",
            "Circuits match uniquely.\n",  # Missing final result.
            "Final result: Circuits match uniquely.\nFinal result: Circuits match uniquely.\n",
            "",
        ):
            with self.subTest(report=report):
                self.assertFalse(silicon_synth.lvs_matches(report))

    def test_router_violations_are_independent_of_process_drc_and_exit_status(self):
        self.assertEqual(silicon_synth.router_drc("0\n")["status"], "PASS")
        result = silicon_synth.router_drc("47\n")
        self.assertEqual((result["status"], result["violations"]), ("FAIL", 47))
        for count in ("", "-1", "0.0", "unknown", "0\n47\n"):
            with self.subTest(count=count), self.assertRaises(RuntimeError):
                silicon_synth.router_drc(count)

    def test_pinned_opensta_summary_retains_violated_setup_and_met_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "global-route-summary.json").write_text('{"instances":90320}')
            # Exact format observed in the retained real controller reports.
            (out / "global-setup-summary.rpt").write_text("worst slack max -12.73\n")
            (out / "global-hold-summary.rpt").write_text("worst slack min 0.03\n")
            result = silicon_synth.layout_reports(out, global_route=True)
            self.assertEqual((result["setup_timing"], result["setup_worst_slack_ns"]),
                             ("VIOLATED", -12.73))
            self.assertEqual((result["hold_timing"], result["hold_worst_slack_ns"]),
                             ("MET", 0.03))
            for report in ("worst slack min -12.73\n", "", "worst slack max nan\n",
                           "worst slack max 0\nworst slack max -12.73\n"):
                (out / "global-setup-summary.rpt").write_text(report)
                with self.subTest(report=report), self.assertRaises(RuntimeError):
                    silicon_synth.layout_reports(out, global_route=True)

    def test_small_negative_slack_and_negative_zero_do_not_become_met(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "global-route-summary.json").write_text('{"instances":1}')
            (out / "global-hold-summary.rpt").write_text("worst slack min 0.000001\n")
            for value in ("-0.000001", "-0.000000", "-0.00"):
                (out / "global-setup-summary.rpt").write_text(f"worst slack max {value}\n")
                result = silicon_synth.layout_reports(out, global_route=True)
                with self.subTest(value=value):
                    self.assertEqual(result["setup_timing"], "VIOLATED")
                    self.assertEqual(result["hold_timing"], "MET")
            (out / "global-setup-summary.rpt").write_text("worst slack max 0.000001\n")
            self.assertEqual(silicon_synth.layout_reports(out, global_route=True)["setup_timing"], "MET")

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
