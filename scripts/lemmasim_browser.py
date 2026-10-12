#!/usr/bin/env python3
"""Prepare a local static bundle from source-validated guest and RTL artifacts."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import mimetypes
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
    guest_archive=getattr(args,'guest_bundle',None)
    if guest_archive is None:
        prepared={w:silicon_guest.prepared(w,args.profile) for w in ('notebook','initializer')}
    else:
        import silicon_guest_bundle
        prepared={w:silicon_guest_bundle.prepared(guest_archive,'rtl',w,args.profile)
                  for w in ('notebook','initializer')}
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
    if guest_archive is not None:
        result['guest_archive']={'manifest_sha256':sha(guest_archive/'bundle.json'),
            'source_commit':prepared['notebook']['native_bundle']['source_commit'],
            'scope':'unchanged validated archived genuine guest on current source-bound RTL/Wasm; not fresh target compilation'}
    result['rom']=artifact(prepared['notebook']['rom'],'boot.bin')
    for w,data in prepared.items():
        entry=data['workloads'][w]
        result['workloads'][w]={k:artifact(entry[k],w+'/'+k+('.elf' if k=='image' else '.bin')) for k in ('image','dtb','descriptor')}
        result['workloads'][w]['qualification']={k:artifact(entry[k],w+'/'+k+'.json')
            for k in ('build','provenance','audit','capacity') if k in entry}
    for name in ('machine.mjs','machine.wasm'):shutil.copyfile(source/name,out/name)
    for p in (ROOT/'sim/browser').glob('*'):
        if p.suffix in ('.js','.html','.css'):shutil.copyfile(p,out/p.name)
    result['files']={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n')
    notice='Local development bundle. Existing Lean/compiler/application sources have no selected project-wide redistribution license. Do not infer permission to redistribute from this local build.\nWasm host adapter: Apache-2.0 per source notices; no repository-wide relicensing.\nCVW pinned '+m['core_revision']+': Apache-2.0 WITH SHL-2.1 and preserved MIT notices.\nVerilator5.052: LGPL-3.0-only OR Artistic-2.0; generated model licensing follows its upstream terms. Emscripten6.0.9: MIT; generated runtime dependencies retain their upstream notices.\nSource/tool input closure is retained in wasm-build.json. Physical conformance UNVERIFIED.\n'
    (out/'DEPENDENCIES.txt').write_text(notice);shutil.copyfile(source/'build.json',out/'wasm-build.json')
    print(out/'index.html')

def build(args):
    subprocess.run([sys.executable,str(ROOT/'scripts/silicon_wasm.py'),'--output-dir',str(args.wasm_build),'--profile',args.profile],check=True)
    bundle(args)

def validated_bundle(directory):
    """Admit immutable packaged inputs, independent of the current checkout.

    This validates identities, not an unqualified notebook acceptance result.
    Only inventoried bytes are served; no file upload or directory traversal.
    """
    from silicon_guest_bundle import read_json
    directory=Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir():raise ValueError('Invalid browser bundle directory')
    manifest_path=directory/'bundle.json'
    if manifest_path.is_symlink():raise ValueError('Symlinked browser manifest')
    m=read_json(manifest_path)
    if m.get('schema')!='lemmasim-browser-bundle/1' or m.get('profile')!='lemma-silicon-dev/0.3.0' or (m.get('width'),m.get('height'))!=(1650,2200):
        raise ValueError('Unsupported browser machine bundle')
    files=m.get('files')
    if not isinstance(files,dict) or not 1<=len(files)<=2048:raise ValueError('Invalid browser inventory')
    total=0
    for name,digest in files.items():
        if not isinstance(name,str) or not name or name!=Path(name).as_posix() or Path(name).is_absolute() or any(p in ('..','.') for p in name.split('/')):
            raise ValueError('Invalid browser inventory path')
        if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid browser checksum')
        path=directory/name
        if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():raise ValueError('Missing/symlinked browser artifact: '+name)
        total+=path.stat().st_size
        if total>1024*1024*1024:raise ValueError('Browser bundle exceeds byte bound')
        if sha(path)!=digest:raise ValueError('Changed browser artifact: '+name)
    if not {'index.html','worker.js','app.js','machine.mjs','machine.wasm','boot.bin'}<=files.keys():raise ValueError('Incomplete browser launch bundle')
    for workload in ('notebook','initializer'):
        entry=m.get('workloads',{}).get(workload,{})
        for kind in ('image','dtb','descriptor'):
            item=entry.get(kind,{})
            if not isinstance(item,dict) or item.get('path') not in files or files[item['path']]!=item.get('sha256'):
                raise ValueError('Unbound browser guest '+workload+'/'+kind)
    if m.get('rom',{}).get('path')!='boot.bin' or m['rom'].get('sha256')!=files['boot.bin']:raise ValueError('Unbound browser boot artifact')
    wasm=directory/'wasm-build.json'
    if wasm.is_symlink() or not wasm.is_file() or sha(wasm)!=m.get('wasm_build_sha256'):raise ValueError('Unbound Wasm build manifest')
    build=read_json(wasm)
    if build.get('status')!='BUILT' or build.get('profile')!=m['profile']:raise ValueError('Incompatible Wasm build')
    for name in ('machine.mjs','machine.wasm'):
        if build.get('outputs',{}).get(name)!=files[name]:raise ValueError('Unbound Wasm output '+name)
    allowed=set(files)|{'bundle.json','wasm-build.json','DEPENDENCIES.txt'}
    for path in directory.rglob('*'):
        if path.is_symlink() or (path.is_file() and path.relative_to(directory).as_posix() not in allowed):raise ValueError('Unlisted browser bundle artifact')
    # Metadata served to the worker is frozen to the same validated identity.
    return directory,{**files,'bundle.json':sha(manifest_path),'wasm-build.json':sha(wasm)}

def local_server(directory,port):
    directory,identities=validated_bundle(directory)
    if type(port) is not int or not 0<=port<=65535:raise ValueError('Invalid browser port')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):self.respond(False)
        def do_HEAD(self):self.respond(True)
        def respond(self,head):
            name=unquote(urlsplit(self.path).path)
            name='index.html' if name=='/' else name.removeprefix('/')
            if name not in identities:
                self.send_error(404,'Not an inventoried bundle file');return
            path=directory/name
            try:
                if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Changed artifact path')
                content=path.read_bytes()
                if hashlib.sha256(content).hexdigest()!=identities[name]:raise ValueError('Changed artifact bytes')
            except (OSError,ValueError):
                self.send_error(503,'Bundle identity changed; restart with a valid bundle');return
            self.send_response(200)
            self.send_header('Content-Type','application/wasm' if name.endswith('.wasm') else mimetypes.guess_type(name)[0] or 'application/octet-stream')
            self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store')
            self.send_header('Cross-Origin-Opener-Policy','same-origin')
            self.send_header('Cross-Origin-Embedder-Policy','require-corp')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            if not head:self.wfile.write(content)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server

def serve(args):
    if not 1024<=args.port<=65535:raise ValueError('Browser port must be1024..65535')
    server=local_server(args.bundle,args.port)
    print(f'Validated local development machine: http://127.0.0.1:{server.server_port}/',flush=True)
    try:server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:server.server_close()
