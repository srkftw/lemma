// SPDX-License-Identifier: Apache-2.0
// Real generated circuitry on native and Wasm hosts; no target interpretation.
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL}from'node:url';
import {spawn}from'node:child_process';import readline from'node:readline';import crypto from'node:crypto';
const [wasmBuild,nativeBinary,guestBuild,rom,medium,output]=process.argv.slice(2);
if(!output)throw Error('Usage: node check_wasm_machine.mjs WASM_BUILD NATIVE_BINARY GUEST_BUILD ROM MEDIUM NEW_OUTPUT');
fs.mkdirSync(output,{recursive:false});let child,core,fd;const result={status:'FAIL',scope:'predeclared 1M+1M real cycles; exact wrapper bytes and native/Wasm UART/pixels; same-Wasm checkpoint suffix'};
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const parse=s=>JSON.parse(s.replace(/"(?:\\.|[^"\\])*"|(-?\d+)/g,(all,n)=>n===undefined?all:JSON.stringify(n)));
function wrapper(b){if(b.subarray(0,8).toString()!=='LMSSRTL1')throw Error('Bad checkpoint');const n=Number(b.readBigUInt64LE(80));return b.subarray(112,112+n);}
function model(b){const n=Number(b.readBigUInt64LE(80));return b.subarray(112+n);}
const start=performance.now();
try{
 result.observerSha256=sha(fs.readFileSync(new URL(import.meta.url)));
 const m=JSON.parse(fs.readFileSync(path.join(wasmBuild,'build.json')));if(m.status!=='BUILT')throw Error('Wasm build not qualified');
 result.identities={wasm:sha(fs.readFileSync(path.join(wasmBuild,'machine.wasm'))),native:sha(fs.readFileSync(nativeBinary)),guest:sha(fs.readFileSync(path.join(guestBuild,'image.elf'))),rom:sha(fs.readFileSync(rom)),initialMedium:sha(fs.readFileSync(medium))};
 const {default:create}=await import(pathToFileURL(path.resolve(wasmBuild,'machine.mjs')));
 core=await create({wasmBinary:fs.readFileSync(path.join(wasmBuild,'machine.wasm'))});
 for(const [to,from]of [['/image.elf',path.join(guestBuild,'image.elf')],['/boot.bin',rom],['/machine.dtb',path.join(guestBuild,'platform.dtb')],['/descriptor.bin',path.join(guestBuild,'descriptor.bin')]])core.FS.writeFile(to,fs.readFileSync(from));
 core.FS.mkdir('/forks');const backingCopy=path.join(output,'wasm.raw');fs.copyFileSync(medium,backingCopy);fd=fs.openSync(backingCopy,'r+');
 core.backing={getSize:()=>fs.fstatSync(fd).size,read:(b,o)=>fs.readSync(fd,b,0,b.length,o.at),write:(b,o)=>fs.writeSync(fd,b,0,b.length,o.at),flush:()=>fs.fsyncSync(fd)};
 function call(name,types=[],args=[]){if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));}
 function snap(name){const p='/'+name;call('lemma_snapshot',['string'],[p]);const b=Buffer.from(core.FS.readFile(p));core.FS.unlink(p);fs.writeFileSync(path.join(output,name),b);return b;}
 call('lemma_create');const nativeCopy=path.join(output,'native.raw');fs.copyFileSync(medium,nativeCopy);
 child=spawn(nativeBinary,['--image',path.join(guestBuild,'image.elf'),'--rom',rom,'--load','0x87e00000:'+path.join(guestBuild,'platform.dtb'),'--descriptor',path.join(guestBuild,'descriptor.bin'),'--medium',nativeCopy,'--session','--quiet-uart','--uart-output',path.join(output,'native-uart.bin'),'--trace-limit','0','--deadline','120','--fork-directory',path.resolve(output)],{stdio:['pipe','pipe','pipe']});
 const pending=[];let childError='';child.on('exit',(code,signal)=>{result.nativeExit={code,signal};});child.stderr.on('data',b=>childError+=b);readline.createInterface({input:child.stdout}).on('line',l=>pending.shift()?.(l));
 async function rpc(line){let timeout;try{const answer=await Promise.race([new Promise(resolve=>{pending.push(resolve);child.stdin.write(line+'\n');}),new Promise((_,reject)=>{timeout=setTimeout(()=>reject(Error('Native RPC timeout: '+childError)),30000);})]);const r=parse(answer);if(!r.ok)throw Error(r.error);return r.result;}finally{clearTimeout(timeout);}}
 for(let i=0;i<20;i++)call('lemma_run',['number'],[50000]);await rpc('run 1000000');
 const before=core.ccall('lemma_inspect','string',[],[]),prefix=snap('wasm-prefix.bin');
 if(core.ccall('lemma_inspect','string',[],[])!==before)throw Error('Snapshot changed live machine');
 await rpc('snapshot '+path.resolve(output,'native-prefix.bin'));
 const nativePrefix=fs.readFileSync(path.join(output,'native-prefix.bin'));
 if(!wrapper(prefix).equals(wrapper(nativePrefix)))throw Error('Native/Wasm authoritative wrapper mismatch');
 for(let i=0;i<20;i++)call('lemma_run',['number'],[50000]);await rpc('run 1000000');
 const suffix=snap('wasm-original.bin');await rpc('snapshot '+path.resolve(output,'native-final.bin'));
 const nativeFinal=fs.readFileSync(path.join(output,'native-final.bin'));
 if(!wrapper(suffix).equals(wrapper(nativeFinal)))throw Error('Native/Wasm suffix wrapper mismatch');
 if(!model(suffix).equals(model(nativeFinal)))throw Error('Native/Wasm generated logical-state suffix mismatch');
 if(!Buffer.from(core.FS.readFile('/uart.bin')).equals(fs.readFileSync(path.join(output,'native-uart.bin'))))throw Error('Native/Wasm UART mismatch');
 const beforeReject=core.ccall('lemma_inspect','string',[],[]),bad=Buffer.from(prefix);bad[112]^=1;core.FS.writeFile('/bad.bin',bad);
 if(core.ccall('lemma_restore','number',['string'],['/bad.bin'])===0)throw Error('Corrupt checkpoint accepted');
 if(core.ccall('lemma_inspect','string',[],[])!==beforeReject)throw Error('Rejected restore altered live state');core.FS.unlink('/bad.bin');
 core.FS.writeFile('/restore.bin',prefix);call('lemma_restore',['string'],['/restore.bin']);core.FS.unlink('/restore.bin');
 for(let i=0;i<20;i++)call('lemma_run',['number'],[50000]);const fork=snap('wasm-fork.bin');
 if(!wrapper(suffix).equals(wrapper(fork))||!model(suffix).equals(model(fork)))throw Error('Same-Wasm exact fork mismatch');
 result.status='PASS';result.prefixCycle='1000000';result.finalCycle='2000000';result.final=parse(core.ccall('lemma_inspect','string',[],[]));
 result.snapshotBytes=prefix.length;result.wrapperSha256=sha(wrapper(suffix));result.sameWasmModelSha256=sha(model(suffix));result.wasmHeapBytes=core.HEAPU8.byteLength;result.hostPeakRssBytes=process.resourceUsage().maxRSS*1024;
 result.acceptanceComplete=true;fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2)+'\n');await rpc('destroy');child.stdin.end();core.ccall('lemma_destroy',null,[],[]);core=null;fs.closeSync(fd);fd=null;
}catch(e){result.error=String(e);process.exitCode=1;}finally{try{core?.ccall('lemma_destroy',null,[],[]);}catch(e){result.cleanupError=String(e);result.status='FAIL';process.exitCode=1;}if(fd!==undefined&&fd!==null)fs.closeSync(fd);if(child&&child.exitCode===null&&child.signalCode===null){child.kill('SIGTERM');await Promise.race([new Promise(resolve=>child.once('exit',resolve)),new Promise(resolve=>setTimeout(resolve,3000))]);if(child.exitCode===null&&child.signalCode===null){child.kill('SIGKILL');await new Promise(resolve=>child.once('exit',resolve));}}result.wallSeconds=(performance.now()-start)/1000;fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));}
