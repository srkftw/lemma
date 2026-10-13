// Compare an actual browser-exported arbitrary boundary and suffix against
// the identical Wasm machine on a native host. No cold-recovery claim.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [bundle,prefixFile,suffixFile,output,outcomesFile]=process.argv.slice(2);
if(!output)throw Error('Usage: node check_wasm_browser_suffix.mjs BUNDLE PREFIX SUFFIX NEW_OUTPUT [ACTUAL_OUTCOMES]');
fs.mkdirSync(output,{recursive:false});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const start=performance.now(),result={status:'FAIL',scope:'same Wasm implementation: real browser arbitrary-boundary archive and exact applicable suffix; not cold recovery or C++/Wasm microstate migration'};
let core,fd;
try{
 result.observerSha256=sha(fs.readFileSync(new URL(import.meta.url)));
 const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'bundle.json')));
 if(manifest.schema!=='lemmasim-browser-bundle/1'||manifest.profile!=='lemma-silicon-dev/0.3.0')throw Error('Unsupported canonical browser bundle');
 for(const [name,want] of Object.entries(manifest.files))if(sha(fs.readFileSync(path.join(bundle,name)))!==want)throw Error('Bundle file changed: '+name);
 const buildBytes=fs.readFileSync(path.join(bundle,'wasm-build.json')),build=JSON.parse(buildBytes);
 if(sha(buildBytes)!==manifest.wasm_build_sha256||build.status!=='BUILT'||!/^[a-f0-9]{64}$/.test(build.snapshot_identity))throw Error('Unqualified Wasm implementation identity');
 const prefix=fs.readFileSync(prefixFile),expected=fs.readFileSync(suffixFile);
 // Canonical0.3's source-bound Pending state contract is container2. It
 // retains the112-byte header; historical container1 is not reinterpreted.
 for(const b of [prefix,expected]){
  if(b.length<128||b.length>768*1048576||b.subarray(0,8).toString()!=='LMSSRTL1'||b.readBigUInt64LE(8)!==2n)throw Error('Invalid canonical container2 archive header');
  if(b.subarray(16,80).toString()!==build.snapshot_identity)throw Error('Archive is not this compiled Wasm implementation');
  const wrapper=b.readBigUInt64LE(80),model=b.readBigUInt64LE(88);
  if(wrapper<16n||model===0n||model>64n*1048576n||wrapper+model!==BigInt(b.length-112))throw Error('Invalid archive component bounds');
 }
 if(!prefix.subarray(16,80).equals(expected.subarray(16,80)))throw Error('Implementation identities differ');
 const first=prefix.readBigUInt64LE(120),last=expected.readBigUInt64LE(120);
 if(last<=first||last-first>64000000n)throw Error('Suffix exceeds declared 64M-cycle bound');
 result.input={bundleSha256:sha(fs.readFileSync(path.join(bundle,'bundle.json'))),prefixSha256:sha(prefix),suffixSha256:sha(expected),firstCycle:String(first),lastCycle:String(last),cycles:String(last-first)};
 const {default:create}=await import(pathToFileURL(path.resolve(bundle,'machine.mjs')));
 core=await create({wasmBinary:fs.readFileSync(path.join(bundle,'machine.wasm'))});
 for(const [to,item] of [['/image.elf',manifest.workloads.notebook.image],['/machine.dtb',manifest.workloads.notebook.dtb],['/descriptor.bin',manifest.workloads.notebook.descriptor],['/boot.bin',manifest.rom]]){
  const b=fs.readFileSync(path.join(bundle,item.path));if(sha(b)!==item.sha256)throw Error('Guest artifact changed: '+item.path);core.FS.writeFile(to,b);
 }
 core.FS.mkdir('/forks');
 // Attach samples the backing before restore. Supply a fresh empty private
 // origin for that constructor, never the original file or peer. Restore
 // replaces its accepted-byte view from the archive before any target cycle.
 core.backing={getSize:()=>268435456,read:b=>{b.fill(0);return b.length;},write:()=>{throw Error('Unexpected constructor backing write');},flush:()=>{throw Error('Unexpected constructor backing barrier');}};
 function call(name,types=[],args=[]){if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));}
 call('lemma_create');core.FS.writeFile('/incoming.bin',prefix);call('lemma_restore',['string'],['/incoming.bin']);core.FS.unlink('/incoming.bin');
 // Export only the restored accepted-byte view. A saved Pending request is
 // never retried against the original adapter or an invented live peer.
 call('lemma_export_private',['string'],['/opaque.raw']);
 const privatePath=path.join(output,'private.raw');fd=fs.openSync(privatePath,'wx+',0o600);
 const mediumSize=core.FS.stat('/opaque.raw').size;
 if(mediumSize!==268435456)throw Error('Wrong private backing capacity');
 fs.ftruncateSync(fd,mediumSize);
 const stream=core.FS.open('/opaque.raw','r'),chunk=Buffer.alloc(1048576);
 try{for(let offset=0;offset<mediumSize;offset+=chunk.length){
  const length=Math.min(chunk.length,mediumSize-offset);
  if(core.FS.read(stream,chunk,0,length,offset)!==length)throw Error('Partial accepted backing export');
  // An exclusively created, extended POSIX file reads holes as zero. Skip
  // only independently observed zero chunks; every other byte is copied.
  if(chunk.subarray(0,length).some(value=>value!==0)&&fs.writeSync(fd,chunk,0,length,offset)!==length)throw Error('Partial private backing copy');
 }}finally{core.FS.close(stream);core.FS.unlink('/opaque.raw');}
 fs.fsyncSync(fd);core.backing={getSize:()=>fs.fstatSync(fd).size,read:(b,o)=>fs.readSync(fd,b,0,b.length,o.at),write:(b,o)=>fs.writeSync(fd,b,0,b.length,o.at),flush:()=>fs.fsyncSync(fd)};
 call('lemma_rebind_private');
 const exact=s=>JSON.parse(s.replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(all,n)=>n===undefined?all:JSON.stringify(n)));
 const initial=exact(core.ccall('lemma_inspect','string',[],[]));if(BigInt(initial.cycle)!==first||!initial.isolated_medium)throw Error('Wrong restored boundary');
 if(initial.backing_io.phase==='1'&&!outcomesFile)throw Error('Pending continuation requires its captured actual outcome tape');
 if(outcomesFile){
  const tape=fs.readFileSync(outcomesFile);
  if(tape.length<72||tape.length>64*1048576||tape.subarray(0,8).toString()!=='LMIOLOG2'||tape.subarray(8,72).toString()!==build.snapshot_identity)throw Error('Invalid implementation-bound outcome tape');
  core.FS.writeFile('/actual-outcomes.io',tape);call('lemma_backing_outcomes',['string'],['/actual-outcomes.io']);core.FS.unlink('/actual-outcomes.io');
  result.input.outcomesSha256=sha(tape);
 }
 result.initial=initial;
 for(let left=last-first;left>0n;){const amount=left<50000n?left:50000n;call('lemma_run',['number'],[Number(amount)]);left-=amount;}
 call('lemma_snapshot',['string'],['/actual.bin']);const actual=Buffer.from(core.FS.readFile('/actual.bin'));
 fs.writeFileSync(path.join(output,'actual.bin'),actual);
 if(!actual.equals(expected))throw Error('Actual browser/native-host Wasm authoritative suffix archive differs');
 result.status='PASS';result.exactArchiveSha256=sha(actual);result.final=exact(core.ccall('lemma_inspect','string',[],[]));result.wasmHeapBytes=core.HEAPU8.byteLength;
}catch(error){result.error=String(error);process.exitCode=1;}
finally{try{core?.ccall('lemma_destroy',null,[],[]);}catch(error){result.status='FAIL';result.cleanupError=String(error);process.exitCode=1;}if(fd!==undefined)fs.closeSync(fd);result.hostPeakRssBytes=process.resourceUsage().maxRSS*1024;result.hostSeconds=(performance.now()-start)/1000;fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
