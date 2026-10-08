# Source map

Tasks 001 and 002 implement the bounded Core0/compiler/machine foundation below.
Runtime, kernel and service rows remain naming guidance for later stages and must
not be read as implemented subsystems.

| Area | Intended responsibility |
| --- | --- |
| `Lemma/Core0/` | Accepted language, declaration checks, reference semantics |
| `Lemma/Compiler/` | Structured LLVM emission and checked Core0 lowering |
| `Lemma/Machine/` | Machine primitives, target layout, startup generation |
| `Lemma/Runtime/` | Stage II runtime; do not stub it in task 001 |
| `Lemma/Kernel/` | Tasks, memory, capabilities, scheduling |
| `Lemma/Services/` | IPC, storage, display/input and networking |
| `Lemma/Ink/` | Stroke/document editing and deterministic replay |
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
