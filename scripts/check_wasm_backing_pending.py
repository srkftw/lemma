#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Admit canonical native/portable producers before replaying actual failed I/O.

Two literal controller cuts qualify pending POSIX outcomes, not guest Save or
arbitrary native/Wasm migration. No cold prefix or original medium is executed.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import shlex

from check_native_evaluation import require
from check_native_usb_wire_pending import run_fixture
from silicon_compute import snapshot_inputs
from silicon_guest import ROOT, sha
from silicon_guest_bundle import prepared
from silicon_wasm import archived_native_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wasm-build', 'rtl-build', 'rtl-source-root', 'native-bundle',
                 'native-result', 'work-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    out = args.work_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT/'build'), 'unused owned output required')
    out.mkdir()
    report = {'schema': 'lemma-portable-backing-pending-qualification/1',
              'status': 'FAIL', 'scope': __doc__}
    try:
        portable = args.wasm_build.resolve()
        build = json.loads((portable/'build.json').read_text())
        manifest, _, header, origin = archived_native_build(
            args.rtl_build, args.rtl_source_root, 'lemma-silicon-dev/0.3.0')
        require(build['status'] == 'BUILT' and build['profile'] == manifest['profile']
                and build['source_recompilation'] == origin, 'portable producer differs')
        for key in ('sha256', 'configuration_includes', 'host_runtime',
                    'binding_generator_inputs', 'host_toolchain_inputs', 'host_binding_sha256'):
            require(build[key] == manifest[key], 'native/portable input map differs: '+key)
        require((portable/'binding/lemma_silicon_binding.h').read_text() == header,
                'portable binding bytes differ')
        for name, digest in build['outputs'].items():
            require(sha(portable/name) == digest, 'portable output changed')
        for name, digest in build['portable_inputs'].items():
            source = ROOT/name if name == 'scripts/silicon_wasm.py' else portable/'portable-host'/name
            require(sha(source) == digest, 'portable host input changed: '+name)
        for name, digest in build['verilator_runtime_inputs'].items():
            require(sha(name) == digest, 'pinned Verilator runtime changed')
        identity_inputs = {k: v for k, v in build.items() if k not in
                           ('status', 'scope', 'snapshot_identity', 'wall_seconds', 'outputs')}
        identity = hashlib.sha256(json.dumps(snapshot_inputs(identity_inputs,
            ROOT/'build/silicon/deps/cvw'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(identity == build['snapshot_identity'], 'complete portable identity differs')
        native = args.native_result.resolve()
        result = json.loads(native.read_text())
        qualified = json.loads((ROOT/'docs/evidence/006-native-backing-pending.json').read_text())[
            'native_linux_file_limit_signal_capture']['literal_native_boundary']['result']
        require(sha(native) == qualified['sha256'] and result['status'] == 'PASS'
                and result['snapshot_identity'] == origin['original_snapshot_identity']
                and result['native_sha256'] == origin['native']['binary_sha256'],
                'native failed-I/O result is not the qualified producer')
        bundle = prepared(args.native_bundle, 'rtl', 'notebook', manifest['profile'])
        require(bundle['workloads']['notebook']['image']['sha256'] ==
                result['archived_genuine_guest']['image']['sha256'], 'actual guest differs')
        cases = []
        for label in ('partial', 'barrier'):
            case = {'name': label, 'suffix_cycles': 2000}
            for key, filename in (('snapshot', label+'-pending.snap'),
                                  ('final_snapshot', label+'-complete.snap'),
                                  ('tape', label+'.io')):
                source = native.parent/filename
                require(sha(source) == result['files'][filename], 'native input changed: '+filename)
                case[key] = str(source)
                case[key+'_sha256'] = result['files'][filename]
            cases.append(case)
        workload = bundle['workloads']['notebook']
        assets = {name: bundle[key] if key == 'rom' else workload[key]
                  for name, key in (('/image.elf', 'image'), ('/machine.dtb', 'dtb'),
                                    ('/descriptor.bin', 'descriptor'), ('/boot.bin', 'rom'))}
        authority = {'schema': 'lemma-portable-backing-pending-authority/1',
                     'module': str(portable/'machine.mjs'), 'module_sha256': build['outputs']['machine.mjs'],
                     'wasm': str(portable/'machine.wasm'), 'wasm_sha256': build['outputs']['machine.wasm'],
                     'native_identity': origin['original_snapshot_identity'], 'portable_identity': identity,
                     'assets': assets, 'cases': cases, 'source_native': origin,
                     'native_result': {'path': str(native), 'sha256': sha(native)},
                     'wasm_build': {'path': str(portable/'build.json'), 'sha256': sha(portable/'build.json')}}
        path = out/'authority.json'
        path.write_text(json.dumps(authority, indent=2)+'\n')
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0):
            raise OSError('qualifier subreaper setup')
        script = ROOT/'scripts/check_wasm_backing_pending.mjs'
        argv = ['nix-shell', str(portable/'portable-host/tooling/silicon/wasm.nix'), '--run',
                shlex.join(['node', '--expose-gc', str(script), str(path), str(out/'actual')])]
        report['owned_children'] = run_fixture(argv, out/'run.log', 600, maximum_rss_kib=4194304)
        observed = json.loads((out/'actual/result.json').read_text())
        require(observed['status'] == 'PASS' and len(observed['cases']) == 2,
                'portable relation did not close both failed-I/O cuts')
        require(sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) <= 4 << 30,
                'retained output bound')
        report.update(status='PASS', actual={'path': str(out/'actual/result.json'),
                      'sha256': sha(out/'actual/result.json')}, source_inputs=254,
                      no_cold_prefix=True, no_original_medium_or_peer=True)
    except BaseException as error:
        report['error'] = repr(error)
    report['observer_sha256'] = sha(__file__)
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'error': report.get('error'), 'result': str(out/'result.json')}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
