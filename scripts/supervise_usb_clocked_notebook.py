#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Closed Clocked13 launch adapter for the unchanged USB workflow supervisor."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import check_guest_usb_clocked_notebook as clocked
import supervise_usb_notebook as supervisor

ROOT=Path(__file__).resolve().parents[1]
BASE_SUPERVISOR_SHA256='6c1af6b08702a7481ceec656d5528447138a1010aa61c78fb2c33e1ee0df67ee'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    launch=sub.add_parser('launch')
    for name in ('native-bundle','host-prepared','formatted-peer','formatted-outbox','work-dir'):
        launch.add_argument('--'+name,type=Path,required=True)
    worker=sub.add_parser('_run');worker.add_argument('manifest',type=Path)
    args=parser.parse_args()
    if supervisor.digest(supervisor.__file__)!=BASE_SUPERVISOR_SHA256:
        raise ValueError('inherited bounded supervisor changed')
    observer=ROOT/'scripts/check_guest_usb_clocked_notebook.py'
    if args.action=='_run':
        data=json.loads(args.manifest.read_text())
        if (data.get('clocked_supervisor_sha256')!=supervisor.digest(__file__) or
                data.get('clocked_observer_sha256')!=supervisor.digest(observer) or
                data.get('profile')!=clocked.NAME or data['argv'][1]!=str(observer)):
            raise ValueError('Clocked adapter source or deployment changed')
        return supervisor.supervise(args.manifest)
    if supervisor.digest(ROOT/'scripts/check_guest_usb_notebook.py')!=clocked.BASE_SHA256:
        raise ValueError('inherited notebook workflow changed')
    clocked.bundle.prepared(args.native_bundle,'rtl',clocked.ROLE,clocked.NAME)
    work=args.work_dir.resolve();out=work.with_name(work.name+'.supervision')
    if work.exists() or out.exists() or not work.is_relative_to(ROOT/'build'):
        parser.error('unused owned workflow and supervision outputs required')
    out.mkdir(parents=True,mode=0o700)
    argv=[sys.executable,str(observer),'--profile',clocked.NAME]
    for name in ('native_bundle','host_prepared','formatted_peer','formatted_outbox','work_dir'):
        argv+=['--'+name.replace('_','-'),str(getattr(args,name).resolve())]
    now=time.time_ns()
    data={'schema':'lemma-usb-notebook-supervision/1','profile':clocked.NAME,
          'work_dir':str(work),'argv':argv,'supervisor_sha256':BASE_SUPERVISOR_SHA256,
          'observer_sha256':clocked.BASE_SHA256,'clocked_supervisor_sha256':supervisor.digest(__file__),
          'clocked_observer_sha256':supervisor.digest(observer),'started_unix_ns':now,
          'absolute_deadline_unix_ns':now+supervisor.MAX_SECONDS*1000000000,
          'whole_host_ceiling_seconds':supervisor.MAX_SECONDS,
          'policy':{'automatic_restart':False,'virtual_time':'inherited original bounded machine quanta and oracles',
                    'external_wall_timeout':'actual60s USB process inactivity remains; paused owner may disconnect',
                    'pause':'no automatic pause or deadline extension; supervisor survives tool/inference interruption',
                    'cancellation':'SIGTERM supervisor; inherited owned-child cleanup and original180s deadline grace'}}
    manifest=out/'manifest.json';manifest.write_text(json.dumps(data,indent=2)+'\n')
    with (out/'supervisor.log').open('xb') as log:
        child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_run',str(manifest)],
                               cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    data['supervisor']=supervisor.identity(child.pid);supervisor.atomic_json(out/'launch.json',data)
    print(json.dumps({'supervisor':data['supervisor'],'manifest':str(manifest),
                      'absolute_deadline_unix_ns':data['absolute_deadline_unix_ns']}))
    return 0

if __name__=='__main__':raise SystemExit(main())
