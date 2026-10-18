"""Raw button admission stays distinct from guest power policy."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_session as session
import lemmasim_fast as fast

class PowerTransport(unittest.TestCase):
    def test_raw_level_capture_without_host_suspend_or_reset(self):
        class Machine:
            identity={'backend':'literal button transport fixture'}
            input_kinds={'pen','button'}
            def __init__(self):self.commands=[]
            def call(self, command):self.commands.append(command);return {'cycle':100,'ticks':10}
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            machine=Machine(); owner=session.Session(machine,Path(directory),
                SimpleNamespace(mode='developer',paused=True,quantum=1000))
            try:
                owner.dispatch({'action':'inject','kind':'button','level':1,'cycle':123})
                owner.dispatch({'action':'inject','kind':'button','level':0,'cycle':123})
                self.assertEqual([c for c in machine.commands if c!='inspect'],
                                 ['inject 123 button 1','inject 123 button 0'])
                rows=[json.loads(row) for row in (Path(directory)/'external.jsonl').read_text().splitlines()]
                self.assertEqual([(r['admission'],r['request']['level'],r['request']['cycle']) for r in rows],
                                 [('applied',1,123),('applied',0,123)])
            finally:owner.close()

    def test_bad_level_and_legacy_profile_reject_before_admission(self):
        for level in (-1,2,True,None):
            with self.subTest(level=level),self.assertRaises(ValueError):
                session.external_command({'action':'inject','kind':'button','level':level},100)
        class Machine:
            identity={'backend':'literal legacy fixture'}; input_kinds={'pen'}
            def __init__(self):self.commands=[]
            def call(self, command):self.commands.append(command);return {'cycle':100,'ticks':10}
            def close(self):pass
        with tempfile.TemporaryDirectory() as directory:
            machine=Machine();owner=session.Session(machine,Path(directory),
                SimpleNamespace(mode='developer',paused=True,quantum=1000))
            try:
                with self.assertRaisesRegex(ValueError,'unsupported'):
                    owner.dispatch({'action':'inject','kind':'button','level':1})
                self.assertEqual(machine.commands,['inspect'])
                self.assertEqual((Path(directory)/'external.jsonl').read_bytes(),b'')
            finally:owner.close()

    def test_fast_translates_only_delivery_clock_and_raw_level(self):
        class QMP:
            def __init__(self):self.commands=[]
            def execute(self,*arguments):self.commands.append(arguments)
        machine=object.__new__(fast.Fast);machine.qmp=QMP()
        machine.data={'profile':'lemma-silicon-dev/0.3.0'}
        machine.input_kinds={'pen','button'};machine.time_origin_ns=1000;machine.clock_hz=100000000
        machine.get=lambda name:'200';machine.inspect=lambda:{'cycle':130}
        machine.call('inject 130 button 1')
        self.assertEqual(machine.qmp.commands,[('qom-set',{'path':'/machine/lemma-hardware',
            'property':'external-button','value':'300 1'})])

if __name__ == '__main__':unittest.main()
