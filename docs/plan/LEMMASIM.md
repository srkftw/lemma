# LemmaSim first-class construction workstream

Status: partial — Task004 bounded native notebook subset observed; finished-machine and physical conformance remain incomplete. The original G1-G7 gates and existing 56 software / six physical unit identifiers remain stable. This cross-cutting workstream runs **alongside** them; it is not a claim of completed implementation.

| ID | Deliverable | Depends on | Required exit evidence | Status |
| --- | --- | --- | --- | --- |
| S0 | Canonical machine contract and versioned assumptions | architecture baseline | interface inventory, UNKNOWN fields and reviewable compatibility policy | partial: frozen core/binding 0.1.0 and device/store ABIs; finished contract remains broader |
| S1 | Deterministic virtual motherboard | S0, G1 | real Lean-authored ELF boots, traceable RV64/MMIO/clock/reset events, negative tests | partial: actual one-hart RV64 binding/discovery/replay; no physical board result |
| S2 | Virtual memory/storage/power fault models | S1, G2/G3 | invalid accesses, flush/crash cutpoints and recovery independently checked | partial: owned memory and admitted block/flush/cut recovery |
| S3 | Virtual pen and e-paper controllers | S1, G4 interfaces | physical USB tablet bridge -> virtual controller -> guest driver -> pixels, with ordered traces | partial: pen FIFO/PLIC, guest ink/paper, recorded pressure; physical USB/manual NOT_RUN |
| S4 | Virtual interaction and distribution | S3, G4/G6 | installable Student mode; offline notebook; snapshot and restore | partial: native launch and offline notebook; installer and whole-machine snapshot NOT_BUILT |
| S5 | Developer and Laboratory modes | S2-S4 | reproducible replay, fault injection, inspectable device state, no bypass of guest enforcement | partial: bounded Developer inspection/replay and Laboratory fault workflows |
| S6 | Integrated virtual finished machine | S4/S5, G5-G7 | complete documented student workflows; proof and tutor trust boundaries checked | planned |
| S7 | Physical/virtual conformance | S6 and custom open RV64 SoC embodiment | independently captured physical traces meet per-interface equivalence relations | blocked: physical hardware unavailable |

## Rules

- One machine contract governs both embodiments. The virtual device is a permanent product, never an interim development-only test harness.
- Preserve historical `LEMMA_VM.md` boot profiles and Task 001/002 evidence. Do not relabel an existing QEMU smoke test as completed virtual hardware.
- Same guest artifacts and functionality wherever possible; board-specific differences must be narrow, versioned, and conformance-tested.
- Student, Developer and Laboratory modes are one implementation with different host controls. Lab fault injection cannot quietly broaden guest privileges.
- Host-only implementation languages are allowed for simulation infrastructure, but target OS, kernel, runtime, mathematical code and maintained compiler logic retain Lean requirements.
- Every phase has executable pass/fail tests and records provenance. A specification-only check is not device implementation evidence.
- The active physical dependency is the custom monolithic open RV64 SoC. Earlier board/cartridge and OEM protocol discussions remain historical; no supplier package is assumed for the RTL development backend. Physical analog and panel inputs remain explicitly unverified. `SIMULATED_ONLY` and `PHYSICAL_CONFIRMED` are distinct evidence states.

## Relationship to established gates

G1: capture board/ISA boot profiles, then build S1 in parallel with Core0. G2/G3: connect traps, allocation, capabilities and durability to S2. G4: implement S3 with authentic guest digitizer/display drivers rather than host ink shortcuts. G5-G7: target the identical virtual and physical learning functionality. S4-S6 provide the additional finished LemmaSim distribution, reliability and usability gate; S7 establishes the physical counterpart.

## Initial repository layout

- `LEMMA_MACHINE_CONTRACT.md`: top-level normative machine target.
- `sim/`: host simulation backends, device models, launch profiles and user distribution (implemented Task004 hardware binding and command surface).
- `conformance/`: independent virtual input/device/store observations and checks; physical trace comparison remains unverified.
- `docs/plan/LEMMASIM.md`: durable sequencing and evidence policy.

[Task004 evidence](../evidence/004-lemmasim-durable-ink.md) binds its tested
implementation, retained failures, CI and offline export. The observed notebook
is a foundation for mathematical documents; S6 proof/tutor integration and S7
physical parity remain unfinished. Keep the named partial scopes and do not
replace the existing G1–G7 completion requirements with this subset.
