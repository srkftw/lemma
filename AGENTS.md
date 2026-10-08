# Lemma contributor and agent instructions

## Read before changing code

Read `README.md`, `docs/ARCHITECTURE.md`, the four files in `docs/contracts/`,
`docs/plan/BUILD_ORDER.md`, and the assigned task under `codex/prompts/`.
This is a construction scaffold, not a working OS. Do not invent successful builds.

## Non-negotiable boundaries

1. Physical/reference application ISA: RISC-V. No ARM substitute, Linux guest,
   hosted userspace executable, or dependency on default OpenSBI in the G1 boot path.
2. Maintained target software and project compiler/runtime logic: Lean 4.
   Host-only shell/Python/Nix/YAML may orchestrate builds, run tests and inspect artifacts.
   Host tools may use their normal runtimes; those runtimes must not enter the target image.
3. No maintained target `.c`, `.cc`, `.cpp`, `.rs`, `.zig`, `.s`, or `.S` files.
   Lean-authored structured primitive lowering may generate narrowly scoped startup,
   CSR and MMIO code. A C/assembly program hidden in a Lean string is not compliance.
4. Use a genuine Lean elaboration path for source declarations and inspect reachable
   runtime dependencies. A manually constructed demonstration AST or LLVM text printer
   is not a compiler for Lean-authored programs.
5. Audit upstream compiler behavior at an immutable revision before assuming it works.
   A small Lean-authored Core0 backend is allowed when the upstream route is unsuitable;
   record why. Do not replace LLVM with a different backend to simplify the task.
6. No target libc, libm, libgcc, compiler-rt, libuv, pthreads, C++ runtime, upstream
   Lean runtime, arbitrary foreign code, or undocumented stubs. Every intrinsic/helper
   must be supported, documented and accounted for. Unknown means reject, not pass.
7. No `sorry`, `admit`, `sorryAx`, extra axioms, or `native_decide` used to certify a
   trusted property. Negative fixtures may mention forbidden constructs. Such fixtures
   must be quarantined and expected to fail, not imported into the trusted implementation.
8. Preserve the difference between tests, proofs, audits, and physical measurements.
   Green scaffolding tests do not establish freestanding execution or compiler correctness.
9. Do not silently broaden Core0's accepted language. Version contracts, add tests,
   and record any accepted feature with its semantics and lowering.
10. Keep vendor hardware documents and firmware/ISA unknowns explicit. Supplier selection
    is not supply confirmation. Do not use guessed panel or controller specifications.

## First task's scope

Task 001 builds a small scalar Core0 vertical slice through LLVM to QEMU. It is not
permission to implement the scheduler, allocator, managed runtime, UI, verifier,
recognizer, network stack, or tutor. Stay on the task's provided branch; do not
change repository visibility, licensing, branch protection, or credentials.

## Second task's scope

Task 002 is defined by `codex/prompts/002-machine-foundation.md`. It deliberately
extends the Task 001-only boundary with versioned scalar profiles, bounded loops,
checked fixed-region memory and effects, compiled device routines, M-mode traps,
timer interrupts, and a bounded diagnostic monitor. Preserve `core0-v0.1` as a
regression profile and advance through the recorded gates in dependency order.
Task 002 still excludes a managed heap/runtime, scheduler, page-table isolation,
filesystem, proof checker, notebook, networking, tutor, and physical-board claims.
Resume from `docs/plan/002-session-state.md` and `docs/plan/002-gates.json`; do not
infer that a later gate passed from the existence of code or a cached earlier run.

## Evidence discipline

- Generate evidence from real commands, record versions and source revisions, and
  mark blocked/not-run work accurately. Never print fabricated expected logs as results.
- Use fail-closed checks: missing tools, skipped runs, an empty test corpus, malformed
  manifests or unexpected linked objects must not yield an ordinary success.
- A clean undefined-symbol table is necessary, not sufficient. Inspect linked-code
  provenance, code generation before/after optimization, ELF attributes and relocations.
- Do not implement no-op allocation/reference-counting helpers to make the image link.
- Keep bounded CI runs. Kill/reap QEMU on timeout. A timeout is a failure unless a
  narrowly documented target test protocol defines an independently observed success.
- Put large generated outputs under ignored `build/`; retain a small checked-in report
  and a hash inventory, or upload CI artifacts with traceable identifiers.
- Update the construction backlog only to reflect demonstrated work. Task 001 does not
  automatically complete G1 or all eight Stage I units.

## Available checks

Metadata-only checks:

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
```

Host-harness failure tests and the complete pinned target acceptance run:

```sh
nix develop --command python3 -m unittest discover -s tests/core0 -v
nix develop --command ./scripts/check-core0.sh --clean
```

Focused interfaces, run inside `nix develop`, are:

```sh
./scripts/build-core0.sh --opt-level O2 --output-dir build/core0/O2 --clean
./scripts/audit-core0.sh build/core0/O2
./scripts/run-core0.sh --image build/core0/O2/image.elf \
  --output-dir build/core0/O2/manual-run --case-id 1 --arg 0 --arg 0 --arg 0
```

The full check performs real O0/O2 RV64 QEMU boots, negative-source checks,
independent-reference comparisons, clean-directory reproducibility builds, a source
mutation, and an audit-regression link.  Missing tools or evidence fail; there is no
skip-to-success mode.  Run both scaffold checks after changes as well.  The Python
programs are host-only orchestration; compiler and target logic remain Lean.

Task 002 has a separate host suite and incremental target checker. Gates 0–7
have recorded clean-source acceptance; Gate 8 is under construction:

```sh
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 7 \
  --work-dir build/foundation/gate7-check --clean --timeout 300 --qemu-timeout 20
```

These interfaces have actually run. Later phases and `--all` must be judged by
their fresh reports and source identities, not assumed green from an older
prefix. Follow the task ledger/checkpoint when resuming. Full detached-worktree
qualification, integrated monitor acceptance, publication, and actual CI remain
separate Task 002 obligations.
