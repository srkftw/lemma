// SPDX-License-Identifier: Apache-2.0
// Actual maintained worker scheduling with controlled async transport timing.
// No CPU, guest, OPFS or clock-boundary qualification is supplied by this test.
import fs from 'node:fs/promises';
import vm from 'node:vm';
import path from 'node:path';
import assert from 'node:assert/strict';
const timers=new Map();let id=0;
const context=vm.createContext({console,Uint8Array,ArrayBuffer,TextEncoder,TextDecoder,BigInt,
 performance,crypto:globalThis.crypto,onmessage:null,postMessage:m=>{throw Error(JSON.stringify(m));},
 setTimeout:f=>{const key=++id;timers.set(key,f);return key;},clearTimeout:key=>timers.delete(key)});
const root=path.resolve('sim/browser'),modules=new Map();
async function load(name){
 if(modules.has(name))return modules.get(name);
 let source;
 if(name.endsWith('/qemu-system-riscv64.js'))source='export default function(){throw Error("CPU is outside scheduler fixture");}';
 else source=await fs.readFile(name,'utf8');
 if(name===root+'/tci/runtime_worker.mjs')source+='\nexport {schedule,pause,enqueue}; export function configure(f,value){step=f;running=value;}';
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
