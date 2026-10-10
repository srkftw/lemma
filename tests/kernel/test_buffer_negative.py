"""Host-only mutation/provenance failure fixtures; never target-run evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_kernel_buffer_negative as negative
from core0_common import Core0Error, sha256, write_json


class BufferNegativeEvidence(unittest.TestCase):
    def temporary(self):
        (ROOT / "build/kernel").mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=ROOT / "build/kernel")

    def test_closed_mutation_rejects_missing_duplicate_and_already_changed_site(self):
        original = (ROOT / negative.SERVER).read_text()
        changed = negative.append_truncated_source(original)
        self.assertEqual(changed.replace(negative.AFTER, negative.BEFORE, 1), original)
        self.assertEqual(changed.count(negative.AFTER), 1)
        self.assertIn("if operation = 4 then if 0 < count then count - 1", changed)
        for source in (changed, original + negative.BEFORE, original.replace(negative.BEFORE, ""),
                       original.replace("(page slot + offset) count", "(page slot + offset) (count - 1)")):
            with self.assertRaises(Core0Error): negative.append_truncated_source(source)

    def test_git_binds_exact_head_only_server_and_no_ignored_extra_input(self):
        with self.temporary() as directory:
            root = Path(directory)
            server = root / negative.SERVER; server.parent.mkdir(parents=True)
            original = (ROOT / negative.SERVER).read_text(); server.write_text(original)
            other = root / "other.txt"; other.write_text("unchanged")
            (root / ".gitignore").write_text("ignored.lean\n")
            def git(*args):
                return subprocess.check_output(("git", *args), cwd=root, stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q"); git("add", ".")
            git("-c", "user.name=host fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "host fixture")
            commit = git("rev-parse", "HEAD")
            server.write_text(negative.append_truncated_source(original))
            sources = {negative.SERVER: sha256(server), "other.txt": sha256(other)}
            with patch.object(negative, "source_inputs", side_effect=lambda _: dict(sources)):
                binding = negative.source_binding(root, commit)
                self.assertEqual(binding["control_source_inputs"][negative.SERVER], hashlib.sha256(original.encode()).hexdigest())
                for bad in ("0" * 40, "HEAD", "0" * 39):
                    with self.assertRaises(Core0Error): negative.source_binding(root, bad)
                other.write_text("extra mutation")
                with self.assertRaises(Core0Error): negative.source_binding(root, commit)
                other.write_text("unchanged")
                ignored = root / "ignored.lean"; ignored.write_text("extra ignored target source")
                sources["ignored.lean"] = sha256(ignored)
                with self.assertRaisesRegex(Core0Error, "uncommitted"): negative.source_binding(root, commit)
                del sources["ignored.lean"]
                server.write_text(negative.append_truncated_source(original) + "\n-- extra target change\n")
                with self.assertRaisesRegex(Core0Error, "canonical"): negative.source_binding(root, commit)

    def fixture(self, directory, *, control=False):
        image = directory / "image.elf"; image.write_bytes(b"host-only-image-fixture")
        (directory / "program.ll").write_bytes(b"host-only-LLVM-fixture")
        commit = "a" * 40
        sources = {negative.SERVER: "host-fixture-source"}
        binding = {"commit": commit, "source_inputs": sources, "control_source_inputs": sources}
        provenance = {"configuration": "service-normal", "stage": "supervisor", "optimization": "O2",
                      "source_commit": commit, "dirty_paths": [] if control else [" M " + negative.SERVER],
                      "source_inputs": sources, "artifacts": {name: sha256(directory / name)
                                                              for name in ("image.elf", "program.ll")}}
        audit = {"status": "PASS", "configuration": "service-normal", "stage": "supervisor",
                 "source_commit": commit, "image_sha256": sha256(image), "optimization": "O2",
                 "dirty_paths": provenance["dirty_paths"]}
        write_json(directory / "provenance.json", provenance); write_json(directory / "audit.json", audit)
        output = directory / "inner"; output.mkdir()
        wire = b"K1" + b" 0000000000000000" * 5 + b"\n"
        for name, data in (("received.bin", wire), ("sent.bin", b"host-only-input-fixture"), ("stderr.bin", b"")):
            (output / name).write_bytes(data)
        child = subprocess.Popen((sys.executable, "-c", "pass")); child.wait()
        runners = negative.runner_inputs(ROOT)
        positive = {name: runners[name] for name in negative.POSITIVE_RUNNERS}
        transport = {name: runners[name] for name in negative.BufferSession.RUNNER_PATHS}
        error = "independent Buffer reference mismatch: host-only distinguishing byte fixture"
        failed_rpc = {"input": {"words": [3, 1, 17, 128, 128]}, "response": {"data_hex": "00" * 128}, "index": 9}
        result = {"status": "FAIL", "image": str(image), "error": error,
                  "service_error": error, "service_error_type": "Core0Error",
                  "failure_category": "observation-failure", "service_failure_category": "buffer-byte-reference",
                  "timeout_seconds": 60, "guest_live_before_cleanup": True, "cleanup": negative.CLEANUP,
                  "returncode": -9, "pid": child.pid, "image_sha256": sha256(image),
                  "audit_sha256": sha256(directory / "audit.json"), "provenance_sha256": sha256(directory / "provenance.json"),
                  "source_inputs": sources, "runner_inputs": transport, "service_runner_inputs": positive,
                  "negative_runner_inputs": runners, "acceptance_checker_sha256": positive["scripts/check_kernel_buffer.py"],
                  "failed_rpc": failed_rpc, "wire_events": ["host-only-event"],
                  "raw_artifacts": {name: sha256(output / name) for name in ("received.bin", "sent.bin", "stderr.bin")}}
        # Synthetic complete cleanup metadata tests only this host validator.
        # Real child-stop behavior belongs to test_buffer_transport fixtures.
        result["uart_quiescence"] = {
            "status": "PASS", "process_group": child.pid, "budget_seconds": 5, "max_cycles": 64,
            "captured_bytes_before": len(wire), "cycles": 1, "resumes": 0,
            "started_monotonic": 1, "original_deadline": 60, "effective_deadline": 6, "frozen_monotonic": 2,
            "observed_stops": [{"pid": child.pid, "code": os.CLD_STOPPED, "signal": signal.SIGSTOP}],
            "final_group_stop_observed": True, "stop_code": os.CLD_STOPPED, "stop_signal": signal.SIGSTOP,
            "frozen_boundary_bytes": len(wire), "partial_bytes": 0, "frozen_stderr_bytes": 0,
            "frozen_stdout_sha256": hashlib.sha256(wire).hexdigest(),
            "frozen_stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "post_kill_boundary_unchanged": True, "post_kill_stderr_unchanged": True}
        facts = {"protocol": "buffer-service-J-byte-failure-v1", "failed_rpc": failed_rpc,
                 "expected_data_hex": "00" * 127 + "ff", "actual_data_hex": "00" * 128,
                 "complete_semantic_replay": True, "replayed_wire_events": 1}
        path = output / "result.json"; write_json(path, result)
        return image, binding, runners, path, result, facts

    def test_failure_binding_rejects_wrong_category_source_cleanup_raw_or_live_pid(self):
        with self.temporary() as directory:
            image, binding, runners, path, result, facts = self.fixture(Path(directory))
            validate = lambda: negative.validate_failed_session(path, image, binding=binding, runners=runners, optimization="O2", root=ROOT)
            with patch.object(negative, "validate_reference_failure", return_value=facts) as replay:
                before = path.read_bytes(); self.assertEqual(validate()["status"], "FAIL")
                self.assertEqual(path.read_bytes(), before)
                mutations = (lambda r: r.update(status="PASS"), lambda r: r.update(error="timeout"),
                             lambda r: r.update(service_failure_category="buffer-response-reference"),
                             lambda r: r.update(service_error="different retained error"),
                             lambda r: r.update(failure_category="post-cleanup-buffer-evidence"),
                             lambda r: r.update(returncode=0), lambda r: r.update(timeout_seconds=61),
                             lambda r: r.update(guest_live_before_cleanup=False),
                             lambda r: r.update(source_inputs={}), lambda r: r.update(negative_runner_inputs={}),
                             lambda r: r.update(image_sha256="different"),
                             lambda r: r.update(image="different-image-path"),
                             lambda r: r.pop("uart_quiescence"),
                             lambda r: r["uart_quiescence"].update(post_kill_boundary_unchanged=False),
                             lambda r: r["uart_quiescence"].update(frozen_stdout_sha256="changed"),
                             lambda r: r["uart_quiescence"].update(observed_stops=[]),
                             lambda r: r.update(cleanup_errors=[{"error": "secondary cleanup failure"}]),
                             lambda r: r["cleanup"].update(target_exited_before_cleanup=True),
                             lambda r: r["cleanup"].update(process_reaped=1))
                for mutate in mutations:
                    bad = copy.deepcopy(result); mutate(bad); write_json(path, bad)
                    with self.assertRaises(Core0Error): validate()
                write_json(path, result)
                live = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(30)"))
                try:
                    write_json(path, {**result, "pid": live.pid})
                    with self.assertRaisesRegex(Core0Error, "absent PID"): validate()
                finally:
                    live.kill(); live.wait()
                write_json(path, result)
                for name in ("received.bin", "sent.bin"):
                    raw = path.parent / name; saved = raw.read_bytes(); raw.write_bytes(saved + b"changed")
                    with self.assertRaisesRegex(Core0Error, "raw bytes changed"): validate()
                    raw.write_bytes(saved)
                (path.parent / "stderr.bin").write_bytes(b"unexpected stderr")
                changed = copy.deepcopy(result); changed["raw_artifacts"]["stderr.bin"] = sha256(path.parent / "stderr.bin")
                write_json(path, changed)
                with self.assertRaisesRegex(Core0Error, "stderr"): validate()
                self.assertEqual(replay.call_count, 1)  # Evidence gates precede semantic replay.

    def test_replay_cannot_qualify_different_byte_or_incomplete_suffix(self):
        with self.temporary() as directory:
            image, binding, runners, path, _, facts = self.fixture(Path(directory))
            for change in ({"actual_data_hex": "00" * 127 + "01"}, {"expected_data_hex": "00" * 128},
                           {"complete_semantic_replay": False}, {"replayed_wire_events": 2},
                           {"failed_rpc": {}}, {"protocol": "different"}):
                with patch.object(negative, "validate_reference_failure", return_value={**facts, **change}):
                    with self.assertRaises(Core0Error):
                        negative.validate_failed_session(path, image, binding=binding, runners=runners, optimization="O2", root=ROOT)

    def test_clean_control_rejects_dirty_commit_wrong_opt_sources_and_runner(self):
        with self.temporary() as directory:
            image, binding, runners, path, report, _ = self.fixture(Path(directory), control=True)
            report.update(status="PASS", source_inputs_after=binding["control_source_inputs"],
                          service_runner_inputs_after=report["service_runner_inputs"],
                          runner_inputs_after=report["runner_inputs"],
                          observed={"protocol": "buffer-service-J-v1", "complete_semantic_replay": True})
            write_json(path, report)
            with patch.object(negative, "validate_session", side_effect=lambda _path, _image: json.loads(path.read_text())), \
                    patch.object(negative, "validate_replay", return_value=report["observed"]):
                self.assertEqual(negative.positive_control(path, binding, ROOT, "O2")["reported_dirty_paths"], [])
                provenance_path = image.parent / "provenance.json"; original = json.loads(provenance_path.read_text())
                for change in ({"dirty_paths": [" M " + negative.SERVER]}, {"source_commit": "b" * 40},
                               {"optimization": "O0"}, {"source_inputs": {}}):
                    write_json(provenance_path, {**original, **change})
                    with self.assertRaises(Core0Error): negative.positive_control(path, binding, ROOT, "O2")
                write_json(provenance_path, original)
                for change in ({"service_runner_inputs": {}}, {"source_inputs_after": {}},
                               {"acceptance_checker_sha256": "changed"}):
                    write_json(path, {**report, **change})
                    with self.assertRaises(Core0Error): negative.positive_control(path, binding, ROOT, "O2")
                write_json(path, report)
                (image.parent / "program.ll").write_bytes(b"changed LLVM")
                with self.assertRaisesRegex(Core0Error, "compiled artifact"): negative.positive_control(path, binding, ROOT, "O2")

    def test_preflight_failure_publishes_fail_and_never_starts_guest(self):
        with self.temporary() as directory:
            output = Path(directory) / "failed-controller"
            with patch.object(negative, "source_binding", side_effect=Core0Error("host fixture rejected source")), \
                    patch.object(negative, "BufferSession") as session:
                report = negative.run(root=ROOT, image=Path(directory) / "image.elf", output_dir=output,
                                      control=Path(directory) / "control.json", expected_commit="a" * 40)
                self.assertEqual(report["status"], "FAIL"); session.assert_not_called()
                self.assertEqual(json.loads((output / "result.json").read_text()), report)
                self.assertEqual(report["inner_positive_checker_status"], "not_run")
            for timeout in (0, True, 59, 61, float("inf")):
                with self.assertRaises(Core0Error):
                    negative.run(root=ROOT, image=ROOT / "missing", output_dir=output,
                                 control=ROOT / "missing-control", expected_commit="a" * 40, timeout=timeout)

    def test_controller_retains_inner_fail_and_rejects_unexpected_checker_success(self):
        # This simulated Session only exercises host orchestration. Its fake
        # artifact and transcript are not guest observations or semantic proofs.
        with self.temporary() as directory:
            image, binding, _, path, inner, facts = self.fixture(Path(directory))
            transport_paths = negative.BufferSession.RUNNER_PATHS
            class HostFixtureSession:
                RUNNER_PATHS = transport_paths
                def __init__(self, **kwargs):
                    self.output_dir = kwargs["output_dir"]; self.output_dir.mkdir()
                    self.report = copy.deepcopy(inner)
                    self.process = SimpleNamespace(poll=lambda: None)
                    for name in inner["raw_artifacts"]:
                        shutil.copyfile(path.parent / name, self.output_dir / name)
                def __enter__(self): return self
                def __exit__(self, _type, error, _traceback):
                    self.report.update(status="FAIL", error=str(error), service_error=str(error))
                    write_json(self.output_dir / "result.json", self.report)
                    return False
            error = Core0Error(inner["error"])
            with patch.object(negative, "source_binding", return_value=binding), \
                    patch.object(negative, "positive_control", return_value={"host_fixture": True}), \
                    patch.object(negative, "BufferSession", HostFixtureSession), \
                    patch.object(negative, "validate_reference_failure", return_value=facts):
                with patch.object(negative, "check_positive", side_effect=error):
                    output = Path(directory) / "qualifying-host-fixture"
                    report = negative.run(root=ROOT, image=image, output_dir=output,
                                          control=Path(directory) / "control.json", expected_commit=binding["commit"])
                self.assertEqual(report["status"], "PASS")
                retained = output / "inner-session/result.json"
                self.assertEqual(json.loads(retained.read_text())["status"], "FAIL")
                self.assertEqual(sha256(retained), report["inner_session"]["sha256"])
                with patch.object(negative, "check_positive", return_value={"fixture": "unexpected success"}):
                    output = Path(directory) / "rejecting-host-fixture"
                    rejected = negative.run(root=ROOT, image=image, output_dir=output,
                                            control=Path(directory) / "control.json", expected_commit=binding["commit"])
                self.assertEqual(rejected["status"], "FAIL")
                self.assertIn("live byte-reference", rejected["error"])


if __name__ == "__main__":
    unittest.main()
