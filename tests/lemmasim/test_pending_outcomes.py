# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_session as module
class PendingOutcomes(unittest.TestCase):
 def test_native_header_versions_are_explicit(self):
  with tempfile.TemporaryDirectory() as directory:
   runtime=object.__new__(module.RTL);runtime.checkpoint_identity='a'*64
   path=Path(directory)/'state'
   for version in (1,2):
    path.write_bytes(b'LMSSRTL1'+struct.pack('<Q',version)+b'a'*64+struct.pack('<4Q',16,1,0,0)+struct.pack('<2Q',0,7)+b'\0')
    runtime.preflight_checkpoint(path,7)
   for version in (0,3):
    wire=bytearray(path.read_bytes());struct.pack_into('<Q',wire,8,version);path.write_bytes(wire)
    with self.assertRaises(ValueError):runtime.preflight_checkpoint(path,7)
 def session(self,mode,backend):
  session=object.__new__(module.Session);session.mode=mode;session.ensure_capture_certain=lambda:None
  class Machine:
   identity={'backend':backend}
   def call(self,command):self.command=command;return {'cycle':42}
  session.machine=Machine();return session
 def test_binding_has_permission_and_backend_admission(self):
  value={'action':'backing-outcomes','path':'outcomes.io'}
  for mode,backend in (('student','rtl'),('developer','qemu')):
   with self.assertRaises(ValueError):self.session(mode,backend).dispatch(value)
  session=self.session('developer','rtl');result=session.dispatch(value)
  self.assertEqual(result['machine']['cycle'],42)
  self.assertTrue(session.machine.command.startswith('backing-outcomes /'))
  with self.assertRaises(ValueError):session.dispatch(dict(value,path='bad\nrun 1'))
if __name__=='__main__':unittest.main()
