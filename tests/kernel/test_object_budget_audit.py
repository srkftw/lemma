"""Independent auditor mutations of retained genuinely elaborated Lean CFGs."""
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


class ObjectBudgetAudit(unittest.TestCase):
    def setUp(self):
        self.fixture=json.loads((ROOT/'tests/kernel/fixtures/objects-v2-generated.json').read_text())
        self.names={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r['symbol'] for r in self.fixture['unit']['functions']}

    def body(self,tail):
        return self.fixture['bodies'][self.names['Lemma.Kernel.Objects.'+tail]]

    def observe(self,fixture=None):
        f=fixture or self.fixture
        ir='\n'.join(f['headers'][s]+'\n'+body+'\n}' for s,body in f['bodies'].items())
        return validate_object_budget(f['unit'],ir)

    def rejected(self,source,before,after):
        f=copy.deepcopy(self.fixture);symbol=self.names[source]
        self.assertIn(before,f['bodies'][symbol])
        f['bodies'][symbol]=f['bodies'][symbol].replace(before,after,1)
        with self.assertRaises(Core0Error):self.observe(f)

    def test_actual_checked_fragments_bind_quota_headers_and_initialization(self):
        result=self.observe()
        self.assertEqual(result['endpoint']['capacity'],{'version1':4,'version2':5})
        self.assertEqual(result['initialization']['wrappers'],{'Lemma.Kernel.Objects.init':1,'Lemma.Kernel.Objects.initPower':2})
        self.assertEqual(result['initialization']['power_callers'],['Lemma.Platform.LemmaSim.NotebookKernel.construct'])
        self.assertEqual({(r['version'],r['encoded_limit']) for r in result['header_cases'] if r['result']==1},{(1,0),(2,5)})

    def test_scalar_header_limits_and_unchanged_budgets_reject_mutation(self):
        o='Lemma.Kernel.Objects.'
        for tail,before,after in [
            ('headerAdmitted','icmp eq i64 %arg1, 0','icmp eq i64 %arg1, 5'),
            ('headerAdmitted','icmp eq i64 %arg0, 2','icmp eq i64 %arg0, 3'),
            ('headerAdmitted','[ 0, %if.else.7 ]','[ 1, %if.else.7 ]'),
            ('endpointLimitFor','[ 0, %if.else.4 ]','[ 5, %if.else.4 ]'),
            ('endpointCapacity','ret i64 4','ret i64 5'),
            ('powerEndpointCapacity','ret i64 5','ret i64 6'),
            ('replyCapacity','ret i64 8','ret i64 9'),
            ('capacity','ret i64 16','ret i64 17')]:
            with self.subTest(tail=tail,before=before):self.rejected(o+tail,before,after)

    def test_header_reads_gates_and_failed_return_cannot_be_forged(self):
        o='Lemma.Kernel.Objects.';body=self.body('table')
        pred=re.search(r'(%[^ ]+) = call zeroext i1 @'+self.names[o+'headerAdmitted']+r'\(i64 (%[^,]+), i64 (%[^)]+)\)',body)
        cmp=re.search(r'(%[^ ]+) = icmp eq i1 '+re.escape(pred[1])+r', 1',body)
        version=re.search(r'add i64 (%[^,]+), 8',body)[0]
        limit=re.search(r'add i64 (%[^,]+), 24',body)[0]
        for before,after in [(version,version.replace(', 8',', 16')),(limit,limit.replace(', 24',', 40')),
            (pred[0],pred[0].replace('i64 '+pred[2]+', i64 '+pred[3],'i64 '+pred[3]+', i64 '+pred[2])),
            (cmp[0],cmp[0].replace(', 1',', 0')),
            ('icmp eq i1 %call49, 1','icmp eq i1 %call49, 0'),
            ('i64 %action.if.value168, 1','i64 5, 1')]:
            with self.subTest(before=before):self.rejected(o+'table',before,after)
        self.rejected(o+'fatal','i64 0, 1','i64 1, 1')
        self.rejected('Lemma.User.CapabilityABI.fatal','ret i8 255','ret i8 0')

    def test_runtime_quota_is_checked_loaded_version_and_returned_value(self):
        o='Lemma.Kernel.Objects.';body=self.body('runtimeEndpointCapacity')
        address=re.search(r'add i64 (%[^,]+), 8',body)[0]
        call=re.search(r'call i64 @'+self.names[o+'endpointLimitFor']+r'\(i64 (%[^)]+)\)',body)[0]
        success=re.search(r'phi i64 \[ (%[^,]+), %([^ ]+) \], \[ (%[^,]+), %([^ ]+) \]',body)[0]
        self.rejected(o+'runtimeEndpointCapacity',address,address.replace(', 8',', 24'))
        self.rejected(o+'runtimeEndpointCapacity',call,re.sub(r'i64 %[^)]+','i64 2',call))
        self.rejected(o+'runtimeEndpointCapacity',success,success.replace('[ %call21,','[ 5,'))
        self.rejected(o+'runtimeEndpointCapacity','icmp eq i1 %call15, 1','icmp eq i1 %call15, 0')

    def test_allocation_requires_strict_count_and_runtime_capacity_status(self):
        o='Lemma.Kernel.Objects.';body=self.body('createEndpoint')
        dynamic=re.search(r'(%[^ ]+) = call \{ i64, i64 \} @'+self.names[o+'runtimeEndpointCapacity']+r'\(\)',body)
        status=re.search(r'(%[^ ]+) = extractvalue \{ i64, i64 \} '+re.escape(dynamic[1])+r', 0',body)
        narrowed=re.search(r'(%[^ ]+) = trunc i64 '+re.escape(status[1])+r' to i8',body)
        helper=re.search(r'(%[^ ]+) = call zeroext i1 @'+self.names[o+'failed']+r'\(i8 zeroext '+re.escape(narrowed[1])+r'\)',body)
        cmp=re.search(r'icmp eq i1 '+re.escape(helper[1])+r', 1',body)[0]
        for before,after in [('icmp ult i64 %action.fold.value28','icmp ule i64 %action.fold.value28'),
            (cmp,cmp.replace(', 1',', 0')),
            ('%action.call.value38','%action.fold.value28')]:
            with self.subTest(before=before):self.rejected(o+'createEndpoint',before,after)

    def test_initializer_versions_encoding_and_publication_are_exact(self):
        o='Lemma.Kernel.Objects.'
        for tail,before,after in [('init','i64 1)','i64 2)'),('initPower','i64 2)','i64 1)'),
            ('initFor','icmp eq i64 %arg0, 1','icmp eq i64 %arg0, 3'),
            ('initFor','icmp eq i1 %if.result3, 0','icmp eq i1 %if.result3, 1'),
            ('initFor','add i64 %action.call.value27, 24','add i64 %action.call.value27, 16'),
            ('initFor','[ 0, %if.else.39 ]','[ 5, %if.else.39 ]'),
            ('initFor','i64 %bin54, i64 %arg0','i64 %bin54, i64 2'),
            ('initFor','icmp eq i1 %call22, 1','icmp eq i1 %call22, 0'),
            ('initFor','icmp eq i1 %call28, 1','icmp eq i1 %call28, 0'),
            ('initFor','icmp eq i1 %call73, 1','icmp eq i1 %call73, 0'),
            ('initFor','i64 %call112, i64 %action.call.value21','i64 %call112, i64 %action.call.value27')]:
            with self.subTest(tail=tail,before=before):self.rejected(o+tail,before,after)
        self.rejected('Lemma.User.CapabilityABI.invalidArgument','ret i8 16','ret i8 0')
        self.rejected('Lemma.Platform.LemmaSim.NotebookKernel.construct','icmp eq i64 %arg2, 3','icmp eq i64 %arg2, 2')

    def test_partial_successor_and_non_kernel_cannot_gain_quota(self):
        for tail in ('runtimeEndpointCapacity','headerAdmitted','endpointLimitFor','powerEndpointCapacity'):
            f=copy.deepcopy(self.fixture);source='Lemma.Kernel.Objects.'+tail
            f['unit']['functions']=[r for r in f['unit']['functions'] if r['symbol']!=self.names[source]]
            with self.subTest(tail=tail),self.assertRaises(Core0Error):self.observe(f)
        for role in ('user','firmware'):
            f=copy.deepcopy(self.fixture);f['unit']['role']=role
            with self.subTest(role=role),self.assertRaises(Core0Error):self.observe(f)

    def test_power_initializer_has_no_alternate_privileged_caller(self):
        f=copy.deepcopy(self.fixture);symbol='unapproved_power_initializer'
        f['unit']['functions'].append({'source':'Lemma.Kernel.Unapproved.initialize','symbol':symbol,'args':[],'effects':[]})
        f['headers'][symbol]='define { i64, i64 } @'+symbol+'() {'
        f['bodies'][symbol]='entry:\n  %result = call { i64, i64 } @'+self.names['Lemma.Kernel.Objects.initPower']+'()\n  ret { i64, i64 } %result\n'
        with self.assertRaises(Core0Error):self.observe(f)

    def test_historical_direct_constant_scope_is_not_relabelled_as_successor(self):
        f=copy.deepcopy(self.fixture)
        selected={'Lemma.Kernel.Objects.endpointCapacity','Lemma.Kernel.Objects.createEndpoint'}
        f['unit']['functions']=[r for r in f['unit']['functions'] if r['source'] in selected]
        self.assertIn('historical direct constant4',self.observe(f)['scope'])

    def test_absent_objects_make_no_quota_claim(self):
        f=copy.deepcopy(self.fixture)
        f['unit']['functions']=[r for r in f['unit']['functions'] if not re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']).startswith('Lemma.Kernel.Objects.')]
        self.assertEqual(self.observe(f),{'scope':'Objects not reachable in this unit; no quota claim'})


if __name__=='__main__':unittest.main()
