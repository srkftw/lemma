"""Literal independent observation boundaries for fixed-v1/compact-v2 pages."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'conformance/lemmasim'))
from inspect_notebook import inspect_page


def literal_page(version=2):
    header = struct.pack('<16Q', 0x314B4E49414D454C, version, 2, 16, 2, 2, 1, *([0] * 9))
    entries = struct.pack('<6Q', 65537, 7, 1, 65538, 8, 0)
    edits = struct.pack('<4Q', 1, 7, 1, 8)
    if version == 1:
        return header + entries + bytes(12416 - 128 - len(entries)) + edits + bytes(8192 - len(edits))
    return header + entries + edits


class PageRecordObservation(unittest.TestCase):
    def test_explicit_versions_choose_distinct_exact_offsets(self):
        for version, size in [(1, 20608), (2, 208)]:
            page = literal_page(version)
            self.assertEqual(len(page), size)
            self.assertEqual(inspect_page(page, 272), [(65537, 7, 1), (65538, 8, 0)])

    def test_unknown_or_malformed_content_is_not_reinterpreted(self):
        page = literal_page()
        for offset, value in [(8, 3), (24, 0), (32, 513), (48, 3), (56, 1), (176, 0)]:
            changed = bytearray(page)
            struct.pack_into('<Q', changed, offset, value)
            with self.assertRaises(ValueError):
                inspect_page(changed, 272)
        for changed in [page[:-8], page + bytes(8), literal_page(1)[:208]]:
            with self.assertRaises(ValueError):
                inspect_page(changed, 272)
        with self.assertRaises(ValueError):
            inspect_page(page, 273)


if __name__ == '__main__':
    unittest.main()
