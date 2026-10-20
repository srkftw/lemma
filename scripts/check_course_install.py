#!/usr/bin/env python3
"""Source-bound genuine course installer/guard component qualification (not CPU)."""
from __future__ import annotations
import argparse, fcntl, json, os, re, resource, shutil, struct, time
from pathlib import Path
from core0_common import Core0Error, require_tools, run_bounded, sha256, write_json
def source_inputs(root: Path) -> dict[str, str]:
    files = {'flake.nix', 'flake.lock', 'lean-toolchain', 'lakefile.toml',
             'lake-manifest.json', 'scripts/build_course_package.py',
             'scripts/course_package.py', 'scripts/core0_common.py',
             'tests/courses/test_package.py'}
    files.update({'scripts/check_course_install.py'})
    pending = ['Lemma/Compiler/CourseInstallExport.lean','tests/courses/InstallExport.lean',
               'tests/courses/GuardExport.lean','tests/courses/Install.lean','tests/courses/Guard.lean',
               'tests/courses/Mount.lean','tests/courses/Selection.lean','tests/courses/SelectionExport.lean','tests/courses/Submission.lean',
               'tests/courses/SubmissionExport.lean','tests/courses/SchoolGuardExport.lean','tests/courses/SchoolGuard.lean',
               'tests/courses/NotebookSchool.lean','tests/courses/RemoteProvenance.lean','tests/courses/LocalReduction.lean']
    while pending:
        name = pending.pop()
        if name in files:
            continue
        path = root / name
        if not path.is_file():
            raise Core0Error('missing transitive project source: ' + name)
        files.add(name)
        for line in path.read_text().splitlines():
            if not line.startswith('import '):
                continue
            for module in line.removeprefix('import ').split():
                if module.startswith('Lemma.'):
                    if not re.fullmatch(r'Lemma(?:\.[A-Za-z0-9_]+)+', module):
                        raise Core0Error('unsupported project import syntax: ' + line)
                    pending.append(module.replace('.', '/') + '.lean')
                elif not any(module == prefix or module.startswith(prefix + '.')
                             for prefix in ('Lean', 'Init', 'Std')):
                    raise Core0Error('unaccounted upstream module: ' + module)
    if len(files) < 20:
        raise Core0Error('unexpectedly empty project/compiler source closure')
    return {name: sha256(root / name) for name in sorted(files)}


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--selection',action='store_true',help='also qualify the additive selected-publication v2 root and faults')
    p.add_argument('--school-submission',action='store_true',help='also qualify notebook ordering/ink Actions, the guest outgoing queue and append-only Store successor')
    a=p.parse_args(); a.selection |= a.school_submission; root=Path(__file__).resolve().parents[1]; out=a.output_dir.resolve()
    if not out.is_relative_to(root/'build/courses') or out.exists(): p.error('unused build/courses output required')
    out.mkdir(parents=True); started=time.monotonic(); commands=[]
    os.environ['LEAN_NUM_THREADS']='2'
    result=dict(status='FAIL',scope='actual Lean Actions and genuinely elaborated LLVM/RV64 objects; CPU/durable medium NOT_RUN',
                host_environment={'LEAN_NUM_THREADS':'2'},
                bounds=dict(command_seconds=300,whole_seconds=900,address_space_bytes=16<<30,file_bytes=1<<30))
    resource.setrlimit(resource.RLIMIT_AS,(16<<30,16<<30)); resource.setrlimit(resource.RLIMIT_FSIZE,(1<<30,1<<30))
    def run(label,argv,env=None):
        remaining=900-(time.monotonic()-started)
        if remaining<=0: raise Core0Error('course install deadline exceeded')
        r=run_bounded(argv,cwd=root,env=env,timeout_seconds=min(300,remaining))
        (out/(label+'.stdout.log')).write_bytes(r.stdout); (out/(label+'.stderr.log')).write_bytes(r.stderr)
        commands.append(dict(label=label,argv=argv,returncode=r.returncode,wall_seconds=r.elapsed_seconds))
        if r.returncode: raise Core0Error(label+' failed; original logs retained')
        return r.stdout
    try:
        tools=require_tools(('lean','lake','opt','llc','llvm-nm','llvm-readelf'))
        versions={n:run('version-'+n,[t,'--version']).decode().strip() for n,t in tools.items()}
        if '4.34.1' not in versions['lean'] or '20.1.8' not in versions['opt']: raise Core0Error('unpinned Lean/LLVM')
        result.update(tools=tools,versions=versions)
        with (root/'build/task006-lake.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX); before=source_inputs(root); archive=out/'consumed-source-root'
            for name,digest in before.items():
                target=archive/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(root/name,target)
                if sha256(target)!=digest: raise Core0Error('changed input during archive:'+name)
            write_json(out/'source-inputs.json',before); result.update(source_inputs=before,source_count=len(before))
            run('build',[tools['lake'],'build','Lemma.Compiler.CourseInstallExport'])
            run('guard-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/Guard.lean'])
            run('install-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/Install.lean'])
            run('mount-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/Mount.lean'])
            env=dict(os.environ,LEMMA_COURSE_INSTALL_OUT=str(out/'install'),LEMMA_COURSE_GUARD_OUT=str(out/'guard'))
            run('install-export',[tools['lake'],'env','lean','-j2','tests/courses/InstallExport.lean'],env)
            run('guard-export',[tools['lake'],'env','lean','-j2','tests/courses/GuardExport.lean'],env)
            if a.selection:
                run('selection-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/Selection.lean'])
                run('selection-export',[tools['lake'],'env','lean','-j2','tests/courses/SelectionExport.lean'],
                    dict(env,LEMMA_COURSE_SELECTION_OUT=str(out/'selection')))
            if a.school_submission:
                run('notebook-build',[tools['lake'],'build','Lemma.Applications.Notebook'])
                run('notebook-school-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/NotebookSchool.lean'])
                run('remote-provenance-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/RemoteProvenance.lean'])
                run('local-reduction-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/LocalReduction.lean'])
                run('submission-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/Submission.lean'])
                run('school-guard-actions',[tools['lake'],'env','lean','-j2','--run','tests/courses/SchoolGuard.lean'])
                run('submission-export',[tools['lake'],'env','lean','-j2','tests/courses/SubmissionExport.lean'],
                    dict(env,LEMMA_SCHOOL_SUBMISSION_OUT=str(out/'submission')))
                run('school-guard-export',[tools['lake'],'env','lean','-j2','tests/courses/SchoolGuardExport.lean'],
                    dict(env,LEMMA_SCHOOL_GUARD_OUT=str(out/'school-guard')))
            if source_inputs(root)!=before: raise Core0Error('consumed source changed during capture')
        qualified={}
        roles=[('install',['Lemma.Courses.PackageStore.install','Lemma.Courses.PackageInstaller.main']),
                           ('guard',['Lemma.Services.Store.Server.courseMain'])]
        if a.selection:
            roles.append(('selection',['Lemma.Courses.PackageInstaller.mainAwaitSelected']))
        if a.school_submission:
            roles.extend([('submission',['Lemma.Courses.SchoolSubmission.'+name for name in
                ('initializeQueue','start','pump','restore','retry','cancel','frontier','writerActive','suspend','resume')]),
                ('school-guard',['Lemma.Services.Store.ServerSchool.main'])])
        for role,roots in roles:
            directory=out/role; unit=json.loads((directory/'unit.json').read_text())
            if unit.get('contract_version')!='core0-user-v0.2' or [x['source'] for x in unit.get('roots',[])]!=roots or unit.get('used_device_ops'):
                raise Core0Error('root/profile closure mismatch:'+role)
            ops={x['stable_id'] for x in unit.get('used_execution_ops',[])}
            if ops!={'execution.virtual-read8','execution.virtual-read64','execution.virtual-write8','execution.virtual-write64','execution.syscall'}:
                raise Core0Error('operation closure mismatch:'+role)
            if len(unit.get('functions',[]))<50: raise Core0Error('empty component:'+role)
            run(role+'-opt',[tools['opt'],'-S','-passes=default<O2>','-verify-each',str(directory/'program.ll'),'-o',str(directory/'program.opt.ll')])
            run(role+'-object',[tools['llc'],'-mtriple=riscv64-unknown-none-elf','-mattr=+m,-a,-f,-d,-c','-relocation-model=static','-filetype=obj',str(directory/'program.opt.ll'),'-o',str(directory/'program.o')])
            undefined=run(role+'-undefined',[tools['llvm-nm'],'--undefined-only',str(directory/'program.o')]).decode().split()
            if undefined!=['U','lemma_exec_syscall']: raise Core0Error('foreign runtime/helper boundary:'+role+repr(undefined))
            attrs=run(role+'-elf',[tools['llvm-readelf'],'-h','-A','-r',str(directory/'program.o')]).decode()
            elf=(directory/'program.o').read_bytes()
            if elf[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<HH',elf,16)!=(1,243) or struct.unpack_from('<I',elf,48)[0]!=0 or 'rv64i2p1_m2p0' not in attrs or re.search(r'\bR_RISCV_(?:RVC|TLS)',attrs):
                raise Core0Error('RV64IM object provenance mismatch:'+role)
            qualified[role]=dict(function_count=len(unit['functions']),roots=roots,unresolved_boundary=undefined[1:],
                artifacts={name:sha256(directory/name) for name in ('unit.json','program.ll','program.opt.ll','program.o','normalized.txt')})
        result.update(status='PASS_SCHOOL_SUBMISSION_STORE_COMPONENTS' if a.school_submission else
                      'PASS_COURSE_SELECTION_INSTALL_GUARD_COMPONENTS' if a.selection else 'PASS_COURSE_INSTALL_GUARD_COMPONENTS',components=qualified)
    except BaseException as e:
        result['error']=repr(e); raise
    finally:
        result.update(commands=commands,wall_seconds=time.monotonic()-started,child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        write_json(out/'result.json',result)
    print(result['status'],result['source_count'],result['wall_seconds'])

if __name__=='__main__': main()
