#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact0.14 QEMU-only source/runtime archive; no new execution/physical claims."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import shutil

PROFILE='lemma-silicon-dev/0.14.0'
SCHEMA='lemmasim-native-multimodal-fast/1'
CONFIGURATIONS={'notebook':'lemmasim-silicon-multimodal-notebook',
                'initializer':'lemmasim-silicon-multimodal-initialize'}
SCHOOL={'notebook':'lemmasim-silicon-school-notebook','initializer':'lemmasim-silicon-school-initialize'}
SCHOOL_SAMPLE_SHA='3f1900b5ede7a4197086dc6cb30176e66fb75ac24aaee68f8cabcf689bb1093e'
LEGACY_CONTROLS=('scripts/lemmasim','scripts/lemmasim_fast.py','scripts/lemmasim_session.py','scripts/silicon_guest_bundle.py','scripts/multimodal_native_bundle.py')
SCHOOL_CONTROLS=LEGACY_CONTROLS+('scripts/lemmasim_school_service.py','scripts/lemmasim_course.py','scripts/lemmasim_tutor.py','scripts/lemmasim_school_panel.py')
PARAMETERIZED={'parameterized-notebook':'lemmasim-silicon-multimodal-parameterized-notebook','parameterized-initializer':'lemmasim-silicon-multimodal-parameterized-initialize'}

def _modules():
    import silicon_guest as guest
    import silicon_guest_bundle as bundle
    import lemmasim_fast as fast
    return guest,bundle,fast

def _origin_destination(manifest,path,digest):
    """Resolve exact origins within this successor schema only."""
    if manifest.get('schema')!=SCHEMA:raise ValueError('Unsupported multimodal origin schema')
    origins=manifest.get('origins')
    entry=origins.get(str(Path(path).resolve())) if isinstance(origins,dict) else None
    destination=entry.get(digest) if isinstance(entry,dict) else None
    files=manifest.get('files')
    if (not isinstance(files,dict) or not isinstance(destination,str) or
            destination not in files or files[destination].get('sha256')!=digest):
        raise ValueError('Archived consumed multimodal input differs: '+str(path))
    return destination


def pack(args):
    guest,bundle,fast=_modules()
    from build_kernel import source_inputs
    from silicon_profile import profile_path
    school=bool(getattr(args,'school_deployment',False))
    conflicts=('base_bundle','refresh_fast','expected_fast_sha256','rtl_build','rtl_source_root',
            'usb_recovery_deployment','usb_closure_recovery_deployment','usb_package_recovery_deployment',
            'usb_package_entry2_deployment','usb_companion_reader_deployment')
    if not school:conflicts+=('notebook_build','initializer_build','guest_source_root','initializer_guest_source_root')
    if args.profile!=PROFILE or any(getattr(args,k,None) for k in conflicts):
        raise ValueError('Multimodal fast archive requires the exact current prepared pair; no replacements or RTL claim')
    source_root=guest.ROOT
    if school:
        if any(getattr(args,key,None) is None for key in ('notebook_build','initializer_build','guest_source_root')):
            raise ValueError('School23/v2 archive requires explicit audited notebook/initializer builds and complete original guest source root')
        source_root=Path(args.guest_source_root).resolve()
        other=Path(getattr(args,'initializer_guest_source_root',None) or source_root).resolve()
        sources=source_inputs(source_root)
        if source_inputs(other)!=sources:raise ValueError('School23/v2 initializer source inventory differs')
        data=copy.deepcopy(bundle.read_json(fast.prepared_path(PROFILE)))
        if (data.get('schema')!='lemmasim-fast-prepared/1' or data.get('profile')!=PROFILE or
            data.get('profile_sha256')!=guest.sha(profile_path(PROFILE)) or data.get('sources')!=fast.sources(PROFILE) or
            data.get('cpu')!=fast.CPU or data.get('icount_shift')!=3):
            raise ValueError('School23/v2 archive requires current prepared QEMU runtime sources')
        for key in ('qemu','derivation'):guest.validate(data[key])
        fast.validate_checkpoint_binding(data)
        selected=dict(SCHOOL);data['workloads']={};data.pop('guest_archive',None)
        data.pop('guest_source_root',None)
        for role in selected:
            base=Path(getattr(args,role+'_build')).resolve()
            guest.verify_guest_build(base,selected[role],bundle.read_json(base/'build.json')['optimization'],source_root=source_root)
            # The complete original archive validator also rejects extra, missing,
            # symlinked or tool-mismatched inputs before copying anything.
            bundle._audited_guest_archive(base,source_root,selected[role],'lemma-school-guest-source-archive/1',
                'actual School23/v2 audited source/tool/object closure; packaging is not execution')
            data['workloads'][role]={k:guest.identified(base/name) for k,name in
                [('image','image.elf'),('build','build.json'),('provenance','provenance.json'),
                 ('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin')]}
    else:
        prepared={role:fast.prepared(role,PROFILE) for role in CONFIGURATIONS}
        available=set(prepared['notebook'].get('workloads',{}))
        if available&set(PARAMETERIZED):
            if not set(PARAMETERIZED)<=available:raise ValueError('Parameterized archive requires the complete parameterized pair')
            prepared.update({role:fast.prepared(role,PROFILE) for role in PARAMETERIZED})
        selected={**CONFIGURATIONS,**(PARAMETERIZED if set(PARAMETERIZED)<=available else {})}
        data=copy.deepcopy(prepared['notebook'])
        for role,item in prepared.items():
            if any(item.get(k)!=data.get(k) for k in ('schema','profile','profile_sha256','qemu','derivation','sources','cpu','icount_shift','checkpoint_binding')):
                raise ValueError('Multimodal fast guest roles have different runtime/source identities')
            data['workloads'][role]=copy.deepcopy(item['workloads'][role])
        if set(data['workloads'])!=set(selected):raise ValueError('Multimodal fast archive requires complete ordinary pair')
        sources=source_inputs(source_root)
        for role,entry in data['workloads'].items():
            base=Path(entry['build']['path']).parent
            guest.verify_guest_build(base,selected[role],bundle.read_json(base/'build.json')['optimization'])
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    manifest={'schema':SCHEMA,'profile':PROFILE,'boot':'ELF-preload development',
              'scope':('audited School23/v2 guest pair and exact QEMU source/runtime archive; packaging is not execution or physical qualification' if school else 'unchanged fully audited ordinary0.14 guest pair and exact QEMU source/runtime archive; no RTL,checkpoint,realtime,physical or educational qualification'),
              'configurations':selected,'sources':sources,'source_commit':bundle.read_json(Path(data['workloads']['notebook']['provenance']['path']))['source_commit'],
              'host_controls':{name:guest.sha(guest.ROOT/name) for name in (SCHOOL_CONTROLS if school else LEGACY_CONTROLS)},
              'origins':{},'host_dependencies':{'qemu':bundle.host_dependencies(data['qemu']['path'])},'backends':{}}
    def add(original,name,expected=None,executable=False):
        original=Path(original).resolve();h=guest.sha(original)
        if expected is not None and h!=expected:raise ValueError('Archive consumed input changed: '+str(original))
        dest=out/name
        if dest.exists():
            if guest.sha(dest)!=h:raise ValueError('Conflicting archive destination')
        else:
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,dest);dest.chmod(0o755 if executable else 0o644)
        manifest['origins'].setdefault(str(original),{})[h]=name
        return {'path':name,'sha256':h}
    for name,h in manifest['host_controls'].items():add(guest.ROOT/name,'controls/'+name,h)
    for name,h in sources.items():add(source_root/name,'source/'+name,h)
    (out/'source/source-inputs.json').write_text(json.dumps(sources,indent=2)+'\n')
    for name,h in data['sources'].items():add(guest.ROOT/name,'backend-sources/'+name,h)
    add(profile_path(PROFILE),'backend-sources/'+str(profile_path(PROFILE).relative_to(guest.ROOT)),data['profile_sha256'])
    for role,entry in data['workloads'].items():
        base=Path(entry['build']['path']).parent
        for name,h in bundle.read_json(base/'provenance.json')['artifacts'].items():add(base/name,'workloads/'+role+'/'+name,h)
        for key,item in list(entry.items()):entry[key]=add(item['path'],'workloads/'+role+'/'+Path(item['path']).name,item['sha256'])
    for key in ('qemu','derivation'):
        item=data[key];data[key]=add(item['path'],'runtime/qemu/'+Path(item['path']).name,item['sha256'],key=='qemu')
    manifest['backends']['qemu']=data
    if school:
        from school_deployment import software_deployment_for
        manifest['software_deployment']=software_deployment_for(SCHOOL['notebook'])
        manifest['school_service_contract']='lemma-school-native-service/1'
    if getattr(args,'sample_course',None) is not None:
        from course_package import decode
        original=Path(args.sample_course).resolve();image=original.read_bytes()
        if len(image)!=4199 or guest.sha(original)!=SCHOOL_SAMPLE_SHA:
            raise ValueError('Account-free sample must be the exact compiled canonical local sample')
        decode(image)
        manifest['sample_course']=add(original,'sample.lcp',SCHOOL_SAMPLE_SHA)
    (out/'DEPENDENCIES.txt').write_text('Local development archive only. QEMU11.1.1 GPL-2.0-or-later. Exact external Nix host loader/libraries and pinned Lean source/tools remain required. Project-wide redistribution rights unresolved. No current compilation or execution claim. Profile0.14 checkpoint unsupported. No physical output authorization.\n')
    if sources!=source_inputs(source_root) or data['sources']!=fast.sources(PROFILE):raise ValueError('Consumed source changed while packing')
    manifest['files']={str(p.relative_to(out)):{'sha256':guest.sha(p),'bytes':p.stat().st_size,'executable':os.access(p,os.X_OK)} for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for role in selected:prepared_archive(out,'qemu',role,PROFILE)
    print(out/'bundle.json')
    return out/'bundle.json'

def prepared_archive(directory,backend,workload,name=None):
    guest,bundle,fast=_modules()
    from build_kernel import source_inputs
    from silicon_profile import profile_path
    directory=Path(directory).resolve();m=bundle.read_json(directory/'bundle.json')
    if m.get('schema')!=SCHEMA or m.get('profile')!=PROFILE or name not in (None,PROFILE) or backend!='qemu' or workload not in {**CONFIGURATIONS,**PARAMETERIZED,**SCHOOL}:
        raise ValueError('Multimodal native archive requires exact0.14 ordinary QEMU role')
    selected=m.get('configurations')
    if selected not in (CONFIGURATIONS,{**CONFIGURATIONS,**PARAMETERIZED},SCHOOL) or workload not in selected:raise ValueError('Multimodal immutable deployment pair differs')
    bundle.inventory(directory,m)
    school=selected==SCHOOL
    if school:
        from school_deployment import software_deployment_for
        if (m.get('software_deployment')!=software_deployment_for(SCHOOL['notebook']) or
            m.get('school_service_contract')!='lemma-school-native-service/1'):
            raise ValueError('School23/v2 software/service contract differs')
    elif 'software_deployment' in m or 'school_service_contract' in m:
        raise ValueError('Legacy multimodal archive acquired school deployment authority')
    sample=m.get('sample_course')
    if sample is not None:
        if (sample!={'path':'sample.lcp','sha256':SCHOOL_SAMPLE_SHA} or
            m.get('files',{}).get('sample.lcp',{}).get('sha256')!=SCHOOL_SAMPLE_SHA or
            (directory/'sample.lcp').stat().st_size!=4199):
            raise ValueError('Account-free sample descriptor differs from exact inventoried compiled sample')
    controls=m.get('host_controls')
    required=SCHOOL_CONTROLS if school else LEGACY_CONTROLS
    if not isinstance(controls,dict) or set(controls)!=set(required):raise ValueError('Archived host control inventory differs')
    for path,h in controls.items():_origin_destination(m,guest.ROOT/path,h)
    root=directory/'source'
    if source_inputs(root)!=m.get('sources') or bundle.read_json(root/'source-inputs.json')!=m['sources']:
        raise ValueError('Multimodal archive complete target source closure differs')
    if set(m.get('backends',{}))!={'qemu'}:raise ValueError('Multimodal fast archive acquired another backend')
    data=copy.deepcopy(m['backends']['qemu'])
    if data.get('schema')!='lemmasim-fast-prepared/1' or data.get('profile')!=PROFILE or data.get('cpu')!=fast.CPU or data.get('icount_shift')!=3:
        raise ValueError('Multimodal fast execution contract differs')
    fast.validate_checkpoint_binding(data)
    if data.get('profile_sha256')!=guest.sha(profile_path(PROFILE)):
        raise ValueError('Archived0.14 binding differs from its retained version')
    _origin_destination(m,profile_path(PROFILE),data['profile_sha256'])
    for path,h in data.get('sources',{}).items():_origin_destination(m,guest.ROOT/path,h)
    if not data.get('sources'):raise ValueError('Missing archived fast source closure')
    def absolute(item):
        if not isinstance(item,dict) or set(item)!={'path','sha256'} or item['path'] not in m['files'] or m['files'][item['path']]['sha256']!=item['sha256']:
            raise ValueError('Prepared multimodal metadata contradicts inventory')
        return {'path':str(directory/item['path']),'sha256':item['sha256']}
    deps=m.get('host_dependencies',{}).get('qemu')
    if not isinstance(deps,dict) or not deps:raise ValueError('Missing exact host runtime libraries')
    for path,h in deps.items():
        if not path.startswith('/nix/store/') or not Path(path).is_file() or guest.sha(path)!=h:raise ValueError('Exact host runtime library missing/changed')
    for key in ('qemu','derivation'):data[key]=absolute(data[key])
    if set(data['workloads'])!=set(selected):raise ValueError('Incomplete multimodal pair')
    for role,entry in data['workloads'].items():
        data['workloads'][role]={k:absolute(item) for k,item in entry.items()}
        base=Path(data['workloads'][role]['build']['path']).parent
        bundle._audited_guest_archive(base,root,selected[role],
            'lemma-school-guest-source-archive/1' if school else 'lemma-multimodal-guest-source-archive/1',
            'audited School23/v2 '+role+' complete source/tool/object closure' if school else
            'unchanged fully audited ordinary0.14 '+role+' complete source/tool/object closure')
    data['native_bundle']={'schema':SCHEMA,'path':str(directory),'manifest_sha256':guest.sha(directory/'bundle.json'),
                           'source_commit':m['source_commit'],'scope':m['scope']}
    return data
