# Source map

Tasks001/002 implement the bounded Core0/compiler/machine foundation. Task003
adds the tested owned-page supervisor/User kernel and volatile service. Task004
adds the explicit LemmaSim hardware binding and durable notebook, with source-
specific results in [its evidence report](evidence/004-lemmasim-durable-ink.md). Runtime,
mathematics and tutor rows remain naming guidance, not implemented subsystems.

| Area | Intended responsibility |
| --- | --- |
| `Lemma/Core0/` | Accepted language, declaration checks, reference semantics |
| `Lemma/Compiler/` | Structured LLVM emission and checked Core0 lowering |
| `Lemma/Machine/` | Machine primitives, target layout, startup generation |
| `Lemma/Runtime/` | Stage II runtime; do not stub it in task 001 |
| `Lemma/Kernel/` | Tasks, memory, capabilities, scheduling |
| `Lemma/Services/Store/` | Guest block-backed record engine/codecs, isolated service, short durable Inspect and owner-bound asynchronous Compact receipts |
| `Lemma/Drivers/` | Lean VirtIO block, PLIC, paper and pen hardware drivers |
| `Lemma/Platform/LemmaSim/` | Descriptor/DTB validation, bounded device mediation and isolated deployments |
| `Lemma/Ink/` | Integer geometry, pressure-aware tile rasterization and owned Gray4 surface |
| `Lemma/Documents/Ink.lean` | Versioned raw provenance, page indices and stable-ID edits |
| `Lemma/Applications/Notebook.lean` | Guest toolbar, streamed pages, live ink and asynchronous commit state |
| `sim/host/` | Host-only QEMU hardware models/adapters; no guest notebook or recovery algorithms |
| `sim/rtl/` | Synthesizable CVW compute/fabric and pen/paper/block controller circuits; `host/` supplies clocks and external bytes only |
| `Lemma/Platform/Silicon/` | Lean-authored reset ROM and narrow silicon binding validation; shared kernel/service/application policy |
| `tooling/silicon/` | Exact open core/EDA/PDK inputs, limited hardware notices, synthesis and physical-flow recipes |
| `conformance/silicon/` | Literal RTL device stimuli and independent RTL workload observations |
| `sim/profiles/` | Versioned machine-readable reference binding |
| `conformance/lemmasim/` | Independent offline observations/oracles and raw input fixtures |
| `Lemma/Verify/` | Exact checkers, proof checking and evidence |
| `Lemma/Learn/` | Content, prerequisites, learner observations/policy |
| `Lemma/Tutor/` | Permissioned remote assistance |
| `examples/core0/` | Real Lean source fixtures admitted/rejected by the compiler |
| `tests/core0/` | Scalar inputs, rejection expectations and fail-closed host tests |
| `examples/foundation/` | Elaborated scalar/loop/Action programs, compiled UART/trap/timer routines and the interactive monitor; quarantined profile rejections |
| `tests/foundation/` | Deterministic corpora, reference comparisons, audit mutations and fail-closed host tests |
| `scripts/` | Host build/run/audit orchestration only, not target compiler/runtime logic |
| `docs/evidence/` | Small checked-in evidence reports; generated bulk artifacts in `build/` |

No target C/assembly scaffolding is needed to reserve directories. No empty fake kernel
modules, `sorry` stubs or target build scripts claiming success should be added.

Task 002's source interfaces are `Lemma/Core0/Bounded.lean` and the checked `Action`
syntax in `Lemma/Core0/Memory.lean`, with declared device, trap and timer semantics
in the adjacent modules. `examples/foundation/Monitor.lean` and `MonitorProtocol.lean`
contain compiled command handling and framing; Python only drives and checks it.
`Lemma/Machine/TrapPrimitives.lean` and `TimerPrimitives.lean` generate narrowly
scoped structured machine glue. `scripts/check_foundation.py` runs the gate suite;
`scripts/qualify_foundation.py` revalidates retained evidence and repeat builds.
These are bounded M-mode capabilities, not a managed runtime, scheduler or isolation.
