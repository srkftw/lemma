"""Fail-closed report validation fixtures; these execute no target program."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import check_kernel_cumulative as cumulative
from core0_common import Core0Error, sha256


class CumulativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.identity = {"commit": "a" * 40, "tree": "b" * 40, "clean": True}
        self.sources = {"Lemma/Fixture.lean": "c" * 64}
        self.consumers = {"scripts/check_kernel_cumulative.py": "d" * 64}
        self.value = {"schema_version": 1, "artifact_category": "kernel-clean-cumulative-lane",
                      "elapsed_seconds": 100, "deadline_seconds": 2400, "status": "PASS", "source": self.identity,
                      "source_inputs": self.sources, "acceptance_inputs": self.consumers,
                      "source_unchanged_after": True, "acceptance_unchanged_after": True,
                      "lane": "F-I", "cases": []}
        for index, (gate, config, module, protocol, _, opt) in enumerate(cumulative.plan("F-I")):
            directory = self.root / str(index); directory.mkdir()
            image = directory / "image.elf"; image.write_bytes(b"fixture image")
            audit = directory / "audit.json"; audit.write_text('{"status":"PASS"}')
            provenance = directory / "provenance.json"
            provenance.write_text(json.dumps({"source_commit": self.identity["commit"],
                "dirty_paths": [], "source_inputs": self.sources, "configuration": config,
                "optimization": opt, "stage": "supervisor"}))
            result = directory / "result.json"
            result.write_text(json.dumps({"status": "PASS", "observed": {"protocol": protocol}}))
            log = directory / "command.log"; log.write_text("actual fixture command result")
            self.value["cases"].append({"gate": gate, "configuration": config, "optimization": opt,
                "checker": module, "returncode": 0, "image": str(image), "image_sha256": sha256(image),
                "result": str(result), "result_sha256": sha256(result), "audit_sha256": sha256(audit),
                "provenance_sha256": sha256(provenance), "log": str(log), "log_sha256": sha256(log)})
        self.path = self.root / "result.json"

    def validate(self, *, failed_guest=False):
        self.path.write_text(json.dumps(self.value))
        def session(path, image):
            if failed_guest:
                raise Core0Error("actual guest observation failed")
            return json.loads(path.read_text())
        with patch.object(cumulative, "source_identity", return_value=self.identity), \
             patch.object(cumulative, "source_inputs", return_value=self.sources), \
             patch.object(cumulative, "acceptance_inputs", return_value=self.consumers), \
             patch.object(cumulative, "validate_session", side_effect=session):
            return cumulative.validate_lane(self.path, self.root)

    def test_missing_optimization_cannot_pass(self):
        self.value["cases"].pop()
        with self.assertRaises(Core0Error): self.validate()

    def test_changed_actual_artifact_cannot_pass(self):
        Path(self.value["cases"][0]["image"]).write_bytes(b"changed image")
        with self.assertRaises(Core0Error): self.validate()

    def test_dirty_provenance_cannot_pass_even_if_hash_updated(self):
        row = self.value["cases"][0]
        path = Path(row["image"]).parent / "provenance.json"
        value = json.loads(path.read_text()); value["dirty_paths"] = [" M Lemma/Fixture.lean"]
        path.write_text(json.dumps(value)); row["provenance_sha256"] = sha256(path)
        with self.assertRaises(Core0Error): self.validate()

    def test_failing_guest_cannot_pass_from_controller_label(self):
        with self.assertRaises(Core0Error): self.validate(failed_guest=True)

    def test_boolean_returncode_is_not_command_success(self):
        self.value["cases"][0]["returncode"] = False
        with self.assertRaises(Core0Error): self.validate()

    def test_wrong_observed_protocol_cannot_pass_with_new_hash(self):
        row = self.value["cases"][0]
        path = Path(row["result"]); path.write_text('{"status":"PASS","observed":{"protocol":"other"}}')
        row["result_sha256"] = sha256(path)
        with self.assertRaises(Core0Error): self.validate()

    def test_source_inventory_change_cannot_pass(self):
        self.value["source_inputs"] = {"Lemma/Fixture.lean": "e" * 64}
        with self.assertRaises(Core0Error): self.validate()

    def test_complete_bound_fixture_is_accepted(self):
        self.assertEqual(self.validate()["status"], "PASS")


    def test_finite_complete_duration_is_mandatory(self):
        valid = self.value.copy()
        for field, bad in (("elapsed_seconds", True), ("elapsed_seconds", float("nan")),
                           ("elapsed_seconds", float("inf")), ("elapsed_seconds", -1),
                           ("elapsed_seconds", 2401), ("deadline_seconds", False),
                           ("deadline_seconds", float("nan")), ("deadline_seconds", 2401),
                           ("schema_version", True), ("artifact_category", "other")):
            with self.subTest(field=field, bad=bad):
                self.value = dict(valid, **{field: bad})
                with self.assertRaises(Core0Error): self.validate()
        for field in ("elapsed_seconds", "deadline_seconds"):
            self.value = dict(valid); self.value.pop(field)
            with self.subTest(missing=field):
                with self.assertRaises(Core0Error): self.validate()
        self.value = valid

    def test_relative_lane_directory_is_bound_to_explicit_checkout_before_build(self):
        # The CLI accepts relative build/kernel paths. This fixture runs from
        # another cwd and fails deliberately at build, without any guest claim.
        output = self.root / "build/kernel/relative-lane"
        def unavailable(**kwargs):
            self.assertEqual(kwargs["root"], self.root.resolve())
            self.assertEqual(kwargs["output_dir"], output / "J-normal-O0")
            self.assertTrue(kwargs["output_dir"].is_absolute())
            raise Core0Error("fixture builder unavailable")
        with patch.object(cumulative, "source_identity", return_value=self.identity), \
             patch.object(cumulative, "require_tools"), \
             patch.object(cumulative, "source_inputs", return_value=self.sources), \
             patch.object(cumulative, "acceptance_inputs", return_value=self.consumers), \
             patch.object(cumulative, "build", side_effect=unavailable) as builder:
            report = cumulative.check(root=self.root, work_dir=Path("build/kernel/relative-lane"),
                                      lane="J", clean=False, timeout=300, deadline=2400)
        builder.assert_called_once()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["error"], "fixture builder unavailable")
        self.assertEqual(json.loads((output / "result.json").read_text()), report)

    def test_relative_output_traversal_is_rejected_before_build(self):
        with patch.object(cumulative, "build") as builder:
            with self.assertRaisesRegex(Core0Error, "build/kernel subdirectory"):
                cumulative.check(root=self.root, work_dir=Path("../outside"),
                                 lane="J", clean=False, timeout=300, deadline=2400)
        builder.assert_not_called()



class CumulativeDeadlineControllerTests(unittest.TestCase):
    """Real main/check/final validator; build and guest work are host fakes."""
    def run_controller(self, mode):
        from contextlib import ExitStack, redirect_stdout
        from types import SimpleNamespace
        import io
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / "build/kernel").mkdir(parents=True)
            identity = {"commit": "a" * 40, "tree": "b" * 40, "clean": True}
            sources, consumers = {"Lemma/Fixture.lean": "c" * 64}, {"scripts/fixture.py": "d" * 64}
            clock = [0.0]; observations = [0]; validations = [0]
            def fake_build(**kwargs):
                output = kwargs["output_dir"]; output.mkdir()
                (output / "image.elf").write_bytes(b"host fixture image")
                (output / "audit.json").write_text('{"status":"PASS"}')
                (output / "provenance.json").write_text(json.dumps({
                    "source_commit": identity["commit"], "dirty_paths": [], "source_inputs": sources,
                    "configuration": kwargs["configuration"], "optimization": kwargs["opt_level"], "stage": "supervisor"}))
                return {"status": "BUILT"}
            def fake_observer():
                observations[0] += 1
                output = Path(sys.argv[sys.argv.index("--output-dir") + 1]); output.mkdir()
                (output / "result.json").write_text(json.dumps({"status": "PASS", "records": [[1]],
                    "observed": {"protocol": "buffer-service-J-v1"}}))
                clock[0] += 2
                if mode == "last-observer" and observations[0] == 4: clock[0] = 2401
                return 0
            def fake_session(path, image):
                validations[0] += 1
                clock[0] += 1 if validations[0] <= 4 else 3
                if mode == "final-replay" and validations[0] == 8: clock[0] = 2401
                return json.loads(path.read_text())
            with ExitStack() as stack:
                stack.enter_context(patch.object(cumulative, "repo_root", return_value=root))
                stack.enter_context(patch.object(cumulative, "source_identity", return_value=identity))
                stack.enter_context(patch.object(cumulative, "source_inputs", return_value=sources))
                stack.enter_context(patch.object(cumulative, "acceptance_inputs", return_value=consumers))
                stack.enter_context(patch.object(cumulative, "require_tools"))
                stack.enter_context(patch.object(cumulative, "build", side_effect=fake_build))
                stack.enter_context(patch.object(cumulative.importlib, "import_module", return_value=SimpleNamespace(__file__="host_fixture.py", main=fake_observer)))
                stack.enter_context(patch.object(cumulative, "validate_session", side_effect=fake_session))
                stack.enter_context(patch.object(cumulative.time, "monotonic", side_effect=lambda: clock[0]))
                stack.enter_context(patch.object(sys, "argv", ["check_kernel_cumulative.py", "--lane", "J", "--work-dir", "build/kernel/fixture", "--deadline", "2400"]))
                with redirect_stdout(io.StringIO()): code = cumulative.main()
            return code, json.loads((root / "build/kernel/fixture/result.json").read_text()), observations[0], validations[0]

    def test_last_observer_overrun_cannot_pass_actual_main(self):
        code, value, count, _ = self.run_controller("last-observer")
        self.assertEqual(count, 4); self.assertEqual(code, 1); self.assertEqual(value["status"], "FAIL")
        self.assertGreater(value["elapsed_seconds"], value["deadline_seconds"])

    def test_final_replay_overrun_cannot_pass_actual_main(self):
        code, value, count, validations = self.run_controller("final-replay")
        self.assertEqual((count, validations), (4, 8)); self.assertEqual(code, 1)
        self.assertEqual(value["status"], "FAIL"); self.assertEqual(value["failure_category"], "mandatory-lane-evidence")
        self.assertGreater(value["elapsed_seconds"], value["deadline_seconds"])

    def test_success_duration_includes_actual_final_replay(self):
        code, value, count, validations = self.run_controller("success")
        self.assertEqual((count, validations), (4, 8)); self.assertEqual(code, 0)
        self.assertEqual(value["status"], "PASS"); self.assertEqual(value["elapsed_seconds"], 24)


if __name__ == "__main__": unittest.main()
