#!/usr/bin/env python3
"""The Gate 7 oracle and fixture are independent of compilation artifacts."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate7_corpus as corpus
from core0_common import Core0Error


class TrapCorpusTests(unittest.TestCase):
    def test_closed_cases_repeat_counts_with_different_seeds(self):
        self.assertEqual([case.count for case in corpus.POSITIVE_CASES], [0, 0, 1, 1, 7, 7, 64, 64])
        for count in (0, 1, 7, 64):
            seeds = {case.seed for case in corpus.POSITIVE_CASES if case.count == count}
            self.assertEqual(len(seeds), 2)
        self.assertEqual(len(corpus.NEGATIVE_CASES), 6)
        self.assertEqual(len(corpus.corpus_manifest()["positive_cases"]), 8)

    def test_fixture_is_only_three_runtime_words_no_expected_answers(self):
        case = corpus.TrapCase("fixture", 0x8877665544332211, 7, 4)
        blob = corpus.fixture_bytes(case)
        self.assertEqual(len(blob), 24)
        self.assertEqual(blob[:8], bytes.fromhex("1122334455667788"))
        self.assertEqual(struct.unpack("<QQQ", blob), (case.seed, 7, 4))

    def test_checksum_known_wrap_values_and_zero(self):
        self.assertEqual(corpus.checksum(corpus.U64_MAX, 0), corpus.U64_MAX)
        self.assertEqual(corpus.checksum(1, 1), 0x100000001B3)
        self.assertEqual(corpus.checksum(corpus.U64_MAX, 1), 0xFFFFFEFFFFFFFE4D)
        # Separately expanded two-step unsigned recurrence.
        first = (0x100000001B3 * 0x0123456789ABCDEF) % (1 << 64)
        expected = (((first ^ 1) * 0x100000001B3) + 0x20000) % (1 << 64)
        self.assertEqual(corpus.checksum(0x0123456789ABCDEF, 2), expected)
        self.assertNotEqual(corpus.checksum(0, 64), corpus.checksum(corpus.U64_MAX, 64))

    def test_exact_exit_priority_and_nonempty_mutation(self):
        self.assertEqual([corpus.expected_exit(case) for case in corpus.NEGATIVE_CASES], [18, 18, 19, 9, 16, 14])
        self.assertEqual(corpus.expected_exit(corpus.MUTANT_CASE, mutant=True), 20)
        for case in (corpus.TrapCase("empty", 0, 0), corpus.TrapCase("fatal", 0, 1, 1), corpus.TrapCase("budget", 0, 65)):
            with self.assertRaises(Core0Error):
                corpus.expected_exit(case, mutant=True)

    def test_rejects_host_type_overflow_and_unsafe_names(self):
        for case in (corpus.TrapCase("bad/name", 0, 0), corpus.TrapCase("bad", True, 0),
                     corpus.TrapCase("bad", -1, 0), corpus.TrapCase("bad", 0, 1 << 64)):
            with self.assertRaises(Core0Error):
                corpus.fixture_bytes(case)
        for count in (True, -1, 65):
            with self.assertRaises(Core0Error):
                corpus.checksum(0, count)


if __name__ == "__main__":
    unittest.main()
