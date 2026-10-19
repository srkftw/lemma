// SPDX-License-Identifier: Apache-2.0
// Host transport/presentation only. Every instruction and device runs in QEMU.
import createQemu from './qemu-system-riscv64.js';
import {Control} from './control.mjs';
import {admitUart} from './uart_arrivals.mjs';
import {attachOpfsFile} from './opfs_backing.mjs';
import {guestRecord,guestPageReady,guestCommitState,guestCourseInstallState} from './guest_records.js';
import {courseInstallFrame,courseSchoolFrames} from './course_transport.js';
import {RunBudget,uint64} from './run_budget.js';
import {PcmEgress} from './pcm_egress.mjs';
import {SchoolTransport,guestSchoolAsk,schoolPackage,guestSchoolSubmission,guestSchoolCapability,guestSchoolQueueState} from './school_transport.js';
const school=new SchoolTransport();let schoolMachineEpoch=0;
const contract='lemma-browser-session-modes/2';
const ordinary=new Set(['open','import','pause','resume','pen','button','reset','export','export-panel','close','school']);
const developer=new Set(['run','raw','raw-batch','course-install','inspect','events']);
let core,control,handle,manifest,backing,loaded=false,running=false,mode='student',mediumName=null,initializing=false;
let serial=Promise.resolve(),timer=null,budget=null,pauseReason=null,started=0,readyAt=null,loops=0,panelSequence=null,guestStart=0,capture=[],coursePartial=false,interruptEpoch=0;
const timing={runSeconds:0},sleep=ms=>new Promise(r=>setTimeout(r,ms));
const exactJson=text=>JSON.parse(text.replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(s,n)=>n===undefined?s:JSON.stringify(n)));
let heapBytes=null,uartPaced=false;
const egress=new PcmEgress();
async function pcm(){
 const result=await control.request('lemma-waveform');
 if(result.format!=='LMPCM001/mono-s16-low16/1'||result.path!=='/audio.bin'||result.source_clock_hz!==100000000)throw Error('Unsupported actual waveform');
 const actual=exactJson(await control.get('multimodal-state')),stream=actual.streams?.[8];
 if(!stream||stream.id!=='8'||stream.consumed!==result.consumed||stream.epoch!==result.stream_epoch)throw Error('Actual playback observations differ');
 egress.poll(core.FS,core.FS.stat('/audio.bin').size,stream,message=>postMessage(message));
}
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
function enqueue(f){const next=serial.then(f);serial=next.catch(async e=>{pause('error');let stopError=null;if(loaded&&control)try{await stopped();}catch(error){stopError=String(error);}postMessage({type:'error',error:String(e),stopError});if(stopError||!loaded)postMessage({type:'runtime-closed'});});return next;}
function pause(reason){running=false;pauseReason=reason;if(timer!==null){clearTimeout(timer);timer=null;}}
function schedule(){if(running&&timer===null)timer=setTimeout(()=>{timer=null;enqueue(step);},0);}
function uart(){try{return core.FS.readFile('/uart.bin');}catch{return new Uint8Array();}}
async function inspect(full=false){
 const clock=await control.request('lemma-clock');
 for(const name of ['paper_completed','paper_accepted','paper_status'])if(typeof clock[name]!=='string'||!/^(0|[1-9][0-9]*)$/.test(clock[name]))throw Error('Missing pure controller observation:'+name);
 if(typeof clock.paper_power!=='boolean')throw Error('Missing actual panel power observation');
 if(!Number.isSafeInteger(clock.wasm_heap_bytes)||clock.wasm_heap_bytes<2147483648)throw Error('Missing actual Wasm heap measurement');heapBytes=clock.wasm_heap_bytes;
 const cycle=(BigInt(clock.virtual_ns)+9n)/10n;
 const state={cycle:String(cycle),ticks:clock.mtime_ticks,virtual_ns:clock.virtual_ns,panel_completed:clock.paper_completed,paper_busy:String(BigInt(clock.paper_status)&1n),panel_power:clock.paper_power?'1':'0',isolated_medium:false,backend:'qemu-tci-wasm64/1',timingScope:'instruction/virtual-timer boundary; not RTL processor-cycle parity'};
 if(full){state.paper=exactJson(await control.get('device-state'));state.storage=exactJson(await control.get('storage-state','/machine/lemma-block'));state.power=exactJson(await control.get('power-state'));state.uart_ingress=exactJson(await control.get('raw-uart-state'));state.fullInspectionVirtualNs=clock.virtual_ns;}
 if(readyAt===null&&guestPageReady(uart(),guestStart,{accepted:clock.paper_accepted,completed:clock.paper_completed}))readyAt={cycle:state.cycle,hostSeconds:(performance.now()-started)/1000};
 return state;
}
async function sendState(state){
 if(state===undefined)state=await inspect();
 postMessage({type:'state',state,mode,modeContract:contract,running,guestObservation:'boot',guestCommit:guestCommitState(uart(),guestStart),guestCourse:guestCourseInstallState(uart(),guestStart),guestQueue:guestSchoolQueueState(uart(),guestStart),backingMedium:{name:mediumName,private:false,ready:true},backingMetrics:backing.metrics,controlMetrics:control.metrics,pcmEgress:egress.inspect(),heapBytes,readyAt,hostSeconds:(performance.now()-started)/1000,pauseReason,budget:budget?.inspection()??null,timing:{scope:'opened-worker-session',elapsedSeconds:(performance.now()-started)/1000,simulationCallSeconds:timing.runSeconds,backingCallSeconds:0,backingCallSecondsDuringRun:0,backingTimingAvailable:false}});
}
async function panel(force=false,observation=null){
 if(!force){observation??=await inspect();if(panelSequence===observation.panel_completed)return;}
 const result=await control.request('lemma-panel');
 if(result.format!=='gray4-high-nibble-first/1'||result.width!==manifest.width||result.height!==manifest.height||result.stride!==Math.ceil(result.width/2)||result.bytes!==result.stride*result.height)throw Error('Actual controller panel format differs');
 const packed=core.FS.readFile(result.path),pixels=new Uint8Array(result.width*result.height);
 if(packed.length!==result.bytes)throw Error('Actual controller panel extent differs');
 for(let y=0;y<result.height;y++)for(let x=0;x<result.width;x++){const value=packed[y*result.stride+(x>>1)];pixels[y*result.width+x]=(x&1)?value&15:value>>4;}
 panelSequence=String(result.completed);postMessage({type:'panel',pixels,width:result.width,height:result.height,captureNs:result.capture_ns,completed:result.completed},[pixels.buffer]);
}
async function artifact(item){if(!item||typeof item.path!=='string'||!item.sha256)throw Error('Missing inventoried artifact');const r=await fetch(item.path);if(!r.ok)throw Error('Artifact unavailable:'+item.path);const bytes=new Uint8Array(await r.arrayBuffer());if(await sha(bytes)!==item.sha256)throw Error('Artifact hash differs:'+item.path);return bytes;}
async function openMedium(name,initialize){
 if(typeof name!=='string'||!/^[a-zA-Z0-9_-]{1,64}$/.test(name))throw Error('Invalid medium name');
 const root=await navigator.storage.getDirectory();
 if(initialize){try{await root.getFileHandle(name+'.raw');throw Error('Medium already exists; initialization refuses to format it');}catch(e){if(e.name!=='NotFoundError')throw e;}}
 const file=await root.getFileHandle(name+'.raw',{create:initialize});
 // A terminated predecessor releases its exclusive handle asynchronously.
 const until=performance.now()+1000;let next;
 while(!next){try{next=await file.createSyncAccessHandle();}catch(e){if(e.name!=='NoModificationAllowedError'||performance.now()>=until)throw e;await sleep(10);}}
 try{if(initialize){next.truncate(268435456);next.flush();}if(next.getSize()!==268435456)throw Error('Expected a256MiB medium');return next;}catch(e){next.close();throw e;}
}
async function load(m){
 if(loaded)throw Error('Close this machine first');if(!['student','developer','laboratory'].includes(m.mode??'student'))throw Error('Unknown session mode');mode=m.mode??'student';
 if(m.initialize!==undefined&&typeof m.initialize!=='boolean')throw Error('Initialize must be Boolean');
 if(m.paused!==undefined&&typeof m.paused!=='boolean')throw Error('Open paused must be Boolean');
 const response=await fetch('./bundle.json');if(!response.ok)throw Error('Bundle unavailable');manifest=await response.json();if(manifest.schema!=='lemmasim-browser-qemu-tci/1'||manifest.execution_backend!=='qemu-tci-wasm64/1'||manifest.session_control_contract!==contract||manifest.profile!=='lemma-silicon-dev/0.14.0')throw Error('Unsupported admitted QEMU Wasm bundle');
 handle=await openMedium(m.name,!!m.initialize);mediumName=m.name;
 const workload=manifest.workloads[m.initialize?'initializer':'notebook'],elf=await artifact(workload.image),dtb=await artifact(workload.dtb),wasm=await artifact(manifest.runtime.wasm);
 const logs=[];started=performance.now();
 core=await createQemu({arguments:['-machine','lemma-silicon-fast','-cpu','rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0','-m','128M','-smp','1','-bios','none','-kernel','/image.elf','-dtb','/machine.dtb','-display','none','-monitor','none','-serial','file:/uart.bin','-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031','-global','lemma-fast-block.medium=/medium.raw','-global','lemma-paper-pen.multimodal-audio-output=/audio.bin'],preRun:[module=>{module.FS.writeFile('/image.elf',elf);module.FS.writeFile('/machine.dtb',dtb);backing=attachOpfsFile(module,'/medium.raw',handle);}],print:t=>{if(logs.length<256)logs.push(String(t));},printErr:t=>{if(logs.length<256)logs.push(String(t));},onAbort:t=>postMessage({type:'error',error:'QEMU abort:'+t,logs})});
 control=new Control(core);await control.ready();if(await control.get('raw-uart-version')!=='lemma-raw-uart/1')throw Error('UART raw transport absent');await control.set('enable-raw-uart','lemma-raw-uart/1');const properties=await control.request('qom-list',{path:'/machine/lemma-hardware'});uartPaced=properties.some(p=>p.name==='raw-uart-paced-version')&&await control.get('raw-uart-paced-version')==='lemma-raw-uart-paced/1';
 loaded=true;initializing=!!m.initialize;guestStart=uart().length;running=!m.paused;pauseReason=m.paused?'opened-paused':null;
 await sendState();await panel(true);schedule();
}
async function stopped(){if((await control.request('query-status')).running)await control.request('stop');}
async function input(m){
 await stopped();const clock=await control.request('lemma-clock'),delivery=String((BigInt(clock.virtual_ns)+9n)/10n*10n);
 if(m.action==='pen'){
  const values=[m.x,m.y,m.pressure,m.flags,m.tool];if(!values.every(Number.isSafeInteger)||m.x<0||m.x>65535||m.y<0||m.y>65535||m.pressure<0||m.pressure>65535||m.flags<0||m.flags>31||m.tool<0||m.tool>65535)throw Error('Invalid raw pen fields');
  await control.set('external-event',`${delivery} ${clock.mtime_ticks} ${m.x} ${m.y} ${m.pressure} ${m.flags} ${m.tool} 0`);
 }else{if(![0,1].includes(m.level))throw Error('Invalid button level');await control.set('external-button',`${delivery} ${m.level}`);}
 capture.push({ingress:'browser-pointer/1',pressureOrigin:m.tool===0?'SYNTHETIC':'EXTERNAL_DEVICE_UNQUALIFIED',hostArrivalMs:m.hostArrivalMs,captureClock:clock,input:m});
}
async function raw(row){
 if(typeof row!=='string'||row.length>256)throw Error('Raw event exceeds256 characters');const f=row.trim().split(/\s+/),clock=await control.request('lemma-clock'),cycle=(BigInt(clock.virtual_ns)+9n)/10n;
 if(f[0]==='now')f[0]=String(cycle);const c=uint64(f[0]);if(c<cycle)throw Error('Raw event is stale');const delivery=c*10n;
 if(f[1]==='uart'&&f.length===3&&/^(?:[a-fA-F0-9]{2}){1,112}$/.test(f[2]))await control.set('external-uart',`${delivery} ${f[2]}`);
 else if(f[1]==='multimodal'&&f.length===6&&c===cycle&&f.slice(2).every(v=>/^(0|[1-9][0-9]{0,9})$/.test(v)))await control.set('multimodal-stimulus',f.slice(2).join(' '));
 else if(f[1]==='pen'&&f.length===9){if(f[2]==='now')f[2]=clock.mtime_ticks;if(!f.slice(2).every(v=>/^(0|[1-9][0-9]{0,19})$/.test(v)))throw Error('Invalid raw pen fields');await control.set('external-event',[String(delivery),...f.slice(2)].join(' '));}
 else if(f[1]==='button'&&f.length===3&&['0','1'].includes(f[2]))await control.set('external-button',`${delivery} ${f[2]}`);
 else throw Error('Unsupported raw event for this profile');capture.push(f.join(' '));
}
async function step(){
 if(!running)return;
 if(budget?.hostExpired(performance.now())){pause('host-limit');await stopped();await panel(true);await sendState();return;}
 const entryEpoch=interruptEpoch,before=await inspect();if(entryEpoch!==interruptEpoch)return;if(budget?.stopOnReady&&readyAt!==null){pause('guest-ready');await sendState(before);return;}
 if(budget?.panelCompleted(before)){pause('panel-complete');await sendState(before);return;}
 const quantum=budget?(budget.remaining<10000000n?budget.remaining:10000000n):10000000n;
 if(quantum===0n){pause('cycle-limit');await sendState(before);return;}
 const target=(BigInt(before.cycle)+quantum)*10n-7n,start=performance.now();
 await control.set('run-until',String(target));if(entryEpoch!==interruptEpoch)return;await control.request('cont');
 while((await control.request('query-status')).running){if(budget?.hostExpired(performance.now())){pause('host-limit');await stopped();break;}if(performance.now()-start>60000){await stopped();const observed=await inspect(true);postMessage({type:'execution-boundary',contract:'lemma-tci-quantum-observation/1',result:'Original60s execution quantum deadline',before,targetVirtualNs:String(target),observed,elapsedSeconds:(performance.now()-start)/1000});throw Error('Original60s execution quantum deadline');}await sleep(5);}
 timing.runSeconds+=(performance.now()-start)/1000;loops++;
 const after=await inspect();if(BigInt(after.cycle)<BigInt(before.cycle)||(after.cycle===before.cycle&&entryEpoch===interruptEpoch))throw Error('Actual guest made no virtual-clock progress');
 if(budget)budget.observe(after.cycle,quantum);
 if(initializing&&guestRecord(uart(),guestStart,'000000000000041f')){pause('initializer-complete');await sendState(after);postMessage({type:'runtime-closed',nextNotebook:true,backingMetrics:backing.metrics});return;}
 if(budget?.remaining===0n)pause('cycle-limit');else if(budget?.stopOnReady&&readyAt!==null)pause('guest-ready');else if(budget?.panelCompleted(after))pause('panel-complete');
 await pcm();await panel(false,after);if(loops%5===0||!running)await sendState(after);schedule();
}
async function schoolActivity(message){
 if(!loaded||manifest.school_service_contract!=='lemma-school-browser-service/1')throw Error('Open a school-capable machine first');
 const epoch=schoolMachineEpoch;
 let result;
 if(message.operation==='sample'){
  if(!manifest.sample_course)throw Error('This bundle has no compiled sample');
  const bytes=await artifact(manifest.sample_course);
  result={package_hex:Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(''),sample:true};
 }else result=await school.operation(message,()=>guestSchoolAsk(uart(),guestStart),()=>guestSchoolSubmission(uart(),guestStart));
 if(epoch!==schoolMachineEpoch)throw Error('Machine changed while school request was pending');
 await enqueue(async()=>{
  if(epoch!==schoolMachineEpoch)throw Error('Machine changed before school response admission');
  if(result.package_hex!==undefined||result.ack_bytes!==undefined){
   if(coursePartial)throw Error('Cold-open before retrying partial course input');
   const wasRunning=running;pause('school-input');await stopped();
   const transaction=(BigInt(crypto.getRandomValues(new Uint32Array(1))[0])+1n).toString(),frame=result.ack_bytes??courseSchoolFrames(schoolPackage(result),transaction,guestSchoolCapability(uart(),guestStart)!==null,result.node??0),clock=await control.request('lemma-clock'),base=(BigInt(clock.virtual_ns)+9n)/10n*10n;
   let accepted=0;
   // Reduced10KB/s serial input has one actual arrival per100us.
   // The additive queue API batches admission without making FIFO bursts.
   let arrival;try{arrival=await admitUart(control,frame,base,uartPaced,n=>{accepted=n;});postMessage({type:'uart-arrival-admission',arrival});}
   catch(e){coursePartial=accepted>0;throw Error('School transfer admitted '+accepted+' of '+frame.length+' bytes; cold-open before retry: '+e);}
   if(wasRunning){running=true;pauseReason=null;schedule();}await sendState();
   if(result.decision)school.command({op:'delivery',decision:result.decision,stage:'transport-admitted',receipt:{transport:'lemma-school-browser-service/1',transaction}}).catch(e=>postMessage({type:'school',operation:'delivery',error:String(e)}));
  }
  const {package_hex,ack_bytes,...view}=result;postMessage({type:'school',operation:message.operation,result:view});
 });
}
onmessage=({data:m})=>{
 // Capability-mode rejection precedes scheduling, backing or machine mutation.
 const opening=m?.action==='open'||m?.action==='import',chosen=opening?(m.mode??'student'):mode;
 if(!m||typeof m.action!=='string'||!['student','developer','laboratory'].includes(chosen)||(!opening&&m.mode!==undefined)||(!ordinary.has(m.action)&&!(chosen!=='student'&&developer.has(m.action)))){postMessage({type:'error',error:'Unsupported action or session capability'});return;}
 m={...m,hostArrivalMs:performance.now()};
 if(m.action==='school'){schoolActivity(m).catch(e=>postMessage({type:'school',operation:m.operation,error:String(e)}));return;}
 // Input/control can interrupt a running quantum through real QMP stop. It
 // does not wait behind the virtual-time budget or fabricate guest progress.
 if(loaded&&control&&['pen','button','pause','close','reset'].includes(m.action)){
  if(['pause','close','reset'].includes(m.action))postMessage({type:'pcm-stop',reason:'Machine presentation paused or output epoch changed',egress:egress.inspect()});
  interruptEpoch++;control.request('stop').catch(e=>postMessage({type:'error',error:'Actual interrupt request failed:'+e}));
 }
 enqueue(async()=>{
  if(m.action==='open'){school.disconnect();schoolMachineEpoch++;await load(m);return;}
  if(m.action==='import'){if(loaded)throw Error('Close the machine first');if(!(m.bytes instanceof ArrayBuffer))throw Error('Import requires opaque ArrayBuffer bytes');const bytes=new Uint8Array(m.bytes);if(bytes.length!==268435456)throw Error('Expected a256MiB raw medium');const expected=await sha(bytes),file=await openMedium(m.name,true);let zeroBytes=0,copiedBytes=0;try{for(let i=0;i<bytes.length;i+=1048576){const chunk=bytes.subarray(i,i+1048576);if(chunk.some(value=>value!==0)){if(file.write(chunk,{at:i})!==chunk.length)throw Error('Partial import');copiedBytes+=chunk.length;}else zeroBytes+=chunk.length;}file.flush();const observed=new Uint8Array(bytes.length);for(let i=0;i<observed.length;i+=1048576)if(file.read(observed.subarray(i,i+1048576),{at:i})!==1048576)throw Error('Partial import readback');if(await sha(observed)!==expected)throw Error('Opaque import readback differs');}finally{file.close();}postMessage({type:'imported',sha256:expected,copiedBytes,zeroBytes,fullReadback:true});postMessage({type:'runtime-closed'});return;}
  if(!loaded){if(m.action==='close'){postMessage({type:'runtime-closed'});return;}throw Error('Machine is not open');}
  if(m.action==='pause'){pause('user');await stopped();await sendState();}
  else if(m.action==='resume'){budget=null;running=true;pauseReason=null;schedule();}
  else if(m.action==='run'){if(m.stopOnPanel!==undefined&&typeof m.stopOnPanel!=='boolean')throw Error('Panel stop must be Boolean');await stopped();const state=await inspect();const next=new RunBudget(state.cycle,m.cycles,m.stopOnReady??false,m.hostSeconds??null,performance.now(),m.stopOnPanel?state.panel_completed:null);if(next.limit>922337203685477580n)throw Error('Run exceeds signed virtual-nanosecond clock');budget=next;running=true;pauseReason=null;await sendState(state);schedule();}
  else if(m.action==='pen'||m.action==='button'){if(capture.length>=1000000)throw Error('Raw capture bound exhausted');await input(m);schedule();}
  else if(m.action==='raw'||m.action==='raw-batch'){await stopped();const rows=m.action==='raw'?[m.row]:typeof m.rows==='string'&&m.rows.length<=65536?m.rows.split(/\r?\n/).filter(r=>r.trim()):[];if(rows.length<1||rows.length>1024||capture.length+rows.length>1000000)throw Error('Raw batch bounds');let accepted=0;try{for(const row of rows){await raw(row);accepted++;}}finally{postMessage({type:'raw-admission',accepted,total:rows.length,error:accepted===rows.length?null:'Remainder rejected; accepted prefix retained'});}await sendState();schedule();}
  else if(m.action==='course-install'){if(coursePartial)throw Error('Cold-open before retrying partial course input');pause('course-input');await stopped();const frame=courseInstallFrame(m.bytes,m.transaction),clock=await control.request('lemma-clock'),base=(BigInt(clock.virtual_ns)+9n)/10n*10n;let accepted=0;try{const arrival=await admitUart(control,frame,base,uartPaced,n=>{accepted=n;});postMessage({type:'uart-arrival-admission',arrival});}catch(e){coursePartial=accepted>0;postMessage({type:'course-admission',accepted,total:frame.length,bytes:frame.length-64,error:String(e)});throw e;}postMessage({type:'course-admission',accepted,total:frame.length,bytes:frame.length-64,error:null});await sendState();}
  else if(m.action==='inspect'){await stopped();await sendState(await inspect(true));postMessage({type:'uart',text:new TextDecoder().decode(uart())});schedule();}
  else if(m.action==='reset'){school.disconnect();schoolMachineEpoch++;if(typeof m.cold!=='boolean')throw Error('Cold reset selector must be Boolean');pause('reset');await stopped();if(m.cold){postMessage({type:'runtime-closed',nextNotebook:true});return;}await control.request('lemma-waveform');egress.discard(core.FS.stat('/audio.bin').size);await control.request('system_reset');guestStart=uart().length;readyAt=null;budget=null;panelSequence=null;await sendState();await panel(true);}
  else if(m.action==='export-panel'){await stopped();await panel(true);const result=await control.request('lemma-panel'),packed=core.FS.readFile(result.path),header=new TextEncoder().encode(`P5\n${result.width} ${result.height}\n255\n`),bytes=new Uint8Array(header.length+result.width*result.height);bytes.set(header);for(let y=0;y<result.height;y++)for(let x=0;x<result.width;x++){const p=packed[y*result.stride+(x>>1)];bytes[header.length+y*result.width+x]=((x&1)?p&15:p>>4)*17;}postMessage({type:'export',name:'lemma-controller.pgm',bytes},[bytes.buffer]);schedule();}
  else if(m.action==='export'){pause('export');await stopped();const bytes=new Uint8Array(268435456);for(let i=0;i<bytes.length;i+=1048576)if(handle.read(bytes.subarray(i,i+1048576),{at:i})!==1048576)throw Error('Backing export partial read');postMessage({type:'export',name:'lemma-backing.raw',bytes},[bytes.buffer]);await sendState();}
  else if(m.action==='events'){const bytes=new TextEncoder().encode(JSON.stringify({schema:'lemma-qemu-browser-raw-capture/1',events:capture}));postMessage({type:'export',name:'lemma-events.json',bytes},[bytes.buffer]);}
  else if(m.action==='close'){school.disconnect();schoolMachineEpoch++;pause('closed');await stopped();postMessage({type:'runtime-closed',backingMetrics:backing.metrics});}
 });
};
