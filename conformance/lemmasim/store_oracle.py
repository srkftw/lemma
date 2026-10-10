"""Independent host-only disk observer for guest store-v1 evidence.

No production guest transition, codec, or recovery function is imported. This
observer never supplies a recovered notebook to a running guest.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

ROOT = 0x31544F4F524D4C
RECORD = 0x314345524D4C
COMMIT = 0x3154494D434D4C
MASK = (1 << 64) - 1
INITIAL = 0xCBF29CE484222325
MAXIMUM = (1 << 63) - 1


def fnv(data: bytes) -> int:
    result = INITIAL
    for octet in data:
        result = ((result ^ octet) * 0x100000001B3) & MASK
    return result


def words(data: bytes, count: int) -> tuple[int, ...]:
    if len(data) != 512:
        raise ValueError("incomplete sector")
    return struct.unpack_from("<" + "Q" * count, data)


@dataclass(frozen=True)
class Root:
    generation: int
    segment: int
    start: int
    length: int
    checkpoint_count: int
    checkpoint_tail: int
    sequence: int
    checksum: int


@dataclass(frozen=True)
class Record:
    namespace: int
    object_id: int
    transaction: int
    sequence: int
    kind: int
    payload: bytes
    sector: int


def root_slot(data: bytes, capacity: int) -> Root | None:
    magic, version, gen, cap, segment, start, length, count, tail, seq, check, inverse = words(data, 12)
    if magic != ROOT:
        return None
    if version != 1:
        raise ValueError("unsupported root version")
    if not (4096 <= cap <= 0x100000000 and cap == capacity and 0 < gen <= MAXIMUM
            and segment in (0, 1) and count <= 1024 and count * 2 <= tail <= length
            and seq <= MAXIMUM and length == (capacity - 8) // 2
            and start == 8 + segment * length and data[96:] == bytes(416)
            and check == fnv(data[:80]) and inverse == (check ^ MASK)):
        return None
    return Root(gen, segment, start, length, count, tail, seq, check)


def recover(image: bytes) -> tuple[Root, int, dict[tuple[int, int], Record]]:
    if len(image) % 512 or len(image) < 4096 * 512:
        raise ValueError("invalid medium length")
    capacity = len(image) // 512
    candidates = [item for item in (root_slot(image[:512], capacity),
                                   root_slot(image[512:1024], capacity)) if item is not None]
    if not candidates:
        raise ValueError("no validated root; never automatically format")
    if len(candidates) == 2 and candidates[0].generation == candidates[1].generation and candidates[0] != candidates[1]:
        raise ValueError("contradictory roots")
    root = max(candidates, key=lambda candidate: candidate.generation)
    cursor = 0
    remaining = root.checkpoint_count
    latest = root.sequence
    objects: dict[tuple[int, int], Record] = {}
    while cursor < root.length:
        first = root.start + cursor
        header = image[first * 512:(first + 1) * 512]
        magic, version, gen, ns, obj, tx, seq, length, kind, sectors, payload_hash, check, inverse = words(header, 13)
        if magic == RECORD and version != 1:
            raise ValueError("unsupported record version")
        shape = (magic == RECORD and gen == root.generation and ns > 0 and obj > 0 and tx > 0
                 and 0 < seq <= MAXIMUM and length <= 32768 and kind in (1, 2)
                 and (kind == 1 or length == 0) and sectors == (length + 511) // 512
                 and sectors + 2 <= root.length - cursor
                 and header[104:] == bytes(408) and check == fnv(header[:88])
                 and inverse == (check ^ MASK))
        if not shape:
            if remaining:
                raise ValueError("damaged published checkpoint")
            break
        if remaining and seq > latest:
            raise ValueError("checkpoint sequence beyond root")
        if not remaining and seq != latest + 1:
            raise ValueError("append sequence contradiction")
        payload = image[(first + 1) * 512:(first + 1) * 512 + length]
        publication = image[(first + 1 + sectors) * 512:(first + 2 + sectors) * 512]
        expected_words = [COMMIT, 1, gen, ns, obj, tx, seq, length, kind, payload_hash, check]
        expected_prefix = struct.pack("<11Q", *expected_words)
        pub_check = fnv(expected_prefix)
        expected = expected_prefix + struct.pack("<QQ", pub_check, pub_check ^ MASK) + bytes(408)
        if fnv(payload) != payload_hash or publication != expected:
            if remaining:
                raise ValueError("invalid committed checkpoint payload/publication")
            break
        key = (ns, obj)
        if key in objects and objects[key].sequence >= seq:
            raise ValueError("repeated/stale object revision")
        objects[key] = Record(ns, obj, tx, seq, kind, payload, first)
        cursor += sectors + 2
        if remaining:
            remaining -= 1
            if remaining == 0 and cursor != root.checkpoint_tail:
                raise ValueError("checkpoint tail disagrees with root")
        else:
            latest = seq
    if remaining:
        raise ValueError("incomplete checkpoint")
    return root, latest, objects
