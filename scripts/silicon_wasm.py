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
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from silicon_compute import prepare, source_manifest, snapshot_inputs, command

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def archived_build(directory, selected_profile):
    """Admit the complete original portable sources, without checkout fallback."""
    from lemmasim_browser import validated_bundle
    from silicon_guest_bundle import read_json
    directory, _ = validated_bundle(directory)
    bundle = read_json(directory/'bundle.json')
    original = read_json(directory/'wasm-build.json')
    if original['profile'] != selected_profile or not bundle.get('wasm_project_inputs'):
        raise ValueError('Portable recompilation requires a complete matching source bundle')
    original_root = Path(bundle['wasm_project_root'])
    def resolve(path):
        path = Path(path)
        try: relative = path.relative_to(original_root).as_posix()
        except ValueError:
            if not str(path).startswith('/nix/store/'):
                raise ValueError('Unarchived external portable input: '+str(path))
            return path
        item = bundle['wasm_project_inputs'].get(relative)
        if item is None:
            raise ValueError('Missing original portable input: '+relative)
        actual = directory/item['path']
        if digest(actual) != item['sha256']:
            raise ValueError('Changed original portable input: '+relative)
        return actual
    for key in ('sha256', 'configuration_includes', 'verilator_runtime_inputs'):
        for name, want in original[key].items():
            if digest(resolve(name)) != want:
                raise ValueError('Changed original portable input: '+name)
    # The original static bundle retains generator policy and profile bytes.
    # Reconstruct the header with that actual policy, then check its original
    # output digest. A current generator never supplies missing old bytes.
    spec = importlib.util.spec_from_file_location('lemma_archived_silicon_profile',
        resolve(original_root/'scripts/silicon_profile.py'))
    generator = importlib.util.module_from_spec(spec)
    previous_bytecode_policy=sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode=True
        spec.loader.exec_module(generator)
    finally:sys.dont_write_bytecode=previous_bytecode_policy
    profile = generator.profile(selected_profile)
    header = ('// Generated from the same authoritative binding as RTL and Lean.\n#pragma once\n'+
        ''.join(f'constexpr uint64_t BINDING_{k.upper()} = {v}ULL;\n'
                for k,v in generator.constants(profile).items()))
    if hashlib.sha256(header.encode()).hexdigest() != original['host_binding_sha256']:
        raise ValueError('Original generated portable host binding differs')
    return original, resolve, header, {
        'schema':'lemma-wasm-original-source-recompilation/1',
        'bundle_sha256':digest(directory/'bundle.json'),
        'build_sha256':digest(directory/'wasm-build.json'),
        'implementation':original['snapshot_identity'],
        'source_count':len(bundle['wasm_project_inputs']),
        'scope':'fresh host compilation of complete original RTL and portable runtime; no fresh guest compilation'}

def host_flags(preset):
    if preset == 'scalar':return []
    if preset == 'simd-lto':return ['-msimd128','-flto']
    raise ValueError('Unknown portable host optimization')

def archived_native_build(build, source_root, selected_profile):
    """Port a complete original canonical or Clocked13 producer.

    The native archive closes all original inputs and its separately bound
    selected JSON. The portable C ABI and build recipe are new host inputs;
    neither is represented as an input to the historical native compilation.
    """
    from silicon_guest import native_source_archive, USB_CLOCKED_PROFILE_NAME
    canonical = selected_profile == 'lemma-silicon-dev/0.3.0'
    if not canonical and selected_profile != USB_CLOCKED_PROFILE_NAME:
        raise ValueError('Native-to-portable source admission is canonical0.3 or Clocked13 only')
    source_root = Path(source_root).resolve()
    if canonical:
        # This validator checks the exact compiler inventory, identity header,
        # binary and selected JSON from the original native producer. A v1
        # archive did not retain that JSON and cannot supply this new port.
        from check_native_evaluation import original_native
        from silicon_guest import _read_unique_json
        build = Path(build).resolve()
        archive = _read_unique_json(build/'consumed-source-archive.json')
        if archive.get('schema') != 'lemma-original-native-component-archive/2':
            raise ValueError('Canonical portable producer requires its complete v2 native archive')
        manifest, original_root, relative_inputs = original_native(build)
        if source_root != original_root.resolve():
            raise ValueError('Canonical portable producer source root differs from its original archive')
        inputs = {str(ROOT/name):want for name,want in relative_inputs.items()}
        evidence = {'schema':'lemma-wasm-canonical-native-producer/1',
            'build_manifest_sha256':digest(build/'build.json'),
            'archive_sha256':digest(build/'consumed-source-archive.json'),
            'binary_sha256':manifest['binary_sha256'],
            'runtime_identity':manifest['snapshot_identity'],
            'source_count':len(relative_inputs),
            'scope':'unchanged complete canonical native producer; selected JSON archived; execution separate'}
    else:
        manifest, inputs, evidence = native_source_archive(build, source_root, selected_profile)
    def resolve(path):
        path = Path(path)
        if not path.is_absolute(): path = ROOT/path
        try: relative = path.relative_to(ROOT).as_posix()
        except ValueError: raise ValueError('Unarchived native portable input: '+str(path))
        expected = inputs.get(str(ROOT/relative))
        if expected is None: raise ValueError('Missing native portable input: '+relative)
        actual = source_root/relative
        if digest(actual) != expected: raise ValueError('Changed native portable input: '+relative)
        return actual
    header = resolve(Path(manifest['host_include_dir'])/'lemma_silicon_binding.h').read_text()
    if digest(resolve(Path(manifest['host_include_dir'])/'lemma_silicon_binding.h')) != manifest['host_binding_sha256']:
        raise ValueError('Original native host binding differs')
    original = {key:value for key,value in manifest.items() if key not in
                ('runtime_identity_header','build_argv','build_jobs','binary_sha256','snapshot_identity')}
    return original, resolve, header, {
        'schema':'lemma-wasm-native-source-port/1',
        'native':evidence,
        'original_snapshot_identity':manifest['snapshot_identity'],
        'native_source_inputs':inputs,
        'scope':'fresh portable host compilation of the complete original '+
            ('canonical0.3' if canonical else 'Clocked13')+' circuit and Machine; no fresh guest compilation'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--deps',type=Path,default=ROOT/'build/silicon/deps/cvw')
    p.add_argument('--profile',default='lemma-silicon-dev/0.3.0')
    p.add_argument('--source-bundle',type=Path,
                   help='complete original static browser source bundle; never mix with current RTL')
    p.add_argument('--native-build',type=Path,
                   help='original canonical0.3 or Clocked13 native build; requires its complete source archive')
    p.add_argument('--native-source-root',type=Path,
                   help='complete selected-profile native source archive; no checkout fallback')
    p.add_argument('--host-optimization',choices=('scalar','simd-lto'),default='scalar',
                   help='host compilation only; RTL clocks, scheduling and guest work are unchanged')
    a=p.parse_args()
    if bool(a.native_build)!=bool(a.native_source_root) or (a.source_bundle and a.native_build):
        p.error('native build/archive must be paired and cannot be mixed with a portable source bundle')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    dep=a.deps.resolve()
    if a.native_build:
        m,resolve,archived_header,recompilation=archived_native_build(a.native_build,a.native_source_root,a.profile)
        m['source_recompilation']=recompilation
        source_paths=[resolve(name) for name in m['sources']]
        include_paths=[resolve(next(name for name in m['configuration_includes']
                                    if Path(name).parent==Path(directory))).parent
                       if any(Path(name).parent==Path(directory) for name in m['configuration_includes'])
                       else a.native_source_root.resolve()/Path(directory).relative_to(ROOT)
                       for directory in m['include_dirs']]
        shell=ROOT/'tooling/silicon/wasm.nix'
        host_root=out/'portable-host';host_root.mkdir()
        # Relative Machine includes stay intact inside this bounded private
        # support tree. Every copied historical input was already validated.
        used=[*m['host_runtime'], 'flake.lock']
        for name in used:
            source=resolve(name);target=host_root/name
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for name in ('sim/browser/wasm_machine.cpp','tooling/silicon/wasm.nix'):
            target=host_root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        # wasm.nix resolves the original immutable flake lock through this tree.
        shell=host_root/'tooling/silicon/wasm.nix'
    elif a.source_bundle:
        m,resolve,archived_header,recompilation=archived_build(a.source_bundle,a.profile)
        for key in ('status','scope','snapshot_identity','wall_seconds','outputs','portable_compilation'):
            m.pop(key,None)
        m['source_recompilation']=recompilation
        original_root=Path(json.loads((a.source_bundle/'bundle.json').read_text())['wasm_project_root'])
        source_paths=[resolve(name) for name in m['sources']]
        include_paths=[a.source_bundle.resolve()/'wasm-sources'/Path(name).relative_to(original_root)
                       for name in m['include_dirs']]
        shell=resolve(original_root/'tooling/silicon/wasm.nix')
        host_root=a.source_bundle.resolve()/'wasm-sources'
    else:
        prepare(dep);m=source_manifest(dep,a.profile)
        source_paths=m['sources'];include_paths=m['include_dirs']
        shell=ROOT/'tooling/silicon/wasm.nix';host_root=ROOT
    portable=[ROOT/'sim/host/panel_pending.h',ROOT/'sim/host/usb_clock.h',ROOT/'sim/browser/wasm_machine.cpp',ROOT/'sim/host/backing_io.h',
              ROOT/'sim/host/backing_io.cpp',ROOT/'sim/host/backing_io_posix.h',ROOT/'sim/host/backing_io_posix.cpp',
              ROOT/'sim/rtl/host/machine_runtime.cpp',ROOT/'sim/rtl/host/machine_runtime.h',
              ROOT/'tooling/silicon/wasm.nix',Path(__file__).resolve()]
    if a.native_build:
        m['portable_inputs']={str(x.relative_to(ROOT)):digest(host_root/x.relative_to(ROOT))
                              for x in portable if x!=Path(__file__).resolve()}
        m['portable_inputs']['scripts/silicon_wasm.py']=digest(Path(__file__))
    elif a.source_bundle:
        m['portable_inputs']['scripts/silicon_wasm.py']=digest(Path(__file__))
    else:m['portable_inputs']={str(x.relative_to(ROOT)):digest(x) for x in portable}
    if a.host_optimization != 'scalar':
        m['portable_compilation']={'schema':'lemma-wasm-host-compilation/1',
            'preset':a.host_optimization,'flags':host_flags(a.host_optimization),
            'scope':'integer SIMD and LLVM LTO; no fast-math, circuit or virtual-time changes'}
    identity=hashlib.sha256(json.dumps(snapshot_inputs(m,dep),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    gen=out/'generated';gen.mkdir();(gen/'lemma_runtime_identity.h').write_text('#pragma once\n#define LEMMA_RUNTIME_IDENTITY "'+identity+'"\n')
    version_script="import json, subprocess; print(json.dumps({tool:subprocess.check_output([tool,'--version'],text=True) for tool in ['verilator','em++','node']}))"
    versions=json.loads(subprocess.check_output(
        ['nix-shell',str(shell),'--run',shlex.join(['python3','-c',version_script])],text=True))
    if a.source_bundle and versions != m['portable_tool_versions']:
        raise ValueError('Original portable tool versions differ')
    m['portable_tool_versions']=versions
    def run(argv,log,timeout=1200):
        with (out/log).open('w') as f:
            command(['nix-shell',shell,'--run',shlex.join(map(str,argv))],timeout=timeout,log=f)
    start=time.monotonic()
    run(['verilator','--cc','--savable','-Wno-fatal','--top-module','lemma_soc','--Mdir',out/'obj',
         *['-I'+str(x) for x in include_paths],*source_paths], 'generate.log',900)
    includes=subprocess.check_output(['nix-shell',shell,'--run','printf %s "$VERILATOR_ROOT"'],text=True)
    if not includes.startswith('/nix/store/'):
        version=subprocess.check_output(['nix-shell',shell,'--run','verilator -V'],text=True)
        import re
        includes=re.search(r'VERILATOR_ROOT\s*=\s*(/nix/store/\S+)',version).group(1)
    upstream_runtime=Path(includes)/'include'
    if a.source_bundle:
        for name,want in m['verilator_runtime_inputs'].items():
            if digest(name)!=want:raise ValueError('Original Verilator runtime changed: '+name)
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
    if a.source_bundle or a.native_build:
        host_binding=out/'binding';host_binding.mkdir()
        (host_binding/'lemma_silicon_binding.h').write_text(archived_header)
    else:host_binding=Path(m['host_include_dir'])
    cpp=sorted((out/'obj').glob('*.cpp'))
    if not cpp:raise RuntimeError('Verilator produced no core sources')
    run(['em++','-O3',*host_flags(a.host_optimization),'-std=c++17','-fexceptions','-include','cstdint',
         '-I'+str(out/'obj'),'-I'+str(runtime),'-I'+str(runtime/'vltstd'),
         '-I'+str(host_root/'sim/rtl/host'),'-I'+str(host_root/'sim/host'),
         '-I'+str(host_binding),'-I'+str(gen),
         *cpp,host_root/'sim/rtl/host/machine_runtime.cpp',host_root/'sim/host/backing_io.cpp',
         host_root/'sim/host/backing_io_posix.cpp',host_root/'sim/browser/wasm_machine.cpp',
         runtime/'verilated.cpp',runtime/'verilated_save.cpp',runtime/'verilated_threads.cpp',
         '--no-entry','-sWASM_BIGINT=1','-sALLOW_MEMORY_GROWTH=1','-sINITIAL_MEMORY=201326592',
         '-sMAXIMUM_MEMORY=2147483648','-sSTACK_SIZE=4194304','-sDISABLE_EXCEPTION_CATCHING=0',
         '-sMODULARIZE=1','-sEXPORT_ES6=1','-sEXPORT_NAME=createLemmaMachine','-sENVIRONMENT=worker,node',
         '-sFORCE_FILESYSTEM=1','-sEXPORTED_RUNTIME_METHODS=["ccall","FS","UTF8ToString","HEAPU8"]',
         '-o',out/'machine.mjs'],'compile.log')
    for name,want in m['portable_inputs'].items():
        actual=ROOT/name if name=='scripts/silicon_wasm.py' else host_root/name
        if digest(actual)!=want:raise RuntimeError('Portable source changed during build: '+name)
    for name,want in m['sha256'].items():
        if digest(resolve(name) if a.source_bundle or a.native_build else name)!=want:raise RuntimeError('RTL source changed during build: '+name)
    if a.source_bundle:
        from lemmasim_browser import validated_bundle
        validated_bundle(a.source_bundle)
    if a.native_build:
        archived_native_build(a.native_build,a.native_source_root,a.profile)
    for x in (ROOT/'sim/browser').glob('*'):
        if x.suffix in ('.html','.js','.css'):shutil.copyfile(x,out/x.name)
    m.update(status='BUILT',scope='real RTL Machine Wasm build; execution acceptance separate',
             snapshot_identity=identity,wall_seconds=time.monotonic()-start,
             outputs={x.name:digest(x) for x in [out/'machine.mjs',out/'machine.wasm']})
    (out/'build.json').write_text(json.dumps(m,indent=2)+'\n')
    print(out/'machine.mjs')

if __name__=='__main__':main()
