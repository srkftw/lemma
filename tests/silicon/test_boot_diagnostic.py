# SPDX-License-Identifier: Apache-2.0
"""Independent literal PC/readiness examples for the developer boot observer."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('boot_diagnostic', ROOT / 'scripts/check_silicon_boot.py')
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class BootDiagnosticTests(unittest.TestCase):
    def test_exact_half_open_ranges_and_ambiguous_user_pc(self):
        text = '''Symbol table '.symtab' contains 5 entries:
   Num:    Value          Size Type    Bind   Vis       Ndx Name
     1: 0000000080200100    16 FUNC    GLOBAL DEFAULT    2 f
     2: 0000000080200110     8 FUNC    LOCAL  DEFAULT    2 g
     3: 0000000080200100    16 OBJECT  GLOBAL DEFAULT    2 data
     4: 0000000000000000     0 FUNC    GLOBAL DEFAULT  UND external
'''
        functions = boot.ranges(text, {'f': 'Lean.f', 'g': 'Lean.g'})
        self.assertEqual(boot.labels(0x80200100, functions), ['Lean.f'])
        self.assertEqual(boot.labels(0x8020010f, functions), ['Lean.f'])
        self.assertEqual(boot.labels(0x80200110, functions), ['Lean.g'])
        self.assertEqual(boot.labels(0x80200118, functions), ['unresolved:0x80200118'])
        self.assertEqual(boot.labels(0, functions), ['unresolved:pc0'])
        self.assertEqual(boot.labels(0x80200100, functions + [(0x80200100,0x80200110,'peer:Lean.h')]),
                         ['Lean.f', 'peer:Lean.h'])

    def test_malformed_or_overflowed_ranges_fail(self):
        for text in ('', '1: 1000 4 OBJECT GLOBAL DEFAULT 1 data',
                     '1: ffffffffffffffff 2 FUNC GLOBAL DEFAULT 1 overflow'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                boot.ranges(text, {})

    def test_ready_needs_actual_guest_record_and_idle_devices(self):
        with tempfile.TemporaryDirectory() as name:
            serial = Path(name) / 'uart.bin'
            serial.write_bytes(b'K1 0000000000000410 0000000000000000 0000000000000000 0000000000000000 0000000000000000\n')
            self.assertFalse(boot.ready(serial, {'paper_busy': 0, 'block_state': 0}))
            serial.write_bytes(serial.read_bytes() + b'K1 0000000000000420 0000000000000001 0000000000000001 0000000000000001 0000000000000000\n')
            self.assertTrue(boot.ready(serial, {'paper_busy': 0, 'block_state': 0}))
            self.assertFalse(boot.ready(serial, {'paper_busy': 0, 'block_state': 0}, serial.stat().st_size))
            self.assertFalse(boot.ready(serial, {'paper_busy': 1, 'block_state': 0}))
            self.assertFalse(boot.ready(serial, {'paper_busy': 0, 'block_state': 1}))
            with self.assertRaises(ValueError):
                boot.read_bounded(serial, 5)


if __name__ == '__main__':
    unittest.main()
