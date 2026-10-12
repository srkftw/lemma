#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Power-v2 native circuit/state qualification; literal initialized state, no guest-driver claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(argv,log,timeout):
    with Path(log).open('xb') as stream:
        process=subprocess.Popen(list(map(str,argv)),cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code=process.wait(timeout=timeout)
            if code:raise subprocess.CalledProcessError(code,argv)
        finally:
            if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=10)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rtl-build',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--guest-bundle',type=Path,required=True);p.add_argument('--fixture',choices=('domain','fault-pending'),default='domain')
    a=p.parse_args();build=a.rtl_build.resolve();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    result={'status':'FAIL','scope':__doc__,'build':str(build),'fixture':a.fixture}
    try:
        import silicon_guest_bundle
        guest=silicon_guest_bundle.prepared(a.guest_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');entry=guest['workloads']['notebook']
        manifest=json.loads((build/'build.json').read_text())
        if manifest.get('profile')!='lemma-silicon-dev/0.4.0':raise ValueError('Power-v2 requires exact 0.4.0 native build')
        identities={Path(path):h for path,h in manifest['sha256'].items()}
        identities.update({ROOT/path:h for path,h in manifest['host_runtime'].items()})
        identities[ROOT/'sim/rtl/host/main.cpp']=manifest['host_adapter']['sha256']
        identities[build/'obj/lemma-rtl']=manifest['binary_sha256']
        for path,h in identities.items():
            if sha(path)!=h:raise ValueError('Stale consumed native input: '+str(path))
        version=subprocess.check_output(['verilator','-V'],text=True)
        prefixes=set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$',version,re.M))
        if len(prefixes)!=1:raise ValueError('Missing/ambiguous pinned Verilator root')
        prefix=Path(prefixes.pop());obj=build/'obj'
        names=['machine_runtime.o','backing_io.o','backing_io_posix.o','verilated.o','verilated_save.o','verilated_threads.o','verilated_dpi.o','Vlemma_soc__ALL.a']
        inputs={str(obj/n):sha(obj/n) for n in names}
        source=ROOT/('tests/lemmasim/native_power_pending.cpp' if a.fixture=='fault-pending' else 'tests/lemmasim/native_power_safety.cpp');binary=out/'test'
        run(['c++','-O2','-std=c++17','-I',ROOT/'sim/rtl/host','-I',obj,'-I',prefix/'include','-I',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        run([binary,out,entry['image']['path'],guest['rom']['path'],entry['dtb']['path'],entry['descriptor']['path'],'0x87e00000'],out/'run.log',60)
        expected='PASS brownout orphans' if a.fixture=='fault-pending' else 'PASS real machine watchdog'
        if expected not in (out/'run.log').read_text():raise ValueError('Missing actual fixture result')
        pairs= [('partial-complete.snap','partial-replay.snap'),('barrier-complete.snap','barrier-replay.snap')] if a.fixture=='fault-pending' else [('watchdog-complete.snap','watchdog-replay.snap'),('loss-complete.snap','loss-replay.snap')]
        for left,right in pairs:
            if (out/left).read_bytes()!=(out/right).read_bytes():raise ValueError('Exact completed suffix differs')
        for path,h in identities.items():
            if sha(path)!=h:raise ValueError('Consumed source changed during qualification')
        result.update(status='PASS',snapshot_identity=manifest['snapshot_identity'],native_sha256=manifest['binary_sha256'],fixture_sha256=sha(source),test_binary_sha256=sha(binary),compiled_inputs=inputs,
                      authoritative_suffix_bytes_equal=True,pending_external_snapshot_admitted=a.fixture=='fault-pending',
                      files={path.name:sha(path) for path in sorted(out.iterdir()) if path.suffix in ('.snap','.io','.log')})
        result['archived_genuine_guest']={'image':entry['image'],'rom':guest['rom'],'archive':guest['native_bundle'],'scope':'Unchanged archived genuine guest instructions supply the CPU prefix; watchdog/controller state is initialized literally. No new driver or Ready claim'}
    except BaseException as e:result['error']=str(e);raise
    finally:
        result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
