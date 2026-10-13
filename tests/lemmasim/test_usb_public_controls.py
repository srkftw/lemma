# Host contract negatives; real controller/suffix execution is separately qualified.
import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_session as runtime

class Observed:
    def __init__(self,backend='rtl',profile='lemma-silicon-dev/0.6.0'):
        self.identity={'backend':backend,'profile':profile};self.commands=[]
    def call(self,line):self.commands.append(line);return {'cycle':17}
    def close(self):pass

class PublicUSBControls(unittest.TestCase):
    def session(self,root,mode='developer',backend='rtl',profile='lemma-silicon-dev/0.6.0'):
        directory=root/str(len(list(root.iterdir())));directory.mkdir();machine=Observed(backend,profile)
        session=runtime.Session(machine,directory,SimpleNamespace(mode=mode,paused=True,quantum=1000));self.addCleanup(session.close)
        return session,machine,directory
    def test_mode_backend_profile_and_path_reject_before_machine(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            for mode,backend,profile in [('student','rtl','lemma-silicon-dev/0.6.0'),('developer','qemu','lemma-silicon-dev/0.6.0'),('laboratory','rtl','lemma-silicon-dev/0.5.0')]:
                session,machine,_=self.session(root,mode,backend,profile)
                for action in ('usb-outcomes','export-usb-replay'):
                    with self.assertRaises(ValueError):session.dispatch({'action':action,'path':str(root/'tape')})
                self.assertEqual(machine.commands,[])
            session,machine,_=self.session(root)
            with self.assertRaises(ValueError):session.dispatch({'action':'usb-outcomes','path':'bad\nrun 1'})
            self.assertEqual(machine.commands,[])
    def test_tape_binding_is_not_raw_guest_input(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);session,machine,directory=self.session(root)
            for action in ('usb-outcomes','export-usb-replay'):session.dispatch({'action':action,'path':str(root/'tape')})
            self.assertEqual(machine.commands,['usb-outcomes '+str(root/'tape'),'export-usb-replay '+str(root/'tape')])
            self.assertEqual((session.event_cursor,session.event_count),(0,0));self.assertEqual((directory/'external.jsonl').read_bytes(),b'')
    def test_only_usb6_admits_container6(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);path=root/'state';identity='0'*64
            header=b'LMSSRTL1'+(6).to_bytes(8,'little')+identity.encode()+(16).to_bytes(8,'little')+(1).to_bytes(8,'little')+bytes(16)+bytes(8)+(17).to_bytes(8,'little')+b'x'
            path.write_bytes(header);machine=runtime.RTL.__new__(runtime.RTL);machine.identity={'profile':'lemma-silicon-dev/0.6.0'};machine.checkpoint_identity=identity
            machine.preflight_checkpoint(path,17)
            for profile in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.4.0','lemma-silicon-dev/0.5.0'):
                machine.identity={'profile':profile}
                with self.assertRaises(ValueError):machine.preflight_checkpoint(path,17)
