# SPDX-License-Identifier: Apache-2.0
"""Regression controls for concrete process-observer failures, without SPICE."""
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('process_comparator', ROOT/'scripts/check_sg13g2_comparator.py')
comparator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparator)


class ProcessObserver(unittest.TestCase):
    def test_expired_budget_cannot_create_process(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(comparator.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, 'budget exhausted before Popen'):
                comparator.invoke(['unreachable'], Path(temporary), Path(temporary)/'log', time.monotonic()-1, 20)
            spawn.assert_not_called()

    def test_long_but_interrupted_transient_rejects(self):
        rows = [[index*1.8e-6/20000]+[0.0]*9 for index in range(20001)]
        with self.assertRaisesRegex(RuntimeError, 'declared start/end'):
            comparator.validate_waveform(rows)

    def test_complete_endpoints_cannot_hide_missing_clock_period(self):
        rows = [[index*2e-6/20000]+[0.0]*9 for index in range(20001)]
        rows[10000][0] = rows[9999][0]
        with self.assertRaisesRegex(RuntimeError, 'gap'):
            comparator.validate_waveform(rows)


if __name__ == '__main__':
    unittest.main()
