<!--
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

The columns distinguish behavior, circuitry, guest execution, timing/state,
distribution and physical qualification.
The Task006 checkpoint and evidence report record execution identities; a
model or an interface specification cannot close a later column.

| Subsystem | Specified behavior | Functional model | RTL | Lean guest integration | Fast timing / exact state | Distribution | Physical qualification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Scalar CPU, M/S/U, Sv39, PMP | Development RV64IM binding, declared clock/counters; extension roadmap retained | QEMU scalar CPU | Existing open processor | Kernel and isolated services | Selected counter/reset checks; full guest-issued ISA/CSR and timing parity unfinished | Native and same-core Wasm | Not closed |
| RAM, fabric, DMA ownership | Checked pool, byte enables, bounded pending beats | External128MiB RAM; configurable latency | Fabric and controller boundary | Indexed deterministic allocation, owner accounting, actual zeroing/pinning/isolation | Hardware and wrapper pending beats serialized; full boundary campaign unfinished | Actual8192-frame canonical RTL Ready1.427B/5487.787s; native bundles | Large physical RAM absent |
| Boot, update, identity | Development preload explicit; recoverable authenticated image selection required | Development preload plus immutable ROM/NV medium | BootNV7 transactions and Lean-authored reset ROM | Actual installation/update and ROM image/DTB/BSS handoff; partial-payload and unacknowledged-attempt reset observations; discovery/PMP failures retained; guarded Product PMP/full audit; healthy confirmation pending | Observational ROM/fork state qualified; comprehensive recovery unfinished | Real product build/session/install commands; production authentication unfinished | Physical nonvolatile/trust implementation absent |
| Exact machine checkpoints | Backend-private observational state and private forks | CPU/RAM/controllers/private clocks and captured backing outcomes | Savable caches/TLBs and pipeline/fabric/controller signals | Selected in-flight guest suffixes observed exact | QEMU soft TLB/TB omission remains open; native Pending forks require captured tape | Native and selected same-Wasm browser suffixes | Not a physical claim |
| Pen |256 samples,64-bit sequence/time, loss/resync | FIFO, raw tablet/pointer transport, warm reset watchdog | Banked synchronous FIFO, cached head; changed one-hot refill literal check passed | Immutable guest ink, warm writing/Save/cold path | Selected raw-input/reset suffixes; full timing parity unfinished | Native and browser raw events | Tablet/manual conformance unverified; setup/routing not closed |
| Paper/panel digital control | Accepted updates, three synthetic phases and scan clocks | Functional sequencer | Versioned sequencer circuitry | Real driver and regional updates | Selected phase state preserved; full reset/latency parity unfinished | Controller pixels presented natively/WebGPU/2D | Synthetic program; physical panel unqualified |
| Local durable storage | Checked DMA and acknowledged barrier; partial failure is not rollback | Shared native/QEMU/Wasm read/write/barrier outcome interface | Existing block controller | Actual Store/recovery/notebook | Recorded outcomes/private replay; native Pending exact suffix qualified, portable guest qualification unfinished | Local files and qualified browser-origin OPFS flush | Physical storage absent |
| Power, clocks, interrupts, reset | Cooperative suspend/wake; electrical domains/watchdog/brownout required | Power-v1 plus opt-in Power-v2 watchdog/power-good/brownout | Power-v2 domain cancellation and eight safe reset edges | Lean authorized syscall68 plus real WFI watchdog/cause/epoch guest qualification | Exact RTL safety/reset suffix qualified; Fast-v2 phase qualification and comprehensive timing unfinished | Native and browser controls | Power-domain/CDC/clock implementation unfinished |
| Companion storage/transport | Bounded framing, durable receipts, reconnect and lost-ACK reconciliation | Independent hosted-Lean opaque peer and durable client outbox | Existing block path reaches peer | Actual guest Store→peer barrier→ACK, lost ACK/both restart/cold recovery; target companion service unfinished | Native Pending observational capture and isolated tape suffix qualified; QEMU retry/cache scope limited | Normal companion build/init/serve/client commands | Not closed |
| USB | Enumeration/control/data endpoints, toggle/stall/cancel required | Raw socket transports modeled packets and captured actual EOF/errors | EP0/control/data/toggle/ACK controller | Actual enumeration/lost-ACK packet peer; integrated Store acceptance in progress after Power-v2 fix | Native disconnect/pending safety qualified; attached-peer snapshots rejected | USB6 native development commands; notebook durability qualification pending | Not closed |
| Wi-Fi6/802.11ax | Complete admitted digital MAC/baseband/PHY and calibration status | Not built | Not built | Not built | Not qualified | Not distributed | Analog/RF separate; digital unfinished |
| Bluetooth5.4 | Complete admitted digital controller/link/PHY and coexistence | Bounded manual LE1M packet/link slice; full5.4 feature scope unfinished | Actual independent CRC/whitening/sample exchange, timing, corruption/loss/coexistence/reset/checkpoint slice | Ordinary Lean packet/controller/link objects; whole-machine binding integration pending | Component exact suffix qualified; full link/radio timing/state unfinished | Development component tooling; product path unfinished | Analog/RF separate; digital unfinished |
| Runtime, G2 | Genuine managed-language lowering, lifetime, OOM and isolation | No host runtime performs guest work | Machine substrate | Ordinary records/sum constructors/cases and User4 ByteArray allocation/push/read/COW/real release execute in isolated Arithmetic; course/migration/Save/cold and genuine31-slot OOM PASS; general arrays/strings/closures/recursion unfinished | Legacy scalar checks retained; actual sum/ByteArray OOM preserves ink/isolation | Prepared managed/Sums/Bytes native and source-archived static browser artifacts; historical actual browser Ready deadline FAIL; changed Surface2 run pending | Not a physical claim |
| Mathematics/checking, G4/G5 | Raw ink separate from typed revisions and scoped trusted evidence | No host mathematical authority | Machine substrate | Isolated rational/polynomial service, Protocol4/document5 with preserved older execution histories, revision-bound implementation/resource identity, edited history and cancellation; proof kernel unfinished | Fast real RV64/cold/migration/OOM acceptance; canonical/browser mathematics workflow unfinished | Original course in guest image | Not a physical claim |
| Courses/learner state, G6 | Packages, rights/source anchors, prerequisite graphs and uncertain estimates | Original authored sequence compiled into guest | Machine substrate | Durable ordered attempts/assistance, migrated records, explainable overridable/disabled review; actual cold acceptance | Fast guest observations; no learning-gain inference | Installable immutable packages unfinished | Not a physical claim |
| Tutor/learning policy, G7 | Permissioned untrusted proposals, independent assessment and rollback | Provider/communication adapter unfinished | USB/radio path unfinished | Authored hints distinct from a tutor; policy/evaluation extension unfinished | Not qualified | Not distributed | Not closed |
| Native/browser and developer distribution, S4–S6 | One machine, build/run/inspect/raw events/snapshots/replay and enforced user roles | Local static RTL/Wasm worker and immutable native development closure | Same generated RTL core | Same audited guest; native helper compiles images | Selected native/Wasm sections and same-Wasm suffix exact; browser cold Ready deadline FAIL; Save/course suffixes unfinished | Real OPFS initializer/private forks; standalone installers, browser compiler, role permissions and redistribution terms unfinished | Full-machine conformance unverified |

Standalone pen mapping and improved global-route estimates do not close the
physical column. Detailed routing, complete SG13G2 rule coverage, process
DRC/LVS, extraction and post-route timing remain separate required results.

-->
