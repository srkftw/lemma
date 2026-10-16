#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Immutable native development package; exact archived inputs, no target policy.

Packing requires ordinary current-tree preparation or an explicitly selected,
complete original source archive for an audited guest pair. Launch validates the entire
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
SCHEMA_USB_NEXT='lemmasim-native-bundle/4'
USB_NEXT_PROFILE='lemma-silicon-dev/0.8.0'
USB_NEXT_DEPLOYMENT='lemma-managed-sums-bulk-usb-next-deployment-v1'
USB_NEXT_CONFIGURATIONS={'usb-next-bulk-notebook':'lemmasim-silicon-usb-next-bulk-notebook',
                         'usb-next-bulk-initializer':'lemmasim-silicon-usb-next-bulk-initialize'}
SCHEMA_USB_WIRE='lemmasim-native-bundle/5'
USB_WIRE_PROFILE='lemma-silicon-dev/0.11.0'
USB_WIRE_DEPLOYMENT='lemma-managed-sums-bulk-usb-wire-deployment-v1'
USB_WIRE_CONFIGURATIONS={'usb-wire-bulk-notebook':'lemmasim-silicon-usb-wire-bulk-notebook',
                         'usb-wire-bulk-initializer':'lemmasim-silicon-usb-wire-bulk-initialize'}
SCHEMA_USB_CLOCKED='lemmasim-native-bundle/6'
USB_CLOCKED_PROFILE='lemma-silicon-dev/0.13.0'
USB_CLOCKED_DEPLOYMENT='lemma-managed-sums-bulk-usb-clocked-deployment-v1'
USB_CLOCKED_CONFIGURATIONS={'usb-clocked-bulk-notebook':'lemmasim-silicon-usb-clocked-bulk-notebook',
                            'usb-clocked-bulk-initializer':'lemmasim-silicon-usb-clocked-bulk-initialize'}
USB_NATIVE_DEPLOYMENTS={USB_NEXT_PROFILE:(SCHEMA_USB_NEXT,USB_NEXT_DEPLOYMENT,USB_NEXT_CONFIGURATIONS),
                        USB_WIRE_PROFILE:(SCHEMA_USB_WIRE,USB_WIRE_DEPLOYMENT,USB_WIRE_CONFIGURATIONS),
                        USB_CLOCKED_PROFILE:(SCHEMA_USB_CLOCKED,USB_CLOCKED_DEPLOYMENT,USB_CLOCKED_CONFIGURATIONS)}
SCHEMA_USB_RECOVERY='lemmasim-native-bundle/7'
USB_RECOVERY_CONFIGURATIONS={'usb-clocked-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-retry-bulk-notebook',
                             'usb-clocked-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-retry-bulk-initialize'}
USB_RECOVERY_SOFTWARE={'contract_version':'lemma-usb-clocked-recovery-deployment-v1',
    'silicon_profile':USB_CLOCKED_PROFILE,
    'user_profiles':{'store':'core0-user-v0.2','notebook':'core0-user-v0.2','arithmetic':'core0-user-v0.3'}}
USB_RECOVERY_CONTROL={'usb_recovery':'lemma-usb-live-recovery/1'}
SCHEMA_USB_CLOSURE_RECOVERY='lemmasim-native-bundle/8'
USB_CLOSURE_RECOVERY_CONFIGURATIONS={'usb-clocked-closure-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook',
                                     'usb-clocked-closure-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize'}
from usb_closure_recovery_deployment import SOFTWARE_DEPLOYMENT as _USB_CLOSURE_RECOVERY_SOFTWARE
USB_CLOSURE_RECOVERY_SOFTWARE=copy.deepcopy(_USB_CLOSURE_RECOVERY_SOFTWARE)
SCHEMA_USB_PACKAGE_RECOVERY='lemmasim-native-bundle/9'
USB_PACKAGE_RECOVERY_CONFIGURATIONS={'usb-clocked-package-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-package-retry-bulk-notebook',
                                     'usb-clocked-package-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-package-retry-bulk-initialize'}
from package_companion_deployment import SOFTWARE_DEPLOYMENT as _USB_PACKAGE_RECOVERY_SOFTWARE
USB_PACKAGE_RECOVERY_SOFTWARE=copy.deepcopy(_USB_PACKAGE_RECOVERY_SOFTWARE)
SCHEMA_USB_PACKAGE_ENTRY2='lemmasim-native-bundle/10'
from package_entry2_deployment import SOFTWARE_DEPLOYMENT as _USB_PACKAGE_ENTRY2_SOFTWARE
USB_PACKAGE_ENTRY2_SOFTWARE=copy.deepcopy(_USB_PACKAGE_ENTRY2_SOFTWARE)
USB_PACKAGE_ENTRY2_CONFIGURATIONS={
    'usb-clocked-package-entry2-bulk-notebook':'lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook',
    'usb-clocked-package-entry2-bulk-initializer':'lemmasim-silicon-usb-clocked-package-entry2-bulk-initialize'}
SCHEMA_USB_COMPANION_READER='lemmasim-native-bundle/11'
from companion_reader_deployment import SOFTWARE_DEPLOYMENT as _USB_COMPANION_READER_SOFTWARE
USB_COMPANION_READER_SOFTWARE=copy.deepcopy(_USB_COMPANION_READER_SOFTWARE)
USB_COMPANION_READER_CONFIGURATIONS={
    'usb-clocked-reader-entry2-bulk-notebook':'lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook',
    'usb-clocked-reader-entry2-bulk-initializer':'lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize'}
USB_RECOVERY_SCHEMAS=(SCHEMA_USB_RECOVERY,SCHEMA_USB_CLOSURE_RECOVERY,SCHEMA_USB_PACKAGE_RECOVERY,SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER)

def usb_recovery_software(schema):
    if schema==SCHEMA_USB_COMPANION_READER:return copy.deepcopy(USB_COMPANION_READER_SOFTWARE)
    if schema==SCHEMA_USB_PACKAGE_ENTRY2:return copy.deepcopy(USB_PACKAGE_ENTRY2_SOFTWARE)
    if schema==SCHEMA_USB_PACKAGE_RECOVERY:return copy.deepcopy(USB_PACKAGE_RECOVERY_SOFTWARE)
    if schema==SCHEMA_USB_RECOVERY:return copy.deepcopy(USB_RECOVERY_SOFTWARE)
    if schema==SCHEMA_USB_CLOSURE_RECOVERY:return copy.deepcopy(USB_CLOSURE_RECOVERY_SOFTWARE)
    raise ValueError('Unknown exact USB recovery software schema')


def usb_native_deployment(profile, *, schema=None, recovery=False, closure_recovery=False, package_recovery=False, package_entry2=False, companion_reader=False):
    if companion_reader or schema==SCHEMA_USB_COMPANION_READER:
        if recovery or closure_recovery or package_recovery or package_entry2 or profile!=USB_CLOCKED_PROFILE or schema not in (None,SCHEMA_USB_COMPANION_READER):
            raise ValueError('Reader19 requires exclusive Clocked13 schema11')
        return SCHEMA_USB_COMPANION_READER,USB_COMPANION_READER_SOFTWARE['contract_version'],USB_COMPANION_READER_CONFIGURATIONS
    if package_entry2 or schema==SCHEMA_USB_PACKAGE_ENTRY2:
        if recovery or closure_recovery or package_recovery or profile!=USB_CLOCKED_PROFILE or schema not in (None,SCHEMA_USB_PACKAGE_ENTRY2):
            raise ValueError("Package Entry2 requires exclusive Clocked13 schema10")
        return SCHEMA_USB_PACKAGE_ENTRY2,USB_PACKAGE_ENTRY2_SOFTWARE["contract_version"],USB_PACKAGE_ENTRY2_CONFIGURATIONS
    if package_recovery or schema==SCHEMA_USB_PACKAGE_RECOVERY:
        if recovery or closure_recovery or profile!=USB_CLOCKED_PROFILE or schema not in (None,SCHEMA_USB_PACKAGE_RECOVERY):
            raise ValueError('Package recovery requires exclusive Clocked13 schema9')
        return SCHEMA_USB_PACKAGE_RECOVERY,USB_PACKAGE_RECOVERY_SOFTWARE['contract_version'],USB_PACKAGE_RECOVERY_CONFIGURATIONS
    if recovery and (closure_recovery or schema==SCHEMA_USB_CLOSURE_RECOVERY):
        raise ValueError('Historical and Closure recovery deployments are mutually exclusive')
    if closure_recovery or schema==SCHEMA_USB_CLOSURE_RECOVERY:
        if profile!=USB_CLOCKED_PROFILE or schema not in (None,SCHEMA_USB_CLOSURE_RECOVERY):
            raise ValueError('Closure recovery native package requires Clocked13 and schema8')
        return SCHEMA_USB_CLOSURE_RECOVERY,USB_CLOSURE_RECOVERY_SOFTWARE['contract_version'],USB_CLOSURE_RECOVERY_CONFIGURATIONS
    if recovery or schema==SCHEMA_USB_RECOVERY:
        if profile!=USB_CLOCKED_PROFILE or schema not in (None,SCHEMA_USB_RECOVERY):
            raise ValueError('Recovery native package requires Clocked13 and schema7')
        return SCHEMA_USB_RECOVERY,USB_RECOVERY_SOFTWARE['contract_version'],USB_RECOVERY_CONFIGURATIONS
    selected=USB_NATIVE_DEPLOYMENTS.get(profile)
    if selected is None or schema not in (None,selected[0]):
        raise ValueError('USB package profile/schema association differs')
    return selected


def usb_software_deployment(schema, version, configurations):
    base=usb_recovery_software(schema) if schema in USB_RECOVERY_SCHEMAS else {'contract_version':version}
    return {**base,'configurations':dict(configurations)}


def require_recovery_runtime(runtime):
    controls=runtime.get('runtime_control_contracts')
    if not isinstance(controls,dict) or controls.get('usb_recovery')!=USB_RECOVERY_CONTROL['usb_recovery']:
        raise ValueError('Recovery package requires its exact native live recovery control contract')
MANAGED_DEPLOYMENT='lemma-managed-notebook-deployment-v1'
MANAGED_CONFIGURATIONS={'notebook':'lemmasim-silicon-managed-notebook',
                      'initializer':'lemmasim-silicon-managed-initialize'}
SUMS_DEPLOYMENT='lemma-managed-sums-deployment-v1'
SUMS_CONFIGURATIONS={'notebook':'lemmasim-silicon-sums-notebook',
                     'initializer':'lemmasim-silicon-sums-initialize'}
BULK_DEPLOYMENT='lemma-managed-sums-bulk-deployment-v1'
BULK_CONFIGURATIONS={'notebook':'lemmasim-silicon-bulk-notebook',
                     'initializer':'lemmasim-silicon-bulk-initialize'}
BYTES_DEPLOYMENT="lemma-managed-bytes-bulk-deployment-v1"
BYTES_CONFIGURATIONS={"notebook":"lemmasim-silicon-bytes-bulk-notebook",
                      "initializer":"lemmasim-silicon-bytes-bulk-initialize"}
ARRAY_DEPLOYMENT="lemma-managed-array-bulk-deployment-v1"
ARRAY_CONFIGURATIONS={"notebook":"lemmasim-silicon-array-bulk-notebook", "initializer":"lemmasim-silicon-array-bulk-initialize"}
STRING_DEPLOYMENT="lemma-managed-string-bulk-deployment-v1"
STRING_CONFIGURATIONS={"notebook":"lemmasim-silicon-string-bulk-notebook",
                       "initializer":"lemmasim-silicon-string-bulk-initialize"}
COURSE_DEPLOYMENT="lemma-course-array-bulk-deployment-v1"
COURSE_CONFIGURATIONS={"notebook":"lemmasim-silicon-course-bulk-notebook",
                       "initializer":"lemmasim-silicon-course-bulk-initialize"}
COURSE_AWAIT_DEPLOYMENT="lemma-course-mounted-await-bulk-deployment-v1"
COURSE_AWAIT_CONFIGURATIONS={"notebook":"lemmasim-silicon-course-await-bulk-notebook",
                             "initializer":"lemmasim-silicon-course-await-bulk-initialize"}
CLOSURE_DEPLOYMENT="lemma-managed-closure-bulk-deployment-v1"
CLOSURE_CONFIGURATIONS={"notebook":"lemmasim-silicon-closure-bulk-notebook",
                        "initializer":"lemmasim-silicon-closure-bulk-initialize"}
CLOSURE_ENTRY2_DEPLOYMENT="lemma-managed-closure-entry2-bulk-deployment-v1"
CLOSURE_ENTRY2_CONFIGURATIONS={"notebook":"lemmasim-silicon-closure-entry2-bulk-notebook",
                               "initializer":"lemmasim-silicon-closure-entry2-bulk-initialize"}
PACKAGE_CLOSURE_DEPLOYMENT="lemma-package-closure-entry2-bulk-deployment-v1"
PACKAGE_CLOSURE_CONFIGURATIONS={"notebook":"lemmasim-silicon-package-closure-entry2-bulk-notebook",
                               "initializer":"lemmasim-silicon-package-closure-entry2-bulk-initialize"}
READER_DEPLOYMENT="lemma-package-reader-bulk-deployment-v1"
READER_CONFIGURATIONS={"notebook":"lemmasim-silicon-package-reader-bulk-notebook",
                      "initializer":"lemmasim-silicon-package-reader-bulk-initialize"}
CHOOSER_READER_DEPLOYMENT='lemma-package-reader-chooser-bulk-deployment-v1'
CHOOSER_READER_CONFIGURATIONS={"notebook":"lemmasim-silicon-package-chooser-bulk-notebook",
                             "initializer":"lemmasim-silicon-package-chooser-bulk-initialize"}
SOFTWARE_DEPLOYMENTS={CHOOSER_READER_DEPLOYMENT:CHOOSER_READER_CONFIGURATIONS,READER_DEPLOYMENT:READER_CONFIGURATIONS,PACKAGE_CLOSURE_DEPLOYMENT:PACKAGE_CLOSURE_CONFIGURATIONS,COURSE_AWAIT_DEPLOYMENT:COURSE_AWAIT_CONFIGURATIONS,CLOSURE_ENTRY2_DEPLOYMENT:CLOSURE_ENTRY2_CONFIGURATIONS,CLOSURE_DEPLOYMENT:CLOSURE_CONFIGURATIONS,COURSE_DEPLOYMENT:COURSE_CONFIGURATIONS,STRING_DEPLOYMENT:STRING_CONFIGURATIONS,ARRAY_DEPLOYMENT:ARRAY_CONFIGURATIONS,BYTES_DEPLOYMENT:BYTES_CONFIGURATIONS,MANAGED_DEPLOYMENT:MANAGED_CONFIGURATIONS,
                      SUMS_DEPLOYMENT:SUMS_CONFIGURATIONS,BULK_DEPLOYMENT:BULK_CONFIGURATIONS}
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
    if manifest.get('schema') in (SCHEMA_WITH_SOURCE_VERSIONS,SCHEMA_WITH_SOFTWARE_DEPLOYMENT,SCHEMA_USB_NEXT,SCHEMA_USB_WIRE,SCHEMA_USB_CLOCKED,SCHEMA_USB_RECOVERY,SCHEMA_USB_CLOSURE_RECOVERY,SCHEMA_USB_PACKAGE_RECOVERY,SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
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
    if getattr(args,'refresh_fast',False):
        conflicts=('notebook_build','initializer_build','rtl_build','rtl_source_root',
                   'guest_source_root','initializer_guest_source_root',
                   'usb_recovery_deployment','usb_closure_recovery_deployment','usb_package_recovery_deployment','usb_package_entry2_deployment','usb_companion_reader_deployment')
        if name!='lemma-silicon-dev/0.3.0' or getattr(args,'base_bundle',None) is None or \
           not getattr(args,'expected_fast_sha256',None) or any(getattr(args,k,None) for k in conflicts):
            raise ValueError('Fast refresh requires canonical base, exact runtime identity and no guest/RTL replacement')
        from refresh_native_fast import refresh
        result=refresh(args.base_bundle,args.output_dir,args.expected_fast_sha256)
        print(result)
        return result
    if getattr(args,'expected_fast_sha256',None):
        raise ValueError('Expected fast identity requires --refresh-fast')
    if getattr(args,'usb_companion_reader_deployment',False) and (name!=USB_CLOCKED_PROFILE or any(getattr(args,k,False) for k in ('usb_recovery_deployment','usb_closure_recovery_deployment','usb_package_recovery_deployment','usb_package_entry2_deployment'))):
        raise ValueError('Reader19 requires exclusive Clocked13 schema11')
    if getattr(args,'usb_recovery_deployment',False) and name!=USB_CLOCKED_PROFILE:
        raise ValueError('Recovery native package requires Clocked13 and schema7')
    if getattr(args,'usb_closure_recovery_deployment',False) and name!=USB_CLOCKED_PROFILE:
        raise ValueError('Closure recovery native package requires Clocked13 and schema8')
    if getattr(args,'usb_recovery_deployment',False) and getattr(args,'usb_closure_recovery_deployment',False):
        raise ValueError('Historical and Closure recovery deployments are mutually exclusive')
    if getattr(args,'usb_package_entry2_deployment',False) and (name!=USB_CLOCKED_PROFILE or any(getattr(args,k,False) for k in ('usb_recovery_deployment','usb_closure_recovery_deployment','usb_package_recovery_deployment'))):
        raise ValueError('Package Entry2 requires exclusive Clocked13 schema10')
    if getattr(args,'usb_package_recovery_deployment',False) and (name!=USB_CLOCKED_PROFILE or getattr(args,'usb_recovery_deployment',False) or getattr(args,'usb_closure_recovery_deployment',False)):
        raise ValueError('Package recovery requires exclusive Clocked13 schema9')
    if name in USB_NATIVE_DEPLOYMENTS:
        return bundle_usb_next(args, name)
    if getattr(args,'initializer_guest_source_root',None) is not None:
        raise ValueError('Separate initializer source archives support only USB native schemas')
    if getattr(args,'rtl_source_root',None) is not None:
        raise ValueError('Explicit native source archives are admitted only by USB native schemas')
    if name!='lemma-silicon-dev/0.3.0':raise ValueError('Native bundle v1 admits canonical0.3 only')
    base=getattr(args,'base_bundle',None)
    replacements=(getattr(args,'notebook_build',None),getattr(args,'initializer_build',None))
    if base is None and any(replacements) or base is not None and not all(replacements):
        raise ValueError('Archived backend replacement requires base bundle and both current audited guest builds')
    guest_root=getattr(args,'guest_source_root',None)
    if guest_root is not None and (base is None or not all(replacements)):
        raise ValueError('Canonical source archive requires an immutable base bundle and both audited guest builds')
    source_origin=Path(guest_root).resolve() if guest_root is not None else ROOT
    archive_receipts={}
    if guest_root is not None:
        for role,build in zip(('notebook','initializer'),replacements):
            archive_receipts[role]=canonical_guest_archive(build,source_origin,name,role)
        if archive_receipts['notebook']['inventory']!=archive_receipts['initializer']['inventory']:
            raise ValueError('Canonical guest roles have different consumed source inventories')
        configurations={role:receipt['configuration'] for role,receipt in archive_receipts.items()}
        ordinary={role:guest.configurations(name)[role] for role in configurations}
        if configurations!=ordinary and configurations not in SOFTWARE_DEPLOYMENTS.values():
            raise ValueError('Original canonical archive requires one complete admitted deployment pair')
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
    source_before=source_inputs(source_origin)
    archive_base=base
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':SCHEMA_WITH_SOURCE_VERSIONS,'profile':name,'boot':'ELF-preload development',
              'compiler':'genuine pinned native Lean/LLVM; archived consumed inputs, not fresh compilation',
              'physical_conformance':'UNVERIFIED','source_commit':(archive_receipts['notebook']['source_commit'] if archive_receipts else subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),
              'sources':source_before,'origins':{},'host_dependencies':{},'backends':{}}
    if archive_receipts:manifest['guest_source_archive']=archive_receipts
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
            'scope':('validated backends and original fully audited guest source/tool/object archives'
                     if archive_receipts else
                     'validated archived QEMU backend; exact current-source RTL backend; new genuine current-source guest compilation'
                     if replacement_rtl is not None else
                     'validated unchanged archived backends; new genuine current-source guest compilation')}
        for workload,build in zip(('notebook','initializer'),replacements):
            override=development_guest(rtl,workload,out,build,'developer',source_root=source_origin if archive_receipts else None)
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
    for path,h in source_before.items():add(source_origin/path,'source/'+path,h)
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
    if source_inputs(source_origin)!=source_before:raise ValueError('Guest inputs changed during pack')
    for role,build in zip(('notebook','initializer'),replacements):
        if archive_receipts and canonical_guest_archive(build,source_origin,name,role)!=archive_receipts[role]:
            raise ValueError('Original consumed guest archive changed during pack')
    for path,h in current_backend_inputs.items():
        if guest.sha(path)!=h:raise ValueError('Replacement RTL input changed during pack: '+path)
    (out/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
    # Read the packed bytes using the same fail-closed validator used at launch.
    for backend in ('rtl','qemu'):
        for w in entries:prepared(out,backend,w,name)
    print(out/'bundle.json')


def usb_archive_roots(args):
    """Select explicit per-role archives without introducing a ROOT fallback."""
    notebook = getattr(args, 'guest_source_root', None)
    initializer = getattr(args, 'initializer_guest_source_root', None)
    if initializer is not None and notebook is None:
        raise ValueError('Separate initializer archive requires explicit notebook guest archive')
    return notebook, initializer if initializer is not None else notebook


def bundle_usb_next(args, selected_profile=USB_NEXT_PROFILE):
    """Pack one independently validated USB8 RTL/guest pair; no fast backend.

    Source archives are explicit caller inputs and use the ordinary complete
    validators. The resulting package retains those exact bytes and original
    source versions, so launch does not consult a mutable prepared registry.
    """
    import silicon_guest as guest
    from build_kernel import source_inputs
    if any(getattr(args, key, None) is not None for key in
           ('base_bundle', 'notebook_build', 'initializer_build')):
        raise ValueError('USB8 package requires its prepared exact pair; canonical backend replacement is separate')
    native_root = getattr(args, 'rtl_source_root', None)
    guest_root, initializer_root = usb_archive_roots(args)
    if selected_profile not in USB_NATIVE_DEPLOYMENTS:raise ValueError('Unsupported USB native package profile')
    selected_schema, selected_deployment, selected_configurations=usb_native_deployment(
        selected_profile,recovery=getattr(args,'usb_recovery_deployment',False),
        closure_recovery=getattr(args,'usb_closure_recovery_deployment',False),
        package_recovery=getattr(args,'usb_package_recovery_deployment',False),
        package_entry2=getattr(args,'usb_package_entry2_deployment',False),
        companion_reader=getattr(args,'usb_companion_reader_deployment',False))
    roles = tuple(selected_configurations)
    data = guest.prepared(roles[0], selected_profile, rtl_source_root=native_root,
                          guest_source_root=guest_root)
    other = guest.prepared(roles[1], selected_profile, rtl_source_root=native_root,
                           guest_source_root=initializer_root)
    for key in ('binary', 'rom', 'rom_audit', 'rtl_build', 'rtl_sources'):
        if data[key] != other[key]:
            raise ValueError('USB8 package roles have different machine implementations')
    selected_build = getattr(args, 'rtl_build', None)
    if selected_build is not None and Path(data['rtl_build']['path']).parent != selected_build.resolve():
        raise ValueError('USB8 package selected RTL implementation differs')
    if selected_schema in USB_RECOVERY_SCHEMAS:
        require_recovery_runtime(read_json(Path(data['rtl_build']['path'])))
    guest.reset_rom_audit(data)
    origin = Path(guest_root).resolve() if guest_root is not None else ROOT
    initializer_origin = Path(initializer_root).resolve() if initializer_root is not None else ROOT
    sources = source_inputs(origin)
    if source_inputs(initializer_origin) != sources:
        raise ValueError('USB guest archives have different complete consumed source inventories')
    for role, configuration in selected_configurations.items():
        build = Path(data['workloads'][role]['build']['path']).parent
        provenance = read_json(build / 'provenance.json')
        if provenance['source_inputs'] != sources:
            raise ValueError('USB8 guest roles differ from the complete selected source tree')
        guest.verify_guest_build(build, configuration, read_json(build / 'build.json')['optimization'],
                                 source_root=origin)
        if selected_schema in USB_RECOVERY_SCHEMAS and read_json(build/'audit.json').get('software_deployment')!=usb_recovery_software(selected_schema):
            raise ValueError('Recovery guest software identity differs from its exact deployment')
    from product_native import archived_original_root
    native_origin=archived_original_root(read_json(Path(data['rtl_build']['path'])))
    if selected_schema not in (SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER) and native_origin!=ROOT:
        raise ValueError('Relocated native archive packaging requires explicit schema10')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': selected_schema, 'profile': selected_profile,
                'original_repository_root': str(ROOT),
                'boot': 'ELF-preload development', 'physical_conformance': 'UNVERIFIED',
                'compiler': 'genuine pinned Lean/LLVM; complete original consumed source versions',
                'source_commit': read_json(Path(data['workloads'][roles[0]]['provenance']['path']))['source_commit'],
                'sources': sources, 'origins': {}, 'host_dependencies': {}, 'backends': {},
                'software_deployment': usb_software_deployment(selected_schema,selected_deployment,selected_configurations)}

    if selected_schema in (SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
        manifest['original_native_repository_root']=str(native_origin)

    def add(source, destination, digest, *, executable=False, original=None):
        source = Path(source)
        if source.is_symlink():
            raise ValueError('Symlink in USB8 package input: ' + str(source))
        source = source.resolve()
        if guest.sha(source) != digest:
            raise ValueError('Consumed USB8 package input changed: ' + str(source))
        target = out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if guest.sha(target) != digest:
                raise ValueError('Conflicting USB8 package destination')
        else:
            shutil.copyfile(source, target)
            target.chmod(0o755 if executable else 0o644)
        manifest['origins'].setdefault(str(Path(original or source).resolve()), {})[digest] = destination
        return {'path': destination, 'sha256': digest}

    for path, digest in sources.items():
        add(origin / path, 'source/' + path, digest, original=ROOT / path)
    for path, digest in data['rtl_sources'].items():
        source = Path(native_root) / guest._native_relative(path,native_origin) if native_root is not None else Path(path)
        add(source, 'backend-sources/' + digest, digest, original=path)
    entries = {}
    for role in roles:
        entry = data['workloads'][role]
        build = Path(entry['build']['path']).parent
        for path, digest in read_json(build / 'provenance.json')['artifacts'].items():
            add(build / path, 'workloads/' + role + '/' + path, digest)
        expected = {'image', 'build', 'provenance', 'audit', 'dtb', 'descriptor'}
        if role == roles[0]:
            expected.add('capacity')
        if set(entry) - {'guest_source_archive'} != expected:
            raise ValueError('USB8 workload artifact inventory differs')
        entries[role] = {key: add(item['path'], 'workloads/' + role + '/' + Path(item['path']).name,
                                  item['sha256']) for key, item in entry.items() if key != 'guest_source_archive'}
        if 'capacity' in expected:
            for path, digest in read_json(Path(entry['capacity']['path']))['artifacts'].items():
                add(build / path, 'workloads/' + role + '/' + path, digest)
    runtime = copy.deepcopy(data)
    runtime.pop('rtl_source_archive', None)
    runtime.pop('binding_profile', None)
    runtime['workloads'] = entries
    for key in ('binary', 'rom', 'rom_audit', 'rtl_build'):
        item = data[key]
        runtime[key] = add(item['path'], 'runtime/rtl/' + Path(item['path']).name,
                           item['sha256'], executable=key == 'binary')
    audit = read_json(Path(data['rom_audit']['path']))
    for key in ('source', 'assembly', 'object', 'elf', 'binary'):
        item = audit[key]
        if item['sha256'] in manifest['origins'].get(str(Path(item['path']).resolve()), {}):
            continue
        source = origin / 'Lemma/Platform/Silicon/BootROM.lean' if key == 'source' else Path(item['path'])
        add(source, 'backend-sources/' + item['sha256'], item['sha256'], original=item['path'])
    manifest['backends']['rtl'] = runtime
    manifest['host_dependencies']['rtl'] = host_dependencies(data['binary']['path'])
    (out / 'DEPENDENCIES.txt').write_text(
        'USB8 local native development package. Exact Linux x86-64 Nix loader/library paths in bundle.json are required. '
        'The independently persistent hosted Lean USB packet peer is launched separately. No QEMU USB backend is supplied. '
        'Host runtimes do not enter the RV64 guest. CVW20f2af74: Apache-2.0 WITH SHL-2.1 and retained MIT notices. '
        'Verilator5.052: LGPL-3.0-only OR Artistic-2.0. Redistribution licensing remains unresolved; no license is granted by this package. '
        'ELF preload is development boot; physical conformance UNVERIFIED.\n')
    manifest['files'] = {str(path.relative_to(out)): {'sha256': guest.sha(path), 'bytes': path.stat().st_size,
                        'executable': os.access(path, os.X_OK)} for path in sorted(out.rglob('*')) if path.is_file()}
    if source_inputs(origin) != sources or source_inputs(initializer_origin) != sources:
        raise ValueError('USB8 source inputs changed during pack')
    (out / 'bundle.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for role in roles:
        prepared(out, 'rtl', role, selected_profile)
    print(out / 'bundle.json')


def validate_usb_runtime(directory, manifest, data, runtime):
    """Reconstruct the entire consumed native closure and implementation ID."""
    import hashlib
    import silicon_guest as guest
    origin = Path(manifest.get('original_native_repository_root' if manifest.get('schema') in (SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER) else 'original_repository_root', ''))
    if manifest.get('schema') in (SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
        from product_native import archived_original_root
        if origin!=archived_original_root(runtime):
            raise ValueError('Schema10 native original prefix differs from its complete manifest')
    if not origin.is_absolute() or '..' in origin.parts:
        raise ValueError('USB8 original source-root authority missing')
    expected = {}

    def add(path, digest):
        path = Path(path)
        path = path if path.is_absolute() else origin / path
        if str(path) in expected and expected[str(path)] != digest:
            raise ValueError('Conflicting USB8 native input digest')
        expected[str(path)] = digest

    for key in ('sha256', 'configuration_includes', 'host_runtime',
                'host_toolchain_inputs', 'binding_generator_inputs'):
        if not isinstance(runtime.get(key), dict) or not runtime[key]:
            raise ValueError('USB8 native manifest missing consumed inventory')
        for path, digest in runtime[key].items():
            add(path, digest)
    if (not isinstance(runtime.get('sources'), list) or
            len(set(runtime['sources'])) != len(runtime['sources']) or
            set(runtime['sources']) != set(runtime['sha256'])):
        raise ValueError('USB8 native manifest source inventory differs')
    for key in ('host_adapter', 'build_driver', 'upstream_patch', 'runtime_identity_header'):
        item = runtime.get(key)
        if not isinstance(item, dict) or not {'path', 'sha256'} <= item.keys():
            raise ValueError('USB8 native input identity missing')
        add(item['path'], item['sha256'])
    add(Path(runtime['host_include_dir']) / 'lemma_silicon_binding.h', runtime['host_binding_sha256'])
    if manifest.get('schema') in (SCHEMA_USB_CLOCKED,SCHEMA_USB_RECOVERY,SCHEMA_USB_CLOSURE_RECOVERY,SCHEMA_USB_PACKAGE_RECOVERY,SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
        if runtime.get('profile')!=USB_CLOCKED_PROFILE:
            raise ValueError('Clocked native manifest selected profile differs')
        add(origin/guest.USB_CLOCKED_PROFILE_FILE,runtime['profile_sha256'])
    dependency = str(origin / 'tooling/silicon/dependencies.json')
    if dependency not in data['rtl_sources']:
        raise ValueError('USB8 native dependency input missing')
    add(dependency, data['rtl_sources'][dependency])
    if expected != data['rtl_sources']:
        raise ValueError('USB8 consumed native closure differs from its original manifest')
    identity = {key: value for key, value in runtime.items() if key not in
                ('sources', 'include_dirs', 'host_include_dir', 'runtime_identity_header',
                 'build_argv', 'build_jobs', 'binary_sha256', 'snapshot_identity')}
    identity['identity_schema'] = 'lemmasim-rtl-implementation/2'
    core = origin / 'build/silicon/deps/cvw'
    generated = Path(runtime['host_include_dir']) / 'lemma_silicon_binding.sv'

    def logical(path):
        path = Path(path)
        if path == generated:
            return 'generated/lemma_silicon_binding.sv'
        for base, prefix in ((core, 'core/'), (core.parent / 'cvw-patched', 'patched-core/'),
                             (origin, 'repository/')):
            try:
                return prefix + path.relative_to(base).as_posix()
            except ValueError:
                pass
        raise ValueError('USB8 native input has no declared logical origin')

    for key in ('sha256', 'configuration_includes'):
        identity[key] = {logical(path): digest for path, digest in runtime[key].items()}
        if len(identity[key]) != len(runtime[key]):
            raise ValueError('USB8 native input logical origins collide')
    actual = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if actual != runtime.get('snapshot_identity'):
        raise ValueError('USB8 native implementation identity differs')
    item = runtime['runtime_identity_header']
    header = directory / origin_destination(manifest, item['path'], item['sha256'])
    if header.read_text() != '#pragma once\n#define LEMMA_RUNTIME_IDENTITY "' + actual + '"\n':
        raise ValueError('USB8 compiled runtime identity header differs')
    pinned = read_json(directory / origin_destination(manifest, dependency, expected[dependency]))
    if (pinned.get('core', {}).get('repository') != runtime.get('core_repository') or
            pinned.get('core', {}).get('revision') != runtime.get('core_revision')):
        raise ValueError('USB8 native core dependency differs')


def prepared_usb_next(directory, manifest, backend, workload, name):
    import silicon_guest as guest
    from build_kernel import source_inputs
    from silicon_profile import profile_path
    selected_profile=manifest.get('profile')
    if selected_profile not in USB_NATIVE_DEPLOYMENTS:raise ValueError('Unsupported USB native package profile')
    selected_schema, selected_deployment, selected_configurations=usb_native_deployment(
        selected_profile,schema=manifest.get('schema'))
    if manifest.get('schema')!=selected_schema:raise ValueError('USB package profile/schema association differs')
    if (manifest.get('profile') != selected_profile or name not in (None, selected_profile) or
            backend != 'rtl' or workload not in selected_configurations):
        raise ValueError('USB8 native package requires its exact RTL profile/workload')
    if (set(manifest.get('backends', {})) != {'rtl'} or
            set(manifest.get('host_dependencies', {})) != {'rtl'} or
            manifest.get('software_deployment') != usb_software_deployment(
                selected_schema,selected_deployment,selected_configurations)):
        raise ValueError('USB8 native deployment/implementation authority differs')
    inventory(directory, manifest)
    if manifest.get('sources') != source_inputs(directory / 'source'):
        raise ValueError('USB8 archived compiler/source closure differs')
    data = copy.deepcopy(manifest['backends']['rtl'])

    def absolute(item):
        if (not isinstance(item, dict) or set(item) != {'path', 'sha256'} or
                item['path'] not in manifest['files'] or
                manifest['files'][item['path']]['sha256'] != item['sha256']):
            raise ValueError('USB8 prepared identity contradicts inventory')
        return {'path': str(directory / item['path']), 'sha256': item['sha256']}

    selected_profile_path=(Path(manifest['original_repository_root'])/guest.USB_CLOCKED_PROFILE_FILE
                           if selected_profile==USB_CLOCKED_PROFILE else profile_path(selected_profile))
    selected_definition=directory/origin_destination(manifest,selected_profile_path,data['profile_sha256'])
    if (data.get('schema_version') != 1 or data.get('profile') != selected_profile or
            (selected_profile!=USB_CLOCKED_PROFILE and data.get('profile_sha256') != guest.sha(profile_path(selected_profile))) or
            set(data.get('workloads', {})) != set(selected_configurations) or
            'rtl_source_archive' in data):
        raise ValueError('USB8 prepared machine authority differs')
    if selected_profile==USB_CLOCKED_PROFILE:
        definition=read_json(selected_definition)
        if definition.get('profile')!=selected_profile or definition.get('schema_version')!=1:
            raise ValueError('Clocked packaged profile namespace differs')
    for path, digest in data['rtl_sources'].items():
        origin_destination(manifest, path, digest)
    dependencies = manifest['host_dependencies']['rtl']
    if not isinstance(dependencies, dict) or not dependencies:
        raise ValueError('USB8 native host runtime closure missing')
    for path, digest in dependencies.items():
        if not path.startswith('/nix/store/') or not Path(path).is_file() or guest.sha(path) != digest:
            raise ValueError('USB8 exact native host library missing/changed')
    for key in ('binary', 'rom', 'rom_audit', 'rtl_build'):
        data[key] = absolute(data[key])
    for role, entry in data['workloads'].items():
        data['workloads'][role] = {key: absolute(item) for key, item in entry.items()}
        base = Path(data['workloads'][role]['build']['path']).parent
        build = read_json(base / 'build.json')
        guest.verify_guest_build(base, selected_configurations[role], build['optimization'],
                                 source_root=directory / 'source')
        if selected_schema in USB_RECOVERY_SCHEMAS and read_json(base/'audit.json').get('software_deployment')!=usb_recovery_software(selected_schema):
            raise ValueError('Recovery guest software identity differs from its exact deployment')
        if role in ('usb-next-bulk-notebook','usb-wire-bulk-notebook','usb-clocked-bulk-notebook','usb-clocked-retry-bulk-notebook','usb-clocked-closure-retry-bulk-notebook'):
            capacity = read_json(Path(data['workloads'][role]['capacity']['path']))
            if capacity.get('status') != 'PASS' or capacity.get('configuration') != selected_configurations[role]:
                raise ValueError('USB8 notebook capacity authority differs')
            for path, digest in capacity['artifacts'].items():
                if guest.sha(base / path) != digest:
                    raise ValueError('USB8 notebook capacity input changed')
    audit = read_json(Path(data['rom_audit']['path']))
    words = [0x00000513, 0x43f00593, 0x01559593, 0x00100293, 0x01f29293, 0x00028067]
    import struct
    if (audit.get('status') != 'PASS' or audit.get('instruction_words') != words or
            Path(data['rom']['path']).read_bytes() != struct.pack('<6I', *words)):
        raise ValueError('USB8 reset ROM instruction inventory differs')
    for key in ('source', 'assembly', 'object', 'elf', 'binary'):
        origin_destination(manifest, audit[key]['path'], audit[key]['sha256'])
    runtime = read_json(Path(data['rtl_build']['path']))
    if (runtime.get('binary_sha256') != data['binary']['sha256'] or runtime.get('profile') != selected_profile or
            runtime.get('profile_sha256') != data['profile_sha256']):
        raise ValueError('USB8 native implementation differs')
    if selected_schema in USB_RECOVERY_SCHEMAS:
        require_recovery_runtime(runtime)
    validate_usb_runtime(directory, manifest, data, runtime)
    if selected_profile==USB_CLOCKED_PROFILE:data['binding_profile']=guest.identified(selected_definition)
    data['native_bundle'] = {'schema': selected_schema, 'manifest_sha256': guest.sha(directory / 'bundle.json'),
                             'source_commit': manifest['source_commit'],
                             'scope': 'complete original consumed '+selected_profile+' sources and artifacts; RTL only',
                             'software_deployment': copy.deepcopy(manifest['software_deployment'])}
    if selected_profile==USB_CLOCKED_PROFILE:data['native_bundle']['path']=str(directory)
    return data


def prepared(directory,backend,workload,name=None):
    import silicon_guest as guest
    from build_kernel import source_inputs
    from silicon_profile import profile_path
    directory=Path(directory).resolve();m=read_json(directory/'bundle.json')
    if m.get('schema') in (SCHEMA_USB_NEXT,SCHEMA_USB_WIRE,SCHEMA_USB_CLOCKED,SCHEMA_USB_RECOVERY,SCHEMA_USB_CLOSURE_RECOVERY,SCHEMA_USB_PACKAGE_RECOVERY,SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
        return prepared_usb_next(directory, m, backend, workload, name)
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
    if manifest.get('schema') in (SCHEMA_USB_NEXT,SCHEMA_USB_WIRE,SCHEMA_USB_CLOCKED,SCHEMA_USB_RECOVERY,SCHEMA_USB_CLOSURE_RECOVERY,SCHEMA_USB_PACKAGE_RECOVERY,SCHEMA_USB_PACKAGE_ENTRY2,SCHEMA_USB_COMPANION_READER):
        selected=usb_native_deployment(manifest.get('profile'),schema=manifest.get('schema'))
        if manifest.get('software_deployment')!=usb_software_deployment(*selected):
            raise ValueError('USB immutable deployment authority differs')
        return dict(selected[2])
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
    'lemmasim-silicon-closure-arithmetic-oom-development',
    'lemmasim-silicon-closure-arithmetic-fault-development',
    'lemmasim-silicon-string-arithmetic-oom-development',
    'lemmasim-silicon-array-arithmetic-oom-development',
    'lemmasim-silicon-bytes-arithmetic-oom-development',
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
    if configuration in (*COURSE_CONFIGURATIONS.values(),*COURSE_AWAIT_CONFIGURATIONS.values(),*PACKAGE_CLOSURE_CONFIGURATIONS.values(),*READER_CONFIGURATIONS.values(),*CHOOSER_READER_CONFIGURATIONS.values()) and mode not in ("developer","laboratory"):
        raise ValueError("Course installer deployment requires Developer or Laboratory mode")
    if (profile=='lemma-silicon-dev/0.3.0' and
            any(configuration==configurations.get(workload) for configurations in SOFTWARE_DEPLOYMENTS.values())
            and mode in ('student','developer','laboratory')):
        return configuration
    if profile=='lemma-silicon-dev/0.3.0' and workload=='notebook' and mode=='laboratory' and configuration in ARITHMETIC_LAB_CONFIGURATIONS:
        return configuration
    raise ValueError('Development guest configuration is not admitted for this profile/workload/mode')


def laboratory_guest_archive(base, source_root, profile, configuration, mode):
    """Exact original canonical failure-image authority; no ROOT fallback."""
    import silicon_guest as guest
    archived_configurations = {
        'lemmasim-silicon-array-arithmetic-oom-development': 'Array OOM',
        'lemmasim-silicon-string-arithmetic-oom-development': 'String OOM',
        'lemmasim-silicon-closure-arithmetic-oom-development': 'Closure OOM',
        'lemmasim-silicon-closure-arithmetic-fault-development': 'Closure fault',
    }
    if (profile != 'lemma-silicon-dev/0.3.0' or mode != 'laboratory' or
            configuration not in archived_configurations):
        raise ValueError('Archived development guest requires an exact canonical Laboratory failure image')
    return _audited_guest_archive(base,source_root,configuration,
        'lemma-laboratory-guest-source-archive/1',
        'unchanged fully audited canonical Laboratory ' + archived_configurations[configuration] + ' guest; complete original source/tool/object closure')


def canonical_guest_archive(base, source_root, profile, workload):
    """Normal canonical role admission plus the complete original audit closure.

    The caller cannot select an arbitrary root or a Laboratory failure image.
    A package still requires a matched notebook/initializer deployment.
    """
    import silicon_guest as guest
    if profile!='lemma-silicon-dev/0.3.0' or workload not in ('notebook','initializer'):
        raise ValueError('Original canonical archive requires profile0.3 notebook or initializer')
    base=Path(base).resolve()
    configuration=read_json(base/'build.json').get('configuration')
    admitted={guest.configurations(profile)[workload]}
    admitted.update(pair[workload] for pair in SOFTWARE_DEPLOYMENTS.values())
    if configuration not in admitted:
        raise ValueError('Original canonical archive requires an exact ordinary deployment role')
    return _audited_guest_archive(base,source_root,configuration,
        'lemma-canonical-guest-source-archive/1',
        'unchanged fully audited canonical '+workload+'; complete original source/tool/object closure')


def _audited_guest_archive(base, source_root, configuration, schema, scope):
    """One fail-closed consumed-source/tool/object validator; no ROOT fallback."""
    import silicon_guest as guest
    base = Path(base).resolve()
    root = Path(source_root).resolve()
    provenance = read_json(base / 'provenance.json')
    build = read_json(base / 'build.json')
    audit = read_json(base / 'audit.json')
    expected = provenance.get('source_inputs')
    if not isinstance(expected, dict) or not expected:
        raise ValueError('Original Laboratory guest input inventory missing')
    inventory_path = root / 'source-inputs.json'
    if not root.is_dir() or read_json(inventory_path) != expected:
        raise ValueError('Laboratory archive differs from original consumed inventory')
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlink in Laboratory consumed-source archive')
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected) | {'source-inputs.json'}:
        raise ValueError('Laboratory archive has missing or unlisted inputs')
    for path, digest in expected.items():
        if (Path(path).is_absolute() or guest._native_relative(path) != path or
                not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or
                guest.sha(root / path) != digest):
            raise ValueError('Laboratory consumed input changed: ' + str(path))
    if (audit.get('source_commit') != provenance.get('source_commit') or
            audit.get('dirty_paths') != provenance.get('dirty_paths') or
            any(report.get('lean_source_realization') != provenance.get('lean_source_realization')
                for report in (build, audit))):
        raise ValueError('Laboratory source/tool realization differs from original audit')
    pin = read_json(root / 'tooling/toolchain-lock.json').get('tools', {}).get('lean', {})
    realization = provenance.get('lean_source_realization', {})
    if (realization.get('revision') != pin.get('revision') or
            realization.get('source_path') != pin.get('source_path') or
            realization.get('narHash') != pin.get('source_sha256') or
            realization.get('narSize') != pin.get('source_nar_size') or
            not Path(realization.get('source_path', '/missing')).is_dir() or
            realization.get('uint_source') != str(Path(pin.get('source_path', '/missing')) / 'src/Init/Data/UInt/Basic.lean') or
            guest.sha(realization['uint_source']) != realization.get('uint_source_sha256')):
        raise ValueError('Original Laboratory Lean source realization changed')
    tools = provenance.get('tools', {})
    if set(tools) != {'lean', 'lake', 'opt', 'llc', 'clang', 'ld.lld', 'qemu-system-riscv64', 'dtc'}:
        raise ValueError('Original Laboratory tool inventory differs')
    observed = {}
    for tool, item in tools.items():
        if (not isinstance(item, dict) or set(item) != {'path', 'version'} or
                not str(item['path']).startswith('/nix/store/') or not os.access(item['path'], os.X_OK)):
            raise ValueError('Original Laboratory immutable tool missing')
        version = subprocess.check_output([item['path'], '--version'], stderr=subprocess.STDOUT, timeout=10).decode().strip()
        if version != item['version']:
            raise ValueError('Original Laboratory tool version differs')
        observed[tool] = {**item, 'sha256': guest.sha(item['path'])}
    guest.verify_guest_build(base, configuration, build['optimization'], source_root=root)
    return {'schema': schema, 'source_root': str(root),
            'inventory': guest.identified(inventory_path), 'build': guest.identified(base / 'build.json'),
            'provenance': guest.identified(base / 'provenance.json'), 'audit': guest.identified(base / 'audit.json'),
            'image': guest.identified(base / 'image.elf'), 'configuration': configuration,
            'source_commit': provenance['source_commit'], 'dirty_paths': provenance['dirty_paths'],
            'inputs': len(expected), 'tools': observed, 'lean_source_realization': realization,
            'scope': scope}


def development_guest(data,workload,directory,guest_build,mode=None,*,source_root=None):
    """An explicitly audited guest on an unchanged archived hardware binding.

    This explicit development option does not modify the immutable package.
    Current sources are mandatory unless the complete original Laboratory
    source archive is explicitly selected. A new capacity receipt is generated
    before a notebook can launch.
    """
    import silicon_guest as guest
    base=Path(guest_build).resolve();build=read_json(base/'build.json')
    configuration=development_configuration(data['profile'],workload,build['configuration'],mode)
    archive=None
    if source_root is not None:
        if not isinstance(data.get('native_bundle'),dict):
            raise ValueError('Original source archive requires a validated immutable native bundle')
        if configuration in ARITHMETIC_LAB_CONFIGURATIONS:
            if workload!='notebook':raise ValueError('Laboratory source archive requires notebook')
            archive=laboratory_guest_archive(base,source_root,data['profile'],configuration,mode)
        else:archive=canonical_guest_archive(base,source_root,data['profile'],workload)
    else:guest.verify_guest_build(base,configuration,build['optimization'])
    result=copy.deepcopy(data)
    entry={key:guest.identified(base/name) for key,name in (
        ('image','image.elf'),('build','build.json'),('provenance','provenance.json'),
        ('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin'))}
    if workload in guest.NOTEBOOK_WORKLOADS:
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
    if archive is not None:
        repeated=(laboratory_guest_archive(base,source_root,data['profile'],configuration,mode)
                  if configuration in ARITHMETIC_LAB_CONFIGURATIONS else
                  canonical_guest_archive(base,source_root,data['profile'],workload))
        if repeated!=archive:raise ValueError('Original consumed archive changed during preparation')
    else:guest.verify_guest_build(base,configuration,build['optimization'])
    result['workloads'][workload]=entry
    result['guest_override']={'scope':'new strict current-source audited development guest on unchanged archived backend',
                              'configuration':configuration,'mode':mode,
                              'build':entry['build'],'provenance':entry['provenance']}
    if archive is not None:
        result['guest_override'].update(scope=archive['scope'],source_archive=archive)
    return result
