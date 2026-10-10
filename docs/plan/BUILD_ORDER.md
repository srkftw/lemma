# Construction order

All units start **planned**. Dependencies permit useful overlap; gates require their own
integration evidence. Months are concentration windows, not commitments. Task 001 is
a first scalar vertical slice across Stage I, not completion of all Stage I units.
Task 002's accepted Gates 0--10 advance and qualify that foundation and partially advance
units 2.1/2.2 with pinned M-mode boot, traps, timers and a compiled diagnostic
monitor. Task 003 has observed supervisor entry, owned frames, Sv39 user
address spaces, scalar tasks, preemption, capabilities, blocking IPC and a
separately linked volatile buffer service through Gate K. Final O0/O2
qualification and all eight actual push/PR CI jobs passed at implementation
`14cc79be8914a349b729347cc05091aba6ac7ca7`; see its ledger for the separate
clean-worktree sources and retained failures. Final report-head CI and the
owner-authorized merge are subsequent publication observations.
These advance units 2.1–2.5, 2.7–2.8 and 3.1–3.3 within the declared Core0
profile. The managed Lean runtime in 2.6, storage in 3.4–3.8 and
the broader G1/G2/G3 finish lines remain incomplete.

## G1 — Core0, LLVM lowering and LemmaVM

Concentration window: months 1–4. Required result: Audited freestanding execution of the declared Core0 profile.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 1.1 | Architecture and trust baseline | None | Reviewed manifests of architecture, ABI, allowed primitives and host/target trust. |
| 1.2 | Versioned LemmaVM contract | 1.1 | Pinned launcher and machine conformance; explicit incompatible-feature failures. |
| 1.3 | Core0 membership checker | 1.1 | Accepted and rejected elaborated declarations, including indirect forbidden dependencies. |
| 1.4 | Core0 executable semantics | 1.1, 1.3 | Lean reference results for defined arithmetic, layout, memory and primitive boundary cases. |
| 1.5 | LLVM lowering audit and implementation | 1.3, 1.4 | Inspectable supported lowerings and pre/post-optimization runtime dependency accounting. |
| 1.6 | Lean-authored machine primitives | 1.2, 1.4, 1.5 | Disassembly and execution check entry, registers, MMIO and ordering contracts. |
| 1.7 | Freestanding image construction | 1.2, 1.5, 1.6 | Actual ELF boot with linker map, relocations, static initialization and complete provenance. |
| 1.8 | Compiler conformance suite | 1.4, 1.7 | Differential optimized/unoptimized target runs; deliberately defective lowerings are detected. |

## G2 — Boot, runtime, traps, memory and scheduling

Concentration window: months 4–9. Required result: Isolated managed-Lean processes with controlled faults and resource limits.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 2.1 | Boot and machine-mode services | 1.8 | Cold boot, declared firmware handoff, valid stacks and supervisor entry. |
| 2.2 | Traps, timers and diagnostics | 2.1 | Injected interrupts/faults with correct identification, saved state and return. |
| 2.3 | Frames and address spaces | 2.1, 2.2 | Page permissions, guard pages and cross-process/kernel isolation tests. |
| 2.4 | Task contexts and user execution | 2.2, 2.3 | Repeated process switches without register or floating-point-state leakage. |
| 2.5 | Explicit allocators and limits | 2.3 | Alignment, ownership/accounting and controlled exhaustion under stress. |
| 2.6 | Managed Lean runtime | 1.8, 2.5 | Representative ordinary Lean without importing upstream C/C++ target runtime. |
| 2.7 | Scheduling and reclamation | 2.4, 2.6 | Preemption, quotas, cancellation and bounded cleanup preserve specified service budgets. |
| 2.8 | Runtime and isolation qualification | 2.7 | Combined crash, cancellation and exhaustion tests preserve unaffected tasks and recovery. |

## G3 — Capabilities, IPC and persistent storage

Concentration window: months 8–12. Required result: Enforced authority and recoverable acknowledged records within a stated failure model.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 3.1 | Capability model | 2.4 | Explicit grant/attenuation/revocation model with proofs or tests appropriately labelled. |
| 3.2 | Capability enforcement | 3.1, 2.8 | Forged, stale and cross-process handles fail at kernel boundaries. |
| 3.3 | Bounded IPC | 3.2 | Malformed requests, queue bounds, cancellation and process death preserve authority/accounting. |
| 3.4 | Device broker and virtual-device foundation | 3.3, 2.5 | Negotiation, descriptor/buffer ownership and invalid-completion tests; DMA trust explicit. |
| 3.5 | Block-device persistence contract | 3.4 | Reads/writes/flush/error model with reproducible simulated interruptions. |
| 3.6 | Recoverable journal | 3.5 | Acknowledged commits survive allowed interruption schedules without invented records. |
| 3.7 | Object store and migration | 3.6 | Interrupted compaction, transactions and schema changes retain recoverable committed content. |
| 3.8 | Authority and durability qualification | 3.2, 3.7 | Unauthorized writes fail and crash campaigns recover an allowed committed history. |

## G4 — Pen, display, ink and mathematical documents

Concentration window: months 11–17. Required result: Write, edit, save, restart and replay an offline notebook.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 4.1 | Input and display contracts | 3.3 | Coordinate/time/mode/completion negotiation and explicit unsupported operations. |
| 4.2 | VirtualEPD and pen replay | 4.1, 3.4 | Recorded input/clock/completion traces reproduce semantic document state. |
| 4.3 | Ink geometry | 4.2 | Raw samples preserved; smoothing/prediction remains derived and replayable. |
| 4.4 | Rendering and mathematical layout | 2.6, 4.1 | Rasterization, clipping, transforms and notation corpus work at supported scales. |
| 4.5 | Pen-first shell | 4.3, 4.4 | Page creation/editing/navigation works without recognition or an attached keyboard. |
| 4.6 | Mathematical document model | 4.3, 3.7 | Ink, typed expressions, annotations and source anchors retain consistent revision identity. |
| 4.7 | Autosave and document recovery | 4.5, 4.6, 3.8 | Pending/committed state is visible and acknowledged edits survive restart/replay. |
| 4.8 | Offline-writing qualification | 4.7 | Sustained writing under CPU/memory/storage/display pressure without a network. |

## G5 — Exact checking and proof checking

Concentration window: months 13–23. Required result: Correctly scoped, version-bound and reproducible mathematical evidence.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 5.1 | Exercise contract | 4.6 | Goal, domain, assumptions, methods, verifier and assistance policy pinned per submission. |
| 5.2 | Restricted exact checkers | 5.1, 2.6 | Reproducible scoped arithmetic/algebra checking with preserved side conditions and explicit unsupported cases. |
| 5.3 | Lean-authored proof-kernel port | 2.6 | Native checking of a pinned theorem corpus and its full environment/dependency closure. |
| 5.4 | Trusted environments and axiom policy | 5.1, 5.3 | Forged imports, altered goals and prohibited assumptions cannot produce Verified evidence. |
| 5.5 | Structured proof construction | 5.4, 4.5 | Generated proof terms check against the original exact exercise goal. |
| 5.6 | Recognition proposal boundary | 5.1, 4.6 | Ambiguous interpretations retain raw ink and require explicit clarification; fixtures first. |
| 5.7 | Evidence ledger | 5.2, 5.4, 3.7 | Results bind exact submissions/revisions/environments/checkers/limits; edits invalidate prior applicability. |
| 5.8 | Verification qualification | 5.5, 5.6, 5.7 | Adversarial proof/answer corpus preserves Verified/Invalid/NeedsClarification/Unsupported/Indeterminate distinctions. |

## G6 — Semantic textbooks and learner state

Concentration window: months 18–25. Required result: A coherent offline learning sequence with traceable observations and recommendations.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 6.1 | Semantic textbook schema | 5.1 | Edition/source/rights anchors, concepts, examples and exercise references remain navigable. |
| 6.2 | Content compiler and packages | 6.1, 3.7 | Immutable offline packages resolve every asset, exercise and checker reference. |
| 6.3 | Prerequisite and scope graph | 6.1 | Logical dependencies and pedagogical prerequisites are separate and inspectable. |
| 6.4 | Complete reference learning sequence | 6.2, 6.3, 5.8 | A coherent sequence contains no missing material or advertised-but-unsupported checks. |
| 6.5 | Learner-event log | 5.7, 3.7 | Attempts, hints, corrections, abandonment and observed assistance have traceable origins. |
| 6.6 | Learner-state estimator | 6.5 | Same event history and model version reconstruct the same uncertain estimates. |
| 6.7 | Transparent baseline review policy | 6.3, 6.6 | Recommendations are reproducible, explainable, overridable and work without a trained model. |
| 6.8 | Assessment and retention framework | 6.4, 6.7 | Held-out/delayed/transfer tasks and fixed scoring remain outside ordinary tutor/policy authority. |

## G7 — Networking, tutor and learning-policy optimization

Concentration window: months 22–30. Required result: Permissioned connected assistance with offline fallback and separately evaluated learning outcomes.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| 7.1 | Native networking substrate | 3.4 | Bounded transport/protocol tests tolerate loss, malformed traffic and disconnects. |
| 7.2 | Cryptography, identity and safe updates | 7.1, 3.8 | Entropy/authentication/credential boundaries and interrupted-update recovery with reviewed evidence. |
| 7.3 | Permissioned remote-service protocol | 7.2, 3.3 | Only authorized context leaves device; bounded streams, retries and cancellation preserve writing. |
| 7.4 | Tutor and recognizer adapters | 7.3, 5.6, 6.2 | Untrusted outputs remain proposals; actual responses/context/version information are recorded. |
| 7.5 | Bounded assistance orchestration | 7.4, 5.7, 6.5 | Tutor cannot alter evidence, grant itself rights or access prohibited assessment material. |
| 7.6 | Constrained learned-policy pipeline | 7.5, 6.7, 6.8 | Policies use fixed action/reward contracts and can be replayed, compared, disabled and rolled back. |
| 7.7 | Learning-outcome evaluation | 7.6 | Delayed independent performance/transfer with comparable time budgets and uncertainty; no proxy-only success claims. |
| 7.8 | Whole-system qualification | 7.7, 4.8, 5.8 | Complete sessions tolerate service failures, malicious content, limits and restart without fabricated evidence/data loss. |

## Physical branch

The hardware branch joins the shared contracts; no cartridge assumptions enter G1.

| Unit | Construction | Direct dependencies | Required evidence |
| --- | --- | --- | --- |
| H.1 | Physical board boot and firmware boundary | 2.1 | Inventory ROM/DDR/clock/firmware handoff and reach the common supervisor contract. |
| H.2 | Physical interrupts, storage and DMA | H.1, 3.5 | Shared conformance plus physical interruption tests and explicit DMA isolation assumptions. |
| H.3 | OEM/FPGA protocol integration | 4.1 | Actual supplier part/revision/interface package; modes/commands/reset/calibration/fault semantics frozen against it. |
| H.4 | Native pen input and registration | H.3, 4.3 | Full-area actual reporting, registration, pressure/tip detection, dropouts and recovery. |
| H.5 | Physical display and networking backends | H.2, H.3, 7.1 | Shared semantic interface tests and simultaneous physical load operation. |
| H.6 | Physical parity and visible-ink qualification | H.4, H.5, 7.8 | Actual document/evidence parity, end-to-end pen latency and physical recovery measurements. |

The authoritative structured backlog is [construction-units.json](construction-units.json).
Gate changes require explicit evidence; no percentage-complete score substitutes for it.

## Parallel foundational workstream: LemmaSim

The original G1-G7 identifiers, dependency graph and recorded evidence remain stable. In parallel with Core0 and boot work, build permanent **LemmaSim** as a first-class virtual embodiment of the finished Lemma One. A single canonical, versioned machine contract governs both embodiments; virtual motherboard, storage/power, pen/e-paper, distribution modes and cross-embodiment tests have independent exit evidence. See [LEMMASIM.md](LEMMASIM.md) and [../../LEMMA_MACHINE_CONTRACT.md](../../LEMMA_MACHINE_CONTRACT.md). Current status is architectural scaffolding, not functional equivalence achieved.
