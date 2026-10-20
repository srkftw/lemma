// SPDX-License-Identifier: Apache-2.0
// Actual app module with independent DOM/device fixtures. Host protocol only;
// no browser GPU, RV64 execution or controller conformance is established.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import vm from 'node:vm';
const source=await fs.readFile('sim/browser/app.js','utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((r,e)=>{resolve=r;reject=e;});return {promise,resolve,reject};};
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
async function appFixture(gpu){
 const nodes=new Map(),sent=[],images=[],canvases=[],gpuBytes=[],viewportListeners=new Map(),documentListeners=new Map(),audioSources=[];let worker,current,rect={left:0,top:0,width:100,height:100};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',checked:false,textContent:'',files:[],dataset:{},addEventListener(name,callback){(this.listeners??=new Map()).set(name,callback);},setPointerCapture(){},releasePointerCapture(){}});return nodes.get(id);};
 function canvas(){const c={width:3,height:1,style:{},setPointerCapture(){},releasePointerCapture(){},getBoundingClientRect:()=>rect,
  cloneNode:()=>canvas(),replaceWith(next){assert.equal(current,this);current=next;},getContext(kind){if(kind==='2d')return {createImageData:(w,h)=>({data:new Uint8Array(w*h*4)}),putImageData:image=>images.push(Array.from(image.data))};
   if(kind==='webgpu')return {configure(){},getCurrentTexture:()=>({createView:()=>({})})};throw Error('unexpected context');}};canvases.push(c);return c;}
 current=canvas();const actions=['pause','resume','snapshot','export','capture-outcomes','events','bind','inspect','close'].map(action=>({dataset:{action}}));
 node('#session-mode').value='student';
 const document={hidden:false,addEventListener:(name,callback)=>documentListeners.set(name,callback),querySelector:id=>id==='canvas'?current:node(id),querySelectorAll:()=>actions,createElement:()=>({click(){}})};
 const context=vm.createContext({fetch:async url=>{assert.equal(url,'./bundle.json');return {ok:true,json:async()=>({backend:'fixture-machine'})};},document,window:{addEventListener:(name,callback)=>viewportListeners.set(name,callback)},navigator:{gpu},Worker:class{constructor(){worker=this;}postMessage(m){sent.push(m);}},Uint8Array,URL:{createObjectURL:()=>'/local-blob',revokeObjectURL(){}},Blob,setTimeout(){},console,AudioContext:class{constructor(){this.state='running';this.currentTime=0;this.destination={};}async resume(){}createBuffer(_channels,length,rate){return {duration:length/rate,getChannelData:()=>new Float32Array(length)};}createBufferSource(){const source={connect(){},start(){this.started=true;},stop(){this.stopped=true;}};audioSources.push(source);return source;}},GPUTextureUsage:{TEXTURE_BINDING:1,COPY_DST:2}});
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
 exercise();return {exercise,sent,images,canvases,gpuBytes,worker,canvas:()=>current,node,actions,setRect:r=>rect=r,resize:()=>viewportListeners.get('resize')?.(),visibility:hidden=>{document.hidden=hidden;documentListeners.get('visibilitychange')?.();},audioSources,trigger:(id,name)=>node(id).listeners?.get(name)?.()};
}
{
 const f=await appFixture(undefined);
 f.node('#session-mode').value='developer';f.node('#session-mode').onchange();
 f.node('#open').onclick();assert.equal(f.sent.at(-1).mode,'developer');
 for(const paused of [true,false]){
  f.node('#open-paused').checked=paused;
  f.node('#initialize').onclick();assert.equal(f.sent.at(-1).initialize,true);
  assert.equal(f.sent.at(-1).paused,paused,'new-medium creation must honor Open paused');
  f.node('#open').onclick();assert.equal(f.sent.at(-1).paused,paused);
 }
 f.worker.onmessage({data:{type:'state',mode:'developer',state:{cycle:'0'},running:false,
  guestObservation:'boot',readyAt:null,heapBytes:1048576,pauseReason:'opened-paused',
  timing:{elapsedSeconds:0,simulationCallSeconds:0,backingCallSecondsDuringRun:0}}});
 assert.equal(f.node('#session-mode').disabled,true);
 f.worker.onmessage({data:{type:'closed'}});assert.equal(f.node('#session-mode').disabled,false);
}
// A real interpreter deadline must retain its measured progress in the error
// shown to a Student. A new machine launch cannot inherit that failed interval.
{
 const f=await appFixture(undefined);
 f.worker.onmessage({data:{type:'execution-boundary',before:{cycle:'332823721'},observed:{cycle:'333000123'},targetVirtualNs:'3428237203',elapsedSeconds:60.125,result:'Original60s execution quantum deadline'}});
 f.worker.onmessage({data:{type:'error',error:'Original60s execution quantum deadline'}});
 assert.match(f.node('#status').textContent,/332823721 to 333000123/);
 assert.match(f.node('#status').textContent,/60\.1 s/);
 f.node('#open').onclick();
 f.worker.onmessage({data:{type:'error',error:'Different launch failure'}});
 assert.equal(f.node('#status').textContent,'Different launch failure');
}
{
 const f=await appFixture(undefined);f.node('#resume-seconds').value='600';
 f.actions.find(n=>n.dataset.action==='resume').onclick();
 assert.equal(f.sent.at(-1).action,'resume');assert.equal(f.sent.at(-1).hostSeconds,'600');
 f.node('#resume-seconds').value='';f.actions.find(n=>n.dataset.action==='resume').onclick();
 assert.equal(f.sent.at(-1).hostSeconds,null);
}
// Hidden-page notification cancels real queued sink sources in the actual app.
// Browser DOM/AudioContext fixtures verify host behavior only, not audibility.
{
 const f=await appFixture(undefined);await f.node('#pcm-enable').onclick();
 const pcm={format:'mono-s16le-low16/1',clock_hz:100000000,dropped:0,samples:[['2000','1',100],['4000','2',-200]]};
 f.worker.onmessage({data:{type:'pcm',pcm}});
 assert.equal(f.audioSources.length,1);assert.equal(f.audioSources[0].started,true);
 f.visibility(true);assert.equal(f.audioSources[0].stopped,true);
 assert.match(f.node('#pcm-status').textContent,/Page hidden/);
 f.worker.onmessage({data:{type:'pcm',pcm}});assert.equal(f.audioSources.length,1,'hidden page must not schedule new sink samples');
 f.visibility(false);await f.node('#pcm-enable').onclick();
 f.worker.onmessage({data:{type:'pcm',pcm:{...pcm,samples:[['6000','3',100],['8000','4',-200]]}}});
 assert.equal(f.audioSources.length,2);f.trigger('#cold','click');assert.equal(f.audioSources[1].stopped,true);
 assert.match(f.node('#pcm-status').textContent,/Machine output epoch changed/);
}
// Controller cancellation clears every queued source independently of the
// browser playback permission. A later authorized controller turn can render.
{
 const f=await appFixture(undefined);await f.node('#pcm-enable').onclick();
 const emit=(first,position)=>f.worker.onmessage({data:{type:'pcm',pcm:{format:'mono-s16le-low16/1',clock_hz:100000000,dropped:0,samples:[[String(first),String(position),100],[String(first+2000),String(position+1),-100]]}}});
 emit(2000,1);assert.equal(f.audioSources.length,1);
 f.worker.onmessage({data:{type:'pcm-stop',reason:'Controller consent epoch revoked'}});
 assert.equal(f.audioSources[0].stopped,true);assert.match(f.node('#pcm-status').textContent,/epoch revoked/);
 emit(6000,3);assert.equal(f.audioSources.length,2,'controller stop must preserve independent speaker permission');
 f.node('#pcm-mute').onclick();assert.equal(f.audioSources[1].stopped,true);
 emit(10000,5);assert.equal(f.audioSources.length,2,'local sink mute must reject subsequent samples');
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
// Slow selected files belong to the machine/action where they were selected.
// Resolve actual app reads after a newer lifecycle intent; no stale message
// may reach the worker or replace the newer operation's status.
{
 for(const transition of ['open','close','reset']){
  const f=await appFixture(undefined),read=deferred();
  const input={files:[{size:512,arrayBuffer:()=>read.promise}],value:'checkpoint'};
  const pending=f.node('#restore').onchange({target:input});
  if(transition==='open')f.node('#open').onclick();
  if(transition==='close')f.actions.find(n=>n.dataset.action==='close').onclick();
  if(transition==='reset')f.node('#warm').onclick();
  const count=f.sent.length;read.resolve(new ArrayBuffer(512));await pending;
  assert.equal(f.sent.length,count,`stale restore crossed ${transition}`);
  assert.equal(input.value,'','same file remains selectable after cancellation');
 }
}
// An explicit newer restore wins even when its file read finishes first.
{
 const f=await appFixture(undefined),a=deferred(),b=deferred();
 const first=f.node('#restore').onchange({target:{files:[{size:512,arrayBuffer:()=>a.promise}],value:'a'}});
 const second=f.node('#restore').onchange({target:{files:[{size:512,arrayBuffer:()=>b.promise}],value:'b'}});
 const newest=new ArrayBuffer(512);b.resolve(newest);await second;
 const count=f.sent.length;a.resolve(new ArrayBuffer(512));await first;
 assert.equal(f.sent.length,count,'older restore overtook selected newer checkpoint');
 assert.equal(f.sent.at(-1).action,'restore');assert.equal(f.sent.at(-1).bytes,newest);
}
// Rejecting a newer file/Send must also cancel the old asynchronous selection.
// Otherwise the error would be followed by an unexpected older restore.
{
 for(const control of ['restore','pending-outcomes','import','install-course','replay']){
  const f=await appFixture(undefined),read=deferred();let invalidReads=0;
  const pending=f.node('#restore').onchange({target:{files:[{size:512,arrayBuffer:()=>read.promise}],value:'old'}});
  const invalid={size:805306369,arrayBuffer:()=>{invalidReads++;throw Error('invalid file read');}};
  if(control==='install-course'){
   f.node('#course-package').files=[invalid];await f.node('#install-course').onclick();
  }else if(control==='replay')await f.node('#replay').onclick();
  else await f.node('#'+control).onchange({target:{files:[invalid],value:'invalid'}});
  const target=f.node(control==='install-course'?'#course-admission':'#status');
  const message=target.textContent,count=f.sent.length;
  assert.ok(message.length,'rejected input must remain visible');
  read.resolve(new ArrayBuffer(512));await pending;
  assert.equal(f.sent.length,count,`old restore followed rejected ${control}`);
  assert.equal(target.textContent,message);assert.equal(invalidReads,0);
 }
}
// Transaction IDs and destination names are selection-time inputs. Editing
// fields during a read must not pair the old bytes with the new fields.
{
 const f=await appFixture(undefined),read=deferred();
 f.node('#course-package').files=[{size:128,arrayBuffer:()=>read.promise}];
 f.node('#course-transaction').value='9007199254740993';
 const pending=f.node('#install-course').onclick();
 f.node('#course-transaction').value='9007199254740994';read.resolve(new ArrayBuffer(128));await pending;
 assert.equal(f.sent.at(-1).transaction,'9007199254740993');
 const imported=deferred();f.node('#medium').value='selected-destination';
 const selecting=f.node('#import').onchange({target:{files:[{size:268435456,arrayBuffer:()=>imported.promise}],value:'source'}});
 f.node('#medium').value='next-destination';imported.resolve(new ArrayBuffer(16));await selecting;
 assert.equal(f.sent.at(-1).name,'selected-destination');
}
// Read failures are visible for the current selection. An obsolete failure
// cannot overwrite the newer machine's status or become an unhandled rejection.
{
 const f=await appFixture(undefined),failure=deferred();
 const pending=f.node('#restore').onchange({target:{files:[{size:512,arrayBuffer:()=>failure.promise}],value:'one'}});
 const before=f.sent.length;failure.reject(Error('permission denied'));await pending;
 assert.equal(f.sent.length,before);assert.match(f.node('#status').textContent,/permission denied/);
 const stale=deferred(),old=f.node('#restore').onchange({target:{files:[{size:512,arrayBuffer:()=>stale.promise}],value:'two'}});
 f.node('#open').onclick();f.node('#status').textContent='new machine status';
 stale.reject(Error('obsolete read error'));await old;
 assert.equal(f.node('#status').textContent,'new machine status');
}
// Multipart replay stops reading later files after cancellation; no selected
// outcome source or raw event stream is consulted for the superseded machine.
{
 const f=await appFixture(undefined),read=deferred();let laterReads=0;
 f.node('#replay-checkpoint').files=[{size:512,arrayBuffer:()=>read.promise}];
 f.node('#replay-io').files=[{size:128,arrayBuffer:()=>{laterReads++;return Promise.resolve(new ArrayBuffer(128));}}];
 f.node('#replay-events').files=[{size:2,text:()=>{laterReads++;return Promise.resolve('[]');}}];
 const pending=f.node('#replay').onclick();f.actions.find(n=>n.dataset.action==='close').onclick();
 const count=f.sent.length;read.resolve(new ArrayBuffer(512));await pending;
 assert.equal(laterReads,0);assert.equal(f.sent.length,count);
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
// One pointer owns the raw power level. Other fingers and stale capture
// notifications cannot release that hold; real capture loss releases it once.
// Close releases into the current machine before asking the worker to close.
{
 const f=await appFixture(undefined),power=f.node('#power');
 const levels=()=>f.sent.filter(m=>m.action==='button').map(m=>m.level);
 power.onpointerdown({pointerId:51});power.onpointerdown({pointerId:52});
 assert.deepEqual(levels(),[1]);
 power.onpointerup({pointerId:52});assert.deepEqual(levels(),[1]);
 power.onlostpointercapture({pointerId:51});assert.deepEqual(levels(),[1,0]);
 power.onpointercancel({pointerId:51});power.onpointerup({pointerId:51});
 assert.deepEqual(levels(),[1,0]);
 power.onpointerdown({pointerId:53});power.onlostpointercapture({pointerId:51});
 assert.deepEqual(levels(),[1,0,1]);
 power.onpointerup({pointerId:53});assert.deepEqual(levels(),[1,0,1,0]);
 power.onpointerdown({pointerId:54});power.onpointercancel({pointerId:54});
 assert.deepEqual(levels(),[1,0,1,0,1,0]);
 power.onpointerdown({pointerId:55});f.actions.find(n=>n.dataset.action==='close').onclick();
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.slice(-2))),[{action:'button',level:0},{action:'close'}]);
 power.onlostpointercapture({pointerId:55});assert.deepEqual(levels(),[1,0,1,0,1,0,1,0]);
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
// A viewport/container transform change ends the old raw contact before any
// new coordinates are sent. No new contact or fabricated controller pixels.
{
 const f=await appFixture(undefined),down=id=>f.canvas().onpointerdown({pointerId:id,pointerType:'pen',pressure:.25,clientX:20,clientY:30});
 down(61);const first=f.sent.at(-1),pixels=f.images.at(-1);
 f.setRect({left:0,top:0,width:200,height:150});f.resize();
 f.canvas().onpointermove({pointerId:61,pointerType:'pen',pressure:.5,clientX:25,clientY:35});
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{...first,pressure:0,flags:10});
 assert.equal(f.images.at(-1),pixels);const end=f.sent.length;
 f.canvas().onpointerup({pointerId:61,pointerType:'pen',clientX:25,clientY:35});assert.equal(f.sent.length,end);
 down(62);assert.equal(f.sent.at(-1).flags,3);const second=f.sent.at(-1),same=f.sent.length;
 f.resize();assert.equal(f.sent.length,same,'unchanged transform cancels contact');
 // Scrolling/repositioning may not dispatch resize. The point guard must
 // notice the changed transform before forwarding the next raw sample.
 f.setRect({left:10,top:15,width:200,height:150});
 f.canvas().onpointermove({pointerId:62,pointerType:'pen',pressure:.75,clientX:28,clientY:39});
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{...second,pressure:0,flags:10});
 const cancelled=f.sent.length;
 for(const rect of [{left:0,top:0,width:0,height:150},{left:0,top:0,width:200,height:NaN}]){
  f.setRect(rect);down(63);assert.equal(f.sent.length,cancelled,'invalid geometry admitted raw input');
 }
 f.setRect({left:0,top:0,width:200,height:150});down(64);
 assert.equal(f.sent.at(-1).flags,3,'bad geometry retained a phantom contact');
 const accepted=f.sent.at(-1);f.canvas().onpointercancel({pointerId:64,pointerType:'pen',clientX:NaN,clientY:NaN});
 assert.deepEqual(JSON.parse(JSON.stringify(f.sent.at(-1))),{...accepted,pressure:0,flags:10});
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
 const transfer=uart_ingress=>f.worker.onmessage({data:{type:'state',state:{cycle:'2',uart_ingress},running:false,heapBytes:1048576,timing:{elapsedSeconds:0,simulationCallSeconds:0,backingCallSecondsDuringRun:0}}});
 transfer({delivered:'16',pending:'9007199254740993',canceled:'0',accepted:'9007199254741009',blocked:true});
 assert.match(f.node('#serial-status').textContent,/16 delivered, 9007199254740993 queued/);
 assert.match(f.node('#serial-status').textContent,/waiting for guest receiver/);
 assert.match(f.node('#course-result').textContent,/No installation result/);
 transfer({delivered:'4040',pending:'0',canceled:'0',accepted:'4040',blocked:false});
 assert.doesNotMatch(f.node('#serial-status').textContent,/waiting/);
 assert.match(f.node('#serial-status').textContent,/Byte delivery is not an installation receipt/);
 assert.match(f.node('#course-result').textContent,/No installation result/);
 emit({state:'installed',identity:'1',edition:'2',sequence:'9007199254740993'});
 assert.match(f.node('#course-result').textContent,/Guest reports installed package 1, edition 2, durable sequence 9007199254740993/);
 assert.doesNotMatch(f.node('#course-admission').textContent,/awaiting/);
 emit({state:'failed',identity:'1',edition:'2',status:'223'});
 assert.match(f.node('#course-result').textContent,/failure \(223\)/);
 f.worker.onmessage({data:{type:'course-admission',accepted:2,total:37,bytes:4040,error:'queue exhausted'}});
 assert.match(f.node('#course-admission').textContent,/Admitted 2 of 37/);assert.match(f.node('#course-admission').textContent,/Close and cold-open/);
 f.worker.onmessage({data:{type:'closed'}});assert.match(f.node('#course-result').textContent,/No running guest/);
 assert.match(f.node('#serial-status').textContent,/No running serial transfer/);
 for(const size of [127,32769]){
  const count=f.sent.length;f.node('#course-package').files=[{size,arrayBuffer:async()=>{throw Error('must not read unbounded file');}}];
  await f.node('#install-course').onclick();assert.equal(f.sent.length,count);
 }
}
// Keyboard pen uses the same raw input boundary, including contact cancellation.
{
 const f=await appFixture(undefined),paper=f.canvas();paper.width=1650;paper.height=2200;
 const images=f.images.length,key=(key,fields={})=>paper.onkeydown({key,repeat:false,preventDefault(){},...fields});
 key('Home');for(let i=0;i<3;i++)key('ArrowRight',{ctrlKey:true});key('ArrowRight');
 key('ArrowDown',{ctrlKey:true});key('ArrowDown');key('ArrowDown');for(let i=0;i<5;i++)key('ArrowDown',{shiftKey:true});
 assert.match(f.node('#keyboard-pen-status').textContent,/320, 145/);key('Enter');
 const down=f.sent.at(-2),up=f.sent.at(-1);assert.equal(down.action,'pen');assert.equal(down.flags,3);assert.equal(up.flags,2);
 assert.equal(down.x,Math.round(320*65535/1649));assert.equal(up.y,Math.round(145*65535/2199));
 key(' ');key('ArrowRight');assert.equal(f.sent.at(-1).flags,3);f.visibility(true);assert.equal(f.sent.at(-1).flags,10);
 const cancelled=f.sent.length;paper.onblur();assert.equal(f.sent.length,cancelled);
 key('Insert');assert.equal(f.sent.at(-1).flags,3);
 paper.onkeyup({key:'Insert'});key('ArrowRight');assert.equal(f.sent.at(-1).flags,3);
 key('Insert');assert.equal(f.sent.at(-1).flags,2);
 key('Insert');paper.onblur();assert.equal(f.sent.at(-1).flags,10);
 key('Insert');key('Escape');assert.equal(f.sent.at(-1).flags,10);
 assert.equal(f.images.length,images,'keyboard input must not manufacture controller pixels');
}
console.log('PASS actual app host fixture: unresolved GPU leaves controls, worker observation and exact Gray4 fallback functional; qualified switch/loss safely cancel contact');
