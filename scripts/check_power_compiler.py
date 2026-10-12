#!/usr/bin/env python3
"""Execute genuine checked LLVM device guards on host-only synthetic registers.

The native derivative and fence counter never enter a target link. This checks
the emitted guard behavior; it is neither a CPU conformance test nor proof of
compiler correctness. The separate RV64 power probe exercises the real device.
"""
from __future__ import annotations
import argparse
import ctypes
import os
from pathlib import Path
import re
import subprocess

from core0_common import Core0Error, repo_root, sha256, write_json


class Result(ctypes.Structure):
    _fields_ = [('status', ctypes.c_uint8), ('value', ctypes.c_uint64)]


def execute(root: Path, path: Path, *, export: bool = True) -> dict:
    if export:
        if path.exists():
            raise Core0Error('refusing to overwrite retained compiler observation')
        subprocess.run(['lake', 'env', 'lean', 'tests/lemmasim/CompilerPowerBoundary.lean'],
            cwd=root, env={**os.environ, 'LEMMA_POWER_BOUNDARY_OUT': str(path)},
            check=True, timeout=120)
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    base = 0x0c000000
    # MAP_FIXED_NOREPLACE refuses any collision; never replace process memory.
    mapped = libc.mmap(base, 4096, 3, 0x22 | 0x100000, -1, 0)
    if mapped != base:
        if mapped not in (None, ctypes.c_void_p(-1).value):
            libc.munmap(mapped, 4096)
        raise Core0Error(f'cannot map isolated synthetic PLIC page, errno={ctypes.get_errno()}')
    observations = []
    try:
        for version, last in [(3, 0x34), (4, 0x38)]:
            contract = f'core0-kernel-v0.{version}'
            original = path / (contract + '.ll')
            symbols = dict(re.findall(r'source=([^;\n]+);llvm=([^\n]+)',
                                     (path / (contract + '.symbols')).read_text()))
            prefix = 'Lemma.Compiler.Test.PowerBoundary.'
            emitted = original.read_text()
            # Explicit host-only target derivative; retain original RV64 bytes.
            emitted = re.sub(r'^target (?:datalayout|triple) = .*\n', '', emitted, flags=re.M)
            emitted = re.sub(r'^!.*\n', '', emitted, flags=re.M)
            emitted = emitted.replace('declare void @core0_io_fence() nounwind', '')
            emitted += '\n@boundary_fences = global i64 0, align 8\n'
            emitted += ('define void @core0_io_fence() {\nentry:\n'
                '  %n = load volatile i64, ptr @boundary_fences, align 8\n'
                '  %next = add i64 %n, 1\n'
                '  store volatile i64 %next, ptr @boundary_fences, align 8\n'
                '  ret void\n}\n')
            host = path / (contract + '.host.ll')
            host.write_text(emitted)
            for optimize in [False, True]:
                source = host
                if optimize:
                    source = path / (contract + '.host.opt.ll')
                    subprocess.run(['opt', '-S', '-passes=default<O2>', str(host), '-o', str(source)],
                                   check=True, timeout=30)
                obj = path / (contract + ('.O2' if optimize else '.O0') + '.o')
                shared = obj.with_suffix('.so')
                subprocess.run(['llc', '-mtriple=x86_64-unknown-linux-gnu', '-filetype=obj',
                    '-relocation-model=pic', str(source), '-o', str(obj)], check=True, timeout=30)
                subprocess.run(['ld.lld', '-shared', str(obj), '-o', str(shared)],
                               check=True, timeout=30)
                library = ctypes.CDLL(str(shared))
                read = getattr(library, symbols[prefix + 'read'])
                write = getattr(library, symbols[prefix + 'write'])
                read.argtypes = [ctypes.c_uint64]; read.restype = Result
                write.argtypes = [ctypes.c_uint64, ctypes.c_uint64]; write.restype = Result
                fences = ctypes.c_uint64.in_dll(library, 'boundary_fences')
                for offset, status in [(0x34, 0), (0x38, 0 if version == 4 else 7),
                                       (0x3c, 7), (0x39, 8), (0, 7), (0x40, 7)]:
                    address = base + offset
                    cell = ctypes.c_uint32.from_address(address & ~3)
                    cell.value = 0x53172abc
                    fences.value = 0
                    result = read(address)
                    if (result.status, result.value, fences.value) != (status,
                            0x53172abc if status == 0 else 0, 2 if status == 0 else 0):
                        raise Core0Error(f'{contract} read guard differs at {address:#x}')
                    fences.value = 0
                    result = write(address, 0x87654321)
                    if (result.status, result.value, cell.value, fences.value) != (status, 0,
                            0x87654321 if status == 0 else 0x53172abc, 2 if status == 0 else 0):
                        raise Core0Error(f'{contract} write guard differs at {address:#x}')
                    observations.append(dict(contract=contract, optimized=optimize,
                        address=address, status=status, read_and_write=True))
                cell = ctypes.c_uint32.from_address(base + last)
                cell.value = 0x2345; fences.value = 0
                result = write(base + last, 0x100000000)
                if (result.status, cell.value, fences.value) != (16, 0x2345, 0):
                    raise Core0Error('oversized 32-bit write reached MMIO or lost invalid-length status')
                fences.value = 0
                result = read(0xffffffffffffffff)
                if (result.status, result.value, fences.value) != (8, 0, 0):
                    raise Core0Error('wrapped unaligned address reached MMIO')
    finally:
        if libc.munmap(base, 4096) != 0:
            raise Core0Error('synthetic register teardown failed')
    report = dict(status='PASS', scope='host execution of checked LLVM guards; RV64 probe separate',
        observations=observations, inputs={str(p.relative_to(root)): sha256(p) for p in
        [root/'tests/lemmasim/CompilerPowerBoundary.lean', Path(__file__).resolve(),
         root/'Lemma/Compiler/CFGLower.lean', root/'Lemma/Core0/Execution.lean']},
        artifacts={p.name: sha256(p) for p in path.iterdir() if p.is_file()})
    write_json(path / 'result.json', report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--existing-export', action='store_true')
    ns = parser.parse_args()
    root = repo_root(); path = (root / ns.work_dir).resolve()
    try:
        result = execute(root, path, export=not ns.existing_export)
    except (Core0Error, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'POWER COMPILER FAIL: {error}'); return 1
    print(f'POWER COMPILER PASS: {len(result["observations"])} exact guard cases, O0/O2')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
