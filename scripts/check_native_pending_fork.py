#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observational native Pending fork against a real hosted-Lean opaque peer.

Literal controller initialization and real RV64 retirement; no Ready or guest
companion-driver claim. Whole authoritative native suffix must match exactly.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import time
from check_native_backing import run, sha, ROOT
import silicon_guest_bundle
import lemmasim_companion
from check_companion_pending import timed_records
from check_companion_session import peer_records


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build','guest-bundle','companion-prepared','work-dir'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--observe-existing',type=Path,help='Correct an independently tested observer using unchanged, already executed fixture artifacts; no live peer work')
    a=p.parse_args();out=a.work_dir.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic();owned=[];server=None;fixture=None
    result={'status':'FAIL','scope':__doc__}
    try:
        prepared=lemmasim_companion.validate(a.companion_prepared)
        guest=silicon_guest_bundle.prepared(a.guest_bundle,'rtl','notebook','lemma-silicon-dev/0.3.0');entry=guest['workloads']['notebook']
        build=a.rtl_build.resolve();manifest=json.loads((build/'build.json').read_text());obj=build/'obj'
        consumed={Path(path):h for path,h in manifest['sha256'].items()};consumed.update({ROOT/path:h for path,h in manifest['host_runtime'].items()});consumed[ROOT/'sim/rtl/host/main.cpp']=manifest['host_adapter']['sha256'];consumed[obj/'lemma-rtl']=manifest['binary_sha256']
        for path,h in consumed.items():
            if sha(path)!=h:raise ValueError('Changed consumed native input: '+str(path))
        version=subprocess.check_output(['verilator','-V'],text=True);prefixes=set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$',version,re.M))
        if len(prefixes)!=1:raise ValueError('Ambiguous Verilator root')
        prefix=Path(prefixes.pop());names=['machine_runtime.o','backing_io.o','backing_io_posix.o','backing_peer.o','verilated.o','verilated_save.o','verilated_threads.o','verilated_dpi.o','Vlemma_soc__ALL.a'];source=ROOT/'tests/lemmasim/native_peer_pending.cpp';binary=out/'test'
        run(['c++','-O2','-std=c++17','-I',ROOT/'sim/rtl/host','-I',obj,'-I',prefix/'include','-I',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        inputs={'native_build_manifest_sha256':sha(build/'build.json'),'native_sha256':manifest['binary_sha256'],'snapshot_identity':manifest['snapshot_identity'],'fixture_sha256':sha(source),'test_binary_sha256':sha(binary),'checker_sha256':sha(__file__),'compiled_inputs':{name:sha(obj/name) for name in names},'guest_image':entry['image'],'guest_archive':guest['native_bundle'],'peer_binaries':prepared['binaries']}
        (out/'inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        if a.observe_existing:
            original=a.observe_existing.resolve();failure=json.loads((original/'result.json').read_text())
            if failure.get('status')!='FAIL' or failure.get('error')!='Expected exactly one opaque write and one barrier receipt':raise ValueError('Reuse requires the retained sole receipt-observer failure')
            if sha(original/'test')!=sha(binary):raise ValueError('Executed fixture binary differs from independently reproduced current input closure')
            lines=(original/'run.log').read_text().splitlines()
            if lines[:3]!=['INITIALIZED','PENDING_SNAPSHOT','COMPLETED'] or not lines[3].startswith('PASS real peer lost-ACK'):raise ValueError('Actual fixture did not complete load-bearing assertions')
            measurement=json.loads(lines[4]);rows=peer_records(original/'peer'/'opaque.log')
            if [row[2] for row in rows]!=[1,2] or [row[4] for row in rows]!=[1,2] or measurement['retired']<=0 or measurement['submissions']!=2 or measurement['passive_reads']!=256:raise ValueError('Independent receipt or resource observation differs')
            records,pending=timed_records(original/'actual.io')
            if pending is not None or len(records)!=2:raise ValueError('Incomplete actual accepted-outcome tape')
            if (original/'complete.snap').read_bytes()!=(original/'replay.snap').read_bytes():raise ValueError('Actual native suffix differs')
            for name in ('pending.snap','fork-pending.snap','complete.snap','replay.snap','rejected.snap'):
                with (original/name).open('rb') as stream:header=stream.read(80)
                if header[:16]!=b'LMSSRTL1'+struct.pack('<Q',2) or header[16:]!=manifest['snapshot_identity'].encode():raise ValueError('Actual checkpoint source identity differs')
            for path,h in consumed.items():
                if sha(path)!=h:raise ValueError('Consumed native input changed during observer qualification')
            result.update(inputs=inputs,status='PASS',qualification='corrected independent receipt observer on unchanged executed fixture; no new peer execution',original_failure={'path':str(original/'result.json'),'sha256':sha(original/'result.json')},executed_run=str(original),measurement=measurement,snapshot_bytes=(original/'pending.snap').stat().st_size,peer_receipt_kinds=[row[2] for row in rows],outcomes=records,exact_suffix=True,missing_tape_clock_advance=0,peak_native_rss_kib=None,resource_limit='Original failure did not retain peak RSS; later isolated fork resource observation is separate',files={name:{'path':str(original/name),'sha256':sha(original/name)} for name in ('pending.snap','fork-pending.snap','complete.snap','replay.snap','rejected.snap','actual.io','run.log')})
            print(json.dumps(result,indent=2));return
        directory=out/'peer';lemmasim_companion.initialize(directory,writer=17);socket=out/'peer.sock';helper=ROOT/'sim/companion/os_io.py'
        def start_peer(name,drop=0):
            log=(out/(name+'.log')).open('xb');process=subprocess.Popen(['python3',ROOT/'sim/companion/server.py','--binary',prepared['binaries']['companion-peer']['path'],'--directory',directory,'--base',directory/'base.img','--writer','17','--helper',helper,'--socket',socket,'--drop-reply',str(drop),'--exit-after-reply',str(drop)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True);owned.append((process,log))
            deadline=time.monotonic()+8
            while not socket.exists():
                if process.poll() is not None or time.monotonic()>deadline:raise ValueError('Real peer failed startup')
                time.sleep(.01)
            return process
        def stop_peer(process):
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        server=start_peer('initial-peer')
        fixture_errors=(out/'fixture.stderr').open('xb')
        fixture=subprocess.Popen(list(map(str,[binary,out,entry['image']['path'],guest['rom']['path'],entry['dtb']['path'],entry['descriptor']['path'],'0x87e00000',prepared['binaries']['companion-client']['path'],socket,out/'client.outbox',helper])),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=fixture_errors,bufsize=0,start_new_session=True)
        owned.append((fixture,fixture_errors));lines=[];peak=0
        def line(timeout):
            nonlocal peak
            deadline=time.monotonic()+timeout;data=bytearray()
            while b'\n' not in data:
                if time.monotonic()>deadline:raise TimeoutError('Native pending fixture output deadline')
                if select.select([fixture.stdout],[],[],min(.1,deadline-time.monotonic()))[0]:
                    part=os.read(fixture.stdout.fileno(),1)
                    if not part:raise ValueError('Native fixture exited before result: '+str(fixture.poll()))
                    data+=part
                try:
                    for text in (Path('/proc')/str(fixture.pid)/'status').read_text().splitlines():
                        if text.startswith('VmHWM:'):peak=max(peak,int(text.split()[1]))
                except FileNotFoundError:pass
            text=data.decode().strip();lines.append(text);return text
        def advance():fixture.stdin.write(b'continue\n');fixture.stdin.flush()
        if line(300)!='INITIALIZED':raise ValueError('No actual accepted-view initialization')
        stop_peer(server);server=start_peer('lost-reply-peer',2);advance()
        if line(40)!='PENDING_SNAPSHOT':raise ValueError('No actual peer Pending snapshot')
        server.wait(timeout=5);journal_before=(directory/'opaque.log').read_bytes();server=start_peer('restart-peer');advance()
        if line(40)!='COMPLETED':raise ValueError('Original Pending completion did not reconcile')
        stop_peer(server);server=None;advance()
        if not line(40).startswith('PASS real peer lost-ACK'):raise ValueError('Missing exact native fork suffix result')
        measurement=json.loads(line(5));code=fixture.wait(timeout=5)
        if code:raise subprocess.CalledProcessError(code,binary)
        (out/'run.log').write_text('\n'.join(lines)+'\n')
        journal=(directory/'opaque.log').read_bytes()
        if journal!=journal_before:raise ValueError('Restart/retry duplicated peer receipt')
        kinds=[row[2] for row in peer_records(directory/'opaque.log')]
        if kinds!=[1,2]:raise ValueError('Expected exactly one opaque write and one barrier receipt')
        records,pending=timed_records(out/'actual.io')
        if pending is not None or len(records)!=2:raise ValueError('Actual outcome tape incomplete')
        if (out/'complete.snap').read_bytes()!=(out/'replay.snap').read_bytes():raise ValueError('Exact authoritative native suffix differs')
        for path,h in consumed.items():
            if sha(path)!=h:raise ValueError('Consumed native source changed during qualification')
        result.update(inputs=inputs,status='PASS',native_sha256=manifest['binary_sha256'],snapshot_identity=manifest['snapshot_identity'],checkpoint_container_version=2,fixture_sha256=sha(source),checker_sha256=sha(__file__),guest_image=entry['image'],guest_archive=guest['native_bundle'],peer_binaries=prepared['binaries'],measurement=measurement,peak_native_rss_kib=peak,peer_receipt_kinds=kinds,outcomes=records,exact_suffix=True,missing_tape_clock_advance=0,snapshot_bytes=(out/'pending.snap').stat().st_size,files={name:sha(out/name) for name in ('pending.snap','fork-pending.snap','complete.snap','replay.snap','rejected.snap','actual.io','run.log')},all_owned_processes_reaped=True)
    except BaseException as error:result['error']=str(error);raise
    finally:
        for process,stream in owned:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
            if stream:stream.close()
        result['host_seconds']=time.monotonic()-started;(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
