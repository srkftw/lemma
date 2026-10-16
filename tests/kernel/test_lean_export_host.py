"""The host worker policy cannot silently rewrite an archived export command."""
import copy
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from core0_common import Core0Error
from lean_export_host import (SOURCE, arguments, command, policy,
                              validate_commands, validate_provenance, for_source)


class ExportHostPolicy(unittest.TestCase):
    def test_current_source_requires_literal_version_and_historical_source_forbids_it(self):
        record = {'schema': 'lemma-lean-export-host/1', 'workers': 2,
                  'argument': '-j2', 'scope': 'host Lean export worker pool only'}
        self.assertEqual(validate_provenance(record, {SOURCE: 'bound-by-source-audit'}), record)
        self.assertIsNone(validate_provenance(None, {'historical-source': 'old'}))
        with self.assertRaises(Core0Error):
            validate_provenance(None, {SOURCE: 'bound-by-source-audit'})
        with self.assertRaises(Core0Error):
            validate_provenance(record, {'historical-source': 'old'})

    def test_unknown_worker_schema_and_extra_field_cannot_enter_audit(self):
        for change in ({'workers': 4}, {'workers': 2.0}, {'workers': '2'},
                       {'schema': 'lemma-lean-export-host/2'},
                       {'argument': '-j4'}, {'extra': 'ignored'}):
            with self.subTest(change=change), self.assertRaises(Core0Error):
                arguments(policy() | change)
        with self.assertRaises(Core0Error):
            arguments({})

    def test_current_and_historical_invocations_are_exact_and_not_interchangeable(self):
        old = [{'argv': ['/pinned/bin/lake', 'env', 'lean', 'Export.lean']}]
        current = [{'argv': ['/pinned/bin/lake', 'env', 'lean', '-j2', 'Export.lean']}]
        validate_commands(old, None)
        validate_commands(current, policy())
        self.assertEqual(command(Path('Export.lean'), source_root=ROOT),
                         ('lake', 'env', 'lean', '-j2', 'Export.lean'))
        with self.assertRaises(Core0Error):
            validate_commands(old, policy())
        with self.assertRaises(Core0Error):
            validate_commands(current, None)
        for replacement in (['-j4', 'Export.lean'], ['Export.lean', '-j2'],
                            ['-j2', '-j2', 'Export.lean'], ['-j2', 'Export.txt']):
            wrong = copy.deepcopy(current)
            wrong[0]['argv'][3:] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(Core0Error):
                validate_commands(wrong, policy())

    def test_archived_construction_preserves_legacy_argv_and_missing_current_helper_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            builder = root / 'scripts/build_kernel.py'
            builder.write_text('# retained historical builder, before resource policy\n')
            self.assertIsNone(for_source(root))
            self.assertEqual(command('Export.lean', source_root=root),
                             ('lake', 'env', 'lean', 'Export.lean'))
            builder.write_text('from lean_export_host import command\n')
            with self.assertRaises(Core0Error):
                for_source(root)
            with self.assertRaises(Core0Error):
                command('Export.lean', source_root=root)

    def test_empty_or_malformed_command_evidence_rejects(self):
        for rows in ([], [None], [{}], [{'argv': []}], [{'argv': [12]}],
                     [{'argv': ['/pinned/bin/lake', 'build', 'Module']} ]):
            with self.subTest(rows=rows), self.assertRaises(Core0Error):
                validate_commands(rows, policy())
