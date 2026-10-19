#!/usr/bin/env python3
"""Operator-local authoring/build orchestration; all domain validation is Lean.

Invoked inside the pinned environment by ./scripts/lemma-school develop.
It never implements publication policy, source rights, checker or model math.
"""
from __future__ import annotations
import argparse
import hashlib
import json
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


def invoke(command, records, timeout=180):
    result=run_bounded([str(x) for x in command],cwd=ROOT,timeout_seconds=timeout)
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
    for name in ['train','evaluate']:
        item=sub.add_parser(name,help='run the real bounded Lean numerical training/evaluation implementation')
        item.add_argument('--dataset',type=Path,required=True);item.add_argument('--checkpoint',type=Path,required=True)
        item.add_argument('--output-dir',type=Path,required=True);item.add_argument('--configuration',type=Path)
        item.add_argument('--timeout',type=float,default=180)
        if name=='train':item.add_argument('--steps',type=int,required=True)
    args=parser.parse_args()
    try:
        if args.command=='build':author_build(args)
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
