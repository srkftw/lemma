#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LemmaSim RTL preparation/launch: byte transport and identity checks only."""
from __future__ import annotations
import fcntl, hashlib, json, os, shutil, signal, struct, subprocess, time
from pathlib import Path
from silicon_profile import PROFILE, profile, profile_path

ROOT=Path(__file__).resolve().parents[1]
PREPARED=ROOT/'build/lemmasim/rtl-prepared.json'
MAX_RUN_SECONDS=7200
CONFIGURATIONS={'service':'silicon-service-development', 'notebook':'lemmasim-silicon-notebook',
                'initializer':'lemmasim-silicon-initialize','devices':'lemmasim-silicon-devices'}
NOTEBOOK_WORKLOADS=frozenset({'parameterized-notebook','notebook','managed-notebook','usb-bulk-notebook','usb-next-bulk-notebook','usb-wire-bulk-notebook','usb-clocked-bulk-notebook','usb-clocked-retry-bulk-notebook','usb-clocked-closure-retry-bulk-notebook','usb-clocked-package-retry-bulk-notebook','usb-clocked-package-entry2-bulk-notebook','usb-clocked-reader-entry2-bulk-notebook'})
POWER_CONFIGURATIONS={'managed-notebook':'lemmasim-silicon-managed-notebook','managed-initializer':'lemmasim-silicon-managed-initialize','notebook':'lemmasim-silicon-power-notebook','initializer':'lemmasim-silicon-power-initialize','power':'lemmasim-silicon-power-probe'}
FULL_CONFIGURATIONS={'notebook':'lemmasim-silicon-full-notebook', 'initializer':'lemmasim-silicon-full-initialize'}
BLE_CONFIGURATIONS={'ble':'lemmasim-silicon-ble-link-probe'}
USB_CONFIGURATIONS={'usb':'lemmasim-silicon-usb-link-probe','notebook':'lemmasim-silicon-usb-notebook','initializer':'lemmasim-silicon-usb-initialize',
                    'usb-bulk-notebook':'lemmasim-silicon-usb-bulk-notebook','usb-bulk-initializer':'lemmasim-silicon-usb-bulk-initialize'}
USB_NEXT_CONFIGURATIONS={'usb-next-bulk-notebook':'lemmasim-silicon-usb-next-bulk-notebook',
                         'usb-next-bulk-initializer':'lemmasim-silicon-usb-next-bulk-initialize'}
PRODUCT_EXECUTED_CONFIGURATIONS={'product-executed-bulk-notebook':'lemmasim-silicon-product-executed-bulk-notebook'}
PRODUCT_NEXT_CONFIGURATIONS={'product-next-bulk-notebook':'lemmasim-silicon-product-next-bulk-notebook'}
USB_WIRE_CONFIGURATIONS={'usb-wire-bulk-notebook':'lemmasim-silicon-usb-wire-bulk-notebook',
                         'usb-wire-bulk-initializer':'lemmasim-silicon-usb-wire-bulk-initialize'}
USB_CLOCKED_CONFIGURATIONS={'usb-clocked-bulk-notebook':'lemmasim-silicon-usb-clocked-bulk-notebook',
                            'usb-clocked-bulk-initializer':'lemmasim-silicon-usb-clocked-bulk-initialize'}
USB_RECOVERY_CONFIGURATIONS={'usb-clocked-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-retry-bulk-notebook',
                             'usb-clocked-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-retry-bulk-initialize'}
USB_ARCHIVE_PROFILES=frozenset({'lemma-silicon-dev/0.6.0','lemma-silicon-dev/0.8.0','lemma-silicon-dev/0.11.0','lemma-silicon-dev/0.13.0'})
USB_CLOSURE_RECOVERY_CONFIGURATIONS={'usb-clocked-closure-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook',
                                     'usb-clocked-closure-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize'}
USB_PACKAGE_RECOVERY_CONFIGURATIONS={'usb-clocked-package-retry-bulk-notebook':'lemmasim-silicon-usb-clocked-package-retry-bulk-notebook',
                                     'usb-clocked-package-retry-bulk-initializer':'lemmasim-silicon-usb-clocked-package-retry-bulk-initialize'}
USB_CLOCKED_PROFILE_NAME='lemma-silicon-dev/0.13.0'
USB_CLOCKED_PROFILE_FILE='sim/profiles/lemma-silicon-dev-0.13.0.json'
SAFETY_CONFIGURATIONS={'power':'lemmasim-silicon-power-safety-probe'}
USB_PACKAGE_ENTRY2_CONFIGURATIONS={'usb-clocked-package-entry2-bulk-notebook':'lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook',
                                  'usb-clocked-package-entry2-bulk-initializer':'lemmasim-silicon-usb-clocked-package-entry2-bulk-initialize'}

from silicon_guest_bundle import USB_COMPANION_READER_CONFIGURATIONS
def configurations(name=None):
    if name=="lemma-silicon-dev/0.14.0":
        profile(name)
        return {"notebook":"lemmasim-silicon-multimodal-notebook","initializer":"lemmasim-silicon-multimodal-initialize","parameterized-notebook":"lemmasim-silicon-multimodal-parameterized-notebook","parameterized-initializer":"lemmasim-silicon-multimodal-parameterized-initialize"}
    if name!=USB_CLOCKED_PROFILE_NAME:profile(name)
    if name==USB_CLOCKED_PROFILE_NAME:return {**USB_CLOCKED_CONFIGURATIONS,**USB_RECOVERY_CONFIGURATIONS,**USB_CLOSURE_RECOVERY_CONFIGURATIONS,**USB_PACKAGE_RECOVERY_CONFIGURATIONS,**USB_PACKAGE_ENTRY2_CONFIGURATIONS,**USB_COMPANION_READER_CONFIGURATIONS}
    return USB_CLOCKED_CONFIGURATIONS if name=='lemma-silicon-dev/0.13.0' else USB_WIRE_CONFIGURATIONS if name=='lemma-silicon-dev/0.11.0' else PRODUCT_EXECUTED_CONFIGURATIONS if name=='lemma-silicon-dev/0.10.0' else PRODUCT_NEXT_CONFIGURATIONS if name=='lemma-silicon-dev/0.9.0' else USB_NEXT_CONFIGURATIONS if name=='lemma-silicon-dev/0.8.0' else USB_CONFIGURATIONS if name=='lemma-silicon-dev/0.6.0' else BLE_CONFIGURATIONS if name=='lemma-silicon-dev/0.5.0' else SAFETY_CONFIGURATIONS if name=='lemma-silicon-dev/0.4.0' else POWER_CONFIGURATIONS if name=='lemma-silicon-dev/0.3.0' else FULL_CONFIGURATIONS if name=='lemma-silicon-dev/0.2.0' else CONFIGURATIONS
def prepared_path(name=None):
    if name=="lemma-silicon-dev/0.14.0":
        profile(name)
        return ROOT/"build/lemmasim/rtl-prepared-0.14.0.json"
    if name!=USB_CLOCKED_PROFILE_NAME:profile(name)
    return ROOT/'build/lemmasim/rtl-prepared-0.13.0.json' if name=='lemma-silicon-dev/0.13.0' else ROOT/'build/lemmasim/rtl-prepared-0.11.0.json' if name=='lemma-silicon-dev/0.11.0' else ROOT/'build/lemmasim/rtl-prepared-0.10.0.json' if name=='lemma-silicon-dev/0.10.0' else ROOT/'build/lemmasim/rtl-prepared-0.9.0.json' if name=='lemma-silicon-dev/0.9.0' else ROOT/'build/lemmasim/rtl-prepared-0.8.0.json' if name=='lemma-silicon-dev/0.8.0' else ROOT/'build/lemmasim/rtl-prepared-0.6.0.json' if name=='lemma-silicon-dev/0.6.0' else ROOT/'build/lemmasim/rtl-prepared-0.5.0.json' if name=='lemma-silicon-dev/0.5.0' else ROOT/'build/lemmasim/rtl-prepared-0.4.0.json' if name=='lemma-silicon-dev/0.4.0' else ROOT/'build/lemmasim/rtl-prepared-0.3.0.json' if name=='lemma-silicon-dev/0.3.0' else ROOT/'build/lemmasim/rtl-prepared-0.2.0.json' if name=='lemma-silicon-dev/0.2.0' else PREPARED

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
def identified(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def run_command(argv, *, timeout, log=None):
    output=log.open('w') if log else None
    proc=subprocess.Popen([str(a) for a in argv],cwd=ROOT,start_new_session=True,stdout=output,stderr=subprocess.STDOUT if output else None)
    try:
        rc=proc.wait(timeout=timeout)
        if rc:raise RuntimeError(f'RTL command failed ({rc}); '+(str(log) if log else str(argv[0])))
    finally:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=5)
        if output:output.close()

def validate(item):
    if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise ValueError('malformed RTL artifact identity')
    p=Path(item['path'])
    if not p.is_file() or sha(p)!=item['sha256']:raise ValueError('RTL artifact changed or missing: '+str(p))
    return p

def _read_unique_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate native source-archive metadata key')
            result[key]=value
        return result
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)

def _native_relative(path, original_root=None):
    value=Path(path)
    if '..' in value.parts:raise ValueError('Escaping native source input')
    if value.is_absolute():
        try:value=value.relative_to(ROOT if original_root is None else original_root)
        except ValueError:raise ValueError('Native input is outside the declared source root') from None
    if not value.parts or any(part in ('..','.') for part in value.parts):
        raise ValueError('Escaping native source input')
    return value.as_posix()

def native_source_archive(build,source_root,name):
    """Validate a complete original USB native closure; no current-source fallback.

    The original public preparation receipt contributes only the preparation-time
    dependency input absent from the native compiler manifest. Clocked schema2
    also retains the selected JSON already bound separately by profile_sha256.
    Every entry is reconstructed from those original identities; guests retain
    their independently validated current or explicit archived source inventory.
    """
    if name not in USB_ARCHIVE_PROFILES:
        raise ValueError('Explicit RTL source archives support only USB6, USB8, USBWire11 or USBClocked13; Product uses its separate ROM validator')
    build=Path(build).resolve();source_root=Path(source_root).resolve()
    manifest_path=build/'build.json';m=_read_unique_json(manifest_path)
    sidecar=source_root.parent/'consumed-source-archive.json'
    receipt_path=source_root.parent/'consumed-runtime-receipt.json'
    a=_read_unique_json(sidecar);receipt=_read_unique_json(receipt_path)
    if m.get('profile')!=name or m.get('configuration')!='external-ram-128MiB':
        raise ValueError('Native archive has a different profile or RAM configuration')
    clocked=name==USB_CLOCKED_PROFILE_NAME
    if clocked and a.get('schema')!='lemma-usb-native-source-archive/2':
        raise ValueError('Clocked native archive requires its separately bound selected profile input')
    if not clocked and m.get('profile_sha256')!=sha(profile_path(name)):
        raise ValueError('Native archive selected profile changed')
    original_root=ROOT
    if clocked:
        from product_native import archived_original_root
        original_root=archived_original_root(m)
    expected={}
    def add(path,digest):
        path=_native_relative(path, original_root)
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Malformed native source digest')
        if path in expected and expected[path]!=digest:raise ValueError('Conflicting native source digest')
        expected[path]=digest
    for key in ('sha256','configuration_includes','host_runtime','host_toolchain_inputs','binding_generator_inputs'):
        if not isinstance(m.get(key),dict) or not m[key]:raise ValueError('Missing native source inventory: '+key)
        for path,digest in m[key].items():add(path,digest)
    if not isinstance(m.get('sources'),list) or len(set(m['sources']))!=len(m['sources']) or set(m['sources'])!=set(m['sha256']):
        raise ValueError('Native compiler source list differs from its digest inventory')
    for key in ('host_adapter','build_driver','upstream_patch','runtime_identity_header'):
        item=m.get(key)
        if not isinstance(item,dict) or not {'path','sha256'}<=item.keys():raise ValueError('Missing native input identity: '+key)
        add(item['path'],item['sha256'])
    add(Path(m['host_include_dir'])/'lemma_silicon_binding.h',m['host_binding_sha256'])
    if not isinstance(receipt.get('rtl_sources'),dict) or not receipt['rtl_sources']:
        raise ValueError('Original native preparation input inventory missing')
    original={_native_relative(path,original_root):digest for path,digest in receipt['rtl_sources'].items()}
    if len(original)!=len(receipt['rtl_sources']):raise ValueError('Duplicate normalized original native source input')
    receipt_paths=set(expected)|{'tooling/silicon/dependencies.json'}
    if clocked and USB_CLOCKED_PROFILE_FILE in original:
        if original[USB_CLOCKED_PROFILE_FILE]!=m['profile_sha256']:
            raise ValueError('Original native receipt selected profile differs')
        receipt_paths.add(USB_CLOCKED_PROFILE_FILE)
    receipt_manifest=Path(receipt.get('rtl_build',{}).get('path',''))
    if clocked:
        if (not receipt_manifest.is_absolute() or '..' in receipt_manifest.parts or
                receipt_manifest.name!='build.json' or not receipt_manifest.is_relative_to(original_root)):
            raise ValueError('Original Clocked native build path is outside its source prefix')
        expected_receipt_manifest=str(receipt_manifest)
        expected_receipt_binary=str(receipt_manifest.parent/'obj/lemma-rtl')
    else:
        expected_receipt_manifest=str(manifest_path)
        expected_receipt_binary=str(build/'obj/lemma-rtl')
    if (receipt.get('schema_version')!=1 or receipt.get('profile')!=name or
        receipt.get('profile_sha256')!=m['profile_sha256'] or
        receipt.get('rtl_build')!={'path':expected_receipt_manifest,'sha256':sha(manifest_path)} or
        receipt.get('binary')!={'path':expected_receipt_binary,'sha256':m.get('binary_sha256')} or
        set(original)!=receipt_paths or
        any(original.get(path)!=digest for path,digest in expected.items())):
        raise ValueError('Original native preparation receipt differs from the full consumed manifest')
    add('tooling/silicon/dependencies.json',original['tooling/silicon/dependencies.json'])
    if clocked:
        selected={'path':USB_CLOCKED_PROFILE_FILE,'sha256':m['profile_sha256']}
        if a.get('selected_profile')!=selected:
            raise ValueError('Clocked selected profile differs from its original native manifest')
        add(selected['path'],selected['sha256'])
    if (a.get('schema')!=('lemma-usb-native-source-archive/2' if clocked else 'lemma-usb-native-source-archive/1') or
        a.get('build_manifest_sha256')!=sha(manifest_path) or
        a.get('binary_sha256')!=m.get('binary_sha256') or
        a.get('snapshot_identity')!=m.get('snapshot_identity') or
        a.get('source_inputs')!=expected):
        raise ValueError('Native source archive differs from the complete original receipt')
    # Recompute the native implementation identity independently of execution paths.
    identity={k:v for k,v in m.items() if k not in
              ('sources','include_dirs','host_include_dir','runtime_identity_header','build_argv','build_jobs','binary_sha256','snapshot_identity')}
    identity['identity_schema']='lemmasim-rtl-implementation/2'
    core=original_root/'build/silicon/deps/cvw';generated=Path(m['host_include_dir'])/'lemma_silicon_binding.sv'
    def logical(path):
        path=Path(path)
        if path==generated:return 'generated/lemma_silicon_binding.sv'
        for base,prefix in ((core,'core/'),(core.parent/'cvw-patched','patched-core/'),(original_root,'repository/')):
            try:return prefix+path.relative_to(base).as_posix()
            except ValueError:pass
        raise ValueError('Unmapped native implementation input')
    for key in ('sha256','configuration_includes'):
        identity[key]={logical(path):digest for path,digest in m[key].items()}
        if len(identity[key])!=len(m[key]):raise ValueError('Duplicate logical native input')
    if hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=m.get('snapshot_identity'):
        raise ValueError('Native implementation identity differs from its original manifest')
    if not source_root.is_dir():raise ValueError('Native source archive directory missing')
    actual=set()
    for path in source_root.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in native source archive')
        if path.is_file():actual.add(path.relative_to(source_root).as_posix())
    if actual!=set(expected):raise ValueError('Native source archive has missing or unlisted files')
    for path,digest in expected.items():
        if sha(source_root/path)!=digest:raise ValueError('Changed archived native input: '+path)
    if clocked:
        selected_json=_read_unique_json(source_root/USB_CLOCKED_PROFILE_FILE)
        if selected_json.get('profile')!=name or selected_json.get('schema_version')!=1:
            raise ValueError('Clocked archived selected profile namespace differs')
    dependency=_read_unique_json(source_root/'tooling/silicon/dependencies.json')
    if (dependency.get('schema_version')!=1 or
        dependency.get('core',{}).get('repository')!=m.get('core_repository') or
        dependency.get('core',{}).get('revision')!=m.get('core_revision')):
        raise ValueError('Archived tool/core dependency declaration differs')
    header=(source_root/_native_relative(m['runtime_identity_header']['path'],original_root)) if clocked else validate(m['runtime_identity_header'])
    if sha(header)!=m['runtime_identity_header']['sha256']:raise ValueError('Native archived compiled identity header changed')
    if header.read_text()!='#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+m['snapshot_identity']+'"\n':
        raise ValueError('Native executable identity header differs')
    binary=validate({'path':str(build/'obj/lemma-rtl'),'sha256':m['binary_sha256']})
    evidence={'schema':'lemma-explicit-rtl-source-archive/1','source_root':str(source_root),
              'archive':identified(sidecar),'original_receipt':identified(receipt_path),
              'native_manifest':identified(manifest_path),'snapshot_identity':m['snapshot_identity'],
              'binary':identified(binary),'inputs':len(expected),
              'scope':('unchanged archived native USB6 machine; newly prepared guests retain their own source and audit identities' if name=='lemma-silicon-dev/0.6.0' else 'unchanged archived native USB8 machine; newly prepared guests retain their own source and audit identities' if name=='lemma-silicon-dev/0.8.0' else 'unchanged archived native USBWire11 machine; newly prepared guests retain their own source and audit identities' if name=='lemma-silicon-dev/0.11.0' else 'unchanged archived native USBClocked13 machine; newly prepared guests retain their own source and audit identities')}
    if clocked:evidence.update(schema='lemma-explicit-rtl-source-archive/2',selected_profile=identified(source_root/USB_CLOCKED_PROFILE_FILE))
    return m,{str(original_root/path):digest for path,digest in expected.items()},evidence

def prepared_profile(data):
    """Read the bound Clocked profile, never substitute a mutable ROOT copy."""
    if data.get('profile')!=USB_CLOCKED_PROFILE_NAME:return profile(data['profile'])
    item=data.get('binding_profile') or data.get('rtl_source_archive',{}).get('selected_profile')
    if item is None:raise ValueError('Clocked prepared machine lacks its archived selected profile')
    path=validate(item)
    if item['sha256']!=data.get('profile_sha256'):raise ValueError('Clocked prepared profile digest differs')
    result=_read_unique_json(path)
    if result.get('profile')!=USB_CLOCKED_PROFILE_NAME or result.get('schema_version')!=1:
        raise ValueError('Clocked prepared profile namespace differs')
    return result

def validate_clocked_capture_authority(data,workload):
    """Reconcile recorded host authority with its complete immutable source set."""
    if data.get('profile')!=USB_CLOCKED_PROFILE_NAME:raise ValueError('Clocked capture authority profile differs')
    package=data.get('native_bundle')
    if package is not None:
        import silicon_guest_bundle
        directory=Path(package.get('path','/missing'))
        checked=silicon_guest_bundle.prepared(directory,'rtl',workload,USB_CLOCKED_PROFILE_NAME)
        if checked!=data:raise ValueError('Clocked captured package authority differs')
    else:
        native=data.get('rtl_source_archive');entry=data['workloads'][workload]
        target=entry.get('guest_source_archive')
        if native is None or target is None:raise ValueError('Clocked capture requires complete explicit native and guest archives')
        _,sources,evidence=native_source_archive(validate(data['rtl_build']).parent,native['source_root'],USB_CLOCKED_PROFILE_NAME)
        if evidence!=native or sources!=data['rtl_sources']:raise ValueError('Clocked captured native authority differs')
        if (data.get('binding_profile')!=evidence['selected_profile'] or
                data.get('profile_sha256')!=evidence['selected_profile']['sha256']):
            raise ValueError('Clocked captured selected profile differs from native authority')
        build=validate(entry['build']).parent;optimization=_read_unique_json(build/'build.json')['optimization']
        checked=guest_source_archive(build,target['source_root'],configurations(USB_CLOCKED_PROFILE_NAME)[workload],optimization,USB_CLOCKED_PROFILE_NAME)
        if checked!=target:raise ValueError('Clocked captured guest authority differs')
    prepared_profile(data)

def guest_source_archive(guest,source_root,configuration,optimization,name):
    """Revalidate an unchanged genuine USB guest's entire consumed source tree.

    The original sidecar is observational evidence, not an alternate compilation
    oracle. The ordinary build/audit validator still checks the original artifacts
    and independently enumerates this complete tree with source_inputs().
    """
    if name not in USB_ARCHIVE_PROFILES or configuration not in configurations(name).values():
        raise ValueError('Explicit guest source archives support only USB6 or USB8 configurations')
    guest=Path(guest).resolve();source_root=Path(source_root).resolve()
    sidecar=source_root.parent/'consumed-source-archive.json'
    a=_read_unique_json(sidecar)
    b=_read_unique_json(guest/'build.json');v=_read_unique_json(guest/'provenance.json');audit=_read_unique_json(guest/'audit.json')
    expected=v.get('source_inputs')
    if not isinstance(expected,dict) or not expected:raise ValueError('Missing original guest source inventory')
    for path,digest in expected.items():
        if Path(path).is_absolute() or _native_relative(path)!=path or not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Malformed original guest source input')
    if (a.get('schema')!='lemma-usb-guest-source-archive/1' or
        a.get('source_inputs')!=expected or a.get('source_commit')!=v.get('source_commit') or
        a.get('dirty_paths')!=v.get('dirty_paths') or a.get('tools')!=v.get('tools') or
        a.get('lean_source_realization')!=v.get('lean_source_realization') or
        a.get('provenance_sha256')!=sha(guest/'provenance.json') or
        a.get('build_sha256')!=sha(guest/'build.json') or a.get('image_sha256')!=sha(guest/'image.elf')):
        raise ValueError('Guest archive differs from its complete original build/provenance/image identities')
    if not source_root.is_dir():raise ValueError('Guest source archive directory missing')
    actual=set()
    for path in source_root.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in guest source archive')
        if path.is_file():actual.add(path.relative_to(source_root).as_posix())
    if actual!=set(expected):raise ValueError('Guest source archive has missing or unlisted files')
    for path,digest in expected.items():
        if sha(source_root/path)!=digest:raise ValueError('Changed archived guest input: '+path)
    if (audit.get('source_commit')!=v.get('source_commit') or audit.get('dirty_paths')!=v.get('dirty_paths') or
        any(report.get('lean_source_realization')!=v.get('lean_source_realization') for report in (b,audit))):
        raise ValueError('Guest audit source/tool realization differs from the original build')
    pin=_read_unique_json(source_root/'tooling/toolchain-lock.json').get('tools',{}).get('lean',{})
    realization=v.get('lean_source_realization',{})
    if (realization.get('revision')!=pin.get('revision') or realization.get('source_path')!=pin.get('source_path') or
        realization.get('narHash')!=pin.get('source_sha256') or realization.get('narSize')!=pin.get('source_nar_size') or
        not Path(realization.get('source_path','/missing')).is_dir() or
        realization.get('uint_source')!=str(Path(pin.get('source_path','/missing'))/'src/Init/Data/UInt/Basic.lean') or
        sha(realization['uint_source'])!=realization.get('uint_source_sha256')):
        raise ValueError('Original guest Lean source realization changed')
    tools=v.get('tools',{})
    if set(tools)!={'lean','lake','opt','llc','clang','ld.lld','qemu-system-riscv64','dtc'}:
        raise ValueError('Original guest tool inventory differs')
    observed_tools={}
    for tool,item in tools.items():
        if not isinstance(item,dict) or set(item)!={'path','version'} or not str(item['path']).startswith('/nix/store/') or not os.access(item['path'],os.X_OK):
            raise ValueError('Missing immutable original guest tool: '+tool)
        output=subprocess.run([item['path'],'--version'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,timeout=10).stdout.decode().strip()
        if output!=item['version']:raise ValueError('Original guest tool version changed: '+tool)
        observed_tools[tool]={**item,'sha256':sha(item['path'])}
    verify_guest_build(guest,configuration,optimization,source_root=source_root)
    return {'schema':'lemma-explicit-guest-source-archive/1','source_root':str(source_root),
            'archive':identified(sidecar),'build':identified(guest/'build.json'),'provenance':identified(guest/'provenance.json'),
            'audit':identified(guest/'audit.json'),'image':identified(guest/'image.elf'),
            'source_commit':v['source_commit'],'dirty_paths':v['dirty_paths'],'inputs':len(expected),
            'configuration':configuration,'optimization':optimization,'tools':observed_tools,
            'lean_source_realization':realization,
            'scope':('unchanged archived genuine USB6 guest and original strict audit; newly prepared host adapter, not fresh target compilation' if name=='lemma-silicon-dev/0.6.0' else 'unchanged archived genuine USB8 guest and original strict audit; newly prepared host adapter, not fresh target compilation' if name=='lemma-silicon-dev/0.8.0' else 'unchanged archived genuine USBWire11 guest and original strict audit; newly prepared host adapter, not fresh target compilation' if name=='lemma-silicon-dev/0.11.0' else 'unchanged archived genuine USBClocked13 guest and original strict audit; newly prepared host adapter, not fresh target compilation')}

def prepared(workload,name=None,*,rtl_source_root=None,guest_source_root=None):
    selected=configurations(name)
    if workload not in selected:raise ValueError('Workload is not admitted by the selected binding')
    data=json.loads(prepared_path(name).read_text())
    if name==USB_CLOCKED_PROFILE_NAME:
        changed=data.get('schema_version')!=1 or data.get('profile')!=name
    else:
        changed=(data.get('schema_version')!=1 or data.get('profile')!=profile(name)['profile'] or
                 data.get('profile_sha256')!=sha(profile_path(name)))
    if changed:
        raise ValueError('RTL prepared binding changed; run lemmasim build --backend rtl')
    validate(data['binary']);validate(data['rom']);validate(data['rom_audit']);validate(data['rtl_build'])
    archived=data.get('rtl_source_archive')
    if archived is not None and rtl_source_root is None:
        raise ValueError('Prepared runtime requires its explicit --rtl-source-root; current-source fallback is forbidden')
    if rtl_source_root is not None:
        _,sources,evidence=native_source_archive(validate(data['rtl_build']).parent,rtl_source_root,data['profile'])
        if sources!=data['rtl_sources'] or (archived is not None and evidence!=archived):
            raise ValueError('Prepared native source archive identity changed')
        if name==USB_CLOCKED_PROFILE_NAME:
            if evidence['selected_profile']['sha256']!=data['profile_sha256']:raise ValueError('Prepared Clocked selected profile changed')
            data['binding_profile']=evidence['selected_profile'];prepared_profile(data)
    else:
        for path,digest in data['rtl_sources'].items():
            if not Path(path).is_file() or sha(path)!=digest:raise ValueError('RTL source/dependency changed: '+path)
    if workload not in data['workloads']:
        raise ValueError('RTL workload is not prepared; run lemmasim build --backend rtl --workload '+workload)
    for key in ('image','build','provenance','audit','dtb','descriptor'):
        validate(data['workloads'][workload][key])
    entry=data['workloads'][workload];guest=validate(entry['build']).parent
    optimization=json.loads((guest/'build.json').read_text())['optimization']
    guest_archive=entry.get('guest_source_archive')
    if guest_archive is not None and guest_source_root is None:
        raise ValueError('Prepared guest requires its explicit --guest-source-root; current-source fallback is forbidden')
    if guest_source_root is not None:
        evidence=guest_source_archive(guest,guest_source_root,selected[workload],optimization,data['profile'])
        if guest_archive is not None and evidence!=guest_archive:raise ValueError('Prepared guest source archive identity changed')
    else:verify_guest_build(guest,selected[workload],optimization)
    if workload in NOTEBOOK_WORKLOADS:
        capacity=json.loads(validate(data['workloads'][workload]['capacity']).read_text())
        if capacity.get('status')!='PASS' or capacity.get('configuration')!=selected[workload]:
            raise ValueError('RTL notebook selected capacity evidence differs')
        for name,digest in capacity['artifacts'].items():
            if sha(guest/name)!=digest:raise ValueError('RTL notebook capacity artifact changed: '+name)
    return data

def reset_rom_audit(data):
    audit=json.loads(validate(data['rom_audit']).read_text())
    words=[0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067]
    if audit.get('status')!='PASS' or audit.get('instruction_words')!=words:
        raise ValueError('Reset ROM audit inventory differs')
    for key in ('source','assembly','object','elf','binary'):validate(audit[key])
    if audit['source']['path']!=str((ROOT/'Lemma/Platform/Silicon/BootROM.lean').resolve()) or audit['binary']!=data['rom']:
        raise ValueError('Reset ROM audited source/binary differs')
    if validate(data['rom']).read_bytes()!=struct.pack('<6I',*words):
        raise ValueError('Reset ROM actual instruction words differ')
    if 'production_admission' in audit:
        admission=audit['production_admission']
        if not isinstance(admission,dict):raise ValueError('Reset ROM production admission is malformed')
        producer=admission.get('producer',{})
        if not isinstance(producer,dict):raise ValueError('Reset ROM producer receipt is malformed')
        encoded=(json.dumps(producer,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        request=(json.dumps(producer.get('request'),sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
        if (admission.get('schema')!='lemma-action-admission/1' or
                admission.get('status') not in ('fresh','reused') or
                hashlib.sha256(encoded).hexdigest()!=admission.get('producer_receipt_id') or
                producer.get('schema')!='lemma-action-producer/1' or
                producer.get('result')!='success' or
                producer.get('action_key')!=admission.get('action_key') or
                hashlib.sha256(request).hexdigest()!=admission.get('action_key') or
                not isinstance(admission.get('outputs'),dict) or
                producer.get('outputs')!=admission.get('outputs') or
                set(admission.get('outputs',{}))!={'boot.S','boot.o','boot.elf','boot.bin'}):
            raise ValueError('Reset ROM production admission differs')
        for field,name in (('assembly','boot.S'),('object','boot.o'),('elf','boot.elf'),('binary','boot.bin')):
            if admission['outputs'].get(name,{}).get('sha256')!=audit[field]['sha256']:
                raise ValueError('Reset ROM admitted output differs: '+name)
        if producer.get('request',{}).get('inputs',{}).get('Lemma/Platform/Silicon/BootROM.lean',{}).get('sha256')!=audit['source']['sha256']:
            raise ValueError('Reset ROM admitted source differs')
    return audit

def reusable_reset_rom(previous,data,guest):
    """Historical prepared-receipt comparison; new builds use ActionCache early.

    Kept for callers inspecting original receipts. It is intentionally absent
    from the ordinary production path, where running the tools first is wasteful.
    """
    if previous is None:return None
    for key in ('schema_version','profile','profile_sha256','binary','rtl_build','rtl_sources','rtl_source_archive','memory','physical_conformance'):
        if previous.get(key)!=data.get(key):return None
    current_provenance=json.loads((guest/'provenance.json').read_text())
    matching_provenance=None
    selected=configurations(data['profile'])
    for workload,entry in previous['workloads'].items():
        if workload not in selected:continue
        try:
            old_guest=validate(entry['build']).parent
            old_build=json.loads((old_guest/'build.json').read_text())
            verify_guest_build(old_guest,selected[workload],old_build['optimization'])
            candidate=json.loads(validate(entry['provenance']).read_text())
        except (OSError,ValueError,KeyError):continue
        if all(candidate[key]==current_provenance[key] for key in ('tools','lean_source_realization','source_inputs')):
            matching_provenance=candidate;break
    if matching_provenance is None:return None
    if data.get('rtl_source_archive') is not None:
        _,sources,evidence=native_source_archive(validate(data['rtl_build']).parent,data['rtl_source_archive']['source_root'],data['profile'])
        if sources!=data['rtl_sources'] or evidence!=data['rtl_source_archive']:raise ValueError('Reset ROM native source archive changed')
    else:
        for path,digest in previous['rtl_sources'].items():
            if not Path(path).is_file() or sha(path)!=digest:raise ValueError('Reset ROM RTL/tool source changed: '+path)
    for key in ('binary','rtl_build'):validate(previous[key])
    old_audit=reset_rom_audit(previous);new_audit=reset_rom_audit(data)
    if old_audit['scope']!=new_audit['scope'] or any(old_audit[key]['sha256']!=new_audit[key]['sha256'] for key in ('source','assembly','object','elf','binary')):
        raise ValueError('Unchanged reset ROM generated artifacts differ')
    return {'rom':previous['rom'],'rom_audit':previous['rom_audit']}

def publish_prepared(data):
    destination=prepared_path(data['profile'])
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.'+str(time.time_ns()))
    try:
        with temporary.open('xb') as stream:
            stream.write((json.dumps(data,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,destination)
    finally:
        if temporary.exists():temporary.unlink()

def build(args):
    from silicon_compute import source_manifest, prepare
    name=getattr(args,'profile',None) or 'lemma-silicon-dev/0.1.0'
    archive_root=getattr(args,'rtl_source_root',None)
    selected_profile_path=(Path(archive_root).resolve()/USB_CLOCKED_PROFILE_FILE
                           if name==USB_CLOCKED_PROFILE_NAME and archive_root is not None else profile_path(name))
    p=_read_unique_json(selected_profile_path) if name==USB_CLOCKED_PROFILE_NAME and archive_root is not None else profile(name)
    selected=configurations(name)
    if p.get('boot_nv_enabled',0):
        raise ValueError('Product hardware requires immutable ROM boot and its separate boot-medium launcher')
    workload=getattr(args,'workload',None) or 'service'
    if workload not in selected:raise ValueError('Workload is not admitted by the selected binding')
    out=(getattr(args,'rtl_build',None) or ROOT/('build/silicon/compute-'+name.split('/')[1] if name!='lemma-silicon-dev/0.1.0' else 'build/silicon/compute')).resolve();dep=(getattr(args,'deps',None) or ROOT/'build/silicon/deps/cvw').resolve()
    archive_sources=archive_evidence=None
    if archive_root is not None:
        if getattr(args,'rtl_build',None) is None:raise ValueError('--rtl-source-root requires an explicit --rtl-build')
        cached,archive_sources,archive_evidence=native_source_archive(out,archive_root,name)
    else:
        prepare(dep);current=source_manifest(dep,name)
        cached=None
        try:cached=json.loads((out/'build.json').read_text())
        except (OSError,ValueError):pass
        if cached is None or cached.get('configuration')!='external-ram-128MiB' or any(cached.get(k)!=v for k,v in current.items()) or not (out/'obj/lemma-rtl').is_file() or cached.get('binary_sha256')!=sha(out/'obj/lemma-rtl'):
            if getattr(args,'rtl_build',None):raise ValueError('Supplied RTL build differs from current exact source closure')
            run_command(['python3','scripts/silicon_compute.py','build','--profile',name,'--output-dir',out,'--deps',dep],timeout=1200)
            cached=json.loads((out/'build.json').read_text())
    stamp=str(time.time_ns());directory=ROOT/f'build/silicon/prepared-{stamp}'
    directory.mkdir(parents=True)
    rom=directory/'rom';rom.mkdir()
    # Eligibility is decided inside the pinned environment before Lake, Lean,
    # assembly, linking or extraction. Current audits remain fresh even on a hit.
    rom_command=['nix','develop','--no-write-lock-file','--command','python3',
                 'scripts/silicon_reset_rom.py','--output-dir',rom,
                 '--profile-file',selected_profile_path]
    if getattr(args,'fresh',False):rom_command+=['--fresh']
    if getattr(args,'cache_dir',None) is not None:rom_command+=['--cache-dir',args.cache_dir]
    run_command(rom_command,timeout=1200,log=directory/'rom-production.log')
    admission=json.loads((rom/'action-admission.json').read_text())
    consumed=admission['producer']['request']['inputs']
    for logical,item in consumed.items():
        source=selected_profile_path if logical=='selected-profile.json' else ROOT/logical
        if item['sha256']!=sha(source):
            raise ValueError('Reset ROM consumed input changed during preparation: '+logical)
    # Independent instruction-word inventory for this fixed versioned binding:
    # a0=0; a1=0x43f<<21; t0=1<<31; jalr x0,t0,0. Unknown words fail closed.
    if (p['dtb_base'],p['entry'])!=(0x87e00000,0x80000000):raise ValueError('Reset handoff audit requires a new binding inventory')
    words=(0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067)
    if (rom/'boot.bin').read_bytes()!=struct.pack('<6I',*words):raise ValueError('Reset handoff instruction inventory differs')
    (rom/'audit.json').write_text(json.dumps({'status':'PASS','scope':'exact structured reset handoff words; no guest privilege initialization',
        'source':identified(ROOT/'Lemma/Platform/Silicon/BootROM.lean'),
        'assembly':identified(rom/'boot.S'),'object':identified(rom/'boot.o'),'elf':identified(rom/'boot.elf'),
        'binary':identified(rom/'boot.bin'),'instruction_words':words,
        'production_admission':admission},indent=2)+'\n')
    data={'schema_version':1,'profile':p['profile'],'profile_sha256':sha(selected_profile_path),
          'binary':identified(out/'obj/lemma-rtl'),'rom':identified(rom/'boot.bin'),'rom_audit':identified(rom/'audit.json'),
          'rtl_build':identified(out/'build.json'),'rtl_sources':{**cached['sha256'],**cached['configuration_includes'],
              str(ROOT/cached['host_adapter']['path']):cached['host_adapter']['sha256'],
              str(Path(cached['host_include_dir'])/'lemma_silicon_binding.h'):cached['host_binding_sha256'],
              **{str(ROOT/path):digest for path,digest in cached['host_runtime'].items()},
              **{str(ROOT/path):digest for path,digest in cached['host_toolchain_inputs'].items()},
              **{str(ROOT/path):digest for path,digest in cached['binding_generator_inputs'].items()},
              str(cached['runtime_identity_header']['path']):cached['runtime_identity_header']['sha256'],
              **{str(ROOT/name):sha(ROOT/name) for name in ('scripts/silicon_compute.py','scripts/silicon_profile.py',
                 'tooling/silicon/apply_cvw.py','tooling/silicon/dependencies.json','tooling/silicon/sim.nix')}},'workloads':{},
          'memory':'128 MiB external simulation bytes, not synthesized SRAM','physical_conformance':'UNVERIFIED'}
    if archive_evidence is not None:
        data['rtl_sources']=archive_sources;data['rtl_source_archive']=archive_evidence
    if name==USB_CLOCKED_PROFILE_NAME:
        data['binding_profile']=identified(selected_profile_path)
        if archive_evidence is None:data['rtl_sources'][str(ROOT/USB_CLOCKED_PROFILE_FILE)]=data['profile_sha256']
        prepared_profile(data)
    guest=getattr(args,'guest_build',None)
    if guest is None:
        guest=ROOT/f'build/kernel/silicon-{workload}-{stamp}-{args.opt_level}'
        guest_command=['nix','develop','--no-write-lock-file','--command','python3','scripts/build_kernel.py',
            '--configuration',selected[workload],'--stage','supervisor','--opt-level',args.opt_level,
            '--output-dir',guest,'--timeout','300']
        if getattr(args,'fresh',False):guest_command+=['--fresh']
        if getattr(args,'cache_dir',None) is not None:guest_command+=['--cache-dir',args.cache_dir]
        run_command(guest_command,timeout=1500,log=directory/'guest-build.log')
        run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/audit_kernel.py',guest],timeout=600,log=directory/'guest-audit.log')
    guest=Path(guest).resolve()
    guest_root=getattr(args,'guest_source_root',None);guest_evidence=None
    if guest_root is not None:
        if getattr(args,'guest_build',None) is None:raise ValueError('--guest-source-root requires an explicit --guest-build')
        guest_evidence=guest_source_archive(guest,guest_root,selected[workload],args.opt_level,name)
    else:verify_guest_build(guest,selected[workload],args.opt_level)
    if workload in NOTEBOOK_WORKLOADS:
        capacity_path=directory/'guest-capacity.json'
        run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/audit_lemmasim_capacity.py',
                     '--build',guest,'--output',capacity_path],timeout=120,log=directory/'guest-capacity.log')
        capacity=json.loads(capacity_path.read_text())
        if capacity.get('status')!='PASS':raise ValueError('RTL notebook selected capacity audit did not pass')
    entry={key:identified(guest/name) for key,name in [('image','image.elf'),('build','build.json'),('provenance','provenance.json'),('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin')]}
    if guest_evidence is not None:entry['guest_source_archive']=guest_evidence
    if workload in NOTEBOOK_WORKLOADS:entry['capacity']=identified(capacity_path)
    previous=None
    try:
        previous=json.loads(prepared_path(name).read_text())
        if previous.get('profile_sha256')==data['profile_sha256']:
            for key,old_entry in previous['workloads'].items():
                if key in selected:
                    try:
                        for field,item in old_entry.items():
                            if field!='guest_source_archive':validate(item)
                        old_build=json.loads(validate(old_entry['build']).read_text())
                        old_archive=old_entry.get('guest_source_archive')
                        if old_archive is not None:
                            evidence=guest_source_archive(validate(old_entry['build']).parent,old_archive['source_root'],selected[key],old_build['optimization'],name)
                            if evidence!=old_archive:raise ValueError('Original archived guest association changed')
                        else:verify_guest_build(validate(old_entry['build']).parent,selected[key],old_build['optimization'])
                        if key in NOTEBOOK_WORKLOADS:validate(old_entry['capacity'])
                    except (OSError,ValueError,KeyError):
                        continue
                    data['workloads'][key]=old_entry
    except FileNotFoundError:pass
    data['workloads'][workload]=entry
    publish_prepared(data)
    print(f'Prepared RTL {workload}; {prepared_path(name)}. Ordinary launch validates identities without rebuilding.')

def verify_guest_build(guest,configuration,optimization,*,source_root=ROOT):
    from build_kernel import source_inputs
    build=json.loads((guest/'build.json').read_text());provenance=json.loads((guest/'provenance.json').read_text())
    audit=json.loads((guest/'audit.json').read_text())
    if (build.get('status'),audit.get('status'))!=('BUILT','PASS'):
        raise ValueError('RTL guest needs a successful real build and strict audit')
    for report in (build,provenance,audit):
        if (report.get('configuration'),report.get('stage'),report.get('optimization'))!=(configuration,'supervisor',optimization):
            raise ValueError('RTL guest build/audit configuration differs')
    # Normal preparation always uses ROOT. A native bundle uses its complete,
    # hash-validated archived source tree, never an unchecked expected digest.
    if provenance.get('source_inputs')!=source_inputs(source_root):raise ValueError('RTL guest source snapshot differs from exact inputs')
    if build.get('provenance_sha256')!=sha(guest/'provenance.json') or audit.get('image_sha256')!=sha(guest/'image.elf'):
        raise ValueError('RTL guest build/audit identities differ')
    for name,digest in provenance['artifacts'].items():
        path=(guest/name).resolve()
        if not path.is_relative_to(guest) or not path.is_file() or sha(path)!=digest:raise ValueError('RTL guest artifact changed: '+name)

def bounded_options(args):
    options={key:getattr(args,key,None) for key in ('cycles','trace_limit','timeout','uart_stop','uart_stop_hex','stop_after_panel','fail_flush','observer_cycle','ram_dump','block_trace')}
    if type(options['cycles']) is not int or not 0<options['cycles']<=10000000000:raise ValueError('RTL cycles must be 1..10000000000')
    if type(options['trace_limit']) is not int or not 0<=options['trace_limit']<=1000000:raise ValueError('RTL trace limit must be 0..1000000')
    options['timeout']=options['timeout'] or 120
    if not 1<=options['timeout']<=MAX_RUN_SECONDS:raise ValueError(f'RTL timeout must be 1..{MAX_RUN_SECONDS} seconds')
    for key in ('stop_after_panel','fail_flush','observer_cycle'):
        value=options[key]
        if value is not None and (type(value) is not int or not 1<=value<=(options['cycles'] if key=='observer_cycle' else 1000000)):raise ValueError('Invalid RTL '+key)
    if options['uart_stop'] and options['uart_stop_hex']:raise ValueError('Use one RTL UART stop marker')
    if options['uart_stop_hex'] is not None:
        if not options['uart_stop_hex'] or len(options['uart_stop_hex'])%2:raise ValueError('RTL UART stop hex must contain whole bytes')
        try:bytes.fromhex(options['uart_stop_hex'])
        except ValueError:raise ValueError('RTL UART stop hex must contain hexadecimal bytes') from None
    if options['ram_dump'] is not None:ram_dump_range(options['ram_dump'])
    if options['block_trace'] is None:options['block_trace']=False
    if type(options['block_trace']) is not bool:raise ValueError('RTL block trace must be a boolean')
    return options

def ram_dump_range(specification):
    """A raw external-memory range; no guest data interpretation."""
    import re
    if not isinstance(specification,str) or not re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+):(?:0x[0-9a-fA-F]+|[0-9]+)',specification):
        raise ValueError('RTL RAM dump requires address:bytes')
    address,size=(int(value,16 if value.startswith('0x') else 10) for value in specification.split(':'))
    p=profile()
    if not 1<=size<=1048576 or not p['ram_base']<=address<=p['ram_base']+p['ram_bytes']-size:
        raise ValueError('RTL RAM dump must be 1..1048576 bytes inside external RAM')
    return address,size

def execute(data,workload,directory,options,inputs,medium):
    from types import SimpleNamespace
    options=bounded_options(SimpleNamespace(**options))
    entry=data['workloads'][workload]
    argv=[data['binary']['path'],'--image',entry['image']['path'],'--rom',data['rom']['path'],
          '--load',f"0x{prepared_profile(data)['dtb_base']:x}:{entry['dtb']['path']}",'--uart-output',directory/'uart.bin',
          '--trace',directory/'trace.csv','--trace-limit',options['trace_limit'],'--cycles',options['cycles'],
          '--deadline',int(options['timeout']),'--panel-output',directory/'panel','--report',directory/'host-report.json','--quiet-uart']
    for key,flag in (('uart','--uart-input'),('events','--events')):
        if inputs.get(key):argv += [flag,validate(inputs[key])]
    if workload!='service':
        if medium is None and workload not in ('power','ble','usb'):raise ValueError('RTL notebook/initializer requires --disk retained raw medium')
        argv+=['--descriptor',entry['descriptor']['path']]
        if medium is not None:argv+=['--medium',medium]
    for key,flag in (('uart_stop','--uart-stop'),('uart_stop_hex','--uart-stop-hex'),('stop_after_panel','--stop-after-panel'),('fail_flush','--fail-flush'),('observer_cycle','--observer-cycle')):
        if options[key] is not None:argv += [flag,options[key]]
    if options['ram_dump']:
        address,size=ram_dump_range(options['ram_dump']);argv+=['--ram-dump',f'{address}:{size}:{directory/"ram.bin"}']
    if options['block_trace']:argv+=['--block-trace',directory/'block.csv']
    process=None;result={'schema_version':1,'scope':'raw RTL transport; functional acceptance is separate',
        'argv':list(map(str,argv)),'status':'NOT_RUN'}
    try:
        with (directory/'run.log').open('w') as log:
            process=subprocess.Popen(list(map(str,argv)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            try:result['exit_code']=process.wait(timeout=options['timeout']+10)
            except subprocess.TimeoutExpired:
                process.kill();process.wait(timeout=5);result['exit_code']=process.returncode
                result['status']='WALL_TIMEOUT';return result
        result['status']='STOPPED_BY_PROTOCOL' if result['exit_code']==0 else 'FAILED'
        if medium is not None:result['final_medium_sha256']=sha(medium)
        result['outputs']={str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file()
            and (p.name in ('uart.bin','trace.csv','host-report.json','ram.bin','block.csv') or p.name.startswith('panel'))}
        return result
    finally:
        if process is not None and process.poll() is None:process.kill();process.wait(timeout=5)
        (directory/'output.json').write_text(json.dumps(result,indent=2)+'\n')

def capture(data,workload,directory,options,input_paths,disk):
    """Shared ordinary capture, including raw copies and exclusive medium lifetime."""
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=False)
    inputs={}
    for key,path in input_paths.items():
        if path:
            destination=directory/('input.'+key);shutil.copyfile(path,destination);inputs[key]=identified(destination)
    if workload=='service' and disk is not None:raise ValueError('RTL service workload has no block medium; omit --disk')
    if workload not in ('service','power','ble','usb') and disk is None:raise ValueError('RTL notebook/initializer requires --disk retained raw medium')
    lock=disk.open('r+b') if disk is not None else None
    try:
        if lock is not None:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        initial=None
        if disk is not None:
            initial_path=directory/'initial-medium.raw';shutil.copyfile(disk,initial_path);initial=identified(initial_path)
        identity={'schema_version':1,'transport':'lemma-silicon-events/1','profile':data['profile'],'prepared':data,
            'workload':workload,'options':options,'reset_cycles':8,'clock_hz':prepared_profile(data)['clock_hz'],'ram_initialization':'zero external RAM plus exact ELF and DTB loads',
            'inputs':inputs,'initial_medium':initial,'medium_path':str(disk) if disk else None}
        (directory/'input.json').write_text(json.dumps(identity,indent=2)+'\n')
        result=execute(data,workload,directory,options,inputs,disk)
    finally:
        if lock is not None:lock.close()
        print(f'RTL run artifacts: {directory}')
    return result


def run(args):
    workload=getattr(args,'workload',None) or 'service'
    name=getattr(args,'profile',None);p=profile(name)
    if args.geometry and args.geometry!=f"{p['geometry'][0]}x{p['geometry'][1]}":raise ValueError('RTL geometry is fixed by the selected binding')
    if args.mode!='developer':raise ValueError('lemma-silicon-dev/0.1.0 currently supports Developer mode only')
    if getattr(args,'raw_input',None) or getattr(args,'fault',None):
        raise ValueError('RTL uses --events and --fail-flush; QEMU raw-input/fault options are unsupported')
    options=bounded_options(args);data=prepared(workload,name)
    directory=args.record or ROOT/f'build/silicon/run-{time.time_ns()}'
    disk=args.disk.resolve() if args.disk else None
    result=capture(data,workload,directory,options,{'uart':args.uart_input,'events':args.events},disk)
    if result['exit_code']!=0:raise RuntimeError(f"RTL run {result['status']} ({result['exit_code']}); {directory/'run.log'}")

def replay(args):
    session=args.session.resolve();identity=json.loads((session/'input.json').read_text());original=json.loads((session/'output.json').read_text())
    if identity.get('schema_version')!=1 or identity.get('transport')!='lemma-silicon-events/1':raise ValueError('Unsupported RTL capture identity')
    if not isinstance(original.get('outputs'),dict) or not original['outputs']:
        raise ValueError('RTL capture contains no completed output inventory')
    for name,digest in original['outputs'].items():
        output=session/name
        if output.resolve().parent!=session or not output.is_file() or sha(output)!=digest:
            raise ValueError('RTL capture output changed or missing: '+name)
    data=identity['prepared'];workload=identity['workload']
    # Validate the captured immutable executable and guest, independently of a
    # newly selected default. No captured result substitutes for execution.
    for key in ('binary','rom','rom_audit','rtl_build'):validate(data[key])
    if data['profile']==USB_CLOCKED_PROFILE_NAME:validate_clocked_capture_authority(data,workload)
    for key,item in data['workloads'][workload].items():
        if data['profile']==USB_CLOCKED_PROFILE_NAME and key=='guest_source_archive':continue
        validate(item)
    if data['profile']!=USB_CLOCKED_PROFILE_NAME:
        for path,digest in data['rtl_sources'].items():
            if not Path(path).is_file() or sha(path)!=digest:raise ValueError('Captured RTL source/dependency changed: '+path)
        if data['profile_sha256']!=sha(profile_path(data['profile'])):raise ValueError('Captured RTL binding is no longer supported by this generator')
    inputs=identity['inputs']
    for item in inputs.values():validate(item)
    directory=ROOT/f'build/silicon/replay-{time.time_ns()}'
    disk=None
    if identity['initial_medium'] is not None:
        initial=validate(identity['initial_medium']);disk=args.disk_copy.resolve()
        if disk.exists():raise ValueError('RTL replay --disk-copy must be new')
        disk.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(initial,disk)
    options=dict(identity['options']);options['timeout']=args.timeout
    # The captured immutable executable is retained; ordinary capture supplies
    # fresh raw-input/reset identities, initial bytes and an exclusive lock.
    result=capture(data,workload,directory,options,
                   {key:validate(item) for key,item in inputs.items()},disk)
    compared={key:result.get(key)==original.get(key) for key in ('exit_code','outputs','final_medium_sha256')}
    (directory/'comparison.json').write_text(json.dumps({'status':'MATCH' if all(compared.values()) else 'MISMATCH',
        'compared':compared,'scope':'same RTL backend replay only; no instruction-schedule equivalence with QEMU'},indent=2)+'\n')
    if not all(compared.values()):raise RuntimeError('RTL replay outputs differ: '+str(directory))
    if result['exit_code']!=0:raise RuntimeError('RTL replay regenerated the original failure: '+str(directory))
    print('RTL external-input replay matched actual UART/panel/medium outputs: '+str(directory))
