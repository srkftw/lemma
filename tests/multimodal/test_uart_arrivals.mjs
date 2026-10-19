// Host-stimulus framing checks; not actual QEMU or guest execution evidence.
import assert from 'node:assert/strict';
import {admitUart} from '../../sim/browser/tci/uart_arrivals.mjs';
const frame=new Uint8Array(4263);for(let i=0;i<frame.length;i++)frame[i]=i&255;
const rows=[];const control={set:async(property,value)=>rows.push({property,value})};
const receipt=await admitUart(control,frame,1000n,true);
assert.equal(receipt.requests,5);assert.equal(receipt.bytesPerSecond,10000);
let offset=0;for(const row of rows){const [when,interval,hex]=row.value.split(' ');assert.equal(row.property,'external-uart-paced');assert.equal(BigInt(when),1000n+BigInt(offset)*100000n);assert.equal(interval,'100000');assert.equal(hex,Buffer.from(frame.subarray(offset,offset+1024)).toString('hex'));offset+=hex.length/2;}assert.equal(offset,4263);
rows.length=0;await admitUart(control,frame.subarray(0,19),1000n,false);assert.equal(rows.length,19);assert.equal(rows[18].value,'1801000 12');
for(const args of [[new Uint8Array(),0n,true],[frame,-1n,true],[frame,9223372036854775797n,true],[frame,0n,1]]){rows.length=0;await assert.rejects(admitUart(control,...args));assert.equal(rows.length,0);}
console.log('PASS actual per-byte arrival framing, bounded batching, legacy schedule and prevalidation');
