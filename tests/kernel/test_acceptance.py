"""Acceptance evidence failure fixtures, not target execution evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_kernel import matrix, validate_session, stop_controller_children
from core0_common import Core0Error, sha256
from run_kernel import Session, validate_reaped_process
from action_cache import process_identity


class AcceptanceFailures(unittest.TestCase):
    def setUp(self):
        (ROOT/'build/kernel').mkdir(parents=True, exist_ok=True)

    def test_interrupted_guest_context_owns_actual_wait_status_and_cleanup(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            p=Path(temporary); image=p/'image.elf'; image.write_bytes(b'host-fixture-not-ELF')
            for name in ('audit.json','provenance.json'): (p/name).write_text('{}')
            # This is a sleeping host fixture, not a QEMU/target observation.
            executable=p/'qemu-system-riscv64'
            ready=p/'fixture-ready'
            executable.write_text(f'#!{sys.executable}\nimport os, time\nfrom pathlib import Path\n'
                                  f'Path({str(ready)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n');executable.chmod(0o700)
            output=p/'interrupted-host-fixture'
            with patch('run_kernel.audit',return_value={'status':'PASS'}), patch('run_kernel.source_inputs',return_value={'fixture':'hash'}), \
                 patch('run_kernel.require_tools',return_value={'qemu-system-riscv64':str(executable)}), patch('run_kernel.qemu_argv',return_value=(str(executable),)):
                with self.assertRaises(Core0Error):
                    with Session(root=ROOT,image=image,output_dir=output) as session:
                        deadline=time.monotonic()+5
                        while not ready.exists() and time.monotonic()<deadline:
                            if session.process.poll() is not None:
                                self.fail('sleeping host fixture exited before readiness')
                            time.sleep(0.01)
                        self.assertTrue(ready.exists(), 'sleeping host fixture did not start')
                        self.assertEqual(ready.read_text(), str(session.process.pid))
                        self.assertIn(str(executable).encode(), Path('/proc', str(session.process.pid), 'cmdline').read_bytes())
                        rows=stop_controller_children(defer_qemu=True)
                        self.assertIn({'pid':session.process.pid,'deferred_to_guest_runner':True},rows)
                        self.assertIsNone(session.process.poll())
                        raise Core0Error('host fixture interruption')
            value=json.loads((output/'result.json').read_text())
            self.assertEqual((value['status'],value['returncode']),('FAIL',-9))
            self.assertEqual(value['cleanup'],{'explicit_host_stop':True,'process_group_killed':True,
                                               'target_exited_before_cleanup':False,'process_reaped':True})
            self.assertFalse(Path('/proc',str(value['pid'])).exists())
            self.assertEqual(value['process_identity']['pid'], value['pid'])
            self.assertTrue(value['process_identity']['boot_id'])
            self.assertTrue(value['process_identity']['start_ticks'].isdigit())

    def test_historical_reap_survives_recycled_pid_but_same_live_owner_rejects(self):
        # This real host process is unrelated to any historical guest receipt.
        # Its PID existence alone cannot undo an observed historical wait().
        owner = process_identity()
        historical = {"pid": os.getpid(), "cleanup": {"process_reaped": True}}
        validate_reaped_process(historical)
        previous = {**owner, "start_ticks": str(int(owner["start_ticks"]) - 1)}
        validate_reaped_process({**historical, "process_identity": previous})
        validate_reaped_process({**historical, "process_identity": {**owner, "boot_id": "another-boot"}})
        for identity in (owner, {**owner, "start_ticks": int(owner["start_ticks"])}):
            with self.assertRaisesRegex(Core0Error, "still present"):
                validate_reaped_process({**historical, "process_identity": identity})
        for identity in (None, {"pid": os.getpid()}, {**owner, "pid": os.getpid() + 1},
                         {**owner, "start_ticks": None}, {**owner, "extra": "unexpected"}):
            with self.assertRaisesRegex(Core0Error, "malformed"):
                validate_reaped_process({**historical, "process_identity": identity})
        for invalid in ({**historical, "cleanup": {"process_reaped": False}},
                        {**historical, "cleanup": {"process_reaped": 1}}, {**historical, "pid": -1}):
            with self.assertRaises(Core0Error):
                validate_reaped_process(invalid)

    def test_interruption_kills_and_reaps_independent_tool_child(self):
        # A real host-only child proves that interruption does not leak the
        # independent tool process group used by the common command helper.
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        try:
            rows = stop_controller_children()
            row = next(value for value in rows if value['pid'] == child.pid)
            self.assertEqual(row['returncode'], -9)
            child.returncode = row['returncode']
            self.assertTrue(row['explicit_host_stop'] and row['process_group_killed'] and row['process_reaped'])
            self.assertFalse(Path('/proc', str(child.pid)).exists())
            with self.assertRaises(ChildProcessError): os.waitpid(child.pid, os.WNOHANG)
        finally:
            if Path('/proc', str(child.pid)).exists():
                os.killpg(child.pid, 9); child.wait()

    def test_required_matrix_has_all_profiles_and_no_later_gate_configuration(self):
        rows = matrix()
        self.assertEqual((len(rows), len(set(rows))), (20, 20))
        for optimization in ('O0', 'O2'):
            self.assertIn(('normal', 'bootstrap-m', optimization), rows)
            self.assertIn(('normal', 'supervisor', optimization), rows)
            self.assertIn(('frames-development', 'bootstrap-m', optimization), rows)
            self.assertIn(('machine-origin-development', 'bootstrap-m', optimization), rows)
            self.assertIn(('user-syscall-development', 'supervisor', optimization), rows)

    def test_missing_raw_source_and_packet_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            p = Path(temporary); image = p/'image.elf'; image.write_bytes(b'host-fixture-not-ELF')
            (p/'audit.json').write_text('{}'); (p/'provenance.json').write_text(json.dumps({'source_inputs': {'fixture': 'hash'}}))
            raw = b'K1' + b' 0000000000000000' * 5 + b'\n'
            for name, value in [('received.bin', raw), ('sent.bin', b''), ('stderr.bin', b'')]: (p/name).write_bytes(value)
            report = {'status':'PASS', 'image_sha256':sha256(image), 'audit_sha256':sha256(p/'audit.json'),
                      'provenance_sha256':sha256(p/'provenance.json'), 'source_inputs': {'fixture':'hash'},
                      'pid':2**31-1, 'returncode':-9, 'guest_live_before_cleanup':True, 'records':[[0]*5],
                      'cleanup':{'explicit_host_stop':True,'process_group_killed':True,'target_exited_before_cleanup':False,'process_reaped':True},
                      'raw_artifacts':{name:sha256(p/name) for name in ('received.bin','sent.bin','stderr.bin')}}
            result = p/'result.json'; result.write_text(json.dumps(report)); validate_session(result,image)
            recycled = {**report, 'pid': os.getpid()}
            result.write_text(json.dumps(recycled)); validate_session(result,image)
            result.write_text(json.dumps({**recycled, 'process_identity': process_identity()}))
            with self.assertRaisesRegex(Core0Error, 'still present'):
                validate_session(result,image)
            for key, value in [('raw_artifacts', {}), ('source_inputs', {}), ('records', [[1]*5]),
                               ('cleanup',{'explicit_host_stop':True,'process_group_killed':True,'process_reaped':True})]:
                bad = {**report, key:value}; result.write_text(json.dumps(bad))
                with self.assertRaises(Core0Error): validate_session(result,image)
