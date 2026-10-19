"""Host-only negative tests for exact artifact and controller access authority.

These small hand-authored IR fixtures test observer rejection, never compiler or
guest execution. Genuine target exports are required to install production pins.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import multimodal_target as target
from core0_common import Core0Error

class TargetAuthorityTests(unittest.TestCase):
    def fixture(self):
        row = {'source':'Lemma.Services.Store.ServerAwait.main', 'symbol':'lemma_user_store_main', 'args':['u64'], 'effects':[]}
        unit = {'configuration':target.CONFIGURATIONS[0], 'role':'user', 'image_key':'store', 'image_id':1,
                'contract_version':'core0-user-v0.1', 'software_deployment':target.SOFTWARE_DEPLOYMENT,
                'functions':[row], 'roots':[{'source':row['source'], 'symbol':row['symbol'], 'id':1, 'args':['u64']}],
                'used_device_ops':[], 'used_execution_ops':[], 'used_loops':[]}
        ir = 'define { i64, i64 } @lemma_user_store_main(i64 %arg0) {\nentry:\n  ret { i64, i64 } zeroinitializer\n}\n'
        return unit, ir
    def pins(self, unit, ir):
        body = target.complete(ir, unit)
        pin = {'catalog_sha256':target.digest(unit), 'pre':{'function_count':1, 'sha256':target.digest(body)},
               'post':{'function_count':1, 'sha256':target.digest(body)}}
        return {'schema':target.VERSION, 'configurations':{
            configuration:{role:copy.deepcopy(pin) for role in target.ROLES}
            for configuration in target.CONFIGURATIONS}}
    def test_missing_authority_never_passes(self):
        unit, ir = self.fixture()
        with tempfile.TemporaryDirectory() as directory, patch.object(target, 'AUTHORITY', Path(directory)/'absent.json'):
            with self.assertRaisesRegex(Core0Error, 'authority unavailable'): target.validate(ir,unit,optimized=False)
    def test_changed_body_catalog_literal_and_empty_role_inventory_reject(self):
        unit, ir = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            authority = Path(directory)/'pins.json'; authority.write_text(json.dumps(self.pins(unit,ir)))
            with patch.object(target,'AUTHORITY',authority):
                self.assertEqual(target.validate(ir,unit,optimized=False)['function_count'],1)
                for mutation in (ir.replace('zeroinitializer','{ i64 7, i64 0 }'),
                                 '@extra = private unnamed_addr constant [1 x i64] [i64 5], align 8\n'+ir):
                    with self.subTest(mutation=mutation), self.assertRaisesRegex(Core0Error,'bodies/globals/callers differ'):
                        target.validate(mutation,unit,optimized=False)
                changed=copy.deepcopy(unit);changed['functions'][0]['effects']=['checked-access']
                with self.assertRaisesRegex(Core0Error,'catalog differs'):target.validate(ir,changed,optimized=False)
                data=self.pins(unit,ir);data['configurations'][unit['configuration']].pop('course')
                authority.write_text(json.dumps(data))
                with self.assertRaisesRegex(Core0Error,'role inventory'):target.validate(ir,unit,optimized=False)
    def test_unknown_profile_or_source_cannot_acquire_multimodal_authority(self):
        unit, ir=self.fixture()
        unit['configuration']='historical-profile'
        for source in ('Lemma.User.Multimodal.inject',
                       'Lemma.Kernel.Memory.AddressSpace.addMultimodalAliases',
                       'Lemma.Kernel.Process.initMultimodal',
                       target.PREFIX+'constructCourseMultimodal'):
            unit['functions'][0]['source']=source
            with self.subTest(source=source),self.assertRaisesRegex(Core0Error,'escaped its exact deployment'):
                target.validate(ir,unit,optimized=False)
    def test_wrong_user_identifier_root_or_device_privilege_rejects(self):
        unit,_=self.fixture()
        for key,value in (('image_id',2),('contract_version','core0-user-v0.2'),('used_device_ops',[{'pretend':'mmio'}])):
            changed=copy.deepcopy(unit);changed[key]=value
            with self.subTest(key=key),self.assertRaises(Core0Error):target.catalog(changed)
    def test_v8_borrows_only_the_v7_copied_request_engine(self):
        unit,_=self.fixture()
        unit.update(image_key='arithmetic',image_id=3,contract_version='core0-user-v0.7')
        source='Lemma.Services.Arithmetic.ServerV8.main'
        unit['functions'][0]['source']=source;unit['roots'][0]['source']=source
        unit['functions'].append({'source':'Lemma.Services.Arithmetic.ServerV7.processCopied',
                                 'symbol':'lemma_user_arithmetic_copy','args':['u64','u64'],'effects':[]})
        target.catalog(unit)
        for suffix in ('main','step','pressureStep','unknownExecutable'):
            changed=copy.deepcopy(unit);changed['functions'][1]['source']='Lemma.Services.Arithmetic.ServerV7.'+suffix
            with self.subTest(suffix=suffix),self.assertRaisesRegex(Core0Error,'another V7 executable'):
                target.catalog(changed)
        changed=copy.deepcopy(unit);changed.update(image_key='store',image_id=1,contract_version='core0-user-v0.1')
        with self.assertRaisesRegex(Core0Error,'isolated role'):target.catalog(changed)
    def test_structural_export_does_not_bootstrap_itself_from_ir_pins(self):
        import package_notebook_target,dirty_batch_notebook_target
        unit,_=self.fixture();source=target.NOTEBOOK_ROOT
        unit.update(image_key='notebook',image_id=2,contract_version='core0-user-v0.2')
        unit['functions'][0]['source']=source;unit['roots'][0]['source']=source
        unit['used_execution_ops']=[{'stable_id':'execution.'+suffix} for suffix in
            ('virtual-read8','virtual-read64','virtual-write8','virtual-write64','syscall')]
        unit['used_loops']=[{'stable_id':'action.loop','callback':'Lemma.Applications.Notebook.multimodalStep'}]
        with tempfile.TemporaryDirectory() as directory,patch.object(target,'AUTHORITY',Path(directory)/'absent.json'):
            self.assertEqual(package_notebook_target.contract(unit)['root'],source)
            self.assertEqual(dirty_batch_notebook_target.numeric_contract(unit)[1]['package_notebook_version'],21)
            with self.assertRaisesRegex(Core0Error,'authority unavailable'):target.validate('',unit,optimized=False)

class NotebookSafetySourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = tuple((ROOT/path).read_text() for path in (
            'Lemma/User/Multimodal.lean','Lemma/Applications/Notebook.lean','Lemma/Notebook/ControlBacklog.lean'))

    def reject(self, source_index, before, after, message):
        changed = list(self.sources)
        self.assertIn(before, changed[source_index])
        changed[source_index] = changed[source_index].replace(before, after, 1)
        with self.assertRaisesRegex(Core0Error,message): target.notebook_safety_sources(*changed)

    def test_reviewed_current_layout_and_idle_safety_routes(self):
        result=target.notebook_safety_sources(*self.sources)
        self.assertEqual((result['allocated_page'],result['page_bytes']),(0x340000,4096))
        self.assertEqual(result['historical_backlog'],[0x20d00,0x20f20])
        self.assertEqual(len(result['disjoint_windows']),7)

    def test_collision_and_outside_page_consumers_reject(self):
        for before,after in (('records + 2048','0x20d00'),('records + 2304','records + 2048'),
                             ('0x340000','0x20d00'),('records + 2304','records + 4096')):
            with self.subTest(after=after):self.reject(0,before,after,'layout')
        self.reject(1,'Multimodal.records + 1536','Multimodal.records + 1024','layout')

    def test_allocation_failure_address_and_clear_order_reject(self):
        self.reject(0,'Syscall.allocatePage records','Syscall.allocatePage state','allocation')
        self.reject(0,'if mmDifferent address records = true then .done 95 0 else',
                    'if mmDifferent address records = false then .done 95 0 else','allocation')
        self.reject(0,'.bind (Syscall.allocatePage records) fun s address =>',
                    '.bind (put 0 0) fun _ _ => .bind (Syscall.allocatePage records) fun s address =>','allocation')

    def test_safety_cannot_render_before_owned_framebuffer_returns(self):
        start='private def multimodalSafety (operation : UInt64) : Action :=\n'
        self.reject(1,start,start+'  .bind multimodalBar fun _ _ =>\n','framebuffer')
        self.reject(1,'if stroke ||| store ||| checking = 0 then if dirtyX = 0xffff then',
                    'if stroke ||| store ||| checking = 1 then if dirtyX = 0xffff then','ownership')
        self.reject(1,'if status &&& 1 = 0 then\n    .bind multimodalBar',
                    'if status &&& 1 = 1 then\n    .bind multimodalBar','ownership')

    def test_busy_queue_contact_and_loss_shortcuts_reject(self):
        self.reject(1,'multimodalSafety (if safetyX < 640 then 1 else 2)',
                    'queueBookTap x y','precede busy')
        start=self.sources[1].index('private def multimodalInputSample')
        changed=self.sources[1][:start]+self.sources[1][start:].replace(
            'if different active 0 = true then appendRaw else\n    if flags',
            'if different active 0 = true then .done 0 0 else\n    if flags',1)
        with self.assertRaisesRegex(Core0Error,'raw-stroke'):
            target.notebook_safety_sources(self.sources[0],changed,self.sources[2])
        start=self.sources[1].index('private def drainMultimodalInput')
        changed=self.sources[1][:start]+self.sources[1][start:].replace(
            'if s = 175 then','if s = 176 then',1)
        with self.assertRaisesRegex(Core0Error,'lost-contact'):
            target.notebook_safety_sources(self.sources[0],changed,self.sources[2])

    def test_tutor_intent_retention_and_dispatch_boundaries_reject(self):
        self.reject(1,'multimodalQueueTutor (if safetyX < 928 then 3 else if safetyX < 1024 then 4 else 5)',
                    'queueBookTap x y','retention')
        self.reject(1,'Memory.write64 (tutorState + 16) operation',
                    '.done 0 0','retain/coalesce')
        self.reject(1,'if stroke ||| rawCount ||| rawPending ||| store ||| checking = 0 then',
                    'if stroke ||| rawCount ||| rawPending ||| store ||| checking = 1 then','dispatch')
        self.reject(1,'.bind (Memory.write64 (tutorState + 16) 0) fun s _ =>',
                    '.bind (.done 0 0) fun s _ =>','exact-once')

    def test_toolbar_requires_every_intersected_tile_and_width_guard(self):
        # x400..1119 and y132..146 intersect exactly row4, columns12..34.
        columns = set(x // 32 for x in range(400,1120))
        rows = set(y // 32 for y in range(132,147))
        self.assertEqual((rows, columns), ({4},set(range(12,35))))
        for before,after in (
            ('if width < 1120 then .done 16 0 else','if width < 624 then .done 16 0 else'),
            ('.boundedFoldU64 23 multimodalBarTile 23','.boundedFoldU64 1 multimodalBarTile 1'),
            ('4 * ((width + 31) / 32) + 12 + i.toUInt64','3 * ((width + 31) / 32) + 12 + i.toUInt64'),
            ('4 * ((width + 31) / 32) + 12 + i.toUInt64','4 * ((width + 31) / 32) + 13 + i.toUInt64'),
            ('4 * ((width + 31) / 32) + 12 + i.toUInt64','4 * ((width + 31) / 32) + 12')):
            with self.subTest(after=after):self.reject(1,before,after,'source toolbar')

    def test_active_capture_inhibition_cannot_start_or_wait_for_busy_queue(self):
        for before,after in (
            ('if different captureActive 0 = true then multimodalSafety 0 else',
             'if different captureActive 0 = false then multimodalSafety 0 else'),
            ('if different captureActive 0 = true then multimodalSafety 0 else',
             'if different captureActive 0 = true then multimodalControl 0 else'),
            ('if 400 ≤ safetyX then if safetyX < 544 then Lemma.User.Multimodal.active',
             'if 400 ≤ safetyX then if safetyX < 640 then Lemma.User.Multimodal.active'),
            ('if 400 ≤ safetyX then if safetyX < 544 then Lemma.User.Multimodal.active',
             'if 400 ≤ safetyX then if safetyX < 544 then .done 0 1')):
            with self.subTest(after=after):self.reject(1,before,after,'source CAPTURE')

    def test_chooser_load_retains_exact_page_publication_and_cancels_stale_request(self):
        for before,after in (
            ('      multimodalQueueBookLoad\n','      .done 0 0\n'),
            ('Memory.write64 (tutorState + 40) identity','Memory.write64 (tutorState + 40) 0'),
            ('if course = 1 then if page = expectedPage then if identity = expectedIdentity then if edition = expectedEdition then',
             'if course = 1 then if page = page then if identity = expectedIdentity then if edition = expectedEdition then'),
            ('if edition = expectedEdition then\n    packageControlPress',
             'if edition = edition then\n    packageControlPress')):
            with self.subTest(after=after):self.reject(1,before,after,'source (?:chooser|queued chooser) LOAD')

    def test_rejected_text_releases_only_its_presentation_work_before_error(self):
        self.reject(1,'private def multimodalAbandonPresentation : Action :=\n  .bind (packagePut 72 0)',
                    'private def multimodalAbandonPresentation : Action :=\n  .bind (packagePut 72 1)',
                    'source rejected view')
        self.reject(1,'.bind multimodalAbandonPresentation fun cleanup _ =>',
                    '.bind (.done 0 0) fun cleanup _ =>','source rejected view')

    def test_explicit_envelope_does_not_inherit_original_reader_crc_or_node(self):
        before='''  .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 176 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (beginPackageRead 60001 sequence)'''
        self.reject(1,before,before.replace('packagePut 160 0','packagePut 160 1'),'source school envelope')

class ReadonlyGuardTests(unittest.TestCase):
    def fixture(self):
        unit={'functions':[{'source':'Lemma.Fixture.lookup','symbol':'lemma_lookup','args':['u64'],'effects':[]}], 'role':'kernel'}
        ir='''@switch.table.lemma_lookup = private unnamed_addr constant [2 x i64] [i64 3, i64 5], align 8

define i64 @lemma_lookup(i64 %arg0) {
entry:
  %bound = icmp ult i64 %arg0, 2
  br i1 %bound, label %lookup, label %done
lookup:
  %pointer = getelementptr inbounds nuw [2 x i64], ptr @switch.table.lemma_lookup, i64 0, i64 %arg0
  %sample = load i64, ptr %pointer, align 8
  br label %done
done:
  %result = phi i64 [ 0, %entry ], [ %sample, %lookup ]
  ret i64 %result
}
'''
        return unit,ir
    def test_bound_is_independent_of_complete_body_pin(self):
        unit,ir=self.fixture()
        with patch.object(target,'validate',return_value={'pinned_fixture':True}):
            sites,tables,_=target.readonly_lookup(ir,unit,optimized=True)
            self.assertEqual(len(sites),1);self.assertEqual(tables[0]['values'],[3,5])
            for changed in (ir.replace('icmp ult i64 %arg0, 2','icmp ule i64 %arg0, 2'),
                            ir.replace('br i1 %bound, label %lookup, label %done','br i1 %bound, label %done, label %lookup'),
                            ir.replace('align 8','align 4',1),
                            ir.replace('ret i64 %result','ret i64 ptrtoint (ptr @switch.table.lemma_lookup to i64)')):
                with self.subTest(changed=changed), self.assertRaises(Core0Error):target.readonly_lookup(changed,unit,optimized=True)
    def test_cfg_comments_switch_bypass_and_poison_are_checked(self):
        unit,ir=self.fixture()
        commented=ir.replace('lookup:','lookup: ; preds = %entry').replace('done:','done: ; preds = %lookup, %entry')
        with patch.object(target,'validate',return_value={'pinned_fixture':True}):
            self.assertEqual(len(target.readonly_lookup(commented,unit,optimized=True)[0]),1)
            bypass=ir.replace('entry:\n','entry:\n  switch i64 %arg0, label %check [\n    i64 7, label %lookup\n  ]\ncheck:\n')
            with self.assertRaisesRegex(Core0Error,'dominating exact unsigned'):target.readonly_lookup(bypass,unit,optimized=True)
            poisoned=ir.replace('[i64 3, i64 5]','[i64 3, i64 poison]')
            with self.assertRaisesRegex(Core0Error,'poison holes'):target.readonly_lookup(poisoned,unit,optimized=True)

if __name__=='__main__':unittest.main()
