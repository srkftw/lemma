"""Strict host observer checks for two historical course-font literals.

These fixed pixel fixtures are never supplied to a running guest. They catch
the independent observer's former J/less-than transcription errors.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'conformance/lemmasim')]
import course_pixel_oracle as oracle


class CoursePixelOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.width, cls.height = 1650, 2200
        pixels = bytearray(b'\xff' * (cls.width * cls.height * 3))
        # Published lemma-course-text-panel/1 literals, independent of ROWS.
        for cell, glyph in enumerate((0x124e, 0x1541)):
            for row in range(15):
                for column in range(9):
                    if glyph >> (14 - (row//3)*3 - column//3) & 1:
                        at = ((320+row)*cls.width+24+cell*12+column)*3
                        pixels[at:at+3] = bytes(3)
        cls.pixels = bytes(pixels)

    def test_historical_j_and_less_than_pixels_match_exactly(self):
        with patch.object(oracle, 'visible_pixels', return_value=(self.width, self.height, self.pixels)):
            self.assertTrue(oracle.course_body_matches('unused.ppm', 'j<'))

    def test_old_j_left_hook_and_any_unexpected_pixel_reject(self):
        # Old oracle0x126e demanded an extra black3x3 block in J's fourth row.
        for x, y in ((24, 329), (100, 500)):
            with self.subTest(x=x, y=y):
                changed = bytearray(self.pixels)
                at = (y*self.width+x)*3
                changed[at:at+3] = bytes(3)
                with patch.object(oracle, 'visible_pixels', return_value=(self.width, self.height, bytes(changed))):
                    self.assertFalse(oracle.course_body_matches('unused.ppm', 'J<'))


if __name__ == '__main__':
    unittest.main()
