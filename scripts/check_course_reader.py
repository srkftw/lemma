#!/usr/bin/env python3
"""Qualify genuine cooperative Store reading and exact course-selection provenance.

This is a component check. It neither installs media nor starts a notebook or
panel controller. Original inputs, real command logs and failures are retained.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import time

from core0_common import Core0Error, require_tools, run_bounded, sha256, write_json
from course_package import decode


def source_inputs(root: Path) -> dict[str, str]:
    files = {'flake.nix', 'flake.lock', 'lean-toolchain', 'lakefile.toml',
             'lake-manifest.json', 'scripts/check_course_reader.py', 'scripts/core0_common.py', 'scripts/course_package.py'}
    pending = ['Lemma/Compiler/CourseReaderExport.lean', 'tests/courses/Reader.lean',
               'tests/courses/ReaderExport.lean']
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
                        raise Core0Error('unsupported import syntax: ' + line)
                    pending.append(module.replace('.', '/') + '.lean')
                elif not any(module == p or module.startswith(p + '.') for p in ('Lean', 'Init', 'Std')):
                    raise Core0Error('unaccounted upstream module: ' + module)
    if len(files) < 20:
        raise Core0Error('unexpectedly empty compiler/source closure')
    return {name: sha256(root / name) for name in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--retained-dir', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    if out.exists() or not out.is_relative_to(root / 'build/courses'):
        parser.error('unused build/courses directory required')
    out.mkdir(parents=True)
    started = time.monotonic()
    commands = []
    package = args.package.resolve()
    os.environ['LEAN_NUM_THREADS'] = '2'
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    report = {'status': 'FAIL',
              'scope': 'actual guest Actions and genuine User2 LLVM/RV64 object; notebook/controller execution NOT_RUN',
              'bounds': {'whole_seconds': 600, 'command_seconds': 180,
                         'address_space_bytes': 16 << 30, 'generated_file_bytes': 1 << 30},
              'host_environment': {'LEAN_NUM_THREADS': '2'}}

    def run(label, argv, env=None):
        remaining = 600 - (time.monotonic() - started)
        if remaining <= 0:
            raise Core0Error('course reader original aggregate deadline exceeded')
        result = run_bounded(argv, cwd=root, env=env, timeout_seconds=min(180, remaining))
        (out / (label + '.stdout.log')).write_bytes(result.stdout)
        (out / (label + '.stderr.log')).write_bytes(result.stderr)
        commands.append({'label': label, 'argv': list(argv), 'returncode': result.returncode,
                         'wall_seconds': result.elapsed_seconds})
        if result.returncode:
            raise Core0Error(label + ' failed; original logs retained')
        return result.stdout

    try:
        tools = require_tools(('lean', 'lake', 'opt', 'llc', 'llvm-nm', 'llvm-readelf'))
        versions = {name: run('version-' + name, [tool, '--version']).decode().strip()
                    for name, tool in tools.items()}
        if '4.34.1' not in versions['lean'] or '20.1.8' not in versions['opt'] or '20.1.8' not in versions['llc']:
            raise Core0Error('unpinned Lean/LLVM tools')
        report.update(tools=tools, versions=versions)
        with (root / 'build/task006-lake.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            before = source_inputs(root)
            archive = out / 'consumed-source-root'
            if args.retained_dir is not None:
                retained = args.retained_dir.resolve()
                if not retained.is_relative_to(root / 'build/courses') or retained == out:
                    raise Core0Error('retained course component directory required')
                old = json.loads((retained / 'result.json').read_text())
                original = json.loads((retained / 'consumed-source-root/source-inputs.json').read_text())
                if old.get('status') != 'FAIL' or old.get('error') != "Core0Error('empty/foreign reader effect closure')" or old.get('source_inputs') != original:
                    raise Core0Error('retained result is not the exact original effect-observer failure')
                if set(original) != set(before) or {name for name in original if original[name] != before[name]} != {'scripts/check_course_reader.py'}:
                    raise Core0Error('retained component differs beyond the one corrected host observer')
                for name, digest in original.items():
                    if sha256(retained / 'consumed-source-root' / name) != digest:
                        raise Core0Error('corrupt original consumed source: ' + name)
                component = retained / 'component'
                if [x['label'] for x in old.get('commands', [])][-3:] != ['build','actions','export'] or any(x['returncode'] for x in old['commands']):
                    raise Core0Error('retained source/Actions/export did not actually pass')
                if sha256(package) != old.get('reference_package', {}).get('sha256'):
                    raise Core0Error('retained package input mismatch')
                shutil.copytree(retained / 'consumed-source-root', archive)
                shutil.copytree(component, out / 'component')
                report.update(source_count=len(original), source_inputs=original,
                    source_inventory_sha256=sha256(archive / 'source-inputs.json'),
                    reference_package=old['reference_package'],
                    original_capture={'path':str(retained),'result_sha256':sha256(retained / 'result.json'),
                        'status':'FAIL','scope':'original source/export/Action identity retained; no recompilation'},
                    corrected_observer={'path':'scripts/check_course_reader.py','sha256':before['scripts/check_course_reader.py']})
            else:
                capture(root, out, archive, before, report, run, tools, package)
            if source_inputs(root) != before:
                raise Core0Error('actual source closure changed during export/observation')
        component = out / 'component'
        unit = json.loads((component / 'unit.json').read_text())
        roots = ['Lemma.Courses.PackageReader.start','Lemma.Courses.PackageReader.step',
                 'Lemma.Courses.PackageReader.finish','Lemma.Courses.PackageReader.cancel',
                 'Lemma.Courses.PackageBinding.capture','Lemma.Courses.PackageBinding.validate',
                 'Lemma.Courses.PackageBinding.applicable']
        if unit.get('contract_version') != 'core0-user-v0.2' or [row['source'] for row in unit.get('roots', [])] != roots:
            raise Core0Error('profile/root closure mismatch')
        if unit.get('used_device_ops') or {row['stable_id'] for row in unit.get('used_execution_ops', [])} != {
            'execution.virtual-read8', 'execution.virtual-read64',
            'execution.virtual-write8', 'execution.virtual-write64','execution.syscall'}:
            raise Core0Error('reader acquired device authority or lost declared checked operations')
        functions = unit.get('functions', [])
        # These three additional effects are the existing declared syscall
        # semantics, not new target operations or permission/role grants.
        if len(functions) < 20 or any(set(row['effects']) - {'checked-access', 'virtual-read', 'virtual-write',
                'user-syscall', 'io-order', 'privilege-transition'} for row in functions):
            raise Core0Error('empty/foreign reader effect closure')
        run('opt', [tools['opt'], '-S', '-passes=default<O2>', '-verify-each',
                    str(component / 'program.ll'), '-o', str(component / 'program.opt.ll')])
        run('rv64-object', [tools['llc'], '-mtriple=riscv64-unknown-none-elf', '-mattr=+m,-a,-f,-d,-c',
                            '-relocation-model=static', '-filetype=obj', str(component / 'program.opt.ll'),
                            '-o', str(component / 'program.o')])
        undefined = run('undefined', [tools['llvm-nm'], '--undefined-only', str(component / 'program.o')])
        if undefined.decode().split() != ['U','lemma_exec_syscall']:
            raise Core0Error('reader linked undeclared runtime/helpers')
        attributes = run('elf', [tools['llvm-readelf'], '-h', '-A', '-r', str(component / 'program.o')]).decode()
        elf = (component / 'program.o').read_bytes()
        if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', elf, 16) != (1, 243) or struct.unpack_from('<I', elf, 48)[0] != 0:
            raise Core0Error('reader object is not freestanding RV64')
        if 'rv64i2p1_m2p0' not in attributes or re.search(r'\bR_RISCV_(?:RVC|TLS)', attributes):
            raise Core0Error('reader admitted undeclared ISA/relocations')
        if unit.get('reader_contract') != 'lemma-course-reader/1' or unit.get('selection_binding_contract') != 'lemma-course-selection-binding/1' or unit.get('maximum_requests') != 256 or unit.get('maximum_chunk_bytes') != 128 or unit.get('context_bytes') != 128 or unit.get('maximum_call_ticks') != 300000000:
            raise Core0Error('reader/binding version or resource mismatch')
        report.update(status='PASS_GENUINE_COURSE_READER_BINDING_COMPONENT', function_count=len(functions),
                      roots=roots, unresolved_boundary=['lemma_exec_syscall'], artifacts={name: sha256(component / name) for name in
                        ('unit.json', 'program.ll', 'program.opt.ll', 'program.o', 'normalized.txt')})
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report.update(commands=commands, wall_seconds=time.monotonic() - started,
                      child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        write_json(out / 'result.json', report)
    print(report['status'], report['source_count'], report['wall_seconds'])


def capture(root, out, archive, before, report, run, tools, package):
            for name, digest in before.items():
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / name, target)
                if sha256(target) != digest:
                    raise Core0Error('source changed during archive: ' + name)
            write_json(archive / 'source-inputs.json', before)
            report.update(source_count=len(before), source_inputs=before,
                          source_inventory_sha256=sha256(archive / 'source-inputs.json'))
            run('build', [tools['lake'], 'build', 'Lemma.Compiler.CourseReaderExport'])
            if not package.is_file():
                raise Core0Error('real Lean-published reference package required')
            observed = decode(package.read_bytes())
            if observed['identity'] != 1 or observed['edition'] != 1 or [(x['identity'], x['kind'], x['goal']) for x in observed['nodes']] != [
                    (1,1,0),(2,2,0),(3,3,1),(4,1,0),(5,2,0),(6,3,2),(7,3,3),(8,4,0)]:
                raise Core0Error('fixture requires the original pinned-goal reference sequence')
            copied_package = out / 'reference.lcp'
            shutil.copyfile(package, copied_package)
            report.update(reference_package={'original':str(package),'sha256':sha256(copied_package),
                'independent_crc32':observed['crc32'],'bytes':observed['bytes']})
            run('actions', [tools['lake'], 'env', 'lean', '-j2', '--run', 'tests/courses/Reader.lean'],
                dict(os.environ, LEMMA_COURSE_PACKAGE_FILE=str(copied_package)))
            run('export', [tools['lake'], 'env', 'lean', '-j2', 'tests/courses/ReaderExport.lean'],
                dict(os.environ, LEMMA_COURSE_READER_OUT=str(out / 'component')))


if __name__ == '__main__':
    main()
