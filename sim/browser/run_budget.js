// SPDX-License-Identifier: Apache-2.0
// Host scheduling only. The machine still executes every admitted cycle.
export const UINT64_MAX=18446744073709551615n;
export function uint64(value,label='Cycle count'){
 if(typeof value!=='bigint'&&(typeof value!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(value)))
  throw Error(label+' must be an exact unsigned decimal string or BigInt');
 const n=BigInt(value);if(n<0n||n>UINT64_MAX)throw Error(label+' exceeds UInt64');return n;
}
export class RunBudget{
 constructor(cycle,cycles,stopOnReady=false){
  this.requested=uint64(cycles,'Run budget');if(this.requested===0n)throw Error('Run budget must be positive');
  if(typeof stopOnReady!=='boolean')throw Error('Ready stop must be a boolean');
  this.used=0n;this.stopOnReady=stopOnReady;this.rebase(cycle);
 }
 get remaining(){return this.requested-this.used;}
 // The existing initializer launches another actual CPU at cycle zero.
 // Carry the unused budget across that launch instead of replenishing it.
 rebase(cycle){this.cycle=uint64(cycle);if(this.remaining>UINT64_MAX-this.cycle)throw Error('Run budget would overflow the virtual clock');this.limit=this.cycle+this.remaining;}
 quantum(cycle){if(uint64(cycle)!==this.cycle)throw Error('Run budget boundary changed');return this.remaining<50000n?this.remaining:50000n;}
 observe(cycle,quantum){const next=uint64(cycle),n=uint64(quantum);
  if(next<this.cycle||next-this.cycle>n||next-this.cycle>this.remaining)throw Error('Machine advanced outside the run budget');
  this.used+=next-this.cycle;this.cycle=next;
 }
 inspection(){return {requested:String(this.requested),used:String(this.used),remaining:String(this.remaining),limit:String(this.limit),stopOnReady:this.stopOnReady};}
}
