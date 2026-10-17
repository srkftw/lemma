# SPDX-License-Identifier: Apache-2.0
"""Actual subprocess/Unix-socket fixtures; these do not execute a guest."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_fast as fast

PEER = '''import json,socket,sys
sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
sock.bind(sys.argv[1]);sock.listen(1)
connection,_=sock.accept();stream=connection.makefile('rwb',buffering=0)
stream.write(b'{"QMP":{"scope":"independent lifecycle transport fixture"}}\\n')
for line in stream:
    request=json.loads(line);command=request['execute'];reply={'id':request['id'],'return':{}}
    if command=='query-status':reply['return']={'status':'paused','running':False}
    if command=='qom-list':reply['return']=[]
    if command=='qom-get':
        reply['return']='0' if request['arguments']['property']=='virtual-time' else '{}'
    if command=='human-monitor-command':
        reply['return']='0200bff8: 0x0000000000000000\\r\\n' if request['arguments']['command-line'].startswith('xp ') else 'literal CPU transport fixture'
    if command=='lemma-load-machine':reply={'id':request['id'],'error':{'class':'GenericError','desc':'literal rejected VMState'}}
    stream.write(json.dumps(reply).encode()+b'\\n')
    if command=='quit':break
stream.close();connection.close();sock.close()
'''


class FastTransport(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / ('persistent-' + 'x' * 70) / ('fork-parent-' + 'y' * 70)
        self.directory.mkdir(parents=True)
        self.children = []; self.sockets = []
        real_popen = subprocess.Popen

        def launch(command, **kwargs):
            socket_argument = command[command.index('-qmp') + 1]
            socket_path = Path(socket_argument.split(',')[0][5:])
            self.sockets.append(socket_path)
            process = real_popen([sys.executable, '-c', PEER, str(socket_path)], **kwargs)
            self.children.append(process)
            return process

        self.data = {'profile': 'lemma-silicon-dev/0.2.0',
            'qemu': {'path': 'unused', 'sha256': 'a' * 64},
            'derivation': {'sha256': 'b' * 64}, 'workloads': {'service': {
                name: {'path': 'unused', 'sha256': 'c' * 64} for name in ('image', 'dtb', 'descriptor')}}}
        self.args = SimpleNamespace(workload='service', profile='lemma-silicon-dev/0.2.0',
            memory_latency=0, fail_flush=0, disk=None, events=None, trace_limit=0, timeout=2)
        self.prepared = mock.patch.object(fast, 'prepared', return_value=self.data)
        self.popen = mock.patch.object(fast.subprocess, 'Popen', side_effect=launch)
        self.prepared.start(); self.popen.start()
        self.addCleanup(self.prepared.stop); self.addCleanup(self.popen.stop)
        self.addCleanup(self.reap)

    def reap(self):
        for child in self.children:
            if child.poll() is None:
                child.kill(); child.wait(timeout=3)

    def test_deep_session_and_nested_failed_restore_use_short_owned_sockets(self):
        machine = fast.Fast(self.args, self.directory)
        self.addCleanup(machine.close)
        original_socket = self.sockets[0]
        self.assertGreater(len(str(self.directory / 'qmp.sock')), 108)
        self.assertLess(len(str(original_socket)), 104)
        self.assertEqual(original_socket.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue(original_socket.exists())
        before = machine.inspect(); old_process = machine.process
        checkpoint = self.root / 'machine.chk'; checkpoint.write_bytes(b'independent transport fixture state')
        checkpoint.with_name('clock.json').write_text(json.dumps({'schema':fast.CLOCK_SCHEMA,'time_origin_ns':0}))
        with self.assertRaisesRegex(RuntimeError, 'rejected VMState'):
            machine.restore_checkpoint(checkpoint)
        self.assertEqual(machine.inspect(), before)
        self.assertIs(machine.process, old_process)
        self.assertTrue(original_socket.exists())
        self.assertFalse(self.sockets[1].parent.exists(), 'failed candidate leaked its socket directory')
        self.assertIsNotNone(self.children[1].poll(), 'failed candidate child was not reaped')
        self.assertFalse(list(self.directory.glob('machine-fork-*')), 'failed isolated fork was not removed')
        self.assertEqual(checkpoint.read_bytes(), b'independent transport fixture state')
        machine.close()
        self.assertIsNotNone(old_process.poll())
        self.assertFalse(original_socket.parent.exists())
        self.assertTrue(self.directory.exists(), 'teardown removed persistent user files')

    def test_already_exited_child_still_releases_socket_and_open_handles(self):
        machine = fast.Fast(self.args, self.directory)
        path = self.sockets[0]; old_log = machine.log; old_qmp = machine.qmp
        machine.qmp.execute('quit'); machine.process.wait(timeout=3)
        machine.close(); machine.close()
        self.assertTrue(old_log.closed)
        self.assertTrue(old_qmp.stream.closed)
        self.assertFalse(path.parent.exists())

    def test_constructor_failure_removes_socket_directory_and_reaps_child(self):
        with mock.patch.object(fast, 'QMP', side_effect=RuntimeError('literal readiness failure')):
            with self.assertRaisesRegex(RuntimeError, 'readiness failure'):
                fast.Fast(self.args, self.directory)
        self.assertIsNotNone(self.children[0].poll())
        self.assertFalse(self.sockets[0].parent.exists())

    def test_malformed_feature_inventory_fails_closed_and_reaps_child(self):
        execute = fast.QMP.execute
        for inventory in ({}, [None], [{'name':'raw-uart-version'}],
                          [{'name':7,'type':'str'}]):
            with self.subTest(inventory=inventory):
                def reply(peer, command, arguments=None):
                    if command == 'qom-list':
                        return inventory
                    return execute(peer, command, arguments)
                with mock.patch.object(fast.QMP, 'execute', reply):
                    with self.assertRaisesRegex(ValueError, 'Malformed backend property'):
                        fast.Fast(self.args, self.directory)
                self.assertIsNotNone(self.children[-1].poll())
                self.assertFalse(self.sockets[-1].parent.exists())

    def test_unknown_advertised_uart_version_fails_closed(self):
        execute = fast.QMP.execute
        self.args.profile = self.data['profile'] = 'lemma-silicon-dev/0.3.0'
        def reply(peer, command, arguments=None):
            if command == 'qom-list':
                return [{'name':'raw-uart-version','type':'str'}]
            if command == 'qom-get' and arguments['property']=='raw-uart-version':
                return 'lemma-raw-uart/unknown'
            return execute(peer, command, arguments)
        with mock.patch.object(fast.QMP, 'execute', reply):
            with self.assertRaisesRegex(ValueError, 'Unsupported raw UART'):
                fast.Fast(self.args, self.directory)
        self.assertIsNotNone(self.children[-1].poll())
        self.assertFalse(self.sockets[-1].parent.exists())

    def test_preflight_failure_allocates_no_socket_directory_or_child(self):
        self.args.memory_latency = 1
        with mock.patch.object(fast.tempfile, 'TemporaryDirectory') as allocation:
            with self.assertRaisesRegex(ValueError, 'memory-latency'):
                fast.Fast(self.args, self.directory)
            allocation.assert_not_called()
        self.assertFalse(self.children)

    def test_clock_origin_missing_malformed_or_oversized_rejects_before_candidate(self):
        machine=fast.Fast(self.args,self.directory);self.addCleanup(machine.close)
        checkpoint=self.root/'machine.chk';checkpoint.write_bytes(b'fixture state')
        before=machine.inspect();count=len(self.children)
        malformed=[None,{}, {'schema':fast.CLOCK_SCHEMA,'time_origin_ns':True},
                   {'schema':fast.CLOCK_SCHEMA,'time_origin_ns':-1},
                   {'schema':fast.CLOCK_SCHEMA,'time_origin_ns':fast.MAX_NS+1},
                   {'schema':'unknown','time_origin_ns':0}]
        for value in malformed:
            clock=self.root/'clock.json'
            if value is None:clock.unlink(missing_ok=True)
            else:clock.write_text(json.dumps(value))
            with self.subTest(value=value),self.assertRaises(ValueError):
                machine.restore_checkpoint(checkpoint)
        (self.root/'clock.json').write_text(' '*257)
        with self.assertRaises(ValueError):machine.restore_checkpoint(checkpoint)
        (self.root/'clock.json').write_text('{"schema":"lemmasim-fast-clock/1","time_origin_ns":0,"time_origin_ns":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):machine.restore_checkpoint(checkpoint)
        self.assertEqual(len(self.children),count)
        self.assertEqual(machine.inspect(),before)

    def test_global_deadline_and_raw_delivery_map_to_local_clock(self):
        machine=object.__new__(fast.Fast)
        machine.time_origin_ns=1000;machine.clock_hz=100000000
        machine.get=lambda name:'40'
        machine.inspect=lambda:{'literal':'observer fixture'}
        machine.clock=lambda:{'literal':'clock fixture'}
        machine.args=SimpleNamespace(timeout=1)
        calls=[]
        class QMP:
            def execute(self,command,arguments=None):
                calls.append((command,arguments))
                return '{}' if command=='qom-get' else {'status':'paused','running':False}
        machine.qmp=QMP()
        machine.run_until_ns(1120)
        machine.call('inject 115 pen 999 1 2 127 3 1 0')
        mutations=[row for row in calls if row[0] in ('qom-set','cont','stop')]
        self.assertEqual(mutations[0],('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':'120'}))
        self.assertEqual(calls[-1],('qom-set',{'path':'/machine/lemma-hardware','property':'external-event',
                         'value':'150 999 1 2 127 3 1 0'}))
        count=len(mutations)
        for target in (1000,fast.MAX_NS,fast.MAX_NS+1,True):
            with self.subTest(target=target),self.assertRaises(ValueError):machine.run_until_ns(target)
        # Reading the actual runstate is valid before admission; malformed
        # deadlines still must never change a property or resume execution.
        self.assertEqual(len([row for row in calls if row[0] in ('qom-set','cont','stop')]),count)


if __name__ == '__main__':
    unittest.main()
