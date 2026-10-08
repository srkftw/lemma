#!/usr/bin/env python3
"""Run one genuinely interactive Gate 6 compiled-UART session.

The guest is started before any request bytes are written.  This runner waits
for the exact READY frame, sends each request through the live QEMU process,
and validates the corresponding byte prefix and fixed response before sending
the next request.  Terminal cases retain stdin without closing it so a guest
timeout is a device-polling result, not host EOF behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Sequence

import gate6_corpus
from core0_common import Core0Error, load_json, repo_root, require_tools, sha256, write_json


ARTIFACT_CATEGORY = "test-device-suite"
PROFILE = gate6_corpus.PROFILE
TEST_ABI = gate6_corpus.TEST_ABI
ROOT = "Lemma.Examples.Foundation.Device.deviceSession"
DEVICE_OPS = {
    "uart.read-status",
    "uart.read-byte",
    "uart.write-byte",
    "uart.enable-reset-fifo",
}
ROOT_EFFECTS = {
    "checked-access",
    "fixed-ram-read",
    "fixed-ram-write",
    "mmio-read",
    "mmio-write",
    "io-order",
}


@dataclass
class _Capture:
    sent: bytearray = field(default_factory=bytearray)
    received: bytearray = field(default_factory=bytearray)
    stderr: bytearray = field(default_factory=bytearray)
    pid: int | None = None
    returncode: int | None = None
    argv: tuple[str, ...] = ()
    responses: list[dict[str, object]] = field(default_factory=list)


def _hex_identity(value: int) -> str:
    return f"{value:016x}"


def _as_dict(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} is not a JSON object")
    return value


def validate_image_binding(image: Path) -> dict[str, object]:
    """Bind the runner to the exact built device suite and its hash closure."""

    directory = image.parent
    names = (
        "image.elf",
        "device-suite-manifest.json",
        "device-test-abi.json",
        "device-contract.json",
        "layout.json",
        "provenance.json",
        "build.json",
    )
    paths = {name: directory / name for name in names}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise Core0Error("device image binding is missing: " + ", ".join(missing))
    if image.resolve() != paths["image.elf"].resolve():
        raise Core0Error("device runner image is not the bound image.elf artifact")

    manifest = _as_dict(load_json(paths["device-suite-manifest.json"]), "device manifest")
    abi = _as_dict(load_json(paths["device-test-abi.json"]), "device ABI")
    contract = _as_dict(load_json(paths["device-contract.json"]), "device contract")
    layout = _as_dict(load_json(paths["layout.json"]), "machine layout")
    provenance = _as_dict(load_json(paths["provenance.json"]), "device provenance")
    build = _as_dict(load_json(paths["build.json"]), "device build record")

    if (
        manifest.get("artifact_category") != ARTIFACT_CATEGORY
        or manifest.get("contract_version") != PROFILE
        or manifest.get("test_abi") != TEST_ABI
    ):
        raise Core0Error("device manifest has the wrong category/profile/ABI")
    expected_identity = {
        "suite_id": _hex_identity(gate6_corpus.DEFAULT_SUITE_ID),
        "source_seed": _hex_identity(gate6_corpus.DEFAULT_SOURCE_SEED),
        "runtime_seed": _hex_identity(gate6_corpus.DEFAULT_RUNTIME_SEED),
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected or abi.get(key) != expected:
            raise Core0Error(f"device image {key} differs from the closed corpus")

    roots = manifest.get("roots")
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], dict):
        raise Core0Error("device manifest must contain exactly one root")
    if roots[0].get("source") != ROOT or roots[0].get("signature") != {"args": []}:
        raise Core0Error("device manifest root identity/signature differs")
    action_functions = manifest.get("action_functions")
    if not isinstance(action_functions, list):
        raise Core0Error("device manifest lacks its Action closure")
    root_entries = [
        item for item in action_functions
        if isinstance(item, dict) and item.get("source") == ROOT
    ]
    if len(root_entries) != 1 or set(root_entries[0].get("transitive_effects", ())) != ROOT_EFFECTS:
        raise Core0Error("device root transitive effects differ from the closed contract")
    operations = manifest.get("used_device_ops")
    if not isinstance(operations, list) or {
        item.get("stable_id") for item in operations if isinstance(item, dict)
    } != DEVICE_OPS:
        raise Core0Error("device manifest does not contain the exact UART operation catalog")

    statuses = abi.get("statuses")
    internal = [
        item for item in statuses if isinstance(item, dict) and item.get("code") == 10
    ] if isinstance(statuses, list) else []
    if (
        abi.get("contract_version") != PROFILE
        or abi.get("name") != TEST_ABI
        or abi.get("ready") != gate6_corpus.READY.decode("ascii")
        or abi.get("requests_per_session") != gate6_corpus.REQUESTS_PER_SESSION
        or abi.get("poll_budget") != 1_000_000
        or len(internal) != 1
        or internal[0].get("public") is not False
    ):
        raise Core0Error("device test ABI differs from the exact interactive contract")
    if (
        contract.get("contract_version") != PROFILE
        or contract.get("machine") != "qemu-virt-rv64-single-hart"
        or contract.get("interrupt_use") != "none; Gate 6 is polling-only"
        or contract.get("general_ram_api_access") is not False
    ):
        raise Core0Error("device contract differs from the pinned polling-only machine")
    uart = layout.get("uart_16550")
    finisher = layout.get("sifive_test")
    if (
        not isinstance(uart, dict)
        or uart.get("base") != "0x0000000010000000"
        or uart.get("size") != "0x0000000000000100"
        or not isinstance(finisher, dict)
        or finisher.get("base") != "0x0000000000100000"
    ):
        raise Core0Error("device image layout differs from the pinned UART/finisher map")
    if (
        provenance.get("artifact_category") != ARTIFACT_CATEGORY
        or build.get("artifact_category") != ARTIFACT_CATEGORY
        or build.get("status") != "pass"
    ):
        raise Core0Error("device image provenance/build category or status differs")
    artifacts = build.get("artifacts")
    if not isinstance(artifacts, dict):
        raise Core0Error("device build record lacks artifact hashes")
    for name in (
        "image.elf",
        "device-suite-manifest.json",
        "device-test-abi.json",
        "device-contract.json",
    ):
        if artifacts.get(name) != sha256(paths[name]):
            raise Core0Error(f"device build hash differs for {name}")
    return {
        "manifest": manifest,
        "abi": abi,
        "contract": contract,
        "layout": layout,
    }


def validate_scenario(scenario: gate6_corpus.Scenario) -> None:
    if not isinstance(scenario, gate6_corpus.Scenario):
        raise Core0Error("device scenario has the wrong type")
    if not scenario.name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in scenario.name):
        raise Core0Error("device scenario name is not a safe artifact stem")
    if scenario.exchanges:
        if (
            len(scenario.exchanges) != gate6_corpus.REQUESTS_PER_SESSION
            or scenario.raw_input
            or scenario.withhold_after_ready
            or scenario.suppress_output_after_ready
            or scenario.expected_exit_status != gate6_corpus.STATUS_OK
        ):
            raise Core0Error("normal device scenario does not describe one exact two-request session")
        for exchange in scenario.exchanges:
            expected = gate6_corpus.expected_exchange(exchange.request)
            if exchange != expected:
                raise Core0Error("device scenario exchange differs from the independent oracle")
    else:
        if scenario.expected_exit_status not in gate6_corpus.STATUS_NAMES:
            raise Core0Error("terminal device scenario has an unknown exit status")
        if scenario.expected_exit_status in (
            gate6_corpus.STATUS_OK,
            gate6_corpus.STATUS_POLL_AGAIN_INTERNAL,
        ):
            raise Core0Error("terminal device scenario has a nonterminal/internal exit status")
        if scenario.suppress_output_after_ready and scenario.expected_exit_status != gate6_corpus.STATUS_TX_TIMEOUT:
            raise Core0Error("suppressed-output scenario must expect the transmit timeout")
        if scenario.suppress_output_after_ready and scenario != gate6_corpus.TX_BACKPRESSURE:
            raise Core0Error("suppressed-output scenario differs from the closed backpressure fixture")


def _qemu_argv(image: Path) -> tuple[str, ...]:
    return (
        "qemu-system-riscv64",
        "-machine", "virt,acpi=off",
        "-accel", "tcg",
        "-cpu", "rv64",
        "-smp", "1",
        "-m", "128M",
        "-bios", "none",
        "-kernel", str(image),
        "-nodefaults",
        "-nic", "none",
        "-display", "none",
        "-serial", "stdio",
        "-monitor", "none",
        "-no-reboot",
        "-seed", "1",
    )


def _remaining(deadline: float, context: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Core0Error(f"device session timed out while {context}")
    return remaining


def _read_stderr(fd: int, capture: _Capture) -> bool:
    try:
        chunk = os.read(fd, 65536)
    except BlockingIOError:
        return True
    if chunk:
        capture.stderr.extend(chunk)
        return True
    return False


def _read_exact(
    process: subprocess.Popen[bytes],
    count: int,
    *,
    deadline: float,
    capture: _Capture,
    context: str,
) -> bytes:
    if process.stdout is None or process.stderr is None:
        raise Core0Error("device process does not expose stdout/stderr pipes")
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    result = bytearray()
    stderr_open = True
    while len(result) < count:
        timeout = min(_remaining(deadline, context), 0.1)
        readers = [stdout_fd] + ([stderr_fd] if stderr_open else [])
        ready, _, _ = select.select(readers, [], [], timeout)
        if stderr_fd in ready:
            stderr_open = _read_stderr(stderr_fd, capture)
        if stdout_fd in ready:
            chunk = os.read(stdout_fd, count - len(result))
            if not chunk:
                returncode = process.poll()
                if returncode is None:
                    try:
                        returncode = process.wait(timeout=min(_remaining(deadline, context), 0.1))
                    except subprocess.TimeoutExpired:
                        returncode = None
                if returncode not in (None, 0):
                    capture.returncode = int(returncode)
                    raise Core0Error(
                        f"device process failure: exited with {returncode} before {context}"
                    )
                raise Core0Error(
                    f"device process ended with a truncated {context}: "
                    f"received {len(result)} of {count} bytes"
                )
            result.extend(chunk)
            capture.received.extend(chunk)
        elif process.poll() is not None:
            raise Core0Error(
                f"device process exited with {process.returncode} before {context}"
            )
    return bytes(result)


def _write_all(
    process: subprocess.Popen[bytes],
    payload: bytes,
    *,
    deadline: float,
    capture: _Capture,
    context: str,
) -> None:
    if process.stdin is None:
        raise Core0Error("device process does not expose an stdin pipe")
    fd = process.stdin.fileno()
    offset = 0
    while offset < len(payload):
        timeout = min(_remaining(deadline, context), 0.1)
        _, ready, _ = select.select([], [fd], [], timeout)
        if fd not in ready:
            if process.poll() is not None:
                raise Core0Error(
                    f"device process exited with {process.returncode} while {context}"
                )
            continue
        try:
            written = os.write(fd, payload[offset:])
        except BrokenPipeError as error:
            raise Core0Error(f"device stdin closed while {context}") from error
        if written <= 0:
            raise Core0Error(f"device stdin made no progress while {context}")
        capture.sent.extend(payload[offset : offset + written])
        offset += written


def _drain_after_exit(stream: BinaryIO | None, target: bytearray) -> None:
    if stream is None:
        return
    fd = stream.fileno()
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return
        if not chunk:
            return
        target.extend(chunk)


def _wait_and_collect(
    process: subprocess.Popen[bytes],
    *,
    deadline: float,
    capture: _Capture,
    read_stdout: bool,
) -> int:
    if process.stdout is None or process.stderr is None:
        raise Core0Error("device process does not expose output pipes")
    stdout_fd = process.stdout.fileno()
    stderr_fd = process.stderr.fileno()
    while process.poll() is None:
        timeout = min(_remaining(deadline, "waiting for status-coded QEMU exit"), 0.05)
        readers = ([stdout_fd] if read_stdout else []) + [stderr_fd]
        ready, _, _ = select.select(readers, [], [], timeout)
        if read_stdout and stdout_fd in ready:
            try:
                chunk = os.read(stdout_fd, 65536)
            except BlockingIOError:
                chunk = b""
            if chunk:
                capture.received.extend(chunk)
        if stderr_fd in ready:
            _read_stderr(stderr_fd, capture)
    process.wait()
    _drain_after_exit(process.stdout, capture.received)
    _drain_after_exit(process.stderr, capture.stderr)
    return int(process.returncode)


def _kill_and_reap(process: subprocess.Popen[bytes], capture: _Capture) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)
    capture.returncode = process.returncode
    _drain_after_exit(process.stdout, capture.received)
    _drain_after_exit(process.stderr, capture.stderr)


def _close_process_streams(process: subprocess.Popen[bytes]) -> None:
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _paths(output_dir: Path, scenario: gate6_corpus.Scenario) -> dict[str, Path]:
    stem = scenario.name
    return {
        "sent": output_dir / f"sent-{stem}.bin",
        "received": output_dir / f"received-{stem}.bin",
        "stderr": output_dir / f"qemu-{stem}.stderr",
        "record": output_dir / f"run-{stem}.json",
    }


def _persist_raw(paths: dict[str, Path], capture: _Capture) -> None:
    paths["sent"].write_bytes(bytes(capture.sent))
    paths["received"].write_bytes(bytes(capture.received))
    paths["stderr"].write_bytes(bytes(capture.stderr))


def _raw_record_fields(paths: dict[str, Path], root: Path) -> dict[str, object]:
    return {
        "sent": _relative(paths["sent"], root),
        "sent_sha256": sha256(paths["sent"]),
        "received": _relative(paths["received"], root),
        "received_sha256": sha256(paths["received"]),
        "stderr": _relative(paths["stderr"], root),
        "stderr_sha256": sha256(paths["stderr"]),
    }


def run_session(
    *,
    root: Path,
    image: Path,
    output_dir: Path,
    scenario: gate6_corpus.Scenario,
    timeout_seconds: float,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(output_dir, scenario)
    # A rerun can never inherit an earlier PASS record.
    paths["record"].unlink(missing_ok=True)
    capture = _Capture()
    process: subprocess.Popen[bytes] | None = None
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    image_digest: str | None = None
    try:
        if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise Core0Error("device session timeout must be positive")
        validate_scenario(scenario)
        if not image.is_file():
            raise Core0Error(f"device target image is missing: {image}")
        validate_image_binding(image)
        image_digest = sha256(image)
        require_tools(("qemu-system-riscv64",))
        argv = _qemu_argv(image)
        capture.argv = argv
        process = subprocess.Popen(
            list(argv),
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            bufsize=0,
        )
        capture.pid = process.pid
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)
        deadline = started + timeout_seconds

        ready = _read_exact(
            process,
            len(gate6_corpus.READY),
            deadline=deadline,
            capture=capture,
            context="reading READY",
        )
        if ready != gate6_corpus.READY:
            raise Core0Error(f"device READY frame differs: {ready!r}")

        if scenario.exchanges:
            for index, exchange in enumerate(scenario.exchanges):
                request = exchange.request.encode()
                _write_all(
                    process,
                    request,
                    deadline=deadline,
                    capture=capture,
                    context=f"sending exchange {index}",
                )
                prefix = _read_exact(
                    process,
                    len(exchange.expected_prefix),
                    deadline=deadline,
                    capture=capture,
                    context=f"reading exchange {index} prefix",
                )
                if prefix != exchange.expected_prefix:
                    raise Core0Error(
                        f"device exchange {index} prefix differs: {prefix!r}"
                    )
                frame = _read_exact(
                    process,
                    gate6_corpus.RESPONSE_BYTES,
                    deadline=deadline,
                    capture=capture,
                    context=f"reading exchange {index} response",
                )
                response = gate6_corpus.parse_response(frame)
                if response != exchange.expected_response:
                    raise Core0Error(
                        f"device exchange {index} response differs: "
                        f"observed={response!r} expected={exchange.expected_response!r}"
                    )
                capture.responses.append({
                    "index": index,
                    "pid": process.pid,
                    "image_sha256": image_digest,
                    "prefix_hex": prefix.hex(),
                    "response": asdict(response),
                })
        elif scenario.raw_input:
            _write_all(
                process,
                scenario.raw_input,
                deadline=deadline,
                capture=capture,
                context="sending terminal raw input",
            )

        returncode = _wait_and_collect(
            process,
            deadline=deadline,
            capture=capture,
            read_stdout=not scenario.suppress_output_after_ready,
        )
        # Preserve the process outcome before any protocol-level classification.
        capture.returncode = returncode
        if returncode != scenario.expected_exit_status:
            raise Core0Error(
                f"device QEMU exit status {returncode} differs from compiled status "
                f"{scenario.expected_exit_status}"
            )
        if capture.stderr:
            raise Core0Error(
                "device QEMU wrote unexpected stderr: "
                + bytes(capture.stderr).decode("utf-8", errors="replace")
            )

        post_ready = bytes(capture.received[len(gate6_corpus.READY) :])
        if scenario.exchanges:
            expected = b"".join(
                exchange.expected_prefix
                + gate6_corpus.encode_response(exchange.expected_response)
                for exchange in scenario.exchanges
            )
            if post_ready != expected:
                raise Core0Error("device emitted bytes beyond the exact exchange transcript")
        elif scenario.suppress_output_after_ready:
            # Backpressure may become visible during the stress body or during
            # its immediately following response.  Accept only a *proper*
            # prefix of that independently known byte stream; a complete
            # response cannot legitimately accompany terminal status 11.
            stress_prefix = b"\x55" * 65535
            response = gate6_corpus.encode_response(
                gate6_corpus.Response(
                    gate6_corpus.STATUS_OK,
                    0x8001,
                    65535,
                )
            )
            response_prefix = post_ready[len(stress_prefix) :]
            if (
                not post_ready.startswith(stress_prefix)
                or len(response_prefix) >= len(response)
                or not response.startswith(response_prefix)
            ):
                raise Core0Error(
                    "device backpressure transcript is not the complete stress prefix "
                    "followed by an incomplete response prefix"
                )
        elif post_ready:
            raise Core0Error("terminal device scenario emitted unexpected UART bytes")

        if capture.pid is None or any(
            item["pid"] != capture.pid or item["image_sha256"] != image_digest
            for item in capture.responses
        ):
            raise Core0Error("device exchanges did not use one PID and one bound ELF")

        _persist_raw(paths, capture)
        elapsed = time.monotonic() - started
        finished_at = datetime.now(timezone.utc)
        record: dict[str, object] = {
            "schema_version": 1,
            "status": "pass",
            "profile": PROFILE,
            "test_abi": TEST_ABI,
            "scenario": scenario.name,
            "purpose": scenario.purpose,
            "image": _relative(image, root),
            "image_sha256": image_digest,
            "qemu_pid": capture.pid,
            "single_pid": True,
            "single_elf": True,
            "qemu_argv": list(capture.argv),
            "qemu_returncode": returncode,
            "expected_exit_status": scenario.expected_exit_status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": round(elapsed, 6),
            "ready_hex": gate6_corpus.READY.hex(),
            "withhold_after_ready": scenario.withhold_after_ready,
            "suppress_output_after_ready": scenario.suppress_output_after_ready,
            "exchanges": capture.responses,
            **_raw_record_fields(paths, root),
        }
        write_json(paths["record"], record)
        return record
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        if process is not None:
            _kill_and_reap(process, capture)
        _persist_raw(paths, capture)
        finished_at = datetime.now(timezone.utc)
        failure = {
            "schema_version": 1,
            "status": "fail",
            "profile": PROFILE,
            "test_abi": TEST_ABI,
            "scenario": getattr(scenario, "name", "<invalid>"),
            "image": _relative(image, root),
            "image_sha256": image_digest,
            "qemu_pid": capture.pid,
            "qemu_returncode": capture.returncode,
            "qemu_argv": list(capture.argv),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "error": str(error),
            **_raw_record_fields(paths, root),
        }
        write_json(paths["record"], failure)
        if isinstance(error, Core0Error):
            raise
        raise Core0Error(f"device session failed: {error}") from error
    finally:
        if process is not None:
            _close_process_streams(process)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenario", choices=sorted(gate6_corpus.SCENARIO_BY_NAME), required=True)
    parser.add_argument("--timeout", type=float, default=15.0)
    ns = parser.parse_args()
    root = repo_root()

    def resolve(path: Path) -> Path:
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    try:
        record = run_session(
            root=root,
            image=resolve(ns.image),
            output_dir=resolve(ns.output_dir),
            scenario=gate6_corpus.SCENARIO_BY_NAME[ns.scenario],
            timeout_seconds=ns.timeout,
        )
    except Core0Error as error:
        print(f"DEVICE SESSION RUN FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
