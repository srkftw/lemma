<!--
# Gate 7 synchronous-trap construction audit

Status: synchronous-trap acceptance passed at clean implementation
`6c1b6a8ded1e94a822cff9977578b7c292075f75`, tree
`5c53acabde200edd2ef7061ba65830c7c00b5b5b`. The focused O0/O2 matrix passed 32 boots
and both behavioral restore mutants; cumulative Gates 1–7 passed 426 boots and
legacy Task 001 passed separately. Exact commands/hashes are in Task 002 evidence.
This is not a compiler proof, asynchronous-interrupt result, or G1/G2 completion.

## Immutable references

The ISA reference is the official [RISC-V Privileged Architecture, version
20240411](https://docs.riscv.org/reference/isa/v20240411/_attachments/riscv-privileged.pdf),
Machine ISA 1.13, 172 PDF pages, SHA-256
`538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d`.
Relevant PDF sections are 3.1.6.1 (pages 26–27), 3.1.7 (34), 3.1.13–15
(41–42), 3.1.16 (45–46), and 3.3.1–2 (50–51). The corresponding
[machine chapter](https://docs.riscv.org/reference/isa/v20240411/priv/machine.html)
uses different HTML section numbering.

The emulator remains QEMU 11.1.1, revision
`c3d48b7d1e89604920e5b81b91140c2ad39a1943`, archive SHA-256
`079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`.
The following files were inspected from that pinned archive, not a moving branch:

| QEMU source | SHA-256 | Relevant lines |
| --- | --- | --- |
| `target/riscv/tcg/cpu_helper.c` | `172bd47c98c1ea9da48e95e3add0f3b3ac923a4e8a743ab3b785b098f90e4416` | 2046–2077, 2143–2168, 2310–2349 |
| `target/riscv/tcg/op_helper.c` | `1f20356f87c88c648a4262997a548e7c324e3d451ab0606b68944cc9fd779a9c` | 390–407, 426–473 |
| `target/riscv/tcg/insn_trans/trans_privileged.c.inc` | `ac5942e7bc960fecbd2a868710412889767e77ec9de91f57f60487e1918ba3f1` | 27–75, 113–125 |
| `target/riscv/tcg/csr.c` | `631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360` | 3032–3048, 3150–3175, 5999–6005 |
| `target/riscv/cpu_bits.h` | `8aaa29ddd9cdbf94673c62dab5ad904f1d1e56e687e645df717b55af800c4482` | 613–623, 768–776 |
| `target/riscv/cpu.c` | `47a2a33230a5597dfc75294601bae8994a1d00d34cbec6af88a7b01bc3ca7645` | 3345–3369 |
| `target/riscv/tcg/tcg-cpu.c` | `562e89fd688a921f9d48d718c60af73b51a7effaf5ec0577b67d0b177d99a7b9` | 1630–1646 |

Trap entry copies MIE into MPIE, clears MIE, records prior privilege in MPP,
and writes the faulting/interrupted PC to MEPC. MRET restores MIE from MPIE,
sets MPIE, and resets MPP to the least supported privilege. Consequently raw
pre/post `mstatus` equality is not a valid oracle. ECALL from M-mode has cause
11 and zero trap value. EBREAK has cause 3; its trap value may be zero or its
PC. Pinned QEMU reports the PC for ordinary EBREAK. Semihosting is not enabled,
and the probe is not the special three-instruction semihosting sequence.
The pinned TCG feature normalization explicitly disables both Smrnmi and
Smdbltrp. The exact `-cpu rv64` launch therefore reaches the software latch on
the nested-ECALL fixture; this must not be generalized to a CPU with hardware
double-trap redirection enabled.

## Closed compiler and effect contract

The additive profile is `core0-v0.6`; earlier profiles retain their contracts.
The only new source Actions are `trapEcall`, `trapBreakpoint`,
`trapUnexpectedEcall`, and `trapIllegalInstruction`, under
`Lemma.Core0.Memory.Action`. Exact identities/signatures and immediate checked
continuations are required. No source-supplied encoding, address, CSR, exception
cause, extern registration, or runtime callback is admitted.

The Actions have separate transitive `sync-trap` and `machine-state` effects.
Their four closed machine declarations return one `i64` context mask; the
returning Action receives status zero and that mask. Unexpected/illegal fixture
operations do not return in correct execution. The old finite RAM/UART models
reject trap Actions explicitly; they do not simulate hardware traps as success.
All ordinary source algorithms still use genuine elaboration, checked Action
IR, validated CFG/LLVM, and integer LP64 RV64 code.

## Frame, stack, and return

The machine representation is typed Lean instructions, not an embedded assembly
program. Startup masks `mie` and MSTATUS.MIE before other work, establishes the
existing boot/BSS contract, initializes canaries, installs a four-aligned direct
`mtvec`, and places the private trap-stack top in `mscratch`.

| Storage | Address / size | Role |
| --- | --- | --- |
| Foreground stack | `0x807f0000` / 64 KiB | Existing stack; low 16 bytes reserved for canary |
| Trap stack | `0x80810000` / 16 KiB | Two 16-byte canaries; usable top `0x80813ff0` |
| Probe caller context | `0x80815000` / 4 KiB | Private fixed 128-byte ABI caller save |
| Probe stack | `0x80818000` / 4 KiB | Sentinel SP `0x80818800`; 248-byte snapshot above SP |

Private regions do not add IDs to the ordinary checked-memory catalog. The
288-byte aligned frame stores x1 through x31 at `(register_number - 1) * 8`,
including interrupted SP at offset 8 and t0 at 32. CSR offsets are mstatus 248,
mepc 256, mcause 264, mtval 272, and mie 280.

Entry exchanges SP with `mscratch` and branches to stackless fatal status 19
if the received value is zero. It allocates the frame, saves t0 before using it,
and exchanges the interrupted SP out of `mscratch` while setting that latch to
zero. All remaining integer registers are saved before use. GP/TP are saved,
then zeroed before compiled dispatch; the artifact audit must reject any GP/TP
use in compiled code. Floating/vector state is excluded by the target profile.

The compiled dispatcher receives nine scalar words: cause, PC, mstatus, tval,
mie, and both authorized site/continuation pairs. Its ninth argument occupies
offset zero of a separate 16-byte aligned outgoing frame. The two-word Action
return is status in a0 and explicit resume PC in a1. A nonzero status goes to
the bounded fatal finisher (18); success installs the approved PC, restores
captured/validated mstatus and mie, and restores all integer registers.

The final tail restores t0, releases the frame, resets `mscratch` to trap-stack
top, reloads SP from its saved slot with SP as its own base, and executes MRET.
The 16,352-byte usable trap stack must cover the 288-byte frame, 16 outgoing
bytes, and the measured compiled dispatch chain, at most 16,048 bytes. Canaries
are observations, not substitutes for a static/resource bound.

Non-nesting is a software contract. Masking interrupts does not suppress
synchronous exceptions. The zero latch catches faults during dispatch; a real
ECALL from compiled dispatch exercises this path. Entry before latch clearing
and the final aligned SP load/MRET after latch resetting presume fault-free
fixed mapped RAM/CSR accesses, MPRV clear, an approved M-mode continuation, and
no NMI. The implementation does not claim exhaustive double-fault classification
outside that premise or a hardware double-trap extension.

## Source policy and target observations

The compiled source requires `(mstatus & 0x21888) == 0x1800` and `mie == 0`.
Only cause 11 at the exact ECALL site with tval zero, or cause 3 at the exact
EBREAK site with tval zero/PC, may resume. It selects explicit continuation
symbols; each approved instruction is independently checked to occupy four
bytes. Unknown causes/PCs produce five bounded source-encoded UART diagnostic
frames and fatal status 18. Nested entry produces status 19 without another
stack access or compiled call. The finisher uses the declared SiFive-test MMIO.

Returning probes save the actual ABI caller in private RAM, initialize all 31
integer registers to distinct sentinels (SP to a valid private stack), execute
the real trap, and snapshot all 31 registers before comparison clobbers any of
them. Failure bits 0–30 correspond to x1–x31; six canary pairs occupy bits
31–36. Caller ABI state is restored before returning the mask. The quarantined
`restore-s3-from-s4` mutation substitutes the S4 slot for S3 on return. Distinct
sentinels require mask `0x40000`; this is intended to boot, dispatch, and return,
not fail compilation or artifact audit.

The foreground computes a runtime-seeded wrapping 64-bit mix in both a control
fold and an interrupted fold, with zero through 64 iterations and an ECALL plus
EBREAK per interrupted iteration. Runtime seed/count/scenario bytes are supplied
only after building the image. Fourteen software-denial checks run with the
vector active; successful denial requires the expected status/value, unchanged
trap count, and unchanged scratch guard. Normal output includes the actual
checksum, trap count, denial count, and context mask. The host checks an
independent arithmetic oracle and retained raw frames.

`TrapPolicyProbes.lean` directly evaluates 20 source predicates and checks two
conditional local policy lemmas; their dependencies are `propext` and
`Quot.sound`. These are not a proof of trap entry, the frontend, LLVM, or full
compiler correctness. Register/canary target tests, static audits, local lemmas,
and emulator behavior remain distinct evidence. No scheduler, privilege
transition, memory isolation, physical-board result, or G1/G2 completion follows.

-->
