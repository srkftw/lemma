"""Literal allocator/descriptor contradictions for the read-only observer."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('owned_memory', ROOT / 'conformance/lemmasim/check_owned_memory.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def fixture():
    rows = [(0, 0, 0, 0)] * 8192
    rows[0] = (1, 1, 0, 1)  # Task table
    rows[1] = (1, 1, 0, 1)  # Descriptor
    rows[2] = (3, 2, 1, 1)  # Sv39 root
    for index in range(3, 11):
        rows[index] = (3, 1, 0, 1)
    rows[11] = (3, 4, 1, 1)
    descriptor = bytearray(4096)
    values = {0: 0x31534150414D454C, 8: 2, 16: 8193, 24: 3, 32: 1,
              40: 13, 48: 1, 56: 8194, 64: 0x82002000,
              72: 0x8000000000082002, 80: 1024, 88: 32, 128: 8194, 1408: 8}
    for index in range(8):
        values[1424 + index * 16] = 8195 + index
        values[1432 + index * 16] = 0x82003000 + index * 4096
    for offset, value in values.items():
        struct.pack_into('<Q', descriptor, offset, value)
    pages = [bytearray(4096) for _ in range(8)]
    # Fixed literal PTE: physical0x8200b000, U/R/W/A/D and no X.
    # Registry v2 literal byte layout: VA, handle, exact PTE, permissions.
    struct.pack_into('<4Q', pages[0], 0, 0x40000, 8203, 0x20802CD7, 3)
    return rows, bytes(descriptor), [bytes(page) for page in pages]


class OwnedMemory(unittest.TestCase):
    def test_exact_fixed_pool_accounting(self):
        rows, _, _ = fixture()
        data = b''.join(struct.pack('<4Q', *row) for row in rows)
        result = observer.check_accounting((8192, 8192, 4), 8180, 8180, data)
        self.assertEqual(result['allocated_or_retired_frames'], 12)
        self.assertEqual(result['allocated_or_retired_bytes'], 49152)
        self.assertEqual(result['owner_frame_counts'], {'1': 2, '3': 10, '0': 8180})
        self.assertEqual(result['owned_mapping_count'], 2)
        for before, after in ((8179, 8180), (8180, 8179), (8193, 8193), (0, 0)):
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                observer.check_accounting((8192, 8192, 4), before, after, data)
        for config in ((512, 32, 4), (8192, 32, 4), (8192, 8192, 2)):
            with self.assertRaises(ValueError): observer.check_accounting(config, 8180, 8180, data)
        for shortened in (data[:-1], data + bytes(32), b''):
            with self.assertRaises(ValueError): observer.check_accounting((8192, 8192, 4), 8180, 8180, shortened)

    def test_free_live_retired_generation_and_purpose_contradictions(self):
        rows, _, _ = fixture()
        for row in ((0, 1, 0, 0), (0, 0, 1, 0), ((1 << 64) - 1, 2, 0, 1),
                    (3, 0, 0, 1), (3, 6, 0, 1), (3, 4, 0, 0), (3, 4, 0, 1 << 63)):
            changed = list(rows); changed[11] = row
            with self.subTest(row=row), self.assertRaises(ValueError):
                observer.decode_rows(b''.join(struct.pack('<4Q', *record) for record in changed))
        retired = [(0, 0, 0, 0)] * 8192
        retired[1] = ((1 << 64) - 1, 0, 0, 1)
        result = observer.check_accounting((8192, 8192, 4), 8191, 8191,
                    b''.join(struct.pack('<4Q', *record) for record in retired))
        self.assertEqual(result['retired_frames'], 1)
        self.assertEqual(result['live_owned_frames'], 0)

    def test_exact_descriptor_generation_owner_root_and_registry(self):
        rows, descriptor, pages = fixture()
        context = observer.descriptor_context(descriptor, 8193, rows)
        self.assertEqual(context['physical'], 0x82001000)
        self.assertEqual(context['leaf_capacity'], 1024)
        self.assertEqual(context['registry'][7], {'handle': 8202, 'physical': 0x8200A000})
        self.assertEqual(observer.check_leaf_registry(context, pages, rows)['observed_live_leaf_rows'], 1)
        for offset, value in ((8, 1), (16, 8194), (24, 0), (32, 0), (40, 33),
                              (48, 1025), (56, 8195), (64, 0x82003000), (72, 0),
                              (80, 32), (88, 33), (1408, 7), (1432, 0x82004000)):
            changed = bytearray(descriptor); struct.pack_into('<Q', changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                observer.descriptor_context(bytes(changed), 8193, rows)
        duplicate = bytearray(descriptor)
        struct.pack_into('<2Q', duplicate, 1440, 8195, 0x82003000)
        with self.assertRaises(ValueError): observer.descriptor_context(bytes(duplicate), 8193, rows)
        for record in ((4, 1, 0, 1), (3, 4, 0, 1), (3, 1, 1, 1), (3, 1, 0, 2)):
            changed = list(rows); changed[3] = record
            with self.assertRaises(ValueError): observer.descriptor_context(descriptor, 8193, changed)

    def test_leaf_registry_exact_bounds_permissions_pte_and_owner(self):
        rows, descriptor, pages = fixture(); context = observer.descriptor_context(descriptor, 8193, rows)
        for field, value in ((0, 0x40001), (0, 0x40000000), (1, 16395), (3, 5), (2, 0x20802CD6)):
            changed = list(pages); first = bytearray(changed[0]); struct.pack_into('<Q', first, field * 8, value); changed[0] = bytes(first)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                observer.check_leaf_registry(context, changed, rows)
        # Swapping the actual ABI's PTE and permissions must fail. This was the
        # first real observer defect and is preserved as a substantive negative.
        swapped = list(pages); first = bytearray(swapped[0])
        struct.pack_into('<2Q', first, 16, 3, 0x20802CD7); swapped[0] = bytes(first)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            observer.check_leaf_registry(context, swapped, rows)
        context['mapped_leaf_rows'] = 2
        changed = list(pages); first = bytearray(changed[0]); first[32:64] = first[:32]; changed[0] = bytes(first)
        with self.assertRaises(ValueError): observer.check_leaf_registry(context, changed, rows)
        with self.assertRaises(ValueError): observer.check_leaf_registry(context, pages[:-1], rows)

    def test_selected_literal_call_closure_rejects_hidden_page_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); unit = root / 'users/notebook'; unit.mkdir(parents=True)
            functions = [{'source': 'Lemma.Applications.Notebook.' + name, 'symbol': name}
                         for name in ('appendRaw', 'renderPair', 'loadPage')]
            (unit / 'unit.json').write_text(json.dumps({'functions': functions}))
            (unit / 'program.ll').write_text('define i64 @appendRaw() {\n call i64 @renderPair()\n ret i64 0\n}\n'
                                             'define i64 @renderPair() {\n ret i64 0\n}\n')
            metadata = {'notebook': {'path': str(root / 'image.elf')}}
            self.assertEqual(len(observer.source_path_observations(metadata)['observations']), 2)
            complete = (unit / 'program.ll').read_text()
            (unit / 'program.ll').write_text('define i64 @appendRaw() {\n ret i64 0\n}\n')
            with self.assertRaises(ValueError): observer.source_path_observations(metadata)
            (unit / 'program.ll').write_text(complete)
            with (unit / 'program.ll').open('a') as stream:
                stream.write('define i64 @loadPage() {\n ret i64 0\n}\n')
            changed = (unit / 'program.ll').read_text().replace('call i64 @renderPair()', 'call i64 @loadPage()')
            (unit / 'program.ll').write_text(changed)
            with self.assertRaises(ValueError): observer.source_path_observations(metadata)

    def test_bounded_reads_periodic_slice_and_final_before_quit(self):
        rows, descriptor, pages = fixture(); table = bytearray(4096)
        struct.pack_into('<2Q', table, 0, 8193, 3)
        data = {0x804006A0: struct.pack('<3Q', 8192, 8192, 4), 0x80400100: struct.pack('<Q', 8180),
                0x0200BFF8: struct.pack('<Q', 100), 0x80400728: struct.pack('<Q', 8192),
                0x82000000: bytes(table), 0x82001000: descriptor,
                0x80401000: b''.join(struct.pack('<4Q', *row) for row in rows)}
        data.update({0x82003000 + i * 4096: page for i, page in enumerate(pages)})
        commands = []
        class Sim:
            def document_observations(self, serial): return {'ready': True}
            def qmp(self, socket, command, arguments=None):
                commands.append((command, arguments))
                if command == 'quit': return {}
                if command != 'pmemsave': raise AssertionError('non-read observer command')
                address, size = arguments['val'], arguments['size']
                for base, blob in data.items():
                    if base <= address and address + size <= base + len(blob):
                        Path(arguments['filename']).write_bytes(blob[address - base:address - base + size]); return {}
                raise AssertionError('unknown physical read')
        with tempfile.TemporaryDirectory() as tmp, patch.object(observer, 'source_path_observations', return_value={'scope': 'literal test'}):
            sim = Sim()
            value = observer.Observation(sim, Path(tmp) / 'run', Path(tmp) / 'memory', {'notebook': {'sha256': 'literal'}})
            value.socket = Path('literal.qmp')
            value.snapshot('guest-ready', full=True)
            value.snapshot('periodic', full=False)
            value.qmp(value.socket, 'quit')
            result = value.require_observed()
            self.assertEqual(result['status'], 'OBSERVED')
            self.assertTrue(result['final_before_reap_observed'])
            self.assertEqual(result['max_observed_allocated_or_retired_bytes'], 49152)
            self.assertEqual(value.samples[1]['ownership_slice_bytes'], 65536)
            self.assertTrue(all(args['size'] <= 65536 for command, args in commands if command == 'pmemsave'))
            self.assertEqual(commands[-1][0], 'quit')
            with self.assertRaises(ValueError): value.read(0x80401000, 65537, 'too-large')
            value.final = False
            with self.assertRaises(ValueError): value.require_observed()
            quick = observer.Observation(sim, Path(tmp) / 'quick-run', Path(tmp) / 'quick-memory', {'notebook': {'sha256': 'literal'}})
            quick.qmp(Path('quick.qmp'), 'quit')
            self.assertEqual(quick.require_observed()['status'], 'OBSERVED')
            self.assertEqual([row['label'] for row in quick.samples],
                             ['guest-ready-at-final-boundary', 'final-before-process-reap'])

    def test_workload_hook_is_optional_and_observation_failure_propagates(self):
        spec = importlib.util.spec_from_file_location('owned_memory_workflow', ROOT / 'scripts/check_lemmasim.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        calls = []
        class Observation:
            def __init__(self, sim, run, output, metadata):
                calls.append(('construct', run, output))
            def __enter__(self): calls.append(('enter',)); return self
            def __exit__(self, *_): calls.append(('exit',))
            def require_observed(self): raise ValueError('literal contradictory memory accounting')
        import check_owned_memory
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(check_owned_memory, 'Observation', Observation), \
             patch.object(checker, 'generate', return_value=(b'', {'input_samples': 0,
                          'actions':[{'kind':'tool','button':7},{'kind':'tool','button':8}]})), \
             patch.object(checker.sim, 'launch', return_value={'status': 'OBSERVED_GUEST_WORKFLOW_BOUNDARY', 'process_reaped': True}) as launch:
            root = Path(tmp); initial = root / 'initial.raw'; initial.write_bytes(bytes(512))
            with self.assertRaisesRegex(ValueError, 'contradictory memory'):
                checker.workflow({}, initial, 'workload', '1650x2200', root, 3000, observe_owned_memory=True)
            self.assertEqual([row[0] for row in calls], ['construct', 'enter', 'exit'])
            self.assertEqual(calls[0][1:], (root / 'workload/run', root / 'workload/owned-memory'))
            self.assertEqual(launch.call_args.kwargs['until_confirmations'],2)
            calls.clear()
            with self.assertRaisesRegex(ValueError, 'unknown raw fixture'):
                checker.workflow({}, initial, 'basic', '1650x2200', root, 180)
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
