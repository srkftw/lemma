"""The host worker policy cannot silently rewrite an archived export command."""
import copy
import hashlib
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from core0_common import Core0Error
from lean_export_host import (SOURCE, arguments, command, policy,
                              validate_commands, validate_provenance, for_source, environment, V1_SOURCE_SHA256)


class ExportHostPolicy(unittest.TestCase):
    def test_current_source_requires_literal_version_and_historical_source_forbids_it(self):
        record = policy()
        source_digest = hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest()
        self.assertEqual(validate_provenance(record, {SOURCE: source_digest}), record)
        self.assertIsNone(validate_provenance(None, {'historical-source': 'old'}))
        with self.assertRaises(Core0Error):
            validate_provenance(None, {SOURCE: source_digest})
        with self.assertRaises(Core0Error):
            validate_provenance(record, {'historical-source': 'old'})

    def test_unknown_worker_schema_and_extra_field_cannot_enter_audit(self):
        for change in ({'workers': 4}, {'workers': 2.0}, {'workers': '2'},
                       {'schema': 'lemma-lean-export-host/3'},
                       {'argument': '-j4'}, {'extra': 'ignored'}):
            with self.subTest(change=change), self.assertRaises(Core0Error):
                arguments(policy() | change)
        with self.assertRaises(Core0Error):
            arguments({})

    def test_current_and_historical_invocations_are_exact_and_not_interchangeable(self):
        old = [{'argv': ['/pinned/bin/lake', 'env', 'lean', 'Export.lean']}]
        current = [{'argv': ['/pinned/bin/lake', 'env', 'lean', '-j2', 'Export.lean'], 'host_environment': environment(policy())}]
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

    def test_v1_source_policy_and_commands_remain_exact(self):
        old = policy(1)
        self.assertEqual(validate_provenance(old, {SOURCE: V1_SOURCE_SHA256}), old)
        validate_commands([{'argv': ['/pin/lake', 'env', 'lean', '-j2', 'Export.lean']}], old)
        with self.assertRaises(Core0Error):
            validate_provenance(policy(), {SOURCE: V1_SOURCE_SHA256})
        with self.assertRaises(Core0Error):
            validate_provenance(old, {SOURCE: 'unknown'})

    def test_stack_and_worker_environment_are_exact_for_all_lake_commands(self):
        rows = [{'argv': ['/pin/lake', 'env', 'lean', '-j2', 'Export.lean'],
                 'host_environment': environment(policy())},
                {'argv': ['/pin/lake', 'build', 'Module'],
                 'host_environment': environment(policy())}]
        validate_commands(rows, policy())
        for changed in (None, {}, {'LEAN_NUM_THREADS': '2'},
                        environment(policy()) | {'LEAN_STACK_SIZE_KB': '1048576'}):
            bad = copy.deepcopy(rows)
            if changed is None:
                del bad[1]['host_environment']
            else:
                bad[1]['host_environment'] = changed
            with self.subTest(changed=changed), self.assertRaises(Core0Error):
                validate_commands(bad, policy())
        with self.assertRaises(Core0Error):
            validate_commands(rows, policy(1))

    def test_invoker_applies_and_records_override_without_recording_other_environment(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from build_kernel import command_invoker
        rows = []
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as temporary:
            out = Path(temporary)
            with patch('build_kernel.run_bounded', return_value=SimpleNamespace(
                    returncode=0, elapsed_seconds=.01, stdout=b'actual', stderr=b'')) as invoke:
                run = command_invoker(ROOT, out, {'lake': '/pinned/bin/lake'}, 3, rows)
                self.assertEqual(run(('lake', 'build', 'Module'), ROOT,
                    {'LEAN_NUM_THREADS': '128', 'LEAN_STACK_SIZE_KB': '1048576', 'OTHER': 'kept'}), b'actual')
                self.assertEqual(invoke.call_args.kwargs['env'],
                    environment(policy()) | {'OTHER': 'kept'})
            self.assertEqual(rows[0]['host_environment'], environment(policy()))
            self.assertNotIn('OTHER', str(rows))
