#!/usr/bin/env python3
"""Static regressions for the bounded, pinned foundation and kernel CI lanes."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/core0.yml"


JOBS = ("lemmasim-writing-rv64", "metadata", "kernel-managed-rv64", "kernel-services-rv64", "legacy-rv64",
        "foundation-rv64", "kernel-rv64", "kernel-source-negatives-rv64",
        "kernel-architecture-rv64", "silicon-devices-rtl")


def job_block(source: str, job: str) -> str:
    """Slice one actual job, independent of its following sibling's name."""
    jobs = list(re.finditer(r"^  ([a-z0-9-]+):$", source.split("jobs:\n", 1)[1], re.MULTILINE))
    body = source.split("jobs:\n", 1)[1]
    selected = [index for index, match in enumerate(jobs) if match[1] == job]
    if len(selected) != 1:
        raise ValueError("missing/duplicate job: " + job)
    index = selected[0]
    return body[jobs[index].start():jobs[index + 1].start() if index + 1 < len(jobs) else len(body)]


def logged_blocks(source: str) -> list[str]:
    blocks = re.findall(r"run: \|\n((?: {10}.*(?:\n|$))+)", source)
    return [block for block in blocks if "| tee " in block]


class CiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text()
        cls.blocks = {name: job_block(cls.source, name) for name in JOBS}
        cls.metadata = cls.blocks["metadata"]
        cls.legacy = cls.blocks["legacy-rv64"]
        cls.foundation = cls.blocks["foundation-rv64"]
        cls.kernel = cls.blocks["kernel-rv64"]
        cls.task002 = cls.metadata + cls.legacy + cls.foundation

    def test_pr_campaign_does_not_duplicate_task_branch_push(self):
        triggers = self.source.split("permissions:\n", 1)[0]
        self.assertRegex(triggers, r"push:\n\s+branches:\n\s+- main\n")
        self.assertNotIn('"task/**"', triggers)
        self.assertIn("  pull_request:\n", triggers)
        self.assertIn("  workflow_dispatch:\n", triggers)

    def test_separate_jobs_keep_host_metadata_away_from_qemu(self):
        jobs = re.findall(
            r"^  ([a-z0-9-]+):$", self.source.split("jobs:\n", 1)[1], re.MULTILINE
        )
        self.assertEqual(jobs, list(JOBS))
        for suite in ("tests/scaffold", "tests/core0", "tests/foundation", "tests/kernel", "tests/silicon"):
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
                r"^\s+timeout-minutes:\s+(\d+)$", self.task002, re.MULTILINE
            )
        ]
        self.assertEqual(timeouts, [45, 45, 60])

    def test_every_logged_pipeline_fails_closed_with_explicit_pipefail(self):
        expected = {
            "lemmasim-writing-rv64": ("lemmasim-host-build.log", "lemmasim-writing.log"),
            "metadata": ("metadata/check-scaffold.log", "metadata/scaffold-unittest.log",
                         "metadata/core0-host-unittest.log", "metadata/lake-build.log",
                         "metadata/foundation-host-unittest.log", "metadata/kernel-host-unittest.log",
                         "metadata/silicon-host-unittest.log"),
            "legacy-rv64": ("legacy-rv64.log",),
            "foundation-rv64": ("foundation-gates1-9.log", "foundation-qualification.log"),
            "kernel-managed-rv64": ("kernel-managed-rv64.log",),
            "kernel-services-rv64": ("kernel-services-rv64.log",),
            "kernel-rv64": ("kernel-rv64.log",),
            "kernel-source-negatives-rv64": ("kernel-source-negatives-rv64.log",),
            "kernel-architecture-rv64": ("kernel-architecture-rv64.log",),
            "silicon-devices-rtl": ("silicon-devices-rtl.log", "silicon-bus-lanes-rtl.log"),
        }
        for job, names in expected.items():
            with self.subTest(job=job):
                blocks = logged_blocks(self.blocks[job])
                self.assertEqual([re.findall(r"\| tee build/ci/([^\s]+)", block)[0] for block in blocks], list(names))
                for block in blocks:
                    commands = [line.strip() for line in block.splitlines() if line.strip()]
                    self.assertEqual(commands[0], "set -euo pipefail")
                    self.assertEqual(block.count("| tee "), 1)

    def test_lemmasim_lane_builds_pinned_host_and_checks_real_cold_guest_ink(self):
        lane = self.blocks['lemmasim-writing-rv64']
        for required in ('tooling/lemmasim/qemu.nix', './scripts/check-lemmasim.sh',
                         '--clean --lane writing --with-o0', '--deadline 3500',
                         "value['source']['commit'] != head", "len(value['cases']) != 2",
                         "observed['retained_unique_raw_samples'] != 50", "cold['status'] != 'PASS'",
                         'if-no-files-found: error', 'retention-days: 14'):
            self.assertIn(required, lane)
        self.assertEqual(lane.count('timeout --foreground --signal=TERM --kill-after=30s'), 2)

    def test_job_slice_cannot_absorb_an_added_sibling(self):
        source = "jobs:\n  metadata:\n    run: host-only\n  new-job:\n    run: qemu\n  legacy-rv64:\n    run: guest\n"
        self.assertEqual(job_block(source, "metadata"), "  metadata:\n    run: host-only\n")
        self.assertEqual(job_block(source, "new-job"), "  new-job:\n    run: qemu\n")
        with self.assertRaises(ValueError): job_block(source, "missing")

    def test_literal_rtl_lane_is_bounded_exact_source_and_retains_failures(self):
        lane = self.blocks['silicon-devices-rtl']
        for required in ('timeout-minutes: 20', 'literal host stimuli',
                         'timeout --foreground --signal=TERM --kill-after=30s 15m',
                         'python3 scripts/check_silicon.py --lane devices',
                         '--work-dir build/silicon/ci-devices --timeout 600 --jobs 2',
                         "value['source_commit'] != head", "value['observations'] != expected",
                         "len(value['commands']) != 2", "value['source_inputs'].items()",
                         "command['log_sha256']", "command['exit_code'] != 0",
                         'if: ${{ always() }}', 'if-no-files-found: error'):
            self.assertIn(required, lane)
        self.assertNotIn('continue-on-error', lane)

    def test_kernel_lane_requires_bounded_clean_source_and_complete_evidence(self):
        self.assertIn("timeout-minutes: 45", self.kernel)
        self.assertIn("timeout --foreground --signal=TERM --kill-after=30s 40m", self.kernel)
        for required in ("nix develop --no-write-lock-file --command", "python3 scripts/check_kernel.py",
                         "--work-dir build/kernel/ci-prefix", "--clean", "--timeout 300", "--qemu-timeout 90", "--deadline 2400"):
            self.assertIn(required, self.kernel)
        pipeline_blocks = re.findall(r"run: \|\n((?: {10}.*(?:\n|$))+)", self.kernel)
        logged = [block for block in pipeline_blocks if "| tee " in block]
        self.assertEqual(len(logged), 1)
        self.assertEqual(next(line.strip() for line in logged[0].splitlines() if line.strip()), "set -euo pipefail")
        for required in ('value["status"] == "PASS" and value["source"]["clean"] is True',
                         'value["required_gate_prefix"] == "A-E" and value["highest_exercised_gate"] == "E"',
                         'len(value["images"]) == 20 and len(value["observations"]) == 24',
                         'value["qemu_sessions"] == 28 and value["syscall_user_instances"] == 6',
                         'recorded["source_commit"] == value["source"]["commit"]',
                         'recorded["lean_source_realization"]',
                         'realized["source_path"] == lean["source_path"] and realized["revision"] == lean["revision"]',
                         'realized["narHash"] == lean["source_sha256"] and realized["narSize"] == lean["source_nar_size"]',
                         'digest(audit) == row["audit_sha256"] and digest(provenance) == row["provenance_sha256"]',
                         'digest(observed) == row["sha256"] and result["status"] == "PASS"'):
            self.assertIn(required, self.kernel)
        self.assertIn("if: ${{ always() }}", self.kernel)
        self.assertIn("actions/upload-artifact@", self.kernel)
        self.assertIn("if-no-files-found: error", self.kernel)
        self.assertIn("build/kernel/ci-prefix/", self.kernel)
        self.assertIn("build/ci/kernel-rv64.log", self.kernel)
        self.assertIn("retention-days: 14", self.kernel)

    def test_new_kernel_lanes_require_exact_bounded_commands_and_revalidators(self):
        cases = (
            ("kernel-managed-rv64", "scripts/check_kernel_cumulative.py",
             ("--lane F-I", "--clean", "--timeout 300"), "validate_lane", "ci-managed",
             ('value["lane"] != "F-I" or len(value["cases"]) != 8',)),
            ("kernel-services-rv64", "scripts/check_kernel_cumulative.py",
             ("--lane J", "--clean", "--timeout 300"), "validate_lane", "ci-services",
             ('value["lane"] != "J" or len(value["cases"]) != 4',)),
            ("kernel-source-negatives-rv64", "scripts/check_kernel_mutations.py",
             ('candidate="$(git rev-parse HEAD)"', '--expected-commit "$candidate"'),
             "validate_campaign", "ci-source-negatives",
             ('value["protocol"] != "kernel-source-mutations-K-v1" or len(value["cases"]) != 4',
              'build/kernel/ci-source-negatives/checkouts/*/build/kernel/K-mutations/')),
            ("kernel-architecture-rv64", "scripts/check_kernel_architecture.py",
             ("--clean", "--timeout 300"), "validate_architecture", "ci-architecture",
             ('value["status"] != "PASS" or len(value["cases"]) != 12',)),
        )
        for job, checker, arguments, validator, evidence, gates in cases:
            with self.subTest(job=job):
                block = self.blocks[job]
                self.assertEqual(re.findall(r"^    timeout-minutes: (\d+)$", block, re.M), ["45"])
                for required in (checker, *arguments, validator, *gates, "--deadline 2400",
                                 "timeout --foreground --signal=TERM --kill-after=30s 40m",
                                 "nix develop --no-write-lock-file --command",
                                 "--work-dir build/kernel/" + evidence,
                                 'Path("build/kernel/' + evidence + '/result.json")',
                                 "Path.cwd()", "raise RuntimeError", "set -euo pipefail",
                                 "if: ${{ always() }}", "actions/upload-artifact@",
                                 "if-no-files-found: error", "retention-days: 14",
                                 "build/ci/" + job + ".log"):
                    self.assertIn(required, block)
                self.assertNotRegex(block, r"\bassert\s")
                self.assertNotIn("continue-on-error", block)

    def test_prefix_revalidator_binds_current_source_exact_roles_and_real_sessions(self):
        for required in ('value["source"] == source_identity(Path.cwd())',
                         'value["source_inputs"] == source_inputs(Path.cwd())',
                         'value["acceptance_inputs"] == acceptance_inputs(Path.cwd())',
                         'for cfg, stage, opt in matrix():',
                         'expected_observations.extend((cfg, stage, opt, role) for role in roles)',
                         '== expected_observations)',
                         'audited["dirty_paths"] == []', 'recorded["dirty_paths"] == []',
                         'recorded["source_inputs"] == value["source_inputs"]',
                         'tuple(audited[k] for k in ("configuration", "stage", "optimization"))',
                         'tuple(recorded[k] for k in ("configuration", "stage", "optimization"))',
                         'result = json.loads(observed.read_text())',
                         'actual["fresh_user_runs"] == 3', '== list(DEFAULT_SEEDS)',
                         'validate_session(Path(child["result"]), image)',
                         'validate_session(observed.resolve(), image, machine_origin=row["role"] == "machine-origin")'):
            self.assertIn(required, self.kernel)
        self.assertNotRegex(self.kernel, r"\bassert\s")
        self.assertNotIn("continue-on-error", self.source)

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
