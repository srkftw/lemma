"""External byte transport boundaries; not guest or assessment qualification."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import Future
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from lemmasim_school_service import submission_stream,school_capability,SchoolService

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
    def test_only_explicit_course_or_review_intent_selects_a_publication(self):
        for operation in ('install','review','join','help'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as name:
                directory=Path(name);uart=directory/'uart.bin'
                uart.write_bytes(row(0x731,2,512,262144,2));(directory/'session.json').write_text('{}')
                state={'cycle':100,'devices':{'uart_ingress':{'enabled':True,'pending':0}}}
                session=SimpleNamespace(directory=directory,machine=SimpleNamespace(call=lambda _:state),
                                        ensure_capture_certain=lambda:None)
                service=SchoolService(session)
                identity=60000 if operation=='join' else 60001 if operation=='help' else 803
                payload=bytearray(256);struct.pack_into('<2Q',payload,24,identity,2);struct.pack_into('<Q',payload,80,123)
                result={'package_hex':payload.hex(),'node':3}
                if operation=='help':result['decision']='help.1'
                future=Future();future.set_result(result)
                service.jobs['operation']={'status':'pending','operation':operation,'epoch':service.epoch,
                    'binding':'joined-session','review':'original-review',
                    'ask':{'sequence':1,'revision':5,'object':13},'future':future}
                packets=[]
                try:
                    with patch('lemmasim_school_service.uart_path',return_value=uart), \
                         patch.object(service,'admit_packet',side_effect=lambda packet,_:packets.append(packet)):
                        service.pump()
                    self.assertEqual(service.jobs['operation']['status'],'completed')
                    self.assertEqual(len(packets),1);packet=packets[0]
                    self.assertEqual(packet[64:320],payload)
                    if operation in ('install','review'):
                        self.assertEqual(len(packet),384)
                        selection=struct.unpack('<8Q',packet[320:])
                        self.assertEqual(selection[2:6],(9,803,2,3))
                    else:
                        self.assertEqual(len(packet),320,'invitation/help must not retarget the guest reader')
                finally:service.close()

    def test_selection_remains_opt_in_and_legacy_guest_gets_install_only(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);uart=directory/'uart.bin';uart.write_bytes(b'')
            (directory/'session.json').write_text('{}')
            session=SimpleNamespace(directory=directory,machine=SimpleNamespace(call=lambda _: {
                'cycle':100,'devices':{'uart_ingress':{'enabled':True,'pending':0}}}),ensure_capture_certain=lambda:None)
            service=SchoolService(session);payload=bytearray(256)
            struct.pack_into('<2Q',payload,24,803,2);struct.pack_into('<Q',payload,80,123)
            packets=[]
            try:
                with patch('lemmasim_school_service.uart_path',return_value=uart), \
                     patch.object(service,'admit_packet',side_effect=lambda packet,_:packets.append(packet)):
                    service.admit({'package_hex':payload.hex()},select_publication=True)
                    uart.write_bytes(row(0x731,2,512,262144,2))
                    service.admit({'package_hex':payload.hex()})
                self.assertEqual([len(packet) for packet in packets],[320,320])
            finally:service.close()

    def test_delivery_keeps_original_peer_and_does_not_infer_visibility(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);uart=directory/'uart.bin';uart.write_bytes(b'')
            (directory/'session.json').write_text('{}')
            paper={'status':1,'completed':4,'pending_sequence':5,'target_sha256':'a'*64,'visible_sha256':'b'*64}
            session=SimpleNamespace(directory=directory,machine=SimpleNamespace(call=lambda _:{'cycle':100,'devices':{'paper':paper}}))
            service=SchoolService(session);original=('http://127.0.0.1:1/v1/client','a'*64)
            service.connection=original
            service.delivery={'decision':'work.7','sequence':7,'revision':9,'object':13,'cursor':0,'partial':b'',
                              'accepted':False,'snapshots':0,'lastBusy':None}
            try:
                with patch('lemmasim_school_service.uart_path',return_value=uart):
                    uart.write_bytes(row(0x725,6,1,0,0)+row(0x724,0,9,13,0))
                    service.observe_delivery();self.assertEqual(service.receipts,{})
                    with uart.open('ab') as stream:stream.write(row(0x725,7,1,0,0)[:-1])
                    service.observe_delivery();self.assertEqual(service.receipts,{})
                    with uart.open('ab') as stream:stream.write(b'\n')
                    service.observe_delivery();paper['status']=0;paper['completed']=5;service.observe_delivery()
                    before=len(service.receipts);service.observe_delivery();self.assertEqual(len(service.receipts),before)
                    service.invalidate('disconnect');service.connection=('http://127.0.0.1:2/v1/client','b'*64)
                commands=[receipt['command'] for receipt in service.receipts.values()]
                self.assertEqual([c['kind'] for c in commands],['guest-raster','controller-snapshot','controller-snapshot','cancelled'])
                self.assertTrue(all(r['connection']==original for r in service.receipts.values()))
                self.assertTrue(all('visible' not in c['observation'] for c in commands))
                self.assertEqual(commands[-1]['observation'],{'reason':'disconnect'})
            finally:service.close()

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

    def test_browser_queue_progress_requires_complete_ordered_guest_stream(self):
        _,records=fixture()
        script=r"""
import assert from 'node:assert/strict';
import {guestSchoolQueueState} from './sim/browser/school_transport.js';
const rows=JSON.parse(process.argv[1]),encode=x=>new TextEncoder().encode(x),observe=x=>guestSchoolQueueState(encode(x));
const initial=observe(rows[0]);assert.equal(initial.streamedBytes,'0');assert.equal(initial.streamComplete,false);
assert.equal(observe(rows.slice(0,2).join('')).streamedBytes,'16');
const prefix=rows.slice(0,-1).join('');assert.equal(observe(prefix).streamedBytes,'264');assert.equal(observe(prefix).streamComplete,false);
assert.equal(observe(prefix+rows.at(-1).slice(0,-1)).streamComplete,false,'partial terminal record is not complete');
const complete=rows.join('');assert.equal(observe(complete).streamComplete,true);
assert.equal(observe(complete+rows[0]).streamComplete,false,'old completion cannot complete a new stream');
assert.equal(observe(complete+rows[0]).streamedBytes,'0');
assert.equal(guestSchoolQueueState(encode(complete),complete.length),null);
assert.equal(observe(rows.at(-1)),null,'a suffix cannot invent its missing start');
for(const invalid of [rows[0]+rows[2]+rows[1],rows[0]+rows.at(-1),prefix+rows.at(-1).replace('0000000000000017','0000000000000018'),complete+rows[1]])assert.throws(()=>observe(invalid));
const failure='K1 0000000000000732 00000000000000f0 0000000000000000 0000000000000000 0000000000000000\n';
assert.equal(observe(complete+failure).state,'failed');assert.equal(observe(complete+failure+rows[0]).streamComplete,false);
"""
        result=subprocess.run(['node','--input-type=module','-e',script,json.dumps([r.decode() for r in records])],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

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
