# Gate 9 compiled monitor construction contract

Status: under construction, not accepted. Gate 8 is the highest passing gate.
The monitor reuses `core0-v0.7`; it adds neither a source-language primitive nor
machine glue. Its closed category is `test-monitor-image`, ABI `lemma-monitor-v1`.
The elaborated roots are `Monitor.foreground` and the existing nine-word
`Timer.dispatch`. All parsing, dispatch, buffer algorithms and encoding remain
compiled Lean. The only linked objects remain `program.o` and `startup.o`.

## Wire and bounds

Requests are `LMQ9`, version 1, command byte, payload length byte, zero flags,
little-endian UInt64 request ID, then at most 32 payload bytes. The header is
16 bytes. Responses are exactly 48 bytes: `LMS9`, version 1, status byte,
length 32, zero flags, the same ID and four little-endian UInt64 values.
The compiled READY banner is `LEMMA_MONITOR/1\nREADY\n`.

| ID | Command | Payload bytes |
| --- | --- | --- |
| 1 | HELLO | 0 |
| 2 | STATUS | 0 |
| 3 | EVAL | 32 |
| 4 | FILL | 24 |
| 5 | CHECKSUM | 16 |
| 6 | TRAP_TEST | 8 |
| 7 | TIMER_START | 8 |
| 8 | TIMER_STOP | 0 |
| 9 | TICKS | 16 |
| 10 | EXIT | 0 |

HELLO's tag is ASCII `LEMMON01`, bytes `4c454d4d4f4e3031`, loaded little-endian
as `0x31304e4f4d4d454c`. Its other words identify v0.7, machine profile 1 and
the ten-command capability mask `0x3ff`. STATUS reports complete bounded
requests handled (including malformed ones), recoverable errors, synchronous
recoveries and the last work checksum. The current request increments the
handled count before validation/dispatch. Session capacity is 256 requests;
only a successfully checked EXIT returns ordinary status zero to the finisher.

Known bounded headers with wrong magic/version/flags consume their declared
payload, reply 14 and recover. Wrong command length replies 16, unknown commands
17. Oversize payload lengths terminate 16 without a reply; missing input is 12,
partial header/payload is 15. UART statuses 11/13 remain terminal. Internal fold
stop status 10 is consumed, never sent as a public response. Error responses
normally contain four zero words; context/missing-event errors may carry the
observed mismatch/count. Transport/protocol/process/timeout failures are not
credited as successful behavioral feature tests.

Parser scratch offsets are 0--47. The user buffer is disjoint, logical
`[0,3840)` mapped to scratch offsets 256--4095 and initialized to zero. Bounds
establish `offset <= 3840` and `length <= 3840-offset` before addition/narrowing.
A zero-length interval at offset 3840 is valid. FILL rejects values above 255
before truncation and writes only after complete preflight. CHECKSUM is wrapping
UInt64 byte sum. Lifetime counters occupy events offsets 128--152, outside
timer initialization 0--127 and below the low ring guard at 240.
Private events word 160 retains the shutdown-work checksum, seeded from runtime
count, so optimization cannot erase the STOP stability-test work.

## Integration and evidence premises

EVAL selectors add/xor fresh arguments or execute bounded 128-step mixing quanta.
The IRQ-progress selector observes actual hardware count advancement while
running useful work, with a finite one-million-quanta ceiling. Host reference
mixing is independent and based on the reported completed quanta, not elapsed
time. TRAP_TEST invokes only the fixed authorized ECALL/EBREAK primitives and
checks context and the compiled dispatch's actual recovery-count increment.

TIMER_START admits 10,000--1,000,000 ticks (1--100 ms at the pinned timebase),
validates the deadline domain, arms with interrupts masked, witnesses
pending with zero entries, then runs the full asynchronous register probe and
requires a real entry before returning. TIMER_STOP masks, clears MTIE, parks
compare at MAX, marks inactive, and checks stable count during bounded work.
It does not require instantaneous MTIP deassertion. TICKS atomically snapshots
counters/timing/state or peeks/pops a checked ring record under saved/masked MIE,
restoring it before UART formatting. EXIT stops, checks guards, replies and drains.
The immutable hardware references and no-NMI/full-frame/non-nesting premises
remain those of [Gate 8](timers-core0-v07.md).

The monitor's minimum period is deliberately narrower than the lower-level
Core0/Gate 8 deadline policy. An actual development period-one request failed
to return within three seconds (retained at
`build/foundation/gate9-period1-diagnostic-eoo8qb_n`); QEMU was killed/reaped.
Continuous pending delivery can starve foreground progress when ISR work exceeds
the requested period. Requests below 10,000 now receive bounded status 22 rather
than arming. This is an empirically qualified diagnostic policy, not a proof of
worst-case service time or a hard-real-time guarantee.

Acceptance must use differing post-boot request streams against the same ELF,
including malformed frames, denied intervals, real trap recovery, hardware
progression/overflow/wrap, checked records and shutdown. Exact new source/IR/
machine inventories, resource bounds, fresh command results and retained raw
transcripts are not yet available. This document does not establish a general
compiler proof, hard-real-time behavior, isolation, physical compatibility,
managed runtime, scheduler or G1/G2 completion.
