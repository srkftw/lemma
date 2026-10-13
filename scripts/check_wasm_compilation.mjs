// Host-only comparison of two actual RTL Machine Wasm compilations.
// Header bytes16..79 identify the host implementation. Every other byte,
// including both complete authoritative components and their CRCs, is exact.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

const [scalarArg,optimizedArg,outArg]=process.argv.slice(2);
if(!outArg)throw Error('usage: node scripts/check_wasm_compilation.mjs SCALAR_BUNDLE OPTIMIZED_BUNDLE UNUSED_OUTPUT');
const out=path.resolve(outArg);fs.mkdirSync(out,{recursive:false});
const started=performance.now(),MAX_SECONDS=600,MAX_CYCLES=10000000n;
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const receipt={schema:'lemma-wasm-host-compilation-comparison/1',status:'FAIL',
 scope:'real cold RV64 initializer prefix and exact authoritative RTL/state at four declared cuts; notebook Ready and complete browser workflow remain separate',
 observation_relation:'Header implementation identity is checked independently against each admitted build. Bytes0..15 and80..end, including complete state, generated RTL and CRCs, must match. No cross-implementation restore.',
 limits:{cycles:String(MAX_CYCLES),host_seconds:MAX_SECONDS},cuts:['9','32','1000000','10000000'],runs:[]};
function bound(){assert((performance.now()-started)/1000<=MAX_SECONDS,'predeclared host deadline');}
function copyMemfs(core,source,dest){const f=core.FS.open(source,'r'),fd=fs.openSync(dest,'wx'),size=core.FS.stat(source).size;
 try{const b=new Uint8Array(1048576);for(let at=0;at<size;at+=b.length){const n=Math.min(b.length,size-at);assert.equal(core.FS.read(f,b,0,n,at),n);assert.equal(fs.writeSync(fd,b,0,n,at),n);}fs.fsyncSync(fd);}
 finally{core.FS.close(f);fs.closeSync(fd);core.FS.unlink(source);}return size;}
try{
 for(const [label,arg]of [['scalar',scalarArg],['optimized',optimizedArg]]){
  const bundle=path.resolve(arg),m=JSON.parse(fs.readFileSync(path.join(bundle,'bundle.json')));
  assert.equal(m.profile,'lemma-silicon-dev/0.3.0');assert.equal(m.schema,'lemmasim-browser-bundle/1');
  for(const [name,want]of Object.entries(m.files))assert.equal(sha(fs.readFileSync(path.join(bundle,name))),want,name);
  const build=JSON.parse(fs.readFileSync(path.join(bundle,'wasm-build.json')));
  assert.equal(sha(fs.readFileSync(path.join(bundle,'wasm-build.json'))),m.wasm_build_sha256);
  assert.equal(build.outputs['machine.wasm'],m.files['machine.wasm']);
  assert.equal(build.outputs['machine.mjs'],m.files['machine.mjs']);
  if(receipt.runs.length){assert.deepEqual(m.workloads,receipt.runs[0].workloads);assert.deepEqual(m.rom,receipt.runs[0].rom);}
  const dir=path.join(out,label);fs.mkdirSync(dir);
  const fd=fs.openSync(path.join(dir,'medium.raw'),'wx+');fs.ftruncateSync(fd,268435456);fs.fsyncSync(fd);
  const calls={read:0,write:0,barrier:0},run={label,bundle_sha256:sha(fs.readFileSync(path.join(bundle,'bundle.json'))),
   implementation:build.snapshot_identity,wasm:build.outputs['machine.wasm'],workloads:m.workloads,rom:m.rom,cuts:[],simulation_seconds:0};
  const {default:createMachine}=await import(pathToFileURL(path.join(bundle,'machine.mjs')));
  let core=await createMachine();
  core.backing={getSize:()=>268435456,
   read(b,{at}){calls.read++;return fs.readSync(fd,b,0,b.length,at);},
   write(b,{at}){calls.write++;return fs.writeSync(fd,b,0,b.length,at);},
   flush(){calls.barrier++;fs.fsyncSync(fd);}};
  const check=(name,types=[],args=[])=>{if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));};
  const state=()=>core.ccall('lemma_inspect','string',[],[]);
  try{
   core.FS.mkdir('/forks');
   for(const [target,item]of [['/image.elf',m.workloads.initializer.image],['/machine.dtb',m.workloads.initializer.dtb],
    ['/descriptor.bin',m.workloads.initializer.descriptor],['/boot.bin',m.rom]])core.FS.writeFile(target,fs.readFileSync(path.join(bundle,item.path)));
   check('lemma_create');
   check('lemma_event',['string'],['17 pen 1 10000 20000 2048 3 1 0']);
   check('lemma_event',['string'],['23 pen 2 10000 20000 0 2 1 0']);
   let cycle=0n;
   for(const at of receipt.cuts){const goal=BigInt(at);assert(goal<=MAX_CYCLES);
    while(cycle<goal){bound();const n=Number(goal-cycle>50000n?50000n:goal-cycle),s=performance.now();check('lemma_run',['number'],[n]);run.simulation_seconds+=(performance.now()-s)/1000;cycle+=BigInt(n);}
    const before=state(),beforeCalls={...calls};assert.equal(JSON.parse(before).snapshot_identity,build.snapshot_identity);
    check('lemma_snapshot',['string'],['/cut.bin']);assert.equal(state(),before);assert.deepEqual(calls,beforeCalls);
    const name=path.join(dir,at+'.chk'),bytes=copyMemfs(core,'/cut.bin',name);
    run.cuts.push({cycle:at,state:before,bytes,checkpoint:name,calls:{...calls}});
    console.log(JSON.stringify({label,cycle:at,simulation_seconds:run.simulation_seconds}));
   }
   fs.writeFileSync(path.join(dir,'uart.bin'),core.FS.readFile('/uart.bin'));
   run.heap_bytes=core.HEAPU8.byteLength;run.calls=calls;receipt.runs.push(run);
  }finally{core?.ccall('lemma_destroy',null,[],[]);fs.closeSync(fd);core=null;global.gc?.();}
 }
 for(let i=0;i<receipt.cuts.length;i++){
  const a=receipt.runs[0].cuts[i],b=receipt.runs[1].cuts[i];assert.equal(a.bytes,b.bytes);
  const fa=fs.openSync(a.checkpoint,'r'),fb=fs.openSync(b.checkpoint,'r');
  try{const x=Buffer.alloc(1048576),y=Buffer.alloc(1048576);
   for(let at=0;at<a.bytes;at+=x.length){const n=Math.min(x.length,a.bytes-at);assert.equal(fs.readSync(fa,x,0,n,at),n);assert.equal(fs.readSync(fb,y,0,n,at),n);
    if(at===0){assert.equal(x.subarray(0,8).toString(),'LMSSRTL1');assert.equal(x.subarray(16,80).toString(),receipt.runs[0].implementation);
     assert.equal(y.subarray(16,80).toString(),receipt.runs[1].implementation);assert.deepEqual(x.subarray(0,16),y.subarray(0,16));assert.deepEqual(x.subarray(80,n),y.subarray(80,n));}
    else assert.deepEqual(x.subarray(0,n),y.subarray(0,n));}
  }finally{fs.closeSync(fa);fs.closeSync(fb);}
  assert.deepEqual(a.calls,b.calls);
 }
 assert.deepEqual(fs.readFileSync(path.join(out,'scalar/uart.bin')),fs.readFileSync(path.join(out,'optimized/uart.bin')));
 receipt.speedup=receipt.runs[0].simulation_seconds/receipt.runs[1].simulation_seconds;receipt.status='PASS';
}catch(e){receipt.error=String(e);process.exitCode=1;}
finally{receipt.host_seconds=(performance.now()-started)/1000;receipt.peak_rss_bytes=process.resourceUsage().maxRSS*1024;
 receipt.observer_sha256=sha(fs.readFileSync(new URL(import.meta.url)));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify(receipt));}
