// SPDX-License-Identifier: Apache-2.0
// Outer lifecycle transport. Terminating a runtime releases its pthread tree
// and exclusive OPFS handle. Never interpret guest durable bytes here.
let runtime=null,opening=null,closing=false,pendingImported=null;
function spawn(message){
 runtime=new Worker('./runtime_worker.mjs',{type:'module'});
 runtime.onmessage=({data})=>{
  if(data.type==='imported'){pendingImported=data;return;}
  if(data.type==='runtime-closed'){
   runtime.terminate();runtime=null;
   if(pendingImported){postMessage(pendingImported);pendingImported=null;}
   if(closing){closing=false;opening=null;postMessage({type:'closed'});}
   else if(data.nextNotebook){const next={...opening,initialize:false};setTimeout(()=>spawn(next),10);}
   return;
  }
  postMessage(data,data.type==='panel'?[data.pixels.buffer]:data.type==='export'?[data.bytes.buffer]:[]);
 };
 runtime.onerror=e=>postMessage({type:'error',error:'QEMU worker lost: '+e.message});
 runtime.postMessage(message);
}
onmessage=({data})=>{
 if(data.action==='open'){
  if(runtime){postMessage({type:'error',error:'Close the current machine first'});return;}
  opening={...data};spawn(data);return;
 }
 if(data.action==='import'){
  if(runtime){postMessage({type:'error',error:'Close the current machine first'});return;}
  spawn(data);return;
 }
 if(!runtime){postMessage({type:'error',error:'Open a machine first'});return;}
 if(data.action==='close')closing=true;
 runtime.postMessage(data);
};
