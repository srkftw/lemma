"""Driver cancellation is tested only with isolated owned sleeping processes."""
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
sys.path.insert(0,str(ROOT/"scripts"))
from action_cache import is_process_alive,process_identity
from check_incremental_builds import Core0Error,invocation_counts,run_logged


class IncrementalDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.writer = self.root/"writer.py"
        self.writer.write_text(
            "import os,pathlib,subprocess,sys,time,json\n"
            "root=pathlib.Path(sys.argv[1])\n"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)\n"
            "(root/'pids.json').write_text(json.dumps([os.getpid(),child.pid]))\n"
            f"sys.path.insert(0,{str(ROOT/'scripts')!r})\n"
            "from action_cache import process_identity\n"
            "(root/'identities.json').write_text(json.dumps([process_identity(os.getpid()),process_identity(child.pid)]))\n"
            "print('partial stdout',flush=True)\n"
            "print('partial stderr',file=sys.stderr,flush=True)\n"
            "for n in range(3000):\n (root/'shared').write_text(str(n));time.sleep(0.01)\n")

    def wait_ready(self,process):
        deadline = time.monotonic()+5
        while not (self.root/"shared").exists() and time.monotonic()<deadline:
            if process.poll() is not None: self.fail("fixture driver exited before readiness")
            time.sleep(0.01)
        self.assertTrue((self.root/"shared").exists())
        return [process_identity(pid) for pid in json.loads((self.root/"pids.json").read_text())]

    def assert_stopped(self,identities):
        self.assertTrue(all(not is_process_alive(identity) for identity in identities))
        previous = (self.root/"shared").read_bytes()
        time.sleep(0.05)
        self.assertEqual((self.root/"shared").read_bytes(),previous)

    def test_timeout_reaps_owned_detached_tree_and_retains_partial_log(self):
        unrelated = subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],start_new_session=True)
        self.addCleanup(lambda: (unrelated.kill(),unrelated.wait()) if unrelated.poll() is None else None)
        with self.assertRaisesRegex(Core0Error,"timed out"):
            run_logged([sys.executable,str(self.writer),str(self.root)],cwd=self.root,
                       log=self.root/"timeout.log",timeout=0.2,env=dict(os.environ))
        identities = json.loads((self.root/"identities.json").read_text())
        self.assert_stopped(identities)
        text = (self.root/"timeout.log").read_text()
        self.assertIn("partial stdout",text)
        self.assertIn("partial stderr",text)
        self.assertIsNone(unrelated.poll(),"cleanup signalled an unrelated existing child")

    def test_sigterm_and_sigint_cancel_campaign_write_fail_report_and_reap(self):
        parent = ROOT/"build/incremental"
        parent.mkdir(parents=True,exist_ok=True)
        for number in (signal.SIGTERM,signal.SIGINT):
            with self.subTest(signal=number),tempfile.TemporaryDirectory(prefix="driver-cancel-test-",dir=parent) as directory:
                # The campaign's clone operation is replaced with this isolated
                # sleep fixture; no real production build is started by the test.
                work = Path(directory)/"campaign"
                runner = self.root/"runner.py"
                runner.write_text(
                    f"import sys,os\nsys.path.insert(0,{str(ROOT/'scripts')!r})\n"
                    "import check_incremental_builds as d\n"
                    "def isolated_snapshot(root,destination,log):\n"
                    f" d.run_logged([sys.executable,{str(self.writer)!r},{str(self.root)!r}],cwd=d.Path({str(self.root)!r}),log=log,timeout=30,env=dict(os.environ))\n"
                    " raise RuntimeError('fixture must be cancelled before it completes')\n"
                    "d.snapshot_checkout=isolated_snapshot\n"
                    f"sys.argv=['driver','--work-dir',{str(work)!r},'--strace',sys.executable]\n"
                    "raise SystemExit(d.main())\n")
                (self.root/"shared").unlink(missing_ok=True)
                process = subprocess.Popen([sys.executable,str(runner)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
                self.addCleanup(lambda p=process: (p.kill(),p.wait()) if p.poll() is None else None)
                identities = self.wait_ready(process)
                os.kill(process.pid,number)
                stdout,stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode,128+number,(stdout,stderr))
                report = json.loads((work/"report.json").read_text())
                self.assertEqual(report["status"],"FAIL")
                self.assertEqual(report["cancellation_signal"],number)
                self.assertIn("cancelled",report["error"])
                self.assert_stopped(identities)

    def test_trace_counts_successful_resumed_failed_and_metadata_calls(self):
        trace = self.root/"trace"
        trace.write_text(
            '10 execve("/nix/bin/opt", ["opt", "--version"], 0x123) = 0\n'
            '11 execve("/nix/bin/llc", ["llc", "program.ll", "-o", "program.o"], 0x123 <unfinished ...>\n'
            '11 <... execve resumed>) = 0\n'
            '12 execve("/missing/clang", ["clang"], 0x123) = -1 ENOENT (No such file)\n'
            '13 execve("/nix/bin/lean", ["lean", "--githash"], 0x123) = 0\n')
        counts = invocation_counts(trace)
        self.assertEqual(counts["successful_execve_by_tool"],{"opt":1,"llc":1,"lean":1})
        self.assertEqual(counts["production_by_tool"],{"llc":1})
        self.assertEqual(counts["metadata_by_tool"],{"opt":1,"lean":1})


if __name__ == "__main__":
    unittest.main()
