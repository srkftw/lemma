#!/usr/bin/env python3
"""Host serial framing for the guest Buffer command client.

This module encodes opaque input and decodes guest output. Buffer ownership,
allocation and operations execute only in the separately linked User server.
"""
from __future__ import annotations

import struct

from core0_common import Core0Error
from run_kernel import RECORD_BYTES, parse_record

INPUT_MAGIC = b"LMI1"
OUTPUT_MAGIC = b"LMO1"
APPLICATION_MAGIC = 0x31524642414D454C
HEADER_BYTES = 64
MAX_PAYLOAD = 192
PUBLIC_TRANSPORT_STATUSES = frozenset((0, 12, 16, 17, 22, 33, 38, 71, 72, 73, 74,
                                      80, 81, 83, 89, 90, 91, 92, 93, 94, 96, 97,
                                      98, 99, 100, 101))


def validate_input_envelope(raw: bytes) -> None:
    if not isinstance(raw, bytes) or len(raw) < 8 or raw[:4] != INPUT_MAGIC:
        raise Core0Error("input requires a complete LMI1 envelope")
    category, reserved, length = struct.unpack("<BBH", raw[4:8])
    if (reserved or category not in (1, 2)
            or (not 1 <= length <= 168 if category == 1 else length != 40)
            or len(raw) != 8 + length):
        raise Core0Error("input envelope class/reserved/length fields differ")


def input_envelope(payload: bytes, *, diagnostic: bool = False) -> bytes:
    if not isinstance(payload, bytes):
        raise Core0Error("input payload must be bytes")
    if diagnostic:
        if len(payload) != 40:
            raise Core0Error("development input must contain five u64 words")
    elif not 0 < len(payload) <= 168:
        raise Core0Error("ordinary input payload must contain1..168 bytes")
    raw = INPUT_MAGIC + struct.pack("<BBH", 2 if diagnostic else 1, 0, len(payload)) + payload
    validate_input_envelope(raw)
    return raw


def command(operation: int, epoch: int = 0, handle: int = 0,
            offset: int = 0, length: int = 0, data: bytes = b"") -> bytes:
    words = (operation, epoch, handle, offset, length)
    if any(type(word) is not int or not 0 <= word < 2**64 for word in words):
        raise Core0Error("command fields must be unsigned64 integers")
    if not 1 <= operation <= 10 or not isinstance(data, bytes):
        raise Core0Error("unknown command operation or nonbinary payload")
    if operation in (2, 4):
        if length > 128 or len(data) != length:
            raise Core0Error("write/append input must contain the exact bounded byte count")
    elif data:
        raise Core0Error("only write/append commands carry bytes")
    return input_envelope(struct.pack("<5Q", *words) + data)


def response(payload: bytes) -> dict:
    if not isinstance(payload, bytes) or not HEADER_BYTES <= len(payload) <= MAX_PAYLOAD:
        raise Core0Error("output application length is outside64..192 bytes")
    words = struct.unpack("<8Q", payload[:HEADER_BYTES])
    magic, version, operation, epoch, handle, length, count, packed = words
    detail = packed & 0xFFFFFFFF
    application = (packed >> 32) & 255
    transport = (packed >> 40) & 255
    data = payload[HEADER_BYTES:]
    if (magic != APPLICATION_MAGIC or version != 1 or not 1 <= operation <= 10
            or packed >> 48 or application not in (0, *range(200, 209))
            or transport not in PUBLIC_TRANSPORT_STATUSES):
        raise Core0Error("output magic/version/operation/status fields differ")
    if transport:
        if application or (handle, length, count, detail) != (0, 0, 0, 0) or data:
            raise Core0Error("transport error carries unvalidated service output")
    elif application:
        if (operation > 6 or (handle, length, count) != (0, 0, 0)
                or data or (application != 208 and detail)):
            raise Core0Error("service error exposes successful response fields")
    elif operation <= 6:
        if count > 128 or (len(data) != count if operation == 3 else bool(data)):
            raise Core0Error("operation-specific reply byte count differs")
        if operation in (1, 5, 6) and count:
            raise Core0Error("noncopy operation reports copied bytes")
        if operation == 6 and (handle, length, detail) != (0, 0, 0):
            raise Core0Error("destroy response retains released buffer fields")
    elif data or count:
        raise Core0Error("local informational command carries buffer bytes")
    return {"operation": operation, "epoch": epoch, "handle": handle,
            "length": length, "count": count, "detail": detail,
            "application_status": application, "transport_status": transport,
            "data_hex": data.hex(), "words": list(words)}


def decode_uart(raw: bytes, *, allow_partial: bool = False) -> tuple[list[dict], bytes]:
    """Parse complete frames with exact offsets; never scan inside binary data."""
    if not isinstance(raw, bytes):
        raise Core0Error("UART capture must be bytes")
    events, offset = [], 0
    while offset < len(raw):
        remaining = len(raw) - offset
        if raw.startswith(b"K1", offset):
            length = RECORD_BYTES
            kind = "kernel"
        elif raw.startswith(OUTPUT_MAGIC, offset):
            if remaining < 8:
                break
            category, reserved, payload_length = struct.unpack_from("<BBH", raw, offset + 4)
            if category != 1 or reserved or not HEADER_BYTES <= payload_length <= MAX_PAYLOAD:
                raise Core0Error("malformed output envelope header")
            length, kind = 8 + payload_length, "client"
        elif remaining < 4 and (b"K1".startswith(raw[offset:]) or OUTPUT_MAGIC.startswith(raw[offset:])):
            break
        else:
            raise Core0Error(f"unexplained UART bytes at offset{offset}")
        if remaining < length:
            break
        frame = raw[offset:offset + length]
        value = list(parse_record(frame)) if kind == "kernel" else response(frame[8:])
        events.append({"offset": offset, "bytes": length, "kind": kind, "value": value})
        offset += length
    remainder = raw[offset:]
    if remainder and not allow_partial:
        raise Core0Error(f"truncated UART frame at offset{offset}")
    return events, remainder
