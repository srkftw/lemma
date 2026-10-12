"""Independent expected-pixel observer tests; no CPU acceptance claim."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'conformance/lemmasim'))
from notebook_pixels import empty_pixels, check_empty


class CompletePixels(unittest.TestCase):
    def test_literal_geometry_and_footer(self):
        w, h = 512, 320
        pixels = empty_pixels(w, h)
        def gray(x, y):
            return pixels[(y*w+x)*3:(y*w+x)*3+3]
        for x, y, value in ((0, 0, 0), (24, 36, 0), (36, 36, 255),
                            (24, 131, 204), (24, 132, 0),
                            (100, 148, 0), (24, 180, 204),
                            (100, 180, 221), (100, 181, 255)):
            self.assertEqual(gray(x, y), bytes([value])*3)
        self.assertEqual(check_empty(w, h, pixels)['pixels'], w*h)

    def test_full_output_and_state_mutations_reject(self):
        p = bytearray(empty_pixels(513, 321))
        p[-1] ^= 17
        with self.assertRaises(ValueError):
            check_empty(513, 321, p)
        with self.assertRaises(ValueError):
            check_empty(513, 321, empty_pixels(513, 321, status='PENDING'))
        for args in ((511, 320), (512, 319), (4097, 320)):
            with self.assertRaises(ValueError):
                empty_pixels(*args)


if __name__ == '__main__':
    unittest.main()
