// Independent literal transport checks, not hardware or audibility evidence.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PcmEgress} from '../../sim/browser/tci/pcm_egress.mjs';
function fixture(rows){const b=new Uint8Array(8+24*rows.length);b.set(new TextEncoder().encode('LMPCM001'));const v=new DataView(b.buffer);rows.forEach(([tick,pos,sample],i)=>{v.setBigUint64(8+i*24,BigInt(tick),true);v.setBigUint64(16+i*24,BigInt(pos),true);v.setBigInt64(24+i*24,BigInt(sample),true);});return b;}
function fs(bytes,short=false){return {open:()=>1,close(){},read(_f,out,offset,count,position){out.set(bytes.subarray(position,position+count),offset);return short?count-1:count;}};}
const state=(overrides={})=>({state:'5',epoch:'2',consent:'1',consumed:'3',...overrides});
const data=fixture([[2000,1,-32768],[4000,2,32767],[6000,3,-123]]),events=[],egress=new PcmEgress();
egress.poll(fs(data),data.length,state(),m=>events.push(m));
assert.deepEqual(events.map(e=>e.type),['pcm-stop','pcm']);
assert.deepEqual(events[1].pcm.samples,[['2000','1',-32768],['4000','2',32767],['6000','3',-123]]);
egress.poll(fs(data),data.length,state(),m=>events.push(m));assert.equal(events.length,2,'stable cursor must not repeat emitted samples');
egress.poll(fs(data),data.length,state({state:'3',consent:'0'}),m=>events.push(m));assert.equal(events.at(-1).type,'pcm-stop');
const cancelled=new PcmEgress(),stopped=[];cancelled.poll(fs(data),data.length,state({state:'3'}),m=>stopped.push(m));assert.equal(cancelled.dropped,3);assert(!stopped.some(m=>m.type==='pcm'));
for(const bad of [fixture([[2000,1,32768]]),fixture([[2000,1,-32769]]),fixture([[2000,0,1]]),fixture([[2000,4,1]]),fixture([[2000,1,1],[2000,2,2]]),fixture([[2000,1,1],[4000,3,2]])])assert.throws(()=>new PcmEgress().poll(fs(bad),bad.length,state(),()=>{}));
for(const size of [0,7,9,67108865])assert.throws(()=>new PcmEgress().poll(fs(data),size,state(),()=>{}));
assert.throws(()=>new PcmEgress().poll(fs(data,true),data.length,state(),()=>{}),/header|Short/);
assert.throws(()=>new PcmEgress().poll(fs(data),data.length,state({consumed:3}),()=>{}),/Malformed actual/);
const reset=new PcmEgress();reset.discard(data.length);const retained=[];reset.poll(fs(data),data.length,state({consumed:'0',epoch:'1',consent:'0'}),m=>retained.push(m));assert.equal(reset.dropped,3);assert(!retained.some(m=>m.type==='pcm'));
if(process.argv[2]){const actual=new Uint8Array(readFileSync(process.argv[2])),out=[];const e=new PcmEgress();e.poll(fs(actual),actual.length,state({consumed:'1'}),m=>out.push(m));assert.deepEqual(out.find(m=>m.type==='pcm').pcm.samples.map(r=>r[2]),[32767]);console.log(JSON.stringify({result:'PASS_ACTUAL_CONTROLLER_FILE_DECODE',bytes:actual.length,records:e.rows,samples:out.find(m=>m.type==='pcm').pcm.samples}));}
console.log('PASS literal PCM signedness, ordering, bounds, cancellation and no-repeat controls');
