#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent host staging property and comparable canonical-pixel benchmark."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    result={'status':'FAIL','scope':'Independent ordered-map property and equivalent full canonical pixel staging; not guest or Machine integration'}
    start=time.monotonic()
    try:
        result['sources']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('sim/host/panel_pending.h','tests/lemmasim/panel_pending.cpp')}
        result['compiler']=subprocess.check_output(['c++','--version'],text=True,timeout=10).splitlines()[0]
        command=['c++','-std=c++20','-O2','-Wall','-Wextra','-Werror',str(ROOT/'tests/lemmasim/panel_pending.cpp'),'-o',str(out/'panel-pending')]
        result['command']=command
        compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (out/'compile.log').write_text(compiled.stdout+compiled.stderr);compiled.check_returncode()
        code='import subprocess,resource,json,sys; p=subprocess.run(sys.argv[1:],capture_output=True,text=True); print(p.stdout,end=""); print(p.stderr,end="",file=sys.stderr); print(json.dumps({"max_rss_kib":resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}),file=sys.stderr); raise SystemExit(p.returncode)'
        records={}
        for mode in ('property','map','indexed'):
            run=subprocess.run(['python3','-c',code,str(out/'panel-pending'),mode],capture_output=True,text=True,timeout=60)
            (out/(mode+'.log')).write_text(run.stdout+run.stderr);run.check_returncode()
            match=re.search(r'checksum=(\d+) host_seconds=([0-9.e+-]+)',run.stdout)
            if not match:raise ValueError('Missing actual staging result')
            records[mode]={'output':run.stdout.strip(),'checksum':match[1],'host_seconds':float(match[2]),**json.loads(run.stderr.strip())}
        if records['map']['checksum']!=records['indexed']['checksum']:raise ValueError('Independent map/indexed full-pixel checksums differ')
        result.update(status='PASS_HOST_STAGING_ONLY',records=records)
    except Exception as error:
        result['error']=str(error)
    finally:
        result['host_seconds']=time.monotonic()-start
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS_HOST_STAGING_ONLY' else 1

if __name__=='__main__':raise SystemExit(main())
