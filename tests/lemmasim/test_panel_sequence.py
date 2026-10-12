"""Independent synthetic digital-panel sequence and cancellation observations."""
import subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class PanelSequence(unittest.TestCase):
    def test_literal_sequence_and_reset(self):
        with tempfile.TemporaryDirectory(prefix='lemma-panel-sequence-') as directory:
            exe=Path(directory)/'sequence'
            subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
                '-I',str(ROOT/'sim/host'),str(ROOT/'sim/host/lemma_model.c'),
                str(ROOT/'tests/lemmasim/sequence_boundaries.c'),'-o',str(exe)],check=True,timeout=60)
            subprocess.run([str(exe)],check=True,timeout=10)
