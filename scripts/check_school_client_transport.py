#!/usr/bin/env python3
"""Exercise the real Lean school through the client's mutex and HTTP transport.

No guest or school policy is emulated. This checks local byte routing, a real
authority process, concurrent-writer refusal, and fail-closed endpoint bounds.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from lemmasim_school import school_call


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args(); out=args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):
        parser.error('unused ignored build output required')
    out.mkdir(parents=True); binary=args.binary.resolve(); root=out/'school'
    report={'schema':'lemma-school-client-transport-check/1','status':'FAIL','scope':__doc__,'cases':[]}
    child=None; started=time.monotonic()
    try:
        report['binary']={'path':str(binary),'sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
        school_call(binary,root,dict(op='init',school='transport-school',actor='owner',deployment='transport-local',clockModel='monotonic-ms'),out,'init')
        report['cases'].append('actual Lean initialization through OS mutex')
        with socket.socket() as reserved:
            reserved.bind(('127.0.0.1',0)); port=reserved.getsockname()[1]
        endpoint=f'http://127.0.0.1:{port}/v1/command'
        command=[sys.executable,str(ROOT/'scripts/school_transport.py'),'--binary',str(binary),str(root),'run','--port',str(port)]
        log=(out/'http-stderr.log').open('xb')
        child=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log)
        status=dict(op='status',school='transport-school',actor='owner')
        until=time.monotonic()+15
        while True:
            if child.poll() is not None: raise ValueError('actual HTTP authority exited before admission')
            try:
                result=school_call(binary,root,status,out,'http-status',endpoint)
                break
            except urllib.error.URLError:
                if time.monotonic()>=until: raise
                time.sleep(0.02)
        if result.get('school')!='transport-school' or result.get('generation',0)<2:
            raise ValueError('real long-lived authority identity/generation absent')
        report['cases'].append('actual HTTP status from long-lived Lean authority')
        try:
            school_call(binary,root,status,out,'concurrent-direct')
            raise ValueError('second writer bypassed the OS mutex')
        except ValueError:
            if b'already owned by another process' not in (out/'concurrent-direct-stderr.log').read_bytes(): raise
        report['cases'].append('concurrent direct writer refused by actual mutex')
        for index,endpoint in enumerate(('https://127.0.0.1:8790/v1/command','http://example.invalid/v1/command','http://127.0.0.1:8790/other')):
            try:
                school_call(binary,root,status,out,'endpoint-negative-'+str(index),endpoint)
                raise RuntimeError('unsupported endpoint unexpectedly admitted')
            except ValueError as error:
                if 'endpoint must be' not in str(error): raise
        report['cases'].append('nonlocal/TLS/other-path endpoints rejected before network I/O')
        try:
            school_call(binary,root,{'opaque':'x'*1048577},out,'oversized',f'http://127.0.0.1:{port}/v1/command')
            raise RuntimeError('oversized request unexpectedly admitted')
        except ValueError as error:
            if 'request exceeds' not in str(error): raise
        report['cases'].append('oversized request rejected without reaching authority')
        final=school_call(binary,root,status,out,'http-still-responsive',f'http://127.0.0.1:{port}/v1/command')
        if final.get('generation')!=result['generation']: raise ValueError('transport restarted the authority')
        report['cases'].append('same authority remains responsive after rejected requests')
        report['status']='PASS_REAL_LEAN_TRANSPORT'
    except BaseException as error:
        report['error']=repr(error)
    finally:
        if child is not None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill();child.wait(timeout=10)
            log.close(); report['process_exit']=child.returncode
        report['seconds']=time.monotonic()-started
        report['source_inputs']={relative:hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() for relative in
            ('scripts/lemmasim_school.py','scripts/school_transport.py','scripts/check_school_client_transport.py')}
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return 0 if report['status']=='PASS_REAL_LEAN_TRANSPORT' else 1


if __name__=='__main__': raise SystemExit(main())
