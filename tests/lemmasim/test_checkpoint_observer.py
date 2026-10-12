# SPDX-License-Identifier: Apache-2.0
"""Serializer mutation fixtures; these establish observer behavior, not a boot."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'conformance/lemmasim'))
import check_fast_state_equivalence as observer


def section(kind, ident, name, version, payload):
    return bytes([kind]) + struct.pack('>I', ident) + bytes([len(name)]) + name + \
        struct.pack('>II', 0, version) + payload + b'\x7e' + struct.pack('>I', ident)


def fixture(metadata=None):
    size_record = struct.pack('>Q', 4096 | 4) + b'\x03ram' + struct.pack('>Q', 4096)
    ram = section(1, 1, b'ram', 4, size_record + struct.pack('>Q', 16))
    ram += b'\x02' + struct.pack('>I', 1) + struct.pack('>Q', 8) + b'\x03ram' + bytes(4096)
    ram += struct.pack('>Q', 16) + b'\x7e' + struct.pack('>I', 1)
    cpu = section(4, 2, b'cpu', 11, bytes(32 * 8))
    timer = section(4, 0, b'timer', 2, struct.pack('>q', 70) + bytes(8) + struct.pack('>q', 80) +
                    b'\x05\x0ctimer/icount\0\0\0\1' + struct.pack('>qq', 90, 100))
    if metadata is None:
        metadata = {'page_size': 4096, 'devices': [copy.deepcopy(observer.TIMER),
            {'name': 'cpu', 'instance_id': 0, 'version': 11,
             'fields': [{'name': 'env.gpr', 'array_len': 32, 'type': 'uint64', 'size': 8}]}]}
    encoded = json.dumps(metadata).encode()
    return b'QEVM\0\0\0\3\x07\0\0\0\x12lemma-silicon-fast' + ram + cpu + timer + \
        b'\0\x06' + struct.pack('>I', len(encoded)) + encoded


class CheckpointObservation(unittest.TestCase):
    def saved(self, root, name, origin=50, adapter=observer.ADAPTER):
        directory=Path(root)/name;directory.mkdir()
        state=directory/'machine.chk';state.write_bytes(fixture())
        clock=directory/'clock.json'
        clock.write_text(json.dumps({'schema':'lemmasim-fast-clock/1','time_origin_ns':origin}))
        manifest={'schema':'lemmasim-session/1','virtual_ns':1000,'external_event_cursor':0,
            'identity':{'backend':'qemu','runtime':observer.RUNTIME_SHA256,'profile':'lemma-silicon-dev/0.2.0',
                'cpu':observer.CPU,'icount_shift':3,'adapter':adapter},
            'files':[{'path':p.name,'bytes':p.stat().st_size,'sha256':observer.file_sha(p)} for p in (state,clock)]}
        (directory/'snapshot.json').write_text(json.dumps(manifest))
        return state

    def test_clock_origin_mutation_rejected_despite_valid_individual_checksums(self):
        with tempfile.TemporaryDirectory() as root:
            a=self.saved(root,'left');b=self.saved(root,'right',origin=51)
            with self.assertRaisesRegex(ValueError,'wrapper clock'):
                observer.compare_checkpoints(a,b)

    def test_required_clock_state_is_exact_not_only_equivalent_json(self):
        with tempfile.TemporaryDirectory() as root:
            a=self.saved(root,'left');b=self.saved(root,'right')
            self.assertEqual(observer.compare_checkpoints(a,b)['status'],'PASS')
            clock=b.with_name('clock.json');clock.write_text(clock.read_text()+'\n')
            manifest=b.with_name('snapshot.json');data=json.loads(manifest.read_text())
            data['files'][1].update(bytes=clock.stat().st_size,sha256=observer.file_sha(clock))
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'wrapper clock'):
                observer.compare_checkpoints(a,b)

    def test_missing_stale_unknown_or_unbounded_clock_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            a=self.saved(root,'left')
            for index, origin in enumerate((True,-1,1001)):
                b=self.saved(root,'bad'+str(index),origin=origin)
                with self.subTest(origin=origin),self.assertRaisesRegex(ValueError,'clock state'):
                    observer.compare_checkpoints(a,b)
            b=self.saved(root,'unknown',adapter='lemmasim-fast-adapter/3')
            with self.assertRaisesRegex(ValueError,'wrapper version'):
                observer.compare_checkpoints(a,b)
            b=self.saved(root,'missing');b.with_name('clock.json').unlink()
            with self.assertRaisesRegex(ValueError,'missing checkpoint sidecar'):
                observer.compare_checkpoints(a,b)
            b=self.saved(root,'stale');b.with_name('clock.json').write_bytes(b'invalid')
            with self.assertRaisesRegex(ValueError,'sidecar length/checksum'):
                observer.compare_checkpoints(a,b)

    def test_six_named_host_and_guest_field_mutations(self):
        checks = observer.mutation_checks(fixture())
        self.assertEqual({row['field']: row['observed'] for row in checks}, {
            'cpu_ticks_offset': 'PASS', 'cpu_clock_offset': 'PASS',
            'qemu_icount_bias': 'FAIL', 'qemu_icount': 'FAIL',
            'cpu.env.gpr[1]': 'FAIL', 'RAM.first_page.byte[0]': 'FAIL'})

    def test_raw_container_difference_is_retained_and_named(self):
        source = fixture(); position = observer.layout(source)['host_fields'][1][1]
        target = source[:position] + b'\1' + source[position + 1:]
        result = observer.compare(source, target)
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['raw_container_equal'])
        self.assertNotEqual(result['left_sha256'], result['right_sha256'])
        self.assertEqual(result['differences'], [{'start': position, 'end': position + 1,
                         'left_hex': '00', 'right_hex': '01'}])
        self.assertEqual(result['host_statistics'][1]['name'], 'cpu_clock_offset')

    def test_unnamed_private_byte_change_rejected(self):
        source = fixture(); position = observer.layout(source)['cpu_gpr_x1'] + 40
        target = source[:position] + b'\1' + source[position + 1:]
        result = observer.compare(source, target)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['unauthorized_differences'], result['differences'])

    def test_missing_unknown_and_ambiguous_timer_state_rejected(self):
        source = fixture(); info = observer.layout(source)
        altered = [source[:info['icount']] + source[info['icount'] + 8:],
                   source.replace(b'\x05\x0ctimer/icount', b'\x05\x0ctimer/badbad'),
                   source.replace(b'\x05timer', b'\x05other'),
                   source + b'\x04\0\0\0\7\x05timer\0\0\0\0\0\0\0\2']
        for data in altered:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                observer.layout(data)
        # A false section-looking string in RAM must reject ambiguity rather
        # than cause the observer to omit the wrong eight-byte interval.
        header = b'\x04\0\0\0\7\x05timer\0\0\0\0\0\0\0\2'
        position = observer.ram_mutation_offset(source)
        duplicate = source[:position] + header + source[position + len(header):]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            observer.layout(duplicate)

    def test_schema_change_and_terminal_damage_rejected(self):
        source = fixture(); changed = json.loads(source[observer.layout(source)['metadata_start']:])
        changed['devices'][0]['subsections'][0]['fields'].append({'name': 'new', 'type': 'int64', 'size': 8})
        for data in (fixture(changed), source[:-1], source + b'junk'):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                observer.layout(data)

    def test_resource_bound_precedes_schema_decoding(self):
        with mock.patch.object(observer, 'MAX_STATE', 100), self.assertRaises(ValueError):
            observer.layout(fixture())


if __name__ == '__main__':
    unittest.main()
