# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import subprocess
import socket
import struct
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_session as runtime


class Machine:
    identity={'backend':'rtl','implementation':'literal failure-test fixture'}
    def __init__(self):self.commands=[];self.cycle=10
    def call(self,command):
        self.commands.append(command)
        if command.startswith('snapshot '):Path(command[9:]).write_bytes(b'complete-literal-state')
        if command.startswith('run '):self.cycle+=int(command[4:])
        return {'cycle':self.cycle,'ticks':self.cycle//10,'finished':False}
    def close(self):pass


class LifecycleFailures(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.directory=self.root/'live';self.directory.mkdir()
        self.machine=Machine()
        self.session=runtime.Session(self.machine,self.directory,SimpleNamespace(mode='laboratory',paused=True,quantum=1000))
        self.addCleanup(self.session.close)
    def checkpoint(self):
        path=self.root/'snapshot';self.session.snapshot(path);return path
    def alter(self,path,change):
        file=path/'snapshot.json';data=json.loads(file.read_text());change(data);file.write_text(json.dumps(data))
    def unchanged_rejection(self,path):
        before=len(self.machine.commands)
        with self.assertRaises((ValueError,KeyError,OSError)):self.session.restore(path)
        self.assertEqual(len(self.machine.commands),before,'invalid state reached machine restore')
    def test_snapshot_never_drains_flushes_or_resets(self):
        self.checkpoint()
        self.assertEqual(len(self.machine.commands),1)
        self.assertTrue(self.machine.commands[0].startswith('snapshot '))
    def test_clock_reads_existing_rtl_time_without_external_admission(self):
        original=self.machine.call
        def observed(command):
            return {**original(command),'backend':'rtl','devices':{'not_clock':'payload'},
                    'cpu_registers':'full observer payload'}
        self.machine.call=observed
        result=self.session.dispatch({'action':'clock'})
        self.assertEqual(result,{'machine':{'backend':'rtl','cycle':10,'ticks':1,'finished':False},'running':False})
        self.assertEqual(self.machine.commands,['inspect'])
        self.assertEqual((self.session.event_count,self.session.event_cursor,self.session.presentation_generation),(0,0,0))
        self.assertEqual((self.directory/'external.jsonl').read_bytes(),b'')
    def test_fast_clock_retains_exact_phase_and_actual_local_mtime(self):
        clock={'backend':'qemu','cycle':13,'ticks':7,'virtual_ns':128,'local_virtual_ns':8,
               'local_ticks':7,'time_origin_ns':120,'finished':False,'runstate':'paused'}
        self.machine.clock=lambda:dict(clock)
        self.machine.call=mock.Mock(side_effect=AssertionError('Clock requested full inspection'))
        # Read-only observation remains available after uncertain admission.
        self.session.capture_uncertain=True
        result=self.session.dispatch({'action':'clock'})
        self.assertEqual(result,{'machine':clock,'running':False})
        self.machine.call.assert_not_called()
        self.assertEqual((self.directory/'external.jsonl').read_bytes(),b'')
        self.assertEqual((self.session.event_count,self.session.event_cursor),(0,0))
        self.assertTrue(self.session.capture_uncertain)
    def test_clock_missing_mandatory_fields_fails_without_admission(self):
        self.machine.clock=lambda:{'cycle':10,'ticks':1,'finished':False}
        with self.assertRaises(KeyError):self.session.dispatch({'action':'clock'})
        self.assertEqual(self.machine.commands,[])
        self.assertEqual((self.directory/'external.jsonl').read_bytes(),b'')
    def test_pointer_clock_preserves_mtime_and_literal_contact_hover_fields(self):
        calls=[]
        def rpc(directory,value):
            calls.append((directory,value))
            return {'machine':{'ticks':0x100000005,'cycle':999,'virtual_ns':9984}} if value['action']=='clock' else {}
        with mock.patch.object(runtime,'request',rpc):
            runtime._sample_pointer(self.directory,-1,10000,True,1650,2200,3)
            runtime._sample_pointer(self.directory,42,57,False,1650,2200,3)
        self.assertEqual(calls,[(self.directory,{'action':'clock'}),
            (self.directory,{'action':'inject','kind':'pen','words':[0x100000005,0,65535,2047,7,1,0]}),
            (self.directory,{'action':'clock'}),
            (self.directory,{'action':'inject','kind':'pen','words':[0x100000005,5007,5096,0,6,1,0]})])
    def test_pointer_clock_failure_cannot_admit_a_sample(self):
        with mock.patch.object(runtime,'request',side_effect=TimeoutError('Clock observer unavailable')) as rpc:
            with self.assertRaises(TimeoutError):runtime._sample_pointer(self.directory,42,57,True,1650,2200,3)
        rpc.assert_called_once_with(self.directory,{'action':'clock'})
    def test_snapshot_refuses_existing_destination(self):
        path=self.checkpoint();before=(path/'machine.chk').read_bytes()
        with self.assertRaises(FileExistsError):self.session.snapshot(path)
        self.assertEqual((path/'machine.chk').read_bytes(),before)
    def test_stale_identity_rejected_before_apply(self):
        path=self.checkpoint();self.alter(path,lambda d:d.update(identity={'implementation':'different'}));self.unchanged_rejection(path)
    def test_missing_checksum_or_truncated_state_rejected_before_apply(self):
        path=self.checkpoint();(path/'machine.chk').write_bytes(b'incomplete');self.unchanged_rejection(path)
    def test_missing_state_rejected_before_apply(self):
        path=self.checkpoint();(path/'machine.chk').unlink();self.unchanged_rejection(path)
    def test_duplicate_state_inventory_rejected_before_apply(self):
        path=self.checkpoint();self.alter(path,lambda d:d['files'].append(d['files'][0]));self.unchanged_rejection(path)
    def test_path_escape_rejected_before_apply(self):
        path=self.checkpoint();self.alter(path,lambda d:d['files'][0].update(path='../outside'));self.unchanged_rejection(path)
    def test_symlinked_state_rejected_before_apply(self):
        path=self.checkpoint();other=self.root/'other';other.write_bytes((path/'machine.chk').read_bytes())
        (path/'machine.chk').unlink();(path/'machine.chk').symlink_to(other);self.unchanged_rejection(path)
    def test_bad_pacing_rejected_before_machine_restore(self):
        path=self.checkpoint();self.alter(path,lambda d:d.update(quantum=True));self.unchanged_rejection(path)
    def test_null_state_path_rejected_before_apply(self):
        path=self.checkpoint();self.alter(path,lambda d:d['files'][0].update(path=None));self.unchanged_rejection(path)
    def test_omitted_durable_inventory_rejected_before_apply(self):
        self.machine.checkpoint_files={'machine.chk','durable.raw'}
        path=self.checkpoint()
        (path/'durable.raw').write_bytes(b'unvalidated sidecar')
        self.unchanged_rejection(path)
    def test_boot_discovery_identity_change_rejected_before_apply(self):
        self.machine.identity={'backend':'qemu','implementation':'literal fixture','dtb':'a'*64,'descriptor':'c'*64}
        path=self.checkpoint()
        self.machine.identity={**self.machine.identity,'dtb':'b'*64}
        self.unchanged_rejection(path)
    def test_non_object_snapshot_manifest_rejected_before_apply(self):
        path=self.checkpoint()
        for value in (None,[],17):
            with self.subTest(value=value):
                (path/'snapshot.json').write_text(json.dumps(value));self.unchanged_rejection(path)

    def power_startup(self,path,**changes):
        return runtime.startup_restore_medium(SimpleNamespace(restore=path,disk=None,
            workload='power',backend='qemu',**changes))
    def fast_power_checkpoint(self):
        path=self.checkpoint();clock=path/'clock.json';clock.write_bytes(b'bounded-clock-fixture')
        self.alter(path,lambda d:d['files'].append({'path':'clock.json','bytes':clock.stat().st_size,
            'sha256':runtime.digest(clock)}))
        return path
    def test_power_startup_selects_verified_optional_backing(self):
        path=self.fast_power_checkpoint();self.assertFalse(self.power_startup(path))
        medium=path/'durable.raw'
        with medium.open('xb') as stream:stream.truncate(256*1024*1024)
        self.alter(path,lambda d:d['files'].append({'path':'durable.raw','bytes':medium.stat().st_size,
            'sha256':runtime.digest(medium)}))
        self.assertTrue(self.power_startup(path))
        medium.write_bytes(b'truncated')
        with self.assertRaisesRegex(ValueError,'length/checksum'):self.power_startup(path)
    def test_power_startup_rejects_wrong_inventory_and_short_medium(self):
        path=self.fast_power_checkpoint();self.alter(path,lambda d:d['files'].pop())
        with self.assertRaisesRegex(ValueError,'inventory'):self.power_startup(path)
        clock=path/'clock.json'
        medium=path/'durable.raw';medium.write_bytes(b'bad')
        self.alter(path,lambda d:d['files'].extend([
            {'path':'clock.json','bytes':clock.stat().st_size,'sha256':runtime.digest(clock)},
            {'path':'durable.raw','bytes':3,'sha256':runtime.digest(medium)}]))
        with self.assertRaisesRegex(ValueError,'medium length'):self.power_startup(path)
    def test_every_startup_restore_rejects_unrelated_user_backing(self):
        for backend in ('qemu','rtl'):
            for workload in ('service','power','notebook'):
                with self.subTest(backend=backend,workload=workload),self.assertRaisesRegex(ValueError,'omit --disk'):
                    runtime.startup_restore_medium(SimpleNamespace(restore=self.root/'snapshot',
                        disk=self.root/'user.raw',workload=workload,backend=backend))
    def test_raw_event_fields_and_separate_delivery_preserved(self):
        words=[2**63+1,1234,5678,4095,7,2,3]
        self.session.dispatch({'action':'inject','kind':'pen','cycle':45,'words':words})
        self.assertEqual(self.machine.commands[-1],'inject 45 pen '+' '.join(map(str,words)))
        row=json.loads((self.directory/'external.jsonl').read_text())
        self.assertEqual(row['cycle'],10);self.assertEqual(row['request']['cycle'],45);self.assertEqual(row['request']['words'],words)
    def test_stale_event_and_invalid_pressure_reject_before_delivery(self):
        for value in ({'action':'inject','kind':'pen','cycle':9,'words':[1,1,1,1,3,1,0]},
                      {'action':'inject','kind':'pen','words':[1,1,1,4096,3,1,0]}):
            with self.subTest(value=value),self.assertRaises(ValueError):self.session.dispatch(value)
        self.assertFalse(any(c.startswith('inject ') for c in self.machine.commands))
    def test_restore_changes_timeline_cursor_but_preserves_capture_ordinal(self):
        path=self.checkpoint()
        self.session.dispatch({'action':'inject','kind':'uart','hex':'a500'})
        self.session.restore(path)
        self.assertEqual((self.session.event_count,self.session.event_cursor),(1,0))
        self.session.dispatch({'action':'inject','kind':'uart','hex':'ab00'})
        rows=[json.loads(line) for line in (self.directory/'external.jsonl').read_text().splitlines()]
        self.assertEqual([(r['ordinal'],r['cursor']) for r in rows],[(0,0),(1,0)])
    def test_replay_uses_original_admission_boundary_and_raw_delivery(self):
        path=self.checkpoint();capture=self.root/'closed.jsonl'
        capture.write_text(json.dumps({'ordinal':0,'cursor':0,'cycle':20,'request':{'action':'inject','kind':'uart','cycle':25,'hex':'a5'}})+'\n')
        result=self.session.replay(path,capture,50)
        self.assertEqual(result['machine']['cycle'],50)
        self.assertIn('run 10',self.machine.commands);self.assertIn('inject 25 uart a5',self.machine.commands)
        self.assertIn('run 30',self.machine.commands)
    def test_live_or_ambiguous_capture_rejected_without_restore(self):
        path=self.checkpoint();before=len(self.machine.commands)
        with self.assertRaises(ValueError):self.session.replay(path,self.directory/'external.jsonl',50)
        capture=self.root/'closed.jsonl';capture.write_text(json.dumps({'ordinal':0,'cursor':2,'cycle':20,'request':{'action':'warm-reset'}})+'\n')
        with self.assertRaises(ValueError):self.session.replay(path,capture,50)
        self.assertEqual(len(self.machine.commands),before)
    def test_replay_preflight_rejects_malformed_suffix_without_state_change(self):
        path=self.checkpoint();capture=self.root/'closed.jsonl'
        normal={'ordinal':0,'cursor':0,'cycle':20,'request':{'action':'inject','kind':'pen','words':[2,1,2,1,3,1,0]}}
        malformed=[
            [{**normal,'request':{'action':'inject','kind':'pen','words':[2,1,2,4096,3,1,0]}}],
            [{**normal,'request':{'action':'inject','kind':'pen','cycle':19,'words':[2,1,2,1,3,1,0]}}],
            [{**normal,'cycle':True}],
            [{**normal,'ordinal':True}],
            [{**normal,'request':None}],
            [normal,{'ordinal':1,'cursor':1,'cycle':15,'request':{'action':'warm-reset'}}],
            [normal,{**normal,'cursor':1,'cycle':25}],
            [{**normal,'cycle':60},{'ordinal':1,'cursor':1,'cycle':20,'request':{'action':'warm-reset'}}],
        ]
        for rows in malformed:
            with self.subTest(rows=rows):
                capture.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                before=len(self.machine.commands)
                with self.assertRaises(ValueError):self.session.replay(path,capture,50)
                self.assertEqual(len(self.machine.commands),before,'malformed replay reached owner')
    def test_capture_write_failure_rejects_before_device_admission(self):
        self.session.automatic=True
        with mock.patch.object(self.session,'capture',wraps=self.session.capture) as capture:
            capture.write.side_effect=OSError('literal full capture filesystem')
            with self.assertRaisesRegex(OSError,'full capture filesystem'):
                self.session.dispatch({'action':'inject','kind':'pen','words':[1,2,3,4,7,1,0]})
        self.assertFalse(any(c.startswith('inject ') for c in self.machine.commands))
        self.assertFalse(self.session.automatic)
        self.assertEqual(self.session.event_cursor,0)
    def test_full_capture_rejects_record_before_device_admission(self):
        with mock.patch.object(self.session,'capture',wraps=self.session.capture) as capture:
            capture.tell.return_value=256*1024*1024-1
            with self.assertRaises(ValueError):
                self.session.dispatch({'action':'inject','kind':'pen','words':[1,2,3,4,7,1,0]})
            capture.write.assert_not_called()
        self.assertFalse(any(c.startswith('inject ') for c in self.machine.commands))
    def test_replay_manifest_resource_bound_rejects_without_state_change(self):
        path=self.checkpoint();capture=self.root/'closed.jsonl';capture.write_text('')
        (path/'snapshot.json').write_text(' '*runtime.MAX_REQUEST+'{}')
        before=len(self.machine.commands)
        with self.assertRaises(ValueError):self.session.replay(path,capture,50)
        self.assertEqual(len(self.machine.commands),before)
    def test_failed_interval_pauses_and_remains_inspectable(self):
        original=self.machine.call
        def failed_interval(command):
            if command.startswith('run '):raise TimeoutError('literal interval resource deadline')
            return original(command)
        self.machine.call=failed_interval;self.session.automatic=True
        with self.assertRaises(TimeoutError):self.session.dispatch({'action':'run','cycles':20})
        result=self.session.dispatch({'action':'inspect'})
        self.assertFalse(result['running'])
        self.assertEqual(result['last_failed_operation'],'literal interval resource deadline')
    def test_failed_interval_clock_query_pauses_and_remains_inspectable(self):
        def failed_clock():raise RuntimeError('literal clock transport failure')
        self.machine.clock=failed_clock;self.session.automatic=True
        with self.assertRaises(RuntimeError):self.session.dispatch({'action':'run','cycles':20})
        result=self.session.dispatch({'action':'inspect'})
        self.assertFalse(result['running'])
        self.assertEqual(result['last_failed_operation'],'literal clock transport failure')
    def test_failed_rtl_startup_reaps_real_child(self):
        import silicon_guest
        launched=[];real_popen=subprocess.Popen
        def child(*unused,**kwargs):
            process=real_popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
            launched.append(process);return process
        data={'profile':'lemma-silicon-dev/0.1.0','binary':{'path':'unused','sha256':'a'*64},
              'rom':{'path':'unused','sha256':'b'*64},'workloads':{'service':{
              name:{'path':'unused','sha256':'c'*64} for name in ('image','dtb','descriptor')}}}
        args=SimpleNamespace(workload='service',profile='lemma-silicon-dev/0.1.0',memory_latency=0,
              fail_flush=0,disk=None,events=None,trace_limit=1000,timeout=0.1)
        try:
            with mock.patch.object(silicon_guest,'prepared',return_value=data), \
                 mock.patch.object(runtime.subprocess,'Popen',side_effect=child), \
                 mock.patch.object(runtime.RTL,'call',side_effect=RuntimeError('unsupported runtime handshake')):
                with self.assertRaisesRegex(RuntimeError,'unsupported runtime handshake'):
                    runtime.RTL(args,self.directory)
            self.assertEqual(len(launched),1)
            self.assertIsNotNone(launched[0].poll(),'failed constructor leaked its child')
        finally:
            for process in launched:
                if process.poll() is None:process.kill();process.wait(timeout=3)
                for stream in (process.stdin,process.stdout):
                    if stream is not None:stream.close()
    def test_failed_fast_startup_reaps_real_child(self):
        import lemmasim_fast as fast
        launched=[];real_popen=subprocess.Popen
        def child(*unused,**kwargs):
            process=real_popen([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
            launched.append(process);return process
        data={'profile':'lemma-silicon-dev/0.1.0','qemu':{'path':'unused','sha256':'a'*64},
              'derivation':{'sha256':'b'*64},'workloads':{'service':{
              name:{'path':'unused','sha256':'c'*64} for name in ('image','dtb','descriptor')}}}
        args=SimpleNamespace(workload='service',profile='lemma-silicon-dev/0.1.0',memory_latency=0,
              fail_flush=0,disk=None,events=None,timeout=0.1)
        try:
            with mock.patch.object(fast,'prepared',return_value=data), \
                 mock.patch.object(fast.subprocess,'Popen',side_effect=child), \
                 mock.patch.object(fast,'QMP',side_effect=RuntimeError('unsupported QMP readiness')):
                with self.assertRaisesRegex(RuntimeError,'unsupported QMP readiness'):
                    fast.Fast(args,self.directory)
            self.assertEqual(len(launched),1)
            self.assertIsNotNone(launched[0].poll(),'failed constructor leaked its child')
        finally:
            for process in launched:
                if process.poll() is None:process.kill();process.wait(timeout=3)
    def test_fast_timeout_and_pause_stop_execution_without_reset_or_snapshot(self):
        import lemmasim_fast as fast
        class QMP:
            def __init__(self):self.running=True;self.commands=[]
            def execute(self,command,arguments=None):
                self.commands.append(command)
                if command=='stop':self.running=False
                # Pinned QEMU StatusInfo requires both fields. Preserve the
                # adapter's internal-error guard while modeling stop/cont.
                if command=='query-status':return {'running':self.running,'status':'running' if self.running else 'paused'}
        machine=object.__new__(fast.Fast);machine.qmp=QMP();machine.args=SimpleNamespace(timeout=0)
        machine.data={'profile':'lemma-silicon-dev/0.1.0'}
        machine.clock_hz=100000000;machine.time_origin_ns=0;machine.get=lambda name:'0'
        machine.inspect=lambda:{'running':machine.qmp.running}
        with self.assertRaises(TimeoutError):machine.call('run 1000')
        self.assertFalse(machine.qmp.running)
        machine.qmp.running=True;self.assertFalse(machine.call('pause')['running'])
        self.assertTrue(set(machine.qmp.commands)<={'qom-set','cont','query-status','stop'})
    def test_departed_socket_client_does_not_terminate_persistent_owner(self):
        # An actual session process/socket with an independent machine-boundary
        # fixture. The test establishes transport teardown, not guest execution.
        directory=self.root/'socket-live'
        code='''import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
import lemmasim_session as runtime
class Machine:
    identity={'backend':'rtl','scope':'independent socket fixture'}
    argv=[]
    def call(self,command):return {'cycle':10,'ticks':1,'finished':False}
    def close(self):pass
runtime.RTL=lambda args,directory:Machine()
runtime.serve(SimpleNamespace(session_dir=Path(sys.argv[2]),disk=None,backend='rtl',mode='developer',
    headless=True,tablet=None,paused=True,quantum=1000,restore=None))
'''
        child=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'scripts'),str(directory)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+3
            while not (directory/'session.json').exists() and time.monotonic()<deadline:
                if child.poll() is not None:break
                time.sleep(0.01)
            self.assertIsNone(child.poll(),'Session exited before readiness')
            metadata=json.loads((directory/'session.json').read_text())
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as incomplete:
                incomplete.connect(metadata['socket'])
                incomplete.sendall(b'{"action":')
                # Force a real peer reset before a complete newline request.
                incomplete.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
            self.assertEqual(runtime.request(directory,{'action':'inspect'},timeout=2)['machine']['cycle'],10)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as departed:
                departed.connect(metadata['socket'])
                departed.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
                departed.sendall(b'{"action":"inspect"}\n')
            result=runtime.request(directory,{'action':'inspect'},timeout=2)
            self.assertEqual(result['machine']['cycle'],10)
            runtime.request(directory,{'action':'destroy'},timeout=2)
            _,stderr=child.communicate(timeout=3)
            self.assertEqual(child.returncode,0,stderr)
        finally:
            if child.poll() is None:
                child.kill();child.communicate(timeout=3)
            child.stdout.close();child.stderr.close()
    def test_restore_rejects_pending_live_tablet_but_replays_recorded_samples(self):
        connected=True
        def disconnected():
            nonlocal connected
            connected=False
        self.session.adapter=lambda:{'tablet':{'connected':connected}}
        self.session.disconnect_adapter=disconnected
        path=self.checkpoint();self.session.restore(path)
        before=len(self.machine.commands)
        words=[2,123,456,99,3,1,2]
        for value in ({'action':'clock','source':'tablet'},
                      {'action':'inject','source':'tablet','kind':'pen','words':words}):
            with self.subTest(value=value),self.assertRaises((ValueError,RuntimeError)):
                self.session.dispatch(value)
        self.assertEqual(len(self.machine.commands),before,'pending live tablet crossed restored boundary')
        capture=self.root/'closed-tablet.jsonl'
        capture.write_text(json.dumps({'ordinal':0,'cursor':0,'cycle':20,
            'request':{'action':'inject','source':'tablet','kind':'pen','cycle':20,'words':words}})+'\n')
        result=self.session.replay(path,capture,30)
        self.assertEqual(result['replayed_events'],1)
        self.assertIn('inject 20 pen 2 123 456 99 3 1 2',self.machine.commands)
    def test_unsupported_backend_uart_replay_rejects_before_state_change(self):
        self.machine.input_kinds={'pen'}
        path=self.checkpoint();capture=self.root/'closed-uart.jsonl'
        capture.write_text(json.dumps({'ordinal':0,'cursor':0,'cycle':20,
            'request':{'action':'inject','kind':'uart','cycle':25,'hex':'a5'}})+'\n')
        before=len(self.machine.commands)
        with self.assertRaises(ValueError):self.session.replay(path,capture,50)
        self.assertEqual(len(self.machine.commands),before,'unsupported backend input restored or advanced machine')
    def test_initializer_guest_error_cannot_become_acknowledged(self):
        import lemmasim_fast as fast
        directory=self.root/'failed-initializer'
        class RejectedInitializer(Machine):
            def __init__(self,args,output):
                super().__init__()
                (output/'uart-0.bin').write_bytes(b'K1 000000000000041f 00000000000000e3 0000000000000000 0000000000000000 0000000000000000\n')
        args=SimpleNamespace(force=False,size_mib=256,backend='qemu',profile='lemma-silicon-dev/0.2.0',
            session_dir=directory,disk=self.root/'failed-medium.raw',timeout=2)
        with mock.patch.object(fast,'prepared'),mock.patch.object(fast,'Fast',RejectedInitializer):
            with self.assertRaisesRegex(RuntimeError,'rejected durable initialization'):
                runtime.initialize(args)
        result=json.loads((directory/'result.json').read_text())
        self.assertEqual(result['status'],'FAIL')
        self.assertNotIn('guest_ack',result)


class FastClockPhaseFailures(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);directory=self.root/'live';directory.mkdir()
        class ClockFixture(Machine):
            identity={'backend':'qemu','scope':'independent clock transport fixture'}
            clock_hz=100000000
            input_kinds={'pen'}
            def __init__(self):super().__init__();self.ns=96
            def clock(self):return {'cycle':(self.ns+9)//10,'virtual_ns':self.ns,'ticks':self.ns//100,'finished':False}
            def call(self,command):
                self.commands.append(command)
                if command.startswith('snapshot '):Path(command[9:]).write_bytes(b'complete-phase-fixture')
                return self.clock()
            def restore_checkpoint(self,path,expected_ns):
                assert expected_ns==96
                self.commands.append('restore '+str(path));self.ns=96
                return self.clock()
            def run_until_ns(self,ns):
                self.commands.append('phase '+str(ns));self.ns=ns
                return self.clock()
        self.machine=ClockFixture()
        self.session=runtime.Session(self.machine,directory,SimpleNamespace(mode='developer',paused=True,quantum=1000))
        self.addCleanup(self.session.close)
        self.source=self.root/'snapshot';self.session.snapshot(self.source)
        self.capture=self.root/'external.jsonl'
        self.row={'ordinal':0,'cursor':0,'cycle':11,'virtual_ns':104,
                  'request':{'action':'inject','kind':'pen','cycle':12,'words':[4,5,6,7,7,1,0]}}
    def test_live_raw_admission_uses_exact_phase_and_keeps_full_post_state(self):
        self.machine.ns=104
        original=self.machine.call
        capture_path=self.session.directory/'external.jsonl'
        def post_state(command):
            if command=='inspect':raise AssertionError('Admission requested a full inspection')
            self.assertEqual(json.loads(capture_path.read_text())['admission'],'pending')
            return {**original(command),'devices':{'pen_queued':1},'cpu_registers':'post-injection observations'}
        self.machine.call=post_state
        value={'action':'inject','kind':'pen','cycle':12,'words':[4,5,6,7,7,1,0]}
        result=self.session.dispatch(value)
        row=json.loads(capture_path.read_text())
        self.assertEqual(row,{'admission':'applied',**self.row})
        self.assertEqual(self.machine.commands[-1],'inject 12 pen 4 5 6 7 7 1 0')
        self.assertEqual(result['devices'],{'pen_queued':1})
        self.assertEqual(result['cpu_registers'],'post-injection observations')
        self.assertEqual((self.session.event_count,self.session.event_cursor),(1,1))
    def test_live_stale_delivery_rejects_without_capture_or_mutation(self):
        self.machine.ns=104
        before=list(self.machine.commands)
        with self.assertRaises(ValueError):
            self.session.dispatch({'action':'inject','kind':'pen','cycle':10,'words':[4,5,6,7,7,1,0]})
        self.assertEqual(self.machine.commands,before)
        self.assertEqual((self.session.directory/'external.jsonl').read_bytes(),b'')
        self.assertEqual((self.session.event_count,self.session.event_cursor),(0,0))
    def test_live_uncertain_admission_blocks_clock_and_all_new_delivery(self):
        self.session.capture_uncertain=True
        self.machine.clock=mock.Mock(side_effect=AssertionError('Uncertain input read a new clock'))
        before=list(self.machine.commands)
        with self.assertRaises(RuntimeError):
            self.session.dispatch({'action':'inject','kind':'pen','words':[4,5,6,7,7,1,0]})
        self.machine.clock.assert_not_called()
        self.assertEqual(self.machine.commands,before)
        self.assertEqual((self.session.directory/'external.jsonl').read_bytes(),b'')
    def test_live_lost_delivery_reply_retains_pending_exact_phase(self):
        self.machine.ns=104
        self.machine.call=mock.Mock(side_effect=TimeoutError('Lost device reply after possible admission'))
        value={'action':'inject','kind':'pen','cycle':12,'words':[4,5,6,7,7,1,0]}
        with self.assertRaises(TimeoutError):self.session.dispatch(value)
        self.machine.call.assert_called_once_with('inject 12 pen 4 5 6 7 7 1 0')
        self.assertEqual(json.loads((self.session.directory/'external.jsonl').read_text()),
                         {'admission':'pending',**self.row})
        self.assertTrue(self.session.capture_uncertain)
        self.assertEqual((self.session.event_count,self.session.event_cursor),(0,0))
    def test_nonintegral_controller_phase_replays_exactly(self):
        self.capture.write_text(json.dumps(self.row)+'\n')
        result=self.session.replay(self.source,self.capture,None,144)
        self.assertEqual(result['machine']['virtual_ns'],144)
        self.assertEqual(result['machine']['cycle'],15)
        self.assertIn('phase 104',self.machine.commands)
        self.assertIn('inject 12 pen 4 5 6 7 7 1 0',self.machine.commands)
    def test_missing_or_inconsistent_phase_rejects_before_restore(self):
        for phase in (None,96,112,True):
            with self.subTest(phase=phase):
                self.capture.write_text(json.dumps({**self.row,'virtual_ns':phase})+'\n')
                before=len(self.machine.commands)
                with self.assertRaises(ValueError):self.session.replay(self.source,self.capture,None,144)
                self.assertEqual(len(self.machine.commands),before)
    def test_phase_reversal_with_same_ceiling_cycle_rejects(self):
        rows=[{**self.row,'virtual_ns':108},{**self.row,'ordinal':1,'cursor':1,'virtual_ns':104}]
        self.capture.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        before=len(self.machine.commands)
        with self.assertRaises(ValueError):self.session.replay(self.source,self.capture,None,144)
        self.assertEqual(len(self.machine.commands),before)

if __name__=='__main__':unittest.main()
