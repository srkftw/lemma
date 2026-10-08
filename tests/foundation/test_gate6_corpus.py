from __future__ import annotations

import struct
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gate6_corpus  # noqa: E402


class Gate6CorpusTests(unittest.TestCase):
    def test_wire_constants_are_exact(self) -> None:
        self.assertEqual(gate6_corpus.READY, b"LEMMA_DEVICE/1\nREADY\n")
        self.assertEqual(gate6_corpus.REQUEST_MAGIC, b"LMQ6")
        self.assertEqual(gate6_corpus.RESPONSE_MAGIC, b"LMS6")
        self.assertEqual(int.from_bytes(gate6_corpus.REQUEST_MAGIC, "little"), 0x36514D4C)
        self.assertEqual(int.from_bytes(gate6_corpus.RESPONSE_MAGIC, "little"), 0x36534D4C)
        self.assertEqual(gate6_corpus.RESPONSE_BYTES, 24)

    def test_request_layout_is_little_endian(self) -> None:
        request = gate6_corpus.Request(
            command=gate6_corpus.COMMAND_ADD64,
            request_id=0x0102030405060708,
            payload=struct.pack("<QQ", 1, 2),
        )
        encoded = request.encode()
        self.assertEqual(encoded[:8], b"LMQ6\x01\x01\x10\x00")
        self.assertEqual(encoded[8:16], bytes.fromhex("0807060504030201"))
        self.assertEqual(len(encoded), 32)

    def test_response_round_trip_and_internal_status_rejection(self) -> None:
        expected = gate6_corpus.Response(
            gate6_corpus.STATUS_UNSUPPORTED_COMMAND,
            0x0102030405060708,
            0x8899AABBCCDDEEFF,
        )
        self.assertEqual(
            gate6_corpus.parse_response(gate6_corpus.encode_response(expected)), expected
        )
        internal = bytearray(gate6_corpus.encode_response(replace(expected, status=0)))
        internal[5] = gate6_corpus.STATUS_POLL_AGAIN_INTERNAL
        with self.assertRaisesRegex(gate6_corpus.CorpusError, "internal poll status"):
            gate6_corpus.parse_response(bytes(internal))

    def test_response_parser_fails_closed(self) -> None:
        valid = gate6_corpus.encode_response(gate6_corpus.Response(0, 1, 2))
        mutations = (
            valid[:-1],
            b"BAD!" + valid[4:],
            valid[:4] + b"\x02" + valid[5:],
            valid[:6] + b"\x07" + valid[7:],
            valid[:7] + b"\x01" + valid[8:],
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation.hex()):
                with self.assertRaises(gate6_corpus.CorpusError):
                    gate6_corpus.parse_response(mutation)

    def test_two_request_sessions_have_independent_oracles(self) -> None:
        for scenario in (
            gate6_corpus.ARITHMETIC,
            gate6_corpus.BRANCH_EFFECTS,
            gate6_corpus.UNSUPPORTED_RECOVERY,
            gate6_corpus.TX_STRESS_SMALL,
        ):
            with self.subTest(scenario=scenario.name):
                self.assertEqual(len(scenario.exchanges), 2)
                self.assertNotEqual(
                    scenario.exchanges[0].request.request_id,
                    scenario.exchanges[1].request.request_id,
                )
                for exchange in scenario.exchanges:
                    self.assertEqual(
                        gate6_corpus.expected_exchange(exchange.request), exchange
                    )

    def test_branch_and_recovery_expectations_are_distinguishing(self) -> None:
        false_exchange, true_exchange = gate6_corpus.BRANCH_EFFECTS.exchanges
        self.assertEqual(false_exchange.expected_prefix, b"")
        self.assertEqual(false_exchange.expected_response.value, 0)
        self.assertEqual(true_exchange.expected_prefix, b"\xa5")
        self.assertEqual(true_exchange.expected_response.value, 1)
        unsupported, recovered = gate6_corpus.UNSUPPORTED_RECOVERY.exchanges
        self.assertEqual(
            unsupported.expected_response.status,
            gate6_corpus.STATUS_UNSUPPORTED_COMMAND,
        )
        self.assertEqual(recovered.expected_response.status, gate6_corpus.STATUS_OK)
        self.assertEqual(recovered.expected_response.value, 42)

    def test_terminal_catalog_covers_required_failures(self) -> None:
        expected = {
            "rx-timeout": gate6_corpus.STATUS_RX_TIMEOUT,
            "truncated-header": gate6_corpus.STATUS_TRUNCATED_FRAME,
            "truncated-payload": gate6_corpus.STATUS_TRUNCATED_FRAME,
            "malformed-magic": gate6_corpus.STATUS_MALFORMED_FRAME,
            "malformed-version": gate6_corpus.STATUS_MALFORMED_FRAME,
            "malformed-flags": gate6_corpus.STATUS_MALFORMED_FRAME,
            "invalid-length-oversize": gate6_corpus.STATUS_INVALID_LENGTH,
            "invalid-known-command-length": gate6_corpus.STATUS_INVALID_LENGTH,
            "invalid-branch-bool": gate6_corpus.STATUS_MALFORMED_FRAME,
            "tx-timeout-backpressure": gate6_corpus.STATUS_TX_TIMEOUT,
        }
        self.assertEqual(
            {name: gate6_corpus.SCENARIO_BY_NAME[name].expected_exit_status for name in expected},
            expected,
        )

    def test_manifest_is_closed_and_json_serializable(self) -> None:
        manifest = gate6_corpus.scenario_manifest()
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["profile"], "core0-v0.5")
        self.assertEqual(manifest["test_abi"], "lemma-device-session-v1")
        self.assertEqual(len(manifest["scenarios"]), len(gate6_corpus.SCENARIOS))
        names = [item["name"] for item in manifest["scenarios"]]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
