# Target ABI — G1 proposal

Status: Task 001 validates the scalar RV64/LP64 bootstrap profile against the pinned
compiler and emitted ELF. Task 002 Gates 2--6 preserve that profile, exercise wider
integer call shapes, add the explicit checked-result ABI, and use it for a compiled
polling UART session. The managed Lean ABI remains future work.

| Field | Proposal |
| --- | --- |
| Triple | `riscv64-unknown-elf`, subject to exact LLVM target spelling |
| Application machine | RV64GC-capable, little endian |
| G1 generated code | Integer-only RV64 subset, no F/D/vector operations |
| G1 calling convention | Standard integer LP64; do not silently mix with LP64D objects |
| Pointer and word width | 64 bits |
| Stack | 16-byte alignment at call boundaries; fixed reserved area initially |
| ELF | Static RV64 ELF, explicit entry, no interpreter/dynamic dependencies |
| Initial privilege | M-mode for the first slice |
| Later privilege | M-mode platform services, S-mode OS, U-mode isolated processes |

Choosing the integer ABI for G1 is a scoped bootstrap choice, not a claim that the
managed Lean ABI has been ported. Record all changes before linking objects from another profile.

## Core0 scalar and checked-result conventions

The v0.1--v0.3 scalar profiles use the standard integer LP64 convention for admitted
`Bool`, `UInt8`, `UInt32`, and `UInt64` arguments/results. Narrow arguments and results
are zero-extended at the explicit project ABI boundary. Calls with more than eight
integer arguments use the psABI stack slots and retain 16-byte call-boundary stack
alignment; the conformance suites keep dedicated non-inlined calls to exercise this.

`core0-v0.4` Actions have the logical result
`{ status : UInt8, value : UInt64 }`. The project LLVM ABI is exactly
`{ i64, i64 }`, returned directly rather than through `sret`; RV64 returns status in
`a0` and value in `a1`. The status word must have bits 63 through 8 clear. Action
callers and the test harness reject a noncanonical status or a mismatched aggregate
shape. This two-word convention is a versioned Core0 ABI only; it is not a general
managed-Lean object layout.

`core0-v0.5` preserves this exact two-register checked-result convention. Its sole
device-session root has no scalar arguments. `core0_main` calls that root, treats
status zero as success, and writes `0x5555` to the fixed SiFive test finisher. A
nonzero status writes `(status << 16) | 0x3333`, allowing the host to distinguish
the bounded terminal cause. The root performs its own compiled UART initialization,
framing, parsing, polling, responses, and final drain; none of those operations are
part of the harness ABI.

The device wire protocol is independent of the Action calling convention. Its request
header is `LMQ6`, version, command, payload length, zero flags, and a little-endian
64-bit request ID. Its response is exactly 24 bytes: `LMS6`, version, status, length
8, zero flags, the echoed request ID, and a little-endian 64-bit value. Protocol bytes
arrive after boot and are never linker or loader inputs.
For the branch command, the result word contains the checked RAM-marker readback in
bits 15..8 and the selector in bit zero: `0x5a00` for false and `0x3c01` for true.

The Gate 5 test image reserves four fixed 4 KiB ordinary regions plus separate image,
stack, UART, and SiFive-test entries as recorded in `CORE0.md`. Those addresses are a
pinned LemmaVM/test-image contract, not arbitrary pointers supplied through the ABI.
Runtime request metadata is loaded from the declared input fixture at `0x81000000`;
it is data, not executable code or a second boot image.

## Gate 7 synchronous-trap ABI

`core0-v0.6` retains the Action `{i64,i64}` return and integer LP64 convention.
Its dispatcher has nine `UInt64` arguments; the machine caller places the ninth
at zero of a 16-byte outgoing frame. The returned a0 is status and a1 is the
explicit authorized resume PC. Four closed no-argument machine primitives
return a 64-bit context-check mask to the checked Action continuation.

The trap frame saves x1–x31, including interrupted SP, and five critical CSR
snapshots before dispatch. Its aligned size is 288 bytes. Dedicated private
storage and exact offsets are specified in
[`traps-core0-v06.md`](../audits/traps-core0-v06.md). Saved GP/TP are temporarily
zeroed for compiled dispatch, whose object code must use neither register;
no relaxation is permitted. MRET architectural changes to mstatus are not
mistaken for arbitrary context corruption. Clean O0/O2 target acceptance is
recorded in Task 002 evidence; asynchronous timer handling is not implied.

## Gate 8 timer ABI

`core0-v0.7` preserves the two-word Action result, full integer trap frame, and
nine-word dispatcher convention. Its seven closed `core0_timer_*`/`core0_irq_*`
machine functions each return one i64. Compare receives one i64 deadline;
restore and interrupt-enable receive canonical i64 0/1 converted from source
Bool. Asynchronous dispatch returns the captured interrupted PC unchanged,
not PC+4. Source timer/critical-section policy remains compiled Lean, not an ABI
stub. See [`timers-core0-v07.md`](../audits/timers-core0-v07.md); its finite
O0/O2 target matrix passed at clean `42674c1`. This does not qualify arbitrary
interrupt handlers, nested execution, or a scheduler.

## Gate 9 monitor wire ABI under construction

`lemma-monitor-v1` preserves the v0.7 machine calling convention. Its versioned
UART requests have a 16-byte header and at most 32 payload bytes; responses have
a 16-byte header and four UInt64 words (48 bytes total), all little-endian.
These are compiled encodings in fixed RAM, not heap-backed target objects.
Only the monitor foreground and existing nine-word timer dispatcher are roots.
The exact framing and failure rules are in
[`monitor-core0-v07.md`](../audits/monitor-core0-v07.md); no target acceptance
is yet claimed for this image.

## Entry and layout

Generate the minimal entry sequence from reviewed Lean-authored primitive definitions.
It must establish a valid stack before any code with a compiler-generated prologue executes,
preserve/document boot inputs, clear required zero-initialized storage, and handle `gp` /
relaxation deliberately. No assumptions about a C runtime having prepared the environment.

Reserve text, readonly data, writable data, zero-initialized storage, stack and any runtime
test-input region in one machine-readable layout. Verify alignment, bounds and non-overlap.
Record ELF entry, load segments, target features, relocations and a linker map. No implied
heap or process environment. Any required compiler helper must be Lean-authored and audited
or the operation must be rejected. Prefer explicit LLVM/LLD tools over a driver that links
hosted startup/default libraries implicitly.

## Provenance

Every linked input has a path, source identity, SHA-256, generation command and purpose.
Track symbols/sections back to Lean source or an explicitly declared generated primitive.
Inspect pre-optimization and optimized IR, as well as object and final image closure.
No unresolved symbols is not enough: known, statically linked unwanted libraries also fail.

Consult the RISC-V psABI and LLVM manuals listed in `docs/SOURCES.md`; freeze the exact
versions and relevant rules in task 001's audit report.
