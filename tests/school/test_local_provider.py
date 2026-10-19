"""Actual Lean provider admission with explicitly synthetic declaration bytes.

These tests exercise configuration, quotas, reports and fencing. The maintained
job/load scenarios separately register real QEMU launch slots and execute RV64.
"""
import json
import subprocess
import unittest
import test_authority as authority


class LocalProvider(unittest.TestCase):
    setUp = authority.Authority.setUp
    command = authority.Authority.command
    call = authority.Authority.call
    stage = authority.Authority.stage

    def node(self, **changes):
        data = dict(node="local", version=1, provider="local", profile="core0-v0.5",
                    capabilities=["school-linear-worker/1"], maxWorkers=4,
                    memoryBytes=536870912, storageBytes=268435456)
        data.update(changes)
        return self.call("node-config", **data)

    def worker(self, worker="w1", **changes):
        data = dict(worker=worker, version=1, node="local", controller="controller",
                    profile="core0-v0.5", imageSha256=self.image,
                    capabilities=["school-linear-worker/1"], cpuSlots=1,
                    memoryBytes=134217728, inputBytes=88, outputBytes=48, scratchBytes=16384)
        data.update(changes)
        return self.call("worker-config", **data)

    def health(self, worker="w1", status="ready", **changes):
        data = dict(worker=worker, configVersion=1, generation=1, status=status,
                    reason="deliberately synthetic controller launch report; no VM is running",
                    artifacts=[self.image], actor="controller")
        data.update(changes)
        return self.call("worker-health", **data)

    def prepare(self, workers=("w1",)):
        self.image = self.stage("explicitly synthetic registry test bytes, not an RV64 executable")
        self.node()
        for worker in workers:
            self.worker(worker)
            self.health(worker)

    def submit(self, job="j1"):
        return self.call("job-submit", job=job, **{"class": "interactive"}, artifacts=[self.image],
                         input={"kind": "school-linear-worker/1", "imageSha256": self.image,
                                "model": 1, "parameters": self.image, "features": [1, 2], "requestId": 1})

    def lease(self, job="j1", worker="w1", **changes):
        data = dict(job=job, worker=worker, duration=1000)
        data.update(changes)
        return self.call("job-lease", **data)

    def complete_negative(self, lease, error, **changes):
        data = dict(job="j1", worker="w1", generation=lease["generation"], fence=lease["fence"],
                    result=self.image, error=error)
        data.update(changes)
        self.call("job-complete", **data)

    def test_explicit_registry_capability_health_and_controller_admission(self):
        self.image = self.stage("synthetic provider declaration bytes")
        self.submit()
        self.lease(error="node is not configured")
        self.node(provider="unimplemented-remote", error="unsupported")
        first = self.node()["record"]
        self.assertEqual(self.node()["record"], first)
        self.lease(error="worker is not configured")
        self.worker(memoryBytes=1, error="resource profile")
        self.worker(profile="unsupported-profile", error="profile/capability/image")
        self.worker(imageSha256="f" * 64, error="missing committed artifact")
        first = self.worker()["record"]
        self.assertEqual(self.worker()["record"], first)
        self.lease(error="no readiness report")
        self.health(actor="peer", error="controller denied")
        self.health(artifacts=[], error="configured image")
        self.health(configVersion=2, error="stale")
        ready = self.health()["record"]
        self.assertEqual(self.health()["record"], ready)
        lease = self.lease()["record"]["data"]
        self.assertEqual(lease["provider"]["healthSequence"], ready["sequence"])
        self.assertEqual(lease["provider"]["storageBytes"], len(b"synthetic provider declaration bytes"))
        self.assertEqual(lease["provider"]["memoryBytes"], 134217728)
        self.call("provider-status", actor="peer", error="grant denied")

    def test_drain_and_concurrent_slot_memory_storage_reservations(self):
        self.prepare(("w1", "w2", "w3"))
        self.node(version=2, maxWorkers=2, memoryBytes=268435456)
        for job in ("j1", "j2", "j3"):
            self.submit(job)
        self.call("worker-drain", actor="controller", worker="w1", draining=True)
        self.lease(error="draining")
        self.call("worker-drain", actor="controller", worker="w1", draining=False)
        self.lease()
        self.call("node-drain", node="local", draining=True)
        self.lease("j2", "w2", error="draining")
        before = self.call("jobs")
        self.call("reconcile")
        self.assertEqual(self.call("jobs"), before)  # drain preserves current work
        self.call("node-drain", node="local", draining=False)
        self.lease("j2", "w1", error="already owns")
        self.lease("j2", "w2")
        self.lease("j3", "w3", error="slots exhausted")
        self.call("job-cancel", job="j1")
        self.node(version=3, maxWorkers=2, memoryBytes=134217728)
        before = self.call("jobs")
        self.call("reconcile")
        self.assertEqual(self.call("jobs"), before)  # node budget change affects new work
        self.lease("j3", "w3", error="memory reservation exhausted")
        self.call("job-cancel", job="j2")
        self.node(version=4, maxWorkers=2, memoryBytes=268435456, storageBytes=1)
        self.lease("j3", "w3", error="storage reservation exhausted")
        self.node(version=5, maxWorkers=2, memoryBytes=268435456)
        self.lease("j3", "w3")

    def test_offline_requeues_before_expiry_and_reconciliation_converges(self):
        self.prepare(("w1", "w2"))
        self.submit()
        old = self.lease(now=10)["record"]["data"]
        self.health(status="offline", now=11)
        self.complete_negative(old, "not reported ready", now=11)
        self.call("reconcile", now=11)
        rows = self.call("jobs")
        self.assertEqual(rows[0]["data"]["status"], "queued")
        self.assertEqual(rows[0]["data"]["retries"], 1)
        count = self.call("status")["records"]
        self.call("reconcile", now=11)
        self.assertEqual(self.call("jobs"), rows)
        self.assertEqual(self.call("status")["records"], count)
        new = self.lease(worker="w2", now=12)["record"]["data"]
        self.assertGreater(new["fence"], old["fence"])
        self.complete_negative(old, "worker or lease owner differs", now=12)

    def test_offline_ready_cannot_resurrect_old_lease_and_restart_requires_report(self):
        self.prepare()
        self.submit()
        old = self.lease(now=10)["record"]["data"]
        self.health(status="offline", now=11)
        self.health(now=12)
        self.complete_negative(old, "health report superseded", now=12)
        self.call("reconcile", now=12)
        new = self.lease(now=13)["record"]["data"]
        self.assertGreater(new["fence"], old["fence"])
        lines = "\n".join(json.dumps(self.command(op)) for op in ["provider-status", "stop"]) + "\n"
        process = subprocess.run([str(authority.BINARY), str(self.root), "serve"], input=lines,
                                 capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertTrue(all(response["ok"] for response in responses), responses)
        self.assertEqual(responses[0]["result"]["generation"], 2)
        self.lease(now=14, error="readiness configuration/generation is stale")
        self.complete_negative(new, "stale generation", now=14)
        self.health(generation=2, now=14)
        self.lease(now=15)

    def test_pure_completion_drain_and_configuration_epochs(self):
        result = subprocess.run(["lake", "env", "lean", "--run", "tests/school/LocalProviderMain.lean"],
                                cwd=authority.REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checks = json.loads(result.stdout)
        self.assertGreaterEqual(len(checks), 8)
        self.assertTrue(all(checks.values()), checks)
