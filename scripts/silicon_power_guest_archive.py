#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Complete immutable genuine Power-v2 probe archive; host build orchestration."""
import argparse,hashlib,json,shutil
from pathlib import Path
import silicon_guest as guest
PROFILE='lemma-silicon-dev/0.4.0'
CONFIG='lemmasim-silicon-power-safety-probe'
SCHEMA='lemmasim-power-guest-archive/1'
SCOPE='unchanged genuinely compiled Power-v2 probe; fully validated consumed source archive; no fresh compilation'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def prepared(path,workload,name):
    supplied=Path(path)
    if supplied.is_symlink():raise ValueError('Power archive root is a symlink')
    path=supplied.resolve()
    if name!=PROFILE or workload!='power':raise ValueError('Power archive admits only profile0.4 Power probe')
    if path.is_symlink() or not path.is_dir():raise ValueError('Power archive is missing')
    m=json.loads((path/'archive.json').read_text())
    if set(m)!={'schema','profile','configuration','optimization','scope','files'} or (m['schema'],m['profile'],m['configuration'],m['optimization'],m['scope'])!=(SCHEMA,PROFILE,CONFIG,'O2',SCOPE):raise ValueError('Unsupported Power guest archive')
    if not isinstance(m['files'],dict) or not m['files']:raise ValueError('Empty Power guest archive')
    actual={str(f.relative_to(path)) for f in path.rglob('*') if f.is_file() and f!=path/'archive.json'}
    if len(actual)>8192 or sum(f.stat().st_size for f in path.rglob('*') if f.is_file())>256*1024*1024:raise ValueError('Power archive exceeds bounded inventory/capacity')
    if actual!=set(m['files']) or any(f.is_symlink() for f in path.rglob('*')):raise ValueError('Power archive inventory differs')
    for n,h in m['files'].items():
        f=(path/n).resolve()
        if not f.is_relative_to(path) or not f.is_file() or sha(f)!=h:raise ValueError('Power archive file changed: '+n)
    d=path/'guest';guest.verify_guest_build(d,CONFIG,'O2',source_root=path/'source')
    return {'workloads':{'power':{k:guest.identified(d/p) for k,p in [('image','image.elf'),('build','build.json'),('provenance','provenance.json'),('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin')]}}}
def build(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    guest.verify_guest_build(source,CONFIG,'O2')
    p=json.loads((source/'provenance.json').read_text());output.mkdir()
    for n,h in p['source_inputs'].items():
        f=guest.ROOT/n;dest=output/'source'/n
        if sha(f)!=h:raise ValueError('Current source changed before archive: '+n)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    shutil.copytree(source,output/'guest')
    guest.verify_guest_build(output/'guest',CONFIG,'O2',source_root=output/'source')
    m={'schema':SCHEMA,'profile':PROFILE,'configuration':CONFIG,'optimization':'O2','scope':SCOPE,
       'files':{str(f.relative_to(output)):sha(f) for f in sorted(output.rglob('*')) if f.is_file()}}
    (output/'archive.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    prepared(output,'power',PROFILE)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--guest-build',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    if a.guest_build:build(a.guest_build,a.output)
    else:prepared(a.output,'power',PROFILE)
    print('PASS: fully validated immutable genuine Power-v2 probe archive')
