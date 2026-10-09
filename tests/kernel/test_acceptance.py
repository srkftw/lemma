"""Acceptance evidence failure fixtures, not target execution evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_kernel import matrix, validate_session, stop_controller_children
from core0_common import Core0Error, sha256
from run_kernel import Session


class AcceptanceFailures(unittest.TestCase):
    def test_interrupted_guest_context_owns_actual_wait_status_and_cleanup(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build/kernel') as temporary:
            p=Path(temporary); image=p/'image.elf'; image.write_bytes(b'host-fixture-not-ELF')
            for name in ('audit.json','provenance.json'): (p/name).write_text('{}')
            # This is a sleeping host fixture, not a QEMU/target observation.
            executable=p/'qemu-system-riscv64'
            executable.write_text(f'#!{sys.executable}\nimport time\ntime.sleep(60)\n');executable.chmod(0o700)
            output=p/'interrupted-host-fixture'
            with patch('run_kernel.audit',return_value={'status':'PASS'}), patch('run_kernel.source_inputs',return_value={'fixture':'hash'}), \
                 patch('run_kernel.require_tools',return_value={'qemu-system-riscv64':str(executable)}), patch('run_kernel.qemu_argv',return_value=(str(executable),)):
                with self.assertRaises(Core0Error):
                    with Session(root=ROOT,image=image,output_dir=output) as session:
                        rows=stop_controller_children(defer_qemu=True)
                        self.assertIn({'pid':session.process.pid,'deferred_to_guest_runner':True},rows)
                        self.assertIsNone(session.process.poll())
                        raise Core0Error('host fixture interruption')
            value=json.loads((output/'result.json').read_text())
            self.assertEqual((value['status'],value['returncode']),('FAIL',-9))
            self.assertEqual(value['cleanup'],{'explicit_host_stop':True,'process_group_killed':True,
                                               'target_exited_before_cleanup':False,'process_reaped':True})
            self.assertFalse(Path('/proc',str(value['pid'])).exists())

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
        self.assertEqual((len(rows), len(set(rows))), (18, 18))
        for optimization in ('O0', 'O2'):
            self.assertIn(('normal', 'bootstrap-m', optimization), rows)
            self.assertIn(('normal', 'supervisor', optimization), rows)
            self.assertIn(('frames-development', 'bootstrap-m', optimization), rows)
            self.assertIn(('machine-origin-development', 'bootstrap-m', optimization), rows)

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
            for key, value in [('raw_artifacts', {}), ('source_inputs', {}), ('records', [[1]*5]),
                               ('cleanup',{'explicit_host_stop':True,'process_group_killed':True,'process_reaped':True})]:
                bad = {**report, key:value}; result.write_text(json.dumps(bad))
                with self.assertRaises(Core0Error): validate_session(result,image)
