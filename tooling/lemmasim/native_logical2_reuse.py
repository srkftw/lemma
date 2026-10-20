#!/usr/bin/env python3
"""Independently bind retained native objects, reproduce their link, rebind logical2.

Retained objects are observed now, never retroactively called fresh. A cold build
uses qemu_uart.nix logicalSoftTlb=true and does not require this optional cache.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--reference',type=Path,required=True)
p.add_argument('--inputs',type=Path,required=True)
a=p.parse_args()
root=Path.cwd();out=root/'logical2-reuse-current';out.mkdir()
start=time.monotonic();deadline=start+360
report={'schema':'lemma-native-logical2-retained-build/1','status':'FAIL',
        'scope':__doc__,'commands':[], 'bounds':{'whole_seconds':360,'tree_rss_bytes':1<<30,
        'minimum_available_bytes':2<<30,'minimum_free_bytes':2<<30},'peak_tree_rss_bytes':0}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
    if not v:raise ValueError(m)
def available():
    return next(int(r.split()[1])*1024 for r in Path('/proc/meminfo').read_text().splitlines() if r.startswith('MemAvailable:'))
def run(argv,phase,env=None):
    require(time.monotonic()<deadline and available()>=2<<30 and shutil.disk_usage(root).free>=2<<30,'Original time/resource floor')
    t=time.monotonic();child=None;row={'argv':list(map(str,argv)),'phase':phase}
    try:
        with (out/(phase+'.log')).open('wb') as log:
            child=subprocess.Popen(row['argv'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            while child.poll() is None:
                rss=0
                for stat in Path('/proc').glob('[0-9]*/stat'):
                    try:
                        f=stat.read_text().rsplit(')',1)[1].split()
                        if int(f[2])==child.pid:rss+=int(f[21])*os.sysconf('SC_PAGE_SIZE')
                    except (OSError,ValueError,IndexError):pass
                report['peak_tree_rss_bytes']=max(report['peak_tree_rss_bytes'],rss)
                require(time.monotonic()<deadline and rss<=1<<30 and available()>=2<<30,'Original owned compile/link bound')
                time.sleep(.1)
            require(child.returncode==0,'Actual command failed: '+phase)
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        row.update(seconds=time.monotonic()-t,exit_code=child.returncode if child else None);report['commands'].append(row)
    return (out/(phase+'.log')).read_text()
def objects():return {str(p):sha(p) for p in sorted((root/'build').rglob('*')) if p.is_file() and p.suffix in ('.o','.a')}
try:
    require(sha(root/'accel/tcg/lemma_softtlb_qemu.inc.c') in ('aebe0aace1b1a463e2837f01b6edbf91b96dbf695b2cf34fe5d3aba688a28eb5','4701a3ae4bd50beb1bcc91e90a31f048cd0af3b8b2a0a520a2b020162740a9fa'),'Expected qualified schema2 predecessor helper')
    # Reconstruct the maintained cold-patch result from the independently pinned
    # normal configured source. Version5 is temporarily changed to counter3 only
    # to reproduce the cold recipe order (counter -> MM -> logical -> rawUART).
    names=['hw/riscv/lemma_qemu.c','hw/riscv/lemma_multimodal.c','hw/riscv/lemma_multimodal.h',
      'hw/riscv/lemma_multimodal_qemu.inc.c','accel/tcg/cputlb.c','system/cpu-timers.c','cpu-common.c',
      'migration/savevm.c','migration/ram.c','accel/tcg/icount-common.c','include/exec/cputlb.h',
      'include/hw/core/cpu.h','include/exec/memattrs.h','include/exec/tlb-common.h','qapi/migration.json']
    require(sha(a.reference)=='28cd7f5894ac1e0ece8c2c1a2884ee8c7411d27119f300a93b87403909ed47da','Pinned canonical normal configured archive differs')
    report['reference']={'path':str(a.reference),'sha256':sha(a.reference)}
    with tempfile.TemporaryDirectory(dir=root,prefix='logical2-reproduction-') as temp:
        stage=Path(temp)
        with tarfile.open(a.reference) as archive:
            for m in archive:
                name=m.name.removeprefix('./')
                if name in names:
                    dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.extractfile(m).read())
        require(all((stage/n).is_file() for n in names),'Complete normal source references required')
        q=stage/'hw/riscv/lemma_qemu.c';q.write_text(q.read_text().replace('.version_id=5,.minimum_version_id=5,','.version_id=3,.minimum_version_id=3,'))
        tool=a.inputs/'tooling/lemmasim';host=a.inputs/'sim/host'
        run(['python3',tool/'patch_multimodal_checkpoint.py',stage,'--qemu-helper',host/'lemma_multimodal_checkpoint.inc.c','--model-helper',host/'lemma_multimodal_checkpoint_valid.inc.c'],'source-mm')
        run(['python3',tool/'patch_soft_tlb2.py',stage,'--helper',host/'lemma_softtlb2_qemu.inc.c'],'source-logical2')
        run(['python3',tool/'patch_logical2_lifecycle.py',stage],'source-lifecycle')
        q.write_text(q.read_text().replace('.version_id=3,.minimum_version_id=3,','.version_id=5,.minimum_version_id=5,'))
        for n in names:require(sha(stage/n)==sha(root/n),'Retained source does not equal maintained cold recipe: '+n)
    # Verify every other maintained source consumed by this profile; the normal
    # generated profile/header, upstream patch inputs, flags and dependency bytes
    # remain in the complete configured source archive and baseline link closure.
    mapping={n:'hw/riscv/'+n for n in ['lemma_model.c','lemma_model.h','lemma_device_abi.h','lemma_power_abi.h','lemma_fast_block.c','lemma_uart_ingress.h','lemma_uart_qemu.inc.c']}
    mapping.update({'lemma_durable.c':'block/lemma-durable.c'})
    for n in ['backing_io.h','backing_io.cpp','backing_io_posix.h','backing_io_posix.cpp']:mapping[n]='hw/riscv/host/'+n
    for n,dest in mapping.items():require(sha(host/n)==sha(root/dest),'Other maintained controller source differs: '+n)
    for n in ['backing_peer.h','backing_peer.cpp','backing_c.h','backing_c.cpp']:require(sha(a.inputs/'sim/companion'/n)==sha(root/'hw/riscv/companion'/n),'Companion backing source differs: '+n)
    bound=objects();report['retained_object_and_archive_count']=len(bound)
    require(len(bound)==1457,'Exact qualified1457-object/archive retained closure missing')
    (out/'retained-objects.json').write_text(json.dumps(bound,sort_keys=True,indent=2)+'\n')
    report['retained_inventory_sha256']=sha(out/'retained-objects.json')
    binary=root/'build/qemu-system-riscv64';baseline=sha(binary);report['baseline_binary_sha256']=baseline
    require(baseline in ('8a1858f57253c634890b776d91a0c9b39ac9a89cbb8065fecaf124921690c5e2','dd2ba2f41bdcde80a925fbc0054bb46ad5a15773b51f682afbc063364e4aa98f'),'Exact qualified predecessor ELF identity differs')
    shutil.copyfile(binary,out/'baseline-original.qemu')
    binary.unlink()
    dry=run(['ninja','-C','build','-n','qemu-system-riscv64'],'baseline-plan')
    report['baseline_plan']=dry[-12000:]
    # Ninja dry-run pessimistically assumes this PHONY generator changes its
    # restat output. Only the two exact version-header consumers may appear;
    # real execution below must prove NO compilation and unchanged objects.
    version_consumers={'libqmp.a.p/monitor_qmp-cmds-control.c.o','libsystem.a.p/system_vl.c.o'}
    planned=set(re.findall(r'Compiling C object (\S+)',dry))
    require('Linking target qemu-system-riscv64' in dry and planned<=version_consumers,'Unexpected baseline invalidation')
    # Nix's wrapper injects the current output's RUNPATH even though the
    # command/objects are unchanged. Reproduce the original LINK environment,
    # then use the current output environment for the changed action. This is
    # an actual byte-identical baseline, never an ELF normalization.
    dynamic=subprocess.run(['readelf','-d',str(out/'baseline-original.qemu')],capture_output=True,text=True,check=True).stdout
    original_runpath=re.findall(r'Library runpath: \[([^]]+)\]',dynamic)
    require(len(original_runpath)==1,'Exact original ELF RUNPATH required')
    original_prefix=original_runpath[0].split(':')[0]
    require(original_prefix in ('/nix/store/532kp9djjmg5kzlbbz3qrjg60zm2ir27-lemmasim-qemu-private-logical-wakes-v2-11.1.1/lib','/nix/store/1nqjws03faak74p8f8y781s779rfklq1-lemmasim-qemu-raw-uart-logical-v2-retained-11.1.1/lib'),'Qualified baseline output prefix differs')
    environment=os.environ.copy();current_prefix=environment['out']+'/lib'
    needle='-rpath '+current_prefix
    require(environment.get('NIX_LDFLAGS','').count(needle)==1,'Exact Nix wrapper output RUNPATH injection required')
    environment['NIX_LDFLAGS']=environment['NIX_LDFLAGS'].replace(needle,'-rpath '+original_prefix)
    report['baseline_link_environment']={'current_output_RUNPATH':current_prefix,'reproduced_original_RUNPATH':original_prefix,'other_flags_unchanged':True}
    baseline_log=run(['ninja','-C','build','-j2','qemu-system-riscv64'],'baseline-link',env=environment)
    report['baseline_actual_compiles']=re.findall(r'Compiling C object (\S+)',baseline_log)
    require(not report['baseline_actual_compiles'],'Baseline actually recompiled retained objects')
    report['baseline_actual_binary_sha256']=sha(binary)
    report['baseline_object_differences']=[n for n,v in objects().items() if bound.get(n)!=v]
    report['link_environment']={n:os.environ.get(n) for n in ['NIX_LDFLAGS','NIX_CFLAGS_COMPILE','NIX_HARDENING_ENABLE','out']}
    if sha(binary)!=baseline:
        for name,path in [('original',out/'baseline-original.qemu'),('actual',binary)]:
            report['baseline_'+name+'_dynamic']=subprocess.run(['readelf','-d',str(path)],capture_output=True,text=True,check=True).stdout
        old=(out/'baseline-original.qemu').read_bytes();new=binary.read_bytes();diff=[i for i,(l,r) in enumerate(zip(old,new)) if l!=r]
        report['baseline_difference']={'old_bytes':len(old),'new_bytes':len(new),'unequal_common_bytes':len(diff),'first':diff[:32],'last':diff[-32:]}
    require(sha(binary)==baseline and objects()==bound,'Baseline real link must reproduce original binary byte-for-byte without object changes')
    report['baseline_reproduced']=True
    helper=root/'accel/tcg/lemma_softtlb_qemu.inc.c';new_helper=(host/'lemma_softtlb2_qemu.inc.c').read_bytes()
    changed_helper=helper.read_bytes()!=new_helper
    if changed_helper:helper.write_bytes(new_helper)
    # A reused current helper needs no compiler. The new output environment
    # still requires a real link; force only that target after the baseline.
    binary.unlink()
    dry=run(['ninja','-C','build','-n','qemu-system-riscv64'],'changed-plan')
    report['changed_plan']=dry[-12000:]
    planned=set(re.findall(r'Compiling C object (\S+)',dry))
    expected_object='libsystem.a.p/accel_tcg_cputlb.c.o'
    require((expected_object in planned)==changed_helper and planned<=version_consumers|{expected_object} and 'Linking target qemu-system-riscv64' in dry,'Unexpected changed dependency invalidation')
    actual=run(['ninja','-C','build','-j2','qemu-system-riscv64'],'changed-object-link')
    report['changed_actual_compiles']=re.findall(r'Compiling C object (\S+)',actual)
    require(set(report['changed_actual_compiles'])==({expected_object} if changed_helper else set()),'Changed action compiled unexpected objects')
    after=objects();changed=[n for n in bound if after.get(n)!=bound[n]]
    require(changed==([str(root/'build/libsystem.a.p/accel_tcg_cputlb.c.o')] if changed_helper else []),'Unexpected retained object change')
    report.update(status='PASS_MAINTAINED_LOGICAL2_OBJECT_AND_REAL_LINK',changed_objects=changed,
                  fresh_object_count=len(changed),reused_object_and_archive_count=len(bound)-len(changed),binary_sha256=sha(binary))
except BaseException as error:
    report['error']=repr(error);raise
finally:
    report['seconds']=time.monotonic()-start
    (out/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['schema','status','seconds','peak_tree_rss_bytes']},sort_keys=True),flush=True)
