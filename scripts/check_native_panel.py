#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Native indexed pixel staging, snapshot and pipeline suffix; literal pixels."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from check_native_power import ROOT,sha,run

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build','guest-bundle','work-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    result={'status':'FAIL','scope':'Literal pixel staging, observational snapshot and actual RV64 pipeline suffix. Not guest paper/ink/Ready acceptance.'}
    try:
        import silicon_guest_bundle
        guest=silicon_guest_bundle.prepared(args.guest_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');entry=guest['workloads']['notebook']
        build=args.rtl_build.resolve();m=json.loads((build/'build.json').read_text())
        if m['profile']!='lemma-silicon-dev/0.3.0' or 'sim/host/panel_pending.h' not in m['host_runtime']:raise ValueError('Indexed canonical native input missing')
        identities={Path(p):h for p,h in m['sha256'].items()};identities.update({ROOT/p:h for p,h in m['host_runtime'].items()})
        identities[ROOT/'sim/rtl/host/main.cpp']=m['host_adapter']['sha256'];identities[build/'obj/lemma-rtl']=m['binary_sha256']
        for p,h in identities.items():
            if sha(p)!=h:raise ValueError('Changed native source/output: '+str(p))
        version=subprocess.check_output(['verilator','-V'],text=True,timeout=10)
        roots=set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$',version,re.M))
        if len(roots)!=1:raise ValueError('Ambiguous Verilator root')
        prefix=Path(roots.pop());obj=build/'obj'
        names=['machine_runtime.o','backing_io.o','backing_io_posix.o','ble_peer_transport.o','verilated.o','verilated_save.o','verilated_threads.o','verilated_dpi.o','Vlemma_soc__ALL.a']
        source=ROOT/'tests/lemmasim/native_panel_pending.cpp';binary=out/'test'
        run(['c++','-O2','-std=c++17','-I',ROOT/'sim/rtl/host','-I',obj,'-I',prefix/'include','-I',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        run([binary,out,entry['image']['path'],guest['rom']['path'],entry['dtb']['path'],entry['descriptor']['path'],'0x87e00000'],out/'run.log',60)
        if not (out/'run.log').read_text().startswith('PASS literal staged pixels'):raise ValueError('Missing actual property result')
        for left,right in (('pending.snap','restored.snap'),('live-complete.snap','fork-complete.snap'),('live-reset.snap','fork-reset.snap')):
            if sha(out/left)!=sha(out/right):raise ValueError('Authoritative snapshot/suffix differs')
        for p,h in identities.items():
            if sha(p)!=h:raise ValueError('Native source changed during property qualification')
        result.update(status='PASS',snapshot_identity=m['snapshot_identity'],native_sha256=m['binary_sha256'],guest=entry['image'],guest_archive=guest['native_bundle'],fixture_sha256=sha(source),compiled_inputs={n:sha(obj/n) for n in names},files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir()) if p.suffix in ('.snap','.log')})
    except Exception as error:result['error']=str(error)
    finally:
        result['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
