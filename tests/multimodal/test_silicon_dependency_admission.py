"""Explicit bus dependency admission stays read-only and rejects before compile."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_silicon import bus_dependency
import silicon_compute

class DependencyAdmission(unittest.TestCase):
    def test_missing_explicit_dependency_cannot_clone(self):
        with tempfile.TemporaryDirectory() as name,patch('silicon_compute.prepare') as prepare:
            with self.assertRaisesRegex(ValueError,'existing CVW Git checkout'):bus_dependency(Path(name)/'absent')
            prepare.assert_not_called()
    def test_nongit_directory_cannot_be_inferred_from_parent(self):
        with tempfile.TemporaryDirectory() as name,patch('silicon_compute.prepare') as prepare:
            with self.assertRaisesRegex(ValueError,'existing CVW Git checkout'):bus_dependency(Path(name))
            prepare.assert_not_called()
    def test_wrong_real_git_revision_rejects_before_manifest(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);subprocess.run(['git','init','-q',root],check=True)
            (root/'fixture').write_text('wrong dependency\n')
            subprocess.run(['git','-C',root,'add','fixture'],check=True)
            subprocess.run(['git','-C',root,'-c','user.name=Dependency test','-c','user.email=fixture@invalid','commit','-qm','fixture'],check=True)
            with self.assertRaisesRegex(RuntimeError,'CVW identity mismatch'):bus_dependency(root)
    def test_dirty_exact_revision_rejects_before_source_read(self):
        # Minimal host command control exercises the actual prepare ordering;
        # immutable real checkout mutation is exercised separately, read-only.
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'.git').mkdir()
            with patch('silicon_compute.subprocess.check_output',side_effect=[silicon_compute.REV+'\n',' M src/cvw.sv\n']),patch('silicon_compute.sources') as sources:
                with self.assertRaisesRegex(RuntimeError,'CVW source tree modified'):bus_dependency(root)
                sources.assert_not_called()
    def test_deps_flag_rejects_other_lane_without_outputs(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name)/'unused'
            result=subprocess.run([sys.executable,str(silicon_compute.ROOT/'scripts/check_silicon.py'),'--lane','devices','--deps',name,'--work-dir',out],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2);self.assertIn('only for bus-lanes',result.stderr);self.assertFalse(out.exists())
