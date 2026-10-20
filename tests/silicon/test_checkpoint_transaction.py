# SPDX-License-Identifier: Apache-2.0
"""Restore failures must preserve an interactive school's current authority."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_session as runtime


class CheckpointTransaction(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);directory=self.root/'live';directory.mkdir()
        self.events=[]
        class Machine:
            native_logical2=True
            identity={'backend':'qemu','implementation':'transaction fixture'}
            checkpoint_files={'machine.chk','clock.json','logical.tlb','durable.raw'}
            clock_hz=100000000
            def __init__(machine):machine.cycle=10;machine.directory=directory;machine.failure=None;machine.applied=[]
            def call(machine,command):
                if command.startswith('snapshot '):
                    path=Path(command[9:]);path.write_bytes(b'current VMState')
                    for name,value in [('clock.json',b'{}'),('logical.tlb',b'logical translations'),('durable.raw',b'acknowledged work')]:
                        path.with_name(name).write_bytes(value)
                return {'cycle':machine.cycle,'virtual_ns':machine.cycle*10}
            def preflight_checkpoint(machine,path,cycle):
                if machine.failure=='preflight':raise ValueError('Malformed required controller')
            def restore_checkpoint(machine,path,phase):
                self.events.append('candidate')
                machine.applied.append(path)
                # This path must own its bytes independently of the submitted
                # directory until the private candidate has completed loading.
                self.assertNotEqual(path.parent,self.source)
                self.assertEqual(path.read_bytes(),b'current VMState')
                self.assertEqual(path.with_name('durable.raw').read_bytes(),b'acknowledged work')
                self.assertEqual(self.school.binding,'current school admission')
                if machine.failure=='load':raise ValueError('Partial private candidate rejected')
                self.events.append('adopted');machine.cycle=phase//10
                return {'cycle':machine.cycle,'virtual_ns':phase}
            def close(machine):pass
        self.machine=Machine()
        self.session=runtime.Session(self.machine,directory,SimpleNamespace(mode='developer',paused=True,quantum=1000))
        self.addCleanup(self.session.close)
        self.source=self.root/'snapshot';self.session.snapshot(self.source)
        class School:
            binding='current school admission'
            def invalidate(school):self.events.append('invalidate');school.binding=None
            def close(school):pass
        self.school=School();self.session.school_service=self.school
        self.session.adapter=object()
        def disconnect():self.events.append('disconnect');self.session.adapter=None
        self.session.disconnect_adapter=disconnect
        self.session.event_cursor=9;self.session.presentation_generation=3

    def unchanged(self):
        self.assertEqual(self.machine.cycle,10)
        self.assertEqual(self.school.binding,'current school admission')
        self.assertIsNotNone(self.session.adapter)
        self.assertEqual((self.session.event_cursor,self.session.presentation_generation),(9,3))
        self.assertNotIn('invalidate',self.events);self.assertNotIn('disconnect',self.events)
        self.assertEqual(list(self.session.directory.glob('restore-inputs-*')),[])

    def test_identity_failure_keeps_school_and_adapter(self):
        manifest=self.source/'snapshot.json';data=json.loads(manifest.read_text());data['identity']={};manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'identity'):self.session.restore(self.source)
        self.unchanged();self.assertEqual(self.machine.applied,[])

    def test_controller_preflight_failure_keeps_school_and_adapter(self):
        self.machine.failure='preflight'
        with self.assertRaisesRegex(ValueError,'controller'):self.session.restore(self.source)
        self.unchanged();self.assertEqual(self.machine.applied,[])

    def test_private_partial_load_keeps_school_and_adapter(self):
        self.machine.failure='load'
        with self.assertRaisesRegex(ValueError,'private candidate'):self.session.restore(self.source)
        self.unchanged();self.assertEqual(self.events,['candidate'])

    def test_source_replacement_cannot_retarget_verified_restore(self):
        original=runtime.stage_checkpoint_inputs
        def replaced(source,manifest,destination):
            (source/'durable.raw').write_bytes(b'different history')
            return original(source,manifest,destination)
        with mock.patch.object(runtime,'stage_checkpoint_inputs',side_effect=replaced):
            with self.assertRaisesRegex(ValueError,'source changed'):self.session.restore(self.source)
        self.unchanged();self.assertEqual(self.machine.applied,[])

    def test_success_invalidates_only_after_machine_adoption(self):
        result=self.session.restore(self.source)
        self.assertEqual(self.events,['candidate','adopted','invalidate','disconnect'])
        self.assertIsNone(self.school.binding);self.assertIsNone(self.session.adapter)
        self.assertEqual((self.session.event_cursor,self.session.presentation_generation),(0,4))
        self.assertEqual(result['medium'],'isolated snapshot fork')
        self.assertEqual((self.source/'durable.raw').read_bytes(),b'acknowledged work')
        self.assertEqual(list(self.session.directory.glob('restore-inputs-*')),[])


if __name__=='__main__':unittest.main()
