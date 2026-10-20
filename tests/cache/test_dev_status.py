"""Status must remain conservative when observations or process IDs get stale."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dev_status as status


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) if not isinstance(value, str) else value)
        return path

    def assessment(self, *, kind="validation", result="PASS"):
        self.write("source.lean", "source")
        self.write("output.elf", "bytes")
        self.write("check.py", "observer")
        original = self.write("build/original.json", {"status": result, "source_commit": "old-source", "started_at": "old-time"})
        value = {"schema": status.EVIDENCE_SCHEMA, "claim": "claim", "kind": kind, "route": "fresh", "result": result,
                 "campaign": "campaign-a", "producer": {"source_commit": "old-source", "executed_at": "old-time", "command": ["real-check"]},
                 "receipt": {"path": "build/original.json", "sha256": status.digest(original)},
                 "inputs": {"source.lean": status.digest(self.root / "source.lean")},
                 "outputs": {"output.elf": status.digest(self.root / "output.elf")},
                 "validator": {"check.py": status.digest(self.root / "check.py")}}
        if kind == "execution":
            value["context"] = {key: "explicit-fixture-identity" for key in status.EXECUTION_CONTEXT}
        return self.write("build/assessment.json", value)

    def test_omitted_and_production_only_do_not_pass_execution(self):
        required = {"claim": {"kind": "execution", "command": "check"}}
        for evidence in ([], [{"claim": "claim", "kind": "production", "disposition": "reused"}]):
            aggregate = status.aggregate(required, evidence)
            self.assertEqual(aggregate["counts"]["pending"], 1)
            self.assertFalse(aggregate["complete"])

    def test_fresh_requires_explicit_current_campaign(self):
        path = self.assessment()
        self.assertEqual(status.assess_evidence(self.root, path)["disposition"], "reused")
        row = status.assess_evidence(self.root, path, campaign="campaign-a")
        self.assertEqual(row["disposition"], "fresh-pass")
        self.assertEqual(row["original"]["producer"]["executed_at"], "old-time")

    def test_lowercase_legacy_result_is_preserved_in_new_assessment(self):
        path = self.assessment()
        value = json.loads(path.read_text())
        original = self.root / value["receipt"]["path"]
        source = json.loads(original.read_text())
        source["status"] = "pass"
        original.write_text(json.dumps(source))
        value["receipt"]["sha256"] = status.digest(original)
        path.write_text(json.dumps(value))
        row = status.assess_evidence(self.root, path)
        self.assertEqual(row["disposition"], "reused")
        self.assertEqual(row["original_execution_result"], "pass")
        self.assertEqual(json.loads(original.read_text())["status"], "pass")

    def test_relevant_input_and_validation_changes_invalidate(self):
        path = self.assessment()
        self.write("unrelated.md", "unrelated")
        self.assertEqual(status.assess_evidence(self.root, path)["disposition"], "reused")
        self.write("check.py", "changed-observer")
        row = status.assess_evidence(self.root, path)
        self.assertEqual(row["disposition"], "pending")
        self.assertIn("validator changed: check.py", row["reasons"])
        self.write("source.lean", "defect")
        self.assertIn("input changed: source.lean", status.assess_evidence(self.root, path)["reasons"])

    def test_missing_corrupt_unknown_and_incomplete_context_are_unavailable(self):
        path = self.assessment(kind="execution")
        value = json.loads(path.read_text())
        value["context"].pop("initial_state")
        path.write_text(json.dumps(value))
        self.assertEqual(status.assess_evidence(self.root, path)["disposition"], "unavailable")
        path.write_text('{"status":"PASS","status":"FAIL"}')
        self.assertEqual(status.assess_evidence(self.root, path)["disposition"], "unavailable")
        path.write_text('{"status":"PASS"}')
        row = status.assess_evidence(self.root, path)
        self.assertEqual(row["original"]["status"], "PASS")
        self.assertEqual(row["disposition"], "unavailable")
        self.assertEqual(status.assess_evidence(self.root, self.root / "missing.json")["disposition"], "unavailable")

    def test_retained_failure_remains_failed_and_aggregate_cannot_hide_it(self):
        row = status.assess_evidence(self.root, self.assessment(result="FAIL"))
        self.write("source.lean", "new-source")
        self.assertEqual(row["disposition"], "failed")
        result = status.aggregate({"claim": {"kind": "validation", "command": "check"}},
                                  [row, {"claim": "claim", "kind": "validation", "disposition": "fresh-pass"}])
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertFalse(result["complete"])

    def test_recycled_pid_and_other_boot_are_abandoned(self):
        proc = self.root / "proc"
        self.write("proc/sys/kernel/random/boot_id", "boot-a")
        # Linux stat fields after comm: state is field 3, starttime field 22.
        self.write("proc/123/stat", "123 (worker with spaces) " + " ".join(["S"] + ["0"] * 18 + ["456"]))
        owner = {"pid": 123, "boot_id": "boot-a", "start_ticks": "456"}
        self.assertEqual(status.process_identity(owner, proc_root=proc)["ownership"], "verified")
        owner["start_ticks"] = "455"
        self.assertEqual(status.process_identity(owner, proc_root=proc)["ownership"], "abandoned")
        owner["boot_id"] = "boot-old"
        self.assertEqual(status.process_identity(owner, proc_root=proc)["ownership"], "abandoned")
        self.assertEqual(status.process_identity({"pid": 123}, proc_root=proc)["ownership"], "unverified")

    def test_cache_registry_real_process_is_verified_without_signals(self):
        proc = Path(f"/proc/{os.getpid()}/stat").read_text()
        owner = {"pid": os.getpid(), "start_ticks": proc[proc.rfind(")") + 2:].split()[19],
                 "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
        self.write("cache/work/one/owner.json", {"owner": owner, "action_key": "abc", "started_at": 1})
        self.write("cache/work/two/owner.json", {"owner": {"pid": os.getpid()}})
        result = status.cache_jobs(self.root / "cache", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["jobs"][0]["ownership"], "verified")
        self.assertEqual(result["jobs"][0]["action_key"], "abc")

    def test_routes_keep_contract_validation_and_history_separate(self):
        config = status.load(Path(__file__).resolve().parents[2] / "scripts/verification_routes.json")
        cases = (("docs/contracts/006-trial-boot-watchdog-v1.html", "contract-review"),
                 ("scripts/build_actions.py", "notebook-qemu"),
                 ("scripts/action_cache.py", "cache-host"),
                 ("scripts/core0_common.py", "kernel-host"))
        for path, claim in cases:
            self.assertIn(claim, status.verification_plan(config, [path])["required_claims"])
        history = status.verification_plan(config, ["docs/plan/006-session-state.html"])
        self.assertNotIn("artifact-production", [row["boundary"] for row in history["affected"]])
        self.assertEqual(set(history["required_claims"]), {"metadata", *config["baseline_claims"]})
        self.assertIn("dependency-review", status.verification_plan(config, ["unknown-helper.py"])["required_claims"])
        self.assertIn("incremental-canonical-qemu", config["baseline_claims"])
        self.assertNotIn("notebook-qemu", config["baseline_claims"])
        focused = status.verification_plan(config, ["scripts/check_incremental_notebook.py"])
        self.assertIn("incremental-canonical-qemu", focused["required_claims"])
        self.assertNotIn("notebook-qemu", focused["required_claims"])
        shared = status.verification_plan(config, ["scripts/check_live_notebook.py"])
        self.assertIn("notebook-qemu", shared["required_claims"])
        self.assertIn("--with-o0", config["claims"]["notebook-qemu"]["command"])

    def test_build_inspection_uses_real_receipts_and_cannot_pass_execution(self):
        from action_cache import ActionCache
        self.write("scripts/build_actions.py", "fixture-recipe")
        self.write("scripts/audit_kernel.py", "fixture-validator")
        self.write("scripts/build_admission.py", "fixture-admission-validator")
        for helper in ("core0_common.py", "action_worker.py", "build_dependencies.py"):
            self.write("scripts/" + helper, "fixture-runtime-" + helper)
        source = self.write("source.lean", "real source bytes")
        directory = self.root / "build/kernel/example"
        directory.mkdir(parents=True)
        cache = ActionCache(self.root, self.root / "cache")
        action = {"schema": "lemma-build-actions/1", "recipe_sha256": status.digest(self.root / "scripts/build_actions.py"),
                  "execution_helpers": {helper: status.digest(self.root / "scripts" / helper) for helper in
                                        ("core0_common.py", "action_worker.py", "build_dependencies.py")},
                  "host_python": {"path": sys.executable, "sha256": status.digest(Path(sys.executable))},
                  "tools": {"python": {"path": sys.executable, "sha256": status.digest(Path(sys.executable))}}}
        def produce(work):
            # Execute a real byte transformation. Admission checks its output,
            # original command/result and hashes independently of the producer.
            argv = [sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes().upper())",
                    str(work.inputs["source.lean"]), str(work.outputs["program.ll"])]
            result = subprocess.run(argv, check=True)
            return {"commands": [{"argv": argv, "returncode": result.returncode}]}
        receipt = cache.run(action, {"source.lean": source}, {"program.ll": directory / "program.ll"}, produce,
                            provenance={"commit": "original-commit"},
                            validator={"schema": "lemma-build-actions/1", "audit_kernel_sha256": status.digest(self.root / "scripts/audit_kernel.py"),
                                       "build_admission_sha256": status.digest(self.root / "scripts/build_admission.py")})
        receipt.update(materialized={"program.ll": "program.ll"}, requested_argv=["fixture-export", "source.lean"])
        receipt_path = self.write("build/kernel/example/action-receipts/0000.json", receipt)
        self.write("build/kernel/example/commands.json", [{"route": "lemma-build-actions/1", "admission": "action-receipts/0000.json", "admission_sha256": status.digest(receipt_path)}])
        self.write("build/kernel/example/actions.json", {"schema": "lemma-build-actions/1", "counts": {"fresh": 1, "reused": 0, "incremental": 0},
                    "actions": [{"action_key": receipt["action_key"], "status": "fresh"}]})
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "reused", row)
        self.assertEqual(row["counts"], {"fresh": 1})
        self.assertIn("pending", row["functional_result"])
        aggregate = status.aggregate({"claim": {"kind": "execution", "command": "guest"}}, [row])
        self.assertEqual(aggregate["counts"]["pending"], 1)
        self.write("scripts/action_worker.py", "changed-process-execution")
        self.assertIn("current action execution/dependency helpers differ", status.assess_build(self.root, directory)["reasons"])
        self.write("scripts/action_worker.py", "fixture-runtime-action_worker.py")
        self.write("scripts/build_admission.py", "changed-admission-policy")
        self.assertIn("current validator differs; re-audit required", status.assess_build(self.root, directory)["reasons"])
        self.write("scripts/build_admission.py", "fixture-admission-validator")
        self.write("scripts/audit_kernel.py", "changed-validator")
        self.assertIn("current validator differs; re-audit required", status.assess_build(self.root, directory)["reasons"])
        self.write("build/kernel/example/program.ll", "corruption")
        self.assertTrue(any("materialized output changed" in reason for reason in status.assess_build(self.root, directory)["reasons"]))
        self.write("build/kernel/example/action-receipts/0000.json", {})
        self.assertEqual(status.assess_build(self.root, directory)["disposition"], "unavailable")

    def test_reviewed_registry_is_default_and_missing_receipts_are_unavailable(self):
        path = self.assessment()
        config = {"schema": "lemma-verification-routes/v1", "objective": "fixture objective",
                  "historical_checkpoint": "history.md", "resource_budgets": {}, "boundaries": [],
                  "claims": {"claim": {"kind": "validation", "command": "actual-check"}},
                  "baseline_claims": ["claim"],
                  "evidence_paths": [{"path": "build/assessment.json", "claim": "claim", "kind": "validation"}]}
        self.write("scripts/verification_routes.json", config)
        for args in (("init", "-q"), ("config", "user.email", "fixture@example.invalid"),
                     ("config", "user.name", "Fixture"), ("add", "."), ("commit", "-qm", "fixture")):
            subprocess.run(("git", *args), cwd=self.root, check=True, capture_output=True)
        value = status.collect(self.root, changed=[])
        self.assertEqual(value["aggregate"]["counts"]["reused"], 1)
        self.assertEqual(value["evidence"][0]["selection"], "registered")
        # An unrelated PASS is not discovered by directory scanning.
        self.write("build/unregistered-pass.json", {"status": "PASS"})
        self.assertEqual(len(status.collect(self.root, changed=[])["evidence"]), 1)
        path.unlink()
        missing = status.collect(self.root, changed=[])
        self.assertEqual(missing["aggregate"]["counts"]["unavailable"], 1)
        self.assertFalse(missing["aggregate"]["complete"])
        self.assertEqual(missing["next_action"], "actual-check")
        config["evidence_paths"] = []
        self.write("scripts/verification_routes.json", config)
        self.assertEqual(status.collect(self.root, changed=[])["aggregate"]["counts"]["pending"], 1)

    def derived_build(self, *, extra_output=False):
        """Two real host byte transformations with role-scoped action receipts."""
        from action_cache import ActionCache
        for name in ("build_actions.py", "audit_kernel.py", "build_admission.py",
                     "core0_common.py", "action_worker.py", "build_dependencies.py"):
            self.write("scripts/" + name, "fixture-" + name)
        source = self.write("source.lean", "fixture source bytes")
        directory = self.root / "build/derived"
        role = directory / "users/notebook"
        role.mkdir(parents=True)
        cache = ActionCache(self.root, self.root / "cache")
        action = {"schema": "lemma-build-actions/1",
                  "recipe_sha256": status.digest(self.root / "scripts/build_actions.py"),
                  "execution_helpers": {name: status.digest(self.root / "scripts" / name) for name in
                                        ("core0_common.py", "action_worker.py", "build_dependencies.py")},
                  "host_python": {"path": sys.executable, "sha256": status.digest(Path(sys.executable))},
                  "tools": {"python": {"path": sys.executable, "sha256": status.digest(Path(sys.executable))}}}
        validator = {"schema": "lemma-build-actions/1",
                     "audit_kernel_sha256": status.digest(self.root / "scripts/audit_kernel.py"),
                     "build_admission_sha256": status.digest(self.root / "scripts/build_admission.py")}
        receipts = []
        for kind, input_name, input_path, output_name in (
                ("fixture-export", "source.lean", source, "program.ll"),
                ("opt", "program.ll", role / "program.ll", "program.opt.ll")):
            outputs = {output_name: role / output_name}
            if kind == "opt" and extra_output:
                outputs["opt.meta"] = role / "opt.meta"
            def produce(work, input_name=input_name, output_name=output_name):
                argv = [sys.executable, "-c",
                        "from pathlib import Path; import sys; "
                        "Path(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes().upper()); "
                        "[Path(p).write_bytes(b'fixture metadata') for p in sys.argv[3:]]",
                        str(work.inputs[input_name]), str(work.outputs[output_name]),
                        *(str(path) for name, path in work.outputs.items() if name != output_name)]
                result = subprocess.run(argv, check=True)
                return {"commands": [{"argv": argv, "returncode": result.returncode}]}
            receipt = cache.run({**action, "kind": kind}, {input_name: input_path}, outputs, produce,
                                provenance={"commit": "original-fixture"}, validator=validator)
            receipt.update(materialized={name: str(path.relative_to(directory)) for name, path in outputs.items()},
                           requested_argv=["fixture-byte-transformation", input_name, output_name])
            receipts.append(receipt)
        def journal(rows):
            commands = []
            for index, receipt in enumerate(rows):
                relative = f"action-receipts/{index:04}.json"
                path = directory / relative
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(receipt))
                commands.append({"route": "lemma-build-actions/1", "admission": relative,
                                 "admission_sha256": status.digest(path)})
            (directory / "commands.json").write_text(json.dumps(commands))
            (directory / "actions.json").write_text(json.dumps({"schema": "lemma-build-actions/1",
                "counts": {"fresh": len(rows)}, "actions": [
                    {"status": "fresh", "action_key": row["action_key"]} for row in rows]}))
        journal(receipts)
        return directory, receipts, journal

    def test_role_generated_input_is_bound_and_root_decoy_cannot_shadow_it(self):
        directory, _, _ = self.derived_build()
        self.write("program.ll", "unrelated checkout file")
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "reused", row)
        self.assertIn("pending", row["functional_result"])
        (directory / "users/notebook/program.ll").write_text("tampered actual role input")
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "pending", row)
        self.assertIn("production input changed: program.ll", row["reasons"])

    def test_generated_input_without_earlier_admitted_output_rejects(self):
        directory, receipts, journal = self.derived_build()
        journal(receipts[1:])
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "pending", row)
        self.assertTrue(any("unbound generated production input" in reason for reason in row["reasons"]))

    def test_cross_role_same_bytes_cannot_substitute_for_generated_input(self):
        directory, receipts, journal = self.derived_build()
        other = directory / "users/arithmetic"
        other.mkdir()
        for name in ("program.ll", "program.opt.ll"):
            (other / name).write_bytes((directory / "users/notebook" / name).read_bytes())
        receipts[1]["materialized"]["program.opt.ll"] = "users/arithmetic/program.opt.ll"
        journal(receipts)
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "pending", row)
        self.assertTrue(any("unbound generated production input" in reason for reason in row["reasons"]))

    def test_ambiguous_generated_input_output_scopes_reject(self):
        directory, receipts, journal = self.derived_build(extra_output=True)
        self.assertEqual(status.assess_build(self.root, directory)["disposition"], "reused")
        other = directory / "users/arithmetic"
        other.mkdir()
        (other / "opt.meta").write_bytes((directory / "users/notebook/opt.meta").read_bytes())
        receipts[1]["materialized"]["opt.meta"] = "users/arithmetic/opt.meta"
        journal(receipts)
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "unavailable", row)
        self.assertIn("ambiguous generated production input scope", row["reasons"][0])

    def test_generated_input_metadata_must_match_earlier_output(self):
        directory, receipts, journal = self.derived_build()
        receipt = receipts[1]
        producer = receipt["producer"]
        producer["request"]["inputs"]["program.ll"]["size"] += 1
        key = status.canonical_digest(producer["request"])
        producer["action_key"] = receipt["action_key"] = key
        receipt["producer_receipt_id"] = status.canonical_digest(producer)
        journal(receipts)
        row = status.assess_build(self.root, directory)
        self.assertEqual(row["disposition"], "pending", row)
        self.assertTrue(any("unbound generated production input" in reason for reason in row["reasons"]))

    def test_registry_cannot_retag_another_claim_and_external_jobs_need_ownership(self):
        path = self.assessment()
        config = {"claims": {"different": {"kind": "validation"}},
                  "evidence_paths": [{"path": "build/assessment.json", "claim": "different", "kind": "validation"}]}
        row = status.registered_evidence(self.root, config)[0]
        self.assertEqual(row["disposition"], "unavailable")
        self.assertEqual(row["claim"], "different")
        proc = Path(f"/proc/{os.getpid()}/stat").read_text()
        owner = {"pid": os.getpid(), "start_ticks": proc[proc.rfind(")") + 2:].split()[19],
                 "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
        job = self.write("job.json", {"owner": owner, "status": "RUNNING", "label": "real host fixture"})
        self.assertEqual(status.external_job(job)["ownership"], "verified")
        self.write("job.json", {"pid": os.getpid(), "status": "RUNNING"})
        self.assertEqual(status.external_job(job)["ownership"], "unverified")
        self.write("job.json", {"owner": owner, "status": "PASS"})
        self.assertEqual(status.external_job(job)["ownership"], "inactive")

    def test_git_status_preserves_first_leading_space_and_renames(self):
        def git(*args):
            return subprocess.run(("git", *args), cwd=self.root, capture_output=True, check=True)
        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        self.write("file with spaces", "old")
        git("add", ".")
        git("commit", "-qm", "fixture")
        clean_id = status.source_state(self.root)["worktree_content_id"]
        self.write("file with spaces", "new")
        changed = status.source_state(self.root)
        self.assertEqual(changed["dirty_paths"], ["file with spaces"])
        self.assertNotEqual(clean_id, changed["worktree_content_id"])
        self.assertEqual(changed["dirty_inputs"]["file with spaces"]["sha256"], status.digest(self.root / "file with spaces"))
        git("mv", "file with spaces", "renamed file")
        self.assertEqual(status.source_state(self.root)["dirty_paths"], ["file with spaces", "renamed file"])

    def test_objective_baseline_keeps_required_claims_after_real_commit(self):
        def git(*args):
            return subprocess.run(("git", *args), cwd=self.root, capture_output=True, check=True).stdout.decode().strip()
        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Fixture")
        self.write("watched.py", "original")
        git("add", ".")
        git("commit", "-qm", "objective baseline")
        baseline = git("rev-parse", "HEAD")
        config = {"schema": "lemma-verification-routes/v1", "comparison_base": baseline,
                  "objective": "fixture", "resource_budgets": {}, "historical_checkpoint": "old.md",
                  "claims": {"behavior": {"kind": "execution", "command": "actual-check"}},
                  "boundaries": [{"id": "consumer", "inputs": ["watched.py", "scripts/verification_routes.json"],
                                  "claims": ["behavior"]}], "evidence_paths": []}
        self.write("scripts/verification_routes.json", config)
        self.write("watched.py", "changed")
        before = status.collect(self.root)
        self.assertEqual(before["aggregate"]["required_claims"][0]["disposition"], "pending")
        git("add", ".")
        git("commit", "-qm", "same changed bytes committed")
        after = status.collect(self.root)
        self.assertEqual(after["source"]["dirty_paths"], [])
        self.assertIn("watched.py", after["source"]["changed_paths"])
        self.assertEqual(after["source"]["since"], baseline)
        self.assertEqual(after["aggregate"]["required_claims"], before["aggregate"]["required_claims"])
        self.assertEqual(status.collect(self.root, since="HEAD")["routing"]["affected"], [])


if __name__ == "__main__":
    unittest.main()
