// SPDX-License-Identifier: Apache-2.0
// Actual worker module, fake machine/storage boundaries. This is a host
// protocol fixture; it neither executes RV64 nor qualifies Wasm performance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const encoder=new TextEncoder(),decoder=new TextDecoder();
const MAX=18446744073709551615n;
const record=(kind,sequence=0n)=>`K1 ${kind.toString(16).padStart(16,'0')} ${sequence.toString(16).padStart(16,'0')} 0000000000000001 0000000000000001 0000000000000000\n`;
async function fixture({cycle=9007199254740993n,initialUART='',initialize=false,onRun}={}){
 let now=0,nextTimer=0,generation=0,finished=false,current=cycle,paper={completed:'0',accepted:'0'},uart=initialUART;
 const files=new Map([['/capture.io',encoder.encode('literal captured outcome bytes')]]),messages=[],timers=new Map(),calls=[],events=[];
 const bytes=encoder.encode('hash-validated fake ELF/descriptor/ROM');
 const digest=Buffer.from(await webcrypto.subtle.digest('SHA-256',bytes)).toString('hex');
 const item={path:'artifact.bin',sha256:digest},manifest={schema:'lemmasim-browser-bundle/1',width:1,height:1,rom:item,workloads:{notebook:{image:item,dtb:item,descriptor:item},initializer:{image:item,dtb:item,descriptor:item}}};
 const medium={read(b){now+=2;return b.length;},write(b){now+=3;return b.length;},flush(){now+=4;},getSize(){return 268435456;},close(){},truncate(){}};
 const mediumNames=new Set(initialize?[]:['test.raw']);
 const root={async getFileHandle(name,options={}){if(!mediumNames.has(name)&&!options.create){const e=Error('missing');e.name='NotFoundError';throw e;}mediumNames.add(name);return {async createSyncAccessHandle(){return medium;}};}};
 const core={HEAPU8:new Uint8Array(16),FS:{mkdir(){},writeFile(p,b){files.set(p,new Uint8Array(b));},readFile(p){if(p==='/uart.bin')return encoder.encode(uart);if(!files.has(p))throw Error('missing '+p);return new Uint8Array(files.get(p));},unlink(p){files.delete(p);},stat(){return {size:268435456};},open(){return {};},read(_stream,_chunk,_offset,length){return length;},close(){}},
 ccall(name,_return,_types,args=[]){calls.push([name,...args]);switch(name){
  case 'lemma_create':case 'lemma_create_mode':current=generation++===0?cycle:0n;finished=false;return 0;
  case 'lemma_destroy':return undefined;
  case 'lemma_inspect':return `{"cycle":${current},"ticks":${current},"panel_completed":${paper.completed},"finished":${finished}}`;
  case 'lemma_paper_inspect':return JSON.stringify(paper);
  case 'lemma_run':{const n=BigInt(args[0]);assert(n>0n&&n<=50000n);current+=n;now+=5;core.backing.read(new Uint8Array(1),{at:0});return onRun?.({n,current,generation,setUART:x=>{uart=x;},setPaper:x=>{paper=x;},setCycle:x=>{current=x;},finish:()=>{finished=true;}})??0;}
  case 'lemma_event':events.push(args[0]);return 0;
  case 'lemma_pixels':return 0;
  case 'lemma_pixel_count':return 1;
  case 'lemma_capture_path':return '/capture.io';
  case 'lemma_snapshot':files.set(args[0],encoder.encode(String(current)));return 0;
  case 'lemma_restore':current=BigInt(decoder.decode(files.get(args[0])));return 0;
  case 'lemma_export':case 'lemma_export_private':files.set(args[0],encoder.encode('opaque'));return 0;
  case 'lemma_rebind_private':case 'lemma_backing_outcomes':return 0;
  case 'lemma_reset':current=0n;return 0;
  case 'lemma_error':return 'fake machine error';
  default:throw Error('unimplemented fixture call '+name);
 }} };
 const context=vm.createContext({Uint8Array,ArrayBuffer,TextEncoder,TextDecoder,BigInt,console,crypto:webcrypto,
  performance:{now:()=>now},navigator:{storage:{getDirectory:async()=>root}},
  fetch:async path=>path==='./bundle.json'?{json:async()=>manifest}:{ok:true,arrayBuffer:async()=>bytes.buffer},
  postMessage:m=>messages.push(m),setTimeout:f=>{const id=++nextTimer;timers.set(id,f);return id;},clearTimeout:id=>timers.delete(id)});
 const modules=new Map();
 async function module(name){if(modules.has(name))return modules.get(name);const code=name==='machine.mjs'?'export default globalThis.fakeCreateMachine;':await fs.readFile('sim/browser/'+name,'utf8');
  const m=new vm.SourceTextModule(code,{context,identifier:name});modules.set(name,m);await m.link(spec=>module(spec.replace('./','')));return m;}
 context.fakeCreateMachine=async()=>core;
 const worker=await module('worker.js');await worker.evaluate();
 const send=async(action,rest={})=>{await context.onmessage({data:{action,...rest}});await settle();};
 async function settle(){for(let i=0;i<4;i++)await new Promise(resolve=>setTimeout(resolve,1));}
 async function tick(){const first=timers.entries().next().value;assert(first,'worker failed to schedule');timers.delete(first[0]);first[1]();await settle();}
 async function drain(){for(let i=0;timers.size&&i<30;i++)await tick();assert.equal(timers.size,0,'fixture run did not pause');}
 const state=()=>messages.filter(m=>m.type==='state').at(-1),exports=()=>messages.filter(m=>m.type==='export');
 await send('open',{name:'test',initialize});await send('pause');
 return {send,tick,drain,state,exports,messages,timers,calls,events,cycle:()=>current,advanceWall:n=>{now+=n;},setUART:x=>{uart=x;},setPaper:x=>{paper=x;}};
}

// UInt64 values above Number precision, exact tail, and worker cancellation.
{
 const f=await fixture(),origin=f.cycle();await f.send('run',{cycles:'100001'});await f.drain();
 assert.equal(f.cycle(),origin+100001n,JSON.stringify(f.messages.filter(m=>m.type==='error')));assert.equal(f.state().state.cycle,String(origin+100001n));
 assert.equal(f.state().pauseReason,'cycle-limit');assert.equal(f.state().budget.used,'100001');assert.equal(f.state().budget.remaining,'0');
 assert.deepEqual(f.calls.filter(x=>x[0]==='lemma_run').map(x=>x[1]),[50000,50000,1]);
 assert.equal(f.state().timing.simulationCallSeconds,.021);assert.equal(f.state().timing.backingCallSecondsDuringRun,.006);
 const simulation=f.state().timing.simulationCallSeconds;f.advanceWall(10000);await f.send('inspect');
 assert.equal(f.state().timing.simulationCallSeconds,simulation);assert(f.state().timing.elapsedSeconds>10);
 await f.send('snapshot');const checkpoint=f.exports().at(-1);assert.equal(decoder.decode(checkpoint.bytes),String(f.cycle()));
 assert.equal(f.timers.size,0);await f.send('inspect');assert.equal(f.cycle(),origin+100001n);
 await f.send('resume');await f.send('resume');assert.equal(f.timers.size,1);await f.tick();
 await f.send('run',{cycles:1n});assert.equal(f.timers.size,1);await f.drain();assert.equal(f.cycle(),origin+150002n);
 assert.equal(f.state().budget.requested,'1');await f.send('resume');assert.equal(f.timers.size,1);await f.tick();await f.send('pause');assert.equal(f.state().budget,null);
 for(const bad of [1,0n,'0','01','-1','1.0',' 1',String(MAX+1n)]){const before=f.cycle();await f.send('run',{cycles:bad});assert.equal(f.cycle(),before);assert.equal(f.timers.size,0);assert.equal(f.messages.at(-1).type,'error');}
 const before=f.cycle();await f.send('run',{cycles:'1',stopOnReady:'false'});assert.equal(f.cycle(),before);assert.equal(f.messages.at(-1).type,'error');
 await f.send('raw',{row:'now pen now 1 2 3 3 1 0'});const count=f.exports().length;
 await f.send('events');assert.equal(f.exports().length,count+1);assert.equal(f.exports().at(-1).name,'lemma-events.json');
 const raw=JSON.parse(decoder.decode(f.exports().at(-1).bytes));assert.equal(raw.until,String(f.cycle()));assert.equal(raw.events[0],`${f.cycle()} pen ${f.cycle()} 1 2 3 3 1 0`);
 assert.equal(Object.values(raw.checkpoints)[0].cycle,String(origin+100001n));
 await f.send('capture-outcomes');assert.equal(f.exports().length,count+2);assert.equal(f.exports().at(-1).name,'lemma-backing.io');
 await f.send('capture');assert.equal(f.exports().length,count+4);assert.deepEqual(f.exports().slice(-2).map(x=>x.name),['lemma-backing.io','lemma-events.json']);
}
{
 const f=await fixture({cycle:MAX-1n});await f.send('run',{cycles:'2'});assert.equal(f.timers.size,0);assert.equal(f.cycle(),MAX-1n);assert.match(f.messages.at(-1).error,/overflow/);
 await f.send('run',{cycles:'1'});await f.drain();assert.equal(f.cycle(),MAX);
}
// Only the existing full guest/controller predicate can end Ready runs.
{
 let runs=0;const full=record(0x420)+record(0x425,2n);
 const f=await fixture({initialUART:full,onRun:({setUART,setPaper})=>{runs++;setUART(full+record(0x420)+(runs>=2?record(0x425,3n):''));setPaper({completed:runs>=3?'3':'2',accepted:'3'});}});
 await f.send('run',{cycles:'200000',stopOnReady:true});await f.drain();
 assert.equal(runs,3);assert.equal(f.state().pauseReason,'guest-ready');assert.equal(f.state().budget.used,'150000');assert.equal(f.state().budget.remaining,'50000');
 assert.equal(f.state().readyAt.cycle,String(f.cycle()));const boundary=f.cycle();await f.send('run',{cycles:'1',stopOnReady:true});await f.drain();assert.equal(f.cycle(),boundary);
}
{
 const f=await fixture({onRun:({setUART,setPaper})=>{setUART(record(0x420)+record(0x425,3n));setPaper({completed:'2',accepted:'3'});}});
 await f.send('run',{cycles:'100001',stopOnReady:true});await f.drain();assert.equal(f.state().pauseReason,'cycle-limit');assert.equal(f.state().readyAt,null);
}
// Actual initializer transition retains the total budget across clock reset.
{
 const f=await fixture({cycle:0n,initialize:true,onRun:({generation,setUART,finish})=>{if(generation===1){setUART(record(0x41f));finish();}else setUART('');}});
 await f.send('run',{cycles:'100001'});await f.drain();assert.equal(f.cycle(),50001n);assert.equal(f.state().budget.used,'100001');assert.equal(f.state().budget.remaining,'0');
}
{
 const f=await fixture({cycle:0n,initialize:true,onRun:({generation,setUART,finish})=>{if(generation===1){setUART(record(0x41f));finish();}else setUART('');}});
 await f.send('run',{cycles:'50000'});await f.drain();assert.equal(f.cycle(),50000n);assert.equal(f.calls.filter(x=>x[0]==='lemma_create').length,1);
 await f.send('resume');await f.tick();await f.tick();await f.send('pause');assert.equal(f.calls.filter(x=>x[0]==='lemma_create').length,2);assert.equal(f.cycle(),50000n);
}
// Reset clears Ready history and budget; restored snapshots stay paused.
{
 const f=await fixture();await f.send('run',{cycles:'1'});await f.drain();await f.send('snapshot');const checkpoint=f.exports().at(-1).bytes;
 await f.send('run',{cycles:'10'});await f.drain();await f.send('restore',{bytes:checkpoint.buffer});assert.equal(f.state().state.cycle,decoder.decode(checkpoint));assert.equal(f.state().running,false);assert.equal(f.timers.size,0);assert.equal(f.state().budget,null);
 await f.send('reset',{cold:true});assert.equal(f.cycle(),0n);assert.equal(f.state().budget,null);assert.equal(f.state().readyAt,null);assert.equal(f.timers.size,0);
}
// A failed native call retains its actual executed prefix and stops scheduling.
{
 const f=await fixture({cycle:0n,onRun:({setCycle})=>{setCycle(7n);return 1;}});
 await f.send('run',{cycles:'100001'});await f.drain();assert.equal(f.cycle(),7n);assert.equal(f.state().budget.used,'7');assert.equal(f.state().budget.remaining,'99994');assert.equal(f.state().pauseReason,'error');
 assert.equal(f.calls.filter(x=>x[0]==='lemma_run').length,1);assert.match(f.messages.at(-1).error,/fake machine error/);
}
// Actual app handlers transmit input strings and make one explicit download.
{
 const nodes=new Map(),sent=[],downloads=[];let appWorker;
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',files:[],dataset:{},getContext:()=>({}),setPointerCapture(){}});return nodes.get(id);};
 const actions=['pause','resume','snapshot','export','capture-outcomes','events','bind','inspect','close'].map(action=>({...node('action-'+action),dataset:{action}}));
 const document={querySelector:node,querySelectorAll:()=>actions,createElement:()=>({click(){downloads.push(this.download);}})};
 const context=vm.createContext({document,navigator:{},Worker:class{constructor(){appWorker=this;}postMessage(m){sent.push(m);}},URL:{createObjectURL:()=>'/local-blob',revokeObjectURL(){}},Blob,setTimeout(){},console});
 const app=new vm.SourceTextModule(await fs.readFile('sim/browser/app.js','utf8'),{context});await app.link(()=>{throw Error('unexpected app import');});await app.evaluate();
 node('#run-cycles').value='18446744073709551615';node('#stop-ready').checked=true;node('#run-bounded').onclick();
 assert.equal(sent.at(-1).action,'run');assert.equal(sent.at(-1).cycles,String(MAX));assert.equal(typeof sent.at(-1).cycles,'string');assert.equal(sent.at(-1).stopOnReady,true);
 for(const action of ['events','capture-outcomes']){actions.find(n=>n.dataset.action===action).onclick();assert.equal(sent.at(-1).action,action);}
 appWorker.onmessage({data:{type:'export',name:'lemma-events.json',bytes:encoder.encode('{}')}});assert.deepEqual(downloads,['lemma-events.json']);
 appWorker.onmessage({data:{type:'state',state:{cycle:String(MAX)},running:false,pauseReason:'cycle-limit',readyAt:null,heapBytes:1048576,guestObservation:'continuation',hostSeconds:100,
  timing:{elapsedSeconds:100,simulationCallSeconds:2,backingCallSecondsDuringRun:1}}});
 assert.match(node('#status').textContent,/100.0 s elapsed/);assert.match(node('#status').textContent,/2.0 s simulation calls \(1.0 s backing\)/);assert.match(node('#status').textContent,/cycle-limit/);
}
console.log('PASS host worker protocol: exact budgets, cooperative pause, genuine Ready observation, initializer carry, passive snapshots, single-file exports, timing separation, actual UI handlers');
