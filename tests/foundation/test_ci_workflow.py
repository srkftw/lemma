#!/usr/bin/env python3
"""Static regressions for the bounded, pinned foundation and kernel CI lanes."""

from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import os
import re
import textwrap
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/core0.yml"


REQUIRED_JOBS = ("lemmasim-writing-rv64", "metadata", "kernel-managed-rv64", "kernel-services-rv64", "legacy-rv64",
        "foundation-rv64", "kernel-rv64", "kernel-source-negatives-rv64",
        "kernel-architecture-rv64", "silicon-devices-rtl", "crypto-rv64")
JOBS = (*REQUIRED_JOBS[:6], "kernel-rv64-shard", *REQUIRED_JOBS[6:], "acceptance-summary")

CHECK_NAMES = {
    "lemmasim-writing-rv64": "Task 004 real notebook O0/O2 writing and cold recovery",
    "metadata": "Metadata and host-only suites",
    "kernel-managed-rv64": "Task 003 Gates F-I RV64 acceptance",
    "kernel-services-rv64": "Task 003 Buffer service RV64 acceptance",
    "legacy-rv64": "Legacy Core0 RV64 acceptance",
    "foundation-rv64": "Foundation Gates 1-9 and clean qualification",
    "kernel-rv64": "Task 003 implemented Gates A-E RV64 acceptance",
    "kernel-source-negatives-rv64": "Task 003 source-negative RV64 qualification",
    "kernel-architecture-rv64": "Task 003 architectural containment RV64 acceptance",
    "silicon-devices-rtl": "RTL device and digital power conformance with literal host stimuli",
    "crypto-rv64": "Public-development SHA/HMAC RV64 and authenticated ROM audit",
}


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
    return [block for block in blocks if re.search(r"\|\s*tee\b", block)]


def logged_pipeline_names(source: str) -> list[str]:
    """Check each logged run, including every pipeline in a multi-command run."""
    names = []
    for block in logged_blocks(source):
        commands = [line.strip() for line in block.splitlines() if line.strip()]
        if commands[0] != "set -euo pipefail":
            raise ValueError("logged run lacks explicit fail-closed shell options")
        paths = re.findall(r"\| tee build/ci/([^\s]+)", block)
        if len(paths) != len(re.findall(r"\|\s*tee\b", block)):
            raise ValueError("logged pipeline lacks its retained CI log path")
        names.extend(paths)
    return names


class CiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text()
        cls.blocks = {name: job_block(cls.source, name) for name in JOBS}
        cls.metadata = cls.blocks["metadata"]
        cls.legacy = cls.blocks["legacy-rv64"]
        cls.foundation = cls.blocks["foundation-rv64"]
        cls.kernel = cls.blocks["kernel-rv64"]
        cls.kernel_shard = cls.blocks["kernel-rv64-shard"]
        cls.writing = cls.blocks["lemmasim-writing-rv64"]
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
        for suite in ("tests/ci", "tests/scaffold", "tests/core0", "tests/foundation", "tests/boot", "tests/kernel", "tests/cache", "tests/silicon"):
            self.assertIn(suite, self.metadata)
        self.assertIn("scripts/check_scaffold.py", self.metadata)
        self.assertIn("lake build Lemma Lemma.Platform.LemmaSim.NotebookKernel", self.metadata)
        self.assertIn("Lemma.Courses.Arithmetic Lemma.Courses.Package", self.metadata)
        self.assertIn("Lemma.Courses.PackageInstaller", self.metadata)
        self.assertLess(self.metadata.index("Lemma.Courses.PackageInstaller"),
                        self.metadata.index("tests/courses/IngressIdle.lean"))
        self.assertLess(self.metadata.index("lake build"), self.metadata.index("tests/foundation"))
        self.assertIn("Lemma.Applications.Notebook", self.metadata)
        self.assertIn("lake build Lemma.Numerics.Linear", self.metadata)
        self.assertLess(self.metadata.index("lake build Lemma.Numerics.Linear"),
                        self.metadata.index("python3 scripts/check_school_training.py"))
        self.assertLess(self.metadata.index("Lemma.Applications.Notebook"),
                        self.metadata.index("tests/courses/NotebookPackage.lean"))
        for source in ("tests/courses/NumberEntry.lean", "tests/courses/NumberPad.lean"):
            self.assertIn(source, self.metadata)
            self.assertLess(self.metadata.index("Lemma.Applications.Notebook"), self.metadata.index(source))
        self.assertIn("Lemma.Compiler.KernelExport", self.metadata)
        self.assertLess(self.metadata.index("Lemma.Compiler.KernelExport"),
                        self.metadata.index("tests/kernel/ManagedNotebookDeployment.lean"))
        self.assertIn("Lemma.Services.Arithmetic.ClientV2", self.metadata)
        self.assertLess(self.metadata.index("Lemma.Services.Arithmetic.ClientV2"),
                        self.metadata.index("tests/mathematics/ExecutionIdentity.lean"))
        self.assertIn("test ! -e build/kernel/ci-user-word-inline", self.metadata)
        self.assertIn("env LEMMA_WORD_INLINE_FIXTURE_DIR=build/kernel/ci-user-word-inline", self.metadata)
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
        # Three original job ceilings plus narrower Reader19 and school-worker steps.
        self.assertEqual(timeouts, [45, 12, 45, 8, 60])

    def test_required_names_dependencies_and_exact_checkout_are_preserved(self):
        self.assertEqual(set(CHECK_NAMES), set(REQUIRED_JOBS))
        for job in REQUIRED_JOBS:
            block = self.blocks[job]
            with self.subTest(job=job):
                self.assertEqual(re.findall(r"^    name: (.+)$", block, re.M), [CHECK_NAMES[job]])
                self.assertEqual(re.findall(r"^    runs-on: (.+)$", block, re.M), ["ubuntu-24.04"])
                self.assertNotRegex(block, re.compile(r"^    if:", re.M))
                self.assertEqual(re.findall(r"^    needs: (.+)$", block, re.M),
                                 ["[metadata, kernel-rv64-shard]"] if job == "kernel-rv64" else [])
                self.assertIn("persist-credentials: false", block)
                self.assertIn("ref: ${{ github.sha }}", block)
                self.assertIn("scripts/ci_source.py", block)
                self.assertIn("build/ci/source.json", block)
                self.assertEqual(re.findall(r"retention-days: (\d+)", block),
                                 ["14", "14"] if job == "metadata" else ["14"])
        self.assertNotIn("continue-on-error", self.source)
        self.assertNotIn("actions/cache@", self.source)
        self.assertNotIn("magic-nix-cache", self.source)

    def test_every_logged_pipeline_fails_closed_with_explicit_pipefail(self):
        expected = {
            "lemmasim-writing-rv64": ("lemmasim-host-build.log", "lemmasim-writing.log"),
            "metadata": ("metadata/ci-unittest.log", "metadata/check-scaffold.log", "metadata/scaffold-unittest.log",
                         "metadata/core0-host-unittest.log", "metadata/lake-build.log",
                         "metadata/foundation-host-unittest.log", "metadata/boot-host-unittest.log", "metadata/user-copy-scans.log",
                         "metadata/loader-copy.log", "metadata/course-save.log", "metadata/course-ingress-idle.log", "metadata/power-authority.log",
                         "metadata/power-object-budget.log", "metadata/power-compiler.log",
                         "metadata/frame-index.log", "metadata/owned-table-prefix.log",
                         "metadata/exact-mathematics.log",
                         "metadata/owned-arena.log", "metadata/arithmetic-ipc.log",
                         "metadata/arithmetic-object-budget.log",
                         "metadata/pool-read-refinement.log",
                         "metadata/backing-io.log", "metadata/companion-peer.log",
                         "metadata/descriptor-model.log",
                         "metadata/descriptor-direct-loads.log",
                         "metadata/notebook-package-state-layout.log",
                         "metadata/course-workspace-codec.log",
                         "metadata/workspace-retry-shapes.log",
                         "metadata/workspace-reconciliation-actions.log",
                         "metadata/course-render-delta.log",
                         "metadata/course-packed-words.log",
                         "metadata/managed-notebook-deployment.log",
                         "metadata/user-word-inline.log",
                         "metadata/arithmetic-execution-identity.log",
                         "metadata/ipc-poll-borrow.log",
                         "metadata/control-render.log", "metadata/number-entry-actions.log",
                         "metadata/number-pad-reference.log", "metadata/number-pad-actions.log",
                         "metadata/companion-number-entry-actions.log",
                         "metadata/browse-history-build.log",
                         "metadata/browse-history-package.log",
                         "metadata/browse-history-actions.log",
                         "metadata/reader-retry5-shapes.log",
                         "metadata/companion-reader-recovery5-actions.log",
                         "metadata/companion-reader-deployment19.log",
                         "metadata/chooser-reader-deployment20.log",
                         "metadata/reader-location-actions.log",
                         "metadata/notebook-reader-actions.log",
                         "metadata/reader-deployment-actions.log",
                         "metadata/product-reader-deployment-actions.log",
                         "metadata/recovery-entry2-deployment-actions.log",
                         "metadata/arithmetic-aligned-actions.log",
                         "metadata/llvm-name-sets.log",
                         "metadata/kernel-host-unittest.log",
                         "metadata/cache-host-unittest.log",
                         "metadata/silicon-host-unittest.log",
                         "metadata/school-host-production.log",
                         "metadata/school-host-validation.log",
                         "metadata/school-training-preparation.log",
                         "metadata/school-host-training.log"),
            "acceptance-summary": (),
            "crypto-rv64": ("crypto-rv64.log", "development-auth-rom.log", "development-auth-layout.log"),
            "legacy-rv64": ("legacy-rv64.log", "school-worker-preparation.log",
                            "school-worker-fixture.log", "school-worker-parameters.log",
                            "school-worker-O0-build.log", "school-worker-O0-execution.log",
                            "school-worker-O2-build.log", "school-worker-O2-execution.log"),
            "foundation-rv64": ("foundation-gates1-9.log", "foundation-qualification.log"),
            "kernel-managed-rv64": ("kernel-managed-rv64.log",),
            "kernel-services-rv64": ("kernel-services-rv64.log",),
            "kernel-rv64-shard": ("kernel-rv64-shard.log", "kernel-rv64-shard-pack.log"),
            "kernel-rv64": ("kernel-rv64-shard-O0-unpack.log", "kernel-rv64-shard-O2-unpack.log", "kernel-rv64.log"),
            "kernel-source-negatives-rv64": ("kernel-source-negatives-rv64.log",),
            "kernel-architecture-rv64": ("kernel-architecture-rv64.log",),
            "silicon-devices-rtl": ("silicon-devices-rtl.log", "silicon-bus-lanes-rtl.log",
                                    "silicon-power-rtl.log", "silicon-reset-runtime-build.log",
                                    "silicon-pen-uart-resync.log"),
        }
        for job, names in expected.items():
            with self.subTest(job=job):
                self.assertEqual(logged_pipeline_names(self.blocks[job]), list(names))

    def test_logged_pipeline_scan_covers_later_commands_and_rejects_unretained_logs(self):
        source = """        run: |
          set -euo pipefail
          first 2>&1 | tee build/ci/first.log
          second 2>&1 | tee build/ci/second.log
        run: |
          set -euo pipefail
          third 2>&1 | tee build/ci/third.log
"""
        self.assertEqual(logged_pipeline_names(source), ["first.log", "second.log", "third.log"])
        with self.assertRaises(ValueError):
            logged_pipeline_names(source.replace("set -euo pipefail", "set -eu", 1))
        with self.assertRaises(ValueError):
            logged_pipeline_names(source.replace("build/ci/second.log", "unretained.log"))

    def test_kernel_host_prerequisite_is_produced_shared_and_revalidated(self):
        receipt = "build/ci/metadata/kernel-host-prerequisite"
        artifact = "kernel-host-prerequisite-${{ github.run_id }}-${{ github.run_attempt }}"
        for required in ("python3 scripts/host_prerequisites.py produce",
                         "--output-dir " + receipt + " --timeout 850",
                         "timeout --foreground --signal=TERM --kill-after=30s 15m",
                         "name: " + artifact, receipt + "/receipt.json",
                         receipt + "/kernel-host.log"):
            self.assertIn(required, self.metadata)
        share = self.metadata.split("      - name: Share the exact successful kernel host receipt\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("uses: actions/upload-artifact@", share)
        self.assertIn("if-no-files-found: error", share)
        self.assertNotIn("if:", share)
        self.assertEqual(self.metadata.count("scripts/host_prerequisites.py produce"), 1)
        self.assertRegex(self.kernel, r"(?m)^    needs: \[metadata, kernel-rv64-shard\]$")
        self.assertRegex(self.kernel_shard, r"(?m)^    needs: metadata$")
        for required in ("uses: actions/download-artifact@", "name: " + artifact,
                         "path: " + receipt, "--host-prerequisite " + receipt + "/receipt.json"):
            self.assertIn(required, self.kernel_shard)
        for required in ("uses: actions/download-artifact@", "name: " + artifact,
                         "path: " + receipt, "--host-prerequisite " + receipt + "/receipt.json",
                         "from host_prerequisites import validate as validate_host_prerequisite",
                         'validate_host_prerequisite(Path.cwd(), Path("build/kernel/ci-prefix/host-prerequisite/receipt.json"))',
                         'row.get("route") == "lemma-kernel-host-prerequisite/1"',
                         'require(len(shared) == 1 and shared[0] == {"label": "kernel-host", **admission})',
                         'require(value["host_tests"] == admission["test_count"] and admission["test_count"] > 0)'):
            self.assertIn(required, self.kernel)
        self.assertLess(self.kernel.index("uses: actions/download-artifact@"), self.kernel.index("python3 scripts/check_kernel.py"))
        self.assertNotIn("continue-on-error", self.kernel)

    def test_aggregate_requires_exact_original_jobs_and_rejects_every_non_success(self):
        summary = self.blocks["acceptance-summary"]
        self.assertIn("    if: ${{ always() }}\n", summary)
        self.assertIn("REQUIRED_DISPOSITIONS: ${{ toJSON(needs) }}", summary)
        needs = summary.split("    needs:\n", 1)[1].split("    steps:\n", 1)[0]
        self.assertEqual(re.findall(r"^      - ([a-z0-9-]+)$", needs, re.M), list(REQUIRED_JOBS))
        self.assertNotIn("continue-on-error", summary)
        script = textwrap.dedent(summary.split("          python3 - <<'PY'\n", 1)[1].split("          PY", 1)[0])
        code = compile(script, str(WORKFLOW) + ":acceptance-summary", "exec")

        def require_dispositions(values):
            with mock.patch.dict(os.environ, {"REQUIRED_DISPOSITIONS": json.dumps(values)}), redirect_stdout(io.StringIO()):
                exec(code, {})

        successful = {job: {"result": "success"} for job in REQUIRED_JOBS}
        require_dispositions(successful)
        for job in REQUIRED_JOBS:
            missing = dict(successful)
            del missing[job]
            with self.subTest(job=job, result="missing"), self.assertRaisesRegex(RuntimeError, "inventory is incomplete"):
                require_dispositions(missing)
            for result in ("failure", "cancelled", "skipped", "unavailable", "", None):
                with self.subTest(job=job, result=result), self.assertRaisesRegex(RuntimeError, "Required claim failed"):
                    require_dispositions({**successful, job: {"result": result}})
        with self.assertRaisesRegex(RuntimeError, "inventory is incomplete"):
            require_dispositions({**successful, "unexpected": {"result": "success"}})

    def test_cache_host_suite_retains_a_nonempty_success_requirement(self):
        for required in ("python3 -m unittest discover -s tests/cache -v",
                         'Path("build/ci/metadata/cache-host-unittest.log").read_text()',
                         'count = re.search(r"Ran ([0-9]+) tests?", value)',
                         'if not count or int(count[1]) <= 0 or not re.search(r"^OK$", value, re.M):',
                         'raise RuntimeError("Cache/status host suite is missing, empty or failing")'):
            self.assertIn(required, self.metadata)

    def test_lemmasim_lane_builds_pinned_host_and_checks_real_cold_guest_ink(self):
        lane = self.blocks['lemmasim-writing-rv64']
        for required in ('tooling/lemmasim/qemu.nix', './scripts/check-lemmasim.sh',
                         '--clean --lane writing --with-o0', '--deadline 3500',
                         "value['source']['commit'] != head", "len(value['cases']) != 2",
                         "observed['retained_unique_raw_samples'] != 50", "cold['status'] != 'PASS'",
                         'if-no-files-found: error', 'retention-days: 14'):
            self.assertIn(required, lane)
        self.assertEqual(lane.count('timeout --foreground --signal=TERM --kill-after=30s'), 2)

    def test_crypto_lane_requires_real_rv64_and_exact_rom_source(self):
        lane = self.blocks['crypto-rv64']
        for required in ('scripts/check_crypto.py', 'scripts/build_development_auth_boot.py',
                         '--public-development-key', 'tests/boot/DevelopmentAuthentication.lean',
                         'PASS_GENUINE_RV64_SHA256_HMAC_COMPONENT',
                         'PASS_GENUINE_DEVELOPMENT_AUTH_ROM', "report['source_commit'] != head",
                         "report['dirty_paths']", "report['source_inputs'].items()",
                         'DEVELOPMENT_AUTH_LAYOUT:PASS', 'if-no-files-found: error'):
            self.assertIn(required, lane)

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
                         "len(value['commands']) != 8", "value['source_inputs'].items()",
                         "conformance/silicon/BlockProtocol.sv", "len(value['compiled_binaries']) != 4",
                         'PEN-BANKS full-capacity all-fields two-wrap and ingress bypass PASS',
                         'PEN-BANKS refill backpressure reset cancellation and watchdog head PASS',
                         'PAPER-SEQUENCER immutable 3-phase row/source clocks backpressure powerdown PASS',
                         'PAPER-SEQUENCER invalid mode reset retained panel and scan error abort PASS',
                         'conformance/silicon/PenBanks.sv', 'conformance/silicon/PaperSequencer.sv',
                         "((0, 'Devices'), (2, 'BlockProtocol'), (4, 'PenBanks'), (6, 'PaperSequencer'))",
                         "command['log_sha256']", "command['exit_code'] != 0",
                         'if: ${{ always() }}', 'if-no-files-found: error',
                         'python3 scripts/check_silicon.py --lane power',
                         '--work-dir build/silicon/ci-power --timeout 240 --jobs 2',
                         'timeout --foreground --signal=TERM --kill-after=30s 5m',
                         "power['lane'] != 'power' or power['source_commit'] != head",
                         'POWER six independent BUSY sources malformed MMIO no false completion PASS',
                         'POWER raw edge guest decision exact cancel wake and W1C precedence PASS',
                         'POWER warm held-button epoch retention and cold control reset PASS',
                         'sim/rtl/lemma_power.sv', 'conformance/silicon/PowerControl.sv',
                         'sim/profiles/lemma-silicon-dev-0.3.0.json',
                         "len(power['commands']) != 2", "for command in power['commands']:",
                         "command['log_sha256']", "power['compiled_binary_sha256']",
                         "power['generated_binding_sha256']"):
            self.assertIn(required, lane)
        self.assertNotIn('continue-on-error', lane)

    def test_kernel_lane_requires_bounded_clean_source_and_complete_evidence(self):
        self.assertIn("timeout-minutes: 45", self.kernel)
        self.assertIn("timeout --foreground --signal=TERM --kill-after=30s 40m", self.kernel)
        for required in ("nix develop --no-write-lock-file --command", "python3 scripts/check_kernel.py",
                         "--work-dir build/kernel/ci-prefix", "--source-event build/ci/source.json", "--deadline 2400",
                         "--collect-shard build/kernel/ci-prefix/shards/O0/result.json",
                         "--collect-shard build/kernel/ci-prefix/shards/O2/result.json"):
            self.assertIn(required, self.kernel)
        self.assertNotIn("--clean", self.kernel)
        pipeline_blocks = re.findall(r"run: \|\n((?: {10}.*(?:\n|$))+)", self.kernel)
        logged = [block for block in pipeline_blocks if "| tee " in block]
        self.assertEqual(len(logged), 2)
        for block in logged:
            self.assertEqual(next(line.strip() for line in block.splitlines() if line.strip()), "set -euo pipefail")
        for required in ('value["status"] == "PASS" and value["source"]["clean"] is True',
                         'value["required_gate_prefix"] == "A-E" and value["highest_exercised_gate"] == "E"',
                         'len(value["images"]) == 20 and len(value["observations"]) == 24',
                         'value["qemu_sessions"] == 28 and value["syscall_user_instances"] == 6',
                         'value["production_route"] == "same-run-shards" and len(value["shard_producers"]) == 2',
                         '[producer["optimization"] for producer in value["shard_producers"]] == ["O0", "O2"]',
                         'len(value["matrix_rows"]) == 20',
                         '[row["index"] for row in value["matrix_rows"]] == list(range(20))',
                         'revalidate_collected(Path.cwd(), Path("build/kernel/ci-prefix").resolve(), result.resolve(), Path("build/ci/source.json"))',
                         'validate_retained_row_result(Path.cwd(), Path(request["work_dir"]).resolve(), request,',
                         'request_path.resolve(), row["request_sha256"], supervisor_path.resolve(), row)',
                         'require(admitted["supervision"] == row)',
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

    def test_kernel_cold_shards_keep_both_optimizations_and_original_execution_bounds(self):
        shard = self.kernel_shard
        self.assertEqual(re.findall(r"^    name: (.+)$", shard, re.M),
                         ["Task 003 cold A-E shard (${{ matrix.optimization }})"])
        self.assertIn("    strategy:\n      fail-fast: false\n      matrix:\n        optimization: [O0, O2]\n", shard)
        self.assertEqual(re.findall(r"^    timeout-minutes: (\d+)$", shard, re.M), ["45"])
        self.assertNotRegex(shard, re.compile(r"^    if:", re.M))
        for required in ("persist-credentials: false", "ref: ${{ github.sha }}",
                         "python3 scripts/ci_source.py --output build/ci/source.json",
                         "timeout --foreground --signal=TERM --kill-after=30s 40m",
                         "nix develop --no-write-lock-file --command",
                         "nix shell --no-write-lock-file --inputs-from . nixpkgs#git --command",
                         "--work-dir build/kernel/ci-prefix/shards/${{ matrix.optimization }}",
                         "--shard ${{ matrix.optimization }}", "--source-event build/ci/source.json",
                         "--clean", "--jobs 1", "--timeout 300", "--qemu-timeout 90", "--deadline 2400",
                         "name: kernel-A-E-shard-${{ matrix.optimization }}-${{ github.run_id }}-${{ github.run_attempt }}",
                         "python3 scripts/kernel_shard_artifact.py pack",
                         "--archive build/ci/kernel-AE-shard-${{ matrix.optimization }}.tar",
                         "--receipt build/ci/kernel-AE-shard-${{ matrix.optimization }}.pack.json",
                         "cp build/ci/kernel-rv64-shard.log build/kernel/ci-prefix/shards/${{ matrix.optimization }}/ci.log",
                         "if-no-files-found: error", "retention-days: 14"):
            self.assertIn(required, shard)
        self.assertLess(shard.index("scripts/ci_source.py"), shard.index("python3 scripts/check_kernel.py"))
        self.assertEqual(shard.count("--shard ${{ matrix.optimization }}"), 1)
        self.assertNotIn("--collect-shard", shard)
        self.assertNotIn("--jobs 2", shard)
        self.assertNotIn("continue-on-error", shard)
        for step in ("Stage shard failure log and original source event", "Package the shard with its exact file modes",
                     "Retain the exact cold optimization shard", "Retain shard source and transport failure logs"):
            block = shard.split("      - name: " + step + "\n", 1)[1].split("      - name:", 1)[0]
            self.assertIn("if: ${{ always() }}", block)
        pack = shard.split("      - name: Package the shard with its exact file modes\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("timeout --foreground --signal=TERM --kill-after=30s 2m", pack)
        self.assertIn("nix develop --no-write-lock-file --command", pack)
        self.assertLess(shard.index("Stage shard failure log and original source event"),
                        shard.index("Package the shard with its exact file modes"))
        upload = shard.split("      - name: Retain the exact cold optimization shard\n", 1)[1].split("      - name:", 1)[0]
        paths = upload.split("          path: |\n", 1)[1].split("          if-no-files-found:", 1)[0]
        self.assertEqual([line.strip() for line in paths.splitlines() if line.strip()],
                         ["build/ci/kernel-AE-shard-${{ matrix.optimization }}.tar",
                          "build/ci/kernel-AE-shard-${{ matrix.optimization }}.pack.json"])
        failure_logs = shard.split("      - name: Retain shard source and transport failure logs\n", 1)[1]
        for required in ("build/ci/source.json", "build/ci/kernel-rv64-shard.log", "build/ci/kernel-rv64-shard-pack.log"):
            self.assertIn(required, failure_logs)
        self.assertEqual(re.findall(r"retention-days: (\d+)", shard), ["14", "14"])

    def test_kernel_collector_downloads_only_exact_same_run_pair_without_cleaning_imports(self):
        for optimization in ("O0", "O2"):
            marker = "      - name: Download this run's exact " + optimization + " producer\n"
            block = self.kernel.split(marker, 1)[1].split("      - name:", 1)[0]
            self.assertIn("uses: actions/download-artifact@", block)
            self.assertIn("name: kernel-A-E-shard-" + optimization + "-${{ github.run_id }}-${{ github.run_attempt }}", block)
            self.assertIn("path: build/ci/kernel-shard-artifacts/" + optimization, block)
            self.assertNotIn("pattern:", block)
            self.assertNotIn("if:", block)
        self.assertEqual(self.kernel.count("uses: actions/download-artifact@"), 3)
        self.assertEqual(self.kernel.count("--collect-shard "), 2)
        self.assertNotIn("--shard ", self.kernel)
        self.assertNotIn("--clean", self.kernel)
        self.assertNotIn("rm -", self.kernel)
        self.assertNotIn("continue-on-error", self.kernel)
        self.assertLess(self.kernel.index("Download this run's exact O2 producer"),
                        self.kernel.index("python3 scripts/check_kernel.py"))
        restore = self.kernel.split("      - name: Restore both exact mode-preserving shard archives\n", 1)[1].split("      - name:", 1)[0]
        self.assertEqual(restore.count("timeout --foreground --signal=TERM --kill-after=30s 2m"), 2)
        self.assertNotIn("nix develop", restore)
        self.assertEqual(restore.count("python3 -I scripts/kernel_shard_artifact.py unpack"), 2)
        self.assertIn('"executable_sha256": digest.hexdigest()', restore)
        self.assertIn('"isolated": sys.flags.isolated', restore)
        for optimization in ("O0", "O2"):
            for required in ("--optimization " + optimization,
                             "--archive build/ci/kernel-shard-artifacts/" + optimization + "/kernel-AE-shard-" + optimization + ".tar",
                             "--manifest build/ci/kernel-shard-artifacts/" + optimization + "/kernel-AE-shard-" + optimization + ".pack.json",
                             "--destination build/kernel/ci-prefix/shards/" + optimization,
                             "--receipt build/ci/kernel-AE-shard-" + optimization + ".extract.json"):
                self.assertIn(required, restore)
        self.assertLess(self.kernel.index("Restore both exact mode-preserving shard archives"),
                        self.kernel.index("Collect and revalidate both exact cold producers"))
        retain = self.kernel.split("      - name: Retain Task 003 prefix evidence\n", 1)[1]
        for required in ("build/ci/kernel-shard-artifacts/", "build/ci/kernel-AE-shard-O0.extract.json",
                         "build/ci/kernel-AE-shard-O2.extract.json", "build/ci/kernel-rv64-shard-O0-unpack.log",
                         "build/ci/kernel-rv64-shard-O2-unpack.log", "build/ci/kernel-shard-transport-python.json"):
            self.assertIn(required, retain)
        self.assertNotIn("chmod", self.kernel)
        self.assertNotIn("tar -", self.kernel)
        for required in ('request["source"] == value["source"] and request["source_inputs"] == value["source_inputs"]',
                         'request["acceptance_inputs"] == value["acceptance_inputs"]',
                         'digest(request_path) == row["request_sha256"] and digest(supervisor_path) == row["supervisor_sha256"]',
                         'digest(Path(row["result"])) == row["result_sha256"] and row["cleanup_complete"] is True',
                         'require(admitted["supervision"] == row)'):
            self.assertIn(required, self.kernel)

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

    def test_task004_keeps_independent_host_binding_and_real_writing_recovery(self):
        for required in (
            "timeout-minutes: 120",
            "timeout --foreground --signal=TERM --kill-after=30s 50m",
            "nix build --no-write-lock-file --file tooling/lemmasim/qemu.nix",
            "--out-link build/lemmasim/ci-qemu",
            "timeout --foreground --signal=TERM --kill-after=30s 60m",
            "./scripts/check-lemmasim.sh --clean --lane writing --with-o0",
            "--qemu build/lemmasim/ci-qemu/bin/qemu-system-riscv64",
            "--work-dir build/lemmasim/ci-writing --deadline 3500",
            "value['source']['commit'] != head",
            "not value['source']['clean']",
            "value['lane'] != 'writing' or not value['with_o0'] or len(value['cases']) != 2",
            "observed['retained_unique_raw_samples'] != 50",
            "cold['status'] != 'PASS'",
            "build/lemmasim/ci-writing/",
            "build/kernel/ci-writing-*/",
            "build/ci/lemmasim-*.log",
            "if: ${{ always() }}",
            "if-no-files-found: error",
        ):
            self.assertIn(required, self.writing)
        self.assertLess(self.writing.index("nix build"), self.writing.index("./scripts/check-lemmasim.sh"))
        self.assertNotRegex(self.writing, r"\bassert\s")

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
            self.assertEqual(int(match.group(1)), 14)
        self.assertIn("build/core0/ci-legacy/", self.legacy)
        self.assertIn("build/foundation/ci-gates1-9/", self.foundation)
        self.assertIn("build/foundation/ci-qualification/", self.foundation)


if __name__ == "__main__":
    unittest.main()
