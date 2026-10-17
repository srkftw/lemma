import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import supervise_usb_notebook as supervisor


class Supervision(unittest.TestCase):
    def test_absolute_deadline_reaps_owned_observer_without_restart(self):
        with tempfile.TemporaryDirectory(dir=supervisor.ROOT/'build') as raw:
            out=Path(raw);work=out/'campaign';work.mkdir()
            manifest={'argv':[sys.executable,'-c','import time; time.sleep(100)'],
                      'work_dir':str(work),'supervisor_sha256':supervisor.digest(supervisor.__file__),
                      'observer_sha256':supervisor.digest(supervisor.ROOT/'scripts/check_guest_usb_notebook.py'),
                      'absolute_deadline_unix_ns':time.time_ns()+500000000}
            path=out/'manifest.json';path.write_text(json.dumps(manifest))
            old={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT)}
            try:self.assertEqual(supervisor.supervise(path),1)
            finally:
                for sig,handler in old.items():signal.signal(sig,handler)
            result=json.loads((out/'supervision.json').read_text())
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['cause'],'predeclared absolute supervisor deadline')
            self.assertEqual(result['observer_exit_code'],-signal.SIGTERM)
            self.assertEqual(result['owned_survivors'],[])
            self.assertFalse(supervisor.alive(result['observer']))
            self.assertEqual(result['absolute_deadline_unix_ns'],manifest['absolute_deadline_unix_ns'])

    def test_start_time_identity_rejects_pid_reuse(self):
        actual=supervisor.identity(os.getpid());self.assertTrue(supervisor.alive(actual))
        wrong={**actual,'start_ticks':actual['start_ticks']+1}
        self.assertFalse(supervisor.alive(wrong))
        self.assertIsNone(supervisor.identity(999999999))
        self.assertIn(actual,supervisor.descendants(os.getpid()))
