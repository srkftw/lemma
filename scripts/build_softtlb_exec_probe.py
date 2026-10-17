#!/usr/bin/env python3
"""Genuine checked Lean executable-translation/self-modification test image.

The two leaf instruction streams come only from ordinary Lean declarations.
Host code invokes pinned tools, checks their output and binds source identities;
it never generates LLVM, target instructions, a guest PTE or a guest result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import signal
import struct
import subprocess
import sys
import time

from build_core0 import LLC_ARGUMENTS, STARTUP_ARGUMENTS

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def leaf_sections(elf, symbols):
    """Audit actual compiler output needed by the guest's single-word copy."""
    raw = elf.read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[0][:7] == b'\x7fELF\x02\x01\x01' and h[2] == 243 and h[7] == 0,
            'RV64 uncompressed little-endian ELF required')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6] + index * 64)
                for index in range(h[12])]
    names = sections[h[13]]
    strings = raw[names[4]:names[4] + names[5]]
    table = {strings[row[0]:].split(b'\0', 1)[0].decode(): row for row in sections}
    ph = [struct.unpack_from('<IIQQQQQQ', raw, h[5] + index * 56) for index in range(h[10])]
    result = {}
    for name, virtual, physical, addition in (('.alias_a', 0x82050000, 0x82103000, 111),
                                               ('.alias_b', 0x82104000, 0x82104000, 222)):
        row = table[name]
        require(row[3] == virtual and row[5] == 8 and row[2] & 4, 'exact compiled executable leaf extent')
        require(any(p[0] == 1 and p[3:7] == (virtual, physical, 8, 8) for p in ph),
                'exact separate ELF virtual/load addresses')
        code = raw[row[4]:row[4] + row[5]]
        add, ret = struct.unpack('<2I', code)
        require(add & 0xfffff == 0x50513 and add >> 20 == addition and ret == 0x8067,
                'actual LLVM leaf must be addi a0,a0,constant; ret, with no PC-relative dependency')
        result[name] = {'virtual': virtual, 'physical': physical, 'bytes': len(code),
                        'sha256': hashlib.sha256(code).hexdigest(),
                        'compiler_symbol': symbols['valueA' if name == '.alias_a' else 'valueB']}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    # Pinned Lean reserves 9.10 GB of virtual addresses even for Core0.IR;
    # independently measured in task006-lean-virtual-reservation-a2. Keep real
    # resident memory bounded separately instead of denying that reservation.
    resource.setrlimit(resource.RLIMIT_AS, (16 << 30, 16 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    report = {'status': 'RUNNING', 'scope': __doc__, 'commands': [],
              'bounds': {'whole_seconds': 600, 'command_seconds': 300,
                         'process_AS_bytes': 16 << 30, 'process_RSS_bytes': 4 << 30,
                         'file_bytes': 1 << 30}, 'peak_RSS_bytes': 0}
    files = sorted((ROOT / 'Lemma').rglob('*.lean')) + [
        ROOT / 'tests/qemu' / name for name in ('SoftTlbProbe.lean', 'SoftTlbExecProbe.lean', 'SoftTlbExecExport.lean')]
    files += [ROOT / name for name in ('scripts/build_softtlb_exec_probe.py', 'scripts/build_core0.py',
             'scripts/core0_common.py', 'flake.nix', 'flake.lock', 'lakefile.toml', 'lake-manifest.json',
             'lean-toolchain', 'tooling/toolchain-lock.json')]
    report['source_inputs'] = {str(path.relative_to(ROOT)): sha(path) for path in files}

    def run(argv, label, *, env=None):
        left = 600 - (time.monotonic() - started)
        require(left > 0, 'prospective whole build deadline')
        began = time.monotonic()
        limit = min(300, left)
        with (out / (label + '.log')).open('xb') as log:
            process = subprocess.Popen(argv, cwd=ROOT, stdout=log, stderr=log,
                start_new_session=True,
                env={**os.environ, 'LEAN_NUM_THREADS': '2', **(env or {})})
            try:
                while process.poll() is None:
                    try:
                        status = Path('/proc', str(process.pid), 'status').read_text()
                        resident = re.search(r'^VmRSS:\s+(\d+) kB', status, re.M)
                        if resident:
                            used = int(resident[1]) * 1024
                            report['peak_RSS_bytes'] = max(report['peak_RSS_bytes'], used)
                            require(used <= 4 << 30, 'actual tool resident-memory bound')
                    except FileNotFoundError:
                        pass
                    require(time.monotonic() - began < limit, 'actual tool time bound: ' + label)
                    time.sleep(.01)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                report['commands'].append({'argv': argv, 'returncode': process.returncode,
                    'seconds': time.monotonic() - began})
        require(process.returncode == 0, 'actual tool failed: ' + label)
        return (out / (label + '.log')).read_text()

    try:
        tools = {name: shutil.which(name) for name in
                 ('lean', 'lake', 'opt', 'llc', 'clang', 'ld.lld', 'llvm-nm', 'llvm-readelf', 'llvm-objdump')}
        require(all(path and str(Path(path).resolve()).startswith('/nix/store/') for path in tools.values()),
                'pinned Nix tools required')
        report['tools'] = {name: {'path': path, 'sha256': sha(path),
                                  'version': run([path, '--version'], name + '-version')}
                           for name, path in tools.items()}
        runtime = Path(tools['lean']).resolve().with_name('.lean-wrapped')
        require(runtime.is_file(), 'pinned wrapped Lean runtime missing')
        report['tools']['lean']['runtime'] = {'path': str(runtime), 'sha256': sha(runtime)}
        require('4.34.1' in report['tools']['lean']['version'] and
                all('20.1.8' in report['tools'][name]['version'] for name in ('opt', 'llc', 'clang', 'ld.lld')),
                'pinned Lean/LLVM versions required')
        front = out / 'frontend'
        (front / 'tests/qemu').mkdir(parents=True)
        standard = Path(tools['lean']).resolve().parent.parent / 'lib/lean'
        require((standard / 'Lean.olean').is_file(), 'pinned standard library missing')
        env = {'LEAN_PATH': str(front) + ':' + str(standard),
               'LEMMA_SOFTTLB_EXEC_OUT': str(out / 'export')}
        # Build the actual dependency closure serially with pinned Lean, from
        # source into a fresh directory. No project .olean cache is consumed.
        seen, visiting, order = set(), set(), []
        report['toolchain_imports'] = {}
        def dependency(name):
            require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', name), 'unsupported module spelling')
            if name in seen:
                return
            source = ROOT / (name.replace('.', '/') + '.lean')
            if not source.is_file():
                obj = standard / (name.replace('.', '/') + '.olean')
                require(obj.is_file(), 'unknown import: ' + name)
                report['toolchain_imports'][name] = {'path': str(obj), 'sha256': sha(obj)}
                seen.add(name)
                return
            require(name not in visiting, 'cyclic project imports')
            visiting.add(name)
            for line in source.read_text().splitlines():
                if line.startswith('import '):
                    for imported in line.split('--', 1)[0][7:].split():
                        dependency(imported)
            visiting.remove(name)
            seen.add(name)
            order.append(name)
        dependency('Lemma.Compiler.CFGLower')
        dependency('Lemma.Platform.RiscV.ExecutionPrimitives')
        dependency('tests.qemu.SoftTlbExecProbe')
        report['elaborated_project_modules'] = []
        for index, name in enumerate(order):
            relative = name.replace('.', '/') + '.lean'
            obj = front / (name.replace('.', '/') + '.olean')
            obj.parent.mkdir(parents=True, exist_ok=True)
            run([tools['lean'], '-j2', '-o', str(obj), relative], 'module-' + str(index), env=env)
            report['elaborated_project_modules'].append({'module': name, 'source_sha256': sha(ROOT / relative),
                                                        'olean_sha256': sha(obj)})
        run([tools['lean'], '-j2', 'tests/qemu/SoftTlbExecExport.lean'], 'genuine-export', env=env)
        for name in ('program.ll', 'startup.S', 'link.ld', 'symbols.txt', 'normalized.txt'):
            shutil.copyfile(out / 'export' / name, out / name)
        symbols = {}
        for line in (out / 'symbols.txt').read_text().splitlines():
            for name in ('valueA', 'valueB'):
                if line.startswith('source=Lemma.Qemu.SoftTlbExecProbe.' + name + ';llvm='):
                    require(name not in symbols, 'ambiguous genuinely lowered leaf')
                    symbols[name] = line.split(';llvm=')[1]
        require(set(symbols) == {'valueA', 'valueB'}, 'missing genuine scalar declarations')
        run([tools['opt'], '-S', '-passes=verify', str(out / 'program.ll'), '-o', str(out / 'program.verified.ll')], 'verify')
        run([tools['opt'], '-S', '-passes=default<O2>', str(out / 'program.ll'), '-o', str(out / 'program.opt.ll')], 'optimize')
        for phase in ('program.ll', 'program.opt.ll'):
            text = (out / phase).read_text()
            require(text.count('call i64 @' + symbols['valueA'] + '(') >= 5 and
                    text.count('call i64 @' + symbols['valueB'] + '(') >= 1,
                    'ordinary compiled alias calls disappeared: ' + phase)
        run([tools['llc'], *LLC_ARGUMENTS, '-function-sections', '-O2', str(out / 'program.opt.ll'),
             '-o', str(out / 'program.o')], 'llc')
        run([tools['clang'], *STARTUP_ARGUMENTS, str(out / 'startup.S'), '-o', str(out / 'startup.o')], 'startup')
        run([tools['ld.lld'], '-m', 'elf64lriscv', '--no-relax', '-T', str(out / 'link.ld'),
             str(out / 'startup.o'), str(out / 'program.o'), '--Map=' + str(out / 'image.map'),
             '-o', str(out / 'image.elf')], 'link')
        require(not run([tools['llvm-nm'], '--undefined-only', str(out / 'image.elf')], 'undefined').strip(),
                'unaccounted target helper')
        audit = run([tools['llvm-readelf'], '-h', '-A', '-l', '-s', '-r', str(out / 'image.elf')], 'elf-audit')
        require('rv64i2p1_m2p0_zicsr2p0_zifencei2p0' in audit and
                'There are no relocations' in audit, 'exact ISA/link closure')
        disasm = run([tools['llvm-objdump'], '-d', str(out / 'image.elf')], 'disassembly')
        require('sfence.vma' in disasm and 'fence.i' in disasm, 'actual guest translation/instruction fences absent')
        report['leafs'] = leaf_sections(out / 'image.elf', symbols)
        require(all(sha(ROOT / name) == digest for name, digest in report['source_inputs'].items()),
                'consumed source changed during genuine compilation')
        report['outputs'] = {name: sha(out / name) for name in ('image.elf', 'program.ll', 'program.opt.ll',
            'program.o', 'startup.S', 'startup.o', 'link.ld', 'symbols.txt', 'normalized.txt',
            'elf-audit.log', 'disassembly.log')}
        report['status'] = 'PASS_GENUINE_LEAN_EXECUTABLE_SOFTTLB_TEST_IMAGE'
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
