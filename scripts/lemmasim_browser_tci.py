#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the actual functional QEMU/Wasm machine and audited Lean guests.

This is an explicit sibling of the RTL embodiment, not a processor timing
substitute. Admission validates retained production; it never creates execution
evidence. The loopback server rechecks immutable bytes on every request.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='lemmasim-browser-qemu-tci/1'
PROFILE='lemma-silicon-dev/0.14.0'
BACKEND='qemu-tci-wasm64/1'
MAX_FILES=2048
MAX_BYTES=128*1024*1024
RUNTIME_SCHEMA='lemma-tci-retained-runtime/1'
RUNTIME_SCHEMA_WITH_HELPERS='lemma-tci-retained-runtime/2'
HELPER_FILES={'patch_tci_helpers.py','typed_helpers.json','tci-typed-helpers.patch'}
HELPER_SOURCES={'include/tcg/helper-info.h','include/exec/helper-info.c.inc','tcg/tci.c','tcg/tci/tcg-target.c.inc','accel/tcg/tcg-runtime.h'}
RUNTIME_BUILD_SCHEMAS={'lemma-tci-wasm-build/1','lemma-tci-public-build/1'}
RUNTIME_OUTPUTS={'qemu-system-riscv64.js','qemu-system-riscv64.wasm'}
CONTROLLERS={'lemma_fast_block.c','lemma_model.c','lemma_model.h',
             'lemma_multimodal.c','lemma_multimodal.h','lemma_multimodal_qemu.inc.c',
             'lemma_qemu.c','lemma_silicon_fast.h','lemma_uart_ingress.h','lemma_uart_qemu.inc.c'}
UI_EXPORT='\n// Host execution observer uses the same UI transport.\nexport {worker,send};\n'
UI_FILES=('app.js','style.css','guest_records.js','course_transport.js','run_budget.js','school_transport.js')
BRIDGE_FILES=('worker.mjs','runtime_worker.mjs','control.mjs','opfs_backing.mjs','pcm_egress.mjs','uart_arrivals.mjs')
PACKAGING_INPUTS={'scripts/lemmasim_browser_tci.py','sim/browser/index.html'}|{'sim/browser/'+name for name in UI_FILES}|{'sim/browser/tci/'+name for name in BRIDGE_FILES}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>16*1024*1024:raise ValueError('Invalid bounded manifest')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate manifest member')
            result[key]=value
        return result
    def constant(value):raise ValueError('Nonfinite manifest value: '+value)
    result=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    if not isinstance(result,dict):raise ValueError('Manifest must be an object')
    return result

def inventory(directory,files,extras):
    directory=Path(directory).absolute()
    if directory.is_symlink() or not directory.is_dir() or any(p.is_symlink() for p in directory.parents):raise ValueError('Invalid immutable directory')
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES:raise ValueError('Invalid file count')
    total=0
    for name,digest in files.items():
        if not isinstance(name,str) or not name or Path(name).is_absolute() or any(p in ('','.','..') for p in name.split('/')) or '\\' in name:raise ValueError('Invalid inventory path')
        if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid file checksum')
        p=directory/name
        if not p.is_file() or any(v.is_symlink() for v in (p,*p.parents)):raise ValueError('Missing or symlinked artifact')
        total+=p.stat().st_size
        if total>MAX_BYTES:raise ValueError('Byte budget exceeded')
        if sha(p)!=digest:raise ValueError('Artifact changed: '+name)
    actual=set()
    for p in directory.rglob('*'):
        if p.is_symlink():raise ValueError('Symlinked archive member')
        if p.is_file():actual.add(p.relative_to(directory).as_posix())
        elif not p.is_dir():raise ValueError('Nonregular archive member')
    if actual!=set(files)|set(extras):raise ValueError('Unlisted or missing archive member')
    return files

def retained_runtime(directory):
    directory=Path(directory).absolute();m=read(directory/'runtime.json')
    if m.get('schema') not in (RUNTIME_SCHEMA,RUNTIME_SCHEMA_WITH_HELPERS) or m.get('abi')!='lemma-qemu-wasm-control/1':raise ValueError('Runtime requires maintained retained-build admission')
    if m['schema']==RUNTIME_SCHEMA and 'direct_helpers' in m:raise ValueError('Legacy runtime cannot declare a new helper route')
    files=inventory(directory,m.get('files'),{'runtime.json'})
    required=RUNTIME_OUTPUTS|{'original-build.json','source-inputs.json','COPYING.QEMU','lemma_browser_control.inc.c','dependencies.json','patch_wasm.py','build.py','shell.nix','package.json','res_query_unavailable.c'}|{'controller-source/'+name for name in CONTROLLERS}
    if m['schema']==RUNTIME_SCHEMA_WITH_HELPERS:required|=HELPER_FILES
    build=read(directory/'original-build.json')
    if build.get('production_mode') in ('incremental-controller-object-and-real-link/1','fresh-upstream-objects-and-real-link/1'):
        required.add('incremental_uart.py')
        if build.get('inputs',{}).get('tooling/lemmasim/tci/incremental_uart.py')!=files.get('incremental_uart.py'):raise ValueError('Unbound incremental controller producer')
    if build.get('production_mode')=='incremental-flow-objects-and-real-link/1':
        required|={'incremental_flow.py','patch_uart_flow.py','retained-closure.json','retained-closure-inputs.json',
                   'retained-closure-source/incremental_flow.py','retained-closure-source/build.py','retained-closure-source/shell.nix',
                   'flow-source/chardev/char-fe.c','flow-source/hw/char/serial.c'}
        if build.get('inputs',{}).get('tooling/lemmasim/tci/incremental_flow.py')!=files.get('incremental_flow.py'):raise ValueError('Unbound incremental flow producer')
        observed=read(directory/'retained-closure.json')
        if observed.get('status')!='PASS_NEWLY_OBSERVED_RETAINED_CLOSURE_AND_BYTE_IDENTICAL_LINK' or observed.get('observed_object_count')!=1047 or build.get('fresh_object_count')!=3 or build.get('reused_object_count')!=1044:raise ValueError('Incomplete independently observed flow object closure')
        if sha(directory/'retained-closure.json')!=build.get('retained_closure_observation',{}).get('sha256') or sha(directory/'retained-closure-inputs.json')!=observed.get('observed_inputs_sha256') or read(directory/'retained-closure-inputs.json')!=observed.get('observed_inputs') or observed.get('observed_inputs')!=build.get('retained_inputs'):raise ValueError('Changed retained closure observation')
        if observed.get('predecessor',{}).get('sha256')!=build.get('predecessor',{}).get('sha256') or observed.get('outputs')!=build.get('predecessor',{}).get('outputs') or observed.get('original_source_closure_sha256')!=build.get('predecessor',{}).get('source_closure_sha256'):raise ValueError('Retained baseline production differs')
        for name in ('incremental_flow.py','build.py','shell.nix'):
            expected=[v['sha256'] for k,v in observed.get('inputs',{}).items() if Path(k).name==name]
            if len(expected)!=1 or expected[0]!=files.get('retained-closure-source/'+name):raise ValueError('Unbound retained observer source')
        patch=[v['sha256'] for k,v in build.get('overlay_inputs',{}).items() if k.endswith('/tooling/lemmasim/patch_uart_flow.py')]
        if patch!=[files.get('patch_uart_flow.py')]:raise ValueError('Unbound frozen UART flow overlay')
    if set(files)!=required:raise ValueError('Unknown or incomplete admitted runtime closure')
    source=read(directory/'source-inputs.json')
    if build.get('production_mode')=='incremental-flow-objects-and-real-link/1':
        for name in ('chardev/char-fe.c','hw/char/serial.c'):
            if source.get(name)!=files.get('flow-source/'+name):raise ValueError('Unbound changed UART source')
    if type(build.get('exit_code')) is not int or type(build.get('source_file_count')) is not int:raise ValueError('Runtime production counters must be exact integers')
    if build.get('schema')=='lemma-tci-public-build/1':
        origin=build.get('producer_input_root')
        if not isinstance(origin,str) or not Path(origin).is_absolute() or '..' in Path(origin).parts:raise ValueError('Fresh runtime requires its actual producer input root')
    if build.get('schema') not in RUNTIME_BUILD_SCHEMAS or build.get('result')!='BUILT_WASM64_QEMU_TCI' or build.get('exit_code')!=0 or sha(directory/'original-build.json')!=m.get('original_build',{}).get('sha256') or sha(directory/'source-inputs.json')!=build.get('source_closure_sha256') or not source or build.get('source_file_count')!=len(source):raise ValueError('Unbound actual runtime production')
    if not isinstance(build.get('outputs'),dict) or set(build['outputs'])!=RUNTIME_OUTPUTS:raise ValueError('Unknown runtime output inventory')
    if any(not isinstance(name,str) or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest) for name,digest in source.items()):raise ValueError('Invalid runtime source closure')
    for name in RUNTIME_OUTPUTS:
        item=build.get('outputs',{}).get(name,{})
        if item.get('sha256')!=files[name] or item.get('bytes')!=(directory/name).stat().st_size:raise ValueError('Unbound runtime output')
    if source.get('hw/riscv/lemma_browser_control.inc.c')!=files['lemma_browser_control.inc.c']:raise ValueError('Unbound control implementation')
    if source.get('COPYING')!=files['COPYING.QEMU']:raise ValueError('Changed original QEMU license')
    for name,digest in files.items():
        if name.startswith('controller-source/') and source.get('hw/riscv/'+name.split('/',1)[1])!=digest:raise ValueError('Unbound retained controller')
    if m['schema']==RUNTIME_SCHEMA_WITH_HELPERS:
        selected=m.get('direct_helpers')
        if type(selected) is not bool or type(build.get('direct_helpers',False)) is not bool or build.get('direct_helpers',False)!=selected:raise ValueError('Undeclared typed-helper route')
        helper=read(directory/'typed_helpers.json')
        if helper.get('schema')!='lemma-qemu-tci-typed-helper-patch/1' or helper.get('upstream_version')!='11.1.1' or helper.get('patch_sha256')!=files['tci-typed-helpers.patch'] or set(helper.get('sources',{}))!=HELPER_SOURCES:raise ValueError('Unknown typed-helper patch')
        for name in HELPER_FILES:
            if m.get('admission_inputs',{}).get('tooling/lemmasim/tci/'+name)!=files[name]:raise ValueError('Unbound typed-helper producer source')
        for name,item in helper['sources'].items():
            if not isinstance(item,dict) or set(item)!={'before','after'} or any(not isinstance(v,str) or not re.fullmatch('[a-f0-9]{64}',v) for v in item.values()) or source.get(name)!=item['after' if selected else 'before']:raise ValueError('Typed-helper route differs from compiled sources')
    return directory,m

def bundle(args):
    import silicon_guest_bundle
    from multimodal_native_bundle import SCHEMA as NATIVE_SCHEMA
    if args.profile!=PROFILE or args.workbook not in ('ordinary','parameterized','school'):raise ValueError('TCI requires exact multimodal profile/workbook')
    packaging_inputs={name:sha(ROOT/name) for name in sorted(PACKAGING_INPUTS)}
    runtime,admission=retained_runtime(args.wasm_build)
    archive=Path(args.guest_bundle).absolute();native=read(archive/'bundle.json')
    if native.get('schema')!=NATIVE_SCHEMA:raise ValueError('TCI requires the complete audited multimodal guest archive')
    roles={w:('parameterized-'+w if args.workbook=='parameterized' else w) for w in ('notebook','initializer')}
    if args.workbook=='school':
        from multimodal_native_bundle import SCHOOL
        if native.get('configurations')!=SCHOOL:raise ValueError('School browser requires the exact School22 native pair')
    elif native.get('configurations')==__import__('multimodal_native_bundle').SCHOOL:raise ValueError('School roots require explicit school workbook identity')
    prepared={w:silicon_guest_bundle.prepared(archive,'qemu',role,PROFILE) for w,role in roles.items()}
    out=Path(args.output_dir).absolute();out.mkdir(parents=True,exist_ok=False)
    def add(path,name,expected=None):
        path=Path(path);digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('Changed consumed artifact')
        dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        if sha(dest)!=digest:raise ValueError('Artifact changed during copy')
        return {'path':name,'sha256':digest}
    m={'schema':SCHEMA,'profile':PROFILE,'execution_backend':BACKEND,
       'session_control_contract':'lemma-browser-session-modes/2','width':1650,'height':2200,
       'multimodal_workbook':args.workbook,'course_install_contract':'lemma-course-console-command/1',
       'school_service_contract':'lemma-school-browser-service/1',
       'checkpoint_contract':'UNSUPPORTED: no exact TCI continuation relation is admitted',
       'timing_scope':'instruction/virtual-timer boundary; not RTL processor-cycle parity',
       'boot':'ELF-preload development boot; no production identity or physical entropy claim',
       'memory':{'guest_bytes':134217728,'host_wasm_heap_bytes':2147483648},
       'persistence':'Actual OPFS SyncAccessHandle flush; origin eviction and physical power-loss durability unqualified',
       'source_commit':native['source_commit'],'guest_archive_sha256':sha(archive/'bundle.json'),
       'runtime_admission_sha256':sha(runtime/'runtime.json'),'workloads':{},'runtime':{},
       'packaging_inputs':packaging_inputs}
    for name,digest in admission['files'].items():add(runtime/name,'runtime-source/'+name,digest)
    add(runtime/'runtime.json','runtime-source/runtime.json')
    for name in ('qemu-system-riscv64.js','qemu-system-riscv64.wasm'):
        item=add(runtime/name,name,admission['files'][name]);m['runtime']['wasm' if name.endswith('.wasm') else 'factory']=item
    # Every required current contract remains in the actual consumed closure.
    for name,digest in native['sources'].items():add(archive/'source'/name,'guest-source/'+name,digest)
    m['guest_sources']=native['sources']
    for w,data in prepared.items():
        entry=data['workloads'][roles[w]];m['workloads'][w]={}
        for key in ('image','dtb','descriptor','build','provenance','audit'):
            if key not in entry:raise ValueError('Incomplete guest qualification')
            item=entry[key];m['workloads'][w][key]=add(item['path'],w+'/'+Path(item['path']).name,item['sha256'])
    if getattr(args,'sample_course',None):
        if not 128<=Path(args.sample_course).stat().st_size<=32768:raise ValueError('Sample package bound rejected')
        m['sample_course']=add(args.sample_course,'sample.lcp')
    for name in UI_FILES:add(ROOT/'sim/browser'/name,name,packaging_inputs['sim/browser/'+name])
    # Export existing UI transport for an external observer, retaining both exact
    # source and the declared suffix. This adds no ink, journal or checking path.
    original=add(ROOT/'sim/browser/app.js','ui-source/app.js',packaging_inputs['sim/browser/app.js'])
    (out/'app.js').write_text((out/'ui-source/app.js').read_text(encoding='utf-8')+UI_EXPORT,encoding='utf-8')
    m['ui_transport_adapter']={'contract':'lemma-ui-existing-transport-export/1','source':original}
    for name in BRIDGE_FILES:add(ROOT/'sim/browser/tci'/name,'worker.js' if name=='worker.mjs' else name,packaging_inputs['sim/browser/tci/'+name])
    for name,digest in packaging_inputs.items():add(ROOT/name,'packaging-source/'+name,digest)
    index=(out/'packaging-source/sim/browser/index.html').read_text(encoding='utf-8').replace('Local RTL machine · development preload','Functional QEMU TCI/Wasm · shared Lean RV64 guest')
    (out/'index.html').write_text(index,encoding='utf-8')
    (out/'DEPENDENCIES.txt').write_text('Local development bundle. QEMU11.1.1 GPL-2.0-or-later; public source URLs, patches, original actual production identities and controller source are retained in runtime-source/. Emscripten and other upstream dependencies retain their notices. Project-wide redistribution rights remain unresolved. Functional instruction execution is not RTL timing parity. Physical and educational qualification remain unverified.\n')
    m['files']={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'bundle.json').write_text(json.dumps(m,indent=2)+'\n')
    retained_runtime(runtime)
    if sha(archive/'bundle.json')!=m['guest_archive_sha256']:raise ValueError('Guest archive changed during packaging')
    if any(sha(ROOT/name)!=digest for name,digest in packaging_inputs.items()):raise ValueError('Packaging source changed during production')
    validated_bundle(out);print(out/'bundle.json');return out/'bundle.json'

def validated_bundle(directory):
    directory=Path(directory).absolute();m=read(directory/'bundle.json')
    if m.get('schema')!=SCHEMA or m.get('profile')!=PROFILE or m.get('execution_backend')!=BACKEND or m.get('session_control_contract')!='lemma-browser-session-modes/2' or (m.get('width'),m.get('height'))!=(1650,2200):raise ValueError('Unsupported TCI bundle')
    if m.get('multimodal_workbook') not in ('ordinary','parameterized','school') or m.get('course_install_contract')!='lemma-course-console-command/1':raise ValueError('Unsupported workbook')
    if m.get('memory')!={'guest_bytes':134217728,'host_wasm_heap_bytes':2147483648} or set(m.get('workloads',{}))!={'notebook','initializer'} or set(m.get('runtime',{}))!={'factory','wasm'}:raise ValueError('Unsupported TCI machine resources')
    files=inventory(directory,m.get('files'),{'bundle.json'})
    required={'index.html','worker.js','runtime_worker.mjs','control.mjs','opfs_backing.mjs','pcm_egress.mjs','app.js','style.css','guest_records.js','course_transport.js','run_budget.js','qemu-system-riscv64.js','qemu-system-riscv64.wasm','runtime-source/runtime.json'}
    if m.get('school_service_contract') is not None and (m['school_service_contract']!='lemma-school-browser-service/1' or 'school_transport.js' not in files):raise ValueError('Unsupported school service closure')
    if m.get('sample_course') is not None and (m['sample_course']!={'path':'sample.lcp','sha256':files.get('sample.lcp')} or not 128<=(directory/'sample.lcp').stat().st_size<=32768):raise ValueError('Unbound sample package')
    if not required<=files.keys():raise ValueError('Incomplete TCI launch bundle')
    if 'packaging_inputs' not in m:raise ValueError('Missing packaging source closure')
    if 'packaging_inputs' in m:
        inputs=m['packaging_inputs']
        if not isinstance(inputs,dict) or set(inputs)!=(PACKAGING_INPUTS if m.get('school_service_contract') else PACKAGING_INPUTS-{'sim/browser/school_transport.js'}) or any(files.get('packaging-source/'+name)!=digest for name,digest in inputs.items()):raise ValueError('Incomplete packaging source closure')
        for name in UI_FILES:
            if name=='school_transport.js' and not m.get('school_service_contract'):continue
            target='ui-source/app.js' if name=='app.js' else name
            if files.get(target)!=inputs['sim/browser/'+name]:raise ValueError('Changed packaged UI input')
        for name in BRIDGE_FILES:
            target='worker.js' if name=='worker.mjs' else name
            if files.get(target)!=inputs['sim/browser/tci/'+name]:raise ValueError('Changed packaged bridge input')
        index=(directory/'packaging-source/sim/browser/index.html').read_text(encoding='utf-8').replace('Local RTL machine · development preload','Functional QEMU TCI/Wasm · shared Lean RV64 guest')
        if (directory/'index.html').read_text(encoding='utf-8')!=index:raise ValueError('Changed derived launch page')
    if 'ui_transport_adapter' not in m:raise ValueError('Missing UI source closure')
    if 'ui_transport_adapter' in m:
        adapter=m['ui_transport_adapter']
        if adapter!={'contract':'lemma-ui-existing-transport-export/1','source':{'path':'ui-source/app.js','sha256':files.get('ui-source/app.js')}} or 'ui-source/app.js' not in files:raise ValueError('Unbound UI transport adapter')
        if (directory/'app.js').read_text(encoding='utf-8')!=(directory/'ui-source/app.js').read_text(encoding='utf-8')+UI_EXPORT:raise ValueError('Changed UI transport adapter')
    _,admission=retained_runtime(directory/'runtime-source')
    if sha(directory/'runtime-source/runtime.json')!=m.get('runtime_admission_sha256'):raise ValueError('Unbound retained runtime admission')
    # The entire admitted runtime closure is preserved, not only its executable.
    runtime_files=admission.get('files')
    if not isinstance(runtime_files,dict) or not runtime_files:raise ValueError('Missing admitted runtime closure')
    for name,digest in runtime_files.items():
        if files.get('runtime-source/'+name)!=digest:raise ValueError('Missing original runtime source')
    for key,name in [('factory','qemu-system-riscv64.js'),('wasm','qemu-system-riscv64.wasm')]:
        if m.get('runtime',{}).get(key)!={'path':name,'sha256':files[name]} or runtime_files.get(name)!=files[name]:raise ValueError('Unbound runtime executable')
    sources=m.get('guest_sources')
    if not isinstance(sources,dict) or not sources:raise ValueError('Missing guest source closure')
    for name,digest in sources.items():
        if files.get('guest-source/'+name)!=digest:raise ValueError('Missing consumed guest source')
    profile_source='sim/profiles/lemma-silicon-dev-0.14.0.json'
    if admission.get('admission_inputs',{}).get(profile_source)!=sources.get(profile_source) or profile_source not in sources:raise ValueError('Runtime and guest board bindings differ')
    from build_kernel import source_inputs
    if source_inputs(directory/'guest-source')!=sources:raise ValueError('Incomplete consumed guest source closure')
    for w in ('notebook','initializer'):
        entry=m.get('workloads',{}).get(w,{})
        names={'image':'image.elf','dtb':'platform.dtb','descriptor':'descriptor.bin','build':'build.json','provenance':'provenance.json','audit':'audit.json'}
        for key,name in names.items():
            item=entry.get(key,{})
            if not isinstance(item,dict) or item.get('path')!=w+'/'+name or item['path'] not in files or files[item['path']]!=item.get('sha256'):raise ValueError('Unbound guest '+w+'/'+key)
        build=read(directory/entry['build']['path']);audit=read(directory/entry['audit']['path']);provenance=read(directory/entry['provenance']['path'])
        prefix='lemmasim-silicon-multimodal-'+('parameterized-' if m['multimodal_workbook']=='parameterized' else '')
        configuration=prefix+('initialize' if w=='initializer' else 'notebook')
        if m['multimodal_workbook']=='school':
            from school_deployment import FAST,INITIALIZE
            configuration=INITIALIZE if w=='initializer' else FAST
        for report in (build,audit,provenance):
            if report.get('schema_version')!=2 or report.get('artifact_category')!='development-kernel-boot-package' or report.get('configuration')!=configuration or report.get('stage')!='supervisor' or report.get('optimization') not in ('O0','O2'):raise ValueError('Incompatible actual guest qualification')
        if len({report['optimization'] for report in (build,audit,provenance)})!=1:raise ValueError('Inconsistent guest optimization')
        if build.get('status')!='BUILT' or audit.get('status')!='PASS' or audit.get('image_sha256')!=entry['image']['sha256'] or provenance.get('source_inputs')!=sources:raise ValueError('Incompatible actual guest qualification')
        if build.get('provenance_sha256')!=entry['provenance']['sha256'] or audit.get('source_commit')!=m.get('source_commit') or provenance.get('source_commit')!=m.get('source_commit') or not re.fullmatch('[a-f0-9]{40}',str(m.get('source_commit'))):raise ValueError('Unbound guest production provenance')
        for report in (build,provenance):
            for key in ('image','dtb','descriptor'):
                if report.get('artifacts',{}).get(names[key])!=entry[key]['sha256']:raise ValueError('Unbound guest production artifact')
        if not build.get('lean_source_realization') or any(report.get('lean_source_realization')!=build['lean_source_realization'] for report in (audit,provenance)):raise ValueError('Inconsistent Lean source realization')
    return directory,{**files,'bundle.json':sha(directory/'bundle.json')}
