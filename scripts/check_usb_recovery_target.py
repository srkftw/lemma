#!/usr/bin/env python3
"""Bounded, source-bound four-role Recovery artifact and Action qualification.

This inspects a genuine original capture and its complete archived sources.
Only the listed artifact-observer additions may differ. It never rewrites
provenance, executes target instructions, formats media or claims guest recovery.
Fresh ordinary whole builds and connected recovery remain separately required.
"""
import argparse,json,os,resource,shutil,sys,time
from pathlib import Path
from core0_common import Core0Error,run_bounded,sha256
from build_kernel import source_inputs
from audit_kernel import validate_unit,validate_ir,alloc_section_names,inspect_backend_jump_tables,validate_backend_jump_tables
from lemmasim_readonly import validate_object
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/kernel'))
from usb_recovery_mutations import exercise,backend_exercise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component',type=Path,required=True)
    p.add_argument('--medium',type=Path,required=True,help='Exact independently acknowledged Saved11 opaque bytes for Action-only Engine scan')
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=420)
    a=p.parse_args();out=a.work_dir.resolve();origin=a.component.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build') or not 180<=a.timeout<=600:p.error('unused build path and original180..600s bound required')
    out.mkdir(parents=True);start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30))
    r={'schema':'lemma-usb-recovery-artifact-qualification/1','status':'FAIL','scope':__doc__,'bounds':{'seconds':a.timeout,'virtual_memory_bytes':16<<30},'commands':[],'roles':{}}
    extra=('scripts/check_usb_recovery_target.py','tests/kernel/usb_recovery_mutations.py','tests/usb/BlockRecovery.lean','tests/store/ServerRecovery.lean','tests/store/RecoveryCompile.lean','tests/ink/NotebookRecoverable.lean','tests/ink/NotebookRecoverableCompile.lean')
    def inventory():return {**source_inputs(ROOT),**{n:sha256(ROOT/n) for n in extra}}
    def run(label,argv,cwd=ROOT):
        remaining=a.timeout-(time.monotonic()-start)
        if remaining<=0:raise Core0Error('original Recovery qualification deadline exhausted')
        q=run_bounded(argv,cwd=cwd,env={**os.environ,'LEAN_NUM_THREADS':'2'},timeout_seconds=remaining)
        (out/(label+'.log')).write_bytes(q.stdout+q.stderr);r['commands'].append({'label':label,'argv':list(q.argv),'returncode':q.returncode,'seconds':q.elapsed_seconds})
        if q.returncode:raise Core0Error('actual Recovery qualification command failed: '+label)
        return q.stdout.decode()
    try:
        before=inventory();r['source_inputs']=before;r['medium']={'path':str(a.medium.resolve()),'sha256':sha256(a.medium)}
        capture=json.loads((origin/'result.json').read_text())
        if capture.get('schema')!='lemma-usb-recovery-genuine-component/1' or capture.get('status')!='PASS_GENUINE_COMPONENT_EXPORT_OBJECT_ONLY' or capture.get('source_inputs_equal') is not True or set(capture.get('roles',{}))!={'kernel','kernel-init','store','notebook'}:raise Core0Error('missing exact genuine four-role original capture')
        original=capture['source_inputs'];current=source_inputs(ROOT)
        authorities={'scripts/usb_recovery_target.py','tooling/usb-recovery-target-authority.json'}
        additions=set(current)-set(original)
        changes={n for n in original if n in current and original[n]!=current[n]}
        # The page-word observer qualifies the already captured algorithm;
        # complete target bodies and original inputs still cannot change.
        if additions not in (authorities,authorities|{'scripts/usercopy_page_words.py'}) or set(original)-set(current) or not changes<={'scripts/audit_kernel.py','scripts/build_kernel.py','scripts/paper_clocked.py','scripts/arithmetic_sums_identity.py'}:raise Core0Error('reused target/compiler/profile/source inventory changed')
        if 'scripts/arithmetic_sums_identity.py' in changes:
            # Genuine Arithmetic3 emission was unchanged; one closed registry
            # omitted only the exact new software pair. No other source, pin,
            # caller or prior configuration delta is admitted here.
            pair="CONFIGURATIONS |= frozenset(('lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize'))\n"
            actual=(ROOT/'scripts/arithmetic_sums_identity.py').read_text()
            previous=(origin/'consumed-source-root/scripts/arithmetic_sums_identity.py').read_text()
            if actual.count(pair)!=1 or actual.replace(pair,'')!=previous:raise Core0Error('Arithmetic identity observer changed beyond exact Recovery pair registry')
        for n,digest in original.items():
            source=origin/'consumed-source-root'/n
            if source.is_symlink() or not source.is_file() or sha256(source)!=digest:raise Core0Error('original source archive missing/corrupt: '+n)
        actual_paths={str(q.relative_to(origin/'consumed-source-root')) for q in (origin/'consumed-source-root').rglob('*') if q.is_file()}
        if actual_paths!=set(original):raise Core0Error('original complete source archive inventory differs')
        r['origin']={'path':str(origin),'receipt_sha256':sha256(origin/'result.json'),'original_source_inputs':original,'observer_only_changes':sorted(changes),'new_complete_authorities':sorted(additions)}
        for n,digest in before.items():
            target=out/'consumed-source-root'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target)
            if sha256(target)!=digest:raise Core0Error('qualification source changed during capture')
        tools={n:v['path'] for n,v in capture['tools'].items()}
        for n,v in capture['tools'].items():
            if not v['path'].startswith('/nix/store/') or sha256(Path(v['path']))!=v['sha256']:raise Core0Error('original pinned tool differs: '+n)
        tools['llvm-mc']=str(Path(tools['llc']).with_name('llvm-mc'));r['tools']={n:{'path':v,'sha256':sha256(Path(v))} for n,v in tools.items()}
        run('mc-version',[tools['llvm-mc'],'--version'])
        for role,row in capture['roles'].items():
            source=Path(row['path']);d=out/role;d.mkdir()
            for name,digest in row['artifacts'].items():
                if source.is_symlink() or (source/name).is_symlink() or sha256(source/name)!=digest:raise Core0Error('actual original artifact changed: '+role+'/'+name)
                shutil.copyfile(source/name,d/name)
            unit=json.loads((d/'unit.json').read_text());validate_unit(unit,unit['role'],configuration=unit['configuration'],image_key=unit.get('image_key'))
            pre=(d/'program.ll').read_text();post=(d/'program.opt.ll').read_text()
            audits={phase:validate_ir(text,unit,optimized=phase=='post',optimization='O2') for phase,text in [('pre',pre),('post',post)]}
            rejected=exercise(pre,post,unit)
            undefined=run(role+'-undefined',[tools['llvm-nm'],'--undefined-only','program.o'],d)
            if {line.split()[-1] for line in undefined.splitlines() if line.strip()}!=set(row['expected_external_boundaries']):raise Core0Error('RV64 object external runtime changed')
            def inspect(tool,args,label):return run(role+'-'+label,[tools[tool],*(['--elf-output-style=GNU'] if tool=='llvm-readelf' else []),*args],d)
            sections=inspect('llvm-readelf',['-S','--wide','program.o'],'sections');symbols=inspect('llvm-readelf',['-s','--wide','program.o'],'symbols');relocs=inspect('llvm-readelf',['-r','program.o'],'relocations');raws={}
            for section in ('.rodata','.rodata.cst32'):
                if section in alloc_section_names(sections):
                    name=section[1:]+'.bin';inspect('llvm-objcopy',['-O','binary','--only-section='+section,'program.o',name],name);raws[section]=(d/name).read_bytes()
            readonly=validate_object(sections,symbols,relocs,raws,audits['post']['readonly_optimizer_tables'],'program.o')
            backend=inspect_backend_jump_tables(inspect,d,object_file='program.o',section_text=sections,symbol_text=symbols,relocation_text=relocs,unit=unit,optimization='O2',readonly_tables=readonly['readonly_tables'])
            if unit['role']=='kernel':rejected+=backend_exercise((d/'program-audit-companion.s').read_text(),backend,unit)
            # Corrupt actual readonly bytes, independent of the full LLVM pins.
            for section,data in raws.items():
                literal=next((row for row in readonly['readonly_tables'] if row['section']==section),None)
                if literal is None:continue
                offset=literal['offset'];altered={**raws,section:data[:offset]+bytes([data[offset]^1])+data[offset+1:]}
                try:validate_object(sections,symbols,relocs,altered,audits['post']['readonly_optimizer_tables'],'program.o')
                except Core0Error as error:rejected.append({'mutation':'actual-object-readonly-byte-'+section,'status':'REJECTED','reason':str(error)})
                else:raise Core0Error('corrupt actual readonly object bytes admitted')
            # Real backend-table zero bytes must be covered even in the scalar
            # Store object, which has no LLVM literal pool.
            if backend['jump_tables']:
                data=raws['.rodata'];offset=backend['jump_tables'][0]['offset'];altered=data[:offset]+bytes([data[offset]^1])+data[offset+1:]
                try:validate_backend_jump_tables(sections,symbols,relocs,altered,unit=unit,optimized_ir=post,optimization='O2',readonly_tables=readonly['readonly_tables'],assembly=(d/'program-audit-companion.s').read_text(),companion_symbols=(out/(role+'-program-jump-companion-symbols.log')).read_text(),companion_relocations=(out/(role+'-program-jump-companion-relocations.log')).read_text(),text=(d/'program-audit-text.bin').read_bytes(),companion_text=(d/'program-audit-companion-text.bin').read_bytes())
                except Core0Error as error:rejected.append({'mutation':'actual-backend-table-byte','status':'REJECTED','reason':str(error)})
                else:raise Core0Error('corrupt actual backend table bytes admitted')
            r['roles'][role]={'configuration':unit['configuration'],'function_count':len(unit['functions']),'pre':audits['pre']['usb_recovery_v1'],'post':audits['post']['usb_recovery_v1'],'readonly_objects':readonly,'backend_objects':backend,'mutations':rejected,'artifacts':row['artifacts']}
            print(role,'PASS',len(rejected),'actual mutants rejected',flush=True)
        for label,test,marker,args in [('driver','tests/usb/BlockRecovery.lean','USB_RECOVERY_COMPILE:PASS',[]),('server','tests/store/ServerRecovery.lean','STORE_RECOVERY_ACTION:PASS',[str(a.medium.resolve())]),('notebook','tests/ink/NotebookRecoverable.lean','NOTEBOOK_RECOVERABLE_ACTION:PASS',[])]:
            log=run(label+'-actual-action',['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean','--run',test,*args])
            if log.count(marker)!=1:raise Core0Error('actual Action fixture not complete: '+label)
        if inventory()!=before or sha256(a.medium)!=r['medium']['sha256']:raise Core0Error('actual consumed source/medium changed during qualification')
        r.update(status='PASS_COMPLETE_RECOVERY_ARTIFACT_AND_ACTION_QUALIFICATION',source_inputs_equal=True,connected_rv64_recovery='NOT_RUN',whole_linked_images='NOT_RUN')
    except BaseException as e:r['error']=repr(e)
    finally:
        r['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ('status','error','host_seconds') if k in r}),flush=True)
    return 0 if r['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
