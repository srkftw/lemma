# Lemma Silicon Specification v0.1.0

**Status:** normative architectural direction; **not** a verified physical design, approved MPW submission, or demonstration of device parity.  
**Date:** 2026-10-10  
**Precedence:** [Canonical machine contract](../../LEMMA_MACHINE_CONTRACT.md) defines observable behavior; this document constrains its silicon realization. Historical [LemmaVM](../contracts/LEMMA_VM.md) QEMU `virt` addresses and tests **do not** become Lemma silicon addresses by implication.

## 1. Decisions and non-negotiable constraints

1. Lemma One targets one custom, **monolithic RV64 mixed-signal SoC**, developed for multi-project-wafer (MPW) fabrication. Internal blocks remain independently specified, reusable, and physically partitionable for an eventual chiplet design. Chiplets are **not** required for the first tapeout.
2. Hardware source (RTL, schematics, layouts, memories/macros, RF and analog blocks), firmware, and necessary design-flow inputs must be publicly inspectable and redistributable under compatible licenses. An openly described API for an opaque implementation does **not** satisfy this requirement. Every third-party dependency gets provenance, exact revision, license, and an independently rebuildable or explicitly **BLOCKED** status.
3. The **sole exception** is manufacture of the electrophoretic display panel/medium. The controller, host software, power-sequence logic, and redistribution rights for essential waveform data must remain open. Proprietary panel waveforms are not implicitly exempt. Physical passive devices and fabrication services do not become licensed design IP merely through purchase; where process/manufacturing details remain closed, disclose that distinction rather than claim an entirely open fabrication process.
4. Do not seek private documentation, vendor contacts, NDAs or proprietary IP to close specification gaps. Work from public materials and original design. Fabrication submission will eventually require a foundry transaction, separately authorized.
5. **IHP SG13G2 is a provisional process candidate only.** No statement of RF performance, PDK closure, MPW eligibility, die fit, procurement, or open-source signoff is asserted until independently evidenced.
6. LemmaSim remains a **permanent first-class Lemma One embodiment**. Both run one maintained freestanding Lean-authored software stack against the same versioned observable machine. Functional equivalence requires interface-specific traces and measured physical conformance; browser convenience paths must not bypass guest devices.
7. Maintain the existing `docs/contracts/LEMMA_VM.md` historical QEMU profiles unmodified. This specification does not retroactively qualify hardware, RF or a panel.

## 2. Scope and version semantics

**Frozen at v0.1.0:** architectural commitments, module boundaries, ownership, openness policy, methods for change, required contracts, and evidence gates.  
**Not frozen:** exact RV64 extension set, ISA privilege version, cache geometry, SoC addresses, SRAM and external RAM sizes, clock rates, bus protocols, package/pinout, voltages, panel geometry and waveforms, RF band/channel configuration, target frequencies, area, power, analog performance or MPW date. They are **UNKNOWN**, never inferred from QEMU `virt` or proposed components.

A change to guest-visible behavior requires a versioned amendment to the canonical machine contract, migration rules for durable formats, compatible simulator/device models and conformance vectors. Silicon-only changes require a new implementation revision; breaking module interfaces require a new module-interface version. Candidate process substitutions are allowed without guest ABI changes.

## 3. Logical SoC partition and required interfaces

| Block | Ownership and first meaningful construction | Stable boundary to define | Physical concerns |
| --- | --- | --- | --- |
| RV64 compute | Open core/RTL; boot a genuine Lean-produced freestanding image | ISA/CSR/traps, instruction memory, MMU/PMP, interrupt and debug contracts | clocks, reset, timing, core-area |
| Interconnect/security | Open address decoder, bus fabric, DMA and access controls | bus ordering, transaction IDs, faults, endianness, barriers, capability-to-DMA authorization | arbitration, crossings, isolation |
| Memory | Open ROM image, SRAM implementation and external RAM controller if needed | memory map, cache/DMA coherence, reset retention, ECC/errors, write ordering | open macro availability, pads, timing |
| Boot/recovery | Immutable/open boot source and recovery mechanism | reset vector, image identity, fault/retry/rollback, boot-device transport | nonvolatile bootstrap, ROM masks |
| Pen | Open electrode/readout design and digitizer controller | sample frames, timestamp, coordinate calibration, pressure/hover capabilities, overflow/error | sensing SNR, ADC, shielding, display stack |
| Electrophoretic display | Custom open pixel/update/waveform engine | framebuffer ownership, update queues, refresh/busy/completion/errors and reset | panel power, VCOM, waveforms, external panel pins |
| Wi-Fi 6 | Open 802.11ax MAC/baseband and original RF where necessary | host queues, authentication boundaries, DMA, status, link and faults | bands, synthesizers, PA/LNA, ADC/DAC, certification |
| Bluetooth 5.4 | Open Bluetooth LE host/controller/PHY | HCI or versioned equivalent; supported roles/features, timing, pairing and faults | RF/coexistence, interop, qualification |
| Companion link | Open transport and protocol | discovery, reconnection, acknowledgements, save/flush ordering | physical interface and pin budget |
| Debug/measurement | Open trace, counters, fault injection and test access | privilege limits, event schema, capture/replay | DFT access, test fixtures |

Module contracts MUST enumerate register layout, field semantics, endian/width/alignment, state transitions, accepted/rejected commands, ordering, interrupts, timing bounds, reset/power behavior, errors, DMA permissions and conformance observations before those values are declared frozen. An unassigned register or address remains **TBD**, not implicitly zero.

## 4. Monolithic now, chiplet-compatible later

All blocks use explicit versioned logical interfaces, transaction ordering, reset handshakes, independent clock-domain descriptions, explicit backpressure and bounded queues. No guest software may depend on a module being on the same die. A future die-to-die bridge must preserve software-visible semantics; any additional permitted latency, loss, or reset behavior is a **declared contract revision**. Do **not** prematurely promise pin-compatible UCIe, an open physical PHY, chiplet packaging availability, or zero additional latency.

The present intended floorplan is **one** digital/analog mixed-signal die, not an already-qualified radio/process solution. External display panel, antenna/matching, power components, and working memory may still be physically necessary; “one chip” means one custom logic/RF SoC die, not an entire tablet made of one part.

## 5. Diskless machine and durable state

No HDD/SSD is required. This does **not** imply zero ROM, zero boot configuration storage, or durability without a backing store. Boot must be possible without a cyclic dependency on an unconfigured interface. Pen capture and immediate ink feedback operate locally when possible. Record durability is acknowledged **only** after a specified flush barrier reaches persistent media (local open journal or companion-backed service); disconnection, timeout, brownout and cold-restart behavior remain observable. Mark strokes as provisional until acknowledged. No unsupported promise of offline persistence. Existing Task 004 storage semantics are preserved unless explicitly versioned.

## 6. Display and pen boundaries

The **manufacturing-only** panel exception does not extend to closed controller firmware. Do not freeze display resolution, pixel format, voltage, waveform tables or pen stack from an unqualified listing. Define a panel-independent guest device first and a versioned open panel adapter second. Panel acceptance requires publicly releasable electrical/interface and waveform inputs or an independently developed driving model qualified against the selected material; unknown manufacturer-specific behavior remains UNKNOWN.

The pen sensing arrangement must demonstrate digitizer/dielectric stack compatibility before physical signoff. For LemmaSim, digitizer sample records and controller state transitions are canonicalized independently of host pointer-rendering shortcuts. Analog origin is modeled with stated error envelopes rather than false bit-exact physical equivalence.

## 7. Dual-radio open-silicon targets (NOT demonstrated)

Wi-Fi 6 / IEEE 802.11ax and Bluetooth 5.4 are end-state targets; no assumption that openwifi already implements complete 802.11ax, nor that an open BLE host establishes a full 5.4 controller or radio. Identify required 2.4/5 GHz modes, channel widths, security, BLE roles/features, coexistence and mandatory/optional compliance before implementation.

All PLL, clocking, data-converter, mixers, receive/transmit path, calibration and digital MAC/PHY dependencies must pass the open design/IP audit. Run RF circuit simulations and a measured silicon characterization campaign before claiming protocol compliance. The provisional SG13G2 PDK has **not** been demonstrated to meet integrated Wi-Fi 6 requirements or to provide full open RF signoff. Radio work must **not** block the compute/display/pen simulator.

## 8. MPW process and EDA qualification ledger

The process choice is a **hypothesis** until objective evidence closes each item below. Every item is initially `UNVERIFIED`:

| Gate | Required public, reproducible evidence |
| --- | --- |
| PDK | Exact commit, redistribution/license audit, complete design-rule and device/corner coverage; document missing proprietary-only signoff steps |
| Cells/memories | Inspectable standard-cell and SRAM collateral, legal integration, synthesis/P&R timing and macro layout; avoid undocumented memory black boxes |
| Digital | Reproducible source → netlist → layout, DRC/LVS, parasitic extraction, static timing, clock/reset analysis, power estimate |
| Analog/RF | Public models, reproducible RF schematic/layout/parasitic simulation and calibrated target requirements |
| Integration | Area and pad-ring budgets, power domains, clock crossings, mixed-signal isolation, DFT and package feasibility |
| Foundry | Public shuttle parameters and submission constraints; **no claimed submission acceptance** without a real acceptance record |
| Packaging | Pinout, RF escape/antenna interface, external RAM, display and pen hookups and test access documented and checked |
| Post-silicon | Actual measurements of boot, pen, display, memory, RF and failure cases cross-referenced to LemmaSim trace corpus |

Statuses are `UNKNOWN`, `BLOCKED`, `UNVERIFIED`, `SIMULATED_ONLY`, `MEASURED`, and `QUALIFIED`; none upgrades by writing prose or creating an empty test. A complete SoC tapeout is prohibited until the required process-specific checks pass.

## 9. Equivalence and provenance

For a declared version `v`, inputs `i` and initial states `s`, the goal is `Obs_v(LemmaSim,i,s) ≈_v Obs_v(Silicon,i,s)`, using the per-device relation in [the canonical contract](../../LEMMA_MACHINE_CONTRACT.md). Exact guest bytes and persistent records where specified; bounded time, asynchronous events, and analog-origin observations only within explicitly defined relations. Browser simulation includes the virtual SoC's guest-visible controller operations, not unmodeled host helpers. Analog channel simulation is not a claim of electromagnetic equivalence.

Every artifact should record: source commit, dependency and PDK/toolchain hashes, versioned machine profile, RTL/firmware hashes, model version, simulator/target backend, input and initial-state hashes, actual commands, raw outputs, outcome and failure evidence. Model tests, Lean proofs, DRC reports, emulator boots, physical measurements and certification are **distinct**.

## 10. Construction order: useful vertical slices

1. **S0: enforceable contracts.** Create versioned machine/module schemas, open-IP inventory, process qualification records; keep UNKNOWN explicit.
2. **S1: bootable silicon SoC.** Synthesize a real RV64 core + boot ROM + RAM + timer/interrupt + debug transport; execute a freestanding Lean image on RTL simulation and retain hashes/traces. Then run open-layout feasibility.
3. **S2: ink end-to-end.** Connect actual guest pen driver, controller event FIFO, pixel/update queue, open panel adapter and durable write/reopen; compare controller traces in LemmaSim. Do not fake pen or screen success through host UI.
4. **S3: diskless companion.** Real versioned link, bounded retransmission, disconnected edits and acknowledged persistence; prove restart behaviors through targeted cutpoint experiments.
5. **S4: open wireless digital.** Deliver a concrete interoperable BLE feature slice, then measured 802.11ax MAC/PHY slices; maintain mandatory feature matrix, not version-name claims.
6. **S5: RF test silicon.** Fabricate RF/analog test structures only after publicly reproducible design/layout validation; measure against predicted parameters.
7. **S6: SoC tapeout.** Integrate and close actual layout and signoff; package, bring up, measure, and run the canonical conformance suite. No inferred success.

Implementation effort is measured by running guest functionality and physical design milestones, not numbers of scaffold tests. Retain historical Task 001–004 evidence and failures intact.

## 11. Open decisions requiring evidence before v0.2.0

- Exact RV64 ISA extensions, privilege and MMU specification; module-specific clocks and reset.
- Concrete bus and chiplet-portable link protocol; interrupt and DMA maps.
- Boot configuration storage, memory size/technology, pad/power budget.
- Releasable panel waveforms, pen stack, display geometry, actual controller electrical front end.
- Bluetooth 5.4 feature subset, 802.11ax bands/channel widths, RF sensitivity/linearity, regulatory scope.
- SG13G2 digital timing and RF viability, open SRAM, full licensing/signoff, shuttle/package eligibility and die area.

**Do not silently answer an open item with an invented number.** Prefer a demonstrable, versioned minimal machine whose functionality can grow without contradicting the canonical contract.
