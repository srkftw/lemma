# Lean export host resources, version 2

`lemma-lean-export-host/2` retains the literal `-j2` argument for direct
kernel/user exports and adds an explicit environment for every Lake build and
export: `LEAN_NUM_THREADS=2`, `LEAN_STACK_SIZE_KB=65536`. These select the pinned
host runtime's documented worker pool and 64 MiB thread-stack reservation.
They do not change target stacks, Lean source semantics, checked lowering,
LLVM arguments, device timing or the maintained RV64 runtime.

The command invoker applies these exact two values after combining the caller's
environment and records only these nonsecret values as `host_environment` on
each actual Lake command. Successful and unsuccessful commands retain that
record. Audit rejects a missing or changed value, including on a dependency
build preceding the exports. Address-space, aggregate RSS, command deadlines
and owned-process cleanup remain independent limits.

The consumed helper hash selects the policy. The exact version-1 helper
`52e96d6d3ec2139dd6c5a12fbc824d65b121af52a81642fa2cb966757a6433fa`
retains version 1, its original arguments and absence of environment evidence.
Pre-helper archives retain their original no-flag commands. Unknown helper
sources, a missing current helper, or a policy inconsistent with the complete
consumed-source inventory reject. Historical artifacts are never rewritten.

The retained recovery16 component first failed during dependency compilation,
before export, with thread creation failure under 8 GiB address space. An
owned-process diagnostic observed the same failure with the worker variable
present and literal child `-j2`; Lake and its child approached the address cap.
The immutable Lean runtime reserves 1 GiB per thread by default. A second
bounded diagnostic changed only the documented stack environment, completed the
same dependency build, and reduced Lake's peak virtual size from 8,142,852,096
to 3,244,695,552 bytes. The original failure remains a failure. This observation
concerns host virtual reservations, not a claim that all 64 MiB of stack is
required or that a worker count bounds the total OS thread count.

A genuine normal/initializer recovery16 component subsequently completed under
the same 8 GiB address and 4 GiB owned-RSS caps. Full linked-image qualification
and connected guest/device execution have separate receipts. Version 1's
previous complete matched15 qualification remains bound to its original source.
