// SPDX-License-Identifier: Apache-2.0
// Serialized asynchronous transport to actual QMP. No notebook policy.
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
}
