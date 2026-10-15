"""Admission failures that could otherwise overstate the course Save receipt."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_course_save import CourseSave, rtl_idle
import check_course_save


class CourseSaveObserverTests(unittest.TestCase):
    def test_retained_completed_io_and_large_counters(self):
        counter = (1 << 63) + 17
        state = dict.fromkeys(("event_queue", "pen_queue", "uart_queue", "paper_busy",
                              "panel_pending_pixels", "block_state", "dma_outstanding"), 0)
        state["backing_io"] = dict(phase=2, next_id=counter + 1, completed=counter,
                                   durable_barrier=counter, observed_write=counter - 1,
                                   retry_ready=False, fork_suspended=False, orphan=False,
                                   poisoned=False)
        self.assertTrue(rtl_idle(state))
        state["backing_io"]["phase"] = 1
        self.assertFalse(rtl_idle(state))
        state["backing_io"]["phase"] = 2
        state["backing_io"]["poisoned"] = True
        self.assertFalse(rtl_idle(state))
        state["backing_io"]["completed"] = float(counter)
        with self.assertRaisesRegex(ValueError, "counter schema"):
            rtl_idle(state)

    def finish_census(self, extra_import):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".course-save-observer-") as name:
            directory = Path(name)
            known, late = directory / "known.py", directory / "late.py"
            known.write_bytes(b"# source bound before launch\n")
            late.write_bytes(b"# imported only during shutdown\n")
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            inputs = {str(known.relative_to(ROOT)): digest(known)}
            final = dict(inputs)
            if extra_import:
                final[str(late.relative_to(ROOT))] = digest(late)
            census = directory / "imports.json"
            census.write_text(json.dumps(final))
            actor = CourseSave.__new__(CourseSave)
            actor.directory, actor.sessions, actor.commands = directory, [], io.StringIO()
            actor.started, actor.frozen, actor.censuses = time.monotonic(), inputs, [census]
            actor.report = {"status": "PASS"}
            actor.finish()
            return json.loads((directory / "result.json").read_text())

    def test_final_census_admits_unchanged_closure(self):
        result = self.finish_census(False)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["cleanup_errors"], [])
        self.assertTrue(result["consumed_host_current_equal"])

    def test_late_cli_import_cannot_turn_into_pass(self):
        result = self.finish_census(True)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("unannounced CLI import" in error for error in result["cleanup_errors"]))

    def test_cli_rejects_failure_discovered_during_finalization(self):
        actor = mock.Mock()
        actor.report = {"status": "PASS_REAL_COURSE_ANNOTATION_IDLE_SAVE_COLD_REOPEN"}
        actor.finish.side_effect = lambda: actor.report.update(status="FAIL")
        arguments = ["check_course_save.py", "--backend", "qemu", "--disk", "source.raw",
                     "--package", "course.lcp", "--work-dir", "unused",
                     "--guest-source-root", "archive", "--native-bundle", "bundle",
                     "--guest-build", "guest"]
        with mock.patch.object(sys, "argv", arguments), \
                mock.patch.object(check_course_save, "CourseSave", return_value=actor), \
                mock.patch.object(check_course_save.resource, "setrlimit"):
            with self.assertRaisesRegex(ValueError, "failed during finalization"):
                check_course_save.main()
        actor.execute.assert_called_once_with()
        actor.finish.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
