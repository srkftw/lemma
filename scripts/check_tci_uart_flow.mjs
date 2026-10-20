#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Actual TCI execution of versioned UART backpressure, separate from UI work.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {Control} from '../sim/browser/tci/control.mjs';
import {attachOpfsFile} from '../sim/browser/tci/opfs_backing.mjs';

const [runtime,guest,dtb,directory]=process.argv.slice(2).map(p=>path.resolve(p));
if(!directory||fs.existsSync(directory))throw Error('Four paths and unused output required');
fs.mkdirSync(directory,{recursive:true});
const sha=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const start=performance.now(),report={schema:'lemma-tci-uart-flow-boundaries/1',result:'FAIL',
 scope:'Actual QEMU/Wasm16550 full-FIFO, readiness, receive-reset and cancellation execution with maintained Lean guest. No browser UI, school workflow, RTL timing or physical throughput claim.',
 limits:{wholeSeconds:180,requestSeconds:20},cases:{},
 inputs:Object.fromEntries([path.resolve(process.argv[1]),guest,dtb,path.join(runtime,'runtime.json'),path.join(runtime,'qemu-system-riscv64.js'),path.join(runtime,'qemu-system-riscv64.wasm'),path.resolve('sim/browser/tci/control.mjs'),path.resolve('sim/browser/tci/opfs_backing.mjs')].map(p=>[p,sha(p)]))};
let core,backing;const logs=[];
const whole=setTimeout(()=>finish(Error('Original180s whole deadline')),180000);
function finish(error){
 clearTimeout(whole);if(error)report.error=String(error);
 report.elapsedSeconds=(performance.now()-start)/1000;report.peakRssBytes=process.resourceUsage().maxRSS*1024;
 report.logs=logs;report.backing=backing?.metrics;
 fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(report,null,2)+'\n');process.exit(error?1:0);
}
function require(v,text){if(!v)throw Error(text);}
// Flow selection is intentionally reset-only and also rejects historical raw
// admission. Each comparison therefore needs a fresh machine, as native does.
// Sequential child processes release the2GiB Wasm memory before the next case.
if(!process.argv[6]){
 try{
  for(const mode of ['legacy','flow']){
   const childDirectory=path.join(directory,mode);
   const child=spawnSync(process.execPath,[path.resolve(process.argv[1]),runtime,guest,dtb,childDirectory,mode],
    {timeout:Math.max(1,Math.floor(180000-(performance.now()-start))),killSignal:'SIGKILL',encoding:'utf8'});
   fs.writeFileSync(path.join(directory,mode+'.log'),(child.stdout??'')+(child.stderr??''));
   const result=path.join(childDirectory,'result.json');
   if(fs.existsSync(result)){const data=JSON.parse(fs.readFileSync(result));report.cases[mode]=data;}
   require(!child.error&&child.status===0,'Actual '+mode+' execution failed: '+String(child.error??child.status));
  }
  report.ownedProcessesReaped=true;report.result='PASS';finish();
 }catch(error){report.ownedProcessesReaped=true;finish(error);}
}
try{
 const {default:createQemu}=await import(pathToFileURL(path.join(runtime,'qemu-system-riscv64.js')));
 const pages=new Map(),capacity=268435456;
 const handle={getSize:()=>capacity,read:(bytes,{at})=>{bytes.fill(0);for(let i=0;i<bytes.length;){const page=Math.floor((at+i)/4096),within=(at+i)%4096,n=Math.min(4096-within,bytes.length-i),data=pages.get(page);if(data)bytes.set(data.subarray(within,within+n),i);i+=n;}return bytes.length;},write:(bytes,{at})=>{for(let i=0;i<bytes.length;){const page=Math.floor((at+i)/4096),within=(at+i)%4096,n=Math.min(4096-within,bytes.length-i);let data=pages.get(page);if(!data){data=new Uint8Array(4096);pages.set(page,data);}data.set(bytes.subarray(i,i+n),within);i+=n;}return bytes.length;},flush:()=>{}};
 core=await createQemu({arguments:['-machine','lemma-silicon-fast','-cpu','rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0','-m','128M','-smp','1','-bios','none','-kernel','/image.elf','-dtb','/machine.dtb','-display','none','-monitor','none','-serial','file:/uart.bin','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-global','lemma-fast-block.medium=/medium.raw'],preRun:[m=>{m.FS.writeFile('/image.elf',fs.readFileSync(guest));m.FS.writeFile('/machine.dtb',fs.readFileSync(dtb));backing=attachOpfsFile(m,'/medium.raw',handle);}],print:x=>{if(logs.length<64)logs.push(String(x));},printErr:x=>{if(logs.length<64)logs.push(String(x));},onAbort:x=>finish(Error('Actual QEMU abort:'+x))});
 const c=new Control(core,20000);await c.ready();
 const get=p=>c.get(p),put=(p,v)=>c.set(p,v),state=async()=>JSON.parse(await get('raw-uart-state'));
 const run=async until=>{await put('run-until',String(until));await c.request('cont');while((await c.request('query-status')).running){if(performance.now()-start>180000)throw Error('Original whole deadline');await new Promise(r=>setTimeout(r,2));}};
 require(await get('raw-uart-flow-version')==='lemma-raw-uart-flow/1','Actual versioned flow property absent');
 await put('enable-raw-uart','lemma-raw-uart/1');
 for(const flow of [process.argv[6]==='flow']){
  await c.request('system_reset');
  if(flow)await put('enable-raw-uart-flow','lemma-raw-uart-flow/1');
  const initial=await state();require(initial.flow===flow,'Flow selection identity');
  let now=BigInt(await get('virtual-time'));
  await put('external-uart-paced',`${now} 10 ${'00'.repeat(64)}`);
  await run(now+4000n);const full=await state();
  require(full.pending>0&&full.serial_can_receive===0,'Actual UART not full');
  require(full.blocked===flow&&full.timer_pending!==flow,'Full FIFO backpressure boundary');
  const observed=JSON.parse(await get('execution-state'));
  require(JSON.stringify(full)===JSON.stringify(await state())&&JSON.stringify(observed)===JSON.stringify(JSON.parse(await get('execution-state'))),'Read-only observation mutated state');
  await put('external-uart-paced',`${now+5000n} 1000 aabb`);
  await run(now+8000n);const blocked=await state();
  require(blocked.delivered===full.delivered,'Full UART accepted byte');
  require(flow?blocked.poll_calls===full.poll_calls:blocked.poll_calls>full.poll_calls+100,'Flow/legacy polling distinction');
  await c.request('system_reset');const reset=await state();
  require(reset.pending===0&&!reset.blocked&&!reset.timer_pending&&reset.flow===flow,'Reset cancellation/identity');
  require(reset.canceled-initial.canceled===full.pending+2,'Reset loss accounting');
  now=BigInt(await get('virtual-time'));const due=now+1000n;
  await put('external-uart-paced',`${due} 100000 ${'00'.repeat(32)}`);
  await run(due-16n);const early=await state();require(early.delivered===reset.delivered,'Early byte delivery');
  await run(due+12n);const first=await state();require(first.delivered===reset.delivered+1,'Exact first due delivery');
  // Normal maintained initialization frees RBR/FCR. Advance actual execution,
  // never write the guest receiver or manufacture a readiness callback.
  if(flow)await run(now+4000000000n);
  const received=await state();
  if(flow)require(received.delivered>first.delivered&&received.wakeups>0,'Actual guest receive/FCR readiness did not resume bytes');
  report.cases[flow?'flow':'legacy']={initial,full,blocked,reset,early,first,received,executionObserver:observed};
 }
 if(report.cases.flow)require(report.cases.flow.full.poll_calls-report.cases.flow.initial.poll_calls<10,'Flow retry storm');
 report.clock=await c.request('lemma-clock');report.result='PASS';finish();
}catch(error){finish(error);}
