"""Malformed host-evidence rejection; these tests establish no guest behavior."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from check_kernel_capabilities import CapabilityTrace,MAX_SERIAL,CASE_ORDER
from core0_common import Core0Error


class CapabilityEvidenceTests(unittest.TestCase):
    def trace(self):
        trace=object.__new__(CapabilityTrace)
        trace.tasks={512:{"image":0,"nonce":19,"reaped":False,"start":True}}
        trace.current=512; trace.remaining=440
        trace.grants={}; trace.aliases={}; trace.seed=None; trace.queue=None
        trace.cases=[]; trace.peer_cases=[]; trace.snapshots={}; trace.handles={}
        trace.endpoint_frames=1; trace.endpoint_cleanup=0
        trace.serial_advance=None; trace.pending_ack=(0x36,0); trace.exhaustion=[]
        trace.ready_for_serial=None; trace.corpus_serials=set(); trace.endpoint_releases=set()
        trace.owner_death_cleanup=None
        return trace

    def test_user_alias_or_wrong_descriptor_target_rejected(self):
        for pte in (((0x82003000>>12)<<10)|0xd7,((0x80401000>>12)<<10)|0xc7):
            with self.subTest(pte=pte),self.assertRaises(Core0Error):
                self.trace().observe((0xb2,1024,0x82003a00,pte,0x31a00))

    def test_supervisor_alias_to_another_owned_page_is_rejected(self):
        with self.assertRaises(Core0Error):
            self.trace().observe((0xb2,1024,0x82003a00,((0x82003000>>12)<<10)|0xc7,0x31a00))

    def test_numeric_handle_reuse_before_publication_rejected(self):
        trace=self.trace(); trace.current=None
        trace.observe((0xb1,1024,16,1,2))
        with self.assertRaises(Core0Error): trace.observe((0xb1,1536,16,1,2))

    def test_wrong_authority_reply_or_reordered_case_rejected(self):
        for event in ((0x110,512,1,0,16),(0x110,512,1,80,16),(0x110,512,2,80,0)):
            with self.subTest(event=event),self.assertRaises(Core0Error): self.trace().observe(event)

    def test_rollback_cannot_change_source_or_resource_accounting(self):
        trace=self.trace()
        trace.observe((0x140,512,1,29,(4<<32)|440))
        for event in ((0x140,512,2,30,(4<<32)|440),(0x140,512,2,29,(4<<32)|439),
                      (0x140,512,2,29,(5<<32)|440)):
            with self.subTest(event=event),self.assertRaises(Core0Error): trace.observe(event)

    def test_equal_but_wrong_reference_counts_rejected(self):
        with self.assertRaises(Core0Error): self.trace().observe((0x140,512,1,28,(4<<32)|440))

    def test_peer_success_cannot_return_zero_authority(self):
        trace=self.trace(); trace.tasks[1024]={"image":1,"reaped":False}; trace.current=1024
        with self.assertRaises(Core0Error): trace.observe((0x120,1024,1,0,0))

    def test_last_serial_cannot_be_reported_by_peer(self):
        trace=self.trace(); trace.tasks[1024]={"image":1,"reaped":False}; trace.current=1024; trace.serial_advance=[0xb3,44,MAX_SERIAL,MAX_SERIAL,0]
        with self.assertRaises(Core0Error): trace.observe((0x1fd,1024,MAX_SERIAL<<4,MAX_SERIAL,0))

    def test_failed_publication_cannot_consume_a_serial(self):
        trace=self.trace(); trace.corpus_serials=set(range(1,46))-{23}
        with self.assertRaises(Core0Error): trace.observe((0x1fe,512,19,0,0))

    def test_peer_can_observe_transfer_before_owner_logs_but_must_match(self):
        trace=self.trace(); trace.tasks[1024]={"image":1,"reaped":False}; trace.current=1024
        trace.observe((0x124,1024,640,15,0))
        trace.current=512; trace.cases=[[] for _ in range(CASE_ORDER.index(215))]
        with self.assertRaises(Core0Error): trace.observe((0x110,512,215,0,656))

    def test_serial_wrap_or_repeated_advance_rejected(self):
        trace=self.trace(); trace.current=None
        for event in ((0xb3,0,MAX_SERIAL,MAX_SERIAL,0),(0xb3,9,0,MAX_SERIAL,0)):
            with self.subTest(event=event),self.assertRaises(Core0Error): trace.observe(event)
        trace.observe((0xb3,9,MAX_SERIAL,MAX_SERIAL,0))
        with self.assertRaises(Core0Error): trace.observe((0xb3,9,MAX_SERIAL,MAX_SERIAL,0))

    def test_exhaustion_without_last_actual_publication_rejected(self):
        with self.assertRaises(Core0Error): self.trace().observe((0x1ff,512,19,91,MAX_SERIAL<<4))


if __name__=="__main__": unittest.main()
