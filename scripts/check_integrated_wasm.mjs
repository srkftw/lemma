// SPDX-License-Identifier: Apache-2.0
// Real portable Integrated15 ROM/NV execution, with two distinct opaque stores.
// This finite continuation case is not notebook Ready or browser OPFS evidence.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const [buildArg,preparedArg,bootArg,userArg,outArg]=process.argv.slice(2);
if(!outArg)throw Error('usage: check_integrated_wasm.mjs WASM_BUILD PREPARED BOOT_MEDIUM USER_MEDIUM UNUSED_OUTPUT');
const [build,prepared,boot,user,out]=[buildArg,preparedArg,bootArg,userArg,outArg].map(p=>path.resolve(p));
fs.mkdirSync(out,{recursive:false});
const start=performance.now(),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const production=JSON.parse(fs.readFileSync(path.join(build,'build.json'))),admission=JSON.parse(fs.readFileSync(path.join(prepared,'prepared.json')));
assert.equal(production.profile,'lemma-silicon-dev/0.15.0');assert.equal(production.status,'BUILT');assert.equal(admission.profile,production.profile);
for(const [name,pin]of Object.entries(production.outputs))assert.equal(sha(fs.readFileSync(path.join(build,name))),pin);
const counters={boot:{reads:0,writes:0,flushes:0},user:{reads:0,writes:0,flushes:0}};
const fds=[];let core;
function backing(file,counts){const fd=fs.openSync(file,'r');fds.push(fd);const size=fs.fstatSync(fd).size;return {
 getSize:()=>size,read(p,{at}){assert(Number.isSafeInteger(at)&&at>=0&&at+p.length<=size);counts.reads++;return fs.readSync(fd,p,0,p.length,at);},
 write(){counts.writes++;throw Error('predeclared read-only ROM-stage case attempted write');},flush(){counts.flushes++;}
};}
function check(name,types=[],args=[]){assert.equal(core.ccall(name,'number',types,args),0,core.ccall('lemma_error','string',[],[]));}
function state(){return JSON.parse(core.ccall('lemma_inspect','string',[],[]));}
function bound(){assert((performance.now()-start)/1000<300,'original300s deadline');}
const report={schema:'lemma-integrated15-portable-rom-case/1',result:'FAIL',limits:{wall_seconds:300,cycles:200000},
 inputs:{producer:sha(fs.readFileSync(path.join(build,'build.json'))),prepared:sha(fs.readFileSync(path.join(prepared,'prepared.json'))),boot:sha(fs.readFileSync(boot)),user:sha(fs.readFileSync(user)),observer:sha(fs.readFileSync(new URL(import.meta.url)))},
 scope:'real Wasm RTL, actual Lean ROM and separate boot/user byte stores; initial finite synthetic-stimulus checkpoint case',
 excluded:['notebook Ready','ordinary browser school workflow','OPFS crash durability','active converter acquisition','arbitrary exact continuation','cross-backend microstate migration','physical qualification']};
try{
 const {default:create}=await import(pathToFileURL(path.join(build,'machine.mjs')));core=await create();
 core.backing=backing(user,counters.user);core.bootBacking=backing(boot,counters.boot);core.FS.mkdir('/forks');
 core.FS.writeFile('/boot.bin',fs.readFileSync(path.join(admission.rom_build,'component/rom.bin')));
 core.FS.writeFile('/descriptor.bin',fs.readFileSync(path.join(prepared,'descriptor.bin')));
 // No ELF or DTB is ever preloaded by this observer or Product create path.
 check('lemma_create');assert.equal(state().cycle,0);assert.equal(state().boot_backing.enabled,true);
 check('lemma_event',['string'],['100 multimodal 0 123 10 7']);check('lemma_event',['string'],['110000 multimodal 7 456 3 1']);
 check('lemma_snapshot',['string'],['/cut.chk']);const cut=core.FS.readFile('/cut.chk');report.cut_sha256=sha(cut);
 for(let i=0;i<20;i++){bound();check('lemma_run',['number'],[10000]);}
 report.final=state();assert.equal(report.final.cycle,200000);assert.equal(report.final.event_queue,0);assert.equal(report.final.finished,false);
 check('lemma_snapshot',['string'],['/suffix.chk']);const original=core.FS.readFile('/suffix.chk');report.suffix_sha256=sha(original);report.checkpoint_bytes=original.length;
 check('lemma_restore',['string'],['/cut.chk']);for(let i=0;i<20;i++){bound();check('lemma_run',['number'],[10000]);}
 check('lemma_snapshot',['string'],['/fork.chk']);assert.deepEqual(core.FS.readFile('/fork.chk'),original,'complete same-Wasm serialized suffix differs');
 report.same_backend_suffix=true;report.backing_calls=counters;report.wasm_heap_bytes=core.HEAPU8.length;report.result='PASS_FINITE_ROM_CASE';
}catch(error){report.error=String(error);process.exitCode=1;if(core)report.failed_state=state();}
finally{core?.ccall('lemma_destroy',null,[],[]);for(const fd of fds)fs.closeSync(fd);report.wall_seconds=(performance.now()-start)/1000;report.peak_rss_bytes=process.resourceUsage().maxRSS*1024;fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
