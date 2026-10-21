// SPDX-License-Identifier: Apache-2.0
// Actual maintained worker scheduling with controlled async transport timing.
// No CPU, guest, OPFS or clock-boundary qualification is supplied by this test.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import path from 'node:path';
import assert from 'node:assert/strict';
const timers=new Map(),messages=[];let id=0;
const context=vm.createContext({console,Uint8Array,ArrayBuffer,TextEncoder,TextDecoder,BigInt,
 performance,crypto:globalThis.crypto,onmessage:null,postMessage:m=>messages.push(m),
 setTimeout:f=>{const key=++id;timers.set(key,f);return key;},clearTimeout:key=>timers.delete(key)});
const root=path.resolve('sim/browser'),modules=new Map();
async function load(name){
 if(modules.has(name))return modules.get(name);
 let source;
 if(name.endsWith('/qemu-system-riscv64.js'))source='export default function(){throw Error("CPU is outside scheduler fixture");}';
 else source=await fs.readFile(name,'utf8');
 if(name===root+'/tci/runtime_worker.mjs')source+='\nexport {schedule,pause,enqueue,raw,queueOpticalSource}; export function configure(f,value){step=f;running=value;} export function configureOptical(c,t){control=c;opticalTransport=t;capture=[];stopContract=null;} export function captured(){return capture.slice();}';
 const mod=new vm.SourceTextModule(source,{context,identifier:name});modules.set(name,mod);
 await mod.link(async(spec,parent)=>{let p=path.resolve(path.dirname(parent.identifier),spec);try{await fs.access(p);}catch{if(!spec.endsWith('qemu-system-riscv64.js'))p=path.resolve(root,spec);}return load(p);});return mod;
}
const mod=await load(root+'/tci/runtime_worker.mjs');await mod.evaluate();const worker=mod.namespace;
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const settle=async()=>{for(let i=0;i<24;i++)await Promise.resolve();};
const fire=()=>{assert.equal(timers.size,1,'one pending scheduled turn');const [key,f]=timers.entries().next().value;timers.delete(key);f();};
const first=deferred(),second=deferred(),input=deferred();let steps=0;
worker.configure(async()=>{const n=++steps;assert(n<=2,'a duplicate step escaped the cancelled budget');await (n===1?first:second).promise;worker.schedule();},true);
worker.schedule();worker.schedule();assert.equal(timers.size,1);fire();await settle();assert.equal(steps,1);
// Pointer input owns the serial queue while awaiting the real QMP stop and
// controller admission. The next timer can fire during that await, so one
// step is already queued when input calls schedule(). Do not queue a second.
const admission=worker.enqueue(async()=>{await input.promise;worker.configure(async()=>{const n=++steps;assert.equal(n,2);await second.promise;worker.schedule();},true);worker.schedule();});
first.resolve();await settle();fire();await settle();assert.equal(steps,1);
input.resolve();await admission;await settle();assert.equal(steps,2);
assert.equal(timers.size,0,'input completion duplicated an already queued execution step');
second.resolve();await settle();assert.equal(timers.size,1,'completion schedules exactly one successor');
worker.pause('user');assert.equal(timers.size,0,'pause cancels the successor');
await settle();assert.equal(steps,2);
console.log('PASS actual TCI scheduler: pointer transport over a queued step, one successor, pause cancellation');

// The real full-frame transport uses at most1024 rows per atomic source QOM
// admission. A later failure retains exactly the earlier acknowledged batches;
// no simulated CPU, DMA completion or ready result is invented by this fixture.
const opticalModule=await load(root+'/optical_transport.js');await opticalModule.evaluate();
const optical=opticalModule.namespace;
let requests=[],admitted=[],failBatch=null;
const fakeControl={
 async stopped(){requests.push(['stopped']);},
 async request(name){assert.equal(name,'lemma-clock');requests.push([name]);return {virtual_ns:'90071992547409930',mtime_ticks:'9007199254740993'};},
 async set(name,wire){
  const rows=wire.split('\n');requests.push([name,rows.length]);
  assert.equal(name,'optical-source-batch');assert(wire.length<=65536);assert(rows.length<=1024);
  if(failBatch!==null&&requests.filter(r=>r[0]===name).length===failBatch)throw Error('actual property rejection fixture');
  for(const row of rows){const f=row.split(' ');assert.equal(f.length,5);assert.equal(f[2],f[1]==='1'?'18446744073709551615':'0');}
  admitted.push(...rows);
 }
};
const face=new Uint8Array(76800);face.fill(255);
worker.configureOptical(fakeControl,optical);
await worker.queueOpticalSource({endpoint:'3',bytes:face.buffer});
assert.equal(requests.filter(r=>r[0]==='stopped').length,1);assert.equal(requests.filter(r=>r[0]==='lemma-clock').length,1);
assert.equal(requests.filter(r=>r[0]==='optical-source-batch').length,10);assert.equal(admitted.length,9602);
assert.equal(worker.captured().length,9602);assert.equal(worker.captured()[1],'9007199254740993 optical-frame 3 1 18446744073709551615 8 0');
assert.equal(messages.at(-1).accepted,9602);assert.equal(messages.at(-1).error,null);
requests=[];admitted=[];failBatch=2;worker.configureOptical(fakeControl,optical);
await assert.rejects(worker.queueOpticalSource({endpoint:'3',bytes:face.buffer}),/property rejection/);
assert.equal(admitted.length,1024);assert.equal(worker.captured().length,1024);
assert.equal(messages.at(-1).accepted,1024);assert.equal(messages.at(-1).total,9602);assert.match(messages.at(-1).error,/prefix retained/);
const before=requests.length;
context.onmessage({data:{action:'optical-frame',endpoint:'3',bytes:face.buffer}});
assert.equal(requests.length,before);assert.match(messages.at(-1).error,/session capability/);
console.log('PASS actual TCI optical queue: full76800B, ten atomic batches, u64 precision, rejected suffix, Student denial');
