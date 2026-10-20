#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepared matched-profile QEMU and lifecycle transport; no guest policy."""
from __future__ import annotations
import copy
import hashlib
import struct
import json
import os
import re
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import tempfile

from silicon_profile import profile, profile_path
import silicon_guest as guest
from lemmasim_session import digest, write_json, ROOT, MAX_REQUEST, external_command

CPU = 'rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0'
ADAPTER = 'lemmasim-fast-adapter/4'
RAW_UART_ADAPTER = 'lemmasim-fast-adapter/5'
RAW_UART_FLOW_ADAPTER = 'lemmasim-fast-adapter/6'
MAX_NS = (1 << 63) - 1
CLOCK_SCHEMA = 'lemmasim-fast-clock/1'
LOGICAL2_BINDING = 'lemma-silicon-fast-softtlb/0.2.0'
MM2_BINDING = 'lemma-silicon-fast-mm2-subset/0.1.0'
OPTICAL_BINDING = 'lemma-optical17-functional-mm2/1'
MM2_CHECKPOINT_BINDING = 'lemma-silicon-fast-mm2-softtlb/0.1.0'
MM2_CHECKPOINT_CONTRACT = 'lemma-native-mm2-continuation/1'
# Explicit same-backend/local-backing admission; archived false flags remain
# false. The unqualified cancelled held-read capture is still rejected below.
MM2_CHECKPOINT_ADMITTED = True
MM2_CACHE_SEED = '/nix/store/1nirimaaikhpbkf7af763zp3fj8yg6z2-lemmasim-qemu-raw-uart-logical-v2-retained-11.1.1'
# Admitted only for the explicitly selected version2 binding/local backing.
# Current guest DMA, PCM, storage, unknown work and Session transaction cases
# are indexed in docs/evidence/009-integrated-machine.html.
LOGICAL2_CHECKPOINT_ADMITTED = True
LOGICAL2_CACHE_SEED = '/nix/store/1nqjws03faak74p8f8y781s779rfklq1-lemmasim-qemu-raw-uart-logical-v2-retained-11.1.1'
LOGICAL2_NORMAL_REFERENCE = '/nix/store/fz255cis6w7pzd7kv6g6klb3w7fr9i2l-lemmasim-qemu-raw-uart-v1-11.1.1'


def logical2_selected(name):
    value=os.environ.get('LEMMA_FAST_LOGICAL2','')
    cached=os.environ.get('LEMMA_FAST_LOGICAL2_CACHE','')
    if value not in ('','1') or cached not in ('','1'):
        raise ValueError('Logical2 selections admit only the explicit value1')
    if cached and not value:raise ValueError('Logical2 retained cache requires explicit logical2 selection')
    if value and (profile(name)['profile']!='lemma-silicon-dev/0.14.0' or not raw_uart_selected(name)):
        raise ValueError('Logical2 requires explicit rawUART and exactFast0.14')
    return value=='1'


def mm2_selected(name):
    value=os.environ.get('LEMMA_FAST_MM2','')
    if value not in ('','1'):raise ValueError('MM2 subset selection admits only explicit value1')
    if value and (profile(name)['profile']!='lemma-silicon-dev/0.14.0' or not logical2_selected(name)):
        raise ValueError('MM2 functional subset requires explicit rawUART logical engine and Fast0.14')
    return value=='1'


def mm2_checkpoint_selected(name):
    value=os.environ.get('LEMMA_FAST_MM2_CHECKPOINT','')
    if value not in ('','1'):raise ValueError('MM2 checkpoint selection admits only explicit value1')
    if value and not mm2_selected(name):raise ValueError('MM2 continuation requires the explicit MM2 controller subset')
    return value=='1'


def validate_mm2_checkpoint_cut(state):
    """Bound public continuation to qualified controller cuts, without running it."""
    ring=state.get('ring') if isinstance(state,dict) else None
    if (not isinstance(state,dict) or state.get('controller_abi')!=2 or not isinstance(ring,dict) or
            type(ring.get('held_kind')) is not int or ring['held_kind'] not in (0,1,2) or
            type(ring.get('held_cancel')) is not int or ring['held_cancel'] not in (0,1)):
        raise ValueError('MM2 checkpoint requires a complete current held-read observation')
    if ring['held_cancel']:
        raise ValueError('MM2 cancelled held-read checkpoint boundary remains unsupported; retry after its acknowledgement')


def validate_execution_binding(data):
    value=data.get('execution_binding')
    if (data.get('profile')=='lemma-silicon-dev/0.17.0' or
            any(k in data for k in ('optical_controller_abi','optical_frame_contract')) or value==OPTICAL_BINDING):
        required={'sim/host/lemma_optical.c','sim/host/lemma_optical.h',
                  'sim/host/lemma_optical_qemu.inc.c','tooling/lemmasim/patch_optical.py',
                  'sim/profiles/lemma-silicon-dev-0.17.0.json','sim/host/lemma_multimodal_v2.c'}
        sources=data.get('sources')
        if (data.get('profile')!='lemma-silicon-dev/0.17.0' or value!=OPTICAL_BINDING or
                type(data.get('optical_controller_abi')) is not int or data.get('optical_controller_abi')!=1 or
                data.get('optical_frame_contract')!='lemma-optical-frame/1' or
                type(data.get('multimodal_controller_abi')) is not int or data.get('multimodal_controller_abi')!=2 or
                data.get('controller_contract')!='lemma-multimodal-converter/2' or
                data.get('checkpoint_binding') is not None or ('checkpoint_admitted' in data and data['checkpoint_admitted'] is not False) or
                not isinstance(sources,dict) or not required.issubset(sources) or
                any(not isinstance(sources[k],str) or re.fullmatch('[0-9a-f]{64}',sources[k]) is None for k in required)):
            raise ValueError('Unsupported optical17 functional/controller/source authority')
        return True
    if value is None:
        if any(k in data for k in ('multimodal_controller_abi','controller_contract')):
            raise ValueError('Unbound controller extension metadata')
        if any(k in data for k in ('checkpoint_contract','observation_relation','checkpoint_admitted')):
            raise ValueError('Unbound MM2 continuation metadata')
        return False
    if (value!=MM2_BINDING or data.get('profile')!='lemma-silicon-dev/0.14.0' or
            data.get('multimodal_controller_abi')!=2 or data.get('controller_contract')!='lemma-multimodal-converter/2' or
            data.get('checkpoint_binding') not in (None,MM2_CHECKPOINT_BINDING) or 'sim/host/lemma_multimodal_v2.c' not in data.get('sources',{})):
        raise ValueError('Unsupported MM2 subset/controller/source authority')
    if data.get('checkpoint_binding') is not None:
        if (data.get('checkpoint_contract')!=MM2_CHECKPOINT_CONTRACT or
                data.get('observation_relation')!='lemma-native-MM2-logical-observation-relation/3' or
                type(data.get('checkpoint_admitted')) is not bool or
                'tooling/lemmasim/patch_soft_tlb2.py' not in data.get('sources',{}) or
                (data['checkpoint_admitted'] and 'scripts/native_logical_relation.py' not in data.get('sources',{}))):
            raise ValueError('Unsupported MM2 continuation contract/source authority')
    elif any(k in data for k in ('checkpoint_contract','observation_relation','checkpoint_admitted')):
        raise ValueError('Unbound MM2 continuation metadata')
    return True


def validate_checkpoint_binding(data):
    # True selects the logical sidecar engine, not permission to export state.
    # The independent public admission check also requires the qualified flag.
    version=data.get('school_notebook_version',23)
    from school_deployment import configuration_for
    configuration_for(version,'notebook')
    if version in (24,25) and data.get('checkpoint_binding') is not None:
        raise ValueError(f'School{version} prepared local-tool IPC continuation is not qualified; use regular MM2 and durable cold recovery')
    if validate_execution_binding(data):return data.get('checkpoint_binding')==MM2_CHECKPOINT_BINDING
    binding=data.get('checkpoint_binding')
    if binding is None:return False
    if (binding!=LOGICAL2_BINDING or data.get('profile')!='lemma-silicon-dev/0.14.0' or
            'tooling/lemmasim/patch_soft_tlb2.py' not in data.get('sources',{})):
        raise ValueError('Unsupported native logical checkpoint binding/source authority')
    return True



def read_clock(path):
    """Validate wrapper state before exposing any candidate VM to restore."""
    path = Path(path)
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 256:
        raise ValueError('Missing or oversized fast clock state')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('Duplicate fast clock field')
            value[key] = item
        return value
    value = json.loads(path.read_bytes(), object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {'schema', 'time_origin_ns'} or value['schema'] != CLOCK_SCHEMA:
        raise ValueError('Unsupported fast clock state')
    origin = value['time_origin_ns']
    if type(origin) is not int or not 0 <= origin <= MAX_NS:
        raise ValueError('Fast clock origin exceeds its bound')
    return origin


def raw_uart_selected(name):
    value = os.environ.get('LEMMA_FAST_RAW_UART', '')
    if value not in ('', '1'):
        raise ValueError('LEMMA_FAST_RAW_UART admits only the explicit value1')
    if value and profile(name)['profile'] not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.14.0'):
        raise ValueError('Raw UART backend1 requires canonical0.3 or multimodal0.14')
    return value == '1'


def qemu_recipe(name):
    if mm2_selected(name):return ROOT/'tooling/lemmasim/qemu_mm2_reuse.nix'
    if logical2_selected(name) and os.environ.get('LEMMA_FAST_LOGICAL2_CACHE')=='1':
        return ROOT/'tooling/lemmasim/qemu_logical2_reuse.nix'
    return ROOT / ('tooling/lemmasim/qemu_uart.nix' if raw_uart_selected(name)
                   else 'tooling/lemmasim/qemu.nix')


def prepared_path(name=None):
    version = profile(name)['profile'].split('/')[1]
    prefix = ('fast-uart1-mm2' if mm2_selected(name) else 'fast-uart1-logical2' if logical2_selected(name) else 'fast-uart1') if raw_uart_selected(name) else 'fast'
    if mm2_checkpoint_selected(name):prefix+='-logical2'
    return ROOT / f'build/lemmasim/{prefix}-prepared-{version}.json'


def sources(name):
    paths = [ROOT/'tooling/lemmasim/qemu.nix', ROOT/'tooling/lemmasim/apply_qemu.py',
             ROOT/'flake.lock', profile_path(name)]
    if raw_uart_selected(name):
        paths += [qemu_recipe(name), ROOT/'tooling/lemmasim/patch_uart_ingress.py',
                  ROOT/'tooling/lemmasim/uart_build_budget.py']
    if logical2_selected(name):
        paths += [ROOT/'tooling/lemmasim'/name for name in (
            'patch_soft_tlb.py','patch_soft_tlb2.py','patch_multimodal_checkpoint.py',
            'patch_logical2_lifecycle.py','qemu_uart.nix','qemu_logical2_reuse.nix',
            'native_logical2_reuse.py')]
        paths.append(ROOT/'docs/contracts/009-qemu-logical-softtlb-v2.html')
    if profile(name)['profile'] in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.4.0','lemma-silicon-dev/0.14.0'):
        paths.append(ROOT/'tooling/lemmasim/patch_counter_clock.py')
    if profile(name)['profile']=='lemma-silicon-dev/0.4.0':paths += [ROOT/'tooling/lemmasim/patch_power_safety.py',ROOT/'scripts/silicon_power_guest_archive.py']
    paths += sorted(p for p in (ROOT/'sim/host').glob('*') if p.is_file())
    paths += sorted(p for p in (ROOT/'sim/companion').glob('backing_*') if p.is_file())
    if mm2_selected(name):paths += [ROOT/'tooling/lemmasim'/n for n in ('qemu_mm2_reuse.nix','native_mm2_reuse.py','patch_multimodal_v2.py')];paths.append(ROOT/'docs/contracts/009-multimodal-pcm-ring-v1.html')
    if mm2_checkpoint_selected(name):paths += [ROOT/'docs/contracts/009-native-mm2-continuation-v1.html',ROOT/'scripts/native_logical_relation.py']
    return {str(p.relative_to(ROOT)): digest(p) for p in paths}

def workload_configurations(name,school_notebook_version=23):
    from school_deployment import configuration_for
    configuration_for(school_notebook_version,'notebook')
    selected=guest.configurations(name)
    if school_notebook_version in (24,25):
        if name!='lemma-silicon-dev/0.14.0':raise ValueError('School24/25 Fast preparation requires0.14')
        selected={**selected,'school-notebook':configuration_for(school_notebook_version,'notebook'),
                  'school-initializer':configuration_for(school_notebook_version,'initialize')}
    return selected


def build(args):
    name = profile(args.profile)['profile']
    if name in ('lemma-silicon-dev/0.15.0','lemma-silicon-dev/0.16.0'):
        raise ValueError('Integrated0.15 requires canonical RTL/native or RTL/Wasm; fast BootNV/clockedUSB/power-v2 models are not implemented')
    version=getattr(args,'school_notebook_version',23)
    selected = workload_configurations(name,version)
    workload = args.workload or 'notebook'
    if version in (24,25) and (mm2_checkpoint_selected(name) or (logical2_selected(name) and not mm2_selected(name))):
        raise ValueError('School24/25 prepared local-tool IPC continuation is not qualified; use regular MM2 and durable cold recovery')
    if version in (24,25) and workload not in ('school-notebook','school-initializer'):
        raise ValueError('School24/25 preparation requires an explicit School workload')
    if workload not in selected:
        raise ValueError('Workload is not admitted by this binding')
    source_root = Path(getattr(args,'guest_source_root',None) or ROOT).resolve()
    if source_root != ROOT and (name != 'lemma-silicon-dev/0.14.0' or workload not in ('school-notebook','school-initializer') or not args.guest_build):
        raise ValueError('Archived Fast sources require explicit School23/v2 audited0.14 guest')
    archived=None
    archive_path=getattr(args,'guest_bundle',None)
    if archive_path is not None:
        if args.guest_build is not None or name not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.4.0'):raise ValueError('Archived guest requires qualified binding without --guest-build')
        archived=archived_guest(archive_path,workload,name)
        archived_build=json.loads(Path(archived['workloads'][workload]['build']['path']).read_text())
        if archived_build['optimization']!=args.opt_level:raise ValueError('Archived guest optimization differs')
    link = ROOT / ('build/lemmasim/qemu-fast-' + (('uart1-mm2-' if mm2_selected(name) else 'uart1-logical2-' if logical2_selected(name) else 'uart1-') if raw_uart_selected(name) else '') + name.split('/')[1])
    recipe = qemu_recipe(name)
    before = sources(name)
    limits = ['--cores', '2', '--max-jobs', '1', '--builders', ''] if raw_uart_selected(name) else []
    runtime_arguments=[];runtime_expression=''
    if mm2_selected(name):
        if not Path(MM2_CACHE_SEED).is_dir():raise ValueError('Exact qualified MM2 retained seed is absent')
        runtime_arguments=['--arg','seed','builtins.storePath '+json.dumps(MM2_CACHE_SEED)]
        runtime_expression=' seed = builtins.storePath '+json.dumps(MM2_CACHE_SEED)+';'
    elif logical2_selected(name):
        if os.environ.get('LEMMA_FAST_LOGICAL2_CACHE')=='1':
            if not all(Path(p).is_dir() for p in (LOGICAL2_CACHE_SEED,LOGICAL2_NORMAL_REFERENCE)):
                raise ValueError('Qualified local logical2 cache is absent; unsetLEMMA_FAST_LOGICAL2_CACHE for the maintained cold build')
            for key,path in [('seed',LOGICAL2_CACHE_SEED),('normalReference',LOGICAL2_NORMAL_REFERENCE)]:
                runtime_arguments+=['--arg',key,'builtins.storePath '+json.dumps(path)]
                runtime_expression+=' '+key+' = builtins.storePath '+json.dumps(path)+';'
        else:
            runtime_arguments=['--arg','logicalSoftTlb','true']
            runtime_expression=' logicalSoftTlb = true;'
    guest.run_command(['nix-build', recipe, *limits, '--arg', 'siliconProfile',
                       profile_path(name), *runtime_arguments, '-o', link], timeout=2400)
    binary = link.resolve()/'bin/qemu-system-riscv64'
    expression = 'let q = import (builtins.toPath ' + json.dumps(str(recipe)) + ') { siliconProfile = builtins.path { path = builtins.toPath ' + json.dumps(str(profile_path(name))) + '; };'+runtime_expression+' }; in { output = q.outPath; derivation = q.drvPath; }'
    evaluated = subprocess.run(['nix-instantiate', '--eval', '--strict', '--json', '--expr', expression],
                               cwd=ROOT, capture_output=True, text=True, timeout=120, check=True)
    closure = json.loads(evaluated.stdout)
    if binary != Path(closure['output'])/'bin/qemu-system-riscv64' or sources(name) != before:
        raise ValueError('Fast backend sources/output changed during preparation')
    directory = ROOT / ('build/kernel/fast-' + workload + '-' + str(time.time_ns()))
    if archived is not None:
        entry=copy.deepcopy(archived['workloads'][workload])
    elif args.guest_build:
        directory = args.guest_build.resolve()
    else:
        guest_command=['nix','develop','--no-write-lock-file','--command','python3','scripts/build_kernel.py',
                           '--configuration',selected[workload],'--stage','supervisor','--opt-level',args.opt_level,
                           '--output-dir',directory,'--timeout','300']
        if getattr(args,'fresh',False):guest_command+=['--fresh']
        if getattr(args,'cache_dir',None) is not None:guest_command+=['--cache-dir',args.cache_dir]
        guest.run_command(guest_command, timeout=1500)
        guest.run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/audit_kernel.py',directory],timeout=600)
    if archived is None:
        guest.verify_guest_build(directory, selected[workload], args.opt_level, source_root=source_root)
        if source_root != ROOT:
            from silicon_guest_bundle import _audited_guest_archive
            _audited_guest_archive(directory,source_root,selected[workload],
                'lemma-school-guest-source-archive/1',
                'actual audited frozen School23/v2 source; current runtime preparation is not target compilation')
        entry = {k: guest.identified(directory/p) for k,p in
                 [('image','image.elf'),('build','build.json'),('provenance','provenance.json'),
                  ('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin')]}
    data = {'schema':'lemmasim-fast-prepared/1','profile':name,'profile_sha256':digest(profile_path(name)),
            'qemu':guest.identified(binary),'derivation':guest.identified(closure['derivation']),
            'sources':before,'cpu':CPU,'icount_shift':3,'workloads':{workload:entry},
            'boot':'ELF-preload development; QEMU reset-ROM handoff to identical Lean guest ELF and supplied DTB'}
    if version in (24,25):data['school_notebook_version']=version
    if mm2_selected(name):
        data.update(execution_binding=MM2_BINDING,multimodal_controller_abi=2,controller_contract='lemma-multimodal-converter/2')
        if mm2_checkpoint_selected(name):
            data.update(checkpoint_binding=MM2_CHECKPOINT_BINDING,checkpoint_contract=MM2_CHECKPOINT_CONTRACT,
                        observation_relation='lemma-native-MM2-logical-observation-relation/3',checkpoint_admitted=MM2_CHECKPOINT_ADMITTED)
    elif logical2_selected(name):data['checkpoint_binding']=LOGICAL2_BINDING
    if source_root != ROOT:
        from build_kernel import source_inputs
        data['guest_source_root']={'path':str(source_root),'sources':source_inputs(source_root)}
    if archived is not None:
        data['guest_archive']={'path':str(Path(archive_path).resolve()),'manifest_sha256':digest(archive_manifest(archive_path,name)),
                               'scope':'unchanged archived genuine guest; new backend, not fresh target compilation'}
        validate_archived_entry(data,workload)
    path = prepared_path(name)
    try:
        previous = json.loads(path.read_text())
        if previous.get('guest_archive')==data.get('guest_archive') and previous.get('guest_source_root')==data.get('guest_source_root') and all(previous.get(k) == data.get(k) for k in ('schema','profile','profile_sha256','qemu','derivation','sources','cpu','icount_shift','checkpoint_binding','checkpoint_contract','observation_relation','checkpoint_admitted','execution_binding','multimodal_controller_abi','controller_contract','school_notebook_version')):
            for key, old in previous['workloads'].items():
                if key == workload or key not in selected: continue
                try:
                    for item in old.values(): guest.validate(item)
                    if archived is not None:validate_archived_entry(previous,key)
                    else:
                        old_dir = Path(old['build']['path']).parent
                        guest.verify_guest_build(old_dir,selected[key],json.loads((old_dir/'build.json').read_text())['optimization'],source_root=source_root)
                    data['workloads'][key] = old
                except (ValueError,KeyError,OSError): pass
    except FileNotFoundError: pass
    path.parent.mkdir(parents=True,exist_ok=True)
    write_json(path,data)
    print(f'Prepared matched fast {workload}: {path}')


def archive_manifest(path,name):
    return Path(path)/('archive.json' if name=='lemma-silicon-dev/0.4.0' else 'bundle.json')

def archived_guest(path,workload,name):
    if name=='lemma-silicon-dev/0.4.0':
        import silicon_power_guest_archive
        return silicon_power_guest_archive.prepared(path,workload,name)
    import silicon_guest_bundle
    return silicon_guest_bundle.prepared(path,'qemu',workload,name)

def validate_archived_entry(data,workload):
    archive=data.get('guest_archive')
    if not isinstance(archive,dict) or set(archive)!={'path','manifest_sha256','scope'} or archive['scope']!='unchanged archived genuine guest; new backend, not fresh target compilation':
        raise ValueError('Malformed archived guest preparation')
    path=Path(archive['path']).resolve()
    if digest(archive_manifest(path,data['profile']))!=archive['manifest_sha256']:raise ValueError('Archived guest manifest changed')
    archived=archived_guest(path,workload,data['profile'])
    if data['workloads'][workload]!=archived['workloads'][workload]:raise ValueError('Guest artifacts differ from validated archived closure')


def prepared(workload,name=None):
    name = profile(name)['profile']
    data = json.loads(prepared_path(name).read_text())
    version=data.get('school_notebook_version',23)
    selected=workload_configurations(name,version)
    if version in (24,25) and workload not in ('school-notebook','school-initializer'):
        raise ValueError('School24/25 preparation contains a non-School workload')
    if data.get('schema') != 'lemmasim-fast-prepared/1' or data.get('profile') != name or data.get('profile_sha256') != digest(profile_path(name)):
        raise ValueError('Unsupported/stale fast preparation')
    if data.get('sources') != sources(name) or data.get('cpu') != CPU or data.get('icount_shift') != 3:
        raise ValueError('Fast implementation changed; prepare current sources')
    validate_checkpoint_binding(data)
    guest.validate(data['qemu']); guest.validate(data['derivation'])
    entry = data['workloads'][workload]
    for item in entry.values(): guest.validate(item)
    if 'guest_archive' in data:validate_archived_entry(data,workload)
    else:
        directory = Path(entry['build']['path']).parent
        original = data.get('guest_source_root')
        source_root = ROOT
        if original is not None:
            from build_kernel import source_inputs
            from silicon_guest_bundle import _audited_guest_archive
            if (not isinstance(original,dict) or set(original)!={'path','sources'} or
                    name!='lemma-silicon-dev/0.14.0' or workload not in ('school-notebook','school-initializer')):
                raise ValueError('Unsupported frozen Fast guest source authority')
            source_root=Path(original['path']).resolve()
            if source_inputs(source_root)!=original['sources']:raise ValueError('Frozen Fast guest source closure changed')
            _audited_guest_archive(directory,source_root,selected[workload],
                'lemma-school-guest-source-archive/1','actual frozen audited School23/v2 target source')
        guest.verify_guest_build(directory,selected[workload],json.loads((directory/'build.json').read_text())['optimization'],source_root=source_root)
    return data


class QMP:
    def __init__(self,path,process,timeout):
        self.socket = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.socket.settimeout(timeout)
        try:
            deadline = time.monotonic()+timeout
            while True:
                try: self.socket.connect(str(path)); break
                except (FileNotFoundError,ConnectionRefusedError):
                    if process.poll() is not None: raise RuntimeError('Fast machine exited before QMP readiness; see machine.log')
                    if time.monotonic() >= deadline: raise TimeoutError('Fast machine QMP readiness deadline')
                    time.sleep(0.01)
            self.stream = self.socket.makefile('rwb',buffering=0)
            self.read()
            self.serial = 0
            self.reset_generation = 0
            self.execute('qmp_capabilities')
        except BaseException:
            if hasattr(self,'stream'):self.stream.close()
            self.socket.close()
            raise

    def read(self):
        line = self.stream.readline(MAX_REQUEST+1)
        if not line: raise RuntimeError('QMP disconnected')
        if len(line)>MAX_REQUEST: raise ValueError('QMP response exceeds bound')
        return json.loads(line)

    def execute(self,command,arguments=None):
        self.serial+=1
        self.stream.write(json.dumps({'execute':command,'arguments':arguments or {},'id':self.serial}).encode()+b'\n')
        while True:
            value=self.read()
            if value.get('event')=='RESET':self.reset_generation+=1
            if value.get('id')!=self.serial: continue
            if 'error' in value: raise RuntimeError(str(value['error']))
            return value['return']

    def close(self):
        self.stream.close();self.socket.close()


def copy_new(source,destination):
    """Copy durable bytes only. Never issue FLUSH or overwrite a destination."""
    source,destination=Path(source),Path(destination)
    with source.open('rb') as src,destination.open('xb') as dst:
        length=0
        for part in iter(lambda:src.read(1024*1024),b''):
            if part.count(0)==len(part):dst.seek(len(part),os.SEEK_CUR)
            else:dst.write(part)
            length+=len(part)
        dst.truncate(length)
        dst.flush();os.fsync(dst.fileno())


class Fast:
    boundary = 'paused instruction/virtual-timer boundary; no controller drain or storage flush'
    input_kinds = {'pen'}
    def __init__(self,args,directory):
        self.args,self.directory=copy.copy(args),directory
        self.session_directory=directory
        if getattr(args,'native_bundle',None):
            import silicon_guest_bundle
            self.data=silicon_guest_bundle.prepared(args.native_bundle,'qemu',args.workload,args.profile)
            if getattr(args,'guest_build',None):
                if getattr(args,'guest_source_root',None) is None:
                    self.data=silicon_guest_bundle.development_guest(self.data,args.workload,directory,args.guest_build,args.mode)
                else:
                    self.data=silicon_guest_bundle.development_guest(self.data,args.workload,directory,args.guest_build,args.mode,
                                                                   source_root=args.guest_source_root)
        else:self.data=prepared(args.workload,args.profile)
        self.native_logical2=validate_checkpoint_binding(self.data)
        self.mm2_subset=validate_execution_binding(self.data)
        self.optical=self.data.get('execution_binding')==OPTICAL_BINDING
        self.identity={'backend':'qemu','profile':self.data['profile'],'runtime':self.data['qemu']['sha256'],
                       'adapter':ADAPTER,
                       'derivation':self.data['derivation']['sha256'],'guest':self.data['workloads'][args.workload]['image']['sha256'],
                       'dtb':self.data['workloads'][args.workload]['dtb']['sha256'],
                       'descriptor':self.data['workloads'][args.workload]['descriptor']['sha256'],
                       'cpu':CPU,'icount_shift':3}
        if self.data['profile'] in ('lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.17.0'):
            self.identity['host_controls']={name:digest(ROOT/name) for name in ('scripts/lemmasim','scripts/lemmasim_fast.py','scripts/lemmasim_session.py','scripts/silicon_guest_bundle.py','scripts/multimodal_native_bundle.py','scripts/lemmasim_school_service.py','scripts/lemmasim_school_panel.py','scripts/lemmasim_course.py','scripts/lemmasim_tutor.py')}
            if isinstance(self.data.get('native_bundle'),dict):self.identity['native_bundle']=dict(self.data['native_bundle'])
        override_archive=self.data.get('guest_override',{}).get('source_archive')
        if override_archive is not None:
            self.identity['development_guest_source_archive']={key:override_archive[key] for key in ('inventory','build','provenance','audit','image','configuration','source_commit','dirty_paths','inputs','scope')}
        if self.native_logical2:self.identity['checkpoint_binding']=self.data['checkpoint_binding']
        if self.data.get('checkpoint_binding')==MM2_CHECKPOINT_BINDING:
            self.identity.update(checkpoint_contract=MM2_CHECKPOINT_CONTRACT,
                                 observation_relation=self.data['observation_relation'],
                                 checkpoint_admitted=bool(self.data['checkpoint_admitted'] and MM2_CHECKPOINT_ADMITTED))
        if self.mm2_subset:self.identity.update(execution_binding=self.data['execution_binding'],multimodal_controller_abi=2,controller_contract='lemma-multimodal-converter/2')
        if self.optical:self.identity.update(optical_controller_abi=1,optical_frame_contract='lemma-optical-frame/1')
        self.clock_hz=profile(self.data['profile'])['clock_hz']
        self.mtime_address=profile(self.data['profile'])['devices']['timer']['mtime']
        self.power_enabled=bool(profile(self.data['profile']).get('power_enabled',0))
        self.input_kinds={'pen','button'} if self.power_enabled else {'pen'}
        if self.data['profile']=='lemma-silicon-dev/0.4.0':self.input_kinds.update(('pgood','brownout'))
        if self.data['profile'] in ('lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.17.0'):self.input_kinds.add('multimodal')
        self.medium=args.disk.resolve() if args.disk else None
        self.companion=None
        if getattr(args,'companion',None) is not None:
            import lemmasim_companion
            peer=lemmasim_companion.peer_info(args.companion)
            compiled=lemmasim_companion.validate(args.companion_prepared)
            self.companion={'client':compiled['binaries']['companion-client']['path'],
                            'socket':str(args.companion_socket.resolve()),'state':str(args.companion_state.resolve()),
                            'writer':str(peer['writer']),'helper':str(ROOT/'sim/companion/os_io.py')}
        self.has_medium=self.medium is not None or self.companion is not None
        self.checkpoint_files={'machine.chk','clock.json','durable.raw'} if self.has_medium else {'machine.chk','clock.json'}
        if self.native_logical2:self.checkpoint_files.add('logical.tlb')
        self.time_origin_ns=0
        self.generation=0
        self.replay_path=None
        self.start()

    def start(self):
        entry=self.data['workloads'][self.args.workload]
        if self.medium and self.medium.stat().st_size!=256*1024*1024:
            raise ValueError('Matched medium requires exactly256MiB raw sectors')
        if self.args.memory_latency:
            raise ValueError('Fast CPU memory-latency injection is not implemented; use RTL for that boundary')
        if self.args.events:
            raise ValueError('Fast persistent session uses recorded/injected boundary events; RTL event text is not portable')
        # Files and durable forks may have long user-selected paths. The
        # private control socket must fit sockaddr_un independently of them.
        socket_directory=tempfile.TemporaryDirectory(prefix='lemma-qmp-',dir='/tmp')
        self.socket_directory=socket_directory
        path=Path(socket_directory.name)/'qmp.sock'
        command=[self.data['qemu']['path'],'-machine','lemma-silicon-fast-softtlb' if self.native_logical2 or self.mm2_subset else 'lemma-silicon-fast','-cpu',CPU,'-m','128M','-smp','1',
                 '-bios','none','-kernel',entry['image']['path'],'-dtb',entry['dtb']['path'],
                 '-display','none','-monitor','none','-serial',f'file:{self.directory}/uart-{self.generation}.bin',
                 '-qmp',f'unix:{path},server=on,wait=off','-S','-no-shutdown',
                 '-icount','shift=3,align=off,sleep=off','-seed','0x4c454d4d413031',
                 '-global',f'lemma-paper-pen.raw-output={self.directory}/input-{self.generation}.bin']
        if self.mm2_subset:command+=['-global','lemma-paper-pen.multimodal-controller-abi=2',
                                     '-global',f'lemma-paper-pen.multimodal-audio-output={self.directory}/audio-{self.generation}.bin']
        if self.optical:command+=['-global','lemma-paper-pen.optical-controller-abi=1']
        if self.medium:
            command+=['-global',f'lemma-fast-block.medium={self.medium}']
        if self.companion:
            for key,value in self.companion.items():command+=['-global',f'lemma-fast-block.companion-{key}={value}']
        if self.has_medium:
            command+=['-global',f'lemma-fast-block.backing-capture={self.directory}/backing-{self.generation}.io',
                      '-global',f'lemma-fast-block.backing-identity={self.data["qemu"]["sha256"]}']
        if self.replay_path is not None:
            if self.medium is None or self.companion is not None:raise ValueError('Backing replay requires a private restored local medium')
            command+=['-global',f'lemma-fast-block.backing-replay={self.replay_path}',
                      '-global','lemma-fast-block.replay-private=on']
        if self.args.fail_flush:
            command+=['-global',f'lemma-fast-block.fail-flush={self.args.fail_flush}']
        trace_limit=getattr(self.args,'trace_limit',0)
        if trace_limit:
            command+=['-global',f'lemma-paper-pen.trace-file={self.directory}/devices-{self.generation}.log',
                      '-global',f'lemma-paper-pen.trace-limit={trace_limit}',
                      '-global',f'lemma-fast-block.trace-file={self.directory}/media-{self.generation}.log',
                      '-global',f'lemma-fast-block.trace-limit={trace_limit}']
        self.argv=command
        self.log=None;self.process=None;self.qmp=None
        try:
            self.log=(self.directory/'machine.log').open('ab')
            self.process=subprocess.Popen(command,cwd=ROOT,stdout=self.log,stderr=self.log,start_new_session=True)
            self.qmp=QMP(path,self.process,self.args.timeout)
            # Negotiate the actual immutable backend feature at reset, before
            # any target clock. Old prepared binaries keep adapter4 unchanged.
            properties = self.qmp.execute('qom-list', {'path':'/machine/lemma-hardware'})
            if (not isinstance(properties, list) or
                    any(not isinstance(row, dict) or
                        not isinstance(row.get('name'), str) or
                        not isinstance(row.get('type'), str) for row in properties)):
                raise ValueError('Malformed backend property inventory')
            self.raw_uart = False
            self.raw_uart_paced = False
            self.raw_uart_flow = False
            self.execution_state = any(row.get("name") == "execution-state" for row in properties)
            self.input_kinds = self.input_kinds - {'uart'}
            if self.optical:
                names={row['name'] for row in properties}
                if (not {'optical-version','optical-source','optical-source-batch','optical-state'}.issubset(names) or
                        self.get('optical-version')!='lemma-optical-frame/1'):
                    raise ValueError('Actual optical source/controller ABI is absent')
                self.input_kinds=self.input_kinds|{'optical-frame'}
            self.identity = {**self.identity, 'adapter':ADAPTER}
            if any(row.get('name') == 'raw-uart-version' for row in properties):
                if self.data['profile'] not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.17.0') or self.get('raw-uart-version') != 'lemma-raw-uart/1':
                    raise ValueError('Unsupported raw UART backend/profile')
                self.qmp.execute('qom-set', {'path':'/machine/lemma-hardware',
                                           'property':'enable-raw-uart','value':'lemma-raw-uart/1'})
                self.raw_uart = True
                self.input_kinds = self.input_kinds | {'uart'}
                self.identity = {**self.identity, 'adapter':RAW_UART_ADAPTER}
                if any(row.get('name') == 'raw-uart-paced-version' for row in properties):
                    if self.get('raw-uart-paced-version') != 'lemma-raw-uart-paced/1':
                        raise ValueError('Unsupported paced UART backend contract')
                    self.raw_uart_paced = True
                if (self.data['profile'] == 'lemma-silicon-dev/0.14.0' and
                        any(row.get('name') == 'raw-uart-flow-version' for row in properties)):
                    if self.get('raw-uart-flow-version') != 'lemma-raw-uart-flow/1':
                        raise ValueError('Unsupported UART backpressure flow contract')
                    self.qmp.execute('qom-set', {'path':'/machine/lemma-hardware',
                                               'property':'enable-raw-uart-flow',
                                               'value':'lemma-raw-uart-flow/1'})
                    self.raw_uart_flow = True
                    self.identity = {**self.identity, 'adapter':RAW_UART_FLOW_ADAPTER,
                                     'uart_flow':'lemma-raw-uart-flow/1'}
        except BaseException:
            if self.process is not None:
                if self.process.poll() is None:os.killpg(self.process.pid,signal.SIGKILL)
                self.process.wait(timeout=5)
            if self.qmp is not None:self.qmp.close()
            if self.log is not None:self.log.close()
            socket_directory.cleanup();self.socket_directory=None
            raise

    def get(self,property):
        return self.qmp.execute('qom-get',{'path':'/machine/lemma-hardware','property':property})

    def clock(self):
        local=int(self.get('virtual-time'))
        ns=self.time_origin_ns+local
        if not 0<=local<=ns<=MAX_NS:raise ValueError('Fast virtual clock exceeds its bound')
        status=self.qmp.execute('query-status')
        # Read the actual pure MTIME register. Warm reset clears ACLINT MTIME
        # through its time_delta while the instruction clock keeps advancing.
        text=self.qmp.execute('human-monitor-command',{'command-line':f'xp /1gx 0x{self.mtime_address:x}'})
        match=re.fullmatch(r'([0-9a-fA-F]+):\s+0x([0-9a-fA-F]{16})\r?\n?',text)
        if match is None or int(match[1],16)!=self.mtime_address:
            raise ValueError('Malformed MTIME observer response')
        ticks=int(match[2],16)
        return {'backend':'qemu','cycle':(ns*self.clock_hz+999999999)//1000000000,'ticks':ticks,'virtual_ns':ns,
                'local_virtual_ns':local,'local_ticks':ticks,'time_origin_ns':self.time_origin_ns,
                'finished':status['status'] in ('shutdown','internal-error','guest-panicked'),
                'runstate':status['status']}

    def inspect(self):
        devices=json.loads(self.get('device-state'))
        if self.data['profile'] in ('lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.17.0'):devices['multimodal']=json.loads(self.get('multimodal-state'))
        if getattr(self,'optical',False):devices['optical']=json.loads(self.get('optical-state'))
        if getattr(self,'power_enabled',False):devices['power']=json.loads(self.get('power-state'))
        if getattr(self,'raw_uart',False):
            devices['uart_ingress']={**json.loads(self.get('raw-uart-state')), 'paced':getattr(self,'raw_uart_paced',False)}
        if getattr(self,'execution_state',False):devices['execution']=json.loads(self.get('execution-state'))
        return {**self.clock(),'devices':devices,
                'storage':json.loads(self.qmp.execute('qom-get',{'path':'/machine/lemma-block','property':'storage-state'})),
                'cpu_registers':self.qmp.execute('human-monitor-command',{'command-line':'info registers'}),
                'cpu_info':self.qmp.execute('human-monitor-command',{'command-line':'info cpus'})}

    def stop(self):
        try:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.qmp.execute('quit');self.process.wait(timeout=5)
                except (OSError,RuntimeError,subprocess.TimeoutExpired):
                    pass
                finally:
                    if self.process.poll() is None: os.killpg(self.process.pid,signal.SIGKILL)
                    self.process.wait(timeout=5)
        finally:
            if self.qmp is not None:self.qmp.close();self.qmp=None
            if self.log is not None:self.log.close();self.log=None
            if getattr(self,'socket_directory',None) is not None:
                self.socket_directory.cleanup();self.socket_directory=None

    def run_until_ns(self, ns):
        if self.qmp.execute('query-status')['status']=='internal-error':raise ValueError('Fast execution scope was rejected; inspect machine.log. Use exact RTL or an explicit cold-cycle; this machine cannot resume.')
        now=self.time_origin_ns+int(self.get('virtual-time'))
        if type(ns) is not int or not now<=ns<=MAX_NS:raise ValueError('Fast interval must advance a supported virtual time')
        if ns==now:return self.clock()
        # A timer may be observed at the next eight-nanosecond instruction
        # boundary; reserve that final partial instruction before admission.
        if ns>MAX_NS-7:raise ValueError('Fast interval would overflow its instruction clock phase')
        self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'run-until','value':str(ns-self.time_origin_ns)})
        self.qmp.execute('cont')
        deadline=time.monotonic()+self.args.timeout
        while self.qmp.execute('query-status')['running']:
            if time.monotonic()>=deadline:
                self.qmp.execute('stop')
                raise TimeoutError('Fast virtual interval exceeded host resource deadline')
            time.sleep(0.001)
        if self.qmp.execute('query-status')['status']=='internal-error':raise ValueError('Fast execution scope was rejected; inspect machine.log. Use exact RTL or an explicit cold-cycle; no guest success was admitted.')
        storage=json.loads(self.qmp.execute('qom-get',{'path':'/machine/lemma-block','property':'storage-state'}))
        if storage.get('backing_poisoned'):
            raise RuntimeError('Backing persistence unresolved; machine paused without acknowledgment. Restart the companion/outbox to reconcile; this machine cannot snapshot pending work.')
        return self.clock()

    def checkpoint_admission(self):
        data=getattr(self,'data',{})
        if data.get('profile')=='lemma-silicon-dev/0.17.0':
            raise ValueError('Optical pending source/DMA/lease continuation is not qualified; no checkpoint or candidate created')
        if getattr(self,'mm2_subset',False):
            if (not MM2_CHECKPOINT_ADMITTED or data.get('checkpoint_binding')!=MM2_CHECKPOINT_BINDING or
                    data.get('checkpoint_admitted') is not True):
                raise ValueError('MM2 pending ring continuation is not publicly admitted; no checkpoint or candidate created')
        if data.get('profile')=='lemma-silicon-dev/0.14.0':
            if not getattr(self,'native_logical2',False):
                raise ValueError('Profile0.14 exact checkpoint and live restore are explicitly unsupported; no snapshot file or candidate was created')
            if not LOGICAL2_CHECKPOINT_ADMITTED:
                raise ValueError('Native logical2 checkpoint qualification remains guarded; no snapshot file or candidate was created')
            if self.companion is not None:
                raise ValueError('Logical2 continuation requires isolated local backing; externalcompanion state is not admitted')

    def checkpoint_capture_admission(self):
        self.checkpoint_admission()
        if getattr(self,'mm2_subset',False):
            validate_mm2_checkpoint_cut(json.loads(self.get('multimodal-state')))

    def preflight_checkpoint(self,path,expected_cycle):
        self.checkpoint_admission()
        path=Path(path)
        origin=read_clock(path.with_name('clock.json'))
        if type(expected_cycle) is not int or not 0<=expected_cycle<(1<<64):raise ValueError('Invalid checkpoint cycle')
        if self.native_logical2:
            side=path.with_name('logical.tlb')
            if side.is_symlink() or not side.is_file() or not 88<=side.stat().st_size<=64*1024*1024:
                raise ValueError('Missing or oversized logical2 sidecar')
            value=side.read_bytes();length=struct.unpack_from('<Q',value,16)[0]
            if (value[:8]!=b'LMTLB02\0' or struct.unpack_from('<Q',value,8)[0]!=2 or
                    length!=len(LOGICAL2_BINDING) or value[24:24+length]!=LOGICAL2_BINDING.encode() or
                    value[24+length:56+length]!=bytes.fromhex(digest(path)) or
                    value[-32:]!=hashlib.sha256(value[:-32]).digest()):
                raise ValueError('Logical2 sidecar version, mainbinding or integrity differs')
        if self.has_medium:
            medium=path.with_name('durable.raw')
            if medium.is_symlink() or not medium.is_file() or medium.stat().st_size!=256*1024*1024:
                raise ValueError('Checkpoint requires exact isolated256MiB backing')
        return origin

    def restore_checkpoint(self,path,expected_ns=None):
        self.checkpoint_admission()
        path=Path(path)
        origin=read_clock(path.with_name('clock.json'))
        if expected_ns is not None and (type(expected_ns) is not int or not origin<=expected_ns<=MAX_NS):
            raise ValueError('Snapshot origin and virtual phase disagree')
        directory=self.session_directory/f'machine-fork-{self.generation+1}-{time.time_ns()}'
        directory.mkdir()
        candidate=object.__new__(Fast)
        candidate.__dict__={key:value for key,value in self.__dict__.items() if key not in ('process','qmp','log','socket_directory')}
        candidate.directory=directory
        candidate.generation=self.generation+1
        candidate.time_origin_ns=origin
        try:
            if self.has_medium:
                candidate.medium=directory/'durable.raw'
                copy_new(path.with_name('durable.raw'),candidate.medium)
                candidate.companion=None
            replay=getattr(self.args,'backing_replay',None)
            if replay is not None:
                if not self.has_medium:raise ValueError('Backing replay requires checkpoint durable bytes')
                candidate.replay_path=Path(replay).resolve()
            candidate.start()
            candidate.qmp.execute('lemma-load-machine-softtlb' if getattr(self,'native_logical2',False) else 'lemma-load-machine',
                                  {'filename':str(path),**({'cache-filename':str(path.with_name('logical.tlb'))} if getattr(self,'native_logical2',False) else {})})
            if expected_ns is not None and candidate.clock()['virtual_ns']!=expected_ns:
                raise ValueError('Snapshot metadata differs from its saved virtual phase')
            # Complete every observer that can reject before retiring the
            # currently interactive machine. A failed inspection belongs to
            # this disposable candidate just like a partial VMState load.
            restored=candidate.inspect()
            if getattr(candidate,'mm2_subset',False):
                validate_mm2_checkpoint_cut(restored['devices']['multimodal'])
        except BaseException:
            # QEMU may reject after partially reading VMState. Only this
            # disposable fork was exposed; the current machine stays intact.
            if getattr(candidate,'qmp',None) is not None:candidate.stop()
            # Only the newly created failed fork is disposable. Its source
            # checkpoint and the currently owned durable medium stay intact.
            shutil.rmtree(directory)
            raise
        self.stop()
        self.__dict__.update(candidate.__dict__)
        return restored

    def call(self,command):
        action,_,text=command.partition(' ')
        if action=='snapshot':self.checkpoint_capture_admission()
        elif action=='restore':self.checkpoint_admission()
        if action=='inspect':return self.inspect()
        if action=='pause':
            if self.qmp.execute('query-status')['running']:self.qmp.execute('stop')
            return self.inspect()
        if action=='companion-retry':
            if self.qmp.execute('query-status')['running']:raise ValueError('Backing retry requires paused execution')
            self.qmp.execute('qom-set',{'path':'/machine/lemma-block','property':'retry-backing','value':'retry'})
            return self.inspect()
        if action=='run':
            ns=self.time_origin_ns+int(self.get('virtual-time'))+int(text)*1000000000//self.clock_hz
            return self.run_until_ns(ns)
        if action=='run-until-ns':return self.run_until_ns(int(text))
        if action=='optical-source-batch':
            if not getattr(self,'optical',False):raise ValueError('Actual optical source is absent')
            cycle,separator,wire=text.partition(' ')
            if not separator or re.fullmatch(r'0|[1-9][0-9]{0,19}',cycle) is None:
                raise ValueError('Optical batch requires an exact current cycle')
            _,request=external_command({'action':'optical-source-batch','cycle':int(cycle),'rows':wire},self.clock()['cycle'])
            self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'optical-source-batch','value':request['rows']})
            return self.inspect()
        if action=='inject':
            fields=text.split();cycle=int(fields[0]);kind=fields[1]
            if ('uart' if kind=='uart-paced' else kind) not in self.input_kinds: raise ValueError('Fast input is unsupported by this profile')
            ns=cycle*1000000000//self.clock_hz
            now=self.time_origin_ns+int(self.get('virtual-time'))
            if not now<=ns<=MAX_NS-7:raise ValueError('Fast event delivery exceeds its virtual time bound')
            if kind == 'multimodal':
                if len(fields)!=6 or cycle!=self.clock()['cycle']:raise ValueError('Fast multimodal stimulus requires current cycle; future scheduled stimuli are not admitted')
                self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'multimodal-stimulus','value':' '.join(fields[2:])})
                return self.inspect()
            if kind == 'optical-frame':
                if (not getattr(self,'optical',False) or len(fields)!=7 or cycle!=self.clock()['cycle'] or
                        any(re.fullmatch(r'0|[1-9][0-9]{0,19}',word) is None for word in fields[2:])):
                    raise ValueError('Fast optical source requires the admitted binding and exact current cycle')
                words=[int(word) for word in fields[2:]]
                external_command({'action':'inject','kind':'optical-frame','words':words},cycle)
                self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'optical-source','value':' '.join(map(str,words))})
                return self.inspect()
            if kind == 'uart-paced':
                if not getattr(self,'raw_uart_paced',False):raise ValueError('Backend lacks paced UART admission')
                if len(fields)!=4 or not re.fullmatch(r'[1-9][0-9]{0,18}',fields[2]) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){1,65536}',fields[3]):
                    raise ValueError('Fast paced UART requires bounded interval and hexadecimal bytes')
                interval=int(fields[2]);count=len(fields[3])//2
                if ns+(count-1)*interval>MAX_NS-10:raise ValueError('Fast paced UART final arrival overflows virtual time')
                self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'external-uart-paced','value':str(ns-self.time_origin_ns)+' '+str(interval)+' '+fields[3]})
                return self.inspect()
            if kind == 'uart':
                if len(fields) != 3 or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){1,65536}', fields[2]) or ns > MAX_NS-10:
                    raise ValueError('Fast UART requires bounded raw hexadecimal bytes and time')
                self.qmp.execute('qom-set', {'path':'/machine/lemma-hardware','property':'external-uart',
                                           'value':str(ns-self.time_origin_ns)+' '+fields[2]})
                return self.inspect()
            supply=kind in ('pgood','brownout')
            value=[str(ns-self.time_origin_ns),*(['2' if kind=='pgood' else '3'] if supply else []),*fields[2:]]
            self.qmp.execute('qom-set',{'path':'/machine/lemma-hardware','property':'external-supply' if supply else 'external-button' if kind=='button' else 'external-event',
                                      'value':' '.join(value)})
            return self.inspect()
        if action=='snapshot':
            path=Path(text)
            clock_path=path.with_name('clock.json')
            if clock_path.exists():raise FileExistsError('Fast clock snapshot already exists')
            self.qmp.execute('lemma-save-machine-softtlb' if getattr(self,'native_logical2',False) else 'lemma-save-machine',
                             {'filename':str(path),**({'cache-filename':str(path.with_name('logical.tlb'))} if getattr(self,'native_logical2',False) else {})})
            with clock_path.open('x') as stream:
                json.dump({'schema':CLOCK_SCHEMA,'time_origin_ns':self.time_origin_ns},stream)
                stream.write('\n');stream.flush();os.fsync(stream.fileno())
            if self.has_medium:
                self.qmp.execute('qom-set',{'path':'/machine/lemma-block','property':'export-medium','value':str(path.with_name('durable.raw'))})
            return self.inspect()
        if action=='restore':
            return self.restore_checkpoint(text)
        if action=='warm-reset':
            before=self.qmp.reset_generation
            self.qmp.execute('system_reset')
            deadline=time.monotonic()+self.args.timeout
            while self.qmp.reset_generation==before:
                self.qmp.execute('query-status')
                if self.qmp.reset_generation==before:
                    if time.monotonic()>=deadline:raise TimeoutError('Fast warm reset event deadline')
                    time.sleep(0.001)
            return self.inspect()
        if action=='cold-cycle':
            if self.replay_path is not None:raise ValueError('Recorded I/O suffix belongs to its restored clock; start another isolated restore')
            origin=self.clock()['virtual_ns']
            self.stop();self.time_origin_ns=origin;self.generation+=1;self.start();return self.inspect()
        if action=='panel':
            self.qmp.execute('screendump',{'filename':text});return self.inspect()
        if action=='export-medium':
            if not self.has_medium: raise ValueError('Machine has no durable backing')
            self.qmp.execute('qom-set',{'path':'/machine/lemma-block','property':'export-medium','value':text});return self.inspect()
        if action=='destroy': self.stop();return {'destroyed':True}
        raise ValueError('Unsupported fast lifecycle operation')

    def close(self):
        self.stop()
