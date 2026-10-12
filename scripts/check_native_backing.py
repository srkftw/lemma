#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Literal RTL/runtime pending I/O qualification; no guest-driver claim."""
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rtl-build',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--guest-bundle',type=Path,required=True);p.add_argument('--fixture',choices=('pending','fault-pending'),default='pending')
    a=p.parse_args();build=a.rtl_build.resolve();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
    result={'status':'FAIL','scope':__doc__,'build':str(build)}
    try:
        import silicon_guest_bundle
        guest=silicon_guest_bundle.prepared(a.guest_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');entry=guest['workloads']['notebook']
        manifest=json.loads((build/'build.json').read_text())
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
        source=ROOT/('tests/lemmasim/native_pending.cpp' if a.fixture=='pending' else 'tests/lemmasim/native_fault_pending.cpp');binary=out/'test'
        run(['c++','-O2','-std=c++17','-I',ROOT/'sim/rtl/host','-I',obj,'-I',prefix/'include','-I',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        run([binary,out,entry['image']['path'],guest['rom']['path'],entry['dtb']['path'],entry['descriptor']['path'],'0x87e00000'],out/'run.log',60)
        if ('PASS held request' if a.fixture=='pending' else 'PASS actual partial pwrite') not in (out/'run.log').read_text():raise ValueError('Missing actual fixture result')
        pairs=[('complete.snap','replay.snap')] if a.fixture=='pending' else [('partial-complete.snap','partial-replay.snap'),('barrier-complete.snap','barrier-replay.snap')]
        for left,right in pairs:
            if (out/left).read_bytes()!=(out/right).read_bytes():raise ValueError('Exact completed suffix differs')
        for path,h in identities.items():
            if sha(path)!=h:raise ValueError('Consumed source changed during qualification')
        result.update(status='PASS',snapshot_identity=manifest['snapshot_identity'],native_sha256=manifest['binary_sha256'],fixture_sha256=sha(source),test_binary_sha256=sha(binary),compiled_inputs=inputs,
                      authoritative_suffix_bytes_equal=True,pending_external_snapshot_admitted=True,
                      files={path.name:sha(path) for path in sorted(out.iterdir()) if path.suffix in ('.snap','.io','.log')})
        result['archived_genuine_guest']={'image':entry['image'],'rom':guest['rom'],'archive':guest['native_bundle'],'scope':'Real guest instructions run while literal initialized controller request is held; no guest-driver or Ready claim'}
    except BaseException as e:result['error']=str(e);raise
    finally:
        result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
