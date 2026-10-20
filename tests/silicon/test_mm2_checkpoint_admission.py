"""Keep the additive MM2 transaction engine distinct from public admission."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from concurrent.futures import Future

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_fast as fast
import lemmasim_session as runtime
from lemmasim_school_service import SchoolService
loader=importlib.machinery.SourceFileLoader('mm2_checkpoint_cli',str(ROOT/'scripts/lemmasim'))
spec=importlib.util.spec_from_loader(loader.name,loader);cli=importlib.util.module_from_spec(spec);loader.exec_module(cli)

def metadata():
    return {'profile':'lemma-silicon-dev/0.14.0','execution_binding':fast.MM2_BINDING,
            'multimodal_controller_abi':2,'controller_contract':'lemma-multimodal-converter/2',
            'checkpoint_binding':fast.MM2_CHECKPOINT_BINDING,'checkpoint_contract':fast.MM2_CHECKPOINT_CONTRACT,
            'observation_relation':'lemma-native-MM2-logical-observation-relation/3','checkpoint_admitted':False,
            'sources':{'sim/host/lemma_multimodal_v2.c':'source','tooling/lemmasim/patch_soft_tlb2.py':'source'}}

class MM2CheckpointAdmission(unittest.TestCase):
    def selection(self,**changes):
        return SimpleNamespace(**({'controller_binding':'mm2-subset','checkpoint_binding':'native-mm2-logical2',
            'profile':'lemma-silicon-dev/0.14.0','command':'native-bundle-build','school_deployment':True,
            'backend':'qemu','workload':'school-notebook','mode':'student'}|changes))

    def test_explicit_selection_changes_no_student_capability(self):
        args=self.selection()
        with mock.patch.dict(os.environ,{},clear=True):
            cli.select_checkpoint_binding(args)
            self.assertEqual(os.environ['LEMMA_FAST_MM2_CHECKPOINT'],'1')
            self.assertTrue(fast.mm2_checkpoint_selected(args.profile))
            self.assertEqual(args.mode,'student')
            self.assertIn('mm2-logical2',str(fast.prepared_path(args.profile)))

    def test_wrong_controller_profile_role_is_rejected_before_environment_mutation(self):
        for change in ({'controller_binding':None},{'checkpoint_binding':'native-logical2'},
                       {'profile':'lemma-silicon-dev/0.16.0'},{'school_deployment':False},
                       {'command':'build','backend':'rtl'},{'command':'build','workload':'service'}):
            with self.subTest(change=change),mock.patch.dict(os.environ,{},clear=True):
                with self.assertRaises(cli.Failure):cli.select_checkpoint_binding(self.selection(**change))
                self.assertEqual(dict(os.environ),{})

    def test_old_mm2_selection_remains_separate(self):
        with mock.patch.dict(os.environ,{'LEMMA_FAST_MM2_CHECKPOINT':'1'},clear=True):
            cli.select_checkpoint_binding(self.selection(checkpoint_binding=None))
            self.assertNotIn('LEMMA_FAST_MM2_CHECKPOINT',os.environ)
            self.assertNotIn('mm2-logical2',str(fast.prepared_path('lemma-silicon-dev/0.14.0')))

    def test_required_versioned_engine_metadata(self):
        self.assertTrue(fast.validate_execution_binding(metadata()))
        self.assertTrue(fast.validate_checkpoint_binding(metadata()))
        for change in ({'checkpoint_binding':fast.LOGICAL2_BINDING},{'multimodal_controller_abi':1},
                       {'checkpoint_contract':'other'},{'observation_relation':'other'},
                       {'checkpoint_admitted':1},{'checkpoint_admitted':True},
                       {'sources':{'sim/host/lemma_multimodal_v2.c':'source'}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                fast.validate_checkpoint_binding(metadata()|change)
        admitted=metadata();admitted['checkpoint_admitted']=True
        admitted['sources']['scripts/native_logical_relation.py']='current maintained relation'
        self.assertTrue(fast.validate_checkpoint_binding(admitted))

    def test_default_mm2_and_legacy_logical2_metadata_are_unchanged(self):
        data=metadata()
        for key in ('checkpoint_binding','checkpoint_contract','observation_relation','checkpoint_admitted'):data.pop(key)
        self.assertTrue(fast.validate_execution_binding(data))
        self.assertFalse(fast.validate_checkpoint_binding(data))
        self.assertTrue(fast.validate_checkpoint_binding({'profile':'lemma-silicon-dev/0.14.0',
            'checkpoint_binding':fast.LOGICAL2_BINDING,'sources':{'tooling/lemmasim/patch_soft_tlb2.py':'source'}}))

    def test_guard_rejects_before_snapshot_or_candidate_side_effects(self):
        machine=fast.Fast.__new__(fast.Fast);machine.data=metadata();machine.mm2_subset=True
        machine.native_logical2=True;machine.companion=None;machine.qmp=mock.Mock()
        with self.assertRaisesRegex(ValueError,'not publicly admitted'):machine.call('snapshot unused')
        with self.assertRaisesRegex(ValueError,'not publicly admitted'):machine.restore_checkpoint(Path('unused'))
        machine.qmp.execute.assert_not_called()
        # A coherently edited archive flag alone cannot bypass the code guard.
        machine.data['checkpoint_admitted']=True
        with mock.patch.object(fast,'MM2_CHECKPOINT_ADMITTED',False):
            with self.assertRaisesRegex(ValueError,'not publicly admitted'):machine.checkpoint_admission()

    def test_ordinary_session_guard_precedes_destination_and_manifest_access(self):
        machine=fast.Fast.__new__(fast.Fast);machine.data=metadata();machine.mm2_subset=True
        machine.native_logical2=True;machine.companion=None;machine.qmp=mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            session=runtime.Session(machine,root,SimpleNamespace(mode='student',paused=True,quantum=1000))
            try:
                with self.assertRaisesRegex(ValueError,'not publicly admitted'):session.snapshot(root/'unused')
                self.assertFalse((root/'unused').exists())
                with self.assertRaisesRegex(ValueError,'not publicly admitted'):session.restore(root/'absent')
                self.assertEqual((session.event_cursor,session.presentation_generation),(0,0))
                machine.qmp.execute.assert_not_called()
            finally:session.capture.close()

    def test_future_admission_still_requires_archived_permission_and_local_backing(self):
        machine=fast.Fast.__new__(fast.Fast);machine.data=metadata();machine.mm2_subset=True
        machine.native_logical2=True;machine.companion=None
        machine.get=mock.Mock(return_value=json.dumps({'controller_abi':2,'ring':{'held_kind':2,'held_cancel':0}}))
        with mock.patch.object(fast,'MM2_CHECKPOINT_ADMITTED',True):
            with self.assertRaisesRegex(ValueError,'not publicly admitted'):machine.checkpoint_admission()
            machine.data['checkpoint_admitted']=True;machine.checkpoint_admission()
            machine.companion=object()
            with self.assertRaisesRegex(ValueError,'externalcompanion'):machine.checkpoint_admission()

    def test_cancelled_held_read_and_unknown_observations_remain_unsupported(self):
        for state in ({}, {'controller_abi':1,'ring':{'held_kind':2,'held_cancel':0}},
                      {'controller_abi':2,'ring':{'held_kind':2}},
                      {'controller_abi':2,'ring':{'held_kind':2,'held_cancel':True}},
                      {'controller_abi':2,'ring':{'held_kind':2,'held_cancel':1}}):
            with self.subTest(state=state),self.assertRaises(ValueError):fast.validate_mm2_checkpoint_cut(state)
        for kind in (0,1,2):fast.validate_mm2_checkpoint_cut({'controller_abi':2,'ring':{'held_kind':kind,'held_cancel':0}})

    def test_unsupported_current_capture_does_not_prevent_safe_restore(self):
        machine=fast.Fast.__new__(fast.Fast);machine.data=metadata();machine.data['checkpoint_admitted']=True
        machine.mm2_subset=True;machine.native_logical2=True;machine.companion=None
        machine.get=mock.Mock(return_value=json.dumps({'controller_abi':2,'ring':{'held_kind':2,'held_cancel':1}}))
        with mock.patch.object(fast,'MM2_CHECKPOINT_ADMITTED',True):
            machine.checkpoint_admission()
            machine.get.assert_not_called()
            with self.assertRaisesRegex(ValueError,'cancelled held-read'):machine.checkpoint_capture_admission()

    def test_detached_school_rejects_late_completed_authority_job(self):
        service=SchoolService(SimpleNamespace())
        future=Future();future.set_running_or_notify_cancel()
        service.connection=('http://127.0.0.1:1/v1/client','fixture-token')
        service.binding='old binding';service.review='old review'
        service.jobs['late']={'status':'pending','operation':'join','epoch':service.epoch,
                              'binding':'old binding','future':future}
        service.admit=mock.Mock()
        try:
            service.invalidate()
            future.set_result({'package_hex':'must never enter the restored guest'})
            service.pump()
            self.assertIsNone(service.connection);self.assertIsNone(service.binding);self.assertIsNone(service.review)
            self.assertEqual(service.jobs['late']['status'],'failed')
            self.assertIn('epoch changed',service.jobs['late']['error'])
            service.admit.assert_not_called()
        finally:service.close()

if __name__=='__main__':unittest.main()
