"""Independent literal native-input examples; no production transition oracle."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_ingress', ROOT / 'conformance/lemmasim/check_native_ingress.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class NativeIngress(unittest.TestCase):
    def fixture(self, rejected=True):
        commands = [{'x': 6000, 'y': 8000, 'down': False}]
        commands += [{'x': 6000 + i * 400, 'y': 8000 + i * 250, 'down': True} for i in range(20)]
        commands += [{'x': 13600, 'y': 12750, 'down': False}]
        # Independently written pinned scaling expression, including fixed
        # endpoint examples below. No observer scale/transition calls.
        raw = b''.join(struct.pack('<9Q', i + 1, 5000 + i * 100,
                                  row['x'] * 65535 // 32767, row['y'] * 65535 // 32767,
                                  2047 if row['down'] else 0, 7 if row['down'] else 6, 1, 0, 1)
                       for i, row in enumerate(commands))
        lines = ['0 device-reset 0 2 0']
        for i in range(22):
            sequence = i if rejected else i + 1
            event = 'pen-input-rejected' if rejected and i == 0 else 'pen-input'
            lines.append(f'{(5000 + i * 100) * 100} {event} {i + 1} {sequence} 2')
        plan = {'schema_version': 1, 'source': 'qmp-native-pointer', 'device': 'lemma-hardware', 'commands': commands}
        return plan, raw, '\n'.join(lines) + '\n'

    def run_case(self, plan, raw, trace):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'commands.json').write_text(json.dumps(plan))
            (root / 'raw.bin').write_bytes(raw)
            (root / 'devices.trace').write_text(trace)
            return observer.check(root / 'raw.bin', root / 'commands.json', root / 'devices.trace')

    def test_literal_endpoints_and_capture_provenance(self):
        self.assertEqual([observer.scale_axis(x) for x in (0, 1, 16383, 16384, 32767)], [0, 2, 32766, 32768, 65535])
        plan, raw, trace = self.fixture()
        result, fixture = self.run_case(plan, raw, trace)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['captured_samples'], 22)
        self.assertEqual(result['first_stroke_ingress'], {'sequence': 1, 'epoch': 2, 'time_ns': 510000})
        self.assertEqual(fixture['actions'][0]['first_sequence'], 2)
        self.assertEqual(fixture['actions'][0]['last_sequence'], 22)
        self.assertEqual(fixture['expected']['retained_raw_samples'], 21)
        self.assertEqual(fixture['workflow'], 'native-pointer')
        self.assertEqual(fixture['expected']['final_view'], {'namespace': 1, 'page': 1})
        self.assertEqual(fixture['input_sha256'], result['identity']['raw_sha256'])
        self.assertTrue(result['initial_resync_release_rejected'])
        self.assertFalse(self.run_case(*self.fixture(False))[0]['initial_resync_release_rejected'])

    def test_raw_axis_pressure_flags_tool_buttons_epoch_and_ordinal_reject(self):
        plan, raw, trace = self.fixture()
        for field in (0, 2, 3, 4, 5, 6, 7, 8):
            altered = bytearray(raw)
            current = struct.unpack_from('<Q', altered, 72 + field * 8)[0]
            struct.pack_into('<Q', altered, 72 + field * 8, current + 1)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_case(plan, bytes(altered), trace)

    def test_raw_truncation_extra_backward_time_and_unknown_command_reject(self):
        plan, raw, trace = self.fixture()
        for altered in (raw[:-1], raw + bytes(72), b''):
            with self.assertRaises(ValueError): self.run_case(plan, altered, trace)
        altered = bytearray(raw); struct.pack_into('<Q', altered, 72 + 8, 4999)
        with self.assertRaises(ValueError): self.run_case(plan, bytes(altered), trace)
        for mutation in ('axis', 'button', 'identity', 'shape', 'multiple_strokes'):
            changed = copy.deepcopy(plan)
            if mutation == 'axis': changed['commands'][1]['x'] = 32768
            if mutation == 'button': changed['commands'][1]['down'] = 1
            if mutation == 'identity': changed['device'] = 'other'
            if mutation == 'shape': changed['commands'][1]['pressure'] = 2047
            if mutation == 'multiple_strokes': changed['commands'][5]['down'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): self.run_case(changed, raw, trace)

    def test_missing_duplicate_out_of_order_rejected_contact_and_epoch_reject(self):
        plan, raw, trace = self.fixture()
        lines = trace.splitlines()
        bads = [lines[:-1], lines + [lines[-1]], [lines[0], lines[2], lines[1], *lines[3:]],
                [*lines[:2], lines[2].replace('pen-input 2 1', 'pen-input-rejected 2 0'), *lines[3:]],
                [*lines[:-1], lines[-1][:-1] + '3'], lines + ['9999999 pen-watchdog-loss 2 1 0']]
        for bad in bads:
            with self.assertRaises(ValueError): self.run_case(plan, raw, '\n'.join(bad) + '\n')
        with self.assertRaises(ValueError): self.run_case(plan, raw, trace.replace('510000 pen-input', '510100 pen-input'))


if __name__ == '__main__':
    unittest.main()
