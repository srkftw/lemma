"""Actual hosted Lean authority, transactions and forced process interruption.

Run after `lake build school school-curriculum` in the pinned environment.
No Python implementation of school transitions supplies the expected state.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

REPO = Path(__file__).resolve().parents[2]
BINARY = Path(os.environ.get("LEMMA_SCHOOL_TEST_BINARY", REPO / ".lake/build/bin/school"))
CURRICULUM = Path(os.environ.get("LEMMA_SCHOOL_TEST_CURRICULUM", REPO / ".lake/build/bin/school-curriculum"))


class Authority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BINARY.is_file() or not CURRICULUM.is_file():
            raise RuntimeError("build actual Lean executables with lake build school school-curriculum")
        cls.unit = json.loads(subprocess.check_output([str(CURRICULUM), "fixture"], cwd=REPO))
        cls.unit["course"]["identity"] = "1"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lemma-school-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "school"
        self.call("init", deployment="deployment-a", clockModel="controlled-ms")

    def command(self, op, actor="owner", **kwargs):
        return dict(op=op, school="school-a", actor=actor, **kwargs)

    def call(self, op, *, error=None, root=None, **kwargs):
        req = self.command(op, **kwargs)
        result = subprocess.run([str(BINARY), str(root or self.root), json.dumps(req)],
                                cwd=REPO, capture_output=True, timeout=15)
        response = json.loads(result.stdout)
        if error:
            self.assertFalse(response["ok"], response)
            self.assertIn(error, response["error"])
            self.assertNotEqual(result.returncode, 0)
            return response
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(response["ok"], response)
        return response["result"]

    def publish(self, unit=None, **kwargs):
        return self.call("publish", definition=unit or self.unit, policy=1, **kwargs)

    def enroll(self, learner="learner"):
        self.publish()
        self.call("enroll", learner=learner, course=1, revision=1)

    def ask(self, sequence=1, task=4):
        return dict(session=41, consent=7, revision=3, object=99, sequence=sequence,
                    source=1, edition=1, task_id=task, cutoff=100, now=120,
                    deadline=1000, grants=1, modality=1)

    def join(self):
        return self.call("join", actor="learner", course=1, revision=1,
                         session="client-a", guestSession=41, expires=10000, ask=self.ask())

    def attempt(self, **kwargs):
        defaults = dict(actor="learner", course=1, revision=1, activity="coefficients",
                        id="attempt-1", values=[0, 1, 1, 2, 1])
        defaults.update(kwargs)
        return self.call("attempt", **defaults)

    def test_versions_exact_checker_assistance_and_due_review(self):
        self.enroll()
        self.join()
        help_result = self.call("assist", actor="learner", session="client-a", ask=self.ask())
        self.assertEqual(help_result["identity"], 60001)
        self.attempt()
        self.attempt()  # lost acknowledgement retry: no duplicate attempt/review
        progress = self.call("progress", actor="learner", now=86400001)
        self.assertEqual(len(progress["attempts"]), 1)
        original = progress["attempts"][0]["data"]
        self.assertTrue(original["assisted"])
        self.assertEqual(original["outcome"], 1)
        self.assertEqual(progress["due"][0]["data"]["activity"], "later-review")
        changed = json.loads(json.dumps(self.unit))
        changed["course"]["edition"] = "2"
        changed["course"]["title"] += " revised"
        self.publish(changed)
        old = self.call("progress", actor="learner")["attempts"][0]["data"]
        self.assertEqual(old["definition"], original["definition"])
        self.assertEqual(old["revision"], 1)

    def test_independent_teacher_review_does_not_claim_exact_check(self):
        self.enroll()
        self.attempt(activity="reason")
        row = self.call("progress", actor="learner")["attempts"][0]["data"]
        self.assertEqual(row["outcome"], 4)
        self.assertEqual(row["checker"], "teacher-review/1")
        self.assertTrue(row["independent"])
        self.assertFalse(row["assisted"])
        self.join()
        self.call("assist", actor="learner", session="client-a", ask=self.ask(task=6), error="prohibits assistance")

    def test_immutable_definition_and_unsupported_editor_diagnostics(self):
        self.publish()
        changed = json.loads(json.dumps(self.unit))
        changed["course"]["title"] += " conflicting"
        self.publish(changed, error="immutable publication conflict")
        unknown = json.loads(json.dumps(self.unit))
        unknown["secretModelExecution"] = True
        self.publish(unknown, error="unsupported")

    def test_school_actor_session_and_sequence_admission(self):
        self.enroll()
        self.call("status", actor="learner", error="grant denied")
        self.call("publish", actor="learner", definition=self.unit, policy=1, error="grant denied")
        raw = self.command("enroll", learner="intruder", course=1, revision=1)
        raw["school"] = "school-b"
        result = subprocess.run([str(BINARY), str(self.root), json.dumps(raw)], capture_output=True)
        self.assertIn("cross-school", json.loads(result.stdout)["error"])
        self.join()
        self.call("assist", actor="outsider", session="client-a", ask=self.ask(), error="actor")
        self.call("assist", actor="learner", session="client-a", ask=self.ask())
        self.call("assist", actor="learner", session="client-a", ask=self.ask(), error="replayed")
        self.call("cancel-session", actor="learner", session="client-a")
        self.call("assist", actor="learner", session="client-a", ask=self.ask(2), error="cancelled")

    def submit_job(self, job="job-a", class_name="interactive", **kwargs):
        return self.call("job-submit", job=job, **{"class": class_name},
                         input={"kind": "test-byte-operation/1", "data": [1, 2]}, artifacts=[], **kwargs)

    def stage(self, text="result-bytes"):
        path = self.base / "result"
        path.write_text(text)
        result = self.call("artifact-put", path=str(path))
        self.assertEqual(result["digest"], hashlib.sha256(text.encode()).hexdigest())
        return result["digest"]

    def test_fences_worker_identity_cancellation_and_commit_retry(self):
        self.submit_job()
        lease = self.call("job-lease", job="job-a", worker="worker-a", duration=1000, now=10)["record"]["data"]
        later = self.call("job-lease", job="job-a", worker="worker-b", duration=1000, now=1010)["record"]["data"]
        digest = self.stage()
        self.call("job-complete", job="job-a", worker="worker-a", generation=1, fence=lease["fence"], result=digest, now=1011, error="worker")
        self.call("job-complete", job="job-a", worker="worker-b", generation=1, fence=lease["fence"], result=digest, now=1011, error="stale")
        done = dict(job="job-a", worker="worker-b", generation=1, fence=later["fence"], result=digest, now=1011)
        self.call("job-complete", **done)
        self.call("job-complete", **done)
        self.assertEqual(len(self.call("jobs")), 1)
        self.submit_job("job-b")
        b = self.call("job-lease", job="job-b", worker="worker-a", duration=1000, now=1012)["record"]["data"]
        self.call("job-cancel", job="job-b", now=1013)
        self.call("job-complete", job="job-b", worker="worker-a", generation=1, fence=b["fence"], result=digest, now=1014, error="cancelled")

    def test_bulk_backpressure_reserves_interactive_capacity(self):
        for i in range(28):
            self.submit_job(f"bulk-{i}", "bulk")
        self.submit_job("bulk-full", "bulk", error="backpressure")
        for i in range(4):
            self.submit_job(f"interactive-{i}")
        self.submit_job("overfull", error="backpressure")
        self.call("job-cancel", job="bulk-0")
        self.submit_job("interactive-after-cancel")
        big = self.base / "oversize"
        with big.open("wb") as f:
            f.truncate(8388609)
        self.call("artifact-put", path=str(big), error="exceeds")

    def cut(self, op, phase, **kwargs):
        env = dict(os.environ, LEMMA_SCHOOL_TEST_CUT=phase)
        process = subprocess.Popen([str(BINARY), str(self.root), json.dumps(self.command(op, **kwargs))],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                   start_new_session=True)
        try:
            ready, _, _ = select.select([process.stderr], [], [], 15)
            self.assertTrue(ready, "authority did not reach actual interruption boundary")
            self.assertEqual(process.stderr.readline().decode().strip(), "SCHOOL_BOUNDARY " + phase)
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            self.assertEqual(process.stdout.read(), b"")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_termination_artifact_staging_and_before_after_commit(self):
        self.cut("publish", "after-artifact", definition=self.unit, policy=1)
        self.assertEqual(self.call("status")["records"], 0)
        self.assertGreater(self.call("gc")["reclaimed"], 0)
        self.cut("publish", "before-commit", definition=self.unit, policy=1)
        self.assertEqual(self.call("status")["records"], 0)
        self.cut("publish", "after-commit", definition=self.unit, policy=1)
        self.assertEqual(self.call("status")["records"], 1)
        self.assertTrue(self.publish()["reused"])
        self.call("gc")
        self.assertEqual(self.call("status")["records"], 1)

    def test_actual_daemon_abrupt_restart_rejects_old_generation(self):
        self.submit_job()
        self.call("job-lease", job="job-a", worker="worker-a", duration=60000)
        proc = subprocess.Popen([sys.executable, str(REPO / "scripts/school_transport.py"),
                                 "--binary", str(BINARY), str(self.root), "serve"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
        try:
            proc.stdin.write(json.dumps(self.command("status")).encode() + b"\n")
            proc.stdin.flush()
            status = json.loads(proc.stdout.readline())["result"]
            self.assertEqual(status["generation"], 2)
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            proc.stdin.close()
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(self.call("status")["generation"], 2)
        digest = self.stage()
        self.call("job-complete", job="job-a", worker="worker-a", generation=1, fence=1,
                  result=digest, error="stale")
        self.call("reconcile")
        first = self.call("status")["records"]
        self.call("reconcile")
        self.assertEqual(self.call("status")["records"], first)

    def test_export_restore_and_definition_clone_are_independent(self):
        self.enroll()
        self.attempt()
        self.submit_job()
        lease = self.call("job-lease", job="job-a", worker="worker-a", duration=60000)["record"]["data"]
        digest = self.stage()
        exported = self.base / "export"
        self.call("export", to=str(exported))
        restored = self.base / "restored"
        self.call("restore", root=restored, **{"from": str(exported)}, offline=True)
        self.assertEqual(len(self.call("progress", root=restored, actor="learner")["attempts"]), 1)
        self.call("job-complete", root=restored, job="job-a", worker="worker-a", generation=1,
                  fence=lease["fence"], result=digest, error="stale")
        cloned = self.base / "clone"
        clone = self.call("clone", to=str(cloned), newSchool="school-b", newDeployment="deployment-b")
        self.assertEqual(clone["learnerRecords"], 0)
        left = self.root / "artifacts" / digest
        if left.exists():
            for target in restored.glob("artifacts/*"):
                self.assertNotEqual(target.stat().st_ino, (self.root / "artifacts" / target.name).stat().st_ino)
        self.assertNotEqual((restored / "state.json").stat().st_ino, (self.root / "state.json").stat().st_ino)

    def test_missing_committed_artifact_and_corrupt_snapshot_fail_closed(self):
        self.publish()
        digest = self.call("status")["artifacts"][0]
        (self.root / "artifacts" / digest).unlink()
        self.call("status", error="missing committed artifact")

    def test_selected_history_export_restores_exact_prefix_and_artifact_closure(self):
        self.enroll()
        self.attempt()
        self.submit_job("completed")
        lease = self.call("job-lease", job="completed", worker="worker-a", duration=60000)["record"]["data"]
        result = self.stage("selected committed result")
        self.call("job-complete", job="completed", worker="worker-a", generation=1,
                  fence=lease["fence"], result=result)
        self.submit_job("pending")
        pending = self.call("job-lease", job="pending", worker="worker-a", duration=60000)["record"]["data"]
        original = json.loads((self.root / "state.json").read_text())["payload"]
        through = len(original["records"])
        self.call("enroll", learner="later-learner", course=1, revision=1)
        self.attempt(actor="later-learner", id="later-attempt")
        excluded = self.stage("later private artifact")
        exported = self.base / "selected"
        self.call("export", actor="learner", to=str(exported), throughSequence=through, error="grant denied")
        self.call("export", to=str(exported), throughSequence=through+100, error="throughSequence")
        self.call("export", to=str(exported), throughSequence="not-an-integer", error="Natural number")
        receipt = self.call("export", to=str(exported), throughSequence=through)
        self.assertEqual(receipt["records"], through)
        selected = json.loads((exported / "state.json").read_text())["payload"]
        self.assertEqual(selected["records"], original["records"])
        manifest = json.loads((exported / "export.json").read_text())
        expected = {digest for row in original["records"] for digest in row["artifacts"]}
        self.assertEqual(set(manifest["artifacts"]), expected)
        self.assertEqual({p.name for p in (exported / "artifacts").iterdir()}, expected)
        self.assertEqual(manifest["throughSequence"], through)
        self.assertGreater(manifest["sourceRecords"], through)
        self.assertNotIn(excluded, expected)
        self.assertIn(result, expected)
        restored = self.base / "selected-restored"
        self.call("restore", root=restored, **{"from": str(exported)}, offline=True)
        self.assertEqual(len(self.call("progress", root=restored, actor="learner")["attempts"]), 1)
        self.assertEqual(self.call("progress", root=restored, actor="later-learner")["attempts"], [])
        jobs = {row["key"]: row["data"] for row in self.call("jobs", root=restored)}
        self.assertEqual(jobs["completed"]["result"], result)
        self.call("job-complete", root=restored, job="pending", worker="worker-a", generation=1,
                  fence=pending["fence"], result=result, error="stale")
        for artifact in (restored / "artifacts").iterdir():
            self.assertNotEqual(artifact.stat().st_ino, (self.root / "artifacts" / artifact.name).stat().st_ino)
        self.assertEqual(len(self.call("progress", actor="later-learner")["attempts"]), 1)

    def test_reusable_package_has_a_fresh_independent_authority_consumer(self):
        self.enroll()
        self.attempt()
        self.call("grant", subject="teacher", action="publish", resource="school")
        package_dir = self.base / "definition"
        self.call("definition-export", to=str(package_dir))
        package = json.loads((package_dir / "school-package.json").read_text())
        self.assertEqual(package["schema"], "lemma-school-package/1")
        self.assertEqual(len(package["publications"]), 1)
        for field in ("school", "deployment", "operator", "records", "generation"):
            self.assertNotIn(field, package)
        new_root = self.base / "package-school"
        # Exercise the ordinary mutex transport too: it creates authority.lock
        # before Lean's fresh-destination check and carries no package semantics.
        request = dict(op="init-package", school="school-package-b", actor="new-owner",
                       deployment="deployment-package-b", **{"from": str(package_dir)})
        result = subprocess.run([sys.executable, str(REPO / "scripts/school_transport.py"),
                                 "--binary", str(BINARY), str(new_root), json.dumps(request)],
                                cwd=REPO, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        def new_call(op, **fields):
            response = subprocess.check_output([str(BINARY), str(new_root), json.dumps(
                dict(op=op, school="school-package-b", actor="new-owner", **fields))], cwd=REPO)
            return json.loads(response)["result"]
        status = new_call("status")
        self.assertEqual(status["school"], "school-package-b")
        self.assertEqual(new_call("progress")["attempts"], [])
        state = json.loads((new_root / "state.json").read_text())["payload"]
        if isinstance(state, str):
            state = json.loads(state)
        self.assertTrue(all(row["kind"] == "publication" for row in state["records"]))
        for artifact in new_root.glob("artifacts/*"):
            self.assertNotEqual(artifact.stat().st_ino,
                                (self.root / "artifacts" / artifact.name).stat().st_ino)
        self.assertEqual(len(self.call("progress", actor="learner")["attempts"]), 1)

    def test_transport_parent_kill_keeps_actual_child_authority_mutex(self):
        for mode in ("serve", json.dumps(self.command("publish", definition=self.unit, policy=1))):
            environment = dict(os.environ, LEMMA_SCHOOL_TEST_CUT="before-commit")
            command = [sys.executable, str(REPO / "scripts/school_transport.py"),
                       "--binary", str(BINARY), str(self.root), mode]
            parent = subprocess.Popen(command, cwd=REPO, env=environment,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            child_pid = None
            try:
                readable, _, _ = select.select([parent.stderr], [], [], 10)
                self.assertTrue(readable, "actual child did not reach its commit boundary")
                self.assertIn(b"SCHOOL_BOUNDARY before-commit", parent.stderr.readline())
                children = Path(f"/proc/{parent.pid}/task/{parent.pid}/children").read_text().split()
                self.assertEqual(len(children), 1)
                child_pid = int(children[0])
                parent.kill()
                parent.wait(timeout=5)
                self.assertEqual(parent.returncode, -signal.SIGKILL)
                competitor = subprocess.run([sys.executable, str(REPO / "scripts/school_transport.py"),
                    "--binary", str(BINARY), str(self.root), json.dumps(self.command("status"))],
                    cwd=REPO, capture_output=True, timeout=5)
                self.assertNotEqual(competitor.returncode, 0)
                self.assertIn(b"already owned", competitor.stderr)
                os.kill(child_pid, signal.SIGKILL)
                child_pid = None
                # Killing the actual child closes its inherited lock. A new
                # transport may now recover the last authoritative snapshot.
                recovered = subprocess.run([sys.executable, str(REPO / "scripts/school_transport.py"),
                    "--binary", str(BINARY), str(self.root), json.dumps(self.command("status"))],
                    cwd=REPO, capture_output=True, timeout=5)
                self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
                self.assertTrue(json.loads(recovered.stdout)["ok"])
            finally:
                if parent.poll() is None:
                    parent.kill()
                parent.wait(timeout=5)
                if child_pid is not None:
                    os.kill(child_pid, signal.SIGKILL)
                for handle in (parent.stdin, parent.stdout, parent.stderr):
                    handle.close()

    def test_package_install_rejects_unknown_requirements_and_existing_storage(self):
        self.publish()
        package_dir = self.base / "definition"
        self.call("definition-export", to=str(package_dir))
        path = package_dir / "school-package.json"
        original = json.loads(path.read_text())
        changed = dict(original, requiredProvider="unimplemented-remote")
        path.write_text(json.dumps(changed))
        self.call("init-package", root=self.base / "unsupported", deployment="new-deployment",
                  **{"from": str(package_dir)}, error="provider")
        path.write_text(json.dumps(original))
        existing = self.base / "occupied"
        existing.mkdir()
        (existing / "keep.txt").write_text("preserve existing contents")
        self.call("init-package", root=existing, deployment="new-deployment",
                  **{"from": str(package_dir)}, error="fresh")
        self.assertEqual((existing / "keep.txt").read_text(), "preserve existing contents")

    def test_consent_changes_dataset_eligibility_without_relabeling_replay(self):
        digest = self.stage("synthetic drawing byte fixture")
        consent = dict(schema="lemma-observation-consent/1", version=1, school="school-a",
                       learner="learner", resource="fixture-ink", collection=True,
                       processing=True, upload=False, retention=True, training=True,
                       exportAllowed=False, revoked=False)
        observation = dict(schema="lemma-observation/1", id="ink-1", executionId="ink-1",
                           school="school-a", learner="learner", modality="ink",
                           sourceClass="syntheticFixture", sourceId="fixture-ink",
                           acquiredAt=100, acquisitionClock="device-clock", calibration=None,
                           quality="synthetic fixture", missingness="present", artifact=digest,
                           origin="synthetic", parentObservationIds=[], execution="live",
                           executionAt=200, executionClock="device-clock", replayOf=None)
        self.call("consent", actor="learner", consent=consent)
        self.call("observation-put", actor="learner", observation=observation)
        self.assertEqual(len(self.call("dataset-eligible", actor="learner")["observations"]), 1)
        replay = self.call("observation-replay", actor="learner", id="ink-1",
                           executionId="replay-1", executionAt=500, executionClock="replay-clock")
        replay = replay["record"]["data"]
        self.assertEqual(replay["id"], "ink-1")
        self.assertEqual(replay["acquiredAt"], 100)
        self.assertEqual(replay["origin"], "synthetic")
        self.assertEqual(len(self.call("dataset-eligible", actor="learner")["observations"]), 1)
        self.call("export", to=str(self.base / "forbidden-export"), error="not consented")
        consent["version"] = 2
        consent["training"] = False
        consent["exportAllowed"] = True
        self.call("consent", actor="learner", consent=consent)
        through = self.call("status")["records"]
        self.call("export", to=str(self.base / "permitted-prefix"), throughSequence=through)
        self.assertEqual(self.call("dataset-eligible", actor="learner")["observations"], [])
        self.assertEqual(len(self.call("observations", actor="learner")["observations"]), 1)
        consent["version"] = 3
        consent["revoked"] = True
        self.call("consent", actor="learner", consent=consent)
        self.assertEqual(self.call("observations", actor="learner")["observations"], [])
        self.call("export", to=str(self.base / "revoked-prefix"), throughSequence=through, error="revoked")

    def test_real_monotonic_http_runtime_expires_lease_and_releases_lock(self):
        real = self.base / "real-school"
        self.call("init", root=real, deployment="real-deployment")
        # The fixture's test helper explicitly controls clocks; this instance
        # instead uses the production monotonic clock without a supplied now.
        envelope = json.loads((real / "state.json").read_text())
        self.assertEqual(envelope["payload"]["clockModel"], "monotonic-ms")
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        proc = subprocess.Popen([sys.executable, str(REPO / "scripts/school_transport.py"),
                                 "--binary", str(BINARY), str(real), "run", "--port", str(port)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        def post(op, **kwargs):
            data = json.dumps(self.command(op, **kwargs)).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/command", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)
        try:
            ready, _, _ = select.select([proc.stderr], [], [], 10)
            self.assertTrue(ready)
            self.assertIn(b"school transport", proc.stderr.readline())
            first = post("status")
            self.assertTrue(first["ok"], first)
            self.assertGreater(first["result"]["clock"], 0)
            declared = dict(job="real-job", **{"class": "interactive"}, input={"data": [1]}, artifacts=[])
            self.assertTrue(post("job-submit", **declared)["ok"])
            self.assertTrue(post("job-lease", job="real-job", worker="local-worker", duration=20)["ok"])
            time.sleep(0.04)
            retried = post("job-lease", job="real-job", worker="replacement", duration=1000)
            self.assertEqual(retried["result"]["record"]["data"]["fence"], 2)
            explicit = post("status", now=0)
            self.assertFalse(explicit["ok"])
            self.assertIn("controlled-ms", explicit["error"])
            before_runtime = json.loads((real / "transport.json").read_text())
            routed = subprocess.run([sys.executable, str(REPO / "scripts/school_transport.py"),
                                        "--binary", str(BINARY), str(real), json.dumps(self.command("status"))],
                                       capture_output=True, timeout=10)
            self.assertEqual(routed.returncode, 0, routed.stdout + routed.stderr)
            self.assertEqual(json.loads(routed.stdout)["result"]["generation"], first["result"]["generation"])
            self.assertEqual(json.loads((real / "transport.json").read_text()), before_runtime)
            competing = subprocess.run([sys.executable, str(REPO / "scripts/school_transport.py"),
                                        "--binary", str(BINARY), str(real), "run", "--port", str(port)],
                                       capture_output=True, timeout=10)
            self.assertNotEqual(competing.returncode, 0)
            self.assertIn(b"already owned", competing.stderr)
            self.assertTrue(post("stop")["result"]["stopping"])
            proc.wait(timeout=10)
            self.assertEqual(proc.returncode, 0)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()
        self.call("status", root=real)


if __name__ == "__main__":
    unittest.main()
