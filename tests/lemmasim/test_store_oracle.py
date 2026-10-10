"""Independent format examples; observed production-Action disks are checked separately."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lemma_store_oracle", ROOT / "conformance/lemmasim/store_oracle.py")
oracle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = oracle
spec.loader.exec_module(oracle)


def sector(fields):
    prefix = struct.pack("<" + "Q" * len(fields), *fields)
    check = oracle.fnv(prefix)
    return prefix + struct.pack("<QQ", check, check ^ oracle.MASK) + bytes(512 - len(prefix) - 16)


def fixture():
    image = bytearray(4096 * 512)
    image[:512] = sector([oracle.ROOT, 1, 1, 4096, 0, 8, 2044, 0, 0, 0])
    image[512:1024] = image[:512]
    payload = b"record payload"
    body_hash = oracle.fnv(payload)
    image[8 * 512:9 * 512] = sector([oracle.RECORD, 1, 1, 7, 9, 1, 1, len(payload), 1, 1, body_hash])
    image[9 * 512:9 * 512 + len(payload)] = payload
    header_hash = struct.unpack_from("<Q", image, 8 * 512 + 88)[0]
    image[10 * 512:11 * 512] = sector([oracle.COMMIT, 1, 1, 7, 9, 1, 1, len(payload), 1, body_hash, header_hash])
    return image


class StoreOracleTests(unittest.TestCase):
    def test_literal_checksum(self):
        self.assertEqual(oracle.fnv(b""), 0xcbf29ce484222325)
        self.assertEqual(oracle.fnv(b"a"), 0xaf63dc4c8601ec8c)
        self.assertEqual(oracle.fnv(b"foobar"), 0x85944171f73967e8)

    def test_valid_literal_namespace(self):
        root, sequence, objects = oracle.recover(fixture())
        self.assertEqual(root.generation, 1)
        self.assertEqual(sequence, 1)
        self.assertEqual(objects[(7, 9)].payload, b"record payload")

    def test_torn_publication_excludes_whole_pending_transaction(self):
        image = fixture()
        image[10 * 512 + 99] ^= 1
        _, sequence, objects = oracle.recover(image)
        self.assertEqual(sequence, 0)
        self.assertEqual(objects, {})

    def test_damaged_nonempty_medium_has_no_format_fallback(self):
        with self.assertRaisesRegex(ValueError, "never automatically format"):
            oracle.recover(bytes([42]) * (4096 * 512))

    def test_unknown_mandatory_version_rejects(self):
        image = fixture()
        struct.pack_into("<Q", image, 8, 2)
        with self.assertRaisesRegex(ValueError, "unsupported root version"):
            oracle.recover(image)

    def test_empty_corpus_not_success(self):
        with self.assertRaises(ValueError):
            oracle.recover(b"")

    def test_corrupt_checkpoint_never_becomes_empty_store(self):
        image = fixture()
        image[:512] = sector([oracle.ROOT, 1, 2, 4096, 0, 8, 2044, 1, 3, 1])
        image[512:1024] = image[:512]
        image[8 * 512:9 * 512] = bytes(512)
        with self.assertRaisesRegex(ValueError, "damaged published checkpoint"):
            oracle.recover(image)


if __name__ == "__main__":
    unittest.main()
