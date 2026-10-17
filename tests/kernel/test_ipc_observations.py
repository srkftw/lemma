"""Malformed IPC evidence must fail; these fixtures claim no guest execution."""
from collections import Counter
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
from check_kernel_ipc import IPCTrace,A_ORDER,require_death_order,require_ipc_binding,digest
from core0_common import Core0Error

class IPCEvidenceTests(unittest.TestCase):
    def trace(self):
        t=object.__new__(IPCTrace)
        t.tasks={512:{"key":"clienta","image":1,"nonce":19,"reaped":False,"start":True},
                 1024:{"key":"clientb","image":2,"nonce":23,"reaped":False,"start":True},
                 1536:{"key":"server","image":0,"nonce":29,"reaped":False,"start":True},
                 2048:{"key":"fault","image":4,"nonce":1284,"reaped":False,"start":False}}
        t.current=512;t.remaining=410;t.cases={};t.serials=set();t.events=[]
        t.server_accepts={};t.server_replies={};t.server_duplicates={};t.server_invalid={}
        t.fault_calls={};t.packets=[];t.payloads=[];t.snapshots={};t.refs={}
        return t

    def test_manifest_policy_cannot_replace_actual_ipc_graph(self):
        for binding in ({}, {"managed_policy":"lemma-ipc-v1"},
                        {"managed_policy":"lemma-ipc-v1","managed_ipc":{"managed_policy":"lemma-ipc-v1"}}):
            with self.subTest(binding=binding),self.assertRaises(Core0Error):require_ipc_binding(binding)

    def test_wrong_reply_status_or_error_value_rejected(self):
        for event in ((0x230,512,1,0,0),(0x230,512,1,80,16),(0x230,512,2,81,0)):
            with self.subTest(event=event),self.assertRaises(Core0Error):self.trace().observe(event)

    def test_actual_transaction_cannot_skip_serial_after_failed_publication(self):
        t=self.trace();t.cases[512]=[None]*A_ORDER.index(30)
        for serial in (0,8,10):
            with self.subTest(serial=serial),self.assertRaises(Core0Error):t.observe((0x230,512,30,0,serial))

    def test_sender_must_match_request_client_even_if_other_client_alive(self):
        t=self.trace();t.current=1536
        with self.assertRaises(Core0Error):t.observe((0x221,1536,19*256+1,1024,18))

    def test_reply_capability_cannot_reuse_wrong_server_slot(self):
        t=self.trace();t.current=1536
        with self.assertRaises(Core0Error):t.observe((0x221,1536,19*256+1,512,19))

    def test_packet_cannot_authenticate_another_live_task(self):
        t=self.trace()
        with self.assertRaises(Core0Error):t.observe((0x231,512,19*256+16,1024,64))

    def test_packet_and_payload_allow_preemption_between_console_syscalls(self):
        t=self.trace()
        t.current=1024
        t.observe((0x231,1024,23*256+1,1536,256))
        t.current=512
        t.observe((0x231,512,19*256+2,1536,88))
        t.observe((0x232,512,19*256+2,24,digest(19,24,0xa5)))
        t.current=1024
        t.observe((0x232,1024,23*256+1,192,digest(23,192,0xa5)))
        self.assertEqual(len(t.payloads),2)

    def test_payload_correlation_retains_exact_prior_packet_and_digest(self):
        for fault in ('absent','other-request','wrong-length','wrong-digest','duplicate-payload'):
            with self.subTest(fault=fault),self.assertRaises(Core0Error):
                t=self.trace();t.current=1024
                if fault!='absent':
                    t.observe((0x231,1024,23*256+(2 if fault=='other-request' else 1),1536,
                               88 if fault=='wrong-length' else 256))
                row=(0x232,1024,23*256+1,192,digest(23,192,0xa5)^(1 if fault=='wrong-digest' else 0))
                t.observe(row)
                if fault=='duplicate-payload':t.observe(row)

    def test_duplicate_packet_is_not_a_second_prior_witness(self):
        t=self.trace()
        t.observe((0x231,512,19*256+1,1536,256))
        with self.assertRaises(Core0Error):t.observe((0x231,512,19*256+1,1536,256))

    def test_equal_rollback_snapshot_with_wrong_object_or_refcount_rejected(self):
        for event in ((0x233,512,1,7,410),(0x233,512,1,6,409)):
            with self.subTest(event=event),self.assertRaises(Core0Error):self.trace().observe(event)
        t=self.trace();t.snapshots[1]=[0x233,512,1,6,410]
        with self.assertRaises(Core0Error):t.observe((0x234,512,1,2,3))

    def test_fresh_caller_must_have_first_transaction(self):
        t=self.trace();t.current=2048
        with self.assertRaises(Core0Error):t.observe((0x250,2048,1284,0,2))

    def test_sleep_elapsed_alone_cannot_certify_post_acceptance_death(self):
        t=self.trace();t.faults=[{"task":2048,"event_index":10}];t.peer_death=None
        t.server_accepts[1284]={"record":[0x221,1536,1284,2048,18],"event_index":11}
        t.server_replies[1284]={"record":[0x222,1536,1284,80,0],"event_index":12}
        with self.assertRaises(Core0Error):require_death_order(t)

if __name__=="__main__":unittest.main()
