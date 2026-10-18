"""Real process death must not leave an unlocked writable compiler workspace."""
from __future__ import annotations

import fcntl
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"))
from action_cache import is_process_alive, process_identity
from core0_common import (Core0Error, action_lease, run_bounded, _stop_bounded,
                          LEASE_WORKER_SHA256, LEASE_WORKER_PATH, sha256)


def leased_parent(directory):
    root = Path(directory)
    with (root/"lease.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with action_lease(lock.fileno()):
            run_bounded([sys.executable,str(root/"writer.py"),str(root)],
                        cwd=root,timeout_seconds=30)


class ActionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_lease(self, code, *, timeout=5, stdin=None):
        with (self.root/"lease.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with action_lease(lock.fileno()):
                return run_bounded([sys.executable,"-c",code],cwd=self.root,
                                   timeout_seconds=timeout,stdin=stdin)

    def test_original_output_input_and_returncode_are_preserved(self):
        result = self.run_lease("import sys;print(sys.stdin.read().upper());print('error stream',file=sys.stderr);sys.exit(17)",stdin=b"payload")
        self.assertEqual(result.argv[0],sys.executable)
        self.assertEqual(result.returncode,17)
        self.assertEqual(result.stdout,b"PAYLOAD\n")
        self.assertEqual(result.stderr,b"error stream\n")
        signal_result = self.run_lease("import os,signal;os.kill(os.getpid(),signal.SIGTERM)")
        self.assertEqual(signal_result.returncode,-signal.SIGTERM)

    def test_independent_deadline_kills_and_reaps_owned_tool(self):
        code = (f"import os,sys,time,pathlib;pathlib.Path({str(self.root/'pid')!r}).write_text(str(os.getpid()));"
                "print('partial output',flush=True);print('partial error',file=sys.stderr,flush=True);time.sleep(30)")
        started = time.monotonic()
        with self.assertRaisesRegex(Core0Error,"timed out") as observed:
            self.run_lease(code,timeout=0.2)
        self.assertEqual(observed.exception.stdout,b"partial output\n")
        self.assertEqual(observed.exception.stderr,b"partial error\n")
        self.assertEqual(observed.exception.argv,(sys.executable,"-c",code))
        self.assertGreaterEqual(observed.exception.elapsed_seconds,0.2)
        self.assertLess(time.monotonic()-started,5)
        pid = int((self.root/"pid").read_text())
        self.assertFalse(Path(f"/proc/{pid}").exists())

    def test_unleased_timeout_retains_partial_observations(self):
        command = [sys.executable,"-c","import sys,time;print('ordinary output',flush=True);print('ordinary error',file=sys.stderr,flush=True);time.sleep(30)"]
        with self.assertRaisesRegex(Core0Error,"timed out") as observed:
            run_bounded(command,cwd=self.root,timeout_seconds=0.2)
        self.assertEqual(observed.exception.stdout,b"ordinary output\n")
        self.assertEqual(observed.exception.stderr,b"ordinary error\n")
        self.assertEqual(observed.exception.argv,tuple(command))

    def test_slow_cleanup_never_kills_supervisor_or_releases_its_lease(self):
        # A real uninterruptible kernel writer is unsafe to create in a test.
        # Exercise the exact fallback with an owned-process stand-in instead.
        process = Mock(pid=os.getpid())
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(["worker"],7,output=b"earlier",stderr=b"earlier error"),
            subprocess.TimeoutExpired(["worker"],7,output=b"complete partial output",stderr=b"complete partial error")]
        with patch("core0_common._worker_descendants",return_value=[]),patch("core0_common.threading.Thread") as thread:
            stdout,stderr = _stop_bounded(process,leased=True)
        self.assertEqual(stdout,b"complete partial output")
        self.assertEqual(stderr,b"complete partial error")
        process.kill.assert_not_called()
        process.send_signal.assert_called_once_with(signal.SIGTERM)
        self.assertEqual(process._lemma_cleanup_worker,process_identity())
        thread.assert_called_once_with(target=process.wait,daemon=True,name="lemma-action-worker-reaper")
        thread.return_value.start.assert_called_once()

    def test_lease_executes_frozen_worker_bytes_after_isolated_source_change(self):
        source = self.root/"mutable-worker.py"
        source.write_bytes((ROOT/"scripts/action_worker.py").read_bytes())
        original_hash = sha256(source)
        with (self.root/"lease.lock").open("a+b") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with action_lease(lock.fileno(),worker_path=source):
                frozen = LEASE_WORKER_PATH.get()
                self.assertEqual(LEASE_WORKER_SHA256.get(),original_hash)
                self.assertEqual(sha256(frozen),original_hash)
                source.write_text("raise RuntimeError('changed mutable worker must not run')\n")
                result = run_bounded([sys.executable,"-c","print('frozen worker ran')"],
                                     cwd=self.root,timeout_seconds=5)
                self.assertEqual(result.returncode,0)
                self.assertEqual(result.stdout,b"frozen worker ran\n")
        self.assertFalse(frozen.exists())
        self.assertIsNone(LEASE_WORKER_PATH.get())
        self.assertIsNone(LEASE_WORKER_SHA256.get())

    def test_success_does_not_leave_background_descendants(self):
        code = ("import subprocess,sys,pathlib,time;"
                f"p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True);"
                f"pathlib.Path({str(self.root/'background')!r}).write_text(str(p.pid))")
        self.assertEqual(self.run_lease(code).returncode,0)
        pid = int((self.root/"background").read_text())
        self.assertFalse(Path(f"/proc/{pid}").exists())

    def test_killed_parent_retains_lease_until_tool_and_detached_child_are_gone(self):
        # The writer mutates shared state repeatedly and starts a child in a
        # different process group, exercising both lease and subreaper cleanup.
        (self.root/"writer.py").write_text(
            "import os,pathlib,subprocess,sys,time\n"
            "root=pathlib.Path(sys.argv[1])\n"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)\n"
            "(root/'pids.json').write_text(__import__('json').dumps([os.getpid(),child.pid]))\n"
            "for n in range(1000):\n (root/'shared').write_text(str(n));time.sleep(0.01)\n")
        unrelated = subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True)
        def stop_unrelated():
            if unrelated.poll() is None: unrelated.kill()
            unrelated.wait()
        self.addCleanup(stop_unrelated)
        parent = multiprocessing.get_context("fork").Process(target=leased_parent,args=(str(self.root),))
        parent.start()
        self.addCleanup(lambda: parent.is_alive() and parent.kill())
        deadline = time.monotonic()+5
        while not (self.root/"shared").exists() and time.monotonic()<deadline:
            time.sleep(0.01)
        self.assertTrue((self.root/"shared").exists())
        pids = json.loads((self.root/"pids.json").read_text())
        identities = [process_identity(pid) for pid in pids]
        self.assertTrue(all(is_process_alive(identity) for identity in identities))
        os.kill(parent.pid,signal.SIGKILL)
        parent.join(5)
        with (self.root/"lease.lock").open("a+b") as contender:
            acquired = False
            deadline = time.monotonic()+5
            while time.monotonic()<deadline:
                try:
                    fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError: time.sleep(0.01)
            self.assertTrue(acquired,"abandoned worker failed to relinquish lease after cleanup")
            self.assertTrue(all(not is_process_alive(identity) for identity in identities),
                            "lease was available while an old compiler was still live")
            before = (self.root/"shared").read_bytes()
            time.sleep(0.1)
            self.assertEqual((self.root/"shared").read_bytes(),before)
            self.assertIsNone(unrelated.poll(),"cleanup signalled an unrelated process")


if __name__ == "__main__":
    unittest.main()
