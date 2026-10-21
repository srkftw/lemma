"""Actual host ingress guards; no controller, guest or timing qualification."""
import copy
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from lemmasim_session import Session,external_command,optical_source_batch
from lemmasim_fast import Fast,OPTICAL_BINDING,validate_execution_binding


class OpticalInput(unittest.TestCase):
    def test_external_words_retain_full_unsigned_data_and_reject_bad_fields(self):
        request={'action':'inject','kind':'optical-frame','words':[1,1,(1<<64)-1,8,65535]}
        command,record=external_command(request,9007199254740993)
        self.assertEqual(command,'inject 9007199254740993 optical-frame 1 1 18446744073709551615 8 65535')
        self.assertEqual(record['words'][2],(1<<64)-1)
        for index,value in [(0,0),(0,4),(1,4),(2,1<<64),(2,-1),(2,True),(2,'9007199254740993'),(3,9),(4,65536)]:
            with self.subTest(index=index,value=value),self.assertRaises(ValueError):
                words=list(request['words']);words[index]=value
                external_command(dict(request,words=words),9007199254740993)

    def test_bounded_batches_validate_before_device_mutation(self):
        wire='1 0 0 0 0\n1 1 18446744073709551615 8 65535\n1 2 0 0 0'
        command,record=external_command({'action':'optical-source-batch','rows':wire},17)
        self.assertEqual(command,'optical-source-batch 17 '+wire)
        self.assertEqual(record['rows'],wire)
        for bad in ['',wire+'\n',wire+'\nno',('1 0 0 0 0\n'*1025).rstrip('\n'),'1 1 18446744073709551616 8 0','1 1 0 9 0','1 1 0 8 0é']:
            with self.subTest(bad=bad[:60]),self.assertRaises(ValueError):optical_source_batch(bad)
        with self.assertRaises(ValueError):external_command({'action':'optical-source-batch','cycle':18,'rows':wire},17)

    def test_student_rejection_precedes_clock_and_device_access(self):
        session=Session.__new__(Session);session.mode='student'
        session.ensure_capture_certain=lambda:None
        def unexpected():
            self.fail('denied raw source touched the machine')
        session.machine=SimpleNamespace(clock=unexpected)
        with self.assertRaisesRegex(ValueError,'Developer or Laboratory'):
            session.dispatch({'action':'inject','kind':'optical-frame','words':[1,0,0,0,0]})
        with self.assertRaisesRegex(ValueError,'Developer or Laboratory'):
            session.dispatch({'action':'optical-source-batch','rows':'1 0 0 0 0'})

    def test_fast_source_is_queue_only_current_and_lossless(self):
        fast=Fast.__new__(Fast);fast.optical=True;fast.input_kinds={'optical-frame'}
        fast.clock_hz=100000000;fast.time_origin_ns=0
        calls=[]
        fast.get=lambda key:'90071992547409930'
        fast.clock=lambda:{'cycle':9007199254740993}
        fast.inspect=lambda:{'cycle':9007199254740993}
        fast.qmp=SimpleNamespace(execute=lambda command,arguments:calls.append((command,arguments)))
        result=fast.call('inject 9007199254740993 optical-frame 1 1 18446744073709551615 8 65535')
        self.assertEqual(result['cycle'],9007199254740993)
        self.assertEqual(calls,[('qom-set',{'path':'/machine/lemma-hardware','property':'optical-source','value':'1 1 18446744073709551615 8 65535'})])
        for command in ['inject 9007199254740994 optical-frame 1 0 0 0 0',
                        'inject 9007199254740993 optical-frame 1 1 18446744073709551616 8 0',
                        'inject 9007199254740993 optical-frame 1 1 +1 8 0',
                        'inject 9007199254740993 optical-frame 1 1 0 9 0']:
            with self.subTest(command=command),self.assertRaises(ValueError):fast.call(command)
        self.assertEqual(len(calls),1)
        fast.call('optical-source-batch 9007199254740993 1 0 0 0 0\n1 1 18446744073709551615 8 0')
        self.assertEqual(calls[-1][1]['property'],'optical-source-batch')
        self.assertEqual(calls[-1][1]['value'],'1 0 0 0 0\n1 1 18446744073709551615 8 0')
        count=len(calls)
        for command in ['optical-source-batch 9007199254740994 1 0 0 0 0','optical-source-batch 9007199254740993 1 1 0 9 0']:
            with self.assertRaises(ValueError):fast.call(command)
        self.assertEqual(len(calls),count)
        fast.optical=False
        with self.assertRaises(ValueError):fast.call('inject 9007199254740993 optical-frame 1 0 0 0 0')
        fast.data={'profile':'lemma-silicon-dev/0.17.0'}
        with self.assertRaisesRegex(ValueError,'not qualified'):fast.checkpoint_admission()

    def test_only_explicit_source_bound_functional_binding_is_admitted(self):
        sources={name:'a'*64 for name in ['sim/host/lemma_optical.c','sim/host/lemma_optical.h',
                 'sim/host/lemma_optical_qemu.inc.c','tooling/lemmasim/patch_optical.py',
                 'sim/profiles/lemma-silicon-dev-0.17.0.json','sim/host/lemma_multimodal_v2.c']}
        good={'profile':'lemma-silicon-dev/0.17.0','execution_binding':OPTICAL_BINDING,
              'optical_controller_abi':1,'optical_frame_contract':'lemma-optical-frame/1',
              'multimodal_controller_abi':2,'controller_contract':'lemma-multimodal-converter/2','sources':sources}
        self.assertTrue(validate_execution_binding(good))
        for fields in [{'profile':'lemma-silicon-dev/0.14.0'},
                       {'execution_binding':'lemma-optical17-canonical/1'},
                       {'optical_controller_abi':True},{'optical_controller_abi':2},
                       {'optical_frame_contract':'future'}, {'multimodal_controller_abi':1},
                       {'checkpoint_binding':'lemma-silicon-fast-mm2-softtlb/0.1.0'},
                       {'checkpoint_admitted':True},{'checkpoint_admitted':0},
                       {'sources':list(sources)},{'sources':{}}]:
            with self.subTest(fields=fields),self.assertRaises(ValueError):validate_execution_binding(dict(good,**fields))
        for name in sources:
            bad=copy.deepcopy(good);bad['sources'].pop(name)
            with self.subTest(missing=name),self.assertRaises(ValueError):validate_execution_binding(bad)


if __name__=='__main__':unittest.main()
