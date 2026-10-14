#!/usr/bin/env python3
"""Qualify the genuine owned Doc8/package workspace component.

Actual imported guest Actions and checked LLVM/RV64 are separate from a running
Notebook, a checker reply, a Store durability acknowledgement or cold recovery.
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

ROOTS = ['Lemma.Courses.PackageWorkspace.' + name for name in (
    'create', 'validate', 'snapshotSelection', 'captureSelection', 'stageRefresh',
    'stageCompleted', 'stageUnknownSelection', 'stageCompletedUnknown')]


def source_inputs(root: Path) -> dict[str, str]:
    files = {'flake.nix', 'flake.lock', 'lean-toolchain', 'lakefile.toml',
             'lake-manifest.json', 'scripts/check_course_workspace.py',
             'scripts/core0_common.py', 'scripts/course_package.py'}
    pending = ['Lemma/Compiler/CourseWorkspaceExport.lean',
               'tests/courses/Workspace.lean', 'tests/courses/WorkspaceExport.lean']
    while pending:
        name = pending.pop()
        if name in files:
            continue
        path = root / name
        if not path.is_file():
            raise Core0Error('missing transitive project input: ' + name)
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
        raise Core0Error('unexpectedly empty source/compiler closure')
    return {name: sha256(root / name) for name in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    package = args.package.resolve()
    if out.exists() or not out.is_relative_to(root / 'build/courses'):
        parser.error('unused build/courses directory required')
    out.mkdir(parents=True)
    started = time.monotonic()
    commands = []
    os.environ['LEAN_NUM_THREADS'] = '2'
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    report = {'status': 'FAIL', 'scope': 'imported guest Actions and genuine User2 LLVM/RV64 component; Notebook/checker/Store CPU execution and durability NOT_RUN',
              'bounds': {'whole_seconds': 420, 'command_seconds': 180,
                         'address_space_bytes': 16 << 30, 'generated_file_bytes': 1 << 30},
              'host_environment': {'LEAN_NUM_THREADS': '2'}}

    def run(label, argv, env=None):
        remaining = 420 - (time.monotonic() - started)
        if remaining <= 0:
            raise Core0Error('workspace original aggregate deadline exceeded')
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
        report['tools'] = tools
        versions = {name: run('version-' + name, [tool, '--version']).decode().strip()
                    for name, tool in tools.items()}
        report['versions'] = versions
        if '4.34.1' not in versions['lean'] or any('20.1.8' not in versions[t] for t in ('opt', 'llc')):
            raise Core0Error('unpinned Lean/LLVM tools')
        with (root / 'build/task006-lake.lock').open('a+b') as lock:
            # Include time waiting for the shared build lock in the same bound.
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - started >= 420:
                        raise Core0Error('workspace shared lock aggregate deadline exceeded')
                    time.sleep(0.1)
            before = source_inputs(root)
            archive = out / 'consumed-source-root'
            for name, digest in before.items():
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / name, target)
                if sha256(target) != digest:
                    raise Core0Error('source changed while archiving: ' + name)
            write_json(archive / 'source-inputs.json', before)
            report.update(source_count=len(before), source_inputs=before,
                          source_inventory_sha256=sha256(archive / 'source-inputs.json'))
            if not package.is_file():
                raise Core0Error('actual published reference package required')
            observed = decode(package.read_bytes())
            if observed['identity'] != 1 or observed['edition'] != 1 or [(n['identity'], n['kind'], n['goal']) for n in observed['nodes']] != [
                    (1, 1, 0), (2, 2, 0), (3, 3, 1), (4, 1, 0), (5, 2, 0), (6, 3, 2), (7, 3, 3), (8, 4, 0)]:
                raise Core0Error('reference package pinned goal sequence differs')
            copied = out / 'reference.lcp'
            shutil.copyfile(package, copied)
            report['reference_package'] = {'original': str(package), 'sha256': sha256(copied),
                                           'independent_crc32': observed['crc32'], 'bytes': observed['bytes']}
            run('build', [tools['lake'], 'build', 'Lemma.Compiler.CourseWorkspaceExport'])
            run('actions', [tools['lake'], 'env', 'lean', '-j2', '--run', 'tests/courses/Workspace.lean'],
                dict(os.environ, LEMMA_COURSE_PACKAGE_FILE=str(copied)))
            run('export', [tools['lake'], 'env', 'lean', '-j2', 'tests/courses/WorkspaceExport.lean'],
                dict(os.environ, LEMMA_COURSE_WORKSPACE_OUT=str(out / 'component')))
            if source_inputs(root) != before:
                raise Core0Error('consumed source changed during actual build/Actions/export')
        component = out / 'component'
        unit = json.loads((component / 'unit.json').read_text())
        if unit.get('contract_version') != 'core0-user-v0.2' or [r['source'] for r in unit.get('roots', [])] != ROOTS:
            raise Core0Error('workspace root/profile closure differs')
        if unit.get('used_device_ops') or {r['stable_id'] for r in unit.get('used_execution_ops', [])} != {
                'execution.virtual-read8', 'execution.virtual-read64', 'execution.virtual-write64'}:
            raise Core0Error('workspace acquired foreign effects/boundary')
        functions = unit.get('functions', [])
        if len(functions) < 20 or any(set(f['effects']) - {'checked-access', 'virtual-read', 'virtual-write'} for f in functions):
            raise Core0Error('empty/foreign checked effect closure')
        expected = {'workspace_contract': 'lemma-course-workspace/1', 'document_version': 8,
                    'context_bytes': 3712, 'inner_document_offset': 64, 'selection_offset': 2560,
                    'attempts_offset': 2688, 'binding_bytes': 128, 'maximum_attempts': 8,
                    'selection_binding_contract': 'lemma-course-selection-binding/1'}
        if any(unit.get(k) != v for k, v in expected.items()):
            raise Core0Error('workspace layout/version/resource contract differs')
        run('opt', [tools['opt'], '-S', '-passes=default<O2>', '-verify-each',
                    str(component / 'program.ll'), '-o', str(component / 'program.opt.ll')])
        run('rv64-object', [tools['llc'], '-mtriple=riscv64-unknown-none-elf', '-mattr=+m,-a,-f,-d,-c',
                           '-relocation-model=static', '-filetype=obj', str(component / 'program.opt.ll'),
                           '-o', str(component / 'program.o')])
        if run('undefined', [tools['llvm-nm'], '--undefined-only', str(component / 'program.o')]).split():
            raise Core0Error('workspace linked undeclared runtime/helpers')
        attributes = run('elf', [tools['llvm-readelf'], '-h', '-A', '-r', str(component / 'program.o')]).decode()
        elf = (component / 'program.o').read_bytes()
        if elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', elf, 16) != (1, 243) or struct.unpack_from('<I', elf, 48)[0] != 0:
            raise Core0Error('workspace object is not freestanding RV64')
        if 'rv64i2p1_m2p0' not in attributes or re.search(r'\bR_RISCV_(?:RVC|TLS)', attributes):
            raise Core0Error('workspace admitted undeclared ISA/relocations')
        if source_inputs(root) != before:
            raise Core0Error('consumed source changed during object observation')
        report.update(status='PASS_GENUINE_COURSE_WORKSPACE_COMPONENT', function_count=len(functions),
                      roots=ROOTS, unresolved_boundary=[], authoritative_source_unchanged=True,
                      artifacts={n: sha256(component / n) for n in
                                 ('unit.json', 'program.ll', 'program.opt.ll', 'program.o', 'normalized.txt')})
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report.update(commands=commands, wall_seconds=time.monotonic() - started,
                      child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        write_json(out / 'result.json', report)
    print(report['status'], report['source_count'], report['wall_seconds'])


if __name__ == '__main__':
    main()
