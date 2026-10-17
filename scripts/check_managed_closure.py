#!/usr/bin/env python3
"""Host-only bounded qualification of genuinely compiled isolated RV64 closures.
The host observes outputs/resource failure; it never applies a guest closure.
"""
import argparse, hashlib, json, os, re, selectors, shutil, signal, subprocess, sys, time
from pathlib import Path
from core0_common import Core0Error, require_tools, run_bounded, sha256, write_json
from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS, OPT_PASSES, capture_platform_dtb
from run_monitor_session import qemu_argv

REVISION = '5045d0056413266e57c625dcd7c365b10e377c52'
MASK = (1 << 64)-1
RECORD = re.compile(rb'K1(?: [0-9a-f]{16}){5}\n')

def require(condition, message):
    if not condition: raise Core0Error(message)

def inputs(root):
    pending = ['Lemma.Compiler.ClosureExport']; seen = set(); result = {}
    while pending:
        module = pending.pop()
        if module in seen or not module.startswith('Lemma.'): continue
        seen.add(module)
        path = root / (module.replace('.', '/')+'.lean')
        require(path.is_file(), 'Missing actual imported source: '+module)
        result[str(path.relative_to(root))] = sha256(path)
        for line in re.findall(r'(?m)^\s*import\s+([^\n]+)',path.read_text()): pending.extend(line.split())
    for name in ('lakefile.toml','lake-manifest.json','lean-toolchain','flake.nix','flake.lock',
                 'scripts/check_managed_closure.py','scripts/core0_common.py','scripts/build_core0.py',
                 'scripts/run_monitor_session.py','scripts/audit_kernel.py','scripts/audit_memory.py','Lemma/Compiler/Test/ManagedClosure.lean','tests/runtime/ManagedClosure.lean'):
        result[name] = sha256(root/name)
    return dict(sorted(result.items()))

def expected():
    # Independent unsigned64 arithmetic, with no inspection of target outputs.
    def selected(selector,capture):
        values = [(argument+capture)&MASK if selector == 0 else (argument*((capture+selector)&MASK))&MASK
                  for argument in (MASK,0x8000000000000001)]
        return values[0]^(values[1]>>1)
    a,b=MASK,0x8000000000000001
    constant=(b*((a+b)&MASK)+(a^b))&MASK
    four_values=[((argument+a)&MASK)^constant for argument in (MASK,0x8000000000000001)]
    four=four_values[0]^(four_values[1]>>1)
    def lamb(selector,capture):
        values=[(argument+capture)&MASK if selector==0 else (argument*capture)&MASK
                for argument in (MASK,0x8000000000000001)]
        return values[0]^(values[1]>>1)
    shared_values=[(argument+b)&MASK for argument in (MASK,0x8000000000000001)]
    shared_plus=shared_values[0]^(shared_values[1]>>1)
    shared_values=[(argument*b)&MASK for argument in (MASK,0x8000000000000001)]
    shared_times=shared_values[0]^(shared_values[1]>>1)
    return [(0,selected(0,MASK)),(0,selected(2,b)),(0,four),(0,selected(MASK,b)),
            (237,0),(237,0),(0,lamb(0,b)),(0,lamb(2,b)),(0,shared_plus),(0,shared_times)]

def observe(image,dtb,directory,deadline):
    directory.mkdir()
    argv = [*qemu_argv(image),'-dtb',str(dtb)]
    started = time.monotonic(); data=bytearray(); records=[]; pending=bytearray(); success=False
    with (directory/'stderr.log').open('wb') as stderr:
        process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=stderr,start_new_session=True)
        select=selectors.DefaultSelector(); select.register(process.stdout,selectors.EVENT_READ)
        try:
            while time.monotonic()-started < deadline:
                if process.poll() is not None: raise Core0Error('QEMU exited before complete closure observation')
                for key,_ in select.select(min(1,max(0,deadline-(time.monotonic()-started)))):
                    chunk=os.read(key.fileobj.fileno(),65536)
                    require(chunk,'Truncated actual guest UART stream')
                    data.extend(chunk); pending.extend(chunk)
                    require(len(data)<2_000_000,'Unbounded guest transcript')
                    while b'\n' in pending:
                        line,_,rest=pending.partition(b'\n'); pending=bytearray(rest); line+=b'\n'
                        require(RECORD.fullmatch(line) is not None,'Unexpected actual UART record: '+repr(line))
                        row=tuple(int(word,16) for word in line.split()[1:]); records.append(row)
                        if row[0] == 0xc7:
                            require(row==(0xc7,10,0,0,0),'Closure kernel completion count differs')
                            actual=[(r[1],r[2]) for r in records if r[0]==0xd2]
                            require(actual==expected(),'Actual isolated closure semantic/status output differs: '+repr(actual))
                            d2=[r for r in records if r[0]==0xd2]
                            require(len({r[4] for r in d2})==1 and all(r[3]<r[4] for r in d2),
                                    'Owned process frame teardown did not restore one baseline')
                            require(len([r for r in records if r[0]==0xd0])==10 and
                                    len([r for r in records if r[0]==0xd1])==10 and
                                    not any(r[0] in (0xdc,0xde,0xdd,0xe0) for r in records),'Isolation/load/exit failure')
                            success=True; break
                    if success: break
                if success: break
            require(success,'Closure observation deadline expired')
            require(not pending,'Truncated suffix after completion marker')
        finally:
            select.close()
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=10)
            (directory/'received.bin').write_bytes(data)
            write_json(directory/'observation.json',{'status':'PASS' if success else 'FAIL','argv':argv,
                'elapsed_seconds':time.monotonic()-started,'image_sha256':sha256(image),'dtb_sha256':sha256(dtb),
                'records':[list(r) for r in records],'finite_protocol':'10 independently compared exits and c7 completion before explicit kill/reap',
                'process_returncode_after_cleanup':process.returncode})
    return json.loads((directory/'observation.json').read_text())

def audit_ir(directory,role,optimization):
    unit=json.loads((directory/'unit.json').read_text()); names={r['source']:r['symbol'] for r in unit['functions']}
    require(len(names)==len(unit['functions']) and len(set(names.values()))==len(names),'Duplicate genuine source/symbol inventory')
    allowed={r['primitive_symbol'] for r in unit['used_execution_ops'] if r['primitive_symbol'] is not None}
    if role != 'user': allowed.add('core0_io_fence')
    rows=[]
    for name in ('program.ll','program.opt.ll'):
        ir=(directory/name).read_text()
        defs=re.findall(r'^define[^@\n]*@([^ (]+)',ir,re.M)
        require(set(defs)==set(names.values()) and len(defs)==len(names),'Complete checked source/LLVM correspondence differs')
        declarations=set(re.findall(r'^declare[^@\n]*@([^ (]+)',ir,re.M))
        integer_sites={
            '_private.Lemma.Kernel.Memory.UserCopy.0.Lemma.Kernel.Memory.UserCopy.firstLength':'llvm.umin.i64',
            '_private.Lemma.Kernel.Memory.Frames.0.Lemma.Kernel.Memory.Frames.releaseIndex':'llvm.umin.i64',
            '_private.Lemma.Kernel.Memory.AddressSpace.0.Lemma.Kernel.Memory.AddressSpace.findRowPageStep':'llvm.umin.i64',
            '_private.Lemma.Kernel.Loader.0.Lemma.Kernel.Loader.textStep':'llvm.umin.i64',
            '_private.Lemma.Kernel.Memory.UserCopy.0.Lemma.Kernel.Memory.UserCopy.copyFromUserResult':'llvm.umax.i32',
            'Lemma.Kernel.Memory.UserCopy.copyToUser':'llvm.umax.i32',
            'Lemma.Kernel.KernelInput.read':'llvm.umin.i64'}
        intrinsics={'llvm.umin.i64','llvm.umax.i32'} if role=='kernel' and name=='program.opt.ll' and optimization=='O2' else set()
        require(declarations<=allowed|intrinsics,'Unaccounted foreign target runtime/helper')
        for intrinsic in declarations&intrinsics:
            width=64 if intrinsic=='llvm.umin.i64' else 32
            require(re.search(r'^declare i'+str(width)+r' @'+re.escape(intrinsic)+r'\(i'+str(width)+r', i'+str(width)+r'\)',ir,re.M),
                    'Observed integer optimizer intrinsic signature differs')
        sites={}
        reverse={symbol:source for source,symbol in names.items()}
        for definition in re.finditer(r'^define[^\n]*@([^ (]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}',ir,re.M|re.S):
            actual=re.findall(r'\bcall[^@\n]*@(llvm\.[^ (]+)\(',definition[2])
            if actual:
                require(role=='kernel' and name=='program.opt.ll' and optimization=='O2' and len(actual)==1 and
                        integer_sites.get(reverse[definition[1]])==actual[0],
                        'Optimizer intrinsic escaped its exact inherited source site')
                sites[reverse[definition[1]]]=actual[0]
        if role=='kernel' and name=='program.opt.ll' and optimization=='O2':
            require(sites==integer_sites,'Complete observed inherited optimizer site inventory differs')
        require(set(re.findall(r'\bcall[^@\n]*@([^ (]+)\(',ir))<=set(names.values())|declarations,'LLVM call closure escaped checked functions')
        if role=='kernel' and name=='program.opt.ll' and optimization=='O2':
            from audit_kernel import validate_readonly_pmp_lookup
            adapted={**unit,'configuration':'normal','functions':[                {**row,'effects':[] if row['effects']=='pure' or row['effects']=='{}' else row['effects'][1:-1].split(',')}
                for row in unit['functions']]}
            _,tables=validate_readonly_pmp_lookup(ir,adapted,optimized=True)
            require({row['source'] for row in tables}=={'Lemma.Kernel.MachineServices.expectedPmp',
                'Lemma.User.CapabilityABI.typeMask','Lemma.Kernel.Objects.replyLimitFor'},
                'Exact inherited readonly source tables differ')
        else:
            require(not re.search(r'^\s*@',ir,re.M),'Unaccounted target globals/static runtime state')
        require(not re.search(r'\b(?:float|double)\b',ir) and
                not re.search(r'^(?:define|declare)\s+ptr\b|^(?:define|declare)[^\n]*@[^ (]+\([^\n]*\bptr\b',ir,re.M),
                'Target acquired unchecked pointer/float function ABI')
        rows.append({'stage':name,'sha256':sha256(directory/name),'functions':len(defs),'declarations':sorted(declarations)})
    if role=='user':
        require(unit['contract_version']=='core0-user-v0.7' and allowed=={'lemma_exec_syscall'},'User7 boundary differs')
        for suffix in ('create','release','retain','capture','finish','abort'):
            require('Lemma.User.Runtime.ManagedClosure.'+suffix in names,'Real closure graph helper missing: '+suffix)
        require(len([n for n in names if '.__lemma_managed_closure_v07.__apply' in n ])==4,'Finite genuine dispatchers absent')
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--deadline',type=float,default=180)
    parser.add_argument('--resume-export',type=Path);args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]; out=args.work_dir.resolve()
    require(out.is_relative_to(root/'build') and not out.exists(),'Must use unused ignored build output')
    require(0<args.deadline<=600,'Deadline must be finite and bounded')
    out.mkdir(parents=True); report={'status':'FAIL','scope':'isolated RV64 closure v1 qualification; no production mathematical authority'}
    commands=[]
    def invoke(argv,cwd=root,env=None,timeout=300):
        result=run_bounded(argv,cwd=cwd,env=env,timeout_seconds=timeout)
        index=len(commands);base=out/f'command-{index:03d}'
        base.with_suffix('.stdout').write_bytes(result.stdout);base.with_suffix('.stderr').write_bytes(result.stderr)
        commands.append({'argv':list(argv),'cwd':str(cwd),'returncode':result.returncode,'elapsed_seconds':result.elapsed_seconds,
                         'stdout_sha256':sha256(base.with_suffix('.stdout')),'stderr_sha256':sha256(base.with_suffix('.stderr'))})
        write_json(out/'commands.json',commands)
        require(result.returncode==0,'Actual command failed: '+' '.join(argv)+' (retained command '+str(index)+')')
        return result
    try:
        tools=require_tools(('lake','lean','opt','llc','clang','ld.lld','llvm-nm','llvm-objcopy','llvm-objdump','llvm-readelf','qemu-system-riscv64','dtc','flock'))
        report['tools']={name:{'path':path,'sha256':sha256(Path(path)),'version':invoke([name,'--version']).stdout.decode(errors='replace').splitlines()[:3]}
                         for name,path in tools.items() if name!='flock'}
        if args.resume_export is None:
            source=inputs(root);report['source_inputs']=source
            for name,digest in source.items():
                target=out/'consumed-source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
                require(sha256(target)==digest,'Source archive did not retain exact consumed bytes')
            report['base_commit']=invoke(['git','rev-parse','HEAD']).stdout.decode().strip()
            invoke(['flock',str(root/'build/task006-lake.lock'),'lake','build','Lemma.Compiler.ClosureExport'])
            consumer=out/'Export.lean';consumer.write_text('import Lemma.Compiler.ClosureExport\nset_option maxHeartbeats 12000000\n#lemma_export_closure_probe\n')
            export=out/'export';invoke(['flock',str(root/'build/task006-lake.lock'),'lake','env','lean',str(consumer)],
                                     env={**os.environ,'LEMMA_CLOSURE_PROBE_OUT':str(export)})
            require(inputs(root)==source,'Maintained source changed while consumed; preserved failed capture')
            report['source_capture']='fresh genuine elaboration with before/after source identity check'
            export_receipt={'source_inputs':source,'export_artifacts':{str(path.relative_to(export)):sha256(path)
                for path in sorted(export.rglob('*')) if path.is_file()},
                'elaboration_commands_sha256':sha256(out/'commands.json')}
            write_json(out/'export-receipt.json',export_receipt)
            report['export_receipt_sha256']=sha256(out/'export-receipt.json')
        else:
            previous=args.resume_export.resolve()
            require(previous.is_relative_to(root/'build') and previous!=out,'Resume must name retained ignored capture')
            prior=json.loads((previous/'qualification.json').read_text());source=prior['source_inputs']
            receipt=json.loads((previous/'export-receipt.json').read_text())
            require(sha256(previous/'export-receipt.json')==prior['export_receipt_sha256'] and
                    receipt['source_inputs']==source,'Retained genuine export receipt/source binding differs')
            actual={str(path.relative_to(previous/'export')):sha256(path) for path in sorted((previous/'export').rglob('*')) if path.is_file()}
            require(actual==receipt['export_artifacts'],'Retained exported source-derived LLVM/metadata changed')
            for name,digest in source.items():
                archived=previous/'consumed-source'/name
                require(sha256(archived)==digest,'Retained consumed source changed: '+name)
                target=out/'consumed-source'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(archived,target)
            original_commands=json.loads((previous/'commands.json').read_text())
            require(any(row.get('returncode')==0 and 'lake' in row.get('argv',[]) and 'env' in row.get('argv',[]) and
                        'lean' in row.get('argv',[]) and str(previous/'Export.lean') in row.get('argv',[]) for row in original_commands),
                    'Retained capture lacks actual successful elaboration command')
            export=out/'export';shutil.copytree(previous/'export',export)
            report.update(source_inputs=source,base_commit=prior['base_commit'],                source_capture='validated exact archived genuine export reuse; observer successor, fresh target execution',                reused_capture=str(previous),original_capture_report_sha256=sha256(previous/'qualification.json'),                original_commands_sha256=sha256(previous/'commands.json'),                observer_sha256=sha256(Path(__file__)))
            report['retained_export_artifacts']=receipt['export_artifacts']
            write_json(out/'export-receipt.json',receipt)
            report['export_receipt_sha256']=sha256(out/'export-receipt.json')
        metadata=json.loads((export/'closure.json').read_text())
        require(metadata['compiler_revision']==REVISION and metadata['maximum_captures']==4 and
                metadata['maximum_targets']==8 and metadata['slots']==31 and
                {row['root'] for row in metadata['genuine_ir']}=={'Lemma.User.ClosureExamples.selected',
                    'Lemma.User.ClosureExamples.fourCaptures','Lemma.User.ClosureExamples.lambdaEntry','Lemma.User.ClosureExamples.sharedCaptures'},
                'Genuine closure metadata/bounds/selected roots differ')
        capture_platform_dtb(output_dir=out,root=root,command_log=commands,timeout_seconds=30)
        results={}
        for opt in ('O0','O2'):
            build=out/opt;shutil.copytree(export,build)
            audits={}
            for role in ('firmware','kernel','user'):
                directory=build/role
                invoke(['opt',f'-passes={OPT_PASSES[opt]}','-S','program.ll','-o','program.opt.ll'],cwd=directory)
                audits[role]=audit_ir(directory,role,opt)
                invoke(['llc',*LLC_ARGUMENTS,'-stack-size-section','program.opt.ll','-o','program.o'],cwd=directory)
                undefined=invoke(['llvm-nm','--undefined-only','program.o'],cwd=directory).stdout.decode()
                allowed_object={row['primitive_symbol'] for row in json.loads((directory/'unit.json').read_text())['used_execution_ops'] if row['primitive_symbol'] is not None}
                if role!='user':allowed_object.add('core0_io_fence')
                require(set(re.findall(r'\bU\s+(\S+)',undefined))<=allowed_object,'Integer intrinsic acquired target runtime/object helper')
                invoke(['llvm-readelf','-h','-A','-S','-r','program.o'],cwd=directory)
                disassembly=invoke(['llvm-objdump','-d','--no-show-raw-insn','program.o'],cwd=directory).stdout.decode()
                if role=='user':
                    from audit_kernel import INTEGER_INSTRUCTIONS
                    opcodes=re.findall(r'^\s*[0-9a-f]+:\s+([A-Za-z.][A-Za-z0-9.]*)',disassembly,re.M)
                    forbidden={'ecall','wfi','sret','mret','sfence.vma','rdtime','rdcycle','rdinstret'}
                    require(opcodes and set(opcodes)<=INTEGER_INSTRUCTIONS and
                            not any(op in forbidden or op.startswith('csr') for op in opcodes),
                            'Compiled ordinary User closure object acquired unaccounted/privileged instructions')
            invoke(['clang',*STARTUP_ARGUMENTS,'user/startup.S','-o','user/startup.o'],cwd=build)
            invoke(['ld.lld','-m','elf64lriscv','--no-relax','-T','user/link.ld','user/startup.o','user/program.o','-o','user/image.elf'],cwd=build)
            require(not invoke(['llvm-nm','--undefined-only','user/image.elf'],cwd=build).stdout.strip(),'User ELF unresolved helpers')
            invoke(['llvm-objcopy','--dump-section=.text=user-text.bin','--dump-section=.data=user-data.bin','user/image.elf'],cwd=build)
            invoke(['clang',*STARTUP_ARGUMENTS,'startup.S','-o','startup.o'],cwd=build)
            invoke(['clang',*STARTUP_ARGUMENTS,'boot-package.S','-o','boot-package.o'],cwd=build)
            invoke(['ld.lld','-m','elf64lriscv','--no-relax','-T','link.ld','startup.o','firmware/program.o','kernel/program.o','boot-package.o','-o','image.elf'],cwd=build)
            require(not invoke(['llvm-nm','--undefined-only','image.elf'],cwd=build).stdout.strip(),'Boot ELF unresolved helpers')
            for elf in ('user/image.elf','image.elf'):
                observed=invoke(['llvm-readelf','-h','-A','-l','-S',elf],cwd=build).stdout.decode()
                require('RISC-V' in observed and 'rv64i2p1_m2p0' in observed,'Linked ELF ISA differs')
                require(' RWE ' not in observed,'Linked ELF acquired RWX segment')
            results[opt]={'ir_audits':audits,'image_sha256':sha256(build/'image.elf'),
                          'user_sha256':sha256(build/'user/image.elf'),'guest':observe(build/'image.elf',out/'platform.dtb',build/'run',args.deadline)}
        report.update(status='PASS',results=results,expected_outputs=expected(),closure_metadata_sha256=sha256(export/'closure.json'))
    finally:
        write_json(out/'qualification.json',report);write_json(out/'commands.json',commands)
    print('MANAGED_CLOSURE_RV64:PASS O0/O2 real isolated closures + aliases/reclamation +31slot OOM')

if __name__=='__main__':
    try:main()
    except (Core0Error,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as error:
        print('MANAGED_CLOSURE_RV64:FAIL',error,file=sys.stderr);raise SystemExit(1)
