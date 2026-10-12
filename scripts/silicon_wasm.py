#!/usr/bin/env python3
"""Build the maintained RTL Machine for a local Wasm worker; host tools only."""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_compute import prepare, source_manifest, snapshot_inputs, command

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--deps',type=Path,default=ROOT/'build/silicon/deps/cvw')
    p.add_argument('--profile',default='lemma-silicon-dev/0.3.0')
    a=p.parse_args();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    dep=a.deps.resolve();prepare(dep)
    m=source_manifest(dep,a.profile)
    portable=[ROOT/'sim/host/panel_pending.h',ROOT/'sim/browser/wasm_machine.cpp',ROOT/'sim/host/backing_io.h',
              ROOT/'sim/host/backing_io.cpp',ROOT/'sim/host/backing_io_posix.h',ROOT/'sim/host/backing_io_posix.cpp',
              ROOT/'sim/rtl/host/machine_runtime.cpp',ROOT/'sim/rtl/host/machine_runtime.h',
              ROOT/'tooling/silicon/wasm.nix',Path(__file__).resolve()]
    m['portable_inputs']={str(x.relative_to(ROOT)):digest(x) for x in portable}
    identity=hashlib.sha256(json.dumps(snapshot_inputs(m,dep),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    gen=out/'generated';gen.mkdir();(gen/'lemma_runtime_identity.h').write_text('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+identity+'"\n')
    shell=ROOT/'tooling/silicon/wasm.nix'
    version_script="import json, subprocess; print(json.dumps({tool:subprocess.check_output([tool,'--version'],text=True) for tool in ['verilator','em++','node']}))"
    m['portable_tool_versions']=json.loads(subprocess.check_output(
        ['nix-shell',str(shell),'--run',shlex.join(['python3','-c',version_script])],text=True))
    def run(argv,log,timeout=1200):
        with (out/log).open('w') as f:
            command(['nix-shell',shell,'--run',shlex.join(map(str,argv))],timeout=timeout,log=f)
    start=time.monotonic()
    run(['verilator','--cc','--savable','-Wno-fatal','--top-module','lemma_soc','--Mdir',out/'obj',
         *['-I'+x for x in m['include_dirs']],*m['sources']], 'generate.log',900)
    includes=subprocess.check_output(['nix-shell',shell,'--run','printf %s "$VERILATOR_ROOT"'],text=True)
    if not includes.startswith('/nix/store/'):
        version=subprocess.check_output(['nix-shell',shell,'--run','verilator -V'],text=True)
        import re
        includes=re.search(r'VERILATOR_ROOT\s*=\s*(/nix/store/\S+)',version).group(1)
    upstream_runtime=Path(includes)/'include'
    runtime=out/'verilator-portable'
    shutil.copytree(upstream_runtime,runtime)
    m['verilator_runtime_inputs']={str(x):digest(x) for x in sorted(upstream_runtime.rglob('*')) if x.is_file()}
    # Emscripten supplies POSIX-looking CPU_ZERO declarations, but cannot
    # bind a worker to a Linux CPU. The machine uses one evaluation thread;
    # exclude only these host affinity branches, preserving the upstream
    # portable fallback and every generated circuit evaluation.
    for name,guard in [('verilatedos_c.h','#if defined(__linux) || defined(CPU_ZERO)'),
                       ('verilated_threads.cpp','#if defined(__linux) || defined(CPU_ZERO) || defined(VL_CPPCHECK)')]:
        x=runtime/name;text=x.read_text()
        if text.count(guard)!=1:raise RuntimeError('Pinned host affinity guard changed: '+name)
        x.chmod(0o644)
        x.write_text(text.replace(guard,'#if !defined(__EMSCRIPTEN__) && ('+guard[4:]+')'))
    m['portable_verilator_patch']={name:digest(runtime/name) for name in ('verilatedos_c.h','verilated_threads.cpp')}
    identity=hashlib.sha256(json.dumps(snapshot_inputs(m,dep),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (gen/'lemma_runtime_identity.h').write_text('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+identity+'"\n')
    cpp=sorted((out/'obj').glob('*.cpp'))
    if not cpp:raise RuntimeError('Verilator produced no core sources')
    run(['em++','-O3','-std=c++17','-fexceptions','-include','cstdint',
         '-I'+str(out/'obj'),'-I'+str(runtime),'-I'+str(runtime/'vltstd'),
         '-I'+str(ROOT/'sim/rtl/host'),'-I'+str(ROOT/'sim/host'),
         '-I'+m['host_include_dir'],'-I'+str(gen),
         *cpp,ROOT/'sim/rtl/host/machine_runtime.cpp',ROOT/'sim/host/backing_io.cpp',
         ROOT/'sim/host/backing_io_posix.cpp',ROOT/'sim/browser/wasm_machine.cpp',
         runtime/'verilated.cpp',runtime/'verilated_save.cpp',runtime/'verilated_threads.cpp',
         '--no-entry','-sWASM_BIGINT=1','-sALLOW_MEMORY_GROWTH=1','-sINITIAL_MEMORY=201326592',
         '-sMAXIMUM_MEMORY=2147483648','-sSTACK_SIZE=4194304','-sDISABLE_EXCEPTION_CATCHING=0',
         '-sMODULARIZE=1','-sEXPORT_ES6=1','-sEXPORT_NAME=createLemmaMachine','-sENVIRONMENT=worker,node',
         '-sFORCE_FILESYSTEM=1','-sEXPORTED_RUNTIME_METHODS=["ccall","FS","UTF8ToString","HEAPU8"]',
         '-o',out/'machine.mjs'],'compile.log')
    for name,want in m['portable_inputs'].items():
        if digest(ROOT/name)!=want:raise RuntimeError('Portable source changed during build: '+name)
    for name,want in m['sha256'].items():
        if digest(name)!=want:raise RuntimeError('RTL source changed during build: '+name)
    for x in (ROOT/'sim/browser').glob('*'):
        if x.suffix in ('.html','.js','.css'):shutil.copyfile(x,out/x.name)
    m.update(status='BUILT',scope='real RTL Machine Wasm build; execution acceptance separate',
             snapshot_identity=identity,wall_seconds=time.monotonic()-start,
             outputs={x.name:digest(x) for x in [out/'machine.mjs',out/'machine.wasm']})
    (out/'build.json').write_text(json.dumps(m,indent=2)+'\n')
    print(out/'machine.mjs')

if __name__=='__main__':main()
