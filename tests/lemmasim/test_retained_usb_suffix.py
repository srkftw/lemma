from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_retained_usb_suffix import checkpoint, external_admissions


class RetainedUSBSuffixInputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def image(self):
        data = b'fixture-checkpoint-bytes'
        (self.path / 'machine.chk').write_bytes(data)
        metadata = {'schema': 'lemmasim-session/1',
                    'identity': {'backend': 'rtl', 'profile': 'lemma-silicon-dev/0.8.0'},
                    'virtual_cycle': 100, 'files': [{'path': 'machine.chk', 'bytes': len(data),
                    'sha256': hashlib.sha256(data).hexdigest()}]}
        (self.path / 'snapshot.json').write_text(json.dumps(metadata))
        return metadata

    def row(self, **fields):
        row = {'admission': 'applied', 'cursor': 4, 'ordinal': 4, 'cycle': 110,
               'request': {'action': 'inject', 'kind': 'pen', 'cycle': 115,
                           'words': [11, 12, 13, 14, 15, 16, 17]}}
        row.update(fields)
        return row

    def events(self, rows):
        path = self.path / 'external.jsonl'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return path

    def test_complete_declared_checkpoint(self):
        expected = self.image()
        self.assertEqual(checkpoint(self.path), expected)

    def test_missing_corrupt_and_unlisted_bytes_reject(self):
        self.image()
        for name in ('missing', 'corrupt', 'unlisted'):
            with self.subTest(name=name):
                self.image()
                if name == 'missing': (self.path / 'machine.chk').unlink()
                elif name == 'corrupt': (self.path / 'machine.chk').write_bytes(b'wrong')
                else: (self.path / 'hidden').write_bytes(b'undocumented')
                with self.assertRaises((ValueError, FileNotFoundError)): checkpoint(self.path)
                (self.path / 'hidden').unlink(missing_ok=True)

    def test_scope_and_symlink_reject(self):
        self.image()
        link = self.path.parent / (self.path.name + '-link')
        link.symlink_to(self.path, target_is_directory=True)
        try:
            with self.assertRaises(ValueError): checkpoint(link)
        finally: link.unlink()
        metadata = self.image(); metadata['identity']['profile'] = 'lemma-silicon-dev/0.7.0'
        (self.path / 'snapshot.json').write_text(json.dumps(metadata))
        with self.assertRaises(ValueError): checkpoint(self.path)

    def test_exact_admission_request_is_preserved(self):
        rows = [self.row(), self.row(cursor=5, ordinal=5, cycle=120)]
        rows[1]['request']['cycle'] = 125
        self.assertEqual(external_admissions(self.events(rows), 100, 200, 4), rows)
        self.assertEqual(external_admissions(None, 100, 200, 4), [])

    def test_cursor_order_boundary_and_pending_reject(self):
        for rows in ([self.row(cursor=5)], [self.row(admission='pending')],
                     [self.row(cycle=201)], [self.row(), self.row(cursor=5, cycle=105)],
                     [self.row(), self.row(cursor=5, ordinal=7)]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    external_admissions(self.events(rows), 100, 200, 4)

    def test_only_recorded_raw_pen_requests_are_admitted(self):
        for field, value in (('action', 'warm-reset'), ('kind', 'power'),
                             ('cycle', 100), ('words', [0]), ('words', [-1] * 7)):
            row = self.row(); row['request'][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    external_admissions(self.events([row]), 100, 200, 4)


if __name__ == '__main__': unittest.main()
