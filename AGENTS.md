# Lemma contributor and agent instructions

## Read before changing code

Read `README.md`, `docs/ARCHITECTURE.md`, the files in `docs/contracts/`,
`docs/plan/BUILD_ORDER.md`, and the assigned task under `codex/prompts/`.
This is a tested, bounded freestanding foundation, not a complete OS. Do not invent successful builds.

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

## Third task's scope

Task 003 is authorized by `codex/prompts/003-kernel-isolated-services.md`.
It extends the earlier task boundaries with a real supervisor kernel, owned
physical pages, Sv39 user address spaces, syscalls, preemptive tasks, capabilities,
blocking IPC and a separately linked volatile buffer service. Preserve every
legacy Core0 profile and check. Keep target policy and algorithms in compiled
Lean; structured machine primitives implement only the declared hardware boundary.
Resume from `docs/plan/003-session-state.md` and `docs/plan/003-gates.json`.
Gates A–K require their own observed results; code existence does not pass a gate.
The managed Lean heap/runtime, filesystem/persistence, networking, graphical
notebook, tutor and physical-board claims remain out of scope. Publish a draft PR
against main. The owner explicitly authorized completion and then a guarded
merge commit for this session; that authorization overrides the original
draft-only instruction after full verification and applicable CI pass. Do not
change repository settings or delete task branches. Leave USGCE untouched.

## Fourth task's scope

Task 004 is authorized by `codex/prompts/004-lemmasim-durable-ink.md`.
It extends the historical restrictions with the `lemma-one-core/0.1.0` and
`lemmasim-virt/0.1.0` profiles, host-only QEMU device implementation, compiled
Lean block/pen/paper drivers, durable records, rasterized ink, isolated notebook
applications and capture/replay. Historical profiles and evidence retain their
original meanings. Target policy, codecs, recovery, ink and notebook remain Lean.
Host C is confined to `sim/host/` and the separately identified QEMU patch; it
must never enter the RV64 link. Resume the current Task 004 checkpoint. Completion
requires a usable persistent notebook, not devices or a bring-up demonstration.
Publish a draft PR against current main; do not merge or inherit Task 003 merge
authorization. Keep physical conformance UNVERIFIED and USGCE untouched.

## Fifth task's scope

Task005 is authorized by `codex/prompts/005-open-silicon-bringup.md`.
Use `task/005-open-silicon-bringup`; preserve the exact PR#6 specification
dependency and its attribution. Implement `lemma-silicon-dev/0.1.0` as a
development backend of first-class LemmaSim. Synthesizable RTL is circuitry;
all target software and compiler policy remain genuinely elaborated Lean.
Host adapters and generated Verilator C++ supply clocks, reset, external memory,
raw input, medium bytes and panel effects only. They never execute instructions,
construct documents or recover journals. QEMU remains the default native
notebook backend. Read `docs/plan/005-session-state.md` before resuming.

The sequence is RTL compute/reset -> existing isolated services -> actual
pen/paper/block controllers -> short durable notebook -> scoped open-flow
feasibility. External simulation RAM is not on-chip SRAM. Track exact core,
tool, library and source identities, unresolved cells and failed observations.
Synthesis, routed-controller feasibility, DRC/LVS and physical conformance
have separate results. Reuse artifacts only after validating their exact consumed
source/tool identities; distinguish literal RTL tests, real guest execution and
physical-flow results. No managed-runtime rewrite, radio, browser rewrite,
fabrication submission, paid infrastructure, supplier outreach or proprietary
closure. The original assignment required a draft PR. The owner subsequently
authorized finishing and a guarded Task 005 merge in this session after relevant
verification and applicable CI pass. Preserve task branches and repository
settings. This does not authorize future merges. USGCE is untouched.

Task 005 acceptance uses short source-bound RTL workloads and independent
observations. The registered controller at a760e5f/2b6ede4 has closed A/B/C,
literal protocols, durable write/edit/Save/cold and failed-FLUSH/cold evidence.
Exact current-controller RTL replay has its own closed PASS receipt. Historical
runs retain their original identities.
Fresh hardware execution using validated unchanged guest ELF sources is not
fresh target compilation. Preserve original FAIL reports when an independently
tested host oracle correction produces a new observation. The checkpoint keeps
synthesis, live global-route timing, incomplete detailed routing, rule-coverage
assessment and cell-only process checks separate. A slower hypothetical STA
clock does not change the development binding or establish physical signoff.

Use unused outputs for the short literal RTL protocol check:

```sh
python3 scripts/check_silicon.py --lane devices \
  --work-dir build/silicon/devices-agent-new --timeout 600 --jobs 2
```

Real isolated-service and notebook acceptance use the existing launcher/checkers
listed in the checkpoint. Literal device tests, host tests and CI passes are
separate from those guest claims. Reuse unchanged artifacts only after exact
consumed-input validation; do not rerun every historical lane for a report edit.

## Sixth task's scope

Task 006 is authorized by `codex/prompts/006-whole-machine-lemmasim.md` and the
owner's whole-machine assignment. Use `task/006-whole-machine-lemmasim`; resume
`docs/plan/006-session-state.md`. It extends earlier task-local exclusions with
state-complete machine sessions, matched fast/RTL bindings, digital devices,
boot/power/recovery, companion/radio, native/browser embodiments and eventual
G2/G5–G7 product work. Keep target policy and algorithms genuinely elaborated
Lean. Host transport/presentation must not implement guest ink, journals,
recovery or mathematical authority. Synthetic panel sequencing is digital
evidence, not physical panel conformance. Report each unfinished subsystem.

Publish a draft PR against current main; do not merge or inherit prior merge
authorization. Preserve historical profiles/results, durable formats, USGCE,
repository settings and unrelated branches. Same-backend exact checkpoints
must retain in-flight work and restore into isolated durable forks. They are
not cold recovery or QEMU/RTL microstate migration. The canonical-resolution
RTL boot timeout and physical routing failures are retained failures, not
implicit passes. Use the checkpoint for the exact final execution identities
and remaining blockers; do not rerun historical workloads for report changes.

## Evidence discipline (all tasks)

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

Task 002 has a separate host suite and incremental target checker. Gates 0–10
have recorded clean-source acceptance at `09c47ba` (full identity in the ledger):

```sh
nix develop --no-write-lock-file --command lake build
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
nix develop --no-write-lock-file --command ./scripts/check-core0.sh \
  --work-dir build/core0/qualification-legacy --clean
```

The focused monitor interface passed historically at clean `8fd45d8`. The current
`--all --stress`, legacy and qualifier passed separately in a cold detached
worktree at `09c47ba`: 482 cumulative/23 legacy boots and 26 raw-session replays.
These do not inherit earlier passes. Follow the task ledger/checkpoint when
resuming. The branch is pushed with an upstream and published as draft stacked
PR #2 against Task 001. Its first actual CI run failed at Gate 3 because the pinned
Lean source was evaluated but not realized in the fresh Nix store. The explicit
realization repair passed all fresh detached acceptance at `09c47ba` and all
three jobs in actual push/PR runs `37825241614`/`37825247231`. Push checks exact
`09c47ba`; PR checks synthetic merge `e292d435...` with the same tree. Later
report-only commits are separate. Preserve historical failure evidence.

The cumulative/stress and qualification commands (the latter requires committed,
clean source) are:

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --stress \
  --work-dir build/foundation/gates1-9-clean --clean --timeout 300 --qemu-timeout 20
nix develop --no-write-lock-file --command python3 scripts/qualify_foundation.py \
  --gate9-dir build/foundation/gates1-9-clean/gate9 \
  --work-dir build/foundation/qualification --clean --timeout 300 --qemu-timeout 20
```

The first detached qualification failed closed on duplicate evidence-role labels;
its valid cumulative/legacy results and failed report remain retained. The fixed
candidate's complete detached rerun passed. Do not relabel earlier artifacts as
outputs of the fix, or infer CI success from the workflow file.

## Task 003 verification and recovery

The A–K milestone is recorded at implementation
`14cc79be8914a349b729347cc05091aba6ac7ca7`, separately from the report-bearing
head and subsequent merge. Read the Task 003 report, ledger and checkpoint
before resuming; historical failures retain their original results. The full
acceptance interfaces use the pinned environment and require clean committed
source and unused output paths:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_kernel.py \
  --work-dir build/kernel/verify-A-E --clean --timeout 300 --qemu-timeout 90 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py \
  --lane F-I --work-dir build/kernel/verify-F-I --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py \
  --lane J --work-dir build/kernel/verify-J --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_architecture.py \
  --work-dir build/kernel/verify-architecture --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_mutations.py \
  --expected-commit "$(git rev-parse HEAD)" \
  --work-dir build/kernel/verify-source-negatives --deadline 2400
```

Keep the separate legacy Core0 and cumulative/stress foundation qualification
above. README contains actual build, boot and ordinary terminal commands;
`docs/evidence/003-kernel-isolated-services-commands.json` lists all acceptance
interfaces. Recover an interrupted campaign using a new output path; never
overwrite or turn a retained FAIL into PASS. A report-only commit may reference
its tested implementation as permitted by the assignment. Do not start the
managed runtime or another implementation task as part of this publication.

## LemmaSim first-class architecture

Read `LEMMA_MACHINE_CONTRACT.md` and `docs/plan/LEMMASIM.md` before any change to the machine, peripheral, pen, display, storage or simulator. LemmaSim is a permanent user-facing virtual Lemma One with Student, Developer and Laboratory modes, all using one canonical versioned machine contract alongside the physical embodiment. Preserve the historical pinned `docs/contracts/LEMMA_VM.md` boot profiles and G1-G7 evidence. No host-side bypass of guest drivers or mathematical authorities; no unfounded claims of physical equivalence, controller compatibility or completed conformance.
