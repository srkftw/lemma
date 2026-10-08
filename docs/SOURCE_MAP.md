# Source map

Task 001 now occupies only the Core0/compiler/machine rows below.  The remaining rows
are naming guidance for later stages and must not be read as implemented subsystems.

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
| `scripts/` | Host build/run/audit orchestration only, not target compiler/runtime logic |
| `docs/evidence/` | Small checked-in evidence reports; generated bulk artifacts in `build/` |

No target C/assembly scaffolding is needed to reserve directories. No empty fake kernel
modules, `sorry` stubs or target build scripts claiming success should be added.
