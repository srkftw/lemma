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

def validate_wasm_inputs(source,m,input_bundle=None,source_archive=None):
    """Check the complete recorded portable build/generation closure on reuse.

    Generated binding bytes alone cannot certify unchanged generator policy.
    This checks actual files before packaging, without rebuilding the machine.
    The immutable packaged launch validator remains independent of checkout.
    """
    archive=None;consumed={};browser_archive=False;original_sources=None
    if source_archive is not None:
        if input_bundle is not None:raise ValueError('Choose one exact Wasm source provider')
        source_archive=Path(source_archive).resolve()
        original_sources=json.loads((source_archive/'consumed-source-archive.json').read_text())
        if (original_sources.get('schema')!='lemma-original-portable-consumed-source-archive/1' or
            original_sources.get('original_manifest_sha256')!=sha(source/'build.json') or
            original_sources.get('implementation')!=m.get('snapshot_identity') or
            original_sources.get('outputs')!=m.get('outputs') or not isinstance(original_sources.get('inputs'),dict)):
            raise ValueError('Portable source archive does not bind original producer')
        expected={}
        for group in ('sha256','configuration_includes','binding_generator_inputs','portable_inputs','verilator_runtime_inputs','host_toolchain_inputs','host_runtime'):
            for name,want in m.get(group,{}).items():
                path=Path(name);path=path if path.is_absolute() else ROOT/path
                expected[str(path)]=want
        for group in ('build_driver','upstream_patch'):
            item=m[group];expected[str(ROOT/item['path'])]=item['sha256']
        expected[str(Path(m['host_include_dir'])/'lemma_silicon_binding.h')]=m['host_binding_sha256']
        actual={item.get('original_path'):item.get('sha256') for item in original_sources['inputs'].values()}
        if actual!=expected:raise ValueError('Portable archive input inventory differs from complete original producer')
    if input_bundle is not None:
        from silicon_guest_bundle import read_json,inventory
        input_bundle=Path(input_bundle).resolve()
        archive=read_json(input_bundle/'bundle.json')
        if archive.get('schema')=='lemmasim-browser-bundle/1':
            validated_bundle(input_bundle);browser_archive=True
        else:inventory(input_bundle,archive)
    def check(path,want,label):
        resolved=path
        try:relative=path.relative_to(ROOT)
        except ValueError:relative=None
        if original_sources is not None:
            alias=relative.as_posix() if relative is not None else 'immutable-external/'+path.as_posix().lstrip('/')
            item=original_sources['inputs'].get(alias,{})
            if item.get('original_path')!=str(path) or item.get('sha256')!=want:raise ValueError('Missing original portable archive input: '+label)
            resolved=source_archive/'consumed-source-root'/alias
        if archive is not None and relative is not None:
            if browser_archive:
                item=archive.get('wasm_project_inputs',{}).get(relative.as_posix())
                if item is not None and item.get('sha256')==want:
                    resolved=input_bundle/item['path']
                elif relative.as_posix()=='scripts/silicon_wasm.py' and m.get('source_recompilation'):
                    # A fresh host compilation uses the current compiler
                    # driver. All old RTL/runtime bytes come from the archive.
                    original=read_json(input_bundle/'wasm-build.json')
                    receipt=m['source_recompilation']
                    if (receipt.get('schema')!='lemma-wasm-original-source-recompilation/1' or
                        receipt.get('bundle_sha256')!=sha(input_bundle/'bundle.json') or
                        receipt.get('build_sha256')!=sha(input_bundle/'wasm-build.json') or
                        receipt.get('implementation')!=original.get('snapshot_identity') or
                        receipt.get('source_count')!=len(archive.get('wasm_project_inputs',{}))):
                        raise ValueError('Fresh portable driver lacks its exact original source receipt')
                    resolved=path
                else:raise ValueError('Missing original browser consumed input: '+label)
            else:
                from silicon_guest_bundle import origin_destination
                try:resolved=input_bundle/origin_destination(archive,path,want)
                except ValueError:
                    # A native archive need not consume browser-only sources.
                    # Their actual unchanged bytes must still match the original
                    # Wasm receipt; a changed checkout is never a fallback.
                    resolved=path
        if sha(resolved)!=want:raise ValueError('Wasm input changed: '+label)
        if relative is not None:
            consumed[relative.as_posix()]={'path':resolved,'sha256':want}
    def inputs(key,relative):
        values=m.get(key)
        if not isinstance(values,dict) or not values:raise ValueError('Missing Wasm inputs: '+key)
        for name,want in values.items():
            if not isinstance(name,str) or not isinstance(want,str) or not re.fullmatch('[a-f0-9]{64}',want):
                raise ValueError('Malformed Wasm input: '+key)
            path=Path(name)
            if relative:
                if path.is_absolute() or '..' in path.parts:raise ValueError('Escaping Wasm input: '+name)
                path=ROOT/path
            elif not path.is_absolute():raise ValueError('Nonabsolute Wasm generated/tool input: '+name)
            check(path,want,name)
    for key in ('portable_inputs','binding_generator_inputs','host_toolchain_inputs','host_runtime'):
        inputs(key,True)
    for key in ('sha256','configuration_includes','verilator_runtime_inputs'):
        inputs(key,False)
    for key in ('build_driver','upstream_patch'):
        item=m.get(key)
        if not isinstance(item,dict) or not isinstance(item.get('path'),str) or not isinstance(item.get('sha256'),str):
            raise ValueError('Missing Wasm generation identity: '+key)
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or not re.fullmatch('[a-f0-9]{64}',item['sha256']):
            raise ValueError('Malformed Wasm generation identity: '+key)
        check(ROOT/path,item['sha256'],key)
    profile='sim/profiles/'+m['profile'].replace('/','-')+'.json'
    if m['binding_generator_inputs'].get(profile)!=m.get('profile_sha256'):
        raise ValueError('Wasm binding profile is not source bound')
    binding_header=Path(m['host_include_dir'])/'lemma_silicon_binding.h'
    if original_sources is not None:
        check(binding_header,m['host_binding_sha256'],'host binding')
    if original_sources is None and sha(binding_header)!=m['host_binding_sha256']:
        raise ValueError('Portable host binding changed')
    patched=m.get('portable_verilator_patch')
    if not isinstance(patched,dict) or set(patched)!={'verilatedos_c.h','verilated_threads.cpp'}:
        raise ValueError('Missing portable Verilator adaptation identity')
    for name,want in patched.items():
        if sha(source/'verilator-portable'/name)!=want:raise ValueError('Portable Verilator adaptation changed: '+name)
    outputs=m.get('outputs')
    if not isinstance(outputs,dict) or set(outputs)!={'machine.mjs','machine.wasm'}:
        raise ValueError('Incomplete Wasm output inventory')
    for name,want in outputs.items():
        if sha(source/name)!=want:raise ValueError('Wasm output changed: '+name)
    return consumed

def bundle(args):
    if args.profile=='lemma-silicon-dev/0.15.0':return product_bundle(args)
    import silicon_guest
    if args.profile not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.14.0'):raise ValueError('The local browser bundle admits canonical0.3 or multimodal0.14')
    from silicon_guest_bundle import read_json
    source=args.wasm_build.resolve();m=read_json(source/'build.json')
    if m.get('status')!='BUILT' or m.get('profile')!=args.profile:raise ValueError('Missing compatible Wasm build')
    input_bundle=getattr(args,'wasm_input_bundle',None)
    consumed=validate_wasm_inputs(source,m,input_bundle)
    workbook=getattr(args,'workbook','ordinary')
    if workbook not in ('ordinary','parameterized') or (workbook=='parameterized' and args.profile!='lemma-silicon-dev/0.14.0'):raise ValueError('Parameterized browser workbook requires exact0.14')
    roles={w:('parameterized-'+w if workbook=='parameterized' else w) for w in ('notebook','initializer')}
    guest_archive=getattr(args,'guest_bundle',None)
    if guest_archive is None:
        prepared={w:silicon_guest.prepared(role,args.profile) for w,role in roles.items()}
    else:
        import silicon_guest_bundle
        prepared={w:silicon_guest_bundle.prepared(guest_archive,'rtl',role,args.profile)
                  for w,role in roles.items()}
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    def artifact(item,name):
        path=Path(item['path'])
        if sha(path)!=item['sha256']:raise ValueError('Guest artifact changed: '+str(path))
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        return {'path':name,'sha256':sha(dest)}
    result={'schema':'lemmasim-browser-bundle/1','profile':args.profile,'width':1650,'height':2200,
            'boot':'ELF-preload development boot','compiler':'native pinned Lean/LLVM helper; no browser compiler',
            'persistence':'OPFS SyncAccessHandle.flush; origin eviction and physical power loss unqualified',
            'session_control_contract':'lemma-browser-session-modes/2',
            'controller_image_contract':'lemma-controller-gray4-image/1',
            'wasm_build_sha256':sha(source/'build.json'),'wasm_project_root':str(ROOT),'workloads':{}}
    if args.profile=='lemma-silicon-dev/0.14.0':
        result.update(multimodal_contract='synthetic-aperture/1',checkpoint_contract='UNSUPPORTED: new acquisition and live-output state relation is not admitted')
    if guest_archive is not None:
        result['guest_archive']={'manifest_sha256':sha(guest_archive/'bundle.json'),
            'source_commit':prepared['notebook']['native_bundle']['source_commit'],
            'scope':'unchanged validated archived genuine guest on current source-bound RTL/Wasm; not fresh target compilation'}
    if input_bundle is not None:
        result['wasm_consumed_source_reuse']={'input_bundle_sha256':sha(Path(input_bundle)/'bundle.json'),
            'scope':('fresh host compilation of complete original RTL/runtime source versions; execution qualification separate'
                     if m.get('source_recompilation') else
                     'unchanged Wasm artifact with exact recorded consumed source versions; no current-machine compilation or execution qualification')}
        if guest_archive is not None:
            result['guest_archive']['scope']=('validated archived genuine guest on freshly host-compiled original RTL/runtime; not fresh target compilation'
                if m.get('source_recompilation') else
                'validated archived genuine guest on unchanged Wasm artifact; exact consumed source versions retained; not fresh target or machine compilation')
    result['wasm_project_inputs']={name:{'path':'wasm-sources/'+name,'sha256':item['sha256']}
                                 for name,item in consumed.items()}
    for name,item in consumed.items():
        destination=out/'wasm-sources'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(item['path'],destination)
        if sha(destination)!=item['sha256']:raise ValueError('Wasm consumed input changed while archiving: '+name)
    from silicon_guest_bundle import SOFTWARE_DEPLOYMENTS,COURSE_DEPLOYMENT,COURSE_AWAIT_DEPLOYMENT,PACKAGE_CLOSURE_DEPLOYMENT,READER_DEPLOYMENT,CHOOSER_READER_DEPLOYMENT
    deployment=prepared['notebook'].get('native_bundle',{}).get('software_deployment',{})
    if deployment.get('contract_version') in (COURSE_DEPLOYMENT,COURSE_AWAIT_DEPLOYMENT,PACKAGE_CLOSURE_DEPLOYMENT,READER_DEPLOYMENT,CHOOSER_READER_DEPLOYMENT):
        selected=deployment['contract_version']
        if deployment.get('configurations')!=SOFTWARE_DEPLOYMENTS[selected]:raise ValueError('Course bundle deployment differs')
        result['course_install_contract']='lemma-course-console-command/1'
    if args.profile=='lemma-silicon-dev/0.14.0':
        result['course_install_contract']='lemma-course-console-command/1'
        result['multimodal_workbook']=workbook
    result['rom']=artifact(prepared['notebook']['rom'],'boot.bin')
    for w,data in prepared.items():
        entry=data['workloads'][roles[w]]
        result['workloads'][w]={k:artifact(entry[k],w+'/'+k+('.elf' if k=='image' else '.bin')) for k in ('image','dtb','descriptor')}
        result['workloads'][w]['qualification']={k:artifact(entry[k],w+'/'+k+'.json')
            for k in ('build','provenance','audit','capacity') if k in entry}
    for name in ('machine.mjs','machine.wasm'):shutil.copyfile(source/name,out/name)
    for p in (ROOT/'sim/browser').glob('*'):
        if p.suffix in ('.js','.html','.css'):shutil.copyfile(p,out/p.name)
    result['files']={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n')
    notice='Local development bundle. Existing Lean/compiler/application sources have no selected project-wide redistribution license. Do not infer permission to redistribute from this local build.\nWasm host adapter: Apache-2.0 per source notices; no repository-wide relicensing.\nCVW pinned '+m['core_revision']+': Apache-2.0 WITH SHL-2.1 and preserved MIT notices.\nVerilator5.052: LGPL-3.0-only OR Artistic-2.0; generated model licensing follows its upstream terms. Emscripten6.0.9: MIT; generated runtime dependencies retain their upstream notices.\nSource/tool input closure is retained in wasm-build.json. Physical conformance UNVERIFIED.\n'
    if m.get('portable_compilation',{}).get('preset')=='simd-lto':
        notice+='This optional host compilation requires WebAssembly SIMD. The scalar build remains available. LLVM LTO/SIMD do not change RTL cycles, device scheduling or guest work.\n'
    (out/'DEPENDENCIES.txt').write_text(notice);shutil.copyfile(source/'build.json',out/'wasm-build.json')
    print(out/'index.html')

def build(args):
    command=[sys.executable,str(ROOT/'scripts/silicon_wasm.py'),'--output-dir',str(args.wasm_build),
             '--profile',args.profile,'--host-optimization',getattr(args,'host_optimization','scalar')]
    source_bundle=getattr(args,'wasm_source_bundle',None)
    if source_bundle is not None:command+=['--source-bundle',str(source_bundle)]
    subprocess.run(command,check=True)
    if source_bundle is not None:args.wasm_input_bundle=source_bundle
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
    if m.get('schema')=='lemmasim-browser-qemu-tci/1':
        import lemmasim_browser_tci
        return lemmasim_browser_tci.validated_bundle(directory)
    if m.get('schema')!='lemmasim-browser-bundle/1' or m.get('profile') not in ('lemma-silicon-dev/0.3.0','lemma-silicon-dev/0.14.0','lemma-silicon-dev/0.15.0') or (m.get('width'),m.get('height'))!=(1650,2200):
        raise ValueError('Unsupported browser machine bundle')
    if m.get('session_control_contract') not in (None, 'lemma-browser-session-modes/1', 'lemma-browser-session-modes/2'):
        raise ValueError('Unsupported browser control contract')
    if 'controller_image_contract' in m and m['controller_image_contract']!='lemma-controller-gray4-image/1':
        raise ValueError('Unsupported controller image export contract')
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
    product=m['profile']=='lemma-silicon-dev/0.15.0'
    if product:
        if m.get('product_boot_contract')!='lemma-browser-product-nv/1' or m.get('boot')!='immutable Lean ROM/NV' or set(m.get('workloads',{}))!={'notebook'}:raise ValueError('Unsupported Product15 boot contract')
        for kind,size in (('boot_medium',33558528),('user_seed',268435456)):
            item=m.get(kind)
            if kind=='user_seed' and item is None:continue
            if not isinstance(item,dict) or item.get('path') not in files or files[item['path']]!=item.get('sha256') or item.get('bytes')!=size or (directory/item['path']).stat().st_size!=size:raise ValueError('Unbound Product15 '+kind)
        item=m.get('product_prepared',{})
        if item.get('path') not in files or files[item['path']]!=item.get('sha256'):raise ValueError('Unbound Product15 component admission')
        admitted=read_json(directory/item['path'])
        if admitted.get('profile')!=m['profile'] or admitted.get('rom_sha256')!=files['boot.bin'] or admitted.get('digital_discovery',{}).get('descriptor_sha256')!=m['workloads']['notebook'].get('descriptor',{}).get('sha256'):raise ValueError('Product15 component identities differ')
    for workload in (('notebook',) if product else ('notebook','initializer')):
        entry=m.get('workloads',{}).get(workload,{})
        for kind in (('descriptor',) if product else ('image','dtb','descriptor')):
            item=entry.get(kind,{})
            if not isinstance(item,dict) or item.get('path') not in files or files[item['path']]!=item.get('sha256'):
                raise ValueError('Unbound browser guest '+workload+'/'+kind)
    course_contract=m.get('course_install_contract')
    if course_contract is not None:
        from silicon_guest_bundle import SOFTWARE_DEPLOYMENTS,COURSE_DEPLOYMENT,COURSE_AWAIT_DEPLOYMENT,PACKAGE_CLOSURE_DEPLOYMENT,READER_DEPLOYMENT,CHOOSER_READER_DEPLOYMENT
        if course_contract!='lemma-course-console-command/1' or 'course_transport.js' not in files:
            raise ValueError('Unsupported/incomplete browser course transport')
        configurations={}
        for workload in ('notebook','initializer'):
            item=m['workloads'][workload].get('qualification',{}).get('build',{})
            if item.get('path') not in files or files[item['path']]!=item.get('sha256'):
                raise ValueError('Unbound course installer deployment')
            configurations[workload]=read_json(directory/item['path']).get('configuration')
        admitted=[SOFTWARE_DEPLOYMENTS[name] for name in (COURSE_DEPLOYMENT,COURSE_AWAIT_DEPLOYMENT,PACKAGE_CLOSURE_DEPLOYMENT,READER_DEPLOYMENT,CHOOSER_READER_DEPLOYMENT)]
        if m['profile']=='lemma-silicon-dev/0.14.0':
            workbook=m.get('multimodal_workbook')
            if workbook not in ('ordinary','parameterized'):raise ValueError('Multimodal workbook identity missing')
            prefix='lemmasim-silicon-multimodal-'+('parameterized-' if workbook=='parameterized' else '')
            admitted=[{'notebook':prefix+'notebook','initializer':prefix+'initialize'}]
        if configurations not in admitted:
            raise ValueError('Browser course transport requires the complete exact guest deployment')
    if m.get('rom',{}).get('path')!='boot.bin' or m['rom'].get('sha256')!=files['boot.bin']:raise ValueError('Unbound browser boot artifact')
    wasm=directory/'wasm-build.json'
    if wasm.is_symlink() or not wasm.is_file() or sha(wasm)!=m.get('wasm_build_sha256'):raise ValueError('Unbound Wasm build manifest')
    build=read_json(wasm)
    if build.get('status')!='BUILT' or build.get('profile')!=m['profile']:raise ValueError('Incompatible Wasm build')
    for name in ('machine.mjs','machine.wasm'):
        if build.get('outputs',{}).get(name)!=files[name]:raise ValueError('Unbound Wasm output '+name)
    consumed=m.get('wasm_project_inputs')
    if consumed is not None:
        if not isinstance(consumed,dict) or not consumed:raise ValueError('Missing archived Wasm source inventory')
        expected={}
        for key in ('portable_inputs','binding_generator_inputs','host_toolchain_inputs','host_runtime'):
            values=build.get(key)
            if not isinstance(values,dict) or not values:raise ValueError('Missing original Wasm source identity: '+key)
            expected.update(values)
        for key in ('build_driver','upstream_patch'):
            item=build.get(key,{})
            expected[item.get('path')]=item.get('sha256')
        # Absolute project paths in the original source manifest retain their
        # spelling. Match the archived relative path to its original digest;
        # external tool/store/dependency inputs remain pinned by that receipt.
        project_root=m.get('wasm_project_root')
        if not isinstance(project_root,str) or not Path(project_root).is_absolute() or '..' in Path(project_root).parts:
            raise ValueError('Invalid original Wasm project root')
        for key in ('sha256','configuration_includes','verilator_runtime_inputs'):
            values=build.get(key)
            if not isinstance(values,dict) or not values:raise ValueError('Missing original Wasm absolute input identity: '+key)
            for path,digest in values.items():
                try:relative=Path(path).relative_to(project_root).as_posix()
                except ValueError:continue
                expected[relative]=digest
        if product:
            header=(Path(build['host_include_dir'])/'lemma_silicon_binding.h').relative_to(project_root).as_posix()
            expected[header]=build['host_binding_sha256']
        if set(consumed)!=set(expected):raise ValueError('Incomplete archived Wasm consumed source closure')
        for name,digest in expected.items():
            item=consumed[name]
            if not isinstance(item,dict) or item!={'path':'wasm-sources/'+name,'sha256':digest} or files.get(item['path'])!=digest:
                raise ValueError('Unbound archived Wasm consumed source: '+str(name))
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


def product_bundle(args):
    """Package real Product15 ROM/NV creation; never preload target image state."""
    import lemmasim_auth
    from silicon_guest_bundle import read_json
    prepared_path=getattr(args,'product_prepared',None);boot_path=getattr(args,'boot_medium',None)
    if prepared_path is None or boot_path is None:raise ValueError('Product15 browser requires --product-prepared and explicit opaque --boot-medium')
    prepared_path=Path(prepared_path).resolve();admission,_,rom=lemmasim_auth.prepared(prepared_path)
    if admission['profile']!='lemma-silicon-dev/0.15.0':raise ValueError('Exact Product15 prepared components required')
    source=args.wasm_build.resolve();m=read_json(source/'build.json')
    if m.get('status')!='BUILT' or m.get('profile')!=admission['profile']:raise ValueError('Exact Product15 Wasm producer required')
    consumed=validate_wasm_inputs(source,m,getattr(args,'wasm_input_bundle',None),getattr(args,'wasm_source_archive',None))
    boot_path=Path(boot_path).resolve();user_path=getattr(args,'user_seed',None)
    if boot_path.stat().st_size!=33558528:raise ValueError('Exact bounded Product boot medium required')
    if user_path is not None:
        user_path=Path(user_path).resolve()
        if user_path.stat().st_size!=268435456:raise ValueError('Exact256MiB guest-produced user seed required')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    def artifact(path,name):
        path=Path(path);want=sha(path);target=out/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
        if sha(target)!=want:raise ValueError('Product browser input changed while copying: '+name)
        return {'path':name,'sha256':want}
    result={'schema':'lemmasim-browser-bundle/1','profile':admission['profile'],'width':1650,'height':2200,
      'boot':'immutable Lean ROM/NV','product_boot_contract':'lemma-browser-product-nv/1',
      'compiler':'native pinned Lean/LLVM helper; no browser compiler',
      'persistence':'separate OPFS boot/user SyncAccessHandles; flush primitives, origin eviction and physical power loss unqualified',
      'session_control_contract':'lemma-browser-session-modes/2','controller_image_contract':'lemma-controller-gray4-image/1',
      'multimodal_contract':'synthetic-aperture/1',
      'checkpoint_contract':'initial sealed synthetic case only; ordinary Product checkpoint import/private boot persistence not admitted',
      'wasm_build_sha256':sha(source/'build.json'),'wasm_project_root':str(ROOT),
      'rom':artifact(rom['binary'],'boot.bin'),
      'product_prepared':artifact(prepared_path/'prepared.json','product/prepared.json'),
      'boot_medium':{**artifact(boot_path,'product/boot.raw'),'bytes':33558528},
      'workloads':{'notebook':{'descriptor':artifact(prepared_path/'descriptor.bin','notebook/descriptor.bin')}},
      'initialization':'copy exact guest-produced user seed' if user_path else 'requires imported guest-produced user medium; fresh initializer not present',
      'authentication':admission['authentication'],'production_identity':'OPEN','anti_rollback':'OPEN',
      'qualification':'packaged actual ROM/NV machine; no image preload, notebook Ready or ordinary browser workflow inferred'}
    if user_path:result['user_seed']={**artifact(user_path,'product/user.raw'),'bytes':268435456}
    result['wasm_project_inputs']={name:{'path':'wasm-sources/'+name,'sha256':item['sha256']} for name,item in consumed.items()}
    for name,item in consumed.items():
        archived=artifact(item['path'],'wasm-sources/'+name)
        if archived['sha256']!=item['sha256']:raise ValueError('Changed original portable source')
    for name in ('machine.mjs','machine.wasm'):artifact(source/name,name)
    for path in (ROOT/'sim/browser').glob('*'):
        if path.suffix in ('.js','.html','.css'):artifact(path,path.name)
    result['files']={path.relative_to(out).as_posix():sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    (out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n');shutil.copyfile(source/'build.json',out/'wasm-build.json')
    (out/'DEPENDENCIES.txt').write_text('Local Product15 development bundle. Public development authentication key; production identity and anti-rollback OPEN. Existing project, CVW, IHP functional SRAM, Verilator and Emscripten rights/notices remain. Raw media are opaque supplied guest-produced seeds; no permission to redistribute private work or supplied source corpus is inferred.\n')
    validated_bundle(out);print(out/'index.html')
