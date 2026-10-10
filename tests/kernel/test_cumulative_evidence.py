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
        self.value = {"status": "PASS", "source": self.identity,
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


if __name__ == "__main__": unittest.main()
