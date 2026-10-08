#!/usr/bin/env python3
"""Closed deterministic Gate 6 UART protocol corpus and independent oracle."""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path

from core0_common import Core0Error


SCHEMA_VERSION = 1
PROFILE = "core0-v0.5"
TEST_ABI = "lemma-device-session-v1"
DEFAULT_SUITE_ID = 0x4C454D4D41363036
DEFAULT_SOURCE_SEED = 0x534F555243453036
DEFAULT_RUNTIME_SEED = 0x52554E54494D4536

READY = b"LEMMA_DEVICE/1\nREADY\n"
REQUEST_MAGIC = b"LMQ6"
RESPONSE_MAGIC = b"LMS6"
VERSION = 1
REQUEST_HEADER_BYTES = 16
MAXIMUM_PAYLOAD_BYTES = 16
RESPONSE_BYTES = 24
RESPONSE_PAYLOAD_BYTES = 8
REQUESTS_PER_SESSION = 2

COMMAND_ADD64 = 1
COMMAND_XOR64 = 2
COMMAND_BRANCH = 3
COMMAND_TX_STRESS = 4

BRANCH_SENTINEL = 0x3C
BRANCH_FALSE_MARKER = 0x5A
BRANCH_TRUE_UART_MARKER = 0xA5

STATUS_OK = 0
STATUS_POLL_AGAIN_INTERNAL = 10
STATUS_TX_TIMEOUT = 11
STATUS_RX_TIMEOUT = 12
STATUS_LINE_ERROR = 13
STATUS_MALFORMED_FRAME = 14
STATUS_TRUNCATED_FRAME = 15
STATUS_INVALID_LENGTH = 16
STATUS_UNSUPPORTED_COMMAND = 17

STATUS_NAMES = {
    STATUS_OK: "ok",
    STATUS_TX_TIMEOUT: "tx-timeout",
    STATUS_RX_TIMEOUT: "rx-timeout",
    STATUS_LINE_ERROR: "line-error",
    STATUS_MALFORMED_FRAME: "malformed-frame",
    STATUS_TRUNCATED_FRAME: "truncated-frame",
    STATUS_INVALID_LENGTH: "invalid-length",
    STATUS_UNSUPPORTED_COMMAND: "unsupported-command",
}

U64_MASK = (1 << 64) - 1


class CorpusError(Core0Error):
    pass


@dataclass(frozen=True)
class Request:
    command: int
    request_id: int
    payload: bytes
    magic: bytes = REQUEST_MAGIC
    version: int = VERSION
    flags: int = 0
    declared_length: int | None = None

    def encode(self) -> bytes:
        return encode_request(self)


@dataclass(frozen=True)
class Response:
    status: int
    request_id: int
    value: int


@dataclass(frozen=True)
class Exchange:
    request: Request
    expected_prefix: bytes
    expected_response: Response


@dataclass(frozen=True)
class Scenario:
    name: str
    exchanges: tuple[Exchange, ...] = ()
    raw_input: bytes = b""
    expected_exit_status: int = STATUS_OK
    withhold_after_ready: bool = False
    suppress_output_after_ready: bool = False
    purpose: str = ""


def _u8(value: int, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise CorpusError(f"{context} is outside UInt8")
    return value


def _u64(value: int, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MASK:
        raise CorpusError(f"{context} is outside UInt64")
    return value


def encode_request(request: Request) -> bytes:
    if not isinstance(request.magic, bytes) or len(request.magic) != 4:
        raise CorpusError("request magic must contain exactly four bytes")
    command = _u8(request.command, "request command")
    version = _u8(request.version, "request version")
    flags = _u8(request.flags, "request flags")
    request_id = _u64(request.request_id, "request id")
    if not isinstance(request.payload, bytes):
        raise CorpusError("request payload must be bytes")
    length = len(request.payload) if request.declared_length is None else request.declared_length
    length = _u8(length, "declared request length")
    return (
        request.magic
        + bytes((version, command, length, flags))
        + struct.pack("<Q", request_id)
        + request.payload
    )


def parse_response(frame: bytes) -> Response:
    if not isinstance(frame, bytes) or len(frame) != RESPONSE_BYTES:
        raise CorpusError(f"response must contain exactly {RESPONSE_BYTES} bytes")
    if frame[:4] != RESPONSE_MAGIC:
        raise CorpusError(f"response magic differs: {frame[:4]!r}")
    if frame[4] != VERSION:
        raise CorpusError(f"response version differs: {frame[4]}")
    status = frame[5]
    if status == STATUS_POLL_AGAIN_INTERNAL:
        raise CorpusError("internal poll status escaped into a public response")
    if status not in STATUS_NAMES:
        raise CorpusError(f"response status is outside the public catalog: {status}")
    if frame[6] != RESPONSE_PAYLOAD_BYTES or frame[7] != 0:
        raise CorpusError("response length or flags differ from the fixed ABI")
    return Response(
        status=status,
        request_id=struct.unpack_from("<Q", frame, 8)[0],
        value=struct.unpack_from("<Q", frame, 16)[0],
    )


def encode_response(response: Response) -> bytes:
    if response.status not in STATUS_NAMES:
        raise CorpusError(f"cannot encode status outside public catalog: {response.status}")
    return (
        RESPONSE_MAGIC
        + bytes((VERSION, response.status, RESPONSE_PAYLOAD_BYTES, 0))
        + struct.pack("<Q", _u64(response.request_id, "response request id"))
        + struct.pack("<Q", _u64(response.value, "response value"))
    )


def expected_exchange(request: Request) -> Exchange:
    if request.magic != REQUEST_MAGIC or request.version != VERSION or request.flags != 0:
        raise CorpusError("malformed requests have no normal exchange response")
    declared = len(request.payload) if request.declared_length is None else request.declared_length
    if not 0 <= declared <= MAXIMUM_PAYLOAD_BYTES or declared != len(request.payload):
        raise CorpusError("invalid/truncated requests have no normal exchange response")
    if request.command == COMMAND_ADD64:
        if declared != 16:
            raise CorpusError("ADD64 requires a 16-byte payload")
        left, right = struct.unpack("<QQ", request.payload)
        prefix = b""
        response = Response(STATUS_OK, request.request_id, (left + right) & U64_MASK)
    elif request.command == COMMAND_XOR64:
        if declared != 16:
            raise CorpusError("XOR64 requires a 16-byte payload")
        left, right = struct.unpack("<QQ", request.payload)
        prefix = b""
        response = Response(STATUS_OK, request.request_id, left ^ right)
    elif request.command == COMMAND_BRANCH:
        if declared != 1 or request.payload[0] not in (0, 1):
            raise CorpusError("BRANCH normal exchange requires one canonical Bool byte")
        branch = request.payload[0]
        observed_marker = BRANCH_SENTINEL if branch else BRANCH_FALSE_MARKER
        prefix = bytes((BRANCH_TRUE_UART_MARKER,)) if branch else b""
        response_value = (observed_marker << 8) | branch
        response = Response(STATUS_OK, request.request_id, response_value)
    elif request.command == COMMAND_TX_STRESS:
        if declared != 4:
            raise CorpusError("TX_STRESS requires a 4-byte payload")
        count = struct.unpack("<I", request.payload)[0]
        if count > 65535:
            raise CorpusError("TX_STRESS count exceeds its source bound")
        prefix = b"\x55" * count
        response = Response(STATUS_OK, request.request_id, count)
    else:
        prefix = b""
        response = Response(STATUS_UNSUPPORTED_COMMAND, request.request_id, 0)
    return Exchange(request=request, expected_prefix=prefix, expected_response=response)


def _request(command: int, request_id: int, payload: bytes) -> Request:
    return Request(command=command, request_id=request_id, payload=payload)


ARITHMETIC = Scenario(
    name="arithmetic-two-requests",
    exchanges=(
        expected_exchange(_request(COMMAND_ADD64, 0x1001, struct.pack("<QQ", U64_MASK, 2))),
        expected_exchange(
            _request(COMMAND_XOR64, 0x1002, struct.pack("<QQ", 0xF0F00F0FA5A55A5A, 0x55AA55AA12345678))
        ),
    ),
    purpose="two independently computed responses from one PID and ELF",
)

BRANCH_EFFECTS = Scenario(
    name="branch-effects",
    exchanges=(
        expected_exchange(_request(COMMAND_BRANCH, 0x2001, b"\x00")),
        expected_exchange(_request(COMMAND_BRANCH, 0x2002, b"\x01")),
    ),
    purpose=(
        "target-observed scratch+64 readback distinguishes false 0x5a overwrite "
        "from true 0x3c sentinel preservation, while true also emits raw 0xa5"
    ),
)

UNSUPPORTED_RECOVERY = Scenario(
    name="unsupported-then-valid",
    exchanges=(
        expected_exchange(_request(0x7F, 0x3001, b"\xaa\xbb")),
        expected_exchange(_request(COMMAND_ADD64, 0x3002, struct.pack("<QQ", 41, 1))),
    ),
    purpose="status-17 response followed by synchronized recovery",
)

TX_STRESS_SMALL = Scenario(
    name="tx-stress-small",
    exchanges=(
        expected_exchange(_request(COMMAND_TX_STRESS, 0x4001, struct.pack("<I", 257))),
        expected_exchange(_request(COMMAND_XOR64, 0x4002, struct.pack("<QQ", U64_MASK, 0x55))),
    ),
    purpose="bounded packet prefix and subsequent request",
)

RX_TIMEOUT = Scenario(
    name="rx-timeout",
    expected_exit_status=STATUS_RX_TIMEOUT,
    withhold_after_ready=True,
    purpose="no first request byte reaches the compiled receiver",
)

TRUNCATED_HEADER = Scenario(
    name="truncated-header",
    raw_input=REQUEST_MAGIC + bytes((VERSION,)),
    expected_exit_status=STATUS_TRUNCATED_FRAME,
    withhold_after_ready=True,
    purpose="partial fixed header times out",
)

_truncated_payload_request = _request(
    COMMAND_ADD64, 0x5002, struct.pack("<QQ", 1, 2)
).encode()
TRUNCATED_PAYLOAD = Scenario(
    name="truncated-payload",
    raw_input=_truncated_payload_request[:21],
    expected_exit_status=STATUS_TRUNCATED_FRAME,
    withhold_after_ready=True,
    purpose="complete header plus partial payload times out",
)

MALFORMED_MAGIC = Scenario(
    name="malformed-magic",
    raw_input=Request(0x7F, 0x6001, b"", magic=b"BAD!").encode(),
    expected_exit_status=STATUS_MALFORMED_FRAME,
    purpose="bad request magic",
)

MALFORMED_VERSION = Scenario(
    name="malformed-version",
    raw_input=Request(0x7F, 0x6002, b"", version=2).encode(),
    expected_exit_status=STATUS_MALFORMED_FRAME,
    purpose="unsupported request version",
)

MALFORMED_FLAGS = Scenario(
    name="malformed-flags",
    raw_input=Request(0x7F, 0x6003, b"", flags=1).encode(),
    expected_exit_status=STATUS_MALFORMED_FRAME,
    purpose="nonzero reserved flags",
)

INVALID_OVERSIZE = Scenario(
    name="invalid-length-oversize",
    raw_input=Request(COMMAND_ADD64, 0x7001, b"", declared_length=17).encode(),
    expected_exit_status=STATUS_INVALID_LENGTH,
    purpose="declared payload exceeds the fixed receive buffer",
)

INVALID_COMMAND_LENGTH = Scenario(
    name="invalid-known-command-length",
    raw_input=Request(COMMAND_ADD64, 0x7002, struct.pack("<Q", 9)).encode(),
    expected_exit_status=STATUS_INVALID_LENGTH,
    purpose="known command has the wrong bounded payload size",
)

INVALID_BRANCH_BOOL = Scenario(
    name="invalid-branch-bool",
    raw_input=Request(COMMAND_BRANCH, 0x7003, b"\x02").encode(),
    expected_exit_status=STATUS_MALFORMED_FRAME,
    purpose="branch payload is not a canonical Bool",
)

TX_BACKPRESSURE = Scenario(
    name="tx-timeout-backpressure",
    raw_input=Request(COMMAND_TX_STRESS, 0x8001, struct.pack("<I", 65535)).encode(),
    expected_exit_status=STATUS_TX_TIMEOUT,
    suppress_output_after_ready=True,
    purpose="host stops consuming serial output so bounded transmit polling expires",
)

SCENARIOS = (
    ARITHMETIC,
    BRANCH_EFFECTS,
    UNSUPPORTED_RECOVERY,
    TX_STRESS_SMALL,
    RX_TIMEOUT,
    TRUNCATED_HEADER,
    TRUNCATED_PAYLOAD,
    MALFORMED_MAGIC,
    MALFORMED_VERSION,
    MALFORMED_FLAGS,
    INVALID_OVERSIZE,
    INVALID_COMMAND_LENGTH,
    INVALID_BRANCH_BOOL,
    TX_BACKPRESSURE,
)
SCENARIO_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}
assert len(SCENARIO_BY_NAME) == len(SCENARIOS)


def scenario_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "test_abi": TEST_ABI,
        "suite_id": f"0x{DEFAULT_SUITE_ID:016x}",
        "source_seed": f"0x{DEFAULT_SOURCE_SEED:016x}",
        "runtime_seed": f"0x{DEFAULT_RUNTIME_SEED:016x}",
        "ready_hex": READY.hex(),
        "scenarios": [
            {
                "name": scenario.name,
                "purpose": scenario.purpose,
                "exchange_count": len(scenario.exchanges),
                "raw_input_hex": scenario.raw_input.hex(),
                "expected_exit_status": scenario.expected_exit_status,
                "withhold_after_ready": scenario.withhold_after_ready,
                "suppress_output_after_ready": scenario.suppress_output_after_ready,
                "exchanges": [
                    {
                        "request_hex": exchange.request.encode().hex(),
                        "expected_prefix_hex": exchange.expected_prefix.hex(),
                        "expected_response": asdict(exchange.expected_response),
                    }
                    for exchange in scenario.exchanges
                ],
            }
            for scenario in SCENARIOS
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    ns = parser.parse_args()
    manifest = scenario_manifest()
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if ns.output is None:
        print(text, end="")
    else:
        ns.output.parent.mkdir(parents=True, exist_ok=True)
        ns.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
