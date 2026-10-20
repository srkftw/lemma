"""Consequential source negatives for the selected25 capture/Console path.

These are observer tests; genuine Actions, complete LLVM pins and CPU runs
retain their independent scopes.
"""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
import school_stream_target as target

class StreamSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.values={key:(ROOT/name).read_text() for key,name in target.COMPONENTS.items()}
    def reject(self,key,before,after):
        self.assertIn(before,self.values[key],'mutation anchor absent')
        values=dict(self.values);values[key]=values[key].replace(before,after,1)
        with self.assertRaises(Core0Error):target.sources(values)
    def cases(self,key,pairs):
        for before,after in pairs:
            with self.subTest(key=key,before=before):self.reject(key,before,after)
    def test_current_explicit_mode_and_byte_extent(self):
        result=target.sources(self.values)
        self.assertEqual((result['mode'],result['legacy_modes'],result['flag_offset'],result['capture_rounds']),(3,[0,1,2],656,8))
        self.assertEqual((result['maximum_payload'],result['maximum_frame'],result['console_limit']),(96,230,256))
    def test_mode_flag_reset_and_partial_removal_reject(self):
        self.cases('notebook',[
          ('mainMultimodalConfigured bootArgument 3','mainMultimodalConfigured bootArgument 2'),
          ('school ≤ 3','school ≤ 4'),('if school = 3 then 1 else 0','if 2 ≤ school then 1 else 0'),
          ('Memory.write64 schoolStreamFlag 0','Memory.write64 schoolStreamFlag 1'),
          ('state + 656','state + 648'),('private def schoolStreamFlag','private def removedStreamFlag'),
          ('def mainMultimodalSchoolV3','def removedSchoolV3'),
          ('if school = 3 then CapabilityConsole.record console 0x740 1 96 230 256','if school = 2 then CapabilityConsole.record console 0x740 1 96 230 256')])
    def test_bounded_real_capture_preserves_owner_yield_and_errors(self):
        self.cases('notebook',[
          ('.boundedFoldU64 8 advance 8','.boundedFoldU64 9 advance 9'),
          ('if before = 0 then .done Status.iterationStop rounds','if before = 1 then .done Status.iterationStop rounds'),
          ('.bind multimodalRawPump fun s _ =>','.bind (Syscall.sleep 1) fun s _ =>'),
          ('if queueOwns = 0 then pumpBookmarkSave else .done 0 0','if queueOwns = 1 then pumpBookmarkSave else .done 0 0'),
          ('if before = after then if pending = 0 then','if before = after then if pending = 1 then'),
          ('if status = Status.iterationStop then .done 0 rounds else .done status rounds','if status = Status.iterationStop then .done 0 rounds else .done 0 rounds')])
    def test_idle_suffix_preserves_nonblocking_input_and_legacy_sleep(self):
        self.cases('notebook',[
          ('if 0 < captured then Syscall.yield else Syscall.sleep 10000','if 1 < captured then Syscall.yield else Syscall.sleep 10000'),
          ('if 0 < captured then Syscall.yield else Syscall.sleep 10000','if 0 < captured then Syscall.sleep 10000 else Syscall.yield'),
          ('else Syscall.sleep 10000\n\nprivate def multimodalDrainInput','else Syscall.yield\n\nprivate def multimodalDrainInput'),
          ('if consumed = 0 then multimodalIdleInput else .done 0 consumed','if consumed = 1 then multimodalIdleInput else .done 0 consumed'),
          ('if s = 174 then multimodalIdleInput else','if s = 174 then Syscall.sleep 10000 else'),
          ('      .bind (Syscall.call 65 input 1 raw 0 0)','      .bind (Syscall.call 65 input 2 raw 0 0)')])
    def test_fresh_wire_selection_and_pointer_recovery_order(self):
        self.cases('notebook',[
          ('if wire = 1 then Lemma.Courses.SchoolSubmission.enableWire96 else .done 0 0','if wire = 0 then Lemma.Courses.SchoolSubmission.enableWire96 else .done 0 0'),
          ('Lemma.Courses.SchoolSubmission.restore 1','Lemma.Courses.SchoolSubmission.restore 2')])
        self.cases('submission',[
          ('if phase = 0 then if enabled = 0 then put 336 1','if phase = 1 then if enabled = 0 then put 336 1'),
          ('if phase = 0 then if enabled = 0 then put 336 1','if phase = 0 then if enabled = 1 then put 336 1'),
          ('.boundedFoldU64 48 zeroStep 48','.boundedFoldU64 42 zeroStep 42'),
          ('let count := minimum (if wire = 1 then 96 else 16) available','let count := minimum 96 available'),
          ('SchoolStream.send console queue offset source count','SchoolStream.send console queue 0 source count'),
          ('crcWords source count','crcWords source 16'),('put 160 (offset+count)','put 160 (offset+available)')])
    def test_packet_bounds_header_and_complete_hex_source(self):
        self.reject('console','packetAddress : UInt64 := 0x20200','packetAddress : UInt64 := 0x20220')
        self.reject('notebook','def raw : UInt64 := 0x20300','def raw : UInt64 := 0x202e0')
        self.cases('stream',[
          ('def maximumPayload : UInt64 := 96','def maximumPayload : UInt64 := 97'),
          ('queue >>> 48 = 0x5351','queue >>> 48 = 0x5352'),('if 0 < (queue &&& 0x0000ffffffffffff) then','if 0 ≤ (queue &&& 0x0000ffffffffffff) then'),
          ('if offset < 262144 then','if offset ≤ 262144 then'),('count ≤ 262144-offset','count ≤ 262144'),
          ('word (packet+3) queue','word (packet+3) offset'),('count <<< 48','count <<< 47'),
          ('.boundedFoldU64 96 byteStep','.boundedFoldU64 95 byteStep'),
          ('Memory.read8 (source+i.toUInt64)','Memory.read8 (source+i.toUInt64+1)'),
          ('Console.digit (value >>> 4)','Console.digit (value &&& 15)'),
          ('Memory.write8 (packet+37+count*2) 10','Memory.write8 (packet+37+count*2) 13'),
          ('.done 0 (38+count*2)','.done 0 (37+count*2)')])
    def test_short_or_error_output_and_start_resynchronization(self):
        self.cases('stream',[
          ('if actual = length then .done 0 count','if actual ≤ length then .done 0 count'),
          ('else .done Console.failure actual','else .done 0 actual'),
          ('Console.prepareRecord 0x72e queue sequence total ns','Console.prepareRecord 0x72e queue sequence ns total'),
          ('.boundedFoldU64 88 shiftStartStep 88','.boundedFoldU64 87 shiftStartStep 87'),
          ('packet+87-i.toUInt64','packet+i.toUInt64'),
          ('Memory.write8 packet 10','Memory.write8 packet 32'),
          ('Capability.consoleWrite console packet 89','Capability.consoleWrite console packet 88'),
          ('if actual = 89 then .done 0 0','if actual = 88 then .done 0 0')])

if __name__=='__main__':unittest.main()
