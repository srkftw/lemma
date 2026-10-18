#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host-only public-source Wasm64 QEMU/TCI producer and exact retained-build admission.

All software executing in the RV64 machine still comes from the maintained Lean
ELF. This builder compiles the upstream CPU and host controllers, never guest policy.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,signal,subprocess,tarfile,time,urllib.request
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MIN_FREE=2*1024**3

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def identity(root):return {str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def read(path):return json.loads(Path(path).read_text())
def sources():
    paths=[ROOT/'flake.lock',ROOT/'sim/profiles/lemma-silicon-dev-0.14.0.json',*HERE.glob('*')]
    paths += list((ROOT/'sim/host').glob('*'))+list((ROOT/'sim/companion').glob('backing_*'))
    paths += [ROOT/'tooling/lemmasim'/name for name in ('apply_qemu.py','patch_counter_clock.py','patch_uart_ingress.py')]
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(paths) if p.is_file()}

def command(argv,out,limit,env=None):
    start=time.monotonic();row={'argv':list(map(str,argv)),'wall_seconds':limit,'minimum_free_bytes':MIN_FREE,'result':'FAIL'}
    if shutil.disk_usage(out).free<MIN_FREE:raise RuntimeError('2GiB free-space floor before command')
    proc=None
    try:
        with (out/'command.log').open('ab') as f:
            proc=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
            while proc.poll() is None:
                if time.monotonic()-start>limit or shutil.disk_usage(out).free<MIN_FREE:
                    row['termination']='declared wall/free-space limit';os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                    break
                time.sleep(1)
        row['exit_code']=proc.returncode
        if proc.returncode:raise RuntimeError('Host producer command failed; inspect bounded command.log')
        row['result']='PASS'
    finally:
        if proc is not None and proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        row['elapsed_seconds']=time.monotonic()-start
        with (out/'commands.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')

def acquire(item,directory,cache):
    p=cache/item['filename'] if cache else directory/item['filename']
    if not p.exists():
        p=directory/item['filename'];temporary=p.with_suffix(p.suffix+'.pending')
        with urllib.request.urlopen(item['url'],timeout=120) as source,temporary.open('xb') as out:
            total=0
            while block:=source.read(1024*1024):
                total+=len(block)
                if total>256*1024*1024:raise ValueError('Public source exceeds256MiB bound')
                out.write(block)
        temporary.rename(p)
    if sha(p)!=item['sha256'] or ('bytes' in item and p.stat().st_size!=item['bytes']):raise ValueError('Public source identity differs: '+item['filename'])
    return p.resolve()

def extract(archive,out,skip_roms=False):
    with tarfile.open(archive) as t:
        members=[m for m in t if not (skip_roms and len(Path(m.name).parts)>1 and Path(m.name).parts[1]=='roms')]
        t.extractall(out,members=members,filter='data')

def cross(prefix):
    return """[host_machine]
system='emscripten'
cpu_family='wasm64'
cpu='wasm64'
endian='little'
[binaries]
c='emcc'
cpp='em++'
ar='emar'
ranlib='emranlib'
pkg-config=['pkg-config','--static']
[built-in options]
c_args=['-O2','-pthread','-DWASM_BIGINT','-sMEMORY64=1','-Wno-incompatible-function-pointer-types']
cpp_args=['-O2','-pthread','-DWASM_BIGINT','-sMEMORY64=1']
c_link_args=['-pthread','-sMEMORY64=1','-sWASM_BIGINT','-L"""+str(prefix/"lib")+"""']
cpp_link_args=['-pthread','-sMEMORY64=1','-sWASM_BIGINT','-L"""+str(prefix/"lib")+"""']
[properties]
needs_exe_wrapper=true
"""

def build(a):
    out=a.work_dir.resolve()
    # A fresh complete source/GLib/QEMU build needs additional staging space.
    if shutil.disk_usage(out.parent).free<4*1024**3:raise RuntimeError('Fresh Wasm64 build requires4GiB free staging space; retain existing artifacts')
    out.mkdir(exist_ok=False);initial=sources();report={'schema':'lemma-tci-public-build/1','result':'FAIL','inputs':initial,'producer_input_root':str(ROOT),'direct_helpers':bool(getattr(a,'direct_helpers',False)),'limits':{'wall_seconds_per_phase':a.timeout,'jobs':2,'minimum_free_bytes':MIN_FREE},'scope':'Host Wasm64 functional QEMU/TCI, exact maintained0.14 controller binding; no target compilation, exact RTL timing, durable browser storage, real-time or educational qualification'}
    try:
        downloads=out/'downloads';downloads.mkdir();archives={item['filename']:acquire(item,downloads,a.source_cache) for item in read(HERE/'dependencies.json')['sources']};write(out/'archives.json',{name:{'path':str(p),'sha256':sha(p)} for name,p in archives.items()})
        src=out/'source';src.mkdir();deps=out/'deps-source';deps.mkdir()
        extract(archives['qemu-11.1.1.tar.xz'],src,True)
        for name in ('zlib-1.3.2.tar.xz','libffi-3.5.2.tar.gz','pixman-0.44.2.tar.gz','glib-2.84.0.tar.xz'):extract(archives[name],deps)
        q=src/'qemu-11.1.1';extract(archives['dtc-b6910bec11614980a21e46fbccc35934b671bd81.tar.gz'],q/'subprojects');(q/'subprojects/dtc-b6910bec11614980a21e46fbccc35934b671bd81').rename(q/'subprojects/dtc')
        packagecache=deps/'glib-2.84.0/subprojects/packagecache';packagecache.mkdir(exist_ok=True)
        for name in ('pcre2-10.44.tar.bz2','pcre2_10.44-2_patch.zip'):shutil.copyfile(archives[name],packagecache/name)
        for script in ('apply_qemu.py','patch_counter_clock.py','patch_uart_ingress.py'):
            argv=['python3',str(ROOT/'tooling/lemmasim'/script),str(q)]
            if script=='apply_qemu.py':argv+=['--repository',str(ROOT),'--silicon-profile',str(ROOT/'sim/profiles/lemma-silicon-dev-0.14.0.json')]
            if script=='patch_uart_ingress.py':argv+=['--header',str(ROOT/'sim/host/lemma_uart_ingress.h'),'--implementation',str(ROOT/'sim/host/lemma_uart_qemu.inc.c')]
            command(argv,out,a.timeout)
        command(['python3',str(HERE/'patch_wasm.py'),str(q),'--report',str(out/'wasm-patch.json')],out,a.timeout)
        if getattr(a,'direct_helpers',False):
            command(['python3',str(HERE/'patch_tci_helpers.py'),str(q),'--report',str(out/'typed-helpers-patch.json')],out,a.timeout)
        prefix=out/'prefix';prefix.mkdir();(prefix/'lib').mkdir();crossfile=out/'cross.meson';crossfile.write_text(cross(prefix))
        quote=shlex.quote;script=out/'build-host.sh'
        preamble='set -euo pipefail\nexport EMCC_CORES=1 BINARYEN_CORES=1 AR=emar RANLIB=emranlib\n'+''.join('export '+key+'='+quote(value)+'\n' for key,value in {'EM_CACHE':str(out/'emcache'),'CFLAGS':'-O2 -pthread -DWASM_BIGINT -sMEMORY64=1','CXXFLAGS':'-O2 -pthread -DWASM_BIGINT -sMEMORY64=1','LDFLAGS':'-sWASM_BIGINT -sMEMORY64=1 -pthread -L'+str(prefix/'lib'),'PKG_CONFIG_LIBDIR':str(prefix/'lib/pkgconfig'),'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig'),'EM_PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig')}.items())
        script.write_text(preamble+f'''
cd {quote(str(deps/'zlib-1.3.2'))}
emconfigure ./configure --prefix={quote(str(prefix))} --static
emmake make -j2
emmake make install
cd {quote(str(deps/'libffi-3.5.2'))}
emconfigure ./configure --host=wasm64-unknown-linux --prefix={quote(str(prefix))} --enable-static --disable-shared --disable-dependency-tracking --disable-builddir --disable-multi-os-directory --disable-raw-api --disable-docs
emmake make -j2
emmake make install SUBDIRS=include
cd {quote(str(deps/'pixman-0.44.2'))}
meson setup _build --prefix={quote(str(prefix))} --cross-file={quote(str(crossfile))} --default-library=static --buildtype=release -Dtests=disabled -Ddemos=disabled
ninja -C _build -j2
meson install -C _build --no-rebuild
cd {quote(str(out))}
emcc $CFLAGS -c {quote(str(HERE/'res_query_unavailable.c'))} -fPIC -o res_query_unavailable.o
emar rcs {quote(str(prefix/'lib/libresolv.a'))} res_query_unavailable.o
cd {quote(str(deps/'glib-2.84.0'))}
meson setup _build --prefix={quote(str(prefix))} --cross-file={quote(str(crossfile))} --default-library=static --buildtype=release --wrap-mode=nodownload --force-fallback-for=pcre2 -Dselinux=disabled -Dxattr=false -Dlibmount=disabled -Dnls=disabled -Dtests=false -Dintrospection=disabled -Dsysprof=disabled
sed -i -E '/#define HAVE_POSIX_SPAWN 1/d; /#define HAVE_PTHREAD_GETNAME_NP 1/d' _build/config.h
ninja -C _build -j2
meson install -C _build --no-rebuild
''')
        command(['nix-shell',str(HERE/'shell.nix'),'--run','bash '+quote(str(script))],out,a.timeout)
        obj=out/'obj';obj.mkdir();script=out/'build-qemu.sh';script.write_text(preamble+f'''cd {quote(str(obj))}
{quote(str(q/'configure'))} --cpu=wasm64 --cc=emcc --cxx=em++ --enable-tcg-interpreter --target-list=riscv64-softmmu --without-default-features --without-default-devices --with-devices-riscv64=lemma --disable-tools --disable-docs --disable-guest-agent --disable-werror --disable-download --disable-install-blobs --disable-rust --enable-pixman --enable-fdt=internal --extra-cflags=-DEMSCRIPTEN=__EMSCRIPTEN__ --extra-ldflags='-sMODULARIZE=1 -sEXPORT_NAME=createLemmaQemu -sEXPORTED_RUNTIME_METHODS=addFunction,removeFunction,TTY,FS,ccall,UTF8ToString'
ninja -j2 qemu-system-riscv64.js
''')
        write(out/'source-inputs.json',identity(q));write(out/'prefix-inputs.json',identity(prefix))
        command(['nix-shell',str(HERE/'shell.nix'),'--run','bash '+quote(str(script))],out,a.timeout)
        if initial!=sources() or read(out/'source-inputs.json')!=identity(q):raise ValueError('Source changed during actual Wasm64 production')
        report.update(completed_build_metadata(out,q,obj))
        report['result']='BUILT_WASM64_QEMU_TCI'
    finally:write(out/'build.json',report)

def completed_build_metadata(out,source_root,build_dir):
    """Bind successful compiler outputs to the actual predeclared source inventory.

    This is metadata production, never evidence that a dummy/module fixture ran.
    """
    inventory=out/'source-inputs.json'
    observed=identity(source_root)
    if not observed or read(inventory)!=observed:
        raise ValueError('Actual source changed or missing at producer completion')
    outputs={}
    for name in ('qemu-system-riscv64.js','qemu-system-riscv64.wasm'):
        p=build_dir/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size==0:
            raise ValueError('Required real compiler output missing:'+name)
        if name.endswith('.wasm'):
            with p.open('rb') as f:
                if f.read(8)!=b'\x00asm\x01\x00\x00\x00':raise ValueError('Compiler output is not a WebAssembly1 module')
        outputs[name]={'sha256':sha(p),'bytes':p.stat().st_size}
    return {'outputs':outputs,'source_closure_sha256':sha(inventory),
            'source_file_count':len(observed),'exit_code':0}

def retained_producer_input_root(report,receipt):
    """Keep prototype and ordinary fresh producer schemas explicitly distinct."""
    schema=report.get('schema')
    if schema=='lemma-tci-public-build/1':
        if report.get('producer_input_root')!=str(ROOT):
            raise ValueError('Fresh producer repository input root differs')
        return ROOT
    if schema=='lemma-tci-wasm-build/1':return receipt.parent.parent
    raise ValueError('Unknown retained host producer schema')

def retained_source_identity(report,inventory,source_root):
    observed=identity(source_root)
    if report.get('result')!='BUILT_WASM64_QEMU_TCI' or type(report.get('exit_code')) is not int or report['exit_code']!=0 or type(report.get('source_file_count')) is not int or not observed or len(observed)!=report['source_file_count'] or sha(inventory)!=report.get('source_closure_sha256') or read(inventory)!=observed:
        raise ValueError('Retained actual source/production identity differs')
    return observed

def admit(a):
    """Retain exact already-built prototype outputs, with a separate admission receipt."""
    initial=sources()
    if shutil.disk_usage(a.output_dir.resolve().parent).free<MIN_FREE+32*1024*1024:raise RuntimeError('2GiB free-space floor plus32MiB retained runtime staging')
    r=read(a.receipt);inventory=a.receipt.parent/'source-inputs.json'
    input_root=retained_producer_input_root(r,a.receipt)
    retained_source_identity(r,inventory,a.source_root)
    for name,digest in r.get('inputs',{}).items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(input_root/name)!=digest:raise ValueError('Recorded host producer input differs:'+name)
    if not r.get('inputs'):raise ValueError('Missing original host producer input closure')
    selected=r.get('direct_helpers',False)
    if not isinstance(selected,bool):raise ValueError('Unknown helper route declaration')
    helper_manifest=read(HERE/'typed_helpers.json')
    for name,expected in helper_manifest['sources'].items():
        if sha(a.source_root/name)!=expected['after' if selected else 'before']:raise ValueError('Declared exact helper route source differs:'+name)
    control=a.source_root/'hw/riscv/lemma_browser_control.inc.c'
    if sha(control)!=sha(HERE/'lemma_browser_control.inc.c') or (a.source_root/'VERSION').read_text().strip()!='11.1.1':raise ValueError('Retained runtime has another QEMU/control implementation')
    for name in ('lemma_model.c','lemma_model.h','lemma_multimodal.c','lemma_multimodal.h','lemma_multimodal_qemu.inc.c','lemma_fast_block.c'):
        if sha(a.source_root/'hw/riscv'/name)!=sha(ROOT/'sim/host'/name):raise ValueError('Retained controller source differs:'+name)
    out=a.output_dir.resolve();out.mkdir(exist_ok=False)
    for name in ('qemu-system-riscv64.js','qemu-system-riscv64.wasm'):
        p=a.build_dir/name;item=r['outputs'][name]
        if sha(p)!=item['sha256'] or p.stat().st_size!=item['bytes']:raise ValueError('Retained compiled output differs:'+name)
        shutil.copyfile(p,out/name)
    for name in ('dependencies.json','lemma_browser_control.inc.c','patch_wasm.py','shell.nix','build.py','res_query_unavailable.c','patch_tci_helpers.py','typed_helpers.json','tci-typed-helpers.patch'):shutil.copyfile(HERE/name,out/name)
    shutil.copyfile(inventory,out/'source-inputs.json');shutil.copyfile(a.receipt,out/'original-build.json')
    shutil.copyfile(a.source_root/'COPYING',out/'COPYING.QEMU')
    for name in ('lemma_qemu.c','lemma_silicon_fast.h','lemma_model.c','lemma_model.h','lemma_multimodal.c','lemma_multimodal.h','lemma_multimodal_qemu.inc.c','lemma_fast_block.c','lemma_uart_ingress.h','lemma_uart_qemu.inc.c'):
        destination=out/'controller-source'/name;destination.parent.mkdir(exist_ok=True);shutil.copyfile(a.source_root/'hw/riscv'/name,destination)
    (out/'package.json').write_text('{"type":"module"}\n')
    if initial!=sources() or read(inventory)!=identity(a.source_root):raise ValueError('Retained source changed during admission')
    write(out/'runtime.json',{'schema':'lemma-tci-retained-runtime/2','abi':'lemma-qemu-wasm-control/1','admission_inputs':initial,'original_build':{'path':str(a.receipt.resolve()),'sha256':sha(a.receipt)},'original_source_root':str(a.source_root.resolve()),'direct_helpers':selected,'files':identity(out),'scope':'Exact retained actual Wasm64 QEMU/TCI compiled outputs and complete source inventory, independently source-bound retained-build admission. Not fresh compilation, exact RTL timing, browser durability or whole-workbook execution.'})
    print(out/'runtime.json')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    b=sub.add_parser('build');b.add_argument('--work-dir',type=Path,required=True);b.add_argument('--source-cache',type=Path);b.add_argument('--timeout',type=int,default=900);b.add_argument('--direct-helpers',action='store_true',help='Compile exact declared C helper thunks; preserve explicitly identified libffi fallbacks')
    b=sub.add_parser('admit');b.add_argument('--receipt',type=Path,required=True);b.add_argument('--source-root',type=Path,required=True);b.add_argument('--build-dir',type=Path,required=True);b.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    if a.action=='build':
        if not 30<=a.timeout<=1800:raise ValueError('Host phase deadline outside30..1800s')
        build(a)
    else:admit(a)
if __name__=='__main__':main()
