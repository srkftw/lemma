"""Profile14 explicitly unsupported snapshots fail before raw-state publication."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_fast import Fast

class MultimodalCheckpointAdmission(unittest.TestCase):
    def test_snapshot_rejects_before_qmp_or_file_creation(self):
        machine=Fast.__new__(Fast);machine.data={'profile':'lemma-silicon-dev/0.14.0'};machine.qmp=Mock()
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'snapshot.chk'
            with self.assertRaisesRegex(ValueError,'explicitly unsupported'):machine.call('snapshot '+str(path))
            self.assertEqual(list(Path(name).iterdir()),[])
        machine.qmp.execute.assert_not_called()

    def test_restore_rejects_before_candidate_or_missing_path_access(self):
        machine=Fast.__new__(Fast);machine.data={'profile':'lemma-silicon-dev/0.14.0'};machine.qmp=Mock();machine.restore_checkpoint=Mock()
        with self.assertRaisesRegex(ValueError,'explicitly unsupported'):machine.call('restore /absent/raw-state.chk')
        machine.qmp.execute.assert_not_called();machine.restore_checkpoint.assert_not_called()

if __name__=='__main__':unittest.main()
