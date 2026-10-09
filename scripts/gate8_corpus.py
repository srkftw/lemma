#!/usr/bin/env python3
"""Closed runtime-only timer inputs and an independent fixed-width fold oracle."""
from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

from core0_common import Core0Error

PROFILE = "core0-v0.7"
ARTIFACT_CATEGORY = "test-timer-suite"
TEST_ABI = "lemma-timer-test-v1"
READY = b"LEMMA_DEVICE/1\nREADY\n"
U64_MAX = (1 << 64) - 1
MAXIMUM_TIME = (1 << 63) - 1
MAXIMUM_GOAL = 512
MAXIMUM_PERIOD = 1_000_000
MAXIMUM_QUANTA = 1_000_000
WORK_QUANTUM = 128
RING_CAPACITY = 16
TIMER_CAUSE = (1 << 63) | 7
FIXTURE_ADDRESS = 0x81000000
STAT_IDS = tuple(range(0x8101, 0x8119))
STAT_FIELDS = (
    "checksum", "outer_quanta", "irq_count", "head", "tail", "overflow", "skipped",
    "spurious", "maximum_catch_up", "context_mask", "pending_witness", "before",
    "after", "guard_mask", "last_consumed_sequence", "last_consumed_time",
    "last_isr_time", "deadline", "real_time", "real_pending", "last_ring_sequence",
    "last_ring_time", "last_ring_pc", "last_ring_cause",
)
RING_BASE_ID = 0x8200
FAILURE_ID = 0x81FF
RESTORE_MASK = 1 << 18
MUTATION_IDENTITIES = ("none", "restore-s3-from-s4", "disable-timer-arming")


@dataclass(frozen=True)
class TimerCase:
    name: str
    seed: int
    goal: int
    period: int
    scenario: int = 0


def validate_case(case: TimerCase) -> None:
    if not isinstance(case, TimerCase) or not isinstance(case.name, str) or not case.name or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in case.name
    ):
        raise Core0Error("timer case has the wrong type or unsafe artifact name")
    for key in ("seed", "goal", "period", "scenario"):
        value = getattr(case, key)
        if type(value) is not int or not 0 <= value <= U64_MAX:
            raise Core0Error(f"timer case {key} is outside UInt64")


def validate_mutation(mutation: int) -> None:
    if type(mutation) is not int or mutation not in (0, 1, 2):
        raise Core0Error("timer mutation must be the integer 0, 1, or 2")


def fixture_bytes(case: TimerCase) -> bytes:
    validate_case(case)
    return struct.pack("<QQQQ", case.seed, case.goal, case.period, case.scenario)


def expected_exit(case: TimerCase, *, mutation: int = 0) -> int:
    validate_case(case)
    validate_mutation(mutation)
    if case.goal == 0 or case.goal > MAXIMUM_GOAL:
        code = 16
    elif case.period == 0 or case.period > MAXIMUM_PERIOD:
        code = 22
    elif case.scenario > 4:
        code = 14
    else:
        code = 0
    if mutation:
        if code:
            raise Core0Error("timer behavioral mutant requires a valid positive runtime case")
        return 20 if mutation == 1 else 21
    return code


def checksum(seed: int, outer_quanta: int) -> int:
    if type(seed) is not int or not 0 <= seed <= U64_MAX:
        raise Core0Error("timer checksum seed is outside UInt64")
    if type(outer_quanta) is not int or not 0 <= outer_quanta <= MAXIMUM_QUANTA:
        raise Core0Error("timer checksum quanta exceed the semantic work budget")
    value = seed
    for index in range(WORK_QUANTUM * outer_quanta):
        value = (((value ^ index) * 0x100000001B3) + (index << 17)) & U64_MAX
    return value


POSITIVE_CASES = (
    TimerCase("overflow-zero", 0, 256, 10000),
    TimerCase("overflow-wrap-seed", U64_MAX, 256, 10000),
    TimerCase("masked-pending", 0x0123456789ABCDEF, 1, 100000, 1),
    TimerCase("forced-catch-up", 0xFEDCBA9876543210, 32, 10000, 2),
    TimerCase("shutdown", 0x123456789ABCDEF0, 64, 20000, 3),
    TimerCase("interleaved-wrap", 0xA55AA55A5AA55AA5, 128, 10000, 4),
)
NEGATIVE_CASES = (
    TimerCase("zero-goal", 0, 0, 10000),
    TimerCase("excess-goal", 0, 513, 10000),
    TimerCase("zero-period", 0, 1, 0),
    TimerCase("excess-period", 0, 1, 1000001),
    TimerCase("malformed-scenario", 0, 1, 10000, 5),
)
MUTANT_CASES = {
    1: TimerCase("restore-s3-from-s4", 0x0123456789ABCDEF, 32, 10000),
    2: TimerCase("disable-timer-arming", 0xFEDCBA9876543210, 1, 100000, 1),
}


def corpus_manifest() -> dict[str, object]:
    cases = (*POSITIVE_CASES, *NEGATIVE_CASES, *MUTANT_CASES.values())
    if len({case.name for case in cases}) != len(cases):
        raise Core0Error("duplicate timer corpus case names")
    return {
        "schema_version": 1, "profile": PROFILE, "artifact_category": ARTIFACT_CATEGORY,
        "test_abi": TEST_ABI, "fixture_address": hex(FIXTURE_ADDRESS), "fixture_bytes": 32,
        "runtime_fields": ["seed", "goal", "period", "scenario"],
        "oracle": "((acc ^ globalIndex) * 0x100000001b3 + (globalIndex << 17)) mod 2^64",
        "work_quantum": WORK_QUANTUM, "ring_capacity": RING_CAPACITY,
        "positive_cases": [dict(asdict(case), minimum_hardware_irqs=case.goal,
            useful_foreground_required=case.goal >= 32) for case in POSITIVE_CASES],
        "negative_cases": [dict(asdict(case), expected_exit=expected_exit(case)) for case in NEGATIVE_CASES],
        "mutations": [dict(asdict(case), mutation=mutation,
            identity=MUTATION_IDENTITIES[mutation], production_selectable=False,
            expected_exit=expected_exit(case, mutation=mutation),
            expected_failure_value=RESTORE_MASK if mutation == 1 else 0)
            for mutation, case in MUTANT_CASES.items()],
    }
