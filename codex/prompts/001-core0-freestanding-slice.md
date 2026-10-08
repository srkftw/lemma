# Task 001 — A real Core0 -> LLVM -> bare-metal RV64 vertical slice

Implement the first executable foundation of Lemma. Work in this repository on the
provided task branch. Read `AGENTS.md`, `docs/ARCHITECTURE.md`, all four contracts in
`docs/contracts/`, `docs/decisions/0001-bootstrap-boundaries.md`, and the Stage I
construction units before editing.

## Objective

Compile a small, precisely declared subset of ordinary Lean 4 source through LLVM
into a freestanding RV64 ELF, boot it on a pinned QEMU RISC-V `virt` machine with
`-bios none`, and produce actual UART results from runtime-dependent computation.
Audit the complete target code/dependency closure. Do not stop at a plan, a documentation
patch, a manually authored LLVM example, or a banner that proves only generated startup.

This is the first scalar slice of G1, not the entire G1 gate, managed Lean, or an OS.

## Non-negotiable constraints

- RISC-V target, LLVM backend, maintained project compiler/target code in Lean 4.
- No target C/C++/Rust/Zig/handwritten assembly, Linux guest, hosted Lean executable,
  OpenSBI default, upstream Lean target runtime, libc/libm/libgcc/compiler-rt/libuv,
  foreign allocator, or undeclared binary. Host dependencies are separate and recorded.
- A small Lean-authored structured primitive generator for startup/CSR/MMIO is allowed.
  Do not hide a complete assembly/C program in a Lean string or bypass source compilation.
- Core0 source must pass through Lean elaboration. Inspect reachable declarations and
  lowered runtime operations. A hand-built toy AST is not the required source pipeline.
- No fabricated execution logs, constant-answer generator, dummy runtime helpers,
  `sorry`/axiom shortcuts, skipped tests reported as passes, or architecture substitutions.

## 1. Audit and pin the actual toolchain

Inspect the chosen immutable Lean source revision and its actual compiler pipeline.
Evaluate the upstream LLVM emitter's availability/build requirements, target layout,
scalar representations, boxing, reference counting, initialization and emitted helpers.
Record concrete file paths, revisions and probe results in `docs/audits/llvm-core0.md`.
Do not assume a command-line option or backend works because documentation names it.

Use the upstream route when it can honestly satisfy this slice. Otherwise implement
a narrow Lean-authored lowering from elaborated declarations or a documented Lean IR
boundary to LLVM, explaining the choice. Do not quietly use Lean -> C -> LLVM.

Replace the unresolved `tooling/toolchain-lock.json` entries with tested immutable
identities and hashes, create `lean-toolchain`/Lake configuration, and provide a
reproducible host environment. Prefer a pinned Nix flake/lock for this user's NixOS
workflow; document the actual Codex-host setup too. Do not use an unpinned `latest`.
Use caches or binary distributions only with recorded identities; do not commit
large upstream checkouts or binaries.

## 2. Implement a small real compiler profile

At minimum support nontrivial `UInt64` functions with parameters, constants, wrapping
arithmetic, unsigned comparisons, let bindings, conditionals and direct scalar calls.
Add `UInt8`/`UInt32` and bit operations as needed for a minimal documented machine boundary.
Reject features not implemented; do not implement a broad managed runtime to avoid rejection.

Create accepted source fixtures under `examples/core0/` and isolated rejection fixtures.
Trace forbidden dependencies through helpers/imports. Account for proof erasure and
static normalization without mistaking host metaprogramming for target allocation.
Use an exact primitive identity/type/effects allowlist, not just symbol-name filtering.

Document semantics and lowering of every accepted operation. Do not attach LLVM
`nsw`/`nuw`/`inbounds`/aliasing/alignment promises without proving or enforcing their
premises. Reject division and shifts outside the supported domain until their full
Lean semantics are deliberately handled. Include a Lean reference evaluator/model.

## 3. Generate and run the first freestanding image

Create the minimal Lean-authored startup/primitive layer, linker layout and static
image. Set a valid aligned stack before calling compiled functions, initialize any
required static storage, handle `gp`/relaxation deliberately, and record boot inputs.
No implicit runtime initializers or memory managers are allowed.

Pin and validate the VM configuration: one RV64 hart, M-mode entry, declared RAM,
UART and loading path, no disk/network, and `-bios none`. Derive/confirm addresses
against the pinned machine/DTB. Declare QEMU's reset trampoline and DTB rather than
claiming that no emulator-provided code exists.

The guest must emit a versioned banner plus a framed computed result. Supply test
inputs after code generation via UART or a reserved, documented test-memory fixture.
Confirm results depend on those inputs and on the actual compiled function bodies.
Keep any input-memory region separate from image/stack. Use bounded polling and
bounded host timeouts; always terminate/reap QEMU.

## 4. Build acceptance tests that detect false success

Provide at least:

- Positive source tests: scalar calls, both branches, zero, maximum-width values,
  overflow wraparound, conversions and the admitted memory/MMIO boundary.
- Negative tests: reachable allocation/boxed data, capturing closures, hosted IO,
  arbitrary extern, unknown operations, hidden helper dependency, initialization
  effects, and unsupported arithmetic. Unused unreachable host imports alone are
  not grounds for rejection. Require useful declaration/dependency diagnostics.
- Actual RV64 differential execution at unoptimized and optimized settings against
  the independent Lean reference, using recorded seeds and runtime-provided inputs.
- Clean-build repetition and artifact hashes. Distinguish byte identity from merely
  repeated behavior; explain nondeterministic metadata rather than suppressing it.
- ELF/code-closure audit: architecture/ABI, entry, segments, relocations, dynamic
  dependencies, undefined symbols, all linked objects/archives, symbols, intrinsics
  and helpers before/after optimization, and their source provenance.
- At least one audit-regression fixture with an unexpected foreign/runtime dependency
  that fails even when statically resolved. Audit itself must fail closed.
- Harness failure tests: missing tools, missing manifest, empty corpus, malformed or
  truncated target output, target timeout and nonzero exits cannot report PASS.
- A source-mutation test showing that changing an accepted function changes guest
  behavior, rather than compiling a canned target program or printing fixed answers.

A zero unresolved-symbol count and a UART banner alone do not satisfy this task.
A finite passing corpus does not prove compiler correctness.

## 5. Deliver a reproducible implementation and bounded evidence

Add actual commands (for example `scripts/check-core0.sh`, `scripts/build-core0.sh`,
`scripts/run-core0.sh`, `scripts/audit-core0.sh`) or a similarly coherent interface,
then document only commands that exist. Run existing scaffold tests as well.
Add CI for the real checks with pinned dependencies/actions, bounded execution and
retained artifact evidence. Green metadata checks must be labelled separately.

Write `docs/evidence/001-core0.md` containing the exact implemented subset, commands
actually executed, toolchain identities, target transcripts, input seeds, artifact
inventory/hashes, dependency findings and limitations. Store bulky artifacts under
`build/` or a retrievable CI artifact. Do not commit secrets, NDA documents or binaries.
Update `AGENTS.md` with runnable checks and adjust the backlog only for demonstrated
work; leave remaining G1 obligations open.

## Scope and stop conditions

Do not build an allocator, scheduler, capabilities, filesystem, pen UI, proof kernel,
recognizer, network stack or tutor in this task. Do not modify GitHub visibility,
licensing, access controls or credentials. Keep the change focused on the scalar slice.

Complete the vertical slice when technically possible. A real external blocker
(e.g. unavailable pinned dependency or denied network access) is not a reason to
fake a pass or substitute forbidden technology: preserve useful implementation,
run all reachable checks, include a minimal reproducer and exact unblock/resume
commands, and mark the result partial/blocked. Do not treat upstream inconvenience
as proof the freestanding goal is impossible.

## Final response

Report implemented files/features, the chosen compilation route and why, commands
actually run with their results, observed guest output, artifact/evidence locations,
remaining limitations and the next smallest construction task. Explicitly state
whether the first freestanding slice passed. Do not declare the entire OS or G1 done.
