"""Kernel lifecycle observers, not guest execution or fault qualification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from lemmasim_session import NotebookFaultObserver, Session


def row(kind, *fields):
    return ('K1 ' + ' '.join(f'{x:016x}' for x in (kind, *fields)) + '\n').encode()


class NotebookFault(unittest.TestCase):
    def test_only_current_primary_kernel_fault_stops_pacing(self):
        primary = row(0xf1, 0x2047, 1, 2, 0x100000)
        trap = row(0xf4, 0x2047, 227, 0, 13)
        helper = row(0xf4, 0x2087, 227, 0, 13)
        for observer in (NotebookFaultObserver(),):
            self.assertIsNone(observer.feed(trap))
            self.assertIsNone(observer.feed(primary + helper))
            self.assertIsNone(observer.feed(row(0xf4, 0x2047, 1, 0, 0)))
            self.assertIsNone(observer.feed(trap[:-1]))
            found = observer.feed(b'\n')
            self.assertEqual(found['cause'], '000000000000000d')
            self.assertEqual(found['descriptor'], '0000000000002047')
            observer.reset()
            self.assertIsNone(observer.feed(trap))
            self.assertIsNone(observer.feed(b'x' * 100000 + b'\n' + primary))
            self.assertEqual(observer.feed(trap), found)
        script = '''
import {NotebookFaultObserver} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const rows=JSON.parse(process.argv[1]), enc=x=>new TextEncoder().encode(x);
const o=new NotebookFaultObserver();
let text=rows.trap;assert.equal(o.observe(enc(text),0),null);
text+=rows.primary+rows.helper+rows.normal+rows.trap.slice(0,-1);
assert.equal(o.observe(enc(text),0),null);text+='\\n';
assert.equal(o.observe(enc(text),0).cause,'000000000000000d');
assert.equal(o.observe(enc(text),0).descriptor,'0000000000002047');
o.reset(text.length);assert.equal(o.observe(enc(text+rows.trap),text.length),null);
assert.throws(()=>o.observe(enc(''),text.length));
// A reset in the middle of an old line cannot adopt its newly emitted tail.
text=rows.primary;const n=3;o.reset(n);assert.equal(o.observe(enc(text+rows.trap),n),null);
text='x'.repeat(100000)+'\\n'+rows.primary+rows.trap;o.reset(0);
assert.equal(o.observe(enc(text),0).cause,'000000000000000d');
'''
        run = subprocess.run(['node', '--input-type=module', '-e', script, json.dumps(dict(
            primary=primary.decode(), trap=trap.decode(), helper=helper.decode(),
            normal=row(0xf4, 0x2047, 1, 0, 0).decode()))], cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_real_session_observation_keeps_backing_and_pauses_only_primary(self):
        class Machine:
            identity = {'backend': 'rtl'}
            def call(self, command):
                if command.startswith('run '): self.cycle += int(command.split()[1])
                return {'cycle': self.cycle}
            cycle = 0
            def close(self): pass
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            session = Session(Machine(), directory,
                SimpleNamespace(mode='student', paused=False, quantum=1000, workload='school-notebook'))
            try:
                uart = directory / 'uart.bin'
                uart.write_bytes(row(0xf1, 0x2047, 1, 2, 0) + row(0xf4, 0x2087, 227, 0, 13))
                session.run(1000)
                self.assertTrue(session.automatic)
                with uart.open('ab') as stream: stream.write(row(0xf4, 0x2047, 227, 0, 13))
                session.run(1000)
                self.assertFalse(session.automatic)
                self.assertEqual(session.dispatch({'action':'inspect'})['guest_fault']['cause'], '000000000000000d')
                session.notebook_epoch()
                session.automatic = True
                session.run(1000)
                self.assertTrue(session.automatic)
                self.assertIsNone(session.notebook_lifecycle.fault)
            finally:
                session.close()
