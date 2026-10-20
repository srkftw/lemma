// SPDX-License-Identifier: Apache-2.0
// Raw source transport only. The controller owns clocks, permissions, gain,
// capture headers, DMA completion and every subsequent interpretation.
export function opticalBinding(manifest){
 return manifest?.profile==='lemma-silicon-dev/0.17.0'&&
  ['lemma-optical17-functional-mm2/1','lemma-optical17-canonical/1'].includes(manifest.execution_binding)&&
  manifest.optical_controller_abi===1&&manifest.optical_frame_contract==='lemma-optical-frame/1';
}
export function opticalWords(values){
 if(!Array.isArray(values)||values.length!==5)throw Error('Optical source requires endpoint, kind, data, bytes and quality');
 const words=values.map(value=>{
  if(typeof value!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(value))throw Error('Optical source words must be lossless unsigned decimal strings');
  const word=BigInt(value);if(word>18446744073709551615n)throw Error('Optical source word exceeds u64');return word;
 });
 if(words[0]<1n||words[0]>3n||words[1]>3n||words[3]>8n||words[4]>65535n)throw Error('Optical source field outside its wire range');
 // Deliberately retain malformed SOF/DATA/EOF combinations: they are actual
 // raw stimuli which the device, rather than this transport, must reject.
 return words.map(String);
}
export function syntheticOpticalFrame(endpoint,format){
 if(!['1','2','3'].includes(endpoint))throw Error('Optical endpoint must be1..3');
 let width,height,bytesPerPixel;
 if(format==='synthetic16-u16'&&endpoint==='1'){width=16;height=16;bytesPerPixel=2;}
 else if(format==='eye160-gray8'&&endpoint!=='3'){width=160;height=120;bytesPerPixel=1;}
 else if(format==='face320-gray8'&&endpoint==='3'){width=320;height=240;bytesPerPixel=1;}
 else throw Error('Raw source format is incompatible with this endpoint');
 const bytes=new Uint8Array(width*height*bytesPerPixel);
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  // Explicit spatially varying raw image codes, independent of documents or viewport.
  const code=bytesPerPixel===2?(x>=5&&x<=8&&y>=6&&y<=9?60000:256+x+y):(x*3+y*5)&255;
  const at=(y*width+x)*bytesPerPixel;bytes[at]=code&255;if(bytesPerPixel===2)bytes[at+1]=code>>8;
 }
 return bytes;
}
export function opticalFrameBeats(endpoint,bytes){
 if(!['1','2','3'].includes(endpoint)||!(bytes instanceof Uint8Array)||bytes.length<1||bytes.length>76800)throw Error('Optical raw frame requires endpoint1..3 and1..76800 bytes');
 const beats=[[endpoint,'0','0','0','0']];
 for(let at=0;at<bytes.length;at+=8){
  const count=Math.min(8,bytes.length-at);let word=0n;
  for(let n=0;n<count;n++)word|=BigInt(bytes[at+n])<<BigInt(n*8);
  beats.push([endpoint,'1',String(word),String(count),'0']);
 }
 beats.push([endpoint,'2','0','0','0']);return beats;
}
