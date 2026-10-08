#!/usr/bin/env python3
"""Independent monitor arithmetic, state, bounds, framing, and corpus tests."""
import dataclasses
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import gate9_corpus as corpus
from core0_common import Core0Error

RANGES = [[0x80000000, 0x80010000]]


class MonitorCorpusTests(unittest.TestCase):
    def setUp(self):
        self.oracle = corpus.Oracle(RANGES)
        self.identifier = 0

    def accept(self, command, payload=(), values=(0, 0, 0, 0), status=0, **header):
        self.identifier += 1
        request = corpus.Request(command, self.identifier, corpus.words(*payload), **header)
        self.oracle.accept(request, corpus.Response(status, self.identifier, values))

    def test_exact_wire_layout_and_unsigned_extremes(self):
        request = corpus.Request(3, corpus.U64_MAX, corpus.words(0, corpus.U64_MAX, 1, 0))
        data = request.encode()
        self.assertEqual(len(data), 48)
        self.assertEqual(data[:8], b"LMQ9\x01\x03\x20\x00")
        self.assertEqual(data[8:16], b"\xff" * 8)
        response = corpus.Response(17, corpus.U64_MAX, (0, 1, 2, corpus.U64_MAX))
        self.assertEqual(corpus.parse_response(response.encode()), response)
        self.assertEqual(corpus.READY, b"LEMMA_MONITOR/1\nREADY\n")

    def test_internal_and_fatal_statuses_are_not_monitor_frames(self):
        for status in (10, 18, 19, 23, 255):
            blob = b"LMS9" + bytes((1, status, 32, 0)) + corpus.words(1, 0, 0, 0, 0)
            with self.assertRaises(Core0Error):
                corpus.parse_response(blob)
        for value in (-1, 1 << 64, True, 1.0):
            with self.assertRaises(Core0Error):
                corpus.Request(1, value).encode()

    def test_independent_mix_known_answers_and_global_index(self):
        self.assertEqual(corpus.mix(0, 1), 0x9BB873CA8B160D00)
        self.assertEqual(corpus.mix(corpus.U64_MAX, 1), 0x0864A6B2791206FF)
        self.assertEqual(corpus.mix(corpus.U64_MAX, 0), corpus.U64_MAX)
        self.assertNotEqual(corpus.mix(0, 2), corpus.mix(corpus.mix(0, 1), 1))

    def test_closed_corpus_has_differing_streams_and_required_boundaries(self):
        manifest = corpus.corpus_manifest()
        self.assertEqual(len(manifest["scenarios"]), 9)
        streams = [b"".join(request.encode() for request in scenario.requests) for scenario in corpus.MIXED_SCENARIOS]
        self.assertNotEqual(*streams)
        for scenario in corpus.MIXED_SCENARIOS:
            self.assertLess(len(scenario.requests), 256)
            self.assertEqual({request.command for request in scenario.requests if request.command <= 10}, set(range(1, 11)))
            periods = [struct.unpack("<Q", request.payload)[0] for request in scenario.requests if request.command == 7]
            self.assertTrue({0, 1, 9999, 1_000_000, 1_000_001} <= set(periods))
            evals = [struct.unpack("<QQQQ", request.payload) for request in scenario.requests if request.command == 3]
            self.assertTrue(any(selector == 2 and count == 4096 for selector, _, count, _ in evals))
            self.assertTrue(any(selector == 3 and count == 256 for selector, _, count, _ in evals))
        self.assertEqual([len(scenario.requests) for scenario in corpus.BUDGET_SCENARIOS], [256, 256])
        self.assertEqual([scenario.expected_exit for scenario in corpus.BUDGET_SCENARIOS], [0, 9])

    def test_initial_timer_snapshots_and_stop_preserve_default_period(self):
        self.accept(9, (0, 0))
        self.accept(9, (1, 0))
        self.accept(9, (2, 0), (0, 10000, 0, 0))
        self.accept(8)
        self.accept(9, (2, 0), (0, 10000, 0, 0))

    def test_buffer_preflight_denials_and_zero_length_boundary(self):
        self.accept(5, (0, 3840), (0, 3840, 0, 0))
        self.accept(4, (0, 3840, 255), (3840, 979200, 0, 0))
        self.accept(4, (3840, 0, 0), (0, 0, 3840, 0))
        self.accept(4, (3840, 1, 0), status=7)
        self.accept(4, (corpus.U64_MAX, 2, 0), status=7)
        self.accept(4, (0, corpus.U64_MAX, 0), status=7)
        self.accept(4, (0, 1, 256), status=14)
        self.accept(5, (0, 3840), (979200, 3840, 0, 0))
        self.assertEqual(self.oracle.errors, 4)

    def test_complete_malformed_requests_count_and_recover(self):
        self.accept(1, (99,), status=14, magic=b"BAD9")
        self.accept(1, (99,), status=14, version=2)
        self.accept(1, (99,), status=14, flags=1)
        self.accept(1, (99,), status=16)
        self.accept(255, (99,), status=17)
        self.accept(2, values=(6, 5, 0, 0))

    def test_arithmetic_and_checksum_are_not_trusted_guest_words(self):
        self.accept(3, (0, corpus.U64_MAX, 2, 0), (1, 0, 0, 0))
        self.accept(3, (1, corpus.U64_MAX, 1 << 63, 0), ((1 << 63) - 1, 0, 0, 0))
        self.accept(3, (2, 0, 1, 0), (0x9BB873CA8B160D00, 1, 0, 0))
        with self.assertRaisesRegex(Core0Error, "checksum"):
            self.accept(3, (2, 0, 1, 0), (0, 1, 0, 0))

    def test_period_domain_active_rejection_and_real_restart_lifetime(self):
        for period in (0, 1, 9999, 1_000_001):
            self.accept(7, (period,), status=22)
        self.accept(3, (2, 0, 1, 0), (0x9BB873CA8B160D00, 1, 0, 0))
        self.accept(7, (10000,), (1, 10000, 20000, 0))
        self.accept(7, (10000,), status=16)
        self.accept(6, (0,), (0, 1, 1, 2))
        self.accept(8, values=(2, 2, 0, 1))
        self.accept(7, (1_000_000,), (1, 1_000_000, 2_000_000, 0))
        self.accept(9, (2, 0), (1, 1_000_000, 0, 0))
        self.accept(2, values=(12, 5, 1, 0x9BB873CA8B160D00))
        self.assertEqual(self.oracle.prior_hardware_irqs, 2)

    def test_skipped_spurious_deadline_and_irq_monotonicity(self):
        self.accept(7, (10000,), (1, 10000, 10000, 0))
        self.accept(9, (0, 0), (20, 16, 0, 4))
        self.accept(9, (1, 0), (3, 2, 1000, 11000))
        for values in ((2, 2, 1000, 11000), (3, 1, 1000, 11000), (3, 2, 999, 11000),
                       (3, 2, 1000, 10999), (3, 2, 1000, 11001)):
            with self.assertRaises(Core0Error):
                self.accept(9, (1, 0), values)
        with self.assertRaisesRegex(Core0Error, "hardware IRQ"):
            self.accept(8, values=(19, 19, 0, 0))

    def test_ring_record_cause_pc_order_and_peek_pop_identity(self):
        self.accept(7, (10000,), (1, 10000, 10000, 0))
        self.accept(9, (0, 0), (20, 16, 0, 4))
        record = (1, 100, 0x80001000, corpus.TIMER_CAUSE)
        self.accept(9, (3, 0), record)
        self.accept(9, (4, 0), record)
        self.accept(9, (3, 16), status=7)
        for record in ((2, 101, 0x80001002, corpus.TIMER_CAUSE), (2, 101, 0x90000000, corpus.TIMER_CAUSE),
                       (2, 101, 0x80001000, 7), (1, 101, 0x80001000, corpus.TIMER_CAUSE)):
            with self.assertRaises(Core0Error):
                self.accept(9, (4, 0), record)

    def test_missing_real_event_work_and_shutdown_corruption_reject(self):
        self.accept(3, (3, 0, 1, 0), (0, 0, 0, 0), status=21)
        self.accept(7, (10000,), (1, 10000, 10000, 0))
        with self.assertRaisesRegex(Core0Error, "real hardware"):
            self.accept(3, (3, 0, 32, 0), (corpus.mix(0, 1), 1, 1, 1))
        with self.assertRaisesRegex(Core0Error, "shutdown"):
            self.accept(8, values=(1, 2, 0, 0))

    def test_invalid_terminal_or_session_shapes_reject(self):
        for scenario in (corpus.Scenario("bad"), corpus.Scenario("bad", (corpus.Request(1, 1),)),
            corpus.Scenario("bad", (corpus.Request(10, 1), corpus.Request(10, 2))),
            corpus.Scenario("bad", expected_exit=9),
            corpus.Scenario("bad", terminal_input=corpus.Request(1, 1).encode(), expected_exit=15)):
            with self.assertRaises(Core0Error):
                corpus.validate_scenario(scenario)


if __name__ == "__main__":
    unittest.main()
