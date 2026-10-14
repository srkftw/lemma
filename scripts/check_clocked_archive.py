#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify actual Clocked selected-profile archives; no CPU execution/relabeling."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
from unittest.mock import patch

import silicon_guest as guest
import silicon_guest_bundle as bundle
import silicon_profile

ROOT=Path(__file__).resolve().parents[1]
NAME='lemma-silicon-dev/0.13.0'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('rtl-build','rtl-source-root','original-native-source-root','native-bundle','execution-result','work-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):parser.error('unused owned build output required')
    out.mkdir();started=time.monotonic()
    result={'schema':'lemma-clocked-selected-profile-archive-evidence/1','status':'FAIL',
            'scope':'Separate observation of original manifest-bound profile bytes and unchanged executed identities; no new CPU, target compilation or reinterpretation of original coverage failure.',
            'host_seconds_bound':120,'automatic_restart':False,'mutants':[]}
    try:
        original=args.rtl_source_root.resolve();package=args.native_bundle.resolve()
        profile_path=original/guest.USB_CLOCKED_PROFILE_FILE
        before={str(path):sha(path) for path in (profile_path,args.rtl_build/'build.json',args.execution_result,package/'bundle.json')}
        # The old capture omitted one separately hash-bound manifest input.
        try:guest.native_source_archive(args.rtl_build,args.original_native_source_root,NAME)
        except ValueError as error:result['original_coverage_failure']=str(error)
        else:raise ValueError('Original incomplete Clocked capture unexpectedly accepted')
        with patch.object(guest,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(silicon_profile,'profile_path',side_effect=AssertionError('ROOT profile fallback')):
            machine,sources,evidence=guest.native_source_archive(args.rtl_build,original,NAME)
            first=bundle.prepared(package,'rtl','usb-clocked-bulk-initializer',NAME)
            second=bundle.prepared(package,'rtl','usb-clocked-bulk-notebook',NAME)
            facts=guest.prepared_profile(first)
            guest.validate_clocked_capture_authority(first,'usb-clocked-bulk-initializer')
            registry=guest._read_unique_json(guest.prepared_path(NAME))
            guest_root=registry['workloads']['usb-clocked-bulk-initializer']['guest_source_archive']['source_root']
            direct=guest.prepared('usb-clocked-bulk-initializer',NAME,rtl_source_root=original,guest_source_root=guest_root)
        result.update(native_archive=evidence,inputs=len(sources),binding_profile=first['binding_profile'],
                      profile_sha256=machine['profile_sha256'],bundle=first['native_bundle'])
        if facts['profile']!=NAME or facts['descriptor']['abi']!=14:raise ValueError('Different archived Clocked profile')
        # Actual published execution remains attached to its original receipt.
        execution=json.loads(args.execution_result.read_text())
        entry=first['workloads']['usb-clocked-bulk-initializer']
        identities={'native':first['binary']['sha256'],'implementation':machine['snapshot_identity'],
                    'guest':entry['image']['sha256'],'rom':first['rom']['sha256'],
                    'dtb':entry['dtb']['sha256'],'descriptor':entry['descriptor']['sha256']}
        if execution.get('status')!='PASS' or execution['identity']!=identities or len(execution['cases'])!=9:
            raise ValueError('Selected package differs from actual nine-cut execution')
        result['unchanged_execution']={'path':str(args.execution_result.resolve()),'sha256':sha(args.execution_result),'identity':identities,'cases':len(execution['cases'])}
        # Host API vectors only: deliberately stop before launching a CPU or
        # constructing a replay medium. These are not execution receipts.
        class BeforeCPU(RuntimeError):pass
        command=[]
        def no_cpu(argv,**_):command.extend(map(str,argv));raise BeforeCPU('host launch boundary only')
        launch=out/'host-launch';launch.mkdir()
        with patch.object(guest,'profile',side_effect=AssertionError('ROOT profile fallback')),patch.object(guest.subprocess,'Popen',side_effect=no_cpu):
            try:guest.execute(first,'usb-clocked-bulk-initializer',launch,{'cycles':1,'trace_limit':0,'timeout':1},{},Path('/not-opened-host-vector-medium'))
            except BeforeCPU:pass
            else:raise ValueError('Host vector unexpectedly launched a CPU')
        if command[command.index('--load')+1]!=f"0x{facts['dtb_base']:x}:{entry['dtb']['path']}":raise ValueError('Host vector did not use the bound DTB base')
        captured=out/'host-replay';captured.mkdir();log=captured/'actual-pending.log'
        shutil.copyfile(args.execution_result.parent/'run.log',log)
        (captured/'output.json').write_text(json.dumps({'outputs':{log.name:sha(log)}}))
        (captured/'input.json').write_text(json.dumps({'schema_version':1,'transport':'lemma-silicon-events/1','prepared':first,'workload':'usb-clocked-bulk-initializer','inputs':{},'initial_medium':None,'options':{}}))
        reached=[]
        def no_replay(*_args,**_kwargs):reached.append(True);raise BeforeCPU('host replay capture boundary only')
        with patch.object(guest,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(silicon_profile,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(guest,'capture',side_effect=no_replay):
            try:guest.replay(SimpleNamespace(session=captured,timeout=1))
            except BeforeCPU:pass
            else:raise ValueError('Host replay vector unexpectedly reached CPU execution')
        if not reached:raise ValueError('Host replay did not reach bound capture boundary')
        (captured/'input.json').write_text(json.dumps({'schema_version':1,'transport':'lemma-silicon-events/1','prepared':direct,'workload':'usb-clocked-bulk-initializer','inputs':{},'initial_medium':None,'options':{}}))
        reached.clear()
        with patch.object(guest,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(silicon_profile,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(guest,'capture',side_effect=no_replay):
            try:guest.replay(SimpleNamespace(session=captured,timeout=1))
            except BeforeCPU:pass
            else:raise ValueError('Explicit archive replay vector unexpectedly reached CPU execution')
        if not reached:raise ValueError('Explicit archive replay did not reach bound capture boundary')
        result['host_only_vectors']={'execute_argv':command,'replay':'package and explicit native+guest archives each fully revalidated then stopped before capture; no CPU/medium/replay result claimed'}
        clone=out/'archive';shutil.copytree(original.parent,clone)
        candidate=clone/'source'/guest.USB_CLOCKED_PROFILE_FILE;profile_bytes=candidate.read_bytes()
        sidecar=clone/'consumed-source-archive.json';sidecar_bytes=sidecar.read_bytes()
        def rejects(label,call):
            try:call()
            except (ValueError,OSError,AssertionError,KeyError) as error:result['mutants'].append({'case':label,'status':'REJECT','reason':str(error)})
            else:raise ValueError('Actual archive mutation accepted: '+label)
        other=out/'different-valid-profile.json';changed=copy.deepcopy(facts);changed['dtb_base']+=4096;other.write_text(json.dumps(changed))
        wrong=copy.deepcopy(direct);wrong['binding_profile']=guest.identified(other);wrong['profile_sha256']=wrong['binding_profile']['sha256']
        rejects('direct-captured-profile-differs-from-native-authority',lambda:guest.validate_clocked_capture_authority(wrong,'usb-clocked-bulk-initializer'))
        check=lambda:guest.native_source_archive(args.rtl_build,clone/'source',NAME)
        candidate.unlink();rejects('native-missing-selected-profile',check);candidate.write_bytes(profile_bytes)
        candidate.write_bytes(b'{}');rejects('native-corrupt-selected-profile',check);candidate.write_bytes(profile_bytes)
        metadata=json.loads(sidecar_bytes);metadata['selected_profile']['sha256']='0'*64;sidecar.write_text(json.dumps(metadata))
        rejects('native-mismatched-selected-manifest-profile',check);sidecar.write_bytes(sidecar_bytes)
        candidate.unlink();candidate.symlink_to(profile_path);rejects('native-symlink-selected-profile',check);candidate.unlink();candidate.write_bytes(profile_bytes)
        private=out/'package';shutil.copytree(package,private)
        manifest=private/'bundle.json';manifest_bytes=manifest.read_bytes();metadata=json.loads(manifest_bytes)
        original_profile=Path(metadata['original_repository_root'])/guest.USB_CLOCKED_PROFILE_FILE
        relative=bundle.origin_destination(metadata,original_profile,machine['profile_sha256'])
        candidate=private/relative;profile_bytes=candidate.read_bytes()
        check=lambda:bundle.prepared(private,'rtl','usb-clocked-bulk-initializer',NAME)
        candidate.unlink();rejects('package-missing-selected-profile',check);candidate.write_bytes(profile_bytes)
        candidate.write_bytes(b'{}');rejects('package-corrupt-selected-profile',check);candidate.write_bytes(profile_bytes)
        metadata['backends']['rtl']['profile_sha256']='0'*64;manifest.write_text(json.dumps(metadata))
        rejects('package-mismatched-selected-profile',check);manifest.write_bytes(manifest_bytes)
        metadata=json.loads(manifest_bytes);del metadata['backends']['rtl']['rtl_sources'][str(original_profile)];manifest.write_text(json.dumps(metadata))
        rejects('package-selected-profile-omitted-from-native-closure',check);manifest.write_bytes(manifest_bytes)
        with patch.object(guest,'profile_path',side_effect=AssertionError('ROOT profile fallback')),patch.object(silicon_profile,'profile_path',side_effect=AssertionError('ROOT profile fallback')):
            check()
        if any(sha(path)!=digest for path,digest in before.items()):raise ValueError('Original qualified artifact changed')
        result.update(status='PASS',original_inputs=before,observer_sha256=sha(__file__))
    except BaseException as error:result['error']=repr(error)
    finally:
        result['host_seconds']=time.monotonic()-started
        if result['host_seconds']>120:result.update(status='FAIL',error='predeclared archive observer deadline')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return result['status']!='PASS'

if __name__=='__main__':raise SystemExit(main())
