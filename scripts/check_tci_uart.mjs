#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Actual QEMU/Wasm external UART boundary checks. Host bytes and observation
// only; this establishes neither browser UI nor ordinary notebook workflows.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {Control} from '../sim/browser/tci/control.mjs';
import {attachOpfsFile} from '../sim/browser/tci/opfs_backing.mjs';
import {admitUart} from '../sim/browser/tci/uart_arrivals.mjs';
const [runtime,guest,dtb,directory]=process.argv.slice(2).map(p=>path.resolve(p));
if(!directory||fs.existsSync(directory))throw Error('Four paths and unused output required');fs.mkdirSync(directory,{recursive:true});
const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const start=performance.now(),report={schema:'lemma-tci-paced-uart-execution/1',result:'FAIL',scope:'Actual Wasm64 QEMU16550/timer/admission execution; no browser UI, notebook, timing parity or physical UART qualification.',limits:{wholeSeconds:120,requestSeconds:20},cases:[],inputs:Object.fromEntries([path.resolve(process.argv[1]),guest,dtb,path.join(runtime,'runtime.json'),path.join(runtime,'qemu-system-riscv64.js'),path.join(runtime,'qemu-system-riscv64.wasm'),path.resolve('sim/browser/tci/control.mjs'),path.resolve('sim/browser/tci/opfs_backing.mjs'),path.resolve('sim/browser/tci/uart_arrivals.mjs')].map(p=>[p,sha(p)]))};
let core,backing;const logs=[];
const whole=setTimeout(()=>finish(Error('Original120s whole deadline')),120000);
function finish(error){
 clearTimeout(whole);if(error)report.error=String(error);report.elapsedSeconds=(performance.now()-start)/1000;report.peakRssBytes=process.resourceUsage().maxRSS*1024;report.logs=logs;report.backing=backing?.metrics;fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(report,null,2)+'\n');process.exit(error?1:0);
}
try{
 const {default:createQemu}=await import(pathToFileURL(path.join(runtime,'qemu-system-riscv64.js')));
 const pages=new Map(),capacity=268435456;
 const handle={getSize:()=>capacity,read:(bytes,{at})=>{bytes.fill(0);for(let i=0;i<bytes.length;){const page=Math.floor((at+i)/4096),within=(at+i)%4096,n=Math.min(4096-within,bytes.length-i),data=pages.get(page);if(data)bytes.set(data.subarray(within,within+n),i);i+=n;}return bytes.length;},write:(bytes,{at})=>{for(let i=0;i<bytes.length;){const page=Math.floor((at+i)/4096),within=(at+i)%4096,n=Math.min(4096-within,bytes.length-i);let data=pages.get(page);if(!data){data=new Uint8Array(4096);pages.set(page,data);}data.set(bytes.subarray(i,i+n),within);i+=n;}return bytes.length;},flush:()=>{}};
 core=await createQemu({arguments:['-machine','lemma-silicon-fast','-cpu','rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0','-m','128M','-smp','1','-bios','none','-kernel','/image.elf','-dtb','/machine.dtb','-display','none','-monitor','none','-serial','file:/uart.bin','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-global','lemma-fast-block.medium=/medium.raw'],preRun:[m=>{m.FS.writeFile('/image.elf',fs.readFileSync(guest));m.FS.writeFile('/machine.dtb',fs.readFileSync(dtb));backing=attachOpfsFile(m,'/medium.raw',handle);}],print:x=>{if(logs.length<64)logs.push(String(x));},printErr:x=>{if(logs.length<64)logs.push(String(x));},onAbort:x=>finish(Error('Actual QEMU abort:'+x))});
 const c=new Control(core,20000);await c.ready();const get=p=>c.get(p),put=(p,v)=>c.set(p,v),state=async()=>JSON.parse(await get('raw-uart-state'));
 if(await get('raw-uart-paced-version')!=='lemma-raw-uart-paced/1')throw Error('Actual paced property absent');
 const reject=async(label,value)=>{const before=JSON.stringify(await state());let rejected=false;try{await put('external-uart-paced',value);}catch{rejected=true;}if(!rejected||JSON.stringify(await state())!==before)throw Error('Transactional rejection failed:'+label);report.cases.push(label);};
 await reject('disabled-port','100000 100000 aa');await put('enable-raw-uart','lemma-raw-uart/1');
 for(const [label,value] of [['empty','100000 100000 '],['oddhex','100000 100000 a'],['nonhex','100000 100000 xx'],['zero-interval','100000 0 aa'],['negative-interval','100000 -1 aa'],['overflow-last','9223372036854775797 1 aabb']])await reject(label,value);
 report.admission=await admitUart(c,Uint8Array.from({length:12},(_,i)=>i+1),100000n,true);const before=await state();if(before.pending!==12||before.first_due_ns!==100000)throw Error('Per-byte queue differs');
 await put('run-until','100003');await c.request('cont');const end=performance.now()+20000;while((await c.request('query-status')).running){if(performance.now()>end)throw Error('Actual timer stop deadline');await new Promise(r=>setTimeout(r,2));}
 const after=await state();if(after.delivered!==1||after.pending!==11||after.first_due_ns!==200000)throw Error('Actual first16550 arrival differs');report.firstArrival=after;report.clock=await c.request('lemma-clock');report.cases.push('real16550-first-arrival');
 await reject('stale-arrival','0 100000 aa');await c.request('system_reset');const reset=await state();if(reset.pending!==0||reset.canceled!==11)throw Error('Reset retained pending bytes');report.cases.push('reset-cancels-pending');
 const now=BigInt(await get('virtual-time')),base=now+1000000n;for(let i=0;i<64;i++)await put('external-uart-paced',`${base+BigInt(i*1024)*100000n} 100000 ${'ab'.repeat(1024)}`);
 if((await state()).pending!==65536)throw Error('Full queue extent differs');await reject('full65536-byte-queue',`${base} 100000 00`);report.finalState=await state();report.wasmHeapBytes=report.clock.wasm_heap_bytes;report.result='PASS';finish();
}catch(error){finish(error);}
