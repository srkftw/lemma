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

    def test_array_version_keeps_learner_authority_and_exact_old_origins(self):
        words=self.current_record(True);words[1]=6;words[233]=4
        prior=self.inspect(self.current_record(True))
        current=self.inspect(words)
        self.assertEqual(current['learner'],prior['learner'])
        self.assertEqual(current['execution'],prior['execution'])
        for index,value in [(22,2),(24,65),(25,0),(19,1),(105,1|(2<<8)|(1<<16))]:
            changed=list(words);changed[index]=value
            with self.assertRaises(ValueError):self.inspect(changed)
        slot=[47,*math_oracle.ARRAY_EXECUTION_IDENTITIES,8,0,5]
        words[240:248]=slot;words[248:256]=slot
        self.assertEqual(self.inspect(words)['execution']['active']['origin'],'IsolatedArray')
        changed=list(words);changed[1]=5;changed[233]=3
        with self.assertRaises(ValueError):self.inspect(changed)

    def test_edited_answer_preserves_old_evidence_without_current_applicability(self):
        words=self.record();words[5]=12;words[8]=7;words[12]=words[13]=0
        result=self.inspect(words)
        self.assertEqual(result['outcome'],0)
        self.assertEqual(result['history'][0]['answer'][:2],[5,6])
        self.assertEqual(result['history'][0]['revision'],11)
        words[13]=11
        with self.assertRaises(ValueError):self.inspect(words)

    def test_string_record_preserves_prior_origins_and_strict_learner_validation(self):
        words=self.current_record(True);words[1]=7;words[233]=5
        for origin,identities in [(2,math_oracle.EXECUTION_IDENTITIES),
                                  (3,math_oracle.SUMS_EXECUTION_IDENTITIES),
                                  (4,math_oracle.BYTES_EXECUTION_IDENTITIES),
                                  (5,math_oracle.ARRAY_EXECUTION_IDENTITIES)]:
            slot=[48,*identities,8,0,origin]
            words[240:248]=slot;words[248:256]=slot
            self.assertNotEqual(self.inspect(words)['execution']['active']['origin'],'IsolatedString')
        slot=[49,0x0006000100000001,0x0006000000000001,
              0x0001000400000001,0x000400000000001f,8,0,6]
        words[240:248]=slot;words[248:256]=slot
        observed=self.inspect(words)
        self.assertEqual(observed['execution']['active']['origin'],'IsolatedString')
        self.assertEqual(observed['execution']['active']['runtime'],'lemma-owned-arena-string-graph-v1')
        for index in [233,22,25,105,*range(240,256)]:
            changed=list(words);changed[index]+=1
            with self.assertRaises(ValueError):self.inspect(changed)
        changed=list(words);changed[1]=6;changed[233]=4
        with self.assertRaises(ValueError):self.inspect(changed)
        changed=list(words);changed[5]=12;changed[8]=7;changed[12]=changed[13]=0
        changed[240:248]=[0]*8
        self.assertEqual(self.inspect(changed)['execution']['history'],observed['execution']['history'])
        changed[240:248]=slot
        with self.assertRaises(ValueError):self.inspect(changed)

    def test_history_and_unused_storage_cannot_hide_forged_results(self):
        for offset,value in [(35,7),(39,2),(40,0),(50,1),(22,1)]:
            words=self.record();words[offset]=value
            with self.assertRaises(ValueError):self.inspect(words)

    def test_closure_record_retains_prior_authority_and_rejects_forged_applicability(self):
        # Literal independent Doc8 authority; do not build this expectation
        # from the implementation registry or infer trust from outcome1.
        words=self.current_record(True);words[1]=8;words[233]=6
        historical=[(2,(0x0002000100000001,0x0002000000000001,0x0001000000000001,0x000100000000001f)),
                    (3,(0x0003000100000001,0x0003000000000001,0x0001000100000001,0x000100000000001f)),
                    (4,(0x0004000100000001,0x0004000000000001,0x0001000200000001,0x000200000000001f)),
                    (5,(0x0005000100000001,0x0005000000000001,0x0001000300000001,0x000300000000001f)),
                    (6,(0x0006000100000001,0x0006000000000001,0x0001000400000001,0x000400000000001f))]
        for origin,identities in historical:
            slot=[50,*identities,8,0,origin]
            words[240:248]=slot;words[248:256]=slot
            self.assertNotEqual(self.inspect(words)['execution']['active']['origin'],'IsolatedClosure')
        slot=[51,0x0007000100000001,0x0007000000000001,
              0x0001000500000001,0x000500000000001f,8,0,7]
        words[240:248]=slot;words[248:256]=slot
        observed=self.inspect(words)
        self.assertEqual((observed['execution']['active']['origin'],
                          observed['execution']['active']['resources']),
                         ('IsolatedClosure','lemma-arithmetic-closure-resource-v1'))
        for index in [1,233,14,15,16,17,*range(240,256)]:
            changed=list(words);changed[index]+=1
            with self.assertRaises(ValueError):self.inspect(changed)
        for version,extension in [(3,1),(4,2),(5,3),(6,4),(7,5)]:
            changed=list(words);changed[1]=version;changed[233]=extension
            with self.assertRaises(ValueError):self.inspect(changed)
        changed=list(words);changed[5]=12;changed[8]=7;changed[12]=changed[13]=0
        changed[240:248]=[0]*8
        self.assertEqual(self.inspect(changed)['execution']['history'],observed['execution']['history'])
        changed[240:248]=slot
        with self.assertRaises(ValueError):self.inspect(changed)

    def test_unsupported_and_resource_outcomes_are_distinct(self):
        self.assertEqual(math_oracle.result(3,5,6,1,2,1,8),4)
        self.assertEqual(math_oracle.result(1,5,6,0,0,0,0),5)
        self.assertEqual(math_oracle.result(1,5,0,0,0,0,0),2)
        self.assertEqual(math_oracle.result(2,0,1,1,2,1,6),1)
        self.assertEqual(math_oracle.result(2,0,1,1,3,1,6),2)


if __name__=='__main__':unittest.main()
