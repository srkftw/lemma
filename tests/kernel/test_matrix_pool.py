"""Host process scheduling/admission negatives; these are not RV64 observations."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_kernel import (ROW_SUPERVISORS, acceptance_inputs, matrix, merge_rows,
                          protocol_guard, row_main, row_checkers, run_matrix_rows,
                          validate_row_result, execute_row)
from core0_common import Core0Error, write_json


def fixture_row(index):
    profile = dict(zip(('configuration', 'stage', 'optimization'), matrix()[index]))
    return {'schema': 'lemma-kernel-matrix-row/v1', 'status': 'PASS', 'index': index,
            'row': list(matrix()[index]), 'images': [{**profile, 'image': 'host-fixture'}],
            'observations': [{**profile, 'role': role, 'qemu_sessions': count, 'status': 'PASS',
                              'syscall_user_instances': 3 if role == 'syscall' else 0}
                             for _, _, role, count in row_checkers(matrix()[index])],
            'invocations': [{'host_fixture_row': index}]}


class MatrixProcessTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'build/kernel').mkdir(parents=True, exist_ok=True)
        self.assertFalse(ROW_SUPERVISORS)

    def test_guards_keep_original_complete_protocol_and_cleanup_reserve(self):
        for sessions, bound in ((1, 210), (3, 390)):
            protocol_guard(bound, 90, sessions)
            with self.assertRaisesRegex(Core0Error, 'insufficient remaining'):
                protocol_guard(bound - .001, 90, sessions)

    def test_out_of_order_completion_preserves_exact_full_matrix_and_counts(self):
        report = {}
        merge_rows(report, [fixture_row(i) for i in reversed(range(20))], tuple(range(20)), complete=True)
        self.assertEqual([(r['configuration'], r['stage'], r['optimization']) for r in report['images']], list(matrix()))
        self.assertEqual(len(report['observations']), 24)
        self.assertEqual(sum(x['qemu_sessions'] for x in report['observations']), 28)
        self.assertEqual(sum(x['syscall_user_instances'] for x in report['observations']), 6)
        self.assertEqual([r['host_fixture_row'] for r in report['invocations']], list(range(20)))

    def test_incomplete_duplicate_outside_wrong_role_and_cross_row_cannot_pass(self):
        rows = [fixture_row(0), fixture_row(19)]
        bad_cases = [rows[:1], [rows[0], rows[0]], [rows[0], fixture_row(18)]]
        wrong = copy.deepcopy(rows); wrong[1]['observations'][0]['qemu_sessions'] = 2; bad_cases.append(wrong)
        wrong = copy.deepcopy(rows); wrong[1]['images'][0]['optimization'] = 'O0'; bad_cases.append(wrong)
        wrong = copy.deepcopy(rows); wrong[1]['observations'][0]['role'] = 'user'; bad_cases.append(wrong)
        wrong = copy.deepcopy(rows); wrong[1]['status'] = 'FAIL'; bad_cases.append(wrong)
        for value in bad_cases:
            with self.subTest(value=value), self.assertRaises(Core0Error):
                merge_rows({}, value, (0, 19), complete=True)

    def test_consumer_inventory_includes_process_supervisor(self):
        inputs = acceptance_inputs(ROOT)
        self.assertIn('scripts/kernel_row_supervisor.py', inputs)
        self.assertIn('tests/kernel/test_matrix_pool.py', inputs)

    def test_invalid_worker_plan_deadline_and_hidden_request_fail_before_launch(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/kernel') as temporary:
            work = Path(temporary)
            kwargs = dict(root=ROOT, work_dir=work, indices=(0,), jobs=2, identity={}, sources={}, consumers={},
                          timeout=300, qemu_timeout=90, finish_by=time.monotonic()+20)
            for change in ({'jobs': 3}, {'jobs': True}, {'indices': (0, 0)}, {'indices': (20,)},
                           {'finish_by': time.monotonic()-1}, {'finish_by': time.monotonic()+2500}, {'qemu_timeout': 0}):
                with self.subTest(change=change), self.assertRaises(Core0Error), patch('check_kernel.subprocess.Popen') as launch:
                    run_matrix_rows(**{**kwargs, **change})
                launch.assert_not_called()
            request = work / 'request.json'
            write_json(request, {'schema': 'lemma-kernel-row-request/v1', 'root': str(ROOT), 'work_dir': str(work),
                                 'index': 0, 'row': list(matrix()[19])})
            with self.assertRaisesRegex(Core0Error, 'invalid fixed matrix'), patch('check_kernel.build') as build:
                row_main(request)
            build.assert_not_called()

    def test_unreaped_supervisor_or_changed_request_cannot_admit_row(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/kernel') as temporary:
            work = Path(temporary); request = work/'request.json'; request.write_text('{}')
            receipt = work/'supervisor.json'
            for cleanup in (False, 1, None):
                write_json(receipt, {'schema':'lemma-kernel-row-supervisor/v1','status':'PASS',
                                     'child_returncode':0,'cleanup_complete':cleanup})
                with self.assertRaisesRegex(Core0Error, 'cleanup'):
                    validate_row_result(ROOT, work, {}, request, 'wrong', receipt)
            write_json(receipt, {'schema':'lemma-kernel-row-supervisor/v1','status':'PASS',
                                 'child_returncode':0,'cleanup_complete':True})
            with self.assertRaisesRegex(Core0Error, 'request changed'):
                validate_row_result(ROOT, work, {}, request, 'wrong', receipt)

    def test_supervisor_launch_source_deadline_and_reap_bindings_cannot_be_forged(self):
        from core0_common import sha256
        from check_kernel import row_command
        from kernel_row_supervisor import process_identity
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary); path=work/'request.json'; path.write_text('{}'); receipt=work/'supervisor.json'
            request={'finish_by':123, 'acceptance_inputs':{'scripts/kernel_row_supervisor.py':'helper-digest'}}
            dead={'pid':2**31-1,'start_ticks':'1'}
            valid={'schema':'lemma-kernel-row-supervisor/v1','status':'PASS','child_returncode':0,
                   'cleanup_complete':True,'reason':'child-exited','deadline_monotonic':123,
                   'supervisor_sha256':'helper-digest','argv':row_command(ROOT,path),'cleanup':{'remaining':[]},
                   'owner':dead,'child_identity':dead,'owned_processes':[dead]}
            cases=[{'deadline_monotonic':124},{'supervisor_sha256':'changed'},{'argv':['different']},
                   {'reason':'deadline-expired'},{'cleanup':{'remaining':[dead]}},{'owned_processes':[]},
                   {'owner':process_identity(os.getpid())}, {'child_returncode':False}]
            for change in cases:
                write_json(receipt,{**valid,**change})
                with self.subTest(change=change), self.assertRaises(Core0Error):
                    validate_row_result(ROOT,work,request,path,sha256(path),receipt)

    def test_each_image_explicitly_cold_prepares_and_executes_fresh_target_actions(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/kernel') as temporary:
            work = Path(temporary); (work/'rows/00').mkdir(parents=True)
            image_dir = work/'normal-bootstrap-m-O0'; image_dir.mkdir()
            (image_dir/'image.elf').write_bytes(b'host fixture')
            from core0_common import sha256
            write_json(image_dir/'provenance.json', {'source_commit':'fixture','source_inputs':{}})
            write_json(image_dir/'audit.json', {'status':'PASS','source_commit':'fixture',
                                               'image_sha256':sha256(image_dir/'image.elf')})
            with patch('check_kernel.source_identity',return_value={'commit':'fixture'}), \
                 patch('check_kernel.source_inputs',return_value={}), patch('check_kernel.acceptance_inputs',return_value={}), \
                 patch('check_kernel.row_checkers',return_value=()), patch('check_kernel.build',return_value={'status':'BUILT'}) as build:
                execute_row(root=ROOT,work_dir=work,index=0,identity={'commit':'fixture'},sources={},consumers={},
                            timeout=300,qemu_timeout=90,finish_by=time.monotonic()+400,cache_dir=work/'cache/slot-0')
            self.assertIs(build.call_args.kwargs['fresh'],True)
            self.assertEqual(build.call_args.kwargs['cache_dir'],work/'cache/slot-0')
            self.assertEqual(json.loads((work/'rows/00/result.json').read_text())['status'],'PASS')

    def test_construction_signal_cannot_kill_supervisor_before_registration(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary)
            fixture=work/'row.py'
            fixture.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                               "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)\n"
                               "Path(sys.argv[1]).with_name('descendant.pid').write_text(str(child.pid))\ntime.sleep(60)\n")
            parent=work/'parent.py'
            parent.write_text(f"""import sys,os,signal,time,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,{str(ROOT/'scripts')!r})
import check_kernel as k
root=Path({str(ROOT)!r}); work=Path({str(work)!r}); actual=k.subprocess.Popen; seen=[]
def terminate(number,frame):
 seen.append(bool(k.ROW_SUPERVISORS))
 if not k.ROW_SUPERVISORS:k.stop_controller_children()
 raise k.Core0Error('fixture interruption')
signal.signal(signal.SIGTERM,terminate)
def launch(*args,**kwargs):
 p=actual(*args,**kwargs)
 os.kill(os.getpid(),signal.SIGTERM)
 time.sleep(.2)
 return p
try:
 with patch('check_kernel.subprocess.Popen',side_effect=launch), patch('check_kernel.row_command',side_effect=lambda root,path:[sys.executable,{str(fixture)!r},str(path)]):
  k.run_matrix_rows(root=root,work_dir=work,indices=(0,),jobs=1,identity={{}},sources={{}},consumers={{}},timeout=300,qemu_timeout=90,finish_by=time.monotonic()+10)
except k.Core0Error:
 pass
(work/'parent-result.json').write_text(json.dumps({{'seen_registered':seen,'active':list(k.ROW_SUPERVISORS)}}))
""")
            result=subprocess.run([sys.executable,str(parent)],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            observed=json.loads((work/'parent-result.json').read_text())
            self.assertEqual(observed,{'seen_registered':[True],'active':[]})
            receipt=json.loads((work/'rows/00/supervisor.json').read_text())
            self.assertTrue(receipt['cleanup_complete'])
            pidfile=work/'rows/00/descendant.pid'
            if pidfile.exists():self.assertFalse(Path('/proc',pidfile.read_text()).exists())

    def run_host_pool(self, work, source, *, indices=(0, 1, 2, 3), jobs=2, deadline=10):
        script = work/'fixture.py'; script.write_text(source)
        def fake_admission(root, work_dir, request, request_path, digest, receipt_path, **kwargs):
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual((receipt['status'],receipt['cleanup_complete'],receipt['child_returncode']),('PASS',True,0))
            return fixture_row(request['index'])
        with patch('check_kernel.row_command', side_effect=lambda root, request: [sys.executable,str(script),str(request)]), \
             patch('check_kernel.validate_row_result', side_effect=fake_admission):
            return run_matrix_rows(root=ROOT,work_dir=work,indices=indices,jobs=jobs,identity={},sources={},consumers={},
                                   timeout=300,qemu_timeout=90,finish_by=time.monotonic()+deadline)

    def test_actual_two_process_scheduling_has_fixed_slots_and_ordered_merge(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary)
            source = '''import json,sys,time,os
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text()); p=Path(sys.argv[1]).parent
(p/'started.json').write_text(json.dumps({'at':time.monotonic(),'pid':os.getpid()}))
time.sleep(.35 if r['index']%2==0 else .1)
(p/'finished').write_text(str(time.monotonic()))
'''
            rows=self.run_host_pool(work,source)
            self.assertEqual([r['index'] for r in rows],[0,1,2,3])
            evidence=json.loads((work/'rows/execution.json').read_text())
            self.assertTrue(evidence['cleanup_complete'])
            self.assertEqual([r['slot'] for r in evidence['rows']],[0,1,1,0])
            requests=[json.loads((work/f'rows/{i:02}/request.json').read_text()) for i in range(4)]
            self.assertEqual(len({r['finish_by'] for r in requests}),1)
            self.assertEqual(len({r['cache_dir'] for r in requests}),2)
            intervals=[(json.loads((work/f'rows/{i:02}/started.json').read_text())['at'],float((work/f'rows/{i:02}/finished').read_text())) for i in range(4)]
            self.assertLess(intervals[1][0],intervals[0][1])
            self.assertGreaterEqual(intervals[2][0],intervals[1][1])
            self.assertGreaterEqual(intervals[3][0],intervals[0][1])
            self.assertFalse(ROW_SUPERVISORS)

    def test_failed_row_cancels_peer_and_never_admits_third_row(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary)
            source='''import json,sys,time,subprocess,os
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text()); p=Path(sys.argv[1]).parent
if r['index']==0:
 while not (p.parent/'01/descendant.pid').exists():time.sleep(.01)
 sys.exit(7)
child=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'],start_new_session=True)
(p/'descendant.pid').write_text(str(child.pid))
time.sleep(60)
'''
            with self.assertRaisesRegex(Core0Error,'supervisor failed'):
                self.run_host_pool(work,source,indices=(0,1,2))
            self.assertFalse((work/'rows/02').exists())
            child=int((work/'rows/01/descendant.pid').read_text())
            self.assertFalse(Path(f'/proc/{child}').exists())
            receipt=json.loads((work/'rows/01/supervisor.json').read_text())
            self.assertTrue(receipt['cleanup_complete'])
            self.assertNotEqual(receipt['status'],'PASS')
            self.assertFalse(ROW_SUPERVISORS)

    def test_global_deadline_cancels_processes_without_row_budget_reset(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            work=Path(temporary)
            with self.assertRaisesRegex(Core0Error,'deadline|supervisor failed'):
                self.run_host_pool(work,'import time;time.sleep(60)',indices=(0,1),deadline=.3)
            evidence=json.loads((work/'rows/execution.json').read_text())
            self.assertTrue(evidence['cleanup_complete'])
            self.assertEqual(len(evidence['rows']),2)
            self.assertTrue(all(row['returncode'] is not None for row in evidence['rows']))
            self.assertFalse(ROW_SUPERVISORS)


if __name__=='__main__': unittest.main()
