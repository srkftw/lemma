# Task 003 kernel and isolated services

Current accepted prefix: Gates A and B. Higher gates are not run. This is a
freestanding foundation increment, not a completed operating system.

The distinct boot package links genuinely elaborated Lean firmware and kernel
units, a separate user ELF and a data-only image descriptor. The explicit
bootstrap-M stage executes the maintained kernel policy in M-mode; it does not
establish S/U execution. The normal image excludes development imports. The
frames-development image exposes privileged diagnostic transport over the same
maintained Frames and Batch implementations.

Fresh O0/O2 normal and development builds and complete artifact audits passed.
Each development guest returned 2,214 actual records covering ownership,
read/write, zero reuse, stale references, quota/global exhaustion, recovery,
partial quota/global rollback, a mapping bookkeeping guard and generation
retirement. Capacity restored to512 before the final retirement fixture and
was511 afterward. Installed mappings and translation invalidation remain Gate D.
Both normal profiles accepted the pinned DTB and rejected reserved-memory and
unsupported root-cell fixtures. Every finite observation ended with explicit
host kill/reap of the live guest; no timeout or SIGKILL is labelled normal exit.

The shared UART algorithms were moved into maintained ConsoleDevice. Fresh
legacy monitor acceptance passed18 O0/O2 boots,1598 requests,1411 hardware IRQs,
20 synchronous recoveries and192 records. Scaffold18, Core032, foundation439 and
kernel audit13 host tests passed. Exact closure/index compatibility repairs were
reviewed against generated bodies; the prior failed audits and parser boot are
retained separately and are not relabelled.

The three kernel-checked indexed ownership lemmas concern a mathematical model.
They do not certify the allocator's machine code or LLVM. The target/compiler
trust boundary and physical-device unknowns remain explicit.

See [compact result](003-kernel-isolated-services.json), the gate ledger and
session checkpoint. The full source and artifact hash inventory is retained in
ignored `build/kernel/gateAB/hash-inventory.json`, bound by the compact result.
Acceptance currently used dirty source on merged main `ff4045a79a6fda45f9cd8198587357846530a806`;
clean-worktree qualification and Task003 publication remain outstanding.
