# Core0 contract — versioned scalar profiles

Status: Task 001 implements and tests the bounded `core0-v0.1` scalar membership
checker. Task 002 Gate 3 adds the explicitly separate `core0-v0.2` scalar/CFG
profile. Task 002 Gate 4 adds the narrowly bounded `core0-v0.3` iteration profile
described below. Task 002 Gate 5 adds the separately selected `core0-v0.4`
checked-memory/Action profile. Task 002 Gate 6 adds the separately selected
`core0-v0.5` polling-device profile. Gate 7 is implementing the separate
`core0-v0.6` synchronous-trap profile below; its target acceptance is pending.
Timers and the broader Core0 contract remain future work.

## Purpose

Accept a precisely bounded subset of ordinary, elaborated Lean declarations and
compile their reachable target code without an allocator or managed runtime.
Core0 membership is about runtime representation/effects and transitive dependencies,
not a keyword search of surface syntax or a blanket ban on host-side Lean libraries.
Proof terms and typeclass elaboration can occur on the host; they must be erased or
lowered soundly so they do not introduce unmanaged runtime dependencies on the guest.

## Implemented scalar profiles

`core0-v0.1` remains the Task 001/Gate 2 profile. It admits the scalar types,
first-order calls, lets, pure conditionals, equality and unsigned comparisons,
wrapping addition/subtraction/multiplication, bitwise and/or/xor, and the six
unsigned widening/truncation conversions exercised by its closed conformance
suite. Its historical checker/exporter commands retain their original meaning;
division, remainder, shifts, and complement remain rejection cases in v0.1.

`core0-v0.2` is additive and must be selected explicitly. It retains every v0.1
primitive and adds fixed-width complement, left and logical-right shift, unsigned
division, and unsigned remainder for `UInt8`, `UInt32`, and `UInt64`. It also
changes conditional lowering to validated branch/phi control flow. Its checked
programs, suite manifests, corpus, model, exporter, and audit carry
`core0-v0.2`; an unknown or mismatched version fails closed.

For v0.2, the pinned Lean semantics are:

- `x / 0 = 0` and `x % 0 = x`;
- shift counts are reduced modulo 8, 32, or 64 as appropriate;
- complement flips exactly the bits of the fixed-width value.

The lowering branches on an exact divisor-zero check and emits LLVM `udiv` or
`urem` only in the nonzero successor. It masks a shift count by width minus one
before LLVM `shl` or `lshr`. The structured LLVM validator checks termination,
targets, reachability, SSA definitions/types, dominance, predecessor/phi sets,
edge availability, returns, and direct-call signatures. The independent artifact
audit additionally checks the source-count masks and that a divisor-zero edge
cannot reach its dangerous operation. These checks and finite differential tests
are not a proof of compiler correctness.

`core0-v0.3` is additive and must also be selected explicitly. It retains every
v0.2 scalar operation and admits exactly one higher-order-looking source construct:

```lean
Lemma.Core0.Bounded.boundedFoldU32
  (budget : Nat)
  (step : UInt32 -> UInt32 -> UInt32)
  (count initial : UInt32) : UInt64
```

This is a compiler-recognized bounded-fold form, not general closure support. The
budget must be a canonical standard `Nat` literal in `0..256`, and `step` must be a
direct reference to a safe, total, monomorphic top-level declaration of exactly the
displayed callback type. The callback and its ordinary helper dependencies pass
through the same transitive Core0 checker. Lambdas, captured environments, runtime
function values, arbitrary higher-order dispatch, partial definitions, and recursive
callback/helper cycles remain rejected.

`count` and `initial` are runtime `UInt32` values. When `count.toNat <= budget`, the
fold invokes `step index accumulator` in ascending index order from zero through
`count - 1`, beginning with `initial`, and returns the final accumulator zero-extended
to `UInt64`. When `count.toNat > budget`, it invokes the callback zero times and
returns `0x8000000000000000 ||| initial.toUInt64`. Bit 63 therefore distinguishes
semantic budget exhaustion from every successful result; bits 62 through 32 remain
zero, and the low 32 bits preserve the unchanged initial value. This tagged outcome
is distinct from the checked model's expression/call traversal-fuel diagnostic and
from a host or QEMU timeout.

The erased budget and callback identity never become a target `Nat`, closure, or
function pointer. Lowering emits a runtime count guard, scalar `i32` index and
accumulator phis, one direct callback call on the body edge, and an actual backedge.
It uses fixed call frames rather than recursive iteration. The profile adds no heap,
arrays, boxed tuples, allocator, exception machinery, or managed Lean runtime.

## Implemented checked-memory profile

`core0-v0.4` is additive and must be selected explicitly with the v0.4 checker.
It preserves v0.1--v0.3 and adds an explicit, compiler-recognized `Action` syntax.
An Action is closed first-order syntax with statically resolved continuations and
bounded-fold callbacks; it is not `IO`, a general state monad, a runtime closure, or
permission to call arbitrary externs. The checker computes `checkedAccess`,
`ramRead`, and `ramWrite` effects transitively through direct calls and loop bodies.
Scalar profiles reject Actions, and a scalar result cannot conceal an Action effect.

The source operations are `done`, `bind`, `load8`, `load32`, `load64`, `store8`,
`store32`, `store64`, `checkReadRange`, `checkWriteRange`, and the v0.4
`boundedFoldU64`. The fold has the same static-callback and literal-budget discipline
as v0.3, carries fixed scalar state, has a maximum admitted budget of 256, and returns
the checked status `budget-exceeded` without executing its callback when the runtime
count exceeds the declared budget. The logical result is
`{ status : UInt8, value : UInt64 }`; its physical ABI is specified in
`TARGET_ABI.md`.

The fixed region catalog is part of the profile, not caller-supplied authority:

| ID | Name | Base | Length | Class/permission | Widths |
| --- | --- | --- | --- | --- | --- |
| 1 | scratch | `0x80801000` | `0x1000` | ordinary RAM, read/write | 1, 4, 8 |
| 2 | input | `0x81000000` | `0x1000` | ordinary RAM, read-only | 1, 4, 8 |
| 3 | output | `0x80803000` | `0x1000` | ordinary RAM, read/write | 1, 4, 8 |
| 4 | events | `0x80805000` | `0x1000` | ordinary RAM, read/write | 4, 8 |
| `0x70` | image | `0x80000000` | `0x7f0000` | reserved | none |
| `0x71` | stack | `0x807f0000` | `0x10000` | reserved | none |
| `0x80` | UART | `0x10000000` | device | device, denied here | none |
| `0x81` | SiFive test | `0x00100000` | device | device, denied here | none |

Every access evaluates guards in this order: region lookup, class, permission,
width, bounds, alignment. Bounds checking first establishes a valid region interval,
then validates the width, then compares `offset <= length - width`; it never relies
on a potentially wrapping `offset + width`. A pointer and a volatile physical load or
store are constructed only on the success edge. Range preflight performs no physical
access. The fixed status codes are:

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | unknown region |
| 2 | reserved region |
| 3 | device region |
| 4 | read denied |
| 5 | write denied |
| 6 | width denied |
| 7 | out of bounds |
| 8 | misaligned |
| 9 | iteration budget exceeded |

Status 4 is catalogued but unreachable under this exact table because every ordinary
region is readable and class checks precede permission checks. Rejected operations
return zero as their value, do not perform a physical access, and do not append a
model event. Successful modeled loads/stores append one ordered event containing the
operation, region, offset, width, and transferred value. The finite-memory model and
its interval/rejected-write lemmas describe this contract; they are not a proof that
the compiler preserves it.

The v0.4 region API is checked access inside one trusted M-mode image. It is not a
hardware protection boundary against arbitrary privileged code, an allocator, an
address-space system, or a device API. MMIO remains excluded from ordinary RAM and
requires the separately versioned effect and ordering contract below.

## Implemented compiled-device profile

`core0-v0.5` is additive and must be selected explicitly. It retains the complete
v0.4 scalar, Action, and checked-RAM contract and admits exactly four device Actions:
`uartReadStatus`, `uartReadByte`, `uartWriteByte`, and
`uartEnableAndResetFifo`. They denote the pinned ns16550a LSR read, RBR read, THR
write, and fixed FCR `0x07` write respectively. Source code cannot supply an MMIO
base, register offset, width, alignment, volatility flag, or fence policy.

Each admitted device Action lowers to exactly one volatile `i8` access with alignment
one at its fixed address, immediately preceded and followed by the generated
`core0_io_fence` (`fence iorw, iorw`) primitive. Device effects are recorded separately
as `mmioRead`, `mmioWrite`, and `ioOrder`; the checker unions them transitively through
conditionals, direct helper calls, and bounded-fold callbacks. Ordinary RAM access to
the UART region remains status 3 and never becomes a generic MMIO escape hatch.

The v0.5 `boundedFoldU64` maximum is 1,000,000 iterations, while the v0.4 maximum
remains 256. Status 10 is an internal early-stop result consumed by polling helpers and
must not escape the public protocol. The added public terminal statuses are 11
(transmit timeout), 12 (receive timeout), 13 (line error), 14 (malformed frame),
15 (truncated frame), 16 (invalid length), and 17 (unsupported command). Unknown
operations and stale device/effect metadata fail closed.

The fixed Gate 6 root initializes the UART FIFO, transmits
`LEMMA_DEVICE/1\nREADY\n`, and handles exactly two runtime requests received after
boot. Requests use the 16-byte `LMQ6` little-endian header and at most 16 payload
bytes; responses are fixed 24-byte `LMS6` frames. ADD64, XOR64, a distinguishing
RAM-versus-UART branch, and bounded TX stress are admitted. An unsupported command
gets status 17 and preserves framing for the next request; malformed, truncated,
invalid-length, and bounded polling failures terminate with their declared Action
status.

The branch command initializes `scratch+64` to `0x3c`. Selector zero alone writes
`0x5a`; selector one alone sends the raw UART byte `0xa5`. Each selected branch then
reads the marker through checked RAM and returns `(observedMarker << 8) | selector`.
The independent target oracle therefore requires `0x5a00` and `0x3c01`, respectively,
and can observe both the false write and the true branch's marker preservation.

The finite UART and packet models describe register side effects, ordered access
events, polling outcomes, parsing, dispatch, and encoding. Their local lemmas and
executable comparisons do not prove that the frontend or LLVM lowering preserves
those models. This profile is specific to the pinned QEMU machine; it is not a
general driver framework, physical-board port, interrupt implementation, hosted IO,
or managed runtime.

## Synchronous-trap profile under construction

`core0-v0.6` must be selected explicitly. It preserves v0.5 and adds exactly
`Action.trapEcall`, `trapBreakpoint`, `trapUnexpectedEcall`, and
`trapIllegalInstruction`. Each takes an immediate checked `UInt8 -> UInt64 ->
Action` continuation and no caller-selected machine address, instruction, CSR,
cause, or frame pointer. The first two execute fixed authorized traps and return
status zero with a target register/canary mismatch mask. The latter two are
controlled fatal fixtures, not recoverable arbitrary-fault primitives.

The new transitive effects are `sync-trap` and `machine-state`. Scalar wrappers
cannot hide these effects; old Action profiles reject them. Source signatures,
normalized checked nodes, operation catalogs, declared effects, and exact closed
`core0_trap_*` machine declarations must agree. The finite ordinary-memory and
UART models explicitly reject trap Actions rather than pretending to execute
hardware. The v0.5 fold budget and fixed-memory/UART contracts are unchanged.

Added terminal statuses are 18 (unexpected trap), 19 (double fault), and 20
(context mismatch). Status 10 remains internal. The nine-word compiled trap
dispatcher checks cause, exact PC, relevant mstatus bits, mie, and specification-
permitted trap values; only explicit site/continuation pairs may resume. The
machine entry/return and resource premises are in
[`traps-core0-v06.md`](../audits/traps-core0-v06.md). This contract describes the
implementation being qualified, not a compiler-correctness proof or a completed
Gate 7 acceptance run.

## Future profile work

- `UInt8`, `UInt32`, `UInt64`, explicitly represented Boolean values, and literal data.
- First-order monomorphic scalar functions, direct calls, let bindings, conditionals,
  unsigned comparisons, bit operations and wrapping integer addition/subtraction/multiplication.
- Timer interrupts and interrupt-safe synchronization remain later separately
  reviewed machine profiles; v0.5 UART operation is polling-only and v0.6 is
  synchronous, non-nested M-mode trap handling only.
- No floating point, vectors, atomics, dynamic allocation or concurrency in this first profile.
- General recursion and dynamic loops may be rejected initially. Any admitted bounded loop
  needs an explicit representation and lowering; the compiler must not ignore its body.

The first implementation may narrow the profile when justified, but must preserve
nontrivial scalar calls/branches and actual target computation, and document omissions.
Changing the initial subset does not permit changing the RISC-V/Lean/LLVM constraints.

## Reject or require an explicit intrinsic rule

Heap-backed data, capturing closures, boxed values requiring a runtime, reference-count
operations, arbitrary foreign imports, implicit initialization effects, hosted `IO`,
exceptions, unsupported memory access and unresolved calls are rejected on their
reachable target path. The compiler may normalize static constants safely; do not
infer that a whole import needs a runtime simply because the host uses one.

Unknown operations are rejected with declaration/dependency path, unsupported feature
and source location where available. No dummy allocator or empty initializer may make
a rejected program appear supported.

## Source-to-target evidence

Inspect elaborated terms and the actual post-lowering target dependency graph. Audit
optimization-created helpers and residual runtime calls. Intrinsics are accepted by
exact declaration identity, signature, effects and lowering rule; names alone are not proof.
User-defined foreign declarations do not enter the allowlist automatically.

Test dependencies hidden behind helper functions, aliases and imported modules. Renaming
an accepted function must not break compilation; replacing its arithmetic must change its
behavior. Whole-program strings or manually assembled example ASTs are not acceptable substitutes.

## Semantics

State the fixed-width overflow rules, Boolean representation, conversion/truncation rules,
comparison signedness, shift behavior and memory access preconditions. A profile that does
not admit division or shifts must reject them rather than lower them accidentally.
An admitting profile must establish LLVM's nonzero-divisor and in-range-count premises.
No `nuw`, `nsw`, `inbounds`, alignment or aliasing attributes without a justified premise.
Any admitted division must handle the full source domain, including division by zero,
in accord with the pinned Lean semantics; do not assume C semantics.

Use a Lean reference evaluator/model for the admitted operations and distinguish this
reference from a proof that the compiler preserves semantics. That proof is not claimed
by a passing finite differential corpus.
