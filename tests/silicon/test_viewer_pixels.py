"""Controller presentation only: no guest document or pen interpretation."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from lemmasim_session import paper_view_pixels, paper_view_ppm


class PaperViewTests(unittest.TestCase):
    def test_each_single_pixel_survives_minification(self):
        for position in range(9):
            with self.subTest(position=position):
                pixels = bytearray(b'\xff' * 9)
                pixels[position] = 0
                self.assertEqual(paper_view_pixels(bytes(pixels), 3, 3, 1, 3), (1, 1, b'\0'))

    def test_partial_right_and_bottom_cells(self):
        pixels = bytes([255] * 19 + [17])
        self.assertEqual(paper_view_pixels(pixels, 5, 4, 1, 3),
                         (2, 2, bytes([255, 255, 255, 17])))

    def test_rgb_and_opaque_legacy_rgba_keep_thin_ink(self):
        gray = bytes([255, 0, 255, 255])
        for channels in (3, 4):
            pixels = b''.join(bytes([value] * 3 + ([255] if channels == 4 else [])) for value in gray)
            self.assertEqual(paper_view_pixels(pixels, 2, 2, channels, 2),
                             (1, 1, b'\0\0\0' + (b'\xff' if channels == 4 else b'')))

    def test_color_selects_existing_pixel_instead_of_inventing_black(self):
        pixels = bytes([255, 0, 0, 0, 255, 0, 255, 255, 255, 255, 255, 255])
        result = paper_view_pixels(pixels, 2, 2, 3, 2)[2]
        self.assertIn(result, [pixels[i:i + 3] for i in range(0, len(pixels), 3)])
        self.assertNotEqual(result, b'\0\0\0')

    def test_transparent_black_does_not_hide_visible_opaque_ink(self):
        pixels = bytes([0, 0, 0, 0, 50, 50, 50, 255])
        self.assertEqual(paper_view_pixels(pixels, 2, 1, 4, 2), (1, 1, bytes([50, 50, 50, 255])))

    def test_full_scale_is_exact_and_input_is_immutable(self):
        data = bytes(range(24))
        self.assertEqual(paper_view_pixels(data, 3, 2, 4, 1), (3, 2, data))
        self.assertEqual(data, bytes(range(24)))

    def test_p5_and_p6_controller_frames(self):
        self.assertEqual(paper_view_ppm(b'P5\n2 2\n255\n\xff\0\xff\xff', 2),
                         b'P5\n1 1\n255\n\0')
        self.assertEqual(paper_view_ppm(b'P6\n2 1\n255\n\xff\xff\xff\0\0\0', 2),
                         b'P6\n1 1\n255\n\0\0\0')

    def test_first_raster_byte_whitespace_and_header_comments(self):
        data = b'P5\n# actual frame comment\n1 1\n255\n\n'
        self.assertEqual(paper_view_ppm(data, 1), b'P5\n1 1\n255\n\n')

    def test_crlf_header_and_nondivisible_geometry(self):
        data = b'P5\r\n5 1\r\n255\r\n\xff\xff\0\xff\x11'
        self.assertEqual(paper_view_ppm(data, 3, (5, 1)), b'P5\n2 1\n255\n\0\x11')

    def test_invalid_geometry_and_payload_reject(self):
        for width, height, channels, scale in [(0, 1, 1, 1), (1, 4097, 1, 1),
                                              (True, 1, 1, 1), (1, 1, True, 1),
                                              (1, 1, 2, 1), (1, 1, 1, 17)]:
            with self.subTest(geometry=(width, height, channels, scale)):
                with self.assertRaises(ValueError):
                    paper_view_pixels(b'\xff', width, height, channels, scale)
        with self.assertRaises(ValueError):
            paper_view_pixels(b'\xff', 2, 2, 1, 2)

    def test_malformed_or_wrong_machine_frame_rejects(self):
        for data in [b'P6\n1 1\n65535\nabc', b'P6\n1 1\n255\nab',
                     b'P6\n1 1\n255\nabcd', b'P5\n# no newline',
                     b'P5\n' + b' ' * 4100 + b'1 1\n255\n\0']:
            with self.subTest(data=data[:40]):
                with self.assertRaises(ValueError):
                    paper_view_ppm(data, 2)
        with self.assertRaises(ValueError):
            paper_view_ppm(b'P5\n1 1\n255\n\0', 2, (2, 2))


if __name__ == '__main__':
    unittest.main()
