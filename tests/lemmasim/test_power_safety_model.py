from pathlib import Path
import os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
class PowerSafetyModel(unittest.TestCase):
 def test_actual_boundary_model(self):
  with tempfile.TemporaryDirectory(prefix='lemma-power-safety-') as d:
   binary=Path(d)/'power'
   subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'sim/host'),str(ROOT/'sim/host/lemma_model.c'),str(ROOT/'sim/host/lemma_power_safety.c'),str(ROOT/'tests/lemmasim/power_safety_boundaries.c'),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=30)
   subprocess.run([str(binary)],check=True,timeout=10)
