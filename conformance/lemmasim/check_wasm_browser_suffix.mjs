// Compare an actual browser-exported arbitrary boundary and suffix against
// the identical Wasm machine on a native host. No cold-recovery claim.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';

const [bundle,prefixFile,suffixFile,output]=process.argv.slice(2);
if(!output)throw Error('Usage: node check_wasm_browser_suffix.mjs BUNDLE PREFIX SUFFIX NEW_OUTPUT');
fs.mkdirSync(output,{recursive:false});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const start=performance.now(),result={status:'FAIL',scope:'same Wasm implementation: real browser arbitrary-boundary archive and exact applicable suffix; not cold recovery or C++/Wasm microstate migration'};
let core,fd;
try{
 result.observerSha256=sha(fs.readFileSync(new URL(import.meta.url)));
 const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'bundle.json')));
 if(manifest.schema!=='lemmasim-browser-bundle/1')throw Error('Unsupported bundle');
 for(const [name,want] of Object.entries(manifest.files))if(sha(fs.readFileSync(path.join(bundle,name)))!==want)throw Error('Bundle file changed: '+name);
 const prefix=fs.readFileSync(prefixFile),expected=fs.readFileSync(suffixFile);
 for(const b of [prefix,expected])if(b.subarray(0,8).toString()!=='LMSSRTL1'||b.readBigUInt64LE(8)!==1n)throw Error('Invalid archive header');
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
 // Constructor capacity only. It may not read, write or acknowledge any
 // original backing store before the checkpoint has been restored.
 core.backing={getSize:()=>268435456,read:()=>{throw Error('Unexpected original backing read');},write:()=>{throw Error('Unexpected original backing write');},flush:()=>{throw Error('Unexpected original backing barrier');}};
 function call(name,types=[],args=[]){if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));}
 call('lemma_create');core.FS.writeFile('/incoming.bin',prefix);call('lemma_restore',['string'],['/incoming.bin']);core.FS.unlink('/incoming.bin');
 call('lemma_export',['string'],['/opaque.raw']);
 const medium=core.FS.readFile('/opaque.raw');core.FS.unlink('/opaque.raw');
 const privatePath=path.join(output,'private.raw');fd=fs.openSync(privatePath,'wx+',0o600);
 for(let offset=0;offset<medium.length;offset+=1048576){const b=medium.subarray(offset,offset+1048576);if(fs.writeSync(fd,b,0,b.length,offset)!==b.length)throw Error('Partial private backing copy');}
 fs.fsyncSync(fd);core.backing={getSize:()=>fs.fstatSync(fd).size,read:(b,o)=>fs.readSync(fd,b,0,b.length,o.at),write:(b,o)=>fs.writeSync(fd,b,0,b.length,o.at),flush:()=>fs.fsyncSync(fd)};
 call('lemma_rebind_private');
 const exact=s=>JSON.parse(s.replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(all,n)=>n===undefined?all:JSON.stringify(n)));
 const initial=exact(core.ccall('lemma_inspect','string',[],[]));if(BigInt(initial.cycle)!==first||!initial.isolated_medium)throw Error('Wrong restored boundary');
 if(initial.backing_io.phase==='1')throw Error('Synchronous contract cannot admit a pending external callback');
 result.initial=initial;
 for(let left=last-first;left>0n;){const amount=left<50000n?left:50000n;call('lemma_run',['number'],[Number(amount)]);left-=amount;}
 call('lemma_snapshot',['string'],['/actual.bin']);const actual=Buffer.from(core.FS.readFile('/actual.bin'));
 fs.writeFileSync(path.join(output,'actual.bin'),actual);
 if(!actual.equals(expected))throw Error('Actual browser/native-host Wasm authoritative suffix archive differs');
 result.status='PASS';result.exactArchiveSha256=sha(actual);result.final=exact(core.ccall('lemma_inspect','string',[],[]));result.wasmHeapBytes=core.HEAPU8.byteLength;
}catch(error){result.error=String(error);process.exitCode=1;}
finally{try{core?.ccall('lemma_destroy',null,[],[]);}catch(error){result.status='FAIL';result.cleanupError=String(error);process.exitCode=1;}if(fd!==undefined)fs.closeSync(fd);result.hostPeakRssBytes=process.resourceUsage().maxRSS*1024;result.hostSeconds=(performance.now()-start)/1000;fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
