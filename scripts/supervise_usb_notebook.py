#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Supervise one bounded USB notebook observer without automatic restarts.

The detached supervisor survives tool/inference interruptions. Virtual clocks
remain controlled by the original observer; external host timeouts are never
reset. Cancellation reaps only processes recorded in this owned descendant tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
MAX_SECONDS=65000  # Nine declared7200s phases plus200s startup/cleanup overhead.


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def identity(pid):
    try:
        raw=(Path('/proc')/str(pid)/'stat').read_text();at=raw.rfind(') ')
        fields=raw[at+2:].split();return {'pid':pid,'start_ticks':int(fields[19])}
    except (FileNotFoundError,ProcessLookupError):return None

def descendants(pid):
    pending,seen,rows=[pid],set(),[]
    while pending:
        q=pending.pop()
        if q in seen:continue
        seen.add(q)
        if len(seen)>64:raise RuntimeError('owned process bound exceeded')
        item=identity(q)
        if item is None:continue
        rows.append(item)
        try:pending.extend(int(x) for x in (Path('/proc')/str(q)/'task'/str(q)/'children').read_text().split())
        except (FileNotFoundError,ProcessLookupError):pass
    return rows

def alive(item):return identity(item['pid'])==item

def atomic_json(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)

def supervise(manifest):
    data=json.loads(manifest.read_text());out=manifest.parent
    if data['supervisor_sha256']!=digest(__file__) or data['observer_sha256']!=digest(ROOT/'scripts/check_guest_usb_notebook.py'):raise ValueError('supervisor/observer source changed before execution')
    cancelled=False
    def cancel(_signal,_frame):
        nonlocal cancelled;cancelled=True
    signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
    log=(out/'observer.log').open('xb');child=subprocess.Popen(data['argv'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    known={};record={**data,'status':'RUNNING','supervisor':identity(os.getpid()),'observer':identity(child.pid)}
    try:
        while child.poll() is None:
            known={key:item for key,item in known.items() if alive(item)}
            for item in descendants(child.pid):known[(item['pid'],item['start_ticks'])]=item
            record['last_heartbeat_unix_ns']=time.time_ns();record['owned_live']=[x for x in known.values() if alive(x)];atomic_json(out/'supervision.json',record)
            if cancelled or time.time_ns()>=data['absolute_deadline_unix_ns']:
                record['cause']='explicit cancellation' if cancelled else 'predeclared absolute supervisor deadline'
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=180)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
                break
            time.sleep(.5)
        child.wait(timeout=10);record['observer_exit_code']=child.returncode
        result=Path(data['work_dir'])/'result.json'
        record['status']='PASS' if not cancelled and 'cause' not in record and child.returncode==0 and result.is_file() and json.loads(result.read_text()).get('status')=='PASS' else 'FAIL'
        if result.is_file():record['result_sha256']=digest(result)
    finally:
        if child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=180)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=10)
        # Record start-time identities protect against PID reuse. Stop only
        # survivors belonging to this exact observer, never a global scan.
        survivors=[x for x in known.values() if alive(x)]
        for item in survivors:
            try:os.kill(item['pid'],signal.SIGTERM)
            except ProcessLookupError:pass
        end=time.monotonic()+10
        while any(alive(x) for x in survivors) and time.monotonic()<end:time.sleep(.05)
        for item in survivors:
            if alive(item):
                try:os.kill(item['pid'],signal.SIGKILL)
                except ProcessLookupError:pass
        record['owned_survivors']=[x for x in survivors if alive(x)];record['finished_unix_ns']=time.time_ns()
        if record['owned_survivors']:record['status']='FAIL'
        atomic_json(out/'supervision.json',record);log.close()
    return 0 if record['status']=='PASS' else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    launch=sub.add_parser('launch')
    for name in ('host-prepared','formatted-peer','formatted-outbox','work-dir'):launch.add_argument('--'+name,type=Path,required=True)
    launch.add_argument('--profile',choices=('lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0'),default='lemma-silicon-dev/0.6.0')
    launch.add_argument('--native-bundle',type=Path)
    launch.add_argument('--rtl-source-root',type=Path)
    launch.add_argument('--guest-source-root',type=Path)
    worker=sub.add_parser('_run');worker.add_argument('manifest',type=Path)
    a=p.parse_args()
    if a.action=='_run':return supervise(a.manifest)
    if not ((a.native_bundle is None and a.rtl_source_root is not None and a.guest_source_root is not None) or
            (a.profile=='lemma-silicon-dev/0.8.0' and a.native_bundle is not None and a.rtl_source_root is None and a.guest_source_root is None)):
        p.error('explicit complete source archives or one USB8 immutable bundle required')
    work=a.work_dir.resolve();supervision=work.with_name(work.name+'.supervision')
    if work.exists() or supervision.exists() or not work.is_relative_to(ROOT/'build'):p.error('unused owned campaign and supervision outputs under build required')
    supervision.mkdir(parents=True,mode=0o700)
    argv=[sys.executable,str(ROOT/'scripts/check_guest_usb_notebook.py')]
    argv+=['--profile',a.profile]
    for name in ('host_prepared','rtl_source_root','guest_source_root','native_bundle','formatted_peer','formatted_outbox','work_dir'):
        value=getattr(a,name)
        if value is not None:argv+=['--'+name.replace('_','-'),str(value.resolve())]
    now=time.time_ns();data={'schema':'lemma-usb-notebook-supervision/1','work_dir':str(work),'argv':argv,'supervisor_sha256':digest(__file__),'observer_sha256':digest(ROOT/'scripts/check_guest_usb_notebook.py'),'started_unix_ns':now,'absolute_deadline_unix_ns':now+MAX_SECONDS*1000000000,'whole_host_ceiling_seconds':MAX_SECONDS,
        'policy':{'automatic_restart':False,'virtual_time':'original observer bounded quanta; no schedule or timeout reset','external_wall_timeout':'unchanged actual USB process60s inactivity; a paused owner may disconnect','pause':'no automatic pause; supervisor survives tool/inference interruption; manual machine pause is not hidden from host wall time','cancellation':'SIGTERM supervisor; observer handles interruption and reaps owned children; deadline180s grace then owned identities only'}}
    manifest=supervision/'manifest.json';manifest.write_text(json.dumps(data,indent=2)+'\n')
    log=(supervision/'supervisor.log').open('xb');process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_run',str(manifest)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);log.close();data['supervisor']=identity(process.pid);atomic_json(supervision/'launch.json',data)
    print(json.dumps({'supervisor':data['supervisor'],'manifest':str(manifest),'absolute_deadline_unix_ns':data['absolute_deadline_unix_ns']}));return 0


if __name__=='__main__':raise SystemExit(main())
