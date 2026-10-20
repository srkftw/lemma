"""Exact observer fixtures; no CPU execution or valid-controller claim."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import native_logical_relation as relation

TIMER=b'\x05timer'+struct.pack('>II',0,2)
ICOUNT=b'\x05\x0ctimer/icount'
LEGACY_WORDS=13+8+9*(29+16*8+4)

def marker(abi,version=None):
    name=('lemma-paper-pen/1/multimodal-v'+str(abi)).encode()
    return b'\x05'+bytes([len(name)])+name+struct.pack('>I',abi if version is None else version)

def machine(abi=2,offsets=(11,22)):
    prefix=b'observer-fixture'+TIMER+struct.pack('>qQq',offsets[0],0,offsets[1])+ICOUNT+struct.pack('>QQ',77,88)
    return prefix+marker(abi)+bytes((LEGACY_WORDS+(20 if abi==2 else 0))*8)+struct.pack('>q',900)

def logical(state,payload=b'all logical translation and wake witness bytes'):
    binding=b'lemma-silicon-fast-softtlb/0.2.0'
    body=b'LMTLB02\0'+struct.pack('<QQ',2,len(binding))+binding+hashlib.sha256(state).digest()+payload
    return body+hashlib.sha256(body).digest()

class NativeLogicalRelation(unittest.TestCase):
    def test_legacy_and_mm2_have_distinct_exact_relation_versions(self):
        for abi,version in ((1,relation.VERSION),(2,relation.MM2_VERSION)):
            with self.subTest(abi=abi):
                state=machine(abi)
                self.assertEqual(relation.compare_machine(state,state)['version'],version)
                self.assertEqual(relation.compare_logical(logical(state),logical(state),state,state)['version'],version)
        self.assertNotIn('ring',relation.multimodal_payload(machine(1)))
        payload=relation.multimodal_payload(machine(2),2)
        self.assertEqual(payload['controller_abi'],2)
        self.assertEqual(len(payload['ring']),20)

    def test_wrong_controller_abi_or_subsection_version_rejects(self):
        with self.assertRaises(AssertionError):relation.multimodal_payload(machine(1),2)
        for abi in (1,2):
            state=machine(abi).replace(marker(abi),marker(abi,3))
            with self.subTest(abi=abi),self.assertRaises(AssertionError):relation.compare_machine(state,state)

    def test_missing_mixed_and_duplicate_subsections_reject(self):
        for state in (machine(2).replace(marker(2),bytes(len(marker(2)))),
                      machine(2)+marker(1),machine(2)+marker(2),
                      machine(2)+marker(3),machine(2)+marker(1,3)):
            with self.subTest(bytes=len(state)),self.assertRaises(AssertionError):relation.multimodal_payload(state)

    def test_equal_incomplete_controller_body_is_not_a_pass(self):
        for abi in (1,2):
            state=machine(abi)[:-8]
            with self.subTest(abi=abi),self.assertRaises((AssertionError,struct.error)):
                relation.compare_machine(state,state)

    def test_all_twenty_ring_fields_and_controller_timer_are_exact(self):
        left=machine(2);at=left.index(marker(2))+len(marker(2))+LEGACY_WORDS*8
        for field in range(21):
            right=bytearray(left);struct.pack_into('>Q',right,at+field*8,1)
            with self.subTest(field=field),self.assertRaises(AssertionError):relation.compare_machine(left,bytes(right))

    def test_only_two_named_host_offsets_are_excluded(self):
        left,right=machine(2,(11,22)),machine(2,(33,44))
        result=relation.compare_machine(left,right)
        self.assertFalse(result['raw_equal'])
        self.assertEqual([r['name'] for r in result['host_fields']],['timer.cpu_ticks_offset','timer.cpu_clock_offset'])
        self.assertEqual([(r['left'],r['right']) for r in result['host_fields']],[(11,33),(22,44)])
        self.assertTrue(relation.compare_logical(logical(left),logical(right),left,right)['all_translation_and_witness_payload_equal'])
        changed=bytearray(right);at=changed.index(ICOUNT)+len(ICOUNT);struct.pack_into('>Q',changed,at,78)
        with self.assertRaises(AssertionError):relation.compare_machine(left,bytes(changed))

    def test_rehashed_translation_payload_and_main_binding_changes_reject(self):
        state=machine(2);other=machine(2,(33,44))
        with self.assertRaises(AssertionError):relation.compare_logical(logical(state),logical(other,b'changed witness'),state,other)
        with self.assertRaises(AssertionError):relation.compare_logical(logical(state),logical(state),state,other)

if __name__=='__main__':unittest.main()
