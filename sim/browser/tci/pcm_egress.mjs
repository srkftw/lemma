// SPDX-License-Identifier: Apache-2.0
// Decode only actual modeled DAC output. No text, resynthesis or guest policy.
export class PcmEgress{
 constructor(){this.cursor=8;this.rows=0;this.dropped=0;this.lastPosition=null;this.lastTick=null;this.binding=null;this.active=false;}
 inspect(){return {contract:'lemma-tci-waveform-egress/1',filePosition:this.cursor,records:this.rows,dropped:this.dropped,binding:this.binding,limitBytes:67108864,scope:'digitally consumed DAC waveform; sink delivery and physical onset are separate'};}
 discard(size){if(!Number.isSafeInteger(size)||size<this.cursor||size>67108864||(size-8)%24)throw Error('Invalid waveform cancellation boundary');this.dropped+=(size-this.cursor)/24;this.cursor=size;this.binding=null;this.lastTick=null;this.lastPosition=null;this.active=false;}
 poll(fs,size,stream,emit){
  if(!Number.isSafeInteger(size)||size<8||size>67108864||(size-8)%24||size<this.cursor)throw Error('Waveform extent outside bounded append-only transport');
  if(!stream||!['state','epoch','consent','consumed'].every(k=>typeof stream[k]==='string'&&/^(0|[1-9][0-9]*)$/.test(stream[k])))throw Error('Malformed actual playback observation');
  const binding=stream.epoch+'/'+stream.consent,active=stream.state==='5'&&stream.consent!=='0';
  if(binding!==this.binding||(!active&&this.active)){emit({type:'pcm-stop',reason:binding!==this.binding?'Controller playback epoch/grant changed':'Controller playback stopped',binding,digitalConsumed:stream.consumed});this.binding=binding;this.lastTick=null;this.lastPosition=null;}
  this.active=active;
  // At most 16,384 records per observation. Backlog is reported, never relabeled
  // as successful presentation. The complete digital file remains retained.
  const end=Math.min(size,this.cursor+16384*24),file=fs.open('/audio.bin','r');
  try{
   const header=new Uint8Array(8);if(fs.read(file,header,0,8,0)!==8||new TextDecoder().decode(header)!=='LMPCM001')throw Error('Waveform header differs');
   while(this.cursor<end){
    const count=Math.min(256,(end-this.cursor)/24),bytes=new Uint8Array(count*24);
    if(fs.read(file,bytes,0,bytes.length,this.cursor)!==bytes.length)throw Error('Short waveform read');
    const view=new DataView(bytes.buffer),samples=[];
    for(let n=0;n<count;n++){
     const tick=view.getBigUint64(n*24,true),position=view.getBigUint64(n*24+8,true),word=view.getBigInt64(n*24+16,true);
     if(word< -32768n||word>32767n||!position||position>BigInt(stream.consumed))throw Error('Malformed actual DAC record');
     if(this.lastTick!==null&&(tick<=this.lastTick||position!==this.lastPosition+1n))throw Error('Unmarked DAC sequence discontinuity');
     this.lastTick=tick;this.lastPosition=position;this.rows++;
     if(active)samples.push([String(tick),String(position),Number(word)]);else this.dropped++;
    }
    this.cursor+=bytes.length;
    if(samples.length)emit({type:'pcm',pcm:{format:'mono-s16le-low16/1',clock_hz:100000000,samples,dropped:this.dropped,binding,digitalConsumed:stream.consumed}});
   }
  }finally{fs.close(file);}
  if(end<size)throw Error('PCM egress backlog exceeds declared observation bound; machine paused');
 }
}
