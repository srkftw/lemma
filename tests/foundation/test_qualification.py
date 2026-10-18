#!/usr/bin/env python3
"""Gate 10 qualification orchestration and fail-closed evidence tests."""

import ast
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_core0
import build_monitor
import gate9_corpus as corpus
import qualify_foundation as qualifier
import run_monitor_session as runner
from core0_common import CommandResult, Core0Error, sha256, write_json


class FoundationQualificationTests(unittest.TestCase):
    def test_real_command_callsites_have_distinct_semantic_evidence_roles(self):
        source = (ROOT / "scripts/qualify_foundation.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_record_command"
        ]
        self.assertEqual(len(calls), 3)
        observed = []
        for call in calls:
            keywords = {keyword.arg: keyword.value for keyword in call.keywords}
            self.assertEqual(set(("name", "evidence_role")) - set(keywords), set())
            self.assertIsInstance(keywords["name"], ast.Constant)
            observed.append((keywords["name"].value, keywords["evidence_role"]))
        stale_roles = {
            role.value for name, role in observed
            if name == "failure" and isinstance(role, ast.Constant)
        }
        self.assertEqual(stale_roles, {
            "stale Gate 9 command", "stale monitor runner command",
        })
        audit_roles = [role for name, role in observed if name == "audit-failure"]
        self.assertEqual(len(audit_roles), 1)
        self.assertIsInstance(audit_roles[0], ast.JoinedStr)
        self.assertTrue(any(
            isinstance(value, ast.FormattedValue)
            and isinstance(value.value, ast.Name)
            and value.value.id == "identifier"
            for value in audit_roles[0].values
        ))
        self.assertEqual(
            "".join(
                value.value for value in audit_roles[0].values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ),
            " audit command",
        )

    def test_reproducibility_catalog_and_provenance_closure_are_exact(self):
        self.assertEqual(
            qualifier.DETERMINISTIC_ARTIFACTS,
            (
                *runner.SOURCE_ARTIFACTS,
                "program.opt.ll",
                "program.o",
                "startup.o",
                "image.elf",
                "image.map",
                "platform.dtb",
                "platform.dts",
            ),
        )
        self.assertEqual(len(qualifier.DETERMINISTIC_ARTIFACTS), 16)
        self.assertIn(Path("scripts/qualify_foundation.py"), build_monitor.HOST_INPUTS)
        source = (ROOT / "scripts/audit_core0.py").read_text(encoding="utf-8")
        self.assertIn('"scripts/qualify_foundation.py"', source)

    def test_actual_success_artifact_role_composition_is_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"

            def evidence(path, role):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((role + "\n").encode())
                return qualifier._artifact(root, path, role)

            evidence(
                gate9 / qualifier.gate9_checker.RESULT_FILE,
                "input Gate 9 result",
            )
            for optimization in qualifier.PROFILES:
                for name in ("build.json", "audit.json", "provenance.json", "image.elf"):
                    evidence(
                        gate9 / optimization / name,
                        f"input Gate 9 {optimization} {name}",
                    )

            rebuild = []
            for optimization in qualifier.PROFILES:
                for name in (
                    *qualifier.DETERMINISTIC_ARTIFACTS,
                    "build.json", "audit.json", "provenance.json",
                ):
                    rebuild.append(evidence(
                        work / "rebuild" / optimization / name,
                        f"{optimization} rebuilt {name}",
                    ))

            phase = work / "failure-experiments/stale-phase9"
            runner_failure = work / "failure-experiments/stale-runner"
            stale = [
                evidence(phase / "check-failure.json", "early Gate 9 failure report"),
                evidence(phase / "old-gate9-results.retained.json", "retained old Gate 9 PASS input"),
            ]
            command_result = CommandResult(("false",), 1, b"stdout", b"stderr", 0.1)
            with mock.patch.object(
                qualifier, "run_bounded", return_value=command_result
            ):
                _, phase_command = qualifier._record_command(
                    root=root, directory=phase, name="failure",
                    evidence_role="stale Gate 9 command", argv=("false",),
                    timeout_seconds=1,
                )
            stale.extend((phase_command["stdout"], phase_command["stderr"]))
            stale.extend((
                evidence(runner_failure / "run.json", "early runner failure report"),
                evidence(runner_failure / "old-run.retained.json", "retained old runner PASS input"),
            ))
            for name in ("sent.bin", "received.bin", "stderr.bin"):
                stale.append(evidence(
                    runner_failure / name, f"failed runner {name}"
                ))
            with mock.patch.object(
                qualifier, "run_bounded", return_value=command_result
            ):
                _, runner_command = qualifier._record_command(
                    root=root, directory=runner_failure, name="failure",
                    evidence_role="stale monitor runner command", argv=("false",),
                    timeout_seconds=1,
                )
            stale.extend((runner_command["stdout"], runner_command["stderr"]))

            artifact_failures = []
            for identifier in ("missing-program-object", "tampered-program-ir"):
                directory = work / "failure-experiments" / identifier
                artifact_failures.append(evidence(
                    directory / "experiment.json", f"{identifier} experiment"
                ))
                with mock.patch.object(
                    qualifier, "run_bounded", return_value=command_result
                ):
                    _, command = qualifier._record_command(
                        root=root, directory=directory, name="audit-failure",
                        evidence_role=f"{identifier} audit command", argv=("false",),
                        timeout_seconds=1,
                    )
                artifact_failures.extend((command["stdout"], command["stderr"]))
            raw = work / "failure-experiments/missing-raw-evidence"
            artifact_failures.extend((
                evidence(raw / "experiment.json", "missing raw evidence experiment"),
                evidence(
                    raw / "old-run.retained.json",
                    "missing raw evidence retained old runner PASS input",
                ),
            ))

            catalog = qualifier._qualification_artifact_catalog(
                root=root, gate9_directory=gate9, work=work,
                rebuild_evidence=rebuild, stale_evidence=stale,
                artifact_evidence=artifact_failures,
            )
            self.assertEqual((len(catalog), len({item["path"] for item in catalog}),
                              len({item["role"] for item in catalog})), (66, 66, 66))
            by_role = {item["role"]: item["path"] for item in catalog}
            self.assertEqual(
                {role: by_role[role] for role in qualifier._mandatory_artifact_role_paths(
                    root, gate9, work
                )},
                qualifier._mandatory_artifact_role_paths(root, gate9, work),
            )
            forged = json.loads(json.dumps(catalog))
            forged[-1]["role"] = forged[0]["role"]
            with self.assertRaisesRegex(Core0Error, "roles are duplicate"):
                qualifier._validate_artifact_role_closure(
                    forged, root=root, gate9_directory=gate9, work=work
                )

    def test_normalized_build_and_audit_only_hide_output_bound_fields(self):
        build = {
            "output_directory": "build/first",
            "artifacts": {"program.ll": "1", "provenance.json": "2"},
            "status": "PASS",
        }
        audit = {
            "directory": "build/first",
            "hashes": {"program.ll": "1", "provenance.json": "2"},
            "status": "PASS",
        }
        normalized_build = qualifier._normal_build(build)
        normalized_audit = qualifier._normal_audit(audit)
        self.assertEqual(build["output_directory"], "build/first")
        self.assertEqual(audit["directory"], "build/first")
        self.assertEqual(normalized_build["output_directory"], "$OUTPUT")
        self.assertEqual(
            normalized_build["artifacts"]["provenance.json"],
            "$INTENTIONAL_PROVENANCE_DIGEST",
        )
        self.assertEqual(normalized_audit["directory"], "$OUTPUT")
        self.assertEqual(
            normalized_audit["hashes"]["provenance.json"],
            "$INTENTIONAL_PROVENANCE_DIGEST",
        )

    @staticmethod
    def _command(cwd, *, elapsed=1.0, stdout="first", stderr=""):
        return {
            "argv": ["tool", "input", "-o", "output"],
            "cwd": cwd,
            "returncode": 0,
            "elapsed_seconds": elapsed,
            "stdout": stdout,
            "stderr": stderr,
        }

    def test_provenance_comparison_records_only_observational_differences(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "build/input/O0"
            rebuilt = root / "build/qualification/rebuild/O0"
            first = {
                "schema_version": 2,
                "source_commit": "a" * 40,
                "commands": [self._command("build/input/O0")],
            }
            second = {
                "schema_version": 2,
                "source_commit": "a" * 40,
                "commands": [
                    self._command(
                        "build/qualification/rebuild/O0",
                        elapsed=2.0,
                        stdout="second",
                    )
                ],
            }
            result = qualifier._compare_provenance(
                first, second, baseline, rebuilt, root
            )
            self.assertTrue(result["stable_fields_equal"])
            self.assertTrue(result["command_structure_equal"])
            self.assertEqual(
                len(result["intentional_command_observation_differences"]), 1
            )
            second["source_commit"] = "b" * 40
            with self.assertRaisesRegex(Core0Error, "source_commit"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            second["source_commit"] = "a" * 40
            second["commands"][0]["argv"] = ["different"]
            with self.assertRaisesRegex(Core0Error, "command structure"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            second["commands"][0] = self._command(
                "build/qualification/rebuild/O0"
            )
            second["commands"][0]["returncode"] = False
            with self.assertRaisesRegex(Core0Error, "return code"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_controlled_lake_environment_only_normalizes_the_bound_output(self):
        from build_actions import controlled_environment

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline, rebuilt = root / "build/first", root / "build/second"
            first, second = [], []
            for output, rows in ((baseline, first), (rebuilt, second)):
                row = self._command(".")
                row["argv"] = ["lake", "env", "lean", "Export.lean"]
                row["environment"] = controlled_environment(
                    {"lake": "/pin/bin/lake"}, {"LEMMA_CORE0_OUT": str(output)})
                rows.append(row)
            original = copy.deepcopy((first, second))
            result = qualifier._compare_provenance(
                {"commands": first}, {"commands": second}, baseline, rebuilt, root)
            self.assertTrue(result["command_structure_equal"])
            self.assertEqual((first, second), original)
            self.assertEqual(qualifier._normal_command(first[0], baseline, root)["environment"]["LEMMA_CORE0_OUT"], "$OUTPUT")
            for key, value, diagnostic in (
                ("PATH", "/other/bin", "command structure"),
                ("TZ", "local", "not controlled"),
                ("LEAN_PATH", "/foreign", "not controlled"),
                ("LEMMA_CORE0_OUT", str(root / "wrong"), "output differs"),
            ):
                with self.subTest(environment=key):
                    changed = copy.deepcopy(second)
                    changed[0]["environment"][key] = value
                    with self.assertRaisesRegex(Core0Error, diagnostic):
                        qualifier._compare_provenance(
                            {"commands": first}, {"commands": changed}, baseline, rebuilt, root)

    def action_fixture(self, root, *, reused=False):
        """Actual host subprocesses and admissions; no Lean/LLVM/target claim."""
        from build_actions import BuildActions

        for name in ("build_actions.py", "build_admission.py", "core0_common.py", "action_worker.py", "build_dependencies.py"):
            path = root / "scripts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / "scripts" / name).read_bytes())
        (root / "scripts/audit_kernel.py").write_text("host fixture observer\n")
        tools = {}
        for name in ("lean", "lake", "opt", "llc", "clang", "ld.lld", "llvm-objcopy"):
            path = root / "tools" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(
                f"#!{sys.executable}\n"
                "import pathlib,sys\n"
                "if '--version' in sys.argv:\n print('host fixture 1');sys.exit(0)\n"
                "args=sys.argv[1:]\n"
                "pathlib.Path(args[-1]).write_bytes(pathlib.Path(args[-3]).read_bytes()+b'fixture output')\n"
                "print('HOST_FIXTURE_ONLY: no target compilation')\n")
            path.chmod(0o755)
            tools[name] = str(path)
        records = []
        for index in range(2):
            output = root / "build" / ("first" if index == 0 else "second")
            output.mkdir(parents=True)
            (output / "program.ll").write_bytes(b"host input fixture\n")
            rows = []
            actions = BuildActions(root, output, tools, 10, rows, fresh=not (reused and index))
            actions.invoke(["opt", "-S", "-passes=verify", "program.ll", "-o", "program.opt.ll"], output)
            records.append((output, {"schema_version": 2, "commands": rows}))
        return records

    def test_fresh_actions_compare_validated_requests_and_retain_actual_producer_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (baseline, first), (rebuilt, second) = self.action_fixture(root)
            original = copy.deepcopy((first, second))
            compared = qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            self.assertTrue(compared["command_structure_equal"])
            observation = compared["intentional_command_observation_differences"][0]
            self.assertEqual(observation["route"], "lemma-build-actions/1")
            for label, directory, record in (("baseline", baseline, first), ("rebuilt", rebuilt, second)):
                receipt = json.loads((directory / record["commands"][0]["admission"]).read_text())
                saved = observation[label]
                self.assertEqual(receipt["status"], "fresh")
                self.assertEqual(saved["producer_receipt_id"], receipt["producer_receipt_id"])
                self.assertEqual(saved["original_producer_commands"], receipt["producer"]["executed"]["commands"])
                self.assertIn("HOST_FIXTURE_ONLY", saved["original_producer_commands"][0]["stdout"])
                self.assertNotIn("stdout", saved)
                self.assertNotIn("returncode", saved)
                self.assertNotIn("elapsed_seconds", saved)
            self.assertEqual((first, second), original)

    def test_independent_fresh_qualification_rejects_an_actual_warm_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (baseline, first), (rebuilt, second) = self.action_fixture(root, reused=True)
            receipt = json.loads((rebuilt / second["commands"][0]["admission"]).read_text())
            self.assertEqual(receipt["status"], "reused")
            with self.assertRaisesRegex(Core0Error, "fresh qualification rejects reused"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_warm_producer_cannot_be_relabelled_as_fresh_independent_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (baseline, first), (rebuilt, second) = self.action_fixture(root, reused=True)
            row = second["commands"][0]
            path = rebuilt / row["admission"]
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt["status"], "reused")
            producer = copy.deepcopy(receipt["producer"])
            receipt["status"] = "fresh"
            write_json(path, receipt)
            row["admission_sha256"] = sha256(path)
            self.assertEqual(json.loads(path.read_text())["producer"], producer)
            with self.assertRaisesRegex(Core0Error, "fresh qualification producer request differs"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_action_comparison_cannot_bypass_real_admission_or_accept_unknown_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (baseline, first), (rebuilt, second) = self.action_fixture(root)
            changed = copy.deepcopy(second)
            changed["commands"][0]["route"] = "unrecognized-action/1"
            with self.assertRaisesRegex(Core0Error, "action route differs"):
                qualifier._compare_provenance(first, changed, baseline, rebuilt, root)
            receipt = rebuilt / second["commands"][0]["admission"]
            original = receipt.read_bytes()
            receipt.write_bytes(b"corrupt receipt")
            with self.assertRaisesRegex(Core0Error, "receipt missing, corrupt"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)
            receipt.write_bytes(original)
            (rebuilt / "program.opt.ll").write_bytes(b"changed output")
            with self.assertRaisesRegex(Core0Error, "consumed/admitted file differs"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_fresh_comparison_binds_the_complete_validated_action_request(self):
        from action_cache import _digest, _json
        from build_actions import admitted_commands

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (baseline, first), (rebuilt, second) = self.action_fixture(root)
            row = second["commands"][0]
            path = rebuilt / row["admission"]
            receipt = json.loads(path.read_text())
            producer = receipt["producer"]
            producer["request"]["action"]["tools"]["opt"]["sha256"] = "a" * 64
            producer["action_key"] = _digest(_json(producer["request"]))
            receipt["action_key"] = producer["action_key"]
            receipt["producer_receipt_id"] = _digest(_json(producer))
            write_json(path, receipt)
            row["admission_sha256"] = sha256(path)
            self.assertEqual(admitted_commands([row], root=root, output_dir=rebuilt)[0]["admitted_route"], "fresh")
            with self.assertRaisesRegex(Core0Error, "command structure"):
                qualifier._compare_provenance(first, second, baseline, rebuilt, root)

    def test_copied_qualification_fixture_preserves_producers_and_rejects_the_consumed_ir(self):
        from build_actions import admitted_commands

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (source, record), _ = self.action_fixture(root)
            write_json(source / "provenance.json", record)
            original = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            destination = root / "build/qualification/failure-experiments/tampered-program-ir/artifact"
            self.assertTrue(qualifier._copy_qualification_audit_fixture(source, destination, root))
            copied = json.loads((destination / "provenance.json").read_text())
            row = copied["commands"][0]
            first = json.loads((source / record["commands"][0]["admission"]).read_text())
            second = json.loads((destination / row["admission"]).read_text())
            for field in ("producer", "producer_receipt_id", "action_key", "outputs", "materialized"):
                self.assertEqual(first[field], second[field])
            self.assertEqual(admitted_commands(copied["commands"], root=root, output_dir=destination)[0]["admitted_route"], "fresh")
            (destination / "program.ll").write_bytes(b"tampered consumed IR fixture")
            with self.assertRaises(Core0Error) as rejected:
                admitted_commands(copied["commands"], root=root, output_dir=destination)
            self.assertEqual(str(rejected.exception), "action consumed/admitted file differs: " + str(destination / "program.ll"))
            self.assertEqual(original, {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()})

    def test_gate9_stress_mode_must_be_exact_and_boolean(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            gate9.mkdir(parents=True)
            base = {key: None for key in qualifier.EXPECTED_GATE9_KEYS}
            base.update(
                schema_version=1,
                status="PASS",
                gate=9,
                profile=corpus.PROFILE,
                artifact_category=corpus.ARTIFACT_CATEGORY,
                test_abi=corpus.TEST_ABI,
            )
            for stress in ({"enabled": 1}, {"enabled": True}):
                with self.subTest(stress=stress):
                    base["stress"] = stress
                    write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, base)
                    with self.assertRaisesRegex(Core0Error, "stress"):
                        qualifier.validate_gate9_bundle(
                            root=root,
                            gate9_directory=gate9,
                            source={"commit": "a" * 40},
                        )
            base["schema_version"] = True
            base["stress"] = corpus.stress_manifest(stress=False)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, base)
            with self.assertRaisesRegex(Core0Error, "identity"):
                qualifier.validate_gate9_bundle(
                    root=root,
                    gate9_directory=gate9,
                    source={"commit": "a" * 40},
                )

    def test_probe_literal_counts_and_return_code_are_strict_integers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            source = root / "examples/foundation/MonitorPolicyProbes.lean"
            log = gate9 / "probes/monitor-policy-frontend.txt"
            source.parent.mkdir(parents=True)
            log.parent.mkdir(parents=True)
            source.write_text("#guard true\n" * 50, encoding="utf-8")
            log.write_text(
                "Monitor genuine v0.7 frontend/lowering passed: 54 scalar functions, "
                "88 Action functions, 7 timer/2 trap/4 UART operations\n"
                + qualifier.gate9_checker.POLICY_MARKER + "\n",
                encoding="utf-8",
            )
            probe = {
                "source": str(source.relative_to(root)),
                "source_sha256": sha256(source),
                "argv": ["lake", "env", "lean", str(source.relative_to(root))],
                "returncode": 0,
                "policy_probes": 50,
                "frontend_lowering": 1,
                "log": str(log.relative_to(root)),
                "log_sha256": sha256(log),
                "scope": "direct source predicates/encoding/frontend observations, not hardware or compiler proof",
            }
            for name, value in (
                ("returncode", False), ("frontend_lowering", True),
                ("policy_probes", True),
            ):
                with self.subTest(name=name):
                    changed = dict(probe)
                    changed[name] = value
                    with mock.patch.object(
                        qualifier.gate8_checker, "_load_rejections", return_value=()
                    ):
                        with self.assertRaisesRegex(Core0Error, "probe identity"):
                            qualifier._validate_probe_and_rejections(
                                {"source_probes": changed, "source_rejections": []},
                                root,
                                gate9,
                            )

    def test_probe_completion_marker_matches_current_closed_monitor_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            source = root / "examples/foundation/MonitorPolicyProbes.lean"
            log = gate9 / "probes/monitor-policy-frontend.txt"
            source.parent.mkdir(parents=True)
            log.parent.mkdir(parents=True)
            source.write_text("#guard true\n" * 50, encoding="utf-8")
            frontend = (
                "Monitor genuine v0.7 frontend/lowering passed: 54 scalar functions, "
                "88 Action functions, 7 timer/2 trap/4 UART operations"
            )
            marker = qualifier.gate9_checker.POLICY_MARKER
            good = frontend + "\n" + marker + "\n"
            probe = {
                "source": str(source.relative_to(root)),
                "source_sha256": sha256(source),
                "argv": ["lake", "env", "lean", str(source.relative_to(root))],
                "returncode": 0,
                "policy_probes": 50,
                "frontend_lowering": 1,
                "log": str(log.relative_to(root)),
                "scope": "direct source predicates/encoding/frontend observations, not hardware or compiler proof",
            }
            with mock.patch.object(
                qualifier.gate8_checker, "_load_rejections", return_value=()
            ):
                for output in (
                    good,
                    good.replace("88 Action", "85 Action"),
                    good.replace("54 scalar", "53 scalar"),
                    good.replace(frontend, ""),
                    good + frontend + "\n",
                    good.replace(marker, ""),
                    good + marker + "\n",
                    good + "sorryAx\n",
                ):
                    with self.subTest(output=output):
                        log.write_text(output, encoding="utf-8")
                        # Rehash each mutation so completion validation, rather
                        # than an incidental stale digest, must reject it.
                        probe["log_sha256"] = sha256(log)
                        report = {"source_probes": probe, "source_rejections": []}
                        if output == good:
                            actual = qualifier._validate_probe_and_rejections(
                                report, root, gate9
                            )
                            self.assertEqual(actual["probe_log_sha256"], sha256(log))
                        else:
                            with self.assertRaisesRegex(Core0Error, "completion marker"):
                                qualifier._validate_probe_and_rejections(report, root, gate9)

    def test_missing_retained_raw_file_is_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "build/image"
            run = root / "build/run"
            output.mkdir(parents=True)
            run.mkdir(parents=True)
            (output / "image.elf").write_bytes(b"image")
            write_json(output / "audit.json", {"audit": "bound"})
            scenario = corpus.SCENARIOS[0]
            (run / "sent.bin").write_bytes(b"")
            (run / "stderr.bin").write_bytes(b"")
            binding = {"audit_sha256": sha256(output / "audit.json")}
            machine = {"executable_ranges": [[0x80000000, 0x80010000]], "symbols": {}}
            record = {
                "schema_version": 1,
                "status": "PASS",
                "profile": corpus.PROFILE,
                "artifact_category": corpus.ARTIFACT_CATEGORY,
                "test_abi": corpus.TEST_ABI,
                "scenario": scenario.name,
                "image": str((output / "image.elf").resolve()),
                "image_sha256": sha256(output / "image.elf"),
                "binding": binding,
                "machine": machine,
                "pid": 100,
                "returncode": scenario.expected_exit,
                "expected_exit": scenario.expected_exit,
                "argv": list(runner.qemu_argv(output / "image.elf")),
                "timeout_seconds": 20,
                "elapsed_seconds": 1,
                "started_at": "2026-10-08T00:00:00+00:00",
                "finished_at": "2026-10-08T00:00:01+00:00",
                "ready_observed_before_input": True,
                "stdin_open_until_exit": True,
                "semantic_validation_after_exit": True,
                "single_pid": True,
                "single_elf": True,
                "first_input_after_ready": True,
                "outcome": "verified-monitor-session",
                "responses": [],
                "summary": {},
                "raw_artifacts": {
                    "sent.bin": sha256(run / "sent.bin"),
                    "received.bin": "0" * 64,
                    "stderr.bin": sha256(run / "stderr.bin"),
                },
            }
            write_json(run / runner.RESULT_FILE, record)
            with mock.patch.object(runner, "validate_transcript") as replay, \
                 mock.patch.object(runner, "validate_image_binding", return_value=binding), \
                 mock.patch.object(runner, "image_machine_info", return_value=machine):
                with self.assertRaisesRegex(Core0Error, "missing/stale"):
                    qualifier._revalidate_run(
                        root=root,
                        output=output,
                        run_directory=run,
                        scenario=scenario,
                        expected_record=record,
                    )
                replay.assert_not_called()

    def test_invalid_timeout_removes_stale_pass_before_any_source_or_build_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            work.mkdir(parents=True)
            write_json(work / qualifier.RESULT_FILE, {"status": "PASS"})
            with mock.patch.object(qualifier, "_source_identity") as source:
                with self.assertRaisesRegex(
                    qualifier.QualificationFailure, "harness-input-failure.*build"
                ):
                    qualifier.qualify_foundation(
                        root=root,
                        gate9_directory=gate9,
                        work=work,
                        clean=False,
                        timeout_seconds=float("nan"),
                        qemu_timeout=20,
                    )
                source.assert_not_called()
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            self.assertFalse((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_malformed_cli_removes_stale_pass_when_work_directory_is_known(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            work.mkdir(parents=True)
            write_json(work / qualifier.RESULT_FILE, {"status": "PASS"})
            argv = [
                "qualify_foundation.py", "--gate9-dir", "build/gate9",
                "--work-dir", "build/qualification", "--timeout", "not-a-number",
            ]
            with (
                mock.patch.object(qualifier, "repo_root", return_value=root),
                mock.patch.object(sys, "argv", argv),
                mock.patch("sys.stderr"),
            ):
                self.assertEqual(qualifier.main(), 2)
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            failure = json.loads((work / qualifier.FAILURE_FILE).read_text())
            self.assertEqual((failure["status"], failure["gate"]), ("FAIL", 10))

    def test_help_is_side_effect_free_even_when_work_directory_is_named(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            work.mkdir(parents=True)
            result = b'{"status":"PASS"}\n'
            failure = b'{"status":"OLD"}\n'
            (work / qualifier.RESULT_FILE).write_bytes(result)
            (work / qualifier.FAILURE_FILE).write_bytes(failure)
            argv = [
                "qualify_foundation.py", "--help", "--work-dir",
                "build/qualification",
            ]
            with (
                mock.patch.object(qualifier, "repo_root", return_value=root),
                mock.patch.object(sys, "argv", argv),
                mock.patch("sys.stdout"),
            ):
                self.assertEqual(qualifier.main(), 0)
            self.assertEqual((work / qualifier.RESULT_FILE).read_bytes(), result)
            self.assertEqual((work / qualifier.FAILURE_FILE).read_bytes(), failure)

    def test_success_is_published_only_after_final_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, {"status": "PASS"})
            for optimization in qualifier.PROFILES:
                directory = gate9 / optimization
                directory.mkdir()
                for name in ("build.json", "audit.json", "provenance.json"):
                    write_json(directory / name, {"name": name})
                (directory / "image.elf").write_bytes(optimization.encode())
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            gate9_result = {
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            stale = [
                {"id": "phase9-stale-pass", "passed": True},
                {"id": "runner-stale-pass", "passed": True},
            ]
            failures = [
                {"id": "missing-program-object", "passed": True},
                {"id": "tampered-program-ir", "passed": True},
                {"id": "missing-raw-evidence", "passed": True},
            ]
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=gate9_result
                ),
                mock.patch.object(
                    qualifier,
                    "rebuild_and_compare",
                    return_value=({"O0": {}, "O2": {}}, []),
                ),
                mock.patch.object(
                    qualifier, "stale_pass_experiments", return_value=(stale, [])
                ),
                mock.patch.object(
                    qualifier,
                    "artifact_failure_experiments",
                    return_value=(failures, []),
                ),
                mock.patch.object(
                    qualifier, "_qualification_artifact_catalog", return_value=[]
                ),
                mock.patch.object(qualifier, "validate_qualification_report") as validate,
            ):
                report = qualifier.qualify_foundation(
                    root=root,
                    gate9_directory=gate9,
                    work=work,
                    clean=True,
                    timeout_seconds=1,
                    qemu_timeout=1,
                )
            validate.assert_called_once()
            self.assertEqual(report, json.loads((work / qualifier.RESULT_FILE).read_text()))
            self.assertFalse((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_validation_failure_never_publishes_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            gate9 = root / "build/gate9"
            work = root / "build/qualification"
            gate9.mkdir(parents=True)
            write_json(gate9 / qualifier.gate9_checker.RESULT_FILE, {"status": "PASS"})
            for optimization in qualifier.PROFILES:
                directory = gate9 / optimization
                directory.mkdir()
                for name in ("build.json", "audit.json", "provenance.json"):
                    write_json(directory / name, {"name": name})
                (directory / "image.elf").write_bytes(optimization.encode())
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            gate9_result = {
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=gate9_result
                ),
                mock.patch.object(
                    qualifier,
                    "rebuild_and_compare",
                    return_value=({"O0": {}, "O2": {}}, []),
                ),
                mock.patch.object(
                    qualifier,
                    "stale_pass_experiments",
                    return_value=([{"id": "phase9-stale-pass"}, {"id": "runner-stale-pass"}], []),
                ),
                mock.patch.object(
                    qualifier,
                    "artifact_failure_experiments",
                    return_value=([{"id": "missing-program-object"}], []),
                ),
                mock.patch.object(
                    qualifier, "_qualification_artifact_catalog", return_value=[]
                ),
                mock.patch.object(
                    qualifier,
                    "validate_qualification_report",
                    side_effect=Core0Error("final evidence changed"),
                ),
            ):
                with self.assertRaisesRegex(Core0Error, "final evidence changed"):
                    qualifier.qualify_foundation(
                        root=root,
                        gate9_directory=gate9,
                        work=work,
                        clean=True,
                        timeout_seconds=1,
                        qemu_timeout=1,
                    )
            self.assertFalse((work / qualifier.RESULT_FILE).exists())
            self.assertTrue((work / (qualifier.RESULT_FILE + ".tmp")).exists())

    def test_final_validator_rejects_missing_mandatory_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "build/qualification"
            gate9 = root / "build/gate9"
            work.mkdir(parents=True)
            gate9.mkdir(parents=True)
            reproducibility = {}
            for optimization in qualifier.PROFILES:
                baseline = gate9 / optimization
                rebuilt = work / "rebuild" / optimization
                baseline.mkdir(parents=True)
                rebuilt.mkdir(parents=True)
                comparisons = {}
                for name in qualifier.DETERMINISTIC_ARTIFACTS:
                    first, second = baseline / name, rebuilt / name
                    first.write_bytes(name.encode())
                    second.write_bytes(name.encode())
                    comparisons[name] = {
                        "baseline_sha256": sha256(first),
                        "rebuilt_sha256": sha256(second),
                        "bytes": first.stat().st_size,
                        "identical": True,
                    }
                reproducibility[optimization] = {
                    "rebuilt_directory": str(rebuilt.relative_to(root)),
                    "binding": {},
                    "deterministic_artifacts": comparisons,
                    "image_map_inspected_and_identical": True,
                    "metadata": {},
                }
            source = {
                "commit": "a" * 40,
                "tree": "b" * 40,
                "clean": True,
                "dirty_paths": [],
            }
            report = {
                "schema_version": 1,
                "status": "PASS",
                "task": "002-machine-foundation",
                "gate": 10,
                "started_at": "start",
                "finished_at": "finish",
                "source": source,
                "invocation": {
                    "gate9_directory": "build/gate9",
                    "work_directory": "build/qualification",
                    "clean": True,
                    "timeout_seconds": 1,
                    "qemu_timeout": 1,
                    "stress_selected_by_gate9_report": False,
                },
                "gate9_input": {"bound": True},
                "reproducibility": reproducibility,
                "failure_experiments": [
                    {
                        "id": "phase9-stale-pass", "passed": True,
                        "old_pass_sha256": "0" * 64, "canonical_pass_absent": True,
                        "observed_category": "harness-input-failure",
                        "failure_report": {}, "retained_old_report": {}, "command": {},
                    },
                    {
                        "id": "runner-stale-pass", "passed": True,
                        "old_pass_sha256": "0" * 64, "new_failure_sha256": "1" * 64,
                        "observed_category": "image-or-harness-rejection",
                        "failure_report": {}, "retained_old_report": {},
                        "raw_artifacts": {}, "command": {},
                    },
                    {
                        "id": "missing-program-object", "passed": True,
                        "accepted_image_modified": False, "target": "program.o",
                        "mode": "missing", "original_sha256": "0" * 64,
                        "changed_sha256": None, "canonical_audit_absent": True,
                        "command": {}, "record": {},
                    },
                    {
                        "id": "tampered-program-ir", "passed": True,
                        "accepted_image_modified": False, "target": "program.ll",
                        "mode": "tamper", "original_sha256": "0" * 64,
                        "changed_sha256": "1" * 64, "canonical_audit_absent": True,
                        "command": {}, "record": {},
                    },
                    {
                        "id": "missing-raw-evidence", "passed": True,
                        "removed": "received.bin", "removed_sha256": "0" * 64,
                        "canonical_pass_absent": True, "diagnostic": "missing",
                        "record": {}, "retained_old_report": {},
                    },
                ],
                "artifacts": [
                    {
                        "path": f"build/qualification/missing-{index}.bin",
                        "bytes": 1,
                        "sha256": "0" * 64,
                        "role": f"missing evidence {index}",
                    }
                    for index in range(66)
                ],
                "counts": {
                    "replayed_gate9_sessions": 18,
                    "normal_sessions": 18,
                    "stress_sessions": 0,
                    "reproducible_profiles": 2,
                    "deterministic_artifacts_per_profile": 16,
                    "failure_path_experiments": 5,
                },
                "limitations": [],
            }
            fresh = {
                "bound": True,
                "stress": {"enabled": False},
                "counts": {"fresh_qemu_boots": 18},
                "normal_counts": {"fresh_qemu_boots": 18},
                "stress_counts": {"fresh_qemu_boots": 0},
            }
            report["gate9_input"] = fresh
            with (
                mock.patch.object(qualifier, "_source_identity", return_value=source),
                mock.patch.object(
                    qualifier, "validate_gate9_bundle", return_value=fresh
                ),
                mock.patch.object(
                    runner, "validate_image_binding", return_value={}
                ),
                mock.patch.object(
                    qualifier, "_reproducibility_metadata", return_value={}
                ),
            ):
                with self.assertRaisesRegex(Core0Error, "missing/stale"):
                    qualifier.validate_qualification_report(
                        report, root=root, work=work
                    )

    def test_audit_experiments_use_the_closed_monitor_policy(self):
        source = (ROOT / "scripts/qualify_foundation.py").read_text(encoding="utf-8")
        self.assertIn(
            '"--policy", audit_core0.TEST_MONITOR_IMAGE_POLICY', source
        )
        self.assertEqual(
            audit_core0.TEST_MONITOR_IMAGE_POLICY, corpus.ARTIFACT_CATEGORY
        )


if __name__ == "__main__":
    unittest.main()
