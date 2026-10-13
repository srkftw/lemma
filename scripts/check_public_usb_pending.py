#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual public USB6 snapshot/tape commands; genuine guest and isolated forks."""
import argparse,json,os,signal,subprocess,sys,time
from pathlib import Path
from check_guest_usb_link import ROOT,require,sha,request
from check_guest_usb_notebook import copy_opaque_peer
from lemmasim_usb import validate as validate_host
from lemmasim_companion import validate as validate_companion


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('host-prepared','rtl-source-root','guest-source-root','formatted-peer','formatted-outbox','work-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.work_dir.resolve();require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused owned output');out.mkdir(parents=True)
    start=time.monotonic();deadline=start+900;owners=[];peer=None;logs=[]
    report={'schema':'lemma-public-usb-pending/1','status':'FAIL','scope':'public commands on genuine RV64 USB6 startup/reset/owned endpoint heads and queues; recorded same-native suffix only, not privately live peer or USB PHY','bounds':{'original_cycles':20000000,'host_seconds':900}}
    def call(directory,value):
        require(time.monotonic()<deadline,'public qualification host bound');return request(directory,value,timeout=min(130,deadline-time.monotonic()))
    def inspect(directory):return call(directory,{'action':'inspect'})['machine']
    def rejected(directory,value):
        before=inspect(directory)
        try:call(directory,value)
        except RuntimeError as e:error=str(e)
        else:raise ValueError('operation unexpectedly accepted: '+str(value))
        require(inspect(directory)==before,'rejection changed authoritative state');return error
    def launch(label,restore=None,tape=None):
        directory=out/label;log=(out/(label+'.log')).open('xb');logs.append(log)
        cmd=[sys.executable,str(ROOT/'scripts/lemmasim'),'session','--backend','rtl','--profile','lemma-silicon-dev/0.6.0','--workload','usb-bulk-initializer','--mode','laboratory','--headless','--paused','--session-dir',str(directory),'--timeout','120','--quantum','1000','--rtl-source-root',str(a.rtl_source_root.resolve()),'--guest-source-root',str(a.guest_source_root.resolve())]
        if restore is None:cmd+=['--usb-host-prepared',str(a.host_prepared.resolve()),'--usb-peer-directory',str(out/'peer'),'--usb-peer-socket',str(out/'peer.sock'),'--usb-host-state',str(out/'outbox')]
        else:cmd+=['--restore',str(restore)]
        if tape is not None:cmd+=['--usb-replay',str(tape)]
        proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);owners.append((directory,proc))
        end=time.monotonic()+60
        while not (directory/'session.json').exists():
            require(proc.poll() is None and time.monotonic()<end,'public startup failed '+label);time.sleep(.01)
        state=inspect(directory);return directory,state,cmd
    def snapshot(directory,label):
        before=inspect(directory);capture=directory/'usb.raw';old=sha(capture) if capture.exists() else None;path=out/(label+'.snapshot');call(directory,{'action':'snapshot','path':str(path)});require(inspect(directory)==before and (old is None or sha(capture)==old),'snapshot altered live USB state/capture');return path,before
    def cut(directory,label,suffix):
        checkpoint,before=snapshot(directory,label);prefix=out/(label+'-prefix.tape');call(directory,{'action':'export-usb-replay','path':str(prefix)});require(inspect(directory)==before,'export advanced original state')
        call(directory,{'action':'run','cycles':suffix});final,after=snapshot(directory,label+'-final');tape=out/(label+'.tape');call(directory,{'action':'export-usb-replay','path':str(tape)})
        fork,state,argv=launch(label+'-fork',checkpoint);require(state['usb']['fork_suspended'],'no-tape public fork not suspended');errors=[rejected(fork,{'action':'run','cycles':1})]
        call(fork,{'action':'usb-outcomes','path':str(prefix)});errors.append(rejected(fork,{'action':'run','cycles':1}));call(fork,{'action':'usb-outcomes','path':str(tape)});errors.append(rejected(fork,{'action':'run','cycles':suffix+1}));call(fork,{'action':'run','cycles':suffix});f,_=snapshot(fork,label+'-replay');require(sha(f/'machine.chk')==sha(final/'machine.chk'),'public exact suffix differs')
        call(fork,{'action':'destroy'});owners[-1][1].wait(timeout=10)
        bound,state2,argv2=launch(label+'-bound',checkpoint,tape);require(not state2['usb']['fork_suspended'] and state2['cycle']==before['cycle'],'CLI restore/tape binding advanced or stayed suspended');call(bound,{'action':'run','cycles':suffix});f2,_=snapshot(bound,label+'-bound-replay');require(sha(f2/'machine.chk')==sha(final/'machine.chk'),'CLI-bound exact suffix differs');call(bound,{'action':'destroy'});owners[-1][1].wait(timeout=10)
        require(inspect(directory)==after,'private public forks changed original owner')
        report.setdefault('cases',[]).append({'label':label,'snapshot_cycle':before['cycle'],'suffix_cycles':suffix,'before':before['usb'],'after':after['usb'],'rejected':errors,'fork_argv':argv,'bound_argv':argv2,'snapshot_sha256':sha(checkpoint/'machine.chk'),'suffix_sha256':sha(final/'machine.chk')})
    try:
        validate_host(a.host_prepared);prepared=a.host_prepared.resolve().parent/'companion/prepared.json';validate_companion(prepared);copy_opaque_peer(a.formatted_peer.resolve(),out/'peer',a.formatted_outbox.resolve(),out/'outbox')
        log=(out/'peer.log').open('xb');logs.append(log);peer=subprocess.Popen([sys.executable,str(ROOT/'scripts/lemmasim'),'companion','serve','--prepared',str(prepared),'--directory',str(out/'peer'),'--socket',str(out/'peer.sock')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        end=time.monotonic()+15
        while not (out/'peer.sock').exists():require(peer.poll() is None and time.monotonic()<end,'peer startup');time.sleep(.01)
        live,state,argv=launch('live');report['identity']=call(live,{'action':'inspect'})['identity'];report['live_argv']=argv;require(state['cycle']==0,'original CPU not cold');cut(live,'startup',5000)
        while inspect(live)['usb']['command']!='RESET 5000000':require(inspect(live)['cycle']<1000000,'reset not admitted');call(live,{'action':'run','cycles':1000})
        cut(live,'reset',3000);seen=set()
        while seen!={'owned-receive','owned-submit'}:
            s=inspect(live);require(not s['finished'] and s['cycle']<20000000,'actual guest endpoint heads not reached');call(live,{'action':'run','cycles':1000});s=inspect(live)
            # Observe the actual RTL EP1 guest-submit queue and EP2 decoded
            # receive head, never infer them from host command success.
            if 'owned-submit' not in seen and s['usb']['configured'] and s['usb']['tx_queued_mask']&2:
                cut(live,'owned-submit',5000);seen.add('owned-submit')
            if 'owned-receive' not in seen and s['usb']['configured'] and s['usb']['rx_head_mask']&2:
                cut(live,'owned-receive',5000);seen.add('owned-receive')
        call(live,{'action':'warm-reset'});cut(live,'domain-reset',3000);require(inspect(live)['usb']['terminal'],'domain reset did not cancel original host')
        report['status']='PASS'
    except BaseException as e:report['error']=repr(e)
    finally:
        for directory,proc in owners:
            if proc.poll() is None:
                try:call(directory,{'action':'destroy'});proc.wait(timeout=10)
                except BaseException:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        if peer is not None and peer.poll() is None:os.killpg(peer.pid,signal.SIGTERM);peer.wait(timeout=10)
        for log in logs:log.close()
        report['host_seconds']=time.monotonic()-start;report['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
