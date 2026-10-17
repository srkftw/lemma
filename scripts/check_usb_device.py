#!/usr/bin/env python3
"""Source/tool-bound decoded-packet USB device circuitry qualification.

This leaf check does not claim RV64 guest integration, a USB PHY, a USB class,
an assigned product VID/PID, companion durability or complete USB conformance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
from check_silicon import command,device_build
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--jobs',type=int,choices=[1,2],default=2)
    a=p.parse_args();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('work-dir must be unused under build/')
    if not 30<=a.timeout<=300:p.error('timeout must be30..300seconds')
    out.mkdir(parents=True);started=time.monotonic()
    result={'schema':'lemma-usb-device-evidence/1','status':'FAIL','scope':'literal decoded-packet device + arbitrary partial RX/status-ACK exact circuit suffix; no whole machine/guest/PHY claim'}
    names=['sim/rtl/lemma_usb_device.sv','tests/usb/device.cpp','scripts/check_usb_device.py','scripts/check_silicon.py','tooling/silicon/sim.nix','flake.lock']
    try:
        before={n:sha(ROOT/n) for n in names};result['source_inputs']=before
        obj=out/'obj';obj.mkdir();snapshots=out/'snapshots';snapshots.mkdir()
        argv=['verilator','--cc','--exe','--build','--savable','-Wall','-j',str(a.jobs),'--top-module','lemma_usb_device','--Mdir',str(obj),'-CFLAGS','-std=c++17 -O2',str(ROOT/names[0]),str(ROOT/names[1])]
        built,tools=device_build(argv,out/'tools.json',out/'build.log',a.timeout)
        ran=command([str(obj/'Vlemma_usb_device'),str(snapshots)],out/'simulation.log',30)
        log=(out/'simulation.log').read_text()
        if log.count('USB_DEVICE_LITERAL_PASS cycles=')!=1 or 'FAIL' in log:raise RuntimeError('missing actual USB circuit result')
        for left,right in [('live.state','fork.state'),('partial-live.state','partial-fork.state')]:
            if sha(snapshots/left)!=sha(snapshots/right):raise RuntimeError('authoritative arbitrary circuit suffix differs')
        if before!={n:sha(ROOT/n) for n in names}:raise RuntimeError('consumed USB leaf source changed')
        result.update(status='PASS',commands=[built,ran],tool_inputs=tools,compiled_binary_sha256=sha(obj/'Vlemma_usb_device'),observation=log.strip(),snapshots={f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(snapshots.iterdir())})
    except BaseException as error:result['error']=str(error)
    finally:
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        result['resources']={'largest_reaped_child_peak_rss_kib':usage.ru_maxrss,'reaped_children_user_seconds':usage.ru_utime,'reaped_children_system_seconds':usage.ru_stime}
        result['host_seconds']=time.monotonic()-started
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'host_seconds':result['host_seconds']},indent=2))
    return 0 if result['status']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
