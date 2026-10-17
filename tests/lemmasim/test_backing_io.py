# SPDX-License-Identifier: Apache-2.0
"""Compile/run the real host boundary with independent file-byte observations."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BackingIO(unittest.TestCase):
    def test_scoped_real_write_failure_keeps_capture_and_replay_usable(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'The backing-I/O check requires a host C++ compiler')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'scoped-write-limit'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                            str(ROOT/'sim/host/backing_io.cpp'),
                            str(ROOT/'sim/host/backing_io_posix.cpp'),
                            str(ROOT/'tests/lemmasim/backing_scoped_write_limit.cpp'),
                            '-o', str(executable)], check=True, timeout=60)
            result = subprocess.run([str(executable), directory], capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS actual scoped partial pwrite/EFBIG', result.stdout)

    def test_default_file_limit_signal_is_captured_without_global_policy_change(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'The backing-I/O check requires a host C++ compiler')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'file-limit-signal'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                            str(ROOT/'sim/host/backing_io.cpp'),
                            str(ROOT/'sim/host/backing_io_posix.cpp'),
                            str(ROOT/'tests/lemmasim/backing_fsize_signal.cpp'),
                            '-o', str(executable)], check=True, timeout=60)
            result = subprocess.run([str(executable), directory], capture_output=True,
                                    text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS actual default-SIGXFSZ partial pwrite/EFBIG capture', result.stdout)

    def test_timed_c_boundary_actual_failures_private_replay(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'The backing-I/O check requires a host C++ compiler')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'timed-replay'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(ROOT/'sim/host/backing_io.cpp'), str(ROOT/'sim/host/backing_io_posix.cpp'),
                            str(ROOT/'sim/companion/backing_peer.cpp'), str(ROOT/'sim/companion/backing_c.cpp'),
                            str(ROOT/'tests/lemmasim/backing_timed_replay.cpp'), '-o', str(executable)],
                           check=True, timeout=60)
            result = subprocess.run([str(executable), directory], check=True,
                                    capture_output=True, text=True, timeout=20)
            self.assertIn('PASS exact timed actual partial pwrite/EFBIG', result.stdout)

    def test_shared_c_boundary_state_capture_and_passive_export(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'The backing-I/O check requires a host C++ compiler')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'backing-c'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(ROOT/'sim/host/backing_io.cpp'), str(ROOT/'sim/host/backing_io_posix.cpp'),
                            str(ROOT/'sim/companion/backing_peer.cpp'), str(ROOT/'sim/companion/backing_c.cpp'),
                            str(ROOT/'tests/lemmasim/backing_c_boundaries.cpp'), '-o', str(executable)],
                           check=True, timeout=60)
            result = subprocess.run([str(executable), directory], check=True,
                                    capture_output=True, text=True, timeout=20)
            self.assertIn('PASS actual EBADF capture', result.stdout)
            with (Path(directory)/'export').open('rb') as stream:
                stream.seek(512)
                self.assertEqual(stream.read(512), b'\x93'*512)

    def test_real_posix_failures_and_isolated_replay(self):
        compiler = shutil.which('c++')
        self.assertIsNotNone(compiler, 'The backing-I/O check requires a host C++ compiler')
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'backing-io'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'sim/host'),
                            str(ROOT / 'sim/host/backing_io.cpp'),
                            str(ROOT / 'sim/host/backing_io_posix.cpp'),
                            str(ROOT / 'tests/lemmasim/backing_io_boundaries.cpp'),
                            '-o', str(executable)], check=True, timeout=60)
            result = subprocess.run([str(executable), directory], check=True,
                                    capture_output=True, text=True, timeout=20)
            self.assertIn('actual partial pwrite/EFBIG', result.stdout)
            self.assertTrue(result.stdout.strip().endswith('PASS'))
