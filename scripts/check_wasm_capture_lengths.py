#!/usr/bin/env python3
"""Execute actual 32-bit backing capture APIs and reject the original shift defect.

This is host-boundary qualification. No firmware, journal or document policy
executes here, and no host object or runtime enters the RV64 image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CPP = ['sim/host/backing_io.cpp', 'sim/host/backing_io_posix.cpp',
       'sim/companion/backing_peer.cpp', 'sim/companion/backing_c.cpp',
       'tests/lemmasim/wasm_capture_lengths.cpp']
HEADERS = ['sim/host/backing_io.h', 'sim/host/backing_io_posix.h',
           'sim/companion/backing_peer.h', 'sim/companion/backing_c.h']
FLAGS = ['-O3', '-msimd128', '-flto', '-std=c++17', '-fexceptions',
         '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
         '-sASSERTIONS=2', '-sALLOW_MEMORY_GROWTH=1',
         '-sMAXIMUM_MEMORY=1073741824', '-sSTACK_SIZE=4194304',
         '-sDISABLE_EXCEPTION_CATCHING=0', '-sENVIRONMENT=node']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    out = args.work_dir.resolve()
    if not out.is_relative_to(ROOT/'build') or out.exists():
        raise ValueError('Require unused task-owned output under build')
    out.mkdir(parents=True)
    start = time.monotonic()
    inputs = {name:sha(ROOT/name) for name in CPP+HEADERS+
              ['tooling/silicon/wasm.nix','flake.lock',str(Path(__file__).relative_to(ROOT))]}
    archive = out/'source'
    for name in inputs:
        destination = archive/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,destination)
    report = {'schema':'lemma-wasm-capture-lengths/1','status':'FAIL','scope':__doc__,
              'inputs':inputs,'flags':FLAGS,'commands':[],
              'bounds':{'whole_host_seconds':600,'compile_seconds':180,'run_seconds':30,
                        'wasm_heap_bytes':1073741824,'host_output_bytes':16777216}}
    (out/'plan.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(argv,name,timeout,expected=0):
        if time.monotonic()-start >= 600:
            raise ValueError('Original whole host bound exceeded')
        command = ['nix-shell',str(archive/'tooling/silicon/wasm.nix'),
                   '--run',shlex.join(map(str,argv))]
        report['commands'].append(command)
        result = subprocess.run(command,cwd=archive,capture_output=True,text=True,timeout=timeout)
        (out/name).write_text(result.stdout+result.stderr)
        if (expected==0 and result.returncode!=0) or (expected!=0 and result.returncode==0):
            raise ValueError('Unexpected actual exit status: '+name)
        return result
    try:
        tools = {}
        for tool in ('em++','node'):
            tools[tool] = run([tool,'--version'],tool.replace('+','p')+'-version.log',30).stdout
        report['tools'] = tools
        normal = out/'normal.js'
        run(['em++',*FLAGS,*CPP,'-o',normal],'compile.log',180)
        completed = run(['node',normal],'run.log',30)
        if 'PASS actual32-bit backing WRITE/barrier/READ captures; full64-bit lengths and CRCs' not in completed.stdout:
            raise ValueError('Nonempty actual capture corpus missing')
        code = (archive/'sim/companion/backing_c.cpp').read_text()
        if code.count('uint64_t(wire.size())>>(8*i)') != 2:
            raise ValueError('Exact original size-shift mutation sites differ')
        mutant = archive/'sim/companion/backing_c_mutant.cpp'
        mutant.write_text(code.replace('uint64_t(wire.size())>>(8*i)','wire.size()>>(8*i)'))
        mutant_cpp = [str(mutant) if x=='sim/companion/backing_c.cpp' else x for x in CPP]
        run(['em++',*FLAGS,*mutant_cpp,'-o',out/'mutant.js'],'mutant-compile.log',180)
        failed = run(['node',out/'mutant.js'],'mutant-run.log',30,expected=1)
        if 'shift exponent 32 is too large for 32-bit type' not in failed.stderr:
            raise ValueError('Mutant did not expose original undefined shift')
        for name,digest in inputs.items():
            if sha(ROOT/name)!=digest or sha(archive/name)!=digest:
                raise ValueError('Original or archived input changed: '+name)
        if sum(x.stat().st_size for x in out.rglob('*') if x.is_file()) > 16777216:
            raise ValueError('Original output bound exceeded')
        report.update(status='PASS_ACTUAL_WASM32_CAPTURE_AND_ORIGINAL_SHIFT_MUTANT',
            actual_operations=['WRITE512','barrier','READ512'],
            wire_versions=['LMIOLOG1','LMIOLOG2'], complete_high_length_bytes_checked=True,
            all_record_crcs_checked=True, undefined_shift_mutant_exit=failed.returncode,
            outputs={x.name:sha(x) for x in out.glob('*.wasm')})
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        report['error'] = str(error)
    report['host_seconds'] = time.monotonic()-start
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
