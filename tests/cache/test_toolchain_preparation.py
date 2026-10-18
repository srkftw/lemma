"""Negative receipts cannot substitute for immutable source/tool preparation."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import toolchain_preparation as preparation
from core0_common import Core0Error
from build_kernel import LEAN_SOURCE_EXPRESSION


class PreparationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.pin = json.loads((ROOT / 'tooling/toolchain-lock.json').read_text())
        self.identities = {}
        for name in preparation.TOOLS:
            key = ('lean' if name in ('lean', 'lake') else 'qemu' if name == 'qemu-system-riscv64'
                   else 'lld' if name == 'ld.lld' else 'llvm')
            store = (self.pin['tools']['llvm']['outputs']['clang_unwrapped']['store_path'] if name == 'clang'
                     else self.pin['tools'][key]['store_path'])
            self.identities[name] = {'path': store + '/bin/' + name,
                                     'invoked_as': store + '/bin/' + name, 'sha256': '0' * 64}
        self.rows = [{'argv': [self.identities[name]['invoked_as'], '--version'], 'cwd': '.',
                      'returncode': 0, 'stdout': expected + '\n', 'stderr': ''}
                     for name, expected in preparation.VERSIONS.items()]
        source = self.pin['tools']['lean']
        self.rows += [
            {'argv': [self.identities['nix']['invoked_as'], 'build', '--no-link', '--print-out-paths', '--impure', '--expr', LEAN_SOURCE_EXPRESSION],
             'cwd': '.', 'returncode': 0, 'stdout': source['source_path'] + '\n', 'stderr': ''},
            {'argv': [self.identities['nix']['invoked_as'], 'path-info', '--json', source['source_path']],
             'cwd': '.', 'returncode': 0, 'stdout': json.dumps({source['source_path']: {'narHash': source['source_sha256'], 'narSize': source['source_nar_size']}}), 'stderr': ''}]
        self.result = {'schema': preparation.SCHEMA,
                       'versions': {name: {'path': self.identities[name]['invoked_as'], 'version': expected}
                                    for name, expected in preparation.VERSIONS.items()},
                       'lean_source_realization': {}}

    def reject(self, expected):
        with self.assertRaisesRegex(Core0Error, expected):
            preparation._validate(self.result, self.pin, self.identities, self.rows)

    def test_missing_original_command_rejects_before_source_admission(self):
        self.rows.pop()
        self.reject('complete actual command')

    def test_reordered_original_queries_reject(self):
        self.rows[0], self.rows[1] = self.rows[1], self.rows[0]
        self.reject('command order')

    def test_changed_version_stdout_cannot_retain_success(self):
        self.rows[0]['stdout'] = 'unexpected compiler\n'
        self.reject('version observation')

    def test_changed_source_nar_cannot_retain_success(self):
        source = self.pin['tools']['lean']['source_path']
        self.rows[-1]['stdout'] = json.dumps({source: {'narHash': 'wrong', 'narSize': 1}})
        self.reject('source NAR differs')

    def test_corrupt_materialized_receipt_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / 'toolchain-admission.json').write_text('{}')
            (out / 'toolchain-preparation.json').write_text('{}')
            row = {'route': preparation.SCHEMA, 'admission': 'toolchain-admission.json',
                   'admission_sha256': '0' * 64, 'result': 'toolchain-preparation.json',
                   'result_sha256': '0' * 64}
            with self.assertRaisesRegex(Core0Error, 'missing or changed'):
                preparation.admitted_commands(row, root=ROOT, output_dir=out)


if __name__ == '__main__':
    unittest.main()
