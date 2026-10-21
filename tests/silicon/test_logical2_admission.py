# SPDX-License-Identifier: Apache-2.0
"""The public selector must preserve profile, role and external-owner boundaries."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_fast as fast
loader=importlib.machinery.SourceFileLoader('logical2_native_cli',str(ROOT/'scripts/lemmasim'))
spec=importlib.util.spec_from_loader(loader.name,loader);cli=importlib.util.module_from_spec(spec);loader.exec_module(cli)

class Logical2Admission(unittest.TestCase):
    def selection(self,**changes):
        return SimpleNamespace(**({'checkpoint_binding':'native-logical2','profile':'lemma-silicon-dev/0.14.0','command':'native-bundle-build','school_deployment':True,'backend':'qemu','workload':'school-notebook'}|changes))

    def test_default_does_not_select_another_runtime(self):
        with mock.patch.dict(os.environ,{},clear=True):
            cli.select_checkpoint_binding(self.selection(checkpoint_binding=None))
            self.assertNotIn('LEMMA_FAST_LOGICAL2',os.environ)
            self.assertNotIn('LEMMA_FAST_RAW_UART',os.environ)

    def test_wrong_profile_backend_or_role_is_transactional(self):
        cases=[{'profile':'lemma-silicon-dev/0.15.0'}, {'command':'build','backend':'rtl'}, {'command':'build','workload':'service'}, {'school_deployment':False}]
        for changes in cases:
            with self.subTest(changes=changes),mock.patch.dict(os.environ,{},clear=True):
                with self.assertRaises(cli.Failure):cli.select_checkpoint_binding(self.selection(**changes))
                self.assertNotIn('LEMMA_FAST_LOGICAL2',os.environ)
                self.assertNotIn('LEMMA_FAST_RAW_UART',os.environ)

    def test_packaged_selection_does_not_change_actor_or_mode(self):
        args=self.selection();args.mode='student';args.actor='learner'
        with mock.patch.dict(os.environ,{},clear=True):
            cli.select_checkpoint_binding(args)
            self.assertEqual(os.environ['LEMMA_FAST_LOGICAL2'],'1')
            self.assertEqual(os.environ['LEMMA_FAST_RAW_UART'],'1')
            self.assertEqual((args.mode,args.actor),('student','learner'))

    def test_default_and_external_backing_still_cannot_checkpoint(self):
        machine=fast.Fast.__new__(fast.Fast);machine.data={'profile':'lemma-silicon-dev/0.14.0'}
        machine.native_logical2=False;machine.companion=None
        with self.assertRaisesRegex(ValueError,'unsupported'):machine.checkpoint_admission()
        machine.native_logical2=True;machine.companion=object()
        with self.assertRaisesRegex(ValueError,'externalcompanion'):machine.checkpoint_admission()
        machine.companion=None;machine.checkpoint_admission()

    def test_binding_requires_exact_profile_and_controller_source(self):
        valid={'checkpoint_binding':fast.LOGICAL2_BINDING,'profile':'lemma-silicon-dev/0.14.0','sources':{'tooling/lemmasim/patch_soft_tlb2.py':'source'}}
        self.assertTrue(fast.validate_checkpoint_binding(valid))
        for change in [{'checkpoint_binding':'lemma-silicon-fast-softtlb/0.1.0'},{'profile':'lemma-silicon-dev/0.15.0'},{'sources':{}}]:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'binding/source'):fast.validate_checkpoint_binding(valid|change)

if __name__=='__main__':unittest.main()
