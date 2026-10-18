// SPDX-License-Identifier: Apache-2.0
// Opaque host bytes only. The guest and modeled block controller own journals.
// Install before QEMU opens the regular file; fsync reaches the actual handle.
export function attachOpfsFile(module,path,handle){
 const FS=module.FS,capacity=268435456;
 if(handle.getSize()!==capacity)throw Error('Expected an exclusively owned 256 MiB medium');
 if(!/^\/[a-z][a-z0-9-]*\.raw$/.test(path))throw Error('Invalid backing transport path');
 const metrics={contract:'lemma-qemu-opfs-backing/1',readCalls:0,readBytes:0,writeCalls:0,writeBytes:0,flushCalls:0,flushCompleted:0,errors:0,lastError:null};
 const translate=error=>{metrics.errors++;metrics.lastError=String(error);const errno=({QuotaExceededError:51,NotAllowedError:2,SecurityError:2,InvalidStateError:8,AbortError:29,NotFoundError:44})[error.name]??29;throw new FS.ErrnoError(errno);};
 const checked=(f)=>{try{return f();}catch(error){if(error?.name==='ErrnoError')throw error;return translate(error);}};
 const span=(buffer,offset,length,position)=>{
  if(!(buffer instanceof Uint8Array)&&!(buffer instanceof Int8Array)||![offset,length,position].every(Number.isSafeInteger)||offset<0||length<0||length>1048576||offset>buffer.byteLength-length||position<0||position>capacity-length)throw new FS.ErrnoError(28);
 };
 FS.writeFile(path,new Uint8Array());const node=FS.lookupPath(path).node;
 const originalGet=node.node_ops.getattr;
 node.node_ops={getattr:n=>({...originalGet(n),size:capacity,blocks:capacity/4096}),setattr:(n,attr)=>{
  if(attr.size!==undefined&&attr.size!==capacity)throw new FS.ErrnoError(28);
  for(const key of ['mode','atime','mtime','ctime'])if(attr[key]!==undefined)n[key]=attr[key];
 }};
 node.stream_ops={
  llseek:(stream,offset,whence)=>{const next=offset+(whence===1?stream.position:whence===2?capacity:0);if(![0,1,2].includes(whence)||!Number.isSafeInteger(next)||next<0||next>capacity)throw new FS.ErrnoError(28);return next;},
  read:(stream,buffer,offset,length,position)=>checked(()=>{span(buffer,offset,length,position);metrics.readCalls++;const n=handle.read(buffer.subarray(offset,offset+length),{at:position});if(!Number.isInteger(n)||n<0||n>length)throw Error('Invalid backing read extent');metrics.readBytes+=n;return n;}),
  write:(stream,buffer,offset,length,position)=>checked(()=>{span(buffer,offset,length,position);metrics.writeCalls++;const n=handle.write(buffer.subarray(offset,offset+length),{at:position});if(!Number.isInteger(n)||n<0||n>length)throw Error('Invalid backing write extent');metrics.writeBytes+=n;node.mtime=Date.now();return n;}),
  fsync:()=>checked(()=>{metrics.flushCalls++;handle.flush();metrics.flushCompleted++;return 0;})
 };
 return {metrics,capacity,path};
}
