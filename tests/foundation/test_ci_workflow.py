#!/usr/bin/env python3
"""Static regressions for the bounded, pinned Task 002 CI lanes."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/core0.yml"


def job_block(source: str, job: str, following: str | None = None) -> str:
    start = source.index(f"  {job}:\n")
    if following is None:
        return source[start:]
    return source[start:source.index(f"  {following}:\n", start)]


class CiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text()
        cls.metadata = job_block(cls.source, "metadata", "legacy-rv64")
        cls.legacy = job_block(cls.source, "legacy-rv64", "foundation-rv64")
        cls.foundation = job_block(cls.source, "foundation-rv64")

    def test_three_separate_jobs_keep_host_metadata_away_from_qemu(self):
        jobs = re.findall(
            r"^  ([a-z0-9-]+):$", self.source.split("jobs:\n", 1)[1], re.MULTILINE
        )
        self.assertEqual(jobs, ["metadata", "legacy-rv64", "foundation-rv64"])
        for suite in ("tests/scaffold", "tests/core0", "tests/foundation"):
            self.assertIn(suite, self.metadata)
        self.assertIn("scripts/check_scaffold.py", self.metadata)
        self.assertIn("lake build", self.metadata)
        self.assertLess(self.metadata.index("lake build"), self.metadata.index("tests/foundation"))
        for guest_marker in ("check-core0.sh", "check-foundation.sh", "qualify_foundation.py", "qemu"):
            self.assertNotIn(guest_marker, self.metadata.lower())

    def test_guest_jobs_execute_real_bounded_acceptance_commands(self):
        self.assertIn("./scripts/check-core0.sh", self.legacy)
        self.assertIn("--work-dir build/core0/ci-legacy", self.legacy)
        self.assertIn("timeout --foreground --signal=TERM --kill-after=30s", self.legacy)

        self.assertIn("./scripts/check-foundation.sh", self.foundation)
        self.assertRegex(self.foundation, r"--all\s+\\\n\s+--stress")
        self.assertIn("--work-dir build/foundation/ci-gates1-9", self.foundation)
        self.assertIn("python3 scripts/qualify_foundation.py", self.foundation)
        self.assertIn("--gate9-dir build/foundation/ci-gates1-9/gate9", self.foundation)
        self.assertIn("--work-dir build/foundation/ci-qualification", self.foundation)
        self.assertEqual(
            self.foundation.count("timeout --foreground --signal=TERM --kill-after=30s"),
            2,
        )
        for required in ("--clean", "--timeout 300", "--qemu-timeout 20"):
            self.assertGreaterEqual(self.foundation.count(required), 2)

    def test_permissions_actions_and_job_timeouts_are_narrow_and_pinned(self):
        self.assertIn("permissions:\n  contents: read\n", self.source)
        self.assertIn("concurrency:\n", self.source)
        self.assertIn("defaults:\n  run:\n    shell: bash\n", self.source)
        self.assertNotIn("secrets.", self.source)
        action_uses = re.findall(r"^\s+uses:\s+([^\s#]+)", self.source, re.MULTILINE)
        self.assertGreaterEqual(len(action_uses), 1)
        for action in action_uses:
            self.assertRegex(action, r"^[^@\s]+@[0-9a-f]{40}$")
        timeouts = [
            int(value)
            for value in re.findall(
                r"^\s+timeout-minutes:\s+(\d+)$", self.source, re.MULTILINE
            )
        ]
        self.assertEqual(timeouts, [45, 45, 60])

    def test_every_logged_pipeline_fails_closed_with_explicit_pipefail(self):
        pipeline_blocks = re.findall(
            r"run: \|\n((?: {10}.*(?:\n|$))+)", self.source
        )
        logged = [block for block in pipeline_blocks if "| tee " in block]
        self.assertEqual(len(logged), 8)
        for block in logged:
            commands = [line.strip() for line in block.splitlines() if line.strip()]
            self.assertEqual(commands[0], "set -euo pipefail")

    def test_each_lane_retains_bounded_artifacts_even_on_failure(self):
        for block in (self.metadata, self.legacy, self.foundation):
            self.assertIn("if: ${{ always() }}", block)
            self.assertIn("actions/upload-artifact@", block)
            self.assertIn("if-no-files-found: warn", block)
            match = re.search(r"retention-days:\s+(\d+)", block)
            self.assertIsNotNone(match)
            self.assertGreaterEqual(int(match.group(1)), 1)
            self.assertLessEqual(int(match.group(1)), 14)
        self.assertIn("build/core0/ci-legacy/", self.legacy)
        self.assertIn("build/foundation/ci-gates1-9/", self.foundation)
        self.assertIn("build/foundation/ci-qualification/", self.foundation)


if __name__ == "__main__":
    unittest.main()
