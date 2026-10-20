"""Browser status observer; this does not establish guest or Wasm execution."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

class BrowserGuestRecords(unittest.TestCase):
    def test_recoverable_course_rejection_needs_complete_current_guest_receipt(self):
        script=r"""
import {guestCourseRejection} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const encode=x=>new TextEncoder().encode(x);
const row=(status=175n,page=1n,ns=1n,detail=0n)=>'K1 '+[0x454n,status,page,ns,detail].map(x=>x.toString(16).padStart(16,'0')).join(' ')+'\n';
const text=row();assert.deepEqual(guestCourseRejection(encode(text),0),{authority:'compiled-guest-report',status:'175',page:'1',namespace:'1'});
for(const invalid of [text.slice(0,-1),'prefix'+text,row(0n),row(256n),row(1n,0n),row(1n,1n,0n),row(1n,1n,1n,2n)])assert.equal(guestCourseRejection(encode(invalid),0),null);
assert.equal(guestCourseRejection(encode(text),text.length),null);
assert.equal(guestCourseRejection(encode(text+row(230n,9007199254740993n)),0).page,'9007199254740993');
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_only_complete_current_installation_receipt_can_present_success(self):
        script=r"""
import {guestCourseInstallState} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const encode=x=>new TextEncoder().encode(x);
const row=(outcome=1n,sequence=9007199254740993n,object=0x20001n,crc=0x12345678n)=>'K1 '+[0x4b1n,outcome,sequence,object,crc].map(x=>x.toString(16).padStart(16,'0')).join(' ')+'\n';
const receipt=row();
assert.deepEqual(guestCourseInstallState(encode(receipt),0),{authority:'compiled-guest-report',state:'installed',status:'0',identity:'1',edition:'2',sequence:'9007199254740993',crc32:'305419896'});
assert.equal(guestCourseInstallState(encode(receipt),receipt.length),null);
for(const text of [receipt.slice(0,-1),'prefix'+receipt,row(2n),row(1n,0n),row(0x10001n),row(1n,1n,0x20000n),row(1n,1n,1n),row(1n,1n,1n<<48n),row(1n,1n,0x20001n,1n<<32n)])assert.equal(guestCourseInstallState(encode(text),0),null);
const failure=guestCourseInstallState(encode(row(0xdf01n,0n)),0);
assert.equal(failure.state,'failed');assert.equal(failure.status,'223');assert.equal(failure.sequence,'0');
assert.equal(guestCourseInstallState(encode(receipt+row(0xe301n,0n)),0).status,'227');
for(const operation of [2n,3n,8n,9n,10n]){
 const selected=row(operation,4n);
 assert.deepEqual(guestCourseInstallState(encode(receipt+selected),0),guestCourseInstallState(encode(receipt),0));
 assert.equal(guestCourseInstallState(encode(receipt+selected),receipt.length),null);
 assert.equal(guestCourseInstallState(encode(receipt+row(0xe301n,0n)+selected),0).state,'failed');
}
assert.equal(guestCourseInstallState(encode(receipt+row(1n,0n)+row(9n)),0),null);
assert.equal(guestCourseInstallState(encode(receipt+row(9n)+row(1n,7n,0x20323n)),0).identity,'803');
assert.equal(guestCourseInstallState(encode(receipt+row(1n,7n).slice(0,-1)),0).sequence,'9007199254740993');
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_selected_publication_is_a_separate_validated_guest_receipt(self):
        script=r"""
import {guestCourseInstallState,guestCourseSelectionState} from './sim/browser/guest_records.js';
import assert from 'node:assert/strict';
const encode=x=>new TextEncoder().encode(x);
const row=(status=0n,sequence=9007199254740993n,object=0x10324n,crc=0n)=>'K1 '+[0x4b9n,status,sequence,object,crc].map(x=>x.toString(16).padStart(16,'0')).join(' ')+'\n';
const text=row(),expected={authority:'compiled-guest-report',state:'selected',status:'0',identity:'804',edition:'1',sequence:'9007199254740993',crc32:'0'};
assert.deepEqual(guestCourseSelectionState(encode(text),0),expected);
assert.equal(guestCourseSelectionState(encode(text),text.length),null);
for(const bad of [text.slice(0,-1),'prefix'+text,row(256n),row(0n,0n),row(0n,1n,1n),row(0n,1n,0x10000n),row(0n,1n,1n<<48n),row(0n,1n,0x10324n,1n<<32n),row(0n,0x7fffffffffffffffn)]){
 assert.equal(guestCourseSelectionState(encode(bad),0),null);
 if(bad.startsWith('K1 ')&&bad.endsWith('\n'))assert.equal(guestCourseSelectionState(encode(text+bad),0),null,'malformed latest tuple retained older selection');
}
assert.equal(guestCourseSelectionState(encode(text+row(223n,0n)),0).state,'failed');
assert.equal(guestCourseSelectionState(encode(text+row(0n,7n,0x20323n,123n)),0).identity,'803');
const failure='K1 '+[0x4b1n,0xdf01n,0n,0x10324n,0n].map(x=>x.toString(16).padStart(16,'0')).join(' ')+'\n';
assert.equal(guestCourseInstallState(encode(failure+text),0).status,'223');
assert.deepEqual(guestCourseSelectionState(encode(failure+text),0),expected);
assert.equal(guestCourseSelectionState(encode(failure),0),null);
assert.throws(()=>guestCourseSelectionState(encode(text),-1));
"""
        run=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

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
