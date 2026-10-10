"""Host malformed-evidence fixtures; target lifecycle claims require a live VM."""
from collections import Counter, deque
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_kernel_lifecycle import LifecycleTrace
from core0_common import Core0Error


class LifecycleEvidenceTests(unittest.TestCase):
    def trace(self):
        trace = object.__new__(LifecycleTrace)
        trace.current, trace.irq, trace.remaining = 1024, 5, 480
        trace.owners, trace.physical, trace.faults, trace.pressures = {2}, {}, [], []
        trace.pending_pressure = None
        trace.fault_pc, trace.fault_word = 0x10120, 0x10002573
        trace.creation_queue, trace.acks = deque(), []
        trace.pending_ack = None
        trace.tasks = {1024: {"image": 3, "key": "fault", "nonce": 19,
                             "dispatches": 1, "start": True, "reaped": False,
                             "terminal": None, "reasons": Counter(), "state": 3}}
        return trace

    def test_wrong_actual_fault_cause_pc_word_or_origin_rejected(self):
        for event in ((0xd4, 8, 0x10120, 0x10002573, 0x200000020),
                      (0xd4, 2, 0x10124, 0x10002573, 0x200000020),
                      (0xd4, 2, 0x10120, 0, 0x200000020),
                      (0xd4, 2, 0x10120, 0x10002573, 0x200000120)):
            with self.subTest(event=event), self.assertRaises(Core0Error):
                self.trace().observe(event)

    def test_fault_return_without_architectural_record_rejected(self):
        with self.assertRaises(Core0Error):
            self.trace().observe((0xf2, 1024, 5, 6, 0x10120))

    def test_fault_termination_without_actual_return_rejected(self):
        trace = self.trace()
        trace.observe((0xd4, 2, 0x10120, 0x10002573, 0x200000020))
        trace.current = None
        with self.assertRaises(Core0Error):
            trace.observe((0xf4, 1024, 44, 19, 2))

    def test_old_bss_or_stack_secret_rejected(self):
        for tail in ((1, 0), (0, 19)):
            trace = self.trace()
            trace.tasks[1024]["start"] = False
            trace.physical[1024] = [0xfe, 1024, 0x82003000, 0x82004020, 3]
            with self.subTest(tail=tail), self.assertRaises(Core0Error):
                trace.observe((0xe8, 1024, 19, *tail))

    def test_live_peer_page_alias_rejected(self):
        trace = self.trace()
        trace.current = None
        trace.tasks[1024]["dispatches"] = 0
        trace.tasks[1536] = {"reaped": False}
        trace.physical[1536] = [0xfe, 1536, 0x82003000, 0x82004020, 2]
        with self.assertRaises(Core0Error):
            trace.observe((0xfe, 1024, 0x82004000, 0x82005020, 3))

    def test_pressure_partial_rollback_or_leaked_holds_rejected(self):
        trace = self.trace()
        trace.current = None
        trace.pending_pressure = {"image": 0, "held": 15}
        with self.assertRaises(Core0Error):
            trace.observe((0xe9, 0, 38, 480, 465))
        trace.observe((0xe9, 0, 38, 480, 464))
        for event in ((0xea, 3, 15, 16, 480), (0xea, 3, 15, 15, 479), (0xea, 2, 15, 15, 480)):
            with self.subTest(event=event), self.assertRaises(Core0Error):
                trace.observe(event)

    def test_duplicate_pressure_cleanup_rejected(self):
        trace = self.trace()
        trace.current = None
        trace.pending_pressure = {"image": 0, "held": 15}
        trace.observe((0xe9, 0, 38, 480, 464))
        trace.observe((0xea, 3, 15, 15, 480))
        with self.assertRaises(Core0Error):
            trace.observe((0xea, 4, 15, 15, 480))


if __name__ == "__main__":
    unittest.main()
