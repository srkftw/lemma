# SPDX-License-Identifier: Apache-2.0
"""Host-only reset/input identity, lock and process-group regressions."""
from pathlib import Path
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'conformance/silicon'))
import silicon_guest as guest
from notebook_observations import reset_identity


class CaptureLifetimeTests(unittest.TestCase):
    def options(self):
        return guest.bounded_options(SimpleNamespace(cycles=10,trace_limit=0,
            timeout=5,observer_cycle=10,block_trace=False))

    def data(self,path):
        entries={}
        for key in ('image','build','provenance','audit','dtb','descriptor','capacity'):
            item=path/(key+'.fixture');item.write_bytes(('host identity fixture '+key).encode())
            entries[key]=guest.identified(item)
        data={'schema_version':1,'profile':'lemma-silicon-dev/0.1.0',
              'profile_sha256':guest.sha(guest.PROFILE),'workloads':{'notebook':entries},
              'rtl_sources':{}}
        for key in ('binary','rom','rom_audit','rtl_build'):
            item=path/(key+'.fixture');item.write_bytes(('host identity fixture '+key).encode())
            data[key]=guest.identified(item)
        return data

    @staticmethod
    def outputs(path,exit_code=0):
        contents={'uart.bin':b'literal host-only fixture\n','panel':b'literal panel fixture',
                  'panel.events':b'cycle,event,sequence,x,y,gray\n',
                  'host-report.json':b'{"host_test":true}\n'}
        for name,value in contents.items():(path/name).write_bytes(value)
        result={'status':'STOPPED_BY_PROTOCOL' if exit_code==0 else 'FAILED',
                'exit_code':exit_code,'outputs':{name:guest.sha(path/name) for name in contents}}
        (path/'output.json').write_text(json.dumps(result))
        return result

    def capture(self,path,data):
        path.mkdir()
        initial=path/'initial-medium.raw';initial.write_bytes(b'acknowledged external-byte fixture')
        raw=path/'input.events';raw.write_bytes(b'10 pen 1 20000 22000 1024 3 1 0\n')
        identity={'schema_version':1,'transport':'lemma-silicon-events/1',
                  'profile':'lemma-silicon-dev/0.1.0','prepared':data,'workload':'notebook',
                  'options':self.options(),'reset_cycles':8,'clock_hz':100000000,
                  'ram_initialization':'zero external RAM plus exact ELF and DTB loads',
                  'inputs':{'events':guest.identified(raw)},'initial_medium':guest.identified(initial)}
        (path/'input.json').write_text(json.dumps(identity))
        result=self.outputs(path);result['final_medium_sha256']=guest.sha(initial)
        (path/'output.json').write_text(json.dumps(result))
        return identity

    def test_replay_regenerates_fresh_reset_input_and_locked_medium(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);data=self.data(path);original=path/'original'
            identity=self.capture(original,data);disk=path/'replay.raw';seen=[]
            def execute(selected,workload,directory,options,inputs,medium):
                self.assertEqual(selected,data)
                self.assertEqual(workload,'notebook')
                self.assertEqual(options['observer_cycle'],10)
                self.assertEqual(inputs['events']['path'],str(directory/'input.events'))
                self.assertNotEqual(inputs['events']['path'],identity['inputs']['events']['path'])
                self.assertEqual(guest.validate(inputs['events']).read_bytes(),(original/'input.events').read_bytes())
                with medium.open('rb') as competing:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(competing,fcntl.LOCK_EX|fcntl.LOCK_NB)
                reset=reset_identity(directory,'notebook',original/'initial-medium.raw',directory/'input.events')
                self.assertEqual(reset['prepared'],data)
                result=self.outputs(directory);result['final_medium_sha256']=guest.sha(medium)
                (directory/'output.json').write_text(json.dumps(result));seen.append(directory)
                return result
            with mock.patch.object(guest,'ROOT',path),mock.patch.object(guest,'execute',side_effect=execute), \
                 mock.patch.object(guest,'prepared',side_effect=AssertionError('captured identity must be selected')):
                guest.replay(SimpleNamespace(session=original,disk_copy=disk,timeout=5))
            self.assertEqual(len(seen),1)
            self.assertEqual(json.loads((seen[0]/'comparison.json').read_text())['status'],'MATCH')
            with disk.open('rb') as released:fcntl.flock(released,fcntl.LOCK_EX|fcntl.LOCK_NB)

    def test_replay_changed_raw_input_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);data=self.data(path);original=path/'original';self.capture(original,data)
            (original/'input.events').write_bytes(b'changed external input')
            with mock.patch.object(guest,'ROOT',path),mock.patch.object(guest,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'changed or missing'):
                    guest.replay(SimpleNamespace(session=original,disk_copy=path/'new.raw',timeout=5))
                execute.assert_not_called()

    def test_replay_existing_medium_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);data=self.data(path);original=path/'original';self.capture(original,data)
            disk=path/'existing.raw';disk.write_bytes(b'keep these bytes')
            with mock.patch.object(guest,'ROOT',path),mock.patch.object(guest,'execute') as execute:
                with self.assertRaisesRegex(ValueError,'must be new'):
                    guest.replay(SimpleNamespace(session=original,disk_copy=disk,timeout=5))
                execute.assert_not_called()
            self.assertEqual(disk.read_bytes(),b'keep these bytes')

    def test_replay_actual_failure_keeps_failed_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);data=self.data(path);original=path/'original';self.capture(original,data)
            seen=[]
            def execute(selected,workload,directory,options,inputs,medium):
                result=self.outputs(directory,exit_code=3);result['final_medium_sha256']=guest.sha(medium)
                (directory/'output.json').write_text(json.dumps(result));seen.append(directory);return result
            with mock.patch.object(guest,'ROOT',path),mock.patch.object(guest,'execute',side_effect=execute):
                with self.assertRaisesRegex(RuntimeError,'outputs differ'):
                    guest.replay(SimpleNamespace(session=original,disk_copy=path/'new.raw',timeout=5))
            comparison=json.loads((seen[0]/'comparison.json').read_text())
            self.assertEqual(comparison['status'],'MISMATCH')
            self.assertFalse(comparison['compared']['exit_code'])

    def test_medium_lock_conflict_never_launches_the_hart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);disk=path/'locked.raw';disk.write_bytes(b'raw fixture')
            args=SimpleNamespace(**self.options(),workload='notebook',geometry=None,mode='developer',
                record=path/'capture',uart_input=None,events=None,disk=disk,raw_input=None,fault=None)
            with disk.open('rb') as owner:
                fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with mock.patch.object(guest,'execute') as execute:
                    with mock.patch.object(guest,'prepared',return_value=self.data(path)):
                        with self.assertRaises(BlockingIOError):guest.run(args)
                    execute.assert_not_called()

    def test_real_host_fixture_inherits_the_launcher_process_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);script=path/'stub-host'
            script.write_text('#!'+sys.executable+'\nimport os,pathlib\npathlib.Path('+repr(str(path/'group'))+').write_text(str(os.getpgrp()))\n')
            script.chmod(0o755)
            data={'binary':{'path':str(script)},'rom':{'path':'fixture-rom'},
                  'workloads':{'service':{'image':{'path':'fixture-image'},'dtb':{'path':'fixture-dtb'}}}}
            result=guest.execute(data,'service',path,self.options(),{},None)
            self.assertEqual(result['exit_code'],0)
            self.assertEqual(int((path/'group').read_text()),os.getpgrp())

    def test_internal_timeout_kills_and_reaps_only_the_hart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);process=mock.Mock(returncode=-9)
            process.wait.side_effect=[subprocess.TimeoutExpired('fixture-hart',15),-9]
            process.poll.return_value=-9
            data={'binary':{'path':'fixture-hart'},'rom':{'path':'fixture-rom'},
                  'workloads':{'service':{'image':{'path':'fixture-image'},'dtb':{'path':'fixture-dtb'}}}}
            with mock.patch.object(guest.subprocess,'Popen',return_value=process) as launched, \
                 mock.patch.object(guest.os,'killpg') as kill_group:
                result=guest.execute(data,'service',path,self.options(),{},None)
            self.assertFalse(launched.call_args.kwargs.get('start_new_session',False))
            process.kill.assert_called_once_with();self.assertEqual(process.wait.call_count,2)
            kill_group.assert_not_called();self.assertEqual(result['status'],'WALL_TIMEOUT')

    def test_exception_cleanup_kills_and_reaps_only_the_hart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary);process=mock.Mock()
            process.wait.side_effect=[KeyboardInterrupt(),-9];process.poll.return_value=None
            data={'binary':{'path':'fixture-hart'},'rom':{'path':'fixture-rom'},
                  'workloads':{'service':{'image':{'path':'fixture-image'},'dtb':{'path':'fixture-dtb'}}}}
            with mock.patch.object(guest.subprocess,'Popen',return_value=process), \
                 mock.patch.object(guest.os,'killpg') as kill_group:
                with self.assertRaises(KeyboardInterrupt):guest.execute(data,'service',path,self.options(),{},None)
            process.kill.assert_called_once_with();self.assertEqual(process.wait.call_count,2)
            kill_group.assert_not_called()
            self.assertEqual(json.loads((path/'output.json').read_text())['status'],'NOT_RUN')


if __name__=='__main__':unittest.main()
