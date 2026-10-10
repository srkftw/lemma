#!/usr/bin/env python3
"""Focused adversarial tests for the live Gate 6 UART session runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import core0_common  # noqa: E402
import gate6_corpus  # noqa: E402
import run_device_session  # noqa: E402


def _identity() -> dict[str, str]:
    return {
        "suite_id": f"{gate6_corpus.DEFAULT_SUITE_ID:016x}",
        "source_seed": f"{gate6_corpus.DEFAULT_SOURCE_SEED:016x}",
        "runtime_seed": f"{gate6_corpus.DEFAULT_RUNTIME_SEED:016x}",
    }


def _success_child(scenario: gate6_corpus.Scenario) -> str:
    statements = [
        "import sys",
        f"out=sys.stdout.buffer; inp=sys.stdin.buffer; out.write(bytes.fromhex('{gate6_corpus.READY.hex()}')); out.flush()",
    ]
    for exchange in scenario.exchanges:
        request = exchange.request.encode()
        response = exchange.expected_prefix + gate6_corpus.encode_response(
            exchange.expected_response
        )
        statements.extend(
            [
                f"data=inp.read({len(request)})",
                f"assert data==bytes.fromhex('{request.hex()}')",
                f"out.write(bytes.fromhex('{response.hex()}')); out.flush()",
            ]
        )
    statements.append(f"sys.exit({scenario.expected_exit_status})")
    return ";".join(statements)


def _terminal_child(scenario: gate6_corpus.Scenario) -> str:
    statements = [
        "import sys",
        f"out=sys.stdout.buffer; inp=sys.stdin.buffer; out.write(bytes.fromhex('{gate6_corpus.READY.hex()}')); out.flush()",
    ]
    if scenario.raw_input:
        statements.extend(
            [
                f"data=inp.read({len(scenario.raw_input)})",
                f"assert data==bytes.fromhex('{scenario.raw_input.hex()}')",
            ]
        )
    statements.append(f"sys.exit({scenario.expected_exit_status})")
    return ";".join(statements)


class DeviceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.output = self.root / "runs"
        self.image = self.artifacts / "image.elf"
        self.image.write_bytes(b"bound-device-elf")
        identity = _identity()
        manifest = {
            "artifact_category": "test-device-suite",
            "contract_version": gate6_corpus.PROFILE,
            "test_abi": gate6_corpus.TEST_ABI,
            **identity,
            "roots": [
                {
                    "source": run_device_session.ROOT,
                    "signature": {"args": []},
                }
            ],
            "action_functions": [
                {
                    "source": run_device_session.ROOT,
                    "transitive_effects": sorted(run_device_session.ROOT_EFFECTS),
                }
            ],
            "used_device_ops": [
                {"stable_id": operation}
                for operation in sorted(run_device_session.DEVICE_OPS)
            ],
        }
        abi = {
            "contract_version": gate6_corpus.PROFILE,
            "name": gate6_corpus.TEST_ABI,
            "ready": gate6_corpus.READY.decode("ascii"),
            "requests_per_session": 2,
            "poll_budget": 1_000_000,
            "statuses": [
                {"code": 0, "name": "ok"},
                {"code": 10, "name": "poll-again-internal", "public": False},
            ],
            **identity,
        }
        contract = {
            "contract_version": gate6_corpus.PROFILE,
            "machine": "qemu-virt-rv64-single-hart",
            "interrupt_use": "none; Gate 6 is polling-only",
            "general_ram_api_access": False,
        }
        layout = {
            "uart_16550": {
                "base": "0x0000000010000000",
                "size": "0x0000000000000100",
            },
            "sifive_test": {"base": "0x0000000000100000"},
        }
        documents = {
            "device-suite-manifest.json": manifest,
            "device-test-abi.json": abi,
            "device-contract.json": contract,
            "layout.json": layout,
            "provenance.json": {"artifact_category": "test-device-suite"},
        }
        for name, document in documents.items():
            (self.artifacts / name).write_text(json.dumps(document), encoding="utf-8")
        hashes = {
            name: core0_common.sha256(self.artifacts / name)
            for name in (
                "image.elf",
                "device-suite-manifest.json",
                "device-test-abi.json",
                "device-contract.json",
            )
        }
        (self.artifacts / "build.json").write_text(
            json.dumps(
                {
                    "artifact_category": "test-device-suite",
                    "status": "pass",
                    "artifacts": hashes,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_child(
        self,
        scenario: gate6_corpus.Scenario,
        code: str,
        *,
        timeout: float = 2.0,
    ) -> dict[str, object]:
        argv = (sys.executable, "-u", "-c", code)
        with mock.patch.object(
            run_device_session, "require_tools", return_value={}
        ), mock.patch.object(run_device_session, "_qemu_argv", return_value=argv):
            return run_device_session.run_session(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                scenario=scenario,
                timeout_seconds=timeout,
            )

    def test_two_live_exchanges_use_one_pid_and_bound_elf(self) -> None:
        scenario = gate6_corpus.ARITHMETIC
        record = self.run_child(scenario, _success_child(scenario))
        self.assertEqual(record["status"], "pass")
        self.assertTrue(record["single_pid"])
        self.assertTrue(record["single_elf"])
        self.assertEqual(len(record["exchanges"]), 2)
        started_at = datetime.fromisoformat(record["started_at"])
        finished_at = datetime.fromisoformat(record["finished_at"])
        self.assertEqual(started_at.utcoffset(), timezone.utc.utcoffset(started_at))
        self.assertEqual(finished_at.utcoffset(), timezone.utc.utcoffset(finished_at))
        self.assertLessEqual(started_at, finished_at)
        self.assertEqual(
            {exchange["pid"] for exchange in record["exchanges"]},
            {record["qemu_pid"]},
        )
        self.assertEqual(
            {exchange["image_sha256"] for exchange in record["exchanges"]},
            {core0_common.sha256(self.image)},
        )
        sent = (self.output / f"sent-{scenario.name}.bin").read_bytes()
        received = (self.output / f"received-{scenario.name}.bin").read_bytes()
        self.assertEqual(sent, b"".join(item.request.encode() for item in scenario.exchanges))
        self.assertEqual(
            received,
            gate6_corpus.READY
            + b"".join(
                item.expected_prefix + gate6_corpus.encode_response(item.expected_response)
                for item in scenario.exchanges
            ),
        )

    def test_branch_prefix_and_terminal_raw_or_no_input_are_supported(self) -> None:
        branch = gate6_corpus.BRANCH_EFFECTS
        branch_record = self.run_child(branch, _success_child(branch))
        self.assertEqual(branch_record["exchanges"][0]["prefix_hex"], "")
        self.assertEqual(
            branch_record["exchanges"][0]["response"],
            {
                "status": gate6_corpus.STATUS_OK,
                "request_id": 0x2001,
                "value": 0x5A00,
            },
        )
        self.assertEqual(branch_record["exchanges"][1]["prefix_hex"], "a5")
        self.assertEqual(
            branch_record["exchanges"][1]["response"],
            {
                "status": gate6_corpus.STATUS_OK,
                "request_id": 0x2002,
                "value": 0x3C01,
            },
        )

        for scenario in (gate6_corpus.RX_TIMEOUT, gate6_corpus.MALFORMED_MAGIC):
            with self.subTest(scenario=scenario.name):
                record = self.run_child(scenario, _terminal_child(scenario))
                self.assertEqual(record["qemu_returncode"], scenario.expected_exit_status)
                self.assertEqual(record["exchanges"], [])

    def test_exit_after_stale_readiness_snapshot_drains_actual_stdout(self) -> None:
        partial = b"LMS6\x01"
        for label, response, exit_status, diagnostic in (
            ("partial-success-exit", partial, 0, "truncated.*received 5 of 24 bytes"),
            ("partial-failure-exit", partial, 5, "exited with 5"),
            ("complete-success-exit", bytes(range(24)), 0, None),
        ):
            with self.subTest(label=label):
                code = (
                    "import sys;"
                    f"sys.stdout.buffer.write(bytes.fromhex('{response.hex()}'));"
                    "sys.stdout.buffer.flush();"
                    f"sys.exit({exit_status})"
                )
                process = subprocess.Popen(
                    (sys.executable, "-u", "-c", code),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    self.assertEqual(process.wait(timeout=2), exit_status)
                    self.assertIsNotNone(process.stdout)
                    self.assertIsNotNone(process.stderr)
                    stdout_fd = process.stdout.fileno()
                    stderr_fd = process.stderr.fileno()
                    os.set_blocking(stdout_fd, False)
                    os.set_blocking(stderr_fd, False)
                    capture = run_device_session._Capture()
                    real_select = run_device_session.select.select
                    select_calls = 0

                    def stale_first_snapshot(readers, writers, exceptional, timeout):
                        nonlocal select_calls
                        select_calls += 1
                        if select_calls == 1:
                            self.assertEqual(set(readers), {stdout_fd, stderr_fd})
                            # Model the snapshot just before stdout becomes ready.
                            # The child, exit status and buffered output are real.
                            return [stderr_fd], [], []
                        return real_select(readers, writers, exceptional, timeout)

                    with mock.patch.object(
                        run_device_session.select, "select", side_effect=stale_first_snapshot
                    ):
                        if diagnostic is None:
                            self.assertEqual(
                                run_device_session._read_exact(
                                    process, 24, deadline=time.monotonic() + 2,
                                    capture=capture, context="reading exchange 0 response",
                                ),
                                response,
                            )
                        else:
                            with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                                run_device_session._read_exact(
                                    process, 24, deadline=time.monotonic() + 2,
                                    capture=capture, context="reading exchange 0 response",
                                )
                    self.assertGreaterEqual(select_calls, 2)
                    self.assertEqual(bytes(capture.received), response)
                    self.assertEqual(bytes(capture.stderr), b"")
                    if exit_status:
                        self.assertEqual(capture.returncode, exit_status)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(process.pid, 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=2)
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.stderr is not None:
                        process.stderr.close()

    def test_truncated_and_malformed_response_fail_closed(self) -> None:
        scenario = gate6_corpus.ARITHMETIC
        request = scenario.exchanges[0].request.encode()
        for label, response, diagnostic in (
            ("truncated", b"LMS6\x01", "truncated"),
            ("bad-magic", b"BAD!" + gate6_corpus.encode_response(
                scenario.exchanges[0].expected_response
            )[4:], "magic"),
            ("internal-status", (
                b"LMS6" + bytes((1, 10, 8, 0))
                + scenario.exchanges[0].request.request_id.to_bytes(8, "little")
                + bytes(8)
            ), "internal poll status"),
        ):
            with self.subTest(label=label):
                code = ";".join(
                    (
                        "import sys",
                        f"out=sys.stdout.buffer; inp=sys.stdin.buffer; out.write(bytes.fromhex('{gate6_corpus.READY.hex()}')); out.flush()",
                        f"inp.read({len(request)})",
                        f"out.write(bytes.fromhex('{response.hex()}')); out.flush()",
                    )
                )
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    self.run_child(scenario, code)
                failure = json.loads(
                    (self.output / f"run-{scenario.name}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(failure["status"], "fail")

    def test_timeout_kills_process_group_and_reaps_child(self) -> None:
        scenario = gate6_corpus.ARITHMETIC
        code = ";".join(
            (
                "import sys,time",
                f"sys.stdout.buffer.write(bytes.fromhex('{gate6_corpus.READY.hex()}'));sys.stdout.buffer.flush()",
                "sys.stdin.buffer.read(32)",
                "time.sleep(10)",
            )
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "timed out"):
            self.run_child(scenario, code, timeout=0.2)
        failure = json.loads(
            (self.output / f"run-{scenario.name}.json").read_text(encoding="utf-8")
        )
        pid = failure["qemu_pid"]
        self.assertIsInstance(pid, int)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_suppressed_output_accepts_only_a_proper_stress_response_prefix(self) -> None:
        scenario = gate6_corpus.TX_BACKPRESSURE
        code = ";".join(
            (
                "import sys",
                f"out=sys.stdout.buffer; inp=sys.stdin.buffer; out.write(bytes.fromhex('{gate6_corpus.READY.hex()}')); out.flush()",
                f"assert inp.read({len(scenario.raw_input)})==bytes.fromhex('{scenario.raw_input.hex()}')",
                "out.write(b'\\x55'*65535+b'L');out.flush()",
                f"sys.exit({gate6_corpus.STATUS_TX_TIMEOUT})",
            )
        )
        record = self.run_child(scenario, code)
        self.assertEqual(record["qemu_returncode"], gate6_corpus.STATUS_TX_TIMEOUT)
        received = (self.output / f"received-{scenario.name}.bin").read_bytes()
        self.assertEqual(received, gate6_corpus.READY + b"\x55" * 65535 + b"L")

    def test_process_failure_is_not_a_protocol_mismatch(self) -> None:
        scenario = gate6_corpus.ARITHMETIC
        code = ";".join(
            (
                "import sys",
                f"sys.stdout.buffer.write(bytes.fromhex('{gate6_corpus.READY.hex()}'));sys.stdout.buffer.flush()",
                "sys.exit(5)",
            )
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "exited with 5"):
            self.run_child(scenario, code)

    def test_failed_rerun_replaces_stale_pass_record_and_retains_raw_files(self) -> None:
        scenario = gate6_corpus.ARITHMETIC
        self.output.mkdir()
        record_path = self.output / f"run-{scenario.name}.json"
        record_path.write_text('{"status":"pass","stale":true}\n', encoding="utf-8")
        code = ";".join(
            (
                "import sys",
                "sys.stdout.buffer.write(b'WRONG');sys.stdout.buffer.flush()",
                "sys.exit(0)",
            )
        )
        with self.assertRaises(core0_common.Core0Error):
            self.run_child(scenario, code)
        failure = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(failure["status"], "fail")
        self.assertNotIn("stale", failure)
        self.assertLessEqual(
            datetime.fromisoformat(failure["started_at"]),
            datetime.fromisoformat(failure["finished_at"]),
        )
        self.assertTrue((self.output / f"sent-{scenario.name}.bin").is_file())
        self.assertTrue((self.output / f"received-{scenario.name}.bin").is_file())
        self.assertTrue((self.output / f"qemu-{scenario.name}.stderr").is_file())

    def test_tampered_bound_artifact_hash_is_rejected_before_spawn(self) -> None:
        (self.artifacts / "device-contract.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(run_device_session.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(core0_common.Core0Error, "device contract"):
                run_device_session.run_session(
                    root=self.root,
                    image=self.image,
                    output_dir=self.output,
                    scenario=gate6_corpus.ARITHMETIC,
                    timeout_seconds=1.0,
                )
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
