#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Public native Pending restore/bind/run commands and isolated fork resources.

Reuses a qualified actual peer outcome corpus. It never opens the original peer
or medium and does not rerun its initialization or claim cold guest recovery.
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time
from check_native_backing import ROOT,sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build','qualified-observation','work-dir'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic();process=None
    result={'status':'FAIL','scope':__doc__}
    try:
        observed=json.loads(args.qualified_observation.read_text());manifest=json.loads((args.rtl_build/'build.json').read_text())
        if observed.get('status')!='PASS' or observed.get('inputs',{}).get('native_sha256')!=manifest['binary_sha256']:raise ValueError('Qualified actual corpus native identity differs')
        corpus=Path(observed['executed_run']);binary=args.rtl_build/'obj/lemma-rtl'
        if sha(binary)!=manifest['binary_sha256']:raise ValueError('Immutable native binary differs')
        for name,item in observed['files'].items():
            if sha(item['path'])!=item['sha256']:raise ValueError('Actual corpus artifact differs: '+name)
        peak=0;commands=[]
        with (out/'stderr.log').open('xb') as errors:
            process=subprocess.Popen([binary,'--session','--restore',corpus/'pending.snap','--fork-directory',out,'--uart-output',out/'uart.bin','--quiet-uart'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,bufsize=0,start_new_session=True)
            def call(command):
                nonlocal peak
                before=time.monotonic();process.stdin.write(command.encode()+b'\n');process.stdin.flush();line=bytearray()
                while not line.endswith(b'\n'):
                    if time.monotonic()-before>30:raise TimeoutError('Native command deadline: '+command)
                    if select.select([process.stdout],[],[],.01)[0]:
                        part=os.read(process.stdout.fileno(),1)
                        if not part:raise ValueError('Native runtime exited before command result')
                        line+=part
                    try:
                        for row in (Path('/proc')/str(process.pid)/'status').read_text().splitlines():
                            if row.startswith('VmHWM:'):peak=max(peak,int(row.split()[1]))
                    except FileNotFoundError:pass
                response=json.loads(line);seconds=time.monotonic()-before;commands.append({'command':command,'host_seconds':seconds,'response':response});return response
            response=call('inspect');state=response['result'];cycle=state['cycle'];restore_seconds=time.monotonic()-started
            if not state['backing_io']['fork_suspended'] or cycle!=observed['measurement']['snapshot_cycle']:raise ValueError('Native restore lost inherited Pending ownership')
            rejection=call('run 1')
            if rejection.get('ok') is not False or 'virtual clock unchanged' not in rejection.get('error',''):raise ValueError('Missing tape did not explicitly suspend')
            if call('inspect')['result']['cycle']!=cycle:raise ValueError('Rejected run advanced the virtual clock')
            call('backing-outcomes '+str(corpus/'actual.io'));call('companion-retry')
            final=observed['measurement']['final_cycle'];response=call('run '+str(final-cycle))
            if response.get('ok') is False or response['result']['cycle']!=final:raise ValueError('Native public suffix did not reach exact final cycle')
            call('snapshot '+str(out/'replay.snap'));call('destroy');process.wait(timeout=5)
        with (corpus/'complete.snap').open('rb') as original,(out/'replay.snap').open('rb') as replay:
            while True:
                a,b=original.read(1048576),replay.read(1048576)
                if a!=b:raise ValueError('Public native authoritative suffix differs')
                if not a:break
        result.update(status='PASS',native_sha256=manifest['binary_sha256'],snapshot_identity=manifest['snapshot_identity'],qualified_actual_observation={'path':str(args.qualified_observation),'sha256':sha(args.qualified_observation)},checker_sha256=sha(__file__),restore_seconds_including_startup=restore_seconds,peak_native_rss_kib=peak,exact_suffix=True,commands=commands,final_checkpoint_sha256=sha(out/'replay.snap'),all_owned_processes_reaped=True)
    except BaseException as error:result['error']=str(error);raise
    finally:
        if process and process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
        result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
