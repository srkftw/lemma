"""Independent observer rejects forged/stale mathematical evidence."""
import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'conformance/lemmasim'))
import math_oracle


class MathematicsEvidenceTests(unittest.TestCase):
    def record(self):
        words=[0]*104
        words[:22]=[math_oracle.MAGIC,1,math_oracle.IDENTITY,1,1,11,1,5,6,0,0,0,
                    1,11,math_oracle.IDENTITY,1,0,8,1,0,64,2]
        words[32:41]=[11,1,5,6,0,0,0,1,8]
        return words

    def inspect(self, words):
        return math_oracle.inspect(struct.pack('<'+str(len(words))+'Q',*words),1,0x8001)

    def test_uncertain_baseline_uses_events_and_explicit_disable(self):
        words=self.record()+[0]*128
        words[1]=2;words[22:28]=[math_oracle.IDENTITY,0,1,1,1,0]
        words[104:106]=[11,1|(1<<8)|(1<<16)]
        observed=self.inspect(words)['learner']
        self.assertEqual((observed['recommendation'],observed['reason'],observed['understanding']),
                         ('later','exact-attempt','uncertain'))
        words[19]=1;words[24]=2;words[106:108]=[11,2|(1<<8)|(1<<16)]
        self.assertEqual(self.inspect(words)['learner']['reason'],'assisted')
        words[23]=4;words[24]=3;words[27]=1;words[108:110]=[11,3|(1<<8)|(4<<16)]
        self.assertEqual(self.inspect(words)['learner']['recommendation'],'disabled')
        for index,value in [(22,2),(23,0),(25,0),(105,1|(2<<8)|(1<<16)),(109,3|(1<<8)|(5<<16)),(111,1)]:
            changed=list(words);changed[index]=value
            with self.assertRaises(ValueError):self.inspect(changed)

    def current_record(self, known):
        words=self.record()+[0]*208
        words[1]=3;words[22:28]=[math_oracle.IDENTITY,0,1,1,1,0]
        words[104:106]=[11,1|(1<<8)|(1<<16)]
        words[232:240]=[math_oracle.EXECUTION_MAGIC,1,0,0,0,0,0,0]
        if known:
            slot=[44,*math_oracle.EXECUTION_IDENTITIES,8,0,2]
            words[240:248]=slot;words[248:256]=slot
        return words

    def test_current_execution_identity_and_unknown_legacy_are_distinct(self):
        unknown=self.inspect(self.current_record(False))
        self.assertEqual(unknown['execution']['active'],{'origin':'Unknown'})
        self.assertEqual(unknown['execution']['history'][0],{'origin':'Unknown'})
        words=self.current_record(True)
        known=self.inspect(words)
        self.assertEqual(known['execution']['active']['request'],44)
        self.assertEqual(known['execution']['active']['status'],0)
        self.assertEqual(known['execution']['active']['implementation'],'lemma-isolated-arithmetic-managed-v1')
        for index in [232,233,234,*range(240,256)]:
            changed=list(words);changed[index]+=1
            with self.assertRaises(ValueError):self.inspect(changed)
        changed=list(words);changed[256:264]=changed[248:256]
        with self.assertRaises(ValueError):self.inspect(changed)

    def test_current_edit_clears_only_active_execution_applicability(self):
        words=self.current_record(True)
        saved=words[248:256]
        words[5]=12;words[8]=7;words[12]=words[13]=0;words[240:248]=[0]*8
        record=self.inspect(words)
        self.assertEqual(record['execution']['active'],{'origin':'Unknown'})
        self.assertEqual(record['execution']['history'][0]['request'],44)
        self.assertEqual(words[248:256],saved)
        words[240:248]=saved
        with self.assertRaises(ValueError):self.inspect(words)

    def test_sums_version_preserves_exact_old_authority_and_rejects_cross_origin(self):
        words=self.current_record(True);words[1]=4;words[233]=2
        observed=self.inspect(words)
        self.assertEqual(observed['execution']['history'][0]['origin'],'IsolatedManaged')
        slot=[45,*math_oracle.SUMS_EXECUTION_IDENTITIES,8,0,3]
        words[240:248]=slot;words[248:256]=slot
        observed=self.inspect(words)
        self.assertEqual(observed['execution']['active']['origin'],'IsolatedSums')
        self.assertEqual(observed['execution']['active']['runtime'],'lemma-owned-arena-sum-cookie-v1')
        for index,value in [(1,3),(233,1),(247,2),(255,2),(241,math_oracle.EXECUTION_IDENTITIES[0]),(243,math_oracle.EXECUTION_IDENTITIES[2])]:
            changed=list(words);changed[index]=value
            with self.assertRaises(ValueError):self.inspect(changed)

    def test_bytes_version_retains_older_origins_and_binds_its_distinct_resources(self):
        words=self.current_record(True);words[1]=5;words[233]=3
        self.assertEqual(self.inspect(words)['execution']['active']['origin'],'IsolatedManaged')
        older=[45,*math_oracle.SUMS_EXECUTION_IDENTITIES,8,0,3]
        words[240:248]=older;words[248:256]=older
        self.assertEqual(self.inspect(words)['execution']['active']['origin'],'IsolatedSums')
        slot=[46,*math_oracle.BYTES_EXECUTION_IDENTITIES,8,0,4]
        words[240:248]=slot;words[248:256]=slot
        active=self.inspect(words)['execution']['active']
        self.assertEqual((active['origin'],active['runtime'],active['resources']),
                         ('IsolatedBytes','lemma-owned-arena-bytes-cookie-v1',
                          'lemma-arithmetic-bytes-resource-v1'))
        for index in [0,233,*range(240,256)]:
            changed=list(words);changed[index]+=1
            with self.assertRaises(ValueError):self.inspect(changed)
        for version,extension in [(3,1),(4,2)]:
            changed=list(words);changed[1]=version;changed[233]=extension
            with self.assertRaises(ValueError):self.inspect(changed)
        changed=list(words);changed[5]=12;changed[12]=changed[13]=0
        changed[240:248]=[0]*8
        self.assertEqual(self.inspect(changed)['execution']['history'][0]['request'],46)
        changed[240:248]=slot
        with self.assertRaises(ValueError):self.inspect(changed)

    def test_actual_rational_values_and_revision_are_load_bearing(self):
        words=self.record()
        self.assertEqual(self.inspect(words)['outcome'],1)
        for offset,value in [(8,7),(13,10),(14,2),(15,2),(16,1),(17,0)]:
            changed=list(words);changed[offset]=value
            with self.assertRaises(ValueError):self.inspect(changed)

    def test_edited_answer_preserves_old_evidence_without_current_applicability(self):
        words=self.record();words[5]=12;words[8]=7;words[12]=words[13]=0
        result=self.inspect(words)
        self.assertEqual(result['outcome'],0)
        self.assertEqual(result['history'][0]['answer'][:2],[5,6])
        self.assertEqual(result['history'][0]['revision'],11)
        words[13]=11
        with self.assertRaises(ValueError):self.inspect(words)

    def test_history_and_unused_storage_cannot_hide_forged_results(self):
        for offset,value in [(35,7),(39,2),(40,0),(50,1),(22,1)]:
            words=self.record();words[offset]=value
            with self.assertRaises(ValueError):self.inspect(words)

    def test_unsupported_and_resource_outcomes_are_distinct(self):
        self.assertEqual(math_oracle.result(3,5,6,1,2,1,8),4)
        self.assertEqual(math_oracle.result(1,5,6,0,0,0,0),5)
        self.assertEqual(math_oracle.result(1,5,0,0,0,0,0),2)
        self.assertEqual(math_oracle.result(2,0,1,1,2,1,6),1)
        self.assertEqual(math_oracle.result(2,0,1,1,3,1,6),2)


if __name__=='__main__':unittest.main()
