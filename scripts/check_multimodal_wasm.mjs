// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL,fileURLToPath} from 'node:url';import crypto from 'node:crypto';
import {runProbe} from '../sim/browser/multimodal_probe.mjs';
const [build,guest,rom,binding,output]=process.argv.slice(2);if(!output)throw Error('usage: check_multimodal_wasm.mjs WASM_BUILD GUEST_ELF ROM_BIN BINDING_DIR UNUSED_OUTPUT');
fs.mkdirSync(output,{recursive:false});
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const inputs={};const read=(name,file)=>{file=file instanceof URL?fileURLToPath(file):file;const bytes=fs.readFileSync(file);inputs[name]={path:path.resolve(file),sha256:digest(bytes)};return bytes;};
const artifacts={'image.elf':read('guest',guest),'boot.bin':read('rom',rom),'machine.dtb':read('dtb',path.join(binding,'platform.dtb')),'descriptor.bin':read('descriptor',path.join(binding,'descriptor.bin'))};
read('wasm',path.join(build,'machine.wasm'));read('factory',path.join(build,'machine.mjs'));read('production',path.join(build,'build.json'));read('observer',new URL('../sim/browser/multimodal_probe.mjs',import.meta.url));
let report={schema:'lemma-multimodal-wasm-probe/v1',result:'FAIL',inputs,node:process.version,limits:{wall_seconds:120,rtl_cycles:5000000}};
try{const {default:createMachine}=await import(pathToFileURL(path.resolve(build,'machine.mjs')).href);const result=await runProbe(createMachine,artifacts);
 fs.writeFileSync(path.join(output,'records.bin'),result.records);fs.writeFileSync(path.join(output,'uart.bin'),result.uart);delete result.records;delete result.uart;report={...report,...result};}
catch(e){report.error=String(e);throw e;}
finally{report.outputs=Object.fromEntries(fs.readdirSync(output).map(name=>[name,digest(fs.readFileSync(path.join(output,name)))]));fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report,null,2));
