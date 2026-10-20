"""Host launcher resource policy; native startup is qualified separately."""
import importlib.util
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('operator_transport',ROOT/'scripts/school_transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
class OperatorResources(unittest.TestCase):
    def test_default_and_explicit_settings(self):
        with patch.object(resource,'getrlimit',return_value=(-1,-1)):
            base={'OTHER':'retained'};env=transport.authority_environment(base)
            self.assertEqual(env,{'OTHER':'retained','LEAN_NUM_THREADS':'2','LEAN_STACK_SIZE_KB':'65536'})
            self.assertEqual(base,{'OTHER':'retained'})
            self.assertEqual(transport.authority_environment({'LEAN_NUM_THREADS':'3','LEAN_STACK_SIZE_KB':'131072'}),
                {'LEAN_NUM_THREADS':'3','LEAN_STACK_SIZE_KB':'131072'})
    def test_virtual_limit_distinct_from_rss(self):
        with patch.object(resource,'getrlimit',return_value=(2<<30,2<<30)):
            with self.assertRaisesRegex(ValueError,'4096 MiB virtual address space'):
                transport.authority_environment({})
        with patch.object(resource,'getrlimit',return_value=(4<<30,4<<30)):
            self.assertEqual(transport.authority_environment({})['LEAN_NUM_THREADS'],'2')
    def test_actual_cli_rejects_before_native_or_authority_lock(self):
        with tempfile.TemporaryDirectory(prefix='lemma-operator-resource-') as temp:
            base=Path(temp);binary=base/'must-not-execute';marker=base/'executed'
            binary.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath('+repr(str(marker))+').touch()\n')
            binary.chmod(0o700)
            def limits():resource.setrlimit(resource.RLIMIT_AS,(2<<30,2<<30))
            result=subprocess.run([sys.executable,str(ROOT/'scripts/school_transport.py'),'--binary',str(binary),
                str(base/'school'),'{"op":"status","school":"s","actor":"o"}'],capture_output=True,preexec_fn=limits,timeout=10)
            self.assertEqual(result.returncode,1)
            self.assertIn(b'4096 MiB virtual address space',result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((base/'school/authority.lock').exists())
if __name__=='__main__':unittest.main()
