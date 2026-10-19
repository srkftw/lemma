"""Observe pure Lean admission of acquisition/replay metadata and granular grants."""
import json
from pathlib import Path
import subprocess
import unittest
ROOT = Path(__file__).resolve().parents[2]

class ObservationTests(unittest.TestCase):
    def test_provenance_missingness_replay_and_current_consent(self):
        build = subprocess.run(["lake", "build", "Lemma.School.Observation"], cwd=ROOT, text=True, capture_output=True, timeout=120)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        run = subprocess.run(["lake", "env", "lean", "--run", "tests/school/ObservationMain.lean"], cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        checks = json.loads(run.stdout)
        self.assertGreaterEqual(len(checks), 20)
        self.assertTrue(all(checks.values()), checks)
