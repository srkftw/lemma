#!/usr/bin/env python3
"""Operator-local authoring/build orchestration; all domain validation is Lean.

Invoked inside the pinned environment by ./scripts/lemma-school develop.
It never implements publication policy, source rights, checker or model math.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import time
import re
from pathlib import Path
import shutil
import subprocess
import sys

from build_actions import lean_source_inputs, retain_source
from action_cache import tool_identity
from core0_common import Core0Error, run_bounded

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(command, records, timeout=180, env=None):
    result=run_bounded([str(x) for x in command],cwd=ROOT,timeout_seconds=timeout,env=env)
    records.append(dict(argv=[str(x) for x in command],returncode=result.returncode,
                        elapsedSeconds=result.elapsed_seconds,
                        stdout=result.stdout.decode(errors='replace'),stderr=result.stderr.decode(errors='replace')))
    if result.stderr: sys.stderr.buffer.write(result.stderr)
    if result.returncode:
        if result.stdout: sys.stderr.buffer.write(result.stdout)
        raise Core0Error(f"command failed ({result.returncode}); preserve the Lean diagnostic above")
    return result.stdout


def under_repo(path):
    path=path.resolve()
    try: path.relative_to(ROOT)
    except ValueError: raise Core0Error('Lean build source must be in this checkout so imported source identity is reviewable')
    if not path.is_file() or path.is_symlink(): raise Core0Error(f'expected regular source file: {path}')
    return path


def author_build(args):
    source,unit=under_repo(args.lean),under_repo(args.unit)
    if args.output_dir.exists(): raise Core0Error('build destination exists; select a new version directory to preserve older editions')
    output=args.output_dir.resolve();output.mkdir(parents=True)
    commands=[]
    inputs=lean_source_inputs(ROOT,[source,ROOT/'Lemma/School/CurriculumMain.lean'])
    # Include literal data reads used by the hosted examples and their imported
    # fixture modules. This is a source inventory, not a cache for hosted IO.
    for path in list(inputs.values()):
        if path.suffix!='.lean': continue
        for literal in re.findall(r'include_str\s+"([^"\n]+)"',path.read_text()):
            included=under_repo(path.parent/literal)
            inputs[str(included.relative_to(ROOT))]=included
    inputs[str(unit.relative_to(ROOT))]=unit
    for name in ['scripts/school_develop.py','scripts/build_actions.py','scripts/core0_common.py']:
        inputs[name]=ROOT/name
    before={name:digest(path) for name,path in inputs.items()}
    report=dict(schema='lemma-school-developer-build/1',result='FAIL',source=str(source.relative_to(ROOT)),
                unit=str(unit.relative_to(ROOT)),sourceInputs=before,commands=commands,
                tools={name:tool_identity(name) for name in ['lean','lake']},
                boundary='hosted Lean elaboration and course package production; actual guest installation/rendering is separate')
    try:
        invoke(['lake','build','school-curriculum'],commands)
        actual=json.loads(invoke(['lake','env','lean','--run',source.relative_to(ROOT)],commands))
        canonical=json.loads(invoke([ROOT/'.lake/build/bin/school-curriculum','preview',unit],commands))
        if actual!=canonical:
            raise Core0Error('Lean example preview differs from the Unit: emit Authoring.preview of the exact published definition')
        package=output/'package.lcp'
        compiled=json.loads(invoke([ROOT/'.lake/build/bin/school-curriculum','compile',unit,package],commands))
        if compiled['sha256']!=canonical['packageSha256'] or digest(package)!=canonical['packageSha256']:
            raise Core0Error('shared Lean preview/package identity differs')
        if before!={name:digest(path) for name,path in inputs.items()}:
            raise Core0Error('consumed source changed during build; retry from a stable candidate')
        retain_source(ROOT,output,before)
        shutil.copyfile(unit,output/'definition.json')
        (output/'preview.json').write_text(json.dumps(canonical,ensure_ascii=False,indent=2)+'\n')
        report.update(result='PASS',packageSha256=canonical['packageSha256'],packageBytes=compiled['bytes'],
                      definitionSha256=digest(output/'definition.json'),
                      course=canonical['definition']['course']['identity'],edition=canonical['definition']['course']['edition'],
                      incremental='Lake reuses unchanged dependency builds; example elaboration and previews execute freshly')
    finally:
        (output/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(result='PASS',build=str(output),course=report['course'],edition=report['edition'],
                          package=str(package),packageSha256=report['packageSha256'])))


def publish(args):
    output=args.build_dir.resolve();receipt=json.loads((output/'build.json').read_text())
    if receipt.get('result')!='PASS' or digest(output/'definition.json')!=receipt['definitionSha256'] or digest(output/'package.lcp')!=receipt['packageSha256']:
        raise Core0Error('developer build is failed or changed; build a fresh version before publication')
    commands=[]
    request=dict(op='publish',school=args.school,actor=args.actor,path=str(output/'definition.json'),policy=args.policy)
    response=json.loads(invoke([sys.executable,ROOT/'scripts/school_transport.py','--binary',args.binary.resolve(),args.root.resolve(),json.dumps(request)],commands))
    if not response.get('ok'): raise Core0Error(str(response))
    admitted=response['result']
    publication=admitted.get('publication',admitted.get('record'))
    if not publication or publication['data']['artifact']!=receipt['packageSha256']:
        raise Core0Error('authority publication differs from built package; no enrollments requested, inspect its immutable record')
    for learner in args.enroll:
        request=dict(op='enroll',school=args.school,actor=args.actor,learner=learner,
                     course=int(receipt['course']),revision=int(receipt['edition']))
        response=json.loads(invoke([sys.executable,ROOT/'scripts/school_transport.py','--binary',args.binary.resolve(),args.root.resolve(),json.dumps(request)],commands))
        if not response.get('ok'): raise Core0Error(str(response))
    print(json.dumps(dict(ok=True,course=receipt['course'],edition=receipt['edition'],packageSha256=receipt['packageSha256'],enrolled=args.enroll,
                          scope='publication/enrollment admitted by the running or offline Lean authority; learner selects this exact edition through catalogue')))


def training(args):
    commands=[]
    source=ROOT/'examples/school/Train.lean'
    mode=('train-config' if args.configuration else 'train') if args.command=='train' else ('evaluate-config' if args.configuration else 'evaluate')
    command=['lake','env','lean','--run',source,mode,args.dataset.resolve(),args.checkpoint.resolve(),args.output_dir.resolve()]
    if args.command=='train': command.append(args.steps)
    if args.configuration: command.append(args.configuration.resolve())
    elif args.command=='train': command.append(0)
    data=invoke(command,commands,timeout=args.timeout)
    sys.stdout.buffer.write(data)



def service_build(args):
    """Build the selected closed service and its real notebook consumer together.

    The existing deployment/exporter remains the capability authority. This
    command cannot add a service, grant, runtime loader or foreign target code.
    """
    from build_kernel import source_inputs
    import school_deployment
    select=getattr(school_deployment,'configuration_for',None)
    if select is None:
        raise Core0Error('this source has no versioned School service deployment authority; select an admitted source edition')
    configurations={role:select(args.notebook_version,name) for role,name in
                    [('notebook','notebook'),('initializer','initialize')]}
    if not math.isfinite(args.timeout) or not 0 < args.timeout <= 7200:
        raise Core0Error('service build requires a finite whole deadline in (0,7200] seconds')
    output=args.output_dir.absolute()
    try:relative=output.relative_to(ROOT/'build/school')
    except ValueError:raise Core0Error('service build output must be a new build/school subdirectory')
    if (not relative.parts or '..' in relative.parts or output.exists() or
            any(path.is_symlink() for path in (output,*output.parents))):
        raise Core0Error('unused non-symlinked service build output required; older builds are never replaced')
    # The current Student sample path admits one source-grounded package.
    # Diagnose that existing capability before any expensive target action;
    # newly authored publications use the protected catalogue/install path.
    from multimodal_native_bundle import SCHOOL_SAMPLE_SHA
    from course_package import decode
    sample=args.sample_course.resolve()
    if not sample.is_file() or sample.stat().st_size!=4199 or digest(sample)!=SCHOOL_SAMPLE_SHA:
        raise Core0Error('this native Student sample binding requires the canonical4199-byte account-free package '
                         f'(SHA256 {SCHOOL_SAMPLE_SHA}); publish newly authored courses with develop publish '
                         'and select their exact edition through the protected school catalogue. No target build started.')
    decode(sample.read_bytes())
    # Keep the caller's outer Nix resource guard. Only the child compiler's Nix
    # identity resolves the exact immutable executable consumed by producers.
    locked=json.loads((ROOT/'tooling/toolchain-lock.json').read_text())
    nix=Path(locked['tools']['host_environment']['nix']['executable'])
    if not nix.is_file() or not str(nix).startswith('/nix/store/') or not os.access(nix,os.X_OK):
        raise Core0Error('locked immutable Nix is unavailable; no service build started')
    child_env=dict(os.environ);child_env['PATH']=str(nix.parent)+os.pathsep+child_env.get('PATH','')
    token=hashlib.sha256(str(output).encode()).hexdigest()[:12]
    builds={role:ROOT/'build/kernel'/('school-sdk-'+token+'-'+role) for role in configurations}
    if any(path.exists() for path in builds.values()):
        raise Core0Error('service build owns existing target output; choose a new output version')
    def preflight():
        available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                       if line.startswith('MemAvailable:'))
        free=shutil.disk_usage(ROOT).free
        if available < 8*1024**3 or free < 8*1024**3:
            raise Core0Error('service build requires8GiB available memory and8GiB free storage before each phase')
        return dict(availableBytes=available,freeBytes=free)
    resources=preflight();output.mkdir(parents=True)
    before=source_inputs(ROOT);source=retain_source(ROOT,output,before);commands=[]
    report=dict(schema='lemma-school-service-build/1',result='FAIL',notebookVersion=args.notebook_version,
                configurations=configurations,sourceInputs=before,sourceRoot=str(source),
                targetBuilds={role:str(path) for role,path in builds.items()},commands=commands,
                scope='genuine closed service/notebook build, audit and local software bundle selection; no runtime code in course packages or authenticated ROM installation claim',
                limits=dict(wholeSeconds=args.timeout,commandSeconds=900,compilerActionSeconds=300,
                            minimumAvailableBytes=8*1024**3,minimumFreeBytes=8*1024**3),
                preflight=resources,entryInputs={name:digest(ROOT/name) for name in
                    ['scripts/school_develop.py','scripts/lemma-school','scripts/school_deployment.py']},
                accountFreeSample=dict(path=str(sample),sha256=SCHOOL_SAMPLE_SHA,bytes=4199,
                                       scope='existing canonical Student sample binding; authored publications are installed through school admission'),
                childNix=str(nix),execution='not executed by building; use the actual ordinary Student native/browser paths')
    began=time.monotonic()
    def phase(argv):
        preflight();left=args.timeout-(time.monotonic()-began)
        if left<=0:raise Core0Error('original service build whole deadline reached')
        if source_inputs(ROOT)!=before:raise Core0Error('consumed target source changed; preserve this failed build and restart from a frozen edition')
        if not sample.is_file() or sample.stat().st_size!=4199 or digest(sample)!=SCHOOL_SAMPLE_SHA:
            raise Core0Error('account-free sample changed after preflight; preserve this failed build and select the original package')
        return invoke(argv,commands,timeout=min(900,left),env=child_env)
    try:
        for role,configuration in configurations.items():
            phase([sys.executable,ROOT/'scripts/build_kernel.py','--configuration',configuration,
                   '--stage','supervisor','--opt-level',args.opt_level,'--output-dir',builds[role],'--timeout','300'])
            phase([sys.executable,ROOT/'scripts/audit_kernel.py',builds[role],'--source-root',source])
            if json.loads((builds[role]/'audit.json').read_text()).get('status')!='PASS':
                raise Core0Error('actual target source/LLVM/object/ISA/capability audit failed; no bundle produced')
        version=['--school-notebook-version',str(args.notebook_version)]
        for role,workload in [('notebook','school-notebook'),('initializer','school-initializer')]:
            phase([sys.executable,ROOT/'scripts/lemmasim','build','--backend','qemu','--profile','lemma-silicon-dev/0.14.0',
                   '--controller-binding','mm2-subset','--workload',workload,'--guest-build',builds[role],
                   '--guest-source-root',source,*version])
        phase([sys.executable,ROOT/'scripts/lemmasim','native-bundle-build','--school-deployment',
               '--controller-binding','mm2-subset','--profile','lemma-silicon-dev/0.14.0',*version,
               '--notebook-build',builds['notebook'],'--initializer-build',builds['initializer'],
               '--guest-source-root',source,'--sample-course',sample,'--output-dir',output/'native'])
        report['native']=dict(path=str(output/'native'),manifestSHA256=digest(output/'native/bundle.json'))
        if args.wasm_build is not None:
            phase([sys.executable,ROOT/'scripts/lemmasim','browser-build','--engine','qemu-tci','--workbook','school',
                   '--profile','lemma-silicon-dev/0.14.0',*version,'--reuse-wasm','--wasm-build',args.wasm_build.resolve(),
                   '--guest-bundle',output/'native','--sample-course',sample,'--output-dir',output/'browser'])
            report['browser']=dict(path=str(output/'browser'),manifestSHA256=digest(output/'browser/bundle.json'))
        if source_inputs(ROOT)!=before:
            raise Core0Error('consumed target source changed before the service build completed; retained artifacts are from the recorded original edition')
        if time.monotonic()-began > args.timeout:
            raise Core0Error('original service build whole deadline reached during final admission')
        report.update(result='PASS',incremental='unchanged admitted actions and runtime objects may be reused; producer receipts retain their original fresh/reused identities')
    finally:
        report['elapsedSeconds']=time.monotonic()-began
        (output/'service-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ['result','notebookVersion','native',*(['browser'] if 'browser' in report else [])]}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build',help='elaborate a Lean Unit example, validate matching JSON, preview and compile its product package')
    build.add_argument('--lean',type=Path,default=Path('examples/school/ConsecutiveSquares.lean'))
    build.add_argument('--unit',type=Path,default=Path('examples/school/consecutive-squares-unit.json'))
    build.add_argument('--output-dir',type=Path,required=True)
    release=sub.add_parser('publish',help='publish a successful immutable developer build and optionally enroll learners')
    release.add_argument('--build-dir',type=Path,required=True);release.add_argument('--root',type=Path,required=True)
    release.add_argument('--binary',type=Path,default=ROOT/'.lake/build/bin/school')
    release.add_argument('--school',required=True);release.add_argument('--actor',required=True)
    release.add_argument('--policy',type=int,required=True);release.add_argument('--enroll',action='append',default=[])
    check=sub.add_parser('check',help='show actual Lean/Core0 capability/schema/lowering diagnostics from a source file')
    check.add_argument('--lean',type=Path,required=True)
    target=sub.add_parser('target-build',help='existing genuine Lean/Core0 RV64 scalar build path; no unrestricted guest plugin claim')
    target.add_argument('--export-source',type=Path,default=Path('examples/core0/Build.lean'))
    target.add_argument('--output-dir',type=Path,required=True);target.add_argument('--opt-level',choices=['O0','O2'],default='O2')
    target.add_argument('--timeout',type=float,default=180)
    service=sub.add_parser('service-build',help='build/audit an admitted closed School service plus its real notebook consumer and select local native/browser software bundles')
    service.add_argument('--notebook-version',type=int,choices=[23,24,25],default=24)
    service.add_argument('--output-dir',type=Path,required=True)
    service.add_argument('--sample-course',type=Path,required=True,
                         help='existing canonical account-free package; publish/install authored courses through school admission')
    service.add_argument('--wasm-build',type=Path,help='optional existing admitted TCI runtime; no Wasm/compiler rebuild')
    service.add_argument('--opt-level',choices=['O0','O2'],default='O2')
    service.add_argument('--timeout',type=float,default=3600,help='original whole build/audit/package deadline, seconds')
    for name in ['train','evaluate']:
        item=sub.add_parser(name,help='run the real bounded Lean numerical training/evaluation implementation')
        item.add_argument('--dataset',type=Path,required=True);item.add_argument('--checkpoint',type=Path,required=True)
        item.add_argument('--output-dir',type=Path,required=True);item.add_argument('--configuration',type=Path)
        item.add_argument('--timeout',type=float,default=180)
        if name=='train':item.add_argument('--steps',type=int,required=True)
    args=parser.parse_args()
    try:
        if args.command=='service-build':service_build(args)
        elif args.command=='build':author_build(args)
        elif args.command=='publish':publish(args)
        elif args.command in {'train','evaluate'}:training(args)
        elif args.command=='check':
            records=[]
            invoke(['lake','build','Lemma.Core0','Lemma.School.Authoring'],records)
            sys.stdout.buffer.write(invoke(['lake','env','lean',under_repo(args.lean).relative_to(ROOT)],records))
        elif args.command=='target-build':
            return subprocess.call([sys.executable,str(ROOT/'scripts/build_core0.py'),'--export-source',str(args.export_source),
                '--output-dir',str(args.output_dir),'--opt-level',args.opt_level,'--timeout',str(args.timeout)],cwd=ROOT)
    except (Core0Error,OSError,ValueError,KeyError) as error:
        print(f'school developer: {error}',file=sys.stderr);return 1
    return 0


if __name__=='__main__':sys.exit(main())
