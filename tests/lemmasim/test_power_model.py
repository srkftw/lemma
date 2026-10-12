"""Actual host controller transitions, independent literal expectations."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class PowerModel(unittest.TestCase):
    def test_edges_busy_retention_and_counter_overflow(self):
        with tempfile.TemporaryDirectory(prefix='lemma-power-model-') as directory:
            executable = Path(directory) / 'power'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                            '-I',str(ROOT/'sim/host'),str(ROOT/'sim/host/lemma_model.c'),
                            str(ROOT/'tests/lemmasim/power_boundaries.c'),'-o',str(executable)],
                           check=True,timeout=60)
            subprocess.run([str(executable)],check=True,timeout=10)

if __name__ == '__main__':
    unittest.main()
