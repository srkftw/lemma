# LemmaSim first-class construction workstream

Status: partial — Task006 adds persistent native sessions, backend-private checkpoints, a canonical-capacity fast binding, synthetic digital panel sequencing and Lean-controlled cooperative power to the earlier notebook. Canonical RTL cold notebook acceptance remains blocked by its ready deadline. Finished-machine and physical conformance remain incomplete. The original G1-G7 gates and existing 56 software / six physical unit identifiers remain stable. This cross-cutting workstream runs **alongside** them; it is not a claim of completed implementation.

| ID | Deliverable | Depends on | Required exit evidence | Status |
| --- | --- | --- | --- | --- |
| S0 | Canonical machine contract and versioned assumptions | architecture baseline | interface inventory, UNKNOWN fields and reviewable compatibility policy | partial: frozen core/binding 0.1.0 and device/store ABIs; finished contract remains broader |
| S1 | Deterministic virtual motherboard | S0, G1 | real Lean-authored ELF boots, traceable RV64/MMIO/clock/reset events, negative tests | partial: actual one-hart RV64 binding/discovery/replay; no physical board result |
| S2 | Virtual memory/storage/power fault models | S1, G2/G3 | invalid accesses, flush/crash cutpoints and recovery independently checked | partial: owned memory and admitted block/flush/cut recovery |
| S3 | Virtual pen and e-paper controllers | S1, G4 interfaces | physical USB tablet bridge -> virtual controller -> guest driver -> pixels, with ordered traces | partial: pen FIFO/PLIC, guest ink/paper, recorded pressure; physical USB/manual NOT_RUN |
| S4 | Virtual interaction and distribution | S3, G4/G6 | installable Student mode; offline notebook; snapshot and restore | partial: persistent native lifecycle and exact fast/RTL subset checkpoints; installer, browser and finished-machine state remain incomplete |
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

## Task006 capability inventory

The columns distinguish behavior from circuitry and physical qualification.
The Task006 checkpoint and evidence report record execution identities; a
model or an interface specification cannot close a later column.

| Subsystem | Specified behavior | Functional model | RTL | Lean guest integration | Physical qualification |
| --- | --- | --- | --- | --- | --- |
| Scalar CPU, M/S/U, Sv39, PMP | Development RV64IM binding, declared clock/counters | QEMU scalar CPU; fixed clock/reset state qualified separately | Existing open processor | Kernel and isolated services; full ISA/CSR parity unfinished | Not closed |
| RAM, fabric, DMA ownership | Checked pool, byte enables, bounded pending beats | External128MiB RAM; configurable latency | Fabric and controller boundary | Deterministic indexed allocation, maintained owner counts, real zeroing/pinning/isolation; canonical boot still being measured | Large physical RAM absent |
| Boot and image update | Development preload explicit; recoverable update required | ELF/DTB preload | Lean-authored reset ROM | Current Lean kernel boot | Nonvolatile update/recovery absent |
| Exact machine checkpoints | Versioned backend-private state | CPU/RAM/controllers/private clock; soft TLB is flushed on restore, arbitrary cache-state continuation unfinished | Verilator caches/TLBs plus wrapper state | Listed in-flight guest suffixes observed exact | Not a physical claim |
| Pen | Full 256 samples, 64-bit sequence/time, loss/resync | FIFO, raw tablet transport, warm reset and MTIME-based watchdog | Synchronous banks and cached head | Driver, immutable ink, warm writing/Save/cold workflow | Tablet/manual conformance unverified |
| Paper/panel digital control | Accepted updates, three synthetic phases and scan clocks | Functional sequencer | Versioned sequencer circuitry | Existing paper driver, regional updates | Synthetic program; panel unqualified |
| Local durable block medium | Checked DMA and acknowledged barrier | Shared captured read/write/barrier outcomes, partial-change failure model and isolated RTL/Wasm replay; fast integration in progress | Existing block controller | Store/recovery and notebook; no host journal interpretation | Physical storage absent |
| Power/reset/controls | Versioned cooperative suspend/wake and reset causes; electrical sequencing/watchdog/brownout still required | Power-v1 state, raw button queue and exact checkpoint | Power-v1 controller and existing reset boundary | Lean kernel policy, separately authorized syscall68; canonical suspend and failed-save recovery, paired cold/wake probe | New controller physical flow not run |
| Companion/USB | Enumeration, bounded framing, reconnect and durable peer required | Development hosted-Lean opaque peer, durable receipts/outbox and lost-ACK restart reconciliation; native RTL launch connected | Existing block path reaches peer; USB controller absent | Guest block/store remains authoritative; asynchronous companion service/USB driver unfinished | Not closed |
| Wi-Fi 6 / Bluetooth 5.4 | Complete digital controllers/MAC/baseband/PHY required | Not built | Not built | Not built | Analog/RF separate; digital unfinished |
| Native/browser distribution | One core and controller-produced display | Local static RTL/Wasm worker, real OPFS initializer, observational private forks and selected exact suffix observed; canonical browser Ready/Save unfinished | Same generated RTL core, no replacement CPU | Same audited guest artifacts; native helper builds images | Manual/native installers and physical conformance unverified |
| Mathematics and learning | G2 and G5–G7 remain required | No host mathematical authority | Machine substrate only | Actual guest rational/polynomial checks, typed revision-bound evidence, authored course/hints, Save and cold full-pixel recovery; managed runtime/proof kernel unfinished | Not closed |
| Courses and learner state, G5/G6 | Immutable packages, rights/source anchors, separate prerequisite graphs and uncertain estimates required | Original authored reference sequence is compiled into the current image; package distribution unfinished | Machine substrate only | Durable attempts/assistance and evidence history; explainable review extension in progress | Not closed |
| Tutor and learning policy, G7 | Permissioned untrusted proposals, held-out assessment and reversible policy required | Communication/provider adapter unfinished | USB/radio path unfinished | Authored local hints are visibly separate from a tutor/provider; policy/evaluation unfinished | Not closed |
| Developer distribution, S4–S6 | Reproducible build/run, inspection, raw devices, snapshots, installation and replay | Native command surface and local browser developer controls; native/Wasm selected suffix exact | Same machine | Native pinned compiler helper; browser-local compiler, package/image update and permission modes unfinished | Not closed |

Standalone pen mapping and improved global-route estimates do not close the
physical column. Detailed routing, complete SG13G2 rule coverage, process
DRC/LVS, extraction and post-route timing remain separate required results.
