# Core0 v0.1 semantics and lowering

This document freezes the deliberately small profile implemented for Task 001.  It
describes executable behavior, not a proof that the compiler preserves that behavior.
The independent model is `Lemma/Core0/Semantics.lean`; finite differential tests are
evidence only.

## Source and checking boundary

The input is an ordinary, safe, monomorphic Lean declaration already installed in a
`Lean.Environment` by the Lean elaborator.  `Lemma.Core0.checkAndLower` reads the
kernel-checked `ConstantInfo`, checks the declaration body, and follows every reachable
direct user call.  It produces a dependency-first typed Core0 tree.  It does not accept
surface syntax or a caller-built demonstration AST.

Runtime parameters and results are exactly `Bool`, `UInt8`, `UInt32`, or `UInt64`.
Function parameters are explicit and scalar.  Proofs, implicit parameters, aggregates,
boxed data, closures, recursion, loops, exceptions, `IO`, arbitrary `extern`,
`implemented_by`, initialization attributes, unsafe/partial/opaque declarations, and
unknown terms are rejected.  An unused host import is irrelevant because only the
reachable declaration graph is traversed.

Each primitive match checks its exact Lean declaration identity, complete scalar
signature, and the standard instance/decider expression introduced by elaboration.
The generated manifest records every dependency-first function signature and
deterministic typed Core0 body, its source-to-LLVM symbol mapping, and stable primitive
IDs with resolved Lean identities, signatures, and the `pure` effect.  The closure
audit cross-checks that data against the normalized and symbol companion artifacts.
A same-named user declaration or custom typeclass instance does not enter the allowlist.

## Scalar semantics and LLVM rules

`UIntN` values are mathematical naturals reduced modulo `2^N`.  LLVM integer values
have the same widths.  `Bool` is a Core0 Boolean and lowers to LLVM `i1`; it is not the
boxed Lean runtime representation.

| Core0 operation | Source semantics | LLVM lowering |
| --- | --- | --- |
| integer literal | value modulo `2^N` | `i8`, `i32`, or `i64` constant |
| `add` | wrapping addition modulo `2^N` | plain `add` |
| `sub` | wrapping subtraction modulo `2^N` | plain `sub` |
| `mul` | wrapping multiplication modulo `2^N` | plain `mul` |
| `and`, `or`, `xor` | fixed-width bitwise operation | `and`, `or`, `xor` |
| equality | equal Boolean or equal normalized unsigned value | `icmp eq` |
| `<`, `<=` | unsigned comparison | `icmp ult`, `icmp ule` |
| widening conversion | preserve unsigned value | `zext` |
| narrowing conversion | retain the low target-width bits | `trunc` |
| `let` | evaluate the pure value, then bind it | SSA value/local mapping |
| conditional | evaluate the selected branch | both pure, total branches lowered followed by `select` |
| direct call | first-order call with the checked scalar signature | direct call to a generated internal symbol |

Eager branch lowering is valid only because this profile is pure, total,
recursion-free, and contains no source memory operation.  Adding effects or partial
operations requires replacing that rule with control flow and versioning this
contract.

No source operation is lowered with `nsw`, `nuw`, `inbounds`, alias promises, or fast
math.  The audit rejects those flags in generated input IR.  The pinned optimizer may
prove and add `nsw`/`nuw` from ranges (notably to bounded harness counters and hexadecimal
digits); the post-optimization audit inventories those inferred flags and still rejects
`inbounds`.  Division, remainder, shifts, complement, floating point, vectors, atomics,
and generic memory access have no Core0 IR constructor and are rejected.  This avoids
importing accidental LLVM poison or a compiler helper whose behavior was not specified.

## Machine boundary

Machine effects do not masquerade as source primitives.  Separate Lean-authored
structured generators provide:

- `_start`: establish the fixed 16-byte-aligned stack, preserve `a0`/`a1`, clear BSS,
  record the boot hart ID and DTB pointer, call `core0_main`, then halt if it returns;
- `core0_io_fence`: an explicit `fence iorw, iorw` around ordered MMIO;
- bounded 16550 polling and byte output at the layout-declared UART region;
- aligned volatile reads from the reserved host-injected input region; and
- fenced 32-bit writes to the SiFive test finisher for success or nonzero failure.

The input record is five little-endian `UInt64` words: magic `LEMMA001`, case ID, and
three root arguments.  The target root ABI is exactly
`UInt64 -> UInt64 -> UInt64 -> UInt64`.  The result frame is
`LEMMA_CORE0/1\nRESULT:<16-hex-case>:<16-hex-result>\n`.

The image deliberately has no global-pointer setup.  LLVM receives
`SmallDataLimit=0`, assembly and linking disable relaxation, the linker script collects
small-data sections explicitly, and the closure audit rejects `gp` instructions and
`R_RISCV_RELAX`.  Any future small-data or relaxation support must establish `gp` before
use and change this reviewed policy.

All maintained target logic is Lean.  The generated LLVM, startup assembly, linker
script, objects, and ELF are build artifacts.  The only permitted pre-link external
edge is LLVM code calling the generated `core0_io_fence`; the final ELF must have no
undefined symbol, dynamic section, interpreter, or relocation.

## Deliberate limits

This slice has no heap, managed Lean ABI/runtime, general memory API, exception model,
general recursion, user-mode isolation, scheduler, filesystem, or proof of compiler
correctness.  Passing the corpus establishes one bounded scalar vertical slice and
does not complete G1.
