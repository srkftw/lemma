#!/usr/bin/env python3
"""Independent literal FDT fixtures for the compiled-Lean host Action probe.
This checks declarations using actual QEMU DTB bytes, not RV64 boot execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def properties(blob):
    def word(at):
        return struct.unpack_from('>I', blob, at)[0]
    cursor = word(8)
    end = cursor + word(36)
    strings = word(12)
    stack = []
    result = {}
    while cursor < end:
        token = word(cursor)
        cursor += 4
        if token == 1:
            stop = blob.index(0, cursor)
            stack.append(blob[cursor:stop].decode('ascii'))
            cursor = (stop + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            length, offset = word(cursor), word(cursor + 4)
            cursor += 8
            stop = blob.index(0, strings + offset)
            name = blob[strings + offset:stop].decode('ascii')
            key = ('/'.join(stack), name)
            if key in result:
                raise ValueError('duplicate fixture property')
            result[key] = cursor, length
            cursor = (cursor + length + 3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            return result
        else:
            raise ValueError('unknown fixture token')
    raise ValueError('fixture has no END token')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qemu, probe = args.qemu.resolve(), args.probe.resolve()
    report = {'scope': 'host Action validator and actual patched-QEMU FDT; not RV64 boot',
              'status': 'FAIL', 'qemu_sha256': digest(qemu), 'probe_sha256': digest(probe), 'observations': []}
    try:
        disk = out / 'empty.img'
        with disk.open('xb') as file:
            file.truncate(2 * 1024 * 1024)
        command = [str(qemu), '-machine', f'lemmasim-virt,dumpdtb={out}/actual.dtb', '-m', '128M', '-smp', '1',
                   '-cpu', 'rv64,smrnmi=false,smdbltrp=false', '-accel', 'tcg', '-bios', 'none', '-nodefaults',
                   '-display', 'none', '-global', 'virtio-mmio.force-legacy=false',
                   '-blockdev', json.dumps({'driver': 'file', 'filename': str(disk), 'node-name': 'fixture-file', 'read-only': True}),
                   '-blockdev', json.dumps({'driver': 'raw', 'file': 'fixture-file', 'node-name': 'fixture-raw', 'read-only': True}),
                   '-device', 'virtio-blk-device,drive=fixture-raw,bus=virtio-mmio-bus.0']
        result = subprocess.run(command, capture_output=True, timeout=20)
        (out / 'qemu.stderr').write_bytes(result.stderr)
        report['qemu_argv'] = command
        report['qemu_returncode'] = result.returncode
        if result.returncode:
            raise ValueError('actual QEMU DTB generation failed')
        original = (out / 'actual.dtb').read_bytes()
        offsets = properties(original)
        cases = [('actual', None, None, 0),
                 ('bad-irq', ('/soc/lemma-paper@10010000', 'interrupts'), struct.pack('>I', 11), 169),
                 ('unknown-abi', ('/soc/lemma-pen@10011000', 'lemma,abi-version'), struct.pack('>I', 2), 169),
                 ('bad-timebase', ('/cpus', 'timebase-frequency'), struct.pack('>I', 10000001), 169),
                 ('overlap', ('/fw-cfg@10100000', 'reg'), struct.pack('>QQ', 0x10010000, 0x18), 169),
                 ('bad-header-size', None, None, 60)]
        for name, key, value, expected in cases:
            blob = bytearray(original)
            if key:
                offset, length = offsets[key]
                if length != len(value):
                    raise ValueError('literal fixture length differs')
                blob[offset:offset + length] = value
            if name == 'bad-header-size':
                struct.pack_into('>I', blob, 4, len(blob) - 4)
            path = out / (name + '.dtb')
            path.write_bytes(blob)
            result = subprocess.run([str(probe), str(path)], capture_output=True, timeout=60)
            (out / (name + '.stdout')).write_bytes(result.stdout)
            (out / (name + '.stderr')).write_bytes(result.stderr)
            fields = result.stdout.decode('ascii').strip().split(':')
            status = int(fields[1]) if len(fields) == 3 and fields[0] == 'DESCRIPTOR_HOST_ACTION' else None
            accepted = status == expected and result.returncode == (0 if expected == 0 else 1)
            report['observations'].append({'case': name, 'dtb_sha256': digest(path), 'status': status,
                                           'returncode': result.returncode, 'expected_status': expected, 'accepted': accepted})
            if not accepted:
                raise ValueError(f'actual guest declaration behavior differs for {name}')
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: actual DTB and five rejected literal boundaries (host Action scope)')


if __name__ == '__main__':
    main()
