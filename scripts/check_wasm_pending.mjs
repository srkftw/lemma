// SPDX-License-Identifier: Apache-2.0
// Host-only qualification of real RV64 guest I/O in the portable RTL Machine.
// The external adapter handles opaque bytes; the initializer runs in the guest.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const [bundleArg,outArg]=process.argv.slice(2);
if(!bundleArg||!outArg)throw Error('usage: node scripts/check_wasm_pending.mjs BROWSER_BUNDLE UNUSED_OUTPUT');
const bundle=path.resolve(bundleArg),out=path.resolve(outArg),start=performance.now();
fs.mkdirSync(out,{recursive:false});
const CAPACITY=268435456,MAX_CYCLES=30000000n,MAX_HOST_SECONDS=600;
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const observerSha256=sha(fs.readFileSync(new URL(import.meta.url)));
const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'bundle.json')));
assert.equal(manifest.schema,'lemmasim-browser-bundle/1');
assert.equal(manifest.profile,'lemma-silicon-dev/0.3.0');
for(const [name,digest]of Object.entries(manifest.files)){
 if(path.isAbsolute(name)||name.split('/').includes('..'))throw Error('Invalid bundle path');
 assert.equal(sha(fs.readFileSync(path.join(bundle,name))),digest,'changed bundle artifact: '+name);
}
const build=JSON.parse(fs.readFileSync(path.join(bundle,'wasm-build.json')));
assert.equal(build.status,'BUILT');
assert.equal(sha(fs.readFileSync(path.join(bundle,'wasm-build.json'))),manifest.wasm_build_sha256);
const mediumPath=path.join(out,'original.raw'),privatePath=path.join(out,'private.raw');
let originalFd=fs.openSync(mediumPath,'wx+'),privateFd;
fs.ftruncateSync(originalFd,CAPACITY);fs.fsyncSync(originalFd);
let core,pending,held=false,released=false,firstWrite,originalCalls={reads:0,writes:0,flushes:0,submits:0,polls:0};
function bounded(offset,n){assert(Number.isSafeInteger(offset)&&Number.isSafeInteger(n)&&offset>=0&&n>=0&&offset+n<=CAPACITY);}
function local(fd,counters){return {
 getSize:()=>fs.fstatSync(fd).size,
 read(p,{at}){bounded(at,p.length);if(counters)counters.reads++;return fs.readSync(fd,p,0,p.length,at);},
 write(p,{at}){bounded(at,p.length);if(counters)counters.writes++;return fs.writeSync(fd,p,0,p.length,at);},
 flush(){if(counters)counters.flushes++;fs.fsyncSync(fd);}
};}
const live=local(originalFd,originalCalls);
live.submit=(request,bytes)=>{
 assert(!pending);assert.match(request.id,/^[1-9][0-9]*$/);assert.match(request.boundary,/^[0-9]+$/);
 bounded(request.offset,request.length);assert(request.length<=1048576);
 assert([0,1,2].includes(request.kind));
 assert.equal(bytes.length,request.kind===1?request.length:0);
 originalCalls.submits++;pending={request,bytes:bytes.slice()};
 if(request.kind===1&&!firstWrite){firstWrite={...request};held=true;}
};
live.poll=()=>{
 originalCalls.polls++;assert(pending);
 if(held&&!released)return null;
 const {request:r,bytes}=pending;pending=null;let result;
 if(r.kind===2){live.flush();result={transferred:0,error:0,bytes:new Uint8Array()};}
 else if(r.kind===0){const b=new Uint8Array(r.length),n=live.read(b,{at:r.offset});result={transferred:n,error:n===r.length?0:5,bytes:b.slice(0,n)};}
 else{const n=live.write(bytes,{at:r.offset});result={transferred:n,error:n===r.length?0:5,bytes:bytes.slice(0,n)};}
 return result;
};
function check(name,types=[],args=[]){const status=core.ccall(name,'number',types,args);if(status)throw Error(core.ccall('lemma_error','string',[],[]));}
function state(){return JSON.parse(core.ccall('lemma_inspect','string',[],[]).replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(s,n)=>n===undefined?s:JSON.stringify(n)));}
function hostBound(){if((performance.now()-start)/1000>MAX_HOST_SECONDS)throw Error('predeclared 600s host deadline exceeded');}
let nextProgress=1000000n;
function run(n=10000){hostBound();assert(BigInt(state().cycle)+BigInt(n)<=MAX_CYCLES,'predeclared 30M guest cycle bound');
 check('lemma_run',['number'],[n]);const s=state();
 if(BigInt(s.cycle)>=nextProgress){console.log(JSON.stringify({cycle:s.cycle,retired:s.retired,backing:s.backing_io,hostSeconds:(performance.now()-start)/1000}));nextProgress=BigInt(s.cycle)+1000000n;}}
function copyMemfs(source,destination){const stream=core.FS.open(source,'r'),fd=fs.openSync(destination,'wx'),size=core.FS.stat(source).size;
 try{const chunk=new Uint8Array(1048576);for(let i=0;i<size;i+=chunk.length){const n=Math.min(chunk.length,size-i);assert.equal(core.FS.read(stream,chunk,0,n,i),n);assert.equal(fs.writeSync(fd,chunk,0,n,i),n);}fs.fsyncSync(fd);}
 finally{core.FS.close(stream);fs.closeSync(fd);core.FS.unlink(source);}return size;
}
function checkpoint(name){check('lemma_snapshot',['string'],['/'+name]);return copyMemfs('/'+name,path.join(out,name));}
function initAck(){return /K1 000000000000041f 0000000000000000 0000000000000000 0000000000000000(?:\r?\n|$)/.test(new TextDecoder().decode(core.FS.readFile('/uart.bin')));}
const receipt={status:'FAIL',scope:'actual RV64 initializer WRITE Pending, observational snapshot, private byte backing and captured applicable same-Wasm suffix',
 limits:{guest_cycles:String(MAX_CYCLES),host_seconds:MAX_HOST_SECONDS},
 identities:{bundle:sha(fs.readFileSync(path.join(bundle,'bundle.json'))),wasm:build.outputs['machine.wasm'],runtime:build.snapshot_identity,guest:manifest.workloads.initializer.image.sha256},
 excluded:['canonical notebook Ready','browser OPFS acceptance','cross-backend microstate migration','USB or radio conformance','product ROM boot/update']};
try{
 const {default:createMachine}=await import(pathToFileURL(path.join(bundle,'machine.mjs')));
 core=await createMachine();core.backing=live;core.FS.mkdir('/forks');
 for(const [target,item]of [['/image.elf',manifest.workloads.initializer.image],['/machine.dtb',manifest.workloads.initializer.dtb],['/descriptor.bin',manifest.workloads.initializer.descriptor],['/boot.bin',manifest.rom]])
  core.FS.writeFile(target,fs.readFileSync(path.join(bundle,item.path)));
 check('lemma_create');
 while(!held)run();
 assert.equal(state().backing_io.phase,'1');assert.equal(initAck(),false);
 const before=state(),callsBefore={...originalCalls},pendingStart=performance.now();
 receipt.pendingSnapshotBytes=checkpoint('pending.bin');
 assert.deepEqual(state(),before);assert.deepEqual(originalCalls,callsBefore);
 receipt.pendingSnapshotSeconds=(performance.now()-pendingStart)/1000;
 receipt.pendingCycle=before.cycle;receipt.pendingRequest=firstWrite;
 released=true;
 while(!initAck())run();
 run(20000);const final=state(),uart=core.FS.readFile('/uart.bin');
 assert(BigInt(final.backing_io.durable_barrier)>0n);assert.equal(final.backing_io.phase,'2');
 receipt.finalSnapshotBytes=checkpoint('original.bin');
 fs.writeFileSync(path.join(out,'original-uart.bin'),uart);
 const capture=core.ccall('lemma_capture_path','string',[],[]);
 core.FS.writeFile('/suffix.io',core.FS.readFile(capture));
 fs.writeFileSync(path.join(out,'backing.io'),core.FS.readFile(capture));
 receipt.originalFinal=final;receipt.originalCalls={...originalCalls};receipt.ackHostSeconds=(performance.now()-start)/1000;
 core.FS.writeFile('/pending.bin',fs.readFileSync(path.join(out,'pending.bin')));
 check('lemma_restore',['string'],['/pending.bin']);core.FS.unlink('/pending.bin');
 const suspended=state();assert.equal(suspended.backing_io.fork_suspended,true);
 assert.notEqual(core.ccall('lemma_run','number',['number'],[1]),0);assert.deepEqual(state(),suspended);
 check('lemma_export_private',['string'],['/private.raw']);
 assert.deepEqual(state(),suspended);assert.deepEqual(originalCalls,receipt.originalCalls);
 copyMemfs('/private.raw',privatePath);privateFd=fs.openSync(privatePath,'r+');
 core.backing=local(privateFd);check('lemma_rebind_private');
 assert.deepEqual(state(),suspended);assert.deepEqual(originalCalls,receipt.originalCalls);
 fs.closeSync(originalFd);originalFd=undefined;fs.unlinkSync(mediumPath);
 const replayStart=performance.now();check('lemma_backing_outcomes',['string'],['/suffix.io']);core.FS.unlink('/suffix.io');
 const remaining=BigInt(final.cycle)-BigInt(state().cycle);
 assert(remaining>0n);let left=remaining;
 while(left){const n=Number(left>100000n?100000n:left);run(n);left-=BigInt(n);}
 assert.equal(initAck(),true);assert.deepEqual(originalCalls,receipt.originalCalls);
 receipt.replaySnapshotBytes=checkpoint('fork.bin');
 const original=fs.readFileSync(path.join(out,'original.bin')),fork=fs.readFileSync(path.join(out,'fork.bin'));
 assert.deepEqual(fork,original,'authoritative wrapper and generated RTL state exact applicable suffix');
 assert.deepEqual(core.FS.readFile('/uart.bin'),uart,'exact actual guest UART suffix');
 receipt.checkpointSha256=sha(original);receipt.replaySeconds=(performance.now()-replayStart)/1000;
 receipt.replayFinal=state();receipt.wasmHeapBytes=core.HEAPU8.byteLength;receipt.status='PASS';
}catch(e){receipt.error=String(e);process.exitCode=1;
 if(core){receipt.failedState=state();try{receipt.failedSnapshotBytes=checkpoint('failed-boundary.bin');}catch(snapshotError){receipt.failedSnapshotError=String(snapshotError);}}}
finally{
 core?.ccall('lemma_destroy',null,[],[]);
 if(originalFd!==undefined)fs.closeSync(originalFd);if(privateFd!==undefined)fs.closeSync(privateFd);
 receipt.hostSeconds=(performance.now()-start)/1000;receipt.hostPeakRssBytes=process.resourceUsage().maxRSS*1024;
 receipt.observerSha256=observerSha256;
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));
}
