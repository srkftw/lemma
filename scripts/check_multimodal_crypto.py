#!/usr/bin/env python3
"""Build genuine Lean RFC8439 workload, audit closure and execute RV64 QEMU.
Finite component evidence only: not production identity, privacy or P1/P2.
"""
import argparse,ast,fcntl,hashlib,json,os,re,struct,subprocess,sys,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS,STARTUP_ARGUMENTS
from audit_core0 import parse_stack_sizes,validate_loop_stack_call_graph
from audit_kernel import validate_machine
from check_crypto import audit_elf
ROOT=Path(__file__).resolve().parents[1]
OPS={'execution.physical-read8','execution.physical-read64','execution.physical-write8','execution.physical-write64'}
DEVICE={'uart.enable-reset-fifo','uart.write-byte','uart.read-status'}
REQUIRED={'Lemma.Crypto.'+n for n in ['ChaCha20.block','ChaCha20.quarter','Poly1305.authenticate','Poly1305.process','AEAD.seal','AEAD.open','AEAD.mac','MultimodalProbe.entry']}

def audit_ir(unit,pre,post):
    if unit.get('schema')!='lemma-multimodal-crypto-rv64-component/1' or unit.get('contract_version')!='core0-boot-v0.1' or unit.get('root')!='Lemma.Crypto.MultimodalProbe.entry':raise Core0Error('unknown component tuple')
    if set(unit.get('used_execution_ops',[]))!=OPS or set(unit.get('used_device_ops',[]))!=DEVICE:raise Core0Error('effect boundary differs')
    sources={};symbols={}
    for row in unit.get('functions',[]):
        name=re.sub(r'^_private\.[^.]+(?:\.[^.]+)*?\.[0-9]+\.(Lemma\..*)$',r'\1',row['source']);symbol=row['symbol']
        if not (name.startswith(('Lemma.Crypto.','Lemma.Kernel.Memory.Access.','Lemma.Boot.RecoveryExecuted.transmit')) or name in ('Lemma.Core0.Memory.Status.iterationStop','Lemma.Core0.Memory.Status.txTimeout')):raise Core0Error('foreign crypto source '+name)
        if name in sources or symbol in symbols or not re.fullmatch(r'lemma_crypto_core0_(scalar|action)_[0-9]+',symbol):raise Core0Error('ambiguous crypto provenance')
        if any(a not in ('u8','u32','u64','bool') for a in row['args']):raise Core0Error('foreign crypto ABI')
        sources[name]=row;symbols[symbol]=name
    if not REQUIRED<=sources.keys() or unit['entry_symbol']!=sources[unit['root']]['symbol']:raise Core0Error('missing actual AEAD closure '+repr(REQUIRED-sources.keys()))
    for phase,ir in [('pre',pre),('post',post)]:
        definitions=re.findall(r'(?m)^define[^\n]*@([A-Za-z_0-9.$]+)\(',ir)
        if not definitions or len(definitions)!=len(set(definitions)) or not set(definitions)<=symbols.keys() or phase=='pre' and set(definitions)!=symbols.keys():raise Core0Error('definition closure differs')
        if re.search(r'(?m)^@|\basm\b|\b(?:invoke|landingpad|resume|callbr|indirectbr|alloca)\b',ir) or re.search(r'\bcall[^\n]*%[A-Za-z_][A-Za-z_0-9]*\(',ir):raise Core0Error('foreign code/data/dispatch')
        declarations={name:result+'('+re.sub(r'\s+','',args)+')' for result,name,args in re.findall(r'(?m)^declare\s+(void|i[0-9]+)\s+@([^ (]+)\(([^)]*)\)',ir)}
        if declarations.pop('core0_io_fence',None)!='void()' or any(n!='llvm.umin.i64' or s!='i64(i64,i64)' for n,s in declarations.items()) or phase=='pre' and declarations:raise Core0Error('unaccounted runtime')
        if not set(re.findall(r'\bcall[^\n]*@([A-Za-z_0-9.$]+)\(',ir))<=set(definitions)|set(declarations)|{'core0_io_fence'}:raise Core0Error('unresolved IR call')
    return {'genuine_functions':len(sources),'optimized_functions':len(definitions),'helpers':['core0_io_fence'],'intrinsics':declarations}

def complete_sources():
    """Exact transitive maintained Lean/compiler and host-tool import inputs.
    Missing/unknown project imports reject; local Python imports are closed
    recursively. Current contracts and tool locks keep renamed authorities in
    the consumed inventory, never silently optional old .md lookups.
    """
    paths=set();pending=['Lemma/Crypto/MultimodalProbe.lean','Lemma/Compiler/MultimodalCryptoExport.lean','tests/multimodal/Crypto.lean']
    while pending:
        name=pending.pop()
        if name in paths:continue
        path=ROOT/name
        if not path.is_file():raise Core0Error('missing maintained Lean input '+name)
        paths.add(name)
        for line in re.findall(r'(?m)^\s*import\s+([^\n]+)',path.read_text()):
            for module in line.split():
                if module.startswith('Lemma.'):
                    if not re.fullmatch(r'Lemma(?:\.[A-Za-z0-9_]+)+',module):raise Core0Error('unknown project import '+module)
                    pending.append(module.replace('.','/')+'.lean')
                elif not any(module==prefix or module.startswith(prefix+'.') for prefix in ('Lean','Init','Std')):raise Core0Error('unknown upstream import '+module)
    pending=[Path(__file__).name]
    while pending:
        name=pending.pop();relative='scripts/'+name
        if relative in paths:continue
        path=ROOT/relative
        if not path.is_file():raise Core0Error('missing host tool input '+relative)
        paths.add(relative)
        for node in ast.walk(ast.parse(path.read_text(),filename=str(path))):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for module in modules:
                first=module.split('.')[0];local=ROOT/'scripts'/(first+'.py')
                if local.is_file():pending.append(local.name)
                elif first not in sys.stdlib_module_names and first!='__future__':raise Core0Error('unknown host dependency '+module)
    for name in ('flake.nix','flake.lock','lean-toolchain','lakefile.toml','lake-manifest.json','tooling/toolchain-lock.json','docs/document-map.json'):
        if not (ROOT/name).is_file():raise Core0Error('missing source/tool/contract authority '+name)
        paths.add(name)
    contracts=sorted((ROOT/'docs/contracts').glob('*.html'))
    if not contracts:raise Core0Error('missing current HTML contracts')
    paths.update(str(p.relative_to(ROOT)) for p in contracts)
    if len(paths)<50:raise Core0Error('unexpectedly short complete source closure')
    return {name:sha256(ROOT/name) for name in sorted(paths)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build'):p.error('unused ignored output required')
    out.mkdir(parents=True);began=time.monotonic();process=None
    report={'status':'FAIL','scope':__doc__,'bounds':{'aggregate_seconds':600,'qemu_seconds':60},'source_inputs':complete_sources(),'commands':[]}
    try:
        report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        archive=out/'consumed-source-root';archive.mkdir()
        for name,identity in report['source_inputs'].items():
            source=ROOT/name
            if sha256(source)!=identity:raise Core0Error('source changed before snapshot '+name)
            target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        tools=require_tools(('lake','lean','opt','llc','clang','ld.lld','llvm-nm','llvm-readelf','llvm-objdump','qemu-system-riscv64'))
        report['tools']={k:{'path':str(v),'sha256':sha256(Path(v))} for k,v in tools.items()}
        if any(not str(v).startswith('/nix/store/') for v in tools.values()):raise Core0Error('pinned tools required')
        def run(label,argv,env=None):
            remaining=600-(time.monotonic()-began)
            if remaining<=0:raise Core0Error('aggregate deadline')
            r=run_bounded(argv,cwd=ROOT,timeout_seconds=min(180,remaining),env=env);(out/(label+'.log')).write_bytes(r.stdout+r.stderr)
            report['commands'].append({'argv':list(r.argv),'returncode':r.returncode,'seconds':r.elapsed_seconds})
            if r.returncode:raise Core0Error('actual command failed: '+label)
            return r.stdout.decode()
        env={**os.environ,'LEAN_NUM_THREADS':'2','LEMMA_MULTIMODAL_CRYPTO_OUT':str(out/'component')}
        export=out/'Export.lean';export.write_text('import Lemma.Compiler.MultimodalCryptoExport\n#lemma_export_multimodal_crypto\n')
        with (ROOT/'build/multimodal-lake.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            run('elaborate',[tools['lake'],'build','Lemma.Crypto.MultimodalProbe','Lemma.Compiler.MultimodalCryptoExport'],env)
            if run('actions',[tools['lake'],'env','lean',str(ROOT/'tests/multimodal/Crypto.lean')],env).count('MULTIMODAL_CRYPTO_ACTIONS:PASS')!=1:raise Core0Error('missing Action vectors')
            if run('export',[tools['lake'],'env','lean',str(export)],env).count('MULTIMODAL_CRYPTO_EXPORT:PASS')!=1:raise Core0Error('missing genuine export')
        d=out/'component';run('verify',[tools['opt'],'-passes=verify','-disable-output',str(d/'program.ll')]);run('opt',[tools['opt'],'-S','-passes=default<O2>',str(d/'program.ll'),'-o',str(d/'program.opt.ll')])
        pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text();report['closure']=audit_ir(json.loads((d/'unit.json').read_text()),pre,post)
        run('llvm',[tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section',str(d/'program.opt.ll'),'-o',str(d/'program.o')]);run('startup',[tools['clang'],*STARTUP_ARGUMENTS,str(d/'startup.S'),'-o',str(d/'startup.o')])
        if run('object-undefined',[tools['llvm-nm'],'--undefined-only',str(d/'program.o')]).split()!=['U','core0_io_fence']:raise Core0Error('unaccounted object runtime')
        run('link',[tools['ld.lld'],'-m','elf64lriscv','--no-relax','-T',str(d/'link.ld'),'-o',str(d/'image.elf'),str(d/'startup.o'),str(d/'program.o')])
        if run('undefined',[tools['llvm-nm'],'--undefined-only',str(d/'image.elf')]).strip():raise Core0Error('unresolved runtime')
        if 'There are no relocations in this file.' not in run('relocations',[tools['llvm-readelf'],'--elf-output-style=GNU','-r',str(d/'image.elf')]):raise Core0Error('runtime relocations')
        validate_machine(run('machine',[tools['llvm-objdump'],'-d','--no-show-raw-insn',str(d/'image.elf')]))
        report['stack']=validate_loop_stack_call_graph(post,parse_stack_sizes(run('stack',[tools['llvm-readelf'],'--elf-output-style=GNU','--stack-sizes',str(d/'program.o')])))
        # Only constants present in the audited pre/post scalar LLVM closure
        # may become8byte literal-pool words; arbitrary linked data is rejected.
        constants={int(x)&0xffffffffffffffff for x in re.findall(r'(?<![A-Za-z_0-9.])-?[0-9]+(?![A-Za-z_0-9.])',pre+'\n'+post)}
        report['elf']=audit_elf((d/'image.elf').read_bytes(),literals=constants)
        run('attributes',[tools['llvm-readelf'],'--elf-output-style=GNU','-h','-l','-A','-S',str(d/'image.elf')])
        uart=out/'uart.bin';argv=[tools['qemu-system-riscv64'],'-machine','virt','-cpu','rv64','-m','128M','-bios','none','-kernel',str(d/'image.elf'),'-display','none','-monitor','none','-serial','file:'+str(uart)]
        report['qemu_argv']=argv;started=time.monotonic()
        with (out/'qemu.log').open('xb') as log:
            process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while True:
                wire=uart.read_bytes() if uart.exists() else b''
                if len(wire)>=336:break
                if process.poll() is not None or time.monotonic()-started>=60:raise Core0Error('guest deadline before actual terminal')
                time.sleep(.02)
        # 3headers*24 +16tag+120ciphertext+120plaintext+8terminal =336.
        if len(wire)!=336:raise Core0Error('actual protocol length')
        expected_cipher=bytes.fromhex('d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d63dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b3692ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc3ff4def08e4b7a9de576d26586cec64b6116')
        message=b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it."
        expected_headers=[(0,1,0),(160,2,0),(304,3,247)]
        for offset,case,status in expected_headers:
            if struct.unpack_from('<3Q',wire,offset)!=(0x32444145414d454c,case,status):raise Core0Error('actual guest status differs')
        if wire[24:40]!=bytes.fromhex('1ae10b594f09e26a7e902ecbd0600691') or wire[40:154]!=expected_cipher or wire[184:298]!=message or wire[328:]!=struct.pack('<Q',0x32444e45414d454c):raise Core0Error('actual RFC8439 output differs')
        report['actual_rv64']={'status':'PASS','aead_ciphertext_bytes':114,'authenticated_plaintext_bytes':114,'bad_tag_status':247,'seconds':time.monotonic()-started,'uart_sha256':sha256(uart),'relation':'exact RFC8439 ciphertext/tag/plaintext; explicit tamper rejection; finite standalone CPU component'}
        report['artifacts']={str(f.relative_to(out)):sha256(f) for f in d.iterdir() if f.is_file()}
        if any(sha256(ROOT/name)!=h for name,h in report['source_inputs'].items()):raise Core0Error('consumed source changed')
        report['status']='PASS_GENUINE_RV64_RFC8439_COMPONENT'
    except BaseException as error:report['error']=repr(error)
    finally:
        if process:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
            report['qemu_reaped']=process.returncode is not None
        report['seconds']=time.monotonic()-began
        (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('status','seconds','error')}));return 0 if report['status'].startswith('PASS_') else 1
if __name__=='__main__':raise SystemExit(main())
