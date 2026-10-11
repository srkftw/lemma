#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pinned open CVW source closure and Verilator build; no guest execution helpers."""
from pathlib import Path
import argparse, hashlib, json, os, shlex, signal, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tooling/silicon'))
from apply_cvw import apply
from silicon_profile import profile, constants
REV='20f2af74e7aa76513e94012231d16567fa42648a'
SIM_SHELL=ROOT/'tooling/silicon/sim.nix'
BUILD_OPTIONS={'host_cflags':'-O3 -std=c++17',
               'make_flags':'OPT_FAST=-Os OPT_SLOW=',
               'verilator':['--cc','--exe','--build','-Wno-fatal','--top-module','lemma_soc']}

def command(args, cwd=ROOT, timeout=300, log=None):
    process=subprocess.Popen([str(a) for a in args],cwd=cwd,start_new_session=True,
                             stdout=log,stderr=subprocess.STDOUT if log else None)
    try:
        code=process.wait(timeout=timeout)
        if code: raise subprocess.CalledProcessError(code,args)
    finally:
        if process.poll() is None: os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=10)

def sources(dep, patched=False):
    # Only core closure; upstream demo SoC, peripheral and RVVI/testbench excluded.
    dirs=['cache','ebu','fpu','generic','hazard','ieu','ifu','lsu','mdu','mmu','privileged','wally']
    paths=[dep/'src/cvw.sv']+[p for d in dirs for p in sorted((dep/'src'/d).rglob('*.sv'))
                                if p.name!='wallypipelinedsoc.sv']
    if patched:
        patches=apply(dep,dep.parent/'cvw-patched')
        paths=[dep.parent/'cvw-patched'/p.relative_to(dep) if str(p.relative_to(dep)) in patches else p for p in paths]
    return paths

def prepare(dep):
    if not dep.exists():
        dep.parent.mkdir(parents=True,exist_ok=True)
        command(['git','clone','--no-checkout','https://github.com/openhwfoundation/cvw.git',dep],timeout=300)
        command(['git','checkout','--detach',REV],cwd=dep)
    got=subprocess.check_output(['git','rev-parse','HEAD'],cwd=dep,text=True).strip()
    if got!=REV: raise RuntimeError(f'CVW identity mismatch: {got}')
    if subprocess.check_output(['git','status','--porcelain'],cwd=dep,text=True).strip():
        raise RuntimeError('CVW source tree modified')
    missing=[str(p) for p in sources(dep) if 'SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1' not in p.read_text() and 'Permission is hereby granted, free of charge' not in p.read_text()]
    if missing: raise RuntimeError(f'CVW core source license inventory gaps: {missing}')

def source_manifest(dep):
    binding=dep.parent/'cvw-patched/lemma_silicon_binding.sv'
    fields=constants(profile())
    binding.parent.mkdir(parents=True,exist_ok=True)
    binding.write_text('// Generated from sim/profiles/lemma-silicon-dev-0.1.0.json\npackage lemma_silicon_binding;\n'+''.join(f"  localparam logic [63:0] {k.upper()} = 64'h{v:016x};\n" for k,v in fields.items())+'endpackage\n')
    header=dep.parent/'cvw-patched/lemma_silicon_binding.h'
    header.write_text('// Generated from the same authoritative binding as RTL and Lean.\n#pragma once\n'+''.join(f'constexpr uint64_t BINDING_{k.upper()} = {v}ULL;\n' for k,v in fields.items()))
    paths=[binding]+sources(dep,patched=True)+[ROOT/'tooling/silicon/config.vh',ROOT/'sim/rtl/lemma_compute.sv',ROOT/'sim/rtl/lemma_soc.sv',ROOT/'sim/rtl/lemma_pen.sv',ROOT/'sim/rtl/lemma_paper.sv',ROOT/'sim/rtl/lemma_block.sv',ROOT/'sim/rtl/lemma_register_ram.sv']
    return {'core_repository':'https://github.com/openhwfoundation/cvw','core_revision':REV,
            'core_license':'Apache-2.0 WITH SHL-2.1 and six preserved MIT-notice files','top':'lemma_soc',
            'build_options':BUILD_OPTIONS,
            'upstream_patch':{'path':'tooling/silicon/apply_cvw.py','sha256':hashlib.sha256((ROOT/'tooling/silicon/apply_cvw.py').read_bytes()).hexdigest(),'purpose':'architectural AHB HRESP access-fault delivery'},
            'sources':[str(p) for p in paths],
            'include_dirs':[str(ROOT/'tooling/silicon'),str(dep/'config/shared')],
            'host_include_dir':str(header.parent),
            'host_binding_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),
            'profile_sha256':hashlib.sha256((ROOT/'sim/profiles/lemma-silicon-dev-0.1.0.json').read_bytes()).hexdigest(),
            'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'host_adapter':{'path':'sim/rtl/host/main.cpp','sha256':hashlib.sha256((ROOT/'sim/rtl/host/main.cpp').read_bytes()).hexdigest()},
            'configuration_includes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((dep/'config/shared').glob('*.vh'))}}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('action',choices=['prepare','manifest','build'])
    ap.add_argument('--deps',type=Path,default=ROOT/'build/silicon/deps/cvw')
    ap.add_argument('--output-dir',type=Path,default=ROOT/'build/silicon/compute')
    ap.add_argument('--register-ram',action='store_true',help='bounded 4KiB register-memory configuration; scalar workloads only')
    ap.add_argument('--jobs',type=int,default=min(os.cpu_count() or 1,8));a=ap.parse_args()
    dep=a.deps.resolve(); out=a.output_dir.resolve();prepare(dep)
    if a.action=='prepare': return
    manifest=source_manifest(dep)
    manifest['configuration']='register-ram-4KiB' if a.register_ram else 'external-ram-128MiB'
    if a.action=='manifest': print(json.dumps(manifest,indent=2));return
    out.mkdir(parents=True,exist_ok=True)
    (out/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    args=['verilator',*manifest['build_options']['verilator'],
          '-j',str(a.jobs),'--Mdir',str(out/'obj'),'-o','lemma-rtl',
          '-MAKEFLAGS',manifest['build_options']['make_flags'],
          '-CFLAGS',manifest['build_options']['host_cflags']+' -I'+manifest['host_include_dir']]
    if a.register_ram: args+=['-GREGISTER_RAM=1']
    args += ['-I'+d for d in manifest['include_dirs']]+manifest['sources']+[str(ROOT/'sim/rtl/host/main.cpp')]
    args=['nix-shell',str(SIM_SHELL),'--run',shlex.join(args)]
    manifest['build_argv']=args
    manifest['build_jobs']=a.jobs
    with (out/'build.log').open('w') as log:
        try: command(args,timeout=900,log=log)
        except subprocess.SubprocessError:
            log.flush()
            print((out/'build.log').read_text()[-16000:],file=sys.stderr)
            raise
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest
           for p,digest in manifest['sha256'].items()):
        raise RuntimeError('RTL source changed during Verilator build; retained output is unqualified')
    if manifest['host_adapter']['sha256']!=hashlib.sha256((ROOT/'sim/rtl/host/main.cpp').read_bytes()).hexdigest():
        raise RuntimeError('Host adapter changed during Verilator build; retained output is unqualified')
    manifest['binary_sha256']=hashlib.sha256((out/'obj/lemma-rtl').read_bytes()).hexdigest()
    (out/'build.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(out/'obj/lemma-rtl')
if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.SubprocessError) as e: print(f'silicon: {e}',file=sys.stderr);sys.exit(1)
