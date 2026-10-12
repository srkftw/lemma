"""Independent authored M rows: a wrong row must fail the live pixel oracle."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from check_math_session import MathChecker


class ReviewPixels(unittest.TestCase):
    def test_exact_m_and_corrupted_row(self):
        # Literal authored font contract: 0x5fed, not read from guest code,
        # FONT_ROWS, machine memory or the production observer's pattern table.
        width,height=12,20
        pixels=bytearray([255])*(width*height*3)
        rows=('101','111','111','101','101')
        for r,row in enumerate(rows):
            for c,bit in enumerate(row):
                if bit=='1':
                    for dy in range(3):
                        for dx in range(3):
                            at=((r*3+dy)*width+c*3+dx)*3
                            pixels[at:at+3]=bytes(3)
        checker=object.__new__(MathChecker)
        with tempfile.TemporaryDirectory() as directory:
            panel=Path(directory)/'literal.ppm'
            panel.write_bytes(b'P6\n12 20\n255\n'+pixels)
            checker.label(panel,'M',0,0)
            # The old observer's erroneous fourth-row center bit is black.
            at=((3*3+1)*width+3+1)*3
            pixels[at:at+3]=bytes(3)
            panel.write_bytes(b'P6\n12 20\n255\n'+pixels)
            with self.assertRaises(ValueError):checker.label(panel,'M',0,0)


if __name__=='__main__':unittest.main()
