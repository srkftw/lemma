#!/usr/bin/env python3
"""Publish a typed Lean course and qualify its genuine guest decoder component.

Run inside the pinned Nix environment. This host orchestration does not install
packages into a guest medium or imply full-image/CPU/notebook qualification.
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
             'lake-manifest.json', 'scripts/build_course_package.py',
             'scripts/course_package.py', 'scripts/core0_common.py',
             'tests/courses/test_package.py'}
    pending = ['Lemma/Courses/PackagePublishMain.lean', 'Lemma/Compiler/CoursePackageExport.lean',
               'tests/courses/Export.lean', 'tests/courses/Package.lean',
               'tests/courses/Store.lean', 'tests/courses/StoreExport.lean', 'tests/courses/Author.lean']
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
                elif not module.startswith(('Lean', 'Init', 'Std')):
                    raise Core0Error('unaccounted upstream module: ' + module)
    if len(files) < 20:
        raise Core0Error('unexpectedly empty project/compiler source closure')
    return {name: sha256(root / name) for name in sorted(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.output_dir.resolve()
    if not out.is_relative_to(root / 'build/courses') or out.exists():
        parser.error('an unused build/courses directory is required')
    out.mkdir(parents=True)
    started = time.monotonic()
    result = dict(status='FAIL', format='lemma-course-package/1',
                  scope='typed original publisher + genuine read-only decoder and copied-IPC Store loader LLVM/RV64 components; CPU/notebook NOT_RUN',
                  bounds=dict(command_seconds=300, whole_seconds=1200, address_space_bytes=16 << 30,
                              generated_file_bytes=1 << 30, package_bytes=32768))
    # Pinned Lean reserves more than4GiB of virtual address space for its
    # thread stacks despite a much smaller resident footprint. This cap is a
    # virtual-address bound; actual child peak RSS is reported separately.
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    commands = []

    def run(label, argv, env=None):
        remaining = 1200 - (time.monotonic() - started)
        if remaining <= 0:
            raise Core0Error('course qualification whole deadline exceeded')
        record = run_bounded(argv, cwd=root, env=env, timeout_seconds=min(300, remaining))
        (out / (label + '.stdout.log')).write_bytes(record.stdout)
        (out / (label + '.stderr.log')).write_bytes(record.stderr)
        commands.append(dict(label=label, argv=list(argv), returncode=record.returncode,
                             wall_seconds=record.elapsed_seconds))
        if record.returncode:
            raise Core0Error(f'{label} failed with exit {record.returncode}; retained actual logs in {out}')
        return record

    try:
        tools = require_tools(('lean', 'lake', 'opt', 'llc', 'llvm-nm', 'llvm-readelf'))
        versions = {}
        for name in tools:
            versions[name] = run('version-' + name, [tools[name], '--version']).stdout.decode().strip()
        if '4.34.1' not in versions['lean'] or '20.1.8' not in versions['opt'] or '20.1.8' not in versions['llc']:
            raise Core0Error('course qualification requires the pinned Lean4.34.1/LLVM20.1.8 tools')
        result.update(tools=tools, versions=versions)
        with (root / 'build/task006-lake.lock').open('a+b') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            before = source_inputs(root)
            archive = out / 'consumed-source-root'
            archive.mkdir()
            for name, digest in before.items():
                source = root / name
                if sha256(source) != digest:
                    raise Core0Error('source changed before archive: ' + name)
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            write_json(out / 'source-inputs.json', before)
            result.update(source_inputs=before, source_count=len(before))
            run('build', [tools['lake'], 'build', 'Lemma.Courses.PackagePublishMain',
                          'Lemma.Compiler.CoursePackageExport'])
            run('publish', [tools['lake'], 'env', 'lean', '--run',
                            'Lemma/Courses/PackagePublishMain.lean', '--output-dir', str(out / 'package')])
            run('author-edition', [tools['lake'], 'env', 'lean', '--run', 'tests/courses/Author.lean',
                                   '--output-dir', str(out / 'author-package')])
            env = dict(os.environ, LEMMA_COURSE_PACKAGE_FILE=str(out / 'package/arithmetic.lcp'),
                       LEMMA_COURSE_PACKAGE_OUT=str(out / 'component'),
                       LEMMA_COURSE_STORE_OUT=str(out / 'store-component'))
            run('guest-actions', [tools['lake'], 'env', 'lean', '--run', 'tests/courses/Package.lean'], env)
            run('genuine-export', [tools['lake'], 'env', 'lean', 'tests/courses/Export.lean'], env)
            run('store-actions', [tools['lake'], 'env', 'lean', '--run', 'tests/courses/Store.lean'], env)
            run('store-genuine-export', [tools['lake'], 'env', 'lean', 'tests/courses/StoreExport.lean'], env)
            run('independent-codec', [os.environ.get('PYTHON', 'python3'), '-m', 'unittest',
                                      'discover', '-s', 'tests/courses', '-v'], env)
            if source_inputs(root) != before:
                raise Core0Error('consumed project/compiler source changed during capture')
        component = out / 'component'
        unit = json.loads((component / 'unit.json').read_text())
        if unit.get('contract_version') != 'core0-user-v0.2' or len(unit.get('roots', [])) != 4:
            raise Core0Error('genuine decoder contract/root closure differs')
        functions = unit.get('functions', [])
        if len(functions) < 10 or any(set(row['effects']) - {'checked-access', 'virtual-read'} for row in functions):
            raise Core0Error('guest decoder is empty or acquired undeclared effects')
        expected_ops = {'execution.virtual-read8', 'execution.virtual-read64'}
        if {row['stable_id'] for row in unit['used_execution_ops']} != expected_ops or unit['used_device_ops']:
            raise Core0Error('guest decoder operation closure differs')
        if re.search(r'\bstore\b', (component / 'program.ll').read_text()):
            raise Core0Error('observational decoder LLVM contains a store')
        run('opt', [tools['opt'], '-S', '-passes=default<O2>', '-verify-each',
                    str(component / 'program.ll'), '-o', str(component / 'program.opt.ll')])
        run('rv64-object', [tools['llc'], '-mtriple=riscv64-unknown-none-elf',
                           '-mattr=+m,-a,-f,-d,-c', '-relocation-model=static', '-filetype=obj',
                           str(component / 'program.opt.ll'), '-o', str(component / 'program.o')])
        undefined = run('undefined', [tools['llvm-nm'], '--undefined-only', str(component / 'program.o')]).stdout
        if undefined.strip():
            raise Core0Error('unexpected helper/runtime dependency in decoder component')
        symbols = run('symbols', [tools['llvm-nm'], '--defined-only', str(component / 'program.o')]).stdout.decode()
        if re.search(r'\b(?:lean_|malloc|calloc|realloc|free|memcpy|memset|__.*(?:div|mod))', symbols):
            raise Core0Error('unaccounted hosted/helper dependency in RV64 object')
        attributes = run('elf', [tools['llvm-readelf'], '-h', '-A', '-r', str(component / 'program.o')]).stdout.decode()
        # require_tools resolves llvm-readelf to llvm-readobj in this pinned
        # distribution, whose independently printed machine name is EM_RISCV.
        # Also check the actual ELF header instead of relying on presentation.
        elf = (component / 'program.o').read_bytes()
        if (elf[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<HH', elf, 16) != (1, 243) or
                struct.unpack_from('<I', elf, 48)[0] != 0 or
                ('Machine: EM_RISCV' not in attributes and 'Machine:                           RISC-V' not in attributes) or
                'rv64i2p1_m2p0' not in attributes or re.search(r'\bR_RISCV_(?:RVC|TLS)', attributes)):
            raise Core0Error('decoder object ISA/relocation provenance differs')
        artifact = decode((out / 'package/arithmetic.lcp').read_bytes())
        write_json(out / 'independent-package.json', artifact)
        authored = decode((out / 'author-package/arithmetic.lcp').read_bytes())
        if (authored['identity'] != 1 or authored['edition'] != 2 or authored['nodes'][2]['goal'] != 1 or
                not authored['nodes'][2]['hint'].startswith('Choose a common positive denominator') or
                authored['source_anchor'] != 'tests/courses/Author.lean#editionTwo'):
            raise Core0Error('ordinary author publisher/unchanged guest decoder edition path differs')
        write_json(out / 'independent-author-package.json', authored)
        store_component = out / 'store-component'
        store_unit = json.loads((store_component / 'unit.json').read_text())
        if (store_unit.get('contract_version') != 'core0-user-v0.2' or
                [row['source'] for row in store_unit.get('roots', [])] != ['Lemma.Courses.PackageStore.load'] or
                store_unit.get('used_device_ops') or
                {row['stable_id'] for row in store_unit.get('used_execution_ops', [])} != {
                    'execution.virtual-read8', 'execution.virtual-read64',
                    'execution.virtual-write8', 'execution.virtual-write64', 'execution.syscall'}):
            raise Core0Error('dynamic Store loader escaped its declared copied-IPC operation closure')
        run('store-opt', [tools['opt'], '-S', '-passes=default<O2>', '-verify-each',
                          str(store_component / 'program.ll'), '-o', str(store_component / 'program.opt.ll')])
        run('store-rv64-object', [tools['llc'], '-mtriple=riscv64-unknown-none-elf',
                                 '-mattr=+m,-a,-f,-d,-c', '-relocation-model=static', '-filetype=obj',
                                 str(store_component / 'program.opt.ll'), '-o', str(store_component / 'program.o')])
        store_undefined = run('store-undefined', [tools['llvm-nm'], '--undefined-only',
                                                 str(store_component / 'program.o')]).stdout.decode().split()
        if store_undefined != ['U', 'lemma_exec_syscall']:
            raise Core0Error('Store component must leave exactly the existing declared syscall boundary unresolved')
        result.update(status='PASS_TYPED_PACKAGE_AND_GENUINE_RV64_COMPONENTS',
                      package_sha256=sha256(out / 'package/arithmetic.lcp'),
                      package_bytes=artifact['bytes'], package_crc32=artifact['crc32'],
                      node_count=len(artifact['nodes']), function_count=len(functions),
                      author_package_sha256=sha256(out / 'author-package/arithmetic.lcp'),
                      author_package_bytes=authored['bytes'], author_package_crc32=authored['crc32'],
                      author_edition=authored['edition'],
                      unit_sha256=sha256(component / 'unit.json'),
                      llvm_sha256=sha256(component / 'program.ll'),
                      optimized_llvm_sha256=sha256(component / 'program.opt.ll'),
                      object_sha256=sha256(component / 'program.o'),
                      store_function_count=len(store_unit['functions']),
                      store_unit_sha256=sha256(store_component / 'unit.json'),
                      store_llvm_sha256=sha256(store_component / 'program.ll'),
                      store_optimized_llvm_sha256=sha256(store_component / 'program.opt.ll'),
                      store_object_sha256=sha256(store_component / 'program.o'),
                      store_unresolved_boundary=['lemma_exec_syscall'])
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        result.update(commands=commands, wall_seconds=time.monotonic()-started,
                      child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
        write_json(out / 'result.json', result)
    print(result['status'], result['package_bytes'], result['wall_seconds'])


if __name__ == '__main__':
    main()
