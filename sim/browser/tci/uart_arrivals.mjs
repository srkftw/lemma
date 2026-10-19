// SPDX-License-Identifier: Apache-2.0
// External serial stimulus only. Byte arrival is distinct from guest receipt.
export const UART_ARRIVALS={contract:'lemma-browser-uart-arrivals/1',intervalNs:'100000',bytesPerSecond:10000};
export async function admitUart(control,frame,base,paced,onAccepted=()=>{}){
 if(!(frame instanceof Uint8Array)||!frame.length||frame.length>65536||typeof base!=='bigint'||base<0n||base+BigInt(frame.length-1)*100000n>9223372036854775797n||typeof paced!=='boolean')throw Error('UART arrival bounds');
 let accepted=0;
 // The additive capability batches individually timed bytes. Legacy v1 uses
 // the same exact arrival schedule through separate one-byte requests.
 const window=paced?1024:1;
 for(let offset=0;offset<frame.length;offset+=window){
  const bytes=frame.subarray(offset,offset+window),when=String(base+BigInt(offset)*100000n),hex=Array.from(bytes,v=>v.toString(16).padStart(2,'0')).join('');
  await control.set(paced?'external-uart-paced':'external-uart',when+(paced?' 100000 ':' ')+hex);accepted+=bytes.length;onAccepted(accepted);
 }
 return {...UART_ARRIVALS,accepted,requests:Math.ceil(frame.length/window),admission:paced?'lemma-raw-uart-paced/1':'lemma-raw-uart/1/one-byte-requests'};
}
