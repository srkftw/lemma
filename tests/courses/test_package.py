"""Independent package codec and checker-boundary mutation tests."""
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from course_package import PackageError, decode
from build_course_package import source_inputs
from core0_common import Core0Error


def changed(image, offset, value, *, rechecksum=True):
    raw = bytearray(image)
    struct.pack_into('<Q', raw, offset, value)
    if rechecksum:
        raw[80:96] = bytes(16)
        crc = zlib.crc32(raw)
        struct.pack_into('<QQ', raw, 80, crc, crc ^ 0xffffffff)
    return bytes(raw)


class PackageBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        filename = os.environ.get('LEMMA_COURSE_PACKAGE_FILE')
        if not filename:
            raise RuntimeError('LEMMA_COURSE_PACKAGE_FILE must identify a real Lean-published artifact')
        cls.image = Path(filename).read_bytes()

    def test_real_original_reference_material_and_separate_graphs(self):
        course = decode(self.image)
        self.assertEqual((course['identity'], course['edition'], len(course['nodes'])), (1, 1, 8))
        self.assertEqual([node['goal'] for node in course['nodes']], [0, 0, 1, 0, 0, 2, 3, 0])
        self.assertEqual(course['nodes'][2]['logical_prerequisites'], [0])
        self.assertEqual(course['nodes'][2]['pedagogical_prerequisites'], [1])
        self.assertEqual(course['nodes'][3]['logical_prerequisites'], [])
        self.assertEqual(course['nodes'][3]['pedagogical_prerequisites'], [2])
        self.assertIn('5/6', course['nodes'][1]['worked'])
        self.assertIn('Q[x]', course['nodes'][5]['exercise'])
        self.assertIn('Unsupported', course['nodes'][6]['body'])
        self.assertIn('unresolved', course['rights_anchor'])

    def test_integrity_rejects_real_changed_bytes(self):
        raw = bytearray(self.image)
        raw[-1] ^= 1
        with self.assertRaisesRegex(PackageError, 'CRC32'):
            decode(bytes(raw))
        with self.assertRaises(PackageError):
            decode(changed(self.image, 80, 0, rechecksum=False))

    def test_semantic_shape_failures_after_valid_independent_crc(self):
        exercise = 128 + 2 * 192
        for offset, value in [(8, 2), (40, 17), (56, 136), (72, 16385),
                              (exercise + 16, 4), (exercise + 24, 2),
                              (exercise + 32, 2), (exercise + 40, 1),
                              (exercise + 48, 1 << 2), (exercise + 56, 1 << 2),
                              (exercise + 80, 1)]:
            with self.subTest(offset=offset):
                with self.assertRaises(PackageError):
                    decode(changed(self.image, offset, value))

    def test_text_span_alias_and_unclaimed_bytes_reject(self):
        span = struct.unpack_from('<Q', self.image, 96)[0]
        with self.assertRaises(PackageError):
            decode(changed(self.image, 96, span - 1))
        raw = bytearray(self.image)
        first = span & 0xffffffff
        raw[first] = 0x80
        raw[80:96] = bytes(16)
        crc = zlib.crc32(raw)
        struct.pack_into('<QQ', raw, 80, crc, crc ^ 0xffffffff)
        with self.assertRaisesRegex(PackageError, 'text byte'):
            decode(bytes(raw))

    def test_source_archive_rejects_std_prefix_lookalikes(self):
        for module in ('LeanFake', 'InitCourse', 'StdOverride'):
            with self.subTest(module=module), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'tests/courses/Author.lean'
                source.parent.mkdir(parents=True)
                source.write_text('import ' + module + '\n')
                with self.assertRaisesRegex(Core0Error, 'unaccounted upstream module'):
                    source_inputs(root)


if __name__ == '__main__':
    unittest.main()
