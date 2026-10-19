"""Real host-process ownership fixtures; these do not execute target images."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/kernel_row_supervisor.py"


class RowSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lemma-row-supervisor-")
        self.directory = Path(self.temporary.name)
        self.children = []
        self.writers = []

    def tearDown(self):
        for fd in self.writers:
            try:
                os.close(fd)
            except OSError:
                pass
        for child in self.children:
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        self.temporary.cleanup()

    def wait_file(self, path, *, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if path.exists():
                return path.read_text()
            time.sleep(.01)
        self.fail(f"host fixture did not publish {path.name}")

    def start(self, name, source, *, timeout=10, term_grace=.1, inherited_blocked_mask=False):
        receipt, log = self.directory / (name + ".json"), self.directory / (name + ".log")
        read_fd, write_fd = os.pipe()
        self.writers.append(write_fd)
        argv = [sys.executable, str(HELPER), "--parent-pid", str(os.getpid()),
                "--control-fd", str(read_fd), "--deadline", str(time.monotonic() + timeout),
                "--receipt", str(receipt), "--term-grace", str(term_grace), "--", sys.executable, "-c", source]
        previous_mask = (signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT, signal.SIGALRM})
                         if inherited_blocked_mask else None)
        try:
            with log.open("wb") as stream:
                process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream,
                                           stderr=subprocess.STDOUT, pass_fds=(read_fd,))
        finally:
            if previous_mask is not None:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
            os.close(read_fd)
        self.children.append(process)
        return process, receipt, write_fd

    def finish(self, process, receipt, *, timeout=8):
        code = process.wait(timeout=timeout)
        value = json.loads(receipt.read_text())
        self.assertEqual(code == 0, value["status"] == "PASS")
        self.assertTrue(value["cleanup_complete"], value)
        self.assertEqual(value["cleanup"]["remaining"], [])
        for row in value["owned_processes"]:
            self.assertTrue(row["start_ticks"].isdigit())
            self.assertFalse(Path(f"/proc/{row['pid']}").exists(), row)
        return value

    def tree_source(self, name, *, leader_ignores_term=True):
        ready = self.directory / (name + "-ready")
        grandchild = ("import os, signal, time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)")
        source = ("import signal, subprocess, sys, time; from pathlib import Path; "
                  + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if leader_ignores_term else "")
                  + f"subprocess.Popen([sys.executable, '-c', {grandchild!r}], start_new_session=True); "
                  + "time.sleep(60)")
        return source, ready

    def test_success_retains_real_child_status_and_inherited_output(self):
        child, receipt, _ = self.start("success", "print('actual host row output')")
        value = self.finish(child, receipt)
        self.assertEqual((value["status"], value["reason"], value["child_returncode"]),
                         ("PASS", "child-exited", 0))
        self.assertEqual(value["cleanup"]["killed"], [])
        self.assertIn("actual host row output", (self.directory / "success.log").read_text())
        self.assertEqual(len(value["cleanup"]["reaped"]), 1)

    def test_nonzero_child_is_not_success(self):
        child, receipt, _ = self.start("nonzero", "raise SystemExit(7)")
        value = self.finish(child, receipt)
        self.assertEqual((value["status"], value["reason"], value["child_returncode"]),
                         ("FAIL", "child-failed", 7))

    def test_absolute_deadline_kills_and_reaps_separate_session_descendant(self):
        source, ready = self.tree_source("timeout")
        child, receipt, _ = self.start("timeout", source, timeout=1)
        grandchild = int(self.wait_file(ready))
        value = self.finish(child, receipt)
        self.assertEqual((value["status"], value["reason"]), ("FAIL", "deadline-expired"))
        self.assertEqual(value["child_returncode"], -signal.SIGKILL)
        self.assertIn(grandchild, {row["pid"] for row in value["cleanup"]["killed"]})
        self.assertIn(grandchild, {row["pid"] for row in value["cleanup"]["reaped"]})

    def test_control_eof_cancels_owned_tree(self):
        source, ready = self.tree_source("control")
        child, receipt, writer = self.start("control", source)
        grandchild = int(self.wait_file(ready))
        os.close(writer)
        self.writers.remove(writer)
        value = self.finish(child, receipt)
        self.assertEqual(value["reason"], "control-closed")
        self.assertIn(grandchild, {row["pid"] for row in value["cleanup"]["reaped"]})

    def test_supervisor_term_reaps_tree_and_preserves_actual_returncode(self):
        source, ready = self.tree_source("term")
        child, receipt, _ = self.start("term", source)
        self.wait_file(ready)
        child.send_signal(signal.SIGTERM)
        value = self.finish(child, receipt)
        self.assertEqual(value["reason"], f"signal-{signal.SIGTERM}")
        self.assertEqual(value["child_returncode"], -signal.SIGKILL)

    def test_control_close_allows_row_to_unwind_and_reap_its_own_child(self):
        ready, unwound = self.directory / "unwind-ready", self.directory / "unwound"
        descendant = ("import os, signal, time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)")
        source = ("import signal, subprocess, sys, time; from pathlib import Path\n"
                  "def interrupted(number, frame): raise SystemExit(0)\n"
                  "signal.signal(signal.SIGTERM, interrupted)\n"
                  f"child = subprocess.Popen([sys.executable, '-c', {descendant!r}], start_new_session=True)\n"
                  "try:\n    time.sleep(60)\n"
                  "finally:\n    child.kill()\n    child.wait()\n"
                  f"    Path({str(unwound)!r}).write_text(str(child.returncode))\n")
        child, receipt, writer = self.start("unwind", source, term_grace=1)
        descendant_pid = int(self.wait_file(ready))
        os.close(writer)
        self.writers.remove(writer)
        value = self.finish(child, receipt)
        self.assertEqual((value["status"], value["reason"], value["child_returncode"]),
                         ("FAIL", "control-closed", 0))
        self.assertEqual(value["cleanup"]["killed"], [])
        self.assertEqual(unwound.read_text(), str(-signal.SIGKILL))
        self.assertFalse(Path(f"/proc/{descendant_pid}").exists())

    def test_inherited_blocked_mask_is_released_before_graceful_eof_and_deadline(self):
        for mode in ("eof", "deadline"):
            with self.subTest(mode=mode):
                ready, unwound = self.directory / (mode + "-mask-ready"), self.directory / (mode + "-mask-unwound")
                source = ("import json, os, signal, time; from pathlib import Path\n"
                          "def interrupted(number, frame): raise SystemExit(0)\n"
                          "signal.signal(signal.SIGTERM, interrupted)\n"
                          "blocked = sorted(int(number) for number in signal.pthread_sigmask(signal.SIG_BLOCK, set()))\n"
                          f"Path({str(ready)!r}).write_text(json.dumps({{'pid': os.getpid(), 'blocked': blocked}}))\n"
                          "try:\n    time.sleep(60)\n"
                          f"finally:\n    Path({str(unwound)!r}).write_text('actual row finally')\n")
                child, receipt, writer = self.start("masked-" + mode, source, timeout=1 if mode == "deadline" else 10,
                                                    term_grace=1, inherited_blocked_mask=True)
                observed = json.loads(self.wait_file(ready))
                self.assertFalse({signal.SIGTERM, signal.SIGINT, signal.SIGALRM} & set(observed["blocked"]))
                if mode == "eof":
                    os.close(writer)
                    self.writers.remove(writer)
                value = self.finish(child, receipt)
                self.assertEqual(value["reason"], "control-closed" if mode == "eof" else "deadline-expired")
                self.assertEqual(value["child_returncode"], 0)
                self.assertEqual(value["status"], "FAIL")
                self.assertEqual(value["cleanup"]["killed"], [])
                self.assertEqual(unwound.read_text(), "actual row finally")

    def test_zero_exit_with_orphan_is_rejected_and_orphan_reaped(self):
        ready = self.directory / "orphan-ready"
        descendant = ("import os, signal, time; from pathlib import Path; "
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)")
        source = ("import subprocess, sys, time; from pathlib import Path\n"
                  f"subprocess.Popen([sys.executable, '-c', {descendant!r}], start_new_session=True)\n"
                  f"while not Path({str(ready)!r}).exists(): time.sleep(.01)\n")
        child, receipt, _ = self.start("orphan", source)
        grandchild = int(self.wait_file(ready))
        value = self.finish(child, receipt)
        self.assertEqual((value["status"], value["reason"], value["child_returncode"]),
                         ("FAIL", "child-left-descendants", 0))
        self.assertIn(grandchild, {row["pid"] for row in value["descendants_at_child_exit"]})
        self.assertIn(grandchild, {row["pid"] for row in value["cleanup"]["reaped"]})

    def test_two_supervisors_do_not_claim_or_cancel_each_others_rows(self):
        source, ready = self.tree_source("first")
        first, first_receipt, first_writer = self.start("first", source)
        self.wait_file(ready)
        second_ready, finish = self.directory / "second-ready", self.directory / "second-finish"
        second_source = ("import os, time; from pathlib import Path\n"
                         f"Path({str(second_ready)!r}).write_text(str(os.getpid()))\n"
                         f"while not Path({str(finish)!r}).exists(): time.sleep(.01)\n")
        second, second_receipt, _ = self.start("second", second_source)
        second_pid = int(self.wait_file(second_ready))
        os.close(first_writer)
        self.writers.remove(first_writer)
        value = self.finish(first, first_receipt)
        self.assertNotIn(second_pid, {row["pid"] for row in value["owned_processes"]})
        self.assertIsNone(second.poll())
        self.assertTrue(Path(f"/proc/{second_pid}").exists())
        finish.touch()
        value = self.finish(second, second_receipt)
        self.assertEqual(value["status"], "PASS")

    def test_parent_sigkill_is_detected_and_descendants_are_reaped(self):
        libc, previous = ctypes.CDLL(None, use_errno=True), ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        source, ready = self.tree_source("parent-death")
        receipt, helper_pid = self.directory / "parent-death.json", self.directory / "helper-pid"
        launcher = ("import os, subprocess, sys, time; from pathlib import Path\n"
                    "reader, writer = os.pipe()\n"
                    f"argv = [sys.executable, {str(HELPER)!r}, '--parent-pid', str(os.getpid()), "
                    "'--control-fd', str(reader), '--deadline', str(time.monotonic()+10), "
                    f"'--receipt', {str(receipt)!r}, '--term-grace', '.1', '--', sys.executable, '-c', {source!r}]\n"
                    "child = subprocess.Popen(argv, pass_fds=(reader,))\n"
                    "os.close(reader)\n"
                    f"Path({str(helper_pid)!r}).write_text(str(child.pid))\n"
                    "time.sleep(60)\n")
        helper = None
        try:
            with (self.directory / "parent-death.log").open("wb") as log:
                parent = subprocess.Popen([sys.executable, "-c", launcher], stdout=log, stderr=subprocess.STDOUT)
            self.children.append(parent)
            helper = int(self.wait_file(helper_pid))
            self.wait_file(ready)
            parent.kill()
            parent.wait(timeout=5)
            value = json.loads(self.wait_file(receipt))
            end = time.monotonic() + 5
            waited = 0
            while time.monotonic() < end:
                waited, status = os.waitpid(helper, os.WNOHANG)
                if waited:
                    break
                time.sleep(.01)
            self.assertEqual(waited, helper)
            self.assertEqual(os.waitstatus_to_exitcode(status), 1)
            self.assertIn(value["reason"], {"parent-died", "control-closed", f"signal-{signal.SIGTERM}"})
            self.assertTrue(value["cleanup_complete"])
            self.assertGreaterEqual(len(value["cleanup"]["reaped"]), 2)
            for row in value["owned_processes"]:
                self.assertFalse(Path(f"/proc/{row['pid']}").exists())
        finally:
            if helper is not None and Path(f"/proc/{helper}").exists():
                os.kill(helper, signal.SIGTERM)
                os.waitpid(helper, 0)
            libc.prctl(36, previous.value, 0, 0, 0)

    def test_expired_deadline_does_not_launch_row(self):
        marker = self.directory / "must-not-run"
        child, receipt, _ = self.start("expired", f"from pathlib import Path; Path({str(marker)!r}).touch()", timeout=-1)
        value = self.finish(child, receipt)
        self.assertEqual(value["reason"], "deadline-expired")
        self.assertIsNone(value["child_returncode"])
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
