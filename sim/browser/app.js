// SPDX-License-Identifier: Apache-2.0
const worker=new Worker('./worker.js',{type:'module'}),status=document.querySelector('#status'),commitStatus=document.querySelector('#commit-status');
let canvas=document.querySelector('canvas'),lastPlane=null;
let displayedMediumName=null;
let executionBoundary=null;
function boundaryText(){if(executionBoundary===null)return '';const b=executionBoundary;
 return ` · Last execution boundary: cycle ${b.before?.cycle??'?'} to ${b.observed?.cycle??'?'}; target ${b.targetVirtualNs??'?'} virtual ns; ${Number(b.elapsedSeconds).toFixed(1)} s (${b.result})`;}
// File reads finish outside the worker queue. A later selection or machine
// lifecycle intent cancels their authority to submit into that queue.
let selectionEpoch=0n,selectionMachineName=null;
function beginSelection(){return ++selectionEpoch;}
async function selectionBytes(file,selection,errorTarget=status){
 try{const bytes=await file.arrayBuffer();return selection===selectionEpoch?bytes:null;}
 catch(e){if(selection===selectionEpoch)errorTarget.textContent=String(e);return null;}
}
let active=null,activeTool=0,activeTransform=null,last={x:0,y:0};
// WebGPU only presents controller-produced Gray4 bytes. Device loss selects
// a fresh 2D canvas presenting the identical plane; it never fabricates ink.
// Controls and worker observation always start with a usable 2D canvas.
// An unresolved adapter/device promise cannot block their registration.
let context=canvas.getContext('2d'),gpu=null,pipeline=null,device=null;
const displayScale=document.querySelector('#display-scale');
const sessionMode=document.querySelector('#session-mode');
fetch('./bundle.json').then(response=>{if(!response.ok)throw Error('Bundle unavailable');return response.json();}).then(bundle=>{
 document.querySelector('#machine-build').textContent=(bundle.backend??bundle.profile??'Local machine')+(bundle.initialization?' · '+bundle.initialization:'');
 if(bundle.initialization?.startsWith('copy exact guest-produced'))document.querySelector('#initialize').textContent='Create from guest-produced seed';
 else if(bundle.initialization?.startsWith('requires imported')){document.querySelector('#initialize').disabled=true;document.querySelector('#initialize').title=bundle.initialization;}
}).catch(error=>{document.querySelector('#machine-build').textContent=String(error);});
function modeControls(){document.querySelectorAll('[data-developer]').forEach(control=>{control.hidden=sessionMode.value==='student';});}
sessionMode.onchange=()=>{beginSelection();modeControls();};modeControls();
function scaleDisplay(){const factor=({'1':1,'1.5':1.5,'2':2})[displayScale.value]||0;
 canvas.style.width=factor?`${canvas.width*factor}px`:'';}
function cancelContact(){cancelKeyboardPen();if(active===null)return;const pointer=active;active=null;activeTransform=null;
 send('pen',{...last,pressure:0,flags:10,tool:activeTool});
 try{canvas.releasePointerCapture(pointer);}catch(e){} }
// Zoom presents the existing controller plane. Cancel an active contact before
// changing its coordinate transform, just as for a display-device replacement.
displayScale.onchange=()=>{cancelContact();scaleDisplay();};
function fallback(){cancelContact();gpu=null;pipeline=null;device=null;
 const next=canvas.cloneNode(false);canvas.replaceWith(next);canvas=next;context=canvas.getContext('2d');bindPointer();
 if(lastPlane)present(lastPlane);status.textContent='Display device lost; controller pixels now use the 2D fallback.';}
async function initializeGPU(){if(!navigator.gpu)return;
 const adapter=await navigator.gpu.requestAdapter();if(!adapter)return;
 const candidate=await adapter.requestDevice();let lost=false;
 candidate.lost.then(()=>{lost=true;if(device===candidate)fallback();});
 const shader=candidate.createShaderModule({code:`@group(0) @binding(0) var t:texture_2d<f32>;
 @vertex fn v(@builtin(vertex_index) i:u32)->@builtin(position) vec4f{var p=array<vec2f,3>(vec2f(-1,-1),vec2f(3,-1),vec2f(-1,3));return vec4f(p[i],0,1);}
 @fragment fn f(@builtin(position) p:vec4f)->@location(0) vec4f{let g=textureLoad(t,vec2i(p.xy),0).r*17;return vec4f(g,g,g,1);}`});
 const format=navigator.gpu.getPreferredCanvasFormat();
 const prepared=await candidate.createRenderPipelineAsync({layout:'auto',vertex:{module:shader,entryPoint:'v'},fragment:{module:shader,entryPoint:'f',targets:[{format}]},primitive:{topology:'triangle-list'}});
 if(lost)return;
 // A canvas already bound to 2D cannot become a WebGPU canvas. Prepare a
 // detached replacement before cancelling contact and changing presentation.
 const next=canvas.cloneNode(false),target=next.getContext('webgpu');if(!target)return;
 target.configure({device:candidate,format,alphaMode:'opaque'});if(lost)return;
 cancelContact();canvas.replaceWith(next);canvas=next;context=null;device=candidate;pipeline=prepared;gpu=target;bindPointer();if(lastPlane)present(lastPlane);
}
function send(action,rest={},transfer=[]){
 if(action==='open')executionBoundary=null;
 if(action==='close'||action==='reset'||action==='restore')document.querySelector('#school-credential').value='';
 worker.postMessage({action,...rest},transfer);
}
function download(name,bytes){const u=URL.createObjectURL(new Blob([bytes])),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
document.querySelector('#open').onclick=()=>{beginSelection();send('open',{name:document.querySelector('#medium').value,mode:sessionMode.value,paused:document.querySelector('#open-paused').checked});};
document.querySelector('#initialize').onclick=()=>{beginSelection();send('open',{name:document.querySelector('#medium').value,mode:sessionMode.value,initialize:true,paused:document.querySelector('#open-paused').checked});};
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{
 if(b.dataset.action==='close'){beginSelection();cancelContact();cancelPower();}
 send(b.dataset.action,b.dataset.action==='resume'?{hostSeconds:document.querySelector('#resume-seconds').value||null}:{});});
document.querySelector('#run-bounded').onclick=()=>send('run',{cycles:document.querySelector('#run-cycles').value,stopOnReady:document.querySelector('#stop-ready').checked,stopOnPanel:document.querySelector('#stop-panel').checked,hostSeconds:document.querySelector('#run-seconds').value||null});
document.querySelector('#admit-raw').onclick=()=>send('raw',{row:document.querySelector('#raw-event').value});
document.querySelector('#admit-batch').onclick=()=>send('raw-batch',{rows:document.querySelector('#raw-batch').value});
document.querySelector('#warm').onclick=()=>{beginSelection();cancelContact();send('reset',{cold:false});};
document.querySelector('#cold').onclick=()=>{beginSelection();cancelContact();send('reset',{cold:true});};
document.querySelector('#install-course').onclick=async()=>{
 const selection=beginSelection(),file=document.querySelector('#course-package').files[0];
 if(!file||file.size<128||file.size>32768){document.querySelector('#course-admission').textContent='Choose a course package containing 128 to32768 bytes.';return;}
 const transaction=document.querySelector('#course-transaction').value;
 const bytes=await selectionBytes(file,selection,document.querySelector('#course-admission'));
 if(bytes!==null)send('course-install',{bytes,transaction},[bytes]);
};
// Auto-submitting file controls consume a selection, allowing the same file
// to be chosen again for a retry or another private restore. Explicit Send
// controls (course/replay) retain their selected files until the user sends.
function selectedFile(input){const file=input.files[0];input.value='';return file;}
document.querySelector('#restore').onchange=async e=>{const selection=beginSelection(),file=selectedFile(e.target);if(!file)return;if(file.size>805306368){status.textContent='Checkpoint exceeds the machine bound';return;}const bytes=await selectionBytes(file,selection);if(bytes!==null)send('restore',{bytes},[bytes]);};
document.querySelector('#pending-outcomes').onchange=async e=>{const selection=beginSelection(),file=selectedFile(e.target);if(!file)return;if(file.size>268435456){status.textContent='Outcome tape exceeds the machine bound';return;}const bytes=await selectionBytes(file,selection);if(bytes!==null)send('outcomes',{bytes},[bytes]);};
document.querySelector('#import').onchange=async e=>{const selection=beginSelection(),file=selectedFile(e.target);if(!file)return;if(file.size!==268435456){status.textContent='Expected a 256 MiB raw medium';return;}const name=document.querySelector('#medium').value,mode=sessionMode.value,bytes=await selectionBytes(file,selection);if(bytes!==null)send('import',{name,mode,bytes},[bytes]);};
document.querySelector('#replay').onclick=async()=>{const selection=beginSelection();try{
 const c=document.querySelector('#replay-checkpoint').files[0],io=document.querySelector('#replay-io').files[0],raw=document.querySelector('#replay-events').files[0];
 if(!c||!io||!raw)throw Error('Select checkpoint, backing outcomes and raw event capture');
 if(c.size>805306368||io.size>268435456||raw.size>268435456)throw Error('Replay input exceeds its bound');
 const name=document.querySelector('#medium').value,mode=sessionMode.value;
 const checkpoint=await selectionBytes(c,selection);if(checkpoint===null)return;
 const replayLog=await selectionBytes(io,selection);if(replayLog===null)return;
 const events=JSON.parse(await raw.text());if(selection!==selectionEpoch)return;
 send('replay',{name,mode,checkpoint,replayLog,events},[checkpoint,replayLog]);
 }catch(e){if(selection===selectionEpoch)status.textContent=String(e);}};
const power=document.querySelector('#power');let powerPointer=null;
function cancelPower(){if(powerPointer===null)return;const pointer=powerPointer;powerPointer=null;
 send('button',{level:0});try{power.releasePointerCapture(pointer);}catch(e){} }
power.onpointerdown=e=>{if(powerPointer!==null)return;power.setPointerCapture(e.pointerId);powerPointer=e.pointerId;send('button',{level:1});};
power.onpointerup=power.onpointercancel=power.onlostpointercapture=e=>{if(e.pointerId===powerPointer)cancelPower();};
function pointerTransform(){const r=canvas.getBoundingClientRect();
 const result={left:r.left,top:r.top,width:r.width,height:r.height,pixelsX:canvas.width,pixelsY:canvas.height};
 return Object.values(result).every(Number.isFinite)&&r.width>0&&r.height>0&&canvas.width>0&&canvas.height>0?result:null;}
function sameTransform(next){return next!==null&&activeTransform!==null&&
 Object.keys(activeTransform).every(key=>activeTransform[key]===next[key]);}
// Resizing or scrolling must not join points from two coordinate systems.
// Cancellation uses the last accepted raw point, including on invalid layout;
// it never constructs ink or changes virtual time in the presentation thread.
window.addEventListener('resize',()=>{if(active!==null&&!sameTransform(pointerTransform()))cancelContact();});
function point(e,contact,cancel=false){const r=pointerTransform();
 if(!sameTransform(r)||!Number.isFinite(e.clientX)||!Number.isFinite(e.clientY)){cancelContact();return;}
 last={x:Math.max(0,Math.min(65535,Math.round((e.clientX-r.left)/r.width*65535))),y:Math.max(0,Math.min(65535,Math.round((e.clientY-r.top)/r.height*65535)))};
 // Pressure is a raw browser device capability. A mouse is explicitly a
 // synthetic-pressure source; cancellation supplies a loss/resync flag.
 send('pen',{...last,pressure:contact?Math.round((e.pointerType==='pen'?e.pressure:0.5)*4095):0,flags:cancel?10:contact?3:2,tool:e.pointerType==='pen'?1:0});}
// Keyboard input is an ordinary synthetic pen source. It sends the same raw
// samples as a mouse and never draws a host cursor into controller pixels.
let keyboardX=0,keyboardY=0,keyboardDown=false;
function keyboardPoint(contact,cancel=false){send('pen',{x:Math.round(keyboardX*65535/Math.max(1,canvas.width-1)),y:Math.round(keyboardY*65535/Math.max(1,canvas.height-1)),pressure:contact?2047:0,flags:cancel?10:contact?3:2,tool:0});}
function cancelKeyboardPen(){if(keyboardDown){keyboardDown=false;keyboardPoint(false,true);}}
function keyboardPosition(){document.querySelector('#keyboard-pen-status').textContent=`Keyboard pen at ${keyboardX}, ${keyboardY}${keyboardDown?' · contact':''}`;}
function keyboardKey(e){
 const movement={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
 if(movement){e.preventDefault();const step=e.shiftKey?1:e.ctrlKey?100:20;
  keyboardX=Math.max(0,Math.min(canvas.width-1,keyboardX+movement[0]*step));keyboardY=Math.max(0,Math.min(canvas.height-1,keyboardY+movement[1]*step));
  if(keyboardDown)keyboardPoint(true);keyboardPosition();
 }else if(e.key==='Home'){e.preventDefault();cancelKeyboardPen();keyboardX=keyboardY=0;keyboardPosition();
 }else if(e.key===' '){e.preventDefault();if(!e.repeat&&!keyboardDown&&active===null){keyboardDown=true;keyboardPoint(true);keyboardPosition();}
 }else if(e.key==='Insert'){e.preventDefault();if(!e.repeat&&active===null){keyboardDown=!keyboardDown;keyboardPoint(keyboardDown);keyboardPosition();}
 }else if(e.key==='Enter'){e.preventDefault();if(!e.repeat&&!keyboardDown&&active===null){keyboardPoint(true);keyboardPoint(false);}
 }else if(e.key==='Escape'){e.preventDefault();cancelKeyboardPen();keyboardPosition();}
}
function bindPointer(){canvas.tabIndex=0;canvas.onkeydown=keyboardKey;
 canvas.onkeyup=e=>{if(e.key===' '){e.preventDefault();if(keyboardDown){keyboardDown=false;keyboardPoint(false);keyboardPosition();}}};
 canvas.onblur=()=>{cancelKeyboardPen();keyboardPosition();};
 canvas.onpointerdown=e=>{cancelKeyboardPen();if(active!==null)return;const transform=pointerTransform();
 if(transform===null||!Number.isFinite(e.clientX)||!Number.isFinite(e.clientY))return;
 active=e.pointerId;activeTool=e.pointerType==='pen'?1:0;activeTransform=transform;canvas.setPointerCapture(active);point(e,true);};
canvas.onpointermove=e=>{if(e.pointerId===active)point(e,true);};
canvas.onpointerup=e=>{if(e.pointerId===active){point(e,false);active=null;activeTransform=null;}};
canvas.onpointercancel=e=>{if(e.pointerId===active)cancelContact();};
// Capture can disappear independently of pointerup/cancel (for example when
// the browser moves focus). End the raw contact and admit the next gesture.
canvas.onlostpointercapture=e=>{if(e.pointerId===active)cancelContact();};}bindPointer();
function present(m){lastPlane=m;if(m.pixels.length!==m.width*m.height){status.textContent='Invalid controller pixel plane';return;}canvas.width=m.width;canvas.height=m.height;scaleDisplay();
 if(gpu)try{const renderer=device,texture=device.createTexture({size:[m.width,m.height],format:'r8unorm',usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST});
  device.queue.writeTexture({texture},m.pixels,{bytesPerRow:m.width},[m.width,m.height]);const encoder=device.createCommandEncoder();
  const pass=encoder.beginRenderPass({colorAttachments:[{view:gpu.getCurrentTexture().createView(),loadOp:'clear',storeOp:'store'}]});pass.setPipeline(pipeline);
  pass.setBindGroup(0,device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:texture.createView()}]}));pass.draw(3);pass.end();device.queue.submit([encoder.finish()]);device.queue.onSubmittedWorkDone().then(()=>texture.destroy()).catch(()=>{if(device===renderer)fallback();});
 }catch(e){fallback();}
 else if(context){const image=context.createImageData(m.width,m.height);for(let i=0;i<m.pixels.length;i++){const gray=m.pixels[i]*17;image.data[4*i]=image.data[4*i+1]=image.data[4*i+2]=gray;image.data[4*i+3]=255;}context.putImageData(image,0,0);}}
let schoolCursor=0,reviewCursor=0;
const schoolStatus=document.querySelector('#school-status');
function schoolAction(operation,fields={}){send('school',{operation,...fields});schoolStatus.textContent='School '+operation+' pending · local pen and Save remain available';}
document.querySelector('#school-connect').onclick=async()=>{
 const file=document.querySelector('#school-credential').files[0];
 if(!file||file.size>4096){schoolStatus.textContent='Choose the bounded private school pairing file.';return;}
 try{const credential=JSON.parse(await file.text());schoolAction('connect',{credential});}catch(e){schoolStatus.textContent=String(e);}
};
document.querySelector('#school-sample').onclick=()=>schoolAction('sample');
document.querySelector('#school-next').onclick=()=>schoolAction('catalogue',{after:schoolCursor});
document.querySelector('#school-install').onclick=()=>{
 const selected=document.querySelector('#school-course').selectedOptions[0];
 if(!selected){schoolStatus.textContent='Connect and select an enrolled publication first.';return;}
 schoolAction('install',{course:Number(selected.dataset.course),revision:Number(selected.dataset.revision)});
};
for(const operation of ['join','help','feedback','receipts','submit','cancel','disconnect'])document.querySelector('#school-'+operation).onclick=()=>schoolAction(operation);
document.querySelector('#school-reviews').onclick=()=>schoolAction('reviews',{after:0});
document.querySelector('#school-reviews-next').onclick=()=>schoolAction('reviews',{after:reviewCursor});
document.querySelector('#school-review-open').onclick=()=>{
 const id=document.querySelector('#school-review').value;
 if(!id){schoolStatus.textContent='Choose a due review first.';return;}
 schoolAction('review',{id});
};
worker.onmessage=({data:m})=>{
 if(m.type==='closed')document.querySelector('#serial-status').textContent='No running serial transfer.';
 if(m.type==='closed')document.querySelector('#ink-loss-status').textContent='No running guest. Retain an export before recovery.';
 if(m.type==='school'){
  schoolStatus.textContent=m.error?m.error:JSON.stringify(m.result,null,2);
  if(m.result?.courses){schoolCursor=m.result.next;const list=document.querySelector('#school-course');list.replaceChildren();
   for(const course of m.result.courses){const option=document.createElement('option');option.textContent=course.title+' · '+course.course+'/'+course.revision;option.dataset.course=course.course;option.dataset.revision=course.revision;list.append(option);}}
  if(m.result?.reviews){reviewCursor=m.result.next;const list=document.querySelector('#school-review');list.replaceChildren();
   for(const review of m.result.reviews){const option=document.createElement('option');option.value=review.id;option.textContent=review.courseTitle+' · '+review.title+' · '+review.course+'/'+review.edition;list.append(option);}}
 }
 if(m.type==='execution-boundary'){executionBoundary=m;status.textContent=boundaryText().slice(3);}
 if(m.type==='error'){stopPcm('Machine bridge error.');status.textContent=m.error+boundaryText();}
 if(m.type==='closed'){document.querySelector('#school-installation').textContent='No running guest.';document.querySelector('#school-outgoing').textContent='No running guest.';document.querySelector('#school-status').textContent='School disconnected. Saved local work remains in the medium.';stopPcm('Machine closed.');beginSelection();selectionMachineName=null;displayedMediumName=null;document.querySelector('#course-result').textContent='No running guest. Open runs recovery from backing bytes.';document.querySelector('#course-admission').textContent='';document.querySelector('#retry-private').disabled=true;document.querySelector('#backing-status').textContent='No active medium. The displayed name is retained for reopen.';commitStatus.textContent='No running guest. Open runs recovery from backing bytes.';sessionMode.disabled=false;status.textContent='Machine closed. Reopen runs guest recovery from actual backing bytes.';}
 if(m.type==='imported')status.textContent='Durable medium imported. Open it to run real cold guest recovery.';
 if(m.type==='course-admission')document.querySelector('#course-admission').textContent=m.error?`Admitted ${m.accepted} of ${m.total} raw events; rejected remainder: ${m.error}. The accepted prefix remains queued. Close and cold-open backing before retrying.`:`Admitted ${m.bytes} package bytes to the guest. See the guest installation result below.`;
 if(m.type==='raw-admission')document.querySelector('#raw-result').textContent=m.error?`Accepted ${m.accepted} of ${m.total} events; rejected remainder: ${m.error}`:`Admitted ${m.accepted} raw events.`;
 if(m.type==='state'){const reported=m.guestCommit??null;
  const loss=m.guestInkLoss;
  document.querySelector('#ink-loss-status').textContent=loss==null?'No input loss reported in this guest launch.':loss.state==='malformed'?
   'Input loss report invalid; inspect the retained work.':
   `Input loss: ${loss.discarded} buffered samples discarded (${loss.cumulative} total); reason ${loss.reason}. Saved covers retained work. Missing controller samples may be additional and uncounted.`;
  const serial=m.state.uart_ingress;
  document.querySelector('#serial-status').textContent=serial===undefined?'Serial transfer status unavailable.':
   `Serial bytes: ${serial.delivered} delivered, ${serial.pending} queued, ${serial.canceled} cancelled of ${serial.accepted} accepted${serial.blocked?' · waiting for guest receiver':''}. Byte delivery is not an installation receipt.`;
  const course=m.guestCourse??null;
  document.querySelector('#course-result').textContent=course===null?'No installation result observed in this guest launch.':course.state==='installed'?`Guest reports installed package ${course.identity}, edition ${course.edition}, durable sequence ${course.sequence}.`:`Guest reports installation failure (${course.status}) for package ${course.identity}, edition ${course.edition}.`;
  document.querySelector('#school-installation').textContent=document.querySelector('#course-result').textContent;
  const queue=m.guestQueue;
  document.querySelector('#school-outgoing').textContent=queue===undefined||queue===null?'No committed outgoing work observed in this launch.':queue.state==='failed'?`Guest outgoing queue failed (${queue.code}); saved paper remains available.`:queue.state==='pending'?`Guest committed outgoing work ${queue.queue}; awaiting school acknowledgement.`:`Guest reports outgoing work ${queue.queue} ${queue.state}${queue.observation==='restored-pointer-read'?' after cold recovery':''}.`;
  const backing=m.backingMedium;
  if(backing&&typeof backing.name==='string'){
   if(backing.name!==selectionMachineName){beginSelection();selectionMachineName=backing.name;}
   document.querySelector('#retry-private').disabled=backing.ready;
   document.querySelector('#backing-status').textContent=backing.ready?`Active ${backing.private?'private ':''}medium: ${backing.name}. Close/Open runs guest recovery from this backing.`:`Private backing is incomplete. Keep this machine open to retry binding or export its bytes.`;
   // Adopt a newly opened/bound medium once. Later periodic observations do
   // not overwrite a name the user is preparing for the next open/import.
   if(backing.ready&&backing.name!==displayedMediumName){document.querySelector('#medium').value=backing.name;displayedMediumName=backing.name;}
  }
  commitStatus.textContent=reported===null?'No save result observed in this guest launch.':reported.state==='saved'?`Guest reports Saved ${reported.value} · page ${reported.page} · namespace ${reported.namespace}`:reported.state==='pending'?`Guest save pending ${reported.value} · page ${reported.page} · namespace ${reported.namespace}`:`Guest save failed (${reported.value}) · page ${reported.page} · namespace ${reported.namespace}`;
  if(m.mode){sessionMode.value=m.mode;sessionMode.disabled=true;modeControls();}status.textContent=`Cycle ${m.state.cycle} · ${m.guestFault?'Notebook fault reported by kernel (cause0x'+m.guestFault.cause+', exit0x'+m.guestFault.exitCode+'). Export backing bytes before recovery.':m.readyAt?'Guest Ready observed at '+m.readyAt.cycle:m.guestObservation==='continuation'?'Restored continuation; Ready not observed':'Booting'} · ${m.running?'running':'paused'+(m.pauseReason?' ('+m.pauseReason+')':'')} · ${Math.round(m.heapBytes/1048576)} MiB Wasm heap · ${m.timing.elapsedSeconds.toFixed(1)} s elapsed · ${m.timing.simulationCallSeconds.toFixed(1)} s simulation calls (${m.timing.backingCallSecondsDuringRun.toFixed(1)} s backing)`;
  document.querySelector('#inspection').textContent=JSON.stringify(m,null,2);}
 if(m.type==='pcm')presentPcm(m.pcm);
 if(m.type==='pcm-stop')stopPcm(m.reason??'Controller playback stopped.',false);
 if(m.type==='panel')present(m);
 if(m.type==='uart')document.querySelector('#uart').textContent=m.text;
 if(m.type==='export')download(m.name,m.bytes);
};
// Presentation availability never gates raw input, storage controls or CPU
// scheduling. Rejected or indefinitely pending GPU setup leaves 2D active.
initializeGPU().catch(()=>{if(gpu)fallback();});

// Speaker embodiment consumes controller-produced PCM only. No text-to-speech.
// Sink queue is bounded to20ms. UI mute stops every queued source immediately;
// this is a host sink receipt, independent of guest cancellation and audibility.
let pcmContext=null,pcmAllowed=false,pcmNext=0,pcmLastTick=null,pcmLastPosition=null,pcmSources=new Set(),pcmDrops=0;
const pcmStatus=document.querySelector('#pcm-status');
document.querySelector('#pcm-enable').onclick=async()=>{try{pcmContext??=new AudioContext();await pcmContext.resume();pcmAllowed=pcmContext.state==='running';pcmStatus.textContent=pcmAllowed?'Guest PCM speaker presentation enabled. Physical audibility and bone transducer onset remain unmeasured.':'Audio context unavailable.';}catch(e){pcmAllowed=false;pcmStatus.textContent=String(e);}};
function stopPcm(reason,withdrawPermission=true){if(withdrawPermission)pcmAllowed=false;for(const source of pcmSources)try{source.stop();}catch{}pcmSources.clear();pcmNext=0;pcmLastTick=null;pcmLastPosition=null;pcmStatus.textContent=reason+' Queued sink samples cancelled; emitted samples cannot be undone. Guest action cancellation is a separate receipt.';}
document.querySelector('#pcm-mute').onclick=()=>stopPcm('Speaker presentation muted.');
document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelContact();stopPcm('Page hidden.');}});
function presentPcm(pcm){if(pcm.format!=='mono-s16le-low16/1'||pcm.clock_hz!==100000000||!Array.isArray(pcm.samples)||pcm.samples.length>256){stopPcm('Unsupported PCM egress.');return;}
 if(!pcmAllowed||!pcmContext||pcmContext.state!=='running'){pcmDrops+=pcm.samples.length;return;}
 const groups=[];let group=null;
 for(const row of pcm.samples){const tick=BigInt(row[0]),position=BigInt(row[1]);if(!Number.isInteger(row[2])||row[2]<-32768||row[2]>32767){stopPcm('Malformed PCM waveform.');return;}
  const period=pcmLastTick===null?null:tick-pcmLastTick;
  if(period===null||period<=0n||pcmLastPosition+1n!==position){pcmLastTick=tick;pcmLastPosition=position;pcmDrops++;continue;}
  const rate=100000000/Number(period);if(rate<3000||rate>384000){pcmDrops++;pcmLastTick=tick;pcmLastPosition=position;continue;}
  if(!group||group.period!==period){group={period,rate,samples:[]};groups.push(group);}group.samples.push(row[2]);pcmLastTick=tick;pcmLastPosition=position;
 }
 for(const group of groups){const now=pcmContext.currentTime;pcmNext=Math.max(pcmNext,now);const seconds=group.samples.length/group.rate;if(pcmNext-now+seconds>0.020){pcmDrops+=group.samples.length;continue;}
  const buffer=pcmContext.createBuffer(1,group.samples.length,group.rate),samples=buffer.getChannelData(0);for(let i=0;i<samples.length;i++)samples[i]=group.samples[i]/32768;
  const source=pcmContext.createBufferSource();source.buffer=buffer;source.connect(pcmContext.destination);pcmSources.add(source);source.onended=()=>pcmSources.delete(source);source.start(pcmNext);pcmNext+=seconds;
 }
 pcmStatus.textContent=`Modeled PCM speaker sink; digital egress dropped ${pcm.dropped}, presentation dropped ${pcmDrops}; at most20ms queued. Physical onset unmeasured.`;
}

for(const id of ['warm','cold','power'])document.querySelector('#'+id).addEventListener('click',()=>stopPcm('Machine output epoch changed.'));
