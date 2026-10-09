#!/usr/bin/env python3
"""Runtime-only monitor requests and an independent stateful response oracle."""
from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field

from core0_common import Core0Error

PROFILE = "core0-v0.7"
ARTIFACT_CATEGORY = "test-monitor-image"
TEST_ABI = "lemma-monitor-v1"
READY = b"LEMMA_MONITOR/1\nREADY\n"
REQUEST_BYTES = 16
RESPONSE_BYTES = 48
MAX_PAYLOAD = 32
BUFFER_BYTES = 3840
MAX_REQUESTS = 256
U64_MAX = (1 << 64) - 1
MAX_TIME = (1 << 63) - 1
TIMER_CAUSE = (1 << 63) | 7
COMMAND_LENGTHS = {1: 0, 2: 0, 3: 32, 4: 24, 5: 16, 6: 8, 7: 8, 8: 0, 9: 16, 10: 0}
COMMAND_NAMES = dict(enumerate(("HELLO", "STATUS", "EVAL", "FILL", "CHECKSUM", "TRAP_TEST",
    "TIMER_START", "TIMER_STOP", "TICKS", "EXIT"), 1))
PUBLIC_STATUSES = frozenset(range(23)) - {10, 18, 19}


def _u64(value: int, label: str) -> None:
    if type(value) is not int or not 0 <= value <= U64_MAX:
        raise Core0Error(f"monitor {label} is outside UInt64")


def words(*values: int) -> bytes:
    for value in values:
        _u64(value, "payload word")
    return struct.pack("<" + "Q" * len(values), *values)


@dataclass(frozen=True)
class Request:
    command: int
    request_id: int
    payload: bytes = b""
    magic: bytes = b"LMQ9"
    version: int = 1
    flags: int = 0

    def encode(self) -> bytes:
        _u64(self.request_id, "request ID")
        if (type(self.command) is not int or not 0 <= self.command <= 255
                or type(self.version) is not int or not 0 <= self.version <= 255
                or type(self.flags) is not int or not 0 <= self.flags <= 255
                or not isinstance(self.magic, bytes) or len(self.magic) != 4
                or not isinstance(self.payload, bytes) or len(self.payload) > MAX_PAYLOAD):
            raise Core0Error("malformed host monitor request")
        return self.magic + bytes((self.version, self.command, len(self.payload), self.flags)) + words(self.request_id) + self.payload


@dataclass(frozen=True)
class Response:
    status: int
    request_id: int
    values: tuple[int, int, int, int]

    def encode(self) -> bytes:
        _u64(self.request_id, "response ID")
        if type(self.status) is not int or self.status not in PUBLIC_STATUSES or len(self.values) != 4:
            raise Core0Error("malformed monitor response")
        return b"LMS9" + bytes((1, self.status, 32, 0)) + words(self.request_id, *self.values)


def parse_response(data: bytes) -> Response:
    if (len(data) != RESPONSE_BYTES or data[:4] != b"LMS9" or data[4] != 1
            or data[6:8] != b"\x20\x00" or data[5] not in PUBLIC_STATUSES):
        raise Core0Error("monitor response framing/version/length/flags/status differs")
    unpacked = struct.unpack_from("<QQQQQ", data, 8)
    return Response(data[5], unpacked[0], tuple(unpacked[1:]))


def mix(seed: int, quanta: int) -> int:
    """Independent wrapping fold; never run on the live transport critical path."""
    _u64(seed, "mix seed")
    if type(quanta) is not int or not 0 <= quanta <= 1_000_000:
        raise Core0Error("monitor mix quanta exceed the semantic bound")
    result = seed
    for index in range(128 * quanta):
        result = (((result ^ index) * 0x100000001B3) + (index << 17)) & U64_MAX
    return result


@dataclass(frozen=True)
class Scenario:
    name: str
    requests: tuple[Request, ...] = ()
    terminal_input: bytes = b""
    expected_exit: int = 0
    integration: bool = False


def validate_scenario(scenario: Scenario) -> None:
    if (not isinstance(scenario, Scenario) or not isinstance(scenario.name, str) or not scenario.name
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in scenario.name)):
        raise Core0Error("monitor scenario type/name differs")
    if not isinstance(scenario.requests, tuple) or not isinstance(scenario.terminal_input, bytes):
        raise Core0Error("monitor scenario streams have the wrong type")
    if scenario.requests:
        for request in scenario.requests:
            if not isinstance(request, Request):
                raise Core0Error("monitor session contains a non-request")
            request.encode()
        if len(scenario.requests) > MAX_REQUESTS:
            raise Core0Error("monitor scenario exceeds the session budget")
    if scenario.expected_exit == 0:
        if (not scenario.requests or scenario.terminal_input
                or scenario.requests[-1] != Request(10, scenario.requests[-1].request_id)
                or any(request.command == 10 for request in scenario.requests[:-1])):
            raise Core0Error("monitor session lacks its single final successful EXIT")
    elif scenario.expected_exit == 9:
        if len(scenario.requests) != MAX_REQUESTS or scenario.terminal_input or any(request.command == 10 for request in scenario.requests):
            raise Core0Error("monitor budget failure requires exactly 256 non-EXIT requests")
    elif scenario.expected_exit in (12, 15, 16) and not scenario.integration:
        if any(request.command == 10 for request in scenario.requests):
            raise Core0Error("monitor terminal prefix cannot EXIT")
        raw = scenario.terminal_input
        inferred = 12 if not raw else 15 if len(raw) < 16 else 16 if raw[6] > MAX_PAYLOAD else 15
        if inferred != scenario.expected_exit or (len(raw) >= 16 and raw[6] <= MAX_PAYLOAD and len(raw) >= 16 + raw[6]):
            raise Core0Error("monitor terminal input is not its declared receive failure")
    else:
        raise Core0Error("monitor terminal scenario differs from bounded receive failures")


def _mixed(name: str, seed: int, byte: int, period: int, base: int) -> Scenario:
    commands: list[tuple[int, bytes, dict[str, object]]] = []
    def add(command: int, *payload: int, **header: object) -> None:
        commands.append((command, words(*payload), header))
    add(1); add(2)
    add(9, 0, 0); add(9, 1, 0); add(9, 2, 0)
    add(1, 0x1122334455667788, magic=b"BAD9")
    add(2, 99, version=2)
    add(5, 0, 0, flags=1)
    add(1, 123)  # known command with incorrect bounded length
    add(255, 0xFEEDFACE)
    add(3, 0, seed, U64_MAX, 0)
    add(3, 1, seed, 0x0123456789ABCDEF, 0)
    add(3, 2, seed, 0, 0)
    add(3, 2, seed, 3, 0)
    add(3, 2, seed, 4096, 0)
    add(3, 2, seed, 4097, 0)
    add(3, 0, 1, 2, 1)
    add(3, 99, 0, 0, 0)
    add(3, 3, seed, 1, 0)  # inactive timer is distinct from transport failure
    add(5, 0, BUFFER_BYTES)
    add(4, 0, BUFFER_BYTES, byte)
    add(5, 0, BUFFER_BYTES)
    add(4, 0, 1, byte ^ 0xFF)
    add(4, BUFFER_BYTES - 1, 1, 255)
    add(4, 17, 31, byte ^ 0x5A)
    add(4, BUFFER_BYTES, 0, 0)
    add(5, BUFFER_BYTES, 0)
    add(4, BUFFER_BYTES, 1, 0)
    add(4, U64_MAX, 2, 0)
    add(4, 0, U64_MAX, 0)
    add(4, 0, 1, 256)
    add(5, U64_MAX, U64_MAX)
    add(5, 0, BUFFER_BYTES)  # all denials must have preserved the buffer
    add(6, 0); add(6, 1); add(6, 2)
    add(7, 0); add(7, 1); add(7, 9999); add(7, 1_000_001)
    add(9, 3, 0); add(9, 4, 0)
    add(9, 0, 1); add(9, 99, 0)
    add(8)
    add(9, 2, 0)
    add(7, period)
    add(7, period + 1)
    add(9, 2, 0)
    add(6, 0); add(6, 1)
    add(3, 3, seed, 64, 0)
    add(9, 0, 0); add(9, 1, 0)
    add(9, 3, 0)
    for _ in range(16):
        add(9, 4, 0)
    add(3, 3, seed ^ U64_MAX, 256, 0)
    add(8)
    add(9, 0, 0); add(9, 1, 0)
    for index in range(16):
        add(9, 3, index)
    add(9, 3, 16)
    for _ in range(16):
        add(9, 4, 0)
    add(9, 4, 0); add(9, 3, 0)
    add(9, 0, 0); add(9, 2, 0)
    add(8); add(2)
    # A true restart clears only timer state, not monitor lifetime counters.
    add(7, 1_000_000)
    add(9, 0, 0); add(9, 1, 0); add(9, 2, 0)
    add(6, 0)
    add(3, 3, seed ^ 0xA55A, 16, 0)
    add(8)
    add(9, 0, 0); add(9, 1, 0)
    for _ in range(16):
        add(9, 4, 0)
    add(9, 0, 0); add(9, 2, 0)
    add(2); add(10)
    scenario = Scenario(name, tuple(Request(command, (base + index) & U64_MAX, payload, **header)
        for index, (command, payload, header) in enumerate(commands)), integration=True)
    validate_scenario(scenario)
    return scenario


MIXED_SCENARIOS = (
    _mixed("mixed-zero", 0, 0x5A, 10_000, 0x9000),
    _mixed("mixed-wrap", U64_MAX, 0xA5, 20_000, U64_MAX - 200),
)
TERMINAL_SCENARIOS = (
    Scenario("oversize-payload", terminal_input=b"LMQ9" + bytes((1, 4, 33, 0)) + words(0x9101), expected_exit=16),
    Scenario("truncated-header", terminal_input=b"LMQ9\x01\x01\x00", expected_exit=15),
    Scenario("truncated-payload", terminal_input=Request(7, 0x9103, words(10_000)).encode()[:-5], expected_exit=15),
    Scenario("missing-input", expected_exit=12),
    Scenario("active-truncated-payload", requests=(Request(7, 0x9110, words(10_000)),),
        terminal_input=Request(7, 0x9111, words(10_000)).encode()[:-5], expected_exit=15),
)
BUDGET_SCENARIOS = (
    Scenario("exit-at-session-limit", tuple(Request(1, 0xA000 + index) for index in range(255)) + (Request(10, 0xA0FF),)),
    Scenario("session-limit-without-exit", tuple(Request(1, 0xB000 + index) for index in range(256)), expected_exit=9),
)
SCENARIOS = MIXED_SCENARIOS + TERMINAL_SCENARIOS + BUDGET_SCENARIOS
STRESS_PROFILE = "lemma-monitor-stress-v1"
STRESS_PARAMETERS = (
    ("stress-one", 1, 0x11, 10_000, 0xC000),
    ("stress-high-bit", 0x8000000000000000, 0x80, 12_500, 0xD000),
    ("stress-pattern", 0x0123456789ABCDEF, 0x3C, 15_000, 0xE000),
    ("stress-deadbeef", 0xDEADBEEFCAFEBABE, 0xD3, 20_000, 0xF000),
)
STRESS_SEEDS = tuple(parameters[1] for parameters in STRESS_PARAMETERS)
STRESS_SCENARIOS = tuple(_mixed(*parameters) for parameters in STRESS_PARAMETERS)
# Expose individual stress sessions to the runner CLI without changing the
# default acceptance catalog. They still require the identical image binding.
SCENARIO_BY_NAME = {scenario.name: scenario for scenario in (*SCENARIOS, *STRESS_SCENARIOS)}


def selected_scenarios(*, stress: bool = False) -> tuple[Scenario, ...]:
    if type(stress) is not bool:
        raise Core0Error("monitor stress selection must be a boolean")
    normal_names = {"mixed-zero", "mixed-wrap", "oversize-payload", "truncated-header",
        "truncated-payload", "missing-input", "active-truncated-payload",
        "exit-at-session-limit", "session-limit-without-exit"}
    if len(SCENARIOS) != 9 or {scenario.name for scenario in SCENARIOS} != normal_names:
        raise Core0Error("monitor normal corpus is empty, incomplete or duplicated")
    if stress and (len(STRESS_SCENARIOS) != 4 or STRESS_SCENARIOS != tuple(_mixed(*parameters) for parameters in STRESS_PARAMETERS)):
        raise Core0Error("monitor stress corpus differs from its four deterministic mixed streams")
    scenarios = SCENARIOS + STRESS_SCENARIOS if stress else SCENARIOS
    if len({scenario.name for scenario in scenarios}) != len(scenarios):
        raise Core0Error("duplicate monitor scenario names")
    for scenario in scenarios:
        validate_scenario(scenario)
        if SCENARIO_BY_NAME.get(scenario.name) != scenario:
            raise Core0Error("monitor scenario lookup differs from the selected corpus")
    return scenarios


def stress_manifest(*, stress: bool = False) -> dict[str, object]:
    selected_scenarios(stress=stress)
    return {"enabled": stress, "profile": STRESS_PROFILE if stress else None,
        "extra_sessions_per_optimization": 4 if stress else 0,
        "parameters": [{"name": name, "seed": seed, "fill_byte": byte,
            "period": period, "request_id_base": base} for name, seed, byte, period, base
            in STRESS_PARAMETERS] if stress else []}


def corpus_manifest(*, stress: bool = False) -> dict[str, object]:
    scenarios = selected_scenarios(stress=stress)
    return {"schema_version": 1, "artifact_category": ARTIFACT_CATEGORY, "profile": PROFILE,
        "test_abi": TEST_ABI, "request_bytes": REQUEST_BYTES, "response_bytes": RESPONSE_BYTES,
        "maximum_payload_bytes": MAX_PAYLOAD, "fresh_post_boot_uart_only": True,
        "stress": stress_manifest(stress=stress),
        "scenarios": [{"name": scenario.name, "expected_exit": scenario.expected_exit,
            "integration": scenario.integration, "requests_hex": [request.encode().hex() for request in scenario.requests],
            "terminal_input_hex": scenario.terminal_input.hex()} for scenario in scenarios]}


@dataclass
class Oracle:
    """Independent software state plus bounded observations of nondeterministic IRQs."""
    executable_ranges: list[list[int]]
    buffer: bytearray = field(default_factory=lambda: bytearray(BUFFER_BYTES))
    handled: int = 0
    errors: int = 0
    sync: int = 0
    last_checksum: int = 0
    active: bool = False
    period: int = 10_000
    count: int = 0
    head: int = 0
    tail: int = 0
    overflow: int = 0
    consumed: tuple[int, int] = (0, 0)
    last_isr: int = 0
    records: dict[int, tuple[int, int, int, int]] = field(default_factory=dict)
    maximum_record_sequence: int = 0
    full_ring_required: bool = False
    hardware_work: int = 0
    observed_overflow: bool = False
    observed_wrap: bool = False
    active_traps: int = 0
    prior_records_checked: int = 0
    prior_hardware_irqs: int = 0
    skipped: int = 0
    spurious: int = 0
    deadline: int = 0

    def require(self, condition: bool, detail: str) -> None:
        if not condition:
            raise Core0Error(f"monitor semantic mismatch: {detail}")

    def _count(self, value: int) -> None:
        self.require(self.count <= value <= 1_000_000, "hardware IRQ count decreased or exceeded its range")
        if not self.active:
            self.require(value == self.count, "inactive timer hardware count changed")
        self.count = value

    def _record(self, values: tuple[int, int, int, int], position: int) -> None:
        sequence, clock, pc, cause = values
        self.require(0 < sequence <= 1_000_000 and clock <= MAX_TIME, "ring sequence/time range")
        self.require(pc % 4 == 0 and any(start <= pc < stop for start, stop in self.executable_ranges), "ring PC outside executable ELF range")
        self.require(cause == TIMER_CAUSE, "ring event is not a hardware timer interrupt")
        if not self.active:
            self.require(sequence <= self.count and clock <= self.last_isr, "ring record exceeds stopped IRQ/time witness")
        if position in self.records:
            self.require(self.records[position] == values, "peek/pop changed an unconsumed ring record")
        for previous_position, record in self.records.items():
            if previous_position < position:
                self.require(record[0] < sequence and record[1] <= clock, "ring chronological sequence/time order")
            elif previous_position > position:
                self.require(sequence < record[0] and clock <= record[1], "ring reverse chronological sequence/time order")
        self.records[position] = values
        self.maximum_record_sequence = max(self.maximum_record_sequence, sequence)

    def accept(self, request: Request, response: Response) -> None:
        self.handled += 1
        self.require(response.request_id == request.request_id, "response request ID")
        values, expected_status, expected_values = response.values, 0, None
        self.require(all(type(value) is int and 0 <= value <= U64_MAX for value in values), "response word types/ranges")
        payload = struct.unpack("<" + "Q" * (len(request.payload) // 8), request.payload) if len(request.payload) % 8 == 0 else ()
        if request.magic != b"LMQ9" or request.version != 1 or request.flags != 0:
            expected_status, expected_values = 14, (0, 0, 0, 0)
        elif request.command not in COMMAND_LENGTHS:
            expected_status, expected_values = 17, (0, 0, 0, 0)
        elif len(request.payload) != COMMAND_LENGTHS[request.command]:
            expected_status, expected_values = 16, (0, 0, 0, 0)
        elif request.command == 1:
            expected_values = (0x31304E4F4D4D454C, 7, 1, 0x3FF)
        elif request.command == 2:
            expected_values = (self.handled, self.errors, self.sync, self.last_checksum)
        elif request.command == 3:
            selector, a, b, c = payload
            if c:
                expected_status, expected_values = 14, (0, 0, 0, 0)
            elif selector not in (0, 1, 2, 3):
                expected_status, expected_values = 17, (0, 0, 0, 0)
            elif (selector == 2 and b > 4096) or (selector == 3 and not 1 <= b <= 256):
                expected_status, expected_values = 16, (0, 0, 0, 0)
            elif selector == 3 and not self.active:
                expected_status, expected_values = 21, (self.count, 0, 0, 0)
            else:
                result, quanta, before, after = values
                self._count(before)
                self._count(after)
                if selector == 0:
                    expected_values = ((a + b) & U64_MAX, 0, before, after)
                elif selector == 1:
                    expected_values = (a ^ b, 0, before, after)
                else:
                    if selector == 2:
                        self.require(quanta == b, "fixed work quantum count")
                    else:
                        self.require(0 < quanta <= 1_000_000 and before + b < 1_000_000 and after >= before + b,
                                     "required real hardware IRQ progress during useful work")
                        self.hardware_work += 1
                        self.full_ring_required = b >= 16
                    self.require(result == mix(a, quanta), "independent wrapping foreground checksum")
                    self.last_checksum = result
                    expected_values = values
        elif request.command in (4, 5):
            offset, length = payload[:2]
            if request.command == 4 and payload[2] > 255:
                expected_status, expected_values = 14, (0, 0, 0, 0)
            elif offset > BUFFER_BYTES or length > BUFFER_BYTES - offset:
                expected_status, expected_values = 7, (0, 0, 0, 0)
            elif request.command == 4:
                byte = payload[2]
                self.buffer[offset:offset + length] = bytes((byte,)) * length
                expected_values = (length, (length * byte) & U64_MAX, offset, 0)
            else:
                expected_values = (sum(self.buffer[offset:offset + length]) & U64_MAX, length, offset, 0)
        elif request.command == 6:
            if payload[0] not in (0, 1):
                expected_status, expected_values = 17, (0, 0, 0, 0)
            else:
                mask, delta, before, after = values
                self._count(before); self._count(after)
                self.require(mask == 0 and delta == 1, "authorized synchronous trap context/recovery delta")
                self.sync += 1
                self.active_traps += int(self.active)
                expected_values = values
        elif request.command == 7:
            period = payload[0]
            if not 10_000 <= period <= 1_000_000:
                expected_status, expected_values = 22, (0, 0, 0, 0)
            elif self.active:
                expected_status, expected_values = 16, (0, 0, 0, 0)
            else:
                count, observed_period, deadline, reserved = values
                self.require(0 < count <= 1_000_000 and observed_period == period and 0 < deadline <= MAX_TIME and reserved == 0,
                             "timer start pending/probe/hardware witness")
                self.prior_hardware_irqs += self.count
                self.active, self.period, self.count = True, period, count
                self.head = self.tail = self.overflow = self.last_isr = 0
                self.skipped = self.spurious = 0
                self.deadline = deadline
                self.prior_records_checked += len(self.records)
                self.consumed, self.records, self.maximum_record_sequence = (0, 0), {}, 0
                self.full_ring_required = False
                expected_values = values
        elif request.command == 8:
            before, after, reserved, pending = values
            self._count(before)
            self.require(before == after and reserved == 0 and pending in (0, 1), "shutdown count stability/canonical pending")
            self.active = False
            expected_values = values
        elif request.command == 9:
            mode, index = payload
            if mode not in range(5):
                expected_status, expected_values = 17, (0, 0, 0, 0)
            elif mode != 3 and index != 0:
                expected_status, expected_values = 7, (0, 0, 0, 0)
            elif mode == 0:
                count, head, tail, overflow = values
                self._count(count)
                self.require(head >= self.head and tail == self.tail and 0 <= head - tail <= 16
                    and head + overflow == count and overflow >= self.overflow
                    and self.maximum_record_sequence <= count, "ring head/tail/drop hardware accounting")
                if self.full_ring_required:
                    self.require(head - tail == 16, "required IRQ progress did not fill the event ring")
                self.head, self.overflow = head, overflow
                self.observed_overflow |= overflow > 0
                self.observed_wrap |= head > 16
                expected_values = values
            elif mode == 1:
                skipped, spurious, last_isr, deadline = values
                zero_state = not self.active and self.count == 0 and values == (0, 0, 0, 0)
                self.require(skipped >= self.skipped and spurious >= self.spurious,
                    "skipped/spurious counters decreased within a timer epoch")
                self.require(zero_state or (spurious <= (1_000_000 if self.active else self.count)
                    and self.last_isr <= last_isr < deadline <= MAX_TIME
                    and deadline - last_isr <= self.period
                    and deadline >= self.deadline and last_isr >= self.consumed[1]), "timer ISR/deadline/spurious witnesses")
                self.last_isr, self.deadline = last_isr, deadline
                self.skipped, self.spurious = skipped, spurious
                expected_values = values
            elif mode == 2:
                expected_values = (int(self.active), self.period, *self.consumed)
            elif mode == 3:
                if index >= 16 or (index >= self.head - self.tail and response.status == 7):
                    expected_status, expected_values = 7, (0, 0, 0, 0)
                else:
                    self.require(index < self.head - self.tail, "peek lacks an independently known retained record")
                    self._record(values, self.tail + index)
                    expected_values = values
            else:
                if values == (0, 0, 0, 0):
                    self.require(self.head == self.tail, "empty pop discarded a known ring record")
                else:
                    self._record(values, self.tail)
                    self.require(values[0] > self.consumed[0] and values[1] >= self.consumed[1], "consumed record order")
                    self.consumed = values[:2]
                    self.tail += 1
                    self.head = max(self.head, self.tail)
                self.full_ring_required = False
                expected_values = values
        else:  # EXIT performs shutdown before its final response.
            handled, sync, count, reserved = values
            self._count(count)
            self.require((handled, sync, reserved) == (self.handled, self.sync, 0), "successful EXIT counters/guard result")
            self.active = False
            expected_values = values
        self.require(response.status == expected_status, f"command {request.command} status {response.status} != {expected_status}")
        self.require(values == expected_values, f"command {request.command} result words")
        self.errors += int(expected_status != 0)

    def finish(self, *, integration: bool, terminal: bool = False) -> dict[str, object]:
        self.require(terminal or not self.active, "session did not shut down its timer")
        if integration:
            self.require(self.hardware_work >= 3 and self.active_traps >= 3 and self.sync == 5,
                         "missing combined foreground/hardware/trap exercise")
            self.require(self.observed_overflow and self.observed_wrap and self.tail == self.head and self.prior_records_checked >= 32,
                         "missing overflow, ring wrap, retained-record validation or drain")
        return {"handled_requests": self.handled, "recoverable_errors": self.errors,
            "synchronous_recoveries": self.sync, "final_hardware_irqs": self.count,
            "last_work_checksum": self.last_checksum, "hardware_work_commands": self.hardware_work,
            "active_trap_commands": self.active_traps, "observed_overflow": self.observed_overflow,
            "observed_ring_wrap": self.observed_wrap, "records_checked": self.prior_records_checked + len(self.records),
            "observed_hardware_irqs": self.prior_hardware_irqs + self.count,
            "active_at_terminal_input": self.active if terminal else False}
