#!/usr/bin/env python3
"""Bounded, source-bound five-role Closure recovery artifact and Action qualification.

This inspects a genuine original capture and its complete archived sources.
Only the new separately derived complete authority may be added. It never rewrites
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
from usb_closure_recovery_mutations import exercise,backend_exercise

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--component',type=Path,required=True)
    p.add_argument('--medium',type=Path,required=True,help='Exact independently acknowledged Saved11 opaque bytes for Action-only Engine scan')
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=420)
    a=p.parse_args();out=a.work_dir.resolve();origin=a.component.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'build') or not 180<=a.timeout<=600:p.error('unused build path and original180..600s bound required')
    out.mkdir(parents=True);start=time.monotonic();resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30))
    r={'schema':'lemma-usb-closure-recovery-artifact-qualification/1','status':'FAIL','scope':__doc__,'bounds':{'seconds':a.timeout,'virtual_memory_bytes':16<<30},'commands':[],'roles':{}}
    extra=('scripts/check_usb_closure_recovery_target.py','tests/kernel/usb_closure_recovery_mutations.py','tests/usb/BlockRecovery.lean','tests/store/ServerRecovery.lean','tests/store/RecoveryCompile.lean','tests/ink/NotebookClosureRecoverable.lean','tests/ink/NotebookRetryClosurePolicy.lean')
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
        if capture.get('schema')!='lemma-usb-closure-recovery-genuine-component-cohort/1' or capture.get('status')!='PASS_GENUINE_COMPONENT_COHORT_MISSING_ROLES_ONLY' or capture.get('source_inputs_equal') is not True or set(capture.get('roles',{}))!={'kernel','kernel-init','store','notebook','arithmetic'}:raise Core0Error('missing exact genuine five-role composed cohort')
        reuse=capture.get('reused_completed_roles',{});prior_path=Path(reuse.get('origin',''))
        if reuse.get('roles')!=['kernel','kernel-init'] or reuse.get('original_status')!='FAIL' or not prior_path.is_relative_to(ROOT/'build') or sha256(prior_path/'result.json')!=reuse.get('original_result_sha256'):raise Core0Error('original retained partial capture identity absent')
        prior=json.loads((prior_path/'result.json').read_text())
        if prior.get('schema')!='lemma-usb-closure-recovery-genuine-component/1' or prior.get('status')!='FAIL' or set(prior.get('roles',{}))!={'kernel','kernel-init'} or prior['source_inputs']!=capture['source_inputs'] or prior['tools']!=reuse['original_tools']:raise Core0Error('composed cohort original source/tool/result mismatch')
        for role in reuse['roles']:
            if prior['roles'][role]['artifacts']!=capture['roles'][role]['artifacts'] or capture['roles'][role].get('freshly_exported_in_this_suffix') is not False:raise Core0Error('composed original role hashes/scope differ')
            for name,digest in prior['roles'][role]['artifacts'].items():
                if sha256(Path(prior['roles'][role]['path'])/name)!=digest:raise Core0Error('original retained completed artifact changed')

        original=capture['source_inputs'];current=source_inputs(ROOT)
        authorities={'tooling/usb-closure-recovery-target-authority.json'}
        additions=set(current)-set(original)
        changes={n for n in original if n in current and original[n]!=current[n]}
        # This exact command/CWD observer correction was independently qualified
        # after the producer376 capture. It is not a target/compiler replacement.
        # No other broad inventory change or future helper hash is admitted.
        observer_delta={'scripts/audit_kernel.py':(
            '7b4c9b7a5563f2c20007aa4abf002d5d1d888284db48d2c0123a8814864339f3',
            '80eebc15bfa59f12c5fdd79063826202fd60b37ffb0091bd045583aae20babf5')}
        if (additions!=authorities or set(original)-set(current) or
                not changes<=set(observer_delta) or
                any((original[name],current[name])!=observer_delta[name] for name in changes)):
            raise Core0Error('genuine Closure recovery capture source/compiler/profile/helper inventory changed')
        r['explicit_qualified_observer_delta']={name:{'before_sha256':original[name],'after_sha256':current[name],
            'scope':'Only validate_multi_commands and audit callsite: strict complete archived source workspace/Nix/Lake/CWD validation; target bytes unchanged'} for name in changes}

        authority=json.loads((ROOT/'tooling/usb-closure-recovery-target-authority.json').read_text())
        if authority.get('origin_sha256')!=sha256(origin/'result.json'):raise Core0Error('new complete authority is not derived from this exact genuine capture')
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
            rejected=exercise(pre,post,unit) if role!='arithmetic' else []
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
            r['roles'][role]={'configuration':unit['configuration'],'function_count':len(unit['functions']),'pre':audits['pre'].get('usb_closure_recovery_v1'),'post':audits['post'].get('usb_closure_recovery_v1'),'arithmetic_identity':audits['pre'].get('arithmetic_closure_execution_identity'),'readonly_objects':readonly,'backend_objects':backend,'mutations':rejected,'artifacts':row['artifacts']}
            print(role,'PASS',len(rejected),'actual mutants rejected',flush=True)
        for label,test,marker,args in [('driver','tests/usb/BlockRecovery.lean','USB_RECOVERY_COMPILE:PASS',[]),('server','tests/store/ServerRecovery.lean','STORE_RECOVERY_ACTION:PASS',[str(a.medium.resolve())]),('notebook','tests/ink/NotebookClosureRecoverable.lean','CLOSURE_RECOVERY_ACTION:PASS',[]),('policy','tests/ink/NotebookRetryClosurePolicy.lean','Closure retry shape policy:',[])]:
            log=run(label+'-actual-action',['flock',str(ROOT/'build/task006-lake.lock'),tools['lake'],'env','lean','--run',test,*args])
            if log.count(marker)!=1:raise Core0Error('actual Action fixture not complete: '+label)
        if inventory()!=before or sha256(a.medium)!=r['medium']['sha256']:raise Core0Error('actual consumed source/medium changed during qualification')
        r.update(status='PASS_COMPLETE_CLOSURE_RECOVERY_ARTIFACT_AND_ACTION_QUALIFICATION',source_inputs_equal=True,connected_rv64_recovery='NOT_RUN',whole_linked_images='NOT_RUN')
    except BaseException as e:r['error']=repr(e)
    finally:
        r['host_seconds']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k] for k in ('status','error','host_seconds') if k in r}),flush=True)
    return 0 if r['status'].startswith('PASS') else 1
if __name__=='__main__':raise SystemExit(main())
