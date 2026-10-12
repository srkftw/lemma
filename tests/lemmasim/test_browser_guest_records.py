"""Browser status observer; this does not establish guest or Wasm execution."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

class BrowserGuestRecords(unittest.TestCase):
    def test_reset_history_partial_and_unrelated_records_cannot_claim_ready(self):
        script=r"""
import {guestRecord} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const encode=x=>new TextEncoder().encode(x);
const ready='K1 0000000000000420 0000000000000000 0000000000000000 0000000000000000 0000000000000000\n';
const old=encode(ready),partial=encode(ready.slice(0,-1));
assert.equal(guestRecord(old,0,'0000000000000420'),true);
assert.equal(guestRecord(old,old.length,'0000000000000420'),false);
assert.equal(guestRecord(partial,0,'0000000000000420'),false);
assert.equal(guestRecord(encode(ready+'booting\n'),old.length,'0000000000000420'),false);
assert.equal(guestRecord(encode(ready+ready),old.length,'0000000000000420'),true);
assert.equal(guestRecord(encode(ready.replace('0420','041f')),0,'0000000000000420'),false);
assert.equal(guestRecord(encode('prefix'+ready),0,'0000000000000420'),false);
assert.equal(guestRecord(encode(ready.replace('0000000000000000','wrong')),0,'0000000000000420'),false);
assert.throws(()=>guestRecord(old,old.length+1,'0000000000000420'));
assert.throws(()=>guestRecord(old,0,'0420'));
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

if __name__=='__main__':unittest.main()
