"""Original genuinely compiled Objects-v3 fragments and fail-closed mutations."""
import copy
import json
from pathlib import Path
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_kernel import validate_object_budget
from core0_common import Core0Error

class ObjectsV3Audit(unittest.TestCase):
    def setUp(self):
        self.f=json.loads((ROOT/'tests/kernel/fixtures/objects-v3-generated.json').read_text())
        self.names={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r['symbol'] for r in self.f['unit']['functions']}
    def observe(self,f=None):
        f=f or self.f
        return validate_object_budget(f['unit'],'\n'.join(f['headers'][s]+'\n'+b+'\n}' for s,b in f['bodies'].items()))
    def reject(self,tail,before,after):
        f=copy.deepcopy(self.f);symbol=self.names['Lemma.Kernel.Objects.'+tail]
        self.assertIn(before,f['bodies'][symbol]);f['bodies'][symbol]=f['bodies'][symbol].replace(before,after,1)
        with self.assertRaises(Core0Error):self.observe(f)
    def test_actual_closed_revision_and_legacy_budgets(self):
        r=self.observe();self.assertEqual(r['endpoint']['capacity'],{'version1':4,'version2':5,'version3':6})
        self.assertEqual(r['reply']['capacity'],{'version1':8,'version2':8,'version3':7})
        self.assertEqual({(c['version'],c['encoded_limit']) for c in r['header_cases'] if c['result']},{(1,0),(2,5),(3,6)})
        self.assertEqual(r['initialization']['wrappers'],{'Lemma.Kernel.Objects.init':1,'Lemma.Kernel.Objects.initArithmetic':3})
    def test_header_version_limit_and_quota_mutations(self):
        for tail,before,after in [('headerAdmitted','icmp eq i64 %arg0, 3','icmp eq i64 %arg0, 4'),
            ('arithmeticEndpointCapacity','ret i64 6','ret i64 7'),('arithmeticReplyCapacity','ret i64 7','ret i64 8'),
            ('replyCapacity','ret i64 8','ret i64 7'),('capacity','ret i64 16','ret i64 17'),
            ('replyLimitFor','icmp eq i64 %arg0, 3','icmp eq i64 %arg0, 4'),
            ('initArithmetic','i64 3)','i64 2)'),('encodedLimitFor','icmp eq i64 %arg0, 3','icmp eq i64 %arg0, 2')]:
            with self.subTest(tail=tail):self.reject(tail,before,after)
    def test_reply_quota_actual_version_and_strict_count(self):
        for tail in ('runtimeReplyCapacity','runtimeEndpointCapacity'):
            body=self.f['bodies'][self.names['Lemma.Kernel.Objects.'+tail]]
            address=re.search(r'add i64 %[^,]+, 8',body)[0]
            self.reject(tail,address,address.replace(', 8',', 24'))
        body=self.f['bodies'][self.names['Lemma.Kernel.Objects.replyAvailable']]
        count=re.search(r'icmp ult i64 %[^,]+, %[^\n]+',body)[0]
        self.reject('replyAvailable',count,count.replace(' ult ',' ule '))
    def test_missing_reply_closure_and_unknown_authority_reject(self):
        for tail in ('runtimeReplyCapacity','arithmeticReplyCapacity','replyLimitFor','replyAvailable'):
            f=copy.deepcopy(self.f);f['unit']['functions']=[r for r in f['unit']['functions'] if r['symbol']!=self.names['Lemma.Kernel.Objects.'+tail]]
            with self.subTest(tail=tail),self.assertRaises(Core0Error):self.observe(f)
        f=copy.deepcopy(self.f);f['unit']['role']='user'
        with self.assertRaises(Core0Error):self.observe(f)
    def test_initializer_binding_and_encoding_reject(self):
        symbol=self.names['Lemma.Platform.LemmaSim.NotebookKernel.construct'];f=copy.deepcopy(self.f)
        self.assertIn('icmp eq i64 %arg2, 3',f['bodies'][symbol]);f['bodies'][symbol]=f['bodies'][symbol].replace('icmp eq i64 %arg2, 3','icmp eq i64 %arg2, 2')
        with self.assertRaises(Core0Error):self.observe(f)
        self.reject('initFor','i64 %arg0)','i64 2)')

    def test_shared_v3_header_does_not_require_optional_arithmetic_wrapper(self):
        # Genuine shared initializer fragments, restricted to the closure that
        # historical H/J units actually reach. This is an observer regression;
        # the independently retained CI artifacts establish its real occurrence.
        f=copy.deepcopy(self.f)
        removed={self.names['Lemma.Kernel.Objects.initArithmetic'],
                 self.names['Lemma.Platform.LemmaSim.NotebookKernel.construct']}
        f['unit']['functions']=[r for r in f['unit']['functions'] if r['symbol'] not in removed]
        for symbol in removed:
            del f['bodies'][symbol]
            del f['headers'][symbol]
        result=self.observe(f)['initialization']
        self.assertEqual(result['wrappers'],{'Lemma.Kernel.Objects.init':1})
        self.assertEqual(result['power_callers'],[])
        self.assertEqual({r['version'] for r in result['version_cases'] if r['result']},{1,2,3})
        for tail,before,after in [('initFor','icmp eq i64 %arg0, 3','icmp eq i64 %arg0, 4'),
            ('init','i64 1)','i64 3)'),
            ('encodedLimitFor','@'+self.names['Lemma.Kernel.Objects.arithmeticEndpointCapacity']+'()',
                '@'+self.names['Lemma.Kernel.Objects.powerEndpointCapacity']+'()')]:
            mutant=copy.deepcopy(f);symbol=self.names['Lemma.Kernel.Objects.'+tail]
            self.assertIn(before,mutant['bodies'][symbol])
            mutant['bodies'][symbol]=mutant['bodies'][symbol].replace(before,after,1)
            with self.subTest(tail=tail),self.assertRaises(Core0Error):self.observe(mutant)

if __name__=='__main__':unittest.main()
