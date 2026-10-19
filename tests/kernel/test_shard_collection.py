"""Host-only shard/collector admission fixtures; no synthetic target PASS claims."""
import copy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from check_kernel import (artifact_inventory,collect_shards,matrix,merge_rows,revalidate_collected,
    row_checkers,same_source_event,shard_indices,validate_retained_row_result,
    validate_row_result,validate_shard,validate_source_event,check)
from core0_common import Core0Error,sha256,write_json


def host_row(index):
    profile=dict(zip(('configuration','stage','optimization'),matrix()[index]))
    return {'index':index,'row':list(matrix()[index]),'status':'PASS',
            'images':[{**profile,'image':'explicit-host-fixture'}],
            'observations':[{**profile,'role':role,'qemu_sessions':count,'syscall_user_instances':3 if role=='syscall' else 0,'status':'PASS'}
                            for _,_,role,count in row_checkers(matrix()[index])],
            'invocations':[],'supervision':{'index':index,'row':list(matrix()[index]),'explicit_host_fixture':True}}


class ShardSelectionTests(unittest.TestCase):
    def test_fixed_halves_reconstruct_every_ordered_observation(self):
        self.assertEqual(shard_indices('O0'),tuple(range(10)))
        self.assertEqual(shard_indices('O2'),tuple(range(10,20)))
        self.assertEqual(shard_indices(),shard_indices('O0')+shard_indices('O2'))
        for optimization in ('O0','O2'):
            report={};merge_rows(report,[host_row(i) for i in shard_indices(optimization)],shard_indices(optimization),complete=True)
            self.assertEqual((len(report['images']),len(report['observations']),sum(x['qemu_sessions'] for x in report['observations']),sum(x['syscall_user_instances'] for x in report['observations'])),(10,12,14,3))
        for wrong in ('O1','O3','',True):
            with self.assertRaises(Core0Error):shard_indices(wrong)

    def test_collector_clean_rejects_before_touching_downloaded_shards(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            path=Path(temporary); marker=path/'keep';marker.write_bytes(b'original evidence')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/check_kernel.py'),'--collect-shard','anything','--clean','--work-dir',str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2)
            self.assertEqual(marker.read_bytes(),b'original evidence')

    def test_inventory_detects_raw_mutation_and_only_excludes_declared_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work=root/'shard';work.mkdir();(work/'received.bin').write_bytes(b'real raw fixture')
            original=artifact_inventory(root,work)
            for name in ('result.json','ci.log','ci-source-original.json'):(work/name).write_text('diagnostic')
            (work/'cache').mkdir();(work/'cache/state').write_text('ephemeral')
            self.assertEqual(artifact_inventory(root,work),original)
            (work/'received.bin').write_bytes(b'changed');self.assertNotEqual(artifact_inventory(root,work),original)
            (work/'foreign').symlink_to(work/'received.bin')
            with self.assertRaisesRegex(Core0Error,'symlink'):artifact_inventory(root,work)


    def test_shard_final_inventory_failure_or_overrun_never_retains_pass(self):
        for mode in ('error','deadline'):
            with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
                work=Path(temporary)/'run';identity={'commit':'fixture','tree':'fixture','clean':True}
                def run_rows(**kwargs):kwargs['progress']([host_row(i) for i in shard_indices('O0')])
                def census(*args):
                    if mode=='error':raise Core0Error('fixture final census failure')
                    time.sleep(.1);return {}
                command=SimpleNamespace(argv=('host-fixture',),returncode=0,stdout=b'Ran 23 tests in 0.1s\nOK\n',stderr=b'')
                with patch('check_kernel.require_tools'),patch('check_kernel.source_identity',return_value=identity), \
                     patch('check_kernel.source_inputs',return_value={}),patch('check_kernel.acceptance_inputs',return_value={}), \
                     patch('check_kernel.run_bounded',return_value=command),patch('check_kernel.run_matrix_rows',side_effect=run_rows), \
                     patch('check_kernel.artifact_inventory',side_effect=census),self.assertRaises(Core0Error):
                    check(root=ROOT,work_dir=work,clean=False,timeout=300,qemu_timeout=90,deadline=.05 if mode=='deadline' else 1,shard='O0')
                self.assertEqual(json.loads((work/'result.json').read_text())['status'],'FAIL')

    def test_shard_scope_typing_and_complete_retained_raw_inventory(self):
        identity={'commit':'fixture','tree':'fixture','clean':True}
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            campaign=Path(temporary);work=campaign/'shards/O0';work.mkdir(parents=True);path=work/'result.json'
            raw=work/'received.bin';raw.write_bytes(b'original raw host fixture')
            event=validate_source_event(ROOT,None,identity)
            value={'status':'PASS','production_scope':'optimization-shard','shard':'O0','matrix_indices':list(shard_indices('O0')),
                   'jobs':1,'highest_exercised_gate':'not_run','required_gate_prefix':'A-E','source':identity,
                   'source_inputs':{},'acceptance_inputs':{},'deadline_seconds':2400,'command_timeout_seconds':300,
                   'qemu_timeout_seconds':90,'production_deadline_monotonic':123,'elapsed_seconds':10,'images':[{}]*10,'observations':[{}]*12,
                   'qemu_sessions':14,'syscall_user_instances':3,'event_provenance':event,'artifact_inventory':artifact_inventory(ROOT,work)}
            for change in ({'jobs':True},{'elapsed_seconds':True},{'elapsed_seconds':float('nan')},{'elapsed_seconds':2401},{'highest_exercised_gate':'E'}):
                write_json(path,{**value,**change})
                with self.subTest(change=change),self.assertRaisesRegex(Core0Error,'scope'):
                    validate_shard(ROOT,path,'O0',identity=identity,sources={},consumers={},event=event,campaign_root=campaign)
            write_json(path,value);raw.write_bytes(b'mutated raw host fixture')
            with self.assertRaisesRegex(Core0Error,'artifact/action/raw/log inventory'):
                validate_shard(ROOT,path,'O0',identity=identity,sources={},consumers={},event=event,campaign_root=campaign)


class EventBindingTests(unittest.TestCase):
    def event(self):
        identity={'commit':'a'*40,'tree':'b'*40,'clean':True}
        value={'schema_version':1,'checkout':{**identity,'parents':['d'*40,'c'*40]},
               'inputs':{name:sha256(ROOT/name) for name in ('flake.nix','flake.lock','lean-toolchain','tooling/toolchain-lock.json')},
               'event':'pull_request','repository':'fixture/fixture','ref':'refs/pull/12/merge','job':'kernel-rv64-shard',
               'run_id':'123','run_attempt':'1','pull_request':{'number':12,'head':'c'*40,'base':'d'*40},
               'runner':{'os':'Linux','arch':'X64'},'scope':'explicit host fixture'}
        return identity,value

    def test_run_attempt_source_head_base_pins_and_only_approved_job_difference(self):
        identity,event=self.event()
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            path=Path(temporary)/'source.json';write_json(path,event)
            producer=validate_source_event(ROOT,path,identity,expected_job='kernel-rv64-shard')
            collector=copy.deepcopy(producer);collector['record']['job']='kernel-rv64'
            self.assertTrue(same_source_event(producer,collector))
            for key,value in (('run_id','124'),('run_attempt','2'),('event','push'),('ref','refs/heads/elsewhere'),('repository','other/repo')):
                changed=copy.deepcopy(collector);changed['record'][key]=value;self.assertFalse(same_source_event(producer,changed))
            changed=copy.deepcopy(collector);changed['record']['pull_request']['head']='e'*40;self.assertFalse(same_source_event(producer,changed))
            for change in ({'job':'wrong'}, {'run_id':'0'}, {'run_attempt':'0'}, {'inputs':{}}, {'checkout':{**event['checkout'],'tree':'e'*40}},
                           {'pull_request':{**event['pull_request'],'base':'e'*40}}):
                write_json(path,{**event,**change})
                with self.subTest(change=change),self.assertRaises(Core0Error):validate_source_event(ROOT,path,identity,expected_job='kernel-rv64-shard')
            local=validate_source_event(ROOT,None,identity)
            self.assertFalse(same_source_event(local,collector));self.assertFalse(same_source_event(producer,local))
            self.assertTrue(same_source_event(local,copy.deepcopy(local)))


    def test_retained_ci_event_file_bytes_are_checked_not_only_embedded_record(self):
        identity,event=self.event()
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            campaign=Path(temporary);work=campaign/'shards/O0';work.mkdir(parents=True)
            event_path=work/'source-event.json';write_json(event_path,event)
            producer=validate_source_event(ROOT,event_path,identity,expected_job='kernel-rv64-shard')
            collector=copy.deepcopy(producer);collector['record']['job']='kernel-rv64'
            value={'status':'PASS','production_scope':'optimization-shard','shard':'O0','matrix_indices':list(shard_indices('O0')),
                   'jobs':1,'highest_exercised_gate':'not_run','required_gate_prefix':'A-E','source':identity,
                   'source_inputs':{},'acceptance_inputs':{},'deadline_seconds':2400,'command_timeout_seconds':300,
                   'qemu_timeout_seconds':90,'production_deadline_monotonic':123,'elapsed_seconds':10,
                   'images':[{}]*10,'observations':[{}]*12,'qemu_sessions':14,'syscall_user_instances':3,
                   'event_provenance':producer,'artifact_inventory':artifact_inventory(ROOT,work)}
            path=work/'result.json';write_json(path,value)
            with self.assertRaisesRegex(Core0Error,'row order'):
                validate_shard(ROOT,path,'O0',identity=identity,sources={},consumers={},event=collector,campaign_root=campaign)
            write_json(event_path,{**event,'run_attempt':'2'})
            with self.assertRaisesRegex(Core0Error,'source event differs'):
                validate_shard(ROOT,path,'O0',identity=identity,sources={},consumers={},event=collector,campaign_root=campaign)


class RetainedRowTests(unittest.TestCase):
    def fixture(self,work):
        directory=work/'rows/01';directory.mkdir(parents=True)
        request_path=directory/'request.json';receipt=directory/'supervisor.json'
        command=[sys.executable,'-c','pass']
        read_fd,write_fd=os.pipe()
        process=subprocess.Popen([sys.executable,str(ROOT/'scripts/kernel_row_supervisor.py'),'--parent-pid',str(os.getpid()),
            '--control-fd',str(read_fd),'--deadline',str(time.monotonic()+10),'--receipt',str(receipt),'--',*command],pass_fds=(read_fd,))
        os.close(read_fd)
        try:self.assertEqual(process.wait(timeout=10),0)
        finally:os.close(write_fd)
        supervisor=json.loads(receipt.read_text())
        request={'index':1,'row':list(matrix()[1]),'source':{},'source_inputs':{},
                 'acceptance_inputs':{'scripts/kernel_row_supervisor.py':sha256(ROOT/'scripts/kernel_row_supervisor.py')},
                 'finish_by':supervisor['deadline_monotonic'],'cache_dir':str(work/'cache/slot-0'),'slot':0}
        write_json(request_path,request)
        image_dir=work/'normal-supervisor-O0';image_dir.mkdir();image=image_dir/'image.elf';image.write_bytes(b'host fixture only')
        for name in ('audit.json','provenance.json'):(image_dir/name).write_text('{}')
        observation=work/'observed.json';observation.write_text('{}')
        profile=dict(zip(('configuration','stage','optimization'),matrix()[1]))
        row={'schema':'lemma-kernel-matrix-row/v1','status':'PASS',**{key:request[key] for key in ('index','row','source','source_inputs','acceptance_inputs','finish_by','cache_dir')},
             'request_sha256':sha256(request_path),'images':[{**profile,'image':str(image.relative_to(ROOT)),'sha256':sha256(image),
             'audit_sha256':sha256(image_dir/'audit.json'),'provenance_sha256':sha256(image_dir/'provenance.json')}],
             'observations':[{**profile,'role':'user','qemu_sessions':1,'syscall_user_instances':0,'status':'PASS','result':str(observation.relative_to(ROOT)),'sha256':sha256(observation)}],'invocations':[]}
        write_json(directory/'result.json',row)
        return request,request_path,receipt,command

    def test_live_then_retained_cleanup_cross_boot_never_inspects_foreign_pids(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary);request,path,receipt,command=self.fixture(work)
            with patch('check_kernel.row_command',return_value=command),patch('check_kernel.validate_session'):
                row=validate_row_result(ROOT,work,request,path,sha256(path),receipt)
                assessment=row['supervision'];self.assertTrue(assessment['process_absence']['all_absent'])
                retained=validate_retained_row_result(ROOT,work,request,path,sha256(path),receipt,assessment)
                self.assertEqual(retained['supervision'],assessment)
                for change in ({'all_absent':False},{'checked_identities':0},{'supervisor_sha256':'forged'},{'boot_id':'wrong'}):
                    bad=copy.deepcopy(assessment);bad['process_absence'].update(change)
                    with self.subTest(change=change),self.assertRaises(Core0Error):validate_retained_row_result(ROOT,work,request,path,sha256(path),receipt,bad)
                supervisor=json.loads(receipt.read_text());supervisor['owner']['boot_id']='explicit-foreign-boot-fixture';write_json(receipt,supervisor)
                foreign=copy.deepcopy(assessment);foreign['supervisor_sha256']=sha256(receipt)
                foreign['process_absence'].update(boot_id=supervisor['owner']['boot_id'],supervisor_sha256=sha256(receipt))
                with patch('kernel_row_supervisor.process_identity',side_effect=AssertionError('foreign PID lookup forbidden')):
                    self.assertEqual(validate_retained_row_result(ROOT,work,request,path,sha256(path),receipt,foreign)['supervision'],foreign)
                with self.assertRaisesRegex(Core0Error,'different producer boot'):validate_row_result(ROOT,work,request,path,sha256(path),receipt)

    def test_retained_claim_cannot_substitute_for_actual_child_wait(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary);request,path,receipt,command=self.fixture(work)
            with patch('check_kernel.row_command',return_value=command),patch('check_kernel.validate_session'):
                assessment=validate_row_result(ROOT,work,request,path,sha256(path),receipt)['supervision']
                supervisor=json.loads(receipt.read_text());supervisor['cleanup']['reaped']=[];write_json(receipt,supervisor)
                assessment['supervisor_sha256']=sha256(receipt);assessment['process_absence']['supervisor_sha256']=sha256(receipt)
                with self.assertRaisesRegex(Core0Error,'actual successful wait'):validate_retained_row_result(ROOT,work,request,path,sha256(path),receipt,assessment)


class CollectorTests(unittest.TestCase):
    def fixture(self,root):
        work=root/'build/kernel/ci-prefix';work.mkdir(parents=True)
        identity={'commit':'host-fixture','tree':'host-fixture','clean':True}
        values={}
        for opt in ('O0','O2'):
            path=work/'shards'/opt/'result.json';path.parent.mkdir(parents=True);write_json(path,{'explicit_host_fixture':opt,'status':'PASS','shard':opt,'elapsed_seconds':12})
            values[opt]=({'host_tests':23,'elapsed_seconds':12,'event_provenance':validate_source_event(root,None,identity)},[host_row(i) for i in shard_indices(opt)])
        return work,identity,values

    def context(self,identity,values):
        stack=ExitStack();stack.enter_context(patch('check_kernel.source_identity',return_value=identity))
        stack.enter_context(patch('check_kernel.source_inputs',return_value={}))
        stack.enter_context(patch('check_kernel.acceptance_inputs',return_value={}))
        stack.enter_context(patch('check_kernel.validate_shard',side_effect=lambda root,path,opt,**kwargs:values[opt]))
        return stack

    def test_collector_exact_pair_order_raw_counts_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work,identity,values=self.fixture(root)
            paths=tuple(work/'shards'/opt/'result.json' for opt in ('O2','O0'))
            with self.context(identity,values):
                for wrong in ((paths[0],),(paths[0],paths[0]),(paths[0],work/'elsewhere.json')):
                    with self.assertRaises(Core0Error):collect_shards(root=root,work_dir=work,shard_paths=wrong)
                result=collect_shards(root=root,work_dir=work,shard_paths=paths)
                self.assertEqual((len(result['images']),len(result['observations']),result['qemu_sessions'],result['syscall_user_instances']),(20,24,28,6))
                self.assertEqual([x['index'] for x in result['matrix_rows']],list(range(20)))
                self.assertEqual(result['event_provenance']['kind'],'local')
                revalidate_collected(root,work,work/'result.json',None)
                before=(work/'result.json').read_bytes()
                with self.assertRaisesRegex(Core0Error,'replace'):collect_shards(root=root,work_dir=work,shard_paths=paths)
                self.assertEqual((work/'result.json').read_bytes(),before)
                result['observations'].reverse();write_json(work/'result.json',result)
                with self.assertRaisesRegex(Core0Error,'differs'):revalidate_collected(root,work,work/'result.json',None)

    def test_combined_work_budget_rejects_bad_headers_overflow_and_forged_arithmetic(self):
        for elapsed in (True,float('nan'),0,2400):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);work,identity,values=self.fixture(root)
                path=work/'shards/O0/result.json';write_json(path,{'status':'PASS','shard':'O0','elapsed_seconds':elapsed})
                with self.context(identity,values),patch('check_kernel.validate_shard') as heavy,self.assertRaises(Core0Error):
                    collect_shards(root=root,work_dir=work,shard_paths=tuple(work/'shards'/opt/'result.json' for opt in ('O0','O2')))
                heavy.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work,identity,values=self.fixture(root)
            path=work/'shards/O0/result.json';write_json(path,{'status':'PASS','shard':'O0','elapsed_seconds':2399.95})
            def slow(root,path,opt,**kwargs):time.sleep(.1);return values[opt]
            with self.context(identity,values),patch('check_kernel.validate_shard',side_effect=slow),self.assertRaisesRegex(Core0Error,'deadline'):
                collect_shards(root=root,work_dir=work,shard_paths=tuple(work/'shards'/opt/'result.json' for opt in ('O0','O2')))
            failed=json.loads((work/'result.json').read_text());self.assertEqual(failed['status'],'FAIL')
            self.assertGreater(failed['computed_critical_path_work_seconds'],2400)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);work,identity,values=self.fixture(root)
            with self.context(identity,values):
                value=collect_shards(root=root,work_dir=work,shard_paths=tuple(work/'shards'/opt/'result.json' for opt in ('O0','O2')))
                value['computed_critical_path_work_seconds']+=1;write_json(work/'result.json',value)
                with self.assertRaisesRegex(Core0Error,'arithmetic'):
                    revalidate_collected(root,work,work/'result.json',None)

    def test_collector_rejects_missing_duplicate_failed_or_cross_profile_rows(self):
        for mutation in ('missing','duplicate','failed','profile'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);work,identity,values=self.fixture(root)
                rows=values['O2'][1]
                if mutation=='missing':rows.pop()
                elif mutation=='duplicate':rows[-1]=rows[-2]
                elif mutation=='failed':rows[-1]['status']='FAIL'
                else:rows[-1]['images'][0]['optimization']='O0'
                with self.context(identity,values),self.assertRaises(Core0Error):collect_shards(root=root,work_dir=work,shard_paths=tuple(work/'shards'/opt/'result.json' for opt in ('O0','O2')))
                self.assertEqual(json.loads((work/'result.json').read_text())['status'],'FAIL')


if __name__=='__main__':unittest.main()
