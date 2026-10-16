# SPDX-License-Identifier: Apache-2.0
"""Exact wrapper-output authority; no synthetic guest-execution claim."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from package_native import qemu_output_for_launcher, sha


class NativeRuntimeClosureTests(unittest.TestCase):
    def test_wrapper_output_selected_by_actual_bytes_including_debug_output(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            runtime, debug = store / 'runtime', store / 'debug'
            (runtime / 'bin').mkdir(parents=True)
            # Other declared outputs need not be realised in a publisher's
            # store. Never demand or download an unused debug output.
            launcher = runtime / 'bin/qemu-system-riscv64'
            launcher.write_bytes(b'exact locally built wrapper\n')
            self.assertEqual(qemu_output_for_launcher(
                [str(debug), str(runtime)], sha(launcher), store), runtime)
            launcher.write_bytes(b'changed wrapper\n')
            with self.assertRaisesRegex(ValueError, 'unique original output'):
                qemu_output_for_launcher([str(debug), str(runtime)], '0' * 64, store)

    def test_empty_duplicate_ambiguous_and_outside_outputs_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory)
            paths = [store / 'one', store / 'two']
            for path in paths:
                (path / 'bin').mkdir(parents=True)
                (path / 'bin/qemu-system-riscv64').write_bytes(b'same wrapper')
            digest = sha(paths[0] / 'bin/qemu-system-riscv64')
            for outputs in ([], [str(paths[0])] * 2, [str(p) for p in paths],
                            [str(store / 'one/../two')], [str(store.parent)]):
                with self.subTest(outputs=outputs), self.assertRaises(ValueError):
                    qemu_output_for_launcher(outputs, digest, store)


if __name__ == '__main__':
    unittest.main()
