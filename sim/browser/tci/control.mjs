// SPDX-License-Identifier: Apache-2.0
// Serialized asynchronous transport to actual QMP. No notebook policy.
export const CPU_STOP_CONTRACT='lemma-qemu-cpu-stop/1';
export function cpuStopObservation(clock){
 if(clock.stop_boundary_contract!==CPU_STOP_CONTRACT||clock.cpu_count!==1||
    !Number.isInteger(clock.cpus_stopped)||clock.cpus_stopped<0||clock.cpus_stopped>clock.cpu_count||
    typeof clock.all_cpus_stopped!=='boolean'||clock.all_cpus_stopped!==(clock.cpus_stopped===clock.cpu_count))
  throw Error('Missing or inconsistent actual CPU stop acknowledgement');
 return {contract:CPU_STOP_CONTRACT,count:clock.cpu_count,stopped:clock.cpus_stopped,allStopped:clock.all_cpus_stopped};
}
export class Control{
 constructor(module,timeoutMs=60000){this.module=module;this.id=0;this.tail=Promise.resolve();this.timeoutMs=timeoutMs;this.metrics={requests:0,seconds:0,commands:{}};}
 call(name,type='number',types=[],args=[]){return this.module.ccall(name,type,types,args);}
 async ready(){const end=performance.now()+this.timeoutMs;while(!this.call('lemma_browser_ready')){if(performance.now()>end)throw Error('QEMU machine-init deadline');await new Promise(r=>setTimeout(r,5));}if(this.call('lemma_browser_abi','string')!=='lemma-qemu-wasm-control/1')throw Error('Unsupported QEMU control ABI');}
 request(execute,args){const pending=this.tail.then(()=>this.exchange(execute,args));this.tail=pending.catch(()=>{});return pending;}
 async exchange(execute,args){
  if(this.id>=4294967295)throw Error('Browser command counter exhausted');
  const began=performance.now();const body={execute,id:++this.id};if(args!==undefined)body.arguments=args;const json=JSON.stringify(body);
  if(new TextEncoder().encode(json).length>4096)throw Error('Browser control packet exceeds4096 bytes');
  const status=this.call('lemma_browser_submit','number',['string'],[json]);if(status!==0)throw Error('Browser request not queued:'+status);
  const end=performance.now()+this.timeoutMs;let text;
  while(!(text=this.call('lemma_browser_poll','string'))){if(performance.now()>end)throw Error('Original QMP request deadline');await new Promise(r=>setTimeout(r,5));}
  let response;try{response=JSON.parse(text);}finally{if(this.call('lemma_browser_ack')!==0)throw Error('Browser response acknowledgement failed');}
  const elapsed=(performance.now()-began)/1000;this.metrics.requests++;this.metrics.seconds+=elapsed;const stat=this.metrics.commands[execute]??={count:0,seconds:0,maxSeconds:0};stat.count++;stat.seconds+=elapsed;stat.maxSeconds=Math.max(stat.maxSeconds,elapsed);
  if(response.id!==body.id)throw Error('QMP response identifier differs');
  if(response.error)throw Error(response.error.desc??JSON.stringify(response.error));return response.return;
 }
 get(property,path='/machine/lemma-hardware'){return this.request('qom-get',{path,property});}
 set(property,value,path='/machine/lemma-hardware'){return this.request('qom-set',{path,property,value});}
 async stopped(contract=null,deadline=performance.now()+this.timeoutMs){
  if(contract!==null&&contract!==CPU_STOP_CONTRACT)throw Error('Unknown CPU stop acknowledgement contract');
  const check=()=>{if(contract!==null&&performance.now()>=deadline)throw Error('Original CPU stop acknowledgement deadline');};
  check();
  let status=await this.request('query-status');
  if(status.running){await this.request('stop');status=null;}
  if(contract===null)return;
  for(;;){
   // QMP PAUSED can precede pause_all_vcpus. Only the actual stopped field
   // acknowledges a CPU thread; guest WFI/idle and runstate are insufficient.
   check();if(status===null)status=await this.request('query-status');
   const clock=await this.request('lemma-clock');check();
   if(!status.running&&cpuStopObservation(clock).allStopped)return;
   status=null;
   await new Promise(r=>setTimeout(r,5));
  }
 }
}
