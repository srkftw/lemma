"""Host evidence rejection tests; these never establish target execution."""
from collections import Counter, deque
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from check_kernel_tasks import Trace, validate_sleeping_idle, arithmetic_ranges
from core0_common import Core0Error


class TaskObservationTests(unittest.TestCase):
    def trace(self):
        # Deliberately tiny synthetic invalid-evidence fixture. The actual
        # checker requires audited artifacts and a real live Session.
        trace = object.__new__(Trace)
        trace.current, trace.remaining, trace.irq, trace.now = 1024, 481, 4, 200
        trace.users = {"busy": {"function_ranges": {"loop": {"base": 0x10100, "bytes": 64}},
                                "syscall_bridge": {"ecall_pc": 0x10200}, "exit_ecall_pc": 0x10020}}
        trace.images = {}
        trace.tasks = {1024: {"key": "busy", "image": 2, "nonce": 7, "root": 0x82001000,
                             "pages": 18, "reaped": False, "dispatches": 2,
                             "reasons": Counter({1: 1}), "preempt_irqs": [3],
                             "terminal": None, "stats": None}}
        trace.creation_queue, trace.idle, trace.queries, trace.acks = deque(), [], [], []
        trace.pending_ack = None
        return trace

    def test_rejects_wrong_task_context(self):
        with self.assertRaises(Core0Error):
            self.trace().observe((0xf2, 1536, 1, 5, 0x10110))

    def test_rejects_cooperative_noncooperative_evidence(self):
        with self.assertRaises(Core0Error):
            self.trace().observe((0xf2, 1024, 2, 5, 0x10200))

    def test_rejects_preempt_pc_outside_audited_image(self):
        for pc in (0x10102, 0x10140, 0x80200000):
            with self.subTest(pc=pc), self.assertRaises(Core0Error):
                self.trace().observe((0xf2, 1024, 1, 5, pc))

    def test_rejects_hardware_counter_reversal(self):
        for count in (2, 4):
            with self.subTest(count=count), self.assertRaises(Core0Error):
                self.trace().observe((0xf2, 1024, 1, count, 0x10110))

    def test_empty_table_wfi_cannot_certify_sleeping_tasks(self):
        rows = [{"record": [0xfd, 100, 2, 1, 200], "live_task_states": {}},
                {"record": [0xfd, 200, 3, 0, 300], "live_task_states": {"1024": 4, "1536": 4}}]
        with self.assertRaises(Core0Error):
            validate_sleeping_idle(rows, [1024, 1536])

    def test_one_blocked_peer_cannot_certify_all_sleeping(self):
        rows = [{"record": [0xfd, 100, 2, 1, 200], "live_task_states": {"1024": 4, "1536": 2}}]
        with self.assertRaises(Core0Error):
            validate_sleeping_idle(rows, [1024, 1536])

    def test_rejects_active_stack_reclamation(self):
        trace = self.trace()
        trace.tasks[1024]["stats"] = [0xf5, 1024, 1, 0, 2]
        with self.assertRaises(Core0Error):
            trace.observe((0xf6, 1024, 481, 499, 0))

    def test_rejects_page_leak_hidden_by_terminal_record(self):
        trace = self.trace()
        trace.current = None
        trace.tasks[1024]["stats"] = [0xf5, 1024, 1, 0, 2]
        with self.assertRaises(Core0Error):
            trace.observe((0xf6, 1024, 481, 498, 0))

    def test_rejects_stale_identity_after_reclamation(self):
        trace = self.trace()
        trace.current = None
        trace.tasks[1024]["reaped"] = True
        with self.assertRaises(Core0Error):
            trace.observe((0xfc, 1024, 2, 7, 1))

    def test_rejects_unmatched_acknowledgment(self):
        trace = self.trace()
        trace.current = None
        with self.assertRaises(Core0Error):
            trace.observe((0xf7, 0x31, 0, 499, 0))

    def test_startup_preemption_cannot_certify_arithmetic_context(self):
        trace = self.trace()
        trace.tasks[1024].update(image=0, key="compute", start=True, complete=False,
                                 rounds=[None] * 8, wakes=[], acc=7, arithmetic_preemptions=[])
        with self.assertRaisesRegex(Core0Error, "actual interruption inside"):
            trace.observe((0xfa, 1024, 7, 7 ^ 0x1375a94f2468bace, 7))

    def test_unrelated_backward_branch_cannot_certify_churn_loop(self):
        unit = {"functions": [{"source": "Lemma.User.Development.Tasks.Compute.churn", "symbol": "churn"},
                               {"source": "Lemma.User.Development.Tasks.Compute.chunk", "symbol": "round"}]}
        functions = {"churn": {"base": 0x10100, "bytes": 32}, "round": {"base": 0x10200, "bytes": 64}}
        with self.assertRaisesRegex(Core0Error, "churn-call-containing"):
            arithmetic_ranges(unit, functions, " 10210: jalr -0x10(ra) <other>\n 10220: j 0x10210 <round+0x10>\n")


if __name__ == "__main__":
    unittest.main()
