"""Literal quarantine/observer checks, not a compiled-guest experiment."""
from importlib.machinery import SourceFileLoader
import importlib.util
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
loader = SourceFileLoader('literal_input_negative', str(ROOT / 'scripts/check_lemmasim_input_negative.py'))
spec = importlib.util.spec_from_loader(loader.name, loader)
negative = importlib.util.module_from_spec(spec)
loader.exec_module(negative)


def source():
    # Independent reviewed shape, with a matching-looking count write outside
    # the mutation declaration. This is never compiled into the trusted guest.
    return ('def other : Action :=\n  ' + negative.BEFORE + '\n  .done 0 0\n\n'
            'private def cancelInput : Action :=\n'
            '  .bind (put 104 0) fun s _ => if statusFailed s = true then .done s 0 else\n'
            '  .bind (put 112 0) fun s _ => if statusFailed s = true then .done s 0 else\n'
            '  .bind (put 296 0) fun s _ => if statusFailed s = true then .done s 0 else\n'
            '  .bind (put 304 0) fun s _ => if statusFailed s = true then .done s 0 else\n'
            '  .bind (put 408 0) fun s _ => if statusFailed s = true then .done s 0 else\n'
            '  put 432 1\n\n'
            'def following : Action := .done 0 0\n')


class InputNegative(unittest.TestCase):
    def test_mutation_is_one_count_clear_in_exact_cancel_declaration(self):
        original = source()
        changed = negative.mutate_source(original)
        self.assertEqual(changed.count(negative.BEFORE), 1)
        self.assertEqual(changed.count(negative.AFTER), 1)
        self.assertEqual(changed.replace(negative.AFTER, negative.BEFORE), original)
        self.assertEqual(changed.split(negative.DECLARATION)[0], original.split(negative.DECLARATION)[0])
        self.assertTrue(changed.endswith('def following : Action := .done 0 0\n'))
        self.assertIn('.bind (put 104 0)', changed)
        self.assertIn('put 432 1', changed)
        for wrong in (original.replace(negative.DECLARATION, 'def cancelInput : Action :=\n'),
                      original + original, original.replace('  put 432 1', '  put 432 0'),
                      original.replace('  .bind (put 112 0)', '  .bind (put 112 1)'),
                      original.replace('  .bind (put 104 0)', '  .bind (put 104 1)'),
                      original[:original.index('\n\ndef following')]):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                negative.mutate_source(wrong)

    def test_generic_failure_or_only_source_hash_change_cannot_pass(self):
        actual = {'retained_cancelled_samples': 8, 'objects': [{'object_id': 65537}]}
        for observed in ({'status': 'PASS'}, {'status': 'FAIL', 'error': 'source hash differs'},
                         {'status': 'FAIL', 'error': 'guest process timed out'},
                         {'status': 'FAIL', 'error': 'missing or truncated raw device ingress'}):
            with self.subTest(observed=observed), self.assertRaises(ValueError):
                negative.require_oracle_rejection(observed, actual)
        rejected = {'status': 'FAIL', 'error': 'completed stroke has no original pen-up'}
        for wrong in ({'retained_cancelled_samples': 0, 'objects': []},
                      {'retained_cancelled_samples': 9, 'objects': [{}]},
                      {'retained_cancelled_samples': 8, 'objects': []}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                negative.require_oracle_rejection(rejected, wrong)
        negative.require_oracle_rejection(rejected, actual)
        negative.require_oracle_rejection(rejected, {'retained_cancelled_samples': 1, 'objects': [{}]})

    def test_actual_tuple_extraction_requires_admitted_cancelled_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw, manifest = negative.generate('loss-disconnect', 1650, 2200, 200000000, 100000, 200000000)
            raw_file = root / 'input.bin';raw_file.write_bytes(raw)
            disk = root / 'literal.disk';disk.write_bytes(b'literal observer input, not guest evidence')
            device = root / 'devices'
            loss = manifest['expected']['loss']
            tuples, lines = [], []
            for ordinal in range(loss['cancelled_first_sequence'], loss['boundary_first_sequence']):
                sample = struct.unpack_from('<9Q', raw, (ordinal - 1) * 72)
                tuples.append((ordinal - 1, *sample[1:8], 2))
                lines.append(f'{sample[1]*100} pen-input {ordinal} {ordinal-1} 2\n')
            device.write_text(''.join(lines))
            header = [0] * 16
            header[:3] = [0x314B4E49414D454C, 1, 3]
            header[4] = 14;header[6] = 8;header[14] = 3
            data = struct.pack('<16Q', *header) + b''.join(struct.pack('<9Q', *row) for row in tuples)
            record = SimpleNamespace(payload=data, kind=1)
            with patch.object(negative, 'recover', return_value=(SimpleNamespace(generation=2), 11, {(1,65537):record})):
                observation = negative.cancelled_records(disk, raw_file, manifest, device)
                self.assertEqual(observation['retained_cancelled_samples'], 8)
                self.assertEqual(observation['objects'][0]['lifecycle'], 3)
                negative.require_oracle_rejection({'status':'FAIL','error':'completed stroke has no original pen-up'}, observation)
                device.write_text(''.join(lines[1:]))
                with self.assertRaisesRegex(ValueError, 'never actually entered the FIFO'):
                    negative.cancelled_records(disk, raw_file, manifest, device)
            device.write_text(''.join(lines))
            with patch.object(negative, 'recover', return_value=(SimpleNamespace(generation=1), 5, {})):
                positive = negative.cancelled_records(disk, raw_file, manifest, device)
                self.assertEqual(positive['retained_cancelled_samples'], 0)
            raw_file.write_bytes(raw[:-1])
            with self.assertRaisesRegex(ValueError, 'changed/truncated'):
                negative.cancelled_records(disk, raw_file, manifest, device)

    def test_independent_lifecycle_rejects_the_retained_contact_without_pen_up(self):
        # Literal behavioural rejection uses the independent lifecycle observer,
        # never a production cancel/transition function or changed source hash.
        from check_notebook_workflow import join_chunks
        header = [0] * 16;header[14] = 3
        contact = (26, 400000000, 49151, 49151, 2048, 3, 1, 0, 2)
        with self.assertRaisesRegex(ValueError, 'completed stroke has no original pen-up'):
            join_chunks([(tuple(header), [contact])])
        up = (27, 400100000, 49151, 49151, 0, 2, 1, 0, 2)
        self.assertEqual(join_chunks([(tuple(header), [contact, up])]), [contact, up])


if __name__ == '__main__':
    unittest.main()
