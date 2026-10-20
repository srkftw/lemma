"""Host failure fixtures only; these transcripts make no guest pass claim."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import check_kernel_buffer as checker
from buffer_reference import BufferReference
from buffer_transport import command, decode_uart, APPLICATION_MAGIC
from core0_common import Core0Error


def response(op=3, epoch=1, handle=4, length=128, count=128, data=bytes(128), status=0):
    return {'operation':op,'epoch':epoch,'handle':handle,'length':length,'count':count,
            'detail':256,'application_status':status,'transport_status':0,'data_hex':data.hex()}


class BufferCheckerFailures(unittest.TestCase):
    def test_silicon_startup_is_a_distinct_strict_binding(self):
        root=0x82001000
        rows=[(0xa,0x87e00000,1,512,0x82000000),
              (0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,2),
              (0xc1,2,3,1,0),(0xc2,17,22,22,123456),
              (0xd3,root,(8<<60)|(root>>12),500,0),
              (0xf0,1,8,512,10000),(0xb0,1,16,16,497)]
        events=[{'kind':'kernel','value':list(row)} for row in rows]
        facts=checker.startup(events,configuration='silicon-service-development')
        self.assertEqual(facts['supervisor']['firmware_witness_and_csrs'][-1],2)
        with self.assertRaises(Core0Error):checker.startup(events)
        for row,column,value in ((0,1,0x87e01000),(1,4,0x1446),(2,2,2),(3,4,0),(0,2,True)):
            bad=deepcopy(events);bad[row]['value'][column]=value
            with self.subTest(row=row,column=column),self.assertRaises(Core0Error):
                checker.startup(bad,configuration='silicon-service-development')
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp),'silicon-service-development')
            self.assertIn('fault',trace.keys)

    def test_timeout_ceiling_rejects_invalid_values_before_guest_setup(self):
        for timeout in (True, False, 0, -1, 300.01, float('inf'), float('-inf'), float('nan'), None, '300'):
            with self.subTest(timeout=timeout), self.assertRaises(Core0Error):
                checker.validate_timeout(timeout)
        for timeout in (0.01, 1, 300, 300.0):
            self.assertEqual(checker.validate_timeout(timeout), timeout)
        for timeout in ('0', '301', 'inf', 'nan'):
            with self.subTest(cli_timeout=timeout), \
                    patch.object(sys, 'argv', ['check_kernel_buffer.py', '--image', 'missing',
                                              '--output-dir', 'missing-output', '--timeout', timeout]), \
                    patch.object(checker, 'repo_root') as root, \
                    patch.object(checker, 'BufferSession') as session, patch('builtins.print'):
                self.assertEqual(checker.main(), 1)
                root.assert_not_called()
                session.assert_not_called()
        for timeout in (True, 0, -1, 3600.01, float('inf'), float('nan')):
            with self.subTest(rtl_timeout=timeout), self.assertRaises(Core0Error):
                checker.validate_rtl_timeout(timeout)
        self.assertEqual(checker.validate_rtl_timeout(3600), 3600)

    def fixture(self, directory, configuration='service-normal'):
        users={k:{'exit_ecall_pc':0x10020,'syscall_bridge':{'ecall_pc':0x10020},
                  'function_ranges':{'tick':{'base':0x10000,'bytes':0x400}}}
               for k in ('server','cli','peer','busy')+(('fault',) if configuration in checker.ServiceTrace.development_configurations else ())}
        edges=[['Lemma.Kernel.Objects.'+name,'Lemma.Kernel.Objects.withdrawService'] for name in ('destroy','beginRevoke')]
        edges += [['Lemma.Kernel.Directory.discover','Lemma.Kernel.Capability.grantDiscovered']]
        # Explicit two read obligations, rather than a broad UserCopy prefix.
        edges += [['Lemma.Kernel.KernelInput.read','Lemma.Kernel.Memory.UserCopy.validateWrite'],
                  ['Lemma.Kernel.KernelInput.read','Lemma.Kernel.Memory.UserCopy.copyToUser']]
        binding={'configuration':configuration,'stage':'supervisor','managed_policy':checker.POLICY,
                 'elf':{'users':users},'user_images':{k:{'id':i+1,'text_bytes':512} for i,k in enumerate(users)},
                 'managed_service':{'managed_policy':checker.POLICY,'source_call_edges':edges,'checked_cfg_gates':['fixture']}}
        path=directory/'users/busy';path.mkdir(parents=True)
        (path/'unit.json').write_text(json.dumps({'functions':[{'source':checker.ServiceTrace.busy_root,'symbol':'main'},
                       {'source':checker.ServiceTrace.busy_callback,'symbol':'tick'}],
                       'used_execution_ops':[{'stable_id':'checked-read64'}],
                       'used_loops':[{'callback':checker.ServiceTrace.busy_callback}]}))
        (directory/'audit.json').write_text(json.dumps(binding))
        session=SimpleNamespace(root=ROOT,image=directory/'image.elf',binding=binding,report={},events=[],records=[])
        trace=checker.ServiceTrace(session)
        for id,kind,rights in [(512,1,2),(512,2,8),(1024,1,3),(1024,4,1024),(1536,1,2),(1536,4,1024)]:
            slot=len(trace.grants.get(id,[]));serial=len(trace.serials)+1
            trace.observe((0xb1,id,(serial<<4)|slot,kind,rights))
        trace.observe((0xb4,512,51,416,0))
        for id,index,nonce,root in [(1024,1,1,0x82001000),(1536,2,2,0x82002000),(2048,3,3,0x82003000),(512,0,1,0x82004000)]:
            trace.observe((0xf1,id,index,nonce,root))
        trace.observe((0x300,512,51,1,1024))
        return trace,session

    def accept_read(self, trace, data):
        trace.model.buffers[4]={'capacity':256,'data':data}
        trace.model.generations[0]=1
        trace.backings[512]={0x40000}
        action={'kind':'rpc','index':7,'words':[3,1,4,0,128],'data_hex':'','epoch':1,'expected_transport':0}
        trace.begin_action(action)
        trace.current=512
        trace.observe((0x321,512,99,1024,114))
        trace.observe((0x323,512,99,0,192))
        trace.current=1024

    def fault_fixture(self, directory):
        trace,session=self.fixture(directory,'service-development')
        fault=2560
        for kind,rights in ((1,2),(4,1024)):
            slot=len(trace.grants.get(fault,[]));serial=max(trace.serials)+1
            trace.observe((0xb1,fault,(serial<<4)|slot,kind,rights))
        trace.expect_create(4,7)
        trace.observe((0xf1,fault,4,7,0x82005000))
        trace.current=fault
        trace.observe((0x340,fault,1,((max(trace.serials)+1)<<4)|2,7))
        return trace,session,fault

    def actor_response(self, trace, caller, request, *, app=0, payload=64, allocation=None, release=None):
        trace.current=trace.server
        if trace.server in trace.active_accept:
            previous=trace.active_accept[trace.server]['key'][1]
            trace.observe((0x327,trace.server,previous,0,0))
        trace.observe((0x321,trace.server,request,caller,((max(trace.serials)+1)<<4)|2))
        if allocation is not None:
            trace.observe((0x322,trace.server,allocation,0,allocation))
        if release is not None:
            trace.observe((0x324,trace.server,release,0,release))
        trace.observe((0x323,trace.server,request,app,payload))
        trace.current=caller

    def held_fault_create(self, trace, fault, request=1):
        self.actor_response(trace,fault,request,allocation=0x40000)
        trace.observe((0x341,fault,4,64,1))

    def held_fault_denial(self, trace, fault, request=3):
        # Host failure fixtures supply literal other-owner backing facts;
        # the denial still requires the authenticated real response shape.
        trace.backings[trace.server]={0x40000,0x41000,0x42000,0x43000}
        self.actor_response(trace,fault,request,app=204)
        trace.observe((0x343,fault,request,204,4))

    def held_fault_release(self, trace, fault, request=4):
        self.actor_response(trace,fault,request,release=0x40000)
        trace.observe((0x345,fault,4,1,request))

    def test_held_fault_denial_release_and_fresh_generation_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_,fault=self.fault_fixture(Path(tmp))
            trace.backings[trace.server]={0x40000,0x41000,0x42000,0x43000}
            self.actor_response(trace,fault,1,app=204)
            trace.observe((0x346,fault,1,204,0))
            self.assertFalse(trace.peer_state[fault].get('seen_global_denial',False))
            trace.backings[trace.server].remove(0x40000)
            self.held_fault_create(trace,fault,3)
            binary=checker.digest(checker.pattern(7,fault,16))
            with self.assertRaisesRegex(Core0Error,'own actual global denial'):
                trace.observe((0x342,fault,4,binary,16))
            self.held_fault_denial(trace,fault,5)
            self.held_fault_release(trace,fault,6)
            self.assertNotIn(4,trace.foreign)
            self.assertEqual(trace.peer_state[fault]['temporary'],0)
            self.assertEqual(trace.peer_state[fault]['next_create'],7)
            self.assertTrue(trace.actual_buffer_releases[0]['confirmed'])
            # Replacement can also meet a true full-device denial while Peer
            # holds the freed slot. It does not become the designated witness.
            trace.backings[trace.server].add(0x40000)
            self.actor_response(trace,fault,7,app=204)
            trace.observe((0x346,fault,7,204,2))
            trace.backings[trace.server].remove(0x40000)
            self.actor_response(trace,fault,9,allocation=0x40000)
            trace.observe((0x341,fault,8,64,1))
            self.actor_response(trace,fault,257)
            self.actor_response(trace,fault,258,payload=80)
            trace.observe((0x342,fault,8,binary,16))
            trace.observe((0x344,fault,8,1,7))
            self.assertEqual([r[0] for r in trace.actor_events],
                             [0x340,0x346,0x341,0x343,0x345,0x346,0x341,0x342,0x344])

    def test_fault_denial_rejects_absent_held_buffer_and_incomplete_or_foreign_facts(self):
        for variant in ('unheld','three-backings','wrong-owner','wrong-request','wrong-held','wrong-status','unaccepted-response'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_,fault=self.fault_fixture(Path(tmp))
                if variant!='unheld': self.held_fault_create(trace,fault)
                trace.backings[trace.server]={0x40000,0x41000,0x42000,0x43000}
                if variant=='three-backings':trace.backings[trace.server].remove(0x43000)
                request=5 if variant=='wrong-request' else 3
                self.actor_response(trace,fault,request,app=203 if variant=='wrong-status' else 204)
                if variant=='unaccepted-response':trace.active_accept[trace.server]['response']=None
                row=(0x343,1536 if variant=='wrong-owner' else fault,request,204,8 if variant=='wrong-held' else 4)
                with self.assertRaises(Core0Error):trace.observe(row)
                self.assertFalse(trace.peer_state[fault].get('seen_global_denial',False))

    def test_fault_destroy_requires_actual_held_denial_and_matching_release(self):
        for variant in ('unbacked','before-denial','wrong-request','other-owner','missing-release','unaccepted-response','release-request'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_,fault=self.fault_fixture(Path(tmp))
                if variant!='unbacked':
                    self.held_fault_create(trace,fault)
                    if variant!='before-denial':self.held_fault_denial(trace,fault)
                    self.actor_response(trace,fault,4,release=None if variant=='missing-release' else 0x40000)
                if variant=='unaccepted-response':trace.active_accept[trace.server]['response']=None
                if variant=='release-request':trace.actual_buffer_releases[-1]['request']=6
                row=(0x345,1536 if variant=='other-owner' else fault,4,1,6 if variant=='wrong-request' else 4)
                with self.assertRaises(Core0Error):trace.observe(row)
                self.assertFalse(any(r['confirmed'] for r in trace.actual_buffer_releases))

    def test_fault_replacement_requires_later_generation_of_released_slot(self):
        for variant in ('same-generation','other-slot','without-denial','without-release'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_,fault=self.fault_fixture(Path(tmp))
                self.held_fault_create(trace,fault)
                if variant!='without-denial':self.held_fault_denial(trace,fault)
                if variant not in {'without-denial','without-release'}:self.held_fault_release(trace,fault)
                slot=1 if variant=='other-slot' else 0
                handle=4 if variant=='same-generation' else 8|slot
                if 0x40000+slot*4096 in trace.backings[trace.server]:trace.backings[trace.server].remove(0x40000+slot*4096)
                self.actor_response(trace,fault,5,allocation=0x40000+slot*4096)
                with self.assertRaises(Core0Error):trace.observe((0x341,fault,handle,64,1))

    def test_fault_create_and_final_binary_requests_are_exact_and_bounded(self):
        for request in (2,3,257):
            with self.subTest(create_request=request),tempfile.TemporaryDirectory() as tmp:
                trace,_,fault=self.fault_fixture(Path(tmp))
                self.actor_response(trace,fault,request,allocation=0x40000)
                with self.assertRaisesRegex(Core0Error,'bounded successful Create'):
                    trace.observe((0x341,fault,4,64,1))
        with tempfile.TemporaryDirectory() as tmp:
            trace,_,fault=self.fault_fixture(Path(tmp))
            self.held_fault_create(trace,fault);self.held_fault_denial(trace,fault);self.held_fault_release(trace,fault)
            self.actor_response(trace,fault,5,allocation=0x40000);trace.observe((0x341,fault,8,64,1))
            with self.assertRaisesRegex(Core0Error,'actual final Write/Read'):
                trace.observe((0x342,fault,8,checker.digest(checker.pattern(7,fault,16)),16))

    def test_missing_or_foreign_server_acceptance_cannot_validate_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp))
            trace.begin_action({'kind':'rpc','index':7,'words':[3,1,4,0,128],'data_hex':'','epoch':1})
            trace.current=1024
            with self.assertRaisesRegex(Core0Error,'preceding actual accepted'):
                trace.client(response())
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp));self.accept_read(trace,bytes(128))
            trace.pending_rpc['server_key'][2]=1536
            with self.assertRaisesRegex(Core0Error,'preceding actual accepted'):
                trace.client(response())

    def test_distinguishing_append_read_mismatch_preserves_actual_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,session=self.fixture(Path(tmp));expected=bytes(127)+b'\xff';self.accept_read(trace,expected)
            actual=response(data=bytes(128))
            with self.assertRaisesRegex(Core0Error,'independent Buffer reference mismatch'):
                trace.client(actual)
            self.assertEqual(session.report['service_failure_category'],'buffer-byte-reference')
            self.assertEqual(session.report['failed_rpc']['response']['data_hex'],bytes(128).hex())
            self.assertEqual(session.report['failed_rpc']['input']['words'],[3,1,4,0,128])
            self.assertEqual(trace.model.buffers[4]['data'],expected)

    def test_client_wakeup_before_server_reply_record_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp));self.accept_read(trace,bytes(128))
            trace.client(response())
            self.assertEqual(len(trace.rpc_pairs),1)
            self.assertIn(512,trace.active_accept)
            trace.current=512;trace.observe((0x327,512,99,0,0))
            self.assertNotIn(512,trace.active_accept)

    def test_actual_server_reply_snapshot_survives_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp));self.accept_read(trace,bytes(128))
            trace.client(response())
            trace.current=512;trace.observe((0x327,512,99,0,0))
            self.assertEqual(trace.replies[0]['key'], (512,99,1024))
            self.assertIsInstance(trace.replies[0]['key'], tuple)
            snapshot=trace.snapshot()
            self.assertEqual(snapshot['server_replies'][0]['key'], [512,99,1024])
            self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)
            self.assertEqual(trace.accepted_result(512,99,1024)['key'], (512,99,1024))

    def test_expiry_cannot_release_shadow_before_actual_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp));trace.current=512
            trace.model.foreign_created(4);trace.foreign[4]={'owner':1536,'epoch':1,'capacity':128}
            trace.backings[512]={0x40000}
            trace.observe((0x324,512,0x40000,0,0x40000))
            trace.observe((0x325,512,4,1536,100))
            self.assertIn(4,trace.model.foreign)
            with self.assertRaisesRegex(Core0Error,'deadline/time'):
                trace.observe((0x326,512,99,0,1))
            self.assertIn(4,trace.model.foreign)

    def test_lease_scan_inside_accepted_call_defers_effect_until_exact_expiry(self):
        # These are ordered host observer fixtures, not generated guest evidence.
        for operation in (3,1):
            for variant in ('valid','wrong-owner','wrong-generation','before-deadline','missing-marker'):
                with self.subTest(operation=operation,variant=variant),tempfile.TemporaryDirectory() as tmp:
                    trace,_=self.fixture(Path(tmp))
                    owner=trace.cli if operation==3 else 1536
                    if operation==3:
                        trace.model.buffers[4]={'capacity':64,'data':b'x'}
                        trace.model.generations[0]=1
                        trace.backings[512]={0x40000}
                    else:
                        for handle in (4,5,6,7):
                            trace.model.foreign_created(handle)
                            trace.foreign[handle]={'owner':owner,'epoch':1,'capacity':64}
                        trace.backings[512]={0x40000,0x41000,0x42000,0x43000}
                    action={'kind':'rpc','index':7,'words':[operation,1,4 if operation==3 else 0,0,1 if operation==3 else 64],
                            'data_hex':'','epoch':1,'expected_transport':0}
                    trace.begin_action(action)
                    trace.observe((0xf3,512,0x82004000,1,90))
                    trace.observe((0x321,512,99,trace.cli,114))
                    before=trace.remaining
                    trace.observe((0x324,512,0x40000,0,0x40000))
                    self.assertEqual(trace.remaining,before+1)
                    self.assertIn(4,trace.model.buffers if operation==3 else trace.model.foreign)
                    self.assertIn(4,trace.pending_rpc['reference'].buffers if operation==3 else trace.pending_rpc['reference'].foreign)
                    with self.assertRaisesRegex(Core0Error,'unmatched or unconfirmed'):
                        checker.qualification(trace)
                    # A genuine SSIP scheduling sequence can interrupt the gap
                    # between the release syscall record and its expiry markers.
                    trace.observe((0xf2,512,1,1,0x10000))
                    trace.observe((0xf3,2048,0x82003000,1,110))
                    trace.observe((0xf2,2048,1,2,0x10000))
                    trace.observe((0xf3,512,0x82004000,2,120))
                    if variant=='missing-marker':
                        with self.assertRaisesRegex(Core0Error,'actual deadline/time'):
                            trace.observe((0x326,512,150,0,1))
                        with self.assertRaisesRegex(Core0Error,'successful Destroy response'):
                            trace.observe((0x323,512,99,201,64))
                        continue
                    expiry=(0x325,512,8 if variant=='wrong-generation' else 4,
                            2048 if variant=='wrong-owner' else owner,100)
                    if variant in ('wrong-owner','wrong-generation'):
                        with self.assertRaisesRegex(Core0Error,'witnessed live full owner/handle'):
                            trace.observe(expiry)
                        self.assertFalse(trace.actual_buffer_releases[-1]['confirmed'])
                        continue
                    trace.observe(expiry)
                    if variant=='before-deadline':
                        with self.assertRaisesRegex(Core0Error,'actual deadline/time'):
                            trace.observe((0x326,512,99,0,1))
                        continue
                    trace.observe((0x326,512,150,0,1))
                    self.assertNotIn(4,trace.model.buffers if operation==3 else trace.model.foreign)
                    self.assertEqual(trace.pending_rpc['actual_backing_count'],len(trace.backings[512]))
                    self.assertTrue(trace.actual_buffer_releases[-1]['confirmed'])
                    self.assertEqual(trace.actual_buffer_releases[-1]['kind'],'expiry')
                    if operation==1:
                        trace.observe((0x322,512,0x40000,0,0x40000))
                    trace.observe((0x323,512,99,201 if operation==3 else 0,64))
                    trace.observe((0xf2,512,1,3,0x10000))
                    trace.observe((0xf3,1024,0x82001000,1,200))
                    reply=response(op=operation,status=201 if operation==3 else 0,
                                   handle=0 if operation==3 else 8,length=0,count=0,data=b'')
                    reply['detail']=0 if operation==3 else 64
                    trace.client(reply)
                    trace.require_settled_releases()
                    self.assertEqual(trace.rpc_pairs[-1]['response'],reply)
    def query_fixture(self, directory, *, sample_delta=-1, pc=0x10024, reason=1):
        """Ordered host fixture, never a replacement for real guest evidence."""
        trace,session=self.fixture(directory,'service-development')
        session.events=[{"fixture_prefix":i} for i in range(7)]
        def emit(row):
            raw=('K1'+''.join(f' {word:016x}' for word in row)+'\n').encode()
            event,tail=decode_uart(raw)
            self.assertFalse(tail)
            session.events.append(event[0]);trace.observe(row);trace.events.append(list(row))
        trace.current=1536
        emit((0x331,1536,1,114,2))
        emit((0xf2,1536,3,0,0x10020))
        emit((0xf3,512,0x82004000,1,100))
        emit((0x321,512,99,1536,130))
        emit((0xf2,512,reason,1,pc))
        before=trace.remaining
        action={'kind':'diagnostic','index':len(session.events),'words':[0x31,2048,0,0,0],'expected_status':0}
        trace.begin_action(action)
        emit((0xfc,2048,2,3,100))
        query=(0xf7,0x31,0,before+sample_delta,2048)
        return trace,session,emit,query,before

    def finish_query_allocation(self,trace,emit):
        emit((0xf3,512,0x82004000,2,120))
        emit((0x322,512,0x40000,0,0x40000))
        emit((0x323,512,99,0,64))
        emit((0xf2,512,1,2,0x10000))
        emit((0xf3,1536,0x82002000,1,130))
        emit((0x335,1536,4,64,1))
        emit((0xf2,1536,3,2,0x10020))
        emit((0xf3,512,0x82004000,3,140))
        emit((0x327,512,99,0,0))
        emit((0xf2,512,6,2,0x10020))

    def test_deferred_query_requires_exact_matching_effect_and_fresh_settled_query(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,session,emit,query,before=self.query_fixture(Path(tmp))
            emit(query)
            sample=trace.diagnostic_frame_samples[-1]
            self.assertEqual(sample['record'],list(query))
            self.assertEqual(sample['record_accounting_at_query'],before)
            self.assertEqual(sample['acceptance'],[512,99,1536])
            self.assertIsNone(sample['reconciliation'])
            with self.assertRaisesRegex(Core0Error,'unresolved diagnostic'):
                checker.qualification(trace)
            self.finish_query_allocation(trace,emit)
            self.assertEqual(trace.remaining,query[3])
            self.assertEqual(sample['reconciliation']['record'],[0x322,512,0x40000,0,0x40000])
            self.assertEqual(sample['reconciliation']['acceptance'],sample['acceptance'])
            self.assertGreater(sample['reconciliation']['index'],sample['index'])
            with self.assertRaisesRegex(Core0Error,'fresh exact settled query'):
                trace.require_settled_frame_samples()
            trace.begin_action({'kind':'diagnostic','index':len(session.events),'words':[0x31,2048,0,0,0]})
            emit((0xfc,2048,2,3,101));emit((0xf7,0x31,0,trace.remaining,2048))
            trace.require_settled_frame_samples()
            self.assertTrue(trace.diagnostic_frame_samples[-1]['settled'])
            self.assertEqual(trace.diagnostic_frame_samples[0]['record'],list(query))
            snapshot=trace.snapshot();self.assertEqual(snapshot,json.loads(json.dumps(snapshot)))

    def test_deferred_release_sample_needs_exact_release_and_confirmed_destroy(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,session,emit,query,_=self.query_fixture(Path(tmp),sample_delta=1)
            # Prior live backing/owner is fixture setup, not guest evidence.
            trace.backings[512]={0x40000};trace.remaining-=1
            trace.model.foreign_created(4);trace.foreign[4]={'owner':1536,'epoch':1,'capacity':64}
            trace.peer_state[1536]['temporary']=4
            query=(0xf7,0x31,0,trace.remaining+1,2048);emit(query)
            emit((0xf3,512,0x82004000,2,120));emit((0x324,512,0x40000,0,0x40000))
            self.assertEqual(trace.diagnostic_frame_samples[-1]['reconciliation']['record'],[0x324,512,0x40000,0,0x40000])
            emit((0x323,512,99,0,64));emit((0xf2,512,1,2,0x10000))
            emit((0xf3,1536,0x82002000,1,130));emit((0x337,1536,4,1,0))
            self.assertTrue(trace.actual_buffer_releases[-1]['confirmed'])
            emit((0xf2,1536,3,2,0x10020));emit((0xf3,512,0x82004000,3,140))
            emit((0x327,512,99,0,0));emit((0xf2,512,6,2,0x10020))
            trace.begin_action({'kind':'diagnostic','index':len(session.events),'words':[0x31,2048,0,0,0]})
            emit((0xfc,2048,2,3,101));emit((0xf7,0x31,0,trace.remaining,2048))
            trace.require_settled_releases();trace.require_settled_frame_samples()

    def test_query_discrepancy_rejects_unexplained_or_non_return_boundary(self):
        for variant in ('no-request','response-present','wrong-pc','sleep','outside-count'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_,emit,query,_=self.query_fixture(Path(tmp),
                    pc=0x10000 if variant=='wrong-pc' else 0x10020 if variant=='sleep' else 0x10024,
                    reason=3 if variant=='sleep' else 1,
                    sample_delta=513 if variant=='outside-count' else -1)
                if variant=='no-request':trace.active_accept.clear()
                if variant=='response-present':trace.active_accept[512]['response']=[0x323,512,99,0,64]
                with self.assertRaisesRegex(Core0Error,'unresolved full Server request at syscall return'):
                    emit(query)
                self.assertFalse(trace.diagnostic_frame_samples)

    def test_next_backing_record_must_be_exact_success_for_same_full_request(self):
        for variant in ('wrong-count','failed-allocation','wrong-full-caller','unrelated-frame-effect'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_,emit,query,_=self.query_fixture(Path(tmp),sample_delta=-2 if variant=='wrong-count' else -1)
                emit(query)
                if variant=='unrelated-frame-effect':
                    with self.assertRaisesRegex(Core0Error,'unrelated frame effect'):
                        emit((0xf6,2048,trace.remaining,trace.remaining+20,0))
                else:
                    emit((0xf3,512,0x82004000,2,120))
                    if variant=='wrong-full-caller':trace.active_accept[512]['key']=(512,99,1024)
                    with self.assertRaisesRegex(Core0Error,'next exact same-request backing effect'):
                        emit((0x322,512,0x40000,38,0) if variant=='failed-allocation' else (0x322,512,0x40000,0,0x40000))
                self.assertIsNone(trace.diagnostic_frame_samples[0]['reconciliation'])

    def test_never_settled_query_remains_failure_after_unrelated_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_,emit,query,_=self.query_fixture(Path(tmp));emit(query)
            emit((0xf3,2048,0x82003000,1,120));emit((0xf2,2048,1,2,0x10000))
            with self.assertRaisesRegex(Core0Error,'unresolved diagnostic frame samples'):
                trace.require_settled_frame_samples()
            with self.assertRaisesRegex(Core0Error,'unresolved diagnostic frame samples'):
                checker.qualification(trace)

    def test_live_diagnostic_waits_for_effect_without_rechecking_stale_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,session,emit,query,_=self.query_fixture(Path(tmp))
            trace.pending_ack=trace.pending_ack_action=None
            rows=iter([query,(0xf3,512,0x82004000,2,120),(0x322,512,0x40000,0,0x40000)])
            session.send=lambda *_args,**_kwargs:None
            waits=[]
            def until(predicate):
                waits.append(0)
                while not predicate():
                    emit(next(rows));waits[-1]+=1
            with patch.object(trace,'until',side_effect=until):
                result=trace.diagnostic(0x31,2048)
            self.assertEqual(result,list(query));self.assertEqual(waits,[1,2])
            self.assertIsNotNone(trace.diagnostic_frame_samples[-1]['reconciliation'])

    def test_quota_claim_needs_actual_server_denial_and_full_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp));trace.current=1536
            with self.assertRaisesRegex(Core0Error,'authenticated Server denial'):
                trace.observe((0x338,1536,123,204,1))
            trace.replies.append({'key':(512,123,1536),'response':[0x323,512,123,204,64],'actual_backing_count':3})
            with self.assertRaisesRegex(Core0Error,'four actual'):
                trace.observe((0x338,1536,123,204,1))
            trace.replies[-1]['actual_backing_count']=4
            trace.observe((0x338,1536,123,204,1))

    def test_finish_boundary_requires_sleep_receive_and_settled_real_effects(self):
        for variant in ('valid','server-running','peer-runnable','accepted','expiry','release','allocation'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_=self.fixture(Path(tmp))
                trace.tasks[512]['state']=5
                trace.tasks[1536]['state']=4
                if variant=='server-running':trace.tasks[512]['state']=3
                elif variant=='peer-runnable':trace.tasks[1536]['state']=2
                elif variant=='accepted':trace.active_accept[512]={'key':(512,99,1024)}
                elif variant=='expiry':trace.pending_expiry=[0x325,512,4,1536,100]
                elif variant=='release':trace.actual_buffer_releases.append({'confirmed':False})
                elif variant=='allocation':trace.new_allocations[(512,0x40000)]={'claimed':False}
                self.assertEqual(trace.service_quiescent(1536),variant=='valid')

    def test_terminal_capture_closes_observed_pages_without_draining_continuous_service(self):
        for variant in ('running-next-request','release','expiry','frame-sample'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_=self.fixture(Path(tmp))
                trace.tasks[512]['state']=2
                trace.tasks[1536]['state']=5
                trace.active_accept[512]={'key':(512,99,1536)}
                if variant=='release':trace.actual_buffer_releases.append({'confirmed':False})
                elif variant=='expiry':trace.pending_expiry=[0x325,512,4,1536,100]
                elif variant=='frame-sample':
                    trace.diagnostic_frame_samples.append({'status':'deferred','reconciliation':None})
                self.assertFalse(trace.service_quiescent(1536))
                self.assertEqual(trace.terminal_boundary(b''),variant=='running-next-request')
                if variant=='running-next-request':trace.require_settled_releases()
                else:
                    with self.assertRaises(Core0Error):trace.require_settled_releases()
                # The earlier live milestone remains stronger; terminal
                # capture still rejects any missing already observed frame.
                trace.session.events.append({'kind':'kernel','value':[1,2,3,4,5]})
                with self.assertRaisesRegex(Core0Error,'observed prefix'):
                    trace.terminal_boundary(b'')

    def test_restart_requires_actual_cli_identity_and_unexpired_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace,_=self.fixture(Path(tmp),'service-development')
            trace.pending_ack=(0x41,1024);trace.observe((0x301,512,1024,0,0))
            trace.pending_rpc={'expected_transport':96};trace.current=512
            with self.assertRaisesRegex(Core0Error,'matching delivered Reply'):
                trace.observe((0x302,512,1536,51,1))
            trace.observe((0x302,512,1024,51,1))
            with self.assertRaisesRegex(Core0Error,'unexpired deadline'):
                trace.observe((0x303,512,0x10000,100,100))
            trace.observe((0x303,512,0x10000,100,99))

    def test_peer_destroy_completion_keeps_its_authenticated_server_epoch(self):
        for variant in ('valid','epoch','server','owner','handle','round','response','confirmed'):
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as tmp:
                trace,_=self.fixture(Path(tmp))
                peer=1536
                trace.tasks[peer]['start']=True
                self.actor_response(trace,peer,249,allocation=0x41000)
                trace.observe((0x335,peer,5,64,1))
                trace.peer_state[peer]['round']=79
                self.actor_response(trace,peer,251,release=0x41000)
                release=trace.actual_buffer_releases[-1]
                # The old reply is complete; only its caller's witness is late.
                trace.server=2560;trace.epoch=2;trace.current=peer
                row=[0x337,peer,5,1,79]
                if variant=='epoch':row[3]=2
                elif variant=='server':release['server']=2560
                elif variant=='owner':release['owner']=1024
                elif variant=='handle':release['handle']=9
                elif variant=='round':row[4]=78
                elif variant=='response':trace.active_accept[512]['response'][3]=204
                elif variant=='confirmed':release['confirmed']=True
                if variant=='valid':
                    trace.observe(tuple(row))
                    self.assertTrue(release['confirmed'])
                    self.assertEqual(trace.peer_state[peer]['temporary'],0)
                    with self.assertRaises(Core0Error):trace.observe(tuple(row))
                else:
                    with self.assertRaises(Core0Error):trace.observe(tuple(row))

    def test_exact_inputs_and_semantic_cleanup_suffix_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);trace,session=self.fixture(directory)
            initial=[(0xa,0x87e00000,1,512,0x82000000),(0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,0x1446),
                     (0xc1,2,3,1,0),(0xc2,17,22,22,123),(0xd3,0x82000000,0x8000000000082000,500,0),
                     (0xf0,1,8,512,10000),(0xb0,1,16,16,497)]
            controls=initial+[r for rows in trace.grants.values() for r in rows]
            controls += [(0xb4,512,51,416,0),(0xf1,1024,1,1,0x82001000),(0xf1,1536,2,2,0x82002000),
                         (0xf1,2048,3,3,0x82003000),(0xf1,512,0,1,0x82004000),(0x300,512,51,1,1024),
                         (0xf3,1024,0x82001000,1,100),(0x310,1024,1,trace.grants[1024][0][2],trace.grants[1024][1][2])]
            raw=b''.join(('K1'+''.join(f' {w:016x}' for w in row)+'\n').encode() for row in controls)
            import struct
            payload=struct.pack('<8Q',APPLICATION_MAGIC,1,7,0,0,0,0,1)
            raw += b'LMO1'+struct.pack('<BBH',1,0,64)+payload
            action={'kind':'rpc','index':len(controls),'words':[7,0,0,0,0],'data_hex':'','epoch':1}
            (directory/'sent.bin').write_bytes(command(7))
            report={'wire_format':'kernel-buffer-uart-v1','complete_raw_coverage':True,
                    'observed':{'protocol':'buffer-service-J-v1','actions':[action]}}
            events,_=decode_uart(raw);report['wire_events']=events;(directory/'received.bin').write_bytes(raw)
            with patch.object(checker,'qualification',return_value={'fixture_only':True}):
                self.assertTrue(checker.validate_replay(ROOT,session.image,report,directory)['complete_semantic_replay'])
                suffix=('K1'+''.join(f' {w:016x}' for w in (0xdead,0,0,0,0))+'\n').encode()
                (directory/'received.bin').write_bytes(raw+suffix);report['wire_events']=decode_uart(raw+suffix)[0]
                with self.assertRaises(Core0Error):checker.validate_replay(ROOT,session.image,report,directory)
            (directory/'sent.bin').write_bytes(command(7)+b'\x00')
            with self.assertRaisesRegex(Core0Error,'retained input bytes'):
                checker.validate_replay(ROOT,session.image,report,directory)

    def test_partial_failed_replay_accepts_only_actual_append_last_byte_counterexample(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);base,session=self.fixture(directory)
            initial=[(0xa,0x87e00000,1,512,0x82000000),(0xc0,0x534543414c4c0001,0x1b1b1f1818,0xb1ff,0x1446),
                     (0xc1,2,3,1,0),(0xc2,17,22,22,123),(0xd3,0x82000000,0x8000000000082000,500,0),
                     (0xf0,1,8,512,10000),(0xb0,1,16,16,497)]
            records=initial+[r for rows in base.grants.values() for r in rows]
            records += [(0xb4,512,51,416,0),(0xf1,1024,1,1,0x82001000),(0xf1,1536,2,2,0x82002000),
                        (0xf1,2048,3,3,0x82003000),(0xf1,512,0,1,0x82004000),(0x300,512,51,1,1024),
                        (0xf3,512,0x82004000,1,100),(0x320,512,1,base.grants[512][1][2],base.grants[512][0][2]),
                        (0xf2,512,6,0,0x10020),(0xf3,1024,0x82001000,1,110),
                        (0x310,1024,1,base.grants[1024][0][2],base.grants[1024][1][2])]
            raw=b''.join(('K1'+''.join(f' {w:016x}' for w in row)+'\n').encode() for row in records)
            actions=[];sent=b''
            import struct
            def control(row):
                nonlocal raw
                raw += ('K1'+''.join(f' {w:016x}' for w in row)+'\n').encode()
            def output(op,length,count,data=b'',capacity=256):
                nonlocal raw
                payload=struct.pack('<8Q',APPLICATION_MAGIC,1,op,1,4,length,count,capacity)+data
                raw += b'LMO1'+struct.pack('<BBH',1,0,len(payload))+payload
            for i,(op,length,data) in enumerate([(1,256,b''),(2,128,b'A'*128),(4,128,b'B'*127+b'\xff'),(3,128,b'')],1):
                off=128 if op==3 else 0
                index=len(decode_uart(raw)[0]);words=[op,1,0 if op==1 else 4,off,length]
                actions.append({'kind':'rpc','index':index,'words':words,'data_hex':data.hex(),'epoch':1,'expected_transport':0})
                sent += command(*words,data=data)
                control((0xf2,1024,6,i-1,0x10020));control((0xf3,512,0x82004000,i+1,120+i*20))
                if i>1:control((0x327,512,i-1,0,0))
                control((0x321,512,i,1024,((7+i)<<4)|2))
                if op==1:control((0x322,512,0x40000,0,0x40000))
                control((0x323,512,i,0,192 if op==3 else 64))
                control((0xf2,512,1,i,0x10000));control((0xf3,1024,0x82001000,i+1,130+i*20))
                output(op,0 if op==1 else 128 if op==2 else 256,0 if op==1 else 128,
                       b'B'*127+b'\x00' if op==3 else b'')
            events,_=decode_uart(raw);live=SimpleNamespace(root=ROOT,image=session.image,binding=session.binding,report={},events=events[:7],records=[])
            trace=checker.ServiceTrace(live);cursor=0
            for index,event in enumerate(events[7:],7):
                if cursor<len(actions) and actions[cursor]['index']==index:
                    trace.begin_action(deepcopy(actions[cursor]));cursor+=1
                live.events.append(event)
                if event['kind']=='kernel':trace.observe(tuple(event['value']));trace.events.append(event['value'])
                else:
                    try:trace.client(event['value'])
                    except Core0Error:
                        self.assertEqual(index,len(events)-1)
            primary=deepcopy(live.report)
            saved_pending=trace.pending_rpc
            with patch.object(trace,'until',side_effect=Core0Error('settlement deadline')):
                trace.settle_reference_failure()
            self.assertEqual(live.report['service_failure_settlement']['status'],'FAIL')
            self.assertEqual(live.report['failed_rpc'],primary['failed_rpc'])
            self.assertEqual(live.report['service_failure_category'],'buffer-byte-reference')
            trace.pending_rpc=saved_pending
            background=[(0xf2,1024,3,4,0x10020),(0xf3,512,0x82004000,6,230),
                        (0x327,512,4,0,0),(0xf2,512,6,4,0x10020),
                        (0xf3,1536,0x82002000,1,240),(0xf2,1536,3,4,0x10020)]
            for row in background:control(row)
            complete_events=decode_uart(raw)[0]
            suffix=iter(complete_events[len(events):])
            def background_event():
                event=next(suffix);live.events.append(event);return event
            live.event=background_event
            trace.settle_reference_failure()
            self.assertEqual(live.report['service_failure_settlement']['status'],'PASS')
            self.assertEqual(live.report['failed_rpc'],primary['failed_rpc'])
            self.assertEqual(len(trace.actions),len(actions))
            self.assertIsNone(trace.pending_rpc)
            events=complete_events
            report={**live.report,'status':'FAIL','wire_format':'kernel-buffer-uart-v1','complete_raw_coverage':True,
                    'wire_events':events,'service_progress':trace.snapshot()}
            (directory/'received.bin').write_bytes(raw);(directory/'sent.bin').write_bytes(sent)
            proof=checker.validate_reference_failure(ROOT,session.image,report,directory)
            self.assertEqual(proof['expected_data_hex'],(b'B'*127+b'\xff').hex())
            self.assertEqual(proof['actual_data_hex'],(b'B'*127+b'\x00').hex())
            for field,value in [('status','PASS'),('service_failure_category','buffer-response-reference')]:
                changed=deepcopy(report);changed[field]=value
                with self.assertRaises(Core0Error):checker.validate_reference_failure(ROOT,session.image,changed,directory)
            changed=deepcopy(report);changed['failed_rpc']['response']['data_hex']=bytes(128).hex()
            with self.assertRaises(Core0Error):checker.validate_reference_failure(ROOT,session.image,changed,directory)
            for field,value in [('status','FAIL'),('events_after',report['service_failure_settlement']['events_before']),
                                ('events_before',report['service_failure_settlement']['events_before']+1)]:
                changed=deepcopy(report);changed['service_failure_settlement'][field]=value
                with self.assertRaises(Core0Error):checker.validate_reference_failure(ROOT,session.image,changed,directory)
            suffix=('K1'+''.join(f' {w:016x}' for w in (0xdead,0,0,0,0))+'\n').encode()
            (directory/'received.bin').write_bytes(raw+suffix);report['wire_events']=decode_uart(raw+suffix)[0]
            with self.assertRaises(Core0Error):checker.validate_reference_failure(ROOT,session.image,report,directory)

    def test_post_cleanup_contradiction_writes_fail_with_distinct_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            class FixtureSession:
                def __init__(self,**kwargs):self.output_dir=directory;self.report={'status':'FAIL'}
                def __enter__(self):return self
                def __exit__(self,*args):self.report['status']='PASS';return False
                def finish(self,value):self.report['observed']=value
            with patch.object(sys,'argv',['check_kernel_buffer.py','--image',str(directory/'image.elf'),'--output-dir',str(directory)]), \
                 patch.object(checker,'BufferSession',FixtureSession),patch.object(checker,'check',return_value={'fixture_only':True}), \
                 patch.object(checker,'runner_inputs',return_value={'fixture':'hash'}), \
                 patch.object(checker,'replay_aftercleanup',side_effect=Core0Error('late contradiction')):
                self.assertEqual(checker.main(),1)
            value=json.loads((directory/'result.json').read_text())
            self.assertEqual(value['status'],'FAIL')
            self.assertEqual(value['service_failure_category'],'post-cleanup-semantic-replay')


if __name__=='__main__':unittest.main(verbosity=2)
