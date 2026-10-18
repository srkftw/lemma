"""Exercise actual subprocesses, filesystem admission and process coordination."""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from action_cache import (ActionCache, CacheError, file_hash, is_process_alive,
                          process_identity, tool_identity, write_if_changed)


def process_request(root: str, number: int, queue=None, pause: bool = False) -> None:
    directory = Path(root)
    cache = ActionCache(directory)
    def producer(work):
        with (directory / "invocations").open("a") as stream:
            stream.write("execute\n")
        work.outputs["payload"].write_bytes(work.inputs["source"].read_bytes().upper())
        if pause:
            (directory / "ready").write_text("ready")
            time.sleep(30)
        else:
            time.sleep(0.08)
        return {"commands": [{"argv": ["fixture-producer"], "returncode": 0}]}
    receipt = cache.run({"recipe": "concurrent/1"}, {"source": directory / "source"},
                        {"payload": directory / f"out-{number}"}, producer)
    if queue is not None:
        queue.put(receipt["status"])


class ActionCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = ActionCache(self.root)
        self.source = self.root / "input"
        self.source.write_text("hello\n")
        self.program = self.root / "compiler.py"
        self.program.write_text(
            "import pathlib,sys\n"
            "data=pathlib.Path(sys.argv[1]).read_bytes()\n"
            "pathlib.Path(sys.argv[2]).write_bytes(data.upper())\n"
            "with pathlib.Path(sys.argv[3]).open('a') as s:s.write('compile\\n')\n")
        self.inputs = {"input": self.source, "compiler.py": self.program}
        self.outputs = {"payload": self.root / "result"}
        self.action = {"recipe": "test-compiler/1", "tool": tool_identity(sys.executable),
                       "options": ["uppercase"], "environment": {}, "path_semantics": "bytes-only"}

    def producer(self, work):
        command = [sys.executable, str(work.inputs["compiler.py"]), str(work.inputs["input"]),
                   str(work.outputs["payload"]), str(self.root / "count")]
        result = subprocess.run(command, check=True, capture_output=True)
        return {"commands": [{"argv": command, "returncode": result.returncode}]}

    def request(self, **kwargs):
        return self.cache.run(self.action, self.inputs, self.outputs, self.producer, **kwargs)

    def count(self):
        return len((self.root / "count").read_text().splitlines())

    def entry(self, receipt):
        return self.cache.directory / "actions" / f"{receipt['action_key']}.json"

    def test_warm_request_preserves_original_commands_and_uses_independent_copy(self):
        first = self.request(provenance={"commit": "original"})
        self.assertEqual(first["status"], "fresh")
        output_hash = file_hash(self.outputs["payload"])
        self.outputs["payload"].write_text("consumer corruption")
        second = self.request(provenance={"commit": "new"})
        self.assertEqual(second["status"], "reused")
        self.assertEqual(self.count(), 1)
        self.assertEqual(file_hash(self.outputs["payload"]), output_hash)
        self.assertEqual(second["producer_receipt_id"], first["producer_receipt_id"])
        self.assertEqual(second["producer"], first["producer"])
        self.assertEqual(second["producer"]["provenance"]["commit"], "original")
        blob = self.cache.directory / "objects" / output_hash
        self.assertNotEqual(blob.stat().st_ino, self.outputs["payload"].stat().st_ino)

    def test_declared_dependencies_and_options_invalidate_only_their_actions(self):
        first = self.request()
        (self.root / "unrelated.md").write_text("not in explicit compiler closure")
        self.assertEqual(self.request()["action_key"], first["action_key"])
        self.assertEqual(self.count(), 1)
        self.source.write_text("application changed")
        changed = self.request()
        self.assertNotEqual(changed["action_key"], first["action_key"])
        self.assertEqual(self.count(), 2)
        self.program.write_text(self.program.read_text() + "# compiler changed\n")
        compiler = self.request()
        self.assertNotEqual(compiler["action_key"], changed["action_key"])
        self.action["options"] = ["other-optimization"]
        self.assertEqual(self.request()["status"], "fresh")
        self.assertEqual(self.count(), 4)

    def test_validator_change_does_not_recompile(self):
        first = self.request(validator={"policy": "one"})
        second = self.request(validator={"policy": "two"})
        self.assertEqual(self.count(), 1)
        self.assertEqual(first["action_key"], second["action_key"])
        self.assertEqual(second["validator"], {"policy": "two"})
        self.assertEqual(second["status"], "reused")

    def test_fresh_compiles_and_payload_matches_reuse(self):
        first = self.request()
        self.cache.fresh = True
        second = self.request()
        self.assertEqual(second["status"], "fresh")
        self.assertEqual(second["outputs"], first["outputs"])
        self.assertEqual(self.count(), 2)
        self.assertNotEqual(first["producer_receipt_id"], second["producer_receipt_id"])
        self.cache.fresh = False
        self.assertEqual(self.request()["producer_receipt_id"], first["producer_receipt_id"])

    def test_corrupt_missing_and_incompatible_entries_rebuild_and_quarantine(self):
        receipt = self.request()
        blob = self.cache.directory / "objects" / receipt["outputs"]["payload"]["sha256"]
        blob.chmod(0o644)
        blob.write_bytes(b"bad bytes")
        corrupt = self.request()
        self.assertEqual(corrupt["status"], "fresh")
        self.assertIn("rejected", corrupt["reason"])
        blob.unlink()
        missing = self.request()
        self.assertEqual(missing["status"], "fresh")
        self.assertIn("missing", missing["reason"])
        entry = self.entry(missing)
        data = json.loads(entry.read_text())
        data["schema"] = "unsupported"
        entry.chmod(0o644)
        entry.write_text(json.dumps(data))
        incompatible = self.request()
        self.assertEqual(incompatible["status"], "fresh")
        self.assertEqual(self.count(), 4)
        self.assertEqual(len(list((self.cache.directory / "quarantine").iterdir())), 3)

    def test_incomplete_producer_failure_and_extra_outputs_never_publish(self):
        def missing(work):
            return {"commands": []}
        with self.assertRaises(FileNotFoundError):
            self.cache.run(self.action, self.inputs, self.outputs, missing)
        def failing(work):
            work.outputs["payload"].write_text("partial")
            raise RuntimeError("failed command")
        with self.assertRaisesRegex(RuntimeError, "failed command"):
            self.cache.run(self.action, self.inputs, self.outputs, failing)
        def extra(work):
            work.outputs["payload"].write_text("payload")
            (work.directory / "outputs" / "undeclared").write_text("hidden")
            return {"commands": []}
        with self.assertRaisesRegex(CacheError, "undeclared"):
            self.cache.run(self.action, self.inputs, self.outputs, extra)
        self.assertFalse(list((self.cache.directory / "actions").iterdir()))

    def test_same_key_parallel_requests_execute_once(self):
        (self.root / "source").write_bytes(b"concurrent input")
        context = multiprocessing.get_context("fork")
        queue = context.Queue()
        processes = [context.Process(target=process_request, args=(str(self.root), n, queue))
                     for n in range(4)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        statuses = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(statuses.count("fresh"), 1)
        self.assertEqual(statuses.count("reused"), 3)
        self.assertEqual((self.root / "invocations").read_text().splitlines(), ["execute"])
        for n in range(4):
            self.assertEqual((self.root / f"out-{n}").read_bytes(), b"CONCURRENT INPUT")

    def test_killed_producer_is_not_admitted_and_dead_work_can_be_cleaned(self):
        (self.root / "source").write_bytes(b"input")
        context = multiprocessing.get_context("fork")
        process = context.Process(target=process_request, args=(str(self.root), 0, None, True))
        process.start()
        deadline = time.monotonic() + 5
        while not (self.root / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.root / "ready").exists())
        self.assertTrue(any(item["active"] for item in self.cache.inspect()["work"]))
        self.assertEqual(self.cache.cleanup(older_than_seconds=0)["removed"], [])
        os.kill(process.pid, signal.SIGKILL)
        process.join(5)
        self.assertFalse(list((self.cache.directory / "actions").iterdir()))
        self.assertTrue(any(not item["active"] for item in self.cache.inspect()["work"]))
        self.assertTrue(self.cache.cleanup(older_than_seconds=0)["removed"])
        process_request(str(self.root), 1)
        self.assertEqual((self.root / "out-1").read_bytes(), b"INPUT")

    def test_snapshot_detaches_live_edits_and_rejects_snapshot_mutation(self):
        def producer(work):
            self.source.write_text("changed while executing")
            work.outputs["payload"].write_bytes(work.inputs["input"].read_bytes())
            return {"commands": []}
        first = self.cache.run(self.action, self.inputs, self.outputs, producer)
        self.assertEqual(self.outputs["payload"].read_text(), "hello\n")
        self.assertNotEqual(self.request()["action_key"], first["action_key"])
        def corrupt_snapshot(work):
            work.inputs["input"].chmod(0o644)
            work.inputs["input"].write_text("bad")
            work.outputs["payload"].write_bytes(b"bad")
            return {"commands": []}
        self.action["recipe"] = "snapshot-mutation"
        with self.assertRaisesRegex(CacheError, "modified"):
            self.cache.run(self.action, self.inputs, self.outputs, corrupt_snapshot)

    def test_tool_bytes_and_declared_path_semantics(self):
        tool = self.root / "tool"
        tool.write_text("#!/bin/sh\nprintf 'version-one\\n'\n")
        tool.chmod(0o755)
        original = tool_identity(str(tool))
        tool.write_text("#!/bin/sh\nprintf 'version-two\\n'\n")
        changed = tool_identity(str(tool))
        self.assertNotEqual(changed, original)
        self.action["tool"] = original
        first = self.request()
        relocated = self.root / "relocated"
        relocated.mkdir()
        target = {"payload": relocated / "result"}
        receipt = self.cache.run(self.action, self.inputs, target, self.producer)
        self.assertEqual(receipt["status"], "reused")
        self.action["tool"] = changed
        self.assertEqual(self.request()["status"], "fresh")
        self.action["consumed_absolute_path"] = str(relocated)
        self.assertNotEqual(self.request()["action_key"], first["action_key"])

    def test_pid_recycling_is_not_live_ownership_and_pinned_outputs_survive_cleanup(self):
        owner = process_identity()
        self.assertTrue(is_process_alive(owner))
        self.assertFalse(is_process_alive({**owner, "start_ticks": str(int(owner["start_ticks"]) + 1)}))
        self.assertFalse(is_process_alive({**owner, "boot_id": "another-boot"}))
        receipt = self.request()
        self.assertEqual(self.cache.cleanup(older_than_seconds=0,
                                          pinned_keys=(receipt["action_key"],))["removed"], [])
        self.assertTrue(self.entry(receipt).exists())
        archived_receipt = self.root / "retained-evidence" / "producer.json"
        archived_receipt.parent.mkdir()
        archived_receipt.write_text(json.dumps(receipt["producer"]))
        cleanup = self.cache.cleanup(older_than_seconds=0)
        self.assertEqual(self.outputs["payload"].read_text(), "HELLO\n")
        self.assertGreater(cleanup["bytes_reclaimed"], 0)
        self.assertFalse(list((self.cache.directory / "objects").iterdir()))
        self.assertEqual(json.loads(archived_receipt.read_text()), receipt["producer"])

    def test_original_input_archive_is_retained_and_validated(self):
        receipt = self.request()
        source_hash = receipt["producer"]["request"]["inputs"]["input"]["sha256"]
        archived_source = self.cache.directory / "objects" / source_hash
        self.assertEqual(archived_source.read_bytes(), b"hello\n")
        archived_source.chmod(0o644)
        archived_source.write_bytes(b"corrupt historical input")
        second = self.request()
        self.assertEqual(second["status"], "fresh")
        self.assertIn("rejected", second["reason"])
        self.assertEqual(archived_source.read_bytes(), b"hello\n")

    def test_cleanup_preserves_shared_blobs_and_refuses_unknown_references(self):
        first = self.request()
        self.action["options"] = ["independent-action-same-bytes"]
        second = self.request()
        self.cache.cleanup(older_than_seconds=0, pinned_keys=(second["action_key"],))
        self.assertFalse(self.entry(first).exists())
        self.assertEqual(self.request()["status"], "reused")
        orphan = self.cache.directory / "objects" / ("0" * 64)
        orphan.write_bytes(b"orphan")
        bad = self.cache.directory / "receipts" / ("f" * 64 + ".json")
        bad.write_bytes(b"incomplete metadata")
        # A recent unknown receipt survives the age filter and stops blob GC.
        os.utime(orphan, (0, 0))
        result = self.cache.cleanup(older_than_seconds=100,
                                    pinned_keys=(second["action_key"],))
        self.assertTrue(result["objects_retained"])
        self.assertIn("unsafe reference", result["reason"])
        self.assertTrue(orphan.exists())

    def test_fresh_conflict_poisons_key_and_retains_both_original_and_new_outputs(self):
        receipt = self.request()
        self.cache.fresh = True
        def conflict(work):
            work.outputs["payload"].write_bytes(b"different nondeterministic bytes")
            return {"commands": []}
        with self.assertRaisesRegex(CacheError, "conflicts"):
            self.cache.run(self.action, self.inputs, self.outputs, conflict)
        self.cache.fresh = False
        with self.assertRaisesRegex(CacheError,"poisoned"):
            self.request()
        poison = json.loads((self.cache.directory/"poisoned"/f"{receipt['action_key']}.json").read_text())
        archive = Path(poison["conflict_archive"])
        self.assertEqual((archive/"original-outputs/payload").read_bytes(),b"HELLO\n")
        self.assertEqual((archive/"outputs/payload").read_bytes(),b"different nondeterministic bytes")
        self.assertEqual(self.cache.inspect()["entries"][0]["status"],"poisoned")
        self.cache.cleanup(older_than_seconds=0)
        with self.assertRaisesRegex(CacheError,"poisoned"):
            self.request()
        self.assertEqual(self.cache.inspect()["poisoned"][0]["action_key"],receipt["action_key"])
        self.assertTrue((archive/"original-producer.json").exists())

    def test_write_if_changed_preserves_inode_and_mtime(self):
        path = self.root / "generated" / "header.h"
        self.assertTrue(write_if_changed(path, b"constant"))
        identity = path.stat()
        self.assertFalse(write_if_changed(path, b"constant"))
        self.assertEqual(path.stat().st_ino, identity.st_ino)
        self.assertEqual(path.stat().st_mtime_ns, identity.st_mtime_ns)
        self.assertTrue(write_if_changed(path, b"changed"))

    def test_tool_invocation_alias_is_part_of_identity(self):
        canonical = self.root/"canonical-driver"
        canonical.write_text(f"#!{sys.executable}\nprint('same version for both aliases')\n")
        canonical.chmod(0o755)
        first, second = self.root/"frontend-one", self.root/"frontend-two"
        first.symlink_to(canonical)
        second.symlink_to(canonical)
        one, two = tool_identity(str(first)), tool_identity(str(second))
        self.assertEqual(one["path"], two["path"])
        self.assertEqual(one["sha256"], two["sha256"])
        self.assertEqual(one["version_stdout"], two["version_stdout"])
        self.assertNotEqual(one["invoked_as"], two["invoked_as"])


if __name__ == "__main__":
    unittest.main()
