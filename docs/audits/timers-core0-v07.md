# Gate 8 machine-timer construction audit

Status: finite O0/O2 target acceptance passed at clean implementation
`42674c1ba773454c36c277620e2acd289539e5a2`, tree
`f7bea0b4f126275773bbc84e8fb534849ac6bb35`. The clean cumulative Gates 1--8
run passed 456 boots, including Gate 8's 30 boots and 1,474 positive-corpus real
timer entries; legacy separately passed 23 boots. See Task 002 evidence for
report hashes. This report-bearing edit is not the tested implementation source.
The integrated monitor and detached final qualification remain separate work.

## Immutable hardware references

The emulator is pinned QEMU 11.1.1, revision
`c3d48b7d1e89604920e5b81b91140c2ad39a1943`. Its source archive SHA-256 is
`079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`.
Inspection used that archive, not a moving branch. The generated DTB SHA-256 is
`c9c27a1a5c9a652c5c9daa8109c5109d651dacf502b2b7c6081d63d99849d73f`;
decoded DTS SHA-256 is
`dbc65ed2346dd8aa6ab8f3218639cbe39636f2649201d88f516a7343396b3ec8`.

| Pinned QEMU file | SHA-256 | Inspected lines |
| --- | --- | --- |
| `hw/riscv/virt.c` | `ab1ef03005e1a94c25f6a8c7e1ddb7c44393802a7db13410c5c97603a1ea4920` | 85–90, 600–602, 623–633, 1384–1392 |
| `include/hw/intc/riscv_aclint.h` | `6bd7dac8694d4d8012f1036c00d6b1e9e746d3d7635fc0380d100026e01f7d39` | 74–80 |
| `hw/intc/riscv_aclint.c` | `0b2ba0e01c110141df685e16b1ce98383646f95ec426c92b23ab3313a6cb1b89` | 51–130, 138–167, 192–202, 266–277, 323–336, 374–419 |
| `target/riscv/cpu.c` | `47a2a33230a5597dfc75294601bae8994a1d00d34cbec6af88a7b01bc3ca7645` | 913–920, 1338–1363 |
| `target/riscv/tcg/cpu_helper.c` | `172bd47c98c1ea9da48e95e3add0f3b3ac923a4e8a743ab3b785b098f90e4416` | 351–372, 553–590, 2310–2347 |
| `target/riscv/tcg/csr.c` | `631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360` | 1814–1819, 2292–2308, 3776–3813 |
| `target/riscv/cpu_bits.h` | `8aaa29ddd9cdbf94673c62dab5ad904f1d1e56e687e645df717b55af800c4482` | 613, 617, 806, 828 |

The DTB declares a 10,000,000-Hz timebase at `/cpus` (DTS line 39), CPU 0's
local interrupt controller (55–60), and a `clint@2000000` region of size
`0x10000` with local causes 3 and 7 (194–198). QEMU's compatibility wrapper
constructs ACLINT MSWI and MTIMER devices. Hart 0's 64-bit `mtimecmp` is
`0x02004000`; `mtime` is `0x0200bff8`. Neither address is an ordinary source
memory-region ID. Machine timer cause is `0x8000000000000007`, MTIE/MTIP bit 7,
and global MIE bit 3. No SBI or PLIC call is needed for this local interrupt.

The official [Privileged Architecture 20240411 PDF](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-privileged.pdf)
has SHA-256 `538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d`.
Machine ISA 1.13 §3.2.1, printed pages 49–50 (PDF indices 54–55), specifies
unsigned `mtime >= mtimecmp`, wrapping time, atomic naturally aligned RV64
64-bit accesses, eventual MTIP update, and possible spurious delivery after
rearming. §3.1.9, printed 36–37 (PDF indices 41–42), describes pending/enable
state and re-evaluation after CSR writes and xRET. Masking does not clear MTIP.

QEMU uses its virtual clock, not a guaranteed instruction count or host wall
clock. Reset compare is zero, so startup parks it while interrupts are masked.
A past compare raises pending immediately; a future compare uses `timer_mod`
to replace expiry. The implementation permits architectural delayed clearing
and spurious entries rather than asserting immediate pending-bit equality.

## Closed source and machine interface

The additive profile is `core0-v0.7`. Seven exact checked Actions are admitted:
`timerReadTime`, `timerSetCompare`, `timerReadPending`, `irqSaveDisable`,
`irqRestore`, `timerSetInterrupt`, and `timerProbe`. The two enable arguments
are source Bool values, explicitly widened to canonical i64 at their closed
machine ABI boundaries. Immediate continuations receive UInt8 status and
UInt64 value. All seven primitives return one i64; checked logical status is
zero. Values are actual time, pending 0/1, prior global enable 0/1, context
mask, or zero for setters. No source-selected address, CSR, foreign declaration,
interrupt handler registration, or instruction encoding is admitted.

All operations carry ordered-I/O and machine-state effects; timer and interrupt
state have distinct transitive effect bits. Clock/compare accesses have their
read/write effects. Older finite RAM/UART models explicitly reject timer
Actions. They do not synthesize clock progression or delivery. Source policy,
bounded folds, ring algorithms, and formatting pass genuine Lean elaboration,
checked Action IR, CFG validation, LLVM, and the same freestanding integer RV64
LP64 toolchain. Machine helpers remain typed Lean instruction structures.

The trap frame, private stacks, software non-nesting latch, full x1–x31 save,
and nine-argument dispatcher convention are unchanged from the
[Gate 7 audit](traps-core0-v06.md). Timer dispatch requires MPP=M, MPIE=1,
MIE=0, MPRV=0, exact MTIE, zero trap value, and a four-aligned image PC.
Successful asynchronous dispatch returns the interrupted PC unchanged. The
authorized synchronous sites still return their explicit continuations.
Actual executable LOAD-segment containment is additionally checked from the ELF by
the host; the source uses a conservative image-address interval.

## Deadline, buffer, and synchronization policy

Periods are 1 through 1,000,000 timer ticks. Admitted observations satisfy
`now <= 0x7fffffffffffffff - period`. For a due entry, constant-work rearming
sets `next = now + period` and separately adds `(now - oldDeadline) / period`
to skipped nominal periods. It does not loop, replay missed periods, or add
them to observed hardware entries. An early/spurious entry increments its own
counter and retains the existing future deadline. Every accepted hardware
entry increments the hardware count exactly once.

Sixteen event records contain one-based hardware sequence, actual time,
interrupted PC, and cause. Full-buffer entries are dropped with explicit
overflow count; successful enqueues advance absolute head. Foreground advances
tail and validates each consumed record. Interrupts are non-nested. Foreground
ring operations save/mask global MIE and restore its prior state. Checked
volatile RAM plus ordered external primitive calls prevent cached/reordered
shared accesses. Aligned 64-bit MTIMER accesses have full fences. No A extension,
threading library, allocation, or ISR formatting/UART output is introduced.

Shutdown masks global MIE, clears MTIE, parks compare at all ones, and marks the
source state inactive. It then re-enables global MIE for bounded foreground
work and verifies unchanged hardware count. All ones is a far-future compare,
not a perpetual-disable mechanism across wrap. The explicit half-range domain
and MTIE mask are necessary parts of this contract. Final output reports real
pending state without requiring instantaneous deassertion.

## Optimizer and final-instruction closure

Pinned O2 optimization introduces exactly one `llvm.umin.i64` call in the scalar
`retainedRecords` helper, implementing unsigned `min(head, 16)`. It is a closed
optimizer-created intrinsic, not a source foreign-call capability or linked
runtime helper. The timer audit checks its exact declaration, call, function
shape and optimization/profile placement; O0 does not use it. Machine code and
the undefined-symbol audit must still show no runtime dependency. Existing
optimizer intrinsics retain their separately reviewed contracts.

All seven final timer primitive instruction bodies have explicit canonical
hashes, including the complete asynchronous probe; the disabled-arming mutant
has its sole declared alternate compare-store body. The profile-specific complete
entry body is also bound to a final-instruction
hashes. The all-function CLINT inventory is exactly three aligned 64-bit sites:
startup compare parking, the time reader, and the compare setter. Conservative
constant/alias inference rejects compiled CLINT-derived pointers live across
branches or calls, unsupported transforms, or untracked stores; it is not a
general CFG or arbitrary-pointer proof. The host binds this complete inventory,
not merely its aggregate count. Actual CSR/system operations
are deny-by-default, including base encodings and aliases. Only the fixed illegal
instruction fixture may decode as unknown. Every original compiled function is
checked across local symbol headers before the collision-free Gate 7 compatibility
projection. Neither a symbol rename nor a local PC-relative label may hide a
body from GP/TP/privileged-instruction inspection. Audits also restrict the
hardware ISR's direct caller to dispatch and exclude it from the foreground
call closure; these checks do not amount to a whole-compiler correctness proof.

## Intended distinguishing observations and limits

A 32-byte post-build fixture supplies seed, event goal, period, and scenario.
The foreground checksum is recomputed with interrupts disabled and independently
checked by the host. Target output retains hardware counts, overflow/skipped/
spurious counters, deadline/time/pending observations, context/canary checks,
shutdown counts, and the last sixteen raw physical ring records. The host checks
all retained records; guest code checks every consumed record. The retained
window is not a complete trace of every interrupt.

The asynchronous probe saves its real caller, initializes all integer registers
to sentinels, and enables MIE during a finite countdown loop. It snapshots all
registers before comparisons and restores the caller. One quarantined image
changes only S3 restoration to S4's slot, requiring context mask `0x40000` and
guest status 20. A second changes only the compare store to the far-future
value, requiring absent-event guest status 21. Compilation, audit rejection,
timeout, malformed output, and missing artifacts are not valid detections.

`TimerPolicyProbes.lean` directly evaluates 26 policy predicates and six finite
model examples. Six conditional TimerModel lemmas concern nonwrapping future
deadlines, bounded buffer size, and separate event/skip/overflow accounting.
Their assumptions do not prove the UInt64 implementation, compiler, timer
hardware, interrupt preservation, or whole-program correctness. Real target
tests and structural/disassembly audits remain independently required. No
scheduler, hard-real-time latency, board compatibility, G1, or G2 is claimed.
