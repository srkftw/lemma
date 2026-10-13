#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Literal USB controller responsiveness after actual raw-process transport failure.
This does not execute a guest notebook or perform a storage commit.
"""
import argparse,json,re,subprocess,time,sys
from pathlib import Path
from check_native_backing import ROOT,run,sha

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl-build',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic();result={'status':'FAIL','scope':__doc__}
    try:
        build=args.rtl_build.resolve();manifest=json.loads((build/'build.json').read_text())
        if manifest['profile']!='lemma-silicon-dev/0.6.0':raise ValueError('USB requires profile6')
        identities={Path(p):v for p,v in manifest['sha256'].items()};identities.update({ROOT/p:v for p,v in manifest['host_runtime'].items()});identities[ROOT/'sim/rtl/host/main.cpp']=manifest['host_adapter']['sha256'];identities[build/'obj/lemma-rtl']=manifest['binary_sha256']
        for p,v in identities.items():
            if sha(p)!=v:raise ValueError('Stale consumed native source: '+str(p))
        version=subprocess.check_output(['verilator','-V'],text=True);roots=set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$',version,re.M))
        if len(roots)!=1:raise ValueError('Ambiguous Verilator root')
        prefix=Path(roots.pop());obj=build/'obj';names=['machine_runtime.o','backing_io.o','backing_io_posix.o','backing_peer.o','ble_peer_transport.o','usb_transport.o','verilated.o','verilated_save.o','verilated_threads.o','verilated_dpi.o','Vlemma_soc__ALL.a'];compiled={str(obj/n):sha(obj/n) for n in names};source=ROOT/'tests/lemmasim/native_usb_disconnect.cpp';binary=out/'test'
        run(['c++','-O2','-std=c++17','-Wall','-Wextra','-Werror','-I',ROOT/'sim/rtl/host','-I',obj,'-isystem',prefix/'include','-isystem',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        python=Path(sys.executable).resolve();python_hash=sha(python)
        run([binary,out,python,ROOT/'tests/usb/disconnect_actor.py'],out/'run.log',110)
        if 'PASS actual USB EOF/pending-RECV/domain-reset capture' not in (out/'run.log').read_text():raise ValueError('Missing actual USB disconnect property result')
        for p,v in identities.items():
            if sha(p)!=v:raise ValueError('Consumed native source changed during qualification: '+str(p))
        measurements=[json.loads(line) for line in (out/'run.log').read_text().splitlines() if line.startswith('{')]
        if len(measurements)!=3:raise ValueError('Missing actual resource/phase measurements')
        result.update(status='PASS',measurements=measurements,snapshot_identity=manifest['snapshot_identity'],binary_sha256=manifest['binary_sha256'],fixture_sha256=sha(source),checker_sha256=sha(__file__),compiled_inputs=compiled,raw_actor_sha256=sha(ROOT/'tests/usb/disconnect_actor.py'),python={'path':str(python),'sha256':python_hash},all_owned_processes_reaped=True,files={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.suffix in ('.raw','.log')})
    except BaseException as error:result['error']=str(error);raise
    finally:result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
