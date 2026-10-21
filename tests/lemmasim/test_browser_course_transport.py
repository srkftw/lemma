"""Raw host framing; target package validation/durability require real guest observations."""
from pathlib import Path
import subprocess,unittest
ROOT=Path(__file__).resolve().parents[2]
class CourseTransport(unittest.TestCase):
 def test_complete_opaque_packet_and_64_bit_boundaries(self):
  script=r"""
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const source=await fs.readFile('sim/browser/course_transport.js','utf8');
const {courseInstallFrame,courseInstallRows,courseSchoolFrames,schoolSelectionRequested}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const input=new ArrayBuffer(32768),v=new DataView(input);v.setBigUint64(24,65535n,true);v.setBigUint64(32,4294967295n,true);v.setBigUint64(80,4294967295n,true);
new Uint8Array(input).fill(0xa5,128);
const packet=courseInstallFrame(input,'9223372036854775807'),rows=courseInstallRows(packet,'18446744073709551615');
assert.equal(packet.length,32832);assert(rows.every(x=>x.length<=256));
const observed=Buffer.from(rows.map(r=>r.split(' ')[2]).join(''),'hex');
assert.deepEqual(observed,Buffer.from(packet));assert.deepEqual(observed.subarray(64),Buffer.from(input));
assert.deepEqual(Array.from({length:8},(_,i)=>observed.readBigUInt64LE(8*i)),[0x31504b43414d454cn,1n,1n,65535n,4294967295n,32768n,9223372036854775807n,4294967295n]);
for(const transaction of ['0','-1','+1','01','1.0','9007199254740993x','9223372036854775808',1,1n])assert.throws(()=>courseInstallFrame(input,transaction));
for(const n of [0,127,32769])assert.throws(()=>courseInstallFrame(new ArrayBuffer(n),'1'));
for(const [offset,value]of [[24,0n],[24,65536n],[32,0n],[32,4294967296n],[80,4294967296n]]){const before=v.getBigUint64(offset,true);v.setBigUint64(offset,value,true);assert.throws(()=>courseInstallFrame(input,'1'));v.setBigUint64(offset,before,true);}
for(const cycle of ['-1','1.5','18446744073709551616',1n,1])assert.throws(()=>courseInstallRows(packet,cycle));
// An invalid package checksum is copied unchanged; only the guest checks it.
v.setBigUint64(80,1n,true);assert.equal(new DataView(courseInstallFrame(input,'1').buffer).getBigUint64(56,true),1n);
// Invitation/help packages are transport payloads. They must never append a
// selection command that retargets the guest away from its authored activity.
for(const operation of ['sample','install','review','join','help','submit','cancel','feedback','unknown']){
 const explicit=['sample','install','review'].includes(operation);
 const selected=courseSchoolFrames(input,'8',schoolSelectionRequested(operation,true),4);
 assert.equal(selected.length,packet.length+(explicit?64:0));
 assert.deepEqual(selected.subarray(64,32832),new Uint8Array(input));
 if(explicit){const tail=new DataView(selected.buffer,32832,64);assert.equal(tail.getBigUint64(16,true),9n);assert.equal(tail.getBigUint64(40,true),4n);}
 assert.equal(schoolSelectionRequested(operation,false),false);
}
"""
  r=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
