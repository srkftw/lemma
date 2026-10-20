// SPDX-License-Identifier: Apache-2.0
// Local support observations contain no admission credential or executable state.
export function supportReport({manifest,state,uart,guestStart,mode,readyAt,timing,capture}){
 const limit=131072, start=Math.max(0,uart.length-limit), source={};
 for(const key of ['schema','profile','execution_backend','execution_binding','multimodal_controller_abi','controller_contract','guest_archive_sha256','runtime_admission_sha256','wasm_build_sha256'])if(manifest[key]!==undefined)source[key]=manifest[key];
 return {schema:'lemma-client-support-report/1',scope:'Read-only controller and guest-console observations. Not a checkpoint, durable-work assessment or mathematical verification.',source,mode,readyAt,state,timing,
  console:{totalBytes:uart.length,launchStart:guestStart,tailStart:start,tailHex:Array.from(uart.subarray(start),v=>v.toString(16).padStart(2,'0')).join('')},
  input:{total:capture.length,tailStart:Math.max(0,capture.length-128),tail:capture.slice(-128).map(row=>typeof row==='string'?row:{ingress:row.ingress,pressureOrigin:row.pressureOrigin,hostArrivalMs:row.hostArrivalMs,captureClock:row.captureClock,input:row.input?Object.fromEntries(['action','x','y','pressure','flags','tool','level'].filter(k=>row.input[k]!==undefined).map(k=>[k,row.input[k]])):undefined})},
  limits:{consoleTailBytes:limit,inputTailEvents:128},privacy:'Keep this local report private: console and pen observations can contain your mathematical work. School pairing credentials are excluded.'};
}
