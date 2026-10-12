#!/usr/bin/env python3
"""Prepare a local static bundle from source-validated guest and RTL artifacts."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def bundle(args):
    import silicon_guest
    if args.profile!='lemma-silicon-dev/0.3.0':raise ValueError('The local browser bundle currently admits profile0.3 only')
    source=args.wasm_build.resolve();m=json.loads((source/'build.json').read_text())
    if m.get('status')!='BUILT' or m.get('profile')!=args.profile:raise ValueError('Missing compatible Wasm build')
    for p,h in m['portable_inputs'].items():
        if sha(ROOT/p)!=h:raise ValueError('Wasm source changed: '+p)
    for p,h in m['sha256'].items():
        if sha(p)!=h:raise ValueError('RTL source changed: '+p)
    for p,h in m['configuration_includes'].items():
        if sha(p)!=h:raise ValueError('RTL configuration changed: '+p)
    if sha(Path(m['host_include_dir'])/'lemma_silicon_binding.h')!=m['host_binding_sha256']:
        raise ValueError('Portable host binding changed')
    if sha(ROOT/'flake.lock')!=m['host_toolchain_inputs']['flake.lock']:
        raise ValueError('Pinned portable tool inputs changed')
    for p,h in m['outputs'].items():
        if sha(source/p)!=h:raise ValueError('Wasm output changed: '+p)
    prepared={w:silicon_guest.prepared(w,args.profile) for w in ('notebook','initializer')}
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    def artifact(item,name):
        path=Path(item['path'])
        if sha(path)!=item['sha256']:raise ValueError('Guest artifact changed: '+str(path))
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        return {'path':name,'sha256':sha(dest)}
    result={'schema':'lemmasim-browser-bundle/1','profile':args.profile,'width':1650,'height':2200,
            'boot':'ELF-preload development boot','compiler':'native pinned Lean/LLVM helper; no browser compiler',
            'persistence':'OPFS SyncAccessHandle.flush; origin eviction and physical power loss unqualified',
            'wasm_build_sha256':sha(source/'build.json'),'workloads':{}}
    result['rom']=artifact(prepared['notebook']['rom'],'boot.bin')
    for w,data in prepared.items():
        entry=data['workloads'][w]
        result['workloads'][w]={k:artifact(entry[k],w+'/'+k+('.elf' if k=='image' else '.bin')) for k in ('image','dtb','descriptor')}
    for name in ('machine.mjs','machine.wasm'):shutil.copyfile(source/name,out/name)
    for p in (ROOT/'sim/browser').glob('*'):
        if p.suffix in ('.js','.html','.css'):shutil.copyfile(p,out/p.name)
    result['files']={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    (out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n')
    notice='Local development bundle. Existing Lean/compiler/application sources have no selected project-wide redistribution license. Do not infer permission to redistribute from this local build.\nWasm host adapter: Apache-2.0 per source notices; no repository-wide relicensing.\nCVW pinned '+m['core_revision']+': Apache-2.0 WITH SHL-2.1 and preserved MIT notices.\nVerilator5.052: LGPL-3.0-only OR Artistic-2.0; generated model licensing follows its upstream terms. Emscripten6.0.9: MIT; generated runtime dependencies retain their upstream notices.\nSource/tool input closure is retained in wasm-build.json. Physical conformance UNVERIFIED.\n'
    (out/'DEPENDENCIES.txt').write_text(notice);shutil.copyfile(source/'build.json',out/'wasm-build.json')
    print(out/'index.html')

def build(args):
    subprocess.run([sys.executable,str(ROOT/'scripts/silicon_wasm.py'),'--output-dir',str(args.wasm_build),'--profile',args.profile],check=True)
    bundle(args)
