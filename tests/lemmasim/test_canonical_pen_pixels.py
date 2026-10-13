"""Known-answer checks for the corrected independent offline pixel observer."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'conformance/lemmasim'))
from check_canonical_pen_pixels import endpoint,coverage,expected_stroke

SAMPLES=[(2,142809999,13115,32783,1024,3,1,0,1),
         (3,142909999,13513,32843,1216,3,1,0,1),
         (4,143009999,13513,32843,0,2,1,0,1)]

class CanonicalPenPixels(unittest.TestCase):
    def test_writing_area_quantization_known_answer(self):
        # A screen-only quantization gives y1100 and misses the real endpoint.
        self.assertEqual(endpoint(SAMPLES[0],1650,2200),(330,1099))
        self.assertEqual(endpoint(SAMPLES[1],1650,2200),(340,1101))

    def test_complete_short_stroke_known_answer(self):
        pixels,points=expected_stroke(SAMPLES)
        self.assertEqual(points,[[330,1099],[331,1099],[332,1099],
            [333,1100],[334,1100],[335,1100],[336,1100],[337,1100],
            [338,1101],[339,1101],[340,1101]])
        self.assertEqual(len(pixels),1650*2200*3)
        self.assertEqual(pixels[(1100*1650+330)*3:(1100*1650+330)*3+3],bytes([255])*3)

    def test_signed_direction_and_caps(self):
        # Reversal and decreasing pressure must retain a valid centerline;
        # beyond either cap and an off-axis pixel remain outside this brush.
        self.assertTrue(coverage((6,4),(10,4),(2,4),4095,0))
        self.assertFalse(coverage((12,4),(10,4),(2,4),4095,0))
        self.assertFalse(coverage((6,6),(10,4),(2,4),4095,0))
        self.assertTrue(coverage((10,5),(10,4),(10,4),4095,4095))

    def test_wrong_or_incomplete_fixture_rejected(self):
        for field,value in [(2,65536),(4,4096),(5,1),(6,2),(7,1),(8,2)]:
            rows=[list(s) for s in SAMPLES];rows[0][field]=value
            with self.assertRaises(ValueError):expected_stroke(rows)
        with self.assertRaises(ValueError):expected_stroke(SAMPLES,1100,1650)
        with self.assertRaises(ValueError):expected_stroke(SAMPLES[:2])

if __name__=='__main__':unittest.main()
