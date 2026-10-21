// Actual transport helper, controlled QMP replies: no CPU execution claim.
import assert from 'node:assert/strict';
import {Control,CPU_STOP_CONTRACT,cpuStopObservation} from '../../sim/browser/tci/control.mjs';

const clock=stopped=>({stop_boundary_contract:CPU_STOP_CONTRACT,cpu_count:1,
 cpus_stopped:stopped?1:0,all_cpus_stopped:stopped});
const c=new Control(null),calls=[];
let ack=false;
c.request=async name=>{calls.push(name);
 if(name==='query-status')return {running:false};
 assert.equal(name,'lemma-clock');const result=clock(ack);ack=true;return result;};
await c.stopped(CPU_STOP_CONTRACT);
assert.deepEqual(calls,['query-status','lemma-clock','query-status','lemma-clock']);
assert.equal(cpuStopObservation(clock(true)).allStopped,true);
// PAUSED and guest WFI/idle never stand in for CPUState.stopped.
assert.equal(cpuStopObservation({...clock(false),running:false,halted:true}).allStopped,false);
for(const bad of [{},clock(false),clock(true)]){
 if(bad.stop_boundary_contract){bad.cpus_stopped=2;}
 assert.throws(()=>cpuStopObservation(bad),/Missing or inconsistent/);
}
assert.throws(()=>cpuStopObservation({...clock(false),all_cpus_stopped:true}),/inconsistent/);
assert.throws(()=>cpuStopObservation({...clock(true),cpu_count:0}),/inconsistent/);
await assert.rejects(c.stopped('unknown'),/Unknown/);
await assert.rejects(c.stopped(CPU_STOP_CONTRACT,performance.now()-1),/Original/);
// Neither a stop request nor a stopped CPU can replace PAUSED runstate.
calls.length=0;let queries=0;
c.request=async name=>{calls.push(name);if(name==='query-status')return {running:++queries<3};
 if(name==='stop')return {};assert.equal(name,'lemma-clock');return clock(true);};
await c.stopped(CPU_STOP_CONTRACT);
assert.equal(queries,3);assert.equal(calls.filter(x=>x==='stop').length,1);
// A late acknowledgement cannot turn the original deadline into a success.
let deadline=performance.now()+10;
c.request=async name=>{if(name==='query-status')return {running:false};
 await new Promise(r=>setTimeout(r,15));return clock(true);};
await assert.rejects(c.stopped(CPU_STOP_CONTRACT,deadline),/Original/);
// Legacy immutable bindings retain their original query-status-only scope.
calls.length=0;c.request=async name=>{calls.push(name);return {running:false};};
await c.stopped();assert.deepEqual(calls,['query-status']);
console.log('PASS actual CPU stop transport helper: delayed/invalid/late acknowledgements; explicit legacy scope');
