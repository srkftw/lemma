# SPDX-License-Identifier: Apache-2.0
"""Compile/run the real host boundary with independent file-byte observations."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BackingIO(unittest.TestCase):
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
