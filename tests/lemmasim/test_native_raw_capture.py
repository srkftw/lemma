"""The native observer compares real seven-word capture, not a fabricated log."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_live_notebook import observe_raw_input
from notebook_input import Input


class NativeRawCapture(unittest.TestCase):
    def setUp(self):
        self.stream = Input(1650, 2200, 12345, 100000, 0)
        self.stream.sample(825, 160, 0, False)
        self.stream.stroke('original', 1, 1, 3, 1200)

    def test_binary_default_retains_all_nine_word_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.bin'
            p.write_bytes(b''.join(struct.pack('<9Q', *r) for r in self.stream.events))
            observe_raw_input(p, self.stream)
            data = bytearray(p.read_bytes()); data[-1] ^= 1; p.write_bytes(data)
            with self.assertRaises(ValueError): observe_raw_input(p, self.stream)

    def test_native_compares_exact_cycle_and_every_raw_field(self):
        rows = [f'{r[1] * 10} pen ' + ' '.join(map(str, r[1:8])) for r in self.stream.events]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.events'; p.write_text('\n'.join(rows) + '\n')
            observe_raw_input(p, self.stream, 'native-seven-text')
            for column in (0, 2, 3, 4, 5, 6, 7, 8):
                bad = rows.copy(); words = bad[1].split(); words[column] = str(int(words[column]) + 1)
                bad[1] = ' '.join(words); p.write_text('\n'.join(bad) + '\n')
                with self.assertRaises(ValueError): observe_raw_input(p, self.stream, 'native-seven-text')
            for bad in (rows[:-1], rows + [rows[-1]], list(reversed(rows)),
                        [rows[0].replace('pen', 'uart')] + rows[1:]):
                p.write_text('\n'.join(bad) + '\n')
                with self.assertRaises(ValueError): observe_raw_input(p, self.stream, 'native-seven-text')
            p.write_text('\n'.join(rows))
            with self.assertRaises(ValueError): observe_raw_input(p, self.stream, 'native-seven-text')
            with self.assertRaises(ValueError): observe_raw_input(p, self.stream, 'unknown')


if __name__ == '__main__': unittest.main()
