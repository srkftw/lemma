"""Worker/UI host protocol fixtures; these do not establish RV64 execution."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

class BrowserWorker(unittest.TestCase):
    def test_tci_waits_for_actual_stopped_cpu_acknowledgement(self):
        run=subprocess.run(['node','tests/lemmasim/tci_stop_boundary.mjs'],cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('PASS actual CPU stop transport helper',run.stdout)

    def test_actual_worker_with_bounded_machine_and_storage_fixtures(self):
        run=subprocess.run(['node','--experimental-vm-modules',
                            'tests/lemmasim/browser_worker_protocol.mjs'],cwd=ROOT,
                           capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('PASS host worker protocol',run.stdout)

    def test_pending_gpu_cannot_block_actual_app_controls_or_fallback_pixels(self):
        run=subprocess.run(['node','--experimental-vm-modules',
                            'tests/lemmasim/browser_app_startup.mjs'],cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertIn('PASS actual app host fixture',run.stdout)

if __name__=='__main__':unittest.main()
