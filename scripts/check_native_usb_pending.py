#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real audited guest USB6 raw Pending/queue/reset checkpoints and private suffixes.

This host property links the exact reusable Machine core. It never writes a
controller field or constructs a USB packet or guest document.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from check_native_power import ROOT, sha, run
from check_guest_usb_notebook import copy_opaque_peer
from lemmasim_usb import validate as validate_host
from lemmasim_companion import validate as validate_companion
from silicon_guest import guest_source_archive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build','guest-build','guest-source-root','host-prepared','formatted-peer','formatted-outbox','work-dir'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused owned output under build required')
    out.mkdir(parents=True);start=time.monotonic();peer=None;peer_log=None
    result={'schema':'lemma-usb6-pending-evidence/1','status':'FAIL',
            'scope':'Actual audited RV64 guest-issued owned USB receive/submit; observational startup/reset/queue snapshots and isolated exact captured raw suffixes. No privately live peer continuation, USB PHY, cross-backend migration or QEMU cached-state claim.',
            'bounds':{'original_target_cycles':70000000,'fixture_host_seconds':1800},
            'external_process_policy':'restored forks have no USB process; strict implementation-bound checksum/prefix/horizon tape only'}
    try:
        host=validate_host(a.host_prepared);companion=a.host_prepared.resolve().parent/'companion/prepared.json';validate_companion(companion)
        guest=guest_source_archive(a.guest_build,a.guest_source_root,'lemmasim-silicon-usb-bulk-initialize','O2','lemma-silicon-dev/0.6.0')
        build=a.rtl_build.resolve();m=json.loads((build/'build.json').read_text())
        if m['profile']!='lemma-silicon-dev/0.6.0':raise ValueError('USB6 native profile differs')
        identities={Path(q):h for q,h in m['sha256'].items()};identities.update({ROOT/q:h for q,h in m['host_toolchain_inputs'].items()});identities.update({ROOT/q:h for q,h in m['host_runtime'].items()})
        identities[ROOT/'sim/rtl/host/main.cpp']=m['host_adapter']['sha256'];identities[build/'obj/lemma-rtl']=m['binary_sha256']
        for q,h in identities.items():
            if sha(q)!=h:raise ValueError('Changed native source/output: '+str(q))
        registry=json.loads((ROOT/'build/lemmasim/rtl-prepared-0.6.0.json').read_text());rom=registry['rom']
        if sha(rom['path'])!=rom['sha256']:raise ValueError('Original reset ROM identity differs')
        writer=copy_opaque_peer(a.formatted_peer.resolve(),out/'peer',a.formatted_outbox.resolve(),out/'outbox')
        if writer!=83:raise ValueError('Fixture writer namespace differs')
        socket=out/'peer.sock';peer_argv=[os.sys.executable,str(ROOT/'scripts/lemmasim'),'companion','serve','--prepared',str(companion),'--directory',str(out/'peer'),'--socket',str(socket)]
        peer_log=(out/'peer.log').open('xb');peer=subprocess.Popen(peer_argv,cwd=ROOT,stdout=peer_log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+15
        while not socket.exists():
            if peer.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Independent hosted Lean peer did not start')
            time.sleep(.01)
        version=subprocess.check_output(['verilator','-V'],text=True,timeout=10);roots=set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$',version,re.M))
        if len(roots)!=1:raise ValueError('Ambiguous Verilator root')
        prefix=Path(roots.pop());obj=build/'obj'
        names=['machine_runtime.o','backing_io.o','backing_io_posix.o','backing_peer.o','ble_peer_transport.o','usb_transport.o','verilated.o','verilated_save.o','verilated_threads.o','verilated_dpi.o','Vlemma_soc__ALL.a']
        source=ROOT/'tests/lemmasim/native_usb_pending.cpp';binary=out/'test'
        run(['c++','-O2','-std=c++17','-I',ROOT/'sim/rtl/host','-I',obj,'-I',prefix/'include','-I',prefix/'include/vltstd',source,*[obj/n for n in names],'-pthread','-o',binary],out/'compile.log',60)
        arguments=[binary,out,a.guest_build.resolve()/'image.elf',rom['path'],a.guest_build.resolve()/'platform.dtb',a.guest_build.resolve()/'descriptor.bin',host['binary']['path'],socket,out/'outbox',ROOT/'sim/companion/os_io.py']
        result.update(snapshot_identity=m['snapshot_identity'],native_sha256=m['binary_sha256'],guest_archive=guest,host_prepared={'path':str(a.host_prepared.resolve()),'sha256':sha(a.host_prepared)},rom=rom,fixture_sha256=sha(source),compiled_inputs={n:sha(obj/n) for n in names},peer_argv=peer_argv,fixture_argv=[str(v) for v in arguments])
        run(arguments,out/'run.log',1800)
        log=(out/'run.log').read_text()
        if not log.endswith('PASS real RV64 USB startup/reset and owned receive/submit raw Pending snapshots; private exact captured native suffixes\n'):raise ValueError('Missing actual native property result')
        rows=[json.loads(line) for line in log.splitlines() if line.startswith('{')]
        if {r['case'] for r in rows}!={'startup','reset','owned-receive','owned-submit','domain-reset'}:raise ValueError('Required actual boundary missing')
        for label in ('startup','reset','owned-receive','owned-submit','domain-reset'):
            for left,right in ((label+'.snap',label+'-restored.snap'),(label+'-final.snap',label+'-replay.snap')):
                if sha(out/left)!=sha(out/right):raise ValueError('Authoritative native suffix differs: '+label)
        for q,h in identities.items():
            if sha(q)!=h:raise ValueError('Native source changed during qualification: '+str(q))
        result.update(status='PASS',cases=rows,files={q.name:{'bytes':q.stat().st_size,'sha256':sha(q)} for q in sorted(out.iterdir()) if q.suffix in ('.snap','.tape','.log','.raw','.uart')})
    except BaseException as e:result['error']=repr(e)
    finally:
        if peer is not None and peer.poll() is None:
            os.killpg(peer.pid,signal.SIGTERM)
            try:peer.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(peer.pid,signal.SIGKILL);peer.wait(timeout=5)
        if peer_log is not None:peer_log.close()
        result['host_seconds']=time.monotonic()-start
        files=[q.stat() for q in out.rglob('*') if q.is_file() and not q.is_symlink()]
        result['owned_disk']={'apparent_bytes':sum(q.st_size for q in files),'allocated_bytes':sum(q.st_blocks*512 for q in files)}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
