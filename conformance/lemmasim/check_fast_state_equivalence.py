#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact checkpoint byte observer with two explicitly pinned host statistics.

This never rewrites snapshots or removes guest counters/timer state. See
QEMU_STATE_EQUIVALENCE.md for the source-bound observation relation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

RUNTIME_SHA256 = '87d7282df1de259a3560fee369ef1f303a644654793726fc9da12009d639d467'
REVIEWED_RUNTIMES = {RUNTIME_SHA256: ('lemma-silicon-dev/0.1.0', 'lemma-silicon-dev/0.2.0')}
REVIEWED_RUNTIMES['80e54f2095774ecdbfe3bcd36e52e7c55b1c5e566ecf869b4c6ed3f8c857b43a'] = ('lemma-silicon-dev/0.3.0',)
ADAPTER = 'lemmasim-fast-adapter/2'
CPU = 'rv64i,m=true,s=true,u=true,mmu=true,pmp=true,sv39=true,zicsr=true,zifencei=true,zicntr=true,zihpm=false,priv_spec=v1.12.0'
MAX_STATE = 256 * 1024 * 1024
MAX_JSON = 1024 * 1024
TIMER = {
    'name': 'timer', 'instance_id': 0, 'vmsd_name': 'timer', 'version': 2,
    'fields': [
        {'name': 'cpu_ticks_offset', 'type': 'int64', 'size': 8},
        {'name': 'unused', 'type': 'unused_buffer', 'size': 8},
        {'name': 'cpu_clock_offset', 'type': 'int64', 'size': 8}],
    'subsections': [{'vmsd_name': 'timer/icount', 'version': 1, 'fields': [
        {'name': 'qemu_icount_bias', 'type': 'int64', 'size': 8},
        {'name': 'qemu_icount', 'type': 'int64', 'size': 8}]}]}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('Duplicate JSON field')
        result[name] = value
    return result


def parse_json(data):
    if not 0 < len(data) <= MAX_JSON:
        raise ValueError('JSON resource bound')
    return json.loads(data, object_pairs_hook=unique_object)


def section_payload(data, name, version, kind=4):
    """Locate a unique complete fixed-schema section, rejecting ambiguity."""
    key = bytes([len(name)]) + name + struct.pack('>II', 0, version)
    matches = []
    cursor = 0
    while True:
        offset = data.find(key, cursor)
        if offset < 0:
            break
        if offset >= 5 and data[offset - 5] == kind:
            matches.append(offset)
        cursor = offset + 1
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous section ' + name.decode())
    offset = matches[0]
    return offset + len(key), data[offset - 4:offset]


def layout(data):
    if not 64 < len(data) <= MAX_STATE or data[:8] != b'QEVM\0\0\0\3':
        raise ValueError('Unsupported migration container')
    configuration = b'\x07\0\0\0\x12lemma-silicon-fast'
    if data[8:8 + len(configuration)] != configuration:
        raise ValueError('Unsupported machine configuration')
    # Same terminal description framing as pinned scripts/analyze-migration.py,
    # additionally requiring a bounded, exact terminal JSON record.
    start = data.find(b'{', data.rfind(b'\0'))
    if start < 5 or data[start - 5] != 6:
        raise ValueError('Missing VMState description')
    length = struct.unpack('>I', data[start - 4:start])[0]
    if length != len(data) - start:
        raise ValueError('Truncated or trailing VMState description')
    metadata = parse_json(data[start:])
    if not isinstance(metadata, dict) or metadata.get('page_size') != 4096:
        raise ValueError('Unsupported migration metadata')
    devices = metadata.get('devices')
    if not isinstance(devices, list):
        raise ValueError('Missing VMState device inventory')
    timers = [d for d in devices if isinstance(d, dict) and d.get('name') == 'timer']
    cpus = [d for d in devices if isinstance(d, dict) and d.get('name') == 'cpu']
    if timers != [TIMER] or len(cpus) != 1 or cpus[0].get('version') != 11:
        raise ValueError('Unsupported timer/CPU serialization schema')
    fields = cpus[0].get('fields')
    if not isinstance(fields, list) or not fields or fields[0] != {'name': 'env.gpr', 'array_len': 32, 'type': 'uint64', 'size': 8}:
        raise ValueError('Unsupported CPU register serialization')
    payload, ident = section_payload(data, b'timer', 2)
    if data[payload + 8:payload + 16] != bytes(8):
        raise ValueError('Unexpected unused timer field')
    subsection = b'\x05\x0ctimer/icount\0\0\0\1'
    if data[payload + 24:payload + 24 + len(subsection)] != subsection:
        raise ValueError('Unsupported icount subsection')
    icount = payload + 24 + len(subsection)
    if data[icount + 16:icount + 21] != b'\x7e' + ident:
        raise ValueError('Unexpected timer subsection/footer')
    cpu, _ = section_payload(data, b'cpu', 11)
    return {'host_fields': [('cpu_ticks_offset', payload), ('cpu_clock_offset', payload + 16)],
            'icount': icount, 'cpu_gpr_x1': cpu + 8, 'metadata_start': start}


def differences(left, right):
    """Retain every differing byte as contiguous regions, with exact values."""
    regions = []
    for base in range(0, min(len(left), len(right)), 65536):
        a, b = left[base:base + 65536], right[base:base + 65536]
        if a == b:
            continue
        for index, (x, y) in enumerate(zip(a, b)):
            if x == y:
                continue
            offset = base + index
            if regions and regions[-1][1] == offset:
                regions[-1][1] += 1
            else:
                regions.append([offset, offset + 1])
    return [{'start': start, 'end': end, 'left_hex': left[start:end].hex(),
             'right_hex': right[start:end].hex()} for start, end in regions]


def compare(left, right):
    a, b = layout(left), layout(right)
    if a != b or len(left) != len(right) or left[a['metadata_start']:] != right[b['metadata_start']:]:
        raise ValueError('Checkpoint schema/layout/length differs')
    regions = differences(left, right)
    windows = a['host_fields']
    unauthorized = [r for r in regions if not any(offset <= r['start'] and r['end'] <= offset + 8
                                                 for _, offset in windows)]
    fields = []
    for name, offset in windows:
        fields.append({'name': name, 'offset': offset, 'bytes': 8,
                       'left': struct.unpack('>q', left[offset:offset + 8])[0],
                       'right': struct.unpack('>q', right[offset:offset + 8])[0]})
    return {'status': 'FAIL' if unauthorized else 'PASS',
            'relation': 'exact every serialized byte except the two named host elapsed-time statistics',
            'bytes': len(left), 'raw_container_equal': left == right,
            'left_sha256': sha(left), 'right_sha256': sha(right),
            'differing_bytes': sum(r['end'] - r['start'] for r in regions),
            'differences': regions, 'host_statistics': fields,
            'unauthorized_differences': unauthorized,
            'all_other_bytes_equal': not unauthorized,
            'timer_icount': {'offset': a['icount'],
                'qemu_icount_bias': struct.unpack('>q', left[a['icount']:a['icount'] + 8])[0],
                'qemu_icount': struct.unpack('>q', left[a['icount'] + 8:a['icount'] + 16])[0]}}


def ram_mutation_offset(data):
    """Independent first-page decoder for the pinned uncompressed RAM stream."""
    offset, ident = section_payload(data, b'ram', 4, kind=1)
    record = struct.unpack('>Q', data[offset:offset + 8])[0]
    if record & 4095 != 4:
        raise ValueError('Unsupported RAM size record')
    remaining, offset = record & ~4095, offset + 8
    while remaining:
        n = data[offset]
        size = struct.unpack('>Q', data[offset + 1 + n:offset + 9 + n])[0]
        if not 0 < size <= remaining:
            raise ValueError('Invalid RAM block inventory')
        remaining -= size
        offset += 9 + n
    expected = struct.pack('>Q', 16) + b'\x7e' + ident + b'\x02' + ident
    if data[offset:offset + len(expected)] != expected:
        raise ValueError('Unsupported RAM first section')
    offset += len(expected)
    record = struct.unpack('>Q', data[offset:offset + 8])[0]
    if record & 4095 != 8:
        raise ValueError('Expected an uncompressed first RAM page')
    offset += 8
    return offset + 1 + data[offset]


def mutation_checks(data):
    info = layout(data)
    checks = []
    sites = [(name, offset, 'PASS') for name, offset in info['host_fields']]
    sites += [('qemu_icount_bias', info['icount'], 'FAIL'),
              ('qemu_icount', info['icount'] + 8, 'FAIL'),
              ('cpu.env.gpr[1]', info['cpu_gpr_x1'], 'FAIL'),
              ('RAM.first_page.byte[0]', ram_mutation_offset(data), 'FAIL')]
    power = power_offsets(data)
    if power is not None:
        sites += [('power.' + name, offset, 'FAIL') for name, offset in power.items()]
    for name, offset, expected in sites:
        altered = data[:offset] + bytes([data[offset] ^ 1]) + data[offset + 1:]
        observed = compare(data, altered)
        if observed['status'] != expected or observed['differing_bytes'] != 1:
            raise ValueError('Observer mutation check failed: ' + name)
        checks.append({'field': name, 'offset': offset, 'expected': expected,
                       'observed': observed['status']})
    return checks


def power_offsets(data):
    """Locate all seven fixed Power-v1 words; none is an allowed difference.

    This is an independent wire-layout decoder, not a controller state checker.
    The reviewed device prefix has no conditional or variable-size fields.
    An unexpected prefix/schema rejects rather than guessing an offset.
    """
    info = layout(data)
    metadata = parse_json(data[info['metadata_start']:])
    devices = [d for d in metadata['devices'] if d.get('name') == 'lemma-paper-pen/1']
    if not devices or (len(devices) == 1 and devices[0].get('version') == 1):
        return None
    if len(devices) != 1 or devices[0].get('version') != 2:
        raise ValueError('Unsupported power device serialization')
    fields = devices[0].get('fields', [])
    expected = [('width', 'uint32 equal', 4), ('height', 'uint32 equal', 4),
                ('pressure_max', 'uint32 equal', 4), ('frame_bytes', 'uint32 equal', 4),
                ('pen', 'struct', 18523), ('paper', 'struct', 1054),
                ('power_enabled', 'bool', 1), ('power', 'struct', 56)]
    if len(fields) < 8 or [(f.get('name'), f.get('type'), f.get('size')) for f in fields[:8]] != expected:
        raise ValueError('Unsupported fixed power serialization prefix')
    names = ('state', 'error', 'reset_cause', 'button_level', 'events', 'epoch', 'wake_cause')
    if fields[7].get('struct') != {'vmsd_name': 'lemma-power/1', 'version': 1,
            'fields': [{'name': name, 'type': 'uint64', 'size': 8} for name in names]}:
        raise ValueError('Unsupported Power-v1 serialization schema')
    payload, _ = section_payload(data, b'lemma-paper-pen/1', 2)
    start = payload + sum(item[2] for item in expected[:7])
    if start + 56 > info['metadata_start']:
        raise ValueError('Truncated Power-v1 state')
    return {name: start + index * 8 for index, name in enumerate(names)}


def load(path):
    if not path.is_file() or path.is_symlink() or not 64 < path.stat().st_size <= MAX_STATE:
        raise ValueError('Invalid checkpoint file or resource bound')
    manifest_path = path.with_name('snapshot.json')
    if not manifest_path.is_file() or manifest_path.is_symlink() or not 0 < manifest_path.stat().st_size <= MAX_JSON:
        raise ValueError('Invalid snapshot manifest or resource bound')
    manifest = parse_json(manifest_path.read_bytes())
    identity = manifest['identity']
    if manifest['schema'] != 'lemmasim-session/1' or identity.get('backend') != 'qemu' or \
       identity.get('profile') not in REVIEWED_RUNTIMES.get(identity.get('runtime'), ()) or \
       identity.get('cpu') != CPU or identity.get('icount_shift') != 3:
        raise ValueError('Unsupported checkpoint implementation/configuration')
    if type(manifest.get('virtual_ns')) is not int or not 0 <= manifest['virtual_ns'] <= (1 << 63) - 1:
        raise ValueError('Invalid checkpoint virtual phase')
    adapter = identity.get('adapter')
    if adapter not in (None, ADAPTER):
        raise ValueError('Unsupported fast wrapper version')
    inventory = manifest['files']
    if not isinstance(inventory, list) or not 1 <= len(inventory) <= 3:
        raise ValueError('Unsupported checkpoint inventory')
    names = [item['path'] for item in inventory]
    allowed = {'machine.chk', 'durable.raw', 'clock.json'} if adapter else {'machine.chk', 'durable.raw'}
    if len(set(names)) != len(names) or not set(names) <= allowed or \
       'machine.chk' not in names or (adapter and 'clock.json' not in names):
        raise ValueError('Missing or unknown wrapper state')
    items = [f for f in manifest['files'] if f['path'] == path.name]
    data = path.read_bytes()
    if items != [{'path': path.name, 'bytes': len(data), 'sha256': sha(data)}]:
        raise ValueError('Checkpoint manifest checksum/length differs')
    clock = None
    for item in inventory:
        state = path.with_name(item['path'])
        if set(item) != {'path', 'bytes', 'sha256'} or not state.is_file() or state.is_symlink():
            raise ValueError('Malformed or missing checkpoint sidecar')
        bound = 256 if item['path'] == 'clock.json' else MAX_STATE
        if type(item['bytes']) is not int or not 0 < item['bytes'] <= bound or \
           state.stat().st_size != item['bytes'] or file_sha(state) != item['sha256']:
            raise ValueError('Checkpoint sidecar length/checksum differs')
        if item['path'] == 'clock.json':
            clock = state.read_bytes()
            value = parse_json(clock)
            origin = value.get('time_origin_ns') if isinstance(value, dict) else None
            if not isinstance(value, dict) or set(value) != {'schema', 'time_origin_ns'} or \
               value.get('schema') != 'lemmasim-fast-clock/1' or type(origin) is not int or \
               not 0 <= origin <= manifest['virtual_ns'] <= (1 << 63) - 1:
                raise ValueError('Unsupported or invalid wrapper clock state')
    return data, manifest, clock


def compare_checkpoints(left_path, right_path):
    left, lm, lc = load(left_path)
    right, rm, rc = load(right_path)
    if lm['identity'] != rm['identity'] or lm['virtual_ns'] != rm['virtual_ns'] or \
       lm['external_event_cursor'] != rm['external_event_cursor']:
        raise ValueError('Machine identity/virtual phase/external cursor differs')
    if lc != rc:
        raise ValueError('Exact wrapper clock state differs')
    ld = [item for item in lm['files'] if item['path'] == 'durable.raw']
    rd = [item for item in rm['files'] if item['path'] == 'durable.raw']
    if ld != rd:
        raise ValueError('Exact durable base state differs')
    report = compare(left, right)
    report.update({'identity': lm['identity'], 'virtual_ns': lm['virtual_ns'],
                   'durable_base': ld[0] if ld else None,
                   'wrapper_clock': {'bytes': len(lc), 'sha256': sha(lc),
                        'time_origin_ns': parse_json(lc)['time_origin_ns']} if lc is not None else
                        {'adapter': 'historical absent-version wrapper', 'time_origin_ns': 0}})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--left', type=Path, required=True)
    parser.add_argument('--right', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new result JSON; never overwrite evidence')
    parser.add_argument('--mutation-checks', action='store_true')
    args = parser.parse_args()
    try:
        if not 0 < args.qemu.stat().st_size <= MAX_STATE:
            raise ValueError('QEMU binary exceeds its resource bound')
        runtime = file_sha(args.qemu)
        if runtime not in REVIEWED_RUNTIMES:
            raise ValueError('Unreviewed QEMU binary identity')
        version = subprocess.run([str(args.qemu), '--version'], capture_output=True,
                                 text=True, timeout=10, check=True).stdout.splitlines()[0]
        if 'QEMU emulator version 11.1.1' not in version:
            raise ValueError('Unreviewed QEMU version')
        report = compare_checkpoints(args.left, args.right)
        if report['identity']['runtime'] != runtime:
            raise ValueError('Checkpoint does not belong to the selected QEMU binary')
        report.update({'schema': 'lemmasim-fast-state-observation/1', 'qemu': version,
                       'observer_sha256': sha(Path(__file__).read_bytes()),
                       'left': str(args.left.resolve()), 'right': str(args.right.resolve())})
        if args.mutation_checks:
            report['mutation_checks'] = mutation_checks(args.left.read_bytes())
    except (ValueError, KeyError, TypeError, OSError, struct.error, subprocess.SubprocessError) as error:
        report = {'schema': 'lemmasim-fast-state-observation/1', 'status': 'FAIL', 'error': str(error)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(report['status'] + ': ' + str(args.output))
    return report['status'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
