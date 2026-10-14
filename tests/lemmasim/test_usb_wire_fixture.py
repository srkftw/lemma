"""Owned host-process cleanup, separate from any guest/USB property claim."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_native_usb_wire_pending import run_fixture
from supervise_usb_notebook import alive


class WireFixtureChildren(unittest.TestCase):
    def setUp(self):
        self.assertEqual(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0), 0)

    def test_normal_exit_reaps_separately_grouped_child_and_preserves_unrelated(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'])
        try:
            with tempfile.TemporaryDirectory() as directory:
                command = [sys.executable, '-c',
                    'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'
                    '"import time;time.sleep(20)"],start_new_session=True);time.sleep(.3)']
                owned = run_fixture(command, Path(directory) / 'run.log', 5)
                self.assertGreaterEqual(len(owned), 2)
                self.assertTrue(all(not alive(item) for item in owned))
                self.assertIsNone(unrelated.poll())
                record = json.loads((Path(directory) / 'run.supervision.json').read_text())
                self.assertEqual(record['status'], 'PASS')
                self.assertEqual(record['owned_survivors'], [])
                self.assertEqual(record['owned_children'], owned)
                self.assertFalse(record['automatic_restart'])
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)

    def test_predeclared_timeout_reaps_separately_grouped_child(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'run.log'
            command = [sys.executable, '-c',
                'import subprocess,sys,time;child=subprocess.Popen([sys.executable,"-c",'
                '"import time;time.sleep(20)"],start_new_session=True);'
                'print(child.pid,flush=True);time.sleep(20)']
            with self.assertRaisesRegex(TimeoutError, 'predeclared'):
                run_fixture(command, log, .3)
            child_pid = int(log.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
            record = json.loads(log.with_suffix('.supervision.json').read_text())
            self.assertEqual(record['status'], 'FAIL')
            self.assertIn('predeclared', record['error'])
            self.assertEqual(record['host_seconds_bound'], .3)
            self.assertEqual(record['owned_survivors'], [])
            self.assertFalse(record['automatic_restart'])

    def test_failed_fixture_retains_exit_status_and_reaps_its_child(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'run.log'
            command = [sys.executable, '-c',
                'import subprocess,sys,time;child=subprocess.Popen([sys.executable,"-c",'
                '"import time;time.sleep(20)"],start_new_session=True);'
                'print(child.pid,flush=True);time.sleep(.2);sys.exit(7)']
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                run_fixture(command, log, 5)
            self.assertEqual(failure.exception.returncode, 7)
            record = json.loads(log.with_suffix('.supervision.json').read_text())
            self.assertEqual((record['status'], record['returncode']), ('FAIL', 7))
            self.assertEqual(record['owned_survivors'], [])
            with self.assertRaises(ProcessLookupError):
                os.kill(int(log.read_text()), 0)

    def test_predeclared_memory_limit_reaps_only_the_owned_fixture(self):
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(20)'])
        try:
            with tempfile.TemporaryDirectory() as directory:
                log = Path(directory) / 'run.log'
                command = [sys.executable, '-c', 'import time;data=bytearray(8*1024*1024);time.sleep(20)']
                with self.assertRaisesRegex(RuntimeError, 'memory bound exceeded'):
                    run_fixture(command, log, 5, maximum_rss_kib=1)
                record = json.loads(log.with_suffix('.supervision.json').read_text())
                self.assertEqual(record['status'], 'FAIL')
                self.assertGreater(record['peak_tree_rss_kib'], record['maximum_tree_rss_kib'])
                self.assertEqual(record['owned_survivors'], [])
                self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
