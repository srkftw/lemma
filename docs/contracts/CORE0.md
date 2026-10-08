# Core0 contract — v0.1 proposal

Status: Task 001 implements and tests the bounded v0.1 scalar membership checker;
the broader Core0 contract remains proposed.

## Purpose

Accept a precisely bounded subset of ordinary, elaborated Lean declarations and
compile their reachable target code without an allocator or managed runtime.
Core0 membership is about runtime representation/effects and transitive dependencies,
not a keyword search of surface syntax or a blanket ban on host-side Lean libraries.
Proof terms and typeclass elaboration can occur on the host; they must be erased or
lowered soundly so they do not introduce unmanaged runtime dependencies on the guest.

## First accepted profile

- `UInt8`, `UInt32`, `UInt64`, explicitly represented Boolean values, and literal data.
- First-order monomorphic scalar functions, direct calls, let bindings, conditionals,
  unsigned comparisons, bit operations and wrapping integer addition/subtraction/multiplication.
- A small, separately named primitive boundary for startup, bounds/alignment-checked
  fixed memory access, ordered MMIO and bounded polling. Record effects explicitly.
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
comparison signedness, shift behavior and memory access preconditions. Unsupported division
or out-of-range shifts can be rejected rather than lowered with accidental LLVM poison.
No `nuw`, `nsw`, `inbounds`, alignment or aliasing attributes without a justified premise.
Any admitted division must handle the full source domain, including division by zero,
in accord with the pinned Lean semantics; do not assume C semantics.

Use a Lean reference evaluator/model for the admitted operations and distinguish this
reference from a proof that the compiler preserves semantics. That proof is not claimed
by a passing finite differential corpus.
