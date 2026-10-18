// SPDX-License-Identifier: Apache-2.0
// Laboratory-only observer of the same real RV64 Lean controller component.
export async function runProbe(createMachine, artifacts, wallLimitMs=120000) {
 const core=await createMachine();
 core.backing={getSize:()=>268435456,read:(bytes)=>{bytes.fill(0);return bytes.length;},write:()=>{throw Error('probe storage writes are not admitted');},flush:()=>{}};
 for(const [name,bytes] of Object.entries(artifacts))core.FS.writeFile('/'+name,bytes);
 core.FS.mkdir('/forks');
 const check=(name,types=[],args=[])=>{if(core.ccall(name,'number',types,args))throw Error(core.ccall('lemma_error','string',[],[]));};
 check('lemma_create');
 const state=JSON.parse(core.ccall('lemma_inspect','string',[],[]));
 for(let i=0;i<8;i++)check('lemma_event',['string'],[`${state.cycle} multimodal ${i} ${100+i} 10 0`]);
 const began=performance.now();let cycles=0,uart;
 do {if(performance.now()-began>wallLimitMs)throw Error('probe wall deadline');check('lemma_run',['number'],[100000]);cycles+=100000;uart=core.FS.readFile('/uart.bin');await new Promise(resolve=>setTimeout(resolve,0));}
 while(!new TextDecoder().decode(uart).includes('LMMP')&&cycles<5000000);
 check('lemma_multimodal_diagnostic_records');const records=core.FS.readFile('/multimodal-probe.bin'),view=new DataView(records.buffer,records.byteOffset,records.byteLength);
 const words=Array.from({length:80},(_,i)=>view.getBigUint64(i*8,true));
 if(words[0]!==0x4c4d4d50n||words[6]!==0n)throw Error(`actual guest marker/status ${words[0]}/${words[6]}`);
 if(words[1]!==511n||words[3]!==8n||words[4]!==1n||words[5]!==0n)throw Error('actual guest feature/count/consumption/cancel receipt');
 const expected=[90n,546n,552n,564n,16777528n,79n,192n,194n],rows=[];
 for(let i=0;i<8;i++){const row=words.slice(16+i*8,24+i*8);rows.push(row.map(String));
  if(row[0]!==expected[i]||row[2]-row[1]!==3n||row.slice(4).map(String).join(',')!=='1,2,1,1')throw Error(`independent primitive oracle stream${i}: ${row}`);}
 const pcm=JSON.parse(core.ccall('lemma_pcm','string',[],[]));
 if(pcm.format!=='mono-s16le-low16/1'||pcm.samples.length!==1||pcm.samples[0][1]!=='1'||pcm.samples[0][2]!==32767||pcm.dropped!=='0')throw Error('actual DAC waveform/cancellation oracle');
 const inspection=JSON.parse(core.ccall('lemma_inspect','string',[],[]));core.ccall('lemma_destroy','void',[],[]);
 return {result:'PASS',scope:'actual shared Lean M-mode component in portable RTL/Wasm; no whole notebook,consumer realtime,headband/full sensor,physical or educational qualification',cycles,elapsedSeconds:(performance.now()-began)/1000,header:words.slice(0,8).map(String),rows,pcm,inspection,records,uart};
}
