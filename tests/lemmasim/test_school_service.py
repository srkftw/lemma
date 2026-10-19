"""External byte transport boundaries; not guest or assessment qualification."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from lemmasim_school_service import submission_stream,school_capability

QUEUE=0x5351000000000011

def row(tag,*words):return ('K1 '+' '.join(f'{v:016x}' for v in (tag,*words))+'\n').encode()
def fixture():
    payload=bytes(range(256))+b'12345678'
    records=[row(0x72e,QUEUE,23,len(payload),2)]
    for offset in range(0,len(payload),16):
        part=payload[offset:offset+16];a,b=struct.unpack('<2Q',part.ljust(16,b'\0'))
        records.append(row(0x72f,QUEUE,offset|(len(part)<<48),a,b))
    records.append(row(0x730,QUEUE,23,len(payload),0))
    return payload,records

class SchoolByteTransport(unittest.TestCase):
    def test_versioned_capability_and_actual_receipt_scope(self):
        for version,chunks in ((1,8),(2,512)):
            self.assertEqual(school_capability(row(0x731,version,chunks,262144,2))['maximumChunks'],chunks)
        for version,chunks in ((3,512),(1,512),(2,513)):
            with self.assertRaises(ValueError):school_capability(row(0x731,version,chunks,262144,2))
        script=r"""
import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const source=await fs.readFile('sim/browser/school_transport.js','utf8');
const {guestSchoolCapability,guestSchoolQueueState}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const bytes=Uint8Array.from(Buffer.from(process.argv[1],'hex'));
assert.deepEqual(guestSchoolCapability(bytes),{version:2,maximumChunks:512,maximumBytes:262144,selection:2});
const queue=guestSchoolQueueState(bytes);assert.equal(queue.state,'acknowledged');assert.equal(queue.queue,process.argv[2]);
assert.equal(queue.observation,'restored-pointer-read');assert.equal(queue.observedFrontier,'99');
assert.equal(guestSchoolQueueState(bytes,bytes.length),null);
assert.throws(()=>guestSchoolCapability(Uint8Array.from(Buffer.from(process.argv[3],'hex'))));
"""
        data=row(0x731,2,512,262144,2)+row(0x72e,QUEUE,23,4320,2)+row(0x733,QUEUE,71,31,3)+row(0x734,QUEUE,71,99,3)
        result=subprocess.run(['node','--input-type=module','-e',script,data.hex(),str(QUEUE),row(0x731,1,512,262144,2).hex()],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_full_width_identity_and_odd_word_boundary(self):
        payload,records=fixture();result=submission_stream(b''.join(records))
        self.assertEqual(result['queue'],QUEUE);self.assertEqual(result['commit'],23)
        self.assertEqual(bytes(result['bytes']),payload)

    def test_partial_new_mixed_reordered_and_false_end_reject(self):
        _,records=fixture()
        for data in (b''.join(records[:-1]),b''.join(records)+records[0],
                     b''.join([records[0],records[2],records[1],*records[3:]]),
                     b''.join(records[:-1])+row(0x730,QUEUE,24,264,0),
                     b''.join([records[0],row(0x72f,QUEUE+1,16<<48,0,0),*records[2:]])):
            with self.assertRaises(ValueError):submission_stream(data)

    def test_browser_copies_same_bytes_and_preserves_ack_identity(self):
        payload,records=fixture()
        script=r"""
import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const source=await fs.readFile('sim/browser/school_transport.js','utf8');
const {guestSchoolSubmission,schoolAcknowledgement}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const rows=Uint8Array.from(Buffer.from(process.argv[1],'hex')),stream=guestSchoolSubmission(rows),reply=JSON.parse(process.argv[2]);
assert.equal(stream.queue,BigInt(reply.queueObject));assert.equal(Buffer.from(stream.bytes).toString('hex'),process.argv[3]);
const ack=schoolAcknowledgement(stream,reply);assert.equal(new DataView(ack.buffer).getBigUint64(24,true),stream.queue);
assert.equal(new DataView(ack.buffer).getBigUint64(48,true),23n);
assert.throws(()=>schoolAcknowledgement(stream,{...reply,queueObject:String(stream.queue+1n)}));
assert.throws(()=>schoolAcknowledgement(stream,{...reply,envelopeCRC32:0}));
assert.throws(()=>guestSchoolSubmission(rows.subarray(0,rows.length-1)));
"""
        import zlib
        reply=dict(queueObject=str(QUEUE),commitSequence='9007199254740997',envelopeCRC32=zlib.crc32(payload))
        result=subprocess.run(['node','--input-type=module','-e',script,b''.join(records).hex(),json.dumps(reply),payload.hex()],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
