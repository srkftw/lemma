"""Browser receipt byte transport and fault behavior; no guest or visibility claim."""
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]


class SchoolDelivery(unittest.TestCase):
    def test_browser_original_peer_raw_records_backpressure_and_lost_ack(self):
        script=r'''
import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';
globalThis.crypto??=webcrypto;
const source=await fs.readFile('sim/browser/school_transport.js','utf8');
const {SchoolTransport}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
let calls=[],lost=true,reject=false;
globalThis.fetch=async(endpoint,options)=>{
 const body=options.body,request=JSON.parse(body);calls.push({endpoint,body,request,token:options.headers.Authorization});
 if(lost&&request.kind==='transport'){lost=false;throw Error('simulated lost response after server commit');}
 const reply=reject?{ok:false,error:'admission revoked'}:{ok:true,result:{observation:'a'.repeat(64),commitSequence:11,reused:calls.length>1}};
 return new Response(JSON.stringify(reply),{status:200,headers:{'Content-Type':'application/json'}});
};
const school=new SchoolTransport();
const credential=endpoint=>({schema:'lemma-school-credential/1',endpoint,token:(endpoint.includes('8891')?'1':'2').repeat(64)});
school.connect(credential('http://127.0.0.1:8891/v1/client'));
const ask={sequence:1n,revision:3n,object:9007199254740999n};
school.beginDelivery({decision:'immutable-decision-a'},ask,0);
const packet=Uint8Array.from([0,1,2,3,4]);await school.transportDelivery(packet,2);
const row=(tag,a,b,c,d,cr=false)=>'K1 '+[tag,a,b,c,d].map(x=>BigInt(x).toString(16).padStart(16,'0')).join(' ')+(cr?'\r':'')+'\n';
let uart=row(0x724,0,3,ask.object,0)+row(0x725,2,1,0,0);
const bytes=()=>new TextEncoder().encode(uart);
await school.observeDelivery(bytes(),0,{cycle:100,completed:2,busy:0});
assert.equal(calls.filter(x=>x.request.kind==='controller-snapshot').length,0);
const raw=row(0x725,1,1,0,0,true);uart+=raw.slice(0,-1);await school.observeDelivery(bytes(),0,null);
uart+='\n';await school.observeDelivery(bytes(),0,{cycle:101,completed:2,accepted:3,busy:1});
await school.observeDelivery(bytes(),0,{cycle:102,completed:2,accepted:3,busy:1,targetSHA256:'b'.repeat(64),hashEncoding:'gray4'});
await school.observeDelivery(bytes(),0,{cycle:103,completed:3,accepted:3,busy:0,targetSHA256:'b'.repeat(64),visibleSHA256:'c'.repeat(64),hashEncoding:'gray4'});
await school.observeDelivery(bytes(),0,{cycle:104,completed:4,accepted:4,busy:0});
// The old peer owns already queued receipts even after selecting a new school.
school.disconnect();school.connect(credential('http://127.0.0.1:8892/v1/client'));
const settle=async()=>{const deadline=Date.now()+4000;while(school.deliveryStatus().pending&&Date.now()<deadline)await new Promise(r=>setTimeout(r,10));assert.equal(school.deliveryStatus().pending,0);};
await settle();
assert.ok(calls.length>=6);assert.ok(calls.every(x=>x.endpoint.includes('8891')));
const transport=calls.filter(x=>x.request.kind==='transport');assert.equal(transport.length,2);assert.equal(transport[0].body,transport[1].body);
const raster=calls.filter(x=>x.request.kind==='guest-raster');assert.equal(raster.length,1);
const digest=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))).toString('hex');assert.equal(raster[0].request.observation.uartSHA256,digest);
assert.equal(calls.filter(x=>x.request.kind==='guest-rejected').length,0);
const panels=calls.filter(x=>x.request.kind==='controller-snapshot');assert.equal(panels.length,2);assert.deepEqual(panels.map(x=>x.request.observation.busy),[1,0]);
assert.equal(calls.filter(x=>x.request.kind==='cancelled').length,1);
assert.ok(!JSON.stringify(school.deliveryStatus()).includes('Bearer'));assert.ok(!JSON.stringify(school.deliveryStatus()).includes(credential('8891').token));
// A genuine rejection is retained for explicit retry using its original peer.
reject=true;school.beginDelivery({decision:'immutable-decision-b'},ask,0);school.cancelDelivery('user-cancel');await settle();assert.equal(school.deliveryStatus().failed,1);
school.connect(credential('http://127.0.0.1:8891/v1/client'));reject=false;await school.operation({operation:'receipts'});await settle();assert.equal(school.deliveryStatus().failed,0);assert.ok(calls.at(-1).endpoint.includes('8892'));
// A reconnect does not make a lower UART length an old raster acceptance.
school.beginDelivery({decision:'immutable-decision-c'},ask,50);await school.observeDelivery(new Uint8Array(10),0,null);await settle();assert.equal(calls.at(-1).request.observation.reason,'machine-restart');
console.log(JSON.stringify({result:'PASS',lostAcknowledgementRetrySameBytes:true,originalPeerRetained:true,raw725HashExactCRLF:true,controllerSnapshots:2,manualRetry:true}));
'''
        result=subprocess.run(['node','--input-type=module','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
