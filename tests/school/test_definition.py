"""Execute actual Lean package extraction/validation against live-state fixtures."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SchoolDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = subprocess.run(["lake", "build", "Lemma.School.Definition", "Lemma.School.FixtureUnit"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)

    def run_definition(self, *args):
        result = subprocess.run(["lake", "env", "lean", "--run", "tests/school/DefinitionMain.lean", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_same_compiler_binds_artifacts_and_rejects_unsupported_requirements(self):
        checks = self.run_definition()
        self.assertGreaterEqual(len(checks), 20)
        self.assertTrue(all(checks.values()), checks)

    def test_package_excludes_live_identity_private_work_and_credentials(self):
        package = self.run_definition("emit")
        serialized = json.dumps(package)
        for private in ["private-school-unique", "live-deployment-unique", "live-owner-unique",
                        "private-learner-unique", "secret-private-learner-work-unique",
                        "secret-live-credential-unique", "/private/deployment/source-resolver-unique"]:
            self.assertNotIn(private, serialized)
        self.assertEqual(package["schema"], "lemma-school-package/1")
        self.assertEqual(len(package["publications"]), 1)
        self.assertEqual([model["version"] for model in package["models"]], [1])
        self.assertIsNone(package["selectedModel"])
        self.assertNotIn("records", package)
        self.assertNotIn("generation", package)
