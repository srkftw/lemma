"""Run the maintained Lean snapshot semantic validator on independent invalid histories."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class StoreSemanticValidationTests(unittest.TestCase):
    def test_commit_recovery_validator_rejects_malformed_histories(self):
        build = subprocess.run(["lake", "build", "Lemma.School.Store"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        result = subprocess.run(["lake", "env", "lean", "--run", "tests/school/StoreValidationMain.lean"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checks = json.loads(result.stdout)
        self.assertTrue(checks.pop("empty-valid"))
        self.assertTrue(checks.pop("ordered-valid"))
        self.assertTrue(checks.pop("read-clock-ahead-valid"))
        self.assertGreaterEqual(len(checks), 10)
        self.assertFalse(any(checks.values()), checks)

    def test_artifact_recovery_admits_regular_bytes_with_actual_budget(self):
        build = subprocess.run(["lake", "build", "Lemma.School.Store"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        with tempfile.TemporaryDirectory(prefix="lemma-artifact-bounds-") as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()
            data = b"permitted bounded artifact"
            digest = hashlib.sha256(data).hexdigest()
            path = root / "artifacts" / digest
            path.write_bytes(data)
            command = ["lake", "env", "lean", "--run", "tests/school/StoreValidationMain.lean", root, digest]
            valid = subprocess.run([*map(str, command), str(len(data))], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            for limit in [0, len(data)-1]:
                rejected = subprocess.run([*map(str, command), str(limit)], cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn("regular-file bound", rejected.stdout + rejected.stderr)
            path.unlink()
            path.mkdir()
            rejected = subprocess.run([*map(str, command), "16777216"], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("regular-file bound", rejected.stdout + rejected.stderr)
