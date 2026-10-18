// Synthetic idle-component diagnostic. This is not the economy workload gate.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
const [build,guest,rom,binding,out]=process.argv.slice(2);
if(!out)throw Error('usage: benchmark_multimodal_wasm.mjs WASM_BUILD PROBE_ELF ROM BINDING UNUSED_OUTPUT');
fs.mkdirSync(out,{recursive:false});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex'),inputs={};
const read=(name,file)=>{file=file instanceof URL?fileURLToPath(file):file;const data=fs.readFileSync(file);inputs[name]={path:path.resolve(file),sha256:sha(data)};return data;};
const report={schema:'lemma-portable-idle-component-performance/1',result:'FAIL',
 scope:'Real shared Lean M-mode probe followed by idle CPU loop. No notebook, sustained acquisition, economy, inference or browser performance qualification.',
 host:{node:process.version,arch:process.arch,platform:process.platform,cpu:os.cpus()[0]?.model,logicalCPUs:os.cpus().length},
 limits:{steadyCycles:3000000,perBatchCycles:100000,wallSeconds:90},inputs};
const started=performance.now();let core;
try{
 for(const name of ['machine.mjs','machine.wasm','build.json'])read(name,path.join(build,name));
 read('observer',new URL(import.meta.url));
 const {default:create}=await import(pathToFileURL(path.resolve(build,'machine.mjs')).href);core=await create();
 core.backing={getSize:()=>268435456,read:bytes=>{bytes.fill(0);return bytes.length;},write:()=>{throw Error('storage write not admitted');},flush:()=>{}};
 for(const [name,file] of Object.entries({'image.elf':guest,'boot.bin':rom,'machine.dtb':path.join(binding,'platform.dtb'),'descriptor.bin':path.join(binding,'descriptor.bin')}))core.FS.writeFile('/'+name,read(name,file));
 core.FS.mkdir('/forks');const check=(name,types=[],args=[])=>{if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));};
 check('lemma_create');
 for(let i=0;i<8;i++)check('lemma_event',['string'],[`0 multimodal ${i} ${100+i} 10 0`]);
 const run=()=>{if(performance.now()-started>90000)throw Error('original wall deadline');check('lemma_run',['number'],[100000]);};
 for(let i=0;i<10;i++)run();
 if(!new TextDecoder().decode(core.FS.readFile('/uart.bin')).includes('LMMP'))throw Error('actual Lean probe did not finish');
 const before=JSON.parse(core.ccall('lemma_inspect','string',[],[]));
 const cpu=process.cpuUsage(),began=performance.now();
 for(let i=0;i<30;i++)run();
 const after=JSON.parse(core.ccall('lemma_inspect','string',[],[])),seconds=(performance.now()-began)/1000;
 if(after.cycle-before.cycle!==3000000||after.finished)throw Error('actual clock advancement/CPU continuation differs');
 report.result='MEASURED_IDLE_COMPONENT_ONLY';report.steady={cycles:3000000,virtualSeconds:0.03,wallSeconds:seconds,
  realTimeFactor:0.03/seconds,cpuMicroseconds:process.cpuUsage(cpu),memory:process.memoryUsage(),wasmHeapBytes:core.HEAPU8.byteLength,
  initialCycle:before.cycle,finalCycle:after.cycle,initialRetired:before.retired,finalRetired:after.retired};
 if(Object.values(inputs).some(item=>sha(fs.readFileSync(item.path))!==item.sha256))throw Error('consumed source changed');
}catch(error){report.result='FAIL';report.error=String(error);throw error;}
finally{if(core)core.ccall('lemma_destroy','void',[],[]);report.elapsedSeconds=(performance.now()-started)/1000;fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report.steady,null,2));
