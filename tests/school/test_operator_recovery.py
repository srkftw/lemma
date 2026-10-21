"""Actual Lean authority across synthetic boot domains and real OS barriers.

Clock-domain fixtures replace only host boot identity/monotonic readings. They
never fabricate school records or successful recovery snapshots.
"""
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from test_authority import BINARY, CURRICULUM, REPO


class OperatorRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="lemma-operator-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "school"
        self.environment = dict(os.environ, LEMMA_SCHOOL_TEST_BOOT_ID="synthetic-boot-a",
                                LEMMA_SCHOOL_TEST_MONO_MS="9000000")
        self.call("init", deployment="deployment-a")

    def request(self, op, actor="owner", **fields):
        return dict(op=op, school="school-a", actor=actor, **fields)

    def call(self, op, root=None, error=None, **fields):
        process = subprocess.run([str(BINARY), str(root or self.root), json.dumps(self.request(op, **fields))],
                                 cwd=REPO, env=self.environment, capture_output=True, timeout=20)
        reply = json.loads(process.stdout)
        if error:
            self.assertFalse(reply["ok"], reply)
            self.assertIn(error, reply["error"])
            return reply
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertTrue(reply["ok"], reply)
        return reply["result"]

    def send(self, child, op, **fields):
        child.stdin.write(json.dumps(self.request(op, **fields)).encode() + b"\n")
        child.stdin.flush()
        ready, _, _ = select.select([child.stdout], [], [], 10)
        self.assertTrue(ready, "actual authority did not respond within bound")
        return json.loads(child.stdout.readline())

    def serve(self, environment=None):
        process = subprocess.Popen([str(BINARY), str(self.root), "serve"], cwd=REPO,
                                   env=environment or self.environment, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            for handle in (process.stdin, process.stdout, process.stderr):
                handle.close()
        self.addCleanup(cleanup)
        return process

    def stage(self):
        path = self.base / "result.txt"
        path.write_text("actual operator recovery result")
        return self.call("artifact-put", path=str(path))["digest"]

    def test_restore_lower_uptime_preserves_history_fences_and_accepts_new_work(self):
        unit = json.loads(subprocess.check_output([str(CURRICULUM), "fixture"], cwd=REPO))
        unit["course"]["identity"] = "1"
        self.call("publish", definition=unit, policy=1)
        self.call("enroll", learner="learner", course=1, revision=1)
        self.environment["LEMMA_SCHOOL_TEST_MONO_MS"] = "9100000"
        self.call("attempt", actor="learner", course=1, revision=1, activity="coefficients",
                  id="original", values=[0, 1, 1, 2, 1])
        self.call("job-submit", job="pending", **{"class": "interactive"}, input={"data": [1]}, artifacts=[])
        lease = self.call("job-lease", job="pending", worker="old-worker", duration=60000)["record"]["data"]
        digest = self.stage()
        self.call("artifact-register", artifact=digest, kind="execution-receipt", metadata={})
        original = json.loads((self.root / "state.json").read_text())["payload"]
        backup = self.base / "backup"
        self.call("export", to=str(backup))
        self.environment.update(LEMMA_SCHOOL_TEST_BOOT_ID="synthetic-boot-b", LEMMA_SCHOOL_TEST_MONO_MS="5")
        restored = self.base / "restored"
        receipt = self.call("restore", root=restored, **{"from": str(backup)}, offline=True)
        self.assertEqual(receipt["clockEpochSequence"], 2)
        recovered = json.loads((restored / "state.json").read_text())["payload"]
        self.assertEqual(recovered["records"], original["records"])
        self.assertEqual(recovered["clock"], original["clock"])
        self.assertEqual(recovered["generation"], original["generation"] + 1)
        self.call("job-complete", root=restored, job="pending", worker="old-worker", generation=1,
                  fence=lease["fence"], result=digest, error="stale")
        self.call("reconcile", root=restored)
        new_lease = self.call("job-lease", root=restored, job="pending", worker="new-worker", duration=1000)["record"]["data"]
        self.call("job-complete", root=restored, job="pending", worker="new-worker",
                  generation=recovered["generation"], fence=new_lease["fence"], result=digest)
        self.call("attempt", root=restored, actor="learner", course=1, revision=1,
                  activity="coefficients", id="after-restore", values=[0, 1, 1, 2, 1])
        self.assertEqual(len(self.call("progress", root=restored, actor="learner")["attempts"]), 2)
        # Unknown downtime did not make a future review immediately due.
        self.assertEqual(self.call("progress", root=restored, actor="learner")["due"], [])
        self.environment["LEMMA_SCHOOL_TEST_MONO_MS"] = str(86400005)
        self.assertTrue(self.call("progress", root=restored, actor="learner")["due"])
        for artifact in restored.glob("artifacts/*"):
            self.assertNotEqual(artifact.stat().st_ino, (backup / "artifacts" / artifact.name).stat().st_ino)

    def test_restart_changed_boot_rebases_without_rewriting_old_rows(self):
        self.environment["LEMMA_SCHOOL_TEST_MONO_MS"] = "9002000"
        self.call("job-submit", job="before", **{"class": "interactive"}, input={}, artifacts=[])
        before = json.loads((self.root / "state.json").read_text())["payload"]
        self.environment.update(LEMMA_SCHOOL_TEST_BOOT_ID="synthetic-boot-c", LEMMA_SCHOOL_TEST_MONO_MS="1")
        after = self.call("status")
        self.assertEqual(after["generation"], before["generation"] + 1)
        self.assertEqual(after["clock"], before["clock"])
        self.assertEqual(json.loads((self.root / "state.json").read_text())["payload"]["records"], before["records"])
        self.call("job-submit", job="after", **{"class": "interactive"}, input={}, artifacts=[])
        self.assertEqual(len(self.call("jobs")), 2)

    def test_cached_queries_do_not_recommit_snapshot(self):
        # Use the real host clock, not a fixed test time, so successive queries
        # actually observe increasing uptime. Only domain writes may commit.
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"LEMMA_SCHOOL_TEST_BOOT_ID", "LEMMA_SCHOOL_TEST_MONO_MS"}}
        child = self.serve(environment)
        first = self.send(child, "status")
        self.assertTrue(first["ok"], first)
        snapshot = (self.root / "state.json").read_bytes()
        identity = (self.root / "state.json").stat()
        clocks = []
        for _ in range(30):
            response = self.send(child, "status")
            self.assertTrue(response["ok"], response)
            clocks.append(response["result"]["clock"])
        self.assertGreater(clocks[-1], first["result"]["clock"])
        self.assertEqual((self.root / "state.json").read_bytes(), snapshot)
        after = (self.root / "state.json").stat()
        self.assertEqual((after.st_ino, after.st_mtime_ns), (identity.st_ino, identity.st_mtime_ns))
        changed = self.send(child, "job-submit", job="new", **{"class": "interactive"}, input={}, artifacts=[])
        self.assertTrue(changed["ok"], changed)
        self.assertNotEqual((self.root / "state.json").read_bytes(), snapshot)
        self.assertTrue(self.send(child, "stop")["result"]["stopping"])
        child.wait(timeout=5)

    def test_failed_barrier_stops_authority_without_acknowledging_mutation(self):
        marker = self.base / "fail-barrier"
        helper = self.base / "barrier.py"
        real_helper = REPO / "scripts/school_fs_barrier.py"
        helper.write_text("import pathlib, subprocess, sys\n"
                          f"if pathlib.Path({str(marker)!r}).exists(): raise OSError('injected barrier failure')\n"
                          f"subprocess.run([sys.executable, {str(real_helper)!r}, *sys.argv[1:]], check=True)\n")
        environment = dict(self.environment, LEMMA_SCHOOL_FS_BARRIER=str(helper))
        child = self.serve(environment)
        self.assertTrue(self.send(child, "status")["ok"])
        before = (self.root / "state.json").read_bytes()
        marker.touch()
        failed = self.send(child, "job-submit", job="unacknowledged", **{"class": "interactive"}, input={}, artifacts=[])
        self.assertFalse(failed["ok"])
        self.assertIn("authority stopped", failed["error"])
        child.wait(timeout=5)
        self.assertEqual(child.returncode, 1)
        self.assertEqual((self.root / "state.json").read_bytes(), before)
        self.assertEqual(self.call("jobs"), [])

    def test_lifecycle_start_status_backup_stop_restore_and_private_free_fork(self):
        transport = [sys.executable, str(REPO / "scripts/school_transport.py"), "--binary", str(BINARY)]
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        def invoke(root, operation, *arguments):
            process = subprocess.run([*transport, str(root), operation, "--school", "school-a", "--actor", "owner", *arguments],
                                     cwd=REPO, env=self.environment, capture_output=True, timeout=25)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            reply = json.loads(process.stdout)
            self.assertTrue(reply["ok"], reply)
            return reply["result"]
        invoke(self.root, "start", "--port", str(port))
        self.addCleanup(lambda: subprocess.run([*transport, str(self.root), "stop", "--school", "school-a", "--actor", "owner"],
                                              cwd=REPO, env=self.environment, capture_output=True, timeout=10))
        self.assertTrue((self.root / "transport.json").exists())
        self.assertIn("budgets", invoke(self.root, "status"))
        backup = self.base / "lifecycle-backup"
        invoke(self.root, "backup", "--to", str(backup))
        fork = self.base / "independent-school"
        fork_result = invoke(self.root, "fork", "--to", str(fork), "--new-school", "school-b", "--new-deployment", "deployment-b")
        self.assertEqual(fork_result["learnerRecords"], 0)
        self.assertTrue(invoke(self.root, "stop")["stopping"])
        deadline = time.monotonic() + 5
        while (self.root / "transport.json").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse((self.root / "transport.json").exists())
        self.environment.update(LEMMA_SCHOOL_TEST_BOOT_ID="synthetic-lifecycle-boot", LEMMA_SCHOOL_TEST_MONO_MS="1")
        restored = self.base / "lifecycle-restored"
        self.assertEqual(invoke(restored, "restore", "--from", str(backup))["clockEpoch"], "synthetic-lifecycle-boot")
        self.assertEqual(invoke(restored, "status")["records"], 0)

    def test_protected_endpoint_uses_private_pairing_and_rejects_owner_path_requests(self):
        transport = [sys.executable, str(REPO / "scripts/school_transport.py"), "--binary", str(BINARY), str(self.root)]
        ports = []
        for _ in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        if ports[0] == ports[1]:
            self.fail("OS returned the same ephemeral test port twice")
        def invoke(op, *arguments):
            process = subprocess.run([*transport, op, "--school", "school-a", "--actor", "owner", *arguments],
                                     cwd=REPO, env=self.environment, capture_output=True, timeout=25)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            reply = json.loads(process.stdout)
            self.assertTrue(reply["ok"], reply)
            return reply["result"]
        browser_origin = "http://127.0.0.1:8877"
        invoke("start", "--port", str(ports[0]), "--client-port", str(ports[1]), "--browser-origin", browser_origin)
        self.addCleanup(lambda: subprocess.run([*transport, "stop", "--school", "school-a", "--actor", "owner"],
                                              cwd=REPO, env=self.environment, capture_output=True, timeout=10))
        first = self.base / "learner-a.json"
        second = self.base / "learner-b.json"
        issued = invoke("pair", "--learner", "learner-a", "--to", str(first), "--client-port", str(ports[1]))
        invoke("pair", "--learner", "learner-b", "--to", str(second), "--client-port", str(ports[1]))
        credential = json.loads(first.read_text())
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        self.assertEqual(credential["schema"], "lemma-school-credential/1")
        self.assertNotIn(credential["token"].encode(), (self.root / "state.json").read_bytes())
        def learner(command, token=credential["token"], path="client", authenticated=True, origin=None):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            if authenticated:
                headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(f"http://127.0.0.1:{ports[1]}/v1/{path}",
                                         data=json.dumps(command).encode(), headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                if origin == browser_origin:
                    self.assertEqual(response.headers["Access-Control-Allow-Origin"], browser_origin)
                return json.load(response)
        self.assertTrue(learner({"op": "progress", "actor": "owner", "school": "wrong-school"})["ok"])
        forbidden = learner({"op": "work-put", "path": str(REPO / "flake.lock")})
        self.assertFalse(forbidden["ok"])
        self.assertIn("bounded", forbidden["error"])
        uploaded = learner({"op": "work-upload", "hex": b"opaque written reasoning".hex()})
        self.assertTrue(uploaded["ok"], uploaded)
        with self.assertRaises(urllib.error.HTTPError) as missing:
            learner({"op": "progress"}, authenticated=False)
        self.assertEqual(missing.exception.code, 401)
        missing.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as wrong_path:
            learner({"op": "status"}, path="command")
        wrong_path.exception.close()
        preflight = urllib.request.Request(f"http://127.0.0.1:{ports[1]}/v1/client", method="OPTIONS", headers={
            "Origin": browser_origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type"})
        with urllib.request.urlopen(preflight, timeout=10) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], browser_origin)
        self.assertTrue(learner({"op": "progress"}, origin=browser_origin)["ok"])
        with self.assertRaises(urllib.error.HTTPError) as foreign:
            learner({"op": "progress"}, origin="http://127.0.0.1:9999")
        self.assertEqual(foreign.exception.code, 403)
        self.assertIsNone(foreign.exception.headers.get("Access-Control-Allow-Origin"))
        foreign.exception.close()
        owner_preflight = urllib.request.Request(f"http://127.0.0.1:{ports[0]}/v1/command", method="OPTIONS", headers={
            "Origin": browser_origin, "Access-Control-Request-Method": "POST"})
        with self.assertRaises(urllib.error.HTTPError) as owner_cors:
            urllib.request.urlopen(owner_preflight, timeout=10)
        self.assertIsNone(owner_cors.exception.headers.get("Access-Control-Allow-Origin"))
        owner_cors.exception.close()
        owner_req = urllib.request.Request(f"http://127.0.0.1:{ports[0]}/v1/command",
                    data=json.dumps(self.request("admission-revoke", tokenHash=issued["tokenHash"])).encode())
        with urllib.request.urlopen(owner_req, timeout=10) as response:
            self.assertTrue(json.load(response)["ok"])
        revoked = learner({"op": "progress"})
        self.assertFalse(revoked["ok"])
        self.assertIn("revoked", revoked["error"])
        self.assertTrue(learner({"op": "progress"}, token=json.loads(second.read_text())["token"])["ok"])
        invoke("stop")


if __name__ == "__main__":
    unittest.main()
