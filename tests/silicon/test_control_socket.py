# SPDX-License-Identifier: Apache-2.0
"""Actual Unix-socket lifecycle and owner-confusion negatives; host evidence.

The independent machine-boundary fixture does not stand in for RV64 execution.
It exercises the real persistent owner, requests, snapshots and cleanup.
"""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_session as runtime

CHILD='''import json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
import lemmasim_session as runtime
class Machine:
    identity={'backend':'rtl','scope':'independent control transport fixture'}
    argv=[]
    def __init__(self,args,directory):
        if sys.argv[3]=='fail':raise RuntimeError('literal failed machine construction')
        self.cycle=0
    def call(self,command):
        if command.startswith('run '):self.cycle+=int(command[4:])
        if command.startswith('snapshot '):Path(command[9:]).write_text(str(self.cycle))
        if command.startswith('restore '):self.cycle=int(Path(command[8:]).read_text())
        return {'cycle':self.cycle,'ticks':self.cycle//10,'finished':False}
    def close(self):pass
runtime.serve(SimpleNamespace(session_dir=Path(sys.argv[2]),disk=None,backend='rtl',mode='laboratory',
    headless=True,tablet=None,paused=True,quantum=1000,restore=None),machine_type=Machine)
'''


class ControlSocketTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.children=[]
        self.addCleanup(self.stop_children)

    def stop_children(self):
        for child,directory in self.children:
            if child.poll() is None:
                try:runtime.request(directory,{'action':'destroy'},timeout=2)
                except (OSError,ValueError,RuntimeError):child.terminate()
                try:child.communicate(timeout=3)
                except subprocess.TimeoutExpired:child.kill();child.communicate(timeout=3)
            child.stdout.close();child.stderr.close()

    def launch(self,name,long=False):
        directory=self.root/(('long-'+'x'*130) if long else name)
        if long:directory=directory/name
        child=subprocess.Popen([sys.executable,'-c',CHILD,str(ROOT/'scripts'),str(directory),'ok'],
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.children.append((child,directory))
        deadline=time.monotonic()+4
        while not (directory/'session.json').exists() and time.monotonic()<deadline:
            if child.poll() is not None:break
            time.sleep(.01)
        self.assertIsNone(child.poll(),'persistent owner exited before readiness')
        metadata=json.loads((directory/'session.json').read_text())
        return child,directory,metadata

    def test_real_long_lifecycle_preserves_ordinary_requests_and_owned_cleanup(self):
        child,directory,metadata=self.launch('long-live',True)
        self.assertGreaterEqual(len(os.fsencode(str(directory/'machine.sock'))),104)
        self.assertLess(len(os.fsencode(metadata['socket'])),104)
        private=Path(metadata['control']['directory'])
        self.assertEqual(stat.S_IMODE(private.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE((private/'owner.json').stat().st_mode),0o600)
        self.assertEqual(runtime.request(directory,{'action':'run','cycles':30},2)['cycle'],30)
        snapshot=self.root/'long-snapshot'
        runtime.request(directory,{'action':'snapshot','path':str(snapshot)},2)
        runtime.request(directory,{'action':'run','cycles':20},2)
        self.assertEqual(runtime.request(directory,{'action':'restore','path':str(snapshot)},2)['machine']['cycle'],30)
        self.assertEqual(runtime.request(directory,{'action':'inspect'},2)['machine']['cycle'],30)
        runtime.request(directory,{'action':'destroy'},2)
        _,stderr=child.communicate(timeout=3)
        self.assertEqual(child.returncode,0,stderr)
        self.assertFalse(private.exists(),'normal owner cleanup left its private socket directory')

    def test_ordinary_short_and_legacy_manifest_keep_the_existing_address(self):
        child,directory,metadata=self.launch('short-live')
        self.assertEqual(metadata['socket'],str(directory/'machine.sock'))
        self.assertNotIn('control',metadata)
        self.assertEqual(runtime.request(directory,{'action':'inspect'},2)['machine']['cycle'],0)
        runtime.request(directory,{'action':'destroy'},2)
        _,stderr=child.communicate(timeout=3)
        self.assertEqual(child.returncode,0,stderr)
        self.assertFalse((directory/'machine.sock').exists())

    def test_cross_session_manifest_is_rejected_before_contact(self):
        _,a,am=self.launch('a',True);_,b,bm=self.launch('b',True)
        self.assertNotEqual(am['socket'],bm['socket'])
        (a/'session.json').write_text(json.dumps(bm))
        with self.assertRaisesRegex(ValueError,'identify this session'):
            runtime.request(a,{'action':'run','cycles':40},2)
        (a/'session.json').write_text(json.dumps(am))
        self.assertEqual(runtime.request(a,{'action':'inspect'},2)['machine']['cycle'],0)
        self.assertEqual(runtime.request(b,{'action':'inspect'},2)['machine']['cycle'],0)

    def test_legacy_short_manifest_cannot_redirect_to_another_live_session(self):
        _,a,am=self.launch('legacy-a');_,b,bm=self.launch('legacy-b')
        (a/'session.json').write_text(json.dumps(bm))
        with self.assertRaisesRegex(ValueError,'Legacy control address'):
            runtime.request(a,{'action':'run','cycles':40},2)
        (a/'session.json').write_text(json.dumps(am))
        self.assertEqual(runtime.request(a,{'action':'inspect'},2)['machine']['cycle'],0)
        self.assertEqual(runtime.request(b,{'action':'inspect'},2)['machine']['cycle'],0)

    def test_stale_start_time_and_replaced_binding_reject_without_machine_change(self):
        _,directory,metadata=self.launch('stale',True)
        binding=metadata['control']
        with mock.patch.object(runtime,'process_start_ticks',return_value=binding['start_ticks']+1):
            with self.assertRaisesRegex(ValueError,'PID was reused'):
                runtime.request(directory,{'action':'run','cycles':40},2)
        private=Path(binding['directory']);owner=private/'owner.json';original=owner.read_text()
        changed={**binding,'nonce':'0'*64};owner.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'owner binding changed'):
            runtime.request(directory,{'action':'run','cycles':40},2)
        owner.write_text(original)
        os.chmod(private,0o755)
        with self.assertRaisesRegex(ValueError,'owner binding changed'):
            runtime.request(directory,{'action':'run','cycles':40},2)
        os.chmod(private,0o700)
        self.assertEqual(runtime.request(directory,{'action':'inspect'},2)['machine']['cycle'],0)

    def test_wrong_nonce_cannot_dispatch_and_fake_response_is_rejected(self):
        _,directory,metadata=self.launch('nonce',True)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as raw:
            raw.settimeout(2);raw.connect(metadata['socket'])
            raw.sendall(b'{"action":"run","cycles":40,"_control_nonce":"wrong"}\n')
            answer=json.loads(raw.recv(4096).split(b'\n')[0])
            self.assertFalse(answer['ok'])
        self.assertEqual(runtime.request(directory,{'action':'inspect'},2)['machine']['cycle'],0)
        fake=mock.MagicMock()
        fake.__enter__.return_value=fake
        fake.recv.return_value=b'{"ok":true,"result":{},"_control_nonce":"wrong"}\n'
        with mock.patch.object(runtime.socket,'socket',return_value=fake):
            with self.assertRaisesRegex(RuntimeError,'another owner'):
                runtime.request(directory,{'action':'run','cycles':40},2)
        self.assertEqual(runtime.request(directory,{'action':'inspect'},2)['machine']['cycle'],0)

    def test_failed_machine_constructor_removes_private_control_directory(self):
        directory=self.root/('failed-'+'x'*130)
        owned=self.root/'owned-control'
        def create_private(*unused,**kw):owned.mkdir(mode=0o700);return str(owned)
        class Failed:
            def __init__(self,*unused):raise RuntimeError('literal failed construction')
        from types import SimpleNamespace
        args=SimpleNamespace(session_dir=directory,disk=None,backend='rtl',mode='developer',
                             headless=True,tablet=None,paused=True,quantum=1000,restore=None)
        with mock.patch.object(runtime.tempfile,'mkdtemp',side_effect=create_private):
            with self.assertRaisesRegex(RuntimeError,'failed construction'):
                runtime.serve(args,machine_type=Failed)
        self.assertFalse(owned.exists())
        self.assertFalse((directory/'session.json').exists())

    def test_existing_session_and_foreign_socket_are_never_replaced_or_removed(self):
        directory=self.root/'existing';directory.mkdir();(directory/'sentinel').write_bytes(b'original')
        from types import SimpleNamespace
        with self.assertRaises(FileExistsError):runtime.serve(SimpleNamespace(session_dir=directory))
        self.assertEqual((directory/'sentinel').read_bytes(),b'original')
        fresh=self.root/'owned';fresh.mkdir();control=runtime.ControlSocket(fresh)
        path=Path(control.address)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as original:
            original.bind(str(path));control.bound();path.unlink()
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as foreign:
                foreign.bind(str(path));control.close()
                self.assertTrue(path.exists(),'cleanup removed a replacement socket')
                path.unlink()


if __name__=='__main__':unittest.main()
