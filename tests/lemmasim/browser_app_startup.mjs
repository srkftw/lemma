// SPDX-License-Identifier: Apache-2.0
// Actual app module with independent DOM/device fixtures. Host protocol only;
// no browser GPU, RV64 execution or controller conformance is established.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source=await fs.readFile('sim/browser/app.js','utf8');
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
async function appFixture(gpu){
 const nodes=new Map(),sent=[],images=[],canvases=[],gpuBytes=[];let worker,current,rect={left:0,top:0,width:100,height:100};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',files:[],dataset:{},setPointerCapture(){}});return nodes.get(id);};
 function canvas(){const c={width:3,height:1,style:{},setPointerCapture(){},releasePointerCapture(){},getBoundingClientRect:()=>rect,
  cloneNode:()=>canvas(),replaceWith(next){assert.equal(current,this);current=next;},getContext(kind){if(kind==='2d')return {createImageData:(w,h)=>({data:new Uint8Array(w*h*4)}),putImageData:image=>images.push(Array.from(image.data))};
   if(kind==='webgpu')return {configure(){},getCurrentTexture:()=>({createView:()=>({})})};throw Error('unexpected context');}};canvases.push(c);return c;}
 current=canvas();const actions=['pause','resume','snapshot','export','capture-outcomes','events','bind','inspect','close'].map(action=>({dataset:{action}}));
 node('#session-mode').value='student';
 const document={querySelector:id=>id==='canvas'?current:node(id),querySelectorAll:()=>actions,createElement:()=>({click(){}})};
 const context=vm.createContext({document,navigator:{gpu},Worker:class{constructor(){worker=this;}postMessage(m){sent.push(m);}},Uint8Array,URL:{createObjectURL:()=>'/local-blob',revokeObjectURL(){}},Blob,setTimeout(){},console,GPUTextureUsage:{TEXTURE_BINDING:1,COPY_DST:2}});
 const module=new vm.SourceTextModule(source,{context});await module.link(()=>{throw Error('unexpected app import');});
 let watchdog;try{await Promise.race([module.evaluate(),new Promise((_resolve,reject)=>{watchdog=setTimeout(()=>reject(Error('renderer initialization blocked actual app registration')),250);})]);}finally{clearTimeout(watchdog);}
 function exercise(){node('#medium').value='owned';node('#open').onclick();assert.equal(sent.at(-1).action,'open');assert.equal(sent.at(-1).name,'owned');assert.equal(sent.at(-1).mode,'student');
  actions.find(n=>n.dataset.action==='inspect').onclick();assert.equal(sent.at(-1).action,'inspect');
  node('#run-cycles').value='9007199254740993';node('#run-bounded').onclick();assert.equal(sent.at(-1).cycles,'9007199254740993');
  node('#import').onchange({target:{files:[]}});assert.equal(typeof node('#import').onchange,'function');
  worker.onmessage({data:{type:'state',state:{cycle:'9007199254740993'},running:false,guestObservation:'continuation',readyAt:null,heapBytes:1048576,pauseReason:'cycle-limit',timing:{elapsedSeconds:12,simulationCallSeconds:2,backingCallSecondsDuringRun:1}}});
  assert.match(node('#status').textContent,/9007199254740993/);
  worker.onmessage({data:{type:'panel',pixels:new Uint8Array([0,8,15]),width:3,height:1}});
  assert.deepEqual(images.at(-1),[0,0,0,255,136,136,136,255,255,255,255,255]);
 }
 exercise();return {exercise,sent,images,canvases,gpuBytes,worker,canvas:()=>current,node,actions,setRect:r=>rect=r};
}
{
 const f=await appFixture(undefined);
 f.node('#session-mode').value='developer';f.node('#session-mode').onchange();
 f.node('#open').onclick();assert.equal(f.sent.at(-1).mode,'developer');
 f.worker.onmessage({data:{type:'state',mode:'developer',state:{cycle:'0'},running:false,
  guestObservation:'boot',readyAt:null,heapBytes:1048576,pauseReason:'opened-paused',
  timing:{elapsedSeconds:0,simulationCallSeconds:0,backingCallSecondsDuringRun:0}}});
 assert.equal(f.node('#session-mode').disabled,true);
 f.worker.onmessage({data:{type:'closed'}});assert.equal(f.node('#session-mode').disabled,false);
}
// Presentation labels only newly emitted guest reports; a missing result,
// restored continuation or Close cannot inherit an earlier Saved label.
{
 const f=await appFixture(undefined);
 const state=guestCommit=>f.worker.onmessage({data:{type:'state',guestCommit,state:{cycle:'9007199254740993'},running:false,guestObservation:'continuation',readyAt:null,heapBytes:1048576,pauseReason:'user',timing:{elapsedSeconds:12,simulationCallSeconds:2,backingCallSecondsDuringRun:1}}});
 const reported={authority:'compiled-guest-report',value:'9007199254740993',page:'1',namespace:'1',detail:'32769'};
 state({...reported,state:'pending'});assert.match(f.node('#commit-status').textContent,/Guest save pending 9007199254740993/);
 state({...reported,state:'saved'});assert.match(f.node('#commit-status').textContent,/Guest reports Saved 9007199254740993/);
 state({...reported,state:'failed',value:'227'});assert.match(f.node('#commit-status').textContent,/Guest save failed \(227\)/);
 state(null);assert.match(f.node('#commit-status').textContent,/No save result observed/);
 state({...reported,state:'saved'});f.worker.onmessage({data:{type:'closed'}});assert.match(f.node('#commit-status').textContent,/No running guest/);
}
// A completed fork updates the reopen name once; ordinary observations do
// not overwrite the user's next-name edit. Failure never publishes a new name.
{
 const f=await appFixture(undefined);
 const emit=backingMedium=>f.worker.onmessage({data:{type:'state',backingMedium,state:{cycle:'17'},running:false,guestObservation:'continuation',readyAt:null,heapBytes:1048576,pauseReason:'restore',timing:{elapsedSeconds:1,simulationCallSeconds:0,backingCallSecondsDuringRun:0}}});
 emit({name:'original',private:false,ready:true});assert.equal(f.node('#medium').value,'original');
 emit({name:'unbound',private:true,ready:false});assert.equal(f.node('#medium').value,'original');
 assert.equal(f.node('#retry-private').disabled,false);assert.match(f.node('#backing-status').textContent,/incomplete/);
 emit({name:'fork_123',private:true,ready:true});assert.equal(f.node('#medium').value,'fork_123');
 assert.equal(f.node('#retry-private').disabled,true);assert.match(f.node('#backing-status').textContent,/Active private medium: fork_123/);
 f.node('#medium').value='next';emit({name:'fork_123',private:true,ready:true});assert.equal(f.node('#medium').value,'next');
 f.node('#medium').value='fork_123';f.worker.onmessage({data:{type:'closed'}});
 assert.equal(f.node('#medium').value,'fork_123');assert.equal(f.node('#retry-private').disabled,true);
 f.node('#open').onclick();assert.equal(f.sent.at(-1).name,'fork_123');
}
// An implicit capture loss ends exactly the held raw contact. A stale loss
// after pointerup cannot cancel a new pointer, and lifecycle controls release
// contact before asking the worker to close or reset the digital machine.
{
 const f=await appFixture(undefined);
 const down=id=>f.canvas().onpointerdown({pointerId:id,pointerType:'pen',pressure:.25,clientX:20,clientY:30});
 down(41);const first=f.sent.at(-1),count=f.sent.length;
 f.canvas().onlostpointercapture({pointerId:40});assert.equal(f.sent.length,count);
 f.canvas().onlostpointercapture({pointerId:41});
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{...first,pressure:0,flags:10});
 const cancelled=f.sent.length;f.canvas().onlostpointercapture({pointerId:41});assert.equal(f.sent.length,cancelled);
 down(42);assert.equal(f.sent.at(-1).flags,3);
 f.canvas().onpointerup({pointerId:42,pointerType:'pen',clientX:21,clientY:31});
 down(43);const third=f.sent.at(-1);f.canvas().onlostpointercapture({pointerId:42});assert.equal(f.sent.at(-1),third);
 f.node('#warm').onclick();assert.equal(f.sent.at(-2).flags,10);assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{action:'reset',cold:false});
 down(44);f.node('#cold').onclick();assert.equal(f.sent.at(-2).flags,10);assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{action:'reset',cold:true});
 down(45);f.actions.find(n=>n.dataset.action==='close').onclick();assert.equal(f.sent.at(-2).flags,10);assert.equal(f.sent.at(-1).action,'close');
}
// View scaling cannot advance a clock or change controller pixels. Scrolled,
// scaled geometry still supplies raw normalized device coordinates; a held
// contact is cancelled before the transform changes.
{
 const f=await appFixture(undefined),count=f.sent.length,pixels=f.images.at(-1);
 f.node('#display-scale').value='2';f.node('#display-scale').onchange();
 assert.equal(f.canvas().style.width,'6px');assert.equal(f.sent.length,count);
 assert.deepEqual(f.images.at(-1),pixels);
 f.setRect({left:120,top:-80,width:400,height:800});
 f.canvas().onpointerdown({pointerId:9,pointerType:'mouse',clientX:220,clientY:520});
 assert.equal(Object.keys(f.sent.at(-1)).sort().join(','),'action,flags,pressure,tool,x,y');
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{action:'pen',x:16384,y:49151,pressure:2048,flags:3,tool:0});
 f.node('#display-scale').value='fit';f.node('#display-scale').onchange();
 assert.equal(f.canvas().style.width,'');
 assert.equal(Object.keys(f.sent.at(-1)).sort().join(','),'action,flags,pressure,tool,x,y');
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{action:'pen',x:16384,y:49151,pressure:0,flags:10,tool:0});
}
// A GPU implementation may leave either capability promise pending forever.
for(const phase of ['adapter','device']){
 const never=new Promise(()=>{}),gpu={requestAdapter:()=>phase==='adapter'?never:Promise.resolve({requestDevice:()=>never}),getPreferredCanvasFormat:()=> 'rgba8unorm'};
 const f=await appFixture(gpu);await settle();f.exercise();assert.equal(f.canvases.length,1);assert.equal(f.sent.filter(m=>m.action==='pen').length,0);
}
// Qualifying a replacement and later device loss both cancel real contact.
{
 const adapter=deferred(),device=deferred(),pipeline=deferred(),lost=deferred(),written=[];
 const candidate={lost:lost.promise,createShaderModule:()=>({}),createRenderPipelineAsync:()=>pipeline.promise,
  createTexture:()=>({createView:()=>({}),destroy(){}}),createBindGroup:()=>({}),
  createCommandEncoder:()=>({beginRenderPass:()=>({setPipeline(){},setBindGroup(){},draw(){},end(){}}),finish:()=>({})}),
  queue:{writeTexture(_destination,bytes){written.push(Array.from(bytes));},submit(){},onSubmittedWorkDone:()=>Promise.resolve()}};
 const f=await appFixture({requestAdapter:()=>adapter.promise,getPreferredCanvasFormat:()=> 'rgba8unorm'});
 f.canvas().onpointerdown({pointerId:7,pointerType:'pen',pressure:.5,clientX:10,clientY:20});assert.equal(f.sent.at(-1).flags,3);const start=f.sent.at(-1);
 adapter.resolve({requestDevice:()=>device.promise});await settle();assert.equal(f.canvases.length,1);
 device.resolve(candidate);await settle();assert.equal(f.canvases.length,1);assert.equal(f.sent.at(-1),start);
 pipeline.resolve({getBindGroupLayout:()=>({})});await settle();assert.equal(f.canvases.length,2);
 const cancelled=f.sent.at(-1);assert.equal(cancelled.action,'pen');assert.equal(cancelled.pressure,0);assert.equal(cancelled.flags,10);assert.equal(cancelled.tool,1);assert.equal(cancelled.x,start.x);assert.equal(cancelled.y,start.y);
 assert.deepEqual(written.at(-1),[0,8,15]);assert.equal(typeof f.canvas().onpointerdown,'function');
 f.canvas().onpointerdown({pointerId:8,pointerType:'mouse',clientX:20,clientY:30});lost.resolve({reason:'destroyed'});await settle();
 assert.equal(f.canvases.length,3);assert.equal(f.sent.at(-1).flags,10);assert.equal(f.sent.at(-1).tool,0);assert.equal(f.sent.at(-1).pressure,0);
 assert.deepEqual(f.images.at(-1),[0,0,0,255,136,136,136,255,255,255,255,255]);
}

// The file form moves only opaque bytes and a decimal transaction. It never
// invents an Installed receipt and Close clears the previous launch's label.
{
 const f=await appFixture(undefined),bytes=new ArrayBuffer(4040);
 f.node('#course-package').files=[{size:4040,arrayBuffer:async()=>bytes}];
 f.node('#course-transaction').value='9007199254740993';
 await f.node('#install-course').onclick();
 assert.equal(f.sent.at(-1).action,'course-install');assert.equal(f.sent.at(-1).bytes,bytes);
 assert.equal(f.sent.at(-1).transaction,'9007199254740993');
 f.worker.onmessage({data:{type:'course-admission',accepted:37,total:37,bytes:4040,error:null}});
 assert.match(f.node('#course-admission').textContent,/Admitted 4040 package bytes/);
 assert.match(f.node('#course-admission').textContent,/guest installation result below/);
 const emit=guestCourse=>f.worker.onmessage({data:{type:'state',guestCourse,state:{cycle:'1'},running:false,guestObservation:'boot',readyAt:null,heapBytes:1048576,timing:{elapsedSeconds:0,simulationCallSeconds:0,backingCallSecondsDuringRun:0}}});
 emit(null);assert.match(f.node('#course-result').textContent,/No installation result/);
 emit({state:'installed',identity:'1',edition:'2',sequence:'9007199254740993'});
 assert.match(f.node('#course-result').textContent,/Guest reports installed package 1, edition 2, durable sequence 9007199254740993/);
 assert.doesNotMatch(f.node('#course-admission').textContent,/awaiting/);
 emit({state:'failed',identity:'1',edition:'2',status:'223'});
 assert.match(f.node('#course-result').textContent,/failure \(223\)/);
 f.worker.onmessage({data:{type:'course-admission',accepted:2,total:37,bytes:4040,error:'queue exhausted'}});
 assert.match(f.node('#course-admission').textContent,/Admitted 2 of 37/);assert.match(f.node('#course-admission').textContent,/Close and cold-open/);
 f.worker.onmessage({data:{type:'closed'}});assert.match(f.node('#course-result').textContent,/No running guest/);
 for(const size of [127,32769]){
  const count=f.sent.length;f.node('#course-package').files=[{size,arrayBuffer:async()=>{throw Error('must not read unbounded file');}}];
  await f.node('#install-course').onclick();assert.equal(f.sent.length,count);
 }
}
console.log('PASS actual app host fixture: unresolved GPU leaves controls, worker observation and exact Gray4 fallback functional; qualified switch/loss safely cancel contact');
