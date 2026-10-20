#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute Integrated15's admitted guest through Product10-compatible ROM/NV.

Uses acknowledged input media, real raw pen, explicit Save and a new cold CPU.
The optional finite checkpoint case is sealed synthetic same-backend execution;
it does not qualify live reauthorization, full multimodal services or fast parity.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import lemmasim_auth as auth
import lemmasim_session as sessions
from product_native import sha
from check_development_auth_notebook import expected_home
from check_live_notebook import guest_events,visible_pixels
sys.path.insert(0,str(ROOT/'conformance/lemmasim'))
from store_oracle import recover
from notebook_input import Input
from check_canonical_pen_pixels import expected_stroke


def require(value,message):
    if not value:raise RuntimeError(message)


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('prepared','boot-medium','user-medium','work-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--checkpoint-only',action='store_true')
    a=p.parse_args();out=a.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused ignored output required')
    out.mkdir(parents=True);start=time.monotonic();end=start+(300 if a.checkpoint_only else 18000)
    report={'schema':'lemma-integrated15-product-execution/1','result':'FAIL','scope':__doc__,
            'bounds':{'whole_seconds':300 if a.checkpoint_only else 18000,'cold_each_cycles':1300000000,'cold_each_seconds':7200,'save_cycles':300000000,'save_seconds':1800,'checkpoint_suffix_cycles':200000},
            'phases':[],'inputs':{str(path.resolve()):sha(path) for path in (a.prepared/'prepared.json',a.boot_medium,a.user_medium)},
            'commands':[],'observer':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__))},'compilation':'reused source-bound runtime, opaque boot image and public-development-key ROM; fresh Integrated15 RTL execution'}
    live=[]
    def publish():(out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
    def call(directory,value,timeout=120):
        require(time.monotonic()<end,'original whole deadline')
        return sessions.request(directory,value,timeout)
    def launch(name,boot,disk,restore=None):
        directory=out/name
        argv=[sys.executable,str(ROOT/'scripts/lemmasim_auth.py'),'--public-development-key','launch','--prepared',str(a.prepared.resolve()),'--session-dir',str(directory),'--paused','--headless','--mode','laboratory','--host-threads','1','--timeout','120']
        if restore is None:argv+=['--boot-medium',str(boot),'--disk',str(disk)]
        else:argv+=['--restore',str(restore)]
        log=(out/(name+'.log')).open('xb');process=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        live.append((process,directory,log));report['commands'].append(argv);deadline=time.monotonic()+30
        while not(directory/'session.json').is_file():
            require(process.poll() is None and time.monotonic()<deadline,'session did not open');time.sleep(.05)
        return directory
    def close(directory):
        row=next(x for x in live if x[1]==directory);process,_,log=row
        if process.poll() is None:call(directory,{'action':'destroy'})
        process.wait(timeout=10);require(process.returncode==0,'owned session failed');log.close();live.remove(row)
    def phase(directory,name,cap,seconds,predicate):
        begin=call(directory,{'action':'inspect'})['machine']['cycle'];t=time.monotonic()
        while True:
            state=call(directory,{'action':'inspect'})['machine'];rows=guest_events(directory/'uart.bin')
            require(not state['finished'] and not any(r[0] in (0xd4,0xf4,0x424) for r in rows),'guest failure in '+name)
            if predicate(state,rows):break
            used=state['cycle']-begin
            require(used<cap and time.monotonic()-t<seconds,'original phase bound: '+name)
            call(directory,{'action':'run','cycles':min(1000000,cap-used)})
        report['phases'].append({'name':name,'start_cycle':begin,'end_cycle':state['cycle'],'cycles':state['cycle']-begin,'seconds':time.monotonic()-t});publish();print(name,state['cycle'],flush=True);return state
    def full(directory,state,expected):
        if any(state[k] for k in ('event_queue','pen_queue','uart_queue','paper_busy','panel_pending_pixels','block_state','dma_outstanding')) or not state['panel_completed']:return False
        panel=out/(directory.name+'-observed.ppm');call(directory,{'action':'panel','path':str(panel)})
        return visible_pixels(panel)==(1650,2200,expected)
    try:
        data,_,_=auth.prepared(a.prepared);require(data['profile']=='lemma-silicon-dev/0.15.0','Integrated15 actual product required');report['identity']={'profile':data['profile'],'native':data['binary_sha256'],'implementation':data['runtime_identity'],'rom':data['rom_sha256'],'compatibility_view':data['digital_discovery'].get('compatibility_view')}
        boot=out/'boot.raw';disk=out/'user.raw'
        subprocess.run(['cp','--reflink=auto','--sparse=always',str(a.boot_medium),str(boot)],check=True)
        subprocess.run(['cp','--reflink=auto','--sparse=always',str(a.user_medium),str(disk)],check=True)
        _,seq,before=recover(disk.read_bytes());expected=expected_home(before);report['initial_store_sequence']=seq
        original=launch('original',boot,disk)
        if a.checkpoint_only:
            call(original,{'action':'inject','kind':'multimodal','cycle':100,'words':[0,123,10,7]})
            call(original,{'action':'inject','kind':'multimodal','cycle':110000,'words':[7,456,3,1]})
            cut=out/'cut.chk';call(original,{'action':'snapshot','path':str(cut)})
            call(original,{'action':'run','cycles':200000});first=out/'original-final.chk';call(original,{'action':'snapshot','path':str(first)})
            fork=launch('fork',None,None,cut);call(fork,{'action':'run','cycles':200000});second=out/'fork-final.chk';call(fork,{'action':'snapshot','path':str(second)})
            require(sha(first/'machine.chk')==sha(second/'machine.chk'),'same-backend all-state suffix differs')
            corrupted=out/'corrupt.chk';shutil.copytree(cut,corrupted);raw=bytearray((corrupted/'machine.chk').read_bytes());raw[-1]^=1;(corrupted/'machine.chk').write_bytes(raw)
            metadata=json.loads((corrupted/'snapshot.json').read_text());metadata['files'][0]['sha256']=sha(corrupted/'machine.chk');(corrupted/'snapshot.json').write_text(json.dumps(metadata,indent=2)+'\n')
            baseline=call(fork,{'action':'inspect'})['machine']
            rejected=False
            try:call(fork,{'action':'restore','path':str(corrupted)})
            except (ValueError,RuntimeError):rejected=True
            require(rejected and call(fork,{'action':'inspect'})['machine']==baseline,'restore rejection mutated running session')
            after=out/'after-rejection.chk';call(fork,{'action':'snapshot','path':str(after)});require(sha(after/'machine.chk')==sha(second/'machine.chk'),'rejected restore changed full checkpoint')
            observed=call(original,{'action':'inspect'})['machine']
            report['architectural_observation']={key:observed[key] for key in ('cycle','ticks','pc','privilege','retired','finished','boot_backing','power','usb_clocks')}
            report['checkpoint']={'cut_sha256':sha(cut/'machine.chk'),'suffix_sha256':sha(first/'machine.chk'),'all_serialized_bytes':(first/'machine.chk').stat().st_size,'suffix_cycles':200000,'pending_synthetic_stimuli':2,'corrupt_restore_transactional':True,'scope':'initial actual ROM/NV with two changed external converter inputs; not active multimodal-controller qualification'}
            close(fork);close(original);report['result']='PASS_INTEGRATED15_SEALED_SYNTHETIC_CHECKPOINT'
        else:
            ready=phase(original,'authenticated-cold-Ready',1300000000,7200,lambda state,rows:any(r[0]==0x420 for r in rows) and full(original,state,expected))
            stream=Input(1650,2200,ready['ticks']+10000,100000,0);stream.sample(825,160,0,False);stream.stroke('integrated15-physical-sram-ink',1,1,3,1700);stroke=stream.events[1:].copy();stream.tool(7,'explicit Save')
            for event in stream.events:call(original,{'action':'inject','kind':'pen','cycle':event[1]*10,'words':list(event[1:8])})
            desired=bytearray(expected)
            for x,y in expected_stroke(stroke)[1]:desired[(y*1650+x)*3:(y*1650+x)*3+3]=bytes(3)
            phase(original,'SRAM-pen-explicit-Save',300000000,1800,lambda state,rows:any(r[0]==0x421 and r[1]>=seq+3 for r in rows) and full(original,state,bytes(desired)))
            ack=out/'acknowledged-user.raw';nv=out/'acknowledged-boot.raw';call(original,{'action':'export-medium','path':str(ack)});call(original,{'action':'export-boot-medium','path':str(nv)})
            _,afterseq,after=recover(ack.read_bytes());require(afterseq>=seq+3 and expected_home(after)==bytes(desired),'saved raw/page/root or pixels differ');require(all(after[k].payload==v.payload for k,v in before.items() if k not in ((1,1),(1,257))),'older immutable objects changed');report['pen']={'events':stream.events,'durable_sequence':afterseq,'acknowledged_sha256':sha(ack)};close(original)
            coldboot=out/'cold-boot.raw';colddisk=out/'cold-user.raw'
            for source,dest in ((nv,coldboot),(ack,colddisk)):subprocess.run(['cp','--reflink=auto','--sparse=always',str(source),str(dest)],check=True)
            cold=launch('cold',coldboot,colddisk);phase(cold,'independent-new-CPU-all-pixels',1300000000,7200,lambda state,rows:any(r[0]==0x420 for r in rows) and full(cold,state,bytes(desired)))
            recovered=out/'recovered-user.raw';call(cold,{'action':'export-medium','path':str(recovered)});require(sha(recovered)==sha(ack),'cold changed acknowledged bytes');close(cold)
            report['result']='PASS_INTEGRATED15_AUTHENTICATED_NOTEBOOK_SRAM_PEN_SAVE_COLD'
        require(all(sha(path)==digest for path,digest in report['inputs'].items()),'original input changed')
    except BaseException as error:report['error']=repr(error)
    finally:
        for process,directory,log in live:
            try:
                if process.poll() is None:sessions.request(directory,{'action':'destroy'},5)
            except BaseException:pass
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            log.close()
        report['seconds']=time.monotonic()-start;report['owned_processes_reaped']=all(process.poll() is not None for process,_,_ in live)
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['result'],report.get('error',''),flush=True)
    return 0 if report['result'].startswith('PASS_') else 1

if __name__=='__main__':raise SystemExit(main())
