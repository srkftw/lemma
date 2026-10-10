# LemmaSim first-class construction workstream

Status: planned. The original G1-G7 gates and existing 56 software / six physical unit identifiers remain stable. This cross-cutting workstream runs **alongside** them; it is not a claim of completed implementation.

| ID | Deliverable | Depends on | Required exit evidence | Status |
| --- | --- | --- | --- | --- |
| S0 | Canonical machine contract and versioned assumptions | architecture baseline | interface inventory, UNKNOWN fields and reviewable compatibility policy | partial (draft only) |
| S1 | Deterministic virtual motherboard | S0, G1 | real Lean-authored ELF boots, traceable RV64/MMIO/clock/reset events, negative tests | planned |
| S2 | Virtual memory/storage/power fault models | S1, G2/G3 | invalid accesses, flush/crash cutpoints and recovery independently checked | planned |
| S3 | Virtual pen and e-paper controllers | S1, G4 interfaces | physical USB tablet bridge -> virtual controller -> guest driver -> pixels, with ordered traces | planned |
| S4 | Virtual interaction and distribution | S3, G4/G6 | installable Student mode; offline notebook; snapshot and restore | planned |
| S5 | Developer and Laboratory modes | S2-S4 | reproducible replay, fault injection, inspectable device state, no bypass of guest enforcement | planned |
| S6 | Integrated virtual finished machine | S4/S5, G5-G7 | complete documented student workflows; proof and tutor trust boundaries checked | planned |
| S7 | Physical/virtual conformance | S6 and physical board/cartridge | independently captured physical traces meet per-interface equivalence relations | blocked: physical hardware unavailable |

## Rules

- One machine contract governs both embodiments. The virtual device is a permanent product, never an interim development-only test harness.
- Preserve historical `LEMMA_VM.md` boot profiles and Task 001/002 evidence. Do not relabel an existing QEMU smoke test as completed virtual hardware.
- Same guest artifacts and functionality wherever possible; board-specific differences must be narrow, versioned, and conformance-tested.
- Student, Developer and Laboratory modes are one implementation with different host controls. Lab fault injection cannot quietly broaden guest privileges.
- Host-only implementation languages are allowed for simulation infrastructure, but target OS, kernel, runtime, mathematical code and maintained compiler logic retain Lean requirements.
- Every phase has executable pass/fail tests and records provenance. A specification-only check is not device implementation evidence.
- Parameter assumptions and unsourced OEM protocols remain explicitly unverified. `SIMULATED_ONLY` and `PHYSICAL_CONFIRMED` are distinct evidence states.

## Relationship to established gates

G1: capture board/ISA boot profiles, then build S1 in parallel with Core0. G2/G3: connect traps, allocation, capabilities and durability to S2. G4: implement S3 with authentic guest digitizer/display drivers rather than host ink shortcuts. G5-G7: target the identical virtual and physical learning functionality. S4-S6 provide the additional finished LemmaSim distribution, reliability and usability gate; S7 establishes the physical counterpart.

## Initial repository layout

- `LEMMA_MACHINE_CONTRACT.md`: top-level normative machine target.
- `sim/`: host simulation backends, device models, launch profiles and user distribution (currently design scaffold).
- `conformance/`: cross-embodiment input traces, invariants, model tests and recorded evidence (currently design scaffold).
- `docs/plan/LEMMASIM.md`: durable sequencing and evidence policy.

Next implementation slice: version a *minimal canonical motherboard profile*, specify one concrete register-level virtual device and independent oracle, run a Lean-authored RV64 guest operation through it, retain full stimulus/output traces, then add a fail-closed CI check. Do not guess display/OEM values.
