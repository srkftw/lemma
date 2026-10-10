"""Host-only invalid-evidence fixtures; these never establish target execution."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_kernel_timer_negative as negative
from check_kernel_supervisor import S_WITNESS, PMP_CONFIGURATION, MEDELEG, MIDELEG
from check_kernel_user import satp
from core0_common import Core0Error, sha256, write_json


def wire(records):
    return b"".join(("K1" + "".join(f" {word:016x}" for word in row) + "\n").encode() for row in records)


class TimerNegativeEvidence(unittest.TestCase):
    def fixture(self, directory):
        image = directory / "image.elf"
        image.write_bytes(b"host-only-image-fixture")
        ranges = {"_user_start": {"base": 0x10000, "bytes": 64},
                  "churn": {"base": 0x10100, "bytes": 32}, "round": {"base": 0x10200, "bytes": 64},
                  "lemma_exec_syscall": {"base": 0x10400, "bytes": 32}}
        users = {key: {"function_ranges": ranges, "syscall_bridge": {"ecall_pc": 0x10418},
                       "exit_ecall_pc": 0x10024} for key in ("compute", "sleeper", "busy")}
        audit = {"status": "PASS", "configuration": "tasks-development", "stage": "supervisor",
                 "elf": {"users": users}, "user_images": {
                     key: {"id": index + 1, "text_bytes": 512}
                     for index, key in enumerate(("compute", "sleeper", "busy"))}}
        busy = directory / "users/busy"; busy.mkdir(parents=True)
        write_json(busy / "unit.json", {"used_execution_ops": [{"stable_id": "execution.virtual-read64"}],
                   "functions": [{"source": "Lemma.User.Development.Tasks.Busy.main"},
                                 {"source": "Lemma.User.Development.Tasks.Busy.tick"}],
                   "used_loops": [{"stable_id": "action.loop", "callback": "Lemma.User.Development.Tasks.Busy.tick"}]})
        compute = directory / "users/compute"; compute.mkdir(parents=True)
        write_json(compute / "unit.json", {"functions": [
            {"source": "Lemma.User.Development.Tasks.Compute.churn", "symbol": "churn"},
            {"source": "Lemma.User.Development.Tasks.Compute.chunk", "symbol": "round"}]})
        (compute / "audit-user-disassembly.txt").write_text(" 10210: jalr -0x10(ra) <churn>\n 10220: j 0x10210 <round+0x10>\n")
        records = [[0xa, 0x87e00000, 1, 512, 0x82000000],
                   [0xc0, S_WITNESS, PMP_CONFIGURATION, MEDELEG, MIDELEG],
                   [0xc1, 0, 1, 1, 0], [0xc2, 17, 22, 22, 100000],
                   [0xd3, 0x82000000, satp(0x82000000), 500, 0], [0xf0, 1, 8, 512, 10000],
                   [0xf1, 512, 0, 7, 0x82010000], [0xf1, 1024, 1, 8, 0x82020000],
                   [0xf1, 1536, 2, 9, 0x82030000],
                   [0xf3, 512, 0x82010000, 1, 100], [0xf8, 512, 1, 7, 7], [0xf2, 512, 2, 1, 0x10418],
                   [0xf3, 1024, 0x82020000, 1, 200], [0xf8, 1024, 2, 8, 8], [0xf2, 1024, 3, 1, 0x10418],
                   [0xf3, 1536, 0x82030000, 1, 300]]
        import struct
        sent = struct.pack("<5Q", 0x30, 7, 8, 9, 0)
        return image, audit, records, sent

    def test_only_the_closed_call5_mutation_is_admitted(self):
        original = (ROOT / negative.FIRMWARE).read_text()
        changed = negative.timer_disabled_source(original)
        self.assertEqual(changed.replace(negative.AFTER, negative.BEFORE, 1), original)
        self.assertIn(".bind (write lastDeadlineAddress (now + payload))", changed)
        for text in (original.replace(negative.BEFORE, ""), original + negative.BEFORE, changed):
            with self.assertRaises(Core0Error):
                negative.timer_disabled_source(text)

    def test_wrong_head_extra_dirty_path_or_extra_firmware_edit_rejects(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/kernel") as temporary:
            root = Path(temporary)
            firmware = root / negative.FIRMWARE; firmware.parent.mkdir(parents=True)
            original = (ROOT / negative.FIRMWARE).read_text(); firmware.write_text(original)
            other = root / "other.txt"; other.write_text("unchanged")
            def git(*args):
                return subprocess.check_output(("git", *args), cwd=root, stderr=subprocess.DEVNULL).decode().strip()
            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=host fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "host fixture")
            commit = git("rev-parse", "HEAD")
            firmware.write_text(negative.timer_disabled_source(original))
            ignored = root / "Lemma/Ignored.lean"
            link = root / "other-link.txt"
            def inputs(_root):
                values = {negative.FIRMWARE: sha256(firmware), "other.txt": sha256(other)}
                if ignored.exists(): values["Lemma/Ignored.lean"] = sha256(ignored)
                if link.exists(): values["other-link.txt"] = sha256(link)
                return values
            with patch.object(negative, "source_inputs", side_effect=inputs):
                result = negative.source_binding(root, commit)
                self.assertEqual(result["control_source_inputs"][negative.FIRMWARE], hashlib.sha256(original.encode()).hexdigest())
                with self.assertRaises(Core0Error): negative.source_binding(root, "0" * 40)
                other.write_text("extra mutation")
                with self.assertRaises(Core0Error): negative.source_binding(root, commit)
                other.write_text("unchanged")
                firmware.write_text(negative.timer_disabled_source(original).replace("else reply pc 17 0", "else reply pc 0 0"))
                with self.assertRaises(Core0Error): negative.source_binding(root, commit)
                firmware.write_text(negative.timer_disabled_source(original))
                (root / ".git/info/exclude").write_text("/Lemma/Ignored.lean\n")
                ignored.write_text("-- ignored extra input must not bind to a clean control\n")
                with self.assertRaisesRegex(Core0Error, "uncommitted or nonregular"):
                    negative.source_binding(root, commit)
                ignored.unlink()
                firmware.write_text(original)
                link.symlink_to("other.txt")
                git("add", "other-link.txt")
                git("-c", "user.name=host fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "symlink fixture")
                commit = git("rev-parse", "HEAD")
                firmware.write_text(negative.timer_disabled_source(original))
                with self.assertRaisesRegex(Core0Error, "uncommitted or nonregular"):
                    negative.source_binding(root, commit)

    def test_only_the_started_peers_and_last_live_busy_prefix_qualifies(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/kernel") as temporary:
            image, audit, records, sent = self.fixture(Path(temporary))
            observed = negative.validate_stalled_runtime(records, sent, image=image, audit=audit)
            self.assertEqual(observed["scheduling_interrupt_returns"], 0)
            self.assertEqual(observed["compute_completion"], "not_observed")
            for mutate in (lambda rows: rows.pop(), lambda rows: rows.__setitem__(5, [0xf0, 1, 8, 512, 1000000]),
                           lambda rows: rows.__setitem__(11, [0xf2, 512, 1, 1, 0x10100]),
                           lambda rows: rows.__setitem__(14, [0xf2, 1024, 2, 1, 0x10418]),
                           lambda rows: rows.__setitem__(10, [0xf8, 512, 1, 8, 8]),
                           lambda rows: rows.__setitem__(15, [0xf3, 512, 0x82010000, 2, 300])):
                bad = copy.deepcopy(records); mutate(bad)
                with self.assertRaises(Core0Error): negative.validate_stalled_runtime(bad, sent, image=image, audit=audit)
            for packet in (sent[:-1], sent + sent):
                with self.assertRaises(Core0Error): negative.validate_stalled_runtime(records, packet, image=image, audit=audit)

    def test_positive_control_requires_exact_clean_committed_revision(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/kernel") as temporary:
            directory = Path(temporary)
            image, audit, _, _ = self.fixture(directory)
            sources = {negative.FIRMWARE: "host-fixture-source"}
            binding = {"control_source_inputs": sources, "commit": "a" * 40}
            provenance = {"source_inputs": sources, "source_commit": binding["commit"], "dirty_paths": [],
                          "configuration": "tasks-development", "stage": "supervisor", "optimization": "O2"}
            audit.update(source_commit=binding["commit"], dirty_paths=[])
            runners = {name: "host-fixture-runner" for name in negative.POSITIVE_RUNNERS}
            value = {"image": str(image), "source_inputs": sources,
                     "image_sha256": "host-fixture-image", "audit_sha256": "host-fixture-audit",
                     "provenance_sha256": "host-fixture-provenance", "runner_inputs": runners,
                     "acceptance_checker_sha256": runners["scripts/check_kernel_tasks.py"],
                     "observed": {"protocol": "preemptive-tasks-F-v1", "final_remaining_frames": 499,
                                  "tasks": {"512": {"image": 0, "complete": True, "arithmetic_preemptions": [1]}}}}
            path = directory / "result.json"; write_json(path, value)
            def validate():
                write_json(directory / "provenance.json", provenance)
                write_json(directory / "audit.json", audit)
                with patch.object(negative, "validate_session", return_value=value), \
                     patch.object(negative, "sha256", return_value="host-fixture-runner"):
                    return negative.positive_control(path, binding, directory, "O2")
            self.assertEqual(validate()["reported_source_commit"], binding["commit"])
            for target, field, bad in ((provenance, "source_commit", "b" * 40),
                                       (provenance, "dirty_paths", [" M " + negative.FIRMWARE]),
                                       (audit, "source_commit", "b" * 40),
                                       (audit, "dirty_paths", [" M " + negative.FIRMWARE])):
                previous = target[field]; target[field] = bad
                with self.assertRaises(Core0Error): validate()
                target[field] = previous

    def test_arbitrary_timeout_early_exit_wrong_binding_and_cleanup_suffix_reject(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/kernel") as temporary:
            directory = Path(temporary)
            image, audit, records, sent = self.fixture(directory)
            binding = {"source_inputs": {negative.FIRMWARE: "host-fixture-sha"}}
            runners = {"host-fixture-runner": "host-fixture-sha"}
            write_json(directory / "audit.json", audit)
            write_json(directory / "provenance.json", {"source_inputs": binding["source_inputs"],
                       "configuration": "tasks-development", "stage": "supervisor"})
            output = directory / "inner"; output.mkdir()
            (output / "received.bin").write_bytes(wire(records))
            (output / "sent.bin").write_bytes(sent)
            (output / "stderr.bin").write_bytes(b"")
            child = subprocess.Popen((sys.executable, "-c", "pass")); child.wait()
            result = {"status": "FAIL", "error": negative.READ_TIMEOUT, "failure_category": "observation-failure",
                      "timeout_seconds": 8, "guest_live_before_cleanup": True,
                      "cleanup": {"explicit_host_stop": True, "process_group_killed": True,
                                  "target_exited_before_cleanup": False, "process_reaped": True},
                      "returncode": -9, "pid": child.pid, "image_sha256": sha256(image),
                      "audit_sha256": sha256(directory / "audit.json"),
                      "provenance_sha256": sha256(directory / "provenance.json"),
                      "source_inputs": binding["source_inputs"], "runner_inputs": runners,
                      "records": records, "raw_artifacts": {name: sha256(output / name) for name in
                                                           ("received.bin", "sent.bin", "stderr.bin")}}
            path = output / "result.json"
            write_json(path, result)
            negative.validate_failed_session(path, image, binding=binding, runners=runners)
            before = path.read_bytes()
            for mutate in (lambda row: row.update(status="PASS"), lambda row: row.update(error="startup timeout"),
                           lambda row: row.update(returncode=0), lambda row: row.update(timeout_seconds=1),
                           lambda row: row["cleanup"].update(target_exited_before_cleanup=True),
                           lambda row: row.update(image_sha256="different"),
                           lambda row: row.update(runner_inputs={})):
                bad = copy.deepcopy(result); mutate(bad); write_json(path, bad)
                with self.assertRaises(Core0Error): negative.validate_failed_session(path, image, binding=binding, runners=runners)
            path.write_bytes(before)
            (output / "received.bin").write_bytes(wire(records) + b"!")
            result["raw_artifacts"]["received.bin"] = sha256(output / "received.bin")
            write_json(path, result)
            with self.assertRaisesRegex(Core0Error, "trailing bytes"):
                negative.validate_failed_session(path, image, binding=binding, runners=runners)
            self.assertEqual((output / "received.bin").read_bytes(), wire(records) + b"!")
            self.assertEqual(json.loads(path.read_text())["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
