// SPDX-License-Identifier: Apache-2.0
// Finite same-circuit native/Wasm serialized-state relation, not migration.
// Only independently admitted implementation identity bytes are rebound.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const [authorityArg,outArg]=process.argv.slice(2);
if(!outArg)throw Error('usage: node scripts/check_wasm_clocked_pending.mjs VALIDATED_AUTHORITY UNUSED_OUTPUT');
const a=JSON.parse(fs.readFileSync(authorityArg)),out=path.resolve(outArg),started=performance.now();
assert.equal(a.schema,'lemma-clocked-portable-pending-authority/1');
assert.match(a.native_identity,/^[0-9a-f]{64}$/);assert.match(a.portable_identity,/^[0-9a-f]{64}$/);assert.notEqual(a.native_identity,a.portable_identity);
assert.equal(a.cases.length,9);assert.deepEqual(new Set(a.cases.map(c=>c.name)),new Set(['startup','reset','physical-send','physical-receive','physical-guard','physical-chip-send','owned-submit','owned-receive','domain-reset']));
fs.mkdirSync(out,{recursive:false});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const receipt={schema:'lemma-clocked-native-wasm-pending-relation/1',status:'FAIL',
 scope:'finite same-circuit native/Wasm serialization and recorded-outcome suffix relation at nine actual guest cuts; no cold prefix run or live peer',
 relation:'Snapshot header bytes16..79 and tape first-line implementation identity are explicitly rebound to the admitted portable producer before restore. Every other snapshot byte, component CRC and tape byte is unchanged. Production restore must reject native identity.',
 bounds:{host_seconds:1800,total_suffix_cycles:70000000,maximum_rss_kib:4194304,maximum_output_bytes:12000000000},
 native_identity:a.native_identity,portable_identity:a.portable_identity,authority_sha256:sha(fs.readFileSync(authorityArg)),cases:[],
 excluded:['arbitrary host/QEMU microstate migration','full Clocked notebook or browser workflow','full USB MAC/timing/topology/electrical/analog CDC','privately live peer continuation']};
let core;
const bound=()=>assert((performance.now()-started)/1000<=1800,'predeclared host deadline');
assert.equal(sha(fs.readFileSync(a.module)),a.module_sha256,'changed portable module');
assert.equal(sha(fs.readFileSync(a.wasm)),a.wasm_sha256,'changed portable Wasm');
const {default:create}=await import(pathToFileURL(a.module));
function check(name,types=[],args=[]){const result=core.ccall(name,'number',types,args);if(result)throw Error(core.ccall('lemma_error','string',[],[]));}
function state(){return core.ccall('lemma_inspect','string',[],[]);}
function rejected(name,types=[],args=[]){const before=state();assert.notEqual(core.ccall(name,'number',types,args),0,name+' admitted');assert.equal(state(),before,'negative mutated logical state');}
function publishSnapshot(name){check('lemma_snapshot',['string'],['/snapshot.bin']);const p=path.join(out,name),input=core.FS.open('/snapshot.bin','r'),fd=fs.openSync(p,'wx'),size=core.FS.stat('/snapshot.bin').size;
 try{const bytes=new Uint8Array(1048576);for(let at=0;at<size;at+=bytes.length){const n=Math.min(bytes.length,size-at);assert.equal(core.FS.read(input,bytes,0,n,at),n);assert.equal(fs.writeSync(fd,bytes,0,n,at),n);}fs.fsyncSync(fd);}
 finally{core.FS.close(input);fs.closeSync(fd);core.FS.unlink('/snapshot.bin');}return p;}
function compareCheckpoint(native,portable){const n=fs.statSync(native).size;assert.equal(fs.statSync(portable).size,n,'checkpoint length');const x=Buffer.alloc(1048576),y=Buffer.alloc(1048576),na=fs.openSync(native,'r'),pa=fs.openSync(portable,'r');
 try{for(let at=0;at<n;at+=x.length){const count=Math.min(x.length,n-at);assert.equal(fs.readSync(na,x,0,count,at),count);assert.equal(fs.readSync(pa,y,0,count,at),count);
  if(!at){assert.equal(x.subarray(0,8).toString(),'LMSSRTL1');assert.equal(x.readBigUInt64LE(8),10n);assert.equal(x.subarray(16,80).toString(),a.native_identity);assert.equal(y.subarray(16,80).toString(),a.portable_identity);assert.deepEqual(x.subarray(0,16),y.subarray(0,16));assert.deepEqual(x.subarray(80,count),y.subarray(80,count));}
  else assert.deepEqual(x.subarray(0,count),y.subarray(0,count));}}
 finally{fs.closeSync(na);fs.closeSync(pa);}return n;}
function reboundTape(p,expected){const raw=fs.readFileSync(p);assert.equal(sha(raw),expected,'changed captured tape');const text=raw.toString('utf8');assert(text.startsWith('LMUSBRP1 '+a.native_identity+'\n'));return text.replace('LMUSBRP1 '+a.native_identity+'\n','LMUSBRP1 '+a.portable_identity+'\n');}
try{
 let total=0;
 for(const cut of a.cases){bound();assert(Number.isSafeInteger(cut.suffix_cycles)&&cut.suffix_cycles>0);total+=cut.suffix_cycles;assert(total<=70000000);
  core=await create();core.FS.mkdir('/forks');core.backing=new Proxy({}, {get(){throw Error('private USB relation contacted an external backing');}});
  check('lemma_create_usb_private');const original=fs.readFileSync(cut.snapshot);assert.equal(sha(original),cut.snapshot_sha256);core.FS.writeFile('/foreign.bin',original);
  rejected('lemma_restore',['string'],['/foreign.bin']);core.FS.unlink('/foreign.bin');
  assert.equal(original.subarray(16,80).toString(),a.native_identity);a.portable_identity.split('').forEach((char,index)=>{original[16+index]=char.charCodeAt(0);});
  original[original.length-1]^=1;core.FS.writeFile('/corrupt.bin',original);rejected('lemma_restore',['string'],['/corrupt.bin']);core.FS.unlink('/corrupt.bin');original[original.length-1]^=1;
  core.FS.writeFile('/pending.bin',original);check('lemma_restore',['string'],['/pending.bin']);core.FS.unlink('/pending.bin');
  const prefix=publishSnapshot(cut.name+'-portable-prefix.snap'),bytes=compareCheckpoint(cut.snapshot,prefix);
  const inspected=JSON.parse(state());assert.equal(inspected.cycle,cut.snapshot_cycle);assert.equal(inspected.usb.fork_suspended,true);assert.equal(inspected.usb_clocks.position,0);
  assert.equal(inspected.usb_clocks.host_ppm,2500);assert.equal(inspected.usb_clocks.chip_ppm,-2500);assert.equal(inspected.usb_clocks.host_initial_phase,7);assert.equal(inspected.usb_clocks.chip_initial_phase,38);
  rejected('lemma_run',['number'],[1]);
  core.FS.writeFile('/foreign.tape',fs.readFileSync(cut.tape));rejected('lemma_usb_outcomes',['string'],['/foreign.tape']);core.FS.unlink('/foreign.tape');
  const tape=reboundTape(cut.tape,cut.tape_sha256),bad=tape.slice(0,-3)+(tape.at(-3)==='0'?'1':'0')+tape.slice(-2);core.FS.writeFile('/bad.tape',bad);rejected('lemma_usb_outcomes',['string'],['/bad.tape']);core.FS.unlink('/bad.tape');
  core.FS.writeFile('/prefix.tape',reboundTape(cut.prefix_tape,cut.prefix_tape_sha256));check('lemma_usb_outcomes',['string'],['/prefix.tape']);rejected('lemma_run',['number'],[1]);core.FS.unlink('/prefix.tape');
  core.FS.writeFile('/suffix.tape',tape);check('lemma_usb_outcomes',['string'],['/suffix.tape']);core.FS.unlink('/suffix.tape');rejected('lemma_run',['number'],[cut.suffix_cycles+1]);
  const before=performance.now();check('lemma_run',['number'],[cut.suffix_cycles]);const final=publishSnapshot(cut.name+'-portable-final.snap');assert.equal(sha(fs.readFileSync(cut.final_snapshot)),cut.final_snapshot_sha256,'changed native final checkpoint');compareCheckpoint(cut.final_snapshot,final);
  const expectedUart=fs.readFileSync(cut.uart);assert.equal(sha(expectedUart),cut.uart_sha256,'changed native UART');assert.deepEqual(Buffer.from(core.FS.readFile('/uart.bin')),expectedUart,'exact actual guest UART suffix');
  const row={name:cut.name,snapshot_cycle:cut.snapshot_cycle,suffix_cycles:cut.suffix_cycles,checkpoint_bytes:bytes,
   complete_authoritative_prefix_and_suffix_equal:true,foreign_identity_no_tape_corrupt_horizon_reject_unchanged:true,actual_uart_suffix_equal:true,
   suffix_seconds:(performance.now()-before)/1000,wasm_heap_bytes:core.HEAPU8.byteLength};receipt.cases.push(row);console.log(JSON.stringify(row));
  if(cut.semantic_tape){
   check('lemma_destroy');core=null;global.gc?.();core=await create();core.FS.mkdir('/forks');check('lemma_create_usb_private');
   core.FS.writeFile('/pending.bin',original);check('lemma_restore',['string'],['/pending.bin']);core.FS.unlink('/pending.bin');
   core.FS.writeFile('/semantic.tape',reboundTape(cut.semantic_tape,cut.semantic_tape_sha256));check('lemma_usb_outcomes',['string'],['/semantic.tape']);core.FS.unlink('/semantic.tape');
   assert.notEqual(core.ccall('lemma_run','number',['number'],[cut.suffix_cycles]),0,'checksum-valid future error admitted');
   assert(JSON.parse(state()).usb_clocks.position>0,'semantic failure did not expose actual partial physical clock');
   rejected('lemma_run',['number'],[1]);rejected('lemma_snapshot',['string'],['/interrupted.snap']);
   row.actual_semantic_future_mismatch_and_partial_cycle_rejections=true;
  }
  check('lemma_destroy');core=null;global.gc?.();
 }
 receipt.status='PASS';receipt.total_suffix_cycles=total;receipt.no_external_peer=true;
}catch(error){receipt.error=String(error);process.exitCode=1;if(core)receipt.failedState=state();}
finally{core?.ccall('lemma_destroy',null,[],[]);receipt.host_seconds=(performance.now()-started)/1000;receipt.host_peak_rss_kib=process.resourceUsage().maxRSS;receipt.observer_sha256=sha(fs.readFileSync(new URL(import.meta.url)));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({status:receipt.status,error:receipt.error,cases:receipt.cases.length}));}
