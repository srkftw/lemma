#!/usr/bin/env python3
"""Real Clocked13 raw ownership and exact rejection checks, without a guest.

Use --retained-component to qualify new structural checks against a sealed
earlier execution without repeating its live prefix. Neither mode establishes
guest journal reconciliation, enumeration, authenticated transport or Saved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

from check_native_usb_wire_pending import run_fixture
from silicon_compute import source_manifest, snapshot_inputs
from silicon_guest import ROOT, sha

OBJECTS = ('machine_runtime.o', 'backing_io.o', 'backing_io_posix.o',
           'backing_peer.o', 'ble_peer_transport.o', 'usb_transport.o',
           'verilated.o', 'verilated_save.o', 'verilated_threads.o',
           'verilated_dpi.o', 'Vlemma_soc__ALL.a')
FIXTURES = ROOT / 'conformance/lemmasim'
MASK = (1 << 64) - 1


def require(value, message):
    if not value:
        raise ValueError(message)


def compile_probe(native, source, output):
    compiler = Path(shutil.which('c++') or '').resolve()
    require(str(compiler).startswith('/nix/store/') and compiler.is_file(),
            'Pinned native compiler is required; use tooling/silicon/sim.nix')
    version = subprocess.check_output(['verilator', '-V'], text=True, timeout=10)
    roots = set(re.findall(r'^\s*VERILATOR_ROOT\s*=\s*(\S+)\s*$', version, re.M))
    require(len(roots) == 1, 'Unambiguous Verilator runtime required')
    prefix = Path(roots.pop())
    objects = [native / 'obj' / name for name in OBJECTS]
    inputs = {str(path): sha(path) for path in objects + [source]}
    command = [str(compiler), '-O2', '-std=c++17', '-I', str(ROOT/'sim/rtl/host'),
               '-I', str(native/'obj'), '-isystem', str(prefix/'include'),
               '-isystem', str(prefix/'include/vltstd'), str(source),
               *map(str, objects), '-pthread', '-o', str(output/'probe')]
    (output/'compile-command.json').write_text(json.dumps(command, indent=2)+'\n')
    with (output/'compile.log').open('xb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=60)
    return inputs


def crc_table():
    table = []
    for byte in range(256):
        value = byte << 56
        for _ in range(8):
            value = ((value << 1) ^ (0x42f0e1eba9ea3693 if value >> 63 else 0)) & MASK
        table.append(value)
    return table


def mutants(component, output):
    table = crc_table()
    def crc(raw):
        value = 0
        for byte in raw:
            value = ((value << 8) ^ table[(value >> 56) ^ byte]) & MASK
        return value
    require(crc(b'123456789') == 0x6c40df5f0b497347, 'Published CRC64 known answer')
    parent = json.loads((component/'result.json').read_text())
    binding = parent['namespace_binding']
    raw = (component/'after-attach.snap').read_bytes()
    require(raw[:8] == b'LMSSRTL1' and struct.unpack_from('<Q', raw, 8)[0] == 11,
            'Require actual recovery container11')
    wn, mn, wc, mc = struct.unpack_from('<4Q', raw, 80)
    require(112+wn+mn == len(raw) and crc(memoryview(raw)[112:112+wn]) == wc
            and crc(memoryview(raw)[112+wn:]) == mc, 'Retained whole snapshot CRC')
    offset = raw.find(binding.encode())
    require(offset >= 112 and offset == raw.rfind(binding.encode()) and
            struct.unpack_from('<3Q', raw, offset-24) == (1, 2, 64),
            'Unambiguous actual recovery marker/epoch/binding')
    for name, at, value in (('marker', offset-24, 2), ('epoch-zero', offset-16, 0),
                            ('epoch-overflow', offset-16, MASK), ('container', 8, 10)):
        changed = bytearray(raw)
        struct.pack_into('<Q', changed, at, value)
        if at >= 112:
            struct.pack_into('<Q', changed, 96, crc(memoryview(changed)[112:112+wn]))
        (output/(name+'.snap')).write_bytes(changed)
    changed = bytearray(raw)
    changed[offset] = ord('g')
    struct.pack_into('<Q', changed, 96, crc(memoryview(changed)[112:112+wn]))
    (output/'binding-hex.snap').write_bytes(changed)
    lines = (component/'final.tape').read_text().splitlines()
    require(lines[0].startswith('LMUSBRP2 ') and lines[1].startswith('HORIZON '),
            'Retained recovery outcomes schema')
    horizon = int(lines[1].split()[1])
    rows = lines[2:-1]
    indices = [i for i, row in enumerate(rows) if ' 3 2 ATTACH 3 '+binding in row]
    require(len(indices) == 1, 'Require one actual reconnect')
    cycle = rows[indices[0]].split()[0]
    other_binding = ('b' if binding[0] != 'b' else 'c') + binding[1:]
    for name, frame in (('tape-epoch', f'{cycle} 3 3 ATTACH 3 {binding}'),
                        ('tape-next-id', f'{cycle} 3 2 ATTACH 4 {binding}'),
                        ('tape-binding', f'{cycle} 3 2 ATTACH 3 {other_binding}')):
        changed_rows = rows[:]
        changed_rows[indices[0]] = frame
        value = 14695981039346656037
        for byte in ('\n'.join(changed_rows)+'\n'+f'{horizon} 4 0 HORIZON\n').encode():
            value = ((value ^ byte) * 1099511628211) & MASK
        (output/(name+'.tape')).write_text(
            '\n'.join(lines[:2]+changed_rows+[f'CHECKSUM {value}'])+'\n')
    return {p.name: sha(p) for p in output.iterdir() if p.suffix in ('.snap', '.tape')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl-build', type=Path, required=True)
    parser.add_argument('--retained-component', type=Path)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.work_dir.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'build'):
        parser.error('Require unused owned output under build')
    output.mkdir(parents=True)
    started = time.monotonic()
    result = {'schema': 'lemma-native-usb-recovery-check/1', 'status': 'FAIL',
              'scope': __doc__, 'bounds': {'total_host_seconds': 300,
                'live_clocks': 100000, 'tree_rss_bytes': 4294967296,
                'maximum_owned_output_bytes': 6442450944}, 'observer_sha256': sha(__file__)}
    try:
        native = args.rtl_build.resolve()
        manifest = json.loads((native/'build.json').read_text())
        require(manifest.get('profile') == 'lemma-silicon-dev/0.13.0' and
                manifest.get('runtime_control_contracts') == {'usb_recovery':'lemma-usb-live-recovery/1'},
                'Explicit recovery native manifest required')
        dependencies = ROOT/'build/silicon/deps/cvw'
        current = source_manifest(dependencies, manifest['profile'])
        require(all(manifest.get(k) == v for k, v in current.items()), 'Exact current native source closure')
        require(manifest.get('configuration') == 'external-ram-128MiB', 'Canonical native memory configuration')
        # The compiler seals this pre-build manifest. Output paths, the identity
        # itself and the resulting executable hash are added afterwards.
        current['configuration'] = manifest['configuration']
        identity = hashlib.sha256(json.dumps(snapshot_inputs(current, dependencies),
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        require(identity == manifest['snapshot_identity'] and
                sha(native/'obj/lemma-rtl') == manifest['binary_sha256'], 'Native implementation/binary identity')
        component = args.retained_component.resolve() if args.retained_component else output/'component'
        if not args.retained_component:
            component.mkdir()
            inputs = compile_probe(native, FIXTURES/'UsbRecovery.cpp', component)
            binding = hashlib.sha256(json.dumps({'fixture_sha256':sha(FIXTURES/'UsbRecoveryPeer.py'),
                'namespace':str(component)}, sort_keys=True).encode()).hexdigest()
            run_fixture([component/'probe', component, Path(sys.executable).resolve(),
                         FIXTURES/'UsbRecoveryPeer.py', binding], component/'run.log', 180)
            log = (component/'run.log').read_text()
            require(log.endswith('NATIVE_USB_RECOVERY_PASS actualEOF globalIDs zero-clockattach realresetpending exactthreeforks no-live-fork horizon stale duplicate rejection\n'), 'Actual raw component result')
            parent = {'status':'PASS_RAW_NATIVE_RECOVERY_COMPONENT', 'native_identity':identity,
                'namespace_binding':binding, 'compiled_inputs':inputs,
                'capture_sha256':sha(component/'live.raw'), 'tape_sha256':sha(component/'final.tape'),
                'snapshots':{p.name:{'bytes':p.stat().st_size, 'sha256':sha(p)}
                             for p in component.glob('*.snap')}}
            (component/'result.json').write_text(json.dumps(parent, indent=2)+'\n')
        parent = json.loads((component/'result.json').read_text())
        require(parent['status'] == 'PASS_RAW_NATIVE_RECOVERY_COMPONENT' and
                parent['native_identity'] == identity, 'Retained component identity/result')
        for path, digest in parent['compiled_inputs'].items():
            require(sha(path) == digest, 'Retained compiled input changed: '+path)
        for name, record in parent['snapshots'].items():
            require(Path(name).name == name and sha(component/name) == record['sha256'], 'Retained snapshot changed')
        require(sha(component/'live.raw') == parent['capture_sha256'] and
                sha(component/'final.tape') == parent['tape_sha256'] and
                int((component/'spawn-count').read_text()) == 2, 'Actual original outcomes/two child lifetimes')
        validation = output/'validation'
        validation.mkdir()
        mutations = mutants(component, validation)
        inputs = compile_probe(native, FIXTURES/'UsbRecoveryValidation.cpp', validation)
        run_fixture([validation/'probe', component, validation], validation/'run.log', 120)
        log = (validation/'run.log').read_text()
        require(log.endswith('NATIVE_USB_RECOVERY_VALIDATION_PASS eight structural negatives exact unchanged full archive zero clocks no peer\n'), 'Actual complete state rejection result')
        for path, digest in inputs.items():
            require(sha(path) == digest, 'Validation compiled input changed')
        require(int((component/'spawn-count').read_text()) == 2 and
                sha(component/'live.raw') == parent['capture_sha256'], 'Validation contacted original process')
        require(time.monotonic()-started <= 300 and
                sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) <= 6442450944,
                'Original complete check resource bounds')
        result.update(status='PASS_RAW_RECOVERY_AND_EIGHT_EXACT_REJECTIONS',
            native_identity=identity, native_manifest_sha256=sha(native/'build.json'),
            parent_result_sha256=sha(component/'result.json'), reused_live_prefix=bool(args.retained_component),
            validation_clocks=0, original_process_spawns=2, mutations=mutations,
            validation_compiled_inputs=inputs, actual_validation_log=log,
            authoritative_boundary_sha256=sha(validation/'before.snap'),
            unchanged_after_valid_binding_sha256=sha(validation/'bound.snap'))
    except (OSError, ValueError, KeyError, AssertionError, RuntimeError, subprocess.SubprocessError) as error:
        result['error'] = repr(error)
    result['host_seconds'] = time.monotonic()-started
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','error','host_seconds','reused_live_prefix')}))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
