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
SCHEMA_WITH_SOURCE_VERSIONS='lemmasim-native-bundle/2'
SCHEMA_WITH_SOFTWARE_DEPLOYMENT='lemmasim-native-bundle/3'
MANAGED_DEPLOYMENT='lemma-managed-notebook-deployment-v1'
MANAGED_CONFIGURATIONS={'notebook':'lemmasim-silicon-managed-notebook',
                      'initializer':'lemmasim-silicon-managed-initialize'}
SUMS_DEPLOYMENT='lemma-managed-sums-deployment-v1'
SUMS_CONFIGURATIONS={'notebook':'lemmasim-silicon-sums-notebook',
                     'initializer':'lemmasim-silicon-sums-initialize'}
SOFTWARE_DEPLOYMENTS={MANAGED_DEPLOYMENT:MANAGED_CONFIGURATIONS,
                      SUMS_DEPLOYMENT:SUMS_CONFIGURATIONS}
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


def origin_destination(manifest,path,digest):
    """Resolve one exact consumed version; never choose an arbitrary revision."""
    origins=manifest.get('origins')
    if not isinstance(origins,dict) or not origins:raise ValueError('Missing archived origin inventory')
    entry=origins.get(str(Path(path).resolve()))
    if manifest.get('schema') in (SCHEMA_WITH_SOURCE_VERSIONS,SCHEMA_WITH_SOFTWARE_DEPLOYMENT):
        if not isinstance(entry,dict):raise ValueError('Missing versioned archived origin: '+str(path))
        destination=entry.get(digest)
    elif manifest.get('schema')==SCHEMA:
        destination=entry
    else:raise ValueError('Unsupported archived origin schema')
    files=manifest.get('files')
    if not isinstance(files,dict) or not isinstance(destination,str) or destination not in files or files[destination].get('sha256')!=digest:
        raise ValueError('Archived consumed input differs: '+str(path))
    return destination


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


def current_rtl_backend(build,previous):
    """Replace only an exactly consumed, audited current canonical machine core.

    Guest artifacts are independently replaced/validated by the ordinary path.
    Every current input is retained by its actual version alongside old backend
    inputs; an existing output path or matching nominal profile is insufficient.
    """
    import hashlib
    import silicon_guest as guest
    from silicon_compute import source_manifest,snapshot_inputs,prepare
    build=Path(build).resolve();m=read_json(build/'build.json')
    dep=ROOT/'build/silicon/deps/cvw';prepare(dep)
    expected=source_manifest(dep,'lemma-silicon-dev/0.3.0')
    expected['configuration']='external-ram-128MiB'
    if any(m.get(k)!=v for k,v in expected.items()):
        raise ValueError('Replacement native RTL differs from exact consumed inputs')
    identity=hashlib.sha256(json.dumps(snapshot_inputs(expected,dep),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if m.get('snapshot_identity')!=identity:raise ValueError('Replacement RTL implementation identity differs')
    binary=build/'obj/lemma-rtl'
    if guest.sha(binary)!=m.get('binary_sha256'):raise ValueError('Replacement RTL binary changed')
    header=guest.validate(m.get('runtime_identity_header'))
    if header.read_text()!='#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+identity+'"\n':
        raise ValueError('Replacement RTL compiled identity header differs')
    consumed={**m['sha256'],
        **{str(ROOT/p):h for k in ('host_runtime','host_toolchain_inputs','binding_generator_inputs') for p,h in m[k].items()},
        **m['configuration_includes'],
        str(ROOT/m['build_driver']['path']):m['build_driver']['sha256'],
        str(ROOT/m['upstream_patch']['path']):m['upstream_patch']['sha256'],
        str(ROOT/m['host_adapter']['path']):m['host_adapter']['sha256'],
        str(Path(m['host_include_dir'])/'lemma_silicon_binding.h'):m['host_binding_sha256'],
        str(header):m['runtime_identity_header']['sha256']}
    for path,h in consumed.items():
        if guest.sha(path)!=h:raise ValueError('Replacement RTL input changed: '+path)
    result=copy.deepcopy(previous)
    result.update(binary=guest.identified(binary),rtl_build=guest.identified(build/'build.json'),rtl_sources=consumed)
    return result,consumed


def bundle(args):
    import silicon_guest as guest
    import lemmasim_fast as fast
    from build_kernel import source_inputs
    name=args.profile
    if name!='lemma-silicon-dev/0.3.0':raise ValueError('Native bundle v1 admits canonical0.3 only')
    base=getattr(args,'base_bundle',None)
    replacements=(getattr(args,'notebook_build',None),getattr(args,'initializer_build',None))
    if base is None and any(replacements) or base is not None and not all(replacements):
        raise ValueError('Archived backend replacement requires base bundle and both current audited guest builds')
    replacement_rtl=getattr(args,'rtl_build',None)
    if replacement_rtl is not None and base is None:
        raise ValueError('Replacement RTL requires an immutable base bundle and both audited guest builds')
    if base is None:
        rtl=guest.prepared('notebook',name)
        initializer=guest.prepared('initializer',name)
        if any(rtl[k]!=initializer[k] for k in ('binary','rom','rtl_build','rtl_sources')):
            raise ValueError('Native workloads have different RTL implementations')
        guest.reset_rom_audit(rtl)
        qemu=fast.prepared('notebook',name)
    else:
        base=Path(base).resolve()
        rtl=prepared(base,'rtl','notebook',name)
        qemu=prepared(base,'qemu','notebook',name)
        prepared(base,'rtl','initializer',name)
        prepared(base,'qemu','initializer',name)
    current_backend_inputs={}
    if replacement_rtl is not None:
        rtl,current_backend_inputs=current_rtl_backend(replacement_rtl,rtl)
    source_before=source_inputs(ROOT)
    archive_base=base
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':SCHEMA_WITH_SOURCE_VERSIONS,'profile':name,'boot':'ELF-preload development',
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
        prior=manifest['origins'].setdefault(str(path),{}).setdefault(h,name)
        if guest.sha(out/prior)!=h:raise ValueError('Conflicting bundle origin')
        return {'path':name,'sha256':h}
    def backend_source(path,h):
        if current_backend_inputs.get(str(Path(path).resolve()))==h:
            if guest.sha(path)!=h:raise ValueError('Replacement RTL source changed during pack: '+str(path))
            return Path(path)
        if archive_base is None:
            return Path(path)
        old=read_json(archive_base/'bundle.json');dest=origin_destination(old,path,h)
        return archive_base/dest
    def add_backend_source(path,h):
        item=add(backend_source(path,h),'backend-sources/'+h,h)
        manifest['origins'].setdefault(str(Path(path).resolve()),{}).setdefault(h,item['path'])
        return item
    if base is not None:
        manifest['base_bundle']={'sha256':guest.sha(base/'bundle.json'),
            'scope':('validated archived QEMU backend; exact current-source RTL backend; new genuine current-source guest compilation'
                     if replacement_rtl is not None else
                     'validated unchanged archived backends; new genuine current-source guest compilation')}
        for workload,build in zip(('notebook','initializer'),replacements):
            override=development_guest(rtl,workload,out,build,'developer')
            rtl['workloads'][workload]=override['workloads'][workload]
        qemu['workloads']=copy.deepcopy(rtl['workloads'])
    selected_configurations={w:read_json(Path(rtl['workloads'][w]['build']['path']))['configuration']
                             for w in ('notebook','initializer')}
    ordinary={w:guest.configurations(name)[w] for w in ('notebook','initializer')}
    deployment=next((name for name,configurations in SOFTWARE_DEPLOYMENTS.items()
                     if selected_configurations==configurations),None)
    if deployment is not None:
        manifest['schema']=SCHEMA_WITH_SOFTWARE_DEPLOYMENT
        manifest['software_deployment']={'contract_version':deployment,
                                         'configurations':dict(SOFTWARE_DEPLOYMENTS[deployment])}
    elif selected_configurations!=ordinary:
        raise ValueError('Native bundle requires one complete admitted software deployment')
    for path,h in source_before.items():add(ROOT/path,'source/'+path,h)
    for path,h in rtl['rtl_sources'].items():
        add_backend_source(path,h)
    for path,h in qemu['sources'].items():add_backend_source(str(ROOT/path),h)
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
        if item['sha256'] not in manifest['origins'].get(str(Path(item['path']).resolve()),{}):
            add_backend_source(item['path'],item['sha256'])
    manifest['backends']['rtl']=relocate(rtl,'rtl')
    manifest['backends']['qemu']=relocate(qemu,'qemu')
    for key,item in (('rtl',rtl['binary']),('qemu',qemu['qemu'])):
        manifest['host_dependencies'][key]=host_dependencies(item['path'])
    (out/'DEPENDENCIES.txt').write_text('Local prepared development artifacts. A compatible Linux x86-64 host, Python3, optional Tk/evdev and the exact external Nix loader/library files in bundle.json are required. No target host runtime is linked into RV64. Project-wide redistribution licensing remains unresolved; this package grants no redistribution license. CVW20f2af74: Apache-2.0 WITH SHL-2.1 and retained MIT notices. Verilator5.052: LGPL-3.0-only OR Artistic-2.0. QEMU11.1.1: GPL-2.0-or-later. Exact source/tool identities are archived. ELF preload is development boot. Physical conformance UNVERIFIED.\n')
    manifest['files']={str(p.relative_to(out)):{'sha256':guest.sha(p),'bytes':p.stat().st_size,
                        'executable':os.access(p,os.X_OK)} for p in sorted(out.rglob('*')) if p.is_file()}
    if source_inputs(ROOT)!=source_before:raise ValueError('Guest inputs changed during pack')
    for path,h in current_backend_inputs.items():
        if guest.sha(path)!=h:raise ValueError('Replacement RTL input changed during pack: '+path)
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
    if m.get('schema') not in (SCHEMA,SCHEMA_WITH_SOURCE_VERSIONS,SCHEMA_WITH_SOFTWARE_DEPLOYMENT) or m.get('profile')!='lemma-silicon-dev/0.3.0' or name not in (None,m['profile']):
        raise ValueError('Unsupported/mismatched native bundle')
    if backend not in ('rtl','qemu') or workload not in ('notebook','initializer'):raise ValueError('Unsupported bundled execution')
    selected_configurations=bundle_configurations(m)
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
        origin_destination(m,path,h)
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
    if set(data['workloads'])!={'notebook','initializer'}:raise ValueError('Incomplete bundled software deployment')
    for w,e in data['workloads'].items():
        if w not in ('notebook','initializer'):raise ValueError('Unknown bundled workload')
        data['workloads'][w]={k:absolute(item) for k,item in e.items()}
        base=Path(data['workloads'][w]['build']['path']).parent
        build=read_json(base/'build.json')
        guest.verify_guest_build(base,selected_configurations[w],build['optimization'],source_root=directory/'source')
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
    data['native_bundle']={'schema':m['schema'],'manifest_sha256':guest.sha(directory/'bundle.json'),
                           'source_commit':m['source_commit'],'scope':'validated archived inputs; not current compilation'}
    if m['schema']==SCHEMA_WITH_SOFTWARE_DEPLOYMENT:
        data['native_bundle']['software_deployment']=copy.deepcopy(m['software_deployment'])
    return data


def bundle_configurations(manifest):
    """An immutable package selects both guest roles under one closed contract."""
    import silicon_guest as guest
    if manifest.get('profile')!='lemma-silicon-dev/0.3.0':
        raise ValueError('Software deployment requires canonical hardware0.3')
    if manifest.get('schema')==SCHEMA_WITH_SOFTWARE_DEPLOYMENT:
        selected=manifest.get('software_deployment')
        if not isinstance(selected,dict) or set(selected)!={'contract_version','configurations'}:
            raise ValueError('Managed bundle software deployment differs')
        version=selected.get('contract_version')
        if not isinstance(version,str) or version not in SOFTWARE_DEPLOYMENTS:
            raise ValueError('Managed bundle software deployment differs')
        configurations=SOFTWARE_DEPLOYMENTS[version]
        if selected['configurations']!=configurations:
            raise ValueError('Managed bundle software deployment differs')
        return dict(configurations)
    if manifest.get('schema') not in (SCHEMA,SCHEMA_WITH_SOURCE_VERSIONS) or 'software_deployment' in manifest:
        raise ValueError('Historical bundle acquired software deployment authority')
    return {w:guest.configurations(manifest['profile'])[w] for w in ('notebook','initializer')}


ARITHMETIC_LAB_CONFIGURATIONS=frozenset({
    'lemmasim-silicon-sums-arithmetic-oom-development',
    'lemmasim-silicon-power-arithmetic-oom-development',
    'lemmasim-silicon-power-arithmetic-fault-development',
    'lemmasim-silicon-power-arithmetic-stall-development',
})


def development_configuration(profile,workload,configuration,mode):
    import silicon_guest as guest
    selected=guest.configurations(profile)
    if workload not in selected:raise ValueError('Workload is not admitted by the selected hardware profile')
    ordinary=selected[workload]
    if configuration==ordinary:return ordinary
    if (profile=='lemma-silicon-dev/0.3.0' and
            any(configuration==configurations.get(workload) for configurations in SOFTWARE_DEPLOYMENTS.values())
            and mode in ('student','developer','laboratory')):
        return configuration
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
