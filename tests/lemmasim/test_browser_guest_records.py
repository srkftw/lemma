"""Browser status observer; this does not establish guest or Wasm execution."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

class BrowserGuestRecords(unittest.TestCase):
    def test_reset_history_partial_and_unrelated_records_cannot_claim_ready(self):
        script=r"""
import {guestRecord,guestRecordFields,guestPageReady} from './sim/browser/guest_records.js';
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
// A main-loop prefix and accepted display work must never report Ready.
const opened=sequence=>'K1 0000000000000425 '+sequence+' 0000000000000001 0000000000000001 0000000000000000\n';
const data=encode(ready+opened('0000000000000002'));
assert.equal(guestPageReady(old,0,{completed:'1',accepted:'1'}),false);
assert.equal(guestPageReady(data,0,{completed:'0',accepted:'2'}),false);
assert.equal(guestPageReady(data,0,{completed:'1',accepted:'2'}),false);
assert.equal(guestPageReady(data,0,{completed:'2',accepted:'2'}),true);
assert.equal(guestPageReady(data,data.length,{completed:'2',accepted:'2'}),false);
const adjacent=encode(ready+opened('0000000000000002')+opened('0000000000000003'));
assert.equal(guestRecordFields(adjacent,0,'0000000000000425')[0],'0000000000000003');
assert.equal(guestPageReady(adjacent,0,{completed:'2',accepted:'3'}),false);
assert.equal(guestPageReady(adjacent,0,{completed:'3',accepted:'3'}),true);
const large=encode(ready+opened('0020000000000001'));
assert.equal(guestPageReady(large,0,{completed:'9007199254740992',accepted:'9007199254740993'}),false);
assert.equal(guestPageReady(large,0,{completed:'9007199254740993',accepted:'9007199254740993'}),true);
assert.throws(()=>guestPageReady(large,0,{completed:9007199254740993,accepted:'9007199254740993'}));
assert.equal(guestPageReady(encode(ready+opened('0000000000000000')),0,{completed:'0',accepted:'0'}),false);
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_guest_publication_is_complete_ordered_and_launch_local(self):
        script=r"""
import {guestCommitState} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const encode=x=>new TextEncoder().encode(x);
const row=(kind,value,page=1n,ns=1n,detail=0x8001n)=>'K1 '+[kind,value,page,ns,detail].map(x=>x.toString(16).padStart(16,'0')).join(' ')+'\n';
const pending=row(0x423n,26n),saved=row(0x421n,26n),failed=row(0x424n,227n);
for(const text of ['',saved.slice(0,-1),'prefix'+saved,saved.replace('0000000000000421','0000000000000425'),saved.replace('000000000000001a','00000000000000xz')])
 assert.equal(guestCommitState(encode(text),0),null);
assert.equal(guestCommitState(encode(saved),saved.length),null);
assert.equal(guestCommitState(encode(saved+pending),saved.length).state,'pending');
assert.equal(guestCommitState(encode(pending+saved+failed),0).state,'failed');
assert.equal(guestCommitState(encode(saved+failed+pending),0).state,'pending');
assert.deepEqual(guestCommitState(encode(pending+failed+saved),0),{authority:'compiled-guest-report',state:'saved',recordKind:'0000000000000421',value:'26',page:'1',namespace:'1',detail:'32769'});
assert.equal(guestCommitState(encode(saved.replace('\n','\r\n')),0).value,'26');
const largest=guestCommitState(encode(row(0x421n,18446744073709551615n,9007199254740993n)),0);
assert.equal(largest.value,'18446744073709551615');assert.equal(largest.page,'9007199254740993');
for(const bad of [-1,0.5,Infinity,'0',100000])assert.throws(()=>guestCommitState(encode(saved),bad));
assert.throws(()=>guestCommitState(saved,0));
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,
                           capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

if __name__=='__main__':unittest.main()
