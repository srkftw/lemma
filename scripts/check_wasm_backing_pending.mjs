// SPDX-License-Identifier: Apache-2.0
// Finite original-source native/Wasm failed-I/O relation; no live backing replay.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const [authorityArg,outArg]=process.argv.slice(2);
if(!outArg)throw Error('usage: node scripts/check_wasm_backing_pending.mjs VALIDATED_AUTHORITY UNUSED_OUTPUT');
const a=JSON.parse(fs.readFileSync(authorityArg)),out=path.resolve(outArg),start=performance.now();
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
assert.equal(a.schema,'lemma-portable-backing-pending-authority/1');
assert.deepEqual(a.cases.map(c=>c.name),['partial','barrier']);
for(const id of [a.native_identity,a.portable_identity])assert.match(id,/^[0-9a-f]{64}$/);
assert.notEqual(a.native_identity,a.portable_identity);
assert.equal(sha(fs.readFileSync(a.module)),a.module_sha256);
assert.equal(sha(fs.readFileSync(a.wasm)),a.wasm_sha256);
fs.mkdirSync(out,{recursive:false});
const report={schema:'lemma-portable-backing-pending-relation/1',status:'FAIL',cases:[],
 scope:'two literal native controller cuts and recorded actual POSIX partial-write/barrier failures; no guest-issued Save, cold boot or arbitrary migration claim',
 relation:'Only independently admitted header implementation identities are rebound. Every other checkpoint byte, complete component CRC and recorded outcome byte remains exact. Production restore must reject native identity.',
 limits:{host_seconds:600,total_suffix_cycles:4000,private_barrier_failure_cycles:2000,rss_kib:4194304,output_bytes:4294967296},
 native_identity:a.native_identity,portable_identity:a.portable_identity,authority_sha256:sha(fs.readFileSync(authorityArg))};
const {default:create}=await import(pathToFileURL(a.module));
let core,fd;
const state=()=>core.ccall('lemma_inspect','string',[],[]);
function check(name,types=[],args=[]){if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));}
function rejected(name,types,args){const before=state();assert.notEqual(core.ccall(name,'number',types,args),0);assert.equal(state(),before,'rejection changed logical state');}
function copyMemfs(source,target){const input=core.FS.open(source,'r'),output=fs.openSync(target,'wx'),size=core.FS.stat(source).size;
 try{const chunk=new Uint8Array(1048576);for(let at=0;at<size;at+=chunk.length){const n=Math.min(chunk.length,size-at);assert.equal(core.FS.read(input,chunk,0,n,at),n);assert.equal(fs.writeSync(output,chunk,0,n,at),n);}fs.fsyncSync(output);}
 finally{core.FS.close(input);fs.closeSync(output);core.FS.unlink(source);}return size;}
function compare(native,portable){const n=fs.statSync(native).size;assert.equal(fs.statSync(portable).size,n);const x=Buffer.alloc(1048576),y=Buffer.alloc(1048576),nf=fs.openSync(native,'r'),pf=fs.openSync(portable,'r');
 try{for(let at=0;at<n;at+=x.length){const count=Math.min(x.length,n-at);assert.equal(fs.readSync(nf,x,0,count,at),count);assert.equal(fs.readSync(pf,y,0,count,at),count);
  if(at===0){assert.equal(x.subarray(0,8).toString(),'LMSSRTL1');assert.equal(x.readBigUInt64LE(8),2n);assert.equal(x.subarray(16,80).toString(),a.native_identity);assert.equal(y.subarray(16,80).toString(),a.portable_identity);assert.deepEqual(x.subarray(0,16),y.subarray(0,16));assert.deepEqual(x.subarray(80,count),y.subarray(80,count));}
  else assert.deepEqual(x.subarray(0,count),y.subarray(0,count));}}
 finally{fs.closeSync(nf);fs.closeSync(pf);}return n;}
function snapshot(name){const before=state();check('lemma_snapshot',['string'],['/snapshot.bin']);assert.equal(state(),before);const target=path.join(out,name);copyMemfs('/snapshot.bin',target);return target;}
function assets(){for(const [target,item]of Object.entries(a.assets)){const bytes=fs.readFileSync(item.path);assert.equal(sha(bytes),item.sha256);core.FS.writeFile(target,bytes);}}
try{
 for(const cut of a.cases){assert((performance.now()-start)/1000<600);assert.equal(cut.suffix_cycles,2000);
  core=await create();core.FS.mkdir('/forks');let seedReads=0,seeding=true,originalCalls=0,privateCalls={read:0,write:0,barrier:0};
  // Creation observes an explicitly blank disposable medium before any CPU
  // clock. Restore then replaces it with its snapshot-owned private bytes.
  const blankBacking={getSize:()=>268435456,read(b){if(seeding){seedReads++;b.fill(0);return b.length;}originalCalls++;throw Error('original read');},write(){originalCalls++;throw Error('original write');},flush(){originalCalls++;throw Error('original barrier');}};
  core.backing=blankBacking;assets();
  check('lemma_create');seeding=false;assert.equal(JSON.parse(state()).cycle,0);const original=fs.readFileSync(cut.snapshot);assert.equal(sha(original),cut.snapshot_sha256);
  core.FS.writeFile('/foreign.bin',original);rejected('lemma_restore',['string'],['/foreign.bin']);core.FS.unlink('/foreign.bin');
  assert.equal(original.subarray(16,80).toString(),a.native_identity);original.write(a.portable_identity,16,64,'ascii');
  original[original.length-1]^=1;core.FS.writeFile('/corrupt.bin',original);rejected('lemma_restore',['string'],['/corrupt.bin']);core.FS.unlink('/corrupt.bin');original[original.length-1]^=1;
  core.FS.writeFile('/pending.bin',original);check('lemma_restore',['string'],['/pending.bin']);core.FS.unlink('/pending.bin');
  const prefix=snapshot(cut.name+'-portable-prefix.snap'),bytes=compare(cut.snapshot,prefix);
  assert.equal(JSON.parse(state()).backing_io.fork_suspended,true);rejected('lemma_run',['number'],[1]);
  check('lemma_export_private',['string'],['/private.raw']);const medium=path.join(out,cut.name+'-private.raw');copyMemfs('/private.raw',medium);fd=fs.openSync(medium,'r+');
  const privateBacking={getSize:()=>fs.fstatSync(fd).size,
   read(b,{at}){privateCalls.read++;return fs.readSync(fd,b,0,b.length,at);},
   write(b,{at}){privateCalls.write++;return fs.writeSync(fd,b,0,b.length,at);},
   flush(){privateCalls.barrier++;fs.fsyncSync(fd);}};core.backing=privateBacking;
  check('lemma_rebind_private');const tape=fs.readFileSync(cut.tape);assert.equal(sha(tape),cut.tape_sha256);assert.equal(tape.subarray(0,8).toString(),'LMIOLOG2');assert.equal(tape.subarray(8,72).toString(),a.native_identity);
  core.FS.writeFile('/foreign.io',tape);rejected('lemma_backing_outcomes',['string'],['/foreign.io']);core.FS.unlink('/foreign.io');
  tape.write(a.portable_identity,8,64,'ascii');tape[tape.length-1]^=1;core.FS.writeFile('/corrupt.io',tape);rejected('lemma_backing_outcomes',['string'],['/corrupt.io']);core.FS.unlink('/corrupt.io');tape[tape.length-1]^=1;
  core.FS.writeFile('/suffix.io',tape);check('lemma_backing_outcomes',['string'],['/suffix.io']);core.FS.unlink('/suffix.io');
  check('lemma_run',['number'],[cut.suffix_cycles]);assert.equal(sha(fs.readFileSync(cut.final_snapshot)),cut.final_snapshot_sha256);
  const final=snapshot(cut.name+'-portable-final.snap');compare(cut.final_snapshot,final);assert.equal(originalCalls,0,'replay contacted original backing');
  const finalState=JSON.parse(state());assert.equal(finalState.backing_io.completed,1);assert.equal(finalState.backing_io.durable_barrier,0);
  if(cut.name==='partial'){const b=Buffer.alloc(4);assert.equal(fs.readSync(fd,b,0,4,1536),4);assert.deepEqual(b,Buffer.from([0x91,0x91,0,0]));assert.equal(privateCalls.write,1);}
  if(cut.name==='barrier')assert.equal(privateCalls.barrier,1,'failed original barrier still requires a real private replay barrier');
  report.cases.push({name:cut.name,checkpoint_bytes:bytes,suffix_cycles:cut.suffix_cycles,
   complete_authoritative_prefix_and_suffix_equal:true,foreign_identity_corruption_and_no_tape_rejected:true,
   private_calls:privateCalls,blank_creation_reads:seedReads,wasm_heap_bytes:core.HEAPU8.byteLength,no_original_contact:true});
  if(cut.name==='barrier'){
   // A local replay failure cannot become the recorded guest failure or a
   // completed fork. The owner must stop further clocks and checkpoints.
   // Use a fresh instance: an existing replay owner already retains its tape.
   core.ccall('lemma_destroy',null,[],[]);core=null;global.gc?.();core=await create();core.FS.mkdir('/forks');
   seeding=true;core.backing=blankBacking;assets();check('lemma_create');seeding=false;
   core.FS.writeFile('/pending.bin',original);check('lemma_restore',['string'],['/pending.bin']);core.FS.unlink('/pending.bin');
   let failures=0;core.backing={...privateBacking,flush(){failures++;throw Error('private barrier unavailable');}};check('lemma_rebind_private');
   core.FS.writeFile('/suffix.io',tape);check('lemma_backing_outcomes',['string'],['/suffix.io']);core.FS.unlink('/suffix.io');
   assert.notEqual(core.ccall('lemma_run','number',['number'],[2000]),0,'local failed barrier admitted');
   const poisoned=JSON.parse(state());assert.equal(failures,1);assert.equal(poisoned.backing_io.poisoned,true);assert.equal(poisoned.backing_io.completed,0);assert.equal(poisoned.backing_io.durable_barrier,0);
   rejected('lemma_run',['number'],[1]);rejected('lemma_snapshot',['string'],['/poisoned.snap']);assert.equal(originalCalls,0);
   report.cases.at(-1).private_barrier_failure_stops_without_completion=true;
  }
  core.ccall('lemma_destroy',null,[],[]);core=null;fs.closeSync(fd);fd=undefined;global.gc?.();
 }
 report.status='PASS';
}catch(error){report.error=String(error);process.exitCode=1;if(core)report.failed_state=state();}
finally{core?.ccall('lemma_destroy',null,[],[]);if(fd!==undefined)fs.closeSync(fd);report.host_seconds=(performance.now()-start)/1000;report.peak_rss_kib=process.resourceUsage().maxRSS;report.observer_sha256=sha(fs.readFileSync(new URL(import.meta.url)));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,error:report.error,cases:report.cases.length}));}
