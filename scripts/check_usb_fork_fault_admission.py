#!/usr/bin/env python3
"""Zero-cycle actual native admission/horizon checks for injected EOF forks."""
import argparse
import json
from pathlib import Path
import time

from check_guest_usb_link import ROOT, require, sha
from check_guest_usb_notebook import Checker
from check_usb_fork_disconnect import ForkSession, create_fault
from usb_fork_fault import prefix, chain, file_record, PROFILE


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('native-bundle','host-prepared','boundary','snapshot','prefix-tape','capture','work-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.profile=PROFILE;args.rtl_source_root=args.guest_source_root=None
    args.cold_cycles=1600000000;args.cold_deadline=7200;args.ink_cycles=200000000
    args.action_cycles=1600000000;args.action_deadline=7200
    checker=Checker(args);started=time.monotonic()
    checker.report.update(schema='lemma-usb-fork-fault-admission/1',status='FAIL',
        scope=__doc__,bounds={'whole_host_seconds':120,'target_cycles':0,'maximum_owned_rss_kib':4194304})
    try:
        session=ForkSession(checker,args);initial=session.start
        sidecar=create_fault(args,initial,session.identity,checker.out)
        data=json.loads(sidecar.read_text());horizon=initial['cycle']+1000
        rows,logical=prefix(args.prefix_tape,initial['snapshot_identity'],initial['cycle'])
        fault=data['fault'];fault['horizon']=horizon
        row=f"{fault['cycle']} 2 {fault['request_id']} {fault['frame']}\n".encode()
        value=chain(row,logical['accepted_hash']);bridge=Path(data['bridge']['path'])
        bridge.write_bytes(f'LMUSBRP1 {initial["snapshot_identity"]}\nHORIZON {horizon}\n'.encode()+b''.join(rows)+row+
            f'CHECKSUM {chain(f"{horizon} 3 0 HORIZON\n".encode(),value)}\n'.encode())
        data['bridge']=file_record(bridge);sidecar.write_text(json.dumps(data,indent=2)+'\n')
        def rejected(command):
            before=session.machine()
            try:session.control(command)
            except RuntimeError as error:text=str(error)
            else:raise ValueError('negative admitted')
            require(session.machine()==before,'negative advanced or changed native state');return text
        errors={'no-tape':rejected({'action':'run','cycles':1}),
                'historical-sidecar':rejected({'action':'usb-outcomes','path':str(sidecar)})}
        session.control({'action':'usb-fault','path':str(sidecar)})
        errors['actual-native-horizon']=rejected({'action':'run','cycles':1001})
        require('exceeds captured horizon' in errors['actual-native-horizon'],'horizon failed at an unrelated argument guard')
        errors['duplicate-fault']=rejected({'action':'usb-fault','path':str(sidecar)})
        session.control({'action':'snapshot','path':str(checker.out/'admitted')})
        require(sha(checker.out/'admitted/machine.chk')==sha(args.snapshot/'machine.chk'),
                'admission mutated any original serialized state before edge')
        require(session.machine()['cycle']==initial['cycle'] and time.monotonic()-started<=120,
                'admission clock or host bound')
        checker.sample_resources()
        checker.report.update(status='PASS_ADMISSION_ONLY',identity=session.identity,exact_all_before_edge_bytes=True,
            rejections=errors,initial_machine=initial,input_files={'fault':file_record(sidecar),'capture':file_record(args.capture),
            'original_machine':file_record(args.snapshot/'machine.chk')},cpu_cycles_executed=0,peer_processes_started=0)
    except BaseException as error:checker.report['error']=repr(error)
    finally:
        for session in checker.sessions:session.close()
        checker.commands.close();checker.progress.close()
        checker.report.update(host_seconds=time.monotonic()-started,
            owned_children_reaped=all(s.process.poll() is not None for s in checker.sessions));checker.update()
    print(json.dumps(checker.report,indent=2));return 0 if checker.report['status']=='PASS_ADMISSION_ONLY' else 1


if __name__=='__main__':raise SystemExit(main())
