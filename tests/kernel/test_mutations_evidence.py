"""Host-only mutation orchestration evidence and owned cleanup fixtures.

No target build, guest or Git mutation is performed by these tests. Complex
existing F/J replays remain tested by their own evidence suites; the aggregate
fixtures test the additional fixed matrix, source, path and immutable bindings.
"""
import copy
import difflib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_kernel_mutations as mutations
from core0_common import Core0Error, load_json, sha256, write_json


class MutationObservationBudgetTests(unittest.TestCase):
    def test_setup_and_replay_allowances_preserve_each_exact_guest_deadline(self):
        for kind, opt in mutations.plan():
            paths = mutations._paths(Path("/host-only/budget-fixture"), kind, opt)
            _, _, _, positive, negative, _, _ = mutations.KINDS[kind]
            for label, argv, _, bound in mutations._case_commands(paths, kind, opt):
                if not label.endswith("-observe"):
                    continue
                guest = negative if label.endswith("-mutant-observe") else positive
                with self.subTest(kind=kind, opt=opt, label=label):
                    self.assertEqual(argv[argv.index("--timeout") + 1], str(guest))
                    self.assertEqual(bound, 120 + guest + 60)
                    # A legitimate mandatory setup alone exceeded the old
                    # timer mutant's entire 38-second process deadline.
                    self.assertGreaterEqual(bound - guest, 70 + 30)
        self.assertEqual(mutations.KINDS["timer"][4], 8)
        self.assertEqual(mutations.KINDS["append"][4], 60)

    def test_larger_observe_allowance_is_clamped_by_remaining_campaign_budget(self):
        class CompletedCommand:
            pid, returncode = 999999999, 0
            waited = None
            def wait(self, *, timeout):
                self.waited = timeout
                return self.returncode
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            runner = object.__new__(mutations.Commands)
            runner.work, runner.report, runner.process = work, {"commands": []}, None
            child = CompletedCommand()
            paths = mutations._paths(work, "timer", "O0")
            label, argv, cwd, bound = mutations._case_commands(paths, "timer", "O0")[-1]
            with patch.object(runner, "remaining", return_value=17), \
                 patch.object(runner, "inventory", return_value={}), \
                 patch.object(mutations.subprocess, "Popen", return_value=child):
                row = runner.run(label, argv, cwd, bound)
            self.assertEqual(child.waited, 17)
            self.assertEqual(row["timeout_seconds"], 17)
            self.assertEqual(row["returncode"], 0)


class MutationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / "build/kernel/mutation-fixture"
        self.work.mkdir(parents=True)
        self.identity = {"commit": "a" * 40, "tree": "b" * 40, "clean": True}
        original = {mutations.timer.FIRMWARE: (ROOT / mutations.timer.FIRMWARE).read_text(),
                    mutations.append.SERVER: (ROOT / mutations.append.SERVER).read_text()}
        for name in mutations.CHECKOUTS:
            checkout = self.work / "checkouts" / name
            for source, text in original.items():
                path = checkout / source; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        control = self.work / "checkouts/control"
        self.sources = {name: sha256(control / name) for name in original}
        self.consumers = {"scripts/check_kernel_mutations.py": "c" * 64}
        self.inventory = {"source_inputs": self.sources, "acceptance_inputs": self.consumers}
        self.bindings, self.control_summaries, self.failed_summaries = {}, {}, {}
        self.value = {"schema_version": 1, "status": "PASS", "protocol": mutations.PROTOCOL,
                      "source": self.identity, **self.inventory, "deadline_seconds": 2400,
                      "elapsed_seconds": 10, "source_unchanged_after": True,
                      "acceptance_unchanged_after": True, "images": 8, "qemu_sessions": 8,
                      "checkouts": {}, "cases": [], "commands": [],
                      "controller_cleanup": {"owned": [], "remaining": [], "killed": [], "reaped": []}}
        for name in mutations.CHECKOUTS:
            checkout = self.work / "checkouts" / name
            self.value["checkouts"][name] = {"path": str(checkout), "initial_source": self.identity,
                                             "initial_inventory": self.inventory}
        for kind in ("timer", "append"):
            module = mutations._module(kind)
            source = module.FIRMWARE if kind == "timer" else module.SERVER
            path = self.work / "checkouts" / kind / source
            path.write_text((module.timer_disabled_source if kind == "timer" else module.append_truncated_source)(original[source]))
            sources = {**self.sources, source: sha256(path)}
            binding = {"commit": self.identity["commit"], "tree": self.identity["tree"],
                       "source_inputs": sources, "control_source_inputs": self.sources,
                       "mutation": {"path": source, "before_sha256": self.sources[source], "after_sha256": sources[source]}}
            self.bindings[kind] = binding
            diff = self.work / "mutations" / (kind + ".diff"); diff.parent.mkdir(exist_ok=True)
            diff.write_text("".join(difflib.unified_diff(original[source].splitlines(True), path.read_text().splitlines(True),
                                                       fromfile=source, tofile=source)))
            self.value["checkouts"][kind].update(source=binding, diff_sha256=sha256(diff))
        for name in mutations.CHECKOUTS:
            self.command("checkout-" + name, ["git", "worktree", "add", "--detach", str(self.work / "checkouts" / name), self.identity["commit"]], self.root, 60)
        for kind, opt in mutations.plan():
            paths = mutations._paths(self.work, kind, opt)
            config, _, _, _, bound, protocol, expected_failure = mutations.KINDS[kind]
            for role in ("control", "mutant"):
                sources = self.sources if role == "control" else self.bindings[kind]["source_inputs"]
                dirty = [] if role == "control" else [" M " + self.bindings[kind]["mutation"]["path"]]
                self.artifact(paths[role + "_artifact"], config, opt, sources, dirty)
            control_path = paths["control_run"] / "result.json"
            write_json(control_path, {"status": "PASS", "image": str(paths["control_artifact"] / "image.elf")})
            summary = {"path": str(control_path), "sha256": sha256(control_path), "status": "host-fixture-control"}
            self.control_summaries[(kind, opt)] = summary
            inner = paths["mutant_run"] / "inner-session"
            inner.mkdir(parents=True)
            for name, content in (("received.bin", b"host-fixture-wire"), ("sent.bin", b"host-fixture-input"), ("stderr.bin", b"")):
                (inner / name).write_bytes(content)
            raw = {name: sha256(inner / name) for name in ("received.bin", "sent.bin", "stderr.bin")}
            cleanup = {"explicit_host_stop": True, "process_group_killed": True,
                       "target_exited_before_cleanup": False, "process_reaped": True}
            write_json(inner / "result.json", {"status": "FAIL", "image": str(paths["mutant_artifact"] / "image.elf"),
                       "returncode": -9, "pid": 999999999, "guest_live_before_cleanup": True,
                       "cleanup": cleanup, "error": "host-only expected replay fixture", "raw_artifacts": raw})
            failed = {"path": str(inner / "result.json"), "sha256": sha256(inner / "result.json"),
                      "status": "FAIL", "cleanup": cleanup, "raw_artifacts": raw,
                      "observed": {"host_fixture": True}}
            self.failed_summaries[(kind, opt)] = failed
            runners = {"host-fixture-runner": "d" * 64}
            write_json(paths["mutant_run"] / "result.json", {
                "status": "PASS", "protocol": protocol, "image": str(paths["mutant_artifact"] / "image.elf"),
                "timeout_seconds": bound, "inner_positive_checker_status": "FAIL", "source": self.bindings[kind],
                "runner_inputs": runners, "source_unchanged_after": True, "runners_unchanged_after": True,
                "observed_expected_failure": expected_failure, "inner_session": failed, "positive_control": summary})
            row = {"mutation": kind, "optimization": opt, "configuration": config, "status": "PASS"}
            with self.mocks(): row.update(mutations.validate_case(row, self.work, self.identity, self.sources))
            self.value["cases"].append(row)
            for label, argv, cwd, limit in mutations._case_commands(paths, kind, opt):
                self.command(label, [self.identity["commit"] if arg == "COMMIT" else arg for arg in argv], cwd, limit)
        self.path = self.work / "result.json"

    def command(self, label, argv, cwd, bound):
        log = self.work / "logs" / (label + ".log"); log.parent.mkdir(exist_ok=True)
        log.write_text("host-only command fixture\n")
        self.value["commands"].append({"label": label, "argv": argv, "cwd": str(cwd),
            "timeout_seconds": bound, "returncode": 0, "pid": 999999999,
            "log": str(log), "log_sha256": sha256(log)})

    def artifact(self, directory, config, opt, sources, dirty):
        directory.mkdir(parents=True)
        image = directory / "image.elf"; image.write_bytes(b"host-only image fixture")
        artifacts = {"image.elf": sha256(image)}
        common = {"configuration": config, "optimization": opt, "stage": "supervisor"}
        commands = [{"returncode": 0}]
        write_json(directory / "provenance.json", {**common, "source_commit": self.identity["commit"],
                   "dirty_paths": dirty, "source_inputs": sources, "artifacts": artifacts, "commands": commands})
        write_json(directory / "build.json", {**common, "status": "BUILT", "artifacts": artifacts,
                   "provenance_sha256": sha256(directory / "provenance.json")})
        write_json(directory / "audit.json", {**common, "status": "PASS", "source_commit": self.identity["commit"],
                   "dirty_paths": dirty, "image_sha256": sha256(image), "commands": commands})

    def mocks(self):
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(mutations, "source_identity", return_value=self.identity))
        stack.enter_context(patch.object(mutations, "_inventory", return_value=self.inventory))
        stack.enter_context(patch.object(mutations, "acceptance_inputs", return_value=self.consumers))
        stack.enter_context(patch.object(mutations, "_detached"))
        for kind in ("timer", "append"):
            module = mutations._module(kind)
            stack.enter_context(patch.object(module, "source_binding", return_value=self.bindings[kind]))
            stack.enter_context(patch.object(module, "runner_inputs", return_value={"host-fixture-runner": "d" * 64}))
            def control(path, binding, root, opt, kind=kind):
                return self.control_summaries[(kind, opt)]
            def failure(path, image, *, binding, runners, kind=kind, **kwargs):
                opt = "O0" if "O0" in str(path) else "O2"
                return self.failed_summaries[(kind, opt)]
            stack.enter_context(patch.object(module, "positive_control", side_effect=control))
            stack.enter_context(patch.object(module, "validate_failed_session", side_effect=failure))
        return stack

    def validate(self):
        write_json(self.path, self.value)
        with self.mocks(): return mutations.validate_campaign(self.path, self.root)

    def refresh_case(self, index):
        row = self.value["cases"][index]
        with self.mocks(): row.update(mutations.validate_case(row, self.work, self.identity, self.sources))

    def test_complete_fixed_campaign_revalidates_each_existing_protocol(self):
        self.assertEqual(self.validate()["status"], "PASS")
        self.assertEqual(mutations.plan(), (("timer", "O0"), ("timer", "O2"), ("append", "O0"), ("append", "O2")))
        self.assertEqual(len(self.value["commands"]), 27)

    def test_missing_duplicate_reordered_or_wrong_profile_case_rejects(self):
        original = copy.deepcopy(self.value)
        for change in (lambda value: value["cases"].pop(),
                       lambda value: value["cases"].__setitem__(1, value["cases"][0]),
                       lambda value: value["cases"].reverse(),
                       lambda value: value["cases"][0].update(configuration="service-development")):
            self.value = copy.deepcopy(original); change(self.value)
            with self.assertRaises(Core0Error): self.validate()

    def test_changed_inner_raw_or_report_never_relabels_an_expected_failure(self):
        paths = mutations._paths(self.work, "append", "O0")
        inner = paths["mutant_run"] / "inner-session/result.json"
        before = inner.read_bytes()
        value = load_json(inner); value["status"] = "PASS"; write_json(inner, value)
        with self.assertRaises(Core0Error): self.validate()
        self.assertEqual(load_json(inner)["status"], "PASS")  # Validator did not rewrite it.
        inner.write_bytes(before)
        (inner.parent / "received.bin").write_bytes(b"changed raw")
        with self.assertRaises(Core0Error): self.validate()
        self.assertEqual(inner.read_bytes(), before)

    def test_cleanup_failure_live_pid_or_missing_reap_is_not_counterexample(self):
        paths = mutations._paths(self.work, "timer", "O0")
        inner = paths["mutant_run"] / "inner-session/result.json"
        original = load_json(inner)
        for change in (lambda row: row.update(cleanup_errors=["injected cleanup failure"]),
                       lambda row: row.update(pid=os.getpid()),
                       lambda row: row["cleanup"].update(process_reaped=False),
                       lambda row: row["cleanup"].update(target_exited_before_cleanup=True)):
            value = copy.deepcopy(original); change(value); write_json(inner, value)
            # Even rebinding report hashes cannot make invalid cleanup pass.
            failed = self.failed_summaries[("timer", "O0")]
            failed["sha256"] = sha256(inner)
            outer = paths["mutant_run"] / "result.json"; report = load_json(outer)
            report["inner_session"] = failed; write_json(outer, report)
            with self.assertRaises(Core0Error): self.validate()

    def test_wrong_clean_control_opt_source_or_mutant_build_fail_closed(self):
        paths = mutations._paths(self.work, "timer", "O0")
        artifact = paths["control_artifact"]
        for name, field, bad in (("provenance.json", "dirty_paths", [" M unexpected"]),
                                 ("provenance.json", "optimization", "O2"),
                                 ("audit.json", "status", "FAIL")):
            original = (artifact / name).read_bytes(); value = load_json(artifact / name)
            value[field] = bad; write_json(artifact / name, value)
            if name == "provenance.json":
                build = load_json(artifact / "build.json"); build["provenance_sha256"] = sha256(artifact / name)
                write_json(artifact / "build.json", build)
            with self.assertRaises(Core0Error): self.validate()
            (artifact / name).write_bytes(original)
            build = load_json(artifact / "build.json"); build["provenance_sha256"] = sha256(artifact / "provenance.json")
            write_json(artifact / "build.json", build)
        (paths["mutant_artifact"] / "image.elf").write_bytes(b"changed compiled image")
        with self.assertRaises(Core0Error): self.validate()

    def test_safe_hash_inventory_and_commands_are_mandatory(self):
        original = copy.deepcopy(self.value)
        for change in (lambda row: row["commands"].pop(),
                       lambda row: row["commands"][3].update(returncode=False),
                       lambda row: row["commands"][3].update(pid=os.getpid()),
                       lambda row: row["commands"][3].pop("log_sha256"),
                       lambda row: row["commands"][3]["argv"].append("--clean"),
                       lambda row: row["checkouts"]["append"].pop("diff_sha256"),
                       lambda row: row.update(deadline_seconds=float("nan")),
                       lambda row: row.update(elapsed_seconds=2401),
                       lambda row: row["controller_cleanup"].update(remaining=[{"pid": 1}])):
            self.value = copy.deepcopy(original); change(self.value)
            with self.assertRaises(Core0Error): self.validate()

    def test_review_diff_must_match_canonical_actual_source(self):
        path = self.work / "mutations/append.diff"; path.write_text("misleading source diff\n")
        self.value["checkouts"]["append"]["diff_sha256"] = sha256(path)
        with self.assertRaisesRegex(Core0Error, "review diff"): self.validate()

    def test_outer_pass_cannot_bypass_either_existing_failure_replay(self):
        write_json(self.path, self.value)
        for kind in ("timer", "append"):
            with self.mocks(), patch.object(mutations._module(kind), "validate_failed_session",
                                           side_effect=Core0Error("inner failure is not the required counterexample")) as validator:
                with self.assertRaisesRegex(Core0Error, "required counterexample"):
                    mutations.validate_campaign(self.path, self.root)
                validator.assert_called_once()

    def test_dangling_output_symlink_and_preflight_deadline_reject_before_any_command(self):
        path = self.root / "build/kernel/dangling"
        path.symlink_to("missing-output")
        with patch.object(mutations, "Commands") as commands:
            with self.assertRaisesRegex(Core0Error, "existing mutation output"):
                mutations.check(root=self.root, work_dir=path, expected_commit=self.identity["commit"])
            commands.assert_not_called()
        inventory = {**self.inventory, "acceptance_inputs": {
            "scripts/check_kernel_mutations.py": sha256(Path(mutations.__file__))}}
        with patch.object(mutations, "source_identity", return_value=self.identity), \
             patch.object(mutations, "_inventory", return_value=inventory), \
             patch.object(mutations, "require_tools"), \
             patch.object(mutations.time, "monotonic", side_effect=[0, 1]), \
             patch.object(mutations, "Commands") as commands:
            with self.assertRaisesRegex(Core0Error, "deadline during clean source validation"):
                mutations.check(root=self.root, work_dir=Path("build/kernel/preflight-timeout"),
                                expected_commit=self.identity["commit"], deadline=.5)
            commands.assert_not_called()

    def test_existing_output_traversal_dirty_source_and_wrong_commit_stop_before_checkout(self):
        for directory, commit in ((self.work, self.identity["commit"]),
                                  (Path("../outside"), self.identity["commit"]),
                                  (Path("build/kernel/new"), "short")):
            with patch.object(mutations, "Commands") as commands:
                with self.assertRaises(Core0Error):
                    mutations.check(root=self.root, work_dir=directory, expected_commit=commit)
                commands.assert_not_called()
        with patch.object(mutations, "source_identity", side_effect=Core0Error("dirty source")), \
             patch.object(mutations, "Commands") as commands:
            with self.assertRaisesRegex(Core0Error, "dirty source"):
                mutations.check(root=self.root, work_dir=Path("build/kernel/new"), expected_commit=self.identity["commit"])
            commands.assert_not_called()
        with patch.object(mutations, "source_identity", return_value=self.identity), \
             patch.object(mutations, "Commands") as commands:
            with self.assertRaisesRegex(Core0Error, "HEAD differs"):
                mutations.check(root=self.root, work_dir=Path("build/kernel/new"), expected_commit="d" * 40)
            commands.assert_not_called()

    def test_artifact_inventory_cannot_escape_through_path_or_symlink(self):
        paths = mutations._paths(self.work, "append", "O2")
        artifact = paths["mutant_artifact"]
        target = self.work / "outside.bin"; target.write_bytes(b"foreign")
        for name in ("../outside.bin", "escaped.bin"):
            if name == "escaped.bin": (artifact / name).symlink_to(target)
            provenance = load_json(artifact / "provenance.json")
            provenance["artifacts"][name] = sha256(target); write_json(artifact / "provenance.json", provenance)
            build = load_json(artifact / "build.json"); build.update(artifacts=provenance["artifacts"], provenance_sha256=sha256(artifact / "provenance.json"))
            write_json(artifact / "build.json", build)
            with self.assertRaises(Core0Error): self.validate()
            provenance["artifacts"].pop(name); write_json(artifact / "provenance.json", provenance)
            build.update(artifacts=provenance["artifacts"], provenance_sha256=sha256(artifact / "provenance.json")); write_json(artifact / "build.json", build)


@unittest.skipUnless(sys.platform.startswith("linux"), "owned child fixture requires Linux /proc and subreaping")
class MutationCleanupTests(unittest.TestCase):
    def test_expired_observation_budget_still_kills_the_owned_process(self):
        import time
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); report = {"status": "FAIL", "commands": []}
            commands = mutations.Commands(work, report, 30, grace=.1)
            try:
                code = "import pathlib,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path('ready').write_text('ready'); time.sleep(20)"
                commands.process = subprocess.Popen((sys.executable, "-c", code), cwd=work, start_new_session=True)
                finish = time.monotonic() + 3
                while not (work / "ready").exists() and time.monotonic() < finish: time.sleep(.01)
                self.assertTrue((work / "ready").exists())
                commands.inventory(); commands.finish = time.monotonic() - 1
                cleanup = commands.cleanup("late-external-interruption")
                self.assertTrue(any(row["pid"] == commands.process.pid for row in cleanup["killed"]))
                self.assertEqual(commands.process.wait(timeout=3), -9)
            finally:
                commands.finish = time.monotonic() + 3
                self.assertFalse(commands.close()["remaining"])

    def test_timeout_reaps_separate_session_descendant_and_preserves_unrelated_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            unrelated = subprocess.Popen((sys.executable, "-c", "import time; time.sleep(20)"), start_new_session=True)
            report = {"status": "FAIL", "commands": []}
            commands = mutations.Commands(work, report, 30, grace=.15)
            try:
                code = ("import pathlib,subprocess,sys,time; "
                        "p=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)'],start_new_session=True); "
                        "pathlib.Path('descendant.pid').write_text(str(p.pid)); time.sleep(20)")
                with self.assertRaisesRegex(Core0Error, "exceeded its bound"):
                    commands.run("native-child-timeout", [sys.executable, "-c", code], work, .3)
                child = int((work / "descendant.pid").read_text())
                row = report["commands"][0]
                self.assertFalse(Path("/proc", str(child)).exists())
                self.assertIsNone(unrelated.poll())
                self.assertFalse(row["cleanup"]["remaining"])
                self.assertTrue(any(item["pid"] == child for item in row["cleanup"]["killed"]))
                self.assertTrue(any(item["pid"] == child and item["returncode"] == -9 for item in row["cleanup"]["reaped"]))
                self.assertEqual(load_json(work / "result.json")["status"], "FAIL")
                self.assertTrue((work / "logs/native-child-timeout.log").is_file())
            finally:
                self.assertFalse(commands.close()["remaining"])
                unrelated.kill(); unrelated.wait(timeout=5)

    def test_preexisting_grandchild_survives_reparenting_during_owned_command(self):
        import time
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            parent_code = """import pathlib, subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
pathlib.Path('unrelated-grandchild.pid').write_text(str(p.pid))
while not pathlib.Path('release-unrelated-parent').exists(): time.sleep(.01)
"""
            parent = subprocess.Popen((sys.executable, "-c", parent_code), cwd=work, start_new_session=True)
            commands = None; child = None
            try:
                finish = time.monotonic() + 3
                while not (work / "unrelated-grandchild.pid").exists() and time.monotonic() < finish: time.sleep(.01)
                self.assertTrue((work / "unrelated-grandchild.pid").exists())
                child = int((work / "unrelated-grandchild.pid").read_text())
                before = mutations._proc(child)
                self.assertIsNotNone(before)
                self.assertEqual(before["ppid"], parent.pid)
                report = {"status": "FAIL", "commands": []}
                commands = mutations.Commands(work, report, 30, grace=.15)
                owned_code = """import pathlib, subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(20)'], start_new_session=True)
pathlib.Path('owned-grandchild.pid').write_text(str(p.pid))
pathlib.Path('release-unrelated-parent').write_text('release')
time.sleep(20)
"""
                with self.assertRaisesRegex(Core0Error, "exceeded its bound"):
                    commands.run("native-reparenting-timeout", [sys.executable, "-c", owned_code], work, .6)
                self.assertEqual(parent.wait(timeout=3), 0)
                after = mutations._proc(child)
                self.assertIsNotNone(after)
                self.assertEqual(after["start"], before["start"])
                self.assertEqual(after["ppid"], os.getpid())
                self.assertNotEqual(after["state"], "Z")
                owned_child = int((work / "owned-grandchild.pid").read_text())
                cleanup = report["commands"][0]["cleanup"]
                self.assertFalse(Path("/proc", str(owned_child)).exists())
                self.assertFalse(cleanup["remaining"])
                self.assertTrue(any(item["pid"] == owned_child for item in cleanup["killed"]))
                self.assertNotIn(child, commands.owned)
                self.assertFalse(any(item["pid"] in (parent.pid, child) for item in cleanup["owned"] + cleanup["killed"] + cleanup["reaped"]))
                self.assertFalse(commands.close()["remaining"])
                commands = None
                self.assertEqual(mutations._proc(child)["start"], before["start"])
            finally:
                if commands is not None: commands.close()
                if parent.poll() is None: parent.kill()
                parent.wait(timeout=5)
                if child is None and (work / "unrelated-grandchild.pid").exists():
                    child = int((work / "unrelated-grandchild.pid").read_text())
                if child is not None:
                    try: os.kill(child, signal.SIGKILL)
                    except ProcessLookupError: pass
                    try: os.waitpid(child, 0)
                    except ChildProcessError: pass

    def test_term_grace_allows_owned_context_to_reap_before_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary); report = {"status": "FAIL", "commands": []}
            commands = mutations.Commands(work, report, 30, grace=1)
            code = """import pathlib, signal, subprocess, sys, time
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], start_new_session=True)
pathlib.Path('descendant.pid').write_text(str(p.pid))
def stop(number, frame):
    p.terminate(); p.wait(timeout=2)
    pathlib.Path('context-reaped').write_text(str(p.returncode))
    raise SystemExit(1)
signal.signal(signal.SIGTERM, stop)
time.sleep(20)
"""
            try:
                with self.assertRaises(Core0Error): commands.run("native-context-timeout", [sys.executable, "-c", code], work, .3)
                self.assertEqual((work / "context-reaped").read_text(), str(-signal.SIGTERM))
                self.assertEqual(report["commands"][0]["cleanup"]["killed"], [])
                self.assertFalse(Path("/proc", (work / "descendant.pid").read_text()).exists())
            finally:
                self.assertFalse(commands.close()["remaining"])


if __name__ == "__main__": unittest.main()
