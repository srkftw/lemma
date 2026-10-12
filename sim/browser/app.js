// SPDX-License-Identifier: Apache-2.0
const worker=new Worker('./worker.js',{type:'module'}),status=document.querySelector('#status');
let canvas=document.querySelector('canvas'),lastPlane=null;
let active=null,last={x:0,y:0};
// WebGPU only presents controller-produced Gray4 bytes. Device loss selects
// a fresh 2D canvas presenting the identical plane; it never fabricates ink.
let context,gpu,pipeline,device;
if(navigator.gpu)try{const adapter=await navigator.gpu.requestAdapter();if(adapter){device=await adapter.requestDevice();gpu=canvas.getContext('webgpu');
 const format=navigator.gpu.getPreferredCanvasFormat();gpu.configure({device,format,alphaMode:'opaque'});
 const shader=device.createShaderModule({code:`@group(0) @binding(0) var t:texture_2d<f32>;
 @vertex fn v(@builtin(vertex_index) i:u32)->@builtin(position) vec4f{var p=array<vec2f,3>(vec2f(-1,-1),vec2f(3,-1),vec2f(-1,3));return vec4f(p[i],0,1);}
 @fragment fn f(@builtin(position) p:vec4f)->@location(0) vec4f{let g=textureLoad(t,vec2i(p.xy),0).r*17;return vec4f(g,g,g,1);}`});
 pipeline=device.createRenderPipeline({layout:'auto',vertex:{module:shader,entryPoint:'v'},fragment:{module:shader,entryPoint:'f',targets:[{format}]},primitive:{topology:'triangle-list'}});
 device.lost.then(()=>{gpu=null;const next=canvas.cloneNode(false);canvas.replaceWith(next);canvas=next;context=canvas.getContext('2d');bindPointer();if(lastPlane)present(lastPlane);status.textContent='Display device lost; controller pixels now use the 2D fallback.';});}}
catch(e){gpu=null;}if(!gpu)context=canvas.getContext('2d');
function send(action,rest={},transfer=[]){worker.postMessage({action,...rest},transfer);}
function download(name,bytes){const u=URL.createObjectURL(new Blob([bytes])),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
document.querySelector('#open').onclick=()=>send('open',{name:document.querySelector('#medium').value});
document.querySelector('#initialize').onclick=()=>send('open',{name:document.querySelector('#medium').value,initialize:true});
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>send(b.dataset.action));
document.querySelector('#admit-raw').onclick=()=>send('raw',{row:document.querySelector('#raw-event').value});
document.querySelector('#warm').onclick=()=>send('reset',{cold:false});document.querySelector('#cold').onclick=()=>send('reset',{cold:true});
document.querySelector('#restore').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>805306368){status.textContent='Checkpoint exceeds the machine bound';return;}const bytes=await file.arrayBuffer();send('restore',{bytes},[bytes]);};
document.querySelector('#pending-outcomes').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>268435456){status.textContent='Outcome tape exceeds the machine bound';return;}const bytes=await file.arrayBuffer();send('outcomes',{bytes},[bytes]);};
document.querySelector('#import').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size!==268435456){status.textContent='Expected a 256 MiB raw medium';return;}const bytes=await file.arrayBuffer();send('import',{name:document.querySelector('#medium').value,bytes},[bytes]);};
document.querySelector('#replay').onclick=async()=>{try{
 const c=document.querySelector('#replay-checkpoint').files[0],io=document.querySelector('#replay-io').files[0],raw=document.querySelector('#replay-events').files[0];
 if(!c||!io||!raw)throw Error('Select checkpoint, backing outcomes and raw event capture');
 if(c.size>805306368||io.size>268435456||raw.size>268435456)throw Error('Replay input exceeds its bound');
 const checkpoint=await c.arrayBuffer(),replayLog=await io.arrayBuffer(),events=JSON.parse(await raw.text());
 send('replay',{name:document.querySelector('#medium').value,checkpoint,replayLog,events},[checkpoint,replayLog]);
 }catch(e){status.textContent=String(e);}};
const power=document.querySelector('#power');power.onpointerdown=e=>{power.setPointerCapture(e.pointerId);send('button',{level:1});};power.onpointerup=power.onpointercancel=()=>send('button',{level:0});
function point(e,contact,cancel=false){const r=canvas.getBoundingClientRect();
 last={x:Math.max(0,Math.min(65535,Math.round((e.clientX-r.left)/r.width*65535))),y:Math.max(0,Math.min(65535,Math.round((e.clientY-r.top)/r.height*65535)))};
 // Pressure is a raw browser device capability. A mouse is explicitly a
 // synthetic-pressure source; cancellation supplies a loss/resync flag.
 send('pen',{...last,pressure:contact?Math.round((e.pointerType==='pen'?e.pressure:0.5)*4095):0,flags:cancel?10:contact?3:2,tool:e.pointerType==='pen'?1:0});}
function bindPointer(){canvas.onpointerdown=e=>{if(active!==null)return;active=e.pointerId;canvas.setPointerCapture(active);point(e,true);};
canvas.onpointermove=e=>{if(e.pointerId===active)point(e,true);};
canvas.onpointerup=e=>{if(e.pointerId===active){point(e,false);active=null;}};
canvas.onpointercancel=e=>{if(e.pointerId===active){point(e,false,true);active=null;}};}bindPointer();
function present(m){lastPlane=m;if(m.pixels.length!==m.width*m.height){status.textContent='Invalid controller pixel plane';return;}canvas.width=m.width;canvas.height=m.height;
 if(gpu){const texture=device.createTexture({size:[m.width,m.height],format:'r8unorm',usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST});
  device.queue.writeTexture({texture},m.pixels,{bytesPerRow:m.width},[m.width,m.height]);const encoder=device.createCommandEncoder();
  const pass=encoder.beginRenderPass({colorAttachments:[{view:gpu.getCurrentTexture().createView(),loadOp:'clear',storeOp:'store'}]});pass.setPipeline(pipeline);
  pass.setBindGroup(0,device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:texture.createView()}]}));pass.draw(3);pass.end();device.queue.submit([encoder.finish()]);device.queue.onSubmittedWorkDone().then(()=>texture.destroy());
 }else if(context){const image=context.createImageData(m.width,m.height);for(let i=0;i<m.pixels.length;i++){const gray=m.pixels[i]*17;image.data[4*i]=image.data[4*i+1]=image.data[4*i+2]=gray;image.data[4*i+3]=255;}context.putImageData(image,0,0);}}
worker.onmessage=({data:m})=>{
 if(m.type==='error')status.textContent=m.error;
 if(m.type==='closed')status.textContent='Machine closed. Reopen runs guest recovery from actual backing bytes.';
 if(m.type==='imported')status.textContent='Durable medium imported. Open it to run real cold guest recovery.';
 if(m.type==='state'){status.textContent=`Cycle ${m.state.cycle} · ${m.readyAt?'Guest Ready observed at '+m.readyAt.cycle:m.guestObservation==='continuation'?'Restored continuation; Ready not observed':'Booting'} · ${m.running?'running':'paused'} · ${Math.round(m.heapBytes/1048576)} MiB Wasm heap · ${m.hostSeconds.toFixed(1)} s host`;
  document.querySelector('#inspection').textContent=JSON.stringify(m,null,2);}
 if(m.type==='panel')present(m);
 if(m.type==='uart')document.querySelector('#uart').textContent=m.text;
 if(m.type==='export')download(m.name,m.bytes);
};
