"""Consequential source observer negatives; not compiler or guest execution."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
import school_reduction_target as target


class ReductionSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.values={key:(ROOT/name).read_text() for key,name in target.COMPONENTS.items()}

    def reject(self,key,before,after):
        self.assertIn(before,self.values[key],'scoped mutation anchor missing')
        changed=dict(self.values);changed[key]=changed[key].replace(before,after,1)
        with self.assertRaises(Core0Error):target.sources(changed)

    def test_current_source_has_closed_mode_phases_and_disjoint_IO(self):
        result=target.sources(self.values)
        self.assertEqual((result['mode'],result['legacy_School_mode'],result['enabled_offset']),(2,1,728))
        self.assertEqual(result['phases'],[16,17,18,19])
        for index,(_,left,length) in enumerate(result['IO_windows']):
            self.assertLessEqual(left+length,4096)
            for _,right,size in result['IO_windows'][index+1:]:self.assertTrue(left+length<=right or right+size<=left)

    def test_startup_mode_and_partial_removal_cannot_downgrade(self):
        for before,after in (
            ('mainMultimodalConfigured bootArgument 2','mainMultimodalConfigured bootArgument 1'),
            ('Memory.write64 reductionEnabled (if school = 2 then 1 else 0)','Memory.write64 reductionEnabled 1'),
            ('Memory.write64 schoolActivityFlag (if school = 2 then 1 else school)','Memory.write64 schoolActivityFlag school'),
            ('private def configureSchoolMode','private def renamedConfigureSchoolMode'),
            ('Memory.write64 (state+728) 0','Memory.write64 (state+728) 1')):
            with self.subTest(before=before):self.reject('notebook',before,after)

    def test_scratch_layout_raster_and_control_are_exact(self):
        for before,after in (
            ('mathematicsIO+512','mathematicsIO+256'),('mathematicsIO+640','mathematicsIO+4096'),
            ('state+728','state+768'),('Memory.read64 (reductionMeta+offset)','Memory.read64 (mathematicsIO+offset)'),
            ('.boundedFoldU64 1080 reductionBarStep 1080','.boundedFoldU64 1081 reductionBarStep 1081'),
            ('if operation = 10 then beginLocalReduction','if operation = 10 then .done 0 0')):
            with self.subTest(before=before):self.reject('notebook',before,after)

    def test_store_frontier_and_current_work_precede_endpoint_call(self):
        for before,after in (
            ('if floor < frontier then','if floor ≤ frontier then'),
            ('if pending ||| status = 0 then','if pending = 0 then'),
            ('reductionPut 8 frontier','reductionPut 8 0'),
            ('put 536 16','put 536 17'),
            ('LocalReduction.current packageWorkspace mathematics mathematicsIO reductionEvent ns page','LocalReduction.current packageWorkspace mathematics mathematicsIO reductionEvent 1 1')):
            with self.subTest(before=before):self.reject('notebook',before,after)

    def test_cancel_and_ink_settle_owned_pending_IPC(self):
        for before,after in (
            ('if (if phase = 1 then true else phase = 17) = true then','if phase = 1 then'),
            ('if phase = 17 then Lemma.Services.Arithmetic.ClientV9.pollCall','if phase = 17 then pollArithmetic'),
            ('if 16 ≤ phase then if phase ≤ 19 then true else false else false','if 16 ≤ phase then false else false')):
            with self.subTest(before=before):self.reject('notebook',before,after)

    def test_service_envelope_and_client_echo_are_required(self):
        for key,before,after in (
            ('protocol','def requestBytes : UInt64 := 144','def requestBytes : UInt64 := 136'),
            ('protocol','if reserved0 ||| reserved1 = 0 then','if reserved0 = 0 then'),
            ('server','if submission = request then ProtocolV9.evaluate payload','if submission = request then ProtocolV9.evaluate ServerV7.outgoing'),
            ('client','.boundedFoldU64 18 echoStep 18','.boundedFoldU64 17 echoStep 17'),
            ('client','if actual = expected then .done 0 acc','if actual = actual then .done 0 acc'),
            ('client','if identity = ProtocolV9.serviceIdentity then','if identity = 0 then'),
            ('client','if kind = IPCABI.replyKind then','if kind = IPCABI.requestKind then'),
            ('client','if (if sender = 0 then false else true) = true then','if sender = 0 then'),
            ('client','if authority = 0 then','if authority = authority then'),
            ('client','Syscall.call 67 transaction incoming','Syscall.call 67 1 incoming')):
            with self.subTest(key=key,before=before):self.reject(key,before,after)

    def test_service_context_cannot_acquire_arbitrary_object_or_source(self):
        for before,after in (
            ('if 2 < ns then false','if 2 < ns then true'),
            ('if 64 < page then false','if 64 < page then true'),
            ('if object = (0x504b000000000000 ||| page) then','if object = object then'),
            ('if request = 0 then false','if request = 0 then true'),
            ('if source = 60001 then false','if source = 60001 then true'),
            ('if edition = 0 then false','if edition = 0 then true'),
            ('if 16 < node then false','if 16 < node then true'),
            ('if policy = 0 then false else true','if policy = 0 then true else true')):
            with self.subTest(before=before):self.reject('protocol',before,after)

    def test_full_work_and_source_CRC_binding_remain_required(self):
        for before,after in (
            ('same document 40 request 56','same document 40 request 40'),
            ('same document 56 request 80','same document 56 request 88'),
            ('same (workspace+PackageWorkspace.selection) 32 event 64','same (workspace+PackageWorkspace.selection) 32 request 64'),
            ('(current workspace document request event ns page)','(current workspace document request event 1 1)'),
            ('Mathematics.applyLocalTool stagedDocument event','Mathematics.copyCurrent stagedDocument event')):
            with self.subTest(before=before):self.reject('local',before,after)

    def test_application_keeps_revision_and_numeric_limits(self):
        for key,before,after in (
            ('math','if expected = revision then if goal = 1 then if n = oldN then if d = oldD then','if expected = revision then if goal = 1 then if n = oldN then if d = d then'),
            ('reduction','.boundedFoldU64 32 gcdStep 32','.boundedFoldU64 64 gcdStep 64'),
            ('reduction','if budget < requiredBudget then .done 235 0 else','if budget < requiredBudget then .done 0 0 else')):
            with self.subTest(key=key,before=before):self.reject(key,before,after)


if __name__=='__main__':unittest.main()
