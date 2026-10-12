#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Immutable native development package; exact archived inputs, no target policy.

Packing requires ordinary current-tree preparation. Launch validates the entire
package and archived compiler closure. It does not relabel old builds as fresh.
Host dynamic libraries remain pinned external dependencies, not bundled target
objects. This is a local development package, not a redistribution license.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='lemmasim-native-bundle/1'
MAX_FILES=2048
MAX_BYTES=1024*1024*1024


def read_json(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Duplicate bundle metadata key')
            result[k]=v
        return result
    if path.stat().st_size>16*1024*1024:raise ValueError('Oversized bundle metadata')
    return json.loads(path.read_text(),object_pairs_hook=unique)


def inventory(directory,manifest):
    from silicon_guest import sha
    files=manifest.get('files')
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES:raise ValueError('Invalid bundle file inventory')
    total=0
    for name,item in files.items():
        if not isinstance(name,str) or not name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Invalid bundle file path')
        if not isinstance(item,dict) or set(item)!={'sha256','bytes','executable'}:
            raise ValueError('Malformed bundle file identity')
        h=item['sha256'];size=item['bytes'];execute=item['executable']
        if not isinstance(h,str) or not re.fullmatch('[a-f0-9]{64}',h) or type(size) is not int or size<1 or type(execute) is not bool:
            raise ValueError('Malformed bundle checksum/length/mode')
        total+=size
        if total>MAX_BYTES:raise ValueError('Bundle exceeds byte bound')
        path=directory/name
        if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file() or path.stat().st_size!=size or sha(path)!=h:
            raise ValueError('Bundle artifact missing, symlinked or changed: '+name)
        if execute and not os.access(path,os.X_OK):raise ValueError('Bundle executable mode missing')
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()}
    if actual!=set(files)|{'bundle.json'}:raise ValueError('Bundle has an unlisted/missing file')


def host_dependencies(binary):
    """Record actual loader/library files, including ELF interpreter and RPATH.

    Only runs on a build already verified by the ordinary preparation path.
    ldd output is bounded and missing/unresolved dependencies fail closed.
    """
    from silicon_guest import sha
    result=subprocess.run(['ldd',str(binary)],text=True,capture_output=True,check=True,timeout=30)
    if len(result.stdout)>65536 or 'not found' in result.stdout:raise ValueError('Unresolved native host libraries')
    files=set()
    for line in result.stdout.splitlines():
        matches=re.findall(r'(/[A-Za-z0-9_+./-]+)',line)
        files.update(matches)
    if not files:raise ValueError('Native host dependency inventory is empty')
    return {p:sha(p) for p in sorted(files)}


def bundle(args):
    import silicon_guest as guest
    import lemmasim_fast as fast
    from build_kernel import source_inputs
    name=args.profile
    if name!='lemma-silicon-dev/0.3.0':raise ValueError('Native bundle v1 admits canonical0.3 only')
    # Validate current consumed inputs before copying any executable.
    rtl=guest.prepared('notebook',name)
    initializer=guest.prepared('initializer',name)
    if any(rtl[k]!=initializer[k] for k in ('binary','rom','rtl_build','rtl_sources')):
        raise ValueError('Native workloads have different RTL implementations')
    guest.reset_rom_audit(rtl)
    qemu=fast.prepared('notebook',name)
    source_before=source_inputs(ROOT)
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':SCHEMA,'profile':name,'boot':'ELF-preload development',
              'compiler':'genuine pinned native Lean/LLVM; archived consumed inputs, not fresh compilation',
              'physical_conformance':'UNVERIFIED','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'sources':source_before,'origins':{},'host_dependencies':{},'backends':{}}
    def add(path,name,expected=None,executable=False):
        path=Path(path).resolve();h=guest.sha(path)
        if expected is not None and h!=expected:raise ValueError('Consumed artifact changed during pack: '+str(path))
        dest=out/name
        if dest.exists():
            if guest.sha(dest)!=h:raise ValueError('Conflicting bundle destination')
        else:
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
            dest.chmod(0o755 if executable else 0o644)
        prior=manifest['origins'].setdefault(str(path),name)
        if guest.sha(out/prior)!=h:raise ValueError('Conflicting bundle origin')
        return {'path':name,'sha256':h}
    for path,h in source_before.items():add(ROOT/path,'source/'+path,h)
    for path,h in rtl['rtl_sources'].items():
        p=Path(path).resolve()
        dest='source/'+str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else 'dependencies/'+h
        add(p,dest,h)
    for path,h in qemu['sources'].items():add(ROOT/path,'source/'+path,h)
    entries={}
    for workload in ('notebook','initializer'):
        entry=rtl['workloads'][workload];base=Path(entry['build']['path']).parent
        provenance=read_json(base/'provenance.json')
        for p,h in provenance['artifacts'].items():add(base/p,'workloads/'+workload+'/'+p,h)
        entries[workload]={}
        for key,item in entry.items():
            filename=Path(item['path']).name
            entries[workload][key]=add(item['path'],'workloads/'+workload+'/'+filename,item['sha256'])
        if workload=='notebook':
            capacity=read_json(Path(entry['capacity']['path']))
            for p,h in capacity['artifacts'].items():add(base/p,'workloads/'+workload+'/'+p,h)
    def relocate(data,backend):
        result=copy.deepcopy(data);result['workloads']=copy.deepcopy(entries)
        for key in (('binary','rom','rom_audit','rtl_build') if backend=='rtl' else ('qemu','derivation')):
            item=result[key];result[key]=add(item['path'],'runtime/'+backend+'/'+Path(item['path']).name,item['sha256'],key in ('binary','qemu'))
        return result
    rom_audit=read_json(Path(rtl['rom_audit']['path']))
    for key in ('source','assembly','object','elf','binary'):
        item=rom_audit[key]
        if str(Path(item['path']).resolve()) not in manifest['origins']:
            add(item['path'],'runtime/rom/'+Path(item['path']).name,item['sha256'])
    manifest['backends']['rtl']=relocate(rtl,'rtl')
    manifest['backends']['qemu']=relocate(qemu,'qemu')
    for key,item in (('rtl',rtl['binary']),('qemu',qemu['qemu'])):
        manifest['host_dependencies'][key]=host_dependencies(item['path'])
    (out/'DEPENDENCIES.txt').write_text('Local prepared development artifacts. A compatible Linux x86-64 host, Python3, optional Tk/evdev and the exact external Nix loader/library files in bundle.json are required. No target host runtime is linked into RV64. Project-wide redistribution licensing remains unresolved; this package grants no redistribution license. CVW20f2af74: Apache-2.0 WITH SHL-2.1 and retained MIT notices. Verilator5.052: LGPL-3.0-only OR Artistic-2.0. QEMU11.1.1: GPL-2.0-or-later. Exact source/tool identities are archived. ELF preload is development boot. Physical conformance UNVERIFIED.\n')
    manifest['files']={str(p.relative_to(out)):{'sha256':guest.sha(p),'bytes':p.stat().st_size,
                        'executable':os.access(p,os.X_OK)} for p in sorted(out.rglob('*')) if p.is_file()}
    if source_inputs(ROOT)!=source_before:raise ValueError('Guest inputs changed during pack')
    (out/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Read the packed bytes using the same fail-closed validator used at launch.
    for backend in ('rtl','qemu'):
        for w in entries:prepared(out,backend,w,name)
    print(out/'bundle.json')


def prepared(directory,backend,workload,name=None):
    import silicon_guest as guest
    from build_kernel import source_inputs
    from silicon_profile import profile_path
    directory=Path(directory).resolve();m=read_json(directory/'bundle.json')
    if m.get('schema')!=SCHEMA or m.get('profile')!='lemma-silicon-dev/0.3.0' or name not in (None,m['profile']):
        raise ValueError('Unsupported/mismatched native bundle')
    if backend not in ('rtl','qemu') or workload not in ('notebook','initializer'):raise ValueError('Unsupported bundled execution')
    inventory(directory,m)
    if m.get('sources')!=source_inputs(directory/'source'):raise ValueError('Archived compiler/source closure differs')
    data=copy.deepcopy(m['backends'][backend])
    def absolute(item):
        if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise ValueError('Malformed prepared bundle identity')
        if item['path'] not in m['files'] or m['files'][item['path']]['sha256']!=item['sha256']:
            raise ValueError('Prepared metadata contradicts inventory')
        return {'path':str(directory/item['path']),'sha256':item['sha256']}
    origins=m.get('origins')
    if not isinstance(origins,dict) or not origins:raise ValueError('Missing archived origin inventory')
    def archived(path,h):
        dest=origins.get(str(Path(path).resolve()))
        if dest not in m['files'] or m['files'][dest]['sha256']!=h:raise ValueError('Archived consumed input differs: '+path)
    if data.get('profile')!=m['profile'] or data.get('profile_sha256')!=guest.sha(profile_path(m['profile'])):
        raise ValueError('Bundled versioned profile changed')
    archived(str(profile_path(m['profile'])),data['profile_sha256'])
    for path,h in (data['rtl_sources'] if backend=='rtl' else {str(ROOT/k):v for k,v in data['sources'].items()}).items():archived(path,h)
    dependencies=m['host_dependencies'][backend]
    if not isinstance(dependencies,dict) or not dependencies:raise ValueError('Missing host runtime closure')
    for path,h in dependencies.items():
        if not path.startswith('/nix/store/') or not Path(path).is_file() or guest.sha(path)!=h:
            raise ValueError('Exact external native host library missing/changed: '+path)
    for key in (('binary','rom','rom_audit','rtl_build') if backend=='rtl' else ('qemu','derivation')):data[key]=absolute(data[key])
    for w,e in data['workloads'].items():
        if w not in ('notebook','initializer'):raise ValueError('Unknown bundled workload')
        data['workloads'][w]={k:absolute(item) for k,item in e.items()}
        base=Path(data['workloads'][w]['build']['path']).parent
        build=read_json(base/'build.json')
        guest.verify_guest_build(base,guest.configurations(m['profile'])[w],build['optimization'],source_root=directory/'source')
        if w=='notebook':
            capacity=read_json(Path(data['workloads'][w]['capacity']['path']))
            if capacity.get('status')!='PASS' or capacity.get('configuration')!=build['configuration']:raise ValueError('Bundled capacity audit differs')
            for p,h in capacity['artifacts'].items():
                if guest.sha(base/p)!=h:raise ValueError('Bundled capacity input differs')
    if backend=='rtl':
        audit=read_json(Path(data['rom_audit']['path']))
        words=[0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067]
        import struct
        if audit.get('status')!='PASS' or audit.get('instruction_words')!=words or Path(data['rom']['path']).read_bytes()!=struct.pack('<6I',*words):raise ValueError('Bundled reset ROM audit differs')
        for key in ('source','assembly','object','elf','binary'):archived(audit[key]['path'],audit[key]['sha256'])
        if audit['binary']['sha256']!=data['rom']['sha256']:raise ValueError('Bundled ROM provenance differs')
        runtime=read_json(Path(data['rtl_build']['path']))
        if runtime.get('binary_sha256')!=data['binary']['sha256'] or runtime.get('profile')!=data['profile']:
            raise ValueError('Bundled native implementation differs')
    else:
        from lemmasim_fast import CPU
        if data.get('schema')!='lemmasim-fast-prepared/1' or data.get('cpu')!=CPU or data.get('icount_shift')!=3:
            raise ValueError('Bundled fast execution contract differs')
    data['native_bundle']={'schema':SCHEMA,'manifest_sha256':guest.sha(directory/'bundle.json'),
                           'source_commit':m['source_commit'],'scope':'validated archived inputs; not current compilation'}
    return data


ARITHMETIC_LAB_CONFIGURATIONS=frozenset({
    'lemmasim-silicon-power-arithmetic-oom-development',
    'lemmasim-silicon-power-arithmetic-fault-development',
    'lemmasim-silicon-power-arithmetic-stall-development',
})


def development_configuration(profile,workload,configuration,mode):
    import silicon_guest as guest
    ordinary=guest.configurations(profile)[workload]
    if configuration==ordinary:return ordinary
    if profile=='lemma-silicon-dev/0.3.0' and workload=='notebook' and mode=='laboratory' and configuration in ARITHMETIC_LAB_CONFIGURATIONS:
        return configuration
    raise ValueError('Development guest configuration is not admitted for this profile/workload/mode')


def development_guest(data,workload,directory,guest_build,mode=None):
    """A new current-source guest on an unchanged archived hardware binding.

    This explicit development option does not modify the immutable package.
    Its current-source strict audit is required even if bytes match an older
    image. A new capacity receipt is generated before a notebook can launch.
    """
    import silicon_guest as guest
    base=Path(guest_build).resolve();build=read_json(base/'build.json')
    configuration=development_configuration(data['profile'],workload,build['configuration'],mode)
    guest.verify_guest_build(base,configuration,build['optimization'])
    result=copy.deepcopy(data)
    entry={key:guest.identified(base/name) for key,name in (
        ('image','image.elf'),('build','build.json'),('provenance','provenance.json'),
        ('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin'))}
    if workload=='notebook':
        capacity=directory/'guest-override-capacity.json'
        guest.run_command(['nix','develop','--no-write-lock-file','--command','python3',
            'scripts/audit_lemmasim_capacity.py','--build',base,'--output',capacity],
            timeout=120,log=directory/'guest-override-capacity.log')
        receipt=read_json(capacity)
        if receipt.get('status')!='PASS' or receipt.get('configuration')!=build['configuration']:
            raise ValueError('Development guest capacity audit failed')
        for name,h in receipt['artifacts'].items():
            if guest.sha(base/name)!=h:raise ValueError('Development guest capacity input changed')
        entry['capacity']=guest.identified(capacity)
    guest.verify_guest_build(base,configuration,build['optimization'])
    result['workloads'][workload]=entry
    result['guest_override']={'scope':'new strict current-source audited development guest on unchanged archived backend',
                              'configuration':configuration,'mode':mode,
                              'build':entry['build'],'provenance':entry['provenance']}
    return result
