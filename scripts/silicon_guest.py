#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LemmaSim RTL preparation/launch: byte transport and identity checks only."""
from __future__ import annotations
import fcntl, hashlib, json, os, shutil, signal, struct, subprocess, time
from pathlib import Path
from silicon_profile import PROFILE, profile

ROOT=Path(__file__).resolve().parents[1]
PREPARED=ROOT/'build/lemmasim/rtl-prepared.json'
CONFIGURATIONS={'service':'silicon-service-development', 'notebook':'lemmasim-silicon-notebook',
                'initializer':'lemmasim-silicon-initialize','devices':'lemmasim-silicon-devices'}

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()
def identified(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def run_command(argv, *, timeout, log=None):
    output=log.open('w') if log else None
    proc=subprocess.Popen([str(a) for a in argv],cwd=ROOT,start_new_session=True,stdout=output,stderr=subprocess.STDOUT if output else None)
    try:
        rc=proc.wait(timeout=timeout)
        if rc:raise RuntimeError(f'RTL command failed ({rc}); '+(str(log) if log else str(argv[0])))
    finally:
        if proc.poll() is None:os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=5)
        if output:output.close()

def validate(item):
    if not isinstance(item,dict) or set(item)!={'path','sha256'}:raise ValueError('malformed RTL artifact identity')
    p=Path(item['path'])
    if not p.is_file() or sha(p)!=item['sha256']:raise ValueError('RTL artifact changed or missing: '+str(p))
    return p

def prepared(workload):
    data=json.loads(PREPARED.read_text())
    if data.get('schema_version')!=1 or data.get('profile')!=profile()['profile'] or data.get('profile_sha256')!=sha(PROFILE):
        raise ValueError('RTL prepared binding changed; run lemmasim build --backend rtl')
    validate(data['binary']);validate(data['rom']);validate(data['rom_audit']);validate(data['rtl_build'])
    for path,digest in data['rtl_sources'].items():
        if not Path(path).is_file() or sha(path)!=digest:raise ValueError('RTL source/dependency changed: '+path)
    if workload not in data['workloads']:
        raise ValueError('RTL workload is not prepared; run lemmasim build --backend rtl --workload '+workload)
    for key in ('image','build','provenance','audit','dtb','descriptor'):
        validate(data['workloads'][workload][key])
    guest=validate(data['workloads'][workload]['build']).parent
    verify_guest_build(guest,CONFIGURATIONS[workload],json.loads((guest/'build.json').read_text())['optimization'])
    if workload=='notebook':
        capacity=json.loads(validate(data['workloads'][workload]['capacity']).read_text())
        if capacity.get('status')!='PASS' or capacity.get('configuration')!=CONFIGURATIONS[workload]:
            raise ValueError('RTL notebook selected capacity evidence differs')
        for name,digest in capacity['artifacts'].items():
            if sha(guest/name)!=digest:raise ValueError('RTL notebook capacity artifact changed: '+name)
    return data

def reset_rom_audit(data):
    audit=json.loads(validate(data['rom_audit']).read_text())
    words=[0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067]
    if audit.get('status')!='PASS' or audit.get('instruction_words')!=words:
        raise ValueError('Reset ROM audit inventory differs')
    for key in ('source','assembly','object','elf','binary'):validate(audit[key])
    if audit['source']['path']!=str((ROOT/'Lemma/Platform/Silicon/BootROM.lean').resolve()) or audit['binary']!=data['rom']:
        raise ValueError('Reset ROM audited source/binary differs')
    if validate(data['rom']).read_bytes()!=struct.pack('<6I',*words):
        raise ValueError('Reset ROM actual instruction words differ')
    return audit

def reusable_reset_rom(previous,data,guest):
    if previous is None:return None
    for key in ('schema_version','profile','profile_sha256','binary','rtl_build','rtl_sources','memory','physical_conformance'):
        if previous.get(key)!=data.get(key):return None
    current_provenance=json.loads((guest/'provenance.json').read_text())
    matching_provenance=None
    for workload,entry in previous['workloads'].items():
        if workload not in CONFIGURATIONS:continue
        try:
            old_guest=validate(entry['build']).parent
            old_build=json.loads((old_guest/'build.json').read_text())
            verify_guest_build(old_guest,CONFIGURATIONS[workload],old_build['optimization'])
            candidate=json.loads(validate(entry['provenance']).read_text())
        except (OSError,ValueError,KeyError):continue
        if all(candidate[key]==current_provenance[key] for key in ('tools','lean_source_realization','source_inputs')):
            matching_provenance=candidate;break
    if matching_provenance is None:return None
    for path,digest in previous['rtl_sources'].items():
        if not Path(path).is_file() or sha(path)!=digest:raise ValueError('Reset ROM RTL/tool source changed: '+path)
    for key in ('binary','rtl_build'):validate(previous[key])
    old_audit=reset_rom_audit(previous);new_audit=reset_rom_audit(data)
    if old_audit['scope']!=new_audit['scope'] or any(old_audit[key]['sha256']!=new_audit[key]['sha256'] for key in ('source','assembly','object','elf','binary')):
        raise ValueError('Unchanged reset ROM generated artifacts differ')
    return {'rom':previous['rom'],'rom_audit':previous['rom_audit']}

def publish_prepared(data):
    PREPARED.parent.mkdir(parents=True,exist_ok=True)
    temporary=PREPARED.with_name(PREPARED.name+'.'+str(time.time_ns()))
    try:
        with temporary.open('xb') as stream:
            stream.write((json.dumps(data,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,PREPARED)
    finally:
        if temporary.exists():temporary.unlink()

def build(args):
    from silicon_compute import source_manifest, prepare
    out=(getattr(args,'rtl_build',None) or ROOT/'build/silicon/compute').resolve();dep=ROOT/'build/silicon/deps/cvw'
    prepare(dep);current=source_manifest(dep)
    cached=None
    try:cached=json.loads((out/'build.json').read_text())
    except (OSError,ValueError):pass
    if cached is None or cached.get('configuration')!='external-ram-128MiB' or any(cached.get(k)!=v for k,v in current.items()) or not (out/'obj/lemma-rtl').is_file() or cached.get('binary_sha256')!=sha(out/'obj/lemma-rtl'):
        if getattr(args,'rtl_build',None):raise ValueError('Supplied RTL build differs from current exact source closure')
        run_command(['python3','scripts/silicon_compute.py','build','--output-dir',out],timeout=1200)
        cached=json.loads((out/'build.json').read_text())
    stamp=str(time.time_ns());directory=ROOT/f'build/silicon/prepared-{stamp}'
    directory.mkdir(parents=True)
    rom=directory/'rom';rom.mkdir()
    run_command(['nix','develop','--no-write-lock-file','--command','lake','build','Lemma.Platform.Silicon.Binding'],timeout=300,log=directory/'rom-elaboration.log')
    run_command(['nix','develop','--no-write-lock-file','--command','lake','env','lean','--run',
                 'Lemma/Platform/Silicon/BootROM.lean',rom/'boot.S'],timeout=300,log=directory/'rom-export.log')
    # One immutable Lean/LLVM closure; no maintained assembly source.
    for argv in ([ 'clang','--target=riscv64-unknown-elf','-march=rv64im_zicsr_zifencei','-mabi=lp64','-mcmodel=medany','-mno-relax','-c',rom/'boot.S','-o',rom/'boot.o'],
                 ['ld.lld','-m','elf64lriscv','--no-relax','-Ttext=0x1000','-e','_reset',rom/'boot.o','-o',rom/'boot.elf'],
                 ['llvm-objcopy','-O','binary','--only-section=.text',rom/'boot.elf',rom/'boot.bin']):
        run_command(['nix','develop','--no-write-lock-file','--command',*argv],timeout=300)
    # Independent instruction-word inventory for this fixed versioned binding:
    # a0=0; a1=0x43f<<21; t0=1<<31; jalr x0,t0,0. Unknown words fail closed.
    if (profile()['dtb_base'],profile()['entry'])!=(0x87e00000,0x80000000):raise ValueError('Reset handoff audit requires a new binding inventory')
    words=(0x00000513,0x43f00593,0x01559593,0x00100293,0x01f29293,0x00028067)
    if (rom/'boot.bin').read_bytes()!=struct.pack('<6I',*words):raise ValueError('Reset handoff instruction inventory differs')
    (rom/'audit.json').write_text(json.dumps({'status':'PASS','scope':'exact structured reset handoff words; no guest privilege initialization',
        'source':identified(ROOT/'Lemma/Platform/Silicon/BootROM.lean'),
        'assembly':identified(rom/'boot.S'),'object':identified(rom/'boot.o'),'elf':identified(rom/'boot.elf'),
        'binary':identified(rom/'boot.bin'),'instruction_words':words},indent=2)+'\n')
    data={'schema_version':1,'profile':profile()['profile'],'profile_sha256':sha(PROFILE),
          'binary':identified(out/'obj/lemma-rtl'),'rom':identified(rom/'boot.bin'),'rom_audit':identified(rom/'audit.json'),
          'rtl_build':identified(out/'build.json'),'rtl_sources':{**cached['sha256'],**cached['configuration_includes'],
              str(ROOT/cached['host_adapter']['path']):cached['host_adapter']['sha256'],
              str(Path(cached['host_include_dir'])/'lemma_silicon_binding.h'):cached['host_binding_sha256'],
              **{str(ROOT/name):sha(ROOT/name) for name in ('scripts/silicon_compute.py','scripts/silicon_profile.py',
                 'tooling/silicon/apply_cvw.py','tooling/silicon/dependencies.json','tooling/silicon/sim.nix')}},'workloads':{},
          'memory':'128 MiB external simulation bytes, not synthesized SRAM','physical_conformance':'UNVERIFIED'}
    workload=getattr(args,'workload',None) or 'service'
    guest=getattr(args,'guest_build',None)
    if guest is None:
        guest=ROOT/f'build/kernel/silicon-{workload}-{stamp}-{args.opt_level}'
        run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/build_kernel.py',
            '--configuration',CONFIGURATIONS[workload],'--stage','supervisor','--opt-level',args.opt_level,
            '--output-dir',guest,'--timeout','300'],timeout=1500,log=directory/'guest-build.log')
        run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/audit_kernel.py',guest],timeout=600,log=directory/'guest-audit.log')
    guest=Path(guest).resolve()
    verify_guest_build(guest,CONFIGURATIONS[workload],args.opt_level)
    if workload=='notebook':
        run_command(['nix','develop','--no-write-lock-file','--command','python3','scripts/audit_lemmasim_capacity.py',
                     '--build',guest,'--output',guest/'capacity.json'],timeout=120,log=directory/'guest-capacity.log')
        capacity=json.loads((guest/'capacity.json').read_text())
        if capacity.get('status')!='PASS':raise ValueError('RTL notebook selected capacity audit did not pass')
    entry={key:identified(guest/name) for key,name in [('image','image.elf'),('build','build.json'),('provenance','provenance.json'),('audit','audit.json'),('dtb','platform.dtb'),('descriptor','descriptor.bin')]}
    if workload=='notebook':entry['capacity']=identified(guest/'capacity.json')
    previous=None
    try:
        previous=json.loads(PREPARED.read_text())
        if previous.get('profile_sha256')==data['profile_sha256']:
            for key,old_entry in previous['workloads'].items():
                if key in CONFIGURATIONS:
                    try:
                        for item in old_entry.values():validate(item)
                        old_build=json.loads(validate(old_entry['build']).read_text())
                        verify_guest_build(validate(old_entry['build']).parent,CONFIGURATIONS[key],old_build['optimization'])
                        if key=='notebook':validate(old_entry['capacity'])
                    except (OSError,ValueError,KeyError):
                        continue
                    data['workloads'][key]=old_entry
    except FileNotFoundError:pass
    data['workloads'][workload]=entry
    reused=reusable_reset_rom(previous,data,guest)
    if reused:
        write={'status':'PASS','scope':'Verified immutable reset-ROM reuse; not functional acceptance',
               'generated_rom':data['rom'],'generated_rom_audit':data['rom_audit'],'reused':reused}
        (directory/'rom-reuse.json').write_text(json.dumps(write,indent=2)+'\n')
        data.update(reused)
    publish_prepared(data)
    print(f'Prepared RTL {workload}; {PREPARED}. Ordinary launch validates identities without rebuilding.')

def verify_guest_build(guest,configuration,optimization):
    from build_kernel import source_inputs
    build=json.loads((guest/'build.json').read_text());provenance=json.loads((guest/'provenance.json').read_text())
    audit=json.loads((guest/'audit.json').read_text())
    if (build.get('status'),audit.get('status'))!=('BUILT','PASS'):
        raise ValueError('RTL guest needs a successful real build and strict audit')
    for report in (build,provenance,audit):
        if (report.get('configuration'),report.get('stage'),report.get('optimization'))!=(configuration,'supervisor',optimization):
            raise ValueError('RTL guest build/audit configuration differs')
    if provenance.get('source_inputs')!=source_inputs(ROOT):raise ValueError('RTL guest source snapshot differs from current exact inputs')
    if build.get('provenance_sha256')!=sha(guest/'provenance.json') or audit.get('image_sha256')!=sha(guest/'image.elf'):
        raise ValueError('RTL guest build/audit identities differ')
    for name,digest in provenance['artifacts'].items():
        path=(guest/name).resolve()
        if not path.is_relative_to(guest) or not path.is_file() or sha(path)!=digest:raise ValueError('RTL guest artifact changed: '+name)

def bounded_options(args):
    options={key:getattr(args,key,None) for key in ('cycles','trace_limit','timeout','uart_stop','uart_stop_hex','stop_after_panel','fail_flush','observer_cycle','ram_dump','block_trace')}
    if type(options['cycles']) is not int or not 0<options['cycles']<=10000000000:raise ValueError('RTL cycles must be 1..10000000000')
    if type(options['trace_limit']) is not int or not 0<=options['trace_limit']<=1000000:raise ValueError('RTL trace limit must be 0..1000000')
    options['timeout']=options['timeout'] or 120
    if not 1<=options['timeout']<=3600:raise ValueError('RTL timeout must be 1..3600 seconds')
    for key in ('stop_after_panel','fail_flush','observer_cycle'):
        value=options[key]
        if value is not None and (type(value) is not int or not 1<=value<=(options['cycles'] if key=='observer_cycle' else 1000000)):raise ValueError('Invalid RTL '+key)
    if options['uart_stop'] and options['uart_stop_hex']:raise ValueError('Use one RTL UART stop marker')
    if options['uart_stop_hex'] is not None:
        if not options['uart_stop_hex'] or len(options['uart_stop_hex'])%2:raise ValueError('RTL UART stop hex must contain whole bytes')
        try:bytes.fromhex(options['uart_stop_hex'])
        except ValueError:raise ValueError('RTL UART stop hex must contain hexadecimal bytes') from None
    if options['ram_dump'] is not None:ram_dump_range(options['ram_dump'])
    if options['block_trace'] is None:options['block_trace']=False
    if type(options['block_trace']) is not bool:raise ValueError('RTL block trace must be a boolean')
    return options

def ram_dump_range(specification):
    """A raw external-memory range; no guest data interpretation."""
    import re
    if not isinstance(specification,str) or not re.fullmatch(r'(?:0x[0-9a-fA-F]+|[0-9]+):(?:0x[0-9a-fA-F]+|[0-9]+)',specification):
        raise ValueError('RTL RAM dump requires address:bytes')
    address,size=(int(value,16 if value.startswith('0x') else 10) for value in specification.split(':'))
    p=profile()
    if not 1<=size<=1048576 or not p['ram_base']<=address<=p['ram_base']+p['ram_bytes']-size:
        raise ValueError('RTL RAM dump must be 1..1048576 bytes inside external RAM')
    return address,size

def execute(data,workload,directory,options,inputs,medium):
    from types import SimpleNamespace
    options=bounded_options(SimpleNamespace(**options))
    entry=data['workloads'][workload]
    argv=[data['binary']['path'],'--image',entry['image']['path'],'--rom',data['rom']['path'],
          '--load',f"0x{profile()['dtb_base']:x}:{entry['dtb']['path']}",'--uart-output',directory/'uart.bin',
          '--trace',directory/'trace.csv','--trace-limit',options['trace_limit'],'--cycles',options['cycles'],
          '--deadline',int(options['timeout']),'--panel-output',directory/'panel','--report',directory/'host-report.json','--quiet-uart']
    for key,flag in (('uart','--uart-input'),('events','--events')):
        if inputs.get(key):argv += [flag,validate(inputs[key])]
    if workload!='service':
        if medium is None:raise ValueError('RTL notebook/initializer requires --disk retained raw medium')
        argv+=['--descriptor',entry['descriptor']['path'],'--medium',medium]
    for key,flag in (('uart_stop','--uart-stop'),('uart_stop_hex','--uart-stop-hex'),('stop_after_panel','--stop-after-panel'),('fail_flush','--fail-flush'),('observer_cycle','--observer-cycle')):
        if options[key] is not None:argv += [flag,options[key]]
    if options['ram_dump']:
        address,size=ram_dump_range(options['ram_dump']);argv+=['--ram-dump',f'{address}:{size}:{directory/"ram.bin"}']
    if options['block_trace']:argv+=['--block-trace',directory/'block.csv']
    process=None;result={'schema_version':1,'scope':'raw RTL transport; functional acceptance is separate',
        'argv':list(map(str,argv)),'status':'NOT_RUN'}
    try:
        with (directory/'run.log').open('w') as log:
            process=subprocess.Popen(list(map(str,argv)),cwd=ROOT,start_new_session=True,stdout=log,stderr=subprocess.STDOUT)
            try:result['exit_code']=process.wait(timeout=options['timeout']+10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5);result['exit_code']=process.returncode
                result['status']='WALL_TIMEOUT';return result
        result['status']='STOPPED_BY_PROTOCOL' if result['exit_code']==0 else 'FAILED'
        if medium is not None:result['final_medium_sha256']=sha(medium)
        result['outputs']={str(p.relative_to(directory)):sha(p) for p in sorted(directory.rglob('*')) if p.is_file()
            and (p.name in ('uart.bin','trace.csv','host-report.json','ram.bin','block.csv') or p.name.startswith('panel'))}
        return result
    finally:
        if process is not None and process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        (directory/'output.json').write_text(json.dumps(result,indent=2)+'\n')

def run(args):
    workload=getattr(args,'workload',None) or 'service'
    if args.geometry and args.geometry!=f"{profile()['geometry'][0]}x{profile()['geometry'][1]}":raise ValueError('RTL geometry is fixed by lemma-silicon-dev/0.1.0')
    if args.mode!='developer':raise ValueError('lemma-silicon-dev/0.1.0 currently supports Developer mode only')
    if getattr(args,'raw_input',None) or getattr(args,'fault',None):
        raise ValueError('RTL uses --events and --fail-flush; QEMU raw-input/fault options are unsupported')
    options=bounded_options(args);data=prepared(workload)
    directory=(args.record or ROOT/f'build/silicon/run-{time.time_ns()}').resolve();directory.mkdir(parents=True,exist_ok=False)
    inputs={}
    for key,path in [('uart',args.uart_input),('events',args.events)]:
        if path:
            destination=directory/('input.'+key);shutil.copyfile(path,destination);inputs[key]=identified(destination)
    disk=args.disk.resolve() if args.disk else None
    if workload=='service' and disk is not None:raise ValueError('RTL service workload has no block medium; omit --disk')
    if workload!='service' and disk is None:raise ValueError('RTL notebook/initializer requires --disk retained raw medium')
    lock=disk.open('r+b') if disk is not None else None
    try:
        if lock is not None:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        initial=None
        if disk is not None:
            initial_path=directory/'initial-medium.raw';shutil.copyfile(disk,initial_path);initial=identified(initial_path)
        identity={'schema_version':1,'transport':'lemma-silicon-events/1','profile':data['profile'],'prepared':data,
            'workload':workload,'options':options,'reset_cycles':8,'clock_hz':profile()['clock_hz'],'ram_initialization':'zero external RAM plus exact ELF and DTB loads',
            'inputs':inputs,'initial_medium':initial,'medium_path':str(disk) if disk else None}
        (directory/'input.json').write_text(json.dumps(identity,indent=2)+'\n')
        result=execute(data,workload,directory,options,inputs,disk)
    finally:
        if lock is not None:lock.close()
        print(f'RTL run artifacts: {directory}')
    if result['exit_code']!=0:raise RuntimeError(f"RTL run {result['status']} ({result['exit_code']}); {directory/'run.log'}")

def replay(args):
    session=args.session.resolve();identity=json.loads((session/'input.json').read_text());original=json.loads((session/'output.json').read_text())
    if identity.get('schema_version')!=1 or identity.get('transport')!='lemma-silicon-events/1':raise ValueError('Unsupported RTL capture identity')
    if not isinstance(original.get('outputs'),dict) or not original['outputs']:
        raise ValueError('RTL capture contains no completed output inventory')
    for name,digest in original['outputs'].items():
        output=session/name
        if output.resolve().parent!=session or not output.is_file() or sha(output)!=digest:
            raise ValueError('RTL capture output changed or missing: '+name)
    data=identity['prepared'];workload=identity['workload']
    # Validate the captured immutable executable and guest, independently of a
    # newly selected default. No captured result substitutes for execution.
    for key in ('binary','rom','rom_audit','rtl_build'):validate(data[key])
    for item in data['workloads'][workload].values():validate(item)
    for path,digest in data['rtl_sources'].items():
        if not Path(path).is_file() or sha(path)!=digest:raise ValueError('Captured RTL source/dependency changed: '+path)
    if data['profile_sha256']!=sha(PROFILE):raise ValueError('Captured RTL binding is no longer supported by this generator')
    inputs=identity['inputs']
    for item in inputs.values():validate(item)
    directory=ROOT/f'build/silicon/replay-{time.time_ns()}';directory.mkdir(parents=True)
    disk=None
    if identity['initial_medium'] is not None:
        initial=validate(identity['initial_medium']);disk=args.disk_copy.resolve()
        if disk.exists():raise ValueError('RTL replay --disk-copy must be new')
        disk.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(initial,disk)
    options=dict(identity['options']);options['timeout']=args.timeout
    result=execute(data,workload,directory,options,inputs,disk)
    compared={key:result.get(key)==original.get(key) for key in ('exit_code','outputs','final_medium_sha256')}
    (directory/'comparison.json').write_text(json.dumps({'status':'MATCH' if all(compared.values()) else 'MISMATCH',
        'compared':compared,'scope':'same RTL backend replay only; no instruction-schedule equivalence with QEMU'},indent=2)+'\n')
    if not all(compared.values()):raise RuntimeError('RTL replay outputs differ: '+str(directory))
    if result['exit_code']!=0:raise RuntimeError('RTL replay regenerated the original failure: '+str(directory))
    print('RTL external-input replay matched actual UART/panel/medium outputs: '+str(directory))
