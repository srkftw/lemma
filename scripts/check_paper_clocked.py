#!/usr/bin/env python3
"""Bounded genuine Clocked13 K6 lowering and complete component artifact guards.

No CPU, full linked guest, physical timing, Pending or notebook qualification is
claimed by this command. Reuse requires an explicit genuine source receipt,
complete original source archive, exact artifact hashes and unchanged target/tool
inputs; any observer-only revision is recorded separately from original results.
"""
import argparse,json,os,shutil,sys,time
from pathlib import Path
from core0_common import Core0Error,require_tools,run_bounded,sha256
from build_core0 import LLC_ARGUMENTS
from build_kernel import source_inputs
from check_paper_wire import validate_kernel_attributes
from paper_clocked import validate
from audit_kernel import validate_unit,validate_ir,alloc_section_names,inspect_backend_jump_tables
from lemmasim_readonly import validate_object
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/kernel'))
from paper_clocked_mutations import exercise,backend_exercise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--dtb',type=Path,required=True,help='Actual generated Clocked13 DTB, consumed by genuine Action/fault fixture')
    p.add_argument('--kernel-component',type=Path,help='Explicit genuine two-role component receipt/archive; only recorded host observer differences allowed')
    p.add_argument('--timeout',type=int,default=420)
    a=p.parse_args();out=a.work_dir.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build') or not 180<=a.timeout<=600:p.error('unused build output and timeout180..600 required')
    out.mkdir(parents=True);start=time.monotonic();r={'schema_version':1,'status':'FAIL','scope':__doc__,'commands':[]}
    extra=('scripts/check_paper_clocked.py','scripts/check_paper_wire.py','tests/kernel/paper_clocked_mutations.py','tests/kernel/ClockedDiscoveryFlags.lean')
    def inventory():return {**source_inputs(ROOT),**{n:sha256(ROOT/n) for n in extra}}
    def run(argv,label,cwd=ROOT,env=None):
        remaining=a.timeout-(time.monotonic()-start)
        if remaining<=0:raise Core0Error('original component deadline exhausted')
        q=run_bounded(argv,cwd=cwd,env=env,timeout_seconds=remaining)
        (out/(label+'.log')).write_bytes(q.stdout+q.stderr)
        r['commands'].append({'argv':list(q.argv),'returncode':q.returncode,'host_seconds':q.elapsed_seconds,'log':label+'.log'})
        if q.returncode:raise Core0Error('component command failed: '+label)
        return q.stdout.decode()
    try:
        before=inventory();r['source_inputs']=before;r['dtb']={'path':str(a.dtb.resolve()),'sha256':sha256(a.dtb)}
        tools=require_tools(['lake','opt','llc','llvm-readobj','llvm-nm','llvm-readelf','llvm-objcopy','llvm-mc']);r['tools']={}
        for name,path in tools.items():
            q=run_bounded([path,'--version'],cwd=ROOT,timeout_seconds=30)
            if q.returncode or not path.startswith('/nix/store/') or not q.stdout.strip():raise Core0Error('missing pinned tool identity: '+name)
            r['tools'][name]={'path':path,'sha256':sha256(Path(path)),'version':q.stdout.decode().splitlines()[:4]}
        archive=out/'consumed-source-root'
        for name,digest in before.items():
            target=archive/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
            if sha256(target)!=digest:raise Core0Error('current input changed during archive copy: '+name)
        reused=None
        if a.kernel_component:
            origin=a.kernel_component.resolve();reused=json.loads((origin/'result.json').read_text())
            if reused.get('status')!='PASS_GENUINE_COMPONENT_EXPORT_OBJECT_ONLY' or not reused.get('source_inputs_equal'):raise Core0Error('missing genuine original component source admission')
            original=reused['source_inputs']
            current={**source_inputs(ROOT),'tests/kernel/ClockedDiscoveryFlags.lean':sha256(ROOT/'tests/kernel/ClockedDiscoveryFlags.lean')}
            if set(current)!=set(original):raise Core0Error('reused complete input inventory differs')
            changed={n for n in original if original[n]!=current[n]}
            if not changed<={'scripts/audit_kernel.py','scripts/lemmasim_readonly.py','scripts/paper_clocked.py'}:raise Core0Error('reused target/compiler/profile/tool inputs changed')
            for name,digest in original.items():
                if sha256(origin/'consumed-source-root'/name)!=digest:raise Core0Error('original complete archive changed: '+name)
            for name,old in reused['tools'].items():
                if (old['path'],old['sha256'])!=(r['tools'][name]['path'],r['tools'][name]['sha256']):raise Core0Error('reused pinned compiler tool differs: '+name)
            r['reused_genuine_component']={'path':str(origin),'receipt_sha256':sha256(origin/'result.json'),'original_source_inputs':original,'observer_only_changes':{n:{'original':original[n],'current':current[n]} for n in sorted(changed)},'scope':'Original export/object result remains unchanged; current full observer is a separate component qualification.'}
        run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'build','Lemma.Platform.LemmaSim.NotebookKernel','Lemma.Compiler.KernelExport'],'lake')
        raw=run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean','tests/kernel/ClockedDiscoveryFlags.lean'],'raw-fdt-action',env={**os.environ,'LEMMA_CLOCKED_DTB':str(a.dtb.resolve())})
        if raw.count('CLOCKED_RAW_FDT:PASS17FLAGS_6FACTS_DUPLICATE_WIDTH_30FAULTS_6REGISTERS_12NEGATIVES')!=1:raise Core0Error('actual Action/rawFDT/fault fixture did not complete')
        roles={};shared=[]
        for role,entry in (('notebook','siliconUSBClockedBoot'),('initializer','siliconUSBClockedInitializeMedium')):
            d=out/role;d.mkdir();cfg='lemmasim-silicon-usb-clocked-bulk-'+('initialize' if role=='initializer' else 'notebook')
            if reused:
                for name,digest in reused['roles'][role]['artifacts'].items():
                    source=origin/role/name
                    if sha256(source)!=digest:raise Core0Error('reused original artifact changed: '+role+'/'+name)
                    shutil.copyfile(source,d/name)
            else:
                (d/'Export.lean').write_text('import Lemma.Platform.LemmaSim.NotebookKernel\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "kernel" [Lemma.Platform.LemmaSim.NotebookKernel.'+entry+', Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBClockedBulk]\n')
                env={**os.environ,'LEMMA_KERNEL_CONFIGURATION':cfg,'LEMMA_KERNEL_OUT':str(d)}
                run(['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean',str(d/'Export.lean')],role+'-export',env=env)
                run([tools['opt'],'-S','-passes=default<O2>','program.ll','-o','program.opt.ll'],role+'-opt',d)
                run([tools['llc'],*LLC_ARGUMENTS,'-O2','-stack-size-section','program.opt.ll','-o','program.o'],role+'-object',d)
            unit=json.loads((d/'unit.json').read_text());validate_unit(unit,'kernel',configuration=cfg)
            pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text()
            authority={kind:validate(ir,unit,optimized=kind=='post') for kind,ir in [('pre',pre),('post',post)]}
            ir={'pre':validate_ir(pre,unit,optimized=False),'post':validate_ir(post,unit,optimized=True,optimization='O2')}
            rejected=exercise(pre,post,unit)
            attrs=run([tools['llvm-readobj'],'--file-headers','--arch-specific','program.o'],role+'-attributes',d);validate_kernel_attributes(attrs)
            undefined=run([tools['llvm-nm'],'--undefined-only','program.o'],role+'-undefined',d)
            actual={line.split()[-1] for line in undefined.splitlines() if line.strip()}
            declared={op['primitive_symbol'] for op in unit['used_execution_ops'] if op['primitive_symbol'] is not None}
            if unit['used_device_ops'] or any(op['stable_id'].startswith('lemmasim.device-') for op in unit['used_execution_ops']):declared.add('core0_io_fence')
            if actual!=declared:raise Core0Error('undeclared RV64 component runtime boundary')
            def inspect(tool,args,label):return run([tools[tool],*(['--elf-output-style=GNU'] if tool=='llvm-readelf' else []),*args],role+'-'+label,d)
            sections=inspect('llvm-readelf',['-S','--wide','program.o'],'sections');symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'symbols');relocs=inspect('llvm-readelf',['-r','program.o'],'relocations')
            raws={}
            for name in ('.rodata','.rodata.cst32'):
                if name in alloc_section_names(sections):
                    file='literal-'+name[1:]+'.bin';inspect('llvm-objcopy',['-O','binary','--only-section='+name,'program.o',file],file);raws[name]=(d/file).read_bytes()
            readonly=validate_object(sections,symbols,relocs,raws,ir['post']['readonly_optimizer_tables'],'program.o')
            backend=inspect_backend_jump_tables(inspect,d,object_file='program.o',section_text=sections,symbol_text=symbols,relocation_text=relocs,unit=unit,optimization='O2',readonly_tables=readonly['readonly_tables'])
            rejected+=backend_exercise((d/'program-audit-companion.s').read_text(),backend,unit)
            shared.append({kind:{s:digest for s,digest in authority[kind]['complete_body_identities'].items() if not s.endswith(('.siliconUSBClockedBoot','.siliconUSBClockedInitializeMedium'))} for kind in ('pre','post')})
            roles[role]={'configuration':cfg,'authorities':authority,'complete_ir':ir,'readonly_object':readonly,'backend_object':backend,'rejected_mutations':rejected,'declared_undefined_boundaries':sorted(actual),'artifacts':{n:sha256(d/n) for n in ('Export.lean','unit.json','program.ll','program.opt.ll','program.o')}}
            r['roles']=roles
        if shared[0]!=shared[1] or any(len(shared[0][kind])!=49 for kind in ('pre','post')):raise Core0Error('49 actual shared successor bodies differ across roles')
        if inventory()!=before or sha256(a.dtb)!=r['dtb']['sha256']:raise Core0Error('consumed component sources/rawFDT changed')
        r.update(status='PASS_GENUINE_COMPONENT_AND_COMPLETE_ARTIFACT_GUARDS',roles=roles,source_inputs_equal=True,shared_authorities_pre_post=49)
    except BaseException as e:r['error']=repr(e)
    finally:
        r['host_seconds']=time.monotonic()-start
        (out/'result.json').write_text(json.dumps(r,indent=2)+'\n')
        print(json.dumps({k:r[k] for k in ('status','error','host_seconds') if k in r}),flush=True)
    return 0 if r['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
