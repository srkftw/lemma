# Source map

Only planning, scaffold checks and the publishing helper exist initially. The directories
below are a naming guide; task 001 should create only modules it actually implements.

| Area | Intended responsibility |
| --- | --- |
| `Lemma/Core0/` | Accepted language, declaration checks, reference semantics |
| `Lemma/Compiler/` | Core0 normalization, LLVM emission, dependency audit |
| `Lemma/Machine/` | Machine primitives, target layout, startup generation |
| `Lemma/Runtime/` | Stage II runtime; do not stub it in task 001 |
| `Lemma/Kernel/` | Tasks, memory, capabilities, scheduling |
| `Lemma/Services/` | IPC, storage, display/input and networking |
| `Lemma/Ink/` | Stroke/document editing and deterministic replay |
| `Lemma/Verify/` | Exact checkers, proof checking and evidence |
| `Lemma/Learn/` | Content, prerequisites, learner observations/policy |
| `Lemma/Tutor/` | Permissioned remote assistance |
| `examples/core0/` | Real Lean source fixtures admitted/rejected by the compiler |
| `tests/` | Semantic, rejection, artifact, execution and later hardware tests |
| `scripts/` | Host orchestration only, not the Core0 compiler/runtime |
| `docs/evidence/` | Small checked-in evidence reports; generated bulk artifacts in `build/` |

No target C/assembly scaffolding is needed to reserve directories. No empty fake kernel
modules, `sorry` stubs or target build scripts claiming success should be added.
