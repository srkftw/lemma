# Core0 contract — versioned scalar profiles

Status: Task 001 implements and tests the bounded `core0-v0.1` scalar membership
checker. Task 002 Gate 3 adds the explicitly separate `core0-v0.2` scalar/CFG
profile described below. The broader effectful Core0 contract remains proposed.

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

## Broader proposed profile

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
comparison signedness, shift behavior and memory access preconditions. A profile that does
not admit division or shifts must reject them rather than lower them accidentally.
An admitting profile must establish LLVM's nonzero-divisor and in-range-count premises.
No `nuw`, `nsw`, `inbounds`, alignment or aliasing attributes without a justified premise.
Any admitted division must handle the full source domain, including division by zero,
in accord with the pinned Lean semantics; do not assume C semantics.

Use a Lean reference evaluator/model for the admitted operations and distinguish this
reference from a proof that the compiler preserves semantics. That proof is not claimed
by a passing finite differential corpus.
