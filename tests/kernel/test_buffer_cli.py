"""Real host pipe fixtures; no target build or guest execution is claimed."""
import importlib.util
import fcntl
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from core0_common import Core0Error
from buffer_transport import APPLICATION_MAGIC
from run_buffer_session import BufferSession, transport

spec = importlib.util.spec_from_file_location("buffer_cli_pump", ROOT / "scripts/buffer-cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class TerminalInputTests(unittest.TestCase):
    def session(self, process, *, timeout=3):
        session = object.__new__(BufferSession)
        session.process = process
        session.capture = transport._Capture()
        session.deadline = time.monotonic() + timeout
        session.events, session.records, session.responses = [], [], []
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
        return session

    def stop(self, process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=2)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()

    def test_paused_operator_drains_real_full_pipe_and_preserves_batch_utf8_eof(self):
        read_fd, write_fd = os.pipe()
        kernel = b"K1" + b" 0000000000000000" * 5 + b"\n"
        code = ("import os,sys\n"
                "frame=b'K1'+b' 0000000000000000'*5+b'\\n'\n"
                "for _ in range(1200): os.write(1,frame)\n"
                "os.write(int(sys.argv[1]),b'x'*12000+b'\\n'+'help\\nbuffer append 4 λ\\nquit'.encode())\n"
                "os.close(int(sys.argv[1]))\n"
                "os.read(0,1)\n")
        process = subprocess.Popen([sys.executable, "-c", code, str(write_fd)],
                                   pass_fds=(write_fd,), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        os.close(write_fd)
        try:
            session = self.session(process)
            terminal = cli.TerminalInput(read_fd)
            with self.assertRaisesRegex(ValueError, "at most"):
                terminal.readline(session)
            self.assertLessEqual(len(terminal.buffer), terminal.MAX_LINE_BYTES + terminal.READ_BYTES)
            # The child could not publish stdin until its output, larger
            # than the pipe, had made real progress while the operator paused.
            self.assertGreaterEqual(len(session.capture.received),
                                    len(kernel) * 1200 - fcntl.fcntl(process.stdout.fileno(), fcntl.F_GETPIPE_SZ))
            self.assertEqual(terminal.readline(session), "help")
            self.assertEqual(terminal.readline(session), "buffer append 4 λ")
            self.assertEqual(terminal.readline(session), "quit")
            with self.assertRaises(EOFError): terminal.readline(session)
            # Fair input delivery may leave complete guest frames queued.
            # The same parser owner accounts for the finite remainder.
            while len(session.events) < 1200:
                self.assertEqual(session.event()["kind"], "kernel")
            self.assertEqual(bytes(session.capture.received), kernel * 1200)
            self.assertEqual(len(session.events), 1200)
            self.assertEqual(session.capture.sent, b"")
            self.assertEqual(session.capture.stderr, b"")
            self.assertIsNone(process.poll())
        finally:
            os.close(read_fd)
            self.stop(process)
        self.assertEqual(process.returncode, -9)

    def test_perpetual_kernel_output_serves_preloaded_and_ready_input_fairly(self):
        read_fd, write_fd = os.pipe()
        kernel = b"K1" + b" 0000000000000000" * 5 + b"\n"
        code = ("import os,sys\n"
                "frame=b'K1'+b' 0000000000000000'*5+b'\\n'\n"
                "os.write(int(sys.argv[1]),b'help\\nversion\\nquit')\n"
                "os.close(int(sys.argv[1]))\n"
                "while True: os.write(1,frame*1200)\n")
        process = subprocess.Popen([sys.executable, "-c", code, str(write_fd)],
                                   pass_fds=(write_fd,), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        os.close(write_fd)
        try:
            session = self.session(process)
            terminal = cli.TerminalInput(read_fd)
            terminal.buffer.extend(b"discover\n")
            # Both streams are actually ready before input delivery. The
            # producer never stops output or reaches a voluntary EOF.
            self.assertIn(read_fd, select.select([read_fd], [], [], 2)[0])
            self.assertIn(process.stdout.fileno(),
                          select.select([process.stdout.fileno()], [], [], 2)[0])
            for expected in ("discover", "help", "version", "quit"):
                before = len(session.events)
                self.assertEqual(terminal.readline(session), expected)
                self.assertLessEqual(len(session.events) - before, 1)
                self.assertIsNone(process.poll())
            with self.assertRaises(EOFError):
                terminal.readline(session)
            self.assertGreater(len(session.events), 0)
            self.assertEqual(bytes(session.capture.received), kernel * len(session.events))
            self.assertEqual(session.capture.sent, b"")
            self.assertEqual(session.capture.stderr, b"")
        finally:
            os.close(read_fd)
            self.stop(process)
        self.assertEqual(process.returncode, -9)

    def test_invalid_utf8_and_oversized_lines_recover_without_unbounded_buffer(self):
        read_fd, write_fd = os.pipe()
        process = subprocess.Popen([sys.executable, "-c", "import os;os.read(0,1)"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        try:
            session = self.session(process)
            terminal = cli.TerminalInput(read_fd)
            os.write(write_fd, b"\xff\nhelp\n")
            with self.assertRaises(UnicodeDecodeError): terminal.readline(session)
            self.assertEqual(terminal.readline(session), "help")
            terminal.buffer.extend(b"x" * terminal.MAX_LINE_BYTES)
            os.write(write_fd, b"x\nversion\n")
            with self.assertRaisesRegex(ValueError, "at most"): terminal.readline(session)
            self.assertLessEqual(len(terminal.buffer), terminal.MAX_LINE_BYTES + terminal.READ_BYTES)
            self.assertEqual(terminal.readline(session), "version")
            session.deadline = time.monotonic() - 1
            with self.assertRaises(TimeoutError): terminal.readline(session)
            self.assertEqual(session.capture.sent, b"")
        finally:
            os.close(read_fd); os.close(write_fd)
            self.stop(process)

    def test_unsolicited_client_frame_is_not_a_new_command_response(self):
        payload = struct.pack("<8Q", APPLICATION_MAGIC, 1, 7, 0, 0, 0, 0, 1)
        raw = b"LMO1" + struct.pack("<BBH", 1, 0, 64) + payload
        read_fd, write_fd = os.pipe()
        process = subprocess.Popen([sys.executable, "-c",
                                    f"import os;os.write(1,{raw!r});os.read(0,1)"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        try:
            session = self.session(process)
            with self.assertRaisesRegex(Core0Error, "no outstanding request"):
                cli.TerminalInput(read_fd).readline(session)
            self.assertEqual(bytes(session.capture.received), raw)
            self.assertEqual(session.capture.sent, b"")
        finally:
            os.close(read_fd); os.close(write_fd)
            self.stop(process)


if __name__ == "__main__":
    unittest.main(verbosity=2)
