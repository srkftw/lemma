#!/usr/bin/env python3
"""Pure host-input and independent timer-fold oracle tests."""
import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate8_corpus as corpus
from core0_common import Core0Error


class TimerCorpusTests(unittest.TestCase):
    def test_fixture_contains_only_four_runtime_words(self):
        for case in (*corpus.POSITIVE_CASES, *corpus.NEGATIVE_CASES):
            data = corpus.fixture_bytes(case)
            self.assertEqual(len(data), 32)
            self.assertEqual(struct.unpack("<QQQQ", data), (case.seed, case.goal, case.period, case.scenario))
        self.assertEqual(corpus.corpus_manifest()["fixture_bytes"], 32)

    def test_checksum_known_unsigned_wrap_and_global_indices(self):
        self.assertEqual(corpus.checksum(0, 0), 0)
        self.assertEqual(corpus.checksum(corpus.U64_MAX, 0), corpus.U64_MAX)
        self.assertEqual(corpus.checksum(0, 1), 0x9BB873CA8B160D00)
        self.assertEqual(corpus.checksum(corpus.U64_MAX, 1), 0x0864A6B2791206FF)
        seed = 0x123456789ABCDEF0
        value = seed
        for index in range(256):
            value = (((value ^ index) * 1099511628211) + index * 131072) % (1 << 64)
        self.assertEqual(corpus.checksum(seed, 2), value)

    def test_actual_positive_matrix_and_semantic_rejection_priority(self):
        self.assertEqual(len(corpus.POSITIVE_CASES), 6)
        self.assertGreater(sum(case.goal for case in corpus.POSITIVE_CASES), 700)
        self.assertEqual({case.scenario for case in corpus.POSITIVE_CASES}, set(range(5)))
        self.assertEqual([corpus.expected_exit(case) for case in corpus.NEGATIVE_CASES], [16, 16, 22, 22, 14])
        case = corpus.TimerCase("priority", 0, 0, 0, 99)
        self.assertEqual(corpus.expected_exit(case), 16)
        self.assertEqual(corpus.expected_exit(replace(case, goal=1)), 22)
        self.assertEqual(corpus.expected_exit(replace(case, goal=1, period=1)), 14)

    def test_mutants_are_closed_and_require_positive_cases(self):
        self.assertEqual(corpus.expected_exit(corpus.MUTANT_CASES[1], mutation=1), 20)
        self.assertEqual(corpus.expected_exit(corpus.MUTANT_CASES[2], mutation=2), 21)
        for mutation in (-1, 3, True, "1"):
            with self.assertRaises(Core0Error):
                corpus.expected_exit(corpus.POSITIVE_CASES[0], mutation=mutation)
        for mutation in (1, 2):
            with self.assertRaises(Core0Error):
                corpus.expected_exit(corpus.NEGATIVE_CASES[0], mutation=mutation)

    def test_wrong_host_types_ranges_and_names_reject(self):
        good = corpus.POSITIVE_CASES[0]
        for field in ("seed", "goal", "period", "scenario"):
            for bad in (True, -1, 1 << 64, "1"):
                with self.subTest(field=field, bad=bad):
                    with self.assertRaises(Core0Error):
                        corpus.fixture_bytes(replace(good, **{field: bad}))
        for name in ("", "../escape", "UPPER", None, 7):
            with self.assertRaises(Core0Error):
                corpus.validate_case(replace(good, name=name))
        for bad in (True, -1, corpus.MAXIMUM_QUANTA + 1):
            with self.assertRaises(Core0Error):
                corpus.checksum(0, bad)


if __name__ == "__main__":
    unittest.main()
