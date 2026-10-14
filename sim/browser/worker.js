// SPDX-License-Identifier: Apache-2.0
import createMachine from './machine.mjs';
import {guestRecord,guestPageReady,guestCommitState,guestCourseInstallState} from './guest_records.js';
import {courseInstallFrame,courseInstallRows} from './course_transport.js';
import {RunBudget,uint64} from './run_budget.js';
let core, handle, running=false, loaded=false, manifest, panelSequence='-1';
let activeMediumName=null;
let loops=0, capture=[], checkpoints={}, readyAt=null, started=0,initializing=false;
let busy=false,backingReady=true,replayUntil=null;
let guestOutputStart=0;
let guestObservation='boot';
let sessionMode='student';
const SESSION_CONTROL_CONTRACT='lemma-browser-session-modes/2';
const ordinaryActions=new Set(['open','import','pause','resume','pen','button','reset','snapshot','export','restore','bind','close']);
const developerActions=new Set(['replay','run','raw','raw-batch','course-install','inspect','outcomes','events','capture','capture-outcomes']);
function admission(message){
 if(!message||typeof message!=='object'||typeof message.action!=='string')throw Error('Invalid browser request');
 const opening=['open','replay','import'].includes(message.action);
 if(!opening&&message.mode!==undefined)throw Error('Session mode is fixed until the machine is closed');
 if(opening&&message.mode!==undefined&&!['student','developer','laboratory'].includes(message.mode))
  throw Error('Unknown browser session mode');
 if(opening&&loaded&&message.mode!==undefined&&message.mode!==sessionMode)
  throw Error('Session mode is fixed until the machine is closed');
 const mode=opening&&!loaded?(message.mode??'student'):sessionMode;
 if(!['student','developer','laboratory'].includes(mode))throw Error('Unknown browser session mode');
 if(!ordinaryActions.has(message.action)&&!(mode!=='student'&&developerActions.has(message.action)))
  throw Error(developerActions.has(message.action)?'This control requires Developer or Laboratory mode':'Unsupported browser action');
 return mode;
}
let courseInputPartial=false;
let budget=null,stepTimer=null,pauseReason=null,timing=null,inRun=false;
const hash=async b=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),x=>x.toString(16).padStart(2,'0')).join('');
// Preserve every 64-bit JSON integer literally. Number is used only for
// bounded geometry, byte lengths and run quanta, never clocks or addresses.
function state(){return JSON.parse(core.ccall('lemma_inspect','string',[],[]).replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(s,n)=>n===undefined?s:JSON.stringify(n)));}
function check(name,types=[],args=[]){if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));}
function sendState(){const s=state();postMessage({type:'state',state:s,mode:sessionMode,modeContract:SESSION_CONTROL_CONTRACT,running,guestObservation,guestCommit:guestCommitState(core.FS.readFile('/uart.bin'),guestOutputStart),guestCourse:guestCourseInstallState(core.FS.readFile('/uart.bin'),guestOutputStart),backingMedium:{name:activeMediumName,private:s.isolated_medium===true,ready:backingReady},heapBytes:core.HEAPU8.byteLength,readyAt,hostSeconds:(performance.now()-started)/1000,
 pauseReason,budget:budget?.inspection()??null,timing:{scope:'opened-worker-session',elapsedSeconds:(performance.now()-timing.started)/1000,
 simulationCallSeconds:timing.runSeconds,backingCallSeconds:timing.backingSeconds,backingCallSecondsDuringRun:timing.backingRunSeconds,
 simulationOutsideBackingSeconds:Math.max(0,timing.runSeconds-timing.backingRunSeconds)}});return s;}
// These are synchronous call durations, not guest CPU time. A run call
// includes its backing waits; elapsed time also includes paused observation.
function timedBacking(backing){const adapter={};for(const name of ['read','write','flush','getSize','submit','poll'])if(typeof backing[name]==='function')
 adapter[name]=(...args)=>{const start=performance.now();try{return backing[name](...args);}finally{const seconds=(performance.now()-start)/1000;
  timing.backingSeconds+=seconds;if(inRun)timing.backingRunSeconds+=seconds;}};return adapter;}
function pause(reason){running=false;pauseReason=reason;if(stepTimer!==null){clearTimeout(stepTimer);stepTimer=null;}}
function scheduleStep(){if(running&&stepTimer===null)stepTimer=setTimeout(()=>{stepTimer=null;step();},0);}
function observeReady(data=core.FS.readFile('/uart.bin')){if(readyAt===null&&guestPageReady(data,guestOutputStart,JSON.parse(core.ccall('lemma_paper_inspect','string',[],[]))))
 readyAt={cycle:state().cycle,hostSeconds:(performance.now()-started)/1000};return readyAt!==null;}
function exportEvents(){const log={schema:'lemmasim-browser-raw-capture/1',events:capture.slice(),checkpoints,until:state().cycle};
 const raw=new TextEncoder().encode(JSON.stringify(log));postMessage({type:'export',name:'lemma-events.json',bytes:raw},[raw.buffer]);}
function panel(force=false){const s=state();if(force||s.panel_completed!==panelSequence){panelSequence=s.panel_completed;
 const p=core.ccall('lemma_pixels','number',[],[]),n=core.ccall('lemma_pixel_count','number',[],[]);
 const pixels=core.HEAPU8.slice(p,p+n);postMessage({type:'panel',pixels,width:manifest.width,height:manifest.height},[pixels.buffer]);}}
function admit(e){if(replayUntil!==null)throw Error('Offline replay accepts its recorded events only');if(capture.length>=1000000)throw Error('Raw capture exceeds its event bound');const s=state();
 const row=e.action==='pen'?`${s.cycle} pen ${s.ticks} ${e.x} ${e.y} ${e.pressure} ${e.flags} ${e.tool} 0`:`${s.cycle} button ${e.level}`;
 check('lemma_event',['string'],[row]);capture.push(row);}
function admitRaw(text,observe=true){if(replayUntil!==null)throw Error('Offline replay accepts its recorded events only');
 if(typeof text!=='string'||text.length>256||capture.length>=1000000)throw Error('Raw event exceeds its bound');
 const fields=text.trim().split(/\s+/),s=state();
 if(!['pen','button','uart'].includes(fields[1]))throw Error('Raw input admits pen, button or uart only');
 if(fields[0]==='now')fields[0]=s.cycle;if(fields[1]==='pen'&&fields[2]==='now')fields[2]=s.ticks;
 const row=fields.join(' ');check('lemma_event',['string'],[row]);capture.push(row);if(observe)sendState();}
function admitBatch(text){
 if(typeof text!=='string'||text.length>65536)throw Error('Raw batch exceeds 65536 characters');
 const rows=text.split(/\r?\n/).map(row=>row.trim()).filter(Boolean);
 if(rows.length===0||rows.length>1024||rows.some(row=>row.length>256)||capture.length+rows.length>1000000)
  throw Error('Raw batch requires 1–1024 bounded events within the capture limit');
 // Each accepted device event is authoritative. A later rejection cannot
 // retract its prefix; report it exactly and leave the machine paused.
 let accepted=0;try{for(const row of rows){admitRaw(row,false);accepted++;}}
 catch(e){postMessage({type:'raw-admission',accepted,total:rows.length,error:String(e)});
  throw Error(`Raw batch rejected after ${accepted} of ${rows.length} events: ${e}`);}
 sendState();postMessage({type:'raw-admission',accepted,total:rows.length,error:null});
}
function admitCourseInstall(message){
 if(!loaded||!backingReady)throw Error('Open the package-enabled machine first');
 if(manifest.course_install_contract!=='lemma-course-console-command/1')throw Error('This bundle does not expose the guest package installer');
 if(courseInputPartial||guestObservation==='continuation')throw Error('Close and cold-open backing before sending another package after a partial admission or restored continuation');
 if(replayUntil!==null)throw Error('Offline replay accepts its recorded events only');
 const packet=courseInstallFrame(message.bytes,message.transaction);
 const rows=courseInstallRows(packet,state().cycle);
 if(capture.length+rows.length>1000000)throw Error('Course input exceeds the raw capture limit');
 pause('course-input');
 let accepted=0;
 try{for(const row of rows){admitRaw(row,false);accepted++;}}
 catch(e){courseInputPartial=accepted>0;postMessage({type:'course-admission',accepted,total:rows.length,bytes:packet.length-64,error:String(e)});throw e;}
 sendState();postMessage({type:'course-admission',accepted,total:rows.length,bytes:packet.length-64,error:null});
}
function step(){if(!running)return;try{
 if(budget?.hostExpired(performance.now())){pause('host-limit');panel(true);sendState();return;}
 const before=state(),cycle=uint64(before.cycle);
 if(budget?.panelCompleted(before)){pause('panel-complete');panel(true);sendState();return;}
 let quantum=budget?budget.quantum(before.cycle):50000n;
 if(budget?.stopOnReady&&observeReady()){pause('guest-ready');panel(true);sendState();return;}
 if(replayUntil!==null){const left=uint64(replayUntil)-cycle;if(left<=0n){pause('replay-limit');panel(true);sendState();return;}if(left<quantum)quantum=left;}
 if(quantum===0n){pause('cycle-limit');panel(true);sendState();return;}
 if(initializing&&guestRecord(core.FS.readFile('/uart.bin'),guestOutputStart,'000000000000041f')){
  pause('initializer-complete');initializing=false;launchNotebook().catch(e=>{pause('error');postMessage({type:'error',error:String(e)});});return;}
 const start=performance.now();inRun=true;
 try{check('lemma_run',['number'],[Number(quantum)]);}finally{inRun=false;timing.runSeconds+=(performance.now()-start)/1000;if(budget)budget.observe(state().cycle,quantum);}
 loops++;
 const after=state(),periodic=loops%10===0;
 if(budget?.hostExpired(performance.now())){pause('host-limit');panel(true);sendState();return;}
 const data=(periodic||initializing||budget?.stopOnReady)?core.FS.readFile('/uart.bin'):null;
 if(data)observeReady(data);
 if(budget?.remaining===0n){pause('cycle-limit');panel(true);sendState();return;}
 if(budget?.panelCompleted(after)){pause('panel-complete');panel(true);sendState();return;}
 if(budget?.stopOnReady&&readyAt!==null){pause('guest-ready');panel(true);sendState();return;}
 if(replayUntil!==null&&uint64(after.cycle)>=uint64(replayUntil)){pause('replay-limit');panel(true);sendState();return;}
 if(initializing&&guestRecord(data,guestOutputStart,'000000000000041f')){
  pause('initializer-complete');initializing=false;launchNotebook().catch(e=>{pause('error');postMessage({type:'error',error:String(e)});});return;}
 if(after.finished===true||after.finished==='1'){pause('guest-finished');panel(true);sendState();return;}
 if(uint64(after.cycle)===cycle)throw Error('Machine run made no clock progress');
 if(periodic){panel();sendState();}
 scheduleStep();
 }catch(e){pause('error');sendState();postMessage({type:'error',error:String(e)});}}
async function getBytes(item){const r=await fetch(item.path);if(!r.ok)throw Error('Artifact fetch failed: '+item.path);
 const b=new Uint8Array(await r.arrayBuffer());
 if(await hash(b)!==item.sha256)throw Error('Artifact hash mismatch: '+item.path);return b;}
async function openMedium(name,initialize){
 if(typeof name!=='string'||!/^[a-zA-Z0-9_-]{1,64}$/.test(name))throw Error('Use a medium name with letters, digits, underscores or hyphens');
 const root=await navigator.storage.getDirectory();let file;
 if(initialize){try{await root.getFileHandle(name+'.raw');throw Error('Medium already exists; initialization refuses to format it');}
  catch(e){if(e.name!=='NotFoundError')throw e;}file=await root.getFileHandle(name+'.raw',{create:true});}
 else file=await root.getFileHandle(name+'.raw');
 const next=await file.createSyncAccessHandle();
 try{
  if(initialize){next.truncate(268435456);next.flush();}
  if(next.getSize()!==268435456)throw Error('Expected a 256 MiB medium');
  return next;
 }catch(error){
  // No machine owns this handle yet. Release its exclusive lease even when
  // creating/validating the medium failed after changing backing bytes.
  // A secondary close error cannot replace the original storage outcome.
  try{next.close();}catch{}
  throw error;
 }
}
async function load(message){if(loaded)throw Error('Close this machine before opening another');
 if(message.paused!==undefined&&typeof message.paused!=='boolean')throw Error('Open paused must be a Boolean');
 manifest=await(await fetch('./bundle.json')).json();if(manifest.schema!=='lemmasim-browser-bundle/1')throw Error('Unsupported bundle');
 if(manifest.session_control_contract!==SESSION_CONTROL_CONTRACT)throw Error('Browser control contract differs from this worker');
 if(!navigator.storage?.getDirectory)throw Error('Browser OPFS persistence is required');
 handle=await openMedium(message.name,!!message.initialize);
 activeMediumName=message.name;
 try{timing={started:performance.now(),runSeconds:0,backingSeconds:0,backingRunSeconds:0};core=await createMachine();core.backing=timedBacking(handle);core.FS.mkdir('/forks');
  const workload=manifest.workloads[message.initialize&&!message.replay?'initializer':'notebook'];
  for(const [path,item]of [['/image.elf',workload.image],['/machine.dtb',workload.dtb],['/descriptor.bin',workload.descriptor],['/boot.bin',manifest.rom]])core.FS.writeFile(path,await getBytes(item));
  if(message.replay){
   core.FS.writeFile('/replay.io',new Uint8Array(message.replayLog));check('lemma_create_mode',['number'],[1]);
   await restore(message.checkpoint);
   const log=message.events;if(log.schema!=='lemmasim-browser-raw-capture/1'||!Array.isArray(log.events)||log.events.length>1000000)throw Error('Invalid raw replay capture');
   const boundary=log.checkpoints[await hash(message.checkpoint)];
   if(!boundary||boundary.cycle!==state().cycle||!Number.isSafeInteger(boundary.eventCount)||boundary.eventCount<0||boundary.eventCount>log.events.length)throw Error('Capture does not bind this checkpoint');
   const until=BigInt(log.until);if(until<BigInt(state().cycle)||until>18446744073709551615n)throw Error('Invalid replay end');
   for(const row of log.events.slice(boundary.eventCount)){if(typeof row!=='string'||row.length>256)throw Error('Invalid bounded raw event');const cycle=BigInt(row.split(' ')[0]);if(cycle<BigInt(state().cycle)||cycle>until)throw Error('Replay event outside suffix');check('lemma_event',['string'],[row]);}
   replayUntil=String(until);
  }else check('lemma_create');courseInputPartial=false;loaded=true;guestOutputStart=core.FS.readFile('/uart.bin').length;guestObservation=message.replay?'continuation':'boot';initializing=!!message.initialize&&!message.replay;started=performance.now();running=!message.paused;pauseReason=message.paused?'opened-paused':null;sendState();panel(true);if(running)scheduleStep();
 }catch(e){pause('error');core?.ccall('lemma_destroy',null,[],[]);handle?.close();handle=null;activeMediumName=null;loaded=false;throw e;}}
async function launchNotebook(){busy=true;try{core.ccall('lemma_destroy',null,[],[]);
 const w=manifest.workloads.notebook;
 for(const [path,item]of [['/image.elf',w.image],['/machine.dtb',w.dtb],['/descriptor.bin',w.descriptor]])core.FS.writeFile(path,await getBytes(item));
 check('lemma_create');if(budget)budget.rebase(state().cycle);guestOutputStart=core.FS.readFile('/uart.bin').length;guestObservation='boot';loops=0;capture=[];checkpoints={};readyAt=null;started=performance.now();sendState();panel(true);running=true;pauseReason=null;scheduleStep();
 }finally{busy=false;}}
async function bindPrivate(){
 // Copy opaque backing bytes, including observed unacknowledged changes.
 // No guest journal is interpreted by this transport.
 const path='/private-'+loops+'.raw';check('lemma_export_private',['string'],[path]);
 const nextName='fork_'+crypto.randomUUID().replaceAll('-','');
 let next,stream;try{next=await openMedium(nextName,true);
  const size=core.FS.stat(path).size;if(size!==268435456)throw Error('Invalid private backing capacity');
  stream=core.FS.open(path,'r');const chunk=new Uint8Array(1048576);
  for(let i=0;i<size;i+=chunk.length){const length=Math.min(chunk.length,size-i);
   if(core.FS.read(stream,chunk,0,length,i)!==length||next.write(chunk.subarray(0,length),{at:i})!==length)
    throw Error('Private medium copy failed');}
  next.flush();core.backing=timedBacking(next);check('lemma_rebind_private');const old=handle;handle=next;activeMediumName=nextName;next=null;backingReady=true;old.close();
 }finally{if(stream)core.FS.close(stream);core.FS.unlink(path);next?.close();if(!backingReady)core.backing=timedBacking(handle);}
}
function restoreCheckpoint(bytes){
 if(!(bytes instanceof ArrayBuffer)||bytes.byteLength>805306368)throw Error('Checkpoint exceeds the machine bound');
 core.FS.writeFile('/incoming.bin',new Uint8Array(bytes));
 try{check('lemma_restore',['string'],['/incoming.bin']);}finally{core.FS.unlink('/incoming.bin');}
}
async function restore(bytes){
 restoreCheckpoint(bytes);
 // A valid restored machine stays paused until its private origin backing
 // is complete. On storage failure, retry binding or export its actual bytes.
 backingReady=false;await bindPrivate();
}
onmessage=async({data:m})=>{
 // Admission is outside the mutation/error-pause path. A denied control must
 // not cancel scheduled clocks, touch backing storage or alter live state.
 let nextMode;try{nextMode=admission(m);}catch(e){postMessage({type:'error',error:String(e)});return;}
 if(busy){postMessage({type:'error',error:'A storage or restore operation is pending'});return;}
 busy=true;try{
 if(m.action==='open'||m.action==='replay'){if(loaded)throw Error('Close this machine before opening another');capture=[];checkpoints={};replayUntil=null;backingReady=true;budget=null;readyAt=null;loops=0;panelSequence='-1';
  sessionMode=nextMode;await load({...m,replay:m.action==='replay',initialize:m.action==='replay'||m.initialize});return;}
 if(m.action==='import'){
  if(loaded)throw Error('Close this machine before importing another medium');
  const b=new Uint8Array(m.bytes);if(b.length!==268435456)throw Error('Expected a 256 MiB raw medium');
  const next=await openMedium(m.name,true);try{for(let i=0;i<b.length;i+=1048576)
   if(next.write(b.subarray(i,i+1048576),{at:i})!==Math.min(1048576,b.length-i))throw Error('Medium import partial transfer');next.flush();}
  finally{next.close();}postMessage({type:'imported'});return;
 }
 if(!loaded)throw Error('Open a machine first');
 if(m.action==='pause'){pause('user');sendState();}
 else if(m.action==='resume'){if(!backingReady)throw Error('Private origin backing is incomplete; retry binding before continuing');budget=null;pauseReason=null;running=true;scheduleStep();}
 else if(m.action==='run'){if(!backingReady)throw Error('Private origin backing is incomplete; retry binding before continuing');
  if(m.stopOnPanel!==undefined&&typeof m.stopOnPanel!=='boolean')throw Error('Panel stop must be a boolean');
  const initial=state(),next=new RunBudget(initial.cycle,m.cycles,m.stopOnReady??false,m.hostSeconds??null,performance.now(),m.stopOnPanel?initial.panel_completed:null);pause(null);budget=next;running=true;sendState();scheduleStep();}
 else if(m.action==='pen'||m.action==='button'){admit(m);}
 else if(m.action==='raw'){admitRaw(m.row);}
 else if(m.action==='raw-batch'){admitBatch(m.rows);}
 else if(m.action==='course-install')admitCourseInstall(m);
 else if(m.action==='inspect'){sendState();postMessage({type:'uart',text:new TextDecoder().decode(core.FS.readFile('/uart.bin'))});}
 else if(m.action==='reset'){if(!backingReady)throw Error('Private backing is incomplete');if(replayUntil!==null)throw Error('Reset is outside this recorded suffix');pause('reset');budget=null;guestOutputStart=core.FS.readFile('/uart.bin').length;guestObservation='boot';check('lemma_reset',['number'],[m.cold?1:0]);capture=[];checkpoints={};readyAt=null;sendState();panel(true);}
 else if(m.action==='snapshot'){pause('snapshot');const path='/snapshot-'+loops+'.bin';check('lemma_snapshot',['string'],[path]);
  const b=core.FS.readFile(path);core.FS.unlink(path);checkpoints[await hash(b)]={eventCount:capture.length,cycle:state().cycle};
  postMessage({type:'export',name:'lemma-checkpoint.bin',bytes:b},[b.buffer]);sendState();}
 else if(m.action==='export'){pause('export');const path='/durable-'+loops+'.raw';check('lemma_export',['string'],[path]);
  const b=core.FS.readFile(path);core.FS.unlink(path);postMessage({type:'export',name:'lemma-backing.raw',bytes:b},[b.buffer]);sendState();}
 else if(m.action==='restore'){
  // The machine validates before replacing authoritative state. Reject an
  // incompatible/corrupt archive without cancelling the live run or budget.
  // No asynchronous copy starts until this synchronous acceptance succeeds.
  try{restoreCheckpoint(m.bytes);}catch(error){postMessage({type:'error',error:String(error)});return;}
  pause('restore');budget=null;guestOutputStart=core.FS.readFile('/uart.bin').length;guestObservation='continuation';capture=[];checkpoints={};replayUntil=null;readyAt=null;
  // Clear launch observations before private backing can fail. The accepted
  // continuation remains paused and retryable, with no prior Ready/save label.
  backingReady=false;await bindPrivate();sendState();panel(true);
 }
 else if(m.action==='bind'){pause('bind');if(backingReady)throw Error('Private backing is already bound');await bindPrivate();sendState();}
 else if(m.action==='outcomes'){pause('outcomes');if(!backingReady)throw Error('Private origin backing is incomplete');
  if(!(m.bytes instanceof ArrayBuffer)||m.bytes.byteLength>268435456)throw Error('Outcome tape exceeds its bound');
  const path='/inherited-outcomes.io';core.FS.writeFile(path,new Uint8Array(m.bytes));
  try{check('lemma_backing_outcomes',['string'],[path]);}finally{core.FS.unlink(path);}sendState();}
 else if(m.action==='events'){pause('events');exportEvents();sendState();}
 else if(m.action==='capture'||m.action==='capture-outcomes'){pause('capture');const path=core.ccall('lemma_capture_path','string',[],[]);if(!path)throw Error('This replay instance does not capture live outcomes');
  const b=core.FS.readFile(path);postMessage({type:'export',name:'lemma-backing.io',bytes:b},[b.buffer]);
  if(m.action==='capture')exportEvents();sendState();}
 else if(m.action==='close'){pause('close');core.ccall('lemma_destroy',null,[],[]);handle.close();loaded=false;handle=null;activeMediumName=null;postMessage({type:'closed'});}
 else throw Error('Unsupported browser action');
 }catch(e){pause('error');if(loaded)sendState();postMessage({type:'error',error:String(e)});}finally{busy=false;}};
