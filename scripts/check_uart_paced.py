#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise actual native QEMU paced external-UART admission at a paused boundary.

This checks the real QOM queue, transactionality and timer ordering. It does not
assert guest packet installation, browser responsiveness or physical UART rates.
"""
from pathlib import Path
import argparse,json,os,signal,subprocess,time,hashlib
from lemmasim_fast import QMP

def main(a):
    out=a.output_dir.resolve();out.mkdir(exist_ok=False);start=time.monotonic();q=None;p=None
    report={'schema':'lemma-raw-uart-paced-boundaries/1','result':'FAIL','scope':__doc__,'limits':{'whole_seconds':120},'cases':[]}
    report['inputs']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),a.qemu,a.guest,a.dtb)}
    try:
        disk=out/'medium.raw'
        with disk.open('xb') as f:f.truncate(268435456)
        argv=[str(a.qemu.resolve()),'-machine','lemma-silicon-fast','-cpu','rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0','-m','128M','-smp','1','-bios','none','-kernel',str(a.guest.resolve()),'-dtb',str(a.dtb.resolve()),'-display','none','-monitor','none','-serial','file:'+str(out/'uart.bin'),'-S','-no-shutdown','-icount','shift=3,align=off,sleep=off','-global','lemma-fast-block.medium='+str(disk),'-qmp','unix:'+str(out/'qmp.sock')+',server=on,wait=off']
        report['argv']=argv
        with (out/'machine.log').open('wb') as log:p=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        q=QMP(out/'qmp.sock',p,5)
        def get(name):return q.execute('qom-get',{'path':'/machine/lemma-hardware','property':name})
        def put(name,value):return q.execute('qom-set',{'path':'/machine/lemma-hardware','property':name,'value':value})
        def state():return json.loads(get('raw-uart-state'))
        def reject(label,value):
            before=state()
            try:put('external-uart-paced',value)
            except RuntimeError:pass
            else:raise AssertionError('Invalid UART admission accepted:'+label)
            assert state()==before,label+' partially changed queue';report['cases'].append(label)
        assert get('raw-uart-version')=='lemma-raw-uart/1'
        assert get('raw-uart-paced-version')=='lemma-raw-uart-paced/1'
        reject('disabled','1000 100 00')
        put('enable-raw-uart','lemma-raw-uart/1')
        for label,value in [('empty','1000 100 '),('oddhex','1000 100 a'),('nonhex','1000 100 xx'),('zerointerval','1000 0 00'),('negativeinterval','1000 -1 00'),('extraword','1000 100 00 01'),('overflowwhen','9223372036854775798 1 00'),('overflowlast','9223372036854775797 1 0000')]:reject(label,value)
        put('external-uart-paced','1000 1000 a1b2c3');put('external-uart','2000 dd');put('external-uart-paced','1500 1000 eef1')
        assert state()['pending']==6 and state()['first_due_ns']==1000;report['cases'].append('legacy-and-paced-stable-merge')
        # Stop through the real virtual timer after the first byte. No UART
        # register, guest memory or host parser is used to manufacture receipt.
        put('run-until','1003');q.execute('cont')
        until=time.monotonic()+10
        while q.execute('query-status')['running']:
            if time.monotonic()>until:raise TimeoutError('First real arrival boundary')
            time.sleep(.005)
        observed=state();assert observed['delivered']==1 and observed['pending']==5 and observed['first_due_ns']==1500;report['first_arrival']=observed;report['cases'].append('first-real16550-delivery')
        reject('stalearrival','0 100 00')
        q.execute('system_reset');assert state()['pending']==0
        # A complete queue uses the same bounded state representation. Rejection
        # at capacity must leave all counters, head and timer untouched.
        now=int(get('virtual-time'));base=now+100000
        put('external-uart-paced',str(base)+' 100 '+('ab'*65536));assert state()['pending']==65536
        reject('fullqueue',str(base)+' 100 00');report['cases'].append('full65536-byte-admission')
        report['result']='PASS'
    finally:
        if q:q.close()
        if p and p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
        report['elapsed_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'result.json')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--qemu',type=Path,required=True);p.add_argument('--guest',type=Path,required=True);p.add_argument('--dtb',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);main(p.parse_args())
