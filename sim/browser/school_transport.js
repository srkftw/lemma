// SPDX-License-Identifier: Apache-2.0
// Network bytes and complete guest ASK observations only. Lean owns admission,
// publication, assistance policy, assessment and every durable transition.
export function guestSchoolCapability(bytes,start=0){
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)throw Error('Invalid guest capability observation');
 let capability=null;
 for(const row of new TextDecoder().decode(bytes.subarray(start)).matchAll(/(?:^|\n)K1 0000000000000731 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g)){
  const [version,chunks,bytes,selection]=row.slice(1).map(x=>BigInt('0x'+x));
  if(!((version===1n&&chunks===8n)||(version===2n&&chunks===512n))||bytes!==262144n||selection!==2n)throw Error('Unsupported guest school capability tuple');
  capability={version:Number(version),maximumChunks:Number(chunks),maximumBytes:Number(bytes),selection:Number(selection)};
 }
 return capability;
}
export function guestSchoolQueueState(bytes,start=0){
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)throw Error('Invalid guest queue observation');
 let state=null;
 for(const row of new TextDecoder().decode(bytes.subarray(start)).matchAll(/(?:^|\n)K1 (000000000000072e|000000000000073[234]) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g)){
  const [tag,a,b,c,d]=row.slice(1).map(x=>BigInt('0x'+x));
  if(tag===0x732n)state={state:'failed',code:String(a),authority:'compiled-guest-report'};
  else if(tag===0x72en)state={state:'pending',queue:String(a),localQueueCommit:String(b),bytes:String(c),authority:'compiled-guest-report'};
  else if((d===2n&&b===0n)||(d===3n&&b>0n))state={state:d===2n?'cancelled':'acknowledged',queue:String(a),schoolCommit:String(b),observedFrontier:String(c),observation:tag===0x733n?'new-pointer-commit':'restored-pointer-read',authority:'compiled-guest-report'};
  else throw Error('Malformed terminal guest queue report');
 }
 return state;
}
export function guestSchoolAsk(bytes,start=0){
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)throw Error('Invalid guest observation boundary');
 const rows=new TextDecoder().decode(bytes.subarray(start)).matchAll(/(?:^|\n)K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g);
 let pending=[],complete=null;
 for(const row of rows){const tag=BigInt('0x'+row[1]),v=row.slice(2).map(x=>BigInt('0x'+x));
  if(tag===0x721n)pending=[v];
  else if(tag===0x722n&&pending.length===1)pending.push(v);
  else if(tag===0x723n&&pending.length===2){
   const [session,revision,object,sequence]=pending[0],[source,edition,task_id,cutoff]=pending[1],[consent,deadline,grants,maxPcm]=v;
   if(grants!==1n||maxPcm!==0n)throw Error('This school connection supports the guest text-only ASK');
   complete={session,revision,object,sequence,source,edition,task_id,cutoff,now:cutoff,consent,deadline,grants,modality:1};pending=[];
  }
 }
 if(!complete||pending.length)throw Error('Tap ASK in the current guest course first');
 return complete;
}
export function guestSchoolSubmission(bytes,start=0){
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length||bytes.length-start>16*1048576)throw Error('Invalid bounded guest submission observation');
 const rows=new TextDecoder().decode(bytes.subarray(start)).matchAll(/(?:^|\n)K1 ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g);
 let current=null,complete=null;
 for(const row of rows){const [tag,a,b,c,d]=row.slice(1).map(x=>BigInt('0x'+x));
  if(tag===0x72en){
   if(a>>48n!==0x5351n||b===0n||c<256n||c>262144n||(d!==1n&&d!==2n))throw Error('Malformed guest submission stream start');
   current={queue:a,commit:b,total:Number(c),bytes:new Uint8Array(Number(c)),used:0};
  }else if(tag===0x72fn&&current){
   const offset=Number(b&((1n<<48n)-1n)),count=Number(b>>48n);
   if(a!==current.queue||count<1||count>16||offset!==current.used||count>current.total-offset)throw Error('Guest submission stream is missing, reordered or mixed');
   const words=new DataView(new ArrayBuffer(16));words.setBigUint64(0,c,true);words.setBigUint64(8,d,true);
   current.bytes.set(new Uint8Array(words.buffer,0,count),offset);current.used+=count;
  }else if(tag===0x730n&&current){
   if(a!==current.queue||b!==current.commit||c!==BigInt(current.total)||d!==0n||current.used!==current.total)throw Error('Guest submission ended before its exact committed bytes');
   complete=current;current=null;
  }
 }
 if(current)throw Error('Guest work is still streaming; writing and Save remain available');
 if(!complete)throw Error('Tap SEND on the guest paper to commit and stream work first');
 return complete;
}
function crc32(bytes){let crc=0xffffffff;for(const byte of bytes){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
export function schoolAcknowledgement(stream,result){
 if(BigInt(result.queueObject)!==stream.queue||BigInt(result.envelopeCRC32)!==BigInt(crc32(stream.bytes)))throw Error('School commit acknowledgement differs from exact guest bytes');
 const commit=BigInt(result.commitSequence);if(commit<1n||commit>=(1n<<63n))throw Error('School returned no bounded durable commit');
 const frame=new Uint8Array(64),view=new DataView(frame.buffer),fields=[0x31504b43414d454cn,3n,10n,stream.queue,commit,0n,stream.commit,BigInt(result.envelopeCRC32)];
 fields.forEach((v,i)=>view.setBigUint64(i*8,v,true));return frame;
}
function parseSchoolJson(text){
 // Preserve full64-bit durable identities while keeping small UI values numeric.
 return JSON.parse(text.replace(/"(?:\\.|[^"\\])*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/g,token=>
  token[0]==='"'||/[.eE]/.test(token)||Number.isSafeInteger(Number(token))?token:JSON.stringify(token)));
}
function encoded(value){
 if(typeof value==='bigint')return value.toString();
 if(Array.isArray(value))return '['+value.map(encoded).join(',')+']';
 if(value&&typeof value==='object')return '{'+Object.entries(value).map(([k,v])=>JSON.stringify(k)+':'+encoded(v)).join(',')+'}';
 return JSON.stringify(value);
}
export class SchoolTransport {
 constructor(){this.pending=new Set();this.connection=null;this.session=null;this.review=null;this.generation=0;this.deliveryQueue=[];this.deliveryFailed=[];this.deliveryDropped=0;this.deliveryLastError=null;this.deliveryActive=null;this.deliveryObserver=null;this.deliveryRunning=false;}
 disconnect(){this.cancelDelivery('disconnect');this.generation++;this.intent=(this.intent??0)+1;this.busy=false;for(const c of this.pending)c.abort();this.pending.clear();this.connection=null;this.session=null;this.review=null;}
 // These bounded live observations are outside guest/checkpoint state. Every
 // queued receipt owns its original peer; reconnect can never retarget it.
 beginDelivery(result,context,uartByteStart=0){
  if(!result||typeof result.decision!=='string'||!result.decision.length||result.decision.length>256||!this.connection)throw Error('No authored school decision to observe');
  if(!Number.isSafeInteger(uartByteStart)||uartByteStart<0)throw Error('Invalid delivery console boundary');
  if(this.deliveryActive?.decision===result.decision&&!this.deliveryActive.cancelled)return this.deliveryStatus();
  this.cancelDelivery('navigation');
  this.deliveryObserver??='browser-'+crypto.randomUUID();
  this.deliveryActive={decision:result.decision,ask:{...context},connection:{...this.connection},observer:this.deliveryObserver,
   uartStart:uartByteStart,uartCursor:uartByteStart,notes:new Set(),records:new Set(),controller:null,controllerCount:0,rasterAccepted:false,controllerDone:false,cancelled:false,observing:false};
  return this.deliveryStatus();
 }
 deliveryStatus(){return {pending:this.deliveryQueue.length+(this.deliveryRunning?1:0),failed:this.deliveryFailed.length,dropped:this.deliveryDropped,lastError:this.deliveryLastError,
  scope:'Bounded live reported observations; no guest checkpoint persistence or all-body visibility claim'};}
 _deliveryNote(delivery,kind,observation){
  if(!delivery)return;
  const command={op:'delivery-observe',decision:delivery.decision,sequence:delivery.ask.sequence,observer:delivery.observer,kind,observation};
  const identity=encoded(command);if(delivery.notes.has(identity))return;
  if(this.deliveryQueue.length+(this.deliveryRunning?1:0)>=64||delivery.notes.size>=64){this.deliveryDropped++;this.deliveryLastError='Delivery observation queue full; original guest work is unchanged';return;}
  delivery.notes.add(identity);this.deliveryQueue.push({command,connection:delivery.connection});void this._pumpDelivery();
 }
 async _deliveryExchange(entry){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
  try{
   const response=await fetch(entry.connection.endpoint,{method:'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+entry.connection.token},body:encoded(entry.command),signal:controller.signal});
   if(!response.ok)throw Error('Delivery observation HTTP '+response.status);
   const reader=response.body.getReader();let count=0,parts=[];
   for(;;){const {done,value}=await reader.read();if(done)break;count+=value.length;if(count>65536){await reader.cancel();throw Error('Delivery receipt exceeds64KiB');}parts.push(value);}
   const bytes=new Uint8Array(count);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.length;}
   const reply=parseSchoolJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
   if(reply.ok!==true)throw Error('Lean school rejected delivery observation: '+String(reply.error));
   if(!reply.result||typeof reply.result.observation!=='string'||!/^[a-f0-9]{64}$/.test(reply.result.observation)||BigInt(reply.result.commitSequence??0)<1n)throw Error('School returned no committed delivery receipt');
   return reply.result;
  }finally{clearTimeout(timer);}
 }
 async _pumpDelivery(){
  if(this.deliveryRunning)return;this.deliveryRunning=true;
  try{while(this.deliveryQueue.length){
   const entry=this.deliveryQueue.shift();let completed=false;
   for(let attempt=0;attempt<3&&!completed;attempt++){
    try{entry.receipt=await this._deliveryExchange(entry);this.deliveryLastReceipt=entry.receipt;completed=true;}
    catch(error){this.deliveryLastError=String(error);if(String(error).includes('Lean school rejected'))break;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,200*(attempt+1)));}
   }
   if(!completed){if(this.deliveryFailed.length>=64){this.deliveryFailed.shift();this.deliveryDropped++;}this.deliveryFailed.push(entry);}
  }}finally{this.deliveryRunning=false;}
 }
 retryDelivery(){
  while(this.deliveryFailed.length&&this.deliveryQueue.length+(this.deliveryRunning?1:0)<64)this.deliveryQueue.push(this.deliveryFailed.shift());
  void this._pumpDelivery();return this.deliveryStatus();
 }
 async transportDelivery(packetBytes,admittedBytes){
  const delivery=this.deliveryActive;if(!delivery)return this.deliveryStatus();
  const packet=packetBytes instanceof Uint8Array?packetBytes:new Uint8Array(packetBytes);
  if(packet.length<1||packet.length>65536||!Number.isSafeInteger(admittedBytes)||admittedBytes<0||admittedBytes>packet.length)throw Error('Invalid bounded delivery byte admission');
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',packet));
  this._deliveryNote(delivery,'transport',{admittedBytes,wireBytes:packet.length,packetSHA256:Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('')});
  return this.deliveryStatus();
 }
 cancelDelivery(reason='user-cancel'){
  const delivery=this.deliveryActive;if(delivery&&!delivery.cancelled){delivery.cancelled=true;this._deliveryNote(delivery,'cancelled',{reason});}
  return this.deliveryStatus();
 }
 async observeDelivery(uartBytes,start=0,controller=null){
  const delivery=this.deliveryActive;if(!delivery||delivery.cancelled||delivery.observing)return this.deliveryStatus();
  if(!(uartBytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>uartBytes.length||uartBytes.length>16*1048576)throw Error('Invalid bounded delivery console observation');
  if(uartBytes.length<delivery.uartCursor){this.cancelDelivery('machine-restart');return this.deliveryStatus();}
  delivery.observing=true;
  try{
   let end=uartBytes.length;while(end>delivery.uartCursor&&uartBytes[end-1]!==10)end--;
   let from=Math.max(start,delivery.uartStart,delivery.uartCursor>delivery.uartStart?delivery.uartCursor-1:delivery.uartStart);
   if(end-from>1048576){from=end-1048576;this.deliveryDropped++;this.deliveryLastError='Delivery console observation gap exceeds1MiB';}
   if(end>from){
    const text=new TextDecoder().decode(uartBytes.subarray(from,end));delivery.uartCursor=end;
    for(const row of text.matchAll(/(?:^|\n)K1 (0000000000000724|0000000000000725) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g)){
     const [tag,a,b,c,d]=row.slice(1).map(x=>BigInt('0x'+x));let kind=null;
     if(tag===0x725n&&a===BigInt(delivery.ask.sequence)&&b===1n&&c===0n&&d===0n)kind='guest-raster';
     if(tag===0x724n&&a>0n&&b===BigInt(delivery.ask.revision)&&c===BigInt(delivery.ask.object)&&d===0n)kind='guest-rejected';
     if(!kind||delivery.records.has(row[0]))continue;delivery.records.add(row[0]);if(kind==='guest-raster')delivery.rasterAccepted=true;
     const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(row[0].replace(/^\n/,'')+'\n')));
     this._deliveryNote(delivery,kind,{record:[tag,a,b,c,d],uartSHA256:Array.from(digest,b=>b.toString(16).padStart(2,'0')).join('')});
    }
   }
   if(controller&&delivery.rasterAccepted&&!delivery.controllerDone){
    const allowed=['cycle','completed','accepted','busy','targetSHA256','visibleSHA256','hashEncoding'];
    if(Object.keys(controller).some(key=>!allowed.includes(key)))throw Error('Unknown raw delivery controller field');
    const observation={};for(const key of ['cycle','completed','busy','accepted'])if(key in controller){
     const value=controller[key];if(typeof value==='number'&&!Number.isSafeInteger(value))throw Error('Unsafe controller integer');
     const raw=BigInt(value);if(raw<0n||raw>0xffffffffffffffffn)throw Error('Controller integer exceeds64bits');observation[key]=raw;
    }
    for(const key of ['targetSHA256','visibleSHA256','hashEncoding'])if(key in controller)observation[key]=controller[key];
    const projection={...observation};delete projection.cycle;const identity=encoded(projection);
    if(identity!==delivery.controller&&(delivery.controllerCount===0||observation.busy===0n)){delivery.controller=identity;
     if(delivery.controllerCount<2){delivery.controllerCount++;this._deliveryNote(delivery,'controller-snapshot',observation);}
     if(observation.busy===0n||delivery.controllerCount===2)delivery.controllerDone=true;
    }
   }
  }finally{delivery.observing=false;}
  return this.deliveryStatus();
 }
 connect(credential){
  this.disconnect();
  if(!credential||credential.schema!=='lemma-school-credential/1'||!/[a-f0-9]{64}/.test(credential.token)||credential.token.length!==64)throw Error('Choose an admitted local school credential');
  const url=new URL(credential.endpoint);
  if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.pathname!=='/v1/client'||url.username||url.password||url.search||url.hash)throw Error('Local school requires an explicit loopback /v1/client endpoint');
  this.connection={endpoint:url.href,token:credential.token};
 }
 async command(command){
  if(!this.connection)throw Error('Choose your school pairing file first');
  const generation=this.generation,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);this.pending.add(controller);
  try{
   const response=await fetch(this.connection.endpoint,{method:'POST',mode:'cors',credentials:'omit',cache:'no-store',redirect:'error',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+this.connection.token},body:encoded(command),signal:controller.signal});
   if(!response.ok)throw Error('School connection rejected: HTTP '+response.status);
   const reader=response.body.getReader();let size=0,parts=[];
   for(;;){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>1048576){await reader.cancel();throw Error('School response exceeds 1MiB');}parts.push(value);}
   const bytes=new Uint8Array(size);let offset=0;for(const p of parts){bytes.set(p,offset);offset+=p.length;}
   if(generation!==this.generation)throw Error('School connection changed during request');
   const reply=parseSchoolJson(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
   if(reply.ok!==true)throw Error('Lean school rejected: '+String(reply.error));
   if(!reply.result||typeof reply.result!=='object')throw Error('School returned no bounded result');
   return reply.result;
  }finally{clearTimeout(timer);this.pending.delete(controller);}
 }
 async operation(message,ask,submission){
  const mutation=['install','review','join','help','submit','cancel'].includes(message.operation);
  if(message.operation==='cancel'){
   for(const request of this.pending)request.abort();this.intent=(this.intent??0)+1;this.busy=false;
  }
  if(mutation&&this.busy)throw Error('A school transfer is pending; cancel it or wait before changing its publication/context');
  const intent=mutation?(this.intent=(this.intent??0)+1):this.intent;
  if(mutation)this.busy=true;
  try{return await this.perform(message,ask,submission);}
  finally{if(mutation&&this.intent===intent)this.busy=false;}
 }
 async perform(message,ask,submission){
  if(message.operation==='receipts')return this.retryDelivery();
  if(message.operation==='disconnect'){this.disconnect();return {state:'disconnected'};}
  if(message.operation==='connect'){this.connect(message.credential);return this.command({op:'course-catalogue',limit:20,after:0});}
  if(message.operation==='catalogue')return this.command({op:'course-catalogue',limit:20,after:message.after??0});
  if(message.operation==='feedback')return this.command({op:'feedback',limit:20,after:message.after??0});
  if(message.operation==='reviews')return this.command({op:'reviews',limit:20,after:message.after??0});
  if(message.operation==='review'){const result=await this.command({op:'review-open',id:message.id});this.review=message.id;return result;}
  if(message.operation==='submit'){const stream=submission(),result=await this.command({op:'guest-submit',hex:Array.from(stream.bytes,b=>b.toString(16).padStart(2,'0')).join('')});return {...result,ack_bytes:schoolAcknowledgement(stream,result)};}
  if(message.operation==='install'){
   this.review=null;
   if(!Number.isSafeInteger(message.course)||!Number.isSafeInteger(message.revision)||message.course<1||message.course>65535||message.revision<1||message.revision>0xffffffff)throw Error('Select a bounded published course and edition');
   return this.command({op:'client-course',course:message.course,revision:message.revision});
  }
  if(message.operation==='join'){
   const context=ask();this.session='browser-'+context.session+'-'+context.source+'-'+context.edition;
   return this.command({op:'join',course:context.source,revision:context.edition,session:this.session,guestSession:context.session,lifetimeMs:3600000,ask:context,...(this.review?{reviewId:this.review}:{})});
  }
  if(message.operation==='help'){
   if(!this.session)throw Error('Bind the current guest ASK to the school first');
   const context=ask();return this.command({op:'assist',session:this.session,course:context.source,revision:context.edition,ask:context});
  }
  if(message.operation==='cancel'){
   if(!this.session)throw Error('No school session is bound');
   this.cancelDelivery('user-cancel');const result=await this.command({op:'cancel-session',session:this.session});this.session=null;return result;
  }
  throw Error('Unsupported school activity');
 }
}
export function schoolPackage(result){
 if(typeof result.package_hex!=='string'||result.package_hex.length<256||result.package_hex.length>65536||!/^(?:[a-f0-9]{2})+$/.test(result.package_hex))throw Error('School returned no bounded publication bytes');
 return Uint8Array.from(result.package_hex.match(/../g),b=>parseInt(b,16)).buffer;
}
