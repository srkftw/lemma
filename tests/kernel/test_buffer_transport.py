"""Distinguish framed binary payloads from control records and truncation."""
import struct
import sys
import json
import importlib.util
import os
import signal
import subprocess
import contextlib
import copy
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from buffer_transport import APPLICATION_MAGIC, command, decode_uart, input_envelope, validate_input_envelope
from core0_common import Core0Error, sha256
from run_buffer_session import BufferSession, SiliconBufferSession, _known_complete_prefix, _quiesce_uart, validate_quiescence
from run_kernel import Session
import run_device_session as transport

cli_spec = importlib.util.spec_from_file_location("buffer_cli", Path(__file__).resolve().parents[2]
                                                / "scripts/buffer-cli.py")
buffer_cli = importlib.util.module_from_spec(cli_spec)
cli_spec.loader.exec_module(buffer_cli)


class BufferTransportTests(unittest.TestCase):
    def test_rtl_diagnostics_are_exact_and_qemu_stays_strict(self):
        from types import SimpleNamespace
        prepared = {key:key for key in ("profile", "profile_sha256", "binary", "rom", "rom_audit", "rtl_build", "rtl_sources")}
        prepared["workloads"] = {"service":{"image":"fixture"}}
        capture = transport._Capture()
        context = SimpleNamespace(prepared=prepared, capture=capture, report={}, PROGRESS=SiliconBufferSession.PROGRESS)
        line = b"RTL progress cycles=1000000 pc=0x80000100 privilege=1 retired=250000 ticks=100000 timer_traps=1 UART=176\n"
        with patch("silicon_guest.prepared", return_value=prepared):
            capture.stderr.extend(line)
            SiliconBufferSession.validate_stderr(context)
            self.assertEqual(context.report["rtl_progress"][0]["timer_traps"], 1)
            with self.assertRaises(Core0Error):Session.validate_stderr(context)
            for bad in (line[:-1], line.replace(b"privilege=1", b"privilege=4"), line+b"unknown diagnostic\n"):
                capture.stderr[:] = bad
                with self.subTest(bad=bad), self.assertRaises(Core0Error):
                    SiliconBufferSession.validate_stderr(context)
            capture.stderr[:] = line
            changed = copy.deepcopy(prepared);changed["binary"] = "changed"
            with patch("silicon_guest.prepared", return_value=changed), self.assertRaises(Core0Error):
                SiliconBufferSession.validate_stderr(context)

    def output(self, *, data=b"", operation=3, application=0, transport=0, handle=5):
        payload = struct.pack("<8Q", APPLICATION_MAGIC, 1, operation, 1, handle,
                              len(data), len(data), (application << 32) | (transport << 40)) + data
        return b"LMO1" + struct.pack("<BBH", 1, 0, len(payload)) + payload

    def test_binary_control_lookalikes_are_payload(self):
        kernel = b"K1" + b" 0000000000000000" * 5 + b"\n"
        data = kernel + b"\x00\xffLMO1" + "∑λ".encode()
        raw = kernel + self.output(data=data) + kernel
        events, tail = decode_uart(raw)
        self.assertEqual([event["kind"] for event in events], ["kernel", "client", "kernel"])
        self.assertEqual(events[1]["value"]["data_hex"], data.hex())
        self.assertEqual(sum(event["bytes"] for event in events), len(raw))
        self.assertFalse(tail)

    def test_truncated_suffix_must_be_completed(self):
        raw = self.output(data=b"\x00\xff")
        for length in (1, 3, 7, 8, len(raw)-1):
            with self.subTest(length=length):
                with self.assertRaises(Core0Error):
                    decode_uart(raw[:length])
                events, tail = decode_uart(raw[:length], allow_partial=True)
                self.assertFalse(events)
                self.assertEqual(tail, raw[:length])
        self.assertEqual(len(decode_uart(raw)[0]), 1)

    def test_unknown_bytes_and_malformed_envelope_fail(self):
        for raw in (b"garbage", self.output() + b"?", b"LMO1\x02\x00\x40\x00",
                    b"LMO1\x01\x01\x40\x00", b"LMO1\x01\x00\xff\x00"):
            with self.subTest(raw=raw), self.assertRaises(Core0Error):
                decode_uart(raw)

    def test_large_mixed_capture_preserves_offsets_and_rejects_its_suffix(self):
        kernel = b"K1" + b" 0000000000000000" * 5 + b"\n"
        client = self.output(data=b"\x00\xffK1LMO1")
        raw = (kernel + client) * 4096
        events, tail = decode_uart(raw)
        self.assertEqual(len(events), 8192)
        self.assertEqual(events[-1]["offset"], len(raw) - len(client))
        self.assertEqual(sum(event["bytes"] for event in events), len(raw))
        self.assertFalse(tail)
        with self.assertRaisesRegex(Core0Error, f"unexplained UART bytes at offset{len(raw)}"):
            decode_uart(raw + b"?")
        partial_events, partial = decode_uart(raw + client[:7], allow_partial=True)
        self.assertEqual(partial_events, events)
        self.assertEqual(partial, client[:7])
        with self.assertRaisesRegex(Core0Error, f"truncated UART frame at offset{len(raw)}"):
            decode_uart(raw + client[:7])

    def test_error_cannot_expose_success_fields(self):
        for raw in (self.output(application=202), self.output(transport=96),
                    self.output(data=b"x", operation=2)):
            with self.subTest(raw=raw), self.assertRaises(Core0Error):
                decode_uart(raw)
        raw = self.output(operation=5, application=201, handle=0)
        self.assertEqual(decode_uart(raw)[0][0]["value"]["application_status"], 201)

    def test_input_is_exact_binary_envelope(self):
        raw = command(2, 1, 5, 0, 2, b"\x00\xff")
        self.assertEqual(raw[:8], b"LMI1\x01\x00\x2a\x00")
        self.assertEqual(raw[8:], struct.pack("<5Q", 2, 1, 5, 0, 2) + b"\x00\xff")
        self.assertEqual(input_envelope(bytes(40), diagnostic=True)[:8], b"LMI1\x02\x00\x28\x00")
        for args in ((2, 1, 5, 0, 3, b"ab"), (3, 1, 5, 0, 2, b"ab")):
            with self.assertRaises(Core0Error):
                command(*args)

    def test_complete_input_header_and_length_are_required(self):
        valid = input_envelope(b"\x00\xff")
        validate_input_envelope(valid)
        for raw in (b"LMI1", valid[:-1], valid + b"x", b"LMI1\x01\x01\x02\x00ab",
                    b"LMI1\x03\x00\x02\x00ab", b"LMI1\x02\x00\x02\x00ab",
                    b"LMI1\x01\x00\x00\x00"):
            with self.subTest(raw=raw), self.assertRaises(Core0Error):
                validate_input_envelope(raw)

    def test_private_or_unknown_transport_status_is_rejected(self):
        for status in (95, 253, 254, 255):
            with self.subTest(status=status), self.assertRaises(Core0Error):
                decode_uart(self.output(operation=10, transport=status, handle=0))
        with self.assertRaises(Core0Error):
            decode_uart(self.output(operation=7, application=200, handle=0))
        self.assertEqual(decode_uart(self.output(operation=10, transport=96, handle=0))[0][0]
                         ["value"]["transport_status"], 96)

    def test_idle_prompt_deadline_escapes_command_error_handler(self):
        read_fd, write_fd = os.pipe()
        previous_handler = signal.getsignal(signal.SIGALRM)
        try:
            with self.assertRaises(TimeoutError):
                try:
                    with buffer_cli.prompt_deadline(time.monotonic() + 0.03):
                        os.read(read_fd, 1)
                except (Core0Error, ValueError):
                    self.fail("prompt deadline was swallowed as a malformed command")
            self.assertIs(signal.getsignal(signal.SIGALRM), previous_handler)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        finally:
            os.close(read_fd)
            os.close(write_fd)


class BufferSessionCleanupTests(unittest.TestCase):
    """Host-only real child processes; no target execution or policy claims."""
    kernel = b"K1" + b" 0000000000000000" * 5 + b"\n"

    @contextlib.contextmanager
    def native_child(self, chunks, *, stderr=b"", natural_exit=False):
        code = """import json, os, signal, sys
with open(sys.argv[1]) as source:
    chunks = [bytes.fromhex(value) for value in json.load(source)]
def continued(_signal, _frame):
    if chunks:
        os.write(1, chunks.pop(0))
signal.signal(signal.SIGCONT, continued)
os.write(2, bytes.fromhex(sys.argv[2]))
os.write(1, chunks.pop(0))
if sys.argv[3] == 'exit':
    sys.exit(0)
while True:
    signal.pause()
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "chunks.json"
            source.write_text(json.dumps([chunk.hex() for chunk in chunks]))
            process = subprocess.Popen((sys.executable, "-c", code, str(source),
                                        stderr.hex(), "exit" if natural_exit else "live"),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, bufsize=0)
            capture = transport._Capture(pid=process.pid, argv=tuple(process.args))
            for stream in (process.stdin, process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
            try:
                transport._read_exact(process, len(chunks[0]), deadline=time.monotonic()+2,
                                      capture=capture, context="waiting for real host child readiness")
                yield process, capture
            finally:
                if not process.stdout.closed:
                    transport._kill_and_reap(process, capture)
                transport._close_process_streams(process)
                self.assertIsNotNone(process.poll())
                self.assertFalse(Path("/proc", str(process.pid)).exists())

    def exercise(self, *, suffix=b"", stderr=b"", natural_exit=False, mutate_runner=False,
                 expect_failure=False, mutate_stdout=False, mutate_stderr=False, original=None,
                 deadline_expired=False, base_error_before_kill=False, base_persistence_error=False,
                 mutate_parsed_prefix=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "run"
            output.mkdir()
            image = root / "image.elf"
            image.write_bytes(b"host fixture image")
            for name in ("audit.json", "provenance.json", *BufferSession.RUNNER_PATHS):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            session = BufferSession.__new__(BufferSession)
            session.root, session.image, session.output_dir = root, image, output
            session.sources = {"source.lean": "fixture"}
            session.digest = sha256(image)
            session.runner_inputs = {name: sha256(root / name) for name in BufferSession.RUNNER_PATHS}
            session.report = {"status": "FAIL", "guest_live_before_cleanup": True,
                              "audit_sha256": sha256(root / "audit.json"),
                              "provenance_sha256": sha256(root / "provenance.json")}
            original_exit = Session.__exit__
            original_write = Path.write_bytes
            injected = []

            def write_bytes(path, raw):
                if base_persistence_error and path == output / "received.bin" and not injected:
                    injected.append(True)
                    raise OSError("injected actual base raw persistence error")
                return original_write(path, raw)

            def drained_exit(_session, *args):
                if base_error_before_kill:
                    raise OSError("injected base exit before kill")
                result = original_exit(_session, *args)
                if mutate_runner:
                    (root / BufferSession.RUNNER_PATHS[0]).write_text("changed during cleanup")
                if mutate_stdout:
                    session.capture.received[-2] = ord("1")
                if mutate_stderr:
                    session.capture.stderr.extend(b"post-kill stderr mutation")
                return result

            with self.native_child([self.kernel+suffix], stderr=stderr, natural_exit=natural_exit) as (process, capture):
                session.process, session.capture = process, capture
                session.events = decode_uart(self.kernel)[0]
                session.records = [event["value"] for event in session.events]
                if mutate_parsed_prefix:
                    capture.received[4] = ord("1")
                session.started = time.monotonic()
                session.deadline = session.started + (-1 if deadline_expired else 2)
                session.success = True
                if natural_exit:
                    process.wait(timeout=2)
                with patch.object(Session, "__exit__", drained_exit), \
                        patch.object(Path, "write_bytes", write_bytes), \
                        patch("run_buffer_session.source_inputs", return_value=session.sources):
                    if expect_failure and original is None:
                        with self.assertRaises((Core0Error, OSError)):
                            session.__exit__(None, None, None)
                    else:
                        self.assertFalse(session.__exit__(type(original) if original else None,
                                                         original, None))
            value = json.loads((output / "result.json").read_text())
            self.assertEqual(value["status"], "FAIL" if expect_failure else "PASS")
            return value

    def test_complete_cleanup_suffix_is_retained_for_semantic_replay(self):
        value = self.exercise(suffix=self.kernel)
        self.assertEqual(value["observed_event_count"], 1)
        self.assertEqual(len(value["wire_events"]), 2)
        self.assertEqual(len(value["records"]), 2)
        self.assertTrue(value["complete_raw_coverage"])

    def test_unexplained_cleanup_suffix_persists_fail_and_raises(self):
        self.exercise(suffix=b"?", expect_failure=True)

    def test_late_stderr_and_natural_exit_cannot_retain_pass(self):
        self.exercise(stderr=b"late error", expect_failure=True)
        self.exercise(natural_exit=True, expect_failure=True)

    def test_runner_changed_during_cleanup_cannot_retain_pass(self):
        self.exercise(mutate_runner=True, expect_failure=True)

    def test_same_length_stdout_and_changed_stderr_after_stop_fail(self):
        self.exercise(mutate_stdout=True, expect_failure=True)
        self.exercise(mutate_stderr=True, expect_failure=True)

    def test_mutated_already_parsed_prefix_fails_complete_post_kill_decode(self):
        value = self.exercise(mutate_parsed_prefix=True, expect_failure=True)
        self.assertEqual(value["uart_quiescence"]["status"], "PASS")
        self.assertIn("differs from observed frames", value["error"])
        self.assertEqual(value["returncode"], -9)
        self.assertFalse(value["complete_raw_coverage"])

    def test_semantic_error_survives_secondary_cleanup_failure(self):
        for suffix, expired in ((b"?", False), (b"K1", True)):
            with self.subTest(suffix=suffix):
                value = self.exercise(suffix=suffix, deadline_expired=expired, expect_failure=True,
                                      original=Core0Error("actual binary reference mismatch"))
                self.assertEqual(value["error"], "actual binary reference mismatch")
                self.assertEqual(value["failure_category"], "observation-failure")
                self.assertEqual(value["uart_quiescence"]["status"], "FAIL")
                self.assertTrue(value["cleanup_errors"])
                self.assertEqual(value["returncode"], -9)
                self.assertEqual(value["raw_artifacts"]["received.bin"], hashlib.sha256(self.kernel+suffix).hexdigest())

    def test_base_exit_failure_retains_primary_error_and_real_child_cleanup(self):
        for kwargs in ({"base_error_before_kill": True}, {"base_persistence_error": True}):
            with self.subTest(kwargs=kwargs):
                value = self.exercise(expect_failure=True, original=Core0Error("actual binary reference mismatch"), **kwargs)
                self.assertEqual(value["error"], "actual binary reference mismatch")
                self.assertEqual(value["failure_category"], "observation-failure")
                self.assertEqual(value["returncode"], -9)
                self.assertEqual(value["raw_artifacts"]["received.bin"], hashlib.sha256(self.kernel).hexdigest())
                self.assertEqual(value["cleanup_errors"][0]["stage"], "base-session-cleanup")
                with self.assertRaises(Core0Error):
                    validate_quiescence(value, self.kernel, b"")
        self.exercise(expect_failure=True, base_persistence_error=True)

    def test_real_fragmented_kernel_and_binary_frames_need_fresh_refreeze(self):
        binary = BufferTransportTests().output(data=b"\x00\xffK1LMO1")
        chunks = [self.kernel[:2], self.kernel[2:]+binary[:1], binary[1:4], binary[4:8], binary[8:]]
        with self.native_child(chunks) as (process, capture):
            facts = {}
            _quiesce_uart(process, capture, time.monotonic()+2, facts, budget=1)
            self.assertIsNone(process.poll(), "stop notification must not reap the owned child")
            self.assertEqual(bytes(capture.received), self.kernel+binary)
            self.assertEqual(facts["cycles"], 5)
            self.assertEqual(facts["resumes"], 4)
            self.assertEqual(len(facts["observed_stops"]), 5)
            frozen = bytes(capture.received)
            transport._kill_and_reap(process, capture)
            self.assertEqual(capture.returncode, -9)
            self.assertEqual(bytes(capture.received), frozen)
            facts.update(post_kill_boundary_unchanged=True, post_kill_stderr_unchanged=True)
            report = {"pid": process.pid, "uart_quiescence": facts}
            validate_quiescence(report, bytes(capture.received), bytes(capture.stderr))
            events, tail = decode_uart(frozen)
            self.assertEqual([event["offset"] for event in events], [0, 88])
            self.assertEqual(events[1]["value"]["data_hex"], b"\x00\xffK1LMO1".hex())
            self.assertFalse(tail)
            for changed in ("frozen_stdout_sha256", "frozen_stderr_sha256", "cycles", "post_kill_stderr_unchanged"):
                forged = copy.deepcopy(report)
                forged["uart_quiescence"][changed] = False
                with self.subTest(changed=changed), self.assertRaises(Core0Error):
                    validate_quiescence(forged, frozen, bytes(capture.stderr))

    def test_real_large_parsed_prefix_only_decodes_new_partial_tail_while_frozen(self):
        binary = BufferTransportTests().output(data=b"\x00\xffK1LMO1")
        prefix = self.kernel * 4096 + binary
        observed = decode_uart(prefix)[0]
        for frame in (self.kernel, binary):
            with self.subTest(kind=frame[:2]), self.native_child([prefix + frame[:2], frame[2:]]) as (process, capture):
                known = _known_complete_prefix(observed, len(capture.received))
                self.assertEqual(known, len(prefix))
                facts = {}
                with patch("run_buffer_session.decode_uart", wraps=decode_uart) as decoder:
                    _quiesce_uart(process, capture, time.monotonic()+5, facts,
                                  known_complete_bytes=known)
                self.assertEqual([len(call.args[0]) for call in decoder.call_args_list], [2, len(frame)])
                self.assertEqual(facts["cycles"], 2)
                self.assertIsNone(process.poll())
                frozen = bytes(capture.received)
                self.assertEqual(frozen, prefix + frame)
                transport._kill_and_reap(process, capture)
                self.assertEqual(capture.returncode, -9)
                self.assertEqual(bytes(capture.received), frozen)
                facts.update(post_kill_boundary_unchanged=True, post_kill_stderr_unchanged=True)
                validate_quiescence({"pid": process.pid, "uart_quiescence": facts}, frozen, bytes(capture.stderr))
                events, tail = decode_uart(frozen)
                self.assertEqual(events[:len(observed)], observed)
                self.assertEqual(events[-1]["offset"], len(prefix))
                self.assertFalse(tail)

    def test_parsed_prefix_metadata_must_be_contiguous_typed_and_bounded(self):
        events = decode_uart(self.kernel)[0]
        self.assertEqual(_known_complete_prefix(events, len(self.kernel)), len(self.kernel))
        for field, value in (("offset", 1), ("offset", False), ("bytes", True),
                             ("bytes", 87), ("kind", "unknown"), ("kind", [])):
            changed = copy.deepcopy(events)
            changed[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(Core0Error):
                _known_complete_prefix(changed, len(self.kernel))
        for size in (True, -1, len(self.kernel)-1):
            with self.subTest(size=size), self.assertRaises(Core0Error):
                _known_complete_prefix(events, size)

    def test_stale_stop_and_expired_deadline_are_rejected(self):
        with self.native_child([self.kernel]) as (process, capture):
            os.killpg(process.pid, signal.SIGSTOP)
            until = time.monotonic()+1
            while os.waitid(os.P_PID, process.pid, os.WSTOPPED | os.WNOHANG | os.WNOWAIT) is None:
                self.assertLess(time.monotonic(), until)
                time.sleep(0.001)
            with self.assertRaisesRegex(Core0Error, "preexisting stop"):
                _quiesce_uart(process, capture, time.monotonic()+1, {})
        with self.native_child([self.kernel]) as (process, capture):
            with self.assertRaisesRegex(Core0Error, "deadline"):
                _quiesce_uart(process, capture, time.monotonic()-1, {})

    def test_partial_timeout_and_cycle_limit_do_not_reap_or_discard(self):
        for kwargs, message in (({"budget": 0.03}, "timed out"), ({"max_cycles": 1}, "cycle budget")):
            with self.subTest(kwargs=kwargs), self.native_child([b"K1"]) as (process, capture):
                with self.assertRaisesRegex(Core0Error, message):
                    _quiesce_uart(process, capture, time.monotonic()+1, {}, **kwargs)
                self.assertIsNone(process.poll())
                self.assertEqual(bytes(capture.received), b"K1")
        with self.native_child([self.kernel]) as (process, capture):
            for kwargs in ({"budget": True}, {"budget": float("nan")}, {"budget": 6},
                           {"max_cycles": True}, {"max_cycles": 65},
                           {"known_complete_bytes": True}, {"known_complete_bytes": -1},
                           {"known_complete_bytes": len(self.kernel)+1}):
                with self.subTest(kwargs=kwargs), self.assertRaises(Core0Error):
                    _quiesce_uart(process, capture, time.monotonic()+1, {}, **kwargs)


if __name__ == "__main__":
    unittest.main()
