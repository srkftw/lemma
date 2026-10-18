#!/usr/bin/env python3
"""Fresh genuine Lean -> LLVM -> RV64 converter/PCM component production.
No simulator execution claim is made by this builder. Use the resulting exact
ELF on both controller bindings and independently inspect capture records.
"""
import argparse, hashlib, json, os, re, subprocess, time
from pathlib import Path
from core0_common import Core0Error, require_tools, run_bounded, sha256, write_json
from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS
from audit_core0 import parse_stack_sizes, validate_loop_stack_call_graph
from audit_kernel import validate_machine
ROOT=Path(__file__).resolve().parents[1]
PREFIXES=('Lemma.Multimodal.ControllerProbe.','Lemma.Drivers.Multimodal.',
          'Lemma.Platform.Silicon.BindingMultimodal.','Lemma.Platform.LemmaSim.IO.',
          'Lemma.Kernel.Memory.Access.','Lemma.Boot.RecoveryExecuted.transmit')
OPS={'execution.physical-write64','lemmasim.device-read64','lemmasim.device-write64'}
DEVICE={'uart.enable-reset-fifo','uart.read-status','uart.write-byte'}


def audit(unit,pre,post):
    if (unit.get('schema'),unit.get('contract_version'),unit.get('root')) != (
        'lemma-multimodal-controller-rv64-component/1','core0-kernel-v0.9','Lemma.Multimodal.ControllerProbe.entry'):
        raise Core0Error('unknown controller component identity')
    if set(unit['used_execution_ops'])!=OPS or set(unit['used_device_ops'])!=DEVICE:
        raise Core0Error('unknown controller component authority')
    symbols={}
    for row in unit['functions']:
        name=re.sub(r'^_private\..*?\.\d+\.(Lemma\..*)$',r'\1',row['source'])
        if not (name.startswith(PREFIXES) or name in ('Lemma.Core0.Memory.Status.iterationStop','Lemma.Core0.Memory.Status.txTimeout')):
            raise Core0Error('unknown controller source '+name)
        if row['symbol'] in symbols or not re.fullmatch(r'lemma_multimodal_probe_core0_(scalar|action)_\d+',row['symbol']):
            raise Core0Error('duplicate/unknown controller symbol')
        if any(a not in ('u8','u32','u64','bool') for a in row['args']):raise Core0Error('unknown source ABI')
        symbols[row['symbol']]=name
    if unit['entry_symbol'] not in symbols or symbols[unit['entry_symbol']]!=unit['root']:
        raise Core0Error('missing compiled controller entry')
    reports=[]
    for phase,ir in [('pre',pre),('post',post)]:
        definitions=re.findall(r'(?m)^define[^\n]*@([A-Za-z_0-9.$]+)\(',ir)
        if not definitions or len(definitions)!=len(set(definitions)) or not set(definitions)<=symbols.keys() or (phase=='pre' and set(definitions)!=symbols.keys()):
            raise Core0Error('definition/source closure differs')
        if re.search(r'(?m)^@|\basm\b|\b(?:invoke|landingpad|resume|callbr|indirectbr|alloca)\b',ir) or re.search(r'\bcall[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):
            raise Core0Error('unaccounted globals/code/dispatch')
        declared={n:r+'('+re.sub(r'\s+','',a)+')' for r,n,a in re.findall(r'(?m)^declare\s+(void|i[0-9]+)\s+@([^ (]+)\(([^)]*)\)',ir)}
        if declared.pop('core0_io_fence',None)!='void()' or any(n not in ('llvm.umin.i64','llvm.umax.i64') or a!='i64(i64,i64)' for n,a in declared.items()):
            raise Core0Error('unknown runtime helper')
        calls=set(re.findall(r'\bcall[^\n]*@([A-Za-z_0-9.$]+)\(',ir))
        if not calls<=set(definitions)|set(declared)|{'core0_io_fence'}:raise Core0Error('unresolved IR dependency')
        reports.append({'phase':phase,'functions':len(definitions),'intrinsics':declared})
    return reports


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=300)
    a=p.parse_args();out=a.output_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build') or not 0<a.timeout<=600:p.error('unused ignored output and bounded timeout required')
    out.mkdir(parents=True);start=time.monotonic()
    report={'schema':'lemma-multimodal-controller-production/1','status':'FAIL','execution':'NOT_RUN',
            'commands':[],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'limits':{'whole_seconds':a.timeout,'command_seconds':180}}
    # Component's genuine source plus compiler closure. No mutable artifact or
    # path from another worktree is admitted as a source/compiled dependency.
    files=sorted((ROOT/'Lemma').rglob('*.lean'))+[Path(__file__),ROOT/'lean-toolchain',ROOT/'flake.lock']
    before={str(f.relative_to(ROOT)):sha256(f) for f in files};report['source_inputs']=before
    try:
        tools=require_tools(('lake','lean','opt','llc','clang','ld.lld','llvm-nm','llvm-readelf','llvm-objdump'))
        report['tools']={n:{'path':str(t),'sha256':sha256(Path(t))} for n,t in tools.items()}
        if any(not str(t).startswith('/nix/store/') for t in tools.values()):raise Core0Error('immutable pinned tools required')
        def run(label,argv,env=None):
            left=a.timeout-(time.monotonic()-start)
            if left<=0:raise Core0Error('component deadline')
            r=run_bounded(argv,cwd=ROOT,timeout_seconds=min(left,180),env=env)
            (out/(label+'.log')).write_bytes(r.stdout+r.stderr)
            report['commands'].append({'label':label,'argv':list(r.argv),'returncode':r.returncode,'seconds':r.elapsed_seconds})
            if r.returncode:raise Core0Error('actual component operation failed: '+label)
            return r.stdout.decode()
        run('elaborate',[tools['lake'],'build','Lemma.Compiler.MultimodalProbeExport'])
        export=out/'Export.lean';export.write_text('import Lemma.Compiler.MultimodalProbeExport\n#lemma_export_multimodal_probe\n')
        d=out/'component'
        output=run('export',[tools['lake'],'env','lean',str(export)],{**os.environ,'LEAN_NUM_THREADS':'2','LEMMA_MULTIMODAL_PROBE_OUT':str(d)})
        if output.count('MULTIMODAL_PROBE_EXPORT:PASS')!=1:raise Core0Error('missing genuine export receipt')
        run('verify',[tools['opt'],'-passes=verify','-disable-output',str(d/'program.ll')])
        run('opt',[tools['opt'],'-S','-passes=default<O2>',str(d/'program.ll'),'-o',str(d/'program.opt.ll')])
        unit=json.loads((d/'unit.json').read_text());post=(d/'program.opt.ll').read_text()
        report['closure']=audit(unit,(d/'program.ll').read_text(),post)
        run('llvm',[tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section',str(d/'program.opt.ll'),'-o',str(d/'program.o')])
        run('startup',[tools['clang'],*STARTUP_ARGUMENTS,str(d/'startup.S'),'-o',str(d/'startup.o')])
        if run('object-undefined',[tools['llvm-nm'],'--undefined-only',str(d/'program.o')]).split()!=['U','core0_io_fence']:
            raise Core0Error('unknown compiled runtime dependency')
        run('link',[tools['ld.lld'],'-m','elf64lriscv','--no-relax','-T',str(d/'link.ld'),'-o',str(d/'image.elf'),str(d/'startup.o'),str(d/'program.o')])
        if run('undefined',[tools['llvm-nm'],'--undefined-only',str(d/'image.elf')]).strip():raise Core0Error('unresolved linked runtime')
        if 'There are no relocations in this file.' not in run('relocations',[tools['llvm-readelf'],'--elf-output-style=GNU','-r',str(d/'image.elf')]):raise Core0Error('runtime relocation')
        validate_machine(run('machine',[tools['llvm-objdump'],'-d','--no-show-raw-insn',str(d/'image.elf')]))
        report['stack']=validate_loop_stack_call_graph(post,parse_stack_sizes(run('stack',[tools['llvm-readelf'],'--elf-output-style=GNU','--stack-sizes',str(d/'program.o')])))
        attributes=run('attributes',[tools['llvm-readelf'],'--elf-output-style=GNU','-h','-l','-A','-S',str(d/'image.elf')])
        import struct
        data=(d/'image.elf').read_bytes()
        if len(data)<64 or data[:7]!=b'\x7fELF\x02\x01\x01':raise Core0Error('not ELF64 little endian')
        elf=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
        if (elf[1],elf[2],elf[3],elf[4],elf[7],elf[8],elf[9])!=(2,243,1,0x80000000,0,64,56):raise Core0Error('ELF architecture/entry/flags differ')
        loads=[struct.unpack_from('<IIQQQQQQ',data,elf[5]+i*56) for i in range(elf[10])]
        loads=[h for h in loads if h[0]==1]
        if len(loads)!=1 or loads[0][1]!=5 or loads[0][3]!=0x80000000 or loads[0][4]!=0x80000000 or not 0<loads[0][5]==loads[0][6]<=65536:
            raise Core0Error('component ELF must contain only bounded RX code, no runtime data image')
        if 'rv64i' not in attributes or 'RISC-V' not in attributes:raise Core0Error('missing RV64 attributes')
        report['elf']={'RX_load_bytes':loads[0][5],'entry':elf[4],'flags':elf[7],'load_count':1}
        if before!={str(f.relative_to(ROOT)):sha256(f) for f in files}:raise Core0Error('component source changed during production')
        report.update(status='BUILT_AUDITED_COMPONENT',image={'path':str(d/'image.elf'),'sha256':sha256(d/'image.elf')},
                      scope='genuine compiled controller component; no execution or full notebook acceptance')
    except (OSError,ValueError,KeyError,Core0Error) as e:report['error']=str(e)
    report['seconds']=time.monotonic()-start
    report['artifacts']={str(f.relative_to(out)):sha256(f) for f in out.rglob('*') if f.is_file()}
    write_json(out/'result.json',report)
    print(report['status']+(': '+report.get('error','')))
    return 0 if report['status']=='BUILT_AUDITED_COMPONENT' else 1
if __name__=='__main__':raise SystemExit(main())
