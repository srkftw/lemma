#!/usr/bin/env python3
"""Closed Gate 7 runtime inputs and an independent unsigned-fold oracle.

Only seed/count/scenario enter the guest fixture.  Answers are host-side
expectations, never loader data or compiler/exporter configuration.
"""
from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

from core0_common import Core0Error

PROFILE = "core0-v0.6"
ARTIFACT_CATEGORY = "test-trap-suite"
TEST_ABI = "lemma-sync-trap-test-v1"
READY = b"LEMMA_DEVICE/1\nREADY\n"
U64_MAX = (1 << 64) - 1
MAXIMUM_COUNT = 64
FIXTURE_ADDRESS = 0x81000000
RESULT_IDS = (0x7101, 0x7102, 0x7103, 0x7104)
FATAL_IDS = (0x7001, 0x7002, 0x7003, 0x7004, 0x7005)
MUTANT_ID = 0x71FF
MUTANT_MASK = 1 << 18
DENIAL_COUNT = 14


@dataclass(frozen=True)
class TrapCase:
    name: str
    seed: int
    count: int
    scenario: int = 0


def validate_case(case: TrapCase) -> None:
    if not isinstance(case, TrapCase):
        raise Core0Error("trap case has the wrong type")
    if not case.name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in case.name):
        raise Core0Error("trap case name is not a safe artifact stem")
    for key in ("seed", "count", "scenario"):
        value = getattr(case, key)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U64_MAX:
            raise Core0Error(f"trap case {key} is outside UInt64")


def fixture_bytes(case: TrapCase) -> bytes:
    validate_case(case)
    return struct.pack("<QQQ", case.seed, case.count, case.scenario)


def checksum(seed: int, count: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= U64_MAX:
        raise Core0Error("checksum seed is outside UInt64")
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAXIMUM_COUNT:
        raise Core0Error("checksum count exceeds the semantic fold budget")
    value = seed
    for index in range(count):
        value = (((value ^ index) * 0x100000001B3) + (index << 17)) & U64_MAX
    return value


POSITIVE_CASES = (
    TrapCase("zero-zero", 0, 0),
    TrapCase("zero-wrap-seed", U64_MAX, 0),
    TrapCase("one-zero", 0, 1),
    TrapCase("one-wrap-seed", U64_MAX, 1),
    TrapCase("several-pattern-a", 0x0123456789ABCDEF, 7),
    TrapCase("several-pattern-b", 0xFEDCBA9876543210, 7),
    TrapCase("maximum-zero", 0, 64),
    TrapCase("maximum-wrap-seed", U64_MAX, 64),
)
NEGATIVE_CASES = (
    TrapCase("unauthorized-ecall", 0x1234, 1, 1),
    TrapCase("illegal-instruction", 0x1234, 1, 2),
    TrapCase("nested-ecall", 0x1234, 1, 4),
    TrapCase("semantic-budget", 0x1234, 65),
    TrapCase("invalid-count-u32", 0x1234, 1 << 32),
    TrapCase("malformed-scenario", 0x1234, 1, 3),
)
MUTANT_CASE = TrapCase("restore-s3-from-s4", 0x0123456789ABCDEF, 1)


def expected_exit(case: TrapCase, *, mutant: bool = False) -> int:
    validate_case(case)
    if mutant:
        if case.scenario != 0 or not 1 <= case.count <= MAXIMUM_COUNT:
            raise Core0Error("behavioral restore mutant requires a nonempty normal fold")
        return 20
    if case.scenario in (1, 2):
        return 18
    if case.scenario == 4:
        return 19
    if case.scenario != 0:
        return 14
    if case.count > 0xFFFFFFFF:
        return 16
    return 9 if case.count > MAXIMUM_COUNT else 0


def corpus_manifest() -> dict[str, object]:
    cases = (*POSITIVE_CASES, *NEGATIVE_CASES)
    if len({case.name for case in cases}) != len(cases):
        raise Core0Error("duplicate trap corpus case names")
    return {
        "schema_version": 1, "profile": PROFILE, "artifact_category": ARTIFACT_CATEGORY,
        "test_abi": TEST_ABI, "fixture_address": hex(FIXTURE_ADDRESS),
        "fixture_bytes": 24, "maximum_count": MAXIMUM_COUNT,
        "oracle": "((acc ^ index) * 0x100000001b3 + (index << 17)) mod 2^64",
        "positive_cases": [dict(asdict(case), checksum=checksum(case.seed, case.count),
                                actual_trap_count=2 * case.count, software_denials=DENIAL_COUNT,
                                context_mask=0) for case in POSITIVE_CASES],
        "negative_cases": [dict(asdict(case), expected_exit=expected_exit(case)) for case in NEGATIVE_CASES],
        "restore_mutation": dict(asdict(MUTANT_CASE), expected_exit=20,
                                 expected_mask=MUTANT_MASK, production_selectable=False),
    }
