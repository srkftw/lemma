// SPDX-License-Identifier: Apache-2.0
// Host scheduling only. The machine still executes every admitted cycle.
export const UINT64_MAX=18446744073709551615n;
export function uint64(value,label='Cycle count'){
 if(typeof value!=='bigint'&&(typeof value!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(value)))
  throw Error(label+' must be an exact unsigned decimal string or BigInt');
 const n=BigInt(value);if(n<0n||n>UINT64_MAX)throw Error(label+' exceeds UInt64');return n;
}
// Ordinary Resume may limit host resource use without granting raw input or
// selecting a virtual execution prefix. The limit pauses actual execution.
export function hostSecondsLimit(value){
 if(value===null||value===undefined)return null;
 if(typeof value!=='string'||!/^[1-9][0-9]{0,3}$/.test(value)||BigInt(value)>7200n)
  throw Error('Host limit must be an integer decimal string from1 through7200 seconds');
 return Number(value);
}
export function resumeBudget(cycle,hostSeconds,now=performance.now(),maximum=UINT64_MAX){
 if(hostSeconds===null||hostSeconds===undefined)return null;
 const current=uint64(cycle),limit=uint64(maximum);
 if(current>=limit)throw Error('No virtual execution range remains');
 return new RunBudget(current,limit-current,false,hostSeconds,now);
}
export class RunBudget{
 constructor(cycle,cycles,stopOnReady=false,hostSeconds=null,now=performance.now(),panelBoundary=null){
  this.requested=uint64(cycles,'Run budget');if(this.requested===0n)throw Error('Run budget must be positive');
  if(typeof stopOnReady!=='boolean')throw Error('Ready stop must be a boolean');
  const seconds=hostSecondsLimit(hostSeconds);
  if(!Number.isFinite(now)||now<0)throw Error('Invalid monotonic host clock');
  this.hostSeconds=seconds;this.startedAt=now;
  this.panelBoundary=panelBoundary===null?null:uint64(panelBoundary,'Panel boundary');
  this.used=0n;this.stopOnReady=stopOnReady;this.rebase(cycle);
 }
 // This host scheduling limit suspends at a real machine boundary. It is
 // independent of virtual time and is never stored in the machine archive.
 hostExpired(now){if(!Number.isFinite(now)||now<this.startedAt)throw Error('Invalid monotonic host clock');
  return this.hostSeconds!==null&&now-this.startedAt>=this.hostSeconds*1000;}
 // A completed scan is an observation of the real controller. It never
 // completes a pending scan, submits guest work or acknowledges storage.
 panelCompleted(state){return this.panelBoundary!==null&&uint64(state.panel_completed)>this.panelBoundary&&
  state.paper_busy==='0'&&state.panel_power==='0';}
 get remaining(){return this.requested-this.used;}
 // The existing initializer launches another actual CPU at cycle zero.
 // Carry the unused budget across that launch instead of replenishing it.
 rebase(cycle){this.cycle=uint64(cycle);if(this.remaining>UINT64_MAX-this.cycle)throw Error('Run budget would overflow the virtual clock');this.limit=this.cycle+this.remaining;}
 quantum(cycle){if(uint64(cycle)!==this.cycle)throw Error('Run budget boundary changed');return this.remaining<50000n?this.remaining:50000n;}
 observe(cycle,quantum){const next=uint64(cycle),n=uint64(quantum);
  if(next<this.cycle||next-this.cycle>n||next-this.cycle>this.remaining)throw Error('Machine advanced outside the run budget');
  this.used+=next-this.cycle;this.cycle=next;
 }
 inspection(){return {requested:String(this.requested),used:String(this.used),remaining:String(this.remaining),limit:String(this.limit),stopOnReady:this.stopOnReady,hostSecondsLimit:this.hostSeconds,panelBoundary:this.panelBoundary===null?null:String(this.panelBoundary)};}
}
