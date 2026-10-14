#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit original Clocked producers before a finite native/Wasm state relation."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import sys

from silicon_wasm import archived_native_build
from silicon_compute import snapshot_inputs
from silicon_guest_bundle import prepared
from check_native_usb_wire_pending import CASES, run_fixture
from check_guest_usb_link import require, sha

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('wasm-build','rtl-build','rtl-source-root','native-bundle','native-result','work-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();out=args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT/'build'),'unused owned qualifier output')
    out.mkdir();report={'schema':'lemma-clocked-portable-pending-qualification/1','status':'FAIL','scope':__doc__}
    try:
        portable=args.wasm_build.resolve();build=json.loads((portable/'build.json').read_text())
        manifest,resolve,header,origin=archived_native_build(args.rtl_build,args.rtl_source_root,'lemma-silicon-dev/0.13.0')
        require(build['status']=='BUILT' and build['profile']=='lemma-silicon-dev/0.13.0' and
                build['source_recompilation']==origin,'portable producer does not match complete original native archive')
        for key in ('sha256','configuration_includes','host_runtime','binding_generator_inputs','host_toolchain_inputs'):
            require(build[key]==manifest[key],'native/portable producer input map differs: '+key)
        require(build['host_binding_sha256']==manifest['host_binding_sha256'],'portable generated hardware binding differs')
        require((portable/'binding/lemma_silicon_binding.h').read_text()==header,'portable bound header bytes differ')
        for name,digest in build['outputs'].items():require(sha(portable/name)==digest,'portable output changed')
        for name,digest in build['portable_inputs'].items():
            path=ROOT/name if name=='scripts/silicon_wasm.py' else portable/'portable-host'/name
            require(sha(path)==digest,'portable host input changed: '+name)
        for name,digest in build['verilator_runtime_inputs'].items():require(sha(name)==digest,'pinned Verilator runtime changed')
        filtered={key:value for key,value in build.items() if key not in ('status','scope','snapshot_identity','wall_seconds','outputs')}
        identity=hashlib.sha256(json.dumps(snapshot_inputs(filtered,ROOT/'build/silicon/deps/cvw'),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        require(identity==build['snapshot_identity'],'portable implementation identity differs from complete producer')
        bundle=prepared(args.native_bundle,'rtl','usb-clocked-bulk-initializer','lemma-silicon-dev/0.13.0')
        actual_path=args.native_result.resolve();actual=json.loads(actual_path.read_text())
        qualified=json.loads((ROOT/'docs/evidence/006-usb-clocked13.json').read_text())['guest_pending']
        require(sha(actual_path)==qualified['sha256'] and actual['status']=='PASS' and actual['profile']=='lemma-silicon-dev/0.13.0',
                'input is not the independently qualified actual native Pending result')
        require(actual['identity']['native']==bundle['binary']['sha256']==origin['native']['binary']['sha256'] and
                actual['identity']['implementation']==origin['original_snapshot_identity'] and
                actual['identity']['guest']==bundle['workloads']['usb-clocked-bulk-initializer']['image']['sha256'],
                'actual native guest/implementation association differs')
        require({case['case'] for case in actual['cases']}==CASES and len(actual['cases'])==9,'actual nine-cut corpus differs')
        cases=[];total=0
        for case in actual['cases']:
            label=case['case'];total+=case['suffix_cycles'];entry={'name':label,'snapshot_cycle':case['snapshot_cycle'],'suffix_cycles':case['suffix_cycles']}
            for field,filename in (('snapshot',label+'.snap'),('final_snapshot',label+'-final.snap'),
                                   ('prefix_tape',label+'-prefix.tape'),('tape',label+'.tape'),('uart',label+'-fork.uart')):
                path=actual_path.parent/filename;item=actual['files'][filename]
                require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],'actual captured input changed: '+filename)
                entry[field]=str(path);entry[field+'_sha256']=item['sha256']
            if label=='physical-send':
                path=actual_path.parent/'physical-send-semantic-error.tape';item=actual['files'][path.name]
                require(path.stat().st_size==item['bytes'] and sha(path)==item['sha256'],'actual semantic-negative tape changed')
                entry['semantic_tape']=str(path);entry['semantic_tape_sha256']=item['sha256']
            cases.append(entry)
        require(total<=70000000,'predeclared suffix cycle limit')
        authority={'schema':'lemma-clocked-portable-pending-authority/1','module':str(portable/'machine.mjs'),'module_sha256':build['outputs']['machine.mjs'],
                   'wasm':str(portable/'machine.wasm'),'wasm_sha256':build['outputs']['machine.wasm'],
                   'native_identity':actual['identity']['implementation'],'portable_identity':identity,'cases':cases,
                   'source_native':origin,'wasm_build':{'path':str(portable/'build.json'),'sha256':sha(portable/'build.json')},
                   'native_result':{'path':str(actual_path),'sha256':sha(actual_path)},'guest_bundle':bundle['native_bundle'],
                   'relation':'only independently validated snapshot/tape implementation identity fields may be rebound; all authoritative state is exact'}
        authority_path=out/'authority.json';authority_path.write_text(json.dumps(authority,indent=2)+'\n')
        if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0):raise OSError('qualifier subreaper setup')
        node_script=ROOT/'scripts/check_wasm_clocked_pending.mjs'
        import shlex
        argv=['nix-shell',str(portable/'portable-host/tooling/silicon/wasm.nix'),'--run',
              shlex.join(['node','--expose-gc',str(node_script),str(authority_path),str(out/'actual')])]
        report['owned_children']=run_fixture(argv,out/'run.log',1800,maximum_rss_kib=4194304)
        actual_port=json.loads((out/'actual/result.json').read_text());require(actual_port['status']=='PASS' and len(actual_port['cases'])==9,'portable property did not close all nine cases')
        require(sum(path.stat().st_size for path in out.rglob('*') if path.is_file())<=12000000000,'predeclared retained output bound')
        report.update(status='PASS',actual={'path':str(out/'actual/result.json'),'sha256':sha(out/'actual/result.json')},
                      authority={'path':str(authority_path),'sha256':sha(authority_path)},native_inputs=255,
                      producer_identity_relation='complete original native circuit/Machine sources plus separately declared portable host shim/tools',
                      no_cpu_cold_prefix=True,no_external_peer=True)
    except BaseException as error:report['error']=repr(error)
    report['observer_sha256']=sha(__file__);(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'error':report.get('error'),'result':str(out/'result.json')}))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
